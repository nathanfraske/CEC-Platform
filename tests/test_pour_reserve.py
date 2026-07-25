#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# PRE-FR POUR-CORRIDOR RESERVATION teeth (owner priority ruling 2026-07-24,
# docs/slab-pour-design-2026-07-24.md: "the pour takes priority and gets its
# route first"; the reachability half of the RS1 starvation-cycle fix).
# Pure-raster tests (no pcbnew, no board) exercising the reservation's pure
# half -- route_overunder -> reservation_from_search -> corridors_to_keepouts
# -- on hand-built masks, same style as tests/test_overunder.py. The
# board-coupled wrapper (reserve_pour_corridors) and the cec_fr.route_once
# wire-up are exercised by the in-container end-to-end run, not here.
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cec_slab_pour import (  # noqa: E402
    Grid,
    _mask_rects,
    corridor_masks,
    corridors_to_keepouts,
    reservation_from_search,
    route_overunder,
)


class _G(Grid):
    """Grid stub with a fixed geometry (no board needed) -- mirrors
    tests/test_overunder.py's stub of the same name."""
    def __init__(self, nx, ny, cell=0.8):
        self.x0 = self.y0 = 0.0
        self.cell = cell
        self.nx, self.ny = nx, ny
        self.x1, self.y1 = nx * cell, ny * cell


def _uniform(lay, r, c):
    return 1.0


def _two_cluster_scene(ny=14, nx=40):
    """One open layer A with two terminal clusters at the ends -- the
    canonical corridor case. Returns (passable, anchors, clab, foreign)."""
    passable = {"A": np.ones((ny, nx), bool)}
    anchors = {"A": np.zeros((ny, nx), bool)}
    anchors["A"][6:8, 1:3] = True
    anchors["A"][6:8, 37:39] = True
    clab = np.zeros((ny, nx), int)
    clab[6:8, 1:3] = 1
    clab[6:8, 37:39] = 2
    foreign = {"A": np.zeros((ny, nx), bool)}
    return passable, anchors, clab, foreign


def _rects_to_mask(rects, grid):
    """Rebuild the boolean mask a rect list covers (exact inverse of
    _mask_rects' mm mapping)."""
    m = np.zeros((grid.ny, grid.nx), bool)
    for (x0, y0, x1, y1) in rects:
        i0 = int(round((x0 - grid.x0) / grid.cell))
        i1 = int(round((x1 - grid.x0) / grid.cell))
        j0 = int(round((y0 - grid.y0) / grid.cell))
        j1 = int(round((y1 - grid.y0) / grid.cell))
        m[j0:j1, i0:i1] = True
    return m


class TestMaskRects(unittest.TestCase):
    def test_exact_cover_on_staircase_mask(self):
        # a staircase with a hole -- the decomposition must reproduce the
        # mask EXACTLY (never overshoot into a foreign halo, never leave an
        # unreserved sliver).
        grid = _G(12, 8)
        m = np.zeros((8, 12), bool)
        m[1:4, 1:9] = True
        m[3:7, 6:11] = True
        m[2, 4] = False                      # a bitten cell inside the band
        rects = _mask_rects(m, grid)
        self.assertTrue((_rects_to_mask(rects, grid) == m).all(),
                        "rect union must equal the mask cell-for-cell")

    def test_straight_band_is_one_rect(self):
        grid = _G(30, 10)
        m = np.zeros((10, 30), bool)
        m[4:7, 2:28] = True
        rects = _mask_rects(m, grid)
        self.assertEqual(len(rects), 1,
                         "a straight corridor leg must collapse to ONE rect")
        (x0, y0, x1, y1) = rects[0]
        self.assertAlmostEqual(x0, 2 * grid.cell)
        self.assertAlmostEqual(x1, 28 * grid.cell)
        self.assertAlmostEqual(y0, 4 * grid.cell)
        self.assertAlmostEqual(y1, 7 * grid.cell)


class TestCorridorReservation(unittest.TestCase):
    def test_corridor_found_on_empty_board(self):
        # empty board (no foreign): the search connects the two clusters and
        # the reservation yields covering rects on the searched layer.
        passable, anchors, clab, foreign = _two_cluster_scene()
        grid = _G(clab.shape[1], clab.shape[0])
        path_cells, bridges, ok, bottleneck = route_overunder(
            ["A"], passable, anchors, clab, 2, bias_fn=_uniform)
        self.assertTrue(ok, bottleneck)
        rcells = {"A": 2}
        cors, reserved = reservation_from_search(
            "/SENSE12V_LO", ok, path_cells, bridges, rcells, foreign, grid)
        self.assertTrue(reserved)
        self.assertTrue(cors, "an empty board must reserve a corridor")
        self.assertEqual({c["layer"] for c in cors}, {"A"})
        self.assertEqual({c["net"] for c in cors}, {"/SENSE12V_LO"})

    def test_corridor_rects_cover_path_at_width(self):
        # every path cell must be covered at the FULL half-width + margin --
        # the rect union must equal the corridor mask exactly, and the
        # corridor mask must contain the whole dilated path (no foreign to
        # bite it here).
        from scipy import ndimage
        passable, anchors, clab, foreign = _two_cluster_scene()
        grid = _G(clab.shape[1], clab.shape[0])
        path_cells, bridges, ok, _b = route_overunder(
            ["A"], passable, anchors, clab, 2, bias_fn=_uniform)
        self.assertTrue(ok)
        rcells = {"A": 2}
        masks = corridor_masks(path_cells, bridges, rcells, foreign, grid,
                               margin_cells=1)
        st = ndimage.generate_binary_structure(2, 1)
        want = ndimage.binary_dilation(path_cells["A"], structure=st,
                                       iterations=3)   # rc 2 + margin 1
        self.assertTrue((masks["A"] == want).all(),
                        "with no foreign, corridor = dilate(path, rc+margin)")
        cors, reserved = reservation_from_search(
            "X", ok, path_cells, bridges, rcells, foreign, grid)
        self.assertTrue(reserved)
        rebuilt = _rects_to_mask([(c["x0"], c["y0"], c["x1"], c["y1"])
                                  for c in cors], grid)
        self.assertTrue((rebuilt == masks["A"]).all(),
                        "rect union must equal the corridor mask exactly")

    def test_foreign_is_never_swallowed(self):
        # a foreign blob beside the lane: the margin ring may reach it, but
        # the corridor must never cover a foreign cell (a keepout there
        # would wall FR off from copper it must still reach) -- and the path
        # itself must stay covered at width.
        from scipy import ndimage
        passable, anchors, clab, foreign = _two_cluster_scene()
        rc = 2
        # foreign blob 2 rows above the terminal row band; the search erodes
        # around it so the path keeps rc clearance
        foreign["A"][0:3, 15:20] = True
        st = ndimage.generate_binary_structure(2, 1)
        passable["A"] = ndimage.binary_erosion(
            ~foreign["A"], structure=st, iterations=rc) | anchors["A"]
        grid = _G(clab.shape[1], clab.shape[0])
        path_cells, bridges, ok, _b = route_overunder(
            ["A"], passable, anchors, clab, 2, bias_fn=_uniform)
        self.assertTrue(ok)
        masks = corridor_masks(path_cells, bridges, {"A": rc}, foreign, grid)
        self.assertFalse((masks["A"] & foreign["A"]).any(),
                         "the corridor may NEVER cover foreign cells")
        self.assertTrue((masks["A"][path_cells["A"]]).all(),
                        "every path cell itself must stay reserved")

    def test_no_path_reserves_nothing(self):
        # hard wall all the way across, single layer -> no path exists; the
        # reservation must yield ([], False): a no-path net reserves nothing
        # and (at the wire-up) excludes no pads -- it stays fully FR-routed.
        ny, nx = 10, 20
        passable = {"A": np.ones((ny, nx), bool)}
        passable["A"][:, 9:11] = False
        anchors = {"A": np.zeros((ny, nx), bool)}
        anchors["A"][4:6, 1:3] = True
        anchors["A"][4:6, 16:18] = True
        clab = np.zeros((ny, nx), int)
        clab[4:6, 1:3] = 1
        clab[4:6, 16:18] = 2
        grid = _G(nx, ny)
        path_cells, bridges, ok, bottleneck = route_overunder(
            ["A"], passable, anchors, clab, 2, bias_fn=_uniform)
        self.assertFalse(ok)
        cors, reserved = reservation_from_search(
            "+5VSB", ok, path_cells, bridges, {"A": 2},
            {"A": np.zeros((ny, nx), bool)}, grid)
        self.assertEqual(cors, [])
        self.assertFalse(reserved)

    def test_single_cluster_reserves_nothing(self):
        # one terminal cluster = trivially connected: route_overunder
        # returns an empty path -- nothing to reserve, FR keeps the net.
        ny, nx = 10, 20
        grid = _G(nx, ny)
        cors, reserved = reservation_from_search(
            "+3V3", True, {}, [], {"A": 2},
            {"A": np.zeros((ny, nx), bool)}, grid)
        self.assertEqual(cors, [])
        self.assertFalse(reserved)


class TestKeepoutDicts(unittest.TestCase):
    def test_keepouts_carry_layer_and_flags(self):
        passable, anchors, clab, foreign = _two_cluster_scene()
        grid = _G(clab.shape[1], clab.shape[0])
        path_cells, bridges, ok, _b = route_overunder(
            ["A"], passable, anchors, clab, 2, bias_fn=_uniform)
        cors, reserved = reservation_from_search(
            "/SENSE12V_LO", ok, path_cells, bridges, {"A": 2}, foreign, grid)
        self.assertTrue(reserved)
        kos = corridors_to_keepouts(cors)
        self.assertEqual(len(kos), len(cors))
        for ko, c in zip(kos, cors):
            self.assertEqual(ko["layers"], (c["layer"],),
                             "keepout must land on the corridor's OWN layer")
            self.assertIs(ko["block_fills"], False,
                          "the same-net pour must be able to FILL the "
                          "reserved corridor")
            self.assertNotIn("allow_vias", ko,
                             "vias stay blocked (bake_hints default): a "
                             "foreign via would antipad a hole in the lane")
            self.assertTrue(ko["name"].startswith("pourres_SENSE12V_LO_"))
            for k in ("x0", "y0", "x1", "y1"):
                self.assertEqual(ko[k], c[k])

    def test_polygon_matches_rect_corners(self):
        passable, anchors, clab, foreign = _two_cluster_scene()
        grid = _G(clab.shape[1], clab.shape[0])
        path_cells, bridges, ok, _b = route_overunder(
            ["A"], passable, anchors, clab, 2, bias_fn=_uniform)
        cors, _res = reservation_from_search(
            "X", ok, path_cells, bridges, {"A": 2}, foreign, grid)
        for c in cors:
            self.assertEqual(c["polygon"],
                             [(c["x0"], c["y0"]), (c["x1"], c["y0"]),
                              (c["x1"], c["y1"]), (c["x0"], c["y1"])])


if __name__ == "__main__":
    unittest.main()
