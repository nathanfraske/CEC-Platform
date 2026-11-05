# Local-return feedback and frozen-placement transaction — 2026-09-15

## Completed parallel pass

`build/frozen-pi-followup-suite-20260915/suite.json` finished **11:08:09Z**.
Hub took 169.27 s (156.35-s placement); PCIe3 took 430.40 s (417.6-s
placement). Both stopped at placement. Source/hierarchy and engine guards
passed. There is **no new admitted routing output or fab candidate**.

Hub's search accepted two local proposals and reduced its visible craft
violations, but the final frozen-power synchronization rejected two dependent
moves. Its proposed board `b3631d615a3e...` therefore has a stale placement
snapshot (five mismatches); this is not a qualified improvement. PCIe3 retained
the exact input `d97d5dbc9336...`. Its three native local-access failures were
incorrectly deferred to the same local constructor in routing, so its initial
placement policy said `needs_repair=false` and skipped craft repair entirely.
The priority route gate subsequently blocked it. Neither board bypassed final
admission, but this was wasted scheduling and a misleading proposal/commit
boundary.

The actual completed-pass image was inspected, not inferred from an old board:
`C:/Users/Admin/Documents/CEC-Board-Reviews/frozen-pi-followup-suite-20260915/all-boards-d352b18ec4100fa4.png`.
Both panels are explicitly BLOCKED placement reviews. The Hub archive ID is
`pass-frozen-pi-followup-suite-20260915-hub-standard-rev2-51dc4eb6a3`; the PCIe3
ID is `pass-frozen-pi-followup-suite-20260915-pcie-8pin-3port-8688315b1e`.
Windows localhost:8090 responded and the Hub ID was present. The earlier
018276 gallery was only an intermediate image with PCIe3 still running; do
not use it as the final pass picture.

## Three generic changes

1. `cec_local_return_feedback.failed_searches` consumes structured, exhausted
   native ground-return certificates only for a currently failed cell. Those
   failures cannot be deferred to the identical constructor. They enter
   `return_path_placement` and make resumed placement repair mandatory.
   An unconstructed cell without that failure proof can still reach its
   mandatory routing stage. Exhaustion is a bounded-search result, not a proof
   that the whole board is impossible.
2. The same module supplies bounded, geometry-derived axis-exit proposals for
   a return via blocked by a power reservation, including inner layers. A
   translated owner retains every assigned capacitor as one rigid cell;
   capacitor-only options are also tried when appropriate. Measured via
   diameter/clearance plus 0.05-mm search margin determine the displacement.
   Defaults: 12-mm maximum displacement, 48 proposals; all are policy
   parameters. Stale coordinates, incomplete regions, fixed members and
   nonfinite values are refused. No power polygon is moved or clipped, and
   native full-board craft/copper/outline admission remains mandatory.
3. `_commit_frozen_craft_repair` snapshots the complete existing
   placement-authority family before materialization. Rejected state sync or
   exceptions restore it byte-for-byte. Rejected moves remain diagnostic
   proposals, but no longer count as retained accepted changes. New sibling
   authority files created by a failed attempt are removed during rollback;
   source boards are not touched.

No board/refdes/coordinate selector, power-budget change, dimension increase,
or manufacturing waiver was introduced.

## Evidence

- `build/local-return-final-tests-v2-20260915.log`: **373 passed in 94.93 s**
  in the final focused/general regression run. Covers native
  authority, full pipeline, placement craft, local/global handoff,
  generalization and new feedback/transaction tests. The earlier 369-test run
  passed before the four transaction tests were added; do not add overlapping
  counts. A first command with an incorrect test filename ran no tests.
- `build/local-return-replay-v2-20260915/report.json`: fresh native local-PI
  replay of the explicit six-family plan, with source/engine signatures intact.
  Hub exposes four exhausted cells and 18 proposals. PCIe3 exposes two
  exhausted cells in this replay and eight proposals; its previous completed
  cohort had three failed access rows. Do not equate failed-cell counts with
  independent DRC/open counts. PCIe2 local PI passes with zero proposals.
  VHP has its prior non-ground local-access diagnostic and no proposals from
  this rule. EPS retains its unmoved placement/mating obligations. ATX fails
  closed on unavailable required current power authority.
- `build/local-return-control-comparison-20260915.json`: protected historical
  PCIe2 PCB SHA, entire `board_regression`, and all `probes` exactly equal the
  prior baseline after the final transaction edit. Its existing stricter
  release failures remain; this is non-regression, not fresh fab admission.
- `build/local-return-generality-20260915.json`: **68 core modules / zero core
  violations**. The broader runtime still has **380 findings**; no claim that
  the entire legacy runtime is generic or release-qualified.

The first native harness used the wrong `Placement.P` attribute and produced
adapter errors; that `local-return-replay-20260915` report is not evidence of
board failure or a successful replay. The corrected v2 uses `Placement.pos`.

## Next bounded cohort

`tmp/local_return_followup_20260915.py` reuses the exact input plan
`build/frozen-pi-followup-inputs-20260915.json`, deliberately NOT the rejected
Hub b363 proposal. The shared gate/proposal/transaction changes are the
experimental variable. Hub and PCIe3 run concurrently with two workers each,
12 trials/two craft rounds, eight routing passes, 1800-s board bounds,
1200-s priority repair allowance, 480-s pair allowance and a 2100-s parent
process-group deadline; 16-GiB free floor remains. Do not edit shared engines
while either board or a native descendant is live.

Dispatched **11:39:42Z** as
`build/local-return-feedback-suite-20260915/suite.json`: Hub PID **153173**,
PCIe3 PID **153174**. Both processes/journals confirmed running. Parent shell
session 54378; engine files must remain fixed until completion. Free space at
dispatch: 68 GiB. Completed-stage/pass publication remains enabled.

The other four families remain in the reviewed suite: no identical exhausted
VHP USB or PCIe2 route attempt is repeated, and EPS/ATX cannot route until
their coupled mechanical interfaces are qualified. The new follow-up is an
experiment, not an assertion that these proposals already close a board.
