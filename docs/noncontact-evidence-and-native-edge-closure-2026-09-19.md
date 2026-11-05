# Scoped construction evidence and native edge-clearance repair — 2026-09-19

## Result and limits

A private current-input 12VHPWR candidate now passes the production placement
physical gate. Native pad-to-edge violations fall from **3 to 0**. All **506
existing copper items** and the entire remaining native board are unchanged.
Unconnected items remain **220**; C7 still requires the declared
`pre_route_local_interconnect` step. This is placement progress with partial
routing retained, **not full-board routing, thermal qualification or fab signoff**.

Source:
`build/qualified-escape-suite-20260915/12vhpwr-standard/02-placement/board.kicad_pcb`
(`3af185f38201c8f9e0b08a3f85204cc40b61e4998fe588b7d82902a3ce32293a`).

Verified output:
`build/noncontact-evidence-placement-20260919/12vhpwr-standard/board.kicad_pcb`
(`e9fd08b171747ac1eb3b6cb567036b4047218f29935410d876eedba465872323`).

The canonical input plan, source PCBs and schematic hierarchies are unchanged.
The output is not promoted. Its independent proof is
`build/noncontact-evidence-placement-20260919/12vhpwr-standard/independent-native-proof.json`.

## Generic fixes

The prior non-contact prototype retained native geometry but lost the scoped
construction reports required by the craft gate. It also spent its bounded
trial quota on small displacements that did not clear the native edge fault.
These were pipeline/evidence defects, not a reason to delete existing routes.

1. `cec_noncontact_placement` now binds `.cellreport.json` and `.railreport.json`
   to their source hashes, checks their board identity and counters, and freezes
   declared blueprint members and all report-dependent native members. Preserved
   nets and force-lane net owners participate. Unknown typed references refuse.
   The complete report, including negative observations, is retained with source,
   output and immutable-member provenance; only its board basename is rebound.
2. The production craft wrapper enables the strict non-contact fallback by
   default when reconstruction lacks complete copper ownership. Explicit
   `placement_noncontact_resume=false` retains the prior refusal path. This grants
   **no copper ownership or release authority**. Attached/locked/through-hole,
   zone-coupled or other unsupported moves still refuse; reconstruction and
   priority-repair ownership gates remain intact.
3. Edge-repair proposals try the largest bounded cardinal translations before
   finer and diagonal samples. Native screening requires an actual removed edge
   conflict and no new native pad conflict before the expensive craft trial.
   Missing evidence refuses. The screen cannot admit a board by itself; full
   craft, physical and frozen-copper checks remain required.

No board name, reference or coordinate selects these fixes. R1 and FB2 are
result witnesses: native evidence selected two 0.4-mm inward moves. Restoring
only their poses in an independent native reload reproduces the full original
native serialization. This covers all other footprints, copper, zones, outline
and graphics, beyond merely comparing copper counts.

Retention proves that scoped source observations are unchanged; it does not
newly validate every legacy construction claim. Full downstream admission is
still mandatory. No failed observation is rewritten as a success.

## Validation

- **371 focused tests pass**, final default-enabled run:
  `build/noncontact-evidence-tests-final-20260919.xml`.
- Six-board native replay:
  `build/noncontact-evidence-final-suite-20260919/report.json`. All source and
  hierarchy signatures remain unchanged. The canonical VHP row still reports
  its original three edge faults because this private repair was not promoted.
- Historical PCIe2 control: exact board hash, board-regression and probe parity.
  Its pre-existing wider release failure is not hidden or called newly passing.
- Source-bound report/native retention cohort:
  `build/noncontact-retention-cohort-20260919/report.json`. Hub, PCIe2 and PCIe3
  baseline copies are byte-identical; VHP additionally retains the full cell
  report with 55 immutable members. EPS/ATX correctly refuse at interface-ECO
  admission before any repair attempt. All sources and hierarchies are unchanged.
- Independent full KiCad DRC: edge faults 3→0 and opens 220→220. Every other
  raw type is unchanged: via diameter 8, hole clearance 4, annular width 8,
  silk overlap 199, silk over copper 199, library footprint issues 110 and
  silk edge clearance 20. Existing process qualifications are not requalified
  by this slice. High-speed pair result rows are unchanged, including existing
  incomplete routing.

## Review publication

[Verified diagnostic dashboard candidate](http://localhost:8090/?id=pass-20260919-noncontact-edge-repair-12vhpwr-standard-2feaf0c43f).

Archive:
`build/board-archive/pass-20260919-noncontact-edge-repair-12vhpwr-standard-2feaf0c43f/`.
Windows front/back mirrors:
`C:/Users/Admin/Documents/CEC-Board-Reviews/noncontact-edge-repair-20260919/12vhpwr-standard/`.

Both rendered sides were inspected. Windows localhost HTTP checks return 200
for the dashboard and both immutable PNG endpoints (66,537 and 52,651 bytes).
The gallery says **BLOCKED / NOT FAB SIGNOFF** because route/release admission
remains incomplete, even though placement admission passes. The publication is
a review adapter for the verified private output, not a completed pipeline run.
Its equal publication input/output hashes must not be confused with the repair's
different source/output hashes documented above.

## Continuation boundary

Do not rerun the cleared edge-repair batch. Next for this output is properly
rebinding it as an explicit next input, constructing the deferred local
interconnect, then priority routing under the existing ownership gates.
Keep `build/additive-first-next-inputs-20260917.json` unchanged until that handoff.
Keep the Hub's 174-pose history; it still has the previously recorded return
blocker. EPS/ATX remain held pending the owner's mating-span choice, not sent
through identical failed waves. See
[paired mating-row repair](paired-row-generation-repair-2026-09-19.md).

All validation workers completed; approximately 64 GiB remains free.
