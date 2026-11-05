# Generic supply-search and group-ranking slices — 2026-09-09

These changes extend the September 7 ground-portal work. They contain no
board/refdes/coordinate corrective selector. Source schematics, BOM, footprints,
fabrication allowances and protected archived boards are not changed.

## 1. Apply local-path admission inside the search

The local supply router could find a connected bridge on its first layer/seat
pair, return it, and then reject it for excessive length. It did not advance to
the next candidate after that rejection. The generic bridge engine already
supported a complete-candidate `ops_ok` predicate, but the local supply caller
did not use it, and the dedicated POFV bridge did not expose it.

Both local bridge paths now apply the unchanged locality limit **inside** their
candidate search. A rejected connected path advances to another candidate.
The POFV path also observes the caller's existing deadline during endpoint and
layer searches; it cannot spend unbounded extra time after the local budget.

On the exact saved 72 mm board, the MCU supply bridge changes from a rejected
5.330 mm path to an accepted 4.330 mm path under the existing 4.340 mm limit.
There is no increased length allowance, width relaxation or component move.
The fixed-seat four-size native construction replay improves as follows:

| Outline | Previously constructible | Now constructible |
| --- | --- | --- |
| 58 × 68 mm | 13/16 | 14/16 |
| 58 × 72 mm | 13/16 | 14/16 |
| 58 × 76 mm | 13/16 | 14/16 |
| 58 × 80 mm | 12/16 | 13/16 |

All four complete transactions still refuse/roll back in this fixed-seat
comparison because of the other remaining cells. Evidence lives in
`build/12vhpwr-supply-escape-20260909/bridge-matrix/comparison.json`.

## 2. Prefer native-feasible complete supply groups

The remaining mux failures were not missing power-layer capacity: narrow ground
pads cannot contain the declared POFV land, and neighboring bypass supply pads
occupied their off-pad escape directions. The late placer ranked whole groups
by source-only geometric cost and deferred native ground construction entirely
until final checking. That allowed a cheaper, blocked layout to outrank an
available constructible one.

The existing source-derived local group generator produces 12 candidate layouts
for this owner; five pass the complete isolated native supply/return proof.
`cec_supply_native.preferred_layouts` now ranks those proven layouts first,
preserving their geometric cost order. Unknown/failed isolated layouts remain
as explicitly unproved fallbacks: isolated failure does not prove that sharing
a neighboring board portal is impossible. A timeout produces no positive
preference, not a false impossibility conclusion.

The actual late `_qualified_supply_layouts` provider calls this preference.
Early critical-owner locks continue to require a strictly qualified local group.
Both retain the separate full-board placement and construction admission gates.
Proof/index accounting is retained in the placement report; malformed or
duplicate indexes fail closed. No named capacitor relocation is implemented.

## Native context experiment and its limits

The five native-preferred layouts were replayed through current-source native
materialization at the saved owner position. All preserve pad bounds,
courtyard legality and required authored power copper; all allow construction
of 16/16 local cells. The first such layout commits its local copper without
new DRC, unlike the previous all-cell rollback.

**Constructibility is not the complete placement verdict.** Its saved-board audit
still reports 14/16: two pre-existing cap-to-owner-ground distances are 2.624 mm
and 2.507 mm against the unchanged 2.500 mm limit. All global routing, plane,
thermal and fabrication gates still apply. No claim of routing/fab readiness is
made from the 16/16 construction result.

The context trials are recorded in
`build/12vhpwr-supply-escape-20260909/group-seats/report.json`; the committed local
diagnostic and its before/after DRC evidence are in
`build/12vhpwr-supply-escape-20260909/complete-local-proposal/native-cell-replay.json`.
These are automatic source-generated alternatives, not a manually edited PCB.

## Authority and validation

All 12 current 12VHPWR hierarchical schematic hashes match the prior closeout.
The manifest selects `12vhpwr-standard-module.kicad_sch`, not either stale
canonical/candidate PCB as electrical authority. A fresh single-outline run
re-synchronizes a disposable input from that live hierarchy and invokes the real
production placement stage with seed 0 / plain strategy on 58 × 72 mm. Outline
search is bounded for this test only; no persistent board policy is changed.
Its source-intake gate passes. See
`build/12vhpwr-supply-escape-fresh-20260909/slice-run-contract.json`.

The regression suite passes **808 tests, 14 existing skips and 8 subtests**.
New tests cover rejection of the first overlong bridge in favor of a later
layer, deadline enforcement, renamed group identities, deterministic preference,
retained fallbacks, corrupt index refusal, and execution of the actual late
provider with distinct strict/late behavior. Existing power, placement, native
cell, source, manufacturing and last-mile tests are included. Log:
`build/supply-escape-regression-tests-20260909.log`.

The immutable PCIe control still has **0 DRC, 0 opens, 615 tracks, 226 vias and
1242.073 mm**. Its complete score and eight current broader constraint blockers
exactly match the September 7 replay. Its broader release/differential-pair gate
is still false; the regression command therefore exits 1 as before, not because
new DRC/open regressions appeared. Evidence:
`build/supply-escape-pcie-regression-20260909.json`.

## Fresh production-placement result

The single-outline fresh run completed in **261.9 seconds**. It independently
selected a native-feasible group and retained zero placement residual, pad
bounds/courtyard legality, the four mounting holes, physical MCU edge seat,
lower-right I/O, all six required power lanes and the complete wide-power width
inventory. Only five footprint poses differ from the prior 72 mm diagnostic;
the owner IC, MCU, interfaces, mounts and outline did not move. The pose diff
is retained in `build/12vhpwr-supply-escape-fresh-20260909/closeout.json`.

All **16/16 local cells construct and commit**, with no all-cell rollback.
Their explicit connections reduce opens **222 → 170** while structural DRC
stays **41 → 41**; the local DRC regression map is empty. This proves the new
ranking works through fresh placement, not just a hand-selected fixed-seat
replay. No detailed global routing was requested or run.

The broader placement decoupling check improves **12 → 11 findings**, measured
with the same current checker on both boards. Two are absolute ground-pin
distance failures; nine concern pin-proximity excess. The saved local-route
audit still accepts 14/16 under its distance contract. Thus the 16/16 constructor
success **does not supersede those independent placement failures**. Routing,
thermal and fab admission remain false. The old structural DRC set also remains
unresolved; no waiver was introduced.

Review PCB: `native-cell-proposal/board.kicad_pcb` under the fresh run directory.
The exact no-body top/bottom PNGs alongside it show the committed local copper
and carry **LOCAL ROUTES ONLY — 170 OPENS — NOT FAB-READY** banners. Windows copies
were hash-verified, visually inspected, and both dashboard artifact endpoints
returned HTTP 200. This is a diagnostic, not a fab-review archive promotion.

The declared neutral-core generic audit passes; the full runtime still has 380
legacy selector findings. These slices do not turn that larger result into a
full-pipeline-generic claim. The next bounded placement slice should optimize
complete-loop proximity using the same native feasibility and power-preservation
proofs, retaining these successful routes as a regression control. It should
address the remaining distance/proximity certificates without relaxing their
limits or manually moving named capacitors.
