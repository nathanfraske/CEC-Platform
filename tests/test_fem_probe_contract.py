#!/usr/bin/env python3
"""Input-contract teeth for the 12VHPWR field probe."""

import importlib.util
import json
import os
import unittest
from types import SimpleNamespace


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "scripts", "probes", "fem_probe_12vhpwr.py")
SPEC = importlib.util.spec_from_file_location("fem_probe_12vhpwr", PATH)
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class FemProbeContractTest(unittest.TestCase):
    def _scenario(self, **changes):
        value = {
            "name": "balanced",
            "pin_A": {str(index): 8.0 for index in range(1, 7)},
            "gnd_A": 48.0,
        }
        value.update(changes)
        return json.dumps(value)

    def test_balanced_scenario_is_normalized(self):
        scenario = PROBE.parse_scenario(self._scenario())
        self.assertEqual(scenario["gnd_A"], 48.0)
        self.assertEqual(scenario["backend"], "auto")
        self.assertEqual(scenario["ambient_env"], "enclosed_passive")
        self.assertIsNone(scenario["grid_mm"])

    def test_ambient_environment_reaches_solver_config(self):
        scenario = PROBE.parse_scenario(self._scenario(ambient_env="airflow"))
        cfg = SimpleNamespace(params={})
        currents = PROBE.apply_scenario(
            cfg, scenario,
            {"enclosed_passive": 50.0, "airflow": 35.0, "worst_case": 60.0})
        self.assertEqual(cfg.params["thermal_env"], "airflow")
        self.assertEqual(cfg.params["ambient_C"], 35.0)
        self.assertEqual(currents["GND"], 48.0)

    def test_unknown_ambient_environment_is_refused(self):
        with self.assertRaisesRegex(ValueError, "ambient_env"):
            PROBE.parse_scenario(self._scenario(ambient_env="desk"))

    def test_help_does_not_parse_as_json(self):
        self.assertEqual(PROBE.main(["--help"]), 0)

    def test_absent_net_makes_injection_incomplete(self):
        field = SimpleNamespace(
            nets_requested={"/SENSEP1_HI": 8.0},
            nets_dropped={},
            nets_absent={"/SENSEP1_HI": "not on board"},
        )
        report = PROBE.injection_report(field)
        self.assertFalse(report["complete"])
        self.assertEqual(report["injected_A"], {})

    def test_return_current_must_equal_lane_sum(self):
        with self.assertRaisesRegex(ValueError, "lane-current sum"):
            PROBE.parse_scenario(self._scenario(gnd_A=40.0))

    def test_transient_input_is_refused_not_ignored(self):
        with self.assertRaisesRegex(ValueError, "steady-state"):
            PROBE.parse_scenario(self._scenario(transient={"seconds": 10}))

    def test_unknown_lane_and_nonpositive_current_are_refused(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            PROBE.parse_scenario(self._scenario(
                pin_A={"1": 8.0, "7": 8.0}, gnd_A=16.0))
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            PROBE.parse_scenario(self._scenario(
                pin_A={"1": 0.0}, gnd_A=1.0))


if __name__ == "__main__":
    unittest.main()
