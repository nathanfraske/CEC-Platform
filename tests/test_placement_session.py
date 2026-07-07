# SPDX-License-Identifier: Apache-2.0
"""Tests for the PlacementSession intent-compiler (placer-feasibility SLICE-1b).

Covers the two correctness guarantees: (1) partition=None is byte-identical to the
un-partitioned placer (inertness -> golden-safe), and (2) an agent's region assignment is
enforced as HARD containment (a free part lands in its region, through the full placer). The
real-route ORACLE grade is gated behind CEC_ORACLE_TEST=1 (it routes a board, ~60s).

unittest-style (2026-07-07): the original module used pytest, which the routing container
does not carry -- the suite is unittest everywhere else in this repo."""
import dataclasses
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import cec_synth_pipeline as csp           # noqa: E402
import cec_placement_session as cps        # noqa: E402

BOARD, W, H = "eps-8pin", 96.0, 37.0


def _sess():
    return cps.PlacementSession(BOARD, W, H)


class TestPlacementSession(unittest.TestCase):
    def test_partition_none_is_byte_identical(self):
        """A session with no assign() must compile to EXACTLY the un-partitioned placement (the
        golden-safety guarantee: the partition lever is inert until an agent uses it)."""
        cfgd = dataclasses.asdict(csp.Config.load(BOARD))
        base = csp.synth_one(cfgd, W, H, "dataflow", 0, partition=None)
        sess = _sess().compile()                       # no assign -> partition()=None
        self.assertEqual(sess.P, base.P)
        self.assertEqual(sess.residual, base.residual)

    def test_helpers_classify_eps(self):
        """peripheral_ics = the FREE core (CAN/LDO/RESET button); cable_parts = the sense chain
        (shunts + INA238 + INA181 + comparator); antenna = the ESP. No overlap, ESP in neither."""
        s = _sess()
        periph, cable, ant = set(s.peripheral_ics()), set(s.cable_parts()), set(s.antenna_ics())
        self.assertEqual(ant, {"U1"})                            # the ESP32
        self.assertLessEqual({"RS1", "RS2"}, cable)              # shunts
        self.assertLessEqual({"U10", "U11", "U20", "U21"}, cable)  # INA238 + INA181
        self.assertIn("U2", periph)                              # CAN is a free peripheral
        self.assertIn("U3", periph)                              # LDO is a free peripheral
        self.assertNotIn("U1", cable)
        self.assertNotIn("U1", periph)
        self.assertTrue(periph.isdisjoint(cable))

    def test_partition_hard_containment(self):
        """Assigning the free peripheral ICs to a right-half region must leave EVERY governed
        part inside that region (free_violations empty), at zero residual."""
        s = _sess()
        s.half("periph", "x", 0.58, 1.00)
        s.half("cables", "x", 0.00, 0.58)
        s.assign(s.peripheral_ics(), "periph")
        s.assign(s.cable_parts(), "cables")
        cand = s.compile()
        self.assertEqual(s.free_violations(cand), {})
        self.assertEqual(cand.residual, 0)
        # every governed (free) assigned ref is genuinely inside its region box
        rep = s.containment_report(cand)
        gov = {r: v for r, v in rep.items() if v[2]}
        self.assertTrue(gov)
        self.assertTrue(all(v[1] for v in gov.values()))

    def test_partition_teeth_arbitrary_box(self):
        """The teeth: a free IC FORCED to an arbitrary tight box lands inside it -- proves the
        containment is real hard placement, not a coincidence of the default layout."""
        s = _sess()
        s.region("box", (2.0, 2.0, 16.0, 16.0))
        s.assign(["U2"], "box")                        # U2 = CAN transceiver, a free mover
        cand = s.compile()
        region, inside, governed, (ccx, ccy) = s.containment_report(cand)["U2"]
        self.assertTrue(governed)
        self.assertTrue(inside)
        self.assertTrue(2.0 <= ccx <= 16.0 and 2.0 <= ccy <= 16.0)

    def test_snapshot_rollback(self):
        s = _sess()
        s.half("a", "x", 0.0, 0.5)
        s.half("b", "x", 0.5, 1.0)
        s.assign(["U2"], "a")
        snap = s.snapshot()
        s.assign(["U2"], "b")
        self.assertEqual(s._assign["U2"], "b")
        s.rollback(snap)
        self.assertEqual(s._assign["U2"], "a")

    @unittest.skipUnless(os.environ.get("CEC_ORACLE_TEST") == "1",
                         "real-route oracle grade (~60s); set CEC_ORACLE_TEST=1 to run")
    def test_partitioned_eps_reaches_gate(self):
        """Milestone-1 metric: a structure-first partition compiles to a board the route-oracle
        grades gate-clean (matching the hand-intent eps). Slow -- routes a real board."""
        s = _sess()
        s.half("periph", "x", 0.58, 1.00)
        s.half("cables", "x", 0.00, 0.58)
        s.assign(s.peripheral_ics(), "periph")
        s.assign(s.cable_parts(), "cables")
        v = s.grade(passes=12, opt=15)
        self.assertTrue(v["foreign_ok"] and v["thermal_ok"])
        self.assertTrue(v["kelvin_ok"], v["reasons"])


if __name__ == "__main__":
    unittest.main()
