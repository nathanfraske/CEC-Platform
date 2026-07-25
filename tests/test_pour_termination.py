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
