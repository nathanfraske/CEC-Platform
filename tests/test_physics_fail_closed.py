#!/usr/bin/env python3
"""Release-facing field-physics fallback and injection-accounting gates."""

import os
import sys
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_synth_pipeline as csp  # noqa: E402


class TopLevelPhysicsFailClosedTest(unittest.TestCase):
    @staticmethod
    def _cfg():
        return types.SimpleNamespace(board="unit-board",
                                     params={"thermal_field": True})

    def test_field_exception_keeps_analytic_result_but_adds_blocking_flag(self):
        analytic = types.SimpleNamespace(calibration="uncalibrated")
        with mock.patch.object(csp, "field_electrothermal_solve",
                               side_effect=RuntimeError("solver unavailable")), \
                mock.patch.object(csp, "electrothermal_solve", return_value=analytic), \
                mock.patch.object(csp, "physics_gates", return_value=[]):
            res, flags = csp.physics("board.kicad_pcb", self._cfg())
        self.assertIs(res, analytic)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].name, "thermal field solver unavailable")
        self.assertEqual(flags[0].conf, 1.0)
        self.assertEqual(flags[0].binding, "gate")
        self.assertIn("solver unavailable", flags[0].detail["error"])

    def test_dropped_configured_net_adds_blocking_flag(self):
        field = types.SimpleNamespace(
            nets_requested={"PWR": 10.0},
            nets_dropped={"PWR": "open circuit"})
        result = types.SimpleNamespace(field=field, cooling="still-air",
                                       calibration="uncalibrated")
        with mock.patch.object(csp, "field_electrothermal_solve", return_value=result), \
                mock.patch.object(csp, "physics_gates", return_value=[]):
            _, flags = csp.physics("board.kicad_pcb", self._cfg())
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].name, "thermal current injection incomplete")
        self.assertEqual(flags[0].conf, 1.0)
        self.assertIn("PWR", flags[0].detail["nets_dropped"])

    def test_absent_configured_net_adds_blocking_flag(self):
        field = types.SimpleNamespace(
            nets_requested={"PWR": 10.0}, nets_dropped={},
            nets_absent={"PWR": "not present on board"})
        result = types.SimpleNamespace(field=field, cooling="still-air",
                                       calibration="uncalibrated")
        with mock.patch.object(csp, "field_electrothermal_solve", return_value=result), \
                mock.patch.object(csp, "physics_gates", return_value=[]):
            _, flags = csp.physics("board.kicad_pcb", self._cfg())
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0].name, "thermal current injection incomplete")
        self.assertIn("PWR", flags[0].detail["nets_absent"])

    def test_zero_requested_current_is_not_a_field_pass(self):
        field = types.SimpleNamespace(nets_requested={}, nets_dropped={})
        result = types.SimpleNamespace(field=field, cooling="still-air",
                                       calibration="uncalibrated")
        with mock.patch.object(csp, "field_electrothermal_solve", return_value=result), \
                mock.patch.object(csp, "physics_gates", return_value=[]):
            _, flags = csp.physics("board.kicad_pcb", self._cfg())
        self.assertEqual([f.name for f in flags],
                         ["thermal field has no requested current"])


if __name__ == "__main__":
    unittest.main()
