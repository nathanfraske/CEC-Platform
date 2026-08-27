#!/usr/bin/env python3
"""Regression tests for exact Edge.Cuts dimensional inference."""

import os
import sys
import unittest

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_board_geometry as geometry  # noqa: E402


class BoardGeometryTest(unittest.TestCase):
    def test_centerline_bbox_excludes_edge_cuts_stroke(self):
        board = pcbnew.BOARD()
        corners = ((0, 0), (86, 0), (86, 74), (0, 74), (0, 0))
        for start, end in zip(corners, corners[1:]):
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
            edge.SetLayer(pcbnew.Edge_Cuts)
            edge.SetWidth(pcbnew.FromMM(0.1))
            edge.SetStart(pcbnew.VECTOR2I(
                pcbnew.FromMM(start[0]), pcbnew.FromMM(start[1])))
            edge.SetEnd(pcbnew.VECTOR2I(
                pcbnew.FromMM(end[0]), pcbnew.FromMM(end[1])))
            board.Add(edge)

        painted = board.GetBoardEdgesBoundingBox()
        self.assertAlmostEqual(painted.GetWidth() / 1_000_000.0, 86.1)
        self.assertAlmostEqual(painted.GetHeight() / 1_000_000.0, 74.1)
        self.assertEqual(geometry.outline_bbox_mm(board),
                         (0.0, 0.0, 86.0, 74.0))


if __name__ == "__main__":
    unittest.main()
