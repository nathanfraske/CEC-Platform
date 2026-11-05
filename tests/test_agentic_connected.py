"""Actual saved native macro construction, never a model-authored pass flag."""

import copy
import json
from pathlib import Path

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_complete_cell_receiving as receiving
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_planar_reflow as planar
import cec_native_contour_receiving as contour_receiving
import cec_redundant_force_branch as authority
from cec_pipeline import construction, geometry, power
from cec_pipeline.cells import preview
from test_complete_cell_receiving import saved_pair
from test_complete_cell_connections import native_source
from test_native_contour_regions import board as contour_board


def cell_order(source, reference_child, proposal):
    parent, child = [pcbnew.LoadBoard(str(path)) for path in (source, reference_child)]
    ids = {str(track.m_Uuid.AsString()) for track in parent.GetTracks()}
    poses = []
    for ref in proposal["poses"]:
        footprint = child.FindFootprintByReference(ref)
        poses.append(
            dict(
                reference=ref,
                at_nm=list(footprint.GetPosition()),
                rotation_deg=round(footprint.GetOrientationDegrees()),
            )
        )
    routes = []
    for track in child.GetTracks():
        if str(track.m_Uuid.AsString()) in ids:
            continue
        assert track.GetClass() == "PCB_TRACK"
        points = [list(track.GetStart()), list(track.GetEnd())]
        if not geometry.heading(*points):
            # Deterministic synthetic fixture construction only. Production
            # callers receive ports and author their own explicit path.
            points = geometry.direct_paths(*points, minimum_phase_nm=20000)[0]
        routes.append(
            dict(
                net=str(track.GetNetname()),
                layer=str(pcbnew.BOARD.GetStandardLayerName(track.GetLayer())),
                width_nm=int(track.GetWidth()),
                points_nm=points,
            )
        )
    return dict(
        kind="place_cell",
        poses=poses,
        routes=routes,
        vias=[],
        max_shift_nm=6000000,
        allow_locked_track_uuids=[],
        allow_locked_footprint_uuids=[],
    )


@pytest.mark.parametrize("quarter", [0, 1, 2, 3])
def test_connected_cell_reconstructs_from_authored_ports_and_receives_saved_source(
    tmp_path, monkeypatch, quarter
):
    source, reference, proposal = saved_pair(tmp_path, monkeypatch, quarter)
    operation = cell_order(source, reference, proposal)
    request = dict(
        intent="Move the source-selected ceramic toward its original Ground return, keeping its owner.",
        operations=[operation],
    )
    candidate = force._copy_family(source, source.parent / "authored")
    before = source.read_bytes()
    observation = preview(source, operation, "opaque")
    assert observation["ok"] and observation["source_owned_connections"]
    record = construction._construct(source, candidate, request, "opaque")
    assert record["transaction_kind"] == "place_cell" and not record["ordinary_only"]
    proof = receiving.receive(source, candidate, board_hint="opaque")
    assert proof["ok"] and proof["complete"], proof
    assert proof["all_original_surviving_native_partitions_preserved"]
    assert proof["all_source_ground_returns"]["ok"]
    assert source.read_bytes() == before and not record["release_authority"]


def test_incomplete_authored_cell_cannot_be_selected_by_connectivity_claim(
    tmp_path, monkeypatch
):
    source, reference, proposal = saved_pair(tmp_path, monkeypatch)
    operation = cell_order(source, reference, proposal)
    operation["routes"] = []
    candidate = force._copy_family(source, source.parent / "missing-restoration")
    construction._construct(source, candidate, dict(operations=[operation]), "opaque")
    proof = receiving.receive(source, candidate, board_hint="opaque")
    assert not proof["ok"] and proof["errors"]


def test_scratch_fixture_does_not_require_implicit_project_side_effect(tmp_path, monkeypatch):
    save = pcbnew.SaveBoard

    def without_implicit_project(filename, board, *args, **kwargs):
        result = save(filename, board, *args, **kwargs)
        path = Path(filename)
        if path.name == "seed-native-source.kicad_pcb":
            assert path.parent == tmp_path
            path.with_suffix(".kicad_pro").unlink(missing_ok=True)
        return result

    monkeypatch.setattr(pcbnew, "SaveBoard", without_implicit_project)
    source, parent, _, _ = native_source(tmp_path, monkeypatch)
    assert source.with_suffix(".kicad_pro").is_file()
    assert parent.GetDesignSettings().m_MinClearance == 200000
    assert parent.GetDesignSettings().m_NetSettings.GetDefaultNetclass().GetTrackWidth() == 200000


@pytest.mark.parametrize("style", ["square", "chamfer45"])
def test_source_current_floor_and_real_saved_fill_receive_power_contours(
    tmp_path, monkeypatch, style
):
    board, tracks = contour_board()
    for index, fp in enumerate(board.GetFootprints()):
        fp.SetReference("GENERIC_PORT_" + str(index))
    ground = pcbnew.NETINFO_ITEM(board, "GND")
    board.Add(ground)
    zone = pcbnew.ZONE(board)
    zone.SetNet(ground)
    zone.SetLayer(pcbnew.In1_Cu)
    zone.SetMinThickness(100000)
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    outline = pcbnew.SHAPE_POLY_SET()
    outline.NewOutline()
    for point in (
        (1000000, 1000000),
        (5000000, 1000000),
        (5000000, 5000000),
        (1000000, 5000000),
    ):
        outline.Append(*point)
    zone.Outline().Append(outline)
    board.Add(zone)
    assert pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    source = tmp_path / "board.kicad_pcb"
    field._save_field_snapshot(board, source)
    # A valid source can have a different literal property order than KiCad's
    # serializer. Unrelated fields must remain source-exact across the edit.
    root, nodes = additive._nodes(source)
    footprint = next(node for node in nodes.values() if node[0] == "footprint")
    reference = next(node for node in footprint if isinstance(node, list)
                     and node[:2] == ["property", '"Reference"'])
    reference[:] = [node for node in reference if not isinstance(node, list) or node[0] != "hide"]
    reference.append(["hide", "yes"])
    source.write_text(additive._render(root) + "\n")
    # The numerical values are synthetic source contracts for this test, not
    # a change to any production board's current budget or qualification.
    model = (
        dict(net="/ARBITRARY_POWER", amps=1.0, complete=True, source_refs=("source",), sink_refs=("sink",)),
        dict(net="/ARBITRARY_POWER", amps=1.0, required_by_layer_mm={"F.Cu": 1.5}, routing_layers=("F.Cu", "B.Cu")),
    )
    monkeypatch.setattr(planar, "_model", lambda *args: ("aggregate_source_sink", *copy.deepcopy(model)))
    operation = dict(
        kind="power_contour",
        track_uuids=[str(track.m_Uuid.AsString()) for track in tracks],
        style=style,
        allow_locked_track_uuids=[],
        allow_grouped_track_uuids=[],
    )
    candidate = force._copy_family(source, tmp_path / "private")
    before = source.read_bytes()
    record = construction._construct(
        source, candidate, dict(operations=[operation]), "synthetic"
    )
    change = record["changes"][0]
    proof = contour_receiving.receive_literal_phase(
        source, candidate, [change["contour_record"]], board_hint="synthetic"
    )
    assert proof["ok"] and proof["complete"], proof
    assert proof["exact_source_phase_and_ground_refill_received"]
    assert change["source_current_model"]["required_width_nm"] == 1500000
    # Real workers cross JSON boundaries: tuples must compare by canonical
    # JSON identity, without ignoring any contract value or numeric type.
    saved_change = json.loads(json.dumps(change))
    received = power.receive(source, candidate, operation, saved_change, board_hint="synthetic")
    assert received["ok"] and received["complete"], received
    assert (
        source.read_bytes() == before
        and not change["new_current_or_thermal_qualification"]
    )
    model[1]["required_by_layer_mm"]["F.Cu"] = 2.5
    with pytest.raises(ValueError, match="requirement_changed"):
        power.receive(source, candidate, operation, change, board_hint="synthetic")
