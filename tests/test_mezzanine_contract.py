#!/usr/bin/env python3
"""Physical and electrical teeth for the segmented Hub/24-pin mezzanine."""

import os
import tempfile
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew  # noqa: E402
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest("KiCad pcbnew required") from exc

import cec_constraints as C  # noqa: E402
import cec_swig_guard
cec_swig_guard.pin()
_NATIVE_KEEPALIVE = []
import cec_sync_pcb_from_schematic as SYNC  # noqa: E402
import cec_synth_pipeline as SP  # noqa: E402
from cec_fresh_wave import MEZZ_HUB_24PIN  # noqa: E402


ATX = os.path.join(ROOT, "beta", "atx-24pin-rev3", "candidate",
                   "atx-24pin-rev3-candidate.kicad_pcb")
HUB = os.path.join(ROOT, "beta", "hub-standard-rev2", "candidate",
                   "hub-standard-rev2-candidate.kicad_pcb")
HUB_SCHEMATIC = os.path.join(ROOT, "beta", "hub-standard-rev2",
                             "hub-standard-rev2.kicad_sch")


class MezzanineContractTest(unittest.TestCase):
    def corrected_board(self, path):
        """Rebind native fixture to the current contact/seat contract in memory.

        Immutable legacy candidates are deliberately kept as failing regression
        evidence; never edit those old boards to make a test appear green.
        """
        import cec_mezz_contract as mezz
        from cec_fresh_wave import mating_frame_pins
        board=pcbnew.LoadBoard(path)
        hub=path==HUB
        role='hub-standard-rev2' if hub else 'atx-24pin-rev3'
        W,H=mezz.SIDES['socket' if hub else 'header']['nominal_outline']
        poses=mating_frame_pins(W,H,MEZZ_HUB_24PIN,role)
        by={f.GetReference():f for f in board.GetFootprints()}
        for ref,(x,y,angle) in poses['anchor_pins'].items():
            fp=by[ref]
            if hub:
                replacement=pcbnew.FootprintLoad(os.path.join(ROOT,'lib/vendor/Connector_PinSocket_2.54mm.pretty'),fp.GetFPID().GetLibItemName())
                replacement.SetReference(ref);replacement.SetValue(fp.GetValue());replacement.SetFPID(fp.GetFPID())
                nets={p.GetNumber():p.GetNet() for p in fp.Pads()}
                for p in replacement.Pads():p.SetNet(nets[p.GetNumber()])
                _NATIVE_KEEPALIVE.append(fp)
                board.Remove(fp);board.Add(replacement);fp=replacement
            fp.SetOrientationDegrees(angle);fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y)))
        for ref,(x,y) in poses['mount_pos_override'].items():
            old=by[ref]
            nick,item=mezz.GROUND_LUG['footprint'].split(':')
            lug=pcbnew.FootprintLoad(os.path.join(ROOT,'lib/vendor/MountingHole.pretty'),item)
            lug.SetFPID(pcbnew.LIB_ID(nick,item));lug.SetReference(ref)
            for pad in lug.Pads():pad.SetNet(board.FindNet('GND'))
            lug.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x),pcbnew.FromMM(y)))
            _NATIVE_KEEPALIVE.append(old)
            board.Remove(old);board.Add(lug)
        return board

    def test_legacy_hub_candidate_cannot_pass_on_origins_only(self):
        board = pcbnew.LoadBoard(HUB)
        ok, detail = C._chk_mezzanine_segment_contract(board, HUB, {})
        self.assertFalse(ok, detail)
        self.assertIn('physical contact registration failed',detail)

    def test_corrected_hub_contact_field_and_ground_lug_pass(self):
        board=self.corrected_board(HUB)
        ok,detail=C._chk_mezzanine_segment_contract(board,HUB,{})
        self.assertTrue(ok,detail)

    def test_correct_xy_on_wrong_component_face_fails(self):
        board=self.corrected_board(HUB)
        fp=next(f for f in board.GetFootprints() if f.GetReference()=='J6P')
        fp.SetLayer(pcbnew.B_Cu)
        ok,detail=C._chk_mezzanine_segment_contract(board,HUB,{})
        self.assertFalse(ok)
        self.assertIn('component face',detail)

    def test_correct_origin_and_angle_but_bad_pad_fails(self):
        board=self.corrected_board(HUB)
        fp=next(f for f in board.GetFootprints() if f.GetReference()=='J6P')
        pad=next(p for p in fp.Pads() if p.GetNumber()=='3')
        p=pad.GetPosition();pad.SetPosition(pcbnew.VECTOR2I(p.x+pcbnew.FromMM(.2),p.y))
        ok,detail=C._chk_mezzanine_segment_contract(board,HUB,{})
        self.assertFalse(ok)
        self.assertIn('physical contact registration failed',detail)

    def test_atx_candidate_matches_segment_and_ground_lug_contract(self):
        board = self.corrected_board(ATX)
        ok, detail = C._chk_mezzanine_segment_contract(board, ATX, {})
        self.assertTrue(ok, detail)

    def test_mating_datum_does_not_follow_a_resized_laminate_edge(self):
        board = self.corrected_board(HUB)
        bounds = board.GetBoardEdgesBoundingBox()
        max_x = bounds.GetRight()
        max_y = bounds.GetBottom()
        grow = pcbnew.FromMM(6.0)
        for drawing in board.GetDrawings():
            if drawing.GetLayer() != pcbnew.Edge_Cuts:
                continue
            start = drawing.GetStart()
            end = drawing.GetEnd()
            drawing.SetStart(pcbnew.VECTOR2I(
                start.x + (grow if start.x == max_x else 0),
                start.y + (grow if start.y == max_y else 0)))
            drawing.SetEnd(pcbnew.VECTOR2I(
                end.x + (grow if end.x == max_x else 0),
                end.y + (grow if end.y == max_y else 0)))
        ok, detail = C._chk_mezzanine_segment_contract(
            board, "resized-hub.kicad_pcb", {})
        self.assertTrue(ok, detail)

    def test_both_candidate_lugs_are_plated_gnd(self):
        self.assertEqual(MEZZ_HUB_24PIN["mount_net"], "GND")
        self.assertEqual(MEZZ_HUB_24PIN["mount_function"],
                         "inter-board-ground-lug")
        self.assertEqual(MEZZ_HUB_24PIN["mount_electrical_role"],
                         "supplemental-ground-bond")
        self.assertEqual(MEZZ_HUB_24PIN["mount_population"], "fit")
        self.assertEqual(MEZZ_HUB_24PIN["mount_contact"],
                         "conductive-fastener-on-exposed-copper")
        for path in (ATX, HUB):
            board = pcbnew.LoadBoard(path)
            lug = next(fp for fp in board.GetFootprints()
                       if fp.GetReference() == "H1")
            pads = list(lug.Pads())
            self.assertTrue(pads, path)
            self.assertTrue(all(p.GetNetname() == "GND" for p in pads), path)
            self.assertTrue(all(p.GetDrillSize().x > 0 for p in pads), path)

    def test_datum_does_not_follow_outline_origin(self):
        board=self.corrected_board(HUB)
        for edge in board.GetDrawings():
            if edge.GetLayer()==pcbnew.Edge_Cuts:
                edge.Move(pcbnew.VECTOR2I_MM(1.3,1.2))
        ok,detail=C._chk_mezzanine_segment_contract(board,HUB,{})
        self.assertTrue(ok,detail)

    def test_ground_lug_gate_rejects_non_ground_land(self):
        board = self.corrected_board(HUB)
        lug = next(fp for fp in board.GetFootprints()
                   if fp.GetReference() == "H1")
        non_ground = board.FindNet("+5VSB")
        self.assertIsNotNone(non_ground)
        next(iter(lug.Pads())).SetNet(non_ground)
        ok, detail = C._chk_mezzanine_segment_contract(board, HUB, {})
        self.assertFalse(ok)
        self.assertIn("not entirely GND", detail)

    def test_ground_lug_gate_rejects_masked_contact_face(self):
        board = self.corrected_board(HUB)
        lug = next(fp for fp in board.GetFootprints()
                   if fp.GetReference() == "H1")
        pad = max(lug.Pads(), key=lambda p: p.GetDrillSize().x)
        layers = pad.GetLayerSet()
        layers.RemoveLayer(pcbnew.F_Mask)
        pad.SetLayerSet(layers)
        ok, detail = C._chk_mezzanine_segment_contract(board, HUB, {})
        self.assertFalse(ok)
        self.assertIn("not exposed on both outer faces", detail)

    def test_ground_lug_gate_rejects_old_hole_diameter(self):
        board = self.corrected_board(HUB)
        lug = next(fp for fp in board.GetFootprints() if fp.GetReference() == 'H1')
        pad = max(lug.Pads(), key=lambda p: p.GetDrillSize().x)
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(2.7, 2.7))
        ok, detail = C._chk_mezzanine_segment_contract(board, HUB, {})
        self.assertFalse(ok, detail)
        self.assertIn('2.2', detail)

    def test_explicit_ground_lug_override_is_never_droppable(self):
        footprint = "cec-MountingHole:MountingHole_2.2mm_M2_Pad_Via"
        positions = {"H1": (5.0, 5.0, 0.0), "JX": (5.0, 5.0, 0.0)}
        components = {"H1": footprint, "JX": footprint}
        dropped = SP._drop_optional_corner_mount_conflicts(
            positions, components, protected={"H1"})
        self.assertEqual(dropped, ())
        self.assertIn("H1", positions)

    def test_schematic_sync_restores_explicit_board_only_ground_lug(self):
        board = pcbnew.LoadBoard(HUB)
        lug = next(fp for fp in board.GetFootprints()
                   if fp.GetReference() == "H1")
        for pad in lug.Pads():
            pad.SetNetCode(0)
        with tempfile.TemporaryDirectory() as td:
            target = os.path.join(td, "hub.kicad_pcb")
            pcbnew.SaveBoard(target, board)
            report = SYNC.synchronize(
                HUB_SCHEMATIC, target,
                extra_pad_nets={("H1", "1"): "GND"})
            synced = pcbnew.LoadBoard(target)
            synced_lug = next(fp for fp in synced.GetFootprints()
                              if fp.GetReference() == "H1")
            self.assertEqual(report["pads_reassigned"], 9)
            self.assertTrue(all(pad.GetNetname() == "GND"
                                for pad in synced_lug.Pads()))


if __name__ == "__main__":
    unittest.main()
