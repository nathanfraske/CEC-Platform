# Ground access / owned power copper slices — 2026-09-07

Status: implemented and exercised on disposable, fixed-seat current-hierarchy
12VHPWR candidates. **Not a new full placement wave, routed board, thermal
qualification or fab promotion.** No canonical board or source schematic/BOM
was changed in these slices.

## Slice 1: reserve required returns before constructing wide copper

The prior local-cell refusal certificates identified back-layer power tracks
blocking through-board ground vias. The power constructor did not consider
those future returns when committing its tracks. Additional detailed-router
effort cannot legally drill a ground barrel through foreign power copper.

`scripts/cec_portal_copper.py` adds a bounded, product-neutral primitive:

- Derive prospective ground via-in-pad sites from the current bypass assignment
  and actual owner/capacitor return pads. Rail-to-rail bypasses are not converted
  to ground. Distinct physical pads sharing a pad number remain distinct.
- Require the explicitly declared fabrication profile, qualified via geometry,
  native pad/copper/edge checks and existing drill-spacing clearance before
  reserving a site. Reservations are **not installed vias or plane signoff**.
- Replan only tracks explicitly supplied by the copper constructor. Other
  locked copper and grouped topology stay protected. No refdes, net spelling,
  product, footprint or coordinate selector determines the repair.
- Generate a single orthogonal side-step around a conflicting interval. Preserve
  exact track width, endpoints, layer, net, lock status and every old same-net
  track/via/pad contact. Check every replacement leg against native foreign
  geometry and every reserved site. Respect board/netclass clearance floors.
- Bound each search (32 affected tracks, up to 12 proposals per track by
  default). Endpoint-blocked, diagonal, grouped, obstructed and contact-losing
  cases retain the original track and emit a refusal. Never narrow a power
  path to improve a cell count.

The first production adapter is `cec_force_lanes.lay_force_lanes`. Both native
materialization paths save its reservation/replan evidence in `.cellreport.json`;
the admission reader carries that evidence into the candidate report. Future
sites remain advisory until the complete native cell constructor proves them.
The existing transitive-import cache fingerprint includes the new engine.

This is not a claim that every older power/pour producer is generic or now uses
this adapter. The neutral-core audit passes; the full runtime audit still fails
with 380 legacy selector findings. Grouped/multi-segment power replanning and
other producers require their own owner-aware integration.

## Slice 2: rejected neckdowns cannot count as constructed links

The first experiment appeared to improve local proposals from 8/16 to 14/16.
Examining the complete cell records exposed a false-owned shared ground link:
its 2.2966 mm, 0.2 mm-wide path on a 0.5 mm class was explicitly rejected by
endpoint qualification (`escape_budget_exceeded`, 0.75 mm allowance), but the
caller ignored that rejection and returned success anyway.

`cec_decoupler_cell._admit_link_neckdowns` now requires **all generated narrow
segments** to pass the existing geometric qualifier before owning a same-layer
link, shared-ground link, multilayer bridge or ground dogbone. Refused trial
copper is deleted atomically. Read-only probes which omit persistent grouping
still run the same qualification. Rejection evidence is retained; no width rule
or local escape allowance was relaxed. An old synthetic test which expected the
invalid whole-link neckdown to pass now asserts refusal and cleanup.

A trial dependency retry added no improvement and was removed rather than
retained as another unproductive loop. This admission repair qualifies newly
generated links; it is not a replacement for whole-board width, return-plane,
DRC or thermal signoff on existing/imported copper.

## Measured fixed-seat replay

Authority remains `beta/12vhpwr-standard/12vhpwr-standard-module.kicad_sch`
plus its 11 numbered children, loaded through the manifest with a fresh
hierarchical netlist. The check identifies 103 source components and 16 bypass
requirements. Each native candidate still contains those components plus four
mounts and three fiducials (110 footprints).

Inputs are the four immutable candidates from
`build/12vhpwr-power-aware-full-placement-20260907/02-placement/candidates`.
Outputs and exact comparison evidence are in
`build/12vhpwr-ground-portal-final-20260907/closeout.json`.

Both before and after native trials use the **corrected** link qualifier:

| Fixed outline | Qualified local proposals before → after | Full-width detours | Structural DRC before = after | Opens before = after |
| --- | --- | --- | --- | --- |
| 58 × 68 mm | 7/16 → 13/16 | 6 | 39 | 223 |
| 58 × 72 mm | 7/16 → 13/16 | 6 | 41 | 223 |
| 58 × 76 mm | 7/16 → 13/16 | 6 | 41 | 223 |
| 58 × 80 mm | 7/16 → 12/16 | 5 | 38 | 222 |

All four retain all six power lanes and six authored sensing cells / 444
blueprint segments. Independent native comparisons prove unchanged footprint
poses, pad connectivity, wide-power width inventory, terminal connectivity
partitions and structural DRC item/location signatures. Short-message net order
is canonicalized because KiCad may reverse the two net names. Raw ratsnest
endpoint signatures can change after a detour; they are not used to disguise
terminal connectivity changes.

The 72 mm track length grows 980.124 → 999.594 mm (+19.470 mm, about 2.0% across
all copper), with the six detoured trunks retaining their 2.5 mm width. Unchanged
width is not thermal proof: changed current paths need fresh thermal/current
qualification before release. No cooling credit was added.

There are 27 prospective qualified pad-center sites and two refused sites on
each board. At 68/72/76 mm, no reserved site remains blocked by a track. At 80 mm,
three sites remain blocked: the independent straight-segment replan cannot
preserve the required contacts around that multi-segment power shape. It refuses
three affected segments rather than severing or narrowing the lane.

**Every complete cell transaction still rolls back. Saved owned-cell count is
zero.** At 68/72/76 mm the remaining proposals are the power mux's two ground
returns and one MCU supply link (C27, C6 and C7 in this hierarchy). At 80 mm the
remaining power obstruction additionally blocks C12. These identities are
diagnostic output, not repair selectors. No detailed routing was launched with
these prerequisite failures still open.

The bounded four-process comparison took about 23 seconds wall time (each task
22.0–23.3 seconds), including constructor, before/after score and native cell
trials. This is **not comparable to the previous 840-second full placement
stage** and is not claimed as a placement speedup.

## Validation, control and review artifacts

The broad regression suite, including the new native/synthetic portal tests,
passes 720 tests with 14 existing skips. Evidence:
`build/ground-portal-final-tests-20260907.log`. Coverage includes renamed nets,
axis/reversal/translation transforms, preserved native contacts and widths,
obstacles, layers, explicit ownership, immutable refusal, search budgets,
fabrication-profile absence, duplicate physical pads, rail-to-rail topology,
mandatory neckdown qualification with/without grouping, and sidecar propagation.

The immutable PCIe fab-review control replay remains at **0 structural DRC,
0 opens, 615 tracks, 226 vias, 1242.073 mm**. Current score and the eight existing
broader constraint blockers exactly match the prior replay. Its current broader
release/differential-pair gate is still false; zero DRC/opens is not a new release
approval. The control and protected Hub/12VHPWR source-board hashes are unchanged.
See `build/ground-portal-pcie-regression-20260907.json`.

Exact saved 58 × 72 mm no-body renders:

- `build/12vhpwr-ground-portal-final-20260907/72/ground-portals-72-top.png`
- `build/12vhpwr-ground-portal-final-20260907/72/ground-portals-72-bottom.png`

Both carry a **POWER DIAGNOSTIC — NOT ROUTED / NOT PROMOTED** banner and show the
saved constructor copper, not the rolled-back local-cell proposal. Windows
copies were hash-verified and both dashboard `/artifact?p=...` endpoints returned
HTTP 200. They are direct diagnostic artifacts, not a misleading fab-review entry.

## Next causal boundary

Use full native ground/supply-access certificates to qualify the whole IC/cap
group before committing its placement: bounded fine-pitch escape, a legal
class-width shared-return body, and an immediately accessible return portal.
The remaining mux pad-center sites already fail before broad power is added;
moving that power alone cannot solve their package-level escape. Keep source
pin-distance requirements and protected power topology as hard constraints.
Do not substitute a named-cap move or another blind routing wave. The older
unresolved DRC set, plane continuity and thermal/fabrication gates remain separate
work after local-cell feasibility is closed.
