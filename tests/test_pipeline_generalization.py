#!/usr/bin/env python3
"""The reusable engine must remain product-identity free."""

import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_generalization_gate as gate  # noqa: E402


class PipelineGeneralizationGateTest(unittest.TestCase):
    def test_generic_engine_contains_no_product_or_refdes_selectors(self):
        report = gate.audit(ROOT)
        self.assertTrue(report["ok"], report["violations"])
        self.assertEqual(
            set(report["checked_modules"]),
            set(gate.GENERIC_ENGINE_MODULES))


class BoundedRouteSearchTest(unittest.TestCase):
    def setUp(self):
        import cec_search_policy
        self.policy = cec_search_policy

    def test_seed_budget_is_finite_and_capped(self):
        self.assertEqual(
            self.policy.bounded_seed_plan(10, 4), (10, 11, 12, 13))
        with self.assertRaisesRegex(ValueError, "hard cap"):
            self.policy.bounded_seed_plan(0, 9)

    def test_placement_strategy_product_is_finite_and_capped(self):
        self.assertEqual(
            self.policy.bounded_placement_plan(
                ("plain", "dataflow"), (0, 1)),
            (("plain", 0), ("plain", 1),
             ("dataflow", 0), ("dataflow", 1)))
        with self.assertRaisesRegex(ValueError, "hard cap"):
            self.policy.bounded_placement_plan(
                ("plain", "dataflow", "thermal", "hybrid"),
                range(5))

    def test_candidate_selection_uses_release_objective(self):
        rows = [
            {"seed": 2, "routed": "a", "gate": False,
             "sort_key": [1, 0, 0], "drc": 0, "unconnected": 1},
            {"seed": 3, "routed": "b", "gate": True,
             "sort_key": [0, 9, 9], "drc": 0, "unconnected": 0},
        ]
        self.assertEqual(self.policy.select_candidate(rows)["seed"], 3)


if __name__ == "__main__":
    unittest.main()
