# Power admission and lossless placement replay — 2026-09-23

## Outcome

Three board-neutral corrections are implemented. The current Hub now has an
exact-admitted **8/8 power-domain composition**, up from the previous production
6/8 result. This is **not signal routing or fabrication approval**: the exact
preview has 0 structural DRC violations, 200 unconnected items, and one remaining
MCU bypass-placement finding. Neither board was enlarged or promoted to release.

The compact ATX progresses past a false terminal-identity refusal, but its
physical power candidate is rejected. That rejection is preserved, not hidden.

## 1. Transactional via-throat qualification

The PSU completion candidate was electrically connected but rejected as
`no_full_width_throat`. The first surface-only forensic was insufficient: the
F.Cu landing really is narrow, but the newly generated through via has a 1.0 mm
B.Cu continuation. The 0.8/0.4 mm via passes the selected process's actual local
POFV test. Its group was empty because `synthesize_lastmile` registered generated
vias only after it had already rejected the endpoint neck.

The generic correction in `cec_fr.py` proves the entire proposed transaction
before changing ownership groups. An explicitly proposed via may pass the live
fabrication/locality check before registration; it must still have an actual
same-net full-width continuation on another layer. All narrow components must
pass before either group is committed. This also prevents partially successful
grouping from surviving a rejected transaction.

The pin escape remains 0.25 mm wide and 1.25 mm long, inside the unchanged 1.5 mm
maximum local allowance. No zone-membership waiver, width reduction, clearance
reduction, or thermal qualification was introduced.

An isolated replay of the original rejected Hub artifact now closes this domain
in the fast pass: three track legs, one via, zero refused attempts, unchanged
old copper, unchanged placements, and a passing current-width checker.

Evidence: `build/hub-atx-terminal-access-20260923/zone-throat-fixed/route.json`.
The earlier `zone-throat-fast/observations.json` records the unregistered via and
its actual other-layer continuation.

## 2. Bounded prospective allocation-order retry

`cec_power_order.solve_prospective_batch` is integrated into the production
pre-freeze over-under path. It permits at most one distinct failed-nets-first
retry, with current priority as a deterministic tie-break. The native board and
existing reservation inputs do not change between alternatives. Only prospective
generated lanes are reconsidered; this does not authorize replacing frozen
power copper.

The alternate must gain at least one solved domain and lose none. Its complete
search state travels with its geometry so reservation masks cannot accidentally
come from the discarded candidate. Refill, current-width, and exact source/sink
admission remain mandatory. Errors propagate; no retry receipt is a release gate.

The fresh production Hub run needed 39.39 seconds, without the earlier diagnostic
monkeypatch. Its initial allocation found 7/8 paths in 1.65 seconds; the single
alternate found 8/8 in 1.57 seconds. Exact compilation then admitted all eight.
Both orders and the gained/lost sets are saved in `allocation_order_search` in
the frozen state. This scheduling policy is registered with the generic-core
audit.

Evidence: `build/hub-atx-terminal-access-20260923/hub-production-final/`:

- `probe.json` — production boundary and unchanged source proof.
- `board.pourfirst-state.json` — exact authority plus bounded order receipt.
- `exact-preview.state.json` — independently compiled, filled review board.
- `physical-recheck.json` — bounds, courtyard, constraints, and remaining craft gate.
- `published.json` — exact artifact SHA and dashboard identity.

## 3. Lossless native-coordinate reconstruction

The ATX first refused before exact copper checking because its local power
terminal hash differed between source and reconstructed placement. Comparing
native terminal tuples found only one-nanometre shifts: C53's Y coordinate and
C62's X coordinate. There was no intended component move.

KiCad's Python `FromMM` uses integer truncation. A native integer converted to
floating-point millimetres can therefore reconstruct as N−1. The shared
rehydrated materializer now rounds to the nearest native unit instead. Exact
terminal hashing remains unchanged; real one-unit edits are still distinct.

The ATX replay now has identical source, skeleton, and contract terminal hashes:
`715ac4f188ea65942b79b8daec292f890ee41927e1740a387f9c9c754f88f37c`.
No changed terminal references remain. Native regression fixtures cover positive
and negative coordinates, rotations, and three successive reconstructions.

Evidence: `atx-production-power/terminal-replay-forensic.json` and
`atx-production-final/terminal-replay-forensic.json` under the same slice root.

## Exact board status

| Candidate | Exact result | Remaining work |
| --- | --- | --- |
| Hub power composition | 8/8 domains; 0 structural DRC; 200 unconnected items | MCU C36/U1.2 complete-loop excess 0.650 mm versus 0.250 mm limit; then signal routing |
| Compact ATX diagnostic | Rejected; 30 structural DRC; 269 unconnected items | Both proposed protected paths remain open after fill; power allocation and local copper cleanup |
| PCIe two-port fab-review control | 0 DRC; 0 unconnected; bytes unchanged | Two pre-existing release findings below, not repaired by this slice |

ATX rejection details: `/SENSE12V_LO` and `/SENSE5VSB_LO` remain open. Its DRC
breakdown is 23 dangling vias, 2 dangling tracks, and 5 `items_not_allowed`.
The planner proposed only two protected nets; the preview's `0/2` label refers
to those checked domains, not to a claim that the complete ATX power problem was
solved. The rejected board is retained with SHA
`598169486eeedb71cf9f8677212f7727e2930f1c80c6bde74795c650cddb145c`.

The Hub's remaining placement failure was remeasured; the local cell is
constructible, but its 3.979 mm supply-plus-return loop is still too far from
the individual tangent optimum. The companion capacitor C11 is already near
its limit (0.244 mm excess). The next placement slice must address the joint
two-capacitor geometry, not repeatedly move only the failing reference or
silently relax the proximity limit.

## Regression and preserved authority

The final combined native/synthetic run passed **520 tests, plus 10 subtests**,
with no skips or failures and two deprecation warnings, in 119.32 seconds.
New tests cover renamed/translated routing scenes, provisional-via rejection
without proper process/locality/width, all-or-nothing rollback, save/reload
recovery, finite order retries, losing-candidate grid isolation, and native
coordinate reconstruction.

`pcie2-regression-final.json` retains every non-regression term, including
connectivity, DRC, fabrication, route craft, differential and Kelvin score gates,
and exact control content. Its overall release remains false for the existing
RS1 pad-2 nonperpendicular inward Kelvin departure and CAN adjacent filled-GND
coverage of 80% versus 95%. These are not new failures and are not waived.

`generalization.json` passes the audited generic core, including the new order
module. The full legacy physical/integration pipeline still has recorded
special-case debt; this is not a declaration that the entire pipeline is generic.

The 84.49 × 72.2 mm Hub and 78 × 95 mm ATX outlines are preserved. The paired
assembly/body/vent screen passes, with all 18 transformed mating contacts aligned.
`pair-validation/paired-progress-validation.json` confirms that neither the
source boards nor the active-pair manifest changed. Incoming samples, hardware
tolerance/load validation, and thermal/bench qualification remain open.

Unchanged protected SHA-256 values:

- Active pair manifest: `dfbeccb8eca4331c53c92c95b77d82dea03d4d8f396effda2860ca1d99882463`.
- Hub placement source: `cbfe6b6f1e105a001356bad4c5e730d527264ed26618965cfd4a5f55380cd1b7`.
- ATX placement source: `83799200c0dae6ddd158d66de1e43d548a34547bd59b8d29539d929ac3d7814b`.
- PCIe control: `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.

## Review artifacts

Both top/bottom views are models-off renders of the actual saved native boards.
They are diagnostic archive entries, not promoted routed winners. Windows-side
HTTP checks found both exact IDs in the dashboard catalog and returned HTTP 200
for their images. Opening the Hub in Codex returned `queued`, so that response
is not treated as proof that the user saw it.

- Hub: `http://localhost:8090/?id=20260923-hub-standard-rev2-power-progress-fa727ef963`
- ATX rejected diagnostic: `http://localhost:8090/?id=20260923-atx-24pin-rev3-power-REJECTED-598169486e`

No unrestricted unattended waves were started, no source board or BOM was
replaced, and no Git commit/push was made. This slice adds code, tests, and bounded
diagnostic artifacts while preserving the pre-existing dirty worktree.
