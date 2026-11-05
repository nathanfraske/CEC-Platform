"""Conservative, bounded rigid fastener-pattern exclusion (no board knowledge).

Pair distances are invariant under ANY rigid rotation, translation or flip.
If no injective assignment satisfies every pair-distance interval, a complete
mount is excluded. A surviving assignment is only a possible fit: collision,
thread engagement, axis direction and contact stack still need separate proof.
Never use electrical net names to filter a mechanical mismatch search.
"""
from __future__ import annotations

import math


def possible_fit(receiver, insert, *, joint_error_mm, max_states=100000):
    """Can every insert fastener coincide with distinct receiver fasteners?

    ``joint_error_mm`` bounds the combined radial play and location error at
    EACH joint. Pair distances can therefore differ by twice this amount.
    Keeping the translation free avoids the old exact-anchor false negative:
    two errors can be shared between opposite ends instead of pinning one end.
    A search limit is UNKNOWN, never evidence of physical keying.
    """
    def points(values):
        result = [tuple(float(x) for x in row) for row in values]
        if not result or any(len(row) != 2 or not all(map(math.isfinite, row))
                             for row in result):
            raise ValueError('nonempty finite 2D fastener pattern required')
        return result

    receiver, insert = points(receiver), points(insert)
    error = float(joint_error_mm)
    if not math.isfinite(error) or error < 0 or max_states < 1:
        raise ValueError('invalid mount search policy')
    states, assignment, exhausted = 0, [], False
    if len(insert) > len(receiver):
        return {'status': 'excluded', 'reason': 'insufficient_fasteners',
                'complete': True, 'states': 0, 'mapping': None}

    def search():
        nonlocal states, exhausted
        if len(assignment) == len(insert):
            return list(assignment)
        i = len(assignment)
        for j in range(len(receiver)):
            if j in assignment:
                continue
            if states >= max_states:
                exhausted = True
                return None
            states += 1
            if any(abs(math.dist(insert[i], insert[k]) -
                       math.dist(receiver[j], receiver[v])) > 2 * error + 1e-9
                   for k, v in enumerate(assignment)):
                continue
            assignment.append(j)
            found = search()
            assignment.pop()
            if found is not None or exhausted:
                return found
        return None

    found = search()
    return {'status': 'unknown' if exhausted else
            ('possible' if found is not None else 'excluded'),
            'complete': not exhausted, 'mapping': found, 'states': states,
            'reason': 'search_budget' if exhausted else
            ('distance_compatible_assignment' if found is not None else
             'pair_distance_intervals_incompatible')}


def pitch_residual(receiver, insert):
    """Maximum adjacent pitch discrepancy, translation independent, fixed order."""
    if len(receiver) != len(insert) or len(insert) < 2:
        raise ValueError('paired rows of at least two fasteners required')
    return max(abs((b - a) - (d - c)) for a, b, c, d in
               zip(receiver, receiver[1:], insert, insert[1:]))
