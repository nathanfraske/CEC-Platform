#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# FAIL-CLOSED hardening of the absolute high-current-pour keepout (owner-flagged fail-open, 2026-06-28).
#
# THE HOLE: cec_constraints._derive_pour_boxes wrapped cec_fr.derive_power_pours in try/except and
# collapsed both a RAISE and an EMPTY result into a benign (None, None) -> applicable=False -> the
# router fold never fired -> a board WITH laid SENSEC pours but a broken region-finder (SWIG/net
# corruption, or a placement that broke shunt-straddle detection) shipped silently with its 40A fill
# unprotected. derive works off connector+shunt PAD geometry, so pours can EXIST while derive fails.
#
# THE FIX: _has_sensec_pours(board) reads board.Zones() (INDEPENDENT of derive) to detect laid SENSEC
# F.Cu/B.Cu pour copper; when present and derive raises/empties, _derive_pour_boxes raises
# PourRegionError -> foreign_on_pour_summary reports status="error"/applicable=True ->
# _chk_foreign_on_pour FAILs and cec_router.independent_drc forces gates_pass=False. A GENUINE no-pour
# board (Hub, pre-route floorplan) keeps the correct applicable=False N/A even when derive raises.
#
# TEETH: construct a board-with-pours from the committed EPS floorplan (cec_fr.add_power_pours lays the
# SENSEC zones), force derive to raise OR return [], and assert every gate path fails CLOSED.

import os
import sys
import shutil
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

EPS = os.path.join(ROOT, "beta", "eps-8pin-rev3", "eps-8pin-rev3.kicad_pcb")
HUB = os.path.join(ROOT, "hubs", "hub-standard", "hub-standard.kicad_pcb")

try:
    import pcbnew                                              # noqa: F401
    import cec_fr
    import cec_constraints as K
    import cec_router
    import cec_score
    HAVE = True
except Exception:                                              # noqa: BLE001
    HAVE = False

CID = "no-foreign-on-high-current-pour"


def _copy_with_siblings(src_pcb, dst_pcb):
    shutil.copy(src_pcb, dst_pcb)
    for ext in (".kicad_pro", ".kicad_dru", ".kicad_prl"):
        s = src_pcb[:-len(".kicad_pcb")] + ext
        if os.path.isfile(s):
            shutil.copy(s, dst_pcb[:-len(".kicad_pcb")] + ext)


def _eps_with_pours(tmpdir):
    """A copy of the committed EPS floorplan with the additive SENSEC F.Cu/B.Cu pour zones laid
    (cec_fr.add_power_pours) -- i.e. _has_sensec_pours(board) is True. Reproducible from committed
    parts, no build/ artifact dependency."""
    dst = os.path.join(tmpdir, "eps_with_pours.kicad_pcb")
    _copy_with_siblings(EPS, dst)
    b = pcbnew.LoadBoard(dst)
    pours = cec_fr.derive_power_pours(dst, board=b)
    assert pours, "the committed EPS floorplan must yield SENSEC pours to seed this test"
    cec_fr.add_power_pours(b, pours)
    b.Save(dst)
    return dst


@unittest.skipUnless(HAVE and os.path.isfile(EPS), "pcbnew + eps-8pin-rev3 required")
class TestForeignOnPourFailClosed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self._orig_derive = cec_fr.derive_power_pours

    def tearDown(self):
        cec_fr.derive_power_pours = self._orig_derive

    def test_has_sensec_pours_detects_laid_zones(self):
        p = _eps_with_pours(self.tmp)
        self.assertTrue(K._has_sensec_pours(pcbnew.LoadBoard(p)),
                        "add_power_pours zones must be seen by _has_sensec_pours")
        # control: the bare floorplan (no laid pours) is NOT a pours-board
        self.assertFalse(K._has_sensec_pours(pcbnew.LoadBoard(EPS)))

    def _force(self, fn):
        cec_fr.derive_power_pours = fn

    def test_derive_raises_with_pours_fails_closed(self):
        p = _eps_with_pours(self.tmp)
        self._force(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulated SWIG net corruption")))
        # summary: applicable=True (NOT vacuous), status="error"
        s = K.foreign_on_pour_summary(p)
        self.assertTrue(s["applicable"])
        self.assertEqual(s["status"], "error")
        # checker: FAIL (not an N/A skip)
        ok, detail = K.CHECKERS[CID](pcbnew.LoadBoard(p), p, {})[:2]
        self.assertIs(ok, False, detail)
        self.assertIn("FAIL-CLOSED", detail)
        # router INDEPENDENT verdict: gates_pass forced False with the fail-closed reason
        v = cec_router.independent_drc(p, cec_score.Rules.from_board(p))
        self.assertFalse(v["gates_pass"], "region-finder error on a pours-board must fail the verdict")
        self.assertEqual(v["foreign_on_pour"]["status"], "error")
        self.assertTrue(any("FAIL-CLOSED" in r for r in v["reasons"]), v["reasons"])

    def test_derive_empty_with_pours_fails_closed(self):
        p = _eps_with_pours(self.tmp)
        self._force(lambda *a, **k: [])
        s = K.foreign_on_pour_summary(p)
        self.assertTrue(s["applicable"])
        self.assertEqual(s["status"], "error")
        ok = K.CHECKERS[CID](pcbnew.LoadBoard(p), p, {})[0]
        self.assertIs(ok, False)

    def test_sense_body_clear_sibling_fails_closed(self):
        p = _eps_with_pours(self.tmp)
        self._force(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        ok, detail = K._chk_sense_body_clear(pcbnew.LoadBoard(p), p, {})[:2]
        self.assertIs(ok, False, detail)
        self.assertIn("FAIL-CLOSED", detail)

    @unittest.skipUnless(os.path.isfile(HUB), "hub-standard required")
    def test_genuine_no_pour_board_stays_na_on_error(self):
        # a board with NO SENSEC pours must remain a correct applicable=False N/A even when derive
        # raises -- the fix must not convert genuine non-cable boards into false failures.
        self._force(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        s = K.foreign_on_pour_summary(HUB)
        self.assertFalse(s["applicable"])
        self.assertEqual(s["status"], "na")
        ok = K.CHECKERS[CID](pcbnew.LoadBoard(HUB), HUB, {})[0]
        self.assertIsNone(ok, "no-pour board must stay N/A, not fail")

    def test_empty_no_pour_board_stays_na(self):
        self._force(lambda *a, **k: [])
        s = K.foreign_on_pour_summary(EPS)        # committed floorplan: no laid pours
        self.assertFalse(s["applicable"])
        self.assertEqual(s["status"], "na")


if __name__ == "__main__":
    unittest.main()
