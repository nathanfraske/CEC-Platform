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


def _bypass_board():
    """Power bypass C1/U1 plus a Default-class signal RC C2/U2."""
    import pcbnew

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(6)
    nets = {}
    for name in ("GND", "/POWER", "/SENSE"):
        nets[name] = pcbnew.NETINFO_ITEM(board, name)
        board.Add(nets[name])
    front = pcbnew.LSET()
    front.AddLayer(pcbnew.F_Cu)

    def add(ref, pads):
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference(ref)
        for number, x, y, net in pads:
            pad = pcbnew.PAD(footprint)
            pad.SetPadName(str(number))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(0.4, 0.4))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x, y))
            pad.SetLayerSet(front)
            pad.SetNet(nets[net])
            footprint.Add(pad)
        board.Add(footprint)

    add("C1", ((1, 5, 5, "/POWER"), (2, 5, 6, "GND")))
    add("U1", ((1, 9, 5, "/POWER"),))
    add("C2", ((1, 5, 10, "/SENSE"), (2, 5, 11, "GND")))
    add("U2", ((1, 9, 10, "/SENSE"),))
    return board


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

    def test_profiled_path_neckdown_is_bounded_at_both_ends(self):
        import pcbnew
        import cec_fr

        points = [pcbnew.VECTOR2I_MM(0, 0), pcbnew.VECTOR2I_MM(4, 0)]
        legs = cec_fr._profiled_lastmile_path(
            points, int(1.0e6),
            start_escape=(int(0.25e6), int(1.5e6)),
            end_escape=(int(0.25e6), int(1.5e6)))
        self.assertEqual([width for _a, _b, width in legs],
                         [int(0.25e6), int(1.0e6), int(0.25e6)])
        self.assertEqual(legs[0][0], points[0])
        self.assertEqual(legs[-1][1], points[-1])

    def test_fine_pitch_power_gap_uses_local_neckdowns(self):
        """A class-width trunk must not make a physically routable SMD pin
        escape look blocked; only the <=1.5 mm endpoint prefixes may narrow."""
        import pcbnew
        import cec_fr

        b = _board([(5, 5, "/POWER"), (7, 5, "/POWER"),
                    (6, 5.9, "/BLOCK")])
        power_pads = [p for fp in b.GetFootprints() for p in fp.Pads()
                      if p.GetNetname() == "/POWER"]
        for pad in power_pads:
            pad.SetSize(pcbnew.VECTOR2I_MM(0.4, 0.4))
        b.BuildConnectivity()

        with mock.patch.object(cec_fr, "_lastmile_bridge", return_value=None):
            result = cec_fr.synthesize_lastmile(
                b, netclass_resolver=lambda net: {
                    "track_width": 1.0 if net == "/POWER" else 0.25})
        self.assertEqual(result["closed"], 1)
        power_tracks = [t for t in b.GetTracks()
                        if t.GetNetname() == "/POWER"]
        self.assertTrue(power_tracks)
        self.assertLessEqual(max(t.GetWidth() for t in power_tracks),
                             int(0.25e6))

    def test_cloned_same_net_pad_uuids_do_not_collapse_clusters(self):
        import pcbnew
        import cec_fr

        b = pcbnew.BOARD()
        b.SetCopperLayerCount(4)
        net = pcbnew.NETINFO_ITEM(b, "/A")
        b.Add(net)
        first = pcbnew.FOOTPRINT(b)
        first.SetReference("U1")
        first.SetPosition(pcbnew.VECTOR2I_MM(5.0, 5.0))
        pad = pcbnew.PAD(first)
        pad.SetPadName("1")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
        pad.SetPosition(first.GetPosition())
        front = pcbnew.LSET()
        front.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(front)
        pad.SetNet(net)
        first.Add(pad)
        b.Add(first)

        # The copy constructor preserves the child UUID, reproducing the Hub
        # reference's cloned-footprint defect on two pads of the same net.
        second = pcbnew.FOOTPRINT(first)
        second.SetReference("U2")
        second.SetPosition(pcbnew.VECTOR2I_MM(7.0, 5.0))
        b.Add(second)
        pads = [p for fp in b.GetFootprints() for p in fp.Pads()]
        self.assertEqual(pads[0].m_Uuid.AsString(), pads[1].m_Uuid.AsString())

        b.BuildConnectivity()
        result = cec_fr.synthesize_lastmile(b)
        self.assertEqual(result["closed"], 1)
        self.assertTrue(list(b.GetTracks()))

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

    def test_blocked_straight_takes_guarded_same_layer_detour(self):
        import cec_fr

        b = _board([(5, 5, "/A"), (9, 5, "/A"), (7, 5, "/BLOCK")])
        with mock.patch.object(cec_fr, "_lastmile_bridge", return_value=None):
            result = cec_fr.synthesize_lastmile(b)
        self.assertEqual(result["closed"], 1)
        tracks = [t for t in b.GetTracks() if t.GetNetname() == "/A"]
        self.assertGreaterEqual(len(tracks), 3,
                                "the closure should route around the blocker")
        self.assertTrue(any(t.GetStart().y != t.GetEnd().y for t in tracks))

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
        self.assertEqual(result["closed"], 1,
                         "a guarded dogleg may route around the LED hole")
        tracks = [t for t in b.GetTracks() if t.GetNetname() == "/A"]
        self.assertTrue(tracks)
        self.assertTrue(all(
            cec_fr._edge_leg_clear(b, t.GetStart(), t.GetEnd(),
                                   t.GetWidth() // 2)
            for t in tracks),
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

    def test_local_power_bypass_links_only_power_class_and_locks(self):
        import cec_fr

        board = _bypass_board()
        resolve = lambda net: {  # noqa: E731 - compact test resolver
            "name": "Power" if net == "/POWER" else "Default",
            "track_width": 1.0 if net == "/POWER" else 0.25,
            "clearance": 0.25,
        }
        result = cec_fr.synthesize_local_power_bypass_links(
            board, netclass_resolver=resolve)

        self.assertEqual((result["pairs"], result["linked"],
                          result["refused"]), (1, 1, 0))
        power = [track for track in board.GetTracks()
                 if track.GetNetname() == "/POWER"]
        signal = [track for track in board.GetTracks()
                  if track.GetNetname() == "/SENSE"]
        self.assertTrue(power)
        self.assertFalse(signal, "Default-class signal RC capacitors are not "
                                 "pre-routed as power bypasses")
        self.assertTrue(all(track.IsLocked() for track in power))
        self.assertIn(int(1.0e6), {track.GetWidth() for track in power},
                      "the middle of a 4 mm power link keeps class width")
        self.assertIn(int(0.2e6), {track.GetWidth() for track in power},
                      "fine SMD endpoints use bounded neck-downs")

    def test_local_power_bypass_is_idempotent(self):
        import cec_fr

        board = _bypass_board()
        resolve = lambda net: {  # noqa: E731 - compact test resolver
            "track_width": 1.0 if net == "/POWER" else 0.25,
            "clearance": 0.25,
        }
        first = cec_fr.synthesize_local_power_bypass_links(
            board, netclass_resolver=resolve)
        count = len(list(board.GetTracks()))
        second = cec_fr.synthesize_local_power_bypass_links(
            board, netclass_resolver=resolve)

        self.assertEqual(first["linked"], 1)
        self.assertEqual(second["linked"], 0)
        self.assertEqual(len(list(board.GetTracks())), count)
        self.assertEqual(second["detail"][0]["status"], "already-connected")

    def test_local_signal_links_only_private_low_fanout_ic_network(self):
        import cec_fr

        board = _bypass_board()
        resolve = lambda net: {  # noqa: E731 - compact test resolver
            "track_width": 1.0 if net == "/POWER" else 0.20,
            "clearance": 0.20,
        }
        result = cec_fr.synthesize_local_signal_links(
            board, netclass_resolver=resolve)

        self.assertEqual((result["networks"], result["linked"],
                          result["refused"]), (1, 1, 0))
        signal = [track for track in board.GetTracks()
                  if track.GetNetname() == "/SENSE"]
        power = [track for track in board.GetTracks()
                 if track.GetNetname() == "/POWER"]
        self.assertTrue(signal)
        self.assertFalse(power, "distributed/power-width nets remain the "
                         "global router's responsibility")
        self.assertTrue(all(track.IsLocked() for track in signal))

    def test_local_signal_uses_guarded_bridge_when_face_escape_is_blocked(self):
        import pcbnew
        import cec_fr

        board = _bypass_board()
        resolve = lambda net: {  # noqa: E731 - compact test resolver
            "track_width": 1.0 if net == "/POWER" else 0.20,
            "clearance": 0.20,
            "via_diameter": 0.60, "via_drill": 0.30,
        }
        # Model a dense surface channel that has no guarded F.Cu route.  The
        # same collision-aware over-the-top primitive used by last-mile must
        # be tried before refusing a private local control net.
        guarded = cec_fr._guarded_profiled_lastmile_legs

        def block_long_face_route(board_, start, end, width, layer, *args,
                                  **kwargs):
            if (layer == pcbnew.F_Cu
                    and math.hypot(end.x - start.x, end.y - start.y)
                    > int(3.0e6)):
                return None
            return guarded(board_, start, end, width, layer, *args, **kwargs)

        with mock.patch.object(cec_fr, "_guarded_profiled_lastmile_legs",
                               side_effect=block_long_face_route):
            result = cec_fr.synthesize_local_signal_links(
                board, netclass_resolver=resolve)

        self.assertEqual((result["networks"], result["linked"],
                          result["refused"]), (1, 1, 0))
        self.assertEqual(result["vias"], 2)
        signal = [item for item in board.GetTracks()
                  if item.GetNetname() == "/SENSE"]
        self.assertTrue(any(item.GetClass() == "PCB_VIA" for item in signal))
        self.assertTrue(any(item.GetClass() != "PCB_VIA"
                            and item.GetLayer() != pcbnew.F_Cu
                            for item in signal))
        self.assertTrue(all(item.IsLocked() for item in signal))

    def test_layer_junction_via_heals_roundtrip_but_skips_tht(self):
        import pcbnew
        import cec_fr

        def fixture(with_pth=False):
            board = pcbnew.BOARD()
            board.SetCopperLayerCount(6)
            net = pcbnew.NETINFO_ITEM(board, "/PWR")
            board.Add(net)
            p0 = pcbnew.VECTOR2I_MM(5.0, 5.0)
            # Reproduce SES decimal round-trip drift: endpoints differ by
            # 0.00005 mm but are visually the same layer transition.
            for layer, end in ((pcbnew.F_Cu, pcbnew.VECTOR2I_MM(7.0, 5.0)),
                               (pcbnew.In2_Cu,
                                pcbnew.VECTOR2I_MM(7.00005, 5.00005))):
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(p0 if layer == pcbnew.F_Cu else end)
                track.SetEnd(end if layer == pcbnew.F_Cu
                             else pcbnew.VECTOR2I_MM(9.0, 5.0))
                track.SetWidth(pcbnew.FromMM(0.5))
                track.SetLayer(layer)
                track.SetNet(net)
                board.Add(track)
            if with_pth:
                fp = pcbnew.FOOTPRINT(board)
                fp.SetReference("J1")
                pad = pcbnew.PAD(fp)
                pad.SetPadName("1")
                pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
                pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
                pad.SetSize(pcbnew.VECTOR2I_MM(1.2, 1.2))
                pad.SetDrillSize(pcbnew.VECTOR2I_MM(0.6, 0.6))
                pad.SetPosition(pcbnew.VECTOR2I_MM(7.0, 5.0))
                pad.SetLayerSet(pcbnew.PAD.PTHMask())
                pad.SetNet(net)
                fp.Add(pad)
                board.Add(fp)
            return board

        resolve = lambda _net: {"via_diameter": 0.8, "via_drill": 0.4,
                                "clearance": 0.2}
        board = fixture()
        repaired = cec_fr.synthesize_missing_layer_junction_vias(
            board, netclass_resolver=resolve)
        self.assertEqual((repaired["candidates"], repaired["added"],
                          repaired["refused"]), (1, 1, 0))
        self.assertEqual(len([item for item in board.GetTracks()
                              if item.GetClass() == "PCB_VIA"]), 1)

        tht_board = fixture(with_pth=True)
        skipped = cec_fr.synthesize_missing_layer_junction_vias(
            tht_board, netclass_resolver=resolve)
        self.assertEqual((skipped["candidates"], skipped["added"]), (0, 0))

    def test_maze_shape_snapshot_matches_authoritative_foreign_guard(self):
        import pcbnew
        import cec_fr

        board = _board([(5, 5, "/A"), (7, 5, "/A"),
                        (6, 5, "/BLOCK")])
        start = pcbnew.VECTOR2I_MM(5.0, 5.0)
        blocked = pcbnew.VECTOR2I_MM(7.0, 5.0)
        clear = pcbnew.VECTOR2I_MM(5.0, 7.0)
        code = board.GetNetcodeFromNetname("/A")
        zones, copper = cec_fr._layer_foreign_shapes(
            board, pcbnew.F_Cu, {code})
        for end in (blocked, clear):
            with self.subTest(end=(end.x, end.y)):
                expected = cec_fr._tap_foreign_clear(
                    board, start, end, int(0.2e6), pcbnew.F_Cu,
                    int(0.2e6), {code})
                actual = cec_fr._snapshot_foreign_clear(
                    start, end, int(0.2e6), int(0.2e6), zones, copper)
                self.assertEqual(actual, expected)

    def test_wave_plumbing(self):
        import cec_fresh_wave as w
        self.assertTrue(w.BOARD_PARAMS["hub-standard-rev2"].get("lastmile"))
        import cec_synth_pipeline as csp
        with csp._oracle_env({"lastmile": True}):
            self.assertEqual(os.environ.get("CEC_LASTMILE"), "1")
        self.assertNotEqual(os.environ.get("CEC_LASTMILE"), "1")


if __name__ == "__main__":
    unittest.main()
