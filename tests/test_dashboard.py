#!/usr/bin/env python3
"""Current-BETA and clean-machine dashboard regressions."""
import glob
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_beta_manifest as manifest  # noqa: E402
import cec_dashboard as dashboard  # noqa: E402
import cec_render  # noqa: E402


class TestDashboard(unittest.TestCase):
    def test_analyzer_exposes_complete_six_layer_stack(self):
        self.assertEqual([panel for panel, _filename, _layers
                          in dashboard.COPPER_PLOTS],
                         ["plotf", "plot1", "plot2", "plot3", "plot4", "plotb"])
        self.assertEqual([layers.split(",")[0]
                          for _panel, _filename, layers in dashboard.COPPER_PLOTS],
                         ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"])

    @unittest.skipUnless(shutil.which("kicad-cli") and shutil.which("rsvg-convert"),
                         "KiCad and rsvg-convert required for the real wave tile")
    def test_wave_tile_shows_added_in3_in4_without_temp_leak(self):
        from PIL import Image
        board = os.path.join(ROOT, "beta", "hub-standard-rev2", "candidate",
                             "hub-standard-rev2-candidate.kicad_pcb")
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "six-layer.png")
            # Isolate the helper's temp root so the assertion remains stable if
            # unrelated tests also use /tmp.
            with mock.patch.object(cec_render.tempfile, "tempdir", directory):
                self.assertEqual(cec_render.hex_panel(board, output), output)
                self.assertEqual(glob.glob(os.path.join(directory, "cec_hex_*")), [])
            with Image.open(output) as image:
                self.assertGreaterEqual(image.width, 3000,
                                        "six layers require the 4-column tile")

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
