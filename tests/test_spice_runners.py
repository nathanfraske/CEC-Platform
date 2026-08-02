#!/usr/bin/env python3
"""Batch-runner and failure-propagation tests for the SPICE harnesses."""

import os
import sys
import tempfile
import types
import unittest
from unittest import mock

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sys.path.insert(0, os.path.join(ROOT, "scripts", "sim"))

import cec_spice as CELL  # noqa: E402
import cec_backfeed_models as BACKFEED  # noqa: E402


class AnalogCellRunnerTest(unittest.TestCase):
    def test_windows_selector_never_uses_gui_executable(self):
        with mock.patch.object(CELL.os, "name", "nt"), \
                mock.patch.object(CELL.shutil, "which", return_value=None), \
                mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(CELL._ngspice_executable(), "ngspice_con.exe")

    def test_nonzero_exit_raises(self):
        proc = types.SimpleNamespace(returncode=2, stdout="", stderr="bad model")
        with mock.patch.object(CELL, "NGSPICE", "batch-ngspice"), \
                mock.patch.object(CELL.subprocess, "run", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "ngspice exited 2"):
                CELL._run(CELL._cell_cir(0.002, 50.0, 1.65, 1.0))

    def test_empty_success_output_raises(self):
        proc = types.SimpleNamespace(returncode=0, stdout="noise only", stderr="")
        with mock.patch.object(CELL, "NGSPICE", "batch-ngspice"), \
                mock.patch.object(CELL.subprocess, "run", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "no requested values"):
                CELL._run(CELL._cell_cir(0.002, 50.0, 1.65, 1.0))


class BackfeedRunnerTest(unittest.TestCase):
    def test_windows_prefers_console_then_docker(self):
        def which(name):
            return (r"C:\Spice64\bin\ngspice_con.exe"
                    if name == "ngspice_con.exe" else None)

        with mock.patch.object(BACKFEED.os, "name", "nt"), \
                mock.patch.object(BACKFEED.shutil, "which", side_effect=which), \
                mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(BACKFEED._ngspice_runner(),
                             ("local", r"C:\Spice64\bin\ngspice_con.exe"))

    def test_runner_failure_raises_instead_of_returning_empty_measures(self):
        proc = types.SimpleNamespace(returncode=1, stdout="", stderr="bad deck")
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(BACKFEED, "SCRATCH", directory), \
                mock.patch.object(BACKFEED.subprocess, "run", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "runner exited 1"):
                BACKFEED.run_ngspice("* title\n.end\n", "bad",
                                     runner=("local", "ngspice-batch"))

    def test_stale_transient_file_is_removed_and_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            stale = os.path.join(directory, "tran.data")
            with open(stale, "w", encoding="utf-8") as handle:
                handle.write("0 0\n")
            with mock.patch.object(BACKFEED, "SCRATCH", directory), \
                    mock.patch.object(BACKFEED, "_ngspice_runner",
                                      return_value=("local", "ngspice-batch")), \
                    mock.patch.object(BACKFEED, "run_ngspice",
                                      return_value=({}, "", "")):
                with self.assertRaisesRegex(RuntimeError, "no transient data"):
                    BACKFEED.run_ngspice_tran(
                        BACKFEED.TITLE, ["v(out)"], "tran",
                        tstep="1u", tstop="10u")
            self.assertFalse(os.path.exists(stale))

    def test_local_transient_uses_relative_wrdata_in_scratch_directory(self):
        captured = {}

        def fake_run(cir, name, **kwargs):
            captured["cir"] = cir
            captured["name"] = name
            captured.update(kwargs)
            with open(os.path.join(captured["run_cwd"], "tran.data"), "w",
                      encoding="utf-8") as handle:
                handle.write("0 0\n1e-6 1\n")
            return {}, "", ""

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(BACKFEED, "SCRATCH", directory), \
                mock.patch.object(BACKFEED, "_ngspice_runner",
                                  return_value=("local", "ngspice-batch")), \
                mock.patch.object(BACKFEED, "run_ngspice",
                                  side_effect=fake_run):
            data, _, _ = BACKFEED.run_ngspice_tran(
                BACKFEED.TITLE, ["v(out)"], "tran",
                tstep="1u", tstop="10u")

        self.assertIn("wrdata tran.data v(out)", captured["cir"])
        self.assertNotIn(":/", captured["cir"])
        self.assertEqual(captured["run_cwd"], directory)
        self.assertEqual(data["v(out)"].tolist(), [0.0, 1.0])

    def test_charge_uses_available_numpy_trapezoid_api(self):
        data = {"time": np.array([0.0, 1.0, 2.0]),
                "i(vsense)": np.array([0.0, 1.0, 0.0])}
        self.assertAlmostEqual(BACKFEED.charge_coulombs(data, "i(vsense)"), 1.0)


if __name__ == "__main__":
    unittest.main()
