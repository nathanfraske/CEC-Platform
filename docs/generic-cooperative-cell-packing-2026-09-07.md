# Generic cooperative cell packing

2026-09-07. Bounded placement slice completed and tested. The current 12VHPWR
MCU is now inside the unchanged outline. **This is placement review, not a
routed or fabrication candidate.** Detailed craft and critical-route gates
still refuse it. No design source, board policy or immutable control was edited.

## Corrected diagnosis

The preceding ownership report cited a six-column, 9 mm minimum-pitch warning
as evidence about the final row. Inspection showed that warning described an
intermediate shared-bus walk; a later lane re-fan replaced it with a 6.8 mm
pitch. The final row was not the geometry described by that warning.

Measured courtyards, pad extents and authored copper need approximately 6.8 mm
pitch with a 0.3 mm envelope margin for this template. Horizontal squeezing
therefore offers little. The original MCU search also restricted itself to a
right-hand column. A full-outline ablation with the original row still found
no legal seat: removing that restriction alone was insufficient.

The new search moved the **complete row**, preserving its six-channel pitch,
rotation, polarity, member geometry and fixed connector positions. It found a
whole nine-part MCU/support macro reservation after 26 trials: a (0, -13) mm
translation, moving the sensing-cell anchor row from y=40 to y=27 mm. These
coordinates are measured results, not values encoded in the solver.

## Reusable implementation and boundaries

- `scripts/cec_cell_packing.py` is a parameterized, product/refdes/net-free
  translation solver. It receives physical envelopes, outline, clearance,
  search step/budget, fixed obstacles and a future-macro reservation callback.
  Every tested site consumes budget, including sites rejected before the
  callback. Search order is deterministic and capped at 65 trials per mode.
- Envelopes include pad-aware courtyards, actual-width authored tracks and
  via copper. Rounded copper is conservatively buffered. Copper is projected
  across layers for floorplanning, not granted speculative layer-crossing
  exemptions. Native downstream checks remain authoritative.
- The placement adapter runs before blueprint ownership locks. For a collinear
  row and a single unseated RF-module owner, it first tries the complete macro,
  then an owner-only fallback: at most 130 sites total. Explicit pins, existing
  locks, frozen pour references and absolute cell anchors prevent row motion.
  Explicit macro placement partitions/pins keep their upstream authority.
- The accepted owner is reserved against later re-seating. Support parts remain
  eligible for existing pin-local constructors; no authored copper is falsely
  treated as following independently moved parts. Actual blueprint members
  remain rigidly owned. Refreshed stamps use the translated live anchors.
- Fixed connector and fanout regions remain obstacles. Movable fiducials do
  not block this critical reservation; pinned mechanical parts still do.
- A separate existing bug was fixed: late lane re-fanning could overwrite
  upstream pinned cells. It now refuses that rewrite. Provisional walk warnings
  are explicitly marked superseded when a later re-fan actually replaced them.
- Packing decisions, trials, rejection counts, member list and reservation
  poses survive into canonical placement-review/replacement reports.

This slice does not solve arbitrary 2-D cell packing, change row pitch, merge
cells, rotate individual blueprint parts, or optimize every IC family. The
primitive is generic; the current adapter is deliberately narrower. Existing
legacy force-corridor selectors remain technical debt, not newly claimed
generic behavior. Generic-core audit passes; whole-runtime genericity is still
false. No board/refdes/coordinate repair was added for this experiment.

## Verified comparison

Both source intake and the complete source-file signature match the prior
verified current-hierarchy replay. This remains the U16/LDO 12VHPWR source,
not the stale U3/buck saved candidate.

| Measurement | Ownership baseline | Cooperative packing |
| --- | ---: | ---: |
| Placement residuals, not DRC count | 12 | 5 |
| MCU pads outside outline | 73 | 0 |
| Exact courtyard violations | 0 | 0 |
| Complete blueprint cells / locked segments | 6 / 444 | 6 / 444 |
| Decoupler craft findings | 12 | 12 |
| Stranded-part findings | 3 | 1 |
| Outline | 58 x 80 mm | 58 x 80 mm |

Residuals fell by seven (58%), but this is **not monotonic electrical closure**:

- C3-to-MCU decoupling distance improved from 28.48 to 13.26 mm, still failed.
  C7's former 31.81 mm owner-distance failure became a much smaller local-loop
  proximity failure, 0.27 mm against the unchanged 0.25 mm excess limit.
- C4-to-U5 distance worsened from 16.01 to 24.72 mm. The constructor reports no
  distinct compatible capacitor for U5.1/U5.7 and U2.5. This needs assignment
  and source-role investigation, not a hardcoded move of C4.
- All six sensing bypasses now report the existing 2.00 mm local-cell-access
  failure. Locking the template makes its deficiencies reproducible; it does
  not qualify its bypass geometry.
- The prior R13/R7/D1 stranded findings disappeared, but C22 is now stranded
  28.829 mm from U4 on /VREF. This is a newly visible follower-placement defect.
- The same /FAN_12V exact-pour failure remains: attachment groups occupy two
  disconnected components. No permissive fallback was accepted.

Physical admission now reaches precise route preflight. Three critical pairs
are refused: USB flow-through and CAN_INT exhaust their existing bounded search
budgets; CAN reports incomplete physical-pad ownership/duplicate-pad closure.
The raster's zero unroutable count is not substituted for these failed exact
proofs. Pair-launch craft passing also does not override the detailed failures.
No residual routing or thermal solve was run.

Plain and thermal seed 0 still collapse to **one unique pose**. The placement
stage took 704.181 s for two candidates. Exact preflight took 547.86 and
571.52 s respectively, running concurrently; these times are not additive.
A read-only stack sample located substantial work in pair transition-return
via checks and via-pad exclusion. Earlier physically rejected placements had
skipped this work, so comparing total runtimes would not measure solver speed.
Existing effort limits were not reduced to obtain a quicker comparison.

The candidate run preceded only the final pinned-refan/warning fix. A replay
through the critical-seat stage with that final fix again produced the same
26-trial, (0, -13) whole-macro result. The new pinned-case synthetic regression
and final broad suite cover the final code; a second full 12-minute preflight
was not repeated for an unchanged unpinned geometry.

## Tests, regression and artifacts

- Final broad suite: **467 passed, 13 skipped**, 82.94 s. Includes 13 new
  primitive/adapter tests: both translation axes, bounded failure, copper/via
  extents, invalid input, renamed synthetic members, actual pre-lock adapter,
  refreshed stamps, fixed obstacles and upstream pin preservation.
- `git diff --check` and Python compilation pass.
- Archived PCIe 2-port live score and complete blocker list are unchanged:
  **0 structural DRC / 0 opens**, 615 tracks, 226 vias, 1242.073 mm. Its eight
  pre-existing release-blocker categories remain. This is an unchanged-board
  regression replay, not a fresh PCIe placement demonstration.
- Source staging board, old 12VHPWR candidate, Hub candidate and archived PCIe
  SHA-256 hashes all match the prior provenance record. No Hub copper changed.
- Full evidence and exact retained boards:
  `build/12vhpwr-cell-packing-20260907/02-placement/placement-candidates.json`
- Compact before/after, source hashes and control comparison:
  `build/12vhpwr-cell-packing-20260907/comparison.json`
- PCIe evidence: `build/cell-packing-pcie-regression-20260907.json`
- Test log: `build/cell-packing-final-tests-20260907.log`
- Model-free native preview: retained candidate `000/placement.png`, visibly
  marked placement review / not routed. Its PCB hash was checked after render.

The experiment directory uses approximately 6 MB. No dashboard/fab promotion
was made and no unattended waves remain running from this experiment.

## Next bounded work

1. Make supply-cap assignment and pin-local access part of macro reservation,
   with explicit failures for missing compatible components. Repair authored
   bypass-cell geometry upstream; never detach members after copper ownership.
2. Carry complete shared-net follower groups through the same reservation and
   admission process, using the new stranded /VREF case as a renamed regression.
3. Address exact power attachment and physical-pad-complete pair escape from
   their existing failure witnesses. Profile/reuse invariant via-exclusion
   geometry before increasing pair-search effort or spawning duplicate waves.

Keep this measured placement improvement as a diagnostic baseline, not a new
manufacturing authority. Each next slice must compare individual craft terms,
the preserved PCIe control and fresh placement behavior, not only residuals.
