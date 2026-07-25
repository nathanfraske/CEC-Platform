#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# v4 TERRITORY POUR PLANNER teeth (docs/slab-pour-design-2026-07-24.md v4).
# Host-runnable: the duck-typed fake boards from test_pour_first drive
# cec_pour_plan.plan_pours end-to-end (no pcbnew). The five task-mandated
# teeth: (1) a corridor between two manifolds is straight / one-bend on the
# obstacle-corner graph; (2) 2D overlap forces distinct layers (zero
# same-layer inter-net overlap is HARD); (3) a forced crossing yields
# exactly ONE compact via field at the defined crossing point; (4) the
# verifier rejects a deliberately-thin corridor (min-width invariant);
# (5) the route_overunder fallback fires ONLY on planner failure.
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cec_pour_plan  # noqa: E402
from cec_pour_plan import plan_pours  # noqa: E402
from test_pour_first import _LAY, _Board, _FP, _Pad, _wall  # noqa: E402

B_CU = [_LAY["B.Cu"]]
IN2_CU = [_LAY["In2.Cu"]]


def _tht_col(net, nc, x, ys):
    return [_Pad(net, nc, x, y) for y in ys]


def _recorder():
    calls = []

    def fb(board, ask, sub):
        calls.append(ask.get("net"))
        return [], [], {"path_found": False, "reason": "recorded"}
    return calls, fb


class TestStraightCorridor(unittest.TestCase):
    def _board(self, with_wall=False):
        nc = 1
        fps = [_FP("J1", _tht_col("+5V_MAIN", nc, 6.0, [4.0, 7.0, 10.0, 13.0])),
               _FP("TB1", _tht_col("+5V_MAIN", nc, 34.0, [4.0, 7.0, 10.0,
                                                          13.0]))]
        if with_wall:
            # foreign THT picket x~19-21 leaving a gap only at the bottom
            fps.append(_FP("W1", _wall(2, 19.0, 21.0, 0.5, 12.0)))
        return _Board(40, 20, fps, {nc: "+5V_MAIN", 2: "GND"})

    def test_open_board_is_one_straight_corridor_no_fields(self):
        board = self._board()
        pours, vias, rep = plan_pours(
            board, [{"net": "+5V_MAIN", "layers": ("In2.Cu",)}])
        e = rep["+5V_MAIN"]
        self.assertTrue(e["path_found"], e)
        self.assertEqual(e["corridors"], 1)
        self.assertEqual(e["bends"], 0, "two manifolds on an open board "
                                        "connect STRAIGHT")
        self.assertEqual(e["via_fields"], {"terminal": 0, "crossing": 0},
                         "THT manifolds anchor every layer: no via fields")
        self.assertEqual(vias, [])
        mine = [d for d in pours if d["net"] == "+5V_MAIN"]
        self.assertTrue(any(d["provenance"] == "pourplan" and
                            d["name"] == "pourplan:+5V_MAIN" for d in mine),
                        [d.get("name") for d in mine])
        self.assertTrue(any(str(d.get("name", "")).startswith("manifold:")
                            for d in mine), "stage-0 manifolds still lead")

    def test_wall_forces_one_bend_on_the_corner_graph(self):
        board = self._board(with_wall=True)
        _p, _v, rep = plan_pours(
            board, [{"net": "+5V_MAIN", "layers": ("In2.Cu",)}])
        e = rep["+5V_MAIN"]
        self.assertTrue(e["path_found"], e)
        self.assertEqual(e["corridors"], 1)
        self.assertGreaterEqual(e["bends"], 1, "the picket forces a bend")
        self.assertLessEqual(e["bends"], 2, "corner-graph path stays "
                                            "purposeful (L-ish), never a "
                                            "cell-walk staircase")


class TestOverlapForcesLayers(unittest.TestCase):
    def test_crossing_nets_take_distinct_layers(self):
        # net A horizontal, net B vertical, crossing mid-board: candidate
        # capsules overlap in 2D, so zero-same-layer-overlap forces them
        # onto different layers -- and NO via field (different nets on
        # different layers cross for free).
        fps = [_FP("U1", [_Pad("/A", 1, 5.0, 10.0)]),
               _FP("U2", [_Pad("/A", 1, 35.0, 10.0)]),
               _FP("U3", [_Pad("/B", 3, 20.0, 3.0)]),
               _FP("U4", [_Pad("/B", 3, 20.0, 17.0)])]
        board = _Board(40, 20, fps, {1: "/A", 3: "/B"})
        _p, vias, rep = plan_pours(
            board, [{"net": "/A", "layers": ("In2.Cu",)},
                    {"net": "/B", "layers": ("In2.Cu",)}])
        self.assertTrue(rep["/A"]["path_found"], rep["/A"])
        self.assertTrue(rep["/B"]["path_found"], rep["/B"])
        la = set(rep["/A"]["layers_used"])
        lb = set(rep["/B"]["layers_used"])
        self.assertTrue(la.isdisjoint(lb),
                        "overlapping corridors must sit on distinct layers "
                        "(A=%s B=%s)" % (la, lb))
        self.assertEqual(vias, [], "THT terminals + distinct layers: no "
                                   "via field anywhere")


class TestForcedCrossing(unittest.TestCase):
    def test_split_yields_exactly_one_crossing_field(self):
        # /AVERT is forced onto In2 (B-only foreign walls swallow its pads
        # on B), /BVERT is forced onto B (In2-only walls), /XNET crosses
        # BOTH -- no single conflict-free layer exists, so it must SPLIT at
        # ONE defined crossing with ONE compact via field there. F.Cu is
        # choked away mid-board by a far-corner shunt.
        nc_x, nc_a, nc_b = 1, 3, 4
        fps = [
            _FP("U1", [_Pad("/XNET", nc_x, 4.0, 10.0)]),
            _FP("U2", [_Pad("/XNET", nc_x, 44.0, 10.0)]),
            _FP("U3", [_Pad("/AVERT", nc_a, 16.0, 2.0)]),
            _FP("U4", [_Pad("/AVERT", nc_a, 16.0, 18.0)]),
            _FP("U5", [_Pad("/BVERT", nc_b, 32.0, 2.0)]),
            _FP("U6", [_Pad("/BVERT", nc_b, 32.0, 18.0)]),
            # B-only walls around /AVERT's pads (gap at y~10 for /XNET)
            _FP("W1", _wall(5, 13.0, 19.0, 0.5, 6.5, half=0.7)),
            _FP("W2", _wall(5, 13.0, 19.0, 13.5, 19.5, half=0.7)),
            # In2-only walls around /BVERT's pads
            _FP("W3", _wall(6, 29.0, 35.0, 0.5, 6.5, half=0.7)),
            _FP("W4", _wall(6, 29.0, 35.0, 13.5, 19.5, half=0.7)),
            # far-corner shunt: F.Cu becomes shunt-neighborhood-only
            _FP("RS9", [_Pad("/SH_HI", 8, 43.5, 3.0),
                        _Pad("/SH_LO", 9, 45.5, 3.0)]),
        ]
        for fp in fps:
            if fp.GetReference() in ("W1", "W2"):
                for p in fp.Pads():
                    p._ls = type(p._ls)(B_CU)          # B-only foreign
            if fp.GetReference() in ("W3", "W4"):
                for p in fp.Pads():
                    p._ls = type(p._ls)(IN2_CU)        # In2-only foreign
        board = _Board(48, 20, fps,
                       {nc_x: "/XNET", nc_a: "/AVERT", nc_b: "/BVERT",
                        5: "GNDB", 6: "GNDI", 8: "/SH_HI", 9: "/SH_LO"})
        _p, vias, rep = plan_pours(
            board, [{"net": "/XNET", "layers": ("In2.Cu",)},
                    {"net": "/AVERT", "layers": ("In2.Cu",)},
                    {"net": "/BVERT", "layers": ("In2.Cu",)}])
        self.assertTrue(rep["/AVERT"]["path_found"], rep["/AVERT"])
        self.assertTrue(rep["/BVERT"]["path_found"], rep["/BVERT"])
        self.assertEqual(rep["/AVERT"]["layers_used"], ["In2.Cu"])
        self.assertEqual(rep["/BVERT"]["layers_used"], ["B.Cu"])
        ex = rep["/XNET"]
        self.assertTrue(ex["path_found"], ex)
        self.assertNotIn("fallback", ex, "a split is a PLAN, not a fallback")
        self.assertEqual(ex["via_fields"]["crossing"], 1,
                         "exactly ONE via field at the defined crossing: %r"
                         % ex)
        self.assertEqual(ex["via_fields"]["terminal"], 0,
                         "THT terminals need no fields")
        xv = [v for v in vias if v["net"] == "/XNET"]
        self.assertTrue(xv, "the crossing field lays real vias")
        self.assertTrue(all(4.0 < v["x_mm"] < 44.0 for v in xv),
                        "field sits at the crossing point, mid-run: %r" % xv)
        self.assertLessEqual(len(xv), 3, "COMPACT array, never smeared")


class TestVerifierRejectsThin(unittest.TestCase):
    def test_thin_corridor_fails_min_width_and_falls_back(self):
        # sabotage realization: capsules at quarter width. The exact
        # geometric erosion (min-width invariant) must reject every
        # corridor and the net must fall back -- loudly labeled.
        nc = 1
        fps = [_FP("J1", _tht_col("+5V", nc, 6.0, [8.0, 11.0])),
               _FP("TB1", _tht_col("+5V", nc, 34.0, [8.0, 11.0]))]
        board = _Board(40, 20, fps, {nc: "+5V"})
        calls, fb = _recorder()
        real = cec_pour_plan._capsule
        try:
            cec_pour_plan._capsule = lambda pts, hw: real(pts, hw / 4.0)
            _p, _v, rep = plan_pours(
                board, [{"net": "+5V", "layers": ("In2.Cu",)}], fallback=fb)
        finally:
            cec_pour_plan._capsule = real
        e = rep["+5V"]
        self.assertEqual(calls, ["+5V"], "fallback must fire for the net")
        self.assertEqual(e.get("fallback"), "route_overunder")
        self.assertIn("min-width", str(e.get("planner_reason")),
                      "the rejection names the violated invariant: %r" % e)


class TestFallbackOnlyOnFailure(unittest.TestCase):
    def test_healthy_net_plans_walled_net_falls_back(self):
        nc_h, nc_w = 1, 3
        fps = [
            _FP("U1", [_Pad("/H", nc_h, 5.0, 16.0)]),
            _FP("U2", [_Pad("/H", nc_h, 12.0, 16.0)]),
            _FP("U3", [_Pad("/W", nc_w, 5.0, 3.0)]),
            _FP("U4", [_Pad("/W", nc_w, 35.0, 3.0)]),
            # hermetic full-height THT wall between /W's pads (blocks every
            # layer; /H lives entirely left of it)
            _FP("W1", _wall(2, 19.0, 21.0, 0.5, 19.5)),
        ]
        board = _Board(40, 20, fps, {nc_h: "/H", nc_w: "/W", 2: "GND"})
        calls, fb = _recorder()
        _p, _v, rep = plan_pours(
            board, [{"net": "/H", "layers": ("In2.Cu",)},
                    {"net": "/W", "layers": ("In2.Cu",)}], fallback=fb)
        self.assertTrue(rep["/H"]["path_found"], rep["/H"])
        self.assertNotIn("fallback", rep["/H"],
                         "fallback NEVER fires on a planner success")
        self.assertEqual(calls, ["/W"],
                         "fallback fires for exactly the failed net")
        self.assertEqual(rep["/W"].get("fallback"), "route_overunder")

    def test_trivial_single_group_is_no_fallback(self):
        nc = 1
        fps = [_FP("U1", [_Pad("/T", nc, 5.0, 5.0)])]
        board = _Board(40, 20, fps, {nc: "/T"})
        calls, fb = _recorder()
        _p, _v, rep = plan_pours(
            board, [{"net": "/T", "layers": ("In2.Cu",)}], fallback=fb)
        self.assertEqual(calls, [])
        self.assertTrue(rep["/T"].get("trivial"))
        self.assertTrue(rep["/T"]["path_found"],
                        "single-cluster contract matches route_overunder")


class TestCollectContract(unittest.TestCase):
    def test_collect_carries_reservation_internals(self):
        nc = 1
        fps = [_FP("J1", _tht_col("+5V", nc, 6.0, [8.0, 11.0])),
               _FP("TB1", _tht_col("+5V", nc, 34.0, [8.0, 11.0]))]
        board = _Board(40, 20, fps, {nc: "+5V"})
        collect = {}
        plan_pours(board, [{"net": "+5V", "layers": ("In2.Cu",)}],
                   collect=collect)
        self.assertIn("_grid", collect)
        ci = collect["+5V"]
        self.assertTrue(ci["ok"])
        self.assertTrue(any(m.any() for m in ci["path_cells"].values()))
        self.assertIn("foreign", ci)
        self.assertIn("reqw", ci)
        # the reservation consumer runs on it unmodified
        import cec_slab_pour
        cors, reserved = cec_slab_pour.reservation_from_search(
            "+5V", ci["ok"], ci["path_cells"], ci["bridges"], ci["rcells"],
            ci["foreign"], collect["_grid"])
        self.assertTrue(reserved)
        self.assertTrue(all(c["net"] == "+5V" for c in cors))


if __name__ == "__main__":
    unittest.main()
