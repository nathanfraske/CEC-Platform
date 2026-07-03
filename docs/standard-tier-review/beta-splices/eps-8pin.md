# EPS 8-pin module -- BETA-1 splice (W11/H3a standalone-mode ESD/EMI suite)

Scope: `modules/eps-8pin/eps8pin-module.kicad_sch` (+ its BOM CSV). PCB untouched
(board stays placement-complete / zero-copper, per its committed state). Splice
discipline followed: hand-edited the existing hand-maintained schematic, never
regenerated via `gen-modules.py`.

## What landed

1. **W11/H3 standalone suite** -- **D3 = USBLC6-2SC6** (LCSC C2687116), wired
   exactly like the Hub's D6 reference (hub-standard.kicad_sch): a shunt/tap
   device on the USB data pair, not a series element. Taps `USB_D_P`/`USB_D_N`
   (same nets J5/U1 already share -- no break), `GND`, and `VBUS_RAW` (the
   *pre-bead* VBUS segment, so the ESD steering sits closest to J5, matching
   best practice and the hub-parity ask). This one part is read as satisfying
   both "USB D+/D- ESD" and "VBUS-side clamp" (USBLC6-2SC6 steers ESD current to
   both VBUS and GND rails; there is no separate dedicated VBUS TVS anywhere in
   the Hub reference either) -- flagged as an interpretation, not assumed silently.
2. **H3a ferrites**:
   - **(a) VBUS entry bead, POPULATED**: **FB1**, in series between J5's VBUS
     pins and the rest of the board (D2 ORing diode, C9 bulk cap). Corrected the
     lock register's MPN: **"MPZ2012S601ATD01" does not exist** (verified live,
     2026-07-03, LCSC/DigiKey/TDK) -- the real, stocked TDK part in that family is
     **MPZ2012S601AT000, LCSC C21519** (0805, 600R@100MHz, 2A, ~147k stock).
   - **(b) 5VSB RJ-45 VCC-entry bead position, 0R-default**: **FB2**, in series
     between J1 pin 1 (VCC) and the board's `+5VSB` net. Populated by default
     with a 0R jumper (UNI-ROYAL 0805W8F0000T5E, LCSC C17477 -- read
     **out-of-stock** at verification; any generic 0R 0805 jumper substitutes,
     flag at BOM-freeze), same 0805 land as FB1 so a real bead can be swapped in
     later on EMC evidence, per the lock register.
   - **(c) CAN pair common-mode-choke position, DNP**: **FL1**, in true series
     between the RJ-45-side CAN pair (renamed `CAN_H_RJ`/`CAN_L_RJ`) and the
     TJA1051T/3-side pair (`CAN_H`/`CAN_L` unchanged). Real-part candidate if
     ever populated: **TDK ACT45B-510-2P-TL003, LCSC C76584** (CAN-bus-rated
     SMD-4P 4.5x3.2mm, 51uH/line, 177k stock, verified live). **No footprint
     assigned** -- none exists in `lib/vendor` yet.
   - **CAUTION flagged in the schematic Description property**: because FL1 is
     DNP, the W6 routing pass must lay a parallel 0R bypass (or a direct,
     uncut trace) across its footprint so CAN stays continuous with FL1
     unpopulated -- KiCad's netlist/ERC do not model DNP as an open circuit
     (dnp is an assembly attribute only), so this is a real copper-continuity
     consequence for the layout pass to handle, not something resolvable at
     the schematic level.
3. **Rev -> BETA-1**: added a `title_block` (none existed before) with
   `rev "BETA-1"`, dated 2026-07-03, and a revision-note comment summarizing
   this splice. Alpha state is preserved in git history (no fab/ snapshot
   existed to rename).

## Symbol/library note (found mid-task, resolved)

Two other beta-splice agents had, concurrently and independently, already
added ferrite/CMC placeholder symbols to the shared `lib/vendor/cec-vendor.kicad_sym`:
`FerriteBead_Small` + `CommonModeChoke_Small` (one lineage) and `CEC_CMC_4T`
(another). EPS's splice was rebased onto these instead of inventing a fourth:
**FB1/FB2 now use `cec-vendor:FerriteBead_Small`**, **FL1 uses
`cec-vendor:CEC_CMC_4T`** (its IN/OUT pin grouping wired correctly: pins 1/2 =
`CAN_H_RJ`/`CAN_L_RJ`, pins 3/4 = `CAN_H`/`CAN_L`). D3 (USBLC6-2SC6) already
existed in the shared library from the Hub board, no change needed there.
**Flag for the orchestrator/owner**: `lib/vendor/cec-vendor.kicad_sym` now
carries three overlapping symbol families for the same H3a(c) CMC provision
(`CommonModeChoke_Small`, `CEC_CMC_4T`) plus one ferrite family
(`FerriteBead_Small`) -- these need consolidation to one canonical symbol each
before/at merge, across whichever boards picked up which name.

## Gates

- **ERC**: baseline (git HEAD) = 100 violations, all in 4 documented-benign
  classes (`pin_to_pin` 53, `lib_symbol_mismatch` 45, `pin_not_driven` 1,
  `pin_not_connected` 1). After the splice = **103 violations, same 4 classes,
  no new class**: `pin_to_pin` 53 (unchanged -- 2 new D3-related "Unspecified
  and Passive connected" pairs on the same USB net exactly balance 2 that
  disappeared when the direct `#PWR01`-to-J1 tie was replaced by the FB2 series
  break), `lib_symbol_mismatch` 48 (+3: FB1, FB2, FL1 -- new symbol instances,
  same class as the 45 pre-existing generator-cache mismatches), `pin_not_driven`
  1 and `pin_not_connected` 1 (both the identical pre-existing items, U2 TXD and
  U1's documented NC pad -- untouched).
- **Netlist assertions per splice** (`kicad-cli sch export netlist`, verified
  node-for-node):
  - `/VBUS_RAW` = {D3.5, FB1.1, J5.A4/A9/B4/B9} ; `/VBUS` = {C9.1, D2.2, FB1.2}
  - `/USB_D_P` = {D3.1, D3.6, J5.A6/B6, U1.18} ; `/USB_D_N` = {D3.3, D3.4,
    J5.A7/B7, U1.17} (shunt-tap, no break -- matches the hub reference)
  - `/VCC_RJ45_RAW` = {FB2.1, J1.1} ; `+5VSB` = {FB2.2, C1.1, C4.1, C6.1, D2.1,
    U2.3, U3.1, U3.3, ...} (FB2 correctly joins the pre-existing global rail)
  - `/CAN_H_RJ` = {FL1.1, J1.3} ; `/CAN_H` = {FL1.3, U2.7} ; `/CAN_L_RJ` =
    {FL1.2, J1.6} ; `/CAN_L` = {FL1.4, U2.6}
- **`--check-overlaps`** (`scripts/cec_sch_layout.py`): baseline 53 pairs, after
  69 pairs. Position-matched diff (ignoring text renames): **17 new pairs, all
  self-contained within the 4 new parts' own Reference/Value text sitting close
  to their own pins/labels** (D3, FB1, FB2, FL1 -- exactly the artifact of
  adding a part before its placement pass), **zero new pairs against any
  pre-existing content**; 1 pre-existing pair actually disappeared (the removed
  `#PWR01` Value text). This is the "needs placement before W6" case flagged
  below, not a collision with the rest of the board.
- **BOM CSV** (`bom/eps8pin-module-BOM-jlcpcb.csv`): added D3, FB1, FB2 lines
  (sourced, real LCSC numbers). **FL1 excluded** from the assembly CSV (DNP --
  no footprint exists yet either, so it cannot be placed even if it weren't
  DNP); documented instead in the schematic's Description property and this
  report. No existing lines were touched (the pre-existing stale connector
  footprint text and missing RS1/RS2 MPN, both flagged in the standing
  `docs/standard-tier-review/eps-8pin.md` review, are out of this splice's
  scope and left as-is).

## Placement still needed before the W6 routing pass

All four new parts (D3, FB1, FB2, FL1) plus their two new power-symbol ties
(`#PWR201` +5VSB, `#PWR202` GND) were placed in open schematic space (around
x=400-465, y=340-460) purely for schematic legality -- coordinates are on the
board's 1.27 mm grid (required to avoid ERC `endpoint_off_grid`, see below) but
are **not** integrated into the existing floorplan's visual layout. The W6
pass needs to:
- Move D3 physically adjacent to J5 (ESD device belongs at the connector).
- Move FB1 in series on the VBUS trace between J5 and D2/C9.
- Move FB2 in series on the RJ-45 pin-1 VCC trace, near J1.
- Move FL1 in series on the CAN_H/CAN_L run between J1 and U2, **and** decide/
  lay the 0R-bypass-or-direct-trace continuity workaround called out above.
- Source and vendor a real SMD-4P footprint for FL1/`CEC_CMC_4T` (currently
  Footprint = "") before it can go on the board at all, even DNP.
- Spread each new part's Reference/Value text off its own pins (clears the 17
  new `--check-overlaps` pairs, which are cosmetic-only right now).

## Two design interpretations made (flagged, not silently assumed)

1. **USBLC6-2SC6 satisfies both the "USB D+/D-" and "VBUS clamp" asks with one
   part**, tapping the pre-bead VBUS node -- there is no separate VBUS TVS
   anywhere in the Hub reference this board is asked to match parity with.
2. **FL1's DNP status leaves a real copper-continuity gap** that only the W6
   layout pass can close (bypass or direct trace) -- surfaced explicitly rather
   than silently routing around it or pretending DNP means "electrically
   absent" (it does not, in KiCad's netlist model).

## Not touched

`modules/eps-8pin/eps8pin-module.kicad_pcb`, `.kicad_pro`/`.kicad_dru`
netclasses (the new `VBUS_RAW`/`VCC_RJ45_RAW`/`CAN_H_RJ`/`CAN_L_RJ` segments
fall to Default class today -- flagging for W6 to fold them into the existing
Power/CAN netclass patterns), any other board, and `lib/vendor/cec-vendor.kicad_sym`
(consumed the concurrently-added shared symbols as-is rather than adding a
competing one).
