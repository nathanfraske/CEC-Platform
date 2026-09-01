"""Detailed-route refusals must steer generic placement neighborhoods."""

import os
import sys
import unittest
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_completion_evidence as evidence  # noqa: E402


def _completion():
    certificate = {
        "schema": 1, "net": "/CTRL", "endpoints": [
            {"endpoint": "a", "kind": "pad", "ref": "R1", "pad": "1",
             "x_mm": 10.0, "y_mm": 20.0},
            {"endpoint": "b", "kind": "trk", "x_mm": 12.0, "y_mm": 20.0}],
        "layers": [{"layer": "F.Cu", "endpoint_escape": [
            {"endpoint": "a", "clear_rays": ["E", "NE"]}]}],
        "dominant_blockers": [
            {"kind": "pad", "ref": "C9", "pad": "1", "hit_count": 3},
            {"kind": "track", "uuid": "track-only", "hit_count": 20}],
    }
    detail = {"net": "/CTRL", "distance_mm": 2.0,
              "certificate": certificate}
    return {"best": {"completion_report": {
        "lastmile": {"refused_details": [detail]},
        "final_completion": {"refused_details": [detail]}}}}


class CompletionEvidenceTest(unittest.TestCase):
    def test_deduplicates_and_names_endpoint_and_pad_blocker(self):
        result = evidence.placement_hints(_completion())
        self.assertEqual(result["certificate_count"], 1)
        by_ref = {row["ref"]: row for row in result["hints"]}
        self.assertEqual(set(by_ref), {"R1", "C9"})
        self.assertEqual(by_ref["R1"]["role"], "refused_endpoint")
        self.assertEqual(by_ref["R1"]["directions"], ["E", "NE"])
        self.assertEqual(by_ref["C9"]["anchors"], [[11.0, 20.0]])

    def test_critical_refusal_outranks_noncritical(self):
        result = evidence.placement_hints(
            _completion(), critical_nets=("CTRL",))
        self.assertGreater(result["hints"][0]["score"], 1000000)

    def test_augmentation_does_not_mutate_baseline(self):
        baseline = {"gate": False, "nested": {"x": 1}}
        augmented = evidence.augment_placement_evidence(
            baseline, _completion())
        augmented["nested"]["x"] = 2
        self.assertEqual(baseline["nested"]["x"], 1)
        self.assertEqual(augmented["completion_evidence"]["hint_count"], 2)

    def test_power_authority_failure_enters_placement_power_evidence(self):
        failure = {
            "path_found": False,
            "planner_reason": "terminal field incomplete",
            "planner_bottleneck": {
                "kind": "via_field_access", "net": "/RAIL",
                "fields": [{
                    "field_index": 0, "centre_mm": [10.0, 20.0],
                    "minimum": 4, "placed": 1,
                    "terminal_refs": ["J1"],
                    "nearest_pad_obstacles": [{
                        "owner": "C1", "pad": "1", "fixed": False,
                        "distance_mm": 1.0,
                    }],
                }],
            },
        }
        completion = {"candidates": [{"compile_failure": {
            "report": {"/RAIL": failure},
        }}]}
        baseline = {"power_body_clearance": {
            "planner_failures": {"/OLD": {
                "planner_bottleneck": {"kind": "corridor", "net": "/OLD"},
            }},
        }}

        augmented = evidence.augment_placement_evidence(
            baseline, completion)

        failures = augmented["power_body_clearance"]["planner_failures"]
        self.assertEqual(set(failures), {"/OLD", "/RAIL"})
        self.assertEqual(
            failures["/RAIL"]["planner_bottleneck"]["kind"],
            "via_field_access")
        self.assertEqual(
            augmented["completion_evidence"]
            ["power_planner_failure_nets"], ["/RAIL"])
        self.assertNotIn("error", baseline["power_body_clearance"])

    def test_projected_hints_enter_general_placement_move_ladder(self):
        import cec_synth_pipeline as pipeline

        baseline = evidence.augment_placement_evidence({}, _completion())
        candidate = SimpleNamespace(P={
            "R1": (10.0, 20.0, 0.0),
            "C9": (13.0, 20.0, 90.0),
            "J1": (0.0, 0.0, 0.0)})
        cfg = SimpleNamespace(pins={})
        moves = pipeline._route_access_move_specs(
            candidate, baseline, cfg, shift_mm=(0.5,))
        self.assertEqual(moves[0]["ref"], "R1")
        self.assertTrue(any(
            row["ref"] == "R1"
            and row["kind"] == "completion_escape_shift"
            for row in moves))
        self.assertTrue(any(
            row["ref"] == "C9"
            and row["kind"] == "completion_blocker_relief"
            for row in moves))
        self.assertFalse(any(row["ref"] == "J1" for row in moves))

    def test_coarse_blocked_pad_does_not_suppress_completion_hints(self):
        """Independent late-router evidence survives an ordinary access warning."""
        import cec_synth_pipeline as pipeline

        baseline = evidence.augment_placement_evidence({
            "pin_access_blocked": [{
                "ref": "U4", "critical": False,
                "blocked_options": [],
            }],
        }, _completion())
        candidate = SimpleNamespace(P={
            "U4": (4.0, 4.0, 0.0),
            "R1": (10.0, 20.0, 0.0),
            "C9": (13.0, 20.0, 90.0),
        })
        cfg = SimpleNamespace(pins={}, params={
            "placement_completion_ref_limit": 4})
        moves = pipeline._route_access_move_specs(
            candidate, baseline, cfg, shift_mm=(0.5,))

        self.assertTrue(any(
            row["ref"] == "R1"
            and row["kind"] == "completion_escape_shift"
            for row in moves))
        self.assertTrue(any(
            row["ref"] == "C9"
            and row["kind"] == "completion_blocker_relief"
            for row in moves))


if __name__ == "__main__":
    unittest.main()
