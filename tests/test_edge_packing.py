"""Renamed synthetic geometry: connector alignment, obstacles and legacy replay."""
from unittest import mock
from types import SimpleNamespace
from pathlib import Path

import pytest

from cec_edge_packing import bank_start
import cec_synth_pipeline as synth


@pytest.mark.parametrize("alignment,expected", [("start", 2.), ("center", 16.), ("end", 30.)])
def test_alignment_uses_complete_bank_and_asymmetric_margins(alignment, expected):
    assert bank_start(50., [(0., 8., 0., 5.), (10., 17., 0., 5.)],
                      alignment=alignment, start_margin=2., end_margin=3.) == expected


def test_end_alignment_reserves_real_corner_hardware_only_in_same_band():
    items = [(0., 8., 40., 52.), (10., 17., 46., 51.)]
    # Lower corner blocks the bank, but a distant obstacle does not.
    assert bank_start(50., items, [(43., 49., 44., 50.), (20., 45., 0., 5.)],
                      alignment="end", clearance=.25) == 25.75


def test_finite_search_can_choose_either_side_of_an_interior_obstacle():
    items = [(0., 4., 0., 5.)]
    obs = [(8., 12., 0., 5.)]
    assert bank_start(20., items, obs, alignment="center", clearance=.1) == pytest.approx(3.9)
    assert bank_start(20., items, obs, alignment="end", clearance=.1) == 14.5


@pytest.mark.parametrize("kwargs", [
    {"alignment": "bottom"}, {"end_margin": float("nan")}, {"clearance": -1.},
    {"start_margin": 20.},
])
def test_invalid_and_impossible_policy_is_not_silently_ignored(kwargs):
    with pytest.raises(ValueError):
        bank_start(20., [(0., 10., 0., 5.)], **kwargs)


def test_fully_blocked_edge_refuses_instead_of_colliding():
    with pytest.raises(ValueError, match="no clearance-safe"):
        bank_start(20., [(0., 4., 0., 5.)], [(0., 20., 0., 5.)])


@pytest.mark.parametrize("edge,rotation", [("right", 90.), ("left", 270.),
                                         ("bottom", 0.), ("top", 180.)])
def test_real_seed_adapter_honors_alignment_rotation_hardware_and_pins(edge, rotation):
    nl = synth.Netlist(comps={ref: synth.Comp(ref, "connector", "land")
                             for ref in ("J701", "J909")}, nets={})
    horizontal = edge in ("top", "bottom")
    # Symmetric synthetic body; each bank item is 4 mm long.
    with mock.patch.object(synth, "_role", return_value="host"), \
            mock.patch.object(synth, "_courtyard_info", return_value=(0., 0., 2., 2.)), \
            mock.patch.object(synth, "_pad_band", return_value=((-1., 1.), (-1., 1.))), \
            mock.patch.object(synth, "_pad_copper_band", return_value=((-1., 1.), (-1., 1.))):
        args = (nl, 40., 40., {r: "land" for r in nl.comps}, {})
        kw = dict(edge_override={r: edge for r in nl.comps}, pack_right_top=True)
        old = synth.seed_anchors(*args, **kw)
        assert old == synth.seed_anchors(*args, **kw, edge_packing={})
        obstacles = [(33., 39., 0., 40.)] if horizontal else [(0., 40., 33., 39.)]
        placed = synth.seed_anchors(*args, **kw, edge_packing={edge: {"alignment": "end"}},
                                    edge_obstacles=obstacles)
        along = 0 if horizontal else 1
        assert placed["J909"][along] + 2. == pytest.approx(32.9)
        assert all(pos[2] == rotation for pos in placed.values())
        pinned = synth.seed_anchors(*args[:-1], {"J701": (10., 10., 23.)}, **kw,
                                    edge_packing={edge: {"alignment": "end"}})
        assert pinned["J701"] == (10., 10., 23.)


def test_p2_provisional_cell_clearance_cannot_split_declared_bank():
    import cec_passes as passes
    components = {ref: "land" for ref in ("J701", "J909")}
    nl = synth.Netlist(comps={r: synth.Comp(r, "connector", "land") for r in components}, nets={})
    template = {"parts": {"CELL": {"offset_mm": [0., 0.], "rot_delta": 0.,
                                    "footprint": "wide_cell"}}}
    params = {"force_lanes": True, "lane_pitch": 4., "mount_holes": "none",
              "fiducials": "none", "connector_overhang": "none",
              "blueprint_cells": [{"template": template}, {"template": template}],
              "edge_packing": {"right": {"alignment": "end"}}}
    class Captured(Exception):
        pass
    def run(ladder, state=None):
        stage = next(p for p in ladder.passes if p.name == "p2_anchors")
        stage.fn(ladder)
        scope = dict(zip(stage.fn.__code__.co_freevars, stage.fn.__closure__))
        positions = scope["anchors"].cell_contents
        # The provisional cell row overlaps the bank, so the legacy path
        # would split/move it. Its later negotiator must instead solve the row.
        assert positions["J701"] == (36.5, 30.5, 90.)
        assert positions["J909"] == (36.5, 36.5, 90.)
        assert set(components) <= set(stage.resolve_locks(ladder))
        raise Captured
    with mock.patch.object(synth, "View", return_value=SimpleNamespace(nl=nl)), \
            mock.patch.object(synth, "_bind_declared_interface_anchors"), \
            mock.patch.object(synth, "_part_halfext", return_value={}), \
            mock.patch.object(synth, "_fp_of", return_value=components), \
            mock.patch.object(synth, "_classify", return_value=({}, [], [], [])), \
            mock.patch.object(synth, "_role", return_value="host"), \
            mock.patch.object(synth, "_courtyard_info", side_effect=lambda fp, *a, **kw:
                              (0., 0., 20., 11.) if fp == "wide_cell" else (0., 0., 2., 2.)), \
            mock.patch.object(synth, "_pad_band", return_value=((-1., 1.), (-1., 1.))), \
            mock.patch.object(synth, "_pad_copper_band", return_value=((-1., 1.), (-1., 1.))), \
            mock.patch.object(passes.PassLadder, "run", run):
        with pytest.raises(Captured):
            synth.synth_one({"board": "synthetic", "params": params}, 40., 40., "plain", 0)


@pytest.mark.parametrize("pinned_x,pinned_y,expected_end", [(10., 10., 38.5), (36.5, 36.5, 34.4)])
def test_internal_pinned_connector_is_obstacle_not_phantom_bank_slot(pinned_x, pinned_y, expected_end):
    refs = ("J701", "J808", "J909")
    nl = synth.Netlist(comps={r: synth.Comp(r, "connector", "land") for r in refs}, nets={})
    report = {}
    with mock.patch.object(synth, "_role", return_value="host"), \
            mock.patch.object(synth, "_courtyard_info", return_value=(0., 0., 2., 2.)), \
            mock.patch.object(synth, "_pad_band", return_value=((-1., 1.), (-1., 1.))), \
            mock.patch.object(synth, "_pad_copper_band", return_value=((-1., 1.), (-1., 1.))):
        poses = synth.seed_anchors(nl, 40., 40., {r: "land" for r in refs},
            {"J808": (pinned_x, pinned_y, 23.)},
            edge_packing={"right": {"alignment": "end"}}, edge_packing_report=report)
    assert report["right"]["refs"] == ["J701", "J909"]
    assert poses["J909"][1] - poses["J701"][1] == 6.  # actual 2 mm body gap
    assert report["right"]["end_mm"] == pytest.approx(expected_end)
    assert poses["J808"] == (pinned_x, pinned_y, 23.)


@pytest.mark.parametrize("relative", [
    "build/board-archive/20260831T1619-pcie-8pin-2port-v113-zero-open-v43/board.kicad_pcb",
    "beta/hub-standard-rev2/candidate/hub-standard-rev2-candidate.kicad_pcb",
    "build/12vhpwr-four-mount-76mm-review-20260907/02-placement/candidates/001/board.kicad_pcb",
])
def test_cross_board_native_footprint_bank_replay_is_read_only(relative):
    import hashlib
    import pcbnew
    path = Path(__file__).resolve().parents[1] / relative
    if not path.is_file():
        pytest.skip("retained board control not installed")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    board = pcbnew.LoadBoard(str(path))
    ports = sorted((fp for fp in board.GetFootprints()
                    if "RJ45" in fp.GetFPIDAsString() or "USB_C" in fp.GetFPIDAsString()),
                   key=lambda fp: fp.GetReference())[:2]
    assert len(ports) == 2
    nl = synth.Netlist(comps={fp.GetReference(): synth.Comp(
        fp.GetReference(), fp.GetValue(), fp.GetFPIDAsString()) for fp in ports}, nets={})
    fp_of = {r: c.footprint for r, c in nl.comps.items()}
    report = {}
    poses = synth.seed_anchors(nl, 80., 80., fp_of, {}, overhang="edge",
        role_overrides={r: "host" for r in fp_of}, edge_packing={"right": {"alignment": "end"}},
        edge_obstacles=[(73., 79., 73., 79.)], edge_packing_report=report)
    assert report["right"]["end_mm"] <= 72.900001
    assert len(report["right"]["refs"]) == 2
    for ref, (x, y, rotation) in poses.items():
        (x0, x1), (y0, y1) = synth._pad_copper_band(fp_of[ref], rotation)
        assert 0. <= x + x0 <= x + x1 <= 79.350001
        assert 0. <= y + y0 <= y + y1 <= 80.
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
