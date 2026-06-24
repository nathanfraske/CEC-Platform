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
