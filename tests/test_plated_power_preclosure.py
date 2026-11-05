"""Plated local power pins use existing connectivity, not extra via guesses."""
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_fr
import cec_staged_fr


class PlatedPreclosureTests(unittest.TestCase):
    def board(self, *, vertical=False, plated=True):
        board = pcbnew.BOARD()
        board.SetCopperLayerCount(6)
        net = pcbnew.NETINFO_ITEM(board, "anonymous-power")
        board.Add(net)
        for a, b in [((0, 0), (20, 0)), ((20, 0), (20, 20)),
                     ((20, 20), (0, 20)), ((0, 20), (0, 0))]:
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetLayer(pcbnew.Edge_Cuts)
            edge.SetStart(pcbnew.VECTOR2I_MM(*a))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
            board.Add(edge)
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference("BANK")
        pads = []
        for index in range(3):
            pad = pcbnew.PAD(fp)
            pad.SetNumber(str(index + 1))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH if plated else pcbnew.PAD_ATTRIB_NPTH)
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I_MM(1.6, 1.6))
            pad.SetDrillSize(pcbnew.VECTOR2I_MM(0.8, 0.8))
            pad.SetPosition(pcbnew.VECTOR2I_MM(5 if vertical else 5 + index * 2.54,
                                              5 + index * 2.54 if vertical else 5))
            pad.SetLayerSet(pcbnew.LSET.AllCuMask())
            pad.SetNet(net)
            fp.Add(pad)
            pads.append(pad)
        board.Add(fp)
        return board, pads

    def run_links(self, board, **kwargs):
        return cec_fr.synthesize_same_footprint_links(
            board, include_nets={"anonymous-power"}, include_plated_through=True,
            netclass_resolver=lambda _: {"track_width": 0.3, "clearance": 0.2},
            prefer_connector_bridge=False, allow_maze=False, **kwargs)

    def test_new_local_connections_are_octilinear_without_added_vias(self):
        for vertical in (False, True):
            with self.subTest(vertical=vertical):
                board, _ = self.board(vertical=vertical)
                result = self.run_links(board)
                self.assertEqual(result["linked"], 2, result)
                self.assertEqual(result["refused"], 0, result)
                tracks = list(board.GetTracks())
                self.assertTrue(tracks)
                self.assertTrue(all(t.GetClass() == "PCB_TRACK" for t in tracks))
                self.assertTrue(all(t.GetWidth() >= pcbnew.FromMM(0.3) for t in tracks))
                for item in tracks:
                    delta = item.GetEnd() - item.GetStart()
                    self.assertTrue(delta.x == 0 or delta.y == 0 or abs(delta.x) == abs(delta.y))
                self.assertEqual(cec_staged_fr.fully_connected_nets(board, {"anonymous-power"})[0],
                                 {"anonymous-power"})
                self.assertEqual(self.run_links(board)["linked"], 0)

    def test_existing_back_layer_connection_needs_no_extra_tracks_or_vias(self):
        board, pads = self.board()
        for start, end in zip(pads, pads[1:]):
            track = pcbnew.PCB_TRACK(board)
            track.SetNet(start.GetNet())
            track.SetStart(start.GetPosition())
            track.SetEnd(end.GetPosition())
            track.SetWidth(pcbnew.FromMM(0.3))
            track.SetLayer(pcbnew.B_Cu)
            board.Add(track)
        ids = {t.m_Uuid.AsString() for t in board.GetTracks()}
        self.assertEqual(self.run_links(board)["linked"], 0)
        self.assertEqual({t.m_Uuid.AsString() for t in board.GetTracks()}, ids)

    def test_route_layer_policy_is_respected(self):
        board, _ = self.board()
        with mock.patch.object(cec_fr, "_lastmile_route_layers", return_value=[pcbnew.B_Cu]):
            result = self.run_links(board)
        self.assertEqual(result["linked"], 2)
        self.assertTrue(all(t.GetLayer() == pcbnew.B_Cu for t in board.GetTracks()))

    def test_npth_and_implicit_scope_are_excluded(self):
        board, _ = self.board(plated=False)
        self.assertEqual(self.run_links(board)["linked"], 0)
        self.assertFalse(list(board.GetTracks()))
        board, _ = self.board()
        self.assertEqual(cec_fr.synthesize_same_footprint_links(board)["linked"], 0)
        with self.assertRaisesRegex(ValueError, "explicit net scope"):
            cec_fr.synthesize_same_footprint_links(board, include_plated_through=True)
        self.assertFalse(list(board.GetTracks()))


if __name__ == "__main__":
    unittest.main()
