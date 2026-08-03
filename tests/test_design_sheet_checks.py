#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Teeth for the STANDARD-DESIGN-SHEET §K mechanization set (cec_constraints
# assembly-dfm checkers, sheet §J.6). AM-02 discipline: every checker must FAIL
# on a demonstrably bad example (sabotaged in-memory on a real board) and hold
# its measured verdict on the committed boards. pcbnew-gated like the CL-25 pack:
#
#   docker compose -f docker/compose.yaml run --rm --no-deps routing \
#       bash -lc 'cd /workspace && python3 -m unittest tests.test_design_sheet_checks -v'
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew
    HAVE_PCBNEW = True
    import cec_constraints as K
except ImportError:
    HAVE_PCBNEW = False
    K = None

EPS = os.path.join(ROOT, "old-revisions", "beta", "eps-8pin-pre-rev3",
                   "eps8pin-module.kicad_pcb")
HPWR = os.path.join(ROOT, "beta", "12vhpwr-standard", "12vhpwr-standard-module.kicad_pcb")
HUB = os.path.join(ROOT, "old-revisions", "hubs", "hub-standard-alpha",
                   "hub-standard.kicad_pcb")

CIDS = ("fiducial-protocol", "mlcc-edge-orientation", "ecap-edge-distance",
        "decoupler-adjacency-k5")


def _mm_pt(x, y):
    return pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6))


@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(HUB), "pcbnew + boards required")
class TestRegistration(unittest.TestCase):
    # RATIFICATION STATE (owner GO 2026-07-19, after the fleet calibration run):
    # mlcc-edge-orientation + ecap-edge-distance ratified strong (zero alpha
    # false-positives); fiducial-protocol + decoupler-adjacency-k5 HELD at
    # advisory/proposed (the shipped 12vhpwr alpha fails the 5mm fiducial edge
    # rule; the K.5 1.5mm target fails 100% of the fleet -- doctrine gap, not
    # defects). This test pins the RULED state per checker, not a blanket.
    RULED = {"mlcc-edge-orientation": ("strong", "ratified"),
             "ecap-edge-distance": ("strong", "ratified"),
             "fiducial-protocol": ("advisory", "proposed"),
             "decoupler-adjacency-k5": ("advisory", "proposed")}

    def test_registered_per_ruled_state(self):
        by_id = {c.id: c for c in K.REGISTRY}
        for cid in CIDS:
            self.assertIn(cid, by_id)
            self.assertIn(cid, K.CHECKERS)
            sev, st = self.RULED[cid]
            self.assertEqual(by_id[cid].severity, sev, cid)
            self.assertEqual(by_id[cid].status, st, cid)


@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(HUB) and os.path.isfile(HPWR)
                     and os.path.isfile(EPS), "pcbnew + boards required")
class TestMeasuredVerdicts(unittest.TestCase):
    """The committed-board verdicts, measured 2026-07-17 -- a checker drift flips these."""

    @classmethod
    def setUpClass(cls):
        cls.hub = pcbnew.LoadBoard(HUB)
        cls.hpwr = pcbnew.LoadBoard(HPWR)
        cls.eps = pcbnew.LoadBoard(EPS)

    def test_fiducial_protocol_hub_passes(self):
        ok, detail = K.CHECKERS["fiducial-protocol"](self.hub, HUB, {})[:2]
        self.assertTrue(ok, detail)

    def test_fiducial_protocol_hpwr_reports_edge_margin(self):
        # the 12VHPWR precedent satisfies ASYMMETRY (sheet §K.4) but its FID1/FID2 sit
        # 4.2/2.9mm from an edge vs the 5.0 [wb] target -- the audit reports, honestly
        ok, detail = K.CHECKERS["fiducial-protocol"](self.hpwr, HPWR, {})[:2]
        self.assertFalse(ok, detail)
        self.assertIn("from an edge", detail)
        self.assertNotIn("symmetric", detail)

    def test_fiducial_protocol_na_without_fids(self):
        ok, _ = K.CHECKERS["fiducial-protocol"](self.eps, EPS, {})[:2]
        self.assertIsNone(ok)

    def test_mlcc_edge_na_on_committed_boards(self):
        # no committed board parks a 2-pad MLCC inside the 1mm edge band today (eps's
        # mid-layout off-board parks are deliberately out of scope)
        for b, p in ((self.hub, HUB), (self.hpwr, HPWR), (self.eps, EPS)):
            ok, detail = K.CHECKERS["mlcc-edge-orientation"](b, p, {})[:2]
            self.assertIsNone(ok, detail)

    def test_ecap_edge_hub_passes_eps_na(self):
        ok, detail = K.CHECKERS["ecap-edge-distance"](self.hub, HUB, {})[:2]
        self.assertTrue(ok, detail)
        self.assertIsNone(K.CHECKERS["ecap-edge-distance"](self.eps, EPS, {})[0])

    def test_decoupler_k5_reports_retired_universal_threshold(self):
        # The 2026-08-02 source audit found no device-independent basis for the
        # former 1.5mm number. Keep the historical ID visible but non-gating.
        ok, detail = K.CHECKERS["decoupler-adjacency-k5"](self.hub, HUB, {})[:2]
        self.assertIsNone(ok, detail)
        self.assertIn("1.5mm K.5 target retired", detail)
        self.assertIn("one-to-one", detail)


@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(HUB), "pcbnew + boards required")
class TestTeethSabotage(unittest.TestCase):
    """Each checker demonstrably FAILS on a constructed-bad state (fresh board load
    per test; sabotage is in-memory, nothing written)."""

    def setUp(self):
        self.hub = pcbnew.LoadBoard(HUB)

    def _fp(self, ref):
        fp = self.hub.FindFootprintByReference(ref)
        self.assertIsNotNone(fp, ref)
        return fp

    def test_fiducial_count_teeth(self):
        # rename, never board.Remove() -- the recorded SWIG footgun (Remove segfaults
        # the process; the toolchain memory's footgun list). "XFID3" leaves the FID* set
        self._fp("FID3").SetReference("XFID3")
        ok, detail = K.CHECKERS["fiducial-protocol"](self.hub, HUB, {})[:2]
        self.assertFalse(ok)
        self.assertIn("count 2 != 3", detail)

    def test_fiducial_symmetry_teeth(self):
        # FID1 + FID2 mirrored about the board centre, FID3 at the centre -> the set
        # maps onto itself under 180 degrees = the vision ambiguity the rule forbids
        bb = self.hub.GetBoardEdgesBoundingBox()
        cx = (bb.GetLeft() + bb.GetRight()) / 2e6
        cy = (bb.GetTop() + bb.GetBottom()) / 2e6
        f1 = self._fp("FID1")
        p1 = f1.GetPosition()
        self._fp("FID2").SetPosition(_mm_pt(2 * cx - p1.x / 1e6, 2 * cy - p1.y / 1e6))
        self._fp("FID3").SetPosition(_mm_pt(cx, cy))
        ok, detail = K.CHECKERS["fiducial-protocol"](self.hub, HUB, {})[:2]
        self.assertFalse(ok)
        self.assertIn("symmetric", detail)

    def test_mlcc_edge_orientation_teeth(self):
        # park a real 0402 hard against the LEFT edge; its long axis is derived from
        # the pads, so orientation decides the verdict: perpendicular fires, parallel passes
        bb = self.hub.GetBoardEdgesBoundingBox()
        fp = next((f for f in self.hub.GetFootprints()
                   if f.GetReference().startswith("C") and "_0402_" in f.GetFPIDAsString()), None)
        self.assertIsNotNone(fp, "hub carries 0402 decouplers")
        fp.SetOrientationDegrees(0.0)     # 0402 long axis horizontal = perpendicular to L edge
        fp.SetPosition(_mm_pt(bb.GetLeft() / 1e6 + 0.6, (bb.GetTop() + bb.GetBottom()) / 2e6))
        ok, detail = K.CHECKERS["mlcc-edge-orientation"](self.hub, HUB, {})[:2]
        self.assertFalse(ok, detail)
        self.assertIn(fp.GetReference(), detail)
        fp.SetOrientationDegrees(90.0)    # long axis vertical = parallel to the L edge
        ok, detail = K.CHECKERS["mlcc-edge-orientation"](self.hub, HUB, {})[:2]
        self.assertTrue(ok, detail)

    def test_ecap_edge_teeth(self):
        bb = self.hub.GetBoardEdgesBoundingBox()
        self._fp("C1").SetPosition(_mm_pt(bb.GetLeft() / 1e6 + 1.0,
                                          (bb.GetTop() + bb.GetBottom()) / 2e6))
        ok, detail = K.CHECKERS["ecap-edge-distance"](self.hub, HUB, {})[:2]
        self.assertFalse(ok)
        self.assertIn("C1", detail)

    def test_decoupler_assignment_is_one_to_one_and_value_qualified(self):
        measured = K._device_bypass_assignment(self.hub, project_max_mm=1000.0)
        cap_refs = [item["cap_ref"] for item in measured["assigned"].values()]
        self.assertEqual(len(cap_refs), len(set(cap_refs)))
        assigned_100n = next(
            item for item in measured["assigned"].values()
            if item["requirement"]["kind"] == "100n"
        )
        before = len(measured["assigned"])
        self._fp(assigned_100n["cap_ref"]).SetValue("1nF")
        after = K._device_bypass_assignment(self.hub, project_max_mm=1000.0)
        self.assertLess(len(after["assigned"]), before)


if __name__ == "__main__":
    unittest.main()
