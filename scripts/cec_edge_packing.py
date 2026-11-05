"""Bounded one-dimensional connector-bank packing from actual body geometry."""
import math


class EdgePackingInfeasible(ValueError):
    """Valid geometry has no legal bank seat; distinct from malformed input."""


def bank_start(length, items, obstacles=(), *, alignment="center",
               start_margin=1.5, end_margin=1.5, clearance=0.1):
    """Return a legal bank translation along an edge, or reject an impossible bank.

    Items are (along_lo, along_hi, perpendicular_lo, perpendicular_hi), in a
    bank-local along frame and board-global perpendicular frame. Obstacles use
    the same tuple in the board frame. Only overlapping perpendicular bands
    obstruct a particular item. Interval subtraction is exact and finite; this
    does not grid-search, change connector rotation, or move mechanical datums.
    Start/end mean increasing board x on horizontal edges, y on vertical ones.
    """
    if alignment not in ("start", "center", "end"):
        raise ValueError("edge packing alignment must be start, center or end")
    values = [length, start_margin, end_margin, clearance]
    if any(not math.isfinite(float(v)) or float(v) < 0 for v in values):
        raise ValueError("edge packing dimensions must be finite and nonnegative")
    if not items:
        return float(start_margin)
    for rect in (*items, *obstacles):
        if (len(rect) != 4 or any(not math.isfinite(float(v)) for v in rect)
                or rect[1] < rect[0] or rect[3] < rect[2]):
            raise ValueError("edge packing requires finite ordered rectangles")
    low = float(start_margin) - min(row[0] for row in items)
    high = float(length) - float(end_margin) - max(row[1] for row in items)
    if high < low - 1e-9:
        raise EdgePackingInfeasible("edge packing bank exceeds the usable edge length")
    available = [(low, max(low, high))]
    for a0, a1, p0, p1 in items:
        for b0, b1, q0, q1 in obstacles:
            if p1 + clearance <= q0 or q1 + clearance <= p0:
                continue
            forbidden_low = b0 - clearance - a1
            forbidden_high = b1 + clearance - a0
            remaining = []
            for lo, hi in available:
                if forbidden_high <= lo or forbidden_low >= hi:
                    remaining.append((lo, hi))
                    continue
                if forbidden_low >= lo:
                    remaining.append((lo, min(hi, forbidden_low)))
                if forbidden_high <= hi:
                    remaining.append((max(lo, forbidden_high), hi))
            available = remaining
    if not available:
        raise EdgePackingInfeasible("edge packing has no clearance-safe bank position")
    preferred = {"start": low, "center": (low + high) / 2, "end": high}[alignment]
    return min((min(hi, max(lo, preferred)) for lo, hi in available),
               key=lambda x: (abs(x - preferred), x))
