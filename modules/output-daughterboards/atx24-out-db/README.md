# 24-pin ATX output daughterboard — BETA-1

Passive connector-daughterboard for the 24-pin ATX module's OUTPUT side, per
spec **§2.8 v1.4.0** (`CEC-Platform-Ground-Truth-Spec.md`) and the owner
ruling `docs/standard-tier-review/SYNTHESIS-beta-plan.md` §D-5a. Mates with
the main board's `TB1`–`TB9` Keystone 3586 universal blade clips (already
built, `modules/atx-24pin-rev3`, commit `b76a62a`) and reproduces the full
24-circuit ATX output pin map for a bare pigtail or a future MODDIY-class
vertical header. **No active or passive components** — connector bodies and
fan-out copper only, per the ratified "no components beyond the connector
body and its fan-out copper" text.

DRAFT (no fab yet — the OQ-86 physical fit-check sample gate is still open).

## Posture — STANDS PERPENDICULAR to the main board (owner ruling, 2026-07-05)

This board is a small vertical card, not a parallel mezzanine (an earlier
framing this pass corrected). It stands up off the main board on edge; the
TE 63849-1 tabs mount near its **bottom (near) edge** with their blades
pointing straight out of the board face — i.e. **horizontal** once the board
is standing — engaging the main-board Keystone 3586 clips via **side entry**
(the clip's spring jaw takes the blade from the top or the side; owner
ruling, universal-clip datasheet). The output field sits above the tab row;
the 2×5 signal header sits beside the field, rotated 90° so it costs no
extra board height.

**Board axes**: X = length, parallel to the main board once installed (the
FREE dimension — minimized opportunistically, no ceiling). Y = height, the
board's own vertical extent standing up off the main board — the **ruled
cap, ≤15 mm "or so"** (owner, 2026-07-05).

**Measured final size** (`pcbnew.GetBoardEdgesBoundingBox`): **81.2 × 16.6 mm**
(length × height). Height is inside the owner's practical range for this
tier ("≤15–17 mm tall", given how many interleaved rails this board carries
— see "Layer stack / routing" below); length runs a little over the owner's
own rough single-face guess of ~75 mm (see "Dual-face tabs" below for why —
that guess assumed a benefit dual-face does not actually deliver for this
specific part, so single-face, slightly longer, is what is built).

**Mating height**: tab-row centreline sits **1.94 mm** above this board's own
near/bottom edge (0.4 mm edge margin + half the TE tab's 3.08 mm courtyard
height). Read as "blade centreline height above the main board surface"
*if* this board's near edge sits flush at that surface (zero standoff) — the
real number depends on the chassis/strain-relief interface, which is still
OQ-87's to spec. This board's own contribution to that number is fixed and
documented here as the reference point.

## Mounting / retention — no mounting holes (owner directive, 2026-07-05)

Earlier drafts of this pass carried 4× M3 corner mounts; the owner cut them:
*"they don't need a ton of mounting holes either... that can probably go
away."* Retention is instead:
1. The Keystone 3586 clip's own **high insertion force** — a deliberate
   **feature**, not a shortfall, per the owner's 2026-07-04 ruling on this
   connector family: these joints are not meant for casual swapping, and
   mis-seat/pull-out (which hardware would be there to prevent) is exactly
   the failure a stiff joint rejects.
2. **Chassis strain relief** on the cable/assembly side (spec §2.8 v1.4.0);
   OQ-87 still owns the numeric pull-force/flex-cycle spec for that
   interface.
No footprint or BOM line changed because of this — mounts were never a
schematic/BOM part on this generator (PCB-only mechanical footprints), so
removing them only touched the PCB placement code.

## Tab map (9 joints, TE 63849-1 / LCSC C86469)

| Ref | Net | ATX pins bundled | Matches main-board clip |
|---|---|---|---|
| J10 | +12V | 10, 11 | TB1 |
| J11 | +5V | (shares +5V net with J12) | TB2 |
| J12 | +5V | 4, 6, 21, 22, 23 | TB3 |
| J13 | +3V3 | 1, 2, 12, 13 | TB4 |
| J14 | +5VSB | 9 | TB5 |
| J15–J18 | GND | 3, 5, 7, 15, 17, 18, 19, 24 | TB6–TB9 |

Joint count and per-rail split (12V×1, 5V×2, 3.3V×1, 5VSB×1, GND×4) are the
spec-ratified §2.8 v1.4.0 numbers, and the tab ORDER (12V, 5V, 5V, 3.3V,
5VSB, GND×4) matches the already-built main board's `TB1`–`TB9` net sequence
1:1 — verified against `modules/atx-24pin-rev3/README.md`.

## Signal header (J20, 2×5 2.54 mm, `cec:CEC_CONN_2x5`)

Pin order matches the main board's `J_SIG` (same commit) exactly, so a
mating cable/header is not left to guess a 1↔2 swap:

| Pin | Net | Note |
|---|---|---|
| 1 | PS_ON# | |
| 2 | PWR_OK | |
| 3 | −12V | |
| 4 | GND | local reference |
| 5–10 | reserved | no-connect; sense-return provision (OQ-88), unpopulated |

No 5VSB-sense/remote-sense net exists on the main board's signal set today
(verified against the current netlist per that board's own README), so none
is carried here either.

## Output field (J1, `cec-Connector_Generic:ATX24_Daughterboard_Field_P4.20mm`)

Bare THT solder field, 24 positions, 2×12 @ 4.20 mm pitch / 5.5 mm row —
geometry measured off the vendored, verified Molex Mini-Fit Jr 5569-24A1
land (`lib/vendor/Connector_Molex.pretty`), same pitch family the study's §4
recommends for exactly this field. Reuses the platform's own `cec:CEC_ATX_24`
symbol (same pin names/map as J3 on the 24-pin module) so the electrical
identity is inherited verbatim; only the footprint differs — a bare pad
field, no male-header shroud. 20 of the 24 positions are power-class (1.8 mm
drill / 2.7×3.7 mm oval, the real Molex land, 16 AWG-class); the 4 non-power
ATX circuits (pin 8 PWR_OK, pin 14 −12V, pin 16 PS_ON#, pin 20 NC/reserved)
are downsized to 1.4 mm drill / 2.6 mm round (18 AWG-class, matching the TE
tab's own leg size).

**Population options** (same field serves all three, per the study §4 "one
field, two/three uses"):
1. **Bare pigtail** (default) — hand-solder 16 AWG (power) / 18 AWG (signal)
   wire directly into the field.
2. **MODDIY-class vertical female header** — dimensionally compatible
   (4.20 mm pitch, same "Molex 5557/5559 family" pitch the part claims), but
   **NOT placed here**: no MODDIY footprint is vendored in this library (no
   manufacturer name / MPN / datasheet — OQ-88's provenance gap), so nothing
   is invented. On the standing-board posture the header's own pins point
   horizontally (same direction as the tabs), so — unlike an earlier,
   since-corrected concern about a parallel-mezzanine framing — there is no
   height-budget conflict with a vertical header option here; population
   stays an owner decision pending the physical fit check (OQ-86/88).
3. **Sellable daughterboard-plus-extension assembly** — same holes, wire
   soldered in with a chassis-anchored strain-relief bar, terminating in a
   standard female housing (OQ-89, SKU TBD). Wire dress runs parallel to the
   main board (the natural consequence of the field's pins exiting
   perpendicular to a *standing* board — i.e. horizontally).

## Keying

**Single row of 9 tabs at 8.9 mm pitch** (mm centre-to-centre), net order
unchanged from the original design (12V, 5V, 5V, 3.3V, 5VSB, GND×4) — see
the tab map above. The pitch clears a measured floor: the TE 63849-1's own
courtyard is exactly 7.92 mm wide
(`cec-Connector_Blade:TE_63849-1_FASTON_Tab_250x032_THT`, matching the TE
datasheet's 7.92 mm shoulder-flange dimension to the micron), so 8.9 mm
leaves 0.98 mm of real clearance between adjacent tab bodies.

**The real safety property is proved, not assumed.**
`scripts/check_output_daughterboards.py` computes every family's tab-centre
list from its own `pcb_placement()` (the exact coordinates on the committed
board) and, for every ORDERED pair of families, searches all 4 rotations
(0/90/180/270°) × every candidate translation for a rigid mapping that seats
one family's whole tab set onto a subset of another's, within 0.5 mm
(bipartite exact-match, not a coincidence heuristic) — see that script for
the algorithm. All 6 ordered pairs come back "cannot seat." An earlier
attempt at this board's pitch (8.6 mm) plus EPS's original 8.3 mm and
PCIe's 8.2 mm PASSED the joint-count/pitch checks but MEASURABLY FAILED this
proof (PCIe's 4 tabs seated within the 0.5 mm tolerance as a subset of EPS's
6-tab grid, because a 0.1 mm/step pitch difference over only 3 gaps
accumulates to just 0.15 mm at the worst point) — corrected by widening the
per-family pitch deltas until every pair clears (G/2)×Δpitch > 0.5 mm at G =
the smaller family's own gap count (its own tab count − 1); see
`scripts/gen-output-daughterboard.py`'s `TAB_PITCH` comment for the exact
math. **This daughterboard's tab grid is the authoritative main-board
mating drawing** — the main board carries no clips yet, so the (separate)
main-board layout mirrors these exact positions.

**Dual-face tabs (evaluated, REJECTED)**: putting tabs on both faces
(blades pointing opposite directions, halving the apparent row length —
the owner's initial framing assumed roughly 75→38 mm for this board) does
NOT work for the TE 63849-1 as vendored. Its copper PADS already span
7.58 mm inside the 7.92 mm courtyard (only 0.17 mm of margin per side), so
the pitch floor is governed by pad-to-pad copper clearance almost as much
as by the courtyard — and copper clearance does not care which face a
through-hole tab's body sits against, because the DRILLED HOLES exist
through the whole board either way. Minimum safe pitch cross-face
(pad-edge-to-pad-edge, ~0.3 mm clearance) works out to ~7.9 mm vs the
~8.9 mm used here same-face — a ~11% saving, not the ~50% the "halve it"
framing assumed. Single-face, single-row is what is built.

## Layer stack / routing

**4-layer** (F.Cu / In1.Cu / In2.Cu / B.Cu, 2 oz outer / 1 oz inner — the
platform's own interposer convention). GND floods **In1.Cu alone**, a
single full-board plane (the largest, most-scattered net). Of the
remaining 7 nets, only **4 are real multi-point busses** — +12V, +5V, +3V3,
+5VSB (several field pins, one or two tabs each) — and only THOSE get a
lane. The other 3 (−12V, PWR_OK, PS_ON#) are a plain 2-terminal net apiece
(exactly one field pin to the matching `J20` header pin, no tab at all,
netlist-verified), so they route as direct point-to-point tracks with no
lane at all. That split is what makes a ≤17 mm-class board height possible
with this many interleaved rails — see the two design notes below.

**The 4 BUS lanes live in a short CORRIDOR** between the field's bottom row
and the tab row, on **In2.Cu only** — 4 thin zones (0.3 mm wide, 0.65 mm
pitch) stacked in the ~2.25 mm gap between the field (which dominates the
board's own height) and the tab row. Each bus field-pin runs a 0.5 mm F.Cu
stub down to its own lane + a 0.3/0.5 mm via (smaller than this platform's
usual 0.5/0.9 mm power via — the 0.65 mm slot pitch cannot safely hold a
0.9 mm-diameter via without adjacent slots' vias physically overlapping);
each tab bridges its TE 63849-1's two physical pads (numbered "1" but with
no internal copper between them in the footprint) then stubs up into its
own lane the same way.

**DESIGN NOTE — a two-layer lane split does NOT help here, though it looks
like it should** (a first pass built one, then reverted it once DRC caught
the result). Splitting the 4 (or originally, all 7) lanes across In2.Cu
*and* B.Cu, thinking two layers halve the stack depth, is unsafe for a
zone this thin: a via is a THROUGH feature, so a B.Cu-target via also
crosses In2.Cu at that (x,y), and KiCad's `ZONE_FILLER` auto-clears
(anti-pads) it there — normally harmless (exactly how a signal via safely
crosses a GND plane everywhere on this platform) *only* because a plane is
wide in both directions and copper can route around the hole. A 0.3 mm-tall
lane has no "around": a via whose keepout diameter (~0.9 mm here) exceeds
the lane's own height clears its FULL height at that one X, severing it
into two islands — measured as a real `unconnected_items` DRC hit between
two ends of what should obviously be one zone. Offsetting the two layers'
Y by half a pitch does not fix it either: the safe stand-off a via needs
from a foreign-LAYER lane it merely passes near
(`via_keepout_radius + lane_half_height + min_width`, ≈0.8 mm here) is the
same separation the lanes already need from EACH OTHER on one layer — two
layers buy nothing once every slot carries a via. The actual fix was fewer
lanes (drop the 3 point-to-point signals out of the scheme entirely), not
more layers.

**The 3 point-to-point signals (−12V/PWR_OK/PS_ON#) route on B.Cu**,
deliberately NOT F.Cu: the bus field-pins' dodge-then-descend stubs (below)
are on F.Cu and physically transit this same row-gap band on their way to
the corridor, at up to 12 different X's, so putting the point-to-point
runs on the otherwise-empty B.Cu avoids that whole family of crossings in
one move. No via is needed at either end (both the field pins and the
header pins are through-hole). The three runs still share one layer with
each other, so each gets its own dedicated Y inside the field's row-gap
(0.42 mm steps, a 0.2 mm track — thinner than the platform-default 0.4 mm,
because the safe row-gap window is only ~1.1 mm wide once the 0.25 mm
GND-class clearance and each pad's own 1.85 mm half-height are accounted
for), assigned by which row each signal approaches from so no two runs'
occupied (X, Y) actually coincide — worked out and commented in
`route_atx24()`, `scripts/gen-output-daughterboard.py`.

**Row-conflict fan-out rule** (why some bus field-pin stubs jog sideways):
the real ATX-24 pinout puts row0 (pins 1–12) and row1 (pins 13–24) on the
*same* 12 X-columns, so a straight vertical stub from a row0 pin can run
directly into a *different-net* row1 pad below it. Fixed by a **permanent
+2.1 mm (half the 4.20 mm pitch) sideways offset** on exactly the row0 pins
whose column-mate differs — landing dead-centre in the gap between two
adjacent pad columns (~0.75 mm clear of both neighbours) — taken for the
pin's *entire* descent (never jogged back), which also keeps every column's
own stub on a unique X for its whole length. Row1 pins and same-net columns
route straight down natively.

Field-pin currents here are modest (24-pin design basis: 6 A/circuit, ATX
bar) — 0.5 mm 2 oz stub tracks are comfortably inside that per-pin figure;
the per-rail AGGREGATE current (up to ~30 A on the 5V rail, per the study's
§1 margin table) is what the **9 blade-clip joints on the main board** are
sized for, not this daughterboard's own individual per-pin fan-out traces.
Verified DRC-clean (see below).

## Electrothermal sanity — PENDING (W-item, not wired this pass)

The repo's `cec_synth_pipeline.physics.electrothermal_solve` (IPC-2221 Picard
solver) is not parametrized for this board's "per-pin stub + thin lane"
topology; wiring it up is not cheap within this pass's scope. Hand sanity
only: 0.5 mm/2 oz external-layer traces at a 10 °C rise carry roughly 2–3 A
by the standard IPC-2221 external-trace curve — comfortably above the
~6 A/circuit-shared, sub-amp-per-stub currents these individual field-pin
fan-out traces actually see (the real per-rail current rides the 9 blade
joints, sized separately per the study). Flagged as a **pending W-item**:
run the real solver once it is generalized to this topology, before treating
this board as production-ready.

## Sense-return provision

Per spec §2.8 v1.4.0 / OQ-88: a zero-component sense-return contact (a
downstream voltage tap per sensed rail, feeding a main-board resistor divider
and spare ADC — mirrors Hub Standard's `MAIN_5V_SENSE`/`5VSB_SENSE` pattern)
is a candidate designed-in monitor for this joint's fretting-corrosion
wear-out mode. **Not decided** whether it ships, when, or at what
granularity — this board **provisions** for it only: 6 of the J20 header's
10 positions are reserved/no-connect, physically available for a future
sense-return tap without a board respin. No components are added here.

## Verification (this pass — 2026-07-05 floorplan rework)

- ERC: 0 errors (5 benign `lib_symbol_mismatch` warnings, the same
  documented-benign class every generated schematic in this repo produces).
- Static connectivity audit (`scripts/audit-sch.py`): clean.
- DRC: **0 violations at error severity, 0 unconnected** (`kicad-cli pcb drc
  --severity-error`, and every `unconnected_items` slot is empty — the real
  gate this project's `check_output_daughterboards.py` enforces). At full
  (all-severity) verbosity there are 31 hits, ALL cosmetic silkscreen
  (8 `silk_overlap` + 23 `silk_over_copper` — silk text crowded by the dense
  THT field/tab row on a much smaller board, no copper impact); this is the
  same documented-benign category the platform's other generated boards
  already carry, just a higher count here because the board itself shrank
  ~4.6× in area (from 238×77 mm) while the same 24+9+10-position component
  count stayed on it — a GUI silk-refinement pass, not a routing defect.
- `scripts/check_output_daughterboards.py`: **all checks pass**, including
  the geometric no-subset-seating proof against both EPS and PCIe (see
  "Keying" above).
- Netlist-verified: every one of the 9 tabs lands on its mapped ATX rail;
  every header pin lands on its mapped signal/GND/reserved net; the field's
  24 positions reproduce the standard ATX-24 map exactly (pin 20 = NC).

## Library assets used / added this pass

- `cec-vendor:TE_63849-1_FASTON_Tab` / `cec-Connector_Blade:TE_63849-1_FASTON_Tab_250x032_THT` (pre-existing, LCSC C86469).
- `cec:CEC_ATX_24` (pre-existing, reused verbatim for the field connector's electrical identity).
- `cec:CEC_CONN_2x5` + `cec-Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical` (pre-existing from the main-board task; this project's own library-asset pass independently reproduced byte-identical geometry).
- `cec-Connector_Generic:ATX24_Daughterboard_Field_P4.20mm` (this family's
  own field footprint; its Y-margin was tightened this pass —
  `scripts/gen-daughterboard-libassets.py`'s `solder_field()` now uses actual
  pad half-height instead of half the row pitch, dropping the field's own
  courtyard height 13.0→10.2 mm, the single biggest lever in fitting this
  board under the height cap — see that script for the reasoning).
- No mounting-hole footprint — removed this pass (owner directive; see
  "Mounting / retention" above). Never a schematic/BOM part on this
  generator, so the BOM is unaffected.

Generator: `scripts/gen-output-daughterboard.py atx24-out-db`.
