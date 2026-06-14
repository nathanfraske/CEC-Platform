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
                    "kelvin_ok": True, "diffpair_ok": True, "drc": 6, "unconnected": 2}

    def _result(self, *, flipped=1, reverted=False, gates_pass=True, drc=4, unconnected=0, board=True):
        return {"report": {"flipped": flipped, "reverted": reverted},
                "rescored": {"kelvin_ok": True, "diffpair_ok": True, "gates_pass": gates_pass,
                             "drc": drc, "unconnected": unconnected},
                "board": self.board_rel if board else None}

    def test_adopts_and_refreshes_metrics(self):
        reason = fs._adopt_staggered_board(self.rec, self._result(drc=4, unconnected=0), self.root)
        self.assertTrue(reason)
        self.assertEqual(self.rec["routed"], os.path.join(self.root, self.board_rel))
        self.assertTrue(self.rec["staggered"])
        self.assertEqual(self.rec["drc"], 4)                     # refreshed from the rescore
        self.assertEqual(self.rec["unconnected"], 0)

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


if __name__ == "__main__":
    unittest.main()
