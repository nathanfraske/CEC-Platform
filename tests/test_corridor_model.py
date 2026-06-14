"""Phase 0 of the corridor-aware reseed placer (docs/placement-strategy-2026-06-14.md).

The falsifiable proof that the domain model SEES the eps-8pin ceiling before any placement
changes: build_corridor_model + corridor_cross_count must report >= 3 through-crossers on the
committed board (the /DETC1 /THRESH /I2C sandwich) AND /CAN_L must contribute 0 (it must not be
a false offender). corridor_cross_count is pure geometry -> exercised synthetically with no
pcbnew; the real-board proof + the two new checkers are pcbnew-gated (skip on a kicad-less box).
"""
import os
import sys
import unittest
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import cec_synth_pipeline as sp                                  # noqa: E402

try:
    import pcbnew                                                # noqa: F401
    HAVE_PCBNEW = True
except Exception:
    HAVE_PCBNEW = False

EPS_PCB = os.path.normpath(os.path.join(HERE, "..", "modules", "eps-8pin", "eps8pin-module.kicad_pcb"))


# --------------------------------------------------------------------------- pure geometry
class TestCorridorCrossPure(unittest.TestCase):
    """corridor_cross_count is pure geometry -- synthetic fixtures, runs everywhere."""

    def setUp(self):
        # cable-1 band x[10,20], cable-2 band x[34,47], both y[9,28] (the eps shape)
        self.bands = {"/SENSEC1": (10.0, 20.0, 9.0, 28.0), "/SENSEC2": (34.0, 47.0, 9.0, 28.0)}
        self.corridor = {"/SENSEC1_HI", "/SENSEC1_LO", "/SENSEC2_HI", "/SENSEC2_LO"}

    def _n(self, pbn):
        return sp.corridor_cross_count(pbn, self.bands, self.corridor)

    def test_through_cross_counts_one(self):
        # a pad left of band-2 (x22) and a pad right of it (x57) -> forced through band-2
        self.assertEqual(self._n({"/DETC1": [(22.0, 19.0), (57.0, 20.0)]}), 1)

    def test_clean_placement_zero(self):
        # both pads on the same side of every band -> corridor-clean
        self.assertEqual(self._n({"/DETC1": [(48.0, 19.0), (60.0, 20.0)]}), 0)

    def test_can_analog_right_of_bands_zero(self):
        # the /CAN_L shape (entirely right of both bands) must NOT be a false offender
        self.assertEqual(self._n({"/CAN_L": [(62.5, 11.7), (89.5, 12.6)]}), 0)

    def test_edge_terminating_not_a_through_cross(self):
        # one pad INSIDE band-2 (x45), one right (x57): originates at the band edge, not through it
        self.assertEqual(self._n({"/DETC2": [(45.0, 19.0), (57.0, 20.0)]}), 0)

    def test_y_disjoint_not_counted(self):
        # x straddles band-2 but the net runs in a y-band clear of it -> no cross
        self.assertEqual(self._n({"/SIG": [(22.0, 30.0), (57.0, 31.0)]}), 0)

    def test_corridor_power_sense_excluded(self):
        pbn = {"/SENSEC1_HI": [(5.0, 19.0), (55.0, 20.0)],   # the corridor's own force net
               "/+3V3": [(5.0, 19.0), (55.0, 20.0)],         # a power rail
               "GND": [(5.0, 19.0), (55.0, 20.0)],
               "/SENSEC2_LO": [(5.0, 19.0), (55.0, 20.0)]}
        self.assertEqual(self._n(pbn), 0)

    def test_spans_both_bands_counts_two(self):
        # an I2C-shaped net crossing band-1 AND band-2
        self.assertEqual(self._n({"/I2C_SCL": [(5.0, 19.0), (73.0, 20.0)]}), 2)

    def test_three_bands_pcie_shaped(self):
        # a 3-cable (PCIe) board: a net spanning all three bands counts 3
        bands = {"/SENSEC1": (10.0, 20.0, 9.0, 28.0), "/SENSEC2": (34.0, 47.0, 9.0, 28.0),
                 "/SENSEC3": (60.0, 75.0, 9.0, 28.0)}
        corridor = {"/SENSEC%d_%s" % (i, s) for i in (1, 2, 3) for s in ("HI", "LO")}
        self.assertEqual(sp.corridor_cross_count({"/N": [(5.0, 19.0), (80.0, 20.0)]}, bands, corridor), 3)

    def test_degenerate_band_skipped_with_board_w(self):
        # a near-board-wide band (corridor not formed) is NOT counted -> no false clean/cross.
        # (a net must reach OUTSIDE the 73mm band on both sides to straddle it at all -- which is
        # itself why a wide band is meaningless; the guard makes that explicit.)
        wide = {"/SENSEC1": (3.0, 76.0, 9.0, 28.0)}            # 73mm on a 96mm board
        net = {"/N": [(1.0, 19.0), (90.0, 20.0)]}
        self.assertEqual(sp.corridor_cross_count(net, wide, set()), 1)              # no guard: counts
        self.assertEqual(sp.corridor_cross_count(net, wide, set(), board_w=96.0), 0)  # guard: skipped

    def test_build_model_no_kelvin_empty(self):
        # a board with no Kelvin pair -> empty model, no crash (Hub boards)
        nl = sp.Netlist(comps={"U1": sp.Comp(ref="U1", value="ESP32", footprint="x:y")},
                        nets={"/GND": [("U1", "1")], "/+3V3": [("U1", "2")]})
        model = sp.build_corridor_model(nl, {"U1": (0.0, 0.0, 0.0)}, {"U1": "x:y"}, board_w=50.0)
        self.assertEqual(model.cables, [])
        self.assertEqual(model.bands, {})

    def test_single_pad_net_skipped(self):
        self.assertEqual(self._n({"/ONEPAD": [(22.0, 19.0)]}), 0)

    def test_net_role_classification(self):
        self.assertEqual(sp._corridor_net_role("/SENSEC1_HI", self.corridor), "power_corridor")
        self.assertEqual(sp._corridor_net_role("/+3V3", self.corridor), "decouple")
        self.assertEqual(sp._corridor_net_role("GND", self.corridor), "decouple")
        self.assertEqual(sp._corridor_net_role("/SENSEC2_LO", self.corridor), "power_corridor")
        # a sense pair NOT in this board's corridor set still classifies as sense (not signal)
        self.assertEqual(sp._corridor_net_role("/SENSEC9_LO", self.corridor), "sense")
        self.assertEqual(sp._corridor_net_role("/DETC1", self.corridor), "signal")


# --------------------------------------------------------------------------- helpers (pcbnew)
def _board_nl(path):
    """Build a synth Netlist + placement P + comps map straight off a .kicad_pcb (pcbnew),
    so build_corridor_model can run on the committed board with no kicad-cli export."""
    b = pcbnew.LoadBoard(path)
    comps, nets, P = {}, defaultdict(list), {}
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        libid = fp.GetFPIDAsString()
        comps[ref] = sp.Comp(ref=ref, value=fp.GetValue(), footprint=libid)
        pos = fp.GetPosition()
        P[ref] = (pos.x / 1e6, pos.y / 1e6, fp.GetOrientationDegrees())
        for pad in fp.Pads():
            nn = pad.GetNetname()
            if nn:
                nets[nn].append((ref, pad.GetPadName()))
    nl = sp.Netlist(comps=comps, nets=dict(nets))
    return nl, P, {r: c.footprint for r, c in comps.items()}


def _board_pads_by_net(path):
    b = pcbnew.LoadBoard(path)
    d = defaultdict(list)
    for fp in b.GetFootprints():
        for pad in fp.Pads():
            nn = pad.GetNetname()
            if nn:
                p = pad.GetPosition()
                d[nn].append((p.x / 1e6, p.y / 1e6))
    return dict(d)


# --------------------------------------------------------------------------- the real-board proof
@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(EPS_PCB),
                     "pcbnew + the committed eps-8pin board required")
class TestCorridorModelEps(unittest.TestCase):
    """The Phase-0 falsifiable proof on the committed eps-8pin floorplan."""

    BOARD_W = 96.0

    @classmethod
    def setUpClass(cls):
        cls.nl, cls.P, cls.comps = _board_nl(EPS_PCB)
        cls.model = sp.build_corridor_model(cls.nl, cls.P, cls.comps, board_w=cls.BOARD_W)
        cls.pbn = _board_pads_by_net(EPS_PCB)
        cls.crossings = sp.corridor_cross_count(cls.pbn, cls.model.bands, cls.model.corridor_nets,
                                                board_w=cls.BOARD_W)

    def _cc(self, pbn):
        return sp.corridor_cross_count(pbn, self.model.bands, self.model.corridor_nets,
                                       board_w=self.BOARD_W)

    def test_two_cables_resolved(self):
        self.assertEqual(len(self.model.cables), 2)
        for cab in self.model.cables:
            self.assertTrue(cab.shunt.upper().startswith("RS"), "shunt: %r" % cab.shunt)
            self.assertTrue(cab.sense_ics, "no sense IC on %s" % cab.base)

    def test_committed_corridors_are_formed(self):
        # the committed board has inline shunts + aligned connectors -> tight, FORMED bands
        for cab in self.model.cables:
            self.assertTrue(cab.formed, "%s band should be formed (tight column)" % cab.base)
            self.assertLess(cab.band[1] - cab.band[0], 0.55 * self.BOARD_W)

    def test_band2_covers_the_sandwich(self):
        # connector+shunt band (INA pads excluded): x ~ [32.5,48.1] y ~ [9.5,27.5]
        x0, x1, y0, y1 = self.model.bands["/SENSEC2"]
        self.assertLess(x0, 36.0)
        self.assertGreater(x1, 45.0)
        self.assertLessEqual(y0, 15.0)
        self.assertGreaterEqual(y1, 26.0)

    def test_through_crossers_match_the_known_ceiling(self):
        # the real ceiling on the committed board: /DETC1 + /THRESH + /I2C_SCL(x2) + /I2C_SDA(x2) = 6
        # (band,net) pairs. >=5 keeps headroom if the board is lightly re-placed; the companion
        # offender + false-positive tests pin the exact set.
        self.assertGreaterEqual(self.crossings, 5,
                                "model must see the real corridor crossings; got %d" % self.crossings)

    def test_can_contributes_zero(self):
        self.assertEqual(self._cc({k: v for k, v in self.pbn.items() if k == "/CAN_L"}), 0,
                         "/CAN_L must NOT be a false corridor offender")

    def test_known_offenders(self):
        # the named through-crossers; /I2C_* dominate (cross both bands) and must not be missed
        for net in ("/DETC1", "/THRESH", "/I2C_SCL", "/I2C_SDA"):
            self.assertGreaterEqual(self._cc({net: self.pbn[net]}), 1,
                                    "%s should be a through-crosser on the committed board" % net)


# --------------------------------------------------------------------------- the two new checkers
@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(EPS_PCB),
                     "pcbnew + the committed eps-8pin board required")
class TestCorridorCheckers(unittest.TestCase):
    """The discover->ratify->enforce close: the two registry entries now have real checkers."""

    @classmethod
    def setUpClass(cls):
        import cec_constraints
        cls.cc = cec_constraints
        cls.board = pcbnew.LoadBoard(EPS_PCB)

    def _run(self, cid):
        return self.cc.CHECKERS[cid](self.board, EPS_PCB, {})[:2]

    def test_both_registered(self):
        for cid in ("shunt-inline-in-corridor", "high-current-corridor-keepout"):
            self.assertIn(cid, self.cc.CHECKERS, "%s has no checker" % cid)

    def test_shunt_inline_passes_on_committed_board(self):
        ok, detail = self._run("shunt-inline-in-corridor")
        self.assertTrue(ok, "committed eps shunts are inline by design: %s" % detail)

    def test_corridor_keepout_na_on_floorplan(self):
        # 0 tracks -> the route-time keepout N/A's (it has teeth only on a routed board)
        ok, detail = self._run("high-current-corridor-keepout")
        self.assertIsNone(ok, "keepout is a route-time check on a floorplan: %s" % detail)

    def test_corridor_keepout_has_teeth(self):
        # inject a foreign /DETC1 track running THROUGH band-2 -> the checker must FAIL it
        b = pcbnew.LoadBoard(EPS_PCB)
        det = b.FindNet("/DETC1")
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(30_000_000, 20_000_000))
        t.SetEnd(pcbnew.VECTOR2I(50_000_000, 20_000_000))
        t.SetWidth(200_000)
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(det)
        b.Add(t)
        res = self.cc.CHECKERS["high-current-corridor-keepout"](b, EPS_PCB, {})
        self.assertFalse(res[0], "foreign track in the corridor must FAIL: %s" % res[1])
        self.assertIn("/DETC1", res[1])

    def test_corridor_keepout_via_teeth(self):
        # the VIA code path: a foreign /DETC1 via INSIDE band-2 must FAIL (distinct from the track path)
        b = pcbnew.LoadBoard(EPS_PCB)
        det = b.FindNet("/DETC1")
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(40_000_000, 18_000_000))   # inside band-2 (x~[32,48] y~[9,28])
        v.SetDrill(300_000)
        v.SetWidth(600_000)
        v.SetNet(det)
        b.Add(v)
        res = self.cc.CHECKERS["high-current-corridor-keepout"](b, EPS_PCB, {})
        self.assertFalse(res[0], "foreign via in the corridor must FAIL: %s" % res[1])

    def test_shunt_inline_fail_teeth(self):
        # move a shunt far off the J_IN->J_OUT axis -> the checker must FAIL it
        b = pcbnew.LoadBoard(EPS_PCB)
        rs1 = b.FindFootprintByReference("RS1")
        rs1.SetPosition(pcbnew.VECTOR2I(7_500_000, 17_500_000))   # x=7.5, far left of the connectors
        res = self.cc.CHECKERS["shunt-inline-in-corridor"](b, EPS_PCB, {})
        self.assertFalse(res[0], "an off-axis shunt must FAIL the inline check: %s" % res[1])
        self.assertIn("RS1", res[1])

    def test_shared_bus_boards_na(self):
        # 12VHPWR / 24-pin share J3/J4 across pairs -> the per-cable checkers must N/A, never false-FAIL
        for rel in ("12vhpwr-standard/12vhpwr-standard-module.kicad_pcb",
                    "atx-24pin/atx24pin-module.kicad_pcb"):
            p = os.path.normpath(os.path.join(HERE, "..", "modules", rel))
            if not os.path.isfile(p):
                continue
            board = pcbnew.LoadBoard(p)
            for cid in ("shunt-inline-in-corridor", "high-current-corridor-keepout"):
                ok = self.cc.CHECKERS[cid](board, p, {})[0]
                self.assertIsNone(ok, "%s on %s must be N/A (shared-bus), got %r" % (cid, rel, ok))

    def test_registry_entries_marked_checkable(self):
        by_id = {c.id: c for c in self.cc.REGISTRY}
        for cid in ("shunt-inline-in-corridor", "high-current-corridor-keepout"):
            self.assertEqual(by_id[cid].checkable, "yes")


# --------------------------------------------------------------------------- Phase 1: ranking
class TestCorridorRanking(unittest.TestCase):
    """Phase 1's load-bearing lever: corridor_cross is the PRIMARY rank key after legality, so a
    corridor-clean placement beats a lower-HPWL sandwich. Pure -- synthetic Candidates."""

    def _cand(self, tag, residual, cc, hpwl):
        return sp.Candidate(strat=tag, seed=0, P={}, W=96.0, H=37.0, residual=residual,
                            proxy={"hpwl": hpwl, "corridor_cross": cc}, corridor_cross=cc)

    def _rank(self, cands):
        return sorted(cands, key=lambda c: (c.residual, c.corridor_cross, c.proxy["hpwl"]))

    def test_corridor_clean_beats_lower_hpwl_sandwich(self):
        clean = self._cand("clean", 2, 0, 1900.0)      # corridor-clean, but higher HPWL
        sandwich = self._cand("cross", 2, 4, 1639.0)   # lower HPWL, but crosses 4 corridors
        self.assertIs(self._rank([sandwich, clean])[0], clean)

    def test_residual_still_dominates_corridor(self):
        # legality first: a residual-2 crossing beats a residual-5 clean (an illegal board is worse)
        low_res_cross = self._cand("legal", 2, 8, 1700.0)
        high_res_clean = self._cand("illegal", 5, 0, 1700.0)
        self.assertIs(self._rank([high_res_clean, low_res_cross])[0], low_res_cross)

    def test_hpwl_breaks_corridor_ties(self):
        a = self._cand("a", 2, 0, 1800.0)
        b = self._cand("b", 2, 0, 1700.0)
        self.assertIs(self._rank([a, b])[0], b)

    def test_proxy_reject_corridor_opt_in(self):
        proxy = {"rudy_peak": 1.0, "thermal_peak_w": 0.1, "corridor_cross": 3}
        self.assertFalse(sp.proxy_reject(proxy)[0])                       # OFF by default -> no reject
        rej, why = sp.proxy_reject(proxy, corridor_max=0)
        self.assertTrue(rej)                                             # opt-in rejects a crosser
        self.assertTrue(any("corridor_cross" in r for r in why))
        self.assertFalse(sp.proxy_reject({**proxy, "corridor_cross": 0}, corridor_max=0)[0])


# --------------------------------------------------------------------------- Phase 1: the placer
def _have_kicad_cli():
    import shutil
    return shutil.which("kicad-cli") is not None


@unittest.skipUnless(HAVE_PCBNEW and _have_kicad_cli() and os.path.isfile(EPS_PCB),
                     "pcbnew + kicad-cli + the eps-8pin board required")
class TestPlacerCorridorEps(unittest.TestCase):
    """Phase 2 FORMS the per-cable corridors (spine seed: align J_OUT under J_IN, shunt on the cable
    axis at rot270), so build_corridor_model reports formed bands and corridor_cross is MEANINGFUL on
    synth output (Phase 1a left it inert). NOTE: a formed corridor is not yet corridor-CLEAN -- driving
    cc down is the open Phase-2/3 work. synth_one is process-deterministic per (strat, seed)."""

    @classmethod
    def setUpClass(cls):
        cls.cfg = sp.Config.load("eps-8pin")
        cls.cd = {k: getattr(cls.cfg, k) for k in ("board", "profile", "pins", "params",
                                                   "dir", "sch", "net", "pcb", "bom_csv")}

    def _cand(self, strat, seed):
        return sp.synth_one(self.cd, 96.0, 37.0, strat, seed)

    def test_phase2_forms_the_corridors(self):
        # Phase 2: the spine seed makes each per-cable corridor FORMED (tight band) and seats the
        # shunt on the cable axis at rot270 (H3) -- so corridor_cross is now MEANINGFUL, not inert.
        cand = self._cand("thermal_separated", 7)
        nl = sp.View(self.cfg).nl
        model = sp.build_corridor_model(nl, cand.P, sp._fp_of(nl), board_w=cand.W)
        self.assertEqual(len(model.cables), 2)
        for cab in model.cables:
            self.assertTrue(cab.formed, "%s corridor must be FORMED after the spine seed" % cab.base)
            self.assertEqual(cand.P[cab.shunt][2], 270.0, "shunt %s must be seated rot270" % cab.shunt)

    def test_synth_one_process_deterministic(self):
        # the sorted-iteration fix: corridor_cross is stable for a given (strat, seed)
        a = self._cand("compact", 6).corridor_cross
        b = self._cand("compact", 6).corridor_cross
        self.assertEqual(a, b)

    def test_place_candidates_uses_production_sort_key(self):
        # NOT a shadow re-implementation: call the real place_candidates and assert its output IS
        # ordered by the production key, so a drift in the sort key is caught here.
        cands = sp.place_candidates(self.cfg, 96.0, 37.0,
                                    strategies=("thermal_separated", "compact"), seeds=(0, 1),
                                    max_workers=1)
        keys = [(c.residual, c.corridor_cross, c.proxy["hpwl"]) for c in cands]
        self.assertEqual(keys, sorted(keys))

    def test_stored_corridor_cross_matches_recompute(self):
        # the Candidate.corridor_cross attached by synth_one must equal an independent recompute
        # from its placement P (the stored rank key is honest, not stale)
        cand = self._cand("thermal_separated", 7)
        nl = sp.View(self.cfg).nl
        comps = sp._fp_of(nl)
        obj = sp._placement_obj(self.cfg, cand.P, cand.W, cand.H, sp._part_halfext(nl), nl)
        model = sp.build_corridor_model(nl, cand.P, comps, board_w=cand.W)
        cc = sp.corridor_cross_count(obj.pads_by_net, model.bands, model.corridor_nets,
                                     board_w=cand.W)
        self.assertEqual(cc, cand.corridor_cross)


if __name__ == "__main__":
    unittest.main()
