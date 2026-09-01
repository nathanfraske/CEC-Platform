import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "cec_sync_pcb_from_schematic.py")


def _carve(text, start):
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise ValueError("unterminated PCB expression")


class TestSyncPcbFromSchematic(unittest.TestCase):
    def test_replace_mismatched_footprint_preserves_placement_and_nets(self):
        schematic = os.path.join(
            ROOT, "beta", "pcie-8pin-2port",
            "pcie8pin-2port-module.kicad_sch")
        source = os.path.join(
            ROOT, "beta", "pcie-8pin-2port", "candidate",
            "pcie-8pin-2port-candidate.kicad_pcb")
        with tempfile.TemporaryDirectory() as directory:
            board_path = os.path.join(directory, "candidate.kicad_pcb")
            board = pcbnew.LoadBoard(source)
            cap = board.FindFootprintByReference("C6")
            before = cap.GetPosition()
            cap.SetFPID(pcbnew.LIB_ID(
                "cec-Capacitor_SMD", "C_0603_1608Metric"))
            for item in list(board.GetTracks()):
                board.Remove(item)
            zone_count = len(list(board.Zones()))
            self.assertGreater(zone_count, 0)
            pcbnew.SaveBoard(board_path, board)

            proc = subprocess.run(
                [sys.executable, SCRIPT, "--schematic", schematic,
                 "--pcb", board_path,
                 "--replace-mismatched-footprints", "--add-missing"],
                text=True, capture_output=True, check=False)

            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            report = {}
            for line in proc.stdout.splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                report[key] = ast.literal_eval(value)
            self.assertEqual(report["zones_refilled"], zone_count)
            synced = pcbnew.LoadBoard(board_path)
            replaced = synced.FindFootprintByReference("C6")
            self.assertEqual(
                replaced.GetFPID().GetUniStringLibId(),
                "cec-Capacitor_SMD:C_0805_2012Metric")
            self.assertEqual(replaced.GetPosition(), before)
            self.assertEqual(
                {pad.GetNetname() for pad in replaced.Pads()},
                {"+5VSB", "GND"})

    def test_add_missing_materializes_connected_nonoverlapping_footprints(self):
        schematic = os.path.join(
            ROOT, "beta", "pcie-8pin-3port",
            "pcie8pin-3port-module.kicad_sch")
        source = os.path.join(
            ROOT, "beta", "pcie-8pin-3port", "candidate",
            "pcie-8pin-3port-candidate.kicad_pcb")
        with tempfile.TemporaryDirectory() as directory:
            board_path = os.path.join(directory, "candidate.kicad_pcb")
            shutil.copy2(source, board_path)
            proc = subprocess.run(
                [sys.executable, SCRIPT, "--schematic", schematic,
                 "--pcb", board_path, "--remove-ref", "C45",
                 "--remove-ref", "R19", "--add-missing"],
                text=True, capture_output=True, check=False)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            report = {}
            for line in proc.stdout.splitlines():
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                report[key] = ast.literal_eval(value)
            self.assertEqual(report["missing_schematic_refs"], [])
            self.assertIn("C45", report["added_refs"])
            self.assertIn("R19", report["added_refs"])

            with open(board_path, encoding="utf-8") as handle:
                board_text = handle.read()
            positions = []
            for ref in report["added_refs"]:
                position = report["added_placements_mm"][ref]
                self.assertGreater(position[0], 0.0)
                self.assertGreater(position[1], 0.0)
                positions.append(position[:2])
                blocks = [
                    _carve(board_text, match.start())
                    for match in re.finditer(r"\(footprint\b", board_text)
                ]
                block = next(
                    item for item in blocks
                    if f'(property "Reference" "{ref}"' in item)
                self.assertIn("(net ", block)
            self.assertEqual(len(positions), len(set(positions)))


if __name__ == "__main__":
    unittest.main()
