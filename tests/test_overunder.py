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
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cec_slab_pour import (  # noqa: E402
    Grid,
    _stamp_generated_pour_keepouts,
    _stamp_generated_via_keepouts,
    bridge_via_reservations,
    bridges_to_vias,
    field_via_line,
    prune_unseeded_pour_components,
    power_bridge_cost,
    route_overunder,
    synthesize_overunder_pours,
    terminal_clusters,
)


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
    def test_high_current_bridge_cost_prices_physical_via_field(self):
        self.assertEqual(power_bridge_cost(0.5, 1.25, {"F.Cu": 1}), 8.0)
        cost = power_bridge_cost(
            39.0, 1.25, {"F.Cu": 10, "B.Cu": 10, "In3.Cu": 123})
        self.assertEqual(cost, 46.0)

    def test_high_bridge_cost_keeps_route_on_preferred_open_layer(self):
        ny, nx = 12, 40
        passable = {"A": np.ones((ny, nx), bool),
                    "B": np.ones((ny, nx), bool)}
        anchors = {"A": np.zeros((ny, nx), bool),
                   "B": np.zeros((ny, nx), bool)}
        anchors["A"][5:7, 1:3] = True
        anchors["A"][5:7, 37:39] = True
        clab = np.zeros((ny, nx), int)
        clab[5:7, 1:3] = 1
        clab[5:7, 37:39] = 2

        path_cells, bridges, ok, bottleneck = route_overunder(
            ["A", "B"], passable, anchors, clab, 2,
            bias_fn=lambda layer, _r, _c: 1.0 if layer == "A" else 0.1,
            bridge_cost=46.0)

        self.assertTrue(ok, bottleneck)
        self.assertEqual(bridges, [])
        self.assertTrue(path_cells["A"].any())
        self.assertFalse(path_cells["B"].any())

    def test_unseeded_split_pour_is_pruned_before_materialization(self):
        class Box:
            def __init__(self, x0, y0, x1, y1):
                self.v = [int(q * 1e6) for q in (x0, y0, x1, y1)]
            def GetLeft(self): return self.v[0]
            def GetTop(self): return self.v[1]
            def GetRight(self): return self.v[2]
            def GetBottom(self): return self.v[3]
        class Pad:
            def GetNetname(self): return "RAIL"
            def GetBoundingBox(self): return Box(0.8, 0.8, 1.2, 1.2)
            def IsOnLayer(self, _layer): return True
        class Footprint:
            def Pads(self): return [Pad()]
        class Board:
            def GetFootprints(self): return [Footprint()]
            def GetTracks(self): return []
            def GetLayerID(self, layer): return layer

        pours = [
            {"net": "RAIL", "layer": "F.Cu", "name": "seed",
             "polygon": [(0, 0), (2, 0), (2, 2), (0, 2)]},
            {"net": "RAIL", "layer": "F.Cu", "name": "same-layer",
             "polygon": [(2, 0), (4, 0), (4, 2), (2, 2)]},
            {"net": "RAIL", "layer": "B.Cu", "name": "via-linked",
             "polygon": [(3, 0), (5, 0), (5, 2), (3, 2)]},
            {"net": "RAIL", "layer": "F.Cu", "name": "point-only",
             "polygon": [(4, 2), (5, 2), (5, 3), (4, 3)]},
            {"net": "RAIL", "layer": "F.Cu", "name": "orphan",
             "polygon": [(8, 0), (9, 0), (9, 1), (8, 1)]},
        ]
        kept, report = prune_unseeded_pour_components(
            Board(), pours,
            [{"net": "RAIL", "x_mm": 3.5, "y_mm": 1.0}])

        self.assertEqual([row["name"] for row in kept],
                         ["seed", "same-layer", "via-linked"])
        self.assertEqual(report["removed"], 2)
        self.assertEqual([row["name"] for row in report["detail"]],
                         ["point-only", "orphan"])

    def test_subcell_pad_anchors_do_not_merge_through_touched_empty_cell(self):
        class Box:
            def __init__(self, x0, y0, x1, y1):
                self.v = [int(q * 1e6) for q in (x0, y0, x1, y1)]
            def GetLeft(self): return self.v[0]
            def GetTop(self): return self.v[1]
            def GetRight(self): return self.v[2]
            def GetBottom(self): return self.v[3]
        class Pad:
            def __init__(self, x):
                self.box = Box(x - 0.05, 0.45, x + 0.05, 0.55)
            def GetNetCode(self): return 7
            def GetBoundingBox(self): return self.box
        class Footprint:
            def Pads(self): return [Pad(0.99), Pad(2.01)]
        class Board:
            def GetFootprints(self): return [Footprint()]
            def GetTracks(self): return []

        labels, count = terminal_clusters(Board(), 7, _G(4, 2, cell=1.0))

        self.assertEqual(count, 2)
        self.assertNotEqual(labels[0, 0], labels[0, 2])

    def test_existing_track_merges_guarded_pad_and_pickup_terminals(self):
        class Point:
            def __init__(self, x, y):
                self.x, self.y = int(x * 1e6), int(y * 1e6)
        class Box:
            def __init__(self, x0, y0, x1, y1):
                self.v = [int(q * 1e6) for q in (x0, y0, x1, y1)]
            def GetLeft(self): return self.v[0]
            def GetTop(self): return self.v[1]
            def GetRight(self): return self.v[2]
            def GetBottom(self): return self.v[3]
        class Pad:
            def __init__(self, x, y): self.box = Box(x, y, x + 0.2, y + 0.2)
            def GetNetCode(self): return 7
            def GetBoundingBox(self): return self.box
        class Footprint:
            def Pads(self): return [Pad(1.1, 1.1), Pad(5.1, 5.1)]
        class Track:
            def GetClass(self): return "PCB_TRACK"
            def GetNetCode(self): return 7
            def GetLayer(self): return 0
            def GetStart(self): return Point(1.1, 1.1)
            def GetEnd(self): return Point(5.1, 5.1)
        class Board:
            def GetFootprints(self): return [Footprint()]
            def GetTracks(self): return [Track()]

        labels, count = terminal_clusters(Board(), 7, _G(10, 10, cell=1.0))

        self.assertEqual(count, 1)
        self.assertEqual(labels[1, 1], labels[5, 5])

    def test_earlier_foreign_bridge_via_is_reserved_for_later_net(self):
        grid = _G(12, 12)
        mask = np.zeros((grid.ny, grid.nx), bool)
        prior = [{"net": "RAIL_A", "x_mm": 4.0, "y_mm": 4.0,
                  "radius_mm": 0.45}]

        self.assertEqual(
            _stamp_generated_via_keepouts(mask, grid, prior, "RAIL_B"), 1)
        self.assertTrue(mask.any(), "foreign planned barrel must block search")
        own_mask = np.zeros_like(mask)
        self.assertEqual(
            _stamp_generated_via_keepouts(own_mask, grid, prior, "RAIL_A"), 0)
        self.assertFalse(own_mask.any(), "same-net barrel remains an anchor")

    def test_earlier_foreign_pour_is_reserved_for_later_net(self):
        grid = _G(12, 12)
        prior = [{"net": "RAIL_A", "layer": "In3.Cu",
                  "polygon": [(3.0, 3.0), (5.0, 3.0),
                              (5.0, 5.0), (3.0, 5.0)]}]
        mask = np.zeros((grid.ny, grid.nx), bool)

        self.assertEqual(_stamp_generated_pour_keepouts(
            mask, grid, prior, "RAIL_B", "In3.Cu"), 1)
        self.assertTrue(mask.any(), "foreign planned pour must block search")
        own_mask = np.zeros_like(mask)
        self.assertEqual(_stamp_generated_pour_keepouts(
            own_mask, grid, prior, "RAIL_A", "In3.Cu"), 0)
        self.assertFalse(own_mask.any(), "same-net pour remains attachable")
        other_layer = np.zeros_like(mask)
        self.assertEqual(_stamp_generated_pour_keepouts(
            other_layer, grid, prior, "RAIL_B", "F.Cu"), 0)
        self.assertFalse(other_layer.any(), "other-layer copper is not foreign")

    def test_one_net_invocation_carries_prior_allocation_into_search(self):
        class Net:
            def GetNetname(self): return "RAIL_B"
        class NetInfo:
            def NetsByNetcode(self): return {7: Net()}
        class Board:
            def GetNetInfo(self): return NetInfo()
            def GetTracks(self): return []

        prior_pours = [{"net": "RAIL_A", "layer": "In3.Cu",
                        "polygon": [(3.0, 3.0), (5.0, 3.0),
                                    (5.0, 5.0), (3.0, 5.0)]}]
        prior_vias = [{"net": "RAIL_A", "x_mm": 4.0, "y_mm": 4.0,
                       "radius_mm": 0.45}]
        with mock.patch("cec_slab_pour.Grid", return_value=_G(12, 12)), \
                mock.patch("cec_slab_pour._board_thermal_config",
                           return_value=None), \
                mock.patch("cec_slab_pour.shunt_neighborhoods",
                           return_value=[]), \
                mock.patch("cec_slab_pour._prep_overunder_net",
                           return_value=(None, "bounded test stop")) as prep:
            _pours, _vias, report = synthesize_overunder_pours(
                Board(), [{"net": "RAIL_B", "layers": ("In3.Cu",)}],
                reserved_pours=prior_pours, reserved_vias=prior_vias)

        self.assertFalse(report["RAIL_B"]["path_found"])
        self.assertEqual(prep.call_args.kwargs["generated_pours"],
                         prior_pours)
        self.assertEqual(prep.call_args.kwargs["generated_vias"], prior_vias)

    def test_compact_field_cannot_reseat_outside_admitted_corridor(self):
        grid = _G(12, 12)
        bridge = (5, 5, "A", "B", 1.0, 0.0)
        allowed = lambda x, y: x < 4.5

        vias, _reseated = field_via_line(
            bridge, 1.2, grid, (), (), n_needed=2, via_allow=allowed)

        self.assertTrue(vias)
        self.assertTrue(all(allowed(x, y) for x, y in vias),
                        "spare-ring slots must obey the realized corridor")

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

    def test_bridge_transition_respects_all_layer_keepout(self):
        ny, nx = 10, 40
        passable = {"A": np.ones((ny, nx), bool),
                    "B": np.ones((ny, nx), bool)}
        passable["A"][:, 15:25] = False
        anchors = {"A": np.zeros((ny, nx), bool),
                   "B": np.zeros((ny, nx), bool)}
        anchors["A"][4:6, 1:3] = True
        anchors["A"][4:6, 36:38] = True
        clab = np.zeros((ny, nx), int)
        clab[4:6, 1:3] = 1
        clab[4:6, 36:38] = 2
        forbidden = np.ones((ny, nx), bool)
        forbidden[:, 14] = False
        forbidden[:, 25] = False

        _paths, bridges, ok, bottleneck = route_overunder(
            ["A", "B"], passable, anchors, clab, 2, bias_fn=_uniform,
            bridge_forbidden=forbidden)

        self.assertTrue(ok, bottleneck)
        self.assertEqual(len(bridges), 2)
        self.assertTrue(all(not forbidden[r, c]
                            for r, c, *_rest in bridges))

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

    def test_pickup_vias_keep_pour_on_non_top_layer(self):
        ny, nx = 10, 24
        passable = {"F.Cu": np.ones((ny, nx), bool),
                    "In3.Cu": np.ones((ny, nx), bool)}
        anchors = {"F.Cu": np.zeros((ny, nx), bool),
                   "In3.Cu": np.zeros((ny, nx), bool)}
        clab = np.zeros((ny, nx), int)
        # Broad top pads, each with a real through pickup at its centre.
        anchors["F.Cu"][3:7, 1:5] = True
        anchors["F.Cu"][3:7, 19:23] = True
        anchors["In3.Cu"][5, 3] = True
        anchors["In3.Cu"][5, 21] = True
        clab[3:7, 1:5] = 1
        clab[3:7, 19:23] = 2

        path_cells, bridges, ok, bottleneck = route_overunder(
            ["In3.Cu", "F.Cu"], passable, anchors, clab, 2,
            bias_fn=_uniform)

        self.assertTrue(ok, bottleneck)
        self.assertEqual(bridges, [],
                         "a real pickup makes an F.Cu transition unnecessary")
        self.assertTrue(path_cells["In3.Cu"].any())
        self.assertFalse(path_cells["F.Cu"].any(),
                         "top pad breadth must not beat its through pickup")


class TestBridgesToVias(unittest.TestCase):
    def test_exact_field_reservation_spans_every_routing_layer(self):
        rows = bridge_via_reservations(
            [{"net": "+5V", "x_mm": 10.0, "y_mm": 20.0}],
            ("F.Cu", "In2.Cu", "In3.Cu", "B.Cu"))
        self.assertEqual(len(rows), 4)
        self.assertEqual({row["layer"] for row in rows},
                         {"F.Cu", "In2.Cu", "In3.Cu", "B.Cu"})
        self.assertTrue(all(row["kind"] == "bridge_via" for row in rows))
        self.assertTrue(all((row["x0"], row["y0"], row["x1"], row["y1"])
                            == (9.35, 19.35, 10.65, 20.65)
                            for row in rows))

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
                + (v["y_mm"] - centre["y_mm"]) ** 2, 1.10 ** 2)

    def test_default_ledger_enforces_barrel_edge_clearance(self):
        grid = _G(30, 20)
        bridges = [(10, 10, "A", "B", 1.0, 0.0)]
        req_w = {"A": 1.2, "B": 1.2}
        baseline = bridges_to_vias(bridges, req_w, grid)
        self.assertEqual(len(baseline), 2)
        seat = min(baseline, key=lambda v: v["y_mm"])
        existing = [(seat["x_mm"], seat["y_mm"] - 1.0)]
        revised = bridges_to_vias(bridges, req_w, grid, existing=existing)
        self.assertEqual(len(revised), 1,
                         "1.0mm centres leave only 0.10mm between 0.9mm "
                         "barrels and must be rejected")


class TestRectRealization(unittest.TestCase):
    """Mandate part 3 (2026-07-25): when route_overunder must run, its path
    is realized as DRAWN geometry -- straight capsule covers per same-layer
    run + ONE compact via field per genuine layer change at the run
    boundary -- never the dilated-cell smear (3-cell bridge disks +
    closing) that read as the owner's amorphous blobs / via lines."""

    def test_generated_via_batch_clips_prior_foreign_pour_symmetrically(self):
        from shapely.geometry import Point, Polygon
        from cec_slab_pour import _clip_pours_around_generated_vias

        pours = [
            {"net": "A", "layer": "In3.Cu", "provenance": "overunder",
             "polygon": [(0, 0), (10, 0), (10, 5), (0, 5)]},
            {"net": "B", "layer": "In3.Cu", "provenance": "overunder",
             "polygon": [(0, 0), (10, 0), (10, 5), (0, 5)]},
        ]
        vias = [{"net": "A", "x_mm": 2.0, "y_mm": 2.0},
                {"net": "B", "x_mm": 8.0, "y_mm": 2.0}]
        clipped, count = _clip_pours_around_generated_vias(pours, vias)
        self.assertEqual(count, 2)
        copper = {}
        for row in clipped:
            copper.setdefault(row["net"], []).append(
                Polygon(row["polygon"], row.get("holes") or ()))
        self.assertTrue(any(p.covers(Point(2, 2)) for p in copper["A"]))
        self.assertFalse(any(p.covers(Point(8, 2)) for p in copper["A"]))
        self.assertTrue(any(p.covers(Point(8, 2)) for p in copper["B"]))
        self.assertFalse(any(p.covers(Point(2, 2)) for p in copper["B"]))
        for rows in copper.values():
            for polygon in rows:
                rings = [polygon.exterior] + list(polygon.interiors)
                self.assertTrue(all(
                    abs(x1 - x0) < 1e-9 or abs(y1 - y0) < 1e-9
                    for ring in rings
                    for (x0, y0), (x1, y1) in zip(
                        ring.coords, list(ring.coords)[1:])))

    def _routed(self):
        import numpy as np
        from cec_slab_pour import realize_overunder_rects
        g = _G(30, 9)
        layers = ["In2.Cu", "B.Cu"]
        ny, nx = g.ny, g.nx
        passable = {"In2.Cu": np.ones((ny, nx), bool),
                    "B.Cu": np.ones((ny, nx), bool)}
        passable["In2.Cu"][:, 14:17] = False           # wall -> under-pass
        anchors = {"In2.Cu": np.zeros((ny, nx), bool),
                   "B.Cu": np.zeros((ny, nx), bool)}
        anchors["In2.Cu"][4, 2] = True
        anchors["In2.Cu"][4, 27] = True
        clab = np.zeros((ny, nx), int)
        clab[4, 2] = 1
        clab[4, 27] = 2
        chains = []
        path_cells, bridges, ok, _bn = route_overunder(
            layers, passable, anchors, clab, 2, bias_fn=_uniform,
            chains_out=chains)
        self.assertTrue(ok)
        self.assertGreaterEqual(len(bridges), 2, "out and back")
        reqw = {"In2.Cu": 1.6, "B.Cu": 1.6}
        polys, vias, notes = realize_overunder_rects(
            chains, bridges, reqw, g)
        return g, bridges, polys, vias, notes

    def test_via_fields_sit_at_run_boundaries_only(self):
        g, bridges, _polys, vias, _notes = self._routed()
        self.assertTrue(vias)
        bpts = [(g.x0 + (c + 0.5) * g.cell, g.y0 + (r + 0.5) * g.cell)
                for (r, c, *_x) in bridges]
        for (vx, vy) in vias:
            d = min(((vx - bx) ** 2 + (vy - by) ** 2) ** 0.5
                    for (bx, by) in bpts)
            self.assertLessEqual(
                d, 1.6 / 2.0 + 1.8 + 0.05,
                "via (%.2f,%.2f) is %.2fmm from every layer change -- "
                "fields belong AT the run boundary" % (vx, vy, d))

    def test_vacated_layer_carries_no_copper_at_the_wall(self):
        from shapely.geometry import Point, Polygon
        g, _bridges, polys, _vias, _notes = self._routed()
        wall_mid = Point(g.x0 + 15.5 * g.cell, g.y0 + 4.5 * g.cell)
        for coords in polys.get("In2.Cu", ()):
            self.assertFalse(
                Polygon(coords).buffer(0).covers(wall_mid),
                "In2 copper crosses the wall the path bridged around")
        self.assertTrue(
            any(Polygon(coords).buffer(0).covers(wall_mid)
                for coords in polys.get("B.Cu", ())),
            "the under-pass layer must carry the wall crossing")

    def test_rect_realization_is_leaner_than_the_smear(self):
        import numpy as np
        from shapely.geometry import Polygon
        from cec_slab_pour import (apply_bridge_overlap, realize_overunder,
                                   realize_overunder_rects)
        g = _G(30, 9)
        layers = ["In2.Cu", "B.Cu"]
        ny, nx = g.ny, g.nx
        passable = {"In2.Cu": np.ones((ny, nx), bool),
                    "B.Cu": np.ones((ny, nx), bool)}
        passable["In2.Cu"][:, 14:17] = False
        anchors = {"In2.Cu": np.zeros((ny, nx), bool),
                   "B.Cu": np.zeros((ny, nx), bool)}
        anchors["In2.Cu"][4, 2] = True
        anchors["In2.Cu"][4, 27] = True
        clab = np.zeros((ny, nx), int)
        clab[4, 2] = 1
        clab[4, 27] = 2
        chains = []
        path_cells, bridges, ok, _bn = route_overunder(
            layers, passable, anchors, clab, 2, bias_fn=_uniform,
            chains_out=chains)
        self.assertTrue(ok)
        reqw = {"In2.Cu": 1.6, "B.Cu": 1.6}
        rect_polys, _v, _n = realize_overunder_rects(chains, bridges, reqw, g)
        rect_area = sum(Polygon(c).buffer(0).area
                        for ps in rect_polys.values() for c in ps)
        pc = {k: m.copy() for k, m in path_cells.items()}
        apply_bridge_overlap(pc, bridges, g)
        smear = realize_overunder(pc, {"In2.Cu": 1, "B.Cu": 1}, g)
        smear_area = sum(Polygon(c).buffer(0).area
                         for ps in smear.values() for c in ps)
        self.assertLess(rect_area, smear_area * 0.85,
                        "rect realization (%.1fmm2) should be materially "
                        "leaner than the smear (%.1fmm2)"
                        % (rect_area, smear_area))

    def test_f_runs_clip_to_the_admit_region(self):
        import numpy as np
        from cec_slab_pour import realize_overunder_rects
        g = _G(30, 9)
        chains = [[(4, c, "F.Cu") for c in range(2, 28)]]
        polys, vias, notes = realize_overunder_rects(
            chains, [], {"F.Cu": 1.6}, g,
            f_admit=[(0.0, 0.0, 8.0, 7.2)])   # admit only the left end
        self.assertTrue(any("clipped to the top-copper admit" in n
                            or "outside the top-copper admit" in n
                            for n in notes), notes)
        from shapely.geometry import Point, Polygon
        right = Point(g.x0 + 26.5 * g.cell, g.y0 + 4.5 * g.cell)
        for coords in polys.get("F.Cu", ()):
            self.assertFalse(Polygon(coords).buffer(0).covers(right),
                             "F copper escaped the admit clip")

    def test_vector_width_cannot_regrow_over_a_blocked_corridor_cell(self):
        from shapely.geometry import Point, Polygon
        from cec_slab_pour import realize_overunder_rects
        g = _G(14, 7)
        chains = [[(3, c, "In3.Cu") for c in range(1, 13)]]
        clip = np.zeros((g.ny, g.nx), bool)
        clip[2:5, 1:13] = True
        clip[2:5, 6] = False             # foreign pad/clearance column
        holes = {}
        polys, _vias, _notes = realize_overunder_rects(
            chains, [], {"In3.Cu": 1.6}, g,
            clip_masks={"In3.Cu": clip}, holes_out=holes)

        copper = [Polygon(coords, holes.get(("In3.Cu", index), ())).buffer(0)
                  for index, coords in enumerate(polys.get("In3.Cu", ()))]
        blocked = Point((6 + 0.5) * g.cell, (3 + 0.5) * g.cell)
        self.assertFalse(any(poly.covers(blocked) for poly in copper),
                         "vector widening regrew over a raster obstacle")
        for col in (3, 10):
            clear = Point((col + 0.5) * g.cell, (3 + 0.5) * g.cell)
            self.assertTrue(any(poly.covers(clear) for poly in copper))

    def test_l_simplification_cannot_leave_final_corridor_and_fragment(self):
        from scipy import ndimage
        from shapely.geometry import Point, Polygon
        from shapely.ops import unary_union
        from cec_slab_pour import realize_overunder_rects

        g = _G(12, 12)
        # A connected staircase whose free-space L lies far outside its final
        # reserved corridor.  Simplifying against free space alone and then
        # intersecting with this clip leaves separate start/end islands.
        cells = [(1, 1), (1, 2), (2, 2), (2, 3), (3, 3), (3, 4),
                 (4, 4), (4, 5), (5, 5), (5, 6), (6, 6), (6, 7),
                 (7, 7), (7, 8), (8, 8)]
        free = np.ones((g.ny, g.nx), bool)
        spine = np.zeros_like(free)
        for row, col in cells:
            spine[row, col] = True
        clip = ndimage.binary_dilation(
            spine, structure=ndimage.generate_binary_structure(2, 1),
            iterations=1)

        polys, _vias, _notes = realize_overunder_rects(
            [[(row, col, "In3.Cu") for row, col in cells]], [],
            {"In3.Cu": 1.2}, g,
            free_masks={"In3.Cu": free}, clip_masks={"In3.Cu": clip})
        copper = unary_union([Polygon(coords).buffer(0)
                              for coords in polys["In3.Cu"]])
        self.assertEqual(copper.geom_type, "Polygon",
                         "search-proven corridor must remain one component")
        for row, col in (cells[0], cells[-1]):
            point = Point(g.x0 + (col + 0.5) * g.cell,
                          g.y0 + (row + 0.5) * g.cell)
            self.assertTrue(copper.covers(point))

    def test_f_bridge_landing_covers_every_barrel_on_both_layers(self):
        from shapely.geometry import Point, Polygon
        from cec_slab_pour import realize_overunder_rects
        g = _G(30, 9)
        bridge = (4, 10, "F.Cu", "In3.Cu", 1.0, 0.0)
        cx = g.x0 + 10.5 * g.cell
        cy = g.y0 + 4.5 * g.cell
        polys, vias, _notes = realize_overunder_rects(
            [[(4, 10, "F.Cu"), (4, 10, "In3.Cu")]], [bridge],
            {"F.Cu": 4.0, "In3.Cu": 4.0}, g,
            f_admit=[(cx - 0.2, cy - 0.2, cx + 0.2, cy + 0.2)],
            strict_bridges=True)
        self.assertTrue(vias)
        for layer in ("F.Cu", "In3.Cu"):
            copper = [Polygon(coords).buffer(0)
                      for coords in polys.get(layer, ())]
            for via in vias:
                self.assertTrue(any(poly.covers(Point(*via)) for poly in copper),
                                "%s must land every transition barrel" % layer)

    def test_bridge_landing_is_not_cut_back_to_centerline_clip(self):
        from shapely.geometry import Point, Polygon
        from cec_slab_pour import realize_overunder_rects
        g = _G(20, 9)
        bridge = (4, 10, "In2.Cu", "B.Cu", 1.0, 0.0)
        clip = np.zeros((g.ny, g.nx), bool)
        clip[4, 10] = True

        polys, vias, _notes = realize_overunder_rects(
            [[(4, 10, "In2.Cu"), (4, 10, "B.Cu")]], [bridge],
            {"In2.Cu": 4.0, "B.Cu": 4.0}, g,
            clip_masks={"In2.Cu": clip, "B.Cu": clip},
            strict_bridges=True)

        self.assertTrue(vias)
        for layer in ("In2.Cu", "B.Cu"):
            copper = [Polygon(coords).buffer(0)
                      for coords in polys.get(layer, ())]
            for via in vias:
                self.assertTrue(any(poly.covers(Point(*via)) for poly in copper),
                                "%s landing was clipped off a barrel" % layer)

    def test_strict_f_bridge_rejects_search_draw_admission_mismatch(self):
        from cec_slab_pour import realize_overunder_rects
        g = _G(30, 9)
        bridge = (4, 10, "F.Cu", "In3.Cu", 1.0, 0.0)
        with self.assertRaisesRegex(RuntimeError, "no admitted F.Cu landing"):
            realize_overunder_rects(
                [[(4, 10, "F.Cu"), (4, 10, "In3.Cu")]], [bridge],
                {"F.Cu": 1.6, "In3.Cu": 1.6}, g,
                f_admit=[(0.0, 0.0, 1.0, 1.0)], strict_bridges=True)

    def test_blocked_bridge_field_reseats_on_free_two_layer_spur(self):
        import cec_slab_pour
        from cec_slab_pour import realize_overunder_rects

        g = _G(12, 8)
        bridge = (4, 5, "In2.Cu", "B.Cu", 1.0, 0.0)
        masks = {"In2.Cu": np.ones((g.ny, g.nx), bool),
                 "B.Cu": np.ones((g.ny, g.nx), bool)}
        shifted_via = ((5 + 0.5) * g.cell, (4 + 0.5) * g.cell)
        with mock.patch.object(
                cec_slab_pour, "field_via_line",
                side_effect=[([], 0), ([shifted_via], 1)]) as field:
            _polys, vias, notes = realize_overunder_rects(
                [[(4, 5, "In2.Cu"), (4, 5, "B.Cu")]], [bridge],
                {"In2.Cu": 1.6, "B.Cu": 1.6}, g,
                free_masks=masks, strict_bridges=True)

        self.assertEqual(field.call_count, 2)
        self.assertEqual(vias, [shifted_via])
        self.assertTrue(any("field reseated" in note for note in notes), notes)

    def test_rect_realization_forwards_current_sized_via_count(self):
        """Corridor width must not silently override the ampacity model."""
        import cec_slab_pour
        from cec_slab_pour import realize_overunder_rects

        g = _G(12, 8)
        bridge = (4, 5, "In2.Cu", "B.Cu", 1.0, 0.0)
        masks = {"In2.Cu": np.ones((g.ny, g.nx), bool),
                 "B.Cu": np.ones((g.ny, g.nx), bool)}
        seats = [((5 + 0.5) * g.cell, (4 + 0.5 + j) * g.cell)
                 for j in (-1, 0, 1)]
        with mock.patch.object(
                cec_slab_pour, "field_via_line",
                return_value=(seats, 0)) as field:
            realize_overunder_rects(
                [[(4, 5, "In2.Cu"), (4, 5, "B.Cu")]], [bridge],
                # A deliberately wide corridor would request many vias under
                # the obsolete width heuristic.
                {"In2.Cu": 8.0, "B.Cu": 8.0}, g,
                free_masks=masks, bridge_via_count=3,
                strict_bridges=True)

        self.assertEqual(field.call_args.kwargs["n_needed"], 3)

    def test_partial_current_rated_field_is_reseated_as_one_atomic_unit(self):
        import cec_slab_pour
        from cec_slab_pour import realize_overunder_rects

        g = _G(12, 8)
        bridge = (4, 5, "In2.Cu", "B.Cu", 1.0, 0.0)
        masks = {"In2.Cu": np.ones((g.ny, g.nx), bool),
                 "B.Cu": np.ones((g.ny, g.nx), bool)}
        partial = [((5 + 0.5) * g.cell, (4 + 0.5) * g.cell)]
        complete = [((4 + 0.5 + j) * g.cell, (4 + 0.5) * g.cell)
                    for j in (-1, 0, 1)]
        with mock.patch.object(
                cec_slab_pour, "field_via_line",
                side_effect=[(partial, 0), (complete, 1)]) as field:
            _polys, vias, notes = realize_overunder_rects(
                [[(4, 5, "In2.Cu"), (4, 5, "B.Cu")]], [bridge],
                {"In2.Cu": 1.6, "B.Cu": 1.6}, g,
                free_masks=masks, bridge_via_count=3,
                strict_bridges=True)

        self.assertEqual(field.call_count, 2)
        self.assertEqual(vias, complete)
        self.assertTrue(any("field reseated" in note for note in notes), notes)

    def test_blocked_bridge_field_searches_past_one_package_width(self):
        import cec_slab_pour
        from cec_slab_pour import realize_overunder_rects

        g = _G(24, 16)
        bridge = (8, 10, "In2.Cu", "B.Cu", 1.0, 0.0)
        masks = {"In2.Cu": np.ones((g.ny, g.nx), bool),
                 "B.Cu": np.ones((g.ny, g.nx), bool)}
        shifted_via = ((5 + 0.5) * g.cell, (8 + 0.5) * g.cell)
        # Initial field + four cardinal probes at each of radii 1..4 fail.
        # The first radius-five probe (left) is a legal landing.
        outcomes = [([], 0)] * 17 + [([shifted_via], 1)]
        with mock.patch.object(
                cec_slab_pour, "field_via_line",
                side_effect=outcomes) as field:
            _polys, vias, notes = realize_overunder_rects(
                [[(8, 10, "In2.Cu"), (8, 10, "B.Cu")]], [bridge],
                {"In2.Cu": 1.6, "B.Cu": 1.6}, g,
                free_masks=masks, strict_bridges=True)

        self.assertEqual(field.call_count, 18)
        self.assertEqual(vias, [shifted_via])
        self.assertTrue(any("(8,5)" in note for note in notes), notes)

    def test_blocked_bridge_field_can_reseat_through_a_qualified_dogleg(self):
        import cec_slab_pour
        from cec_slab_pour import realize_overunder_rects

        g = _G(24, 16)
        bridge = (8, 10, "In2.Cu", "B.Cu", 1.0, 0.0)
        masks = {"In2.Cu": np.ones((g.ny, g.nx), bool),
                 "B.Cu": np.ones((g.ny, g.nx), bool)}
        shifted_via = ((9 + 0.5) * g.cell, (7 + 0.5) * g.cell)
        # Initial field plus every cardinal probe through radius eight fails;
        # the first diagonal pocket, one up and one left, succeeds.
        outcomes = [([], 0)] * 33 + [([shifted_via], 1)]
        with mock.patch.object(
                cec_slab_pour, "field_via_line",
                side_effect=outcomes) as field:
            polys, vias, notes = realize_overunder_rects(
                [[(8, 10, "In2.Cu"), (8, 10, "B.Cu")]], [bridge],
                {"In2.Cu": 1.6, "B.Cu": 1.6}, g,
                free_masks=masks, strict_bridges=True)

        self.assertEqual(field.call_count, 34)
        self.assertEqual(vias, [shifted_via])
        self.assertTrue(any("Manhattan spur" in note for note in notes), notes)
        self.assertTrue(polys["In2.Cu"])


if __name__ == "__main__":
    unittest.main()
