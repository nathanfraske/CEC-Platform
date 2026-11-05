# Local bypass cells and exact power landing construction — 2026-09-22

Status: **measurable partial progress, not route admission or fabrication signoff**.
This is a follow-on to `hub-atx-power-construction-progress-2026-09-22.md`.
The active paired source manifest and compact incumbents were not replaced.

Follow-up: `power-grid-refinement-and-return-topology-2026-09-22.md` supersedes
the U4/C4 proximity interpretation below. Requalifying reused return topology
removes that finding and exposes U1/C36 instead; historical results below are
retained as the record of what that checker reported at the time.

## Result

The Hub now has an exact-filled power/local-cell composition with **zero structural
DRC errors**, **202 unconnected items**, and **six of eight requested power domains
admitted**. Ordinary signal routing has not started for this candidate. The prior
Hub power-prefix certificate had zero structural DRC errors and 267 unconnected
items. That is 65 fewer unconnected items, not 65 completed nets or full routing.

All 14 assigned Hub bypass cells construct without refusal. The exact filled
reference-plane check proves connectivity for all **23 of 23 required local
ground vias**. Fresh-process placement measurement reports no remaining local
return-access failure. Its sole craft blocker is a proximity finding: U4.3/C4 has
0.285 mm excess against the unchanged 0.250 mm limit. No footprint was manually
moved to obtain this result, and that finding was not waived.

| Check | Previous protected Hub checkpoint | New private composition |
| --- | --- | --- |
| Structural DRC | 0 | 0 |
| Unconnected items after exact power fill | 267 | 202 |
| Admitted requested power domains | 6/8 | 6/8 |
| Local return-access failures | 3 | 0 |
| Board outline | 84.49 × 72.2 mm | Unchanged |
| Signal routing admitted | No | No |

The ATX private pre-freeze constructor probe also built **25/25 assigned cells**
without a new non-deferred structural regression. It is only a local-cell probe:
its new ground entries still require the final filled-plane/power composition.
The compact ATX remains **78 × 95 mm, one of four force rails**, and was not
replaced by the wider diagnostic. No new ATX force-rail closure is claimed.

The new exact Hub artifact paired with the compact ATX passes the existing
declared body/vent/assembly checks and all **18 mating contacts**. This preserves
the dead-bug transform, approved two-cap positions and mechanical datum policy.
Physical sample, supplier/tolerance, cable/latch, thermal, hold-up and fabrication
qualification gates remain open; this is not a blanket mechanical qualification.

## Generic root-cause fixes

1. **Construct local bypass copper before prospective power allocation.** The
   ordinary admitted local-cell constructor formerly ran too late to inform the
   frozen power plan. `cec_prefreeze_local_pi.prepare` now makes its supply and
   return geometry an input. Existing copper is not ripped up. Failed construction
   aborts this transaction instead of publishing an incomplete certificate.
2. **Carry the same local copper through the stage boundary.** Generated UUIDs,
   terminal geometry and fabrication groups are captured in the existing exact
   replay contract. Final materialization proves the actual reference-plane
   entries. Placement measurement replays that same contract only when its exact
   admission binds the current PCB bytes; it does not solve a different local
   route against an already frozen reservation.
3. **Test full via lands after actual clipping, inside the bounded search.** A
   legal drill centre is insufficient when the surrounding copper is cut away.
   The over-under search now checks the complete field on both transition layers
   after the same realizer and clipping operations used by production. Typed
   refusal feeds its existing bounded retry mechanism; current requirements,
   field counts and clearances are not relaxed.
4. **Return source-side placement evidence too.** A failed transition previously
   reported only the disconnected destination cluster. Nearby current-authority
   terminal clusters at rejected field proposals are now additional evidence for
   the existing complete-cell placement proposals. They are proposals, not proof
   that the nearby component is the cause; identity/net/position checks and exact
   admission still apply.
5. **Use the same body exclusions for fields and outlines.** The forensic trace
   proved that the field generator accepted sites under a foreign component
   body, after which the outline clipper removed their F.Cu landing. Field seating
   now applies the shared mounting-face body exclusion, including the full land
   collar, before selecting sites. Only actual transition faces are constrained;
   inner layers are not blocked by projecting a surface body through the board.
6. **Quantize polygon topology before export and retain holes in exact replay.**
   Independent coordinate rounding collapsed a tiny feature into a backtracking
   edge, producing a self-intersecting B.Cu contour. The exact overlap consumer
   then discarded that layer as invalid. Polygon export now quantizes valid
   topology at the existing 0.001 mm export grid, preserves holes and removes
   zero-area features. Arbitrary invalid source geometry is refused. The exact
   via-overlap consumer also retains polygon holes instead of treating them as
   available copper.

These production changes contain no Hub/ATX product selector, reference-specific
move or board-coordinate repair. Synthetic fixtures cover translated scenes,
front/back mounting faces, transition layer selection, hole exclusion, collapsed
necks, invalid input, exact handoff identity and bounded failure feedback.

## Bounded run and remaining work

One full Hub attempt was completed before the final body/quantization corrections.
It made 12 bounded complete-cell proposals: five failed power reconstruction,
six failed physical placement, and one passed exact power but failed the unchanged
post-authority proximity gate. None was accepted. Subsequent cause-specific
probes reproduced the failures and established the corrected exact composition
at the **original incumbent poses** in 35.54 seconds. No unattended retry loop
was started.

Remaining Hub blockers in this evidence:

- `/CAN + FOUR MODULE PORTS + STACK/VCC_P2`: no required-width connection to its
  declared terminal cluster.
- `/POWER INPUT + SOURCE SELECTION/PSU_5V_KVM`: no required-width connection to the
  current-authority IC terminal cluster.
- One local proximity excess: 0.285 mm versus 0.250 mm.
- Full priority/signal routing and all downstream release checks remain to run.

Next work should repair these through the generic placement/power transaction,
then rerun route admission. Do not replay unchanged full waves or promote this
partial power prefix as a completed board.

## Validation and receipts

- **499 tests passed**, two dependency deprecation warnings, 177.62 seconds:
  `build/hub-atx-local-access-20260922/final-tests.log`.
- Fresh PCIe 2-port control replay retains **0 DRC, 0 unconnected, 0 fabrication
  blockers and 0 route-craft issues**, with its control bytes unchanged. Its two
  already documented release findings remain: RS1 Kelvin departure and CAN
  adjacent-filled-ground coverage. Therefore the full release regression is
  still false; the non-regression terms and core generic-module audit pass.
  The legacy full-pipeline generalization audit is still false; this slice does
  not claim to make the entire historical pipeline generic.
- Control receipt: `build/hub-atx-local-access-20260922/pcie2-final-regression.json`.
- Main exact artifact: `build/hub-atx-local-access-20260922/hub-quantized-power/exact-preview.kicad_pcb`.
- Exact fill/local-plane receipt: sibling `exact-preview.state.json`.
- Fresh physical measurement: sibling `physical-recheck.json`.
- Body-clipping witnesses: `build/hub-atx-local-access-20260922/hub-landing-forensic-v2/landing-clips.json`.
- Hub and ATX constructor-only receipts: `hub-prefreeze/report.json` and
  `atx-prefreeze/report.json` under the same run root.
- Pair receipt: `build/hub-atx-local-access-20260922/paired-validation/paired-progress-validation.json`.
- Full bounded attempt: `build/hub-atx-local-access-20260922/hub-full-pass`.

The dashboard publishes the **actual exact-preview PCB**, not its open placement
seed, with model-free top/bottom renders and an explicit NOT SIGNAL-ROUTED label:

`http://localhost:8090/?id=20260922-hub-standard-rev2-local-power-progress-5f14bc8772`

Windows-side page and image requests both returned HTTP 200. Artifact SHA256:
`5f14bc877217ce8040179b9de50c34253a3862aa9486ac2df0dc04525c5b137d`.

Protected inputs remain byte-identical:

- Active pair manifest: `dfbeccb8eca4331c53c92c95b77d82dea03d4d8f396effda2860ca1d99882463`.
- Hub v8 incumbent: `cbfe6b6f1e105a001356bad4c5e730d527264ed26618965cfd4a5f55380cd1b7`.
- Compact ATX v3 incumbent: `83799200c0dae6ddd158d66de1e43d548a34547bd59b8d29539d929ac3d7814b`.
- PCIe 2-port control: `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
