# EPS and ATX compaction / current-interface rebuild — 2026-09-12

## Correction after independent terminal inspection

Follow-through: `docs/native-placement-copper-and-mating-resume-2026-09-12.md` records the implemented shared admission/resume fixes, native spacing probes and protected-control regression. The interface geometry itself remains unqualified and blocked.

**Neither compact candidate is physically accepted or route-ready.** The earlier courtyard-only interpretation was incomplete. The owner correctly challenged the screw-terminal spacing. Native pad inspection and independent KiCad DRC establish terminal copper shorts on both EPS and ATX; the final EPS replay also has two real terminal courtyard intersections. No fab promotion occurred.

The shared row compiler budgets nominal body widths, body tolerance and positional error, producing 7.0 mm pitch for neighboring T340 terminals. However, the actual four-pad T340 footprint, rotated into these rows, has a 7.5 mm lateral copper envelope. Adjacent pads on different nets overlap by approximately 0.5 mm. The declared courtyard is narrower than this copper envelope, so a positive courtyard gap does not prove electrical clearance. This is a footprint-envelope / mating-policy defect, not a routing problem that more routing waves can solve.

The selected EPS trial and final ATX board have no exact terminal courtyard intersections (neighboring T340 courtyard gap is about 0.11 mm), but both have terminal pad shorts. In the final EPS replay, a later courtyard repair moved TB11 and TB21 individually by -0.6 mm in X. That created TB11/TB13 and TB21/TB23 courtyard intersections, each approximately 4.7236 mm². The continuation path restores mechanical pins for placement-work checkpoints but not placement-review candidates; the latter do not carry the corresponding pin context. Thus the required-position overlay described below did not protect the row throughout continuation.

Copied footprint children also retain duplicate UUIDs, which can misattribute native DRC items to the wrong reference. Diagnostic copies were processed with the existing duplicate-ID repair: 377 repeated occurrences on the selected EPS copy and 622 on the ATX copy. Removing UUID fields before comparison proves all other PCB text was unchanged. Correctly attributed DRC still reports the terminal shorts: 48 shorting rows on EPS, and 36 shorting plus 24 clearance rows on ATX. These are report rows, with repeated layer findings, not counts of unique physical short sites. Original boards were not modified.

The inspected current PCIe two-port and three-port artifacts have no terminal courtyard/copper violations in this targeted check. This does not certify their other circuitry or substitute for their full release gates.

Evidence:

- `build/terminal-clearance-audit-20260912/report.json`: exact courtyard intersections and independent native DRC for all five inspected artifacts.
- `build/terminal-clearance-audit-20260912/unique-identities/report.json`: duplicate-ID cross-check, unchanged-source/geometry proof and corrected attribution.

Required follow-up is generic: validate actual rotated copper envelopes as well as body/courtyard envelopes; carry rigid mating constraints through every continuation and repair; ensure generated item identities are unique before diagnostics. Reconcile any corrected pitch with both mating boards and the fixed maximum interface span. Do not shrink pads, waive clearance, move isolated terminals or silently enlarge the interface to make a screen pass. The footprint and physical mating qualification remain provisional; no physical terminal geometry repair is claimed by this report.

## Scope and source authority

The owner requested continuing compaction and including EPS and the 24-pin stack. EPS here is the single current `eps-8pin-rev3` product with two ports, not an additional EPS variant. 12VHPWR's dimensions and the previous slim-M2 ECO are unchanged by this slice. No electrical operating assumptions, load budgets, BOM or schematics were changed.

The latest interface-repair outputs are the inputs, rather than the older manifest staging PCBs or the pre-interface six-board pass. Both selected artifacts match their pipeline journals and their interface-ECO certificates:

- EPS: `build/mating-repair-20260911-i/eps-8pin-rev3/02-placement/board.kicad_pcb`, SHA256 `f834e3de8be286b6cd81670cae23bcb82efbaddf16ee168b8bcd14fca22b7fc6`.
- ATX: `build/mating-repair-20260911-i/atx-24pin-rev3/02-placement/board.kicad_pcb`, SHA256 `b35abf8bd31463a90f7f44c844719152f85e4d526140180ee529ff35747fa56e`.

Receipt: `build/eps-atx-compaction-inputs-20260912.json`. The current canonical ATX PCB is an older outline-less staging cloud, whereas the selected repaired candidate has 129 footprints and an 86 × 95 mm outline. Reverting to staging would discard useful placements. Invalidated interface copper must nevertheless not become route authority.

## Two generic repairs

1. **Rebuild a verified interface ECO without reverting its placements.** Explicit replacement plus explicit derived-input permission may now normalize a hash-bound, invalidated interface-ECO working copy. The source remains untouched. Ordinary derived continuation still cannot strip copper; fresh-only derived replacement retains its existing refusal. Missing/changed rule files, changed PCB bytes and incomplete publication fail closed. Normalization only clears invalidation after proving the working copy current and copper-free; normal live hierarchy/electrical intake follows. Reports distinguish the canonical manifest PCB from the actual normalization input.
2. **Materialize rebound mechanical anchors.** Outline variants already rebound the terminal macro in configuration, but incremental placement could retain the old native poses. The generic `bind_required_positions` overlay now applies exact numeric datums before collision legalization, so the complete output macro moves together and its newly displaced neighbors are considered. Lock-reason strings do not invent poses; missing, malformed or non-finite exact anchors fail. No board, reference or coordinate repair conditions were added to the helper.

Native checks prove both normalizations retained **every footprint pose**, emitted no tracks/vias/non-rule copper zones, and left both source files unchanged. All actual selected terminal poses agree with their target-outline macro (including equivalent -90°/270° rotations). The ATX mezzanine segments and H1 remain at their original fixed datums. The shared output-mount audit reports no nominal pin-order, pitch or body-gap findings for these two selected main boards. As established above, that body-only audit missed actual pad shorts and is not physical clearance approval, measured 3D fit or physical anti-mismatch qualification.

Evidence: `build/eps-atx-compact-verification-20260912.json`.

## Bounded initial compaction pass

Two concurrent board jobs, each with three exact-evaluation workers and a 540-second work deadline. No engine changes occurred during the pass. All source/engine stability checks passed. Existing outlines were never expanded.

| Board | Starting size | Smaller trial (not accepted) | Geometric size change only | Candidate-stage electrical status |
| --- | --- | --- | --- | --- |
| EPS | 96 × 40 mm | **92 × 40 mm** | 3840 → 3680 mm², **4.17% smaller** | Zero decoupler violations; three high-current corridor failures remain. |
| ATX 24-pin | 86 × 95 mm | **82 × 95 mm** | 8170 → 7790 mm², **4.65% smaller** | Three decoupler findings; high-current corridor/placement-craft blockers remain. |

Both smaller initial trials have zero native courtyard overlaps and pass pad containment, but this incomplete screen missed terminal copper shorts. Neither size reduction is an accepted physical improvement. ATX's baseline and 82 mm trial both have three decoupler findings in this exact comparison; do not compare that candidate-stage count to an older final-stage count as if criteria were identical.

EPS tested five candidates in 59.821 seconds. The 88 × 40, 96 × 36 and 96 × 32 mm trials each have ten overlaps; height reductions also worsen decoupling. ATX tested three candidates in 78.211 seconds. Its 78 × 95 mm trial has five overlaps and is rejected. ATX height was not reduced because stack access needs joint verification.

Candidate records:

- `build/eps-atx-compact-pass-20260912/eps-8pin-rev3/02-placement/candidates/003/board.placement-review.json`; PCB SHA256 `04e78d87c8a3ce809608eede823b5de7b89a0751306682435877af942963751c`.
- `build/eps-atx-compact-pass-20260912/atx-24pin-rev3/02-placement/candidates/001/board.placement-review.json`; PCB SHA256 `1ffe72e63ba4c7d6cba62f0f23fe4f040325c78ad44d16100c82a1ca29938e24`.

## Newly exposed joint-stack access issue

The nominal stack access proof still uses a 74 mm Hub, but the actual latest compact Hub is 84 × 80 mm. The previous Hub was also 80 mm tall, so this defect was not introduced by the latest width reduction.

All three actual mezzanine origins and H1 agree on the same dead-bug transformation: reflect X, then translate by (86.0, 9.8) mm. Under that transform, the actual Hub silhouette occupies (2.0, 9.8) to (86.0, 89.8) mm in the carrier frame.

The actual ATX input connector's courtyard starts at Y=84.605 mm, so it overlaps that silhouette by **5.195 mm**, rather than providing the declared 1.2 mm planar access guard. Two larger output-terminal courtyards have only **0.105 mm** gap. The auxiliary output header courtyard also lies inside the silhouette. These are planar access failures, not claims of a hard 3D body collision across the 18 mm stack gap.

Evidence: `build/live-stack-access-20260912.json`. This readback uses actual native boards and courtyard geometry, not the obsolete nominal-outline arithmetic. The 24-pin board's height must not shrink while this remains unresolved. The next joint mechanical search should first recover Hub height / rearrange the paired assembly, not automatically enlarge the carrier or independently move a single mezzanine segment.

## Validation and follow-through

The combined regression suite passes **511 tests in 90.52 seconds**, including the new source-ECO boundaries, native pose retention, required-anchor overlays, outline resizing, mount contracts, craft retention, routing guards, preview/continuation tests and the paired assembly-access checker. Log: `build/eps-atx-compaction-final-v2-tests-20260912.log`. These tests do not yet cover the newly identified copper-envelope / review-continuation defects; passing tests did not qualify these candidates.

A bounded full-admission replay of both compact trials completed under `build/eps-atx-compact-admission-20260912`. Both failed admission; no residual routing or fab promotion followed. EPS finished at 92 × 40 mm in 250.768 seconds with zero decoupler findings, courtyard failures and three high-current corridor failures. ATX finished at 82 × 95 mm in 165.412 seconds with three decoupler findings, four force-rail refusals and five high-current corridor failures. The independent terminal findings above are additional evidence explaining why courtyard-only summaries were insufficient.

The new generic `cec_assembly_access.py` checker uses actual board outlines, rigid paired datums and declared port courtyards. Its report `build/eps-atx-live-assembly-access-20260912.json` confirms the stack-access failures described above. It is presently an independent paired review check, not automatically integrated into per-board signoff.

The protected PCIe two-port fab-review control was not modified. All four control probes match the earlier control report exactly; it retains zero DRC errors and zero unconnected items. Evidence: `build/eps-atx-compaction-control-20260912.json`. This does not override any broader release gate.
