"""Exact upgrade of an already proved consumer island's undersized path.

This is not an inherited-width waiver. The unchanged native single-consumer
proof supplies the existing load/tap. New same-face copper must carry the
entire actual floor; parts, barrels, allocation, main buses and rules stay put.
"""
import json
import hashlib
import math
import tempfile
import time
import uuid
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_consumer_corner_miter as webs
import cec_copper_echo as syntax
import cec_current_debt as debt
import cec_distributed_supply as supply
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as ordinary
import cec_pair_local_reference_refinement as chains
import cec_sensitive_scalar_path_reflow as paths
import cec_supply_consumer_branch as consumer
from cec_generated_pickup_retirement import _scoped_terminal_graph
from cec_native_items import discard_items

POLICY = 'native-retained-consumer-actual-floor-repair-v1'


def require(value, message):
    if not value:
        raise ValueError(message)


def actual_floor(board, source, proof, ids, face):
    """Read-only effort selection; saved plan/receiving derive this afresh."""
    spec = fr._project_netclass_resolver(str(source), board=board)(proof['net']) or {}
    return max(*(math.ceil(proof['retained_island_track_requirements'][u]['required_mm']*1e6) for u in ids),
        board.GetDesignSettings().m_TrackMinWidth,
        math.ceil(float(spec.get('track_width') or 0)*1e6),
        math.ceil(float((spec.get('track_width_by_layer_mm') or {}).get(fab.COPPER_LAYER_IDS[face]) or 0)*1e6))


def plan(source, *, board_hint, retired_track_uuids, points_nm, allow_locked_source=False):
    source = Path(source).resolve()
    require(type(board_hint) is str and bool(board_hint) and type(allow_locked_source) is bool,
        'explicit_retained_floor_context_required')
    ids = ordinary._ids(retired_track_uuids, 'retained_floor_cut', 8)
    require(bool(ids), 'nonempty_retained_floor_path_required')
    deadline = time.monotonic()+10.
    board = pcbnew.LoadBoard(str(source))
    inventory = consumer.inventory(board, board_hint=board_hint, timeout_s=10.)
    require(inventory['complete'], 'complete_native_consumer_island_proof_required')
    proofs = [q for q in inventory['proofs'] if ids <= q['retained_island_track_requirements'].keys()]
    require(len(proofs) == 1, 'one_existing_exclusive_consumer_island_required')
    proof = proofs[0]
    # A whole-stage allowance is a conservative default, not proof that an
    # exclusive resistor-fed voltage monitor carries the output load. Keep
    # unknown branches conservative, but dispatch a positively closed native
    # monitor to its own owner instead of widening it to the stage allowance.
    import cec_resistive_monitor_branch as monitor
    for contract in proof['budget'].get('closed_monitor_loads', []):
        try:
            branch = monitor.plan(board, contract['pad_uuid'], timeout_s=2.)
        except ValueError:
            continue
        if branch['source_resistive_monitor_contract'] == contract:
            require(not ids & set(branch['track_uuids']),
                'positively_typed_monitor_requires_monitor_reconnection_owner')
    live = {force._uid(t): t for t in board.GetTracks()}
    old = [live[u] for u in sorted(ids)]
    owned = {force._uid(i) for g in board.Groups() for i in g.GetItems()}
    require(not ids & owned and all(t.GetClass() == 'PCB_TRACK' and not t.GetParentGroup()
        and not t.HasSolderMask() and (not t.IsLocked() or allow_locked_source)
        and 0 < t.GetLength() <= 32000000 for t in old)
        and len({(int(t.GetLayer()), t.GetWidth(), bool(t.IsLocked()), t.GetNetname()) for t in old}) == 1,
        'uniform_plain_explicitly_owned_retained_floor_path_required')
    first = old[0]
    _, source_nodes = additive._nodes(source)
    process = chains._process(source_nodes[force._uid(first)])
    require(all(chains._process(source_nodes[force._uid(t)]) == process for t in old),
        'every_original_track_process_field_must_match')
    face = int(first.GetLayer())
    require(face in (pcbnew.F_Cu, pcbnew.B_Cu) and sum(t.GetLength() for t in old) <= 48000000,
        'bounded_outer_retained_floor_path_required')
    before = [list(p) for p in chains._chain(old)]
    points = [list(p) for p in paths._points(points_nm)]
    require(len(points) <= 16 and points[0] == before[0] and points[-1] == before[-1],
        'literal_fixed_source_end_ports_required')
    req = proof['retained_island_track_requirements']
    require(all(first.GetWidth() < math.ceil(req[u]['required_mm']*1e6) for u in ids),
        'this_owner_only_repairs_actual_underfloor_source_strokes')
    spec = fr._project_netclass_resolver(str(source), board=board)(proof['net']) or {}
    width = actual_floor(board, source, proof, ids, face)
    require(first.GetWidth() < width <= 1000000, 'positive_bounded_actual_consumer_floor_required')
    gap = max(board.GetDesignSettings().m_MinClearance, math.ceil(float(spec.get('clearance') or .2)*1e6))
    new = []
    for a, z in zip(points, points[1:]):
        t = first.Duplicate()
        t.SetStart(pcbnew.VECTOR2I(*a))
        t.SetEnd(pcbnew.VECTOR2I(*z))
        t.SetWidth(width)
        require(fr._edge_leg_clear(board, t.GetStart(), t.GetEnd(), (width+1)//2)
            and fr._tap_foreign_clear(board, t.GetStart(), t.GetEnd(), width, face, gap, {first.GetNetCode()}),
            'actual_floor_foreign_clearance_hole_rule_area_or_edge_refused')
        new.append(t)
    require(sum(t.GetLength() for t in new) <= sum(t.GetLength() for t in old)+8000000,
        'bounded_actual_floor_reconstruction_length_required')
    contacts = []
    peers = [*board.GetTracks(), *(p for f in board.GetFootprints() for p in f.Pads()), *board.Zones()]
    require(len(peers) <= 16384, 'bounded_actual_floor_contact_inventory_required')
    for item in peers:
        if force._uid(item) in ids or item.GetNetname() != first.GetNetname() or not item.IsOnLayer(face):
            continue
        if item.GetClass() == 'ZONE':
            require(item.GetIsRuleArea() or not any(item.Outline().Collide(t.GetEffectiveShape(face), 0) for t in old),
                'power_pour_contact_requires_separate_owner')
            continue
        if any(t.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face), 0) for t in old):
            contacts.append(webs.retained_contact_proof(item, old, new, face, first.GetWidth(), deadline))
    groups = [g for g in board.Groups() if g.GetName().startswith(consumer.PREFIX)
        and g.GetName()[len(consumer.PREFIX):].split('|')[:2] == [proof['root_pad_uuid'], proof['anchor_uuid']]]
    require(len(groups) == 1, 'one_exact_retained_floor_allocation_group_required')
    require(time.monotonic() < deadline, 'retained_floor_planning_deadline')
    return dict(policy=POLICY, authority_sha256=force._hash(Path(__file__).resolve()),
        source_sha256=force._hash(source), board_hint=board_hint, retired_track_uuids=sorted(ids),
        points_nm=points, source_points_nm=before, layer=face, source_width_nm=first.GetWidth(),
        actual_floor_width_nm=width, locked=bool(first.IsLocked()), allow_locked_source=allow_locked_source,
        root_pad_uuid=proof['root_pad_uuid'], anchor_uuid=proof['anchor_uuid'], source_budget=proof['budget'],
        group_uuid=force._uid(groups[0]), source_group_sha256=hashlib.sha256(repr(syntax._freeze(
            additive._nodes(source)[1][force._uid(groups[0])])).encode()).hexdigest(),
        native_retained_contact_webs=contacts, source_current_reduced=False, branch_sharing_assumed=False,
        new_barrels_or_part_moves_authorized=False, release_authority=False)


def construct(source, proposal):
    fresh = plan(source, board_hint=proposal['board_hint'], retired_track_uuids=proposal['retired_track_uuids'],
        points_nm=proposal['points_nm'], allow_locked_source=proposal['allow_locked_source'])
    require(fresh == proposal, 'stale_or_forged_retained_floor_proposal')
    board = pcbnew.LoadBoard(str(Path(source).resolve()))
    old = [t for t in board.GetTracks() if force._uid(t) in proposal['retired_track_uuids']]
    template = old[0].Duplicate()
    discard_items(board, old)
    for index, (a, z) in enumerate(zip(proposal['points_nm'], proposal['points_nm'][1:])):
        t = template.Duplicate()
        token = json.dumps([POLICY, proposal['source_sha256'], proposal['retired_track_uuids'], proposal['points_nm'], index])
        t.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL, token))))
        t.SetStart(pcbnew.VECTOR2I(*a))
        t.SetEnd(pcbnew.VECTOR2I(*z))
        t.SetWidth(proposal['actual_floor_width_nm'])
        board.Add(t)
    additive._ground_refill(board)
    return board


def receive(source, candidate, proposal, *, board_hint):
    result = dict(ok=False, complete=False, errors=[], current_qualified=False, inherited_debt_qualified=False,
        source_current_reduced=False, branch_sharing_assumed=False, release_authority=False)
    try:
        source, candidate = [Path(p).resolve() for p in (source, candidate)]
        require(source != candidate and board_hint == proposal['board_hint'], 'distinct_literal_floor_receiving_context_required')
        epoch = force._code_identity()
        families = [force._family(p, board_hint) for p in (source, candidate)]
        require(force._sidecars(source) == force._sidecars(candidate), 'retained_floor_project_or_rules_changed')
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        fresh = plan(source, board_hint=board_hint, retired_track_uuids=proposal['retired_track_uuids'],
            points_nm=proposal['points_nm'], allow_locked_source=proposal['allow_locked_source'])
        require(fresh == proposal, 'saved_retained_floor_plan_changed')
        _, old = additive._nodes(source)
        _, got = additive._nodes(candidate)
        retired = set(proposal['retired_track_uuids'])
        added = set(got)-set(old)
        require(set(old)-set(got) == retired and len(added) == len(proposal['points_nm'])-1,
            'exact_retained_floor_cut_and_planar_additions_required')
        with tempfile.TemporaryDirectory(prefix='cec-retained-floor-replay-') as work:
            path = force._copy_family(source, Path(work)/'expected')
            field._save_field_snapshot(construct(source, proposal), path)
            _, expected = additive._nodes(path)
            require(got.keys() == expected.keys() and all(syntax._freeze(got[u]) == syntax._freeze(expected[u]) for u in got),
                'exact_saved_floor_source_reconstruction_differs')
        inventory = consumer.inventory(child, board_hint=board_hint, timeout_s=10.)
        matches = [q for q in inventory['proofs'] if q['root_pad_uuid'] == proposal['root_pad_uuid']]
        require(inventory['complete'] and len(matches) == 1 and matches[0]['budget'] == proposal['source_budget']
            and matches[0]['anchor_uuid'] == proposal['anchor_uuid']
            and added <= matches[0]['retained_island_track_requirements'].keys(),
            'same_saved_complete_consumer_budget_tap_and_island_required')
        live = {force._uid(t): t for t in child.GetTracks()}
        require(all(live[u].GetWidth() >= math.ceil(matches[0]['retained_island_track_requirements'][u]['required_mm']*1e6)
            for u in added), 'every_saved_incoming_stroke_must_carry_actual_consumer_floor')
        first = ordinary._partition(parent, time.monotonic()+10., retired_uuids=retired)
        last = ordinary._partition(child, time.monotonic()+10., retained_keys=set().union(*first))
        require(all(any(a <= z for z in last) for a in first), 'retained_floor_lost_surviving_native_partition')
        source_tracks = {force._uid(t): t for t in parent.GetTracks()}
        boundaries = ordinary._boundaries(parent, child, [source_tracks[u] for u in retired], time.monotonic()+10.)
        drilled = [_scoped_terminal_graph(b, matches[0]['net'], timeout_s=10.) for b in (parent, child)]
        require(drilled[0]['pad_uuids'] == drilled[1]['pad_uuids'], 'retained_floor_changed_actual_drilled_terminals')
        budget = proposal['source_budget']
        contract = dict(net=matches[0]['net'], current_authority=budget['current_authority'],
            required_by_layer_mm=budget['required_by_layer_mm'], routing_layers=list(budget['required_by_layer_mm']))
        graphs = [supply._graph(b, matches[0]['net'], contract) for b in (parent, child)]
        require(all(not g['unsupported_terminal_uuids'] and g['planar_full_width_components'] is not None for g in graphs),
            'complete_actual_allocated_full_width_terminal_graphs_required')
        require(all(any(set(a) <= set(z) for z in graphs[1]['planar_full_width_components'])
            for a in graphs[0]['planar_full_width_components']), 'retained_floor_lost_preexisting_rated_terminal_join')
        current = debt.receive(source, candidate, board_hint=board_hint)
        require(current['ok'] and current['complete'], 'retained_floor_whole_current_debt_worsened')
        require(epoch == force._code_identity() and proposal['authority_sha256'] == force._hash(Path(__file__).resolve())
            and families == [force._family(p, board_hint) for p in (source, candidate)], 'retained_floor_epoch_changed')
        result.update(ok=True, complete=True, retired_track_uuids=sorted(retired), added_native_uuids=sorted(added),
            source_sha256=force._hash(source), candidate_sha256=force._hash(candidate), source_candidate_and_code_unchanged=True,
            exact_native_source_reconstruction=True, actual_floor_width_nm=proposal['actual_floor_width_nm'],
            independent_whole_current_debt=current, all_surviving_native_partitions_preserved=True,
            restored_full_width_source_boundaries=boundaries, actual_drilled_terminal_graphs=drilled,
            allocated_full_width_terminal_graphs=graphs, all_preexisting_allocated_full_width_joins_preserved=True,
            same_source_consumer_proof=matches[0], every_incoming_actual_floor_rederived=True,
            source_allocation_group_exact=True, new_vias=0, pads_moved=0,
            full_native_drc_kelvin_fields_stack_and_release_still_required=True)
    except (ValueError, RuntimeError, KeyError, TypeError, OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
