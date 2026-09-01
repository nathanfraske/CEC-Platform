import os
import sys
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

try:
    import pcbnew
    import cec_ground_plane as ground_plane
    HAVE_PCBNEW = True
except ImportError:
    HAVE_PCBNEW = False


@unittest.skipUnless(HAVE_PCBNEW, "pcbnew required")
class GroundPlaneTests(unittest.TestCase):
    def _board(self, *, include_in4=True):
        board = pcbnew.BOARD()
        board.SetCopperLayerCount(6)
        properties = board.GetProperties()
        properties["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(properties)
        gnd = pcbnew.NETINFO_ITEM(board, "GND")
        board.Add(gnd)
        board.GetDesignSettings().m_MinThroughDrill = pcbnew.FromMM(0.20)

        for start, end in (
                ((0, 0), (20, 0)), ((20, 0), (20, 20)),
                ((20, 20), (0, 20)), ((0, 20), (0, 0))):
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetStart(pcbnew.VECTOR2I_MM(*start))
            edge.SetEnd(pcbnew.VECTOR2I_MM(*end))
            edge.SetLayer(pcbnew.Edge_Cuts)
            board.Add(edge)

        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
        via.SetDrill(pcbnew.FromMM(0.25))
        via.SetWidth(pcbnew.FromMM(0.50))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNet(gnd)
        via.SetLocked(True)
        board.Add(via)

        anchor = pcbnew.FOOTPRINT(board)
        anchor.SetReference("H1")
        pad = pcbnew.PAD(anchor)
        pad.SetPadName("1")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(pcbnew.VECTOR2I_MM(1.2, 1.2))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(0.6, 0.6))
        pad.SetLayerSet(pcbnew.PAD.PTHMask())
        pad.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
        pad.SetNet(gnd)
        anchor.Add(pad)
        board.Add(anchor)

        zone = pcbnew.ZONE(board)
        layers = pcbnew.LSET()
        layers.AddLayer(board.GetLayerID("In1.Cu"))
        if include_in4:
            layers.AddLayer(board.GetLayerID("In4.Cu"))
        zone.SetLayerSet(layers)
        zone.SetNet(gnd)
        zone.SetZoneName("GND Plane")
        zone.SetAssignedPriority(0)
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in ((0.5, 0.5), (19.5, 0.5),
                     (19.5, 19.5), (0.5, 19.5)):
            outline.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
        board.Add(zone)
        return board, via.m_Uuid.AsString()

    def test_fill_connects_priority_via_on_both_declared_planes(self):
        board, via_uuid = self._board()
        report = ground_plane.fill_board(
            board, required_via_uuids=(via_uuid,))
        self.assertTrue(report["ok"], report["reasons"])
        self.assertEqual(report["required_via_count"], 1)
        self.assertEqual(report["connected_via_count"], 1)
        self.assertEqual(
            {row["layer"] for row in report["ground_layers"]},
            {"In1.Cu", "In4.Cu"})
        self.assertTrue(all(
            row["filled_components"] == 1
            and row["coverage_ratio"] >= 0.50
            for row in report["ground_layers"]))
        self.assertEqual(
            {row["layer"] for row in report["vias"][0]["layers"]
             if row["connected"]},
            {"In1.Cu", "In4.Cu"})
        self.assertTrue(report["zone_declarations_unchanged"])
        self.assertTrue(report["routed_copper_unchanged"])

    def test_audit_missing_profile_ground_layer_fails_closed(self):
        board, via_uuid = self._board(include_in4=False)
        report = ground_plane.audit_board(
            board, required_via_uuids=(via_uuid,))
        self.assertFalse(report["ok"])
        self.assertTrue(any("In4.Cu has no GND zone" in reason
                            for reason in report["reasons"]))

    def test_fill_derives_missing_profile_plane_from_exact_outline(self):
        board, via_uuid = self._board(include_in4=False)
        report = ground_plane.fill_board(
            board, required_via_uuids=(via_uuid,))
        self.assertTrue(report["ok"], report)
        self.assertEqual(
            [row["layer"] for row in report["declaration"]["added"]],
            ["In4.Cu"])
        self.assertEqual(report["connected_via_count"], 1)
        self.assertEqual(
            {row["layer"] for row in report["ground_layers"]},
            {"In1.Cu", "In4.Cu"})
        self.assertTrue(report["zone_declarations_unchanged"])
        self.assertTrue(report["routed_copper_unchanged"])

    def test_declaration_is_idempotent(self):
        board, _via_uuid = self._board(include_in4=False)
        first = ground_plane.declare_profile_ground_planes(board)
        second = ground_plane.declare_profile_ground_planes(board)
        self.assertEqual([row["layer"] for row in first["added"]],
                         ["In4.Cu"])
        self.assertEqual(second["added"], [])
        self.assertEqual(
            {row["layer"] for row in second["existing"]},
            {"In1.Cu", "In4.Cu"})

    def test_missing_required_via_identity_fails_closed(self):
        board, _via_uuid = self._board()
        report = ground_plane.fill_board(
            board, required_via_uuids=("not-a-real-via",))
        self.assertFalse(report["ok"])
        self.assertTrue(any("is missing" in reason
                            for reason in report["reasons"]))

    def test_legacy_ground_report_preserves_exact_via_identity(self):
        report = {"cells": [{
            "owner_ground_return": {"via_uuid": "via-a"},
            "ground_return": {"via_uuid": "via-b"},
        }, {
            "owner_ground_return": {"via_uuid": "via-a"},
            "ground_return": {"status": "refused"},
        }]}
        self.assertEqual(
            ground_plane.required_vias_from_ground_report(report),
            ("via-a", "via-b"))

    def test_transaction_removes_reserved_via_dangling_without_regression(self):
        board, via_uuid = self._board()
        with tempfile.TemporaryDirectory() as temp:
            source = os.path.join(temp, "source.kicad_pcb")
            destination = os.path.join(temp, "filled.kicad_pcb")
            pcbnew.SaveBoard(source, board)
            report = ground_plane.fill_and_admit(
                source, destination, required_via_uuids=(via_uuid,))
        self.assertTrue(report["ok"], report)
        self.assertFalse(report["rolled_back"])
        self.assertGreaterEqual(
            report["before"]["drc_types"].get("via_dangling", 0), 1)
        self.assertEqual(
            report["after"]["drc_types"].get("via_dangling", 0), 0)
        self.assertEqual(report["drc_regression"], {})


if __name__ == "__main__":
    unittest.main()
