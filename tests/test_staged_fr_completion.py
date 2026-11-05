import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pcbnew
import cec_fr
import cec_staged_fr


class StagedCompletionTests(unittest.TestCase):
    def test_foreign_pour_admission_is_fail_closed(self):
        with mock.patch(
                "cec_pour_clearance.inspect_file",
                return_value={"applicable": True, "status": "ok",
                              "n_tracks": 2, "n_vias": 1,
                              "by_pour": {"RAIL": {"SIG": 3}},
                              "tracks": [{"uuid": "t"}], "vias": []}):
            report = cec_staged_fr.foreign_pour_admission("candidate")

        self.assertFalse(report["ok"])
        self.assertEqual((report["tracks"], report["vias"]), (2, 1))
        self.assertEqual(report["items"], [{"uuid": "t"}])

    def test_foreign_pour_delta_allows_only_inherited_identity(self):
        inherited = {"kind": "via", "uuid": "v1", "net": "/GPIO0",
                     "pour": "/SENSE", "pour_net": ""}
        report = cec_staged_fr.foreign_pour_delta_admission(
            {"status": "ok", "items": [inherited]},
            {"status": "ok", "items": [dict(inherited)]})
        self.assertTrue(report["ok"])
        self.assertEqual((report["inherited_count"], report["new_count"]),
                         (1, 0))

    def test_foreign_pour_delta_rejects_new_identity(self):
        inherited = {"kind": "via", "uuid": "v1", "net": "/GPIO0",
                     "pour": "/SENSE", "pour_net": ""}
        introduced = {"kind": "track", "uuid": "t2", "net": "/SIG",
                      "pour": "patch:/SENSE", "pour_net": "/SENSE"}
        report = cec_staged_fr.foreign_pour_delta_admission(
            {"status": "ok", "items": [inherited]},
            {"status": "ok", "items": [inherited, introduced]})
        self.assertFalse(report["ok"])
        self.assertEqual(report["new_items"], [introduced])

    def _board(self):
        board = pcbnew.BOARD()
        net_a = pcbnew.NETINFO_ITEM(board, "/A")
        net_b = pcbnew.NETINFO_ITEM(board, "/B")
        board.Add(net_a); board.Add(net_b)
        layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)

        def pad(ref, number, net, x):
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference(ref)
            item = pcbnew.PAD(footprint)
            item.SetNumber(number)
            item.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            item.SetShape(pcbnew.PAD_SHAPE_RECT)
            item.SetSize(pcbnew.VECTOR2I_MM(1, 1))
            item.SetPosition(pcbnew.VECTOR2I_MM(x, 2))
            item.SetLayerSet(layers); item.SetNet(net)
            footprint.Add(item); board.Add(footprint)
            return item

        a1 = pad("A1", "1", net_a, 1)
        a2 = pad("A2", "1", net_a, 5)
        pad("B1", "1", net_b, 1)
        pad("B2", "1", net_b, 5)
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(a1.GetPosition()); track.SetEnd(a2.GetPosition())
        track.SetLayer(pcbnew.F_Cu); track.SetWidth(pcbnew.FromMM(0.2))
        track.SetNet(net_a); board.Add(track)
        return board

    def test_only_electrically_complete_tier_net_is_protectable(self):
        complete, incomplete = cec_staged_fr.fully_connected_nets(
            self._board(), {"/A", "/B"})
        self.assertEqual(complete, {"/A"})
        self.assertEqual(incomplete, {"/B"})

    def test_connectivity_evidence_retains_branch_identity_before_rollback(self):
        evidence = {}
        complete, incomplete = cec_staged_fr.fully_connected_nets(
            self._board(), {"/A", "/B"}, evidence=evidence)
        self.assertEqual(complete, {"/A"})
        self.assertEqual(incomplete, {"/B"})
        self.assertEqual(evidence["/A"]["copper_item_count"], 1)
        self.assertEqual(evidence["/A"]["unreached_pads"], [])
        self.assertEqual(evidence["/B"]["unreached_pads"][0]["ref"], "B2")
        self.assertEqual(evidence["/B"]["unreached_pads"][0]["at_mm"], [5.0, 2.0])

    def test_backend_echo_is_replaced_by_exact_protected_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = str(Path(directory) / "source.kicad_pcb")
            candidate_path = str(Path(directory) / "candidate.kicad_pcb")
            source = self._board()
            protected = next(item for item in source.GetTracks()
                             if item.GetNetname() == "/A")
            protected.SetLocked(True)
            protected_uuid = protected.m_Uuid.AsString()
            rule_group = pcbnew.PCB_GROUP(source)
            rule_group.SetName("CEC_TEST_OBJECT_RULE")
            source.Add(rule_group)
            rule_group.AddItem(protected)
            pcbnew.SaveBoard(source_path, source)

            candidate = pcbnew.LoadBoard(source_path)
            echo = protected.Duplicate()
            echo.SetStart(pcbnew.VECTOR2I_MM(1, 2.2))
            echo.SetEnd(pcbnew.VECTOR2I_MM(5, 2.2))
            candidate.Add(echo)
            tier = pcbnew.PCB_TRACK(candidate)
            tier.SetStart(pcbnew.VECTOR2I_MM(1, 4))
            tier.SetEnd(pcbnew.VECTOR2I_MM(5, 4))
            tier.SetLayer(pcbnew.F_Cu)
            tier.SetWidth(pcbnew.FromMM(0.2))
            tier.SetNet(candidate.FindNet("/B"))
            candidate.Add(tier)
            pcbnew.SaveBoard(candidate_path, candidate)

            report = cec_staged_fr.restore_protected_copper_prefix(
                source_path, candidate_path, {"/A"})
            restored = pcbnew.LoadBoard(candidate_path)

            self.assertEqual((report["removed"], report["restored"]), (2, 1))
            self.assertEqual(
                cec_fr.copper_geometry_signature(
                    source_path, {"/A"})["sha256"],
                cec_fr.copper_geometry_signature(
                    candidate_path, {"/A"})["sha256"])
            self.assertEqual(
                sum(item.GetNetname() == "/B"
                    for item in restored.GetTracks()), 1,
                "tier-owned delta must survive prefix restoration")
            restored_ids = {
                item.m_Uuid.AsString() for item in restored.GetTracks()
                if item.GetNetname() == "/A"}
            self.assertEqual(restored_ids, {protected_uuid},
                             "delta restore must preserve exact ownership IDs")
            restored_group = next(
                group for group in restored.Groups()
                if group.GetName() == "CEC_TEST_OBJECT_RULE")
            restored_protected = next(
                item for item in restored.GetTracks()
                if item.m_Uuid.AsString() == protected_uuid)
            self.assertTrue(restored_group.ContainsItem(restored_protected),
                            "object-scoped rule membership must survive SES")
            self.assertIn("CEC_TEST_OBJECT_RULE", report["restored_groups"])

    def test_incomplete_net_restore_discards_speculative_stub(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = str(Path(directory) / "source.kicad_pcb")
            candidate_path = str(Path(directory) / "candidate.kicad_pcb")
            source = self._board()
            pcbnew.SaveBoard(source_path, source)

            candidate = pcbnew.LoadBoard(source_path)
            stub = pcbnew.PCB_TRACK(candidate)
            stub.SetStart(pcbnew.VECTOR2I_MM(2, 4))
            stub.SetEnd(pcbnew.VECTOR2I_MM(3, 4))
            stub.SetLayer(pcbnew.F_Cu)
            stub.SetWidth(pcbnew.FromMM(0.2))
            stub.SetNet(candidate.FindNet("/B"))
            candidate.Add(stub)
            pcbnew.SaveBoard(candidate_path, candidate)

            before = cec_fr.copper_geometry_signature(
                source_path, {"/B"})
            report = cec_staged_fr.restore_protected_copper_prefix(
                source_path, candidate_path, {"/B"})
            after = cec_fr.copper_geometry_signature(
                candidate_path, {"/B"})

            self.assertEqual(before["sha256"], after["sha256"])
            self.assertEqual((report["removed"], report["restored"]),
                             (1, 0))

    def test_item_restoration_preserves_new_trunk_on_the_same_net(self):
        with tempfile.TemporaryDirectory() as directory:
            source_path = str(Path(directory) / "source.kicad_pcb")
            candidate_path = str(Path(directory) / "candidate.kicad_pcb")
            source = self._board()
            owned = next(iter(source.GetTracks())).m_Uuid.AsString()
            pcbnew.SaveBoard(source_path, source)
            candidate = pcbnew.LoadBoard(source_path)
            from cec_native_items import discard_items
            discard_items(candidate, list(candidate.GetTracks()))
            trunk = pcbnew.PCB_TRACK(candidate)
            trunk.SetStart(pcbnew.VECTOR2I_MM(1, 5))
            trunk.SetEnd(pcbnew.VECTOR2I_MM(5, 5))
            trunk.SetLayer(pcbnew.F_Cu); trunk.SetWidth(pcbnew.FromMM(0.8))
            trunk.SetNet(candidate.FindNet('/A')); candidate.Add(trunk)
            trunk_id = trunk.m_Uuid.AsString()
            pcbnew.SaveBoard(candidate_path, candidate)
            original = Path(source_path).read_bytes()
            report = cec_staged_fr.restore_protected_copper_prefix(
                source_path, candidate_path, (), item_uuids={owned})
            final = pcbnew.LoadBoard(candidate_path)
            self.assertEqual({item.m_Uuid.AsString() for item in final.GetTracks()},
                             {owned, trunk_id})
            self.assertEqual((report['removed'], report['restored']), (0, 1))
            self.assertEqual(original, Path(source_path).read_bytes())
            with self.assertRaisesRegex(RuntimeError, 'absent from source'):
                cec_staged_fr.restore_protected_copper_prefix(
                    source_path, candidate_path, (), item_uuids={'absent'})
            again = cec_staged_fr.restore_protected_copper_prefix(
                source_path, candidate_path, (), item_uuids={owned})
            self.assertEqual((again['removed'], again['restored']), (1, 1))


if __name__ == "__main__":
    unittest.main()
