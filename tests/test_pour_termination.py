"""Teeth for the pour-termination ruling (owner 2026-07-24, implemented 2026-07-25).

"Force copper stops at the shunt pad, the gap belongs to the taps." The ruling sat
in the design doc for a day with no code behind it, and every force pour ran
straight through the tap gap (measured: 8.16 mm2 of /SENSEC1_HI inside RS1's gap on
the eps winner). These tests pin the geometry half -- the clip itself -- so it
cannot silently become prose again.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fr                                             # noqa: E402


def area(poly):
    """Shoelace area of a simple polygon."""
    a = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2.0


class SubtractRectTest(unittest.TestCase):
    """_subtract_rect is the clip primitive; it must remove the gap and nothing else."""

    RECT = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]

    def test_no_overlap_returns_the_polygon_untouched(self):
        out = cec_fr._subtract_rect(self.RECT, (20.0, 20.0, 25.0, 25.0))
        self.assertEqual(out, [(self.RECT, [])],
                         "a pour clear of every gap must pass through byte-identical")

    def test_gap_area_is_removed(self):
        out = cec_fr._subtract_rect(self.RECT, (4.0, 0.0, 6.0, 10.0))
        self.assertGreater(len(out), 0)
        total = sum(area(e) - sum(area(h) for h in hs) for e, hs in out)
        self.assertAlmostEqual(total, 100.0 - 20.0, delta=0.01,
                               msg="the 2x10 gap band must be gone from the pour")

    def test_no_copper_survives_inside_the_gap(self):
        """The property that matters: no COPPER in the gap.

        Both representations must satisfy it -- the shapely path excises an
        interior ring (the gap sits inside the pour), the host fallback splits
        into slabs. Checking only the exterior would pass the very bug this
        suite exists for: keeping the exterior and dropping the hole restored
        the pour exactly and still reported a successful clip.
        """
        for gap in ((4.0, 0.0, 6.0, 10.0),        # spans the pour top-to-bottom
                    (4.0, 4.0, 6.0, 6.0)):        # strictly interior -> a hole
            for e, hs in cec_fr._subtract_rect(self.RECT, gap):
                xs = [q[0] for q in e]
                ys = [q[1] for q in e]
                ext_covers = not (max(xs) <= gap[0] or min(xs) >= gap[2]
                                  or max(ys) <= gap[1] or min(ys) >= gap[3])
                if not ext_covers:
                    continue                       # slab form: already clear
                hole_covers = any(
                    min(q[0] for q in h) <= gap[0] + 1e-6
                    and max(q[0] for q in h) >= gap[2] - 1e-6
                    and min(q[1] for q in h) <= gap[1] + 1e-6
                    and max(q[1] for q in h) >= gap[3] - 1e-6
                    for h in hs)
                self.assertTrue(hole_covers,
                                f"gap {gap} is inside survivor {e} with no hole "
                                f"excising it (holes={hs}) -- copper still in the tap gap")

    def test_pour_entirely_inside_the_gap_is_dropped(self):
        out = cec_fr._subtract_rect([(4.5, 4.5), (5.5, 4.5), (5.5, 5.5), (4.5, 5.5)],
                                    (4.0, 4.0, 6.0, 6.0))
        self.assertEqual(out, [], "a pour that is ALL gap must produce no copper")

    def test_chained_clips_never_leave_a_hole_outside_the_outline(self):
        """The bug that made every force pour fill as a scrap.

        Clip 1 (the tap gap) sits INSIDE the pour -> the result carries a hole.
        Clip 2 (terminate-at-the-pad) then removes the whole region that hole
        lived in. Subtracting only the exterior and carrying the hole across left
        a zone whose hole lay outside its own outline -- malformed geometry that
        KiCad filled with 16.6mm2 of a 170mm2 pour. Every surviving hole must lie
        inside its own exterior.
        """
        gap = (4.0, 4.0, 6.0, 6.0)          # interior -> makes a hole
        step1 = cec_fr._subtract_rect(self.RECT, gap)
        self.assertTrue(any(hs for _e, hs in step1), "clip 1 should create a hole")
        halfplane = (-1.0, 3.0, 11.0, 11.0)  # removes everything at/below y=3
        for ext, holes in step1:
            for ext2, holes2 in cec_fr._subtract_rect(ext, halfplane, holes):
                ex0 = min(q[0] for q in ext2); ex1 = max(q[0] for q in ext2)
                ey0 = min(q[1] for q in ext2); ey1 = max(q[1] for q in ext2)
                for h in holes2:
                    hx0 = min(q[0] for q in h); hx1 = max(q[0] for q in h)
                    hy0 = min(q[1] for q in h); hy1 = max(q[1] for q in h)
                    self.assertTrue(ex0 <= hx0 and hx1 <= ex1 and ey0 <= hy0 and hy1 <= ey1,
                                    f"hole {h} lies outside its exterior "
                                    f"({ex0},{ey0})-({ex1},{ey1}) -- the filler will scrap this zone")

    def test_gap_through_the_middle_splits_the_pour(self):
        out = cec_fr._subtract_rect(self.RECT, (4.0, -1.0, 6.0, 11.0))
        self.assertGreaterEqual(len(out), 2,
                                "a gap crossing the whole pour must leave both sides")


class ShuntGapGeometryTest(unittest.TestCase):
    """The gap derivation must be layer-scoped: an inner plane under an SMD shunt
    is correct copper and must never be clipped."""

    class _Pad:
        def __init__(self, box, layers):
            self._b, self._l = box, layers

        def GetBoundingBox(self):
            class B:
                def __init__(s, b): s.b = b
                def GetLeft(s): return int(s.b[0] * 1e6)
                def GetTop(s): return int(s.b[1] * 1e6)
                def GetRight(s): return int(s.b[2] * 1e6)
                def GetBottom(s): return int(s.b[3] * 1e6)
            return B(self._b)

        def GetLayerSet(self):
            outer = self._l

            class LS:
                def CuStack(s): return outer
            return LS()

    def _board(self, pads, ref="RS1"):
        class FP:
            def __init__(s, pads, ref): s._p, s._r = pads, ref
            def GetReference(s): return s._r
            def Pads(s): return s._p

        class BD:
            def GetFootprints(s): return [FP(pads, ref)]
        return BD()

    def setUp(self):
        # The stub pads carry layer NAMES; the real code resolves layer IDs through
        # pcbnew.LayerName. Pass it through for the duration of these tests so the
        # geometry is what is under test, not the SWIG enum.
        self._ln = cec_fr.pcbnew.LayerName
        cec_fr.pcbnew.LayerName = lambda l: l

    def tearDown(self):
        cec_fr.pcbnew.LayerName = self._ln

    def test_gap_between_x_separated_pads(self):
        pads = [self._Pad((0.0, 0.0, 2.0, 3.0), ["F.Cu"]),
                self._Pad((5.0, 0.0, 7.0, 3.0), ["F.Cu"])]
        gaps = cec_fr.shunt_tap_gaps(self._board(pads))
        self.assertEqual(len(gaps), 1)
        lays, rect, ref = gaps[0]
        self.assertEqual(rect, (2.0, 0.0, 5.0, 3.0),
                         "the gap is between the pads' inner edges, spanning their shared extent")
        self.assertEqual(ref, "RS1")

    def test_gap_is_scoped_to_the_pads_own_layers(self):
        pads = [self._Pad((0.0, 0.0, 2.0, 3.0), ["F.Cu"]),
                self._Pad((5.0, 0.0, 7.0, 3.0), ["F.Cu"])]
        lays, _rect, _ref = cec_fr.shunt_tap_gaps(self._board(pads))[0]
        self.assertEqual(lays, {"F.Cu"})
        self.assertNotIn("In1.Cu", lays,
                         "an inner GND plane under an SMD shunt must not be clipped")

    def test_overlapping_pads_have_no_gap(self):
        pads = [self._Pad((0.0, 0.0, 5.0, 3.0), ["F.Cu"]),
                self._Pad((4.0, 0.0, 9.0, 3.0), ["F.Cu"])]
        self.assertEqual(cec_fr.shunt_tap_gaps(self._board(pads)), [])

    def test_non_shunt_parts_are_ignored(self):
        pads = [self._Pad((0.0, 0.0, 2.0, 3.0), ["F.Cu"]),
                self._Pad((5.0, 0.0, 7.0, 3.0), ["F.Cu"])]
        self.assertEqual(cec_fr.shunt_tap_gaps(self._board(pads, ref="R7")), [])


if __name__ == "__main__":
    unittest.main()


class RectilinearPourTest(unittest.TestCase):
    """Pour outlines are Manhattan (owner 2026-07-25: "diagonal blobs that don't
    make sense"). mask_to_polys builds a rectilinear union of cell runs; the
    Douglas-Peucker simplify that used to follow it cut corners and manufactured
    the diagonals -- 77 of them across the 24-pin's pourfirst zones."""

    def _diag(self, pts, tol=1e-6):
        n = len(pts)
        d = 0
        for i in range(n - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            if abs(x1 - x0) > tol and abs(y1 - y0) > tol:
                d += 1
        return d

    def test_masks_render_rectilinear(self):
        try:
            import numpy as np
            import cec_slab_pour as sp
        except ImportError:
            self.skipTest("numpy/cec_slab_pour unavailable")

        class G:
            x0 = y0 = 0.0
            cell = 0.5
            nx = ny = 40
        # a staircase-ish blob: the shape Douglas-Peucker used to diagonalise
        m = np.zeros((G.ny, G.nx), bool)
        for j in range(G.ny):
            m[j, : max(1, min(G.nx, 4 + j))] = True
        polys = sp.mask_to_polys(m, G, min_area_mm2=0.1)
        self.assertTrue(polys, "the mask should produce at least one polygon")
        for p in polys:
            self.assertEqual(self._diag(p), 0,
                             f"pour outline has diagonal edge(s): {p[:8]}... "
                             "-- smoothing must happen on the MASK, never on the polygon")

    def test_drop_collinear_preserves_shape(self):
        import cec_slab_pour as sp
        square = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (0, 2), (0, 0)]
        out = sp._drop_collinear(square)
        self.assertLess(len(out), len(square), "collinear points should be dropped")
        self.assertEqual(min(x for x, _ in out), 0)
        self.assertEqual(max(x for x, _ in out), 2)
        self.assertEqual(max(y for _, y in out), 2)


class ViaFieldShapeTest(unittest.TestCase):
    """A layer change is ONE compact via array, not a fence (owner 2026-07-25:
    "concentrate them at one via array spot... instead of going ham on them").
    Measured before the fix: 22 vias in a row spanning 1.6..37.0mm -- half the
    board -- because the field was sized as a single line across the corridor's
    full ampacity-driven width."""

    class G:
        x0 = y0 = 0.0
        cell = 0.5

    def _field(self, half_w):
        import cec_slab_pour as sp
        # arrival direction +x -> the old code laid the fence along y
        field6 = (20, 20, "In2.Cu", "B.Cu", 1.0, 0.0)
        return sp.field_via_line(field6, half_w, self.G, [], [])

    def test_wide_corridor_does_not_become_a_fence(self):
        vias, _ = self._field(9.0)           # 18mm-wide corridor
        self.assertGreater(len(vias), 4, "a wide corridor still needs its barrels")
        span_y = max(v[1] for v in vias) - min(v[1] for v in vias)
        span_x = max(v[0] for v in vias) - min(v[0] for v in vias)
        self.assertLess(span_y, 2.0 * 9.0 * 0.75,
                        f"via field still spans the corridor width ({span_y:.1f}mm) -- "
                        "that is the fence, not an array")
        self.assertGreater(span_x, 0.0,
                           "an array must use both axes; a single row is the old fence")

    def test_count_is_current_derived_not_width_derived(self):
        """SUPERSEDED BELIEF, corrected 2026-07-26. This test used to assert the
        width-derived count was preserved exactly, on my claim that "the count is
        ampacity". It was not -- it was the corridor WIDTH, which is wide for
        reach and min-width reasons too, and it handed +3V3 (0.8A, one barrel of
        need) a 29-via block. The count now comes from current where the caller
        knows it, and is capped otherwise."""
        import cec_slab_pour as sp
        vias, _ = self._field(9.0)                       # an 18mm-wide corridor
        self.assertLessEqual(len(vias), sp.FIELD_VIA_CAP,
                             f"{len(vias)} barrels is the perforation again")
        self.assertGreaterEqual(len(vias), 2, "a layer change needs a spare barrel")

    def test_aspect_is_roughly_square(self):
        vias, _ = self._field(6.0)
        span_x = max(v[0] for v in vias) - min(v[0] for v in vias)
        span_y = max(v[1] for v in vias) - min(v[1] for v in vias)
        self.assertLessEqual(max(span_x, span_y) / max(0.1, min(span_x, span_y)), 3.0,
                             f"array aspect {span_x:.1f}x{span_y:.1f} is a line, not an array")


class LSimplifyTest(unittest.TestCase):
    """A run's copper is one or two straight legs, not a stair (owner 2026-07-26:
    the pours "are still diagonal" -- Manhattan EDGES were not enough while the
    PATH still walked a diagonal as steps)."""

    def _free(self, n=10):
        return [[True] * n for _ in range(n)]

    def test_staircase_becomes_an_L(self):
        import cec_slab_pour as sp
        stair = [(0, 0), (0, 1), (1, 1), (1, 2), (2, 2), (2, 3), (3, 3)]
        out = sp._l_simplify(stair, self._free(), None)
        turns = sum(1 for a, b, c in zip(out, out[1:], out[2:])
                    if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]))
        self.assertLessEqual(turns, 1, f"an L has at most one turn, got {turns}: {out}")
        self.assertEqual(out[0], stair[0])
        self.assertEqual(out[-1], stair[-1])

    def test_blocked_L_keeps_the_original_walk(self):
        import cec_slab_pour as sp
        free = self._free()
        for c in range(10):            # wall across row 0 and column 0 corners
            free[0][c] = False
        for r in range(10):
            free[r][0] = False
        stair = [(1, 1), (1, 2), (2, 2), (2, 3), (3, 3)]
        free[1][3] = False             # block one L corner
        free[3][1] = False             # block the other
        out = sp._l_simplify(stair, free, None)
        self.assertEqual(out, stair,
                         "with both L corners blocked the search's own walk must stand")

    def test_straight_run_is_untouched(self):
        import cec_slab_pour as sp
        run = [(2, 0), (2, 1), (2, 2), (2, 3)]
        self.assertEqual(sp._l_simplify(run, self._free(), None), run)

    def test_no_mask_is_a_noop(self):
        import cec_slab_pour as sp
        stair = [(0, 0), (0, 1), (1, 1), (1, 2)]
        self.assertEqual(sp._l_simplify(stair, None, None), stair)


class ViaCountTest(unittest.TestCase):
    """A field carries its net's CURRENT across a layer change, sized from the
    DESIGN BASIS (owner 2026-07-26: "don't just say it gives some amperage
    without checking it against design spec... plan for worst case").

    The screenshot that prompted this was +3V3 with ~29 barrels. That net's
    worst case is bounded by its source -- the LP5907 LDO at 250mA maximum per
    the TI datasheet (spec Hub regulator row) -- so it needs one barrel and a
    spare. The count had come from the corridor's WIDTH.
    """

    def test_spec_anchor_logic_rail(self):
        import cec_slab_pour as sp
        self.assertEqual(sp.vias_for_current(0.25), 2,
                         "+3V3 is LDO-bounded at 250mA: one barrel plus a spare")

    def test_spec_anchor_atx_circuit_vs_rail(self):
        """The 6A bar is PER CIRCUIT; the RAIL is what crosses a layer.

        Owner correction 2026-07-26: "we have two blades, because I have seen
        much more amperage than that." The re-ratified joint counts agree --
        atx24 carries 3V3 x2 joints at 18.32A each (2026-07-06, TE 63969-1 at
        22.9A/125%), so the 3.3V rail sits well above one joint, ~18A for three
        ATX circuits, not the 6A I first sized it at."""
        import cec_slab_pour as sp
        self.assertEqual(sp.vias_for_current(6.0), 5,
                         "ONE 6A circuit: 4 barrels plus a spare")
        self.assertGreaterEqual(sp.vias_for_current(18.0), 12,
                                "the ~18A 3.3V RAIL needs a real field, not a circuit's worth")

    def test_margin_policy_is_applied(self):
        """spec 2.8: continuous rating >= 125% of sustained worst case."""
        import cec_slab_pour as sp
        self.assertEqual(sp.vias_for_current(3.2), 3)
        self.assertGreater(sp.vias_for_current(8.0), sp.vias_for_current(4.0))

    def test_a_field_never_becomes_a_perforation(self):
        import cec_slab_pour as sp
        self.assertLessEqual(sp.vias_for_current(52.0), sp.FIELD_VIA_CAP,
                             "an EPS-class crossing wants a planned transition, "
                             "not an unbounded via block")

    def test_width_heuristic_is_capped(self):
        import cec_slab_pour as sp

        class G:
            x0 = y0 = 0.0
            cell = 0.5
        vias, _ = sp.field_via_line((20, 20, "In2.Cu", "B.Cu", 1.0, 0.0), 9.0, G, [], [])
        self.assertLessEqual(len(vias), sp.FIELD_VIA_CAP,
                             f"{len(vias)} barrels from a width heuristic is the 29-via block")

    def test_explicit_count_wins(self):
        import cec_slab_pour as sp

        class G:
            x0 = y0 = 0.0
            cell = 0.5
        vias, _ = sp.field_via_line((20, 20, "In2.Cu", "B.Cu", 1.0, 0.0), 9.0, G, [], [],
                                    n_needed=2)
        self.assertEqual(len(vias), 2)
