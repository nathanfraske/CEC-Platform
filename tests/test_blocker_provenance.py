import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import cec_blocker_provenance as provenance


class BlockerProvenanceTests(unittest.TestCase):
    def test_final_drc_does_not_claim_pipeline_origin(self):
        blockers = provenance.final_blockers({
            "violations": [{
                "type": "clearance",
                "description": "clearance violation",
                "items": [{
                    "uuid": "track-1",
                    "description": "Track [+5V_SYS] of C15",
                    "pos": {"x": 10.0, "y": 20.0},
                }, {
                    "uuid": "via-2",
                    "description": "Via [GND]",
                    "pos": {"x": 10.2, "y": 20.0},
                }],
            }],
            "unconnected_items": [],
        })
        self.assertEqual(len(blockers), 1)
        self.assertFalse(blockers[0]["origin_known"])
        self.assertEqual(
            blockers[0]["causal_chain"][-1]["certainty"], "observed")
        self.assertEqual(
            provenance.compact_summary(blockers)["full_fail_stack"], False)

    def test_exact_uuid_attributes_stage_but_net_only_is_association(self):
        blockers = provenance.final_blockers({
            "violations": [],
            "unconnected_items": [{
                "type": "unconnected_items",
                "items": [{
                    "uuid": "track-1",
                    "description": "Track [/USB_D_P] of U1",
                }],
            }],
        })
        net_event = provenance.normalize_event(
            "placement_preflight", "failed", "blocked endpoint",
            nets=["/USB_D_P"], refs=["U1"])
        joined = provenance.join_events(blockers, [net_event])
        self.assertFalse(joined[0]["origin_known"])
        self.assertEqual(
            joined[0]["causal_chain"][0]["certainty"], "associated")

        owner_event = provenance.normalize_event(
            "precision_route", "passed", "generated trace",
            uuids=["track-1"], nets=["/USB_D_P"])
        joined = provenance.join_events(blockers, [owner_event])
        self.assertTrue(joined[0]["origin_known"])
        self.assertEqual(
            joined[0]["causal_chain"][0]["certainty"], "attributed")
        self.assertTrue(
            provenance.compact_summary(joined)["full_fail_stack"])

    def test_large_stage_detail_is_referenced_instead_of_duplicated(self):
        blockers = provenance.final_blockers({
            "violations": [],
            "unconnected_items": [{
                "type": "unconnected_items",
                "items": [{
                    "uuid": "track-1",
                    "description": "Track [/USB_D_P] of U1",
                }],
            }],
        })
        event = provenance.normalize_event(
            "detailed_route_completion", "refused", "bounded search failed",
            uuids=["track-1"], detail={"certificate": "x" * 5000})
        joined = provenance.join_events(blockers, [event])
        attached = joined[0]["causal_chain"][0]
        self.assertNotIn("detail", attached)
        self.assertEqual(attached["detail_ref"]["scope"], "stage_trace")
        self.assertEqual(attached["detail_ref"]["index"], 0)
        self.assertGreater(attached["detail_ref"]["bytes"], 5000)
        self.assertIn("detail", event)

    def test_fail_closed_run_has_last_stage_chain(self):
        trace = [provenance.normalize_event(
            "precision_route", "passed", "pair refused to fallback"),
                 provenance.normalize_event(
                     "critical_pair_fallback", "failed",
                     "coupled coverage below limit")]
        blocker = provenance.failure_blocker(trace, "fallback failed")
        self.assertEqual(blocker["rule"], "critical_pair_fallback")
        self.assertTrue(blocker["origin_known"])
        self.assertEqual(len(blocker["causal_chain"]), 2)

    def test_stage_owned_non_drc_observation_is_attributed(self):
        blocker = provenance.observed_blocker(
            "thermal_injection", "current_injection_complete",
            "one source was dropped", authority="cec_thermal2d")
        self.assertTrue(blocker["origin_known"])
        self.assertEqual(
            blocker["causal_chain"][0]["certainty"], "attributed")

    def test_advisory_does_not_count_as_blocking_fail_stack(self):
        blockers = provenance.final_blockers(
            {"violations": [], "unconnected_items": []},
            topology={"issues": [{
                "kind": "odd_angle", "severity": "advisory",
                "message": "ordinary route angle", "net": "GPIO",
                "track_uuids": ["track-a"], "at_mm": [1.0, 2.0],
            }]})
        summary = provenance.compact_summary(blockers)
        self.assertEqual(summary["blocking_count"], 0)
        self.assertEqual(summary["advisory_count"], 1)
        self.assertFalse(summary["full_fail_stack"])


if __name__ == "__main__":
    unittest.main()
