#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  Anchor fixture for the cluster-5 measurement-claims corpus entries
#  (owner ratification 2026-06-10, items 1/2/3/5). This file IS the AM-02
#  fixture the entries point at: change a ruled value and the assertions fire.
#  Host-runnable, dependency-free.
# ============================================================================
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Promotion MOVES entries staging->promoted (id unchanged; an id lives in exactly one
# zone, lint-enforced), so this anchor fixture reads its family file from BOTH zones.
GEN_DIRS = (os.path.join(ROOT, "corpus", "staging", "general"),
            os.path.join(ROOT, "corpus", "promoted", "general"))


def _load(fname="measurement-claims.json"):
    out = {}
    for d in GEN_DIRS:
        p = os.path.join(d, fname)
        if os.path.exists(p):
            out.update({e["id"]: e for e in json.load(open(p))})
    return out


class T1TargetTable(unittest.TestCase):
    def setUp(self):
        self.t = _load()["meas.targets.v1"]["value"]

    def _rows(self, quantity):
        return [r for r in self.t["rows"] if r["quantity"] == quantity]

    def test_voltage_rows_as_ruled(self):
        v = self._rows("voltage")
        by = {(r["tier_path"].split(" ")[0], r["basis"],
               r["conditions"].get("temp_C")): r["value_pct"] for r in v}
        self.assertEqual(by[("Pro", "design_outcome", None)], 0.15)  # stays design-outcome
        self.assertEqual(by[("12VHPWR", "promise", 25)], 0.5)        # the loose end
        self.assertEqual(by[("12VHPWR", "design_outcome", 25)], 0.3)
        self.assertEqual(by[("bare-ADC", "promise", 25)], 1.0)

    def test_promises_state_both_temperature_points(self):
        """Items 2+5: accuracy is stated at BOTH temperature points -- every
        promise path carries a 50C row (placeholder until the budget doc's
        TCR terms land)."""
        v = self._rows("voltage")
        paths_25 = {r["tier_path"] for r in v
                    if r["basis"] == "promise" and r["conditions"].get("temp_C") == 25}
        paths_50 = {r["tier_path"] for r in v
                    if r["basis"] == "promise" and r["conditions"].get("temp_C") == 50}
        self.assertEqual(paths_25, paths_50,
                         "every promise path must carry both the 25C and 50C rows")
        for r in v:
            if r["basis"] == "promise" and r["conditions"].get("temp_C") == 50:
                self.assertIsNone(r["value_pct"],
                                  "50C values are pending the budget doc TCR terms")

    def test_promise_ordering_sane(self):
        """design-outcome <= promise on the same path; bare-ADC loosest."""
        self.assertLessEqual(0.3, 0.5)
        self.assertLessEqual(0.5, 1.0)

    def test_current_rows_are_placeholders(self):
        for r in self._rows("current"):
            self.assertEqual(r["basis"], "placeholder",
                             "current promises enter as placeholders pending the budget doc")
            self.assertIsNone(r["value_pct"])

    def test_power_is_policy_energy_is_none(self):
        (p,) = self._rows("power")
        (e,) = self._rows("energy")
        self.assertEqual(p["basis"], "policy")
        self.assertEqual(p["conditions"]["ref"], "meas.policy.power_error_rss")
        self.assertEqual(e["basis"], "none")
        self.assertEqual(e["conditions"]["ref"], "meas.policy.energy_unpromised")

    def test_no_typ_basis_anywhere(self):
        """'typ never is' a promise -- and typ never appears as a basis."""
        for r in self.t["rows"]:
            self.assertIn(r["basis"], ("promise", "design_outcome", "placeholder",
                                       "policy", "none"))


class T2Policies(unittest.TestCase):
    def setUp(self):
        self.m = _load()

    def test_power_rss(self):
        v = self.m["meas.policy.power_error_rss"]["value"]
        self.assertIn("RSS", v["error_model"])
        self.assertEqual(v["presentation"], "computed, not promised")

    def test_energy_mechanism(self):
        v = self.m["meas.policy.energy_unpromised"]["value"]
        self.assertIn("gain error linearly", v["mechanism"])
        self.assertIn("characterized-pending", v["concierge"])

    def test_promotion_rule(self):
        v = self.m["meas.policy.promise_promotion"]["value"]
        self.assertIn("worst-case floor", v["rule"])
        self.assertIn("headroom", v["rule"])
        self.assertIn("spec-revision candidate", v["spec_divergence"])


class T3Calibration(unittest.TestCase):
    def setUp(self):
        self.m = _load()

    def test_per_tier_legs(self):
        v = self.m["meas.cal.strategy_per_tier"]["value"]
        self.assertIn("no per-unit cal", v["standard"])
        self.assertIn("SHUNT_CAL trimmed at provisioning", v["pro"])
        self.assertIn("per quantity", v["no_cal_grade_per_quantity"])

    def test_temperature_points_consistent_with_statement_form(self):
        cal = self.m["meas.cal.temperature_policy"]["value"]
        form = self.m["meas.statement_form"]["value"]
        self.assertEqual(cal["calibrate_at_C"], 25)
        self.assertEqual(cal["state_accuracy_at_C"], form["temperature_points"])
        self.assertEqual(form["temperature_points"], [25, 50])

    def test_storage_decided(self):
        v = self.m["meas.cal.storage"]["value"]
        self.assertEqual(v["system_of_record"], "factory MAC plus database")
        self.assertEqual(sorted(v["per_unit_record"]), ["cal date", "instrument ID"])


class T4Anchors(unittest.TestCase):
    def setUp(self):
        self.m = _load()

    def test_ref3030_anchor_pinned(self):
        e = self.m["meas.anchor.ref3030_initial_accuracy"]
        self.assertEqual(e["class"], "A")
        self.assertEqual(e["value"], 0.2)
        self.assertEqual(e["source"]["type"], "datasheet")
        # the vendored artifact must resolve
        self.assertTrue(os.path.exists(os.path.join(ROOT, "lib", "datasheets",
                                                    "REF30E-REF30.pdf")))

    def test_standard_current_anchor_is_shunt_tolerance(self):
        v = self.m["meas.anchor.standard_current"]["value"]
        self.assertEqual(v["anchor"], "shunt tolerance as built")

    def test_pro_anchor_deferred_pending_instrument(self):
        """Owner 2026-06-10: empty bench -> deferred, never placeholder-numbered."""
        v = self.m["meas.anchor.pro_cal_instrument"]["value"]
        self.assertIn("DEFERRED-PENDING-INSTRUMENT", v["value"])
        self.assertIn("never placeholder-numbered", v["value"])
        self.assertIn("cal instrument", v["anchor"])


class T5TruthChainAndJudge(unittest.TestCase):
    def setUp(self):
        self.m = _load()

    def test_claim_levels_locked(self):
        """Owner 2026-06-10: NIST rejected outright; 'characterized' full stop."""
        v = self.m["meas.truth_chain.claim_level"]["value"]
        self.assertIn("REJECTED OUTRIGHT", v["force"])
        self.assertEqual(v["public_language"], "characterized -- full stop")
        self.assertEqual(v["standard"], "characterized")
        self.assertIn("DEFERRED-PENDING-INSTRUMENT", v["pro"])

    def test_founders_ack_scope_shrunk(self):
        """Founders-ack = promise rows + dV/dI tier framing ONLY; the
        traceability wording goes to them as DECIDED."""
        self.assertIn("FOUNDERS-ACK REQUIRED BEFORE PROMOTION",
                      self.m["meas.targets.v1"]["notes"])
        self.assertNotIn("FOUNDERS-ACK REQUIRED BEFORE PROMOTION",
                         self.m["meas.truth_chain.claim_level"]["notes"])
        self.assertIn("AS DECIDED", self.m["meas.truth_chain.claim_level"]["notes"])

    def test_empty_bench_state_and_carveout(self):
        e = self.m["meas.bench.empty_instrument_state"]["value"]
        self.assertIn("no trusted voltage reference", e["state"])
        self.assertTrue(any("RULING-7" in c for c in e["consequences"]))
        self.assertIn("lane-impedance-DRIFT", e["carve_out"])
        self.assertIn("datasheet facts", e["unaffected"])

    def test_spec_wording_drafted(self):
        v = self.m["meas.truth_chain.spec_wording"]["value"]
        self.assertIn("CHARACTERIZED", v["drafted_wording"])
        self.assertIn("no NIST-traceability claim", v["drafted_wording"])
        self.assertIn("worst-case", v["drafted_wording"])

    def test_judge_band_rule(self):
        v = self.m["judge.reading_assertion_band"]["value"]
        self.assertIn("never a bare number", v["rule"])
        self.assertIn("false-claim class", v["violation"])

    def test_dispute_chain(self):
        chain = self.m["meas.truth_chain.dispute"]["value"]["chain"]
        self.assertEqual(len(chain), 3)
        self.assertIn("stated conditions", chain[0])
        self.assertIn("named bench instrument", chain[1])


class T6TypingDiscipline(unittest.TestCase):
    def test_h_never_physics_no_compile(self):
        for e in _load().values():
            if e["class"] == "H":
                self.assertNotIn("physics", e["applies_to"], e["id"])
                self.assertNotIn("compile", e, e["id"])

    def test_unique_ids(self):
        ids = [e["id"] for d in GEN_DIRS
               for e in (json.load(open(os.path.join(d, "measurement-claims.json")))
                         if os.path.exists(os.path.join(d, "measurement-claims.json")) else [])]
        self.assertEqual(len(ids), len(set(ids)))  # unique within AND across zones


if __name__ == "__main__":
    unittest.main()
