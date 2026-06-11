#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  Anchor fixture for the cluster-6 + cluster-5-item-4 corpus entries
#  (docs/research/gpu-12vhpwr-fault-phenomenology-2026-06-10.md + the owner
#  decision slate, 2026-06-10). This file IS the AM-02 fixture the entries
#  point at: recomputes the excursion curve, the Malucci conversion, the
#  power-per-mOhm correction, the alarm ordering, and the dV/dI gate chain.
#  Host-runnable, dependency-free.
# ============================================================================
import json
import math
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAULT = os.path.join(ROOT, "corpus", "staging", "general", "fault-phenomenology.json")
STAB = os.path.join(ROOT, "corpus", "staging", "general", "stability-terms.json")
MEAS = os.path.join(ROOT, "corpus", "staging", "general", "measurement-claims.json")


def _load(path):
    return {e["id"]: e for e in json.load(open(path))}


def aic_R(t_us):
    """Intel ATX 3.0 Table 3-1 add-in-card excursion curve."""
    return 3.0 if t_us <= 100 else 4.0 - 0.2171 * math.log(t_us)


class T1ExcursionCurve(unittest.TestCase):
    def setUp(self):
        self.v = _load(FAULT)["atx3.aic_excursion_curve"]["value"]

    def test_curve_points_reproduce(self):
        self.assertAlmostEqual(aic_R(1000), 2.5, delta=0.01)       # 1 ms
        self.assertAlmostEqual(aic_R(10000), 2.0, delta=0.01)      # 10 ms
        self.assertAlmostEqual(aic_R(1000000), 1.0, delta=0.01)    # 1 s
        for p in self.v["points"]:
            t = {"1ms": 1000, "10ms": 10000, "1s": 1000000}[p["T"]]
            self.assertAlmostEqual(aic_R(t), p["R"], delta=0.01)

    def test_continuous_at_100us_boundary(self):
        """R = 4 - 0.2171*ln(100) = 3.00 -- the formula meets the plateau."""
        self.assertAlmostEqual(4.0 - 0.2171 * math.log(100), 3.0, delta=0.01)
        self.assertEqual(self.v["R_below_100us"], 3.0)

    def test_psu_table_duty_cycles_rev21(self):
        """The source-conflict ruling: rev 2.1 duties (5/8/12.5/25), not 10%."""
        rows = _load(FAULT)["atx3.psu_excursion_tables"]["value"][
            "psu_over_450w_with_12v2x6"]
        duties = [r.get("test_duty_pct") for r in rows if "test_duty_pct" in r]
        self.assertEqual(duties, [5, 8, 12.5, 25])


class T2Malucci(unittest.TestCase):
    def setUp(self):
        self.v = _load(FAULT)["conn.malucci_runaway_onset"]["value"]

    def test_resistance_conversion(self):
        """32 mV onset at the 9 A class / 9.2 A = ~3.5 mOhm rise."""
        self.assertAlmostEqual(self.v["onset_at_9A_V"] / 9.2 * 1000,
                               self.v["onset_resistance_rise_mohm_at_9p2A"], delta=0.1)

    def test_onset_window_above_baseline(self):
        lo, hi = self.v["onset_contact_drop_change_V"]
        self.assertEqual((lo, hi), (0.01, 0.03))
        self.assertLess(self.v["healthy_baseline_mohm"],
                        self.v["onset_resistance_rise_mohm_at_9p2A"])
        self.assertLess(self.v["onset_statistical_avg_V"], self.v["tin_melting_voltage_V"])


class T3PowerPerMohm(unittest.TestCase):
    """The owner-erratum correction entry: P = I^2 * dR."""

    def test_correct_figure(self):
        v = _load(FAULT)["conn.power_per_mohm"]["value"]
        self.assertAlmostEqual(9.2 ** 2 * 0.001, 0.085, delta=0.001)
        self.assertEqual(v["W_per_mohm_at_9p2A"], 0.085)

    def test_old_figure_is_28A_territory(self):
        self.assertAlmostEqual(28 ** 2 * 0.001, 0.78, delta=0.01)


class T4AlarmThresholds(unittest.TestCase):
    def setUp(self):
        self.v = _load(FAULT)["alarm.12vhpwr_per_pin"]["value"]
        self.r = _load(FAULT)["conn.12vhpwr_pin_ratings"]["value"]

    def test_ordering(self):
        """balanced 8.3 < rating 9.2 <= WARN 9.5 < ALARM 11 < ceiling 12 << failure 22"""
        balanced = 600.0 / 12 / 6                                   # 600 W / 12 V / 6 pairs
        self.assertAlmostEqual(balanced, 8.33, delta=0.01)
        self.assertLess(balanced, self.r["12vhpwr_A_per_pin"])
        self.assertLessEqual(self.r["12vhpwr_A_per_pin"], self.v["warn_A_sustained"])
        self.assertEqual(self.v["warn_A_sustained"], self.r["12v2x6_A_per_pin"])
        self.assertLess(self.v["warn_A_sustained"], self.v["alarm_A_sustained"])
        self.assertLess(self.v["alarm_A_sustained"], self.v["instantaneous_ceiling_A"])

    def test_critical_fires_on_documented_failure(self):
        """der8auer's failing cable must trip the imbalance trigger."""
        wires = _load(FAULT)["evidence.gpu_transient_measured"]["value"][
            "der8auer_failing_cable_A_per_wire"]
        ratio = max(wires) / (sum(wires) / len(wires))
        self.assertGreater(ratio, 2.0,
                           "the CRITICAL imbalance ratio must fire on the one "
                           "documented failure capture")

    def test_hog_default_tightened(self):
        """OQ-59 ruling: 11 A sustained is the hard alarm; 12 A instantaneous only."""
        self.assertEqual(self.v["alarm_A_sustained"], 11)
        self.assertEqual(self.v["instantaneous_ceiling_A"], 12)
        self.assertEqual(self.v["alarm_min_duration_s"], 1)


class T5CaptureDisposition(unittest.TestCase):
    def test_oversample_clears_the_corner(self):
        """50 kHz SADC floor -> 25 kHz Nyquist > the 16.9 kHz RC corner."""
        self.assertGreater(50000 / 2, 16900)

    def test_disposition_fields(self):
        v = _load(FAULT)["capture.10khz_disposition"]["value"]
        self.assertIn("10 kHz", v["keep"])
        self.assertIn("DE-SCOPED", v["descope"])
        self.assertIn("OVERSAMPLE-AND-DECIMATE", v["path"])
        self.assertIn("2-5 kHz", v["fallback"])
        self.assertIn("spec-revision candidate", v["documentation_rule"])


class T6DvdiChain(unittest.TestCase):
    def setUp(self):
        self.d = _load(FAULT)["dvdi.requirement_tier_verdict"]["value"]
        self.stab = _load(STAB)

    def test_gate_ordering(self):
        """0.3 (promote) < 0.7 (restrict) < 1.0 (signal) < 3.5 (onset)."""
        onset = _load(FAULT)["conn.malucci_runaway_onset"]["value"][
            "onset_resistance_rise_mohm_at_9p2A"]
        self.assertLess(0.3, 0.7)
        self.assertLess(0.7, 1.0)
        self.assertLess(1.0, onset)
        self.assertIn("0.3 mOhm", self.d["validity_gates"]["promote_standard_to_full"])
        self.assertIn("0.7 mOhm", self.d["validity_gates"]["restrict_to_pro_only"])

    def test_margin_is_3x(self):
        self.assertIn("~3x", self.d["margin"])

    def test_crux_term_same_order_as_signal(self):
        """The WSL load-life additive (~0.5 mOhm) is the same order as the
        1 mOhm signal -- the documented reason the shunt BOM decides."""
        wsl = self.stab["stab.shunt_loadlife_tcr_vishay_wsl"]["value"]
        self.assertEqual(wsl["load_life_additive_mohm"], 0.5)
        self.assertGreater(wsl["load_life_additive_mohm"], 0.3)   # above the promote gate
        self.assertLess(wsl["load_life_additive_mohm"], 1.0)      # below the signal

    def test_tcr_ordering_css_beats_wsl_low_ohm(self):
        css = self.stab["stab.shunt_loadlife_bourns_css"]["value"]
        wsl = self.stab["stab.shunt_loadlife_tcr_vishay_wsl"]["value"]
        self.assertLess(css["tcr_ppm_per_C"],
                        wsl["tcr_component_ppm_per_C"]["1_to_2p9_mohm"])

    def test_targets_table_carries_stability_row(self):
        rows = _load(MEAS)["meas.targets.v1"]["value"]["rows"]
        stab = [r for r in rows if r["quantity"].startswith("stability")]
        self.assertEqual(len(stab), 1)
        self.assertEqual(stab[0]["conditions"]["ref"], "dvdi.requirement_tier_verdict")
        self.assertTrue(stab[0]["conditions"]["founders_ack"])


class T8LaneTopologyAndCapability(unittest.TestCase):
    """Owner ruling 2026-06-10 (lane/2 resolution): per-pin thresholds +
    pins_per_lane facts + the family-scoped capability consequences."""

    def test_pins_per_lane_facts(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import cec_facts as F
        self.assertEqual(F.pins_per_lane("12vhpwr-standard"), 1)
        self.assertEqual(F.pins_per_lane("12vhpwr-pro"), 1)
        self.assertEqual(F.pins_per_lane("eps-8pin"), 4)
        self.assertEqual(F.pins_per_lane("pcie-8pin-2port"), 3)
        self.assertEqual(F.pins_per_lane("pcie-8pin-3port"), 3)
        self.assertIsNone(F.pins_per_lane("hub-standard"))

    def test_alarm_entry_resolved_to_per_pin(self):
        v = _load(FAULT)["alarm.12vhpwr_per_pin"]["value"]
        self.assertIn("PER-PIN", v["per_pin_computation"])
        self.assertIn("PINS_PER_LANE", v["per_pin_computation"])
        self.assertNotIn("lane current / 2", v["per_pin_computation"],
                         "the slate's lane/2 is superseded by the per-pin ruling")

    def test_capability_entry_and_targets_row(self):
        cap = _load(FAULT)["capability.hog_detection_family_scope"]["value"]
        self.assertEqual(cap["per_pin_families"], ["12vhpwr-standard", "12vhpwr-pro"])
        self.assertIn("eps-8pin", cap["aggregate_families"])
        self.assertIn("pcie-8pin-2port", cap["aggregate_families"])
        self.assertIn("pcie-8pin-3port", cap["aggregate_families"])
        rows = _load(MEAS)["meas.targets.v1"]["value"]["rows"]
        imb = [r for r in rows if r["quantity"].startswith("imbalance")]
        self.assertEqual(len(imb), 1)
        self.assertEqual(imb[0]["conditions"]["ref"],
                         "capability.hog_detection_family_scope")

    def test_eps_pcie_threshold_gate(self):
        g = _load(FAULT)["alarm.eps_pcie_threshold_gate"]["value"]
        self.assertIn("pinned entries", g["gate"])
        self.assertIn("TERMINAL SERIES", g["reason"])

    def test_eval_verdicts_never_authority(self):
        e = _load(FAULT)["judge.eval_verdicts_not_authority"]
        self.assertEqual(e["applies_to"], ["judge"])
        self.assertIn("NEVER citable as design truth", e["value"]["rule"])
        self.assertIn("BY CONSTRUCTION", e["value"]["why"])


class T7CrossRefsAndTyping(unittest.TestCase):
    def test_cited_entry_ids_resolve(self):
        f = _load(FAULT)
        all_ids = set(f) | set(_load(STAB)) | set(_load(MEAS))
        for eid in ("conn.12vhpwr_pin_ratings", "conn.malucci_runaway_onset",
                    "evidence.gpu_transient_measured", "stab.shunt_loadlife_bourns_css",
                    "stab.shunt_loadlife_tcr_vishay_wsl", "conn.mating_cycle_life"):
            self.assertIn(eid, all_ids)

    def test_evidence_never_standalone(self):
        e = _load(FAULT)["evidence.gpu_transient_measured"]
        self.assertEqual(e["applies_to"], ["judge"])
        self.assertIn("NEVER STANDALONE AUTHORITY", e["notes"])

    def test_h_discipline(self):
        for e in list(_load(FAULT).values()) + list(_load(STAB).values()):
            if e["class"] == "H":
                self.assertNotIn("physics", e["applies_to"], e["id"])
                self.assertNotIn("compile", e, e["id"])

    def test_founders_ack_on_tier_verdict(self):
        self.assertIn("FOUNDERS-ACK REQUIRED BEFORE PROMOTION",
                      _load(FAULT)["dvdi.requirement_tier_verdict"]["notes"])


if __name__ == "__main__":
    unittest.main()
