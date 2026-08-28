import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import cec_fab_check
import cec_fab_profile

try:
    import pcbnew
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest("pcbnew required") from exc


class FabCheckProfileTests(unittest.TestCase):
    def test_through_via_geometry_obeys_board_drill_and_annular_minima(self):
        class Settings:
            m_ViasMinSize = 500_000
            m_MinThroughDrill = 300_000
            m_ViasMinAnnularWidth = 125_000

        class Board:
            @staticmethod
            def GetDesignSettings():
                return Settings()

        diameter, drill, evidence = (
            cec_fab_profile.board_legal_through_via_geometry(
                Board(), 0.45, 0.25))
        self.assertEqual(drill, 0.30)
        self.assertEqual(diameter, 0.55)
        self.assertEqual(evidence["board_min_drill_mm"], 0.30)
        self.assertEqual(evidence["board_min_annular_mm"], 0.125)

    def test_current_pcie_family_names_resolve_high_current_profile(self):
        for name in ("pcie-8pin-2port", "pcie-8pin-3port"):
            self.assertEqual(
                cec_fab_profile.profile_for_board_hint(name),
                "jlcpcb_6l_pofv_high_current")

    def test_acid_traps_and_failed_artifact_scan_block_fabrication(self):
        base = {"drc_total": 0, "slivers": [], "islands": [],
                "drill_aspect": [], "acid_traps": []}
        self.assertEqual(cec_fab_check.blocking_count(base), 0)
        acid = dict(base, acid_traps=[{"angle_deg": 25.0}])
        self.assertEqual(cec_fab_check.blocking_count(acid), 1)
        failed = dict(base, artifact_error="geometry backend unavailable")
        self.assertEqual(cec_fab_check.blocking_count(failed), 1)

    def test_pofv_overlay_uses_declared_process_floors(self):
        process = cec_fab_profile.get_profile("jlcpcb_6l_pofv_signal")
        rules = cec_fab_check.profile_rules(
            cec_fab_check.PROFILES["jlcpcb"], 1.0, process
        )
        self.assertEqual(rules["via"], 0.35)
        self.assertEqual(rules["drill"], 0.20)
        self.assertEqual(rules["annular"], 0.05)
        self.assertEqual(rules["h2h"], 0.25)
        self.assertEqual(rules["hole_clearance"], 0.20)

    def test_ordinary_process_keeps_conservative_via_floors(self):
        rules = cec_fab_check.profile_rules(
            cec_fab_check.PROFILES["jlcpcb"], 1.0
        )
        self.assertEqual(rules["via"], 0.45)
        self.assertEqual(rules["annular"], 0.13)
        self.assertEqual(rules["h2h"], 0.50)

    def test_only_explicit_narrow_qualified_rules_cross_fab_boundary(self):
        text = """(version 1)
(rule ordinary_design_exception
  (condition "A.memberOfFootprint('J1')")
  (constraint hole_clearance (min 0.10mm)))
(rule fab_qualified_vendor_land
  (condition "A.memberOfFootprint('J2') && A.Pad_Number == '1'")
  (constraint hole_clearance (min 0.15mm)))
(rule fab_qualified_too_broad
  (constraint clearance (min 0.01mm)))
(rule fab_qualified_wrong_domain
  (condition "A.memberOfFootprint('U1')")
  (constraint track_width (min 0.01mm)))
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "board.kicad_dru"
            path.write_text(text, encoding="utf-8")
            rules = cec_fab_check.extract_qualified_fab_rules(str(path))
        self.assertEqual([row["name"] for row in rules],
                         ["fab_qualified_vendor_land"])
        self.assertEqual(rules[0]["minima"]["hole_clearance"], 0.15)

    def test_generated_fab_dru_appends_qualified_rule(self):
        rules = cec_fab_check.profile_rules(
            cec_fab_check.PROFILES["jlcpcb"], 1.0)
        qualified = [{
            "name": "fab_qualified_vendor_land",
            "text": "(rule fab_qualified_vendor_land\n"
                    "  (condition \"A.memberOfFootprint('J2')\")\n"
                    "  (constraint hole_clearance (min 0.15mm)))",
        }]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fab.kicad_dru"
            cec_fab_check.write_fab_dru(
                str(path), rules, qualified_rules=qualified)
            generated = path.read_text(encoding="utf-8")
        self.assertIn("fab_qualified_vendor_land", generated)
        self.assertIn("fab min clearance", generated)

    def test_fab_drc_uses_central_geometry_qualification_fail_closed(self):
        rows = [{"type": "via_diameter"}, {"type": "clearance"}]
        board = object()
        with mock.patch(
                "cec_score.qualify_structural_violations",
                return_value=[rows[1]]) as qualify:
            self.assertEqual(
                cec_fab_check.qualify_fab_drc_violations(rows, board),
                [rows[1]])
            qualify.assert_called_once_with(rows, board)
        with mock.patch(
                "cec_score.qualify_structural_violations",
                side_effect=RuntimeError("proof unavailable")):
            self.assertEqual(
                cec_fab_check.qualify_fab_drc_violations(rows, board), rows)

    def test_same_net_pad_copper_covers_acute_track_junction(self):
        board = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(board, "/SIG")
        board.Add(net)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("U1")
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("1")
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.2, 1.2))
        pad.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(net)
        footprint.Add(pad)
        board.Add(footprint)
        for end in ((12, 10), (12, 12)):
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pcbnew.VECTOR2I_MM(10, 10))
            track.SetEnd(pcbnew.VECTOR2I_MM(*end))
            track.SetWidth(pcbnew.FromMM(0.20))
            track.SetLayer(board.GetLayerID("F.Cu"))
            track.SetNet(net)
            board.Add(track)

        rules = cec_fab_check.profile_rules(
            cec_fab_check.PROFILES["jlcpcb"], 1.0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "board.kicad_pcb"
            pcbnew.SaveBoard(str(path), board)
            report = cec_fab_check.artifact_scan(str(path), rules)
        self.assertEqual(report["acid_traps"], [])
        self.assertEqual(len(report["covered_acute_junctions"]), 1)
        self.assertEqual(report["covered_acute_junctions"][0]["anchor_pads"],
                         ["U1.1"])


if __name__ == "__main__":
    unittest.main()
