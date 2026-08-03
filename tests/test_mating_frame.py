#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# mating_frame_pins v2 teeth (structural segmented mezz, owner GO 2026-07-22,
# docs/mezz-structural-segments-2026-07-22.md): the segment-list contract form,
# the legacy single-connector form (unchanged behavior), the R1/R2 mount forms,
# the mounting footprint override plumbing, and THE property that actually
# matters -- mating fields land coincident after each side's declared physical
# transform.
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cec_fresh_wave import (mating_frame_pins, MEZZ_HUB_24PIN,
                            BOARD_PARAMS, BOARD_WH)              # noqa: E402


LEGACY = {
    "conn_dc": (10.0, 5.0), "conn_rot": 180,
    "mount_dc": ((-30.0, 2.0), (30.0, 18.0)),
    "sides": {"a": {"conn_ref": "J6", "mount_refs": ("H1", "H2"),
                    "mirror_x": False},
              "b": {"conn_ref": "J6", "mount_refs": ("H1", "H2"),
                    "mirror_x": False}},
}

V2 = {
    "conns": [{"ref": "J6P", "dc": (-32.0, 2.5), "rot": 0},
              {"ref": "J6C", "dc": (33.0, -10.5), "rot": 0},
              {"ref": "J6D", "dc": (33.0, 19.5), "rot": 90}],
    "mount_dc": ((-20.0, 14.0),),
    "mount_fp": "cec-MountingHole:MountingHole_2.2mm_M2_Pad_Via",
    "mount_net": "GND",
    "mount_function": "inter-board-ground-lug",
    "mount_electrical_role": "supplemental-ground-bond",
    "mount_population": "fit",
    "mount_contact": "conductive-fastener-on-exposed-copper",
    "sides": {"a": {"mount_refs": ("H1",), "mirror_x": False},
              "b": {"mount_refs": ("H1",), "mirror_x": False}},
}


class TestLegacyForm(unittest.TestCase):
    def test_single_conn_and_mounts(self):
        out = mating_frame_pins(80.0, 60.0, LEGACY, "a")
        self.assertEqual(out["anchor_pins"], {"J6": (50.0, 35.0, 180)})
        self.assertEqual(len(out["mount_pos_override"]), 2)
        self.assertNotIn("mount_fp_override", out)   # legacy: platform default land


class TestV2Form(unittest.TestCase):
    def test_three_segments_one_provisioned_mount(self):
        out = mating_frame_pins(74.0, 55.0, V2, "a")
        pins = out["anchor_pins"]
        self.assertEqual(set(pins), {"J6P", "J6C", "J6D"})
        self.assertEqual(pins["J6D"][2], 90)               # per-segment rot honored
        self.assertEqual(list(out["mount_pos_override"]), ["H1"])
        self.assertEqual(out["mount_fp_override"],
                         {"H1": "cec-MountingHole:MountingHole_2.2mm_M2_Pad_Via"})

    def test_r1_pure_empty_mounts(self):
        c = dict(V2, mount_dc=())
        out = mating_frame_pins(74.0, 55.0, c, "a")
        self.assertEqual(out["mount_pos_override"], {})
        self.assertNotIn("mount_fp_override", out)

    def test_mate_invariant_constant_translation(self):
        """Every mating ref must differ between the two sides by the SAME
        (dx, dy) -- the property that makes the stacked fields coincident,
        independent of either board's size."""
        a = mating_frame_pins(74.0, 55.0, V2, "a")
        b = mating_frame_pins(88.0, 70.0, V2, "b")
        deltas = set()
        for ref in a["anchor_pins"]:
            ax, ay, _ = a["anchor_pins"][ref]
            bx, by, _ = b["anchor_pins"][ref]
            deltas.add((round(bx - ax, 6), round(by - ay, 6)))
        for ref in a["mount_pos_override"]:
            ax, ay = a["mount_pos_override"][ref]
            bx, by = b["mount_pos_override"][ref]
            deltas.add((round(bx - ax, 6), round(by - ay, 6)))
        self.assertEqual(len(deltas), 1,
                         f"mate invariant broken: multiple deltas {deltas}")


class TestProductionContract(unittest.TestCase):
    def test_mezz_hub_24pin_is_v2_segments(self):
        self.assertIn("conns", MEZZ_HUB_24PIN)
        refs = [c["ref"] for c in MEZZ_HUB_24PIN["conns"]]
        self.assertEqual(refs, ["J6P", "J6C", "J6D"])
        # Exactly one populated M2 inter-board ground lug.
        self.assertEqual(len(MEZZ_HUB_24PIN["mount_dc"]), 1)
        self.assertIn("M2", MEZZ_HUB_24PIN["mount_fp"])
        self.assertEqual(MEZZ_HUB_24PIN["mount_net"], "GND")
        self.assertEqual(MEZZ_HUB_24PIN["mount_function"],
                         "inter-board-ground-lug")
        self.assertEqual(MEZZ_HUB_24PIN["mount_electrical_role"],
                         "supplemental-ground-bond")
        self.assertEqual(MEZZ_HUB_24PIN["mount_population"], "fit")
        self.assertEqual(MEZZ_HUB_24PIN["mount_contact"],
                         "conductive-fastener-on-exposed-copper")
        for side in ("atx-24pin-rev3", "hub-standard-rev2"):
            out = mating_frame_pins(*BOARD_WH[side], MEZZ_HUB_24PIN, side)
            self.assertEqual(set(out["anchor_pins"]), {"J6P", "J6C", "J6D"})
            self.assertEqual(list(out["mount_pos_override"]), ["H1"])

    def test_dead_bug_reflection_is_position_and_rotation_conjugate(self):
        atx = mating_frame_pins(86.0, 95.0, MEZZ_HUB_24PIN,
                                "atx-24pin-rev3")
        hub = mating_frame_pins(86.0, 74.0, MEZZ_HUB_24PIN,
                                "hub-standard-rev2")
        hdx, hdy = MEZZ_HUB_24PIN["stack"]["hub_assembly_dc_mm"]
        for ref, (ax, ay, ar) in atx["anchor_pins"].items():
            hx, hy, hr = hub["anchor_pins"][ref]
            self.assertAlmostEqual(ax - 43.0, hdx - (hx - 43.0))
            self.assertAlmostEqual(ay - 47.5, hdy + (hy - 37.0))
            self.assertAlmostEqual(ar % 360.0, (180.0 - hr) % 360.0)
        for ref, (ax, ay) in atx["mount_pos_override"].items():
            hx, hy = hub["mount_pos_override"][ref]
            self.assertAlmostEqual(ax - 43.0, hdx - (hx - 43.0))
            self.assertAlmostEqual(ay - 47.5, hdy + (hy - 37.0))

    def test_rj45_height_has_nominal_stack_margin(self):
        stack = MEZZ_HUB_24PIN["stack"]
        self.assertEqual(stack["board_gap_mm"], 18.0)
        self.assertGreaterEqual(stack["nominal_height_margin_mm"], 4.0)
        self.assertAlmostEqual(stack["board_gap_mm"]
                               - stack["inward_component_height_mm"],
                               stack["nominal_height_margin_mm"])
        self.assertIn("-17-", stack["header_family"])
        self.assertEqual(stack["standoff_thread"], "M2.5")
        self.assertEqual(stack["hub_assembly_dc_mm"], (0.0, -0.7))
        guard = stack["atx_planar_guard_mm"]
        self.assertGreaterEqual(stack["atx_top_access_band_mm"],
                                stack["atx_top_header_inboard_reach_mm"] + guard)
        self.assertGreaterEqual(stack["atx_bottom_access_band_mm"],
                                stack["atx_bottom_header_inboard_reach_mm"] + guard)

    def test_user_access_and_edge_orientation_contract(self):
        hub = BOARD_PARAMS["hub-standard-rev2"]
        self.assertEqual(BOARD_WH["hub-standard-rev2"], (86.0, 74.0))
        self.assertEqual(BOARD_WH["atx-24pin-rev3"], (86.0, 95.0))
        self.assertTrue(all(hub["edge_override"][r] == "left"
                            for r in ("J2", "J3", "J4", "J5")))
        self.assertEqual(set(hub["fixed_back_refs"]), set())
        self.assertEqual(hub["anchor_pins"]["SW_RESET"][:2], (75.0, 20.0))
        self.assertEqual(hub["anchor_pins"]["SW_BOOT"][:2], (75.0, 27.0))
        self.assertEqual(hub["logo_side"], "back")
        atx = BOARD_PARAMS["atx-24pin-rev3"]
        self.assertEqual(atx["edge_override"]["J3"], "bottom")
        self.assertTrue(all(atx["edge_override"][f"TB{i}"] == "top"
                            for i in range(1, 11)))

    def test_pattern_asymmetric_one_way_insertion(self):
        """A 180-degree mistake cannot put any segment over its own mate.

        The three segment sizes are deliberately unique (2x2, 2x3, 2x4), so a
        cross-ref proximity is not a seatable mate and must not be used as the
        asymmetry metric. This preserves the requested bilateral support while
        retaining one-way mechanical keying.
        """
        import math
        for segment in MEZZ_HUB_24PIN["conns"]:
            x, y = segment["dc"]
            d = math.hypot(x - (-x), y - (-y))
            self.assertGreaterEqual(
                d, 8.0,
                f"{segment['ref']} is too close to its own 180-degree mate "
                f"({d:.1f}mm)")

    def test_structural_support_is_bilaterally_balanced(self):
        pts = {c["ref"]: c["dc"] for c in MEZZ_HUB_24PIN["conns"]}
        px, py = pts["J6P"]
        dx, dy = pts["J6D"]
        cx, cy = pts["J6C"]
        hx, hy = MEZZ_HUB_24PIN["mount_dc"][0]
        self.assertLess(px, 0.0)
        self.assertGreater(dx, 0.0)
        self.assertLessEqual(abs(abs(px) - abs(dx)), 12.0)
        self.assertLessEqual(abs(py - dy), 8.0)
        self.assertEqual((hx, hy), (-cx, cy))

    def test_runtime_size_rebuilds_every_stack_datum(self):
        import cec_fresh_wave as wave
        W, H = 91.0, 101.0
        session, _ = wave._build_session(
            "atx-24pin-rev3", W, H, "plain", "compact", 5,
            pourfirst_artifact=False)
        expected = mating_frame_pins(W, H, MEZZ_HUB_24PIN,
                                     "atx-24pin-rev3")
        for ref, pin in expected["anchor_pins"].items():
            self.assertEqual(session.cfg.pins[ref], pin)
        self.assertEqual(session.cfg.params["mount_pos_override"],
                         expected["mount_pos_override"])


if __name__ == "__main__":
    unittest.main()
