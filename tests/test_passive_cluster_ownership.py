#!/usr/bin/env python3
"""Regression teeth for topology-owned compact passive placement."""

import os
import sys
import unittest

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


class ClusterFollowerContractTest(unittest.TestCase):
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

    def test_unowned_part_keeps_neighbor_fallback(self):
        placed = {"U1": (2.0, 3.0, 0.0), "J1": (8.0, 9.0, 90.0)}
        points = S._functional_affinity_points(
            "X1", placed, {}, {}, {"X1": {"U1", "J1"}})
        self.assertCountEqual(points, [(2.0, 3.0), (8.0, 9.0)])


if __name__ == "__main__":
    unittest.main()
