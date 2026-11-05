# Electrical dependency closure and fixed-power-aware placement search

## Implemented production changes

The bounded placement legalizer now translates complete transitive collateral
groups. Membership combines the existing paired-route station topology,
owner/bypass relationships, and detector/amplifier relationships reported by
the existing electrical checker. Passing detector cells are included, not only
already-failed cells. Missing members, fixed members, incompatible primary
transforms, and unavailable dependency evidence cannot authorize a partial
secondary move. No board name, reference designator or coordinate selects a fix.

The membership builder is `scripts/cec_placement_dependencies.py`, included in
the protected generic-engine audit. It does not claim arbitrary circuit role
recognition: the detector relationships still come from the existing checker
contract. Extending that contract to other circuit roles remains separate work.

Shared changes in `scripts/cec_synth_pipeline.py` apply this grouping inside the
beam, not just to a completed proposal. Route-feedback prelegalization, later
route-preflight collateral repair, craft macro repair and atomic child searches
use the dependency context. One-step craft eviction also completes the enlarged
group before exact admission. Intentional primary transformations retain their
own repair semantics rather than forcing every primary group to stay rigid.

The early route-feedback menu now includes joint terminal moves and uses the
existing diverse sampler before its finite quota. Terminal repair cannot consume
the entire menu merely by being prepended ahead of owner/pair/flow-through moves.

## Power authority enters the search

`cec_power_guard_geometry.placement_reservations` is shared by the native
postfreeze commit guard and the search adapter. It preserves the existing
F.Cu-body and through-via reservation semantics, including exact hook geometry;
this slice does not change that manufacturing/placement policy. Each search row
carries the commit clearance and explicit consumer exemptions. An arbitrary
same-net footprint does not gain a new exemption.

`cec_frozen_placement_domain.Domain.search_pad_collisions` adds the previously
missing native consumer-pad condition. It tests actual pad copper layers against
the frozen regions and through-vias, returns obstruction and pad-boundary
witnesses for tangent generation, caches source-relative poses, and restores
every temporary native transform. The solver uses the colliding pad boundary,
not the whole IC body, when calculating a pad-only escape. An insulated body
over an inner bus remains permitted where the established native guard permits
it; a pad or through-via conflict remains prohibited.

Fixed power geometry is never regenerated for these trials. The alternate
unreserved atomic macro path is unavailable when frozen authority is bound;
child searches also retain those fixed reservations. Exact postfreeze checks,
native physical checks, craft checks and routing checks remain mandatory.

A final synthetic regression exposed another boundary gap: a primary proposal
could itself move an explicitly fixed member while the helper only checked
secondary movability. The helper now rejects that transaction before searching
neighbor evictions. Unchanged carried anchors remain valid. The red/green
reproduction is retained in `build/coupled-fixed-primary-before-20260919.log`
and the final regression run.

## Replay evidence and honest limits

All experiments use the hash-bound six-board manifest
`build/additive-first-next-inputs-20260917.json`, not older board roots.

- Initial cohort: `build/coupled-placement-suite-20260919`. PCIe3's diagnostic
  worker initially failed on an incorrect harness-only helper import. The other
  workers completed. The failed receipt was retained; only PCIe3 was retried in
  `build/coupled-placement-pcie3-retry-20260919` after correcting that import.
- Native-pad-aware cohort: `build/coupled-placement-suite-20260919-v2`.
- Final fixed-primary regression cohort:
  `build/coupled-placement-suite-20260919-final`. Use its report for final-code
  cross-board/control parity; the earlier directories explain the investigation.

The initial corrected PCIe3 replay found two physically acceptable placements in
the previously blocked 35-proposal neighborhood, versus zero in the previous
macro-frontier replay. Its detector/amplifier separation failure was eliminated
by moving the linked group. However, both placements produced **12 Kelvin
refusals**, worse than the prior 11-refusal constructor baseline (and the earlier
separate 10-refusal trials). They were rejected, not promoted. Physical placement
success is not equivalent to improved connectivity or board closure.

The Hub completed two bounded repair batches, each selecting 16 previously
untried poses and revisiting none. They yielded 27 and 31 geometrically legal
variants respectively, but no monotonic craft improvement. The two ground-return
blockers and regulator-input proximity blocker remain. The durable history is
now **157 distinct poses**, located at:

`build/coupled-placement-suite-20260919-v2/hub-standard-rev2/board.placement-search.json`

Future Hub runs must seed this history, not the older 125/141-pose histories.
The final cohort performs Hub read-only checks instead of another unchanged
batch. Current PCIe2 and 12VHPWR receive cross-board checks; EPS/ATX remain held
on their coupled-interface ECO. No candidate from this slice is a fab candidate.

## Validation and next boundary

The synthetic/native suite covers transitive grouping, arbitrary references,
all four rotations, both faces, fixed/missing members, deliberate primary
transforms, body versus pad-only power conflicts, and native pose restoration.
Final test and cohort results follow.

Final broad regression: **854 tests and two subtests pass**, with only the
existing KiCad SWIG deprecation warning, in 67.25 seconds. Receipt:
`build/coupled-placement-wide-tests-final-20260919.log`.

The final 35-primary PCIe3 replay rejects 15 forbidden fixed-primary moves
immediately; 14 other primary searches exhaust their bounded beam. Six primaries
produce ten variants, all clearing the native frozen-power guard: **zero late
frozen-power rejections**, versus 28 in the previous macro-frontier slice.
Eight were physically tested in the initial quota. Three fail terminal-order
checks, two fail local ground-return access, one fails the separate pour-territory
craft check, and the two physical survivors still produce the worse 12-refusal
Kelvin result. The remaining two quota-deferred variants are evaluated separately
in `build/coupled-placement-tail-20260919`; this does not repeat the first eight.
Both tail variants fail physical craft checks (detector locality/pour territory,
with terminal order also failing in one). Thus all ten variants are accounted
for. These are deliberate primary detector moves, not split collateral groups;
primary electrical relationships still need explicit search constraints too.
Both tail boards retain all native copper and leave the canonical source intact.

All six canonical source and hierarchy signatures are unchanged. The historical
PCIe2 board hash, DRC/open regression receipt, and probes match the current
baseline, including its already-known sideways-Kelvin finding. Core generic
audit passes; full-pipeline inventory remains 23 physical / 380 runtime issues.
The final six-board report has no worker errors and grants no release authority.

The next electrical placement contract must preserve critical terminal
reachability/order during collateral movement and primary detector locality,
not only collateral detector/bypass/pair membership. The actual regressions
above are the evidence for that work;
do not promote these two placements or rerun their unchanged route trials.
Hub ground-return construction still requires its own failure-directed repair.
Core generic audit success must not be reported as whole-pipeline generic or
manufacturing qualification; the broader audit remains separately tracked.
