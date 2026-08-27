#!/usr/bin/env python3
"""Regression teeth for topology-owned compact passive placement."""

import math
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_synth_pipeline as S  # noqa: E402


def _comp(ref, value="fixture"):
    return S.Comp(ref=ref, value=value)


class PassiveOwnerLocalityTest(unittest.TestCase):
    def test_private_sense_node_beats_global_raw_rail_anchor(self):
        # R17 touches both a broad raw rail at J_PWR and the private ADC sense
        # node at U1.  Physical ownership belongs to U1, not the connector.
        nl = S.Netlist(
            comps={r: _comp(r) for r in
                   ("R17", "R18", "U1", "J_PWR", "D1", "D2", "D3")},
            nets={
                "/5VSB_RAW": [("R17", "1"), ("J_PWR", "1"),
                               ("D1", "1"), ("D2", "1"), ("D3", "1")],
                "/5VSB_SENSE": [("R17", "2"), ("R18", "1"), ("U1", "18")],
                "GND": [("R18", "2"), ("U1", "1")],
            })
        spec, _series = S.derive_passive_spec(
            nl, ["R17", "R18"], ["U1"], anchor_refs={"J_PWR"})
        self.assertEqual(spec["R17"], ("U1", "18"))
        self.assertEqual(spec["R18"], ("U1", "18"))

    def test_connector_preference_remains_after_locality_tie(self):
        nl = S.Netlist(
            comps={r: _comp(r) for r in ("R1", "U1", "J1")},
            nets={"/CC1": [("R1", "1"), ("U1", "2"), ("J1", "A5")],
                  "GND": [("R1", "2"), ("U1", "1")]})
        spec, _series = S.derive_passive_spec(
            nl, ["R1"], ["U1"], anchor_refs={"J1"})
        self.assertEqual(spec["R1"], ("J1", "A5"))

    def test_shared_owner_uses_private_divider_node_not_global_rail_pad(self):
        nl = S.Netlist(
            comps={r: _comp(r) for r in
                   ("R_TOP", "R_BOT", "U1", "J1", "X1", "X2")},
            nets={
                "/RAW": [("R_TOP", "1"), ("U1", "7"), ("J1", "1"),
                         ("X1", "1"), ("X2", "1")],
                "/OV1": [("R_TOP", "2"), ("R_BOT", "1"), ("U1", "5")],
                "GND": [("R_BOT", "2"), ("U1", "12")],
            })
        spec, _series = S.derive_passive_spec(
            nl, ["R_TOP", "R_BOT"], ["U1"], anchor_refs={"J1"})
        self.assertEqual(spec["R_TOP"], ("U1", "5"))
        self.assertEqual(spec["R_BOT"], ("U1", "5"))

    def test_private_ic_connector_series_resistor_owns_scarce_ic_escape(self):
        nl = S.Netlist(
            comps={r: _comp(r) for r in ("R19", "U1", "J1")},
            nets={
                "/UART_TX": [("R19", "1"), ("U1", "19")],
                "/UART_TXC": [("R19", "2"), ("J1", "3")],
            })
        spec, series = S.derive_passive_spec(
            nl, ["R19"], ["U1"], anchor_refs={"J1"})
        self.assertEqual(spec["R19"], ("U1", "19"))
        self.assertNotIn("R19", series)
        self.assertEqual(
            S._local_signal_followers(nl, spec),
            [("R19", "U1", "19", "/UART_TX", 2)])

    def test_private_series_rule_does_not_capture_connector_pulldown(self):
        nl = S.Netlist(
            comps={r: _comp(r) for r in ("R_CC", "U1", "J1")},
            nets={
                "/CC1": [("R_CC", "1"), ("U1", "2"), ("J1", "A5")],
                "GND": [("R_CC", "2"), ("U1", "1")],
            })
        spec, series = S.derive_passive_spec(
            nl, ["R_CC"], ["U1"], anchor_refs={"J1"})
        self.assertEqual(spec["R_CC"], ("J1", "A5"))
        self.assertNotIn("R_CC", series)

    def test_ic_divider_midpoint_beats_equal_fanout_connector_reference(self):
        # The top divider resistor touches two three-member signal nets.  The
        # IC/R_TOP/R_BOTTOM net is the compact ADC cell; J/TVS/R_TOP is only
        # the distributed source/reference side and must not split the pair.
        nl = S.Netlist(
            comps={r: _comp(r) for r in
                   ("R_TOP", "R_BOTTOM", "U1", "J1", "D1")},
            nets={
                "/REFERENCE": [("D1", "1"), ("J1", "5"),
                               ("R_TOP", "1")],
                "/SENSE": [("R_TOP", "2"), ("R_BOTTOM", "1"),
                           ("U1", "39")],
                "GND": [("R_BOTTOM", "2"), ("U1", "1")],
            })
        spec, _series = S.derive_passive_spec(
            nl, ["R_TOP", "R_BOTTOM"], ["U1"], anchor_refs={"J1"})
        self.assertEqual(spec["R_TOP"], ("U1", "39"))
        self.assertEqual(spec["R_BOTTOM"], ("U1", "39"))


class ClusterFollowerContractTest(unittest.TestCase):
    def test_parallel_signal_ground_pair_rotates_for_unobstructed_escapes(self):
        import cec_pcb

        nl = S.Netlist(
            comps={r: _comp(r) for r in ("C1", "D1", "J1")},
            nets={
                "/DETECT": [("C1", "1"), ("D1", "1"), ("J1", "8")],
                "GND": [("C1", "2"), ("D1", "2"), ("J1", "SH")],
            })
        stamps = {"C1": (10.0, 13.0, 90.0),
                  "D1": (10.4, 10.0, 90.0)}
        owners = {"J1": [("C1", "8"), ("D1", "8")]}
        local = {
            "C1": {"1": (0.48, 0.0), "2": (-0.48, 0.0)},
            "D1": {"1": (1.05, 0.0), "2": (-1.05, 0.0)},
        }
        sizes = {
            "C1": {"1": (0.56, 0.62), "2": (0.56, 0.62)},
            "D1": {"1": (0.60, 0.45), "2": (0.60, 0.45)},
        }
        with mock.patch.object(
                cec_pcb, "local_pads",
                side_effect=lambda comp: local[comp.ref]), \
                mock.patch.object(
                    cec_pcb, "local_pad_sizes",
                    side_effect=lambda comp: sizes[comp.ref]):
            changed = S._align_parallel_two_terminal_fixed_stamps(
                nl, nl.comps, stamps, owners)

        self.assertEqual(set(changed), {"C1", "D1"})
        self.assertEqual(stamps["C1"][2] % 180.0, 0.0)
        self.assertEqual(stamps["D1"][2] % 180.0, 0.0)

    def test_owner_pad_alignment_distinguishes_outward_from_sideways(self):
        owner = (10.0, 10.0, 0.0)
        top_pin = (10.0, 8.0)
        self.assertAlmostEqual(
            S._pad_outward_alignment(owner, top_pin, (10.0, 6.0)), 1.0)
        self.assertAlmostEqual(
            S._pad_outward_alignment(owner, top_pin, (12.0, 8.0)), 0.0)
        self.assertAlmostEqual(
            S._pad_outward_alignment(owner, top_pin, (10.0, 9.0)), -1.0)

    def test_pad_escape_visibility_rejects_sibling_land_crossing(self):
        obstacles = [(10.0, 11.0, 0.4)]
        self.assertFalse(S._segment_avoids_pad_disks(
            (10.0, 10.0), (10.0, 12.0), obstacles))
        self.assertTrue(S._segment_avoids_pad_disks(
            (10.0, 10.0), (8.0, 10.0), obstacles))

    def test_rectangular_pad_escape_uses_orthogonal_neck(self):
        obstacle = [(0.6, 1.4, -0.2, 0.2)]
        self.assertFalse(S._segment_avoids_pad_boxes(
            (0.0, 0.0), (2.0, 0.0), obstacle))
        length = S._pad_box_path_length(
            (0.0, 0.0), (2.0, 0.0), obstacle,
            max_lane_offset=1.0, lane_step=0.25)
        self.assertGreater(length, 2.0)
        self.assertLess(length, float("inf"))

    def test_rectangular_pad_escape_refuses_enclosed_endpoint(self):
        self.assertEqual(S._pad_box_path_length(
            (0.0, 0.0), (2.0, 0.0), [(-0.1, 0.1, -0.1, 0.1)]),
            float("inf"))

    def test_pad_escape_never_certifies_arbitrary_angle_leg(self):
        length = S._pad_box_path_length(
            (0.0, 0.0), (1.0, 2.0), [], max_lane_offset=0.0)
        self.assertAlmostEqual(length, 1.0 + math.sqrt(2.0))
        self.assertGreater(length, math.sqrt(5.0),
                           "arbitrary-angle direct rays are not routable proof")

    def test_blueprint_and_explicit_pins_are_not_movable_followers(self):
        got = S._cluster_passive_refs(
            ["C1", "C2", "R1", "R2"], blueprint_refs={"R2"},
            pinned_refs={"C1": (63.8, 42.0, 0.0)})
        self.assertEqual(got, ["C2", "R1"])

    def test_late_reseat_scores_an_owned_passive_only_against_owner(self):
        placed = {
            "U5": (10.0, 11.0, 0.0),
            "GND_A": (70.0, 60.0, 0.0),
            "GND_B": (80.0, 65.0, 0.0),
        }
        points = S._functional_affinity_points(
            "R_ILIM1", placed, {}, {"R_ILIM1": ("U5", "10")},
            {"R_ILIM1": {"U5", "GND_A", "GND_B"}})
        self.assertEqual(points, [(10.0, 11.0)])

    def test_only_low_fanout_non_power_followers_get_final_local_seats(self):
        nl = S.Netlist(
            comps={r: _comp(r) for r in
                   ("R_ILIM", "U1", "G1", "C_RAIL", "U2", "X1", "X2")},
            nets={
                "/U1_ILIM": [("R_ILIM", "1"), ("U1", "10")],
                "GND": [("R_ILIM", "2"), ("U1", "12")],
                "+5V": [("C_RAIL", "1"), ("U2", "1"),
                         ("X1", "1"), ("X2", "1")],
            })
        rows = S._local_signal_followers(
            nl, {"R_ILIM": ("U1", "10"), "C_RAIL": ("U2", "1")})
        self.assertEqual(rows,
                         [("R_ILIM", "U1", "10", "/U1_ILIM", 2)])

    def test_flow_through_pair_reserves_board_interior_exit(self):
        import cec_pcb

        protector = object()
        connector = object()
        nl = S.Netlist(
            comps={"D1": _comp("D1"), "J1": _comp("J1")},
            nets={
                "/USB_D_P": [("J1", "A6"), ("D1", "1"), ("D1", "4")],
                "/USB_D_N": [("J1", "A7"), ("D1", "3"), ("D1", "6")],
            })
        pads = {
            protector: {"1": (-1.0, -1.0), "3": (1.0, -1.0),
                        "4": (-1.0, 1.0), "6": (1.0, 1.0)},
            connector: {},
        }
        with mock.patch.object(
                cec_pcb, "local_pads", side_effect=lambda comp: pads[comp]):
            boxes = S._anchor_flow_through_pair_corridors(
                nl, {"D1": protector, "J1": connector},
                {"D1": (10.0, 10.0, 0.0),
                 "J1": (10.0, 20.0, 0.0)},
                {"D1": {"owner": "J1"}}, length_mm=6.0,
                margin_mm=0.55)

        self.assertEqual(len(boxes), 1)
        name, x0, x1, y0, y1 = boxes[0]
        self.assertEqual(name, "pair-escape:D1:/USB_D")
        self.assertAlmostEqual(x0, 8.45)
        self.assertAlmostEqual(x1, 11.55)
        self.assertAlmostEqual(y0, 2.45)
        self.assertAlmostEqual(y1, 9.55)

    def test_flow_through_pair_infers_unique_connector_owner(self):
        import cec_pcb

        protector = object()
        connector = object()
        endpoint = object()
        nl = S.Netlist(
            comps={"D1": _comp("D1"), "J1": _comp("J1"),
                   "U1": _comp("U1")},
            nets={
                "/USB_D_P": [("J1", "A6"), ("D1", "1"),
                               ("D1", "4"), ("U1", "2")],
                "/USB_D_N": [("J1", "A7"), ("D1", "3"),
                               ("D1", "6"), ("U1", "3")],
            })
        pads = {
            protector: {"1": (-1.0, -1.0), "3": (1.0, -1.0),
                        "4": (-1.0, 1.0), "6": (1.0, 1.0)},
            connector: {}, endpoint: {},
        }
        with mock.patch.object(
                cec_pcb, "local_pads", side_effect=lambda comp: pads[comp]):
            boxes = S._anchor_flow_through_pair_corridors(
                nl, {"D1": protector, "J1": connector, "U1": endpoint},
                {"D1": (10.0, 10.0, 0.0),
                 "J1": (10.0, 20.0, 0.0),
                 "U1": (10.0, 2.0, 0.0)},
                {}, length_mm=6.0, margin_mm=0.55)

        self.assertEqual(1, len(boxes))
        self.assertEqual("pair-escape:D1:/USB_D", boxes[0][0])

    def test_pair_endpoint_reserves_bounded_pad_launch_toward_next_station(self):
        import cec_pcb

        endpoint = object()
        protector = object()
        connector = object()
        nl = S.Netlist(
            comps={"U1": _comp("U1"), "D1": _comp("D1"),
                   "J1": _comp("J1")},
            nets={
                "/USB_D_P": [("U1", "18"), ("D1", "1"),
                               ("D1", "4"), ("J1", "A6")],
                "/USB_D_N": [("U1", "17"), ("D1", "3"),
                               ("D1", "6"), ("J1", "A7")],
            })
        pads = {
            endpoint: {"18": (1.0, -0.4), "17": (1.0, 0.4)},
            protector: {"1": (-1.0, -1.0), "3": (-1.0, 1.0),
                        "4": (1.0, -1.0), "6": (1.0, 1.0)},
            connector: {},
        }
        with mock.patch.object(
                cec_pcb, "local_pads", side_effect=lambda comp: pads[comp]):
            boxes = S._critical_pair_endpoint_corridors(
                nl, {"U1": endpoint, "D1": protector, "J1": connector},
                {"U1": (2.0, 10.0, 0.0),
                 "D1": (10.0, 10.0, 0.0),
                 "J1": (18.0, 10.0, 0.0)},
                length_mm=6.0, margin_mm=0.45)

        self.assertEqual(1, len(boxes))
        name, x0, x1, y0, y1 = boxes[0]
        self.assertEqual("pair-escape:U1:/USB_D", name)
        self.assertAlmostEqual(2.55, x0)
        self.assertAlmostEqual(9.45, x1)
        self.assertAlmostEqual(9.15, y0)
        self.assertAlmostEqual(10.85, y1)

    def test_unowned_part_keeps_neighbor_fallback(self):
        placed = {"U1": (2.0, 3.0, 0.0), "J1": (8.0, 9.0, 90.0)}
        points = S._functional_affinity_points(
            "X1", placed, {}, {}, {"X1": {"U1", "J1"}})
        self.assertCountEqual(points, [(2.0, 3.0), (8.0, 9.0)])


if __name__ == "__main__":
    unittest.main()
