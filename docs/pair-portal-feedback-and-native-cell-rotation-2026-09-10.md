# Pair portal feedback and native cell rotation

## Result and board authority

**The current BETA 12VHPWR is still not route-ready.** This slice does not
promote a placement or routed board. Its input and rejected-trial output are
byte-identical:

- `build/12vhpwr-pair-search-20260909/checkpoint/board.kicad_pcb`
- SHA-256 `3a0deb439290e8b7646b1b736e2947d5c1a711d0b3e4f17b7919c0c5b3da0e28`
- Native result: 4 DRC, 228 opens, 415 tracks, 12 vias, 837.8186 mm.
- All 12 hierarchical schematic files and four authority controls were
  rehashed against the prior closeout and remain unchanged.
- The unchanged source retains the previous 199-primitive protected-power
  proof and grounded-mount geometry. No power bus or mounting land was moved.

Evidence: `build/route-ready-repair-20260910/closeout.json` and `repair.json`.
An unchanged placement image is deliberately not presented as a new candidate.

## Implemented reusable changes

### Exhausted local escape feedback

`cec_portal_feedback.py` extracts exact source-portal identities from exhausted
shared-middle searches which made only local progress. Identity includes both
electrical lane positions and the launch direction; a common centre alone is
not sufficient. Invalid geometry, incomplete diagnostics, time/state limits
and searches which made substantial progress cannot exclude a portal.

The production `_route_coupled_via_portals` wrapper can refill its escape beam
twice after these witnesses. Exclusions are local to this transaction, and all
attempts share the original absolute deadline. It stops on success, deadline,
the refill limit, a prequalified start, or no new witness. Successful original
routes return unchanged; the underlying exact copper, return-path, coupling,
geometry and rollback checks still own admission. The full prior-beam evidence
is retained under `portal_refill`; this is not a permanent geometric ban or a
proof that the entire board is impossible.

The new module is included in the reusable-engine identity audit. Tests cover
rotated geometry, polarity, malformed coordinates, timeout/state-limit refusal,
bounded distinct and repeated witnesses, shared cache/deadline behaviour, and
transaction-local exclusions.

### Native-consistent rigid cell rotations

The station-rotation proposal used a counterclockwise centre transform while
adding a positive KiCad angle to each footprint. In KiCad's y-down coordinates,
these operations rotate in opposite directions. The existing 180-degree test
could not expose this: both signs produce the same half-turn.

Both station centres and lane-axis ranking now use `cec_pcb._rot`, matching the
footprint/pad convention. A synthetic cell with an off-centre pad and an owned
follower is compared against native `FOOTPRINT.Rotate` at 90/180/270 degrees.
The new test failed by **2 mm** before the fix and passes after it. No board,
reference designator or placement-coordinate exception was introduced.

## Native replay results

The standalone USB replay used the existing 90-second pair budget (about
45 seconds for the first flow leg). It excluded two exhausted start portals and
entered one refill, but that refill exhausted its remaining search time. The
45.11-second transaction still refused and retained no route. This is evidence
that feedback executes, **not** a connectivity or runtime improvement.

The production placement repair then ran one bounded round: 12 selected
proposals, up to two full finalists, four exact-probe workers, and no power
replanning. It completed in **512.72 seconds**:

| Result | Count |
| --- | ---: |
| Generated proposals | 933 |
| Selected / coarse-legal proposals | 12 / 12 |
| Rejected while rebuilding protected power | 8 |
| Reached exact critical-route probes | 4 |
| Improved the critical-route key | 0 |
| Accepted placements / retained connections gained | 0 / 0 |

The four measured alternatives still refused all three priority pairs. Two
kept four remaining critical edges and two worsened this to six. Neither was
accepted. The native quarter-turn proposals were generated, but their
materialized variants failed the protected-power boundary, so the synthetic
rotation correction is not a demonstrated board-level closure improvement.

## Newly established blocker: preservation after regeneration

The materialization path is currently inconsistent with frozen-prefix intent:

1. `_materialize_rehydrated_board` invokes a live-hierarchy synchronization with
   `--rip-all-copper` for a routed seed.
2. It reapplies footprint poses and regenerates blueprint/force copper.
3. `_admit_materialized_power_prefix` checks whether every previously protected
   primitive survived this regeneration.

The check correctly rejects changes, but regeneration can reshape a priority
trunk around an ordinary placement proposal before this check runs. Six trials
lost 23 expected primitives across `/FAN_12V` and `/SENSEP6_LO`; two lost one
`/FAN_12V` primitive. These are trial artifacts, not modifications to the
authoritative board. **The safeguard remains enabled.**

This also explains measured cost: trial materialization consumed 288.47 seconds,
whereas the four parallel exact probes took 72.19 seconds wall time. Increasing
route seeds would not address eight failures occurring before routing.

### Next implementation boundary, not completed here

Separate frozen-prefix placement ECOs from destructive topology replacement:
carry the exact admitted current copper through materialization, regenerate
only mutable/local copper, and treat fixed-copper conflicts as placement
rejections. Source hierarchy changes must still invalidate stale electrical
authority; do not simply disable synchronization, restore copper over a new
pad short, or weaken the prefix check. Test mixed protected/mutable nets,
changed pad assignments, same-net extensions, and layer-specific collisions
before replaying these rejected proposals.

There is a second measured search-cost opportunity: beam refills currently
repeat earlier rejected local probes. A transaction-scoped cache of completed
negative probes could reduce that work, but must never memoize incomplete
deadline failures or replay a successful report without recreating its copper.
That optimization is **not implemented** in this slice.

## Validation and control regression

- `build/portal-rotation-final-tests-20260910.log`: 408 passed, 13 skipped,
  two subtests passed (91.78 seconds).
- `build/portal-rotation-contract-tests-20260910.log`: 138 passed (2.89 seconds).
  These are separate test files: 546 tests plus two subtests in total.
- `build/quarter-turn-red-20260910.log`: retained before-fix native failure.
- `build/portal-rotation-pcie-regression-20260910.json`: PCIe two-port control
  hash `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`
  remains 0 DRC / 0 opens, 615 tracks, 226 vias and 1242.073 mm. Its score and
  eight pre-existing broader release blockers match the preceding regression.
  This read-only replay is not a new from-scratch routing run or unconditional
  fabrication approval.
- Python compilation and changed tracked-file whitespace checks pass.

The bounded batch is complete; no unattended wave or background routing task
was left running by this slice.
