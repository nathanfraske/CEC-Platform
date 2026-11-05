# Junction continuation and route-to-placement feedback

## Outcome

**The current BETA 12VHPWR is not closed or route-ready.** This slice repairs
reusable search and feedback mechanisms, but the two bounded placement replays
accepted no candidate. No schematic, source placement, power bus, board outline
or mounting land was changed. An unchanged board image is not presented as a
new candidate.

Authority remains
`build/12vhpwr-pair-search-20260909/checkpoint/board.kicad_pcb`, SHA-256
`3a0deb439290e8b7646b1b736e2947d5c1a711d0b3e4f17b7919c0c5b3da0e28`.
Native score: **4 DRC / 228 opens / 415 tracks / 12 vias / 837.8186 mm**.
All 12 hierarchical source files and four authority controls match the prior
closeout. Each rejected replay is byte-identical to the source and retains the
exact 199-primitive protected-power prefix.

Evidence: `build/route-continuation-closeout-20260910.json`.

## Implemented generic changes

### Compare local junctions by their continuation cost

The multidrop solver formerly stopped at the first locally valid junction.
It now ranks the feasible candidates from its cheap search phase by the worse
member's paid copper plus remaining endpoint reach, then the sum and local
distance. A short positive-member path cannot conceal a long negative-member
escape. Expensive local detours remain a fallback when the direct menu has no
valid star.

This is a **ranking heuristic**, not a proof that a global route exists or an
admissible bound for pruning. Final graph geometry, coupling, route quality and
whole-transaction detour checks remain unchanged.

### Fit virtual runways to the actual edge

Fixed millimetre launch lengths could extend a junction portal past a nearby
peer and force the following trunk to turn back. Mitered junctions now bound
their virtual throat/runway reach to a configurable fraction of projected
peer distance (default 0.45; permitted range greater than zero through 0.5).
This reserves the peer side of the corridor. It does not shrink trace widths,
pair gaps or manufacturing clearances. Exact checks still reject a cell too
short to work.

The native CAN_INT replay's worse-member detour fell from **4.267910x to about
3.98x**, still above the unchanged 2x limit. No resulting copper was retained.

### Cache only immutable foreign geometry

Local candidate screens share native foreign-copper and blocker indexes while
only the exempt pair nets change. The shared snapshot stops at the end of
prefiltering. Subsequent star emission/reselection gets a fresh snapshot,
because trunk routing can add ground-return vias that are foreign obstacles.
Opposite-member copper remains a per-call snapshot throughout.

### Reopen source-owned bypass groups after exact routing fails

The existing joint two-link packing solver previously ran only when a source-
owned bypass exceeded its locality limit. Passing that radius does not prove
that both electrical ends have usable escapes. Exact pair-refusal endpoint
identities now reactivate the same pin-relative joint solver for the affected
group, even when the locality checker passes.

Ownership still comes from populated, unambiguous live source topology. No
group is inferred from net spelling, reference names or coordinates. Source
errors, unrelated endpoints, fixed components and unsupported geometry are not
waived. The frozen-copper prefilter, macro legalization and complete downstream
admission remain in the path.

### Reconsider inline stations that pass coarse launch checks

The same gap existed for a single inline protection/filter station: it could
pass excursion and short-launch checks yet have incompatible exact endpoint
escape orientations. Matching exact pair refusals now reactivate the existing
contact-site/orthogonal-bank placement solver using the two measured banks.
Reports distinguish `flow_through_routing_refusal` from a failed excursion;
passing coarse evidence is not falsified to trigger a repair.

Incomplete bank evidence, mismatched pair identities and multi-station chains
do not trigger independent reseating. Fixed/back-side restrictions remain.
The early "no moves" exit now occurs after these feedback families can run.

## Measured replays

Each production replay used the same immutable input, one round, 12 selected
proposals, a 90-second pair budget and at most two full finalists. Power
replanning stayed disabled.

| Metric | Previous frozen-copper slice | Joint-link feedback | Inline + joint-link feedback |
| --- | ---: | ---: | ---: |
| Selected proposals | 12 | 12 | 12 |
| Reached exact routing | 9 | 9 | 11 |
| Materialization failures | 0 | 0 | 0 |
| Improved critical-route key | 0 | 0 | 0 |
| Accepted candidates | 0 | 0 | 0 |
| Wall time | 368.27 s | 298.73 s | 316.72 s |

The last replay generated 32 source-owned link-group proposals and 14 inline
proposals. Six inline placements and two joint-link placements reached exact
routing, alongside three existing move-family candidates. All still refused
three critical pairs. Remaining-edge diagnostics were four or six; none beat
the incumbent. One selected candidate failed physical legalization. No full
finalist was evaluated and no board-level connectivity gain was achieved.

These are single bounded run timings, not controlled performance benchmarks.
The latest run is about 14% shorter than the prior frozen-copper replay while
testing more exact candidates, but **runtime is not routing closure**.

Reports:

- `build/frozen-prefix-20260910/route-feedback.json`
- `build/frozen-prefix-20260910/flow-feedback.json`
- `build/route-continuation-final-can-20260910/result.json`

Separate diagnostic-only probes widened the junction domain and tried compact
virtual seats. Neither produced an accepted route. Those menu expansions were
not integrated into the production engine.

## What the longer USB solve established

A separate native USB replay raised the pair budget to 240 seconds, without
changing any admission rule. Its first flow-through leg completed the bounded
search and refused after **71.87 seconds**, rather than simply timing out.
That is stronger failure evidence, not a globally complete impossibility proof.

On the inner-layer transition search:

- Positive lane order: zero accepted connector portals, one accepted inline
  portal.
- Negative lane order: four accepted connector portals, zero accepted inline
  portals.
- All four reported endpoint screens completed without exhausting their hard
  deadline. Consequently no same-order portal pair reached middle routing.
- The other exterior reused the completed local screens; the failed local
  matched through-via fields cannot be fixed just by changing the middle layer.

The source-pad via-in-pad fallback also remained unqualified; its eligibility
was not weakened. Exact refusals name connector pad/hole clearance, nearby
passives, signal-via fields and return-via availability. Merely granting more
runtime is not the demonstrated solution.

Evidence: `build/route-continuation-usb-20260910/result.json` and the compact
transition-screen comparison in the closeout report.

## Verification and limits

- Final disjoint suite: **758 tests passed, 13 skipped, two subtests passed**.
  Log: `build/route-continuation-complete-tests-20260910.log`.
- The tightened cache-scope assertion was rerun with all 100 precision-flow
  tests and two subtests, passing. This overlaps the above count and is not
  added to it. Log: `build/route-continuation-cache-final-tests-20260910.log`.
- Synthetic tests cover translated/rotated/scaled short junctions, unchanged
  lane spacing and octilinear runways, invalid reach policy, member-balanced
  ranking, production selection of a later feasible star, cache scope, exact-
  refusal reactivation and refusal to invent missing topology.
- The immutable PCIe two-port control remains **0 DRC / 0 opens**, byte-identical,
  with the same measured score and eight pre-existing broader release blockers.
  Report: `build/route-continuation-pcie-regression-20260910.json`.
- Native post-change CAN replay and read-only closeout confirm the same
  rejection boundaries and untouched authority. Syntax and whitespace checks
  pass.

## Next closure work

The plateau is now established beyond the previous coarse locality gates.
Next work should construct joint endpoint escape cells with compatible lane
orders and actual via/return fields, and propagate empty same-order domains
into placement rather than aggregating both signs as generic available space.
For CAN, the current candidate generator still finds only one usable local
internal star and no outer-bus star; both external routing and the two-ended
bypass footprint geometry need to participate in that joint feasibility test.

Do not relax coupling, detour, clearance, via qualification or the frozen-power
contract to force a pass. Do not label this board fab-ready or start another
identical wave expecting a different result.
