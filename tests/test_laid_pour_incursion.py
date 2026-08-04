#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Teeth for the actual laid-pour incursion checker."""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import pcbnew  # noqa: E402
import cec_constraints as C  # noqa: E402
import cec_fab_profile as FAB  # noqa: E402
import cec_fr as FR  # noqa: E402
import cec_slab_pour as SLAB  # noqa: E402
import cec_fresh_wave as WAVE  # noqa: E402


def _board():
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(2)
    power = pcbnew.NETINFO_ITEM(board, "PWR")
    signal = pcbnew.NETINFO_ITEM(board, "SIG")
    board.Add(power)
    board.Add(signal)
    zone = pcbnew.ZONE(board)
    zone.SetNet(power)
    zone.SetLayer(pcbnew.F_Cu)
    zone.SetZoneName("overunder:PWR")
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in ((0, 0), (10, 0), (10, 10), (0, 10)):
        outline.Append(pcbnew.VECTOR2I_MM(x, y))
    board.Add(zone)
    return board, power, signal


class TestLaidPourIncursion(unittest.TestCase):
    def test_checker_is_reachable_from_normal_constraint_runs(self):
        check_id = "no-incursion-in-laid-pour"
        self.assertIn(check_id, C.CHECKERS)
        self.assertTrue(any(row.id == check_id for row in C.REGISTRY))

    def test_checker_returns_normal_na_tuple_not_an_error_shape(self):
        board = pcbnew.BOARD()
        state, detail = C._chk_laid_pour_incursion(board, board, {})[:2]
        self.assertIsNone(state)
        self.assertIn("no reserved", detail)

    def test_checker_fails_on_detected_incursion(self):
        board, _power, signal = _board()
        track = pcbnew.PCB_TRACK(board)
        track.SetNet(signal)
        track.SetLayer(pcbnew.F_Cu)
        track.SetStart(pcbnew.VECTOR2I_MM(2, 5))
        track.SetEnd(pcbnew.VECTOR2I_MM(8, 5))
        track.SetWidth(pcbnew.FromMM(0.25))
        board.Add(track)
        state, detail = C._chk_laid_pour_incursion(board, board, {})[:2]
        self.assertFalse(state)
        self.assertIn("inside pour", detail)

    def test_wide_track_edge_is_detected_when_centerline_is_outside(self):
        board, _power, signal = _board()
        track = pcbnew.PCB_TRACK(board)
        track.SetNet(signal)
        track.SetLayer(pcbnew.F_Cu)
        track.SetStart(pcbnew.VECTOR2I_MM(-0.4, 1))
        track.SetEnd(pcbnew.VECTOR2I_MM(-0.4, 9))
        track.SetWidth(pcbnew.FromMM(1.0))
        board.Add(track)
        report = C.laid_pour_incursion_summary(board)
        self.assertEqual(report["n_tracks"], 1)

    def test_actual_via_diameter_is_detected_when_center_is_outside(self):
        board, _power, signal = _board()
        via = pcbnew.PCB_VIA(board)
        via.SetNet(signal)
        via.SetPosition(pcbnew.VECTOR2I_MM(-0.4, 5))
        via.SetWidth(pcbnew.FromMM(1.0))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(via)
        report = C.laid_pour_incursion_summary(board)
        self.assertEqual(report["n_vias"], 1)

    def test_own_net_copper_is_not_an_incursion(self):
        board, power, _signal = _board()
        track = pcbnew.PCB_TRACK(board)
        track.SetNet(power)
        track.SetLayer(pcbnew.F_Cu)
        track.SetStart(pcbnew.VECTOR2I_MM(1, 5))
        track.SetEnd(pcbnew.VECTOR2I_MM(9, 5))
        track.SetWidth(pcbnew.FromMM(1.0))
        board.Add(track)
        report = C.laid_pour_incursion_summary(board)
        self.assertEqual((report["n_parts"], report["n_tracks"], report["n_vias"]),
                         (0, 0, 0))

    def test_post_route_guard_refuses_foreign_laid_pour_incursion(self):
        board, power, signal = _board()
        start = pcbnew.VECTOR2I_MM(2, 5)
        end = pcbnew.VECTOR2I_MM(8, 5)
        self.assertFalse(FR._tap_foreign_clear(
            board, start, end, pcbnew.FromMM(0.25), pcbnew.F_Cu,
            pcbnew.FromMM(0.2), {signal.GetNetCode()}))
        self.assertTrue(FR._tap_foreign_clear(
            board, start, end, pcbnew.FromMM(0.25), pcbnew.F_Cu,
            pcbnew.FromMM(0.2), {power.GetNetCode()}))
        self.assertFalse(FR._via_spot_clear(
            board, pcbnew.VECTOR2I_MM(5, 5), pcbnew.FromMM(0.6),
            pcbnew.FromMM(0.2), {signal.GetNetCode()},
            drill_nm=pcbnew.FromMM(0.3), net_code=signal.GetNetCode()))

    def test_declared_internal_power_plane_is_not_a_reserved_pour(self):
        board = pcbnew.BOARD()
        board.SetCopperLayerCount(6)
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
        board.SetLayerName(board.GetLayerID("In3.Cu"), "PWR")
        power = pcbnew.NETINFO_ITEM(board, "PWR")
        signal = pcbnew.NETINFO_ITEM(board, "SIG")
        board.Add(power)
        board.Add(signal)
        zone = pcbnew.ZONE(board)
        zone.SetNet(power)
        zone.SetLayer(board.GetLayerID("In3.Cu"))
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in ((0, 0), (10, 0), (10, 10), (0, 10)):
            outline.Append(pcbnew.VECTOR2I_MM(x, y))
        board.Add(zone)
        via = pcbnew.PCB_VIA(board)
        via.SetNet(signal)
        via.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(via)
        self.assertEqual(FAB.board_profile_name(board), "jlcpcb_6l_pofv_signal")
        report = C.laid_pour_incursion_summary(board)
        self.assertFalse(report["applicable"])
        self.assertEqual(report["status"], "na")


class TestRealHubAllocation(unittest.TestCase):
    HUB = os.path.join(ROOT, "beta", "hub-standard-rev2", "candidate",
                       "hub-standard-rev2-candidate.kicad_pcb")

    @unittest.skipUnless(os.path.isfile(HUB), "Hub candidate required")
    def test_absent_requested_rail_is_refused(self):
        board = pcbnew.LoadBoard(self.HUB)
        with self.assertRaises(SLAB.SlabAllocationError) as raised:
            SLAB.synthesize_slab_pours(
                board, [{"net": "/NO_SUCH_RAIL", "layers": ("In3.Cu",)}])
        self.assertEqual(raised.exception.failures,
                         (("/NO_SUCH_RAIL", "In3.Cu"),))

    @unittest.skipUnless(os.path.isfile(HUB), "Hub candidate required")
    def test_stale_candidate_diagnostic_fails_closed_on_every_current_ask(self):
        board = pcbnew.LoadBoard(self.HUB)
        asks = WAVE.BOARD_PARAMS["hub-standard-rev2"]["pour_asks"]
        previous = os.environ.get("CEC_THERMAL_BOARD_HINT")
        os.environ["CEC_THERMAL_BOARD_HINT"] = self.HUB
        try:
            pours, report = SLAB.synthesize_slab_pours(
                board, asks, strict=False)
        finally:
            if previous is None:
                os.environ.pop("CEC_THERMAL_BOARD_HINT", None)
            else:
                os.environ["CEC_THERMAL_BOARD_HINT"] = previous
        expected = {(ask["net"], "In3.Cu") for ask in asks}
        self.assertEqual(set(report), expected)
        self.assertTrue(all(row.get("allocation_failed_closed")
                            for row in report.values()))
        # Non-strict is diagnostic only: it may return provisional polygons,
        # including zero or multiple fragments for an ask, but every row
        # remains explicitly blocked and cannot be released. Do not encode the
        # retired one-giant-manifold-per-rail shape as an allocation contract.
        self.assertTrue(pours)
        self.assertLessEqual({p["net"] for p in pours},
                             {ask["net"] for ask in asks})

    @unittest.skipUnless(os.path.isfile(HUB), "Hub candidate required")
    def test_current_hub_allocation_is_refused_until_widths_are_satisfied(self):
        board = pcbnew.LoadBoard(self.HUB)
        asks = WAVE.BOARD_PARAMS["hub-standard-rev2"]["pour_asks"]
        previous = os.environ.get("CEC_THERMAL_BOARD_HINT")
        os.environ["CEC_THERMAL_BOARD_HINT"] = self.HUB
        try:
            with self.assertRaises(SLAB.SlabAllocationError) as raised:
                SLAB.synthesize_slab_pours(
                    board, asks)
        finally:
            if previous is None:
                os.environ.pop("CEC_THERMAL_BOARD_HINT", None)
            else:
                os.environ["CEC_THERMAL_BOARD_HINT"] = previous
        self.assertEqual({key[0] for key in raised.exception.failures},
                         {ask["net"] for ask in asks})


if __name__ == "__main__":
    unittest.main()
