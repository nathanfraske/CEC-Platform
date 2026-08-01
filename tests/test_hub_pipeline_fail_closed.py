#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The standalone Hub runner may publish only a complete accepted artifact."""

import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_constraints  # noqa: E402
import cec_router  # noqa: E402
import hub_pipeline_run as H  # noqa: E402


class TestHubAcceptance(unittest.TestCase):
    def test_all_terms_are_required(self):
        args = ({"gates_pass": True}, 0, [], True, True)
        terms, accepted = H._acceptance_terms(*args)
        self.assertTrue(accepted)
        self.assertTrue(all(terms.values()))
        mutations = [
            ({"gates_pass": False}, 0, [], True, True),
            ({"gates_pass": True}, 1, [], True, True),
            ({"gates_pass": True}, 0, [object()], True, True),
            ({"gates_pass": True}, 0, [], False, True),
            ({"gates_pass": True}, 0, [], True, False),
        ]
        for values in mutations:
            with self.subTest(values=values):
                self.assertFalse(H._acceptance_terms(*values)[1])

    def test_conformance_exception_is_a_failure(self):
        messages = []
        cfg = type("Cfg", (), {"params": {}})()
        with mock.patch.object(cec_constraints, "run", side_effect=RuntimeError("boom")):
            count, rows = H._conformance("fixture.kicad_pcb", cfg, messages.append)
        self.assertEqual(count, 1)
        self.assertEqual(rows[0]["status"], "ERROR")
        self.assertIn("boom", rows[0]["detail"])

    def test_reference_intake_binds_parent_schematic(self):
        result = {"ok": False, "reasons": ["fixture"]}
        with mock.patch.object(cec_constraints, "intake_gate",
                               return_value=result) as intake:
            self.assertIs(H._reference_intake(), result)
        board_arg = os.path.normpath(intake.call_args.args[0])
        sch_arg = os.path.normpath(intake.call_args.kwargs["ctx"]["sch"])
        self.assertEqual(board_arg, os.path.normpath(os.path.join(ROOT, H.REF)))
        self.assertEqual(sch_arg, os.path.normpath(os.path.join(ROOT, H.REF_SCH)))

    def test_route_timeout_divides_remaining_window(self):
        self.assertEqual(H._route_iteration_timeout(150, 3), 40)
        with self.assertRaises(RuntimeError):
            H._route_iteration_timeout(20, 3)

    def test_board_spec_carries_worker_timeout(self):
        import tempfile
        import cec_router

        board = os.path.join(ROOT, H.REF)
        with tempfile.TemporaryDirectory() as out:
            spec, _ = cec_router.board_spec(board, out, seeds=(0,), fr_timeout=17)
        self.assertEqual(spec.regions[0].fr_params["timeout"], 17)

    def test_empty_route_batch_returns_controlled_failure(self):
        import tempfile

        board = os.path.join(ROOT, H.REF)
        with tempfile.TemporaryDirectory() as out, \
                mock.patch.dict(os.environ, {"CEC_SKIP_INTAKE": "1"}), \
                mock.patch.object(cec_router.cec_fr, "generate_batch", return_value=[]):
            spec, _ = cec_router.board_spec(
                board, out, seeds=(0,), max_iters=1, fr_timeout=5)
            final, log = cec_router.route(board, spec, verbose=False,
                                          work_dir=os.path.join(out, "work"))
        self.assertIsNone(final)
        self.assertFalse(log.final["verdict"]["gates_pass"])

    def test_route_intake_exception_refuses(self):
        import tempfile

        board = os.path.join(ROOT, H.REF)
        with tempfile.TemporaryDirectory() as out, \
                mock.patch.dict(os.environ, {"CEC_SKIP_INTAKE": ""}), \
                mock.patch.object(cec_constraints, "intake_gate",
                                  side_effect=RuntimeError("synthetic intake crash")):
            spec, _ = cec_router.board_spec(board, out, seeds=(0,), max_iters=1)
            with self.assertRaisesRegex(RuntimeError, "failed closed"):
                cec_router.route(board, spec, verbose=False,
                                 work_dir=os.path.join(out, "work"))


if __name__ == "__main__":
    unittest.main()
