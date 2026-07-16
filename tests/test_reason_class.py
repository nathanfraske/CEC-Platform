"""Host tests for the refute reason-class counter (CL-24 lesson 1). No GPU, no container -- pure
detector over synthetic verdict records shaped like cec_verifier.VERDICT_SCHEMA."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import cec_reason_class as rc  # noqa: E402


def _v(round, failure_class, verdict="refute", charter="actuation-space", reason="r"):
    return {"round": round, "charter": charter, "verdict": verdict,
            "failure_class": failure_class, "reason": reason}


class TestClassSetMatchesSchema(unittest.TestCase):
    def test_classes_match_verifier_schema(self):
        # the source of truth is cec_verifier; this module mirrors it and must not drift
        import cec_verifier
        enum = cec_verifier.VERDICT_SCHEMA["properties"]["failure_class"]["enum"]
        self.assertEqual(tuple(enum), rc.REFUTE_CLASSES,
                         "REFUTE_CLASSES drifted from cec_verifier.VERDICT_SCHEMA")


class TestRecurringDetection(unittest.TestCase):
    def test_same_class_two_rounds_is_flagged(self):
        # lesson 5 made visible: max_T (scoring) refuted R1, thrashed back R3 -> recurs
        recs = [_v(1, "scoring"), _v(2, "routing"), _v(3, "scoring")]
        flags = rc.recurring(recs, min_rounds=2)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["failure_class"], "scoring")
        self.assertEqual(flags[0]["rounds"], [1, 3])
        self.assertEqual(flags[0]["n_rounds"], 2)

    def test_distinct_class_each_round_not_flagged(self):
        recs = [_v(1, "scoring"), _v(2, "routing"), _v(3, "placement")]
        self.assertEqual(rc.recurring(recs, min_rounds=2), [])

    def test_same_class_same_round_counts_once(self):
        # two refutes of the same class within ONE round is not "across rounds"
        recs = [_v(1, "evidence"), _v(1, "evidence")]
        self.assertEqual(rc.recurring(recs, min_rounds=2), [])
        # but the tally still records the single round
        t = rc.tally(recs)
        self.assertEqual(t[("actuation-space", "evidence")]["rounds"], [1])

    def test_supports_and_uncertains_ignored(self):
        recs = [_v(1, "scoring", verdict="support"), _v(2, "scoring", verdict="uncertain"),
                _v(3, "scoring", verdict="refute")]
        # only one refute -> not recurring
        self.assertEqual(rc.recurring(recs, min_rounds=2), [])
        self.assertEqual(rc.report(recs)["n_refute_events"], 1)


class TestCharterKeying(unittest.TestCase):
    def test_same_class_different_charters_not_folded_by_default(self):
        recs = [_v(1, "scoring", charter="actuation-space"),
                _v(2, "scoring", charter="evidence-provenance")]
        # per-charter: each charter saw the class once -> no recurrence
        self.assertEqual(rc.recurring(recs, min_rounds=2, by_charter=True), [])
        # folded across charters: the class recurs across 2 rounds -> flagged
        folded = rc.recurring(recs, min_rounds=2, by_charter=False)
        self.assertEqual(len(folded), 1)
        self.assertIsNone(folded[0]["charter"])
        self.assertEqual(folded[0]["rounds"], [1, 2])

    def test_one_charter_recurs_across_rounds(self):
        recs = [_v(1, "constraint", charter="spec-conformance"),
                _v(2, "constraint", charter="spec-conformance"),
                _v(3, "routing", charter="spec-conformance")]
        flags = rc.recurring(recs, min_rounds=2, by_charter=True)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["charter"], "spec-conformance")
        self.assertEqual(flags[0]["failure_class"], "constraint")


class TestNormalization(unittest.TestCase):
    def test_unknown_or_absent_class_buckets_to_unknown(self):
        recs = [_v(1, "bogus-class"), _v(2, None)]
        ev = rc.events_from_records(recs)
        self.assertEqual([e["failure_class"] for e in ev], ["unknown", "unknown"])
        # and they recur as 'unknown' across 2 rounds
        self.assertEqual(rc.recurring(recs, min_rounds=2)[0]["failure_class"], "unknown")

    def test_roundless_refute_dropped(self):
        recs = [{"charter": "x", "verdict": "refute", "failure_class": "routing"}]  # no round
        self.assertEqual(rc.events_from_records(recs), [])

    def test_case_insensitive_verdict_and_class(self):
        recs = [_v(1, "Routing", verdict="REFUTE"), _v(2, "ROUTING", verdict="Refute")]
        flags = rc.recurring(recs, min_rounds=2)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["failure_class"], "routing")


class TestReportShape(unittest.TestCase):
    def test_report_verdict_strings(self):
        clean = rc.report([_v(1, "scoring"), _v(2, "routing")])
        self.assertTrue(clean["verdict"].startswith("clean"))
        flagged = rc.report([_v(1, "scoring"), _v(3, "scoring")])
        self.assertTrue(flagged["verdict"].startswith("FLAG"))
        self.assertEqual(flagged["rounds_seen"], [1, 3])


if __name__ == "__main__":
    unittest.main()
