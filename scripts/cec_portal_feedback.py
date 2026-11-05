"""Bounded, transaction-local feedback from pair routing to escape selection.

An exhausted local frontier is evidence about a searched portal, not proof
that the board is impossible. These exclusions only diversify the next beam;
they never create copper or relax any admission predicate.
"""
from __future__ import annotations

import math
import copy
import time
import json


def retain_rejection_witness(rows, witness, *, limit=24):
    """Bounded diagnostic diversity, never solver feedback or cut authority.

    Thousands of early copper-seat refusals must not erase the rare later
    field-clear/fan-in failure which actually determines the next repair.
    Retain nearest examples per reason, then round-robin those groups. The
    caller still publishes aggregate counts and a separate nearest-only view.
    """
    if (type(rows) is not list or type(limit) is not int or not 1<=limit<=24
            or len(rows)>limit or type(witness) is not dict):
        raise ValueError('bounded_portal_rejection_witness_inventory_required')
    grouped={};seen=set()
    for row in [*rows,witness]:
        if (type(row) is not dict or type(row.get('reason')) is not str or not row['reason']
                or len(row['reason'])>512 or type(row.get('score')) not in (list,tuple)
                or not 1<=len(row['score'])<=8 or any(type(v) not in (int,float)
                    or not math.isfinite(v) for v in row['score']) or type(row.get('portal')) is not dict):
            raise ValueError('literal_ranked_portal_rejection_witness_required')
        identity=(row['reason'],bool(row.get('allow_detour')),json.dumps(row['portal'],sort_keys=True,separators=(',',':')))
        if identity in seen:continue
        # Existing rows already belong to this collector. Do not deep-copy
        # all 24 nested native reports for each of thousands of cheap failed
        # seats. Only an incoming witness that survives selection needs its
        # own snapshot; sorting/dropping never mutates an old row's contents.
        seen.add(identity);grouped.setdefault(row['reason'],[]).append(row)
    for group in grouped.values():
        group.sort(key=lambda r:(tuple(r['score']),json.dumps(r['portal'],sort_keys=True,separators=(',',':')),
                                 bool(r.get('allow_detour'))))
    ordered=[grouped[k] for k in sorted(grouped)];kept=[]
    for index in range(limit):
        for group in ordered:
            if index<len(group):
                selected=group[index]
                kept.append(copy.deepcopy(selected) if selected is witness else selected)
            if len(kept)==limit:break
        if len(kept)==limit:break
    rows[:]=kept


def fair_screen_domains(groups, probe, *, deadline=None, clock=time.monotonic,
                        initial_quantum_s=.25, maximum_quantum_s=2., max_rounds=64,
                        minimum_candidates=1, maximum_stalled_rounds=3):
    """Resume independent prerequisite domains without starving alternatives.

    ``probe(domain, deadline)`` returns candidates, complete, and progress.
    A complete empty domain is exhausted only within its finite declared
    search; an interrupted one remains unproved. Every live domain receives
    a turn before optional deepening, and a ready group yields to its consumer.
    The consumer may request a wider positive frontier. A finite completed
    domain with fewer candidates is still usable. Repeated unchanged results
    at the maximum quantum stop optional screening, not declare exhaustion.
    The consumer, not this scheduler, owns exact geometry and acceptance.
    """
    if (not all(math.isfinite(v) and v > 0 for v in
                (initial_quantum_s, maximum_quantum_s))
            or initial_quantum_s > maximum_quantum_s
            or type(max_rounds) is not int or max_rounds < 1
            or type(minimum_candidates) is not int or minimum_candidates < 1
            or type(maximum_stalled_rounds) is not int or maximum_stalled_rounds < 1
            or (deadline is not None and not math.isfinite(deadline))):
        raise ValueError('invalid domain screening budget')
    domains = list(dict.fromkeys(domain for group in groups for domain in group))
    results, visits, stalls = {}, [], {}
    stalled = set()
    ready = []

    def usable(domain):
        row = results.get(domain, {})
        count = len(row.get('candidates') or ())
        return count >= minimum_candidates or bool(
            count and (row.get('complete') or domain in stalled))

    for round_index in range(max_rounds):
        pending = [domain for domain in domains
                   if not (results.get(domain, {}).get('complete')
                           or usable(domain) or domain in stalled)]
        if not pending or (deadline is not None and clock() >= deadline):
            break
        quantum = min(maximum_quantum_s, initial_quantum_s * 2**min(round_index, 20))
        for index, domain in enumerate(pending):
            now = clock()
            if deadline is not None and now >= deadline:
                break
            # Always reserve a peer's fair share; unused time is available in
            # the next round. No negative is inferred from this local deadline.
            share = (quantum if deadline is None else
                     min(quantum, (deadline-now)/(len(pending)-index+1)))
            previous = results.get(domain)
            # Producers can reuse a mutable candidate list. Snapshot before
            # calling them so an append cannot rewrite the prior observation.
            before = ((previous.get('progress', 0),
                       len(previous.get('candidates') or ()),
                       bool(previous.get('complete'))) if previous is not None else None)
            result = probe(domain, now+share)
            results[domain] = result
            after = (result.get('progress', 0), len(result.get('candidates') or ()),
                     bool(result.get('complete')))
            if after == before and share + 1e-9 >= maximum_quantum_s:
                stalls[domain] = stalls.get(domain, 0) + 1
            else:
                stalls[domain] = 0
            if stalls[domain] >= maximum_stalled_rounds and not result.get('complete'):
                stalled.add(domain)
            visits.append({'domain':domain, 'round':round_index,
                           'progress':result.get('progress', 0),
                           'accepted':len(result.get('candidates') or ()),
                           'complete':bool(result.get('complete'))})
        ready = [index for index, group in enumerate(groups)
                 if group and all(usable(domain) for domain in group)]
        if ready:
            break
    return {'domains':results, 'visits':visits, 'ready_groups':ready,
            'minimum_candidates':minimum_candidates,
            'stalled_domains':[domain for domain in domains if domain in stalled],
            'budget_exhausted':deadline is not None and clock() >= deadline,
            'round_limit_reached':bool(visits and visits[-1]['round']+1 >= max_rounds)}


def positive_frontier_refill(evidence, current_minimum):
    """Suggest bounded diversity only after a whole-edge consumer refusal.

    This is scheduling evidence, never a waiver or an impossibility claim.
    No re-run is suggested for exhausted/stalled domains or local-seat-only
    failures. The caller retains its original transaction/deadline/refill cap.
    """
    evidence = evidence or {}
    eligible = {'whole portal edge admission failed',
                'no reproducible lattice-aligned destination portal',
                'shared-centreline ribbon failed exact gap/coupling'}
    reasons = sorted({row.get('refused') for row in evidence.get('attempts', ())
                      if row.get('refused') in eligible})
    capacity = int(evidence.get('max_fanins_per_side') or 0)
    target = min(capacity, 2 * current_minimum)
    stalled = set((evidence.get('screen_schedule') or {}).get('stalled_domains') or ())
    live = [label for label, row in (evidence.get('screened') or {}).items()
            if not row.get('domain_complete') and not row.get('prequalified')
            and label not in stalled and int(row.get('accepted') or 0) < target]
    if reasons and live and target > current_minimum:
        return dict(minimum_candidates=target, domains=sorted(live), reasons=reasons)
    return None


class PortalProbeCache:
    """Reuse only completed negative local queries in one rollback transaction.

    This is not an impossibility cache. The same finite query and exact geometry
    may reuse its refusal; changed geometry/policy or another transaction may
    not. Positive queries always run again to materialize and validate copper.
    """

    def __init__(self, limit=4096):
        self.limit = max(0, int(limit))
        self.rows = {}
        self.hits = 0

    @staticmethod
    def completed_negative(report):
        if (not isinstance(report, dict) or not report.get("refused")
                or not (report.get("admission") or {}).get("direct")):
            return False

        from cec_search_completion import search_completion_evidence
        return not search_completion_evidence(report, witness_limit=0)["inconclusive"]

    def probe(self, key, solve, *, expired):
        # Never turn a cached refusal into work allowed after the caller's
        # deadline. The solver remains responsible for its ordinary timeout.
        if not expired() and key in self.rows:
            self.hits += 1
            return copy.deepcopy(self.rows[key])
        report = solve()
        if (len(self.rows) < self.limit and not expired()
                and self.completed_negative(report)):
            self.rows[key] = copy.deepcopy(report)
        return report


def portal_geometry_key(row):
    """Retain electrical lane order and heading, not just the shared centre."""
    try:
        points = tuple(tuple(float(v) for v in row[key])
                       for key in ("p", "n", "route_heading"))
        if any(len(point) != 2 for point in points):
            return None
        values = tuple(v for point in points for v in point)
        if not all(math.isfinite(v) for v in values):
            return None
        return tuple(round(v, 6) for v in values)
    except (KeyError, TypeError, ValueError):
        return None


def stranded_start_observations(evidence, *, max_progress_fraction=0.25,
                                local_radius_mm=2.0):
    """Find exhaustively explored, still-local start pockets in exact grids.

    Time/state-limit failures cannot remove a candidate. Neither can a grid
    that made meaningful board-scale progress, or malformed/incomplete data.
    Only the exact source portal is named; no area, net or footprint is banned.
    """
    if (not math.isfinite(max_progress_fraction)
            or not 0 <= max_progress_fraction < 0.5
            or not math.isfinite(local_radius_mm) or local_radius_mm < 0):
        raise ValueError("portal feedback requires bounded finite locality policy")
    found = {}
    for attempt in (evidence or {}).get("attempts", ()):
        grid = attempt.get("grid") or (attempt.get("inner_route") or {}).get("grid") or {}
        if grid.get("status") != "grid_exhausted":
            continue
        try:
            start, end, nearest = (tuple(float(v) for v in grid[k]) for k in
                ("route_start_mm", "route_end_mm", "nearest_frontier_mm"))
            if any(len(p) != 2 or not all(math.isfinite(v) for v in p)
                   for p in (start, end, nearest)):
                continue
            visited, limit = int(grid["visited"]), int(grid["max_visited"])
            span = math.dist(start, end)
            progress = math.dist(start, nearest)
            gap = math.dist(nearest, end)
            if (visited < 1 or visited >= limit or span <= 2*local_radius_mm
                    or progress > max(local_radius_mm, max_progress_fraction*span)
                    or gap < 0.5*span):
                continue
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        portal = attempt.get("start") or {}
        key = portal_geometry_key(portal)
        if key is not None and key not in found:
            found[key] = {"portal_key": list(key), "visited": visited,
                          "span_mm": round(span, 6), "progress_mm": round(progress, 6),
                          "frontier_gap_mm": round(gap, 6),
                          "blockers": list(grid.get("dominant_blockers") or ())[:8],
                          "kind": "exhausted_local_start_pocket"}
    return list(found.values())
