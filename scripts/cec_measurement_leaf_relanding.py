"""Stationary, Source-owned direct-shunt input re-landing on its actual pad.

This is not fixed-boundary leaf reflow. A separately derived canonical Source
demand permits a different *inward* landing on the same unchanged shunt pad.
Only the original uniform thin input leaf is retireable. Every force object,
barrel, component pose, opaque original node and rule companion stays exact.
Saved native reconstruction, original partitions, physical inward departure,
foreign clearance, field and craft are independently received. All enclosing
absolute Kelvin/current/native/parity/release gates remain mandatory.
"""
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_current_topology as current
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fr as fr
import cec_isolated_measurement_completion as isolated
import cec_measurement_leaf as leaf
import cec_measurement_route_policy as policy
import cec_measurement_terminal_access as access
import cec_measurement_terminal_route as terminal
import cec_ordinary_route_receiving as ordinary
import cec_route_dimensions as dimensions
import cec_sense_topology as sense
import cec_source_literal_additions as literal
import cec_source_literal_retirement as retirement
import cec_source_retaining_ses_import as raw
from cec_native_items import discard_items


MAX_TRACKS = 16
MAX_LENGTH_NM = 24000000
SHARED_RECEIVERS = ['invariants', 'field', 'ground_returns', 'source_intake',
    'candidate_intake', 'parity', 'native', 'craft', 'source_live',
    'absolute_source_and_candidate_kelvin_contacts', 'full_original_parent_current']


def _deadline(seconds):
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not 0 < seconds <= 10.):
        raise ValueError('bounded_stationary_inward_relanding_lease_required')
    return time.monotonic() + float(seconds)


def _remaining(deadline):
    left = deadline - time.monotonic()
    if left <= 0:
        raise ValueError('stationary_inward_relanding_lease_exhausted')
    return min(10., left)


def plan(board, source, *, board_hint, pad_uuid, timeout_s=10.):
    """Derive retirement and terminal identity from the immutable saved Source."""
    deadline = _deadline(timeout_s)
    if (type(board_hint) is not str or not board_hint.strip()
            or type(pad_uuid) is not str or not pad_uuid):
        raise ValueError('actual_source_relanding_identity_required')
    source = Path(source).resolve(strict=True)
    before = leaf._binding(board)
    if before != leaf._binding(pcbnew.LoadBoard(str(source))):
        raise ValueError('unaltered_saved_Source_required_for_relanding_ownership')
    owned = leaf.plan(board, pad_uuid, timeout_s=_remaining(deadline))
    roots = [p for f in board.GetFootprints() for p in f.Pads() if force._uid(p) == pad_uuid]
    if len(roots) != 1:
        raise ValueError('unique_native_relanding_root_required')
    root = roots[0]
    contract = roles.footprint_contract(root.GetParentFootprint())
    selected = policy.input_contract(board, pad_uuid)
    if (not contract or root.GetParentFootprint().IsDNP()
            or contract['pins'].get(root.GetNumber()) != 'measurement'
            or selected['kind'] != 'shunt_kelvin_front_no_via'
            or selected['allow_layer_bridge'] is not False
            or selected['permitted_layers'] != [int(pcbnew.F_Cu)]
            or owned['layer'] != pcbnew.F_Cu
            or owned['points_nm'][0] != list(root.GetPosition())):
        raise ValueError('Source_direct_front_only_stationary_measurement_leaf_required')
    with force._thermal_hint(board_hint):
        domains = current.board_current_domains(board, board_hint)
    anchors = {ref for d in domains.values() if d.get('complete') is True
        for ref in d.get('authority_refs', ())}
    lineage = sense.board_evidence(board, anchor_pairs=(), anchor_refs=anchors)
    demands = []
    for proof in lineage['details']:
        _remaining(deadline)
        if proof['ref'] != root.GetParentFootprint().GetReference() or proof.get('ok') is not True:
            continue
        for segment in sense.placement_segments(proof):
            if (segment['start']['ref'] != proof['ref']
                    or segment['start']['pad'] != root.GetNumber()
                    or segment['net'] != root.GetNetname()):
                continue
            end = segment['end']
            fp = board.FindFootprintByReference(end['ref'])
            pads = [] if fp is None or fp.IsDNP() else [p for p in fp.Pads()
                if p.GetNumber() == end['pad'] and p.GetNetname() == segment['net']]
            if len(pads) != 1 or proof['selected'].get('kind') != 'direct':
                raise ValueError('unique_actual_Source_direct_shunt_target_required')
            target = pads[0]
            # This tier cannot jump to another same-net junction. The original
            # positively owned leaf must already contact this actual pad.
            if (force._uid(target) not in owned['boundary_uuids']
                    or target.HasHole() or target.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                    or list(target.GetLayerSet().CuStack()) != [pcbnew.F_Cu]
                    or domains.get(segment['net'], {}).get('complete') is not True):
                raise ValueError('Source_leaf_must_already_terminate_on_exact_rated_shunt_land')
            demands.append(dict(pad_uuid=pad_uuid, target_uuid=force._uid(target),
                net=segment['net'], a_nm=list(root.GetPosition()), b_nm=list(target.GetPosition()),
                source_layer_ids=[int(pcbnew.F_Cu)], target_layer_ids=[int(pcbnew.F_Cu)],
                owner_uuid=force._uid(root.GetParentFootprint()), input_pin=root.GetNumber(),
                manufacturer_source=contract['source'], source_topology=proof['selected'],
                source_segment=segment, current_capacity_qualified=False,
                kelvin_qualified=False, release_authority=False))
    if len(demands) != 1:
        raise ValueError('unique_Source_canonical_measurement_to_shunt_demand_required')
    basis = dimensions.nonload_measurement_width(board, source, owned['net'],
        parent_spec=fr._project_netclass_resolver(str(source))(owned['net']) or {})
    if owned['width_nm'] != basis['width_nm']:
        raise ValueError('full_existing_Source_nonload_measurement_width_required')
    if before != leaf._binding(board):
        raise ValueError('Source_relanding_scope_mutated')
    _remaining(deadline)
    return dict(scope='Source_owned_stationary_inward_shunt_leaf_relanding',
        complete=True, source=str(source), source_sha256=force._hash(source), board_hint=board_hint,
        source_native_binding=before, source_leaf=owned, demand=demands[0],
        layer_policy=selected, nonload_width_basis=basis, current_authority=False,
        placement_authority=False, routing_admitted=False, kelvin_qualified=False,
        release_authority=False, maximum_tracks=MAX_TRACKS, maximum_path_length_nm=MAX_LENGTH_NM)


def _projection(source, proposal, *, deadline):
    """Internal exact Source-minus-owned-leaf query, not an isolated Source proof."""
    if force._hash(source) != proposal['source_sha256']:
        raise ValueError('actual_immutable_relanding_Source_required')
    board = pcbnew.LoadBoard(str(source))
    if leaf._binding(board) != proposal['source_native_binding']:
        raise ValueError('exact_relanding_Source_native_epoch_required')
    selected = set(proposal['source_leaf']['track_uuids'])
    items = [t for t in board.GetTracks() if force._uid(t) in selected]
    if len(items) != len(selected):
        raise ValueError('complete_actual_Source_owned_leaf_required')
    discard_items(board, items)
    pads = {force._uid(p): p for f in board.GetFootprints() for p in f.Pads()}
    root = pads[proposal['demand']['pad_uuid']]
    graph = fr._read_only_route_connectivity(board)
    reached = {force._uid(i): i for i in [root, *graph.GetConnectedItems(root)]}
    model = roles.footprint_contract(root.GetParentFootprint())
    actual_island = access._input_island(root, list(reached.values()), model, deadline=deadline)
    if actual_island != [force._uid(root)]:
        raise ValueError('exact_Source_leaf_cut_must_leave_only_the_same_manufacturer_input')
    return board, dict(proposal['demand'], source_input_island_uuids=actual_island,
        preserved_source_prefix=False)


def _assess(source, proposal, points, *, deadline):
    board, demand = _projection(source, proposal, deadline=deadline)
    width = proposal['source_leaf']['width_nm']
    if (type(points) is not list or not 2 <= len(points) <= MAX_TRACKS+1
            or any(type(p) is not list or len(p) != 2 or any(type(v) is not int
                or abs(v) > 2000000000 for v in p) for p in points)
            or points[0] != demand['a_nm']
            or sum(math.dist(a, b) for a, b in zip(points, points[1:])) > MAX_LENGTH_NM):
        raise ValueError('bounded_actual_rooted_relanding_chain_required')
    guard = terminal.contact_guard(board, demand, width_nm=width, deadline=deadline)
    ops = [('trk', pcbnew.VECTOR2I(*a), pcbnew.VECTOR2I(*b), width, pcbnew.F_Cu)
        for a, b in zip(points, points[1:])]
    native_spec = fr._project_netclass_resolver(str(source))(demand['net']) or {}
    clearance = max(200000, int(board.GetDesignSettings().m_MinClearance),
        round(float(native_spec.get('clearance', 0.)) * 1e6))
    cache = {}
    legs = [dict(index=i, foreign=fr._tap_foreign_clear(board, op[1], op[2], width,
        pcbnew.F_Cu, clearance, {board.GetNetcodeFromNetname(demand['net'])}, foreign_cache=cache),
        edge=fr._edge_leg_clear(board, op[1], op[2], width/2+clearance))
        for i, op in enumerate(ops)]
    planar = [guard['planar'](tuple(op[1]), tuple(op[2]), width, int(op[4])) for op in ops]
    physical = guard['clear'](points) and guard['operations'](ops)
    craft = terminal.assess_path_craft(board, ops, net=demand['net'], deadline=deadline)
    field = terminal.assess_path_field(board, ops, net=demand['net'], deadline=deadline,
        netclass_resolver=fr._project_netclass_resolver(str(source), board=board),
        board_hint=proposal['board_hint'])
    stable = guard['unchanged']() and force._hash(source) == proposal['source_sha256']
    complete = time.monotonic() < deadline
    return dict(complete=complete, ok=complete and physical and stable
        and all(row['foreign'] and row['edge'] for row in legs)
        and craft.get('ok') is True and craft.get('complete') is True
        and field.get('ok') is True and field.get('complete') is True,
        exact_inward_pickup_and_no_other_same_net_contact=physical,
        native_legs=legs, native_planar_contacts=planar,
        craft=craft, field=field, source_projection_unchanged=stable,
        routing_admitted=False, release_authority=False, current_authority=False,
        no_fixed_boundary_waiver=True, existing_fixed_leaf_operation_unchanged=True)


def construct_private(source, candidate, *, board_hint, pad_uuid, points_nm, timeout_s=10.):
    """Validate proposed geometry with freshly rederived Source ownership."""
    deadline = _deadline(timeout_s)
    source, candidate = [Path(v).resolve(strict=True) for v in (source, candidate)]
    if (source == candidate or source.samefile(candidate)
            or force._hash(source) != force._hash(candidate)
            or force._sidecars(source) != force._sidecars(candidate)):
        raise ValueError('exact_distinct_private_relanding_Source_copy_required')
    code = force._code_identity()
    family = force._family(source, board_hint)
    proposal = plan(pcbnew.LoadBoard(str(source)), source, board_hint=board_hint,
        pad_uuid=pad_uuid, timeout_s=_remaining(deadline))
    assessment = _assess(source, proposal, points_nm, deadline=deadline)
    if assessment['ok'] is not True:
        raise ValueError('Source_inward_relanding_native_craft_or_field_refused')
    board, _ = _projection(source, proposal, deadline=deadline)
    added = leaf.add_path(board, proposal['source_leaf'], points_nm)
    fresh = leaf.plan(board, pad_uuid, timeout_s=_remaining(deadline))
    if (set(fresh['track_uuids']) != {force._uid(t) for t in added}
            or proposal['demand']['target_uuid'] not in fresh['boundary_uuids']):
        raise ValueError('complete_relanding_leaf_must_end_on_actual_Source_shunt_pad')
    source_text = raw.raw_text(source)
    with tempfile.TemporaryDirectory(prefix='cec-inward-leaf-producer-') as work:
        native = Path(work) / 'native.kicad_pcb'
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(native), board)
        assembled = literal.assemble(retirement.subtract(source_text,
            proposal['source_leaf']['track_uuids']), raw.raw_text(native))
    if family != force._family(source, board_hint) or code != force._code_identity():
        raise ValueError('relanding_Source_family_or_code_changed_before_save')
    _remaining(deadline)
    raw.write_raw(candidate, assembled)
    return dict(complete=True, source_scope=proposal, construction_assessment=assessment,
        candidate=str(candidate), candidate_sha256=force._hash(candidate),
        added_native_uuids=sorted(force._uid(t) for t in added),
        mandatory_shared_receiving=list(SHARED_RECEIVERS),
        saved_independent_receiving_required=True, routing_admitted=False,
        current_authority=False, kelvin_qualified=False, release_authority=False)


def receive(source, candidate, *, board_hint, pad_uuid, timeout_s=10.):
    """Rebuild scope and every saved track; never consume a producer receipt."""
    began = time.monotonic()
    result = dict(scope='saved_Source_owned_stationary_inward_shunt_relanding',
        ok=False, complete=False, errors=[], routing_admitted=False,
        current_authority=False, kelvin_qualified=False, release_authority=False,
        mandatory_shared_receiving=list(SHARED_RECEIVERS))
    try:
        deadline = _deadline(timeout_s)
        source, candidate = [Path(v).resolve(strict=True) for v in (source, candidate)]
        if source == candidate or source.samefile(candidate):
            raise ValueError('distinct_saved_relanding_endpoints_required')
        families = [force._family(p, board_hint) for p in (source, candidate)]
        code = force._code_identity()
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        proposal = plan(parent, source, board_hint=board_hint, pad_uuid=pad_uuid,
            timeout_s=_remaining(deadline))
        old = literal._inventory(raw.raw_text(source))[0]
        new = literal._inventory(raw.raw_text(candidate))[0]
        retired = set(proposal['source_leaf']['track_uuids'])
        if old.keys()-new.keys() != retired:
            raise ValueError('only_complete_Source_owned_thin_leaf_may_be_retired')
        if any(old[u][2] != new[u][2] for u in old.keys()-retired):
            raise ValueError('relanding_changed_opaque_Source_material_or_component')
        incoming = new.keys()-old.keys()
        tracks = [t for t in child.GetTracks() if force._uid(t) in incoming]
        if (not 1 <= len(incoming) <= MAX_TRACKS
                or {force._uid(t) for t in tracks} != incoming):
            raise ValueError('only_bounded_new_front_measurement_tracks_allowed')
        nets = literal.incoming_copper_nets(raw.raw_text(candidate), incoming)
        if set(nets.values()) != {proposal['demand']['net']}:
            raise ValueError('literal_relanding_net_differs_from_Source_measurement')
        ends = isolated._pads(child, dict(demand=proposal['demand']))
        ops = isolated._ordered_ops(tracks, *ends, width_nm=proposal['source_leaf']['width_nm'],
            deadline=deadline)
        points = [ops[0][1], *[op[2] for op in ops]]
        assessment = _assess(source, proposal, points, deadline=deadline)
        result['independent_saved_path_assessment'] = assessment
        if assessment['ok'] is not True:
            raise ValueError('saved_relanding_native_contact_craft_or_field_refused')
        replacement = leaf.plan(child, pad_uuid, timeout_s=_remaining(deadline))
        if (set(replacement['track_uuids']) != incoming
                or replacement['width_nm'] != proposal['source_leaf']['width_nm']
                or replacement['layer'] != proposal['source_leaf']['layer']
                or proposal['demand']['target_uuid'] not in replacement['boundary_uuids']):
            raise ValueError('saved_relanding_must_be_one_actual_leaf_to_same_shunt_pad')
        old_parts = ordinary._partition(parent, deadline, retired_uuids=retired)
        retained_keys = set().union(*old_parts)
        new_parts = ordinary._partition(child, deadline, retained_keys=retained_keys)
        if any(not any(part <= peer for peer in new_parts) for part in old_parts):
            raise ValueError('relanding_lost_original_terminal_or_surviving_conductor_partition')
        with tempfile.TemporaryDirectory(prefix='cec-inward-leaf-receiving-') as work:
            projected = force._copy_family(source, Path(work) / 'Source-minus-owned-leaf')
            board, _ = _projection(source, proposal, deadline=deadline)
            result['independent_exact_owned_cut'] = retirement.write_native_projection(
                source, projected, retired, board)
            replay = additive.receive(projected, candidate, timeout_s=_remaining(deadline))
            result['independent_saved_native_reconstruction'] = replay
            if replay.get('ok') is not True or replay.get('complete') is not True:
                raise ValueError('relanding_saved_native_reconstruction_refused')
        if (families != [force._family(p, board_hint) for p in (source, candidate)]
                or code != force._code_identity()):
            raise ValueError('relanding_saved_endpoints_or_code_changed')
        _remaining(deadline)
        result.update(ok=True, complete=True, source_scope=proposal, new_leaf=replacement,
            retired_track_uuids=sorted(retired), added_native_uuids=sorted(incoming),
            all_original_terminal_and_surviving_conductor_partitions_preserved=True,
            exact_force_copper_barrels_component_poses_and_rules_preserved=True,
            source=str(source), candidate=str(candidate), source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate), Source_families_and_code_unchanged=True,
            source_leaf_endpoint_may_change_only_with_actual_inward_shunt_pickup=True,
            open_reduction_certified=False)
    except Exception as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    result['elapsed_s'] = time.monotonic()-began
    return result
