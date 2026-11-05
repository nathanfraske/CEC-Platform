# Generic rail geometry contract — 2026-09-04

## Outcome and scope

Implemented one shared physical rail compiler for placement reservation and
enabled `force_rails` copper generation. This is a bounded reusable mechanism,
not a claim that the whole pipeline is generic or that a board is fab-ready.
No board-specific component move, new routing wave, or manufacturing release
was performed. Existing candidate and archived control PCBs were read-only.

## Root causes removed

1. The placement reservation independently reconstructed rail geometry. It
   selected a literal source connector, collapsed repeated electrical pin
   numbers, assumed source pad dimensions/type, and substituted component
   origins when physical geometry was unavailable. Its 5 V/standby sizing also
   used 25 A/5 A rather than the declared 20 A/3 A.
2. Live copper generation independently rediscovered terminals using a literal
   source reference prefix and a voltage-name current ladder. A connector could
   therefore belong to a different rail plan than placement reserved.
3. Courtyard-only live envelopes missed copper extending beyond the courtyard.
   Tests also found that the footprint emitter mirrored polygon vertices/pads
   but not line/rectangle/circle/arc coordinate tokens on the back face.

## Reusable changes

- `scripts/cec_rail_geometry.py`: pure topology-to-rail compiler; adapters for
  proposed placement and live KiCad pads; list-based physical contacts preserve
  multiple lands bearing one pin number. It rejects missing terminals, invalid
  geometry, ambiguous direction and invalid explicit roles.
- `scripts/cec_pcb.py`: additive `local_physical_pads` API; existing dictionary
  APIs remain unchanged for unrelated callers.
- `scripts/cec_force_rails.py`: shared geometry and sustained-current authority;
  optional explicit topology and `PowerRole` fields. Conventional reference
  classes remain a compatibility discovery path, but no exact part identity is
  needed. Declared boards cannot silently fall back to guessed current ratings.
- `scripts/cec_synth_pipeline.py`: reservation and both materializers use the
  shared compiler/current resolver and the same declared shared-bus topology.
  An enabled stage with no supported topology fails instead of reporting 0/0
  rails as success.
- `scripts/gen-module-pcb.py`: all supported graphical coordinate tokens follow
  the same native back-face transform as pads. Physical envelope caches are
  bounded and include actual copper plus courtyard geometry.
- `scripts/cec_rail_geometry_replay.py`: read-only adapter parity replay, with
  board hashes and per-rail evidence, parameterized by board path/policy hint.

Anonymous legacy callers retain an explicitly labelled voltage-ladder fallback;
production calls in the two materializers supply board current authority. This
does not qualify those current ratings thermally or mechanically. The existing
rail planner remains a shared-bus/series-element routing grammar, not a universal
replacement for every power topology. Duplicate physical shunt contacts that
the grammar cannot represent are rejected, not guessed.

## Validation

Synthetic tests cover arbitrary references/net names, explicit current override,
invalid/missing current, missing terminals, same-number terminal legs, an
unrelated connector on the same net, ambiguous direction, invalid geometry,
and an empty enabled stage. Copper actually generated on two synthetic boards
is identical after renaming their source connector. All four right-angle poses
on both faces compare library reservation with materialized KiCad geometry;
these include an asymmetric four-leg terminal and a two-land series element.

Relevant suites: **576 unique tests passed, 15 skipped**. The final focused run
was 46 passed (including 9 generalization tests already in the wider suite).
The wider two runs were 412 passed/15 skipped and 127 passed. Logs:

- `build/rail-contract-focused-tests.log`
- `build/rail-contract-regression-tests.log`
- `build/rail-contract-full-pipeline-tests.log`

Cross-board adapter replay:

| Board | Rails | Contacts / series pads / face / current / escape envelope | Hash unchanged |
| --- | ---: | --- | --- |
| Current 24-pin candidate | 4 | All matched | Yes |
| Archived PCIe 2-port fab-review control | 2 | All matched | Yes |
| Current PCIe 3-port candidate | 3 | All matched | Yes |

Reports: `build/rail-contract-replay-{atx,pcie2,pcie3}.json`.
This validates adapters on three boards/two families; it is not an end-to-end
reroute replay of those boards. Conventional discovery on these real boards
does not by itself demonstrate arbitrary `PowerRole` schemas; synthetic tests
exercise the explicit-role path.

PCIe control:
`build/board-archive/20260831T1619-pcie-8pin-2port-v113-zero-open-v43/board.kicad_pcb`

SHA-256: `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`.

Current release probes are exactly equal to the previous turn's replay:
0 DRC, 0 unconnected, 615 tracks, 226 vias, 1242.073 mm track length. The same
8 current constraint blockers remain, alongside 9 non-octilinear segments and
1 fabrication acid-trap finding. The archived summary's old passing release
label is **not** reaffirmed by current checks.

Report: `build/pcie2-fab-review-rail-contract-regression.json` compared against
`build/pcie2-fab-review-current-regression.json` (all four probe payloads equal).

Static audit: physical selector occurrences **32 -> 23** (13 in synthesis,
10 in the separate force-lane engine); runtime occurrences **389 -> 380** across
95 runtime modules. The new core module is included in the gate. These are
static occurrences, not a count of proven functional defects, and do not detect
every possible numeric or dynamic special case. Full generic release remains
false. Evidence: `build/generalization-rail-contract.log` (JSON).

## Next bounded slice

Unify route feature dimensions: source current, trace width, via diameter/drill
and qualified via-in-pad rules should produce one contract consumed by routing,
repair and signoff. The unchanged PCIe findings give concrete regressions:
VBUS routes lack a path meeting the current-derived 0.845 mm width requirement;
50 features on 10 nets are below declared minima; 7 via-in-pad features fail
qualification. First reconcile the authorities, then add synthetic mutations
and bounded cross-board routing repair replay. Do not lower signoff thresholds
to match old copper or patch individual component coordinates.
