# Exact power-bridge search feedback

## Result

This is a generic planner repair and diagnostic slice, not a new admitted board
layout or routing-closure claim. The latest native probes ran concurrently on
hash-bound current Hub and PCIe3 placement copies. No source board, schematic,
approved load budget, terminal interface or protected power bus was promoted
or changed.

- Hub: reproduced the same VCC_P1 transition failure at cell (19,24). The
  transition requires two current-rated vias; zero fit. A second search with
  that transition location excluded found no alternative and identified **F1
  pin 1** as the stranded terminal. The complete power-authority transaction
  remains refused. Elapsed: 6.246 seconds.
- PCIe3: a fresh exact power-authority compilation passed in 22.424 seconds.
  This qualifies the compiler entry point on another board; it does not resolve
  the board's existing priority-route blockers or establish full routing.
- Initial 12VHPWR probe: `power_route_authority_not_requested`; a no-op, not
  validation coverage and not progress.
- Historical PCIe2 control: board hash and all four independent probe objects
  remain exactly equal to the preceding receipt, including its pre-existing
  broader release failures. Native 0 DRC / 0 opens remains unchanged.
- **349 tests plus three subtests passed**, 4.88 seconds; `git diff --check`
  passed.

No full routing wave was launched: the current Hub power authority is still
unrealizable, and the other failed boards' unrelated blockers were not changed.
The existing Hub preview was inspected and its hash verified against this
probe's input. It is the retained placement, not a new routed result.

## Root cause and implementation

`route_overunder` qualifies copper-cell freedom on both transition layers.
Previously, `realize_overunder_rects` could then reject a current-sized via
field after pad, edge and existing-via ledger exclusions, without giving the
path search a chance to avoid that transition. A raster path therefore was
not evidence of physical transition feasibility.

The new `route_overunder_with_bridge_feedback` wrapper:

1. Finds a candidate multi-layer tree with the existing pathfinder.
2. Probes its complete ordered bridge set using the production realizer and
   the same current-sized via counts, pad/edge exclusions, local reseating,
   layer-admission masks and shared via ledger used for final construction.
3. On a typed `BridgeFieldRefused`, excludes that transition cell on a copied
   mask and searches again. It does not forbid ordinary copper traversal there.
4. Stops on admission, no alternative path, repeated refusal or the explicit
   budget (default eight replans). Unexpected exceptions remain errors.
5. Still runs final trunk/landing construction, clipping and independent native
   filled-copper admission. The preliminary field probe never substitutes for
   that gate.

`_overunder_bridge_geometry` supplies the same physical field contract to the
probe and final realizer. No board name, refdes, coordinate or UUID selects a
repair. Tests vary layer names and translations, including an exact-realizer
no-via case, no-bridge routes, unchanged input masks, invalid budgets and
unrelated errors.

This is a bounded search heuristic, not an impossibility proof. Excluding a
failed cell is conservative across orientations and layer pairs; alternative
field orderings or larger placement changes may still make a design possible.
The native Hub result means no alternate route was found under these masks,
not that its layout or underlying circuit cannot work.

## Fail-closed publication and durable evidence

The first diagnostic draft returned a no-path report after exhausted field
refinement. The native Hub test exposed why that was insufficient: the caller
could construct a partial frozen-net state without that rail and proceed to
a later, unrelated CAN-versus-power authority failure. Nothing was promoted,
but a missing rail must not silently become a valid authority inventory.

The final implementation throws `BridgeSearchRefused` when physical bridge
refinement exhausts, preserving the previous transaction-abort behavior.
`pour_first_stage` retains its structured `failure_evidence` alongside the
traceback. The evidence names the owning net, required/available vias,
transition layers/cell, search effort and stranded terminal. A regression
explicitly prohibits partial-authority publication on this failure path.

Native final evidence is at
`build/bridge-feedback-structured-native-20260914/hub-standard-rev2/report.json`,
under `planner.failure_evidence`.

## Receipts

- Final tests: `build/bridge-feedback-final-tests-20260914.log`.
- Final concurrent probes: `build/bridge-feedback-structured-native-20260914/receipt.json`.
  Every source/input signature and the shared engine signature stayed unchanged
  during that probe cohort.
- Protected control: `build/bridge-feedback-final-control-20260914.json`, compared
  with `build/original-neckdown-control-20260914.json`.
- Earlier diagnostic drafts: `build/bridge-feedback-native-20260914` and
  `build/bridge-feedback-native-final-20260914`. These are not selected board
  revisions and must not become continuation inputs.
- Native launcher: `tmp/bridge_feedback_native_20260914.py`; three-/two-board
  bounded diagnostic copies, 240-second per-child limit, two numerical-library
  threads per process, 16 GiB free-space floor. Source bytes are checked before
  and after; no source promotion occurs.

## Next generic slice

Use the structured failed-power-terminal evidence to drive bounded power-pin
escape/placement proposals *before* expensive unrelated priority-pair trials.
For this Hub, moving only the USB protection group cannot establish the missing
F1 power transition. Any proposal must preserve the approved high-current and
interface geometry and pass complete physical, power, pair and decoupling
admission before selection. Do not rerun the unchanged whole Hub pass merely
because the diagnostic is now clearer.

PCIe3/12VHPWR priority access and EPS/ATX coupled terminal clearance remain
separate outstanding work. No other-board closure claim is implied here.
