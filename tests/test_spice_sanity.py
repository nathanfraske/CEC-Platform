import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_spice_sanity as spice


class TestNgspiceExecutable(unittest.TestCase):
    def test_explicit_override_wins(self):
        with mock.patch.dict(os.environ, {"CEC_NGSPICE": "chosen-ngspice"}, clear=True):
            self.assertEqual(spice._ngspice_executable(), "chosen-ngspice")

    def test_windows_prefers_console_binary(self):
        def which(name):
            return "C:/Spice64/bin/ngspice_con.exe" if name == "ngspice_con.exe" else None

        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(spice.os, "name", "nt"), \
                mock.patch.object(spice.shutil, "which", side_effect=which):
            self.assertEqual(spice._ngspice_executable(),
                             "C:/Spice64/bin/ngspice_con.exe")

    def test_windows_ignores_gui_environment_override(self):
        def which(name):
            return "C:/Spice64/bin/ngspice_con.exe" if name == "ngspice_con.exe" else None

        with mock.patch.dict(
                os.environ,
                {"CEC_NGSPICE": "C:/Spice64/bin/ngspice.exe"}, clear=True), \
                mock.patch.object(spice.os, "name", "nt"), \
                mock.patch.object(spice.cec_toolchain.shutil, "which", side_effect=which):
            self.assertEqual(spice._ngspice_executable(),
                             "C:/Spice64/bin/ngspice_con.exe")

    def test_windows_never_falls_back_to_gui_binary(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(spice.os, "name", "nt"), \
                mock.patch.object(spice.shutil, "which", return_value=None):
            self.assertEqual(spice._ngspice_executable(), "ngspice_con.exe")


class TestDeckGeneration(unittest.TestCase):
    def test_resistor_rkm_notation_is_parsed_without_losing_milliohms(self):
        self.assertEqual(spice._r_ohms("0R"), 0.0)
        self.assertAlmostEqual(spice._r_ohms("0R002"), 0.002)
        self.assertAlmostEqual(spice._r_ohms("4R7"), 4.7)
        self.assertAlmostEqual(spice._r_ohms("1k2"), 1200.0)

    def test_zero_ohm_link_is_collapsed_without_tiny_resistor(self):
        deck = spice.build_deck(
            {"R1": "0R"},
            {"NET_A": [("R1", "1")], "NET_B": [("R1", "2")]},
            sources=[("NET_A", 1.0)],
        )
        self.assertEqual(deck.n("NET_A"), deck.n("NET_B"))
        self.assertFalse(any("_R1 " in line for line in deck.lines))

    def test_usblc_flow_through_pairs_are_topology_connections(self):
        deck = spice.build_deck(
            {"D1": "USBLC6-2SC6"},
            {"DP_A": [("D1", "1")], "GND": [("D1", "2")],
             "DM_A": [("D1", "3")], "DM_B": [("D1", "4")],
             "VBUS": [("D1", "5")], "DP_B": [("D1", "6")]},
        )
        self.assertEqual(deck.n("DP_A"), deck.n("DP_B"))
        self.assertEqual(deck.n("DM_A"), deck.n("DM_B"))
        self.assertNotEqual(deck.n("VBUS"), deck.n("GND"))

    def test_dnp_parts_are_removed_from_default_assembly(self):
        comps, nets = spice._filter_assembly(
            {"L2": "TBD", "R1": "10k"},
            {"A": [("L2", "1"), ("R1", "1")],
             "B": [("L2", "2"), ("R1", "2")]},
            {"L2": {"dnp": True, "on_board": True},
             "R1": {"dnp": False, "on_board": True}},
        )
        self.assertNotIn("L2", comps)
        self.assertEqual(nets["A"], [("R1", "1")])

    def test_multi_supply_model_uses_unique_element_names(self):
        deck = spice.build_deck(
            {"U2": "TJA1051"},
            {"VCC": [("U2", "3")], "VIO": [("U2", "5")], "GND": []},
        )
        names = [line.split()[0].lower() for line in deck.lines
                 if line and not line.startswith(("*", "."))]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("r1_u2_ld0", names)
        self.assertIn("r1_u2_ld1", names)

    def test_tlv62569_setpoint_comes_from_actual_feedback_divider(self):
        deck = spice.build_deck(
            {"U3": "TLV62569DBVR", "R1": "560k", "R2": "100k", "L1": "2.2uH"},
            {"VIN": [("U3", "1"), ("U3", "4")],
             "GND": [("U3", "2"), ("R2", "2")],
             "SW": [("U3", "3"), ("L1", "1")],
             "FB": [("U3", "5"), ("R1", "2"), ("R2", "1")],
             "VOUT": [("R1", "1"), ("L1", "2")]},
        )
        source = next(line for line in deck.lines if "_U3_buck " in line)
        self.assertIn("min(3.96", source)
        self.assertEqual(deck.model_classes["U3"], "behavioral-buck-setpoint")

    def test_tlv75533_uses_reviewed_drv_pins_and_dropout(self):
        deck = spice.build_deck(
            {"U16": "TLV75533PDRVR"},
            {"+5VSB": [("U16", "6"), ("U16", "4")],
             "GND": [("U16", "3"), ("U16", "7")],
             "+3V3": [("U16", "1")]},
        )
        source = next(line for line in deck.lines if "_U16_0 " in line)
        self.assertIn("min(3.3", source)
        self.assertIn("- 0.238", source)

    def test_tps2121_uses_verified_in2_pin_and_joins_both_outputs(self):
        deck = spice.build_deck(
            {"U5": "TPS2121RUXR"},
            {"OUT_A": [("U5", "1")], "IN2": [("U5", "2")],
             "CP2": [("U5", "3")], "IN1": [("U5", "7")],
             "OUT_B": [("U5", "8")]},
            state={"tps2121_pos": 2},
        )
        switch = next(line for line in deck.lines if "_U5_sw " in line)
        self.assertIn(deck.n("IN2"), switch)
        self.assertNotIn(deck.n("CP2"), switch)
        self.assertEqual(deck.n("OUT_A"), deck.n("OUT_B"))

    def test_tps2121_selected_path_is_directional_for_reverse_blocking(self):
        deck = spice.build_deck(
            {"U5": "TPS2121RUXR"},
            {"OUT": [("U5", "1"), ("U5", "8")],
             "IN2": [("U5", "2")], "IN1": [("U5", "7")]},
            state={"tps2121_pos": 1},
        )
        selected = next(line for line in deck.lines if "_U5_sw " in line)
        self.assertTrue(selected.startswith("D"))
        self.assertEqual(
            selected.split()[1:3],
            [deck.n("IN1"), deck.n("OUT")],
        )
        self.assertIn("CEC_TPS2121_RCB", selected)
        self.assertEqual(
            deck.model_classes["U5"],
            "two-position-rcb-power-mux",
        )

    def test_external_rails_are_always_coupling_probes(self):
        rails = {"/MAIN_5V_RAW": 5.0, "/KVM_5V_RAW": 5.0, "/USB_VBUS": 5.0}
        internal = ["+5VSB"]
        self.assertEqual(
            spice._coupling_probe_nets(rails, internal, "/USB_VBUS"),
            ["/MAIN_5V_RAW", "/KVM_5V_RAW", "+5VSB"],
        )

    def test_tps2121_instances_have_independent_state_combinations(self):
        states = spice._tps2121_states({
            "U5": "TPS2121RUXR", "U7": "TPS2121RUXR", "R1": "10k",
        })
        self.assertEqual(len(states), 4)
        selections = {tuple(sorted(state["tps2121_positions"].items()))
                      for state, _label in states}
        self.assertIn((("U5", 1), ("U7", 2)), selections)
        self.assertIn((("U5", 2), ("U7", 1)), selections)

    def test_tps2121_fixed_priority_requires_cp2_ground(self):
        comps = {"U5": "TPS2121RUXR"}
        nets = {
            "OUT": [("U5", "1"), ("U5", "8")],
            "IN2": [("U5", "2"), ("U5", "3")],
            "GND": [("U5", "4"), ("U5", "12")],
            "PR1": [("U5", "6")],
            "IN1": [("U5", "7")],
        }
        findings = spice._tps2121_control_findings(comps, nets)
        self.assertTrue(any("CP2 pin 3" in finding for finding in findings))

    def test_connector_sources_cover_main_current_and_kvm_ingress(self):
        comps = {
            "J_IN1": "C1 PSU",
            "J_KVM": "CEC_NANOKVM_AUX_5P",
            "J_USB": "USB-C",
        }
        nets = {
            "C1_HI": [("J_IN1", "5")],
            "GND": [("J_IN1", "1"), ("J_KVM", "2"), ("J_USB", "A1")],
            "KVM_RAW": [("J_KVM", "1")],
            "VBUS_RAW": [("J_USB", "A4"), ("J_USB", "B4")],
        }
        self.assertEqual(
            spice._connector_source_rails(comps, nets),
            {"C1_HI": 12.0, "KVM_RAW": 5.0, "VBUS_RAW": 5.0},
        )

    def test_current_monitor_supply_pins_match_selected_packages(self):
        ina180 = spice.build_deck(
            {"U1": "INA180A2"},
            {"VS": [("U1", "5")], "WRONG": [("U1", "6")]},
        )
        self.assertTrue(any("_U1_ld0 n_VS " in line for line in ina180.lines))
        ina240 = spice.build_deck(
            {"U2": "INA240A3"},
            {"WRONG_TSSOP_VS": [("U2", "5")], "VS_SOIC": [("U2", "6")]},
        )
        self.assertTrue(any("_U2_ld0 n_VS_SOIC " in line for line in ina240.lines))

    def test_esp32_wroom_uses_pin2_and_no_fabricated_load_current(self):
        deck = spice.build_deck(
            {"U1": "ESP32-S3-WROOM-1"},
            {"VDD": [("U1", "2")], "EN": [("U1", "3")]},
        )
        load = next(line for line in deck.lines if "_U1_ld0 " in line)
        self.assertIn("n_VDD", load)
        self.assertTrue(load.endswith(" 1Meg"))

    def test_unmodeled_conduction_parts_are_explicit_coverage_gaps(self):
        deck = spice.build_deck(
            {"Q1": "UNKNOWN_FET", "SW1": "MODE", "RFH1": "10R"},
            {"A": [("Q1", "1"), ("SW1", "1"), ("RFH1", "1")],
             "B": [("Q1", "2"), ("SW1", "2"), ("RFH1", "2")],
             "C": [("Q1", "3")]},
        )
        self.assertTrue(any(gap.startswith("Q1:") for gap in deck.coverage_gaps))
        self.assertTrue(any(gap.startswith("SW1:") for gap in deck.coverage_gaps))
        self.assertFalse(any(gap.startswith("RFH1:") for gap in deck.coverage_gaps))

    def test_ao3400a_uses_verified_sot23_pins_and_body_diode(self):
        deck = spice.build_deck(
            {"Q1": "AO3400A"},
            {"GATE": [("Q1", "1")], "SOURCE": [("Q1", "2")],
             "DRAIN": [("Q1", "3")]},
        )
        switch = next(line for line in deck.lines if line.startswith("S1_Q1 "))
        body = next(line for line in deck.lines if line.startswith("D1_Q1_body "))
        self.assertEqual(
            switch.split()[1:5],
            [deck.n("DRAIN"), deck.n("SOURCE"), deck.n("GATE"), deck.n("SOURCE")],
        )
        self.assertEqual(body.split()[1:3], [deck.n("SOURCE"), deck.n("DRAIN")])
        self.assertFalse(deck.coverage_gaps)

    def test_ao4407a_uses_verified_so8_pins_and_polarity(self):
        deck = spice.build_deck(
            {"Q1": "AO4407A"},
            {"SOURCE": [("Q1", "1"), ("Q1", "2"), ("Q1", "3")],
             "GATE": [("Q1", "4")],
             "DRAIN": [("Q1", "5"), ("Q1", "6"), ("Q1", "7"), ("Q1", "8")]},
        )
        switch = next(line for line in deck.lines if line.startswith("S1_Q1 "))
        body = next(line for line in deck.lines if line.startswith("D1_Q1_body "))
        self.assertEqual(
            switch.split()[1:5],
            [deck.n("DRAIN"), deck.n("SOURCE"), deck.n("SOURCE"), deck.n("GATE")],
        )
        self.assertEqual(body.split()[1:3], [deck.n("DRAIN"), deck.n("SOURCE")])
        self.assertFalse(deck.coverage_gaps)

    def test_mf72_exact_part_uses_only_its_verified_cold_resistance(self):
        self.assertEqual(spice._r_ohms("MF72-5D-20"), 5.0)
        deck = spice.build_deck(
            {"RT1": "MF72-5D-20"},
            {"IN": [("RT1", "1")], "OUT": [("RT1", "2")]},
        )
        self.assertEqual(deck.model_classes["RT1"], "cold-ntc-resistor")
        self.assertTrue(any("self-heating" in note for note in deck.partial_models))
        self.assertFalse(deck.coverage_gaps)

    def test_sata_input_registers_forward_and_reverse_topology_cases(self):
        comps = {"J1": "SATA_PWR_15P", "RT1": "MF72-5D-20"}
        nets = {
            "SATA_IN": [("J1", "7"), ("J1", "8"), ("J1", "9")],
            "PROTECTED": [("RT1", "2")],
        }
        self.assertEqual(spice._external_source_rails(comps, nets),
                         {"SATA_IN": 5.0})
        cases = spice._registered_dc_fault_cases(comps, nets)
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0]["source_v"], -5.0)
        self.assertEqual(cases[0]["probe_net"], "PROTECTED")

    def test_boot_reset_tactile_switches_are_normal_open_in_normal_state(self):
        deck = spice.build_deck(
            {"SW_BOOT": "SW_BOOT", "SW_RESET": "SW_RST"},
            {"A": [("SW_BOOT", "1"), ("SW_RESET", "1")],
             "B": [("SW_BOOT", "2"), ("SW_RESET", "2")]},
        )
        self.assertEqual(deck.coverage_gaps, [])
        self.assertEqual(deck.model_classes["SW_BOOT"],
                         "normally-open-control-switch")

    def test_smaj_is_treated_as_tvs_not_forward_schottky(self):
        deck = spice.build_deck(
            {"D1": "SMAJ5.0A"},
            {"GND": [("D1", "1")], "VBUS": [("D1", "2")]},
        )
        self.assertEqual(deck.model_classes["D1"], "tvs-orientation-only")

    def test_bat54s_uses_verified_dual_series_clamp_pinout(self):
        deck = spice.build_deck(
            {"D1": "BAT54S"},
            {"GND": [("D1", "1")], "+5V": [("D1", "2")],
             "SIGNAL": [("D1", "3")]},
        )
        diodes = [line.split()[1:3] for line in deck.lines
                  if line.startswith(("D1_D1_lo ", "D1_D1_hi "))]
        self.assertEqual(diodes, [["0", deck.n("SIGNAL")],
                                  [deck.n("SIGNAL"), deck.n("+5V")]])
        self.assertEqual(deck.model_classes["D1"],
                         "dual-series-schottky-clamp")
        self.assertFalse(deck.coverage_gaps)

    def test_nonzero_ngspice_exit_is_not_parsed_as_success(self):
        deck = spice.Deck()
        deck.add("* failing deck")
        failed = SimpleNamespace(returncode=1, stdout="", stderr="bad deck")
        with mock.patch.object(spice.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "ngspice exited 1: bad deck"):
                spice.run_deck(deck, [])

    def test_batch_run_uses_repository_spinit_environment(self):
        deck = spice.Deck()
        proc = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(spice.subprocess, "run", return_value=proc) as run:
            spice.run_deck(deck, [])
        env = run.call_args.kwargs["env"]
        self.assertTrue(os.path.isfile(os.path.join(env["SPICE_SCRIPTS"], "spinit")))

    def test_empty_ngspice_output_is_not_parsed_as_success(self):
        deck = spice.Deck()
        deck.add("Vsrc0 n 0 1")
        empty = SimpleNamespace(returncode=0, stdout="noise", stderr="")
        with mock.patch.object(spice.subprocess, "run", return_value=empty):
            with self.assertRaisesRegex(RuntimeError, "no requested values"):
                spice.run_deck(deck, [])


class TestProjectInput(unittest.TestCase):
    def test_project_root_wins_over_shorter_leaf_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "whole-board.kicad_sch")
            leaf = os.path.join(directory, "a.kicad_sch")
            project = os.path.join(directory, "whole-board.kicad_pro")
            for path in (root, leaf, project):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("(kicad_sch)\n")
            self.assertEqual(spice.cec_toolchain.find_root_sch(directory), root)

    def test_netlist_export_failure_is_not_parsed(self):
        failed = SimpleNamespace(returncode=2, stdout="", stderr="bad schematic")
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "board.kicad_sch")
            project = os.path.join(directory, "board.kicad_pro")
            for path in (root, project):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("(kicad_sch)\n")
            with mock.patch.object(spice.cec_toolchain, "require_kicad_cli",
                                   return_value="kicad-cli"), \
                    mock.patch.object(spice.subprocess, "run", return_value=failed):
                with self.assertRaisesRegex(RuntimeError, "exited 2"):
                    spice._project_netlist(directory)

    def test_empty_root_rail_set_is_not_success(self):
        with mock.patch.object(spice, "_project_netlist",
                               return_value=("root.kicad_sch", {}, {"GND": []})):
            with self.assertRaisesRegex(RuntimeError, "no recognized source rails"):
                spice.sanity("board")

    def test_coverage_summary_never_claims_functional_signoff(self):
        deck = spice.Deck()
        deck.gap("Q1", "not modeled")
        report = spice._coverage_summary(deck, [])
        self.assertFalse(report["signoff_ready"])
        self.assertFalse(report["functional_signoff_ready"])


if __name__ == "__main__":
    unittest.main()
