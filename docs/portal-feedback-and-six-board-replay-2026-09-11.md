# Early portal feedback and six-board replay — 2026-09-11

## Implemented slice

The existing portal refill mechanism waited for a complete escape beam to
return. A locally trapped start could therefore spend the remaining deadline
on other destination combinations before its feedback was consumed. The
refill also changed the whole-screen cache key and repeated failed local
queries from the previous beam.

Two product-neutral changes address this:

1. A completed, still-local exhausted grid frontier can yield immediately to
   the next escape beam. This is bounded by the existing refill limit (two by
   default) and the original absolute deadline. Fixed/prequalified throats and
   already-admitted incumbents cannot be discarded by this early yield. Trial
   copper is rolled back before handing the evidence to the next beam.
2. An ephemeral, bounded negative-query cache reuses completed refused local
   fan-in queries within that rollback transaction. Its key includes the
   policy/domain, full unrounded portal row, electrical polarity, exact pin
   locations, local search mode and path budget. Deadline failures, incomplete
   results, exceptions and positive results are not cached. A positive result
   must still materialize copper and pass the normal exact checks.

The cache is fresh for every `_route_coupled_via_portals` invocation, even if
the caller supplies a shared whole-screen cache. Neither change declares a
board globally impossible, creates a keepout, changes a clearance or width,
permits an unqualified via-in-pad transition, or weakens route admission.

Implementation: `scripts/cec_portal_feedback.py` and
`scripts/cec_precision_route.py`. Controls `early_portal_feedback` and
`cache_portal_negatives` allow bounded ablation without altering board policy.

## Validation

- 42 portal-feedback tests pass, including a native KiCad fixture with real
  local copper and an injected exhausted global frontier. With early feedback
  enabled, the beam stops after one failed combination; without it, it tries
  multiple combinations. Both roll back every trial track.
- Expanded related regressions: **264 passed, two subtests passed, no skips**.
  Log: `build/portal-feedback-expanded-tests-20260911.log`.
- The protected PCIe two-port control retains its exact PCB hash, entire score
  and entire constraint report compared with the September 10 v3 replay. It
  remains 0 DRC / 0 opens. Existing broader release failures remain failures;
  this is not a new fabrication approval.
- The generic-core audit passes. Existing full-runtime debt is unchanged:
  23 physical-selector findings and 380 runtime-selector findings. The whole
  legacy runtime is **not** claimed to be generic.

Native before/after pair replay uses the identical accepted placement input
`build/baseline-handoff-20260910-v3/board.kicad_pcb` (SHA-256
`eb56de3d1173b0a3aa706045c805d228221aef0ecf865cf5e94199d3daf89408`).
Only this slice's two controls differ. The native default is 240 seconds per
pair, not the smaller probe allocations used in earlier placement experiments;
do not attribute an improvement from extra effort to this code change. Timing
under concurrent suite load is diagnostic, not a controlled speed benchmark.
Evidence is in `build/portal-feedback-20260911-{before,after}/result.json`.

The native comparison completed in 274.19 s before and 273.02 s after. Both
routed CAN and refused CAN_INT (detour limit) and USB (second flow-through leg
deadline). **No connectivity gain is demonstrated by this slice on this input.**
No early-refill or negative-cache-hit witness appears in the retained native
report. The synthetic regression proves the corrected path; this board's
remaining refusals are not claimed to be solved by it.

## Parallel current-BETA campaign

`build/current-suite-20260911-a/suite.json` is the live authority. All six
manifest-enabled main boards started together, with two placement workers per
board, 12 craft trials, four routing passes when admitted, and a 1,200-second
per-board job cap. The engine is frozen for the duration. Each process checks
source and engine signatures on exit. There is no automatic promotion.

| Board | Input |
|---|---|
| 12VHPWR | Accepted September 10 v3 placement experiment, freshly revalidated |
| Standard Hub | September 10 derived placement, freshly revalidated |
| EPS | September 10 derived placement, freshly revalidated |
| ATX 24-pin | Fresh normalization/placement from the manifest's current source |
| PCIe two-port | Fresh normalization/placement; protected zero-open control remains separate |
| PCIe three-port | Fresh normalization/placement from the manifest's current source |

ARGB and output daughterboards remain reported as not wave-enabled, rather
than being silently counted as successful main-board runs.

The campaign starts only above its 8 GiB free-space floor. About 74 GiB was free
at launch. Inputs, source schematics and protected power copper are not edited
by this coordinator; rejected experiments stay in their build directories.

## Initial cross-board failure trace

All six boards passed source intake. 12VHPWR passed placement admission and
entered route preflight. EPS failed placement, not routing: native courtyard
checks find overlapping terminal bodies/pads, and its craft report refuses
stranded/detection-cell geometry, terminal ordering and four current corridors.

A read-only native inspection found two distinct EPS terminals sharing exactly
the same `(75.65, 35.6, 0 degrees)` seat. This is diagnostic evidence, **not** a
request to hard-code new coordinates. The placement-worker configuration has
no declared interface anchor and no pinned placements. A single fresh-source
comparison (`build/current-suite-20260911-eps-fresh`, four trials, 420-second
cap) distinguishes inherited candidate damage from a still-active generator
problem. Do not route this collision or reinterpret its failed gate as a pass.

That fresh comparison also produced overlapping terminal bodies. A generated
baseline was preserved as `build/eps-fresh-generator-witness-20260911.kicad_pcb`
with read-only terminal geometry in
`build/eps-fresh-terminal-floorplan-20260911.json`. The exact duplicate seat is
not reproduced in this particular fresh baseline, but invalid terminal spacing
is. The old `_role` / `_is_blade` / `_seat_blade_fields` path still groups TB
references as blade fields and writes a zero-degree rotation. Geometry-aware
terminal-group seating, honoring declared mating geometry before power-copper
generation, is the next placement investigation. No terminal-specific move
has been added as a repair here.

The Hub's first accepted priority repair uses the existing generic
`pair_endpoint_station_rotation` operation, rotating a connected two-component
station by 180 degrees. Its full exact evaluation reduces remaining critical
pair edges **6 -> 4** (one pair still refused). The accepted operation takes
428.88 s and returns its incumbent via `remaining_budget_preserves_incumbent`.
This progress belongs to the full pipeline run; it is not isolated evidence
that the new cache caused the improvement. Evidence:
`build/current-suite-20260911-a/hub-standard-rev2/02-placement/operation-priority-repair-y536lx79/report.json`.

**Final Hub outcome supersedes that intermediate result:** exact filled-power
admission rejected the proposal and restored the selected baseline, which still
has six remaining critical-pair edges. The causal record is
`priority_route_repair.cooptimization.history[0].route_authority_failure` in
`02-placement/board.placement.json`. It names
`protected_rail_open_after_exact_fill_and_guarded_repair`: `+5V_SYS` is open
both before and after that guarded fill/repair check. Therefore this evidence
does not establish that the rotation introduced the power defect. It establishes
that the incomplete power path prevents retention of the pair-only improvement.
The preview `build/hub-station-rotation-20260911.png` is this **rejected diagnostic
proposal**, not the selected placement and not a fab candidate.

The fresh EPS comparison stops after 392.97 seconds when the campaign reserve
refuses another placement-measure operation. Its source and engine stayed
unchanged. The saved generation witness remains valid failure evidence, but
the comparison did not complete placement admission.

12VHPWR finishes preflight with `admission_gate: false`. Its legacy journal
prints PASS from analysis `ok: true`, and the old suite projection also marks
that stage admitted. Two synthetic regressions reproduce this reporting defect
in `build/stage-admission-reproducer-20260911.log`. The canonical pipeline
still correctly blocks routing. The reporting repair was applied only after the
frozen-engine cohort finished; old reports remain immutable evidence.

The compact closeout snapshot is generated by
`tmp/portal_feedback_closeout_20260911.py` into
`build/portal-feedback-closeout-20260911.json`. Consult the live suite journals
for later progress; an unfinished stage is not an admitted board.

## Shared admission-reporting repair

`cec_stage_admission.admission_ok` now provides a single strict tri-state
projection for both `StageJournal` and the suite coordinator. An explicit
`admission_gate: false` overrides successful analysis execution; absent or
malformed evidence remains unknown. New journals store `admission_ok` separately
from execution status, print BLOCK/UNKNOWN correctly, and label cached refusals
RESUME-BLOCK. Budget-failure projections preserve their causal reason. The
canonical pipeline's existing admission checks are unchanged.

The two demonstrated failures now pass. The journal/suite/full-pipeline focused
run passes **108 tests** before two additional budget-reason cases were added.
The combined final regression run passes **360 tests and two subtests, with no
skips**, in 61.49 seconds. Results are in `build/portal-feedback-final-tests-20260911.log`.
The final PCIe control replay retains its exact board hash, score and constraint
report; existing broader release blockers remain unchanged.

## Completed cohort outcome

All six jobs ended within their 20-minute budget (plus process teardown), with
unchanged input/source and engine signatures. No detailed-routing stage was
admitted and no candidate was promoted. The reporting-only repair above was
not part of that earlier frozen-engine cohort; the compact closeout applies its
corrected projection to the unchanged raw journals.

| Board | Retained result | Elapsed |
|---|---|---:|
| 12VHPWR | Placement admitted; preflight refuses CAN_INT detour and USB flow-through leg | 591.8 s |
| Standard Hub | Pair-only 6 -> 4 proposal rejected by filled-power admission; selected result still 6 | 933.4 s |
| EPS | Terminal/body and craft blockers; no route admission | 112.6 s |
| ATX 24-pin | Placement budget exhausted | 1200.2 s |
| PCIe two-port fresh | Budget reserve refuses final fiducial operation; no placement admission | 1179.4 s |
| PCIe three-port fresh | Placement budget exhausted | 1200.1 s |

The next physical work should address the demonstrated terminal-group generation
failure and the interaction between incomplete protected power and pair repair.
The evidence does not justify another identical batch or a fabrication claim.

All campaign workers have stopped. Retained artifacts are bounded: the six-board
cohort uses 25 MiB, the EPS comparison 1.7 MiB, and the native before/after pair
experiments about 5.6 MiB each. No source boards or schematic hierarchies were
edited by this slice.
