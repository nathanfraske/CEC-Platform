"""Project-rule provenance teeth for renamed/materialized board artifacts."""
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import cec_synth_pipeline as synth  # noqa: E402


class RuleAuthorityCarriageTests(unittest.TestCase):
    def test_rich_config_donor_replaces_default_only_scratch_project(self):
        with tempfile.TemporaryDirectory() as directory:
            donor_board = os.path.join(directory, "current.kicad_pcb")
            donor_pro = donor_board.replace(".kicad_pcb", ".kicad_pro")
            output_board = os.path.join(directory, "wave.kicad_pcb")
            output_pro = output_board.replace(".kicad_pcb", ".kicad_pro")
            open(donor_board, "w", encoding="utf-8").close()
            open(output_board, "w", encoding="utf-8").close()
            with open(donor_pro, "w", encoding="utf-8") as sink:
                json.dump({
                    "net_settings": {
                        "classes": [
                            {"name": "Default", "track_width": 0.2},
                            {"name": "Power", "track_width": 0.5},
                        ],
                        "netclass_patterns": [
                            {"pattern": "/VBUS", "netclass": "Power"}],
                    },
                    "board": {"design_settings": {"rules": {
                        "min_clearance": 0.15}}},
                }, sink)
            with open(output_pro, "w", encoding="utf-8") as sink:
                json.dump({"meta": {"filename": "stale.kicad_pro"},
                           "net_settings": {"classes": [
                               {"name": "Default", "track_width": 0.2}],
                               "netclass_patterns": []}}, sink)

            report = synth._carry_project_rule_authority(
                SimpleNamespace(board="not-a-real-board", pcb=donor_board),
                output_board)
            self.assertTrue(report["carried"], report)
            with open(output_pro, encoding="utf-8") as source:
                carried = json.load(source)
            self.assertEqual("wave.kicad_pro", carried["meta"]["filename"])
            self.assertEqual(2, len(carried["net_settings"]["classes"]))
            self.assertEqual(
                [{"pattern": "/VBUS", "netclass": "Power"}],
                carried["net_settings"]["netclass_patterns"])
            self.assertEqual(
                0.15, carried["board"]["design_settings"]["rules"][
                    "min_clearance"])


if __name__ == "__main__":
    unittest.main()
