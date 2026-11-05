# Hub current-path qualification and latest 12VHPWR initial placements

Date: 2026-09-06. Status: scoped pipeline repairs and initial placement experiment
completed. Neither board is released for fabrication. Original PCB files and the
archived PCIe control were not overwritten.

## Latest-source verification

Three independent checks were used, rather than treating a recent filename as
authority:

1. Fetched origin. The active repair branch is at
   `069a4126ac4ad5ca7ab51012483491c31b0ac521`; `origin/main` is at
   `fd7114e7cf589ec53018f5a80d046754d8bf2131`. Their tracked
   `beta/12vhpwr-standard` trees have no differences. No newer fetched remote
   12VHPWR source was found.
2. The current-BETA manifest identifies the root hierarchy
   `beta/12vhpwr-standard/12vhpwr-standard-module.kicad_sch`, with its numbered
   child sheets. The August component audit independently describes the same
   U16 TLV75533PDRVR, U5 TPS2121, ESP32-S3-MINI and six INA240 channels.
   **The latest schematic is not the older U3 buck-converter candidate.**
3. Live intake was run against both saved PCBs. Both failed schematic sync.
   The root staging PCB lacked 13 current parts and retained obsolete U3;
   the saved routed candidate was also stale and had incorrect DNP state.
   A new working copy was synchronized from the hierarchy, then all four
   final materializations independently passed source intake, including
   numbered-pad nets, values, footprint identities, assembly flags and ERC.

Proof: `build/12vhpwr-placement-20260906/source-provenance.json`, the root and
candidate intake reports beside it, and each final candidate's
`board.source-check.json`. The provenance record hashes the current hierarchy,
rules, policy, BOM inputs, referenced library lands and blueprint templates.

Original SHA-256 values, unchanged after the experiment:

| Artifact | SHA-256 |
| --- | --- |
| 12VHPWR root staging PCB | `0cccc4bd6e4eef88885b5e9a07cf5b00acd3d10abfbbbc718fc8db078d94f309` |
| 12VHPWR older candidate | `cb86cad3d8262ff51a36cfdc37118478e77b8f0492e5fbf5f94797f654e031cd` |
| Hub current candidate | `769f20bed0f0735c7ad86dbc97c315e8333c7318d3e05ff065d84130ba6f67dc` |
| PCIe archived control | `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea` |

The root README now prominently marks its older June design/routing notes as
historical. The board policy opts into the existing schematic-first
working-copy normalization; there is no fallback to an arbitrary older PCB.

## Generic pipeline repairs

### 1. Reliable current-domain proof and causal evidence

The Hub width checker crashed inside its disposable rated-subgraph analysis.
It permanently discarded borrowed KiCad tracks using `Remove()`, reproducing
the native type-registry lifetime defect already found in other cleanup paths.
The current-width checker, current-track pruning and schematic-sync retirement
now use the shared native permanent-discard helper. No extra registry pins,
board-specific selectors or relaxed electrical thresholds were added.

Two synthetic subprocess tests failed before the change with an unbalanced
registry reference and pass afterward. They repeatedly check/prune a renamed
synthetic board, reload it, verify reference balance, and preserve its input
hash. Existing tests retain narrow-leaf acceptance and narrow-trunk rejection.

The checker also reports original connectivity, rated-subgraph connectivity,
and each removed segment's UUID, layer, actual/required width and endpoints.
It distinguishes `undersized_power_path` from
`preexisting_open_with_undersized_copper`; a preexisting open does not become
a misleading width-only repair request. Both classifications remain failures.

On the current Hub, four domains are connected originally but fail the rated
subgraph proof: `+5VSB`, `+5V_SYS`, `LOGIC_REG_IN`, and `KVM_5V_IN` (the reports
retain full hierarchical names). These are real qualification failures, not
checker crashes. **No Hub copper was repaired in this slice:** structural DRC
remains 5 and unconnected remains 13. Pair integrity, coupling, bypass ownership,
one via/pad overlap and route dimensions also remain open.

Evidence: `build/current-native-hub.json`, `current-native-hub-score.json`,
`current-native-hub-constraints.json`, and `current-native-causal-tests.log`.

### 2. Initial-placement checkpoint and physical-first screening

The canonical entry point now supports `--placement-candidates-only` with
explicit `--replace-placement`. It uses the same normalization, source intake,
candidate generation, materialization and exact finalist evaluation as the
production pipeline. It retains the exact evaluated board families and detailed
failed evidence, then stops before craft-repair loops, detailed routing,
signoff or manufacturing export. It does not grant routing admission.

The current checkpoint implementation rechecks source intake before retaining
a candidate. Worker failures or lost source/assembly state fail closed.
Successful execution is labeled `PLACEMENT_CANDIDATES_REVIEW`, never `RELEASED`.
Pose-diversity counts expose strategies that collapse to the same result.
The detailed-route-oracle environment variable cannot override this review-only
boundary.

The experiment exposed wasted ordering: exact route preflight ran for minutes
on four placements already destined to fail the physical gate. Those probes
were stopped after over four minutes. The canonical pipeline now applies the
same actual-pad-bounds and KiCad courtyard gates before route preflight, defers
invalid geometry explicitly, and retains it for placement repair/review.
This does not skip any release check or declare the board size insufficient.

### 3. Dependency freshness and native assembly state

Source/checkpoint signatures now include referenced footprint library files,
library tables and rigid-cell template files. A changed land or cell invalidates
the cached normalized source and placement even when the schematic path and
text are unchanged. Synthetic tests modify only the library/template and prove
that the digest changes; missing referenced files fail closed.

The final source check also caught a materializer defect: copying a string field
named DNP did not set KiCad's native assembly flags. Fresh generation now carries
DNP, BOM exclusion and position-file exclusion from the source hierarchy.
DNP does not remove copper lands and does not automatically exclude a part from
the source BOM. Four flag combinations, idempotence and the materialization
integration are tested. This fixes the mechanism for all boards.

## 12VHPWR source omission repaired

FL1 had a selected MPN and explicit DNP state but no footprint. The existing
enterprise ACT1210 land was not reused blindly: its pad dimensions, courtyard
and pin mapping did not match this schematic contract.

Assigned `cec-Common_Mode_Choke:TDK_ACT1210L_CEC_13_24`, using TDK's recommended
4.1 by 1.6 mm land extent, 2.0 by 0.4 mm inner gaps, and four 1.05 by 0.60 mm
pads. The CEC symbol's winding pairs are logical 1-3 and 2-4; TDK's physical
pairs are 1-4 and 2-3. The footprint explicitly maps logical 1/2/3/4 to physical
1/2/4/3. Geometry and emission tests verify the map and carried pad nets.

Manufacturer source: [TDK ACT1210L-101 datasheet, page 3](https://product.tdk.com/info/en/catalog/datasheets/cmf_automotive_signal_act1210l-101_en.pdf).
The current text drawing dimensions were checked; the local visual source
`lib/datasheets/ACT1210L-101-2P-TL00.pdf` is the manufacturer's 2019-01-25
edition obtained from a distributor mirror because direct TDK downloads were
denied. The current web-indexed edition is dated 2022-10-24 and lists the same
land dimensions. No 3D model or approval of the fitted EMC option was invented.
FL1 stays DNP; R22/R23 stay fitted. The source BOM export needs its new FL1
footprint/datasheet row refreshed before assembly documentation is issued.

## Initial placement results

Run directory: `build/12vhpwr-placement-20260906/current/`.
All final board artifacts are below `02-placement/candidates/`.
There are **four strategy runs but only one unique placement**.

| Strategy, seed 0 | Outline | Source intake | Placement residual | Pads outside outline | Admission |
| --- | --- | --- | ---: | --- | --- |
| Thermal | 58 x 80 mm | PASS | 17 | U1: 73 | Refused |
| Hybrid | 58 x 80 mm | PASS | 17 | U1: 73 | Refused |
| Plain | 58 x 80 mm | PASS | 17 | U1: 73 | Refused |
| Dataflow | 58 x 80 mm | PASS | 17 | U1: 73 | Refused |

All have 102 schematic components plus three fiducials. Existing force-lane
and accepted rigid-cell copper is visible, but they are **not fully routed**.
The materializer reports six force lanes and 370 locked cell segments, with
one refused cell. No thermal solve was run or claimed on these placements.

The current recipe attempts a one-row six-cell walk that needs 60 mm inside
38 mm of available lane space, then degrades to a still-infeasible 9 mm cell
floor. This is a recipe/packing failure, not proof that a larger PCB is needed.
The MCU has no legal seated position. A later bypass move also breaks the sixth
rigid-cell pose (C15); it is correctly refused instead of silently stamping
copper onto moved pads. Decoupler/local-access and stranded-passive findings
are preserved in the candidate JSON, including large 16-32 mm supply distances.

Final canonical timings: normalization 2.873 s, source intake 11.933 s,
placement generation and exact evidence 152.554 s. Four CPU candidate workers
were used with the existing memory-bound pools. The four route probes were
deferred by the physical-first gate. This run provides no new GPU speedup claim.

Model-free PNGs are beside each board as `placement.png`. Their red banner
states initial placement, physical failure and not routed. All four final
source checks pass in `review-verification.json`; do not use the earlier
`full/` experiment, which retained the superseded DNP-state defect.

## Regression and remaining work

`build/hub-12vhpwr-final-verified-tests.log`: **357 passed, 13 skipped, three
subtests passed**, 66.11 s. The skipped tests are optional placer fixtures;
they are not counted as passes. The final source-retention and assembly subset
also passed 14 tests. `git diff --check` passed.

`build/current-native-pcie2-regression.json` replays the archived PCIe control.
It remains at **0 structural DRC / 0 unconnected**, with unchanged 615 tracks,
226 vias and 1242.073 mm route length. Its measured score matches the previous
slice's `probes.before.score`; eight existing release-blocker categories remain.
It is not newly release-qualified. The declared generic core passes; whole-
pipeline generic acceptance still fails inherited selector debt.

Next bounded implementation work:

1. **Hub:** use the rated-subgraph certificates to rebuild/widen the failing
   aggregate power paths under exact clearance/connectivity admission. Then
   handle remaining opens and pair/return failures; do not treat zero opens as
   complete fabrication qualification.
2. **12VHPWR:** make placement ownership survive every subsequent seating pass,
   then negotiate lane-cell rotation and two-dimensional packing from real
   envelopes. Compare genuinely distinct placements at the existing outline
   before considering any size increase. The current recipe's four-way
   collapse should end that search recipe, not launch more identical waves.
3. **Before release:** qualify the J4 pigtail/wire-landing representation,
   dynamic OVP margin, INA240 filter/calibration error and actual-copper thermal
   paths. The source audit currently reports roughly 212.327 mA including
   margin against the TLV755's 500 mA capacity, but that is not PCB thermal,
   startup, capacitor-derating or source-switching qualification.

No board was promoted to a current routed or fabrication-review authority.
