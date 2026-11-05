"""Exact frozen copper authority, distinct from clipped planning corridors."""
from functools import lru_cache
import json
import math


def placement_reservations(state):
    """The existing postfreeze body reservation, shared with search.

    Deliberately retains the commit guard's current F.Cu-body/through-via
    semantics. Pad-layer independence for declared consumers is still proved
    natively; this is not permission to move a physical power terminal.
    """
    import cec_synth_pipeline as synth
    rows = list(synth._pourfirst_exact_avoid_boxes(state.get('pours') or ()))
    for via in state.get('vias') or ():
        if via.get('x_mm') is None or via.get('y_mm') is None:
            continue
        radius = max(.4, float(via.get('diameter_mm') or 0.0) / 2.0)
        x, y = float(via['x_mm']), float(via['y_mm'])
        rows.append(dict(kind='bridge_via', net=via.get('net'),
                         x0=x-radius, x1=x+radius, y0=y-radius, y1=y+radius))
    return rows


def copper_layer(board, name):
    """Resolve canonical or display copper names; never default to top copper."""
    import pcbnew
    known = {}
    for layer in board.GetEnabledLayers().CuStack():
        known[pcbnew.LayerName(int(layer))] = int(layer)
        known[board.GetLayerName(int(layer))] = int(layer)
    if name not in known:
        raise ValueError('unknown or disabled copper layer: %r' % name)
    return known[name]


def frozen_terminal_tokens(state, token_nets):
    """Return positively declared owned pins, or None for ambiguous authority.

    Sharing a net does not make a high-impedance consumer a current terminal.
    The per-net reserve receipts and aggregate DSN exclusion list must agree,
    and every named pin must still exist on its declared native net. Missing
    or legacy evidence retains the conservative whole-net freeze.
    """
    if state.get('placement_scope') != 'complete':
        return None
    frozen = set(state.get('frozen_nets') or ())
    report = state.get('reserve_report') or {}
    aggregate = set(state.get('exclude_pins') or ())
    owned = set()
    if not frozen or not aggregate:
        return None
    for net in frozen:
        row = report.get(net) or {}
        pins = row.get('exclude_pins')
        if (row.get('reserved') is not True or not isinstance(pins, list)
                or len(set(pins)) < 2):
            return None
        if any(token_nets.get(pin) != {net} for pin in pins):
            return None
        owned.update(pins)
    return owned if owned == aggregate else None


def frozen_pad_contacts(board, footprint, state, clearance_mm):
    """Exact layer-aware copper separation for an unowned consumer's pads.

    A body over an inner bus is not an electrical tap. Conversely, a foreign
    pad on that bus's layer, or a THT pad through it, cannot move on the
    strength of a net-name exemption. Check every pad, including same-net
    contacts, since relocating a physical tap changes the frozen topology.
    """
    import pcbnew
    regions = []
    for row in reservations(state):
        poly = pcbnew.SHAPE_POLY_SET(); poly.NewOutline()
        for x,y in ((row['x0'],row['y0']),(row['x1'],row['y0']),
                    (row['x1'],row['y1']),(row['x0'],row['y1'])):
            poly.Append(pcbnew.FromMM(x),pcbnew.FromMM(y))
        regions.append((copper_layer(board,row['layer']),poly,row['net']))
    hits = []
    for pad in footprint.Pads():
        for layer,shape,net in regions:
            if (pad.IsOnLayer(layer) and pad.GetEffectiveShape(layer).Collide(
                    shape, pcbnew.FromMM(clearance_mm))):
                hit = dict(pad=pad.GetPadName(),net=pad.GetNetname(),
                           power_net=net,layer=pcbnew.LayerName(layer))
                if hit not in hits: hits.append(hit)
        for via in state.get('vias') or ():
            if via.get('x_mm') is None or via.get('y_mm') is None:
                raise ValueError('incomplete frozen via authority')
            at=pcbnew.VECTOR2I_MM(via['x_mm'],via['y_mm'])
            radius=pcbnew.FromMM(max(.4,float(via.get('diameter_mm') or 0)/2))
            shape=pcbnew.SHAPE_CIRCLE(at,radius)
            if any(pad.GetEffectiveShape(int(layer)).Collide(
                    shape,pcbnew.FromMM(clearance_mm)) for layer in pad.GetLayerSet().CuStack()):
                hits.append(dict(pad=pad.GetPadName(),net=pad.GetNetname(),
                                 power_net=via.get('net'),kind='frozen_through_via'))
    return hits


@lru_cache(maxsize=8)
def _exact_rectangles(encoded):
    # Reuse the established exact Manhattan decomposition. This deliberately
    # preserves hook pockets, not a bounding-box approximation of each pour.
    import cec_synth_pipeline
    result=[]
    for pour in json.loads(encoded):
        if not pour.get('polygon') or not pour.get('net') or not pour.get('layer'):
            raise ValueError('incomplete frozen pour geometry')
        rects, approximate=cec_synth_pipeline._orthogonal_polygon_rectangles(pour['polygon'])
        if approximate or not rects:
            raise ValueError('frozen power is not an exact Manhattan polygon')
        for x0,y0,x1,y1 in rects:
            result.append((pour['net'],pour['layer'],x0,y0,x1,y1))
    return tuple(result)


def _retained_search_rows(state, rows, frozen, represented):
    """Retire only superseded raster halos after exact power admission.

    A successful complete solve owns its final polygons, not the dilation of
    the earlier raster search. Keep unknown/explicit reservations, other
    commodities, and every search row near a selected bridge barrel. This
    deliberately conservative last rule preserves future via territory even
    for old states that omitted explicit bridge-via reservation rows.
    """
    if ((state.get('exact_admission') or {}).get('passed') is not True
            or not frozen.issubset(represented)
            or not isinstance(state.get('vias'), list)):
        return rows
    import cec_slab_pour
    via_boxes = []
    for via in state['vias']:
        try:
            x, y = float(via['x_mm']), float(via['y_mm'])
            diameter = float(via.get('diameter_mm') or .9)
        except (KeyError, TypeError, ValueError):
            return rows
        if not all(math.isfinite(v) for v in (x, y, diameter)) or diameter <= 0:
            return rows
        # Use the existing field-reservation convention, including its
        # clearance, and never shrink the materializer's default diameter.
        via_boxes.extend(cec_slab_pour.bridge_via_reservations(
            [via], ['all'], diameter_mm=max(.9, diameter)))
    raster_keys = {'net', 'layer', 'polygon', 'x0', 'y0', 'x1', 'y1'}
    kept = []
    for row in rows:
        if row.get('net') not in frozen or not set(row).issubset(raster_keys):
            kept.append(row)
            continue
        try:
            x0, y0, x1, y1 = (float(row[k]) for k in ('x0', 'y0', 'x1', 'y1'))
        except (KeyError, TypeError, ValueError):
            kept.append(row)
            continue
        if (not all(math.isfinite(v) for v in (x0, y0, x1, y1))
                or x1 <= x0 or y1 <= y0
                or any(x0 <= v['x1'] and x1 >= v['x0']
                       and y0 <= v['y1'] and y1 >= v['y0'] for v in via_boxes)):
            kept.append(row)
    return kept


def solve_status(state):
    """Separate placement completeness from positively declared copper freeze.

    The producer's ``placement_scope`` describes the component population, not
    whether every power commodity was solved. A finite failed solve with no
    emitted/owned geometry may re-enter construction. An empty or contradictory
    purported freeze is still unknown and cannot acquire that permission.
    This status is not electrical, physical, or release qualification.
    """
    if not isinstance(state, dict):
        raise ValueError('power_state_mapping_required')
    if state.get('placement_scope') != 'complete':
        return dict(status='planning', frozen=False, deferred_nets=[], release_authority=False)
    frozen = state.get('frozen_nets') or []
    pours = state.get('pours') or []
    if (not isinstance(frozen, list)
            or any(not isinstance(net, str) or not net for net in frozen)
            or len(set(frozen)) != len(frozen)
            or not isinstance(pours, list)):
        raise ValueError('invalid_frozen_power_inventory')
    if frozen and pours:
        return dict(status='frozen', frozen=True, deferred_nets=[], release_authority=False)
    # A real frozen net, pour, barrel, pin exclusion, or successful admission
    # cannot be erased by appending a negative planner row. Those states still
    # need their owner's geometry, even if other commodities failed.
    exact_admission = state.get('exact_admission') or {}
    if not isinstance(exact_admission, dict):
        raise ValueError('invalid_power_solve_admission')
    if (frozen or pours or state.get('vias') or state.get('reserve_report')
            or state.get('exclude_pins') or exact_admission.get('passed') is True):
        raise ValueError('incomplete_nonempty_frozen_power_authority')
    report = state.get('report')
    if not isinstance(report, dict) or not report or len(report) > 128:
        raise ValueError('complete frozen power authority is empty')
    deferred = []
    for net, row in report.items():
        if not isinstance(net, str) or not net or not isinstance(row, dict):
            raise ValueError('invalid_power_solve_report')
        if (type(row.get('segments')) is not int or row['segments'] != 0
                or type(row.get('bridges')) is not int or row['bridges'] != 0
                or row.get('layers_used') != []):
            raise ValueError('unrepresented_power_solve_geometry')
        if row.get('path_found') is False and row.get('skipped') is not True:
            contract = row.get('current_contract')
            if (not isinstance(contract, dict)
                    or any(type(contract.get(k)) not in (int, float)
                           or not math.isfinite(contract[k]) or contract[k] <= 0
                           for k in ('amps', 'effective_A', 'margin'))
                    or not math.isclose(contract['effective_A'], contract['amps']*contract['margin'],
                                        rel_tol=1e-9, abs_tol=1e-9)
                    or not isinstance(contract.get('source'), str) or not contract['source']):
                raise ValueError('failed_power_solve_current_contract_unknown')
            deferred.append(net)
        elif not (row.get('path_found') is True and row.get('skipped') is True):
            raise ValueError('empty_freeze_without_positive_failed_solve')
    if not deferred:
        raise ValueError('empty_freeze_without_positive_failed_solve')
    return dict(status='deferred', frozen=False, deferred_nets=sorted(deferred),
                release_authority=False, power_qualified=False)


def _future_reservation_rows(state):
    """Retain declared future routes while repairing an unclosed power plan."""
    result = []
    values = state.get('future_owned_routes') or []
    if not isinstance(values, list) or len(values) > 4096:
        raise ValueError('bounded_future_route_inventory_required')
    for row in values:
        if (not isinstance(row, dict) or not isinstance(row.get('net'), str)
                or not row['net']):
            raise ValueError('invalid_future_route_reservation')
        layers = row['layers'] if 'layers' in row else [row.get('layer', 'F.Cu')]
        if (not isinstance(layers, list) or not layers
                or any(not isinstance(layer, str) or not layer for layer in layers)
                or any(type(row.get(k)) not in (int, float) or not math.isfinite(row[k])
                       for k in ('x0', 'x1', 'y0', 'y1'))
                or row['x1'] <= row['x0'] or row['y1'] <= row['y0']):
            raise ValueError('invalid_future_route_reservation_geometry')
        result.extend(dict(row, layer=layer, authority='unclosed_plan_future_route') for layer in layers)
    return result


def reservations(state):
    """Exact frozen copper plus still-owned planning and bridge reservations.

    Search corridors may be clipped around anticipated owned routes. Such
    holes do not cut the frozen pour itself and cannot authorize a new barrel
    or foreign track through it. Conversely, an obsolete raster halo is not
    physical copper after the complete exact solve. Anchor-only, unadmitted
    or incomplete legacy plans retain their conservative search semantics.
    """
    rows=[dict(row) for row in state.get('corridors') or ()]
    status = solve_status(state)
    if status['status'] == 'planning':
        return rows
    if status['status'] == 'deferred':
        # No frozen geometry was emitted by this failed solve. Keep its search
        # and future-route reservations; actual saved copper is independently
        # an obstacle. Never turn this construction permission into a freeze.
        return rows + _future_reservation_rows(state)
    frozen=set(state.get('frozen_nets') or ())
    pours=[{key:p.get(key) for key in ('net','layer','polygon')}
           for p in state.get('pours') or () if p.get('net') in frozen]
    if not frozen or not pours:
        raise ValueError('complete frozen power authority is empty')
    encoded=json.dumps(pours,sort_keys=True,separators=(',',':'))
    exact = _exact_rectangles(encoded)
    if frozen != {r[0] for r in exact}:
        raise ValueError('frozen_power_net_without_exact_polygon')
    rows = _retained_search_rows(state, rows, frozen, {r[0] for r in exact})
    for net,layer,x0,y0,x1,y1 in exact:
        rows.append(dict(net=net,layer=layer,x0=x0,y0=y0,x1=x1,y1=y1,
                         authority='exact_frozen_polygon'))
    return rows
