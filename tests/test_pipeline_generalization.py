#!/usr/bin/env python3
"""The reusable engine must remain product-identity free."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_generalization_gate as gate  # noqa: E402


class PipelineGeneralizationGateTest(unittest.TestCase):
    def test_new_force_reuse_and_event_modules_remain_under_generic_audit(self):
        self.assertTrue({
            "scripts/cec_force_current.py",
            "scripts/cec_pad_surface_access.py",
            "scripts/cec_force_sense_evidence.py",
            "scripts/cec_kelvin_copper_cut.py",
            "scripts/cec_kelvin_force_separation.py",
            "scripts/cec_kelvin_branch_repair.py",
            "scripts/cec_saved_family_repair.py",
            "scripts/cec_priority_force_dispatch.py",
            "scripts/cec_terminal_launch_pocket.py",
            "scripts/cec_pth_return_repair.py",
            "scripts/cec_fiducial_reuse.py",
            "scripts/cec_systemd_completion_event.py",
            "scripts/cec_route_candidate_worker.py",
        }.issubset(set(gate.GENERIC_ENGINE_MODULES)))

    def test_generic_engine_contains_no_product_or_refdes_selectors(self):
        report = gate.audit(ROOT)
        self.assertTrue(report["ok"], report["violations"])
        self.assertEqual(
            set(report["checked_modules"]),
            set(gate.GENERIC_ENGINE_MODULES))

    def test_full_runtime_claim_is_derived_from_full_runtime_findings(self):
        report = gate.audit(ROOT)
        self.assertEqual(
            report["full_pipeline_generic"],
            not bool(report["runtime_violations"]))
        self.assertEqual(report["release_ok"],
                         report["full_pipeline_generic"])
        expected_runtime = (
            set(gate.FULL_PIPELINE_RUNTIME_MODULES)
            - set(gate.DECLARATIVE_POLICY_MODULES))
        self.assertTrue(expected_runtime.issubset(
            set(report["runtime_checked_modules"])))
        self.assertIn(
            "scripts/cec_force_lanes.py",
            gate.runtime_module_closure(ROOT))
        if report["full_pipeline_generic"]:
            expected = "generic_runtime"
        elif report["physical_engine_generic"]:
            expected = "generic_physical_engine_with_integration_debt"
        else:
            expected = (
                "generic_core_with_legacy_physical_and_integration_debt")
        self.assertEqual(report["pipeline_maturity"], expected)
        self.assertEqual(
            report["physical_engine_generic"],
            not bool(report["physical_violations"]))

    def test_cli_refuses_core_only_false_green(self):
        with mock.patch.object(gate, "audit", return_value={
                "ok": True, "release_ok": False}):
            self.assertEqual(gate.main(), 1)

    def test_synthetic_product_and_refdes_leaks_are_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            planted = Path(temp) / "engine.py"
            planted.write_text(
                'def repair(board):\n'
                '    if board == "sample-board":\n'
                '        return {"U42": (12.5, 7.0)}\n',
                encoding="utf-8")
            rows = gate.audit_file(
                planted, product_keys=("sample-board",))

        self.assertEqual(
            {row["kind"] for row in rows},
            {"product_identity", "reference_selector"})

    def test_documentation_and_generic_reference_prefixes_are_allowed(self):
        with tempfile.TemporaryDirectory() as temp:
            planted = Path(temp) / "engine.py"
            planted.write_text(
                '"""sample-board and U42 are illustrative prose."""\n'
                'def movable(ref):\n'
                '    """J3 remains prose, not a selector."""\n'
                '    return ref.startswith("FID")\n',
                encoding="utf-8")
            rows = gate.audit_file(
                planted, product_keys=("sample-board",))

        self.assertEqual(rows, [])


class ConstraintCheckerIsolationTest(unittest.TestCase):
    def test_solver_boundary_runs_out_of_process_before_later_checkers(self):
        import cec_constraints

        first = SimpleNamespace(
            id="trace-width-high-current",
            checker="trace-width-high-current", superseded_by="")
        second = SimpleNamespace(
            id="second", checker="second", superseded_by="")
        board = SimpleNamespace(valid=True)

        def invalidate(board, _path, _ctx):
            board.valid = False
            return True, "first complete"

        def observe(board, _path, _ctx):
            return board.valid, "fresh" if board.valid else "corrupted"

        with mock.patch.object(cec_constraints, "REGISTRY", [first, second]), \
                mock.patch.object(
                    cec_constraints, "CHECKERS",
                    {"trace-width-high-current": invalidate,
                     "second": observe}), \
                mock.patch.object(
                    cec_constraints, "_run_checker_process",
                    return_value=(True, "isolated", None)) as isolated, \
                mock.patch.object(
                    cec_constraints.pcbnew, "LoadBoard",
                    return_value=board) as load:
            rows = cec_constraints.run("fixture.kicad_pcb")

        self.assertEqual([row[1] for row in rows], ["PASS", "PASS"])
        self.assertEqual(load.call_count, 1)
        isolated.assert_called_once()
        self.assertTrue(board.valid)


class BoundedRouteSearchTest(unittest.TestCase):
    def setUp(self):
        import cec_search_policy
        self.policy = cec_search_policy

    def test_seed_budget_is_finite_and_capped(self):
        self.assertEqual(
            self.policy.bounded_seed_plan(10, 4), (10, 11, 12, 13))
        with self.assertRaisesRegex(ValueError, "hard cap"):
            self.policy.bounded_seed_plan(0, 9)

    def test_placement_strategy_product_is_finite_and_capped(self):
        self.assertEqual(
            self.policy.bounded_placement_plan(
                ("plain", "dataflow"), (0, 1)),
            (("plain", 0), ("plain", 1),
             ("dataflow", 0), ("dataflow", 1)))
        with self.assertRaisesRegex(ValueError, "hard cap"):
            self.policy.bounded_placement_plan(
                ("plain", "dataflow", "thermal", "hybrid"),
                range(5))

    def test_candidate_selection_uses_release_objective(self):
        rows = [
            {"seed": 2, "routed": "a", "gate": False,
             "sort_key": [1, 0, 0], "drc": 0, "unconnected": 1},
            {"seed": 3, "routed": "b", "gate": True,
             "sort_key": [0, 9, 9], "drc": 0, "unconnected": 0},
        ]
        self.assertEqual(self.policy.select_candidate(rows)["seed"], 3)


if __name__ == "__main__":
    unittest.main()
