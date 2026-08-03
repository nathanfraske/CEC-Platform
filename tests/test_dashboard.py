#!/usr/bin/env python3
"""Current-BETA and clean-machine dashboard regressions."""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_beta_manifest as manifest  # noqa: E402
import cec_dashboard as dashboard  # noqa: E402


class TestDashboard(unittest.TestCase):
    def test_beta_library_is_exactly_authoritative_manifest(self):
        boards = dashboard._beta_boards()
        self.assertEqual([board["name"] for board in boards],
                         list(manifest.CURRENT_BETA_BOARDS))
        self.assertEqual([board["name"] for board in boards
                          if os.path.basename(board["name"]).startswith("eps-8pin")],
                         ["eps-8pin-rev3"])

    def test_native_analysis_translates_workspace_paths(self):
        translated = dashboard._native_analysis_argv([
            "python3", "scripts/cec_dashboard.py",
            "/workspace/build/example/board.kicad_pcb",
        ])
        self.assertEqual(translated[:2], ["python3", "scripts/cec_dashboard.py"])
        self.assertEqual(translated[2],
                         os.path.join(ROOT, "build", "example", "board.kicad_pcb"))

    def test_native_analysis_preserves_environment_contract(self):
        with mock.patch.object(dashboard, "_docker_analysis_available",
                               return_value=False):
            completed = dashboard._container_run(
                [sys.executable, "-c",
                 "import os; print(os.environ['CEC_DASH_TEST'])"],
                timeout=30, env={"CEC_DASH_TEST": "native"})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "native")


if __name__ == "__main__":
    unittest.main()
