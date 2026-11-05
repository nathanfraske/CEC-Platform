"""Finite directional constraints on a bounded placement proposal domain.

Halfplanes are (nx, ny, offset), meaning n dot translation >= offset.
These utilities neither prove routing feasibility nor alter route admission.
"""
import math


def normalized(rows):
    result = []
    for row in rows:
        values = tuple(map(float, row))
        if len(values) != 3 or not all(math.isfinite(v) for v in values):
            raise ValueError('finite translation halfplanes required')
        x, y, offset = values
        norm = math.hypot(x, y)
        if not math.isfinite(norm) or norm <= 1e-12:
            raise ValueError('nonzero halfplane normal required')
        plane = (x/norm, y/norm, offset/norm)
        if not all(math.isfinite(v) for v in plane):
            raise ValueError('finite normalized halfplanes required')
        result.append(plane)
    return tuple(result)


def contains(point, planes, tolerance=1e-8):
    return all(x*point[0]+y*point[1] >= offset-tolerance
               for x, y, offset in planes)


def clip_rectangle(bounds, planes):
    """Clip the actual bounded rectangle, without inventing a huge work area."""
    x0, y0, x1, y1 = bounds
    polygon = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for nx, ny, offset in planes:
        clipped = []
        for index, end in enumerate(polygon):
            start = polygon[index-1]
            a = nx*start[0]+ny*start[1]-offset
            b = nx*end[0]+ny*end[1]-offset
            if (a >= 0) != (b >= 0):
                fraction = a/(a-b)
                clipped.append((start[0]+fraction*(end[0]-start[0]),
                                start[1]+fraction*(end[1]-start[1])))
            if b >= 0:
                clipped.append(end)
        polygon = clipped
        if not polygon:
            break
    return polygon
