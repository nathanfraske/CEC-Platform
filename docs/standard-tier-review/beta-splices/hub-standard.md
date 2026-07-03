# Hub Standard -- BETA-1 splice (A4 power-in consolidation, W12 comparator, H2 DNP ladder)

Scope: `hubs/hub-standard/hub-standard.kicad_sch` (+ its BOM CSVs). PCB (`.kicad_pcb`)
untouched -- this pass is schematic-only per the task; a placement/route pass for the
new parts is a separate follow-up. Splice discipline followed: hand-edited the existing
hand-maintained schematic via targeted s-expr splices (never ran the GUARDED-STALE
`gen-hub-standard.py`). New footprints (JST S3B-XH-A 1x03, SOT-563, L_0603) and the new
symbols (`CEC_PWR_IN_3P`, `L_Small`, `TPS61023DRLR`, `TPS563201DDCR`) were vendored/added
to `lib/cec.kicad_sym` and `lib/vendor/cec-vendor.kicad_sym` (append-only, at the end of
each file) so the parts resolve outside the schematic's own embedded cache too.

## 1. A4 -- power-in consolidation

Deleted `J_5VSB` (2-pin, 5VSB_IN) and `J_5V` (2-pin, MAIN_5V_IN) plus their dedicated
GND flags and stub wires. Added **J_PWR = JST S3B-XH-A, LCSC C157928** (3A, verified
live in stock) at the old `J_5V` location. Pin order **1=MAIN_5V, 2=GND (center),
3=5VSB** -- matches the register's GND-center ask (misinsertion-benign) and the real
part's physical pinout (pad 2 is the geometric center pad). Net names unchanged
(`MAIN_5V_RAW`, `GND`, `5VSB_RAW`).

**Connectivity assertion (netlist-verified):**
- `/MAIN_5V_RAW` = `{J_PWR.1, R15.1, U7.6, U7.7}` -- J_PWR now sits alongside the
  existing MAIN_5V_RAW consumers (R15 sense divider, U7 TPS2121).
- `/5VSB_RAW` = `{C9.1, J_PWR.3, R17.1, U5.6, U5.7}` -- same pattern.
- `/GND` (single 83-member net) includes `J_PWR.2`.
- Deleting the old connectors left one loose end: C9's 5VSB_RAW filter cap was fed by
  a wire whose OTHER end (the old J_5VSB stub) is gone. Fixed by sliding that label onto
  the *midpoint* of the still-standing vertical wire down to C9 (kept, not deleted) --
  C9 stays on the global net without any new physical wire.

## 2. W12 -- 5V-drop comparator (owner ruling H1)

**U8 = TLV7011DBVR** (already a platform part, LCSC C702117, populated/not DNP).
- **IN+** taps the *existing* R15/R16 47k/10k `MAIN_5V_SENSE` divider node (same node the
  ESP32 ADC IO9 already reads) -- no new sense tap, shares the node via net-name match.
- **IN-** = a new **R26 (34.0k, 1%, LCSC C48939) / R27 (10.0k, 1%, LCSC C25744)** divider
  off `+3V3`, forming `COMP_THRESH`. Both LCSC numbers verified live.
  **Threshold math:** MAIN_5V_SENSE = `V_rail * 10/(47+10) = V_rail * 0.1754`.
  Picking the register's ~0.75V trip: `COMP_THRESH = 3.3 * 10/(34.0+10) = 3.3 * 0.2273 =
  0.75 V` (exact with these two values) -> trips when `V_rail = 0.75 / 0.1754 = 4.28 V`
  (~4.3V, matches the register's number).
- **R28 = 1M** hysteresis feedback, OUT -> `COMP_THRESH` (the *new* reference node, not
  the shared `MAIN_5V_SENSE` node -- keeps the ADC path on that shared node undisturbed).
- **C17 = 100nF** VCC decoupling (Samsung CL05B104KO5NNNC, C1525 -- the platform's
  standard 100nF line).
- **OUT -> `/PWR_FAIL_INT`.** GPIO candidate: **not yet assigned to a specific ESP32 pin**
  -- I did not find a free/unused GPIO by direct inspection of every U1 net in this pass
  (the ESP32-S3-WROOM-1 has ~140 other nets on this board). Candidates worth checking at
  the PCB/firmware pass: any ADC2 channel not already claimed by IO1/IO2 (KVM ratio),
  IO3 (TEMP_HUB), IO9/IO10 (MAIN_5V/5VSB sense), IO11/IO12 (KVM UART), IO13/IO14 (if
  free) -- **flagged, not assumed**; firmware/PCB pass must confirm and bind the pin.

**Connectivity assertion:** `/PWR_FAIL_INT = {R28.1, U8.1}`, `/COMP_THRESH =
{R26.2, R27.1, R28.2, U8.4}`, `/MAIN_5V_SENSE = {R15.2, R16.1, U1.17, U8.3}` -- U8 added
to the existing sense net without displacing U1's own connection.

## 3. H2 -- rung-3 hold-up DNP ladder (position-only insurance)

**RJ_HOLD** (0R, UNI-ROYAL 0402WGF0000TCE C17168, **populated**) now carries what used
to be a bare wire: U3(LDO).IN was hard-labeled `+5V_HOLD`; that one label (only, at the
far end of its existing wire chain -- the chain itself, and U3's pins, were never
touched) is renamed `LDO_IN`, and RJ_HOLD bridges `+5V_HOLD -> LDO_IN`. Electrically
identical to pre-splice (0R jumper = a wire), so **"keep the existing LDO path fully
intact and populated" holds exactly** -- verified via netlist: `/LDO_IN = {C2.1,
RJ_BUCK.2, RJ_HOLD.2, U3.1}`, `/+5V_HOLD = {C1.1, D1.1, RJ_HOLD.1, U3.3, U9.3}`.

**RJ_BUCK** (0R, same MPN, **DNP**) is the alternate: `HOLD_BUCK_OUT -> LDO_IN`.
**Isolation assertion:** `/HOLD_BUCK_OUT = {L2.2, RJ_BUCK.1}` only -- two members, no
path to `LDO_IN` except through RJ_BUCK's own (unpopulated) footprint. On the real board,
with RJ_BUCK not populated, `HOLD_BUCK_OUT` and `LDO_IN` are two disjoint copper islands;
the schematic necessarily *shows* them net-bridged at RJ_BUCK's position (that is what a
jumper position is), but no current can cross an empty footprint. To move to rung 3:
desolder RJ_HOLD, populate RJ_BUCK + the rest of this ladder.

**U9 = TPS61023DRLR** (boost, SOT-563, LCSC C919459, DNP): VIN=`+5V_HOLD`, GND=`GND`,
EN -> **R29** (100k pulldown, DNP, default-disabled) -> `GND`, VOUT=`+HOLD_BOOST`.
FB and SW are genuine **`no_connect`** flags (not stray labels -- ERC's
`isolated_pin_label` check caught my first draft using bare labels here; a real
no-connect is the correct idiom for "reserved, not wired this pass").
**Flagged, not silently resolved:** TPS61023's own datasheet caps adjustable VOUT at
**5.5V** -- it cannot reach the register's literal "~12V" reservoir target. Either the
rung-3 target is revised to ~5.5V with this exact part, or a higher-Vout boost
(TPS61088-class) replaces it at the OQ-56 bench pass. FB divider, inductor, and bulk
caps are intentionally not populated in this position-only pass.

**U10 = TPS563201DDCR** (wide-Vin 4.5-17V buck, SOT-23-6, LCSC C116592, DNP):
VIN=`+HOLD_BOOST`, GND=`GND`, SW=`BUCK_SW`, EN -> **R30** (100k pullup, DNP) ->
`+HOLD_BOOST` (active-high enable per datasheet), VFB and VBST are real `no_connect`
flags for the same reason as U9's FB/SW. **L2** (inductor, DNP, value marked "TBD --
OQ-56 bench") bridges `BUCK_SW -> HOLD_BUCK_OUT` -- the one supporting passive kept in
this pass, because without it RJ_BUCK's alternate source would have no real node to
name.

**Connectivity assertions:** `/+HOLD_BOOST = {R30.2, U10.3, U9.6}` (boost output feeds
buck input + the EN pullup), `/BOOST_EN = {R29.1, U9.2}`, `/BUCK_EN = {R30.1, U10.5}` --
none isolated, all real 2-member nets.

**Residual analog caveat (surfaced, not fixed here):** U3's own **EN pin (pin 3)** is
tied directly to raw `+5V_HOLD` (a pre-existing board decision, unrelated to this
splice), while IN (pin 1) now rides the safely-regulated `LDO_IN`. In a populated
rung-3 future, EN would see the boosted (up to ~5.5V, or more with a swapped part)
`+5V_HOLD` while IN sees the bucked-down `LDO_IN` -- worth a bench check of the LDO's
EN abs-max at rung-3 populate time.

## 4. Rev / title block

Added a `title_block` (none existed before) with `rev "BETA-1"`, `date "2026-07-03"`,
and a `comment 1` summarizing all three splices. Added an on-sheet `text` annotation
near the new parts (x=438, y=321) with the same summary + a pointer to this file.

## 5. Gates

- **ERC before:** 60 violations (58 `lib_symbol_mismatch` + 2 `endpoint_off_grid`,
  both documented pre-existing/benign).
- **ERC after:** 85 violations -- **69 `lib_symbol_mismatch`** (+11, expected: new part
  types now cached, same benign class), **13 `pin_to_pin`** (new class, but *not* a
  defect: it's "Unspecified vs Passive" pin-type warnings from TLV7011/TPS61023/
  TPS563201's datasheet-accurate "unspecified"-typed pins meeting generic R/C/L
  "passive" pins -- verified this is the SAME pattern already present on the committed
  EPS module, which independently shows 53 of these from its own TLV7011 usage), **2
  `endpoint_off_grid`** (the identical pre-existing FLG200/FLG201 pair, untouched),
  **1 `no_connect_connected`** (a PRE-EXISTING latent issue at J5's RJ-45 area --
  `(no_connect (at 570.23 205.74))` sitting on a wire/junction that's ALSO in the
  pristine original file byte-for-byte; it does not fire on the pristine file alone but
  is surfaced once the sheet's overall net count changes. Coordinates are ~130mm from
  every part this splice touches -- flagged for separate investigation, not addressed
  here, out of A4/W12/H2 scope). **Net: zero new unexplained ERC classes.**
- **Netlist export:** clean (`kicad-cli sch export netlist`, exit 0; the persistent
  "schematic has annotation errors" warning is pre-existing on the pristine board too,
  from hand-named refs like `J_KVM`/`SW_BOOT`/now `J_PWR`/`RJ_HOLD` -- benign, matches
  established convention).
- **Overlap gate (`cec_sch_layout.py --check-overlaps`):** pristine board = 122
  pre-existing text overlaps. Final spliced board = **121** -- zero net-new overlaps (one
  new self-collision from the relocated PWR_FLAG's own label was traded for fixing one
  pre-existing collision the label-rename incidentally cleared). Iterated placement of
  R26-R30/U8-U10/C17/L2/RJ_HOLD/RJ_BUCK/PWR_FLAG four times to get here (grid-snapped
  every new coordinate to the file's native 1.27mm connection grid -- my first pass had
  picked "round number" coordinates off that grid, which is what actually caused the
  interim endpoint_off_grid spike to 49).
- **BOM regenerated:** `bom/bom.csv` (tracking, 47 rows, DNP column populated) and
  `bom/hub-standard-BOM-jlcpcb.csv` (41 rows) via `kicad-cli sch export bom`
  (`--exclude-dnp` for the JLC file). Verified: R29/R30/U9/U10/L2/RJ_BUCK (all `in_bom
  no` + `dnp yes`) are present in the tracking CSV with `DNP=Yes` + a Notes column, and
  correctly **absent** from the JLC assembly CSV; J_PWR/R26-28/U8/C17/RJ_HOLD appear in
  both.

## 6. Open items for the next pass (not resolved here)

- W12's OUT GPIO pin is not yet bound to a specific ESP32 IO -- needs a full free-pin
  audit + firmware coordination.
- U9's VOUT-vs-register-target mismatch (5.5V part ceiling vs "~12V" ask) needs an
  owner/bench call before rung-3 ever gets bench-populated.
- No PCB placement/footprint pass yet for any of the 14 new parts -- schematic-only,
  per this task's scope.
- The pre-existing `no_connect_connected` near J5 (RJ-45 port 4) surfaced by this splice
  is a latent board issue, not introduced by it -- worth a separate ticket.
- `lib/vendor/cec-vendor.kicad_sym` and `lib/cec.kicad_sym` were appended to (additive,
  end-of-file) while at least one other concurrent beta-splice branch was also touching
  `cec-vendor.kicad_sym` this session -- worth a diff-check at merge time.
