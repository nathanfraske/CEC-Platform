# Reserve finalization across the complete placement transaction

## Root cause and generic repair

The outer placement loop estimated whether another round fitted, but that was
only a start check. Its nested power rebuild could consume the campaign lease;
the required physical recheck then had zero time. A completed incumbent could
survive in a checkpoint while the full stage ended as an execution failure.

`cec_operation_budget.finalization_reserve` gives the serial coordinator's
optional transaction a shortened shared deadline. Every supervised repair,
power reconstruction and subsequent physical/priority measurement inherits
that deadline; returning to the caller restores the reserved finish time.
Nested scopes restore their parents exactly. There is no deadline renewal or
solver-success inference. Only explicit supervisor budget stops are captured;
worker crashes, cancellation and integrity failures still propagate.

The complete priority cooptimization loop now runs inside this lease, with the
existing 120-second finish reserve. Its round-start estimator does not subtract
the same reserve twice. An interrupted round cannot become the winner: the
coordinator restores the last completely measured PCB/sidecar snapshot before
the final physical checks and report. The report retains the lease and any
operation failure. Authority exceptions also retain their structured operation
evidence instead of only a string.

The optional final fiducial reseat uses the same mechanism with a 60-second
finish reserve and an outer artifact-family transaction. A budget stop restores
the complete input and rebinds its authority; any other exception also restores
the family and then propagates. Existing placement and fabrication checks still
decide admission. This does not waive a fiducial or critical-route defect.

## Validation

- `build/finalization-reserve-tests-20260916.log`: **138 tests pass** in 105.10 s,
  including the existing full-pipeline and fiducial tests.
- `build/finalization-reserve-final-tests-20260916.log`: **110 tests pass** in
  14.71 s after the final diagnostics change. These suites overlap; do not add
  the counts. Tests cover nested/expired/absent/invalid deadlines, a real child
  process inheriting the shortened deadline, budget-vs-crash distinction,
  loaded-native PCB/sidecar rollback, and whole-loop integration boundaries.
- `build/finalization-reserve-replay-20260916/report.json`: concurrent native
  transactions on the four currently admissible families deliberately leave
  too little time for optional finishing. The real operation supervisor
  refuses the worker before launch, all complete artifact families remain
  byte-identical, and their physical gates remain unchanged. EPS/ATX keep their
  explicit unadmitted paired-interface holds. This is not a routing run.
- All six current source/hierarchy identities remain unchanged. The historical
  PCIe2 board hash, complete regression and all probes match. The generic core
  passes; the existing 23 physical / 380 runtime legacy findings are unchanged.

## Completed bounded integration pass (21:53Z)

`build/finalization-reserve-full-pass-20260916/suite.json` ran the complete
pipeline on the newly verified improved placement checkpoint, selected from
`build/frozen-priority-next-inputs-20260916.json` (PCIe3 in this cohort). The
other families' exhausted repair menus were not restarted. Budgets: four
workers, 16 placement trials, 450-second priority operation and 900-second
campaign. Source intake and placement execution completed in 458.071 seconds.
Both finalization receipts report no budget exhaustion. Placement remains
unadmitted with eight critical-route refusals, and the selected PCB is exactly
the input SHA `58c66a712f5a54e211a05f3ebb2f673913fe2507b2226dced593543f8e9fa4db`.
All source/engine identities stayed unchanged. Four critical pair probes
completed; five additional candidates were deferred because the remaining
fixed probe share could not fund their complete worst-case effort. There were
zero full finalists and no accepted move.

Do not claim a new board improvement from these budget tests. Keep the current
eight-refusal checkpoint and canonical manifest. Both cooptimization and
late-fiducial `finalization_budget` receipts are complete. A budget stop must retain the
incumbent and its actual outstanding gates, never become no-path or release
authority. The completed BLOCKED preview is byte-identical, not new progress.
