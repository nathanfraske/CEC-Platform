"""Every restoration topology gets real time, without enlarging the deadline."""
from unittest.mock import Mock

import pytest
import cec_certificate_repair as repair


def row(net="/other/branch", uid="branch", width=200000, length=1000000):
    return dict(net=net, requested_uuid=uid, width=width, source_length_nm=length,
        removed_uuids=[uid], start_escape=None, end_escape=None,
        start_xy=[0, 0], end_xy=[length, 0], net_code=1, layer=0)


@pytest.mark.parametrize("count", [1, 2, 4])
def test_exact_boundaries_cannot_consume_network_fallback(monkeypatch, count):
    now = [100.0]
    monkeypatch.setattr(repair.time, "monotonic", lambda: now[0])
    exact_calls, network_calls = [], []
    def exact(board, snapshot, **args):
        exact_calls.append(args["deadline_monotonic"])
        now[0] = args["deadline_monotonic"]
        return False, {"refusal": "displaced_branch_restore_timeout"}
    def network(board, snapshot, **args):
        network_calls.append((now[0], args["deadline_monotonic"]))
        return True, {"mode": "network_lastmile"}
    monkeypatch.setattr(repair, "_restore_displaced_branch", exact)
    monkeypatch.setattr(repair, "_restore_displaced_net", network)
    ok, evidence = repair._restore_negotiation_blockers(Mock(),
        [row(uid=str(i)) for i in range(count)], board_path="unused",
        maze_margin_mm=4, max_detour_ratio=2, wall_timeout_s=20)
    assert ok and len(exact_calls) == count
    assert max(exact_calls) == pytest.approx(112.0)
    assert network_calls == [(112.0, 120.0)]
    assert evidence["restored"][0]["search_budget"]["fallback_reserve_s"] == 8.0


def test_separate_nets_receive_bounded_nonoverlapping_time(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(repair.time, "monotonic", lambda: now[0])
    events = []
    def exact(board, snapshot, **args):
        events.append(("exact", now[0], args["deadline_monotonic"]))
        now[0] = args["deadline_monotonic"]
        return False, {"refusal": "displaced_branch_restore_timeout"}
    def network(board, snapshot, **args):
        events.append(("network", now[0], args["deadline_monotonic"]))
        now[0] = args["deadline_monotonic"]
        return True, {"mode": "network_lastmile"}
    monkeypatch.setattr(repair, "_restore_displaced_branch", exact)
    monkeypatch.setattr(repair, "_restore_displaced_net", network)
    ok, _ = repair._restore_negotiation_blockers(Mock(),
        [row(net="/A"), row(net="/B")], board_path="unused",
        maze_margin_mm=4, max_detour_ratio=2, wall_timeout_s=20)
    assert ok
    assert events == [("exact", 100.0, 106.0), ("network", 106.0, 110.0),
                      ("exact", 110.0, 116.0), ("network", 116.0, 120.0)]


def test_no_worker_phase_starts_after_deadline(monkeypatch):
    exact, network = Mock(), Mock()
    monkeypatch.setattr(repair, "_restore_displaced_branch", exact)
    monkeypatch.setattr(repair, "_restore_displaced_net", network)
    ok, evidence = repair._restore_negotiation_blockers(Mock(), [row()],
        board_path="unused", maze_margin_mm=4, max_detour_ratio=2,
        wall_timeout_s=0)
    assert not ok and evidence["refusal"] == "displaced_net_restore_timeout"
    exact.assert_not_called()
    network.assert_not_called()


def test_fast_exact_success_does_not_force_fallback(monkeypatch):
    network = Mock()
    monkeypatch.setattr(repair, "_restore_displaced_branch", Mock(return_value=(True, {})))
    monkeypatch.setattr(repair, "_restore_displaced_net", network)
    assert repair._restore_negotiation_blockers(Mock(), [row()],
        board_path="unused", maze_margin_mm=4, max_detour_ratio=2,
        wall_timeout_s=20)[0]
    network.assert_not_called()


@pytest.mark.parametrize("fraction", [0, 1, -1, float("nan"), float("inf")])
def test_invalid_budget_fraction_fails_before_mutating_board(fraction):
    with pytest.raises(ValueError):
        repair._restore_negotiation_blockers(Mock(), [], board_path="unused",
            maze_margin_mm=4, max_detour_ratio=2, exact_budget_fraction=fraction)


def test_identical_net_group_orders_are_not_repeated():
    assert repair._restore_order_modes([]) == ("hardest_first",)
    assert repair._restore_order_modes([row()]) == ("hardest_first",)
    assert repair._restore_order_modes([row(uid="a"), row(uid="b", width=400000)]) == ("hardest_first",)
    assert repair._restore_order_modes([row(net="/A"), row(net="/B")]) == ("hardest_first",)
    assert repair._restore_order_modes([row(net="/A"), row(net="/B", width=400000)]) == (
        "hardest_first", "easiest_first")


@pytest.mark.parametrize("domain", [40.0, 80.0])
def test_live_network_domain_is_not_truncated_to_removed_fragment(monkeypatch, domain):
    now = [100.0]
    monkeypatch.setattr(repair.time, "monotonic", lambda: now[0])
    board = Mock()
    board.GetTracks.return_value = []
    board.GetNetcodeFromNetname.return_value = 1
    calls = []
    def synthesize(board, **args):
        calls.append(args)
        now[0] += args["wall_timeout_s"]
        return {"closed": 0}
    monkeypatch.setattr(repair.cec_fr, "_project_netclass_resolver", lambda _: lambda n: {})
    monkeypatch.setattr(repair.cec_fr, "synthesize_lastmile", synthesize)
    monkeypatch.setattr(repair.cec_fr, "net_connectivity_component_count", lambda *a: 2)
    ok, evidence = repair._restore_displaced_net(board,
        repair._snapshot_from_row(row(length=500000)),
        board_path="unused", maze_margin_mm=4, deadline_monotonic=102,
        max_route_mm=domain)
    assert not ok and len(calls) == 2
    assert [c["max_mm"] for c in calls] == [domain, domain]
    assert calls[1]["maze_max_mm"] == domain
    assert calls[0]["wall_timeout_s"] == 1.2  # No four-second floor past deadline.
    assert calls[1]["wall_timeout_s"] == pytest.approx(0.8)
    assert now[0] == pytest.approx(102)
    assert evidence["completion"]["residual_search_domain_mm"] == domain


@pytest.mark.parametrize("domain", [0, 81, float("nan")])
def test_invalid_network_domain_is_rejected_before_inspecting_board(domain):
    board = Mock()
    with pytest.raises(ValueError):
        repair._restore_displaced_net(board, {}, board_path="unused",
            maze_margin_mm=4, max_route_mm=domain)
    board.GetTracks.assert_not_called()
