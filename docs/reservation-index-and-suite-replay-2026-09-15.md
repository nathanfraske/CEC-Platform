# Exact reservation indexing and suite replay — 2026-09-15

## Prior cohort completed

`build/committed-power-suite-20260915/suite.json` completed without admitting
a new placement or route. Hub took 715.2 s, PCIe3 272.9 s and 12VHPWR 1,043.2 s.
All input board, hierarchy and engine hashes were unchanged. Their immutable
reviews remain accurately labeled BLOCKED; identical input images are not new
routed results.

- [Hub](http://localhost:8090/?id=pass-committed-power-suite-20260915-hub-standard-rev2-5fb3e019c5)
- [PCIe3](http://localhost:8090/?id=pass-committed-power-suite-20260915-pcie-8pin-3port-b8624c5d35)
- [12VHPWR](http://localhost:8090/?id=pass-committed-power-suite-20260915-12vhpwr-standard-17fcb456c4)

Hub's two physical/power-valid dependency trials now correctly used power-first
reservation authority (514 and 504 projected rectangles). Both exhausted their
240-second pair searches and were refused; the earlier power-crossing pair was
not admitted again. This is corrected ownership enforcement, not closure.
The operation completed normally, preserving trial evidence. Several periodic
worker stack samples were inside `_crosses_avoid`, repeatedly scanning the
reservation rows during local paired-escape enumeration. 12VHPWR retained two
priority-route refusals, and PCIe3 its existing placement/priority blockers.

## Generic acceleration

`cec_reservation_index.py` adds a tuple-compatible snapshot of layer-projected
reservations. A bounded spatial bucket lookup selects potentially intersecting
rectangles for each query. The existing exact Liang–Barsky test, track-width
expansion and original first-blocker ordering remain authoritative. No geometry
is rounded, no collision is waived and no bus or clearance policy is changed.

The index uses a configurable 4-mm tile and at most 256 bucket cells per row.
Oversized rows use a global list; oversized queries fall back to a full scan.
A conservative cell halo protects boundary-rounding cases. Tiny lists skip
index construction. Input rows are snapshotted; serialization reconstructs the
index from values for spawned workers, without native-board/cache references.
The index belongs to its exact supplied rectangle set, not a global board cache.

Layer projection now builds the index and the hot collision predicate queries
it. Ordinary five-/six-tuple callers remain supported. One-shot polyline point
iterators are normalized before reuse. No board/refdes/coordinate selector was
introduced.

## Verification and measured cost

- `build/reservation-index-integrated-tests-20260915.log`: **340 passed**, plus
  seventeen subtests. The 161-test focused set overlaps and is not added.
  Coverage includes 3,000 randomized differential queries, exact boundary and
  diagonal cases, giant/degenerate rectangles, deterministic witness ordering,
  layer selection, iterator reuse, input mutation isolation, spawn serialization,
  committed-power reconstruction and existing precision/full-pipeline guards.
- `build/reservation-index-benchmark-final-20260915.json`: **27,160 queries**
  on twelve real reservation layer datasets from Hub, PCIe2 and PCIe3. Every
  accept/reject result and first-blocker identity matched the unindexed scan.
  Per-layer median query speedups were **2.85–6.74×**; the sums of per-layer
  median times were 0.8754 s linear versus 0.1879 s indexed (4.66×).
  These are deterministic synthetic local segments/boundary probes against
  real native reservation data, **not a full routing-wave speedup**. Timed loops
  exclude one-time index construction. No result is a route-admission claim.
- The benchmark checks all six explicit input/hierarchy hashes. Only the three
  stored inputs with bindable complete power states are benchmarked; no state
  was invented for the other three. Every source/hierarchy stayed unchanged.
- `build/reservation-index-control-20260915.json`: historical PCIe2 board hash,
  board regression and all four probe objects exactly match the preceding
  control. Pre-existing release blockers remain visible, including pair/craft
  checks; unchanged control results are not a present-day fabrication pass.
- `build/reservation-index-generalization-20260915.json`: 61 neutral modules,
  zero core selector violations. Legacy findings remain 23 physical/380 runtime;
  whole-pipeline generic maturity remains false.
- `git diff --check` passed. Free space remains above the 16-GiB floor.

## Current follow-up

`build/reservation-index-suite-20260915/suite.json` is the next canonical
simultaneous replay for Hub, PCIe3 and 12VHPWR. It uses the same explicit inputs,
three jobs, two workers each, twelve placement trials, eight route passes,
1,800-second board deadlines and the storage floor. Inspect the journal and
processes before any launch or shared engine edit. Completion previews go to
the dashboard and `C:/Users/Admin/Documents/CEC-Board-Reviews/reservation-index-suite-20260915/`.

EPS/ATX remain at the coupled mating-geometry gate; no dimensions, terminal
lands or one-sided mating coordinates were changed. PCIe2 remains at its latest
0 DRC / 12-open continuation; its unchanged exhausted full route was not repeated.
After this replay, use measured failure certificates to choose the next slice.
The unresolved finalist-key attribution gap and coupled interface work remain
separate priorities; do not turn an inconclusive search into an infeasibility
claim or relax power ownership to recover an apparently successful pair.
