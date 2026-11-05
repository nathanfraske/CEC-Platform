"""Bounded proposal coverage, never a cached geometric pass or no-path proof.

An unrelated accepted move must not make every round probe the same rejected
pose again. Prefer less-tried poses within the existing finite trial budget.
Even a previously tried pose is eligible after alternatives are covered: its
surroundings may have changed. Callers may carry JSON-safe work history across
invocations; the pipeline discards its sidecar when the PCB bytes change.
"""
import math


def export_visits(visits):
    """JSON-safe search preferences, never cached pass/fail evidence."""
    return dict(schema=1, purpose='placement-proposal-ordering',
                cached_admission=False, exhaustion_is_no_path_proof=False,
                visits=[dict(kind=kind, placements={row[0]: list(row[1:])
                             for row in poses}, count=count)
                        for (kind, poses), count in sorted(visits.items())])


def import_visits(data):
    """Reject malformed search state; no caller may import admission from it."""
    if (not isinstance(data, dict) or data.get('schema') != 1
            or data.get('purpose') != 'placement-proposal-ordering'
            or data.get('cached_admission') is not False
            or data.get('exhaustion_is_no_path_proof') is not False
            or not isinstance(data.get('visits'), list)):
        raise ValueError('invalid placement search history')
    result = {}
    for row in data['visits']:
        if (not isinstance(row, dict) or not isinstance(row.get('placements'), dict)
                or not isinstance(row.get('kind'), str)):
            raise ValueError('invalid placement search visit')
        key = signature(row)
        count = row.get('count')
        if (key is None or not isinstance(count, int) or isinstance(count, bool)
                or count < 1 or key in result):
            raise ValueError('invalid or duplicate placement search visit')
        result[key] = count
    return result


def signature(move):
    placements = move.get('placements') or {move.get('ref'): move.get('position')}
    rows = []
    for ref, pose in sorted(placements.items(), key=lambda item: str(item[0])):
        if not ref or not isinstance(pose, (tuple, list)) or len(pose) != 3:
            return None
        try:
            values = tuple(float(v) for v in pose)
        except (TypeError, ValueError, OverflowError):
            return None
        if not all(math.isfinite(v) for v in values):
            return None
        rows.append((str(ref), *values[:2], values[2] % 360.0))
    # Different proposal semantics remain distinct. This key is only a search
    # preference; it is intentionally not an evidence/cache identity.
    return (str(move.get('kind') or ''), tuple(rows)) if rows else None


def select(moves, budget, *, visits, selector):
    """Fairly sample each least-visited tier with the established selector."""
    rows = list(moves or ())
    budget = max(0, int(budget))
    if not visits:
        return selector(rows, budget)
    tiers = {}
    for index, move in enumerate(rows):
        key = signature(move)
        count = visits.get(key, 0) if key is not None else 0
        tiers.setdefault(count, []).append((index, move))
    selected = []
    for count in sorted(tiers):
        if len(selected) >= budget:
            break
        selected.extend(selector([move for _, move in tiers[count]],
                                 budget - len(selected)))
    return selected


def record(move, visits):
    key = signature(move)
    if key is not None:
        visits[key] = visits.get(key, 0) + 1


def certificate(moves, visits):
    counts = [visits.get(signature(move), 0) for move in moves]
    return dict(schema=1, policy='least_visited_then_blocker_fair',
                history_size=len(visits), selected=len(counts),
                untried=sum(count == 0 for count in counts),
                revisited=sum(count > 0 for count in counts),
                prior_attempts=counts, cached_admission=False)


def frontier(moves, visits):
    """Describe the unscheduled part of THIS finite proposal population.

    Visits are work accounting, not geometry proofs. Unknown signatures cannot
    justify extra work or an exhaustive/no-path claim. Duplicate spellings of
    the same proposal count once, as they do in the existing coverage selector.
    """
    signatures, unknown, population = set(), 0, 0
    for move in moves:
        population += 1
        key = signature(move)
        if key is None:
            unknown += 1
        else:
            signatures.add(key)
    unvisited = sum(not visits.get(key, 0) for key in signatures)
    return dict(schema=1, population=population, unique=len(signatures),
                unvisited=unvisited, visited=len(signatures)-unvisited,
                unknown=unknown, cached_admission=False,
                exhaustion_is_no_path_proof=False)


def can_advance(frontier_report, selected_count, *, evaluation_budget_exhausted=False):
    """Use only another caller-funded batch, never restart timed-out trials."""
    return bool(not evaluation_budget_exhausted and selected_count > 0
                and frontier_report.get('unvisited', 0) > 0)
