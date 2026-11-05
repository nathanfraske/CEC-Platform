# Frozen power via replay: identity, self-collision and growth

## Verified result

The 15:10:23Z cleanup follow-up finished at **15:14:11Z**, without entering
backend routing. Both PCIe2 seeds stopped at `local_power_prefix`: frozen
via reseating exhausted its lattice. Placement and preflight passed; the
previous cleanup change was **not** exercised end-to-end by this failed run.
Its source and engine guards passed, and all descendants exited before edits.

The selected current PCIe2 board remains SHA
`905f961c625743053efccb6b46a73f4115aef31f2bcc819db8b161d682b03b22`,
**0 DRC / 10 opens**, 726 tracks, 382 vias, 1572.851 mm. It is not fab-ready.

## Root cause established from native artifacts

`build/frozen-via-replay-probe-20260915.json` compares the prior 12-open
winner, current 10-open winner, and failed local-power-prefix input. The last
is byte-identical to the current winner. In all three, **every one of the 56
declared frozen field vias already exists exactly once**: same net and
nanometre seat, locked, through span, 0.5 mm drill, 0.9 mm copper on every
enabled copper layer.

The reseater included those existing instances in its obstacle ledger without
excluding the candidate's own identity. It treated each as a collision,
shifted the declared field and added another 56 barrels, keeping the originals.
That explains **56 of the 61 added vias** between the last two routed winners
(14 extra on each of four current nets). The next replay ran out of room.
This was a replay/materialization defect, not evidence the board needed that
many additional power vias.

## Board-neutral repair

- Resolve existing instances by exact net, nanometre position, lock, drill,
  through span and all-layer copper diameter. No board/refdes/coordinate
  exception is used.
- Exempt only the exact matched UUID from its own obstacle test. Other
  barrels, foreign tracks and pad/assembly exclusions still apply.
- Reuse qualified instances. Refuse ambiguous duplicates, duplicate requests,
  and real conflicts involving already materialized locked authority. Do not
  move locked power to accommodate a later conflicting producer.
- Preserve the old `add_overunder_vias` return convention for callers counting
  newly added objects. The frozen replay boundary explicitly counts both new
  and reused objects; evidence distinguishes these counts and refusal causes.
- Do not unfill zones on reuse-only calls. Retain the stale-ground-fill defense
  before genuinely adding a new barrel.

This prevents new duplication. **No accumulated surplus vias were removed**:
that needs source/proposal provenance and a qualified copper/connectivity
transaction, not a count-based deletion heuristic.

## Validation

- `build/frozen-via-final-tests-20260915.log`: **947 passed**, 53 subtests,
  three pre-existing skips, 110.98 s.
- `build/frozen-via-boundary-tests-20260915.log`: **18 passed**, including an
  additional native producer-boundary regression. Covers renamed/translated
  fixtures, repeated replay, genuine new fields, wrong net/drill/diameter/lock/
  span, distinct nearby barrels, foreign copper on three layers, duplicate
  requests/instances, and immutable out-of-overlap authority.
- `build/frozen-via-suite-replay-20260915/report.json`: all six current family
  source/hierarchy checks unchanged. Hub materializes 22 field vias once,
  PCIe3 84 once, PCIe2 reuses all 56; a second call adds zero in all three.
  These Hub/PCIe3 changes exist only in disposable native diagnostics, not
  promoted placements. VHP has no sibling frozen state at this placement
  stage; EPS/ATX correctly refuse their unadmitted interface ECO.
- `build/frozen-via-suite-replay-20260915/full-prefix-report.json`: the actual
  previously failing PCIe2 producer passes **unmocked native exact admission
  twice**, with all 382 via UUIDs retained, zero additions, and both output
  boards byte-identical to SHA 905f961c6257. Native warnings remain in the log;
  no warning is counted as an admission result.
- `build/frozen-via-control-comparison-20260915.json`: protected historical
  PCIe2 board hash, whole-board regression and every probe unchanged. Only
  generalization evidence differs. The control's old strict release holds
  remain; it was not newly released by this test.
- `build/frozen-via-generality-20260915.json`: 72 core modules / zero core
  findings, but **23 broader physical and 380 runtime findings remain**.
  This is not a claim the entire legacy pipeline has become generic.

## Continuation

Use the explicit six-family lineage in `build/locked-reconcile-inputs-20260915.json`.
The affected PCIe2 bounded follow-up is `build/frozen-via-followup-suite-20260915`.
Do not repeat unchanged Hub/PCIe3 local-return searches, VHP's pair-escape
failure, or EPS/ATX's unadmitted coupled-interface placement. Their outstanding
work remains on the suite ledger. Keep shared scripts fixed while the new
cohort or any descendants are live; inspect its actual status before resuming.

The next read-only investigation can attribute the remaining local-return
failures and retained-copper preflight demand overhead. Never prune demands
without proving that exact corresponding copper survives downstream routing.

**15:54Z observation:** cohort started 15:46:32Z, PCIe2 PID 328958, parent
session 75545. Placement passed 30.516 s; preflight passed 141.146 s. Candidate
0's previously failing local-power-prefix now passes in 16.442 s, keeping SHA
905f and 0 DRC / 10 opens. Its first backend router pass completed in 74.328 s;
import/cleanup is active. This is not yet a selected routed improvement.
See `local-cell-ordering-investigation-2026-09-15.md` for the concurrent
Hub/PCIe3 read-only experiments and next bounded generic repair hypothesis.
