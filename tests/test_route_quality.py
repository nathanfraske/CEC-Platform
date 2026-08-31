#!/usr/bin/env python3
"""Regression teeth for connected pseudo-stub route geometry."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

try:
    import pcbnew
    import cec_route_quality as quality
    import cec_staged_fr as staged
except ImportError:  # pragma: no cover - host without KiCad
    pcbnew = None
    quality = None
    staged = None


@unittest.skipIf(pcbnew is None, "pcbnew unavailable")
class RouteQualityTest(unittest.TestCase):
    def _board(self, points, *, duplicate_pad=False):
        board = pcbnew.BOARD()
        net = pcbnew.NETINFO_ITEM(board, "/USB_D_P", 1)
        board.Add(net)
        for start, end in zip(points, points[1:]):
            track = pcbnew.PCB_TRACK(board)
            track.SetNet(net)
            track.SetLayer(pcbnew.F_Cu)
            track.SetWidth(int(0.2e6))
            track.SetStart(pcbnew.VECTOR2I(
                int(start[0] * 1e6), int(start[1] * 1e6)))
            track.SetEnd(pcbnew.VECTOR2I(
                int(end[0] * 1e6), int(end[1] * 1e6)))
            board.Add(track)
        return board

    def test_cardinal_and_forty_five_degree_segments_pass_heading_policy(self):
        board = self._board([(0, 0), (2, 0), (3, 1), (3, 3)])
        report = quality.analyze_board(board)
        self.assertTrue(report["geometry_ok"])
        self.assertTrue(report["craft_ok"])
        self.assertEqual(report["non_octilinear_count"], 0)

    def test_raw_diagonal_is_named_and_refused(self):
        board = self._board([(0, 0), (2, 0.5)])
        track = next(iter(board.GetTracks()))
        track.SetLocked(True)
        report = quality.analyze_board(board)
        self.assertFalse(report["geometry_ok"])
        self.assertFalse(report["craft_ok"])
        self.assertEqual(report["non_octilinear_count"], 1)
        self.assertTrue(report["non_octilinear"][0]["locked"])
        self.assertEqual(report["non_octilinear"][0]["net"], "/USB_D_P")

    def test_curved_trace_requires_explicit_per_net_policy(self):
        board = pcbnew.BOARD()
        # Deliberately use a high-frequency-looking name: naming must never
        # silently waive the straight 0/45/90-degree copper policy.
        net = pcbnew.NETINFO_ITEM(board, "/PCIE_REFCLK_P", 1)
        board.Add(net)
        arc = pcbnew.PCB_ARC(board)
        arc.SetNet(net)
        arc.SetLayer(pcbnew.F_Cu)
        arc.SetWidth(int(0.2e6))
        arc.SetStart(pcbnew.VECTOR2I(0, 0))
        arc.SetMid(pcbnew.VECTOR2I(int(1.0e6), int(1.0e6)))
        arc.SetEnd(pcbnew.VECTOR2I(int(2.0e6), 0))
        board.Add(arc)

        refused = quality.analyze_board(board)
        admitted = quality.analyze_board(
            board, allow_curved_nets={"/PCIE_REFCLK_P"})

        self.assertFalse(refused["geometry_ok"])
        self.assertEqual(refused["curved_trace_count"], 1)
        self.assertFalse(
            refused["curved_traces"][0]["allowed_by_explicit_policy"])
        self.assertTrue(admitted["geometry_ok"])
        self.assertTrue(admitted["craft_ok"])
        self.assertTrue(
            admitted["curved_traces"][0]["allowed_by_explicit_policy"])

    def test_nanometre_quantization_does_not_create_a_false_angle(self):
        board = self._board([(0, 0), (0, 0.534)])
        track = next(iter(board.GetTracks()))
        track.SetEnd(pcbnew.VECTOR2I(25, 534000))
        report = quality.analyze_board(board)
        self.assertTrue(report["geometry_ok"])

    def test_heading_scope_checks_only_created_tracks(self):
        board = self._board([(0, 0), (2, 0.5)])
        track = next(iter(board.GetTracks()))
        ignored = quality.analyze_board(
            board, track_uuid_scope={"not-present"})
        checked = quality.analyze_board(
            board, track_uuid_scope={track.m_Uuid.AsString()})
        self.assertTrue(ignored["geometry_ok"])
        self.assertFalse(checked["geometry_ok"])

    def test_connected_135_degree_turn_is_blocking_on_critical_net(self):
        board = self._board([(0, 0), (2, 0), (1, 1)])
        report = quality.analyze_board(board, critical_nets={"/USB_D_P"})
        self.assertFalse(report["ok"])
        self.assertEqual(report["blocking_count"], 1)
        self.assertEqual(report["issues"][0]["type"], "acute_backtrack")
        self.assertAlmostEqual(report["issues"][0]["opening_angle_deg"], 45.0)

    def test_same_geometry_is_ranked_evidence_on_ordinary_net(self):
        board = self._board([(0, 0), (2, 0), (1, 1)])
        report = quality.analyze_board(board)
        self.assertTrue(report["ok"])
        self.assertTrue(report["geometry_ok"])
        self.assertFalse(report["craft_ok"])
        self.assertEqual(report["advisory_count"], 1)

    def test_normal_ninety_degree_corner_passes(self):
        board = self._board([(0, 0), (2, 0), (2, 2)])
        report = quality.analyze_board(board, critical_nets={"/USB_D_P"})
        self.assertTrue(report["ok"])
        self.assertEqual(report["issue_count"], 0)

    def test_covered_launch_is_blocking_even_when_junction_is_in_pad(self):
        board = self._board([(0, 0), (2, 0), (1, 0)])
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("J1")
        pad = pcbnew.PAD(footprint)
        pad.SetNumber("1")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 1.0))
        pad.SetPosition(pcbnew.VECTOR2I_MM(2.0, 0.0))
        pad.SetLayerSet(pad.SMDMask())
        pad.SetNet(board.FindNet("/USB_D_P"))
        footprint.Add(pad)
        board.Add(footprint)

        report = quality.analyze_board(
            board, critical_nets={"/USB_D_P"})

        self.assertFalse(report["ok"])
        self.assertEqual(report["issues"][0]["type"],
                         "covered_backtrack")

    def test_acute_fork_inside_same_net_pad_is_absorbed_by_pad_copper(self):
        board = self._board([(0, 0), (2, 0), (1, 1)])
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("RS1")
        pad = pcbnew.PAD(footprint)
        pad.SetNumber("2")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 1.0))
        pad.SetPosition(pcbnew.VECTOR2I_MM(2.0, 0.0))
        pad.SetLayerSet(pad.SMDMask())
        pad.SetNet(board.FindNet("/USB_D_P"))
        footprint.Add(pad)
        board.Add(footprint)

        report = quality.analyze_board(
            board, critical_nets={"/USB_D_P"})

        self.assertTrue(report["ok"])
        self.assertEqual(report["issue_count"], 0)

    def test_scope_ignores_preexisting_track_pair(self):
        board = self._board([(0, 0), (2, 0), (1, 1)])
        report = quality.analyze_board(
            board, critical_nets={"/USB_D_P"}, track_uuid_scope={"not-present"})
        self.assertTrue(report["ok"])
        self.assertEqual(report["issue_count"], 0)

    def test_staged_admission_drops_only_new_copper_on_bad_net(self):
        board = self._board([(0, 0), (2, 0), (1, 1)])
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "acute.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            report = staged._route_quality_stage_worker(
                path, ("/USB_D_P",), ())
            repaired = pcbnew.LoadBoard(path)

        self.assertEqual(report["refused_nets"], ["/USB_D_P"])
        self.assertEqual(report["removed_generated_items"], 2)
        self.assertEqual(len(list(repaired.GetTracks())), 0)

    def test_staged_admission_drops_generated_raw_diagonal(self):
        board = self._board([(0, 0), (2, 0.5)])
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "raw-diagonal.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            report = staged._route_quality_stage_worker(
                path, ("/USB_D_P",), ())
            repaired = pcbnew.LoadBoard(path)

        self.assertFalse(report["geometry_ok"])
        self.assertEqual(report["refused_nets"], ["/USB_D_P"])
        self.assertEqual(report["removed_generated_items"], 1)
        self.assertEqual(len(list(repaired.GetTracks())), 0)


if __name__ == "__main__":
    unittest.main()
