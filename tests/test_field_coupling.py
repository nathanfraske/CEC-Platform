#!/usr/bin/env python3
"""Physical aggressor/victim interaction and shielding regressions."""

import os
import sys
import tempfile
import unittest
from types import MappingProxyType

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest("KiCad pcbnew required") from exc

import cec_field_coupling as field  # noqa: E402
import cec_pcb  # noqa: E402


class FieldCouplingTest(unittest.TestCase):
    def test_structured_class_uses_only_declared_name_not_dimension_metadata(self):
        metadata = dict(diff_pair_width=.2, diff_pair_gap=.25,
            diff_pair_via_gap=.25, track_width=.2,
            provenance="/older/USB/ADC/CLOCK/design",
            dimension_contract=dict(role="branch", current=None, diff_pair=True))
        for name in ("Default", "Signal", "DDR HighSpeed", "Analog", "SwitchNode",
                     "Clock", "USB", "Sense"):
            for net in ("/renamed/IO8_STRAP", "/renamed/SENSE_HI", "/renamed/PWM"):
                with self.subTest(name=name, net=net):
                    expected = field.classify_net(net, netclass=name)
                    self.assertEqual(expected, field.classify_net(net,
                        netclass=MappingProxyType(dict(metadata, name=name))))
        self.assertEqual(field.classify_net("/IO8_STRAP"),
                         field.classify_net("/IO8_STRAP", netclass=metadata))

    def test_malformed_explicit_class_identity_is_not_inferred_or_accepted(self):
        for value in (True, 4, [], {"name": ["Default"]}, {"name": False}):
            with self.subTest(value=value), self.assertRaisesRegex(
                    ValueError, "invalid_netclass_resolver_result"):
                field.classify_net("/DATA0", netclass=value)

    def test_native_summary_and_proposal_have_identical_class_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ("/opaque-A", "F.Cu", (4., 8.), (20., 8.)),
                ("/opaque-B", "F.Cu", (4., 8.6), (20., 8.6)),
                ("/neutral", "F.Cu", (4., 12.), (20., 12.)),
            ])
            board = pcbnew.LoadBoard(path)
            before = field._field_snapshot_inventory(board)
            proposal = dict(net="/opaque-A", layer=int(pcbnew.F_Cu), width_nm=200000,
                start_nm=(4000000, 8500000), end_nm=(20000000, 8500000))
            for classes, blocked in (({}, False),
                    ({"/opaque-A": "SwitchNode", "/opaque-B": "Analog"}, True)):
                text = lambda net: classes.get(net, "Default")
                structured = lambda net: MappingProxyType(dict(name=text(net),
                    diff_pair_width=.2, diff_pair_gap=.25, diff_pair_via_gap=.25))
                a = field.field_coupling_summary(path, board=board,
                    _netclass_resolver=text)
                b = field.field_coupling_summary(path, board=board,
                    _netclass_resolver=structured)
                self.assertEqual(a["classified_nets"], b["classified_nets"])
                self.assertEqual(field.blocker_keys(a), field.blocker_keys(b))
                self.assertEqual(bool(a["blocking_count"]), blocked)
                p = field.assess_proposed_tracks(board, [proposal], board_path=path,
                    netclass_resolver=structured)
                self.assertTrue(p["complete"], p)
                self.assertEqual(p["ok"], not blocked, p)
            self.assertEqual(field._field_snapshot_inventory(board), before)
            malformed = field.assess_proposed_tracks(board, [proposal], board_path=path,
                netclass_resolver=lambda net: {"name": ["Default"]})
            self.assertIsNone(malformed["ok"])
            self.assertFalse(malformed["complete"])
            self.assertEqual(malformed["reason"], "invalid_netclass_resolver_result")

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

    def test_nearby_wide_trace_is_not_a_crossing_without_projected_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ('/SW', 'In2.Cu', (8., 12.), (9., 13.)),
                ('/VOUT_SENSE', 'In3.Cu', (20., 14.), (24., 14.)),
            ])
            board = pcbnew.LoadBoard(path)
            wide = next(t for t in board.GetTracks() if t.GetNetname() == '/VOUT_SENSE')
            wide.SetWidth(pcbnew.FromMM(6.))
            report = field.field_coupling_summary(path, board=board)
            self.assertTrue(report['ok'], report)
            self.assertTrue(report['interactions'],
                [(t.GetNetname(), t.GetWidth(), board.GetLayerName(t.GetLayer()))
                 for t in board.GetTracks()])
            row = report['interactions'][0]
            self.assertFalse(row['projected_copper_overlap'])
            self.assertGreater(row['edge_gap_mm'], 6.)
            self.assertLess(row['edge_gap_mm'], row['interaction_reach_mm'])

    def test_projected_copper_edge_overlap_requires_crossing_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ('/SW', 'In2.Cu', (4., 8.), (10., 8.)),
                ('/VOUT_SENSE', 'In3.Cu', (10.15, 8.05), (13., 10.9)),
            ])
            report = field.field_coupling_summary(path)
            self.assertFalse(report['ok'], report)
            self.assertTrue(report['interactions'][0]['projected_copper_overlap'])
            self.assertIn('not approximately perpendicular', report['violations'][0])

    def test_nearby_wide_parallel_run_stays_blocking_without_crossing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ('/SW', 'In2.Cu', (8., 12.), (24., 12.)),
                ('/VOUT_SENSE', 'In3.Cu', (8., 16.), (24., 16.)),
            ])
            board = pcbnew.LoadBoard(path)
            for t in board.GetTracks():
                if t.GetNetname() == '/VOUT_SENSE':
                    t.SetWidth(pcbnew.FromMM(2.))
            report = field.field_coupling_summary(path, board=board)
            self.assertFalse(report['ok'], (report,
                [(t.GetNetname(), t.GetWidth(), board.GetLayerName(t.GetLayer()))
                 for t in board.GetTracks()]))
            self.assertFalse(report['interactions'][0]['projected_copper_overlap'])
            self.assertIn('unshielded parallel', report['violations'][0])

    def test_parallel_overlap_is_independent_of_operand_order(self):
        # Unequal oblique lengths have different projections. Save/reload
        # may reorder UUIDs, but cannot change proposal vs final admission.
        a = dict(a=(0., 0.), b=(3., 0.))
        b = dict(a=(0., .3), b=(10., 1.3))
        left = max(field._parallel_overlap(a, b), field._parallel_overlap(b, a))
        right = max(field._parallel_overlap(b, a), field._parallel_overlap(a, b))
        self.assertEqual(left, right)

    def test_native_addition_receiver_refuses_a_new_real_crossing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ('/BUCK/U3_SW', 'In2.Cu', (4., 8.), (20., 8.)),
                ('/ADC/VOUT_SENSE', 'In3.Cu', (24., 14.), (25., 15.)),
            ])
            board = pcbnew.LoadBoard(path)
            before_ids = {t.m_Uuid.AsString() for t in board.GetTracks()}
            added = pcbnew.PCB_TRACK(board)
            added.SetStart(pcbnew.VECTOR2I_MM(8., 4.))
            added.SetEnd(pcbnew.VECTOR2I_MM(16., 12.))
            added.SetWidth(pcbnew.FromMM(.2)); added.SetLayer(pcbnew.In3_Cu)
            added.SetNetCode(board.GetNetcodeFromNetname('/ADC/VOUT_SENSE')); board.Add(added)
            name = board.GetFileName()
            before_live = {t.m_Uuid.AsString() for t in board.GetTracks()}
            result = field.assess_native_additions(board, before_ids, board_path=path)
            self.assertTrue(result['complete'], result)
            self.assertFalse(result['ok'], result)
            self.assertTrue(result['new_blockers'])
            self.assertEqual({t.m_Uuid.AsString() for t in board.GetTracks()}, before_live)
            self.assertEqual(board.GetFileName(), name)
            self.assertFalse(result['board_mutated'])

    def test_new_barrel_cannot_borrow_stale_ground_shielding(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [
                ('/CAN_H', 'F.Cu', (9.5, 8.), (10.5, 8.)),
                ('/ADC/DETECT', 'In2.Cu', (9.5, 8.85), (10.5, 8.85)),
                ('/UNCLASSIFIED', 'F.Cu', (2., 3.), (2.1, 3.)),
            ])
            board = pcbnew.LoadBoard(path)
            for zone in board.Zones():
                if zone.GetNetname() == 'GND':
                    zone.SetLocalClearance(pcbnew.FromMM(1.))
                    zone.UnFill()
            self.assertTrue(pcbnew.ZONE_FILLER(board).Fill(board.Zones()))
            self.assertTrue(field.field_coupling_summary(path, board=board)['ok'])
            before_ids = {t.m_Uuid.AsString() for t in board.GetTracks()}
            via = pcbnew.PCB_VIA(board)
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            # No signal-copper short: the newly cut reference-plane clearance
            # is wider than its actual barrel/land and hits the field locus.
            via.SetPosition(pcbnew.VECTOR2I_MM(10., 8.))
            via.SetWidth(pcbnew.FromMM(.6)); via.SetDrill(pcbnew.FromMM(.3))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNetCode(board.GetNetcodeFromNetname('/CAN_H')); board.Add(via)
            self.assertEqual(via.GetNetname(), '/CAN_H')
            # The caller's cached plane still appears shielded. The private
            # actual fill must reveal the signal barrel's new antipad.
            self.assertTrue(field.field_coupling_summary(path, board=board)['ok'])
            result = field.assess_native_additions(board, before_ids, board_path=path)
            self.assertTrue(result['complete'], result)
            self.assertFalse(result['ok'], result)
            self.assertGreater(result['ground_zones_refilled_on_private_copy'], 0)
            self.assertFalse(result['original_ground_zones_mutated'])

    def test_missing_prior_native_identity_is_unknown_not_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, [('NEUTRAL', 'F.Cu', (10., 10.), (11., 10.))])
            board = pcbnew.LoadBoard(path)
            result = field.assess_native_additions(board, {'missing-identity'}, board_path=path)
            self.assertIsNone(result['ok'])
            self.assertFalse(result['complete'])
            self.assertFalse(result['release_authority'])

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
