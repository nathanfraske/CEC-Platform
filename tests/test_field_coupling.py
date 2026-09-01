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
        names = list(dict.fromkeys(
            ["GND"] + [row[0] for row in rows]))
        with open(netlist, "w", encoding="utf-8") as handle:
            handle.write("(export (nets\n")
            for code, name in enumerate(names, 1):
                handle.write(
                    '  (net (code "%d") (name "%s"))\n' % (code, name))
            handle.write("))\n")
        self.assertTrue(cec_pcb.build_board(
            path, netlist, {}, [(5.0, 5.0)], None, 30.0, 20.0,
            force_argv=False, stackup_profile="jlcpcb_6l_pofv_signal"))
        board = pcbnew.LoadBoard(path)
        nets = {name: board.FindNet(name) for name in names}
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

    def test_matched_pair_return_supports_only_the_signal_via_antipad(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ("/CAN_H", "F.Cu", (9.5, 8.0), (10.5, 8.0)),
                ("/CAN_L", "F.Cu", (2.0, 2.0), (2.1, 2.0)),
                ("/ADC/DETECT", "In2.Cu", (9.5, 8.2), (10.5, 8.2)),
                ("/ZZZ_DUMMY", "F.Cu", (2.0, 3.0), (2.1, 3.0)),
            ])
            board = pcbnew.LoadBoard(path)

            def add_via(net_name, x, y):
                via = pcbnew.PCB_VIA(board)
                via.SetViaType(pcbnew.VIATYPE_THROUGH)
                via.SetPosition(pcbnew.VECTOR2I_MM(x, y))
                via.SetWidth(pcbnew.FromMM(0.60))
                via.SetDrill(pcbnew.FromMM(0.30))
                via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                via.SetNetCode(board.GetNetcodeFromNetname(net_name))
                board.Add(via)
                return via

            add_via("/CAN_H", 10.0, 8.0)
            add_via("/CAN_L", 10.0, 8.8)
            for zone in board.Zones():
                zone.UnFill()
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            unsupported = field.field_coupling_summary(path, board=board)
            self.assertFalse(unsupported["ok"], unsupported)

            returned = pcbnew.PCB_VIA(board)
            returned.SetViaType(pcbnew.VIATYPE_THROUGH)
            returned.SetPosition(pcbnew.VECTOR2I_MM(11.0, 8.4))
            returned.SetWidth(pcbnew.FromMM(0.60))
            returned.SetDrill(pcbnew.FromMM(0.30))
            returned.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            returned.SetNetCode(board.GetNetcodeFromNetname("GND"))
            board.Add(returned)
            for zone in board.Zones():
                zone.UnFill()
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            supported = field.field_coupling_summary(path, board=board)

        self.assertTrue(supported["ok"], supported)
        shield = supported["interactions"][0]["shield"]
        self.assertGreater(shield["transition_return_supported_samples"], 0)
        self.assertTrue(shield["transition_return_evidence"])

    def test_intended_differential_pair_members_are_not_mutual_faults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ("/USB_D_P", "F.Cu", (4.0, 8.0), (20.0, 8.0)),
                ("/USB_D_N", "F.Cu", (4.0, 8.33), (20.0, 8.33)),
            ])
            report = field.field_coupling_summary(path)

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["interaction_count"], 0)

    def test_port_qualified_can_pair_members_are_not_mutual_faults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ("/CAN_H_J1", "F.Cu", (4.0, 8.0), (20.0, 8.0)),
                ("/CAN_L_J1", "F.Cu", (4.0, 8.33), (20.0, 8.33)),
            ])
            report = field.field_coupling_summary(path)

        self.assertTrue(report["ok"], report)
        self.assertEqual(report["interaction_count"], 0)

    def test_port_qualified_pair_does_not_hide_sensitive_neighbor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ("/CAN_H_J1", "F.Cu", (4.0, 8.0), (20.0, 8.0)),
                ("/CAN_L_J1", "F.Cu", (4.0, 8.33), (20.0, 8.33)),
                ("/DETECT", "F.Cu", (4.0, 8.66), (20.0, 8.66)),
            ])
            report = field.field_coupling_summary(path)

        self.assertFalse(report["ok"], report)
        self.assertEqual(report["blocking_count"], 2)
        self.assertNotIn(
            {"/CAN_H_J1", "/CAN_L_J1"},
            [set(row["nets"]) for row in report["interactions"]])


if __name__ == "__main__":
    unittest.main()
