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

# LEGACY fixture: the pre-beta committed board this suite's geometry assertions encode
# (the live beta/eps-8pin is the beta TB-blade board; see tests/fixtures/.../README.md).
EPS_PCB = os.path.normpath(os.path.join(HERE, "..", "tests", "fixtures", "eps-8pin-legacy", "eps8pin-module.kicad_pcb"))


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

    def test_shared_bus_connectors_detected(self):
        # one connector J3 serving BOTH Kelvin pairs -> shared-bus -> excluded from the model + topology
        nl = sp.Netlist(comps={}, nets={
            "/SENSEC1_HI": [("J3", "1")], "/SENSEC1_LO": [("J3", "2"), ("RS1", "1")],
            "/SENSEC2_HI": [("J3", "3")], "/SENSEC2_LO": [("J3", "4"), ("RS2", "1")]})
        self.assertIn("J3", sp._shared_bus_connectors(nl))
        # build_corridor_model must SKIP the shared-bus pairs (rank key inert, not spurious)
        model = sp.build_corridor_model(nl, {}, {}, board_w=58.0)
        self.assertEqual(model.cables, [])
        self.assertEqual(sp._cable_topology(nl), [])

    def test_corridor_veto(self):
        # §2.2 H1: a SENSITIVE body may not enter a FOREIGN formed band; the paired INA is exempt for
        # its OWN band; a non-sensitive part is never vetoed; an unformed band never vetoes.
        bands = {"/SENSEC1": {"band": (10.0, 20.0, 5.0, 30.0), "formed": True},
                 "/SENSEC2": {"band": (40.0, 50.0, 5.0, 30.0), "formed": True}}
        sensitive = {"U10", "U11", "U1"}
        paired = {"/SENSEC1": {"U10"}, "/SENSEC2": {"U11"}}
        # U10 (cable-1 INA) inside cable-2's foreign band -> vetoed
        self.assertTrue(sp._corridor_veto("U10", (45.0, 15.0), bands, sensitive, paired))
        # U10 inside its OWN band (cable 1) -> exempt
        self.assertFalse(sp._corridor_veto("U10", (15.0, 15.0), bands, sensitive, paired))
        # the ESP (sensitive, paired to neither) in any band -> vetoed
        self.assertTrue(sp._corridor_veto("U1", (15.0, 15.0), bands, sensitive, paired))
        # a non-sensitive part (a connector) is never vetoed
        self.assertFalse(sp._corridor_veto("J_OUT1", (15.0, 15.0), bands, sensitive, paired))
        # an UNFORMED band never vetoes
        unformed = {"/SENSEC1": {"band": (10.0, 20.0, 5.0, 30.0), "formed": False}}
        self.assertFalse(sp._corridor_veto("U1", (15.0, 15.0), unformed, sensitive, {}))

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
        checked = 0
        # 12vhpwr-standard lives in beta/ since the 2026-07-22 physical move;
        # atx-24pin is the alpha board and stays under modules/.
        for root, rel in (("beta", "12vhpwr-standard/12vhpwr-standard-module.kicad_pcb"),
                          ("modules", "atx-24pin/24pin-module.kicad_pcb")):
            p = os.path.normpath(os.path.join(HERE, "..", root, rel))
            if not os.path.isfile(p):
                continue
            checked += 1
            board = pcbnew.LoadBoard(p)
            for cid in ("shunt-inline-in-corridor", "high-current-corridor-keepout"):
                ok = self.cc.CHECKERS[cid](board, p, {})[0]
                self.assertIsNone(ok, "%s on %s must be N/A (shared-bus), got %r" % (cid, rel, ok))
        # guard against a silent skip from a wrong path (the audit found atx24pin-module was a typo)
        self.assertGreaterEqual(checked, 2, "both shared-bus boards must exist and be exercised")

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
        cls.cfg = sp.Config.load(os.path.normpath(os.path.join(HERE, "..", "tests", "fixtures", "eps-8pin-legacy")))
        cls.cd = {k: getattr(cls.cfg, k) for k in ("board", "profile", "pins", "params",
                                                   "dir", "sch", "net", "pcb", "bom_csv")}

    def _cand(self, strat, seed):
        return sp.synth_one(self.cd, 96.0, 37.0, strat, seed)

    def test_phase2_forms_the_corridors(self):
        # Phase 2: the spine seed makes each per-cable corridor FORMED + TIGHT (one connector width)
        # and seats the shunt on the cable axis at rot270 (H3). The band-width assert guards against a
        # centroid-alignment regression (origin-aligned columns give ~28mm, the real spine ~15.6mm).
        cand = self._cand("thermal_separated", 7)
        nl = sp.View(self.cfg).nl
        model = sp.build_corridor_model(nl, cand.P, sp._fp_of(nl), board_w=cand.W)
        self.assertEqual(len(model.cables), 2)
        for cab in model.cables:
            self.assertTrue(cab.formed, "%s corridor must be FORMED after the spine seed" % cab.base)
            self.assertLess(cab.band[1] - cab.band[0], 20.0,
                            "%s band must be a tight column (pad-centroid aligned)" % cab.base)
            self.assertEqual(cand.P[cab.shunt][2], 270.0, "shunt %s must be seated rot270" % cab.shunt)

    def test_phase2_default_placement_is_legal(self):
        # the overhang default (power_able) frees the mid-board -> a DRC-legal (residual 0) placement
        # exists; assert residual==0 alongside 'formed' so a geometrically illegal corridor can't pass.
        cands = sp.place_candidates(self.cfg, 96.0, 37.0,
                                    strategies=("thermal_separated", "dataflow", "compact"),
                                    seeds=(0, 3), max_workers=1)
        self.assertEqual(cands[0].residual, 0,
                         "best candidate must be DRC-legal (residual 0) with overhang default")

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
        # assert against the REAL production key (residual, cc_aware, cc, proxy_score) -- the earlier
        # (residual, cc, hpwl) proxy silently dropped corridor_cross_aware (the true 2nd key), so a
        # candidate that ties on cc but differs on cc_aware looked mis-sorted when it was correct.
        keys = [sp._candidate_sort_key(c) for c in cands]
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


# --------------------------------------------------------------------------- the corridor LEVER
@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(EPS_PCB),
                     "pcbnew + the committed eps-8pin board required")
class TestCorridorLever(unittest.TestCase):
    """The PLACEMENT corridor lever (the analogue of the routing corridor-avoid): a SENSITIVE body in
    a foreign formed band is detected (corridor_violations), evicted (cec_place.apply_corridor_evict),
    and proposed by the routing-tier manager (cec_router.corridor_evict_repair)."""

    def _board_with_violation(self):
        # move U10 (cable-1 INA -- a sense IC) into cable-2's band -> a foreign-band violation
        b = pcbnew.LoadBoard(EPS_PCB)
        b.FindFootprintByReference("U10").SetPosition(pcbnew.VECTOR2I(40_000_000, 18_000_000))
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), "eps-violation.kicad_pcb")
        pcbnew.SaveBoard(p, b)
        return p

    def _board_with_movable_violation(self):
        # move U1 (ESP -- a SENSITIVE but NON-sense, MOVABLE body) into cable-2's band
        b = pcbnew.LoadBoard(EPS_PCB)
        b.FindFootprintByReference("U1").SetPosition(pcbnew.VECTOR2I(40_000_000, 18_000_000))
        import tempfile
        p = os.path.join(tempfile.mkdtemp(), "eps-movable-violation.kicad_pcb")
        pcbnew.SaveBoard(p, b)
        return p

    def test_violation_detected(self):
        p = self._board_with_violation()
        viols = sp.corridor_violations(p)
        self.assertTrue(any(v["ref"] == "U10" and v["base"] == "/SENSEC2" for v in viols),
                        "U10 inside cable-2's band must be a corridor violation")

    def test_paired_ina_not_flagged(self):
        # the committed board: each INA is in its OWN band (exempt) -> no violation
        self.assertEqual(sp.corridor_violations(EPS_PCB), [])

    def test_shared_bus_board_no_violations(self):
        p = os.path.normpath(os.path.join(HERE, "..", "modules", "atx-24pin", "24pin-module.kicad_pcb"))
        if os.path.isfile(p):
            self.assertEqual(sp.corridor_violations(p), [])   # no per-cable corridor -> nothing to evict

    def test_evict_clears_the_violation(self):
        import cec_place
        p = self._board_with_violation()
        v = sp.corridor_violations(p)[0]
        b = pcbnew.LoadBoard(p)
        mv = cec_place.apply_corridor_evict(b, v["ref"], v["band"])
        pcbnew.SaveBoard(p, b)
        self.assertTrue(mv["out"])
        self.assertIn("U10", mv["moved_refs"])
        self.assertEqual(sp.corridor_violations(p), [])       # evicted -> clean

    def test_manager_repair_emits_place_cluster(self):
        # PL-03: the manager tier emits a CLUSTER-aware place_cluster for a MOVABLE sensitive body (the
        # ESP) -- was the cap-blind place_nudge. FENCE-01: the edit carries the resolved fence.
        import cec_router
        p = self._board_with_movable_violation()
        rep = cec_router.corridor_evict_repair(p)
        self.assertIsNotNone(rep)
        self.assertEqual(rep["type"], "place_cluster")
        self.assertEqual(rep["ref"], "U1")
        self.assertTrue(rep["cluster"])
        self.assertIn("band", rep)
        self.assertIn("fence", rep)                         # FENCE-01: the resolved fence rides the edit

    def test_manager_repair_refuses_fenced_sense_ic(self):
        # FENCE-01 / TEST-RIGOR-01: a LOCKED Kelvin/§6.13 sense IC (U10) inside a foreign band is NEVER
        # evicted by the manager tier (the §6.8 geometry is a placement-tier/human decision, not a router
        # repair). This is the missing tooth that let FENCE-01 ship.
        import cec_router
        p = self._board_with_violation()                    # moves U10 (a sense IC) into cable-2's band
        self.assertTrue(any(v["ref"] == "U10" for v in sp.corridor_violations(p)))   # it IS a violation
        self.assertIsNone(cec_router.corridor_evict_repair(p))                        # but the manager refuses it

    def test_manager_repair_honors_explicit_fence(self):
        # FENCE-01: an explicit caller fence is also respected (a movable ESP fenced by the caller -> skip).
        import cec_router
        p = self._board_with_movable_violation()
        self.assertIsNone(cec_router.corridor_evict_repair(p, fence={"refs": {"U1"}}))

    def test_manager_repair_skips_structural_ref(self):
        # PL-03 fence: the manager must never propose evicting a band-defining shunt RS*/connector J*.
        import cec_router, cec_synth_pipeline as sp2
        orig = sp2.corridor_violations
        sp2.corridor_violations = lambda bp: [{"ref": "RS1", "band": (0, 1, 0, 1), "base": "/SENSEC1"}]
        try:
            self.assertIsNone(cec_router.corridor_evict_repair("ignored"))   # returns before any pcbnew
        finally:
            sp2.corridor_violations = orig

    def test_evict_restore_record_roundtrips(self):
        # PL-06: apply_corridor_evict returns a `restore` record; restore_poses puts the body + its
        # cluster back byte-exact (pos + rot), so the violation reappears (reversible).
        import cec_place
        p = self._board_with_violation()
        b = pcbnew.LoadBoard(p)
        pre = {r: (b.FindFootprintByReference(r).GetPosition().x,
                   b.FindFootprintByReference(r).GetPosition().y) for r in ("U10",)}
        mv = cec_place.apply_corridor_evict(b, "U10", sp.corridor_violations(p)[0]["band"])
        self.assertIn("restore", mv)
        self.assertNotEqual(b.FindFootprintByReference("U10").GetPosition().x, pre["U10"][0])  # moved
        n = cec_place.restore_poses(b, mv["restore"])
        self.assertEqual(n, len(mv["moved_refs"]))
        self.assertEqual(b.FindFootprintByReference("U10").GetPosition().x, pre["U10"][0])      # byte-exact back
        self.assertEqual(b.FindFootprintByReference("U10").GetPosition().y, pre["U10"][1])

    def test_evict_fence_refuses_pinned_ref(self):
        # PL-04: a fenced ref is refused AT THE LEVER (defense-in-depth), even when in-band.
        import cec_place
        b = pcbnew.LoadBoard(EPS_PCB)
        b.FindFootprintByReference("U10").SetPosition(pcbnew.VECTOR2I(40_000_000, 18_000_000))
        self.assertIsNone(cec_place.apply_corridor_evict(b, "U10", (34.0, 48.0, 9.5, 27.5),
                                                         fence={"refs": {"U10"}}))

    def test_evict_moved_refs_sorted(self):
        # PL-03: the carried cluster is in deterministic (sorted-ref) order.
        import cec_place
        b = pcbnew.LoadBoard(EPS_PCB)
        b.FindFootprintByReference("U10").SetPosition(pcbnew.VECTOR2I(40_000_000, 18_000_000))
        mv = cec_place.apply_corridor_evict(b, "U10", (34.0, 48.0, 9.5, 27.5))
        self.assertEqual(mv["moved_refs"][1:], sorted(mv["moved_refs"][1:]))

    def test_evict_in_movable_set(self):
        import cec_place
        self.assertIn("evict", cec_place.MOVABLE)

    def test_evict_containment_guard_and_no_shunt_drag(self):
        # panel G1: a stale directive whose part is NOT in the band must NO-OP (not shove it back in
        # and drag the corridor shunt); a real eviction must never carry a structural RS*/J* part.
        import cec_place
        b = pcbnew.LoadBoard(EPS_PCB)
        rs1 = b.FindFootprintByReference("RS1").GetPosition().x
        # U10 is in its OWN cable-1 band on the committed board -> NOT in the cable-2 band below
        self.assertIsNone(cec_place.apply_corridor_evict(b, "U10", (34.0, 48.0, 9.5, 27.5)))
        self.assertEqual(rs1, b.FindFootprintByReference("RS1").GetPosition().x, "shunt must not move")
        # a genuine in-band eviction carries no structural part
        b.FindFootprintByReference("U10").SetPosition(pcbnew.VECTOR2I(40_000_000, 18_000_000))
        mv = cec_place.apply_corridor_evict(b, "U10", (34.0, 48.0, 9.5, 27.5))
        self.assertTrue(all(not r.upper().startswith(("RS", "J")) for r in mv["moved_refs"]))


# --------------------------------------------------------------------------- the dedup'd eviction math
@unittest.skipUnless(HAVE_PCBNEW, "cec_place imports pcbnew at module load")
class TestNearestEvictDelta(unittest.TestCase):
    """PL-03: the ONE canonical eviction displacement, regression-pinned to the former inline router
    math so apply_corridor_evict (loop tier) and corridor_evict_repair (manager tier) cannot drift."""

    def _old_inline(self, cx, cy, band, margin=1.5):
        x0, x1, y0, y1 = band
        dl, dr, du, dd = cx - x0, x1 - cx, cy - y0, y1 - cy
        m = min(dl, dr, du, dd)
        return ((-(dl + margin), 0.0) if m == dl else (dr + margin, 0.0) if m == dr
                else (0.0, -(du + margin)) if m == du else (0.0, dd + margin))

    def test_matches_old_inline_math(self):
        import cec_place
        band = (10.0, 20.0, 10.0, 20.0)
        for cx, cy in [(11, 15), (19, 15), (15, 11), (15, 19),     # four edges
                       (11, 11), (12, 13), (18, 11), (13, 18)]:    # diagonals + ties
            self.assertEqual(cec_place.nearest_evict_delta(cx, cy, band),
                             self._old_inline(cx, cy, band), (cx, cy))

    def test_edge_cases_and_determinism(self):
        # DETERMINISM-01: board-boundary band, near-corner, extreme coords -- all match the old math, and
        # repeated calls are bit-identical (the eviction geometry Invariant 6 relies on).
        import cec_place
        cases = [(0.05, 1.0, (0.0, 10.0, 0.0, 10.0)),          # band at the board boundary x0=0
                 (0.001, 0.001, (0.0, 50.0, 0.0, 50.0)),       # sub-0.1mm from a corner
                 (123.4, 567.8, (100.0, 200.0, 500.0, 600.0))] # extreme coordinates
        for cx, cy, band in cases:
            want = self._old_inline(cx, cy, band)
            results = {cec_place.nearest_evict_delta(cx, cy, band) for _ in range(8)}
            self.assertEqual(len(results), 1, (cx, cy, band))   # bit-identical across calls
            self.assertEqual(results.pop(), want, (cx, cy, band))


# --------------------------------------------------------------------------- the LAYER lever
@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(EPS_PCB),
                     "pcbnew + the committed eps-8pin board required")
class TestLayerLever(unittest.TestCase):
    """The route-time LAYER-TIER lever (cec_fr.stagger_corridor_crossings): foreign signals that must
    cross a high-current corridor are staggered across F.Cu/B.Cu so the un-cut outer pour mirror carries."""

    def _board_with_two_crossings(self):
        import tempfile
        b = pcbnew.LoadBoard(EPS_PCB)
        for net, y in (("/DETC1", 18.0), ("/THRESH", 20.0)):     # both on F.Cu across band-2
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(30_000_000, int(y * 1e6)))
            t.SetEnd(pcbnew.VECTOR2I(50_000_000, int(y * 1e6)))
            t.SetWidth(200_000); t.SetLayer(pcbnew.F_Cu); t.SetNetCode(b.FindNet(net).GetNetCode())
            b.Add(t)
        p = os.path.join(tempfile.mkdtemp(), "eps-cross.kicad_pcb")
        pcbnew.SaveBoard(p, b)
        return p

    def test_staggers_across_f_and_b(self):
        import cec_fr
        p = self._board_with_two_crossings()
        rep = cec_fr.stagger_corridor_crossings(p, verify=False)
        self.assertEqual(rep["flipped"], 1)                      # 2 crossings -> 1 stays F, 1 -> B
        self.assertEqual(rep["vias_added"], 2)                   # transition vias at both band edges
        layers = {}
        bb = pcbnew.LoadBoard(p)
        for t in bb.GetTracks():
            if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() in ("/DETC1", "/THRESH"):
                layers.setdefault(t.GetNetname(), set()).add(t.GetLayer())
        self.assertIn(pcbnew.B_Cu, layers["/THRESH"])            # the 2nd crossing now uses B.Cu

    def test_mirror_pour_is_additive_and_passes_the_adoption_guard(self):
        """Item 1: the loop poured the force nets F.Cu-only, so the stagger lever's mirror premise was
        false. synthesize_power_copper(strip_redundant=False) lays the B.Cu mirror + via stitching, purely
        ADDITIVELY (no copper removed), and _route_quality must not regress -- the guard the route uses to
        adopt the mirrored board."""
        import tempfile
        import cec_fr
        wd = tempfile.mkdtemp()
        # build the F.Cu-only poured board the loop's import_ses produces
        b = pcbnew.LoadBoard(EPS_PCB)
        pours = cec_fr.derive_power_pours(EPS_PCB, board=b)
        self.assertEqual(len(pours), 4)                          # 2 cables x (HI, LO)
        cec_fr.add_power_pours(b, pours, fill=True)
        routed = os.path.join(wd, "routed.kicad_pcb"); pcbnew.SaveBoard(routed, b)
        b0 = pcbnew.LoadBoard(routed)
        force_tracks0 = sum(1 for t in b0.GetTracks()
                            if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname().startswith("/SENSEC"))
        del b, b0
        mirrored = os.path.join(wd, "mirror.kicad_pcb")
        rep = cec_fr.synthesize_power_copper(routed, mirrored, strip_redundant=False)
        self.assertEqual(rep["mirror_pours"], 4)                 # the 4 missing B.Cu pours
        self.assertGreater(rep["via_field"], 0)                  # F<->B stitching
        self.assertEqual(rep["stripped_force_traces"], 0)        # additive -- nothing removed
        bm = pcbnew.LoadBoard(mirrored)
        bcu = sum(1 for z in bm.Zones()
                  if z.IsOnLayer(bm.GetLayerID("B.Cu")) and z.GetNetname().startswith("/SENSEC"))
        force_tracks1 = sum(1 for t in bm.GetTracks()
                            if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname().startswith("/SENSEC"))
        self.assertEqual(bcu, 4)                                 # B.Cu mirror present for each force net
        self.assertGreaterEqual(force_tracks1, force_tracks0)    # additive: force copper never decreased
        del bm
        # the adoption guard: a purely additive mirror must not regress route quality
        import math
        q_routed, q_mirror = cec_fr._route_quality(routed), cec_fr._route_quality(mirrored)
        self.assertTrue(math.isfinite(q_mirror))
        self.assertLessEqual(q_mirror, q_routed)                 # the route would ADOPT it

    def test_connectivity_repair_at_boundary_coincident_vertex(self):
        """Re-audit finding 1: a fully-in-band segment ending EXACTLY on the band edge, meeting an
        out-of-band segment on the other layer, used to be left with no transition via -> the net severed.
        The connectivity-repair pass must add the missing target<->other via at that vertex."""
        import tempfile
        import cec_fr
        import cec_synth_pipeline as sp
        b = pcbnew.LoadBoard(EPS_PCB)
        model, _ = sp._board_corridor_model(b)
        band2 = next(c.band for c in model.cables if c.formed and c.base == "/SENSEC2")
        x0, x1, y0, y1 = band2
        yc = (y0 + y1) / 2.0
        nc = b.FindNet("/DETC2").GetNetCode()
        # B.Cu L-bend: enters the band, a fully-in-band middle seg ENDING EXACTLY on x1, then an
        # out-of-band tail starting at x1 -> the boundary-coincident vertex the old rule missed.
        pts = [((x0 - 4, yc), (x0 + 3, yc)), ((x0 + 3, yc), (x1, yc)), ((x1, yc), (x1 + 4, yc))]
        for (sx, sy), (ex, ey) in pts:
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(int(sx * 1e6), int(sy * 1e6)))
            t.SetEnd(pcbnew.VECTOR2I(int(ex * 1e6), int(ey * 1e6)))
            t.SetWidth(200_000); t.SetLayer(pcbnew.B_Cu); t.SetNetCode(nc)
            b.Add(t)
        p = os.path.join(tempfile.mkdtemp(), "eps-boundary.kicad_pcb")
        pcbnew.SaveBoard(p, b)
        cec_fr.stagger_corridor_crossings(p, verify=False)
        # the net must NOT be severed: BuildConnectivity sees zero unconnected ratlines for /DETC2
        bb = pcbnew.LoadBoard(p)
        bb.BuildConnectivity()
        # a transition via must exist at the boundary vertex (x1, yc)
        vx, vy = int(round(x1 * 1e6)), int(round(yc * 1e6))
        vias_at_edge = [t for t in bb.GetTracks()
                        if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == "/DETC2"
                        and abs(t.GetPosition().x - vx) <= 1000 and abs(t.GetPosition().y - vy) <= 1000]
        self.assertTrue(vias_at_edge, "connectivity-repair via missing at the band-edge-coincident vertex")
        # and the /DETC2 copper is a single connected component across the layer change
        layers = {t.GetLayer() for t in bb.GetTracks()
                  if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() == "/DETC2"}
        self.assertEqual(layers, {pcbnew.F_Cu, pcbnew.B_Cu})     # both layers present, bridged by the via

    def test_reverts_on_connectivity_regression_even_when_scalar_improves(self):
        """Re-audit finding 2: a stagger that LOWERS the scalar (re-fill heals drc) but RAISES unconnected
        (a net disconnect) must still REVERT -- the scalar must not be allowed to mask a severed net."""
        import tempfile
        import cec_fr
        b = pcbnew.LoadBoard(EPS_PCB)
        for net, y in (("/DETC1", 18.0), ("/THRESH", 20.0)):     # two full-span crossings -> flipped > 0
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(30_000_000, int(y * 1e6)))
            t.SetEnd(pcbnew.VECTOR2I(50_000_000, int(y * 1e6)))
            t.SetWidth(200_000); t.SetLayer(pcbnew.F_Cu); t.SetNetCode(b.FindNet(net).GetNetCode())
            b.Add(t)
        src = os.path.join(tempfile.mkdtemp(), "eps-conn.kicad_pcb")
        pcbnew.SaveBoard(src, b)
        before = open(src, "rb").read()
        orig = cec_fr._route_quality_detail
        # pre: scalar 20, unconnected 5 ; post: scalar 15 (drc improved) but unconnected 8 (a net severed)
        cec_fr._route_quality_detail = lambda p: ((20.0, 5, True) if p == src else (15.0, 8, True))
        try:
            rep = cec_fr.stagger_corridor_crossings(src, verify=True)
        finally:
            cec_fr._route_quality_detail = orig
        self.assertTrue(rep["reverted"])                         # unconnected rose -> reverted despite lower scalar
        self.assertEqual(open(src, "rb").read(), before)         # original byte-identical

    def test_l_bend_crossing_is_detected_and_flipped(self):
        """An L-bend crossing (3 short segments, NO single segment spans the band x-width) was silently
        missed by the old _seg_crosses_band (the audit's flipped=0). The net-extent + band-clip detector
        catches it and staggers the whole in-band subpath onto the alternate layer."""
        import tempfile
        import cec_fr
        b = pcbnew.LoadBoard(EPS_PCB)
        nc = b.FindNet("/DETC2").GetNetCode()
        # band-2 (/SENSEC2) = x[32.5,48.1] y[9.5,27.5]; an L-bend on B.Cu through it -- no single
        # segment reaches from left of x0 to right of x1, so the old full-span test found nothing.
        pts = [((30, 15), (40, 15)), ((40, 15), (40, 20)), ((40, 20), (52, 20))]
        for (sx, sy), (ex, ey) in pts:
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(int(sx * 1e6), int(sy * 1e6)))
            t.SetEnd(pcbnew.VECTOR2I(int(ex * 1e6), int(ey * 1e6)))
            t.SetWidth(200_000); t.SetLayer(pcbnew.B_Cu); t.SetNetCode(nc)
            b.Add(t)
        # sanity: NO single segment spans the band x-width (this is what defeated the old detector)
        self.assertFalse(any(min(s[0], e[0]) < 32.5 and max(s[0], e[0]) > 48.1 for s, e in pts))
        p = os.path.join(tempfile.mkdtemp(), "eps-lbend.kicad_pcb")
        pcbnew.SaveBoard(p, b)
        rep = cec_fr.stagger_corridor_crossings(p, verify=False)
        self.assertEqual(rep["flipped"], 1)                  # the L-bend IS detected (was 0)
        self.assertEqual(rep["vias_added"], 2)               # one transition via at each band x-edge
        # the in-band copper is now on F.Cu (the alternate layer); B.Cu only on the out-of-band tails
        bb = pcbnew.LoadBoard(p)
        in_band_layers = set()
        for t in bb.GetTracks():
            if t.Type() != pcbnew.PCB_TRACE_T or t.GetNetname() != "/DETC2":
                continue
            mx = (t.GetStart().x + t.GetEnd().x) / 2 / 1e6
            if 32.5 <= mx <= 48.1:
                in_band_layers.add(t.GetLayer())
        self.assertEqual(in_band_layers, {pcbnew.F_Cu})      # whole in-band subpath staggered to F.Cu

    def test_shared_bus_noop(self):
        import cec_fr, tempfile
        p = os.path.normpath(os.path.join(HERE, "..", "modules",
                                          "12vhpwr-standard", "12vhpwr-standard-module.kicad_pcb"))
        if os.path.isfile(p):
            rep = cec_fr.stagger_corridor_crossings(
                p, out_path=os.path.join(tempfile.mkdtemp(), "h.kicad_pcb"), verify=False)
            self.assertEqual(rep["flipped"], 0)                  # no formed cable corridor -> no-op

    def test_foreign_net_classifier(self):
        import cec_fr
        cn = {"/SENSEC1_HI", "/SENSEC1_LO"}
        self.assertTrue(cec_fr._corridor_foreign_net("/DETC1", cn, set()))
        self.assertFalse(cec_fr._corridor_foreign_net("/SENSEC1_HI", cn, set()))   # corridor net
        self.assertFalse(cec_fr._corridor_foreign_net("/IN1_P", cn, {"/IN1_P"}))   # sense net
        self.assertFalse(cec_fr._corridor_foreign_net("GND", cn, set()))
        self.assertFalse(cec_fr._corridor_foreign_net("/+3V3", cn, set()))


# --------------------------------------------------------------------------- the safe-revert metric
class TestRouteQuality(unittest.TestCase):
    """_route_quality (cec_fr): the stagger safe-revert metric. LOWER is better; combines structural
    DRC + unrouted ratlines + a hard-gate penalty; a measurement FAILURE returns +inf (never 0 -- the
    old `except: return 0` masked a broken board as a perfect score, panel G5)."""

    def test_measurement_failure_is_inf_not_zero(self):
        import math
        import cec_fr
        q = cec_fr._route_quality("/no/such/board.kicad_pcb")
        self.assertFalse(math.isfinite(q))        # +inf, NOT 0 -- an unscoreable board is the worst

    def test_gate_failure_dominates(self):
        """A gate-failing board (Kelvin/diff-pair not routed) must score far worse than a gate-passing
        one even with a higher raw DRC count -- so a stagger that strands a sense tap is reverted."""
        import types
        import cec_fr

        def _fake_score(passing, drc, unconnected):
            m = types.SimpleNamespace(drc=drc, unconnected=unconnected,
                                      kelvin_ok=passing, diffpair_ok=passing)
            fake = types.SimpleNamespace(score=lambda _p: m)
            return fake

        orig = sys.modules.get("cec_score")
        try:
            sys.modules["cec_score"] = _fake_score(True, drc=5, unconnected=0)
            q_pass = cec_fr._route_quality("x")
            sys.modules["cec_score"] = _fake_score(False, drc=0, unconnected=0)
            q_gatefail = cec_fr._route_quality("x")
        finally:
            if orig is not None:
                sys.modules["cec_score"] = orig
            else:
                sys.modules.pop("cec_score", None)
        self.assertEqual(q_pass, 5.0)             # drc + unconnected, gates ok -> no penalty
        self.assertGreater(q_gatefail, 1000)      # gate fail -> heavy penalty dominates
        self.assertGreater(q_gatefail, q_pass)


@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(EPS_PCB),
                     "pcbnew + the committed eps-8pin board required")
class TestStaggerSafeRevert(unittest.TestCase):
    """The stagger transform is staged to a TEMP board and only adopted if _route_quality does not
    regress -- an in-place call can never overwrite-then-fail-to-restore the original (panel G2)."""

    def test_reverts_on_quality_regression_without_corrupting_original(self):
        import tempfile
        import cec_fr
        # A board with two straight full-span crossings (so flipped > 0 and verify runs).
        b = pcbnew.LoadBoard(EPS_PCB)
        for net, y in (("/DETC1", 18.0), ("/THRESH", 20.0)):
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pcbnew.VECTOR2I(30_000_000, int(y * 1e6)))
            t.SetEnd(pcbnew.VECTOR2I(50_000_000, int(y * 1e6)))
            t.SetWidth(200_000); t.SetLayer(pcbnew.F_Cu); t.SetNetCode(b.FindNet(net).GetNetCode())
            b.Add(t)
        src = os.path.join(tempfile.mkdtemp(), "eps-cross.kicad_pcb")
        pcbnew.SaveBoard(src, b)
        before = open(src, "rb").read()
        # Force a "regression" by making the staggered board always score worse than the original.
        orig_rq = cec_fr._route_quality_detail
        cec_fr._route_quality_detail = lambda p: ((0.0, 0, True) if p == src else (1.0e9, 0, True))
        try:
            rep = cec_fr.stagger_corridor_crossings(src, verify=True)   # in-place (out_path == src)
        finally:
            cec_fr._route_quality_detail = orig_rq
        self.assertTrue(rep["reverted"])
        self.assertEqual(rep["flipped"], 0)            # reverted -> no flips reported
        self.assertEqual(open(src, "rb").read(), before)  # original board byte-identical (not corrupted)


if __name__ == "__main__":
    unittest.main()
