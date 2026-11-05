#!/usr/bin/env python3
"""Regression tests for constrained-first critical-pair scheduling."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_precision_route as precision


class TestPairSchedule(unittest.TestCase):
    def test_unknown_scope_fails_before_any_copper_is_authored(self):
        for scope in (['USB'], [], 'USB', ['actual', 'misspelled']):
            board=MagicMock()
            with patch.object(precision,'derive_coupled_pairs',return_value=[{'name':'actual'}]), \
                 patch.object(precision.cec_fr,'synthesize_kelvin_taps') as kelvin:
                with self.assertRaises(ValueError):
                    precision.precision_route_board(board,board_path='synthetic',include_pair_names=scope)
                kelvin.assert_not_called()
                board.GetTracks.assert_not_called()

    def test_leg_span_uses_paired_centrelines(self):
        leg = ((0.0, -0.2), (3.0, -0.2),
               (0.0, 0.2), (3.0, 0.2))
        self.assertAlmostEqual(precision._pair_leg_center_span(leg), 3.0)

    def test_diagonal_leg_span(self):
        leg = ((1.0, 1.0), (4.0, 5.0),
               (1.0, 2.0), (4.0, 6.0))
        self.assertAlmostEqual(precision._pair_leg_center_span(leg), 5.0)

    def test_future_launch_reservations_cover_both_ends_only(self):
        leg = ((0.0, -0.2), (10.0, -0.2),
               (0.0, 0.2), (10.0, 0.2))
        pair = {"name": "PAIR", "p": "P", "n": "N",
                "width": 0.2, "gap": 0.2}
        rows = precision._pair_leg_launch_reservations(leg, pair)
        self.assertEqual(len(rows), 2)
        source, target = rows
        self.assertLessEqual(source[0], 0.0)
        self.assertGreaterEqual(source[2], 3.6)
        self.assertLessEqual(target[0], 6.4)
        self.assertGreaterEqual(target[2], 10.0)
        # The bounded launch reservations deliberately leave the middle of a
        # longer prospective route available to earlier critical nets.
        self.assertLess(source[2], target[0])
        self.assertEqual(source[5], "F.Cu")


if __name__ == "__main__":
    unittest.main()
