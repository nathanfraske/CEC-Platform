#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Item 3 of the layer-lever rework (audit w23i0d8nq): the staggered board must be FED BACK into
# rec["routed"] so it actually ships, instead of being measured-and-discarded. _adopt_staggered_board is
# the pure, host-testable core of that feedback path. All host-runnable (pcbnew stubbed -- the helper
# never touches the engine, only the stagger_result dict + a filesystem existence check).

import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
# cec_fullstack -> cec_fr does a top-level `import pcbnew`. These tests never touch the engine (they
# exercise the pure adoption/gate helpers), so on a pcbnew-LESS box we stub it. But if REAL pcbnew is
# present we must NOT install a stub -- a stub in sys.modules would shadow the real module for any other
# test in the same process (e.g. test_corridor_model's real LoadBoard), breaking it order-dependently.
try:
    import pcbnew                                                 # noqa: F401  (real engine present)
except Exception:                                                 # noqa: BLE001
    sys.modules.setdefault("pcbnew", types.ModuleType("pcbnew"))

import cec_fullstack as fs                                        # noqa: E402


class TestAdoptStaggeredBoard(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.board_rel = "build/fullstack/stagger-r3.kicad_pcb"
        p = os.path.join(self.root, self.board_rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w").close()                                     # the staggered board exists on disk
        self.rec = {"routed": "/old/routed.kicad_pcb", "gates_pass": True,
                    "kelvin_ok": True, "diffpair_ok": True, "drc": 6, "unconnected": 2,
                    "vias": 80, "tracks": 500, "length": 999.0, "plane_signal_mm": 1.0, "max_T": 200.0,
                    "objective_base": 88.0}

    def _result(self, *, flipped=1, reverted=False, gates_pass=True, drc=4, unconnected=0, board=True,
                facts=None, rescored_extra=None, drop_max_T=False):
        rs = {"kelvin_ok": True, "diffpair_ok": True, "gates_pass": gates_pass,
              "drc": drc, "unconnected": unconnected, "vias": 96, "tracks": 510,
              "length": 1010.0, "plane_signal_mm": 0.5, "max_T": 150.0, "objective": 42.0}
        if drop_max_T:
            rs.pop("max_T")
        if rescored_extra:
            rs.update(rescored_extra)
        return {"report": {"flipped": flipped, "reverted": reverted},
                "rescored": rs,
                "facts": {"/SENSEC1_HI": {"islands": 1, "area_mm2": 120.0, "components": 1}}
                         if facts is None else facts,
                "board": self.board_rel if board else None}

    def test_refreshes_objective_base_from_shipped_board(self):
        fs._adopt_staggered_board(self.rec, self._result(), self.root)
        self.assertEqual(self.rec["objective_base"], 42.0)       # was 88.0 (pre-stagger) -> shipped board

    def test_drops_stale_max_T_on_fem_error(self):
        # FEM errored on the staggered board (no max_T in the re-measurement) -> the stale pre-stagger
        # max_T must be DROPPED (record excluded from the frontier, not ranked on a stale thermal axis)
        fs._adopt_staggered_board(self.rec, self._result(drop_max_T=True), self.root)
        self.assertNotIn("max_T", self.rec)

    def test_adopts_and_refreshes_all_pareto_axes(self):
        reason = fs._adopt_staggered_board(self.rec, self._result(drc=4, unconnected=0), self.root)
        self.assertTrue(reason)
        self.assertEqual(self.rec["routed"], os.path.join(self.root, self.board_rel))
        self.assertTrue(self.rec["staggered"])
        self.assertEqual(self.rec["drc"], 4)                     # refreshed from the rescore
        self.assertEqual(self.rec["unconnected"], 0)
        self.assertEqual(self.rec["vias"], 96)                   # vias MUST refresh (stagger ADDS vias)
        self.assertEqual(self.rec["tracks"], 510)
        self.assertEqual(self.rec["max_T"], 150.0)               # the axis the lever moves -- refreshed
        self.assertEqual(self.rec["plane_signal_mm"], 0.5)

    def test_no_adopt_without_facts(self):
        # the re-measurement (incl. pour facts) MUST be present -- an unverifiable stagger never ships
        self.assertEqual(fs._adopt_staggered_board(self.rec, self._result(facts={}), self.root), "")
        self.assertEqual(self.rec["routed"], "/old/routed.kicad_pcb")

    def test_no_adopt_when_reverted(self):
        reason = fs._adopt_staggered_board(self.rec, self._result(reverted=True), self.root)
        self.assertEqual(reason, "")
        self.assertEqual(self.rec["routed"], "/old/routed.kicad_pcb")  # unchanged
        self.assertNotIn("staggered", self.rec)

    def test_no_adopt_when_nothing_flipped(self):
        self.assertEqual(fs._adopt_staggered_board(self.rec, self._result(flipped=0), self.root), "")
        self.assertEqual(self.rec["routed"], "/old/routed.kicad_pcb")

    def test_never_downgrades_a_passing_board(self):
        # rec gates_pass=True; the staggered rescore gates_pass=False -> must NOT adopt
        reason = fs._adopt_staggered_board(self.rec, self._result(gates_pass=False), self.root)
        self.assertEqual(reason, "")
        self.assertEqual(self.rec["routed"], "/old/routed.kicad_pcb")
        self.assertTrue(self.rec["gates_pass"])                  # metrics untouched

    def test_adopts_when_original_already_failing(self):
        # a gate-failing board MAY adopt a still-failing-but-not-worse staggered board (no downgrade)
        self.rec["gates_pass"] = False
        reason = fs._adopt_staggered_board(self.rec, self._result(gates_pass=False, drc=3), self.root)
        self.assertTrue(reason)
        self.assertEqual(self.rec["drc"], 3)

    def test_no_adopt_when_board_file_missing(self):
        os.remove(os.path.join(self.root, self.board_rel))
        self.assertEqual(fs._adopt_staggered_board(self.rec, self._result(), self.root), "")

    def test_no_adopt_on_error_or_empty(self):
        self.assertEqual(fs._adopt_staggered_board(self.rec, {"error": "boom"}, self.root), "")
        self.assertEqual(fs._adopt_staggered_board(self.rec, None, self.root), "")


class TestRemeasurePourGate(unittest.TestCase):
    """_remeasure_pour_gate closes the gate-launder (re-audit BLOCKER): the stagger rescore's gates_pass is
    pour-BLIND, so after adoption the SHIPPED board's pour integrity must be re-verified and folded into
    gates_pass -- a fragmented sense pour must force gates_pass False even if the rescore said True."""

    def test_fragmented_pour_forces_gate_fail(self):
        rec = {"gates_pass": True, "drc": 4, "objective": 0.0, "reasons": []}
        facts = {"/SENSEC1_HI": {"islands": 3, "area_mm2": 90.0, "components": 3},   # FRAGMENTED
                 "/SENSEC1_LO": {"islands": 1, "area_mm2": 120.0, "components": 1}}
        det = fs._remeasure_pour_gate(rec, facts, {})
        self.assertFalse(rec["gates_pass"])                      # laundered True -> forced False
        self.assertFalse(rec["pour_integrity_ok"])
        self.assertEqual(rec["islands_excess"], 2)               # 3 islands -> excess 2
        self.assertIn("/SENSEC1_HI", det)                        # det_clipped reflects the staggered board
        self.assertTrue(any("pour_integrity(staggered)" in r for r in rec["reasons"]))

    def test_healthy_pour_keeps_gate(self):
        rec = {"gates_pass": True, "drc": 2, "objective": 0.0, "reasons": []}
        facts = {"/SENSEC1_HI": {"islands": 1, "area_mm2": 120.0, "components": 1},
                 "/SENSEC1_LO": {"islands": 1, "area_mm2": 118.0, "components": 1}}
        det = fs._remeasure_pour_gate(rec, facts, {})
        self.assertTrue(rec["gates_pass"])                       # healthy pours -> gate stays
        self.assertTrue(rec["pour_integrity_ok"])
        self.assertEqual(rec["islands_excess"], 0)
        self.assertEqual(det, [])
        self.assertIsInstance(rec["objective"], float)           # objective recomputed from the shipped board


if __name__ == "__main__":
    unittest.main()
