"""Measure real saved copper changes, not counts of deleted CAD objects.

An overlapping track can keep an entire removed zone physically occupied.
Bracket the net's UNION of filled islands, pads and track capsules, subtract
actual drills, then compare both saved boards. This is a geometric witness,
not a route, clearance, current-sharing, thermal or release qualification.
"""
import math
import time

import cec_kelvin_copper_cut as physical
import cec_board_geometry as geometry


def _material(board, net, layer, deadline):
    from shapely.geometry import GeometryCollection
    from shapely.ops import unary_union
    work = physical._Work(deadline)
    pads, tracks, zones, enabled = physical._inventory(board, work)
    if layer not in enabled:
        raise ValueError('actual_enabled_native_copper_face_required')
    items = [i for i in pads + tracks if str(i.GetNetname()) == net and i.IsOnLayer(layer)]
    poured = [z for z in zones if str(z.GetNetname()) == net and z.IsOnLayer(layer)]
    if len(items) + len(poured) > physical.MAX_NET_ITEMS:
        raise ValueError('native_net_material_delta_item_budget')
    if not items and not poured:
        return {False: GeometryCollection(), True: GeometryCollection()}, dict(items=0, zones=0)
    # Never share a _Work geometry cache between parent and child. UUIDs,
    # net names and start positions can survive an edited track end or zone.
    shapes = {upper: [physical._shape(i, layer, upper, work) for i in items]
              + [physical._filled_shape(z, layer, upper, work) for z in poured]
              for upper in (False, True)}
    drilled = [i for i in pads + tracks if i.GetClass() == 'PCB_VIA' and i.IsOnLayer(layer)
               or i.GetClass() == 'PAD' and i.HasHole()]
    holes = {upper: unary_union([physical._hole(i, upper, work) for i in drilled])
             for upper in (False, True)}
    substrate = physical._poly(geometry.outline_material(board), work)
    bounds = {upper: unary_union(shapes[upper]).difference(holes[not upper]).intersection(
                  physical._envelope(substrate, upper))
              for upper in (False, True)}
    physical._validate_linear_epochs(work)
    if any(not s.is_valid for s in bounds.values()) or not bounds[True].covers(bounds[False]):
        raise ValueError('native_material_delta_bounds_not_nested')
    return bounds, dict(items=len(items), zones=len(poured), actual_drills=len(drilled))


def compare(source, candidate, *, net, layer_ids, timeout_s=10., probe_diameter_mm=None):
    """Read-only conservative area bounds on explicit saved net/face material.

    A positive probe only proves a local disk fits in definitely removed
    copper. It never proves a usable end-to-end routing corridor. Missing,
    invalid, unfilled, timed-out or non-nested geometry is incomplete.
    """
    result = dict(schema=1, scope='saved_native_net_union_material_delta',
        ok=False, complete=False, errors=[], faces=[], board_mutated=False,
        object_count_is_freed_space_evidence=False, routing_corridor_qualified=False,
        actual_native_substrate_clipped=True,
        current_qualified=False, release_authority=False)
    try:
        if (type(net) is not str or not net or type(layer_ids) not in (list, tuple)
                or not 1 <= len(layer_ids) <= 6 or len(set(layer_ids)) != len(layer_ids)
                or any(type(l) is not int for l in layer_ids)
                or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
                or not 0 < timeout_s <= 10.
                or probe_diameter_mm is not None and (type(probe_diameter_mm) not in (int, float)
                    or not math.isfinite(probe_diameter_mm) or not 0 < probe_diameter_mm <= 128.)):
            raise ValueError('bounded_explicit_native_material_delta_scope_required')
        if (tuple(source.GetEnabledLayers().CuStack()) != tuple(candidate.GetEnabledLayers().CuStack())
                or source.GetNetcodeFromNetname(net) <= 0 or candidate.GetNetcodeFromNetname(net) <= 0):
            raise ValueError('same_native_copper_stack_and_existing_net_required')
        deadline = time.monotonic() + timeout_s
        for layer in layer_ids:
            old, before = _material(source, net, layer, deadline)
            new, after = _material(candidate, net, layer, deadline)
            removed = {False: old[False].difference(new[True]),
                       True: old[True].difference(new[False])}
            added = {False: new[False].difference(old[True]),
                     True: new[True].difference(old[False])}
            row = dict(layer_id=layer, layer=source.GetLayerName(layer), net=net,
                before_inventory=before, after_inventory=after,
                before_copper_area_lower_mm2=old[False].area / 1e12,
                after_copper_area_lower_mm2=new[False].area / 1e12,
                definitely_removed_area_mm2=removed[False].area / 1e12,
                possibly_removed_area_mm2=removed[True].area / 1e12,
                definitely_added_area_mm2=added[False].area / 1e12,
                possibly_added_area_mm2=added[True].area / 1e12,
                definitely_removed_bounds_mm=([v / 1e6 for v in removed[False].bounds]
                    if not removed[False].is_empty else None),
                routing_corridor_qualified=False)
            if probe_diameter_mm is not None:
                row.update(probe_diameter_mm=float(probe_diameter_mm),
                    removed_material_contains_local_probe=not removed[False].buffer(
                        -probe_diameter_mm * 5e5).is_empty)
            if time.monotonic() >= deadline:
                raise physical.Unknown('native_material_delta_deadline')
            result['faces'].append(row)
        result.update(ok=True, complete=True)
    except (ValueError, TypeError, KeyError, IndexError, physical.Unknown) as exc:
        result['errors'].append(type(exc).__name__ + ':' + str(exc))
    return result
