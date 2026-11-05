# Supply ownership, pin-local macro and ground-access slices

2026-09-07. Continued the generic placement work on the verified current
12VHPWR hierarchy. **Placement is not fully admitted and residual routing has
not started.** The electrical and owned-power-copper blockers below remain
hard failures, not warnings waived for a visually improved board.

## Implemented

### 1. Shared distinct-capacitor assignment

The native-board matcher used an augmenting path to move an existing capacitor
owner to another capacitor. After that recursive reassignment succeeded, it
deleted the old owner's result entry, which was now its **new** valid entry.
The capacitor-owner map and reported assigned-requirement map diverged. A real
assignment could disappear and later be reported as a missing bypass.

`cec_device_bypass.distinct_assignment` now provides a shared, iterative,
maximum-cardinality matcher to both source placement and native-board checks.
It retains existing choices when an unused compatible part is available, and
uses alternating paths only when needed. This avoids unnecessary common-rail
swaps as well as recursion-depth dependence on larger boards. Compatibility,
explicit owner declarations, reference affinity and physical distance limits
remain the respective callers' authority; no capacitor is invented or used
twice. DNP/excluded source capacitors no longer satisfy fitted bypass roles.

Renamed synthetic tests cover displaced owners, a 1,501-requirement chain,
true component shortages, and the actual native-board assignment adapter.
The first experimental replay exposed gratuitous owner swaps; these were
corrected before the verified replay by preferring unused compatible parts.

### 2. Supply inventory before route effort

Source assignment can now emit a structured inventory: requirements, assigned
count, missing roles, compatible/eligible references and competing owners. It
distinguishes absent eligible components from one-to-one contention, without
pretending that source-only matching proves physical proximity.

The inventory is retained in canonical placement-review/replacement records.
Exact pair probes are deferred on a failed inventory. Production fresh
placement additionally raises `PipelineBlocked` **before geometric repair
loops**, preserving a source-repair certificate and placement journal in the
stage failure evidence. Review-only generation still produces an inspectable
failed candidate. Legacy/read-back candidates without the new inventory
retain their existing independent source and final craft gates; this is not a
claim that every older entry path has been replaced by this source gate.

### 3. Pin-local bypass macro reservation

The MCU macro's old slenderness/antenna heuristic explicitly moved all support
parts onto the non-antenna side and accepted long bypass connections. Reserving
that macro then locked the MCU into a space in which a later pin-local placer
could not repair its bypass.

The generic `_pin_local_macro_bypasses` refinement now searches the real
package's tangent sides in four rotations before measuring and reserving the
macro. Supply-pin distance and return-loop distance outrank old row placement.
Other macro members remain obstacles. The search is bounded by the declared
distance limit (with a 5 mm local-search cap), and failure preserves the old
proposal for downstream rejection instead of widening the limit. This helper
has no board, refdes or coordinate special case. The current integration is
the existing MCU macro builder, not yet every possible analog/connector macro.

The resulting whole-row negotiation used 30 trials and a (0, -15) mm group
translation instead of the previous 26 trials/(0, -13) result. Those are solver
outputs, not embedded placement coordinates. The refined MCU bypass passed
the later native local-cell and proximity checks; the tangent search alone is
not treated as a routing proof.

### 4. Ground-return failure certificates

The six sensing bypasses' `local-cell-access` failures were not all supply-link
failures. Their GND-return failures were concatenated strings without the
blocking copper identities in the retained detail.

The complete-cell constructor now preserves both seating orders and both
terminals' ground-return evidence: process eligibility, edge/drill clearance,
pad-center copper admission, blocker net/layer/UUID, dogbone search counts and
an upstream-owned-copper repair classification for locked obstructions. The
existing all-or-nothing copper rollback remains intact.

On the exact retained board the qualified 0.35/0.25 mm POFV portal is blocked
by the **2.5 mm locked /SENSEP*_LO B.Cu trunks** below the sensing cells.
For example, U10.7 and C10.2 both encounter the same /SENSEP1_LO trunk. Moving
the row does not fix this because the power generator regenerates the trunk
through the translated cell's ground window. A through-via cannot pass through
foreign back-layer copper. Blind/microvias, reduced current-trunk widths or
clearance exceptions were not introduced as a workaround.

The new renamed native regression places a locked foreign trunk on B.Cu and
checks four failed terminal/order attempts, exact blocker identity, upstream
repair attribution, JSON serialization and preservation of the original trunk
with no leaked trial copper. This slice improves detection/attribution; it
does **not** claim that the old force-lane generator has been generically
replanned around those ground portals yet.

## Verified current-board results

Compared with the cooperative-packing candidate immediately preceding this
work:

| Measurement | Before | Verified after |
| --- | ---: | ---: |
| Placement residuals, not DRC violations | 5 | 3 |
| MCU bypass supply-pin distance | 13.26 mm, failed | 1.56 mm, passed local-loop check |
| Out-of-outline pads | 0 | 0 |
| Exact courtyard violations | 0 | 0 |
| Complete sensing cells / locked segments | 6 / 444 | 6 / 444 |
| Decoupler craft findings | 12 | 12 |
| Stranded-part findings | 1 (C22) | 1 (C9) |
| Outline | 58 x 80 mm | 58 x 80 mm |

This remains a mixed result. The MCU failure and C22 stranding are gone, but
C9 is now 34.2 mm from its nearest qualifying shared-net neighbor. Smaller
regulator/reference return/proximity findings remain, and C7's excess is now
0.94 mm rather than 0.27 mm. The aggregate craft gate remains false. No
per-reference move or threshold waiver was used to hide these regressions.

The verified single-strategy placement stage took 135.2 s. The earlier
two-strategy stage took 704.181 s, but these are **not comparable speedup
measurements**: the new source gate skipped exact pair effort and only one
strategy was evaluated. The fresh variant still preserves six rigid cells,
the current source intake and the original outline.

The final forensic-only recheck of the retained board repeats 12 decoupler
findings and confirms the same MCU success while adding ground-return
certificates. It does not mutate or substitute the board.

## Source requirements and approval boundary

The current source inventory satisfies 12 of 15 existing bypass roles:

- U2.5 to U2.3: no eligible VIO-to-VCC capacitor.
- U5.7 to GND: no capacitor eligible under the current local-HF policy on
  /VCC_RJ45; C6 is an existing 10 uF ceramic, not an absent supply capacitor.
- U5.1 to GND: the only eligible +5VSB HF capacitor is C4, already owned by
  U2.3. The source also contains larger capacitors with other local roles.

These are failures of the **existing project contract**, not proof that three
new 100 nF parts are required by manufacturer numeric specifications.
[TI TPS2121 section 11](https://www.ti.com/lit/ds/symlink/tps2121.pdf) recommends
near-device low-ESR X5R/X7R ceramic bypassing on both inputs and the output; it
does not state this pipeline's 1 uF local-HF upper bound. That ceiling is a
separate conservative project policy and must not be misattributed to TI.
[NXP AH1014 section 8.9](https://www.nxp.com/docs/en/supporting-information/AH1014.pdf)
does recommend VIO-to-VCC decoupling for TJA1051/3 EMC performance.

Approval to include current hierarchical schematic/BOM repairs was requested
asynchronously. No source parts were added and no electrical selection policy
was relaxed in this slice. Source repair should first review eligibility and
local ownership, then add only justified components with explicit ownership.

## Regression and durable evidence

- Broad final suite: **523 passed, 13 skipped**, 82.28 s. It includes a broader
  selection of existing tests than the previous 467-test run.
- Final production-admission subset: **133 passed**, 46.11 s. These counts
  overlap and must not be added together.
- Final PCIe control replay: identical score and complete constraint-blocker
  list; **0 structural DRC / 0 opens**, 615 tracks, 226 vias, 1242.073 mm. Eight
  pre-existing release-blocker categories remain; no new fab qualification.
- The source-file signature and hashes of the current staging PCB, stale
  12VHPWR candidate, Hub candidate and archived PCIe board are unchanged.
- Generic-core audit passes. Whole-runtime genericity remains false because
  inherited selector/recipe debt has not all been removed.
- No Hub copper changed. No residual routing, thermal solve, dashboard
  publication, fab promotion or unattended run was performed.

Artifacts:

- `build/12vhpwr-pin-local-verified-20260907/02-placement/placement-candidates.json`
- `build/12vhpwr-pin-local-verified-20260907/comparison.json`
- `build/12vhpwr-pin-local-verified-20260907/final-ground-access-evidence.json`
- `build/pin-local-final-pcie-regression-20260907.json`
- `build/supply-placement-final-tests-20260907.log`
- `build/supply-placement-final-admission-tests-20260907.log`
- Exact retained candidate `000/placement.png`, model-free and visibly marked
  placement review / routing blocked; PCB SHA checked again after rendering.

The two placement experiment directories together used about 4.4 MB before
adding the final small comparison/forensic reports and preview.

## Remaining route-admission work

1. Resolve the source eligibility/ownership failures without creating needless
   BOM growth or silently weakening the local-HF project policy.
2. Make the owned high-current copper planner reserve qualified ground-entry
   space before emitting its trunks; preserve current width, connectivity,
   layer rules and exact DRC in its bounded alternatives. Do not move locked
   bypasses independently to escape copper regenerated through their cells.
3. Correct the remaining regulator/reference local loops and shared-rail
   follower retention (the stranded bulk-cap case), with individual craft
   comparisons rather than trusting the residual score.
4. Re-run exact critical-pair proofs after these gates pass. Previous USB/CAN
   failures have not been re-qualified on the new placement; source deferral
   is explicitly *not run*, not pass. Then admit the residual router.
