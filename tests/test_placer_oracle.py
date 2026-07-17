"""MV2-MV5 of the synth-placer upgrade (docs/placer-upgrade-2026-06-14/plan.json).

MV2 oracle Stage-1 derivation (net-aware _role + edge_override + mount override + outline);
MV3 reproduce-the-reference similarity DIAGNOSTIC (never a rank key);
MV4 proxy_score composite (== HPWL with no reference -> zero regression);
MV5 build_hub_model + hub_score (port-even / antenna-off-edge / power-loop cohesion / USB-ESP prox).

The anti-overfit charter (docs/placer-upgrade-2026-06-14/anti-overfit-charter.md) binds: the
reference is VALIDATION, never an optimization target. The logic terms are exercised host-side with
synthetic fixtures; the real-board derivation + the "reference scores well" charter check are
pcbnew-gated against the committed Hub (skip on a kicad-less box).
"""
import os
import sys
import copy
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import cec_synth_pipeline as sp                                  # noqa: E402

try:
    import pcbnew                                                # noqa: F401
    HAVE_PCBNEW = True
except Exception:
    HAVE_PCBNEW = False

HUB_DIR = os.path.normpath(os.path.join(HERE, "..", "hubs", "hub-standard"))
HUB_PCB = os.path.join(HUB_DIR, "hub-standard.kicad_pcb")
EPS_PCB = os.path.normpath(os.path.join(HERE, "..", "tests", "fixtures", "eps-8pin-legacy", "eps8pin-module.kicad_pcb"))  # legacy fixture


def _nl(comps, nets):
    return sp.Netlist(comps={r: sp.Comp(ref=r, value=v, footprint=f) for r, (v, f) in comps.items()},
                      nets=nets)


# ===================================================================== MV2a: net-aware _role
class TestRoleNetAware(unittest.TestCase):
    def setUp(self):
        # a power-only connector (JST, only rails+GND), a data connector (UART), an RJ-45, a USB.
        self.nl = _nl(
            {"J_PWR": ("", "cec:JST_XH_S2B"), "J_DATA": ("", "cec:JST_PH_S5B"),
             "J_RJ": ("", "cec:RJ45_FTP_Shielded"), "J_USBX": ("", "cec:USB_C_Receptacle")},
            {"/5VSB_RAW": [("J_PWR", "1")], "GND": [("J_PWR", "2"), ("J_DATA", "4")],
             "/AUX_TXC": [("J_DATA", "1")], "/KVM_3V3_REF": [("J_DATA", "3")]})

    def test_power_only_connector_is_power_in(self):
        self.assertEqual(sp._role("J_PWR", "", "cec:JST_XH_S2B", nl=self.nl), "power_in")

    def test_data_connector_is_host(self):
        self.assertEqual(sp._role("J_DATA", "", "cec:JST_PH_S5B", nl=self.nl), "host")

    def test_rj45_and_usb_by_footprint(self):
        self.assertEqual(sp._role("J_RJ", "", "cec:RJ45_FTP_Shielded", nl=self.nl), "host")
        self.assertEqual(sp._role("J_USBX", "", "cec:USB_C_Receptacle", nl=self.nl), "usb")

    def test_without_nl_falls_back_to_host(self):
        # back-compat: a bare J* with no netlist still classifies (the old behaviour), never crashes
        self.assertEqual(sp._role("J_PWR", "", "cec:JST_XH_S2B"), "host")

    def test_sense_ref_tap_makes_connector_host(self):
        # a connector whose only non-power net is a SENSE/REF tap (a voltage token but NOT a rail)
        # must be host, not power_in (M2): /KVM_3V3_REF carries a 3V3 token but is data, not a rail
        nl = _nl({"J_AUXP": ("", "cec:JST_XH_S2B")},
                 {"+5VSB": [("J_AUXP", "1")], "GND": [("J_AUXP", "2")],
                  "/KVM_3V3_REF": [("J_AUXP", "3")]})
        self.assertFalse(sp._is_rail_net("/KVM_3V3_REF"))
        self.assertFalse(sp._is_rail_net("/MAIN_5V_SENSE"))
        self.assertEqual(sp._role("J_AUXP", "", "cec:JST_XH_S2B", nl=nl), "host")

    def test_in_out_name_heuristic_still_wins(self):
        # an explicit IN/OUT ref name short-circuits before the net test (eps J_IN1/J_OUT1)
        self.assertEqual(sp._role("J_IN1", "", "cec:Molex", nl=self.nl), "power_in")
        self.assertEqual(sp._role("J_OUT1", "", "cec:Molex", nl=self.nl), "power_out")

    def test_rail_token_matches_suffixed_names(self):
        self.assertTrue(sp._is_rail_net("/MAIN_5V_RAW"))
        self.assertTrue(sp._is_rail_net("/5VSB_RAW"))
        self.assertTrue(sp._is_rail_net("GND"))
        self.assertFalse(sp._is_rail_net("/AUX_TXC"))
        self.assertFalse(sp._is_rail_net("/CAN_H"))


# ===================================================== anchor_roles must reach EDGE SEATING
class TestAnchorRoleOverrideSeeding(unittest.TestCase):
    """The 12vhpwr fun-run bug (2026-07-09/10): params['anchor_roles'] was honored by _classify
    (J3/J4 became anchors) but seed_anchors re-derived roles itself, so the 12V-2x6's sideband
    DATA pins made _connector_net_role read BOTH connectors as 'host' -> both seated on the
    RIGHT edge instead of power_in->top / power_out->bottom (straight-through). The
    role_overrides= param closes the gap; default None is byte-identical (golden-safe)."""
    FP = "cec:CEC_12V2x6_Horizontal"

    def setUp(self):
        # 12vhpwr-shaped pair: GND rail pads plus sideband DATA pins (SENSE0/CARD_PWR_STABLE) --
        # the data pins are exactly what makes _connector_net_role fall through to 'host'.
        self.nl = _nl(
            {"J3": ("CEC_CONN_12V2x6", self.FP), "J4": ("CEC_CONN_12V2x6", self.FP)},
            {"GND": [("J3", "7"), ("J3", "8"), ("J4", "7"), ("J4", "8")],
             "/SENSE0": [("J3", "13"), ("J4", "13")],
             "/CARD_PWR_STABLE": [("J3", "15"), ("J4", "15")]})
        self.fp_of = {"J3": self.FP, "J4": self.FP}
        self.W, self.H = 60.0, 40.0

    def test_bug_pin_without_override_both_classify_host(self):
        # the bug, pinned at its root: without the override the sideband data pins make BOTH
        # 12V-2x6 connectors classify 'host' (-> the shared host edge, not top/bottom power
        # seating). NB the seeded edge itself is corner-ambiguous here because two 19.4mm
        # connectors overflow the 40mm edge (place_edge has no fit check -- a separate,
        # documented packing gap), so the assertion pins the ROLE, not the resulting corner.
        for r in ("J3", "J4"):
            self.assertEqual(sp._role(r, "CEC_CONN_12V2x6", self.FP, nl=self.nl), "host", r)

    def test_role_overrides_seat_power_in_top_out_bottom(self):
        A = sp.seed_anchors(self.nl, self.W, self.H, self.fp_of, {}, overhang="none",
                            role_overrides={"J3": "power_in", "J4": "power_out"})
        self.assertEqual(sp._edge_of(A["J3"][0], A["J3"][1], 0.0, 0.0, self.W, self.H), "top")
        self.assertEqual(sp._edge_of(A["J4"][0], A["J4"][1], 0.0, 0.0, self.W, self.H), "bottom")
        # straight-through: the two courtyard CENTRES share an x column (origins differ by rot)
        c3 = A["J3"][0] + sp._courtyard_info(self.FP, A["J3"][2])[0]
        c4 = A["J4"][0] + sp._courtyard_info(self.FP, A["J4"][2])[0]
        self.assertLess(abs(c3 - c4), 0.5)

    def test_edge_override_still_wins_over_role_override(self):
        A = sp.seed_anchors(self.nl, self.W, self.H, self.fp_of, {}, overhang="none",
                            role_overrides={"J3": "power_in"}, edge_override={"J3": "left"})
        self.assertEqual(sp._edge_of(A["J3"][0], A["J3"][1], 0.0, 0.0, self.W, self.H), "left")


# ===================================================================== MV4: proxy_score
class TestProxyScore(unittest.TestCase):
    def test_no_reference_equals_hpwl(self):
        px = {"hpwl": 2002.0, "rudy_peak": 3.0, "thermal_peak_w": 0.5}
        self.assertEqual(sp.proxy_score(px), 2002.0)

    def test_no_reference_ignores_congestion(self):
        # without a normalizer RUDY/thermal are uncalibrated -> must NOT enter the score (regression)
        a = {"hpwl": 100.0, "rudy_peak": 1.0, "thermal_peak_w": 0.1}
        b = {"hpwl": 100.0, "rudy_peak": 50.0, "thermal_peak_w": 5.0}
        self.assertEqual(sp.proxy_score(a), sp.proxy_score(b))

    def test_reference_normalized_discriminates_congestion(self):
        ref = {"hpwl": 100.0, "rudy_peak": 3.0, "thermal_peak_w": 0.5}
        tight = {"hpwl": 100.0, "rudy_peak": 3.0, "thermal_peak_w": 0.5}
        loose = {"hpwl": 100.0, "rudy_peak": 12.0, "thermal_peak_w": 0.5}
        self.assertLess(sp.proxy_score(tight, ref_proxy=ref), sp.proxy_score(loose, ref_proxy=ref))

    def test_hpwl_stays_dominant(self):
        # a big wirelength win must beat a congestion win (HPWL-dominant defaults)
        ref = {"hpwl": 100.0, "rudy_peak": 3.0, "thermal_peak_w": 0.5}
        short_busy = {"hpwl": 60.0, "rudy_peak": 12.0, "thermal_peak_w": 0.5}
        long_clean = {"hpwl": 140.0, "rudy_peak": 3.0, "thermal_peak_w": 0.5}
        self.assertLess(sp.proxy_score(short_busy, ref_proxy=ref),
                        sp.proxy_score(long_clean, ref_proxy=ref))

    def test_weights_knob(self):
        ref = {"hpwl": 100.0, "rudy_peak": 3.0, "thermal_peak_w": 0.5}
        px = {"hpwl": 100.0, "rudy_peak": 12.0, "thermal_peak_w": 0.5}
        base = sp.proxy_score(px, ref_proxy=ref)
        heavier = sp.proxy_score(px, ref_proxy=ref, weights={"rudy": 2.0})
        self.assertGreater(heavier, base)

    def test_hub_penalty_folds_in(self):
        ref = {"hpwl": 100.0, "rudy_peak": 3.0, "thermal_peak_w": 0.5}
        clean = {"hpwl": 100.0, "rudy_peak": 3.0, "thermal_peak_w": 0.5, "hub_penalty": 0.0}
        bad = {"hpwl": 100.0, "rudy_peak": 3.0, "thermal_peak_w": 0.5, "hub_penalty": 0.6}
        self.assertLess(sp.proxy_score(clean, ref_proxy=ref), sp.proxy_score(bad, ref_proxy=ref))


# ===================================================================== MV3/MV4: sort key
class TestSortKey(unittest.TestCase):
    def _cand(self, residual, cc, score, sim):
        return sp.Candidate(strat="x", seed=0, P={}, W=10, H=10, residual=residual,
                            proxy={"hpwl": score, "proxy_score": score}, corridor_cross=cc,
                            similarity=sim)

    def test_similarity_is_not_in_the_key(self):
        # a HIGH-similarity but worse-proxy candidate must NOT win -> similarity is a diagnostic only
        better = self._cand(0, 0, 3.0, 0.1)
        worse_but_similar = self._cand(0, 0, 5.0, 0.95)
        ranked = sorted([worse_but_similar, better], key=sp._candidate_sort_key)
        self.assertIs(ranked[0], better)

    def test_residual_dominates(self):
        legal = self._cand(0, 9, 9.0, 0.0)
        illegal = self._cand(2, 0, 1.0, 0.9)
        self.assertIs(sorted([illegal, legal], key=sp._candidate_sort_key)[0], legal)

    def test_corridor_cross_before_proxy(self):
        clean = self._cand(0, 0, 9.0, 0.0)
        sandwich = self._cand(0, 3, 1.0, 0.0)
        self.assertIs(sorted([sandwich, clean], key=sp._candidate_sort_key)[0], clean)

    def test_similarity_not_even_a_tiebreaker(self):
        # equal (residual, cc, proxy_score) but different similarity -> the key must be IDENTICAL,
        # so similarity cannot act even as a hidden tie-breaker (catches an appended `-similarity`)
        a = self._cand(0, 0, 4.0, 0.95)
        b = self._cand(0, 0, 4.0, 0.05)
        self.assertEqual(sp._candidate_sort_key(a), sp._candidate_sort_key(b))


# ===================================================================== MV5: hub model + score
class TestHubModelGate(unittest.TestCase):
    def test_inert_on_single_port_board(self):
        # an eps-shaped board (1 RJ-45 + ESP) must NOT activate the Hub terms
        nl = _nl({"J1": ("", "cec:RJ45"), "U1": ("", "cec:ESP32-C6")},
                 {"/x": [("U1", "1")]})
        P = {"J1": (5, 5, 0), "U1": (20, 20, 0)}
        m = sp.build_hub_model(nl, P, {r: c.footprint for r, c in nl.comps.items()})
        self.assertFalse(m.active)
        self.assertEqual(sp.hub_score(m, P, 40, 40)["hub_penalty"], 0.0)

    def test_active_on_multi_port_hub(self):
        nl = _nl({"J2": ("", "cec:RJ45"), "J3": ("", "cec:RJ45"), "U1": ("", "cec:ESP32-S3")},
                 {"/x": [("U1", "1")]})
        P = {"J2": (10, 5, 0), "J3": (28, 5, 0), "U1": (20, 30, 0)}
        m = sp.build_hub_model(nl, P, {r: c.footprint for r, c in nl.comps.items()})
        self.assertTrue(m.active)
        self.assertEqual(sorted(m.ports), ["J2", "J3"])

    def test_port_even_rewards_uniform_pitch(self):
        nl = _nl({"J2": ("", "cec:RJ45"), "J3": ("", "cec:RJ45"), "J4": ("", "cec:RJ45"),
                  "U1": ("", "cec:ESP32")}, {"/x": [("U1", "1")]})
        m = sp.build_hub_model(nl, {}, {r: c.footprint for r, c in nl.comps.items()})
        m.active = True
        m.ports = ["J2", "J3", "J4"]
        even = {"J2": (10, 5, 0), "J3": (20, 5, 0), "J4": (30, 5, 0), "U1": (20, 30, 0)}
        uneven = {"J2": (10, 5, 0), "J3": (12, 5, 0), "J4": (30, 5, 0), "U1": (20, 30, 0)}
        self.assertGreater(sp.hub_score(m, even, 40, 40)["port_even"],
                           sp.hub_score(m, uneven, 40, 40)["port_even"])

    def test_off_edge_port_penalized(self):
        nl = _nl({"J2": ("", "cec:RJ45"), "J3": ("", "cec:RJ45"), "U1": ("", "cec:ESP32")},
                 {"/x": [("U1", "1")]})
        comps = {r: c.footprint for r, c in nl.comps.items()}
        on_edge = {"J2": (10, 5, 0), "J3": (28, 5, 0), "U1": (20, 30, 0)}
        off_edge = {"J2": (10, 5, 0), "J3": (20, 20, 0), "U1": (20, 30, 0)}  # J3 in the interior
        m = sp.build_hub_model(nl, on_edge, comps)
        self.assertGreater(sp.hub_score(m, on_edge, 40, 40)["port_even"],
                           sp.hub_score(m, off_edge, 40, 40)["port_even"])

    def test_power_cluster_excludes_sense_and_connectors(self):
        # /MAIN_5V_SENSE must NOT pull a part into the loop; the edge JST must not inflate the bbox
        nl = _nl({"J2": ("", "cec:RJ45"), "J3": ("", "cec:RJ45"), "U1": ("", "cec:ESP32"),
                  "U5": ("", "cec:TPS2121"), "C1": ("", "cec:C"), "J_5V": ("", "cec:JST")},
                 {"/MAIN_5V_RAW": [("U5", "1"), ("C1", "1"), ("J_5V", "1")],
                  "/MAIN_5V_SENSE": [("U1", "1"), ("U5", "5")]})
        P = {"U5": (0, 0, 0), "C1": (2, 0, 0), "J_5V": (40, 0, 0), "U1": (20, 20, 0)}
        m = sp.build_hub_model(nl, P, {r: c.footprint for r, c in nl.comps.items()})
        self.assertIn("U5", m.power_refs)
        self.assertIn("C1", m.power_refs)
        self.assertNotIn("U1", m.power_refs)          # sense net excluded
        self.assertNotIn("J_5V", m.power_refs)        # edge connector excluded

    def test_power_loop_is_topological_not_named(self):
        # CHARTER rule 1: the input loop is derived by FANOUT (point-to-point rail vs distributed
        # plane), with NO reference net-name baked in. A small-fanout rail's parts are in; the
        # distributed +5VSB plane (large fanout) is out -- even though both are voltage rails.
        nets = {"/VIN_MUX": [("U5", "1"), ("C1", "1"), ("J_5V", "1")],          # input rail, fan 3
                "+5VSB": [("U5", "2"), ("C2", "1"), ("R1", "1"), ("R2", "1"),    # output plane, fan 8
                          ("R3", "1"), ("DL1", "1"), ("DL2", "1"), ("J2", "1")]}
        nl = _nl({r: ("", "cec:x") for r in
                  ("U5", "C1", "C2", "R1", "R2", "R3", "DL1", "DL2", "J_5V", "J2",
                   "J3", "U1")}, nets)
        P = {r: (i, 0, 0) for i, r in enumerate(nl.comps)}
        m = sp.build_hub_model(nl, P, {r: c.footprint for r, c in nl.comps.items()})
        self.assertIn("U5", m.power_refs)
        self.assertIn("C1", m.power_refs)             # on the small-fanout input rail
        self.assertNotIn("C2", m.power_refs)          # only on the distributed +5VSB plane -> out
        self.assertNotIn("J_5V", m.power_refs)        # connector excluded
        # the per-board OVERRIDE escape hatch selects by name substring
        m2 = sp.build_hub_model(nl, P, {r: c.footprint for r, c in nl.comps.items()},
                                power_input_nets=["+5VSB"])
        self.assertIn("C2", m2.power_refs)


# ===================================================================== MV3: similarity (synthetic)
def _ref_placement():
    pos = {"J1": (10.0, 5.0, 0.0, 2.0, 2.0), "J2": (30.0, 5.0, 0.0, 2.0, 2.0),
           "U1": (20.0, 20.0, 0.0, 3.0, 3.0), "C1": (22.0, 20.0, 0.0, 1.0, 1.0)}
    pads = {"/SIG": [(20.0, 20.0), (22.0, 20.0)], "GND": [(10.0, 5.0), (20.0, 20.0)]}
    val = {r: "" for r in pos}
    return sp.Placement(pos=pos, pads_by_net=pads, value=val, W=40.0, H=40.0, x0=0.0, y0=0.0)


def _sim_nl():
    return _nl({"J1": ("", "cec:RJ45"), "J2": ("", "cec:RJ45"),
                "U1": ("", "cec:ESP32"), "C1": ("", "cec:C_0402")},
               {"/SIG": [("U1", "1"), ("C1", "1")], "GND": [("J1", "2"), ("U1", "5")]})


class TestSimilarity(unittest.TestCase):
    def setUp(self):
        self.ref = _ref_placement()
        self.nl = _sim_nl()

    def _cand_from(self, pos):
        P = {r: (p[0], p[1], p[2]) for r, p in pos.items()}
        return sp.Candidate(strat="x", seed=0, P=P, W=self.ref.W, H=self.ref.H, residual=0,
                            proxy={"hpwl": sp.hpwl(self.ref.pads_by_net)})

    def test_identity_is_one(self):
        cand = self._cand_from(self.ref.pos)
        score, det = sp.oracle_similarity(cand, self.ref, self.nl)
        self.assertEqual(score, 1.0)
        self.assertEqual(det["edge"], 1.0)
        self.assertEqual(det["dist"], 1.0)

    def test_scramble_scores_lower_with_per_term_teeth(self):
        scr = {r: list(p) for r, p in self.ref.pos.items()}
        scr["J1"] = [20.0, 20.0, 0.0]                 # port off its edge, into the interior
        cand = self._cand_from({r: tuple(p) for r, p in scr.items()})
        cand.proxy["hpwl"] = sp.hpwl(self.ref.pads_by_net) * 1.8
        score, det = sp.oracle_similarity(cand, self.ref, self.nl)
        self.assertLess(score, 1.0)
        self.assertLess(det["edge"], 1.0)             # J1 left its edge -> edge term degrades
        self.assertLess(det["dist"], 1.0)             # ...and moved far -> dist term degrades

    def test_cluster_only_scramble(self):
        # spread the cluster (C1 far from U1) while every connector stays put -> ONLY cluster drops
        scr = {r: tuple(p[:3]) for r, p in self.ref.pos.items()}
        scr = dict(scr); scr["C1"] = (38.0, 38.0, 0.0)
        cand = self._cand_from(scr)
        _, det = sp.oracle_similarity(cand, self.ref, self.nl)
        self.assertEqual(det["edge"], 1.0)            # connectors untouched
        self.assertLess(det["cluster"], 1.0)          # the U1+C1 cluster is now loose

    def test_sparse_board_identity_is_one(self):
        # H1: a board with NO connectors must still score identity == 1.0 (renormalize over present
        # terms) -- not diluted toward 0 by the absent edge/dist terms
        nl = _nl({"U1": ("", "cec:ESP32"), "C1": ("", "cec:C_0402")},
                 {"/SIG": [("U1", "1"), ("C1", "1")]})
        ref = sp.Placement(pos={"U1": (5, 5, 0, 1, 1), "C1": (6, 5, 0, 1, 1)},
                           pads_by_net={"/SIG": [(5, 5), (6, 5)]}, value={"U1": "", "C1": ""},
                           W=20.0, H=20.0, x0=0.0, y0=0.0)
        cand = sp.Candidate(strat="x", seed=0, P={"U1": (5, 5, 0), "C1": (6, 5, 0)}, W=20, H=20,
                            residual=0, proxy={"hpwl": sp.hpwl(ref.pads_by_net)})
        score, det = sp.oracle_similarity(cand, ref, nl)
        self.assertEqual(score, 1.0)
        self.assertEqual(det["edge"], -1.0)           # absent term reported as -1, not folded as 0

    def test_hpwl_term_reads_the_gap(self):
        cand = self._cand_from(self.ref.pos)
        cand.proxy["hpwl"] = sp.hpwl(self.ref.pads_by_net) * 2.0   # exactly +100%
        _, det = sp.oracle_similarity(cand, self.ref, self.nl)
        self.assertEqual(det["hpwl"], 0.0)            # 1 - |2x-1x|/1x = 0


# ===================================================================== MV2/MV3/MV5 on the real Hub
@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(HUB_PCB),
                     "pcbnew + the committed Hub board required")
class TestOracleOnHub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = sp.Config.load(HUB_DIR)
        cls.ans = sp.oracle_stage1_answers(cls.cfg, HUB_PCB)

    def test_outline_derived(self):
        w, h = self.ans["size_target_wh"]
        self.assertAlmostEqual(w, 98.1, delta=0.5)
        self.assertAlmostEqual(h, 74.1, delta=0.5)

    def test_connectors_bin_to_three_edges(self):
        eo = self.ans["edge_override"]
        for r in ("J2", "J3", "J4", "J5"):
            self.assertEqual(eo[r], "top", r)
        self.assertEqual(eo["J_KVM"], "bottom")
        self.assertEqual(eo["J_USB"], "bottom")
        # The beta hub schematic renamed the power-in headers (J_5V/J_5VSB -> the J_PWR
        # generation) while the committed PCB still carries the old refs, so the power-in
        # row is legitimately ABSENT from the oracle's map until the PCB's
        # Update-from-Schematic lands (re-baselined 2026-07-07). Assert the invariant that
        # survives the rename: anything binned to the power edge must be a power-in ref.
        for r, e in eo.items():
            if e == "right":
                self.assertIn("5V", r.upper().replace("_", ""),
                              "non-power ref %r binned to the power edge" % r)

    def test_antenna_and_mounts(self):
        self.assertEqual(self.ans.get("antenna_edge"), "left")
        self.assertTrue(self.ans.get("respect_antenna_keepout"))
        self.assertEqual(len(self.ans.get("mount_pos_override", {})), 4)

    def test_edge_override_round_trips_through_seed_anchors(self):
        # the derivation MUST reproduce the reference's own connector edges (a ground-truth self-check)
        nl = sp.View(self.cfg).nl
        fp_of = sp._fp_of(nl)
        w, h = self.ans["size_target_wh"]
        A = sp.seed_anchors(nl, w, h, fp_of, {}, overhang="none",
                            edge_override=self.ans["edge_override"])
        for ref, want in self.ans["edge_override"].items():
            if ref in A:
                got = sp._edge_of(A[ref][0], A[ref][1], 0.0, 0.0, w, h)
                self.assertEqual(got, want, "%s want %s got %s" % (ref, want, got))

    def test_reference_scores_well_on_hub_terms(self):
        # CHARTER: a principled term must score the HAND board well (validate, never tune toward).
        ref_pl = sp.read_placement(HUB_PCB)
        nl = sp.View(self.cfg).nl
        P = {r: (p[0] - ref_pl.x0, p[1] - ref_pl.y0, p[2]) for r, p in ref_pl.pos.items()}
        comps = {r: c.footprint for r, c in nl.comps.items()}
        hs = sp.hub_score(sp.build_hub_model(nl, P, comps, antenna_edge="left"), P, ref_pl.W, ref_pl.H)
        self.assertTrue(hs["active"])
        self.assertLess(hs["hub_penalty"], 0.4)       # hand board is cohesive overall
        self.assertGreater(hs["power_cluster"], 0.5)  # the mux input loop is tight (not red-by-design)

    def test_similarity_reference_against_itself_is_one(self):
        ref_pl = sp.read_placement(HUB_PCB)
        nl = sp.View(self.cfg).nl
        P = {r: (p[0] - ref_pl.x0, p[1] - ref_pl.y0, p[2]) for r, p in ref_pl.pos.items()}
        cand = sp.Candidate(strat="ref", seed=0, P=P, W=ref_pl.W, H=ref_pl.H, residual=0,
                            proxy={"hpwl": sp.hpwl(ref_pl.pads_by_net)})
        score, _ = sp.oracle_similarity(cand, ref_pl, nl)
        self.assertEqual(score, 1.0)

    def test_place_candidates_with_oracle_populates_diagnostics(self):
        cfg = sp.Config.load(HUB_DIR)
        cfg.params["oracle_reference_path"] = HUB_PCB
        w, h = self.ans["size_target_wh"]
        cands = sp.place_candidates(cfg, w, h, strategies=("compact",), seeds=(0,))
        best = cands[0]
        self.assertIn("proxy_score", best.proxy)
        self.assertIn("hub_penalty", best.proxy)
        self.assertIn("hub_terms", best.proxy)
        self.assertGreaterEqual(best.similarity, 0.0)        # similarity computed (diagnostic)
        self.assertIn("edge_override", cfg.params)            # MV2 inputs were applied
        self.assertEqual(cfg.params["edge_override"]["J2"], "top")

    def test_oracle_off_is_unchanged(self):
        # no reference -> no oracle inputs, proxy_score == HPWL (zero behaviour change)
        cfg = sp.Config.load(HUB_DIR)
        w, h = self.ans["size_target_wh"]
        cands = sp.place_candidates(cfg, w, h, strategies=("compact",), seeds=(0,))
        best = cands[0]
        self.assertNotIn("edge_override", cfg.params)
        self.assertEqual(best.proxy["proxy_score"], best.proxy["hpwl"])
        self.assertEqual(best.similarity, -1.0)

    def test_mounts_roundtrip_near_reference_corners(self):
        # MV2 plan validation: the derived mount positions round-trip through place_mechanical to
        # the reference's own corners within ~2mm.
        ref_pl = sp.read_placement(HUB_PCB)
        mp = self.ans["mount_pos_override"]
        w, h = self.ans["size_target_wh"]
        pos, _fp = sp.place_mechanical(w, h, {"mount_pos_override": mp})
        ref_corners = sorted((round(p[0] - ref_pl.x0, 2), round(p[1] - ref_pl.y0, 2))
                             for r, p in ref_pl.pos.items() if sp._is_mount_ref(r))
        got = sorted((pos[r][0], pos[r][1]) for r in pos if r.startswith("H"))
        self.assertEqual(len(got), 4)
        for (gx, gy), (rx, ry) in zip(got, ref_corners):
            self.assertLess(abs(gx - rx), 2.0)
            self.assertLess(abs(gy - ry), 2.0)

    def test_rj45_pitch_is_uniform(self):
        # MV2: the four ganged RJ-45 ports seed at a uniform pitch (~the reference's 18.5mm)
        nl = sp.View(self.cfg).nl
        fp_of = sp._fp_of(nl)
        w, h = self.ans["size_target_wh"]
        A = sp.seed_anchors(nl, w, h, fp_of, {}, overhang="none",
                            edge_override=self.ans["edge_override"])
        xs = sorted(A[r][0] for r in ("J2", "J3", "J4", "J5"))
        gaps = [b - a for a, b in zip(xs, xs[1:])]
        for g in gaps:
            self.assertAlmostEqual(g, gaps[0], delta=0.5)   # uniform pitch
        self.assertAlmostEqual(gaps[0], 18.5, delta=4.0)    # near the reference pitch

    def test_invalid_edge_override_does_not_drop_connector(self):
        # M3: a bad human/spec edge value ("TOP", a typo) must fall back to the role default, never
        # silently drop the connector from the placement.
        nl = sp.View(self.cfg).nl
        fp_of = sp._fp_of(nl)
        w, h = self.ans["size_target_wh"]
        bad = dict(self.ans["edge_override"]); bad["J2"] = "TOP"; bad["J3"] = "north"
        A = sp.seed_anchors(nl, w, h, fp_of, {}, overhang="none", edge_override=bad)
        self.assertIn("J2", A)                         # not dropped
        self.assertIn("J3", A)
        # J2/J3 fall back to their role default edge (host -> right), still placed on-board
        self.assertTrue(0 <= A["J2"][0] <= w and 0 <= A["J2"][1] <= h)

    def test_mv4_reference_ranks_at_or_near_lowest_proxy(self):
        # MV4 plan validation: the reference must land at/near the lowest proxy_score in a sweep --
        # if a worse-spread synth candidate outranks it, the weights are wrong.
        ref_pl = sp.read_placement(HUB_PCB)
        ref_proxy = sp.placement_proxy(ref_pl)
        cfg = sp.Config.load(HUB_DIR)
        cfg.params["oracle_reference_path"] = HUB_PCB
        w, h = self.ans["size_target_wh"]
        cands = sp.place_candidates(cfg, w, h, strategies=sp.STRATEGIES, seeds=(0,))
        ref_score = sp.proxy_score(ref_proxy, ref_proxy=ref_proxy)
        synth_scores = [c.proxy["proxy_score"] for c in cands]
        self.assertLessEqual(ref_score, min(synth_scores) + 1e-6,
                             "reference proxy_score %.3f should be <= every synth %r"
                             % (ref_score, synth_scores))

    def test_mv3_reference_outscores_every_synth_candidate(self):
        # MV3 plan validation: the human board is the optimized answer -> it must out-similarity
        # every synth candidate on its own netlist (and the synth ones must be < 1.0).
        ref_pl = sp.read_placement(HUB_PCB)
        nl = sp.View(self.cfg).nl
        cfg = sp.Config.load(HUB_DIR)
        cfg.params["oracle_reference_path"] = HUB_PCB
        w, h = self.ans["size_target_wh"]
        cands = sp.place_candidates(cfg, w, h, strategies=sp.STRATEGIES, seeds=(0,))
        for c in cands:
            self.assertLess(c.similarity, 1.0, "a synth candidate scored == the reference")
            self.assertGreaterEqual(c.similarity, 0.0)


if __name__ == "__main__":
    unittest.main()
