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
import cec_synth_pipeline as synth
from dataclasses import replace


class CriticalRouteContractTests(unittest.TestCase):
    def test_power_resume_contract_survives_candidate_copy_and_rejects_detour(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "board.kicad_pcb")
            self._board(path)
            board = pcbnew.LoadBoard(path)
            trunk = next(t for t in board.GetTracks() if t.GetNetname() == "/GPIO")
            trunk.SetWidth(pcbnew.FromMM(2.0))
            pcbnew.SaveBoard(path, board)
            nets = cec_fr.locked_pour_authority_nets_board(
                board, include_complete_nets=False)
            self.assertEqual(nets, {"/GPIO"})  # geometry, not a power-name selector
            candidate = synth.Candidate("test", 0, {}, 30, 30, 0, {})
            candidate.protected_power_prefix = cec_fr.copper_geometry_prefix_contract(path, nets)
            copied = replace(candidate, P={"ARBITRARY": (1, 2, 0)})
            self.assertEqual(copied.protected_power_prefix, candidate.protected_power_prefix)
            self.assertTrue(synth._admit_materialized_power_prefix(copied, path)["ok"])
            trunk.SetStart(pcbnew.VECTOR2I_MM(10, 13))
            trunk.SetEnd(pcbnew.VECTOR2I_MM(20, 13))  # same count, width and length
            pcbnew.SaveBoard(path, board)
            # This guard also checks retained qualified pairs now. The copper
            # loss must still fail even though the shared diagnostic names both.
            with self.assertRaisesRegex(ValueError, "protected power copper.*changed"):
                synth._admit_materialized_power_prefix(copied, path)

    def test_ordinary_narrow_local_links_do_not_freeze_a_shared_rail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "board.kicad_pcb")
            self._board(path)
            board = pcbnew.LoadBoard(path)
            self.assertEqual(cec_fr.locked_pour_authority_nets_board(
                board, include_complete_nets=False), set())

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
