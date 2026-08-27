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


if __name__ == "__main__":
    unittest.main()
