"""Interrupted attempts are evidence, not proofs of impossible geometry."""
import copy

import pytest

from cec_search_completion import (
    annotate_refusal, pair_probe_completion, probe_is_inconclusive,
    search_completion_evidence,
)


@pytest.mark.parametrize("interruption", [
    {"deadline_exhausted": True}, {"pair_search_budget_exhausted": True},
    {"flow_leg_budget_exhausted": True}, {"timed_out": True},
    {"round_limit_reached": True},
    {"reason": "paired terminal search deadline exhausted"},
    {"refused": "paired portal search deadline exhausted"},
    {"status": "deadline_exhausted"}, {"error": "worker timed out"},
    {"rejection_counts": {"paired terminal search deadline exhausted": 4}},
    {"grid_status_counts": {"deadline_exhausted": 1}},
])
def test_nested_interruption_survives_false_parent_and_projection(interruption):
    raw = {"name": "arbitrary", "refused": "no coupled route",
           "pair_search_budget_exhausted": False,
           "attempts": [{"screened": {"end:-1": interruption}}]}
    before = copy.deepcopy(raw)
    annotated = annotate_refusal(raw)
    assert annotated["search_inconclusive"] is True
    assert annotated["pair_search_budget_exhausted"] is False
    assert annotated["search_completion"]["interruption_count"] >= 1
    projected = {key: annotated[key] for key in (
        "name", "refused", "pair_search_budget_exhausted",
        "search_inconclusive", "search_completion")}
    assert pair_probe_completion({"refused": [projected]})["inconclusive"]
    assert probe_is_inconclusive(dict(search_completion=projected["search_completion"]))
    assert raw == before


@pytest.mark.parametrize("finite", [
    {"status": "grid_exhausted"}, {"status": "search_exhausted"},
    {"reason": "deadline not reached"}, {"reason": "no legal portal"},
    {"refused": "no finite paired dogbone"},
    {"deadline_exhausted": False, "pair_search_budget_exhausted": False},
    {"rejection_counts": {"paired terminal search deadline exhausted": 0}},
    {"screened": {"domain_complete": False, "accepted": 8}},
    {"phase_budget_seconds": 120, "phase_wall_seconds": 119},
])
def test_finite_or_uninterrupted_search_is_not_a_timeout(finite):
    assert search_completion_evidence(finite)["inconclusive"] is False
    assert not probe_is_inconclusive({"search_completion": search_completion_evidence(finite)})


def test_all_evidence_is_scanned_even_after_witness_and_trace_limits():
    from cec_probe_evidence import compact_pair_search_trace
    raw = {"refused": "no route", "attempts": [
        {"phase_budget_seconds": 1, "deadline_exhausted": True}
        for _ in range(100)] + [{"reason": "worker timed out"}]}
    assert len(compact_pair_search_trace(raw, limit=2)) == 2
    summary = search_completion_evidence(raw, witness_limit=2)
    assert summary["interruption_count"] == 101
    assert len(summary["witnesses"]) == 2 and summary["truncated"]
    assert annotate_refusal(raw, witness_limit=0)["search_inconclusive"]


def test_deep_interruption_beyond_compact_trace_is_not_lost():
    from cec_probe_evidence import compact_pair_search_trace
    raw = {"refused": "no route", "attempts": [
        {"phase_budget_seconds": 1} for _ in range(100)] + [
        {"reason": "paired portal search deadline exhausted"}]}
    assert not search_completion_evidence(compact_pair_search_trace(raw, limit=32))["inconclusive"]
    assert annotate_refusal(raw)["search_inconclusive"]


def test_qualified_success_is_not_rejected_for_an_earlier_interrupted_attempt():
    row = {"name": "qualified", "route_mode": "admitted",
           "attempts": [{"refused": "worker timed out"}]}
    assert annotate_refusal(row) == row
    assert not pair_probe_completion({"routed": [row], "refused": []})["inconclusive"]


def test_probe_completion_uses_only_the_measured_pair_scope():
    failed = {"name": "unmeasured", "refused": "worker timed out"}
    complete = {"name": "measured", "refused": "grid exhausted"}
    report = {"refused": [failed, complete]}
    assert pair_probe_completion(report)["inconclusive"]
    assert not pair_probe_completion(report, pair_names=["measured"])["inconclusive"]
    assert not pair_probe_completion(report, pair_names=[])["inconclusive"]


def test_preflight_summarizes_before_discarding_nested_refusal():
    from unittest import mock
    import cec_fr
    import cec_precision_route
    import cec_route_preflight
    raw = {"name": "synthetic", "p": "/PLUS", "n": "/MINUS",
           "refused": "no route", "pair_search_budget_exhausted": False,
           "local_search": {"reason": "paired portal search deadline exhausted"}}
    with mock.patch.object(cec_fr, "owned_locked_nets", return_value=()), \
         mock.patch.object(cec_precision_route, "precision_route_board", return_value={
             "pairs_ok": False, "pairs": {"refused": [raw]}}), \
         mock.patch.object(cec_precision_route, "_pads_on_net", return_value=[]):
        report = cec_route_preflight._probe_critical_pairs_on_board(object(), "synthetic.kicad_pcb")
    row = report["refused"][0]
    assert "local_search" not in row
    assert row["search_inconclusive"]
    assert probe_is_inconclusive({"search_completion": pair_probe_completion(report)})


@pytest.mark.parametrize("interruption", [
    {"reason": "paired search deadline exhausted"},
    {"rejection_counts": {"paired terminal search deadline exhausted": 2}},
    {"pair_search_budget_exhausted": True},
])
def test_interrupted_local_query_cannot_poison_negative_cache(interruption):
    from unittest import mock
    from cec_portal_feedback import PortalProbeCache
    cache = PortalProbeCache()
    report = {"refused": "no paired dogbone", "admission": {"direct": {"p": {"ok": False}}},
              "nested": interruption}
    solve = mock.Mock(return_value=report)
    for _ in range(2):
        cache.probe("same-exact-geometry", solve, expired=lambda: False)
    assert solve.call_count == 2 and not cache.rows


def test_incomplete_cache_marker_is_not_needed_for_finite_negative_reuse():
    from cec_portal_feedback import PortalProbeCache
    assert PortalProbeCache.completed_negative({
        "refused": "no finite paired dogbone", "admission": {"direct": {"ok": False}},
        "grid": {"status": "grid_exhausted"}})


def test_probe_classifier_keeps_existing_checker_and_budget_failures():
    assert probe_is_inconclusive({"error": "native checker failed"})
    assert probe_is_inconclusive({"pair_search_budget_exhausted": True})
    assert not probe_is_inconclusive({"critical_route_refused_count": 1})
