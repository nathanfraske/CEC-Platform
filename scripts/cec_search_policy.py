#!/usr/bin/env python3
"""Deterministic plateau-directed search-family allocation.

Repeated seeds are useful until the objective stops improving.  After that,
the manager must change a physical/search assumption rather than loop over the
same family indefinitely.  This pure policy emits each bounded family at most
once per incumbent and then returns an explicit stop decision.
"""

from __future__ import annotations

import cec_outline_compaction


MAX_ROUTE_CANDIDATES = 8
MAX_PLACEMENT_CANDIDATES = 16
MAX_UNATTENDED_ROUNDS = 32


def bounded_round_budget(value, *, cap=MAX_UNATTENDED_ROUNDS):
    """Validate one explicit unattended-loop budget.

    A wall-clock deadline is still useful operationally, but it is not a
    search-space bound: a fast failure can otherwise spin for the entire
    window.  Every manager therefore also purchases a finite round budget.
    """
    rounds = int(value)
    cap = max(1, int(cap))
    if rounds < 1:
        raise ValueError("unattended round budget must be positive")
    if rounds > cap:
        raise ValueError(
            "unattended round budget %d exceeds hard cap %d" %
            (rounds, cap))
    return rounds


def incumbent_signature(metadata):
    """Return the durable identity of a published canonical incumbent."""
    row = dict(metadata or {})
    return (
        row.get("source"),
        row.get("updated"),
        tuple(row.get("sort_key") or ()),
        row.get("schematic_match"),
        row.get("mezzanine_contract_ok"),
        row.get("routed"),
    )


def incumbent_transition(previous, current, *, declared_updated=False):
    """Classify one wave against canonical candidate admission.

    Wave-local ranking is intentionally absent.  Progress occurs only when the
    canonical publisher changed the durable incumbent and the wave report says
    that it did.  A disagreement means another writer or incomplete provenance,
    so unattended search must stop rather than manufacture a false improvement.
    """
    before = dict(previous or {})
    after = dict(current or {})
    changed = incumbent_signature(before) != incumbent_signature(after)
    declared = bool(declared_updated)
    consistent = changed == declared
    before_key = tuple(before.get("sort_key") or ())
    after_key = tuple(after.get("sort_key") or ())
    return {
        "accepted": bool(changed and declared and consistent),
        "changed": changed,
        "declared_updated": declared,
        "consistent": consistent,
        "score_improved": bool(
            changed and before_key and after_key and after_key < before_key),
        "previous_sort_key": list(before_key),
        "sort_key": list(after_key),
        "source": after.get("source"),
        "reason": after.get("reason"),
        "gate": bool(after.get("route_gate_passed") or
                     (after.get("grade") or {}).get("gate")),
    }


def bounded_placement_plan(
        strategies, seeds, *, cap=MAX_PLACEMENT_CANDIDATES):
    """Return the finite placement strategy/seed product or reject it."""
    strategies = tuple(str(value) for value in strategies or ()
                       if str(value))
    seeds = tuple(int(value) for value in seeds or ())
    if not strategies or not seeds:
        raise ValueError("placement search requires strategies and seeds")
    plan = tuple((strategy, seed)
                 for strategy in strategies for seed in seeds)
    cap = max(1, int(cap))
    if len(plan) > cap:
        raise ValueError(
            "placement candidate budget %d exceeds hard cap %d" %
            (len(plan), cap))
    return plan


def bounded_seed_plan(base_seed, count, *, cap=MAX_ROUTE_CANDIDATES):
    """Return a deterministic, finite route ensemble.

    This is deliberately not an adaptive while-loop. A caller purchases one
    explicit candidate budget, all seeds are known before work starts, and the
    cap prevents a difficult fixture from becoming an unbounded board-specific
    grind.
    """
    cap = max(1, int(cap))
    count = max(1, int(count))
    if count > cap:
        raise ValueError(
            "route candidate budget %d exceeds hard cap %d" % (count, cap))
    first = int(base_seed)
    return tuple(first + offset for offset in range(count))


def candidate_rank(result):
    """Board-agnostic total order for independently routed candidates."""
    result = dict(result or {})
    native = result.get("sort_key")
    if not isinstance(native, (list, tuple)):
        native = ()
    numeric = []
    for value in native:
        try:
            numeric.append(float(value))
        except (TypeError, ValueError):
            numeric.append(float("inf"))
    blockers = result.get("blocker_summary") or {}

    def _count(value):
        # Route-oracle schema uses exact net-name lists while older wave
        # summaries stored counts.  Ranking accepts both representations so a
        # successfully graded artifact can never be lost at the coordinator
        # boundary merely because it retained richer evidence.
        if isinstance(value, (list, tuple, set, frozenset, dict)):
            return len(value)
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    return (
        0 if result.get("gate") else 1,
        *numeric,
        _count(result.get("unconn_critical")),
        _count(result.get("drc")),
        _count(result.get("unconnected")),
        _count(blockers.get("blocking_count")),
        _count(result.get("seed")),
    )


def select_candidate(results):
    """Select the best completed route without referring to board identity."""
    eligible = [dict(row) for row in (results or ())
                if row and row.get("routed")]
    if not eligible:
        return None
    return min(eligible, key=candidate_rank)


def next_action(*, plateau_streak, patience, used_families=(),
                completion_available=False, nominal_outline=None,
                outline_policy=None):
    """Choose the next untried family for one incumbent."""
    streak = max(0, int(plateau_streak))
    patience = max(1, int(patience))
    used = {str(value) for value in used_families or ()}
    if streak < patience:
        return {"family": "seed_diversity", "stop": False,
                "reason": "plateau patience not reached"}

    actions = []
    if completion_available:
        actions.append({
            "family": "completion_repair", "stop": False,
            "use_completion": True,
            "reason": "project detailed refusal certificates into placement"})
    if nominal_outline is not None:
        nominal = (float(nominal_outline[0]), float(nominal_outline[1]))
        for width, height in cec_outline_compaction.outline_candidates(
                nominal[0], nominal[1], outline_policy):
            if width * height >= nominal[0] * nominal[1] - 1e-9:
                continue
            family = "outline_%gx%g" % (width, height)
            actions.append({
                "family": family, "stop": False,
                "outline": [width, height],
                "reason": "test a smaller outline with size-aware anchors"})
    actions.extend((
        {"family": "broaden_shortlist", "stop": False, "prune": 8,
         "reason": "retain more geometrically distinct placements"},
        {"family": "precision_effort", "stop": False,
         "passes_delta": 4, "opt_delta": 6,
         "reason": "spend deeper route effort only after structural families"},
    ))
    for action in actions:
        if action["family"] not in used:
            return action
    return {
        "family": "stop", "stop": True,
        "reason": "all bounded search families exhausted for this incumbent",
    }
