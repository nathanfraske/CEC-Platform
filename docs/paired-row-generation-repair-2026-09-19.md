# Paired mating-row generation repair — 2026-09-19

## Scope and result

The bad-pitch producer is corrected; **the existing EPS and ATX PCB geometry
is not repaired or newly admitted**. No board, schematic, footprint land,
outline, power budget, or mating-span limit was changed. Their stored shorted
rows remain blocked, not counted as progress. An explicit choice between
relaxing the mating span and evaluating different arrangements/parts has been
requested. Do not repeat unchanged waves on these rows.

Previously `_compile_daughter_body_clearance` selected daughterboard pitches
using body width/tolerance only. `mating_row_targets` then compressed the main
row to match. The later native geometry gate detected the shorts, but nothing
corrected their producer. Existing integration tests even expected these
interfaces to report `already-integrated`; that was not clearance admission.

## Shared implementation

`cec_mating_rows.compile_paired_row` accepts installed envelope sets from both
halves and a hard last-datum limit. It checks every ordered pair, keeps the
first datum fixed, and redistributes available slack when necessary. A feasible
unchanged row remains unchanged. A refused row returns structured conflicting
constraints, minimum span, available span and excess, with **no proposed map**.
No board name, reference or coordinate selector is present in this solver.

The XFCN contract adapter now supplies real installed library copper on both
halves, preserving every repeated terminal land and accounting for pad and
footprint rotation. Body size/tolerance/position budgets also remain active.
All parents sharing a daughterboard participate. The existing explicit
0.20-mm screening gap is used for copper separation proposals; this does not
replace either board's native rules, full assembly/fastener checks, measured
contact depth, keying or incoming-sample qualification. The projection is
conservative, not proof that no staggered or differently oriented arrangement
could fit. Unsupported or missing footprint geometry refuses compilation.

The daughter map, parent-span fit and companion envelope are evaluated before
committing a compiled daughter map. On refusal both authored maps remain
untouched. Main/daughter target generation and interface-anchor binding now
refuse the failed compilation. The direct placement writer refuses before
directory creation, sidecar copying or native board loading. Its multi-project
CLI preflights every member before dispatching any writing worker and emits
structured `mating_geometry_conflict` evidence.

Current conservative straight-row screen:

| Interface | Available datum span | Required span | Excess |
|---|---:|---:|---:|
| EPS | 21.0 mm | 23.1 mm | 2.1 mm |
| ATX | 38.9 mm | 42.3 mm | 3.4 mm |
| PCIe shared daughter interface | 14.0 mm | 11.5 mm | 0 mm |

These are **row-span screening values, not proposed PCB dimension increases**.
ATX's signal companion and both boards' edge, hardware and assembly margins
must also be checked if a changed span is authorized. PCIe preserves its
existing 14.0-mm pitch; no gratuitous compaction was applied.

## Validation

- **138 tests and 41 subtests pass**:
  `build/paired-row-compiler-tests-20260919.xml`.
- New tests cover two-sided limiting geometry, slack redistribution without
  growth, unchanged/idempotent rows, translated frames, asymmetric/nonadjacent
  envelopes, incomplete evidence, immutable refusing inputs, and writer refusal
  before any output directory is created.
- Native saved-board examples at 0 and 90 degrees reproduce a pad conflict,
  apply the shared solved datums to both halves, and pass native pad DRC with
  an explicit 0.5-mm custom clearance. Native tests also compare installed
  projections against the four actual terminal/contact footprints.
- Old tests that blessed the unqualified ATX/EPS maps now assert refusal;
  feasible-macro translation and stale-part metadata repair remain exercised
  using the valid PCIe interface, rather than disabling their coverage.
- `build/paired-row-compiler-suite-20260919/report.json`: four other current
  main-board physical/craft results are identical to the prior replay; EPS/ATX
  retain their source-ECO holds. All six PCB/hierarchy signatures are unchanged.
- Historical PCIe2 fab-review control board hash, board regression and all
  probes match exactly. Its pre-existing wider release failures remain.
- Generic-core audit passes. `release_ok=false` remains for wider legacy debt.
  No full-board routing, physical interface repair or fabrication promotion is
  claimed by this slice.

The board suite was replayed only to check regression, not to spend routing
effort on the known terminal conflicts. All workers completed.
