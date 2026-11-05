# Native ATX refinement after legacy-job retirement

The obsolete job cleanup was merged in PR #72. This follow-on uses the
frontier-directed workbench, not a resurrected wave runner.

## Received change

The ATX +3V3 triangle and its 0.1725 mm redundant cross-link were replaced
together by a vertical run and a 45-degree approach. Exact source ports,
retained branch contacts, 0.20 mm width, face, current requirement, placements
and dimensions remain unchanged. The generic power-route constructor now
accepts a bounded connected source tree; saved boundary/partition/current
receivers still decide whether every branch is preserved.

- Parent PCB: `af7374467e8020c57b3d5d098b3443ebf8a0b3fa68e85a3da14f21f4fed2b25e`.
- Reviewed PCB: `931ab3037222e1f8ecd06481188b0d0ba100e941c73f391d34cb9bfc8a2b4319`.
- Redundant centerline removed: 1.752399 mm.
- Native ATX result: 0 opens, 0 errors, 67 warnings, 0 exclusions, unchanged.
- Craft findings: 49 to 47; no non-octilinear tracks introduced.
- Current, Kelvin preservation, field and declared assembly receivers passed.
- All nine boards were remeasured after portable relocation: 0 opens, 0
  errors, 283 warnings and 0 exclusions in total.

The first three-track trial correctly exposed a dangling cross-link; it was
not selected. Removing the complete four-track tree resolved that warning.

## Removed validation overhead

The old Kelvin wrapper tried two monolithic whole-board cut replays for an
unrelated supply edit. The source replay exhausted its 10-second budget and
could not provide complete evidence. A new exact non-interference receiver
takes about 3.7 seconds on this pair: it checks both fresh complete lineage
manifests and authority, then proves that every other native object, hole,
via, fill, edge, setting and project companion is unchanged. No changed net
may belong to any declared sense pair, typed lineage segment or force domain.

This is not a timeout waiver or a cached positive Kelvin result. Broader edits,
protected copper, unresolved lineage and changed authority cannot take this
path. Absolute cut replay is still required when applicable; native DRC,
current, field and assembly checks remain independent and mandatory.

## Evidence and limits

The portable checkpoint is `checkpoints/review-20261105-atx-refinement/`;
its receipt, work order, actual before/after copper SVGs and native reports
are retained in Git. Earlier controls remain recoverable and unchanged.
The active workflow tests passed (257); the typed power-route/reflow set
passed (132, overlapping that set). Non-interference has positive and
negative native tests for renamed and filtered inputs, rotations, protected
tracks, renetting, pads, holes, fills, settings, companions, unresolved
lineage, incomplete manifests and concurrent code changes.

This is review nonregression, not fabrication, whole-board Kelvin, electrical,
thermal or mating approval. The ATX still has 47 craft findings; the five
recorded EPS coupling blockers and other qualification work are not erased.
