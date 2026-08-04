#!/usr/bin/env python3
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from cec_fr import plane_tht_exclusion_nets  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
