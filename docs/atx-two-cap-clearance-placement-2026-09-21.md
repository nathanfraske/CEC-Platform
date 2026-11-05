# ATX opposing-capacitor clearance placement — 2026-09-21

## Result

**2026-09-22 assembly follow-up:** the two planar capacitor reservations remain
clear, but the paired assembly is blocked by contact-registration and access
failures plus unqualified production tolerances. See the
[vent/tolerance/mating audit](hub-atx-vent-tolerance-mating-audit-2026-09-22.md).
The zero single-board placement count below is not an assembled-fit pass.

The owner accepted the two conventional Hub reservoir capacitors and requested
ATX placements with ample clearance. A separate **82 × 95 mm ATX placement
candidate** now clears both projected capacitor reservations, with **no outline
growth**. The retained source boards and active schematics/BOMs are unchanged.

![ATX clearance placement comparison](../build/atx-two-cap-clearance-20260921/comparison.png)

Gold areas are capacitor reservations, including the selected 1.2 mm lateral
guard; cyan components belong to relocated groups; gray components are fixed.
These are courtyard/body views, **not routed-board renders**.

## Exact authority and scope

Inputs are the hash-bound retained pair in
`build/ordinary-relief-next-inputs-20260920.json` and the accepted study in
`build/hub-two-cap-fit-20260921/fit-result.json`:

- ATX: `build/native-assembly-placement-pass-20260920/atx-24pin-rev3/02-placement/board.kicad_pcb`,
  SHA256 `cb851d4dd9c7418e53ee316c26e7fac4fbd99cb8b55bfa8f77c89b249e807773`.
- Hub: `build/bound-return-hub-pass-20260916/hub-standard-rev2/02-placement/board.kicad_pcb`,
  SHA256 `de0e0e81c87b13824a43b336b068c17d85392eedbcef3fb15d105d0fbd66f98f`.

The proposed Hub capacitors are two Lelon VZH472M1CTR-1816 / C249940, 4700 uF,
16 V, on the isolated hold-up reservoir. They are still a pending schematic/BOM
ECO, not parts already present on the retained native Hub. The supercap remains
rejected on cost. No power-budget, shutdown-detection or firmware-load assumption
was changed by this placement study.

## Reserved geometry

The existing assembly datum fit projects Hub to ATX coordinates as
`x_ATX = 86 - x_Hub`, `y_ATX = y_Hub + 9.8`.
The conservative 23.2 × 20.2 mm cap land/body reservation is enlarged by
**1.2 mm on every side** on the opposing ATX. This is a chosen lateral assembly
guard, not a manufacturer-specified vent clearance.

| ATX reserved area | X bounds, mm | Y bounds, mm | Initial obstructing footprints | After |
| --- | --- | --- | --- | --- |
| Hub cap A | 37.10–62.70 | 59.10–81.70 | 13 | 0 |
| Hub cap B | 1.35–23.95 | 37.60–63.20 | 23 | 0 |

All opposing front-side components are excluded from these entire rectangles;
the study does not assume that an unknown-height component is short enough to
sit under a capacitor. Native KiCad front-side **footprint-only rule areas**
are written into the candidate. They do not prohibit traces, vias or copper
pours. This does not yet prove every automatic placer consumes these rule areas;
the active production policy has not been changed to this provisional stack.

With the previously proposed **22 mm nominal board separation** and **17 mm
maximum capacitor body height**, nominal cap-to-bare-ATX clearance is 5 mm.
This subtraction excludes seating, board bow, standoff and assembly tolerances;
it is **not a guaranteed minimum or vent qualification**.

## Placement changes and preservation

The bounded search relocates 42 footprints in seven functional groups: MCU and
local controls, LDO/input-output decouplers, standby mux and its local parts,
USB bulk pair, standby bulk cap, CAN transceiver/decouplers/bypass pair, and the
12 V current-sense IC/decoupler. Six groups translate; the current-sense group
rotates rigidly by 90 degrees in the planar coordinate system. Group-local pad
distances and decoupler geometry are preserved, not independently optimized.

All connectors, mounting holes, shunts and original copper/rule-zone boundaries
are unchanged. Moved components are also kept out of the mirrored Hub RJ45
courtyards with the same lateral guard. Existing RJ45/ATX overlap debt elsewhere
is not declared solved. The MCU's physical antenna body from the vendor footprint
is included: its native placement courtyard omits that overhang. The copper pad
positions agree with the vendor footprint; this was not evidence of a scaled or
wrong MCU pad pattern. This witness moves the MCU inward; wireless/antenna-edge
performance is not qualified, and the existing wired-only load assumption is
unchanged.

The 12 V sense connection demand rays remain uncrossed. Their exact same-net
pad distances change from 3.479/5.438 mm to 7.774/2.476 mm, both inside the
existing 9 mm Kelvin constructor range. That establishes placement reach only,
not completed Kelvin routes or equal electrical performance.

## Verification and output

- Both reserved rectangles: **zero footprint intersections** after placement.
- Native placement DRC: **0 before, 0 after, 0 introduced**, covering courtyard/
  THT assembly, pad-to-pad copper and pad-to-edge checks. This is not full routed
  DRC, electrical or fabrication signoff.
- Every footprint, pad number and net is preserved; exported/read-back pad
  transforms agree within the 0.000003 mm test tolerance.
- Both footprint keepouts and their bounds survive native save/read-back.
- Existing zone outlines/layers/nets are identical. Retained source hashes and
  hierarchy signatures remain unchanged.
- 25 owner/decoupler relationships were checked for group preservation.
  Existing decoupling/craft debt is not silently marked fixed by a rigid move.

Candidate:
`build/atx-two-cap-clearance-20260921/ATX-two-cap-clearance-PLACEMENT-ONLY.kicad_pcb`.
Its 96 inherited track/via objects are intentionally omitted and zone fills
cleared **only in this disposable placement preview**, so stale routes are not
misrepresented as following moved pads. They remain recoverable in the untouched
retained source. The candidate is not registered as a routed/fab-review winner.

Receipts: `fit-result.json`, `native-placement-validation.json` beside the board.
Reproduce with `.venv/bin/python tmp/atx_cap_clearance_20260921.py`, then
`.venv/bin/python tmp/atx_cap_clearance_native_20260921.py` in WSL. Native CLI
checks use 10-second timeouts. The separate export worker retains detached
native track proxies through export to avoid the observed local SWIG teardown.

## Remaining release gates

This is a bounded mechanical placement witness, not a new generic production
placement stage or a claim of cross-board routing improvement. Functional group
membership is explicit study input; placement coordinates are search outputs.

Before promoting it: finalize the Hub two-cap footprint/schematic/BOM ECO and
startup/inrush change; resolve mezzanine same-pin alignment and insertion/gap
tolerances; qualify cap vent and worst-case vertical clearance; preserve the
reservations in automatic placement admission; then reroute and run the full
electrical, native DRC, thermal and assembly checks. The present origin-based
mirror fit does not waive previously found connector pin-registration errors.
