"""Frame-independent nominal mating-row repair; no board or part selectors.

This aligns lateral datums only. It cannot qualify contact depth, tolerance
stacks, polarity under an assembly flip, or a positive mechanical key.
"""
from __future__ import annotations

import math


class MatingRowConflict(ValueError):
    """A declared paired row cannot be emitted under its current envelopes."""

    def __init__(self, evidence):
        self.evidence = evidence
        super().__init__('paired mating row requires geometry revision: ' +
                         str(evidence.get('reason', 'envelope conflict')) +
                         ('; excess %.6g mm' % evidence['excess_mm']
                          if 'excess_mm' in evidence else ''))


def rigid_row_outline_fit(datums, intervals, *, outline_interval_mm,
                          edge_clearance_mm):
    """Bound a complete row, including companions, without growing its outline.

    The row may translate laterally as a unit. No datum, contact envelope or
    clearance is reduced. A negative translation window proves that this
    particular rigid pattern cannot fit even after recovering all edge slack;
    it is not proof against different parts, topology or a different 3-D mate.
    This is a screen, never native DRC or a proposal to enlarge the PCB.
    """
    xs = list(map(float, datums))
    lands = [tuple(map(float, row)) for row in intervals]
    bounds = tuple(map(float, outline_interval_mm))
    gap = float(edge_clearance_mm)
    if (not xs or len(xs) != len(lands) or len(bounds) != 2 or
            any(len(row) != 2 or row[1] <= row[0] for row in lands) or
            bounds[1] <= bounds[0] or gap < 0 or
            not all(math.isfinite(v) for v in
                    xs + [v for row in lands for v in row] + list(bounds) + [gap])):
        raise ValueError('complete finite row, outline and nonnegative edge margin required')
    left = [x + row[0] for x, row in zip(xs, lands)]
    right = [x + row[1] for x, row in zip(xs, lands)]
    lo, hi = min(left), max(right)
    shift_min, shift_max = bounds[0] + gap - lo, bounds[1] - gap - hi
    required = hi - lo + 2 * gap
    available = bounds[1] - bounds[0]
    fits = shift_min <= shift_max + 1e-9
    return dict(screen_only=True, admission_ok=False, dimensions_changed=False,
                fits_fixed_outline=fits, minimum_width_mm=required,
                available_width_mm=available, additional_width_mm=max(0., required-available),
                translation_window_mm=[shift_min, shift_max],
                edge_clearance_mm=gap, limiting_indices=[left.index(lo), right.index(hi)],
                proposed_translation_mm=min(max(0., shift_min), shift_max) if fits else None)


def compile_paired_row(coordinates, envelope_sets, *, maximum_last_mm):
    """Solve shared ordered datums against *both* halves before moving either.

    Each set supplies a domain, installed intervals about each contact datum,
    and its explicit screening gap. Check all pairs, not just neighbours.
    Redistribute available slack without moving the first datum or exceeding
    the last-datum limit. This conservative 1-D proposal is NOT native DRC,
    a 3-D fit certificate, or proof that other orientations cannot fit.
    """
    xs = list(map(float, coordinates))
    limit = float(maximum_last_mm)
    if (len(xs) < 2 or not all(map(math.isfinite, xs + [limit])) or
            any(b <= a for a, b in zip(xs, xs[1:])) or limit < xs[0]):
        raise ValueError('finite ordered datums and fixed envelope required')
    constraints = []
    sets = list(envelope_sets)
    if not sets:
        raise ValueError('paired envelope evidence required')
    for domain in sets:
        intervals = [tuple(map(float, pair)) for pair in domain['intervals']]
        gap = float(domain['gap_mm'])
        if (len(intervals) != len(xs) or not math.isfinite(gap) or gap < 0 or
                any(len(p) != 2 or not all(map(math.isfinite, p)) or p[1] <= p[0]
                    for p in intervals)):
            raise ValueError('complete finite positive envelopes required')
        for j in range(len(xs)):
            for i in range(j + 1, len(xs)):
                constraints.append(dict(indices=[j, i], domain=str(domain['domain']),
                    minimum_pitch_mm=intervals[j][1] - intervals[i][0] + gap))
    # An asymmetric pad envelope must not authorize reversing contact order.
    constraints += [dict(indices=[i-1, i], domain='order', minimum_pitch_mm=1e-6)
                    for i in range(1, len(xs))]
    incoming = [[r for r in constraints if r['indices'][1] == i] for i in range(len(xs))]
    outgoing = [[r for r in constraints if r['indices'][0] == i] for i in range(len(xs))]
    earliest = [xs[0]]
    for i in range(1, len(xs)):
        earliest.append(max(earliest[r['indices'][0]] + r['minimum_pitch_mm'] for r in incoming[i]))
    violations = [r for r in constraints if xs[r['indices'][1]] - xs[r['indices'][0]]
                  < r['minimum_pitch_mm'] - 1e-9]
    receipt = dict(schema=1, screen_only=True, admission_ok=False, dimensions_changed=False,
                   original_datums_mm=xs, maximum_last_mm=limit,
                   minimum_datums_mm=earliest, minimum_span_mm=earliest[-1]-xs[0],
                   available_span_mm=limit-xs[0], conflicts=violations,
                   constraints=constraints, excess_mm=max(0., earliest[-1]-limit))
    if earliest[-1] > limit + 1e-9:
        return dict(receipt, ok=False, changed=False,
                    reason='paired_envelopes_exceed_fixed_span', proposed_datums_mm=None)
    if not violations and xs[-1] <= limit + 1e-9:
        return dict(receipt, ok=True, changed=False, proposed_datums_mm=xs)
    latest = [limit] * len(xs)
    for j in range(len(xs)-2, -1, -1):
        latest[j] = min(latest[r['indices'][1]] - r['minimum_pitch_mm'] for r in outgoing[j])
    proposed = [xs[0]]
    for i in range(1, len(xs)):
        lower = max(proposed[r['indices'][0]] + r['minimum_pitch_mm'] for r in incoming[i])
        proposed.append(min(max(xs[i], lower), latest[i]))
    if any(proposed[r['indices'][1]] - proposed[r['indices'][0]]
           < r['minimum_pitch_mm'] - 1e-9 for r in constraints):
        raise ValueError('paired row solver failed its own envelope check')
    return dict(receipt, ok=True, changed=True, proposed_datums_mm=proposed)


def envelope_row_screen(coordinates, copper_intervals, *, maximum_last_mm,
                        minimum_clearance_mm=0.0):
    """Conservative lateral-envelope screen for a coherent, same-depth row.

    Intervals are actual rotated copper extents relative to each mating
    datum, not package-body widths. This conservative projection is not a
    complete DRC or permission to move a mating interface. Staggered pads and
    mixed-part screw-axis offsets require exact geometry. A zero-clearance
    call is only an envelope screen, never electrical admission.
    """
    xs = list(map(float, coordinates))
    envelopes = [tuple(map(float, interval)) for interval in copper_intervals]
    if len(xs) < 2 or len(envelopes) != len(xs) or any(len(row) != 2 for row in envelopes):
        raise ValueError('one copper interval per ordered mating datum required')
    values = xs + [v for row in envelopes for v in row] + [maximum_last_mm, minimum_clearance_mm]
    if (not all(math.isfinite(v) for v in values) or minimum_clearance_mm < 0
            or any(b <= a for a, b in zip(xs, xs[1:]))
            or any(right < left for left, right in envelopes)):
        raise ValueError('invalid finite ordered copper envelopes')
    proposed = [xs[0]]
    pairs = []
    for i in range(1, len(xs)):
        required = envelopes[i-1][1] - envelopes[i][0] + minimum_clearance_mm
        gap = xs[i] + envelopes[i][0] - xs[i-1] - envelopes[i-1][1]
        proposed.append(round(proposed[-1] + max(xs[i]-xs[i-1], required), 6))
        pairs.append({'indices': [i-1, i], 'actual_gap_mm': round(gap, 6),
                      'required_pitch_mm': round(required, 6),
                      'ok': gap >= minimum_clearance_mm - 1e-6})
    excess = max(0., proposed[-1] - maximum_last_mm)
    return {'ok': all(pair['ok'] for pair in pairs) and xs[-1] <= maximum_last_mm + 1e-6,
            'fits_fixed_envelope': excess <= 1e-6, 'pairs': pairs,
            'proposed_datums_mm': proposed, 'maximum_last_mm': maximum_last_mm,
            'excess_mm': round(excess, 6), 'clearance_mm': minimum_clearance_mm,
            'screen_only': True, 'dimensions_changed': False}


def edge_channel_origin(origin, *, copper_extent, edge, edge_clearance,
                        route_width, copper_clearance, margin, maximum_shift):
    """Reserve a complete route corridor between a pad envelope and an edge.

    All coordinates are projected on an outward-positive local axis. This is
    a nominal placement proposal, not permission to alter mated depth.
    """
    values = (origin, copper_extent, edge, edge_clearance, route_width,
              copper_clearance, margin, maximum_shift)
    if not all(math.isfinite(float(v)) for v in values) or min(values[3:]) < 0:
        raise ValueError('finite nonnegative channel budgets required')
    limit = edge - edge_clearance - route_width - copper_clearance - margin - copper_extent
    target = min(origin, limit)
    if origin - target > maximum_shift + 1e-9:
        raise ValueError('edge channel exceeds declared depth-change envelope')
    return round(target, 6)


def clearance_row(coordinates, body_widths, body_tolerances, *,
                  position_error_mm, minimum_gap_mm, maximum_last_mm):
    """Spread a row only as needed for a stated worst-size gap budget.

    Tolerances are +/- FULL body-width errors; position_error_mm is +/- at
    EACH center. These are input evidence, never an inferred manufacturing
    qualification. The first datum stays fixed and the maximum envelope is
    hard, so a failed fit cannot quietly enlarge a board.
    """
    xs, widths, errors = [list(map(float, r)) for r in
                           (coordinates, body_widths, body_tolerances)]
    policy = [float(position_error_mm), float(minimum_gap_mm), float(maximum_last_mm)]
    if len(xs) < 2 or len(xs) != len(widths) or len(xs) != len(errors):
        raise ValueError('one body envelope per mating coordinate required')
    if not all(map(math.isfinite, xs + widths + errors + policy)):
        raise ValueError('finite body envelopes required')
    if (min(widths) <= 0 or min(errors) < 0 or min(policy[:2]) < 0 or
            any(b <= a for a, b in zip(xs, xs[1:]))):
        raise ValueError('invalid body clearance policy')
    out = [xs[0]]
    for i in range(1, len(xs)):
        required = ((widths[i-1] + errors[i-1] + widths[i] + errors[i]) / 2
                    + 2 * position_error_mm + minimum_gap_mm)
        out.append(round(out[-1] + max(xs[i] - xs[i-1], required), 6))
    if out[-1] > maximum_last_mm + 1e-6:
        raise ValueError('body tolerance stack cannot fit the fixed interface envelope')
    return out


def shared_row_datums(rows, *, first_datum_mm, tolerance_mm=0.01):
    """Transfer ordered parent pitches to a mate; disagreeing parents refuse.

    Rows are already projected into their declared lateral frames by callers.
    Their absolute origins do not participate in the shared contact pattern.
    """
    rows = [list(map(float, row)) for row in rows]
    origin, tolerance = float(first_datum_mm), float(tolerance_mm)
    if (not rows or len(rows[0]) < 2 or tolerance < 0 or
            not all(math.isfinite(v) for v in [origin, tolerance] + [x for row in rows for x in row]) or
            any(len(row) != len(rows[0]) or any(b <= a for a, b in zip(row, row[1:])) for row in rows)):
        raise ValueError('complete finite ordered parent rows required')
    offsets = [x-rows[0][0] for x in rows[0]]
    if any(abs((x-row[0])-expected) > tolerance
           for row in rows[1:] for x, expected in zip(row, offsets)):
        raise ValueError('parent mating patterns disagree; no unilateral daughter repair')
    return [round(origin+x, 6) for x in offsets]


def align_row(poses, refs, coordinates, *, axis_angle_deg=0.0,
              lateral_offsets=None, row_tolerance_mm=0.01, maximum_span_mm=None):
    """Fit a declared row inside its existing span, retaining its center.

    ``coordinates`` are the mate's ordered lateral datums, not independently
    editable main-board pitches. ``lateral_offsets`` are explicit projected
    origin-to-axis offsets. Unknown offsets must not be presented as measured.
    Rotation follows KiCad's positive-angle screen convention. The normal
    coordinate and each footprint rotation are preserved, not guessed.
    """
    refs, coordinates = list(refs), list(map(float, coordinates))
    if len(refs) < 2 or len(refs) != len(coordinates) or len(set(refs)) != len(refs):
        raise ValueError('one unique reference per mating datum required')
    offsets = dict(lateral_offsets or {})
    if set(offsets) - set(refs):
        raise ValueError('offset refers to undeclared contact')
    values = coordinates + [float(axis_angle_deg), float(row_tolerance_mm)]
    values += [float(v) for v in offsets.values()]
    values += [float(v) for ref in refs for v in poses[ref]]
    if not all(map(math.isfinite, values)) or row_tolerance_mm < 0:
        raise ValueError('finite mating geometry required')
    if any(b <= a for a, b in zip(coordinates, coordinates[1:])):
        raise ValueError('mate datums must be in strictly increasing order')
    a = math.radians(axis_angle_deg)
    axis, normal = (math.cos(a), -math.sin(a)), (math.sin(a), math.cos(a))
    along = {r: poses[r][0] * axis[0] + poses[r][1] * axis[1] for r in refs}
    across = {r: poses[r][0] * normal[0] + poses[r][1] * normal[1] for r in refs}
    if max(across.values()) - min(across.values()) > row_tolerance_mm:
        raise ValueError('contacts are not a coherent row; refuse to infer a frame')
    local = {r: x - float(offsets.get(r, 0)) for r, x in zip(refs, coordinates)}
    old_span = max(along.values()) - min(along.values())
    new_span = max(local.values()) - min(local.values())
    limit = old_span if maximum_span_mm is None else float(maximum_span_mm)
    if not math.isfinite(limit) or limit < 0:
        raise ValueError('finite nonnegative authorized row span required')
    if new_span > limit + row_tolerance_mm:
        raise ValueError('mating repair would enlarge the existing interface span')
    shift = (max(along.values()) + min(along.values()) -
             max(local.values()) - min(local.values())) / 2
    return {r: (round(axis[0] * (local[r] + shift) + normal[0] * across[r], 6),
                round(axis[1] * (local[r] + shift) + normal[1] * across[r], 6),
                poses[r][2]) for r in refs}


def companion_on_axis(pose, anchor, lateral_distance_mm, *, axis_angle_deg=0.0):
    """Change only the companion's lateral datum, preserving depth/rotation."""
    if not all(math.isfinite(float(x)) for x in
               (*pose, *anchor, lateral_distance_mm, axis_angle_deg)):
        raise ValueError('finite companion geometry required')
    a = math.radians(axis_angle_deg)
    axis = (math.cos(a), -math.sin(a))
    correction = ((anchor[0] - pose[0]) * axis[0] +
                  (anchor[1] - pose[1]) * axis[1] + lateral_distance_mm)
    return (round(pose[0] + axis[0] * correction, 6),
            round(pose[1] + axis[1] * correction, 6), pose[2])
