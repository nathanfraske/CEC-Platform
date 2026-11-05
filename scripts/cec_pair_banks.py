"""Conservative geometry evidence for a four-land paired flow station."""
import math
import re


def named_member(net):
    """Return (pair identity, P/N role) for supported differential suffixes.

    Preserves the complete hierarchy. This only recognizes naming syntax;
    topology, geometry and impedance still require independent qualification.
    """
    text = str(net or "")
    match = re.fullmatch(r"(.+)_(P|N)", text, re.I)
    if match:
        return match[1].upper(), match[2].upper()
    match = re.fullmatch(r"(.+_D)(P|M|\+|-)", text, re.I)
    if match:
        return match[1].upper(), ("P" if match[2].upper() in ("P", "+") else "N")
    return None


def ordered_banks(p_points, n_points, *, minimum_sine=0.25,
                  minimum_parallel_cosine=0.95, tolerance=1e-8):
    """Return two matched P/N banks, or None for an ambiguous pin field.

    Two straight same-member links must be parallel, non-degenerate and
    transversely separated. Collinear/interleaved reversible-contact fields
    are not flow stations. This proves a physical bank pattern, not an
    arbitrary connector's electrical role; callers must also prove a unique
    two-terminal chain and keep exact native routing admission.
    """
    if len(p_points) != 2 or len(n_points) != 2:
        return None
    try:
        ps = [tuple(float(x) for x in point) for point in p_points]
        ns = [tuple(float(x) for x in point) for point in n_points]
        if any(len(point) != 2 or not all(math.isfinite(x) for x in point)
               for point in ps + ns):
            return None
    except (TypeError, ValueError):
        return None
    delta = lambda a, b: (b[0] - a[0], b[1] - a[1])
    dot = lambda a, b: a[0] * b[0] + a[1] * b[1]
    cross = lambda a, b: a[0] * b[1] - a[1] * b[0]
    candidates = []
    for order in ((0, 1), (1, 0)):
        p_axis, n_axis = delta(ps[0], ps[1]), delta(ns[order[0]], ns[order[1]])
        lp, ln = math.hypot(*p_axis), math.hypot(*n_axis)
        if min(lp, ln) <= tolerance:
            continue
        if dot(p_axis, n_axis) / (lp * ln) < minimum_parallel_cosine:
            continue
        transverse = [delta(ps[i], ns[order[i]]) for i in (0, 1)]
        lengths = [math.hypot(*v) for v in transverse]
        if min(lengths) <= tolerance:
            continue
        if any(abs(cross(p_axis, v)) / (lp * length) < minimum_sine
               for v, length in zip(transverse, lengths)):
            continue
        # Both banks must preserve the same lane order, not form a bow tie.
        if cross(p_axis, transverse[0]) * cross(p_axis, transverse[1]) <= 0:
            continue
        candidates.append((sum(lengths), order))
    if not candidates:
        return None
    return min(candidates)[1]
