# Routed-prefix power continuation, 2026-09-23

## Scope and source

This is a generic pipeline repair, exercised on the current Standard Hub
checkpoint `build/usb-constructive-20260923/usb-clean-final-proof/board.kicad_pcb`
(SHA256 `3a41e9c2f0d76753815d29d8eb13dc548377bbb86e92d5f9f34b687752b84818`).
That source has zero native DRC and 191 unconnected items. Its USB and six CAN
branches are complete. No schematic, BOM, placement, outline or stack-mating
change is part of this slice.

## Root causes

1. Routed-seed intake used the union of physical pours and prospective power
   reservations to authorize copper evacuation. Four retained CAN tracks
   overlapped a future reservation, not a physical power zone. The source PCB
   contained only its two GND reference planes. Intake now uses actual laid
   power-zone authority. Prospective conflicts must be resolved at the exact
   power boundary; final native, incursion and connectivity gates remain.
2. The local-PI/Kelvin/power barrier replayed the old field, but did not reach
   the existing reconciliation/replanning machinery on refusal. A proposed
   VCC_P1 barrel at (16.313, 15.7) mm conflicts with native CAN copper on In2.Cu.
   With the other proposed barrel fixed, the overlap cannot fit the complete
   field at the original barrel spacing. These coordinates are diagnostic
   evidence only, not implementation constants.
3. Independent examination of the first successful recovery found a second
   coverage defect: the broad-pour filter interpreted wide locked local
   connections as completed supply trunks. It omitted +5VSB and +5V_SYS from
   the fresh solve. The six remaining domains connected, but the original
   eight-domain obligation did not. A successful sub-solve is not proof of
   complete power delivery.
4. The bridge planner already supplied a typed failure certificate, but its
   exception could occur before the state file was written. The enclosing
   power compiler kept only the exception string. Consequently its existing
   bounded failed-net-first reorder never ran for this failure class. The
   structured certificate now survives, feeds the same three-round maximum
   per layer policy, and remains available to downstream failure projection.

## Recovery boundary

`cec_local_power_prefix` now tries ordinary replay first. If the bound plan is
complete but its managed power zones are not yet physically present, a
supervised native worker tries one local reconciliation and one full power
replan. Existing managed power zones prohibit this fallback. Existing tracks,
vias and placements remain protected by the parent-copper and placement
contracts. The native worker uses the shared operation/campaign deadlines,
durable progress, failure evidence and process-group cleanup.

The returned exact state is transferred with the returned board; a copied
placement-era sidecar cannot silently replace newly admitted via seats or
power reservations. Final admission still checks native DRC/connectivity,
ground returns, local decoupling, qualified pairs, and unchanged input copper.
The barrier also captures every original frozen/declared power obligation
before solving and checks their native source/sink connectivity afterwards.
This prevents success by silently shrinking the set of rails being tested.

Broad-pour suppression now requires native source/sink connectivity, falling
back to complete locked-subgraph ownership only when no rated domain exists.
It does not change geometric protection of wide locked copper: a partial
trunk stays fixed, but cannot stand in for its missing global supply path.

## First measured result and limitation

`build/power-prefix-continuation-20260923/barrier-v1/report.json` records a
39.960 s native replay, 0 DRC / 185 opens, with all 340 parent copper items
preserved. Pair physics, native source integrity and placements pass. The
independent proof in `independent-proof-v1.json` confirms six connected power
domains, zero laid-pour incursions, unchanged controls, and explicitly finds
the two omitted supply domains still disconnected. This checkpoint is partial
routing evidence, **not a complete power-stage or fabrication certificate**.

The first normal two-candidate continuation is under `full-pipeline-v1/`.
It starts from the original immutable 191-open checkpoint, not the manually
selected recovery output. Both candidates passed the repaired local barrier
and reached actual native routing. Three critical-control nets and additional
signal nets completed in intermediate stages. The later current tier refused
the omitted +5VSB domain and its current-width gate; these candidates were
withheld and the selected incumbent remained 0 DRC / 191 opens. Do not count
those intermediate signal completions as retained final progress.

## Full power-obligation repair result

`barrier-v2` exercised all eight obligations, refused in 20.803 s, and exposed
the lost bridge-exception feedback. `barrier-v3` then completed in 79.264 s
with the structured-feedback fix:

- **0 native DRC / 180 unconnected**, versus 0 / 191 at input.
- **All eight original rated power domains connected**, including +5VSB and
  +5V_SYS; this is source/sink closure, not a claim that every sense/load branch
  or the whole board is routed.
- All 340 parent copper items retained; placements and input authority family
  unchanged. No component, reference, coordinate or net-name exception added.
- USB and CAN saved-board pair physics/reference checks pass; no foreign
  track/via incursions in actual laid power zones.
- 287 tracks, 73 vias, 22 zones. The code was unchanged during the replay.
- The selected solve automatically promoted the reported constrained supply
  to first place; selected candidate 1, feedback round 1. No requirement for
  current, via count/diameter, trace width, clearance or stackup was relaxed.

Independent evidence: `independent-proof-v3.json`, `barrier-v3/report.json`,
`barrier-v3/seal.json`, and the typed refusal/retry history under
`barrier-v3/recovery/`. Saved-board SHA256:
`0655fcf2a1c50e5c553e61bab146475cc17e8d230aaed719028269fe3300e503`.

The models-off top/bottom renders and all six native copper-layer SVGs are
archived as `20260923-hub-power-prefix-verified-0655fcf2a1`. Dashboard catalog
and panel endpoints were checked from Windows. The earlier six-domain archive
is explicitly marked incomplete, not silently replaced with the new picture.

The final normal continuation uses `full-pipeline-v3/`, again starting with
the original 191-open checkpoint so it must exercise recovery automatically.

## Retained signal-routing progress and bounded-run result

The normal run passed the repaired power barrier in both workers (81.218 s
and 85.677 s). It then completed critical-control routing and the first
signal-access tier. Candidate 0's completed `pre-power-signal-access` artifact
was copied and independently rechecked by the existing native prefix verifier
before subsequent global-route processing:

- **0 native DRC / 140 unconnected items**: 51 fewer than the original 191
  (26.7%), including 40 fewer than the complete power checkpoint's 180.
- Every original rated power domain remains source/sink connected. This does
  not imply that all branches on those supply nets are connected.
- USB and CAN remain connected and pass the saved-board pair checks.
- All 360 copper items in this candidate's power-prefix ancestor are retained;
  that ancestor preserves all 340 original input items. Placement and physical
  power-zone declarations are unchanged. There are no foreign-on-laid-pour
  incursions and no new topology/structural faults in the score comparison.
- The artifact was refilled and measured from disk. It is a continuation
  checkpoint, **not a release-approved or fabrication-ready board**.

Retained artifact:
`build/power-prefix-continuation-20260923/signal-stage-proof/board.kicad_pcb`
(SHA256 `1030fa1e79472c2740e592ba34b10a1842a803f85fcd39e0a94fae2d129daa90`).
Its sibling `report.json` records the fresh checks, `parent-prefix.json`
preserves the admitted power ancestor's receipt, and `retained-parent.json`
maps that ancestor to the separately preserved `parent/` artifact family.
The checkpoint and ancestor survive candidate-directory cleanup.

The dashboard archive is
`20260923-hub-signal-progress-1030fa1e79`, with top/bottom models-off renders
and all six native copper-layer SVGs. Its catalog entry and all eight panels
returned successful responses from Windows:
<http://localhost:8090/?id=20260923-hub-signal-progress-1030fa1e79>.

Both workers subsequently ran all four requested global Freerouting passes
(122.980 s and 128.229 s). The remaining generation budget expired during
post-route processing, before either worker returned a final admitted result.
The executor reports `worker generation exceeded 618.7s with 2/2 task(s)
pending`; this is a wall-budget termination, not evidence of a proven
deadlock. The route stage took 653.769 s including handling/cleanup. No matching
route workers or Freerouting processes remained at the final process check.
Internal Freerouting `togo` counters are not native final connectivity counts.

The coordinator consequently selected the untouched **0 DRC / 191-open
incumbent**, and the full run is **WITHHELD**. The **140-open result is a
separately retained and verified intermediate checkpoint**, not that run's
automatically selected winner. Automatic promotion of qualified intermediate
checkpoints on cancellation/timeout remains a generic orchestration gap.
The next slice should retain such checkpoints transactionally with their
authority families and native proofs, then resume residual routing from the
best admitted checkpoint instead of repeating power and critical routing.
Missing worker reports must remain unknown, not be represented as measured
DRC regressions. This turn did not implement that checkpoint-promotion fix.

Remaining work includes the 140 open connections, the recorded C37 edge-policy
finding (0.475 mm versus 0.8 mm), and current-injection/thermal and hardware
qualification gates. No thermal solve, assembly clearance change, or whole
suite routing improvement is claimed by this Hub-only slice.

## Controls

The final broad test replay passed **1,306 tests and five subtests**. The native
PCIe two-port control remains 0 DRC / 0 unconnected; its earlier release-only
findings are not waived. The active Hub/ATX pair manifest, original CAN source,
Hub placement, ATX placement and PCIe control hashes match the previous
checkpoint receipts. See `independent-proof-v1.json` and `pcie-control.json`.
The stronger pour-suppression rule was replayed on both the original Hub and
the PCIe control: it restores exactly the Hub's two incomplete obligations
while leaving all 17 PCIe suppression decisions unchanged. See
`hub-source-suppression.json` and `pcie-suppression.json`.
