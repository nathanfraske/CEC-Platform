"""Finite full-width attachment points INSIDE actual native SMD copper.

These are route-start proposals, not vias, plane pickups, width exemptions or
electrical qualification. Native route guards and saved-board receiving still
own clearance and real terminal contact. No board/refdes/net/coordinate rule.
"""
import math
import time
import pcbnew
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
import cec_native_fill_geometry as native


def sites(pad, *, width_nm, toward_nm=None, max_sites=8, deadline=None):
    if (type(width_nm) is not int or not 0 < width_nm <= 20000000
            or type(max_sites) is not int or not 0 <= max_sites <= 16
            or toward_nm is not None and (len(toward_nm) != 2
                or any(type(v) is not int or abs(v) > 2000000000 for v in toward_nm))
            or deadline is not None and (type(deadline) not in (int, float)
                or not math.isfinite(deadline))):
        raise ValueError('bounded_native_pad_contact_domain_required')
    if (max_sites == 0 or pad.GetClass() != 'PAD' or pad.HasHole()
            or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
            or tuple(pad.GetOffset()) != (0, 0)
            or pad.GetShape() not in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_ROUNDRECT,
                                     pcbnew.PAD_SHAPE_CIRCLE, pcbnew.PAD_SHAPE_OVAL)):
        return []
    deadline = min(time.monotonic()+1., deadline) if deadline is not None else time.monotonic()+1.
    if time.monotonic() >= deadline: return []
    layers = tuple(map(int, pad.GetLayerSet().CuStack()))
    if len(layers) != 1: return []  # No invented plated/barrel access.
    shape = pcbnew.SHAPE_POLY_SET()
    pad.TransformShapeToPolygon(shape, layers[0], 0, 1, pcbnew.ERROR_OUTSIDE, False)
    polygons = native.snapshot(shape, deadline, max_vertices=4096, max_polygons=1)
    area = unary_union([Polygon(row[0], row[1:]) for row in polygons])
    if not area.is_valid or area.is_empty: return []
    radius = width_nm/2 + 2000  # Strict inset exceeds 1-nm polygon error.
    usable = area.buffer(-radius, quad_segs=64)
    if usable.is_empty: return []
    position = tuple(pad.GetPosition()); size = tuple(pad.GetSize())
    # Keep proposals off the numerical boundary of the eroded polygon too.
    # Equality there can vary with native roundrect tessellation/rotation.
    hx, hy = size[0]/2-radius-2000, size[1]/2-radius-2000
    if min(hx, hy) < 0: return []
    angle = math.radians(float(pad.GetOrientationDegrees()))
    ca, sa = math.cos(angle), math.sin(angle)
    local = {(sx*hx, 0.) for sx in (-1, 1)} | {(0., sy*hy) for sy in (-1, 1)}
    local |= {(sx*hx, sy*hy) for sx in (-1, 1) for sy in (-1, 1)}
    if toward_nm is not None:
        dx, dy = toward_nm[0]-position[0], toward_nm[1]-position[1]
        x, y = dx*ca+dy*sa, -dx*sa+dy*ca
        local.add((max(-hx, min(hx, x)), max(-hy, min(hy, y))))
    result = set()
    for x, y in local:
        if time.monotonic() >= deadline: break
        point = (round(position[0]+x*ca-y*sa), round(position[1]+x*sa+y*ca))
        if point != position and usable.covers(Point(point)):
            result.add(point)
    target = tuple(toward_nm) if toward_nm is not None else position
    return sorted(result, key=lambda q:(math.dist(q, target), q))[:max_sites]
