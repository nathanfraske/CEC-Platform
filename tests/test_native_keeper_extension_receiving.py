"""Retain literal old copper while consolidating new same-net round joins."""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_rectilinear_copper as owner
import cec_native_keeper_extension_receiving as receiving
import cec_native_barrel_landing as barrel_landing
from test_lastmile import _board
from test_field_proposals import track
from test_native_landing_union import keeper_setup
from test_regional_fill import regional_plan


def fixture(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu,renamed=False):
    b,t,z,_=keeper_setup(angle=angle,mirror=mirror,layer=layer)
    properties=b.GetProperties();properties['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(properties)
    if renamed:
        name=str(t.GetNetname());net=pcbnew.NETINFO_ITEM(b,'/OTHER-CATALOG/UNRELATED-RAIL');b.Add(net)
        for item in [*b.GetTracks(),*b.Zones(),*(p for f in b.GetFootprints() for p in f.Pads())]:
            if str(item.GetNetname())==name:item.SetNet(net)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    child=force._copy_family(source,tmp_path/'candidate');c=pcbnew.LoadBoard(str(child))
    st=next(i for i in c.GetTracks() if force._uid(i)==force._uid(t))
    sz=next(i for i in c.Zones() if force._uid(i)==force._uid(z))
    plan=regional_plan(c,st,sz);emitted=owner.materialize(c,plan)
    before=pcbnew.LoadBoard(str(source));owner.fill(c,plan,emitted['zone_uuid'],regional_source=before)
    additive._ground_refill(c);field._save_field_snapshot(c,child)
    return source,child,[dict(plan=plan,materialized=emitted)],force._uid(t),force._uid(z)


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
@pytest.mark.parametrize('renamed',[False,True])
def test_real_saved_native_extension_exactly_replays_source_and_keeps_old_fill(tmp_path,angle,mirror,layer,renamed):
    source,child,rows,_,uid=fixture(tmp_path,angle,mirror,layer,renamed)
    before=[p.read_bytes() for p in (source,child)]
    proof=receiving.receive_literal_phase(source,child,rows,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['actual_modified_zone_uuids']==[uid]
    assert proof['every_source_conductor_and_original_keeper_fill_retained']
    assert proof['exact_original_source_keeper_and_ground_refill_replayed']
    assert not proof['new_capacity_credited'] and not proof['release_authority']
    assert before==[p.read_bytes() for p in (source,child)]


@pytest.mark.parametrize('fault',['source_track','source_keeper','candidate_track','candidate_keeper',
    'source_metadata','extra_material','lost_old_fill','unfilled','changed_pose','sidecar',
    'duplicate','unknown_record_field','forged_rehashed_profile','forged_rehashed_source',
    'retire_tracks','recompile','native_fill_waiver','false_capacity','wrong_owner','no_records'])
def test_no_worker_manifest_or_cached_success_can_replace_immutable_source(tmp_path,fault):
    source,child,rows,tid,zid=fixture(tmp_path)
    if fault in ('source_track','source_keeper','source_metadata'):
        b=pcbnew.LoadBoard(str(source))
        if fault=='source_track':next(t for t in b.GetTracks() if force._uid(t)==tid).SetWidth(1000001)
        elif fault=='source_keeper':next(z for z in b.Zones() if force._uid(z)==zid).SetLocalClearance(199999)
        else:b.SetCopperLayerCount(4)
        field._save_field_snapshot(b,source)
    elif fault in ('candidate_track','candidate_keeper','extra_material','lost_old_fill','unfilled','changed_pose'):
        b=pcbnew.LoadBoard(str(child));z=next(z for z in b.Zones() if force._uid(z)==zid)
        if fault=='candidate_track':next(t for t in b.GetTracks() if force._uid(t)==tid).SetWidth(1000001)
        elif fault=='candidate_keeper':z.SetLocalClearance(199999)
        elif fault=='extra_material':
            t=pcbnew.PCB_TRACK(b);t.SetNet(next(iter(b.GetTracks())).GetNet())
            t.SetStart(pcbnew.VECTOR2I_MM(10,10));t.SetEnd(pcbnew.VECTOR2I_MM(11,10));t.SetWidth(200000);b.Add(t)
        elif fault=='lost_old_fill':
            # Saved-file case: replace the real old material with a literal
            # small rectangle. Sub-nanometre hole/fracture preservation is
            # independently tested by the native owner's in-memory matrix.
            fill=owner._poly([(30000000,30000000),(31000000,30000000),
                (31000000,31000000),(30000000,31000000)])
            z.SetFilledPolysList(pcbnew.F_Cu,fill)
        elif fault=='unfilled':z.UnFill()
        else:next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.1,0))
        field._save_field_snapshot(b,child)
    elif fault=='sidecar':source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='duplicate':rows*=2
    elif fault=='unknown_record_field':rows[0]['accepted']=True
    elif fault=='false_capacity':rows[0]['materialized']['new_capacity_credited']=True
    elif fault=='wrong_owner':rows[0]['materialized']['zone_uuid']='not-the-source-owner'
    elif fault=='no_records':rows=[]
    else:
        plan=rows[0]['plan']
        if fault=='forged_rehashed_profile':plan['polygon_nm'][0][0]+=1
        elif fault=='forged_rehashed_source':plan['replacement_source_zone']['configuration']['clearance_nm']-=1
        elif fault=='retire_tracks':plan['retire_source_tracks']=True
        elif fault=='recompile':plan['rebuild_keeper_from_tracks']=True
        else:plan['fill_policy']='native'
        plan.pop('plan_sha256');plan['plan_sha256']=owner._digest(plan)
    before=[p.read_bytes() for p in (source,child)]
    proof=receiving.receive_literal_phase(source,child,rows,board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof
    assert not proof['new_capacity_credited'] and not proof['release_authority']
    assert before==[p.read_bytes() for p in (source,child)]


@pytest.mark.parametrize('hint',['synthetic','another-explicit-source-context'])
def test_missing_typed_kelvin_declaration_is_not_a_vacuous_positive(tmp_path,hint):
    source,child,rows,_,_=fixture(tmp_path)
    proof=receiving.receive(source,child,rows,board_hint=hint)
    assert not proof['ok'] and not proof['complete']
    assert 'ValueError:keeper_extension_absolute_cuts_and_unaffected_evidence_refused' in proof['errors']


@pytest.mark.parametrize('hint',['synthetic','another-explicit-source-context'])
def test_positive_stage_orchestration_never_elevates_current_or_release(tmp_path,monkeypatch,hint):
    # Only the independent electrical-verdict boundary is simulated here;
    # no invented amperage or fake native Kelvin packet is introduced. The
    # literal geometry matrix above is real, the observer has its own native
    # tests, and actual saved-board electrical replays remain mandatory.
    source,child,rows,_,_=fixture(tmp_path);calls=[]
    def verdict(first,last,**kwargs):
        calls.append(kwargs)
        return dict(comparison_complete=True,same_evidence=True)
    monkeypatch.setattr(receiving.sense,'compare_contour_preservation',verdict)
    proof=receiving.receive(source,child,rows,board_hint=hint)
    assert proof['ok'] and proof['complete'],proof['errors']
    assert calls==[dict(modified_nets=[rows[0]['plan']['net']])]
    assert proof['physical_kelvin_preservation']['comparison_complete']
    assert proof['physical_kelvin_preservation']['same_evidence']
    assert not proof['current_qualified'] and not proof['coupled_thermal_qualified'] and not proof['release_authority']


@pytest.mark.parametrize('seconds',[0,-1,True,float('inf'),float('nan'),10.01])
def test_invalid_literal_work_budget_is_not_clean(tmp_path,seconds):
    source,child,rows,_,_=fixture(tmp_path)
    proof=receiving.receive_literal_phase(source,child,rows,board_hint='synthetic',timeout_s=seconds)
    assert not proof['ok'] and not proof['complete']


@pytest.mark.parametrize('fault',['current','field','unknown_changed_cut','failed_changed_cut','strict_unaffected'])
def test_full_current_field_and_absolute_cut_refusals_remain_independent(tmp_path,monkeypatch,fault):
    source,child,rows,_,_=fixture(tmp_path)
    if fault=='current':
        monkeypatch.setattr(receiving.current,'receive',lambda *a,**kw:dict(ok=False,complete=True,errors=['current_debt_changed']))
    elif fault=='field':
        monkeypatch.setattr(receiving.field,'field_coupling_summary',lambda path:dict(path=path))
        monkeypatch.setattr(receiving.field,'blocker_keys',lambda report:set() if Path(report['path'])==source else {'new-real-field-key'})
    elif fault in ('unknown_changed_cut','failed_changed_cut'):
        monkeypatch.setattr(receiving.sense,'replay',lambda *a,**kw:dict(clipped_isolation=dict(details=[
            dict(net=rows[0]['plan']['net'],ok=None if fault=='unknown_changed_cut' else False)])))
    else:
        monkeypatch.setattr(receiving.sense,'compare_contour_preservation',lambda *a,**kw:dict(comparison_complete=True,same_evidence=False))
    proof=receiving.receive(source,child,rows,board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof
    expected=dict(current='keeper_extension_full_current_debt_refused',
        field='new_native_keeper_extension_field_blocker',
        unknown_changed_cut='changed_keeper_requires_positive_absolute_source_and_candidate_cuts',
        failed_changed_cut='changed_keeper_requires_positive_absolute_source_and_candidate_cuts',
        strict_unaffected='keeper_extension_absolute_cuts_and_unaffected_evidence_refused')[fault]
    assert any(expected in error for error in proof['errors']),proof['errors']
    assert not proof['new_capacity_credited'] and not proof['release_authority']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_read_only_auto_plan_selects_actual_native_contact_not_refdes_or_orientation(angle,mirror,layer):
    from cec_local_copper_cell import copper_inventory
    b,t,z,_=keeper_setup(angle=angle,mirror=mirror,layer=layer)
    before=copper_inventory(b)
    plan=receiving.plan(b,[force._uid(t)],required_width_nm=t.GetWidth())
    assert plan['replacement_source_zone']['configuration']['uuid']==force._uid(z)
    assert plan['fill_policy']=='source_preserving_regions'
    assert plan['retire_source_tracks'] is False and not plan.get('rebuild_keeper_from_tracks',False)
    assert copper_inventory(b)==before


@pytest.mark.parametrize('fault',['no_keeper','unfilled','distant','foreign','two_owners','below_floor',
    'locked','ground','stale','mixed_layer'])
def test_auto_plan_refuses_unowned_ambiguous_unfilled_or_weakened_keeper(fault):
    from cec_local_copper_cell import copper_inventory
    b,t,z,_=keeper_setup();ids=[force._uid(t)]
    if fault=='no_keeper':z.SetZoneName('ordinary-unqualified-pour')
    elif fault=='unfilled':z.UnFill()
    elif fault=='distant':z.Move(pcbnew.VECTOR2I_MM(20,0))
    elif fault=='foreign':z.SetNet(b.FindNet('/RENAMED_FOREIGN'))
    elif fault=='two_owners':
        second=pcbnew.ZONE(b);second.SetNet(z.GetNet());second.SetLayer(z.GetLayer())
        second.SetZoneName(owner.ZONE_NAME);second.SetAssignedPriority(0);second.Outline().NewOutline()
        ring=z.Outline().Outline(0)
        for i in range(ring.PointCount()):second.Outline().Append(ring.CPoint(i).x,ring.CPoint(i).y)
        second.SetFilledPolysList(z.GetLayer(),z.GetFilledPolysList(z.GetLayer()).CloneDropTriangulation())
        second.SetIsFilled(True);b.Add(second)
    elif fault=='below_floor':
        b.GetDesignSettings().m_MinClearance=200000;z.SetLocalClearance(199999)
    elif fault=='locked':t.SetLocked(True);z.SetLocked(True)
    elif fault=='ground':
        n=pcbnew.NETINFO_ITEM(b,'GND');b.Add(n);t.SetNet(n);z.SetNet(n)
    elif fault=='stale':ids=['not-a-native-track']
    else:
        other=pcbnew.PCB_TRACK(b);other.SetNet(t.GetNet());other.SetWidth(t.GetWidth());other.SetLayer(pcbnew.B_Cu)
        other.SetStart(t.GetStart());other.SetEnd(t.GetEnd());b.Add(other);ids.append(force._uid(other))
    before=copper_inventory(b)
    with pytest.raises((ValueError,owner.Refused)):
        receiving.plan(b,ids,required_width_nm=t.GetWidth())
    assert copper_inventory(b)==before


def test_auto_plan_locked_scope_is_explicit_and_keeps_every_old_process_field():
    b,t,z,_=keeper_setup();t.SetLocked(True);z.SetLocked(True)
    plan=receiving.plan(b,[force._uid(t)],required_width_nm=t.GetWidth(),
        allow_locked_track_uuids=[force._uid(t)],allow_locked_zone_uuids=[force._uid(z)])
    assert plan['source_tracks'][0]['locked'] and plan['replacement_source_zone']['configuration']['locked']
    assert not plan['new_capacity_credited'] and not plan['release_authority']


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_explicit_extension_retains_independent_old_keeper_and_track_locks(tmp_path,angle,mirror,layer):
    b,t,z,_=keeper_setup(angle=angle,mirror=mirror,layer=layer);t.SetLocked(True);z.SetLocked(False)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    original=source.read_bytes();uid=force._uid(z);tid=force._uid(t)
    with pytest.raises(owner.Refused,match='contract_must_be_retained'):
        receiving.plan(b,[tid],required_width_nm=t.GetWidth(),allow_locked_track_uuids=[tid])
    plan=receiving.plan(b,[tid],required_width_nm=t.GetWidth(),allow_locked_track_uuids=[tid],
        retain_existing_keeper_lock=True)
    assert plan['locked'] is False and plan['source_tracks'][0]['locked'] is True
    assert plan['replacement_source_zone']['configuration']['locked'] is False
    child=force._copy_family(source,tmp_path/'candidate');c=pcbnew.LoadBoard(str(child))
    emitted=owner.materialize(c,plan,allow_locked_track_uuids=[tid])
    parent=pcbnew.LoadBoard(str(source));owner.fill(c,plan,uid,regional_source=parent)
    additive._ground_refill(c);field._save_field_snapshot(c,child)
    proof=receiving.receive_literal_phase(source,child,[dict(plan=plan,materialized=emitted)],board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert original==source.read_bytes()
    saved=pcbnew.LoadBoard(str(child))
    assert next(t for t in saved.GetTracks() if force._uid(t)==tid).IsLocked()
    assert not next(z for z in saved.Zones() if force._uid(z)==uid).IsLocked()


@pytest.mark.parametrize('fault',['track_permission','forged_keeper_lock','changed_actual_lock',
    'retire','native_fill','recompile','bad_type'])
def test_independent_lock_policy_never_unlocks_or_authorizes_other_native_changes(fault):
    b,t,z,_=keeper_setup();t.SetLocked(True);z.SetLocked(False);tid=force._uid(t)
    kwargs=dict(required_width_nm=t.GetWidth(),clearance_nm=z.GetLocalClearance(),
        min_thickness_nm=z.GetMinThickness(),allow_locked_track_uuids=[tid],retire_source_tracks=False,
        replace_native_zone_uuid=force._uid(z),enclosing_native_zone_uuids=[force._uid(z)],
        fill_policy='source_preserving_regions',retain_existing_keeper_lock=True,contour_style='chamfer45',
        contour_grid_nm=1000,fill_envelope_margin_nm=4,landing_enclosure_mode='canonical_outline')
    if fault in ('retire','native_fill','recompile','bad_type','track_permission'):
        if fault=='retire':kwargs['retire_source_tracks']=True
        elif fault=='native_fill':kwargs['fill_policy']='native'
        elif fault=='recompile':kwargs['rebuild_keeper_from_tracks']=True
        elif fault=='track_permission':kwargs['allow_locked_track_uuids']=[]
        else:kwargs['retain_existing_keeper_lock']=1
        with pytest.raises(owner.Refused):owner.plan(b,[tid],**kwargs)
    else:
        plan=owner.plan(b,[tid],**kwargs)
        if fault=='forged_keeper_lock':
            plan['locked']=True;plan['replacement_source_zone']['configuration']['locked']=True
            plan.pop('plan_sha256');plan['plan_sha256']=owner._digest(plan)
        else:z.SetLocked(True)
        with pytest.raises(owner.Refused):owner.materialize(b,plan,allow_locked_track_uuids=[tid])
    assert t.IsLocked() and (z.IsLocked() is (fault=='changed_actual_lock'))


def barrel_fixture(tmp_path,monkeypatch,quarter=0,mirror=False,layer=pcbnew.F_Cu,locked=False):
    # Only the source electrical-authority boundary is simulated. All native
    # barrel/outline/fill geometry is real. No amperage is invented here;
    # current/cut/native release checks remain separate real-board replays.
    monkeypatch.setattr(barrel_landing.authority,'_model',lambda *a,**kw:
        ('synthetic_source_authority_boundary',{},dict(source='synthetic_positive_boundary_not_hardware_rating',
            routing_layers=('F.Cu','B.Cu'),authority_refs=('synthetic-source-a','synthetic-source-b'),
            nested=dict(retained=(1,2)))))
    def point(x,y):
        if mirror:x=30-x
        for _ in range(quarter):x,y=30-y,x
        return (round(x*1e6),round(y*1e6))
    net='/UNRELATED_SOURCE_RAIL'
    board=_board([(9,11,net),(11,11,net),(4,4,'GND')],edge=(0,0,40,40));board.SetCopperLayerCount(6)
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            x,y=pad.GetPosition();pad.SetPosition(pcbnew.VECTOR2I(*point(x/1e6,y/1e6)))
            layers=pcbnew.LSET();layers.AddLayer(layer);pad.SetLayerSet(layers)
    via=pcbnew.PCB_VIA(board);via.SetNet(board.FindNet(net));via.SetPosition(pcbnew.VECTOR2I(*point(10,10)))
    via.SetWidth(1400000);via.SetDrill(400000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetLocked(True);board.Add(via)
    track(board,net,[v/1e6 for v in point(10,10)],[v/1e6 for v in point(10,10.8)],width=1.,layer=layer)
    zone=pcbnew.ZONE(board);zone.SetNet(board.FindNet(net));zone.SetLayer(layer);zone.SetZoneName(owner.ZONE_NAME)
    zone.SetLocalClearance(200000);zone.SetMinThickness(100000);zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    zone.SetAssignedPriority(0);zone.SetLocked(locked);zone.Outline().NewOutline()
    for x,y in ((8,10),(12,10),(12,11.5),(8,11.5)):zone.Outline().Append(*point(x,y))
    board.Add(zone);selected=pcbnew.ZONES();selected.append(zone);board.BuildConnectivity()
    barrel_landing.cec_zone_fill.compile_selected(board,selected,timeout_s=10.)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(board,source)
    return board,source,force._uid(via),force._uid(zone)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_actual_barrel_landing_is_centered_real_fill_and_exact_source_replay(tmp_path,monkeypatch,quarter,mirror,layer):
    board,source,uid,zid=barrel_fixture(tmp_path,monkeypatch,quarter,mirror,layer)
    before=source.read_bytes();proposal=barrel_landing.plan(board,source,uid,layer,board_hint='synthetic')
    at=proposal['source_barrel']['at_nm'];local={(x-at[0],y-at[1]) for x,y in proposal['centered_cover_nm']}
    assert len(local)==8 and local=={(-x,y) for x,y in local}=={(y,x) for x,y in local}
    made=barrel_landing.construct(board,source,proposal)
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(board,child)
    import json
    persisted=json.loads(json.dumps([dict(plan=proposal,materialized=made)],allow_nan=False))
    proof=barrel_landing.receive_literal_phase(source,child,persisted,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['centered_native_outer_cover_received'] and not proof['new_capacity_credited']
    old_nodes=additive._nodes(source)[1];new_nodes=additive._nodes(child)[1]
    assert old_nodes[uid]==new_nodes[uid] and old_nodes.keys()==new_nodes.keys()
    assert source.read_bytes()==before and not proof['plated_hole_or_current_qualification']


@pytest.mark.parametrize('fault',['unfilled','ordinary_zone','two_owners','thermal','smoothing',
    'no_lock_permission','ground','blind','undersize','foreign','no_source_authority'])
def test_native_barrel_landing_does_not_infer_an_owner_or_waive_source_process(tmp_path,monkeypatch,fault):
    board,source,uid,zid=barrel_fixture(tmp_path,monkeypatch,locked=fault=='no_lock_permission')
    via=next(t for t in board.GetTracks() if force._uid(t)==uid);zone=next(z for z in board.Zones() if force._uid(z)==zid)
    if fault=='unfilled':zone.UnFill()
    elif fault=='ordinary_zone':zone.SetZoneName('NOT_A_PIPELINE_NATIVE_OWNER')
    elif fault=='two_owners':
        other=zone.Duplicate(False);other.m_Uuid.Clone(pcbnew.KIID());board.Add(other)
    elif fault=='thermal':zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    elif fault=='smoothing':zone.SetCornerSmoothingType(pcbnew.ZONE_SETTINGS.SMOOTHING_CHAMFER)
    elif fault=='ground':via.SetNet(board.FindNet('GND'));zone.SetNet(board.FindNet('GND'))
    elif fault=='blind':via.SetViaType(pcbnew.VIATYPE_BLIND)
    elif fault=='undersize':via.SetWidth(400000)
    elif fault=='foreign':
        foreign=pcbnew.NETINFO_ITEM(board,'/FOREIGN');board.Add(foreign)
        t=pcbnew.PCB_TRACK(board);t.SetNet(foreign);t.SetLayer(pcbnew.F_Cu);t.SetWidth(200000)
        t.SetStart(pcbnew.VECTOR2I_MM(9.7,9.2));t.SetEnd(pcbnew.VECTOR2I_MM(10.3,9.2));board.Add(t)
    elif fault=='no_source_authority':
        def refuse(*a,**kw):raise ValueError('unknown_source_current')
        monkeypatch.setattr(barrel_landing.authority,'_model',refuse)
    before=field._field_snapshot_inventory(board)
    with pytest.raises((ValueError,owner.Refused)):barrel_landing.plan(board,source,uid,pcbnew.F_Cu,board_hint='synthetic')
    assert field._field_snapshot_inventory(board)==before


@pytest.mark.parametrize('fault',['via_drill','via_motion','track','pad','clearance','fill','extra',
                                  'forged_support','forged_source','materialized'])
def test_saved_barrel_landing_requires_exact_immutable_copper_and_source_plan(tmp_path,monkeypatch,fault):
    board,source,uid,zid=barrel_fixture(tmp_path,monkeypatch)
    proposal=barrel_landing.plan(board,source,uid,pcbnew.F_Cu,board_hint='synthetic')
    made=barrel_landing.construct(board,source,proposal)
    via=next(t for t in board.GetTracks() if force._uid(t)==uid);zone=next(z for z in board.Zones() if force._uid(z)==zid)
    if fault=='via_drill':via.SetDrill(450000)
    elif fault=='via_motion':via.Move(pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='track':next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(900000)
    elif fault=='pad':next(iter(next(iter(board.GetFootprints())).Pads())).Move(pcbnew.VECTOR2I_MM(.01,0))
    elif fault=='clearance':zone.SetLocalClearance(199999)
    elif fault=='fill':zone.UnFill()
    elif fault=='extra':track(board,'GND',(15,15),(16,15),width=.2)
    elif fault=='forged_support':proposal['centered_cover_nm'][0][0]+=1
    elif fault=='forged_source':proposal['source_barrel']['drill_nm']+=1
    elif fault=='materialized':made['source_preserving_native_fill']['new_capacity_credited']=True
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(board,child)
    proof=barrel_landing.receive_literal_phase(source,child,[dict(plan=proposal,materialized=made)],board_hint='synthetic')
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof


def test_locked_barrel_keeper_permission_retains_locks_and_exact_diameter(tmp_path,monkeypatch):
    board,source,uid,zid=barrel_fixture(tmp_path,monkeypatch,locked=True)
    proposal=barrel_landing.plan(board,source,uid,pcbnew.F_Cu,board_hint='synthetic',allow_locked_source=True)
    barrel_landing.construct(board,source,proposal)
    assert next(t for t in board.GetTracks() if force._uid(t)==uid).IsLocked()
    assert next(z for z in board.Zones() if force._uid(z)==zid).IsLocked()
    assert proposal['source_barrel']['diameter_nm']==1400000 and proposal['source_barrel']['drill_nm']==400000


@pytest.mark.parametrize('reverse',[False,True])
def test_source_barrel_batch_replays_two_landings_on_one_evolving_keeper(tmp_path,monkeypatch,reverse):
    board,source,uid,zid=barrel_fixture(tmp_path,monkeypatch)
    second=pcbnew.PCB_VIA(board);second.SetNet(board.FindNet('/UNRELATED_SOURCE_RAIL'))
    second.SetPosition(pcbnew.VECTOR2I_MM(11.5,10));second.SetWidth(1400000);second.SetDrill(400000)
    second.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);second.SetLocked(True);board.Add(second)
    keeper=next(z for z in board.Zones() if force._uid(z)==zid)
    selected=pcbnew.ZONES();selected.append(keeper);board.BuildConnectivity()
    barrel_landing.cec_zone_fill.compile_selected(board,selected,timeout_s=10.)
    field._save_field_snapshot(board,source);original=source.read_bytes()
    ids=[uid,force._uid(second)]
    if reverse:ids.reverse()
    child=force._copy_family(source,tmp_path/'candidate');records=[]
    for selected_uid in ids:
        evolving=pcbnew.LoadBoard(str(child))
        proposal=barrel_landing.plan(evolving,source,selected_uid,pcbnew.F_Cu,board_hint='synthetic')
        made=barrel_landing.construct(evolving,source,proposal)
        field._save_field_snapshot(evolving,child);records.append(dict(plan=proposal,materialized=made))
    import json
    records=json.loads(json.dumps(records,allow_nan=False))
    proof=barrel_landing.receive_literal_phase(source,child,records,board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['actual_modified_zone_uuids']==[zid] and len(proof['received_barrel_faces'])==2
    assert proof['actual_modified_nets']==['/UNRELATED_SOURCE_RAIL']
    assert source.read_bytes()==original and not proof['plated_hole_or_current_qualification']
    for forged in (records[::-1],records+[records[0]]):
        refused=barrel_landing.receive_literal_phase(source,child,forged,board_hint='synthetic')
        assert not refused['ok'] and not refused['complete']


@pytest.mark.parametrize('hint',[None,'one',True,[['one']],['one','one'],['missing'],['one']*5])
def test_barrel_priority_hint_is_only_an_actual_request_order_not_authority(hint):
    requests=[dict(via_uuid='one',layer_id=pcbnew.F_Cu),dict(via_uuid='two',layer_id=pcbnew.B_Cu)]
    with pytest.raises(ValueError):barrel_landing._priority_requests(requests,hint)
    assert requests==[dict(via_uuid='one',layer_id=pcbnew.F_Cu),dict(via_uuid='two',layer_id=pcbnew.B_Cu)]


def test_barrel_priority_hint_keeps_every_real_request_and_its_exact_payload():
    requests=[dict(via_uuid='one',layer_id=pcbnew.F_Cu,proof='not-authority'),
              dict(via_uuid='two',layer_id=pcbnew.B_Cu,proof='not-authority'),
              dict(via_uuid='one',layer_id=pcbnew.B_Cu,proof='not-authority')]
    ranked=barrel_landing._priority_requests(requests,['two'])
    assert ranked==[requests[1],requests[0],requests[2]]
    assert all(a is b for a,b in zip(ranked,[requests[1],requests[0],requests[2]]))


def test_barrel_landing_never_extends_power_on_profile_reference_plane(tmp_path,monkeypatch):
    board,source,uid,zid=barrel_fixture(tmp_path,monkeypatch)
    import cec_fab_profile as fab
    layer=next(k for k,v in fab.COPPER_LAYER_IDS.items()
               if v in fab.COPPER_LAYERS and fab.get_profile('jlcpcb_6l_pofv_signal')['roles'][fab.COPPER_LAYERS.index(v)]=='GND')
    zone=next(z for z in board.Zones() if force._uid(z)==zid);fill=zone.GetFilledPolysList(pcbnew.F_Cu).CloneDropTriangulation()
    zone.SetLayer(layer);zone.SetFilledPolysList(layer,fill);zone.SetIsFilled(True)
    with pytest.raises(ValueError,match='reference_plane'):
        barrel_landing.plan(board,source,uid,layer,board_hint='synthetic')
    report=barrel_landing.discover(board,source,board_hint='synthetic',max_requests=64)
    assert not any(row['layer_id']==layer for row in report['requests'])


@pytest.mark.parametrize('fault',['authority_ref','routing_layer','nested_source_contract'])
def test_persisted_barrel_authority_fields_are_exactly_rederived_not_type_waived(tmp_path,monkeypatch,fault):
    import json
    board,source,uid,zid=barrel_fixture(tmp_path,monkeypatch)
    proposal=barrel_landing.plan(board,source,uid,pcbnew.F_Cu,board_hint='synthetic')
    made=barrel_landing.construct(board,source,proposal)
    child=force._copy_family(source,tmp_path/'candidate');field._save_field_snapshot(board,child)
    records=json.loads(json.dumps([dict(plan=proposal,materialized=made)],allow_nan=False))
    contract=records[0]['plan']['source_current_contract']
    if fault=='authority_ref':contract['authority_refs'][0]='unrelated-source'
    elif fault=='routing_layer':contract['routing_layers'][0]='In2.Cu'
    else:contract['nested']['retained'][0]=3
    proof=barrel_landing.receive_literal_phase(source,child,records,board_hint='synthetic')
    assert not proof['ok'] and not proof['complete']
    assert any('source_plan_changed' in e for e in proof['errors'])
