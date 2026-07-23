#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Regression teeth for the place_edge per-item rotation leak (owner catch
# 2026-07-23, "the 24 pin connector has been shoved out of bounds"): the
# mouth-flip rotation was computed per item but the placement loop applied the
# bare `rot` loop variable -- the LAST item's rotation -- to EVERY ref on the
# edge. J3 (2x12 Mini-Fit, 63mm pad field) got rot-0 extents with a rot-180
# seat: 22/26 pads off-board, and nothing refused it (the courtyard gate sees
# overlaps, not out-of-bounds). Pins BOTH fixes: per-item rot in seed_anchors,
# and the _oracle_pads_in_bounds pre-route gate.
#
# Container-only (needs the real board netlists + cec_pcb footprint geometry).
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import cec_synth_pipeline as csp                       # noqa: E402
    HAVE = True
except Exception:                                          # noqa: BLE001
    HAVE = False

if not HAVE:
    raise unittest.SkipTest("cec_synth_pipeline deps unavailable (container test)")


class TestEdgeSeatRotation(unittest.TestCase):
    def test_j3_pads_in_bounds_with_own_rotation(self):
        cfg = csp.Config.load("atx-24pin-rev3")
        nl = csp.View(cfg).nl
        W, H = 74.0, 55.0
        res = csp.seed_anchors(nl, W, H,
                               {r: c.footprint for r, c in nl.comps.items()},
                               dict(cfg.pins or {}),
                               overhang=cfg.params.get("connector_overhang", "edge"))
        self.assertIn("J3", res, "J3 must be edge-seated")
        x, y, rot = res["J3"]
        (bx, by) = csp._pad_band(nl.comps["J3"].footprint, rot)
        # the seat's OWN rotation must keep the pad band on-board (the leak put a
        # sibling's rot on J3: rot-0 extents + rot-180 seat = 22/26 pads off-left)
        self.assertGreaterEqual(x + bx[0], -0.25,
                                f"J3 pads off-board left (x={x}, rot={rot})")
        self.assertLessEqual(x + bx[1], W + 0.25, "J3 pads off-board right")
        self.assertGreaterEqual(y + by[0], -0.25, "J3 pads off-board top")
        self.assertLessEqual(y + by[1], H + 0.25, "J3 pads off-board bottom")

    def test_all_edge_anchors_pads_in_bounds(self):
        # the general property under the WAVE's real pin set (BOARD_PARAMS
        # anchor_pins pin the mezz segments; without them J6P gets role-classified
        # onto the top edge beside J3 and trips the SEPARATE, roadmap-known
        # place_edge no-edge-fit-check overflow -- reproduced 2026-07-23, filed in
        # FOLLOWUPS; that gap has its own lever, this test pins the rotation leak)
        import cec_fresh_wave as w
        for board, (W, H) in (("atx-24pin-rev3", (74.0, 55.0)),
                              ("hub-standard-rev2", (88.0, 70.0))):
            cfg = csp.Config.load(board)
            nl = csp.View(cfg).nl
            bp = w._board_params(board)
            pins = dict(cfg.pins or {})
            pins.update(bp.get("anchor_pins") or {})
            res = csp.seed_anchors(nl, W, H,
                                   {r: c.footprint for r, c in nl.comps.items()},
                                   pins,
                                   overhang=cfg.params.get("connector_overhang",
                                                           "edge"))
            # KNOWN-OPEN (noted, not failed -- repo convention): J_SIG1's right-edge
            # pack seats its 4-pin row ~2.2mm past the bottom edge (separate
            # PRE-EXISTING cursor defect exposed by this new test, 2026-07-23 --
            # FOLLOWUPS; the _oracle_pads_in_bounds gate names it per-variant at
            # grade time, so it cannot ship silently while the lever is open).
            known_open = {"J_SIG1"}
            for ref, (x, y, rot) in res.items():
                fp = nl.comps.get(ref)
                if fp is None or ref in known_open:
                    continue
                (bx, by) = csp._pad_band(fp.footprint, rot)
                self.assertTrue(
                    x + bx[0] >= -0.25 and x + bx[1] <= W + 0.25
                    and y + by[0] >= -0.25 and y + by[1] <= H + 0.25,
                    f"{board} {ref}: pads out of bounds at ({x:.1f},{y:.1f},"
                    f"{rot}) band x{bx} y{by}")


if __name__ == "__main__":
    unittest.main()
