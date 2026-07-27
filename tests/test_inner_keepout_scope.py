"""The inner-layer pour reservation must not steal a ROUTING layer.

Reserving inner pour regions from the router is correct on a POUR-FIRST board,
where the pour is really there when the router runs. It is wrong where the
inner floods are post-route ADDITIVE: the hub's power rung depends on In2 being
EMPTY at route time -- "a true third routing layer" (owner 2026-07-23) -- and
reserving it moved the hub from 32 unconnected to a 46-60 band over ten seeds.
"""
import os
import unittest


class InnerKeepoutScopeTest(unittest.TestCase):
    """The discriminator is `inner_gnd_fill`: a board declaring it is saying
    that inner layer is for routing and gets filled afterwards."""

    def setUp(self):
        self._prev = os.environ.get("CEC_INNER_GND_FILL")
        os.environ.pop("CEC_INNER_GND_FILL", None)

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("CEC_INNER_GND_FILL", None)
        else:
            os.environ["CEC_INNER_GND_FILL"] = self._prev

    @staticmethod
    def _reserves():
        """Mirror of the guard in cec_synth_pipeline._oracle_hints_pours."""
        inner_is_routing = bool(os.environ.get("CEC_INNER_GND_FILL"))
        return (os.environ.get("CEC_INNER_POUR_KEEPOUT", "1") == "1"
                and not inner_is_routing)

    def test_pourfirst_board_still_reserves_inner_regions(self):
        self.assertTrue(self._reserves(),
                        "the 24-pin's In2 diagonals came from unreserved inner pours")

    def test_a_board_with_an_inner_routing_layer_does_not(self):
        os.environ["CEC_INNER_GND_FILL"] = "In2.Cu"
        self.assertFalse(self._reserves(),
                         "the hub's third routing layer must stay free at route time")

    def test_the_escape_hatch_still_works(self):
        os.environ["CEC_INNER_POUR_KEEPOUT"] = "0"
        try:
            self.assertFalse(self._reserves())
        finally:
            os.environ.pop("CEC_INNER_POUR_KEEPOUT", None)


if __name__ == "__main__":
    unittest.main()
