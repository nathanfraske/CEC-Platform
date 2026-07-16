#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# PL-10 end-to-end: the placement actuation lifecycle. The HOST leg drives the REAL seams
# (finding_to_delta -> select_deltas -> DeltaLog) through the vindicated/refuted/control CONTRACT the
# run() wiring must satisfy. The CONTAINER leg runs the REAL apply_placement_move on the committed
# eps-8pin board (resolve body -> fence -> evict -> write a per-round override COPY).

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import cec_fs_actuator as act          # noqa: E402
import cec_fullstack as fs             # noqa: E402

EPS_PCB = os.path.join(ROOT, "modules", "eps-8pin", "eps8pin-module.kicad_pcb")
try:
    import pcbnew                      # noqa: F401
    HAVE_PCBNEW = True
except Exception:
    HAVE_PCBNEW = False


def _container_up():
    try:
        _, out = fs._exec_py("print('PING')", timeout=60)
        return "PING" in (out or "")
    except Exception:
        return False


HAVE_CONTAINER = _container_up()


class TestPlacementLifecycleDryRun(unittest.TestCase):
    """The vindicated/refuted/control CONTRACT, driven through the REAL seams (no run(), no GPU/FR)."""
    FENCE = act.resolve_fence(pinned_refs=["RS1", "U2"])
    PF = {"failure_class": "placement", "root_cause": "U30 in the /SENSEC2 corridor",
          "proposed_lever": {"lever": "re-place the body out of the band", "target": "U30"}}

    def _kept_replace(self, rnd):
        d = act.finding_to_delta(self.PF, {"routed": ""}, {}, rnd, self.FENCE, sense_nets=[])
        kept, _ = act.select_deltas([d])         # the live replace delta survives the bound (actionable)
        self.assertIn(d, kept)
        self.assertEqual(d.kind, "replace")
        return d

    def test_vindicated_keeps_and_not_refuted(self):
        log = act.DeltaLog()
        d = log.add(self._kept_replace(5))
        refuted = set()
        oc = log.record_outcome(d, self.PF, {"objective_base": 950}, {"objective_base": 960},
                                gate_metric="objective_base")
        if oc.verdict != "vindicated":           # the run() PL-06 rule
            refuted.add(act.hypothesis_key(self.PF, d))
        self.assertEqual(oc.verdict, "vindicated")
        self.assertNotIn(act.hypothesis_key(self.PF, d), refuted)   # a winner is re-appliable / compounds

    def test_refuted_rolls_back_and_anti_ratchets(self):
        log = act.DeltaLog()
        d = log.add(self._kept_replace(5))
        refuted = set()
        oc = log.record_outcome(d, self.PF, {"objective_base": 965}, {"objective_base": 960},
                                gate_metric="objective_base")
        self.assertEqual(oc.verdict, "refuted")
        self.assertEqual(d.status, "rolled_back")
        if oc.verdict != "vindicated":
            refuted.add(act.hypothesis_key(self.PF, d))
        self.assertIn(act.hypothesis_key(self.PF, d), refuted)      # not re-proposed next round

    def test_control_applies_no_move(self):
        # run() PL-05: a control round routes the committed board (override suppressed) ...
        self.assertIsNone(fs._placement_source_for("control", "/x/placed-r5.kicad_pcb", None))
        # ... and the row records it as suppressed, placement_moved False (the A/B-honest invariant)
        r = fs._placement_row_fields({"moved": False, "verdict": "suppressed"}, "control")
        self.assertFalse(r["placement_moved"])
        self.assertEqual(r["placement_verdict"], "suppressed")

    def test_bound_shared_with_other_deltas(self):
        # a placement delta shares MAX_DELTAS_PER_ROUND with avoid/effort (one select_deltas call). Build
        # FRESH pending deltas (distinct idx); _kept_replace would have already marked them 'applied'.
        cap = act.MAX_DELTAS_PER_ROUND
        deltas = [act.finding_to_delta(self.PF, {"routed": ""}, {}, 5, self.FENCE, sense_nets=[], idx=i)
                  for i in range(cap + 2)]
        self.assertTrue(all(d.kind == "replace" and d.status == "pending" for d in deltas))
        kept, rejected = act.select_deltas(deltas)
        self.assertEqual(len(kept), cap)
        self.assertTrue(all(d.status == "capped" for d in rejected))


@unittest.skipUnless(HAVE_PCBNEW and HAVE_CONTAINER and os.path.isfile(EPS_PCB),
                     "pcbnew + routing container + eps board required for the real consumer leg")
class TestRealApplyPlacementMove(unittest.TestCase):
    """The REAL consumer end-to-end: evict a body to a per-round override, refuse a fenced ref, and
    NEVER mutate the source floorplan."""

    def _violation_board(self, tag):
        import pcbnew
        b = pcbnew.LoadBoard(EPS_PCB)
        b.FindFootprintByReference("U10").SetPosition(pcbnew.VECTOR2I(40_000_000, 18_000_000))
        d = os.path.join(ROOT, "build", "fullstack")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"e2e-{tag}.kicad_pcb")
        pcbnew.SaveBoard(p, b)
        return p

    def test_evict_writes_override_and_preserves_source(self):
        committed = self._violation_board("violation")
        with open(committed, "rb") as fh:
            before = fh.read()
        fence = act.resolve_fence(pinned_refs=["RS1"])
        mv = fs.apply_placement_move(committed, committed, {"ref": None, "net": None}, fence, 999,
                                     out_rel="build/fullstack/e2e-placed.kicad_pcb")
        self.assertEqual(mv.get("verdict"), "placed", mv)
        self.assertEqual(mv["ref"], "U10")                       # resolved the violated body
        self.assertIn("U10", mv["moved_refs"])
        self.assertTrue(os.path.isfile(os.path.join(ROOT, mv["board"])))
        with open(committed, "rb") as fh:
            self.assertEqual(fh.read(), before)                  # source COPY byte-identical (edits override)

    def test_fenced_target_refused_no_override(self):
        committed = self._violation_board("fenced")
        fence = act.resolve_fence(pinned_refs=["U10"])           # the resolved body is fenced -> 2nd wall
        out_rel = "build/fullstack/e2e-fenced-out.kicad_pcb"     # distinct from the source board
        if os.path.isfile(os.path.join(ROOT, out_rel)):
            os.remove(os.path.join(ROOT, out_rel))
        mv = fs.apply_placement_move(committed, committed, {"ref": "U10", "net": None}, fence, 998,
                                     out_rel=out_rel)
        self.assertEqual(mv.get("verdict"), "fenced", mv)
        self.assertFalse(os.path.isfile(os.path.join(ROOT, out_rel)))   # no board written for a fenced move


if __name__ == "__main__":
    unittest.main(verbosity=2)
