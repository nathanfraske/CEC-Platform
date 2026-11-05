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
