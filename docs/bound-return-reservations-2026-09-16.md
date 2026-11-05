# Complete, identity-bound reservation context for return proposals

## Implemented

The local-return proposal generator now consumes the same complete frozen
reservation projection as native via admission, rather than only the truncated
first-blocker sample. `cec_local_return_feedback.bound_reservations` requires
the configured state path and SHA256 to match the authority captured in the
placement evidence. Changed, missing, invalid or incomplete state cannot claim
complete coverage. The resolver reuses `cec_power_guard_geometry.reservations`;
it does not substitute the body-clearance projection, omit inner layers or
discard unclipped physical copper.

The proposal generator excludes only its own return net and combines the
remaining rectangles with the native refusal witnesses. Whole-cell rotations,
bounded displacements, fixed ownership and exact candidate admission remain
unchanged. Moves record the authority digest and `bound_reservation_union`
provenance. Production dispatch occurs through the ordinary craft proposal
generator for all boards and only loads the authority when a return search has
actually failed. There is no product/refdes/net/coordinate special case.

This is proposal data binding, not a permission to replan or move frozen power,
and not a new clearance or current rule. An unavailable binding retains the
previous sampled proposal behavior without claiming complete obstacle coverage;
the native gate remains authoritative in either case.

## Native outcome

The same PCIe3 16-trial, one-round experiment now evaluates 27 legal variants
and accepts a complete regulator/capacitor move with one passive eviction.
Earlier sampled-union geometry evaluated 22 variants and accepted none.
The new candidate has **zero local craft blockers**, and that result survives
a freshly rebuilt power authority and independent full physical measurement.
Evidence: `build/bound-return-cell-screen-20260916/report.json`.

It is **not an accepted overall board improvement**. The independent important-
route replay still reports 11 critical failures and two refused pair edges.
The passive eviction moves one member of a split differential-pair station;
the CAN_H route is then refused for detour ratio 2.176366 against the unchanged
2.0 limit. The existing important-route gate catches the regression, so no
diagnostic is promoted. Evidence:
`build/bound-return-priority-check-20260916/report.json`.

The new full-context capability fixes a real local search omission. It does not
resolve the remaining coupling between local-cell repair and differential-pair
station ownership. Next work must preserve complete pair stations during local
eviction, or evaluate their coordinated replacement as part of the same bounded
transaction. Moving only an obstructing passive is not enough. Do not increase
detour limits, waive pair qualification or repeatedly route this candidate.

## Hub and suite checks

The first diagnostic Hub harness omitted the frozen-placement search-domain
binding. It proposed rotating an owned U7/C15 cell; the final frozen-power commit
correctly refused and rolled it back. This is a **harness limitation**, not a
production success or a newly discovered missing production domain: the actual
pipeline already binds `cec_frozen_placement_domain` before this kind of repair.
Use `build/bound-return-hub-screen-v2-20260916/report.json` for the production-
equivalent screen. Do not use the v1 trial's lower craft count as admitted gain.

The corrected v2 screen **does** commit a power-independent repair: Hub craft
blockers decrease **4 -> 3**. Frozen pours, via fields, corridors, owned nets and
excluded terminals remain identical; independent protected-copper and qualified-
pair checks pass. The PSU_5V_KVM local-return blocker is cleared. Two other U7
returns and the U3 tangent-supply blocker remain. This is a checked placement
substage improvement, not routing admission or fab signoff.

Four board families were replayed concurrently through native physical checks;
all complete physical reports remain identical. EPS/ATX remain interface-held.
The Hub's bound projection contains 238 reservation rectangles, PCIe2's 178 and
PCIe3's 258. VHP has no applicable sibling frozen authority in this read-only
path and no exhausted local-return proposals, so no context is invented for it.
All six canonical source/hierarchy signatures remain unchanged.
Evidence: `build/bound-return-replay-20260916/report.json`.

**310 tests pass** in 91.68 seconds, including production dispatch, stale/missing
state, inner-layer and same-net behavior, deterministic ownership, loaded-native
decoupler/frozen-domain checks and the existing pipeline boundary tests.
Log: `build/bound-return-tests-20260916.log`.

The historical PCIe2 control's full probe/regression/generalization payloads and
PCB hash match the preceding run. Its broader release holds are unchanged;
this is regression parity, not fab approval. The final source/control/physical/
priority comparison is `build/bound-return-qualified-comparison-20260916.json`.

No source, load budget, mechanical envelope, mating interface, protected control
or release limit was changed. No diagnostic is promoted. The bounded canonical
Hub pass subsequently completed in 260 seconds from the old hash-bound source,
**not** the diagnostic: `build/bound-return-hub-pass-20260916`. Its normal journal
reproduces 4 -> 3 blockers. Independent physical measurement matches the final
craft gate, pads/courtyards pass, and frozen power/protected copper/pairs remain
unchanged. Receipt: `build/bound-return-hub-pass-qualified-20260916.json`.

The new immutable continuation plan is `build/bound-return-next-inputs-20260916.json`.
Only the Hub input advances to that journal-qualified **blocked placement**;
the other five incumbent rows and every current-BETA source/hierarchy remain
unchanged. This grants no routing or fabrication admission and no unchanged-wave
relaunch. The full pass review is published to the dashboard under
`pass-bound-return-hub-pass-20260916-hub-standard-rev2-d09e8de6de`, with top/bottom
Windows previews in `CEC-Board-Reviews/bound-return-hub-pass-20260916`.
