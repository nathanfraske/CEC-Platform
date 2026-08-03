#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Teeth preventing EPS rev3 from falling back to an obsolete board/profile."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fresh_wave as wave  # noqa: E402
import cec_beta_manifest as manifest  # noqa: E402
import cec_synth_pipeline as synth  # noqa: E402

try:
    import pcbnew  # noqa: F401,E402
    HAVE_PCBNEW = True
except ImportError:
    HAVE_PCBNEW = False


class TestEpsRev3CurrentPipeline(unittest.TestCase):
    def test_loader_resolves_authoritative_beta_source(self):
        cfg = synth.Config.load("eps-8pin-rev3")
        expected = os.path.realpath(os.path.join(ROOT, "beta", "eps-8pin-rev3"))
        self.assertEqual(os.path.realpath(cfg.dir), expected)
        self.assertEqual(os.path.basename(cfg.sch), "eps-8pin-rev3.kicad_sch")
        self.assertEqual(os.path.basename(cfg.pcb), "eps-8pin-rev3.kicad_pcb")

    def test_fresh_wave_has_explicit_rev3_geometry_and_stackup(self):
        self.assertNotIn("eps-8pin", wave.BOARD_WH)
        self.assertNotIn("eps-8pin", wave.BOARD_PARAMS)
        self.assertNotIn("eps-8pin", manifest.CURRENT_BETA_BOARDS)
        self.assertEqual(manifest.WAVE_BOARDS.count("eps-8pin-rev3"), 1)
        self.assertEqual(wave.BOARD_WH["eps-8pin-rev3"], (96.0, 40.0))
        params = wave._board_params("eps-8pin-rev3")
        self.assertEqual(params["stackup_profile"],
                         "jlcpcb_6l_pofv_high_current")
        self.assertEqual(params["thermal_board_hint"], "eps-8pin-rev3")
        self.assertEqual(params["power_pour_layers"],
                         ("In3.Cu", "B.Cu", "F.Cu", "In2.Cu"))

    @unittest.skipUnless(HAVE_PCBNEW, "pcbnew required (real placement compile)")
    def test_current_rev3_source_compiles_in_fresh_wave(self):
        result = wave._place_variant(
            "eps-8pin-rev3", 96.0, 40.0, "plain", "compact", 0)
        self.assertIsNone(result.get("error"), result.get("error"))
        self.assertEqual(result["label"], "plain-compact-s0")
        self.assertIsInstance(result["place_key"], list)


if __name__ == "__main__":
    unittest.main()
