import copy
import math
import pytest
from cec_constraint_seating import contact_poses
from cec_placement_search_domain import rotate_board_point


def cell():
    return dict(cap_ref='CAPACITOR',owner_ref='CHIP',
        cap_position_mm=[0.,0.],cap_supply_position_mm=[-.5,0.],
        cap_ground_position_mm=[.5,0.],cap_orientation_deg=0.,
        owner_supply_position_mm=[1.,0.],owner_ground_positions_mm=[dict(position=[2.,0.])],
        pin_proximity_mode='isolated_tangent_supply',return_gate_mode='absolute_ground_distance',
        pin_proximity_excess_limit_mm=.25,return_limit_mm=.8,
        tangent_target=dict(best_loop=dict(supply_mm=.5)))


def test_contact_seat_hits_electrical_and_courtyard_intersection_not_grid():
    row=cell();before=copy.deepcopy(row)
    obstacles=[(-10.,-10.,1.123456,10.)]
    poses,report=contact_poses(row,forbidden_centers=lambda angle:obstacles)
    assert poses and row==before
    assert poses[0]['position']==(1.123456,0.,0.)
    assert all(p['predicted_supply_mm']<=.73+1e-6 and p['predicted_ground_mm']<=.78+1e-6 for p in poses)
    assert report['checked']<=128 and report['exhaustion_is_no_path_proof'] is False


@pytest.mark.parametrize('turn',[0,90,180,270])
def test_renamed_rotated_translated_domain(turn):
    row=cell()
    def transform(p):
        x,y=rotate_board_point(p,(0,0),turn)
        return [round(x+27,6),round(y-13,6)]
    for key in ('cap_position_mm','cap_supply_position_mm','cap_ground_position_mm','owner_supply_position_mm'):
        row[key]=transform(row[key])
    row['owner_ground_positions_mm'][0]['position']=transform([2.,0.])
    row['cap_orientation_deg']=turn;row['cap_ref']='OTHER';row['owner_ref']='PACKAGE'
    corners=[transform(p) for p in ((-10,-10),(1.123456,-10),(1.123456,10),(-10,10))]
    box=(min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners))
    poses,_=contact_poses(row,forbidden_centers=lambda angle:[box])
    assert poses[0]['position']==(*transform([1.123456,0.]),float(turn))


def test_bounded_geometry_checks_and_no_missing_obstacle_waiver():
    poses,report=contact_poses(cell(),forbidden_centers=lambda angle:[],feasible=lambda pose:False,max_checks=3)
    assert not poses and report['checked']==3
    boxes=[(-2,-.35+i*.01,3,-.345+i*.01) for i in range(70)]
    poses,report=contact_poses(cell(),forbidden_centers=lambda angle:boxes,max_obstacles=1)
    assert not poses and report['truncated_orientations']==4


@pytest.mark.parametrize('field,value',[('cap_orientation_deg',float('nan')),
    ('cap_supply_position_mm',['broken',0]),('return_limit_mm',-1),
    ('pin_proximity_excess_limit_mm',None),('owner_ground_positions_mm',[])])
def test_invalid_measurement_fails_closed(field,value):
    row=cell();row[field]=value
    assert contact_poses(row,forbidden_centers=lambda angle:[])[0]==[]


def test_unsupported_loop_contract_left_unchanged():
    row=cell();row['pin_proximity_mode']='dual_via_in_pad_complete_loop'
    assert contact_poses(row,forbidden_centers=lambda angle:[])[1]['reason']=='unsupported_contract'


def test_no_bypass_when_courtyard_input_invalid():
    poses,report=contact_poses(cell(),forbidden_centers=lambda angle:[(0,0,float('nan'),1)])
    assert not poses and report['reason']=='invalid_courtyard_domain'


def test_finite_policy_rejects_invalid_limits():
    with pytest.raises(ValueError):contact_poses(cell(),forbidden_centers=lambda angle:[],max_checks=True)


def test_infeasible_electrical_disks_never_relax_limit():
    row=cell();row['owner_ground_positions_mm']=[dict(position=[200,200])]
    poses,report=contact_poses(row,forbidden_centers=lambda angle:[])
    assert not poses and report['checked']==0


def test_distant_furniture_does_not_consume_local_obstacle_budget():
    poses,report=contact_poses(cell(),forbidden_centers=lambda angle:[(100+i,100,101+i,101) for i in range(100)])
    assert poses and report['truncated_orientations']==0


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',[0,90,180,270])
def test_saved_native_terminals_match_predicted_locality(tmp_path,back,turn):
    import cec_swig_guard
    cec_swig_guard.pin()
    import pcbnew
    board=pcbnew.CreateEmptyBoard();nets=[]
    for name in ('LOCAL_SUPPLY','GND'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);nets.append(net)
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('RENAMED_CAP');board.Add(fp)
    for index,x in enumerate((-.5,.5)):
        pad=pcbnew.PAD(fp);pad.SetNumber(str(index+1));pad.SetNet(nets[index])
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(.4,.6));pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetPosition(pcbnew.VECTOR2I_MM(x,0));fp.Add(pad)
    if back:fp.Flip(pcbnew.VECTOR2I(0,0),True)
    fp.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    fp.Move(pcbnew.VECTOR2I_MM(28,35))
    path=tmp_path/'input.kicad_pcb';pcbnew.SaveBoard(str(path),board,True)
    before=path.read_bytes();board=pcbnew.LoadBoard(str(path));fp=board.FindFootprintByReference('RENAMED_CAP')
    def xy(item):return [item.GetPosition().x/1e6,item.GetPosition().y/1e6]
    def transformed(point):
        x,y=rotate_board_point(point,(0,0),turn);return [x+28,y+35]
    row=dict(cell(),cap_ref='RENAMED_CAP',cap_position_mm=xy(fp),
        cap_supply_position_mm=xy(fp.FindPadByNumber('1')),
        cap_ground_position_mm=xy(fp.FindPadByNumber('2')),
        cap_orientation_deg=fp.GetOrientationDegrees(),
        owner_supply_position_mm=transformed([1,0]),
        owner_ground_positions_mm=[dict(position=transformed([2,0]))])
    poses,_=contact_poses(row,forbidden_centers=lambda angle:[])
    assert poses
    for proposal in poses:
        x,y,angle=proposal['position'];fp.SetPosition(pcbnew.VECTOR2I(round(x*1e6),round(y*1e6)))
        fp.SetOrientationDegrees(angle)
        supply=math.dist(xy(fp.FindPadByNumber('1')),row['owner_supply_position_mm'])
        ground=math.dist(xy(fp.FindPadByNumber('2')),row['owner_ground_positions_mm'][0]['position'])
        assert supply==pytest.approx(proposal['predicted_supply_mm'],abs=2e-6)
        assert ground==pytest.approx(proposal['predicted_ground_mm'],abs=2e-6)
        assert supply<=.73+2e-6 and ground<=.78+2e-6
    assert path.read_bytes()==before
