import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import pcbnew
import cec_fr


class CriticalRouteContractTests(unittest.TestCase):
    def _board(self, path):
        board = pcbnew.BOARD()
        owned = pcbnew.NETINFO_ITEM(board, "/USB_D_P")
        other = pcbnew.NETINFO_ITEM(board, "/GPIO")
        board.Add(owned)
        board.Add(other)
        for net, y in ((owned, 10.0), (other, 12.0)):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I_MM(10.0, y))
            track.SetEnd(pcbnew.VECTOR2I_MM(20.0, y))
            track.SetWidth(pcbnew.FromMM(0.20))
            track.SetLayer(pcbnew.F_Cu)
            track.SetNet(net)
            track.SetLocked(True)
            board.Add(track)
        pcbnew.SaveBoard(path, board)

    def test_signature_ignores_unselected_copper_but_detects_owned_change(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "board.kicad_pcb")
            self._board(path)
            first = cec_fr.copper_geometry_signature(path, ["/USB_D_P"])

            board = pcbnew.LoadBoard(path)
            gpio = next(track for track in board.GetTracks()
                        if track.GetNetname() == "/GPIO")
            gpio.SetEnd(pcbnew.VECTOR2I_MM(25.0, 12.0))
            pcbnew.SaveBoard(path, board)
            self.assertEqual(
                first["sha256"],
                cec_fr.copper_geometry_signature(path, ["/USB_D_P"])["sha256"])

            board = pcbnew.LoadBoard(path)
            usb = next(track for track in board.GetTracks()
                       if track.GetNetname() == "/USB_D_P")
            usb.SetEnd(pcbnew.VECTOR2I_MM(21.0, 10.0))
            pcbnew.SaveBoard(path, board)
            self.assertNotEqual(
                first["sha256"],
                cec_fr.copper_geometry_signature(path, ["/USB_D_P"])["sha256"])

    def test_partial_prefix_allows_extensions_but_not_locked_geometry_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "board.kicad_pcb")
            self._board(path)
            contract = cec_fr.copper_geometry_prefix_contract(
                path, ["/USB_D_P"])

            board = pcbnew.LoadBoard(path)
            net = board.FindNet("/USB_D_P")
            extra = pcbnew.PCB_TRACK(board)
            extra.SetStart(pcbnew.VECTOR2I_MM(20.0, 10.0))
            extra.SetEnd(pcbnew.VECTOR2I_MM(25.0, 10.0))
            extra.SetWidth(pcbnew.FromMM(0.20))
            extra.SetLayer(pcbnew.F_Cu)
            extra.SetNet(net)
            board.Add(extra)
            pcbnew.SaveBoard(path, board)
            self.assertTrue(
                cec_fr.check_copper_geometry_prefix(path, contract)["ok"])

            board = pcbnew.LoadBoard(path)
            locked = next(track for track in board.GetTracks()
                          if track.GetNetname() == "/USB_D_P"
                          and track.IsLocked())
            locked.SetEnd(pcbnew.VECTOR2I_MM(19.0, 10.0))
            pcbnew.SaveBoard(path, board)
            report = cec_fr.check_copper_geometry_prefix(path, contract)
            self.assertFalse(report["ok"], report)
            self.assertEqual(report["missing_by_net"], {"/USB_D_P": 1})


if __name__ == "__main__":
    unittest.main()
