# Recovery finalization and return-field hole snapshots — 2026-09-20

## Board result and current input plan

Use **`build/safe-edge-next-inputs-20260920.json`** for the next explicit cohort.
Only VHP advances from its old three-edge-fault input to the previously proved
edge-repaired placement (`e9fd08b171747ac1eb3b6cb567036b4047218f29935410d876eedba465872323`).
The new row binds the publication journal, independent native proof, fresh
source/hierarchy signature and a new current-engine physical evaluation.
The other five board inputs are unchanged. This is a next-input handoff, not a
canonical BETA PCB replacement or fabrication promotion.

`build/edge-continuation-physical-current-20260920.json` independently reconfirms
the physical placement gate under the final code. VHP still has **220 opens,
one USB priority refusal and C7's local-interconnect deferral**. No new routed
copper was admitted by this continuation. Hub retains one recorded local-return
blocker and its 174-pose history. EPS/ATX remain held pending the mating-span
choice, with no unchanged waves spent on their known terminal conflicts.

## What the full continuation actually did

`build/verified-edge-continuation-20260920` was one new, bounded 480-second
production attempt from the journal-verified edge repair. Source intake passed
in 12.5 seconds, and fresh physical placement admission passed. The exact
critical-route probe still refused USB. Critical-only recovery produced no
accepted complete pair; two staged attempts stopped after repeated unadmitted
geometry. The parent and final working PCB remained byte-identical to the
verified input. All source and hierarchy signatures stayed unchanged.

The complete attempt ended after **445.281 seconds** when its final physical
measurement exhausted its remaining **34.812-second** operation allowance.
This was not a newfound placement overlap or permission to skip validation.
The scheduling defect was that critical recovery ran *before* the co-optimizer's
120-second finalization reserve, so reserving time inside co-optimization was
already too late.

The attempted fallback's own pre-rollback evidence—not the subsequently
restored parent's absent USB tracks—records these existing-policy failures:

- Different P/N layer sets and two transition vias on P versus zero on N.
- Two transition vias without a GND return within the declared 1.5 mm reach.
- Filled adjacent-GND coverage 94.0% against the existing 95% requirement.
- Coupled coverage 16.5% against the existing 80% requirement.

Evidence is the first tier in
`12vhpwr-standard/02-placement/priority-recovery-fc3g0r9x/wave-00/board.tier-progress.json`
under that attempt. The precision constructor separately records refusal of
the second flow-through leg through D3; the proposed stations did not produce
a qualifying coupled corridor. These are result witnesses, not new refdes
selectors. Do not restart the rejected ordinary fallback unchanged or portray
an arbitrary connected single-ended route as a qualified differential pair.

## Generic repairs

### Finalization reserve covers critical recovery too

`cec_full_pipeline._recover_placement_priority_routes` now runs its private
worker under the existing parameterized `placement_coopt_finish_reserve_s`
lease (default 120 seconds). Every child inherits the shortened deadline;
the parent's original deadline is restored before validation or commit.

Only explicit supervisor budget exhaustion becomes an unchanged optional
recovery result. An interrupted success-looking receipt is never read or
committed. Crashes, cancellation and other integrity failures still propagate.
Completed admitted results retain the existing commit gates. This does not
claim a finite reserve guarantees every conceivable board can be validated
within it; it fixes the observed omission of that reserve from recovery.

### Scalar drill snapshots for pair-return fields

The native operation stack repeatedly sampled `GetTracks()` inside each
return-via seat's drill check. Copper-shape snapshots were already shared within
the immutable field, but its hole test still re-enumerated all native tracks.

`cec_precision_route._add_pair_transition_returns` now also builds the existing
scalar `HoleIndex` once for that immutable field. The index supplies only a
conservative candidate subset; the same exact drill and all-layer copper checks
still decide every seat. It is rebuilt after every added return via and is not
reused across independent calls or mutation boundaries. There are no retained
SWIG object pointers or new board/refdes/coordinate cases.

## Validation and measured work

- Red regressions: five expected failures and two passes after correcting the
  saved-native fixture to retain GND on a real copper item; KiCad otherwise
  drops that unreferenced test net. No production behavior was changed to fit
  the fixture. See `build/recovery-return-red-v2-tests-20260920.xml`.
- **297 tests and two subtests pass**:
  `build/recovery-return-broad-tests-20260920.xml`.
- Tests cover inherited deadlines, restoration, timeout versus crash behavior,
  refusal to commit interrupted receipts, and a real supervisor timeout with
  save/reloaded native parent copper left intact. Native return-field tests
  compare exact seat verdicts/refusal evidence and rebuild the snapshot after
  a new barrel changes the hole geometry.
- Four-board loaded-native field replay:
  `build/return-hole-snapshot-cohort-20260920/report.json`.
  All 25 sampled fields produce identical return geometry/reasons and preserve
  every existing copper item. All **1,331 seat queries** remain present.

| Board | Fields | Native track enumerations before → after |
| --- | ---: | ---: |
| PCIe2 | 5 | 170 → 19 |
| PCIe3 | 5 | 620 → 52 |
| Hub | 8 | 349 → 37 |
| VHP | 7 | 335 → 35 |
| Total | 25 | **1,474 → 143** |

This is **90.3% fewer native track enumeration calls within those return fields**,
not 90.3% faster whole-board routing. Single-pass diagnostic timing is retained
in the reports but is not a controlled end-to-end speed claim. EPS/ATX were
excluded from this constructive probe by their interface-ECO holds.

Six-board geometry replay and the historical PCIe2 board/regression/probe
control pass: `build/recovery-return-final-suite-20260920/report.json`.
That replay intentionally uses the previous cohort: its VHP still has the
original three edge faults. The additional current-engine physical evaluation
above proves the corrected new input has zero. Core generic audit passes;
wider legacy release debt remains, with `release_ok=false`.

## Review and continuation

[Immutable attempt review](http://localhost:8090/?id=pass-verified-edge-continuation-20260920-12vhpwr-standard-4e74d71338)
is correctly labeled **placement-checkpoint:seed / BUDGET EXHAUSTED / NOT FAB
SIGNOFF**. It is the same unchanged board, not a new routing success. Both
body-free images were inspected, and both immutable PNG endpoints return 200
from Windows localhost. Mirror:
`C:/Users/Admin/Documents/CEC-Board-Reviews/verified-edge-continuation-20260920/12vhpwr-standard/`.

Do not automatically run the same full wave again solely because the scheduler
now reserves time. A useful next slice must improve matched pair station/return
construction or its actual obstacle model, then exercise that change across
admissible boards. C7's local interconnect still must be constructed before
residual routing; nothing here waives it. The reserved-budget fix is covered by
synthetic and real-supervisor/native tests; a complete new full-board route pass
after that fix has **not** been claimed.
