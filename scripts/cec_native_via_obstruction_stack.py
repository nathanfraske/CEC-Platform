"""Bounded read-only copper-layer causes, never through-via admission.

The ordinary via guard deliberately fails fast. Its first F.Cu obstruction
is not the complete set of obstacles to a through hole. This diagnostic
queries every enabled face without deleting the first blocker. Fabrication,
pad/assembly exclusion, drills, reservations and returns remain independent
guards; an empty layer stack is explicitly NOT permission to place a via.
"""
import math
import time
import pcbnew
import cec_fr as fr


def inspect(board, at, diameter_nm, clearance_nm, net_code, *, timeout_s=1.,
            max_blockers_per_layer=64, shape_cache=None):
    result = dict(complete=False, layers=[], errors=[],
        scope='all_enabled_native_foreign_copper_layers_only',
        all_guard_categories_complete=False, via_admitted=False,
        empty_layer_stack_is_not_via_clearance_or_process_authority=True)
    try:
        if (type(diameter_nm) is not int or not 0 < diameter_nm <= 10000000
                or type(clearance_nm) is not int or not 0 <= clearance_nm <= 10000000
                or type(net_code) is not int or net_code <= 0
                or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not 0 < timeout_s <= 5.
                or type(max_blockers_per_layer) is not int or not 1 <= max_blockers_per_layer <= 128):
            raise ValueError('bounded_native_via_layer_diagnostic_required')
        deadline = time.monotonic()+timeout_s
        faces = list(board.GetEnabledLayers().CuStack())
        if not 1 <= len(faces) <= 32:
            raise ValueError('bounded_enabled_native_copper_layers_required')
        if sum(1 for fp in board.GetFootprints() for p in fp.Pads())+len(list(board.GetTracks())) > 16384:
            raise ValueError('native_via_layer_material_inventory_bound')
        cache = {} if shape_cache is None else shape_cache
        circle = pcbnew.SHAPE_CIRCLE(at, diameter_nm//2)
        for face in faces:
            row = dict(layer_id=int(face), layer=board.GetLayerName(face), complete=False, blockers=[], truncated=False)
            result['layers'].append(row)
            if time.monotonic() >= deadline:
                row['error'] = 'native_via_layer_diagnostic_deadline'
                continue
            try:
                key = ('via_layer_failure_stack', int(face), int(net_code))
                if key not in cache:
                    # The optional cache belongs exclusively to an immutable
                    # read-only caller transaction, never a routing mutation.
                    unknown=[]
                    # The fast snapshot historically skips a few unsupported
                    # pad/graphic adapters. That is not a complete diagnostic
                    # inventory: audit those native shapes independently.
                    items=[p for fp in board.GetFootprints() for p in fp.Pads()]
                    items+=list(board.GetTracks())
                    items+=[g for fp in board.GetFootprints() for g in fp.GraphicalItems()]
                    for item in items:
                        try:
                            is_graphic=not hasattr(item,'GetNetCode')
                            if not item.IsOnLayer(face) or not is_graphic and item.GetNetCode()==net_code:
                                continue
                            shape=item.GetEffectiveShape() if is_graphic else item.GetEffectiveShape(face)
                            if shape is None:raise ValueError('native_shape_missing')
                            shape.BBox()
                        except Exception as exc:
                            try:uid=item.m_Uuid.AsString()
                            except Exception:uid=None
                            unknown.append(dict(uuid=uid,error_type=type(exc).__name__))
                    cache[key] = (fr._identified_foreign_shape_indexes(board, face, {net_code}),unknown)
                (zones, copper), unknown = cache[key]
                hits = fr._snapshot_foreign_blockers(at, at, diameter_nm, clearance_nm,
                    zones, copper, limit=max_blockers_per_layer+1, _native_shape=circle)
                row['truncated'] = len(hits) > max_blockers_per_layer
                row['blockers'] = hits[:max_blockers_per_layer]
                row['unknown_native_shapes']=unknown[:128]
                row['complete'] = not unknown and not row['truncated'] and not any(
                    h.get('contact') == 'geometry_unknown' or h.get('native_identity_unavailable') for h in hits)
            except Exception as exc:
                row['error'] = type(exc).__name__+':'+str(exc)
        result['complete'] = len(result['layers']) == len(faces) and all(r['complete'] for r in result['layers'])
        result['queried_enabled_copper_layers'] = [r['layer'] for r in result['layers'] if r['complete']]
        result['distinct_copper_blocker_uuids'] = sorted({h['uuid'] for r in result['layers'] for h in r['blockers'] if h.get('uuid')})
        result['first_layer_only_is_not_a_sole_blocker_proof'] = True
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def enrich_pair_refusal(board, pair, result, *, max_fields=2, timeout_s=1.):
    """Attach a bounded parent-state stack after the route has rolled back.

    Only sampled failed transition fields are covered, not the full search
    domain or the temporary failed fan-in geometry. This does not rerun the
    search or alter a refusal, successful route, board, or admission predicate.
    """
    if not result.get('refused'):
        return
    portal = result.get('portal_evidence')
    if not isinstance(portal, dict):
        return
    geometry = portal.get('signal_via') or {}
    if type(geometry.get('diameter_mm')) not in (int, float):
        return
    try:
        if type(max_fields) is not int or not 1 <= max_fields <= 4 or not 0 < timeout_s <= 2.:
            raise ValueError('bounded_pair_refusal_layer_diagnostic_required')
        candidates, seen = [], set()
        for label, screen in (portal.get('screened') or {}).items():
            for witness in [*(screen.get('reason_diverse_rejected') or ()), *(screen.get('nearest_rejected') or ())]:
                transition = witness.get('transition') or {}
                row = witness.get('portal') or {}
                if not transition or not row.get('p') or not row.get('n'):
                    continue
                points = tuple(tuple(float(v) for v in row[k]) for k in ('p', 'n'))
                if any(len(p) != 2 or any(not math.isfinite(v) for v in p) for p in points):
                    continue
                if points in seen:
                    continue
                seen.add(points)
                candidates.append(dict(label=label, points=points, first_guard_failure=transition))
                break
        if not candidates:
            return
        r = dict(complete=True, scope='sampled_failed_fields_on_rolled_back_native_parent', fields=[],
            sampled_fields_only=True, full_search_domain_not_claimed=True,
            first_guard_failure_is_not_a_sole_blocker_proof=True,
            factory_drill_return_and_retirement_authority_not_granted=True)
        portal['matched_transition_native_failure_stacks'] = r
        deadline = time.monotonic()+timeout_s
        cache = {}
        for candidate in candidates[:max_fields]:
            member_rows = []
            for key, point in zip(('p', 'n'), candidate['points']):
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    member_rows.append(dict(member=key, complete=False, error='layer_stack_diagnostic_budget_exhausted'))
                    continue
                code = board.GetNetcodeFromNetname(pair[key])
                proof = inspect(board, pcbnew.VECTOR2I_MM(*point), round(geometry['diameter_mm']*1e6),
                    round(float(pair['clearance'])*1e6), int(code), timeout_s=min(1., remaining), shape_cache=cache)
                member_rows.append(dict(member=key, point_mm=point, complete=proof['complete'], stack=proof))
            r['fields'].append(dict(label=candidate['label'], first_guard_failure=candidate['first_guard_failure'],
                                    members=member_rows))
        r['complete'] = all(m['complete'] for field in r['fields'] for m in field['members'])
        r['sample_count'] = len(r['fields'])
    except Exception as exc:
        portal['matched_transition_native_failure_stacks'] = dict(complete=False,
            error=type(exc).__name__+':'+str(exc), diagnostic_only=True)
