"""Teeth for sub-minimum track-width normalization.

Freerouting's DSN/SES round-trip can return a track a fraction of a micron under
the board minimum -- measured on the hub candidate, 5 of ~1900 tracks came back
at 0.1998mm against a 0.2000mm minimum. Each is a `track_width` DRC ERROR, so a
0.2um artifact is a hard fab-gate blocker that reseeding cannot clear.

The repair must be surgical: snap only what is within tolerance, never widen a
track that is genuinely too thin (that is a real fault and must stay visible).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))


class _Track:
    def __init__(self, w_mm, cls="PCB_TRACK", start=(0.0, 0.0), end=(1.0, 0.0)):
        self._w = int(round(w_mm * 1_000_000))
        self._cls = cls
        self._start = _Point(*start)
        self._end = _Point(*end)

    def GetClass(self):
        return self._cls

    def GetWidth(self):
        return self._w

    def SetWidth(self, w):
        self._w = w

    def GetStart(self):
        return self._start

    def GetEnd(self):
        return self._end


class _Point:
    def __init__(self, x_mm, y_mm):
        self.x = int(round(x_mm * 1_000_000))
        self.y = int(round(y_mm * 1_000_000))


class _DS:
    def __init__(self, min_mm):
        self.m_TrackMinWidth = int(round(min_mm * 1_000_000))


class _Board:
    def __init__(self, tracks, min_mm=0.2):
        self._t = tracks
        self._ds = _DS(min_mm)

    def GetTracks(self):
        return self._t

    def GetDesignSettings(self):
        return self._ds

    def Remove(self, item):
        self._t.remove(item)


class TrackWidthNormTest(unittest.TestCase):
    def setUp(self):
        import cec_fr
        self.fn = cec_fr.normalize_track_width

    def test_the_measured_case_is_repaired(self):
        """0.1998 against a 0.2000 minimum -- the actual hub defect."""
        t = _Track(0.1998)
        b = _Board([t])
        self.assertEqual(self.fn(b), 1)
        self.assertEqual(t.GetWidth(), 200000)

    def test_a_genuinely_thin_track_is_left_visible(self):
        """0.12mm on a 0.2mm minimum is a DESIGN fault, not a rounding artifact
        -- silently widening it would hide a real problem."""
        t = _Track(0.12)
        b = _Board([t])
        self.assertEqual(self.fn(b), 0)
        self.assertEqual(t.GetWidth(), 120000)

    def test_a_conforming_track_is_untouched(self):
        t = _Track(0.25)
        b = _Board([t])
        self.assertEqual(self.fn(b), 0)
        self.assertEqual(t.GetWidth(), 250000)

    def test_exactly_minimum_is_untouched(self):
        t = _Track(0.2)
        b = _Board([t])
        self.assertEqual(self.fn(b), 0)

    def test_vias_are_not_tracks(self):
        v = _Track(0.1998, cls="PCB_VIA")
        b = _Board([v])
        self.assertEqual(self.fn(b), 0, "vias are normalize_via_annular's job")

    def test_no_minimum_configured_is_a_no_op(self):
        b = _Board([_Track(0.1998)], min_mm=0.0)
        self.assertEqual(self.fn(b), 0)

    def test_the_tolerance_boundary_holds(self):
        inside = _Track(0.1955)     # 4.5um under, within the 5um tolerance
        outside = _Track(0.1940)    # 6um under, outside it
        b = _Board([inside, outside])
        self.assertEqual(self.fn(b), 1)
        self.assertEqual(inside.GetWidth(), 200000)
        self.assertEqual(outside.GetWidth(), 194000)


class DegenerateTrackPruneTest(unittest.TestCase):
    def setUp(self):
        import cec_fr
        self.fn = cec_fr.prune_degenerate_tracks

    def test_nanometre_quantization_artifact_is_removed(self):
        t = _Track(0.2, start=(0.0, 0.0), end=(0.000001, 0.0))
        b = _Board([t])
        self.assertEqual(self.fn(b), 1)
        self.assertEqual(b.GetTracks(), [])

    def test_zero_length_track_is_removed(self):
        t = _Track(0.2, start=(4.0, 5.0), end=(4.0, 5.0))
        b = _Board([t])
        self.assertEqual(self.fn(b), 1)

    def test_real_short_neck_remains_visible(self):
        t = _Track(0.2, start=(0.0, 0.0), end=(0.01, 0.0))
        b = _Board([t])
        self.assertEqual(self.fn(b), 0)
        self.assertEqual(b.GetTracks(), [t])

    def test_via_is_never_pruned(self):
        v = _Track(0.2, cls="PCB_VIA", start=(0.0, 0.0), end=(0.0, 0.0))
        b = _Board([v])
        self.assertEqual(self.fn(b), 0)
        self.assertEqual(b.GetTracks(), [v])
