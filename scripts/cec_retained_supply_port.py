"""Reach source-native plated ports without inventing new supply transitions.

Only existing through columns connected to the selected terminals by actual
current-sized source copper are ports. Whole-rail completion can receive a
truly isolated SMD land from one such existing column on its own copper face.
The proposed new body carries the full unchanged source current and class
width on an authorized non-plane face, with normal bounded package escapes.
Barrel reuse is a native contact witness, not barrel ampacity qualification.
"""
from __future__ import annotations

import math
import time

import pcbnew

import cec_fab_profile as fab
import cec_fr as fr
import cec_pair_semantics as pairs
import cec_search_budget as budget
from cec_route_dimensions import current_trace_widths


def plan(board, first, second, *, width_nm, clearance_nm, current_widths,
         spec, deadline_monotonic, max_length_nm, allow_maze=False,
         terminal_scope='local'):
    if (type(width_nm) is not int or width_nm <= 0
            or type(clearance_nm) is not int or clearance_nm < 0
            or type(deadline_monotonic) not in (int, float)
            or not math.isfinite(deadline_monotonic)
            or deadline_monotonic > time.monotonic() + 10.
            or type(allow_maze) is not bool
            or terminal_scope not in ('local', 'native-current-island')):
        raise ValueError('bounded_retained_supply_port_search_required')
    max_length_nm = fr._checked_route_length_nm(max_length_nm)
    if max_length_nm is None or max_length_nm <= 0:
        raise ValueError('positive_retained_supply_port_length_bound_required')
    if not current_widths or budget.exhausted(deadline_monotonic):
        return None, None
    authority = current_widths.get('current_authority') or {}
    if (any(type(authority.get(k)) not in (int, float)
            or not math.isfinite(authority[k]) or authority[k] <= 0
            for k in ('amps', 'geometry_margin'))
            or type(authority.get('margin_included')) is not bool):
        return None, None
    net, code = str(first.GetNetname()), first.GetNetCode()
    if (code <= 0 or code != second.GetNetCode()
            or net != str(second.GetNetname()) or net.rsplit('/', 1)[-1].upper().startswith('GND')
            or first.GetParentFootprint().IsDNP() or second.GetParentFootprint().IsDNP()):
        return None, None
    protected = {n for _, p, q in pairs.coupled_pair_names(board) for n in (p, q)}
    protected.update(n for p, q in fr._board_kelvin_pairs(board) for n in (p, q))
    protected.update(n for row in pairs.analog_input_pairs(board) for n in (row['p'], row['n']))
    protected.update(pairs.unresolved_current_monitor_nets(board))
    if net in protected:
        return None, None
    enabled = tuple(int(l) for l in board.GetEnabledLayers().CuStack())
    floors = current_widths.get('required_by_layer_nm') or {}
    if (set(floors) != set(enabled) or any(type(w) is not int or w <= 0 for w in floors.values())):
        return None, None
    profile = current_widths.get('profile')
    if profile != fab.active_profile_name(board):
        return None, None
    expected = current_trace_widths(authority,
        tuple(fab.COPPER_LAYER_IDS[l] for l in enabled), profile, rise_c=30.)
    if floors != {board.GetLayerID(n): math.ceil(w * 1e6) for n, w in expected.items()}:
        return None, None
    if type(spec.get('width')) is not int or not 0 < spec['width'] <= width_nm:
        return None, None
    capture_guard = None
    if terminal_scope == 'native-current-island':
        from cec_native_current_capture import Guard
        try:
            capture_guard = Guard(board, board.GetFileName(), net=net,
                timeout_s=max(.001, min(10., deadline_monotonic-time.monotonic())))
        except ValueError as exc:
            return None, dict(scope='native_current_capture_reservation',
                complete=False, error=str(exc), release_authority=False)
    planes = {board.GetLayerID(n) for n in fr.plane_layers(board)}
    layers = [l for l in enabled if l not in planes
        and not any(role in board.GetLayerName(l).upper() for role in ('GND', 'PWR'))]
    if not layers:
        return None, None
    pads = [p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetCode() == code]
    native = [t for t in board.GetTracks() if t.GetNetCode() == code]
    if len(pads) + len(native) > 4096:
        return None, None
    limits = board.GetDesignSettings()
    columns = []
    for item in [*pads, *native]:
        if budget.exhausted(deadline_monotonic):
            return None, None
        if (not all(item.IsOnLayer(l) for l in enabled)
                or item.GetParentGroup() and item.GetParentGroup().GetName().startswith(
                    ('CEC_LOCAL_SUPPLY_ALLOCATION_', 'CEC_CONTROL_CURRENT_', 'CEC_MEASUREMENT_CURRENT_'))):
            continue
        if item.GetClass() == 'PAD':
            if (item.GetAttribute() != pcbnew.PAD_ATTRIB_PTH or not item.HasHole()
                    or item.GetParentFootprint().IsDNP()):
                continue
            drill, size = item.GetDrillSize(), item.GetSize()
            if (drill.x <= 0 or drill.y <= 0
                    or size.x <= drill.x or size.y <= drill.y):
                continue
        elif item.GetClass() == 'PCB_VIA':
            if item.GetViaType() != pcbnew.VIATYPE_THROUGH:
                continue
            drill = int(item.GetDrillValue())
            ordinary = (drill >= limits.m_MinThroughDrill and drill > 0
                and all(item.GetWidth(l) >= max(limits.m_ViasMinSize,
                    drill + 2 * limits.m_ViasMinAnnularWidth) for l in enabled))
            if not ordinary and not fab.local_pofv_via_decision(board, item)[0]:
                continue
        else:
            continue
        columns.append(item)
    if capture_guard is not None:
        columns = [c for c in columns if capture_guard.allows_endpoint(
            dict(native_uuids=[c.m_Uuid.AsString()]))]
    if not columns:
        return None, None
    # The full native graph alone could reach a column through an undersized
    # monitor/consumer twig. Remove those edges from this read-only witness.
    # No zones or source conductor are changed, inferred or capacity-rated.
    current_tracks = [t for t in native if t.GetClass() == 'PCB_TRACK'
        and not (t.GetParentGroup() and t.GetParentGroup().GetName().startswith(
            ('CEC_LOCAL_SUPPLY_ALLOCATION_', 'CEC_CONTROL_CURRENT_', 'CEC_MEASUREMENT_CURRENT_')))
        and t.GetLayer() in floors and t.GetWidth() >= max(
            floors[int(t.GetLayer())], int(limits.m_TrackMinWidth))]
    conn = pcbnew.CONNECTIVITY_DATA()
    for item in [*pads, *current_tracks, *columns]:
        if budget.exhausted(deadline_monotonic) or not conn.Add(item):
            return None, None
    ports = []
    for root in (first, second):
        connected = {x.m_Uuid.AsString() for x in conn.GetConnectedItems(root)}
        connected.add(root.m_Uuid.AsString())
        if second.m_Uuid.AsString() in connected and root == first:
            return None, None
        own = [c for c in columns if c.m_Uuid.AsString() in connected
            and (terminal_scope == 'native-current-island'
                or math.dist(tuple(root.GetPosition()), tuple(c.GetPosition())) <= 1500000)]
        # A rail's closest useful departure may be far from the selected
        # terminal, but reached by proven full-current native source copper.
        # Fund exits near the other island before nearest-root truncation.
        target = second if root == first else first
        rank_from = target if terminal_scope == 'native-current-island' else root
        own.sort(key=lambda c: (math.dist(tuple(rank_from.GetPosition()), tuple(c.GetPosition())),
            c.m_Uuid.AsString()))
        ports.append(own[:64 if terminal_scope == 'native-current-island' else 16])
    if not all(ports) and terminal_scope != 'native-current-island':
        return None, None
    paired = sorted((math.dist(tuple(a.GetPosition()), tuple(b.GetPosition())),
        a.m_Uuid.AsString(), b.m_Uuid.AsString(), a, b)
        for a in ports[0] for b in ports[1] if a.m_Uuid != b.m_Uuid)[:64]
    menu = [(row, ()) for row in paired]
    if terminal_scope == 'native-current-island':
        # A bare, truly isolated SMD land need not invent a plated exit. It
        # can receive a full-current leg on its own face from the OTHER
        # island's already current-sized native column. Do not reinterpret a
        # thin existing twig, allocation, zone contact or another land as an
        # isolated terminal. The real raw graph, not the filtered current
        # witness above, owns that negative fact.
        raw = fr._read_only_route_connectivity(board, {code})
        one_sided = []
        for index, root in enumerate((first, second)):
            if (root.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or root.HasHole()
                    or root.GetParentGroup() is not None
                    or any(x.m_Uuid != root.m_Uuid for x in raw.GetConnectedItems(root))):
                continue
            for column in ports[1-index]:
                a, b = (root, column) if index == 0 else (column, root)
                row = (math.dist(tuple(a.GetPosition()), tuple(b.GetPosition())),
                    a.m_Uuid.AsString(), b.m_Uuid.AsString(), a, b)
                one_sided.append((row, (root.m_Uuid.AsString(),)))
        menu.extend(sorted(one_sided, key=lambda row: row[0][:3])[:64])
    cache = {}
    for (_, _, _, a, b), bare in menu:
        for layer in layers:
            if budget.exhausted(deadline_monotonic):
                return None, None
            if not a.IsOnLayer(layer) or not b.IsOnLayer(layer):
                continue
            route_width = max(width_nm, floors[layer], int(limits.m_TrackMinWidth))
            # Only a source-native isolated land gets a normal bounded
            # package escape; existing columns keep the full body width.
            escapes = {x.m_Uuid.AsString(): fr._pad_local_escape(
                x, route_width, clearance_nm, int(limits.m_TrackMinWidth))
                for x in (a, b) if x.m_Uuid.AsString() in bare}
            legs = fr._guarded_profiled_lastmile_legs(board,
                a.GetPosition(), b.GetPosition(), route_width, layer, clearance_nm, code,
                lambda x, y, half: fr._edge_leg_clear(board, x, y, half),
                start_escape=escapes.get(a.m_Uuid.AsString()),
                end_escape=escapes.get(b.m_Uuid.AsString()),
                allow_maze=allow_maze, foreign_cache=cache,
                deadline_monotonic=deadline_monotonic, max_length_nm=max_length_nm,
                compact_phase_jogs=True, minimize_escape=bool(bare),
                run_guard=(None if capture_guard is None or not capture_guard.active
                    else lambda x,y,w: capture_guard(tuple(x),tuple(y),w,int(layer))))
            if legs and (capture_guard is None or capture_guard.allows_ops(
                    [('trk', x, y, w, layer) for x, y, w in legs])):
                return [('trk', x, y, w, layer) for x, y, w in legs], dict(
                    source_pad_uuids=[first.m_Uuid.AsString(), second.m_Uuid.AsString()],
                    retained_column_uuids=[x.m_Uuid.AsString() for x in (a, b)
                        if x.m_Uuid.AsString() not in bare],
                    native_route_terminal_uuids=[a.m_Uuid.AsString(), b.m_Uuid.AsString()],
                    isolated_source_land_uuids=list(bare),
                    isolated_source_lands_checked_in_raw_native_graph=bool(bare),
                    native_source_current_sized_contact_graph=True,
                    terminal_scope=terminal_scope,
                    layer=board.GetLayerName(layer), width_nm=route_width,
                    unchanged_whole_source_current=authority,
                    current_capture_reservation=(capture_guard.report()
                        if capture_guard is not None else None),
                    new_vias=0, barrel_capacity_qualified=False, release_authority=False)
    return None, None


def plan_rail(board, first, second, *, width_nm, clearance_nm, current_widths,
              spec, deadline_monotonic, allow_maze=False):
    """Complete distinct native rail islands, not a capacitor-owner bypass.

    The bounded geometric detour policy is separate from bypass locality.
    Every new leg still carries the unchanged entire rail current and class
    width. Local bypass access still has its 1.5 mm bound; a whole rail may
    use any retained column reached by the unchanged full-current native
    island graph, under explicit item/menu/work/wall bounds. Neither a
    current allocation nor extra via/barrel credit is introduced.
    """
    if (type(width_nm) is not int or width_nm <= 0
            or type(clearance_nm) is not int or clearance_nm < 0
            or type(deadline_monotonic) not in (int, float)
            or not math.isfinite(deadline_monotonic)
            or deadline_monotonic > time.monotonic() + 10.
            or type(allow_maze) is not bool):
        raise ValueError('bounded_retained_supply_rail_search_required')
    if (first.GetNetCode() <= 0 or first.GetNetCode() != second.GetNetCode()
            or budget.exhausted(deadline_monotonic)):
        return None, None
    graph = fr._read_only_route_connectivity(board, {first.GetNetCode()})
    if (first.m_Uuid == second.m_Uuid or any(x.m_Uuid == second.m_Uuid
            for x in graph.GetConnectedItems(first))):
        return None, None
    direct = math.dist(tuple(first.GetPosition()), tuple(second.GetPosition()))
    limit = math.ceil(max(2 * direct, direct + 2 * width_nm + 2 * clearance_nm))
    ops, proof = plan(board, first, second, width_nm=width_nm,
        clearance_nm=clearance_nm, current_widths=current_widths, spec=spec,
        deadline_monotonic=deadline_monotonic, max_length_nm=limit,
        allow_maze=allow_maze, terminal_scope='native-current-island')
    if proof:
        proof.update(route_context='source-current-owned-native-rail-island-completion',
            max_rail_length_nm=limit, capacitor_locality_waived=False,
            old_native_islands_distinct=True)
    return ops, proof
