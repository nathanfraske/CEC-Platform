# Compact local ground dogbones and native SMD-layer handling

## Changes

The local-ground constructor previously tried a filled/capped via at the land
centre, then only an ordinary through-via dogbone of at least 0.60 / 0.30 mm.
This omitted an already-supported fabrication domain: a compact, filled/capped
via joined by a short same-layer track to its actual SMD owner. The existing
`local_pofv_via_decision`, exact generated-object ownership group and independent
netclass/fabrication signoff already support this geometry.

`cec_decoupler_cell` now tries the declared preferred and permitted process-floor
local geometries before ordinary dogbones. An explicit geometry request remains
exact rather than silently selecting a smaller one. No filename-derived profile
hint can authorize an off-pad process exception. Geometry is bounded to the
existing 1.50 mm local topology limit, four radii and eight octilinear headings
per geometry/width. Existing class-width-first and independently qualified
pad-neckdown rules remain unchanged. This is not a new load-current budget or
permission to shrink plane stitching or load-bearing power vias.

Every trial retains native foreign-copper, pad-overlap, hole-spacing, board-edge,
pair-overlap and future-power reservation checks. Partial pad overlaps are still
forbidden. The constructor re-proves the actual newly added via and track before
accepting them; a failed or exceptional proof destroys those trial objects.
File-stage wrappers continue to own/re-prove exact generated POFV UUIDs and write
only their scoped rule. A copied ownership group without the real local track
does not qualify after reload.

Native back-side tests exposed a separate layer bug: `PAD.GetLayer()` can return
F.Cu for a B.Cu-only SMD land, including on a B.Cu footprint. Both compact and
ordinary ground dogbones now derive a unique SMD copper layer from the native
layer set. This prevents a geometrically plausible but electrically disconnected
stub on the opposite surface. Multilayer-terminal handling is not guessed.

Compact rejection seats are retained in diagnostic evidence and consumed by
`cec_local_return_feedback`. Placement can propose rigid, smaller-envelope exits
from the unchanged power reservation instead of seeing only the old large-via
failure. A blocked lead, incomplete search, stale placement or missing authority
does not become an accepted route. All proposed poses still need full native
requalification; existing power copper/reservations are not moved or waived.

## Validation

**332 tests pass in 13.45 s** in the selected regression suites, including 14 new
compact-ground tests and two new placement-feedback tests. Coverage includes
loaded native objects, both outer layers, renamed/translated/rotated terminals,
preferred/floor domains, exact geometry requests, missing process declarations,
stale ownership after removing the local track, rejected current neckdowns,
locked foreign copper, unmaterialized power reservations and exception cleanup.
Evidence: `build/compact-ground-final-tests-20260917.log`.

The first concurrent native cohort is complete:
`build/compact-ground-suite-20260917/report.json`.

- All six canonical PCB/source hierarchies are unchanged. PCIe2, PCIe3 and VHP
  retain their physical passes; Hub retains three craft blockers. EPS and ATX
  remain interface-ECO holds, not physically admitted.
- Historical PCIe2 board/hash/probe parity passes. The generic core passes;
  legacy debt remains 23 physical / 380 runtime findings and release is false.
- Isolated native ground-geometry probes find compact dogbones on all six narrow
  Hub mux ground lands, one PCIe3 mux ground land, and two VHP lands. PCIe2's three
  narrow mux ground lands are already covered. Some other terminals still refuse
  or use ordinary returns. All trials were rolled back exactly; no PCB was saved
  or promoted as a candidate by these probes.

**These isolated successes are not complete-cell or board admission.** The full
Hub craft probe also activates hash-bound future-power reservations. Those still
block the otherwise legal compact returns for the two mux cells. In particular,
the retained native certificates identify In3.Cu +5VSB reservations, not a reason
to waive ground-pad containment or to increase the board size. The third Hub
blocker remains the regulator input capacitor's tangent-distance requirement.

The bounded placement-frontier cohort completed under
`build/compact-ground-frontier-20260917`: 16 previously unvisited proposals, one
round, 30 legal evaluated variants, no accepted improvement, 171.433 seconds.
The explicit one-round budget stopped the search; this is not a proof of global
infeasibility. Hub retains its three craft blockers. Its exact frozen copper,
qualified pairs, PCB bytes and source hierarchy are unchanged. Other-family
physical checks and historical control parity pass; EPS/ATX remain held. The
visited-pose history now includes this batch. Do not repeat the same domain.
This was not a full-route pass; no new board or preview was promoted.

## Unchanged authority and next work

Keep `build/additive-first-next-inputs-20260917.json` authoritative until a new
artifact actually passes continuation admission. Do not rerun the exhausted
PCIe2 five-open additive domain or PCIe3 pair-order domain unchanged. EPS/ATX
still need a coupled main/daughterboard geometry revision within the fixed span;
same-depth pitch failure is not proof that every staggered geometry is impossible.
No qualified lands, dimensions, mating transforms, current budgets or schematics
were changed here. No board is newly fab-approved.
