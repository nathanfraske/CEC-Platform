# Filtered terminal placement demands — 2026-09-16

## Root cause and implemented slice

The earlier sense-topology repair proved the actual shunt identity through
typed filter resistors, but the critical-terminal placement scorer still
discovered only direct HI/LO nets shared by a shunt and monitor. On the current
12VHPWR input this produced **zero terminal-order relations**, despite six
resolved filtered current-input channels. The cheaper overlap-search metric
inherited the same missing relations. A passing Boolean therefore did not mean
those filtered paths had been scored.

The production placement-evidence hook now supplies the live native topology,
using complete existing current-flow authority for renamed force nets, and
captures native footprint-local pads. `cec_sense_topology.placement_segments`
turns each proven chain into its actual same-net copper demands: monitor input
to the near filter pad, far filter pad to the next stage or shunt. It never
draws copper through the resistor or invents a single shunt-to-IC net. Multiple
series stages retain every intermediate net and pad identity; capacitors are
not series path edges.

The full terminal-order scorer measures those segments when ranking the
existing four IC rotations. Filters and the anchor stay at their current poses
in that rotation comparison. It counts crossed different-net demand segments,
retains endpoint-land obstruction ranking and sums the actual segment demand
lengths. The cheap placement scorer consumes the same portable segment
specification and shared geometry evaluator, so moving a filter changes the
metric too. Existing direct-path behavior is unchanged.

Every segment endpoint is checked against current pad number, net and unique
physical position. Missing, contradictory, ambiguous or unresolved topology
fails closed rather than disappearing from the scored population. Native local
coordinates preserve front/back reflection and arbitrary rotation. No board,
reference-designator, coordinate, resistor value or load-budget exception was
added. No clearance or engineering limit was relaxed.

These are placement demand metrics, **not routed copper, an impossibility
proof, permission to move locked power, or a complete new filtered-routing
algorithm**. This slice adds no independent filter-rotation search or new
ownership/unlock authority; existing materialization and physical admission
remain mandatory.

## Native suite and actual production hook

`build/filtered-terminal-suite-20260916/report.json` replays all six explicit
canonical input identities, with four native family workers and EPS/ATX held
before downstream evaluation by their interface-ECO gate.

| Board | Old scored relations | New scored relations | Result |
|---|---:|---:|---|
| 12VHPWR | 0 | 6 | 24 real segments; zero demand crossings |
| PCIe2 | 4 | 4 | Direct evidence unchanged |
| PCIe3 | 6 | 6 | Direct evidence unchanged |
| Hub | 0 | 0 | No applicable sense-input relation |
| EPS / ATX | held | held | No interface gate bypass |

All full/cheap per-relation crossing and length metrics agree. The six VHP
relations currently pass; this closes a coverage hole, not a placement defect
or a board connection. Source boards and hierarchy signatures are unchanged.

`build/filtered-terminal-craft-replay-20260916/report.json` independently calls
the **actual production placement-craft hook**, not just the new helper, across
the same cohort. Its terminal-order evidence exactly matches the direct replay.
PCIe2 and PCIe3 retain their craft pass; Hub and VHP retain their unrelated craft
holds. This does not reclassify PCIe3's remaining priority-route failures.

## Verification and control

Final integrated tests: **461 passed**, seven existing Shapely deprecation
warnings, 138.29 seconds. Receipt:
`build/filtered-terminal-integrated-tests-20260916.log`.

The overlapping focused suite has 76 tests. New cases include actual segmented
net identity, multiple series stages, unqualified/discontinuous witnesses,
loaded-native translated/rotated/front/back boards, full/cheap parity, crossed
IC rotation, filter movement affecting the demand metric, stale pad/net data,
missing components and ambiguous repeated-pad geometry. No source board bytes
change. Existing direct terminal-pin, current binding, full-pipeline, placement
admission and generalization tests also pass. Do not add overlapping counts.

`build/filtered-terminal-control-20260916.json` is **completely identical** to
the prior `build/hole-snapshot-qualified-control-20260916.json`: protected PCB
hash, complete regression, every probe and generalization metadata. The
historical control's broader release holds remain in force.

Final consolidated receipt:
`build/filtered-terminal-qualified-comparison-20260916.json`.
It records four native families, two preserved interface holds, all six
unchanged source/hierarchy identities, six new filtered relations / 24 segments,
production-hook parity, and `promoted: false` / `release_accepted: false`.
`git diff --check` passes.

## Continuation

No new full board pass or candidate is admitted, so no duplicate dashboard
preview was published. All tests/control/replay workers have finished; 66 GiB
is free, above the 16 GiB floor. Keep the canonical
`build/route-finish-next-inputs-20260916.json` and its no-unchanged-wave decision.

Do not launch another identical VHP or PCIe3 wave just because this coverage
repair landed: the newly measured paths pass without a pose change. Return to
the independent physical dependencies: complete owned local-cell access,
priority escape reconstruction, and jointly constrained EPS/ATX main/mate
geometry. Preserve locked buses, approved currents, dimensions and the
historical PCIe2 control. The suite is still not fabrication-ready.
