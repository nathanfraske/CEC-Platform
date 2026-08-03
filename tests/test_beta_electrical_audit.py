import os
import sys
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_beta_electrical_audit as audit


class TestBetaElectricalAudit(unittest.TestCase):
    @staticmethod
    def _rec(value, *, lcsc="", mpn="", manufacturer="Samsung"):
        return {
            "lib_id": "x:part",
            "value": value,
            "footprint": "x:footprint",
            "dnp": False,
            "in_bom": True,
            "on_board": True,
            "props": {
                "LCSC": lcsc,
                "MPN": mpn,
                "Manufacturer": manufacturer if mpn else "",
            },
        }

    def test_capacitance_parser_handles_repo_notation(self):
        self.assertAlmostEqual(audit.capacitance_f("100nF"), 100e-9)
        self.assertAlmostEqual(audit.capacitance_f("0.1uF"), 100e-9)
        self.assertAlmostEqual(audit.capacitance_f("2u2"), 2.2e-6)
        self.assertAlmostEqual(audit.capacitance_f("4n7"), 4.7e-9)
        self.assertIsNone(audit.capacitance_f("TBD"))

    def test_local_net_contract_accepts_kicad_hierarchy_qualification(self):
        self.assertTrue(audit._same_net(
            "/HOLD-UP + 3V3 REGULATOR/+5V_HOLD", "/+5V_HOLD"))
        self.assertTrue(audit._same_net(
            "/POWER INPUT + SOURCE SELECTION/PSU_5V", "/PSU_5V"))
        self.assertFalse(audit._same_net(
            "/POWER INPUT + SOURCE SELECTION/PSU_5V", "/USB_VBUS"))

    def test_one_bypass_cap_cannot_cover_two_required_devices(self):
        inv = {
            "U1": self._rec("INA181A2IDBVR"),
            "U2": self._rec("INA181A2IDBVR"),
            "C1": self._rec("100nF", lcsc="C1525", mpn="CL05B104KO5NNNC"),
        }
        pins = {
            "U1": {"6": "+3V3"},
            "U2": {"6": "+3V3"},
            "C1": {"1": "+3V3", "2": "GND"},
        }
        findings = audit.check_passives("board", inv, pins)
        missing = [f for f in findings if f["code"] == "DEVICE_BYPASS_MISSING"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["severity"], "BLOCKER")

    def test_unselected_ldo_stability_cap_is_blocking(self):
        inv = {
            "U3": self._rec("LP5907MFX-3.3/NOPB"),
            "C1": self._rec("1uF"),
            "C2": self._rec("1uF", lcsc="C29936", mpn="CL10B105KA8NNNC"),
        }
        pins = {
            "U3": {"1": "+5V", "5": "+3V3"},
            "C1": {"1": "+5V", "2": "GND"},
            "C2": {"1": "+3V3", "2": "GND"},
        }
        findings = audit.check_passives("board", inv, pins)
        self.assertTrue(any(
            f["code"] == "CRITICAL_CAP_SELECTION" and
            f["severity"] == "BLOCKER" and f["ref"] == "U3"
            for f in findings
        ))

    def test_lp5907_requires_non_wireless_load_budget(self):
        inv = {
            "U1": self._rec("ESP32-C6-MINI-1-N4"),
            "U3": self._rec("LP5907MFX-3.3/NOPB"),
            "C1": self._rec("1uF", lcsc="C29936", mpn="CL10B105KA8NNNC"),
            "C2": self._rec("1uF", lcsc="C29936", mpn="CL10B105KA8NNNC"),
            "C3": self._rec("100nF", lcsc="C1525", mpn="CL05B104KO5NNNC"),
        }
        pins = {
            "U1": {"3": "+3V3"},
            "U3": {"1": "+5V", "5": "+3V3"},
            "C1": {"1": "+5V", "2": "GND"},
            "C2": {"1": "+3V3", "2": "GND"},
            "C3": {"1": "+3V3", "2": "GND"},
        }
        findings = audit.check_passives("board", inv, pins)
        headroom = [f for f in findings if f["code"] == "REGULATOR_HEADROOM_UNPROVEN"]
        self.assertEqual(len(headroom), 1)
        self.assertIn("worst-case +3V3 load budget", headroom[0]["message"])
        self.assertIn("wireless-disabled firmware mode", headroom[0]["message"])
        self.assertNotIn("RF TX", headroom[0]["message"])

    def test_tps2121_requires_bypass_on_each_power_node(self):
        inv = {
            "U5": self._rec("TPS2121RUXR"),
            "C1": self._rec("1uF", lcsc="C29936", mpn="CL10B105KA8NNNC"),
            "C2": self._rec("1uF", lcsc="C29936", mpn="CL10B105KA8NNNC"),
        }
        pins = {
            "U5": {"7": "IN1", "2": "IN2", "1": "OUT"},
            "C1": {"1": "IN1", "2": "GND"},
            "C2": {"1": "OUT", "2": "GND"},
        }
        findings = audit.check_passives("board", inv, pins)
        missing = [f for f in findings if f["code"] == "TPS2121_BYPASS_NODE"]
        self.assertEqual(len(missing), 1)
        self.assertIn("IN2", missing[0]["message"])

    def test_tps2121_shared_rail_still_requires_distinct_local_caps(self):
        inv = {
            "U5": self._rec("TPS2121RUXR"),
            "U11": self._rec("TPS2121RUXR"),
            "C1": self._rec("1uF", lcsc="C15849", mpn="CL10A105KB8NNNC"),
            "C2": self._rec("1uF", lcsc="C15849", mpn="CL10A105KB8NNNC"),
            "C3": self._rec("1uF", lcsc="C15849", mpn="CL10A105KB8NNNC"),
            "C4": self._rec("1uF", lcsc="C15849", mpn="CL10A105KB8NNNC"),
            "C5": self._rec("1uF", lcsc="C15849", mpn="CL10A105KB8NNNC"),
        }
        pins = {
            "U5": {"7": "A", "2": "B", "1": "SHARED"},
            "U11": {"7": "SHARED", "2": "C", "1": "D"},
            "C1": {"1": "A", "2": "GND"},
            "C2": {"1": "B", "2": "GND"},
            "C3": {"1": "SHARED", "2": "GND"},
            "C4": {"1": "C", "2": "GND"},
            "C5": {"1": "D", "2": "GND"},
        }
        findings = audit.check_passives("board", inv, pins)
        missing = [f for f in findings if f["code"] == "TPS2121_BYPASS_NODE"]
        self.assertEqual(len(missing), 1)
        self.assertIn("SHARED", missing[0]["message"])

    def test_role_normalizes_mating_net_names(self):
        self.assertEqual(audit._role("/+5V_SYS_PORT"), "POWER5")
        self.assertEqual(audit._role("+5VSB"), "POWER5")
        self.assertEqual(audit._role("/CAN_H_BUS"), "CAN_H")
        self.assertEqual(audit._role("/DETECT1"), "DETECT")
        self.assertEqual(audit._role("unconnected-(J6D-Pin_3-Pad3)"), "NC")

    def test_verified_lcsc_identity_mismatch_is_blocking(self):
        inv = {
            "D1": {
                "value": "PESD5V0S1BA",
                "footprint": "x:SOD-323",
                "dnp": False,
                "in_bom": True,
                "on_board": True,
                "props": {
                    "Manufacturer": "Nexperia",
                    "MPN": "PESD5V0S1BA",
                    "LCSC": "C5261083",
                },
            }
        }
        findings = audit.check_bom("board", inv)
        self.assertTrue(any(f["code"] == "SELECTED_PART_IDENTITY" and
                            f["severity"] == "BLOCKER" for f in findings))

    def test_verified_capacitor_package_mismatch_is_blocking(self):
        inv = {
            "C1": {
                "value": "10uF",
                "footprint": "x:C_0805_2012Metric",
                "dnp": False,
                "in_bom": True,
                "on_board": True,
                "props": {
                    "Manufacturer": "Samsung",
                    "MPN": "CL10A106MA8NRNC",
                    "LCSC": "C96446",
                },
            }
        }
        findings = audit.check_bom("board", inv)
        self.assertTrue(any(f["code"] == "PACKAGE_MISMATCH" and
                            f["severity"] == "BLOCKER" for f in findings))

    def test_cross_board_lcsc_identity_conflict_is_blocking(self):
        def rec(mpn, footprint):
            return {
                "dnp": False,
                "on_board": True,
                "footprint": footprint,
                "props": {
                    "LCSC": "C1", "Manufacturer": "Vendor", "MPN": mpn,
                },
            }

        boards = {
            "a": {"inventory": {"C1": rec("PART-A", "x:C_0402")}},
            "b": {"inventory": {"C2": rec("PART-B", "x:C_0603")}},
        }
        findings = audit.check_lcsc_consistency(boards)
        self.assertTrue(any(f["code"] == "LCSC_IDENTITY_CONFLICT"
                            for f in findings))
        self.assertTrue(any(f["code"] == "LCSC_PACKAGE_CONFLICT"
                            for f in findings))

    def test_dnp_in_source_bom_is_variant_warning(self):
        inv = {
            "FL1": {
                "lib_id": "x:Filter",
                "value": "optional",
                "footprint": "x:fp",
                "dnp": True,
                "in_bom": True,
                "on_board": True,
                "props": {},
            }
        }
        findings = audit.check_bom("board", inv)
        self.assertTrue(any(f["code"] == "DNP_IN_BOM" and
                            f["severity"] == "WARN" for f in findings))

    def test_legacy_power_symbol_is_not_a_physical_part(self):
        inv = {
            "PWR201": {
                "lib_id": "cec-power:+3V3",
                "value": "+3V3",
                "footprint": "",
                "dnp": False,
                "in_bom": True,
                "on_board": True,
                "props": {},
            }
        }
        self.assertEqual(audit.check_bom("board", inv), [])

    def test_in_house_daughterboard_field_is_not_a_purchased_part(self):
        inv = {
            "J1": {
                "lib_id": "x:Connector",
                "value": "ATX24 OUT FIELD",
                "footprint": "cec-Connector_Generic:ATX24_Daughterboard_Field_P4.20mm",
                "dnp": False,
                "in_bom": True,
                "on_board": True,
                "props": {
                    "Manufacturer": "CEC (in-house)",
                    "Description": "Bare field, NOT a stocked/purchased part.",
                },
            }
        }
        findings = audit.check_bom("board", inv)
        self.assertFalse(any(f["code"] in {"MISSING_BOM_FIELD",
                                             "GENERIC_CONNECTOR_SELECTION"}
                             for f in findings))

    def test_generic_pin_header_has_one_selection_blocker_not_missing_mpn_blocker(self):
        inv = {
            "J1": {
                "lib_id": "x:Connector",
                "value": "SIGNAL STUB",
                "footprint": "cec-Connector_PinHeader_2.54mm:PinHeader_1x04",
                "dnp": False,
                "in_bom": True,
                "on_board": True,
                "props": {"Manufacturer": "generic"},
            }
        }
        findings = audit.check_bom("board", inv)
        blockers = [f for f in findings if f["severity"] == "BLOCKER"]
        self.assertEqual([f["code"] for f in blockers],
                         ["GENERIC_CONNECTOR_SELECTION"])

    def test_orderable_pin_header_is_not_generic(self):
        inv = {
            "J1": {
                "lib_id": "x:Connector",
                "value": "ARGB",
                "footprint": "cec-Connector_PinHeader_2.54mm:HDR-TH_4P",
                "dnp": False,
                "in_bom": True,
                "on_board": True,
                "props": {
                    "Manufacturer": "Ckmtw",
                    "MPN": "B-2100S04P-A110",
                    "LCSC": "C124378",
                },
            }
        }
        findings = audit.check_bom("board", inv)
        self.assertFalse(any(f["code"] == "GENERIC_CONNECTOR_SELECTION"
                             for f in findings))

    def test_lp5907_accepts_a_diode_fed_anonymous_input_net(self):
        inv = {
            "U3": {
                "lib_id": "x:LP5907",
                "value": "LP5907MFX-3.3",
                "footprint": "x:SOT-23-5",
                "dnp": False,
                "in_bom": True,
                "on_board": True,
                "props": {},
            }
        }
        pins = {"U3": {"1": "Net-(D3-K)", "2": "GND", "3": "+3V3",
                        "4": "unconnected-(U3-NC-Pad4)", "5": "+3V3"}}
        findings = audit.check_topology("board", "unused.kicad_sch", inv, pins)
        self.assertFalse(any(f["code"] == "PIN_ROLE" and f["ref"] == "U3"
                             for f in findings))

    def test_grounded_tps2121_ov1_is_reported(self):
        inv = {
            "U5": {"value": "TPS2121RUXR", "dnp": False, "on_board": True},
            "U3": {"value": "LP5907MFX-3.3", "dnp": False, "on_board": True},
        }
        findings = audit._check_tps2121_ovp(
            "board", inv, {"U5": {"5": "GND", "7": "+5V"}})
        self.assertTrue(any(f["code"] == "OVP_DISABLED" and
                            f["severity"] == "BLOCKER" for f in findings))

    def test_hub_priority_contract_rejects_cp2_tied_to_in2(self):
        inv = {
            "L2": {"value": "TBD", "dnp": True, "in_bom": False,
                   "on_board": True},
        }
        pins = {
            "U5": {"1": "/PSU_5V", "2": "/USB_VBUS", "3": "/USB_VBUS",
                   "6": "/5VSB_RAW", "7": "/5VSB_RAW", "8": "/PSU_5V"},
            "U11": {"1": "/PSU_5V_KVM", "2": "/KVM_5V_IN", "3": "GND",
                    "6": "/PSU_5V", "7": "/PSU_5V", "8": "/PSU_5V_KVM"},
            "U7": {"1": "+5VSB", "2": "/PSU_5V_KVM", "3": "GND",
                   "6": "/MAIN_5V_RAW", "7": "/MAIN_5V_RAW", "8": "+5VSB"},
        }
        findings = audit.check_board_specific("hub-standard-rev2", inv, pins)
        self.assertTrue(any(f["code"] == "HUB_SOURCE_PRIORITY" and
                            f["severity"] == "BLOCKER" and f["ref"] == "U5"
                            for f in findings))

    def test_legacy_usb_diode_without_mux_is_blocking(self):
        inv = {
            "D2": {"value": "SS34", "dnp": False},
        }
        findings = audit.check_board_specific(
            "eps-8pin-rev3", inv,
            {"D2": {"1": "+5VSB", "2": "/VBUS"}},
        )
        self.assertTrue(any(f["code"] == "LEGACY_USB_ORING" for f in findings))

    def test_wrong_way_argb_pmos_is_blocking(self):
        inv = {
            "J1": {
                "value": "SATA_PWR_15P", "footprint": "selected",
                "props": {},
            },
            "Q1": {"value": "OTHER_PMOS"},
        }
        pins = {
            "J1": {"7": "SATA"},
            "Q1": {"1": "SATA", "2": "SATA", "3": "SATA",
                   "5": "LOAD", "6": "LOAD", "7": "LOAD", "8": "LOAD"},
            "F1": {"1": "LOAD"},
        }
        findings = audit.check_board_specific("argb-standard", inv, pins)
        self.assertTrue(any(f["code"] == "PMOS_REVERSE_POLARITY_ORIENTATION"
                            for f in findings))

    def test_correct_argb_pmos_body_diode_orientation_passes_topology_check(self):
        inv = {
            "J1": {
                "value": "SATA_PWR_15P", "footprint": "selected",
                "props": {},
            },
            "Q1": {"value": "OTHER_PMOS"},
        }
        pins = {
            "J1": {"7": "SATA"},
            "Q1": {"1": "LOAD", "2": "LOAD", "3": "LOAD",
                   "5": "SATA", "6": "SATA", "7": "SATA", "8": "SATA"},
            "F1": {"1": "LOAD"},
        }
        findings = audit.check_board_specific("argb-standard", inv, pins)
        self.assertFalse(any(f["code"] == "PMOS_REVERSE_POLARITY_ORIENTATION"
                             for f in findings))

    def test_c6_download_strap_requires_gpio8_pullup(self):
        inv = {
            "U1": {"value": "ESP32-C6-MINI-1-N4", "on_board": True,
                   "dnp": False},
            "R2": {"value": "10k", "on_board": True, "dnp": False},
            "SW1": {"value": "BOOT", "on_board": True, "dnp": False},
            "SW2": {"value": "RESET", "on_board": True, "dnp": False},
        }
        pins = {
            "U1": {"8": "EN", "22": "IO8", "23": "IO9"},
            "R2": {"1": "+3V3", "2": "EN"},
            "SW1": {"1": "GND", "2": "IO9"},
            "SW2": {"1": "GND", "2": "EN"},
        }
        findings = []
        audit._check_mcu_service_straps(
            findings, "board", "U1", inv, pins,
            "8", "23", c6_io8_pin="22")
        self.assertEqual(
            [f["code"] for f in findings], ["ESP32_C6_GPIO8_STRAP"])

        inv["R19"] = {"value": "10kOhm", "on_board": True, "dnp": False}
        pins["R19"] = {"1": "+3V3", "2": "IO8"}
        findings = []
        audit._check_mcu_service_straps(
            findings, "board", "U1", inv, pins,
            "8", "23", c6_io8_pin="22")
        self.assertEqual(findings, [])

    def test_pour_current_model_drift_is_blocking(self):
        findings = audit.check_pour_current_contract()
        conflicts = [f for f in findings
                     if f["code"] == "POUR_CURRENT_MODEL_CONFLICT"]
        self.assertTrue(any(f["board"] == "atx-24pin-rev3" and
                            "+5VSB" in f["message"] for f in conflicts))
        # The reviewed Hub model is now deliberately reconciled: 2.5 A on
        # mutually-exclusive shared-bus stages and 0.5 A on the held logic
        # reservoir.  Keep the ATX assertion above as a live negative fixture,
        # but a Hub conflict here would be a regression.
        self.assertFalse(any(f["board"] == "hub-standard-rev2"
                             for f in conflicts))


if __name__ == "__main__":
    unittest.main()
