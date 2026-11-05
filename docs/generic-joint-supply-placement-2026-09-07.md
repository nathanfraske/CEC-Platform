# Joint supply-group placement — 2026-09-07

## Scope and source authority

This implements the next bounded placement slice after
`generic-supply-group-compaction-2026-09-07.md`: place a multi-supply device
and its complete required capacitor set together. It does not substitute a
component-specific move for a reusable constructor.

The live manifest-selected hierarchical 12VHPWR Standard schematic is still
the source. The production run normalizes a separate working PCB from that
hierarchy before source intake. Historical root/candidate PCBs remain
reference artifacts, not schematic authority. No schematic, BOM, fabrication
process, fan assumption, connector orientation, or mounting intent changes
in this slice. The source still has 16 recognized capacitor contracts.

## Root causes and generic repairs

1. **Greedy ownership was incomplete.** The earlier constructor could seat one
   capacitor, lock its owner, and strand another input/output capacitor. The
   new bounded solver enumerates compatible whole groups. Failure commits no
   positions and no group locks; success transfers every member to persistent
   placement-cell ownership. Explicit existing cap locks are not overridden.
2. **Small nudges could not leave the original reservation.** Provisional IC
   positions inside a broad connector/bus exclusion exhausted every nearby
   ring. The constructor now reuses configuration-space obstacle subtraction
   to propose separate legal cavities. All group members contribute to the
   forbidden translation regions; a satellite cannot disappear from the
   search envelope. Exact per-member guards still decide admission.
3. **Ranking preceded necessary escape checks.** A low-cost capacitor layout
   could block a programming/signal pin or its own supply lane, consuming the
   shortlist and hiding more useful alternatives. Individual option admission
   and pairwise supply/return-lane compatibility now precede cost pruning.
   Final whole-group proof remains mandatory.
4. **Evidence travels with the candidate.** Reports retain option counts,
   search budgets, rejected proposals by category, chosen poses, cavity/local
   origin, and persistent all-member handoffs. Review records preserve failed
   evidence; an unsuccessful search is not reported as geometric impossibility.

The pure search is `scripts/cec_supply_group.py`; the topology/actual-land
adapter is `_joint_supply_layouts` and the early/late selected-device pass in
`scripts/cec_synth_pipeline.py`. The neutral module is included in the existing
anti-overfit audit. These additions introduce no board, net-name, refdes, or
coordinate special case. Existing legacy identity-dependent code elsewhere
in the coordinator is not thereby certified as fully generic.

## Search and admission boundaries

- At most 32 local options per capacitor, a 24-state beam, 4,096 compatibility
  probes, and 12 complete layouts returned per owner.
- Four rotations; local owner rings within 8 mm (164 distinct default poses,
  capped by the 196-site policy budget), then at most 196 contact-derived sites.
  Complete groups are checked at every proposed owner site.
- Contact construction is additionally bounded per layout/rotation and by the
  existing 4,096-rectangle exclusion limit. Exhaustion fails closed.
- Actual courtyards, mounting/edge/route reservations, member-region bounds,
  private pin escapes, and pads versus reserved authored copper remain hard
  checks. Explicit opposite-layer copper projection follows the earlier slice;
  it grants no trace/via crossing permission.
- Supply distances obey the existing device/project ceiling, not an invented
  manufacturer recommendation. Ordinary ground proximity is screened at the
  configured 2.5 mm bound. Rail-to-rail capacitors also require their explicit
  return-pin path. Native complete-cell construction, saved connectivity,
  reference-plane continuity and DRC remain separate required proofs.
- The already-fixed MCU and CAN owner groups are not forcibly unlocked by
  this change. A refusal there identifies an upstream group-reservation task.
- No fan cooling credit or thermal qualification is inferred from placement.

## Tests and retained probes

- `build/joint-supply-contact-tests-20260907.log`: 591 passed, 14 skipped.
  Skips are the previously absent dual-sided probe and 13 historical Hub
  fixtures, not new passing evidence.
- `tests/test_joint_supply_group.py`: deterministic bounded search, no partial
  solution, explicit final proof, translated/renamed actual adapter execution,
  pinned-member refusal, real WSON land geometry under renamed topology,
  cavity discovery and pre-shortlist option admission.
- `tests/test_placement_candidate_review.py`: failed group evidence survives
  review serialization and does not grant routing/release approval.
- `build/joint-supply-stage-contact-v3-probe-20260907.jsonl`: short early-stage
  trace from the actual hierarchy. Mux and LDO groups both seated; the pinned
  CAN group refused. This trace is not a completed board result.
- `build/12vhpwr-joint-supply-20260907`: cancelled first attempt. Its small-ring
  search exposed the cavity/escape-ranking defects above. It is not a final
  candidate run and must not be promoted.
- Final bounded cohort: `build/12vhpwr-joint-supply-contact-20260907`.
  Sizes remain 58 x 64/68/72/76/80 mm, seed 0, fresh placement, CPU backend,
  four native evaluation workers. The 64 mm connector-bank refusal remains
  recorded, without automatic outline growth.

Native complete-cell construction is exercised on disposable copies by
`tmp/replay_joint_supply_native_20260907.py`, with a 240-second external bound.
It records full before/after DRC admission, individual refusal certificates,
rollback, and an independent audit of the saved board. Generated cells in a
rolled-back proposal are diagnostic only; deferred dangling vias are never
reference-plane signoff. Baseline evidence is under
`build/joint-supply-ground-replay-20260907/baseline-68`.

## Follow-on boundaries identified during this slice

- The pinned CAN owner was seated before its complete capacitor envelope was
  reserved. This is an upstream ownership issue, not permission to move the
  owner after its critical placement lock.
- Existing sensing cells can place local supply copper yet lack legal
  immediate ground-return seats. Their blueprint/ground-return geometry must
  be qualified before stamping/locking, not patched after broad routing.
- A live stack sample during the cohort found the old single-capacitor dense
  owner/cap grid still taking substantial time. The new finite group solver
  can be evaluated for that case in a separate measured slice. Outline
  synthesis also remains serial despite parallel native evaluation.

## Final measurements and no-promotion decision

The cohort completed in **692.9 seconds** (placement stage), versus 681.725 s
for the previous slice: about 1.6% slower, not a runtime improvement. All four
generated candidates pass the same native mechanical/source-intake checks,
retain all six sensing cells / 444 locked internal segments, and retain the
complete wide power net/layer/width inventory. The previous 80 mm fallback
had an incomplete power-path inventory; the new 80 mm candidate does not.
The 64 mm bank is still refused. No further outline reduction was achieved.

For the same 58 x 68 mm comparison:

| Contract | Previous supply distance | Joint-group supply distance |
|---|---:|---:|
| LDO input C1 to U16.6 | 9.288 mm | 1.297 mm |
| LDO output C2 to U16.1 | 23.081 mm | 1.297 mm |
| Mux input C6 to U5.7 | 3.473 mm | 2.491 mm |
| CAN C4 to U2.3 | 3.132 mm | **5.171 mm — regression** |
| CAN C8 to U2.5 | 2.016 mm | **6.651 mm — regression** |

Placement residual improves from 3 to 1, but the aggregate decoupling findings
remain **12**, and native complete-cell construction remains **5 of 16** in
the disposable proposal. Gains are C1, C2 and C6; losses are C4, C8 and C27.
The LDO gains include native supply links and immediate ground entries, not
merely source-distance checks. The mux C27 remains geometrically close but
fails the native immediate-ground-return construction in the assembled group.
Seven existing reference/sensing cells still lack legal ground-return sites;
the MCU bulk C7 still fails its guarded local supply path.

Both baseline and new native construction transactions **rolled back**. The
saved-board audit consequently reports zero complete cells in either output.
The proposal counts above are not installed copper or final plane signoff.
Source placement DRC/open counts are 40/221 before and 38/223 now; these are
unrouted diagnostic placements, not routed-board DRC claims.

**The new 68 mm image is retained for diagnosis, not promoted over the prior
candidate.** Fewer placement residuals cannot compensate for the two new CAN
supply-distance failures. The next correctness slice is to reserve complete
critical-device supply groups *before* fixing those owners, and to include
collective native ground-seat feasibility before group locking. Further
single-cap search/runtime work should be a measured, separate comparison.

The immutable PCIe control's board hash, score and eight existing constraint
blockers are unchanged: **0 DRC, 0 opens, 615 tracks, 226 vias, 1242.073 mm**.
Broader current release acceptance remains false as before; this replay is
not a new fabrication approval. Its report is
`build/joint-supply-pcie-regression-20260907.json`.

The complete native same-size comparison, source/control hashes, group search
reports and journal ownership are retained in
`build/12vhpwr-joint-supply-contact-20260907/joint-supply-closeout.json`.
Native ground replay is under `build/joint-supply-ground-replay-20260907`.
No historical PCB, canonical board candidate, schematic or BOM was overwritten.

The shown 68 mm diagnostic is `02-placement/candidates/000/board.kicad_pcb`
within that cohort, SHA-256
`bcba4542a9dd34e2d07be4f7430799e29bd53ab52ca431ebfaee449761c5bbae`.
Actual no-body renders are `joint-supply-top.png` / `joint-supply-bottom.png`
beside it. Verified identical Windows display copies are
`artifacts/12vhpwr-20260907-joint-supply-top.png` and the corresponding bottom
PNG. Their banners explicitly say **DIAGNOSTIC — NOT PROMOTED**.
