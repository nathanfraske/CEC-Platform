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

    def test_windows_never_falls_back_to_gui_binary(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(spice.os, "name", "nt"), \
                mock.patch.object(spice.shutil, "which", return_value=None):
            self.assertEqual(spice._ngspice_executable(), "ngspice_con.exe")


class TestDeckGeneration(unittest.TestCase):
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

    def test_nonzero_ngspice_exit_is_not_parsed_as_success(self):
        deck = spice.Deck()
        deck.add("* failing deck")
        failed = SimpleNamespace(returncode=1, stdout="", stderr="bad deck")
        with mock.patch.object(spice.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "ngspice exited 1: bad deck"):
                spice.run_deck(deck, [])

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


if __name__ == "__main__":
    unittest.main()
