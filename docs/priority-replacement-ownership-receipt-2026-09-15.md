# Proof-bound priority-copper ownership handoff

## Failure and scope

The 07:33Z cohort retained no new board. Its 12VHPWR worker accepted one
strictly improved placement with a reconstructed, qualified CAN_INT pair, but
the outer placement checkpoint still required the old pair's exact geometry.
The old contract missed 18 H / 14 L primitives. This was a stale ownership
contract, not an allowance to alter power copper or waive pair qualification.

The generic repair carries a bounded, checksummed transition record with the
accepted board. It binds original/target geometry contracts, the full typed
qualified signal-pair closure, preserved power/other-pair/return copper, and
source/accepted artifact hashes. Issuance requires the existing native rebuild,
physical, authority, retained-prefix and pair acceptance proofs, then rechecks
the actual candidate's retained copper and pair qualification.

The original owner remains immutable. On an exact-prefix mismatch, the consumer
can resolve only a source-reachable recorded target whose exact scoped copper
matches the current board. The existing independent final pair-physics check
still runs. Missing, stale, malformed, foreign, partial-pair or changed-power
records do not bypass the guard. Geometry matching is scoped rather than a
whole-file equality test, so valid later mechanical edits do not break it.

## Production integration

- `cec_priority_replacement_receipt.py`: typed issuance, validation, bounded
  history (16 maximum), transactional staging and source-reachable resolution.
- `cec_full_pipeline.py`: shared priority-route/power-terminal producer issues
  the record only inside the measured strict-improvement selection branch,
  before capturing its board payload. Snapshot/restore and source signatures
  include the exact `.priority-replacements.json` sidecar.
- `cec_synth_pipeline.py`: original exact-prefix check remains first; only a
  verified replacement can resolve its mismatch, followed by pair physics.
- `cec_fr.py`: normal board copying includes the record and removes only the
  destination's stale record when the new source has none.
- `cec_route_evidence.py`: record changes invalidate cached measurement identity.

No board name, reference designator, coordinate, relaxed clearance or changed
power budget is encoded in the implementation. Explicit original ground-return
ownership remains unchanged; this receipt does not claim all new supporting
returns as original ownership. History exhaustion fails closed, not truncated.

## Verified evidence

- Broad unique-file test selection: **1,132 passed, 38 subtests passed**, 78.42 s
  (`build/priority-receipt-broad-tests-20260915.log`). Dedicated new tests cover
  proof obligations, malformed/stale ownership, final qualification, atomic
  copy/rollback, history reachability/caps, source signatures and cache identity.
- Native retained-case replay:
  `build/priority-receipt-native-replay-20260915-final/report.json`.
  It reproduces the old consumer failure, then passes the actual consumer with
  actual independent pair physics and **unchanged accepted PCB bytes**. A 1 µm
  protected-power trace change is still rejected; rollback restores admission.
- All six hash-bound current input families remain unchanged. Their normal
  native ownership checks pass (the three boards without owned prefixes are
  explicitly non-applicable, not new route qualifications). Retained diagnostic
  artifacts and the shared engine signature remained unchanged during replay.
- Historical PCIe2 control: `build/priority-receipt-control-20260915.json` equals
  `build/qualified-topology-control-20260915-final.json` in board SHA, full board
  regression and all probes. Archived 0 DRC / 0 opens is preserved. Its existing
  broader strict-release failures remain; unchanged does not mean current fab
  signoff.

## Canonical validation boundary

Retained replay is not a final board admission. The accepted intermediate still
has two priority-route refusals. The next canonical run must demonstrate the
complete producer, worker payload, copying, mechanical finishing and checkpoint
chain; record any new blocker rather than assuming closure.

Run only affected canonical work. Unchanged Hub 1/6 CAN-tree construction and
PCIe3 reserved-current-territory failures need separate root-cause work, not an
identical expensive retry. EPS/ATX remain held for coupled mating qualification;
the protected PCIe2 incumbent must not be replaced by an older board.
