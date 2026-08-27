#!/usr/bin/env python3
"""Regression tests for edge-only global assembly fiducials."""

import json
import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


class TestFiducialEdgePolicy(unittest.TestCase):
    def setUp(self):
        try:
            import pcbnew  # noqa: F401
        except ImportError:
            self.skipTest("pcbnew not available")

    @staticmethod
    def _board():
        import pcbnew

        board = pcbnew.CreateEmptyBoard()
        for ax, ay, bx, by in (
                (0, 0, 50, 0), (50, 0, 50, 50),
                (50, 50, 0, 50), (0, 50, 0, 0)):
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I_MM(ax, ay))
            edge.SetEnd(pcbnew.VECTOR2I_MM(bx, by))
            edge.SetLayer(pcbnew.Edge_Cuts)
            board.Add(edge)
        for ref, x, y in (("FID1", 5, 5), ("FID2", 5, 45),
                          ("FID3", 25, 25)):
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference(ref)
            footprint.SetPosition(pcbnew.VECTOR2I_MM(x, y))
            board.Add(footprint)
        return board

    def test_interior_fiducial_is_reseated_on_peripheral_band(self):
        import pcbnew
        import cec_synth_pipeline as synth

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "fids.kicad_pcb")
            pcbnew.SaveBoard(path, self._board())
            state_path = path[:-len(".kicad_pcb")] + ".pourfirst-state.json"
            with open(state_path, "w", encoding="utf-8") as sink:
                json.dump({
                    "placement_scope": "complete",
                    "placements": {
                        "FID1": [5, 5, 0], "FID2": [5, 45, 0],
                        "FID3": [25, 25, 0],
                    },
                }, sink)
            before = synth._oracle_fiducials(path, expect=True)
            self.assertFalse(before["ok"])
            self.assertTrue(any(row[0] == "interior"
                                for row in before["violations"]))

            repair = synth.repair_fiducials_to_edge_band(path)
            after = synth._oracle_fiducials(path, expect=True)
            saved = pcbnew.LoadBoard(path)
            with open(state_path, encoding="utf-8") as source:
                state = json.load(source)

        self.assertTrue(repair["ok"], repair)
        self.assertEqual([row["ref"] for row in repair["moved"]], ["FID3"])
        self.assertTrue(repair["pourfirst_state_sync"]["updated"])
        self.assertEqual(state["placements"]["FID3"][:2],
                         repair["moved"][0]["to_mm"])
        self.assertTrue(after["ok"], after)
        bounds = saved.GetBoardEdgesBoundingBox()
        left, top = bounds.GetLeft() / 1e6, bounds.GetTop() / 1e6
        right, bottom = bounds.GetRight() / 1e6, bounds.GetBottom() / 1e6
        for footprint in saved.GetFootprints():
            point = footprint.GetPosition()
            distance = min(point.x / 1e6 - left, right - point.x / 1e6,
                           point.y / 1e6 - top, bottom - point.y / 1e6)
            self.assertLessEqual(distance, 8.05)

    def test_mid_edge_fiducial_is_reseated_into_a_corner_sector(self):
        import pcbnew
        import cec_synth_pipeline as synth

        board = self._board()
        fid3 = next(fp for fp in board.GetFootprints()
                    if fp.GetReference() == "FID3")
        fid3.SetPosition(pcbnew.VECTOR2I_MM(25, 45))
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "mid-edge.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            repair = synth.repair_fiducials_to_edge_band(path)
            saved = pcbnew.LoadBoard(path)

        self.assertTrue(repair["ok"], repair)
        self.assertEqual([row["ref"] for row in repair["moved"]], ["FID3"])
        point = next(fp.GetPosition() for fp in saved.GetFootprints()
                     if fp.GetReference() == "FID3")
        x, y = point.x / 1e6, point.y / 1e6
        self.assertTrue((x <= 19.0 or x >= 31.0)
                        and (y <= 19.0 or y >= 31.0), (x, y))

    def test_replacement_reconsiders_legal_fiducials_away_from_route_demand(self):
        import pcbnew
        import cec_synth_pipeline as synth

        board = self._board()
        fid3 = next(fp for fp in board.GetFootprints()
                    if fp.GetReference() == "FID3")
        fid3.SetPosition(pcbnew.VECTOR2I_MM(45, 5))
        signal = pcbnew.NETINFO_ITEM(board, "/SIG")
        board.Add(signal)
        for index, x in enumerate((1.0, 22.0), start=1):
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference("J%d" % index)
            pad = pcbnew.PAD(footprint)
            pad.SetPadName("1")
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I_MM(0.5, 0.5))
            pad.SetPosition(pcbnew.VECTOR2I_MM(x, 5.0))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
            pad.SetNet(signal)
            footprint.Add(pad)
            board.Add(footprint)

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "movable-fids.kicad_pcb")
            pcbnew.SaveBoard(path, board)
            repair = synth.repair_fiducials_to_edge_band(
                path, reconsider_all=True)
            after = synth._oracle_fiducials(path, expect=True)

        self.assertTrue(repair["ok"], repair)
        self.assertTrue(repair["reconsider_all"])
        self.assertTrue(after["ok"], after)
        self.assertLessEqual(
            repair["route_pressure_after"]["conflicts"],
            repair["route_pressure_before"]["conflicts"])
        self.assertGreaterEqual(len(repair["corner_sectors"]), 3, repair)


if __name__ == "__main__":
    unittest.main()
