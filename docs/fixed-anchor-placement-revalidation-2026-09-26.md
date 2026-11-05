# Fixed-anchor placement proposals and route-to-placement revalidation

## Result and authority

The current Hub checkpoint advances from **6 to 5 native opens**, with **0
pipeline-qualified structural DRC violations**. This is routing progress, not
fabrication approval. No clearance, trace-width, power, schematic, BOM, or
fabrication-profile requirement was relaxed.

The input is
`build/residual-clearance-20260925/hub-coordinator-final-verified/final/incumbent/board.kicad_pcb`,
SHA-256 `edef0eaf86e226d14c9741362c9f016fef158ed8a2605c3130ff0f880b619962`.
Evidence for this slice is under `build/residual-anchor-20260926/`.
The earlier six-open report remains historical evidence; its rejected trials
were not retrospectively relabelled as successes.

## Two generic defects corrected

1. **The proposal generator did not search around its actual fixed anchors.**
   Ordinary translation/rotation candidates were ranked before applying the
   immutable local-via owner domain. Most of the retained portfolio was
   therefore unusable. `cec_fixed_pofv_mobility.proposals` now samples a bounded
   set of orthogonal rotations and radial offsets about native fixed barrels,
   intersects all companion-owner domains, and filters before occupancy top-K
   selection. Direct, live same-layer dogbones preserve ownership after an
   earlier legal move; merely being near another same-net pad does not.
   Duplicate pad numbers no longer discard potential owners.

2. **A legal support move had no admission path across the placement boundary.**
   The routing worker found a five-open candidate, but the additive checkpoint
   correctly refused changed component placement. The new
   `cec_route_placement_admission` transaction revalidates that placement in a
   new private artifact family. The original failed additive proof remains
   stored and false. The coordinator then independently grades the new family
   and requires a strict connectivity improvement without gate regressions.

Neither change contains Hub names, component references, or coordinate recipes.
The Hub component name and displacement below are observed results, not solver
inputs. This is a bounded support-movement capability, not permission to move
arbitrary ICs or reconstruct frozen power routes.

## Admission requirements

Only an isolated functional-placement failure may request this transaction.
Outline, authored power zones, parent copper, qualified pairs, power obligations,
and the native improvement proof must already pass. The transaction additionally
requires:

* unchanged project policy and design-rule bytes; only KiCad's display filename
  in project metadata is ignored;
* unchanged native component/pad identity, at most four moved two-SMD-pad
  supports, no configured immutable, locked, or grouped component movement,
  and at most 6 mm translation;
* **every original track/via**, not merely the locked subset, preserved by
  UUID and geometry, plus preservation of protected filled copper;
* a valid source placement contract and the same frozen power plan/skeleton;
* the existing power-independent placement-snapshot update, successful renewed
  authority binding, and the normal physical placement gate;
* unchanged proposed PCB bytes and unchanged input artifact families.

Native work is bounded to 90 seconds and requires a funded finishing reserve.
Exceptions, absent proofs, changed policies, missing authority, or failed
physical checks refuse the transaction. Route grading remains a separate final
decision. The physical placement check is not a replacement for the broader
release gates, thermal analysis, or manufacturing review.

## Measured progression

The read-only proposal replay (`domain-v71.json`) retains 137 owner-domain-
feasible poses out of 144, versus one in the preceding slice. These are
**necessary-domain-feasible proposals**, not 137 mechanically qualified boards.

The real v71 routing worker (`coordinator-v71/`) selected a 90-degree rotation
and approximately 1.571 mm displacement of C_SS3. Its reconnect operation took
11.309 seconds and closed `/POWER INPUT + SOURCE SELECTION/U11_SS`. The complete
180-second repair lease continued exploring other residuals; this is not an
11-second whole-board route or a routing speedup benchmark.

`admission-v71-final/result.json` independently revalidated that retained
candidate and accepted the 6-to-5 improvement in 52.757 seconds, including fresh
before/after grading. All **1,105 original copper items** were unchanged, all
20 protected fill-layer entries preserved, and no route-gate regressions were
found. USB and CAN pair qualification, the eight power-net obligations, and
decoupling checks remained intact. The input artifact families were unchanged.

The normal coordinator's residual stage subsequently reproduced and admitted
the improvement without a manually supplied target or candidate:
`coordinator-admission-v71/result.json`, 241.599 seconds including the 180-second
repair lease, placement revalidation, and fresh grading. A bounded follow-up
residual-stage pass from that result made **no further gain** (195.922 seconds,
180.043 seconds of repair). It stopped at its atomic-negotiation budget rather
than accepting an invalid route. It does not prove the remaining nets
unrouteable. These are residual-stage replays, not complete new-board
placement-to-fabrication runs; the harness does not execute the outer campaign's
search-history persistence step.

The published checkpoint is
[available on the dashboard](http://localhost:8090/?id=20260926-hub-standard-rev2-checkpoint-continuation-966962df43),
SHA-256 `966962df43269eeeb7cee4dc019a50636b46000b9b1313210e60a99d67e33bf0`.
Its top and bottom models-off renders and all six copper-layer views were
fetched successfully through the Windows localhost endpoint. The archive is
marked diagnostic, incomplete, and not release-qualified. The published board
was independently checked again in `published-trace-clearance/`; the counts
below match that exact hash.

## Spacing and cross-board regression

`trace-clearance-v71/summary.json` records 182,902 same-layer trace-pair checks.
The same 53 positive sub-nanometre shortfalls remain, with a minimum measured
gap of 0.199999927 mm against 0.20 mm. There are **zero shortfalls of at least
one nanometre**. The exact check remains flagged, not rounded into a pass.
Native KiCad reports no trace-clearance violations or shorts, and the project
has no DRC exclusions.

Raw native structural messages are not zero: 90 via-diameter, 90 annular-width,
24 copper-edge and four hole-clearance messages are independently qualified by
existing native geometry/profile policies. The raw report is retained beside
the summary; "zero qualified structural DRC" does not mean zero raw messages.

`pcie-final-control/native-control.json` freshly checks the unchanged archived
PCIe 2-port fab-review control at SHA-256
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
It remains at zero opens / zero qualified structural DRC; its native copper
and artifact family are unchanged. The existing pair-gate failure is still
reported, so this control is not claimed as newly fabrication-qualified.

## Automated regression coverage

`final-regression.log`: **974 passed, 4 skipped, 8 subtests passed** in 170.64
seconds. The warning is KiCad's existing SWIG-interface deprecation warning.
The skips are opt-in tests, not newly waived failures.

The 23 fixed-anchor proposal tests cover renamed/translated native fixtures,
front/back rotations, actual barrel containment, bounded deterministic
portfolios, domain intersections, live-dogbone ownership, duplicate pad numbers,
non-owning same-net neighbours, and filtering before occupancy top-K. The 22
placement-admission tests exercise incomplete proofs, changed rules/project,
component/copper/plan changes, fixed components, failed physical checks,
exceptions, input mutation, unfunded transitions, and coordinator gate-regression
refusal. Synthetic transaction tests mock some downstream authority checks;
the real native Hub replays above separately exercise those actual checks.

The wider suite also exercises the existing routing/checkpoint, frozen-power,
via-ownership, pair, spacing, placement-commit, process-watchdog, stage-admission,
and dashboard contracts. This is cross-board control evidence plus synthetic
generality coverage, not a claim that every board in the suite is now routed.

## Remaining work

Five nets remain open: `+3V3`, `+5V_SYS`, `/KVM_5V_IN`,
`/POWER INPUT + SOURCE SELECTION/U11_OV1`, and `/USB_VBUS`.
The pre-existing C37 courtyard-edge gate also remains: 0.475 mm measured against
0.8 mm. Thermal/injection release gates have not been qualified by this run.
Route-shape advisories remain visible: four pre-existing covered backtracks and
one new acute backtrack on the repaired soft-start net, involving a 0.017787 mm
segment. The blocking route-shape count stays zero, but cosmetic/geometry
polishing is not complete. The existing right-angle chamfer is not a general
short-segment acute-backtrack repair. A routing progress candidate must not
replace the fabrication-review release authority.

The next bounded slice should address late-stage route/placement search
allocation and generic short-segment cleanup, with the same native admission
and protected-copper requirements, rather than repeat the same no-gain lease
or hard-code another component displacement.
