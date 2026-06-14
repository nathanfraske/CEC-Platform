#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Host tests for the seat bake-off harness (scripts/cec_seat_bakeoff.py). No broker / no cloud CLI:
# the model call (bo.call) is monkeypatched, so these assert the DETERMINISTIC machinery -- the schema
# validator, the per-seat scorers, the leave-one-out blind judge loop, and the report aggregation
# (generalize-vs-overfit) -- plus the cloud-seat shim's JSON extraction + dispatch in cec_judge_local.
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_seat_bakeoff as bo            # noqa: E402
import cec_judge_local as jl             # noqa: E402


class SchemaValidator(unittest.TestCase):
    def test_panel_enum_required_additional(self):
        self.assertTrue(bo.schema_ok({"action": "repair", "reason": "x"}, bo.PANEL_SCHEMA))
        self.assertFalse(bo.schema_ok({"action": "bogus", "reason": "x"}, bo.PANEL_SCHEMA))   # enum
        self.assertFalse(bo.schema_ok({"action": "repair"}, bo.PANEL_SCHEMA))                 # required
        self.assertFalse(bo.schema_ok({"action": "repair", "reason": "x", "z": 1}, bo.PANEL_SCHEMA))

    def test_audit_nullable_and_intents_maxitems(self):
        good = {"verdict": "repair", "root_cause": "x", "reasoning": "y", "failure_class": "routing",
                "proposed_lever": None, "scorer_penalty": None, "manager_rule": None}
        self.assertTrue(bo.schema_ok(good, bo.AUDIT_SCHEMA))
        self.assertFalse(bo.schema_ok(dict(good, failure_class="weird"), bo.AUDIT_SCHEMA))
        five = {"reasoning": "r", "intents": [{"net": "/A", "layers": ["F.Cu"], "waypoints": []}] * 5}
        self.assertFalse(bo.schema_ok(five, bo.INTENTS_SCHEMA))                                # maxItems 4


class ScorerT1(unittest.TestCase):
    def test_clean_intents_full_marks(self):
        out = {"reasoning": "r", "intents": [
            {"net": "/THRESH", "layers": ["F.Cu"], "waypoints": [{"ref": "U10"}, {"between": ["U10", "U11"]}]}]}
        s = bo.score_t1(out, bo.CASES["kelvin-fail"])
        self.assertTrue(s["schema_ok"])
        self.assertEqual(s["correctness"], 1.0)

    def test_unknown_ref_and_fenced_net_dinged(self):
        out = {"reasoning": "r", "intents": [
            {"net": "/SENSEC1_HI", "layers": ["F.Cu"], "waypoints": [{"ref": "U99"}]}]}    # fenced net + bad ref
        s = bo.score_t1(out, bo.CASES["kelvin-fail"])
        self.assertEqual(s["correctness"], 0.0)
        self.assertIn("U99", s["checks"]["unknown_refs"])
        self.assertIn("/SENSEC1_HI", s["checks"]["fence_violations"])

    def test_empty_intents_partial_on_kelvin_fail(self):
        s = bo.score_t1({"reasoning": "r", "intents": []}, bo.CASES["kelvin-fail"])
        self.assertEqual(s["correctness"], 0.6)                  # not steering a kelvin fail is sub-optimal
        s2 = bo.score_t1({"reasoning": "r", "intents": []}, bo.CASES["gate-pass"])
        self.assertEqual(s2["correctness"], 1.0)                 # nothing to steer on a clean board


class ScorerT5(unittest.TestCase):
    GOOD = {"verdict": "repair", "root_cause": "sense stranded", "reasoning": "r",
            "failure_class": "placement", "proposed_lever": {"lever": "GR-02 repair shift"},
            "scorer_penalty": None, "manager_rule": None}

    def test_correct_steer_high(self):
        s = bo.score_t5(self.GOOD, bo.CASES["kelvin-fail"])
        self.assertGreaterEqual(s["correctness"], 0.9)
        self.assertTrue(s["checks"]["fclass_ok"])

    def test_penalty_on_non_gatepassing_case_dinged(self):
        bad = dict(self.GOOD, failure_class="scoring",
                   scorer_penalty={"metric": "gate_fail", "weight": 9})
        s = bo.score_t5(bad, bo.CASES["kelvin-fail"])
        self.assertFalse(s["checks"]["penalty_ok"])              # no gate-passing candidate + non-priceable
        self.assertLess(s["correctness"], 0.5)

    def test_penalty_ok_on_gatepass_with_priceable_metric(self):
        ok = dict(self.GOOD, failure_class="scoring",
                  scorer_penalty={"metric": "drc", "weight": 2})
        s = bo.score_t5(ok, bo.CASES["gate-pass"])
        self.assertTrue(s["checks"]["penalty_ok"])               # gate-pass + priceable metric

    def test_missing_root_cause_dinged(self):
        s = bo.score_t5(dict(self.GOOD, root_cause=""), bo.CASES["kelvin-fail"])
        self.assertFalse(s["checks"]["root_cause_filled"])
        self.assertLess(s["correctness"], 1.0)


class ScorerT4(unittest.TestCase):
    def test_safety_lens_accepting_gatefail_dinged_even_if_override_saves_aggregate(self):
        # safety lens (item 0) wrongly accepts a gate-fail; the override flips the aggregate to repair,
        # but the SAFETY LENS itself is unsafe -> must be penalized.
        items = [{"action": "accept", "reason": "looks ok"},   # safety lens WRONG
                 {"action": "repair", "reason": "logo"}, {"action": "repair", "reason": "stalling"}]
        s = bo.score_t4(items, bo.CASES["kelvin-fail"])
        self.assertFalse(s["checks"]["safety_lens_ok"])
        self.assertLess(s["correctness"], 1.0)

    def test_correct_panel_full_marks(self):
        items = [{"action": "repair", "reason": "kelvin stranded"},
                 {"action": "repair", "reason": "x"}, {"action": "repair", "reason": "y"}]
        s = bo.score_t4(items, bo.CASES["kelvin-fail"])
        self.assertTrue(s["checks"]["safety_lens_ok"] and s["checks"]["action_ok"])
        self.assertEqual(s["correctness"], 1.0)

    def test_gatepass_accept_ok(self):
        items = [{"action": "accept", "reason": "clean"}] * 3
        s = bo.score_t4(items, bo.CASES["gate-pass"])
        self.assertEqual(s["checks"]["panel_action"], "accept")
        self.assertEqual(s["correctness"], 1.0)


class IqrAndVariants(unittest.TestCase):
    def test_iqr(self):
        self.assertEqual(bo._iqr([5, 5, 5, 5]), 0)
        self.assertGreater(bo._iqr([1, 2, 4, 5]), 0)

    def test_all_variant_builders_yield_items(self):
        for seat, spec in bo.SEATS.items():
            for v, fn in spec["variants"].items():
                items = fn(bo.CASES["kelvin-fail"])
                self.assertTrue(items and all(len(it) == 3 for it in items), (seat, v))
        # t4 yields three lenses, safety first
        lenses = bo.SEATS["t4"]["variants"]["current"](bo.CASES["kelvin-fail"])
        self.assertEqual([l[0] for l in lenses], ["safety", "finishing", "progress"])


class JudgeLeaveOneOut(unittest.TestCase):
    def test_judge_never_scores_own_output_and_is_blind(self):
        tmp = tempfile.mkdtemp()
        orig_out, orig_call = bo.OUTDIR, bo.call
        bo.OUTDIR = tmp
        # seed two produced records from different producers
        os.makedirs(os.path.join(tmp, "produced"))
        for mdl, var in [("opus", "current"), ("sonnet", "terse")]:
            rec = {"seat": "t5", "variant": var, "model": mdl, "case": "kelvin-fail",
                   "outputs": [{"verdict": "repair", "root_cause": "x", "reasoning": "r",
                                "failure_class": "placement", "proposed_lever": None,
                                "scorer_penalty": None, "manager_rule": None}],
                   "latency_s": 1.0, "scribe_used": False, "errors": [], "score": {"correctness": 1.0}}
            json.dump(rec, open(os.path.join(tmp, "produced", "t5__%s__%s__kelvin-fail.json" % (var, mdl)), "w"))
        seen = []

        def stub(model, system, user, schema, max_tokens=1200, timeout=2700, ctx=None):
            seen.append((model, ctx.get("variant")))
            self.assertEqual(ctx.get("producer"), "HIDDEN")      # BLIND
            return {"score": 4, "rationale": "ok"}, 0.1, "{}", None, False, None
        bo.call = stub
        try:
            bo.judge(judges=["opus", "sonnet"])
        finally:
            bo.OUTDIR, bo.call = orig_out, orig_call
        # opus judged only the sonnet output (terse); sonnet judged only the opus output (current)
        self.assertIn(("opus", "terse"), seen)
        self.assertIn(("sonnet", "current"), seen)
        self.assertNotIn(("opus", "current"), seen)              # never judged its own
        self.assertNotIn(("sonnet", "terse"), seen)


class Report(unittest.TestCase):
    def test_report_generalize_vs_overfit(self):
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "judged"))
        # variant A: generalizes (high on both models); variant B: overfit (high on opus, low on worker)
        rows = [("t5", "A", "opus", 0.9), ("t5", "A", "cec-worker-vision", 0.85),
                ("t5", "B", "opus", 0.95), ("t5", "B", "cec-worker-vision", 0.2)]
        for seat, var, mdl, corr in rows:
            rec = {"seat": seat, "variant": var, "model": mdl, "case": "kelvin-fail",
                   "latency_s": 2.0, "scribe_used": False,
                   "score": {"schema_ok": True, "correctness": corr, "checks": {}},
                   "judge": {"median": 4}}
            json.dump(rec, open(os.path.join(tmp, "judged",
                      "t5__%s__%s__kelvin-fail.json" % (var, mdl)), "w"))
        # capture report output
        import io
        import contextlib
        buf = io.StringIO()
        orig = bo.OUTDIR
        bo.OUTDIR = tmp
        try:
            with contextlib.redirect_stdout(buf):
                bo.report(run_dir=tmp)
        finally:
            bo.OUTDIR = orig
        out = buf.getvalue()
        self.assertIn("A: mean", out)
        self.assertIn("generalizes", out)                        # variant A low spread
        self.assertIn("OVERFIT-prone", out)                      # variant B high spread


class CloudShim(unittest.TestCase):
    def test_extract_and_dispatch(self):
        self.assertTrue(jl._is_cloud("opus") and not jl._is_cloud("deepseek-v4-flash"))
        self.assertEqual(jl._extract_json_obj('x ```json\n{"a":{"b":1}}\n``` y'), {"a": {"b": 1}})
        self.assertEqual(jl._extract_json_obj('{"s":"} not end","n":3}'), {"s": "} not end", "n": 3})
        import subprocess
        orig = subprocess.run

        class R:
            returncode = 0
            stderr = ""
            stdout = json.dumps({"type": "result",
                                 "result": '{"verdict":"accept","failure_class":"none"}'})
        subprocess.run = lambda *a, **k: R()
        try:
            out = jl._chat_json("sys", "usr", {"type": "object"}, model="sonnet")
        finally:
            subprocess.run = orig
        self.assertEqual(out, {"verdict": "accept", "failure_class": "none"})

    def test_cloud_retry_then_succeed_and_raw_on_final_failure(self):
        import subprocess

        class R:
            def __init__(self, out):
                self.returncode = 0
                self.stderr = ""
                self.stdout = out
        orig = subprocess.run
        calls = []

        def flaky(cmd, **k):
            calls.append(1)
            payload = "no json yet" if len(calls) == 1 else '{"action":"repair","reason":"x"}'
            return R(json.dumps({"type": "result", "result": payload}))
        subprocess.run = flaky
        try:
            out = jl._chat_json_cloud("s", "u", {"type": "object"}, model="opus")
            self.assertEqual(out, {"action": "repair", "reason": "x"})
            self.assertEqual(len(calls), 2)                          # retried the bad first reply
            subprocess.run = lambda cmd, **k: R(json.dumps({"type": "result", "result": "no json here"}))
            with self.assertRaises(ValueError) as cm:
                jl._chat_json_cloud("s", "u", {"type": "object"}, model="opus")
            self.assertIn("raw=", str(cm.exception))                 # raw snippet surfaced for debug
        finally:
            subprocess.run = orig


if __name__ == "__main__":
    unittest.main()
