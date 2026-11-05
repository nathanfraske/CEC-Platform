# Complete probe cohorts and fixed-owner relief

## Scope and protected constraints

Continuation uses the hash-bound outputs of `build/fair-domain-suite-20260913/`.
Current source hierarchies, terminal pinouts, board dimensions, current budgets,
required copper widths and protected power copper are unchanged. No routing or
fabrication gate is waived. EPS/ATX still have fixed terminal pad shorts under
the existing interface dimensions; no unapproved span increase is implemented.

## Implemented scheduling repair

The preceding 12VHPWR repair prepared 13 legal probe boards but scheduled zero
exact pair probes: its fractional allocation was 206.339 seconds while one
complete two-pair cohort cost 245 seconds. There were 472.679 seconds remaining
and a 60-second finalist reserve. The hard budget could fund a cohort, but the
fractional scheduling preference stranded the whole queue.

`cec_operation_budget.probe_allocation` now funds one complete cohort when it
fits after the hard finalist reserve. It does not shorten per-pair search
effort. Empty queues never borrow; a cohort that cannot fit is still deferred,
not treated as a geometric refusal. Receipts expose the fractional allocation,
available budget and whether the minimum cohort used otherwise idle share.

`cec_board_suite --workers-per-board` exposes the already enforced nested
placement-worker ceiling instead of hard-coding two workers per board. The
default remains two, and it does not alter admission or route settings. The
first two-board campaign used six placement workers per board. The subsequent
four-board production pass uses four per board (16 nested placement workers).

`--priority-repair-timeout` now exposes the existing hard operation budget
through the suite and full-pipeline entry points. Its default is unchanged;
explicit non-finite or non-positive budgets are rejected. The new pass uses
1,200 seconds per priority-repair operation, inside a 3,000-second board cap.

Tests: `build/complete-cohort-native-tests-20260913.log`: 169 passed, 13 skipped,
one existing SWIG warning. The skipped tests require an obsolete committed Hub
fixture; they are not claimed as current-Hub validation. The actual current
Hub and 12VHPWR are being exercised separately through the full pipeline.
Fresh protected-control probes in `build/complete-cohort-control-20260913.json`
equal all four probes in `build/fair-domain-control-20260913.json`. The control's
zero DRC/zero opens and pre-existing broader release failures are unchanged.

## Fixed-owner diagnostic defect

Native current-width configuration-space maps show that the PCIe failures are
disconnected F.Cu domains under the current placement, not merely missed
endpoint samples. However, the default diagnostic for PCIe 2-port's C1 LO
corridor proposes removing fixed GND terminal TB13. Ordinary placement
correctly refuses this move, and that short certificate suppresses a search
for actionable alternatives.

A read-only diagnostic keeping all declared anchors and non-placement copper
owners present instead found a width-feasible detour by removing the movable
U3/C1/C2 cell. This is an ablation witness, not a valid final placement: the
cell still must be relocated and all original gates rechecked. PCIe 3-port
also yields movable witnesses (including a button for C1 LO) with fixed
interfaces retained. These are board observations, not special cases added
to the reusable algorithm.

Evidence:

- `build/current-domains-20260913/pcie2/`: original exact free-space maps.
- `build/current-domains-20260913/pcie2-fixed/`: fixed-owner counterfactuals.
- `build/current-domains-20260913/pcie3-fixed/`: cross-board counterfactuals.
- `tests/test_current_relief_authority.py`: synthetic exact geometry where
  removing a fixed terminal is the tempting one-owner cut, but preserving it
  exposes a two-movable-cell detour. Test passed; no geometry is mutated.
- `tmp/fixed_relief_craft_trial_20260913.py`: experimental adapter refines only
  diagnostic ownership before handing candidates to the unchanged generic
  repair and native craft checks. It grants no routing admission.

## Production fixed-owner repair and source batching

The diagnostic domain is now wired into initial craft measurement, every
accepted-incumbent refresh, negotiated lookahead, and full recertification.
All declared fixed anchors remain obstacles even when they belong to a
different net; reserved copper and other non-footprint objects cannot become
fictional placement moves. This changes repair proposals, not actual copper,
clearance, current width, or the gate. Route-only diagnostics without placement
authority retain their existing behavior.

Blueprint-stamp and blueprint-reference batches also share one schematic
export per call instead of re-exporting the same source per cell. There is no
cross-call cache. A measured six-cell batch fell from six exports / 3.127 s to
one export / 0.598 s, with identical template output hashes. This is a local
preparation improvement, not a claim about end-to-end pipeline speed.

`build/fixed-relief-broad-tests-20260913.log`: **506 passed, 16 skipped**,
including native placement/pour tests, synthetic fixed-owner alternatives,
reserved-copper immutability, source-batch freshness and operation budgets.
The skipped tests are not counted as validation. This overlaps the earlier
169-test and 363-test batches; do not add their counts together.
All four protected-control probes in
`build/fixed-relief-control-20260913.json` exactly equal the prior receipt.
The control remains at zero DRC/zero opens with unchanged broader release
failures; it is not newly certified fabrication-ready by these tests.

## Completed replay and retained placement improvement

`build/complete-cohort-suite-20260913/` is the production scheduling replay.
Hub completed six exact probe jobs in 240.588 seconds of parallel wall time;
all remained inconclusive under their full requested search budgets, with no
placement accepted. It finished in 612.112 seconds. This is actual search work,
not board closure. 12VHPWR completed two critical-only waves (51.904 and 43.417
seconds), both refused by pair connectivity/physics, and entered placement
repair with 13 probe inputs. Six native probes ran and a finalist reached
full craft and critical-route recertification. Its 600-second operation cap
expired before completion; **no candidate from that repair was promoted**.

`build/fixed-relief-craft-20260913/pcie2/` exercised the refined diagnostic
through the existing generic craft repair. One group move was accepted,
reducing failed power corridors from two to one. The run also increased the
trial count, so the improvement cannot be attributed exclusively to the
diagnostic change. Independent, unmodified production recertification in
`build/fixed-relief-certified-20260913/pcie2/` verified the strict craft
improvement and unchanged fixed anchors, and created a hash-bound placement
checkpoint. It did not grant routing admission.

## Four-board production pass (closed; boards remain unadmitted)

`build/fixed-owner-suite-20260914/` consumes that certified PCIe 2-port
checkpoint and the verified preceding PCIe 3-port, Hub and 12VHPWR outputs.
PCIe 2-port found width-valid paths for all four protected power corridors.
Two critical pair refusals became one after accepted priority placement repair.
Its exact filled power still failed two B.Cu copper-sliver findings. The third
priority-placement repair was deliberately interrupted after confirming it was
working around the wrong-stage blocker; its parent finalized normally and
retained the previous accepted board. The board process lasted 1541.907 s;
this was not a completed third search or successful board closure.

PCIe 3-port finished in 754.799 s: 64 selected craft trials, no monotonic legal
improvement, three corridor failures unchanged. Hub finished in 828.594 s with
two pair failures and two critical global-reachability failures. 12VHPWR
finished in 1187.207 s; eight exact placement probes remained inconclusive
under their full 120 s budgets. No board was granted residual routing admission.

Follow-up independent CAN routing, exact fill-seam root cause, and saved-board
qualification are documented in
`coupling-and-generated-fill-seams-2026-09-14.md`. Do not infer current state
from an earlier diagnostic render or from a successful process exit code.
