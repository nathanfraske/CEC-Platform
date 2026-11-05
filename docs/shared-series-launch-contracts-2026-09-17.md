# Native shared-series launch reservations

## Outcome and limitation

A generic reservation defect is repaired, but **no board advances** in this
slice. Fresh concurrent priority probes still refuse eight critical routes on
PCIe3, one on 12VHPWR and one in the Hub priority diagnostic. The Hub also
retains its three separate physical/craft blockers. EPS and ATX remain held
for a coupled mating-interface ECO, not sent into an impossible routing loop.
PCIe2 remains at its verified five-open archive. No new board or image is
published, and no fabrication acceptance is claimed.

Keep **`build/additive-first-next-inputs-20260917.json`** authoritative. Every
current PCB and live hierarchy signature is unchanged. Historical PCIe2
control board hash, regression payload and all independent probes match.

## Verified failure mechanism and implementation

The existing future-pair planner removed an entire broad endpoint rectangle
when it overlapped a shared split-series station. Broad boxes genuinely can
cover the earlier segment's opposite lands, but deleting the box left only
existing pad copper protecting the later segment: it did not preserve any
outgoing routing space. On short legs, rectangle containment could also
suppress the remote endpoint's box even though that endpoint was not shared.

`cec_precision_route._shared_series_launch_contract` now derives independent
outward directions from both members' live opposite lands. Thus two series
components can have different rotations without a refdes-specific rule. The
compiler replaces only the exact shared end, matching the actual P/N native
contacts; it keeps the remote reservation even when both broad boxes overlap
the shared centre.

The local contract requires all of the following:

- Four distinct electrical nets and unique native opposite pads on two
  two-land support footprints; station positions/pad numbers must match.
- Undrilled SMD lands on the same native outer layer within each support.
- Finite bounded launch policy (default 1.0 mm, configurable helper argument,
  maximum 3.6 mm), actual octilinear direction, and project/native clearance.
- Both prospective segments clear native foreign copper, holes, protected
  power reservations and board edges. The proposed members must also clear
  one another at the declared gap/clearance.
- The rectangle representation cannot block either earlier contact or its
  outward launch. Native pad geometry owns pad-clearance proof; a pad AABB
  is not additionally inflated by the current trace radius.

This adds no tracks, vias or board poses. It is a future-space planning
constraint, **not** a guarantee of a complete coupled route, legal signal/return
via field, skew, detour, reference plane or final DRC. Unsupported or obstructed
proposals remain explicitly unqualified; native guards and all downstream
pair/whole-board gates remain mandatory. There is no board/refdes/coordinate
selection in the engine change.

`cec_probe_evidence.compact_pair_launch_contracts` and both preflight projection
boundaries retain bounded current/future pair ownership, native pad UUIDs,
directions/layers, qualification status and reason. This also captures a
successful earlier pair whose later neighbor fails: refusal-only evidence
previously discarded that relationship. Truncation is explicit. Empty
diagnostics do not alter the historical control's projected payload.

## Verification

**575 tests and two subtests pass in 26.98 seconds**, including native renamed,
translated, rotated (cardinal and 45-degree) cases, independently rotated
members, B.Cu lands, wrong-net/ambiguous/stale/NPTH cases, foreign tracks,
protected power, prospective member collisions, short-leg remote preservation,
projection round trips and the existing routing/return/ownership suites.
Log: `build/shared-series-final-tests-20260917.log`.

Native classification on all six current inputs finds applicable successful
contracts on PCIe3 and ATX. ATX's classification is not mechanical admission.
The already routed PCIe2 input declines a new outward reservation because its
existing copper obstructs that prospective straight launch; nothing is moved
or reinterpreted as replaceable. Other families have no applicable exact
shared endpoint in this compiler's current leg domain. Inventory:
`build/native-series-launch-contracts-20260917.json`.

Three concurrent full priority measurements on exact private copies:

| Board | Critical refusals before -> after | New measurement wall time |
| --- | --- | --- |
| PCIe3 | 8 -> 8 | 82.667 s |
| 12VHPWR | 1 -> 1 | 77.430 s |
| Hub | 1 -> 1, with three separate craft blockers unchanged | 137.726 s |

Evidence: `build/shared-series-suite-20260917/report.json`. The engine and all
source hashes stayed fixed throughout the cohort. Concurrent physical checks
and historical control preserve their prior state. The small timing differences
from the preceding cohort are not evidence of a speedup.

After the diagnostic projection change, a native production-entry replay of
the earlier PCIe3 segment routes its CAN pair in memory and independently
rechecks that **both** future member launches remain clear. The shared contract
survives both projection boundaries. This scoped probe takes 0.525 seconds and
creates 20 temporary items (10 CAN segments plus other precision-stage items),
while retaining all pre-existing copper. It does not attempt or qualify the
successor pair and does not save/promote a routed PCB. All six family
classifications and the historical control were rechecked under the final
engine. Evidence: `build/shared-series-final-verify-20260917/report.json`.

Core generalization passes; existing physical/runtime debt remains **23 / 380**
and `release_ok=false`. `git diff --check` passes. All workers have finished;
about 64 GiB remains free. The existing quiet heartbeat remains active.

## Next bounded domain

The new rule preserves local member launches but does not close the failing
PCIe3 pair. Its portal trace still finds only one acceptable positive-sign
SMD transition candidate per inner/back layer and no negative-sign candidate;
earlier CAN copper and native opposite/support pads still constrain the larger
matched signal-via field. The 1 mm straight escape is **not** the complete
paired transition resource. Do not repeatedly lengthen it or rerun these same
probes and call that progress.

Next investigate a jointly qualified shared-station transition field or a
bounded transactional order portfolio for connected pair segments. Reuse
existing native paired-stub/transition-field solvers, exact qualification and
copper rollback. An earlier accepted pair must be reroutable only inside its
explicit newly generated transaction, never by unlocking source power or
other pre-existing copper. Continue independent owned-local-return work on
the Hub and the coupled EPS/ATX geometry domain; neither is solved by this
pair-only change. The existing dimension, edge-span, electrical-budget and
mechanical qualification constraints remain unchanged.
