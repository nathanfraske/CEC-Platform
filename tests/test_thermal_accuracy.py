#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  Tests for scripts/cec_thermal_accuracy.py (Tier-0 instrument-accuracy loop:
#  shunt TCR error, thermal-EMF at Kelvin junctions, sense-amp/reference
#  drift, per-board accuracy-vs-load reconciliation). AM-04 discipline:
#  external anchors (real vendored-datasheet numbers, hand-computed twice)
#  + teeth (a sabotaged TCR must blow the error budget) + additive-only
#  (pure functions over plain {location: T_C} dicts, no board mutation).
#  Own-module isolation: imports ONLY cec_thermal_accuracy.
# ============================================================================
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.dont_write_bytecode = True

import cec_thermal_accuracy as A                               # noqa: E402


class T1ShuntTcrAnchor(unittest.TestCase):
    """(a) shunt TCR reading error, per §6.4 shunt values."""

    def test_12vhpwr_1mohm_tcr_matches_bourns_table(self):
        spec = A.SHUNT_TCR_TABLE["css2h_2512_1m0"]
        self.assertEqual(spec["tcr_ppm_C"], 75.0)
        self.assertAlmostEqual(spec["R_ohm"], 1.0e-3, delta=1e-9)

    def test_eps_pcie_0p5mohm_tcr_matches_bourns_table(self):
        spec = A.SHUNT_TCR_TABLE["css2h_2512_0m5"]
        self.assertEqual(spec["tcr_ppm_C"], 100.0)

    def test_hand_computation_at_50c_rise(self):
        # By hand: %error = TCR * dT / 1e4 = 75 * 50 / 1e4 = 0.375%
        hand = 75.0 * 50.0 / 1e4
        got = A.shunt_tcr_error_pct("css2h_2512_1m0", T_shunt_C=75.0, T_cal_C=25.0)
        self.assertAlmostEqual(got, hand, delta=1e-9)
        self.assertAlmostEqual(got, 0.375, delta=1e-9)

    def test_zero_rise_is_zero_error(self):
        got = A.shunt_tcr_error_pct("css2h_2512_1m0", T_shunt_C=25.0, T_cal_C=25.0)
        self.assertAlmostEqual(got, 0.0, delta=1e-12)

    def test_negative_rise_gives_negative_error_same_magnitude(self):
        hot = A.shunt_tcr_error_pct("css2h_2512_1m0", 75.0, 25.0)
        cold = A.shunt_tcr_error_pct("css2h_2512_1m0", -25.0, 25.0)
        self.assertAlmostEqual(hot, -cold, delta=1e-9)

    def test_teeth_sabotaged_tcr_10x_blows_up_error(self):
        # SABOTAGE: register a fake shunt entry with 10x the real TCR and confirm
        # the computed error is exactly 10x -- proves the function is NOT hard-coding
        # a fixed answer and genuinely scales with the table value.
        A.SHUNT_TCR_TABLE["_sabotage_10x"] = dict(A.SHUNT_TCR_TABLE["css2h_2512_1m0"])
        A.SHUNT_TCR_TABLE["_sabotage_10x"]["tcr_ppm_C"] *= 10
        try:
            real = A.shunt_tcr_error_pct("css2h_2512_1m0", 75.0, 25.0)
            sab = A.shunt_tcr_error_pct("_sabotage_10x", 75.0, 25.0)
            self.assertAlmostEqual(sab, real * 10, delta=1e-9)
            self.assertGreater(abs(sab), abs(real))
        finally:
            del A.SHUNT_TCR_TABLE["_sabotage_10x"]

    def test_25mv_5vsb_proxy_is_explicitly_flagged(self):
        spec = A.SHUNT_TCR_TABLE["css2h_2512_25m0_proxy"]
        self.assertIn("UNVERIFIED", spec["mpn"])
        self.assertIn("OQ-11", spec["citation"])

    def test_wsk_bucket_lookup_matches_datasheet_table(self):
        self.assertEqual(A.shunt_wsk_component_tcr_ppm_C(25e-3), 75.0)   # 7-500 mOhm bucket
        self.assertEqual(A.shunt_wsk_component_tcr_ppm_C(1.5e-3), 275.0)  # 1-2.9 mOhm bucket
        self.assertEqual(A.shunt_wsk_component_tcr_ppm_C(0.6e-3), 400.0)  # 0.5-0.99 mOhm bucket
        self.assertIsNone(A.shunt_wsk_component_tcr_ppm_C(1.0))          # out of range


class T2ThermalEmf(unittest.TestCase):
    """(b) thermal-EMF at Kelvin junctions, expressed as equivalent false amps --
    the 12VHPWR 1 mOhm case especially (µV-level signals, per the task)."""

    def test_hand_computation_12vhpwr_1mohm(self):
        # By hand: EMF = 3uV/C * dT; false_A = EMF / R
        dT = 5.0
        R = 1.0e-3
        hand_emf_V = 3.0e-6 * dT
        hand_A = hand_emf_V / R
        got = A.thermal_emf_false_current_A(dT, R)
        self.assertAlmostEqual(got, hand_A, delta=1e-9)
        self.assertAlmostEqual(got, 0.015, delta=1e-9)   # 15 mA false reading at 5C gradient, 1 mOhm

    def test_smaller_shunt_resistance_gives_larger_false_current(self):
        # The SAME absolute EMF divided by a smaller R -> a bigger equivalent-amps
        # error -- exactly the "12VHPWR 1 mOhm case especially" the task calls out
        # (µV-level signals mean a fixed EMF is a LARGER fraction of a low-R shunt's
        # own signal than a higher-R shunt's).
        a_1m = A.thermal_emf_false_current_A(5.0, 1.0e-3)
        a_25m = A.thermal_emf_false_current_A(5.0, 25.0e-3)
        self.assertGreater(a_1m, a_25m)
        self.assertAlmostEqual(a_1m / a_25m, 25.0, delta=1e-6)

    def test_zero_gradient_is_zero_emf(self):
        self.assertAlmostEqual(A.thermal_emf_false_current_A(0.0, 1.0e-3), 0.0, delta=1e-12)

    def test_sign_independent_of_gradient_direction(self):
        pos = A.thermal_emf_false_current_A(5.0, 1.0e-3)
        neg = A.thermal_emf_false_current_A(-5.0, 1.0e-3)
        self.assertAlmostEqual(pos, neg, delta=1e-12)

    def test_seebeck_junctions_are_cited_and_flagged(self):
        for key, spec in A.SEEBECK_JUNCTIONS.items():
            self.assertIn("citation", spec)
            self.assertTrue(spec.get("unverified"),
                            "%s should be marked UNVERIFIED (no directly-measured "
                            "junction-pair Seebeck coefficient)" % key)


class T3SenseAmpDrift(unittest.TestCase):
    """(c) INA240/INA238/INA181 offset+gain TC applied at local T -- the task's
    required 'worked INA240 case in the test computed two ways'."""

    def test_ina240_worked_case_two_ways(self):
        # Way 1: call sense_amp_drift() directly.
        d = A.sense_amp_drift("INA240", T_local_C=75.0, T_cal_C=25.0, channel="shunt")
        # Way 2: hand-derive from the same table entry independently.
        spec = A.SENSE_AMP_DRIFT["INA240"]
        dT = 75.0 - 25.0
        hand_offset_V = spec["vos_shunt_drift_nV_C"] * 1e-9 * dT
        hand_gain_pct = spec["gain_drift_ppm_C"] * dT / 1e4
        self.assertAlmostEqual(d["offset_V"], hand_offset_V, delta=1e-12)
        self.assertAlmostEqual(d["gain_pct"], hand_gain_pct, delta=1e-9)
        self.assertTrue(d["unverified"], "INA240 has no vendored datasheet")

    def test_ina238_matches_datasheet_exactly(self):
        d = A.sense_amp_drift("INA238", T_local_C=125.0, T_cal_C=-40.0, channel="shunt")
        # dVos/dT max = 20 nV/C over the FULL -40..125C span (165C) -> not what this
        # helper computes (it's linear-in-dT, not a span constant), but the max-rated
        # COEFFICIENT itself must match the datasheet table value used as input.
        self.assertEqual(A.SENSE_AMP_DRIFT["INA238"]["vos_shunt_drift_nV_C"], 20.0)
        self.assertEqual(A.SENSE_AMP_DRIFT["INA238"]["gain_drift_ppm_C"], 25.0)
        self.assertFalse(A.SENSE_AMP_DRIFT["INA238"].get("unverified", False))

    def test_ina228_matches_datasheet_exactly(self):
        self.assertEqual(A.SENSE_AMP_DRIFT["INA228"]["vos_shunt_drift_nV_C"], 10.0)
        self.assertEqual(A.SENSE_AMP_DRIFT["INA228"]["gain_drift_ppm_C"], 20.0)

    def test_teeth_hotter_amp_gives_bigger_offset(self):
        cool = A.sense_amp_drift("INA238", 30.0, 25.0)
        hot = A.sense_amp_drift("INA238", 120.0, 25.0)
        self.assertGreater(abs(hot["offset_V"]), abs(cool["offset_V"]))


class T4ReferenceDrift(unittest.TestCase):
    """(d) REF3030 TC + ESP32 ADC (UNVERIFIED-class, per the task)."""

    def test_ref3030_matches_datasheet_table(self):
        spec = A.REF_DRIFT["REF3030"]
        self.assertEqual(spec["drift_ppm_C_0_70"], 50.0)
        self.assertEqual(spec["drift_ppm_C_full_temp"], 65.0)

    def test_hand_computation(self):
        hand = 50.0 * 20.0 / 1e4     # 20C rise, 0-70C band coefficient
        got = A.reference_drift_pct("REF3030", T_local_C=45.0, T_cal_C=25.0, band="0_70")
        self.assertAlmostEqual(got, hand, delta=1e-9)

    def test_esp32_adc_is_explicitly_unverified_not_silently_defaulted(self):
        self.assertIn("UNVERIFIED", A.ESP32_ADC_DRIFT_UNVERIFIED["citation"])


class T5AccuracyVsLoadReport(unittest.TestCase):
    """(e) per-channel error budget vs the platform's stated accuracy claims."""

    def _spec(self, **kw):
        base = dict(name="pin1", shunt_key="css2h_2512_1m0", I_nominal_A=8.33,
                   sense_amp_part="INA238", shunt_T_key="shunt", amp_T_key="amp",
                   junction_dT_C=2.0, uses_ref3030=True)
        base.update(kw)
        return A.ChannelSpec(**base)

    def test_room_temperature_channel_is_within_claim(self):
        # junction_dT_C=0 isolates the ambient-temperature terms (TCR, sense-amp
        # drift, reference drift) from the persistent Kelvin-junction gradient term,
        # which is independent of ambient by design (see thermal_emf_false_current_A's
        # docstring: it is a GRADIENT input, not derived from absolute temperature).
        temps = {"shunt": 25.0, "amp": 25.0}
        report = A.accuracy_vs_load_report(
            "test-board", [self._spec(junction_dT_C=0.0)], temps)
        row = report["channels"][0]
        self.assertTrue(row["within_claim"])
        self.assertLess(row["rss_pct"], 0.05)

    def test_junction_gradient_contributes_even_at_room_ambient(self):
        # The Seebeck term is a GRADIENT effect, not an ambient effect -- confirm it
        # is nonzero even when both absolute temperatures equal T_cal.
        temps = {"shunt": 25.0, "amp": 25.0}
        zero_grad = A.accuracy_vs_load_report(
            "test-board", [self._spec(junction_dT_C=0.0)], temps)
        with_grad = A.accuracy_vs_load_report(
            "test-board", [self._spec(junction_dT_C=2.0)], temps)
        self.assertGreater(with_grad["channels"][0]["rss_pct"],
                           zero_grad["channels"][0]["rss_pct"])

    def test_hot_channel_reconciles_against_the_platform_claim(self):
        # 12VHPWR's committed cased dT (CLAUDE.md): ambient 50C + dT 22.95C = 72.95C.
        temps = {"shunt": 72.95, "amp": 69.95}
        report = A.accuracy_vs_load_report(
            "12vhpwr-standard",
            [self._spec(sense_amp_part="INA240")], temps)
        row = report["channels"][0]
        self.assertGreater(row["rss_pct"], 0.0)
        self.assertEqual(row["claim_limit_pct"], A.PLATFORM_ACCURACY_CLAIM_PCT["with_ref3030"])
        # RSS composition sanity: total must be >= the largest single contributor and
        # <= the naive linear sum (RSS is always between those two bounds).
        modeled = [c["pct"] for c in row["contributors"] if c["term"] != "esp32_adc"]
        self.assertGreaterEqual(row["rss_pct"] + 1e-9, max(modeled))
        self.assertLessEqual(row["rss_pct"], sum(modeled) + 1e-9)

    def test_esp32_adc_reported_but_not_folded_into_total(self):
        temps = {"shunt": 25.0, "amp": 25.0}
        report = A.accuracy_vs_load_report("test-board", [self._spec()], temps)
        row = report["channels"][0]
        adc = next(c for c in row["contributors"] if c["term"] == "esp32_adc")
        self.assertEqual(adc["pct"], 0.0)
        self.assertTrue(adc["unverified"])

    def test_without_ref3030_claim_is_the_baseline_1pct(self):
        temps = {"shunt": 25.0, "amp": 25.0}
        spec = self._spec(uses_ref3030=False)
        report = A.accuracy_vs_load_report("test-board", [spec], temps)
        self.assertEqual(report["channels"][0]["claim_limit_pct"],
                         A.PLATFORM_ACCURACY_CLAIM_PCT["baseline"])

    def test_teeth_sabotaged_tcr_blows_the_error_budget(self):
        # TEETH (hard rule): a sabotaged TCR (10x the spec) must blow the accuracy
        # gate at a load point that otherwise passes.
        temps = {"shunt": 72.95, "amp": 69.95}
        spec = self._spec(sense_amp_part=None, uses_ref3030=False)
        report_ok = A.accuracy_vs_load_report("test-board", [spec], temps)
        self.assertTrue(report_ok["channels"][0]["within_claim"],
                        "precondition: the un-sabotaged channel must pass so the "
                        "sabotage below is a real regression, not already-failing")

        A.SHUNT_TCR_TABLE["_sabotage_10x"] = dict(A.SHUNT_TCR_TABLE["css2h_2512_1m0"])
        A.SHUNT_TCR_TABLE["_sabotage_10x"]["tcr_ppm_C"] *= 10
        try:
            spec_sab = self._spec(shunt_key="_sabotage_10x", sense_amp_part=None,
                                  uses_ref3030=False)
            report_bad = A.accuracy_vs_load_report("test-board", [spec_sab], temps)
            self.assertFalse(report_bad["channels"][0]["within_claim"],
                            "a 10x-sabotaged TCR must blow the accuracy gate")
            self.assertGreater(report_bad["channels"][0]["rss_pct"],
                              report_ok["channels"][0]["rss_pct"])
        finally:
            del A.SHUNT_TCR_TABLE["_sabotage_10x"]

    def test_channel_error_budget_pure_function_no_side_effects(self):
        temps = {"shunt": 50.0, "amp": 50.0}
        spec = self._spec()
        r1 = A.channel_error_budget(spec, temps)
        r2 = A.channel_error_budget(spec, temps)
        self.assertEqual(r1["rss_pct"], r2["rss_pct"])
        self.assertEqual(temps, {"shunt": 50.0, "amp": 50.0})  # input dict untouched


class T6IsolationDiscipline(unittest.TestCase):
    """Checks actual `import`/`from ... import` STATEMENTS only (a regex anchored at
    line start), not prose -- this module's own docstring/comments legitimately
    mention 'import cec_synth_pipeline.py' in prose explaining what it does NOT do,
    which a naive substring search would misfire on."""

    def test_no_forbidden_imports(self):
        import re
        src = open(os.path.join(ROOT, "scripts", "cec_thermal_accuracy.py")).read()
        forbidden = ("cec_synth_pipeline", "cec_thermal2d", "cec_thermal_sources")
        for line in src.splitlines():
            m = re.match(r"^\s*(import|from)\s+(\S+)", line)
            if m:
                for name in forbidden:
                    self.assertNotIn(name, m.group(2),
                                     msg="forbidden import statement: %r" % line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
