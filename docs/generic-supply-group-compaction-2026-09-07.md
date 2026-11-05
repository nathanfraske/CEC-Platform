# Supply ownership and layer-aware compaction — 2026-09-07

## Scope and authority

Further compact the current hierarchical 12VHPWR Standard design while keeping
the fitted fan header, four M2 holes, and right-facing lower RJ-45/USB-C bank.
The live manifest-selected hierarchy is the source; neither historical root
PCB nor the old candidate PCB is an input authority. This slice changes no
schematic values, BOM selections, fan specification or fabrication process.

The source-first working copy has 16 recognized supply-capacitor contracts
after this repair, versus 15 before. This is added **coverage**, not a newly
added physical capacitor. C7 was already a fitted 10 uF capacitor explicitly
owned by U1.3, but previously escaped the selected-device physical check.

## Reusable repairs

1. **Declared supply contracts are complete.** The source and native board
   checker share `bind_declared_requirements`. Explicitly owned local bulk
   receives its own contract when not consumed by an existing device minimum.
   HF and bulk are distinct requirements; a large capacitor cannot silently
   substitute for a required 100 nF bypass. Invalid or ambiguous parsed local
   declarations fail closed. This operates on the existing supported local
   capacitor inventory, not arbitrary electrolytic/reservoir parts. No
   universal bulk value is invented for unrelated boards.
2. **Essential groups survive decomposition and handoff.** A failed large
   macro may shed optional followers, but not its required supply capacitors.
   The replacement subgroup is re-seated against actual supply pads before
   its envelope is reserved. Tight-limit/HF capacitors get priority. The
   pre-lock reservation exports and locks the complete group, rather than
   just the MCU; a synthetic integration test caught that second handoff bug.
3. **Copper obstacles carry layer meaning.** Explicitly tagged opposite-face
   copper is not an all-layer component-body keepout. Known SMD footprints
   project onto their mounted face; THT, unknown geometry and untagged
   mechanical/cell obstacles remain conservative. This allows front-side
   components above rear-layer bus fanout. It grants no via/track crossing,
   thermal qualification or reference-plane continuity.
4. **Local seats preserve existing cell copper.** Every proposal through the
   local seat-clearance helper now supplies its actual component poses and
   passes the reserved-copper pad check. This includes signal followers and
   switch networks, not just capacitors. Ratifying a capacitor also checks
   its owner IC. Previously body-legal placement could obstruct authored
   sensing tracks and cause an entire cell to be refused at materialization.
   Same-net contact remains allowed; a component courtyard over an insulated
   trace is not itself treated as a pad short.
5. **A rejected outline is not a batch crash.** Geometrically infeasible
   connector banks raise a typed refusal. The coordinator records the
   outline and reason, then continues the bounded sweep. Invalid policy,
   missing inputs and programming errors still propagate. This is not a
   catch-all exception suppression mechanism.

Geometry primitives contain no product/refdes/coordinate exception. The
legacy integration adapters still contain existing product-family logic;
this slice does **not** certify the whole repository as universally generic.

## Bounds and electrical limits

- Fresh, deterministic seed 0; heights 80, 76, 72, 68 and 64 mm at 58 mm width.
- Maximum four height reductions. No automatic board growth or unbounded retry.
- Row negotiation retains pitch and rotation, at most 65 translations per
  macro variant (whole/essential, at most 130 total).
- Four mounts retain 2.2 mm NPTH and the 6 mm hardware allowance plus 0.25 mm
  clearance. The end-aligned I/O bank retains its 2 mm courtyard gap.
- The 3.5 mm generic supply ceiling is a project placement contract, not a
  manufacturer distance recommendation. More restrictive device rules remain.
- Pin proximity, local supply access, ground return, coupled routing,
  complete cell/power copper and thermal qualification are separate checks.
  Passing one must not erase another failure.

Short supply paths and nearby ground vias follow the general placement intent
in [Espressif's PCB layout guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html).
Bare-chip pin-specific capacitor rules are not applied indiscriminately to
the MINI module. The fan remains unqualified: no cooling credit is assumed.

## Validation and retained evidence

The final focused suite passed **573 tests**, with **14 skipped**:
`build/supply-copper-guard-final-tests-20260907.log`.
The skips are one absent dual-sided probe artifact and thirteen unavailable
historical Hub-fixture tests; they are not counted as passing tests.
Tests cover renamed synthetic ownership, multiple bulk values, physical
source/native matching, essential-group lock handoff, surface/THT/unknown
layer projection, all local-seat copper guards, typed outline rejection,
mount/edge packing, and placement/craft/generalization regressions.

The immutable PCIe review control replay is
`build/supply-copper-guard-final-pcie-regression-20260907.json`.
Its score and eight constraint blockers are unchanged: 0 DRC, 0 unconnected,
615 tracks, 226 vias, 1242.073 mm. Its broader current release acceptance is
still false, as before; this is a no-regression result, not retroactive
fabrication approval.

The intermediate layer-aware candidates in
`build/12vhpwr-layer-aware-supply-compact-20260907` are **not final**.
Their smaller bodies fit, but the 72 mm candidate lost two authored sensing
cells and the 76 mm candidate lost one. Those failures motivated repair 4;
they must not be promoted as complete power/routing candidates.

The final independent native measurement and comparison are retained under
`build/12vhpwr-supply-copper-guard-compact-20260907`.
See `02-placement/placement-candidates.json` for every evaluated board and
`02-placement/placement-search-rejections.json` for infeasible outlines.
No candidate from this initial placement sweep is routing-admitted or
fabrication-approved.

## Final measured results

All retained candidates pass native pad containment, courtyard and four-mount
checks, source intake and the 16-of-16 supply inventory. All retain the
right-facing lower I/O bank and fitted fan header. They are **not** full-route
or thermal results.

| Outline | Area change vs 58 x 80 | Sensing cells / locked segments | Wide power inventory preserved | Placement residual | Decoupling findings |
|---|---:|---:|---|---:|---:|
| 58 x 68 mm | -15% | 6 / 444 | Yes | 3 | 12 |
| 58 x 72 mm | -10% | 6 / 444 | Yes | 1 | 12 |
| 58 x 76 mm | -5% | 6 / 444 | Yes | 2 | 12 |
| 58 x 80 mm | 0% | 6 / 444 | **No — incomplete sixth power path** | 1 | 12 |
| 58 x 64 mm | Not admitted | No board generated | Not evaluated | Connector-bank refusal | Not evaluated |

The 68 mm candidate is the smallest mechanically and authored-copper
preserving result of this bounded sweep, **not a proven minimum size**. The
pipeline's first-ranked continuation is the 72 mm candidate. The 80 mm
fallback is not acceptable just because its sensing-cell count is complete:
the independent net/layer/width inventory caught the incomplete power path.

- Aggressive review: `02-placement/candidates/000/board.kicad_pcb`, SHA-256
  `d37f790988bd68f889f62bcf432fc1631a22a62bf3e0f843d18498b80237a6e0`.
- First-ranked continuation: `02-placement/candidates/001/board.kicad_pcb`,
  SHA-256 `0ebdc6bcbaf6b09378ebf5296cda403b637ebc84bf9564e582b5d00b9dcd2801`.
- MCU C3 supply distance remains 1.56 mm. C7 improves from 21.989 mm in the
  retained 80 mm baseline to 3.064 mm in all four new candidates. Its ground
  distance/local-access checks still fail; proximity is not complete decoupling.
- At 68 mm, total 2.5 mm main-bar length is 72 mm shorter, with the wide
  per-net/layer width inventory unchanged. Fan cooling and copper-temperature
  qualification have not been rerun and cannot be inferred from shorter bars.
- The largest 68 mm decoupling failures are the regulator input/output caps:
  C1 is 9.29 mm from U16.6 and C2 is 23.08 mm from U16.1. The 72 mm continuation
  avoids those two separations but still strands mux input C6 at 12.52 mm.
- The final placement stage took 681.725 s. Synthesis of outline variants is
  still serial; native evaluation then used four independent workers. This
  remains an identifiable performance opportunity, not evidence of a minimum
  outline or a stalled run.

The compact comparison is `supply-compaction-closeout.json`. Actual no-body
top/bottom renders are beside candidate 000; identical display copies are in
the Windows workspace's `artifacts/12vhpwr-20260907-supply-compact-*.png`.
They visibly say **placement only — 12 decoupling findings**. No historical
PCB or PCIe control was modified, and no dashboard fabrication authority was
replaced by this study.

### Remaining generic work

The late constructor can jointly relocate a single-supply owner and its cap,
but deliberately refuses to move a multi-supply owner after partially placing
its siblings. Extend that to a bounded, jointly evaluated owner-plus-all-supply
group, with actual supply escape and short ground-return/via admission. Apply
it to muxes, regulators and other ICs rather than naming C1/C2/C6 in a repair.
The current source matcher, reservation contract and evidence already expose
these failures; the twelve findings must stay blocking until physically closed.
