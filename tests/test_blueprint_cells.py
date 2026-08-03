# SPDX-License-Identifier: Apache-2.0
"""Teeth for the P4 BLUEPRINT-CELL primitive (docs/pass-form-plan.md §4, stage S3).

The mechanism: cec_cell_extract lifts a placed cell into a relocatable TEMPLATE (relative
placement + internal routing + net ROLES + ports), synthesize_ideal_internal() compiles a
super-tight IDEAL internal route for a cell whose source was never routed (the owner
addition), and stamp(lay=True) writes that internal copper onto a real board as LOCKED
tracks/vias -- GUARD-CHECKED against foreign copper (whole-cell refusal). locked_nets() +
guard_kelvin_double_lay() are the survive-FR / no-double-lay halves that cec_synth_pipeline
wires into route_oracle_grade.

Pure-logic teeth run wherever pcbnew imports (cec_cell_extract imports it at module load);
the board-touching teeth also need the committed eps board. The FR survive-route + the
synth_one->materialize end-to-end are exercised as the S3 in-container teeth (see the commit
message), not here -- a unit test does not route.
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

try:
    import pcbnew  # noqa: F401  -- cec_cell_extract imports it at module load
    import cec_cell_extract as cce
    HAVE = True
except Exception:                       # noqa: BLE001
    HAVE = False

EPS_PCB = os.path.normpath(os.path.join(
    HERE, "..", "old-revisions", "beta", "eps-8pin-pre-rev3",
    "eps8pin-module.kicad_pcb"))


@unittest.skipUnless(HAVE, "pcbnew required (cec_cell_extract imports it)")
class TestIdealInternal(unittest.TestCase):
    """synthesize_ideal_internal: compile a super-tight ideal route for an unrouted internal net."""

    def _tpl(self):
        # a synthetic cell: two SOT parts whose /DETAMPC{n} pads sit on the LEFT column (same x)
        return {
            "parts": {"U20": {"offset_mm": [0.0, 0.0]}, "U30": {"offset_mm": [0.0, 9.25]}},
            "internal_tracks": [],
            "internal_pads": {
                "/DETAMPC{n}": {"net": "/DETAMPC1", "pads": [
                    {"ref": "U20", "pad": "1", "rel_mm": [-1.14, -0.95]},   # left of U20 centre
                    {"ref": "U30", "pad": "3", "rel_mm": [-1.14, 10.2]}]},  # left of U30 centre
                "unc": {"net": "unc", "pads": [{"ref": "U20", "pad": "3", "rel_mm": [1.0, 0.0]}]},
            },
            "net_roles": {"/DETAMPC{n}": "/DETAMPC1", "unc": "unc"},
        }

    def test_escape_route_leaves_the_pad_column(self):
        out = cce.synthesize_ideal_internal(self._tpl(), width=0.2, escape_mm=1.2)
        segs = [t for t in out["internal_tracks"] if t["net_role"] == "/DETAMPC{n}"]
        self.assertGreaterEqual(len(segs), 2, "an ideal route needs >=2 orthogonal segments")
        # every point must have escaped the pad column x=-1.14 by the margin (or be a pad endpoint)
        xs = {round(p[0], 3) for s in segs for p in (s["start_rel_mm"], s["end_rel_mm"])}
        self.assertIn(round(-1.14 - 1.2, 3), xs, "route must escape outward (x = pad-1.2)")

    def test_lone_pad_net_is_skipped(self):
        out = cce.synthesize_ideal_internal(self._tpl())
        self.assertFalse([t for t in out["internal_tracks"] if t["net_role"] == "unc"],
                         "a net with a single pad is not routable -> no ideal track")

    def test_extracted_copper_wins_over_synthesis(self):
        tpl = self._tpl()
        tpl["internal_tracks"] = [{"net_role": "/DETAMPC{n}", "layer": "F.Cu",
                                   "start_rel_mm": [0, 0], "end_rel_mm": [0, 1], "width_mm": 0.25}]
        out = cce.synthesize_ideal_internal(tpl)
        self.assertEqual(len(out["internal_tracks"]), 1, "a net with extracted copper is not re-synthesized")

    def test_hierarchical_net_resolution_is_exact_then_unique(self):
        names = ("GND", "/SHEET A/DETAMP12V", "/SHEET B/OTHER")
        self.assertEqual(cce._unique_board_netname("GND", names), "GND")
        self.assertEqual(cce._unique_board_netname("/DETAMP12V", names),
                         "/SHEET A/DETAMP12V")

    def test_hierarchical_net_resolution_refuses_ambiguity(self):
        names = ("/SHEET A/DETAMP12V", "/SHEET B/DETAMP12V")
        self.assertIsNone(cce._unique_board_netname("/DETAMP12V", names))


@unittest.skipUnless(HAVE, "pcbnew required")
class TestDoubleLayGuard(unittest.TestCase):
    """guard_kelvin_double_lay: inert on empty, skips a Kelvin pair on a locked net, restores."""

    def _fr(self, seen):
        def kp(_b):
            return [("/SENSEC1_HI", "/SENSEC1_LO"), ("/SENSEC2_HI", "/SENSEC2_LO")]

        def syn(board, *, kelvin_pairs=None, **kw):
            seen[:] = kelvin_pairs if kelvin_pairs is not None else kp(board)
            return {"taps": len(seen)}
        return types.SimpleNamespace(synthesize_kelvin_taps=syn, _board_kelvin_pairs=kp)

    def test_inert_on_empty(self):
        seen = []
        fr = self._fr(seen)
        o = fr.synthesize_kelvin_taps
        with cce.guard_kelvin_double_lay(fr, set()):
            self.assertIs(fr.synthesize_kelvin_taps, o, "no wrap installed on empty locked set")
            fr.synthesize_kelvin_taps("B")
        self.assertEqual(len(seen), 2)

    def test_skips_locked_pair_and_restores(self):
        seen = []
        fr = self._fr(seen)
        o = fr.synthesize_kelvin_taps
        with cce.guard_kelvin_double_lay(fr, {"/SENSEC1_HI"}):
            fr.synthesize_kelvin_taps("B")
        self.assertNotIn(("/SENSEC1_HI", "/SENSEC1_LO"), seen)
        self.assertIn(("/SENSEC2_HI", "/SENSEC2_LO"), seen)
        self.assertIs(fr.synthesize_kelvin_taps, o, "guard must restore the original on exit")


@unittest.skipUnless(HAVE and os.path.isfile(EPS_PCB), "pcbnew + eps board required")
class TestExtractStampLay(unittest.TestCase):
    """Read-only extract, ideal synth, stamp lay=True (clean + sabotage), locked_nets."""

    CELL = ["U10", "U20", "U30", "C10", "C11"]

    def _tpl(self):
        return cce.synthesize_ideal_internal(cce.extract(EPS_PCB, self.CELL, anchor_ref="U10"))

    def test_extract_is_read_only(self):
        with open(EPS_PCB, "rb") as f:
            before = f.read()
        cce.extract(EPS_PCB, self.CELL, anchor_ref="U10")
        with open(EPS_PCB, "rb") as f:
            self.assertEqual(f.read(), before, "extract() must never write the source")

    def test_roundtrip_identity(self):
        tpl = self._tpl()
        meta = tpl["meta"]
        placement, _ = cce.stamp(tpl, at_mm=tuple(meta["anchor_pos_mm"]), rot=meta["anchor_rot_deg"],
                                 ref_map={r: r for r in self.CELL})
        b = pcbnew.LoadBoard(EPS_PCB)
        for r in self.CELL:
            p = b.FindFootprintByReference(r).GetPosition()
            self.assertAlmostEqual(placement[r][0], p.x / 1e6, places=3)
            self.assertAlmostEqual(placement[r][1], p.y / 1e6, places=3)

    def test_clean_lay_locked_then_sabotage_refuses(self):
        import shutil
        import tempfile
        tpl = self._tpl()
        meta = tpl["meta"]
        dst = os.path.join(tempfile.mkdtemp(), "eps.kicad_pcb")
        shutil.copy(EPS_PCB, dst)
        # CLEAN: native anchor -> the ideal route lands legal -> LOCKED copper
        b = pcbnew.LoadBoard(dst)
        _, cop = cce.stamp(tpl, board=b, at_mm=tuple(meta["anchor_pos_mm"]), rot=meta["anchor_rot_deg"],
                           ref_map={r: r for r in self.CELL}, lay=True, apply=True)
        self.assertFalse(cop["laid"]["refused"], cop["laid"]["reason"])
        self.assertGreaterEqual(cop["laid"]["laid_tracks"], 1)
        locked = [t for t in b.GetTracks() if t.IsLocked()]
        self.assertTrue(locked and all(t.GetNetname() == "/DETAMPC1" for t in locked))
        pcbnew.SaveBoard(dst, b)
        self.assertEqual(cce.locked_nets(dst), {"/DETAMPC1"})

        # SABOTAGE: shift so the internal route plows foreign copper -> whole cell REFUSED, 0 laid
        dst2 = os.path.join(tempfile.mkdtemp(), "eps.kicad_pcb")
        shutil.copy(EPS_PCB, dst2)
        b2 = pcbnew.LoadBoard(dst2)
        foul = (meta["anchor_pos_mm"][0] + 6.0, meta["anchor_pos_mm"][1] + 3.0)
        placement, cop2 = cce.stamp(tpl, board=b2, at_mm=foul, rot=meta["anchor_rot_deg"],
                                    ref_map={r: r for r in self.CELL}, lay=True, apply=True)
        self.assertTrue(cop2["laid"]["refused"], "a fouled internal route must refuse the whole cell")
        self.assertEqual(cop2["laid"]["laid_tracks"] + cop2["laid"]["laid_vias"], 0)
        self.assertTrue(all(r in placement for r in self.CELL), "placement still stamps on refusal")
        self.assertEqual(sum(1 for t in b2.GetTracks() if t.IsLocked()), 0)


if __name__ == "__main__":
    unittest.main()
