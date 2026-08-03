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

    def test_obsolete_eps_is_rejected_by_wave(self):
        import cec_fresh_wave
        with self.assertRaisesRegex(ValueError, "not a current"):
            cec_fresh_wave.run_board("eps-8pin", [0], 1, 1, "/tmp/no", "/tmp/no")


if __name__ == "__main__":
    unittest.main()
