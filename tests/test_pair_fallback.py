#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import cec_pair_fallback as fallback


class AtomicPairFallbackTest(unittest.TestCase):
    def _run(self, directory, *, gate_side_effect):
        source = os.path.join(directory, "source.kicad_pcb")
        open(source, "w", encoding="utf-8").close()
        with (mock.patch.object(
                  fallback.cec_staged_fr, "route_tiered",
                  return_value={"tiers": [{"completed_nets": ["P", "N"]}]})
              as staged,
              mock.patch.object(fallback.cec_fr, "copy_project_sidecars"),
              mock.patch.object(
                  fallback.cec_pair_return, "synthesize",
                  return_value={"ok": True, "generated_items": []}),
              mock.patch.object(
                  fallback.cec_constraints, "high_speed_pair_summary",
                  side_effect=gate_side_effect) as gate):
            report = fallback.route_atomic_pairs(
                source, directory, tier_groups=[["P", "N"]],
                pre_locked_nets={"LOCKED"}, seed=7, verbose=False)
        return report, staged, gate

    def test_first_physics_clean_candidate_is_published(self):
        with tempfile.TemporaryDirectory() as directory:
            report, staged, gate = self._run(
                directory, gate_side_effect=[{"ok": True, "violations": []}])
        self.assertTrue(report["ok"])
        self.assertEqual(report["selected_seed"], 7)
        self.assertEqual(len(report["attempts"]), 1)
        self.assertTrue(report["attempts"][0]["accepted"])
        self.assertEqual(staged.call_count, 1)
        self.assertEqual(gate.call_count, 1)

    def test_pair_physics_refusal_search_is_bounded_and_deterministic(self):
        failures = [
            {"ok": False, "violations": ["uncoupled"]},
            {"ok": False, "violations": ["unmatched transitions"]},
            {"ok": True, "violations": []},
        ]
        with tempfile.TemporaryDirectory() as directory:
            report, staged, _gate = self._run(
                directory, gate_side_effect=failures)
        self.assertTrue(report["ok"])
        self.assertEqual(report["selected_seed"], 209766)
        self.assertEqual(staged.call_count, 3)
        self.assertEqual(
            [row["accepted"] for row in report["attempts"]],
            [False, False, True])

    def test_three_refusals_fail_closed_without_selected_board(self):
        with tempfile.TemporaryDirectory() as directory:
            report, staged, _gate = self._run(
                directory,
                gate_side_effect=[{"ok": False, "violations": ["bad"]}] * 3)
        self.assertFalse(report["ok"])
        self.assertIsNone(report["board"])
        self.assertEqual(staged.call_count, 3)
        self.assertEqual(len(report["attempts"]), 3)


if __name__ == "__main__":
    unittest.main()
