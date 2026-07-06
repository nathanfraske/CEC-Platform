#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_thermal_scenarios.py -- T1b wave-1 thermal-solve capability: SCENARIO
#  and STATISTICAL analysis over the connector-JOINT element.
# ============================================================================
# Scope (docs/standard-tier-review/thermal-capabilities-implementation-2026-07-06.md,
# wave-1 assignment T1b): N-1 parallel-element loss sweep; unequal-sharing
# resistor-network solve over contact-R distributions (gate at worst-single-joint);
# I2t fault-withstand check; tolerance-corner runs (thin copper/plating); a
# seeded Monte Carlo margin-confidence wrapper + one-at-a-time sensitivity
# ranking. These realize Appendix B items E1/E2/E3/E4 and C1/C2/F1/F2/F3 of
# docs/standard-tier-review/thermal-solve-completeness-2026-07-06.md.
#
# THIS MODULE IS A LIBRARY WRAPPER, NOT A NEW SOLVER: every temperature number
# below is computed by calling cec_synth_pipeline's OWN, already-anchored
# functions -- JointSegment / JointSpec / joint_solve / joints_solve / dt_ipc /
# the RHO_*/ALPHA_* material constants -- never a re-implementation of the
# Picard/IPC physics. cec_synth_pipeline.py is CONSUMED, NEVER EDITED (per the
# wave-1 module-isolation discipline); this file and tests/test_thermal_scenarios.py
# are the entire footprint of this work. No other existing script or test is
# touched.
#
# THE JOINT MODEL THIS WRAPS (cec_synth_pipeline.joint_te_63951_63969(), the
# ONLY joint class the platform has calibrated so far -- see
# docs/standard-tier-review/blade-interconnect-thermal-2026-07-06.md): TE
# 63951-1 FASTON blade mated into a TE 63969-1 FASTON receptacle, contact R
# <=1 mOhm (spec max, TE 108-1706), Rth calibrated to reproduce the datasheet's
# own 22.9 A -> 30 degC-rise rating point (the SAME 30 degC-rise method the
# platform's own margin policy uses). The ratified iteration-7 joint counts and
# per-rail design-basis currents (docs/standard-tier-review/blade-fit-check-
# 2026-07-04.md addendum 7 SS F.2; cross-checked against the per-tab net maps in
# scripts/gen-output-daughterboard.py's FAMILIES table) are reproduced below as
# FAMILY_JOINT_GROUPS -- this is real, ratified, owner-signed-off platform data,
# not an invented test fixture.
#
# DETERMINISM (hard rule): there is NO wall-clock or unseeded randomness
# anywhere in this file. Every stochastic function takes an explicit `seed`
# (or `rng`) parameter; DEFAULT_SEED below is the single documented default a
# caller gets if it omits the argument, so a bare call is still 100%
# reproducible. Bisection searches (E3's CV threshold, E2's R threshold) reuse
# ONE fixed seed per search so every candidate point in the search is evaluated
# against the IDENTICAL underlying random draw sequence -- this is what makes
# the threshold-finding monotonic and stable (see the E3 section docstring).
#
# UNVERIFIED / assumption markers used throughout (grep for "UNVERIFIED"):
#   - the fault-current envelope in the E4 section (no real PSU/GPU OCP
#     let-through data exists for this platform yet);
#   - the brass melting point / density / specific heat used to extend the
#     Onderdonk-class adiabatic relation from copper (its empirically-validated
#     material) to the joint's brass conductors;
#   - the "fusing-class" temperature marker used by the E2 partial-seat sweep
#     (it reuses cec_synth_pipeline.physics_gates()'s OWN existing
#     T_max_transient_C convention -- t_max + 20 = 125 degC -- rather than
#     inventing a new number, but applying a TRACE transient-allowance ceiling
#     to a CONNECTOR JOINT is an extension, not a joint-specific validated
#     fusing point).
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_synth_pipeline as S  # noqa: E402  -- the library this module wraps


# ============================================================ constants / policy
# DEFAULT_SEED: the single reproducible default for every seeded function in this
# module. Chosen as the module's authorship date (2026-07-06) written as an int
# -- memorable, arbitrary, and NEVER used as a source of "real" randomness (it
# is a determinism anchor, not a security or statistical-independence property).
DEFAULT_SEED = 20260706

# Margin policy (CLAUDE.md / blade-fit-check addendum 7 SS F.2): connector
# continuous rating >= 125% of sustained worst case, at the SAME 30 degC-rise
# method the joint's own Rth is calibrated against. Pulled from the joint spec
# itself (rating_I_A) rather than re-typed, so this module can never drift from
# the calibrated model it wraps.
_BASE_SPEC = S.joint_te_63951_63969()
RATED_I_A = _BASE_SPEC.rating_I_A                      # 22.9 A (TE 108-1706)
MARGIN_POLICY = 1.25                                   # 125% (owner-ratified policy)
ALLOWABLE_I_A = RATED_I_A / MARGIN_POLICY              # 18.32 A/joint

# The two thermal gates physics_gates() already applies (reused here verbatim,
# never re-invented) plus the SAME "brief excursion" transient ceiling it uses
# (t_max + 20), repurposed below as the E2 "fusing-class" marker for a JOINT
# (an extension across element classes -- see the module docstring caveat).
DT_MAX_C = 30.0
T_MAX_C = 105.0
FUSING_CLASS_T_C = T_MAX_C + 20.0                      # 125 degC

AMBIENT_C = S._AMBIENT["enclosed_passive"]             # 50 degC -- the family's
                                                        # own stated full-stack posture
                                                        # (blade-interconnect-thermal.md SS4)


def policy_pass(dT, T, *, dt_max=DT_MAX_C, t_max=T_MAX_C):
    """The SAME OR-gate physics_gates() uses: FAIL if the rise exceeds dt_max
    OR the absolute temperature exceeds t_max."""
    return dT <= dt_max and T <= t_max


# ============================================================ family joint-group data
# Ratified iteration-7 joint counts + per-rail design-basis currents. Source of
# truth: docs/standard-tier-review/blade-fit-check-2026-07-04.md addendum 7 SS
# F.2 (owner-ratified 2026-07-06) and the rating-datum re-derivation percentages
# there (22.9/I_per_joint*100 >= 125%); independently cross-checked against the
# per-tab net assignments in scripts/gen-output-daughterboard.py's
# ATX24_TABS/EPS8_TABS/PCIE8_TABS (group sizes match exactly: atx24 1/2/2/1/4 =
# 10 tabs, eps 3+3 = 6, pcie 3+3 = 6). Figures are PER CABLE for eps/pcie (a
# populated EPS module carries up to 2 cables, PCIe up to 3 -- each cable's
# joint group is independent under the current model, no cross-cable coupling).
FAMILY_JOINT_GROUPS = {
    "atx24": [
        {"rail": "+12V",  "n": 1, "I_total_A": 12.0},
        {"rail": "+5V",   "n": 2, "I_total_A": 30.0},
        {"rail": "+3V3",  "n": 2, "I_total_A": 24.0},
        {"rail": "+5VSB", "n": 1, "I_total_A": 6.0},
        {"rail": "GND",   "n": 4, "I_total_A": 72.0},   # the ratified 127.2% hairline
    ],
    "eps": [
        {"rail": "+12V", "n": 3, "I_total_A": 52.0},
        {"rail": "GND",  "n": 3, "I_total_A": 52.0},
    ],
    "pcie": [
        {"rail": "+12V", "n": 3, "I_total_A": 39.0},
        {"rail": "GND",  "n": 3, "I_total_A": 39.0},
    ],
}
ALL_FAMILIES = tuple(FAMILY_JOINT_GROUPS)


def _rails(family):
    return FAMILY_JOINT_GROUPS[family]


def _iter_rails(families=None):
    for fam in (families or ALL_FAMILIES):
        for grp in _rails(fam):
            yield fam, grp


def rail_margin_pct(I_per_joint):
    """The doc's own percentage convention (blade-fit-check addendum 7):
    rated_current / actual_current_per_joint * 100 -- how far the design-basis
    per-joint current sits below the part's rated ampacity. Policy requires
    >=125%."""
    return (RATED_I_A / I_per_joint) * 100.0 if I_per_joint > 0 else float("inf")


# ============================================================ resistor-network primitive
def current_divider(resistances, I_total):
    """Split I_total across N parallel elements by CONDUCTANCE -- the exact
    resistor-network solve for elements bridging one common low-impedance pair
    of nodes (a bus-bar/pour on each side of a rail's blade-tab row -- the real
    topology a joint GROUP shares). I_i = I_total * G_i / sum(G), G_i = 1/R_i.
    A zero-resistance element is treated as a short and carries everything
    (split evenly among any tied zero-R elements); this is a degenerate guard,
    not a modelled physical case."""
    if not resistances:
        return []
    zero_idx = [i for i, r in enumerate(resistances) if r <= 0]
    if zero_idx:
        share = I_total / len(zero_idx)
        return [share if i in zero_idx else 0.0 for i in range(len(resistances))]
    gs = [1.0 / r for r in resistances]
    tot = sum(gs)
    return [I_total * g / tot for g in gs]


def resistor_network_split(specs, contact_Rs, I_total, T_C):
    """Per-joint current via the conductance divider, using each joint's TOTAL
    resistance (contact + its own JointSpec conductor segments) evaluated at a
    FIXED reference temperature T_C.

    Documented simplification: the split is computed at one reference
    temperature, not re-solved jointly with each element's own rising
    temperature (a fully-coupled T<->split iteration). Brass's low TCR
    (cec_synth_pipeline.ALPHA_BRASS = 0.0015/K) changes R by only ~15% over a
    100 K span, so at the dT scale these scenarios produce (tens of degrees)
    this is a second-order effect layered on top of the FIRST-order effect
    (contact-R variance) these engines exist to expose. Each joint's own dT is
    still solved exactly (self-consistent Picard) via cec_synth_pipeline.joint_solve
    once its current is fixed by this split."""
    Rs = [sp.R_total_ohm(T_C, contact_R_ohm=cr) for sp, cr in zip(specs, contact_Rs)]
    return current_divider(Rs, I_total)


def scaled_joint_spec(base_spec, *, cross_factors=None, contact_R_ohm=None):
    """A modified JointSpec with per-SEGMENT cross-section scale factors
    (cross_factors: {segment_name: factor}, default 1.0 = unchanged) and/or an
    overridden contact resistance. Rth is HELD FIXED at the base spec's own
    calibrated value -- Rth is the joint's convective/envelope thermal
    resistance, which does not change when the internal metal cross-section
    shrinks within manufacturing tolerance or when contact R varies; only R
    (hence P) changes. This is the SAME isolation technique
    tests.test_am04_anchors.T12JointRatingAnchor.test_teeth_sabotaged_cross_raises_dt
    already established for one hand-built sabotage case; this generalizes it
    to named per-segment factors for reuse by every scenario below."""
    cross_factors = cross_factors or {}
    segs = tuple(
        S.JointSegment(seg.name, seg.cross_mm2 * cross_factors.get(seg.name, 1.0),
                       seg.length_mm, seg.rho_ohm_m, seg.alpha_per_C)
        for seg in base_spec.segments
    )
    return S.JointSpec(
        name=base_spec.name + ":scaled",
        contact_R_ohm=base_spec.contact_R_ohm if contact_R_ohm is None else contact_R_ohm,
        segments=segs, rating_I_A=base_spec.rating_I_A, rating_dT_C=base_spec.rating_dT_C,
        rating_ambient_C=base_spec.rating_ambient_C,
        worn_contact_R_ohm=base_spec.worn_contact_R_ohm,
        rth_CW=base_spec.calibrated_rth())


def group_solve(family, rail, *, currents_A=None, contact_Rs=None, spec=None,
                ambient=AMBIENT_C):
    """Solve one rail's joint GROUP: default (no overrides) reproduces the
    plain per-population nominal split (I_total/n at nominal 1 mOhm contact on
    every joint); callers override `currents_A` directly (e.g. an N-1
    redistribution) or `contact_Rs` (a per-joint resistance draw, triggering a
    network re-split). Returns the list of joint_solve records (one per
    joint-in-group) plus the group metadata."""
    grp = next(g for g in _rails(family) if g["rail"] == rail)
    n = grp["n"]
    spec = spec or _BASE_SPEC
    specs = [spec] * n
    if currents_A is not None:
        currents = list(currents_A)
        contact_Rs = contact_Rs or [spec.contact_R_ohm] * len(currents)
    else:
        contact_Rs = contact_Rs or [spec.contact_R_ohm] * n
        currents = resistor_network_split(specs, contact_Rs, grp["I_total_A"], ambient)
    recs = [S.joint_solve(sp, I, ambient, contact_R_ohm=cr)
            for sp, I, cr in zip(specs, currents, contact_Rs)]
    return grp, recs


# ============================================================================
#  E1 -- N-1 parallel-element (joint) loss sweep
# ============================================================================
def n1_sweep(family, *, ambient=AMBIENT_C, dt_max=DT_MAX_C, t_max=T_MAX_C):
    """Drop each joint in a rail's group in turn; the survivors' current is
    RE-SOLVED by the resistor network (identical joints here, so it collapses
    to an even I_total/(n-1) split, but the machinery is the general network
    solve, ready for a future non-identical-joint group). Each survivor's
    temperature is the existing joint_solve -- no new physics, just the
    redistribution + a re-run of the already-anchored solver. A single-joint
    rail has no redundancy at all: 'losing' its one joint is an OPEN CIRCUIT
    (the rail goes dead), not a redistribution case -- flagged distinctly, not
    silently treated as 'passes'."""
    out = {"family": family, "ambient_C": ambient, "rails": []}
    for grp in _rails(family):
        n, I_total = grp["n"], grp["I_total_A"]
        if n == 1:
            out["rails"].append({
                "rail": grp["rail"], "n_joints": 1, "I_total_A": I_total,
                "redundant": False, "open_circuit_on_loss": True,
                "n1_survives_within_policy": False,
                "note": "single joint on this rail: N-1 loss is an open circuit, "
                        "not a redistribution -- no redundancy exists to lose",
            })
            continue
        I_survivor = I_total / (n - 1)
        _, recs = group_solve(family, grp["rail"], currents_A=[I_survivor] * (n - 1),
                              ambient=ambient)
        worst = max(recs, key=lambda r: r["dT"])
        passes = policy_pass(worst["dT"], worst["T"], dt_max=dt_max, t_max=t_max)
        out["rails"].append({
            "rail": grp["rail"], "n_joints": n, "I_total_A": I_total,
            "redundant": True, "open_circuit_on_loss": False,
            "survivors": n - 1, "I_per_survivor_A": round(I_survivor, 2),
            "worst_survivor_dT_C": worst["dT"], "worst_survivor_T_C": worst["T"],
            "n1_survives_within_policy": passes,
        })
    return out


def n1_report(families=ALL_FAMILIES, **kw):
    return [n1_sweep(fam, **kw) for fam in families]


# ============================================================================
#  E3 -- unequal current sharing from a contact-R DISTRIBUTION
#  (the industry's documented 12VHPWR/12V-2x6 melt mechanism)
# ============================================================================
def _lognormal_samples(rng, n, mean, cv):
    """n samples from a lognormal distribution with the given mean and
    coefficient of variation (std/mean). Lognormal (not normal) because
    contact resistance cannot go negative -- a normal draw at a large cv can,
    silently corrupting the network solve; lognormal has the correct support
    and still reduces to the point value at cv=0 (the degenerate/teeth case)."""
    if cv <= 0:
        return [mean] * n
    sigma2 = math.log(1.0 + cv * cv)
    sigma = math.sqrt(sigma2)
    mu = math.log(mean) - 0.5 * sigma2
    return [math.exp(rng.gauss(mu, sigma)) for _ in range(n)]


def unequal_sharing_trial(family, rail, cv, rng, *, ambient=AMBIENT_C, spec=None):
    """ONE resistor-network trial: draw n contact resistances from
    lognormal(mean=spec.contact_R_ohm, cv), solve the TRUE current split (not
    an assumed even share), solve each joint's own temperature, return the
    WORST joint's record -- the gate is at worst-single-joint, never the
    average, per the task."""
    grp = next(g for g in _rails(family) if g["rail"] == rail)
    spec = spec or _BASE_SPEC
    Rs = _lognormal_samples(rng, grp["n"], spec.contact_R_ohm, cv)
    _, recs = group_solve(family, rail, contact_Rs=Rs, spec=spec, ambient=ambient)
    return max(recs, key=lambda r: r["dT"])


def unequal_sharing_worst_at_cv(family, rail, cv, *, seed=DEFAULT_SEED, n_trials=300,
                                percentile=0.95, ambient=AMBIENT_C):
    """Aggregate the worst-joint dT over n_trials independent 'assemblies' (each
    trial draws its own set of n contact resistances), at the given
    spread. `percentile` selects the aggregate across trials (default the 95th
    percentile of assemblies' worst joint -- 'the dT you would see in a
    realistically-unlucky-but-not-vanishingly-rare unit from the population',
    not the single worst-of-all-time outlier, which a small n_trials cannot
    estimate reliably anyway). Fully deterministic for a fixed seed: a fresh
    Random(seed) is created here, so repeated calls at different `cv` values
    replay the IDENTICAL underlying draw sequence (this is what keeps the
    threshold search in find_unequal_sharing_threshold() monotonic)."""
    rng = random.Random(seed)
    dts = sorted(unequal_sharing_trial(family, rail, cv, rng, ambient=ambient)["dT"]
                for _ in range(n_trials))
    idx = min(len(dts) - 1, int(percentile * len(dts)))
    return dts[idx]


def find_unequal_sharing_threshold(family, rail, *, seed=DEFAULT_SEED, n_trials=300,
                                   percentile=0.95, dt_max=DT_MAX_C, cv_max=2.0,
                                   tol=0.005, ambient=AMBIENT_C):
    """Bisect for the contact-R spread (sigma/mu) at which the worst joint in
    this rail's group FIRST crosses the dt_max policy gate. This is the
    bench-measurable acceptance criterion the task calls out explicitly: after
    the OQ-86 sample run, measure the assembled lot's per-joint contact-R
    spread and compare it against this number. Returns None if no crossing is
    found up to cv_max (a healthy-margin rail with no realistic-range
    failure)."""
    lo, hi = 0.0, cv_max
    if unequal_sharing_worst_at_cv(family, rail, hi, seed=seed, n_trials=n_trials,
                                   percentile=percentile, ambient=ambient) < dt_max:
        return None
    if unequal_sharing_worst_at_cv(family, rail, lo, seed=seed, n_trials=n_trials,
                                   percentile=percentile, ambient=ambient) >= dt_max:
        return 0.0
    for _ in range(40):
        mid = 0.5 * (lo + hi)
        v = unequal_sharing_worst_at_cv(family, rail, mid, seed=seed, n_trials=n_trials,
                                        percentile=percentile, ambient=ambient)
        if v >= dt_max:
            hi = mid
        else:
            lo = mid
        if hi - lo < tol:
            break
    return round(0.5 * (lo + hi), 4)


def unequal_sharing_report(families=ALL_FAMILIES, **kw):
    out = []
    for fam, grp in _iter_rails(families):
        I_nom = grp["I_total_A"] / grp["n"]
        thr = find_unequal_sharing_threshold(fam, grp["rail"], **kw)
        out.append({
            "family": fam, "rail": grp["rail"], "n_joints": grp["n"],
            "I_per_joint_nominal_A": round(I_nom, 2),
            "margin_pct_nominal": round(rail_margin_pct(I_nom), 1),
            "cv_threshold_sigma_over_mu": thr,
            "bench_acceptance": (
                "measure the assembled lot's per-joint contact-R spread; a "
                "sigma/mu at or above this value can drive the worst joint "
                "past the 30C-rise policy" if thr is not None else
                "no crossing found up to the search ceiling -- healthy margin "
                "against realistic assembly variance"),
        })
    return out


# ============================================================================
#  E2 -- partial-seat / point-contact scenario (localized-hotspot case)
# ============================================================================
def partial_seat_sweep(family, rail, *, r_values_mohm=(5, 10, 15, 20, 25, 30, 40, 50),
                       ambient=AMBIENT_C, spec=None):
    """ONE joint in the group sits at an ELEVATED contact R (5-50 mOhm, the
    task's specified sweep -- this EXTENDS cec_synth_pipeline's existing
    worn=True single fixed point at 10 mOhm to a parametrized sweep, the same
    mechanism, not a duplicate of it); the other joints stay at nominal 1 mOhm.
    The group's TRUE current split is re-solved (not an assumed even share),
    so this reports BOTH halves of the real physics: the degraded joint's own
    dT, and the healthy survivors' dT (which rises as the degraded joint sheds
    current onto them)."""
    grp = next(g for g in _rails(family) if g["rail"] == rail)
    n, I_total = grp["n"], grp["I_total_A"]
    spec = spec or _BASE_SPEC
    rows = []
    for r_mohm in r_values_mohm:
        Rs = [spec.contact_R_ohm] * (n - 1) + [r_mohm * 1e-3]
        _, recs = group_solve(family, rail, contact_Rs=Rs, spec=spec, ambient=ambient)
        degraded = recs[-1]
        survivors = recs[:-1]
        row = {"contact_R_mohm": r_mohm, "degraded_I_A": degraded["I"],
              "degraded_dT_C": degraded["dT"], "degraded_T_C": degraded["T"],
              "degraded_policy_pass": policy_pass(degraded["dT"], degraded["T"]),
              "degraded_fusing_class": degraded["T"] > FUSING_CLASS_T_C}
        if survivors:
            worst_surv = max(survivors, key=lambda r: r["dT"])
            row.update({"worst_survivor_dT_C": worst_surv["dT"],
                       "worst_survivor_T_C": worst_surv["T"],
                       "survivors_policy_pass": policy_pass(worst_surv["dT"], worst_surv["T"])})
        rows.append(row)
    return {"family": family, "rail": rail, "n_joints": n, "redundant": n > 1,
           "sweep": rows}


def _bisect_R_for_dT(family, rail, target_dt, *, ambient=AMBIENT_C, spec=None,
                     lo_ohm=1e-4, hi_ohm=1.0, tol=1e-6):
    """Find the DEGRADED joint's own contact R (ohms) at which its own dT first
    reaches target_dt, holding the rest of the group nominal. Used for both the
    policy (30C) and fusing-class (125C absolute -> dT = FUSING_CLASS_T_C -
    ambient) thresholds. Returns None if never reached within [lo_ohm, hi_ohm]
    (the self-limiting redundant-group case)."""
    grp = next(g for g in _rails(family) if g["rail"] == rail)
    n = grp["n"]
    spec = spec or _BASE_SPEC

    def dt_at(r_ohm):
        Rs = [spec.contact_R_ohm] * (n - 1) + [r_ohm]
        _, recs = group_solve(family, rail, contact_Rs=Rs, spec=spec, ambient=ambient)
        return recs[-1]["dT"]

    if dt_at(hi_ohm) < target_dt:
        return None
    if dt_at(lo_ohm) >= target_dt:
        return lo_ohm
    for _ in range(60):
        mid = 0.5 * (lo_ohm + hi_ohm)
        if dt_at(mid) >= target_dt:
            hi_ohm = mid
        else:
            lo_ohm = mid
        if hi_ohm - lo_ohm < tol:
            break
    return 0.5 * (lo_ohm + hi_ohm)


def partial_seat_threshold(family, rail, *, ambient=AMBIENT_C):
    """The two R thresholds (policy-fail, fusing-class) for the DEGRADED
    joint's own temperature, plus the redundancy verdict: for a rail with n>1
    joints the degraded joint is thermally SELF-LIMITING (a current divider
    sheds current away from a high-R element -- P = I^2*R falls as R -> inf
    because I falls faster), so the genuine localized-hotspot risk from a
    partial seat exists ONLY on a rail with NO redundancy (n==1), where the
    full nominal current has nowhere else to go."""
    grp = next(g for g in _rails(family) if g["rail"] == rail)
    fusing_dt = FUSING_CLASS_T_C - ambient
    r_policy = _bisect_R_for_dT(family, rail, DT_MAX_C, ambient=ambient)
    r_fusing = _bisect_R_for_dT(family, rail, fusing_dt, ambient=ambient)
    return {
        "family": family, "rail": rail, "n_joints": grp["n"], "redundant": grp["n"] > 1,
        "policy_fail_R_mohm": round(r_policy * 1e3, 3) if r_policy else None,
        "fusing_class_R_mohm": round(r_fusing * 1e3, 3) if r_fusing else None,
        "self_limiting": grp["n"] > 1,
        "note": (
            "no redundancy: the FULL nominal current must cross this one joint "
            "regardless of its resistance -- a partial seat here is a genuine "
            "localized-hotspot risk" if grp["n"] == 1 else
            "redundant group: as this joint's R rises the current-divider sheds "
            "current onto its healthy neighbours, so the degraded joint's OWN "
            "temperature is self-limiting (falls, not rises, at high R) -- the "
            "real consequence is neighbour overload, converging to the E1 N-1 "
            "case as R -> large"),
    }


def partial_seat_report(families=ALL_FAMILIES, **kw):
    out = []
    for fam, grp in _iter_rails(families):
        sweep = partial_seat_sweep(fam, grp["rail"], **kw)
        thr = partial_seat_threshold(fam, grp["rail"])
        out.append({"sweep": sweep, "thresholds": thr})
    return out


# ============================================================================
#  E4 -- adiabatic I2t fault-withstand (Onderdonk / IEEE-Std-80-class relation)
# ============================================================================
# Rigorous adiabatic conductor-heating derivation -- the physical relation
# BEHIND both Onderdonk's empirical wire-fusing fit and the IEEE Std 80
# substation-grounding-conductor sizing equation (the same "adiabatic energy
# balance, no conduction/convection/radiation" class of equation, applied here
# to a joint conductor instead of a PCB trace or a grounding grid conductor):
#
#   J^2 * rho(T) = density * cp * dT/dt         (Joule heating == heat capacity)
#
# integrated from Ta to Tm with rho(T) = rho20*(1+alpha*(T-20)) linear in T:
#
#   I^2*t = A^2 * [density*cp / (rho20*alpha)] * ln(1 + alpha*(Tm-Ta))
#
# CROSS-VALIDATED (see tests.test_thermal_scenarios.TE4Onderdonk) against this
# repo's OWN anchored/tested Onderdonk curve for copper
# (corpus/staging/general/thermal-gates.json id thermal.fusing.onderdonk_jt =
# "1550*sqrt(0.0346/t_s)", anchored by tests/test_thermal_gates_corpus.py --
# NOT edited here, only read as a cross-check target): using standard
# published copper properties (density 8960 kg/m^3, cp 385 J/(kg*K)) this
# derivation reproduces that curve to within ~0.5% at every documented curve
# point -- confirms the SAME functional form, the small constant offset being
# ordinary cross-source material-property rounding, not a derivation error.
#
# Reuses cec_synth_pipeline's OWN resistivity/TCR constants (RHO_CU_20C/
# ALPHA_CU, RHO_BRASS/ALPHA_BRASS) so the material model is identical to the
# one the joint solver already uses; only density/specific-heat/melting-point
# (not otherwise present in cec_synth_pipeline) are added, from standard
# published material data.
_MATERIALS = {
    "copper": {"rho20": S.RHO_CU_20C, "alpha": S.ALPHA_CU,
              "density_kg_m3": 8960.0, "cp_J_kgK": 385.0, "Tm_C": 1083.0},
    # UNVERIFIED for the specific brass alloy actually used (CuZn30/CuZn37,
    # per cec_synth_pipeline's own RHO_BRASS comment): 930 degC is a
    # representative midpoint of CuZn30 (~954-967C) / CuZn37 (~900-920C)
    # published melting ranges; density/cp are standard brass handbook values.
    # Onderdonk's ORIGINAL empirical fit is validated for copper WIRE; applying
    # its rigorous adiabatic FORM (not a re-fit constant) to a brass stamping
    # is an engineering extrapolation, flagged here, not a measured result.
    "brass": {"rho20": S.RHO_BRASS, "alpha": S.ALPHA_BRASS,
             "density_kg_m3": 8530.0, "cp_J_kgK": 380.0, "Tm_C": 930.0},
}


def adiabatic_fuse_current_density(t_s, *, material="copper", ambient_C=20.0):
    """Onderdonk/IEEE-Std-80-class adiabatic fusing current density [A/mm^2] at
    duration t_s (seconds), from a starting temperature ambient_C. Valid for
    short pulses only (<~1 s good, conservative to ~10 s, void beyond --
    IDENTICAL validity caveat to the corpus's own onderdonk_jt entry, since
    this is the same physics)."""
    m = _MATERIALS[material]
    tcap = m["density_kg_m3"] * m["cp_J_kgK"]
    num = tcap * math.log(1.0 + m["alpha"] * (m["Tm_C"] - ambient_C))
    den = m["rho20"] * m["alpha"]
    i_over_a_m2 = math.sqrt(num / den / t_s)
    return i_over_a_m2 / 1e6                   # A/m^2 -> A/mm^2


# Illustrative fault profiles (magnitude as a multiplier of the family/rail's
# OWN nominal per-joint current; duration in seconds). UNVERIFIED: no real PSU
# or GPU fault let-through / OCP-clearing-time data exists for this platform --
# these are engineering-judgment stand-ins spanning "mild overload, PSU-OCP-
# speed clearing" to "near dead-short, arc-speed clearing", explicitly marked
# as assumptions, per the task. The FRAMEWORK (the withstand check itself) is
# real; the input profile is not measured.
FAULT_PROFILES = (
    {"multiplier": 2.0, "duration_s": 0.5,
     "label": "UNVERIFIED: mild overload, slow PSU OCP (~500ms)"},
    {"multiplier": 5.0, "duration_s": 0.1,
     "label": "UNVERIFIED: moderate fault, fast OCP (~100ms)"},
    {"multiplier": 10.0, "duration_s": 0.01,
     "label": "UNVERIFIED: severe fault / near dead-short (~10ms)"},
    {"multiplier": 20.0, "duration_s": 0.001,
     "label": "UNVERIFIED: extreme transient arc/short (~1ms)"},
)


def i2t_fault_withstand(family, rail, *, multiplier, duration_s, ambient=AMBIENT_C,
                        material="brass", spec=None):
    """Per-conductor adiabatic I2t withstand for the joint's WEAKEST segment
    (smallest cross-section along the series current path -- the segment that
    reaches fusing density first), against a parameterized fault
    (multiplier x this rail's own nominal per-joint current, for duration_s)."""
    grp = next(g for g in _rails(family) if g["rail"] == rail)
    spec = spec or _BASE_SPEC
    I_nominal_per_joint = grp["I_total_A"] / grp["n"]
    I_fault = I_nominal_per_joint * multiplier
    weakest = min(spec.segments, key=lambda s: s.cross_mm2)
    j_actual = I_fault / weakest.cross_mm2
    j_fuse = adiabatic_fuse_current_density(duration_s, material=material, ambient_C=ambient)
    margin = (j_fuse / j_actual) if j_actual > 0 else float("inf")
    return {
        "family": family, "rail": rail, "element": weakest.name,
        "cross_mm2": round(weakest.cross_mm2, 4), "material": material,
        "I_nominal_per_joint_A": round(I_nominal_per_joint, 2),
        "fault_multiplier": multiplier, "fault_duration_s": duration_s,
        "fault_current_A": round(I_fault, 1),
        "J_actual_A_mm2": round(j_actual, 1), "J_fuse_A_mm2": round(j_fuse, 1),
        "withstand_margin": round(margin, 2), "withstands": margin >= 1.0,
    }


def i2t_report(families=ALL_FAMILIES, profiles=FAULT_PROFILES, **kw):
    out = []
    for fam, grp in _iter_rails(families):
        for p in profiles:
            rec = i2t_fault_withstand(fam, grp["rail"], multiplier=p["multiplier"],
                                      duration_s=p["duration_s"], **kw)
            rec["profile"] = p["label"]
            out.append(rec)
    return out


# ============================================================================
#  C1/C2 -- deterministic tolerance-CORNER runs (thin copper / thin plating)
# ============================================================================
# "Thin copper" maps onto the joint's two STAMPED-METAL conductor segments
# (blade_63951, receptacle_63969) -- the closest joint-model analog to C1's
# PCB-copper-foil manufacturing tolerance, generalized from foil to stamping.
# "Thin plating" maps onto tails_solder -- the joint's OWN through-board
# soldered pins, the closest joint-model analog to C2's via-barrel-plating
# tolerance (a real plated-through-board feature, not a proxy for an unrelated
# board via). A cited IPC-class copper-thickness tolerance convention
# (commonly +/-10-20% of nominal) sets the default corner at -20%.
TOLERANCE_CORNER_PCT_DEFAULT = 20.0


def tolerance_corner(family, rail, *, copper_thin_pct=TOLERANCE_CORNER_PCT_DEFAULT,
                     plating_thin_pct=TOLERANCE_CORNER_PCT_DEFAULT, ambient=AMBIENT_C):
    """Deterministic WORST-CORNER run (not a distribution): every joint in the
    group is simultaneously thinned by the same corner factors (a lot-wide
    manufacturing-tolerance corner, not a per-joint independent draw -- that is
    what the Monte Carlo wrapper below does instead). Reports the nominal vs
    corner dT/T and the margin erosion."""
    grp = next(g for g in _rails(family) if g["rail"] == rail)
    n, I_total = grp["n"], grp["I_total_A"]
    cu_factor = 1.0 - copper_thin_pct / 100.0
    plate_factor = 1.0 - plating_thin_pct / 100.0
    corner_spec = scaled_joint_spec(
        _BASE_SPEC,
        cross_factors={"blade_63951": cu_factor, "receptacle_63969": cu_factor,
                       "tails_solder": plate_factor})
    _, nominal_recs = group_solve(family, rail, ambient=ambient)
    _, corner_recs = group_solve(family, rail, spec=corner_spec, ambient=ambient)
    nom_worst = max(nominal_recs, key=lambda r: r["dT"])
    cor_worst = max(corner_recs, key=lambda r: r["dT"])
    return {
        "family": family, "rail": rail, "n_joints": n, "I_total_A": I_total,
        "copper_thin_pct": copper_thin_pct, "plating_thin_pct": plating_thin_pct,
        "nominal_dT_C": nom_worst["dT"], "nominal_T_C": nom_worst["T"],
        "corner_dT_C": cor_worst["dT"], "corner_T_C": cor_worst["T"],
        "dT_erosion_C": round(cor_worst["dT"] - nom_worst["dT"], 2),
        "nominal_policy_pass": policy_pass(nom_worst["dT"], nom_worst["T"]),
        "corner_policy_pass": policy_pass(cor_worst["dT"], cor_worst["T"]),
    }


def tolerance_corner_report(families=ALL_FAMILIES, **kw):
    return [tolerance_corner(fam, grp["rail"], **kw) for fam, grp in _iter_rails(families)]


# ============================================================================
#  F1/F2 -- seeded Monte Carlo margin confidence + one-at-a-time sensitivity
# ============================================================================
# Inputs (the task's named four axes), all through the ANALYTIC solve path
# (resistor-network split + joint_solve's own Picard dT -- NEVER the 2.5D field
# solve, per the task's explicit instruction):
#   - contact_R          : per-joint lognormal draw (same mechanism as E3)
#   - copper_thickness    : a lot-wide factor on the blade+receptacle segments
#   - via_plating         : a lot-wide factor on the tails_solder segment (the
#                           joint's own through-board/via-analog feature)
#   - ambient             : a per-trial draw around the enclosed_passive posture
MC_DEFAULT_SIGMAS = {
    "contact_cv": 0.15,          # per-joint contact-R coefficient of variation
    "copper_thickness_sigma": 0.0667,   # ~1-sigma = 1/3 of a 20% IPC-class corner
    "via_plating_sigma": 0.0667,
    "ambient_sigma_C": 3.0,      # spread around the 50C enclosed_passive posture
}


def _normal_factor(rng, mean, sigma, *, lo=0.05):
    if sigma <= 0:
        return mean
    return max(lo, rng.gauss(mean, sigma))


def _mc_trial(family, rail, rng, sigmas, *, ambient_mean=AMBIENT_C):
    grp = next(g for g in _rails(family) if g["rail"] == rail)
    n = grp["n"]
    ambient = rng.gauss(ambient_mean, sigmas["ambient_sigma_C"]) \
        if sigmas["ambient_sigma_C"] > 0 else ambient_mean
    cu = _normal_factor(rng, 1.0, sigmas["copper_thickness_sigma"])
    plate = _normal_factor(rng, 1.0, sigmas["via_plating_sigma"])
    trial_spec = scaled_joint_spec(
        _BASE_SPEC, cross_factors={"blade_63951": cu, "receptacle_63969": cu,
                                   "tails_solder": plate})
    Rs = _lognormal_samples(rng, n, _BASE_SPEC.contact_R_ohm, sigmas["contact_cv"])
    _, recs = group_solve(family, rail, contact_Rs=Rs, spec=trial_spec, ambient=ambient)
    worst = max(recs, key=lambda r: r["dT"])
    return worst["dT"], {"ambient_C": ambient, "copper_thickness_factor": cu,
                         "via_plating_factor": plate, "contact_Rs_ohm": Rs}


def monte_carlo_margin(family, rail, *, n_trials=1000, seed=DEFAULT_SEED,
                       sigmas=None, dt_max=DT_MAX_C, ambient_mean=AMBIENT_C):
    """Seeded Monte Carlo over {contact R, copper thickness, via/plating,
    ambient} through the analytic joint solve. Returns the margin distribution
    (dt_max - worst_joint_dT; positive = pass) and the fraction of trials
    inside the 30C-rise policy gate (`confidence_pass`).

    TEETH (asserted in tests.test_thermal_scenarios): (1) all sigmas at 0
    reproduces the deterministic nominal joint_solve result EXACTLY, every
    trial identical, confidence_pass in {0.0, 1.0}; (2) a deliberately widened
    `sigmas` drops confidence_pass on a rail that passes comfortably at the
    default spread."""
    sigmas = dict(MC_DEFAULT_SIGMAS, **(sigmas or {}))
    rng = random.Random(seed)
    dts = [_mc_trial(family, rail, rng, sigmas, ambient_mean=ambient_mean)[0]
          for _ in range(n_trials)]
    margins = [dt_max - dt for dt in dts]
    passes = sum(1 for dt in dts if dt <= dt_max)
    dts_sorted = sorted(dts)

    def pct(p):
        return dts_sorted[min(len(dts_sorted) - 1, int(p * len(dts_sorted)))]

    return {
        "family": family, "rail": rail, "n_trials": n_trials, "seed": seed,
        "sigmas": sigmas,
        "dT_mean_C": round(sum(dts) / len(dts), 2),
        "dT_p05_C": round(pct(0.05), 2), "dT_p50_C": round(pct(0.50), 2),
        "dT_p95_C": round(pct(0.95), 2), "dT_worst_C": round(max(dts), 2),
        "margin_mean_C": round(sum(margins) / len(margins), 2),
        "confidence_pass": round(passes / len(dts), 4),
    }


def mc_passes_confidence_gate(mc_result, *, min_confidence=0.90):
    return mc_result["confidence_pass"] >= min_confidence


def sensitivity_ranking(family, rail, *, seed=DEFAULT_SEED, sigmas=None, n_trials=1,
                        ambient_mean=AMBIENT_C):
    """One-at-a-time sensitivity: perturb ONE input axis by its configured
    sigma (holding the rest at their nominal/zero-spread value) and measure the
    resulting change in worst-joint dT vs the all-nominal baseline; rank axes
    by |delta|. Deterministic: uses a fresh Random(seed) per axis so every axis
    is evaluated on an equivalent draw (n_trials averages out per-draw noise;
    n_trials=1 with a fixed seed is still fully reproducible, just noisier --
    callers wanting a smoother ranking raise n_trials)."""
    sigmas = dict(MC_DEFAULT_SIGMAS, **(sigmas or {}))
    zero = {k: 0.0 for k in sigmas}
    baseline = _mean_dt(family, rail, zero, seed, n_trials, ambient_mean)
    deltas = {}
    for axis in sigmas:
        one_hot = dict(zero)
        one_hot[axis] = sigmas[axis]
        val = _mean_dt(family, rail, one_hot, seed, n_trials, ambient_mean)
        deltas[axis] = round(abs(val - baseline), 4)
    ranked = sorted(deltas.items(), key=lambda kv: -kv[1])
    return {"family": family, "rail": rail, "baseline_dT_C": round(baseline, 3),
           "deltas_C": deltas, "ranking": [k for k, _ in ranked]}


def _mean_dt(family, rail, sigmas, seed, n_trials, ambient_mean):
    rng = random.Random(seed)
    vals = [_mc_trial(family, rail, rng, sigmas, ambient_mean=ambient_mean)[0]
           for _ in range(n_trials)]
    return sum(vals) / len(vals)


def monte_carlo_report(families=ALL_FAMILIES, *, seed=DEFAULT_SEED, n_trials=1000, **kw):
    out = []
    for fam, grp in _iter_rails(families):
        mc = monte_carlo_margin(fam, grp["rail"], seed=seed, n_trials=n_trials, **kw)
        sens = sensitivity_ranking(fam, grp["rail"], seed=seed, n_trials=max(50, n_trials // 10))
        out.append({"monte_carlo": mc, "sensitivity": sens,
                   "confidence_gate_0_90": mc_passes_confidence_gate(mc, min_confidence=0.90)})
    return out


# ============================================================================
#  Top-level report assembly + CLI
# ============================================================================
def run_all_scenarios(families=ALL_FAMILIES, *, seed=DEFAULT_SEED):
    """Assemble the full per-engine, per-family report this module produces."""
    return {
        "families": list(families),
        "joint_spec": {"name": _BASE_SPEC.name, "rated_I_A": RATED_I_A,
                      "margin_policy": MARGIN_POLICY, "allowable_I_A": round(ALLOWABLE_I_A, 2),
                      "ambient_C": AMBIENT_C},
        "n1_sweep": n1_report(families),
        "unequal_sharing": unequal_sharing_report(families, seed=seed),
        "partial_seat": partial_seat_report(families),
        "i2t_withstand": i2t_report(families),
        "tolerance_corner": tolerance_corner_report(families),
        "monte_carlo": monte_carlo_report(families, seed=seed),
    }


def _print_table(rows, cols, title):
    print("\n== %s ==" % title)
    if not rows:
        print("  (no rows)")
        return
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    print("  " + " | ".join(c.ljust(widths[c]) for c in cols))
    for r in rows:
        print("  " + " | ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


def _print_report(report):
    print("CEC thermal scenario/statistics report (cec_thermal_scenarios.py)")
    print("families: %s | rated joint: %.1fA @ %.0f%% policy -> %.2fA/joint allowable" % (
        ", ".join(report["families"]), RATED_I_A, MARGIN_POLICY * 100, ALLOWABLE_I_A))

    n1_rows = []
    for rep in report["n1_sweep"]:
        for r in rep["rails"]:
            n1_rows.append({
                "family": rep["family"], "rail": r["rail"], "n": r["n_joints"],
                "survives_N-1": r["n1_survives_within_policy"],
                "worst_dT_C": r.get("worst_survivor_dT_C", "open-circuit"),
            })
    _print_table(n1_rows, ["family", "rail", "n", "survives_N-1", "worst_dT_C"],
                "E1: N-1 parallel-joint loss")

    _print_table(report["unequal_sharing"],
                ["family", "rail", "n_joints", "I_per_joint_nominal_A",
                 "margin_pct_nominal", "cv_threshold_sigma_over_mu"],
                "E3: unequal current sharing (contact-R spread threshold)")

    pt_rows = [rep["thresholds"] for rep in report["partial_seat"]]
    _print_table(pt_rows, ["family", "rail", "n_joints", "redundant",
                          "policy_fail_R_mohm", "fusing_class_R_mohm"],
                "E2: partial-seat / point-contact thresholds")

    _print_table(report["i2t_withstand"],
                ["family", "rail", "fault_multiplier", "fault_duration_s",
                 "J_actual_A_mm2", "J_fuse_A_mm2", "withstand_margin", "withstands"],
                "E4: I2t adiabatic fault withstand (Onderdonk/IEEE-80-class)")

    _print_table(report["tolerance_corner"],
                ["family", "rail", "nominal_dT_C", "corner_dT_C", "dT_erosion_C",
                 "corner_policy_pass"],
                "C1/C2: tolerance-corner erosion (-20% copper/plating)")

    mc_rows = []
    for rep in report["monte_carlo"]:
        mc = rep["monte_carlo"]
        mc_rows.append({"family": mc["family"], "rail": mc["rail"],
                       "dT_p50_C": mc["dT_p50_C"], "dT_p95_C": mc["dT_p95_C"],
                       "confidence_pass": mc["confidence_pass"],
                       "top_sensitivity": rep["sensitivity"]["ranking"][0]})
    _print_table(mc_rows, ["family", "rail", "dT_p50_C", "dT_p95_C",
                          "confidence_pass", "top_sensitivity"],
                "F1/F2: Monte Carlo margin confidence + top sensitivity axis")


def main(argv=None):
    import argparse
    import json as _json
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--families", default=",".join(ALL_FAMILIES))
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--json", action="store_true", help="dump the raw report as JSON")
    args = ap.parse_args(argv)
    families = tuple(f.strip() for f in args.families.split(",") if f.strip())
    report = run_all_scenarios(families, seed=args.seed)
    if args.json:
        print(_json.dumps(report, indent=2, default=str))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
