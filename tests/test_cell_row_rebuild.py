"""Whole-cell recompilation owns exact local edges, never entire power nets."""
import copy
from pathlib import Path

import pcbnew
import pytest
import cec_cell_row_rebuild as rebuild
import cec_local_copper_cell as local


def fixture(*,locked=True,protected=False):
    b=pcbnew.BOARD();n=pcbnew.NETINFO_ITEM(b,'LOCAL_ROLE');b.Add(n)
    for ref,x in [('OWNER',10),('BYPASS',12),('FIXED_OTHER',17)]:
        f=pcbnew.FOOTPRINT(b);f.SetReference(ref);f.SetValue('unique_'+ref)
        p=pcbnew.PAD(f);p.SetNumber('1');p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetNet(n);f.Add(p)
        f.SetPosition(pcbnew.VECTOR2I_MM(x,10));b.Add(f)
    edges=[]
    for x0,x1 in [(10,12),(12,14),(14,17)]:
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(x0,10))
        t.SetEnd(pcbnew.VECTOR2I_MM(x1,10));t.SetWidth(200000);t.SetNet(n)
        t.SetLocked(locked);b.Add(t);edges.append(t)
    poses={'OWNER':(10.,13.,0.),'BYPASS':(12.,13.,0.)}
    cells={'arbitrary_channel':['OWNER','BYPASS']}
    return b,poses,cells,edges


def test_explicit_recompile_rigidly_carries_internal_and_cuts_only_owned_pad_leg():
    b,poses,cells,edges=fixture();before=local.copper_inventory(b)
    ids=[t.m_Uuid.AsString() for t in edges]
    p=rebuild.plan(b,poses,cells,allow_owned_locked=True)
    assert p['transformed_track_uuids']==[ids[0]]
    assert p['retired_track_uuids']==[ids[1]]
    report=rebuild.apply(b,p);after=local.copper_inventory(b)
    assert after[ids[2]]==before[ids[2]] and ids[1] not in after
    assert after[ids[0]][3:7]==[10000000,13000000,12000000,13000000]
    assert report['all_vias_and_force_current_copper_exact']
    assert not report['routing_admitted'] and not report['release_authority']
    assert p['all_source_terminal_and_surviving_junction_partitions_require_restoration']


def test_locked_edges_are_not_implicitly_recompile_permission():
    b,poses,cells,_=fixture();before=local.copper_inventory(b)
    p=rebuild.plan(b,poses,cells)
    assert not p['retired_track_uuids'] and not p['transformed_track_uuids']
    assert before==local.copper_inventory(b)


@pytest.mark.parametrize('mode',['wide','protected','grouped'])
def test_wide_power_pairs_and_group_owned_material_never_become_local_removals(mode):
    b,poses,cells,edges=fixture();protected=()
    if mode=='wide':
        for t in edges:t.SetWidth(1000000)
    elif mode=='protected':protected=('LOCAL_ROLE',)
    else:
        g=pcbnew.PCB_GROUP(b);g.SetName('source_owned_power_or_pair')
        for t in edges:g.AddItem(t)
        b.Add(g)
    p=rebuild.plan(b,poses,cells,protected_nets=protected,allow_owned_locked=True)
    assert not p['retired_track_uuids'] and not p['transformed_track_uuids']


@pytest.mark.parametrize('fault',['forged_scope','changed_copper','changed_pose','changed_value','split_cell','overlap'])
def test_stale_or_incomplete_packets_refuse_before_any_mutation(fault):
    b,poses,cells,edges=fixture();p=rebuild.plan(b,poses,cells,allow_owned_locked=True)
    if fault=='forged_scope':p['retired_track_uuids'].append(edges[-1].m_Uuid.AsString())
    elif fault=='changed_copper':edges[-1].SetWidth(300000)
    elif fault=='changed_pose':b.FindFootprintByReference('OWNER').Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='changed_value':b.FindFootprintByReference('FIXED_OTHER').SetValue('changed')
    elif fault=='split_cell':p['target_poses']['BYPASS'][1]=14.
    else:p['cells']['second']=copy.deepcopy(p['cells']['arbitrary_channel'])
    before=rebuild._source_binding(b)
    with pytest.raises(ValueError):rebuild.apply(b,p)
    assert rebuild._source_binding(b)==before


def test_unowned_midsegment_tee_is_retained_as_restoration_boundary():
    b,poses,cells,edges=fixture()
    tee=pcbnew.PCB_TRACK(b);tee.SetStart(pcbnew.VECTOR2I_MM(13,10))
    tee.SetEnd(pcbnew.VECTOR2I_MM(13,11));tee.SetWidth(200000)
    tee.SetNetCode(edges[1].GetNetCode());b.Add(tee)
    p=rebuild.plan(b,poses,cells,allow_owned_locked=True)
    assert edges[1].m_Uuid.AsString() not in p['retired_track_uuids']


def test_supply_consumer_via_is_not_automatically_a_force_field_by_name():
    b,poses,cells,edges=fixture()
    edges[-1].SetWidth(1000000)
    vias=[]
    for x,y in [(16,10),(10,10)]:
        v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(x,y))
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetNetCode(edges[-1].GetNetCode());b.Add(v);vias.append(v)
    protected=rebuild.retained_power_items(b,{'LOCAL_ROLE':{}})
    assert vias[0].m_Uuid.AsString() in protected and vias[1].m_Uuid.AsString() not in protected
    assert edges[-1].m_Uuid.AsString() in protected


def test_source_internal_route_is_not_carried_across_foreign_destination_copper():
    b,poses,cells,edges=fixture();n=pcbnew.NETINFO_ITEM(b,'FOREIGN_RETAINED');b.Add(n)
    t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(11,12))
    t.SetEnd(pcbnew.VECTOR2I_MM(11,14));t.SetWidth(200000);t.SetNet(n);t.SetLocked(True);b.Add(t)
    p=rebuild.plan(b,poses,cells,allow_owned_locked=True)
    uid=edges[0].m_Uuid.AsString()
    assert uid not in p['transformed_track_uuids'] and uid in p['retired_track_uuids']
    assert p['target_internal_chain_blockers'][uid][0]['uuid']==t.m_Uuid.AsString()
    before=local.copper_inventory(b)
    rebuild.apply(b,p)
    after=local.copper_inventory(b)
    assert after[t.m_Uuid.AsString()]==before[t.m_Uuid.AsString()]


def test_noop_packet_never_rips_up_existing_routes():
    b,poses,cells,_=fixture();poses={ref:[b.FindFootprintByReference(ref).GetPosition().x/1e6,
        b.FindFootprintByReference(ref).GetPosition().y/1e6,0.] for ref in poses}
    before=local.copper_inventory(b)
    p=rebuild.plan(b,poses,cells,allow_owned_locked=True)
    assert not p['retired_track_uuids'] and not p['transformed_track_uuids']
    rebuild.apply(b,p)
    assert before==local.copper_inventory(b)


def test_existing_pad_contact_survives_a_small_source_owned_land_translation():
    b,poses,cells,edges=fixture();poses={ref:(b.FindFootprintByReference(ref).GetPosition().x/1e6,
        10.05,0.) for ref in poses}
    # Without a rigid route transfer request, the existing native contact is
    # already live. Keep every branch instead of making a gratuitous open.
    p=rebuild.plan(b,poses,{},allow_owned_locked=True)
    assert not p['retired_track_uuids'] and not p['transformed_track_uuids']
    assert any(r['disposition']=='live_native_pad_contact_retained_at_target'
               for r in p['source_incident_boundaries'])


def test_explicit_external_span_policy_replays_without_broadening_internal_cells():
    b,poses,cells,edges=fixture()
    edges[1].SetEnd(pcbnew.VECTOR2I_MM(23,10))
    edges[2].SetStart(pcbnew.VECTOR2I_MM(23,10))
    edges[2].SetEnd(pcbnew.VECTOR2I_MM(25,10))
    b.FindFootprintByReference('FIXED_OTHER').SetPosition(pcbnew.VECTOR2I_MM(25,10))
    narrow=rebuild.plan(b,poses,cells,allow_owned_locked=True,maximum_pad_leg_length_mm=8.)
    assert edges[1].m_Uuid.AsString() not in narrow['retired_track_uuids']
    p=rebuild.plan(b,poses,cells,allow_owned_locked=True,maximum_pad_leg_length_mm=12.)
    assert edges[1].m_Uuid.AsString() in p['retired_track_uuids']
    assert p['maximum_local_length_mm']==8. and p['maximum_pad_leg_length_mm']==12.
    rebuild.apply(b,p)


def test_external_leg_bound_is_derived_from_native_outline_not_internal_chain_budget():
    b,poses,cells,edges=fixture()
    for a,z in [((0,0),(30,0)),((30,0),(30,20)),((30,20),(0,20)),((0,20),(0,0))]:
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetLayer(pcbnew.Edge_Cuts);edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(edge)
    edges[1].SetEnd(pcbnew.VECTOR2I_MM(23,10))
    edges[2].SetStart(pcbnew.VECTOR2I_MM(23,10))
    edges[2].SetEnd(pcbnew.VECTOR2I_MM(25,10))
    b.FindFootprintByReference('FIXED_OTHER').SetPosition(pcbnew.VECTOR2I_MM(25,10))
    p=rebuild.plan(b,poses,cells,allow_owned_locked=True)
    assert 36<=p['maximum_pad_leg_length_mm']<37
    assert edges[1].m_Uuid.AsString() in p['retired_track_uuids']


@pytest.mark.parametrize('shared',[False,True])
def test_pad_contained_kernel_is_owned_only_by_a_single_source_land(shared):
    b,poses,cells,edges=fixture()
    from cec_native_items import discard_items
    netcode=edges[0].GetNetCode()
    discard_items(b,edges[:2])
    edge=pcbnew.PCB_TRACK(b);edge.SetStart(pcbnew.VECTOR2I_MM(11.9,9.9))
    edge.SetEnd(pcbnew.VECTOR2I_MM(12.1,10.1));edge.SetWidth(100000)
    edge.SetNetCode(netcode);edge.SetLocked(True);b.Add(edge)
    if shared:
        b.FindFootprintByReference('FIXED_OTHER').SetPosition(pcbnew.VECTOR2I_MM(12,10))
    p=rebuild.plan(b,poses,{},allow_owned_locked=True)
    uid=edge.m_Uuid.AsString()
    assert (uid in p['retired_track_uuids']) is (not shared)
    if not shared:
        assert any(r['track_uuid']==uid and r['disposition']=='owned_single_pad_kernel_requires_reconstruction'
                   for r in p['source_incident_boundaries'])
        rebuild.apply(b,p)


def test_single_pad_kernel_with_surviving_midsegment_joint_is_not_cut():
    b,poses,cells,edges=fixture()
    edge=pcbnew.PCB_TRACK(b);edge.SetStart(pcbnew.VECTOR2I_MM(11.9,9.9))
    edge.SetEnd(pcbnew.VECTOR2I_MM(12.1,10.1));edge.SetWidth(100000)
    edge.SetNetCode(edges[0].GetNetCode());edge.SetLocked(True);b.Add(edge)
    p=rebuild.plan(b,poses,{},allow_owned_locked=True)
    assert edge.m_Uuid.AsString() not in p['retired_track_uuids']


def test_two_moving_cells_have_stable_source_ids_for_destination_blockers():
    b,poses,cells,edges=fixture()
    other=pcbnew.NETINFO_ITEM(b,'OTHER_LOCAL');b.Add(other)
    refs=[]
    for ref,y in [('SECOND_OWNER',12),('SECOND_BYPASS',14)]:
        f=pcbnew.FOOTPRINT(b);f.SetReference(ref)
        p=pcbnew.PAD(f);p.SetNumber('1');p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetNet(other);f.Add(p)
        f.SetPosition(pcbnew.VECTOR2I_MM(21,y));b.Add(f);refs.append(ref)
        poses[ref]=(11.,float(y),0.)
    edge=pcbnew.PCB_TRACK(b);edge.SetStart(pcbnew.VECTOR2I_MM(21,12))
    edge.SetEnd(pcbnew.VECTOR2I_MM(21,14));edge.SetWidth(200000)
    edge.SetNet(other);b.Add(edge);cells['second_channel']=refs
    p=rebuild.plan(b,poses,cells,allow_owned_locked=True)
    assert p==rebuild.plan(b,poses,cells,allow_owned_locked=True)
    first=edges[0].m_Uuid.AsString();second=edge.m_Uuid.AsString()
    assert p['target_internal_chain_blockers'][first][0]['uuid']==second
    assert first in p['retired_track_uuids'] and second in p['retired_track_uuids']
    rebuild.apply(b,p)


@pytest.mark.parametrize('fault',[None,'undisclosed','forged_before','forged_after','changed_definition'])
def test_saved_draft_pose_scope_is_independently_received(fault,tmp_path):
    b,poses,cells,edges=fixture()
    source=tmp_path/'source.kicad_pcb';pcbnew.SaveBoard(str(source),b)
    child=pcbnew.LoadBoard(str(source))
    selected=child.FindFootprintByReference('OWNER')
    selected.SetPosition(pcbnew.VECTOR2I_MM(10,13))
    receipt=dict(final_moved_poses={'OWNER':dict(before=[10.,10.,0.],after=[10.,13.,0.])})
    if fault=='undisclosed':child.FindFootprintByReference('BYPASS').Move(pcbnew.VECTOR2I_MM(0,1))
    elif fault=='forged_before':receipt['final_moved_poses']['OWNER']['before'][1]=9.
    elif fault=='forged_after':receipt['final_moved_poses']['OWNER']['after'][1]=14.
    elif fault=='changed_definition':selected.SetValue('unapproved')
    if fault is None:
        assert rebuild._draft_pose_targets(b,child,receipt)=={'OWNER':[10.,13.,0.]}
    else:
        with pytest.raises(ValueError):rebuild._draft_pose_targets(b,child,receipt)


def test_destination_check_budget_refuses_and_restores_original_poses():
    b,poses,cells,edges=fixture()
    spec={'probe':dict(uuids=[edges[0].m_Uuid.AsString()],delta_nm=[0,3000000])}
    before=rebuild._source_binding(b)
    with pytest.raises(ValueError,match='budget_exhausted'):
        rebuild._target_chain_conflicts(b,poses,spec,set(),max_checks=1)
    assert rebuild._source_binding(b)==before


@pytest.mark.parametrize('rotation',[90.,180.,270.])
def test_explicit_single_owner_cardinal_rotation_rederives_external_pad_leg(rotation):
    b,_,_,edges=fixture()
    owner=b.FindFootprintByReference('OWNER');pad=list(owner.Pads())[0]
    pad.SetPosition(pcbnew.VECTOR2I_MM(10.5,10))
    edges[0].SetStart(pad.GetPosition())
    poses={'OWNER':[10.,10.,rotation]}
    before=rebuild._source_binding(b);original=local.copper_inventory(b)
    proposal=rebuild.plan(b,poses,{'renamed_owner_cell':['OWNER']},
        allow_owned_locked=True,allow_cardinal_rotations=True)
    assert rebuild._source_binding(b)==before
    assert edges[0].m_Uuid.AsString() in proposal['retired_track_uuids']
    assert proposal['requires_new_power_prefix_and_rated_current_receiving']
    assert not proposal['transformed_track_uuids']
    receipt=rebuild.apply(b,proposal)
    assert owner.GetOrientationDegrees()%360==rotation
    assert tuple(pad.GetPosition())!=(10500000,10000000)
    after=local.copper_inventory(b)
    for t in edges[1:]:assert after[t.m_Uuid.AsString()]==original[t.m_Uuid.AsString()]
    assert receipt['all_vias_and_force_current_copper_exact'] and not receipt['routing_admitted']


@pytest.mark.parametrize('fault',['no_opt_in','noncardinal','drilled','multiowner','forged_opt_in'])
def test_unproved_rotation_refuses_without_changing_source(fault):
    b,_,_,_=fixture();poses={'OWNER':[10.,10.,90.]};cells={'one':['OWNER']}
    opt_in=True
    if fault=='no_opt_in':opt_in=False
    elif fault=='noncardinal':poses['OWNER'][2]=45.
    elif fault=='drilled':list(b.FindFootprintByReference('OWNER').Pads())[0].SetDrillSize(pcbnew.VECTOR2I_MM(.2,.2))
    elif fault=='multiowner':
        poses['BYPASS']=[12.,10.,90.];cells['one'].append('BYPASS')
    before=rebuild._source_binding(b)
    with pytest.raises(ValueError):
        p=rebuild.plan(b,poses,cells,allow_owned_locked=True,allow_cardinal_rotations=opt_in)
        if fault=='forged_opt_in':
            p['allow_cardinal_rotations']=False;rebuild.apply(b,p)
    assert rebuild._source_binding(b)==before


def test_native_power_arc_and_its_attached_barrel_are_in_fixed_copper_preflight():
    b,poses,cells,edges=fixture()
    arc=pcbnew.PCB_ARC(b);arc.SetStart(pcbnew.VECTOR2I_MM(30,10))
    arc.SetMid(pcbnew.VECTOR2I_MM(31,11));arc.SetEnd(pcbnew.VECTOR2I_MM(32,10))
    arc.SetWidth(1000000);arc.SetNetCode(edges[0].GetNetCode());arc.SetLocked(True);b.Add(arc)
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(31,11))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetNetCode(arc.GetNetCode());b.Add(via)
    scope=rebuild.retained_power_items(b,{'LOCAL_ROLE':{}})
    assert arc.m_Uuid.AsString() in scope and via.m_Uuid.AsString() in scope


@pytest.mark.parametrize('failure',[None,'draft','construction'])
def test_prepare_receives_actual_construction_under_original_stack_policy(tmp_path,monkeypatch,failure):
    import json
    import cec_assembly_envelope as assembly
    import cec_constraints as constraints
    import cec_current_topology as topology
    import cec_placement_geometry as geometry
    import cec_force_current as force
    b,poses,cells,edges=fixture()
    control=tmp_path/'control';control.mkdir()
    draftdir=tmp_path/'draft';draftdir.mkdir()
    source=control/'board.kicad_pcb';draft=draftdir/'board.kicad_pcb'
    pcbnew.SaveBoard(str(source),b);child=pcbnew.LoadBoard(str(source))
    for ref,target in poses.items():
        child.FindFootprintByReference(ref).SetPosition(pcbnew.VECTOR2I_MM(*target[:2]))
    pcbnew.SaveBoard(str(draft),child)
    intent=tmp_path/'intent.json';intent.write_text(json.dumps(dict(cells={
        'renamed_channel':dict(first='OWNER',second='BYPASS')})))
    receipt=dict(source_sha256=force._hash(source),board_sha256=force._hash(draft),
        intent=str(intent),intent_sha256=force._hash(intent),placement_and_paired_stack_pass=True,
        final_moved_poses={ref:dict(before=[b.FindFootprintByReference(ref).GetPosition().x/1e6,
            10.,0.],after=list(target)) for ref,target in poses.items()})
    (draftdir/'placement-draft.json').write_text(json.dumps(receipt))
    source_policy={'source_pinned':'never_read_policy_from_draft'};calls=[]
    monkeypatch.setattr(assembly,'declared_policy',lambda path:source_policy)
    monkeypatch.setattr(assembly,'dependencies',lambda *args:[])
    def stack(path,params=None):
        assert params=={'assembly_envelope':source_policy}
        calls.append(str(path));return dict(ok=True,applicable=True,check_count=17)
    monkeypatch.setattr(assembly,'candidate_check',stack)
    monkeypatch.setattr(assembly,'footprint_reservation_check',lambda board:dict(ok=True))
    monkeypatch.setattr(constraints,'_device_bypass_assignment',lambda *args,**kwargs:dict(assigned={}))
    monkeypatch.setattr(topology,'board_current_domains',lambda *args:{})
    monkeypatch.setattr(geometry,'evaluate',lambda path,**kwargs:dict(
        ok=not ((failure=='draft' and Path(path)==draft)
                or (failure=='construction' and Path(path)!=draft))))
    out=tmp_path/'private'
    if failure=='draft':
        with pytest.raises(ValueError,match='stack_receiving_refused'):
            rebuild.prepare(source,draft,out,board_hint='synthetic',allow_owned_locked=True)
        assert not out.exists()
    else:
        report=rebuild.prepare(source,draft,out,board_hint='synthetic',allow_owned_locked=True)
        assert len(calls)==2 and report['strict_saved_copper_identity_exact']
        assert report['all_unrelated_authored_nodes_exact']
        assert report['source_draft_and_code_unchanged']
        assert report['implementation_files_sha256']==force._code_identity()
        assert report['source_saved_family']==force._family(source,'synthetic')
        if failure=='construction':
            assert report['blocked_stage']=='placement_and_paired_stack_revalidation'
        assert not report['routing_admitted'] and not report['release_authority']
