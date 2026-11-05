"""Explain changed native DRC representatives without waiving a single fault.

Connecting an existing island can change which item pair KiCad reports for a
short cluster. This finite, read-only diagnostic checks the actual two native
conductors in both boards. Its evidence does not alter stage admission, retire
DRC identities, qualify inherited debt, or grant reconstruction authority.
"""
import math
import time

import pcbnew


def explain_changed_identities(before, after, violations, new_identities, *,
                               netclass_resolver, rule_authority_unchanged,
                               timeout_s=2.):
    """Bound the whole reporting batch; preserve every strict gate identity."""
    import cec_stage_admission as stage
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or not callable(netclass_resolver)
            or not isinstance(new_identities, (list, tuple, set, frozenset))
            or len(new_identities) > 64
            or any(type(uid) is not str for uid in new_identities)
            or not isinstance(violations, (list, tuple)) or len(violations) > 16384):
        raise ValueError('bounded_native_fault_reporting_batch_required')
    deadline = time.monotonic()+timeout_s
    result = dict(rows=[], admission_unchanged=True, faults_suppressed=0,
        release_authority=False,
        clearance_scope='resolved_netclass_and_native_minimum_not_custom_DRC_rule_qualification')
    inventory = _inventory(after, deadline)
    requested = set(new_identities)
    rows = [v for v in violations if stage._canonical_identity(v) in requested]
    for row in rows[:64]:
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            result.setdefault('errors', []).append('native_fault_reporting_batch_deadline')
            break
        names = [inventory[u['uuid']].GetNetname() for u in row.get('items', ())
                 if u.get('uuid') in inventory]
        gap = max([int(before.GetDesignSettings().m_MinClearance),
                   *(math.ceil(float((netclass_resolver(n) or {}).get('clearance') or 0)*1e6)
                     for n in names)])
        proof = explain(before, after, [row], clearance_nm=gap,
            rule_authority_unchanged=rule_authority_unchanged,
            timeout_s=min(.5, remaining))
        result['rows'].extend(proof['rows'])
        if proof['errors']:
            result.setdefault('errors', []).extend(proof['errors'])
    result['unexplained_count'] = max(0, len(requested)-len(result['rows']))
    return result


def _inventory(board, deadline):
    result = {}
    for item in [*board.GetTracks(),
                 *(pad for fp in board.GetFootprints() for pad in fp.Pads())]:
        if time.monotonic() >= deadline:
            raise ValueError('native_fault_lineage_deadline')
        uid = str(item.m_Uuid.AsString())
        if uid in result or len(result) >= 8192:
            raise ValueError('bounded_unambiguous_native_item_inventory_required')
        result[uid] = item
    return result


def _geometry(item, layers):
    kind = item.GetClass()
    if kind not in {'PAD', 'PCB_TRACK', 'PCB_VIA'}:
        raise ValueError('native_fault_lineage_unsupported_conductor')
    faces = [layer for layer in layers if item.IsOnLayer(layer)]
    polys = []
    for layer in faces:
        poly = pcbnew.SHAPE_POLY_SET()
        item.TransformShapeToPolygon(poly, layer, 0, 10, pcbnew.ERROR_INSIDE)
        if poly.OutlineCount() > 8 or poly.FullPointCount() > 4096:
            raise ValueError('native_fault_lineage_polygon_bound')
        polys.append((layer, poly.Format()))
    holes = (tuple(item.GetDrillSize()) if kind == 'PAD' else
             item.GetDrillValue() if kind == 'PCB_VIA' else None)
    return kind, str(item.GetNetname()), tuple(faces), holes, tuple(polys)


def explain(before, after, violations, *, clearance_nm,
            rule_authority_unchanged=False, timeout_s=2.):
    """Return source witnesses, never permission to suppress changed fault IDs.

    The explicit clearance is the caller's resolved rule, not text parsed from
    a DRC message. Unknown/custom rule authority, unsupported conductors,
    incomplete pairs and missing native geometry remain unknown. Every new
    fault retains its blocking status, including proved inherited geometry.
    """
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10 or type(clearance_nm) is not int
            or not 0 <= clearance_nm <= 2000000
            or type(rule_authority_unchanged) is not bool
            or not isinstance(violations, (list, tuple)) or len(violations) > 64):
        raise ValueError('bounded_explicit_native_fault_lineage_required')
    result = dict(schema=1, complete=False, rows=[], errors=[],
        admission_unchanged=True, faults_suppressed=0,
        inherited_debt_qualified=False, release_authority=False)
    deadline = time.monotonic() + timeout_s
    try:
        if not rule_authority_unchanged:
            raise ValueError('source_and_candidate_rule_authority_not_proved_exact')
        layers = tuple(map(int, before.GetEnabledLayers().CuStack()))
        if layers != tuple(map(int, after.GetEnabledLayers().CuStack())):
            raise ValueError('native_copper_stack_changed')
        inventories = [_inventory(b, deadline) for b in (before, after)]
        for violation in violations:
            if time.monotonic() >= deadline:
                raise ValueError('native_fault_lineage_deadline')
            ids = [str(row.get('uuid') or '') for row in violation.get('items', ())]
            row = dict(type=violation.get('type'), item_uuids=ids,
                       classification='unknown', remains_blocking=True)
            result['rows'].append(row)
            if (row['type'] not in {'clearance', 'shorting_items'}
                    or len(ids) != 2 or len(set(ids)) != 2 or not all(ids)):
                row['reason'] = 'exact_supported_native_copper_pair_required'
                continue
            if any(uid not in inventory for inventory in inventories for uid in ids):
                row['reason'] = 'new_or_missing_native_conductor'
                continue
            pair_before, pair_after = [[inventory[uid] for uid in ids]
                                       for inventory in inventories]
            try:
                exact = all(_geometry(a, layers) == _geometry(b, layers)
                            for a, b in zip(pair_before, pair_after))
            except ValueError as exc:
                row['reason'] = str(exc)
                continue
            row['native_pair_geometry_exact'] = exact
            if not exact:
                row['reason'] = 'conductor_geometry_net_or_drill_changed'
                continue
            a, b = pair_before
            if a.GetNetCode() <= 0 or b.GetNetCode() <= 0 or a.GetNetname() == b.GetNetname():
                row['reason'] = 'distinct_assigned_native_nets_required'
                continue
            gap = 0 if row['type'] == 'shorting_items' else clearance_nm
            witnesses = [layer for layer in layers if a.IsOnLayer(layer)
                         and b.IsOnLayer(layer)
                         and a.GetEffectiveShape(layer).Collide(b.GetEffectiveShape(layer), gap)]
            row['source_native_collision_layers'] = witnesses
            row['resolved_clearance_nm'] = gap
            if witnesses:
                row['classification'] = 'unchanged_source_pair_with_native_collision'
                row['reason'] = 'changed_DRC_representative_is_not_geometry_repair'
            else:
                row['reason'] = 'source_native_collision_not_witnessed'
        result['complete'] = True
    except (ValueError, RuntimeError) as exc:
        result['errors'].append(str(exc))
    return result
