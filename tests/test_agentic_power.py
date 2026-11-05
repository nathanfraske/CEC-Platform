"""Model-authored power edits must pass literal native typed receiving."""

import copy
import json
from pathlib import Path

import pcbnew
import pytest

import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_planar_reflow as planar
import cec_redundant_force_branch as authority
from cec_pipeline import construction, power
from test_full_current_planar_reflow import fixture as route_fixture
from test_pad_bank_collector import fixture as bank_fixture
from test_field_proposals import track
from test_lastmile import _board


@pytest.mark.parametrize("quarter", range(4))
@pytest.mark.parametrize("restore_branch", [True, False])
def test_power_tree_reconstruction_must_restore_the_third_native_contact(
    tmp_path, monkeypatch, quarter, restore_branch
):
    net = f"/renamed_{quarter}/SUPPLY"

    def pose(p):
        x, y = p[0] - 15, p[1] - 15
        for _ in range(quarter):
            x, y = -y, x
        return 15 + x, 15 + y

    board = _board([(*pose(p), net) for p in ((5, 10), (10, 10))], edge=(0, 0, 30, 30))
    edges = [((5, 10), (5.5, 10.5)), ((5.5, 10.5), (7.5, 10.5)),
             ((7.5, 10.5), (9.5, 10.5)), ((9.5, 10.5), (10, 10)),
             ((7.5, 10.5), (7.5, 10))]
    cut = [track(board, net, pose(a), pose(b)) for a, b in edges]
    retained = track(board, net, pose((7.5, 10)), pose((7.5, 8)))
    source = tmp_path / "source.kicad_pcb"
    field._save_field_snapshot(board, source)
    contract = dict(net=net, required_by_layer_mm={"F.Cu": .2, "B.Cu": .2},
                    routing_layers=["F.Cu", "B.Cu"], current_authority=dict(
                        amps=.5, geometry_margin=1.25, margin_included=False,
                        source="board_design_basis"))
    monkeypatch.setattr(planar.topology, "route_width_contracts",
                        lambda *a, **kw: {net: copy.deepcopy(contract)})
    monkeypatch.setattr(planar.topology, "board_current_domains",
                        lambda *a, **kw: {net: dict(net=net, complete=True,
                            source_refs=["source"], sink_refs=["sink"])})
    candidate = force._copy_family(source, tmp_path / "authored")
    route = [(5, 10), (10, 10)] if restore_branch else [
        (5, 10), (5.5, 10.5), (9.5, 10.5), (10, 10)]
    operation = dict(kind="power_route", track_uuids=[force._uid(t) for t in cut],
                     points_nm=[[round(v * 1e6) for v in pose(p)] for p in route],
                     allow_locked_track_uuids=[])
    before = source.read_bytes()
    result = construction._construct(source, candidate, dict(operations=[operation]), "synthetic")
    proof = power.receive(source, candidate, operation, result["changes"][0], board_hint="synthetic")
    assert bool(proof["ok"] and proof["complete"]) is restore_branch, proof
    if not restore_branch:
        assert any("retired_endpoint" in e or "partition" in e
                   for e in proof["errors"]), proof
    assert len(result["changes"][0]["source_tree_leaves_nm"]) == 3
    saved = pcbnew.LoadBoard(str(candidate))
    assert force._uid(retained) in {force._uid(t) for t in saved.GetTracks()}
    assert source.read_bytes() == before


@pytest.mark.parametrize("edges", [
    [((1, 1), (2, 1)), ((3, 1), (4, 1))],
    [((1, 1), (2, 1)), ((2, 1), (2, 2)), ((2, 2), (1, 1))],
    [((1, 1), (2, 1)), ((2, 1), (1, 1))],
])
def test_power_tree_scope_rejects_disconnected_cyclic_and_duplicate_edges(edges):
    board = _board([], edge=(0, 0, 10, 10))
    tracks = [track(board, "/ANY_SUPPLY", a, b) for a, b in edges]
    with pytest.raises(ValueError):
        power._source_tree(tracks)


def test_contour_preserves_distinct_source_load_and_larger_routing_budget(tmp_path, monkeypatch):
    source, _, _, net, contract, domains = route_fixture(tmp_path)
    board = pcbnew.LoadBoard(str(source))
    zone = pcbnew.ZONE(board)
    zone.SetLayer(pcbnew.In1_Cu)
    zone.SetMinThickness(100000)
    board.Add(zone)
    domains[net]["amps"] = .4
    contract["amps"] = .5
    monkeypatch.setattr(planar.topology, "board_current_domains", lambda *a, **kw: copy.deepcopy(domains))
    monkeypatch.setattr(planar.topology, "route_width_contracts", lambda *a, **kw: {net: copy.deepcopy(contract)})
    operation = dict(track_uuids=[force._uid(t) for t in board.GetTracks()])
    model = power.parameters(board, source, operation, "synthetic")
    assert model["current_domain"]["amps"] == .4
    assert model["unchanged_current_contract"]["amps"] == .5
    assert model["unchanged_current_contract"]["current_authority"]["geometry_margin"] == 1.25
    assert model["required_width_nm"] == 200000
    domains[net]["complete"] = False
    with pytest.raises(ValueError, match="complete_existing"):
        power.parameters(board, source, operation, "synthetic")


@pytest.mark.parametrize("quarter", range(4))
def test_full_current_model_authored_shortcut_receives_actual_saved_path(
    tmp_path, monkeypatch, quarter
):
    straight, detour, uid, net, contract, domains = route_fixture(
        tmp_path, quarter=quarter
    )
    detour = Path(detour)
    parent = pcbnew.LoadBoard(str(detour))
    ids = [force._uid(item) for item in parent.GetTracks()]
    straight_board = pcbnew.LoadBoard(str(straight))
    source_track = next(iter(straight_board.GetTracks()))
    points = [list(source_track.GetStart()), list(source_track.GetEnd())]
    monkeypatch.setattr(
        planar.topology,
        "route_width_contracts",
        lambda *args, **kwargs: {net: copy.deepcopy(contract)},
    )
    monkeypatch.setattr(
        planar.topology,
        "board_current_domains",
        lambda *args, **kwargs: copy.deepcopy(domains),
    )
    candidate = force._copy_family(detour, tmp_path / "authored")
    operation = dict(
        kind="power_route",
        track_uuids=ids,
        points_nm=points,
        allow_locked_track_uuids=[],
    )
    before = detour.read_bytes()
    result = construction._construct(
        detour, candidate, dict(operations=[operation]), "synthetic"
    )
    proof = power.receive(
        detour, candidate, operation, result["changes"][0], board_hint="synthetic"
    )
    assert proof["ok"] and proof["complete"], proof
    assert result["changes"][0]["saved_centerline_mm"] > 0
    assert detour.read_bytes() == before


@pytest.mark.parametrize("quarter,back", [(0, False), (1, True), (2, False), (3, True)])
def test_chamfered_pad_bank_is_literal_solid_saved_copper_not_a_plot(
    tmp_path, monkeypatch, quarter, back
):
    board, pads, tracks = bank_fixture(
        quarter * 90, False, pcbnew.B_Cu if back else pcbnew.F_Cu
    )
    board.GetDesignSettings().m_MinClearance = 200000
    zone = pcbnew.ZONE(board)
    zone.SetNet(board.FindNet(str(pads[0].GetNetname())))
    zone.SetLayer(pcbnew.In2_Cu)
    zone.SetMinThickness(200000)
    zone.Outline().NewOutline()
    for p in (
        (25000000, 25000000),
        (55000000, 25000000),
        (55000000, 55000000),
        (25000000, 55000000),
    ):
        zone.Outline().Append(*p)
    board.Add(zone)
    assert pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    source = tmp_path / "source.kicad_pcb"
    field._save_field_snapshot(board, source)
    source.with_suffix(".kicad_pro").write_text(
        json.dumps(
            dict(
                net_settings=dict(
                    classes=[
                        dict(
                            name="Default",
                            clearance=0.2,
                            track_width=0.2,
                            via_diameter=0.6,
                            via_drill=0.3,
                        )
                    ]
                )
            )
        )
    )
    monkeypatch.setattr(
        authority,
        "_model",
        lambda *args: (dict(complete=True), dict(source="synthetic_fixture_only")),
    )
    candidate = force._copy_family(source, tmp_path / "authored")
    operation = dict(
        kind="bank_collector",
        pad_uuids=[force._uid(p) for p in pads],
        support_track_uuids=[force._uid(t) for t in tracks],
        layer="B.Cu" if back else "F.Cu",
        chamfer_nm=300000,
    )
    before = source.read_bytes()
    result = construction._construct(
        source, candidate, dict(operations=[operation]), "synthetic"
    )
    proof = power.receive(
        source, candidate, operation, result["changes"][0], board_hint="synthetic"
    )
    assert proof["ok"] and proof["complete"], proof
    assert source.read_bytes() == before and not result["release_authority"]
