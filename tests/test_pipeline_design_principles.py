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
            self.assertEqual(normalize.call_count, 1)
            self.assertEqual(normalize.call_args.args[1], source)


if __name__ == "__main__":
    unittest.main()
