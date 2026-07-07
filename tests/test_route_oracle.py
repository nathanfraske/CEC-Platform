"""ROUTE-ORACLE GRADER (placer-feasibility SLICE-1a, docs/placer-feasibility-2026-06-30.md).

The placer used to select on the CHEAP placement_proxy (HPWL/RUDY/thermal), which does NOT predict
real routability -> it converged on placements that proxy-look-good but route DIRTY. route_oracle_grade
closes that: it grades a placement by ACTUALLY ROUTING it (the proven gate-clean recipe) and reading the
REAL post-route ACCEPT CONJUNCTION -- kelvin_ok AND diffpair_ok AND drc-finishing-only AND
foreign_on_pour==0 AND thermal-in-budget AND routing-complete.

Three layers, mirroring tests/test_placer_oracle.py's convention (logic host-side, real-board pcbnew-gated):
  * TestOracleLogic        -- the pure grading LOGIC (classification, sort_key, opt-in switch). Always runs.
  * TestOracleConstruction -- pcbnew-gated: the grader can never pass a board the real route fails (the
                              committed UNROUTED placement, route=False, FAILS) + the gate==AND invariant.
  * TestOracleRoute        -- pcbnew + Freerouting: the real route+grade TEETH on committed fixtures:
                              the gate-clean eps placement PASSES, its proxy-better-but-dirty parent FAILS,
                              and placement_proxy ranking DISAGREES with the oracle ranking.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import cec_synth_pipeline as sp                                  # noqa: E402

try:
    import pcbnew                                                # noqa: F401
    HAVE_PCBNEW = True
except Exception:
    HAVE_PCBNEW = False

ROOT = os.path.normpath(os.path.join(HERE, ".."))
FIX = os.path.join(HERE, "golden", "fixtures", "route-oracle")
N2_PCB = os.path.join(FIX, "eps-rev3-n2.kicad_pcb")              # gate-clean placement -> PASS
WIDEGAP_PCB = os.path.join(FIX, "eps-rev3-widegap-m.kicad_pcb")  # proxy-better-but-dirty parent -> FAIL
GOLDEN_EPS = os.path.join(ROOT, "tests", "golden", "eps-8pin", "eps8pin-module.kicad_pcb")  # UNROUTED


class _R:
    """A tiny stand-in for cec_score.Rules carrying just the pair/net fields _classify_unconnected reads."""
    def __init__(self, kelvin_pairs=(), diff_pairs=(), nets_12v=()):
        self.kelvin_pairs = list(kelvin_pairs)
        self.diff_pairs = list(diff_pairs)
        self.nets_12v = list(nets_12v)


# ===================================================================== logic (no pcbnew)
class TestOracleLogic(unittest.TestCase):
    def test_classify_unconnected_safety_vs_signal(self):
        rules = _R(kelvin_pairs=[("/SENSEC1_HI", "/SENSEC1_LO")],
                   diff_pairs=[("/USB_D_P", "/USB_D_N")], nets_12v=["/SENSEC1_HI"])
        crit, sig = sp._classify_unconnected(
            ["/SENSEC1_LO", "/USB_D_P", "GND", "/SENSEC2_HI", "/GPIO0", "/I2C_SDA"], rules)
        # safety pair leg, diff leg, GND, a bare _HI/_LO, and a 12V net are all CRITICAL
        self.assertIn("/SENSEC1_LO", crit)
        self.assertIn("/USB_D_P", crit)
        self.assertIn("GND", crit)
        self.assertIn("/SENSEC2_HI", crit)        # _HI suffix -> high-current
        # plain signal hops are the finishing residual
        self.assertCountEqual(sig, ["/GPIO0", "/I2C_SDA"])

    def test_sort_key_pass_beats_fail(self):
        # a gate-clean candidate (tier 0) ALWAYS outranks a failing one (tier 1)
        passing = sp._oracle_fail_dict("x")        # then flip its key to a pass-shaped key
        pass_key = (0, 12.0, 50, 1000.0, 0, 0)
        fail_key = (1, 0, 0, 1, 0, 12.0)
        self.assertLess(pass_key, fail_key)
        self.assertEqual(passing["sort_key"][0], 1)   # the fail dict is tier 1 (worst)

    def test_sort_key_fail_closeness(self):
        # among failures: fewer safety fails, then fewer foreign, then fewer unconnected ranks first
        near = (1, 0, 0, 1, 0, 12.0)      # only 1 signal ratline off
        kelvin_broken = (1, 1, 0, 8, 0, 12.0)  # a safety gate fails -> much worse
        foreign_dirty = (1, 0, 6, 0, 0, 12.0)  # foreign-on-pour intrusions
        self.assertLess(near, foreign_dirty)
        self.assertLess(foreign_dirty, kelvin_broken)

    def test_opt_in_switch(self):
        cfg = sp.Config(board="eps-8pin")
        self.assertFalse(sp._route_oracle_enabled(cfg))       # default OFF
        cfg.params["route_oracle"] = True
        self.assertTrue(sp._route_oracle_enabled(cfg))
        cfg.params["route_oracle"] = False
        os.environ["CEC_ROUTE_ORACLE"] = "1"
        try:
            self.assertTrue(sp._route_oracle_enabled(cfg))    # env override
        finally:
            os.environ.pop("CEC_ROUTE_ORACLE", None)

    def test_fail_dict_is_worst_rank(self):
        d = sp._oracle_fail_dict("lbl", route_s=1.0, error="boom")
        self.assertFalse(d["gate"])
        self.assertEqual(d["sort_key"][0], 1)
        self.assertGreaterEqual(d["sort_key"][1], 9)          # max safety-fail weight


# ===================================================================== construction invariant (pcbnew)
@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(GOLDEN_EPS),
                     "pcbnew + the committed golden eps placement required")
class TestOracleConstruction(unittest.TestCase):
    def test_unrouted_board_can_never_pass(self):
        # route=False grades the board AS-IS. The committed eps placement is UNROUTED -> the real route
        # state fails -> the grader MUST fail. (The grader can never pass a board the real route fails.)
        r = sp.route_oracle_grade(GOLDEN_EPS, route=False)
        self.assertFalse(r["gate"])
        self.assertFalse(r["kelvin_ok"])                      # nothing is routed
        self.assertEqual(r["sort_key"][0], 1)

    def test_gate_is_the_full_conjunction(self):
        # gate == AND of every term, never a subset -- on a REAL as-is grade.
        r = sp.route_oracle_grade(GOLDEN_EPS, route=False)
        self.assertEqual(r["gate"], bool(r["gates_pass"] and r["foreign_ok"]
                                         and r["thermal_ok"] and r["routing_complete"]))


# ===================================================================== real route+grade TEETH (pcbnew+FR)
@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(N2_PCB) and os.path.isfile(WIDEGAP_PCB),
                     "pcbnew + Freerouting + the route-oracle fixtures required (in-container)")
class TestOracleRoute(unittest.TestCase):
    """Real Freerouting routes -- minutes; runs in the routing container, skipped on a kicad-less box."""

    @classmethod
    def setUpClass(cls):
        cls.n2 = sp.route_oracle_grade(N2_PCB, passes=8, opt=12)
        cls.wg = sp.route_oracle_grade(WIDEGAP_PCB, passes=8, opt=12)

    def test_gate_clean_placement_passes(self):
        r = self.n2
        self.assertTrue(r["gate"], "eps-rev3-n2 should route GATE-CLEAN: %s" % r["reasons"])
        self.assertTrue(r["kelvin_ok"] and r["diffpair_ok"])
        self.assertEqual(r["drc"], 0)
        self.assertEqual((r["foreign"]["tracks"], r["foreign"]["vias"]), (0, 0))
        self.assertTrue(r["thermal_ok"])
        self.assertFalse(r["unconn_critical"])                # no safety/power ratline
        self.assertEqual(r["sort_key"][0], 0)                 # tier 0 = gate-clean

    def test_known_bad_placement_fails(self):
        # the pre-fix parent. HISTORY: this fixture originally stranded the Kelvin tap
        # (kelvin_ok=False); the 2026-07-07 BENT-TAP fallback (cec_fr dogleg on refusal)
        # genuinely HEALED that mechanism, so kelvin now lays -- but the placement still
        # routes DIRTY (GND + signal ratlines), so it remains a discriminating bad fixture.
        # Asserting kelvin_ok=False again would pin the SUPERSEDED tap behaviour.
        r = self.wg
        self.assertFalse(r["gate"], "widegap-m should route DIRTY")
        self.assertTrue(r["unconn_critical"])                 # safety/power nets left unrouted
        self.assertEqual(r["sort_key"][0], 1)                 # tier 1 = failing

    def test_invariant_gate_implies_real_route_clean(self):
        # the grader can never pass a board the real route fails -- TRUE BY CONSTRUCTION (it IS the route).
        for r in (self.n2, self.wg):
            self.assertEqual(r["gate"], bool(r["gates_pass"] and r["foreign_ok"]
                                             and r["thermal_ok"] and r["routing_complete"]))

    def test_proxy_vs_oracle_disagreement(self):
        # THE POINT: the cheap placement_proxy prefers widegap-m (tighter INA = LOWER hpwl), but that
        # tightness is exactly what breaks the Kelvin sense. The oracle, by routing, correctly demotes it.
        px_n2 = sp.placement_proxy(sp.read_placement(N2_PCB))
        px_wg = sp.placement_proxy(sp.read_placement(WIDEGAP_PCB))
        # cheap proxy: lower hpwl is "better" -> widegap-m ranks ABOVE n2
        self.assertLess(px_wg["hpwl"], px_n2["hpwl"],
                        "the proxy should prefer the tighter (dirty) parent")
        # oracle: n2 (gate-clean) ranks ABOVE widegap-m (dirty) -> the ORDER is INVERTED
        self.assertLess(self.n2["sort_key"], self.wg["sort_key"])
        # i.e. proxy-best != oracle-best on the same two placements
        proxy_best = min((N2_PCB, px_n2["hpwl"]), (WIDEGAP_PCB, px_wg["hpwl"]), key=lambda t: t[1])[0]
        oracle_best = N2_PCB if self.n2["sort_key"] < self.wg["sort_key"] else WIDEGAP_PCB
        self.assertNotEqual(proxy_best, oracle_best)


if __name__ == "__main__":
    unittest.main(verbosity=2)
