#!/usr/bin/env python3
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cec_fr import (filled_tht_exclusion_pins,
                    plane_tht_exclusion_nets)  # noqa: E402


class _Box:
    def __init__(self, width, height):
        self.width, self.height = width, height
    def GetWidth(self): return self.width
    def GetHeight(self): return self.height


class _Zone:
    def __init__(self, net, filled_area, *, rule=False):
        self.net, self.filled_area, self.rule = net, filled_area, rule
    def GetIsRuleArea(self): return self.rule
    def GetNetname(self): return self.net
    def GetFilledArea(self): return self.filled_area


class _Board:
    def __init__(self, zones):
        self.zones = zones
    def GetBoardEdgesBoundingBox(self): return _Box(100, 100)
    def Zones(self): return self.zones


class PlaneThtPolicyTest(unittest.TestCase):
    def test_sparse_cross_board_corridor_is_not_a_plane(self):
        board = _Board([_Zone("+5VSB", 900), _Zone("GND", 6000)])

        self.assertEqual(plane_tht_exclusion_nets(board), {"GND"})

    def test_unfilled_and_rule_zones_never_exclude_tht_pins(self):
        board = _Board([_Zone("PWR", 0), _Zone("RULE", 9000, rule=True)])

        self.assertEqual(plane_tht_exclusion_nets(board), set())

    def test_sparse_rail_excludes_only_the_tht_pin_in_real_inner_fill(self):
        try:
            import pcbnew
        except ImportError:
            self.skipTest("pcbnew not available")

        board = pcbnew.BOARD()
        board.SetCopperLayerCount(4)
        net = pcbnew.NETINFO_ITEM(board, "+5VSB")
        board.Add(net)
        footprint = pcbnew.FOOTPRINT(board)
        footprint.SetReference("J1")
        for number, x in (("1", 5.0), ("2", 15.0)):
            pad = pcbnew.PAD(footprint)
            pad.SetNumber(number)
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I(int(1.5e6), int(1.5e6)))
            pad.SetDrillSize(pcbnew.VECTOR2I(int(0.8e6), int(0.8e6)))
            pad.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(5e6)))
            pad.SetLayerSet(pcbnew.PAD.PTHMask())
            pad.SetNet(net)
            footprint.Add(pad)
        board.Add(footprint)
        zone = pcbnew.ZONE(board)
        zone.SetNet(net)
        zone.SetLayer(pcbnew.In1_Cu)
        outline = zone.Outline(); outline.NewOutline()
        for x, y in ((2, 2), (8, 2), (8, 8), (2, 8)):
            outline.Append(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
        board.Add(zone)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())

        self.assertEqual(filled_tht_exclusion_pins(board), {"J1-1": "+5VSB"})


if __name__ == "__main__":
    unittest.main()
