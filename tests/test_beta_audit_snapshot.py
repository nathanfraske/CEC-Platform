#!/usr/bin/env python3
"""Prevent the Standard-main prose audit from drifting behind live source."""
import json
import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_beta_electrical_audit as audit  # noqa: E402
import cec_beta_manifest as manifest  # noqa: E402


SNAPSHOT = os.path.join(
    ROOT, "docs", "current-beta-standard-main-board-component-audit-2026-08-12.json")
DOCUMENT = os.path.join(
    ROOT, "docs", "current-beta-standard-main-board-component-audit-2026-08-10.md")


class TestBetaAuditSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SNAPSHOT, encoding="utf-8") as handle:
            cls.snapshot = json.load(handle)
        with open(DOCUMENT, encoding="utf-8") as handle:
            cls.document = handle.read()

    def test_snapshot_uses_manifest_owned_six_board_scope(self):
        self.assertEqual(self.snapshot["scope"], "standard-main")
        self.assertEqual(
            set(self.snapshot["scope_boards"]), set(manifest.STANDARD_MAIN_BOARDS))
        self.assertEqual(self.snapshot["projects"], 6)
        self.assertIn("hub-standard-rev2", self.snapshot["scope_boards"])

    def test_snapshot_matches_live_schematic_and_audit_logic_hashes(self):
        implementation_sha256, files = audit._implementation_digest()
        self.assertEqual(
            self.snapshot["audit_implementation_sha256"], implementation_sha256,
            "regenerate the Standard-main JSON snapshot after audit-logic changes")
        self.assertEqual(self.snapshot["audit_implementation_files"], files)
        for board in manifest.STANDARD_MAIN_BOARDS:
            project = manifest.BY_BOARD[board]
            schematic = os.path.join(
                ROOT, "beta", project["directory"], project["schematic"])
            inventory = audit.cec_sch_gates.inventory(schematic)
            digest, source_files = audit._source_digest(schematic, inventory)
            self.assertEqual(
                self.snapshot["boards"][board]["source_sha256"], digest,
                f"regenerate the Standard-main JSON snapshot after changing {board}")
            self.assertEqual(
                self.snapshot["boards"][board]["source_files"], source_files)

    def test_document_names_every_manifest_board_and_no_stale_open_rows(self):
        for board in manifest.STANDARD_MAIN_BOARDS:
            project = manifest.BY_BOARD[board]
            expected = f"beta/{project['directory']}/{project['schematic']}"
            self.assertIn(expected, self.document)
        self.assertNotIn("| ELEC-06 |", self.document)
        self.assertNotIn("| ELEC-11 |", self.document)
        self.assertNotIn("| ELEC-01 |", self.document)
        self.assertNotIn("| ELEC-03 |", self.document)
        self.assertNotIn("| ELEC-04 |", self.document)
        self.assertIn("ELEC-01 on EPS is fixed", self.document)
        self.assertIn("ELEC-03 on EPS is fixed", self.document)
        self.assertIn("ELEC-04 on 12VHPWR is fixed", self.document)
        self.assertIn("ELEC-06 is fixed", self.document)
        self.assertIn("ELEC-11 is fixed", self.document)

    def test_snapshot_has_no_source_level_blockers(self):
        self.assertEqual(self.snapshot["summary"].get("BLOCKER", 0), 0)


if __name__ == "__main__":
    unittest.main()
