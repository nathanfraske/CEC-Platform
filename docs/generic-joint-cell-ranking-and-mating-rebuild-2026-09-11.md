# Joint-cell ranking and interface rebuild boundary — 2026-09-11

## Scope

This slice changes proposal scheduling, not electrical limits or release policy.
The current manifest/hierarchies, approved operating modes, loads, margins, BOM,
board outlines, and protected PCIe review control are unchanged. No fabrication
release is granted. Existing unrelated worktree edits have been preserved.

## Root cause and generic repair

`_decoupler_owner_move_specs` already constructs a finite, jointly legalized
capacitor placement menu for several owner orientations and translations.
However, each orientation was optimized independently, then concatenated in
enumeration order. The bounded downstream selector reserves an early atomic
proposal. Consequently, a first-orientation proposal with positive hard excess
could take that slot ahead of a later zero-excess orientation.

The new neutral `cec_cell_proposals.ranked_joint_proposals` orders complete
joint proposals by external blocker count, measured worst/total excess and
projection cost, then pose displacement/rotation. Invalid or unknown evidence
does not outrank measured evidence. All alternatives remain available; the
same downstream native geometry, protected-copper, electrical, and monotonic
admission checks still decide acceptance. Ranking is not admission.

The production owner mover now applies this ordering to both joint reorientation
and translated/reseated menus before interleaving and finite probe selection.
There are no product, reference, or board-coordinate exceptions in the helper.
It is included in the generic-core audit and is discovered by the existing
transitive code-closure hashing for stage invalidation.

## Reproduced native result

Source: PCIe 3-port's verified placement checkpoint, SHA-256
`8e4a7c148507a917466b87a31b8ed45adb734c771f213c75eb9fd78ae6e69d0b`.
The interface pass I copy has the identical board bytes. This is placement
work, not a routed or admitted artifact.

The recorded menu has 256 non-overlapping joint reorientation proposals for
the failed power-mux owner. The old first proposal has rank
`[0.907296, 0.907296, 0]`; a later rotated proposal has `[0, 0, 0]`.
The native replay chooses owners from missing-assignment evidence, not a
hard-coded reference move. Its before/after boards are disposable ECO copies;
their route authority remains invalidated until rebuilt normally.

| Measured supply pad-center distance | Original | Old menu head | New ranked head |
|---|---:|---:|---:|
| Input 1 / C45 | 11.087 mm | 2.720 mm | 2.214 mm |
| Input 2 / C9 | 8.284 mm | 1.600 mm | 1.612 mm |
| Output / C6 | 6.690 mm | 1.836 mm | 1.746 mm |

The old head resolves assignments but leaves C45's return and proximity
failures. All three cells pass assignment, proximity, and pre-route local
access with the new head. Total reported decoupler violations change 9 → 8 → 6;
missing assignments change 3 → 0. Supply distance alone is not the full
objective: the complete cell, including its return relationship, is checked.
This is **pre-route feasibility**, not completed copper/impedance qualification.

All unrelated footprints, existing copper, and outline are preserved by the
ECO transaction. No new stranded component is reported. Five current-corridor
planner failures and the other placement blockers remain. Native full-craft
comparison times are 16.077 / 16.873 / 17.648 seconds; this is a quality result,
not evidence of an overall pipeline speedup.

Evidence:

- `build/bypass-search-forensic-20260911.json` — full oracle and proposal menu.
- `build/cell-ranking-replay-20260911/report.json` — native before/old/new results.
- `build/cell-ranking-replay-20260911/ranked-head/board.interface-eco.json` —
  changed poses, source/output binding, preserved copper, invalidated authority.

## Real interface-ECO rebuild proof

ATX 24-pin, EPS, and PCIe 2-port canonical inputs have the prior interface ECO's
invalidated route authority. Each was synchronized into a fresh disposable
working copy using the production normalization function. All three copies:

- matched their current schematic hierarchy;
- had zero track/via objects and zero non-rule copper zones;
- received a hash-bound copper-free replacement-seed certificate;
- passed the subsequent production source-intake gate, including current
  project rules and the existing approved electrical audit;
- left all declared source inputs unchanged.

Times: 15.746 / 12.943 / 12.768 seconds respectively. Evidence:
`build/mating-rebuild-proof-20260911/report.json`.

This proves that stale interface copper is not carried into replacement
placement. It does **not** prove new route authority, correct detailed routing,
measured mechanical fit, seating depth, or anti-mismatch keying. Those gates
remain open; the normalized staging copies are not review-board candidates.

## Regression evidence

- 229 tests passed in 30.71 s: joint proposal ordering, owner-mover integration,
  one-trial selection, translation invariance, malformed evidence, collective
  domains, and the native placement-craft admission suite.
- 52 additional boundary tests passed in 11.91 s: interface ECOs, pipeline
  guards, generalization, checkpoints, protected-control regression, previews.
- Protected PCIe control SHA-256 remains
  `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`.
  Current score/constraints/route-quality/fabrication payloads are identical
  to `build/mating-audit-release-replay-20260911.json`: 0 DRC, 0 opens,
  615 tracks, 226 vias, 1242.073 mm. Existing broader release blockers remain.
- Generic-core audit passes with zero violations. The legacy runtime is still
  not fully generic: its existing 23 physical-engine and 380 runtime selectors
  are not resolved by this slice.
- `git diff --check` passes for the touched engine/test files.

Logs: `build/cell-proposal-tests-20260911.log`,
`build/cell-ranking-boundary-tests-20260911.log`,
`build/cell-ranking-control-replay-20260911.json`, and
`build/cell-ranking-generalization-20260911.json`.

## Bounded production replay

The independent native comparison above is separate from the production pass
at `build/cell-ranking-pass-20260911`. That pass runs PCIe 3-port, Standard Hub,
and 12VHPWR concurrently, with 12 craft trials, two rounds, one epoch, and a
420-second per-board ceiling. All engines remain frozen during the campaign.
Its actual retained artifacts, admission state, and fresh no-body previews are
recorded in `suite.json`; a timeout or improvement in one local cell is never
substituted for a completed/admitted board.

The pass finished with all source and engine signatures unchanged:

| Family | Elapsed | Retained result |
|---|---:|---|
| PCIe 3-port | 420.035 s | Time limit during placement repair; verified seed retained byte-identically; no completed repair round promoted |
| Standard Hub | 249.120 s | Byte-identical placement; craft passes; one declared-priority route refusal and two critical reachability failures remain |
| 12VHPWR | 382.743 s | Critical recovery exhausted its remaining 50.6 s operation budget; verified seed retained byte-identically |

None entered residual detailed routing or fabrication admission. The retained
PCIe checkpoint does **not** contain the independently demonstrated three-cap
repair. The diagnostic replay proves the scheduling improvement locally; the
production campaign has not yet proved a complete admitted improvement.

The PCIe pass generated 10,142 moves in 55.191 s and selected 12. A live stack
also confirmed time spent waiting for exact native trial evaluation. Bounded
work retention and budgeting across the entire repair round remain a next
target; merely finding a better proposal is insufficient. No second campaign
was launched. The campaign occupies about 14 MiB; WSL has about 74 GiB free.

All three dashboard image endpoints returned HTTP 200 from Windows. Gallery:
`build/cell-ranking-pass-20260911/all-boards-ad9dd0dcf26e7abf.png`, mirrored to
`C:/Users/Admin/Documents/New project/review-output/cell-ranking-pass-20260911/`.
These are retained placement snapshots, not newly routed boards.

The pass also exposed a status-only display bug: a nested native operation
timeout with no final admission result was labelled `REVIEW ONLY`. After the
campaign ended, `cec_pass_review.status_label` was corrected to show explicit
budget exhaustion (including nested operation evidence) or blockage. Invalid
provenance still has precedence, and a successful process alone still cannot
claim release. All 17 preview tests pass, including six added cases. Original
immutable pass images are retained; the 12VHPWR tile in that historical gallery
predates this label-only fix. Its actual status is the budget failure above.
Presentation-only `-status-v2` dashboard revisions now show the corrected
labels on fresh renders of those exact archived board hashes. They do not
represent another pipeline run. All three revised image endpoints returned
HTTP 200 from Windows. The corrected gallery is
`build/cell-ranking-pass-20260911/status-corrected-boards-a3a30ff3c37bcf20.png`
(also in the desktop mirror above), with lineage in
`status-corrected-review.json`. No prior archive was overwritten.

The next diagnostic targets are the unchanged current-corridor refusals and
the expensive critical-pair transition/return-via search. A live 12VHPWR worker
stack reaches `_via_spot_clear`/`_foreign_shape_indexes`/`GetEffectiveShape`
from the coupled via-portal search. This identifies an investigation target,
not proof that caching it is safe or that it is the only runtime bottleneck.
Any acceleration must preserve mutation-aware obstacle/clearance validity.
