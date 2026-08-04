#!/usr/bin/env python3
"""Regression: FEM may fill declared zones, but must never invent copper."""
import copy
import glob
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew
    import cec_thermal_overlay as overlay
except ImportError:
    pcbnew = None
    overlay = None


@unittest.skipIf(pcbnew is None or overlay is None,
                 "pcbnew and thermal dependencies are required")
class TestThermalGeometryParity(unittest.TestCase):
    BOARDS = (
        ("atx-24pin-rev3", 31, os.path.join(
            ROOT, "beta", "atx-24pin-rev3", "candidate",
            "atx-24pin-rev3-candidate.kicad_pcb")),
        # This is the firing regression: the old verifier added thirteen lane
        # slabs to this one-zone board before solving and drawing it.
        ("12vhpwr-standard", 1, os.path.join(
            ROOT, "beta", "12vhpwr-standard", "candidate",
            "12vhpwr-standard-candidate.kicad_pcb")),
    )
    generated = set()

    @classmethod
    def tearDownClass(cls):
        for path in cls.generated:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def test_actual_beta_candidates_keep_exact_declared_copper(self):
        for name, expected_zones, path in self.BOARDS:
            with self.subTest(board=name):
                source = pcbnew.LoadBoard(path)
                source_manifest = overlay._declared_copper_manifest(source)
                filled, provenance = overlay._prepare_filled(
                    path, return_provenance=True)
                self.generated.add(filled)
                analysis = pcbnew.LoadBoard(filled)
                analysis_manifest = overlay._declared_copper_manifest(analysis)

                self.assertEqual(len(source_manifest["zones"]), expected_zones)
                self.assertEqual(source_manifest, analysis_manifest)
                self.assertEqual(len(list(analysis.Zones())), expected_zones)
                self.assertEqual(provenance["geometry_source"],
                                 overlay.THERMAL_GEOMETRY_SOURCE)
                self.assertEqual(provenance["source_geometry_sha256"],
                                 provenance["analysis_geometry_sha256"])
                self.assertEqual(provenance["geometry_counts"]["zones"],
                                 expected_zones)

    def test_temp_board_is_bounded_and_overwritten_per_worker(self):
        before = set(glob.glob(os.path.join(tempfile.gettempdir(),
                                            ".thermal_filled_*")))
        first = overlay._prepare_filled(self.BOARDS[0][2])
        second = overlay._prepare_filled(self.BOARDS[1][2])
        self.generated.add(first)
        self.assertEqual(first, second)
        self.assertTrue(os.path.isfile(second))
        self.assertIn(second, overlay._TEMP_ANALYSIS_PATHS)
        after = set(glob.glob(os.path.join(os.path.dirname(second),
                                          ".thermal_filled_*")))
        self.assertEqual(after, before, "KiCad temp project sidecars must not accumulate")

    def test_current_beta_lane6_scenario_uses_actual_fan_net_once(self):
        path = self.BOARDS[1][2]
        currents, _stack, overrides, _cooling = overlay.board_thermal_config(path)
        self.assertIn("/FAN_12V", currents)
        self.assertIn("/FAN_12V", overrides)
        self.assertNotIn("/SENSEP6_HI", currents)
        self.assertEqual(len(currents), 13)  # six HI + six LO + GND

    def test_parity_guard_has_teeth(self):
        path = self.BOARDS[1][2]
        source = overlay._declared_copper_manifest(pcbnew.LoadBoard(path))
        contaminated = copy.deepcopy(source)
        contaminated["zones"].append(("/PHANTOM", "pour:/PHANTOM"))
        with self.assertRaisesRegex(overlay.ThermalGeometryError,
                                    "changed declared copper geometry"):
            overlay._assert_geometry_parity(source, contaminated)


if __name__ == "__main__":
    unittest.main()
