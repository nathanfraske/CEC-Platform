# Frozen local-PI authority and copper-layer identity — 2026-09-15

## Completed cohort and forensics

`qualified-escape-suite-20260915` finished **10:26:17Z**, with source, hierarchy
and engine signatures intact. Hub passed placement (888.025 s) and route
preflight (160.901 s), then its two detailed-route candidates both failed the
local-power-prefix barrier before residual routing. That stage failed in
22.981 s; it did not silently accept crossings. VHP finished its 1187.538-s
attempt with the exact input retained and the same USB refusal. No new eligible
whole-board route exists; neither board is fab-ready.

The retained Hub diagnostic is
`build/qualified-escape-suite-20260915/hub-standard-rev2/04-route/candidate-000000/local-power-prefix/kelvin.kicad_pcb`.
`build/frozen-layer-forensic-20260915.json` proves that all seven reported track
incursions were against In3.Cu polygons although the tracks were on F.Cu.
`_derive_pour_boxes` had an outer-layer-only mapping with an F.Cu default.
The three GND vias, in contrast, really pierce that inner power region.
Corrected retained-case counts are **0 tracks / 3 vias**, not a clean board.

## Generic repairs

1. `cec_power_guard_geometry.copper_layer` resolves canonical and display names
   against the board's actual enabled copper stack. Unknown, non-copper and
   disabled layers fail closed; they cannot become top copper. Public obstacle
   records use canonical names, including inner layers.
2. Complete frozen polygons are unioned with search reservations for additive
   track/via guards. Clipping a *planning* corridor around anticipated owned
   copper does not cut the physical frozen pour. Exact Manhattan decomposition
   keeps hook pockets open; no bounding-box slabs are manufactured. Shared
   through-via and canonical/maze track helpers all consume this authority.
3. Route-time local PI had hidden `CEC_POURFIRST_STATE` under a critical-first
   scheduling context, whereas the next exact-power consumer replayed that
   same state unchanged. Complete committed authority is now retained during
   both local-cell production and placement craft qualification. Prospective
   anchor/replan contexts retain their explicit release behavior. Missing
   declared authority fails closed, and context exit restores the environment.

No board/refdes/coordinate selector or power-budget adjustment was added.
No bus outline, land, via size, footprint position or source schematic was
changed by this repair. The original power no-incursion rule remains enforced.

## Validation and actual limitations

- `build/frozen-pi-final-tests-20260915.log`: **486 tests and three subtests
  pass** (106.41 s). Includes final placement-context coverage.
- Separate checker suite: **83 pass / one skip**. An earlier broad selection
  was interrupted because a legacy corridor test launched a complete placement
  search; it is not counted as a completed suite. The bounded focused suites
  and native replay above/below are the completed evidence.
- `build/frozen-pi-native-20260915/report.json`: native source replay completed
  in 5.15 s. The corrected generator refuses four complete cells (three on one
  selector, one regulator cell) and **rolls back**. It no longer emits unsafe
  vias then discovers them at the next stage. Source and engine stayed exact.
  This is detection/transaction repair, **not physical routing closure**.
- `build/frozen-pi-suite-audit-20260915.json`: explicit latest placement-stage
  artifacts for Hub/VHP plus the hash-bound six-family input plan. Hub now
  exposes those local-return failures to placement; PCIe3 exposes three local
  access failures; PCIe2 local PI passes. EPS retains major unmoved-placement
  obligations behind its mating gate. ATX fails closed on missing required
  sibling power state. VHP reports one local-access diagnostic in this replay;
  it was not an affected committed-state case and needs its own certificate
  review before attributing that diagnostic to these changes. No source changed.
- `build/frozen-pi-control-comparison-20260915.json`: protected historical
  PCIe2 SHA, complete board regression and all probes are exactly unchanged.
  Core anti-overfit: **67 modules / zero core violations**; 380 broader runtime
  findings still prevent a whole-runtime generic/release claim.

The previous Hub placement-feasible result did not prove complete PI/power
coexistence, because its local-cell context hid the committed power. The new
placement gate makes that missing obligation explicit. The local/global escape
composition remains useful and its synthetic tests pass; it is not a waiver
of the newly enforced full-cell authority.

## Next bounded work

Exercise the existing generic placement repair with these newly visible local
return blockers on **Hub and PCIe3 concurrently**. Preserve current busses and
their exact authority; do not move one cap or drill manually. Hub input is an
explicit, journal-hash-verified completed placement stage (SHA `b7cc3990...`),
not a fabricated routed winner or mtime fallback. The failed route has no
eligible output. VHP's identical exhausted USB attempt is not restarted.
EPS/ATX remain held for the coupled interface ECO; the PCIe2 incumbent is kept.

Harness: `tmp/frozen_pi_followup_20260915.py`. Keep shared scripts fixed once
the new cohort starts and inspect journals AND live descendants before edits.

Dispatched **11:00:31Z** as `build/frozen-pi-followup-suite-20260915/suite.json`:
Hub PID 121771 / PCIe3 PID 121772. Plan/lineage:
`build/frozen-pi-followup-inputs-20260915.json`. Both were confirmed running;
no new physical result was yet available. Two workers each, 1800-s board
bounds, 1200-s priority allowance, explicit 480-s pair effort, 2100-s parent
hard bound and 16-GiB free floor. Review publication remains enabled.
