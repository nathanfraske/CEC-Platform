# PCIe 8-pin output daughterboard (per-cable) — BETA-1

Passive connector-daughterboard for **one** PCIe 8-pin cable's OUTPUT side,
per spec **§2.8 v1.4.0**. **One design, shared unmodified by both the
2-port and 3-port SKUs** (the same board is instantiated once per cable —
2 boards for `pcie-8pin-2port`, 3 for `pcie-8pin-3port`; no per-SKU
variant). Mates with the main board's per-cable `TB{n}1`–`TB{n}4` Keystone
3586 clips (already built, `modules/pcie-8pin-2port` / `-3port`, commit
`b76a62a`). No active or passive components.

DRAFT (no fab yet — OQ-86 fit-check sample gate open).

## Posture — STANDS PERPENDICULAR to the main board (owner ruling, 2026-07-05)

This board is a small vertical card, not a parallel mezzanine (an earlier
framing this pass corrected — see `atx24-out-db/README.md` "Posture" for
the full reasoning, identical here). The 4 TE 63849-1 tabs mount near the
board's **bottom (near) edge**, blades pointing straight out of the board
face (horizontal once standing), side-entering the main-board Keystone 3586
clips. The output field sits above the tab row. Board axes: X = length
(FREE); Y = height (**ruled cap ≤15 mm "or so"**, owner 2026-07-05).

**Measured final size**: **34.6 × 14.6 mm** — well inside the height cap
and the owner's own rough single-face length estimate (20–36 mm).

**Mating height**: tab-row centreline sits **1.94 mm** above this board's
own near/bottom edge (identical figure to the other two families — see the
24-pin board's "Posture" section for the caveats on reading this as a
main-board mating height).

## Mounting / retention — no mounting holes (owner directive, 2026-07-05)

Same ruling and rationale as the 24-pin board: retention is the Keystone
clip's own high insertion force (a feature) plus chassis strain relief on
the cable/assembly side (OQ-87 owns the numeric spec). No BOM/schematic
impact — mounts were a PCB-only mechanical footprint on this generator.

## Tab map (4 joints/cable, TE 63849-1 / LCSC C86469)

| Ref | Net | PCIe8 pins bundled |
|---|---|---|
| J10, J11 | +12V | 1, 2, 3 |
| J12, J13 | GND | 4, 5, 6, 7, 8 |

2 contacts/polarity — the spec §2.8 v1.4.0 ratified PCIe joint count (8 on
the 2-port module, 12 on the 3-port). Design-basis current: ~13 A/pin
theoretical, only 3×12V pins → ~39 A/cable sustained worst case → ~49 A
margin target (§1 of the study).

## Output field (J1, `cec-Connector_Generic:PCIe8_Daughterboard_Field_P4.20mm`)

Bare THT solder field, 8 positions, 2×4 @ 4.20 mm pitch / 5.5 mm row (same
Molex Mini-Fit Jr 5569-08A2 grid as the EPS field). Standard **PCIe CEM
motherboard-side map**: pins 1–3 = +12V, pins 4–6 = GND, **pins 7–8 =
SENSE1/SENSE0** — per spec §2.8 v1.4.0's "2 sense tied... on the
daughterboard copper" text, these two positions are simply wired onto the
same GND net as pins 4–6 **in this board's own copper** (no dedicated blade
tab — negligible current, purely a presence-indication strap, exactly what
a real 8-pin PCIe cable does at the GPU end to advertise "full 8-pin
present"). Pins 1–6 are power-class (1.8 mm drill / 2.7×3.7 mm oval,
16 AWG); pins 7–8 are downsized 18 AWG-class (1.4 mm/2.6 mm — negligible
current, matching the TE tab leg size). Reuses the generic `cec:CEC_CONN_2x4`
symbol.

**Population options** — identical menu to the other two boards: (1) bare
16 AWG pigtail, power positions + 18 AWG for the two sense straps (default);
(2) MODDIY-class vertical header, dimensionally compatible, **not placed**
(no footprint vendored); (3) sellable daughterboard-plus-extension assembly.

## Keying

**Single row of 4 tabs at 8.2 mm pitch**, net order +12V×2 then GND×2 —
the smallest joint count of the three families. Floor: the TE 63849-1's own
courtyard is exactly 7.92 mm wide (measured, matches the datasheet to the
micron) — 8.2 mm leaves 0.28 mm of clearance, the tightest of the three
families (this family has the fewest gaps, so it needs the least pitch
delta from its neighbours to clear the no-subset-seating proof below — see
`scripts/gen-output-daughterboard.py`'s `TAB_PITCH` comment for the exact
per-family math).

**The real safety property is proved geometrically, not by pitch alone.**
`scripts/check_output_daughterboards.py` takes every family's tab-centre
list from `pcb_placement()` (the committed board's own coordinates) and,
for every ORDERED pair, searches all 4 rotations (0/90/180/270°) × every
candidate translation for a rigid whole-set mapping onto a subset of
another family's grid, within 0.5 mm (exact bipartite match). All 6 ordered
pairs come back "cannot seat." An earlier pitch choice here (8.2 mm,
unchanged) paired with EPS's original 8.3 mm MEASURABLY FAILED this exact
proof — this family's 4 tabs (only 3 gaps) seated within tolerance as a
subset of EPS's 6-tab grid, since a 0.1 mm/step difference over 3 gaps
accumulates to only 0.15 mm at the worst point. EPS's pitch was moved to
8.6 mm (0.4 mm delta from this family, clearing the (G/2)×Δpitch > 0.5 mm
bound at this family's own G=3) to fix it; this family's own pitch did not
need to move. **This daughterboard's tab grid is the authoritative
main-board mating drawing** for the PCIe per-cable clip pattern.

**Dual-face tabs**: evaluated and rejected for this whole family of boards
on the same grounds as the 24-pin board (see that README) — cross-face
interleaving only relieves pad-to-pad copper clearance (the TE 63849-1's
pads already span 7.58 mm inside its 7.92 mm courtyard), buying ~11% pitch
relief, not the ~50% a naive "halve it" framing assumes. Single-face,
single-row is built.

## Layer stack / current

**4-layer** (F.Cu / In1.Cu / In2.Cu / B.Cu, 2 oz outer / 1 oz inner) — same
2-net topology and reasoning as the EPS board: **GND floods both inner
layers** (In1.Cu + In2.Cu), **+12V floods both outer layers** (F.Cu + B.Cu),
zero explicit tracks/vias needed (every pad here is through-hole, so the
real `ZONE_FILLER`'s automatic pad-clearance/pad-connection handles the
whole fan-out). The doubled-layer-pair current margin is the reason 2-layer
was not used, same as EPS.

## Electrothermal sanity — not needed as a solver run

Same reasoning as EPS: both nets are full-board floods on doubled layer
pairs, no thin fan-out geometry on this board to check. The governing
current question is the blade-clip joint (OQ-86), not this board's copper.

## Sense-return provision

Not provisioned (no signal header on this board). The SENSE0/SENSE1 straps
above are a presence indicator, not a monitoring tap — they carry no
information back to the main board's sensing chain.

## Verification (this pass — 2026-07-05 floorplan rework)

- ERC: 0 errors (2 benign `lib_symbol_mismatch` warnings).
- Static connectivity audit: clean.
- DRC: **0 errors, 0 unconnected** (`kicad-cli pcb drc --severity-error`).
  At full verbosity, 12 hits, ALL cosmetic silk (1 `silk_overlap` +
  11 `silk_over_copper`, no copper impact) on a board ~2× smaller in area
  than the original 110×63 mm floorplan.
- `scripts/check_output_daughterboards.py`: all checks pass, including the
  geometric no-subset-seating proof against both ATX24 and EPS.
- Netlist-verified: all 4 tabs land on their mapped rail; the field's 8
  positions reproduce the standard PCIe CEM motherboard-side map, with
  pins 7/8 confirmed tied to the GND net.

## Library assets used

- `cec-vendor:TE_63849-1_FASTON_Tab` / `cec-Connector_Blade:TE_63849-1_FASTON_Tab_250x032_THT` (pre-existing, LCSC C86469).
- `cec:CEC_CONN_2x4` (pre-existing generic connector symbol).
- `cec-Connector_Generic:PCIe8_Daughterboard_Field_P4.20mm` — this pass
  tightened its Y-margin (pad half-height instead of half the row pitch,
  `scripts/gen-daughterboard-libassets.py`), dropping its own courtyard
  height 13.0→10.2 mm.
- No mounting-hole footprint — removed this pass (owner directive; see
  "Mounting / retention" above). Never a schematic/BOM part on this
  generator, so the BOM is unaffected.

Generator: `scripts/gen-output-daughterboard.py pcie-out-db`.
