"""Explicit physical paired throat identity, independent of travel direction.

Explicit member order is immutable. Reversing a heading must reverse its
polarity too to describe the same copper junction; a heading alone cannot.
"""
import math


def throat_key(bank, center, heading, polarity):
    if (type(polarity) is not int or polarity not in (-1, 1)
            or len(bank) != 2 or any(len(p) != 2 for p in bank)
            or len(center) != 2 or len(heading) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   or abs(v) > 2000 for p in (*bank, center, heading) for v in p)):
        raise ValueError('finite_explicit_member_ordered_junction_required')
    dx, dy = heading
    if not (dx or dy) or not (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
        raise ValueError('nonzero_octilinear_junction_heading_required')
    norm = math.hypot(dx, dy)
    normal = (round(-polarity*dy/norm, 12), round(polarity*dx/norm, 12))
    return (tuple(tuple(p) for p in bank), tuple(center), normal)
