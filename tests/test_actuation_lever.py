#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Full actuation lever, Step 1 -- per-rule TRANSITIVE influence lineage + the clean-evidence
# comparator. Pure host tests (no pcbnew, no broker). The invariant under test: a rule may be
# scored ONLY on outcomes it did not influence, and the influence cone is transitive over the
# compounding placement_base lineage. See docs/actuation-lever-design.md.

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fullstack as fs           # noqa: E402  (lazy pcbnew/broker imports -- host-safe)


def _row(lane, influenced, **m):
    r = {"lane": lane, "influenced_by": influenced}
    r.update(m)
    return r


class TestRuleId(unittest.TestCase):
    def test_stable_and_kind_tagged(self):
        a = fs.rule_id("rule", "keep CAN off the edge")
        b = fs.rule_id("rule", "keep CAN off the edge")
        c = fs.rule_id("rule", "different rule")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertTrue(a.startswith("rule:"))
        self.assertTrue(fs.rule_id("penalty", {"metric": "drc", "w": 80.0}).startswith("penalty:"))

    def test_active_steer_ids_excludes_default_penalties(self):
        fresh = {"manager_rules": [], "scorer_penalties": dict(fs._DEFAULT_PENALTIES)}
        self.assertEqual(fs.active_steer_ids(fresh), [])
        lr = {"manager_rules": ["r1"], "scorer_penalties": {**fs._DEFAULT_PENALTIES, "drc": 90.0}}
        ids = fs.active_steer_ids(lr)
        self.assertTrue(any(i.startswith("rule:") for i in ids))
        self.assertTrue(any(i.startswith("penalty:") for i in ids))
        self.assertEqual(len(ids), 2)


class TestInfluenceCone(unittest.TestCase):
    def test_control_round_signature_is_empty(self):
        lr = {"manager_rules": ["r1"], "scorer_penalties": {**fs._DEFAULT_PENALTIES, "drc": 90.0}}
        # even with active steer in lr, a CONTROL round routes committed with a masked view -> clean
        self.assertEqual(fs.influence_signature(lr, "control", placement_id="placement:abc"), [])
        self.assertEqual(
            fs.row_influenced_by(lr, "control", ["placement:kept"], placement_id="placement:abc"), [])

    def test_augmented_signature_includes_this_rounds_steer(self):
        lr = {"manager_rules": ["r1"], "scorer_penalties": dict(fs._DEFAULT_PENALTIES)}
        sig = fs.influence_signature(lr, "augmented", placement_id="placement:p1", layer_id="layer:l1")
        self.assertIn("placement:p1", sig)
        self.assertIn("layer:l1", sig)
        self.assertTrue(any(i.startswith("rule:") for i in sig))

    def test_row_cone_is_transitive_union(self):
        lr = {"manager_rules": [], "scorer_penalties": dict(fs._DEFAULT_PENALTIES)}
        kept = ["placement:keptA", "placement:keptB"]
        cone = fs.row_influenced_by(lr, "augmented", kept, placement_id="placement:inflight")
        self.assertTrue(set(kept).issubset(set(cone)))   # inherits the kept lineage
        self.assertIn("placement:inflight", cone)        # plus this round's in-flight move


class TestCleanEvidenceFirewall(unittest.TestCase):
    def test_firewall_excludes_influenced_rows_from_baseline(self):
        R = "placement:R"
        rows = [
            _row("control", [], drc=20),                 # clean baseline
            _row("augmented", [R], drc=10),              # treatment (R influenced)
            _row("augmented", ["other:X"], drc=18),      # clean baseline (R absent from cone)
            _row("augmented", [R, "other:X"], drc=11),   # treatment (R in a transitive cone)
        ]
        part = fs.clean_pairs(rows, R)
        self.assertEqual(len(part["treatment"]), 2)
        self.assertEqual(len(part["baseline"]), 2)
        self.assertTrue(all(R not in (b.get("influenced_by") or []) for b in part["baseline"]))
        self.assertTrue(all(R in t["influenced_by"] for t in part["treatment"]))

    def test_clean_evidence_delta_uses_only_clean_baseline(self):
        R = "penalty:R"
        rows = [_row("control", [], drc=20), _row("control", [], drc=20),
                _row("augmented", [R], drc=10), _row("augmented", [R], drc=12)]
        d = fs.clean_evidence_delta(rows, R, "drc")
        self.assertEqual((d["n_baseline"], d["n_treatment"]), (2, 2))
        self.assertEqual(d["baseline_mean"], 20.0)
        self.assertEqual(d["treatment_mean"], 11.0)
        self.assertEqual(d["delta"], -9.0)               # drc dropped 9 on clean evidence

    def test_delta_none_when_an_arm_is_empty(self):
        R = "rule:R"
        rows = [_row("augmented", [R], drc=10), _row("augmented", [R], drc=11)]   # no clean baseline
        d = fs.clean_evidence_delta(rows, R, "drc")
        self.assertIsNone(d["delta"])
        self.assertEqual((d["n_baseline"], d["n_treatment"]), (0, 2))

    def test_a_rule_can_never_be_its_own_baseline(self):
        R = "placement:R"
        rows = [_row("augmented", [R], drc=10), _row("control", [], drc=20),
                _row("augmented", [R, "x:1"], drc=9)]
        part = fs.clean_pairs(rows, R)
        self.assertTrue({id(t) for t in part["treatment"]}.isdisjoint({id(b) for b in part["baseline"]}))


if __name__ == "__main__":
    unittest.main()
