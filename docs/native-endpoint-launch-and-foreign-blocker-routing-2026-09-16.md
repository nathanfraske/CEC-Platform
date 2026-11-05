# Native launch attribution and foreign-blocker route identity

## Two demonstrated generic defects

1. The foreign-support repair planner treated any clear certificate ray on any
   copper layer as an available escape. A bare SMD land therefore inherited an
   imaginary inner/back-layer transition. This suppressed an actual foreign
   support obstruction on current PCIe2's soft-start pin.
2. Once that obstruction became eligible, the exact reconnect worker looked
   for the obstructed net on the **moved obstruction's pads**. A foreign-net
   component cannot supply that signal endpoint. One otherwise preflight-clear
   trial stopped at `target_pad_missing_after_move` without searching the
   original signal pair.

Both fixes are in `scripts/cec_certificate_repair.py`, revision
`2026-09-16-native-launch-and-foreign-blocker-pair-v45`. The revision change
invalidates old algorithm-specific search evidence instead of retaining a
false plateau under the new behavior. No board/reference/coordinate selector,
new power-budget assumption, clearance relaxation or layer transition was added.

### Native launch ownership

`_live_endpoint_launch_layers` resolves a unique current SMD pad by reference,
pad number, net and certificate origin (within 1 nm). It starts with that pad's
actual copper layers. Additional layers require existing connected same-net
native copper covering the exact origin. A remote via, foreign track or zone
outline is not a transition. THT/via/unknown endpoints retain conservative
all-layer interpretation; stale/ambiguous data cannot authorize surface-only
inference. Clear rays on genuinely accessible layers still suppress needless
movement. This is proposal attribution, not global no-path proof.

### Original pair survives obstacle relocation

The foreign-blocker planner now transports the certificate's original two
`route_endpoints` in `FootprintRepairTarget`. For an away-from-endpoint move,
the exact reconnect worker binds and routes those original same-net endpoints,
not a fictitious signal pad on the relocated obstacle. Existing support anchors
are restored separately. Ordinary endpoint-support moves keep their existing
behavior. Missing, foreign-net and nonbinary pairs fail the native exact worker.
Whole-board acceptance still governs adoption; no copied certificate alone
authorizes geometry or acceptance.

## Validation

- **250 tests and eight subtests passed**, 17.07 s:
  `build/endpoint-launch-attribution-v45-tests-20260916.log`.
- New native tests cover front/back layers, four quarter-turns and translated
  origins; real via and THT transitions; foreign internal copper and remote
  via controls; stale identity; original-pair transport; actual native signal
  and support reconnection; retained locked anchor; invalid pair rejection.
- Concurrent read-only native replay:
  `build/endpoint-launch-replay-v3-20260916/report.json`.
  PCIe2 uses one exact live pad-pair origin from its retained route-refusal
  evidence. Hub, PCIe3 and 12VHPWR each exercise eight deterministic real
  scalar-net pad-pair geometry samples using unchanged native net-class
  dimensions. Those samples are explicitly **not routing attempts or new
  failures**. No new foreign-blocker target appears on those other three samples.
- EPS and ATX stop at their existing unadmitted interface-ECO guard. This is
  not six successful route runs; four families were applicable to geometry
  replay and two remained held.
- Historical PCIe2 board SHA, complete regression and all probes match.
  All six canonical board and schematic-hierarchy identities are unchanged;
  engine files stayed frozen throughout the native cohort and transaction.
- Generalization audit remains at 23 physical / 380 runtime legacy violations;
  `full_pipeline_generic` and `release_ok` remain false. Passing this slice
  does not qualify the entire legacy pipeline.

Earlier receipts are retained. V1 geometry replay had no samples on the three
placement boards and is **not** evidence for their native launch coverage;
V2/V3 add explicit samples. An initial unit fixture placed a foreign-net via
directly through a pad, and KiCad renetted it on reload. The corrected fixture
uses legal foreign internal copper. Another test invocation named a nonexistent
file and collected no tests. Only the final successful receipts qualify the slice.

## Real transaction outcome: no canonical board gain

`build/endpoint-launch-transaction-v2-20260916/report.json` records the bounded
production relocation trial selected by the newly exposed generic blocker
evidence. The target is current PCIe2 R14 blocking U4's SS signal. This reference
is a **case-study result**, not an engine selector.

Four poses were tried in 13.751 s. Three introduced native preflight DRC faults
against preserved copper and were rejected. The fourth passed preflight and
reached the actual original-pair route search, which returned
`certificate_pair_no_exact_clear_path`. Before the second fix that same pose
instead failed on the nonexistent signal pad. Existing support restoration
still ran independently. No trial was adopted: **0 DRC / 9 opens is unchanged**.
No generated-locked-copper authority was granted in these trials. Power buses
and every canonical source remained unchanged. The first three conflicting
locked tracks also exist in this run's placement baseline; their eligibility
cannot be inferred merely from being locked or from a different run's UUIDs.

There is no new full-pass candidate or preview. Scratch trials must not be
published as routing improvements. Keep
`build/priority-coopt-next-inputs-20260916.json` as the continuation cohort.

## Next bounded work

Do not repeat these four poses or the earlier isolated return-via/cell probes.
Their source identities, exact candidate poses and native decisions are in the
transaction receipt. The newly repaired planner/reconnect plumbing is reusable,
but actual improvement still requires a constructive multi-obstacle/owned-cell
transaction, with producer-bound copper ownership and complete boundary replay,
or a genuinely unvisited placement proposal. Do not expand authority by
unlocking copper wholesale. Continue other eligible families independently;
their existing priority/craft and coupled-interface blockers are unchanged.

The dashboard returned HTTP 200 from Windows. Approximately 65 GiB remains
free; this slice's native evidence/trials use about 25 MiB. The existing
15-minute board-suite review heartbeat remains active. No native worker from
this slice is left running.
