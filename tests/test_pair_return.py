import os
import sys
import unittest
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

try:
    import pcbnew
    import cec_pair_return as pair_return
    HAVE_PCBNEW = True
except ImportError:
    HAVE_PCBNEW = False


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required")
class PairReturnTests(unittest.TestCase):
    def _board(self, n_vias=1):
        board = pcbnew.BOARD()
        nets = {}
        for name in ("GND", "/USB_D_P", "/USB_D_N"):
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
            nets[name] = net
        for a, b in (((0, 0), (20, 0)), ((20, 0), (20, 20)),
                     ((20, 20), (0, 20)), ((0, 20), (0, 0))):
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I_MM(*a))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*b))
            edge.SetLayer(pcbnew.Edge_Cuts)
            board.Add(edge)

        def via(name, x, y):
            item = pcbnew.PCB_VIA(board)
            item.SetPosition(pcbnew.VECTOR2I_MM(x, y))
            item.SetDrill(pcbnew.FromMM(0.3))
            item.SetWidth(pcbnew.FromMM(0.6))
            item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            item.SetNet(nets[name])
            board.Add(item)
            return item

        for index in range(n_vias):
            via("/USB_D_P", 8.0 + index * 4.0, 10.0)
            via("/USB_D_N", 8.5 + index * 4.0, 10.0)
        via("GND", 8.25, 11.0)
        return board

    def test_matched_transition_with_nearby_return_is_admitted(self):
        board = self._board()
        pairs = [{"name": "USB_D", "p": "/USB_D_P", "n": "/USB_D_N",
                  "kind": "usb", "width": 0.2, "gap": 0.13}]
        with mock.patch.object(
                pair_return.cec_precision_route, "derive_coupled_pairs",
                return_value=pairs):
            report = pair_return.synthesize_board(board)
        self.assertTrue(report["ok"])
        self.assertEqual(report["added"], 0)
        self.assertEqual(
            report["pairs"][0]["transitions"][0]["status"], "covered")

    def test_asymmetric_signal_transition_refuses(self):
        board = self._board()
        # Remove only the N member.
        n_via = next(item for item in board.GetTracks()
                     if item.GetClass() == "PCB_VIA"
                     and item.GetNetname() == "/USB_D_N")
        board.Remove(n_via)
        pairs = [{"name": "USB_D", "p": "/USB_D_P", "n": "/USB_D_N",
                  "kind": "usb", "width": 0.2, "gap": 0.13}]
        with mock.patch.object(
                pair_return.cec_precision_route, "derive_coupled_pairs",
                return_value=pairs):
            report = pair_return.synthesize_board(board)
        self.assertFalse(report["ok"])
        self.assertIn("asymmetric", report["pairs"][0]["refused"])

    def test_overwide_transition_is_repaired_as_a_paired_neck(self):
        board = self._board()
        n_via = next(item for item in board.GetTracks()
                     if item.GetClass() == "PCB_VIA"
                     and item.GetNetname() == "/USB_D_N")
        n_via.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))
        pairs = [{"name": "USB_D", "p": "/USB_D_P", "n": "/USB_D_N",
                  "kind": "usb", "width": 0.2, "gap": 0.13}]
        with mock.patch.object(
                pair_return.cec_precision_route, "derive_coupled_pairs",
                return_value=pairs):
            report = pair_return.synthesize_board(board)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["signal_realignments"], 1)
        transition = report["pairs"][0]["transitions"][0]
        self.assertLessEqual(transition["pair_spacing_mm"], 1.5)

    def test_target_search_prefers_least_geometry_movement_that_passes(self):
        failed = {
            "schema": 1, "ok": False, "error": "DRC regression",
            "admission": {"regression": True},
        }
        passed = {
            "schema": 1, "ok": True,
            "admission": {"regression": False},
        }
        with mock.patch.object(
                pair_return, "_synthesize_once",
                side_effect=[failed, failed, passed]) as run:
            report = pair_return.synthesize(
                "input.kicad_pcb", "output.kicad_pcb",
                max_pair_spacing_mm=1.5,
                target_pair_spacing_mm=1.2)
        self.assertTrue(report["ok"])
        self.assertEqual(
            [call.kwargs["target_pair_spacing_mm"]
             for call in run.call_args_list],
            [1.45, 1.4, 1.35])
        self.assertEqual(
            report["target_search"]["selected_target_pair_spacing_mm"],
            1.35)


if __name__ == "__main__":
    unittest.main()
