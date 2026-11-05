"""Return repair can rotate a capacitor without moving its supply terminal."""
import copy
import math

import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_local_return_feedback as feedback
from cec_placement_search_domain import rotate_board_point


def fixture(tmp_path, *, back=False, angle=0., offset=(0.,0.)):
    board=pcbnew.CreateEmptyBoard()
    nets={}
    for name in ('LOCAL_SUPPLY','GND'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);nets[name]=net
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('BYPASS');board.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I_MM(11.5,10.))
    for pin,name,x in (('P','LOCAL_SUPPLY',12.),('R','GND',11.)):
        pad=pcbnew.PAD(fp);pad.SetNumber(pin);pad.SetNet(nets[name])
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.5,.5));pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetPosition(pcbnew.VECTOR2I_MM(x,10.));fp.Add(pad)
    # Mirror across the horizontal line through both terminals so their order
    # stays the same while their real layer/footprint transform changes.
    if back:fp.Flip(pcbnew.VECTOR2I_MM(11.5,10.),True)
    fp.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    fp.Move(pcbnew.VECTOR2I_MM(*offset))
    path=tmp_path/'input.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    board=pcbnew.LoadBoard(str(path));fp=board.FindFootprintByReference('BYPASS')
    def xy(item):return [item.GetPosition().x/1e6,item.GetPosition().y/1e6]
    supply=xy(fp.FindPadByNumber('P'));ground=xy(fp.FindPadByNumber('R'));center=xy(fp)
    corners=[rotate_board_point(p,(0,0),angle) for p in ((8,8),(12,8),(12,12),(8,12))]
    box=[min(p[0] for p in corners)+offset[0],min(p[1] for p in corners)+offset[1],
         max(p[0] for p in corners)+offset[0],max(p[1] for p in corners)+offset[1]]
    positions={'BYPASS':(*center,float(fp.GetOrientationDegrees())), 'OWNER':(30.,30.,0.)}
    proof=dict(search_exhausted=True,conclusion='no_legal_immediate_ground_return',
        terminal=dict(ref='BYPASS',pad='R'),pad_center=dict(copper_admission=dict(
            at_mm=ground,diameter_mm=.35,clearance_mm=.2,blockers=[dict(
                kind='pour_first_reservation',layer='In3.Cu',net='POWER',rect_mm=box)])))
    row=dict(cap_ref='BYPASS',owner_ref='OWNER',status='assigned',supply_access_ok=False,
        cap_position_mm=center,cap_supply_position_mm=supply,cap_ground_position_mm=ground,
        cap_orientation_deg=float(fp.GetOrientationDegrees()),owner_position_mm=[30.,30.],
        supply_access_certificate=dict(ground_return=dict(attempts=[dict(error='blocked',evidence=proof)])))
    return path,board,positions,row,box


def pivots(positions,row,**kwargs):
    return [m for m in feedback.move_specs(positions,[row],rotation_degrees=(0,90,180,270),
            max_specs=128,**kwargs) if m.get('transform_basis')=='fixed_supply_pad_rotation']


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('angle',[0.,90.,180.,270.])
def test_loaded_native_supply_pad_stays_fixed_and_return_clears_power(tmp_path,back,angle):
    path,board,positions,row,box=fixture(tmp_path,back=back,angle=angle,offset=(53.,41.))
    before=path.read_bytes();state=copy.deepcopy((positions,row));moves=pivots(positions,row,immovable=['OWNER'])
    assert moves
    fp=board.FindFootprintByReference('BYPASS')
    for move in moves:
        assert set(move['placements'])=={'BYPASS'} and move['requires_native_requalification']
        x,y,rotation=move['position'];fp.SetPosition(pcbnew.VECTOR2I_MM(x,y));fp.SetOrientationDegrees(rotation)
        supply=fp.FindPadByNumber('P').GetPosition();ground=fp.FindPadByNumber('R').GetPosition()
        assert (supply.x/1e6,supply.y/1e6)==pytest.approx(row['cap_supply_position_mm'],abs=1e-6)
        x,y=ground.x/1e6,ground.y/1e6
        envelope=.35/2+.2+.05
        assert not (box[0]-envelope < x < box[2]+envelope and box[1]-envelope < y < box[3]+envelope)
        assert math.dist(move['position'][:2],positions['BYPASS'][:2])<=12
    assert (positions,row)==state and path.read_bytes()==before


@pytest.mark.parametrize('fault',['missing_supply','stale_angle','nonfinite','malformed','fixed_cap','motion_limit'])
def test_no_unbound_fixed_or_overbudget_pivot(tmp_path,fault):
    _,_,positions,row,_=fixture(tmp_path)
    kwargs={}
    if fault=='missing_supply':row.pop('cap_supply_position_mm')
    elif fault=='stale_angle':row['cap_orientation_deg']+=90
    elif fault=='nonfinite':row['cap_supply_position_mm'][0]=float('nan')
    elif fault=='malformed':row['cap_supply_position_mm'][0]='not a coordinate'
    elif fault=='fixed_cap':kwargs['immovable']=['BYPASS']
    elif fault=='motion_limit':kwargs['max_shift_mm']=.1
    assert not pivots(positions,row,**kwargs)


def test_rotation_policy_zero_preserves_translation_domain(tmp_path):
    _,_,positions,row,_=fixture(tmp_path)
    moves=feedback.move_specs(positions,[row],rotation_degrees=(0,),max_specs=128)
    assert moves and all(m['rotation_deg']==0 for m in moves)


def test_supply_pivot_cannot_shift_supply_to_escape_a_second_power_slab(tmp_path):
    _,_,positions,row,box=fixture(tmp_path)
    context=dict(ok=True,state_sha256='bound',rows=[dict(net='POWER',layer='In3.Cu',
        x0=0,y0=0,x1=40,y1=40)])
    assert not pivots(positions,row,reservation_context=context)
