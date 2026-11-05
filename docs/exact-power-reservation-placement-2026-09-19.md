# Placement access must use the admitted power geometry

## Implemented result

The production Hub physical replay now has **one native local-return refusal,
down from two**. The U7.1/C15 input bypass cell constructs successfully; the
U7.7/C27 output bypass cell remains blocked. This is a real constructor
improvement, not the removal of a checker requirement. No component, existing
track, existing via, frozen pour, power field, schematic or canonical input was
changed. The Hub is not yet admitted to routing or fabrication.

Production evidence: `build/exact-power-reservation-suite-20260919/report.json`.
All six canonical PCB/hierarchy signatures match. All current physical results
retain parity except the Hub's reduced refusal count. Historical PCIe2 PCB,
regression verdict and individual probes also match. PCIe2 still has five opens;
PCIe3 still needs critical-route closure; VHP retains its C7 local-interconnect
deferral; EPS and ATX remain explicitly interface-held. Canonical inputs remain
`build/additive-first-next-inputs-20260917.json`.

## Cause and generic correction

The guard combined final frozen pour polygons with the *earlier raster search*
corridors. Those corridors can extend beyond the final winning physical copper.
Consequently an empty, otherwise legal return-via location was reported as a
power collision. Denser via sampling could not fix that representation error.

`cec_power_guard_geometry.reservations` now retires only superseded, untyped
raster rows for exactly admitted, complete frozen domains. It still protects:

- Every exact frozen polygon and normal copper clearance.
- Search rows near any selected future bridge barrel, using the established
  bridge-reservation land/clearance convention; large explicit lands enlarge
  this test. This conservatively retains whole rows around future barrels.
- Explicit, unknown-purpose and other-net reservations.
- All original search rows for missing, failed or incomplete admission/via
  evidence. A truthy non-Boolean result does not authorize relaxation.

The function projects guards only. It never changes a source polygon, removes
copper, reseats a power via, changes current assumptions or relaxes native
manufacturing/clearance/locality rules. There are no board, refdes or coordinate
selectors in the implementation. Both search feedback and native admission
consume the shared projection.

The now-constructed C15 return uses a 1.305 mm qualified dogbone, with a
1.169 mm shared owner-ground link. Those measured lengths describe this native
witness; they are not new policy limits. Existing copper is exactly preserved.
The constructed cells are private diagnostics, not a completed routing stage.
Independent save/reload checks in
`build/exact-power-reservation-suite-20260919/independent-copper.json`
preserve every pre-existing copper UUID/geometry. The Hub diagnostic contains
77 added local-cell copper items and **zero** foreign trace/via incursions
against its 56 exact protected pour rectangles. PCIe2 and PCIe3 also retain
zero incursions. VHP's checker reports N/A for this particular authority
source; that is not claimed as a new pour-clearance proof for VHP.

## Investigations and qualification

The initial counterfactual omitted all future reservations only in GND-via
checks. It cleared both Hub refusals, but several proposed vias pierced actual
frozen power polygons. It is **not an admissible solution** and must never be
promoted: `build/return-reservation-dependency-20260919/report.json`.

A second private ablation retained exact polygons but omitted raster halos;
it showed one remaining refusal. The production correction additionally retains
whole raster rows near future bridge barrels and keeps unknown reservations.
Its complete six-board replay independently reproduces the one-refusal result.
Neither counterfactual script is part of the production pipeline.

After the guard correction, one new finer radial study was warranted by the
changed obstacle domain: `build/exact-return-refinement-20260919/report.json`.
It found an alternate return on an already-rescued terminal but did not rescue
the remaining output cell. The U7.4 compact domains each still reject all 480
sampled sites. No dense retry feature was integrated and this is not a no-path
proof. Do not repeat that unchanged study.

Validation: **340 tests pass, plus three subtests** in
`build/exact-power-reservation-wide-tests-20260919.log`. The focused 46-test
subset covers native saved/reloaded guards, real copper clearance, renamed and
rotated geometry, future barrels, large via lands, unknown reservations,
incomplete evidence, immutability and deterministic projection. It includes
older frozen-power, shared-return and local-PI reconciliation regressions.
The static generic-core audit passes; the wider historical inventory is not
declared fully generic or closed.

The bounded placement continuation completed in
`build/exact-reservation-placement-20260919-qualified/report.json`.
It generated 707 proposals, selected **16 previously untried poses**, and
accepted none under the full frozen-power/physical comparison. There were zero
revisits. No source or private input placement changed; no bus was moved.
The **latest Hub history now contains 174 poses**:

`build/exact-reservation-placement-20260919-qualified/hub-standard-rev2/board.placement-search.json`

The first private launcher lacked the Python multiprocessing main guard;
child startup failed before a qualifying batch. The corrected launcher is
the `-qualified` run above. It is the only completed placement batch here.
Shared production code was unchanged throughout that batch. All workers ended.

Next: constructive complete-cell surface access for the remaining fixed owner,
or an explicitly validated upstream placement/power transaction if that is
necessary. The failure is not an ordinary courtyard collision: overlaps and
native placement geometry are clean, but the owner ground landing is blocked
by actual frozen copper and neighboring package lands. The search certificate
correctly refuses to move that frozen owner. Do not waive that ownership, cut
approved power buses, widen the ground-return limit or repeat an unchanged
sampling campaign. No replacement board image is published for unchanged
placement geometry, and no full routing/fab result is implied.
