#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Tests for cec_fs_actuator: the bounded/fenced/logged finding->actuator harness + the v4 local-min escape.
# Host-runnable -- cec_fr02 is stubbed (no pcbnew).

import os
import sys
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# ---- stub cec_fr02 (no pcbnew) ----
_fr02 = types.ModuleType("cec_fr02")
_fr02.is_sense_net = lambda n: "SENSEC" in str(n)
_fr02.clipped_corridor_rects = lambda board, nets: {
    "/SENSEC2_LO": {"rect_mm": [10, 20, 30, 50], "layers": ["F.Cu", "B.Cu"]}}
_fr02.offending_net_intents = lambda corridors, nets: [
    {"net": n, "layers": ["F.Cu"], "waypoints": [],
     "avoid": [{"rect_mm": [10, 19, 30, 51], "layers": ["F.Cu", "B.Cu"]}]}
    for n in nets if "SENSEC" not in str(n)]
sys.modules["cec_fr02"] = _fr02

import cec_fs_actuator as act           # noqa: E402

REC = {"routed": "x.kicad_pcb"}
GRID = {"contested": ["GND", "+3V3", "/I2C_SDA", "/THRESH", "/SENSEC2_LO"]}
SENSE = ["/SENSEC1_HI", "/SENSEC1_LO", "/SENSEC2_HI", "/SENSEC2_LO"]
FENCE = act.resolve_fence(kelvin_pairs=[("/SENSEC1_HI", "/SENSEC1_LO"), ("/SENSEC2_HI", "/SENSEC2_LO")],
                          pinned_refs=["RS1", "U2"])


def _f(lever, target=None):
    return {"proposed_lever": {"lever": lever, "target": target}}


class TestFence(unittest.TestCase):
    def test_sense_and_pinned_fenced(self):
        self.assertTrue(act.is_fenced("/SENSEC2_LO", FENCE))    # sense net
        self.assertTrue(act.is_fenced("/SENSEC1_HI", FENCE))    # kelvin pair
        self.assertTrue(act.is_fenced("RS1", FENCE))            # pinned shunt
        self.assertTrue(act.is_fenced("U2", FENCE))             # pinned IC
        self.assertFalse(act.is_fenced("/I2C_SDA", FENCE))      # a free signal net


class TestFindingToDelta(unittest.TestCase):
    def test_avoid_on_free_net(self):
        d = act.finding_to_delta(_f("route net around corridor", "/I2C_SDA"), REC, GRID, 5, FENCE, sense_nets=SENSE)
        self.assertEqual(d.kind, "avoid")
        self.assertEqual(d.intent["net"], "/I2C_SDA")

    def test_avoid_on_sense_REFUSED(self):
        d = act.finding_to_delta(_f("route net around corridor", "/SENSEC2_LO"), REC, GRID, 5, FENCE, sense_nets=SENSE)
        self.assertEqual(d.status, "refused")
        self.assertEqual(d.kind, "refused")

    def test_replace_on_pinned_REFUSED(self):
        d = act.finding_to_delta(_f("re-place the part", "U2"), REC, GRID, 5, FENCE, sense_nets=SENSE)
        self.assertEqual(d.status, "refused")

    def test_effort_and_noop(self):
        self.assertEqual(act.finding_to_delta(_f("bump router passes"), REC, GRID, 5, FENCE).kind, "effort")
        self.assertEqual(act.finding_to_delta(_f("reweight the scorer", "drc"), REC, GRID, 5, FENCE).kind, "noop")
        self.assertEqual(act.finding_to_delta({"proposed_lever": None}, REC, GRID, 5, FENCE).kind, "noop")


class TestBound(unittest.TestCase):
    def test_cap(self):
        ds = [act.finding_to_delta(_f("avoid corridor", n), REC, GRID, 5, FENCE, sense_nets=SENSE, idx=i)
              for i, n in enumerate(["/I2C_SDA", "/THRESH", "/CAN_H"])]
        keep, rejected = act.select_deltas(ds, cap=2)
        self.assertEqual(len(keep), 2)
        self.assertTrue(all(d.status == "applied" for d in keep))
        self.assertTrue(any(d.status == "capped" for d in rejected))


class TestPhysicsFlat(unittest.TestCase):
    def test_flat(self):
        rows = [{"objective": 960000, "max_T": 250.0}] * 3
        self.assertTrue(act.physics_flat(rows))

    def test_improving(self):
        rows = [{"objective": 990000, "max_T": 300}, {"objective": 970000, "max_T": 270},
                {"objective": 940000, "max_T": 250}]
        self.assertFalse(act.physics_flat(rows))


class TestV4Escape(unittest.TestCase):
    FLAT = [{"objective": 960000, "max_T": 250.0}] * 3

    def test_high_risk_flat_forces_structural_not_penalty(self):
        d = act.v4_structural_escape("high", self.FLAT, REC, GRID, 7, FENCE, sense_nets=SENSE)
        self.assertIsNotNone(d)
        self.assertIn(d.kind, ("avoid", "replace"))           # structural, never a penalty
        self.assertEqual(d.source, "v4-escape")
        if d.kind == "avoid":
            self.assertFalse(act.is_fenced(d.intent["net"], FENCE))   # never steers a fenced net

    def test_not_flat_no_escape(self):
        improving = [{"objective": 990000, "max_T": 300}, {"objective": 950000, "max_T": 260},
                     {"objective": 910000, "max_T": 240}]
        self.assertIsNone(act.v4_structural_escape("high", improving, REC, GRID, 7, FENCE, sense_nets=SENSE))

    def test_low_risk_no_escape(self):
        self.assertIsNone(act.v4_structural_escape("low", self.FLAT, REC, GRID, 7, FENCE, sense_nets=SENSE))

    def test_only_fenced_contested_escalates_to_replace(self):
        grid = {"contested": ["/SENSEC2_LO", "GND", "+3V3"]}   # nothing steerable
        d = act.v4_structural_escape("high", self.FLAT, REC, grid, 7, FENCE, sense_nets=SENSE)
        self.assertEqual(d.kind, "replace")                   # never a penalty


class TestSymmetricOutcomes(unittest.TestCase):
    """Failures + overturns enter the corpus with the SAME detail as victories (no survivorship bias)."""
    F = {"root_cause": "foreign nets cross the /SENSEC2 corridor", "failure_class": "routing",
         "reasoning": "I2C_SDA crosses the sense band", "proposed_lever": {"lever": "route around corridor",
         "target": "/I2C_SDA"}}
    FB = {"root_cause": "THRESH crosses too", "failure_class": "routing",
          "proposed_lever": {"lever": "route around corridor", "target": "/THRESH"}}

    def _delta(self, f, rnd):
        return act.finding_to_delta(f, REC, GRID, rnd, FENCE, sense_nets=SENSE)

    def test_failure_recorded_with_full_detail(self):
        log = act.DeltaLog()
        d = log.add(self._delta(self.F, 5))
        oc = log.record_outcome(d, self.F, {"objective": 965000, "gates_pass": False},
                                {"objective": 960000, "gates_pass": False},
                                corpus_state={"live_rules_sha": "abc123"})
        self.assertEqual(oc.verdict, "refuted")
        # SAME fields a victory carries: full finding + BOTH metric sides + margin + corpus_state
        self.assertIn("foreign nets", oc.finding["root_cause"])
        self.assertEqual(oc.finding["proposed_lever"]["target"], "/I2C_SDA")
        self.assertEqual(oc.treatment["objective"], 965000)
        self.assertEqual(oc.control["objective"], 960000)
        self.assertEqual(oc.corpus_state["live_rules_sha"], "abc123")
        self.assertLess(oc.margin, 0)                       # treatment worse than control
        self.assertEqual(d.status, "rolled_back")           # a refuted delta rolls back, never ratchets

    def test_victory(self):
        log = act.DeltaLog()
        d = log.add(self._delta(self.F, 5))
        oc = log.record_outcome(d, self.F, {"objective": 950000, "gates_pass": False},
                                {"objective": 960000, "gates_pass": False})
        self.assertEqual(oc.verdict, "vindicated")
        self.assertGreater(oc.margin, 0)
        self.assertEqual(d.status, "vindicated")

    def test_gatepass_dominates_objective(self):
        log = act.DeltaLog()
        d = log.add(self._delta(self.F, 5))
        oc = log.record_outcome(d, self.F, {"objective": 970000, "gates_pass": True},   # worse obj but PASSES
                                {"objective": 950000, "gates_pass": False})
        self.assertEqual(oc.verdict, "vindicated")

    def test_win_then_loss_is_overturned(self):
        log = act.DeltaLog()
        d1 = log.add(self._delta(self.F, 5))
        log.record_outcome(d1, self.F, {"objective": 950000, "gates_pass": False},
                           {"objective": 960000, "gates_pass": False})
        d2 = log.add(self._delta(self.F, 9))                # SAME hypothesis, later loses
        oc = log.record_outcome(d2, self.F, {"objective": 965000, "gates_pass": False},
                                {"objective": 960000, "gates_pass": False})
        self.assertEqual(oc.verdict, "overturned")
        self.assertEqual(oc.supersedes, d1.id)
        self.assertEqual(log.tally(), {"vindicated": 1, "refuted": 0, "overturned": 1})

    def test_different_hypothesis_loss_is_refuted_not_overturn(self):
        log = act.DeltaLog()
        d1 = log.add(self._delta(self.F, 5))
        log.record_outcome(d1, self.F, {"objective": 950000}, {"objective": 960000})  # F wins
        d2 = log.add(self._delta(self.FB, 9))
        oc = log.record_outcome(d2, self.FB, {"objective": 965000}, {"objective": 960000})  # FB loses
        self.assertEqual(oc.verdict, "refuted")             # different target = different hypothesis


if __name__ == "__main__":
    unittest.main(verbosity=2)
