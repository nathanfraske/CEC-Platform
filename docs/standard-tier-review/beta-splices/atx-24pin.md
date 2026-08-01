# 24-pin ATX module -- BETA-1 splice (J6 reconciliation + RS4 Kelvin + H3/H3a suite)

Scope: `beta/atx-24pin-rev3/24pin-module.kicad_sch` (+ its BOM), plus
`docs/mezzanine-stack-design-2026-06-24.md` (the J6 pinout table, per the K1 gate's own
instructions) and `beta/atx-24pin-rev3/board-manifest.json`/`README.md`. `atx-24pin/`
(shipped alpha) and `atx-24pin-rev2/` untouched. PCB untouched -- still byte-identical to
`atx-24pin-rev2`'s fully-placed/routed layout, which predates every change below (no mux, no
mezzanine header, no C6, no H3 suite, no Kelvin RS4). Layout starts fresh from this schematic.

## 1. J6 mezzanine pin-map reconciliation (K1 gate) -- CLOSED, no schematic change

Extracted both maps completely and diffed pin-by-pin:

| Pin | Design doc (2026-06-24 draft) | rev3 J6 (as-built) | hub-rev2 J_MEZZ (as-built) | Verdict |
|---|---|---|---|---|
| 1 | +5VSB | +5V_SYS | +5V_SYS (net `+5VSB` locally, pre-mux) | MATCH (signal role identical, name updated for the mux) |
| 2 | +5VSB | +5V_SYS | same | MATCH |
| 3 | GND | **+5V_SYS** | **+5V_SYS** | **SCHEMATIC WINS** |
| 4 | GND | GND | GND | MATCH |
| 5 | CAN_H | CAN_H | CAN_H | MATCH |
| 6 | CAN_L | CAN_L | CAN_L | MATCH |
| 7 | GND | GND | GND | MATCH |
| 8 | GND | **STREAM_P** | **STREAM_P** | **SCHEMATIC WINS** |
| 9 | STREAM_P | **STREAM_N** | **STREAM_N** | **SCHEMATIC WINS** |
| 10 | STREAM_N | **GND** | **GND** | **SCHEMATIC WINS** |
| 11 | GND | **DETECT** | **DETECT** | **SCHEMATIC WINS** |
| 12 | GND | GND | GND | MATCH |
| 13 | DETECT | **RSVD** | **RSVD** | **SCHEMATIC WINS** |
| 14 | RSVD | **GND** | **GND** | **SCHEMATIC WINS** |
| 15 | +5VSB | **GND** | **GND** | **SCHEMATIC WINS** |
| 16 | GND | GND | GND | MATCH |

Evidence trail: traced every J6 net through the rev3 schematic (confirms the "SCHEMATIC WINS"
column is the board's real, ERC-clean, netlist-verified state). Then checked the one artifact
that must physically mate with rev3's J6: `hubs/hub-rev2/hub-rev2.kicad_sch`'s J_MEZZ (the
mirrored socket). Its generator (`scripts/gen-hub-rev2.py`) hard-codes the IDENTICAL pin
assignment as rev3's `gen-24pin-rev3.py` (`+5V_SYS` on 1/2/3, `GND` on 4/7/10/12/14/15/16,
`CAN_H`=5, `CAN_L`=6, `DETECT`=11), and its commit (2026-06-24 19:05) landed ~50 minutes AFTER
rev3's final pinout-verify commit (18:14) -- i.e. the real mated hardware pair was built
self-consistently from the START, independently of the earlier (13:58) design-doc draft, which
was never actually implemented on either side. No pin was genuinely ambiguous; every conflict
resolved the same direction (schematic pair correct, doc stale), so no OWNER-DECIDES items.

**Fix applied**: corrected `docs/mezzanine-stack-design-2026-06-24.md` section 3's pinout table
to the as-built map (old table kept in a collapsed `<details>` block for provenance). **The
schematics (rev3 J6, hub-rev2 J_MEZZ) were NOT touched** -- they already agreed with each other;
re-pinning either would have broken a working, already-mated pair for no reason. Updated
`board-manifest.json`'s `errata_rev3` entry from OPEN to RESOLVED with the full evidence chain.

## 2. RS4 -> true 4-terminal Kelvin land (B4)

RS4 (5VSB, 25 mOhm) was `cec-vendor:R_Small` on the 2-pad `R_2512_6332Metric` land -- current
path and INA228 Kelvin sense shared the same two schematic nodes (correct for the platform's
Bourns CSS2H 2-pad convention, but the LOCKED part here is the Vishay WSK2512, a genuine
4-terminal part). Fixed to `cec-vendor:CEC_SHUNT_4T` (already vendored, used by the alpha
board's RS6) on footprint `cec-Resistor_SMD:R_Shunt_Vishay_WSK2512_6332Metric_T1.19mm` (also
already vendored). Split the current path from the Kelvin sense onto four real schematic nodes:

- Pin 1 (I1, current HI) -> `+5VSB` (unchanged bulk node, J3.9)
- Pin 4 (I2, current LO) -> `SENSE5VSB_LO` (unchanged bulk node, J4.9 pass-through)
- Pin 2 (S1, Kelvin sense HI) -> **new** `SENSE5VSB_HI` -> U13 (INA228) Vin+ (pin 10)
- Pin 3 (S2, Kelvin sense LO) -> **new** `SENSE5VSB_LO_KELVIN` -> U13 Vin- (pin 9)

U13's Vin+ was previously riding the bulk `+5VSB` busbar directly and Vin- was riding the bulk
`SENSE5VSB_LO` alongside the load-side pass-through -- both now sense off the shunt's OWN
dedicated pads instead, which is the point of a 4-terminal part. Sourced Manufacturer=Vishay,
MPN=WSK2512R0250FEA (matches the alpha board's RS6 line and the spec's OQ-11 lock). Netlist
verified pin-by-pin (see below). RS1-3 (Bourns CSS2H, 2 mOhm rails) are untouched -- the task
scoped only RS4, and CSS2H parts are the platform's own 2-pad convention, not a defect.

## 3. W11/H3 standalone-mode suite + H3a ferrites

Sensing check first: rev3 already carries 4x INA228 (U10-U13, confirmed by Value grep) -- the
K2 working-basis default is already what's built, no change needed.

Added (new section, "H3 STANDALONE-MODE SUITE", schematic bumped to A2 paper for room):

- **D_USB = USBLC6-2SC6** (LCSC C7519) on the USB pair, wired exactly like the Hub's D6
  reference (`hub-standard.kicad_sch`): I/O1 (pins 1,6) -> `USB_DP`, I/O2 (pins 3,4) ->
  `USB_DM`, VBUS (pin 5) -> `VBUS_RAW`, GND (pin 2) -> `GND`. Shunt-style tap, not inline.
- **D7 = PESD5V0S1BA** (LCSC C5261083) as the VBUS clamp: cathode -> `VBUS_RAW`, anode -> `GND`.
  Judgment call, flagged not silently assumed: reused the platform's existing 5V0 single-line
  ESD/TVS part (the same one already on every DETECT pin) rather than introducing a new MPN,
  since it is the platform's standard low-cap 5V clamp and the H3 ruling doesn't name a specific
  part.
- **FB1 = ferrite bead, POPULATED** (`cec-vendor:FerriteBead_Small`, new symbol, footprint
  borrows the existing `cec-Capacitor_SMD:C_0805_2012Metric` 0805 land): in series between J5's
  raw VBUS and the rest of the board (D2 ORing diode / C9 bulk cap), splitting `VBUS_RAW`
  (connector + ESD side) from `VBUS` (unchanged downstream net). MPN corrected per the
  coordinator's pattern-correction to the real, stocked part: **MPZ2012S601AT000, LCSC C21519**
  (TDK) -- matches `eps-8pin`'s choice for platform consistency; the earlier "MPZ2012S601A"
  (no suffix) and the lock register's "...ATD01" are not real orderable MPNs.
- **FB2 = 0R-default port-entry bead** (same `FerriteBead_Small` symbol/land): in series between
  the mux's `+5V_SYS` output and the port boundary, splitting `+5V_SYS` (board-internal: LDO,
  CAN transceiver, mux loads) from **new** `+5V_SYS_PORT` (feeds both J2.1 and J6.1/2/3).
  **Judgment call, flagged**: the 24-pin's RJ-45 VCC is locked NC (spec Sec.2.7 v3.3 -- no
  incoming 5VSB over the port), so unlike EPS/PCIe/12VHPWR (which get 5VSB IN from the Hub over
  the RJ-45 and place their port bead there), this module's only analogous "port" boundary is
  its own `+5V_SYS` OUTPUT to the JST/mezzanine cable -- the bead sits there instead. MPN matches
  `eps-8pin`'s FB2 for platform consistency: UNI-ROYAL 0805W8F0000T5E, LCSC C17477 (read
  out-of-stock at verification -- any generic 0R 0805 jumper substitutes, flag at BOM-freeze).
- **FL1 = CAN common-mode-choke position, DNP** (`cec-vendor:CEC_CMC_4T` -- the shared symbol
  another agent already added; my own draft `CommonModeChoke_Small` was removed from
  `lib/vendor/cec-vendor.kicad_sym` to avoid a competing definition). Pins 1(H_IN)/2(L_IN) ->
  new `CAN_H_BUS`/`CAN_L_BUS` (J1 + J6, the RJ-45/mezzanine bus side); pins 3(H_OUT)/4(L_OUT) ->
  unchanged `CAN_H`/`CAN_L` (U2/TJA1051T-3 side). Real-part candidate matches `eps-8pin`'s
  choice: TDK ACT45B-510-2P-TL003, LCSC C76584 (CAN-bus-rated SMD-4P, 51 uH/line). No footprint
  assigned -- none exists in `lib/vendor` yet (required lib addition before layout/BOM; per the
  task's own discipline for RS4's footprint, not hand-fabricated here).
  **Coordinator correction applied**: a DNP series CMC electrically OPENS the CAN pair on the
  real board (KiCad's netlist treats the symbol as always-connected regardless of `dnp`, so
  ERC/netlist can't catch this). Added **R_BYP_H / R_BYP_L = 0R, POPULATED by default**
  (`cec-vendor:R_Small`, `cec-Resistor_SMD:R_0402_1005Metric`, UNI-ROYAL 0402WGF0000TCE, LCSC
  C17168 -- matches `eps-8pin`'s bypass part) bridging each CMC channel in parallel
  (`CAN_H_BUS`<->`CAN_H`, `CAN_L_BUS`<->`CAN_L`). Default population = bypassed/continuous;
  populating FL1 for real EMC insurance means removing both 0R jumpers.
- Per H3a(d): no series ferrite on USB D+/D- (SI killer) -- none added, matches the ruling.

## 4. Output-form note (K2 working basis, D-5a)

Added a schematic text note next to J4 (the ATX output connector): "OUTPUT FORM (J4) = WORKING
BASIS, not final. D-5a owner lean: very short captive stub + order-time optional extension...
Swappable section pending the formal form ruling." J4 itself is untouched (still the placeholder
male Mini-Fit Jr header) -- no redesign of the output interface this pass, per instruction.

## 5. Discovered-and-fixed: J2 was still on the stale `+5VSB` input

While tracing nets for the FB2 placement, found J2 (the Hub-power JST, "TO-HUB-PWR") pin 1 was
still wired to the OLD `+5VSB` input net, never migrated to the mux's `+5V_SYS` output --
contradicting the respin doc's own explicit stated intent ("the 24-pin's Hub-power output (J2 +
the mezzanine power pins) move from +5VSB -> +5V_SYS") and the fact that J6 (the mezzanine
header) HAD already made that move. This is directly load-bearing for where FB2 belongs, so
fixed it in the same pass: J2 pin 1 now on `+5V_SYS_PORT` (via FB2), consistent with J6.

## 6. Rev -> BETA-1

Added a `title_block` (none existed before) with `rev "BETA-1"`, matching the convention already
landed on `hub-standard.kicad_sch` by a concurrent agent this session. Rewrote the stale
scaffold-era README (which still described a "not yet implemented" 2026-06-24 state and a
"synced copy, do not edit" convention that no longer applies) to the current BETA-1 status.

## Gates

- **ERC before/after**: baseline (HEAD@38ff2e6) = 101 violations (0 errors: 1 `pin_not_driven`,
  43 `lib_symbol_mismatch`, 4 `footprint_link_issues`, 53 `pin_to_pin`, all pre-existing/benign
  per the platform's own established convention). Final = 107 (same 4 categories; the +6
  `lib_symbol_mismatch` are one-per-new-part-instance, the identical benign pattern already
  covering every other component in this file -- not a new class of issue). **0 new errors, 0
  new structural violations.**
- **Netlist assertions per splice**: RS4 (pins 1/4 current, 2/3 Kelvin sense, verified against
  U13's Vin+/Vin-), J2/J6 (`+5V_SYS_PORT` = {FB2.2, J2.1, J6.1, J6.2, J6.3}), CAN split
  (`CAN_H_BUS`={FL1.1, J1.3, J6.5, R_BYP_H.1}, mirrored for L), VBUS split (`VBUS_RAW`={D7.1,
  D_USB.5, FB1.1, J5 VBUS pins}), USB shunt (D_USB on `USB_DP`/`USB_DM`, unchanged) -- all
  confirmed via `kicad-cli sch export netlist`.
- **J6 reconciliation table**: complete, 16/16 pins, per-pin verdict (§1) -- no OWNER-DECIDES
  items; the mated-pair evidence was decisive on every conflicting pin.
- **`--check-overlaps`**: baseline 195 -> final 209 (+14 new pairs), all cosmetic
  text/silk-label proximity in the freshly-added areas (new components placed close together
  in the new H3 section; RS4's own Value text vs. its new Kelvin-sense labels; a few renamed
  pre-existing clashes like `+5V_SYS`/MEZZANINE-caption and the USB-C connector's inherent
  4-shared-pin VBUS self-overlap, both already present in baseline under the old net names).
  One clear fix already applied (moved the "OUTPUT FORM" note off RS4's Value text, -3 pairs from
  an initial +17). Residual is schematic-readability only -- no copper/DRC impact, and this
  board's PCB gets a from-scratch layout pass regardless (per the module's own current state).
- **BOM regenerated**: `beta/atx-24pin-rev3/bom/bom.csv` (65 rows), confirms `FL1` correctly
  flagged DNP, all new refs present with footprints/values.

## Known residue (not fixed this pass, flagged)

- CMC (`FL1`) has no footprint yet -- required lib addition (a real 4-pad CMC land) before
  BOM-freeze/layout, matching the RS4-style discipline the task specified.
- The board's pre-existing "schematic has annotation errors" / reference-annotation quirk
  (`D_USB`, `R_BYP_H`, `R_BYP_L` show a `?` suffix in the BOM export since they don't end in a
  digit) is cosmetic and was already present/documented for this board before this pass;
  left as-is rather than risk a wider re-annotation under this task's scope.
- ~14 residual cosmetic schematic-text overlaps in the new H3 area (see Gates above) -- a GUI
  silk-tidy item, not a structural defect; the PCB layout pass will redraw this area regardless.
