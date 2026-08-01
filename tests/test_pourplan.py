#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# POUR LEVER stage-4 REBUILD verb (docs/pour-lever-scoping-2026-07-08.md §3.2/§4, owner RATIFIED
# 2026-07-09). PourPlan.rebuild(op, net=...) is the router's actuation surface: an in-loop,
# SAME-net, geometry-only reshape (notch / shrink / relocate / drop_layer) of an auto-derived pour.
#
# TEETH:
#   * the four reshape ops mutate geometry (shrink/relocate/drop_layer/notch);
#   * the AUTONOMY LINE (ruling 1): add / drop / re-net a pour, reshape a net with no derived pour,
#     or touch a FROZEN spec -> EscalateToHuman with a named reason (never a silent proceed);
#   * the min-pour-cross-section HARD gate (ruling 2): a reshape that NECKS the rebuilt pour ->
#     PourCrossSectionRefused (a reshape can never thin copper to dodge the foreign-on-pour gate);
#   * byte-identity: the derivation (pour_polygons on eps, asks=()) is unchanged by the verb module.
#
# Pure-data verb tests need no pcbnew; the notch op + the eps byte-identity read do (skipUnless).

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_pourplan as P                                       # noqa: E402 (pure; lazy pcbnew)

EPS = os.path.join(ROOT, "beta", "eps-8pin-rev3", "eps-8pin-rev3.kicad_pcb")

try:
    import pcbnew                                              # noqa: F401
    HAVE_PCBNEW = True
except Exception:                                              # noqa: BLE001
    HAVE_PCBNEW = False


def _plan_2layer(net="/SENSEC1_HI"):
    """A hand-built 2-layer lane plan (F.Cu + B.Cu), 10x20mm boxes -> min cross 0.696mm^2."""
    poly = ((10, 10), (20, 10), (20, 30), (10, 30))            # shorter side 10mm
    return P.PourPlan(specs=[
        P.PourSpec(net=net, layers=("F.Cu",), shape="lane", polygon=poly),
        P.PourSpec(net=net, layers=("B.Cu",), shape="lane", polygon=poly),
    ])


def _plan_1layer(net="/SENSEC2_HI"):
    return P.PourPlan(specs=[
        P.PourSpec(net=net, layers=("F.Cu",), shape="lane",
                   polygon=((0, 0), (5, 0), (5, 10), (0, 10)))])


class ReshapeOps(unittest.TestCase):
    def test_shrink_pulls_an_edge_in(self):
        pl = _plan_2layer()
        before = pl._min_cross_mm2("/SENSEC1_HI")
        pl.rebuild("shrink", net="/SENSEC1_HI", edge="x1", mm=2.0)
        r = pl._specs_for("/SENSEC1_HI")[0].rect()
        self.assertAlmostEqual(r[1], 18.0)                     # x1 20 -> 18
        self.assertLess(pl._min_cross_mm2("/SENSEC1_HI"), before)

    def test_relocate_translates(self):
        pl = _plan_2layer()
        pl.rebuild("relocate", net="/SENSEC1_HI", dxy=(5, -3))
        r = pl._specs_for("/SENSEC1_HI")[0].rect()
        self.assertEqual((r[0], r[1], r[2], r[3]), (15, 25, 7, 27))

    def test_drop_layer_keeps_the_mirror(self):
        pl = _plan_2layer()
        pl.rebuild("drop_layer", net="/SENSEC1_HI", layer="F.Cu")
        layers = {s.layers[0] for s in pl._specs_for("/SENSEC1_HI")}
        self.assertEqual(layers, {"B.Cu"})

    def test_reshape_marks_router_ask_provenance(self):
        pl = _plan_2layer()
        pl.rebuild("shrink", net="/SENSEC1_HI", edge="y0", mm=1.0)
        self.assertTrue(all(s.provenance == "router_ask"
                            for s in pl._specs_for("/SENSEC1_HI")))

    @unittest.skipUnless(HAVE_PCBNEW, "notch reuses cec_fr (imports pcbnew)")
    def test_notch_opens_the_window(self):
        pl = _plan_2layer()
        pl.rebuild("notch", net="/SENSEC1_HI", at=(15, 20), gap_mm=8, vertical=True)
        r = pl._specs_for("/SENSEC1_HI")[0].rect()
        # box was y 10..30, centred-above shunt(20) -> bottom clamps up to 20-4=16 ... verify it moved
        self.assertNotEqual(r[2:], (10, 30))


class AutonomyLine(unittest.TestCase):
    def test_add_escalates(self):
        with self.assertRaises(P.EscalateToHuman) as cm:
            _plan_2layer().rebuild("add", net="/NEWRAIL")
        self.assertIn("ADDING a pour is a DESIGN change", str(cm.exception))

    def test_drop_escalates(self):
        with self.assertRaises(P.EscalateToHuman) as cm:
            _plan_2layer().rebuild("drop", net="/SENSEC1_HI")
        self.assertIn("DROPPING a required pour", str(cm.exception))

    def test_renet_escalates(self):
        with self.assertRaises(P.EscalateToHuman) as cm:
            _plan_2layer().rebuild("relocate", net="/SENSEC1_HI", dxy=(1, 1),
                                   new_net="/OTHER")
        self.assertIn("CHANGE a pour's net", str(cm.exception))

    def test_reshape_of_undrived_net_escalates(self):
        with self.assertRaises(P.EscalateToHuman) as cm:
            _plan_2layer().rebuild("shrink", net="/NOTHERE", edge="x1", mm=1)
        self.assertIn("no auto-derived pour exists", str(cm.exception))

    def test_frozen_spec_escalates(self):
        pl = _plan_2layer()
        for s in pl.specs:
            s.frozen = True
        with self.assertRaises(P.EscalateToHuman) as cm:
            pl.rebuild("shrink", net="/SENSEC1_HI", edge="x1", mm=1)
        self.assertIn("FROZEN", str(cm.exception))

    def test_drop_layer_leaving_no_pour_escalates(self):
        with self.assertRaises(P.EscalateToHuman) as cm:
            _plan_1layer().rebuild("drop_layer", net="/SENSEC2_HI", layer="F.Cu")
        self.assertIn("NO pour", str(cm.exception))

    def test_unknown_op_escalates(self):
        with self.assertRaises(P.EscalateToHuman):
            _plan_2layer().rebuild("teleport", net="/SENSEC1_HI")


class CrossSectionHardGate(unittest.TestCase):
    def test_necking_shrink_is_refused(self):
        pl = _plan_2layer()                                    # 10mm width -> 0.696 mm^2
        with self.assertRaises(P.PourCrossSectionRefused) as cm:
            pl.rebuild("shrink", net="/SENSEC1_HI", edge="x1", mm=9.5,
                       min_cross_mm2=0.06)                      # necks to ~0.0007 << 0.06
        self.assertIn("min-pour-cross-section", str(cm.exception))

    def test_overshrink_necks_not_grows(self):
        # a shrink larger than the box must NECK (clamp to a sliver), never flip+grow past the gate
        pl = _plan_2layer()
        with self.assertRaises(P.PourCrossSectionRefused):
            pl.rebuild("shrink", net="/SENSEC1_HI", edge="x1", mm=100.0, min_cross_mm2=0.06)

    def test_modest_shrink_passes(self):
        pl = _plan_2layer()
        pl.rebuild("shrink", net="/SENSEC1_HI", edge="x1", mm=1.0, min_cross_mm2=0.06)
        self.assertGreaterEqual(pl._min_cross_mm2("/SENSEC1_HI"), 0.06)

    def test_refusal_is_atomic(self):
        # a REFUSED reshape must leave the plan UNCHANGED (not half-necked) -- rollback
        pl = _plan_2layer()
        before = [s.rect() for s in pl.specs]
        with self.assertRaises(P.PourCrossSectionRefused):
            pl.rebuild("shrink", net="/SENSEC1_HI", edge="x1", mm=9.5, min_cross_mm2=0.06)
        self.assertEqual([s.rect() for s in pl.specs], before)
        self.assertTrue(all(s.provenance == "derived" for s in pl.specs))

    def test_refused_drop_layer_rolls_back_the_removal(self):
        pl = _plan_2layer()
        n = len(pl.specs)
        # drop_layer that necks (force a tiny floor so the remaining single layer "necks")
        with self.assertRaises(P.PourCrossSectionRefused):
            pl.rebuild("drop_layer", net="/SENSEC1_HI", layer="F.Cu", min_cross_mm2=1e9)
        self.assertEqual(len(pl.specs), n)               # the removed spec is restored


@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(EPS), "eps-8pin-rev3 + pcbnew required")
class ByteIdentity(unittest.TestCase):
    def test_derivation_unchanged_by_the_verb_module(self):
        # the stage-4 module adds the rebuild verb but must not perturb the DEFAULT derivation:
        # pour_polygons(asks=()) still equals cec_fr.derive_power_pours byte-for-byte on eps.
        import cec_fr
        legacy = cec_fr.derive_power_pours(EPS)
        plan = P.PourPlan.from_board(EPS).pour_polygons()
        self.assertEqual(plan, legacy)


# ============================================================ PER-CABLE OUTPUT UNIFORMITY
# DERIVE-ONCE-STAMP-N (owner ruling 2026-07-09): a per-cable family's pours are derived ONCE (the
# tightest position) and STAMPED to every position AS ITS OWN TAB-BLOCK SHAPE, so the output pour
# SHAPE is identical across positions while each pour stays laid over its own tabs. Pure-data tests.
def _fam3(w1=20.0, w2=30.0, w3=30.0, h=40.0):
    """3-position LO family; position 1 the SMALLEST (master); each at its own min-corner."""
    def box(x0, w):
        return ((x0, 0.0), (x0 + w, 0.0), (x0 + w, h), (x0, h))
    return P.PourPlan(specs=[P.PourSpec(net="/SENSEC1_LO", polygon=box(0.0, w1)),
                             P.PourSpec(net="/SENSEC2_LO", polygon=box(100.0, w2)),
                             P.PourSpec(net="/SENSEC3_LO", polygon=box(200.0, w3))])


class PerCableStampN(unittest.TestCase):
    def test_no_family_is_a_noop(self):
        # a single-position "family" (one SENSEC index) has no >=2-position role -> byte-identical
        pl = P.PourPlan(specs=[P.PourSpec(net="/SENSEC1_LO",
                                          polygon=((0, 0), (10, 0), (10, 20), (0, 20)))])
        before = [s.rect() for s in pl.specs]
        pl.enforce_uniformity()
        self.assertEqual([s.rect() for s in pl.specs], before)

    def test_master_is_the_smallest_and_shape_stamps_per_tab(self):
        pl = _fam3(w1=20.0, w2=30.0, w3=30.0)     # master = position 1 (20 wide, least area)
        pl.enforce_uniformity()
        widths = {s.net: round(s.rect()[1] - s.rect()[0], 3) for s in pl.specs}
        self.assertEqual(set(widths.values()), {20.0})     # ALL positions carry the master's 20mm width
        # anchored per tab: each pour keeps its OWN min-corner (0 / 100 / 200), not a regularised pitch
        x0s = {s.net: round(s.rect()[0], 3) for s in pl.specs}
        self.assertEqual(x0s, {"/SENSEC1_LO": 0.0, "/SENSEC2_LO": 100.0, "/SENSEC3_LO": 200.0})
        self.assertTrue(all(s.provenance == "uniform_stamp" for s in pl.specs))

    def test_shrink_to_legal_family_wide(self):
        # foreign copper at ONE position -> the master shrinks so ALL positions shrink IDENTICALLY
        pl = _fam3(w1=20.0, w2=20.0, w3=20.0)
        pl.enforce_uniformity(foreign_by_pos={2: [(100.0, 102.9, 0.0, 40.0)]}, min_cross_mm2=0.06)
        widths = {round(s.rect()[1] - s.rect()[0], 3) for s in pl.specs}
        self.assertEqual(len(widths), 1)                   # identical shrunk width everywhere
        self.assertLess(next(iter(widths)), 20.0)          # actually shrank
        p2 = next(s for s in pl.specs if s.net == "/SENSEC2_LO")
        self.assertGreaterEqual(p2.rect()[0], 102.9 - 1e-9)  # position 2 cleared its foreign

    def test_shrink_below_floor_refuses(self):
        pl = _fam3(w1=20.0, w2=20.0, w3=20.0)
        with self.assertRaises(P.PourUniformityRefused) as cm:
            pl.enforce_uniformity(foreign_by_pos={2: [(100.0, 119.0, 0.0, 40.0)]}, min_cross_mm2=1.0)
        self.assertIn("min-pour-cross-section", str(cm.exception))


class UniformityPreservingRebuild(unittest.TestCase):
    def test_shrink_applies_to_ALL_positions(self):
        pl = _fam3(w1=20.0, w2=20.0, w3=20.0)
        pl.rebuild("shrink", net="/SENSEC2_LO", edge="x1", mm=2.0)
        widths = {round(s.rect()[1] - s.rect()[0], 3) for s in pl.specs}
        self.assertEqual(widths, {18.0})                   # every position shrank identically

    def test_absolute_arg_ops_refuse(self):
        for op, kw in (("notch", dict(at=(110, 20), gap_mm=8)),
                       ("relocate", dict(region=(100, 0, 120, 40)))):
            with self.assertRaises(P.PourUniformityRefused):
                _fam3(20, 20, 20).rebuild(op, net="/SENSEC2_LO", **kw)

    def test_single_position_still_takes_the_old_path(self):
        # not a family (one position) -> the plain single-net reshape, no all-positions expansion
        pl = P.PourPlan(specs=[P.PourSpec(net="/SENSEC1_LO",
                                          polygon=((0, 0), (20, 0), (20, 40), (0, 40)))])
        pl.rebuild("shrink", net="/SENSEC1_LO", edge="x1", mm=2.0)
        self.assertAlmostEqual(pl.specs[0].rect()[1], 18.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
