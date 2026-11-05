"""One bounded allocation-order retry for not-yet-frozen power geometry.

Only prospective lanes returned by the solver are reconsidered. Existing
native copper and caller-owned reservation ledgers stay in that solver's
unchanged input. This schedules search, never grants electrical admission.
"""
from copy import deepcopy
import math
import time


def solve_prospective_batch(asks, solve, *, current_priority=None, collect=None,
                            report=None, max_retries=1):
    """Keep the original solve unless one failed-first retry strictly dominates.

    ``solve(asks, collect)`` returns the normal (pours, vias, per-net report).
    A retry may not lose a single originally solved net. Native refill, current
    width and connectivity admission remain the consumer's responsibility.
    The selected geometry and its exact search grid/ledger are returned as one
    unit; losing-candidate reservation state never leaks to downstream stages.
    """
    if (not isinstance(max_retries, int) or isinstance(max_retries, bool)
            or max_retries not in (0, 1)):
        raise ValueError('prospective power order retries must be 0 or 1')
    rows = list(asks)
    priorities = dict(current_priority or {})
    if any(not math.isfinite(float(value)) or float(value) < 0
           for value in priorities.values()):
        raise ValueError('current priorities must be finite and nonnegative')
    receipt = dict(schema=1, scope='prospective_power_only', max_retries=max_retries,
                   exact_admission_required=True, selected=0, attempts=[])

    def run(order):
        state = {}
        started = time.monotonic()
        result = solve(deepcopy(order), state)
        found = {net for net, value in result[2].items()
                 if value.get('path_found') is True}
        receipt['attempts'].append(dict(order=[row.get('net') for row in order],
            found=sorted(found), failed=sorted({row.get('net') for row in order
                if row.get('net')} - found), elapsed_s=round(time.monotonic()-started, 3)))
        return result, state, found

    selected, selected_state, found = run(rows)
    failed = {row.get('net') for row in rows if row.get('net')} - found
    ordered = sorted(rows, key=lambda row: (
        row.get('net') not in failed,
        -float(priorities.get(row.get('net'), 0)), str(row.get('net') or '')))
    if not max_retries or not failed:
        receipt['reason'] = 'disabled' if not max_retries else 'all_paths_found'
    elif [row.get('net') for row in ordered] == [row.get('net') for row in rows]:
        receipt['reason'] = 'no_distinct_order'
    else:
        alternative, alternative_state, alternate_found = run(ordered)
        lost = found - alternate_found
        gained = alternate_found - found
        receipt.update(lost=sorted(lost), gained=sorted(gained))
        if not lost and gained:
            selected, selected_state = alternative, alternative_state
            receipt.update(selected=1, reason='strict_terminal_coverage_improvement')
        else:
            receipt['reason'] = 'lost_solved_net' if lost else 'no_strict_improvement'
    if collect is not None:
        collect.clear()
        collect.update(selected_state)
    if report is not None:
        report.clear()
        report.update(receipt)
    return selected
