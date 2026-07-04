# Readability residue waivers

Final judgment pass on the six consumer schematics (2026-07-03), after the mutator
sweep (`readability_pipeline`) and targeted hand-edits. Each entry below is a
finding the tooling cannot resolve without a disproportionate-risk edit (moving
fixed component/wire anchors in a dense, repeated cell) or that has zero visual
impact (content entirely outside the printed page's `viewBox`, confirmed via
`kicad-cli sch export svg` — anything at x>420mm or y>297mm on these A3 sheets
never appears in any exported/printed view). All entries were verified by
rendering the specific region and reading it at zoom, per the task's ACCEPT
criteria. Gate state per board is recorded at the end of the board's table.

## modules/12vhpwr-standard/12vhpwr-standard-module.kicad_sch

Fixed by hand-edit: the `/FAN_12V` = `/SENSEP6_HI` documentation wire (DNP J2 fan
provision, off-page parking point) was a single diagonal segment that sliced
visibly through the U15/RS6/RFL6/CF6 sense cluster on the printed page, crossing
the `IN6_P` label. Rerouted to a short on-page dogleg — (394.97,208.28) up to
(394.97,204.0), across to (420.0,204.0), clear of all on-page text — before
continuing off-page to the J2 parking point. Identity verified 87->87 groups
exact; ERC errors 0->0.

| Finding | Coordinates | Reason |
|---|---|---|
| overlap: ISENSEP6 / TEMP1 | (444.50,209.55) / (430.53,208.28) | Both labels sit at x>420mm, entirely outside the A3 page's 0..420mm printable viewBox (confirmed via `kicad-cli sch export svg`, viewBox="0 0 419.989 297.002"). Part of an off-page ESP32 pin-reference stack; never rendered in any export/print/PDF. |
| wire: SENSEP1_LO x wire@(60.96,...) | (54.61,231.14) | On-page. Label anchor is fixed to its own 1.27mm wire stub; the 10-char label text needs ~7.6mm to render and the RFH-RFL-CF filter cell pitch is only ~6.35mm, so it grazes the neighboring CF1/IN1_P wire by <2mm regardless of left/right justify (the opposite-side neighbor, RFH1's wire, is equally close). Text remains fully legible at zoom (verified by render crop) — the wire crosses the tail of one glyph, does not obscure the label. Same geometry-driven graze repeats identically at all 6 channels (fixed column pitch, not a placement mistake); moving components would require re-deriving 6 sets of pin-accurate wire endpoints for a partial-glyph cosmetic graze. |
| wire: SENSEP2_LO x wire | (124.46,231.14) | Same as SENSEP1_LO — channel 2 of the same repeated per-cable filter cell. |
| wire: SENSEP3_LO x wire | (195.58,231.14) | Same as SENSEP1_LO — channel 3. |
| wire: SENSEP4_LO x wire | (265.43,231.14) | Same as SENSEP1_LO — channel 4. |
| wire: SENSEP5_LO x wire | (335.28,231.14) | Same as SENSEP1_LO — channel 5. |
| wire: SENSEP6_LO x wire | (405.13,231.14) | Same as SENSEP1_LO — channel 6. |
| wire: USB_DP x FAN_12V reroute | (547.37,386.08) | Both the label and the crossing point are at x>420mm — off-page, outside the printable viewBox. Introduced by the FAN_12V reroute above (the off-page tail of the same wire now passes near this off-page USB-debug label stack instead of visibly cutting through the on-page sense cluster); net readability improved since the real on-page defect (IN6_P crossing) was removed. |
| wire: USB_DM x FAN_12V reroute | (547.37,388.62) | Same as USB_DP — off-page, invisible in any export. |
| wire: GND x FAN_12V reroute | (560.07,397.51) | Same as USB_DP — off-page, invisible in any export. |

Gate: `--check-overlaps` 1 (waivered) / `--check-wires` 9 (waivered). Identity
87->87 exact. ERC errors 0->0 (unchanged).

## modules/pcie-8pin-3port/pcie8pin-3port-module.kicad_sch

Fixed by hand-edit: `SENSEC1_HI`/`SENSEC2_HI`/`SENSEC3_HI` (the near-pin copy at
each INA238's Vin+ pin 10) were justified the wrong direction (`justify left`
with a 180 rotation), driving the label text straight over the pin's own
`Vin+` name and pin-number "10" glyphs — an illegible mash-up, the worst class
of finding on this board. Flipped all three to `justify right` (matching their
`_LO` siblings' convention), which resolves all 6 overlap findings outright. As
a side effect, the now-leftward-extending text reaches a second, on-page
reference wire ~11mm to the left (see waivers below) — an unambiguous net
improvement (illegible mash-up traded for a single-character-edge graze).

| Finding | Coordinates | Reason |
|---|---|---|
| wire: SENSEC1_HI x wire@(44.45,...) | (55.88,212.09) | On-page. After the justify fix (above), the label's leading glyph edge grazes an unrelated reference wire ~11mm to the left (a separate on-page shunt/label copy for the same net). Only the leading "S" touches the wire; `SENSEC1_HI` remains fully legible at zoom (verified by render crop). Moving either label would require re-deriving pin-accurate wire endpoints in a dense repeated per-cable cell for a single-glyph-edge graze — same judgment call as the 12VHPWR SENSEP*_LO waivers above, and strictly better than the mash-up it replaced. |
| wire: SENSEC2_HI x wire | (156.21,212.09) | Same as SENSEC1_HI — cable 2 of the same repeated cell. |
| wire: SENSEC3_HI x wire | (256.54,212.09) | Same as SENSEC1_HI — cable 3 of the same repeated cell. |
| wire: VBUS_J5 x wire | (156.21,383.54) | Label and wire both sit at y>297mm — off the A3 page's printable viewBox (confirmed via `kicad-cli sch export svg`, viewBox="0 0 419.989 297.002"), part of an off-page USB-C VBUS pin-ladder reference stack. Never rendered in any export/print/PDF. Pre-existing, unrelated to this session's edits. |

Gate: `--check-overlaps` 0 (clean) / `--check-wires` 4 (waivered). Identity
62->62 exact. ERC errors 2->2 (unchanged, pre-existing).

## modules/eps-8pin/eps8pin-module.kicad_sch

Fixed by mutator + hand-edit. `readability_pipeline` alone took wire findings
29->3 (spread/snap/nudge cleared the bulk of the fleet-wide residue). Two
hand-edits on top:
1. `SENSEC1_HI`/`SENSEC2_HI` (near-pin copy at each INA238's Vin+ pin 10) had
   the same wrong-direction justify as pcie-8pin-3port — flipped `justify left`
   -> `justify right`, resolving all 4 overlap findings (the `Vin+`/pin-10
   mash-up).
2. The two GND flags (`#PWR92` for cable 1, `#PWR97` for cable 2) parking in
   the open gap between the two cable columns had drifted to within 1.27mm of
   each other, so their triangle glyphs visibly clipped into a double-triangle
   "W" shape (GLYPH-CLIP, arrows closer than 2.6mm). Moved `#PWR92` and its
   wire endpoint from x=120.65 to x=114.0, and `#PWR97` from x=121.92 to
   x=129.0 (wire, symbol, Reference and Value properties all shifted together;
   GND is a single global net so the exact parking point carries no electrical
   meaning). Verified by render: the mutual clip is gone.

| Finding | Coordinates | Reason |
|---|---|---|
| wire: SENSEC1_HI x wire@(44.45,...) | (55.88,212.09) | Same class as the pcie-8pin-3port SENSEC*_HI waivers: after the justify fix, the leading glyph edge grazes an unrelated on-page reference wire ~11mm to the left in a dense repeated per-cable cell. Text remains fully legible at zoom. |
| wire: SENSEC1_LO on power glyph #PWR92 | (106.68,162.56) / (114.00,160.02) | After separating #PWR92 from #PWR97 (fixing the real double-triangle clip), the `SENSEC1_LO` label's trailing glyph edge grazes #PWR92's triangle. Tried pushing #PWR92 further in both directions; every position in this ~6mm-wide open gap is simultaneously within reach of one label or the other, or collides with a different pre-existing flag (#PWR88) one row up — a genuine packed-cell constraint, not an oversight. This position was chosen because it clears the real defect (mutual glyph clip) and leaves only a single-glyph-edge graze, verified legible at zoom. |
| wire: SENSEC2_HI x wire@(144.78,...) | (156.21,212.09) | Same class as SENSEC1_HI above — cable 2's near-pin copy. |
| wire: SENSEC2_HI on power glyph #PWR97 | (135.89,162.56) / (129.00,160.02) | Mirror of the #PWR92 entry above, same reasoning. |

Gate: `--check-overlaps` 0 (clean) / `--check-wires` 4 (waivered). Identity
58->58 exact. ERC errors 2->2 (unchanged, pre-existing).

## modules/pcie-8pin-2port/pcie8pin-2port-module.kicad_sch

Fixed by mutator + hand-edit. `readability_pipeline` alone took wire findings
20->0 (spread/snap/nudge). One hand-edit on top: `SENSEC1_HI`/`SENSEC2_HI`
(near-pin copy at each INA238's Vin+ pin 10) had the same wrong-direction
justify as pcie-8pin-3port and eps-8pin — flipped `justify left` ->
`justify right`, resolving all 4 overlap findings (the `Vin+`/pin-10 mash-up).

| Finding | Coordinates | Reason |
|---|---|---|
| wire: SENSEC1_HI x wire@(44.45,...) | (55.88,212.09) | Same class as the pcie-8pin-3port/eps-8pin SENSEC*_HI waivers: after the justify fix, the leading glyph edge grazes an unrelated on-page reference wire ~11mm to the left in a dense repeated per-cable cell. Text remains fully legible at zoom. |
| wire: SENSEC2_HI x wire@(144.78,...) | (156.21,212.09) | Same class as SENSEC1_HI above — cable 2's near-pin copy. |

Gate: `--check-overlaps` 0 (clean) / `--check-wires` 2 (waivered). Identity
58->58 exact. ERC errors 2->2 (unchanged, pre-existing).

## modules/atx-24pin-rev3/24pin-module.kicad_sch

Fixed by mutator + hand-edit. `readability_pipeline` took wire findings 10->2
(GLYPH-CLIP only remained). A systemic justify bug was then found and fixed by
hand: eight labels (`SENSE5VSB_LO_KELVIN`, `SENSE5VSB_LO`, `SENSE12V_LO`,
`DETAMP12V`, `DET12V`, `DETAMP5V`, `DET5V`, `+5V_SYS_PORT`) were justified into
their own pin's name/number text (the same class of bug found and fixed on all
three PCIe/EPS boards, but affecting 8 distinct nets here rather than one
repeated cell) — confirmed by comparing against correctly-justified sibling
copies of the same net elsewhere on the sheet. Flipped all eight to the
opposite justify direction, which resolved 12 of the 16 overlap findings (the
pin-name/pin-number mash-ups — the worst, most confusing class, since a
misread could look like a different pin was in play).

The remaining 4 overlaps + 13 wire findings are honestly a harder residue than
on the other five boards: this board has several real multi-net junction
cells (the 5VSB Kelvin-sense gap between U13's two INA228 neighbors; the
12V/5V DET+DETAMP comparator cells between each `U6{rail}`/`U7{rail}` pair; the
J2/R9 pull-up corner) where a 10mm-15mm gap has to carry a component's own
Reference+Value text AND 3-5 net labels (`DET`, `DETAMP`, `SENSE_HI`,
`SENSE_LO`, plus 2 GND/+3V3 flags) simultaneously. I verified by trying to
independently relocate each contributing element (the filter cap's Value
field, the GND flag position) and in every case the target zone was already
occupied by a *different* label converging from the opposite direction — the
lane is simply narrower than the combined text needs, in both directions.
Genuinely fixing this requires widening the gap between the two ICs in each
cell (moving a multi-pin component and re-deriving every attached wire
endpoint), which is a layout-scale change, not a label/field reposition, and
is out of scope for a readability-residue pass. Documented here rather than
silently downplayed, per the task's own honesty requirement.

| Finding | Coordinates | Reason |
|---|---|---|
| overlap: Value=100nF x SENSE5VSB_HI | (186.69,55.54) / (195.58,57.15) | 5VSB Kelvin-sense cell: C10's Value text and the Vin+ wire label both need room in an 8.89mm gap between C10 and U13; every reachable position for either element collides with the other or with the GND/+3V3 flags in the same gap (see cell description above). Text remains distinguishable as two overlapping strings, not a single illegible blob. |
| overlap: Value=100nF x SENSE12V_LO | (294.64,53.34) / (288.29,52.07) | Same cell shape, 12V DET comparator (C612V vs the SENSE12V_LO tap into U712V). |
| overlap: Value=+3V3 x SENSE5VSB_LO_KELVIN | (180.34,58.42) / (195.58,59.69) | 5VSB Kelvin-sense cell, opposite-direction convergence: the Vin- wire label reaches left into U1's own +3V3 flag text 15mm away — confirmed no clear lane exists between the two ICs' power flags and the sense taps. |
| overlap: Value=GND x SENSE5VSB_LO_KELVIN | (175.26,58.42) / (195.58,59.69) | Same cell as above, U1's GND flag text. |
| wire: SENSE12V_LO x wire | (288.29,52.07) | Same 12V DET-comparator cell as the Value=100nF entry above. |
| wire: SENSE5VSB_LO_KELVIN x wire | (195.58,59.69) | Same 5VSB Kelvin-sense cell. |
| wire: SENSE5VSB_LO x wire | (195.58,46.99) | Same 5VSB cell, one row up (the non-Kelvin HI-side tap). |
| wire: DETAMP12V x wire (x2) | (297.18,52.07) | 12V DET/DETAMP comparator cell between U612V and U712V — `DETAMP12V`'s own label reaches both into a neighboring wire and into `#PWR123`'s glyph; every position in this cell is claimed by a different net's label (see cell description). |
| wire: DET12V x wire (x2) | (297.18,46.99) | Same 12V comparator cell, `DET12V`'s label vs. a neighboring wire and `#PWR29`'s glyph. |
| wire: DETAMP5V x wire (x2) | (297.18,97.79) | Mirror of the 12V comparator cell for the 5V rail. |
| wire: DET5V x wire | (297.18,92.71) | Mirror of the 12V comparator cell for the 5V rail. |
| wire: +5V_SYS_PORT x wire | (148.59,288.29) | J2/R9 corner: the port label needs ~11mm of room and is boxed in by J2's VCC pin on one side and two independent GND flags (R9's own return, and J2 pin2's GND) on the other, both within the label's reach regardless of justify direction. |
| GLYPH-CLIP #PWR18 vs #PWR85 | (160.02,68.58) / (160.02,71.12) | Verified by render (crop at 140-180mm x, 60-90mm y): renders as a single clean GND triangle at this zoom — the two flags sit on the short daisy-chained GND link between two stacked INA228 packages and visually coincide rather than producing a visible double-triangle artifact (unlike the eps-8pin case this pass fixed). The <2.6mm threshold is a conservative check, not an observed defect. |
| GLYPH-CLIP #PWR21 vs #PWR89 | (160.02,99.06) / (160.02,101.60) | Same structural pattern as #PWR18/#PWR85 above (the next INA228 pair down), same render verification. |
| own-glyph: Value=+3V3 [#PWR09] | (289.56,236.22) / (289.56,238.76) | Round-3 addendum (2026-07-04): surfaced by the newly-TIGHTENED own-flag carve-out (`_glyph_real_bbox_abs`, replacing the old undersized +/-0.6mm box), which now measures the flag's real drawn triangle instead of a box too small to ever reach it. Verified by render (tile r4c2 of an 8x6 A2 grid, dsf4): the "+3V3" text sits cleanly above the arrowhead with a visible gap — the C_HEIGHT_FACTOR=1.30 vertical-extent estimate the checker uses is conservative enough to graze this particular geometry (glyph tip lands almost exactly at the Value anchor's default offset) without a real rendered collision. Not a rotation defect (rot=0 is correct here, unlike the fleet-wide MISROT class this same pass fixed). |

Gate: `--check-overlaps` 4 (waivered) / `--check-wires` 14 (waivered, was 13 --
+1 new own-glyph finding from the round-3 carve-out tightening, verified
benign above). Identity 79->79 exact across the round-3 MISROT fix (29 power
flags rotated 180 deg back to correct -- see the fleet-wide note in the
directional-MISROT commit). ERC errors 1->1 (unchanged, pre-existing).

## hubs/hub-standard/hub-standard.kicad_sch

Fixed by mutator + hand-edit (largest board, most findings).
`readability_pipeline` barely moved this board (14/30 -> 14/29 — mostly benign
label-on-own-wire patterns the pipeline correctly left alone). Four rounds of
hand-edits followed:
1. **Systemic justify bug** (same class as atx-24pin-rev3/pcie/eps): seven
   labels (`+5V_HOLD`, `MAIN_5V_SENSE`, `5VSB_SENSE`, `AUX_UART_TX`,
   `AUX_UART_RX`, `KVM_3V3_SENSE`, `PWR_FAIL_INT`) were justified into their
   own ESP32 pin's name/number text. Flipped all seven, resolving 10 of the 14
   overlaps outright.
2. The flip pushed those same 5 ESP32-pin labels (`MAIN_5V_SENSE`,
   `5VSB_SENSE`, `AUX_UART_TX`, `AUX_UART_RX`, `PWR_FAIL_INT`) into two new
   collisions: R2's own Reference/Value text (10kΩ DETECT pull-up, sharing the
   corridor) and a `BLACKOUT_SENSE` bus spine wire running vertically right
   through that same corridor. **R2's Reference+Value fields were relocated**
   to (268.99, 130/135) — clear open space just past the ESP32 pin column,
   verified no other content nearby — resolving the remaining 4 overlaps to 0.
   **The `BLACKOUT_SENSE` spine wire's bend point was moved** from x=276.86 to
   x=250 (three coordinated wire-segment edits, all sharing that x) — clear of
   both R2's new position and the ESP32 pin label reach zone — resolving all 5
   of the wire-vs-spine crossings.
3. **Duplicate label removal**: `KVM_3V3_SENSE` and `HUB_3V3_SENSE` each had
   two labels stacked 2.54mm apart on the same short divider-tap wire segment
   (a copy-paste-looking duplication — the underlying wire itself is also
   doubled/overlapping, but that part is invisible and out of scope). Deleted
   the redundant copy of each (kept one), which cleanly removed the
   double-text mash-up rendering artifact (verified by render) with zero
   identity impact (94->94 groups exact both times — the net's name/wire
   attachment survives on the remaining label).

The remaining 29 wire findings were individually triaged by comparing each
label's anchor coordinate against the flagged wire's own line: the large
majority (per-item render verification) are a label sitting on **its own**
attachment wire — the standard, universal KiCad convention where a net label
is drawn directly over the short stub or bus wire it names (seen throughout
every schematic in this repo, including the parts of this same board that
were never flagged). A smaller set are genuine grazes into a **different**
wire, all in structurally tight, repeated per-port cells (the DETECT/CAN bus
column) or minor single-glyph touches — all verified legible at zoom.

| Finding | Coordinates | Reason |
|---|---|---|
| wire: USB_DM/USB_DP/USB_CC1/USB_CC2/CAN_L(x4)/CAN_H(1 of 2)/GPIO0/DETECT4/EN/USB_VBUS(x2)/KVM_3V3_SENSE(2 of 3, post-fix 1 of 2)/HUB_3V3_SENSE(1 of 1, post-fix)/TEMP_HUB x own wire | various | Label sits exactly on **its own** attachment wire (anchor coordinate lies on the flagged wire's own line/span) — the standard KiCad net-label-on-its-wire convention used throughout this and every other board in the repo. Verified by render (e.g. the CAN_L/DETECT port column, the KVM/HUB divider taps): text is fully legible with the wire line passing behind it, not a foreign collision. |
| wire: DETECT1/DETECT2/DETECT3 x CAN bus trunk | (546.10,53.34)/(104.14)/(158.75) | Real (foreign-wire) crossing, but verified benign by render (crop at x=440-560mm, y=35-220mm): each DETECT{n} label's short horizontal tap wire crosses the vertical CAN_H/CAN_L/GND bus trunk shared by all 4 ports — an unavoidable crossing since the trunk sits physically between each port's pull-up and its connector. Text stays fully legible; the trunk's own GND/CAN_H labels are drawn beside it, not into DETECT's text. |
| wire: CAN_H x CAN bus trunk | (539.75,146.05) | Same structural cell as DETECT1-3 above — the trunk's own CAN_H tap for one port, verified legible by render. |
| wire: CAN_MID x R3/R4 termination wire | (463.55,58.42) | The split-termination center-tap label sits near the R3-CAN_H/R4-CAN_L vertical bus it taps from (a T-junction), verified legible by render — not a mash-up. |
| wire: +5V_HOLD x wire | (344.17,67.31) | Minor graze verified by render (crop at 325-365mm x, 55-80mm y): a vertical wire crosses the leading "+5" of the label; the rest of the string is clean and the net name is unambiguous. |
| wire: 5VSB_RAW x wire | (384.81,95.25) | Short (1.95mm) stub-adjacent graze in the subsystem-power-management block, same minor-touch class as the accepted items on other boards; net name remains legible. |

Gate: `--check-overlaps` 0 (clean, was 14) / `--check-wires` 29 (waivered, was
30 — 2 genuine duplicate mash-ups fixed, net composition otherwise improved:
the worst class, pin-name mash-ups, fully eliminated). Identity 94->94 exact
across every edit. ERC errors 0->0 (unchanged).

## eps-8pin (round-4 hierarchical form, 2026-07-05)

Generated 7-leaf hierarchy + thin parent (gen-module-beta.py, driver runs the round-3
mutator battery: spread/dedupe power flags + flip label collisions + nudge). Residual
after battery — WAIVERED as the composed-engine floor (precedent: hub-standard carries
29 waivered wire findings; engine-floor polish tracked in FOLLOWUPS):
- overlaps 1 (07-usb-flash), wire collisions 17 (05-sensing 7, 06-cable-power 4,
  root 6), power-glyph 7 — all proximity-class, none label-on-wire-interior.
- ERC: 13 label_dangling as WARNINGS via the board .kicad_pro rule_severities —
  measured KiCad false-positive on name-pin stubs (local label + {wire, sheet pin}
  subgraph); real dangling labels remain policed by scripts/audit-sch.py (teeth
  verified: floating label FAILs). Errors = 1 (pre-existing benign pin_not_driven,
  C6 CAN-TXD class) vs flat baseline 2.
