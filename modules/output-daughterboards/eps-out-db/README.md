# EPS 8-pin output daughterboard (per-cable) — BETA-1

Passive connector-daughterboard for **one** EPS 8-pin cable's OUTPUT side,
per spec **§2.8 v1.4.0** and `docs/standard-tier-review/SYNTHESIS-beta-plan.md`
§D-5a. **One design, instantiated per cable** — the EPS module populates 2
cables, so 2 of these boards are built per module (identical PCB, no
per-cable variant). Mates with the main board's per-cable `TB{n}1`–`TB{n}6`
Keystone 3586 clips (already built, `modules/eps-8pin`, commit `b76a62a`).
No active or passive components.

DRAFT (no fab yet — OQ-86 fit-check sample gate open).

## Posture — STANDS PERPENDICULAR to the main board (owner ruling, 2026-07-05)

This board is a small vertical card, not a parallel mezzanine (an earlier
framing this pass corrected — see `atx24-out-db/README.md` "Posture" for
the full reasoning, identical here). The 6 TE 63849-1 tabs mount near the
board's **bottom (near) edge** with blades pointing straight out of the
board face — horizontal once the board stands up — engaging the main-board
Keystone 3586 clips via **side entry**. The output field sits above the tab
row. Board axes: X = length (parallel to the main board, FREE dimension);
Y = height (the board's own vertical extent standing up, **ruled cap
≤15 mm "or so"**, owner 2026-07-05).

**Measured final size**: **53.0 × 14.6 mm** (length × height,
`pcbnew.GetBoardEdgesBoundingBox`) — well inside both the height cap and the
owner's own rough single-face length estimate (27–53 mm).

**Mating height**: tab-row centreline sits **1.94 mm** above this board's
own near/bottom edge (identical figure to the 24-pin board — same field
height + same edge margins govern it; see that README's "Posture" section
for the caveats on reading this as a main-board mating height).

## Mounting / retention — no mounting holes (owner directive, 2026-07-05)

Same ruling and rationale as the 24-pin board (see that README): retention
is the Keystone clip's own high insertion force (a feature, not a
shortfall) plus chassis strain relief on the cable/assembly side (OQ-87
owns the numeric spec). No BOM/schematic impact — mounts were a PCB-only
mechanical footprint on this generator, never a schematic part.

## Tab map (6 joints/cable, TE 63849-1 / LCSC C86469)

| Ref | Net | EPS8 pins bundled |
|---|---|---|
| J10, J11, J12 | GND | 1, 2, 3, 4 |
| J13, J14, J15 | +12V | 5, 6, 7, 8 |

3 contacts/polarity — matches spec §2.8 v1.4.0's ratified EPS joint count
(12 total across the module's 2 cables). Design-basis current: ~13 A/pin
continuous → ~52 A/cable sustained worst case → ~65 A margin target (§1 of
the output-daughterboard study), well inside 3× the Keystone 3586's 30 A
field rating (confirm-soak/thermal-cycle contact-R trend recommended before
BOM lock, OQ-86/88 — not gating).

## Output field (J1, `cec-Connector_Generic:EPS8_Daughterboard_Field_P4.20mm`)

Bare THT solder field, 8 positions, 2×4 @ 4.20 mm pitch / 5.5 mm row — the
real Molex Mini-Fit Jr 5569-08A2 land (measured off
`lib/vendor/Connector_Molex.pretty`). Pin map **1–4 = GND, 5–8 = +12V**,
matching the platform's own corrected EPS pinout convention (see
`CLAUDE.md` "EPS 8-pin power-connector pinout fix"). All 8 positions are
power-class (1.8 mm drill / 2.7×3.7 mm oval, 16 AWG-class) — no signal
circuits on this cable. Reuses the generic `cec:CEC_CONN_2x4` symbol
(unnamed pins; the net map lives in the wiring, not the symbol).

**Population options** — identical menu to the 24-pin board (see that
README for the full text): (1) bare 16 AWG pigtail (default); (2)
MODDIY-class vertical header, dimensionally compatible, **not placed** (no
footprint vendored, OQ-88 provenance gap); (3) sellable
daughterboard-plus-extension assembly (OQ-89).

## Keying

**Single row of 6 tabs at 8.6 mm pitch**, net order GND×3 then +12V×3
(matching the tab map above). Floor: the TE 63849-1's own courtyard is
exactly 7.92 mm wide (measured off
`cec-Connector_Blade:TE_63849-1_FASTON_Tab_250x032_THT`, matching the TE
datasheet to the micron) — 8.6 mm leaves 0.68 mm of clearance.

**The real safety property is proved geometrically, not by pitch alone.**
`scripts/check_output_daughterboards.py` takes every family's tab-centre
list straight from `pcb_placement()` (the committed board's own
coordinates) and, for every ORDERED pair, searches all 4 rotations
(0/90/180/270°) × every candidate translation for a rigid whole-set mapping
onto a subset of another family's grid, within 0.5 mm (exact bipartite
match). All 6 ordered pairs (this family vs. both others, both directions)
come back "cannot seat." This replaced an earlier (count, pitch, gap)
signature check that could not express a 2-D grid at all — and which, at
an earlier pitch choice (8.3 mm here, 8.2 mm on PCIe), MEASURABLY FAILED
this exact geometric proof: a 0.1 mm/step pitch difference over PCIe's 3
gaps accumulates to only 0.15 mm at the worst point, well inside the 0.5 mm
tolerance, so PCIe's 4 tabs seated as a subset of this board's 6-tab grid.
The pitch here (8.6 mm) and PCIe's (8.2 mm) now differ by 0.4 mm, clearing
the (G/2)×Δpitch > 0.5 mm bound at G=3 (PCIe's own gap count) — see
`scripts/gen-output-daughterboard.py`'s `TAB_PITCH` comment for the general
rule. **This daughterboard's tab grid is the authoritative main-board
mating drawing** for the EPS per-cable clip pattern (the main board carries
no clips yet).

**Dual-face tabs**: evaluated and rejected for this whole family of boards
on the same grounds as the 24-pin board (see that README) — the TE
63849-1's own copper pads already span 7.58 mm inside its 7.92 mm
courtyard, so cross-face interleaving only relieves pad-to-pad clearance,
not full courtyard clearance, buying ~11% pitch relief rather than the
~50% a naive "halve it" framing assumes. Single-face, single-row is built.

## Layer stack / current

**4-layer** (F.Cu / In1.Cu / In2.Cu / B.Cu, 2 oz outer / 1 oz inner) — this
is a **2-net board** (GND, +12V), so unlike the 24-pin board there is no
inter-rail banding problem: **GND floods both inner layers** (In1.Cu +
In2.Cu, matching this platform's own already-built EPS/PCIe cable-power
convention — "two GND inners... 12V lives on the OUTERS",
`scripts/gen-module-pcb.py` `gnd_planes()` docstring) and **+12V floods both
outer layers** (F.Cu + B.Cu). Every field pin and blade tab here is a
through-hole pad by construction (no SMD parts on this board at all), so
each already carries copper on every layer; the real `ZONE_FILLER`
auto-clears around every foreign-net pad within a flood's outline and
auto-connects to every same-net pad — **no explicit tracks/vias are needed
at all** for a genuine 2-net board, which is why 2-layer was NOT chosen
instead: doubling the copper thickness on both rails via full F+B and
In1+In2 pairing (four total flooded layers across two nets) directly buys
current margin on the ~65 A/cable target the 2-layer alternative would have
to fight for with much thinner single-layer copper.

## Electrothermal sanity — not needed as a solver run

Both nets are full-board floods on doubled layer pairs with no thin
fan-out geometry to check (no per-pin stub traces exist on this board —
see above); the governing current-capacity question is the **blade-clip
joint** itself (OQ-86's recommended confirm-soak/thermal-cycle bench), not
this board's own copper. Noted, not treated as a gap.

## Sense-return provision

Not provisioned on this board (no signal header exists here, unlike the
24-pin board — EPS carries only GND/+12V). If OQ-88's sense-return decision
lands "yes" for EPS, it needs a small signal-tab addition in a future
revision; not a silent gap, just genuinely absent today.

## Verification (this pass — 2026-07-05 floorplan rework)

- ERC: 0 errors (2 benign `lib_symbol_mismatch` warnings).
- Static connectivity audit: clean.
- DRC: **0 errors, 0 unconnected** (`kicad-cli pcb drc --severity-error`).
  At full verbosity, 15 hits, ALL cosmetic silk (2 `silk_overlap` +
  13 `silk_over_copper` — silk text vs. the dense THT field on a board
  ~2.1× smaller in area than the original 110×67 mm floorplan; no copper
  impact).
- `scripts/check_output_daughterboards.py`: all checks pass, including the
  geometric no-subset-seating proof against both ATX24 and PCIe.
- Netlist-verified: all 6 tabs land on their mapped rail; the field's 8
  positions reproduce the platform's corrected EPS8 pinout exactly.

## Library assets used

- `cec-vendor:TE_63849-1_FASTON_Tab` / `cec-Connector_Blade:TE_63849-1_FASTON_Tab_250x032_THT` (pre-existing, LCSC C86469).
- `cec:CEC_CONN_2x4` (pre-existing generic connector symbol).
- `cec-Connector_Generic:EPS8_Daughterboard_Field_P4.20mm` — this pass
  tightened its Y-margin (pad half-height instead of half the row pitch,
  `scripts/gen-daughterboard-libassets.py`), dropping its own courtyard
  height 13.0→10.2 mm; the single biggest lever in clearing the height cap.
- No mounting-hole footprint — removed this pass (owner directive; see
  "Mounting / retention" above). Never a schematic/BOM part on this
  generator, so the BOM is unaffected.

Generator: `scripts/gen-output-daughterboard.py eps-out-db`.
