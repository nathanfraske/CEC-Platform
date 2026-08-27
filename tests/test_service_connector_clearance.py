#!/usr/bin/env python3
"""Regression tests for generic edge-service/interface separation."""

import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_synth_pipeline as synth


class TestServiceConnectorClearance(unittest.TestCase):
    def test_rigid_group_moves_to_nearest_clear_interval(self):
        # The PCIe two-port geometry reduced to its along-edge intervals:
        # J1/J5 bank 13.435..42.665, terminal tab 40.755..47.345.
        delta = synth._interval_group_shift(
            (13.435, 42.665), [(40.755, 47.345)], 0.5, 55.1,
            clearance=1.0)
        self.assertAlmostEqual(delta, -2.91, places=6)
        self.assertAlmostEqual(42.665 + delta, 39.755, places=6)

    def test_multiple_forbidden_intervals_and_bounds(self):
        delta = synth._interval_group_shift(
            (10.0, 20.0), [(18.0, 24.0), (28.0, 32.0)], 0.0, 40.0,
            clearance=1.0)
        self.assertEqual(delta, -3.0)

    def test_impossible_group_fails_closed(self):
        self.assertIsNone(synth._interval_group_shift(
            (2.0, 12.0), [(0.0, 8.0), (9.0, 20.0)], 0.0, 20.0,
            clearance=1.0))

    def test_power_is_not_a_signal_owner(self):
        self.assertFalse(synth._is_power_net("/USB_D_P"))
        self.assertFalse(synth._is_power_net("/USB_CC1"))
        self.assertTrue(synth._is_power_net("GND"))
        self.assertTrue(synth._is_power_net("+5VSB"))


if __name__ == "__main__":
    unittest.main()
