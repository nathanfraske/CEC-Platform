#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""cec_passes -- the PASS-RUNNER SKELETON for the pass-form placement/routing ladder
(docs/pass-form-plan.md, stage S1).

The owner's model (2026-07-08): "do placements and routing like a human would ... in a
pass form" -- ordered passes with PROGRESSIVE LOCKING, each ending by locking its output so
later passes fit within and cannot undo it (plan §3.1), and each with its own done-criteria
gate (plan §3.2).

This module is the framework only. A `Pass` declares (name, fn, locks_out, gate); a
`PassLadder` threads a growing LOCKED set through the sequence, records a JSON-able per-pass
journal (what each pass placed / moved / locked, plus gate results), and -- when
`enforce_locks` is ON -- refuses to let a later pass move a ref an earlier pass locked.

S1 invariants (do NOT break without the ablation discipline):
  * `enforce_locks` defaults OFF and every pass's `gate_enabled` defaults OFF, so running a
    ladder is BYTE-IDENTICAL to the un-laddered call order -- the passes are only
    RE-SEQUENCED under the runner, never changed (the golden-safety guarantee).
  * The journal is composed of plain str/num/bool/list/dict so it serialises to JSON: it
    becomes the wave verdict's placement provenance.
  * Turning a lock or a gate on is later fixed-seed ablation work -- one lever at a time --
    NOT a default here.
"""
import math
import time
import copy


# ------------------------------------------------------------------ errors (loud, named)
class LockViolation(RuntimeError):
    """A later pass moved a ref an earlier pass LOCKED (plan §3.1). Raised only when the
    ladder runs with enforce_locks=True."""

    def __init__(self, pass_name, ref, locked_pos, moved_to):
        self.pass_name = pass_name
        self.ref = ref
        self.locked_pos = locked_pos
        self.moved_to = moved_to
        super().__init__(
            "PASS-LOCK VIOLATION: pass %r moved LOCKED ref %r from %r to %r -- a later "
            "pass may not move a ref an earlier pass locked (docs/pass-form-plan.md "
            "§3.1). Fix by escalating a snag to the pass that OWNS %r, never by moving "
            "it here." % (pass_name, ref, locked_pos, moved_to, ref))

    def __reduce__(self):
        # spawn-pool transport (measured 2026-07-12: a LockViolation raised in a wave
        # worker failed to UNPICKLE in the parent -- multi-arg __init__ vs the 1-arg
        # RuntimeError default -- so the pool reported an opaque BrokenProcessPool
        # instead of the named violation).
        return (LockViolation, (self.pass_name, self.ref, self.locked_pos, self.moved_to))


class GateFailure(RuntimeError):
    """A pass did not meet its own done-criteria; the next pass does not start (plan §3.2).
    Raised only when the failing pass has gate_enabled=True."""

    def __init__(self, pass_name, violations):
        self.pass_name = pass_name
        self.violations = list(violations or [])
        super().__init__(
            "PASS-GATE FAILED: pass %r did not meet its done-criteria; violations=%r "
            "(docs/pass-form-plan.md §3.2 -- the next pass does not start)."
            % (pass_name, self.violations))

    def __reduce__(self):
        return (GateFailure, (self.pass_name, self.violations))


class CellOwnershipViolation(RuntimeError):
    """A downstream pass invalidated the geometry consumed by an owning cell."""

    def __init__(self, pass_name, owner_pass, cell, ref, owned_pos, moved_to):
        self.pass_name, self.owner_pass = pass_name, owner_pass
        self.cell, self.ref = cell, ref
        self.owned_pos, self.moved_to = owned_pos, moved_to
        super().__init__(
            "CELL-OWNERSHIP VIOLATION: pass %r changed %r in cell %r owned by %r "
            "from %r to %r; replan the complete cell at its owning stage"
            % (pass_name, ref, cell, owner_pass, owned_pos, moved_to))

    def __reduce__(self):
        return (CellOwnershipViolation, (self.pass_name, self.owner_pass,
                self.cell, self.ref, self.owned_pos, self.moved_to),
                {"failure_evidence": getattr(self, "failure_evidence", {})})


# ------------------------------------------------------------------ position equality
def _pos_eq(a, b):
    """Physical equality for ``(x, y, rotation)`` placement tuples.

    KiCad and the placement transforms may serialize the same orientation as
    ``-90`` or ``270`` and can introduce sub-nanometre float noise on an
    otherwise unchanged coordinate.  Those are not physical moves and must not
    trip progressive locks.  The tolerance is 10 nm; a real grid move remains
    many orders of magnitude larger.
    """
    if a is b:
        return True
    if a is None or b is None:
        return a is b
    try:
        left, right = tuple(a), tuple(b)
    except TypeError:
        return a == b
    if len(left) == len(right) == 3:
        try:
            xy_equal = all(math.isclose(float(left[index]), float(right[index]),
                                        rel_tol=0.0, abs_tol=1e-5)
                           for index in (0, 1))
            angle_delta = ((float(left[2]) - float(right[2]) + 180.0)
                           % 360.0) - 180.0
            return xy_equal and abs(angle_delta) <= 1e-6
        except (TypeError, ValueError):
            pass
    return left == right


# ------------------------------------------------------------------ Pass declaration
class Pass:
    """One ladder stage.

    name         -- stable id used in the journal.
    fn           -- callable(state) that does the stage's work (mutates the placement the
                    ladder observes via its `positions` accessor). Its return value is ignored.
    locks_out    -- refs this pass LOCKS on completion. A static iterable, or a
                    callable(state) -> iterable resolved AFTER fn runs (so a pass can lock the
                    refs it just placed). First lock wins -> stable provenance.
    gate         -- callable(state) -> {"ok": bool, "violations": [...]} | None. The pass's
                    done-criteria (plan §3.2). None = no gate.
    gate_enabled -- default False. A gate is only ENFORCED (can halt the ladder) when True;
                    off, its result is still recorded in the journal if the gate is provided
                    and the ladder is asked to evaluate it. Flipping this on is ablation work.
    phase        -- the plan's P-phase label (P0..P8 / R0..R10), journal metadata only.
    owned_cells_out -- mapping cell id -> member refs, or callable(state) -> mapping.
                    Snapshots persistent geometry consumed by this stage's copper.
                    Members also enter ordinary locks, but re-ratifying those locks
                    cannot rewrite cell ownership. Replan at the owning stage;
                    downstream passes cannot move even the complete stamped cell.
    """

    __slots__ = ("name", "fn", "locks_out", "owned_cells_out", "gate", "gate_enabled", "phase", "doc")

    def __init__(self, name, fn, *, locks_out=(), gate=None, gate_enabled=False,
                 phase="", doc="", owned_cells_out=None):
        if not callable(fn):
            raise TypeError("Pass %r: fn must be callable" % name)
        if gate is not None and not callable(gate):
            raise TypeError("Pass %r: gate must be callable or None" % name)
        self.name = str(name)
        self.fn = fn
        self.locks_out = locks_out
        self.owned_cells_out = owned_cells_out
        self.gate = gate
        self.gate_enabled = bool(gate_enabled)
        self.phase = str(phase)
        self.doc = str(doc)

    def resolve_locks(self, state):
        lo = self.locks_out
        if callable(lo):
            lo = lo(state)
        return list(lo or ())

    def resolve_owned_cells(self, state):
        cells = self.owned_cells_out
        if callable(cells):
            cells = cells(state)
        return {str(cell): sorted(set(refs)) for cell, refs in (cells or {}).items()}

    def __repr__(self):
        return "Pass(%r, phase=%r, gate=%s, gate_enabled=%s)" % (
            self.name, self.phase, self.gate is not None, self.gate_enabled)


# ------------------------------------------------------------------ the runner
class PassLadder:
    """Runs a sequence of Passes, threading a LOCKED set and recording a journal.

    positions -- callable(state) -> {ref: (x, y, rot)} : the CURRENT placement the ladder
                 observes to journal what moved and to enforce locks. May return None/{} for
                 stages that run before any placement dict exists.
    enforce_locks -- default False. When True, after each pass any ref that was locked by an
                 earlier pass and is now at a different position raises LockViolation.
    eval_gates -- default None -> a gate is evaluated iff its own gate_enabled is True. Pass
                 True to EVALUATE every provided gate (for the journal) while still only
                 HALTING on a gate whose gate_enabled is True; pass False to skip all gates.
    """

    def __init__(self, passes, positions, *, enforce_locks=False, eval_gates=None):
        self.passes = list(passes)
        self._positions = positions
        self.enforce_locks = bool(enforce_locks)
        self.eval_gates = eval_gates
        self.locked = {}          # ref -> locked (x,y,rot); first lock wins
        self._owned_cells = {}    # (owning pass, cell id) -> immutable pose snapshot
        self.journal = []

    # -- observation -------------------------------------------------------------
    def _pos(self, state):
        p = self._positions(state)
        return p if p else {}

    def _should_eval(self, p):
        if p.gate is None:
            return False
        if self.eval_gates is None:
            return p.gate_enabled
        return bool(self.eval_gates)

    def _record(self, p, before, after, *, gate, newly, dt, error=None):
        placed = sorted(r for r in after if r not in before)
        moved = sorted(r for r in after
                       if r in before and not _pos_eq(after[r], before[r]))
        entry = {
            "pass": p.name,
            "phase": p.phase,
            "placed": placed,
            "moved": moved,
            "locked": list(newly),
            "n_after": len(after),
            "gate_enabled": bool(p.gate_enabled),
            "gate": _jsonable_gate(gate),
            "dt_ms": round(dt * 1000.0, 3),
        }
        if error is not None:
            entry["error"] = error
        self.journal.append(entry)
        return entry

    # -- run ---------------------------------------------------------------------
    def run(self, state=None):
        """Execute every pass in order. Returns the journal (a list of JSON-able dicts).
        Raises LockViolation / GateFailure only under the opt-in enforcement above."""
        for p in self.passes:
            before = dict(self._pos(state))
            t0 = time.perf_counter()
            try:
                p.fn(state)
            except Exception as e:                       # noqa: BLE001 -- journal then re-raise
                self._record(p, before, self._pos(state), gate=None, newly=[],
                             dt=time.perf_counter() - t0,
                             error="%s: %s" % (type(e).__name__, e))
                raise
            after = self._pos(state)
            # Check persistent cell authority before the mutable progressive
            # lock map. An intent may re-ratify a loose placement lock, but
            # that must not silently authorize drift of downstream copper.
            cells_out = p.resolve_owned_cells(state)
            if self.enforce_locks:
                for (owner, cell), poses in self._owned_cells.items():
                    for ref, pose in poses.items():
                        current = after.get(ref)
                        if not _pos_eq(current, pose):
                            self._raise_cell_violation(
                                p, before, after, t0, owner, cell, ref,
                                pose, current, poses)
                for cell, refs in cells_out.items():
                    for ref in refs:
                        if after.get(ref) is None:
                            self._raise_cell_violation(
                                p, before, after, t0, p.name, cell, ref,
                                None, None, refs)
            # LOCK ENFORCEMENT (opt-in): a locked ref may not have moved during this pass.
            if self.enforce_locks and self.locked:
                for r, lp in self.locked.items():
                    cur = after.get(r)
                    if not _pos_eq(cur, lp):
                        self._record(p, before, after, gate=None, newly=[],
                                     dt=time.perf_counter() - t0,
                                     error="lock-violation:%s" % r)
                        raise LockViolation(p.name, r, lp, cur)
            # this pass's locks join the set (first lock wins -> stable provenance).
            newly = []
            owned_refs = [ref for refs in cells_out.values() for ref in refs]
            for r in p.resolve_locks(state) + owned_refs:
                if r in after and r not in self.locked:
                    self.locked[r] = after[r]
                    newly.append(r)
            for cell, refs in cells_out.items():
                self._owned_cells.setdefault((p.name, cell), {
                    ref: tuple(after[ref]) for ref in refs if ref in after})
            # GATE (opt-in): evaluate + record; HALT only when the failing gate is enabled.
            gate = p.gate(state) if self._should_eval(p) else None
            event = self._record(p, before, after, gate=gate, newly=newly,
                                 dt=time.perf_counter() - t0)
            if cells_out:
                event["owned_cells"] = cells_out
            if p.gate_enabled and gate is not None and not gate.get("ok", True):
                raise GateFailure(p.name, gate.get("violations"))
        return self.journal

    def _raise_cell_violation(self, p, before, after, t0, owner, cell,
                              ref, pose, current, members):
        event = self._record(p, before, after, gate=None, newly=[],
                             dt=time.perf_counter() - t0,
                             error="cell-ownership-violation:%s" % ref)
        event["ownership_violation"] = {
            "cell": cell, "owner_pass": owner, "repair_stage": owner,
            "offending_pass": p.name, "ref": ref, "members": sorted(members),
            "owned_pose": pose, "observed_pose": current,
        }
        error = CellOwnershipViolation(p.name, owner, cell, ref, pose, current)
        error.failure_evidence = {
            "kind": "placement_cell_ownership",
            "certificate": copy.deepcopy(event["ownership_violation"]),
            "placement_journal": copy.deepcopy(self.journal),
        }
        raise error

    # -- convenience -------------------------------------------------------------
    def locked_refs(self):
        return dict(self.locked)


def _jsonable_gate(gate):
    """Coerce a gate result to plain JSON types (or None). A gate must return
    {"ok": bool, "violations": [...]} or None; anything else is stringified defensively."""
    if gate is None:
        return None
    if isinstance(gate, dict):
        out = {"ok": bool(gate.get("ok", True)),
               "violations": list(gate.get("violations", []) or [])}
        for k, v in gate.items():
            if k in ("ok", "violations"):
                continue
            out[k] = v if isinstance(v, (str, int, float, bool, list, dict, type(None))) \
                else repr(v)
        return out
    return {"ok": False, "violations": [repr(gate)]}


def journal_to_json(journal):
    """The journal is already JSON-able by construction; this validates that and returns a
    json string (used by the wave verdict's placement-provenance serialiser)."""
    import json
    return json.dumps(journal, default=str, sort_keys=False)
