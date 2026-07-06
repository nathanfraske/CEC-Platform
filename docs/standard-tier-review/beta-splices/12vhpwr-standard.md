# 12VHPWR Standard module -- BETA-1 splice (W11/H3/H3a suite + J2 fan provision)

Scope: `modules/12vhpwr-standard/12vhpwr-standard-module.kicad_sch` (+ its BOM
CSVs). PCB untouched -- the board stays fully routed/fab-ready per its
committed state (DRC.rpt: 0 unconnected, 0 copper/clearance/courtyard). Splice
discipline followed: hand-edited the existing hand-maintained schematic (real
wires + labels + component blocks, grid-aligned to the file's 1.27 mm pitch),
never regenerated -- this board has no generator (`gen-modules.py` excludes it
per its own header comment).

## What landed

1. **W11/H3 standalone suite**: **D3 = USBLC6-2SC6** (LCSC C2687116), wired
   pin-for-pin like the Hub's D6 reference (`hubs/hub-standard`): I/O1 (pins
   1,6) on `USB_DP`, I/O2 (3,4) on `USB_DM`, VBUS (5) and GND (2). **D4 = VBUS
   clamp**, `PESD5V0S1BA` (Nexperia, LCSC C5261083) -- reused the SAME part
   already on this board as D1 (DETECT-pin ESD), rather than SMF5.0A: it is
   already qualified/stocked on this exact board, IEC 61000-4-2 rated, smaller
   SOD-323 (SMF5.0A is a bulkier SOD-123 TVS sized for power rails, not a
   signal-adjacent VBUS pin on a consumer USB-C port -- no accuracy/energy
   case for the bigger part here). Both D3 and D4 sit on a NEW **`VBUS_RAW`**
   net (J5's own 4 VBUS pins were renamed off `VBUS`), i.e. ESD steering is
   closest to the connector, ahead of the entry bead (best practice).
2. **H3a ferrites**:
   - **(a) VBUS entry bead, POPULATED**: **FB1**, in series `VBUS_RAW` ->
     `VBUS` (the existing net, unchanged everywhere else -- D2 ORing diode,
     C9 bulk cap). **Corrected the register's MPN**: `MPZ2012S601ATD01` does
     not exist at LCSC (verified live); the real in-stock TDK part is
     **MPZ2012S601AT000, LCSC C21519** (0805, 600 ohm@100MHz, 2A, ~147k
     stock). Footprint reuses `cec-Capacitor_SMD:C_0805_2012Metric` (real
     0805/2012-metric land match, not cosmetic).
   - **(b) 5VSB port-VCC entry bead, 0R-default**: **FB2**, in series between
     J1 (RJ-45) pin 1 and the board's `+5VSB` rail. J1's own VCC wire was
     re-pointed to a new `VCC_RAW` net; the existing `+5VSB` power-flag symbol
     (#PWR01) was relocated to sit downstream of FB2. Populated with a 0R
     jumper (UNI-ROYAL 0805W8F0000T5E, LCSC C17477) on the same 0805 land as
     FB1 so a real bead swaps in later on EMC evidence.
   - **(c) CAN CMC position, DNP + required bypass**: **FL1** =
     `cec-vendor:CEC_CMC_4T` (shared symbol another parallel beta-splice agent
     already landed in `lib/vendor/cec-vendor.kicad_sym`; reused rather than
     inventing a competing one), DNP by default, in true series between the
     RJ-45-side CAN pair (`CAN_H`/`CAN_L`, unchanged) and the transceiver-side
     pair (renamed `CAN_H_INT`/`CAN_L_INT`, U2/TJA1051T/3 side only). **R22 +
     R23** (0R, UNI-ROYAL 0402WGF0000TCE, LCSC C17168) bridge FL1's H and L
     windings directly, populated by default -- per the coordinator's
     correction, a DNP 4-pin symbol still opens the netlist path (DNP only
     gates BOM/assembly, not connectivity), so the bypass is required for CAN
     to work out of the box while FL1 is DNP. Netlist-verified: `CAN_H` =
     {FL1.1, J1.3, R22.1}, `CAN_H_INT` = {FL1.3, R22.2, U2.7}; `CAN_L` =
     {FL1.2, J1.6, R23.1}, `CAN_L_INT` = {FL1.4, R23.2, U2.6} -- continuity
     through the populated bypass, proven from the exported netlist, not
     assumed. **Candidate part flag**: this board used TDK
     ACT1210L-101-2P-TL00 (LCSC C307643, verified live, CAN/FlexRay-rated
     1210 4-pin CMC); the EPS beta splice used TDK ACT45B-510-2P-TL003 (LCSC
     C76584) for the same slot -- both are DNP placeholders with no footprint
     vendored yet, but the two boards disagree on candidate MPN. Flag for the
     owner/coordinator to converge on one at BOM-freeze; no footprint exists
     for either yet so nothing is fab-blocking.
3. **J2 fan provision** (12VHPWR-specific, beta-lock-register §J2 / thermal
   menu item 2): 2-pin JST-XH header, DNP, position only. Reuses the
   platform's shared `cec:CEC_PWR_IN_2P` symbol (same part family as
   hub-standard's `J_5VSB`/`J_5V`, MPN JST S2B-XH-A(LF)(SN), LCSC C157931,
   footprint `cec-Connector_JST:JST_XH_S2B-XH-A_1x02_P2.50mm_Horizontal`) --
   that symbol's baked Description is Hub-specific boilerplate, overridden by
   this instance's own Value/Note. **Fan +12V tap is wired by a real drawn
   wire directly onto the existing pre-shunt node** at RS6's own `SENSEP6_HI`
   wire endpoint (394.97, 208.28) -- not a same-name label trick. Net-proof
   from the exported netlist: `/FAN_12V` = {J2.1, **J3.6**, R5.1, RFH6.1,
   **RS6.1**} -- J3 is the 12V-2x6 PSU-side connector (pin 6, one of its six
   +12V pins) and RS6 is that lane's shunt; the fan branches off the node
   BEFORE the shunt (Kirchhoff: current split at that node never crosses
   RS6), so fan draw cannot pollute the per-pin GPU-side current reading on
   any lane. (R5.1 is the existing rail-voltage-divider tap, already
   precedent for using this exact node as a non-sense, board-power purpose.)
   KiCad's ERC absorbed the label `SENSEP6_HI` into the canonical name
   `FAN_12V` for this merged net (ERC `multiple_net_names`, expected -- see
   Gates below); the net literally no longer exports under the old name,
   which is itself confirmation the tap sits on that exact node.
4. **Rev -> BETA-1**: added a `title_block` (none existed before) with
   `rev "BETA-1"`, dated 2026-07-03, and a revision-note comment. Alpha state
   preserved in git history; no fab/ snapshot needed renaming (proto-v1 stays
   as-is, this is a schematic-only forward rev).

## Gates

- **ERC**: before 68 violations (all `lib_symbol_mismatch`, pre-existing
  benign generator-cache noise per CLAUDE.md). After: 75 -- 74
  `lib_symbol_mismatch` (+6: D4, FB1, FB2, FL1, R22, R23, each the same
  pre-existing benign class every reused generic-shape part on this board
  already triggers; D3 and J2 add ZERO new mismatches since they embed
  byte-verbatim copies of real registered library symbols) + **1
  `multiple_net_names`** (the intentional FAN_12V/SENSEP6_HI merge described
  above -- ERC itself confirming the tap-point proof, not a defect). No other
  new ERC class. Exit code 5 both times (violations present), matching the
  pre-existing baseline posture.
- **Netlist**: `kicad-cli sch export netlist` exits 0 before and after; all
  key splice nets verified directly from the exported `.net` (see per-item
  proofs above): `VBUS_RAW`/`VBUS` split at FB1, `VCC_RAW`/`+5VSB` split at
  FB2, `CAN_H`/`CAN_H_INT` and `CAN_L`/`CAN_L_INT` split at FL1 with R22/R23
  continuity, `USB_DP`/`USB_DM` carrying D3, `FAN_12V` proof as above.
- **`--check-overlaps`**: baseline (original file) 399 pairs; final file 398
  pairs, with the diff against baseline showing only 6 lines that are the
  SAME pre-existing overlap (J5's 4 stacked `VBUS` labels at one point,
  4-choose-2 = 6 pairs) carried through the `VBUS`->`VBUS_RAW` rename -- not
  a new condition, same 4 stacked label objects, renamed. **Zero net-new
  overlap pairs** from the new components: iterated three times (FB2 vs the
  relocated `+5VSB` power-flag text, R22/R23 crowding each other and their own
  CAN_H/CAN_L labels, D3's left-side pin labels vs their own pin numbers, J2's
  FAN_12V label vs its own pin number, and J2 vs R22 once J2 landed in the
  same X column as the R22/R23 stack) until `--check-overlaps` showed no
  delta beyond the pre-existing renamed set. Fixes used: wider label-stub
  extension for crowded pin fan-out, shorter Value strings (`0R` instead of
  `0R (CAN_H bridge)` etc. -- detail lives in each part's `Note` property
  instead), and moving J2 to its own X column clear of the R22/R23 vertical
  stack.
- **BOM**: regenerated both `bom/bom.csv` (full, LCSC/MPN/Manufacturer
  columns, group-by Value+Footprint+MPN+LCSC+DNP) and
  `bom/12vhpwr-standard-BOM-jlcpcb.csv` (`--exclude-dnp`) via `kicad-cli sch
  export bom` with fields matched to the existing column layout. New lines
  present: D3, D4 (grouped with D1, same part), FB1, FB2, R22/R23 (grouped).
  FL1 and J2 correctly marked `DNP` in the full BOM and correctly absent from
  the JLCPCB (assembly) BOM.

## Placement -- needed at the beta layout pass (schematic-only pass, PCB
untouched)

- **D3, D4, FB1** placed schematically near the existing USB-C/flash cluster
  (x~547-664, same y-row as J5/D2/C9) -- real layout should put them
  physically adjacent to J5 for genuine ESD-entry proximity; today's
  schematic coordinates are for netlist/readability only.
- **FB2** sits schematically near J1 (RJ-45) at the board's existing
  power-in corner; real layout should keep it hard against J1 pin 1.
- **FL1 + R22 + R23** are a fresh cluster (x~560-680, y~452-508); real layout
  should place FL1 in the CAN pair's actual trace path between J1 and U2, and
  R22/R23 as short adjacent bypass jumpers. **FL1 has no vendored footprint
  yet** (1210 4-pin CMC) -- must be sourced/vendored before layout; also
  reconcile the ACT1210L vs ACT45B candidate-part disagreement with the EPS
  board first (see above).
- **J2** sits in its own column near the FL1/R22/R23 cluster for schematic
  tidiness; real layout should place it wherever the 12VHPWR module's thermal
  design (owner's J2 menu, beta-lock-register §J) puts the fan, with a short
  run back to the `/FAN_12V` (`/SENSEP6_HI`) tap -- the schematic imposes no
  physical constraint here, only the electrical one (must originate before
  RS1-RS6).
- **#PWR01** (`+5VSB` power flag) was relocated 30.48 mm on the schematic
  purely to make room for FB2 in series; real layout is unaffected (it's a
  symbolic flag, not a placed part).

## Files touched

- `modules/12vhpwr-standard/12vhpwr-standard-module.kicad_sch` (title_block
  added, 8 new component instances + wires/labels, 3 existing nets
  re-pointed, 1 power-flag symbol relocated, 4 shared library symbols
  embedded: `USBLC6-2SC6`, `CEC_PWR_IN_2P`, `FerriteBead_Small`,
  `CEC_CMC_4T`).
- `modules/12vhpwr-standard/bom/bom.csv`,
  `modules/12vhpwr-standard/bom/12vhpwr-standard-BOM-jlcpcb.csv`
  (regenerated).
