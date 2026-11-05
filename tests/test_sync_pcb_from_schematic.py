import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import pcbnew
import cec_swig_guard
cec_swig_guard.pin()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "scripts", "cec_sync_pcb_from_schematic.py")


def test_copper_replacement_preserves_native_rule_areas(tmp_path,monkeypatch):
    import cec_sync_pcb_from_schematic as sync
    from cec_assembly_envelope import vent_reservations
    from shapely.geometry import Point,mapping
    board=pcbnew.BOARD()
    vents=[dict(ref='RESERVOIR',xy=mapping(Point(8,9).buffer(3)))]
    vent_reservations(board,vents,install=True)
    guard=next(iter(board.Zones()));guard_id=guard.m_Uuid.AsString()
    pour=pcbnew.ZONE(board);pour.SetLayer(pcbnew.F_Cu)
    pour.Outline().NewOutline()
    for xy in [(20,20),(30,20),(30,30),(20,30)]:
        pour.Outline().Append(round(xy[0]*1e6),round(xy[1]*1e6))
    board.Add(pour)
    track=pcbnew.PCB_TRACK(board);track.SetStart(pcbnew.VECTOR2I_MM(21,21))
    track.SetEnd(pcbnew.VECTOR2I_MM(25,25));board.Add(track)
    path=tmp_path/'seed.kicad_pcb';pcbnew.SaveBoard(str(path),board)
    monkeypatch.setattr(sync,'_schematic_pad_nets',lambda path:({},set()))
    monkeypatch.setattr(sync.cec_sch_gates,'inventory',lambda path:{})
    result=sync.synchronize('synthetic',str(path),rip_all_copper=True)
    after=pcbnew.LoadBoard(str(path))
    assert result['zones_before']==2 and result['zones_after']==1
    assert result['preserved_rule_areas']==1
    assert not list(after.GetTracks())
    assert [z.m_Uuid.AsString() for z in after.Zones()]==[guard_id]
    assert vent_reservations(after,vents)[0]['ok']


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
            fields = {field.GetName(): field.GetText()
                      for field in replaced.GetFields()}
            self.assertEqual(fields["MPN"], "CL21A106KAYNNNE")
            self.assertEqual(fields["LCSC"], "C15850")
            self.assertIn("samsungsem.com", fields["Datasheet"])

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
                self.assertIn('(path "/', block)
            self.assertEqual(len(positions), len(set(positions)))


if __name__ == "__main__":
    unittest.main()
