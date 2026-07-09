# SPDX-License-Identifier: Apache-2.0
"""Teeth for the pass-runner MECHANISM (docs/pass-form-plan.md, stage S1).

These are SYNTHETIC-case teeth for cec_passes -- no pcbnew, host-runnable. They prove the
two enforcement rungs BITE when turned on and are INERT by default (the byte-identity /
golden-safety guarantee the synth_one refactor rests on):

  * enforce_locks=True + a pass that moves a LOCKED ref -> LockViolation (loud + named).
  * a gate_enabled gate whose checker FAILS -> GateFailure halts the ladder (pass name +
    violations), and NO later pass runs.
  * default (enforce_locks=False, gates off) -> the SAME misbehaving pass + failing checker
    do NOT raise; the ladder runs to the end.
  * the per-pass journal serialises to JSON (it becomes the wave verdict's provenance).

Turning a real lock/gate on by default is later fixed-seed ablation work -- these tests only
prove the MECHANISM, not any board policy.
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))

from cec_passes import (Pass, PassLadder, LockViolation, GateFailure,   # noqa: E402
                        journal_to_json, _pos_eq)


class _Board:
    """A minimal placement state the ladder observes: a {ref:(x,y,rot)} dict."""

    def __init__(self):
        self.P = {}


def _positions(st):
    return st.P


# --------------------------------------------------------------- helper pass builders
def _place(ref, xyr):
    def fn(st):
        st.P[ref] = xyr
    return fn


def _move(ref, xyr):
    def fn(st):
        st.P[ref] = xyr
    return fn


class TestLockEnforcement(unittest.TestCase):
    def _ladder(self, enforce):
        st = _Board()
        passes = [
            Pass("p_anchor", _place("J1", (10.0, 5.0, 0.0)), locks_out=["J1"], phase="P2"),
            Pass("p_other", _place("U1", (20.0, 20.0, 0.0)), phase="P3"),
            Pass("p_bad", _move("J1", (99.0, 99.0, 0.0)), phase="P7"),   # moves LOCKED J1
        ]
        return st, PassLadder(passes, _positions, enforce_locks=enforce)

    def test_enforce_on_raises_lockviolation(self):
        st, lad = self._ladder(enforce=True)
        with self.assertRaises(LockViolation) as cm:
            lad.run(st)
        e = cm.exception
        self.assertEqual(e.pass_name, "p_bad")
        self.assertEqual(e.ref, "J1")
        self.assertEqual(e.locked_pos, (10.0, 5.0, 0.0))
        self.assertEqual(e.moved_to, (99.0, 99.0, 0.0))
        # the loud message names the pass and the ref
        self.assertIn("p_bad", str(e))
        self.assertIn("J1", str(e))
        # the ladder journaled the offending pass with a lock-violation error marker
        self.assertEqual(lad.journal[-1]["pass"], "p_bad")
        self.assertEqual(lad.journal[-1]["error"], "lock-violation:J1")

    def test_off_is_inert_same_passes(self):
        # the EXACT same misbehaving ladder must NOT raise with enforcement off (the default)
        st, lad = self._ladder(enforce=False)
        journal = lad.run(st)
        self.assertEqual(st.P["J1"], (99.0, 99.0, 0.0))     # the move landed (no enforcement)
        self.assertEqual(len(journal), 3)                   # every pass ran
        self.assertEqual(lad.locked_refs()["J1"], (10.0, 5.0, 0.0))  # lock still RECORDED

    def test_untouched_lock_does_not_trip(self):
        # a later pass that does NOT move the locked ref runs clean under enforcement
        st = _Board()
        passes = [
            Pass("p_anchor", _place("J1", (10.0, 5.0, 0.0)), locks_out=["J1"]),
            Pass("p_ok", _place("U1", (20.0, 20.0, 0.0))),           # leaves J1 alone
            Pass("p_ok2", _move("J1", (10.0, 5.0, 0.0))),            # re-assigns SAME value: not a move
        ]
        lad = PassLadder(passes, _positions, enforce_locks=True)
        lad.run(st)                                                  # no raise
        self.assertEqual(len(lad.journal), 3)

    def test_first_lock_wins(self):
        st = _Board()
        passes = [
            Pass("p_a", _place("J1", (1.0, 1.0, 0.0)), locks_out=["J1"]),
            Pass("p_b", _place("U1", (2.0, 2.0, 0.0)), locks_out=["J1", "U1"]),  # re-lock J1 (ignored)
        ]
        lad = PassLadder(passes, _positions)
        lad.run(st)
        self.assertEqual(lad.locked_refs()["J1"], (1.0, 1.0, 0.0))   # first lock kept
        self.assertEqual(lad.locked_refs()["U1"], (2.0, 2.0, 0.0))
        # p_b's journal 'locked' lists only the NEWLY locked ref (U1), not the already-locked J1
        self.assertEqual(lad.journal[1]["locked"], ["U1"])

    def test_callable_locks_out_resolved_after_fn(self):
        st = _Board()

        def place_all(s):
            s.P["A"] = (0.0, 0.0, 0.0)
            s.P["B"] = (1.0, 0.0, 0.0)
        # lock whatever the pass placed (resolved AFTER fn)
        p = Pass("p", place_all, locks_out=lambda s: list(s.P.keys()))
        lad = PassLadder([p], _positions)
        lad.run(st)
        self.assertEqual(set(lad.locked_refs()), {"A", "B"})


class TestGateHalt(unittest.TestCase):
    def _passes(self, ran):
        def mk(name):
            def fn(_st):
                ran.append(name)
            return fn
        return mk

    def test_failing_enabled_gate_halts(self):
        ran = []
        mk = self._passes(ran)
        st = _Board()

        def bad_gate(_st):
            return {"ok": False, "violations": ["kelvin-reach:U10", "tht-backside:U11"]}

        passes = [
            Pass("p_first", mk("p_first"), phase="P2"),
            Pass("p_gate", mk("p_gate"), gate=bad_gate, gate_enabled=True, phase="P3"),
            Pass("p_after", mk("p_after"), phase="P4"),          # must NOT run
        ]
        lad = PassLadder(passes, _positions)
        with self.assertRaises(GateFailure) as cm:
            lad.run(st)
        e = cm.exception
        self.assertEqual(e.pass_name, "p_gate")
        self.assertEqual(e.violations, ["kelvin-reach:U10", "tht-backside:U11"])
        self.assertIn("p_gate", str(e))
        self.assertEqual(ran, ["p_first", "p_gate"])            # p_after never started
        # the failing gate result is recorded in the journal
        self.assertEqual(lad.journal[-1]["pass"], "p_gate")
        self.assertFalse(lad.journal[-1]["gate"]["ok"])
        self.assertEqual(lad.journal[-1]["gate"]["violations"],
                         ["kelvin-reach:U10", "tht-backside:U11"])

    def test_passing_enabled_gate_continues(self):
        ran = []
        mk = self._passes(ran)
        st = _Board()
        passes = [
            Pass("p_gate", mk("p_gate"), gate=lambda _s: {"ok": True, "violations": []},
                 gate_enabled=True),
            Pass("p_after", mk("p_after")),
        ]
        PassLadder(passes, _positions).run(st)
        self.assertEqual(ran, ["p_gate", "p_after"])

    def test_disabled_gate_is_inert_by_default(self):
        # a gate that WOULD fail but is gate_enabled=False must NOT halt (default eval_gates=None
        # -> only enabled gates are even evaluated). This is the ablation-discipline default.
        ran = []
        mk = self._passes(ran)
        st = _Board()
        passes = [
            Pass("p_gate", mk("p_gate"),
                 gate=lambda _s: {"ok": False, "violations": ["x"]}, gate_enabled=False),
            Pass("p_after", mk("p_after")),
        ]
        lad = PassLadder(passes, _positions)
        lad.run(st)
        self.assertEqual(ran, ["p_gate", "p_after"])            # ran to completion
        self.assertIsNone(lad.journal[0]["gate"])               # not even evaluated

    def test_eval_gates_records_without_halting(self):
        # eval_gates=True EVALUATES every gate for the journal, but a disabled gate still does
        # NOT halt -- observability without enforcement.
        st = _Board()
        passes = [
            Pass("p_gate", lambda _s: None,
                 gate=lambda _s: {"ok": False, "violations": ["obs"]}, gate_enabled=False),
            Pass("p_after", lambda _s: None),
        ]
        lad = PassLadder(passes, _positions, eval_gates=True)
        lad.run(st)                                             # no raise
        self.assertEqual(lad.journal[0]["gate"]["violations"], ["obs"])
        self.assertEqual(len(lad.journal), 2)


class TestJournal(unittest.TestCase):
    def test_journal_serialises_to_json(self):
        st = _Board()
        passes = [
            Pass("p_a", _place("J1", (10.0, 5.0, 0.0)), locks_out=["J1"], phase="P2"),
            Pass("p_b", _place("U1", (20.0, 20.0, 0.0)),
                 gate=lambda _s: {"ok": True, "violations": []}, gate_enabled=True, phase="P3"),
        ]
        lad = PassLadder(passes, _positions)
        journal = lad.run(st)
        s = journal_to_json(journal)
        back = json.loads(s)                                   # must round-trip
        self.assertEqual(len(back), 2)
        self.assertEqual(back[0]["pass"], "p_a")
        self.assertEqual(back[0]["placed"], ["J1"])
        self.assertEqual(back[0]["locked"], ["J1"])
        self.assertEqual(back[0]["phase"], "P2")
        self.assertIn("dt_ms", back[0])
        self.assertEqual(back[1]["gate"], {"ok": True, "violations": []})

    def test_placed_vs_moved_tracking(self):
        st = _Board()
        passes = [
            Pass("p_a", _place("J1", (1.0, 1.0, 0.0))),
            Pass("p_b", _move("J1", (2.0, 2.0, 0.0))),          # moves J1 (not locked) -> 'moved'
        ]
        lad = PassLadder(passes, _positions)
        lad.run(st)
        self.assertEqual(lad.journal[0]["placed"], ["J1"])
        self.assertEqual(lad.journal[0]["moved"], [])
        self.assertEqual(lad.journal[1]["placed"], [])
        self.assertEqual(lad.journal[1]["moved"], ["J1"])

    def test_exception_in_fn_is_journaled_then_reraised(self):
        st = _Board()

        def boom(_s):
            raise ValueError("kaboom")
        lad = PassLadder([Pass("p_boom", boom)], _positions)
        with self.assertRaises(ValueError):
            lad.run(st)
        self.assertEqual(lad.journal[-1]["pass"], "p_boom")
        self.assertIn("ValueError: kaboom", lad.journal[-1]["error"])


class TestPosEq(unittest.TestCase):
    def test_pos_eq_semantics(self):
        self.assertTrue(_pos_eq((1.0, 2.0, 0.0), (1.0, 2.0, 0.0)))
        self.assertFalse(_pos_eq((1.0, 2.0, 0.0), (1.0, 2.0, 90.0)))
        self.assertTrue(_pos_eq(None, None))
        self.assertFalse(_pos_eq(None, (1.0, 2.0, 0.0)))


if __name__ == "__main__":
    unittest.main()
