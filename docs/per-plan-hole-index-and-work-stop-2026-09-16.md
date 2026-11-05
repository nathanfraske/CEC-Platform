# Per-plan hole index and honest work-budget stopping — 2026-09-16

## Outcome and scope

Two reusable search-engine repairs are implemented and tested. No current board
is newly admitted, no release hold is waived, and no private diagnostic board is
published as a full-pass winner. Keep `build/route-finish-next-inputs-20260916.json`
as the canonical six-board input plan. The historical PCIe2 regression control
and all six current source/hierarchy identities remain unchanged.

The previous endpoint profile identified repeated native via enumeration as a
large part of PCIe2's bounded search cost. This slice removes that repeated work
without changing its exact hole-clearance decision. Fixed-work replay then
exposed a separate outer-loop stopping defect, which is also repaired.

## Exact per-plan spatial lookup

`scripts/cec_hole_index.py` stores immutable scalar hole records in a uniform
grid. It retains native enumeration order, including duplicate UUIDs. Query
reach includes the proposed drill, largest existing drill and board hole gap;
the subset is conservative, not a clearance certificate. Huge queries fall back
to all scalar records rather than enumerating a huge empty grid. Explicit
replacement identities remain available even outside the local query region.

`cec_fr._lastmile_bridge` builds the snapshot once per read-only plan and passes
it privately to `_via_spot_clear`. The exact duplicate-origin, replacement
identity, actual drill-radius and native hole-gap checks still decide legality.
Pad, assembly, foreign-copper and reserved-power checks are unchanged. The
unindexed path retains the original exhaustive native hole loop.

There is no global or persistent cache and no retained SWIG object. A new plan
rebuilds the snapshot even when a via moved or resized without changing the
board's item count. Callers must not reuse the private snapshot across a board
mutation. The module is included in the generic-engine audit.

## Work exhaustion is not an impossibility proof

The first fixed-work diagnostic exhausted its 2,048-unit search scope, but the
outer last-mile loops continued until their 60-second wall guard. On PCIe3 this
produced 4,306/4,326 futile refusal records and approximately 60.2 seconds of
work. These were private diagnostic runs, not production routing progress.

`cec_search_budget.stop_status()` now polls without consuming more work and
preserves nested-scope lifetime. `synthesize_lastmile` stops its outer loops when
the existing active work scope is exhausted, independently of wall timeout.
Reports explicitly carry `search_budget_exhausted`, `search_budget_detail`, and
`bounded_pair_search_budget_exhausted`; `exhaustion_is_no_path_proof` is false.
The repair neither installs a new production quota nor calls an unexplored route
impossible. The corrected PCIe3 indexed diagnostic stops in 0.919 seconds with
one explicit work-budget refusal, rather than thousands of retries.

## Verification

Final integrated suite: **445 tests and eight subtests pass**, 108.23 seconds,
seven existing Shapely deprecation warnings. Receipt:
`build/hole-snapshot-qualified-tests-20260916.log`.

Coverage includes randomized broad-phase conservatism and order, native guard
decision and full refusal-evidence parity, duplicate/replacement identities,
same-count mutations between plans, scalar serialization, nested-budget
restoration, and loaded-native outer-loop stopping. It also covers prior exact
new-hole spacing, pair/endpoint escape, current binding, dimensions, design
principles, full-pipeline and generalization regressions. Do not add overlapping
earlier test counts to this total.

### Warm fixed-query guard comparison

`build/hole-snapshot-warm-parity-20260916/report.json` checks **541 queries** on
four native board families. Every Boolean result and complete blocker record
matches. Measurements warm the existing foreign-shape cache first, alternate
native/indexed order, and report medians.

| Board | Queries | Existing vias | Native seconds | Indexed seconds |
|---|---:|---:|---:|---:|
| 12VHPWR | 144 | 28 | 0.073448 | 0.003984 |
| Hub | 133 | 13 | 0.032504 | 0.007391 |
| PCIe2 | 144 | 386 | 0.243662 | 0.006268 |
| PCIe3 | 120 | 0 | 0.006584 | 0.006018 |

PCIe2 is about 39 times faster for this guard-query batch, **not for the whole
router**. These short measurements do not establish universal throughput; the
zero-existing-via PCIe3 case appropriately gains little.

### Equal fixed-work native replay

`build/hole-snapshot-qualified-fixed-work-suite-20260916/report.json` runs the
four admitted diagnostic families concurrently. EPS and ATX remain explicitly
interface-held. Each native/indexed pair consumes the same 2,048 work units and
has identical guard-call count, score, complete track/via geometry fingerprint,
and zone declarations. Every pair reports work exhaustion rather than timeout.

| Board | Guard calls | Native seconds | Indexed seconds |
|---|---:|---:|---:|
| 12VHPWR | 755 | 1.717 | 1.385 |
| Hub | 311 | 1.175 | 1.083 |
| PCIe2 | 804 | 2.707 | 1.276 |
| PCIe3 | 410 | 1.055 | 0.919 |

The quota is diagnostic-only. No extra connection is credited from these
equivalent-work results.

### Equal wall-clock replay is mixed, not accepted

`build/hole-snapshot-suite-20260916/report.json` used 30 seconds total, six per net
and a 24-closure cap. PCIe2's via-guard calls increased from 11,381 to 161,824,
and complete seat-pair ranker calls from zero to twelve, but its board remains
**0 DRC / 9 opens**. Hub and PCIe3 diagnostic scores are identical.

**12VHPWR worsens from 189 to 190 opens** in this timed experiment, with three
DRC violations unchanged. More search within the same elapsed budget changes
route choices and allocation of the later closure cap. This is not a uniform
route-quality improvement. None of these private diagnostic outputs is promoted.
Mathematical guard equivalence does not justify accepting a worse time-limited
search output; native scoring and incumbent selection remain required.

### Protected control and provenance

`build/hole-snapshot-qualified-control-20260916.json` retains the prior protected
control's PCB hash, complete board regression and every probe. Only the generic
engine metadata differs due to the new module. The historical control remains
0 DRC / 0 opens, 615 tracks, 226 vias and 1,242.073 mm; its broader pre-existing
release holds are not waived. Its nonzero tool exit reflects those holds.

Consolidated receipt:
`build/hole-snapshot-qualified-comparison-20260916.json`.
It explicitly records all six unchanged source/hierarchy identities, fixed-work
geometry parity, the timed VHP one-open regression, and `promoted: false` /
`release_accepted: false`.

## Handoff

All replay, control and test workers have finished. About 66 GiB remains free;
the 16 GiB storage floor is intact. No full-wave output or dashboard preview was
republished. Existing unrelated worktree changes are preserved.

Do not keep rerunning identical PCIe2 timed probes or tuning this now-measured
query kernel. Next useful work is owned priority/local-cell access and coupled
EPS/ATX mating geometry, retaining locked power buses and source identities.
The scheduler can use existing deterministic work scopes with honest exhaustion
and incumbent comparison, but this slice does not install a new production
quota. Current physical gate failures remain real and separate from search
performance; the suite is not yet fabrication-ready.
