# Hub fabrication readiness: field repair and thermal audit

Continuation: [Hub return closure and ATX power waves](hub-return-closure-and-atx-power-wave-2026-09-28.md)
records the newer `166b9b63d8` Hub checkpoint, which resolves the remaining
field interaction. This document retains its original artifact-bound thermal
and qualification evidence; do not treat its older route SHA as the latest.

## Disposition

**Not fabrication/release qualified.** Routing is closed, but routing closure
is not electrical, thermal, mechanical, or assembly qualification. No Gerber
release was approved and no fabrication order was placed.

Accepted parent: `4a5856a5eda920bf3d5778a661f3cd77d6ca5c5e277ddb7ab059f92b3a5a1730`,
`build/zero-open-coordinator-20260928-bg/route/winner.kicad_pcb`.

New independently admitted route checkpoint:
`4aba00e18b0646d662fdac54175382d16e8cdc8c70fd1c6634fbfabdc03f6a4e`,
`build/hub-fab-qualification-20260928/coordinator-field/winner.kicad_pcb`.
The parent and source authority families remain unchanged.

| Measured property | Parent | New checkpoint |
| --- | ---: | ---: |
| Unconnected | 0 | 0 |
| Qualified structural DRC | 0 | 0 |
| Field-coupling interactions failing policy | 2 | 1 |
| Vias | 196 | 196 |
| Routed length, mm | 2506.02 | 2506.41 |

All previously passed route-oracle gates are retained. Placement, population,
outline, project/rules, protected copper, power zones, protected fill and
qualified differential pairs passed independent preservation. The normal
coordinator reproduced the repair in **103.715 s**, including its own fresh
grading and admission. The isolated field actuator took **29.054 s**. A
separate boundary proof passed in **26.177 s**.

Independent release replay of this exact new SHA confirms **zero fabrication
geometry blockers** (including acid traps, slivers, islands and drill aspect),
zero structural DRC and zero opens. Its 50 electrical-constraint checks retain
one hard field-coupling finding; route-craft review is also not clear. Passing
the fabrication geometry subset does not override the remaining release gates.

Dashboard checkpoint (models off, front/back plus all six copper layers):
<http://localhost:8090/?id=20260928-hub-standard-rev2-checkpoint-continuation-4aba00e18b>.
The existing browser tab was navigated and visually checked for this exact
SHA and the `ROUTING COMPLETE / FAB QUALIFICATION PENDING` label. Windows
images are in `C:\Users\Admin\Documents\CEC-Board-Reviews\hub-fab-audit-4aba00e18b\`.

## Generic changes implemented

1. The shared field repair supports canonical 0/45/90-degree segments instead
   of refusing every diagonal. It preserves endpoint identity, net, width and
   layer; protected locked/grouped copper is refused before mutation.
2. Cross-layer repair schedules the existing anchored perpendicular-departure
   primitive, tries both geometric movement roles, and bounds local offsets
   and alternate participant trials. Electrical aggressor/victim roles are
   not changed to make a trial pass. All executable board-family sidecars are
   retained. Public repair accepts only 1–16 rounds and finite bounded margins.
3. `cec_synth_pipeline._oracle_field_coupling` uses the same serialized-copper
   checker as independent electrical release review. It now participates in
   the complete route conjunction, reasons, and blocker provenance. Missing,
   invalid, contradictory or failed checker evidence fails closed.
4. `cec_search_policy` compares per-gate defect counts as well as Boolean
   gates. A still-failing gate cannot regress from one defect to two in exchange
   for a shorter route. Lost existing gates still prohibit admission.
5. `cec_route_field_finish` integrates this into the normal coordinator for
   zero-open/zero-structural-DRC candidates with measured field defects. It
   uses private board families, one round by default, a 90-second owned-process
   budget, campaign finish reserves, and the existing independent final
   admission/rollback. Timeout or partial output cannot replace the parent.
6. `cec_courtyard_edge` provides bounded proposals using actual native
   courtyards and the closed laminate including cutouts. It has no board,
   reference or coordinate special case. **It is only a proposal producer,
   not yet a joint-placement actuator in normal coordination.**
7. `cec_thermal_contract` binds mux loss current to explicit source/sink
   transport envelopes: minimum of the largest mutually exclusive input and
   the single output. Serial stages are not added. Missing/ambiguous topology
   and understated explicit heat-current parameters fail closed.
8. Thermal diagnostics no longer truncate the legacy detail mask to four
   copper layers. Render summaries use the same injection-completeness verdict
   as the image and explicitly deny component-temperature qualification.

The five new/extended neutral modules are registered in
`cec_generalization_gate`. Synthetic tests use renamed parts/nets, translated
coordinates, all octilinear headings, boundary cutouts, lost/invalid evidence,
protected copper, partial worker failure and cross-gate tradeoffs. This does
not claim the repository's older runtime-wide generalization debt is closed.

## Outstanding physical/electrical findings

### One field interaction remains

`/TEMP_HUB` on B.Cu crosses `/CAN_TX` on F.Cu at 45 degrees near a plane
clearance opening. The checker reports 75% filled intermediate-GND coverage,
not the required continuous shielding. This is **not** an ordinary same-layer
copper short. The first, long parallel interaction was eliminated.

Bounded small offsets, perpendicular-departure and relayer trials were tried.
The otherwise attractive front-layer trial introduced three structural DRC
violations; other trials either failed geometry or touched protected copper.
None was adopted. The next useful actuator is a longer unlocked victim-chain
reroute around that opening, not more identical short-segment offsets or a
waiver of the protected CAN prefix.

### Capacitor edge is coupled to the mating assembly

C37's courtyard-edge gap is **0.475 mm**, against the **0.8 mm** rule. Moving
it inward by 0.35 mm fixes the edge gap but introduces two courtyard overlaps
(D8 and R_ILIM2) and leaves its vent projection outside the existing native
guard on the paired ATX board. The 0.40 and 0.45 mm proposals also fail.
All trials were refused; neither source placement nor the paired carrier was
silently modified. This requires coordinated support-component placement,
connected-copper repair, and a newly hash-bound Hub/ATX vent-guard pair.

The existing `docs/hub-atx-stack-qualification-status.json` still says
`PROTOTYPE_BLOCKED`. Declared envelope checks are not supplier-tolerance,
plug/latch swept-volume, cold/aged capacitor/startup, or assembled-sample
qualification. No physical sample measurements were invented.

Four covered-backtrack craft advisories and one detour also remain visible;
protected power geometry was not deleted to reduce cosmetic counts.

## Thermal screening, not package signoff

The fresh **0.15 mm mesh** screen on the unchanged 4a5856 parent included every
requested transport net (none dropped/absent), all six declared copper layers,
the profile dielectric spacings, explicit component heat, natural convection
and radiation. It took **271.588 s** and reported **127.392 °C maximum board
temperature at 50 °C ambient**, a **77.392 °C rise**. The current screen fails
the 30 °C rise criterion. Discrete heat was 3.304781 W and copper Joule heat
0.605065 W. This thermal result is **not rebound to the new route SHA**.

The old model silently used 1 A and typical on-resistance for both muxes.
The new role/topology binding derives U7 = 2.5 A and U11 = 1.1 A from the
existing design envelopes. It does not add USB and KVM current or increase the
shared 2.5 A source decision. The new sensitivity uses the TPS2121 table's
100 mΩ maximum at -40…125 °C with VIN >= 5 V, plus maximum quiescent/standby
currents; these conditions matter. [TI TPS2121 datasheet, table 6.5, p. 7](https://www.ti.com/lit/ds/symlink/tps2121.pdf).
The local source is `lib/datasheets/TPS2121RUXR.pdf`, visually checked.

Important limits:

- The model combines independent per-component/transport maxima. It does not
  yet prove a coherent simultaneous operating case for the cascaded mutually
  exclusive supplies. **127.392 °C is a screening result, not a measured or
  guaranteed real operating temperature.** Consistent primary/USB/KVM cases
  must precede choosing a hardware cooling redesign.
- The table's resistance guarantee does not cover every sub-5-V operating
  condition, and the modeled peak exceeds its 125 °C table range. It cannot be
  advertised as a qualified worst-case bound across all supply/temperature corners.
- PCB field temperature is not package/junction temperature. Sources remain
  explicitly unverified; U6/U8 heat and passive/connector losses need complete
  qualification. No new fan or case-cooling credit was assumed.
- Existing wired-MCU/load decisions and the single 20% operating budget margin
  were retained. LED assumptions were not reduced to make the solve pass.
- `thermal-bound/` is superseded: it incorrectly applied 2.5 A to U11 as well.
  Do not cite its 142 °C result. `thermal-screen/` and `thermal-fine/` used the
  old 1-A mux loss; they are comparisons, not current signoff. The coarse
  0.3-mm run dropped VCC_P2; the 0.15-mm run resolves that mesh omission.
- The private legacy detail PNG predates the all-layer mask correction. Do not
  publish it as a verified all-six-layer thermal visualization. New route
  dashboard panels are native copper exports, not this diagnostic PNG.

## Cross-board control and evidence

Preserved PCIe two-port v103 remains byte-identical at SHA
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
Its independent replay remains **0 opens, 0 structural DRC, 0 fabrication
geometry blockers**. A normal coordinator replay took 74.457 s, retained
0/0 and field count 0, preserved passed gates, and skipped field repair as
inapplicable. Existing general finishing selected a private 1199.66-mm,
197-via variant; the archived control was not replaced.

The **full** release replay of that unchanged control is not green: current
checks flag RS1's Kelvin departure direction and CAN pair adjacent-GND
coverage at 80% versus 95%. These are distinct from this slice's structural
regression result. Runtime-wide legacy generalization findings also remain.
Do not describe this as complete suite fabrication qualification.

Evidence root: `build/hub-fab-qualification-20260928/`.

- `release-replay.json` / `release-replay-final.json`: independent parent/new
  manufacturing, constraint, route-quality and generalization reports.
- `coordinator-field/oracle.json`, `native-control.json`, `field-finish/`:
  normal automatic actuation, budgets, fresh grading and selection.
- `coordinator-boundary.json`: independent placement/power/pair/fill proof.
- `edge/evidence.json`: failed isolated capacitor relocations.
- `thermal-source-bound-fine/evidence.json`: current heat inventory, transport
  binding, mesh, temperatures, geometry provenance and source SHA.
- `pcie2-control.json`, `pcie2-coordinator/`: cross-board replays.
- `final-focused-tests.log`, `generalization-tests.log`, `generalization.json`:
  final test/audit receipts. Earlier overlapping test counts are not additive.

Final focused suite: **290 passed, 4 skipped, 2 subtests passed** in 157.44 s.
The four skips are opt-in minute-scale real-router fixtures; the normal Hub and
PCIe coordinator replays above were actually executed. The separate
generalization suite passed **9 tests**. Declared generic-core audit has zero
violations; the full runtime still reports **378 legacy findings** and correctly
keeps `release_ok=false`. Scoped `git diff --check` passed.

No unattended zero-open routing loop was started. The next work is the
remaining field chain, coordinated capacitor/vent relocation, coherent
operating-case thermal qualification and physical assembly evidence—not more
blind routing seeds or relaxed acceptance limits.
