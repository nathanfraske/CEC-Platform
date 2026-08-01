# 24-pin ATX module — rev3 respin spec (2026-06-24)

rev3 scaffold created at `beta/atx-24pin-rev3/` (copy of rev2). This rev folds in: (A) the optional
mezzanine stack (Hub-on-24-pin, see docs/mezzanine-stack-design-2026-06-24.md), and (B) the 5V/5VSB power-mux
consolidation. Plus the shrink levers already proven (90deg + header overhang + the J4->pigtail option).

> **UPDATE 2026-06-24 (supersedes the "staged/NEXT-build/PENDING" notes below):** the rev3 24-pin schematic
> is **BUILT** — generated in 10 LABELLED SECTIONS by `scripts/gen-24pin-rev3.py` (reuses `build('atx-24pin')`
> for the C6 base + layers the mux, ATX power path, §6.13, mezzanine, J1.1-open). ERC = 1 benign error (the
> C6→CAN-TXD GPIO typing all modules carry, DRAFT). New symbols `CEC_MEZZANINE_16P` + `+5V_SYS`/`+5V_MAIN`
> created; `cec_sch` gained a reusable `sections=` capability. **All 7 IC datasheets are CACHED** in
> `lib/datasheets/` (TPS2121, C6, INA228, INA181, TLV7011, LP5907, TJA1051) and each symbol's `Datasheet`
> URL is set — see the "Datasheets — CACHED" table at the bottom. The GUI hand-off is now **PCB layout** +
> the **TPS2121 control-pin datasheet check** (OV/PR/CP placeholders) + the connector MPN/BOM pass — NOT the
> schematic build, which is done.

## B. Power mux — consolidate MAIN_5V + 5VSB on the 24-pin

### Why
The 24-pin sees BOTH the main +5V rail (sensed, net /RAIL5V_LO) and +5VSB (standby) at the ATX header. The
monitoring subsystem (Hub + up to 4 modules + LEDs + optional NanoKVM) should draw from the HIGH-CAPACITY main
5V when the PC is ON, and fall back to the LIMITED 5VSB (~2.5A typ PSU standby) only in standby -- so it never
overloads 5VSB while running. Today §2.9 does this selection on the HUB (TPS2121 cascade); moving it to the
24-pin gives ONE consolidated 5V output (great for the mezzanine = one power line) and simplifies the Hub.

### Circuit (priority ideal-diode OR + current management)
- **U_MUX = TPS2121RUXR** (RUX-12, already vendored / used on the Hub — reuse the symbol + RUX0012A footprint).
- IN1 (PRIORITY) = MAIN_5V (/RAIL5V_LO, present when PC on). IN2 = +5VSB (always-on). OUT = **+5V_SYS** (new
  net) -> the Hub (replaces the current +5VSB feed on J2 / the mezzanine power pins).
- Priority resistor divider on PR so IN1 (MAIN_5V) wins when valid; auto-fallback to IN2 (5VSB) on MAIN_5V loss.
- C_SS soft-start (~2.2uF) = inrush limit; C_IN1/IN2/OUT 1uF bypass; the ST status pin -> a spare ESP GPIO so
  firmware reports the active source. R_ILIM sets the current limit (below).

### "More than just a mux?" — the amperage answer
The TPS2121 IS already more than a mux: it integrates priority switchover + **inrush limiting** + **current
limit (R_ILIM)** + reverse-current blocking + status. That current limit is exactly the amperage lever:
- Monitoring draw worst case ~2.5-3A (Hub ESP+LEDs ~0.9A + 4 modules ~0.8A + NanoKVM ~0.5-1A; firmware
  LED-capped per OQ-2). TPS2121 handles up to ~5.5A -> comfortable.
- **Set R_ILIM to ~3A**: protects the limited 5VSB rail in standby; MAIN_5V (high capacity) covers the rest when on.
- **A SINGLE TPS2121 SUFFICES** for the platform's ~3A. "More than a mux" is only needed if:
  (a) draw exceeds ~5.5A -> external-FET ideal-diode OR (LM74700 + back-to-back FETs, or the LTC4417 triple-
      prioritizer §2.9 already names for the non-cost-constrained tier), OR
  (b) you want PER-SOURCE limits (higher on MAIN_5V than 5VSB) -> a 2-stage / smarter controller.
  Neither is needed at ~3A; spec the TPS2121, leave the external-FET path as the upgrade note.

### Net changes
- New: +5V_SYS (mux OUT). MUX IN1=/RAIL5V_LO, IN2=+5VSB. The 24-pin's Hub-power output (J2 + the mezzanine
  power pins 1/2/15) move from +5VSB -> +5V_SYS. The RJ-45 link's VCC stays per the locked DETECT/VCC rules.
- §2.9 update: the Hub now ORs (+5V_SYS from 24-pin) vs (USB wall-wart) -- 2-source instead of 3.

## A. Mezzanine (per the stack design doc) — net additions on rev3
- Add J_MEZZ = CEC_MEZZANINE_16P (2x8 2.0mm header, MALE, top side). Pinout per the stack doc:
  +5VSB->**+5V_SYS** x3 (pins 1,2,15) [now the consolidated rail], GND x7, CAN_H=/CAN1_P, CAN_L=/CAN1_N,
  STREAM_P/N (Pro, NC on Standard), DETECT=/DETECT, RSVD. Wire to the SAME nets as J1 (RJ-45) + the mux OUT.
- Add 4x M3 GND mounts (rev2 has none) on the shared alignment rect (<=74x58mm), GND-ringed.
- Population variant: J_MEZZ XOR (J1 RJ-45 + J2 JST).

## Build steps (schematic, via cec_sch + ERC)
1. lib: CEC_MEZZANINE_16P symbol (16 named pins) + vendor stock PinHeader_2x08_P2.00mm (24-pin) +
   PinSocket_2x08_P2.00mm (Hub, placed on B.Cu = the mirror). 
2. rev3 sch: splice U_MUX (TPS2121) + its passives; rename the Hub-power output net +5VSB->+5V_SYS; splice
   J_MEZZ + 4 mounts. ERC + netlist verify (the §6.x checklist).
3. Hub-rev sch: splice the mirrored socket on a dedicated port-0 + power-in (+5V_SYS); move mounts to the
   shared rect; adapt §2.9 to 2-source. ERC + netlist.
4. PCB (GUI / placement pass): place per the shared alignment frame; verify the 8mm-gap clearance.

## STATUS
- DONE: rev3 scaffold; design + amperage analysis (this doc); mezzanine stack design (sister doc).
- NEXT (the build): the schematic splicing (lib parts + cec_sch into both boards + ERC/netlist) -- the careful,
  verification-heavy step. The mux part (TPS2121) + the connector approach (stock 2x8 2.0mm) are settled, so
  the splice is well-defined.

## Datasheets — every new part must carry its real datasheet (referenced + cached)
Hard requirement: at the schematic-splice/BOM pass, EACH new rev3 part gets its real manufacturer datasheet
set in the symbol `Datasheet` property AND the PDF cached in `lib/datasheets/`. Status / sources:

| Part | MPN / LCSC | Datasheet | Status |
|---|---|---|---|
| Power mux | **TPS2121RUXR** (TI) / **C485916** | https://www.ti.com/lit/gpn/tps2121 (TI SLVSDU5) | REFERENCED in symbol cec-vendor:TPS2121. PDF cache PENDING (TI 403s direct; LCSC CDN: datasheet.lcsc.com/...C485916.pdf -- pull via the lcsc skill when jlcsearch is back up). |
| Mezzanine header | 2.0mm dual-row 2x8, MALE | family TBD-at-BOM | SELECT a JLCPCB-stocked 2.0mm 2x8 header (XKB/Wcon/generic -- the platform already sources XKB for the USB-C + buttons); confirm stock + pull the LCSC-CDN datasheet at the BOM pass. |
| Mezzanine socket | 2.0mm dual-row 2x8, FEMALE | family TBD-at-BOM | matched socket to the header above (8mm mated stack). Same BOM-pass selection + datasheet pull. |
| Mux passives | C_SS 2.2uF, C_IN/OUT 1uF, R_ILIM, R_PR | generic | generic; datasheet optional (reuse the platform's existing cap/resistor MPNs which already carry datasheets). |
| M3 mounts (x4) | MountingHole_3.2mm | mechanical | no datasheet (mechanical). |

NOTE (2026-06-24): the jlcsearch API was DOWN and TI hosts 403 a direct fetch, so the PDFs could not be
auto-cached this session. The TPS2121 is properly REFERENCED (TI URL in the symbol). The mezzanine
connector's exact stocked MPN is a live-stock decision = a BOM-pass task. The LCSC datasheet CDN
(datasheet.lcsc.com / wmsc.lcsc.com) does NOT bot-block, so the lcsc skill's fetch_datasheet_lcsc.py will
cache them once jlcsearch resolves the C-numbers. This table is the checklist so nothing ships un-referenced.

## Build progress (2026-06-24)
- DONE + committed: rev3 scaffold; mezzanine + power-mux design + amperage analysis; datasheet contract;
  **vendored the connector footprints** — `lib/vendor/Connector_PinHeader_2.00mm.pretty/PinHeader_2x08_P2.00mm_Vertical.kicad_mod`
  (24-pin header, MALE) + `lib/vendor/Connector_PinSocket_2.00mm.pretty/PinSocket_2x08_P2.00mm_Vertical.kicad_mod`
  (Hub socket, FEMALE; place on B.Cu = the mirror). TPS2121 (mux) symbol + RUX0012A footprint already vendored.
- REMAINING (the meticulous splice pass — staged, NOT rushed): KEY FINDING — `cec_sch.py` is a from-scratch
  schematic GENERATOR, and the rev3/Hub schematics are HAND-MAINTAINED (the generators are stale/guarded), so
  there is NO incremental splice tool. The splice = careful hand-edit of the .kicad_sch s-expr (or a GUI pass),
  which per CLAUDE.md MUST be ERC + netlist verified (wire-to-pin + junctions are where edits break). Steps:
  1. Symbol: create cec:CEC_MEZZANINE_16P (16 named pins per the pinout table) -> register in the lib + fp-lib-table
     (nickname cec-Connector_PinHeader_2.00mm / cec-Connector_PinSocket_2.00mm).
  2. rev3 24-pin sch: add U_MUX (TPS2121) + C_SS/C_IN/C_OUT/R_ILIM/R_PR; net edits IN1=/RAIL5V_LO, IN2=+5VSB,
     OUT=+5V_SYS; rename the Hub-power output +5VSB->+5V_SYS on J2 + the mezzanine power pins. Add J_MEZZ (header)
     wired per the pinout to the J1-link nets + +5V_SYS. Add 4x M3 GND mounts. ERC + netlist.
  3. Hub sch: add the mirrored socket on a port-0 + power-in (+5V_SYS); adapt §2.9 to 2-source; shared-rect mounts. ERC.
  4. BOM/datasheet pass (lcsc skill): the mezzanine MPNs + cache the TPS2121 + connector PDFs (per the datasheet table).
  This is a clean, fully-specified next pass -- best done as a focused GUI/edit session with ERC at each step.

## AUDIT CORRECTIONS (2026-06-24) — read before the GUI splice
A multi-agent audit (wf_b42b699c) of this session's work found real issues; corrected here authoritatively:

1. **The 24-pin "-30.5%" overhang result is CONNECTIVITY-PRESERVING, NOT DRC-CLEAN.** The asym-overhang board
   (build/24pin-rev2-tight/rev2-overhang-asym.kicad_pcb) keeps kelvin/diffpair/unconn=0 but **drc=31, gates_pass=FALSE**.
   The 17 copper_edge_clearance hits are REAL power copper near the new edge (the +5VSB B.Cu run), NOT a free
   "finishing re-pour" artifact — clearing them needs a genuine RE-ROUTE pulling that copper in from the edge. So
   the honest claim is "30.5% smaller, connectivity-preserving, but the tight edge still needs a routing pass to be
   DRC-clean." The size ladder stands; the "clean" framing did not.
2. **Directed-loop origin bug: NOW FIXED IN CODE** (not just the board-normalize workaround). cec_place_planner
   `_region_boxes` gained `ox/oy` (the board's top-left) and all 3 callers pass `bb.GetLeft/Top` — so the partition
   tiles into the board's real frame for ANY origin (verified: 24-pin "right" region 41.5→136.5, now inside x[95..178];
   eps at origin~0 unchanged = back-compat). The earlier "fixed (unconn 160->24)" claim was a board-normalize hack;
   this is the real fix.
3. **Power-mux R_ILIM — corrected.** A SINGLE output current limit also caps the main-5V (S0) running state, so
   setting it to ~3A would cut a legit full-white load when the PC is ON. Set R_ILIM to the **MAX expected running
   draw with margin** (toward the TPS2121's ~5.5A ceiling), and protect the LIMITED 5VSB rail in STANDBY via the
   firmware LED cap (OQ-2), NOT the mux ILIM. If S0 worst-case can exceed the part ceiling, use a 2-source-limit
   controller (the §2.9 LTC4417 path). Do not set ILIM=3A.
4. **Mount placement — do NOT assume 4 corners.** A 74x58 corner rectangle collides with 3 of the 24-pin's 4 corner
   connectors. Solve the mount/standoff positions against the ACTUAL connector keep-outs at layout (the design
   allows >=3 mounts) — the alignment contract is {connector ref + the mount set that fits both boards' keep-outs},
   finalized in the GUI, not a fixed corner rect.
5. **Connector keying — the vendored 2x8 2.0mm header/socket are UN-keyed/un-shrouded.** Since the 8mm M3 standoffs
   set the gap + alignment + carry the load, retention/keying from the connector is NOT required — DROP the "keyed"
   wording; the standoffs handle it. If positive keying is still wanted, source a keyed board-to-board (Wurth WR-BHD /
   Molex SlimStack) and vendor ITS footprint instead. (The vendored footprints' forbidden ${KICAD10_3DMODEL_DIR}
   3D-model paths were STRIPPED this pass for clone-parity.)
6. **"Simplifies the Hub" was an overclaim** — moving the mux to the 24-pin RAISES total part count; the Hub doesn't
   shrink. The real win = ONE consolidated +5V line over the mezzanine (one power conductor in the stacked build),
   and the §2.9 Hub OR drops from 3-source to 2-source. State it that way.
7. **Standoffs are a GND BOND, not the primary power return.** The connector's 7 GND pins carry the 5V return; the
   M3 standoffs are a parallel low-impedance plane-to-plane bond (good for SI), not the main current path.
8. Forensic wall-wart recovery (§2.9 source 3) for the STACKED unit is undefined — define a rear-bracket power-in
   (OQ-54) or keep the Hub's USB-C VBUS as the forensic source for the stacked build. (Open item, not a blocker.)

## rev3 CHANGE LIST — bring the 24-pin current (verified against rev2, 2026-06-24)
The 24-pin is the oldest, hand-maintained module and is BEHIND the platform on several locked/spec items the
other modules already carry. rev3 should fold these in alongside the mezzanine + power mux:

1. **DETECT poke-and-ack tap — MISSING, ADD IT.** rev2's `/DETECT` has only J1.8 + R1 (the 2.2k CAN-only code
   resistor). The EPS/PCIe/12VHPWR modules carry a ~100k tap from `/DETECT` to a spare ESP GPIO (net
   `/DETECT_SENSE`) so the module's MCU can sense the Hub's poke and ack the handshake (active presence/ID beyond
   the passive divider). ADD `R_pa` (100k) `/DETECT -> /DETECT_SENSE -> a free ESP32 GPIO`. The **mezzanine DETECT
   pin (pin 13) then inherits it automatically** — it's the same `/DETECT` net, not a separate connector signal.
2. **DETECT ESD diode (PESD5V0S1BA, C5261083) — MISSING, ADD IT** (locked §2.4 platform requirement). rev2's D1 is
   the VBUS Schottky, NOT the DETECT ESD clamp. Add the low-cap ESD diode cathode-to-`/DETECT`, anode-to-GND.
3. **FTP shielded RJ-45 — UPGRADE.** rev2 still uses the UNSHIELDED Amphenol 54602; switch to the platform FTP jack
   (Kinghelm KH-RJ45-58-8P8C / C2683360, `cec:RJ45_FTP_Shielded_Horizontal`) with SH1/SH2 -> GND (per §2.1).
4. **CAN net rename — `/CAN1_P,/CAN1_N` -> `/CAN_H,/CAN_L`** (platform convention; the queued rev3 erratum in
   board-manifest.json). Coordinate the mezzanine + RJ-45 CAN pins to the post-rename names.
5. **J1.1 (RJ-45 VCC) left OPEN** (spec §2.7 v3.3) — fixes the rev2 parallel-feed erratum (RJ-45 VCC bypassing the
   Hub mux). The bulk 5VSB/+5V_SYS flows over the JST/mezzanine only.
6. **MCU + §6.13 transient front-end — GO for rev3 (owner, 2026-06-24).** Move U1 ESP32-S3-MINI-1 ->
   **ESP32-C6-MINI-1-N4** (cec-vendor, C5736265, footprint cec-RF_Module:ESP32-C6-MINI-1) + add the §6.13 fast
   transient-DETECTION front-end. The 24-pin is hand-maintained so it can NOT be regenerated by gen-modules.py
   (that generator is now C6-specific for the i2c-CABLE boards (EPS/PCIe) and would clobber the 24-pin's hand work
   + its 4x-INA228 topology) — this is a GUI/schematic pass mirroring the EPS/PCIe C6+§6.13 implementation. Spec:
   - **C6 pin map (reuse the verified EPS/PCIe map):** GND pads 1,2,11,14 + 36-53; CAN_TX/RX -> IO20/IO21;
     USB D+/D- pads 18/17; I2C (the 4x INA228 bus) pads 24/25; EN pad 8; BOOT/IO9 pad 23; +3V3 pad 3;
     **DETECT_SENSE (the poke-and-ack tap, item 1) -> IO10/pad 12**; **THRESH_PWM -> IO14/pad 19** (LEDC PWM ->
     R10 -> C40 = the board-shared filtered threshold ref). The per-rail §6.13 DET latches + the 4 INA228 ALERTs
     take the remaining GPIOs.
   - **§6.13 chain, per high-current rail** (12V + 5V at minimum; 3V3/5VSB optional — owner/layout, since each
     front-end is area the shrink work is fighting): the rail SHUNT -> **INA181A2IDBVR** (gain 50, SOT-23-6,
     C2058784, REF->GND unidir, 100n VS bypass) -> DETAMP -> **TLV7011DBVR** hysteresis comparator (SOT-23-5,
     C702117, IN+ = INA181 OUT, IN- = the shared THRESH, 100n VCC bypass) -> per-rail DET -> a C6 GPIO latch that
     ORs into the §6.10 FREEZE (firmware). The INA228 keeps the precise digital energy/power; §6.13 adds the cheap
     fast BINARY transient flag the INA228 averages away.
   - **GPIO-BUDGET CHECK (do this first):** the C6-MINI has FEWER usable GPIOs than the S3. Tally the 24-pin's full
     I/O — I2C(2) + CAN(2) + USB(2) + EN/BOOT(2) + DETECT_SENSE(1) + THRESH_PWM(1) + N×§6.13 DET + 4×INA228 ALERT +
     the §2.9 mux status + any mezzanine sideband — against the C6 map BEFORE committing the rail count for §6.13
     (this is what bounds how many rails get the fast front-end).
   - **AREA TENSION (note):** rev3 ADDS a lot (TPS2121 mux, N×§6.13 front-ends, the mezzanine, poke-ack, ESD) while
     the shrink goal pulls the other way — lean on the proven levers (header overhang, both-sides assembly under
     the connectors, 0402->0201) to absorb the new parts; the §6.13 rail count is the main area dial.
7. **Shunt part lock (OQ-11)** — still open (the §6.4 2mΩ/25mΩ shunt MPNs). Confirm at the BOM pass.
8. (Plus this respin's mezzanine + TPS2121 power mux + the shrink levers — sections above.)

Items 1-5 are mechanical/small + bring parity with the other modules; #6 is the judgment call; #7 is a BOM item.

## Datasheets — CACHED (2026-06-24)
Pulled direct from the manufacturers (jlcsearch was down) into lib/datasheets/, and each symbol's
`Datasheet` URL property is set (referenced). All rev3 ICs covered:

| Part | LCSC | PDF | Source |
|---|---|---|---|
| TPS2121RUXR (power mux) | C485916 | TPS2121RUXR.pdf | ti.com/lit/ds/symlink/tps2121 |
| ESP32-C6-MINI-1-N4 (MCU) | C5736265 | ESP32-C6-MINI-1.pdf | espressif.com |
| INA228 (rail sense) | — | INA228.pdf | ti.com/lit/ds/symlink/ina228 |
| INA181A2IDBVR (§6.13 CSA) | C2058784 | INA181A2IDBVR.pdf | ti.com/lit/ds/symlink/ina181 |
| TLV7011DBVR (§6.13 comparator) | C702117 | TLV7011DBVR.pdf | ti.com/lit/ds/symlink/tlv7011 |
| LP5907MFX-3.3 (3V3 LDO) | C80670 | LP5907.pdf | ti.com/lit/ds/symlink/lp5907 |
| TJA1051T/3 (CAN) | C38695 | TJA1051.pdf | nxp.com (via archive mirror) |

CONNECTOR datasheets remain BOM-pass items (jlcsearch down for the LCSC-CDN pull): the mezzanine
header+socket (generic 2.0mm 2x8, exact MPN TBD at BOM), the ATX Mini-Fit Jr (Molex 5569 — family
spec Molex-PS-5556.pdf already cached), the FTP RJ-45 (Kinghelm C2683360) and USB-C (XKB). NOTE the
TPS2121 OV/PR/CP control-pin config still needs verifying against TPS2121RUXR.pdf before fab.

## Pinout verification vs real datasheets (2026-06-24)
Every placed IC's symbol pinout was cross-checked against its cached datasheet PDF (one agent/part):
| IC | verdict | notes |
|---|---|---|
| ESP32-C6-MINI-1 | ✅ match | all 53 pads vs Espressif Table 3-1 (USB D+/- not swapped; CAN 26/27; I2C 24/25) |
| INA228 (INA226 body) | ✅ match | DGS VSSOP-10 1-10 vs SLYS021A |
| INA181A2 | ✅ match | SOT-23-6 vs SBOS793H |
| TLV7011 | ✅ match | SOT-23-5/DBV vs SLVSDM5F (pin4 name "IN" cosmetic) |
| TPS2121 | ✅ match* | all 12 numbers vs SLVSDU5 (pin10 "ILM" cosmetic) — **PR1 wiring FIXED, see below** |
| LP5907 | ✅ match | SOT-23-5 |
| TJA1051 | ✅ match | SO-8 |

**FIX applied:** the TPS2121 PR1 (pin 6) was a GND placeholder — datasheet Table 9-3 says GND selects
VCOMP "highest-voltage-wins" mode, NOT IN1-priority. Corrected to a **divider off IN1** (R52 100k /
R53 33k, IN1-valid ~4.3V) so IN1>IN2 priority is real. OV1/OV2/CP2→GND placeholders were already
datasheet-correct (OV disabled, fast-switchover off); ST pull-up tightened 100k→10k (datasheet 6-20k).
ERC unchanged (1 benign CAN-TXD typing). The cosmetic symbol names (ILM/ILIM, IN/IN-) have no netlist impact.

## Passive quality/type spec (for the BOM pass) — 2026-06-24
The generated schematic carries VALUE + FOOTPRINT only (platform convention); tolerance / dielectric /
voltage / LCSC part are assigned at the BOM-sourcing pass. Requirements so the critical ones aren't
mis-sourced (JLCPCB Basic 0402 resistors are 1% and Basic caps are X7R/X5R by default, so most fall out free):

**Resistors — 1% (precision, they SET a threshold/limit/code):**
- R1 (2.2k DETECT code, §2.3 divider) · R50 (20k TPS2121 ILIM) · R52 (100k) + R53 (33k) PR1 priority divider ·
  R60 (10k §6.13 threshold). Use 1% / ≤100ppm.
**Resistors — 5% (general: pull-ups/downs, series taps):** R2 (10k EN), R3/R4 (2.2k I2C), R7 (100k poke-ack),
  R8/R9 (5.1k USB CC — 5% is in USB spec), R51 (10k ST pull-up).
**Caps — dielectric + voltage (no timing/precision caps in this design, so X7R/X5R throughout):**
- All 100n decoupling (C3/C4/C5/C8/C10-13/C60 + the §6.13 bypasses): **X7R, ≥16V** on the +5V_SYS/+5V_MAIN/+5VSB
  nets, ≥10V on +3V3-only.
- 1u bulk (C1 LP5907 in, C2 LP5907 out): X7R, C1 ≥16V / C2 ≥10V.
- 10u bulk (C6 board-entry, C7 +3V3, C9 VBUS): **X5R, ≥16V** (C7 ≥10V).
- C50 (2.2u TPS2121 SS soft-start): X7R/X5R ≥16V (sets soft-start time, not precision).
NOTE: the actual LCSC part assignment (+ the connector MPNs) is the BOM pass, pending jlcsearch coming back up
(down 2026-06-24); the ICs were cached direct. This table is the spec that pass must honor.
