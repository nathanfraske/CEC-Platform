# Priority dependency and plated-power preclosure — 2026-09-14

## Current work

The combined changes are running through the canonical pipeline concurrently
on **Hub, 12VHPWR and PCIe3**:
`build/priority-plated-suite-20260914/suite.json`.
Read that journal and live processes before any new launch. Do not edit shared
engine scripts while this cohort runs. Inputs are the explicit hash-bound
current continuations in `build/parallel-suite-inputs-20260914.json`; no
rejected diagnostic trial was promoted to a source.

The run has three board jobs, two workers per board, twelve placement trials,
eight routing passes, two route candidates, and a 1,800-second per-board wall
limit. The 16-GiB free-space floor remains enforced. EPS/ATX still require a
qualified coupled terminal-interface ECO; their guards were not bypassed.
PCIe2's unchanged exhausted completion search was not launched again.

## Completed PCIe2 full pass

`build/copper-echo-route-followup-20260914/suite.json` completed in 1,057.15
seconds. Both seeds passed import sanitation and detailed routing, reached
final signoff, and retained **0 DRC / 12 opens**. No additional connections
closed. The additional runtime versus the previous import failure was spent
in downstream completion/certificate stages that could now execute; it is not
a routing speedup or a fabrication pass.

The journaled winner and its immutable dashboard copy both have SHA256
`fbaa5161199590c28ad54062d3eb6c4d8470b1684469b27a75700ce01956a1e7`.
[Verified partial-route review](http://localhost:8090/?id=pass-copper-echo-route-followup-20260914-pcie-8pin-2port-0f7b88ca36).
The body-free top image was inspected locally, and its dashboard artifact URL
returned HTTP 200/image/png, 76,192 bytes. Windows mirrors are under
`C:/Users/Admin/Documents/CEC-Board-Reviews/copper-echo-route-followup-20260914/pcie-8pin-2port/`.

The live import report counted zero *exact* echoes immediately after SES and
18 after import-side finishing. This localizes when they became exact matches;
it does not distinguish new generation from normalization of overlapping SES
segments. The exact end-of-import reconciliation passed its live producer test.

## Generic changes

1. **Typed frozen-copper refusals and atomic pair dependency plans.** A power
   placement can replace only the complete qualified signal-pair closure named
   by native collisions. Immutable power nets, unrelated copper and item-owned
   return vias remain protected. The actual replacement must be constructed,
   pass independent pair connectivity/physics, retain the remaining prefix,
   rebind power authority and pass final physical checks before promotion.
2. **Fair bounded dependency effort.** Invalid courtyard placements no longer
   consume the two scarce power/rebuild attempts. They remain bounded by the
   twelve placement proposals and outer wall-time budget. Budget exhaustion
   is recorded distinctly from physical impossibility. Full typed collisions
   and native courtyard evidence remain in the trial journal.
3. **Bounded rejected-copper evidence.** Up to two exact filled power failures
   retain PCB, project/rules, state and hashes before temporary cleanup. These
   are explicitly rejected diagnostics with no release authority, not new
   candidate inputs. Storage remains bounded and checks the free-space floor.
4. **Explicit plated-through local power preclosure.** The existing guarded
   same-footprint solver can now join disconnected PTH power pins in an
   explicit net scope. NPTH and through-hole differential breakouts are not
   included. Already connected barrels across other layers need no extra
   copper. Emitted tracks use permitted route layers and existing per-layer
   current-width/clearance contracts; no load budget or via rule was changed.

## Native findings and limits

The initial pair-dependency replay spent its two attempts on courtyard-invalid
rotations. After budget correction, two courtyard-valid translations passed
the former bridge-search obstruction and reached exact filled-power admission.
They were rejected because `+5V_SYS` had three separate authority components:
one included mezzanine pin 1 and its power-switch sink; pins 3 and 5 remained
isolated. The local package-power stage explicitly excluded THT, while the
pours had not joined these pins. That was not a need for extra ground vias.

Both exact rejected boards were retained in
`build/priority-dependency-native-20260914-c/` and replayed in
`build/plated-power-native-20260914/receipt.json`:

- Two local connections added per trial, **zero vias** added.
- All six frozen current domains became connected, retaining their approved
  current declarations.
- Native opens decreased **242 → 240**; DRC stayed **12 → 12**. Those twelve
  `drill_out_of_range` findings were already present in the diagnostic
  baselines; this is not a claim of zero DRC on those trial boards.
- Independent stage admission accepted both local changes; original protected
  copper and source hashes were unchanged.

These are diagnostic local-repair successes. Their released CAN pair still
needs reconstruction, so neither is an admitted Hub placement or routed board.
The live canonical cohort must exercise that remaining transaction. No source
design, pinout, dimensions or main/daughterboard mounting geometry was changed.

## Verification receipts

- `build/priority-plated-integrated-tests-20260914.log`: **187 tests passed**,
  plus fourteen parameterized subtests.
- `build/plated-power-existing-links-tests-20260914.log`: seven additional
  existing local-link tests passed; these are disjoint from the integrated set.
- `build/priority-dependency-cross-board-20260914.json`: read-only ownership
  planning replay on all six inputs. Five qualified-pair cases across Hub,
  12VHPWR and PCIe2 retained atomic ownership and power exclusions. All fifteen
  probed power-net collisions were refused. Boards without qualified pairs
  were not counted as positive reconstruction tests.
- `build/priority-dependency-native-20260914-b/receipt.json`: bounded physical
  retry with source/hierarchy/engine hashes unchanged. PCIe3 was a no-op at
  this particular power-failure entry point, not a newly routed result.
- `build/plated-power-control-20260914.json`: historical PCIe2 board hash,
  board-regression result and all four independent probe objects exactly match
  the prior control. Its other historical release blockers remain visible.
- `build/priority-plated-generalization-20260914.json`: sixty declared neutral
  modules; no core selector violations. Whole-pipeline generic maturity still
  remains false (23 legacy physical and 380 runtime selector findings).
- `git diff --check` passed. No shared engine code was edited during native
  cohorts; the current three-board cohort uses the final tested revision.

## Next review

Inspect each completed board's exact stage and failure certificate, and verify
any published body-free output against its journal hash. In particular check
whether the Hub now reaches actual pair reconstruction and whether 12VHPWR or
PCIe3 gain from their through-hole power prerequisites. Do not repeatedly run
unchanged rejected moves. Retained exact-power diagnostics now support direct
inspection of any remaining fill/terminal fault. Mechanical EPS/ATX conflicts
still require paired geometry/authority work, not a downstream waiver.
