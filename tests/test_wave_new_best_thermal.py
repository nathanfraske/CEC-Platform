#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Teeth for the wave NEW-BEST THERMAL stamp (owner design call 2026-07-17:
# "thermal fires on every wave that produces a new best"). Pure-logic: the
# solve/env are injected fakes, so this runs on the host battery. The real
# solver term (_oracle_thermal: fail-closed + mirage guard + double-solve)
# carries its own guards and was measured live on the routed 12vhpwr
# (dT 23.62 vs the committed 22.95 record, 97s CPU-AMG, 2026-07-17).
import contextlib
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fresh_wave as W                                     # noqa: E402


def _null_env(_params):
    return contextlib.nullcontext()


class _Solve:
    def __init__(self, result=None, raise_=None):
        self.calls = []
        self.result = result or {"ok": True, "dT": 21.0, "max_T": 71.0,
                                 "gate_dt": 30.0, "cooling": "fake"}
        self.raise_ = raise_

    def __call__(self, path):
        self.calls.append(path)
        if self.raise_:
            raise self.raise_
        return dict(self.result)


def _report(pub_dir, ts, sort_key):
    os.makedirs(pub_dir, exist_ok=True)
    with open(os.path.join(pub_dir, f"{ts}-wave-report.json"), "w") as fh:
        json.dump({"best": {"sort_key": sort_key}}, fh)


class TestPrevBestKey(unittest.TestCase):
    def test_no_reports_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(W._prev_best_key(d))

    def test_latest_report_wins(self):
        with tempfile.TemporaryDirectory() as d:
            _report(d, "20260701T0000", [1, 5, 2, 100, 40, 300, 25.0])
            _report(d, "20260715T2300", [1, 2, 1, 80, 30, 200, 21.0])
            self.assertEqual(W._prev_best_key(d), (1, 2, 1, 80, 30, 200, 21.0))

    def test_corrupt_report_fail_safe(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "x-wave-report.json"), "w") as fh:
                fh.write("{not json")
            self.assertIsNone(W._prev_best_key(d))


class TestNewBestThermal(unittest.TestCase):
    def _routed(self, d):
        p = os.path.join(d, "winner.kicad_pcb")
        with open(p, "w") as fh:
            fh.write("(kicad_pcb)")
        return p

    def test_first_wave_fires(self):
        with tempfile.TemporaryDirectory() as d:
            s = _Solve()
            best = {"sort_key": [1, 2, 1, 80, 30, 200, 21.0], "routed": self._routed(d)}
            nb = W._new_best_thermal(best, d, {}, solve=s, env=_null_env)
            self.assertTrue(nb)
            self.assertEqual(len(s.calls), 1)
            self.assertEqual(best["thermal"]["dT"], 21.0)
            self.assertTrue(best["thermal_ok"])

    def test_beating_incumbent_fires(self):
        with tempfile.TemporaryDirectory() as d:
            _report(d, "20260715T2300", [1, 3, 2, 90, 35, 250, 22.0])
            s = _Solve()
            best = {"sort_key": [1, 2, 1, 80, 30, 200, 21.0], "routed": self._routed(d)}
            self.assertTrue(W._new_best_thermal(best, d, {}, solve=s, env=_null_env))
            self.assertEqual(len(s.calls), 1)

    def test_not_beating_incumbent_skips(self):
        with tempfile.TemporaryDirectory() as d:
            _report(d, "20260715T2300", [1, 1, 0, 40, 20, 100, 19.0])
            s = _Solve()
            best = {"sort_key": [1, 2, 1, 80, 30, 200, 21.0], "routed": self._routed(d)}
            self.assertFalse(W._new_best_thermal(best, d, {}, solve=s, env=_null_env))
            self.assertEqual(s.calls, [])
            self.assertNotIn("thermal", best)

    def test_existing_real_solve_not_rerun(self):
        # the lazy path fired (gate-clean winner) -> the stamp must not double-solve
        with tempfile.TemporaryDirectory() as d:
            s = _Solve()
            best = {"sort_key": [0, 21.0, 84, 1.2, 900.0, 0], "routed": self._routed(d),
                    "thermal": {"ok": True, "dT": 21.0}, "thermal_ok": True}
            self.assertTrue(W._new_best_thermal(best, d, {}, solve=s, env=_null_env))
            self.assertEqual(s.calls, [])

    def test_no_routed_board_stamps_note(self):
        with tempfile.TemporaryDirectory() as d:
            s = _Solve()
            best = {"sort_key": [1, 2, 1, 80, 30, 200, 21.0], "routed": None}
            self.assertTrue(W._new_best_thermal(best, d, {}, solve=s, env=_null_env))
            self.assertEqual(s.calls, [])
            self.assertFalse(best["thermal"]["ok"])
            self.assertIn("no routed board", best["thermal"]["note"])

    def test_solver_exception_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            s = _Solve(raise_=RuntimeError("solver exploded"))
            best = {"sort_key": [1, 2, 1, 80, 30, 200, 21.0], "routed": self._routed(d)}
            nb = W._new_best_thermal(best, d, {}, solve=s, env=_null_env)
            self.assertTrue(nb)
            self.assertFalse(best["thermal"]["ok"])
            self.assertFalse(best["thermal_ok"])
            self.assertIn("solver exploded", best["thermal"]["error"])

    def test_failing_solve_published_loud(self):
        # a thermal FAIL stamps ok=False -- the wave publish carries it, never drops it
        with tempfile.TemporaryDirectory() as d:
            s = _Solve(result={"ok": False, "dT": 44.0, "max_T": 94.0, "gate_dt": 30.0,
                               "cooling": "fake"})
            best = {"sort_key": [1, 2, 1, 80, 30, 200, 44.0], "routed": self._routed(d)}
            self.assertTrue(W._new_best_thermal(best, d, {}, solve=s, env=_null_env))
            self.assertFalse(best["thermal_ok"])
            self.assertEqual(best["thermal"]["dT"], 44.0)


if __name__ == "__main__":
    unittest.main()
