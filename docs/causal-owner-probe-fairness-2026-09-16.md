# Causal-owner fairness and concurrent six-board continuation

## Reproduced cause

The prior PCIe3 repair report at
`build/covered-prefix-followup-suite-20260916/pcie-8pin-3port/02-placement/operation-priority-repair-0pj_g83t/report.json`
generated 1,940 proposals and selected 16. Despite nine measured Kelvin-range
failures and directly legal range-closure proposals, its selected causal roots
were only U2, R11, U3 and U4. Three incidental Kelvin probes worsened the count
to ten; no intended Kelvin endpoint closure was sampled. Twelve proposals were
geometrically legal, but no full candidate evaluation occurred.

The allocator called these proposals owner-fair but actually divided slots by
`budget_group`. One owner can generate many station/rotation/portal groups, so
that owner's alternatives exhausted the quota before another owner received a
trial. The direct-physical reserve used the same flat allocation and did not
prevent this starvation. This is a generic search-selection defect, not a reason
to waive a physical gate or hand-place a specific current monitor.

## Repair

`_bounded_owner_evidence_move_specs` allocates the bounded quota to causal roots
first, then uses the existing evidence-family breadth/tail sampler inside each
root's quota. A declared primary root owns its multi-component move; incidental
followers do not multiply its quota. Rootless atomic moves use one joint owner
set. Both ordinary critical-owner selection and its direct-physical reserve use
the helper. Reports now record selected causal-root counts explicitly.

There is no board, net, reference-name, coordinate, component-count or distance
special case. Existing blocker-relief reserves, geometry checks, frozen-copper
checks, complete finalist evaluation and monotonic acceptance remain mandatory.
The change affects candidate selection, not the criteria for accepting boards.

The initial integrated suite passes **233 tests**, with **13 legacy skips**, in
1.98 seconds. Log: `build/owner-fairness-integrated-tests-20260916.log`.
New synthetic cases exercise renamed owners, 100 early alternatives, small and
excess budgets, direct reserves, incidental followers, atomic rootless moves,
unchanged inputs, deterministic order and retained within-owner tail sampling.

## Completed validation

`tmp/owner_fairness_suite_20260916.py` launched six isolated canonical-pipeline
jobs from the exact source/hierarchy hashes in
`build/route-finish-next-inputs-20260916.json`. This is one new-engine pass under
the user's renewed continuation request, not authorization to repeat unchanged
waves forever. It uses six job slots, four nested workers per board, sixteen
placement trials, a 600-second priority-repair allowance and a 1,200-second total
job limit. The larger explicit priority allowance permits at least one complete
pair-probe cohort; the prior 300-second operation had less than the required
305 seconds remaining even before overhead. Search outcomes and scheduling
effects must not be conflated with the sampler change.

Evidence and journal-qualified/explicitly blocked previews are under
`build/owner-fairness-suite-20260916`. Sources are never overwritten. Full-pass
previews are mirrored to the Windows `CEC-Board-Reviews` directory. No candidate
is automatically promoted and no release gate is relaxed.

The archived PCIe2 control's PCB hash, **complete probe reports**, complete
`board_regression` and `generalization` result are identical to the preceding
local-copper-proof control. Its existing broader release failures are unchanged;
this is regression parity, not a new fab approval.
Receipt: `build/owner-fairness-control-20260916.json`.

### Same-population selection experiment

`build/owner-menu-ab-20260916.json` reconstructs one actual native proposal
population and switches only the owner allocator: 1,942 generated proposals,
269 direct-physical proposals, 16 selected trials and an eight-trial direct
reserve on both sides. The old allocator samples four causal owners and zero
Kelvin-range closure proposals. The new allocator samples ten causal owners and
nine Kelvin-range closure proposals. This establishes better search coverage,
not accepted board improvement; it does not depend on the larger wall budget.
All source/hierarchy hashes remain unchanged.

### Six-board outcome

The concurrent pass finished at 2026-09-16T08:22:29Z. All six source and engine
signatures match their starting values. No candidate is promoted. The canonical
continuation inputs remain `build/route-finish-next-inputs-20260916.json`.

| Board | Elapsed seconds | Accepted outcome |
| --- | ---: | --- |
| PCIe2 | 1008.129 | Detailed routing and signoff ran; still 0 DRC errors / 9 opens. |
| PCIe3 | 773.058 | Provisional critical failures 11 -> 10 rejected after power-authority rebuild; restored original 11. |
| Hub | 385.072 | Two small craft moves, but the same four local-cell blockers; no stage gain. |
| 12VHPWR | 813.386 | Same single USB-pair refusal; original placement and protected buses retained. |
| EPS | 68.594 | Fixed terminal pad-copper conflicts; partial placement only. |
| ATX24 | 248.576 | Fixed terminal pad-copper conflicts; partial placement only. |

Independent receipt `build/owner-fairness-qualified-comparison-20260916.json`
verifies source/hierarchy identity, the protected control and PCIe2's exact
journal-selected artifact. PCIe2's new candidate has 749 tracks, 387 vias and
1,656.9508 mm of trace versus 747 / 386 / 1,654.3125 mm for the incumbent.
Placement poses, protected prefix, qualified pairs and local-cell checks pass,
but connectivity does not improve. Keep the incumbent, not the extra one via
and 2.6383 mm of copper. This full pass has **zero accepted closure gains**.

The newly sampled PCIe3 Kelvin proposals expose genuine coupled refusals:
one improves Kelvin range 9 -> 8 but conflicts with local decoupling/power-pour
territory; another improves range while introducing a sense-terminal demand
crossing. Those are not grounds for increasing limits or accepting the move.
The Hub's remaining blockers are three U7 ground returns and U3's isolated
0.72 mm supply tangent against its existing 0.25 mm limit. The 12VHPWR C7/U1.3
cell remains an explicit route-completion deferral, not a claimed resolved cell.

### Reproduced PCIe3 post-authority rejection

The retained accepted candidate has SHA256
`52c46b345034021c335698faa70a7480a1728d5ca40ea839ffec5d6c627bd50a`.
The live transaction reports physical admission before power rebuild, followed
by a refused U3.5[+3V3] bounded ground-return search after rebuild. Pad,
courtyard, constraint and power-authority checks otherwise pass. The generic
transaction restores the original artifact family and excludes the move.

The exact refusal is reproduced in
`build/owner-power-boundary-forensic-v2-20260916/report.json`. Before/after PCB
hashes are identical: the changed dependency is the rebuilt frozen power
reservation state consumed by physical admission, not an unexplained board edit.
The source is unchanged and the diagnostic is not promoted. Both artifact
families, isolated measurements and the compiled power state are retained.

The v1 diagnostic did **not** reproduce this because it called the isolated
worker directly without rebinding the caller's `pourfirst_state` from the result.
V2 uses the production coordinator wrapper and reproduces the live fail stack.
Do not cite v1 as evidence that the live refusal was false. The precise
reservation/ground-path obstruction still needs a geometric witness before
changing how complete owned cells are reserved or repaired.

### Review and next bounded work

All six full-pass records and top/bottom body-free previews were published to
the local dashboard. All six top views and PCIe2's bottom view were inspected.
The gallery is mirrored at
`C:/Users/Admin/Documents/CEC-Board-Reviews/owner-fairness-suite-20260916/all-boards.png`.
EPS/ATX are explicitly partial-placement previews, not routed or qualified
outputs. No preview represents fab signoff. The dashboard responds from Windows.

Next: extract the exact reservation/ground-return obstruction, then implement
complete-cell placement/power dependency handling with synthetic and cross-board
regressions. Kelvin moves must respect both endpoint geometry and terminal
ordering. Also audit route-ensemble incumbent inclusion: the current pass's
selected newly routed candidate is slightly worse than the qualified incumbent.
Do not call this a proven selection defect until its full ranking is compared.
Do not rerun this unchanged exhausted cohort or relocate locked buses. Keep the
mechanical holds below until both mating halves pass a complete fit check.

## Concurrent full-row mechanical screen

The earlier successful +/-8 mm two-terminal transverse test was not a whole-row
or paired-board fit proof. A disposable full-row screen now applies alternating
8 mm transverse patterns in both signs to all declared main-board ports and
their daughterboard lands, preserving lateral pitch, all other poses and copper.
No source, mate or qualification contract is modified.

`build/full-row-transverse-screen-v4-20260916/report.json` has twenty native
screens (two products, main/mate, baseline/four signed patterns). No pattern passes
the whole paired screen: EPS retains main-board conflicts and introduces mate
pad, courtyard and drill conflicts; ATX clears the main's local pad-pair screen
but introduces mate conflicts. The canonical unadmitted ATX staging input also
lacks a closed outline, explicitly preventing a full-fit claim. The original
v1 harness stopped at that condition; v2 reports it without assuming an outline.
V3 extended the signed domain, but showed why native pre-fill DRC alone is
insufficient: some entire daughterboard lands can be off-board without a native
edge violation. V4 adds the explicit necessary pad-envelope containment test;
the positive-Y variants fail it. This is not a new production-gate discovery:
the canonical pipeline already has a separate pads-in-bounds check. Do not use
the earlier partial harness results as fit evidence or infer an assembly flip.

These are nominal relative-position counterfactuals, not a qualified absolute
main/daughterboard mating transform, screw-axis depth, tolerance stack, or key.
They must not be used to admit an interface ECO, shrink lands, grow the edge
envelope, move only one mating half, or start routing a mechanically invalid row.
