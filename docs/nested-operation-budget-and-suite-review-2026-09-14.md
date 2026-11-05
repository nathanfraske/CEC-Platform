# Nested operation budgets and suite review — 2026-09-14

## Completed preceding cohort

`build/priority-plated-suite-20260914/suite.json` finished. All three boards
retained their explicit input: no placement or route was admitted. Source,
schematic hierarchy and engine identities stayed unchanged in each job.

| Board | Elapsed | Actual stop |
|---|---:|---|
| Hub | 289.6 s | Power-terminal repair killed at its 240-second operation cap while reconstructing CAN |
| 12VHPWR | 988.5 s | Two priority-route refusals; repair reported critical-probe budget inconclusive |
| PCIe3 | 265.5 s | Eleven priority-route refusals; proposed access gain worsened the complete capacity key |

The Hub did reach a new stage. Its live preclosure linked the three plated
power pins with two connections, exact power passed for a trial, and the
worker stack reached `cec_priority_dependency.rebuild` → critical checkpoint
→ multidrop pair reconstruction. This is **not** an admitted Hub improvement:
the whole transaction was interrupted and its input remained untouched.

The three published body-free top previews were visually inspected. They
accurately show unchanged placement inputs, prominently marked BLOCKED and
NOT FAB SIGNOFF. No new routed-board claim follows from these images.

## Shared root cause and repair

The outer power-placement repair still had its old 240-second limit after its
scope grew to include full pair reconstruction. The precision solver started
a fresh 240-second pair budget inside that operation. Additionally, nested
worker supervision clamped to the campaign deadline but ignored the parent
operation deadline before overwriting it. A timeout's last reported phase was
only `operation_dispatch`, and completed placement-trial history was written
only at function return.

The repaired scheduling and evidence boundaries:

- Child workers respect the earlier parent-operation/campaign deadline and
  reserve fifteen seconds for parent completion. Invalid budgets fail closed.
- Pair search respects the enclosing deadline and reserves thirty seconds
  for completion/proof. Expired work is explicitly unproved, never successful.
  Existing owned pairs require no fresh search lease and remain preserved.
- Default power-repair effort includes its bounded new scope: 240 seconds
  for placement plus two allowed one-pair reconstructions at 240 seconds each,
  each with thirty seconds proof allowance: **780 seconds**, still clamped
  by the enclosing board job. Explicit configured limits override this plan.
  These are scheduling allowances, not electrical numbers or acceptance rules.
- Materialization, exact-power admission, pair search, reference fill,
  independent proof, authority rebinding and per-trial completion have durable
  phase records. One atomic diagnostic checkpoint retains completed trials
  plus the current trial, even if the process must be stopped.
- Pair reconstruction input/authority files and outputs survive ordinary
  scratch cleanup. At most the configured dependency trials are created;
  the sixteen-GiB free-space floor applies. None grants release authority.

No widths, clearance, power budgets, pair criteria, interfaces or source
placements were relaxed. There is no board/refdes/coordinate selector in
these changes.

## Validation and follow-up

Final integrated tests: `build/nested-budget-integrated-tests-20260914.log` —
**306 passed**, plus sixteen subtests. This includes nested native subprocess
deadline propagation, expired-pair no-mutation/owned-prefix preservation,
scope-funded effort and explicit-limit override, existing package preclosure,
full pipeline, checkpoint, typed power repair and precision flow regressions.
The earlier 157-test focused set overlaps and is not added.

`build/nested-budget-control-20260914.json` exactly matches the preceding
control's board SHA256, board-regression result and all four independent
probe objects. Its pre-existing release failures remain visible, including
pair/craft checks; unchanged results are not a present-day fabrication pass.
`build/nested-budget-generalization-20260914.json` reports sixty neutral
modules, zero core selector violations, and unchanged legacy debt (23 physical,
380 runtime findings); whole-pipeline generic maturity remains false.

Canonical replay: `build/nested-budget-suite-20260914/suite.json`,
three concurrent jobs (Hub, 12VHPWR, PCIe3), two workers each, twelve placement
trials, eight routing passes and an 1,800-second board deadline. Only launch
after final tests; check the journal and processes before any restart. The
launcher validates all six explicit source/hierarchy identities, not mtime.

Live check at 00:34 UTC, September 15: all three jobs are running. All six
source/hierarchy checks passed (`build/nested-budget-source-check-20260914.json`).
Hub trial 3 passed exact-power authority and subsequent physical checks, then
entered CAN reconstruction. A nested authority worker requesting 1,800 seconds
was correctly limited to 701.35 seconds; the following placement worker was
limited to 680.94 seconds. CAN had its complete 240-second search allowance
inside the remaining parent budget. These are live boundary checks, not final
board admission. Dashboard root returned HTTP 200 from Windows. Free space was
72 GiB. No shared engine edits occurred after launch.

## Next diagnostic gap (not changed during the running cohort)

The preceding PCIe3 repair evaluated one exact finalist and rejected it with
`access_gain_worsened_full_capacity_key`. The returned report retained the
unchanged baseline/result vectors, but not that rejected finalist's exact
vector or its first worsening field: `fully_ranked` is discarded at the early
return in `repair_route_preflight`. That prevents precise attribution from the
durable report. A subsequent generic slice should retain bounded finalist
comparisons and their authority-artifact hashes before changing ranking policy.
Do not assume a global congestion penalty is the cause, or weaken the hard
route criteria, without that evidence.

EPS/ATX remain blocked by their coupled terminal-interface geometry. PCIe2's
latest full pass remains 0 DRC / 12 opens; do not repeat its unchanged exhausted
route search. Its historical fab-review reference remains an immutable control.
