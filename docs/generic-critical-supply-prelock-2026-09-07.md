# Critical supply groups before owner locks — 2026-09-07

## Scope and causal repair

The preceding joint-supply slice improved the LDO but regressed the CAN
capacitors. The cause was ordering: the critical-seat stage committed the IC
body before reserving its whole supply group. The later joint constructor
correctly respected that owner lock, but could no longer rotate the package
to create enough room for both capacitors.

The critical-seat boundary now enumerates the source-required multi-capacitor
group before creating a new owner lock. It uses actual package/pad geometry,
bounded four-rotation group layouts, a native local supply/return screen, and
whole-group obstacle-derived seating. Success transfers every member through
the existing persistent cell-ownership journal. Failure must not invent a new
fixed critical owner. Pre-existing user and blueprint locks remain authority.

This is a generic topology/geometry rule, not a named CAN/U2/C4/C8 move.
`scripts/cec_supply_group.py::seat` is the pure bounded placement primitive;
`scripts/cec_supply_native.py` owns the isolated native screening worker;
`scripts/cec_synth_pipeline.py` invokes them before the critical lock boundary.
The new worker is included in the existing neutral-module anti-overfit check.
This does not certify all legacy identity-dependent coordinator code as generic.

## Proof boundaries and budgets

- Source geometry uses current hierarchical component identity, footprints,
  properties and nets. The reference PCB contributes design rules, netclasses,
  fabrication properties and layer count only. No reference footprints,
  tracks, zones or placement are imported.
- The worker tests at most 12 shortlisted layouts in a subprocess with a
  60-second bound. Missing geometry, timeout or worker failure cannot grant a
  new critical group lock. Exact supply and ground construction and the
  configured supply/ground distance limits must all pass.
- This is **isolated local feasibility**, not final board connectivity, plane
  continuity, thermal qualification or DRC signoff. The final placed group may
  meet foreign copper, board edges or a different routing-grid context.
- The current local geometry is front-side. Mirrored/mixed-face groups fail
  closed pending a face-aware proof; they never inherit a front-side coupon's
  approval. A pinned follower likewise cannot accidentally create a new owner
  lock without a complete group. The pinned follower itself remains unmoved.
- Existing later placement proposals still face their full-board native
  admission check. They do not gain native approval from source distances.
  An isolated refusal cannot prove that sharing a neighbouring device's
  ground entry will be impossible on the assembled board.
- The existing geometric beam remains 24 states / 4,096 compatibility probes,
  with 32 cap options and 12 complete groups. Seating uses at most the policy's
  196 local and 196 obstacle-contact owner sites. Failure is bounded-search
  exhaustion, not proof of global geometric impossibility.

## Source and comparison controls

The manifest-selected hierarchical `beta/12vhpwr-standard` source remains
authoritative. The full pipeline normalizes a separate working PCB before
intake. No schematic, BOM, fan cooling assumption, connector direction,
mounting requirement, canonical candidate or archived board was changed.

The fresh cohort is `build/12vhpwr-critical-supply-prelock-20260907`: seed 0,
plain strategy, fresh placement only, four native evaluation workers,
58 x 68/72/76/80 mm. The 58 x 64 mm I/O-bank refusal is retained. This is a
placement comparison, not a routing wave or a request for automatic growth.

Independent measurements compare both retained cohorts:

- `build/12vhpwr-joint-supply-contact-20260907` (immediate predecessor).
- `build/12vhpwr-supply-copper-guard-compact-20260907` (earlier baseline).

The PCIe fab-review archive is immutable. Its fresh replay remains 0 DRC,
0 opens, 615 tracks, 226 vias, 1242.073 mm, with the same eight broader
constraint blockers. Diff-pair/release acceptance remains false. This is
non-regression evidence, not a new manufacturing approval.

## Test and probe evidence

- `build/critical-supply-tests-20260907.log`: 612 passed, 14 existing skips.
- New tests exercise actual critical-lock/anneal adapter behavior under renamed
  references and translated coordinates, complete-group success, search
  refusal, existing pins and blueprint ownership; pure whole-group cavity
  search; real native WSON groups under renamed topology; reference-geometry
  exclusion; supply/ground distance refusal; native timeout/error refusal;
  and critical-group evidence retention in review JSON.
- `build/critical-supply-pcie-regression-20260907.json`: unchanged archive
  score and blocker set.
- `build/critical-supply-pcie-stage-probe-20260907.json`: the same early stage
  on the PCIe hierarchy also reserves all three members, automatically rotates
  the owner 180 degrees, and journals all-member ownership. Stage time is
  about 1.4 seconds. This stops before later placement, does not rewrite the
  routed control, and does not claim a newly placed PCIe board is routed.

## Additional measured limitations

A separate short mux-group investigation found all 12 isolated shortlisted
layouts refused: an owner ground entry is obstructed and one supply route
exceeds the local path-length bound. These are concrete native refusal
certificates, not justification for widening the permitted local loop.
The investigation is `build/critical-supply-late-probe-20260907.jsonl` and
predates narrowing the new mandatory isolated gate to critical-owner locking.

Live stack samples during the fresh cohort still identify the older dense
single-owner/single-cap grid as a runtime hotspot. That constructor and the
serial outline synthesis deserve a separately bounded performance/correctness
slice; this change does not claim to accelerate them.

## Completed comparison

The placement stage finished in **789.4 seconds**, versus 692.9 seconds for
the previous slice: approximately **14% slower**, not a speed improvement.
All four candidates retain the same 16 recognized supply requirements,
103 source components / 110 native footprints, four required mounts, fitted
fan header, right-facing lower I/O bank, and six sensing cells / 444 locked
internal segments. Native mechanical and source-intake checks pass.

| Height | Placement residual | Decoupling findings | Wide-power inventory |
|---|---:|---:|---|
| 68 mm | 1 | 12 | Preserved |
| 72 mm | 0 | 12 | Incomplete — excluded |
| 76 mm | 2 | 12 | Incomplete — excluded |
| 80 mm | 0 | 12 | Preserved |

For the same **58 x 68 mm** board, C4→U2.3 improves from **5.170847 to
1.802422 mm**, and C8→U2.5 from **6.650959 to 1.843509 mm**. Both are also
closer than the earlier copper-guard baseline (3.132491 / 2.015564 mm).
The preceding LDO and mux supply-distance gains are retained. All 16 supply
distances now meet their configured ceilings; this is not equivalent to
passing all decoupling practices. C8 still has a 0.40 mm isolated-tangent
proximity-excess finding, and MCU bulk / reference ground limits remain open.

Native construction on the complete 68 mm placement proposes **8/16 cells**,
versus 5/16 before. The gains are C4, C8 and C23, with no formerly constructed
cell lost. **Only seven proposed cells also satisfy the source distance
limits**: C23 still exceeds the 2.5 mm ground-pin limit. The complete native
transaction still rolls back and the saved-board audit reports **zero owned
cells**. Eight proposed constructions are not eight installed/qualified cells.
The six sensing-cell ground entries, mux C27 ground entry and MCU bulk C7
supply path remain refused. Aggregate decoupling findings remain **12**.

The compact 68 mm board is retained for diagnostic review, **not promoted or
routing/release-admitted**. Its SHA-256 is
`90067b7f95fd9490f4954529fa29528187580f8fc20a0c6b3cd48607b0d33f2b`.
No additional compaction was established by this slice.

## Newly exposed power-copper reporting gap, repaired generically

The 72/76 mm candidates lost the sixth lane's required power copper. Exact
constructor replays identified an ordinary USB ferrite pad obstructing that
lane: `HI vs FB1.1 [/VBUS_F]` at (36.9,20.7) / (36.9,29.7). These coordinates
are diagnostic evidence, not implementation exceptions or repair instructions.
The late topology-rotation pass changed this part from 270 to 180 degrees.
A diagnostic ablation on separate copies restored the earlier 270-degree
orientation and recovered 6/6 required lanes in both cases. That isolates the
late rotation's missing future-power-path admission check. The ablation boards
are not promoted or substituted for an automatic pipeline repair.
The producer correctly refused the collision. The process defect was that its
refusal was printed but omitted from the placement sidecar: a clean report
for six sensing cells did not also prove that six required power lanes existed.

Both materialization paths now persist every authored-lane result. The
placement admission reader requires complete, explicitly reported power
construction when that constructor is enabled; absent, empty or refused
results fail closed. It derives counts and labels from the returned inventory,
not a board name, refdes or coordinate. Successful sensing-cell construction
cannot mask omitted required power copper. Existing historical reports lacking
that evidence must be re-evaluated, not silently treated as complete.

`authored-copper-replay.json` records exact-seat disposable rebuilds: 68/80 mm
are 6/6 and pass that term; 72/76 mm are 5/6 and fail with the offending pad
retained. These are constructor probes, not replacement boards. Candidate and
control hashes remain unchanged. Upstream placement/rotation still needs to
consume those required-path conflicts before commitment; no named ferrite was
manually moved here. That is a measured next generic admission/feedback task.

## Final validation and display provenance

After the cohort finished, refusal-branch hardening and the report/admission
repair were added. `final-guard-stage-equivalence.json` independently replays
all four early critical stages and proves unchanged critical-group positions
and ownership journals. The entire long placement cohort was not rerun after
these guards; the exact-seat copper rebuilds exercise the new materialization
evidence and admission behavior. A final broad test log and PCIe control replay
are retained under `build/critical-supply-final-*20260907*`.
Final broad results: **622 passed, 14 skipped** in 104.55 seconds. The final
PCIe score and all eight existing constraint blockers remain unchanged.
`git diff --check` passes. The cohort and diagnostic copies occupy about 22 MB.

`critical-supply-closeout.json` contains both prior-cohort comparisons, native
source/pad measurements, original/control hashes, persistent group ownership,
native construction and rollback, authored-copper replays, and final early-stage
equivalence. The top/bottom renders are generated from that report's exact
68 mm board, with no 3D bodies and **DIAGNOSTIC — NOT PROMOTED** banners.
Verified Windows copies are under `artifacts/12vhpwr-20260907-critical-supply-prelock-*.png`.

No thermal credit, schematic/BOM update, canonical board replacement, routing
completion, or fabrication approval is implied.
