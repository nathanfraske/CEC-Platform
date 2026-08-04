#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# POUR-FIRST PLACEMENT RUNG teeth (owner ruling 2026-07-25, docs/slab-pour-
# design-2026-07-24.md v3 + v3.1). Host-runnable: duck-typed fake boards (no
# pcbnew) drive connector_manifolds / the width-margin attach /
# synthesize_overunder_pours' no-path manifold-only guarantee, plus the PURE
# decision cores (pourfirst_conv_split, _nowhere_zone_verdict). A
# pcbnew-gated integration test exercises the real reaper end-to-end
# in-container (skips honestly host-side).
import os
import sys
import unittest

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_slab_pour  # noqa: E402
from cec_slab_pour import (  # noqa: E402
    Grid,
    _nowhere_zone_verdict,
    _prep_overunder_net,
    connector_manifolds,
    footprint_copper_boxes,
    pourfirst_conv_split,
    route_overunder,
    synthesize_overunder_pours,
)

MM = 1e6
_LAY = {"F.Cu": 0, "In1.Cu": 1, "In2.Cu": 2, "B.Cu": 31}
_ALL_CU = list(_LAY.values())


class _BB:
    def __init__(self, x0, y0, x1, y1):                 # mm in, nm out
        self._b = (int(x0 * MM), int(y0 * MM), int(x1 * MM), int(y1 * MM))

    def GetLeft(self):
        return self._b[0]

    def GetTop(self):
        return self._b[1]

    def GetRight(self):
        return self._b[2]

    def GetBottom(self):
        return self._b[3]


class _Pt:
    def __init__(self, x_mm, y_mm):
        self.x, self.y = int(x_mm * MM), int(y_mm * MM)


class _LSet:
    def __init__(self, ids):
        self._ids = list(ids)

    def CuStack(self):
        return list(self._ids)


class _Pad:
    def __init__(self, net, nc, cx, cy, half=0.6, layers=_ALL_CU, name="1"):
        self._net, self._nc = net, nc
        self._bb = _BB(cx - half, cy - half, cx + half, cy + half)
        self._pos = _Pt(cx, cy)
        self._ls = _LSet(layers)
        self._name = name

    def GetNetname(self):
        return self._net

    def GetNetCode(self):
        return self._nc

    def GetBoundingBox(self):
        return self._bb

    def GetPosition(self):
        return self._pos

    def GetLayerSet(self):
        return self._ls

    def GetPadName(self):
        return self._name


class _Graphic:
    def __init__(self, layer, box):
        self._layer, self._bb = layer, _BB(*box)

    def GetLayer(self):
        return self._layer

    def GetBoundingBox(self):
        return self._bb


class _FP:
    def __init__(self, ref, pads, graphics=()):
        self._ref, self._pads, self._graphics = ref, pads, graphics

    def GetReference(self):
        return self._ref

    def Pads(self):
        return list(self._pads)

    def GraphicalItems(self):
        return list(self._graphics)


class _Net:
    def __init__(self, name):
        self._n = name

    def GetNetname(self):
        return self._n


class _NetInfo:
    def __init__(self, by_code):
        self._d = {c: _Net(n) for c, n in by_code.items()}

    def NetsByNetcode(self):
        return dict(self._d)


class _Board:
    def __init__(self, W, H, fps, nets_by_code):
        self._bb = _BB(0.0, 0.0, W, H)
        self._fps = fps
        self._ni = _NetInfo(nets_by_code)

    def GetFootprints(self):
        return list(self._fps)

    def GetTracks(self):
        return []

    def GetBoardEdgesBoundingBox(self):
        return self._bb

    def GetLayerID(self, name):
        return _LAY.get(name, -1)

    def GetNetInfo(self):
        return self._ni


def _wall(nc, x0, x1, y0, y1, pitch=1.2, half=0.7):
    """A solid picket of foreign THT barrels (their raster stamps + clearance
    merge into a wall)."""
    pads = []
    y = y0
    while y <= y1:
        x = x0
        while x <= x1:
            pads.append(_Pad("GND", nc, x, y, half=half))
            x += pitch
        y += pitch
    return pads


class TestGridAnchorStamp(unittest.TestCase):
    def test_small_via_anchor_cannot_claim_diagonal_neighbor_cell(self):
        grid = Grid(_Board(30, 30, [], {}), 0.8)
        mask = np.zeros((grid.ny, grid.nx), bool)
        # Real 0.6-mm pickup via from the Hub P1 case.  Conservative obstacle
        # stamping touches four cells, including (2,19), whose centre is
        # 0.95 mm from the via centre.  An electrical anchor may claim only the
        # centre-contained cell (1,20).
        grid.stamp_anchor_box(mask, 16.4375, 1.5, 17.0375, 2.1)
        self.assertTrue(mask[1, 20])
        self.assertFalse(mask[2, 19])
        ys, xs = np.where(mask)
        self.assertEqual(list(zip(ys.tolist(), xs.tolist())), [(1, 20)])


class TestConnectorManifolds(unittest.TestCase):
    def test_multi_pin_group_gangs_to_one_dict_per_layer(self):
        # 4 same-net THT pins on one connector -> ONE dict per natural layer
        # (F.Cu + In2.Cu), never 4 per-pin dicts; GND never manifolds.
        pads = [_Pad("+5VSB", 1, 6.0, 4.0 + 3.0 * k) for k in range(4)]
        pads += [_Pad("GND", 2, 9.0, 4.0), _Pad("GND", 2, 9.0, 7.0)]
        board = _Board(40, 20, [_FP("J3", pads)], {1: "+5VSB", 2: "GND"})
        out = connector_manifolds(board)
        self.assertEqual({(d["net"], d["layer"]) for d in out},
                         {("+5VSB", "F.Cu"), ("+5VSB", "In2.Cu")},
                         "one dict per (net, natural layer); GND excluded")
        for d in out:
            xs = [q[0] for q in d["polygon"]]
            ys = [q[1] for q in d["polygon"]]
            # Local attach only: group bbox + 0.3mm. The remote over-under
            # path owns width; the connector manifold must not become a slab.
            self.assertAlmostEqual(min(xs), 5.4 - 0.3, places=3)
            self.assertAlmostEqual(max(xs), 6.6 + 0.3, places=3)
            self.assertAlmostEqual(min(ys), 3.4 - 0.3, places=3)
            self.assertAlmostEqual(max(ys), 13.6 + 0.3, places=3)
            self.assertEqual(d["name"], "manifold:J3:+5VSB")
            self.assertEqual(d["provenance"], "slab")
            self.assertEqual(d["priority"], 3,
                             "manifold must outrank its same-net feeder zone")

    def test_smd_group_gets_its_own_side_only(self):
        pads = [_Pad("/SIG", 3, 10.0, 5.0, layers=[_LAY["B.Cu"]]),
                _Pad("/SIG", 3, 12.0, 5.0, layers=[_LAY["B.Cu"]])]
        board = _Board(40, 20, [_FP("J9", pads)], {3: "/SIG"})
        out = connector_manifolds(board)
        self.assertEqual([(d["net"], d["layer"]) for d in out],
                         [("/SIG", "B.Cu")])

    def test_nets_filter_and_non_connector_refs_ignored(self):
        pads = [_Pad("+3V3", 4, 6.0, 6.0)]
        board = _Board(40, 20, [_FP("U1", pads),
                                _FP("J1", [_Pad("+3V3", 4, 20.0, 6.0)])],
                       {4: "+3V3"})
        self.assertEqual(connector_manifolds(board, nets={"+5VSB"}), [],
                         "nets filter excludes everything else")
        out = connector_manifolds(board, nets={"+3V3"})
        self.assertTrue(out and all(d["name"].startswith("manifold:J1:")
                                    for d in out),
                        "U1 is not a connector; J1 is")

    def test_single_pin_manifold_does_not_cover_adjacent_foreign_pin(self):
        own = _Pad("+5VSB", 1, 10.0, 10.0, half=0.6)
        foreign = _Pad("/SIG", 2, 12.54, 10.0, half=0.6)
        board = _Board(30, 20, [_FP("J4", [own, foreign])],
                       {1: "+5VSB", 2: "/SIG"})
        rows = connector_manifolds(board, nets={"+5VSB"})
        self.assertTrue(rows)
        for row in rows:
            xs = [point[0] for point in row["polygon"]]
            self.assertLess(max(xs), 12.54 - 0.6,
                            "single-pin pickup must not slab across its neighbor")
            self.assertAlmostEqual(min(xs), 10.0 - 0.6 - 0.3, places=3)
            self.assertAlmostEqual(max(xs), 10.0 + 0.6 + 0.3, places=3)

    def test_footprint_copper_graphics_are_via_obstacles(self):
        fp = _FP("LOGO1", [], [_Graphic(_LAY["B.Cu"], (4.0, 5.0, 8.0, 9.0)),
                               _Graphic(99, (20.0, 21.0, 22.0, 23.0))])
        board = _Board(30, 30, [fp], {})
        boxes = footprint_copper_boxes(
            board, is_copper_layer=lambda layer: layer in _ALL_CU)
        self.assertEqual(boxes, [(4.0, 5.0, 8.0, 9.0)],
                         "only actual footprint copper may block the via field")


def _attach_scene():
    """The v3.1 thesis scene: an own THT pad DEEP in a foreign barrel field,
    reachable only through a sub-width corridor (erosion kills it; the
    4-cell anchor taper does not span the field), + an open-board sink pad.
    Returns (board, nc, manifold_dict)."""
    nc = 1
    own = [_Pad("+5VSB", nc, 10.0, 8.0), _Pad("+5VSB", nc, 30.0, 8.0)]
    foreign = []
    # solid slabs above/below a 1-cell corridor at y~8, pad pocket inside;
    # field spans x 7..16 -- the corridor exit (x~16.7 with clearance) is
    # ~7 cells from the pad: outside the 4-cell taper reach.
    foreign += _wall(2, 7.0, 16.0, 3.0, 6.6)
    foreign += _wall(2, 7.0, 16.0, 9.4, 13.0)
    foreign += _wall(2, 7.0, 7.6, 7.0, 9.0)      # left cap seals the pocket
    fps = [_FP("J3", [own[0]] + foreign), _FP("TB1", [own[1]])]
    board = _Board(40, 20, fps, {nc: "+5VSB", 2: "GND"})
    manifold = {"net": "+5VSB", "layer": "In2.Cu",
                "polygon": [(5.0, 4.0), (22.0, 4.0), (22.0, 12.0),
                            (5.0, 12.0)],
                "provenance": "slab", "priority": 2,
                "name": "manifold:J3:+5VSB"}
    return board, nc, manifold


class TestWidthMarginAttach(unittest.TestCase):
    def _prep(self, board, nc, manifolds):
        grid = Grid(board, 0.8)
        shunt = np.zeros((grid.ny, grid.nx), bool)
        prep, why = _prep_overunder_net(
            board, "+5VSB", nc, ["In2.Cu"], grid, net_currents={},
            shunt_mask=shunt, manifolds=manifolds)
        self.assertIsNone(why)
        return grid, prep

    def test_without_manifold_the_walled_terminal_is_unreachable(self):
        board, nc, _m = _attach_scene()
        _grid, prep = self._prep(board, nc, ())
        _pc, _br, ok, bottleneck = route_overunder(
            prep["layers"], prep["passable"], prep["anchors"], prep["clab"],
            prep["nclusters"], bias_fn=prep["bias_fn"])
        self.assertFalse(ok, "the walled pin must be unreachable at width "
                             "without a manifold (the s415 no-path class)")
        self.assertIsNotNone(bottleneck)

    def test_attach_replaces_cluster_anchors_and_connects(self):
        board, nc, manifold = _attach_scene()
        grid, prep = self._prep(board, nc, (manifold,))
        # the walled pad's raw anchor cell must be REPLACED on the manifold
        # layer: no longer an anchor there...
        iy, ix = grid.iy(8.0), grid.ix(10.0)
        self.assertFalse(prep["anchors"]["In2.Cu"][iy, ix],
                         "raw pad cell must be replaced as an attach target")
        # ...by eroded manifold cells carrying the cluster's label
        self.assertIn("attach_notes", prep)
        self.assertTrue(any("eroded manifold cell" in n
                            for n in prep["attach_notes"]),
                        prep["attach_notes"])
        new_targets = prep["anchors"]["In2.Cu"] & (prep["clab"] > 0)
        self.assertTrue(new_targets.any())
        # and the search now CONNECTS (the v3.1 thesis)
        _pc, _br, ok, bottleneck = route_overunder(
            prep["layers"], prep["passable"], prep["anchors"], prep["clab"],
            prep["nclusters"], bias_fn=prep["bias_fn"])
        self.assertTrue(ok, bottleneck)

    def test_empty_erosion_falls_back_to_raw_anchors(self):
        board, nc, manifold = _attach_scene()
        # a sliver manifold (1 cell wide) erodes to nothing -> raw anchors
        # kept + a loud note
        sliver = dict(manifold,
                      polygon=[(9.4, 7.6), (10.6, 7.6), (10.6, 8.4),
                               (9.4, 8.4)])
        _grid, prep = self._prep(board, nc, (sliver,))
        self.assertTrue(any("erosion empty" in n
                            for n in prep["attach_notes"]),
                        prep["attach_notes"])
        iy, ix = _grid.iy(8.0), _grid.ix(10.0)
        self.assertTrue(prep["anchors"]["In2.Cu"][iy, ix],
                        "fallback keeps the raw pad anchor")


class TestNoPathLaysOnlyManifolds(unittest.TestCase):
    def test_no_path_net_yields_manifold_dicts_only(self):
        # two clusters hermetically walled on EVERY layer -> no path can
        # exist; the returned dicts for the net must be its manifolds ONLY
        # (never lanes, never board-wide fallback sprawl -- deliverable C).
        nc = 3
        fps = [_FP("J7", [_Pad("/SENSE12V_HI", nc, 5.0, 5.0)]),
               _FP("TB9", [_Pad("/SENSE12V_HI", nc, 35.0, 15.0)]),
               _FP("U9", _wall(2, 18.0, 20.0, 0.5, 19.5))]
        board = _Board(40, 20, fps, {nc: "/SENSE12V_HI", 2: "GND"})
        pours, vias, rep = synthesize_overunder_pours(
            board, [{"net": "/SENSE12V_HI", "layers": ("In2.Cu",)}],
            manifolds=True)
        self.assertFalse(rep["/SENSE12V_HI"]["path_found"])
        mine = [d for d in pours if d["net"] == "/SENSE12V_HI"]
        self.assertTrue(mine, "manifolds must still be laid for a no-path net")
        self.assertTrue(all(str(d.get("name", "")).startswith("manifold:")
                            for d in mine),
                        "ONLY manifolds -- no lanes, no fallback sprawl: %r"
                        % [d.get("name") for d in mine])
        self.assertEqual(vias, [], "no bridges for a net that found no path")

    def test_manifolds_off_is_byte_identical_no_dicts(self):
        nc = 3
        fps = [_FP("J7", [_Pad("/X", nc, 5.0, 5.0)]),
               _FP("TB9", [_Pad("/X", nc, 35.0, 15.0)]),
               _FP("U9", _wall(2, 18.0, 20.0, 0.5, 19.5))]
        board = _Board(40, 20, fps, {nc: "/X", 2: "GND"})
        pours, _v, rep = synthesize_overunder_pours(
            board, [{"net": "/X", "layers": ("In2.Cu",)}])
        self.assertFalse(rep["/X"]["path_found"])
        self.assertEqual(pours, [], "manifolds default OFF: import-side "
                                    "callers unchanged")


class TestFrozenPassthrough(unittest.TestCase):
    def test_frozen_nets_never_re_enter_the_conversion(self):
        ask_a = {"net": "+5VSB", "provenance": "placer_ask"}
        ask_b = {"net": "+3V3", "provenance": "placer_ask"}
        rail_c = {"net": "/SENSE12V_HI", "provenance": "rail_compiler"}
        frz_a = {"net": "+5VSB", "provenance": "pourfirst",
                 "name": "pourfirst:+5VSB"}
        pours = [ask_a, ask_b, rail_c, frz_a]
        # full conversion (CEC_SLAB_POUR=1, the 24-pin recipe)
        conv, frozen, keep = pourfirst_conv_split(pours, {"+5VSB"}, True)
        self.assertNotIn(ask_a, conv, "a frozen net's ask is never re-solved")
        self.assertTrue(all(p.get("provenance") != "pourfirst" for p in conv))
        self.assertEqual(frozen, [frz_a])
        self.assertIs(keep[0], frz_a, "frozen dict passes through AS-IS")
        self.assertEqual([p["net"] for p in conv], ["+3V3", "/SENSE12V_HI"])
        # placer_ask-only conversion (no CEC_SLAB_POUR)
        conv2, frozen2, keep2 = pourfirst_conv_split(pours, {"+5VSB"}, False)
        self.assertEqual(conv2, [ask_b])
        self.assertEqual(frozen2, [frz_a])
        self.assertIn(rail_c, keep2, "non-ask dicts survive when not full")
        self.assertIn(frz_a, keep2)

    def test_no_frozen_state_reduces_to_the_historical_filter(self):
        ask = {"net": "A", "provenance": "placer_ask"}
        rail = {"net": "B", "provenance": "rail_compiler"}
        conv, frozen, keep = pourfirst_conv_split([ask, rail], set(), True)
        self.assertEqual((conv, frozen, keep), ([ask, rail], [], []))
        conv, frozen, keep = pourfirst_conv_split([ask, rail], set(), False)
        self.assertEqual((conv, frozen, keep), ([ask], [], [rail]))


class TestNowhereReaperVerdict(unittest.TestCase):
    def test_reaps_sub_two_cluster_zone(self):
        self.assertTrue(_nowhere_zone_verdict("", "+5V_MAIN", 1))
        self.assertTrue(_nowhere_zone_verdict("slab:+5V_MAIN", "+5V_MAIN", 0))

    def test_two_clusters_survive(self):
        self.assertFalse(_nowhere_zone_verdict("", "+5V_MAIN", 2))

    def test_named_exemption_protects_single_cluster_only(self):
        # ZERO-CONNECTION OVERRIDE (mandate part 4b, 2026-07-25, measured on
        # the s510 winner: exempt-named `pourplan:` fragments touching NO
        # terminal cluster survived both reaps = the owner's "pours that
        # exist for no reason"). The name exemption protects the sanctioned
        # SINGLE-cluster judgment only; zero-cluster dies regardless of name.
        self.assertFalse(_nowhere_zone_verdict("patch:+5VSB", "+5VSB", 1))
        self.assertFalse(_nowhere_zone_verdict("manifold:J3:+5VSB", "+5VSB", 1))
        self.assertFalse(_nowhere_zone_verdict("pourfirst:+3V3", "+3V3", 1))
        self.assertTrue(_nowhere_zone_verdict("patch:+5VSB", "+5VSB", 0))
        self.assertTrue(_nowhere_zone_verdict("manifold:J3:+5VSB", "+5VSB", 0))
        self.assertTrue(_nowhere_zone_verdict("pourfirst:+3V3", "+3V3", 0))
        self.assertTrue(_nowhere_zone_verdict("pourplan:+3V3", "+3V3", 0))

    def test_gnd_never_reaped(self):
        self.assertFalse(_nowhere_zone_verdict("", "GND", 0))


class TestEnumerateWinning(unittest.TestCase):
    """SINGLE-OWNER WHITELIST (owner sharpening 2026-07-25): after the
    solve, the keep-set is ENUMERATED -- winning copper + the attach pieces
    the path lands on + required bridges/barrel covers; every other
    same-net pour piece dies by default."""

    def _rect(self, x0, y0, x1, y1):
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    def test_winning_lane_and_its_attach_manifold_survive(self):
        lane = {"net": "+5V", "layer": "In2.Cu", "name": "pourplan:+5V",
                "polygon": self._rect(10, 10, 30, 12)}
        att = {"net": "+5V", "layer": "In2.Cu", "name": "manifold:J1:+5V",
               "polygon": self._rect(8, 8, 12, 14)}
        dup = {"net": "+5V", "layer": "F.Cu", "name": "manifold:J1:+5V",
               "polygon": self._rect(8, 8, 12, 14)}
        kept, dropped = cec_slab_pour.enumerate_winning(
            [lane, att, dup], [])
        self.assertIn(lane, kept, "solution copper is the whitelist core")
        self.assertIn(att, kept, "the attach piece the path lands on IS "
                                 "winning copper")
        self.assertIn(dup, [d for (d, _w) in dropped],
                      "the same-footprint duplicate on a layer the solution "
                      "does not use must die")

    def test_required_bridge_cover_survives_via_embed(self):
        man = {"net": "+5V", "layer": "B.Cu", "name": "manifold:J1:+5V",
               "polygon": self._rect(8, 8, 12, 14)}
        kept, dropped = cec_slab_pour.enumerate_winning(
            [man], [{"net": "+5V", "x_mm": 10.0, "y_mm": 11.0}])
        self.assertIn(man, kept, "a piece embedding a solution via is a "
                                 "required bridge landing")

    def test_insurance_patch_dies_barrel_cover_patch_survives(self):
        p_dead = {"net": "/S_HI", "layer": "F.Cu", "name": "patch:/S_HI",
                  "polygon": self._rect(40, 40, 46, 46)}
        p_live = {"net": "/S_HI", "layer": "F.Cu", "name": "patch:/S_HI",
                  "polygon": self._rect(10, 10, 16, 16)}
        kept, dropped = cec_slab_pour.enumerate_winning(
            [p_dead, p_live], [],
            locked_vias=[("/S_HI", 12.0, 12.0)])
        self.assertIn(p_live, kept, "locked barrels need their cover")
        self.assertIn(p_dead, [d for (d, _w) in dropped],
                      "an insurance patch serving no F use and no barrel "
                      "is the owner's 'pour that goes nowhere'")

    def test_patch_with_solution_f_copper_survives(self):
        land = {"net": "/S_HI", "layer": "F.Cu", "name": "pourplan:/S_HI",
                "polygon": self._rect(11, 11, 14, 14)}
        patch = {"net": "/S_HI", "layer": "F.Cu", "name": "patch:/S_HI",
                 "polygon": self._rect(10, 10, 16, 16)}
        kept, _d = cec_slab_pour.enumerate_winning([land, patch], [])
        self.assertIn(patch, kept)

    def test_gang_keep_holds_one_layer_of_a_trivial_nets_manifolds(self):
        m_in2 = {"net": "+5VSB", "layer": "In2.Cu",
                 "name": "manifold:J3:+5VSB",
                 "polygon": self._rect(8, 8, 12, 14)}
        m_f = {"net": "+5VSB", "layer": "F.Cu", "name": "manifold:J3:+5VSB",
               "polygon": self._rect(8, 8, 12, 14)}
        kept, dropped = cec_slab_pour.enumerate_winning(
            [m_in2, m_f], [], gang_keep={"+5VSB": "In2.Cu"})
        self.assertIn(m_in2, kept, "the gang IS the trivial net's solution")
        self.assertIn(m_f, [d for (d, _w) in dropped])

    def test_no_path_net_keeps_manifolds_v3_loud_rule(self):
        m1 = {"net": "/X", "layer": "In2.Cu", "name": "manifold:J3:/X",
              "polygon": self._rect(8, 8, 12, 14)}
        m2 = {"net": "/X", "layer": "F.Cu", "name": "manifold:J3:/X",
              "polygon": self._rect(8, 8, 12, 14)}
        kept, _d = cec_slab_pour.enumerate_winning(
            [m1, m2], [], no_path_nets=["/X"])
        self.assertIn(m1, kept)
        self.assertIn(m2, kept)


_IN_CONTAINER = (os.path.exists("/.dockerenv")
                 or os.path.exists("/run/.containerenv"))


@unittest.skipUnless(cec_slab_pour.pcbnew is not None and _IN_CONTAINER,
                     "pcbnew + the routing container required (a host-side "
                     "partial pcbnew build segfaults in the zone filler)")
class TestNowhereReaperOnRealBoard(unittest.TestCase):
    def _mini_board(self, tmp):
        import pcbnew
        board = pcbnew.CreateEmptyBoard()
        # outline 40x20
        for (a, b) in (((0, 0), (40, 0)), ((40, 0), (40, 20)),
                       ((40, 20), (0, 20)), ((0, 20), (0, 0))):
            seg = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
            seg.SetStart(pcbnew.VECTOR2I(int(a[0] * MM), int(a[1] * MM)))
            seg.SetEnd(pcbnew.VECTOR2I(int(b[0] * MM), int(b[1] * MM)))
            seg.SetLayer(pcbnew.Edge_Cuts)
            board.Add(seg)
        net = pcbnew.NETINFO_ITEM(board, "+5V_TEST")
        board.Add(net)
        # two same-net vias = two terminal clusters, both on the LEFT half
        for x in (6.0, 14.0):
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(int(x * MM), int(10.0 * MM)))
            v.SetDrill(int(0.3 * MM))
            v.SetWidth(int(0.6 * MM))
            v.SetNetCode(net.GetNetCode())
            board.Add(v)

        def zone(x0, x1, name):
            z = pcbnew.ZONE(board)
            ls = pcbnew.LSET()
            ls.AddLayer(board.GetLayerID("F.Cu"))
            z.SetLayerSet(ls)
            z.SetNetCode(net.GetNetCode())
            z.SetMinThickness(int(0.25 * MM))
            o = z.Outline()
            o.NewOutline()
            for (x, y) in ((x0, 4.0), (x1, 4.0), (x1, 16.0), (x0, 16.0)):
                o.Append(int(x * MM), int(y * MM))
            z.SetZoneName(name)
            board.Add(z)
            return z
        zone(2.0, 18.0, "")                 # spans BOTH via clusters -> stays
        zone(24.0, 30.0, "")                # touches NO cluster -> reaped
        # part 4b (owner 2026-07-25): the name exemption protects the
        # sanctioned SINGLE-cluster judgment only -- a named zone touching
        # NOTHING dies like any other (measured on the s510 winner)
        zone(32.0, 38.0, "patch:+5V_TEST")  # 0 clusters, NAMED -> reaped
        zone(4.0, 8.0, "patch:one")         # 1 cluster, NAMED -> stays
        path = os.path.join(tmp, "reaper-mini.kicad_pcb")
        # ZONE_FILLER segfaults on an in-memory CreateEmptyBoard (measured
        # in-container, 2026-07-25) -- fill on a LOADED board, the pattern
        # every production fill site uses.
        pcbnew.SaveBoard(path, board)
        loaded = pcbnew.LoadBoard(path)
        pcbnew.ZONE_FILLER(loaded).Fill(loaded.Zones())
        pcbnew.SaveBoard(path, loaded)
        return path

    def test_reaper_kills_nowhere_zone_but_never_named(self):
        import tempfile
        import pcbnew
        tmp = tempfile.mkdtemp(prefix="cec_reap_test_")
        path = self._mini_board(tmp)
        n = cec_slab_pour.reap_nowhere_zones(path)
        self.assertEqual(n, 2, "the unnamed AND the named zero-cluster "
                               "zones are reaped")
        after = pcbnew.LoadBoard(path)
        names = sorted(z.GetZoneName() for z in after.Zones())
        self.assertIn("patch:one", names, "a named single-cluster patch "
                                          "keeps the sanctioned exemption")
        self.assertNotIn("patch:+5V_TEST", names,
                         "zero-cluster dies regardless of name (part 4b)")
        self.assertEqual(len(names), 2)


if __name__ == "__main__":
    unittest.main()
