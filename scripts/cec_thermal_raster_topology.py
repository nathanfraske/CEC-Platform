"""Bounded native-terminal/raster parity preflight for a thermal field screen.

This never edits copper or adds graph edges.  A finer, otherwise identical mesh
may recover a lost native contact.  Native component membership is used only to
detect disagreement, never to authorize a local shortcut or certify conductance.
Mesh convergence, package/contact temperatures and operating-scenario coherence
remain separate, unqualified evidence.
"""
from __future__ import annotations

import math
import hashlib
import time

import numpy as np
from scipy.ndimage import label


LIMITS = dict(max_attempts=3, min_pitch_mm=0.05, max_grid_cells=600_000,
              max_net_nodes=1_500_000, max_total_nodes=5_000_000,
              max_estimated_bytes=2 * 1024 ** 3, max_native_items=50_000,
              max_terminal_pads=4096, max_contact_pairs=4096,
              max_drills=10_000, preflight_seconds=30.0)


class PreflightRefusal(RuntimeError):
    pass


def _check(deadline):
    if deadline is not None and time.monotonic() >= deadline:
        raise PreflightRefusal("topology_preflight_deadline")


def _limits(overrides):
    values = dict(LIMITS)
    for key, value in (overrides or {}).items():
        if key not in values or not math.isfinite(float(value)) or value <= 0:
            raise ValueError("invalid thermal topology limit: " + str(key))
        # Callers may tighten work bounds, never silently remove them.
        if ((key == 'min_pitch_mm' and value < values[key]) or
                (key != 'min_pitch_mm' and value > values[key])):
            raise ValueError("thermal topology limit exceeds hard bound: " + key)
        if isinstance(values[key], int) and int(value) != value:
            raise ValueError("thermal topology integer limit required: " + key)
        values[key] = value
    return values


def _uid(item):
    return str(item.m_Uuid.AsString())


def _native_epoch(board):
    """Exact in-memory native serialization; no save or label normalization."""
    import pcbnew
    formatter = pcbnew.STRING_FORMATTER()
    writer = pcbnew.PCB_IO_KICAD_SEXPR()
    writer.FormatBoardToFormatter(formatter, board)
    return hashlib.sha256(formatter.GetString().encode()).hexdigest()


def _native_plan(board, currents, overrides, stds, limits, deadline):
    """Bind every declared physical pad, not merely one convenient pair."""
    wanted = {n for n, amps in currents.items() if amps > 0}
    native_items = list(board.GetTracks()) + list(board.Zones())
    native_items += [p for fp in board.GetFootprints() for p in fp.Pads()]
    if len(native_items) > limits['max_native_items']:
        raise PreflightRefusal('topology_native_item_limit')
    # BOARD.BuildConnectivity()/CONNECTIVITY_DATA.Build() may propagate a pad's
    # net onto an intersecting foreign track. A diagnostic must not rewrite the
    # very conductor identity it is checking. Incremental native inventory
    # supports GetConnectedItems without that net-propagation pass.
    import pcbnew
    conn = pcbnew.CONNECTIVITY_DATA()
    for index, item in enumerate(list(board.GetFootprints()) +
                                 list(board.GetTracks()) + list(board.Zones())):
        if index % 512 == 0:
            _check(deadline)
        conn.Add(item)
    _check(deadline)
    by_net = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = str(pad.GetNetname())
            if net in wanted:
                by_net.setdefault(net, []).append(pad)
    plans, legacy = {}, []
    for net in sorted(wanted):
        _check(deadline)
        ov = (overrides or {}).get(net)
        if not isinstance(ov, dict):
            # Legacy centroid/auto endpoints have no declared native pad bank.
            # Preserve legacy execution but do not claim or adapt their topology.
            legacy.append(net)
            continue
        sides = {}
        for side in ('src', 'sink'):
            refs = set(ov.get('refs_' + side) or ())
            allowed = ov.get('source_layers' if side == 'src' else 'sink_layers')
            allowed = None if allowed is None else set(allowed)
            from cec_thermal_terminal_selection import pads as select_pads
            selector_key='source_pad_uuids' if side=='src' else 'sink_pad_uuids'
            if selector_key in ov and ov[selector_key] is None:
                raise PreflightRefusal('native_terminal_empty_explicit_pad_scope:' + net)
            try:
                rows=select_pads(board,net,refs,stds,allowed_layers=allowed,
                    pad_uuids=ov.get(selector_key),deadline=deadline,
                    max_pads=limits['max_terminal_pads'])
            except ValueError as exc:
                raise PreflightRefusal('native_terminal_face_unresolved:' + net + ':' + str(exc)) from exc
            sides[side] = rows
        rows = sides['src'] + sides['sink']
        if len(rows) > limits['max_terminal_pads']:
            raise PreflightRefusal('topology_terminal_limit:' + net)
        source_ids = {r['uuid'] for r in sides['src']}
        sink_ids = {r['uuid'] for r in sides['sink']}
        if source_ids & sink_ids:
            raise PreflightRefusal('native_source_sink_pad_overlap:' + net)
        component_by_id = {}
        for row in rows:
            _check(deadline)
            if row['uuid'] in component_by_id:
                continue
            members = {_uid(it) for it in conn.GetConnectedItems(row['native'])}
            members.add(row['uuid'])
            if not (members & source_ids) or not (members & sink_ids):
                raise PreflightRefusal('native_terminal_disconnected:' + net)
            component = min(members & (source_ids | sink_ids))
            for member in members & (source_ids | sink_ids):
                component_by_id[member] = component
        plans[net] = dict(sides=sides, component_by_id=component_by_id)
    return plans, legacy


def _component_labels(masks, vertical, grid, deadline):
    """The solver's four-neighbor graph and real positive barrel links only."""
    parent, labels = [], {}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def join(a, b):
        a, b = find(a), find(b)
        if a != b:
            parent[b] = a

    for std, mask in masks.items():
        _check(deadline)
        values, count = label(mask)  # default is 4-neighbor, never 8-neighbor
        offset = len(parent)
        parent.extend(range(offset, offset + count))
        labels[std] = np.where(values, values - 1 + offset, -1)
    for index, (cell, barrels) in enumerate(vertical.items()):
        if index % 512 == 0:
            _check(deadline)
        y, x = divmod(cell, grid.nx)
        if not (0 <= y < grid.ny and 0 <= x < grid.nx):
            raise PreflightRefusal('invalid_native_barrel_cell')
        for barrel in barrels:
            if (not math.isfinite(float(barrel.get('drill_mm', 0))) or
                    float(barrel.get('drill_mm', 0)) <= 0 or
                    not math.isfinite(float(barrel.get('conductance_fraction', 1))) or
                    float(barrel.get('conductance_fraction', 1)) <= 0):
                raise PreflightRefusal('unsupported_native_barrel')
            here = [std for std in barrel['span']
                    if std in labels and labels[std][y, x] >= 0]
            for std in here[1:]:
                join(int(labels[here[0]][y, x]), int(labels[std][y, x]))
    roots = np.array([find(i) for i in range(len(parent))], dtype=np.int64)
    for std, values in labels.items():
        _check(deadline)
        occupied = values >= 0
        values[occupied] = roots[values[occupied]]
    return labels


def _geometry_pairs(board, th):
    enabled = th._enabled_std_layers(board, dict(th.STD_CU_LAYERS))
    pairs = set()
    for item in list(board.GetTracks()) + list(board.Zones()):
        net = str(item.GetNetname())
        if not net:
            continue
        layers = (item.GetLayerSet().Seq() if hasattr(item, 'GetLayerSet')
                  else [item.GetLayer()])
        pairs.update((net, enabled[l]) for l in layers if l in enabled)
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname():
                layers = {enabled[l] for l in p.GetLayerSet().Seq() if l in enabled}
                # Match the existing _pad_cells fallback, including its count.
                pairs.update((str(p.GetNetname()), std)
                             for std in (layers or set(enabled.values())))
    # _zone_polys also represents unnamed zones and any saved filled known
    # layer. Count those conservatively; the estimator cannot omit material
    # which the unchanged thermal raster will process.
    all_layers = dict(th.STD_CU_LAYERS)
    for zone in board.Zones():
        pairs.update((str(zone.GetNetname()), all_layers[l])
                     for l in zone.GetLayerSet().Seq() if l in all_layers)
    return pairs


def _working_memory_reservation(grid, pairs, currents, enabled_layers, limits):
    """Bound the streaming implementation, not the removed dense-all-net cache.

    All geometry is counted. Inactive pairs retain lossless packed occupancy;
    active pairs retain their masks/float widths. Reserve whole-grid scratch
    separately (rasterizer temporaries and one net's unpacked layer masks), plus
    global fields/overlays and the largest electrical/temperature graph. These
    are deliberately conservative reservations, not measured peak RSS.
    """
    active = {(n, layer) for n, layer in pairs if currents.get(n, 0) > 0}
    inactive = pairs - active
    active_layers = {}
    for net, layer in active:
        active_layers.setdefault(net, set()).add(layer)
    largest_graph_layers = max([1] + [len(v) for v in active_layers.values()])
    all_layers = len({layer for _, layer in pairs} | set(enabled_layers))
    pieces = dict(
        global_field_and_overlay_bytes=grid.n * (128 + all_layers),
        active_dense_electrical_bytes=grid.n * 20 * len(active),
        inactive_packed_occupancy_bytes=((grid.n + 7) // 8) * len(inactive),
        stream_temporary_bytes=grid.n * (128 + all_layers),
        graph_workspace_bytes=min(grid.n * largest_graph_layers,
                                  limits['max_net_nodes']) * 400,
        geometry_pair_metadata_bytes=len(pairs) * 512)
    return dict(model='all_copper_streaming_v1', geometry_pairs=len(pairs),
        active_dense_pairs=len(active), inactive_packed_pairs=len(inactive),
        largest_graph_layers=largest_graph_layers, **pieces,
        total_bytes=sum(pieces.values()))


def _recovery_witnesses(board, th, net, grid, labels, limits, deadline):
    """Certify the supported lost-contact class without granting a shortcut.

    A shared integer endpoint of two straight tracks contains their minimum
    half-width disk. Require that disk to be free of *all* actual drill shapes.
    This is a positive geometric explanation for retrying a mesh, not a new
    resistor edge or ampacity/barrel qualification. Other classes stay unknown.
    """
    import pcbnew
    endpoints, by_track, holes = {}, {}, []
    for item in board.GetTracks():
        _check(deadline)
        if item.Type() == pcbnew.PCB_VIA_T:
            if item.GetDrillValue() > 0:
                holes.append((item, item.GetEffectiveHoleShape()))
            continue
        if item.Type() != pcbnew.PCB_TRACE_T or str(item.GetNetname()) != net:
            continue
        std = th.STD_CU_LAYERS.get(item.GetLayer())
        if std not in labels or item.GetWidth() <= 0:
            continue
        for point in (item.GetStart(), item.GetEnd()):
            endpoints.setdefault((std, int(point.x), int(point.y)), []).append(item)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.HasHole():
                holes.append((pad, pad.GetEffectiveHoleShape()))
    if len(holes) > limits['max_drills'] or any(h is None for _, h in holes):
        raise PreflightRefusal('unsupported_recovery_drill_inventory:' + net)

    def track_labels(track, std):
        key = _uid(track)
        if key not in by_track:
            a, b = track.GetStart(), track.GetEnd()
            mask, _ = th._rasterize_tracks([(a.x/1e6, a.y/1e6,
                b.x/1e6, b.y/1e6, track.GetWidth()/1e6)], grid)
            by_track[key] = {int(v) for v in np.unique(labels[std][mask]) if v >= 0}
        return by_track[key]

    witnesses, examined = [], 0
    for (std, x, y), tracks in endpoints.items():
        for i, a in enumerate(tracks):
            for b in tracks[i+1:]:
                examined += 1
                _check(deadline)
                if examined > limits['max_contact_pairs']:
                    raise PreflightRefusal('topology_contact_pair_limit')
                if _uid(a) == _uid(b):
                    continue
                ca, cb = track_labels(a, std), track_labels(b, std)
                if not ca or not cb or ca & cb:
                    continue
                radius = min(int(a.GetWidth()), int(b.GetWidth())) // 2
                if radius <= 0:
                    raise PreflightRefusal('unsupported_zero_material_contact:' + net)
                disk = pcbnew.SHAPE_CIRCLE(pcbnew.VECTOR2I(x, y), radius)
                for index, (item, hole) in enumerate(holes):
                    if index % 512 == 0:
                        _check(deadline)
                    if hole.Collide(disk, 0):
                        raise PreflightRefusal('lost_contact_intersects_actual_drill:' + net)
                witnesses.append(dict(kind='native_shared_straight_track_endpoint_cap',
                    layer=std, point_nm=[x, y], cap_radius_nm=radius,
                    track_uuids=sorted([_uid(a), _uid(b)]),
                    track_widths_nm=[int(a.GetWidth()), int(b.GetWidth())],
                    complete_drill_inventory_count=len(holes),
                    actual_hole_intersections=0, geometry_only=True,
                    conductance_or_ampacity_qualified=False))
    if not witnesses:
        raise PreflightRefusal('unsupported_native_raster_contact_class:' + net)
    return witnesses


def _raster(board, th, grid, nets, stackup, include_traces, deadline):
    """Reconstruct, do not dilate/patch, the production current masks."""
    masks = {}
    stds = dict(th.STD_CU_LAYERS)
    for (net, std), polys in th._zone_polys(board, stds).items():
        _check(deadline)
        if net in nets and stackup.get(std, 0) > 0:
            mask = th._rasterize_polys(polys, grid)
            if mask.any():
                masks.setdefault(net, {})[std] = mask
    if include_traces:
        for (net, std), segments in th._track_segs(board, stds).items():
            _check(deadline)
            if net in nets and stackup.get(std, 0) > 0:
                mask, _ = th._rasterize_tracks(segments, grid)
                old = masks.setdefault(net, {}).get(std)
                masks[net][std] = mask if old is None else old | mask
    pad_map = th._pad_cells(board, grid, stds, area=True, nets=nets)
    for net, refs in pad_map.items():
        _check(deadline)
        for cells in refs.get('__pads__', {}).values():
            for std, cell in cells:
                if stackup.get(std, 0) <= 0:
                    continue
                by_layer = masks.setdefault(net, {})
                mask = by_layer.get(std)
                if mask is None:
                    mask = np.zeros((grid.ny, grid.nx), dtype=bool)
                    by_layer[std] = mask
                mask.ravel()[cell] = True
    return masks, th._collect_vertical_connectors(board, grid, stds)


def _compare(board, th, grid, plans, masks, vertical, limits, deadline):
    total_nodes, results, mismatch = 0, {}, []
    for net, plan in plans.items():
        _check(deadline)
        own = masks.get(net, {})
        nodes = sum(int(mask.sum()) for mask in own.values())
        total_nodes += nodes
        if nodes > limits['max_net_nodes'] or total_nodes > limits['max_total_nodes']:
            raise PreflightRefusal('topology_node_limit')
        labels = _component_labels(own, vertical.get(net, {}), grid, deadline)
        sides, terminal_rows, missing = {}, [], False
        raster_to_native = {}
        for side in ('src', 'sink'):
            sides[side] = set()
            for row in plan['sides'][side]:
                cells = th._pad_cell_set(row['native'], grid)
                own_labels, count = set(), 0
                for std in row['layers']:
                    for c in cells:
                        values = labels.get(std)
                        if values is None or int(values.ravel()[c]) < 0:
                            missing = True
                        else:
                            label_id = int(values.ravel()[c])
                            own_labels.add(label_id)
                            count += 1
                            raster_to_native.setdefault(label_id, set()).add(
                                plan['component_by_id'][row['uuid']])
                if not own_labels:
                    missing = True
                sides[side] |= own_labels
                terminal_rows.append(dict(uuid=row['uuid'], ref=row['ref'], pad=row['pad'],
                    side=side, native_component=plan['component_by_id'][row['uuid']],
                    layers=row['layers'], represented_cells=count,
                    raster_components=sorted(own_labels)))
        common = sides['src'] & sides['sink']
        complete = (not missing and bool(common) and
                    sides['src'] <= common and sides['sink'] <= common)
        false_merge = any(len(group) > 1 for group in raster_to_native.values())
        if false_merge:
            complete = False
        results[net] = dict(native_terminal_connected=True, raster_terminal_complete=complete,
                            raster_merges_native_components=false_merge, nodes=nodes,
                            terminals=terminal_rows)
        if not complete:
            if false_merge:
                raise PreflightRefusal('raster_merges_native_terminal_components:' + net)
            results[net]['recovery_contact_witnesses'] = _recovery_witnesses(
                board, th, net, grid, labels, limits, deadline)
            mismatch.append(net)
    return results, mismatch, total_nodes


def select_grid(board, th, *, currents, overrides, stackup, grid_mm,
                include_traces=True, area_injection=True, ideal_pad_faces=False,
                deadline=None, limits=None):
    """Choose a bounded mesh before any electrical or temperature solve.

    Returned ``complete`` means the checked *terminal topology* was represented,
    not that the finite-volume conductance, real load scenario or temperature was
    qualified. No current is changed, no copper is painted and no shortcut added.
    """
    started = time.monotonic()
    bounds = _limits(limits)
    if not math.isfinite(grid_mm) or grid_mm <= 0:
        raise ValueError('thermal grid pitch must be finite and positive')
    stop = min(deadline if deadline is not None else math.inf,
               started + bounds['preflight_seconds'])
    report = dict(schema=1, complete=False, requested_pitch_mm=grid_mm,
                  selected_pitch_mm=None, attempts=[], limits=bounds,
                  refinement_changed_copper=False, added_graph_shortcuts=False,
                  native_scope='declared terminal component parity only',
                  local_material_conductance_qualified=False,
                  grid_convergence_verified=False, numerical_qualification=False,
                  inherited_deadline_monotonic=deadline, preflight_deadline_monotonic=stop)
    try:
        _check(stop)
        epoch = _native_epoch(board)
        report['native_board_sha256'] = epoch

        def verify_epoch():
            _check(stop)
            if _native_epoch(board) != epoch:
                raise PreflightRefusal('native_geometry_changed_during_topology_preflight')

        stds = th._enabled_std_layers(board, dict(th.STD_CU_LAYERS))
        plans, legacy = _native_plan(board, currents, overrides, stds, bounds, stop)
        verify_epoch()
        report['legacy_unverified_nets'] = legacy
        report['native_terminal_nets'] = sorted(plans)
        if plans and (not area_injection or ideal_pad_faces):
            raise PreflightRefusal('unsupported_legacy_terminal_discretization')
        pairs = _geometry_pairs(board, th)
        bbox = th._board_geometry(board)
        pitch = grid_mm
        for attempt in range(int(bounds['max_attempts'])):
            _check(stop)
            grid = th.Grid(*bbox, pitch)
            reservation = _working_memory_reservation(grid, pairs, currents,
                                                       stds.values(), bounds)
            estimated = reservation['total_bytes']
            report['working_memory_reservation'] = dict(pitch_mm=pitch,
                grid_cells=grid.n, **reservation)
            if grid.n > bounds['max_grid_cells']:
                raise PreflightRefusal('topology_grid_cell_limit')
            if estimated > bounds['max_estimated_bytes']:
                raise PreflightRefusal('topology_working_memory_limit')
            if pitch < bounds['min_pitch_mm']:
                raise PreflightRefusal('topology_minimum_pitch_limit')
            if not plans:
                # No topology claim, but all-copper memory is still bounded for
                # component-only and legacy automatic-endpoint field screens.
                report.update(complete=True, selected_pitch_mm=pitch,
                    status='not_applicable_no_declared_native_terminal_bank')
                return report
            masks, vertical = _raster(board, th, grid, set(plans), stackup,
                                      include_traces, stop)
            verify_epoch()
            results, mismatch, nodes = _compare(board, th, grid, plans, masks, vertical,
                                                bounds, stop)
            _check(stop)
            verify_epoch()
            report['attempts'].append(dict(index=attempt, pitch_mm=pitch,
                grid_cells=grid.n, estimated_working_bytes=estimated, nodes=nodes,
                working_memory_reservation=reservation,
                nets=results, mismatched_nets=mismatch))
            del masks, vertical
            if not mismatch:
                report.update(complete=True, selected_pitch_mm=pitch,
                    native_identity_verified=True,
                    status='native_terminal_parity_at_refined_grid' if attempt
                    else 'native_terminal_parity_at_requested_grid')
                break
            pitch /= 2.0
        if not report['complete']:
            raise PreflightRefusal('topology_refinement_attempt_limit')
    except PreflightRefusal as exc:
        report.update(status='unknown', refusal=str(exc))
    except Exception as exc:
        report.update(status='unknown', refusal='native_topology_preflight_error',
                      error_type=type(exc).__name__, error=str(exc))
    finally:
        report['elapsed_s'] = time.monotonic() - started
    return report
