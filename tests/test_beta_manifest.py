#!/usr/bin/env python3
"""Regression gates for the one-source current BETA product set."""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_beta_manifest as manifest  # noqa: E402
import cec_beta_electrical_audit as audit  # noqa: E402
import cec_sch_layout as sch_layout  # noqa: E402


class TestCurrentBetaManifest(unittest.TestCase):
    def test_manifest_is_complete_and_has_one_eps(self):
        self.assertEqual(manifest.validate(ROOT), [])
        eps = [board for board in manifest.CURRENT_BETA_BOARDS
               if os.path.basename(board).startswith("eps-8pin")]
        self.assertEqual(eps, ["eps-8pin-rev3"])
        self.assertFalse(os.path.exists(os.path.join(ROOT, "beta", "eps-8pin")))

    def test_audit_discovery_is_exactly_the_manifest(self):
        found = audit.discover_projects(os.path.join(ROOT, "beta"))
        self.assertEqual([board for board, _directory, _schematic in found],
                         list(manifest.CURRENT_BETA_BOARDS))
        self.assertFalse(any("candidate" in schematic or "old-revisions" in schematic
                             for _board, _directory, schematic in found))

    def test_large_current_roots_are_functional_hierarchies(self):
        roots = {
            "hub-standard-rev2": 6,
            "eps-8pin-rev3": 5,
            "atx-24pin-rev3": 5,
        }
        for board, expected in roots.items():
            project = manifest.BY_BOARD[board]
            path = os.path.join(ROOT, "beta", project["directory"],
                                project["schematic"])
            text = open(path, encoding="utf-8").read()
            files = re.findall(r'\(property "Sheetfile" "([^"]+)"', text)
            self.assertEqual(len(files), expected, board)
            self.assertEqual(len(files), len(set(files)), board)
            self.assertTrue(all(os.path.isfile(os.path.join(os.path.dirname(path), f))
                                for f in files), board)

    def test_generated_leaves_are_review_scale_and_visibly_clear(self):
        """The hierarchy generator must prove readability, not merely fit.

        A3 is the largest accepted leaf: at the dashboard's 2048 px review
        width, its 1.0 mm engineering notes remain about 4.9 px high and the
        standard 1.27 mm labels about 6.2 px.  We also check the actual text
        geometry, including pin names/numbers, and require every symbol field
        to render horizontally after the symbol's rotation is applied.
        """
        roots = ("hub-standard-rev2", "eps-8pin-rev3", "atx-24pin-rev3")
        paper_width = {"A4": 297.0, "A3": 420.0}
        for board in roots:
            project = manifest.BY_BOARD[board]
            directory = os.path.join(ROOT, "beta", project["directory"])
            root = os.path.join(directory, project["schematic"])
            root_text = open(root, encoding="utf-8").read()
            leaves = re.findall(r'\(property "Sheetfile" "([^"]+)"', root_text)
            for leaf in leaves:
                path = os.path.join(directory, leaf)
                text = open(path, encoding="utf-8").read()
                paper = re.search(r'\(paper "([^"]+)"\)', text).group(1)
                self.assertIn(paper, paper_width, f"{board}/{leaf} exceeds review scale")
                elements = sch_layout._extract_text_elements(text)
                visible_min_mm = min(element["size"] for element in elements)
                effective_px = visible_min_mm * 2048.0 / paper_width[paper]
                self.assertGreaterEqual(effective_px, 4.8, f"{board}/{leaf}")
                self.assertEqual(sch_layout.detect_overlaps(path), [], f"{board}/{leaf}")
                bad_fields = [element for element in elements
                              if element["kind"] == "property"
                              and round(element["render_ang"]) % 180]
                self.assertEqual(bad_fields, [], f"{board}/{leaf}")

    def test_obsolete_eps_is_rejected_by_wave(self):
        import cec_fresh_wave
        with self.assertRaisesRegex(ValueError, "not a current"):
            cec_fresh_wave.run_board("eps-8pin", [0], 1, 1, "/tmp/no", "/tmp/no")


if __name__ == "__main__":
    unittest.main()
