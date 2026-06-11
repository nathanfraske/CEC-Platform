#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  Fixture for docs/research/stability-budget-dvdi-2026-06-10.md: every figure
#  in the budget doc recomputes HERE from the corpus entries (true
#  derivation-from-corpus -- change an entry and the budget's verdict line is
#  re-checked). Revised per the 2026-06-10 refuter panel: durations read from
#  the corpus (no magic numbers), the lane-impedance estimate derives from
#  pinned entries, the stated headroom ratios are pinned exactly, and the
#  thermal term carries the zero-compensation-credit 50C bound.
#  Host-runnable, dependency-free.
# ============================================================================
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN = os.path.join(ROOT, "corpus", "staging", "general")

W_HOURS = 336.0            # the budget's working window: 14 days
SHUNT_UOHM = 1000.0        # 1 mOhm lane shunt in uOhm
SIGNAL_UOHM = 1000.0       # the ratified 1 mOhm requirement
GATE_PROMOTE_UOHM = 300.0  # < 0.3 mOhm -> Standard full
GATE_RESTRICT_UOHM = 700.0  # > 0.7 mOhm -> Pro-only
ZERO_CREDIT_SWING_C = 50.0  # thermal bound with NO compensation credit


def _entry(fname, eid):
    rows = json.load(open(os.path.join(GEN, fname)))
    return next(e for e in rows if e["id"] == eid)


def lane_z_uohm():
    """The doc's inline estimate: shunt + 2x healthy contact + cable limit."""
    contact = _entry("fault-phenomenology.json",
                     "conn.malucci_runaway_onset")["value"]["healthy_baseline_mohm"]
    cable = _entry("fault-phenomenology.json",
                   "conn.llcr_cable_assembly")["value"]["llcr_max_mohm_per_conductor"]
    return SHUNT_UOHM + 2 * contact * 1000 + cable * 1000          # 8600 uOhm


def css_terms():
    v = _entry("stability-terms.json", "stab.shunt_loadlife_bourns_css")["value"]
    aging = SHUNT_UOHM * v["load_life_dRR_pct_max"] / 100.0        # 10
    tcr = SHUNT_UOHM * v["tcr_ppm_per_C"] * 1e-6 * ZERO_CREDIT_SWING_C   # 2.5
    return v, aging, tcr


def wsl_terms():
    v = _entry("stability-terms.json", "stab.shunt_loadlife_tcr_vishay_wsl")["value"]
    aging = v["load_life_additive_mohm"] * 1000 + SHUNT_UOHM * 0.01      # 510
    tcr = (SHUNT_UOHM * v["tcr_component_ppm_per_C"]["1_to_2p9_mohm"]
           * 1e-6 * ZERO_CREDIT_SWING_C)                                 # 13.75
    return v, aging, tcr


def minor_terms():
    ina = _entry("stability-terms.json", "stab.ina240_precision_terms")["value"]
    ref = _entry("stability-terms.json", "stab.ref3030_drift")["value"]
    gain = lane_z_uohm() * ina["gain_drift_ppm_per_C_max"] * 1e-6 * 20   # ~0.43
    refd = lane_z_uohm() * ref["long_term_drift_ppm_0_1000h"] * 1e-6 * (W_HOURS / 1000.0)
    return gain, refd


class T1LaneEstimate(unittest.TestCase):
    def test_inline_derivation_from_pinned_entries(self):
        self.assertEqual(lane_z_uohm(), 8600.0,
                         "1 mOhm shunt + 2x0.8 mOhm contacts + 6 mOhm cable limit")


class T2CruxTerm(unittest.TestCase):
    def test_css_worst_case_clears_gate(self):
        v, aging, _ = css_terms()
        self.assertEqual(aging, 10.0)                                # 1% of 1 mOhm
        self.assertLess(aging, GATE_PROMOTE_UOHM)
        # aging-only ratios stated in the doc
        self.assertAlmostEqual(GATE_PROMOTE_UOHM / aging, 30.0, delta=0.1)
        self.assertAlmostEqual(SIGNAL_UOHM / aging, 100.0, delta=0.1)
        # linear pro-rate reads the duration FROM THE ENTRY
        linear = aging * W_HOURS / v["load_life_duration_h"]
        self.assertAlmostEqual(linear, 0.16, delta=0.01)

    def test_wsl_worst_case_fails_gate(self):
        v, aging, _ = wsl_terms()
        self.assertEqual(aging, 510.0)                               # 0.5 mOhm + 1%
        self.assertGreater(aging, GATE_PROMOTE_UOHM,
                           "WSL worst-case FAILS the promote gate -- the verdict line")
        self.assertLess(aging, GATE_RESTRICT_UOHM)                   # approaches, not over
        linear = aging * W_HOURS / v["load_life_duration_h"]         # duration from entry
        self.assertAlmostEqual(linear, 171.4, delta=1.0)
        self.assertLess(linear, GATE_PROMOTE_UOHM)                   # sneaks under...
        self.assertLess(GATE_PROMOTE_UOHM / linear, 2.0,
                        "...with under-2x margin -- why worst-case governs")

    def test_wsl_tier_boundary(self):
        """The 400 ppm tier (sub-1 mOhm post-tolerance) bound stays sub-signal."""
        v = _entry("stability-terms.json", "stab.shunt_loadlife_tcr_vishay_wsl")["value"]
        worst = (SHUNT_UOHM * v["tcr_component_ppm_per_C"]["0p5_to_0p99_mohm"]
                 * 1e-6 * ZERO_CREDIT_SWING_C)
        self.assertAlmostEqual(worst, 20.0, delta=0.1)
        self.assertLess(worst, SIGNAL_UOHM / 25)


class T3ZeroCreditThermal(unittest.TestCase):
    def test_bounds(self):
        _, _, css_tcr = css_terms()
        _, _, wsl_tcr = wsl_terms()
        self.assertAlmostEqual(css_tcr, 2.5, delta=0.01)
        self.assertAlmostEqual(wsl_tcr, 13.75, delta=0.01)
        self.assertLess(wsl_tcr, SIGNAL_UOHM / 50,
                        "even zero-compensation-credit thermal sits 50x under signal")


class T4MinorTerms(unittest.TestCase):
    def test_gain_and_ref_terms(self):
        gain, refd = minor_terms()
        self.assertAlmostEqual(gain, 0.43, delta=0.01)
        self.assertLess(refd, 0.1)


class T5VerdictTotals(unittest.TestCase):
    def test_totals_and_stated_headroom_ratios(self):
        _, css_aging, css_tcr = css_terms()
        _, wsl_aging, wsl_tcr = wsl_terms()
        gain, refd = minor_terms()
        css_total = css_aging + css_tcr + gain + refd                # ~13.0
        wsl_total = wsl_aging + wsl_tcr + gain + refd                # ~524.3
        self.assertAlmostEqual(css_total, 13.0, delta=0.2)
        self.assertAlmostEqual(wsl_total, 524.3, delta=1.0)
        self.assertLess(css_total, GATE_PROMOTE_UOHM)
        self.assertGreater(wsl_total, GATE_PROMOTE_UOHM)
        # the doc's stated total-based ratios, pinned exactly
        self.assertAlmostEqual(GATE_PROMOTE_UOHM / css_total, 23.0, delta=0.5)
        self.assertAlmostEqual(SIGNAL_UOHM / css_total, 76.7, delta=1.5)

    def test_crossing_is_on_the_aging_term_only(self):
        _, _, css_tcr = css_terms()
        _, _, wsl_tcr = wsl_terms()
        gain, refd = minor_terms()
        for t in (css_tcr, wsl_tcr, gain, refd):
            self.assertLess(t, SIGNAL_UOHM / 50)

    def test_gate_chain_consistency_with_ratified_entries(self):
        d = _entry("fault-phenomenology.json", "dvdi.requirement_tier_verdict")["value"]
        self.assertIn("0.3 mOhm", d["validity_gates"]["promote_standard_to_full"])
        self.assertIn("0.7 mOhm", d["validity_gates"]["restrict_to_pro_only"])
        self.assertIn("1 mOhm", d["requirement"])


if __name__ == "__main__":
    unittest.main()
