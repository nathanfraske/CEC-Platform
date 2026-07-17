#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# The route-time CORRIDOR KEEPOUT keystone (close-the-loop, the ROUTE half): cec_fr.corridor_keepouts
# reserves each cable's connector->shunt high-current corridor so FR routes foreign signals AROUND the
# pour, NOTCHED at the shunt (the tap window) and block_fills=False so the same-net pour still fills SOLID.

import os
import sys
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

EPS_PCB = os.path.join(ROOT, "tests", "fixtures", "eps-8pin-legacy", "eps8pin-module.kicad_pcb")  # legacy fixture (pre-beta geometry)
HUB_PCB = os.path.join(ROOT, "hubs", "hub-standard", "hub-standard.kicad_pcb")
try:
    import pcbnew                                          # noqa: F401
    HAVE_PCBNEW = True
except Exception:
    HAVE_PCBNEW = False

import cec_fr                                              # noqa: E402


@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(EPS_PCB), "pcbnew + eps board required")
class TestCorridorKeepoutGeometry(unittest.TestCase):
    def test_eps_returns_the_four_cable_corridors(self):
        kos = cec_fr.corridor_keepouts(EPS_PCB)
        names = sorted(k["name"] for k in kos)
        self.assertEqual(names, ["corr_SENSEC1_HI", "corr_SENSEC1_LO",
                                 "corr_SENSEC2_HI", "corr_SENSEC2_LO"])

    def test_keepout_blocks_foreign_tracks_but_not_the_same_net_pour(self):
        # block_fills=False is the load-bearing field: the keepout reserves the corridor against FOREIGN
        # tracks (FR routes around) but must NOT block the same-net power pour from filling it solid.
        for k in cec_fr.corridor_keepouts(EPS_PCB):
            self.assertIs(k["block_fills"], False)
            self.assertTrue(k["allow_vias"])

    def test_clip_at_shunt_keeps_the_tap_window_open(self):
        # each corridor is clipped at the shunt centroid (the "notch"): the HI keepout's bottom edge and
        # the LO keepout's top edge both sit at the shunt, leaving the shunt-inner-edge -> INA tap window.
        import pcbnew
        b = pcbnew.LoadBoard(EPS_PCB)
        npads = {fp.GetReference(): fp.GetPadCount() for fp in b.GetFootprints()}
        shunt_y = {}
        for fp in b.GetFootprints():
            if npads.get(fp.GetReference(), 0) == 2:
                for p in fp.Pads():
                    nn = p.GetNetname()
                    if nn.endswith("_HI") or nn.endswith("_LO"):
                        shunt_y.setdefault(nn, p.GetPosition().y / 1e6)
        for k in cec_fr.corridor_keepouts(EPS_PCB):
            net = "/" + k["name"][len("corr_"):]
            sy = shunt_y.get(net)
            if sy is None:
                continue
            # the keepout is clipped AT the shunt on one edge (within rounding)
            self.assertTrue(abs(k["y0"] - sy) < 0.6 or abs(k["y1"] - sy) < 0.6,
                            f"{k['name']} not clipped at shunt y={sy}: {k['y0']}..{k['y1']}")


@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(HUB_PCB), "pcbnew + hub board required")
class TestCorridorKeepoutSelfGating(unittest.TestCase):
    def test_shared_bus_board_yields_no_corridors(self):
        # the Hub has no cable connector->shunt nets -> []
        self.assertEqual(cec_fr.corridor_keepouts(HUB_PCB), [])


@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(EPS_PCB), "pcbnew + eps board required")
class TestVitalKeepoutDelegation(unittest.TestCase):
    def test_cec_router_wrapper_geometry_matches(self):
        import cec_score
        import cec_router
        rules = cec_score.Rules.from_board(EPS_PCB)
        self.assertEqual(cec_router._vital_keepouts_from_rules(EPS_PCB, rules),
                         cec_fr.corridor_keepouts(EPS_PCB, kelvin_pairs=rules.kelvin_pairs,
                                                  nets_12v=rules.nets_12v))


@unittest.skipUnless(HAVE_PCBNEW and os.path.isfile(EPS_PCB), "pcbnew + ZONE_FILLER required")
class TestBlockFillsPourFill(unittest.TestCase):
    """The block_fills bug: a keepout with DoNotAllowZoneFills blocked ~89% of the same-net power pour.
    block_fills=False (corridor keepouts) lets the pour fill the reserved corridor solid."""

    def _pour_area(self, block_fills):
        import pcbnew
        kos = [dict(k, block_fills=block_fills) for k in cec_fr.corridor_keepouts(EPS_PCB)]
        pours = cec_fr.derive_power_pours(EPS_PCB)
        d = tempfile.mkdtemp()
        out = os.path.join(d, "t.kicad_pcb")
        cec_fr.bake_hints(EPS_PCB, out, keepouts=kos)
        b = pcbnew.LoadBoard(out)
        cec_fr.add_power_pours(b, pours, fill=False)
        for z in b.Zones():
            z.UnFill()
        pcbnew.ZONE_FILLER(b).Fill(b.Zones())
        area = 0.0
        for z in b.Zones():
            nn = z.GetNetname()
            if nn.endswith("_HI") or nn.endswith("_LO"):
                try:
                    area += z.GetFilledPolysList(pcbnew.F_Cu).Area() / 1e12
                except Exception:
                    pass
        del b
        return area

    def test_pour_fills_with_block_fills_false_blocked_with_true(self):
        blocked = self._pour_area(True)      # the old (buggy) behaviour
        filled = self._pour_area(False)      # the corridor-keepout default
        self.assertGreater(filled, blocked * 3,
                           f"block_fills=False must let the pour fill (got filled={filled:.1f} "
                           f"vs blocked={blocked:.1f} mm2)")


if __name__ == "__main__":
    unittest.main()
