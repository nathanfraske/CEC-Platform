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
