"""Bounded, read-only all-face diagnostics for an explicitly sized barrel.

The existing via guard keeps its verdict and its inexpensive first refusal.
This opt-in report inventories *every* enabled face in that guard's native
foreign-shape snapshot, even after an early refusal. Missing identities,
unknown collisions, truncation and deadlines make the inventory incomplete.
It is not removal permission, proof of no path, ampacity or release authority.
Ground-plane refill/antipads and non-copper constraints remain separate gates.
"""
import itertools
import math
import time

import pcbnew

MAX_ITEMS = 16384


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise TimeoutError('native_barrel_blocker_inventory_deadline')


def _expected_ids(items, layer, net_code):
    """Detect native shapes silently omitted by an underlying SWIG adapter."""
    result = set()
    for item in items:
        kind = item.GetClass()
        if kind == 'PAD' and item.HasHole() and item.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            result.add(str(item.m_Uuid.AsString()))
        if kind in ('PAD', 'PCB_TRACK', 'PCB_ARC', 'PCB_VIA'):
            if item.GetNetCode() == net_code or not item.IsOnLayer(layer):
                continue
        elif kind == 'ZONE':
            # Reservation selection belongs to the existing native guard.
            continue
        elif item.GetLayer() != layer:
            continue
        result.add(str(item.m_Uuid.AsString()))
    return result


def inventory(board, net_code, at_nm, *, diameter_nm, drill_nm, clearance_nm,
              deadline, max_blockers_per_layer=64, native_padstack_via=None):
    """Report all guarded copper faces without changing acceptance predicates."""
    if (type(net_code) is not int or net_code <= 0
            or not isinstance(at_nm, (list, tuple)) or len(at_nm) != 2
            or any(type(v) is not int or abs(v) > 2_000_000_000 for v in at_nm)
            or type(diameter_nm) is not int or type(drill_nm) is not int
            or not 0 < drill_nm < diameter_nm <= 8_000_000
            or type(clearance_nm) is not int or not 0 <= clearance_nm <= 10_000_000
            or type(deadline) not in (int, float) or not math.isfinite(deadline)
            or not time.monotonic() < deadline <= time.monotonic()+10.
            or type(max_blockers_per_layer) is not int
            or not 1 <= max_blockers_per_layer <= 256):
        raise ValueError('bounded_explicit_native_barrel_diagnostic_required')
    if net_code not in set(map(int, board.GetNetInfo().NetsByNetcode().keys())):
        raise ValueError('native_barrel_diagnostic_source_net_missing')
    layers = tuple(map(int, board.GetEnabledLayers().CuStack()))
    if not 1 <= len(layers) <= 32 or len(layers) != len(set(layers)):
        raise ValueError('bounded_native_barrel_diagnostic_faces_required')
    items = []
    for item in itertools.chain(board.GetTracks(), board.Zones(),
            (p for fp in board.GetFootprints() for p in fp.Pads()),
            (p for fp in board.GetFootprints() for p in fp.GraphicalItems())):
        _tick(deadline)
        items.append(item)
        if len(items) > MAX_ITEMS:
            raise ValueError('native_barrel_diagnostic_item_bound')
    import cec_cell_row_rebuild as cells
    import cec_fr as fr
    binding = cells._source_binding(board)
    land_diameters = None
    if native_padstack_via is not None:
        from cec_native_via_land_context import inspect
        land_diameters = inspect(board, native_padstack_via,
            at=pcbnew.VECTOR2I(*at_nm), maximum_diameter_nm=diameter_nm,
            drill_nm=drill_nm, net_code=net_code, clearance_nm=clearance_nm)
    report = dict(schema=1, scope='native_via_guard_foreign_shape_stack',
        source_native_binding=binding, net_code=net_code, at_nm=list(at_nm),
        diameter_nm=diameter_nm, drill_nm=drill_nm, clearance_nm=clearance_nm,
        enabled_layers=[board.GetLayerName(l) for l in layers], layer_rows=[],
        native_guard_clear=None, native_guard_report={}, inventory_complete=False,
        source_unchanged=False, retirement_authorized=False, current_authority=False,
        routing_admitted=False, no_path_proved=False, release_authority=False,
        includes_ground_plane_zone_refill=False, errors=[])
    report['actual_native_land_diameters_nm'] = (
        {board.GetLayerName(layer): value for layer, value in land_diameters.items()}
        if land_diameters is not None else None)
    point = pcbnew.VECTOR2I(*at_nm)
    circle = pcbnew.SHAPE_CIRCLE(point, diameter_nm // 2)
    try:
        _tick(deadline)
        report['native_guard_clear'] = fr._via_spot_clear(board, point, diameter_nm,
            clearance_nm, {net_code}, drill_nm=drill_nm, net_code=net_code,
            foreign_cache={}, report=report['native_guard_report'],
            native_padstack_via=native_padstack_via)
        complete = True
        for layer in layers:
            _tick(deadline)
            zones, copper = fr._identified_foreign_shape_indexes(board, layer, {net_code})
            _tick(deadline)
            rows = [*zones.get('rows', ()), *copper.get('rows', ())]
            if len(rows) > MAX_ITEMS*2:
                raise ValueError('native_barrel_diagnostic_shape_bound')
            present = {str((r[2] or {}).get('uuid', '')) for r in rows}
            missing = sorted(_expected_ids(items, layer, net_code)-present)
            # Ask for one beyond the explicit output bound. The native query
            # itself is bounded by the item count, and returns exact collisions.
            face_diameter = land_diameters[layer] if land_diameters is not None else diameter_nm
            face_shape = (native_padstack_via.GetEffectiveShape(layer)
                if land_diameters is not None else circle)
            hits = fr._snapshot_foreign_blockers(point, point, face_diameter,
                clearance_nm, zones, copper, limit=max_blockers_per_layer+1,
                _native_shape=face_shape)
            _tick(deadline)
            truncated = len(hits) > max_blockers_per_layer
            hits = hits[:max_blockers_per_layer]
            known = not missing and not truncated and all(
                h.get('geometry_status') != 'unknown' and h.get('uuid')
                and not h.get('native_identity_unavailable') for h in hits)
            complete = complete and known
            report['layer_rows'].append(dict(layer=board.GetLayerName(layer),
                actual_land_diameter_nm=face_diameter,
                blockers=hits, truncated=truncated, missing_native_uuids=missing[:256],
                missing_native_count=len(missing), inventory_complete=bool(known)))
        report['inventory_complete'] = bool(complete)
    except (ValueError, TimeoutError) as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc))
    if binding != cells._source_binding(board):
        raise ValueError('native_barrel_diagnostic_source_mutated')
    report['source_unchanged'] = True
    return report
