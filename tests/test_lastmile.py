#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Last-mile completer teeth (2026-07-23, from the s120 residual autopsy: 13 of
# 30 unconnected gaps were <=5mm same-net pad/via/track gaps FR left in dense
# clusters -- incl. both GND criticals). The completer closes them post-fill
# with guarded canonical 0/45/90 legs or the over-the-top bridge; it must refuse
# blocked and edge-hugging gaps and leave far gaps alone. pcbnew required
# (container-only skip).
import os
import math
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _board(pads, edge=None):
    """Minimal 4-layer board: pads = [(x_mm, y_mm, net), ...] one SMD pad per
    footprint on F.Cu; edge = (x0, y0, x1, y1) optional Edge.Cuts rect."""
    import pcbnew
    b = pcbnew.BOARD()
    b.SetCopperLayerCount(4)
    nets = {}
    for x, y, net in pads:
        if net not in nets:
            ni = pcbnew.NETINFO_ITEM(b, net)
            b.Add(ni)
            nets[net] = ni
        fp = pcbnew.FOOTPRINT(b)
        fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
        p = pcbnew.PAD(fp)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetSize(pcbnew.VECTOR2I(int(0.8e6), int(0.8e6)))
        p.SetPosition(fp.GetPosition())
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        p.SetLayerSet(ls)
        p.SetNet(nets[net])
        fp.Add(p)
        b.Add(fp)
    if edge:
        x0, y0, x1, y1 = [int(v * 1e6) for v in edge]
        for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1),
                                 (x1, y1, x0, y1), (x0, y1, x0, y0)):
            s = pcbnew.PCB_SHAPE(b)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(pcbnew.VECTOR2I(ax, ay))
            s.SetEnd(pcbnew.VECTOR2I(bx, by))
            s.SetLayer(pcbnew.Edge_Cuts)
            b.Add(s)
    return b


class TestLastmile(unittest.TestCase):
    def setUp(self):
        try:
            import pcbnew                          # noqa: F401
        except ImportError:
            self.skipTest("pcbnew not available (container-only test)")

    def test_short_gap_closes_straight(self):
        import cec_fr
        b = _board([(5, 5, "/A"), (7, 5, "/A")])
        r = cec_fr.synthesize_lastmile(b)
        self.assertEqual(r["closed"], 1)
        self.assertGreaterEqual(r["legs"], 1)
        segs = [t for t in b.GetTracks() if t.GetClass() != "PCB_VIA"]
        self.assertTrue(segs, "a closure must lay real copper")

    def test_arbitrary_offset_uses_only_canonical_angles(self):
        import cec_fr
        b = _board([(5, 5, "/A"), (8, 7, "/A")])
        r = cec_fr.synthesize_lastmile(b)
        self.assertEqual(r["closed"], 1)
        segs = [t for t in b.GetTracks() if t.GetClass() != "PCB_VIA"]
        self.assertGreaterEqual(len(segs), 2)
        for track in segs:
            dx = track.GetEnd().x - track.GetStart().x
            dy = track.GetEnd().y - track.GetStart().y
            angle = abs(math.degrees(math.atan2(dy, dx))) % 90.0
            self.assertLess(min(angle, abs(45.0 - angle), abs(90.0 - angle)),
                            1e-6, "last-mile copper must be 0/45/90 degrees")

    def test_canonical_path_helper_covers_octants(self):
        import cec_fr
        for end in ((3, 2), (-3, 2), (2, -3), (-2, -3), (3, 3), (0, 3)):
            with self.subTest(end=end):
                paths = cec_fr._canonical_45_xy_paths((0, 0), end)
                self.assertTrue(paths)
                for path in paths:
                    self.assertEqual(path[0], (0, 0))
                    self.assertEqual(path[-1], end)
                    for (ax, ay), (bx, by) in zip(path, path[1:]):
                        dx, dy = abs(bx - ax), abs(by - ay)
                        self.assertTrue(dx == 0 or dy == 0 or dx == dy,
                                        "every candidate leg must be octilinear")

    def test_far_gap_untouched(self):
        import cec_fr
        b = _board([(5, 5, "/A"), (25, 5, "/A")])
        r = cec_fr.synthesize_lastmile(b)
        self.assertEqual(r["closed"], 0)
        self.assertGreaterEqual(r["far"], 1)
        self.assertFalse(list(b.GetTracks()))

    def test_blocked_straight_takes_bridge_or_L(self):
        # a foreign pad dead-center between the pair blocks the straight; the
        # completer must still close (L around it, or the over-the-top bridge)
        import cec_fr
        b = _board([(5, 5, "/A"), (9, 5, "/A"), (7, 5, "/BLOCK")])
        r = cec_fr.synthesize_lastmile(b)
        self.assertEqual(r["closed"], 1,
                         "blocked straight must fall through to L/bridge")

    def test_edge_hugging_gap_refused(self):
        # pads 0.3mm from the outline: any leg would violate the 0.5 edge rule
        import cec_fr
        b = _board([(1.0, 0.3, "/A"), (3.0, 0.3, "/A")],
                   edge=(0, 0, 20, 10))
        r = cec_fr.synthesize_lastmile(b)
        self.assertEqual(r["closed"], 0,
                         "edge-hugging closure must be refused (the +4 "
                         "copper_edge regression class)")

    def test_internal_edge_cutout_is_not_crossed(self):
        import pcbnew
        import cec_fr

        b = _board([(5, 5, "/A"), (9, 5, "/A")],
                   edge=(0, 0, 20, 10))
        fp = pcbnew.FOOTPRINT(b)
        fp.SetReference("DL1")
        cut = pcbnew.PCB_SHAPE(fp)
        cut.SetShape(pcbnew.SHAPE_T_RECT)
        cut.SetStart(pcbnew.VECTOR2I_MM(6.0, 4.0))
        cut.SetEnd(pcbnew.VECTOR2I_MM(8.0, 6.0))
        cut.SetLayer(pcbnew.Edge_Cuts)
        fp.Add(cut)
        b.Add(fp)
        with mock.patch.object(cec_fr, "_lastmile_bridge", return_value=None):
            result = cec_fr.synthesize_lastmile(b)
        self.assertEqual(result["closed"], 0,
                         "post-route last-mile must honor reverse-LED holes")

    def test_bridge_uses_final_netclass_via_geometry(self):
        """A bridge seat must be judged at the size it will ship, not at the
        smaller router default that normalize_netclass_geometry later grows."""
        import pcbnew
        import cec_fr

        b = _board([(5, 5, "/POWER"), (7, 5, "/POWER")])
        pads = [p for fp in b.GetFootprints() for p in fp.Pads()]
        back = pcbnew.LSET()
        back.AddLayer(pcbnew.B_Cu)
        pads[1].SetLayerSet(back)  # no common layer: force over-the-top bridge

        with mock.patch.object(cec_fr, "_lastmile_bridge", return_value=None) as bridge:
            cec_fr.synthesize_lastmile(
                b, netclass_resolver=lambda _net: {
                    "via_diameter": 0.8, "via_drill": 0.4})
        self.assertTrue(bridge.called)
        self.assertEqual(bridge.call_args.kwargs["dia"], 0.8)
        self.assertEqual(bridge.call_args.kwargs["drill"], 0.4)

    def test_wave_plumbing(self):
        import cec_fresh_wave as w
        self.assertTrue(w.BOARD_PARAMS["hub-standard-rev2"].get("lastmile"))
        import cec_synth_pipeline as csp
        with csp._oracle_env({"lastmile": True}):
            self.assertEqual(os.environ.get("CEC_LASTMILE"), "1")
        self.assertNotEqual(os.environ.get("CEC_LASTMILE"), "1")


if __name__ == "__main__":
    unittest.main()
