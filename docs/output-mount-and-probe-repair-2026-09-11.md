# Output mount safety and funded route probes — 2026-09-11

## Scope and state

The user's requirement is physical daughterboard-to-bolt-header keying: an
incompatible daughterboard must not attach to the wrong output bank. Silkscreen,
connector count, net names, and key IDs do not meet that requirement. Existing
board outlines and maximum interface edge spans are unchanged in this slice.
No terminal, protected power bus, or archived fab-review PCB has been moved.

**Physical key implementation remains OPEN.** This slice closes the obsolete
checker and missing qualification-gate defects; it does not claim a manufactured
anti-mismatch feature has been added. Do not release these interfaces on the
basis of the routing campaign or the old blade checker.

## Current-native interface audit

`scripts/check_output_daughterboards.py` now invokes the XFCN audit by default.
The old TE blade-grid check requires `--legacy-blades` and explicitly says it
does not qualify current BETA. Evidence includes every input PCB's full path and
SHA-256, actual native hole positions, measured main footprint positions, and
electrical nets. Candidate inputs can be selected explicitly with `--input`.

The initial canonical-board screen is in `build/output-mount-audit-20260911.json`.
The completed-pass candidates were checked explicitly in
`build/output-mount-audit-pass-d-20260911.json`; no filename recency search was
used to select them.

| Finding | Evidence and limit |
| --- | --- |
| ATX mating pitch mismatch | On the actual pass-D candidate, the two identical TTR terminals span 44.50 mm versus 37.25 mm on the daughterboard (7.25 mm discrepancy). The four identical T340 contacts use 8.00 mm versus 6.85 mm intervals (1.15 mm discrepancy). The checker compares same-part/same-rotation subgroups even inside a mixed-part port. Their common axis offsets cancel; mixed-part cross-group datums remain unknown. |
| EPS mating pitch mismatch | Both main ports use 7.75 mm intervals; the EPS daughterboard uses 7.00 mm. Common-part, common-rotation screw-axis offsets cancel, so the 0.75 mm nominal pitch discrepancy is real even though absolute screw height is unqualified. |
| PCIe port orientation inconsistency | PCIe 2-port's first pair is GND then post-shunt +12 V in increasing authored X; the other PCIe ports use the opposite order. A final assembly drawing still needs its viewing-side/mated transform. |
| Wrong-family fits not excluded | The daughterboard hole-pattern screen finds possible EPS-on-ATX, PCIe-on-ATX, and PCIe-on-EPS assignments. These are conservative warnings, not claims of fully assembled collision-free fits. |
| Missing physical qualification | Main terminal screw-axis height, contact-face registration, tolerance stack and a positive anti-mismatch key are not qualified. |

### Common electrical mapping (logical port positions)

| Daughterboard family | Required order | Matching main-net roles |
| --- | --- | --- |
| ATX | GND, +3V3, +5V, +12V, +5VSB, GND | GND, SENSE3V3_LO, +5V_MAIN, SENSE12V_LO, SENSE5VSB_LO, GND |
| EPS | GND, +12V, +12V, GND | GND, cable-local SENSE_LO, cable-local SENSE_LO, GND |
| PCIe | +12V, GND | cable-local SENSE_LO, GND |

The audit emits the full refdes-to-refdes pin mapping per port. This table is
logical intent, **not** a release drawing or permission to silently relabel
existing copper. Same-family cable ports should share one mating contract;
different cable families must not physically interchange.

### Generic geometric test

`cec_mount_patterns.possible_fit` has no board names, nets, part IDs, refdes, or
coordinate special cases. It searches injective assignments of all insert holes
to receiver holes, including nonadjacent subsets. Pair-distance intervals are
invariant under arbitrary rotation, translation and reflection. If no assignment
survives exhaustive search, that abstract pattern is excluded. A surviving
assignment is only a possible fit. A search-budget limit is UNKNOWN.

The screen currently uses an explicitly **unqualified** 0.6 mm combined radial
allowance per joint. Two joints can share their alignment error: the pair-distance
allowance is twice that value. The old exact-anchor method could falsely exclude
a fit that succeeds by distributing the error between its ends. No screening
tolerance here is asserted to be a manufacturer-approved tolerance stack.

Actual ATX main-side mixed-terminal geometry is not replaced with footprint
origins pretending to be measured screw axes. Nor are actual main-bank 3D
cross-fits certified by comparing daughterboard hole patterns. Those remain
explicit release blockers. All M3 joints remain electrically monolithic.

### Next physical work, in order

1. Freeze a measured mating frame for each terminal: face plane, screw axis,
   PCB-to-face offset, fastener/washer envelope and tolerance bounds.
2. Derive every main port and its daughterboard from one shared pattern and
   logical pin map. Correct the ATX/EPS pitches and PCIe first-port order in a new
   interface revision, with corresponding copper regeneration, not by moving
   protected terminals in an accepted routed artifact.
3. Implement a positive key within the existing envelope and test the full
   assembly. Merely changing a two-hole pitch cannot prevent reversed same-pair
   attachment; identical M3 fasteners also permit wrong-family single-bolt
   attachment. A keyed insulating guide/interlock must be mechanically retained
   and prevent contact/fastener engagement in prohibited orientations.
4. Exhaustively check wrong families, wrong port offsets, flips and partial
   engagement under the worst tolerance stack. Re-run clearances, contact/thermal
   analysis and incoming-sample fit checks before qualification.

`output_mount_interoperability` is now a mandatory open qualification gate.
Changing its boolean to passed cannot waive the current native audit.

## Generic routing fixes

### Admission API regression

The current working tree had replaced the existing `cec_stage_admission`
snapshot/evaluate/accepts API with new reporting-only helpers. Certificate
repair callers therefore raised `AttributeError` at candidate admission.
Restored the existing identity-aware monotonic mutation checks and retained
`admission_ok`/`label`. Tests now exercise both APIs together. No debt-swap gate
was weakened to make a test pass.

### Fund complete probes instead of starving all candidates

The preceding Hub attempt split a bounded allocation across 12 probes on two
workers, reducing a requested 120-second pair solve to about 29 seconds. All
12 timed out. The allocator now admits only complete affordable batches,
including explicit overhead and a finalist reserve; remaining candidates are
deferred. The reproduced budget admits two 120-second probes, not twelve
29-second probes. Final routing effort is unchanged.

Timeouts and worker failures are explicitly inconclusive and cannot enter the
ranked finalist set as measured improvement or geometric rejection. Parallel
probe failure no longer replays the whole batch serially against the same
already-spent budget. Reporting distinguishes deferred, inconclusive, measured
and fully evaluated candidates.

**Remaining scheduling work:** a persistent, input-bound candidate frontier
across independent attempts is not implemented in this slice. Running the same
unchanged attempt repeatedly could still select the same first funded moves.
Do not launch endless repeat campaigns as a substitute for that work.

### Preserve failure traces at the correct boundary

The pass-D Hub trials still had empty `search_trace` arrays. Investigation
found that preflight discarded `local_search` before the placer tried to extract
phase diagnostics. The shared `cec_probe_evidence` helper now extracts a bounded
trace from the raw router result, before that projection, and preserves it
through subsequent summaries. It also records pair-level timeout evidence.
Worker-internal checker errors are explicitly inconclusive, including errors
returned as report dictionaries rather than raised exceptions.

This diagnostic fix was made **after** the frozen six-board pass. A fresh native
Hub diagnostic probe retained 32 bounded trace rows in about 10.14 seconds
(deliberately using a five-second per-pair diagnostic budget); no geometry was
saved or promoted. The bounded trace is not a claim to preserve the entire
unbounded search tree or prove global unroutability.

## Validation

- Final combined admission, budgeting, certificate-repair, generic mount
  geometry, current native XFCN, trace preservation, preflight and status
  projection tests: **291 passed, 41 subtests**.
- Native XFCN screen reads all seven declared boards and emits eight port
  mappings plus six directed cross-family screens; it deliberately blocks.
- Protected routed PCIe replay and six-board continuation results are recorded
  in `build/current-suite-20260911-d/compact-evidence.json` after the pass.
- The bounded pass uses six concurrent board jobs, two-worker local limits,
  720 seconds per job and an 8 GiB free-space floor. No output is auto-promoted.

### Completed six-board pass D

| Board | Result relative to pass C | Elapsed |
| --- | --- | --- |
| ATX | Final reported decoupler violations 9 -> 8; still placement-blocked | 229.2 s |
| EPS | Final reported decoupler violations 1 -> 0; power-corridor blockers remain | 98.3 s |
| Hub | Byte-identical. Two 120-second probes both inconclusive, ten deferred; no fully evaluated finalist | 367.6 s |
| 12VHPWR | Byte-identical, including protected power copper. Thirteen three-pair probes deferred when too little budget remained; final decoupler count stays 1 | 635.3 s |
| PCIe 2-port working placement | Byte-identical, decoupler count stays 0; power-corridor blocker remains | 112.4 s |
| PCIe 3-port | 720-second cap; verified seed checkpoint retained byte-identically, no new accepted placement | 720.0 s |

All six jobs retained source and engine identity during execution. No new
residual-routing admission or fabrication candidate resulted. Hub's pass took
about 98.6 seconds less than C (466.2 -> 367.6 seconds), but that is a scheduling
result, not a route-quality improvement. Do not compare selection-stage bypass
counts to final-stage counts as though they used identical criteria: the
12VHPWR input and output are identical, with one final-stage finding in both C/D.

The immutable gallery is
`review-output/current-suite-20260911-d/all-boards-268bedda9d6a8121.png` on Windows;
all six archives have top/bottom previews. Campaign directory storage is 38 MiB.

The final post-trace-fix replay is
`build/funded-probes-pcie-control-final-20260911.json`. The protected routed
PCIe control remains SHA-256
`d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`,
0 DRC, 0 opens, 615 tracks, 226 vias and 1242.073 mm route length. Score,
constraints, route-quality and fab probe payloads all match the previous replay.
Its existing broader release/differential-pair blockers are not waived.

The final static generalization audit reports a clean declared generic core,
with the pre-existing **23 physical / 380 runtime findings** still present.
Port mappings live in the declarative XFCN contract, not the checker algorithm.
The new geometry and diagnostic primitives are explicitly included in the
generic-core audit. This does not mean the entire legacy runtime is generic.

The PDF skill was used to visually verify the local T34069 and TTR source
drawings. It kept the distinction between dimensioned features and unverified
main-side screw-axis datums explicit; it did not justify inventing a fit datum.
