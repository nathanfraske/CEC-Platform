# PCIe 8-pin modules (2-port + 3-port) -- BETA-1 splice (W11/H3a + W5)

Scope: `modules/pcie-8pin-2port/pcie8pin-2port-module.kicad_sch` and
`modules/pcie-8pin-3port/pcie8pin-3port-module.kicad_sch` (+ their BOM CSVs,
`.kicad_pro` net_settings, new `.kicad_dru`). Both boards are placement-complete
/ zero-copper (per `docs/standard-tier-review/pcie-8pin.md`); this pass is
schematic + project-file only, applied identically to both SKUs since their
"electronics core" (J1/J5/D1/D2/U1/U2/U3 etc.) sits at IDENTICAL coordinates in
both files. A title block (`Rev "BETA-1"`) was also added to both `.kicad_pcb`
files (metadata only -- DRC-verified as a zero-structural-impact edit) since
the board itself changed generation, even though no copper moved.

Splice discipline followed throughout: hand-edited the existing generator-built
schematics (never regenerated via `gen-pcie-condensed.py`), one Python splice
script (`scratchpad/splice_pcie_h3.py`) applied the same edit set to both files
so they stay byte-parallel in structure, and every gate below was re-verified
after a mid-flight correction (see "Coordinator correction" below).

## What landed (identical on both SKUs)

1. **W11/H3 standalone suite**: **D3 = USBLC6-2SC6** (LCSC C2687116), wired
   exactly like the Hub's D6 reference (`hub-standard.kicad_sch`) -- a
   shunt/tap ESD device on the USB pair, not a series element. Taps
   `USB_D_P`/`USB_D_N` (the renamed nets, see item 3), `VBUS`, and `GND`. Per
   the ST datasheet, USBLC6-2SC6 steers ESD current to both VBUS and GND, so
   this one part reads as satisfying both "USB D+/D- ESD" and a VBUS-side
   steering path; a SEPARATE dedicated VBUS TVS was still added (next item) to
   match the register's explicit "USBLC6-2SC6 ... VBUS-side clamp" wording as
   two distinct devices rather than assuming USBLC6-2SC6 alone covers both.
2. **D4 = VBUS-side TVS clamp**: reused the platform's existing
   **PESD5V0S1BA** (LCSC C5261083) on the generic `D_Schottky` symbol -- the
   same part/symbol pattern D1 already uses for the DETECT-pin clamp -- rather
   than introducing a new part number. Cathode -> `VBUS` (downstream of FB1,
   i.e. the board-side node), anode -> GND.
3. **H3a ferrites** (using the shared `cec-vendor:FerriteBead_Small` symbol
   landed by a concurrent agent -- adopted per coordinator instruction instead
   of a competing R_Small-based representation I had drafted first):
   - **(a) VBUS entry bead, POPULATED**: **FB1**, true series break between
     J5's 4 VBUS pins (renamed `VBUS_J5`) and the rest of the board (`VBUS`:
     C9 bulk cap, D2 ORing diode anode, D3/D4 taps). Real part **TDK
     MPZ2012S601AT000, LCSC C21519** (600R@100MHz, 0805/2012 metric, 2A,
     37k+ stock -- verified live 2026-07-03). The register's stated MPN
     **"MPZ2012S601ATD01" does not exist** in TDK's or LCSC's catalog; T000 is
     the electrically identical, in-stock reel-packaging variant. Footprint
     `cec-Capacitor_SMD:C_0805_2012Metric` (the shared symbol's own convention
     -- same 0805 pad envelope, not a purpose-drawn bead land).
   - **(b) 5VSB / RJ-45 VCC-entry bead position, 0R DEFAULT**: **FB2**, true
     series break between J1 pin 1 (VCC) -- renamed `VCC_J1` -- and the
     board's `+5VSB` net. Populated by default (Value `0R`, no LCSC yet --
     any generic 0805 0R jumper; flag at BOM-freeze), same C_0805 land as FB1
     so a real bead swaps in later on EMC evidence without a footprint change.
   - **(c) CAN pair common-mode-choke position, DNP by default**: **FL1**
     (`cec-vendor:CEC_CMC_4T`, the shared 4-pin CMC placeholder symbol I added
     this pass -- pins 1/2 = H/L in, 3/4 = H/L out, one part couples both
     lines through a shared core). True series break between J1 pins 3/6
     (renamed `CAN_H_J1`/`CAN_L_J1`) and the board's `CAN_H`/`CAN_L` (TJA1051T/3
     side, unchanged). No footprint/MPN assigned yet (H3a is explicitly
     "judicious not blanket" -- not yet part-searched).

## Coordinator correction applied: R11/R12 CAN bypass pair

Mid-task, the coordinator flagged (after the EPS agent's landing surfaced the
same issue) that **KiCad's netlist/ERC treats a DNP symbol as electrically
present regardless of the manufacturing flag** -- so a bare series-DNP FL1
would ship with the CAN pair genuinely OPEN through J1 on every unpopulated
board, silently breaking the platform's control bus with no ERC/DRC signal.
Fixed identically on both SKUs: **R11 and R12**, generic `R_Small` 0R jumpers
(0402, no LCSC yet), **populated by default** (`dnp no`), each bridging one
line in parallel with FL1 (R11: `CAN_H_J1`<->`CAN_H`; R12: `CAN_L_J1`<->`CAN_L`).
Default shipped state = bypassed-continuous (R11/R12 fitted, FL1 empty); the
EMC-populated variant removes R11/R12 and fits FL1. Verified from the exported
netlist on both boards:
`/CAN_H_J1 = {FL1.1, J1.3, R11.1}` -> `/CAN_H = {FL1.3, R11.2, U2.7}` (and the
L-line mirror) -- continuity holds through the populated R11/R12 path with FL1
DNP, exactly the intended default-safe behavior.

Two shared-library naming notes for the owner/next agent to reconcile: (1) a
duplicate `CommonModeChoke_Small` symbol another agent had also added was
since removed from `cec-vendor.kicad_sym` by that agent's own landing, leaving
`CEC_CMC_4T` as the sole CMC symbol (no action needed here, just confirmed no
collision remains); (2) the EPS splice named its equivalent nets
`CAN_H_RJ`/`CAN_L_RJ`/`VBUS_RAW` where this pass used
`CAN_H_J1`/`CAN_L_J1`/`VBUS_J5` -- purely cosmetic (each board's net namespace
is independent), left as-is rather than churning either board to match the
other, but flagged for anyone doing a cross-board audit.

## W5: netclass / `.kicad_dru` / USB `_P`/`_N` rename (EPS pattern, both SKUs)

- Renamed `USB_DP`/`USB_DM` label text to `USB_D_P`/`USB_D_N` on both boards
  (3 label instances each) so KiCad's diff-pair router auto-recognizes the
  pair, exactly mirroring EPS's prior pass.
- Both `.kicad_pro` files now carry the full 7-netclass set (`Default`,
  `Power12V` -> `/SENSEC*`, `GND`, `Power` -> `+3V3`/`+5VSB`/`VBUS`/`VBUS_J5`/
  `VCC_J1`, `Signal`, `CAN` -> `/CAN_H`/`/CAN_L`/`/CAN_H_J1`/`/CAN_L_J1`, `USB`
  -> `/USB_D_P`/`/USB_D_N`), values identical to EPS's. The 2-port `.kicad_pro`
  was previously a bare `{}` (no `net_settings` at all) -- brought to the same
  minimal EPS-style shape (`{"net_settings": {...}}` only). The 3-port
  `.kicad_pro` already had a `Default`-only `net_settings` plus a fuller
  outer structure (board/meta/etc. from an earlier generator run); that outer
  structure was preserved and only `net_settings` replaced, and a stale
  `meta.filename` ("pcie8pin-module.kicad_pro", a copy-paste leftover) was
  corrected to the real per-SKU filename.
- New `pcie8pin-{2,3}port-module.kicad_dru`, textually identical to EPS's
  (Power-class 0.5mm floor, no floor on Power12V, USB diff-pair gap rule, the
  CAN hand-route note) with an added note explaining the `_J1` split.

## Rev -> BETA-1

Both `.kicad_sch` AND `.kicad_pcb` gained a `(title_block ...)` (title/date
2026-07-03/rev "BETA-1"/comment) -- neither board had a title block at all
before this pass on ANY of the four files. The PCB comment explicitly flags
that the new parts are schematic-only this pass (not yet placed) so a reader
of the board alone isn't misled.

## Gates (identical methodology both boards; a fair worktree-based `HEAD`
baseline was used throughout, not a bare git-show copy, since the project's
`fp-lib-table` uses `${KIPRJMOD}`-relative paths that only resolve at the
real repo depth)

- **ERC before/after**: baseline 100 (2-port) / 119 (3-port) violations, all
  `pin_not_driven`(1) / `pin_not_connected`(1) / `lib_symbol_mismatch`
  (45/54) / `pin_to_pin`(53/63, benign SOIC/VSSOP silent-pin noise). After:
  106 / 125, with `pin_not_driven`/`pin_not_connected`/`pin_to_pin` UNCHANGED
  and `lib_symbol_mismatch` +6 on each board -- confirmed by set-diff to be
  exactly the 6 new instances (D4, FB1, FB2, FL1, R11, R12) reusing already-
  embedded/shared symbols, the identical benign class documented platform-wide
  (a generator-cache artifact, not a real defect). Zero new violation *types*.
- **Netlist assertions per splice + rename connectivity-identity proof**: for
  every edit, checked `old_node_set <= new_combined_node_set` with the only
  deltas being the intended new taps -- `USB_DP`/`USB_DM`'s exact pre-rename
  node sets are subsets of `USB_D_P`/`USB_D_N` (extra = D3 only); `VBUS`'s
  pre-split set is a subset of `VBUS_J5 union VBUS` (extra = D3/D4); `CAN_H`/
  `CAN_L`'s pre-split sets are subsets of their `_J1`+downstream unions (extra
  = FL1/R11 or FL1/R12); `+5VSB`'s pre-split set is a subset of `+5VSB union
  VCC_J1` (extra = FB2/PWR203). All PASS, both boards, identically. DETECT
  (pin 8, locked table) and the RS-485 pair (4/5, correctly unconnected on
  Standard) are untouched.
- **`--check-overlaps`, no new pairs**: baseline 37 (2-port) / 43 (3-port).
  Final: 36 / 42 -- net FEWER than baseline on both (one pre-existing
  `+5VSB Value <-> CAN_H label` collision at J1 disappeared when that spot
  became a plain `VCC_J1` label; the 6 pre-existing stacked-duplicate `VBUS`
  labels at J5 just carry the renamed `VBUS_J5` text now). Getting to zero-new
  took two real fixes, noted for future splices reusing this pattern: (1) a
  label placed with `justify` pointing *toward* a neighboring label (rather
  than away, outward from the part) collides with it well before the anchors
  themselves touch -- text bbox width for a 7-char label at 1.27mm font is
  ~9mm, more than half the ~10-18mm gaps used here; (2) stacking multiple new
  parts' Reference/Value text along one column (I first tried this for
  R11/R12 under FL1) collides at typical +/-15.24mm field offsets unless rows
  are >30mm apart -- switched to separate X columns instead of stacked rows.
- **BOM CSVs regenerated**: both `-BOM-jlcpcb.csv` re-exported
  (`--exclude-dnp`, matching the existing grouped Comment/Designator/
  Footprint/LCSC format). FL1 correctly excluded (DNP); D1+D4 correctly
  grouped (same PESD5V0S1BA line); R11+R12 grouped as the bypass pair.

## New-part placement needs for W6 (both boards are zero-copper; nothing here
changes that state)

Seven new components per board need a placement home in the eventual routing
pass: **D3** (USBLC6-2SC6, SOT-23-6, near J5), **D4** (PESD5V0S1BA, SOD-323,
near the VBUS node), **FB1** (0805, in the VBUS entry path right off J5),
**FB2** (0805, in the +5VSB path right off J1 pin 1), **FL1** (CMC, footprint
TBD -- blocks layout until a real part is sourced), **R11/R12** (0402, tight
to FL1's pads so the bypass trace lengths stay negligible). None of the seven
are placed in `.kicad_pcb` yet -- they exist only in the schematic/netlist
this pass, exactly like the rest of the two boards' W11/H3a scope.

## Open items / owner flags

- **FL1's real MPN/footprint is still unsourced** -- per H3a's own "judicious,
  not blanket" framing, no CMC part search was done this pass; needed before
  W6 layout can place it (even DNP positions need a footprint to reserve
  copper/keepout).
- **FB2 and R11/R12's 0R jumpers have no LCSC line yet** -- generic/any-vendor
  0R parts, flag at BOM-freeze like the platform's other still-open sourcing
  gaps (e.g. OQ-11's shunt).
- The `CAN_H_J1`/`VBUS_J5` vs. EPS's `CAN_H_RJ`/`VBUS_RAW` net-naming
  divergence (noted above) is cosmetic but worth a one-time owner ruling on a
  platform-wide convention if more modules pick up this same H3a pattern.
