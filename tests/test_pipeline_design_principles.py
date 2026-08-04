#!/usr/bin/env python3
"""Regression teeth for profile-aware SI and the aggregate release gate."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest("KiCad pcbnew required") from exc

import cec_constraints as C  # noqa: E402
import cec_fab_check as DFM  # noqa: E402
import cec_fr  # noqa: E402
import cec_impedance as SI  # noqa: E402
import cec_pcb  # noqa: E402
import cec_score  # noqa: E402
import cec_synth_pipeline as CSP  # noqa: E402


class HubHierarchicalNetclassTest(unittest.TestCase):
    HUB = os.path.join(ROOT, "beta", "hub-standard-rev2", "candidate",
                       "hub-standard-rev2-candidate.kicad_pcb")
    PROJECTS = (
        os.path.join(ROOT, "beta", "hub-standard-rev2",
                     "hub-standard-rev2.kicad_pro"),
        os.path.join(ROOT, "beta", "hub-standard-rev2", "candidate",
                     "hub-standard-rev2-candidate.kicad_pro"),
    )

    @unittest.skipUnless(os.path.isfile(HUB), "current Hub candidate required")
    def test_current_hierarchical_rails_and_pairs_resolve_to_physical_classes(self):
        # KiCad sheet paths prefix the leaf net name.  Root-only patterns such
        # as `/PSU_5V` silently assign the real
        # `/POWER INPUT + SOURCE SELECTION/PSU_5V` net to Default, which let a
        # 2.5 A rail route at 0.2 mm.  Exercise the actual current Hub names.
        board = pcbnew.LoadBoard(self.HUB)
        expected = {
            "+5VSB": ("Power", 1.0, 0.8, 0.4),
            "/5VSB_RAW": ("Power", 1.0, 0.8, 0.4),
            "/MAIN_5V_RAW": ("Power", 1.0, 0.8, 0.4),
            "/USB_VBUS": ("Power", 1.0, 0.8, 0.4),
            "/POWER INPUT + SOURCE SELECTION/PSU_5V":
                ("Power", 1.0, 0.8, 0.4),
            "/POWER INPUT + SOURCE SELECTION/PSU_5V_KVM":
                ("Power", 1.0, 0.8, 0.4),
            "/HOLD-UP + 3V3 REGULATOR/+5V_HOLD":
                ("Power", 1.0, 0.8, 0.4),
            "/CAN + FOUR MODULE PORTS + STACK/VCC_P4":
                ("Power", 1.0, 0.8, 0.4),
            "/CAN + FOUR MODULE PORTS + STACK/CAN_H":
                ("CAN", 0.25, 0.6, 0.3),
            "/MCU + USB SERVICE PORT/USB_D_P":
                ("USB", 0.20, 0.6, 0.3),
        }
        for net, want in expected.items():
            item = board.GetNetInfo().GetNetItem(net)
            self.assertIsNotNone(item, net)
            cls = item.GetNetClassSlow()
            got = (cls.GetName(), cls.GetTrackWidth() / 1e6,
                   cls.GetViaDiameter() / 1e6, cls.GetViaDrill() / 1e6)
            self.assertEqual(got, want, net)

    def test_materialization_donor_and_reference_share_wildcard_patterns(self):
        expected = {
            ("Power", "+5VSB"), ("Power", "*5VSB_RAW"),
            ("Power", "*+5V_HOLD"), ("Power", "*USB_VBUS"),
            ("Power", "*MAIN_5V_RAW"), ("Power", "*PSU_5V"),
            ("Power", "*PSU_5V_KVM"), ("Power", "*VCC_P1"),
            ("Power", "*VCC_P2"), ("Power", "*VCC_P3"),
            ("Power", "*VCC_P4"), ("CAN", "*CAN_H"),
            ("CAN", "*CAN_L"), ("USB", "*USB_D_P"),
            ("USB", "*USB_D_N"),
        }
        observed = []
        for path in self.PROJECTS:
            with open(path, encoding="utf-8") as source:
                rows = json.load(source)["net_settings"]["netclass_patterns"]
            patterns = {(row["netclass"], row["pattern"]) for row in rows}
            self.assertEqual(patterns, expected, path)
            observed.append(patterns)
        self.assertEqual(observed[0], observed[1])


class RouteGeometryAdvisoryTest(unittest.TestCase):
    def test_unlocked_off_angle_is_reported_and_locked_authored_is_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "angles.kicad_pcb")
            board = pcbnew.CreateEmptyBoard()
            net = pcbnew.NETINFO_ITEM(board, "/A")
            board.Add(net)
            for y, locked in ((2.0, False), (5.0, True)):
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pcbnew.VECTOR2I_MM(1.0, y))
                track.SetEnd(pcbnew.VECTOR2I_MM(4.0, y + 2.0))
                track.SetWidth(pcbnew.FromMM(0.20))
                track.SetLayer(board.GetLayerID("F.Cu"))
                track.SetNet(net)
                track.SetLocked(locked)
                board.Add(track)
            pcbnew.SaveBoard(path, board)
            report = CSP._oracle_route_sanity(path)
            self.assertEqual(report["unlocked_off45_tracks"], 1)
            self.assertEqual(report["unlocked_off45_examples"][0]["net"], "/A")


class CopperCrossingAcceptanceTest(unittest.TestCase):
    """Prove that apparent over-under crossings are legal, while a real
    same-layer, different-net crossing can never pass the route gate."""

    @staticmethod
    def _mm(value):
        return pcbnew.FromMM(value)

    def _board(self, directory, *, over_under):
        path = os.path.join(directory, "crossing.kicad_pcb")
        board = pcbnew.CreateEmptyBoard()
        for (x1, y1), (x2, y2) in (
                ((0, 0), (20, 0)), ((20, 0), (20, 20)),
                ((20, 20), (0, 20)), ((0, 20), (0, 0))):
            edge = pcbnew.PCB_SHAPE(board, pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I(self._mm(x1), self._mm(y1)))
            edge.SetEnd(pcbnew.VECTOR2I(self._mm(x2), self._mm(y2)))
            edge.SetLayer(board.GetLayerID("Edge.Cuts"))
            edge.SetWidth(self._mm(0.1))
            board.Add(edge)
        net_a = pcbnew.NETINFO_ITEM(board, "A")
        net_b = pcbnew.NETINFO_ITEM(board, "B")
        board.Add(net_a)
        board.Add(net_b)

        def pad(ref, x, y, net):
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference(ref)
            pos = pcbnew.VECTOR2I(self._mm(x), self._mm(y))
            footprint.SetPosition(pos)
            item = pcbnew.PAD(footprint)
            item.SetPadName("1")
            item.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            item.SetSize(pcbnew.VECTOR2I(self._mm(1.0), self._mm(1.0)))
            item.SetDrillSize(pcbnew.VECTOR2I(self._mm(0.5), self._mm(0.5)))
            item.SetPosition(pos)
            item.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            item.SetLayerSet(pcbnew.PAD.PTHMask())
            item.SetNet(net)
            footprint.Add(item)
            board.Add(footprint)

        def track(net, start, end, layer):
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(pcbnew.VECTOR2I(self._mm(start[0]), self._mm(start[1])))
            item.SetEnd(pcbnew.VECTOR2I(self._mm(end[0]), self._mm(end[1])))
            item.SetWidth(self._mm(0.25))
            item.SetLayer(board.GetLayerID(layer))
            item.SetNet(net)
            board.Add(item)

        pad("A1", 3, 10, net_a)
        pad("A2", 17, 10, net_a)
        pad("B1", 10, 3, net_b)
        pad("B2", 10, 17, net_b)
        track(net_a, (3, 10), (17, 10), "F.Cu")
        track(net_b, (10, 3), (10, 17), "B.Cu" if over_under else "F.Cu")
        pcbnew.SaveBoard(path, board)
        return path

    def test_same_layer_different_net_crossing_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, over_under=False)
            metrics = cec_score.score(
                path, rules=cec_score.Rules(require_unconnected_zero=False))
            self.assertFalse(metrics.gates_pass, metrics.detail)
            self.assertGreater(metrics.drc_types.get("tracks_crossing", 0), 0,
                               metrics.drc_types)

    def test_different_layer_over_under_crossing_is_not_a_drc(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory, over_under=True)
            metrics = cec_score.score(
                path, rules=cec_score.Rules(require_unconnected_zero=False))
            self.assertTrue(metrics.gates_pass, metrics.detail)
            self.assertEqual(metrics.drc_types.get("tracks_crossing", 0), 0,
                             metrics.drc_types)


class ProfileAwareImpedanceTest(unittest.TestCase):
    def test_current_high_current_profile_replaces_historical_constants(self):
        s = SI.stackup_for_board("beta/12vhpwr-standard/current.kicad_pcb")
        self.assertEqual(s["profile"], "jlcpcb_6l_pofv_high_current")
        self.assertEqual(s["vendor_stackup"], "JLC06162H-3313")
        self.assertAlmostEqual(s["h_mm"], 0.0994, places=4)
        self.assertAlmostEqual(s["er"], 4.10, places=2)
        self.assertAlmostEqual(s["t_mm"], 0.070, places=3)
        self.assertNotEqual(s["h_mm"], SI.LEGACY_STACKUP["h_mm"])

    def test_hub_uses_one_ounce_outer_profile(self):
        s = SI.stackup_for_board("beta/hub-standard-rev2/current.kicad_pcb")
        self.assertEqual(s["profile"], "jlcpcb_6l_pofv_signal")
        self.assertAlmostEqual(s["t_mm"], 0.035, places=3)
        self.assertEqual(s["reference_layer"], "In1.Cu")

    def test_fab_audit_resolves_copper_weight_per_board(self):
        hpwr = DFM.board_outer_copper_oz(
            os.path.join(ROOT, "beta", "12vhpwr-standard",
                         "12vhpwr-standard-module.kicad_pcb"))
        hub = DFM.board_outer_copper_oz(
            os.path.join(ROOT, "beta", "hub-standard-rev2", "candidate",
                         "hub-standard-rev2-candidate.kicad_pcb"))
        self.assertAlmostEqual(hpwr, 2.0, delta=0.05)
        self.assertAlmostEqual(hub, 1.0, delta=0.05)

    def test_no_profile_is_explicitly_labelled_legacy(self):
        s = SI.stackup_for_board("misc/unknown-board.kicad_pcb")
        self.assertIsNone(s["profile"])
        self.assertIn("legacy", s["source"])
        self.assertIn("warning", s)


class AggregateReleaseGateTest(unittest.TestCase):
    def _constraint(self, cid, *, severity="hard", checkable="yes", status="ratified"):
        return C.Constraint(cid, cid, "test", severity, checkable, "none",
                            "rule", "test", status=status)

    def test_post_route_excludes_only_path_based_schematic_sync(self):
        rows = [
            (self._constraint("sch-pcb-sync"), "FAIL", "no sibling schematic", None),
            (self._constraint("decoupling-cap-owner"), "FAIL", "shared bypass", None),
            (self._constraint("soft-one", severity="soft"), "FAIL", "soft", None),
            (self._constraint("proposed-one", status="proposed"), "FAIL", "draft", None),
        ]
        blocked = C.blocking_rows(rows, phase="post_route")
        self.assertEqual([row[0].id for row in blocked], ["decoupling-cap-owner"])

    def test_checker_error_is_release_blocking(self):
        rows = [(self._constraint("route-check"), "ERROR", "crash", None)]
        self.assertEqual(len(C.blocking_rows(rows)), 1)


class HighSpeedPhysicalGateTest(unittest.TestCase):
    def _board(self, directory):
        netlist = os.path.join(directory, "pair.net")
        path = os.path.join(directory, "pair.kicad_pcb")
        with open(netlist, "w", encoding="utf-8") as handle:
            handle.write('(export (nets (net (code "1") (name "GND"))))\n')
        self.assertTrue(cec_pcb.build_board(
            path, netlist, {}, [(5.0, 5.0)], None, 20.0, 20.0,
            force_argv=False, stackup_profile="jlcpcb_6l_pofv_signal"))
        board = pcbnew.LoadBoard(path)
        pnet = pcbnew.NETINFO_ITEM(board, "/USB_D_P")
        nnet = pcbnew.NETINFO_ITEM(board, "/USB_D_N")
        board.Add(pnet)
        board.Add(nnet)
        for net, y in ((pnet, 9.835), (nnet, 10.165)):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I_MM(2.0, y))
            track.SetEnd(pcbnew.VECTOR2I_MM(18.0, y))
            track.SetWidth(pcbnew.FromMM(0.20))
            track.SetLayer(board.GetLayerID("F.Cu"))
            track.SetNet(net)
            board.Add(track)
        pcbnew.SaveBoard(path, board)
        board = pcbnew.LoadBoard(path)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(path, board)
        return path

    def test_clean_surface_pair_has_continuous_ground_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory)
            report = C.high_speed_pair_summary(path)
            self.assertTrue(report["applicable"])
            self.assertTrue(report["ok"], report)
            self.assertGreaterEqual(report["pairs"][0]["reference_coverage_pct"], 95.0)
            self.assertGreaterEqual(report["pairs"][0]["coupled_coverage_pct"], 80.0)

    def test_asymmetric_signal_via_and_missing_return_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory)
            board = pcbnew.LoadBoard(path)
            via = pcbnew.PCB_VIA(board)
            via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetPosition(pcbnew.VECTOR2I_MM(10.0, 9.835))
            # Keep the synthetic via clear of the partner trace; a larger land
            # would physically short the 0.33mm-spaced fixture and KiCad would
            # correctly merge the connected copper onto one net on reload.
            via.SetWidth(pcbnew.FromMM(0.30))
            via.SetDrill(pcbnew.FromMM(0.20))
            via.SetLayerPair(board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu"))
            via.SetNet(board.FindNet("/USB_D_P"))
            board.Add(via)
            pcbnew.SaveBoard(path, board)
            report = C.high_speed_pair_summary(path)
            self.assertFalse(report["ok"])
            joined = " ".join(report["violations"])
            self.assertIn("asymmetric via count", joined)
            self.assertIn("lack a GND return via", joined)

    def test_ses_geometry_is_raised_to_assigned_netclass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._board(directory)
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            with open(pro, "r", encoding="utf-8") as handle:
                project = json.load(handle)
            project["net_settings"] = {
                "classes": [
                    {"name": "Default", "track_width": 0.20,
                     "via_diameter": 0.45, "via_drill": 0.20},
                    {"name": "USB", "track_width": 0.25,
                     "via_diameter": 0.60, "via_drill": 0.30},
                ],
                "netclass_patterns": [{"netclass": "USB", "pattern": "*/USB_D_*"}],
                "netclass_assignments": {},
            }
            with open(pro, "w", encoding="utf-8") as handle:
                json.dump(project, handle)
            board = pcbnew.LoadBoard(path)
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pcbnew.VECTOR2I_MM(10.0, 8.5))
            via.SetWidth(pcbnew.FromMM(0.40))
            via.SetDrill(pcbnew.FromMM(0.20))
            via.SetLayerPair(board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu"))
            via.SetNet(board.FindNet("/USB_D_P"))
            board.Add(via)
            result = cec_fr.normalize_netclass_geometry(board, path)
            self.assertEqual(result["tracks"], 2)
            self.assertEqual(result["vias"], 1)
            widths = [t.GetWidth() / 1e6 for t in board.GetTracks()
                      if t.GetClass() == "PCB_TRACK"]
            self.assertEqual(widths, [0.25, 0.25])
            self.assertAlmostEqual(via.GetWidth(via.TopLayer()) / 1e6, 0.60)
            self.assertAlmostEqual(via.GetDrillValue() / 1e6, 0.30)

    def test_power_width_neckdown_is_bounded_at_fine_pitch_smd_pad(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "neckdown.kicad_pcb")
            pro = path[:-len(".kicad_pcb")] + ".kicad_pro"
            board = pcbnew.CreateEmptyBoard()
            net = pcbnew.NETINFO_ITEM(board, "PWR")
            board.Add(net)

            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference("U1")
            fp.SetLayer(pcbnew.F_Cu)
            fp.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))
            pad = pcbnew.PAD(fp)
            pad.SetPadName("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(1.0, 0.4))
            pad.SetPosition(pcbnew.VECTOR2I_MM(10.0, 10.0))
            layers = pcbnew.LSET()
            layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers)
            pad.SetNet(net)
            fp.Add(pad)
            board.Add(fp)

            def add_track(x0, x1):
                track = pcbnew.PCB_TRACK(board)
                track.SetStart(pcbnew.VECTOR2I_MM(x0, 10.0))
                track.SetEnd(pcbnew.VECTOR2I_MM(x1, 10.0))
                track.SetWidth(pcbnew.FromMM(0.20))
                track.SetLayer(pcbnew.F_Cu)
                track.SetNet(net)
                board.Add(track)

            add_track(10.0, 13.0)  # starts on the narrow SMD pad
            add_track(20.0, 23.0)  # ordinary rail: no neck-down entitlement
            pcbnew.SaveBoard(path, board)
            with open(pro, "w", encoding="utf-8") as handle:
                json.dump({"net_settings": {
                    "classes": [
                        {"name": "Default", "track_width": 0.20,
                         "via_diameter": 0.60, "via_drill": 0.30},
                        {"name": "Power", "track_width": 1.00,
                         "via_diameter": 0.80, "via_drill": 0.40},
                    ],
                    "netclass_assignments": {"PWR": "Power"},
                    "netclass_patterns": [],
                }}, handle)

            result = cec_fr.normalize_netclass_geometry(board, path)
            local = [t for t in board.GetTracks()
                     if t.GetClass() == "PCB_TRACK"
                     and t.GetStart().x / 1e6 < 14.0]
            remote = [t for t in board.GetTracks()
                      if t.GetClass() == "PCB_TRACK"
                      and t.GetStart().x / 1e6 >= 14.0]

            self.assertEqual(result["neckdown_split_tracks"], 1)
            self.assertEqual(result["neckdown_sections"], 1)
            self.assertEqual(sorted(round(t.GetWidth() / 1e6, 2) for t in local),
                             [0.20, 1.00])
            narrow_mm = sum(t.GetLength() / 1e6 for t in local
                            if round(t.GetWidth() / 1e6, 2) == 0.20)
            self.assertAlmostEqual(narrow_mm, 1.5, places=3)
            self.assertEqual([round(t.GetWidth() / 1e6, 2) for t in remote],
                             [1.00])
            before = [(t.GetStart().x, t.GetEnd().x, t.GetWidth())
                      for t in board.GetTracks()
                      if t.GetClass() == "PCB_TRACK"]
            second = cec_fr.normalize_netclass_geometry(board, path)
            after = [(t.GetStart().x, t.GetEnd().x, t.GetWidth())
                     for t in board.GetTracks()
                     if t.GetClass() == "PCB_TRACK"]
            self.assertEqual(second["neckdown_split_tracks"], 0)
            self.assertEqual(after, before)

    def test_ses_import_reads_netclasses_from_staged_source_project(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._board(directory)
            ses = os.path.join(directory, "candidate.ses")
            output = os.path.join(directory, "candidate.kicad_pcb")
            with open(ses, "w", encoding="utf-8") as handle:
                handle.write("(session candidate)\n")

            self.assertFalse(os.path.exists(
                output[:-len(".kicad_pcb")] + ".kicad_pro"))
            with mock.patch.object(pcbnew, "ImportSpecctraSES",
                                   return_value=True), \
                    mock.patch.object(cec_fr, "normalize_netclass_geometry",
                                      return_value={"tracks": 0, "vias": 0}) as normalize:
                cec_fr.import_ses(source, ses, output, fill_zones=False,
                                  power_pours=(), kelvin_taps=False)

            self.assertTrue(os.path.exists(output))
            self.assertGreaterEqual(normalize.call_count, 1)
            self.assertTrue(all(call.args[1] == source
                                for call in normalize.call_args_list))

    def test_ses_import_renormalizes_last_mile_geometry_before_scoring(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self._board(directory)
            ses = os.path.join(directory, "candidate.ses")
            output = os.path.join(directory, "candidate.kicad_pcb")
            with open(ses, "w", encoding="utf-8") as handle:
                handle.write("(session candidate)\n")

            lastmile = {"closed": 1, "legs": 1, "refused": 0,
                        "far": 0, "cross_layer": 0}
            with mock.patch.dict(os.environ, {"CEC_LASTMILE": "1"}), \
                    mock.patch.object(pcbnew, "ImportSpecctraSES",
                                      return_value=True), \
                    mock.patch.object(pcbnew, "ZONE_FILLER"), \
                    mock.patch.object(cec_fr, "synthesize_lastmile",
                                      return_value=lastmile), \
                    mock.patch.object(cec_fr, "normalize_netclass_geometry",
                                      return_value={"tracks": 1, "vias": 1}) as normalize:
                cec_fr.import_ses(source, ses, output, fill_zones=True,
                                  power_pours=(), kelvin_taps=False)

            self.assertEqual(normalize.call_count, 2)
            self.assertTrue(all(call.args[1] == source
                                for call in normalize.call_args_list))


if __name__ == "__main__":
    unittest.main()
