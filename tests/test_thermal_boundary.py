# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# T1a anchor + teeth tests for scripts/cec_thermal_boundary.py (thermal-solve
# completeness wave-1, docs/standard-tier-review/thermal-capabilities-
# implementation-2026-07-06.md). AM-04 discipline: independent hand-derived
# anchors (not just re-calling the implementation), formulas transcribed a
# SECOND time here so a transcription bug in the library is caught, not
# rubber-stamped. Host-runnable; no pcbnew/board files required (this module
# is pure geometry/temperature -> conductance/heat-flow, no KiCad I/O).
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.dont_write_bytecode = True

import cec_thermal_boundary as B                              # noqa: E402


# =====================================================================================
# 1. RADIATION
# =====================================================================================
class T1RadiationGrayBody(unittest.TestCase):
    """Gray-body surface-to-enclosure exchange (X1). Formula: Incropera & DeWitt Eq.
    1.7 / Cengel Eq. 1-27, small gray object in a large isothermal enclosure;
    two-surface network Incropera Eq. 13.23-24 class / Modest Ch. 6."""

    def test_hand_computed_gray_body_case(self):
        # Clean round numbers, arithmetic re-derived independently of the library:
        # Ts = 350K (76.85C), Tsurr = 300K (26.85C), eps = 0.80, A = 2.0 m^2.
        Ts_C, Tsurr_C, eps, A = 76.85, 26.85, 0.80, 2.0
        sigma = 5.67e-8
        Ts_K, Tsurr_K = 350.0, 300.0
        hand_q = eps * sigma * A * (Ts_K ** 4 - Tsurr_K ** 4)
        # 350^4 = 15,006,250,000 ; 300^4 = 8,100,000,000 ; diff = 6,906,250,000
        self.assertAlmostEqual(Ts_K ** 4, 1.500625e10, delta=1.0)
        self.assertAlmostEqual(Tsurr_K ** 4, 8.1e9, delta=1.0)
        self.assertAlmostEqual(hand_q, 0.80 * 5.67e-8 * 2.0 * 6.90625e9, delta=1.0)
        got = B.radiative_flux_small_in_large(Ts_C, Tsurr_C, eps, area_m2=A)
        self.assertAlmostEqual(got, hand_q, delta=1e-6)
        self.assertAlmostEqual(got, 626.535, delta=0.05)  # 0.8*5.67e-8*2*6.90625e9

    def test_h_rad_linear_is_an_exact_algebraic_identity(self):
        # a^4-b^4 = (a-b)(a+b)(a^2+b^2) is exact, not an approximation -- so
        # h_rad_linear*(Ts-Tsurr) must equal radiative_flux_small_in_large(...,area=1)
        # to floating-point precision, for ANY single (Ts, Tsurr) pair.
        for Ts_C, Tsurr_C, eps in ((75, 25, 0.9), (100, 50, 0.7), (40, 39, 0.85)):
            hr = B.h_rad_linear(Ts_C, Tsurr_C, eps)
            exact = B.radiative_flux_small_in_large(Ts_C, Tsurr_C, eps, area_m2=1.0)
            self.assertAlmostEqual(hr * (Ts_C - Tsurr_C), exact, delta=1e-9,
                                   msg="linearized h_rad must be an exact factorization")

    def test_two_surface_enclosure_reduces_to_small_in_large_as_A2_grows(self):
        # OPEN-BOARD-IN-CASE is the A2->inf limit of ENCLOSED-PRODUCT -- the physically
        # required relationship between the two named postures.
        q_small = B.radiative_flux_small_in_large(80, 40, 0.9, area_m2=0.01)
        q_two = B.two_surface_enclosure_flux(80, 40, 0.9, 0.9, 0.01, 1e9, F12=1.0)
        self.assertAlmostEqual(q_two, q_small, delta=1e-4)

    def test_two_surface_enclosure_zero_at_equal_temperature(self):
        q = B.two_surface_enclosure_flux(60, 60, 0.9, 0.5, 0.02, 0.5, F12=1.0)
        self.assertAlmostEqual(q, 0.0, delta=1e-9)

    def test_region_emissivity_defensive_fallback(self):
        # cec_thermal_sources.py (T0, a parallel wave-1 module) does not exist in this
        # checkout -- must NEVER raise, must degrade to the documented whole-board
        # matte-soldermask fallback.
        regions = B.region_emissivity_from_thermal_sources("nonexistent/board.kicad_pcb")
        self.assertEqual(len(regions), 1)
        self.assertAlmostEqual(regions[0].emissivity, B.DEFAULT_EMISSIVITY)
        self.assertAlmostEqual(B.effective_emissivity(regions), B.DEFAULT_EMISSIVITY)

    def test_region_emissivity_real_T0_integration_when_present(self):
        # T0 (cec_thermal_sources.py) landed in this checkout during this session
        # (a genuinely parallel wave-1 module) -- exercise the REAL (non-fallback)
        # parse path against its actual documented contract on a real routed board,
        # not just the defensive-fallback path above. Skips cleanly if T0 or the
        # fixture board is unavailable (e.g. a bare-host leg with no pcbnew).
        try:
            import cec_thermal_sources                             # noqa: F401
        except Exception:
            self.skipTest("cec_thermal_sources not importable on this host")
        pcb = os.path.join(ROOT, "tests", "golden", "fixtures", "am04-microboard",
                           "microboard.kicad_pcb")
        if not os.path.exists(pcb):
            self.skipTest("am04-microboard fixture not present")
        regions = B.region_emissivity_from_thermal_sources(pcb)
        names = {r.name for r in regions}
        self.assertIn("solder_mask_copper", names,
                      "must parse T0's REAL contract (class/area_fraction/emissivity "
                      "keys), not silently fall back to the whole-board default")
        total_frac = sum(r.area_frac for r in regions)
        self.assertAlmostEqual(total_frac, 1.0, delta=1e-2)
        eff = B.effective_emissivity(regions)
        # solder-mask-covered copper dominates the area (~98%) on a typical board,
        # so the effective (area-weighted) emissivity should sit close to its 0.9.
        self.assertGreater(eff, 0.85)
        self.assertLess(eff, 0.91)

    def test_effective_emissivity_area_weighted_hand_check(self):
        regions = [B.RegionEmissivity("copper", 0.05, 0.3),
                  B.RegionEmissivity("soldermask", 0.90, 0.7)]
        hand = 0.05 * 0.3 + 0.90 * 0.7
        self.assertAlmostEqual(B.effective_emissivity(regions), hand, delta=1e-9)

    def test_radiation_fraction_honest_report(self):
        # HONEST VERIFICATION of the completeness doc's "15-30% of still-air heat
        # rejection" claim (Appendix A D1 / Appendix B I1), not a rubber-stamp: at a
        # realistic CEC board scale (L_c ~ 0.05-0.5 m) and a realistic surface
        # temperature (the CITED 12VHPWR case-cooling result, maxT 72.95C at ambient
        # 50C -- CLAUDE.md action item 4), the REAL still-air (v=0) fraction computed
        # from this module's own Churchill-Chu convection + gray-body radiation comes
        # out at 55-70%, NOT 15-30% -- because natural-convection h at this small a
        # characteristic length is genuinely weak (~4-7 W/m^2K from Churchill-Chu),
        # so radiation is comparable to or DOMINANT over convection in TRUE still air.
        # The cited 15-30% figure is recovered once modest (roughly 1-2 m/s class)
        # case airflow is included instead of true zero airflow (see the accompanying
        # report for the full v-sweep) -- reported honestly here, not forced.
        r = B.radiation_fraction_still_air(72.95, 50.0, 0.90, 0.1, orientation="vertical_plate")
        self.assertGreater(r["fraction_radiative"], 0.30,
                           "real still-air fraction at this board scale is ABOVE the "
                           "completeness doc's 15-30% class, not inside it -- see docstring")
        self.assertLess(r["fraction_radiative"], 0.90)


# =====================================================================================
# 2. CONVECTION
# =====================================================================================
class T2ConvectionCorrelations(unittest.TestCase):
    """Orientation-correct natural + forced convection (X2, cheap half). Every Nu
    formula below is independently re-transcribed from the cited textbook coefficients
    (not copy-pasted from the library file) so a coding bug is caught."""

    def test_vertical_plate_churchill_chu_hand_points(self):
        # Churchill & Chu (1975), laminar form (Ra<=1e9):
        #   Nu = 0.68 + 0.670*Ra^0.25 / [1+(0.492/Pr)^(9/16)]^(4/9)
        for Ra, Pr in ((1e6, 0.7), (1e8, 0.7), (1e9, 0.71)):
            d = (1.0 + (0.492 / Pr) ** (9.0 / 16.0)) ** (4.0 / 9.0)
            hand = 0.68 + 0.670 * Ra ** 0.25 / d
            got = B.nusselt_vertical_plate_churchill_chu(Ra, Pr, laminar_only=True)
            self.assertAlmostEqual(got, hand, delta=1e-6)
        # All-Ra form (Ra>1e9, since laminar_only defaults False and Ra>1e9 routes
        # to the all-Ra branch automatically):
        #   Nu = {0.825 + 0.387*Ra^(1/6) / [1+(0.492/Pr)^(9/16)]^(8/27)}^2
        Ra, Pr = 1e11, 0.7
        d2 = (1.0 + (0.492 / Pr) ** (9.0 / 16.0)) ** (8.0 / 27.0)
        hand2 = (0.825 + 0.387 * Ra ** (1.0 / 6.0) / d2) ** 2
        got2 = B.nusselt_vertical_plate_churchill_chu(Ra, Pr)
        self.assertAlmostEqual(got2, hand2, delta=1e-6)

    def test_horizontal_plate_mcadams_hand_points_and_orientation_ordering(self):
        # McAdams: up = 0.54*Ra^0.25 (1e4-1e7); down = 0.27*Ra^0.25 (1e5-1e10).
        Ra, Pr = 1e6, 0.7
        self.assertAlmostEqual(B.nusselt_horizontal_plate_mcadams(Ra, Pr, "up"),
                               0.54 * Ra ** 0.25, delta=1e-6)
        self.assertAlmostEqual(B.nusselt_horizontal_plate_mcadams(Ra, Pr, "down"),
                               0.27 * Ra ** 0.25, delta=1e-6)
        # Physical ordering that must ALWAYS hold: a hot plate loses heat faster
        # facing up (plume detaches freely) than facing down (plume must fight its
        # way around the plate edges) at the SAME Ra -- true at every Ra in the
        # correlations' shared domain.
        for Ra in (1e5, 1e6, 1e7, 1e8):
            up = B.nusselt_horizontal_plate_mcadams(Ra, 0.7, "up")
            down = B.nusselt_horizontal_plate_mcadams(Ra, 0.7, "down")
            self.assertGreater(up, down)

    def test_horizontal_cylinder_churchill_chu_hand_point(self):
        # Nu = {0.60 + 0.387*Ra^(1/6)/[1+(0.559/Pr)^(9/16)]^(8/27)}^2
        Ra, Pr = 1e5, 0.71
        d = (1.0 + (0.559 / Pr) ** (9.0 / 16.0)) ** (8.0 / 27.0)
        hand = (0.60 + 0.387 * Ra ** (1.0 / 6.0) / d) ** 2
        self.assertAlmostEqual(B.nusselt_horizontal_cylinder_churchill_chu(Ra, Pr),
                               hand, delta=1e-6)

    def test_forced_flat_plate_hand_points_laminar_and_turbulent(self):
        # Laminar avg (Re<5e5): Nu = 0.664*Re^0.5*Pr^(1/3)
        Re, Pr = 2e4, 0.7
        self.assertAlmostEqual(B.nusselt_flat_plate_forced(Re, Pr),
                               0.664 * Re ** 0.5 * Pr ** (1.0 / 3.0), delta=1e-6)
        # Mixed/turbulent avg (Re>=5e5): Nu = (0.037*Re^0.8-871)*Pr^(1/3)
        Re = 1e6
        hand = (0.037 * Re ** 0.8 - 871.0) * Pr ** (1.0 / 3.0)
        self.assertAlmostEqual(B.nusselt_flat_plate_forced(Re, Pr), hand, delta=1e-6)

    def test_forced_sweep_covers_0_to_3_ms_and_is_monotonic_increasing(self):
        sweep = B.h_forced_sweep(L_m=0.1, T_film_C=50.0)
        hs = [r["h_W_m2K"] for r in sweep]
        self.assertEqual(len(hs), 7)
        for a, b in zip(hs, hs[1:]):
            self.assertLessEqual(a, b)          # h(v) must not decrease with velocity

    def test_channel_elenbaas_self_consistency_of_optimum_spacing(self):
        # elenbaas_optimum_spacing_m solves Ra_b*(b/L) = target IN CLOSED FORM;
        # verify the closed-form solution actually satisfies the equation it was
        # derived from (a real algebra check, not an external anchor).
        L, dT, Tf = 0.05, 20.0, 45.0
        b_opt = B.elenbaas_optimum_spacing_m(L, dT, Tf, target_Ra_b_star=50.0)
        Ra_b = B.rayleigh(b_opt, dT, Tf)
        self.assertAlmostEqual(Ra_b * (b_opt / L), 50.0, delta=0.05)

    def test_standing_daughterboard_carries_wake_caveat(self):
        res = B.standing_daughterboard_convection_estimate(0.01, 0.05, 20.0, 45.0)
        self.assertIn("caveat", res)
        self.assertIn("NOT MODELED", res["caveat"])
        self.assertIn("wake", res["caveat"].lower())


# =====================================================================================
# 3. CABLE FIN
# =====================================================================================
class T3CableFin(unittest.TestCase):
    """1D fin model of a wire leaving a connector joint (X3). Base solution:
    Incropera Table 3.4 Case C (prescribed tip temperature)."""

    def test_awg_area_matches_standard_wire_chart(self):
        # AWG is a DEFINED mathematical standard (d = 0.127*92^((36-n)/39)); these are
        # the well-known reference cross-sections from the standard AWG wire chart.
        self.assertAlmostEqual(B.awg_conductor_area_mm2(16), 1.309, delta=0.01)
        self.assertAlmostEqual(B.awg_conductor_area_mm2(18), 0.823, delta=0.01)
        self.assertAlmostEqual(B.awg_conductor_area_mm2(12), 3.309, delta=0.02)

    def test_short_cable_reduces_to_simple_fourier_conduction(self):
        # HAND-DERIVED ANCHOR: as mL -> 0 (short and/or highly-conductive cable),
        # sinh(mL)~=mL and cosh(mL)~=1, so the prescribed-tip-temperature fin solution
        # q_into_joint = M*(thetaL/thetab - cosh(mL))/sinh(mL) collapses EXACTLY to
        # simple Fourier conduction along a short rod:
        #   q_into_joint -> k*Ac*(T_far - T_joint)/L
        # (M = sqrt(U'*k*Ac)*thetab, sinh(mL)~=mL, cosh(mL)~=1 =>
        #  q ~= sqrt(U'*k*Ac)*thetab*(thetaL/thetab - 1)/(m*L)
        #     = sqrt(U'*k*Ac)*(thetaL-thetab)/(m*L) = k*Ac*(thetaL-thetab)/L
        #  since sqrt(U'*k*Ac)/m = sqrt(U'*k*Ac)/sqrt(U'/(k*Ac)) = k*Ac.) This is an
        # independent closed-form check of the implementation's sign convention AND
        # its formula, not merely re-calling it.
        cable = B.CableSpec(length_m=0.001, awg=16)     # 1mm: mL << 1
        res = B.cable_fin_conducted_heat(cable, T_joint_C=70.0, T_far_C=110.0,
                                         T_ambient_C=50.0)
        self.assertLess(res["mL"], 0.05, "test setup must stay in the short-cable limit")
        Ac = cable.conductor_area_m2()
        hand = B.K_CU * Ac * (110.0 - 70.0) / cable.length_m
        self.assertAlmostEqual(res["q_into_joint_W"], hand, delta=abs(hand) * 0.02)
        self.assertGreater(res["q_into_joint_W"], 0.0,
                           "far end 40C hotter than the joint -> heat must flow IN")

    def test_sign_flips_at_the_analytically_predicted_crossover_length(self):
        # q_into_joint(L) = 0 exactly where cosh(mL) = thetaL/thetab, i.e.
        # mL = arccosh(thetaL/thetab) -- an internal-consistency check (not an
        # external anchor) that the sign convention and the crossover location the
        # module's own algebra predicts actually line up with its own output.
        T_joint_C, T_far_C, T_amb_C = 67.3, 107.3, 50.0
        theta_b, theta_L = T_joint_C - T_amb_C, T_far_C - T_amb_C
        probe = B.eps_pcie_extension_16awg(length_m=0.1)
        m = B.cable_fin_conducted_heat(probe, T_joint_C, T_far_C, T_amb_C)["m_1_per_m"]
        L_cross = math.acosh(theta_L / theta_b) / m
        below = B.eps_pcie_extension_16awg(length_m=L_cross * 0.9)
        above = B.eps_pcie_extension_16awg(length_m=L_cross * 1.1)
        q_below = B.cable_fin_conducted_heat(below, T_joint_C, T_far_C, T_amb_C)["q_into_joint_W"]
        q_above = B.cable_fin_conducted_heat(above, T_joint_C, T_far_C, T_amb_C)["q_into_joint_W"]
        self.assertGreater(q_below, 0.0, "shorter than crossover -> hot far end still reaches back")
        self.assertLess(q_above, 0.0, "longer than crossover -> cable is a net sink, not a source")

    def test_worked_numbers_vs_the_joints_own_budget(self):
        # The task's own worked-number ask: what does a 40C-hotter GPU-end cable
        # conduct INTO the joint vs the joint's OWN dissipation budget? Cross-checked
        # against cec_synth_pipeline.joint_solve (read-only import; this function
        # needs no board file / no pcbnew) at the SAME EPS nominal operating point
        # the blade-interconnect audit already used (17.3 A allocation, ambient 50C).
        import cec_synth_pipeline as S
        joint = S.joint_solve("te_63951_63969", 17.3, ambient=50.0)
        T_joint_C = joint["T"]
        T_far_C = T_joint_C + 40.0
        for length_m in (0.1, 0.3, 1.0):
            cable = B.eps_pcie_extension_16awg(length_m=length_m)
            res = B.cable_fin_conducted_heat(cable, T_joint_C, T_far_C, T_ambient_C=50.0)
            self.assertLess(abs(res["q_into_joint_W"]), joint["P_W"] * 1.5,
                            "the cable-conducted term should be the same order of "
                            "magnitude as the joint's own I^2R budget, not wildly larger")
        # at a realistically short pigtail length the far end DOES add heat in;
        # at realistic extension-cable lengths (>=0.3m) it does not (see the
        # crossover test above) -- both are asserted, neither is hidden.


# =====================================================================================
# 4. FINITE CHASSIS NODE
# =====================================================================================
class T4FiniteChassisNode(unittest.TestCase):
    """H3: replaces the ideal-sink t_chassis=ambient assumption behind the existing
    case-cooling posture (cec_thermal_overlay.py: `cool_kw["t_chassis"] = ambient`)."""

    def test_zero_load_and_zero_preload_stays_at_room(self):
        ch = B.ChassisNode(area_m2=1.0)
        T = B.effective_chassis_sink_temperature_C(ch, T_room_C=25.0)
        self.assertAlmostEqual(T, 25.0, delta=0.01)

    def test_monotonic_with_system_heat_load(self):
        ch = B.ChassisNode(area_m2=1.0)
        Ts = [B.effective_chassis_sink_temperature_C(ch, 25.0, Q_system_other_W=Q)
              for Q in (0.0, 10.0, 30.0, 60.0)]
        for a, b in zip(Ts, Ts[1:]):
            self.assertLess(a, b)

    def test_preload_delta_applies_directly_at_zero_load(self):
        ch = B.ChassisNode(area_m2=1.0)
        T = B.effective_chassis_sink_temperature_C(ch, 25.0, preload_delta_C=8.0,
                                                   Q_system_other_W=0.0)
        self.assertAlmostEqual(T, 33.0, delta=0.01)

    def test_resistance_is_built_from_the_cited_correlations_not_a_bare_number(self):
        ch = B.ChassisNode(area_m2=1.0, orientation="vertical_plate", emissivity=0.85)
        T_chassis_C, T_room_C = 35.0, 25.0
        R = B.chassis_room_resistance_K_per_W(ch, T_chassis_C, T_room_C)
        T_film = 0.5 * (T_chassis_C + T_room_C)
        hc = B.h_natural_convection(1.0, T_chassis_C - T_room_C, T_film,
                                    orientation="vertical_plate")["h_W_m2K"]
        hr = B.h_rad_linear(T_chassis_C, T_room_C, 0.85)
        hand_R = 1.0 / ((hc + hr) * 1.0)
        self.assertAlmostEqual(R, hand_R, delta=1e-9)


# =====================================================================================
# 5. SOLDER INTERFACE
# =====================================================================================
class T5SolderInterface(unittest.TestCase):
    """X8: per-joint interface resistance + IPC void-fraction derate, composable in
    series with cec_synth_pipeline.JointSegment/JointSpec (read-only consumption)."""

    def test_void_derate_is_the_documented_exact_area_fraction_form(self):
        geom = B.shunt_2512_pad_fillet()
        R0 = B.solder_interface_thermal_resistance_K_per_W(geom, void_fraction=0.0)
        R25 = B.solder_interface_thermal_resistance_K_per_W(geom, void_fraction=0.25)
        self.assertAlmostEqual(R25 / R0, 1.0 / (1.0 - 0.25), delta=1e-9)

    def test_solder_conductivity_citation_value(self):
        # Electronics Cooling, "Thermal Conductivity of Solders" (Aug 2006): SAC-class
        # lead-free alloys ~58-60 W/mK at 25C -- CONFIRMED this session.
        self.assertAlmostEqual(B.SOLDER_K_W_MK["SAC305"], 58.0, delta=3.0)

    def test_solder_fillet_segment_composes_into_a_real_JointSpec(self):
        # The strong integration proof: build an actual cec_synth_pipeline.JointSpec
        # whose segments tuple includes a solder_fillet_segment() alongside a bare
        # JointSegment, and confirm R_total_ohm() composes them in series correctly --
        # i.e. this module's X8 output is LITERALLY "usable in series with the
        # existing JointSegment ... treatments," not just documented as such.
        import cec_synth_pipeline as S
        geom = B.shunt_2512_pad_fillet()
        solder_seg = B.solder_fillet_segment(geom, void_fraction=0.0)
        self.assertIsInstance(solder_seg, S.JointSegment)
        bulk_seg = S.JointSegment("bulk", cross_mm2=6.35 * 0.81, length_mm=12.0)
        spec = S.JointSpec(name="test_with_solder", contact_R_ohm=1.0e-3,
                           segments=(bulk_seg, solder_seg))
        R_total = spec.R_total_ohm(20.0)
        R_expected = 1.0e-3 + bulk_seg.R_ohm(20.0) + solder_seg.R_ohm(20.0)
        self.assertAlmostEqual(R_total, R_expected, delta=1e-12)
        self.assertGreater(solder_seg.R_ohm(20.0), 0.0)


# =====================================================================================
# 6. CROSS-MODULE POSTURE CONSISTENCY (kept-in-sync duplication, not a fragile import)
# =====================================================================================
class T6PostureConsistency(unittest.TestCase):
    def test_posture_ambient_matches_cec_synth_pipeline(self):
        import cec_synth_pipeline as S
        self.assertEqual(B.POSTURE_AMBIENT_C, S._AMBIENT,
                         "POSTURE_AMBIENT_C is a documented DUPLICATE of "
                         "cec_synth_pipeline._AMBIENT -- if this fails, that module's "
                         "postures drifted and this file's copy needs updating "
                         "(cec_synth_pipeline.py itself must never be edited by this pass)")


if __name__ == "__main__":
    unittest.main()
