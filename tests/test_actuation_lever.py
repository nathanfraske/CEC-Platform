#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Full actuation lever, Step 1 -- per-rule TRANSITIVE influence lineage + the clean-evidence
# comparator, post-audit (wf_f24bddf7-9fd). Pure host tests (no pcbnew, no broker). Invariant:
# a rule may be scored ONLY on outcomes it did not influence, and influenced_by on a row is the
# COMPLETE set of run-learned steer that shaped the board THAT ROW MEASURED (route-time snapshot).
# These exercise the SAME functions the loop calls (compute_influenced_by / route_placement_cone /
# the *_steer_id derivers) -- tested == shipped. See docs/actuation-lever-design.md.

import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fullstack as fs           # noqa: E402  (lazy pcbnew/broker imports -- host-safe)


def _row(lane, influenced, **m):
    r = {"lane": lane, "influenced_by": influenced}
    r.update(m)
    return r


class TestRuleIdAndSteer(unittest.TestCase):
    def test_rule_id_stable_and_kind_tagged(self):
        self.assertEqual(fs.rule_id("rule", "x"), fs.rule_id("rule", "x"))
        self.assertNotEqual(fs.rule_id("rule", "x"), fs.rule_id("rule", "y"))
        self.assertTrue(fs.rule_id("penalty", {"m": 1}).startswith("penalty:"))

    def test_active_steer_ids_excludes_default_penalties(self):
        fresh = {"manager_rules": [], "scorer_penalties": dict(fs._DEFAULT_PENALTIES)}
        self.assertEqual(fs.active_steer_ids(fresh), [])
        lr = {"manager_rules": ["r1"], "scorer_penalties": {**fs._DEFAULT_PENALTIES, "drc": 90.0}}
        ids = fs.active_steer_ids(lr)
        self.assertTrue(any(i.startswith("rule:") for i in ids))
        self.assertTrue(any(i.startswith("penalty:") for i in ids))
        self.assertEqual(len(ids), 2)

    def test_intents_steer_id_only_for_model_plan(self):
        plan = [{"net": "/CAN_H"}, {"net": "/I2C_SDA"}]
        self.assertIsNone(fs.intents_steer_id(plan, "seed"))      # static seed is not a steer
        self.assertIsNone(fs.intents_steer_id([], "model"))       # empty plan
        mid = fs.intents_steer_id(plan, "model")
        self.assertTrue(mid.startswith("intents:"))
        # net-set + src keyed: same plan -> same id (tallyable across rounds); order-independent
        self.assertEqual(mid, fs.intents_steer_id(list(reversed(plan)), "model"))

    def test_avoid_steer_ids_per_net(self):
        ids = fs.avoid_steer_ids([{"net": "/CAN_L"}, {"net": "/DETAMP"}])
        self.assertEqual(len(ids), 2)
        self.assertTrue(all(i.startswith("avoid:") for i in ids))
        self.assertEqual(fs.avoid_steer_ids([]), [])

    def test_effort_steer_id(self):
        self.assertIsNone(fs.effort_steer_id(fs._BASE_PASSES, fs._BASE_OPT))     # base = not a steer
        self.assertIsNotNone(fs.effort_steer_id(fs._BASE_PASSES + 8, fs._BASE_OPT))
        self.assertIsNotNone(fs.effort_steer_id(fs._BASE_PASSES, fs._BASE_OPT + 20))


class TestRouteTimeSnapshotAndTransitivity(unittest.TestCase):
    def test_route_placement_cone_includes_kept_plus_in_flight(self):
        self.assertEqual(fs.route_placement_cone(["placement:a"], "placement:b"),
                         ["placement:a", "placement:b"])
        self.assertEqual(fs.route_placement_cone([], None), [])

    def _sim_round(self, kept_cone, pending_id):
        """Mirror the loop: the row's placement cone is the ROUTE-TIME snapshot (kept + in-flight)."""
        return fs.route_placement_cone(kept_cone, pending_id)

    def test_apply_round_not_tagged_with_its_own_just_applied_move(self):
        # Round N: routes with no in-flight move; the move is applied AFTER the route -> N's row must
        # NOT carry it (N's board predates the move). Snapshot at route time has pending=None.
        cone_at_route_N = self._sim_round(kept_cone=[], pending_id=None)
        self.assertEqual(cone_at_route_N, [])

    def test_refuted_moves_own_routed_round_is_tagged_then_clean_after(self):
        M = "placement:M"
        # Round N+1 routes the MOVED board (M is the in-flight pending move) -> tagged with M...
        cone_N1 = self._sim_round(kept_cone=[], pending_id=M)
        self.assertIn(M, cone_N1)
        # ...then M settles REFUTED: not appended to the kept cone, pending cleared. Round N+2 routes
        # the reverted board -> clean of M.
        kept_after_refute = []                  # refuted -> NOT appended
        cone_N2 = self._sim_round(kept_cone=kept_after_refute, pending_id=None)
        self.assertNotIn(M, cone_N2)

    def test_kept_move_compounds_into_every_later_round(self):
        M = "placement:M"
        kept_after_keep = [M]                   # vindicated+keep -> appended to the kept cone
        self.assertIn(M, self._sim_round(kept_cone=kept_after_keep, pending_id=None))
        self.assertIn(M, self._sim_round(kept_cone=kept_after_keep, pending_id="placement:N"))


class TestComputeInfluencedBy(unittest.TestCase):
    def test_control_is_always_empty(self):
        self.assertEqual(fs.compute_influenced_by(
            "control", steer_ids=["rule:x"], placement_cone=["placement:k"],
            intent_id="intents:i", avoid_ids=["avoid:a"], effort_id="effort:e",
            layer_id="layer:l"), [])

    def test_augmented_unions_every_steer_class(self):
        cone = fs.compute_influenced_by(
            "augmented", steer_ids=["rule:x", "penalty:p"], placement_cone=["placement:k"],
            intent_id="intents:i", avoid_ids=["avoid:a1", "avoid:a2"], effort_id="effort:e",
            layer_id="layer:l")
        for x in ("rule:x", "penalty:p", "placement:k", "intents:i", "avoid:a1", "avoid:a2",
                  "effort:e", "layer:l"):
            self.assertIn(x, cone)

    def test_none_steers_are_dropped(self):
        cone = fs.compute_influenced_by("augmented", steer_ids=[], intent_id=None,
                                        effort_id=None, layer_id=None)
        self.assertEqual(cone, [])


class TestCleanEvidenceFirewall(unittest.TestCase):
    def test_firewall_excludes_influenced_rows_from_baseline(self):
        R = "placement:R"
        rows = [_row("control", [], drc=20), _row("augmented", [R], drc=10),
                _row("augmented", ["other:X"], drc=18), _row("augmented", [R, "other:X"], drc=11)]
        part = fs.clean_pairs(rows, R)
        self.assertEqual(len(part["treatment"]), 2)
        self.assertEqual(len(part["baseline"]), 2)
        self.assertTrue(all(R not in (b["influenced_by"] or []) for b in part["baseline"]))

    def test_row_without_cone_key_is_in_neither_arm(self):
        # the absent-key hole: a legacy / cross-run ledger row (no influenced_by) must NOT become a
        # universal clean baseline for every rule.
        R = "rule:R"
        rows = [{"lane": "augmented", "drc": 5},                    # no influenced_by key
                _row("control", [], drc=20), _row("augmented", [R], drc=10)]
        part = fs.clean_pairs(rows, R)
        self.assertEqual(len(part["baseline"]), 1)                 # only the real control row
        self.assertEqual(len(part["treatment"]), 1)

    def test_clean_evidence_delta_uses_only_clean_baseline(self):
        R = "penalty:R"
        rows = [_row("control", [], drc=20), _row("control", [], drc=20),
                _row("augmented", [R], drc=10), _row("augmented", [R], drc=12)]
        d = fs.clean_evidence_delta(rows, R, "drc")
        self.assertEqual((d["n_baseline"], d["n_treatment"]), (2, 2))
        self.assertEqual(d["baseline_mean"], 20.0)
        self.assertEqual(d["treatment_mean"], 11.0)
        self.assertEqual(d["delta"], -9.0)

    def test_delta_none_when_an_arm_is_empty(self):
        R = "rule:R"
        rows = [_row("augmented", [R], drc=10), _row("augmented", [R], drc=11)]
        d = fs.clean_evidence_delta(rows, R, "drc")
        self.assertIsNone(d["delta"])
        self.assertEqual((d["n_baseline"], d["n_treatment"]), (0, 2))

    def test_a_rule_can_never_be_its_own_baseline(self):
        R = "placement:R"
        rows = [_row("augmented", [R], drc=10), _row("control", [], drc=20),
                _row("augmented", [R, "x:1"], drc=9)]
        part = fs.clean_pairs(rows, R)
        self.assertTrue({id(t) for t in part["treatment"]}.isdisjoint({id(b) for b in part["baseline"]}))


class TestCrossRunTally(unittest.TestCase):
    """Step 2: pooling CLEAN evidence over INDEPENDENT runs, keyed by stable rule id."""

    def _run(self, name, rows):
        return (name, rows)

    def test_rule_ids_in_rows(self):
        rows = [_row("augmented", ["rule:a", "placement:b"]), _row("control", []),
                _row("augmented", ["rule:a"])]
        self.assertEqual(fs.rule_ids_in_rows(rows), ["placement:b", "rule:a"])

    def test_tally_pools_only_valid_clean_pairs(self):
        R = "rule:R"
        run1 = self._run("r1", [_row("control", [], drc=20), _row("augmented", [R], drc=10)])
        run2 = self._run("r2", [_row("control", [], drc=22), _row("augmented", [R], drc=12)])
        run3 = self._run("r3", [_row("augmented", [R], drc=11)])   # no clean baseline -> dropped
        t = fs.rule_tally(R, "drc", [run1, run2, run3])
        self.assertEqual(t["n_runs"], 2)                          # run3 contributed no clean pair
        self.assertEqual([p["run"] for p in t["per_run"]], ["r1", "r2"])
        self.assertEqual(t["pooled_delta"], -10.0)                # (-10 + -10)/2
        self.assertEqual(t["n_pairs"], 2)

    def test_tally_empty_when_no_clean_evidence(self):
        R = "rule:R"
        t = fs.rule_tally(R, "drc", [self._run("r1", [_row("augmented", [R], drc=10)])])
        self.assertEqual(t["n_runs"], 0)
        self.assertIsNone(t["pooled_delta"])


class TestGraduationBar(unittest.TestCase):
    """Step 3: the bar -- enough independent clean runs + consistent improving direction + effect."""

    def _tally(self, deltas, n_pairs=None):
        per = [{"run": f"r{i}", "delta": d, "n_baseline": 2, "n_treatment": 2}
               for i, d in enumerate(deltas)]
        return {"rule_id": "rule:R", "metric": "drc", "n_runs": len(per),
                "n_pairs": n_pairs if n_pairs is not None else 2 * len(per),
                "per_run": per, "pooled_delta": round(sum(deltas) / len(deltas), 4) if deltas else None}

    def test_graduates_when_consistent_and_strong(self):
        # drc is lower-is-better; 4 runs all improving by >= the 2.0 effect floor
        v = fs.graduation_verdict(self._tally([-5, -4, -6, -3]))
        self.assertTrue(v["graduate"], v["reasons"])
        self.assertEqual(v["reasons"], [])

    def test_rejected_too_few_runs(self):
        v = fs.graduation_verdict(self._tally([-5, -6]))          # min_runs default 3
        self.assertFalse(v["graduate"])
        self.assertTrue(any("n_runs" in r for r in v["reasons"]))

    def test_rejected_inconsistent_direction(self):
        # 4 runs but only half improve -> fails the sign test (improving_frac 0.5 < 0.75)
        v = fs.graduation_verdict(self._tally([-5, +6, -4, +5]))
        self.assertFalse(v["graduate"])
        self.assertTrue(any("improving_frac" in r for r in v["reasons"]))

    def test_rejected_effect_too_small(self):
        # consistent direction + enough runs, but |pooled| 1.0 < the 2.0 drc effect floor
        v = fs.graduation_verdict(self._tally([-1, -1, -1, -1]))
        self.assertFalse(v["graduate"])
        self.assertTrue(any("pooled" in r for r in v["reasons"]))

    def test_wrong_direction_for_higher_is_better_metric(self):
        # gates_pass is higher-is-better; a NEGATIVE pooled delta is a regression, never graduates
        t = {"rule_id": "rule:R", "metric": "gates_pass", "n_runs": 4, "n_pairs": 8,
             "per_run": [{"run": f"r{i}", "delta": -0.3, "n_baseline": 2, "n_treatment": 2}
                         for i in range(4)], "pooled_delta": -0.3}
        v = fs.graduation_verdict(t)
        self.assertFalse(v["graduate"])


class TestSteerOnlyChokepoint(unittest.TestCase):
    """Step 4: a ratified rule may STEER, never GATE."""

    def test_steer_fields_allowed(self):
        self.assertTrue(fs.assert_steer_only({"rank_key": 1, "seed": 7, "passes": 30}))

    def test_gate_field_write_raises(self):
        for gate in ("gates_pass", "kelvin_ok", "drc", "pour_integrity_ok", "ship"):
            with self.assertRaises(fs.SteerViolation):
                fs.assert_steer_only({gate: True})

    def test_unknown_field_raises(self):
        with self.assertRaises(fs.SteerViolation):
            fs.assert_steer_only({"delete_board": True})

    def test_empty_action_is_noop_ok(self):
        self.assertTrue(fs.assert_steer_only({}))


class TestGraduationBarHoldout(unittest.TestCase):
    """AM-02: the bar's DEFAULT thresholds must correctly classify the held-out pool (tests/holdout/
    actuation) -- the never-tuned complement that keeps the bar honest. A TEST may read holdout; the
    bar code (scripts/) may not (checklist enforces). If you change a bar threshold and a holdout case
    flips, you must understand why -- never edit the fixture to make the bar pass."""

    def test_default_bar_classifies_holdout(self):
        path = os.path.join(ROOT, "tests", "holdout", "actuation", "bar-fixtures.json")
        cases = json.load(open(path))["cases"]
        self.assertGreaterEqual(len(cases), 4)
        for c in cases:
            v = fs.graduation_verdict(c["tally"])         # DEFAULT thresholds, no overrides
            self.assertEqual(v["graduate"], c["expect_graduate"],
                             f"{c['name']}: expected graduate={c['expect_graduate']} ({c['why']}); "
                             f"got {v['graduate']} reasons={v['reasons']}")


class TestActuationLeverReport(unittest.TestCase):
    """The steps 2-3 driver: per-rule tally + graduation advisory over runs, and load_runs_from_dirs."""

    def test_report_flags_a_graduating_rule(self):
        R = "rule:R"
        # 4 runs, 2 clean control + 2 R-treatment rows each -> 8 clean pairs, drc improves by 6
        runs = [(f"r{i}", [_row("control", [], drc=20), _row("control", [], drc=20),
                           _row("augmented", [R], drc=14), _row("augmented", [R], drc=14)])
                for i in range(4)]
        rep = fs.actuation_lever_report(runs)
        self.assertIn(R, rep["candidate_rules"])
        grad_drc = [g for g in rep["graduated"] if g["rule_id"] == R and g["metric"] == "drc"]
        self.assertTrue(grad_drc, rep["graduation"])

    def test_report_no_graduation_without_clean_baseline(self):
        R = "rule:R"
        runs = [(f"r{i}", [_row("augmented", [R], drc=14)]) for i in range(4)]   # no control rows
        rep = fs.actuation_lever_report(runs)
        self.assertEqual(rep["graduated"], [])

    def test_load_runs_from_dirs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            for i, drc in enumerate((10, 12)):
                rd = os.path.join(d, f"fullstack-run-x{i}")
                os.makedirs(rd)
                with open(os.path.join(rd, "measurement.jsonl"), "w") as fh:
                    fh.write(json.dumps(_row("augmented", ["rule:R"], drc=drc)) + "\n")
                json.dump({"board": "eps-8pin"}, open(os.path.join(rd, "bundle.json"), "w"))
            # add a different-board run that must be filtered OUT
            rd2 = os.path.join(d, "fullstack-run-other")
            os.makedirs(rd2)
            open(os.path.join(rd2, "measurement.jsonl"), "w").write(
                json.dumps(_row("augmented", ["rule:R"], drc=99)) + "\n")
            json.dump({"board": "hub-standard"}, open(os.path.join(rd2, "bundle.json"), "w"))
            runs = fs.load_runs_from_dirs([os.path.join(d, "*", "measurement.jsonl")], board="eps-8pin")
            self.assertEqual(len(runs), 2)                # the hub-standard run filtered out
            self.assertTrue(all(any(r.get("drc") != 99 for r in rows) for _, rows in runs))


class TestSingleSourceConstants(unittest.TestCase):
    """The audit's anti-drift pins: run() must init lr penalties from the shared constant, and the
    panel reset must use the shared base-effort constants -- so a retune cannot fork a phantom id."""

    def test_run_inits_penalties_from_the_shared_constant(self):
        src = open(os.path.join(ROOT, "scripts", "cec_fullstack.py")).read()
        self.assertIn('"scorer_penalties": dict(_DEFAULT_PENALTIES)', src)
        # and no re-introduced literal default-penalty dict in run()
        self.assertNotIn('"scorer_penalties": {"plane_signal_mm": 50.0', src)

    def test_panel_reset_uses_base_effort_constants(self):
        src = open(os.path.join(ROOT, "scripts", "cec_fullstack.py")).read()
        self.assertTrue(re.search(r"passes, opt_time = _BASE_PASSES, _BASE_OPT", src))
        self.assertEqual((fs._BASE_PASSES, fs._BASE_OPT), (24, 40))


if __name__ == "__main__":
    unittest.main()
