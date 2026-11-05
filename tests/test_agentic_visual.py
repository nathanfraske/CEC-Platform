"""Relevant visual evidence is distinct from physical qualification/attention."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pcbnew
import pytest

from cec_pipeline import visual, workbench
from cec_pipeline.identity import digest
from test_lastmile import _board
from test_field_proposals import track


def manifest(*rows):
    return dict(complete=True, regions=[dict(layer=face, region_nm=bounds)
                                       for face, bounds in rows], sha256="synthetic")


def write_view(root, layer, bounds):
    view = dict(layer=layer, region_nm=bounds, guide=None)
    view["key"] = digest(view)[:16]
    view["plot_hashes"] = {}
    x, y, right, bottom = bounds
    box = " ".join(str(v / 1e6) for v in (x, y, right - x, bottom - y))
    for side in ("before", "after"):
        name = side + "-" + layer.replace(".", "-") + "-" + view["key"] + ".svg"
        target = root / name
        target.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="' + box + '"/>')
        view["plot_hashes"][name] = workbench.inspection.sha(target)
    return view


def proof(*views):
    return dict(schema=2, views=list(views),
                plot_hashes={k: v for row in views for k, v in row["plot_hashes"].items()})


def test_wrong_layer_and_unrelated_crop_are_not_review_coverage():
    m = manifest(("F.Cu", [100, 200, 300, 400]))
    for view in (dict(layer="B.Cu", region_nm=[0, 0, 1000, 1000]),
                 dict(layer="F.Cu", region_nm=[500, 600, 1000, 1200])):
        assert not visual.coverage(m, [view])["ok"]
    assert visual.coverage(m, [dict(layer="F.Cu", region_nm=[0, 0, 1000, 1000])])["ok"]


def test_multiple_layers_require_all_views_and_keep_both_pairs(tmp_path):
    bounds = [1000000, 2000000, 5000000, 6000000]
    m = manifest(("F.Cu", bounds), ("B.Cu", bounds))
    first = write_view(tmp_path, "F.Cu", bounds)
    with pytest.raises(ValueError, match="not_covered"):
        visual.verify_views(proof(first), m, tmp_path)
    second = write_view(tmp_path, "B.Cu", bounds)
    covered = visual.verify_views(proof(first, second), m, tmp_path)
    assert covered["ok"] and covered["views"] == 2 and not covered["model_attention_proved"]


@pytest.mark.parametrize("damage", ["hash", "inventory", "pair", "viewport", "empty"])
def test_changed_incomplete_or_exaggerated_view_proof_refuses(tmp_path, damage):
    bounds = [1000000, 2000000, 5000000, 6000000]
    v = write_view(tmp_path, "F.Cu", bounds)
    p = proof(v)
    if damage == "hash":
        (tmp_path / next(iter(v["plot_hashes"]))).write_text("changed")
    elif damage == "inventory":
        p["plot_hashes"] = {}
    elif damage == "pair":
        del v["plot_hashes"][next(iter(v["plot_hashes"]))]
    elif damage == "viewport":
        # Keep a plausible native SVG and valid hashes, but make its actual
        # crop smaller than its metadata claims. This must not prove review.
        for name in v["plot_hashes"]:
            path = tmp_path / name
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="1 2 .1 .1"/>')
            v["plot_hashes"][name] = workbench.inspection.sha(path)
        p = proof(v)
    else:
        p = proof()
    with pytest.raises(ValueError):
        visual.verify_views(p, manifest(("F.Cu", bounds)), tmp_path)


def test_native_track_delta_is_on_actual_face_not_requested_face(tmp_path):
    board = _board([(2, 2, "CONTROL")], edge=(0, 0, 15, 15))
    item = track(board, "CONTROL", (3, 3), (7, 3), width=.2, layer=pcbnew.B_Cu)
    source, child = tmp_path / "source.kicad_pcb", tmp_path / "child.kicad_pcb"
    pcbnew.SaveBoard(str(source), board)
    item.SetEnd(pcbnew.VECTOR2I_MM(8, 4))
    pcbnew.SaveBoard(str(child), board)
    before = source.read_bytes()
    m = visual.changed_copper(source, child)
    assert {r["layer"] for r in m["regions"]} == {"B.Cu"}
    bounds = visual.default_region(m)
    assert visual.coverage(m, [dict(layer="B.Cu", region_nm=bounds)])["ok"]
    assert not visual.coverage(m, [dict(layer="F.Cu", region_nm=bounds)])["ok"]
    assert source.read_bytes() == before
    with pytest.raises(ValueError, match="actual_changed_copper"):
        visual.changed_copper(source, source)


def test_native_footprint_move_requires_pad_material_regions(tmp_path):
    board = _board([(4, 4, "CONTROL")], edge=(0, 0, 15, 15))
    fp = next(iter(board.GetFootprints()))
    source, child = tmp_path / "source.kicad_pcb", tmp_path / "child.kicad_pcb"
    pcbnew.SaveBoard(str(source), board)
    fp.SetPosition(pcbnew.VECTOR2I_MM(5, 4))
    pcbnew.SaveBoard(str(child), board)
    m = visual.changed_copper(source, child)
    assert {r["kind"] for r in m["regions"]} == {"FOOTPRINT"}
    assert {r["layer"] for r in m["regions"]} == {"F.Cu"}


def test_native_via_delta_requires_every_actual_copper_layer(tmp_path):
    board = _board([(4, 4, "CONTROL")], edge=(0, 0, 15, 15))
    source, child = tmp_path / "source.kicad_pcb", tmp_path / "child.kicad_pcb"
    pcbnew.SaveBoard(str(source), board)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(8, 8))
    via.SetWidth(600000)
    via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(board.FindNet("CONTROL"))
    board.Add(via)
    pcbnew.SaveBoard(str(child), board)
    m = visual.changed_copper(source, child)
    assert {r["layer"] for r in m["regions"]} == {
        str(pcbnew.BOARD.GetStandardLayerName(l)) for l in board.GetEnabledLayers().CuStack()}


def test_saved_fill_changes_are_reviewed_on_the_reference_layer(tmp_path):
    board = _board([(4, 4, "GND")], edge=(0, 0, 15, 15))
    zone = pcbnew.ZONE(board)
    zone.SetNet(board.FindNet("GND"))
    zone.SetLayer(pcbnew.In1_Cu)
    zone.SetMinThickness(100000)
    zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    outline = zone.Outline()
    outline.NewOutline()
    for p in ((1, 1), (13, 1), (13, 13), (1, 13)):
        outline.Append(p[0] * 1000000, p[1] * 1000000)
    board.Add(zone)
    assert pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    source, child = tmp_path / "source.kicad_pcb", tmp_path / "child.kicad_pcb"
    pcbnew.SaveBoard(str(source), board)
    zone.Move(pcbnew.VECTOR2I_MM(0.5, 0))
    assert pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(child), board)
    m = visual.changed_copper(source, child)
    assert {r["kind"] for r in m["regions"]} == {"ZONE"}
    assert {r["layer"] for r in m["regions"]} == {"In1.Cu"}


def test_selection_cannot_use_a_valid_plot_of_an_unrelated_corner(tmp_path):
    source, child = tmp_path / "source", tmp_path / "child"
    source.write_text("before")
    child.write_text("after")
    path = tmp_path / "job.json"
    path.write_text("{}")
    data = dict(source=str(source), candidate=str(child),
                source_sha256=workbench.inspection.sha(source))
    m = manifest(("F.Cu", [1000000, 1000000, 3000000, 3000000]))
    verdict = dict(ok=True, candidate_sha256=workbench.inspection.sha(child))
    w = object.__new__(workbench.Workbench)
    w._job = lambda job: (path, data)
    w.verdict = lambda job: verdict
    w.journal = Mock()
    unrelated = write_view(tmp_path, "F.Cu", [5000000, 5000000, 7000000, 7000000])
    p = proof(unrelated)
    p.update(source_sha256=data["source_sha256"],
             candidate_sha256=verdict["candidate_sha256"],
             code_identity=workbench.code_identity(), changed_copper_sha256=m["sha256"])
    workbench.inspection.write_json(tmp_path / "render-proof.json", p)
    with patch.object(visual, "changed_copper", return_value=m):
        with pytest.raises(ValueError, match="not_covered"):
            w.select("synthetic", verdict["candidate_sha256"], "A sufficiently long but irrelevant review description.")
        assert not w.journal.transition.called
        relevant = write_view(tmp_path, "F.Cu", [0, 0, 4000000, 4000000])
        p.update(views=[relevant], plot_hashes=relevant["plot_hashes"])
        workbench.inspection.write_json(tmp_path / "render-proof.json", p)
        result = w.select("synthetic", verdict["candidate_sha256"],
                          "Reviewed the synthetic copper change and all its affected geometry.")
        assert result["selected"] and result["visual_coverage"]["ok"]


def test_render_accumulates_layer_views_and_auto_frames_changed_copper(tmp_path):
    # Synthetic orchestration only; no physical approval is mocked into a
    # real candidate. Native material extraction is tested separately above.
    source, child = tmp_path / "source", tmp_path / "child"
    source.write_text("before")
    child.write_text("after")
    data = dict(source=str(source), candidate=str(child),
                source_sha256=workbench.inspection.sha(source))
    path = tmp_path / "job.json"
    path.write_text("{}")
    w = object.__new__(workbench.Workbench)
    w._job = lambda job: (path, data)
    m = manifest(("F.Cu", [1000000, 1000000, 3000000, 3000000]),
                 ("B.Cu", [1000000, 1000000, 3000000, 3000000]))

    def plot(command, **kwargs):
        target = Path(command[command.index("--output") + 1])
        target.write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')

    with patch.object(visual, "changed_copper", return_value=m), \
            patch.object(workbench.inspection, "bounded", side_effect=plot), \
            patch.object(workbench.shutil, "which", return_value=None):
        first = w.render("synthetic", "F.Cu")
        second = w.render("synthetic", "B.Cu")
    assert not first["visual_coverage"]["ok"] and second["visual_coverage"]["ok"]
    p = json.loads((tmp_path / "render-proof.json").read_text())
    assert len(p["views"]) == 2 and len(p["plot_hashes"]) == 4
    assert visual.verify_views(p, m, tmp_path)["ok"]
