#!/usr/bin/env python3
"""The thermal CLI must not start its expensive validation suite implicitly."""

import os
import subprocess
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "cec_thermal2d.py")


class ThermalCliTest(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(
            [sys.executable, SCRIPT, *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_help_is_help_only(self):
        result = self._run("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage:", result.stdout.lower())
        self.assertIn("--self-test", result.stdout)
        self.assertNotIn("ALL_PASS", result.stdout)
        self.assertNotIn("A_single_via_R", result.stdout)

    def test_no_arguments_refuses_instead_of_running_self_tests(self):
        result = self._run()
        self.assertEqual(result.returncode, 2)
        combined = result.stdout + result.stderr
        self.assertIn("required", combined.lower())
        self.assertNotIn("ALL_PASS", combined)
        self.assertNotIn("A_single_via_R", combined)


if __name__ == "__main__":
    unittest.main()
