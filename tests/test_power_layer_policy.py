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

    def test_logic_rail_is_bounded_by_its_source_not_the_bus(self):
        """+3V3 is LDO-fed (LP5907, 250mA max) -- it must NOT inherit the rail."""
        f = self.csp.spec_net_current
        self.assertEqual(f("atx-24pin-rev3", "+3V3"), 0.25)
        self.assertNotEqual(f("atx-24pin-rev3", "+3V3"),
                            f("atx-24pin-rev3", "/SENSE3V3_HI"))

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
