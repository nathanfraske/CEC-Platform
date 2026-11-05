"""Source-owned process returns follow a cohort, not an arbitrary route group."""
import math
import pcbnew
import pytest
import cec_smd_macro_transport as macro
import cec_force_current as force
import cec_field_coupling as field
import cec_fab_profile as fab
import cec_fr as fr
from test_local_pofv_ownership import fixture


def pair(tmp_path, *, offset=(0,0), back=False, group=True):
    board,v=fixture(offset=offset,connected=offset!=(0,0))
    fp=next(iter(board.GetFootprints()));fp.SetReference('RENAMED')
    if back:
        fp.Flip(fp.GetPosition(),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        v.SetPosition(next(iter(fp.Pads())).GetPosition()+pcbnew.VECTOR2I_MM(*offset))
        for t in board.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetStart(next(iter(fp.Pads())).GetPosition());t.SetEnd(v.GetPosition());t.SetLayer(pcbnew.B_Cu)
    if group:fr.group_local_pofv_signal_vias(board,[v])
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,path)
    source=pcbnew.LoadBoard(str(path));candidate=pcbnew.LoadBoard(str(path))
    return source,candidate,force._uid(fp),force._uid(v)


def inventory(b):
    return {force._uid(t):(tuple(t.GetStart()),tuple(t.GetEnd()),
        t.GetWidth(t.TopLayer()) if t.GetClass()=='PCB_VIA' else t.GetWidth(),t.IsLocked()) for t in b.GetTracks()}


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('offset',[(0,0),(.625,0),(0,.625)])
@pytest.mark.parametrize('delta',[(1.25,-.75),(-.6,1.3)])
def test_same_native_return_geometry_follows_renamed_owner_with_zero_new_barrels(tmp_path,back,offset,delta):
    a,b,owner,via=pair(tmp_path,offset=offset,back=back)
    before=inventory(a);fp=next(f for f in b.GetFootprints() if force._uid(f)==owner)
    fp.Move(pcbnew.VECTOR2I_MM(*delta));r=macro.apply(a,b)
    new=next(t for t in b.GetTracks() if force._uid(t)==via)
    old=next(t for t in a.GetTracks() if force._uid(t)==via)
    assert tuple(new.GetPosition())==tuple(p+round(d*1e6) for p,d in zip(tuple(old.GetPosition()),delta))
    assert new.GetDrillValue()==old.GetDrillValue() and new.GetWidth(new.TopLayer())==old.GetWidth(old.TopLayer())
    assert before==inventory(a) and fab.local_pofv_via_decision(b,new)[0]
    assert len(r['source_process_barrel_motion'])==1 and r['new_barrels_created']==0
    assert not r['saved_candidate_authorized'] and not r['routing_admitted'] and not r['release_authority']
    if offset!=(0,0):
        old_leg=next(t for t in a.GetTracks() if t.GetClass()=='PCB_TRACK')
        new_leg=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
        assert math.isclose(old_leg.GetLength(),new_leg.GetLength(),abs_tol=1)


@pytest.mark.parametrize('fault',['width','drill','net','pad_shape','pad_size','rotation','population','overshift','factory_group','locked_group'])
def test_invalid_source_or_group_identity_refuses_before_conductor_writes(tmp_path,fault):
    a,b,owner,via=pair(tmp_path);fp=next(iter(b.GetFootprints()));v=next(iter(b.GetTracks()))
    fp.Move(pcbnew.VECTOR2I_MM(1,0))
    if fault=='width':v.SetWidth(v.GetWidth()+1)
    elif fault=='drill':v.SetDrill(v.GetDrillValue()+1)
    elif fault=='net':v.SetNetCode(0)
    elif fault=='pad_shape':next(iter(fp.Pads())).SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    elif fault=='pad_size':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(1,1))
    elif fault=='rotation':fp.SetOrientationDegrees(90)
    elif fault=='population':b.Add(pcbnew.PCB_VIA(b))
    elif fault=='overshift':fp.Move(pcbnew.VECTOR2I_MM(8,0))
    elif fault in ('factory_group','locked_group'):
        for board in (a,b):
            g=next(iter(board.Groups()))
            if fault=='factory_group':g.SetName('ARBITRARY_ROUTE_OWNER')
            else:g.SetLocked(True)
    before=inventory(b)
    with pytest.raises(ValueError):macro.apply(a,b)
    assert before==inventory(b)


@pytest.mark.parametrize('kw',[{'maximum_shift_mm':65},{'maximum_shift_mm':True},
    {'maximum_footprints':33},{'maximum_conductors':513},{'timeout_s':11},{'timeout_s':float('nan')},
    {'maximum_ordinary_vias':True},{'maximum_ordinary_vias':0},{'maximum_ordinary_vias':9},
    {'maximum_ordinary_vias':4.0},{'maximum_local_return_shift_mm':True},
    {'maximum_local_return_shift_mm':0},{'maximum_local_return_shift_mm':6.1},
    {'maximum_local_return_shift_mm':float('nan')}])
def test_explicit_scope_is_bounded(tmp_path,kw):
    a,b,owner,via=pair(tmp_path);next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(1,0))
    before=inventory(b)
    with pytest.raises(ValueError):macro.apply(a,b,**kw)
    assert before==inventory(b)


def test_destination_reproof_failure_restores_all_native_conductors(tmp_path,monkeypatch):
    a,b,owner,via=pair(tmp_path,offset=(.625,0));next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(1,0))
    original=fab.local_pofv_via_decision;before=inventory(b)
    monkeypatch.setattr(fab,'local_pofv_via_decision',lambda board,v,**k:
        (False,'injected_destination_refusal') if board is b else original(board,v,**k))
    with pytest.raises(ValueError,match='destination_POFV'):macro.apply(a,b)
    assert before==inventory(b)


def test_nearby_tagged_barrel_without_actual_source_copper_is_not_dragged(tmp_path):
    a,b,owner,via=pair(tmp_path,group=False)
    for board in (a,b):next(iter(board.GetTracks())).SetPosition(pcbnew.VECTOR2I_MM(22,30))
    next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(1,0))
    before=inventory(b)
    with pytest.raises(ValueError,match='changed_conductor_budget'):macro.apply(a,b)
    assert before==inventory(b)


def free_pair(tmp_path,monkeypatch):
    a,b,owner,via=pair(tmp_path)
    # Reload a real saved family so the explicit source path is independently
    # bound, not an in-memory caller label. Only semantic classification is
    # stubbed here; every land, stub, barrel and group proof remains native.
    net=pcbnew.NETINFO_ITEM(a,'/OTHER_SCALAR');a.Add(net)
    v=pcbnew.PCB_VIA(a);v.SetPosition(pcbnew.VECTOR2I_MM(25,40));v.SetWidth(600000);v.SetDrill(300000)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(net);a.Add(v)
    for lid,end in ((pcbnew.F_Cu,(28,40)),(pcbnew.B_Cu,(25,44))):
        t=pcbnew.PCB_TRACK(a);t.SetStart(v.GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(*end))
        t.SetLayer(lid);t.SetWidth(250000);t.SetNet(net);a.Add(t)
    path=tmp_path/'free-source.kicad_pcb';field._save_field_snapshot(a,path)
    a,b=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(1,0))
    import cec_ordinary_route_receiving as ordinary
    monkeypatch.setattr(ordinary,'eligible_nets',lambda *a,**k:{'/OTHER_SCALAR'})
    return a,b,path,force._uid(v)


def test_explicit_free_scalar_port_moves_only_with_all_real_incident_stubs(tmp_path,monkeypatch):
    a,b,path,uid=free_pair(tmp_path,monkeypatch)
    r=macro.apply(a,b,ordinary_via_poses=[dict(uuid=uid,position_nm=[26000000,39500000])],
        source_path=path,board_hint='SYNTHETIC')
    assert r['explicit_source_typed_ordinary_barrel_motion'][0]['uuid']==uid
    assert len(r['explicit_source_typed_ordinary_barrel_motion'][0]['actual_source_incident_track_uuids'])==2
    assert uid in {q['uuid'] for q in r['changes']}
    assert r['transient_rebuild_required_uuids'] and not r['saved_candidate_authorized']


@pytest.mark.parametrize('larger_explicit_budget',[False,True])
def test_complete_six_native_scalar_ports_require_an_explicit_still_bounded_budget(tmp_path,monkeypatch,larger_explicit_budget):
    a,b,path,uid=free_pair(tmp_path,monkeypatch)
    net=a.FindNet('/OTHER_SCALAR');requests=[dict(uuid=uid,position_nm=[26000000,39500000])]
    for index in range(1,6):
        v=pcbnew.PCB_VIA(a);v.SetPosition(pcbnew.VECTOR2I_MM(25+10*index,40))
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(net);a.Add(v)
        for lid,end in ((pcbnew.F_Cu,(28+10*index,40)),(pcbnew.B_Cu,(25+10*index,44))):
            t=pcbnew.PCB_TRACK(a);t.SetStart(v.GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(*end))
            t.SetLayer(lid);t.SetWidth(250000);t.SetNet(net);a.Add(t)
        requests.append(dict(uuid=force._uid(v),position_nm=[(26+10*index)*1000000,39500000]))
    field._save_field_snapshot(a,path)
    a,b=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(1,0));before=inventory(b)
    if not larger_explicit_budget:
        with pytest.raises(ValueError):
            macro.apply(a,b,ordinary_via_poses=requests,source_path=path,board_hint='SYNTHETIC')
        assert before==inventory(b)
    else:
        r=macro.apply(a,b,ordinary_via_poses=requests,source_path=path,board_hint='SYNTHETIC',maximum_ordinary_vias=6)
        assert len(r['explicit_source_typed_ordinary_barrel_motion'])==6 and r['new_barrels_created']==0
        assert all(len(p['actual_source_incident_track_uuids'])==2 for p in r['explicit_source_typed_ordinary_barrel_motion'])
        assert not r['saved_candidate_authorized'] and not r['routing_admitted']


@pytest.mark.parametrize('fault',['context','specialized','group','overshift','body_tee'])
def test_free_barrel_is_not_a_permission_to_drag_protected_or_unrepresented_contacts(tmp_path,monkeypatch,fault):
    a,b,path,uid=free_pair(tmp_path,monkeypatch);at=[26000000,39500000]
    if fault=='context':path=tmp_path/'another-source.kicad_pcb'
    elif fault=='specialized':
        import cec_ordinary_route_receiving as ordinary
        monkeypatch.setattr(ordinary,'eligible_nets',lambda *a,**k:set())
    elif fault=='overshift':at=[29000000,40000000]
    elif fault in ('group','body_tee'):
        v=next(t for t in a.GetTracks() if force._uid(t)==uid)
        if fault=='group':
            g=pcbnew.PCB_GROUP(a);g.SetName('PROTECTED');a.Add(g);g.AddItem(v)
        else:
            t=pcbnew.PCB_TRACK(a);t.SetStart(pcbnew.VECTOR2I_MM(23,40));t.SetEnd(pcbnew.VECTOR2I_MM(27,40))
            t.SetLayer(pcbnew.F_Cu);t.SetWidth(250000);t.SetNet(v.GetNet());a.Add(t)
        # Reload the exact common native identities, without assigning SWIG
        # read-only UUID properties or inventing a cut/replacement inventory.
        field._save_field_snapshot(a,path);b=pcbnew.LoadBoard(str(path))
        next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(1,0))
    before=inventory(b)
    with pytest.raises(ValueError):macro.apply(a,b,ordinary_via_poses=[dict(uuid=uid,position_nm=at)],
        source_path=path,board_hint='SYNTHETIC')
    assert before==inventory(b)


def test_same_size_roundrect_copper_change_is_not_a_source_translation(tmp_path):
    a,b,owner,via=pair(tmp_path)
    for board in (a,b):next(iter(next(iter(board.GetFootprints())).Pads())).SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
    p=next(iter(next(iter(b.GetFootprints())).Pads()));p.SetRoundRectRadiusRatio(.1)
    next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(1,0));before=inventory(b)
    with pytest.raises(ValueError,match='source_land_changed'):macro.apply(a,b)
    assert before==inventory(b)


@pytest.mark.parametrize('fault',['group_name','group_lock','owner_value','owner_reference','owner_lock'])
def test_unrelated_identity_or_group_context_changes_are_not_a_macro_pose(tmp_path,fault):
    a,b,owner,via=pair(tmp_path);fp=next(iter(b.GetFootprints()));fp.Move(pcbnew.VECTOR2I_MM(1,0))
    if fault=='group_name':next(iter(b.Groups())).SetName('COPIED_UNRELATED_OWNER')
    elif fault=='group_lock':next(iter(b.Groups())).SetLocked(True)
    elif fault=='owner_value':fp.SetValue('OTHER_COMPONENT')
    elif fault=='owner_reference':fp.SetReference('OTHER_IDENTITY')
    else:fp.SetLocked(True)
    before=inventory(b)
    with pytest.raises(ValueError):macro.apply(a,b)
    assert before==inventory(b)


def cardinal_pair(tmp_path,*,offset=(.625,0),back=False):
    board,v=fixture(offset=offset,connected=offset!=(0,0));fp=next(iter(board.GetFootprints()))
    pad=next(iter(fp.Pads()));at=pcbnew.VECTOR2I(pad.GetPosition())
    fp.SetPosition(at);pad.SetPosition(at)
    other=pcbnew.PAD(fp);other.SetPadName('second');other.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    other.SetShape(pcbnew.PAD_SHAPE_RECT);other.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
    other.SetLayerSet(pcbnew.PAD.SMDMask());other.SetNet(v.GetNet())
    other.SetPosition(at+pcbnew.VECTOR2I_MM(0,2));fp.Add(other)
    second=pcbnew.PCB_VIA(board);second.SetPosition(other.GetPosition());second.SetWidth(350000);second.SetDrill(250000)
    second.SetViaType(pcbnew.VIATYPE_THROUGH);second.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    second.SetNet(v.GetNet());board.Add(second)
    if back:
        fp.Flip(at,pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        v.SetPosition(pad.GetPosition()+pcbnew.VECTOR2I_MM(*offset))
        for t in board.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetStart(at);t.SetEnd(v.GetPosition());t.SetLayer(pcbnew.B_Cu)
    fr.group_local_pofv_signal_vias(board,[v,second])
    tail=pcbnew.PCB_TRACK(board);tail.SetStart(v.GetPosition());tail.SetEnd(v.GetPosition()+pcbnew.VECTOR2I_MM(2,0))
    tail.SetLayer(pcbnew.F_Cu if back else pcbnew.B_Cu);tail.SetWidth(200000);tail.SetNet(v.GetNet());board.Add(tail)
    path=tmp_path/'cardinal-source.kicad_pcb';field._save_field_snapshot(board,path)
    a,b=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    return a,b,force._uid(v),force._uid(tail)


@pytest.mark.parametrize('turn',[90,180,270])
@pytest.mark.parametrize('offset',[(0,0),(.625,0)])
@pytest.mark.parametrize('back',[False,True])
def test_cardinal_rotation_keeps_native_barrel_dogbone_and_marks_external_tail(tmp_path,turn,offset,back):
    a,b,via,tail=cardinal_pair(tmp_path,offset=offset,back=back)
    fp=next(iter(b.GetFootprints()));anchor=next(iter(fp.Pads())).GetPosition()
    fp.Rotate(anchor,pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T));before=inventory(a)
    r=macro.apply(a,b,allow_cardinal_rotations=True)
    assert before==inventory(a) and r['new_barrels_created']==0
    assert fab.local_pofv_via_decision(b,next(t for t in b.GetTracks() if force._uid(t)==via))[0]
    assert r['source_owner_cardinal_transforms'][force._uid(fp)]['cardinal_turn_deg']==turn
    if offset!=(0,0):
        assert tail in r['transient_rebuild_required_uuids']
        dogbone=next(t for t in a.GetTracks() if t.GetClass()=='PCB_TRACK' and force._uid(t)!=tail)
        after=next(t for t in b.GetTracks() if force._uid(t)==force._uid(dogbone))
        assert after.GetLength()==dogbone.GetLength()
        assert force._uid(dogbone) not in r['transient_rebuild_required_uuids']
    assert not r['routing_admitted'] and not r['current_qualified']


@pytest.mark.parametrize('fault',['untyped','not_cardinal','geometry','oversized_pad_trajectory'])
def test_cardinal_rotations_do_not_bypass_source_land_or_motion_guards(tmp_path,fault):
    a,b,via,tail=cardinal_pair(tmp_path);fp=next(iter(b.GetFootprints()))
    anchor=next(iter(fp.Pads())).GetPosition();turn=45 if fault=='not_cardinal' else 90
    if fault=='oversized_pad_trajectory':
        # A tiny origin shift is NOT a bound on a distant pad's trajectory.
        for board in (a,b):
            f=next(iter(board.GetFootprints()));p=next(iter(f.Pads()));old=pcbnew.VECTOR2I(p.GetPosition())
            f.SetPosition(pcbnew.VECTOR2I_MM(0,0));p.SetPosition(old)
        fp=next(iter(b.GetFootprints()));anchor=fp.GetPosition()
    fp.Rotate(anchor,pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    if fault=='geometry':next(iter(fp.Pads())).SetSize(pcbnew.VECTOR2I_MM(1,1))
    before=inventory(b)
    with pytest.raises(ValueError,match='pad_motion_work_limit_exceeded' if fault=='oversized_pad_trajectory' else None):
        macro.apply(a,b,allow_cardinal_rotations=1 if fault=='untyped' else True)
    assert before==inventory(b)


def rc_return_pair(tmp_path,monkeypatch):
    a,b,owner,via=pair(tmp_path)
    gnd=pcbnew.NETINFO_ITEM(a,'GND');a.Add(gnd)
    cap=pcbnew.FOOTPRINT(a);cap.SetReference('C_RENAMED');cap.SetValue('100nF')
    ground=pcbnew.PAD(cap);ground.SetPadName('2');ground.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    ground.SetShape(pcbnew.PAD_SHAPE_RECT);ground.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
    ground.SetLayerSet(pcbnew.PAD.SMDMask());ground.SetPosition(pcbnew.VECTOR2I_MM(30,40));ground.SetNet(gnd);cap.Add(ground)
    signal=pcbnew.PAD(cap);signal.SetPadName('1');signal.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    signal.SetShape(pcbnew.PAD_SHAPE_RECT);signal.SetSize(pcbnew.VECTOR2I_MM(.6,.6))
    signal.SetLayerSet(pcbnew.PAD.SMDMask());signal.SetPosition(pcbnew.VECTOR2I_MM(30,39))
    signal.SetNet(a.FindNet('/ARBITRARY'));cap.Add(signal);a.Add(cap)
    anchor=pcbnew.VECTOR2I(signal.GetPosition());old_ground=pcbnew.VECTOR2I(ground.GetPosition())
    cap.SetPosition(anchor);ground.SetPosition(old_ground);signal.SetPosition(anchor)
    v=pcbnew.PCB_VIA(a);v.SetPosition(pcbnew.VECTOR2I_MM(30.75,40));v.SetWidth(350000);v.SetDrill(250000)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(gnd);a.Add(v)
    t=pcbnew.PCB_TRACK(a);t.SetStart(ground.GetPosition());t.SetEnd(v.GetPosition())
    t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000);t.SetNet(gnd);a.Add(t);fr.group_local_pofv_signal_vias(a,[v])
    path=tmp_path/'rc-source.kicad_pcb';field._save_field_snapshot(a,path)
    a,b=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    next(f for f in b.GetFootprints() if force._uid(f)==owner).Move(pcbnew.VECTOR2I_MM(1,0))
    import cec_ordinary_route_receiving as ordinary
    monkeypatch.setattr(ordinary,'eligible_nets',lambda *a,**k:{'/ARBITRARY'})
    q=dict(uuid=force._uid(v),owner_pad_uuid=force._uid(ground),position_nm=[30550000,40000000])
    return a,b,path,q


def test_reproved_private_signal_return_can_shorten_without_moving_its_owner_or_shrinking_a_barrel(tmp_path,monkeypatch):
    a,b,path,q=rc_return_pair(tmp_path,monkeypatch);before=inventory(a)
    r=macro.apply(a,b,source_path=path,board_hint='SYNTHETIC',local_signal_return_via_poses=[q])
    proof=r['explicitly_reproved_private_signal_return_reseats'][0]
    assert proof['source_return_nm']==750000 and proof['proposed_return_nm']==550000
    assert proof['candidate_local_POFV_reproved'] and before==inventory(a)
    assert not r['current_qualified'] and r['new_barrels_created']==0


def test_joint_cardinal_owner_and_short_return_has_one_explicit_reproved_transform(tmp_path,monkeypatch):
    a,b,path,q=rc_return_pair(tmp_path,monkeypatch)
    cap=b.FindFootprintByReference('C_RENAMED');signal=cap.FindPadByNumber('1')
    cap.Rotate(signal.GetPosition(),pcbnew.EDA_ANGLE(180,pcbnew.DEGREES_T))
    q['position_nm']=[30550000,38000000]
    r=macro.apply(a,b,source_path=path,board_hint='SYNTHETIC',local_signal_return_via_poses=[q],allow_cardinal_rotations=True)
    assert r['explicitly_reproved_private_signal_return_reseats'][0]['candidate_local_POFV_reproved']
    assert q['uuid'] not in {r['uuid'] for r in r['source_process_barrel_motion']}
    assert r['new_barrels_created']==0 and not r['current_qualified']


@pytest.mark.parametrize('explicit_budget',[False,True])
def test_farther_owner_travel_still_needs_a_shorter_locally_qualified_same_geometry_return(tmp_path,monkeypatch,explicit_budget):
    a,b,path,q=rc_return_pair(tmp_path,monkeypatch)
    b.FindFootprintByReference('C_RENAMED').Move(pcbnew.VECTOR2I_MM(4,0))
    q['position_nm']=[34550000,40000000];before=inventory(b)
    opts=dict(source_path=path,board_hint='SYNTHETIC',local_signal_return_via_poses=[q])
    if not explicit_budget:
        with pytest.raises(ValueError,match='reseat_motion_bound'):macro.apply(a,b,**opts)
        assert before==inventory(b)
    else:
        r=macro.apply(a,b,maximum_local_return_shift_mm=6.,**opts)
        proof=r['explicitly_reproved_private_signal_return_reseats'][0]
        assert proof['source_return_nm']==750000 and proof['proposed_return_nm']==550000
        assert proof['candidate_local_POFV_reproved'] and r['new_barrels_created']==0
        assert not r['current_qualified'] and not r['release_authority']


@pytest.mark.parametrize('fault',['bulk','power','owner','group','not_shorter','partial_overlap','another_branch'])
def test_signal_return_reseat_does_not_seize_power_ground_or_shared_copper(tmp_path,monkeypatch,fault):
    a,b,path,q=rc_return_pair(tmp_path,monkeypatch)
    if fault=='bulk':
        for board in (a,b):board.FindFootprintByReference('C_RENAMED').SetValue('10uF')
    elif fault=='power':
        import cec_ordinary_route_receiving as ordinary
        monkeypatch.setattr(ordinary,'eligible_nets',lambda *a,**k:set())
    elif fault=='owner':q['owner_pad_uuid']='missing'
    elif fault=='group':
        for board in (a,b):next(g for g in board.Groups()).SetLocked(True)
    elif fault=='not_shorter':q['position_nm']=[30800000,40000000]
    elif fault=='partial_overlap':q['position_nm']=[30400000,40000000]
    else:
        for board in (a,b):
            v=next(t for t in board.GetTracks() if force._uid(t)==q['uuid'])
            t=pcbnew.PCB_TRACK(board);t.SetStart(v.GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(32,40))
            t.SetLayer(pcbnew.B_Cu);t.SetWidth(200000);t.SetNet(v.GetNet());board.Add(t)
    before=inventory(b)
    with pytest.raises(ValueError):macro.apply(a,b,source_path=path,board_hint='SYNTHETIC',local_signal_return_via_poses=[q])
    assert before==inventory(b)
