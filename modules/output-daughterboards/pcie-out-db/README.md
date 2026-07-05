# PCIe 8-pin output daughterboard (per-cable) — BETA-1

Passive connector-daughterboard for **one** PCIe 8-pin cable's OUTPUT side,
per spec **§2.8 v1.4.0**. **One design, shared unmodified by both the
2-port and 3-port SKUs** (the same board is instantiated once per cable —
2 boards for `pcie-8pin-2port`, 3 for `pcie-8pin-3port`; no per-SKU
variant). Mates with the main board's per-cable `TB{n}1`–`TB{n}4` Keystone
3586 clips (already built, `modules/pcie-8pin-2port` / `-3port`, commit
`b76a62a`). No active or passive components.

DRAFT (no fab yet — OQ-86 fit-check sample gate open).

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

4 tabs in two groups of 2 (+12V, then GND), pitch 9 mm within a group /
10 mm between groups — the smallest joint count (4) and its own distinct
pitch/gap signature vs. EPS (6 tabs, 9/13) and 24-pin (9 tabs, 9/15).

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

## Verification (this pass)

- ERC: 0 errors (2 benign `lib_symbol_mismatch` warnings).
- Static connectivity audit: clean.
- DRC: 0 errors at any severity (7 cosmetic silk warnings, no copper impact).
- Netlist-verified: all 4 tabs land on their mapped rail; the field's 8
  positions reproduce the standard PCIe CEM motherboard-side map, with
  pins 7/8 confirmed tied to the GND net.

## Library assets used

- `cec-vendor:TE_63849-1_FASTON_Tab` / `cec-Connector_Blade:TE_63849-1_FASTON_Tab_250x032_THT` (pre-existing, LCSC C86469).
- `cec:CEC_CONN_2x4` (pre-existing generic connector symbol).
- `cec-Connector_Generic:PCIe8_Daughterboard_Field_P4.20mm` (new this pass).
- `cec-MountingHole:MountingHole_3.2mm_M3_Pad_Via` (pre-existing) — 4 corners, GND-tied.

Generator: `scripts/gen-output-daughterboard.py pcie-out-db`.
