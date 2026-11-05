"""Finite placement-search distances derived from the candidate's domain.

These bounds restrict proposal generation, not electrical or mechanical
admission. A configured cap can narrow the domain but cannot enlarge it.
"""
import math


def axis_exits_from_copper_union(point, *, rectangles=(), capsules=(), envelope=0.0):
    """Minimal axial exits from native track/via capsules and guard boxes.

    A diagonal track's bounding box invents blocked space near its corners.
    Intersect the actual rounded conductor envelope with each search line,
    then merge intervals before choosing an exit. The endpoint is proposal
    geometry only: pads, zones, lead access and final native DRC still apply.
    Capsule rows are ``(start_xy, end_xy, copper_radius_mm)``; a via is a
    zero-length capsule. All coordinates and policy must be finite.
    """
    x, y = map(float, point)
    margin = float(envelope)
    if not all(math.isfinite(v) for v in (x, y, margin)) or margin < 0:
        raise ValueError('copper exit requires finite geometry and nonnegative envelope')
    boxes = []
    for rect in rectangles:
        x0, y0, x1, y1 = map(float, rect)
        if not all(math.isfinite(v) for v in (x0, y0, x1, y1)) or x0 >= x1 or y0 >= y1:
            raise ValueError('copper exit requires nonempty finite rectangles')
        boxes.append((x0-margin, y0-margin, x1+margin, y1+margin))
    shapes = []
    for start, end, radius in capsules:
        a, b = tuple(map(float, start)), tuple(map(float, end))
        r = float(radius)
        if (len(a) != 2 or len(b) != 2 or r <= 0
                or not all(math.isfinite(v) for v in (*a, *b, r))):
            raise ValueError('copper exit requires finite capsules with positive radius')
        shapes.append((a, b, r+margin))

    def capsule_intervals(a, b, r, fixed, axis):
        # Swap axes for the vertical case; solve along the variable coordinate.
        k = 1-axis
        ax, ay, bx, by = a[axis], a[k], b[axis], b[k]
        rows = []
        for cx, cy in ((ax, ay), (bx, by)):
            dy = fixed-cy
            if abs(dy) < r:
                extent = math.sqrt(max(0.0, r*r-dy*dy))
                rows.append((cx-extent, cx+extent))
        length = math.hypot(bx-ax, by-ay)
        if length:
            ux, uy = (bx-ax)/length, (by-ay)/length
            lo, hi = -math.inf, math.inf
            # Rectangular centre strip: 0 <= tangent <= L; |normal| <= r.
            for slope, offset, lower, upper in (
                    (ux, uy*(fixed-ay)-ux*ax, 0.0, length),
                    (-uy, ux*(fixed-ay)+uy*ax, -r, r)):
                if abs(slope) < 1e-15:
                    if not lower < offset < upper:
                        break
                else:
                    first, last = sorted(((lower-offset)/slope, (upper-offset)/slope))
                    lo, hi = max(lo, first), min(hi, last)
            else:
                if lo < hi:
                    rows.append((lo, hi))
        return rows

    def component(intervals, value):
        merged = []
        for lo, hi in sorted(intervals):
            if merged and lo <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        return next(((lo, hi) for lo, hi in merged if lo < value < hi), None)

    horizontal = [(a, c) for a, b, c, d in boxes if b < y < d]
    vertical = [(b, d) for a, b, c, d in boxes if a < x < c]
    for a, b, r in shapes:
        horizontal.extend(capsule_intervals(a, b, r, y, 0))
        vertical.extend(capsule_intervals(a, b, r, x, 1))
    h, v = component(horizontal, x), component(vertical, y)
    if h is None and v is None:
        return [(0.0, 0.0)]
    if h is None or v is None:
        raise ValueError('inconsistent copper line intersection')
    return [(h[0]-x, 0.0), (h[1]-x, 0.0), (0.0, v[0]-y), (0.0, v[1]-y)]


def axis_exits_from_rect_union(point, rectangles, envelope=0.0):
    """Minimal axial translations outside a union of inflated rectangles.

    Leaving one raster tile can put a proposed via inside its neighbouring
    tile. Merge the intervals along each axis before selecting an exit. These
    are proposal endpoints, not clearance proof for the cell or swept path.
    """
    x, y = map(float, point)
    margin = float(envelope)
    if not all(math.isfinite(v) for v in (x, y, margin)) or margin < 0:
        raise ValueError('union exit requires finite geometry and nonnegative envelope')
    boxes = []
    for rect in rectangles:
        x0, y0, x1, y1 = map(float, rect)
        if not all(math.isfinite(v) for v in (x0, y0, x1, y1)) or x0 >= x1 or y0 >= y1:
            raise ValueError('union exit requires nonempty finite rectangles')
        boxes.append((x0-margin, y0-margin, x1+margin, y1+margin))
    if not any(x0 < x < x1 and y0 < y < y1 for x0, y0, x1, y1 in boxes):
        return [(0.0, 0.0)]

    def component(intervals, value):
        merged = []
        for lo, hi in sorted(intervals):
            if merged and lo <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
            else:
                merged.append((lo, hi))
        return next((lo, hi) for lo, hi in merged if lo < value < hi)

    left, right = component([(x0, x1) for x0, y0, x1, y1 in boxes
                             if y0 < y < y1], x)
    top, bottom = component([(y0, y1) for x0, y0, x1, y1 in boxes
                             if x0 < x < x1], y)
    return [(left-x, 0.0), (right-x, 0.0), (0.0, top-y), (0.0, bottom-y)]


def rotate_board_point(point, origin, degrees):
    """Rotate a point with KiCad's positive-angle, downward-Y convention."""
    x, y = map(float, point)
    ox, oy = map(float, origin)
    angle = float(degrees)
    if not all(math.isfinite(value) for value in (x, y, ox, oy, angle)):
        raise ValueError('cell transform requires finite geometry')
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return (ox + cosine * (x-ox) + sine * (y-oy),
            oy - sine * (x-ox) + cosine * (y-oy))


def rigid_cell_transform(placements, root, degrees, offset=(0.0, 0.0)):
    """Transform every member pose about the owner, preserving local geometry.

    The caller supplies the complete cell and checks fixed members and copper
    ownership. This only proposes poses: it never moves copper or grants a
    placement/route admission. All footprint orientations rotate, including
    bypass followers; translating an unrotated follower breaks its pin vector.
    """
    origin = placements[root][:2]
    dx, dy = map(float, offset)
    if not all(math.isfinite(value) for value in (dx, dy)):
        raise ValueError('cell transform requires finite translation')
    result = {}
    for ref, pose in placements.items():
        x, y = rotate_board_point(pose[:2], origin, degrees)
        orientation = float(pose[2])
        if not math.isfinite(orientation):
            raise ValueError('cell transform requires finite orientation')
        result[ref] = (x + dx, y + dy, (orientation + float(degrees)) % 360.0)
    return result


def relocation_radius(candidate, params, key):
    """Any two in-outline centres are at most one bounding-box diagonal apart.

    A constant local step cap incorrectly suppresses measured, longer-range
    endpoint relocations. Invalid or absent dimensions fail closed. The exact
    materialized outline, full cell, and retained copper checks still decide
    whether any proposed pose is feasible.
    """
    try:
        width, height = float(candidate.W), float(candidate.H)
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            return 0.0
        diagonal = math.hypot(width, height)
        if not math.isfinite(diagonal):
            return 0.0
        if key not in (params or {}):
            return diagonal
        cap = float(params[key])
        return min(cap, diagonal) if math.isfinite(cap) and cap >= 0 else 0.0
    except (AttributeError, TypeError, ValueError, OverflowError):
        return 0.0
