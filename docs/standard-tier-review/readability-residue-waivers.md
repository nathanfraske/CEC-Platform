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
