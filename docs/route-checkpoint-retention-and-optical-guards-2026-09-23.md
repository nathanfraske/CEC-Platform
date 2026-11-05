# Transactional route checkpoints and optical guard parity, 2026-09-23

## Scope

Continue the generic routed-prefix pipeline without losing completed work on
worker timeout. No schematic, BOM, outline, functional component placement,
power-current requirement, or fabrication rule is changed by this slice.
Current Hub input: the independently verified 140-open checkpoint from
`power-prefix-continuation-20260923/signal-stage-proof`, not an older beta PCB.

## Completed implementation

- Each route worker receives a checkpoint callback at completed electrical
  stages. Only named completed stages with fresh native counts can publish;
  arbitrary temporary PCBs and failed-stage artifacts are never candidates.
- Two owned flat slots alternate behind an atomic, digest-bound pointer.
  Complete PCB/project/rules/pour-state/skeleton families move together.
  Changed source authority, mutated files, interrupted copies, invalid
  identities and oversized families are refused. At most two 64 MiB families
  per worker are retained; the current Hub families are much smaller.
- After worker shutdown, the coordinator regrades a bounded shortlist (three
  by default, hard cap eight). It checks all incumbent release terms plus
  original copper, qualified pairs, original and newly declared power
  obligations, physical power-zone declarations, outline and placements.
  Stored stage success and counts are not admission certificates.
- Accepted work competes in the ordinary incumbent selection. A checkpoint
  winner is copied out before candidate-tree cleanup and does not spend its
  remaining certification budget on optional finishing. Independent signoff
  still withholds incomplete boards.
- Worker failure records keep counts unknown. Missing reports no longer
  masquerade as measured physical-gate regressions in candidate summaries.

Implementation: `cec_route_checkpoint.py`, the route oracle's trace callback,
and the normal single/parallel coordinator in `cec_full_pipeline.py`.
No board name, refdes, net name or coordinate is a repair dispatch condition.
Board family and seed are identity metadata, not geometry special cases.

## Whole-board admission exposed an optical-rule mismatch

The first native recovery replay properly refused to replace the 191-open
incumbent with the previous 140-open checkpoint: the latter failed the
fiducial optical-clearance term. The earlier checkpoint proof checked native
DRC, power/pairs and parent preservation but was not full craft signoff.

The exact conflict was a 0.2 mm EN trace passing 1.5904 mm from the fiducial
center, leaving 1.4904 mm to copper versus the optical gate's 1.5 mm minimum.
The router had protected only a 1.275 mm half-width library bounding box.
Those coordinates identify the observation; none is an implementation rule.

`cec_fr.fiducial_keepouts` now protects the union of the actual footprint box
and the parameterized optical field (1.5 mm default), with outward rounding.
Opposite-side and inner-layer routing remain available.

For already-routed candidates, checkpoint admission can make one private
proposal using the existing general peripheral fiducial allocator. Only real
fiducial-library footprints with no electrical net are eligible. Fresh native
proofs require all candidate copper, functional component poses, physical
power declarations and power/pair connectivity to remain intact. The complete
oracle must still pass every previously satisfied incumbent gate.

On the Hub this allocator moved one optical mark by 0.5 mm, leaving all copper
and functional components unchanged. It did not reroute EN or modify a pour.

## Native fault-injection evidence

`build/route-checkpoint-continuation-20260923/hub-timeout-replay-v2/` exercises
the production coordinator with a deliberate exception immediately after a
complete stage publication. It performs no routing search:

- Candidate and assembly proposal were freshly graded **0 DRC / 140 opens**.
- Native parent/power/pair preservation passed, with no incumbent gate loss.
- The coordinator selected `route_checkpoint`, not the **191-open** incumbent.
- Source families and engine files stayed unchanged during the replay.
- The complete replay took 29.329 s; release remained withheld.

The same native injected-failure replay on the PCIe two-port fab-review
control retained its equal **0 DRC / 0-open incumbent**. No control board was
edited, and its pre-existing release-only findings were not waived. The
updated-engine replay is `pcie-timeout-replay-v2/` (23.989 s).

Synthetic tests additionally kill a real spawned writer midway through a
copy and verify the previous committed family survives, refuse tampering and
source changes, exercise storage limits and invalid counts, and verify that
failed preservation cannot promote a checkpoint. Optical tests check that
the routing keepout covers signoff's field even with a smaller library box.

## Normal continuation

A normal bounded, two-candidate full run completed under `full-pipeline/`.
It passed source intake, placement and preflight, and both route workers
returned normally. This was a real routing search, not the injected-failure
test. The approximately 16.6-minute end-to-end run produced **0 DRC / 28 opens**
and **0 DRC / 29 opens** from the **0 DRC / 140-open** input. Four-pass global
Java routing took 113.7/119.3 seconds; the longer import/completion phase also
performed the bounded local and wider gap searches. Retained checkpoint
families occupy about 7.5 MiB across both workers.

The stronger admission found three distinctions that the earlier worker
success flag did not establish:

1. Filled zone objects acquired new KiCad UUIDs without any physical
   declaration changes. The ownership comparison now ignores only those
   generated IDs; net, layer, rule-area status, name and contours still count.
2. The missing-layer-junction importer added two unnecessary transition vias
   to an already qualified CAN pair. The importer now respects its upstream
   completed-net ownership set. For retained older snapshots, a bounded
   correction may remove only new vias on parent-qualified pairs; it must
   prove that all parent copper survives and native connectivity, pair
   physics, power obligations and score admission still pass. No named
   board/net/refdes dispatch is used. Source files are never edited.
3. Normal worker cleanup had removed those extra vias, but later fabrication
   polishing changed four previously protected copper primitives. Such
   geometric edits were not independently proved equivalent to the owned
   prefix. Normal returns now receive the same continuation proof as rescued
   snapshots, and new proposal winners receive the immutable pre-finish
   rollback point previously afforded only to incumbent winners. A rejected
   polish restores the selected proposal, not the older inferior input.

The native correction uses the shared `cec_native_items.discard_items`
operation and isolated refill. KiCad `Remove()` instead of native `Delete()`
reproduced a SWIG lifetime failure after returning from the correction; the
native synthetic regression now exercises deletion, garbage collection and
subsequent board loading, as well as source preservation and failed-proof
refusal.

## Accepted result and verification

`hub-recovery-28-v4/` runs the production coordinator against the real
28-open snapshot, with an injected post-checkpoint failure. The coordinator
automatically corrects the two generated pair vias, freshly grades the board
and selects it. This replay took 36.513 seconds and did no new route search.

- **0 native DRC / 28 opens**, a reduction of 112 opens (80%) from this slice's
  140-open input; 163 fewer than the earlier 191-open source.
- All **551 protected input copper primitives** retained; no missing items.
- Previously qualified **USB and CAN pairs** remain connected and pass their
  pair physics checks; all **eight source/sink power obligations** pass.
- Functional placements, outline and physical power declarations unchanged.
  This final 28-open admission needed no additional fiducial relocation.
- Input families and engine files unchanged during the native replay.
- PCIe two-port final-fab-review control remains exactly **0 DRC / 0 opens**
  in `pcie-timeout-replay-v4/` (24.883 seconds), with its original source hash
  `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
- Active Hub/ATX placement-pair manifest and ATX placement hashes unchanged.

Final regression run: **1,552 passed, 13 subtests passed**, no failures, in
168.76 seconds (`build/route-checkpoint-continuation-20260923/regression-final.log`).
The only warning is KiCad's existing deprecated SWIG-interface notice. Coverage
includes checkpoint crash/tamper/storage behavior, normal-candidate and finish
rollback, native deletion lifetime, fiducial guards, protected junction-via
exclusion, pairs, portals, power ownership, last-mile import and coordinator
behavior. Earlier test-fixture omissions were repaired and the entire selected
suite rerun cleanly; no failing tests were excluded from this final run.

The final selected PCB is
`build/route-checkpoint-continuation-20260923/hub-recovery-28-v4/winner.kicad_pcb`,
SHA-256 `445b40561b8871cc1b32d8c63a2fb3f1bc31b0f15f692190142496de111d3396`.
Use this exact retained board for the next routing continuation, not the
earlier full run's unadmitted polished winner or the placement-only source.

[Dashboard: retained 28-open Hub](http://localhost:8090/?id=20260923-hub-standard-rev2-checkpoint-continuation-445b40561b)
contains hash-bound top/bottom models-off renders and all six native copper
layers. The Windows-side catalog and all eight image endpoints returned HTTP
200 with nonempty PNG/SVG content. Publication writes its summary last.

## Remaining obligations, not waived

This is routing progress, **not a fabrication candidate**. A separate native
independent signoff on the exact retained bytes remains withheld:

- 28 unconnected items across 12 nets, including ground; connected rated
  source/sink paths do not imply every auxiliary pad on those nets is closed.
  The measured distribution is +5VSB (9), +3V3 (4), +5V_SYS (3), USB_VBUS (3),
  GND (2), and one each on KVM_5V_IN, GPIO0, the two OV1 inputs, the two SS
  inputs, and the DL5 output. These are observations, not board-specific
  routing rules.
- Courtyard-to-edge finding at C37: 0.475 mm versus the existing 0.8 mm rule.
  This is diagnostic identity, not a proposed refdes-specific repair.
- Seven covered-backtrack route-geometry advisories remain. Generic cleanup
  must either preserve owned copper or explicitly prove the allowed physical
  equivalence, rather than silently erase a protected primitive.
- Current-injection modeling/thermal solve not qualified: thermal was
  deliberately skipped under the existing lazy policy while other gates fail.
- Independent constraint, hardware-qualification and draft/release gates are
  still withheld. No incoming-sample qualification is inferred from routing.
- The blocker log still reports `full_fail_stack: false`; it is not yet a
  complete causal explanation for every remaining open.

Next slice: classify the remaining open endpoints against actual imported
copper/planes, feed their specific failure stage into bounded generic repair,
and retain this admitted incumbent on any regression. Do not reopen completed
power/USB/CAN work or expand the board to cover a solver defect.
