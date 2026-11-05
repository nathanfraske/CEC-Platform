import math
import pcbnew
import pytest
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track
from test_native_pending_joint_cohort import row
from root_native_pending_branch_forest_20261013 import plan


def tree(rotation=0, shift=(0, 0), failure=None):
    specs = [(10, 20, 'RENAMED_A'), (30, 20, 'RENAMED_A'), (20, 30, 'RENAMED_A'),
             (20, 20, 'RENAMED_B')]
    if failure == 'terminal': specs.append((20, 20, 'RENAMED_A'))
    if failure == 'interior': specs.append((15, 16, 'RENAMED_A'))
    board = _board(specs)
    edges = [track(board, 'RENAMED_A', (10, 20), (20, 20)),
             track(board, 'RENAMED_A', (20, 20), (30, 20)),
             track(board, 'RENAMED_A', (20, 20), (20, 30))]
    if failure == 'width': edges[1].SetWidth(250000)
    if failure == 'lock': edges[1].SetLocked(True)
    if failure == 'group':
        group = pcbnew.PCB_GROUP(board); group.SetName('UNRELATED_OWNER'); board.Add(group)
        group.AddItem(edges[1])
    if failure == 'typed':
        group = pcbnew.PCB_GROUP(board); group.SetName('CEC_LOCAL_SUPPLY_ALLOCATION_V1|opaque'); board.Add(group)
        group.AddItem(edges[1])
    if failure == 'barrel':
        via = pcbnew.PCB_VIA(board); via.SetPosition(pcbnew.VECTOR2I_MM(20, 20))
        via.SetWidth(600000); via.SetDrill(300000); via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetNet(board.FindNet('RENAMED_A')); board.Add(via)
    if failure == 'interior':
        track(board, 'RENAMED_A', (15, 20), (15, 16))
    for item in [*board.GetFootprints(), *board.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0, 0), pcbnew.EDA_ANGLE(rotation * 90, pcbnew.DEGREES_T))
        item.Move(pcbnew.VECTOR2I_MM(*shift))
    return board, edges


@pytest.mark.parametrize('rotation', range(4))
@pytest.mark.parametrize('shift', [(0, 0), (3, -2)])
def test_whole_source_branch_reaches_clear_ports_without_consuming_real_terminals(rotation, shift):
    board, edges = tree(rotation, shift)
    before = [(tuple(t.GetStart()), tuple(t.GetEnd()), t.GetWidth()) for t in edges]
    remaining, forests, proof = plan(board, [row(edges[0])], clearance_for=lambda n: 200000)
    assert not remaining and len(forests) == 1 and proof['complete']
    forest = forests[0]
    assert set(forest['member_uuids']) == {force._uid(t) for t in edges}
    assert len(forest['external_ports_nm']) == 3 and len(forest['route_rows']) == 2
    assert all(r['width'] == 200000 and r['layer'] == pcbnew.F_Cu for r in forest['route_rows'])
    assert before == [(tuple(t.GetStart()), tuple(t.GetEnd()), t.GetWidth()) for t in edges]
    assert not proof['automatic_retirement_authorized'] and not proof['release_authority']


@pytest.mark.parametrize('failure', ['terminal', 'barrel', 'width', 'lock', 'group', 'typed', 'interior'])
def test_native_terminal_body_width_and_owner_boundaries_fail_closed(failure):
    board, edges = tree(failure=failure)
    with pytest.raises(ValueError):
        plan(board, [row(edges[0])], clearance_for=lambda n: 200000)


@pytest.mark.parametrize('bad', [True, 0, -1, math.nan, math.inf, 10.1])
def test_only_finite_explicit_bounded_work_is_accepted(bad):
    board, edges = tree()
    with pytest.raises(ValueError):
        plan(board, [row(edges[0])], clearance_for=lambda n: 200000, timeout_s=bad)


def test_already_clear_tree_stays_outside_the_branch_reconstruction_scope():
    board, edges = tree()
    for fp in board.GetFootprints():
        if any(p.GetNetname() == 'RENAMED_B' for p in fp.Pads()):
            fp.Move(pcbnew.VECTOR2I_MM(0, -5))
    original = [row(t) for t in edges]
    remaining, forests, proof = plan(board, original, clearance_for=lambda n: 200000)
    assert len(remaining) == 3 and not forests and not proof['exact_retired_uuids']


def test_complete_native_branch_scope_cannot_exceed_the_cut_length_bound():
    board, edges = tree()
    with pytest.raises(ValueError):
        plan(board, [row(edges[0])], clearance_for=lambda n: 200000, maximum_cut_nm=10000000)


@pytest.mark.parametrize('rotation', range(4))
@pytest.mark.parametrize('shift', [(0, 0), (3, -2)])
def test_literal_body_junction_closes_whole_edges_without_rounding_or_new_ports(rotation, shift):
    board = _board([(10, 20, 'ARBITRARY_RAIL'), (30, 20, 'ARBITRARY_RAIL'),
                    (20, 30, 'ARBITRARY_RAIL'), (20, 20, 'OTHER')])
    edges = [track(board, 'ARBITRARY_RAIL', (10, 20), (30, 20)),
             track(board, 'ARBITRARY_RAIL', (20, 20), (20, 30))]
    for item in [*board.GetFootprints(), *board.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0, 0), pcbnew.EDA_ANGLE(rotation * 90, pcbnew.DEGREES_T))
        item.Move(pcbnew.VECTOR2I_MM(*shift))
    before = [(tuple(t.GetStart()), tuple(t.GetEnd()), t.GetWidth()) for t in edges]
    remaining, forests, proof = plan(board, [row(edges[1])], clearance_for=lambda n: 200000,
                                    allow_literal_body_cohort=True)
    assert not remaining and len(forests) == 1
    assert set(forests[0]['member_uuids']) == {force._uid(t) for t in edges}
    assert len(forests[0]['external_ports_nm']) == 3 and len(forests[0]['route_rows']) == 2
    assert before == [(tuple(t.GetStart()), tuple(t.GetEnd()), t.GetWidth()) for t in edges]
    assert proof['saved_whole_source_current_receiving_required']
    assert not proof['current_qualified'] and not proof['release_authority']


def test_unrepresented_track_body_contact_requires_actual_bounded_closure():
    board, edges = tree(failure='interior')
    _, forests, proof = plan(board, [row(edges[0])], clearance_for=lambda n: 200000,
                            allow_literal_body_cohort=True)
    assert len(forests[0]['member_uuids']) == 4
    assert len(forests[0]['external_ports_nm']) == 4
    assert len(proof['exact_retired_uuids']) == 4


def test_mixed_source_locks_only_tighten_with_explicit_opt_in():
    board, edges = tree(failure='lock')
    _, forests, proof = plan(board, [row(edges[0])], clearance_for=lambda n: 200000,
                            allow_lock_tightening=True)
    assert all(r['locked'] for r in forests[0]['route_rows'])
    assert forests[0]['source_lock_tightened'] and proof['saved_whole_source_current_receiving_required']
    assert edges[1].IsLocked() and not edges[0].IsLocked()


@pytest.mark.parametrize('kind',['PAD','PCB_VIA','OFFCENTER_PAD'])
def test_actual_clear_body_terminal_is_an_exact_retained_port_not_a_new_barrel(kind):
    board,edges=tree()
    if kind in ('PAD','OFFCENTER_PAD'):
        fp=pcbnew.FOOTPRINT(board);fp.SetPosition(pcbnew.VECTOR2I_MM(15,20.3 if kind=='OFFCENTER_PAD' else 20))
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetPosition(fp.GetPosition());p.SetSize(pcbnew.VECTOR2I_MM(1,1))
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(layers);p.SetNet(board.FindNet('RENAMED_A'))
        fp.Add(p);board.Add(fp);terminal=p
    else:
        terminal=pcbnew.PCB_VIA(board);terminal.SetPosition(pcbnew.VECTOR2I_MM(15,20))
        terminal.SetWidth(600000);terminal.SetDrill(300000);terminal.SetViaType(pcbnew.VIATYPE_THROUGH)
        terminal.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);terminal.SetNet(board.FindNet('RENAMED_A'));board.Add(terminal)
    _,forests,proof=plan(board,[row(edges[0])],clearance_for=lambda n:200000,allow_literal_body_cohort=True)
    ports=forests[0]['actual_retained_body_terminal_ports']
    assert len(ports)==1 and ports[0]['native_uuid']==force._uid(terminal)
    assert ports[0]['at_nm']==list(terminal.GetPosition()) and ports[0]['kind']==terminal.GetClass()
    assert ports[0]['actual_retained_terminal_material_contact']
    assert ports[0]['source_center_in_owned_actual_copper'] is (kind!='OFFCENTER_PAD')
    assert not ports[0]['new_barrel_or_current_authority'] and proof['saved_whole_source_current_receiving_required']


def test_only_exact_pending_track_bodies_can_be_excluded_from_scope_not_clearance_authority():
    board,edges=tree(failure='barrel')
    foreign_fp=next(f for f in board.GetFootprints() if any(p.GetNetname()=='RENAMED_B' for p in f.Pads()))
    foreign_fp.Move(pcbnew.VECTOR2I_MM(0,-5))
    temporary=track(board,'RENAMED_B',(18,20),(22,20))
    with pytest.raises(ValueError):
        plan(board,[row(edges[0])],clearance_for=lambda n:200000)
    remaining,forests,proof=plan(board,[row(edges[0])],clearance_for=lambda n:200000,
        provisional_reconstruction_track_uuids=[force._uid(temporary)])
    assert len(remaining)==1 and not forests
    assert proof['excluded_provisional_obstacle_track_uuids']==[force._uid(temporary)]
    assert proof['exclusions_only_for_scope_planning_not_saved_clearance_authority']
    assert not proof['release_authority'] and not proof['current_qualified']


@pytest.mark.parametrize('failure',['terminal','barrel'])
def test_declared_transient_edges_never_ignore_real_foreign_lands_or_barrels(failure):
    board,edges=tree(failure=failure)
    with pytest.raises(ValueError):
        plan(board,[row(edges[0])],clearance_for=lambda n:200000,
             provisional_reconstruction_track_uuids=[force._uid(edges[1])])


@pytest.mark.parametrize('rotation',range(4))
def test_closed_overlapping_loop_with_two_real_external_terminals_is_one_transaction(rotation):
    board=_board([(10,20,'RENAMED_A'),(30,20,'RENAMED_A'),(20,20,'RENAMED_B')])
    edges=[track(board,'RENAMED_A',(10,20),(20,20)),
           track(board,'RENAMED_A',(20,20),(30,20)),
           track(board,'RENAMED_A',(20,20),(20.02,20.02)),
           track(board,'RENAMED_A',(20.02,20.02),(20.02,20))]
    for item in [*board.GetFootprints(),*board.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(90*rotation,pcbnew.DEGREES_T))
    _,forests,proof=plan(board,[row(edges[0])],clearance_for=lambda n:200000,
                        allow_literal_body_cohort=True)
    assert len(forests)==1 and len(forests[0]['route_rows'])==1
    assert len(forests[0]['external_ports_nm'])==2 and forests[0]['literal_two_port_body_cohort']
    assert set(forests[0]['member_uuids'])=={force._uid(t) for t in edges}
    assert proof['saved_whole_source_current_receiving_required'] and not proof['release_authority']


@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('eligible',[True,False])
def test_free_pending_branch_uses_real_ports_before_another_route_can_block_its_anonymous_joint(tmp_path,monkeypatch,rotation,eligible):
    import cec_field_coupling as field
    import cec_ordinary_route_receiving as ordinary
    board,edges=tree(rotation)
    for fp in board.GetFootprints():
        if any(p.GetNetname()=='RENAMED_B' for p in fp.Pads()):fp.Move(pcbnew.VECTOR2I_MM(0,-50))
    path=tmp_path/'ordinary-branch.kicad_pcb';field._save_field_snapshot(board,path)
    board=pcbnew.LoadBoard(str(path));lookup={force._uid(t):t for t in board.GetTracks()}
    monkeypatch.setattr(ordinary,'eligible_nets',lambda *a,**k:{'RENAMED_A'} if eligible else set())
    remaining,forests,proof=plan(board,[row(lookup[force._uid(t)]) for t in edges],
        clearance_for=lambda n:200000,allow_literal_body_cohort=True,
        normalize_free_pending_junctions=True,source_path=path,board_hint='SYNTHETIC')
    if eligible:
        assert not remaining and len(forests)==1 and len(forests[0]['external_ports_nm'])==3
        assert len(forests[0]['route_rows'])==2
    else:assert len(remaining)==3 and not forests
    assert proof['proactive_junction_scope_positive_ordinary_nets_only'] and not proof['release_authority']


@pytest.mark.parametrize('eligible',[True,False])
def test_offcenter_retained_barrel_capture_needs_positive_ordinary_context_and_all_face_clearance(tmp_path,monkeypatch,eligible):
    import cec_field_coupling as field
    import cec_ordinary_route_receiving as ordinary
    board,edges=tree()
    v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I_MM(15,20.3))
    v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(board.FindNet('RENAMED_A'));board.Add(v)
    uid=force._uid(v);path=tmp_path/'offcenter-ordinary-barrel.kicad_pcb'
    field._save_field_snapshot(board,path);board=pcbnew.LoadBoard(str(path))
    lookup={force._uid(t):t for t in board.GetTracks()}
    monkeypatch.setattr(ordinary,'eligible_nets',lambda *a,**k:{'RENAMED_A'} if eligible else set())
    options=dict(clearance_for=lambda n:200000,allow_literal_body_cohort=True,
        normalize_free_pending_junctions=True,source_path=path,board_hint='SYNTHETIC')
    if not eligible:
        with pytest.raises(ValueError):plan(board,[row(lookup[force._uid(t)]) for t in edges],**options)
    else:
        _,forests,proof=plan(board,[row(lookup[force._uid(t)]) for t in edges],**options)
        port=next(r for r in forests[0]['actual_retained_body_terminal_ports'] if r['native_uuid']==uid)
        assert not port['source_center_in_owned_actual_copper'] and port['source_positive_ordinary_barrel_context']
        assert not port['new_barrel_or_current_authority'] and not proof['release_authority']


@pytest.mark.parametrize('rotation',range(4))
@pytest.mark.parametrize('eligible',[True,False])
def test_existing_barrel_root_is_positive_ordinary_only_and_retains_native_via_geometry(tmp_path,monkeypatch,rotation,eligible):
    import cec_field_coupling as field
    import cec_ordinary_route_receiving as ordinary
    board,edges=tree(rotation)
    at=tuple(edges[1].GetEnd())
    for fp in board.GetFootprints():
        if tuple(fp.GetPosition())==at:fp.Move(pcbnew.VECTOR2I_MM(50,50))
    v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I(*at));v.SetWidth(600000);v.SetDrill(300000)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetNet(board.FindNet('RENAMED_A'));board.Add(v);uid=force._uid(v)
    path=tmp_path/'barrel-root.kicad_pcb';field._save_field_snapshot(board,path);board=pcbnew.LoadBoard(str(path))
    lookup={force._uid(t):t for t in board.GetTracks()}
    monkeypatch.setattr(ordinary,'eligible_nets',lambda *a,**k:{'RENAMED_A'} if eligible else set())
    _,forests,proof=plan(board,[row(lookup[force._uid(t)]) for t in edges],clearance_for=lambda n:200000,
        allow_literal_body_cohort=True,normalize_free_pending_junctions=True,
        source_path=path,board_hint='SYNTHETIC',prefer_existing_ordinary_barrel_ports=True)
    star=forests[0]['existing_positive_ordinary_barrel_tree']
    if eligible:
        assert star['native_barrel_uuid']==uid and star['at_nm']==list(at)
        assert all(r['start']==at for r in forests[0]['route_rows'])
        assert not star['new_barrel_or_current_credit']
    else:assert star is None
    assert lookup[uid].GetWidth(0)==600000 and lookup[uid].GetDrillValue()==300000
    assert not proof['release_authority'] and not proof['current_qualified']


@pytest.mark.parametrize('rotation',range(4))
def test_overlapping_pending_trees_are_replanned_as_one_nonduplicated_native_cohort(tmp_path,monkeypatch,rotation):
    import cec_field_coupling as field
    import cec_ordinary_route_receiving as ordinary
    specs=[(4.595,.6591,'RENAMED_A'),(8.125,5.5991,'RENAMED_A'),
           (9.755,4.6491,'RENAMED_A'),(11.035,2.37,'RENAMED_A'),(7.735,4.5791,'RENAMED_B')]
    board=_board(specs)
    for fp in board.GetFootprints():
        for p in fp.Pads():p.SetSize(pcbnew.VECTOR2I_MM(.8,.4))
    points=[((9.755,4.6491),(8.055,4.8991)),((7.4459,2.6591),(7.735,2.37)),
            ((8.7,5.6),(7.735,2.37)),((7.735,2.37),(11.035,2.37)),
            ((8.055,4.8991),(7.735,4.5791)),((4.595,.6591),(7.4459,2.6591)),
            ((7.735,4.5791),(8.7,5.6))]
    edges=[track(board,'RENAMED_A',a,b) for a,b in points]
    for index,t in enumerate(edges,1):t.m_Uuid.Clone(pcbnew.KIID('00000000-0000-0000-0000-'+format(index,'012x')))
    v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I_MM(8.7,5.6));v.SetWidth(600000);v.SetDrill(300000)
    v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    v.SetNet(board.FindNet('RENAMED_A'));board.Add(v)
    for item in [*board.GetFootprints(),*board.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(90*rotation,pcbnew.DEGREES_T))
        item.Move(pcbnew.VECTOR2I_MM(30,30))
    path=tmp_path/'joined-trees.kicad_pcb';field._save_field_snapshot(board,path);board=pcbnew.LoadBoard(str(path))
    lookup={force._uid(t):t for t in board.GetTracks()};ids=[force._uid(t) for t in edges]
    monkeypatch.setattr(ordinary,'eligible_nets',lambda *a,**k:{'RENAMED_A'})
    remaining,forests,proof=plan(board,[row(lookup[u]) for u in ids],clearance_for=lambda n:200000,
        allow_literal_body_cohort=True,normalize_free_pending_junctions=True,
        provisional_reconstruction_track_uuids=ids,source_path=path,board_hint='SYNTHETIC')
    assert not remaining and len(forests)==1
    assert set(forests[0]['member_uuids'])==set(ids) and len(proof['exact_retired_uuids'])==len(ids)
    assert forests[0]['merged_previously_planned_native_member_cohorts']
    assert all(r['width']==200000 for r in forests[0]['route_rows'])
    assert not proof['current_qualified'] and not proof['release_authority']


@pytest.mark.parametrize('failure', ['terminal', 'barrel', 'width', 'group', 'typed'])
def test_literal_body_closure_never_seizes_terminal_or_width_or_owner_boundaries(failure):
    board, edges = tree(failure=failure)
    with pytest.raises(ValueError):
        plan(board, [row(edges[0])], clearance_for=lambda n: 200000,
             allow_literal_body_cohort=True, allow_lock_tightening=True)


@pytest.mark.parametrize('option', ['allow_literal_body_cohort', 'allow_lock_tightening'])
@pytest.mark.parametrize('bad', [1, 'true', None])
def test_body_closure_and_lock_tightening_require_literal_booleans(option, bad):
    board, edges = tree()
    with pytest.raises(ValueError):
        plan(board, [row(edges[0])], clearance_for=lambda n: 200000, **{option: bad})
