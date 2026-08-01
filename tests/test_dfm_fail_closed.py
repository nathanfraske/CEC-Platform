#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""DFM tool failures must not be reported as a clean board."""

import os
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_dfm_check as D  # noqa: E402


class TestDfmFailClosed(unittest.TestCase):
    def test_native_drc_nonzero_exit_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            board = os.path.join(directory, "input.kicad_pcb")
            with open(board, "w", encoding="utf-8") as board_file:
                board_file.write("fixture")
            proc = types.SimpleNamespace(returncode=2, stdout="", stderr="parse failed")
            with mock.patch.object(D.subprocess, "run", return_value=proc):
                with self.assertRaisesRegex(RuntimeError, "exit 2"):
                    D._native_drc(board)

    def test_acid_trap_invalid_json_raises(self):
        proc = types.SimpleNamespace(returncode=0, stdout="not-json", stderr="")
        with mock.patch.object(D.subprocess, "run", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
                D._acid_traps("fixture.kicad_pcb")

    def test_acid_trap_nonzero_exit_raises(self):
        proc = types.SimpleNamespace(returncode=3, stdout="", stderr="worker failed")
        with mock.patch.object(D.subprocess, "run", return_value=proc):
            with self.assertRaisesRegex(RuntimeError, "exit 3"):
                D._acid_traps("fixture.kicad_pcb")


if __name__ == "__main__":
    unittest.main()
