# Native electrical relationships inside placement search

## Failure and generic repair

Moving complete collateral groups prevented split detector/bypass cells, but
did not constrain a deliberate primary transformation or its resulting sense
input distances. The previous PCIe3 replay produced two physically acceptable
placements that worsened Kelvin construction from 11 refusals to 12. These
placements were rejected; neither became a canonical board.

`scripts/cec_placement_relation_guard.py` now binds the existing native pad
templates and critical-terminal contracts into a proposal-search restriction.
It uses reference/pad/net identities from the board and existing checker output,
not board names, hand-selected references, or coordinates. Detector evidence now
includes the exact endpoint pairs used by the existing adjacency checker.

The restriction protects each relationship independently:

- No new terminal crossings.
- Each direct sense input retains its own range allowance. Improving the other
  input cannot hide a regression in an aggregate wire-length score.
- Declared direct-input contracts inherit the Kelvin constructor's actual
  default range, rather than introducing another placer distance setting.
- Existing filtered-topology demands retain their own geometry interpretation;
  they are not subjected to the direct-input radius. Their aggregate demand
  length cannot increase under this conservative search restriction.
- Detector/amplifier locality uses the existing checker's limit and native pad
  endpoints. Missing, ambiguous, nonfinite, or inconsistent bindings fail closed.

This is a **non-regression search restriction, not electrical qualification**.
A pre-existing distance violation may remain equal or improve, but cannot grow.
A currently passing relation can use its existing permitted slack. Passing this
restriction does not clear baseline violations or replace the downstream native,
craft, routing, DRC, or release gates. No power/load assumptions changed.

## Production coverage

The common placement dependency context carries the serializable contract.
The bounded macro legalizer checks the primary proposal before eviction and
each collateral beam shift before expensive geometry checks. Ordinary craft
menus and route-preflight menus screen primary electrical regressions before
their finite trial quota. One-step craft eviction rechecks the resulting pose.

Atomic child searches using the common macro legalizer inherit its restriction.
Direct atomic child/grandchild variants still rely on their existing complete
native craft gates; this slice does not claim new early filtering on every
direct atomic branch. No acceptance gate was weakened.

The new module is included in the protected generic-engine audit. Existing
relationship discovery remains limited to the circuit roles recognized by the
upstream contracts; this is not a claim of universal circuit-role recognition.

## Validation

`build/placement-relations-wide-tests-20260919.log` records **878 tests and two
subtests passing**, with the existing KiCad SWIG deprecation warning. The new
24-case suite covers arbitrary references, translated fixtures, both board
faces, four rotations, native pad projection, crossings, per-input range debt,
detector locality, malformed bindings, and safe collateral direction selection.

The concurrent replay is recorded in:

`build/placement-relations-suite-20260919/report.json`

It uses `build/additive-first-next-inputs-20260917.json`, checks source/hierarchy
hashes and engine stability, and retains all six canonical boards unchanged.
There are no worker errors and no promoted or release-accepted candidates.

### PCIe3 placement search

Of the same 35 primary proposals, 15 are rejected for moving fixed members, one
for primary electrical regression, and 17 exhaust the bounded search. Two
primaries yield three geometric variants. The beam rejects 44 individual
electrically regressing shifts before expensive native trial evaluation.

All three variants preserve the frozen-power placement requirements, maintaining
zero late frozen-power rejections. They still fail physical craft admission:
one fails the separate pour-territory check and two fail the local ground-return
access check for a supply decoupler. No Kelvin trial follows these failures.

The prior ten physical trials are reduced to three by pruning unacceptable
electrical moves. The two prior 12-refusal placements are no longer emitted.
**This is less wasted search work, not additional connected nets or board
closure.** Do not rerun these same three failed variants unchanged.

### Other boards and historical control

- Current PCIe2: existing physical/craft checks pass; its four terminal and two
  detector relationships bind successfully. The canonical partial route remains
  unchanged, including its five open connections.
- Hub: the two local ground-return blockers and regulator-input proximity
  blocker remain. This new sense/detector restriction has no applicable
  relationships on this board; its domain pass is not a physical placement pass.
  No duplicate placement batch was run. Retain the 157-pose history in
  `build/coupled-placement-suite-20260919-v2/hub-standard-rev2/board.placement-search.json`.
- 12VHPWR: six filtered terminal relationships bind; current physical checks
  pass with the existing local C7 interconnect deferred to the pre-route stage.
  No copper or new routes were promoted.
- EPS and ATX24: their coupled-interface ECO holds remain in force. This replay
  does not move mating parts independently or treat those holds as routing jobs.
- Historical PCIe2: board hash, DRC/open regression result, and probes match
  `build/kelvin-departure-control-20260917/current.json`. Its already-known
  sideways-Kelvin finding is retained, not waived by an older baseline.

Core generic-engine checks pass. The broader pipeline inventory still reports
23 physical and 380 runtime issues; full-pipeline generality and fab readiness
are not claimed by the narrower audit result.

## Next work

The next constructive improvement is shared, failure-directed ground-return
placement/connection generation, plus proposing terminal poses inside these
electrical restrictions rather than only pruning bad poses. The remaining
ground-return failures distinguish via-seat clearance from the connecting
stub's clearance; a legal via location alone does not establish a legal return.
They are not evidence that the outline must grow or that a power bus may move.

Keep the canonical manifest, historical control, frozen power geometry, and
interface holds. All replay workers completed. No new board preview is published
because no new candidate passed admission.
