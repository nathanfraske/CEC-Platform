# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# CL-19 wave tests (rulings doc 2026-06-10, checklist items 1-7) -- all
# model-free: the live extractor runs in the pre-binding ritual (Ruling 4);
# these pin the MECHANICS the ritual relies on.
import json, os, sys, unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.dont_write_bytecode = True

import cec_extractor_eval as E                                # noqa: E402
import cec_span_verify as SV                                  # noqa: E402
import cec_verdict_core as VC                                 # noqa: E402


def _core(verdict="accept", basis=None, findings=None):
    return {"schema": VC.SCHEMA_ID,
            "subject": {"board": "b", "candidate_hash": "c", "run_id": "r"},
            "verdict": {"value": verdict, "basis_spans": basis or []},
            "findings": findings or [], "drafted_entry_refs": [], "confidence": 0.9}


class T1PerRegisterGate(unittest.TestCase):
    def test_no_real_cases_is_incomplete_never_pass(self):
        results = [{"id": "a", "register": "reconstructed", "kind": "standard",
                    "zt": [], "fields": {"verdict.value": True}}]
        rep = E._aggregate(results, "m", "p", E.EVAL_DIR)
        self.assertIn("INCOMPLETE", rep["gate"])

    def test_gate_computes_on_real_register_only(self):
        results = [
            {"id": "recon-bad", "register": "reconstructed", "kind": "standard",
             "zt": [{"class": "hallucinated-verdict"}], "fields": {}},
            {"id": "real-good", "register": "real", "kind": "standard",
             "zt": [], "fields": {"verdict.value": True, "findings.recall": 1.0}},
        ]
        rep = E._aggregate(results, "m", "p", E.EVAL_DIR)
        self.assertEqual(rep["gate"], "PASS",
                         "reconstructed-register failures must not gate")
        results[1]["zt"].append({"class": "span-not-found"})
        rep2 = E._aggregate(results, "m", "p", E.EVAL_DIR)
        self.assertEqual(rep2["gate"], "FAIL")

    def test_grade_field_present(self):
        rep = E._aggregate([], "m", "p", E.EVAL_DIR)
        self.assertEqual(rep["grade"], "smoke")


class T2Ratification(unittest.TestCase):
    def _case(self, kind, cid="cl19-rat-x-1"):
        return {"id": cid, "register": "reconstructed", "kind": kind,
                "trace": "## Conclusions\nThe widget is correct.",
                "gold_statement": "The widget is correct.",
                "distractor_statement": "The widget is incorrect."}

    def test_distractor_selected_fails(self):
        c = self._case("ratification-distractor")
        distractor_pick = "B" if E._gold_side(c["id"]) else "A"   # hash-based side
        with mock.patch.object(E, "_chat", return_value=distractor_pick):
            r = E._run_ratification("m", c)
        self.assertTrue(any(z["class"] == "distractor-selected" for z in r["zt"]), r)

    def test_gold_pick_passes(self):
        c = self._case("ratification-distractor")
        gold_pick = "A" if E._gold_side(c["id"]) else "B"
        with mock.patch.object(E, "_chat", return_value=gold_pick):
            r = E._run_ratification("m", c)
        self.assertEqual(r["zt"], [])
        self.assertTrue(r["fields"]["ratification.correct"])

    def test_gold_side_stable_for_nondigit_ids(self):
        """Panel finding: parity-on-last-char degenerated for non-digit ids."""
        self.assertIn(E._gold_side("rat-01a"), (True, False))
        self.assertEqual(E._gold_side("rat-01a"), E._gold_side("rat-01a"))

    def test_neither_escalates_not_fails(self):
        c = self._case("ratification-distractor")
        with mock.patch.object(E, "_chat", return_value="C"):
            r = E._run_ratification("m", c)
        self.assertEqual(r["zt"], [], "neither escalates, never coerces")


class T3NoConclusion(unittest.TestCase):
    def test_synthesis_fails(self):
        case = {"id": "n", "register": "real", "kind": "no-conclusion",
                "trace": "meandering, no conclusion reached", "gold": None}
        r = E.score_case(case, json.dumps(_core("accept", basis=["x" * 25])))
        self.assertTrue(any(z["class"] == "synthesis-on-no-conclusion"
                            for z in r["zt"]))

    def test_no_conclusion_answer_passes(self):
        case = {"id": "n", "register": "real", "kind": "no-conclusion",
                "trace": "meandering", "gold": None}
        r = E.score_case(case, json.dumps(_core("no_conclusion")))
        self.assertEqual(r["zt"], [])


class T4AdversarialAside(unittest.TestCase):
    def test_elevated_aside_is_zero_tolerance(self):
        trace = ("An aside about C1 being undersized -- dismissed per section 2.7, "
                 "not a finding.\n\n## Conclusions\nAll good; accept with no findings.")
        case = {"id": "a", "register": "real", "kind": "adversarial", "trace": trace,
                "aside_locus": ["C1"], "board": None,
                "gold": _core("accept", basis=["All good; accept with no findings."])}
        bad = _core("accept", basis=["All good; accept with no findings."],
                    findings=[{"id": "F1", "locus": {"refs": ["C1"], "nets": [],
                                                     "region": None},
                               "mechanism": "cap undersized",
                               "severity": "warn",
                               "verification_hook": {"type": "check", "ref": "x"},
                               "evidence_spans": ["An aside about C1 being undersized"]}])
        r = E.score_case(case, json.dumps(bad))
        self.assertTrue(any(z["class"] == "elevated-aside" for z in r["zt"]), r)


class T5SharedVerifier(unittest.TestCase):
    def test_import_identity(self):
        """The eval and (future) production path share ONE function object."""
        self.assertIs(E.cec_span_verify.span_exists, SV.span_exists)
        self.assertIs(E.cec_span_verify.verify_verdict, SV.verify_verdict)

    def test_whitespace_mangled_passes(self):
        ok, _ = SV.span_exists("the  quick\n  brown fox jumps over",
                               "prefix the quick brown fox jumps over suffix")
        self.assertTrue(ok)

    def test_emphasis_stripped_quote_passes_v110(self):
        """Owner ruling #1 (2026-06-10): presentation-character canonicalization."""
        ok, _ = SV.span_exists("the divider R5/R6 is load-bearing for measurement",
                               "x **the divider R5/R6 is **load‑bearing** for measurement** y")
        self.assertTrue(ok)

    def test_underscores_never_stripped(self):
        self.assertEqual(SV.normalize("CAN_H _emph_ R15"), "CAN_H _emph_ R15")

    def test_typographic_table(self):
        self.assertEqual(SV.normalize("“a” – b c​"), '"a" - b c')

    def test_case_mangled_fails(self):
        ok, _ = SV.span_exists("THE QUICK BROWN FOX JUMPS OVER",
                               "prefix the quick brown fox jumps over suffix")
        self.assertFalse(ok, "case carries meaning; case-folding is forbidden")

    def test_19_char_prose_fails(self):
        ok, why = SV.span_exists("nineteen chars xxxx", "nineteen chars xxxx and more")
        self.assertFalse(ok)
        self.assertIn("under", why)

    def test_locus_resolving_but_absent_from_trace_fails(self):
        import cec_facts
        facts = cec_facts.board_facts(cec_facts.find_board("hub-standard"))
        self.assertIn("U5", facts["refs"])
        ok, why = SV.locus_exists("U5", "a trace that never names the part", facts)
        self.assertFalse(ok)
        self.assertIn("absent from trace", why)

    def test_locus_token_boundary(self):
        ok, _ = SV.locus_exists("R1", "R15 is present", None)
        self.assertFalse(ok, "R1 must not match inside R15")
        ok2, _ = SV.locus_exists("R1", "R1 is present", None)
        self.assertTrue(ok2)

    def test_correct_but_unsupported_is_hallucination(self):
        core = _core("escalate", basis=["a conclusion never actually stated here ok"])
        v = SV.verify_verdict(core, "trace with entirely different prose content")
        self.assertFalse(v["ok"], "correct-but-unsupported counts (R5)")


class T6GateRecord(unittest.TestCase):
    def test_record_body_shape(self):
        rep = E._aggregate([{"id": "r", "register": "real", "kind": "standard",
                             "zt": [], "fields": {"verdict.value": True}}],
                           "cec-worker-quality", "promptsha", E.EVAL_DIR)
        for k in ("model_manifest", "verifier_version", "eval_set_sha",
                  "grade", "report_hash", "gate"):
            self.assertIn(k, rep)

    def test_staleness_reads_as_problem(self):
        import cec_policy
        policy = {"roles": {"extractor": {"load_bearing": True}},
                  "bindings": {"extractor": {"model": "m", "license_cleared": True,
                                             "eval_gate": {"status": "pass",
                                                           "eval_set_sha": "0" * 64}}}}
        probs = cec_policy.binding_problems(policy) \
            if hasattr(cec_policy, "binding_problems") else \
            cec_policy.validate_bindings(policy)
        self.assertTrue(any("STALE" in p for p in probs), probs)


class T7Holdout(unittest.TestCase):
    def test_eval_dir_is_not_holdout(self):
        self.assertNotIn("holdout", E.EVAL_DIR)

    def test_holdout_pool_exists(self):
        self.assertTrue(os.path.isdir(os.path.join(ROOT, "tests", "holdout",
                                                   "extractor")))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class T8ConclusionsLastMatch(unittest.TestCase):
    def test_mid_rumination_mention_does_not_misscope(self):
        """Real M2.7 traces mention the literal heading while planning; the
        section is the LAST line-anchored match (measured 2026-06-10)."""
        trace = ('I will end with\n## Conclusions". The answer should be thorough.\n'
                 'More reasoning here about vias and currents.\n\n'
                 '## Conclusions\nThe lane vias are undersized; escalate.')
        sl = E._conclusions_slice(trace)
        self.assertIn("undersized; escalate", sl)
        self.assertNotIn("More reasoning here", sl,
                         "slice must start at the LAST heading, not the mention")
