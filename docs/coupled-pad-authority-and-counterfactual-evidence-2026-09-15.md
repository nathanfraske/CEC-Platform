# Coupled pad authority and truthful counterfactual evidence

## Completed 12VHPWR validation

The canonical `priority-receipt-suite-20260915` run completed at **08:44:09Z**
in 1674.755 seconds. Source PCB, source hierarchy and engine signatures stayed
unchanged. The final placement artifact SHA is
`722d7a6e4e1754e25b755ac9b8625b41f4070f6294384551b2f651038bdb23d6`.
The replacement receipt was carried through the real worker, copy, mechanical
finishing and outer checkpoint chain: zero missing protected items, qualified
pair check true, one reachable ownership transition. The accepted intermediate
is no longer lost to the stale-owner exception.

The placement stage completed but admission remains **blocked**. Pads, courts,
craft and constraints pass; two priority-route refusals remain. This is a
retained placement/ownership improvement, not a routed or fab-qualified board.
The output is journal-verified and differs from the input; its body-free preview
was visually inspected. Dashboard:
`http://localhost:8090/?id=pass-priority-receipt-suite-20260915-12vhpwr-standard-07e5947dd0`.

## Opposite-member pad guard

The retained Hub higher-effort diagnostic constructed all six CAN edges but
added a CAN_L track across a physical CAN_H pad. Existing foreign-copper checks
intentionally exclude both pair nets; the assembled-graph portal validator
only checked pair track crossings. It did not restore the opposite-member pad
obligation. The existing conventional-route pad guard rejects the saved bad
segment, but that guard was absent from these portal-path acceptance checks.

New product-neutral `cec_pair_pad_guard.py` uses exact native pad shapes on the
actual layer, including PTH barrels, with explicit positive/negative net identity.
Own-member pads remain legal contacts. Failed shape evaluation refuses rather
than silently accepting. Bounded geometric witnesses name the member segment
and opposite pad; no reference, coordinate or board rule is encoded.

Integration:

- Prequalified junction portal grids now validate opposite pads before selecting
  a lane orientation.
- Generic via-portal grids perform the same check before emitting a temporary
  assembled graph. A rejected pad collision supplies a direction/location
  witness to the existing bounded retry search, rather than repeating the same
  illegal path or adding an unrestricted route exception.
- The final pair candidate guard rechecks transaction-owned tracks after local
  closure/cleanup. Arcs use their native shape rather than a chord. Parent
  copper and supporting returns retain their existing ownership and checks.
- Final saved-board DRC, pair physics and all route-admission gates are unchanged.

The synthetic native regression reproduces the missing obligation: a portal
grid with just its former geometry checks emits a short. Enabling the new
production validator refuses that candidate before emission. Separate tests
cover PTH/SMD layer membership, legal own-member contacts, loaded-file roundtrip,
transaction scope, consumer wiring and invalid clearance.

## Counterfactual report states

`_corridor_relief_evidence` previously initialized broad removal results to
`None`, skipped them after finding a small cut, and serialized `bool(None)` as
`false`. That made an unperformed test look like proof that no placement could
restore the current corridor. It also conflated a tested ranked subset with the
untested universe of all movable owners.

Reports now include explicit `*_removal_tested` flags. `*_restores_path` is
`null` when untested, and a true boolean only for an executed counterfactual.
The identical ranked/all-owner universe can share its executed result. A
successful proper subset does not claim a larger test was run. No extra native
search or wider move is performed. Positive small/large-cardinality cut witnesses
are unchanged; repository search found no automatic consumers of the old
ambiguous booleans. Five synthetic tests distinguish skipped, failed, larger-
universe successful, subset-only successful and empty-universe cases.

This corrects the earlier PCIe3 interpretation. The retained case has a positive
full-required-width U20 removal witness, while its two Kelvin-range proposals
still obstruct that corridor. `wide_relief_sets` refers to owner cardinality,
not copper width. Next solve those simultaneous cell/current constraints;
do not infer that fixed terminals make all layouts impossible.

## Evidence and limits

- Broad tests: **1,318 passed, 4 skipped, 79 subtests passed**, 104.02 s:
  `build/pair-pad-and-counterfactual-broad-tests-20260915.log`.
- Additional generalization tests: **9 passed**.
- Exact native replay: `build/pair-pad-cross-board-audit-20260915.json`.
  All 275 existing pair track segments across six source boards have no new
  opposite-pad violation. Zero-track pairs are non-applicable, not qualified.
  The 24 CAN_INT segments in the completed VHP output also pass. The rejected
  Hub's 149 segments reproduce exactly the new offending-track witness.
  Source families and files remain unchanged; nothing was promoted.
- Historical PCIe2 control SHA, board regression and every probe exactly match
  the prior receipt: `build/pair-pad-control-20260915.json` versus
  `build/priority-receipt-control-20260915.json`. Existing strict release failures
  remain; this is not a new fab signoff.
- Both new guard and ownership receipt are registered in the anti-overfit core:
  65 modules, zero core violations. The whole runtime still has 380 untriaged
  legacy static findings and `release_ok=false`; do not describe the entire
  pipeline as fully generalized.

**Completed native Hub reconstruction replay**, started 08:54:04Z, former PID 68739:
`build/hub-pad-guard-replay-20260915/report.json`. Same retained input, same 514
protected pour reservations, same 480-s pair budget, 630-s operation allowance
and 660-s hard process limit as the prior effort diagnostic. This run tests
whether in-search rejection/retry constructs a legal replacement, not merely
whether the new checker rejects the old board. It **passed in 124.462 s**:
6/6 tree edges, pair physics, placement, preserved copper and source/engine
guards all pass; comparative DRC 12 -> 12, opens 254 -> 242. No new structural
DRC identities. The CAN prefix is admitted; residual routing/fab is not.
No source board was promoted. The verified diagnostic is published at
`http://localhost:8090/?id=20260915-hub-padguard-6edge-qualified-prefix`.

The next canonical two-board run started 08:57:52Z:
`build/pair-pad-guard-suite-20260915/suite.json` (Hub 69367, VHP 69368).
It uses explicit completed-attempt lineage, preserving VHP's new placement,
and the same parameterized 480-s pair effort for both families. See the latest
main ledger for source hashes, bounds and pending work. Do not edit shared
scripts or launch duplicates while this cohort or its descendants are active.
