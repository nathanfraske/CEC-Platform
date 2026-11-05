# Owned signal-anchor replacement handoff — 2026-09-15

## Native cause, not a component-specific nudge

The completed refill cohort increased probe coverage without changing either
board. On 12VHPWR, the frozen-copper screen rejected **248 of 727** generated
proposals before the bounded placement neighborhood was selected. Rejection
rows for the CAN cell said only `frozen_anchor_moved`. The downstream pair
search repeatedly reported blockage from the already-owned internal CAN pair
and the protected fan-power conductor. Moving an attached component genuinely
requires rebuilding its route; the defect was discarding all such proposals
instead of making the existing atomic dependency-replacement mechanism pay
that obligation.

The old mechanism supported typed foreign-pad collisions during power repair,
but neither complete anchor-attachment provenance nor the ordinary placement
handoff. A reference name alone cannot establish whether an anchor belongs
to replaceable signal copper or nonreplaceable power copper.

## Shared repair and boundaries

- Native frozen-copper evidence now records **all attached preserved
  conductors on all relevant pads**, with pad/net/UUID identity and an explicit
  completeness marker. The normal anchor screen still refuses movement.
- The dependency planner can offer replacement only for a complete, qualified
  signal-pair closure. Incomplete/legacy witnesses, unknown copper, power
  attachments and closures exceeding the existing pair budget remain blocked.
- Before an offer consumes a limited trial slot, a cached native context
  checks the proposed destination against everything that will remain: power,
  other pairs and individually retained ground vias. This screen removes
  neither source geometry nor physical admission gates.
- The ordinary placement producer exports bounded screened offers. They share
  the existing two-candidate handoff fairly with stale-power proposals rather
  than silently adding an unbounded queue. Materialization must reproduce
  the live dependency; old offer metadata cannot authorize a move by itself.
- Existing private-board transactions must rebuild and independently qualify
  the entire displaced pair, preserve retained copper and placement, pass
  post-power physical checks and improve the complete priority key before
  promotion. No currents, dimensions, pinouts or clearances changed.

There are no new board, reference-designator or coordinate selectors in this
production logic. The broader pipeline's previously documented legacy
genericity findings are not claimed resolved by this slice.

## Cross-board native audit

`build/owned-anchor-final-audit-20260915/audit.json` checked the six explicit
current input boards and their hierarchy hashes, without modifying them:

| Board | Native anchors | Potential signal replacements | Power anchors kept fixed |
| --- | ---: | ---: | ---: |
| 12VHPWR | 25 | 4 | 21 |
| Hub | 8 | 8 | 0 |
| PCIe2 continuation | 11 | 4 | 5 |
| PCIe3 | 0 | 0 | 0 |
| EPS | 0 | 0 | 0 |
| ATX | 0 | 0 | 0 |

These are ownership classifications, **not admitted moves**. Two additional
PCIe2 anchors lack eligible replacement authority and remain blocked. All 26
power anchors stayed ineligible. Of 32 previously recorded 12VHPWR anchor
proposals, 30 also failed the retained-copper screen, leaving two offers.
Source and engine hashes remained unchanged. Zero anchors does not establish
routing readiness: EPS/ATX still have their coupled mating blockers.

## Native replay findings

`build/owned-anchor-handoff-replay-20260915/` initially reached the existing
transaction boundary, but both first proposals collided with retained fan
power and ground vias after releasing their pair. Neither was promoted. This
motivated the earlier retained-copper screen, not removal of those obstacles.

`build/owned-anchor-screen-replay-20260915/` tested the two surviving offers.
One rotation failed a placement-craft checker. The other passed initial and
post-power physical checks and reached pair reconstruction. That exposed a
second shared integration defect: reconstruction unconditionally requested a
compiled power-state sidecar even though `_requires_frozen_route_authority`
was false for this native locked-bus policy. It stopped before routing with
`committed power authority cannot bind ... no_sibling_pourfirst_state`.

Reconstruction now selects the declared authority mode consistently with
ordinary recovery. Policies requiring compiled reservations still require
their valid bound sidecar, with no fallback on error. Native locked-bus
policies use native copper obstacles and still owe exact prefix, physical,
connectivity and pair-physics proof. The board's routing recipe is scoped into
either mode. Craft failure payloads also retain all failed checker names and
errors, rather than a fixed six-term allowlist that omitted the rotation's
actual failure.

`build/owned-anchor-context-replay-20260915/` completed under its 600-second
operation limit. The rotation's actual failure is now retained:
`critical_control_follower` measured one parallel-link follower at 5.331709 mm
against its unchanged 5.0-mm limit. The other proposal passed physical checks
and reached native construction. Both CAN_INT tree edges were connected, but
the saved solver verdict rejected whole-pair skew: P 10.817413 mm, N 6.366916 mm,
absolute difference **4.450497 mm versus the unchanged 4.0-mm limit**. The
transaction rolled back; no candidate or route was promoted. These are summed
whole-pair route lengths reported by the existing checker, not a claim about
per-path propagation delay. Source/hierarchy and engine hashes stayed unchanged.
The exact previous report/audit hashes are recorded in `lineage.json`.

## Tests and control

- `build/owned-anchor-screen-integrated-tests-20260915.log`: **243 passed,
  19 subtests**, 67.75 s. This overlaps preceding test sets. It covers native
  all-pad witness completeness, refusal of mixed power ownership, bounded
  handoff fairness, immutable retained-copper checks and context reuse,
  unreproduced offers, reconstruction-before-promotion and existing pipeline,
  budget, probe-scope and genericity regressions.
- `owned-anchor-screen-control-20260915.json` exactly matches the preceding
  protected PCIe2 SHA, board regression and all four probes. Existing broader
  release failures remain; this is non-regression, not fab qualification.
- Final mode/checker additions: `build/owned-anchor-context-integrated-tests-20260915.log`
  **245 passed, 19 subtests**, 66.62 s. The preceding focused set had 42 passed;
  these counts overlap. `owned-anchor-context-control-20260915.json` again
  matches the prior protected SHA, board regression and all four probes.
  `git diff --check` passed. Final six-board native audit reproduced the same
  44 ownership classifications and two retained-copper-clear recorded offers,
  with all source/hierarchy/engine hashes unchanged.

## Canonical cross-board follow-up

`build/owned-anchor-suite-20260915/suite.json` started at
2026-09-15T04:30:03Z, testing Hub and 12VHPWR concurrently. Coordinator PID
3242103 and initial board PIDs 3242106 / 3242107 were verified running. It uses
two workers per board, the original two-candidate handoff, 1200-second priority
operation limits, 1800-second board deadlines and a 16-GiB free-space floor.
Available space was about 70 GiB. Do not edit shared engine files while this
cohort runs or launch a duplicate; inspect current journals and processes.

Both are native-audit-identified owned-anchor families. This pass verifies the
complete producer/transaction connection rather than feeding manual moves.
PCIe2 remains the protected regression control, PCIe3 has no such retained
anchors in its current input, and EPS/ATX still cannot route before their
coupled mating ECO. Immutable body-free pass previews publish to the dashboard
and `C:/Users/Admin/Documents/CEC-Board-Reviews/owned-anchor-suite-20260915/`.
Windows dashboard HTTP returned 200 this continuation.

No new accepted board is claimed. The historical PCIe2 control, latest partial
PCIe2 (0 DRC / 12 opens), current power budgets and EPS/ATX mating limits remain
protected. No unchanged PCIe3 campaign is needed for this anchor slice.

Completion update: the cohort finished at 2026-09-15T04:49:02Z, Hub in
684.687 s and 12VHPWR in 1094.163 s. Neither admitted a new placement; outputs,
sources, hierarchies and engine signatures remained unchanged. Both funded
Hub post-physical proposals reached 1/6 CAN edges before exhausting the pair
search budget. The VHP reconstruction remained rejected. The final immutable
gallery is `all-boards-7e0e740d27fd4953.png` in the review directory above.
See [the next cumulative escape slice](cumulative-pair-escape-skew-2026-09-15.md)
for the current follow-up; this owned-anchor cohort is no longer live.
