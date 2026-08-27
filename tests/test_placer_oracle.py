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
import json
import math
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

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
    def test_fiducial_sites_are_selected_as_a_global_open_corner_set(self):
        corners = ((0.0, 0.0), (100.0, 0.0),
                   (0.0, 50.0), (100.0, 50.0))

        def corner_index(point):
            return min(range(4), key=lambda index: math.hypot(
                point[0] - corners[index][0],
                point[1] - corners[index][1]))

        sites = [(5.0, 5.0), (5.0, 45.0)]
        selected = sp._select_fiducial_sites_global(
            sites, [(95.0, 5.0), (95.0, 45.0)], 1, corners,
            corner_index=corner_index,
            route_pressure=lambda _point: (0, 0.0),
            site_openness=lambda point: (
                10.0 if point == (5.0, 45.0) else 1.0),
            minimum_separation=12.0)

        self.assertEqual(selected, [(5.0, 45.0)])

    def test_fiducial_open_space_clearance_is_zero_inside_rectangle(self):
        self.assertEqual(
            sp._point_rect_clearance((2.0, 3.0), (1.0, 1.0, 4.0, 5.0)),
            0.0)
        self.assertAlmostEqual(
            sp._point_rect_clearance((0.0, 0.0), (3.0, 4.0, 7.0, 8.0)),
            5.0)

    def test_pair_affinity_preserves_two_leg_criticality(self):
        nl = _nl(
            {"U1": ("", "cec:MCU"), "D3": ("", "cec:ESD"),
             "J5": ("", "cec:USB"), "R1": ("", "cec:R")},
            {"/USB_D_P": [("U1", "1"), ("D3", "1"), ("J5", "1")],
             "/USB_D_N": [("U1", "2"), ("D3", "2"), ("J5", "2")],
             "/GPIO": [("U1", "3"), ("R1", "1")]})
        affinity = sp._placement_affinity(nl, pair_weight=8.0)
        self.assertEqual(affinity["U1"]["D3"], 8.0)
        self.assertEqual(affinity["U1"]["J5"], 8.0)
        self.assertEqual(affinity["U1"]["R1"], 1.0)
        self.assertEqual(affinity["D3"]["J5"], 8.0)

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

    def test_physical_topk_rerank_beats_shorter_proxy(self):
        blocked = self._cand(0, 0, 3.0, 0.0)
        blocked.strat = "blocked"
        clear = self._cand(0, 0, 5.0, 0.0)
        clear.strat = "clear"
        outside = self._cand(0, 0, 7.0, 0.0)
        reports = {
            "blocked": {"fanout": {"blocked": 0},
                        "pin_access": {"blocked_count": 2},
                        "stackup": {},
                        "congestion": {"unroutable_count": 0,
                                       "residual_overuse_escaped": 1,
                                       "residual_overuse": 1}},
            "clear": {"fanout": {"blocked": 0},
                      "pin_access": {"blocked_count": 0},
                      "stackup": {},
                      "congestion": {"unroutable_count": 0,
                                     "residual_overuse_escaped": 1,
                                     "residual_overuse": 1}},
        }

        def fake_materialize(cand, _cfg, out):
            with open(out, "w", encoding="utf-8") as handle:
                handle.write(cand.strat)
            return out

        def fake_analyze(path, **_kwargs):
            with open(path, encoding="utf-8") as handle:
                return reports[handle.read()]

        cfg = SimpleNamespace(params={"placement_route_preflight_workers": 1})
        with mock.patch.object(sp, "materialize", side_effect=fake_materialize), \
                mock.patch("cec_route_preflight.analyze",
                           side_effect=fake_analyze):
            ranked = sp.rerank_route_preflight(
                cfg, [blocked, clear, outside], topk=2)
        self.assertEqual([cand.strat for cand in ranked],
                         ["clear", "blocked", "x"])
        self.assertEqual(clear.route_preflight["pin_access_blocked_count"], 0)

    def test_route_preflight_worker_count_is_bounded_and_gpu_serial(self):
        cfg = SimpleNamespace(params={"placement_route_preflight_workers": 3})
        self.assertEqual(sp._route_preflight_worker_count(cfg, 8, "cpu"), 3)
        self.assertEqual(sp._route_preflight_worker_count(cfg, 2, "auto"), 2)
        self.assertEqual(sp._route_preflight_worker_count(cfg, 8, "gpu"), 1)
        self.assertEqual(sp._route_preflight_worker_count(cfg, 0, "cpu"), 0)

    def test_route_preflight_uses_each_candidates_outline_config(self):
        first = self._cand(0, 0, 5.0, 0.0)
        first.strat = "first-outline"
        second = self._cand(0, 0, 6.0, 0.0)
        second.strat = "second-outline"
        base = SimpleNamespace(params={
            "placement_route_preflight_workers": 1, "owner": "base"})
        owners = {
            id(first): SimpleNamespace(params={
                "placement_route_preflight_workers": 1,
                "owner": "small"}),
            id(second): SimpleNamespace(params={
                "placement_route_preflight_workers": 1,
                "owner": "large"}),
        }
        seen = []

        def fake_materialize(cand, owner, out):
            seen.append((cand.strat, owner.params["owner"]))
            with open(out, "w", encoding="utf-8") as handle:
                handle.write(cand.strat)
            return out

        def fake_analyze(_path, **_kwargs):
            return {"fanout": {"blocked": 0},
                    "pin_access": {"blocked_count": 0},
                    "stackup": {},
                    "congestion": {"unroutable_count": 0,
                                   "residual_overuse_escaped": 0,
                                   "residual_overuse": 0}}

        with mock.patch.object(sp, "materialize", side_effect=fake_materialize), \
                mock.patch("cec_route_preflight.analyze",
                           side_effect=fake_analyze):
            sp.rerank_route_preflight(
                base, [first, second], topk=2,
                candidate_cfg=lambda cand: owners[id(cand)])
        self.assertEqual(seen, [
            ("first-outline", "small"),
            ("second-outline", "large"),
        ])

    def test_placement_pair_budget_is_scoped_and_restored(self):
        key = "CEC_PRECISION_PAIR_TIMEOUT"
        previous = os.environ.pop(key, None)
        try:
            with sp._oracle_env({"placement_route_pair_timeout_s": 60}):
                self.assertEqual(os.environ.get(key), "60.0")
            self.assertNotIn(key, os.environ)
        finally:
            if previous is not None:
                os.environ[key] = previous

    def test_access_move_specs_prioritize_named_movable_blocker(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {"U11": (5, 5, 0), "R37": (6, 5, 0),
                       "J1": (8, 5, 0)}
        evidence = {"pin_access_blocked": [{
            "ref": "U11", "x": 5, "y": 5,
            "blocked_options": [{"direction": "E", "layers": [{
                "layer": "F.Cu", "blockers": [
                    {"ref": "R37"}, {"ref": "J1"}]}]}]}]}
        moves = sp._route_access_move_specs(
            candidate, evidence, SimpleNamespace(pins={}))
        self.assertTrue(moves)
        self.assertEqual(moves[0]["ref"], "R37")
        self.assertEqual(moves[0]["kind"], "rotate_180")
        blocker_moves = [move["kind"] for move in moves
                         if move["ref"] == "R37"]
        self.assertEqual(blocker_moves[0], "rotate_180")
        self.assertIn("pin_blocker_relief", blocker_moves[:4])
        self.assertLess(blocker_moves.index("pin_blocker_relief"),
                        blocker_moves.index("rotate_90"))
        self.assertNotIn("J1", {move["ref"] for move in moves})

    def test_direct_access_failure_excludes_unrelated_global_pressure_refs(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {
            "U4": (5, 5, 0), "C6": (5, 3, 180),
            "R_FAR": (20, 20, 0), "C_PRESSURE": (25, 25, 0),
        }
        evidence = {
            "pin_access_blocked": [{
                "ref": "U4", "blocked_options": [{
                    "direction": "N", "layers": [{
                        "layer": "F.Cu", "blockers": [{"ref": "C6"}],
                    }],
                }],
            }],
            "blockage_witnesses": [{
                "kind": "unroutable", "candidate_refs": [{
                    "ref": "R_FAR", "role": "unroutable_endpoint",
                }],
            }],
            "future_congestion": {"pressure_refs": [{
                "ref": "C_PRESSURE", "pressure_units": 999999,
            }]},
        }

        moves = sp._route_access_move_specs(
            candidate, evidence, SimpleNamespace(pins={}))

        self.assertEqual({move["ref"] for move in moves}, {"C6", "U4"})
        selected = sp._bounded_evidence_move_specs(moves, 8)
        self.assertEqual({move["ref"] for move in selected}, {"C6", "U4"})
        self.assertTrue({"pin_blocker_relief", "shift"}.intersection(
            {move["kind"] for move in selected}))

    @unittest.skipUnless(HAVE_PCBNEW, "pcbnew unavailable")
    def test_board_route_authority_binds_exact_matching_sibling_state(self):
        class Position:
            x = 5_000_000
            y = 6_000_000

        class Footprint:
            def GetPosition(self):
                return Position()

            def GetOrientationDegrees(self):
                return 90.0

        class Board:
            def FindFootprintByReference(self, ref):
                return Footprint() if ref == "U1" else None

            def GetBoardEdgesBoundingBox(self):
                return SimpleNamespace(
                    GetWidth=lambda: 20_000_000,
                    GetHeight=lambda: 10_000_000)

        with tempfile.TemporaryDirectory() as work:
            board_path = os.path.join(work, "board.kicad_pcb")
            open(board_path, "w", encoding="utf-8").close()
            state_path = os.path.join(work, "board.pourfirst-state.json")
            with open(state_path, "w", encoding="utf-8") as sink:
                json.dump({
                    "schema": 3, "placement_scope": "complete",
                    "placements": {"U1": [5.0, 6.0, 90.0]},
                    "frozen_nets": ["/PWR"],
                    "pours": [{
                        "net": "/PWR", "provenance": "pourfirst",
                        "layer": "F.Cu", "polygon": [
                            [1.0, 1.0], [4.0, 1.0],
                            [4.0, 3.0], [1.0, 3.0]],
                    }],
                    "corridors": [{"net": "/PWR"}],
                }, sink)
            cfg = SimpleNamespace(params={"sentinel": 1})
            with mock.patch("pcbnew.LoadBoard", return_value=Board()):
                bound, report = sp.config_with_board_route_authority(
                    cfg, board_path)

        self.assertTrue(report["ok"])
        self.assertTrue(report["bound"])
        self.assertEqual(bound.params["pourfirst_state"], state_path)
        self.assertEqual(report["avoid_box_count"], 1)
        self.assertEqual(len(bound.params["pourfirst_avoid_boxes"]), 1)
        self.assertEqual(bound.params["pourfirst_seen_placements"]["U1"],
                         [5.0, 6.0, 90.0])
        self.assertNotIn("pourfirst_state", cfg.params)

    @unittest.skipUnless(HAVE_PCBNEW, "pcbnew unavailable")
    def test_board_route_authority_clears_inherited_state_without_sibling(self):
        with tempfile.TemporaryDirectory() as work:
            board_path = os.path.join(work, "board.kicad_pcb")
            open(board_path, "w", encoding="utf-8").close()
            cfg = SimpleNamespace(params={
                "sentinel": 1,
                "pourfirst_state": "/other/placement.pourfirst-state.json",
                "pourfirst_outline_mm": [50.0, 40.0],
                "pourfirst_seen_placements": {"U1": [1.0, 2.0, 0.0]},
                "pourfirst_avoid_boxes": [{"net": "/OLD"}],
            })

            bound, report = sp.config_with_board_route_authority(
                cfg, board_path)

        self.assertTrue(report["ok"])
        self.assertFalse(report["bound"])
        self.assertEqual(report["reason"], "no_sibling_pourfirst_state")
        self.assertEqual(set(report["cleared_inherited_authority"]), {
            "pourfirst_state", "pourfirst_outline_mm",
            "pourfirst_seen_placements", "pourfirst_avoid_boxes",
        })
        self.assertEqual(bound.params, {"sentinel": 1})
        self.assertIn("pourfirst_state", cfg.params)

    def test_future_congestion_pressure_generates_generalized_moves(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {"R27": (5, 5, 0), "U8": (6, 5, 0),
                       "J_USB": (8, 5, 0)}
        evidence = {
            "pin_access_blocked": [],
            "future_congestion": {"pressure_refs": [
                {"ref": "J_USB", "pressure_units": 9000},
                {"ref": "R27", "pressure_units": 2000},
                {"ref": "U8", "pressure_units": 1000},
            ]},
        }
        moves = sp._route_access_move_specs(
            candidate, evidence, SimpleNamespace(pins={}))
        self.assertTrue(moves)
        self.assertEqual(moves[0]["ref"], "R27")
        self.assertEqual(moves[0]["kind"], "rotate_180")
        self.assertNotIn("J_USB", {move["ref"] for move in moves})

    def test_refused_flow_pair_moves_remote_cluster_not_inline_station(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {
            "D6": (10, 10, 0), "U1": (40, 10, 0),
            "C_U1": (41, 10, 0), "J_USB": (8, 10, 0),
        }
        evidence = {
            "critical_pair_refs": ["D6", "J_USB", "U1"],
            "critical_pair_flow_through_refs": ["D6"],
        }
        moves = sp._route_access_move_specs(
            candidate, evidence, SimpleNamespace(pins={}),
            groups={"U1": ("U1", "C_U1")})
        directed = [row for row in moves
                    if row["kind"] == "pair_endpoint_cluster_shift"]
        self.assertTrue(directed)
        self.assertEqual({row["ref"] for row in directed}, {"U1"})
        self.assertTrue(all("C_U1" in row["placements"] for row in directed))
        self.assertTrue(all(row["dx_mm"] < 0 for row in directed))
        self.assertEqual(
            {round(abs(row["dx_mm"]), 6) for row in directed},
            {0.5, 1.0, 2.0, 4.0})

    def test_split_pair_endpoint_moves_as_one_rigid_station(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {
            "U2": (10, 10, 0), "R11": (30, 20, 0),
            "R12": (30, 22, 90), "C11": (31, 20, 0),
        }
        evidence = {
            "critical_pair_refs": ["R11", "R12", "U2"],
            "critical_pair_refused": [{
                "name": "CAN", "p": "/CAN_H", "n": "/CAN_L",
                "endpoint_stations": [
                    {"id": "U2", "physical_refs": ["U2"],
                     "center": [10, 10]},
                    {"id": "R11|R12",
                     "physical_refs": ["R11", "R12"],
                     "center": [30, 21]},
                ],
            }],
        }

        moves = sp._route_access_move_specs(
            candidate, evidence, SimpleNamespace(pins={}, params={}),
            groups={"R11": ("R11", "C11")})

        station_moves = [row for row in moves
                         if row["kind"] == "pair_endpoint_station_shift"]
        self.assertTrue(station_moves)
        first = next(row for row in station_moves
                     if row["station"] == "R11|R12")
        self.assertEqual(set(first["placements"]), {"R11", "R12", "C11"})
        self.assertEqual(first["direction"], "peer-ring-axis")
        self.assertLess(first["dx_mm"], 0)
        self.assertLess(first["dy_mm"], 0)
        self.assertGreater(first["distance_mm"], 10.0)
        self.assertEqual(first["peer_ring_radius_mm"], 4.0)
        self.assertAlmostEqual(
            first["placements"]["R11"][0]
            - first["placements"]["R12"][0], 0.0)
        self.assertAlmostEqual(
            first["placements"]["R12"][1]
            - first["placements"]["R11"][1], 2.0)
        single_package = [row for row in station_moves
                          if row["station"] == "U2"]
        self.assertTrue(single_package)
        self.assertIn("away-from-peer", {
            row["direction"] for row in single_package})
        self.assertEqual({row["budget_group"] for row in station_moves}, {
            "pair-station:CAN:R11|R12", "pair-station:CAN:U2"})
        selected = sp._bounded_evidence_move_specs(moves, 16)
        self.assertEqual(selected[0]["kind"],
                         "pair_endpoint_station_shift")
        selected_station = [row for row in selected
                            if row["kind"] ==
                            "pair_endpoint_station_shift"]
        self.assertEqual({row["station"] for row in selected_station}, {
            "R11|R12", "U2"})

    def test_pair_failure_certificate_drives_rigid_portal_moves_first(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {
            "U2": (10, 10, 0), "R11": (30, 20, 0),
            "R12": (30, 22, 90), "C11": (31, 20, 0),
        }
        evidence = {
            "critical_pair_refs": ["R11", "R12", "U2"],
            "critical_pair_refused": [{
                "name": "CAN", "p": "/CAN_H", "n": "/CAN_L",
                "endpoint_stations": [
                    {"id": "U2", "physical_refs": ["U2"],
                     "center": [10, 10]},
                    {"id": "R11|R12",
                     "physical_refs": ["R11", "R12"],
                     "center": [30, 21]},
                ],
                "failure_certificate": {
                    "classification": ["reservation_barrier"],
                    "endpoints": {
                        "start": {"center_mm": [10, 10]},
                        "end": {"center_mm": [30, 21]},
                    },
                    "relief_vectors": [{
                        "endpoint": "end",
                        "direction": "normal-positive",
                        "vector": [0, 1],
                        "probe_steps_mm": [0.5, 1.0],
                        "reason": "reservation_barrier",
                    }],
                },
            }],
        }

        moves = sp._route_access_move_specs(
            candidate, evidence, SimpleNamespace(pins={}, params={}),
            groups={"R11": ("R11", "C11")})

        self.assertEqual(moves[0]["kind"], "pair_failure_portal_shift")
        self.assertEqual(moves[0]["station"], "R11|R12")
        self.assertEqual(set(moves[0]["placements"]),
                         {"R11", "R12", "C11"})
        self.assertEqual(moves[0]["dy_mm"], 0.5)
        self.assertEqual(
            moves[0]["pair_failure_witness"]["classifications"],
            ["reservation_barrier"])

    def test_insufficient_coupling_drives_rigid_lane_alignment_and_rotation(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {
            "U2": (10, 10, 0), "R11": (30, 20, 0),
            "R12": (30, 22, 90), "C11": (31, 20, 0),
        }
        evidence = {
            "critical_pair_refs": ["R11", "R12", "U2"],
            "critical_pair_refused": [{
                "name": "CAN", "p": "/CAN_H", "n": "/CAN_L",
                "endpoint_stations": [
                    {"id": "U2", "physical_refs": ["U2"],
                     "center": [10, 10], "member_axis": [0, 1],
                     "member_pitch_mm": 1.27,
                     "p_contacts": [{"ref": "U2", "pad": "7",
                                     "point_mm": [12.0, 9.5]}],
                     "n_contacts": [{"ref": "U2", "pad": "6",
                                     "point_mm": [12.0, 10.5]}]},
                    {"id": "R11|R12",
                     "physical_refs": ["R11", "R12"],
                     "center": [30, 21], "member_axis": [0, 1],
                     "member_pitch_mm": 2.0,
                     "p_contacts": [{"ref": "R11", "pad": "2",
                                     "point_mm": [30.5, 20.0]}],
                     "n_contacts": [{"ref": "R12", "pad": "2",
                                     "point_mm": [30.0, 21.5]}]},
                ],
                "failure_certificate": {
                    "classification": ["insufficient_coupling"],
                    "endpoints": {
                        "start": {"center_mm": [10, 10]},
                        "end": {"center_mm": [30, 21]},
                    },
                    "relief_vectors": [],
                },
            }],
        }

        moves = sp._route_access_move_specs(
            candidate, evidence,
            SimpleNamespace(pins={}, params={
                "pair_lane_alignment_max_mm": 20.0}),
            groups={"R11": ("R11", "C11")})

        station_moves = [row for row in moves
                         if row.get("station") == "R11|R12"]
        alignment = next(row for row in station_moves
                         if row["kind"] ==
                         "pair_endpoint_lane_alignment")
        self.assertEqual(alignment["direction"], "lane-align-exact")
        self.assertEqual(set(alignment["placements"]),
                         {"R11", "R12", "C11"})
        self.assertAlmostEqual(alignment["dx_mm"], 0.0)
        self.assertAlmostEqual(alignment["dy_mm"], -11.0)
        self.assertEqual(
            alignment["pair_failure_witness"]["reason"],
            "insufficient_coupling")

        rotation = next(row for row in station_moves
                        if row["kind"] ==
                        "pair_endpoint_station_rotation"
                        and row["rotation_deg"] == 180.0)
        self.assertEqual(rotation["rotation_center_mm"], [30.0, 21.0])
        self.assertEqual(set(rotation["placements"]),
                         {"R11", "R12", "C11"})
        self.assertEqual(rotation["placements"]["R11"],
                         (30.0, 22.0, 180.0))
        self.assertEqual(rotation["placements"]["R12"],
                         (30.0, 20.0, 270.0))
        self.assertEqual(rotation["placements"]["C11"],
                         (29.0, 22.0, 180.0))
        self.assertAlmostEqual(
            math.dist(rotation["placements"]["R11"][:2],
                      rotation["placements"]["R12"][:2]), 2.0)

        pin_flip = next(row for row in station_moves
                        if row["kind"] ==
                        "pair_endpoint_member_pin_flip")
        self.assertEqual(pin_flip["ref"], "R11")
        self.assertEqual(pin_flip["placements"], {
            "R11": (30.0, 20.0, 180.0)})
        self.assertLess(pin_flip["pin_facing_before"], -0.1)
        self.assertGreater(pin_flip["pin_facing_after"], 0.1)

        compound = next(row for row in station_moves
                        if row["kind"] ==
                        "pair_endpoint_member_pin_flip_lane_alignment")
        self.assertEqual(compound["flipped_ref"], "R11")
        self.assertEqual(set(compound["placements"]),
                         {"R11", "R12", "C11"})
        self.assertEqual(compound["placements"]["R11"][2], 180.0)
        self.assertEqual(compound["placements"]["R12"][2], 90.0)
        self.assertEqual(
            compound["pair_failure_witness"]["reason"],
            "pair_pin_flip_lane_alignment")

    def test_power_replan_budget_prefers_causal_pair_witness(self):
        rows = [
            {"kind": "pair_endpoint_station_shift", "refs": ["R1"],
             "proposal": {"distance_mm": 0.5},
             "old_authority_collision_area_mm2": 0.1},
            {"kind": "shift", "refs": ["C1"],
             "proposal": {"distance_mm": 0.25},
             "old_authority_collision_area_mm2": 0.05},
            {"kind": "pair_failure_portal_shift", "refs": ["R1", "R2"],
             "proposal": {"distance_mm": 1.0},
             "pair_failure_witness": {
                 "classifications": ["reservation_barrier"]},
             "old_authority_collision_area_mm2": 2.0},
        ]

        selected = sp._bounded_power_replan_candidates(rows, 2)

        self.assertEqual(selected[0]["kind"],
                         "pair_failure_portal_shift")
        self.assertEqual(len(selected), 2)

    def test_stale_power_only_craft_conflict_requires_moved_ref_and_clean_rest(self):
        baseline = {
            "pour_territory": {"ok": True, "violations": []},
            "power_body_clearance": {"ok": True, "violations": []},
            "decoupler": {"ok": True, "violations": [], "details": []},
        }
        candidate = copy.deepcopy(baseline)
        candidate["pour_territory"] = {
            "ok": False, "authority": "frozen_pour_state",
            "violations": [{"ref": "U1", "net": "/VIN",
                            "overlap_mm2": 0.25}],
        }

        conflicts = sp.stale_power_only_craft_conflicts(
            candidate, baseline, {"U1"})
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(
            sp.stale_power_only_craft_conflicts(
                candidate, baseline, {"U2"}), [])

        candidate["decoupler"] = {
            "ok": False, "violations": [("C1", "U1", 9.0)],
            "details": [{"cap_ref": "C1", "owner_ref": "U1",
                         "actionable": True, "loop_proxy_mm": 9.0}],
        }
        self.assertEqual(
            sp.stale_power_only_craft_conflicts(
                candidate, baseline, {"U1"}), [])

    def test_pair_blocker_is_prioritized_but_not_treated_as_endpoint(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {
            "D6": (10, 10, 0), "U1": (40, 10, 0),
            "C8": (39, 11, 90), "J_USB": (8, 10, 0),
        }
        evidence = {
            "critical_pair_refs": ["D6", "J_USB", "U1"],
            "critical_pair_blocker_refs": ["C8"],
            "critical_pair_flow_through_refs": ["D6"],
        }

        moves = sp._route_access_move_specs(
            candidate, evidence, SimpleNamespace(pins={}))

        self.assertEqual((moves[0]["ref"], moves[0]["kind"]),
                         ("C8", "rotate_180"))
        directed = [row for row in moves
                    if row["kind"] == "pair_endpoint_cluster_shift"]
        self.assertNotIn("C8", {row["ref"] for row in directed})

    def test_pair_blockers_are_spread_together_along_portal_normal(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {
            "D6": (40, 10, 0), "U1": (10, 10, 0),
            "C8": (12, 11, 90), "R10": (12, 9, 90),
            "J_USB": (42, 10, 0),
        }
        evidence = {
            "critical_pair_refs": ["D6", "J_USB", "U1"],
            "critical_pair_blocker_refs": ["C8", "R10"],
            "critical_pair_flow_through_refs": ["D6"],
            "critical_pair_blocker_relief": [
                {"ref": "C8", "endpoint": "end",
                 "normal": [0, -1], "axis": [-1, 0], "count": 100},
                {"ref": "R10", "endpoint": "end",
                 "normal": [0, -1], "axis": [-1, 0], "count": 80},
            ],
        }

        moves = sp._route_access_move_specs(
            candidate, evidence, SimpleNamespace(pins={}),
            shift_mm=(0.5, 1.0))

        first = moves[0]
        self.assertEqual(first["kind"], "pair_blocker_channel_spread")
        self.assertEqual(set(first["placements"]), {"C8", "R10"})
        # The two bodies already bracket the pair channel; spread them farther
        # apart rather than translating the obstruction as a rigid wall.
        self.assertGreater(first["placements"]["C8"][1], 11)
        self.assertLess(first["placements"]["R10"][1], 9)

    def test_pair_blocker_relief_moves_complete_owned_cells(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {
            "U8": (12, 11, 90), "C8": (13, 11, 90),
            "U9": (12, 9, 90), "R10": (13, 9, 90),
            "U1": (10, 10, 0), "J_USB": (42, 10, 0),
        }
        evidence = {
            "critical_pair_refs": ["J_USB", "U1"],
            "critical_pair_blocker_refs": ["C8", "R10"],
            "critical_pair_blocker_relief": [
                {"ref": "C8", "endpoint": "end",
                 "normal": [0, -1], "axis": [-1, 0], "count": 100},
                {"ref": "R10", "endpoint": "end",
                 "normal": [0, -1], "axis": [-1, 0], "count": 80},
            ],
        }

        moves = sp._route_access_move_specs(
            candidate, evidence, SimpleNamespace(pins={}),
            groups={"U8": ("U8", "C8"),
                    "U9": ("U9", "R10")},
            shift_mm=(0.5,))

        first = moves[0]
        self.assertEqual(first["kind"], "pair_blocker_channel_spread")
        self.assertEqual(
            set(first["placements"]), {"U8", "C8", "U9", "R10"})
        self.assertEqual(
            first["placements"]["U8"][1]
            - candidate.P["U8"][1],
            first["placements"]["C8"][1]
            - candidate.P["C8"][1])

    def test_unchanged_kelvin_still_probes_targeted_refused_pair(self):
        self.assertTrue(sp._critical_probe_after_kelvin(
            base_kelvin_refused=1, candidate_kelvin_refused=1,
            base_pair_refused=1, pair_targeted=True))
        self.assertFalse(sp._critical_probe_after_kelvin(
            base_kelvin_refused=1, candidate_kelvin_refused=2,
            base_pair_refused=1, pair_targeted=True))
        self.assertFalse(sp._critical_probe_after_kelvin(
            base_kelvin_refused=1, candidate_kelvin_refused=1,
            base_pair_refused=1, pair_targeted=False))

    def test_refused_pair_endpoints_own_first_repair_slots(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {"D6": (5, 5, 270), "U1": (20, 20, 0),
                       "C_OTHER": (8, 8, 0), "J_USB": (4, 4, 0)}
        evidence = {
            "critical_pair_refs": ["D6", "J_USB", "U1"],
            "future_congestion": {"pressure_refs": [
                {"ref": "C_OTHER", "pressure_units": 999999}]},
        }
        moves = sp._route_access_move_specs(
            candidate, evidence, SimpleNamespace(pins={}))
        self.assertEqual([(row["ref"], row["kind"]) for row in moves[:2]],
                         [("D6", "rotate_180"),
                          ("U1", "rotate_180")])
        self.assertTrue(all(move["ref"] in {"D6", "U1"}
                            for move in moves[:16]))
        self.assertNotIn("J_USB", {move["ref"] for move in moves})

    def test_refused_kelvin_endpoint_owns_first_repair_slot(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {"RS1": (5, 5, 0), "U10": (20, 20, 90),
                       "C_OTHER": (8, 8, 0)}
        evidence = {
            "critical_kelvin_refs": ["RS1", "U10"],
            "future_congestion": {"pressure_refs": [
                {"ref": "C_OTHER", "pressure_units": 999999}]},
        }
        moves = sp._route_access_move_specs(
            candidate, evidence, SimpleNamespace(pins={"RS1": (5, 5, 0)}))
        self.assertEqual((moves[0]["ref"], moves[0]["kind"]),
                         ("U10", "rotate_180"))
        self.assertTrue(all(move["ref"] == "U10" for move in moves[:8]))

    def test_kelvin_range_certificate_proposes_sufficient_pad_vector_move(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {"RS1": (5, 5, 0), "U10": (15, 5, 90),
                       "C_OTHER": (8, 8, 0)}
        evidence = {
            "critical_kelvin_refs": ["RS1", "U10"],
            "critical_kelvin_refused": [{
                "source_ref": "RS1", "target_ref": "U10",
                "source_position_mm": [5.0, 5.0],
                "target_position_mm": [15.0, 5.0],
                "max_distance_mm": 8.3,
                "required_closer_mm": 1.7,
            }],
        }
        moves = sp._route_access_move_specs(
            candidate, evidence,
            SimpleNamespace(pins={"RS1": (5, 5, 0)}, params={}))
        self.assertEqual(
            [(row["ref"], row["kind"]) for row in moves[:2]],
            [("U10", "kelvin_range_closure"),
             ("U10", "kelvin_range_closure")])
        self.assertAlmostEqual(moves[0]["dx_mm"], -1.9, places=6)
        self.assertAlmostEqual(moves[0]["dy_mm"], 0.0, places=6)
        self.assertNotEqual(
            moves[0]["budget_group"], moves[1]["budget_group"])
        self.assertTrue(any(
            row["kind"] == "kelvin_range_axis_closure"
            for row in moves[:6]))
        self.assertTrue(any(
            row["kind"] == "kelvin_range_rotation_closure"
            for row in moves[:8]))

    def test_kelvin_path_certificate_moves_blocker_and_closes_inward_deficit(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {
            "RS1": (5, 5, 0), "U10": (10, 5, 0),
            "C10": (9.6, 5.0, 0), "U11": (20, 10, 0),
            "C11": (20.5, 10, 0),
        }
        evidence = {
            "critical_kelvin_refs": ["RS1", "U10", "U11"],
            "critical_kelvin_blocker_refs": ["C10"],
            "critical_kelvin_refused": [{
                "net": "/SENSE2_LO", "source_ref": "RS1",
                "target_ref": "U11",
                "reason_kind": "kelvin_path_blocked",
                "inward_vector": [0.0, -1.0],
                "target_inward_mm": 0.27,
                "canonical_min_inward_mm": 0.3,
            }],
            "critical_kelvin_blocker_details": [{
                "kelvin_net": "/SENSE1_LO", "kind": "pad",
                "ref": "C10", "pad": "1", "endpoint_owned": False,
                "position_mm": [9.6, 5.0],
                "bbox_mm": [9.3, 4.7, 9.9, 5.3],
                "leg_start_mm": [10.0, 2.0],
                "leg_end_mm": [10.0, 8.0],
                "leg_index": 0, "path_kind": "canonical",
                "width_mm": 0.25, "clearance_mm": 0.2,
                "source_ref": "RS1", "target_ref": "U10",
            }],
        }
        moves = sp._route_access_move_specs(
            candidate, evidence,
            SimpleNamespace(pins={"RS1": (5, 5, 0)}, params={}),
            groups={"U11": ("U11", "C11")})
        rotations = [row for row in moves
                     if row["kind"] == "kelvin_endpoint_cell_rotation"]
        self.assertEqual([row["rotation_deg"] for row in rotations[:2]],
                         [90.0, 270.0])
        self.assertEqual(set(rotations[0]["placements"]), {"U11", "C11"})
        before_distance = math.hypot(
            candidate.P["C11"][0] - candidate.P["U11"][0],
            candidate.P["C11"][1] - candidate.P["U11"][1])
        after_distance = math.hypot(
            rotations[0]["placements"]["C11"][0]
            - rotations[0]["placements"]["U11"][0],
            rotations[0]["placements"]["C11"][1]
            - rotations[0]["placements"]["U11"][1])
        self.assertAlmostEqual(before_distance, after_distance)
        inward = [row for row in moves
                  if row["kind"] == "kelvin_canonical_inward_closure"]
        self.assertTrue(inward)
        self.assertLess(inward[0]["dy_mm"], 0.0)
        self.assertAlmostEqual(
            inward[0]["placements"]["U11"][1]
            - candidate.P["U11"][1],
            inward[0]["placements"]["C11"][1]
            - candidate.P["C11"][1])
        relief = [row for row in moves
                  if row["kind"] == "kelvin_foreign_blocker_relief"]
        self.assertTrue(relief)
        self.assertEqual(set(relief[0]["placements"]), {"C10"})
        self.assertLess(relief[0]["dx_mm"], 0.0)

    def test_blockage_witness_prioritizes_perpendicular_escape_channel(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {"R_ESCAPE": (5, 5, 0), "C_OTHER": (8, 8, 0)}
        evidence = {
            "pin_access_blocked": [],
            "blockage_witnesses": [{
                "kind": "over_capacity", "overuse": 2.0,
                "escape_directions": ["N", "S"],
                "candidate_refs": [{
                    "ref": "R_ESCAPE", "role": "residual_endpoint"}],
            }],
            "future_congestion": {"pressure_refs": [
                {"ref": "C_OTHER", "pressure_units": 9999}]},
        }
        moves = sp._route_access_move_specs(
            candidate, evidence, SimpleNamespace(pins={}))
        self.assertEqual(moves[0]["ref"], "R_ESCAPE")
        self.assertEqual(moves[0]["kind"], "rotate_180")
        escape = [move for move in moves
                  if move["ref"] == "R_ESCAPE"
                  and move["kind"] == "escape_shift"]
        self.assertTrue(escape)
        self.assertEqual({move["dx_mm"] for move in escape}, {0.0})
        self.assertEqual({move["dy_mm"] for move in escape}, {-0.25, 0.25,
                                                               -0.5, 0.5})

    def test_bounded_repair_accepts_only_full_key_improvement(self):
        candidate = self._cand(0, 0, 3.0, 0.0)
        candidate.P = {"R37": (5, 5, 0)}
        candidate.route_preflight = {
            "fanout_blocked_count": 0,
            "pin_access_blocked_count": 1,
            "pin_access_blocked": [{
                "ref": "R37", "blocked_options": []}],
            "unroutable_count": 0,
            "residual_overuse_escaped": 5,
            "residual_overuse": 5,
        }
        cfg = SimpleNamespace(pins={}, params={})

        def fake_analyze(_path, **kwargs):
            congestion = (None if not kwargs["run_congestion"] else {
                "unroutable_count": 0,
                "residual_overuse_escaped": 4,
                "residual_overuse": 4})
            return {"fanout": {"blocked": 0},
                    "pin_access": {"blocked_count": 0, "blocked": []},
                    "stackup": {}, "congestion": congestion}

        incremental_context = SimpleNamespace(
            board_db=SimpleNamespace(fingerprint="f" * 64),
            build_wall_s=0.01)
        incremental_report = {
            "fanout": {"blocked": 0},
            "pin_access": {"blocked_count": 0, "blocked": []},
            "stackup": {}, "congestion": None,
        }

        with mock.patch.object(sp, "View", return_value=SimpleNamespace(
                nl=SimpleNamespace(nets={}))), \
                mock.patch.object(sp, "_fp_of", return_value={"R37": "fp"}), \
                mock.patch.object(sp, "_classify",
                                  return_value=({}, [], [], ["R37"])), \
                mock.patch.object(sp, "derive_passive_spec",
                                  return_value=({}, {})), \
                mock.patch.object(sp, "_count_overlaps", return_value=0), \
                mock.patch.object(sp, "materialize",
                                  return_value="board") as materialize_mock, \
                mock.patch.object(sp, "_oracle_decoupler_adjacency",
                                  return_value={"ok": True,
                                                "violations": []}), \
                mock.patch("cec_pcb.courtyard_bbox",
                           return_value=(1, 2, 1, 2)), \
                mock.patch("cec_route_preflight.prepare_incremental_access",
                           return_value=incremental_context), \
                mock.patch("cec_route_preflight.analyze_incremental_access",
                           return_value=incremental_report), \
                mock.patch("cec_route_preflight.analyze",
                           side_effect=fake_analyze):
            repaired, report = sp.repair_route_preflight(
                cfg, candidate, max_trials=1, full_evals=1)
        self.assertTrue(report["accepted"])
        self.assertEqual(repaired.P["R37"][2], 180)
        self.assertEqual(repaired.route_preflight[
            "pin_access_blocked_count"], 0)
        self.assertTrue(report["incremental_geometry"]["enabled"])
        self.assertEqual(report["incremental_geometry"]["fallback_count"], 0)
        self.assertEqual(report["authority"]["exact_computed"], 1)
        self.assertEqual(report["authority"]["incremental_screened"], 1)
        # Baseline plus the access-improving finalist; no quick-trial board.
        self.assertEqual(materialize_mock.call_count, 2)


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


class TestSenseSeatCurrentApproach(unittest.TestCase):
    def test_primary_sensor_uses_side_opposite_terminal_approach(self):
        mid = (10.0, 10.0)
        normal = (1.0, 0.0)
        self.assertEqual(
            sp._sense_seat_primary_side(
                mid, normal, [(4.0, 3.0), (5.0, 17.0)]),
            1.0)
        self.assertEqual(
            sp._sense_seat_primary_side(
                mid, normal, [(15.0, 3.0), (16.0, 17.0)]),
            -1.0)

    def test_symmetric_or_unknown_approach_is_deterministic(self):
        self.assertEqual(
            sp._sense_seat_primary_side(
                (10.0, 10.0), (1.0, 0.0), [(5.0, 0.0), (15.0, 20.0)]),
            1.0)
        self.assertEqual(
            sp._sense_seat_primary_side(
                (10.0, 10.0), (1.0, 0.0), []),
            1.0)


class TestIndependentDecouplerBatches(unittest.TestCase):
    def test_perpendicular_move_can_preserve_declared_edge_overhang(self):
        self.assertFalse(sp._worsens_existing_outline_overhang(
            (8.0, 12.0, 2.0, 5.0),
            (8.0, 12.0, 1.0, 4.0), 10.0, 10.0))
        self.assertTrue(sp._worsens_existing_outline_overhang(
            (8.0, 12.1, 2.0, 5.0),
            (8.0, 12.0, 1.0, 4.0), 10.0, 10.0))
        self.assertTrue(sp._worsens_existing_outline_overhang(
            (-0.1, 2.0, 2.0, 5.0),
            (0.0, 2.0, 1.0, 4.0), 10.0, 10.0))

    def test_disjoint_owner_repairs_are_combined_in_bounded_prefixes(self):
        candidate = SimpleNamespace(P={
            "U1": (1.0, 1.0, 0.0), "C1": (2.0, 1.0, 0.0),
            "U2": (5.0, 1.0, 0.0), "C2": (6.0, 1.0, 0.0),
            "U3": (9.0, 1.0, 0.0), "C3": (10.0, 1.0, 0.0),
        })
        families = [[
            {"kind": "decoupler_cell_reorient", "ref": "U1",
             "owner_ref": "U1", "position": (1.0, 1.0, 90.0),
             "placements": {"U1": (1.0, 1.0, 90.0),
                              "C1": (1.0, 2.0, 90.0)}},
            {"kind": "decoupler_cell_reorient", "ref": "U2",
             "owner_ref": "U2", "position": (5.0, 1.0, 90.0),
             "placements": {"U2": (5.0, 1.0, 90.0),
                              "C2": (5.0, 2.0, 90.0)}},
            {"kind": "decoupler_cell_reorient", "ref": "U3",
             "owner_ref": "U3", "position": (9.0, 1.0, 90.0),
             "placements": {"U3": (9.0, 1.0, 90.0),
                              "C3": (9.0, 2.0, 90.0)}},
        ]]

        batches = sp._independent_decoupler_batch_specs(
            candidate, families)

        self.assertEqual([row["owners"] for row in batches],
                         [["U1", "U2"], ["U1", "U2", "U3"]])
        self.assertEqual(set(batches[-1]["placements"]),
                         {"U1", "C1", "U2", "C2", "U3", "C3"})

    def test_shared_moved_ref_is_not_batched_twice(self):
        candidate = SimpleNamespace(P={
            "U1": (1.0, 1.0, 0.0), "C1": (2.0, 1.0, 0.0),
            "U2": (5.0, 1.0, 0.0),
        })
        families = [[
            {"kind": "decoupler_cell_reorient", "ref": "U1",
             "owner_ref": "U1", "position": (1.0, 1.0, 90.0),
             "placements": {"U1": (1.0, 1.0, 90.0),
                              "C1": (1.0, 2.0, 90.0)}},
            {"kind": "decoupler_cell_reorient", "ref": "U2",
             "owner_ref": "U2", "position": (5.0, 1.0, 90.0),
             "placements": {"U2": (5.0, 1.0, 90.0),
                              "C1": (5.0, 2.0, 90.0)}},
        ]]
        self.assertEqual(
            sp._independent_decoupler_batch_specs(candidate, families), [])

    def test_exact_single_owner_winners_are_composed_after_evaluation(self):
        current = SimpleNamespace(P={
            "C1": (1.0, 1.0, 0.0),
            "C2": (5.0, 1.0, 0.0),
            "C3": (9.0, 1.0, 0.0),
        })
        finalists = []
        for index, (owner, ref, x) in enumerate((
                ("U1", "C1", 2.0),
                ("U2", "C2", 6.0),
                ("U3", "C3", 10.0))):
            trial = SimpleNamespace(P=dict(current.P))
            trial.P[ref] = (x, 2.0, 90.0)
            finalists.append((
                (0, 2, index), 0, index,
                {"kind": "decoupler_owner_tangent",
                 "ref": ref, "owner_ref": owner},
                trial, {"ok": False}))

        batches = sp._independent_monotonic_finalist_batches(
            current, finalists)

        self.assertEqual(
            [row["move"]["owners"] for row in batches],
            [["U1", "U2"], ["U1", "U2", "U3"]])
        self.assertEqual(
            set(batches[-1]["move"]["placements"]),
            {"C1", "C2", "C3"})
        self.assertEqual(
            batches[-1]["trial"].P["C3"], (10.0, 2.0, 90.0))

    def test_exact_winners_with_shared_transform_are_not_composed(self):
        current = SimpleNamespace(P={"C1": (1.0, 1.0, 0.0)})
        left = SimpleNamespace(P={"C1": (2.0, 1.0, 0.0)})
        right = SimpleNamespace(P={"C1": (3.0, 1.0, 0.0)})
        finalists = [
            ((0, 1), 0, 0, {"ref": "C1", "owner_ref": "U1"},
             left, {"ok": False}),
            ((0, 1), 0, 1, {"ref": "C1", "owner_ref": "U2"},
             right, {"ok": False}),
        ]

        self.assertEqual(
            sp._independent_monotonic_finalist_batches(
                current, finalists), [])


if __name__ == "__main__":
    unittest.main()
