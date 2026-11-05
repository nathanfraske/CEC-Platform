"""Explicit zero-cut, full-class physical joins on distributed supplies.

The existing all-terminal aggregate contract is the authority, not a new
source/sink model.  Each saved addition is one path between two old islands.
Every trace retains the whole aggregate/class floor; every new through via
owes its actual contacts, local web and unchanged process/clearance checks.
Neither this operation nor those web checks qualify barrel ampacity.  The
existing planar/force capacity graphs remain unchanged, and all enclosing
current, return, field, Kelvin, native and intake gates remain mandatory.
"""
from pathlib import Path
import json
import math
import time


def _need(value, reason):
    if not value:
        raise ValueError(reason)


def _deadline(seconds):
    _need(type(seconds) in (int, float) and math.isfinite(seconds)
          and 0 < seconds <= 10., 'bounded_distributed_layer_join_lease_required')
    return time.monotonic() + seconds


def _remaining(deadline):
    value = deadline - time.monotonic()
    _need(value > 0, 'distributed_layer_join_deadline')
    return min(10., value)


def _ids(values):
    _need(type(values) in (list, tuple) and len(values) == 2
          and all(type(v) is str and v for v in values)
          and values[0] != values[1], 'two_exact_distributed_source_lands_required')
    return sorted(values)


def plan(board, source, *, board_hint, net, pad_uuids, timeout_s=10.):
    """Fresh existing load and canonical supply/capacitor terminal authority.

    This deliberately excludes address/enable aliases, THTs, zone-owned nets
    and complete force domains.  A caller supplies identities, never roles,
    coordinates, current, width, layers or barrel permissions.
    """
    import pcbnew
    import cec_force_current as force
    import cec_cell_row_rebuild as cells
    import cec_distributed_supply as supply
    import cec_distributed_supply_prefix as prefixes
    deadline = _deadline(timeout_s)
    selected = _ids(pad_uuids)
    _need(type(board_hint) is str and bool(board_hint)
          and type(net) is str and bool(net), 'explicit_distributed_source_context_required')
    source = Path(source).resolve(strict=True)
    digest = force._hash(source)
    binding = cells._source_binding(board)
    result = dict(scope='source_distributed_full_class_physical_layer_join',
        complete=False, source=str(source), source_sha256=digest,
        source_binding=binding, board_hint=board_hint, net=net, pad_uuids=selected,
        current_authority_changed=False, current_qualified=False,
        plated_barrel_current_qualified=False, release_authority=False,
        no_path_proof=False)
    report = supply.audit(board, board_hint=board_hint, include_nets=[net])
    if set(report['contracts']) != {net}:
        return dict(result, reason='existing_distributed_aggregate_contract_required',
                    refusals=report.get('refusals', {}))
    graph = report['nets'][net]
    if (graph['unsupported_terminal_uuids'] or graph['single_surface_layer_id'] is not None
            or any(z.GetNetname() == net and not z.GetIsRuleArea() for z in board.Zones())):
        return dict(result, reason='surface_only_nonzone_distributed_supply_required')
    pads = {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads()
            if p.GetNetname() == net}
    _need(set(selected) <= pads.keys(), 'actual_distributed_source_lands_required')
    _need(all(pads[u].GetAttribute() == pcbnew.PAD_ATTRIB_SMD and not pads[u].HasHole()
              and len(pads[u].GetLayerSet().CuStack()) == 1 for u in selected),
          'single_face_distributed_source_lands_required')
    islands = graph['native_components']
    indices = [next(i for i, part in enumerate(islands) if u in part) for u in selected]
    if indices[0] == indices[1]:
        return dict(result, reason='selected_distributed_lands_already_joined')
    context = prefixes.prepare(board, report['contracts'], board_hint=board_hint,
                               timeout_s=_remaining(deadline))
    if net not in context['contracts'] or not set(selected) <= context['pads'].keys():
        return dict(result, reason='canonical_supply_or_shunt_terminal_required')
    _need(all(context['pads'][u]['net'] == net and context['pads'][u]['role'] in
              ('manufacturer_supply_pin', 'value_qualified_grounded_ceramic_supply_terminal')
              for u in selected),
          'positive_canonical_distributed_endpoint_role_required')
    _need(force._hash(source) == digest and cells._source_binding(board) == binding,
          'distributed_layer_source_changed_during_compilation')
    _remaining(deadline)
    return dict(result, complete=True, contract=report['contracts'][net],
        source_native_components=islands,
        source_planar_full_width_components=graph['planar_full_width_components'],
        source_terminal_records={u: context['pads'][u] for u in selected},
        source_authority=context['source_bindings'])


def _source_pads(board, proposal):
    import cec_force_current as force
    pads = {force._uid(p): p for fp in board.GetFootprints() for p in fp.Pads()}
    return [pads[u] for u in proposal['pad_uuids']]


def _widths(board, contract):
    import cec_fab_profile as fab
    planes = set(__import__('cec_fr').plane_layers(board))
    result = {int(board.GetLayerID(name)): math.ceil(contract['required_by_layer_mm'][name]*1e6)
              for name in contract['routing_layers'] if name not in planes}
    _need(2 <= len(result) <= 6 and all(l in board.GetEnabledLayers().CuStack()
          and fab.COPPER_LAYER_IDS[l] in contract['routing_layers'] and w > 0
          for l, w in result.items()), 'complete_distributed_source_routing_faces_required')
    return result


def _source_via_limits(board):
    """Ordinary native plus exact saved project floors, never route defaults.

    Loading geometry need not consume the saved project's settings. A higher
    exact companion floor is therefore retained independently; it may never
    lower a native limit. This does not create a local POFV exception.
    """
    import cec_route_dimensions as dimensions
    limits = dimensions.board_limits(board)
    project = Path(board.GetFileName()).with_suffix('.kicad_pro')
    if project.is_file():
        _need(project.stat().st_size <= 4*1024*1024,
              'bounded_distributed_exact_via_project_required')
        rules = json.loads(project.read_text()).get('board', {}).get(
            'design_settings', {}).get('rules', {})
        _need(type(rules) is dict, 'literal_distributed_exact_via_rules_required')
        for key, name in (('via_diameter', 'min_via_diameter'),
                          ('via_drill', 'min_through_hole_diameter'),
                          ('annular', 'min_via_annular_width')):
            if name not in rules:
                continue
            value = rules[name]
            _need(type(value) in (int, float) and math.isfinite(value)
                  and 0 <= value <= 10., 'finite_distributed_source_via_floor_required')
            limits[key] = max(limits[key], value)
    return limits


def _via_geometry(board, contract, *, source_minimum=False):
    import cec_fab_profile as fab
    import cec_fr as fr
    import cec_route_dimensions as dimensions
    _need(type(source_minimum) is bool, 'explicit_distributed_via_geometry_mode_required')
    if source_minimum:
        # The distinct physical-frontier tier may offer an ordinary process
        # minimum. Preferred interactive geometry is not a fabrication floor.
        # Source custom rules, holes, native DRC, actual contacts and the FULL
        # unchanged current/class web remain independently mandatory.
        diameter, drill = dimensions.ordinary_via_geometry({}, _source_via_limits(board))
    else:
        spec = fr._project_netclass_resolver(str(board.GetFileName()))(contract['net']) or {}
        diameter, drill, _ = fab.board_legal_through_via_geometry(board,
            float(spec.get('via_diameter') or 0), float(spec.get('via_drill') or 0))
    # The entire aggregate/class web, never I/N or a tiny terminal allocation.
    drill_nm = math.ceil(drill*1e6)
    diameter_nm = max(math.ceil(diameter*1e6),
                     drill_nm + max(_widths(board, contract).values()))
    return diameter_nm/1e6, drill_nm/1e6


def _drill_spacing(parent, child, incoming, deadline):
    """Check new holes against each other AND every actual retained hole.

    Loading PCB geometry is not a guarantee that KiCad's in-process cached
    settings have consumed a freshly saved project rule. Read the exact
    companion too; never use that observation to reduce a native floor.
    Drill shapes stay native, including oblong PTH/NPTH pads.
    """
    import pcbnew
    import cec_force_current as force
    import cec_route_dimensions as dimensions
    gap = int(parent.GetDesignSettings().m_HoleToHoleMin)
    project = dimensions.project_path(parent.GetFileName())
    if project is not None:
        _need(project.stat().st_size <= 4*1024*1024, 'bounded_distributed_project_rules_required')
        rules = json.loads(project.read_text()).get('board', {}).get('design_settings', {}).get('rules', {})
        value = rules.get('min_hole_to_hole')
        if value is not None:
            _need(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10.,
                  'finite_source_hole_spacing_rule_required')
            gap = max(gap, math.ceil(value*1e6))
    _need(gap >= 0, 'nonnegative_distributed_hole_spacing_required')
    holes = [v for v in child.GetTracks() if v.GetClass() == 'PCB_VIA']
    holes += [p for fp in child.GetFootprints() for p in fp.Pads() if p.HasHole()]
    _need(len(holes) <= 4096, 'bounded_distributed_native_hole_inventory_required')
    checked = 0
    for via in incoming:
        if via.GetClass() != 'PCB_VIA':
            continue
        shape = pcbnew.SHAPE_SEGMENT(via.GetPosition(), via.GetPosition(), int(via.GetDrillValue()))
        for other in holes:
            _remaining(deadline)
            if force._uid(other) == force._uid(via):
                continue
            target = (pcbnew.SHAPE_SEGMENT(other.GetPosition(), other.GetPosition(),
                int(other.GetDrillValue())) if other.GetClass() == 'PCB_VIA'
                else other.GetEffectiveHoleShape())
            _need(target is not None and not target.Collide(shape, gap),
                  'saved_distributed_hole_spacing_required')
            checked += 1
    return dict(complete=True, source_minimum_hole_gap_nm=gap,
        new_against_old_and_new_holes_checked=checked, native_slotted_holes_retained=True,
        no_source_process_floor_reduced=True)


def plan_native_frontier(board, source, *, board_hint, net, pad_uuids, timeout_s=10.):
    """Distinct physical-island access; the legacy capacity graph is intact.

    Both selected terminals retain the original canonical Source compiler.
    An unchanged through barrel may establish ORIGINAL physical membership
    of a full-class track frontier. It is never offered as a new transition,
    sized as a new barrel, or credited with current/thermal capacity. Every
    newly added track and barrel still owes the whole unchanged contract.
    """
    result = plan(board, source, board_hint=board_hint, net=net,
                  pad_uuids=pad_uuids, timeout_s=timeout_s)
    return dict(result, scope='source_distributed_full_class_original_native_frontier_join',
        source_access_mode='original_native_islands_full_class_track_frontiers',
        original_barrels_used_for_physical_membership_only=True,
        old_barrel_capacity_credited=False, existing_planar_current_graph_unchanged=True)


def _ports(board, proposal, deadline, *, native_frontier=False):
    """Actual full-class track access, with an explicit physical-only tier.

    The default graph is unchanged and never traverses a barrel. The distinct
    tier adds only actual original, positive full-depth THROUGH barrels to
    membership; it still excludes every thin track and never offers a barrel
    as a port. No inferred same-number or pad-internal connectivity is used.
    """
    import cec_force_current as force
    import cec_distributed_supply as supply
    import pcbnew
    _need(type(native_frontier) is bool, 'explicit_native_frontier_mode_required')
    contract = proposal['contract']; widths = _widths(board, contract)
    pads = [p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname() == proposal['net']]
    tracks = [t for t in board.GetTracks() if t.GetNetname() == proposal['net']
        and t.GetClass() == 'PCB_TRACK' and t.GetLayer() in widths
        and t.GetWidth() >= widths[t.GetLayer()]]
    _need(len(pads)+len(tracks) <= 4096, 'bounded_distributed_source_ports_required')
    original_barrels = []
    if native_frontier:
        enabled = tuple(map(int, board.GetEnabledLayers().CuStack()))
        for item in board.GetTracks():
            _remaining(deadline)
            if item.GetNetname() != proposal['net'] or item.GetClass() != 'PCB_VIA':
                continue
            if (item.GetViaType() == pcbnew.VIATYPE_THROUGH
                    and item.TopLayer() == pcbnew.F_Cu and item.BottomLayer() == pcbnew.B_Cu
                    and item.GetDrillValue() > 0
                    and all(item.IsOnLayer(l) and item.GetWidth(l) > item.GetDrillValue()
                            for l in enabled)):
                original_barrels.append(item)
        _need(len(original_barrels) <= 4096, 'bounded_original_native_barrel_inventory_required')
    graph = supply._connectivity([*pads, *tracks, *original_barrels])
    originals = {force._uid(i): i for i in [*pads, *tracks]}
    roots = _source_pads(board, proposal); menus = []
    for root, peer in ((roots[0], roots[1]), (roots[1], roots[0])):
        _remaining(deadline)
        reached = {force._uid(root)} | {force._uid(i) for i in graph.GetConnectedItems(root)}
        anchors = [dict(kind='pad_center', uuid=force._uid(root),
            point_nm=list(root.GetPosition()), layer=int(next(iter(root.GetLayerSet().CuStack()))))]
        for t in tracks:
            if force._uid(t) not in reached:
                continue
            a, b = t.GetStart(), t.GetEnd()
            for point in sorted({tuple(a), tuple(b), ((a.x+b.x)//2, (a.y+b.y)//2)}):
                anchors.append(dict(kind='rated_track', uuid=force._uid(t),
                    point_nm=list(point), layer=int(t.GetLayer())))
        seen = set(); retained = []
        for anchor in sorted(anchors, key=lambda a: (
                a['kind'] != 'pad_center', math.dist(a['point_nm'], tuple(peer.GetPosition())),
                a['layer'], a['point_nm'], a['uuid'])):
            _remaining(deadline)
            key = (anchor['layer'], *anchor['point_nm'])
            if key not in seen and supply._anchor_contact(board, anchor, contract,
                                                          items=originals).get('ok') is True:
                seen.add(key); retained.append(anchor)
            if len(retained) >= 24:
                break
        menus.append(retained)
    return menus


def _ordered_chain(board, incoming, pads, contract, deadline, endpoint_ports=None):
    """Exact endpoint graph plus native non-neighbor contact checks.

    Vias collapse only their actual XY at authorized track faces.  No old
    barrel, pad-internal metal or zone is borrowed as a new chain edge.
    """
    import pcbnew
    import cec_force_current as force
    import cec_pad_surface_access as surface
    _need(1 <= len(incoming) <= 128, 'bounded_distributed_new_chain_required')
    vias = [i for i in incoming if i.GetClass() == 'PCB_VIA']
    _need(1 <= len(vias) <= 4, 'explicit_new_distributed_layer_transition_required')
    at_via = {tuple(v.GetPosition()): v for v in vias}
    _need(len(at_via) == len(vias), 'unique_distributed_barrel_axes_required')
    widths = _widths(board, contract)
    adjacency = {}; by_id = {}; edges = {}
    def node(point, layer):
        return ('via', *point) if point in at_via else (layer, *point)
    for item in incoming:
        _remaining(deadline)
        uid = force._uid(item)
        _need(uid not in by_id and item.GetNetname() == contract['net']
              and item.GetParentGroup() is None, 'exact_unowned_distributed_chain_material_required')
        by_id[uid] = item
        if item.GetClass() == 'PCB_VIA':
            continue
        _need(item.GetClass() == 'PCB_TRACK' and not item.HasSolderMask()
              and item.GetLayer() in widths and item.GetWidth() >= widths[item.GetLayer()],
              'complete_aggregate_class_width_on_actual_face_required')
        a, b = tuple(item.GetStart()), tuple(item.GetEnd())
        _need(a != b and (a[0] == b[0] or a[1] == b[1]
              or abs(a[0]-b[0]) == abs(a[1]-b[1])), 'canonical_distributed_chain_edges_required')
        first, last = node(a, item.GetLayer()), node(b, item.GetLayer())
        _need(first != last, 'nonempty_distributed_chain_edge_required')
        edges[uid] = (first, last)
        for here, peer in ((first, last), (last, first)):
            adjacency.setdefault(here, []).append((uid, peer))
    ends = [p for p, neighbors in adjacency.items() if len(neighbors) == 1]
    _need(len(ends) == 2 and all(len(v) in (1, 2) for v in adjacency.values())
          and len(adjacency) == len(edges)+1 and all(('via', *p) in adjacency for p in at_via),
          'one_nonbranching_distributed_layer_chain_required')
    here = ends[0]; visited = set(); ordered = []
    while len(visited) < len(edges):
        _remaining(deadline)
        choices = [(uid, peer) for uid, peer in adjacency[here] if uid not in visited]
        _need(len(choices) == 1, 'disconnected_or_cyclic_distributed_chain')
        uid, peer = choices[0]; visited.add(uid); ordered.append(uid); here = peer
    _need(here == ends[1], 'complete_distributed_chain_required')
    # A drawn crossing/overshoot is not made legal by an endpoint-only graph.
    positions = {uid: i for i, uid in enumerate(ordered)}
    tracks = [by_id[u] for u in ordered]
    for i, a in enumerate(tracks):
        for b in tracks[i+1:]:
            _remaining(deadline)
            if a.GetLayer() == b.GetLayer() and abs(positions[force._uid(a)]-positions[force._uid(b)]) > 1:
                _need(not a.GetEffectiveShape(a.GetLayer()).Collide(b.GetEffectiveShape(b.GetLayer()), 0),
                      'disjoint_nonneighbor_distributed_chain_required')
    for via in vias:
        via_node = ('via', *tuple(via.GetPosition()))
        incident = {uid for uid, _ in adjacency[via_node]}
        for track in tracks:
            _remaining(deadline)
            if force._uid(track) not in incident:
                _need(not via.GetEffectiveShape(track.GetLayer()).Collide(
                    track.GetEffectiveShape(track.GetLayer()), 0), 'no_distributed_barrel_midpath_pickup')
    def endpoint_contact(end, pad, menu):
        point = list(end[1:]); face = next(iter(pad.GetLayerSet().CuStack()))
        if menu is not None:
            return any(point == port['point_nm'] and end[0] in ('via', port['layer']) for port in menu)
        if end[0] != 'via' and end[0] != face:
            return False
        return surface.contact(pad, face, point, contact_inset_nm=50000).get('ok') is True
    menus = endpoint_ports if endpoint_ports is not None else [None, None]
    _need((endpoint_contact(ends[0], pads[0], menus[0]) and endpoint_contact(ends[1], pads[1], menus[1]))
          or (endpoint_contact(ends[0], pads[1], menus[1]) and endpoint_contact(ends[1], pads[0], menus[0])),
          'both_actual_source_land_contacts_required')
    _need(sum(t.GetLength() for t in tracks) <= 128000000,
          'bounded_distributed_chain_length_required')
    return dict(complete=True, track_uuids=ordered, via_uuids=sorted(force._uid(v) for v in vias),
        endpoints=[list(p) for p in ends], no_branches_cycles_spurs_or_crossings=True,
        barrel_ampacity_qualified=False, release_authority=False)


def _source_contacts(parent, incoming, chain, deadline):
    """No middle-of-path pickup, even of another member of an end island.

    A pad-only partition count cannot detect such a redundant Source loop.
    Every old copper contact must belong to an end-incident new object and
    contain that actual end point. Source islands remain geometry, not ratings.
    """
    import pcbnew
    import cec_force_current as force
    net = incoming[0].GetNetname()
    old = [p for f in parent.GetFootprints() for p in f.Pads() if p.GetNetname() == net]
    old += [t for t in parent.GetTracks() if t.GetNetname() == net]
    _need(len(old) <= 4096, 'bounded_distributed_source_contact_inventory_required')
    ends = chain['endpoints']; rows = []
    for item in incoming:
        _remaining(deadline)
        faces = list(item.GetLayerSet().CuStack())
        if item.GetClass() == 'PCB_TRACK':
            at = {tuple(item.GetStart()), tuple(item.GetEnd())}
        else:
            at = {tuple(item.GetPosition())}
        incident = [end for end in ends if tuple(end[1:]) in at
                    and (end[0] == 'via' or end[0] in faces)]
        for original in old:
            for face in faces:
                _remaining(deadline)
                if not original.IsOnLayer(face):
                    continue
                shape = original.GetEffectiveShape(face)
                if not shape.Collide(item.GetEffectiveShape(face), 0):
                    continue
                _need(any((end[0] == 'via' or end[0] == face)
                    and shape.Collide(pcbnew.VECTOR2I(*end[1:]), 0) for end in incident),
                    'distributed_chain_middle_or_unowned_source_pickup')
                rows.append(dict(incoming_uuid=force._uid(item), source_uuid=force._uid(original),
                                 face=int(face)))
    return dict(complete=True, contacts=rows, end_contacts_only=True,
                no_source_parallel_loop_inferred=True, release_authority=False)


def construct_private(source, candidate, proposal, *, board_hint, timeout_s=10.):
    """Bounded native 3D search; a construction is never admission."""
    import pcbnew
    import cec_force_current as force
    import cec_distributed_supply_stage as planar
    import cec_additive_pair_repair as save
    import cec_fr as fr
    import cec_native_current_capture as capture
    from cec_route_proposal_guard import RouteProposalGuard
    from cec_field_search import PlanarSearchGuard
    deadline = _deadline(timeout_s)
    source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
    _need(source != candidate and force._hash(source) == force._hash(candidate),
          'exact_private_distributed_layer_source_copy_required')
    _need(force._sidecars(source) == force._sidecars(candidate),
          'exact_private_distributed_layer_companions_required')
    epoch = force._code_identity(); family = force._family(source, board_hint)
    board = pcbnew.LoadBoard(str(source))
    fresh = plan(board, source, board_hint=board_hint, net=proposal['net'],
        pad_uuids=proposal['pad_uuids'], timeout_s=_remaining(deadline))
    _need(fresh.get('complete') is True
          and planar._replay_identity(fresh) == planar._replay_identity(proposal),
          'fresh_exact_distributed_layer_scope_required')
    pads = _source_pads(board, fresh); contract = fresh['contract']; widths = _widths(board, contract)
    diameter, drill = _via_geometry(board, contract)
    code = board.GetNetcodeFromNetname(fresh['net'])
    search_deadline = deadline-2.
    _need(search_deadline > time.monotonic(), 'distributed_layer_finishing_reserve_required')
    capture_guard = capture.Guard(board, source, net=fresh['net'], board_hint=board_hint,
                                  timeout_s=min(2., _remaining(deadline)))
    _need(capture_guard.complete is True and capture_guard.unclassified_owners == 0
          and all(capture_guard.allows_endpoint({'native_uuids': [force._uid(p)]}) for p in pads),
          'complete_distributed_source_control_reservations_required')
    resolver = fr._project_netclass_resolver(str(source))
    preflight = RouteProposalGuard(board, fresh['net'], board_path=str(source),
        netclass_resolver=resolver, deadline=search_deadline, board_hint=board_hint)
    field_guard = PlanarSearchGuard(board, fresh['net'], netclass_resolver=resolver)
    if getattr(field_guard, 'active', True) is False:
        field_guard = None
    old = {force._uid(t) for t in board.GetTracks()}
    attempts = []; operations = None; cache = {}
    menus = _ports(board, fresh, deadline)
    pairs = sorted(((a, b) for a in menus[0] for b in menus[1]), key=lambda pair: (
        math.dist(pair[0]['point_nm'], pair[1]['point_nm']), pair[0]['point_nm'], pair[1]['point_nm']))[:8]
    work = [(pair, reverse) for pair in pairs for reverse in (False, True)]
    for index, (pair, reverse) in enumerate(work):
        now = time.monotonic()
        if now >= search_deadline:
            break
        first, last = pair[::-1] if reverse else pair
        lease = min(search_deadline, now+max(.15, (search_deadline-now)/min(4, len(work)-index)))
        detail = {}
        operations = fr._multilayer_maze_lastmile_ops(board,
            pcbnew.VECTOR2I(*first['point_nm']), pcbnew.VECTOR2I(*last['point_nm']),
            code, sorted(widths), math.ceil(contract['clearance_mm']*1e6),
            lambda a, b, half: fr._edge_leg_clear(board, a, b, half),
            width_for_layer=lambda layer: widths.get(layer), drill=drill, dia=diameter,
            start_layers=[first['layer']], end_layers=[last['layer']],
            grid_mm=.25, max_vias=2, foreign_cache=cache, deadline_monotonic=lease,
            max_length_nm=128000000, diagnostics=detail, planar_guard=field_guard,
            local_shape_guard=lambda a, b, w, layer: capture_guard(tuple(a), tuple(b), w, int(layer)),
            via_guard=lambda p, _d, dia: all(capture_guard(tuple(p), tuple(p), dia, int(l))
                for l in board.GetEnabledLayers().CuStack()),
            heuristic_weight=3., neutral_state_dominance=True, field_state_dominance=True,
            obstacle_channel_axes=True, canonical_turns_only=True,
            native_board_envelope=True, search_wall_cap_s=10., max_expanded_states=100000)
        attempts.append(dict(reverse=reverse, source_frontier_pair=list(pair), search=detail,
                             complete_route=operations is not None))
        if operations is not None and not preflight(operations):
            attempts[-1]['preflight_refusal'] = preflight.last_attempt(); operations = None
        if operations is not None:
            break
    result = dict(complete=False, reason='bounded_full_class_layer_join_not_found',
        attempts=attempts, full_source_contract=contract, new_barrel_ampacity_credited=False,
        no_path_proof=False, release_authority=False)
    if operations is None or time.monotonic() >= search_deadline:
        return result
    import cec_certificate_repair as repair
    report = repair._lay_ops(board, operations, code, lock=False, reuse_existing_collinear=False)
    incoming = [t for t in board.GetTracks() if force._uid(t) not in old]
    result['native_materialization'] = report
    result['chain'] = _ordered_chain(board, incoming, pads, contract, deadline, endpoint_ports=menus)
    result['source_contacts'] = _source_contacts(pcbnew.LoadBoard(str(source)), incoming,
                                                result['chain'], deadline)
    result['hole_spacing'] = _drill_spacing(pcbnew.LoadBoard(str(source)), board, incoming, deadline)
    saved = dict(created_uuids=[force._uid(t) for t in incoming])
    save.save_native_additions(candidate, board, saved, old, board_hint=board_hint)
    _need(epoch == force._code_identity() and family == force._family(source, board_hint),
          'distributed_layer_construction_source_family_or_code_changed')
    _remaining(deadline)
    return dict(result, complete=True, reason='private_full_class_physical_chain_constructed',
        created_uuids=saved['created_uuids'], independent_saved_receiving_required=True)


def _receive(source, candidate, *, board_hint, net, pad_uuids, timeout_s=10.,
             native_frontier=False):
    """Recompile authority and independently receive the actual saved delta."""
    import pcbnew
    import cec_force_current as force
    import cec_additive_route_receiving as additive
    import cec_native_partition_pair as partitions
    import cec_native_current_capture as capture
    import cec_native_supply_via_context as web
    import cec_source_literal_additions as literal
    import cec_fab_profile as fab
    import cec_fr as fr
    result = dict(ok=False, complete=False, errors=[],
        scope='saved_full_class_distributed_physical_layer_join', current_qualified=False,
        plated_barrel_current_qualified=False, thermal_qualified=False,
        source_current_or_width_changed=False, existing_rating_graphs_unchanged=True,
        whole_shared_stage_still_required=True, release_authority=False)
    try:
        _need(type(native_frontier) is bool, 'explicit_native_frontier_mode_required')
        deadline = _deadline(timeout_s)
        source, candidate = [Path(p).resolve(strict=True) for p in (source, candidate)]
        _need(source != candidate, 'distinct_distributed_layer_saved_files_required')
        epoch = force._code_identity(); families = [force._family(p, board_hint) for p in (source, candidate)]
        parent, child = [pcbnew.LoadBoard(str(p)) for p in (source, candidate)]
        compiler = plan_native_frontier if native_frontier else plan
        scoped = compiler(parent, source, board_hint=board_hint, net=net, pad_uuids=pad_uuids,
                          timeout_s=_remaining(deadline))
        _need(scoped.get('complete') is True, 'fresh_saved_distributed_layer_scope_required')
        _, old = additive._nodes(source); _, new = additive._nodes(candidate)
        _need(not old.keys()-new.keys(), 'distributed_layer_cannot_retire_source_material')
        incoming_ids = new.keys()-old.keys()
        material = [t for t in child.GetTracks() if force._uid(t) in incoming_ids]
        _need(incoming_ids == {force._uid(t) for t in material}
              and all(new[u][0] in ('segment', 'via') for u in incoming_ids),
              'only_exact_new_distributed_tracks_and_vias_required')
        names = literal.incoming_copper_nets(candidate.read_text(), incoming_ids)
        _need(set(names) == incoming_ids and all(n == net for n in names.values()),
              'literal_distributed_new_net_mismatch')
        contract = scoped['contract']
        menus = _ports(parent, scoped, deadline, native_frontier=native_frontier)
        result['chain'] = _ordered_chain(child, material, _source_pads(child, scoped), contract, deadline,
                                         endpoint_ports=menus)
        result['source_contacts'] = _source_contacts(parent, material, result['chain'], deadline)
        result['hole_spacing'] = _drill_spacing(parent, child, material, deadline)
        # Saved geometry uses the original Source clearance/reservations;
        # an automatically generated antipad is not copper/pour permission.
        capture_guard = capture.Guard(parent, source, net=net, board_hint=board_hint,
                                      timeout_s=min(2., _remaining(deadline)))
        _need(capture_guard.complete is True and capture_guard.unclassified_owners == 0,
              'saved_distributed_source_control_reservations_required')
        cache = {}; nc = parent.GetNetcodeFromNetname(net); gap = math.ceil(contract['clearance_mm']*1e6)
        proofs = []
        for item in material:
            _remaining(deadline)
            if item.GetClass() == 'PCB_TRACK':
                layer = int(item.GetLayer()); a, b = item.GetStart(), item.GetEnd(); w = item.GetWidth()
                _need(fr._edge_leg_clear(parent, a, b, math.ceil(w/2))
                      and not force._native_track_rule_hits(parent, item.GetEffectiveShape(layer), layer, cache=cache)
                      and fr._snapshot_foreign_clear(a, b, w, gap,
                          *fr._foreign_shape_indexes(parent, layer, {nc}, cache=cache))
                      and capture_guard(tuple(a), tuple(b), w, layer),
                      'saved_distributed_source_track_guard_refused')
            else:
                _need(item.GetClass() == 'PCB_VIA' and item.GetViaType() == pcbnew.VIATYPE_THROUGH
                      and item.TopLayer() == pcbnew.F_Cu and item.BottomLayer() == pcbnew.B_Cu,
                      'ordinary_through_distributed_axis_required')
                at = item.GetPosition(); drill = item.GetDrillValue()
                diameter = item.GetWidth(pcbnew.F_Cu)
                required_dia, required_drill, _ = fab.board_legal_through_via_geometry(
                    parent, diameter/1e6, drill/1e6)
                if native_frontier:
                    import cec_route_dimensions as dimensions
                    # Re-evaluate the ACTUAL drill against the exact saved
                    # ring floor. The minimum-drill menu's land alone does
                    # not prove a larger actual drill keeps that annulus.
                    required_dia, required_drill = dimensions.ordinary_via_geometry(
                        {}, _source_via_limits(parent),
                        requested=(diameter/1e6, drill/1e6))
                source_dia, source_drill = _via_geometry(parent, contract,
                                                        source_minimum=native_frontier)
                _need(drill >= math.ceil(max(required_drill, source_drill)*1e6)
                      and diameter >= math.ceil(max(required_dia, source_dia)*1e6)
                      and diameter-drill >= max(_widths(parent, contract).values())
                      and all(item.GetWidth(l) == diameter for l in parent.GetEnabledLayers().CuStack())
                      and fr._edge_leg_clear(parent, at, at, math.ceil(diameter/2))
                      and fr._via_spot_clear(parent, at, diameter, gap, {nc}, drill_nm=drill,
                          net_code=nc, foreign_cache=cache)
                      and fr._via_spot_clear(child, at, diameter, gap, {nc}, drill_nm=drill,
                          net_code=nc, existing_via_uuid=force._uid(item), foreign_cache={})
                      and all(capture_guard(tuple(at), tuple(at), diameter, int(l))
                          for l in parent.GetEnabledLayers().CuStack()),
                      'saved_distributed_all_face_barrel_guard_refused')
                proof = web.receive(child, force._uid(item), contract,
                                    timeout_s=min(2., _remaining(deadline)))
                _need(proof['ok'] is True and proof['complete'] is True,
                      'saved_distributed_full_current_contact_web_required')
                proofs.append(proof)
        delta = additive.receive(source, candidate, board_hint=board_hint, timeout_s=_remaining(deadline))
        _need(delta['ok'] is True and delta['complete'] is True,
              'distributed_layer_exact_source_additive_replay_refused:'+str(delta['errors']))
        transition = partitions.compare(parent, child, timeout_s=_remaining(deadline))
        _need(transition['available'] is True and transition['preserved'] is True,
              'every_distributed_source_partition_must_survive')
        keys = [force._item_key(p) for p in _source_pads(parent, scoped)]
        parts = [next(p for p in transition['source_parts'] if key in p) for key in keys]
        _need(parts[0] != parts[1] and any(parts[0] | parts[1] <= p for p in transition['child_parts'])
              and len(transition['child_parts']) == len(transition['source_parts'])-1,
              'exactly_two_distributed_source_islands_must_join')
        _need(epoch == force._code_identity()
              and families == [force._family(p, board_hint) for p in (source, candidate)],
              'distributed_layer_saved_family_or_code_changed')
        _remaining(deadline)
        result.update(ok=True, complete=True, source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate), added_native_uuids=sorted(incoming_ids),
            canonical_supply_endpoints_independently_recompiled=True,
            unchanged_aggregate_current_contract=contract, actual_native_barrel_contacts=proofs,
            source_plus_exact_additions=delta, all_source_partitions_preserved=True,
            exactly_two_source_islands_joined=True,
            source_components=len(scoped['source_native_components']),
            candidate_components=len(scoped['source_native_components'])-1,
            unresolved_barrel_ampacity_and_thermal_debt=True)
        if native_frontier:
            result.update(scope='saved_full_class_original_native_frontier_layer_join',
                source_access_mode=scoped['source_access_mode'],
                original_barrels_used_for_physical_membership_only=True,
                old_barrel_capacity_credited=False, existing_planar_current_graph_unchanged=True)
    except (ValueError, RuntimeError, TypeError, KeyError, OSError, StopIteration) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def receive(source, candidate, *, board_hint, net, pad_uuids, timeout_s=10.):
    """Legacy same-face frontier receiving, unchanged and explicit."""
    return _receive(source, candidate, board_hint=board_hint, net=net,
                    pad_uuids=pad_uuids, timeout_s=timeout_s, native_frontier=False)


def receive_native_frontier(source, candidate, *, board_hint, net, pad_uuids, timeout_s=10.):
    """Receive a zero-cut full-class join to original physical track islands.

    Saved Source, roles, new web/geometry and strict island/contact receiving
    are freshly rederived. Enclosing current, field, absolute Kelvin, native
    DRC and intake gates remain mandatory; this is not current qualification.
    """
    return _receive(source, candidate, board_hint=board_hint, net=net,
                    pad_uuids=pad_uuids, timeout_s=timeout_s, native_frontier=True)
