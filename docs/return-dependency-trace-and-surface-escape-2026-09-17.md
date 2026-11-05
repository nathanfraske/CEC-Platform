# Return-dependency tracing and surface escape correctness

## What was actually wrong

The missing Hub `decoupler_ground_territory_reseat` family was **not** a stale
position or rounding bug. The read-only native trace measured zero coordinate
error and verified the complete bound power-reservation identity. U7 and C15
are fixed endpoints of that frozen power plan. All 166 measured seat proofs
therefore stop at a fixed terminal. Disabling that constraint in a diagnostic
produces 48 proposals; none is admissible authority to move those endpoints.
No fixed constraint, power bus, pad size, interface, or outline was changed.

The production defect was missing proposal-domain evidence. A family could
silently produce zero moves, leaving the final certificate to say only that
placement repair was needed. `cec_local_return_feedback.move_specs` now records
the exact refusal category, counts and up to 16 deduplicated terminal/cell
samples. Fixed terminals, fixed macro members, stale positions, missing geometry
and bounded-motion refusals remain distinct. The production craft dispatcher
persists this data into both round logs and its final blocker certificate,
including the measured reservation identity but not its large geometry dump.
No selection order, admission gate or frozen-plan permission changed.

A zero-physical-trial production replay confirms this end-to-end handoff without
repeating the Hub's 125 previously visited poses. The proper next target is the
fixed power-terminal/local-return dependency and its upstream construction
order, not more capacitor-position trials against the same fixed endpoint.
This is not a proof that every legal ground topology is impossible, nor blanket
permission to reroute a priority power bus.

## Separate generalized layer repair

Loaded native KiCad fixtures reproduced the same `PAD.GetLayer()` ambiguity in
the **neighbor escape sampler**: B.Cu-only SMD lands were sampled on F.Cu. The
shared `cec_return_escape.smd_surface_layer` now resolves actual unique outer
copper membership. Both neighbor-ray clearance and local ground dogbones use
this helper. Ambiguous/non-surface SMDs cannot invent a front-side escape or
receive the compact off-pad process exception. Unresolved sampled terminals
are explicitly counted, not asserted unroutable.

Five new native cases failed before this correction: two saved/reloaded,
translated back-side fixtures and three missing/ambiguous/non-surface cases.
The existing native copper, netclass, process, and future-power checks remain.
Current production-suite surface inventories contain no B.Cu-only SMDs, so this
repair is supported cross-surface coverage, **not a claimed current-board speed
or connectivity improvement**. Mechanical/multilayer pads are reported separately.

## Validation and honest board result

- `build/feedback-surface-red-tests-20260917.log`: 5 expected failures, 58 passes.
- `build/feedback-surface-tests-20260917.log`: 77 passes after repair.
- `build/feedback-surface-broad-tests-20260917.log`: **486 passes**, 50.76 seconds.
- `build/ground-feedback-trace-20260917.json`: exact missing-family forensic.
- `build/feedback-surface-suite-20260917/completed-report.json`: concurrent
  current-suite replay and historical PCIe2 control parity. The initial reporting
  adapter wrongly requested a nonexistent `drc_count` from the residual survey;
  only that PCIe2 report was rerun after correcting the adapter. Original error
  evidence is retained; it was not a board failure or a missing native DRC run.

All six current PCB/source hierarchies and protected copper remain unchanged.
PCIe2 still has five opens. PCIe3 retains its physical pass; VHP retains a physical
pass with its existing local-cell obligation deferred to the mandatory route
stage. Hub retains three craft blockers. EPS/ATX remain interface-ECO holds
pending the paired-interface decision. Historical PCIe2 board/hash/probe parity
passes. No new board has been promoted and no identical image is presented as
a new route result. Keep `build/additive-first-next-inputs-20260917.json` current.

## Completed bounded routing-domain experiment and generic scope repair

`build/priority-tier-continuation-20260917` runs PCIe3 and VHP concurrently through
the existing precision compiler **and then** the existing atomic staged-router
fallback on the refused pair nets. This is a private diagnostic, not a placement
gate bypass or production pipeline integration. One seed, one tier-only attempt,
16 backend threads, 90-second backend timeout and no adaptive child tiers are
used. All original power guards, existing copper and independent pair-physics
checks remain active. Disposable backend scratch is cleaned by the existing
wrapper. Engine scripts stay fixed until both workers finish.

The purpose is to test the advertised fallback path before another precision-only
placement wave. A connected route is not sufficient: native geometry, pair
physics, protected copper and complete-board checks still govern any promotion.
The experiment completed with no admitted candidate. A diagnostic path-type
adapter error occurred after both precision checkpoints were saved; the staged
attempts resumed from those exact checkpoints rather than recomputing them.
The initial adapter receipt remains at `report.json`; the recovered outcome is
`completed-report.json`. Neither failure modified a canonical source.

The underlying staged router did run; neither pair passed its independent gate:

- PCIe3: the CAN connector tier routed one member but left the other without
  tracks. Reported skew was 28.83 mm against the existing 4 mm limit, with
  asymmetric transitions and no coupled-route coverage.
- VHP: USB tracks failed matched transitions (one spacing 4.071 mm against the
  existing 1.50 mm limit), four local ground returns, reference coverage
  (90.1% versus 95%) and coupled coverage (29.8% versus 80%).

These are the project's existing admission thresholds, not newly invented
universal PCB standards. Rejected tier copper was discarded and the parent
retained. Merely permitting that backend later in the pipeline is therefore
not demonstrated closure; the paired path construction still needs work.

### Failures found and repaired while observing those outputs

`cec_pair_fallback` previously saved its `staged` receipt only after all later
checks succeeded. Once a tier was rejected, its parent remained open and the
wrapper's final error could obscure the actual coupling/transition failure.
The receipt is now saved immediately, on both success and refusal.

The wrapper also called the return-via synthesizer on **all pairs**, even for a
single requested tier. The VHP USB-only attempt changed six unrelated CAN copper
objects and introduced non-octilinear CAN topology findings in its rejected
scratch result. Return repair is now limited to the exact requested atomic
net groups; the independent final all-pair check is still global.

Saved-native A/B proof in `build/fallback-scope-native-proof-20260917.json`:
VHP outside-target changes **6 -> 0**, all 506 original copper objects preserved
in the corrected finishing step; PCIe3 **0 -> 0**, all 68 objects preserved.
No failing scratch board was promoted before or after the fix. This is a real
repair-scope regression fix, not a reduction in open connections.

Final concurrent cohort:
`build/priority-tier-scope-verify-20260917/report.json`. Both pair tiers remain
refused, now with the full causal tier report retained. All six canonical
source/hierarchy identities, other-family gates and historical PCIe2 control
parity pass. **528 tests pass in 49.52 seconds** in the combined suite:
`build/return-surface-fallback-final-tests-20260917.log`.

All workers finished. No current board or review image is newly promoted.
Keep the existing canonical manifest and Hub 125-pose history. Next useful work:
paired transition/corridor construction for the recorded CAN/USB failures, and
upstream fixed power-terminal/local-return co-design for Hub. EPS/ATX still
await the paired-interface choice. Do not repeat the same failed staged seed
or weaken coupling, reference-plane, width, via or power-ownership checks.
The existing 15-minute review heartbeat is verified active; no duplicate was
created. Port 8090 returned HTTP 200 from Windows and about 64 GiB remains free.

## Follow-through: oracle handoff also preserves the nested failure

A subsequent call-chain audit found a second evidence-loss boundary. Although
the atomic wrapper now retains its rejected tier, `route_oracle_grade` raised
on `ok=False` before copying those attempts into its own result. Its `_fail`
payload omitted the wrapper result and could retain similarly named locals from
an earlier stage. The source oracle now stores attempts before the refusal,
passes the full fallback receipt into failure evidence, and explicitly clears
per-attempt artifact/staged/return/quality variables before dispatch.

Three isolated execution regressions use the **actual parsed production branch**
(not a reimplementation), including its actual `_trace`, `_fail` and final
failure-dictionary builder. Only the route backend and artifact sanitizer are
replaced. They cover a refused report, an exception before any report, and
retention through final blocker evidence, stage trace and causal chain. The
initial harness missed a local `_protect` initializer; the corrected red receipt
is `build/pair-handoff-red-tests-v2-20260917.log`. **59 focused tests pass** in
`build/pair-handoff-final-tests-20260917.log` (overlapping prior suites, not an
additional 59 unique tests on top of the earlier 528).

`build/pair-handoff-suite-20260917/report.json` replays both saved native PCIe3/VHP
fallback receipts through that production handoff. All three evidence paths
retain the original nested physical failures. It does **not rerun the router**
or claim a new full-pipeline result. All six canonical source/hierarchy hashes
and historical PCIe2 board/hash/probe parity remain unchanged. Core audit passes;
legacy findings remain 23 / 380. No workers, new board candidate, image or
connectivity improvement resulted from this logging-only continuation.
