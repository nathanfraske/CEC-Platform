#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Plateau-floor teeth (probe 2026-07-23): the streak-only plateau-kill was
# discarding boards in the WINNER band -- the seg3 hub board killed flat at
# togo/failed=(34,31) re-routed with the kill off to unconn 7 / kelvin TRUE
# (the best hub board ever); FR's rip-up phases go flat-then-recover. The floor
# says: a flat streak AT/UNDER the floor is terminal grind (finish + grade);
# above it, the kill stands (true collapses sit flat at 190+ from early
# passes). Host-runnable (pure logic + param plumbing).
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cec_fr import (_plateau_floor_disables,
                    _plateau_floor_grants_grace,
                    _plateau_at_terminal_pass)         # noqa: E402


class TestFloorSemantics(unittest.TestCase):
    def test_off_by_default(self):
        # floor<=0 = historical behavior: every plateau kills
        self.assertFalse(_plateau_floor_disables(34, 0))
        self.assertFalse(_plateau_floor_disables(1, 0))
        self.assertFalse(_plateau_floor_disables(34, -1))

    def test_terminal_grind_within_floor_survives(self):
        # the measured hub case: flat at togo 34, floor 100 -> no kill
        self.assertTrue(_plateau_floor_disables(34, 100))
        self.assertTrue(_plateau_floor_disables(100, 100))   # inclusive

    def test_true_collapse_above_floor_still_kills(self):
        # the measured 24-pin collapse band (failed flat 190-230)
        self.assertFalse(_plateau_floor_disables(190, 170))
        self.assertFalse(_plateau_floor_disables(230, 100))

    def test_terminal_grind_gets_bounded_not_infinite_grace(self):
        self.assertTrue(_plateau_floor_grants_grace(34, 100, 0, 2))
        self.assertTrue(_plateau_floor_grants_grace(34, 100, 1, 2))
        self.assertFalse(_plateau_floor_grants_grace(34, 100, 2, 2))
        self.assertFalse(_plateau_floor_grants_grace(190, 100, 0, 2))

    def test_terminal_pass_is_allowed_to_finalize_ses(self):
        self.assertFalse(_plateau_at_terminal_pass(23, 24))
        self.assertTrue(_plateau_at_terminal_pass(24, 24))
        self.assertTrue(_plateau_at_terminal_pass(25, 24))
        self.assertFalse(_plateau_at_terminal_pass(None, 24))
        self.assertFalse(_plateau_at_terminal_pass(20, 24, 4))
        # A four-pass streak window no longer turns passes 21..23 into a
        # pseudo-terminal range that silently expands low-togo grace.
        self.assertFalse(_plateau_at_terminal_pass(21, 24, 4))
        self.assertFalse(_plateau_at_terminal_pass(23, 24, 4))
        self.assertTrue(_plateau_at_terminal_pass(24, 24, 4))


class TestWavePlumbing(unittest.TestCase):
    def test_board_floors_split_winner_vs_collapse_bands(self):
        import cec_fresh_wave as w
        hub = w.BOARD_PARAMS["hub-standard-rev2"]["wave_plateau_floor"]
        p24 = w.BOARD_PARAMS["atx-24pin-rev3"]["wave_plateau_floor"]
        # hub winners finish at unconn 7-36; seg3 kills fired flat at 34-67
        self.assertGreaterEqual(hub, 67)
        # 24-pin winner band 146-158 vs collapse flat 190-230: the floor must
        # sit BETWEEN them (kills collapses, spares the winner band)
        self.assertGreater(p24, 158)
        self.assertLess(p24, 190)

    def test_env_allow_lists_carry_the_floor(self):
        import cec_fr_server
        self.assertIn("CEC_FR_PLATEAU_FLOOR", cec_fr_server.ENV_ALLOW)
        self.assertIn("CEC_FR_PLATEAU_GRACES", cec_fr_server.ENV_ALLOW)


if __name__ == "__main__":
    unittest.main()
