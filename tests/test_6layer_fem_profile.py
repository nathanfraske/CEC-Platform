#!/usr/bin/env python3
"""Regression checks for the approved six-layer fabrication profiles."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fab_profile as FAB  # noqa: E402

try:
    import numpy as np  # noqa: E402
    import cec_thermal2d as T2  # noqa: E402
    import cec_thermal_overlay as TOV  # noqa: E402
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest("numpy/scipy thermal dependencies required") from exc


HIGH = "jlcpcb_6l_pofv_high_current"
SIGNAL = "jlcpcb_6l_pofv_signal"


class FabricationProfileTest(unittest.TestCase):
    def test_exact_vendor_copper_thickness_reaches_solver(self):
        for profile in (HIGH, SIGNAL):
            stack = FAB.stackup_oz(profile)
            for layer in FAB.COPPER_LAYERS:
                modeled_mm = stack[layer] * T2.OZ_M * 1000.0
                self.assertAlmostEqual(
                    modeled_mm, FAB.copper_thickness_mm(profile, layer),
                    places=12)
            self.assertAlmostEqual(
                FAB.copper_thickness_mm(profile, "In3.Cu"), 0.0152,
                places=12)

    def test_half_ounce_inner_width_is_not_treated_as_one_ounce(self):
        half_oz = FAB.ipc2221_required_width_mm(
            10.0, "In3.Cu", profile_name=HIGH)
        one_oz = FAB.ipc2221_required_width_mm(
            10.0, "In3.Cu", copper_mm=FAB.OZ_COPPER_MM)
        expected = FAB.OZ_COPPER_MM / 0.0152
        self.assertAlmostEqual(half_oz / one_oz, expected, places=10)
        self.assertGreater(half_oz, 2.0 * one_oz)

    def test_board_families_select_the_approved_profiles(self):
        self.assertEqual(
            TOV.board_fab_profile("hub-standard-rev2.kicad_pcb"), SIGNAL)
        for hint in ("atx-24pin-rev3", "12vhpwr-standard",
                     "eps-8pin", "pcie-3port"):
            self.assertEqual(TOV.board_fab_profile(hint), HIGH)

    def test_thermal_configs_use_six_exact_layers(self):
        _, hub_stack, _, _ = TOV.board_thermal_config("hub-standard-rev2")
        _, atx_stack, _, _ = TOV.board_thermal_config("atx-24pin-rev3")
        self.assertEqual(set(hub_stack), set(FAB.COPPER_LAYERS))
        self.assertEqual(set(atx_stack), set(FAB.COPPER_LAYERS))
        self.assertAlmostEqual(hub_stack["F.Cu"] * T2.OZ_M * 1000.0,
                               0.035, places=12)
        self.assertAlmostEqual(atx_stack["F.Cu"] * T2.OZ_M * 1000.0,
                               0.070, places=12)
        self.assertAlmostEqual(atx_stack["In3.Cu"] * T2.OZ_M * 1000.0,
                               0.0152, places=12)

    def test_hub_thermal_map_matches_mux_and_port_fuse_topology(self):
        currents, _, terminals, _ = TOV.board_thermal_config(
            "hub-standard-rev2")
        self.assertEqual(currents["/PSU_5V_KVM"], 2.5)
        self.assertEqual(currents["/+5V_HOLD"], 0.5)
        self.assertEqual(
            terminals["/PSU_5V"],
            {"refs_src": ["U5"], "refs_sink": ["U11"]})
        self.assertEqual(
            terminals["/PSU_5V_KVM"],
            {"refs_src": ["U11"], "refs_sink": ["U7"]})
        self.assertEqual(
            terminals["+5VSB"],
            {"refs_src": ["U7"],
             "refs_sink": ["F1", "F2", "F3", "F4"]})
        for index in range(1, 5):
            self.assertEqual(
                terminals[f"/VCC_P{index}"],
                {"refs_src": [f"F{index}"],
                 "refs_sink": [f"J{index + 1}"]})

    def test_real_hub_thermal_map_uses_exact_hierarchical_net_names(self):
        board = os.path.join(
            ROOT, "beta", "hub-standard-rev2", "candidate",
            "hub-standard-rev2-candidate.kicad_pcb")
        currents, _, terminals, _ = TOV.board_thermal_config(board)
        self.assertIn("/POWER INPUT + SOURCE SELECTION/PSU_5V", currents)
        self.assertIn("/HOLD-UP + 3V3 REGULATOR/+5V_HOLD", currents)
        self.assertIn("/CAN + FOUR MODULE PORTS + STACK/VCC_P4", currents)
        self.assertNotIn("/PSU_5V", currents)
        self.assertEqual(set(currents), set(terminals))


class SixLayerFemTest(unittest.TestCase):
    def test_layer_centers_follow_exact_five_dielectrics(self):
        stack = FAB.stackup_oz(HIGH)
        dielectrics = FAB.dielectric_mm(HIGH)
        z = T2._layer_z_centers(stack, dielectrics)
        self.assertEqual(list(z), list(FAB.COPPER_LAYERS))
        for a, b in zip(FAB.COPPER_LAYERS, FAB.COPPER_LAYERS[1:]):
            expected_m = (
                FAB.copper_thickness_mm(HIGH, a) / 2.0
                + dielectrics[(a, b)]
                + FAB.copper_thickness_mm(HIGH, b) / 2.0
            ) * 1e-3
            self.assertAlmostEqual(z[b] - z[a], expected_m, places=12)

    def test_through_via_is_segmented_across_all_six_layers(self):
        z = T2._layer_z_centers(
            FAB.stackup_oz(HIGH), FAB.dielectric_mm(HIGH))
        links = T2._collect_vertical_links(
            [{"drill_mm": 0.3, "span": list(FAB.COPPER_LAYERS)}],
            set(FAB.COPPER_LAYERS), z, 25e-6)
        self.assertEqual([(a, b) for a, b, _ in links], list(zip(
            FAB.COPPER_LAYERS, FAB.COPPER_LAYERS[1:])))
        self.assertTrue(all(resistance > 0 for _, _, resistance in links))

    def test_exact_thinner_inner_copper_increases_joule_loss(self):
        grid = T2.Grid(0.0, 0.0, 20.0, 5.0, 1.0)
        mask = np.ones((grid.ny, grid.nx), dtype=bool)
        src = [("In3.Cu", grid.idx(0, y)) for y in range(grid.ny)]
        sink = [("In3.Cu", grid.idx(grid.nx - 1, y))
                for y in range(grid.ny)]
        common = dict(
            net_layer_mask={"PWR": {"In3.Cu": mask}},
            net_currents={"PWR": 10.0}, grid=grid,
            src_sink_cells={"PWR": (src, sink)}, ambient=50.0,
            h_eff=15.0, nonlinear=False, backend="cpu")
        exact_stack = {"In3.Cu": 0.0152 / FAB.OZ_COPPER_MM}
        one_oz_stack = {"In3.Cu": 1.0}
        exact = T2._synthetic_solve(stackup_oz=exact_stack, **common)
        one_oz = T2._synthetic_solve(stackup_oz=one_oz_stack, **common)
        expected = FAB.OZ_COPPER_MM / 0.0152
        self.assertAlmostEqual(exact[1] / one_oz[1], expected, places=8)
        self.assertGreater(float(exact[0].max()), float(one_oz[0].max()))


if __name__ == "__main__":
    unittest.main()
