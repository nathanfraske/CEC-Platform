# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Wave-1 T1b thermal-scenario/statistics module tests (cec_thermal_scenarios.py).
# Host-runnable, pcbnew-free (the module never loads a board -- it wraps the
# JointSpec/joint_solve/dt_ipc primitives directly). Every number asserted here
# was independently hand-verified against cec_synth_pipeline.joint_solve before
# being written down (see the task transcript); this file is the anchor going
# forward -- a drift in the joint model's own numbers (rating, contact R,
# segment geometry) will legitimately move these, and that's fine, so long as
# it moves in a way this file's own cross-checks (e.g. the Onderdonk corpus
# comparison, the E1/E2 convergence check) still hold.
import json
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.dont_write_bytecode = True

import cec_thermal_scenarios as T  # noqa: E402
import cec_synth_pipeline as S     # noqa: E402

GATES_JSON = os.path.join(ROOT, "corpus", "staging", "general", "thermal-gates.json")


# ============================================================ primitives
class TCurrentDivider(unittest.TestCase):
    def test_equal_resistances_split_evenly(self):
        got = T.current_divider([1.0e-3, 1.0e-3, 1.0e-3], 30.0)
        for i in got:
            self.assertAlmostEqual(i, 10.0, places=6)

    def test_unequal_resistances_split_by_conductance(self):
        # R=[1,2] ohm, Itot=3A -> G=[1,0.5], sum=1.5 -> I=[2,1]
        got = T.current_divider([1.0, 2.0], 3.0)
        self.assertAlmostEqual(got[0], 2.0, places=6)
        self.assertAlmostEqual(got[1], 1.0, places=6)

    def test_zero_resistance_degenerate_short(self):
        got = T.current_divider([0.0, 1.0, 0.0], 10.0)
        self.assertAlmostEqual(got[0], 5.0)
        self.assertAlmostEqual(got[1], 0.0)
        self.assertAlmostEqual(got[2], 5.0)

    def test_empty_group(self):
        self.assertEqual(T.current_divider([], 10.0), [])


class TFamilyData(unittest.TestCase):
    """Sanity-check FAMILY_JOINT_GROUPS against the ratified addendum-7 counts
    and margin percentages (blade-fit-check-2026-07-04.md addendum 7 SS F.2)."""

    def test_joint_counts_match_ratified_totals(self):
        self.assertEqual(sum(g["n"] for g in T.FAMILY_JOINT_GROUPS["atx24"]), 10)
        self.assertEqual(sum(g["n"] for g in T.FAMILY_JOINT_GROUPS["eps"]), 6)
        self.assertEqual(sum(g["n"] for g in T.FAMILY_JOINT_GROUPS["pcie"]), 6)

    def test_margin_percentages_match_the_doc(self):
        # atx24: 12V 191%, 5V 153%, 3V3 191%, 5VSB 382%, GND 127.2%
        expect = {"+12V": 190.8, "+5V": 152.7, "+3V3": 190.8, "+5VSB": 381.7, "GND": 127.2}
        for grp in T.FAMILY_JOINT_GROUPS["atx24"]:
            I = grp["I_total_A"] / grp["n"]
            self.assertAlmostEqual(T.rail_margin_pct(I), expect[grp["rail"]], delta=0.2)
        # eps 132.1%, pcie 176.2%
        for grp in T.FAMILY_JOINT_GROUPS["eps"]:
            self.assertAlmostEqual(T.rail_margin_pct(grp["I_total_A"] / grp["n"]), 132.1, delta=0.2)
        for grp in T.FAMILY_JOINT_GROUPS["pcie"]:
            self.assertAlmostEqual(T.rail_margin_pct(grp["I_total_A"] / grp["n"]), 176.2, delta=0.2)

    def test_nominal_group_solve_matches_joint_solve_directly(self):
        for fam, grp in T._iter_rails():
            _, recs = T.group_solve(fam, grp["rail"])
            I_nom = grp["I_total_A"] / grp["n"]
            direct = S.joint_solve(T._BASE_SPEC, I_nom, T.AMBIENT_C)
            for r in recs:
                self.assertAlmostEqual(r["dT"], direct["dT"], delta=0.05)


# ============================================================ E1: N-1 sweep
class TE1N1Sweep(unittest.TestCase):
    """The honest headline: the ratified iteration-7 counts were sized for
    load (>=125% margin), not for N-1 redundancy. Only PCIe's 3-joint groups
    (176% margin) survive a single-joint loss inside the 30C policy; atx24 and
    EPS do not survive N-1 on ANY of their multi-joint rails, and atx24's two
    single-joint rails (+12V, +5VSB) have no redundancy to lose at all."""

    def test_single_joint_rails_are_open_circuit_not_pass(self):
        rep = T.n1_sweep("atx24")
        by_rail = {r["rail"]: r for r in rep["rails"]}
        for rail in ("+12V", "+5VSB"):
            self.assertTrue(by_rail[rail]["open_circuit_on_loss"])
            self.assertFalse(by_rail[rail]["redundant"])
            self.assertFalse(by_rail[rail]["n1_survives_within_policy"])

    def test_atx24_multijoint_rails_fail_n1(self):
        rep = T.n1_sweep("atx24")
        by_rail = {r["rail"]: r for r in rep["rails"]}
        # 5V: 30A/1 survivor = 30A -> dT well past 30C
        self.assertAlmostEqual(by_rail["+5V"]["I_per_survivor_A"], 30.0, delta=0.01)
        self.assertFalse(by_rail["+5V"]["n1_survives_within_policy"])
        # 3V3: 24A/1 survivor = 24A
        self.assertAlmostEqual(by_rail["+3V3"]["I_per_survivor_A"], 24.0, delta=0.01)
        self.assertFalse(by_rail["+3V3"]["n1_survives_within_policy"])
        # GND: the ratified 127.2% hairline -- 72A/3 survivors = 24A/joint
        self.assertAlmostEqual(by_rail["GND"]["I_per_survivor_A"], 24.0, delta=0.01)
        self.assertFalse(by_rail["GND"]["n1_survives_within_policy"])

    def test_eps_fails_n1(self):
        rep = T.n1_sweep("eps")
        for r in rep["rails"]:
            self.assertAlmostEqual(r["I_per_survivor_A"], 26.0, delta=0.01)
            self.assertFalse(r["n1_survives_within_policy"])

    def test_pcie_survives_n1(self):
        rep = T.n1_sweep("pcie")
        for r in rep["rails"]:
            self.assertAlmostEqual(r["I_per_survivor_A"], 19.5, delta=0.01)
            self.assertTrue(r["n1_survives_within_policy"])
            self.assertLess(r["worst_survivor_dT_C"], 30.0)

    def test_only_pcie_fully_survives_across_the_platform(self):
        survives = {fam: all(r["n1_survives_within_policy"] for r in T.n1_sweep(fam)["rails"])
                   for fam in T.ALL_FAMILIES}
        self.assertEqual(survives, {"atx24": False, "eps": False, "pcie": True})


# ============================================================ E3: unequal sharing
class TE3UnequalSharing(unittest.TestCase):
    def test_cv_zero_reproduces_nominal_deterministic_dT(self):
        for fam, grp in T._iter_rails():
            v = T.unequal_sharing_worst_at_cv(fam, grp["rail"], 0.0, n_trials=5)
            direct = S.joint_solve(T._BASE_SPEC, grp["I_total_A"] / grp["n"], T.AMBIENT_C)
            self.assertAlmostEqual(v, direct["dT"], delta=0.05)

    def test_worst_dt_nondecreasing_with_spread(self):
        prev = -1.0
        for cv in (0.0, 0.1, 0.3, 0.6):
            v = T.unequal_sharing_worst_at_cv("atx24", "GND", cv, n_trials=200)
            self.assertGreaterEqual(v + 1e-9, prev)
            prev = v

    def test_hairline_rails_have_a_finite_threshold(self):
        # atx24 GND (127.2%) and eps (132.1%) are the two ratified hairlines --
        # both must cross the 30C gate at a plausible (<1.0) contact-R spread.
        thr_gnd = T.find_unequal_sharing_threshold("atx24", "GND", n_trials=250)
        thr_eps = T.find_unequal_sharing_threshold("eps", "+12V", n_trials=250)
        self.assertIsNotNone(thr_gnd)
        self.assertIsNotNone(thr_eps)
        self.assertLess(thr_gnd, 1.0)
        self.assertLess(thr_eps, 1.0)
        # the tighter-margin rail (GND, 127.2%) must fail at a SMALLER spread
        # than the healthier eps rail (132.1%) -- ordering must track margin.
        self.assertLess(thr_gnd, thr_eps)

    def test_healthy_margin_rails_have_no_threshold_within_range(self):
        # pcie (176.2%) and atx24's +5V/+3V3/+5VSB (>=153%) must NOT cross the
        # gate anywhere in a physically-plausible contact-R spread (cv_max=2.0
        # already spans an implausibly wide manufacturing tolerance).
        for fam, rail in (("pcie", "+12V"), ("pcie", "GND"),
                         ("atx24", "+5V"), ("atx24", "+3V3"), ("atx24", "+5VSB")):
            thr = T.find_unequal_sharing_threshold(fam, rail, n_trials=200)
            self.assertIsNone(thr, "%s/%s unexpectedly has a sub-2.0 CV threshold" % (fam, rail))

    def test_reproducible_given_same_seed(self):
        a = T.find_unequal_sharing_threshold("atx24", "GND", seed=7, n_trials=150)
        b = T.find_unequal_sharing_threshold("atx24", "GND", seed=7, n_trials=150)
        self.assertEqual(a, b)

    def test_single_joint_rail_is_immune_to_sharing_variance(self):
        # n=1: there is only one path, so a contact-R DISTRIBUTION cannot
        # create unequal SHARING (nothing to share with) -- the worst-at-cv
        # value must still shift (R itself still affects that one joint's own
        # dT) but a threshold search is about REDISTRIBUTION, which cannot
        # occur; this at least must not crash and must remain finite.
        v = T.unequal_sharing_worst_at_cv("atx24", "+5VSB", 0.3, n_trials=50)
        self.assertGreater(v, 0.0)
        self.assertLess(v, 999.0)


# ============================================================ E2: partial seat
class TE2PartialSeat(unittest.TestCase):
    def test_single_joint_rail_is_a_genuine_localized_hotspot(self):
        thr = T.partial_seat_threshold("atx24", "+12V")
        self.assertFalse(thr["redundant"])
        self.assertFalse(thr["self_limiting"])
        self.assertIsNotNone(thr["policy_fail_R_mohm"])
        self.assertIsNotNone(thr["fusing_class_R_mohm"])
        self.assertAlmostEqual(thr["policy_fail_R_mohm"], 4.81, delta=0.1)
        self.assertAlmostEqual(thr["fusing_class_R_mohm"], 12.71, delta=0.1)
        self.assertLess(thr["policy_fail_R_mohm"], thr["fusing_class_R_mohm"])

    def test_5vsb_single_joint_thresholds(self):
        thr = T.partial_seat_threshold("atx24", "+5VSB")
        self.assertAlmostEqual(thr["policy_fail_R_mohm"], 20.65, delta=0.2)
        self.assertAlmostEqual(thr["fusing_class_R_mohm"], 52.35, delta=0.2)

    def test_redundant_rails_are_self_limiting_no_threshold(self):
        for fam, rail in (("atx24", "+5V"), ("atx24", "+3V3"), ("atx24", "GND"),
                         ("eps", "+12V"), ("eps", "GND"), ("pcie", "+12V"), ("pcie", "GND")):
            thr = T.partial_seat_threshold(fam, rail)
            self.assertTrue(thr["redundant"])
            self.assertTrue(thr["self_limiting"])
            self.assertIsNone(thr["policy_fail_R_mohm"])
            self.assertIsNone(thr["fusing_class_R_mohm"])

    def test_degraded_joint_dT_rises_monotonically_when_no_redundancy(self):
        sweep = T.partial_seat_sweep("atx24", "+12V")["sweep"]
        prev = -1.0
        for row in sweep:
            self.assertGreater(row["degraded_dT_C"], prev)
            prev = row["degraded_dT_C"]

    def test_degraded_joint_is_self_limiting_when_redundant(self):
        # atx24 GND (n=4): as the ONE degraded joint's R rises, ITS OWN dT
        # must FALL (current sheds to the healthy neighbours) while the
        # SURVIVORS' dT must RISE -- the opposite-signed trend that
        # distinguishes a real localized hotspot from a self-protecting group.
        sweep = T.partial_seat_sweep("atx24", "GND")["sweep"]
        degraded = [row["degraded_dT_C"] for row in sweep]
        survivors = [row["worst_survivor_dT_C"] for row in sweep]
        self.assertLess(degraded[-1], degraded[0])
        self.assertGreater(survivors[-1], survivors[0])

    def test_partial_seat_converges_to_n1_as_r_grows_large(self):
        # As the degraded joint's R -> very large (an effectively-open joint),
        # the healthy survivors' dT must converge to the E1 N-1 result for the
        # SAME rail -- the two engines describing the same physical limit.
        _, recs = T.group_solve("atx24", "GND", contact_Rs=[T._BASE_SPEC.contact_R_ohm] * 3
                                + [10.0])  # 10 ohm ~ effectively open
        worst_survivor = max(recs[:-1], key=lambda r: r["dT"])
        n1 = T.n1_sweep("atx24")
        gnd = next(r for r in n1["rails"] if r["rail"] == "GND")
        self.assertAlmostEqual(worst_survivor["dT"], gnd["worst_survivor_dT_C"], delta=0.5)


# ============================================================ E4: I2t / Onderdonk
class TE4Onderdonk(unittest.TestCase):
    """Cross-validates the rigorous adiabatic derivation against this repo's
    OWN already-anchored Onderdonk curve (corpus thermal.fusing.onderdonk_jt /
    tests/test_thermal_gates_corpus.py -- read here, never edited)."""

    def setUp(self):
        entries = {e["id"]: e for e in json.load(open(GATES_JSON))}
        self.curve = entries["thermal.fusing.onderdonk_jt"]["value"]

    def test_matches_the_anchored_copper_curve_within_one_percent(self):
        for p in self.curve["curve_points_20C"]:
            mine = T.adiabatic_fuse_current_density(p["t_s"], material="copper", ambient_C=20.0)
            self.assertAlmostEqual(mine / p["J_A_mm2"], 1.0, delta=0.01,
                                   msg="Onderdonk cross-check drifted at t=%s" % p["t_s"])

    def test_documented_half_second_point(self):
        mine = T.adiabatic_fuse_current_density(0.5, material="copper", ambient_C=20.0)
        self.assertAlmostEqual(mine, self.curve["documented_point"]["J_A_mm2"], delta=10)

    def test_monotone_decreasing_with_duration(self):
        prev = 1e18
        for t in (0.001, 0.01, 0.1, 0.5, 1.0, 5.0):
            j = T.adiabatic_fuse_current_density(t, material="copper")
            self.assertLess(j, prev)
            prev = j

    def test_hotter_start_lowers_fusing_density(self):
        cold = T.adiabatic_fuse_current_density(0.5, material="copper", ambient_C=20.0)
        hot = T.adiabatic_fuse_current_density(0.5, material="copper", ambient_C=80.0)
        self.assertLess(hot, cold)

    def test_brass_weakest_segment_is_tails_solder(self):
        weakest = min(T._BASE_SPEC.segments, key=lambda s: s.cross_mm2)
        self.assertEqual(weakest.name, "tails_solder")
        self.assertAlmostEqual(weakest.cross_mm2, 1.148, delta=0.01)

    def test_default_fault_envelope_withstands_on_every_family(self):
        # The joint's own brass conductors comfortably survive the (UNVERIFIED,
        # illustrative) fault envelope on every family -- worth reporting
        # explicitly: the joint is not this platform's fault-withstand
        # bottleneck under these assumptions.
        for rec in T.i2t_report():
            self.assertTrue(rec["withstands"], rec)
            self.assertGreater(rec["withstand_margin"], 1.0)

    def test_check_has_real_teeth_an_extreme_fault_fails(self):
        rec = T.i2t_fault_withstand("atx24", "GND", multiplier=500.0, duration_s=5.0)
        self.assertFalse(rec["withstands"])
        self.assertLess(rec["withstand_margin"], 1.0)


# ============================================================ C1/C2: tolerance corners
class TToleranceCorner(unittest.TestCase):
    def test_zero_corner_matches_nominal_exactly(self):
        rec = T.tolerance_corner("atx24", "GND", copper_thin_pct=0.0, plating_thin_pct=0.0)
        self.assertAlmostEqual(rec["nominal_dT_C"], rec["corner_dT_C"], delta=0.01)
        self.assertAlmostEqual(rec["dT_erosion_C"], 0.0, delta=0.01)

    def test_thin_corner_erodes_margin_on_every_rail(self):
        for rec in T.tolerance_corner_report():
            self.assertGreater(rec["corner_dT_C"], rec["nominal_dT_C"])
            self.assertGreater(rec["dT_erosion_C"], 0.0)

    def test_corner_still_passes_policy_at_the_default_20_percent(self):
        # None of the ratified rails are pushed OVER the gate by a lone -20%
        # copper/plating corner alone (a real, if modest, finding).
        for rec in T.tolerance_corner_report():
            self.assertTrue(rec["corner_policy_pass"], rec)

    def test_scaled_spec_isolates_the_R_effect_rth_held_fixed(self):
        base = T._BASE_SPEC
        thin = T.scaled_joint_spec(base, cross_factors={"blade_63951": 0.5})
        self.assertEqual(thin.calibrated_rth(), base.calibrated_rth())
        self.assertGreater(thin.R_total_ohm(20.0), base.R_total_ohm(20.0))


# ============================================================ F1/F2: Monte Carlo
class TMonteCarlo(unittest.TestCase):
    def test_degenerate_zero_spread_reproduces_deterministic_exactly(self):
        zero = {"contact_cv": 0.0, "copper_thickness_sigma": 0.0,
               "via_plating_sigma": 0.0, "ambient_sigma_C": 0.0}
        mc = T.monte_carlo_margin("atx24", "GND", n_trials=40, sigmas=zero)
        direct = S.joint_solve(T._BASE_SPEC, 72.0 / 4, T.AMBIENT_C)
        for key in ("dT_mean_C", "dT_p05_C", "dT_p50_C", "dT_p95_C", "dT_worst_C"):
            self.assertAlmostEqual(mc[key], direct["dT"], delta=0.01, msg=key)
        self.assertIn(mc["confidence_pass"], (0.0, 1.0))
        self.assertEqual(mc["confidence_pass"], 1.0 if direct["dT"] <= T.DT_MAX_C else 0.0)

    def test_reproducible_given_same_seed(self):
        a = T.monte_carlo_margin("eps", "+12V", n_trials=150, seed=99)
        b = T.monte_carlo_margin("eps", "+12V", n_trials=150, seed=99)
        self.assertEqual(a, b)

    def test_teeth_widened_distribution_drops_confidence_below_gate(self):
        default = T.monte_carlo_margin("atx24", "GND", n_trials=400, seed=T.DEFAULT_SEED)
        widened_sigmas = {"contact_cv": 0.6, "copper_thickness_sigma": 0.3,
                          "via_plating_sigma": 0.3, "ambient_sigma_C": 3.0}
        widened = T.monte_carlo_margin("atx24", "GND", n_trials=400, seed=T.DEFAULT_SEED,
                                       sigmas=widened_sigmas)
        self.assertTrue(T.mc_passes_confidence_gate(default, min_confidence=0.95))
        self.assertFalse(T.mc_passes_confidence_gate(widened, min_confidence=0.95))
        self.assertLess(widened["confidence_pass"], default["confidence_pass"])

    def test_confidence_gate_helper(self):
        self.assertTrue(T.mc_passes_confidence_gate({"confidence_pass": 0.95}, min_confidence=0.9))
        self.assertFalse(T.mc_passes_confidence_gate({"confidence_pass": 0.5}, min_confidence=0.9))

    def test_sensitivity_ranking_covers_all_four_axes_and_matches_baseline(self):
        sens = T.sensitivity_ranking("atx24", "GND", n_trials=30)
        self.assertEqual(set(sens["ranking"]), set(T.MC_DEFAULT_SIGMAS))
        direct = S.joint_solve(T._BASE_SPEC, 72.0 / 4, T.AMBIENT_C)
        self.assertAlmostEqual(sens["baseline_dT_C"], direct["dT"], delta=0.05)

    def test_contact_cv_is_the_dominant_sensitivity_axis_on_the_gnd_hairline(self):
        # Matches the E3 finding: contact-R spread is the single most
        # margin-eroding input on the tightest-margin rail.
        sens = T.sensitivity_ranking("atx24", "GND", n_trials=80, seed=3)
        self.assertEqual(sens["ranking"][0], "contact_cv")


# ============================================================ overall determinism
class TDeterminism(unittest.TestCase):
    def test_run_all_scenarios_is_reproducible(self):
        a = T.run_all_scenarios(("atx24",), seed=5)
        b = T.run_all_scenarios(("atx24",), seed=5)
        self.assertEqual(a, b)

    def test_no_wall_clock_or_unseeded_random_leaks_into_defaults(self):
        # Two default (no explicit seed) calls must be identical -- DEFAULT_SEED
        # is a real fixed default, not merely documented.
        a = T.run_all_scenarios(("pcie",))
        b = T.run_all_scenarios(("pcie",))
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main(verbosity=2)
