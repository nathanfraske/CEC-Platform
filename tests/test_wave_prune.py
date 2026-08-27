#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Teeth for the wave PRUNE -> ADJUDICATE wiring (roadmap throughput lever 1,
# owner GO 2026-07-17): the decision function is pure and unit-tested here;
# _place_variant gets a real-compile smoke (pcbnew-gated). Fidelity contract
# under test: top-K by cheap key routes, placement ERRORS route anyway
# (fail-open), pruned variants are RETURNED for the report (no silent caps),
# CEC_WAVE_PRUNE=0 / small grids route everything.
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fresh_wave as W                                     # noqa: E402
import cec_hub_unattended as HUB                               # noqa: E402

try:
    import pcbnew                                              # noqa: F401
    HAVE_PCBNEW = True
except ImportError:
    HAVE_PCBNEW = False


def _v(iname, strat, seed):
    return (iname, strat, seed, None)


def _row(iname, strat, seed, key):
    return {"label": f"{iname}-{strat}-s{seed}", "iname": iname, "strat": strat,
            "seed": seed, "place_key": key}


class TestWaveManagedRuntime(unittest.TestCase):
    def test_prune_pour_failure_returns_before_redundant_craft_work(self):
        session = SimpleNamespace(
            cfg=SimpleNamespace(params={"pour_first": True}),
            pourfirst_report={"error": "exact bundle did not close"},
            compile=mock.Mock(side_effect=AssertionError(
                "compile must not run after failed freeze")),
        )
        with mock.patch.object(W, "_build_session",
                               return_value=(session, {})):
            row = W._place_variant(
                "board", 10.0, 10.0, "plain", "dataflow", 0)

        self.assertIsNone(row["place_key"])
        self.assertIn("exact bundle did not close", row["error"])
        self.assertEqual(row["pourfirst"], session.pourfirst_report)
        session.compile.assert_not_called()

    def test_pair_only_refusal_dispatches_route_placement_repair(self):
        self.assertTrue(W._route_repair_required({
            "critical_pair_refused_count": 1,
            "critical_pin_access_blocked_count": 0,
            "future_critical_corridor_conflicts": 0,
            "future_overflow_units": 0,
        }))
        self.assertFalse(W._route_repair_required({
            "critical_pair_refused_count": 0,
            "critical_pin_access_blocked_count": 0,
            "future_critical_corridor_conflicts": 0,
            "future_overflow_units": 0,
        }))

    def test_pourfirst_state_is_persisted_and_resume_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "placed.kicad_pcb")
            skeleton = os.path.join(directory, "source-skeleton.kicad_pcb")
            state_path = os.path.join(directory, "source-state.json")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("board")
            with open(skeleton, "w", encoding="utf-8") as handle:
                handle.write("skeleton")
            state = {
                "schema": 3, "skeleton": skeleton,
                "placement_scope": "complete",
                "placements": {"U1": [1.0, 2.0, 0.0]},
                "pours": [{"net": "/PWR", "provenance": "pourfirst"}],
                "vias": [], "frozen_nets": ["/PWR"],
                "corridors": [{"net": "/PWR", "layer": "F.Cu",
                               "x0": 0, "y0": 0, "x1": 1, "y1": 1}],
                "exclude_pins": [],
                "reserve_report": {"/PWR": {"reserved": True}},
                "report": {"/PWR": {
                    "path_found": True, "groups": {"delegated": 0}}},
            }
            with open(state_path, "w", encoding="utf-8") as handle:
                json.dump(state, handle)
            params = {"pour_first": True, "pourfirst_state": state_path}

            stable = W._persist_pourfirst_state(params, board)

            self.assertEqual(stable, params["pourfirst_state"])
            self.assertTrue(os.path.isfile(stable))
            status = W._pourfirst_resume_state_status(params)
            self.assertTrue(status["ok"], status)
            os.unlink(stable)
            self.assertEqual(
                W._pourfirst_resume_state_status(params)["reason"],
                "unreadable_pourfirst_state")

    def test_anchor_only_empty_pourfirst_state_cannot_resume_routing(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "state.json")
            with open(state_path, "w", encoding="utf-8") as handle:
                json.dump({
                    "schema": 2, "pours": [], "vias": [],
                    "frozen_nets": [], "corridors": [],
                    "exclude_pins": [], "reserve_report": {},
                    "placements": {},
                }, handle)
            status = W._pourfirst_resume_state_status({
                "pour_first": True, "pourfirst_state": state_path})
        self.assertFalse(status["ok"])
        self.assertEqual(status["reason"],
                         "non_authoritative_pourfirst_placement_scope")

    def test_direct_cli_reexecs_workspace_python(self):
        expected = os.path.join(ROOT, ".venv", "bin", "python")
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(sys, "prefix", "/usr"), \
             mock.patch.object(sys, "argv", ["cec_fresh_wave.py", "--help"]), \
             mock.patch("cec_fresh_wave.os.path.isfile", return_value=True), \
             mock.patch("cec_fresh_wave.os.access", return_value=True), \
             mock.patch("cec_fresh_wave.os.execv") as execute:
            W._reexec_workspace_python()
        execute.assert_called_once()
        self.assertEqual(execute.call_args.args[0], expected)
        self.assertEqual(execute.call_args.args[1][0], expected)
        self.assertEqual(execute.call_args.args[1][-1], "--help")

    def test_runtime_reexec_can_be_disabled_for_ablation(self):
        with mock.patch.dict(os.environ, {"CEC_KEEP_CALLER_PYTHON": "1"},
                             clear=True), \
             mock.patch("cec_fresh_wave.os.execv") as execute:
            W._reexec_workspace_python()
        execute.assert_not_called()


class TestPruneDecision(unittest.TestCase):
    def test_nested_craft_budget_divides_cpu_without_oversubscription(self):
        self.assertEqual(W._nested_craft_worker_budget(6, cpu_count=64), 10)
        self.assertEqual(W._nested_craft_worker_budget(1, cpu_count=64), 16)
        self.assertEqual(W._nested_craft_worker_budget(128, cpu_count=64), 1)

    def setUp(self):
        # These fixtures give every variant a UNIQUE intent class, so the
        # intent-class floor (2026-07-19: the raw top-K's first live firing
        # pruned all 12 seat proposals -- the winning class) would keep all
        # of them. Pin the RAW top-K arm here; the floor has its own teeth
        # in tests/test_thermal_coarse_cpu.py::TestPruneClassFloor.
        os.environ["CEC_WAVE_PRUNE_CLASS_FLOOR"] = "0"
        self.addCleanup(os.environ.pop, "CEC_WAVE_PRUNE_CLASS_FLOOR", None)
        self.variants = [_v("a", "dataflow", 0), _v("b", "dataflow", 0),
                         _v("c", "compact", 1), _v("d", "compact", 1)]
        self.rows = [_row("a", "dataflow", 0, [0, 3.0, 5.0, 100.0]),
                     _row("b", "dataflow", 0, [1, 0.0, 2.0, 90.0]),
                     _row("c", "compact", 1, [0, 1.0, 3.0, 80.0]),
                     _row("d", "compact", 1, [2, 9.0, 9.0, 999.0])]

    def test_top_k_by_key_routes(self):
        route, pruned = W._prune_variants(self.variants, self.rows, 2)
        labels = [f"{v[0]}-{v[1]}-s{v[2]}" for v in route]
        self.assertEqual(labels, ["c-compact-s1", "a-dataflow-s0"])   # keys (0,1..) < (0,3..)
        self.assertEqual({r["label"] for r in pruned},
                         {"b-dataflow-s0", "d-compact-s1"})
        self.assertTrue(all(r.get("pruned") for r in pruned))

    def test_k_zero_disables(self):
        route, pruned = W._prune_variants(self.variants, self.rows, 0)
        self.assertEqual(route, self.variants)
        self.assertEqual(pruned, [])

    def test_small_grid_routes_all(self):
        route, pruned = W._prune_variants(self.variants, self.rows, 4)
        self.assertEqual(route, self.variants)
        self.assertEqual(pruned, [])

    def test_place_error_routes_fail_open(self):
        rows = list(self.rows)
        rows[0] = {"label": "a-dataflow-s0", "iname": "a", "strat": "dataflow",
                   "seed": 0, "place_key": None, "error": "Boom: compile died"}
        route, pruned = W._prune_variants(self.variants, rows, 2)
        labels = {f"{v[0]}-{v[1]}-s{v[2]}" for v in route}
        self.assertIn("a-dataflow-s0", labels,
                      "an ERRORED placement must never be silently pruned")
        self.assertIn("c-compact-s1", labels)                 # best real key still kept
        self.assertEqual(len(route), 2)

    def test_missing_row_routes_fail_open(self):
        rows = [r for r in self.rows if r["iname"] != "b"]
        route, _ = W._prune_variants(self.variants, rows, 2)
        labels = {f"{v[0]}-{v[1]}-s{v[2]}" for v in route}
        self.assertIn("b-dataflow-s0", labels)

    def test_deterministic_tie_break(self):
        rows = [_row(i, "dataflow", 0, [0, 1.0, 1.0, 50.0]) for i in ("a", "b", "c", "d")]
        variants = [_v(i, "dataflow", 0) for i in ("a", "b", "c", "d")]
        r1, _ = W._prune_variants(variants, rows, 2)
        r2, _ = W._prune_variants(list(reversed(variants)), rows, 2)
        self.assertEqual({f"{v[0]}" for v in r1}, {f"{v[0]}" for v in r2},
                         "equal keys tie-break by label, order-independent")


class TestPolishDecision(unittest.TestCase):
    def test_lower_effort_polish_is_skipped(self):
        run, reason = W._polish_decision(
            {"unconnected": 12},
            {"polish_passes": 16, "polish_opt": 20}, 40, 60)
        self.assertFalse(run)
        self.assertIn("adds no effort", reason)

    def test_close_winner_gets_genuinely_deeper_polish(self):
        run, _reason = W._polish_decision(
            {"unconnected": 12},
            {"wave_passes": 8, "wave_opt": 10,
             "polish_passes": 16, "polish_opt": 20}, 40, 60)
        self.assertTrue(run)

    def test_far_or_already_closed_winner_skips(self):
        self.assertFalse(W._polish_decision(
            {"unconnected": 80}, {}, 8, 10)[0])
        self.assertFalse(W._polish_decision(
            {"unconnected": 0}, {}, 8, 10)[0])

    def test_hard_coordination_is_opt_in_after_controlled_regression(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CEC_WAVE_COORD_POLISH", None)
            self.assertFalse(W._coord_polish_enabled({}))
            self.assertTrue(W._coord_polish_enabled(
                {"wave_coord_polish": True}))
        with mock.patch.dict(os.environ, {"CEC_WAVE_COORD_POLISH": "1"}):
            self.assertTrue(W._coord_polish_enabled({}))
        with mock.patch.dict(os.environ, {"CEC_WAVE_COORD_POLISH": "0"}):
            self.assertFalse(W._coord_polish_enabled(
                {"wave_coord_polish": True}))


class TestHubUnattendedSourceContract(unittest.TestCase):
    def test_candidate_metadata_reader_fails_closed_without_sort_key(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "candidate.json")
            with open(path, "w") as handle:
                handle.write('{"source": "candidate.kicad_pcb"}')
            with self.assertRaises(RuntimeError):
                HUB._read_candidate_metadata(path)

    def test_round_cleanup_is_scoped_and_reclaims_scratch(self):
        with tempfile.TemporaryDirectory() as root:
            round_work = os.path.join(root, "round-007")
            os.makedirs(round_work)
            with open(os.path.join(round_work, "board.ses"), "w") as handle:
                handle.write("scratch")
            HUB._cleanup_round_work(round_work, root)
            self.assertFalse(os.path.exists(round_work))
            with self.assertRaises(RuntimeError):
                HUB._cleanup_round_work(root, root)

    def test_preflight_resolves_production_hierarchical_source(self):
        calls = []
        session = SimpleNamespace(
            nl=SimpleNamespace(comps={"U1": object(), "J6P": object()}),
            cfg=SimpleNamespace(sch="/tmp/current-hierarchical-hub.kicad_sch"))

        def build(*args, **kwargs):
            calls.append((args, kwargs))
            return session, {}

        fake_wave = SimpleNamespace(
            BOARD_WH={HUB.BOARD: (86.0, 74.0)}, _build_session=build)
        with mock.patch.dict(sys.modules, {"cec_fresh_wave": fake_wave}):
            refs, schematic, outline = HUB._current_placement_source_refs()

        self.assertEqual(refs, {"U1", "J6P"})
        self.assertEqual(schematic, "/tmp/current-hierarchical-hub.kicad_sch")
        self.assertEqual(outline, (86.0, 74.0))
        self.assertEqual(calls[0][0],
                         (HUB.BOARD, 86.0, 74.0, "plain", "dataflow", 0))
        self.assertFalse(calls[0][1]["pourfirst_artifact"])


class TestFutureRoutePlacementScore(unittest.TestCase):
    def test_future_capacity_clamps_zero_iterations_to_one(self):
        import cec_route_preflight
        report = {"stackup": {}, "pin_access": {}, "fanout": {},
                  "congestion": {"unroutable_count": 0,
                                 "residual_overuse": 0,
                                 "residual_overuse_escaped": 0}}
        fake = SimpleNamespace(
            analyze=mock.Mock(return_value=report),
            compact_placement_evidence=
                cec_route_preflight.compact_placement_evidence)
        with mock.patch.dict(sys.modules, {"cec_route_preflight": fake}):
            W._future_route_preflight(__file__, iters=0,
                                      multiresolution=False, backend="cpu")
        self.assertEqual(fake.analyze.call_args.kwargs["iters"], 1)

    def test_compact_preflight_carries_unreachable_and_blocked_capacity(self):
        report = {
            "gate": False,
            "wall_s": 1.25,
            "stackup": {"blocked_cell_count": 42,
                        "blocked_cells_per_layer": [10, 11, 12, 9]},
            "pin_access": {
                "blocked_count": 1,
                "blocked": [{"ref": "U1", "pad": "5", "net": "/A"}],
            },
            "congestion": {
                "unroutable_count": 2,
                "unroutable_connections": [
                    {"index": 3, "net": "/A"}, {"index": 8, "net": "/B"}],
                "residual_overuse": 7.0,
                "residual_overuse_escaped": 4.0,
                "layers": [], "hotspots": [],
            },
        }
        import cec_route_preflight
        fake = SimpleNamespace(
            analyze=mock.Mock(return_value=report),
            compact_placement_evidence=
                cec_route_preflight.compact_placement_evidence)
        with mock.patch.dict(sys.modules, {"cec_route_preflight": fake}), \
                mock.patch.dict(os.environ, {
                    "CEC_WAVE_FUTURE_GRID_MM": "1.25",
                    "CEC_WAVE_FUTURE_ITERS": "3"}):
            result = W._future_route_preflight(__file__)
        self.assertEqual(result["unroutable_count"], 2)
        self.assertEqual(result["residual_overuse_escaped"], 4.0)
        self.assertEqual(result["blocked_cell_count"], 42)
        self.assertEqual(result["pin_access_blocked_count"], 1)
        self.assertEqual(result["pin_access_blocked"][0]["ref"], "U1")
        fake.analyze.assert_called_once_with(
            __file__, grid_mm=1.25, iters=3,
            backend="cpu", run_congestion=True,
            run_future_congestion=True)

    def test_route_aware_shortlist_refines_only_equal_resolution_contenders(self):
        variants = [_v(name, "dataflow", 0) for name in ("a", "b", "c", "d")]
        rows = []
        for rank, name in enumerate(("a", "b", "c", "d")):
            row = _row(name, "dataflow", 0, [0, rank, 0, 0])
            row.update({"placed": __file__, "place_key_base": [rank, 100 + rank],
                        "future_route": {"grid_mm": 1.0}, "cfg_params": {}})
            rows.append(row)
        fine = {
            "gate": True, "critical_pair_refused_count": 0,
            "critical_declaration_error_count": 0,
            "critical_pin_access_blocked_count": 0,
            "critical_unroutable_count": 0, "fanout_blocked_count": 0,
            "pin_access_blocked_count": 0, "unroutable_count": 0,
            "residual_overuse_escaped": 2.0, "residual_overuse": 3.0,
            "backend": "gpu", "route_awareness_service": {"used": True},
        }
        with mock.patch.dict(os.environ, {"CEC_WAVE_PRUNE_CLASS_FLOOR": "0"}), \
                mock.patch.object(W, "_future_route_preflight",
                                  return_value=fine) as preflight:
            shortlist, pruned, report = W._refine_route_aware_shortlist(
                variants, rows, 3, grid_mm=0.5, iters=3)
        self.assertEqual([v[0] for v in shortlist], ["a", "b", "c"])
        self.assertEqual([row["label"] for row in pruned], ["d-dataflow-s0"])
        self.assertEqual(preflight.call_count, 3)
        self.assertEqual(report["refined"], 3)
        self.assertTrue(all(row.get("future_route_coarse") == {"grid_mm": 1.0}
                            for row in rows[:3]))
        for call in preflight.call_args_list:
            self.assertEqual(call.kwargs["grid_mm"], 0.5)
            self.assertEqual(call.kwargs["iters"], 3)
            self.assertEqual(call.kwargs["backend"], "auto")
            self.assertFalse(call.kwargs["multiresolution"])

    def test_fine_route_awareness_error_routes_fail_open(self):
        variants = [_v("a", "dataflow", 0), _v("b", "dataflow", 0)]
        rows = []
        for rank, name in enumerate(("a", "b")):
            row = _row(name, "dataflow", 0, [0, rank])
            row.update({"placed": __file__, "place_key_base": [rank],
                        "cfg_params": {}})
            rows.append(row)
        with mock.patch.object(W, "_future_route_preflight",
                               return_value={"error": "CUDA out of memory"}):
            shortlist, _pruned, report = W._refine_route_aware_shortlist(
                variants, rows, 2)
        self.assertEqual(shortlist, variants)
        self.assertEqual(report["failed"], 2)
        self.assertTrue(all(row["place_key"] is None for row in rows))


class TestPublishedRescore(unittest.TestCase):
    def test_saved_artifact_metrics_replace_pre_repair_grade(self):
        best = {
            "gate": False, "gates_pass": False, "kelvin_ok": True,
            "diffpair_ok": True, "drc": 29, "unconnected": 95,
            "sort_key": (1, 0, 2, 0, 95, 29, 1e6),
            "foreign": {"tracks": 0, "vias": 0},
            "thermal": {"ok": False, "dT": None},
            "rails": {"total": 4, "laid": 4},
            "gate_terms": {"gates_pass": False, "routing_complete": False,
                           "foreign_ok": True, "thermal_ok": False},
            "reasons": [],
        }
        metrics = SimpleNamespace(
            gates_pass=False, kelvin_ok=True, diffpair_ok=True, drc=31,
            unconnected=97, drc_types={"tracks_crossing": 1}, vias=6,
            tracks=12, length=42.25,
            detail={"unconn_nets": ["GND", "/UART_TX"]},
        )
        with mock.patch.object(W.cec_score.Rules, "from_board", return_value=object()), \
                mock.patch.object(W.cec_score, "score", return_value=metrics), \
                mock.patch.object(W.csp, "_classify_unconnected",
                                  return_value=(["GND"], ["/UART_TX"])):
            W._rescore_published(best, __file__)

        self.assertEqual(best["drc"], 31)
        self.assertEqual(best["unconnected"], 97)
        self.assertEqual(best["drc_types"], {"tracks_crossing": 1})
        self.assertEqual(best["unconn_critical"], ["GND"])
        self.assertEqual(best["sort_key"], (1, 0, 1, 0, 97, 31, 1e6))
        self.assertFalse(best["gate"])
        self.assertIn("published-artifact rescore", best["reasons"][-1])

    def test_missing_complete_gate_record_fails_closed(self):
        best = {"gate": True, "foreign": {}, "thermal": {}, "reasons": []}
        metrics = SimpleNamespace(
            gates_pass=True, kelvin_ok=True, diffpair_ok=True, drc=0,
            unconnected=0, drc_types={}, vias=0, tracks=0, length=0.0,
            detail={"unconn_nets": []},
        )
        with mock.patch.object(W.cec_score.Rules, "from_board", return_value=object()), \
                mock.patch.object(W.cec_score, "score", return_value=metrics), \
                mock.patch.object(W.csp, "_classify_unconnected", return_value=([], [])):
            W._rescore_published(best, __file__)
        self.assertFalse(best["gate"], "copper-only score cannot waive missing oracle terms")


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (real compile)")
class TestPlaceVariantSmoke(unittest.TestCase):
    def test_compile_only_produces_key(self):
        r = W._place_variant("eps-8pin-rev3", 96.0, 40.0, "plain", "compact", 0)
        self.assertIsNone(r.get("error"), r.get("error"))
        self.assertEqual(r["label"], "plain-compact-s0")
        self.assertIsInstance(r["place_key"], list)
        self.assertGreaterEqual(len(r["place_key"]), 3)
        self.assertIn("residual", r)


if __name__ == "__main__":
    unittest.main()
