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

    def test_full_pipeline_compile_pads_in_bounds(self):
        # the END-TO-END regression: a full wave-config compile (PlacementSession
        # with the board's real _board_params -- pins, roles, tucks, movers, the
        # lot) must materialize with every pad on the board, per the
        # _oracle_pads_in_bounds gate itself. (A raw seed_anchors probe without
        # the wave config packs edges the pipeline never packs and trips the
        # roadmap-known place_edge overflow on synthetic sets -- reproduced
        # 2026-07-23, FOLLOWUPS'd with the J_SIG1/J_KVM instances; that lever is
        # gate-guarded per variant, not re-tested here.)
        import tempfile
        import cec_fresh_wave as w
        for board, (W, H) in (("atx-24pin-rev3", (74.0, 55.0)),
                              ("hub-standard-rev2", (88.0, 70.0))):
            # canonical constructor (2026-07-23 fix): raw
            # PlacementSession(params=...) does NOT thread anchor_pins into
            # pins= (the documented protocol gotcha) -- U1 ran UNPINNED here,
            # hit the v4 no-legal-seat condition and edge-parked; the test was
            # green only by pass-dynamics luck until the legalizer edge inset
            # perturbed it. _build_session is what the pipeline actually runs.
            s, _p = w._build_session(board, W, H, "plain", "dataflow", 97)
            c = s.compile()
            out = os.path.join(tempfile.gettempdir(),
                               f"edge_seat_rot_{board}.kicad_pcb")
            csp.materialize(c, s.cfg, out)
            r = csp._oracle_pads_in_bounds(out)
            self.assertTrue(r.get("ok"),
                            f"{board}: {r.get('violations')}")


if __name__ == "__main__":
    unittest.main()
