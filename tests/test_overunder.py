#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# v2 OVER-UNDER POUR teeth (owner ratification 2026-07-24 late,
# docs/slab-pour-design-2026-07-24.md "v2" section: "the pour is a routed
# object"). Pure-raster tests (no pcbnew, no board) exercising
# route_overunder/bridges_to_vias directly on hand-built masks -- same style
# as tests/test_slab_pour.py's shave() teeth. Three scenarios named in the
# implementation task: a straight single-layer path (no bridge needed), a
# blocked-middle path that MUST bridge out and back, and a genuinely
# disconnected pair that must report failure and lay nothing.
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cec_slab_pour import Grid, bridges_to_vias, route_overunder  # noqa: E402


class _G(Grid):
    """Grid stub with a fixed geometry (no board needed) -- mirrors
    tests/test_slab_pour.py's stub of the same name."""
    def __init__(self, nx, ny, cell=0.8):
        self.x0 = self.y0 = 0.0
        self.cell = cell
        self.nx, self.ny = nx, ny
        self.x1, self.y1 = nx * cell, ny * cell


def _uniform(lay, r, c):
    return 1.0


class TestRouteOverunder(unittest.TestCase):
    def test_straight_single_layer_path(self):
        # layer A fully open; layer B fully impassable (never a bridge
        # target) -- the only possible connection is a pure single-layer
        # path on A, with zero bridges.
        ny, nx = 10, 30
        passable = {"A": np.ones((ny, nx), bool), "B": np.zeros((ny, nx), bool)}
        anchors = {"A": np.zeros((ny, nx), bool), "B": np.zeros((ny, nx), bool)}
        anchors["A"][4:6, 1:3] = True
        anchors["A"][4:6, 27:29] = True
        clab = np.zeros((ny, nx), int)
        clab[4:6, 1:3] = 1
        clab[4:6, 27:29] = 2

        path_cells, bridges, ok, bottleneck = route_overunder(
            ["A", "B"], passable, anchors, clab, 2, bias_fn=_uniform)

        self.assertTrue(ok, bottleneck)
        self.assertEqual(bridges, [])
        self.assertTrue(path_cells["A"][4:6, 10:20].any(),
                        "the path must cross the open mid-board on A")
        self.assertFalse(path_cells["B"].any(),
                         "layer B must never be touched -- it was never "
                         "needed and is not even passable")

    def test_blocked_middle_forces_bridge_out_and_back(self):
        # layer A: open except a FULL-HEIGHT wall at cols 15:25 -- no way
        # around within the grid, so A is topologically severed into a
        # left and a right island. layer B: fully open, no anchors of its
        # own (a pure detour layer). The only route is bridge down at the
        # wall's near edge, cross on B, bridge back up on the far edge.
        ny, nx = 10, 40
        passable = {"A": np.ones((ny, nx), bool), "B": np.ones((ny, nx), bool)}
        passable["A"][:, 15:25] = False
        anchors = {"A": np.zeros((ny, nx), bool), "B": np.zeros((ny, nx), bool)}
        anchors["A"][4:6, 1:3] = True
        anchors["A"][4:6, 36:38] = True
        clab = np.zeros((ny, nx), int)
        clab[4:6, 1:3] = 1
        clab[4:6, 36:38] = 2

        path_cells, bridges, ok, bottleneck = route_overunder(
            ["A", "B"], passable, anchors, clab, 2, bias_fn=_uniform)

        self.assertTrue(ok, bottleneck)
        self.assertEqual(len(bridges), 2,
                         "exactly one bridge down and one bridge back up")
        self.assertFalse(path_cells["A"][:, 15:25].any(),
                         "the vacated layer must carry NO copper in the "
                         "blocked stretch")
        self.assertTrue(path_cells["B"][:, 15:25].any(),
                        "the detour must actually cross on B inside the "
                        "blocked stretch")

        # vias present, on the transition line
        grid = _G(nx, ny)
        req_w = {"A": 1.2, "B": 1.2}
        vias = bridges_to_vias(bridges, req_w, grid)
        self.assertGreaterEqual(len(vias), 2, "at least one via per bridge")

    def test_no_path_reports_failure_and_lays_nothing(self):
        # a single layer, hard-walled all the way across between the two
        # terminals -- no second layer exists to bridge through, so no
        # path can possibly exist.
        ny, nx = 10, 20
        passable = {"A": np.ones((ny, nx), bool)}
        passable["A"][:, 9:11] = False
        anchors = {"A": np.zeros((ny, nx), bool)}
        anchors["A"][4:6, 1:3] = True
        anchors["A"][4:6, 16:18] = True
        clab = np.zeros((ny, nx), int)
        clab[4:6, 1:3] = 1
        clab[4:6, 16:18] = 2

        path_cells, bridges, ok, bottleneck = route_overunder(
            ["A"], passable, anchors, clab, 2, bias_fn=_uniform)

        self.assertFalse(ok)
        self.assertEqual(path_cells, {}, "no partial guess may be laid")
        self.assertEqual(bridges, [])
        self.assertIsNotNone(bottleneck)

    def test_unreachable_terminal_reported_before_search(self):
        # a cluster whose anchor sits ONLY on a layer that is not in the
        # searched layer set at all -- must fail fast with a clear reason,
        # not silently search forever / crash.
        ny, nx = 10, 20
        passable = {"A": np.ones((ny, nx), bool)}
        anchors = {"A": np.zeros((ny, nx), bool)}
        anchors["A"][4:6, 1:3] = True
        # cluster 2 exists in clab (so nclusters=2) but has NO anchor on
        # any searched layer -- e.g. it only ever existed on a layer this
        # call was not given.
        clab = np.zeros((ny, nx), int)
        clab[4:6, 1:3] = 1
        clab[4:6, 16:18] = 2

        path_cells, bridges, ok, bottleneck = route_overunder(
            ["A"], passable, anchors, clab, 2, bias_fn=_uniform)

        self.assertFalse(ok)
        self.assertEqual(path_cells, {})
        self.assertEqual(bottleneck["cluster"], 2)

    def test_single_cluster_is_trivially_connected(self):
        ny, nx = 10, 20
        passable = {"A": np.ones((ny, nx), bool)}
        anchors = {"A": np.zeros((ny, nx), bool)}
        anchors["A"][4:6, 1:3] = True
        clab = np.zeros((ny, nx), int)
        clab[4:6, 1:3] = 1

        path_cells, bridges, ok, bottleneck = route_overunder(
            ["A"], passable, anchors, clab, 1, bias_fn=_uniform)

        self.assertTrue(ok)
        self.assertEqual(path_cells, {})
        self.assertEqual(bridges, [])
        self.assertIsNone(bottleneck)


class TestBridgesToVias(unittest.TestCase):
    def test_ledger_skips_close_existing_via(self):
        grid = _G(30, 20)
        # a bridge at cell (10, 10) travelling along +x -> its via LINE is
        # perpendicular (+y), so multiple candidates are spaced in y.
        bridges = [(10, 10, "A", "B", 1.0, 0.0)]
        req_w = {"A": 3.0, "B": 3.0}   # half_w=1.5mm -> n_v=3 (1.2mm pitch)

        baseline = bridges_to_vias(bridges, req_w, grid)
        self.assertEqual(len(baseline), 3)

        centre = next(v for v in baseline
                     if abs(v["x_mm"] - (10 + 0.5) * grid.cell) < 1e-6
                     and abs(v["y_mm"] - (10 + 0.5) * grid.cell) < 1e-6)
        conflicted = bridges_to_vias(
            bridges, req_w, grid,
            existing=[(centre["x_mm"], centre["y_mm"])])
        self.assertEqual(len(conflicted), 2,
                         "the ledger-conflicting spot must be skipped, "
                         "the other two must survive")
        for v in conflicted:
            self.assertGreaterEqual(
                (v["x_mm"] - centre["x_mm"]) ** 2
                + (v["y_mm"] - centre["y_mm"]) ** 2, 0.85 ** 2)


if __name__ == "__main__":
    unittest.main()
