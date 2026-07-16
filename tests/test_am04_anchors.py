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
    known debt lived). PR two (the debt fix: serial min-cut, per-cluster via
    split, k-by-feature-layer) moves the anchor to the DERIVATION.md CORRECTED
    column. The chart-point/Picard anchors above must NOT move -- the formula was
    never the debt, the composition was. Container leg (needs pcbnew)."""

    def setUp(self):
        try:
            import pcbnew                                     # noqa: F401
        except ImportError:
            self.skipTest("pcbnew absent (host) -- container leg")

    def test_corrected_composition(self):
        cfg = S.Config(board="am04-microboard",
                       params={"net_currents": {"HC": 10.0}, "shunt_rth_CW": 25.0})
        res = S.electrothermal_solve(MICRO, cfg, ambient=25.0)
        hc = res.nets["HC"]
        # CORRECTED: the three 0.348 mm^2 F.Cu/B.Cu sections are in SERIES -> the
        # serial min-cut governs (0.348), NOT the 1.044 segment-sum; and the
        # bottleneck is on an OUTER layer (k external) so dT lands on the Picard
        # anchor _picard_dt(10, 0.348, 25, True) = 6.12. (Was the pinned-debt
        # 1.044 / 4.8 in PR one.)
        self.assertAlmostEqual(hc["cross_mm2"], 0.348, delta=0.005)
        self.assertAlmostEqual(hc["dT"], 6.12, delta=0.1)
        self.assertEqual(len(res.vias), 2)
        for v in res.vias:
            self.assertAlmostEqual(v["I_via"], 5.0, delta=0.01)   # per-cluster split
            self.assertAlmostEqual(v["dT"], 175.3, delta=2.0)     # via barrel anchor unchanged
        self.assertAlmostEqual(res.shunts[0]["P_W"], 0.05, delta=0.005)
        self.assertEqual(res.calibration, "uncalibrated")


class T12JointRatingAnchor(unittest.TestCase):
    """Iteration-11 connector-joint element (blade-interconnect audit,
    2026-07-06): the joint model's thermal resistance is CALIBRATED from TE's
    own published rating datum -- 108-1706 Fig 4, 22.9 A base rated current by
    the 30 degC-rise method (AMP 109-45-1), the SAME method the platform margin
    policy uses. A real external anchor in the AM-04 sense."""

    def test_rating_datum_reproduced(self):
        # At the rating point the calibrated model must return the rating rise.
        r = S.joint_solve("te_63951_63969", 22.9, ambient=25.0)
        self.assertAlmostEqual(r["dT"], 30.0, delta=0.5)

    def test_policy_point_scaling(self):
        # 18.32 A = the 125%-policy allowable. dT scales ~(I/22.9)^2 (mild rho(T)
        # relief downward); must sit inside (0.5x .. 1.0x) of the quadratic value.
        r = S.joint_solve("te_63951_63969", 18.32, ambient=50.0)
        quad = 30.0 * (18.32 / 22.9) ** 2
        self.assertLess(r["dT"], quad * 1.05)
        self.assertGreater(r["dT"], quad * 0.5)
        self.assertLess(r["dT"], 30.0)                        # inside the policy budget

    def test_resistance_composition(self):
        # Total joint R at 20C: contact 1.0 mOhm spec-max + blade + receptacle +
        # tails (brass) -- the bulk metal must be a minority of the interface R.
        spec = S.joint_te_63951_63969()
        R = spec.R_total_ohm(20.0)
        self.assertAlmostEqual(R * 1e3, 1.0 + 0.149 + 0.169 + 0.111, delta=0.05)

    def test_teeth_worn_contact_fails_gate(self):
        # SABOTAGE: a worn/degraded contact (10 mOhm) at the policy current must
        # FAIL the 30C-rise gate loudly -- this is the iteration-10 0.34W-vs-3.4W
        # split as a modeled case, not an aside.
        worn = S.joint_solve("te_63951_63969", 18.32, ambient=50.0, worn=True)
        self.assertGreater(worn["dT"], 100.0)
        res = S.ThermalResult(ambient=50.0, max_T=50 + worn["dT"], max_dT=worn["dT"],
                              nets={}, vias=[], shunts=[], joints=[worn])
        cfg = S.Config(board="x", params={})
        names = [f.name for f in S.physics_gates(res, cfg)]
        self.assertIn("joint over-temp", names)

    def test_teeth_sabotaged_cross_raises_dt(self):
        # SABOTAGE: a blade cross-section cut to 10% must raise R and dT.
        spec = S.joint_te_63951_63969()
        bad = S.JointSpec(name="sabotaged", contact_R_ohm=spec.contact_R_ohm,
                          segments=tuple(
                              S.JointSegment(s.name, s.cross_mm2 * 0.1, s.length_mm,
                                             s.rho_ohm_m, s.alpha_per_C)
                              for s in spec.segments),
                          rth_CW=spec.calibrated_rth())     # SAME rth: isolate the R effect
        good = S.joint_solve(spec, 18.32, ambient=50.0)
        sab = S.joint_solve(bad, 18.32, ambient=50.0)
        self.assertGreater(sab["dT"], good["dT"] * 2.0)

    def test_additive_contract_no_joints_identical(self):
        # The element is ADDITIVE: declaring joints must not perturb the board
        # solve (nets/vias/shunts identical); declaring none yields joints == [].
        try:
            import pcbnew                                     # noqa: F401
        except ImportError:
            self.skipTest("pcbnew absent (host) -- container leg")
        base_cfg = S.Config(board="am04-microboard",
                            params={"net_currents": {"HC": 10.0}, "shunt_rth_CW": 25.0})
        with_j = S.Config(board="am04-microboard",
                          params={"net_currents": {"HC": 10.0}, "shunt_rth_CW": 25.0,
                                  "joints": [{"spec": "te_63951_63969", "I": 18.32}]})
        r0 = S.electrothermal_solve(MICRO, base_cfg, ambient=25.0)
        r1 = S.electrothermal_solve(MICRO, with_j, ambient=25.0)
        self.assertEqual(r0.joints, [])
        self.assertEqual(r0.nets, r1.nets)
        self.assertEqual(r0.vias, r1.vias)
        self.assertEqual(r0.shunts, r1.shunts)
        self.assertEqual(len(r1.joints), 1)

    def test_neg12_rail_classification_fix(self):
        # Audit defect: '-12V'/'/-12V' matched the '12V' substring and took the
        # 40A cable current -> false runaway on a 0.3A ATX signal rail. Fixed:
        # negative rail classifies first; +12V keeps the cable current.
        cfg = S.Config(board="x", params={})
        cur = S._net_currents(cfg, {"-12V", "/-12V", "+12V", "/SENSE1_HI"})
        self.assertEqual(cur["+12V"], 40.0)
        self.assertEqual(cur["/SENSE1_HI"], 40.0)
        self.assertEqual(cur["-12V"], 0.5)
        self.assertEqual(cur["/-12V"], 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
