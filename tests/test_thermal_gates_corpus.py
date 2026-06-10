#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  Anchor fixture for the thermal-gates corpus entries (cluster-1 delivery,
#  docs/research/thermal-gates-derivation-2026-06-10.md). This file IS the
#  AM-02 fixture the Class A entries point at: change any value in
#  corpus/staging/general/{thermal-gates,bom-ratings}.json and the coherence
#  assertions below fire. Host-runnable, dependency-free.
# ============================================================================
import json
import math
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATES = os.path.join(ROOT, "corpus", "staging", "general", "thermal-gates.json")
BOM = os.path.join(ROOT, "corpus", "staging", "general", "bom-ratings.json")


def _load(path):
    return {e["id"]: e for e in json.load(open(path))}


def onderdonk_j(t_s):
    """J_fuse [A/mm2] = 1550*sqrt(0.0346/t) -- the entry's curve, 20C start."""
    return 1550.0 * math.sqrt(0.0346 / t_s)


class T1CoherenceTriple(unittest.TestCase):
    """ambient + rise (+ transient) vs ceiling -- the doc's coherence check."""

    def setUp(self):
        self.g = _load(GATES)

    def test_steady_state_point(self):
        amb = self.g["thermal.gates.design_ambient"]["value"]["degC"]
        rise = self.g["thermal.gates.dt_max_rise"]["value"]
        ceil = self.g["thermal.gates.t_max_ceiling"]["value"]
        self.assertEqual(amb + rise, 80)                       # 50 + 30
        self.assertLessEqual(amb + rise, ceil - 20,            # target <= ceiling - transient
                             "steady state must leave the +20C transient inside the ceiling")

    def test_transient_touches_but_never_exceeds(self):
        amb = self.g["thermal.gates.design_ambient"]["value"]["degC"]
        rise = self.g["thermal.gates.dt_max_rise"]["value"]
        ceil = self.g["thermal.gates.t_max_ceiling"]["value"]
        self.assertLessEqual(amb + rise + 20, ceil)            # 100 <= 105

    def test_cutover_clause_is_exactly_the_threshold(self):
        """The 55C cutover exists because 55+30+20 touches the ceiling."""
        v = self.g["thermal.gates.design_ambient"]["value"]
        ceil = self.g["thermal.gates.t_max_ceiling"]["value"]
        rise = self.g["thermal.gates.dt_max_rise"]["value"]
        self.assertEqual(v["cutover_if_measured_ambient_above_C"], 55)
        self.assertGreaterEqual(v["cutover_if_measured_ambient_above_C"] + rise + 20, ceil,
                                "the cutover threshold is where transient touches the ceiling")
        # and the cut budget restores margin: 55 + 20 + 20 = 95 < 105
        self.assertLess(v["cutover_if_measured_ambient_above_C"]
                        + v["rise_budget_cuts_to_C"] + 20, ceil)


class T2MinOfBom(unittest.TestCase):
    """t_max_ceiling == min over the bom.rating.* sub-facts (the rule entry)."""

    def test_ceiling_is_min_of_bom(self):
        g, b = _load(GATES), _load(BOM)
        ratings = {
            "bom.rating.cap_electrolytic_105c": b["bom.rating.cap_electrolytic_105c"]["value"],
            "bom.rating.schottky_tj_125c": b["bom.rating.schottky_tj_125c"]["value"],
            "bom.rating.fr4_continuous_110c": b["bom.rating.fr4_continuous_110c"]["value"],
            "bom.rating.connector_minifit_105c": b["bom.rating.connector_minifit_105c"]["value"],
        }
        self.assertEqual(g["thermal.gates.t_max_ceiling"]["value"], min(ratings.values()),
                         "ceiling must re-derive as min-of-BOM (the rule-over-constant)")
        # the floor part is the 105C electrolytic (matched by the connector)
        self.assertEqual(ratings["bom.rating.cap_electrolytic_105c"], 105)

    def test_conservative_side_of_sb120_conflict(self):
        b = _load(BOM)
        self.assertEqual(b["bom.rating.schottky_tj_125c"]["value"], 125,
                         "the documented 125-vs-150 conflict resolves conservative")


class T3OnderdonkCurve(unittest.TestCase):
    """The fusing entry's curve: formula, table points, documented 0.5 s point."""

    def setUp(self):
        self.e = _load(GATES)["thermal.fusing.onderdonk_jt"]["value"]

    def test_documented_point_400_at_half_second(self):
        self.assertEqual(self.e["documented_point"], {"t_s": 0.5, "J_A_mm2": 400})
        self.assertAlmostEqual(onderdonk_j(0.5), 408, delta=4,
                               msg="400 A/mm2 is the ~0.5 s Onderdonk point (computed ~408)")

    def test_curve_points_match_formula(self):
        for p in self.e["curve_points_20C"]:
            self.assertAlmostEqual(onderdonk_j(p["t_s"]), p["J_A_mm2"],
                                   delta=0.02 * p["J_A_mm2"] + 3,
                                   msg="curve point %r drifted from the formula" % p)

    def test_hot_start_factor(self):
        """0.93 at exactly 80C: sqrt(log10(1063/254+1) ratio) -- the panel-found
        research-doc erratum (the doc's ~0.94 matches the 70C end of its bracket)."""
        ratio = math.sqrt(math.log10((1083 - 80) / (234 + 80) + 1)
                          / math.log10((1083 - 20) / (234 + 20) + 1))
        self.assertAlmostEqual(ratio, 0.933, places=3)
        self.assertAlmostEqual(self.e["hot_start_factor_80C"], 0.93, places=2)

    def test_monotone_decreasing(self):
        pts = self.e["curve_points_20C"]
        for a, b in zip(pts, pts[1:]):
            self.assertLess(a["t_s"], b["t_s"])
            self.assertGreater(a["J_A_mm2"], b["J_A_mm2"])


class T4DensitySplit(unittest.TestCase):
    """internal < external < via, and every gate sits under the fusing curve
    across its validity window (the backstop is above the operating gates)."""

    def setUp(self):
        self.g = _load(GATES)

    def test_geometry_ordering(self):
        vi = self.g["thermal.jmax.via_barrel"]["value"]
        ex = self.g["thermal.jmax.trace_external"]["value"]
        inr = self.g["thermal.jmax.trace_internal"]["value"]
        self.assertLess(inr, ex)
        self.assertLess(ex, vi)

    def test_gates_below_fusing_through_validity_window(self):
        vi = self.g["thermal.jmax.via_barrel"]["value"]
        # slowest point of the conservative-validity window: 10 s
        self.assertLess(vi, onderdonk_j(10.0),
                        "the operating density gates must sit under the fusing "
                        "backstop everywhere in its validity window")

    def test_flat_100_was_nonconservative_for_traces(self):
        """The reason the flat gate retires: 100 exceeds both trace classes."""
        self.assertGreater(100, self.g["thermal.jmax.trace_external"]["value"])
        self.assertGreater(100, self.g["thermal.jmax.trace_internal"]["value"])


class T5TransientWindows(unittest.TestCase):
    def test_enumerated_windows(self):
        v = _load(GATES)["thermal.gates.transient_allowance"]["value"]
        wins = {tuple(c["window_s"]) for c in v["classes"]}
        self.assertEqual(wins, {(0, 0.01), (0.1, 0.5), (1, 10), (10, None)})
        self.assertIn("interstitial_rule", v)

    def test_budgeted_windows_carry_dt_and_tau(self):
        v = _load(GATES)["thermal.gates.transient_allowance"]["value"]
        for c in v["classes"]:
            if "dT_C" in c:
                self.assertEqual(c["dT_C"], 20)
                self.assertEqual(len(c["tau_s"]), 2)
                self.assertLess(c["tau_s"][0], c["tau_s"][1])

    def test_fast_window_defers_to_fusing(self):
        v = _load(GATES)["thermal.gates.transient_allowance"]["value"]
        fast = next(c for c in v["classes"] if tuple(c["window_s"]) == (0, 0.01))
        self.assertEqual(fast["ref"], "thermal.fusing.onderdonk_jt")


class T6TypingDiscipline(unittest.TestCase):
    """The typing calls this batch rides on (rulings D1 + the as-built taxonomy)."""

    def test_h_entries_never_apply_to_physics(self):
        for e in list(_load(GATES).values()) + list(_load(BOM).values()):
            if e["class"] == "H":
                self.assertNotIn("physics", e["applies_to"],
                                 "%s: H never feeds a deterministic consumer" % e["id"])

    def test_h_entries_carry_no_compile_block(self):
        for e in list(_load(GATES).values()) + list(_load(BOM).values()):
            if e["class"] == "H":
                self.assertNotIn("compile", e,
                                 "%s: an H compile block re-engages AM-02 (D1)" % e["id"])

    def test_class_a_entries_carry_resolving_fixture(self):
        for e in list(_load(GATES).values()) + list(_load(BOM).values()):
            if e["class"] == "A" and not e.get("migrated"):
                self.assertTrue(e.get("fixture"), "%s: new Class A needs AM-02" % e["id"])
                self.assertTrue(os.path.exists(os.path.join(ROOT, e["fixture"])),
                                "%s: fixture must resolve" % e["id"])


if __name__ == "__main__":
    unittest.main()
