"""A narrow real land pocket is usable without a new floor, pad move or stub."""
import json
import math
import os
from pathlib import Path
import time
import pcbnew
import pytest
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_contained_via_events as events
import cec_native_drc_runner as native
from test_lastmile import _board


def fixture(tmp_path,quarter=0,back=False):
    board=_board([],edge=(0,0,20,20));board.SetCopperLayerCount(6);settings=board.GetDesignSettings()
    settings.m_TrackMinWidth=200000;settings.m_MinClearance=200000
    settings.m_ViasMinSize=500000;settings.m_MinThroughDrill=300000;settings.m_ViasMinAnnularWidth=100000
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_high_current';board.SetProperties(props)
    for name in ('GND','/different-sheet/control'):
        board.Add(pcbnew.NETINFO_ITEM(board,name))
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('C937');fp.SetValue('renamed-bypass')
    board.Add(fp);pad=pcbnew.PAD(fp);pad.SetNumber('2');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);pad.SetRoundRectRadiusRatio(.15)
    pad.SetSize(pcbnew.VECTOR2I(560000,620000));pad.SetLayerSet(pcbnew.PAD.SMDMask())
    pad.SetNet(board.FindNet('GND'));fp.Add(pad);fp.SetPosition(pcbnew.VECTOR2I_MM(10,10))
    trace=pcbnew.PCB_TRACK(board);trace.SetNet(board.FindNet('/different-sheet/control'))
    trace.SetStart(pcbnew.VECTOR2I(9000000,10501100));trace.SetEnd(pcbnew.VECTOR2I(11000000,10501100))
    trace.SetLayer(pcbnew.In3_Cu);trace.SetWidth(220000);board.Add(trace)
    if back:fp.Flip(fp.GetPosition(),False)
    angle=pcbnew.EDA_ANGLE(90*quarter,pcbnew.DEGREES_T)
    fp.Rotate(pcbnew.VECTOR2I_MM(10,10),angle);trace.Rotate(pcbnew.VECTOR2I_MM(10,10),angle)
    path=Path(tmp_path)/'source.kicad_pcb';field._save_field_snapshot(board,path)
    path.with_suffix('.kicad_pro').write_text(json.dumps({
        'board':{'design_settings':{'rules':{'min_track_width':.2,'min_clearance':.2,
            'min_via_diameter':.5,'min_through_hole_diameter':.3,'min_via_annular_width':.1}}},
        'net_settings':{'classes':[
            {'name':'Default','track_width':.2,'clearance':.2,'via_diameter':.6,'via_drill':.3},
            {'name':'GND','track_width':.5,'clearance':.2,'via_diameter':.9,'via_drill':.5}],
            'netclass_assignments':{'GND':'GND'}}}))
    board=pcbnew.LoadBoard(str(path));pad=next(p for f in board.GetFootprints()for p in f.Pads())
    return path,board,pad


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_real_return_producer_uses_native_narrow_pocket_and_adds_no_redundant_trace(tmp_path,quarter,back):
    source,board,pad=fixture(tmp_path,quarter,back);before=source.read_bytes()
    original=field._field_snapshot_inventory(board);rules=source.with_suffix('.kicad_pro').read_bytes()
    assert not fr._via_spot_clear(board,pad.GetPosition(),500000,200000,{pad.GetNetCode()},
        drill_nm=300000,net_code=pad.GetNetCode())
    report={};result,error=cells._add_ground_return(board,pad,board_path=str(source),reach_mm=.1,lock=True,diagnostics=report)
    assert result is not None and error is None,report
    assert result['status']=='via-in-pad'and result['contained_off_center']and result['no_added_stub']
    assert result['ordinary_board_floors_unchanged']and not result['centre_only_local_rule_borrowed']
    assert .058<result['distance_mm']<.061
    assert len(result['items'])==1 and result['items'][0].GetClass()=='PCB_VIA'
    via=result['items'][0];assert(via.GetWidth(pcbnew.F_Cu),via.GetDrillValue())==(500000,300000)
    assert events.contains(pad,via.GetPosition(),500000)
    assert fab.local_pofv_via_decision(board,via)[0]
    after=field._field_snapshot_inventory(board)
    assert {k:v for k,v in after.items()if k in original}==original
    assert len(after)==len(original)+1
    assert source.read_bytes()==before and source.with_suffix('.kicad_pro').read_bytes()==rules


@pytest.mark.parametrize('fault',['larger_native_floor','missing_process','blocked_everywhere'])
def test_contained_return_does_not_acquire_a_smaller_floor_or_foreign_copper_waiver(tmp_path,fault):
    source,board,pad=fixture(tmp_path)
    if fault=='larger_native_floor':board.GetDesignSettings().m_ViasMinSize=700000
    elif fault=='missing_process':
        props=board.GetProperties();props['CEC_FAB_PROFILE']='';board.SetProperties(props)
    else:
        trace=next(iter(board.GetTracks()));trace.SetStart(pcbnew.VECTOR2I_MM(9,10))
        trace.SetEnd(pcbnew.VECTOR2I_MM(11,10));trace.SetWidth(1000000)
    original=field._field_snapshot_inventory(board)
    result,error=cells._add_ground_return(board,pad,board_path=str(source),reach_mm=.1,lock=True)
    assert result is None and error and field._field_snapshot_inventory(board)==original


@pytest.mark.parametrize('shape',[pcbnew.PAD_SHAPE_CUSTOM,pcbnew.PAD_SHAPE_TRAPEZOID])
def test_unknown_pad_geometry_never_gets_rectangular_contains_credit(tmp_path,shape):
    source,board,pad=fixture(tmp_path);pad.SetShape(shape)
    assert not events.contains(pad,pad.GetPosition(),500000)
    assert not events.candidates(board,pad,500000,200000,deadline=time.monotonic()+1)['events']


def test_saved_native_rules_and_clearance_receive_the_actual_offcentre_barrel(tmp_path):
    source,board,pad=fixture(tmp_path)
    result,error=cells._add_ground_return(board,pad,board_path=str(source),reach_mm=.1,lock=True)
    assert result is not None and error is None
    candidate=force._copy_family(source,Path(tmp_path)/'child');field._save_field_snapshot(board,candidate)
    assert candidate.with_suffix('.kicad_pro').read_bytes()==source.with_suffix('.kicad_pro').read_bytes()
    build=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not build:pytest.skip('requires explicit native reporting build')
    output=Path(tmp_path)/'native.json';proof=native.run(candidate,output,reporting_build=Path(build),timeout_s=10.)
    assert proof['ok']and proof['complete']and not proof['native_inventory']['potentially_truncated']
    findings=json.loads(output.read_text())['violations'];uid=result['via_uuid']
    assert not [f for f in findings if f['severity']=='error'and any(i.get('uuid')==uid for i in f['items'])]


@pytest.mark.parametrize('quarter,layer',[(0,pcbnew.F_Cu),(1,pcbnew.B_Cu)])
def test_actual_typed_local_mesh_plan_construct_save_and_receive_uses_one_contained_axis(tmp_path,quarter,layer):
    import cec_ground_local_mesh_entry as mesh
    import cec_additive_pair_repair as producer
    import cec_additive_route_receiving as additive
    from test_ground_local_mesh_entry import fixture as source_fixture
    from test_field_proposals import track
    board,source,owner,cap,root=source_fixture(tmp_path,quarter=quarter,layer=layer)
    pad=cap.FindPadByNumber('2');pad.SetSize(pcbnew.VECTOR2I(560000,620000))
    # This Source island also contains its owner's Ground. Keep a stable
    # identity order so the regression exercises the capacitor's INTERIOR
    # site, not the separately legal alternative entry on that other land.
    pad.m_Uuid.Clone(pcbnew.KIID('00000000-0000-4000-8000-000000000001'))
    pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);pad.SetRoundRectRadiusRatio(.15)
    angle=math.radians(pad.GetOrientationDegrees());c,s=math.cos(angle),math.sin(angle)
    x,y=pad.GetPosition().x/1e6,pad.GetPosition().y/1e6
    planes={board.GetLayerID(name)for name in fr.plane_layers(board)}
    routing_face=next(l for l in board.GetEnabledLayers().CuStack()
        if l not in planes and l not in(pcbnew.F_Cu,pcbnew.B_Cu))
    trace=track(board,'/different/control',(x-s*.5011-c,y+c*.5011-s),
        (x-s*.5011+c,y+c*.5011+s),layer=routing_face,width=.22)
    additive._ground_refill(board);field._save_field_snapshot(board,source)
    before=force._family(source,'synthetic');old={force._uid(t)for t in board.GetTracks()}
    proposal=mesh.plan(board,board_hint='synthetic',pad_uuid=force._uid(pad),timeout_s=10.)
    assert proposal['complete']and proposal['strict_native_contained_via_without_redundant_lead'],proposal
    assert len(proposal['ops'])==1 and proposal['ops'][0][0]=='via'
    made=mesh.construct_private(board,proposal,board_hint='synthetic');assert len(made)==1
    child=force._copy_family(source,Path(tmp_path)/'received-child')
    producer.save_native_additions(child,board,{},old,board_hint='synthetic')
    result=mesh.receive(source,child,board_hint='synthetic',timeout_s=10.)
    assert result['ok']and result['complete'],result
    assert before==force._family(source,'synthetic')
    assert not result.get('current_qualified')and not result.get('release_authority')


def test_expired_local_event_slice_does_not_poison_the_remaining_outer_search(monkeypatch):
    import cec_search_budget as budget
    from test_contained_pofv_inset import fixture as inset_fixture
    board,pad=inset_fixture();clock=[100.]
    monkeypatch.setattr(fr.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *a,**k:False)
    def timeout(*args,**kwargs):
        assert kwargs['deadline']==101.
        clock[0]=101.1
        return dict(complete=True,events=[dict(at_nm=[9900000,10000000])])
    monkeypatch.setattr(events,'candidates',timeout)
    with budget.scoped(1000)as outer:
        rows=fr._local_pofv_inset_seats(board,pad.GetPosition(),pcbnew.F_Cu,200000,pad.GetNetCode(),200000,
            profile=fab.get_profile(fab.board_profile_name(board)),leg_ok=lambda *_:True,
            deadline_monotonic=110.)
        assert rows==[]and outer.stop_reason is None
        assert not budget.exhausted(105.)and outer.stop_reason is None
        clock[0]=105.1
        assert budget.exhausted(105.)and outer.stop_reason=='wall_deadline'


@pytest.mark.parametrize('canonical',[False,True])
def test_event_fallback_preserves_canonical_lead_from_actual_offcentre_origin(monkeypatch,canonical):
    from test_contained_pofv_inset import fixture as inset_fixture
    board,pad=inset_fixture();origin=pad.GetPosition()+pcbnew.VECTOR2I(30000,20000);phase=[False]
    monkeypatch.setattr(fr,'_via_spot_clear',lambda *a,**k:phase[0])
    monkeypatch.setattr(fr,'_tap_foreign_clear',lambda *a,**k:True)
    def offer(*args,**kwargs):
        phase[0]=True
        return dict(complete=True,events=[dict(at_nm=[9900000,10020000 if canonical else 10000000])])
    monkeypatch.setattr(events,'candidates',offer)
    found=fr._local_pofv_inset_seats(board,origin,pcbnew.F_Cu,200000,pad.GetNetCode(),200000,
        profile=fab.get_profile(fab.board_profile_name(board)),leg_ok=lambda *_:True,
        deadline_monotonic=time.monotonic()+2.)
    assert bool(found)==canonical
    for xy,ops in found:
        dx,dy=xy[0]-origin.x,xy[1]-origin.y
        assert dx==0 or dy==0 or abs(dx)==abs(dy)
