# Exact local-copper proof and dependency-witness screen — 2026-09-16

## Repaired production defect

While examining the evidence needed for complete owned-cell replacement, the
shared local path checker still defaulted to a **60 micrometre snapping grid**.
Only the immediate-ground-return caller explicitly requested native resolution.
Supply-link reuse, shared-ground reuse and the final local-cell audit could
therefore reason from a different graph than that stricter GND caller.

Two synthetic native counterexamples reproduce the defect:

- Separate hairline fragments with a real 10 micrometre gap collapse to the
  same coarse graph node. A short invented connection masks the actual
  20.8 mm detour. Those hairline fragments are test geometry, not proposed
  fabrication dimensions.
- With a 100 micrometre trace and land, a trace endpoint 105 micrometres from
  the land centre leaves a real 5 micrometre copper gap. The coarse pad-hit
  expansion reports a path although native connectivity reports disconnection.
  The result is reproduced after native save/reload. These dimensions describe
  a synthetic negative control, not a newly qualified fabrication rule.

`cec_decoupler_cell._shortest_track_path_mm` now uses the one-nanometre native
coordinate floor for **all** callers. It rejects requests for a coarser or
invalid resolution, so a future caller cannot silently restore the unsafe
shortcut. Zone copper remains excluded and real long detours remain long.
No native clearance, trace/via dimension, locality limit, current rating or
ownership rule changed. The helper still conservatively requires its supported
explicit endpoint graph; failure is not proof that no physical path exists.

## Rejected hot-path expansion

A separate read-only prototype examined richer complete-cell path witnesses:
split straight tracks at actual interior pickups, T-junctions and exact
same-layer intersections, use real plated pads/vias for layer access, reject
NPTH layer shortcuts, retain path UUIDs, and corroborate accepted paths with
native connectivity. It does not use zones or authorize removal of any item.
Arc interiors and nonrepresentable centreline contacts remain conservative
unsupported cases, not guessed geometry.

The prototype is **not wired into the pipeline**. It is retained only as
`tmp/local_copper_path_witness_20260916.py` with regression tests. It was moved
out of the production scripts directory after measurement; do not mistake its
availability for durable cell ownership or replacement authority.

`build/local-copper-path-suite-20260916/report.json` compares 61 actual supply
queries across the four admitted native families. There are **zero local-cell
gains and zero losses**. Only one PCIe2 path changes by two nanometres, without
a verdict change. PCIe2's batch grows from 0.0174 to 0.7291 seconds in this
single diagnostic sample. There is no justification for installing that more
expensive algorithm on every local-cell query or launching another full wave
because of it. It may be useful as an on-demand dependency witness later.

## Validation

**477 tests pass**, seven existing Shapely deprecation warnings, 140.14 seconds:
`build/local-copper-proof-integrated-20260916.log`.
Coverage includes the old false proofs, rejecting coarse override requests,
native front/back and orthogonal transforms, middle-of-track pickups, PTH versus
NPTH layer access, no bare crossing between layers, same-count geometry changes,
source-byte preservation, coupled-cell construction, placement, current binding,
full-pipeline and generalization regressions. The earlier 91-test focused set
overlaps this total and must not be added to it.

The first new fixture used an unsupported single-integer LSET constructor and
then put one negative-control gap exactly on a strict hit-test boundary; these
fixture defects were corrected. No production gate was relaxed to satisfy them.

`build/local-copper-proof-replay-v2-20260916/report.json` calls the actual
production local-cell auditor with the legacy and corrected helper on all six
explicit source identities. Four native families run concurrently; EPS/ATX
remain interface-held. Every **complete before/after audit report is identical**.
PCIe2's existing cells pass. The partially placed Hub/VHP/PCIe3 do not yet have
complete materialized local copper, and retain their existing audit refusals;
this is not a change to their prospective placement-craft verdicts.

Use **v2**: the first compact replay summary queried a nonexistent `violations`
field and displayed zero by default. Its full audit payloads were correct, but
that summary count was not. V2 requires the real `refused` field, reports
`refused_cells`, and was replayed rather than editing the evidence by hand.

The protected historical PCIe2 control is completely identical to the previous
control, including PCB hash, full regression, every probe and generalization
metadata. Its broader release holds remain. Final consolidated receipt:
`build/local-copper-proof-qualified-comparison-20260916.json`.
All six source/hierarchy identities remain unchanged; `git diff --check` passes.

## Handoff

All tests, native replays and control workers have finished. About 66 GiB is
free, above the 16 GiB floor. No new board geometry was admitted and no duplicate
dashboard preview was published. Keep
`build/route-finish-next-inputs-20260916.json`; PCIe2 remains 0 DRC / 9 opens.

This correctness fix prevents false ownership/locality evidence but does not
close the present physical blockers. Do not repeat the midpoint-witness screen
or spend another wave on unchanged failures. Durable complete-cell replacement
still needs source-bound owner/cap geometry, all reused/shared dependencies and
atomic reconstruction/requalification; UUID path evidence alone is insufficient.
The other useful physical work remains priority-access recovery and coupled
EPS/ATX main/mate geometry, with locked buses, edge spans and budgets preserved.
