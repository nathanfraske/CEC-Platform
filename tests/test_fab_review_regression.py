#!/usr/bin/env python3
"""Pure acceptance tests for archived fab-review replays."""

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import cec_fab_review_regression as regression  # noqa: E402


def _summary():
    return {
        "lineage": {"proposed": {"sha256": "abc"}},
        "gates": {
            "gates_pass": True,
            "drc": 0,
            "unconnected": 0,
            "kelvin_ok": True,
            "diffpair_ok": True,
        },
    }


def _probes():
    return {
        "score": {
            "gates_pass": True, "drc": 0, "unconnected": 0,
            "kelvin_ok": True, "diffpair_ok": True,
        },
        "constraints": {"ok": True},
        "route_quality": {"craft_ok": True},
        "fab": {"blocking_count": 0},
    }


class FabReviewComparisonTest(unittest.TestCase):
    def test_critical_route_selectors_include_derived_pairs(self):
        merged = regression.critical_route_selectors(
            ("/EXPLICIT", "/USB_D_P"),
            kelvin_pairs=(("/SENSE_HI", "/SENSE_LO"),),
            diff_pairs=(("/USB_D_P", "/USB_D_N"),))

        self.assertEqual(merged, (
            "/EXPLICIT", "/USB_D_P", "/SENSE_HI", "/SENSE_LO",
            "/USB_D_N"))

    def test_identical_clean_control_passes(self):
        result = regression.compare_to_baseline(
            _summary(), _probes(), "abc")
        self.assertTrue(result["ok"])
        self.assertEqual(result["failed_terms"], [])

    def test_new_unconnected_item_is_a_regression(self):
        probes = _probes()
        probes["score"]["unconnected"] = 1
        probes["score"]["gates_pass"] = False

        result = regression.compare_to_baseline(
            _summary(), probes, "abc")

        self.assertFalse(result["ok"])
        self.assertIn("connectivity_not_worse", result["failed_terms"])
        self.assertIn("score_gate_retained", result["failed_terms"])

    def test_mutated_control_is_not_silently_rebaselined(self):
        result = regression.compare_to_baseline(
            _summary(), _probes(), "different")
        self.assertFalse(result["ok"])
        self.assertIn("control_content_unchanged", result["failed_terms"])


if __name__ == "__main__":
    unittest.main()
