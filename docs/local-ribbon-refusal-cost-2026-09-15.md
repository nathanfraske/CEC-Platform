# Local pair-search cost and inherited-cell producer evidence

## Generic routing change

`cec_precision_route._route_paired_stub` collected full native blocker identities
and evaluated every leg for every refused ribbon, even after the four retained
diagnostic witnesses were already full. Dense local escape searches spent time
building evidence that was immediately discarded.

After those four witnesses, the solver now short-circuits a candidate only when
one of the **same exact native physical predicates** fails. It uses the existing
immutable-solve cache and preserves the original candidate order/domain. Every
survivor still receives the full octilinear, spacing, crossing, coupling,
handoff, reservation and native-geometry checks. The first four detailed
witnesses remain unchanged; additional exact physical rejections are counted.
No clearance, fabrication floor, search budget, fixed copper or component pose
is relaxed. This is not a product/refdes/coordinate repair.

## Measured result, not a closure claim

The isolated native A/B uses current VHP **3af185f38201**, no contact-seat
prototype, and the same 120-second pair cap. Actual elapsed times are lower
because the existing internal flow/portal budgets terminate earlier.

| Measured in the same bounded pair experiment | Exhaustive evidence | Exact early refusal |
| --- | ---: | ---: |
| Pair wall time | 67.39 s | 66.48 s |
| Local-solver calls | 1,155 | 1,520 |
| Sum of local-solver wall time | 35.42 s | 30.70 s |
| Ribbon candidate evaluations | 37,834 | 57,434 |
| Complete USB pair accepted | no | no |

This is **about 52% more ribbon evaluations**, with about **13% less local
solver time**, in this one native A/B. It is not a universal speedup claim,
not a 52% whole-router improvement, and not another board entering routing.
Bounded-clock searches can visit different frontiers; equivalence without
deadline pressure is tested independently below.

Evidence: `build/vhp-fanin-breadth-probe-20260915/comparison.json` and each mode's
`local-solver-calls.json`. The prototype ran in isolated worker memory before
the shared implementation was changed.

## Verification

- **285 tests and two subtests pass**, no skips, 13.85 s:
  `build/ribbon-prefilter-final-tests-v3-20260915.log`. New loaded-native cases
  cover renamed/translated/quarter-turned front/back geometry; foreign pads,
  foreign tracks, partner pads/copper, reservation and board-edge refusals;
  unchanged first witnesses and source bytes; exact accepted copper against
  an exhaustive-evidence control; and a valid thirteenth ribbon after twelve
  physically blocked proposals. Foreign-blocker enumeration is less than half
  the old count in the relevant fixtures.
- The initial fixture had unused nets dropped on save and an invalid LSET
  constructor; real endpoint pads and explicit layer sets correct those test
  errors. A later test mistakenly treated a legal uncoupled fallback as a
  qualified ribbon; its replacement uses an actual nominal-pitch ribbon and
  native edge failures. No production admission was relaxed to pass a test.
- `build/ribbon-prefilter-suite-replay-20260915/report.json`: old/current
  private selected-pair probes across all six **explicit retained sources**,
  four process workers, 40-second pair caps. EPS/ATX correctly stop at their
  interface-ECO gate. Hub's selected USB pair succeeds in both versions;
  PCIe2 retains its existing pair with zero added copper; VHP remains refused;
  PCIe3 emits the same pair but retains its independent pair-quality refusal.
  A `routed` entry alone does not mean `pairs_ok` or fabrication readiness.
- `native-comparison-v3.json` in that directory independently compares all
  four diagnostic outputs: native copper geometry, poses, structural DRC,
  connectivity, length, tracks/vias and pair/Kelvin gates are identical.
  These are partial diagnostic boards; Hub still has DRC failures and neither
  its nor PCIe3's diagnostic copper is promoted. All original sources and
  hierarchy signatures remain unchanged. Native comparison v1/v2 omitted
  some scalar fields due a diagnostic field-name error; v3 requires the exact
  real `Metrics` fields rather than silently omitting absent attributes.
- Generality passes. The historical PCIe2 control's PCB bytes, full regression
  and probes are identical; only generalization metadata differs:
  `build/ribbon-prefilter-control-comparison-20260915.json`. Its existing
  release holds remain; the expected control exit code is one, not a new fault.

## Separate progress: actual historical local-cell producer located

Read-only lineage inspection found an actual accepted producer report, not
just current group names:

- Journal: `build/current-search-branch-full-suite-20260914/pcie-8pin-2port/pipeline-state.json`.
- Its hash-bound oracle records **64 generated items across 14 local cells**.
- Its exact output is **9f445b897a34**, an ancestor of current PCIe2 **905f961c6257**.
- `build/local-cell-producer-lineage-screen-20260915.json` compares native-file
  primitive data, including unknown serialized fields, against the current
  board. Thirteen complete *recorded generated-item sets* are unchanged.
  Eleven of the 60 current immutable blockers are among these unchanged
  generated records, across five cells. U31/C31's set is not unchanged.

This establishes useful producer evidence for a bounded replacement design;
it does **not** prove complete dependency ownership, authorize unlocking eleven
tracks, or qualify a whole-cell rebuild. The next slice must bind the receipt
to source/owner/cap/pad geometry, account for reused/shared copper and complete
cell boundaries, and require native requalification plus whole-board rollback.
Do not infer that every inherited blocker is a decoupler or pipeline-owned.

## Current scheduling state

All experiment, replay and control workers have exited. No full board cohort
is running and no new dashboard/fab candidate was published. The canonical
retained inputs are still `build/copper-curve-next-inputs-20260915.json`.
The Hub remains on four hard craft holds and must not receive an unchanged
distance-only retry. PCIe2 has ten opens; PCIe3 and VHP retain their distinct
priority holds; EPS/ATX need qualified coupled interface geometry. Use the
new producer evidence for the next ownership slice, or another distinct
cross-board cause, rather than another unchanged full wave.
