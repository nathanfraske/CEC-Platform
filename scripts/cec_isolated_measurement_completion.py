"""Stationary, source-typed surface input completion, not force routing.

The existing manufacturer/schematic demand and ratified Kelvin policy select
the actual input and shunt land. No whole-net target, force-current credit,
layer escape, retirement or placement permission follows. Independently
received shared invariants, fields, returns, intakes, parity, native DRC,
trace craft and live epochs remain mandatory before private selection.
"""
import math
from pathlib import Path
import time


SHARED_RECEIVERS = ['invariants', 'field', 'ground_returns', 'source_intake',
    'candidate_intake', 'parity', 'native', 'craft', 'source_live']
MAX_TRACKS = 16
MAX_PATH_LENGTH_NM = 24000000
# Finite construction portfolios, not electrical length qualification. The
# short default remains byte-compatible at call sites. A longer detour must
# be explicitly requested AND independently received with the same tier;
# neither a producer proposal nor its saved geometry can select the tier.
PATH_LENGTH_WORK_TIERS_NM = (MAX_PATH_LENGTH_NM, 32000000)


def path_length_work_limit(value):
    if type(value) is not int or value not in PATH_LENGTH_WORK_TIERS_NM:
        raise ValueError('explicit_finite_measurement_path_work_tier_required')
    return value


def _budget(seconds, maximum):
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not 0 < seconds <= maximum):
        raise ValueError('bounded_isolated_measurement_work_lease_required')
    return float(seconds)


def plan(board, source, *, board_hint, pad_uuid, timeout_s=10.,
         path_length_budget_nm=MAX_PATH_LENGTH_NM):
    import pcbnew
    import cec_force_current as force
    import cec_cell_row_rebuild as binding
    import cec_measurement_terminal_access as access
    import cec_measurement_route_policy as policy
    import cec_route_dimensions as dimensions
    import cec_fr as fr
    if (type(board_hint) is not str or not board_hint
            or type(pad_uuid) is not str or not pad_uuid):
        raise ValueError('explicit_source_measurement_input_identity_required')
    started = time.monotonic()
    seconds = _budget(timeout_s, 10.)
    limit = path_length_work_limit(path_length_budget_nm)
    source = Path(source).resolve(strict=True)
    before = binding._source_binding(board)
    report = access.requests(board, board_hint=board_hint, timeout_s=seconds,
        allow_partial_inputs=True)
    result = dict(scope='source_typed_stationary_isolated_measurement_join',
        source=str(source), source_sha256=force._hash(source), board_hint=board_hint,
        pad_uuid=pad_uuid, source_requests=report, complete=False,
        retirement_authority=False, placement_authority=False, current_authority=False,
        kelvin_qualified=False, routing_admitted=False, release_authority=False,
        no_path_proof=False, construction_work_limits=dict(maximum_tracks=MAX_TRACKS,
            maximum_path_length_nm=limit, electrical_length_qualified=False))
    rows = [r for r in report['requests'] if r['pad_uuid'] == pad_uuid]
    if len(rows) != 1:
        result['reason'] = 'no_unique_source_stranded_measurement_input'
        return result
    demand = rows[0]
    selected = policy.input_contract(board, pad_uuid)
    if (selected['kind'] != 'shunt_kelvin_front_no_via'
            or selected['allow_layer_bridge'] is not False
            or selected['permitted_layers'] != [int(pcbnew.F_Cu)]
            or demand['source_layer_ids'] != [int(pcbnew.F_Cu)]
            or int(pcbnew.F_Cu) not in demand['target_layer_ids']
            or demand['source_topology'].get('kind') != 'direct'):
        result['reason'] = 'ratified_direct_front_only_shunt_input_required'
        return result
    # Reuse the established isolated-measurement branch floor, not a whole
    # force-net ampacity width. Its positively typed nonload input role is
    # mandatory. No guessed input current or trunk-capacity credit exists.
    basis=dimensions.nonload_measurement_width(board,source,demand['net'],
        parent_spec=fr._project_netclass_resolver(str(source))(demand['net']) or {})
    width = basis['width_nm']
    if not 0 < width <= 350000:
        result['reason'] = 'bounded_existing_measurement_branch_width_required'
        return result
    if before != binding._source_binding(board) or time.monotonic()-started >= seconds:
        raise ValueError('measurement_source_inventory_changed_or_lease_exhausted')
    result.update(complete=True, request=dict(demand=demand, width_nm=width,nonload_width_basis=basis,
        layer_policy=selected), source_native_binding=before)
    return result


def _pads(board, request):
    import cec_force_current as force
    demand = request['demand']
    rows = [p for f in board.GetFootprints() for p in f.Pads()]
    pads = {force._uid(p): p for p in rows}
    if len(pads) != len(rows):
        raise ValueError('unique_native_measurement_terminal_inventory_required')
    ends = [pads.get(demand[k]) for k in ('pad_uuid', 'target_uuid')]
    if any(p is None or p.GetNetname() != demand['net'] for p in ends):
        raise ValueError('actual_measurement_input_and_shunt_lands_required')
    return ends


def construct_private(source, candidate, proposal, *, board_hint, timeout_s=20.,
                      path_length_budget_nm=MAX_PATH_LENGTH_NM):
    import pcbnew
    import cec_force_current as force
    import cec_measurement_terminal_route as terminal
    import cec_cell_escape_replan as escape
    import cec_additive_pair_repair as additive
    started = time.monotonic()
    deadline = started + _budget(timeout_s, 20.)
    limit = path_length_work_limit(path_length_budget_nm)
    source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
    if source == candidate or force._hash(source) != force._hash(candidate):
        raise ValueError('exact_private_measurement_source_copy_required')
    board = pcbnew.LoadBoard(str(source))
    fresh = plan(board, source, board_hint=board_hint, pad_uuid=proposal['pad_uuid'],
        timeout_s=min(10., max(.001, deadline-time.monotonic())),path_length_budget_nm=limit)
    if not fresh['complete']:
        raise ValueError('fresh_source_measurement_input_refused')
    request = fresh['request']
    result = dict(complete=False, request=request, routing_admitted=False,
        construction_work_limits=fresh['construction_work_limits'],
        current_authority=False, kelvin_qualified=False, release_authority=False)
    remaining = deadline-time.monotonic()
    if remaining <= 3.:
        result['reason'] = 'construction_lease_exhausted_before_surface_search'
        return result
    menu = terminal.menus(board, request['demand'], width_nm=request['width_nm'],
        timeout_s=min(10., remaining-3.), max_choices=8,max_length_nm=limit,
        board_hint=board_hint)
    result['surface_menu'] = menu
    if not menu['ops']:
        result['reason'] = 'finite_front_surface_menu_incomplete'
        result['elapsed_s'] = time.monotonic()-started
        return result
    if time.monotonic() >= deadline-2.:
        result['reason'] = 'construction_lease_exhausted_before_native_save'
        return result
    # Recheck the emitted operations, never accept caller-authored geometry.
    # Search is geometry-only and can return a long detour. Do not save a
    # candidate already outside this operator's independent receiving scope.
    # Keep the SAME bounded portfolio and try its other lawful paths first.
    choices = [ops for ops in menu['ops'] if 1 <= len(ops) <= MAX_TRACKS
        and all(op[0] == 'trk' for op in ops)
        and sum(math.dist(op[1], op[2]) for op in ops) <= limit]
    if not choices:
        result['reason'] = 'finite_surface_menu_outside_saved_path_scope'
        result['elapsed_s'] = time.monotonic()-started
        return result
    ops = choices[0]
    guard = terminal.contact_guard(board, request['demand'], width_nm=request['width_nm'],
        deadline=deadline)
    if not guard['operations'](ops):
        raise ValueError('fresh_measurement_operations_lost_source_pickup_scope')
    old = {force._uid(t) for t in board.GetTracks()}
    escape._native_ops(board, ops, request['demand']['net'])
    result['save'] = {}
    additive.save_native_additions(candidate, board, result['save'], old, board_hint=board_hint)
    result.update(complete=time.monotonic() < deadline, elapsed_s=time.monotonic()-started,
        candidate_sha256=force._hash(candidate), ops=ops)
    return result


def _ordered_ops(items, root, target, *, width_nm, deadline,
                 path_length_budget_nm=MAX_PATH_LENGTH_NM):
    """All incoming copper must be ONE bounded simple physical input path."""
    import pcbnew
    limit = path_length_work_limit(path_length_budget_nm)
    if not 1 <= len(items) <= MAX_TRACKS:
        raise ValueError('bounded_new_measurement_track_chain_required')
    adjacency = {}
    for item in items:
        if time.monotonic() >= deadline:
            raise ValueError('measurement_saved_path_lease_exhausted')
        if (item.GetClass() != 'PCB_TRACK' or item.GetLayer() != pcbnew.F_Cu
                or item.GetWidth() != width_nm or item.GetNetname() != root.GetNetname()
                or item.HasSolderMask() or item.GetParentGroup() is not None):
            raise ValueError('measurement_path_must_retain_surface_role_width_and_net')
        a, b = tuple(item.GetStart()), tuple(item.GetEnd())
        if (a == b or a[0] != b[0] and a[1] != b[1]
                and abs(a[0]-b[0]) != abs(a[1]-b[1])):
            raise ValueError('canonical_nonempty_measurement_path_required')
        for point in (a, b):
            adjacency.setdefault(point, []).append((item, b if point == a else a))
    start = tuple(root.GetPosition())
    if (len(adjacency) != len(items)+1 or start not in adjacency
            or len(adjacency[start]) != 1
            or sum(len(rows) == 1 for rows in adjacency.values()) != 2
            or any(len(rows) > 2 for rows in adjacency.values())):
        raise ValueError('one_rooted_nonbranching_measurement_path_required')
    current = start
    visited = set()
    ops = []
    while len(visited) < len(items):
        choices = [(item, peer) for item, peer in adjacency[current] if id(item) not in visited]
        if len(choices) != 1:
            raise ValueError('disconnected_or_cyclic_measurement_path')
        item, peer = choices[0]
        visited.add(id(item))
        ops.append(['trk', list(current), list(peer), width_nm, int(pcbnew.F_Cu)])
        current = peer
    if (not target.GetEffectiveShape(pcbnew.F_Cu).Collide(pcbnew.VECTOR2I(*current), 0)
            or sum(math.dist(op[1], op[2]) for op in ops) > limit):
        raise ValueError('bounded_measurement_path_must_end_in_actual_shunt_land')
    return ops


def receive(source, candidate, *, board_hint, pad_uuid, timeout_s=10.,
            path_length_budget_nm=MAX_PATH_LENGTH_NM):
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_additive_route_receiving as additive
    import cec_source_literal_additions as literal
    import cec_measurement_terminal_route as terminal
    started = time.monotonic()
    deadline = started + _budget(timeout_s, 10.)
    result = dict(scope='source_typed_isolated_measurement_saved_native_join',
        ok=False, complete=False, errors=[], mandatory_shared_receiving=list(SHARED_RECEIVERS),
        routing_admitted=False, current_authority=False, kelvin_qualified=False,
        retirement_authority=False, placement_authority=False, release_authority=False)
    try:
        limit = path_length_work_limit(path_length_budget_nm)
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        if source == candidate:
            raise ValueError('distinct_measurement_source_and_candidate_required')
        code = force._code_identity()
        families = [force._family(p, board_hint) for p in (source, candidate)]
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        fresh = plan(parent, source, board_hint=board_hint, pad_uuid=pad_uuid,
            timeout_s=min(10., max(.001, deadline-time.monotonic())),path_length_budget_nm=limit)
        result['independently_compiled_source_scope'] = fresh
        if not fresh['complete']:
            raise ValueError('saved_measurement_source_scope_unavailable')
        request = fresh['request']
        old_ends, new_ends = [_pads(b, request) for b in (parent, child)]
        for a, b in zip(old_ends, new_ends):
            if (force._item_key(a) != force._item_key(b)
                    or a.GetNetname() != b.GetNetname() or a.GetShape() != b.GetShape()
                    or tuple(a.GetSize()) != tuple(b.GetSize())
                    or a.GetAttribute() != b.GetAttribute()
                    or a.GetOrientationDegrees() != b.GetOrientationDegrees()
                    or tuple(a.GetLayerSet().CuStack()) != tuple(b.GetLayerSet().CuStack())
                    or a.GetParentFootprint().GetValue() != b.GetParentFootprint().GetValue()
                    or a.GetParentFootprint().GetFPIDAsString() != b.GetParentFootprint().GetFPIDAsString()):
                raise ValueError('measurement_input_or_shunt_identity_geometry_changed')
        _, before = additive._nodes(source)
        _, after = additive._nodes(candidate)
        if before.keys()-after.keys():
            raise ValueError('measurement_addition_retired_original_source_material')
        incoming = after.keys()-before.keys()
        tracks = [t for t in child.GetTracks() if force._uid(t) in incoming]
        if {force._uid(t) for t in tracks} != incoming:
            raise ValueError('only_bounded_measurement_track_additions_allowed')
        saved_nets = literal.incoming_copper_nets(candidate.read_text(), set(incoming))
        if any(name != request['demand']['net'] for name in saved_nets.values()):
            raise ValueError('literal_saved_measurement_net_differs_from_native_input')
        ops = _ordered_ops(tracks, *new_ends, width_nm=request['width_nm'], deadline=deadline,
            path_length_budget_nm=limit)
        guard = terminal.contact_guard(parent, request['demand'], width_nm=request['width_nm'],
            deadline=deadline)
        if not guard['operations'](ops) or not guard['unchanged']():
            raise ValueError('measurement_path_acquires_unowned_same_net_force_contact')
        craft=terminal.assess_path_craft(parent,ops,net=request['demand']['net'],deadline=deadline)
        result['complete_saved_path_craft']=craft
        if not(craft.get('ok')is True and craft.get('complete')is True
                and craft.get('board_mutated')is False):
            raise ValueError('saved_measurement_chain_or_pickup_tail_loses_route_craft')
        graph = fr._read_only_route_connectivity(child)
        reached = {force._uid(new_ends[0]),
            *[force._uid(i) for i in graph.GetConnectedItems(new_ends[0])]}
        if force._uid(new_ends[1]) not in reached or not incoming <= reached:
            raise ValueError('saved_measurement_path_is_not_one_actual_native_join')
        net = request['demand']['net']
        counts = [fr.net_connectivity_component_count(b, b.GetNetcodeFromNetname(net))
            for b in (parent, child)]
        if counts[1] >= counts[0]:
            raise ValueError('measurement_native_component_count_not_reduced')
        if (families != [force._family(p, board_hint) for p in (source, candidate)]
                or code != force._code_identity() or time.monotonic() >= deadline):
            raise ValueError('measurement_source_candidate_code_or_lease_changed')
        result.update(ok=True, complete=True, source_components=counts[0],
            candidate_components=counts[1], added_native_uuids=sorted(incoming),
            construction_work_limits=fresh['construction_work_limits'],
            exact_source_pickup_aperture_preserved=True, whole_shared_stage_still_required=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s'] = round(time.monotonic()-started, 6)
    return result
