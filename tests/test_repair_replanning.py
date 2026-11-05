"""Bounded dependency refresh, not a product-specific repair retry loop."""
import copy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_dimension_repair as repair
from test_dimension_repair import fixture, snapshots


def simulation(tmp_path, monkeypatch, *, refresh="changed", reject=False,
               initial_change=True, refreshed_refusal=False, max_seats=4, replans=1):
    path = tmp_path / "neutral.kicad_pcb"
    path.write_text("0")
    targets = [dict(uuid=name, boundary={"revision": 0},
                    seats_nm=[[i, 0] for i in range(max_seats)]) for name in ("first", "neighbor")]
    calls, search_calls = [], []
    def call(kind, board, payload, work, deadline, **kwargs):
        calls.append((kind, copy.deepcopy(payload), deadline))
        if kind == "plan":
            if "target_uuids" not in payload:
                return {"targets": targets if initial_change else targets[1:]}
            assert payload["target_uuids"] == ["neighbor"]
            assert payload["max_targets"] == 1
            if refresh == "timeout":
                raise TimeoutError("bounded refresh timeout")
            if refresh == "missing":
                return {"targets": [], "refused": [{"reason": "unknown_owner"}]}
            new = copy.deepcopy(targets[1])
            if refresh != "repeated":
                new["boundary"]["revision"] = 1
            if refresh == "wrong_target":
                new["uuid"] = "out-of-scope"
            return {"targets": [new]}
        if kind == "search":
            target = payload["target"]
            search_calls.append((target["uuid"], target["boundary"]["revision"],
                                 copy.deepcopy(payload["candidate_seats"])))
            changed = (target["uuid"] == "first" or target["boundary"]["revision"] == 1)
            if refreshed_refusal and target["boundary"]["revision"] == 1:
                return [{"uuid": target["uuid"], "mutation": {
                    "changed": False, "reason": "stale_boundary_or_owner"}}]
            if changed:
                Path(board).write_text(str(int(Path(board).read_text()) + 1))
            return [{"uuid": target["uuid"], "mutation": {
                "changed": changed, "reason": "stale_boundary_or_owner"}}]
        before, _ = snapshots()
        stage = int(Path(board).read_text())
        before["constraints"]["dimensions"] = ["fault-%s" % i for i in range(4 - stage)]
        if reject and stage == 2:
            before["constraints"]["assembly"] = ["new-overlap"]
        return before[kind]
    monkeypatch.setattr(repair, "_call", call)
    result = repair.repair_admitted(path, max_seats=max_seats, max_replans_per_target=replans)
    assert len({row[2] for row in calls}) == 1, "refresh must not reset the deadline"
    return path, result, calls, search_calls


def test_changed_neighbor_refreshes_only_after_admission_and_passes_independent_checks(tmp_path, monkeypatch):
    path, result, calls, searches = simulation(tmp_path, monkeypatch)
    assert path.read_text() == "2"
    assert len(result["accepted"]) == 2
    assert result["replans"][0]["status"] == "refreshed"
    assert result["replans"][0]["consumed_seats"] == 1
    assert [row[1] for row in searches] == [0, 0, 1]
    assert len(searches[-1][2]) == 3, "stale probe consumes original budget, not a fresh budget"
    assert result["attempts"][-1]["planned_generation"] == 1
    assert result["attempts"][-1]["admission"]["accepted"]
    assert sum(kind == "constraints" for kind, _payload, _deadline in calls) == 3


@pytest.mark.parametrize("refresh,reason", [("missing", "no_current_spatial_target"),
                                           ("repeated", "repeated_target_plan")])
def test_unavailable_or_repeated_plan_cannot_retry_forever(tmp_path, monkeypatch, refresh, reason):
    path, result, _calls, searches = simulation(tmp_path, monkeypatch, refresh=refresh)
    assert path.read_text() == "1"
    assert result["deferred_targets"][0]["reason"] == reason
    assert len(result["replans"]) == 1
    assert len(searches) == 2


@pytest.mark.parametrize("replans,seats,reason", [(0, 4, "replan_budget_exhausted"),
                                                (1, 1, "seat_budget_exhausted")])
def test_refresh_limits_do_not_reset_seat_or_target_scope(tmp_path, monkeypatch, replans, seats, reason):
    _path, result, _calls, searches = simulation(tmp_path, monkeypatch, replans=replans, max_seats=seats)
    assert not result["replans"]
    assert result["deferred_targets"][0]["reason"] == reason
    assert len(searches) == 2


@pytest.mark.parametrize("initial_change", [False, True])
def test_no_new_admitted_generation_means_no_refresh(tmp_path, monkeypatch, initial_change):
    _path, result, _calls, _searches = simulation(tmp_path, monkeypatch,
        initial_change=initial_change, refreshed_refusal=True)
    assert result["deferred_targets"][0]["reason"] == "stale_without_admitted_change"
    assert len(result["replans"]) == int(initial_change)


@pytest.mark.parametrize("refresh", ["timeout", "wrong_target"])
def test_refresh_failure_retains_only_prior_admitted_geometry(tmp_path, monkeypatch, refresh):
    path, result, _calls, _searches = simulation(tmp_path, monkeypatch, refresh=refresh)
    assert path.read_text() == "1"
    assert len(result["accepted"]) == 1
    assert result.get("stopped")


def test_refreshed_proposal_cannot_bypass_fault_identity_admission(tmp_path, monkeypatch):
    path, result, _calls, _searches = simulation(tmp_path, monkeypatch, reject=True)
    assert path.read_text() == "1"
    assert len(result["accepted"]) == 1
    assert any("new_assembly_identity" in row.get("admission", {}).get("reasons", ())
               for row in result["attempts"])
    assert len(result["attempts"]) == 5  # one first target + four neighbor seats total


def test_native_planner_filter_never_substitutes_a_different_target(tmp_path):
    path, _board, via, _branches, growth = fixture(tmp_path)
    assert not repair.plan(path, growth, target_uuids=["not-in-board"])["targets"]
    filtered = repair.plan(path, growth, target_uuids=[repair.uid(via)])
    assert [row["uuid"] for row in filtered["targets"]] == [repair.uid(via)]


@pytest.mark.parametrize("value", [-1, 1.5, float("nan")])
def test_invalid_refresh_budget_fails_before_touching_source(tmp_path, value):
    with pytest.raises(ValueError, match="budget"):
        repair.repair_admitted(tmp_path / "absent.kicad_pcb", max_replans_per_target=value)
