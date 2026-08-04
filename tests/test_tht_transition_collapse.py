#!/usr/bin/env python3
"""Regression for redundant through-hole-pad layer-transition dogbones."""
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


class TestPTHTransitionCollapse(unittest.TestCase):
    def setUp(self):
        self.board = pcbnew.CreateEmptyBoard()
        self.net = pcbnew.NETINFO_ITEM(self.board, "/SIG")
        self.board.Add(self.net)

    @staticmethod
    def _pos(x, y):
        return pcbnew.VECTOR2I_MM(x, y)

    def _pad(self, *, pth=True):
        footprint = pcbnew.FOOTPRINT(self.board)
        footprint.SetReference("J1")
        footprint.SetPosition(self._pos(5, 5))
        pad = pcbnew.PAD(footprint)
        pad.SetPadName("1")
        pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        pad.SetSize(self._pos(1.8, 1.8))
        pad.SetPosition(footprint.GetPosition())
        if pth:
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetDrillSize(self._pos(0.9, 0.9))
            pad.SetLayerSet(pcbnew.PAD.PTHMask())
        else:
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask())
        pad.SetNet(self.net)
        footprint.Add(pad)
        self.board.Add(footprint)
        return pad

    def _track(self, start, end, layer):
        track = pcbnew.PCB_TRACK(self.board)
        track.SetStart(self._pos(*start))
        track.SetEnd(self._pos(*end))
        track.SetWidth(pcbnew.FromMM(0.25))
        track.SetLayer(self.board.GetLayerID(layer))
        track.SetNet(self.net)
        self.board.Add(track)
        return track

    def _via(self, x=7, y=5):
        via = pcbnew.PCB_VIA(self.board)
        via.SetPosition(self._pos(x, y))
        via.SetWidth(pcbnew.FromMM(0.6))
        via.SetDrill(pcbnew.FromMM(0.3))
        via.SetLayerPair(self.board.GetLayerID("F.Cu"),
                         self.board.GetLayerID("B.Cu"))
        via.SetNet(self.net)
        self.board.Add(via)
        return via

    def test_pth_barrel_replaces_redundant_via_without_moving_geometry(self):
        self._pad(pth=True)
        stub = self._track((5, 5), (7, 5), "F.Cu")
        continuation = self._track((7, 5), (12, 8), "B.Cu")
        self._via()

        result = cec_fr.collapse_redundant_pth_transitions(self.board)

        self.assertEqual(result["removed"], 1, result)
        self.assertEqual(stub.GetLayer(), continuation.GetLayer())
        self.assertEqual(sum(t.GetClass() == "PCB_VIA"
                             for t in self.board.GetTracks()), 0)
        self.assertEqual((stub.GetStart(), stub.GetEnd()),
                         (self._pos(5, 5), self._pos(7, 5)))

    def test_smd_pad_cannot_waive_the_layer_transition(self):
        self._pad(pth=False)
        self._track((5, 5), (7, 5), "F.Cu")
        self._track((7, 5), (12, 8), "B.Cu")
        self._via()

        result = cec_fr.collapse_redundant_pth_transitions(self.board)

        self.assertEqual(result["removed"], 0, result)
        self.assertEqual(sum(t.GetClass() == "PCB_VIA"
                             for t in self.board.GetTracks()), 1)


if __name__ == "__main__":
    unittest.main()
