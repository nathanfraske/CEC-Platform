# Power-terminal dependency repair

## Implemented boundary

The new board-neutral `cec_power_failure` module validates structured failed
power-bridge terminals against live reference, pin number, net and physical
position. Repeated physical lands with the same pin number remain distinct.
Stale, missing or unproven terminals cannot trigger a placement move.

The canonical full pipeline now projects those verified failures into its
existing local route-access proposal generator and power-replan transaction.
It preserves declared fixed interfaces, anchors, shunts, locked footprints and
complete local follower groups. No board/refdes/coordinate repair table or
replacement router was introduced.

For each bounded proposal, the existing materializer and physical gates run
first, followed by exact power-authority compilation. Placement is measured
again after compilation because the power compiler can change its pose.
Only a power-feasible, physically valid trial earns the expensive priority
measurements. The baseline pair solve is deferred until that first viable
trial exists. Priority quality must not regress; equal priority quality is
admissible only when repairing the previously failed power authority, making
the complete dependency state a strict improvement. The original board and
authority-family fingerprints are checked before publication.

Default bounds are 12 selected proposals, a 240-second isolated operation and
one such operation per placement pass. Worker output stays on a private board
copy and is promoted only on a successful admitted result. The hook applies
both to the initial authority check and to failures encountered after later
placement moves. An unresolved typed power dependency blocks unrelated pair
repair; the outer loop does not spend another round retrying a signal move
against that same failed dependency.

Trial receipts retain exact proposed placements and structured power-failure
evidence, in addition to native geometry/craft, authority and priority results.
No electrical current assumptions, copper rules or fabrication limits changed.

## Native evidence

`build/power-terminal-native-20260914/receipt.json` records concurrent current
Hub and PCIe3 checks. All original board and hierarchy signatures, plus the
shared engine signature, stayed unchanged.

The Hub generated 43 eligible proposals and selected 12. It finished in
**64.573 seconds**, accepted **zero**, and spent **zero pair evaluations** on
the rejected trials:

| Refusal class | Trials |
| --- | ---: |
| Collision with frozen copper | 9 |
| Exact power authority still refused | 2 |
| Physical placement gate refused | 1 |

The first rotated-terminal trial advanced the bridge search through four
refusals (including two sites that fit only one of the required two vias) and
then exhausted the bounded search. It did not establish a valid two-via field.
Most translations collided with existing frozen CAN_H/CAN_L routes. This is
evidence that power access and the owned signal prefix need a coordinated
transaction; it is not justification to move protected power buses, waive
clearance or delete arbitrary copper.

Hub output SHA256 remains
`032f2702da06417d3547cc82fe38f32ebdcbcf1d41636c55e70a9dc9c81c5262`.
The PCIe3 adapter was correctly inapplicable and made no change. Its earlier
fresh exact-power compiler replay remains the separate cross-board evidence;
this no-op is not a newly routed PCIe3 result.

The native probe preceded final diagnostic-field retention and the all-authority
call-site wiring; the canonical follow-up below verifies that final integration.

## Tests and protected control

- `build/power-terminal-integrated-tests-20260914.log`: **360 passed plus three
  subtests**, 4.79 seconds.
- `build/power-terminal-final-tests-20260914.log`: **102 passed plus three
  subtests**, 53.78 seconds, covering the full-pipeline adapters. These suites
  overlap; their counts must not be added as unique tests.
- Native protected PCIe2: `build/power-terminal-control-20260914.json` equals
  `build/bridge-feedback-final-control-20260914.json` for all four probe objects
  and board hash. Its zero DRC / zero opens and pre-existing broader failures
  remain unchanged.
- Static anti-overfit gate: 57 declared core modules, zero core violations.
  Broader existing counts remain 380 runtime and 23 physical findings; whole
  pipeline release/generic status remains false. Receipt:
  `build/power-terminal-generalization-20260914.json`.
- `git diff --check` passes.

No new board layout or route was admitted by the native adapter probe, and
there is no new routed render to claim from it.

## Canonical follow-up and next scope

The canonical production Hub follow-up is complete at
`build/hub-power-terminal-followup-20260914/suite.json`, launched by
`tmp/hub_power_terminal_followup_20260914.py`. It uses the same explicit current
Hub input hash and source signature as the six-board suite, with two placement
workers, a 1800-second board deadline and the existing 16 GiB free-space floor.
Source intake passed in 12.4 seconds. The full invocation finished blocked in
**109.521 seconds**, with a 95.0-second placement stage, compared with
1570.21 seconds for the preceding canonical Hub attempt on the same input.
This is about 93% less failed-pass runtime, not a routing-throughput speedup.
The final integration exercised the new stage: 43 proposals / 12 selected,
nine fixed-copper collisions, two power refusals, one physical refusal and
zero pair evaluations. `priority_route_repair.reason` is
`power_bridge_dependency_unresolved`; unrelated pair-repair rounds were skipped.
No geometry was adopted. Source, hierarchy and engine signatures stayed intact.

The normal publisher produced the verified body-free retained-placement review:
[Hub completed-pass dashboard](http://localhost:8090/?id=pass-hub-power-terminal-followup-20260914-hub-standard-rev2-bcb7f9c09e).
The output SHA equals the input SHA above. Its image was inspected and its URL
returned HTTP 200. It is the unchanged placement, not a newly routed board.

The cohort has exited and signatures are recorded. No board-suite job remains
running. Keep its `power_terminal_repair` / `power_terminal_repairs` receipts;
do not repeat an unchanged failed Hub wave.

After this verification, rotate the next development slice toward the EPS/ATX
joint terminal interface problem instead of another Hub-only loop. The existing
spacing study found native different-net T340 pairs first passing at a tested
7.7 mm pitch, while naive straight-row allocations exceed the present last-datum
limits. That is not an exact two-dimensional packing impossibility proof.
Investigate coordinated main/daughterboard geometry within the fixed edge-span,
outline, pinout and keying contracts; no unilateral terminal movement, land
shrinking or silent outline increase is authorized. See
`docs/native-placement-copper-and-mating-resume-2026-09-12.md` for the bounded
native spacing evidence and its limitations.
