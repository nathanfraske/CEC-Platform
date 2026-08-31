#!/usr/bin/env python3
"""General post-route 90-degree corner finishing regressions."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import pcbnew
except ImportError as exc:  # pragma: no cover
    raise unittest.SkipTest("pcbnew required") from exc

import cec_fr  # noqa: E402


class TestRouteCornerChamfer(unittest.TestCase):
    def setUp(self):
        self.board = pcbnew.CreateEmptyBoard()
        self.net = pcbnew.NETINFO_ITEM(self.board, "/SIG")
        self.board.Add(self.net)

    @staticmethod
    def _pos(x, y):
        return pcbnew.VECTOR2I_MM(x, y)

    def _track(self, start, end, *, locked=False):
        track = pcbnew.PCB_TRACK(self.board)
        track.SetStart(self._pos(*start))
        track.SetEnd(self._pos(*end))
        track.SetWidth(pcbnew.FromMM(0.25))
        track.SetLayer(self.board.GetLayerID("F.Cu"))
        track.SetNet(self.net)
        track.SetLocked(locked)
        self.board.Add(track)
        return track

    def _corner(self, *, locked=False):
        a = self._track((5, 10), (10, 10), locked=locked)
        b = self._track((10, 10), (10, 15))
        return a, b

    def test_unlocked_ordinary_corner_receives_clear_45_degree_bend(self):
        first, second = self._corner()
        report = cec_fr.chamfer_unlocked_right_angles(self.board)

        self.assertEqual(report["right_angles"], 1, report)
        self.assertEqual(report["chamfered"], 1, report)
        tracks = [item for item in self.board.GetTracks()
                  if item.GetClass() == "PCB_TRACK"]
        self.assertEqual(len(tracks), 3)
        diagonal = [track for track in tracks
                    if track not in (first, second)][0]
        dx = abs(diagonal.GetEnd().x - diagonal.GetStart().x)
        dy = abs(diagonal.GetEnd().y - diagonal.GetStart().y)
        self.assertEqual(dx, dy)
        self.assertGreater(dx, 0)
        self.assertEqual(diagonal.GetNetCode(), self.net.GetNetCode())
        self.assertEqual(diagonal.GetWidth(), first.GetWidth())

    def test_locked_or_sensitive_corner_is_immutable(self):
        self._corner(locked=True)
        locked = cec_fr.chamfer_unlocked_right_angles(self.board)
        self.assertEqual(locked["chamfered"], 0, locked)
        self.assertEqual(locked["skipped"]["locked"], 1)

        other = pcbnew.CreateEmptyBoard()
        net = pcbnew.NETINFO_ITEM(other, "/PAIR_P")
        other.Add(net)
        for start, end in (((5, 10), (10, 10)),
                           ((10, 10), (10, 15))):
            track = pcbnew.PCB_TRACK(other)
            track.SetStart(self._pos(*start)); track.SetEnd(self._pos(*end))
            track.SetWidth(pcbnew.FromMM(0.25))
            track.SetLayer(other.GetLayerID("F.Cu")); track.SetNet(net)
            other.Add(track)
        sensitive = cec_fr.chamfer_unlocked_right_angles(
            other, exclude_nets={"/PAIR_P"})
        self.assertEqual(sensitive["chamfered"], 0, sensitive)
        self.assertEqual(sensitive["skipped"]["sensitive"], 1)

    def test_locked_generated_corner_requires_exact_uuid_provenance(self):
        first, second = self._corner(locked=True)
        second.SetLocked(True)
        partial = cec_fr.chamfer_unlocked_right_angles(
            self.board,
            allow_locked_track_uuids={first.m_Uuid.AsString()})
        self.assertEqual(partial["chamfered"], 0, partial)

        complete = cec_fr.chamfer_unlocked_right_angles(
            self.board,
            allow_locked_track_uuids={
                first.m_Uuid.AsString(), second.m_Uuid.AsString()})
        self.assertEqual(complete["chamfered"], 1, complete)

    def test_t_junction_is_not_cut(self):
        self._corner()
        self._track((10, 10), (13, 10))
        report = cec_fr.chamfer_unlocked_right_angles(self.board)
        self.assertEqual(report["chamfered"], 0, report)
        self.assertGreaterEqual(report["skipped"]["junction"], 1)

    def test_via_teardrop_is_recommended_and_enabled(self):
        track = self._track((5, 10), (10, 10))
        via = pcbnew.PCB_VIA(self.board)
        via.SetPosition(track.GetEnd())
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetLayerPair(self.board.GetLayerID("F.Cu"),
                         self.board.GetLayerID("B.Cu"))
        via.SetNet(self.net)
        self.board.Add(via)

        audit = cec_fr.audit_teardrop_junctions(self.board)
        self.assertEqual(audit["by_kind"]["via"], 1, audit)
        applied = cec_fr.enable_recommended_teardrops(self.board)
        self.assertEqual(applied["enabled"], 1, applied)
        self.assertTrue(via.GetTeardropsEnabled())

    def test_smd_teardrops_are_opt_in(self):
        track = self._track((5, 10), (10, 10))
        footprint = pcbnew.FOOTPRINT(self.board)
        footprint.SetReference("U1")
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("1")
        pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(self._pos(1.2, 1.2))
        pad.SetPosition(track.GetEnd())
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(self.net)
        footprint.Add(pad); self.board.Add(footprint)

        ordinary = cec_fr.audit_teardrop_junctions(self.board)
        explicit = cec_fr.audit_teardrop_junctions(
            self.board, target_kinds=("smd",))
        self.assertEqual(ordinary["by_kind"]["smd"], 0)
        self.assertEqual(explicit["by_kind"]["smd"], 1)

    def test_conventional_can_pair_is_discovered_without_netclass(self):
        board = pcbnew.CreateEmptyBoard()
        for name in ("/BUS/CAN_H", "/BUS/CAN_L", "/CAN_TX"):
            board.Add(pcbnew.NETINFO_ITEM(board, name))
        self.assertEqual(cec_fr.coupled_pair_nets(board),
                         {"/BUS/CAN_H", "/BUS/CAN_L"})


if __name__ == "__main__":
    unittest.main()
