#!/usr/bin/env python3
"""Regression teeth for the 2026-08-03 ATX/Hub dead-bug stack."""

import os
import sys
import json
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_sch_gates as gates  # noqa: E402
from cec_fresh_wave import MEZZ_HUB_24PIN  # noqa: E402
from cec_synth_pipeline import _rigid_row_clear_shift  # noqa: E402


class DeadBugStackContractTest(unittest.TestCase):
    def test_obsolete_atx_rj45_is_absent_from_authoritative_hierarchy(self):
        inv = gates.inventory(os.path.join(
            ROOT, "beta", "atx-24pin-rev3", "24pin-module.kicad_sch"))
        self.assertNotIn("J1", inv)
        self.assertTrue({"J2", "J6P", "J6C", "J6D"}.issubset(inv))

    def test_incomplete_hub_boost_reservation_is_archive_only(self):
        inv = gates.inventory(os.path.join(
            ROOT, "beta", "hub-standard-rev2", "hub-standard-rev2.kicad_sch"))
        self.assertFalse({"RJ_BUCK", "U9", "U10", "L2", "R29", "R30", "R31", "R32"} & set(inv))
        self.assertTrue({"RJ_HOLD", "U3", "L1", "C1"}.issubset(inv))

    def test_current_usb_pair_uses_kicad_pn_suffixes(self):
        for board, files in (
                ("atx-24pin-rev3", ("24pin-module.kicad_sch", "02-power-usb.kicad_sch")),
                ("hub-standard-rev2", ("hub-standard-rev2.kicad_sch", "03-mcu-usb.kicad_sch"))):
            text = "\n".join(open(os.path.join(ROOT, "beta", board, name),
                                   encoding="utf-8").read() for name in files)
            self.assertIn("USB_D_P", text)
            self.assertIn("USB_D_N", text)
            self.assertNotIn("USB_DP", text)
            self.assertNotIn("USB_DM", text)

        with open(os.path.join(ROOT, "beta", "atx-24pin-rev3",
                               "24pin-module.kicad_pro"), encoding="utf-8") as handle:
            project = json.load(handle)
        patterns = {row["pattern"]: row["netclass"] for row in
                    project["net_settings"]["netclass_patterns"]}
        self.assertEqual(patterns["*USB_D_P"], "USB")
        self.assertEqual(patterns["*USB_D_N"], "USB")
        self.assertNotIn("*RAIL*", patterns)

    def test_mezz_parts_are_side_specific_and_long_post(self):
        atx = gates.inventory(os.path.join(
            ROOT, "beta", "atx-24pin-rev3", "24pin-module.kicad_sch"))
        hub = gates.inventory(os.path.join(
            ROOT, "beta", "hub-standard-rev2", "hub-standard-rev2.kicad_sch"))
        for ref, count in (("J6P", 3), ("J6C", 4), ("J6D", 2)):
            self.assertEqual(atx[ref]["props"]["MPN"], f"TSW-10{count}-17-G-D")
            self.assertEqual(hub[ref]["props"]["MPN"], f"SSQ-10{count}-03-G-D")
            self.assertIn("PinHeader", atx[ref]["props"]["Footprint"])
            self.assertIn("PinSocket", hub[ref]["props"]["Footprint"])

    def test_reverse_leds_have_real_aperture_footprint_and_ordering(self):
        hub = gates.inventory(os.path.join(
            ROOT, "beta", "hub-standard-rev2", "hub-standard-rev2.kicad_sch"))
        self.assertNotIn("DL6", hub)
        for i in (1, 2, 3, 4, 5, 7):
            d = hub[f"DL{i}"]
            self.assertEqual(d["props"]["LCSC"], "C5149201")
            self.assertIn("ReverseMount", d["props"]["Footprint"])
            self.assertIn("SK6812MINI-E", d["props"]["Datasheet"])
        fp = open(os.path.join(
            ROOT, "lib", "vendor", "LED_SMD.pretty",
            "LED_SK6812MINI-E_3.2x2.8mm_P1.5mm_ReverseMount.kicad_mod"),
            encoding="utf-8").read()
        self.assertIn('(layer "Edge.Cuts")', fp)
        self.assertIn('(at -2.725 0.75)', fp)   # pin 1 = DOUT
        self.assertIn('(at 2.725 0.75)', fp)    # pin 4 = VDD
        dru = open(os.path.join(
            ROOT, "beta", "hub-standard-rev2",
            "hub-standard-rev2.kicad_dru"), encoding="utf-8").read()
        self.assertIn("reverse_led_vendor_aperture_clearance", dru)
        self.assertIn("edge_clearance (min 0.25mm)", dru)
        cand_dru = open(os.path.join(
            ROOT, "beta", "hub-standard-rev2", "candidate",
            "hub-standard-rev2-candidate.kicad_dru"), encoding="utf-8").read()
        self.assertIn("reverse_led_vendor_aperture_clearance", cand_dru)

        for ref in ("C29", "C30", "C31", "C32", "C33", "C34"):
            self.assertIn(ref, hub)
            self.assertEqual(hub[ref]["value"], "100nF")
        self.assertIn("U6 local", hub["C14"]["props"]["Note"])

    def test_blind_mate_row_moves_as_one_unit_around_mezzanine(self):
        row = {
            "TB4": (10.0, 14.0, 2.0, 6.0),
            "J_SIG1": (20.0, 24.0, 2.0, 6.0),
        }
        obstacles = {"J6C": (22.0, 30.0, 5.5, 12.0)}
        shift = _rigid_row_clear_shift(row, obstacles, 40.0)
        self.assertAlmostEqual(shift, -2.5)
        self.assertAlmostEqual((row["J_SIG1"][1] + shift)
                               - obstacles["J6C"][0], -0.5)

        # A signal-stub-only copper check still constrains the whole rigid
        # row to the board outline.
        rail = {"RS3": (17.0, 25.0, 5.5, 20.0)}
        shift = _rigid_row_clear_shift(
            {"J_SIG1": row["J_SIG1"]}, rail, 40.0, bounds_boxes=row)
        self.assertEqual(shift, 5.5)

        # Combining component and copper constraints must reject the smaller
        # rightward copper escape when it would re-enter a fixed connector.
        fixed = {"J6C": (25.0, 31.0, 5.5, 12.0)}
        shift = _rigid_row_clear_shift(
            {"J_SIG1": row["J_SIG1"]}, rail, 40.0, bounds_boxes=row,
            constraints=((row, fixed),
                         ({"J_SIG1": row["J_SIG1"]}, rail)))
        self.assertEqual(shift, -7.5)

    def test_can_is_preserved_and_stream_reservations_are_unchanged(self):
        comms = next(s for s in MEZZ_HUB_24PIN["conns"] if s["ref"] == "J6C")
        # Electrical role source lives in cec_mezz_contract; locate it through
        # the production segment declaration rather than parsing diagram text.
        import cec_mezz_contract as mezz
        roles = next(s["pin_roles"] for s in mezz.SEGMENTS if s["ref"] == "J6C")
        self.assertEqual(roles[3], "CAN_H")
        self.assertEqual(roles[5], "CAN_L")
        self.assertEqual(roles[4], "NC")
        self.assertEqual(roles[6], "NC")
        # Rotation is mechanical and may change when the joint-legality probe
        # re-seats the segment; the CAN/STREAM role map above must not.
        self.assertIn(comms["rot"], (0.0, 90.0, 180.0, 270.0))


if __name__ == "__main__":
    unittest.main()
