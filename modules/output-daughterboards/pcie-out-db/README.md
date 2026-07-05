# PCIe 8-pin output daughterboard (per-cable) — BETA-1

Passive connector-daughterboard for **one** PCIe 8-pin cable's OUTPUT side,
per spec **§2.8 v1.4.0**. **One design, shared unmodified by both the
2-port and 3-port SKUs** (the same board is instantiated once per cable —
2 boards for `pcie-8pin-2port`, 3 for `pcie-8pin-3port`; no per-SKU
variant). Mates with the main board's per-cable `TB{n}1`–`TB{n}4` Keystone
3586 clips (already built, `modules/pcie-8pin-2port` / `-3port`, commit
`b76a62a`). No active or passive components.

DRAFT (no fab yet — OQ-86 fit-check sample gate open).

## Posture — STANDS PERPENDICULAR to the main board (owner ruling, 2026-07-04/05)

This board is a small vertical card, not a parallel mezzanine (an earlier
framing this pass corrected — see `atx24-out-db/README.md` "Posture" for
the full reasoning, identical here). The board's own standing posture is
unchanged; **what changed (owner ruling, 2026-07-05, same day, later): the
TAB CONNECTOR FORM.** The 4 tabs are now **TE 63951-1**, a RIGHT-ANGLE
(flat, in-plane) FASTON .250 PCB tab — the blade lies flat/coplanar with
this board's own standing plane and hangs **below the board's bottom edge**,
rather than pointing perpendicular out of the board's face (the earlier
same-day TE 63849-1 straight-tab / side-entry choice). This lets the whole
daughterboard drop straight down so the hanging blade enters the main-board
Keystone 3586 clip's top-entry slot. Full reasoning + the Keystone
top-entry-compatibility check: `atx24-out-db/README.md` "Posture" and
"Mating geometry" (identical analysis, this board's own numbers below), and
`docs/standard-tier-review/blade-fit-check-2026-07-04.md`'s 2026-07-05
addendum. **No main-board change needed** — see the 24-pin README for why.
Board axes (unchanged): X = length (FREE); Y = height (**ruled cap ≤15 mm
"or so"**, owner 2026-07-05).

**Measured final size**: **34.5 × 14.6 mm** — essentially unchanged from
the perpendicular-tab revision (34.6 × 14.6 mm), well inside the height cap
and the owner's own rough single-face length estimate (20–36 mm).

**Mating geometry (recomputed for TE 63951-1)**: tab-row centreline (the 2
through-hole legs) sits **2.00 mm** above this board's own near/bottom edge
(identical figure to the other two families). Blade hang-length past this
board's own edge: **6.89 mm** (same tab, same figure platform-wide) vs. the
Keystone 3586 clip's own 7.16 mm body height — see the 24-pin README's
"Mating geometry" for the full numeric comparison and the open OQ-86/87
items this surfaces (unresolved from paper on either datasheet, same
caveat here).

## Mounting / retention — no mounting holes (owner directive, 2026-07-05)

Same ruling and rationale as the 24-pin board: retention is the Keystone
clip's own high insertion force (a feature) plus chassis strain relief on
the cable/assembly side (OQ-87 owns the numeric spec). No BOM/schematic
impact — mounts were a PCB-only mechanical footprint on this generator.

## Tab map (4 joints/cable, TE 63951-1 / LCSC C591344)

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
the smallest joint count of the three families. Floor: the new TE 63951-1's
own near-leg shoulder band is exactly 7.92 mm wide (measured, matches the
new tab's own C=63951 drawing to the micron, AND matches the prior 63849-1
footprint's width exactly — verified as a family-wide figure tied to the
shared leg/hole geometry, not blade width, per the blade-fit-check
addendum) — 8.2 mm still leaves 0.28 mm of clearance, unchanged by the
2026-07-05 tab-form swap and still the tightest of the three families (this
family has the fewest gaps, so it needs the least pitch delta from its
neighbours to clear the no-subset-seating proof below — see
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
on the same grounds as the 24-pin board (see that README) — UNCHANGED by
the tab-form swap, since TE 63951-1 shares 63849-1's own leg pattern:
cross-face interleaving only relieves pad-to-pad copper clearance (the
tab's pads still span 7.58 mm inside its 7.92 mm shoulder band), buying
~11% pitch relief, not the ~50% a naive "halve it" framing assumes.
Single-face, single-row is built.

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

## Verification (this pass — 2026-07-05 connector-form rework, TE 63849-1 → 63951-1)

- ERC: 0 errors (2 benign `lib_symbol_mismatch` warnings).
- Static connectivity audit: clean.
- DRC: **0 errors, 0 unconnected** (`kicad-cli pcb drc --severity-error`).
  At full verbosity, 25 hits: 11 `silk_overlap` + 10 `silk_over_copper`
  (same documented-benign class as before) + **4 `silk_edge_clearance`**
  ("silkscreen clipped by board edge") — a NEW category this pass, from the
  tab's blade silk now intentionally crossing Edge.Cuts (the overhang). Not
  a novel risk: the platform's own already-shipped `modules/atx-24pin-rev3`
  and `modules/12vhpwr-standard` boards carry 18 and 8 hits respectively of
  the identical category at the identical cosmetic severity (measured this
  pass) from their own overhanging connectors. No copper crosses the edge
  (0 errors, 0 unconnected) — only the body/silk overhangs, the established
  platform pattern.
- `scripts/check_output_daughterboards.py`: all checks pass, including the
  geometric no-subset-seating proof against both ATX24 and EPS — re-verified
  against the new tab's actual placed coordinates.
- Netlist-verified: all 4 tabs land on their mapped rail; the field's 8
  positions reproduce the standard PCIe CEM motherboard-side map, with
  pins 7/8 confirmed tied to the GND net.

## Library assets used

- **`cec-vendor:TE_63951-1_FASTON_Tab` / `cec-Connector_Blade:TE_63951-1_FASTON_Tab_250x032_RA_THT`
  (NEW this pass, LCSC C591344)** — right-angle/flat .250 FASTON tab,
  vendored from TE's own customer drawing C=63951 rev L2
  (`lib/datasheets/TE_63951-1.pdf`), replacing TE 63849-1 per the owner's
  2026-07-05 connector-form ruling. See
  `docs/standard-tier-review/blade-fit-check-2026-07-04.md`'s dated addendum.
- `cec-vendor:TE_63849-1_FASTON_Tab` / `cec-Connector_Blade:TE_63849-1_FASTON_Tab_250x032_THT`
  — pre-existing, LCSC C86469, now unreferenced by this generator (left
  vendored; harmless).
- `cec:CEC_CONN_2x4` (pre-existing generic connector symbol).
- `cec-Connector_Generic:PCIe8_Daughterboard_Field_P4.20mm` — tightened its
  Y-margin in an earlier pass (pad half-height instead of half the row
  pitch, `scripts/gen-daughterboard-libassets.py`), dropping its own
  courtyard height 13.0→10.2 mm. Unchanged this pass.
- No mounting-hole footprint — removed in an earlier pass (owner directive;
  see "Mounting / retention" above). Never a schematic/BOM part on this
  generator, so the BOM is unaffected.

Generator: `scripts/gen-output-daughterboard.py pcie-out-db`.
