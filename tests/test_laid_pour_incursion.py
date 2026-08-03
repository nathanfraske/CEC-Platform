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
import cec_slab_pour as SLAB  # noqa: E402


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
    def test_current_allocator_replaces_overlapping_legacy_slabs(self):
        from shapely.geometry import Polygon

        board = pcbnew.LoadBoard(self.HUB)
        nets = []
        for zone in board.Zones():
            if ((zone.GetZoneName() or "").startswith("slab:")
                    and zone.GetNetname() not in nets):
                nets.append(zone.GetNetname())
        previous = os.environ.get("CEC_THERMAL_BOARD_HINT")
        os.environ.pop("CEC_THERMAL_BOARD_HINT", None)
        try:
            pours, report = SLAB.synthesize_slab_pours(
                board, [{"net": net, "layers": ("In3.Cu",)} for net in nets],
                strict=False)
        finally:
            if previous is None:
                os.environ.pop("CEC_THERMAL_BOARD_HINT", None)
            else:
                os.environ["CEC_THERMAL_BOARD_HINT"] = previous
        self.assertTrue(pours)
        self.assertTrue(all(row.get("allocation") == "weighted_fair_v1"
                            for row in report.values()))
        self.assertTrue(all(row.get("design_current_source") ==
                            "board_thermal_config" for row in report.values()))
        failed_width = {key[0] for key, row in report.items()
                        if row.get("min_width_ok") is False}
        self.assertEqual(failed_width,
                         {"+5VSB", "/5VSB_RAW", "/MAIN_5V_RAW", "/VCC_P2"})
        self.assertTrue(all(report[(net, "In3.Cu")]["allocation_failed_closed"]
                            for net in failed_width))
        self.assertAlmostEqual(sum(row["allocation_share"] for row in report.values()),
                               1.0, places=9)
        for index, left in enumerate(pours):
            left_shape = Polygon(left["polygon"]).buffer(0)
            for right in pours[index + 1:]:
                if left["net"] == right["net"] or left["layer"] != right["layer"]:
                    continue
                overlap = left_shape.intersection(Polygon(right["polygon"]).buffer(0)).area
                self.assertAlmostEqual(overlap, 0.0, places=9,
                                       msg="%s overlaps %s" % (left["net"], right["net"]))

    @unittest.skipUnless(os.path.isfile(HUB), "Hub candidate required")
    def test_current_hub_allocation_is_refused_until_widths_are_satisfied(self):
        board = pcbnew.LoadBoard(self.HUB)
        nets = sorted({zone.GetNetname() for zone in board.Zones()
                       if (zone.GetZoneName() or "").startswith("slab:")})
        previous = os.environ.get("CEC_THERMAL_BOARD_HINT")
        os.environ["CEC_THERMAL_BOARD_HINT"] = self.HUB
        try:
            with self.assertRaises(SLAB.SlabAllocationError) as raised:
                SLAB.synthesize_slab_pours(
                    board, [{"net": net, "layers": ("In3.Cu",)} for net in nets])
        finally:
            if previous is None:
                os.environ.pop("CEC_THERMAL_BOARD_HINT", None)
            else:
                os.environ["CEC_THERMAL_BOARD_HINT"] = previous
        self.assertEqual({key[0] for key in raised.exception.failures},
                         {"+5VSB", "/5VSB_RAW", "/MAIN_5V_RAW", "/VCC_P2"})


if __name__ == "__main__":
    unittest.main()
