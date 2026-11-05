"""A mixed-width manufacturer input strap is not a blanket sense-net cut."""
import copy
import time

import pcbnew
import pytest
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_measurement_auxiliary_cut as auxiliary
import cec_measurement_leaf as leaf
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,quarter=0,back=False):
    board=_board([],edge=(0,0,40,40));board.SetCopperLayerCount(6)
    for name in ('/opaque/analog_alias','DIFFERENT_INPUT','RAIL','GND','OTHER'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('renamed_monitor');fp.SetValue('INA238AIDGSR')
    fp.SetFPID(pcbnew.LIB_ID('Package_SO','VSSOP-10_3x3mm_P0.5mm'));board.Add(fp)
    for pin in range(1,11):
        net={6:'RAIL',7:'GND',8:'/opaque/analog_alias',9:'/opaque/analog_alias',10:'DIFFERENT_INPUT'}.get(pin,'OTHER')
        p=pcbnew.PAD(fp);p.SetNumber(str(pin));p.SetNet(board.FindNet(net))
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.3,1.45))
        fp.Add(p);p.SetPosition(pcbnew.VECTOR2I_MM(10+(pin-8)*.5,10) if pin>=8
            else pcbnew.VECTOR2I_MM(20+pin,4))
    fixed=pcbnew.FOOTPRINT(board);fixed.SetReference('unrelated_external_boundary');board.Add(fixed)
    for pin,net,at in [('1','/opaque/analog_alias',(10.5,7.5)),('2','DIFFERENT_INPUT',(14,10))]:
        p=pcbnew.PAD(fixed);p.SetNumber(pin);p.SetNet(board.FindNet(net))
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        fixed.Add(p);p.SetPosition(pcbnew.VECTOR2I_MM(*at))
    strap=track(board,'/opaque/analog_alias',(10,10),(10.5,10),width=.25)
    departure=track(board,'/opaque/analog_alias',(10.5,10),(10.5,7.5),width=.2)
    hi=track(board,'DIFFERENT_INPUT',(11,10),(14,10),width=.25)
    for t in (strap,departure,hi):t.SetLocked(True)
    if back:
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Flip(pcbnew.VECTOR2I_MM(20,20),False)
    if quarter:
        angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
        for item in [*board.GetFootprints(),*board.GetTracks()]:item.Rotate(pcbnew.VECTOR2I_MM(20,20),angle)
    source=tmp_path/'source.kicad_pcb';board.SetFileName(str(source));pcbnew.SaveBoard(str(source),board)
    return board,source,fp,strap,departure


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_surface_and_rotated_mixed_width_strap_has_two_independent_scopes(tmp_path,quarter,back):
    board,source,fp,strap,departure=fixture(tmp_path,quarter,back);pad=fp.FindPadByNumber('9')
    before=row._source_binding(board);raw=source.read_bytes()
    with pytest.raises(ValueError):leaf.plan(board,force._uid(pad))
    external,internal=leaf.plan_with_auxiliary_strap(board,force._uid(pad))
    assert external['track_uuids']==[force._uid(departure)] and external['width_nm']==200000
    assert internal['track_uuids']==[force._uid(strap)] and internal['width_nm']==250000
    assert internal['boundary_uuids']==[force._uid(fp.FindPadByNumber('8'))]
    assert internal['separate_external_measurement_restoration_required']
    assert external['separately_owned_source_auxiliary_strap']==internal
    assert internal['layer']==(pcbnew.B_Cu if back else pcbnew.F_Cu)
    assert not internal['current_authority'] and not external['current_authority']
    assert not internal['kelvin_qualified'] and not internal['release_authority']
    assert before==row._source_binding(board) and raw==source.read_bytes()


@pytest.mark.parametrize('fault',['model','DNP','locked_owner','different_net','partial_package',
    'hole','group','wide','parallel','interior_tap','missing_external'])
def test_untyped_shared_or_incomplete_material_never_becomes_a_strap_cut(tmp_path,fault):
    board,source,fp,strap,departure=fixture(tmp_path)
    if fault=='model':fp.SetValue('not_a_manufacturer_model')
    elif fault=='DNP':fp.SetDNP(True)
    elif fault=='locked_owner':fp.SetLocked(True)
    elif fault=='different_net':fp.FindPadByNumber('8').SetNet(board.FindNet('OTHER'))
    elif fault=='partial_package':fp.FindPadByNumber('1').SetNumber('invented')
    elif fault=='hole':fp.FindPadByNumber('8').SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(board);g.AddItem(strap);board.Add(g)
    elif fault=='wide':strap.SetWidth(400000)
    elif fault=='parallel':board.Add(strap.Duplicate())
    elif fault=='interior_tap':track(board,'/opaque/analog_alias',(10.25,10),(10.25,12),width=.2)
    else:board.Remove(departure)
    before=row._source_binding(board)
    with pytest.raises(ValueError):leaf.plan_with_auxiliary_strap(board,force._uid(fp.FindPadByNumber('9')))
    assert before==row._source_binding(board)


@pytest.mark.parametrize('fault',['track','width','boundary','binding'])
def test_worker_auxiliary_context_is_rederived_not_a_cut_allowlist(tmp_path,fault):
    board,source,fp,strap,departure=fixture(tmp_path);pad=fp.FindPadByNumber('9')
    proof=auxiliary.plan(board,force._uid(pad));proof=copy.deepcopy(proof)
    if fault=='track':proof['track_uuids']=[force._uid(departure)]
    elif fault=='width':proof['width_nm']=200000
    elif fault=='boundary':proof['boundary_uuids']=[]
    else:proof['source_native_binding']='not_the_source'
    before=row._source_binding(board)
    with pytest.raises(ValueError,match='exact_source_owned_auxiliary'):
        leaf._plan(board,force._uid(pad),role='measurement',timeout_s=10.,max_tracks=16,
            max_length_mm=24.,source_auxiliary_strap=proof)
    assert before==row._source_binding(board)


def test_complete_cell_keeps_strap_and_external_measurement_requests_distinct(tmp_path,monkeypatch):
    board,source,fp,strap,departure=fixture(tmp_path)
    cap=pcbnew.FOOTPRINT(board);cap.SetReference('renamed_bypass');cap.SetValue('100nF')
    cap.SetPosition(pcbnew.VECTOR2I_MM(26,6));board.Add(cap)
    for pin,net,x in [('1','RAIL',26),('2','GND',27)]:
        p=pcbnew.PAD(cap);p.SetNumber(pin);p.SetNet(board.FindNet(net))
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        cap.Add(p);p.SetPosition(pcbnew.VECTOR2I_MM(x,6))
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**kw:dict(
        assigned={'source':dict(cap_ref=cap.GetReference(),requirement=dict(ref=fp.GetReference(),
            pin='6',rail='RAIL',return_rail='GND'))}))
    monkeypatch.setattr(escape.topology,'board_current_domains',lambda *a,**kw:{})
    monkeypatch.setattr(escape.fr,'coupled_pair_nets',lambda *a,**kw:set())
    pcbnew.SaveBoard(str(source),board)
    poses={f.GetReference():[f.GetPosition().x/1e6,f.GetPosition().y/1e6+.2,f.GetOrientationDegrees()]
        for f in (fp,cap)}
    parent=pcbnew.LoadBoard(str(source))
    before=row._source_binding(parent);proof=escape.prepare(parent,poses,board_hint='opaque')
    assert before==row._source_binding(parent)
    assert {force._uid(strap),force._uid(departure)}<=set(proof['retired_track_uuids'])
    private=pcbnew.LoadBoard(str(source));escape.apply_private(private,proof)
    demands=escape.obligations(parent,private,proof)
    root=force._uid(fp.FindPadByNumber('9'));keys=[k for k in demands if k.startswith('measurement:'+root)]
    assert len(keys)==2 and 'measurement:'+root in keys
    assert sum(':auxiliary:' in k for k in keys)==1
    assert {demands[k]['width_nm'] for k in keys}=={200000,250000}


@pytest.mark.parametrize('timeout',[0.,True,10.001,float('nan'),float('inf')])
def test_auxiliary_cut_work_budget_refuses_before_source_inspection(timeout):
    with pytest.raises(ValueError):auxiliary.plan(None,'opaque',timeout_s=timeout)
