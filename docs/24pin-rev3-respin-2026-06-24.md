# 24-pin ATX module — rev3 respin spec (2026-06-24)

rev3 scaffold created at `modules/atx-24pin-rev3/` (copy of rev2). This rev folds in: (A) the optional
mezzanine stack (Hub-on-24-pin, see docs/mezzanine-stack-design-2026-06-24.md), and (B) the 5V/5VSB power-mux
consolidation. Plus the shrink levers already proven (90deg + header overhang + the J4->pigtail option).

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
