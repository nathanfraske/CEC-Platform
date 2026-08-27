"""Teeth for the board-class power-layer policy (owner ruling 2026-07-25).

Two properties matter and both are asserted in BOTH directions:

  1. UNSET is byte-identical to the historical In2-first behaviour -- every board
     that does not opt in keeps exactly the layer bias it had, so this ruling
     cannot silently move the 24-pin (whose second inner IS a power-routing
     layer) or any cable board.
  2. When a board opts in, the named order actually drives BOTH decision sites --
     the corridor cost bias and the region realization order -- and the demoted
     layer is reported as an exception rather than used silently.
"""

import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_pour_plan as pp                                # noqa: E402


class PowerLayerPolicyTest(unittest.TestCase):
    def setUp(self):
        self._prev = os.environ.get("CEC_POWER_POUR_LAYERS")
        os.environ.pop("CEC_POWER_POUR_LAYERS", None)

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("CEC_POWER_POUR_LAYERS", None)
        else:
            os.environ["CEC_POWER_POUR_LAYERS"] = self._prev

    # -- 1. unset == historical behaviour ---------------------------------
    def test_unset_keeps_in2_first(self):
        self.assertEqual(pp.power_layer_order(), ("In2.Cu", "B.Cu", "F.Cu"))
        self.assertEqual(pp.region_layer_order(), ("In2.Cu", "B.Cu"))

    def test_unset_cost_bias_matches_the_frozen_constant(self):
        """The historical LAYER_PREF numbers, exactly -- not merely the order."""
        self.assertEqual(pp.layer_pref(), pp.LAYER_PREF)

    def test_unset_reports_no_demoted_layer(self):
        self.assertEqual(pp.demoted_layers(), frozenset())

    # -- 2. opt-in drives both decision sites ------------------------------
    def test_hub_policy_puts_outers_first_and_in2_last(self):
        os.environ["CEC_POWER_POUR_LAYERS"] = "B.Cu,F.Cu,In2.Cu"
        self.assertEqual(pp.power_layer_order(), ("B.Cu", "F.Cu", "In2.Cu"))
        pref = pp.layer_pref()
        self.assertLess(pref["B.Cu"], pref["F.Cu"])
        self.assertLess(pref["F.Cu"], pref["In2.Cu"],
                        "In2 must be the LAST resort under the hub policy")
        # region realization must follow the same order, not the old In2/B pair
        self.assertEqual(pp.region_layer_order(), ("B.Cu", "F.Cu", "In2.Cu"))

    def test_demoted_layer_is_named_for_the_exception_report(self):
        os.environ["CEC_POWER_POUR_LAYERS"] = "B.Cu,F.Cu,In2.Cu"
        self.assertEqual(pp.demoted_layers(), frozenset({"In2.Cu"}))

    def test_every_layer_stays_costable(self):
        """A layer the policy omits must still have a cost (never a KeyError in
        the solver's hot path)."""
        os.environ["CEC_POWER_POUR_LAYERS"] = "B.Cu"
        pref = pp.layer_pref()
        for lay in pp.LAYERS_ALL:
            self.assertIn(lay, pref)
        self.assertLess(pref["B.Cu"], pref["In2.Cu"])
        self.assertLess(pref["B.Cu"], pref["F.Cu"])

    def test_garbage_policy_falls_back_to_the_default(self):
        os.environ["CEC_POWER_POUR_LAYERS"] = "Nonsense.Cu, ,Bogus"
        self.assertEqual(pp.power_layer_order(), ("In2.Cu", "B.Cu", "F.Cu"),
                         "an unusable policy must not strand the solver")

    def test_policy_is_read_live_not_cached_at_import(self):
        """The wave sets the env per grade; a cached-at-import order would apply
        one board's policy to the next board in the same process."""
        os.environ["CEC_POWER_POUR_LAYERS"] = "B.Cu,F.Cu,In2.Cu"
        self.assertEqual(pp.power_layer_order()[0], "B.Cu")
        os.environ.pop("CEC_POWER_POUR_LAYERS")
        self.assertEqual(pp.power_layer_order()[0], "In2.Cu")

    def test_parallel_bundle_requires_full_aggregate_capacity(self):
        ask = {"parallel_layers": ("B.Cu", "F.Cu"),
               "parallel_layer_fraction": 0.50}
        bundle = pp.parallel_layer_bundle(
            ask, 48.75, ("F.Cu", "In2.Cu", "B.Cu"))
        self.assertAlmostEqual(1.0, bundle["aggregate_capacity_fraction"])
        ask["parallel_layer_fraction"] = 0.49
        with self.assertRaises(ValueError):
            pp.parallel_layer_bundle(
                ask, 48.75, ("F.Cu", "In2.Cu", "B.Cu"))

    def test_geometry_basis_margin_is_not_reapplied(self):
        with mock.patch.object(pp, "req_width_mm", return_value=6.3) as width:
            result = pp.required_widths_from_geometry_basis(
                {"F.Cu": 24.375}, ("F.Cu",), object())
        self.assertEqual(result, {"F.Cu": 6.3})
        self.assertEqual(width.call_args.kwargs["margin"], 1.0)

    def test_compiler_and_planner_share_resolved_bundle_oracle(self):
        asks = [{"net": "/PWR", "parallel_layers": ("B.Cu", "F.Cu"),
                 "parallel_layer_fraction": 0.50,
                 "parallel_min_amps": 20.0}]
        board = mock.Mock()
        board.GetFileName.return_value = "generic-power-board.kicad_pcb"
        with mock.patch.object(
                pp._fab, "enabled_copper_layers",
                return_value=("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")), \
             mock.patch.object(pp, "_net_currents", return_value={}), \
             mock.patch.object(pp, "_design_current_amps",
                               return_value=48.75):
            result = pp.declared_parallel_bundles(board, asks)
        self.assertEqual(("B.Cu", "F.Cu"), result["/PWR"]["layers"])
        self.assertEqual(48.75, result["/PWR"]["design_current_A"])
        self.assertEqual(24.375, result["/PWR"]["per_layer_amps"])

    def test_bundle_oracle_honors_current_threshold(self):
        asks = [{"net": "/AUX", "parallel_layers": ("B.Cu", "F.Cu"),
                 "parallel_min_amps": 20.0}]
        with mock.patch.object(pp._fab, "enabled_copper_layers",
                               return_value=("F.Cu", "B.Cu")), \
             mock.patch.object(pp, "_net_currents", return_value={}), \
             mock.patch.object(pp, "_design_current_amps",
                               return_value=5.0):
            self.assertEqual({}, pp.declared_parallel_bundles(
                mock.Mock(), asks))


class PriorityPowerAskPolicyTest(unittest.TestCase):
    def test_per_net_parallel_contract_survives_ask_merge(self):
        import cec_current_topology
        import cec_synth_pipeline as csp

        pours = [{"net": "/PWR", "layer": "F.Cu",
                  "parallel_layers": ("B.Cu", "F.Cu"),
                  "parallel_layer_fraction": 0.50,
                  "parallel_min_amps": 20.0},
                 {"net": "/PWR", "layer": "B.Cu"}]
        with mock.patch.object(cec_current_topology,
                               "board_current_domains", return_value={}):
            asks, _domains = csp._priority_power_asks(
                mock.Mock(), pours, "generic.kicad_pcb")
        self.assertEqual(1, len(asks))
        self.assertEqual(("F.Cu", "B.Cu"), asks[0]["layers"])
        self.assertEqual(("B.Cu", "F.Cu"), asks[0]["parallel_layers"])
        self.assertEqual(0.50, asks[0]["parallel_layer_fraction"])

    def test_conflicting_parallel_contracts_fail_closed(self):
        import cec_synth_pipeline as csp

        pours = [{"net": "/PWR", "layer": "F.Cu",
                  "parallel_layer_fraction": 0.50},
                 {"net": "/PWR", "layer": "B.Cu",
                  "parallel_layer_fraction": 0.75}]
        with self.assertRaisesRegex(ValueError, "conflicting"):
            csp._priority_power_asks(mock.Mock(), pours, "generic.kicad_pcb")


class PlacementParallelReservationTest(unittest.TestCase):
    def test_string_board_path_reaches_current_contract_authority(self):
        import cec_slab_pour
        import cec_synth_pipeline as csp

        contract = {"amps": 39.0, "margin_included": False,
                    "geometry_margin": 1.25,
                    "source": "board_design_basis"}
        with mock.patch.object(cec_slab_pour, "_board_thermal_config",
                               return_value=({}, None, {}, None)), \
             mock.patch.object(csp, "spec_net_current_contract",
                               return_value=contract) as authority:
            amps, margins, _domains, chosen = (
                cec_slab_pour.resolve_pour_current_contracts(
                    "/tmp/pcie-8pin-2port.kicad_pcb",
                    [{"net": "/SENSEC1_LO"}]))

        authority.assert_called_once_with(
            "/tmp/pcie-8pin-2port.kicad_pcb", "/SENSEC1_LO")
        self.assertEqual(39.0, amps["/SENSEC1_LO"])
        self.assertEqual(1.25, margins["/SENSEC1_LO"])
        self.assertEqual(48.75, chosen["/SENSEC1_LO"]["effective_A"])

    def test_reservation_uses_margin_inclusive_per_layer_current_once(self):
        import cec_synth_pipeline as csp

        cfg = mock.Mock()
        cfg.pcb = "pcie-8pin-2port.kicad_pcb"
        cfg.board = "pcie-8pin-2port"
        cfg.params = {
            "stackup_profile": "jlcpcb_6l_pofv_high_current",
            "power_parallel_layers": ("B.Cu", "F.Cu"),
            "power_parallel_fraction": 0.50,
            "power_parallel_min_amps": 20.0,
        }
        chosen = {"/PWR": {"effective_A": 48.75}}
        with mock.patch(
                "cec_slab_pour.resolve_pour_current_contracts",
                return_value=({"/PWR": 39.0}, {"/PWR": 1.25}, {}, chosen)), \
             mock.patch("cec_slab_pour.req_width_mm",
                        side_effect=lambda amps, _layer, **kw: amps / 4.0) as width:
            rows = csp._parallel_power_placement_margins(cfg, ("/PWR",))

        self.assertAlmostEqual(24.375, rows["/PWR"]["per_layer_current_A"])
        self.assertAlmostEqual(6.09375, rows["/PWR"]["required_widths_mm"]["F.Cu"])
        self.assertAlmostEqual(6.09375 / 2.0 + 0.30,
                               rows["/PWR"]["margin_mm"])
        self.assertTrue(all(call.kwargs["margin"] == 1.0
                            for call in width.call_args_list))

    def test_unset_parallel_policy_preserves_historical_geometry(self):
        import cec_synth_pipeline as csp

        cfg = mock.Mock()
        cfg.params = {}
        self.assertEqual({}, csp._parallel_power_placement_margins(
            cfg, ("/PWR",)))

    def test_pour_boxes_expand_only_the_declared_net(self):
        import cec_synth_pipeline as csp

        plan = mock.Mock()
        plan.evac_boxes.return_value = [
            ("/PWR", 10.0, 20.0, 30.0, 40.0),
            ("/AUX", 1.0, 2.0, 3.0, 4.0),
        ]
        with mock.patch("cec_pourplan.PourPlan.from_placement",
                        return_value=plan):
            boxes = csp._pour_boxes_unified(
                {}, mock.Mock(), {}, 100.0, 100.0,
                margin_by_net={"/PWR": {"margin_mm": 3.5}})
        self.assertEqual(("/PWR", 7.5, 22.5, 27.5, 42.5), boxes[0])
        self.assertEqual(("/AUX", 1.0, 2.0, 3.0, 4.0), boxes[1])

    def test_owning_pass_uses_same_parallel_power_boxes_as_evac(self):
        import cec_synth_pipeline as csp

        cfg = mock.Mock()
        cfg.params = {"pour_asks": [{"net": "/HI"}]}
        expected_margins = {"/HI": {"margin_mm": 3.5}}
        expected_boxes = [("/HI", 1.0, 9.0, 2.0, 8.0)]
        topo = [{"hi": "/HI", "lo": "/LO"}]
        with mock.patch.object(
                csp, "_parallel_power_placement_margins",
                return_value=expected_margins) as margins, \
             mock.patch.object(
                 csp, "_pour_boxes_unified",
                 return_value=expected_boxes) as boxes:
            actual_boxes, actual_margins = \
                csp._parallel_power_placement_boxes(
                    cfg, topo, {"U1": (1, 2, 0)}, "netlist", {}, 10, 10)

        margins.assert_called_once_with(cfg, ("/HI", "/LO"))
        boxes.assert_called_once_with(
            {"U1": (1, 2, 0)}, "netlist", {}, 10, 10,
            asks=({"net": "/HI"},), margin_by_net=expected_margins)
        self.assertEqual(expected_boxes, actual_boxes)
        self.assertEqual(expected_margins, actual_margins)


if __name__ == "__main__":
    unittest.main()


class SpecNetCurrentTest(unittest.TestCase):
    """Design-basis currents come from the spec, not from substring defaults
    (owner 2026-07-26: "check the actual design spec and plan for worst case
    not just pulling some random number")."""

    def setUp(self):
        import cec_synth_pipeline as csp
        self.csp = csp

    def test_atx_rails_match_the_ratified_joint_counts(self):
        """6A/circuit x circuits, cross-checked against the 2026-07-06 joints
        (TE 63969-1, 18.32A each): 12V x1, 5V x2, 3V3 x2, 5VSB x1."""
        f = self.csp.spec_net_current
        # owner ruling 2026-07-26: "the most we're going to see is like 20A on
        # 3v3 and 5V" -- the real ceiling, not the theoretical per-pin bar
        self.assertEqual(f("atx-24pin-rev3", "/SENSE3V3_HI"), 20.0)
        self.assertEqual(f("atx-24pin-rev3", "/SENSE5V_LO"), 20.0)
        self.assertEqual(f("atx-24pin-rev3", "/SENSE12V_HI"), 12.0)
        for net, joints in (("/SENSE3V3_HI", 2), ("/SENSE5V_HI", 2), ("/SENSE12V_HI", 1)):
            amps = f("atx-24pin-rev3", net)
            self.assertLessEqual(amps * 1.25, joints * 18.32 + 0.01,
                                 f"{net}: {amps}A at 125% exceeds its {joints} ratified joint(s)")

    def test_logic_rail_routes_to_component_budget_not_source_capacity(self):
        """Regulator capacity is checked separately from downstream loading."""
        import cec_power_budget

        f = self.csp.spec_net_current
        expected = (cec_power_budget.budget(
            "atx-24pin-rev3")["required_mA"] / 1000.0)
        self.assertAlmostEqual(f("atx-24pin-rev3", "+3V3"), expected)
        self.assertNotEqual(f("atx-24pin-rev3", "+3V3"),
                            f("atx-24pin-rev3", "/SENSE3V3_HI"))

    def test_current_beta_component_budgets_include_margin_once(self):
        import cec_power_budget

        f = self.csp.spec_net_current
        for board in ("12vhpwr-standard", "hub-standard-rev2"):
            expected = cec_power_budget.budget(board)["required_mA"] / 1000.0
            self.assertAlmostEqual(f(board, "+3V3"), expected)
            contract = self.csp.spec_net_current_contract(board, "+3V3")
            self.assertTrue(contract["margin_included"])
            self.assertEqual(contract["geometry_margin"], 1.0)
            self.assertEqual(contract["source"], "component_power_budget")

    def test_committed_candidate_filename_resolves_board_table(self):
        import cec_power_budget

        self.assertAlmostEqual(self.csp.spec_net_current(
            "beta/atx-24pin-rev3/candidate/atx-24pin-rev3-candidate.kicad_pcb",
            "+3V3"), cec_power_budget.budget(
                "atx-24pin-rev3")["required_mA"] / 1000.0)

    def test_cable_boards_keep_the_owner_per_cable_basis(self):
        f = self.csp.spec_net_current
        self.assertEqual(f("eps-8pin", "/SENSEC1_HI"), 52.0)      # ~13A/pin x4
        self.assertEqual(f("pcie-8pin-2port", "/SENSEC2_LO"), 39.0)  # 3x12V pins
        self.assertEqual(f("12vhpwr-standard", "/SENSEP4_HI"), 9.2)  # per-pin rating

    def test_untabled_board_falls_through(self):
        self.assertIsNone(self.csp.spec_net_current("hub-standard-rev2", "/SENSE3V3_HI"))
        self.assertIsNone(self.csp.spec_net_current("atx-24pin-rev3", "/CAN_H"))


class SpecGndCurrentTest(unittest.TestCase):
    """GND return is DERIVED from the board's own rails, not a global default."""

    def setUp(self):
        import cec_synth_pipeline as csp
        self.csp = csp

    def _nets(self, *rails):
        out = ["GND"]
        for r in rails:
            out += [r + "_HI", r + "_LO"]
        return out

    def test_24pin_sums_its_distinct_rails(self):
        g = self.csp.spec_gnd_current("atx-24pin-rev3",
                                      self._nets("/SENSE3V3", "/SENSE5V",
                                                 "/SENSE12V", "/SENSE5VSB"))
        self.assertEqual(g, 55.0, "20 + 20 + 12 + 3, each rail counted once")

    def test_hi_and_lo_are_one_rail(self):
        """They are in series through the shunt -- counting both doubles it."""
        g = self.csp.spec_gnd_current("atx-24pin-rev3", ["/SENSE12V_HI", "/SENSE12V_LO"])
        self.assertEqual(g, 12.0)

    def test_cable_boards_scale_with_cable_count(self):
        c = self.csp
        self.assertEqual(c.spec_gnd_current("eps-8pin", self._nets("/SENSEC1", "/SENSEC2")), 104.0)
        self.assertEqual(c.spec_gnd_current("pcie-8pin-3port",
                                            self._nets("/SENSEC1", "/SENSEC2", "/SENSEC3")), 117.0)

    def test_12vhpwr_matches_its_power_budget(self):
        g = self.csp.spec_gnd_current("12vhpwr-standard",
                                      self._nets(*["/SENSEP%d" % i for i in range(1, 7)]))
        self.assertAlmostEqual(g, 55.2, places=1)
        self.assertGreater(g, 600.0 / 12.0, "must cover 600W/12V = 50A sustained")

    def test_hub_does_not_double_count_one_muxed_rail(self):
        """+5VSB / 5VSB_RAW / PSU_5V / MAIN_5V / +5V_HOLD are stages of ONE
        supply behind the TPS2121 cascade -- only one source is ever live."""
        g = self.csp.spec_gnd_current("hub-standard-rev2",
                                      ["+5VSB", "/5VSB_RAW", "/PSU_5V", "/MAIN_5V",
                                       "/+5V_HOLD", "/VCC_P1", "GND"])
        self.assertEqual(g, 2.5)

    def test_untabled_board_returns_none(self):
        self.assertIsNone(self.csp.spec_gnd_current("argb-standard", ["GND"]))
