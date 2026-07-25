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

MM = 1e6
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


class TestPourTermination(unittest.TestCase):
    """Pour-termination ruling (owner 2026-07-25): force copper stops AT
    the shunt pad inner edge; the inter-pad gap belongs to the taps."""

    def _rs_board(self, extra_fps=()):
        # RS1: HI pad at (10,10), LO pad at (16,10), half 0.6 -> bboxes
        # 9.4-10.6 and 15.4-16.6; gap = x 10.6..15.4
        fps = [_FP("RS1", [_Pad("/S_HI", 1, 10.0, 10.0,
                                layers=[_LAY["F.Cu"]], name="1"),
                           _Pad("/S_LO", 2, 16.0, 10.0,
                                layers=[_LAY["F.Cu"]], name="2")])]
        fps += list(extra_fps)
        nets = {1: "/S_HI", 2: "/S_LO"}
        for fp in extra_fps:
            for p in fp.Pads():
                nets.setdefault(p.GetNetCode(), p.GetNetname())
        return _Board(40, 20, fps, nets)

    def test_patch_clips_at_pad_inner_edge_not_mid_gap(self):
        import cec_slab_pour
        patches = cec_slab_pour.guaranteed_shunt_patches(self._rs_board())
        by_net = {d["net"]: d["polygon"] for d in patches}
        hi_xs = [q[0] for q in by_net["/S_HI"]]
        lo_xs = [q[0] for q in by_net["/S_LO"]]
        self.assertAlmostEqual(max(hi_xs), 10.6, places=3,
                               msg="HI inner clip = the PAD INNER EDGE "
                                   "(mid-gap 12.85 is the retired rule)")
        self.assertAlmostEqual(min(lo_xs), 15.4, places=3)
        # outer/side margins keep covering the outboard via rows
        self.assertAlmostEqual(min(hi_xs), 10.0 - 0.6 - 4.5, places=3)
        ys = [q[1] for q in by_net["/S_HI"]]
        self.assertAlmostEqual(min(ys), 10.0 - 0.6 - 4.5, places=3)
        self.assertAlmostEqual(max(ys), 10.0 + 0.6 + 4.5, places=3)
        # the gap strip helper names the taps' exclusive territory
        halves = cec_slab_pour._shunt_pad_halves(self._rs_board())
        self.assertEqual(len(halves), 1)
        gx0, gy0, gx1, gy1 = halves[0]["gap"]
        self.assertAlmostEqual(gx0, 10.6, places=3)
        self.assertAlmostEqual(gx1, 15.4, places=3)

    def test_planned_vias_stay_out_of_pads_and_gap(self):
        # a corridor arriving from the GAP side (TB trunk at x=32) must
        # attach the patch-covered shunt pad from the OUTER face: no via
        # in any pad, none in the inter-pad gap.
        tb = _FP("TB1", [_Pad("/S_HI", 1, 32.0, 8.0),
                         _Pad("/S_HI", 1, 32.0, 11.0)])
        board = self._rs_board(extra_fps=(tb,))
        pours, vias, rep = plan_pours(
            board, [{"net": "/S_HI", "layers": ("In2.Cu",)}])
        self.assertTrue(rep["/S_HI"]["path_found"], rep["/S_HI"])
        self.assertTrue(vias, "the F-only shunt pad needs a terminal field")
        pad_boxes = [(9.4, 9.4, 10.6, 10.6), (15.4, 9.4, 16.6, 10.6),
                     (31.4, 7.4, 32.6, 8.6), (31.4, 10.4, 32.6, 11.6)]
        for v in vias:
            x, y = v["x_mm"], v["y_mm"]
            for (x0, y0, x1, y1) in pad_boxes:
                self.assertFalse(x + 0.45 >= x0 and x - 0.45 <= x1 and
                                 y + 0.45 >= y0 and y - 0.45 <= y1,
                                 "via (%.2f,%.2f) overlaps pad box %s"
                                 % (x, y, (x0, y0, x1, y1)))
            self.assertFalse(10.6 < x < 15.4 and 9.4 < y < 10.6,
                             "via (%.2f,%.2f) sits in the inter-pad gap "
                             "(tap territory)" % (x, y))
        # every pourplan F polygon respects the pad inner edge line: no
        # pourplan copper in the gap strip
        for d in pours:
            if d.get("layer") != "F.Cu" or \
                    not str(d.get("name", "")).startswith("pourplan:"):
                continue
            for (x, y) in d["polygon"]:
                self.assertFalse(10.6 + 1e-6 < x < 15.4 - 1e-6
                                 and 9.4 < y < 10.6,
                                 "pourplan F copper vertex in the gap: %s"
                                 % ((x, y),))


class TestViaInPadReseat(unittest.TestCase):
    """Via-in-pad ruling (owner 2026-07-25): assembly-class exclusion +
    reseat-beside-the-pad, never a silent drop."""

    def test_field_vias_slide_past_a_pad(self):
        import cec_slab_pour
        grid = cec_slab_pour.Grid(_Board(40, 20, [], {}), 0.8)
        # field at ~(20,10), travel +x -> via line runs in y; a pad box
        # sits exactly on the +y base slot -> that via must SLIDE, not drop
        r, c = grid.iy(10.0), grid.ix(20.0)
        cx = grid.x0 + (c + 0.5) * grid.cell
        cy = grid.y0 + (r + 0.5) * grid.cell
        field = (r, c, "In2.Cu", "F.Cu", 1.0, 0.0)
        pad = (cx - 0.5, cy + 0.2, cx + 0.5, cy + 1.0)  # swallows +0.6 slot
        vias, reseated = cec_pour_plan._field_vias(
            field, 0.6, grid, [pad], [])
        self.assertEqual(len(vias), 2, "count preserved: reseat, not drop")
        self.assertGreater(reseated, 0, "the blocked slot was slid past")
        for (x, y) in vias:
            self.assertFalse(cec_pour_plan._pad_hit([pad], x, y,
                                                    0.45 + 0.05),
                             "reseated via still overlaps the pad")

    def test_all_slots_blocked_is_loud_empty_never_silent(self):
        import cec_slab_pour
        grid = cec_slab_pour.Grid(_Board(40, 20, [], {}), 0.8)
        r, c = grid.iy(10.0), grid.ix(20.0)
        cx = grid.x0 + (c + 0.5) * grid.cell
        cy = grid.y0 + (r + 0.5) * grid.cell
        field = (r, c, "In2.Cu", "F.Cu", 1.0, 0.0)
        pad = (cx - 3.0, cy - 3.0, cx + 3.0, cy + 3.0)  # swallows all slots
        vias, _rs = cec_pour_plan._field_vias(field, 0.6, grid, [pad], [])
        self.assertEqual(vias, [], "total exhaustion returns [] -- the "
                                   "attach-connectivity verifier then "
                                   "fails the net (loud), never a via in "
                                   "the pad")


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


_IN_CONTAINER = (os.path.exists("/.dockerenv")
                 or os.path.exists("/run/.containerenv"))
try:
    import pcbnew as _pcbnew_mod
except ImportError:
    _pcbnew_mod = None


@unittest.skipUnless(_pcbnew_mod is not None and _IN_CONTAINER,
                     "pcbnew + the routing container required")
class TestViaInPadExclusionRealBoard(unittest.TestCase):
    """cec_fr side of the via-in-pad ruling: _via_pad_excluded /
    _via_spot_clear / add_overunder_vias on a real mini board."""

    def _board(self, tmp):
        import pcbnew
        board = pcbnew.CreateEmptyBoard()
        for (a, b) in (((0, 0), (40, 0)), ((40, 0), (40, 20)),
                       ((40, 20), (0, 20)), ((0, 20), (0, 0))):
            seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
            seg.SetStart(pcbnew.VECTOR2I(int(a[0] * MM), int(a[1] * MM)))
            seg.SetEnd(pcbnew.VECTOR2I(int(b[0] * MM), int(b[1] * MM)))
            seg.SetLayer(pcbnew.Edge_Cuts)
            board.Add(seg)
        net = pcbnew.NETINFO_ITEM(board, "+5V_TEST")
        board.Add(net)
        fp = pcbnew.FOOTPRINT(board)
        fp.SetPosition(pcbnew.VECTOR2I(int(10 * MM), int(10 * MM)))
        pad = pcbnew.PAD(fp)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I(int(2.0 * MM), int(1.0 * MM)))
        pad.SetPosition(pcbnew.VECTOR2I(int(10 * MM), int(10 * MM)))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNetCode(net.GetNetCode())
        fp.Add(pad)
        board.Add(fp)
        path = os.path.join(tmp, "viainpad-mini.kicad_pcb")
        _pcbnew_mod.SaveBoard(path, board)
        return _pcbnew_mod.LoadBoard(path), net.GetNetCode()

    def test_same_net_pad_refuses_and_beside_is_clear(self):
        import tempfile
        import pcbnew
        import cec_fr
        board, nc = self._board(tempfile.mkdtemp(prefix="cec_vip_"))
        in_pad = pcbnew.VECTOR2I(int(10 * MM), int(10 * MM))
        beside = pcbnew.VECTOR2I(int(13 * MM), int(10 * MM))
        self.assertIsNotNone(cec_fr._via_pad_excluded(board, in_pad,
                                                      int(0.9 * MM)))
        self.assertIsNone(cec_fr._via_pad_excluded(board, beside,
                                                   int(0.9 * MM)))
        # _via_spot_clear inherits it even with the pad's OWN net exempt
        self.assertFalse(cec_fr._via_spot_clear(board, in_pad,
                                                int(0.9 * MM),
                                                int(0.3 * MM), {nc}))
        self.assertTrue(cec_fr._via_spot_clear(board, beside,
                                               int(0.9 * MM),
                                               int(0.3 * MM), {nc}))
        # add_overunder_vias refuses the in-pad spot, lays the clear one
        added = cec_fr.add_overunder_vias(
            board, [{"net": "+5V_TEST", "x_mm": 10.0, "y_mm": 10.0},
                    {"net": "+5V_TEST", "x_mm": 13.0, "y_mm": 10.0}])
        self.assertEqual(len(added), 1)
        p = added[0].GetPosition()
        self.assertAlmostEqual(p.x / MM, 13.0, places=2)

    def test_force_vias_clear_a_long_shunt_pad(self):
        # the s464 root cause class: a LONG shunt pad swallowed the fixed
        # 1.6mm outboard base -> in-pad force vias. The fixed base pushes
        # past the pad extent and _via_pad_excluded guards each spot.
        import tempfile
        import pcbnew
        import cec_fr
        board = pcbnew.CreateEmptyBoard()
        for (a, b) in (((0, 0), (40, 0)), ((40, 0), (40, 20)),
                       ((40, 20), (0, 20)), ((0, 20), (0, 0))):
            seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
            seg.SetStart(pcbnew.VECTOR2I(int(a[0] * MM), int(a[1] * MM)))
            seg.SetEnd(pcbnew.VECTOR2I(int(b[0] * MM), int(b[1] * MM)))
            seg.SetLayer(pcbnew.Edge_Cuts)
            board.Add(seg)
        n_hi = pcbnew.NETINFO_ITEM(board, "/T_HI")
        n_lo = pcbnew.NETINFO_ITEM(board, "/T_LO")
        board.Add(n_hi)
        board.Add(n_lo)
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference("RS1")
        fp.SetPosition(pcbnew.VECTOR2I(int(20 * MM), int(10 * MM)))
        boxes = []
        for (name, net, cx) in (("1", n_hi, 17.5), ("2", n_lo, 22.5)):
            pad = pcbnew.PAD(fp)
            pad.SetName(name)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I(int(3.4 * MM), int(1.2 * MM)))
            pad.SetPosition(pcbnew.VECTOR2I(int(cx * MM), int(10 * MM)))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNetCode(net.GetNetCode())
            fp.Add(pad)
            boxes.append((cx - 1.7, 10 - 0.6, cx + 1.7, 10 + 0.6))
        board.Add(fp)
        tmp = tempfile.mkdtemp(prefix="cec_fv_")
        path = os.path.join(tmp, "fv-mini.kicad_pcb")
        pcbnew.SaveBoard(path, board)
        board = pcbnew.LoadBoard(path)
        rep = cec_fr.synthesize_force_vias(
            board, kelvin_pairs=[("/T_HI", "/T_LO")])
        self.assertGreater(rep["vias"], 0, "vias still lay, just outboard")
        for t in board.GetTracks():
            if t.GetClass() != "PCB_VIA":
                continue
            q = t.GetPosition()
            x, y = q.x / MM, q.y / MM
            for (x0, y0, x1, y1) in boxes:
                self.assertFalse(x + 0.45 > x0 and x - 0.45 < x1 and
                                 y + 0.45 > y0 and y - 0.45 < y1,
                                 "force via (%.2f,%.2f) overlaps pad box %s"
                                 % (x, y, (x0, y0, x1, y1)))


class _Trk:
    """Fake PCB_TRACK (pre-connect teeth)."""
    def __init__(self, net, nc, x1, y1, x2, y2, w=1.5, lay="In2.Cu",
                 locked=True):
        from test_pour_first import _Pt
        self._net, self._nc, self._w = net, nc, w
        self._s, self._e = _Pt(x1, y1), _Pt(x2, y2)
        self._lay, self._locked = _LAY[lay], locked

    def GetClass(self):
        return "PCB_TRACK"

    def GetNetname(self):
        return self._net

    def GetNetCode(self):
        return self._nc

    def GetLayer(self):
        return self._lay

    def GetWidth(self):
        return int(self._w * MM)

    def GetStart(self):
        return self._s

    def GetEnd(self):
        return self._e

    def IsLocked(self):
        return self._locked


class _TrackBoard(_Board):
    def __init__(self, W, H, fps, nets_by_code, tracks=()):
        super().__init__(W, H, fps, nets_by_code)
        self._trk = list(tracks)

    def GetTracks(self):
        return list(self._trk)


class TestPreConnectedByExistingCopper(unittest.TestCase):
    """Mandate part 1 (2026-07-25, probe-measured on live skeletons): groups
    the board's own copper (locked force rails) already connects merge into
    ONE planning group -- /SENSE3V3_LO's five groups were ALL pre-connected
    and its 598mm2 s510 fallback amoeba re-solved a finished net."""

    def _board(self, with_rail):
        nc = 1
        fps = [_FP("J1", _tht_col("+5V_MAIN", nc, 6.0, [4.0, 7.0, 10.0,
                                                        13.0])),
               _FP("TB1", _tht_col("+5V_MAIN", nc, 34.0, [4.0, 7.0, 10.0,
                                                          13.0]))]
        trk = ([_Trk("+5V_MAIN", nc, 6.0, 8.5, 34.0, 8.5)]
               if with_rail else [])
        return _TrackBoard(40, 20, fps, {nc: "+5V_MAIN", 2: "GND"}, trk)

    def test_rail_connected_net_is_trivial_no_fallback(self):
        calls, fb = _recorder()
        _p, vias, rep = plan_pours(
            self._board(True), [{"net": "+5V_MAIN", "layers": ("In2.Cu",)}],
            fallback=fb)
        e = rep["+5V_MAIN"]
        self.assertTrue(e["path_found"], e)
        self.assertTrue(e.get("trivial"),
                        "rail-connected groups must merge to ONE planning "
                        "group (already-present corridor): %s" % e)
        self.assertEqual(calls, [], "no fallback for a finished net")
        self.assertEqual(vias, [])

    def test_without_the_rail_a_corridor_is_still_planned(self):
        _p, _v, rep = plan_pours(
            self._board(False), [{"net": "+5V_MAIN", "layers": ("In2.Cu",)}])
        e = rep["+5V_MAIN"]
        self.assertTrue(e["path_found"], e)
        self.assertFalse(e.get("trivial"))
        self.assertEqual(e["corridors"], 1)


class TestRegionClassNets(unittest.TestCase):
    """Mandate part 2 + single-owner 5a (2026-07-25): many-island logic
    nets take the POWER-PLANE doctrine -- ONE clean region polygon on the
    chosen inner/bottom layer + one compact terminal via field per island.
    No tree, no bridges, no snake; the ask's layer is a preference, never
    a mandate (the realized solution owns its layer)."""

    def _board(self, blanket_in2=False):
        nc = 1
        fps = [_FP("RS1", [_Pad("/S_HI", 2, 21.0, 25.5, half=1.2,
                                layers=[_LAY["F.Cu"]]),
                           _Pad("/S_LO", 3, 25.0, 25.5, half=1.2,
                                layers=[_LAY["F.Cu"]])])]
        spots = [(18, 21), (22, 21), (26, 21), (18, 25), (26, 25),
                 (18, 29), (22, 29), (26, 29)]
        for i, (x, y) in enumerate(spots):
            fps.append(_FP("C%d" % i, [_Pad("+3V3", nc, x, y, half=0.5,
                                            layers=[_LAY["F.Cu"]])]))
        if blanket_in2:
            fps.append(_FP("U9", [_Pad("GND", 9, 22.0, 25.0, half=13.0,
                                       layers=[_LAY["In2.Cu"]])]))
        return _Board(44, 44, fps, {nc: "+3V3", 2: "/S_HI", 3: "/S_LO",
                                    9: "GND"})

    def test_region_is_one_clean_plane_with_per_island_fields(self):
        pours, vias, rep = plan_pours(
            self._board(), [{"net": "+3V3", "layers": ("In2.Cu",)}])
        e = rep["+3V3"]
        self.assertTrue(e["path_found"], e)
        self.assertEqual(e.get("planner"), "territory-region", e)
        self.assertEqual(e["corridors"], 0, "no tree for a region net")
        self.assertEqual(e["via_fields"]["crossing"], 0)
        self.assertGreaterEqual(e["via_fields"]["terminal"], 6,
                                "one drop field per island")
        self.assertEqual(e.get("region_layer"), "In2.Cu")
        region = [d for d in pours if d["net"] == "+3V3"
                  and d["layer"] == "In2.Cu"]
        self.assertEqual(len(region), 1,
                         "ONE deliberate region polygon, not %d pieces"
                         % len(region))
        self.assertTrue(vias, "islands drop through via fields")

    def test_ask_layer_is_a_preference_not_a_mandate(self):
        # In2 fully blanketed by foreign copper -> the solve OWNS the layer
        # choice and lands on B; the In2-naming ask lays NO In2 copper.
        pours, _v, rep = plan_pours(
            self._board(blanket_in2=True),
            [{"net": "+3V3", "layers": ("In2.Cu",)}])
        e = rep["+3V3"]
        self.assertTrue(e["path_found"], e)
        self.assertEqual(e.get("region_layer"), "B.Cu", e)
        self.assertFalse([d for d in pours if d["net"] == "+3V3"
                          and d["layer"] == "In2.Cu"],
                         "the ask named In2 but the winning solution lives "
                         "on B -- no In2 copper may exist")


class TestWidthInfeasibleDiag(unittest.TestCase):
    def test_empty_free_space_is_the_honest_diag(self):
        # one mid-board obstacle inflated by an infeasible half-width (the
        # probe-measured In2 class: 1oz internal demands 16-46mm for the
        # heavy rails) swallows the whole region -> free space EMPTY, and
        # _make_candidates diags 'width-infeasible', never 'pa-blocked'
        from shapely.geometry import box as _sbox
        sp = cec_pour_plan._LayerSpace(
            _sbox(0, 0, 10, 10), [_sbox(4, 4, 6, 6)], 20.0)
        self.assertIsNone(sp._prep, "an obstacle inflated past the region "
                                    "span must yield EMPTY free space")


if __name__ == "__main__":
    unittest.main()
