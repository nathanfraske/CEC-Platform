#!/usr/bin/env python3
"""Regression teeth for the top-level synthesis and tool-failure gates."""

import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_synth_pipeline as S  # noqa: E402


class PipelineReleaseGateTest(unittest.TestCase):
    def test_unresolved_preflight_flag_survives_clean_cascade(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "input.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("(kicad_pcb)\n")
            cfg = S.Config(board="fixture", profile="consumer", params={},
                           dir=directory, pcb=board)
            flag = types.SimpleNamespace(binding="gate", name="ERC failed")
            view = types.SimpleNamespace(
                metrics=types.SimpleNamespace(gates_pass=True))
            observed = {}

            def signoff(_board, _cfg, residual, ask=None):
                observed["residual"] = list(residual)
                return False

            ledger = types.SimpleNamespace(
                manifest=lambda: {},
                append=lambda **_kw: {"run_id": "test-run"})
            with mock.patch.object(S, "View", return_value=view), \
                    mock.patch.object(S, "run_stage", return_value=[flag]), \
                    mock.patch.object(S, "resolve_each", return_value=(False, [])), \
                    mock.patch.object(S, "triage_arm", return_value=[]), \
                    mock.patch.object(S, "run_full_cascade", return_value=[]), \
                    mock.patch.object(S, "human_signoff", side_effect=signoff), \
                    mock.patch.object(S, "_archive_corpus"), \
                    mock.patch.dict(sys.modules, {"cec_ledger": ledger}):
                result = S.run_pipeline(
                    cfg, board=board, out_dir=os.path.join(directory, "out"),
                    place=False, verbose=False)

            self.assertEqual(result["status"], "sign-off withheld")
            self.assertEqual(observed["residual"], [flag])
            self.assertEqual(len(result["residual"]), 1)

    def test_full_run_invokes_automatic_placement_without_board_override(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "input.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("(kicad_pcb)\n")
            cfg = S.Config(board="fixture", profile="consumer", params={},
                           dir=directory, pcb=board)
            view = types.SimpleNamespace(
                metrics=types.SimpleNamespace(gates_pass=True))
            candidate = types.SimpleNamespace(
                strat="compact", seed=7, residual=0, proxy={})
            ledger = types.SimpleNamespace(
                manifest=lambda: {},
                append=lambda **_kw: {"run_id": "test-run"})

            def materialize(_candidate, _cfg, path):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("(kicad_pcb)\n")
                return path

            with mock.patch.object(S, "View", return_value=view), \
                    mock.patch.object(S, "run_stage", return_value=[]), \
                    mock.patch.object(S, "resolve_each", return_value=(True, [])), \
                    mock.patch.object(S, "triage_arm", return_value=[]), \
                    mock.patch.object(S, "run_full_cascade", return_value=[]), \
                    mock.patch.object(S, "human_signoff", return_value=False), \
                    mock.patch.object(S, "read_placement",
                                      return_value=types.SimpleNamespace(W=20.0, H=10.0)), \
                    mock.patch.object(S, "place_candidates",
                                      return_value=[candidate]) as place_candidates, \
                    mock.patch.object(S, "materialize",
                                      side_effect=materialize) as materialize_mock, \
                    mock.patch.object(S, "_archive_corpus"), \
                    mock.patch.dict(sys.modules, {"cec_ledger": ledger}):
                result = S.run_pipeline(
                    cfg, out_dir=os.path.join(directory, "out"), verbose=False,
                    placement_strategies=("compact",), placement_seeds=(7,))

            place_candidates.assert_called_once()
            materialize_mock.assert_called_once()
            self.assertEqual(result["status"], "sign-off withheld")

    def test_route_repair_request_remains_blocking_until_revalidated(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "input.kicad_pcb")
            with open(board, "w", encoding="utf-8") as handle:
                handle.write("(kicad_pcb)\n")
            cfg = S.Config(board="fixture", profile="consumer", params={},
                           dir=directory, pcb=board)
            flag = S.Flag("unrouted ratlines", board, 1.0, S.Kind.ROUTE)
            action = S.Action(resolved=True, fixes=[flag.name], rung="worker")
            view = types.SimpleNamespace(
                metrics=types.SimpleNamespace(gates_pass=False))
            observed = {}

            def signoff(_board, _cfg, residual, ask=None):
                observed["residual"] = list(residual)
                return False

            ledger = types.SimpleNamespace(
                manifest=lambda: {},
                append=lambda **_kw: {"run_id": "test-run"})
            with mock.patch.object(S, "View", return_value=view), \
                    mock.patch.object(S, "run_stage", return_value=[]), \
                    mock.patch.object(S, "run_full_cascade", return_value=[flag]), \
                    mock.patch.object(S, "resolve_each",
                                      side_effect=[(True, []),
                                                   (True, [(flag, action)])]), \
                    mock.patch.object(S, "triage_arm", return_value=[]), \
                    mock.patch.object(S, "human_signoff", side_effect=signoff), \
                    mock.patch.object(S, "_archive_corpus"), \
                    mock.patch.dict(sys.modules, {"cec_ledger": ledger}):
                result = S.run_pipeline(
                    cfg, board=board, out_dir=os.path.join(directory, "out"),
                    place=False, verbose=False)

            self.assertEqual(result["status"], "sign-off withheld")
            self.assertEqual(observed["residual"], [flag])

    def test_low_confidence_gate_flag_still_blocks_headless_signoff(self):
        flag = S.Flag("unverified gate", "fixture", 0.1, S.Kind.DFM)
        self.assertFalse(S.human_signoff("fixture", None, [flag]))


class ToolFailureGateTest(unittest.TestCase):
    @staticmethod
    def _completed(returncode=0, stdout="", stderr=""):
        return types.SimpleNamespace(returncode=returncode, stdout=stdout,
                                     stderr=stderr)

    def test_drc_violation_exit_is_valid_when_complete_json_exists(self):
        def run(args, **_kw):
            out = args[args.index("-o") + 1]
            with open(out, "w", encoding="utf-8") as handle:
                json.dump({"violations": [{}], "unconnected_items": []}, handle)
            return self._completed(returncode=5)

        with mock.patch.object(S._tc, "require_kicad_cli", return_value="kicad-cli"), \
                mock.patch.object(S.subprocess, "run", side_effect=run):
            report = S._run_drc("fixture.kicad_pcb")
        self.assertEqual(len(report["violations"]), 1)

    def test_drc_tool_failure_raises_instead_of_returning_empty_pass(self):
        with mock.patch.object(S._tc, "require_kicad_cli", return_value="kicad-cli"), \
                mock.patch.object(S.subprocess, "run",
                                  return_value=self._completed(2, stderr="bad board")):
            with self.assertRaisesRegex(RuntimeError, "DRC failed"):
                S._run_drc("fixture.kicad_pcb")

    def test_erc_invalid_json_raises_instead_of_returning_empty_pass(self):
        def run(args, **_kw):
            out = args[args.index("-o") + 1]
            with open(out, "w", encoding="utf-8") as handle:
                handle.write("not json")
            return self._completed(returncode=0)

        with mock.patch.object(S._tc, "require_kicad_cli", return_value="kicad-cli"), \
                mock.patch.object(S.subprocess, "run", side_effect=run):
            with self.assertRaises(json.JSONDecodeError):
                S._run_erc("fixture.kicad_sch")

    def test_sheet_nested_kicad_erc_json_is_accepted(self):
        def run(args, **_kw):
            out = args[args.index("-o") + 1]
            with open(out, "w", encoding="utf-8") as handle:
                json.dump({"sheets": [{"path": "/", "violations": [{}]}]},
                          handle)
            return self._completed(returncode=5)

        with mock.patch.object(S._tc, "require_kicad_cli", return_value="kicad-cli"), \
                mock.patch.object(S.subprocess, "run", side_effect=run):
            report = S._run_erc("fixture.kicad_sch")
        self.assertEqual(len(report["sheets"][0]["violations"]), 1)

    def test_failed_netlist_export_cannot_reuse_a_stale_process_file(self):
        with tempfile.TemporaryDirectory() as directory:
            sch = os.path.join(directory, "fixture.kicad_sch")
            with open(sch, "w", encoding="utf-8") as handle:
                handle.write("(kicad_sch)\n")
            cfg = S.Config(board="fixture", dir=directory, sch=sch)
            view = S.View(cfg)
            with mock.patch.object(S._tc, "require_kicad_cli",
                                   return_value="kicad-cli"), \
                    mock.patch.object(S.subprocess, "run",
                                      return_value=self._completed(
                                          1, stderr="export refused")):
                with self.assertRaisesRegex(RuntimeError, "netlist export failed"):
                    view._export_netlist()

    def test_materialization_reuses_one_valid_process_netlist_export(self):
        with tempfile.TemporaryDirectory() as directory:
            sch = os.path.join(directory, "fixture.kicad_sch")
            with open(sch, "w", encoding="utf-8") as handle:
                handle.write("(kicad_sch)\n")
            cfg = S.Config(board="fixture", dir=directory, sch=sch)

            def export(args, **_kw):
                out = args[args.index("-o") + 1]
                with open(out, "w", encoding="utf-8") as handle:
                    handle.write("(export (components))\n")
                return self._completed(returncode=0)

            with mock.patch.object(S.tempfile, "gettempdir",
                                   return_value=directory), \
                    mock.patch.object(S._tc, "kicad_cli",
                                      return_value="kicad-cli"), \
                    mock.patch.object(S.subprocess, "run",
                                      side_effect=export) as run:
                first = S._ensure_netlist_path(cfg)
                second = S._ensure_netlist_path(cfg)

            self.assertEqual(first, second)
            self.assertEqual(run.call_count, 1)

    def test_draft_board_does_not_skip_erc(self):
        erc = mock.Mock(return_value={
            "sheets": [{"violations": [{
                "type": "pin_not_driven", "severity": "error"
            }]}]
        })
        view = types.SimpleNamespace(
            cfg=types.SimpleNamespace(is_draft=True),
            sch="draft.kicad_sch", erc=erc)

        flags = S.chk_erc_clean(view)

        erc.assert_called_once_with()
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].name, "ERC violations")

    def test_netclass_checker_failure_is_a_blocking_flag(self):
        pcbnew = types.SimpleNamespace(
            LoadBoard=mock.Mock(side_effect=RuntimeError("load failed")))
        view = types.SimpleNamespace(board="missing.kicad_pcb")

        with mock.patch.dict(sys.modules, {"pcbnew": pcbnew}):
            flags = S.chk_netclass_geometry(view)

        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].binding, "gate")
        self.assertEqual(flags[0].name, "netclass geometry not evaluable")


if __name__ == "__main__":
    unittest.main()
