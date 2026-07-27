"""Teeth for the single-owner redundant-layer pass (owner 2026-07-26:
"it's *already gathered and good on the top layer* why is it *also on the
bottom layer*?").

The pass must delete a functional layer COPY while never severing a bridge and
never trading away copper current genuinely needs.
"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import cec_slab_pour as sp                                  # noqa: E402

def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

def z(name, net, layer, poly):
    return {"name": name, "net": net, "layer": layer, "polygon": poly}


class RedundantLayerTest(unittest.TestCase):
    def test_exact_copy_on_another_layer_is_dropped(self):
        """The measured 24-pin defect: same pads, same barrels, other layer."""
        a = z("manifold:J3:/N", "/N", "F.Cu", rect(0, 0, 20, 10))
        b = z("manifold:J3:/N", "/N", "In2.Cu", rect(0, 0, 20, 10))
        pads = [("/N", 2.0, 2.0, None), ("/N", 18.0, 8.0, None)]
        kept, dropped = sp.drop_redundant_layers([a, b], pads=pads, vias=[])
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["layer"], "F.Cu", "the pad-bearing layer owns")
        self.assertIn("redundant layer", dropped[0][1])

    def test_a_zone_adding_a_new_connection_survives(self):
        """Not a copy -- it reaches a terminal nothing else does."""
        a = z("l1", "/N", "F.Cu", rect(0, 0, 10, 10))
        b = z("l2", "/N", "In2.Cu", rect(20, 0, 30, 10))
        pads = [("/N", 2.0, 2.0, None), ("/N", 25.0, 5.0, None)]
        kept, _ = sp.drop_redundant_layers([a, b], pads=pads, vias=[])
        self.assertEqual(len(kept), 2,
                         "neither reaches the other's terminal -- both real")

    def test_smd_pad_is_not_owned_by_a_layer_that_only_passes_over_it(self):
        """An inner zone crossing an F.Cu SMD pad connects NOTHING there, so
        it must not win ownership and evict the zone that does touch it."""
        f = z("f", "/N", "F.Cu", rect(0, 0, 10, 10))
        i = z("i", "/N", "In2.Cu", rect(0, 0, 30, 10))
        pads = [("/N", 2.0, 2.0, "F.Cu"), ("/N", 25.0, 5.0, "F.Cu")]
        kept, _ = sp.drop_redundant_layers([f, i], pads=pads, vias=[])
        self.assertIn("f", [k["name"] for k in kept],
                      "the zone actually touching the SMD pad must survive")

    def test_bridge_is_never_severed_by_subset_of_the_union(self):
        """Two disjoint zones each hold one end; the bridge touching both is
        NOT redundant even though every point it covers appears elsewhere."""
        left = z("L", "/N", "F.Cu", rect(0, 0, 10, 10))
        right = z("R", "/N", "F.Cu", rect(30, 0, 40, 10))
        bridge = z("B", "/N", "In2.Cu", rect(0, 0, 40, 10))
        pads = [("/N", 5.0, 5.0, None), ("/N", 35.0, 5.0, None)]
        kept, _ = sp.drop_redundant_layers([left, right, bridge], pads=pads, vias=[])
        self.assertIn("B", [k["name"] for k in kept],
                      "subset-of-the-union would have cut the only bridge")

    def test_parallel_ampacity_copper_survives(self):
        """Identical connection sets, but the current needs both layers."""
        a = z("a", "/BIG", "In2.Cu", rect(0, 0, 6, 40))
        b = z("b", "/BIG", "In4.Cu", rect(0, 0, 6, 40))
        pads = [("/BIG", 3.0, 2.0, None), ("/BIG", 3.0, 38.0, None)]
        kept, _ = sp.drop_redundant_layers([a, b], pads=pads, vias=[],
                                           net_amps={"/BIG": 40.0})
        self.assertEqual(len(kept), 2, "ampacity floor must hold the copy")

    def test_same_copper_on_an_outer_layer_needs_no_second(self):
        """External k is ~2x internal -- the 20A/3V3 case."""
        self.assertEqual(sp.layers_for_current(20.0, 20.0, inner=False), 1)
        self.assertGreater(sp.layers_for_current(20.0, 20.0, inner=True), 1)

    def test_untabled_net_defaults_to_one_layer(self):
        a = z("a", "/X", "F.Cu", rect(0, 0, 20, 10))
        b = z("b", "/X", "B.Cu", rect(0, 0, 20, 10))
        kept, _ = sp.drop_redundant_layers([a, b], pads=[("/X", 5.0, 5.0, None)], vias=[])
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main()


class ParallelBridgeTest(unittest.TestCase):
    """Two lanes doing one job: neither is a subset, both must not survive."""

    def test_duplicate_bridge_layer_is_dropped_by_connectivity_proof(self):
        # Two F islands hold the pads; TWO inner lanes each bridge them, and
        # each covers a barrel the other misses -- so neither is a subset of
        # the other and only a connectivity proof can drop one. This is the
        # measured /SENSE3V3_HI shape (In2 1564mm2 + B.Cu 618mm2).
        l = z("L", "/N", "F.Cu", rect(0, 0, 10, 6))
        r = z("R", "/N", "F.Cu", rect(30, 0, 40, 6))
        a = z("a", "/N", "In2.Cu", rect(0, 0, 40, 6))
        b = z("b", "/N", "B.Cu", rect(0, 2, 40, 8))
        pads = [("/N", 2.0, 3.0, "F.Cu"), ("/N", 38.0, 3.0, "F.Cu")]
        vias = [{"net": "/N", "x_mm": 5.0, "y_mm": 3.0},
                {"net": "/N", "x_mm": 35.0, "y_mm": 3.0},
                {"net": "/N", "x_mm": 15.0, "y_mm": 1.0},     # in a only
                {"net": "/N", "x_mm": 15.0, "y_mm": 7.0}]     # in b only
        kept, dropped = sp.drop_redundant_layers([l, r, a, b], pads=pads, vias=vias)
        self.assertTrue(any("parallel bridge" in w for _d, w in dropped),
                        "the duplicate lane needs the connectivity proof")
        self.assertEqual(len([k for k in kept if k["name"] in ("a", "b")]), 1,
                         "exactly one bridging lane should remain")

    def test_a_lane_that_is_the_only_path_is_never_dropped(self):
        """Two F islands joined ONLY through the inner lane's barrels."""
        l = z("L", "/N", "F.Cu", rect(0, 0, 10, 6))
        r = z("R", "/N", "F.Cu", rect(30, 0, 40, 6))
        mid = z("M", "/N", "In2.Cu", rect(0, 0, 40, 6))
        pads = [("/N", 2.0, 3.0, "F.Cu"), ("/N", 38.0, 3.0, "F.Cu")]
        vias = [{"net": "/N", "x_mm": 5.0, "y_mm": 3.0},
                {"net": "/N", "x_mm": 35.0, "y_mm": 3.0}]
        kept, _ = sp.drop_redundant_layers([l, r, mid], pads=pads, vias=vias)
        self.assertIn("M", [k["name"] for k in kept],
                      "removing the only bridge would strand a terminal")

    def test_ampacity_floor_outranks_tidiness(self):
        f = z("f", "/N", "F.Cu", rect(0, 0, 40, 4))
        a = z("a", "/N", "In2.Cu", rect(0, 0, 40, 4))
        pads = [("/N", 2.0, 2.0, "F.Cu"), ("/N", 38.0, 2.0, "F.Cu")]
        vias = [{"net": "/N", "x_mm": 5.0, "y_mm": 2.0}]
        kept, _ = sp.drop_redundant_layers([f, a], pads=pads, vias=vias,
                                           min_layers={"/N": 2})
        self.assertEqual(len(kept), 2)

    def test_a_broken_net_is_left_alone(self):
        """Never tidy a net whose connectivity proof does not already hold."""
        a = z("a", "/N", "F.Cu", rect(0, 0, 5, 5))
        b = z("b", "/N", "B.Cu", rect(30, 0, 35, 5))
        pads = [("/N", 2.0, 2.0, "F.Cu"), ("/N", 32.0, 2.0, "B.Cu")]
        kept, _ = sp.drop_redundant_layers([a, b], pads=pads, vias=[])
        self.assertEqual(len(kept), 2)


class OwnershipOrderTest(unittest.TestCase):
    """WHICH copy dies. Measured defect: the pass dropped the F.Cu manifold
    holding J3's THT pads and kept an inner lane -- legal through a barrel,
    wrong on ampacity and wrong per the owner ("already good on the top")."""

    def test_the_pad_bearing_outer_layer_wins_ownership(self):
        outer = z("manifold:J3:/N", "/N", "F.Cu", rect(0, 0, 40, 8))
        inner = z("pourfirst:/N", "/N", "In2.Cu", rect(0, 0, 40, 8))
        pads = [("/N", 2.0, 4.0, None), ("/N", 38.0, 4.0, None)]   # THT
        vias = [{"net": "/N", "x_mm": 20.0, "y_mm": 4.0}]
        kept, _ = sp.drop_redundant_layers([outer, inner], pads=pads, vias=vias)
        self.assertEqual([k["layer"] for k in kept], ["F.Cu"])

    def test_outer_beats_inner_even_when_inner_is_larger(self):
        outer = z("o", "/N", "F.Cu", rect(0, 0, 20, 8))
        inner = z("i", "/N", "In2.Cu", rect(0, 0, 40, 8))
        pads = [("/N", 2.0, 4.0, None), ("/N", 18.0, 4.0, None)]
        kept, _ = sp.drop_redundant_layers([outer, inner], pads=pads, vias=[])
        self.assertEqual([k["layer"] for k in kept], ["F.Cu"])
