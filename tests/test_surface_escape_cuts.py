"""Layer-owned, bounded pin-escape negotiations; no board-specific dispatch."""
import copy
from dataclasses import replace

import pcbnew
import pytest

import cec_certificate_repair as repair


def track(uid):
    return {"kind": "track", "uuid": uid}


def ray(direction, *blockers):
    return {"direction": direction, "status": "foreign_copper_blocked",
            "blockers": list(blockers)}


def certificate(side="F.Cu"):
    return {"layers": [
        {"layer": side, "endpoint_escape": [{"endpoint": "a",
            "clear_rays": [], "ray_details": [
                ray("N", track("local")),
                ray("W", track("local"), track("second")),
                ray("E", track("fixed")),
                ray("S", track("local"), {"kind": "pad"})]}]},
        {"layer": "INNER", "endpoint_escape": [{"endpoint": "a",
            "clear_rays": ["N"], "ray_details": [ray("E", track("remote"))]}]}]}


@pytest.mark.parametrize("side", ["F.Cu", "B.Cu"])
def test_only_complete_movable_surface_cuts_not_inner_histogram(side):
    assert repair._surface_escape_cut_sets(
        certificate(side), {"a": {side}}, {"a"},
        {"local", "second", "remote"}, max_blockers=2) == [
            ("local",), ("local", "second")]


def test_cut_is_never_truncated_or_fixed_member_ignored():
    cert = certificate()
    cert["layers"][0]["endpoint_escape"][0]["ray_details"] = [
        ray("N", track("local"), track("second")),
        ray("S", track("local"), track("fixed"))]
    assert not repair._surface_escape_cut_sets(
        cert, {"a": {"F.Cu"}}, {"a"}, {"local", "second"}, max_blockers=1)


def test_edge_blocked_and_unbound_or_untrapped_surfaces_are_not_cut_authority():
    cert = certificate()
    for layer in cert["layers"]:
        for endpoint in layer["endpoint_escape"]:
            for row in endpoint["ray_details"]:
                row["status"] = "board_edge_blocked"
    assert not repair._surface_escape_cut_sets(
        cert, {"a": {"F.Cu"}}, {"a"}, {"local", "second"}, max_blockers=2)
    assert not repair._surface_escape_cut_sets(
        certificate(), {}, {"a"}, {"local"}, max_blockers=2)
    assert not repair._surface_escape_cut_sets(
        certificate(), {"a": {"F.Cu"}}, set(), {"local"}, max_blockers=2)


def test_duplicate_cuts_are_deterministic_and_bounded():
    cert = certificate()
    endpoint = cert["layers"][0]["endpoint_escape"][0]
    endpoint["ray_details"] = [ray(str(i), track(str(i))) for i in range(10)] * 2
    before = copy.deepcopy(cert)
    cuts = repair._surface_escape_cut_sets(
        cert, {"a": {"F.Cu"}}, {"a"}, {str(i) for i in range(10)},
        max_blockers=2, limit=99)
    assert cuts == [("0",), ("1",), ("2",), ("3",)]
    assert cert == before


def test_cut_variants_cannot_expand_into_neighbouring_via_dogbones():
    window = repair.NegotiationWindow(
        net="test", distance_mm=3, width_mm=.2, clearance_mm=.2,
        blocker_uuids=("local",), blocker_nets=("other",), blocker_hits=1,
        omitted_movable_blockers=0, fixed_blocker_hits=0, trapped_endpoints=1,
        endpoints=(), priority=(), local_pin_escape=True, surface_escape_cut=True)
    variants = repair._atomic_negotiation_variants(window, True)
    assert len(variants) == 4
    assert all(row[2] == 0 for row in variants)
    assert {row[3] for row in variants} == {False, True}
    assert repair._atomic_negotiation_variants(
        replace(window, surface_escape_cut=False), True)[0][2] == 2


@pytest.mark.parametrize("side", [pcbnew.F_Cu, pcbnew.B_Cu])
def test_planner_ranks_actual_trapped_surface_and_keeps_broad_fallback(tmp_path, side):
    board = pcbnew.CreateEmptyBoard()
    target = pcbnew.NETINFO_ITEM(board, "test-open")
    obstacle = pcbnew.NETINFO_ITEM(board, "test-other")
    board.Add(target)
    board.Add(obstacle)
    fp = pcbnew.FOOTPRINT(board)
    fp.SetReference("X77")
    board.Add(fp)
    pad = pcbnew.PAD(fp)
    pad.SetNumber("8")
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetSize(pcbnew.VECTOR2I_MM(.3, .7))
    pad.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
    layers = pcbnew.LSET()
    layers.AddLayer(side)
    pad.SetLayerSet(layers)
    pad.SetNet(target)
    fp.Add(pad)
    ids = []
    for i, layer in enumerate((side, pcbnew.B_Cu if side == pcbnew.F_Cu else pcbnew.F_Cu)):
        item = pcbnew.PCB_TRACK(board)
        item.SetNet(obstacle)
        item.SetLayer(layer)
        item.SetWidth(pcbnew.FromMM(.2))
        item.SetStart(pcbnew.VECTOR2I_MM(9, 9-i))
        item.SetEnd(pcbnew.VECTOR2I_MM(11, 9-i))
        board.Add(item)
        ids.append(repair._uuid(item))
    path = str(tmp_path / "renamed-board.kicad_pcb")
    pcbnew.SaveBoard(path, board)
    owned = board.GetLayerName(side)
    remote = board.GetLayerName(pcbnew.B_Cu if side == pcbnew.F_Cu else pcbnew.F_Cu)
    cert = {"schema": 1, "net": "test-open", "width_mm": .2,
        "clearance_mm": .2,
        "endpoints": [{"endpoint": "a", "kind": "pad", "ref": "X77",
                       "pad": "8", "x_mm": 10, "y_mm": 10}],
        "dominant_blockers": [{**track(ids[1]), "hit_count": 99}],
        "layers": [
            {"layer": owned, "endpoint_escape": [{"endpoint": "a", "clear_rays": [],
                "ray_details": [ray("N", track(ids[0]))]}]},
            {"layer": remote, "endpoint_escape": [{"endpoint": "a", "clear_rays": ["W"],
                "ray_details": [ray("E", track(ids[1]))]}]}]}
    completion = {"refused_details": [{"net": "test-open", "distance_mm": 3,
                                       "certificate": cert}]}
    plan = repair.plan_negotiations(path, completion, limit=8, max_blockers_per_window=2)
    first = plan["windows"][0]
    assert first["surface_escape_cut"]
    assert first["trapped_endpoints"] == 1
    assert first["blocker_uuids"] == (ids[0],)
    assert any(set(row["blocker_uuids"]) == set(ids)
               for row in plan["windows"] if not row["surface_escape_cut"])
