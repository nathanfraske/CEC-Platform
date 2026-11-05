"""Finite miter run-length state for an octilinear coupled corridor.

Two consecutive same-sense 45-degree turns consume part of both ends of
the inner offset segment. A direction-only maze can choose a segment shorter
than these two miter retreats, then produce a reversed member after offsetting.
This is a necessary search prefilter, not clearance or complete-route proof.
"""
import math


def run_caps(step_mm, member_center_spacing_mm):
    for value in (step_mm, member_center_spacing_mm):
        if (type(value) not in (int, float) or not math.isfinite(value)
                or value <= 0):
            raise ValueError('positive_finite_pair_bend_geometry_required')
    # Two retreats of half the member-centre separation * tan(45/2).
    retreat = member_center_spacing_mm * math.tan(math.pi / 8)
    caps = tuple(max(1, math.floor(retreat / (step_mm * (
        math.sqrt(2) if heading % 2 else 1))) + 1)
        for heading in range(8))
    if max(caps) > 64:
        raise ValueError('bounded_pair_bend_run_state_required')
    return caps


def advance(heading, previous_turn, straight_steps, next_heading, caps):
    """Return the next (last signed turn, capped straight run), or refuse.

    Equal-sense turns require a positive inner segment. Opposite-sense turns
    do not add their miter retreats, so do not impose that unnecessary rule.
    Every emitted member must still pass the existing exact final checks.
    """
    if (type(heading) is not int or type(next_heading) is not int
            or not 0 <= heading < 8 or not 0 <= next_heading < 8
            or type(previous_turn) is not int or previous_turn not in (-1, 0, 1)
            or type(straight_steps) is not int or straight_steps < 0
            or not isinstance(caps, tuple) or len(caps) != 8
            or any(type(v) is not int or not 1 <= v <= 64 for v in caps)
            or straight_steps > caps[heading]):
        raise ValueError('exact_bounded_pair_bend_state_required')
    delta = (next_heading - heading) % 8
    if delta not in (0, 1, 7):
        return None
    if delta == 0:
        return previous_turn, min(caps[heading], straight_steps + 1)
    turn = 1 if delta == 1 else -1
    if turn == previous_turn and straight_steps < caps[heading]:
        return None
    return turn, 1
