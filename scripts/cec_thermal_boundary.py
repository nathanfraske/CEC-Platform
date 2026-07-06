#!/usr/bin/env python3
"""cec_thermal_boundary.py -- T1a boundary-condition physics library (2026-07-06).

WHY THIS EXISTS
---------------
Wave-1 assignment T1a of `docs/standard-tier-review/thermal-capabilities-
implementation-2026-07-06.md`, closing five convergent gaps named in
`docs/standard-tier-review/thermal-solve-completeness-2026-07-06.md`:
  X1 radiation (currently entirely absent from both solvers),
  X2 convection realism -- the CHEAP half (orientation-correct correlations +
     a forced-airflow parametric sweep; full case CFD is Tier-3, out of scope),
  X3 cable/harness as a thermal conductor loading a connector joint from
     outside the board,
  H3 finite chassis node (today's case-cooling model treats the chassis as an
     IDEAL, infinite-capacity, fixed-temperature sink),
  X8 solder-joint interface resistance + IPC void-fraction derate.

THIS MODULE ONLY. Per the wave-1 discipline (CLAUDE.md, AM-04 pattern): own-
module isolation. `scripts/cec_synth_pipeline.py` and `scripts/cec_thermal2d.py`
are READ-ONLY inputs here (their electrothermal_solve/dt_ipc/solve_board_thermal
APIs and boundary-condition treatment were read to match units/conventions and
to find the exact integration seam) -- NEITHER FILE IS EDITED by this pass, and
neither is any existing test. This module is purely ADDITIVE: importing it and
calling nothing changes no existing behavior anywhere.

INTEGRATION SEAMS (documented, NOT wired in this pass -- a future coordinator
pass does the wiring once all three wave-1 modules land and the full suite is
green):
  - cec_thermal2d.solve_board_thermal(..., c_nat=, eps_rad=, t_chassis=, ...):
    `h_natural_convection()`/`h_forced_convection()` here can replace the
    single flat `c_nat`; `radiative_flux_small_in_large()`/`h_rad_linear()`
    can replace the single flat `eps_rad`; `effective_chassis_sink_temperature_C()`
    can replace the flat `t_chassis=ambient` used today by cec_thermal_overlay.py's
    case-cooling posture (`cool_kw["t_chassis"] = ambient` -- the literal H3 gap).
  - cec_synth_pipeline.joint_solve()/JointSpec: `solder_fillet_segment()` returns
    a `cec_synth_pipeline.JointSegment`-compatible object (duck-typed: same
    `.R_ohm(T)` method) so it drops into a `JointSpec.segments` tuple in series
    with the existing blade/receptacle/tail segments with zero new plumbing.
    `cable_fin_conducted_heat()`'s `q_into_joint_W` is an extra heat term a
    future `joint_solve` could add to the joint's P(T) before the Rth multiply.
  - T0 (`cec_thermal_sources.py`, a PARALLEL wave-1 module -- absent from this
    checkout as of authoring): `region_emissivity_from_thermal_sources()` below
    codes against a *documented, best-guess FORMAT* (several plausible call
    signatures, tried defensively) rather than an implementation it cannot see.
    UNVERIFIED: T0's actual contract was not available to consult; this
    consumer NEVER raises on a missing/mismatched T0 and always degrades to
    the documented whole-board matte-solder-mask average.

API SUMMARY (composable: geometry/temperature/posture in, conductance or
heat-flow out; nothing here touches a `.kicad_pcb` or mutates global state)
------------------------------------------------------------------------
Shared:
  air_properties(T_C) -> dict(k_W_mK, nu_m2_s, alpha_m2_s, Pr, beta_1_K)
  rayleigh(L_c_m, dT_C, T_film_C) -> Ra
  reynolds(v_m_s, L_m, T_film_C) -> Re

1. RADIATION (X1)
  RegionEmissivity(name, emissivity, area_frac)
  region_emissivity_from_thermal_sources(board_path, fallback=None) -> [RegionEmissivity]
  effective_emissivity(regions) -> float
  radiative_flux_small_in_large(Ts_C, Tsurr_C, emissivity, area_m2=1.0) -> W   (exact)
  h_rad_linear(Ts_C, Tsurr_C, emissivity) -> W/m2K                            (linearized)
  two_surface_enclosure_flux(T1_C, T2_C, eps1, eps2, A1_m2, A2_m2, F12=1.0) -> W
  radiative_loss_open_board_in_case(...) / radiative_loss_enclosed_product(...)
  radiation_fraction_still_air(Ts_C, Tamb_C, emissivity, L_c_m, orientation) -> dict

2. CONVECTION (X2, cheap half)
  nusselt_vertical_plate_churchill_chu(Ra, Pr, laminar_only=False) -> Nu
  nusselt_horizontal_plate_mcadams(Ra, Pr, facing="up"|"down") -> Nu
  nusselt_horizontal_cylinder_churchill_chu(Ra, Pr) -> Nu
  nusselt_flat_plate_forced(Re, Pr) -> Nu
  nusselt_channel_elenbaas(Ra_b, b_over_L) -> Nu_b                (UNVERIFIED constants)
  h_natural_convection(L_c_m, dT_C, T_film_C, orientation) -> dict
  h_forced_convection(v_m_s, L_m, T_film_C) -> dict
  h_forced_sweep(velocities_m_s, L_m, T_film_C) -> [dict, ...]    (the X2 parametric sweep)
  h_channel_natural_convection(b_m, L_m, dT_C, T_film_C) -> dict
  elenbaas_optimum_spacing_m(L_m, dT_C, T_film_C) -> m
  standing_daughterboard_convection_estimate(...) -> dict          (carries the wake CAVEAT)

3. CABLE FIN (X3)
  AWG_TABLE / awg_conductor_area_mm2(awg) -> mm2
  CableSpec(awg_or_area_mm2, length_m, insulation_od_mm, insulation_k_W_mK, k_conductor_W_mK)
  eps_pcie_extension_16awg(length_m) / pigtail_12vhpwr_16awg(length_m) / argb_fat_sata_feed(length_m)
  cable_fin_conducted_heat(cable, T_joint_C, T_far_C, T_ambient_C, h_outer=None) -> dict

4. FINITE CHASSIS NODE (H3)
  ChassisNode(area_m2, orientation, emissivity, material)
  chassis_room_resistance_K_per_W(chassis, T_chassis_C, T_room_C) -> K/W
  effective_chassis_sink_temperature_C(chassis, T_room_C, Q_system_other_W=0, preload_delta_C=0, board_Q_W=0) -> C

5. SOLDER INTERFACE (X8)
  SOLDER_K_W_MK / SOLDER_RESISTIVITY_OHM_M / IPC_VOID_FRACTION_DEFAULT
  SolderFilletGeometry(name, area_mm2, thickness_mm)
  shunt_2512_pad_fillet() / connector_tht_tail_fillet()           (illustrative presets)
  solder_interface_thermal_resistance_K_per_W(geom, alloy, void_fraction) -> K/W
  solder_fillet_segment(geom, alloy, void_fraction, name) -> JointSegment-compatible

CITATION / VERIFICATION DISCIPLINE
-----------------------------------
Every constant below carries an inline citation. `UNVERIFIED` (grep-able) marks
anything this pass could not independently confirm against a primary source
this session (either the source rendered as an image/paywall, or it is a
commonly-republished secondary-literature number with no primary fetch this
session) -- these still ship (a documented, honestly-labeled approximation
beats silently defaulting), but a reviewer should treat them as lower-
confidence than the formulas marked CONFIRMED (verified against a live source
during this authoring session; see the accompanying report for the exact
searches). None of this module's outputs feed any existing gate; it is a pure
library pending the coordinator integration pass.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# =====================================================================================
# 0. SHARED CONSTANTS AND AIR-PROPERTY / DIMENSIONLESS-GROUP HELPERS
# =====================================================================================

# Stefan-Boltzmann constant. CODATA 2018 value is 5.670374e-8 W/m^2K^4; this module
# uses the SAME 3-sig-fig literal (5.67e-8) already hard-coded as SIGMA_SB in
# cec_thermal2d.py so radiation numbers computed by the two modules agree to full
# floating-point precision rather than differing in the 4th significant figure.
SIGMA_SB = 5.67e-8                       # W/m^2 K^4  (CONFIRMED, matches cec_thermal2d.SIGMA_SB)
G_STD = 9.80665                          # m/s^2, exact SI standard-gravity definition (CONFIRMED)
K_CU = 385.0                             # W/m*K copper thermal conductivity (matches cec_thermal2d.K_CU;
                                          # Incropera & DeWitt Table A.1, pure copper ~385-401 W/m*K
                                          # depending on temperature/purity -- CONFIRMED order, table
                                          # entry precision UNVERIFIED this session)
ALPHA_CU = 0.00393                       # 1/C copper TCR (matches cec_synth_pipeline.ALPHA_CU / cec_thermal2d.ALPHA_CU)

# ---- air properties table (1 atm), keyed by absolute temperature in Kelvin --------
# Source class: Incropera & DeWitt, "Fundamentals of Heat and Mass Transfer," Table
# A.4 (air at atmospheric pressure) -- the standard air-property table used by every
# correlation in section 2. UNVERIFIED-PRECISION: this session's WebFetch attempts at
# a primary copy of the table returned 403/429 (paywalled/rate-limited hosts); the
# entries below are transcribed from well-established general engineering knowledge
# of this specific, extremely widely-reproduced table, NOT independently re-verified
# against a fetched primary copy this session. All properties vary <15% across the
# whole table, so lookup-precision is not gating for the order-of-magnitude Ra/Re
# classification this module needs; a reviewer should still cross-check exact last-
# digit values against a primary table before any bench sign-off use.
_AIR_TABLE_K = {
    #   K :  (k [W/mK], nu [m^2/s],   Pr)
    250:    (0.0223, 9.49e-6,  0.720),
    300:    (0.0263, 15.89e-6, 0.707),
    350:    (0.0300, 20.92e-6, 0.700),
    400:    (0.0338, 25.90e-6, 0.690),
    450:    (0.0373, 31.71e-6, 0.686),
    500:    (0.0407, 37.90e-6, 0.684),
}
_AIR_KEYS = sorted(_AIR_TABLE_K)


def air_properties(T_C):
    """Air properties at 1 atm, linearly interpolated (extrapolated flat past the
    table ends) from `_AIR_TABLE_K` at the given temperature in Celsius. Returns
    dict(k_W_mK, nu_m2_s, alpha_m2_s, Pr, beta_1_K). beta = 1/T[K] is the ideal-gas
    volumetric thermal-expansion-coefficient approximation used throughout natural-
    convection correlations (standard Boussinesq approximation for a gas -- CONFIRMED,
    universal textbook practice, not a table lookup)."""
    T_K = T_C + 273.15
    lo = _AIR_KEYS[0]
    hi = _AIR_KEYS[-1]
    Tq = min(max(T_K, lo), hi)
    for i in range(len(_AIR_KEYS) - 1):
        a, b = _AIR_KEYS[i], _AIR_KEYS[i + 1]
        if a <= Tq <= b:
            f = 0.0 if b == a else (Tq - a) / (b - a)
            ka, nua, Pra = _AIR_TABLE_K[a]
            kb, nub, Prb = _AIR_TABLE_K[b]
            k = ka + f * (kb - ka)
            nu = nua + f * (nub - nua)
            Pr = Pra + f * (Prb - Pra)
            break
    else:                                                        # pragma: no cover
        k, nu, Pr = _AIR_TABLE_K[lo]
    alpha = nu / Pr
    return {"k_W_mK": k, "nu_m2_s": nu, "alpha_m2_s": alpha, "Pr": Pr,
            "beta_1_K": 1.0 / T_K}


def rayleigh(L_c_m, dT_C, T_film_C):
    """Rayleigh number Ra_L = g*beta*|dT|*L_c^3 / (nu*alpha) -- the standard buoyancy-
    vs-diffusion dimensionless group every natural-convection correlation below is a
    function of (CONFIRMED, textbook definition, e.g. Incropera Eq. 9.25)."""
    if L_c_m <= 0:
        return 0.0
    p = air_properties(T_film_C)
    return (G_STD * p["beta_1_K"] * abs(dT_C) * L_c_m ** 3) / (p["nu_m2_s"] * p["alpha_m2_s"])


def reynolds(v_m_s, L_m, T_film_C):
    """Reynolds number Re_L = v*L/nu (CONFIRMED, textbook definition)."""
    if L_m <= 0:
        return 0.0
    p = air_properties(T_film_C)
    return abs(v_m_s) * L_m / p["nu_m2_s"]


# =====================================================================================
# 1. RADIATION (X1) -- gray-body surface-to-enclosure exchange
# =====================================================================================
# Neither cec_thermal2d.py (a single flat EPS_RAD=0.9 "soldermask emissivity" applied
# board-wide) nor cec_synth_pipeline.py (no radiation term at all) currently supports
# per-region emissivity or an enclosed-product two-surface exchange. This section adds
# both, without touching either file.

DEFAULT_EMISSIVITY = 0.90   # whole-board matte-black-soldermask fallback; IDENTICAL
                            # value to cec_thermal2d.EPS_RAD ("soldermask emissivity"),
                            # reused here rather than re-derived so a caller with no
                            # per-region data gets the SAME number the existing 2.5D
                            # solver already uses. Consistent with the non-metallic-
                            # coating emissivity class (paints/epoxies ~0.90-0.96,
                            # Incropera Table A.11 -- CONFIRMED class, this exact digit
                            # is the pre-existing repo constant, not independently
                            # re-derived).

# Per-region emissivity table for boards/materials this platform actually has, beyond
# the single whole-board fallback. Source class: Incropera & DeWitt Table A.11 ("Total,
# Normal (or Hemispherical) Emissivity of Selected Surfaces"). UNVERIFIED-PRECISION:
# this session could not fetch a live primary copy of Table A.11 (see the module
# docstring's air-table note for the same caveat); values below are representative
# midpoints of the well-known ranges for each finish class, not exact table entries --
# flagged for a reviewer to tighten against a primary table before high-stakes use.
EMISSIVITY_TABLE = {
    "soldermask_matte_black": DEFAULT_EMISSIVITY,   # cec_thermal2d.EPS_RAD (see above)
    "copper_bare_polished":   0.04,                 # polished Cu ~0.02-0.05 (UNVERIFIED-PRECISION)
    "copper_oxidized":        0.65,                 # oxidized/tarnished Cu ~0.4-0.8 (UNVERIFIED-PRECISION)
    "enig_gold_finish":       0.03,                 # polished gold ~0.02-0.04 (UNVERIFIED-PRECISION)
    "aluminum_polished":      0.05,                 # polished Al ~0.04-0.06 (UNVERIFIED-PRECISION)
    "aluminum_anodized":      0.84,                 # anodized Al ~0.7-0.9 (UNVERIFIED-PRECISION)
    "steel_painted":          0.90,                 # any paint/epoxy coating, non-metallic (same class as soldermask)
    "steel_bare_oxidized":    0.80,                 # oxidized steel/iron ~0.6-0.9 (UNVERIFIED-PRECISION)
    "fr4_bare_laminate":      0.90,                 # epoxy-glass laminate, non-metallic coating class
}


@dataclass
class RegionEmissivity:
    """One radiating region of a board surface. `area_frac` is this region's share of
    the TOTAL radiating area (0..1); if several regions' area_frac do not sum to 1 they
    are re-normalized by `effective_emissivity()` (equal-weighted degrade if none of the
    fractions are known -- documented, not silent). `citation`/`unverified` carry T0's
    own per-region provenance through when available (optional, informational only)."""
    name: str
    emissivity: float
    area_frac: float = None
    citation: str = None
    unverified: bool = False


def region_emissivity_from_thermal_sources(board_path=None, *, fallback=None):
    """Consume T0's (cec_thermal_sources.py) per-region emissivity extraction.

    T0 LANDED IN THIS CHECKOUT DURING THIS SESSION (a genuinely parallel wave-1
    module -- absent when this function was first authored, so the original pass
    coded defensively against a best-guess format; T0's REAL, now-landed contract is
    documented in `cec_thermal_sources.py`'s own module docstring under "EMISSIVITY
    FORMAT CONTRACT" and is parsed as the PRIMARY shape below):

        emissivity_regions(pcb_path) -> {
            "board": <str>, "board_area_mm2": <float>,
            "regions": [{"class": <str>, "area_mm2": <float>,
                        "area_fraction": <float>, "emissivity": <float>,
                        "citation": <str>, "unverified": <bool>}, ...],
        }
    `regions` is a strict partition of the board area (fractions sum to ~1.0).

    Kept ADDITIONALLY (secondary fallback shapes, in case T0's contract drifts or a
    different board-family module implements the same idea differently later):
      `dict[region_name -> emissivity]`, or a bare `list[{"emissivity":.., ...}]`.

    On ANY failure (module absent, function absent, bad path, wrong shape, exception
    of any kind -- e.g. `emissivity_regions` itself raises RuntimeError on a
    pcbnew-less host or a degenerate board outline, by T0's own documented design)
    this NEVER raises -- it returns `fallback`, or if `fallback` is None, the single
    documented whole-board matte-soldermask-average region."""
    if fallback is None:
        fallback = [RegionEmissivity("whole_board_fallback", DEFAULT_EMISSIVITY, 1.0)]
    try:
        import cec_thermal_sources as _ts                        # noqa: F401  (T0 module)
    except Exception:                                             # noqa: BLE001
        return fallback

    def _normalize(raw):
        # PRIMARY: T0's real, documented contract -- a dict with a "regions" list.
        if isinstance(raw, dict) and isinstance(raw.get("regions"), list) and raw["regions"]:
            regions = []
            for r in raw["regions"]:
                regions.append(RegionEmissivity(
                    str(r.get("class", "region")), float(r["emissivity"]),
                    r.get("area_fraction"), r.get("citation"),
                    bool(r.get("unverified", False))))
            return regions
        # SECONDARY (defensive fallback shapes, contract-drift tolerant):
        if isinstance(raw, dict):
            n = len(raw) or 1
            regions = []
            for name, eps in raw.items():
                regions.append(RegionEmissivity(str(name), float(eps), 1.0 / n))
            return regions or None
        if isinstance(raw, (list, tuple)):
            regions = []
            for r in raw:
                if not isinstance(r, dict) or "emissivity" not in r:
                    return None
                name = r.get("name") or r.get("region") or "region"
                regions.append(RegionEmissivity(str(name), float(r["emissivity"]),
                                                r.get("area_frac")))
            total = sum(r.area_frac for r in regions if r.area_frac)
            if total and abs(total - 1.0) > 1e-6:
                for r in regions:
                    if r.area_frac:
                        r.area_frac = r.area_frac / total
            return regions or None
        return None

    for fn_name in ("emissivity_regions", "region_emissivity_map", "emissivity_map"):
        fn = getattr(_ts, fn_name, None)
        if fn is None:
            continue
        try:
            raw = fn(board_path)
            regions = _normalize(raw)
            if regions:
                return regions
        except Exception:                                         # noqa: BLE001
            continue
    return fallback


def effective_emissivity(regions):
    """Area-weighted average emissivity over a list of `RegionEmissivity`. EXACT (not
    an approximation) for the uniform-surface-temperature assumption this whole-board
    boundary-condition library makes: q = eps*sigma*(Ts^4-Tsurr^4)*A is linear in both
    eps and A at a single Ts, so sum(eps_i*A_i)*sigma*(...) == eps_avg*A_total*sigma*(...)
    identically. A per-cell FEM integration (a future pass) would apply per-region
    emissivity directly instead of collapsing to one average."""
    if not regions:
        return DEFAULT_EMISSIVITY
    known = [r for r in regions if r.area_frac is not None]
    if known and abs(sum(r.area_frac for r in known) - 1.0) < 1e-3:
        return sum(r.emissivity * r.area_frac for r in known)
    return sum(r.emissivity for r in regions) / len(regions)       # equal-weight degrade


def radiative_flux_small_in_large(Ts_C, Tsurr_C, emissivity, area_m2=1.0):
    """EXACT gray-body radiative heat rate [W] from a small object (or a board whose
    surrounding case-interior air/walls are much larger and effectively isothermal) to
    its surroundings: q = eps*sigma*A*(Ts^4 - Tsurr^4), all temperatures in Kelvin
    internally (Incropera & DeWitt Eq. 1.7 / Cengel Eq. 1-27, both textbooks present
    the identical "small gray object in a large isothermal enclosure" simplification
    -- CONFIRMED formula/definition this session). This is also `cec_thermal2d.py`'s
    own per-cell radiation term (`eps_rad*sigma*(T^4-Ta^4)`) generalized with a
    configurable surroundings temperature and a real area, matching that module's
    convention exactly so the two are directly comparable. Positive = net loss from
    the surface. Posture: OPEN-BOARD-IN-CASE (surroundings = the case interior,
    effectively infinite/isothermal relative to the board)."""
    Ts_K = Ts_C + 273.15
    Tsurr_K = Tsurr_C + 273.15
    return emissivity * SIGMA_SB * area_m2 * (Ts_K ** 4 - Tsurr_K ** 4)


radiative_loss_open_board_in_case = radiative_flux_small_in_large  # named-posture alias


def h_rad_linear(Ts_C, Tsurr_C, emissivity):
    """Linearized radiation heat-transfer coefficient [W/m^2K]:
        h_r = eps*sigma*(Ts+Tsurr)*(Ts^2+Tsurr^2)          (Ts, Tsurr in Kelvin)
    (Incropera & DeWitt Eq. 1.9, "linearized radiation coefficient" -- CONFIRMED this
    session). This is an EXACT algebraic factorization of a^4-b^4 = (a-b)(a+b)(a^2+b^2),
    NOT an approximation: h_r*(Ts-Tsurr) == radiative_flux_small_in_large(...)/area for
    any single (Ts, Tsurr) pair (asserted in the anchor tests). Its practical value is
    for ITERATIVE/Picard solvers (like cec_thermal2d._thermal_solve's g_of_T) that want
    a per-cell conductance to add straight into a linear system diagonal, exactly the
    pattern that module already uses for its own (non-linearized, but algebraically
    equivalent) g_of_T -- this function gives the same number in the h-coefficient
    form some solvers expect instead of the loss/dT form."""
    Ts_K = Ts_C + 273.15
    Tsurr_K = Tsurr_C + 273.15
    return emissivity * SIGMA_SB * (Ts_K + Tsurr_K) * (Ts_K ** 2 + Tsurr_K ** 2)


def two_surface_enclosure_flux(T1_C, T2_C, eps1, eps2, A1_m2, A2_m2, F12=1.0):
    """Net radiative exchange [W] between two gray, diffuse, isothermal surfaces
    forming a closed two-surface enclosure (surface 1 = the board/component, surface 2
    = the enclosing case wall) -- the standard radiation-network resistance formula
    (Incropera & DeWitt Eq. 13.23-13.24 class / Modest, "Radiative Heat Transfer,"
    Ch. 6 -- CONFIRMED general form this session; this is the textbook two-surface-
    enclosure result, not a novel derivation):

        q12 = sigma*(T1^4-T2^4) / [ (1-eps1)/(eps1*A1) + 1/(A1*F12) + (1-eps2)/(eps2*A2) ]

    F12 defaults to 1.0 (surface 1 sees ONLY surface 2 -- valid when the board is
    small and fully enclosed by the case wall, or for two closely-spaced directly-
    facing parallel plates where gap << plate dimensions, both common engineering
    approximations -- NOT the exact Hamilton & Morgan aligned-parallel-rectangles
    closed form, which this pass could not independently re-verify to the needed
    precision this session and so deliberately does NOT implement; a caller with a
    real view factor from a verified source should pass it directly).

    CONSISTENCY CHECK (asserted in tests, not just claimed): as A2_m2 -> very large
    (or eps2 -> 1), this reduces EXACTLY to `radiative_flux_small_in_large` -- the
    OPEN-BOARD-IN-CASE posture is the A2->inf limit of the ENCLOSED-PRODUCT posture,
    which is the physically-correct relationship between the two named postures."""
    if A1_m2 <= 0 or F12 <= 0:
        return 0.0
    T1_K = T1_C + 273.15
    T2_K = T2_C + 273.15
    R = (1.0 - eps1) / (eps1 * A1_m2) + 1.0 / (A1_m2 * F12) + (1.0 - eps2) / (eps2 * max(A2_m2, 1e-12))
    return SIGMA_SB * (T1_K ** 4 - T2_K ** 4) / R


def radiative_loss_enclosed_product(Ts_C, Twall_C, eps_board, eps_wall, A_board_m2,
                                    A_wall_m2, F12=1.0):
    """Named-posture wrapper: ENCLOSED-PRODUCT radiative exchange between the board
    (or component) surface and the product's own enclosure wall -- see
    `two_surface_enclosure_flux` for the formula and its citation."""
    return two_surface_enclosure_flux(Ts_C, Twall_C, eps_board, eps_wall, A_board_m2,
                                      A_wall_m2, F12)


def radiation_fraction_still_air(Ts_C, Tamb_C, emissivity, L_c_m, orientation="vertical_plate"):
    """Composable sanity helper: at the SAME surface temperature/area, what fraction of
    total (radiative + natural-convective) heat rejection is radiation? This is the
    honest-verification target the completeness doc's "15-30% of still-air heat
    rejection" claim (Appendix A item D1 / Appendix B item I1) references. Returns
    dict(q_rad_W_m2, q_conv_W_m2, fraction_radiative, Ts_C, Tamb_C). Calls
    `h_natural_convection` (section 2) for the convective half, so this genuinely
    exercises both new subsystems together, not a canned number."""
    q_rad = radiative_flux_small_in_large(Ts_C, Tamb_C, emissivity, area_m2=1.0)
    T_film_C = 0.5 * (Ts_C + Tamb_C)
    hc = h_natural_convection(L_c_m, Ts_C - Tamb_C, T_film_C, orientation=orientation)
    q_conv = hc["h_W_m2K"] * abs(Ts_C - Tamb_C)
    total = q_rad + q_conv
    frac = (q_rad / total) if total > 0 else 0.0
    return {"q_rad_W_m2": q_rad, "q_conv_W_m2": q_conv, "fraction_radiative": frac,
            "Ts_C": Ts_C, "Tamb_C": Tamb_C, "h_conv_W_m2K": hc["h_W_m2K"]}


# =====================================================================================
# 2. CONVECTION (X2, the cheap parametric half -- full case CFD stays Tier-3)
# =====================================================================================

def nusselt_vertical_plate_churchill_chu(Ra, Pr, laminar_only=False):
    """Churchill & Chu (1975) correlation for natural convection off an isothermal
    VERTICAL plate (or a card-on-edge daughterboard). CONFIRMED (verified against a
    live secondary source this session):
      ALL-Ra form (any Ra_L, "one of the most widely used correlations", valid to
      the full turbulent range):
        Nu_L = { 0.825 + 0.387*Ra_L^(1/6) / [1+(0.492/Pr)^(9/16)]^(8/27) }^2
      LAMINAR-only form (Ra_L <= ~1e9, slightly tighter at low Ra):
        Nu_L = 0.68 + 0.670*Ra_L^(1/4) / [1+(0.492/Pr)^(9/16)]^(4/9)
    Both use the plate HEIGHT as the characteristic length L_c in Ra_L."""
    if Ra <= 0:
        return 0.0
    denom = (1.0 + (0.492 / Pr) ** (9.0 / 16.0)) ** (8.0 / 27.0)
    if laminar_only or Ra <= 1e9:
        d49 = (1.0 + (0.492 / Pr) ** (9.0 / 16.0)) ** (4.0 / 9.0)
        return 0.68 + 0.670 * Ra ** 0.25 / d49
    return (0.825 + 0.387 * Ra ** (1.0 / 6.0) / denom) ** 2


def nusselt_horizontal_cylinder_churchill_chu(Ra, Pr):
    """Churchill & Chu correlation for natural convection off a horizontal CYLINDER
    (used here as the default outer-surface convection model for the cable-fin model
    in section 3, treating the wire/cable as a thin horizontal cylinder). CONFIRMED
    this session, valid Ra_D <~ 1e12:
        Nu_D = { 0.60 + 0.387*Ra_D^(1/6) / [1+(0.559/Pr)^(9/16)]^(8/27) }^2
    Characteristic length is the cylinder DIAMETER."""
    if Ra <= 0:
        return 0.0
    denom = (1.0 + (0.559 / Pr) ** (9.0 / 16.0)) ** (8.0 / 27.0)
    return (0.60 + 0.387 * Ra ** (1.0 / 6.0) / denom) ** 2


def nusselt_horizontal_plate_mcadams(Ra, Pr, facing="up"):
    """McAdams-class correlations for a HORIZONTAL plate (a board lying flat, or the
    top/bottom skin of an enclosed product). CONFIRMED this session (validity ranges
    included -- outside them the correlation is used anyway, marked non-conforming by
    `h_natural_convection`'s returned `validity_ok` flag, rather than silently refusing):
      Hot surface facing UP (or a cold surface facing down):
        Nu_L = 0.54*Ra_L^(1/4)   for 1e4 <~ Ra_L <~ 1e7
        Nu_L = 0.15*Ra_L^(1/3)   for 1e7 <~ Ra_L <~ 1e11
      Hot surface facing DOWN (or a cold surface facing up):
        Nu_L = 0.27*Ra_L^(1/4)   for 1e5 <~ Ra_L <~ 1e10
    Characteristic length L_c = A_s/P (surface area / perimeter) is the recommended
    definition (CONFIRMED); the caller is responsible for passing Ra computed with
    that L_c (this function only evaluates the correlation, `h_natural_convection`
    below wires the recommended L_c through when `orientation` is a horizontal case)."""
    if Ra <= 0:
        return 0.0
    if facing == "up":
        return 0.54 * Ra ** 0.25 if Ra <= 1e7 else 0.15 * Ra ** (1.0 / 3.0)
    return 0.27 * Ra ** 0.25


def nusselt_flat_plate_forced(Re, Pr):
    """Forced-convection flat-plate correlation (Incropera Ch. 7 class; laminar branch
    CONFIRMED this session). LAMINAR average (Re_L < 5e5, 0.6<=Pr<=60 -- covers every
    case-airflow velocity 0-3 m/s over a board-scale length ~0.1 m; at 3 m/s and
    L=0.1m, Re ~= 2e4, comfortably laminar):
        Nu_L = 0.664*Re_L^0.5*Pr^(1/3)
    TURBULENT/mixed average (Re_L >= 5e5, included for completeness / a caller with a
    longer characteristic length, though our PC-case velocity range never reaches it):
        Nu_L = (0.037*Re_L^0.8 - 871)*Pr^(1/3)                       (Incropera form)
    """
    if Re <= 0:
        return 0.0
    if Re < 5e5:
        return 0.664 * Re ** 0.5 * Pr ** (1.0 / 3.0)
    return max(0.0, 0.037 * Re ** 0.8 - 871.0) * Pr ** (1.0 / 3.0)


_ORIENTATIONS = {"vertical_plate", "horizontal_plate_up", "horizontal_plate_down",
                 "horizontal_cylinder"}


def h_natural_convection(L_c_m, dT_C, T_film_C, orientation="vertical_plate"):
    """Orientation-correct natural-convection coefficient [W/m^2K] -- REPLACES a
    single flat h/C_nat assumption (what both `cec_thermal2d.C_NAT=1.40` -- one number
    for "both faces lumped", no orientation -- and every prior cec_synth_pipeline
    dashboard figure use) with the correlation matching the actual board/daughterboard
    orientation. Returns dict(h_W_m2K, Nu, Ra, Pr, L_c_m, orientation, correlation,
    validity_ok) -- `validity_ok` is a soft flag (never refuses), true when Ra falls
    inside the correlation's stated validity window."""
    p = air_properties(T_film_C)
    Ra = rayleigh(L_c_m, dT_C, T_film_C)
    if orientation == "vertical_plate":
        Nu = nusselt_vertical_plate_churchill_chu(Ra, p["Pr"])
        ok = True                                      # Churchill-Chu "all Ra" form
        name = "Churchill-Chu vertical plate (1975), all-Ra form"
    elif orientation == "horizontal_plate_up":
        Nu = nusselt_horizontal_plate_mcadams(Ra, p["Pr"], facing="up")
        ok = 1e4 <= Ra <= 1e11
        name = "McAdams horizontal plate, hot-face-up"
    elif orientation == "horizontal_plate_down":
        Nu = nusselt_horizontal_plate_mcadams(Ra, p["Pr"], facing="down")
        ok = 1e5 <= Ra <= 1e10
        name = "McAdams horizontal plate, hot-face-down"
    elif orientation == "horizontal_cylinder":
        Nu = nusselt_horizontal_cylinder_churchill_chu(Ra, p["Pr"])
        ok = Ra <= 1e12
        name = "Churchill-Chu horizontal cylinder (1975)"
    else:
        raise ValueError("orientation must be one of %s" % sorted(_ORIENTATIONS))
    h = Nu * p["k_W_mK"] / max(L_c_m, 1e-9)
    return {"h_W_m2K": h, "Nu": Nu, "Ra": Ra, "Pr": p["Pr"], "L_c_m": L_c_m,
            "orientation": orientation, "correlation": name, "validity_ok": ok}


def h_forced_convection(v_m_s, L_m, T_film_C):
    """Parametric forced-airflow coefficient [W/m^2K] over a flat plate (a board face
    in case airflow) as a function of local velocity -- the "cheap half" of X2 (full
    conjugate case CFD with real fan/obstruction geometry is Tier-3, out of scope here
    per the roadmap). At v_m_s below a small threshold this degrades to the natural-
    convection value at the same L_c (physically continuous: true h does not drop to
    zero as airflow stops, it approaches the natural-convection floor) rather than
    dividing by a near-zero Reynolds number."""
    if v_m_s < 0.05:
        # ambient temperature-difference-free floor: use a nominal small dT so the
        # natural-convection correlation has something to chew on; callers wanting
        # a real natural-convection number at their own dT should call
        # h_natural_convection directly. This branch exists only for numeric
        # continuity of the sweep at v->0, not as a precise physical claim.
        nc = h_natural_convection(L_m, 10.0, T_film_C, orientation="vertical_plate")
        return {"h_W_m2K": nc["h_W_m2K"], "Nu": nc["Nu"], "Re": 0.0, "Pr": nc["Pr"],
                "v_m_s": v_m_s, "L_m": L_m, "correlation": "natural-convection floor (v->0)"}
    p = air_properties(T_film_C)
    Re = reynolds(v_m_s, L_m, T_film_C)
    Nu = nusselt_flat_plate_forced(Re, p["Pr"])
    h = Nu * p["k_W_mK"] / max(L_m, 1e-9)
    name = "flat-plate forced convection, laminar avg (Incropera)" if Re < 5e5 else \
           "flat-plate forced convection, mixed/turbulent avg (Incropera)"
    return {"h_W_m2K": h, "Nu": Nu, "Re": Re, "Pr": p["Pr"], "v_m_s": v_m_s,
            "L_m": L_m, "correlation": name}


def h_forced_sweep(velocities_m_s=(0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0), L_m=0.1,
                   T_film_C=45.0):
    """The X2 parametric forced-airflow sweep: h(v) across the 0-3 m/s local-velocity
    range typical of PC-case internal airflow, at a fixed characteristic length and
    film temperature. Returns a list of `h_forced_convection` dicts, one per velocity
    -- exactly the "parametric ho sweep spanning still-air through typical case-fan
    velocities with sensitivity reporting" the completeness doc's C1 item asks for as
    the Tier-1 (cheap) alternative to full case CFD."""
    return [h_forced_convection(v, L_m, T_film_C) for v in velocities_m_s]


def nusselt_channel_elenbaas(Ra_b, b_over_L):
    """Elenbaas (1942) correlation for natural convection between two ISOTHERMAL
    VERTICAL PARALLEL PLATES forming a channel of spacing b and height L -- the
    daughterboard-standing-off-the-main-board geometry. As commonly reproduced in
    electronics-cooling design references (Kraus & Bar-Cohen, "Thermal Analysis and
    Control of Electronic Equipment," 1983; Simons, "Estimating Natural Convection
    Heat Transfer for Arrays of Vertical Parallel Plates," Electronics Cooling, Feb
    2002 -- both CONFIRMED to exist and cover exactly this correlation this session,
    but this session's fetch of either could not render the formula's exact typeset
    form, only its conceptual description and the ~50 optimum-Ra*(b/L) figure):
        Nu_b = (1/24)*Ra_b*(b/L) * {1 - exp[-35/(Ra_b*(b/L))]}^0.75
    where Ra_b is the standard Rayleigh number using SPACING b as the characteristic
    length (`rayleigh(L_c_m=b, ...)`). UNVERIFIED: the numeric constants 24, 35, and
    the 0.75 exponent are transcribed from well-established secondary engineering
    literature, NOT independently re-verified against a primary rendered source this
    session -- treat this correlation as a documented, moderate-confidence estimate;
    do not gate a design decision on it without a bench cross-check (the same
    OQ-86-class soak discipline this repo already applies to connector-thermal
    claims)."""
    if Ra_b <= 0 or b_over_L <= 0:
        return 0.0
    x = Ra_b * b_over_L
    if x <= 0:
        return 0.0
    return (x / 24.0) * (1.0 - math.exp(-35.0 / x)) ** 0.75


def h_channel_natural_convection(b_m, L_m, dT_C, T_film_C):
    """Natural-convection coefficient [W/m^2K] for the two-board channel case (the
    daughterboard's inner face, facing the main board across gap `b_m`, height
    `L_m`) via `nusselt_channel_elenbaas`. Returns dict(h_W_m2K, Nu_b, Ra_b,
    b_over_L, correlation)."""
    Ra_b = rayleigh(b_m, dT_C, T_film_C)
    b_over_L = b_m / max(L_m, 1e-9)
    Nu_b = nusselt_channel_elenbaas(Ra_b, b_over_L)
    p = air_properties(T_film_C)
    h = Nu_b * p["k_W_mK"] / max(b_m, 1e-9)
    return {"h_W_m2K": h, "Nu_b": Nu_b, "Ra_b": Ra_b, "b_over_L": b_over_L,
            "correlation": "Elenbaas channel (UNVERIFIED constants, see docstring)"}


def elenbaas_optimum_spacing_m(L_m, dT_C, T_film_C, *, target_Ra_b_star=50.0):
    """The Elenbaas OPTIMUM channel spacing: the spacing b that maximizes total heat
    dissipation for a fixed channel height L, obtained by setting the channel
    Rayleigh number Ra_b*(b/L) to ~50 (CONFIRMED this session -- the "~50" figure
    itself was independently corroborated by a live secondary source, even though
    the correlation's own numeric constants above are UNVERIFIED). Since
    Ra_b*(b/L) = [g*beta*dT/(nu*alpha*L)] * b^4, this solves in closed form (no
    iteration): b_opt = (target_Ra_b_star * L * nu * alpha / (g*beta*dT))^(1/4)."""
    p = air_properties(T_film_C)
    denom = G_STD * p["beta_1_K"] * abs(dT_C)
    if denom <= 0 or L_m <= 0:
        return 0.0
    return (target_Ra_b_star * L_m * p["nu_m2_s"] * p["alpha_m2_s"] / denom) ** 0.25


WAKE_RECIRCULATION_CAVEAT = (
    "NOT MODELED (honest limitation, per completeness-doc item E3/F3): a "
    "perpendicular card-on-edge daughterboard standing in case airflow creates a "
    "bluff-body wake/recirculation zone on its downstream face. The channel "
    "correlation above (Elenbaas) and the flat-plate forced correlation both assume "
    "attached, well-characterized flow -- neither captures a stagnant dead-air "
    "pocket sitting exactly on the daughterboard's only convective surface (it has "
    "no dedicated heat sink by design). Treat any 'forced' h reported for a "
    "standing daughterboard's downstream/wake-facing surface as OPTIMISTIC; a real "
    "answer needs local CFD around the connector/daughterboard assembly (Tier-3, "
    "completeness-doc item E3) or a bench thermal-imaging check (OQ-86-class soak)."
)


def standing_daughterboard_convection_estimate(b_m, L_m, dT_C, T_film_C,
                                                exposed_back_face=True,
                                                v_case_m_s=0.0):
    """Composable estimate for the standing (card-on-edge) daughterboard's total
    convective conductance: the inner face uses the two-board CHANNEL correlation
    (facing the main board across gap b_m); the outer/back face (if
    `exposed_back_face`) uses either natural convection (vertical plate) or, if
    `v_case_m_s` > 0, the forced-flat-plate correlation at that velocity -- but ALWAYS
    carries `WAKE_RECIRCULATION_CAVEAT` attached, since the back face is exactly the
    surface a real installed daughterboard's wake sits behind. Returns dict with both
    faces' h, a combined area-weighted h assuming equal-area faces, and the caveat
    text (never silently modeled away)."""
    inner = h_channel_natural_convection(b_m, L_m, dT_C, T_film_C)
    if exposed_back_face:
        outer = (h_forced_convection(v_case_m_s, L_m, T_film_C) if v_case_m_s > 0
                else h_natural_convection(L_m, dT_C, T_film_C, orientation="vertical_plate"))
    else:
        outer = {"h_W_m2K": 0.0}
    h_combined = 0.5 * (inner["h_W_m2K"] + outer["h_W_m2K"]) if exposed_back_face else inner["h_W_m2K"]
    return {"h_inner_channel_W_m2K": inner["h_W_m2K"], "h_outer_W_m2K": outer["h_W_m2K"],
            "h_combined_W_m2K": h_combined, "caveat": WAKE_RECIRCULATION_CAVEAT,
            "inner_detail": inner, "outer_detail": outer}


# =====================================================================================
# 3. CABLE FIN (X3) -- 1D fin model of a wire leaving a connector joint
# =====================================================================================
# Base fin ODE and its PRESCRIBED-TIP-TEMPERATURE solution: Incropera & DeWitt,
# "Fundamentals of Heat and Mass Transfer," Table 3.4 Case C (Eq. 3.82/3.83) --
# CONFIRMED this session against a live secondary source reproducing the table.
# The INSULATED-WIRE extension (folding the insulation's own radial conduction in
# series with the outer-surface convective film into one effective perimeter-loss
# conductance U') is a standard cable-ampacity-modeling technique, DERIVED HERE from
# first principles (a series-resistance combination), not itself a single textbook
# citation -- flagged as such rather than mis-attributed to Table 3.4.

AWG_TABLE_NOTE = ("AWG diameter formula: d_mm = 0.127 * 92^((36-n)/39) -- the exact "
                  "mathematical definition of the American Wire Gauge standard "
                  "(CONFIRMED, a defined standard, not a fitted correlation).")


def awg_conductor_area_mm2(awg):
    """Bare-copper conductor cross-sectional area [mm^2] for AWG size `awg` (may be
    fractional/negative for large gauges, e.g. -3 for 4/0, though every real case here
    is comfortably 12-20 AWG). d_mm = 0.127*92^((36-awg)/39); A = pi/4*d^2."""
    d_mm = 0.127 * 92.0 ** ((36.0 - awg) / 39.0)
    return math.pi / 4.0 * d_mm ** 2


@dataclass
class CableSpec:
    """A cable/harness conductor leaving a connector joint, modeled as a 1D fin.
    Either supply `awg` (AWG size, converted via `awg_conductor_area_mm2`) or
    `area_mm2` directly (e.g. for the ARGB fat-ganged-conductor case, which is not a
    single standard AWG size). `insulation_od_mm` is the INSULATED wire's outer
    diameter (the fin's convective surface); `insulation_k_W_mK` its bulk thermal
    conductivity; `k_conductor_W_mK` the (bare) conductor's own axial conductivity
    (copper, K_CU, unless otherwise specified)."""
    length_m: float
    awg: float = None
    area_mm2: float = None
    insulation_od_mm: float = 2.2          # typical 16 AWG-class hookup-wire insulated OD
    insulation_k_W_mK: float = 0.17        # PVC insulation, commonly cited ~0.14-0.21 W/mK
                                            # (UNVERIFIED-PRECISION: generic PVC compound
                                            # figure, not a specific vendor datasheet)
    k_conductor_W_mK: float = K_CU
    name: str = "cable"

    def conductor_area_m2(self):
        a_mm2 = self.area_mm2 if self.area_mm2 is not None else awg_conductor_area_mm2(self.awg)
        return a_mm2 * 1e-6

    def conductor_diameter_mm(self):
        a_mm2 = self.area_mm2 if self.area_mm2 is not None else awg_conductor_area_mm2(self.awg)
        return 2.0 * math.sqrt(a_mm2 / math.pi)


def eps_pcie_extension_16awg(length_m=0.3):
    """Preset: the platform's own EPS/PCIe daughterboard output extension cable --
    CEC-Platform-Ground-Truth-Spec.md Section 2.8 / CLAUDE.md: 'CEC's own extensions
    use 16 AWG' (a stated platform default, not an assumption of this module)."""
    return CableSpec(length_m=length_m, awg=16, name="eps_pcie_extension_16awg")


def pigtail_12vhpwr_16awg(length_m=0.15):
    """Preset: the 12VHPWR module's captive soldered output pigtail. The spec fixes
    the connector's per-pin current class (~8-10 A/conductor balanced, Section 6.1)
    but does not separately state this pigtail's wire gauge; this preset ASSUMES the
    platform's stated 16 AWG default (spec: 'all figures are AWG-dependent, and CEC's
    own extensions use 16 AWG') applies here too, since no distinct gauge is on
    record for this specific cable -- flagged as an assumption, not a spec fact."""
    return CableSpec(length_m=length_m, awg=16, name="pigtail_12vhpwr_16awg_ASSUMED")


def argb_fat_sata_feed(length_m=0.3):
    """Preset: the ARGB Controller's 'fat ganged cable' (spec Section 7.4/7.6): three
    SATA 5V contacts bonded to one thick conductor, ~7 A working total. Modeled as an
    equivalent conductor area = 3x an 18 AWG contact's area (three SATA power
    contacts, each nominally 18 AWG-class per common SATA power-cable construction --
    UNVERIFIED: the spec documents the bonding, not the per-contact wire gauge)
    ganged into one effective cross-section, NOT a standard AWG size, hence
    `area_mm2` rather than `awg`."""
    a1 = awg_conductor_area_mm2(18)
    return CableSpec(length_m=length_m, area_mm2=3.0 * a1, insulation_od_mm=4.0,
                     name="argb_fat_sata_feed_ganged3x18awg")


def _fin_u_prime(cable, h_outer_W_m2K):
    """Effective perimeter-based loss conductance U' [W/(m*K)] for an INSULATED wire:
    convection at the outer insulation surface in series with radial conduction
    through the insulation wall (annulus, conductor OD -> insulation OD). Standard
    series-resistance combination (derived here; see module/section docstring)."""
    d_cond_mm = cable.conductor_diameter_mm()
    d_ins_mm = max(cable.insulation_od_mm, d_cond_mm * 1.001)
    d_cond_m, d_ins_m = d_cond_mm * 1e-3, d_ins_mm * 1e-3
    r_conv = 1.0 / (h_outer_W_m2K * math.pi * d_ins_m)                      # K*m/W (per unit length)
    r_ins = math.log(d_ins_m / d_cond_m) / (2.0 * math.pi * cable.insulation_k_W_mK)
    return 1.0 / (r_conv + r_ins)


def cable_fin_conducted_heat(cable, T_joint_C, T_far_C, T_ambient_C, h_outer_W_m2K=None):
    """1D-fin conducted heat [W] at the connector-joint boundary from a cable running
    from the joint (base, prescribed T_joint_C) to a far end (tip, prescribed
    T_far_C -- e.g. the GPU-side or PSU-side connector temperature), losing heat to
    T_ambient_C along its insulated length via `h_outer_W_m2K` (default: natural
    convection off the insulation OD as a horizontal cylinder,
    `nusselt_horizontal_cylinder_churchill_chu` -- see that function; supply your own
    h for a forced-airflow case, e.g. from a Churchill-Bernstein cylinder-crossflow
    correlation, NOT implemented in this pass -- out of scope, noted honestly).

    SIGN CONVENTION: `q_into_joint_W` is POSITIVE when net heat flows FROM the far end
    INTO the joint (the far end is hotter -- adds to the joint's thermal budget);
    NEGATIVE when the cable acts as a heat SINK pulling heat out of the joint (the far
    end is cooler). This is the physically-intuitive sign, verified in the anchor
    tests against the short/highly-conductive-cable limit, where the fin equation
    reduces EXACTLY to simple Fourier conduction q = kA_c*(T_far-T_joint)/L (a hand-
    derivable closed-form check, done by expanding sinh/cosh for small mL -- see the
    test file).

    Uses the fin-with-prescribed-tip-temperature solution (Incropera Table 3.4 Case
    C) with base=joint (x=0, theta_b=T_joint-T_amb) and tip=far end (x=L,
    theta_L=T_far-T_amb):
        q_into_joint = M*(theta_L/theta_b - cosh(mL)) / sinh(mL)
        M = sqrt(U'*k*Ac)*theta_b ,  m = sqrt(U'/(k*Ac))
    Returns dict(q_into_joint_W, m_1_per_m, mL, U_prime_W_mK, h_outer_W_m2K,
    conductor_area_mm2, T_joint_C, T_far_C, T_ambient_C)."""
    Ac = cable.conductor_area_m2()
    k = cable.k_conductor_W_mK
    if h_outer_W_m2K is None:
        T_film = 0.5 * (T_joint_C + T_far_C) if T_joint_C != T_far_C else T_joint_C
        d_ins_m = max(cable.insulation_od_mm, cable.conductor_diameter_mm() * 1.001) * 1e-3
        dT_est = max(abs(T_joint_C - T_ambient_C), abs(T_far_C - T_ambient_C), 1.0)
        Ra = rayleigh(d_ins_m, dT_est, T_film)
        p = air_properties(T_film)
        Nu = nusselt_horizontal_cylinder_churchill_chu(Ra, p["Pr"])
        h_outer_W_m2K = max(Nu * p["k_W_mK"] / max(d_ins_m, 1e-9), 1e-6)
    Uprime = _fin_u_prime(cable, h_outer_W_m2K)
    theta_b = T_joint_C - T_ambient_C
    theta_L = T_far_C - T_ambient_C
    m = math.sqrt(max(Uprime / (k * Ac), 1e-30))
    L = max(cable.length_m, 1e-6)
    mL = m * L
    if abs(theta_b) < 1e-9:
        q_into_joint = 0.0
    else:
        M = math.sqrt(Uprime * k * Ac) * theta_b
        sh = math.sinh(mL)
        ch = math.cosh(mL)
        q_into_joint = M * (theta_L / theta_b - ch) / sh if sh > 1e-12 else \
            k * Ac * (theta_L - theta_b) / L                    # mL~0 short-cable limit
    return {"q_into_joint_W": q_into_joint, "m_1_per_m": m, "mL": mL,
            "U_prime_W_mK": Uprime, "h_outer_W_m2K": h_outer_W_m2K,
            "conductor_area_mm2": Ac * 1e6, "T_joint_C": T_joint_C,
            "T_far_C": T_far_C, "T_ambient_C": T_ambient_C, "cable": cable.name}


# =====================================================================================
# 4. FINITE CHASSIS NODE (H3) -- replaces the ideal-sink t_chassis=ambient assumption
# =====================================================================================
# Today: cec_thermal_overlay.py's case-cooling posture sets `cool_kw["t_chassis"] =
# ambient` unconditionally (an infinite-capacity, fixed-temperature sink); this
# section computes a more realistic finite-chassis sink temperature a future
# integration pass can pass into that same `t_chassis=` kwarg instead.

@dataclass
class ChassisNode:
    """A finite sheet-metal chassis panel acting as the case-cooling sink. Through-
    panel conduction resistance for a 1-2mm steel/aluminum panel (R = t/(k*A), t~1e-3m,
    k>=15 W/mK even for stainless, A of order 0.01-0.1 m^2) is >=2 orders of magnitude
    below its own EXTERIOR surface-film resistance (~1/(h*A), h~5-10 W/m2K) -- the
    standard "thermally thin panel" simplification (universal in electronics-enclosure
    thermal design, e.g. Kraus & Bar-Cohen, 'Thermal Analysis and Control of Electronic
    Equipment,' 1983) -- so this node treats the WHOLE panel as one isothermal surface
    exchanging with room air by convection+radiation on its exterior face only."""
    area_m2: float
    orientation: str = "vertical_plate"
    emissivity: float = 0.85               # painted/anodized sheet metal, Incropera
                                            # Table A.11 class (UNVERIFIED-PRECISION)
    material: str = "steel_painted"
    L_c_m: float = None                    # characteristic length for convection; if
                                            # None, sqrt(area_m2) is used (order-of-
                                            # magnitude default, not a claim of a
                                            # specific panel aspect ratio)


def chassis_room_resistance_K_per_W(chassis, T_chassis_C, T_room_C):
    """Combined convection+radiation thermal resistance [K/W] from the chassis
    EXTERIOR surface to room air, using this module's own natural-convection and
    linearized-radiation functions (section 1/2) rather than a hand-picked h -- so a
    "typical steel/aluminum panel resistance" is COMPUTED from cited correlations,
    not asserted as a bare number."""
    L_c = chassis.L_c_m or math.sqrt(max(chassis.area_m2, 1e-6))
    T_film = 0.5 * (T_chassis_C + T_room_C)
    hc = h_natural_convection(L_c, T_chassis_C - T_room_C, T_film,
                              orientation=chassis.orientation)["h_W_m2K"]
    hr = h_rad_linear(T_chassis_C, T_room_C, chassis.emissivity)
    h_total = max(hc + hr, 1e-9)
    return 1.0 / (h_total * chassis.area_m2)


def effective_chassis_sink_temperature_C(chassis, T_room_C, Q_system_other_W=0.0,
                                         preload_delta_C=0.0, board_Q_W=0.0, *,
                                         iters=30):
    """Self-consistent finite-chassis sink temperature: T_chassis = T_room +
    (Q_system_other_W + board_Q_W) * R_chassis_room(T_chassis) + preload_delta_C,
    solved by fixed-point iteration (R depends on T_chassis through the convection/
    radiation coefficients -- the same Picard-style pattern used throughout
    cec_synth_pipeline.py's own dT solves). `Q_system_other_W` is the whole-system
    heat load (GPU/CPU/PSU, everything but this one board) already reaching the
    chassis by the time this board's own contribution (`board_Q_W`) is added;
    `preload_delta_C` is an optional DIRECT elevation offset for when only an
    empirical "the case already runs N degrees over room ambient" figure is known,
    rather than a heat-load number.

    THIS is the number a future integration pass should pass as `t_chassis=` into
    cec_thermal2d.solve_board_thermal / cec_thermal_overlay's case-cooling posture,
    in place of today's `t_chassis=ambient` (H3's ideal-infinite-sink assumption)."""
    T = T_room_C + preload_delta_C
    Q = Q_system_other_W + board_Q_W
    for _ in range(iters):
        R = chassis_room_resistance_K_per_W(chassis, T, T_room_C)
        T_new = T_room_C + Q * R + preload_delta_C
        if abs(T_new - T) < 1e-4:
            T = T_new
            break
        T = T_new
    return T


# =====================================================================================
# 5. SOLDER INTERFACE (X8) -- per-joint interface resistance + IPC void-fraction derate
# =====================================================================================

SOLDER_K_W_MK = {
    "SAC305": 58.0,          # Sn96.5Ag3.0Cu0.5, ~58-60 W/mK @25C (CONFIRMED this
                              # session, Electronics Cooling, "Thermal Conductivity of
                              # Solders," Aug 2006)
    "SnPb63_37": 50.0,        # eutectic 63Sn37Pb (UNVERIFIED-PRECISION: commonly
                              # published ~50 W/mK across various solder-alloy
                              # datasheets; this session's Electronics Cooling fetch
                              # confirmed the SAC305 figure but did not surface this
                              # alloy's table row)
}
SOLDER_RESISTIVITY_OHM_M = {
    "SAC305": 1.4e-7,         # 13.0-14.5 microOhm*cm CONFIRMED this session (Kapp
                              # Alloy / Array Solders-class TDS figures) -> 1.30e-7 to
                              # 1.45e-7 Ohm*m; midpoint used
    "SnPb63_37": 1.5e-7,      # UNVERIFIED-PRECISION: commonly cited ~14-15 microOhm*cm
                              # class figure, not independently re-confirmed this
                              # session for this specific alloy
}
SOLDER_ALPHA_SN_PROXY = 0.0044   # 1/C -- UNVERIFIED, a pure-Sn TCR PROXY (Sn is >95%
                                 # of SAC-class alloys by mass) offered as an optional
                                 # temperature-dependence knob; solder-ALLOY TCR is not
                                 # as consistently published as pure-metal TCR, so the
                                 # default below is alpha=0.0 (untracked) unless a
                                 # caller opts in -- a documented scope simplification,
                                 # not a claim that solder R is temperature-independent.

IPC_VOID_FRACTION_DEFAULT = 0.25   # IPC-A-610 Class 2: a BGA solder ball is a defect
                                    # once the CUMULATIVE PROJECTED void area exceeds
                                    # 25% in x-ray (CONFIRMED this session). ANALOGY
                                    # FLAG: our joints are 2-terminal THT/SMD fillets
                                    # (shunt pads, connector tails), not BGA balls --
                                    # IPC-A-610/7095 do not publish as crisp a single
                                    # numeric void-area limit for that joint class, so
                                    # this default is borrowed from the best-documented
                                    # IPC void figure as a reasonable placeholder, not
                                    # a directly-applicable standard citation for THT
                                    # fillets -- UNVERIFIED for this specific use.


@dataclass
class SolderFilletGeometry:
    """A discrete-source-to-plane (or connector-tail-to-pad) solder interface. Values
    are ILLUSTRATIVE presets (see `shunt_2512_pad_fillet`/`connector_tht_tail_fillet`)
    demonstrating the API with representative round-number geometry -- NOT measured
    from any specific board file; a real integration should read actual pad/fillet
    geometry from the board (documented future hook, section 0 of this docstring)."""
    name: str
    area_mm2: float
    thickness_mm: float


def shunt_2512_pad_fillet():
    """Illustrative preset: one 2512-package current-shunt terminal-to-pad solder
    fillet. Order-of-magnitude geometry only (2512 body ~6.4x3.2mm; terminal contact
    footprint itself is a fraction of that) -- UNVERIFIED/ILLUSTRATIVE, not measured."""
    return SolderFilletGeometry("shunt_2512_pad", area_mm2=2.5, thickness_mm=0.10)


def connector_tht_tail_fillet():
    """Illustrative preset: one through-hole connector tail's barrel/annular solder
    fillet (order-of-magnitude only -- UNVERIFIED/ILLUSTRATIVE, not measured)."""
    return SolderFilletGeometry("connector_tht_tail", area_mm2=1.5, thickness_mm=0.30)


def solder_interface_thermal_resistance_K_per_W(geom, alloy="SAC305", void_fraction=0.0):
    """Per-joint solder-interface THERMAL resistance [K/W]: R = t/(k*A_eff),
    A_eff = area_mm2*(1-void_fraction). FIRST-ORDER area-fraction void derate (voids
    treated as locally non-conductive inclusions uniformly reducing the effective
    conduction area) -- a conservative-leaning simplified engineering approximation,
    NOT a specific published empirical void-vs-resistance curve (real derate depends
    on void morphology/location relative to the heat-flow path; IPC-7095 treats this
    in more depth). UNVERIFIED/DOCUMENTED-APPROXIMATION marker on the functional form;
    the solder conductivity input itself is cited (`SOLDER_K_W_MK`)."""
    k = SOLDER_K_W_MK[alloy]
    A_eff_m2 = max(geom.area_mm2 * (1.0 - void_fraction), 1e-9) * 1e-6
    t_m = geom.thickness_mm * 1e-3
    return t_m / (k * A_eff_m2)


def solder_fillet_segment(geom, alloy="SAC305", void_fraction=0.0, *, name=None,
                          alpha_per_C=0.0):
    """Per-joint solder-interface ELECTRICAL resistance segment, packaged to be
    "usable in series with the existing JointSegment/discrete-source treatments"
    (the task's own words) -- returns a REAL `cec_synth_pipeline.JointSegment` when
    that module is importable (so it drops straight into a `JointSpec.segments`
    tuple with zero adaptation), or a minimal duck-typed equivalent (same
    `.R_ohm(T)` method) when it is not (e.g. this module used standalone). The void
    fraction is applied as the SAME first-order effective-area derate as the thermal
    side above: effective cross-section = area_mm2*(1-void_fraction), so R_ohm scales
    up by 1/(1-void_fraction) relative to a void-free fillet of the same nominal
    geometry."""
    rho = SOLDER_RESISTIVITY_OHM_M[alloy] / max(1.0 - void_fraction, 1e-6)
    length_m_equiv = geom.thickness_mm       # JointSegment takes length in mm already
    seg_name = name or ("solder_%s_void%.0f%%" % (geom.name, void_fraction * 100))
    try:
        import cec_synth_pipeline as _S
        return _S.JointSegment(seg_name, cross_mm2=geom.area_mm2,
                               length_mm=length_m_equiv, rho_ohm_m=rho,
                               alpha_per_C=alpha_per_C)
    except Exception:                                             # noqa: BLE001
        @dataclass
        class _FallbackSegment:
            name: str
            cross_mm2: float
            length_mm: float
            rho_ohm_m: float = rho
            alpha_per_C: float = alpha_per_C

            def R_ohm(self, T_C=20.0):
                if self.cross_mm2 <= 0 or self.length_mm <= 0:
                    return 0.0
                r20 = self.rho_ohm_m * (self.length_mm * 1e-3) / (self.cross_mm2 * 1e-6)
                return r20 * (1.0 + self.alpha_per_C * (T_C - 20.0))
        return _FallbackSegment(seg_name, geom.area_mm2, length_m_equiv)


# =====================================================================================
# Kept in sync (duplicated, not imported) with cec_synth_pipeline._AMBIENT so this
# module's radiation/convection postures share the same three named operating points
# without a fragile cross-module private-name import; a test asserts equality against
# the live value in cec_synth_pipeline so drift there is caught here.
# =====================================================================================
POSTURE_AMBIENT_C = {"enclosed_passive": 50.0, "airflow": 35.0, "worst_case": 60.0}
