#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# mating_frame_pins v2 teeth (structural segmented mezz, owner GO 2026-07-22,
# docs/mezz-structural-segments-2026-07-22.md): the segment-list contract form,
# the legacy single-connector form (unchanged behavior), the R1/R2 mount forms,
# the M2 footprint override plumbing, and THE property that actually matters --
# the MATE INVARIANT: every mating ref differs between two sides by one constant
# translation, so the stacked fields land coincident.
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cec_fresh_wave import mating_frame_pins, MEZZ_HUB_24PIN     # noqa: E402


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
            out = mating_frame_pins(74.0, 55.0, MEZZ_HUB_24PIN, side)
            self.assertEqual(set(out["anchor_pins"]), {"J6P", "J6C", "J6D"})
            self.assertEqual(list(out["mount_pos_override"]), ["H1"])

    def test_pattern_asymmetric_one_way_insertion(self):
        """Owner keying directive (2026-07-23): the segment pattern must be
        asymmetric so the stack only assembles one way INTENTIONALLY -- the
        180-rotated pattern (the only physically relevant mis-orientation under
        no-flip) must land visibly far from the original."""
        import math
        pts = [c["dc"] for c in MEZZ_HUB_24PIN["conns"]]
        rot = [(-x, -y) for (x, y) in pts]
        d = min(math.hypot(a[0] - b[0], a[1] - b[1]) for a in pts for b in rot)
        self.assertGreaterEqual(d, 8.0,
                                f"segment pattern too symmetric ({d:.1f}mm): a "
                                f"180-degree mis-orientation would look seatable")


if __name__ == "__main__":
    unittest.main()
