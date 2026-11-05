"""Exact centerline reuse of retained, adequately wide native track copper.

This removes redundant *proposed* copper, never source copper. Only collinear
same-layer, same-net tracks can cover a proposed section. Pads, zones, nearby
tracks and undersized tracks do not earn reuse credit. The complete constructor
must still prove clearance, topology and saved-board native connectivity.
"""
from __future__ import annotations


def uncovered_segments(proposed, retained):
    """Subtract exact integer-nanometre coverage, preserving width and order.

    Both inputs contain ``(start_xy, end_xy, width_nm)`` rows. Coverage is
    conservative: an interval with a non-integral reconstructed endpoint is
    not reused. No snapping, tolerance inflation or width relaxation is used.
    """
    source = tuple(retained)
    remaining = []
    for start, end, width in proposed:
        ax, ay = map(int, start); bx, by = map(int, end)
        width = int(width)
        if width <= 0:
            raise ValueError('positive_proposed_width_required')
        dx, dy = bx - ax, by - ay
        if not (dx or dy):
            continue
        axis = 0 if abs(dx) >= abs(dy) else 1
        delta = (dx, dy)[axis]
        direction = 1 if delta > 0 else -1
        extent = abs(delta)

        def point_at(offset):
            xnum, ynum = dx * offset, dy * offset
            if xnum % extent or ynum % extent:
                return None
            return (ax + xnum // extent, ay + ynum // extent)

        covered = []
        for left, right, retained_width in source:
            if int(retained_width) < width:
                continue
            cx, cy = map(int, left); ex, ey = map(int, right)
            if (cx, cy) == (ex, ey):
                continue
            if dx * (cy - ay) != dy * (cx - ax):
                continue
            if dx * (ey - ay) != dy * (ex - ax):
                continue
            values = sorted((direction * ((cx, cy)[axis] - (ax, ay)[axis]),
                             direction * ((ex, ey)[axis] - (ax, ay)[axis])))
            lo, hi = max(0, values[0]), min(extent, values[1])
            if lo < hi and point_at(lo) is not None and point_at(hi) is not None:
                covered.append((lo, hi))

        cursor = 0
        for lo, hi in sorted(covered):
            if hi <= cursor:
                continue
            if lo > cursor:
                remaining.append((point_at(cursor), point_at(lo), width))
            cursor = max(cursor, hi)
        if cursor < extent:
            remaining.append((point_at(cursor), point_at(extent), width))
    return remaining


def native_uncovered_plan(board, net_name, plan, layer):
    """Return only uncovered legs; leave every retained native object intact."""
    import pcbnew
    retained = [((int(t.GetStart().x), int(t.GetStart().y)),
                 (int(t.GetEnd().x), int(t.GetEnd().y)), int(t.GetWidth()))
                for t in board.GetTracks()
                if t.GetClass() == 'PCB_TRACK'
                and int(t.GetLayer()) == int(layer)
                and str(t.GetNetname()) == str(net_name)]
    proposed = [((int(a.x), int(a.y)), (int(b.x), int(b.y)), int(width))
                for a, b, width in plan]
    return [(pcbnew.VECTOR2I(*a), pcbnew.VECTOR2I(*b), width)
            for a, b, width in uncovered_segments(proposed, retained)]
