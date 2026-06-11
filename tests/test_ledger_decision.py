#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Unit tests for the cec_ledger DF-01/DF-06 decision-capture schema, PC-01 capture
# criterion, DF-07 settlement/label, and AM-06 counter sharding. Points the ledger at a
# temp CEC_RUNS_DIR so it writes to a throwaway tree -- no real cec-runs repo touched.
#
#   python3 -m unittest tests.test_ledger_decision -v
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import cec_ledger as L  # noqa: E402


class _TmpLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cec-runs-test-")
        self._old = os.environ.get("CEC_RUNS_DIR")
        os.environ["CEC_RUNS_DIR"] = self.tmp

    def tearDown(self):
        if self._old is None:
            os.environ.pop("CEC_RUNS_DIR", None)
        else:
            os.environ["CEC_RUNS_DIR"] = self._old


class TestDecisionCapture(_TmpLedger):
    def test_settleable_decision_is_full(self):
        rec = L.decision(
            decision_class="finding",
            artifact="cand-abc123",
            decider={"kind": "model", "id": "cec-worker", "manifest": {"quant": "UD-Q4_K_M"}},
            verdict="defect",
            claim="SENSEC2_LO kelvin tap is stranded on an inner layer",
            hook={"kind": "check_id", "ref": "kelvin-sense-from-inner-pad"},
        )
        self.assertTrue(rec["settleable"])
        self.assertEqual(rec["capture"], "full")
        self.assertEqual(rec["settlement"], {"state": "open", "grade": None})
        # persisted
        recs = L.read_decisions()
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["decision_id"], rec["decision_id"])

    def test_claim_without_hook_scores_zero(self):
        """DF-06: a claim with no verification hook is legal but NOT settleable (reward-neutral)."""
        rec = L.decision(
            decision_class="finding", artifact="cand-x",
            decider={"kind": "model", "id": "cec-worker"},
            verdict="maybe", claim="something looks off", hook=None,
        )
        self.assertFalse(rec["settleable"])
        self.assertEqual(rec["capture"], "counter-eligible")

    def test_claimless_decision_is_counter_eligible(self):
        rec = L.decision(
            decision_class="allocate", artifact="R-night-1",
            decider={"kind": "model", "id": "orchestrator"}, verdict="seeds=8",
        )
        self.assertFalse(rec["settleable"])
        self.assertEqual(rec["capture"], "counter-eligible")

    def test_bad_class_rejected(self):
        with self.assertRaises(ValueError):
            L.decision(decision_class="not-a-class", artifact="x",
                       decider={"kind": "human", "id": "o"}, verdict="v")

    def test_bad_hook_kind_rejected(self):
        with self.assertRaises(ValueError):
            L.decision(decision_class="finding", artifact="x",
                       decider={"kind": "model", "id": "w"}, verdict="v",
                       claim="c", hook={"kind": "vibes", "ref": "r"})

    def test_bad_settlement_state_rejected(self):
        with self.assertRaises(ValueError):
            L.decision(decision_class="accept", artifact="x",
                       decider={"kind": "human", "id": "o"}, verdict="v",
                       settlement={"state": "totally-done", "grade": 1})


class TestSettlementAndLabel(_TmpLedger):
    def test_settle_appends_not_edits(self):
        d = L.decision(decision_class="promote", artifact="entry-foo",
                       decider={"kind": "human", "id": "nathanfraske"}, verdict="promote",
                       claim="entry-foo gates the REF3030 swap",
                       hook={"kind": "fixture", "ref": "tests/golden/hub-pre"})
        s = L.settle(d["decision_id"], state="settled", grade=2, evidence="golden fired")
        recs = L.read_decisions()
        self.assertEqual(len(recs), 2)  # original + settlement, append-only
        self.assertEqual(s["settles"], d["decision_id"])
        self.assertEqual(s["settlement"], {"state": "settled", "grade": 2})

    def test_label_is_grade1(self):
        d = L.decision(decision_class="accept", artifact="cand-y",
                       decider={"kind": "model", "id": "cec-judge"}, verdict="accept",
                       claim="board passes at 600W balanced", hook={"kind": "bench", "ref": "fem-probe"})
        # CLI label path: physical outcome -> grade-1 settle
        rc = L.main(["label", d["decision_id"], "--outcome", "vindicated", "--evidence", "bench run 7"])
        self.assertEqual(rc, 0)
        settle_recs = [r for r in L.read_decisions() if r.get("settles") == d["decision_id"]]
        self.assertEqual(len(settle_recs), 1)
        self.assertEqual(settle_recs[0]["settlement"], {"state": "settled", "grade": 1})


class TestCounters(_TmpLedger):
    def test_counter_streams_to_sidecar(self):
        L.counter("bandit_draws", "route_seeds=8", n=3, board="eps-8pin")
        p = os.path.join(self.tmp, "decisions", "counters", "bandit_draws.jsonl")
        self.assertTrue(os.path.isfile(p))
        line = json.loads(open(p).read().strip())
        self.assertEqual(line["n"], 3)
        self.assertEqual(line["key"], "route_seeds=8")
        # counters do NOT pollute the main decision stream (AM-06 single-writer per stream)
        self.assertEqual(L.read_decisions(), [])


if __name__ == "__main__":
    unittest.main()
