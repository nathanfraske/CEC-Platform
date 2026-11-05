"""Native contact events propose seats, never waive source cuts or routing."""
import copy
import math
import pcbnew
import pytest
import cec_cell_contact_frontier as contact
import cec_cell_escape_replan as escape
import cec_cell_row_rebuild as row
import cec_force_current as force
import cec_field_coupling as field
from test_complete_cell_connections import native_source


@pytest.mark.parametrize('shift', [(0,0), (10000000,-4000000), (-9000000,17000000)])
@pytest.mark.parametrize('gap', [0,200000,500000])
def test_axis_events_are_exact_translation_invariant_contact_separations(shift,gap):
    a=[0,0,1000000,2000000];b=[500000,500000,1500000,2500000]
    def move(box):return [v+shift[i%2] for i,v in enumerate(box)]
    events=contact.separation_events(a,b,clearance_nm=gap)
    assert events==contact.separation_events(move(a),move(b),clearance_nm=gap)
    assert len(events)==4
    for dx,dy in events:
        moved=[a[0]+dx,a[1]+dy,a[2]+dx,a[3]+dy]
        assert (moved[2]+gap<b[0] or b[2]+gap<moved[0]
                or moved[3]+gap<b[1] or b[3]+gap<moved[1])


@pytest.mark.parametrize('bad',[None,[],[0,0,1],True,[0,0,float('nan'),1],
    [0,0,float('inf'),1],[0,0,True,1],[1,0,0,1]])
def test_malformed_contact_geometry_is_not_an_obstacle_waiver(bad):
    with pytest.raises(ValueError):contact.separation_events(bad,[0,0,1,1])


@pytest.mark.parametrize('options',[{'timeout_s':True},{'timeout_s':11},{'timeout_s':0},
    {'max_shift_mm':33},{'max_shift_mm':float('nan')},{'radius_mm':7},{'radius_mm':True},
    {'max_nodes':129},{'max_nodes':True},{'max_results':9},{'max_results':False},
    {'allow_owned_locked_escapes':1},{'transport_source_barrels':1}])
def test_unknown_or_unbounded_frontier_is_refused_before_files_are_read(options):
    with pytest.raises(ValueError):
        contact.search('not-a-source',{'owner':[1,1,0]},board_hint='opaque',**options)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('barrel_can_clear',[True,False])
def test_independent_surface_and_barrel_events_both_advance_without_accepting_either_alone(
        tmp_path,monkeypatch,quarter,barrel_can_clear):
    # Synthetic classifier outputs isolate the search ordering, not a new
    # electrical/placement qualification. Real native source compilation,
    # fresh final source planning and immutable source bytes remain active.
    import cec_fr as fr
    path,parent,_,proposal=qualified_transport_source(tmp_path,monkeypatch,turn=quarter)
    add_courts(parent)
    vias=[t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA']
    assert fr.group_local_pofv_signal_vias(parent,vias)
    field._save_field_snapshot(parent,path);raw=path.read_bytes()
    monkeypatch.setattr(contact.force,'_family',lambda p,h:force._hash(p))
    ref=next(iter(proposal['selected_bypasses']));seed=proposal['poses'][ref]
    x,y=[round(v*1e6) for v in seed[:2]]
    def surface(board,fp):
        if fp.GetReference()==ref and fp.GetPosition().y<y+800000:
            raise ValueError('synthetic_independent_surface_contact')
    def barrels(board,transport,*,selected_ref=None):
        fp=board.FindFootprintByReference(ref)
        if selected_ref not in (None,ref):return {}
        if not barrel_can_clear or fp.GetPosition().x<x+800000:
            return {ref:dict(via_uuid=force._uid(vias[0]),obstacle_uuid='synthetic_inner_contact',
                events_nm=[(800000,0)])}
        return {}
    monkeypatch.setattr(contact.pi,'_pose_preflight',surface)
    monkeypatch.setattr(contact,'_barrel_refusals',barrels)
    monkeypatch.setattr(contact,'_events',lambda *a,**kw:[(0,800000)])
    result=contact.search(path,proposal['poses'],board_hint='opaque',max_shift_mm=6.,
        radius_mm=2.,max_nodes=3,max_results=1,transport_source_barrels=True)
    first=result['history'][0]
    assert first['separate_pose_and_barrel_fault_count']==2
    assert first['directed_contact_events_nm'][ref]==[[0,800000],[800000,0]]
    assert bool(result['offers']) is barrel_can_clear,result
    if result['offers']:
        pose=result['offers'][0]['poses'][ref]
        assert round(pose[0]*1e6)>=x+800000 and round(pose[1]*1e6)>=y+800000
        assert result['fresh_complete_pose_receiving'][0]['ok']
    assert path.read_bytes()==raw and result['saved_board_candidates']==0
    assert not result['placement_authority'] and not result['routing_admitted']


def qualified_transport_source(tmp_path,monkeypatch,*,turn=0):
    import cec_fr as fr
    path,parent,_,prior=native_source(tmp_path,monkeypatch,turn=turn)
    vias=[t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA']
    assert len(vias)==1
    for via in vias:
        via.SetWidth(500000);via.SetDrill(200000)
    import cec_fab_profile as fab
    assert all(fab.local_pofv_via_decision(parent,v)[0] for v in vias)
    assert fr.group_local_pofv_signal_vias(parent,vias)
    field._save_field_snapshot(parent,path)
    parent=pcbnew.LoadBoard(str(path))
    # Recompile after actual process/group geometry is part of Source.
    proposal=escape.prepare(parent,prior['poses'],board_hint='opaque')
    private=pcbnew.LoadBoard(str(path));escape.apply_private(private,proposal)
    return path,parent,private,proposal


def add_courts(board):
    for fp in board.GetFootprints():
        boxes=[p.GetBoundingBox() for p in fp.Pads()]
        shape=pcbnew.PCB_SHAPE(fp);shape.SetLayer(pcbnew.F_CrtYd)
        shape.SetShape(pcbnew.SHAPE_T_RECT);shape.SetWidth(50000)
        shape.SetStart(pcbnew.VECTOR2I(min(b.GetLeft() for b in boxes)-50000,
            min(b.GetTop() for b in boxes)-50000))
        shape.SetEnd(pcbnew.VECTOR2I(max(b.GetRight() for b in boxes)+50000,
            max(b.GetBottom() for b in boxes)+50000));fp.Add(shape)


def source_with_conflict(tmp_path,monkeypatch,quarter):
    path,parent,_,proposal=native_source(tmp_path,monkeypatch,turn=quarter)
    add_courts(parent)
    target=pcbnew.FOOTPRINT(parent.FindFootprintByReference(next(iter(proposal['selected_bypasses']))))
    pose=proposal['poses'][target.GetReference()]
    target.SetPosition(pcbnew.VECTOR2I_MM(*pose[:2]));target.SetOrientationDegrees(pose[2])
    pad=next(p for p in target.Pads() if p.GetNetname()=='RAIL');at=pad.GetPosition()
    obstacle=pcbnew.PCB_TRACK(parent);obstacle.SetLayer(pcbnew.F_Cu)
    # An immutable-width foreign conductor, not a new small source-owned
    # pad leg that this complete-cell planner could legitimately recompile.
    obstacle.SetNet(parent.FindNet('INPUT_N'));obstacle.SetWidth(600000)
    obstacle.SetStart(at);obstacle.SetEnd(at+pcbnew.VECTOR2I_MM(0,.05));obstacle.SetLocked(True)
    parent.Add(obstacle);field._save_field_snapshot(parent,path)
    # The synthetic fixture has no project sidecars. Bind its exact saved
    # bytes here; production uses the unmodified complete family binder.
    monkeypatch.setattr(contact.force,'_family',lambda p,h:force._hash(p))
    return path,proposal['poses'],force._uid(obstacle)


@pytest.mark.parametrize('quarter',range(4))
def test_real_native_foreign_contact_yields_fresh_poses_without_source_mutation(tmp_path,monkeypatch,quarter):
    path,poses,obstacle=source_with_conflict(tmp_path,monkeypatch,quarter)
    raw=path.read_bytes();frozen=copy.deepcopy(poses)
    pre=escape.prepare(pcbnew.LoadBoard(str(path)),poses,board_hint='opaque')
    assert obstacle not in pre['retired_track_uuids']
    literal=pcbnew.LoadBoard(str(path));cap=literal.FindFootprintByReference(next(iter(pre['selected_bypasses'])))
    cap.SetPosition(pcbnew.VECTOR2I_MM(*poses[cap.GetReference()][:2]))
    cap.SetOrientationDegrees(poses[cap.GetReference()][2])
    fixed=next(t for t in literal.GetTracks() if force._uid(t)==obstacle)
    assert any(p.GetNetCode()!=fixed.GetNetCode() and p.GetEffectiveShape(pcbnew.F_Cu).Collide(
        fixed.GetEffectiveShape(pcbnew.F_Cu),0) for p in cap.Pads())
    result=contact.search(path,poses,board_hint='opaque',max_shift_mm=6.,radius_mm=2.,
        max_nodes=64,max_results=1)
    assert result['offers'],{k:result[k] for k in ('history','fresh_complete_pose_receiving')}
    assert result['fresh_complete_pose_receiving'][0]['ok']
    # A different native conflict can be visited first; UUID enumeration
    # order is not authority to skip the literal foreign obstacle above.
    assert any(q['refusals'] for q in result['history'])
    for offer in result['offers']:
        parent=pcbnew.LoadBoard(str(path));escape.apply_private(parent,offer['source_proposal'])
        for ref in poses:contact.pi._pose_preflight(parent,parent.FindFootprintByReference(ref))
        assert obstacle in {force._uid(t) for t in parent.GetTracks()}
        assert offer['complete_routing_and_independent_receiving_still_required']
    assert poses==frozen and path.read_bytes()==raw
    assert result['source_geometry_and_family_unchanged'] and result['saved_board_candidates']==0
    assert not any(result[k] for k in ('no_path_proof','placement_authority','current_authority',
        'routing_admitted','fab_ready','release_authority'))


def test_cached_proposal_context_cannot_replace_fresh_source_plan_receiving(tmp_path,monkeypatch):
    path,parent,_,proposal=native_source(tmp_path,monkeypatch);add_courts(parent)
    field._save_field_snapshot(parent,path)
    monkeypatch.setattr(contact.force,'_family',lambda p,h:force._hash(p))
    def refuse(*a,**kw):raise ValueError('fresh_native_draft_deliberately_refused')
    monkeypatch.setattr(contact.escape,'apply_private',refuse)
    result=contact.search(path,proposal['poses'],board_hint='opaque',max_results=1,max_nodes=4)
    assert not result['offers'] and result['fresh_complete_pose_receiving']
    assert result['fresh_complete_pose_receiving'][0]['refusal']=='fresh_native_draft_deliberately_refused'
    assert result['saved_board_candidates']==0 and not result['no_path_proof']


def test_unknown_native_refusal_and_tiny_work_budget_never_become_fit(tmp_path,monkeypatch):
    path,parent,_,proposal=native_source(tmp_path,monkeypatch);raw=path.read_bytes()
    monkeypatch.setattr(contact.force,'_family',lambda p,h:force._hash(p))
    def unknown(*a):raise ValueError('unresolved_native_rule_permission')
    monkeypatch.setattr(contact.pi,'_pose_preflight',unknown)
    result=contact.search(path,proposal['poses'],board_hint='opaque',max_nodes=3,max_results=1)
    assert not result['offers'] and len(result['history'])==3
    assert not result['no_path_proof'] and path.read_bytes()==raw


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_source_owned_macro_endpoint_witness_and_cached_projection_are_native_frame_invariant(tmp_path,quarter,back):
    from test_smd_macro_transport import pair,inventory
    import cec_smd_macro_transport as macro
    a,b,owner,via=pair(tmp_path,offset=(.625,0),back=back)
    # The older one-pad fixture has its package origin at (0,0) and its land
    # tens of mm away. Give this rotation test a real local package origin,
    # preserving all absolute native lands before freezing the test source.
    before=next(f for f in a.GetFootprints() if force._uid(f)==owner)
    positions={force._uid(p):tuple(p.GetPosition()) for p in before.Pads()}
    before.SetPosition(next(iter(before.Pads())).GetPosition())
    for p in before.Pads():p.SetPosition(pcbnew.VECTOR2I(*positions[force._uid(p)]))
    path=a.GetFileName();field._save_field_snapshot(a,path)
    a,b=[pcbnew.LoadBoard(path) for _ in range(2)]
    old=inventory(a);before=next(f for f in a.GetFootprints() if force._uid(f)==owner)
    target=next(f for f in b.GetFootprints() if force._uid(f)==owner)
    target.Move(pcbnew.VECTOR2I_MM(1.25,-.75));target.SetOrientationDegrees(before.GetOrientationDegrees()+90*quarter)
    blueprint=macro.apply(a,b,allow_cardinal_rotations=True)
    assert blueprint['changes']
    for q in blueprint['changes']:
        assert len(q['source_endpoint_owner_footprint_uuids'])==len(q['source_nm'])
        assert not any(q['endpoint_has_explicit_nonfootprint_motion'])
        assert all(set(ids)<={owner} for ids in q['source_endpoint_owner_footprint_uuids'])
    poses={target.GetReference():[target.GetPosition().x/1e6+.7,
        target.GetPosition().y/1e6+.4,target.GetOrientationDegrees()]}
    contact._project_macro_context(a,b,poses,blueprint)
    c=pcbnew.LoadBoard(a.GetFileName());fp=next(iter(c.GetFootprints()))
    fp.SetPosition(pcbnew.VECTOR2I_MM(*poses[fp.GetReference()][:2]));fp.SetOrientationDegrees(poses[fp.GetReference()][2])
    macro.apply(a,c,allow_cardinal_rotations=True)
    assert inventory(b)==inventory(c) and inventory(a)==old


@pytest.mark.parametrize('face',[pcbnew.In2_Cu,pcbnew.B_Cu])
def test_through_barrel_terrain_checks_real_hidden_copper_even_when_surface_pad_is_separate(tmp_path,face):
    from test_smd_macro_transport import pair,inventory
    import cec_smd_macro_transport as macro
    a,b,owner,via=pair(tmp_path)
    future=next(iter(b.GetFootprints()));future.Move(pcbnew.VECTOR2I_MM(1.25,0))
    original=next(t for t in a.GetTracks() if force._uid(t)==via)
    at=original.GetPosition()+pcbnew.VECTOR2I_MM(1.25,0)
    net=pcbnew.NETINFO_ITEM(a,'unrelated_inner_priority');a.Add(net)
    t=pcbnew.PCB_TRACK(a);t.SetNet(net);t.SetLayer(face);t.SetWidth(200000)
    t.SetStart(at+pcbnew.VECTOR2I_MM(0,-1));t.SetEnd(at+pcbnew.VECTOR2I_MM(0,1));a.Add(t)
    field._save_field_snapshot(a,a.GetFileName());b=pcbnew.LoadBoard(a.GetFileName())
    future=next(iter(b.GetFootprints()));future.Move(pcbnew.VECTOR2I_MM(1.25,0))
    before=inventory(a);blueprint=macro.apply(a,b)
    faults=contact._barrel_refusals(b,blueprint)
    assert faults[future.GetReference()]['layer']==b.GetLayerName(face)
    assert faults[future.GetReference()]['kind']=='native_barrel_foreign_copper'
    assert not any(p.IsOnLayer(face) for p in future.Pads())
    assert inventory(a)==before


@pytest.mark.parametrize('quarter',range(4))
def test_complete_source_owned_cell_emits_only_fresh_barrel_checked_conditional_frames(tmp_path,monkeypatch,quarter):
    import cec_fr as fr
    path,parent,_,proposal=qualified_transport_source(tmp_path,monkeypatch,turn=quarter)
    add_courts(parent)
    vias=[t for t in parent.GetTracks() if t.GetClass()=='PCB_VIA']
    assert fr.group_local_pofv_signal_vias(parent,vias)
    field._save_field_snapshot(parent,path);raw=path.read_bytes()
    monkeypatch.setattr(contact.force,'_family',lambda p,h:force._hash(p))
    result=contact.search(path,proposal['poses'],board_hint='opaque',max_shift_mm=6.,radius_mm=2.,
        max_results=1,max_nodes=64,transport_source_barrels=True)
    assert result['offers'],{k:result[k] for k in ('history','fresh_complete_pose_receiving')}
    offer=result['offers'][0]
    assert offer['all_enabled_face_barrel_clearance_screen_passed']
    assert offer['no_copper_or_source_partition_reconstruction_claim']
    assert offer['conditional_unconstructed_native_track_uuids']
    assert offer['source_owned_macro_transport']['source_process_barrel_motion']
    assert not offer['source_owned_macro_transport']['saved_candidate_authorized']
    assert result['saved_board_candidates']==0 and not result['routing_admitted'] and path.read_bytes()==raw


@pytest.mark.parametrize('allowed',[False,True])
def test_cut_aware_assembly_events_carry_explicit_locked_escape_policy_to_the_native_source_plan(tmp_path,monkeypatch,allowed):
    import cec_escape_pose_frontier as frontier
    path,parent,_,proposal=native_source(tmp_path,monkeypatch);add_courts(parent)
    field._save_field_snapshot(parent,path);raw=path.read_bytes()
    monkeypatch.setattr(frontier.force,'_family',lambda p,h:force._hash(p))
    actual=escape.prepare;calls=[]
    def observe(*a,**kw):calls.append(kw.copy());return actual(*a,**kw)
    monkeypatch.setattr(frontier.escape,'prepare',observe)
    owner=next(iter(proposal['device_contracts']))
    result=frontier.cell_translation_events(path,[owner],board_hint='opaque',seed_delta_mm=(.5,.5),
        radius_mm=2.,max_sites=4,allow_owned_locked_escapes=allowed)
    assert result['source_owned_locked_escapes_requested'] is allowed
    assert calls and all(q.get('allow_owned_locked_escapes',False) is allowed for q in calls)
    assert result['fresh_source_plan_for_each_final_pose_required'] and not result['routing_admitted']
    assert path.read_bytes()==raw


@pytest.mark.parametrize('value',[1,None,[],{},'yes'])
def test_assembly_event_source_cut_policy_is_not_a_truthy_global_unlock(value):
    import cec_escape_pose_frontier as frontier
    with pytest.raises(ValueError):
        frontier.cell_translation_events('not-a-source',['owner'],board_hint='opaque',seed_delta_mm=(0,0),
            allow_owned_locked_escapes=value)


@pytest.mark.parametrize('quarter',range(4))
def test_complete_connections_receive_the_exact_real_ground_refill_and_restore_trial_copper(tmp_path,monkeypatch,quarter):
    import cec_additive_route_receiving as additive
    path,parent,private,proposal=native_source(tmp_path,monkeypatch,turn=quarter)
    raw=path.read_bytes();selected=additive._ground_refill(private);before=row._source_binding(private)
    result=escape.complete_connection_screen(path,private,proposal,board_hint='opaque',
        per_obligation_leases=True,allow_native_ground_refill=True)
    assert result['complete'],result
    assert result['native_ground_refill_requested']
    assert result['independently_rebuilt_ground_zone_uuids']==selected
    assert result['selection']['all_obligations_present'] and not result['routing_admitted']
    assert result['complete_selection_partition_trials'][-1]['lost_source_partitions']==0
    assert row._source_binding(private)==before and path.read_bytes()==raw


@pytest.mark.parametrize('fault',['not_refilled','foreign_track','ground_outline'])
def test_refill_permission_is_never_a_wildcard_for_stale_fills_or_changed_native_material(tmp_path,monkeypatch,fault):
    import cec_additive_route_receiving as additive
    path,parent,private,proposal=native_source(tmp_path,monkeypatch)
    if fault!='not_refilled':additive._ground_refill(private)
    if fault=='foreign_track':
        t=next(t for t in private.GetTracks() if t.GetClass()=='PCB_TRACK');t.SetWidth(t.GetWidth()+1)
    elif fault=='ground_outline':next(iter(private.Zones())).Move(pcbnew.VECTOR2I(1,0))
    before=row._source_binding(private)
    result=escape.complete_connection_screen(path,private,proposal,board_hint='opaque',allow_native_ground_refill=True)
    assert not result['complete'] and 'complete_connection_draft_differs_from_exact_source_cut_and_pose' in result['errors']
    assert row._source_binding(private)==before and not result['routing_admitted']


@pytest.mark.parametrize('flag',[1,None,[],{},'yes'])
def test_ground_refill_permission_requires_an_explicit_boolean_before_source_reads(flag):
    with pytest.raises(ValueError):
        escape.complete_connection_screen('no-source',None,{},board_hint='opaque',allow_native_ground_refill=flag)


@pytest.mark.parametrize('sign',[-1,1])
@pytest.mark.parametrize('axis',[0,1])
@pytest.mark.parametrize('magnitude',[.125,17.125,34.875])
def test_pose_coordinate_conversion_matches_declared_integer_rounding_not_mm_truncation(sign,axis,magnitude):
    point=[0.,0.];point[axis]=math.nextafter(sign*magnitude,0.)
    expected=tuple(round(v*1e6) for v in point)
    assert tuple(contact._position(point))==expected
    assert tuple(pcbnew.VECTOR2I_MM(*point))!=expected


def test_fractional_mm_source_pose_keeps_the_exact_projected_ground_ownership_witness(tmp_path,monkeypatch):
    path,parent,_,proposal=native_source(tmp_path,monkeypatch)
    # This predicate requires the real declared reference planes. The older
    # routing fixture intentionally has only one; add the second actual
    # native plane rather than mocking a successful ownership observation.
    first=next(iter(parent.Zones()));zone=pcbnew.ZONE(parent);zone.SetLayer(pcbnew.In4_Cu)
    zone.SetNet(parent.FindNet('GND'));zone.Outline().Append(first.Outline())
    zone.SetFilledPolysList(pcbnew.In4_Cu,first.GetFilledPolysList(pcbnew.In1_Cu))
    zone.SetIsFilled(True);parent.Add(zone);field._save_field_snapshot(parent,path)
    poses={fp.GetReference():[math.nextafter(fp.GetPosition().x/1e6+.001,0.),
        fp.GetPosition().y/1e6,fp.GetOrientationDegrees()] for fp in parent.GetFootprints()
        if fp.GetReference() in proposal['poses']}
    assert any(tuple(pcbnew.VECTOR2I_MM(*p[:2]))!=tuple(contact._position(p[:2])) for p in poses.values())
    fresh=escape.prepare(parent,poses,board_hint='opaque',allow_owned_locked_escapes=True)
    private,transport,omitted=contact._macro_context(parent,path,poses,fresh,6.,'opaque')
    for ref,pose in poses.items():
        assert tuple(private.FindFootprintByReference(ref).GetPosition())==tuple(round(v*1e6) for v in pose[:2])
    assert transport.get('independently_retained_projected_ground_contacts')
    assert not transport['saved_candidate_authorized'] and not transport['routing_admitted']
