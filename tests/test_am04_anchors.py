# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# AM-04 analytic FEM anchors (rulings doc 2026-06-10, checklist items 8-12).
# Host-runnable except the composition anchor (pcbnew -> container leg, skips
# cleanly on the bare host). This file is ALSO the AM-02 fixture the
# thermal.ipc2152.ref.plane_adjacent corpus entry declares.
import json, math, os, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.dont_write_bytecode = True

import cec_synth_pipeline as S                                # noqa: E402

ENTRY_FILE = os.path.join(ROOT, "corpus", "staging", "general",
                          "thermal-ipc2152.json")
MICRO = os.path.join(ROOT, "tests", "golden", "fixtures", "am04-microboard",
                     "microboard.kicad_pcb")
TOLERANCE_BAND = 0.20      # owner-set accuracy band once calibration flips (R7)


def _ref_points():
    """Ruling 7 transition mechanics: while promoted/ is empty the goldens read
    the entry BY ID from the staging file directly; at promotion the same
    entry also compiles through the params channel."""
    for e in json.load(open(ENTRY_FILE)):
        if e["id"] == "thermal.ipc2152.ref.plane_adjacent":
            return e["value"]["points"]
    raise AssertionError("reference entry missing")


class T8aChartPointAnchors(unittest.TestCase):
    """Ruling 7(a): dt_ipc reproduces the IPC-2221 chart points exactly --
    pure regression value (these MUST NOT move in the PR-two debt fix)."""

    def test_canonical_points(self):
        for p in _ref_points():
            got = S.dt_ipc(p["I_A"], p["cross_mm2"])
            self.assertAlmostEqual(got, p["dT_2221_computed_C"], delta=0.02,
                                   msg="2221 chart point drifted at %s" % p)

    def test_formula_inverse(self):
        # I = k*dT^0.44*A^0.725 closed under its own inverse
        a_mils = 0.2 * 1550.0031
        I = 0.048 * (12.0 ** 0.44) * (a_mils ** 0.725)
        self.assertAlmostEqual(S.dt_ipc(I, 0.2), 12.0, delta=0.01)


class T8bPicardAnchor(unittest.TestCase):
    """Closed-form rho(T) fixed point: dT = dt0*(1+a(amb-20))/(1-dt0*a)."""

    def test_hand_value(self):
        dt0 = S.dt_ipc(10, 0.348)
        alpha = S.ALPHA_CU
        hand = dt0 * (1 + alpha * (25 - 20)) / (1 - dt0 * alpha)
        self.assertAlmostEqual(S._picard_dt(10, 0.348, 25, True), hand, delta=0.01)
        self.assertAlmostEqual(S._picard_dt(10, 0.348, 25, True), 6.12, delta=0.02)

    def test_runaway_clamps_not_explodes(self):
        v = S._picard_dt(100, 0.01, 25, True)
        self.assertLess(v, 1e6, "fusing regime must clamp, never return 1e40")


class T9Conservatism(unittest.TestCase):
    """Ruling 7(b): the uncalibrated solver's tested property IS conservatism
    -- 2221-computed dT >= the 2152 plane-adjacent reference on every
    chart-domain point. At calibration (per family+quantity, Ruling 9) the
    same points TIGHTEN into accuracy assertions within the owner band --
    green today, automatically stricter at calibration, never red by design."""

    def _calibrated(self):
        cfg = S.Config(board="hub-standard")
        return S._calibration_state(cfg, "hotspot") != "uncalibrated"

    def test_direction_or_band(self):
        calibrated = self._calibrated()
        for p in _ref_points():
            got = S.dt_ipc(p["I_A"], p["cross_mm2"])
            ref = p["dT_2152_plane_adjacent_C"]
            if calibrated:
                self.assertLessEqual(abs(got - ref) / ref, TOLERANCE_BAND,
                                     "calibrated: accuracy band at %s" % p)
            else:
                self.assertGreaterEqual(got, ref,
                                        "uncalibrated solver must be conservative at %s" % p)

    def test_synthetic_flip_tightens(self):
        """The latch test: a synthetic hotspot label for the family flips the
        SAME points into the accuracy band; DC-IR stays uncalibrated."""
        import tempfile, shutil, importlib
        runs = tempfile.mkdtemp()
        old = os.environ.get("CEC_RUNS_DIR")
        os.environ["CEC_RUNS_DIR"] = runs
        try:
            import cec_ledger
            importlib.reload(cec_ledger)
            d = cec_ledger.decision(
                decision_class="confirmed-fixed", artifact="bench-session",
                decider={"kind": "human", "id": "nathanfraske"},
                verdict="label",
                extra={"quantity": "hotspot", "families": ["hub", "hub-standard"]})
            cfg = S.Config(board="hub-standard")
            state = S._calibration_state(cfg, "hotspot")
            self.assertTrue(state.startswith("bench:"),
                            "hotspot label must flip the latch (got %r)" % state)
            self.assertEqual(S._calibration_state(cfg, "dcir"), "uncalibrated",
                             "a hotspot label says nothing about DC-IR")
            mod_cfg = S.Config(board="eps-8pin")
            self.assertEqual(S._calibration_state(mod_cfg, "hotspot"), "uncalibrated",
                             "a hub label says nothing about the module family")
        finally:
            if old is None:
                os.environ.pop("CEC_RUNS_DIR", None)
            else:
                os.environ["CEC_RUNS_DIR"] = old
            shutil.rmtree(runs)
            importlib.reload(cec_ledger)


class T11BlockingWithTheMark(unittest.TestCase):
    """Ruling 9 posture: binding encodes AUTHORITY, calibration encodes
    ACCURACY -- they never trade. An uncalibrated thermal violation still
    blocks signoff AND carries the mark."""

    def test_flag_blocks_and_carries_mark(self):
        res = S.ThermalResult(ambient=50.0, max_T=140.0, max_dT=90.0,
                              nets={"HC": {"I": 10, "cross_mm2": 0.1, "J": 100,
                                           "dT": 90.0, "T": 140.0, "poured": False}},
                              vias=[], shunts=[])
        cfg = S.Config(board="x", params={})
        flags = S.physics_gates(res, cfg)
        self.assertTrue(flags, "an over-temp must flag")
        for f in flags:
            self.assertEqual(f.binding, "gate", "uncalibrated thermal still BLOCKS")
            self.assertEqual(f.detail.get("calibration"), "uncalibrated")
        self.assertFalse(S.human_signoff("x", cfg, flags),
                         "blocking-with-the-mark: signoff must refuse")


@unittest.skipUnless(os.path.exists(MICRO), "micro-board fixture absent")
class T8cCompositionAnchor(unittest.TestCase):
    """Ruling 8: the hand-derivable micro-board pins the COMPOSITION (where the
    known debt lives). PR one pins CURRENT behavior; PR two moves these to the
    DERIVATION.md corrected column. Container leg (needs pcbnew)."""

    def setUp(self):
        try:
            import pcbnew                                     # noqa: F401
        except ImportError:
            self.skipTest("pcbnew absent (host) -- container leg")

    def test_pinned_current_behavior(self):
        cfg = S.Config(board="am04-microboard",
                       params={"net_currents": {"HC": 10.0}, "shunt_rth_CW": 25.0})
        res = S.electrothermal_solve(MICRO, cfg, ambient=25.0)
        hc = res.nets["HC"]
        # the segment-sum debt, PINNED (3 x 0.348 serial sections summed):
        self.assertAlmostEqual(hc["cross_mm2"], 1.044, delta=0.01)
        self.assertAlmostEqual(hc["dT"], 4.8, delta=0.3)
        self.assertEqual(len(res.vias), 2)
        for v in res.vias:
            self.assertAlmostEqual(v["I_via"], 5.0, delta=0.01)   # split correct
            self.assertAlmostEqual(v["dT"], 175.3, delta=2.0)
        self.assertAlmostEqual(res.shunts[0]["P_W"], 0.05, delta=0.005)
        self.assertEqual(res.calibration, "uncalibrated")


if __name__ == "__main__":
    unittest.main(verbosity=2)
