"""Bounded additive covers for shallow, possibly wide 0/45-degree pockets.

Search size is normal displacement, not only the length of a notch's mouth.
Floating geometry proposes a shape; integer native zero-loss and full saved
manufacturing/current/Kelvin receiving remain independent requirements.
"""
import time
from shapely.geometry import LineString, Polygon
import cec_rectilinear_copper as native


def compact(points):
    points = [list(p) for p in points]
    if points and points[0] == points[-1]: points.pop()
    for _ in range(len(points)):
        keep = []
        for i, b in enumerate(points):
            a, c = points[i-1], points[(i+1) % len(points)]
            u = [b[k]-a[k] for k in (0, 1)]; v = [c[k]-b[k] for k in (0, 1)]
            if u[0]*v[1] == u[1]*v[0] and sum(u[k]*v[k] for k in (0, 1)) > 0: continue
            keep.append(b)
        if len(keep) == len(points): break
        points = keep
    return points


def candidates(points, *, minimum_depth_nm=50000, maximum_depth_nm=500000,
        maximum_span_nm=4000000, maximum_window_edges=8, timeout_s=5.):
    if (any(type(v) is not int for v in (minimum_depth_nm, maximum_depth_nm, maximum_span_nm, maximum_window_edges))
            or not 1 <= minimum_depth_nm <= maximum_depth_nm <= 1000000
            or not maximum_depth_nm <= maximum_span_nm <= 8000000
            or not 3 <= maximum_window_edges <= 8 or not 0 < timeout_s <= 10.):
        raise ValueError('finite_shallow_pocket_proposal_domain_required')
    ring = compact(points)
    if (not 4 <= len(ring) <= 256 or any(len(p) != 2 or any(type(v) is not int for v in p) for p in ring)
            or not all(native._centerline_allowed(a, z, 'chamfer45') for a, z in zip(ring, ring[1:]+ring[:1]))):
        raise ValueError('simple_bounded_literal_octilinear_source_outline_required')
    source = Polygon(ring)
    if not source.is_valid or source.interiors or source.area <= 0:
        raise ValueError('valid_single_source_copper_outline_required')
    deadline = time.monotonic()+timeout_s
    results = []; seen = set()
    def cross(a, b): return a[0]*b[1]-a[1]*b[0]
    for i in range(len(ring)):
        for edges in range(3, min(maximum_window_edges, len(ring)-2)+1):
            native._check_deadline(deadline)
            rotated = ring[i:]+ring[:i]
            chain = rotated[:edges+1]; a, z = chain[0], chain[-1]
            extent = max(max(p[k] for p in chain)-min(p[k] for p in chain) for k in (0, 1))
            if extent > maximum_span_nm: continue
            options = [[], [[a[0], z[1]]], [[z[0], a[1]]]]
            previous, following = ring[i-1], rotated[edges+1]
            u = [a[k]-previous[k] for k in (0, 1)]; v = [following[k]-z[k] for k in (0, 1)]
            det = cross(u, v)
            if det:
                num = cross([z[k]-a[k] for k in (0, 1)], v)
                coords = [a[k]*det+u[k]*num for k in (0, 1)]
                if all(q % det == 0 for q in coords): options.append([[q//det for q in coords]])
            for middle in options:
                path = [a, *middle, z]
                if any(a == b or not native._centerline_allowed(a, b, 'chamfer45') for a, b in zip(path, path[1:])): continue
                depth = LineString(chain).hausdorff_distance(LineString(path))
                if not minimum_depth_nm <= depth <= maximum_depth_nm: continue
                trial = compact([a, *middle, z, *rotated[edges+1:]])
                key = tuple(map(tuple, trial))
                if key in seen or len(trial) >= len(ring) or len(trial) < 4: continue
                seen.add(key)
                candidate = Polygon(trial); area = candidate.area-source.area
                if (not candidate.is_valid or candidate.interiors or not candidate.covers(source)
                        or not 0 < area <= maximum_depth_nm*maximum_span_nm): continue
                lost = native._poly(ring); lost.BooleanSubtract(native._poly(trial))
                if lost.OutlineCount(): continue
                results.append(dict(source_points_nm=ring, points_nm=trial,
                    source_window_nm=chain, replacement_path_nm=path,
                    maximum_normal_displacement_nm=depth, added_area_nm2=area,
                    original_vertices=len(ring), replacement_vertices=len(trial),
                    native_source_polygon_loss_outlines=0, numeric_or_area_waiver_used=False,
                    proposal_only_not_current_or_release_authority=True))
    return sorted(results, key=lambda row: (row['added_area_nm2'], row['replacement_vertices'], row['points_nm']))
