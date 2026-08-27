"""Plateau allocation must switch families and terminate without looping."""

import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_search_policy as policy  # noqa: E402


class SearchPolicyTest(unittest.TestCase):
    CONFIG = {"enabled": True, "step_mm": 2, "max_steps": 2}

    def test_patience_keeps_seed_diversity(self):
        action = policy.next_action(
            plateau_streak=2, patience=3, nominal_outline=(80, 60),
            outline_policy=self.CONFIG)
        self.assertEqual(action["family"], "seed_diversity")

    def test_plateau_uses_completion_then_each_compact_outline(self):
        first = policy.next_action(
            plateau_streak=3, patience=3, completion_available=True,
            nominal_outline=(80, 60), outline_policy=self.CONFIG)
        self.assertEqual(first["family"], "completion_repair")
        second = policy.next_action(
            plateau_streak=4, patience=3, completion_available=True,
            used_families={first["family"]}, nominal_outline=(80, 60),
            outline_policy=self.CONFIG)
        self.assertEqual(second["outline"], [76.0, 56.0])

    def test_exhausted_families_stop(self):
        used = {"completion_repair", "outline_76x56", "outline_78x58",
                "broaden_shortlist", "precision_effort"}
        action = policy.next_action(
            plateau_streak=20, patience=3, completion_available=True,
            used_families=used, nominal_outline=(80, 60),
            outline_policy=self.CONFIG)
        self.assertTrue(action["stop"])

    def test_unattended_budget_is_explicit_and_hard_capped(self):
        self.assertEqual(policy.bounded_round_budget(12), 12)
        with self.assertRaises(ValueError):
            policy.bounded_round_budget(0)
        with self.assertRaises(ValueError):
            policy.bounded_round_budget(33)

    def test_only_canonical_admission_counts_as_loop_progress(self):
        before = {
            "source": "candidate-a.kicad_pcb", "updated": "t1",
            "sort_key": [1, 12, 3], "route_gate_passed": False,
        }
        # A wave may have a locally attractive score, but a rejected publish
        # leaves the canonical record untouched and is a plateau.
        rejected = policy.incumbent_transition(
            before, dict(before), declared_updated=False)
        self.assertFalse(rejected["accepted"])
        self.assertTrue(rejected["consistent"])

        after = {
            "source": "candidate-b.kicad_pcb", "updated": "t2",
            "sort_key": [1, 8, 2], "route_gate_passed": False,
            "reason": "sort key improved",
        }
        accepted = policy.incumbent_transition(
            before, after, declared_updated=True)
        self.assertTrue(accepted["accepted"])
        self.assertTrue(accepted["score_improved"])

    def test_incumbent_lineage_mismatch_is_not_progress(self):
        before = {"source": "a", "updated": "t1", "sort_key": [2]}
        after = {"source": "b", "updated": "t2", "sort_key": [1]}
        result = policy.incumbent_transition(
            before, after, declared_updated=False)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["consistent"])

    def test_candidate_rank_accepts_exact_critical_net_lists(self):
        ranked = policy.candidate_rank({
            "gate": False, "sort_key": [1, 2],
            "unconn_critical": ["/RESET", "/INTERLOCK"],
            "drc": 1, "unconnected": 20, "seed": 7,
        })
        self.assertEqual(ranked[-5:], (2, 1, 20, 0, 7))


if __name__ == "__main__":
    unittest.main()
