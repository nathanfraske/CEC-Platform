# Preserve complete local routes during rigid support-cell moves

## Implemented boundary

The existing certificate relocation worker already moves a bounded component
group and reconnects its incident branches in an atomic candidate. Its internal
copper test, however, recognized only a **single segment directly between two
pad centres**. A normal bent three-segment route was torn at both ends; its
middle stayed behind. That makes an otherwise rigid cell recreate its own
existing wiring around stale boundary points.

`cec_local_copper_cell` now finds short degree-two, same-layer chains between
exact cell terminals. It uses net/layer/native coordinates and topology, not
board IDs, references or hand-picked seats. Item/length bounds are proposal
budgets (12 items / 8 mm by default), not claims of physical impossibility.
The certificate worker carries the complete accepted chain with the group.

Native contact checks exclude foreign pads, mid-segment tees, collinear
overlaps, vias, zones and separately grouped copper. Locked items require the
existing explicit generated-item authority; protected power nets remain fixed.
Coincident distinct terminals are ambiguous. Arcs and multi-layer chains are
not newly owned by this slice. An exact before/after track/arc/via inventory
also refuses any undeclared copper change **before saving the trial**. External
incident branches still have explicit anchors and must be reconnected by the
existing transaction; whole-board acceptance has not been weakened.

This is a local motion primitive, **not** the complete proposed route-owned
placement adapter, and not manufacturing qualification.

## Validation and actual applicability

- `build/local-copper-cell-final-tests-20260916.log`: **171 tests pass** in
  2.91 s. This includes translated/renamed native cells at 0/90/180 degrees,
  native saved-board readback, external anchor retention, unrelated same-net
  copper preservation, lock/group/layer/contact exclusions and byte-preserving
  refusal. The first test pass exposed only an unstable path orientation in
  the pure graph report; reports now retain the canonical first traversal.
- `build/local-copper-cell-suite-20260916/report.json`: concurrent native
  discovery on all four eligible current families plus both interface holds.
  All six canonical sources/hierarchies and the frozen engine are unchanged.
  Historical PCIe2 board hash, complete regression and probes match exactly.
- **No native current-board group move was applicable without more provenance.**
  PCIe2 has 1,111 locked objects among 1,133; Hub has 157/157; 12VHPWR has
  506/506; PCIe3 has no routed objects. No generated-lock authority was invented
  or granted. Thus this cross-board replay proves non-regression/conservative
  refusal, not a new board layout or completed routing wave. The positive
  motion cases above are native synthetic fixtures.
- Core generalization audit passes; broader legacy debt remains present and
  `full_pipeline_generic=false`, `release_ok=false`.

The next route-owned step needs a verifiable generated-copper lineage, not
blanket unlock and not a fabricated empty authored baseline. Then the bounded
group proposals can enter a fully reconnected, independently scored transaction.
Do not replay exhausted single-obstacle PCIe2 moves in the meantime.

## Concurrent safe placement continuation

**Completed without improvement.** Read
[generated-copper lineage](generated-copper-lineage-2026-09-16.md) for the final
265.373-s PCIe3 and 291.264-s Hub results. New receipt totals are 48/77;
canonical inputs remain unchanged. The following describes the completed run.

`tmp/safe_frontier_continuation_20260916.py` continues **only Hub and PCIe3** in
`build/safe-frontier-continuation-20260916/`, using the canonical frozen-priority
input manifest. Their matching byte-bound ordering receipts start at 45 and
32 recorded poses, respectively. No first-batch reset is permitted. PCIe2/VHP
retain the routed-copper guard; EPS/ATX retain their coupled-interface holds.
These are bounded placement transactions, not full suite routing waves.

While the cohort is running, do not edit shared engine files. Inspect its
`report.json` and independently verify any changed saved PCB before advancing
inputs or publishing a new review. The other four boards remain explicitly
held, not secretly running and not silently counted as completed.
