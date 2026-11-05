# Proposed-hole spacing and endpoint work attribution

## Shared physical defect fixed

The prior existing-hole repair did not cover **two newly proposed** bridge
barrels. `_ranked_bridge_seat_pairs` still treated 0.85 mm centre spacing as a
hard physical rule. That both rejected legal compact pairs and could admit
illegal larger-drill pairs when their required hole gap exceeded that constant.

The native bridge now checks actual via operations using both drill radii and
the board's existing hole-to-hole rule. Duplicate drill origins are refused.
Track-only operations are not holes. Each proposed seat still passes the
existing assembly, existing-hole, all-layer foreign-copper, power-reservation
and edge checks; final native DRC remains mandatory. No process limit or
geometry exception was relaxed.

The parameterized ranker retains legacy behavior for callers without a native
hole rule. In the native bridge, the previous 0.85 mm search preference is now
a **soft tier**, not a refusal: geometrically valid familiar candidates remain
first, and compact alternatives become available if those fail. Full escape
length ranking remains within each tier.

## Regression caught before integration

The initial expansion ranked all newly legal candidates directly by length.
Its bounded VHP diagnostic had 191 opens versus the legacy branch's 189, despite
both reporting 24 local closures. Different early route choices changed global
connectivity. The output was never admitted or published.

That result motivated stable preference tiers instead of wholesale reordering.
The corrected replay retains VHP, Hub and PCIe2 native metrics exactly. PCIe3
has 194 versus a 195-open timed control in the final replay; another control
already achieved 194, so this is **not attributed as a connectivity improvement**.
The important result is expanded legal fallback coverage with the current
control preserved, plus rejection of an independently reproduced invalid
larger-drill pair. Global route admission still owns regression rejection.

## Validation

- `build/new-hole-pair-qualified-tests-20260916.log`: **414 tests and eight
  subtests passed**, 113.88 seconds. Includes translated/rotated/front/back
  loaded-native fixtures, mixed drill sizes, strict board gaps, duplicate holes,
  invalid policies, deterministic preferred/fallback ordering, and a completed
  compact fixture independently checked by KiCad CLI at **0 errors / 0 opens**.
- Negative controls restore only the former fixed threshold: it rejects the
  valid compact fixtures and accepts the invalid larger-drill fixture.
- `build/new-hole-pair-qualified-suite-20260916/report.json`: four concurrent
  native old/new board-family replays, with EPS/ATX interface-held. Same 30 s
  whole-probe / 6 s per-net bounds and 24-closure cap. All six source/hierarchy
  identities remain unchanged. These are private ordinary-route diagnostics,
  **not admission bypasses or full routed candidates**.
- `build/new-hole-pair-qualified-comparison-20260916.json`: source identity,
  cross-board DRC/connectivity nonregression and generic-core checks pass.
  The historical PCIe2 PCB hash, complete regression and every probe are
  identical; all top-level control fields match. Existing release holds remain.
- Initial unqualified evidence is retained separately in
  `build/new-hole-pair-suite-20260916`; do not select those diagnostic boards.

## Next measured bottleneck — not repaired in this slice

PCIe2 never reached the seat-pair ranker in either residual replay. It spent
its bounded attempts earlier in endpoint qualification. A separate concurrent
native profile on all four admissible families (EPS/ATX held),
`build/endpoint-work-profile-20260916/report.json`, isolates that cost:

- PCIe2: 15.111 s profiled attempt, zero closures.
- `_lastmile_bridge`: 13.893 s cumulative; `_seats`: 13.875 s.
- **2,839 `_via_spot_clear` calls: 12.838 s cumulative.**
- Stub routing: 0.913 s; same-layer maze: 0.730 s.

These are instrumented bounded timings, not production throughput benchmarks.
They contradict the hypothesis that more maze effort is presently the main
cost. Inspect repeated native existing-hole enumeration and pad/foreign-copper
queries before adding another search budget. A promising generic optimization
is a plain-scalar, per-plan immutable existing-hole snapshot/spatial query,
rebuilt for each board mutation, with exact drill/copper decisions unchanged.
Do not introduce a persistent native-object cache or assume a hole snapshot
remains valid after copper mutation. This optimization is **not implemented**.
Use old/new blocker-decision parity and stale-snapshot negative tests before
another affected run. Do not repeat the same unprofiled six-second failures.

## Current retained state

No source layout or placement changed, no new canonical wave was launched, and
no preview was republished. Retain `build/route-finish-next-inputs-20260916.json`:
PCIe2 remains 0 DRC / 9 opens; Hub local cells, PCIe3/VHP critical access and
EPS/ATX coupled-interface holds remain. All test/replay/profile/control workers
finished. Existing suite heartbeat remains useful; no user action is required.
