#!/usr/bin/env python3
"""Fail-closed contracts for the secondary PLACE -> ROUTE -> FEM cascade."""

import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_cascade as C  # noqa: E402


class RouteAcceptanceTest(unittest.TestCase):
    def test_route_ok_requires_drc_and_connectivity(self):
        clean = {"kelvin_ok": True, "diffpair_ok": True,
                 "drc": 0, "unconnected": 0}
        self.assertTrue(C._route_ok(clean))
        self.assertFalse(C._route_ok({**clean, "drc": 1}))
        self.assertFalse(C._route_ok({**clean, "unconnected": 1}))
        self.assertFalse(C._route_ok({**clean, "gates_pass": False}))

    def test_default_apex_does_not_sign_finishing_drc(self):
        summary = {
            "fem": {"pass": True},
            "route": {"verdict": {
                "gates_pass": False, "kelvin_ok": True, "diffpair_ok": True,
                "drc": 1, "unconnected": 0,
            }},
            "place": {"hard_fails": []},
        }
        self.assertFalse(C.default_apex(summary)["signed"])

    def test_saved_board_rescore_failure_blocks_stale_route_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "routed.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("(kicad_pcb)\n")
            spec = types.SimpleNamespace()
            log = types.SimpleNamespace(final={"verdict": {"gates_pass": True}})
            with mock.patch.object(C.cec_router, "board_spec",
                                   return_value=(spec, "fixture")), \
                    mock.patch.object(C.cec_router, "route",
                                      return_value=(board, log)), \
                    mock.patch("cec_score.score",
                               side_effect=RuntimeError("score failed")):
                _final, _log, verdict = C.route_tier(
                    "fixture", board, panel=1, swarm=False, max_iters=1,
                    kmax=1, seeds=(0,), passes=1, opt_time=0, verbose=False)
        self.assertFalse(verdict["gates_pass"])
        self.assertIn("re-verification failed", verdict["reasons"][0])

    def test_requested_via_field_failure_blocks_clean_rescore(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "routed.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("(kicad_pcb)\n")
            spec = types.SimpleNamespace()
            log = types.SimpleNamespace(final={"verdict": {"gates_pass": True}})
            metrics = types.SimpleNamespace(
                gates_pass=True, drc=0, unconnected=0,
                kelvin_ok=True, diffpair_ok=True)
            with mock.patch.object(C.cec_router, "board_spec",
                                   return_value=(spec, "fixture")), \
                    mock.patch.object(C.cec_router, "route",
                                      return_value=(board, log)), \
                    mock.patch("cec_fr.derive_via_field",
                               side_effect=RuntimeError("field failed")), \
                    mock.patch("cec_score.score", return_value=metrics):
                _final, _log, verdict = C.route_tier(
                    "fixture", board, panel=1, swarm=False, max_iters=1,
                    kmax=1, seeds=(0,), passes=1, opt_time=0,
                    via_field=2, verbose=False)
        self.assertFalse(verdict["gates_pass"])
        self.assertIn("requested post-route via field failed",
                      verdict["reasons"][-1])


class PlacementEvidenceTest(unittest.TestCase):
    def test_drc_tool_failure_is_not_an_empty_placement_result(self):
        report = {"verdicts": [], "directives": []}
        proc = types.SimpleNamespace(returncode=2, stdout="", stderr="bad board")
        with mock.patch.object(C.cec_constraints, "report", return_value=report), \
                mock.patch.object(C.toolchain, "require_kicad_cli",
                                  return_value="kicad-cli"), \
                mock.patch.object(C.subprocess, "run", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "placement DRC failed"):
                C.placement_metrics("fixture.kicad_pcb")


class FemEvidenceTest(unittest.TestCase):
    def test_transient_profile_is_refused_by_steady_state_solver(self):
        result = C.fem_tier("fixture", "fixture.kicad_pcb",
                            transient={"peak_ms": 5.0}, verbose=False)
        self.assertFalse(result["pass"])
        self.assertEqual(result["blocking"], ["unsupported_transient_input"])

    def test_current_density_field_flag_remains_blocking(self):
        cfg = C.synth.Config(board="fixture", params={})
        solved = types.SimpleNamespace(max_T=70.0, calibration="uncalibrated")
        flag = C.synth.Flag("current density high", "/PWR", 0.6,
                            C.synth.Kind.MEASURE)
        with mock.patch.object(C.synth.Config, "load", return_value=cfg), \
                mock.patch.object(C.synth, "physics", return_value=(solved, [flag])):
            result = C.fem_tier("fixture", "fixture.kicad_pcb", verbose=False)
        self.assertFalse(result["pass"])
        self.assertIn("current density high", result["blocking"])
        self.assertTrue(cfg.params["thermal_field"])


if __name__ == "__main__":
    unittest.main()
