#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Pin-level regression checks for the live rev3 Hub power-source topology."""

import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_pcb_reconcile  # noqa: E402


SCHEMATIC = os.path.join(
    ROOT, "beta", "hub-standard-rev2", "hub-standard-rev2.kicad_sch")


class TestHubPowerTopology(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        groups = cec_pcb_reconcile.netlist_groups(SCHEMATIC)
        cls.by_name = {name: set(members) for members, name in groups.items()}
        cls.all_refs = {ref for members in cls.by_name.values() for ref, _ in members}

    def net(self, suffix):
        matches = [members for name, members in self.by_name.items()
                   if name == suffix or name.endswith("/" + suffix)]
        self.assertEqual(len(matches), 1,
                         f"expected one exported net ending in {suffix!r}")
        return matches[0]

    def test_stack_rail_is_the_only_system_power_entry(self):
        rail = self.net("+5V_SYS")
        self.assertTrue({("J6P", "1"), ("J6P", "3"), ("J6P", "5"),
                         ("U7", "6"), ("U7", "7"), ("D8", "1"),
                         ("C27", "1"), ("R15", "1"), ("R35", "1")}
                        <= rail)

    def test_usb_vbus_reaches_backup_selector_across_hierarchy(self):
        rail = self.net("USB_VBUS")
        self.assertTrue({("J_USB", "A4"), ("J_USB", "A9"),
                         ("J_USB", "B4"), ("J_USB", "B9"),
                         ("U11", "6"), ("U11", "7"), ("C25", "1")}
                        <= rail)

    def test_kvm_and_usb_merge_only_at_u11_output(self):
        kvm = self.net("KVM_5V_IN")
        backup = self.net("PSU_5V_KVM")
        self.assertTrue({("F5", "2"), ("U11", "2")} <= kvm)
        self.assertTrue({("U11", "1"), ("U11", "8"), ("U7", "2")}
                        <= backup)

    def test_final_selected_rail_still_drives_holdup_detector(self):
        selected = self.net("+5VSB")
        self.assertTrue({("U7", "1"), ("U7", "8"), ("D1", "2"),
                         ("R12", "1")} <= selected)

    def test_source_status_reuses_the_retired_raw_rail_adc_lane(self):
        status = self.net("PWR_SOURCE_STATUS")
        self.assertTrue({("U7", "9"), ("U1", "18")} <= status)

    def test_retired_jpwr_stage_cannot_reappear(self):
        retired = {"J_PWR", "U5", "D9", "R_ILIM1", "C_SS1", "C9",
                   "C24", "R33", "R34", "R17", "R18"}
        self.assertFalse(retired & self.all_refs)


if __name__ == "__main__":
    unittest.main()
