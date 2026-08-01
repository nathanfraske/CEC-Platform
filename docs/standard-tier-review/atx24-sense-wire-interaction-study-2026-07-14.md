# 24-pin ATX control-signal interaction study — Hub-commanded PS_ON# / PWR_OK / −12V

**Date:** 2026-07-14 · **Status:** **RULED + IMPLEMENTED (same day)** — owner approved the §2
hardware add including the optional PESD clamps ("I approve the add, and you may as well clamp
them"), and ruled the assert-with-host-attached policy: **self-test must NOT assert PS_ON# with
a host attached unless the user explicitly overrides — the override puts responsibility on the
user** (interlock 8 below). Landed on `beta/atx-24pin-rev3` via
`scripts/splice_24pin_atxctl.py` (2026-07-14): ERC delta = only the documented-benign
Unspecified-pin warning class (+7), no new errors; netlist diff verified node-for-node against
the §2 design (69 untouched nets byte-identical; 8 new nets; MCU IO2/IO3/IO4/IO5 landed);
`bom/bom.csv` regenerated. One layout-time deviation from the first draft: the PESD column sits
at x=393.7 after the first splice attempt measurably collided D3's GND stub endpoint with Q1's
gate pin endpoint (caught by ERC `multiple_net_names`, reverted, fixed, re-verified).
**Ask (owner):** what it would take on the 24-pin for the Hub to interact directly with the
system's sense wires — check voltages as a self-test, power the system on without touching the
front-panel header — and all of the safety margin needed to do that.

Everything below was measured against the live schematics on branch
`claude/pipeline-consolidation` on 2026-07-14 (netlists exported with kicad-cli, node lists
verified — not quoted from docs).

---

## 1. Measured current state

**Alpha (`modules/atx-24pin`, rev2 line, as shipped):** already READS both control signals.
`PWR_OK` (J3.8) → R9 1 kΩ → U4 74LVC1G17 → U1 IO38; `PS_ON#` (J3.16) → R10 1 kΩ → U5
74LVC1G17 → U1 IO39. The 74LVC1G17 pattern is the documented as-built design
(`docs/atx-interposer-netmap.md` §4): 5-V-tolerant Schmitt input at 3V3 VCC, high-Z so the
PSU's possibly-weak internal PS_ON# pull-up is not disturbed, no divider, no ADC channel
consumed. −12V (J3.14) is a pure pass-through. **No drive capability on anything.**

**Beta (`beta/atx-24pin-rev3`, the board any change lands on):** the read taps did NOT
carry over. All three signals are bare pass-throughs to the daughterboard signal stub:
`/ATX_PSON` = J3.16 → J_SIG1.2, `/ATX_PWROK` = J3.8 → J_SIG1.3, `/ATX_NEG12V` = J3.14 →
J_SIG1.1 (plus C22/C23 reservoir caps, ≥25 V rated per their Note). MCU is ESP32-C6-MINI-1-N4
with **six free real GPIOs** (IO1–IO5, IO15; IO1–IO5 are ADC1-capable) plus the unconnected
UART0 pair. PCB layout has not started — this is a schematic-only add with zero rework cost.

**What the Hub already gets without any change:** the four INA238s report bus voltage
(±1 %-class) and current on 12 V / 5 V / 3V3 / 5VSB, over CAN. So "check voltages" for the
main rails exists today — **what's missing is (a) PWR_OK / PS_ON# state visibility on beta,
(b) −12 V measurement, and (c) the ability to turn the PSU on at all** (without which a
host-off self-test can't run: with the system off there is nothing to measure but 5VSB).

---

## 2. Proposed hardware — four small blocks, all on the rev3 main board

The daughterboard stays passive (LOCKED); the Hub needs **no hardware change** (this is all
module-side, commanded over CAN — the Hub "interacts directly" through the module's firmware
contract, OQ-85 bucket).

### 2a. PWR_OK read (restore the alpha pattern)
`/ATX_PWROK` → 1 kΩ series → 74LVC1G17 (VCC=+3V3, 100 nF) → C6 GPIO (interrupt-capable, so
firmware can timestamp the PWR_OK edge to µs for the T_pwr_ok window check). Input abs max
6.5 V vs the 5.25 V-max line; input leakage ~1 µA — loading on the PSU's PWR_OK driver is nil.

### 2b. PS_ON# read (restore the alpha pattern)
Identical 1 kΩ + 74LVC1G17 → GPIO. This is required for the interlocks in §4: firmware must
distinguish "motherboard is commanding on" from "we are commanding on" (line low ∧ our drive
off ⇒ motherboard), and must verify the line physically went low after our own assert
(stuck-line detection).

### 2c. PS_ON# drive — the new capability (open-drain, never sourced)
N-channel FET, drain → `/ATX_PSON`, source → GND, gate ← C6 GPIO through 100 Ω, with a
**100 kΩ gate pull-down** so the default state at power-up / reset / brownout / firmware
crash is RELEASED. Reuse **AO3400A** (already vendored: `cec-vendor:Q_NMOS_GSD`, LCSC
C20917, from the 12VHPWR fan-gate work) — 30 V / logic-level, Rds(on) ≈ 50 mΩ at 2.5 Vgs.
The FET is **mandatory, not optional**: a C6 GPIO driven as open-drain would still see the
5 V pull-up when released, over its 3.6 V abs max. Wired-OR with the motherboard's own
open-drain driver is the ATX-designed topology — paralleling is electrically safe by
construction; we can force ON, we can never force OFF or fight the board.

### 2d. −12 V measurement (new; ADC)
The rail is negative, so the divider hangs between **+3V3 and −12 V**, not GND:
+3V3 —15 kΩ— node —100 kΩ— `/ATX_NEG12V`, node → 10 kΩ series → C6 ADC pin (ADC1),
100 nF at the pin, **BAT54-class Schottky clamp pin→GND**. 1 % resistors.

Node voltage by rail state (all inside the 0–3.3 V ADC window):

| −12 V rail state | node |
|---|---|
| −13.2 V (−10 % limit) | 1.15 V |
| −12.0 V nominal | 1.30 V |
| −10.8 V (+10 % limit) | 1.46 V |
| rail at 0 V (PSU off, wire present) | 2.87 V |
| wire absent (PSU has no −12 V — legal on modern units) | 3.30 V |

The three signatures (healthy / off / absent) are cleanly separable, and "absent" is treated
as a valid PSU configuration, not a failure. Divider draw on the rail: 133 µA. Reading
accuracy ≈ ±2 % of the rail (1 % parts dominate) against a ±10 % acceptance band — 5×
margin.

**Pin plan** (4 of 6 free pins, 2 spares remain): −12V_ADC → IO2 (ADC1), PSON_DRIVE → IO3,
PWROK_SENSE → IO4, PSON_SENSE → IO5. One schematic-time check owed: confirm the drive pin
has **no boot-time internal pull-up and no strapping duty** per the C6 datasheet §2.4 table
(IO2/IO3-class plain pins qualify; IO8/IO9/IO15 are strapping and are avoided), plus a
one-shot scope check at power-up on the first article (§6, bench row).

**BOM delta:** 2× SN74LVC1G17DBVR, 1× AO3400A, 1× BAT54, ~6 R (1 k×2, 100 Ω, 100 k×2,
15 k, 10 k), 3× 100 nF — ≈ **$0.30/board**, ~25 mm², all jellybean LCSC parts, most already
platform lines. Optional (+$0.04): PESD5V0S1BA on PS_ON# and PWR_OK, consistent with the
platform DETECT-pin ESD posture (these lines leave the board through the harness).

---

## 3. Safety margins (the quantitative answer to "all of the safety margin we need")

| Item | Worst case | Design | Margin |
|---|---|---|---|
| PS_ON# line voltage at FET drain | 5.25 V (ATX max standby pull-up) | AO3400A 30 V | 5.7× |
| PS_ON# sink current | spec-class sink is ~1.6 mA; stiffest plausible field pull-up 1 kΩ→5.25 V = 5.25 mA | FET Vol at 10 mA ≈ 0.5 mV vs Vil ≤ 0.8 V | >1000× on Vol; ≥2× on assumed worst-case current vs spec |
| Drive default state | MCU reset / brownout / crash / reflash | GPIO hi-Z + 100 k gate pull-down ⇒ released | fail-safe by construction |
| Buffer inputs | 5.25 V line | LVC1G17 input abs max 6.5 V (VCC-independent) + 1 kΩ series | 1.25 V headroom + current-limited |
| C6 ADC pin (−12 V path) | single fault: +3V3 rail collapses while −12 V live → divider node −1.57 V | 10 kΩ series + BAT54 clamp holds pin ≥ −0.3 V at ~127 µA | inside abs max under single fault |
| −12 V rail loading | 133 µA divider | rail rated 0.3 A class | ~2000× |
| PWR_OK loading | buffer ~1 µA, no DC path | PSU sources mA-class | nil |
| False PS_ON# trigger when released | FET leakage (nA) + buffer input (µA) | needs mA to pull the line low | 3+ orders |
| 5VSB budget (OQ-2) | added quiescent < 0.2 mA | ~2.5 A shared rail | negligible |
| PSU no-load rails during self-test | legacy group-regulated units drift high at 0 A | module+Hub already load 5 V main a few hundred mA after the TPS2121 mux switches over; acceptance bands set at the ±5 % spec limits | measurement remains honest at no external load |

Firmware interlocks (the other half of the margin — spec these into the OQ-85 contract):

1. **Two-phase CAN command** (arm, then fire within a window) — no single frame can start a
   PSU. 2. **Hold watchdog**: every assert carries a max-hold timeout (renewable); expiry
   releases unconditionally. 3. **Release on CAN loss / Hub-heartbeat loss** while in
   remote-hold mode. 4. **Line-integrity check**: after assert, PSON_SENSE must read low
   within ~1 ms or abort+flag. 5. **State telemetry**: pson_line / pson_ours / pwrok bits in
   the standard CAN frame, always. 6. Boot code writes the gate low before any pin-mux
   changes. 7. A CEC assert can never turn a running system off (wired-OR physics) — the
   one behavioral hazard is *holding* low past an OS shutdown, which leaves rails up in S5;
   the watchdog (2) is the mitigation and the state bits (5) make it visible to the Hub.
8. **Host-attached refusal (OWNER-RULED 2026-07-14):** self-test/assert commands REFUSE by
   default unless the arm command carries an explicit standalone/override flag. Host presence
   cannot be sensed reliably from the sense wires (an S5 motherboard releases PS_ON# just like
   an absent one), so the flag is a user declaration: setting it transfers responsibility to
   the user ("which is on the user at that point," owner). Hub UX must surface the spinning-
   drives/fans consequence at the override prompt.

---

## 4. The honest system-level truth: PSU-on ≠ PC boot

PS_ON# is **downstream of the motherboard's power state machine**, not upstream of it.
Asserting it turns the **PSU** on (all rails up); on a standard motherboard the chipset
remains in S5 — VRMs stay disabled by the SLP signals, the CPU never powers, **the machine
does not boot**. Loads wired directly to the PSU (SATA drives, molex/PSU-fed fans) WILL spin.
This is exactly the "paperclip jump-start" state, held cleanly and instrumented.

What each use in the ask actually needs:

- **"Check voltages and whatnot as a self-test" — fully served.** Host off (S5, 5VSB up →
  module alive): Hub arms+fires over CAN → PS_ON# asserted → rails rise (INA238 §6.10 1 kHz
  ring buffers catch the ramp) → PWR_OK edge timestamped and checked against the ATX
  100–500 ms window → 1–3 s dwell sampling all four rails against ±5 % (−12 V against ±10 %
  via the new divider) → release → verify rail decay and PWR_OK drop → pass/fail per rail
  reported over CAN. A complete PSU health check without booting the host or touching any
  front-panel wire.
- **Standalone / bench mode (§6.14 synergy) — fully served, and arguably the headline.**
  With no motherboard attached the ambiguity vanishes: the module becomes a smart,
  instrumented PSU jump-starter/tester (the thing people buy dumb $5 bridge plugs for),
  driving bench loads, pump/fan rigs, or the CEC fleet itself.
- **"Power the system on" in the sense of *booting the PC* — not achievable from the sense
  wires, on physics.** Booting requires the chipset to initiate (PWRBTN# on the front-panel
  header — the connector the ask excludes — or a BIOS wake source: RTC alarm, Wake-on-LAN,
  wake-on-USB, all configuration-only with no CEC hardware). The NanoKVM ATX kit boots the
  box only because it interposes that same front-panel header (see
  `docs/nanokvm-pro-carrier-exploration-2026-07-06.md` §6 — different connector, no conflict
  with this work). If a true CEC boot path is ever wanted, that is a front-panel-header
  interposer product decision, out of scope here.
- Residual note for force-on **with the host attached**: rails-up-in-S5 is a state boards
  tolerate (it is the shutdown transient, sustained) but PSU-direct drives spin up and the
  board may light standby/RGB — worth a line in the user docs, not a hardware concern.

---

## 5. What it takes — summary

| # | Item | Where | Size |
|---|---|---|---|
| 1 | Restore PWR_OK + PS_ON# read buffers (alpha pattern, netmap §4) | rev3 schematic | 2 ICs + 2 R + 2 C |
| 2 | Add PS_ON# open-drain drive (AO3400A + gate network) | rev3 schematic | 1 FET + 3 R |
| 3 | Add −12 V divider/clamp into ADC | rev3 schematic | 4 R + 1 D + 1 C |
| 4 | Pin assignment + strapping/boot-pull verification | rev3 schematic + C6 datasheet | 4 of 6 free GPIOs |
| 5 | Firmware: self-test FSM + interlocks 1–7 + CAN command/telemetry contract | OQ-85 / SB-07 bucket | firmware only |
| 6 | Hub side | firmware only (CAN commands) | zero hardware |
| 7 | Spec: new §6.1 note or §6.x "ATX control-signal interaction" + drive-policy OQ | owner's pen | doc |
| 8 | Bench (first article): power-up scope on the drive gate; PSU-zoo pull-up survey (measure real PS_ON# pull-ups across owned PSUs) | bench queue | one session |

Total hardware cost ≈ $0.30/board; no LOCKED decision is touched (J_SIG pin map, §2.8
output architecture, §6.4 shunts all unchanged — the taps hang on existing nets); rev3 has
no routed copper yet, so the change is free of rework. The read half is not even new — it is
un-regressing the alpha; the drive half and −12 V are the genuinely new capability.

---

## 6. Open items owed before/at implementation

- C6 datasheet strapping/boot-pull check for the final drive-pin choice (schematic time).
- PSU-zoo PS_ON# pull-up survey (bench; sets the measured — not assumed — sink worst case).
- Owner call on the optional PESD clamps on PS_ON#/PWR_OK (+$0.04, posture consistency).
- Whether the self-test asserts with a host attached by default, or only when the module
  believes it is standalone (DETECT/§6.14 posture) — firmware policy, owner preference.

## 7. DECISION BOX (owner)

**Approve adding the §2 hardware (read taps + PS_ON# drive + −12 V sense) to atx-24pin-rev3
(beta line only), with the §3 interlock set as the firmware contract?** The scope honesty in
§4 is part of the decision: this buys PSU-level power-on (self-test, bench, standalone), not
OS boot — boot-without-front-panel would be a separate front-panel-header product decision.
