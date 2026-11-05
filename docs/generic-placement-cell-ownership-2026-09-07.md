# Generic placement cell ownership repair

2026-09-07. Completed bounded ownership and forensic-evidence slice. **No board
was promoted to routed or fabrication-review authority.** The 12VHPWR placement
result is mixed, not a net claim of board closure.

## Root cause and implementation

The blueprint stage explicitly subtracted device-bypass capacitors from its
progressive locks, although the same blueprint's copper depended on those
capacitors' exact poses. A later pad-local bypass constructor could therefore
move a member independently. The materializer correctly refused the broken
cell, but the ownership conflict should not have reached that boundary.

The real stage declaration is now covered by a renamed synthetic regression:
before the fix it locked only `AMP_Q`, omitting `CAP_Q`; afterward it locks both.
There is no product, reference-designator or coordinate repair in the engine.

Changes:

1. Blueprint stamping locks **every** actual cell member, including assigned
   bypass capacitors. Local constructors can evaluate their fixed positions but
   cannot detach them from their cell to improve another objective.
2. `cec_passes.Pass` accepts declarative `owned_cells_out` membership. The ladder
   snapshots each cell's member poses independently of its mutable progressive
   lock map. Under production lock enforcement, subsequent translation,
   rotation, deletion or rewriting of a lock fails at the first offending pass.
   Ordinary locks now also detect deletion instead of ignoring missing members.
3. The failure identifies the owning pass, offending pass, complete membership,
   old/current pose and upstream repair stage. Its structured certificate and
   pass journal survive worker exception serialization and are persisted in the
   canonical `pipeline-state.json`, alongside the existing traceback. Successful
   placement-review and replacement reports also retain the placement journal.
4. The pass-runner module joins the static generic-core audit. Existing
   whole-pipeline selector debt remains a failure; this slice does not relabel
   the entire runtime as fully generic.

The contract protects the XY/rotation poses consumed by a stamped cell. It is
not a new electrical qualification, geometry solver or face-change approval.
Existing source, physical, copper and release checks remain required. Whole-cell
movement after stamping is also refused: that belongs upstream, followed by
regenerating its copper. Explicit unenforced ablations retain their old behavior;
normal synthesis has lock enforcement enabled.

## Real 12VHPWR replay

The current hierarchy, referenced footprint libraries, blueprint templates and
board policy have the same source signature as the September 6 provenance
record. No source board or schematic was changed in this slice. The verified
candidate passes current schematic/native assembly-state intake. This is the
same current U16/LDO source, not the obsolete saved U3/buck candidate.

| Measurement | September 6 | Ownership repair |
| --- | ---: | ---: |
| Placement residuals (not DRC count) | 17 | 12 |
| Rigid sensing cells laid | 5/6 | 6/6 |
| Refused rigid cells | 1 | 0 |
| Locked blueprint segments | 370 | 444 |
| Decoupler craft violations | 12 | 12 |
| Stranded-part violations | 2 | 3 |
| MCU pads outside outline | 73 | 73 |
| Exact courtyard violations | 0 | 0 |
| Outline | 58 x 80 mm | 58 x 80 mm |

Residuals improved by five, but the detailed craft result is **not monotonic**.
The sixth bypass's ground-distance error is gone and its local-access distance
improved from 3.02 to 2.00 mm, yet the 2.00 mm local-access checks still fail and
additional sensing-cell members appear in that category. D1 is now reported
stranded at 22.7 mm, alongside the existing R13/R7 findings. No exception was
added to hide these failures. The unresolved MCU bounds failure independently
prevents routing admission.

Plain and thermal, seed 0, still collapse to one pose signature. A separate
single-worker plain repeat produced the same signature, source-intake PASS and
six complete cell ownership records covering 36 members. It did not discover
another placement. The two-strategy placement stage took 134.145 s; the final
one-strategy repeat took 125.792 s. These are different job counts, not evidence
of a like-for-like speedup. Detailed route probes were deferred by the existing
physical-first gate. No thermal solve or residual routing was run.

Evidence:

- `build/12vhpwr-cell-ownership-20260907/02-placement/placement-candidates.json`
- `build/12vhpwr-cell-ownership-verified-20260907/02-placement/placement-candidates.json`
- `build/12vhpwr-cell-ownership-verified-20260907/comparison.json`
- The verified board and model-free, visibly failed/not-routed preview are in
  the latter run's `02-placement/candidates/000/` directory.

These are diagnostic artifacts only. They were not published as dashboard
fabrication candidates. The original staging PCB, old saved candidate, Hub PCB
and archived PCIe control all retain their recorded SHA-256 hashes. The two
experiment directories together use about 5.6 MB.

## Cross-board checks and regression coverage

The archived PCIe 2-port control was rechecked with the current score,
constraints, route-quality and fabrication probes. Its live score and complete
constraint-blocker list exactly match the September 6 replay: **0 structural
DRC / 0 opens**, 615 tracks, 226 vias, 1242.073 mm. The same eight release-blocker
categories remain. Its historical archived green flags are not treated as live
qualification. This is an unchanged-board regression replay, not a claim that
fresh PCIe placement was exercised.

The current Hub score remains **5 structural DRC / 13 opens**, 901 tracks and
146 vias. No Hub copper was changed. Its rated-current-path repairs remain the
next Hub-specific workload for a generic actuator, not work completed here.

Tests:

- `build/cell-ownership-before-integration-20260907.log`: real blueprint-stage
  declaration reproduces the missing capacitor lock before repair.
- `build/cell-ownership-regression-tests-20260907.log`: **453 passed, 13 skipped**
  across ownership, ladder, blueprint, passive/bypass, physical placement,
  canonical pipeline and genericity tests.
- `build/cell-ownership-final-verified-tests-20260907.log`: **120 passed** after
  the final journal/worker-certificate changes. This overlaps the broad suite;
  the counts are not additive.
- Ten ownership tests cover renamed members, translations, rotations, removal,
  lock rewriting, equivalent rotations, unrelated movable parts, missing
  members, unenforced ablation, the actual blueprint stage and durable failure
  evidence. `git diff --check` passes.

## Next bounded slice

**Subsequent correction, same day:** inspection in
`generic-cooperative-cell-packing-2026-09-07.md` established that the warning
below described an intermediate walk, superseded by the final 6.8 mm lane
re-fan. It was not evidence that the final row used a 9 mm floor. The historical
measurements above are unchanged; the follow-up records the actual geometry
and the implemented whole-row/macro negotiation.

Fix upstream cell packing before running more identical waves. The current
straight-through recipe still tries six columns in a 38 mm usable span with a
hard-coded 9 mm floor; its own diagnostic says that row is infeasible. This is
not proof the 58 x 80 mm board must grow.

Replace those recipe assumptions with measured courtyard/copper envelopes and
bounded whole-cell alternatives, reserving a legal MCU/support-cell region and
maintaining source/sink polarity and power-corridor clearance. Compare detailed
craft terms as well as residuals, so reducing a coarse score cannot hide newly
stranded parts. The ownership boundary implemented here ensures later local
passes cannot undo an admitted cell configuration.
