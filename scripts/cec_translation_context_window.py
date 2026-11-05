"""Conservative spatial reduction for bounded rigid-translation proposals.

This discards only fixed shapes outside EVERY swept member bounding box,
including the explicit clearance. Roles, layers, mating allowances and exact
collision/admission decisions remain with the caller and independent receivers.
No geometry or source identity is changed, and touching bounds are retained.
"""
import math
import time


def relevant_fixed(groups, fixed, *, clearance=0., timeout_s=10.):
    if (type(groups) is not dict or not 1 <= len(groups) <= 64
            or type(clearance) not in (int, float) or not math.isfinite(clearance)
            or not 0 <= clearance <= 100
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('bounded_translation_context_window_required')
    deadline = time.monotonic() + timeout_s
    fixed = list(fixed)
    if len(fixed) > 32768:
        raise ValueError('translation_window_input_inventory_bound')
    def bounds(member):
        if time.monotonic() >= deadline:
            raise ValueError('translation_context_window_deadline')
        if not isinstance(member, dict) or 'geometry' not in member:
            raise ValueError('valid_translation_window_member_required')
        g = member['geometry']
        if (g.is_empty or not g.is_valid or g.geom_type not in ('Polygon', 'MultiPolygon')
                or g.area <= 0 or not all(math.isfinite(v) for v in g.bounds)):
            raise ValueError('valid_translation_window_geometry_required')
        return g.bounds
    swept = []
    for row in groups.values():
        if not isinstance(row, dict) or not isinstance(row.get('members'), (list, tuple)):
            raise ValueError('explicit_translation_window_members_required')
        delta = row.get('bounds')
        if (not isinstance(delta, (list, tuple)) or len(delta) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in delta)
                or delta[0] > delta[2] or delta[1] > delta[3]
                or not row['members']):
            raise ValueError('finite_ordered_translation_window_required')
        for member in row['members']:
            x0, y0, x1, y1 = bounds(member)
            swept.append((x0+delta[0]-clearance, y0+delta[1]-clearance,
                          x1+delta[2]+clearance, y1+delta[3]+clearance))
            if len(swept) > 4096:
                raise ValueError('translation_window_moving_inventory_bound')
    kept = []
    for member in fixed:
        x0, y0, x1, y1 = bounds(member)
        if any(not (x1 < a or x0 > c or y1 < b or y0 > d) for a, b, c, d in swept):
            kept.append(member)
        if time.monotonic() >= deadline:
            raise ValueError('translation_context_window_deadline')
    return kept, dict(schema=1, input_fixed_members=len(fixed), retained_fixed_members=len(kept),
        excluded_fixed_members=len(fixed)-len(kept), swept_member_bounds_mm=[list(b) for b in swept],
        clearance_mm=clearance, roles_or_layers_not_exempted=True, boundary_touch_retained=True,
        source_geometry_changed=False, exact_native_receiving_required=True, admission_authority=False)
