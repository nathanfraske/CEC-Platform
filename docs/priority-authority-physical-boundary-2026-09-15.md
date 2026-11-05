# Priority repair must requalify physical placement after power rebuilding

## Finished cohort and review

`build/probe-lease-followup-suite-20260915/suite.json` finished **17:24:11Z**,
590.977 seconds, all workers gone, source/hierarchy/engine guards passed.
The scheduling repair did enable real probes: first operation measured six
pair proposals and two full finalists across two rounds. It retained one
pair portal shift: priority refusals **12 -> 11**, pair remaining edges **2 -> 1**.
Final canonical PCB SHA **6e58ee11932313ab6e480788e5c72d3ae939b77c09f02225304fec7c570d30b8**.

However final craft changed **PASS -> FAIL** at C2/U3.5's immediate ground
return. Main routing did not start. This is a tradeoff, not clean placement
closure. Keep 6e58 as a reviewed diagnostic result; retain the old hash-bound
400ff input for the corrected continuation. Do not seed solely from recency.

Immutable dashboard ID:
`pass-probe-lease-followup-suite-20260915-pcie-8pin-3port-14a785e088`.
The top no-body placement was visually inspected; its header matches the
native hash and says BLOCKED / NOT FAB SIGNOFF. Windows mirror:
`C:/Users/Admin/Documents/CEC-Board-Reviews/probe-lease-followup-suite-20260915/pcie-8pin-3port/render.png`,
image SHA **086548d89b05f271ba7d64c0a62f94b391fff7c4f558090014c4e7ff4016b41c**.
The archive API resolves the exact published ID.

## Root cause, not another component-specific move

The exact retained finalist and saved output have identical PCB bytes. Their
project files differ only in metadata filename. Four native ablations in
`build/priority-craft-parity-20260915/report.json` isolate the deciding input:
both paths pass with the **old** frozen power authority, and both fail with
the **new** authority, regardless of prospective-preflight scope. The board
geometry was not lost in serialization and this is not a timeout hypothesis.

The outer placement/power cooptimization loop measured physical craft before
`ensure_authority()`, then rebuilt the frozen power geometry and used the
earlier physical result when selecting its best snapshot. It checked priority
routes again but omitted the post-rebuild physical check. The final stage
correctly caught the return failure, but too late for the alternate-move and
rollback logic to reject that provisional branch.

## Generic repair

`cec_full_pipeline._placement_authority_physical_boundary` now remeasures the
whole physical gate after every successful authority rebuild in that loop,
even if the board bytes or the builder's `changed` flag are unchanged.
Fresh pad/courtyard/craft/constraint evidence enters the existing atomic
placement-authority rollback and excluded-move retry path before priority
ranking or snapshot selection. Structured before/after craft certificates
are preserved per cooptimization round. Failed power and failed physical
preconditions remain fail-closed; checker exceptions cannot authorize a board.
No refdes, coordinates, fabrication/current limits or power geometry were
changed to repair the symptom.

## Validation

- `build/authority-physical-boundary-tests-20260915.log`: **203 passed and
  16 subtests**, including each physical gate failing only after a successful
  power rebuild, unchanged PCB/changed flag, exceptions, failed preconditions,
  and clean composition. Existing integration tests pass.
- `build/authority-physical-native-replay-20260915/report.json`: all six source
  families/hierarchies unchanged. Real native local-cell measurements through
  the new boundary reject the reproduced PCIe3 old/new-state transition;
  PCIe2 remains locally clean; Hub/VHP fail their existing preconditions;
  EPS/ATX retain the unadmitted interface ECO hold. This is an actual native
  local-cell projection using retained power states, **not a new power solve
  or full-board physical/fab admission**.
- `build/authority-physical-control-comparison-20260915.json`: protected
  historical PCIe2 hash, full regression and all four probes unchanged. Only
  generalization evidence differs; prior release holds remain.

## Canonical continuation and family rotation

Next journal: `build/authority-physical-followup-suite-20260915/suite.json`;
harness `tmp/authority_physical_followup_20260915.py`. One affected PCIe3 pass
from the explicit 400ff source, 600-second repair cap, 2400-second board cap,
16-GiB disk floor. Eight independent probe workers use spare CPU capacity
(32 visible CPUs / about 25 GiB available before launch); per-pair effort
stays 120 seconds. Other families were replayed concurrently for regression,
not launched into unchanged exhausted full waves. Do not duplicate this job
or edit shared engine files while any descendants remain live.

**17:50Z observation:** dispatched **17:50:06Z**, pipeline PID **375490**,
parent session **69452**. Intake passed and placement is active. About 68 GiB
free. No new output is yet complete; shared engines must stay fixed until the
cohort and its children exit. This is a historical launch receipt, not a
substitute for checking the live journal next time.

**18:07Z observation:** cohort remains live, pipeline PID 375490. The new
post-power physical check has rejected two provisional pair improvements
because both rebuilt authorities strand the same local return. Their
`operation-placement-measure-iw_7h7o3/report.json` and
`operation-placement-measure-95jklww2/report.json` preserve that failure.
The loop restored the prior placement/authority family and excluded both
move signatures; `operation-priority-repair-h9t8spm6` (PID 386816) is testing
the third bounded alternate branch with two exclusions. No completed new
review or admitted placement improvement yet. This is the guard working,
not routing closure. Shared scripts remain unchanged; 68 GiB free.

After observing this cohort, rotate generic development to the Hub/VHP
local-cell relocation/work-budget failure classes documented in
`probe-lease-dispatch-repair-2026-09-15.md`, or coupled EPS/ATX terminal fit.
Do not keep increasing PCIe3 wave budgets while ignoring those families.
The nine Kelvin-range proposal/scoring limitations remain unimplemented.
