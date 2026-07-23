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

## beta/12vhpwr-standard/12vhpwr-standard-module.kicad_sch

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

## beta/pcie-8pin-3port/pcie8pin-3port-module.kicad_sch

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

## beta/eps-8pin/eps8pin-module.kicad_sch

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

## beta/pcie-8pin-2port/pcie8pin-2port-module.kicad_sch

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

## beta/atx-24pin-rev3/24pin-module.kicad_sch

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

## pcie-8pin-2port and pcie-8pin-3port (round-4 Wave 3a hierarchical form, 2026-07-04)

Both converted with the SAME driver proven on eps-8pin (gen-module-beta.py), extended
generically (not board-hardcoded) to cover two real divergences found by validating the
partition against each board's actual refs/nets before running, per the task's own
discipline:

1. **PCIe-only H3 parts.** The beta-splice commit (99c2b41, "PCIe beta splices landed")
   added a VBUS clamp diode + explicit power-flag symbols that EPS's own splice
   (7acb42f) did not carry: `D4` (cec-vendor:D_Schottky, Value PESD5V0S1BA) on
   `/VBUS` alongside C9/D2/D3/FB1 (single-leaf, 07-usb-flash); `PWR201`/`PWR202`
   (cec-power:GND, D3's and D4's own ground stamps) and `PWR203` (cec-power:+5VSB,
   downstream of FB2) — none carrying KiCad's usual `#` power-symbol reference
   prefix (a pre-existing authoring quirk in the splice, left as-is, not this pass's
   place to fix), so `cec_sch_gates.inventory()` sees them as ordinary parts and
   `classify_ref()` had to place them. Verified via `cec_pcb_reconcile.netlist_groups`
   on the live flat boards (identical on both SKUs) before extending `FIXED_LEAF`;
   `D4`/`PWR201`/`PWR202` -> 07-usb-flash, `PWR203` -> 01-hub-link (FB2's leaf).
   `gen-module-beta.py`'s `LIBS` dict gained a `"cec-power"` alias (same file as the
   existing `"power"` key) since these refs' `lib_id` resolves to that nickname.
   `_emit_symbol2` unconditionally writes an empty `Footprint`/`Datasheet` property
   on every part (correct for every ordinary component, which all already carry
   both) — but the ORIGINAL flat symbol for these three power-flag refs carries
   ONLY Reference+Value, so the driver gained a targeted post-write patch
   (`_strip_absent_props`) removing exactly the spurious empty properties,
   restoring exact G2 inventory equality rather than waiving a real (if inert) diff.
2. **Net-name divergence, not a partition bug.** The hub-link<->can crossing is
   named `CAN_H_RJ`/`CAN_L_RJ` on EPS but `CAN_H_J1`/`CAN_L_J1` on both PCIe SKUs
   (different beta-splice authoring sessions, same electrical crossing) — the
   original `PAIR_SIDES` table hardcoded EPS's literal net names and crashed with
   `KeyError` on PCIe. Replaced with `_pair_sides(extracted)`, which derives each
   2-leaf net's per-leaf "side" from the root BOX x-ordering (verified to reproduce
   EPS's original hand-authored table exactly) instead of a net-name literal — this
   ALSO fixes a latent defect the fixed-2-cable table would otherwise have hit on
   pcie-8pin-3port (a 3rd `SENSEC3_HI`/`SENSEC3_LO` pair with no table entry would
   have gotten NO hier_exports on either leaf — two isolated same-name local labels
   on different sheets, silently stranding the net; caught only by G1/G3, not any
   assertion, so it must never be reached). Re-verified byte-for-byte no-regression
   on eps-8pin (`--force` self-regen in a scratch copy: G1 58/58, G2 0 diffs, G3
   empty map, audit-sch 8/8 ok) after these engine-adjacent changes.
3. **pcie-8pin-3port only:** the per-cable "6.13 TRANSIENT DETECTION cable N"
   caption list was hardcoded to 2 entries (EPS/2-port cable count) — a real G8
   prose-preservation FAIL on the 3rd cable's caption (missing=1), not cosmetic.
   Fixed by deriving the caption per actual `cable_labels` entry instead of a fixed
   list; re-verified verbatim against the flat baseline for both cable counts.

Gates (both boards, vs their own pre-conversion flat baseline at commit 1f132dd): G1
group-identity exact (2-port 58/58, 3-port 62/62, 0 missing/extra each), G2 inventory
0 diffs (2-port 55/55, 3-port 64/64, incl. DNP — FL1 dnp yes carried), G3 rename map
EMPTY on both, G6 region-containment/sheet-bounds 0/0 both, G8 prose preservation 0
missing both (after the 3-port caption fix), G11 BOM identical sorted-by-ref both,
audit-sch.py 8/8 `ok` both. G4 ERC errors: 2-port 1 vs baseline 2, 3-port 1 vs baseline
2 (same benign pre-existing `pin_not_driven` persists both; label_dangling on the
name-pinned stubs downgraded to warning via the SAME per-board `.kicad_pro`
`erc.rule_severities` mechanism as eps-8pin — 13 entries on 2-port, 14 on 3-port).
Netclasses/`.kicad_dru` confirmed byte-identical pre/post on both (only
`.kicad_pro` change is the scoped `erc.rule_severities.label_dangling` write).

G5 residual — WAIVERED as the SAME composed-engine floor already accepted for
eps-8pin/hub-standard (proximity-class only, no label-on-wire-interior mash-up; the
one true "worst class" defect this family is known for, the SENSEC*_HI justify bug,
was already fixed pre-conversion on all three boards per this doc's earlier entries
and carries forward clean):
- **pcie-8pin-2port**: overlaps 1 (07-usb-flash: `USB_D_N` label vs `VBUS_J5`
  hierarchical_label, byte-for-byte the same class/positions as eps-8pin's own
  07-usb-flash overlap, just a differently-named net — EPS calls the same physical
  net `VBUS_RAW`); wire/glyph findings 19 (01-hub-link 3 glyph-MISROT — identical
  coordinates to eps-8pin's own 3, confirming a `compose_hub_link`-level engine
  characteristic independent of cable count; 05-sensing 11 [7 wire + 4 glyph];
  root 5 wire). 06-cable-power is CLEAN on this board (0, vs eps-8pin's 4 — better,
  not worse).
- **pcie-8pin-3port**: overlaps 2 (07-usb-flash: same USB_D_N/VBUS_J5 class as
  2-port; 05-sensing: ONE NEW instance from the added 3rd-cable density — U12's
  `Value="INA238"` property text grazes U11's own pin-7 glyph one row up, the same
  proximity class as the already-accepted SENSEC/DETAMPC-on-power-glyph findings,
  just between two neighboring cable rows instead of a label and its own glyph);
  wire/glyph findings 25 (01-hub-link 3 — same coordinates as 2-port/eps-8pin;
  05-sensing 17 [11 wire incl. the 3-cable density finding's wire-crossing
  counterpart, 6 glyph-clip] — proportionally consistent with 2-port's 11 scaled to
  3 cables; root 5 wire, same class as 2-port).
Not chased further per the round-4 cost directive (deterministic checkers judge,
sonnet/haiku subagents only, no render-read loops); every instance verified by
category match against the already-accepted eps-8pin/hub-standard precedent, none is
a label-on-its-own-pin-name mash-up (the one class this family fixes, never waives).

PCB reconcile (both, `cec_pcb_reconcile.py --baseline-rev 1f132dd`): 0 net renames,
0 real path updates (both PCBs carry zero `(path ...)` fields pre-conversion, same
documented no-op as eps-8pin/12vhpwr's EPS/PCIe precedent — `path_absent_known_ref`
lists every footprint-bearing ref, confirming the absence is pre-existing, not
caused by this pass), `changed: false`, DRC parity EQUAL (2-port 456/456, 3-port
550/550, 0 only-before/only-after). `path_map_misses` lists D3/D4/FB1/FB2/FL1/
PWR201-203/R11/R12 as schematic-side refs with no matching PCB footprint at all —
confirmed PRE-EXISTING (the beta-splice commit's PCB diff was 6 lines, i.e. it never
placed these parts on the board) and unrelated to this conversion; tracked as the
existing PCB-catch-up gap, not a reconcile defect (`net_settings`/DRU confirmed
byte-identical, `netclass_changes: []`, `dru.changed: 0`).

## 12vhpwr-standard (round-4 Wave 3b hierarchical form, 2026-07-05)

Highest-stakes board of the four (fully routed PCB, CI-gated/not-DRAFT, hand-maintained
schematic with hand splices, 85 refs / 87 netlist groups). Converted with a NEW SIBLING
driver, `scripts/gen-12vhpwr-beta.py` (self-contained rather than importing
`gen-module-beta.py`, which is not import-able by a plain `import` statement due to its
dashed filename, and per the task's instruction not to restructure the proven eps driver;
the two share the same underlying engine calls, not code). Partition: 11 literal leaves
(01-input, 02-lanes, 03-output, 04-ina, 05-mcu, 06-can, 07-ldo, 08-usb, 09-hub-link,
10-temp, 11-rail-ref) — verified computationally against the live netlist BEFORE composing
that every one of the 49 cross-leaf + 10 leaf-internal named nets touches <=2 leaves; this
forced two adjustments off the task's own first-draft bin sketch: the rail-voltage divider
(R5/R6/C24) moved into 02-lanes (not a separate rail-ref bin) and the sideband series taps
(R10-R13) moved into 01-input (not 05-mcu) — both required so `/FAN_12V` and the four
`/SB_*` base nets stay 2-leaf, confirmed by a standalone Python check building the same
partition dict against `cec_pcb_reconcile.netlist_groups()` before writing any compose code.

**Engine change (additive, back-compat verified):** `cec_sch_compose.PAPER` gained `"A1"`
(841x594mm) and `"A0"` (1189x841mm) entries — this board's hub-and-spoke fan-out (05-mcu
connects to 8 of the other 10 leaves) needs more page than A2 offers for the thin parent.
Verified byte-identical (masked-uuid) regeneration with vs without the addition across
ent-common (7 files), hub-enterprise (27 files), and eps-8pin (8 files) — every existing
caller passes "A2"/"A3"/"A4" only, so the new dict keys are unreachable dead code for them.

**Two REAL bugs found+fixed via measured connectivity, not assumed** (both a repeat of the
same root cause, first seen on `04-ina`'s INA240 sensing channels and then on `02-lanes`'s
shunt/filter channels):
1. **Tied-Y merge.** `compose_lanes`'s first draft placed all 6 channels SIDE BY SIDE (same
   Y, only X differing per channel). `_route_io_columns`' per-side sort keys on
   `(attach_y, name)`; with 6+ channels sharing an identical attach Y, several channels'
   "already on this row" direct-connect horizontal legs ended up COLLINEAR with
   OVERLAPPING X ranges, and KiCad treats overlapping collinear segments as one conductor
   -- confirmed via `kicad-cli sch export netlist` on the generated leaf: all six
   `CF{n}.1`/`RFH{n}.2` pins had merged onto a single `/IN1_P` node (76 groups instead of
   87, with `IN2_P`..`IN6_P` gone entirely). Fixed by stacking all 6 channels VERTICALLY
   (distinct Y per channel) instead — mirrors `compose_ina`'s own layout, same fix, same
   root cause. `10-temp`'s two NTC channels (`compose_temp`) carried the identical latent
   risk (C20/C21 both at the same Y) and were fixed pre-emptively the same way, without
   waiting to observe an actual merge there.
2. **Root-level box-order violations.** `build_thin_parent` sorts each 2-endpoint net's
   pins by X and requires the smaller-X pin to be `side="right"`; three early `BOX` layout
   drafts placed a destination leaf's box at a smaller X than a source leaf that fed it
   (`03-output` needing to clear BOTH `01-input` and `02-lanes`; several of 05-mcu's five
   spoke leaves sharing 05-mcu's own row-8 Y band, which caused a SEPARATE class of
   failure below) — each caught immediately as a hard `SystemExit` from
   `build_thin_parent` itself ("pin sides must be right(source)->left(dest)"), not a
   silent defect.
3. **Hop-over wire-crosses-box.** Even after fixing (2), `01-input`'s SB_* nets (bound for
   `03-output`, ranked after `02-lanes`) crossed `02-lanes`' own box because both sat in
   the same Y band — `build_thin_parent`'s lane wire runs the FULL X-span between source
   and dest at the source's own row height, and any intermediate leaf's box in that Y
   band is hit regardless of X overlap (measured: "wire ... crosses sheet box 02-lanes").
   Fixed with a Y-STAIRCASE for the 5-leaf main flow chain (01-input -> 02-lanes ->
   03-output/04-ina -> 05-mcu, each a distinct non-overlapping Y band) plus a separate
   observation that 05-mcu's five "spoke" destinations (06-can/08-usb/09-hub-link/
   10-temp/11-rail-ref, each connecting ONLY to mcu) can safely REUSE the y=8 band the
   staircase vacated, since mcu's own outgoing wires run at mcu's row height, a
   completely different Y range that never intersects y=8 regardless of X — this keeps
   the whole layout inside a single `A0` page (see the engine change above) rather than
   needing an unboundedly wide/tall canvas.

Gates (vs the pre-run flat baseline at commit e65b9f8): **G1** group-identity exact, 87/87,
0 missing/0 extra. **G2** inventory: 6 findings, all a known engine-consistent residual, not
a data loss — `J3`/`J4` each dropped an EMPTY `LCSC=""` property (`_emit_symbol2` skips
empty-valued custom properties by design, verified: every OTHER prop on both refs, incl.
Manufacturer/MPN/Datasheet, is unchanged) and `R22`/`R23`'s Value normalized `'0R'`->`'0Ω'`
(the SAME `cec_sch.fmt_value`/`fmt_res` transform every other R_Small value on this board
already used, e.g. `2.2kΩ`/`10kΩ` — `'0R'` was the one value on the flat baseline that
hadn't been through this normalization yet; footprint/DNP/Note/LCSC/MPN/Manufacturer all
confirmed unchanged). **G3** rename map EMPTY (0 entries) — every one of the 49 cross-leaf
+ 10 name-pinned internal nets keeps its exact flat-schematic name. **G4** ERC errors 0 vs
baseline 0 (not increased); warnings 79 (10 label_dangling on the name-pin stubs, downgraded
to warning via the SAME per-board `.kicad_pro erc.rule_severities` mechanism as
eps/pcie-8pin; 69 lib_symbol_mismatch, pre-existing generator-cache noise) vs the baseline's
277 (dominated by stale `lib_symbol_issues`/`footprint_link_issues` noise specific to that
flat file's library cache state — not a like-for-like comparison, but errors are the gating
metric and those are 0 both ways). **G6** region-containment 0, sheet-bounds 0 (after moving
`02-lanes`/`04-ina` from A3 to A2 paper — their per-channel content, once laid out vertically
per the tied-Y fix above, exceeded A3's 297mm height). **G8** prose preservation: all 8
measured flat-sheet captions present verbatim in the new leaf set (0 missing) — "RAIL REF +
SIDEBAND REF3030" lands on `11-rail-ref` even though the sideband taps physically moved to
`01-input` for the <=2-leaf constraint (G8 checks the STRING appears somewhere in the new
file set, not co-location, per the eps precedent). **G11** BOM: 85/85 rows, sorted-by-ref
diff is the SAME 2 rows as the G2 `0R`->`0Ω` normalization, nothing else. **audit-sch.py**:
12/12 files `ok` (all 11 leaves + the thin parent).

G5 residual — WAIVERED as the SAME composed-engine floor already accepted for
eps-8pin/pcie-8pin/hub-standard (proximity-class only, no label-on-wire-interior mash-up),
after fixing what was fixable (04-ina's INA240 vertical pitch widened 30->42 units, clearing
5 Value-text-vs-own-power-glyph crossings entirely; 02-lanes' channel stack start shifted
15->30 to clear a caption/wire graze):
- overlaps 1 (`08-usb`: `VBUS_RAW`/`USB_DM` label pair, same 1-count bar as every sibling
  board's own usb-flash-equivalent leaf).
- wire collisions 40 (`02-lanes` 1 caption-vs-wire graze pre-fix, 0 post-fix; the thin
  parent's own 39 are ALL the identical mechanical artifact: a `lane_labels` tap's LOCAL
  LABEL sitting ~1.95mm from the adjacent vertical lane wire it is tapped off of — a
  structural byproduct of the (unmodified) `lane_labels` tap geometry, scaling linearly
  with this board's 49 cross-leaf nets vs eps's 16; every instance individually confirmed
  label-on-its-own-tap-wire, never a foreign-net mash-up).
- power-glyph 3 (`09-hub-link`, three `MISROT` findings) — confirmed BYTE-IDENTICAL
  coordinates to eps-8pin's own `01-hub-link.kicad_sch` (same `powerflag_nets=
  ["+5VSB","GND"]` call into the shared, unmodified `_powerflag_anchors` helper): a
  pre-existing engine characteristic of that helper, not something this board introduced.

**GND-bus item (owner directive 2, partial):** `05-mcu`'s ESP32-S3-MINI-1 carries 24 GND
pins; the driver's mutator battery (`spread_power_flags`/`dedupe_power_flags`, already part
of the same pass eps-8pin runs) collapsed them to 6 distinct stamps automatically (down from
a raw 24). `cec_sch_gates.bus_power_ladder` (the dedicated Wave-1 tool for a single explicit
link, used on the flat-form 24pin-rev3/hub-standard) found zero qualifying runs on `U1` here
and on each INA240 (`U10`-`U15`, 4 GND pins apiece) — `power_ladder_runs` wants an already-
collinear pin run and this MCU symbol's GND pins are not laid out that way. NOT chased
further into a hand-built compose-time ladder (eps's own `_ladder_column` precedent is
X-oriented; these ICs' GND pins face downward) given the round-4 cost directive and that
this is a quality item, not one of the graded gates. Tracked as a FOLLOWUP, not a regression
(the flat baseline had no single-link GND bus either).

**PCB reconcile** (`cec_pcb_reconcile.py --board beta/12vhpwr-standard --baseline-rev
e65b9f8`): 0 net renames, 77 `(path ...)` relinks (the real case the round-4 plan doc flagged
this board for — 77/85 refs carry a footprint on the committed, routed PCB), 7 mechanical
(mounts/fiducials, no schematic symbol), `net_count` 84->84 unchanged, `netclass_changes: []`
/ `dru.changed: 0` (byte-identical, confirming the zero-rename policy held all the way
through). `path_map_misses` lists 8 refs (D3/D4/FB1/FB2/FL1/J2/R22/R23) — confirmed via a
git-worktree DRC run against the UNCONVERTED baseline PCB+schematic that these have ZERO
footprint on the PCB and produce the IDENTICAL 28 schematic-parity findings pre- and
post-conversion (missing-footprint + stale net-name/Note-text mismatches from the H3a
standalone-mode-suite splice that added them to the schematic after the PCB was last
"Update PCB from Schematic"-synced) — pre-existing, unrelated to this conversion, not a
reconcile defect. **DRC parity CONFIRMED EQUAL**: 19 violations both before and after (4
hole_clearance / 8 silk_edge_clearance / 5 silk_over_copper / 2 silk_overlap, the same known
repo-wide USB-C-footprint + cosmetic-silk residue), 0 unconnected both, 28 schematic-parity
both (verified via a clean `git worktree` checkout of the pre-conversion commit, since a
same-directory scratch copy without the full `lib/` tree produces spurious
`lib_footprint_issues` noise that is a test-harness artifact, not a real board difference).
**Copper byte-identity**: stripping ONLY `(net "...")` and `(path "...")` field values from
both the pre- and post-reconcile `.kicad_pcb` leaves them byte-for-byte identical — every
track, via, zone fill, and pad position is untouched.
