#!/usr/bin/env python3
"""Physical aggressor/victim interaction and shielding regressions."""

import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest("KiCad pcbnew required") from exc

import cec_field_coupling as field  # noqa: E402
import cec_pcb  # noqa: E402


class FieldCouplingTest(unittest.TestCase):
    def test_future_high_speed_names_and_netclasses_are_design_intent(self):
        self.assertTrue(field.classify_net("/SERDES_TX0")["aggressor"])
        neutral = field.classify_net("/DATA0")
        self.assertFalse(neutral["aggressor"])
        classified = field.classify_net("/DATA0", netclass="DDR HighSpeed")
        self.assertTrue(classified["aggressor"])
        self.assertTrue(classified["victim"])
        self.assertIn("fast-netclass:DDR HIGHSPEED", classified["reasons"])

    def _board(self, directory, rows):
        netlist = os.path.join(directory, "field.net")
        path = os.path.join(directory, "field.kicad_pcb")
        with open(netlist, "w", encoding="utf-8") as handle:
            handle.write('(export (nets (net (code "1") (name "GND"))))\n')
        self.assertTrue(cec_pcb.build_board(
            path, netlist, {}, [(5.0, 5.0)], None, 30.0, 20.0,
            force_argv=False, stackup_profile="jlcpcb_6l_pofv_signal"))
        board = pcbnew.LoadBoard(path)
        nets = {}
        for name, _layer, _start, _end in rows:
            if name in nets:
                continue
            net = pcbnew.NETINFO_ITEM(board, name)
            board.Add(net)
            nets[name] = net
        for name, layer, start, end in rows:
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I_MM(*start))
            track.SetEnd(pcbnew.VECTOR2I_MM(*end))
            track.SetWidth(pcbnew.FromMM(0.20))
            track.SetLayer(board.GetLayerID(layer))
            track.SetNet(nets[name])
            board.Add(track)
        pcbnew.SaveBoard(path, board)
        board = pcbnew.LoadBoard(path)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(path, board)
        return path

    def test_same_layer_parallel_switch_and_sense_are_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ("/BUCK/U3_SW", "F.Cu", (4.0, 8.0), (20.0, 8.0)),
                ("/ADC/VOUT_SENSE", "F.Cu", (4.0, 8.6), (20.0, 8.6)),
            ])
            report = field.field_coupling_summary(path)

        self.assertFalse(report["ok"], report)
        self.assertEqual(report["blocking_count"], 1)
        self.assertIn("unshielded parallel", report["violations"][0])

    def test_filled_ground_between_layers_is_real_shield_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ("/BUCK/U3_SW", "F.Cu", (4.0, 8.0), (20.0, 8.0)),
                ("/ADC/VOUT_SENSE", "In2.Cu", (4.0, 8.2), (20.0, 8.2)),
            ])
            report = field.field_coupling_summary(path)

        self.assertTrue(report["ok"], report)
        row = report["interactions"][0]
        self.assertTrue(row["shield"]["shielded"])
        self.assertEqual(row["shield"]["selected_layer"], "In1.Cu")
        self.assertGreaterEqual(row["shield"]["coverage_pct"], 95.0)

    def test_unshielded_adjacent_layers_accept_perpendicular_crossing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ("/BUCK/U3_SW", "In2.Cu", (4.0, 8.0), (20.0, 8.0)),
                ("/ADC/VOUT_SENSE", "In3.Cu", (12.0, 3.0), (12.0, 14.0)),
            ])
            report = field.field_coupling_summary(path)

        self.assertTrue(report["ok"], report)
        self.assertAlmostEqual(report["interactions"][0]["angle_deg"], 90.0)
        self.assertFalse(report["interactions"][0]["shield"]["shielded"])

    def test_unshielded_adjacent_layer_oblique_crossing_is_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ("/BUCK/U3_SW", "In2.Cu", (4.0, 8.0), (20.0, 8.0)),
                ("/ADC/VOUT_SENSE", "In3.Cu", (8.0, 4.0), (16.0, 12.0)),
            ])
            report = field.field_coupling_summary(path)

        self.assertFalse(report["ok"], report)
        self.assertIn("not approximately perpendicular",
                      report["violations"][0])

    def test_intended_differential_pair_members_are_not_mutual_faults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ("/USB_D_P", "F.Cu", (4.0, 8.0), (20.0, 8.0)),
                ("/USB_D_N", "F.Cu", (4.0, 8.33), (20.0, 8.33)),
            ])
            report = field.field_coupling_summary(path)

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["interaction_count"], 0)


if __name__ == "__main__":
    unittest.main()
