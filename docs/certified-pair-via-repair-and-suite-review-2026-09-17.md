# Certified-pair via repair and concurrent suite review

## Result

No board gained an admitted route or placement in this slice. The canonical
cohort remains `build/frozen-priority-next-inputs-20260916.json`; do not promote
scratch trials or publish unchanged pictures as new candidates.

The native via transaction now finishes with specific bounded-search evidence
instead of an avoidable worker timeout. The first scope-only replay took
**8.200 s**, versus **95.015 s** for the preceding implementation. After adding
a genuinely broader local-seat search, the final transaction took **22.202 s**,
with two completed target probes and one refused incident-stub reconstruction.
This is one local transaction comparison, not a whole-pipeline speed benchmark.
PCIe2 remains **zero DRC errors / nine unconnected items**.

## Generic defects repaired

1. The via planner read exact endpoints but discarded them before execution.
   Plans now carry the pair, width and clearance. The worker resolves that
   pair against live native geometry, retains the existing route/profile
   guards, and records component counts and per-pair evidence. It does not
   spend its allowance on unrelated disconnected islands. Malformed or stale
   present endpoint evidence fails closed. Older persisted plans without that
   evidence have an explicitly labeled, bounded legacy-net fallback.
2. The parent killed a worker after 45 seconds while the child could default to
   75 seconds of whole-net searching. The parent now passes an inner allowance
   below its actual remaining watchdog, reserving native save/IPC time. Errors
   identify whether the failure occurred during via re-seat, target completion
   or whole-board admission.
3. The exact-pair solver called its final phase broader, but repeated the same
   four directions and 2-mm via-offset catalogue. The final phase now uses the
   existing shared bounded dogbone/local-lattice catalogue, with ordinary via,
   POFV, copper, layer and edge guards unchanged. Every bridge phase records
   its domain, elapsed time, outcome and budget exhaustion separately.
4. The planner deduplicated every later pair sharing a net and obstacle via.
   It now includes the unordered endpoint identity in that key. Reversed
   duplicates are removed; distinct island pairs remain separate bounded
   tasks. The final current-board planner replay exposes no additional untested
   domain on this PCIe2 input; this correction is covered synthetically.

No board name, reference designator or coordinate is embedded as a new repair
condition. Exact-pair success is not admission: the composite still requires
whole-board DRC/connectivity and protected-copper/pair non-regression. None of
the failed trials replaces its input. Approved loads, high-current buses,
schematics, fabrication rules, mating spans and dimensions are unchanged.

## Evidence and regressions

- `build/pair-scoped-final-tests-20260917.log`: **414 selected tests pass**.
  Native translated/renamed fixtures close only the named pair, leaving a third
  same-net island and every pre-existing track unchanged. Tests also cover
  stale/malformed endpoints, returned timeouts, legacy budget forwarding,
  broad-versus-fast domain distinction, distinct/reversed pair handling and
  rejection after a successful local close when whole-board admission fails.
- `build/certified-via-suite-20260917/report.json`: scope-only native replay,
  concurrent physical review of four current families, two interface holds,
  historical PCIe2 control, and exact six-source/hierarchy checks.
- `build/expanded-pair-suite-20260917/report.json`: final expanded native route
  transactions and concurrent suite review under a frozen v50 engine. A direct
  exact-pair attempt **without moving any obstacle** also refuses in 7.702 s of
  target work; both moved-via attempts refuse after 7.755 / 7.813 s. The broader
  phase completes rather than timing out. The moving-via experiment therefore
  does not justify repeating this same domain.
- `build/pair-scoped-native-review-v2-20260917/report.json`: final v51 native
  planner/source replay and historical control. The native tuple/JSON-list
  representation is normalized before classifying already-tested domains;
  v1's raw-Python comparison was a diagnostic false novelty, not a new route.
- `build/pair-scoped-generalization-20260917.json`: declared core passes;
  wider legacy debt is still **23 physical / 380 runtime findings**. Full
  generic-runtime and fabrication-release claims remain false.

The historical control's board hash, regression and probes match throughout.
The selected test count is not the count of every repository test, and test
counts from the intermediate runs must not be added together.

## Current board separation and next work

| Board | Verified continuation status |
|---|---|
| PCIe2 | Physical screen passes; 0 DRC / 9 opens unchanged. The new pair evidence identifies several pin-access/power/neighboring-route obstructions, not just the relocated via. |
| PCIe3 | Physical screen passes; the same checkpoint retains its recorded 8 critical-route refusals. No unchanged placement wave was repeated. |
| Hub | Fresh native physical review still finds two local ground-return access blockers and one isolated-tangent supply proximity blocker. |
| 12VHPWR | Physical screen passes with one local cell deferred to pre-route interconnect; the same checkpoint retains its recorded USB priority refusal. |
| EPS rev3 | Unadmitted coupled-interface ECO hold; terminal copper envelope/mating repair and route-authority rebuild are required. |
| ATX 24-pin rev3 | Same coupled-interface hold, including stack access. Do not move one mating half alone or infer an unqualified transform. |

Next productive work is coordinated endpoint access/owned support-group repair,
with exact same-island anchor alternatives where supported, and the separate
coupled main/daughterboard copper-envelope problem. Inspect existing mechanisms
before adding another overlapping solver. Do not repeat the tested detector-via
poses, the old single-passive menus, or unchanged Hub/PCIe3 placement batches.
Final refusal evidence is bounded coverage, never a global no-path proof.

These cohorts used concurrent native workers and finished; they were not six
simultaneous routing waves. No new preview is warranted. The existing 15-minute
suite-review heartbeat remains active and reads the newest ledger; it should
continue generic work without duplicating completed campaigns. About 65 GiB
remains free; the two native route/physical cohorts occupy about 38 MiB total.
