# SPDX-License-Identifier: Apache-2.0
"""Tests for the PlacementSession intent-compiler (placer-feasibility SLICE-1b).

Covers the two correctness guarantees: (1) partition=None is byte-identical to the
un-partitioned placer (inertness -> golden-safe), and (2) an agent's region assignment is
enforced as HARD containment (a free part lands in its region, through the full placer). The
real-route ORACLE grade is gated behind CEC_ORACLE_TEST=1 (it routes a board, ~60s)."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

import cec_synth_pipeline as csp           # noqa: E402
import cec_placement_session as cps        # noqa: E402
import dataclasses                         # noqa: E402

BOARD, W, H = "eps-8pin", 96.0, 37.0


def _sess():
    return cps.PlacementSession(BOARD, W, H)


def test_partition_none_is_byte_identical():
    """A session with no assign() must compile to EXACTLY the un-partitioned placement (the
    golden-safety guarantee: the partition lever is inert until an agent uses it)."""
    cfgd = dataclasses.asdict(csp.Config.load(BOARD))
    base = csp.synth_one(cfgd, W, H, "dataflow", 0, partition=None)
    sess = _sess().compile()                       # no assign -> partition()=None
    assert sess.P == base.P
    assert sess.residual == base.residual


def test_helpers_classify_eps():
    """peripheral_ics = the FREE core (CAN/LDO/RESET button); cable_parts = the sense chain
    (shunts + INA238 + INA181 + comparator); antenna = the ESP. No overlap, ESP not in either set."""
    s = _sess()
    periph, cable, ant = set(s.peripheral_ics()), set(s.cable_parts()), set(s.antenna_ics())
    assert ant == {"U1"}                           # the ESP32
    assert {"RS1", "RS2"} <= cable                 # shunts
    assert {"U10", "U11", "U20", "U21"} <= cable   # INA238 + INA181
    assert "U2" in periph and "U3" in periph       # CAN + LDO are free peripherals
    assert "U1" not in cable and "U1" not in periph  # the seated ESP is in neither
    assert periph.isdisjoint(cable)


def test_partition_hard_containment():
    """Assigning the free peripheral ICs to a right-half region must leave EVERY governed part
    inside that region (free_violations empty), at zero residual."""
    s = _sess()
    s.half("periph", "x", 0.58, 1.00)
    s.half("cables", "x", 0.00, 0.58)
    s.assign(s.peripheral_ics(), "periph")
    s.assign(s.cable_parts(), "cables")
    cand = s.compile()
    assert s.free_violations(cand) == {}
    assert cand.residual == 0
    # every governed (free) assigned ref is genuinely inside its region box
    rep = s.containment_report(cand)
    gov = {r: v for r, v in rep.items() if v[2]}
    assert gov and all(v[1] for v in gov.values())


def test_partition_teeth_arbitrary_box():
    """The teeth: a free IC FORCED to an arbitrary tight box lands inside it -- proves the
    containment is real hard placement, not a coincidence of the default layout."""
    s = _sess()
    s.region("box", (2.0, 2.0, 16.0, 16.0))
    s.assign(["U2"], "box")                        # U2 = CAN transceiver, a free mover
    cand = s.compile()
    region, inside, governed, (ccx, ccy) = s.containment_report(cand)["U2"]
    assert governed and inside
    assert 2.0 <= ccx <= 16.0 and 2.0 <= ccy <= 16.0


def test_snapshot_rollback():
    s = _sess()
    s.half("a", "x", 0.0, 0.5)
    s.half("b", "x", 0.5, 1.0)
    s.assign(["U2"], "a")
    snap = s.snapshot()
    s.assign(["U2"], "b")
    assert s._assign["U2"] == "b"
    s.rollback(snap)
    assert s._assign["U2"] == "a"


@pytest.mark.skipif(os.environ.get("CEC_ORACLE_TEST") != "1",
                    reason="real-route oracle grade (~60s); set CEC_ORACLE_TEST=1 to run")
def test_partitioned_eps_reaches_gate():
    """Milestone-1 metric: a structure-first partition compiles to a board the route-oracle
    grades gate-clean (matching the hand-intent eps). Slow -- routes a real board."""
    s = _sess()
    s.half("periph", "x", 0.58, 1.00)
    s.half("cables", "x", 0.00, 0.58)
    s.assign(s.peripheral_ics(), "periph")
    s.assign(s.cable_parts(), "cables")
    v = s.grade(passes=12, opt=15)
    assert v["foreign_ok"] and v["thermal_ok"]
    assert v["kelvin_ok"], v["reasons"]
