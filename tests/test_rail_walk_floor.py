#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Rail-walk pitch-floor teeth (seg4 forensic, 2026-07-23): the walk's
# infeasibility guard degraded min_sep to a hardcoded 8.0 "physical width"
# while the stamped sense cell actually reaches 6.75mm right of its anchor and
# the neighbor shunt reaches 1.98mm left -- pitch 8.0 seated every cell 0.27mm
# INTO the next column's shunt (the U12|RS2 / RS4|U11 / RS1|U13 refusal class),
# and a final _lb clamp AFTER the separation enforce could compress a pitch to
# 5.38 (INA pads touching the shunt).  Two teeth:
#   1. FLOOR DERIVATION (container): recompute the true cell need from the
#      committed blueprint + pad-truth courtyards; CELL_PITCH_FLOOR must cover
#      it. A template edit that grows the cell fails here, forcing re-derive.
#   2. END-TO-END (container): a production-path compile of the seg4-refused
#      seed must come out with every shunt pitch >= the floor and ZERO
#      INA-vs-shunt / mount-vs-anything courtyard refusals.
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

try:
    import cec_synth_pipeline as csp                        # noqa: E402
    import cec_pcb                                          # noqa: E402
    HAVE = True
except Exception:                                           # noqa: BLE001
    HAVE = False

if not HAVE:
    raise unittest.SkipTest("cec_synth_pipeline deps unavailable (container test)")

BP = os.path.join(ROOT, "beta", "atx-24pin-rev3", "blueprints",
                  "sense-rail-v0-taps.json")


class TestFloorDerivation(unittest.TestCase):
    def test_constant_covers_blueprint_reach(self):
        """Recompute the cell's board-frame rightward reach from the committed
        blueprint (parts dict: ref -> offset_mm/rot_delta/footprint; stamped at
        the p4b anchor seat rot 270) + pad-truth courtyards. The measured
        stamped extents (2026-07-23, plain-compact-s175): reach +6.75 / shunt
        left half 1.98 -> need 8.98. The test cross-checks its own rotation
        math against those measurements, then pins CELL_PITCH_FLOOR >= need."""
        t = json.load(open(BP))
        parts = t["parts"]
        self.assertIn("RS2", parts, "anchor RS2 missing from blueprint parts")
        STAMP_ROT = 270.0
        reach_right = -1e9
        shunt_left_half = None
        for ref, p in parts.items():
            fp = p.get("footprint")
            if not fp:
                continue
            dx, dy = (p.get("offset_mm") or (0.0, 0.0))[:2]
            gdx, gdy = cec_pcb._rot(dx, dy, STAMP_ROT)
            rot = (STAMP_ROT + float(p.get("rot_delta", 0.0))) % 360.0
            x0, x1, _y0, _y1 = cec_pcb.courtyard_bbox(fp, gdx, gdy, rot)
            reach_right = max(reach_right, x1)
            if ref == "RS2":
                shunt_left_half = -x0
        self.assertIsNotNone(shunt_left_half)
        # calibration guard: the derivation must reproduce the measured stamped
        # geometry (else the rotation/frame math in THIS TEST drifted)
        self.assertAlmostEqual(reach_right, 6.75, delta=0.3,
                               msg="derived cell reach disagrees with the "
                                   "measured stamped board -- test frame math")
        self.assertAlmostEqual(shunt_left_half, 1.98, delta=0.25)
        need = reach_right + shunt_left_half + 0.25          # + courtyard clearance
        self.assertGreaterEqual(
            csp.CELL_PITCH_FLOOR + 0.05, need,
            f"CELL_PITCH_FLOOR {csp.CELL_PITCH_FLOOR} no longer covers the "
            f"blueprint's measured need {need:.2f} (cell reach {reach_right:.2f} "
            f"+ shunt half {shunt_left_half:.2f} + 0.25) -- re-derive the floor")


class TestEndToEndPitch(unittest.TestCase):
    def test_seg4_seed_pitches_and_refusal_classes(self):
        import tempfile
        import pcbnew
        import cec_fresh_wave as w
        board = "atx-24pin-rev3"
        W, H = w.BOARD_WH[board]
        s, _p = w._build_session(board, W, H, "plain", "compact", 175)
        c = s.compile()
        out = os.path.join(tempfile.gettempdir(), "walk_floor_s175.kicad_pcb")
        csp.materialize(c, s.cfg, out)
        b = pcbnew.LoadBoard(out)
        xs = sorted(f.GetPosition().x / 1e6 for f in b.GetFootprints()
                    if f.GetReference() in ("RS1", "RS2", "RS3", "RS4"))
        self.assertEqual(len(xs), 4, "shunt row incomplete")
        for a2, b2 in zip(xs, xs[1:]):
            self.assertGreaterEqual(
                b2 - a2, csp.CELL_PITCH_FLOOR - 0.05,
                f"walk pitch {b2 - a2:.2f} below the cell floor "
                f"{csp.CELL_PITCH_FLOOR} -- the crush class is back")
        cy = csp._oracle_courtyard_overlaps(out)
        fixed_classes = [v for v in (cy.get("violations") or [])
                         if ("RS" in v and any(u in v for u in
                                               ("U10", "U11", "U12", "U13")))
                         or "H1" in v]
        self.assertFalse(fixed_classes,
                         f"fixed refusal classes re-appeared: {fixed_classes}")


if __name__ == "__main__":
    unittest.main()
