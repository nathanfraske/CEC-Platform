"""Construction-only octilinear landing from a sampled pair grid.

The lattice's final point and the exact terminal runway need not share either
coordinate.  Joining them with a straight residual is not an octilinear route.
Build a forward 45-degree correction and a final straight runway instead.  All
native copper/member/reservation/offset checks belong to the caller and remain
mandatory; this pure geometric proposal grants no routing or process authority.
"""
from __future__ import annotations

import math


def bridge(start, finish, heading):
    """Return an exact-endpoint 0/45 path, or None for a non-forward runway.

``heading`` must already be an octilinear unit/direction vector.  A proposal
does not snap an arbitrary signal heading or move either endpoint.  Both turns
are at most 45 degrees relative to that heading, including diagonal runways.
"""
    def point(value):
        if len(value) != 2 or any(isinstance(v, bool) for v in value):
            raise ValueError('two_finite_coordinates_required')
        result = tuple(float(v) for v in value)
        if not all(math.isfinite(v) for v in result):
            raise ValueError('two_finite_coordinates_required')
        return result

    start, finish, heading = point(start), point(finish), point(heading)
    length = math.hypot(*heading)
    if length <= 1e-12:
        raise ValueError('positive_octilinear_heading_required')
    ux, uy = (v/length for v in heading)
    if min(abs(ux), abs(uy), abs(abs(ux)-abs(uy))) > 1e-9:
        raise ValueError('positive_octilinear_heading_required')
    nx, ny = -uy, ux
    delta = (finish[0]-start[0], finish[1]-start[1])
    forward = delta[0]*ux+delta[1]*uy
    lateral = delta[0]*nx+delta[1]*ny
    if forward < abs(lateral)-1e-9:
        return None
    if math.hypot(*delta) <= 1e-12:
        return [start]
    if abs(lateral) <= 1e-9:
        return [start, finish]
    middle = (start[0]+ux*abs(lateral)+nx*lateral,
              start[1]+uy*abs(lateral)+ny*lateral)
    if math.dist(middle, finish) <= 1e-9:
        return [start, finish]
    return [start, middle, finish]
