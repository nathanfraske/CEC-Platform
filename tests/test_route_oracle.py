"""ROUTE-ORACLE GRADER (placer-feasibility SLICE-1a, docs/placer-feasibility-2026-06-30.md).

The placer used to select on the CHEAP placement_proxy (HPWL/RUDY/thermal), which does NOT predict
real routability -> it converged on placements that proxy-look-good but route DIRTY. route_oracle_grade
closes that: it grades a placement by ACTUALLY ROUTING it (the proven gate-clean recipe) and reading the
REAL post-route ACCEPT CONJUNCTION, including the complete scorer gate, actual-pour incursion,
foreign-on-pour, thermal, and routing-completion terms.

Three layers, mirroring tests/test_placer_oracle.py's convention (logic host-side, real-board pcbnew-gated):
  * TestOracleLogic        -- the pure grading LOGIC (classification, sort_key, opt-in switch). Always runs.
  * TestOracleConstruction -- pcbnew-gated: the grader can never pass a board the real route fails (the
                              committed UNROUTED placement, route=False, FAILS) + the gate==AND invariant.
  * TestOracleRoute        -- explicit opt-in real routes on committed legacy fixtures. Both are
                              rejected by today's stricter gate; this protects against restoring the
                              stale claim that eps-rev3-n2 is gate-clean.
"""
import os
import json
import sys
import tempfile
import unittest
import contextlib
from types import SimpleNamespace
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import cec_synth_pipeline as sp                                  # noqa: E402
import cec_router                                                # noqa: E402
import cec_pourplan                                              # noqa: E402

try:
    import pcbnew                                                # noqa: F401
    HAVE_PCBNEW = True
except Exception:
    HAVE_PCBNEW = False

ROOT = os.path.normpath(os.path.join(HERE, ".."))
FIX = os.path.join(HERE, "golden", "fixtures", "route-oracle")
N2_PCB = os.path.join(FIX, "eps-rev3-n2.kicad_pcb")              # legacy near-pass; not current-clean
WIDEGAP_PCB = os.path.join(FIX, "eps-rev3-widegap-m.kicad_pcb")  # proxy-better-but-dirty parent -> FAIL
GOLDEN_EPS = os.path.join(ROOT, "tests", "golden", "eps-8pin", "eps8pin-module.kicad_pcb")  # UNROUTED
CLEAN_PCIE_DB = os.path.join(
    ROOT, "beta", "output-daughterboards", "pcie-out-db",
    "pcie-out-db-board.kicad_pcb")


class _R:
    """A tiny stand-in for cec_score.Rules carrying just the pair/net fields _classify_unconnected reads."""
    def __init__(self, kelvin_pairs=(), diff_pairs=(), nets_12v=()):
        self.kelvin_pairs = list(kelvin_pairs)
        self.diff_pairs = list(diff_pairs)
        self.nets_12v = list(nets_12v)


# ===================================================================== logic (no pcbnew)
class TestOracleLogic(unittest.TestCase):
    def test_priority_power_layer_search_is_bounded_and_board_agnostic(self):
        orders = sp._priority_power_layer_orders(
            ("In3.Cu", "B.Cu", "F.Cu", "In2.Cu"),
            ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"))

        self.assertEqual(orders[0],
                         ("In3.Cu", "B.Cu", "F.Cu", "In2.Cu"))
        self.assertEqual(orders[1], ("B.Cu", "In3.Cu", "In2.Cu"))
        self.assertEqual(orders[2], ("B.Cu", "F.Cu"))
        self.assertLessEqual(len(orders), 3)

    def test_two_layer_priority_power_candidate_retains_both_faces(self):
        orders = sp._priority_power_layer_orders(
            ("F.Cu", "B.Cu"), ("F.Cu", "B.Cu"))

        self.assertEqual(orders, [("F.Cu", "B.Cu"),
                                  ("B.Cu", "F.Cu")])

    def test_exact_open_power_asks_are_promoted_stably(self):
        asks = [
            {"net": "RAIL_A", "tag": 1},
            {"net": "RAIL_B", "tag": 2},
            {"net": "RAIL_C", "tag": 3},
            {"net": "RAIL_B", "tag": 4},
        ]

        promoted = sp._promote_priority_power_asks(
            asks, ["RAIL_C", "RAIL_B", "RAIL_C"])

        self.assertEqual(
            [(row["net"], row["tag"]) for row in promoted],
            [("RAIL_C", 3), ("RAIL_B", 2), ("RAIL_B", 4),
             ("RAIL_A", 1)])
        self.assertEqual(
            sp._promote_priority_power_asks(promoted,
                                            ["RAIL_C", "RAIL_B"]),
            promoted)

    def test_exact_power_admission_refuses_residual_protected_open(self):
        bbox = SimpleNamespace(GetWidth=lambda: 80_000_000,
                               GetHeight=lambda: 60_000_000)
        board = SimpleNamespace(
            Zones=lambda: [], GetFootprints=lambda: [],
            BuildConnectivity=lambda: None,
            GetBoardEdgesBoundingBox=lambda: bbox)
        filler = SimpleNamespace(Fill=lambda _zones: None)
        baseline = SimpleNamespace(
            drc=0, unconnected=2, drc_types={},
            detail={"unconn_nets": ["RAIL", "SIG"]})
        exact_before = SimpleNamespace(
            drc=0, unconnected=2, drc_types={},
            detail={"unconn_nets": ["RAIL", "SIG"]})
        exact_after = SimpleNamespace(
            drc=0, unconnected=2, drc_types={},
            detail={"unconn_nets": ["RAIL", "SIG"]})
        repair = {"closed": 0, "legs": 0, "refused": 1,
                  "far": 0, "cross_layer": 0}
        prune = {"vias": 0, "stubs": 0, "unlanded_pofv": 0,
                 "detail": []}
        with mock.patch("pcbnew.LoadBoard", return_value=board), \
                mock.patch("pcbnew.SaveBoard"), \
                mock.patch("pcbnew.ZONE_FILLER", return_value=filler), \
                mock.patch.object(
                    sp.cec_score, "score",
                    side_effect=[exact_before, exact_after]), \
                mock.patch("cec_fr._project_netclass_resolver",
                           return_value=lambda _net: {}), \
                mock.patch("cec_fr.synthesize_lastmile",
                           return_value=repair), \
                mock.patch("cec_fr.prune_redundant_dangling_pickups",
                           return_value=prune), \
                mock.patch("cec_current_topology.authority_connectivity",
                           return_value={"available": False,
                                         "connected": False}):
            report = sp._admit_priority_power_candidate(
                "candidate.kicad_pcb", ["RAIL"], baseline)

        self.assertFalse(report["passed"])
        self.assertEqual(report["open_after"], ["RAIL"])
        self.assertEqual(
            report["reason"],
            "protected_rail_open_after_exact_fill_and_guarded_repair")

    def test_exact_power_admission_uses_full_board_maze_budget(self):
        bbox = SimpleNamespace(GetWidth=lambda: 80_000_000,
                               GetHeight=lambda: 60_000_000)
        board = SimpleNamespace(
            Zones=lambda: [], GetFootprints=lambda: [],
            BuildConnectivity=lambda: None,
            GetBoardEdgesBoundingBox=lambda: bbox)
        filler = SimpleNamespace(Fill=lambda _zones: None)
        baseline = SimpleNamespace(
            drc=0, unconnected=1, drc_types={},
            detail={"unconn_nets": ["RAIL"]})
        exact_before = SimpleNamespace(
            drc=0, unconnected=1, drc_types={},
            detail={"unconn_nets": ["RAIL"]})
        exact_after = SimpleNamespace(
            drc=0, unconnected=0, drc_types={},
            detail={"unconn_nets": []})
        repair = {"closed": 1, "legs": 3, "refused": 0,
                  "far": 0, "cross_layer": 0}
        prune = {"vias": 0, "stubs": 0, "unlanded_pofv": 0,
                 "detail": []}
        with mock.patch("pcbnew.LoadBoard", return_value=board), \
                mock.patch("pcbnew.SaveBoard"), \
                mock.patch("pcbnew.ZONE_FILLER", return_value=filler), \
                mock.patch.object(
                    sp.cec_score, "score",
                    side_effect=[exact_before, exact_after]), \
                mock.patch("cec_fr._project_netclass_resolver",
                           return_value=lambda _net: {}), \
                mock.patch("cec_fr.synthesize_lastmile",
                           return_value=repair) as lastmile, \
                mock.patch("cec_fr.prune_redundant_dangling_pickups",
                           return_value=prune), \
                mock.patch("cec_current_topology.authority_connectivity",
                           return_value={"available": False,
                                         "connected": False}):
            report = sp._admit_priority_power_candidate(
                "candidate.kicad_pcb", ["RAIL"], baseline)

        self.assertTrue(report["passed"])
        self.assertAlmostEqual(lastmile.call_args.kwargs["maze_max_mm"],
                               100.0)

    def test_exact_power_admission_refuses_new_fault_even_if_drc_total_drops(self):
        board = SimpleNamespace(
            Zones=lambda: [], GetFootprints=lambda: [],
            BuildConnectivity=lambda: None)
        filler = SimpleNamespace(Fill=lambda _zones: None)
        old_faults = [
            {"type": "clearance", "items": [
                {"uuid": "old-a"}, {"uuid": "old-b"}]},
            {"type": "clearance", "items": [
                {"uuid": "old-c"}, {"uuid": "old-d"}]},
        ]
        new_short = {"type": "shorting_items", "items": [
            {"uuid": "locked-via"}, {"uuid": "new-track"}]}
        baseline = SimpleNamespace(
            drc=2, unconnected=0, drc_types={"clearance": 2},
            detail={"unconn_nets": [],
                    "structural_violations": old_faults})
        exact_before = baseline
        exact_after = SimpleNamespace(
            drc=1, unconnected=0,
            drc_types={"shorting_items": 1},
            detail={"unconn_nets": [],
                    "structural_violations": [new_short]})
        prune = {"vias": 0, "stubs": 0, "unlanded_pofv": 0,
                 "detail": []}
        with mock.patch("pcbnew.LoadBoard", return_value=board), \
                mock.patch("pcbnew.SaveBoard"), \
                mock.patch("pcbnew.ZONE_FILLER", return_value=filler), \
                mock.patch.object(
                    sp.cec_score, "score",
                    side_effect=[exact_before, exact_after]), \
                mock.patch("cec_fr.prune_redundant_dangling_pickups",
                           return_value=prune), \
                mock.patch("cec_current_topology.authority_connectivity",
                           return_value={"available": True,
                                         "connected": True}):
            report = sp._admit_priority_power_candidate(
                "candidate.kicad_pcb", ["RAIL"], baseline)

        self.assertFalse(report["passed"], report)
        self.assertEqual(report["reason"], "new_structural_drc_identity")
        self.assertTrue(report["new_structural_drc"])

    def test_exact_power_admission_runs_in_single_load_worker(self):
        admitted = {"schema": 1, "passed": True, "open_after": []}

        def worker(command, **_kwargs):
            self.assertIn("cec_power_artifact_worker.py", command[1])
            self.assertEqual(command[2], "admit")
            self.assertEqual(command[3], "candidate.kicad_pcb")
            self.assertEqual(
                json.loads(command[command.index("--nets-json") + 1]),
                ["RAIL"])
            self.assertEqual(
                command[command.index("--baseline-board") + 1],
                "baseline.kicad_pcb")
            report_path = command[command.index("--report") + 1]
            with open(report_path, "w", encoding="utf-8") as sink:
                json.dump(admitted, sink)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(sp.subprocess, "run", side_effect=worker):
            report = sp._admit_priority_power_candidate_isolated(
                "candidate.kicad_pcb", ["RAIL"],
                "baseline.kicad_pcb")

        self.assertEqual(report, admitted)

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
        # among failures: safety, critical opens, foreign copper, then DRC;
        # ordinary opens are a safer last-mile repair than invalid geometry.
        near = (1, 0, 0, 1, 0, 1, 12.0)
        kelvin_broken = (1, 1, 0, 8, 0, 0, 12.0)
        foreign_dirty = (1, 0, 6, 0, 0, 0, 12.0)
        drc_dirty = (1, 0, 0, 1, 1, 0, 12.0)
        self.assertLess(near, foreign_dirty)
        self.assertLess(foreign_dirty, kelvin_broken)
        self.assertLess(near, drc_dirty)

    def test_opt_in_switch(self):
        cfg = sp.Config(board="eps-8pin")
        self.assertFalse(sp._route_oracle_enabled(cfg))       # default OFF
        cfg.params["route_oracle"] = True
        self.assertTrue(sp._route_oracle_enabled(cfg))

    def test_route_swarm_inherits_and_restores_board_recipe(self):
        cfg = SimpleNamespace(
            board="hub-standard-rev2",
            params={"power_pickup": True, "overunder": True,
                    "pour_reserve": True, "lastmile": True,
                    "critical_route_nets": ("BLACKOUT_SENSE",
                                             "PWR_FAIL_INT")})

        def board_spec(board, _out, **_kwargs):
            self.assertEqual(os.environ.get("CEC_POWER_PICKUP"), "1")
            self.assertEqual(os.environ.get("CEC_OVERUNDER"), "1")
            self.assertEqual(os.environ.get("CEC_POUR_RESERVE"), "1")
            self.assertEqual(os.environ.get("CEC_LASTMILE"), "1")
            self.assertEqual(
                json.loads(os.environ["CEC_CRITICAL_ROUTE_NETS_JSON"]),
                ["BLACKOUT_SENSE", "PWR_FAIL_INT"])
            self.assertIs(_kwargs["precision"], True)
            self.assertIs(_kwargs["precision_pair_grid"], True)
            return SimpleNamespace(board=board), "hub"

        def route(board, _spec, **_kwargs):
            self.assertEqual(os.environ.get("CEC_POWER_PICKUP"), "1")
            self.assertIn("CEC_CRITICAL_ROUTE_NETS_JSON", os.environ)
            return board + ".routed", {"ok": True}

        names = ("CEC_POWER_PICKUP", "CEC_OVERUNDER",
                 "CEC_POUR_RESERVE", "CEC_LASTMILE",
                 "CEC_CRITICAL_ROUTE_NETS_JSON")
        saved = {name: os.environ.pop(name, None) for name in names}
        try:
            with mock.patch("cec_router.board_spec",
                            side_effect=board_spec), \
                    mock.patch("cec_router.route", side_effect=route):
                output, log = sp.route_swarm(
                    cfg, board="placed.kicad_pcb", verbose=False)
            self.assertEqual(output, "placed.kicad_pcb.routed")
            self.assertEqual(log, {"ok": True})
            self.assertTrue(all(name not in os.environ for name in names))
        finally:
            for name, value in saved.items():
                if value is not None:
                    os.environ[name] = value

    def test_route_swarm_keeps_explicit_precision_ablation(self):
        cfg = SimpleNamespace(
            board="hub-standard-rev2",
            params={"wave_precision": True, "wave_pair_grid": True})

        def board_spec(board, _out, **kwargs):
            self.assertIs(kwargs["precision"], False)
            self.assertIs(kwargs["precision_pair_grid"], False)
            return SimpleNamespace(board=board), "hub"

        with mock.patch("cec_router.board_spec", side_effect=board_spec), \
                mock.patch("cec_router.route",
                           return_value=("placed.routed", {"ok": True})):
            output, _log = sp.route_swarm(
                cfg, board="placed.kicad_pcb", verbose=False,
                precision=False, precision_pair_grid=False)
        self.assertEqual(output, "placed.routed")

    def test_cli_policy_surrounds_recipe_compilation_and_route(self):
        """The CLI must compile the recipe inside the selected policy."""
        marker = "CEC_TEST_ROUTE_POLICY_SCOPE"

        @contextlib.contextmanager
        def policy_scope(_params):
            old = os.environ.get(marker)
            os.environ[marker] = "active"
            try:
                yield
            finally:
                if old is None:
                    os.environ.pop(marker, None)
                else:
                    os.environ[marker] = old

        def board_spec(board, _out, **_kwargs):
            self.assertEqual(os.environ.get(marker), "active")
            return SimpleNamespace(board=board), "hub"

        def route(board, _spec, **_kwargs):
            self.assertEqual(os.environ.get(marker), "active")
            log = SimpleNamespace(final={})
            log.to_json = lambda path: path
            return board + ".routed", log

        bbox = SimpleNamespace(GetWidth=lambda: 86_100_000,
                               GetHeight=lambda: 74_100_000)
        pcb = SimpleNamespace(GetBoardEdgesBoundingBox=lambda: bbox)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cec_router, "find_board",
                                  return_value="placed.kicad_pcb"), \
                mock.patch("pcbnew.LoadBoard", return_value=pcb), \
                mock.patch("cec_fresh_wave._placement_params",
                           return_value={"power_pickup": True}), \
                mock.patch.object(sp, "_oracle_env", side_effect=policy_scope), \
                mock.patch.object(cec_router, "board_spec", side_effect=board_spec), \
                mock.patch.object(cec_router, "route", side_effect=route), \
                mock.patch("cec_ledger.append", return_value={"run_id": "test"}), \
                mock.patch("cec_corpus_compile.evaluate_param_deltas",
                           return_value=[]):
            rc = cec_router.main([
                "--board", "placed.kicad_pcb",
                "--placement-policy", "hub-standard-rev2",
                "--out", tmp,
            ])
        self.assertEqual(rc, 0)
        self.assertNotIn(marker, os.environ)

    def test_config_load_uses_current_beta_board_contract(self):
        cfg = sp.Config.load(os.path.join(ROOT, "beta",
                                          "hub-standard-rev2"))
        self.assertTrue(cfg.params["power_pickup"])
        self.assertTrue(cfg.params["overunder"])
        self.assertTrue(cfg.params["pour_reserve"])
        self.assertTrue(cfg.params["lastmile"])
        self.assertEqual(
            tuple(cfg.params["critical_route_nets"]),
            ("BLACKOUT_SENSE", "COMP_THRESH", "PWR_FAIL_INT"))
        self.assertEqual(cfg.params["stackup_profile"],
                         "jlcpcb_6l_pofv_signal")

        # Explicit callers keep the final say for controlled A/B experiments.
        ablated = sp.Config.load(
            os.path.join(ROOT, "beta", "hub-standard-rev2"),
            params={"power_pickup": False})
        self.assertFalse(ablated.params["power_pickup"])
        cfg.params["route_oracle"] = False
        os.environ["CEC_ROUTE_ORACLE"] = "1"
        try:
            self.assertTrue(sp._route_oracle_enabled(cfg))    # env override
        finally:
            os.environ.pop("CEC_ROUTE_ORACLE", None)

    def test_production_board_spec_consumes_compiled_pour_plan(self):
        """The route-swarm entry point must not re-derive away placer asks."""
        rules = _R()
        compiled_hints = [{"name": "rail-reservation", "layers": ("In3.Cu",)}]
        compiled_pours = [{"net": "+5VSB", "layer": "In3.Cu",
                           "polygon": [(0.0, 0.0), (1.0, 0.0),
                                       (1.0, 1.0), (0.0, 1.0)]}]
        with mock.patch.object(cec_router, "find_board",
                               return_value="/tmp/hub/placed.kicad_pcb"), \
                mock.patch.object(cec_router.os, "makedirs"), \
                mock.patch.object(cec_router.cec_score.Rules, "from_board",
                                   return_value=rules), \
                mock.patch.object(sp, "_oracle_hints_pours",
                                   return_value=(compiled_hints, compiled_pours, rules)), \
                mock.patch.object(cec_router.cec_fr, "fiducial_keepouts",
                                   return_value=[]), \
                mock.patch.object(cec_router.cec_fr,
                                   "laid_pipeline_pour_keepouts", return_value=[]), \
                mock.patch.object(cec_router.cec_fr, "derive_power_pours") as legacy:
            spec, _name = cec_router.board_spec("hub-standard-rev2", "/tmp/out",
                                                seeds=(0,))
        self.assertEqual(spec.power_pours, compiled_pours)
        self.assertIn(compiled_hints[0], spec.regions[0].hints)
        legacy.assert_not_called()

    def test_explicit_ask_survives_unrelated_recipe_change(self):
        """Cable-only recipe flags cannot erase exact-signature Hub intent."""
        with tempfile.TemporaryDirectory() as tmp:
            board = os.path.join(tmp, "hub.kicad_pcb")
            sidecar = os.path.join(tmp, "hub.pourplan.json")
            with open(sidecar, "w", encoding="utf-8") as fh:
                json.dump({
                    "board_sig": "exact",
                    "recipe": {"uniform": False},
                    "specs": [{
                        "net": "+5VSB", "layers": ["In3.Cu"],
                        "shape": "rect", "polygon": [[0, 0], [2, 0],
                                                         [2, 1], [0, 1]],
                        "region": [0, 0, 2, 1], "priority": 2,
                        "provenance": "placer_ask", "evac": False,
                    }],
                }, fh)
            fresh = cec_pourplan.PourPlan(
                specs=[], board_sig="exact", recipe={"uniform": True})
            fresh._board = object()
            with mock.patch.object(cec_pourplan.PourPlan, "from_board",
                                   return_value=fresh), \
                    mock.patch.object(cec_pourplan.PourPlan, "recipe_from_env",
                                      return_value={"uniform": True}):
                loaded = sp._load_pourplan_sidecar(board, _R())
        self.assertEqual(len(loaded.specs), 1)
        self.assertEqual(loaded.specs[0].net, "+5VSB")
        self.assertEqual(loaded.specs[0].layers, ("In3.Cu",))

    def test_fail_dict_is_worst_rank(self):
        d = sp._oracle_fail_dict("lbl", route_s=1.0, error="boom")
        self.assertFalse(d["gate"])
        self.assertEqual(d["sort_key"][0], 1)
        self.assertGreaterEqual(d["sort_key"][1], 9)          # max safety-fail weight

    def test_gate_schema_includes_actual_pour_incursion(self):
        terms = {name: True for name in sp._ROUTE_ORACLE_GATE_TERMS}
        self.assertTrue(sp._route_oracle_accepts(terms))
        terms["incursion_ok"] = False
        self.assertFalse(sp._route_oracle_accepts(terms))
        with self.assertRaises(ValueError):
            sp._route_oracle_accepts({k: v for k, v in terms.items() if k != "incursion_ok"})

    def test_gate_schema_includes_current_injection_admission(self):
        terms = {name: True for name in sp._ROUTE_ORACLE_GATE_TERMS}
        terms["injection_ok"] = False
        self.assertFalse(sp._route_oracle_accepts(terms))
        with self.assertRaises(ValueError):
            sp._route_oracle_accepts({
                key: value for key, value in terms.items()
                if key != "injection_ok"})

    def test_release_pair_gate_delegates_to_physical_pair_authority(self):
        physical = {
            "ok": False,
            "violations": ["CAN coupling below limit"],
            "pairs": [{
                "p": "/SHEET/CAN_H", "n": "/SHEET/CAN_L",
                "length_p_mm": 12.0, "length_n_mm": 11.0,
                "skew_mm": 1.0, "coupled_coverage_pct": 20.0,
                "reference_coverage_pct": 100.0,
            }],
        }
        with mock.patch(
                "cec_constraints.high_speed_pair_summary",
                return_value=physical) as authority:
            result = sp._oracle_pair_quality("candidate.kicad_pcb")
        authority.assert_called_once_with("candidate.kicad_pcb")
        self.assertFalse(result["ok"])
        self.assertEqual(result["violations"], physical["violations"])
        self.assertEqual(result["authority"],
                         "cec_constraints.high_speed_pair_summary")
        self.assertEqual(
            result["pairs"]["/SHEET/CAN_H|/SHEET/CAN_L"]
            ["coupled_coverage_pct"], 20.0)


# ===================================================================== construction invariant (pcbnew)
@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(GOLDEN_EPS),
                     "pcbnew + the committed golden eps placement required")
class TestOracleConstruction(unittest.TestCase):
    @unittest.skipUnless(os.path.isfile(CLEAN_PCIE_DB),
                         "clean current daughterboard required")
    def test_clean_input_bypasses_router_and_is_graded_as_is(self):
        with mock.patch(
                "cec_fr.run_freerouting",
                side_effect=AssertionError("clean input must not invoke router")):
            r = sp.route_oracle_grade(
                CLEAN_PCIE_DB, route=True, thermal="lazy")
        self.assertTrue(r["route_requested"])
        self.assertTrue(r["route_bypassed_clean_input"])
        self.assertEqual(r["routed"], CLEAN_PCIE_DB)
        self.assertEqual((r["drc"], r["unconnected"]), (0, 0))

    def test_unrouted_board_can_never_pass(self):
        # route=False grades the board AS-IS. The committed eps placement is UNROUTED -> the real route
        # state fails -> the grader MUST fail. (The grader can never pass a board the real route fails.)
        r = sp.route_oracle_grade(GOLDEN_EPS, route=False, thermal="lazy")
        self.assertFalse(r["gate"])
        self.assertFalse(r["kelvin_ok"])                      # nothing is routed
        self.assertEqual(r["sort_key"][0], 1)

    def test_gate_is_the_full_conjunction(self):
        # gate == AND of every term, never a subset -- on a REAL as-is grade.
        r = sp.route_oracle_grade(GOLDEN_EPS, route=False, thermal="lazy")
        self.assertEqual(r["gate"], all(r["gate_terms"].values()))
        self.assertIn("incursion_ok", r["gate_terms"])


# ===================================================================== real route+grade TEETH (pcbnew+FR)
@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(N2_PCB) and os.path.isfile(WIDEGAP_PCB)
                     and os.environ.get("CEC_RUN_REAL_ROUTER") == "1",
                     "set CEC_RUN_REAL_ROUTER=1 for the minute-scale real-router fixtures")
class TestOracleRoute(unittest.TestCase):
    """Real Freerouting routes; always explicit because the pair takes minutes."""

    @classmethod
    def setUpClass(cls):
        # craft_gates=False: these tests validate the ORACLE MECHANICS (route->grade->
        # invariants); the 2026-07-08 placement-craft terms (decoupler adjacency, pair
        # skew, bodies-in-pours) are a NEW standard the frozen fixture predates -- the
        # fixture's C1 is genuinely 62mm stranded. Re-freeze under the new standard once
        # a craft-clean winner exists (FOLLOWUPS.md).
        cls.n2 = sp.route_oracle_grade(N2_PCB, passes=8, opt=12, craft_gates=False)
        cls.wg = sp.route_oracle_grade(WIDEGAP_PCB, passes=8, opt=12, craft_gates=False)

    def test_legacy_n2_is_not_claimed_gate_clean(self):
        r = self.n2
        self.assertFalse(r["gate"], r["reasons"])
        self.assertTrue(r["kelvin_ok"] and r["diffpair_ok"])
        self.assertGreater(r["drc"], 0)
        self.assertEqual((r["foreign"]["tracks"], r["foreign"]["vias"]), (0, 0))
        self.assertFalse(r["thermal_ok"])
        self.assertTrue(r["unconn_critical"])
        self.assertEqual(r["sort_key"][0], 1)

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
            self.assertEqual(r["gate"], all(r["gate_terms"].values()))

    def test_proxy_scores_are_not_acceptance_evidence(self):
        px_n2 = sp.placement_proxy(sp.read_placement(N2_PCB))
        px_wg = sp.placement_proxy(sp.read_placement(WIDEGAP_PCB))
        self.assertGreaterEqual(px_n2["hpwl"], 0)
        self.assertGreaterEqual(px_wg["hpwl"], 0)
        self.assertFalse(self.n2["gate"])
        self.assertFalse(self.wg["gate"])


# ===================================================================== per-cable output uniformity
class TestPourUniformity(unittest.TestCase):
    """PER-CABLE OUTPUT-FIELD UNIFORMITY gate (owner ruling 2026-07-09). Two surfaces: (a) the output
    TAB-ROW pitch is uniform across positions (the mechanical mate = interchangeability spec), and
    (b) the output pour SHAPE is identical. The math is pure (`_pour_uniformity_verdict`); the pcbnew
    wrapper reads the tab pads + pours off a board."""

    def test_uneven_tab_pitch_fires(self):
        # cable pitch 25.3mm then 20.6mm (the owner's measured fresh-PCIe defect) -> FAIL, dev 4.7mm
        tabs = {"/SENSEC": {1: [(0.0, 0.0)], 2: [(25.3, 0.0)], 3: [(45.9, 0.0)]}}
        pours = {"/SENSEC": {1: [(0, 10, 0, 40)], 2: [(25.3, 35.3, 0, 40)], 3: [(45.9, 55.9, 0, 40)]}}
        v = sp._pour_uniformity_verdict(tabs, pours)
        self.assertFalse(v["ok"])
        self.assertAlmostEqual(v["max_pitch_dev_mm"], 4.7, places=3)
        self.assertIn("tab-row pitch NON-UNIFORM", v["violations"][0])

    def test_uniform_tab_pitch_passes(self):
        tabs = {"/SENSEC": {1: [(0.0, 0.0)], 2: [(30.0, 0.0)], 3: [(60.0, 0.0)]}}
        pours = {"/SENSEC": {1: [(0, 10, 0, 40)], 2: [(30, 40, 0, 40)], 3: [(60, 70, 0, 40)]}}
        v = sp._pour_uniformity_verdict(tabs, pours)
        self.assertTrue(v["ok"])
        self.assertEqual(v["max_pitch_dev_mm"], 0.0)

    def test_two_positions_are_always_uniform(self):
        # 2 cables = a single pitch = always uniform (a per-slot daughterboard trivially interchanges)
        tabs = {"/SENSEC": {1: [(0.0, 0.0)], 2: [(21.7, 0.0)]}}
        pours = {"/SENSEC": {1: [(0, 10, 0, 40)], 2: [(21.7, 31.7, 0, 40)]}}
        self.assertTrue(sp._pour_uniformity_verdict(tabs, pours)["ok"])

    def test_shape_delta_fires_even_at_uniform_pitch(self):
        tabs = {"/SENSEC": {1: [(0.0, 0.0)], 2: [(30.0, 0.0)], 3: [(60.0, 0.0)]}}
        pours = {"/SENSEC": {1: [(0, 10, 0, 40)], 2: [(30, 45, 0, 40)], 3: [(60, 70, 0, 40)]}}  # c2 15-wide
        v = sp._pour_uniformity_verdict(tabs, pours)
        self.assertFalse(v["ok"])
        self.assertTrue(any("SHAPE differs" in s for s in v["violations"]))


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required")
class TestPourUniformityBoards(unittest.TestCase):
    ATX = os.path.join(ROOT, "beta", "atx-24pin-rev3", "24pin-module.kicad_pcb")
    PCIE3 = os.path.join(ROOT, "beta", "pcie-8pin-3port", "pcie8pin-3port-module.kicad_pcb")

    @unittest.skipUnless(os.path.isfile(ATX), "24-pin board required")
    def test_shared_bus_board_is_na(self):
        # the 24-pin is a per-RAIL (shared-bus) board -- no per-cable output family -> N/A, never fails
        v = sp._oracle_pour_uniformity(self.ATX)
        self.assertFalse(v["applicable"])
        self.assertTrue(v["ok"])

    @unittest.skipUnless(os.path.isfile(PCIE3), "committed pcie-3port board required")
    def test_committed_generator_board_is_uniform(self):
        # the committed (generator-made) pcie-3port module has a uniform output field
        v = sp._oracle_pour_uniformity(self.PCIE3)
        self.assertTrue(v["applicable"])
        self.assertTrue(v["ok"], v.get("violations"))
        self.assertEqual(v["positions"], {"/SENSEC": [1, 2, 3]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
