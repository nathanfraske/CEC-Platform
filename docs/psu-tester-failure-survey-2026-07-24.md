# Orthogonal failure survey — margin we have NOT designed for (2026-07-24)

Companion to the v1.6.0 USB-backfeed package (spec §2.9/§6.14; that class is treated as
FIXED here and used as the pattern bar). This survey sweeps every external interface of the
real boards for fault classes in two operating contexts:

- **Context T (PSU tester):** the ATX-native DC load station
  (`docs/psu-tester-exploration-2026-07-14.md`) uses CEC modules as its sensing front-end —
  **adversarial/faulty PSUs are the NORMAL input**, repeatedly, with long leads and constant
  connector cycling.
- **Context P (regular PC):** one presumed-conformant ATX PSU with working OCP/OVP/OPP/SCP,
  installed once.

**Evidence discipline.** Every row states what protects us TODAY by naming the actual part or
design fact from the boards/spec, and is tagged:
`[M]` = measured/read directly from the committed BOMs, schematics, or an owner-queue sim
number; `[D]` = derived arithmetic from `[M]` facts; `[R]` = reasoned from a recalled
datasheet rating — correct to the author's knowledge but **re-verify before relying on it as
a margin number**. "Nothing" means nothing; no margin is invented.

Boards read for ground truth (2026-07-24): `beta/atx-24pin-rev3`, `beta/eps-8pin`,
`beta/pcie-8pin-2port`, `beta/pcie-8pin-3port`, `beta/12vhpwr-standard`,
`beta/hub-standard-rev2`, `beta/argb-standard` (BOMs + schematic label sweeps), plus
CLAUDE.md board-state notes and spec v1.6.0.

---

## 1. External-interface inventory (as-built facts, all [M])

| # | Interface | Boards | On-board facts today |
|---|---|---|---|
| I1 | ATX 24-pin PSU input J3 (Mini-Fit Jr 5569-24A1) | 24-pin | 12V/5V/3V3 through 2 mΩ shunts (RS1–RS3, CSS2H-2512K), 5VSB through 25 mΩ (RS4), each into an INA238; −12V into 15k/100k divider (R74/R73) + BAT54S dual clamp (D5) + 10 µF/100 nF ≥25 V reservoir; PS_ON#/PWR_OK via 1k taps (R70/R71) into 74LVC1G17 buffers (U4/U8) with PESD clamps (D4/D7); PS_ON# drive = AO3400A open-drain (Q1), 100k fail-safe pull-down; MAIN_5V×5VSB → TPS2121 (U5) → +5V_SYS |
| I2 | EPS / PCIe cable inputs J_IN* (Mini-Fit Jr 87427 / 45586) | EPS, PCIe×2 | 0.5 mΩ shunt per cable (CSS2H-2512R-L500F) → INA238 + INA181A2 + TLV7011 per cable; no caps, no series elements on the sensed rails (pure interposer) |
| I3 | 12VHPWR path: J3 12V-2x6 in → 6× 1 mΩ per-pin shunts → J4 captive pigtail out | 12VHPWR | INA240A3 per pin (REF grounded = unidirectional), 10 Ω+470 nF input RC; 47k/10k rail divider → ESP ADC (IO7) + C24 1 nF; sideband S1–S4 taps via 1k (R10–R13) to GPIOs; TH1/TH2 NTCs |
| I4 | Output blades TB* (TE 63969-1 FASTON receptacles) + J_SIG1 stub | 24-pin (10), EPS (12), PCIe-2 (12), PCIe-3 (18) | Ratified joint counts at 22.9 A/125% margin policy (spec §2.8); passive copper — no protection elements in the output path (by design: interposer) |
| I5 | RJ-45 link (FTP, shield→GND both ends) + DETECT pin 8 | all modules + hub | Module: PESD5V0S1BA on DETECT (D1), 2.2k code resistor; hub-rev2: per-port 500 mA PTC on VCC (F1–F4, C46640983), PESD per DETECT (D2–D5), 100 nF DETECT immunity filter (2026-07-15 rows) |
| I6 | CAN pair (pins 3/6) | all | TJA1051T/3 (C38695); DNP CMC position with populated 0 Ω bypasses (H3a); 120 Ω split termination at hub only |
| I7 | USB-C J5/J_USB | all | USBLC6-2SC6 on D±; VBUS PESD (all but EPS); FB1 bead; **v1.6.0 (spec'd, not yet on boards): TPS2121 ingress + 750 mA polyfuse; D2 SS34 retired** |
| I8 | Hub power-in J_PWR (3-pin: MAIN_5V/GND/5VSB) | hub | TPS2121 cascade (U5/U7: reverse blocking, ILIM 27k ≈ 3.8 A/stage, C_SS 2.2 µF); D8/D9 SMAJ5.0A power-entry TVS (2026-07-15); D1 Schottky isolating +5V_HOLD |
| I9 | KVM aux header J_KVM | hub | D7 PESD on the 3V3 ref pin; ratiometric untrusted 3V3 sense; **v1.6.0 (spec'd): third TPS2121 stage + 1.1 A polyfuse; pin 1 inbound-only** |
| I10 | Mezzanine headers J6P/J6C/J6D | 24-pin, hub-rev2 | DNP by default; +5V_SYS/5VSB/CAN/DETECT pins when populated |
| I11 | Fan header J2 (12VHPWR) | 12VHPWR | DNP; fed off the PRE-shunt lane-6 node; AO3400A low-side + SS34 flyback (D5) |
| I12 | Chassis: 4× M3 chassis-grounded mounts; FTP shield bonded both ends | all | Board GND = chassis at the mounts (deliberate, §6.6/OQ-37 posture) |

---

## 2. Fault survey

Severity scale: **CRIT** (safety / host damage / fire path), **HIGH** (board killed or
measurement lost, likely occurrence), **MED** (damage plausible, bounded), **LOW**
(nuisance/cosmetic). Given per context as T / P.

### 2.1 Overvoltage — miswired or cross-railed PSU (12 V on a 5 V/3.3 V pin, crowbarred rail)

The tester WILL see this: user-built modular cables and failed regulation both put 12 V+ on
low rails.

| Path | Today | Severity T/P | Proposed mitigation (cost) |
|---|---|---|---|
| 24-pin sensed rails → INA238 bus pins | `[R]` INA238 is an 85 V-input part — the sensor itself survives any PSU-class insult | LOW/LOW | none needed |
| 24-pin 5VSB/MAIN → U5 TPS2121 → logic | `[M]` U5 is a 22 V part (abs max 24 V); `[M]` v1.6.0 adds a ~6.04 V OV1 cutoff at the NEW U6 stage → the logic rail disconnects. Before that pass lands: 12 V reaches the LDO (`[R]` LP5907 abs max 6.5 V) = dead logic side | was HIGH, → LOW post-v1.6.0 / LOW | already ratified; implement action item 6 |
| EPS/PCIe/12VHPWR logic (fed from RJ-45 VCC, not the sensed rail) | `[M]` sensed rail and logic rail are galvanically separate nets on the interposers — a cross-railed DUT cannot reach the module's own logic | LOW/LOW | none — good existing structure |
| §6.13 front-end on EPS/PCIe (INA181A2 inputs on the sensed rail) | `[R]` INA181 common-mode abs max ≈ 26 V — survives 12→20 V-class insults, dies at a 24 V+ crowbar | MED/LOW | accept; note in tester manual (>24 V DUT rail = sensing channel sacrificial, ~$0.30 part) |
| 12VHPWR rail divider → ESP ADC | `[D]` 47k/10k puts 24 V at 4.2 V on the pin, over `[R]` 3.6 V abs max; clamp current ≈ (4.2−3.6)/47k ≈ 13 µA — survivable leakage-class, but out of spec | MED/LOW | add 10k series R at the ADC pin (the 24-pin's R76 pattern, ~$0.001) on the next beta pass |
| **Hub J_PWR 5VSB/MAIN inputs** | `[M]` D8/D9 SMAJ5.0A clamp TRANSIENTS; `[R]` a sustained 12 V (cross-railed 24-pin feed cable, or a faulty PSU with the tester's hub attached) sits above the TVS standoff → TVS burns out → 12 V passes; U5/U7 survive (`[M]` 22 V part) but `[M]` no OV divider found in the hub schematic label sweep or BOM (OV pins presumed GND-strapped per the datasheet's "not required" strap — VERIFY at the Sonnet pass) → 12 V reaches the +5VSB rail: `[R]` LP5907 (6.5 V), SK6812 (5.5 V), and every downstream module port get it | **HIGH**/MED | **top finding #3:** extend the v1.6.0 OV-divider posture to the hub's own U5/U7 (47k/10k per input, ≈$0.01/stage, same math as §6.14) — modules would then disconnect at their own new OV; the hub is currently the one unprotected 5VSB consumer |

### 2.2 Reverse polarity / negative voltage

| Path | Today | Severity T/P | Proposed mitigation |
|---|---|---|---|
| Reversed modular cable puts −12 V-class or swapped GND on a positive-rail pin | **Nothing.** `[M]`/`[R]` every semiconductor on those nets (TPS2121, INA238 VBUS pin, INA181) has a −0.3 V abs-max floor; the interposer has no series blocking by design (a series element would corrupt the measurement) | **HIGH**/LOW | Not economically fixable on-board without breaking the product's measurement role. Tester-side: (a) keyed harness only — never user-built modular cables between DUT and module (procedure, $0); (b) sacrificial pre-checked adapter harness per DUT family (~$5); (c) tester pre-flight polarity check at µA sense current before enabling loads (firmware/instrument feature, $0 hardware) |
| 24-pin −12 V pin miswired to +12 V | `[M]` divider R74/R73 + BAT54S (D5) clamps the ADC node both directions; `[D]` divider current at +12 V ≈ 12 V/115k ≈ 104 µA — harmless | LOW/LOW | none — the one negative-rail input was actually designed for abuse |

### 2.3 Hot-plug inrush — both directions

| Path | Today | Severity T/P | Proposed mitigation |
|---|---|---|---|
| PSU turn-on inrush INTO our boards' bulk | `[M]` the sensed rails carry essentially no CEC capacitance by design (EPS/PCIe: none; 12VHPWR: 6× 470 nF behind 10 Ω; 24-pin −12 V: 10 µF) — we are not a meaningful inrush load; logic-side bulk sits behind TPS2121 soft-start (hub today; modules post-v1.6.0) | LOW/LOW | none — measured non-issue, record it |
| Host USB into dead module+PSU (VBUS backfeed) | `[M]` v1.6.0 package (sim: ~27 A pk, ≤22 mC, ~400 mC sustained) | fixed | implement action item 6; interim bench rules in force |
| RJ-45 hot-plug (DETECT ESD, VCC hot-mate) | `[M]` locked DETECT PESD both ends + hub per-port 500 mA PTC (F1–F4) | LOW/LOW | none |
| Blade/Mini-Fit hot-plug UNDER LOAD (tester swap cadence) | **Nothing electrical.** `[M]` §2.8 ratification explicitly treats the blade joint as not-for-constant-swapping (high insertion force is a feature); the tester context inverts that assumption — daily mating cycles, and un-mating at 40–50 A draws an arc across FASTON blades | **HIGH**/LOW | tester interlock: loads to zero before any connector operation (instrument firmware, $0); track contact resistance per OQ-86/88 confirm-soak — now tester-critical, not just recommended; stock sellable daughterboard assemblies as wear parts (§2.8's own SKU) |

### 2.4 Sustained overcurrent through the power path (downstream short, OCP-defective DUT)

`[M]` Design basis (§2.8/§6.3): EPS ~52 A/cable, PCIe-3 ~39 A/cable sustained worst case,
24-pin on the 6 A/circuit ATX bar; joints ratified at ≥125% of that. `[D]` Shunt I²R at
fault: EPS 0.5 mΩ at 150 A = 11.3 W against a `[R]` ~6 W-class CSS2H-2512 rating (verify
exact Bourns figure) — over rating but survivable for the ms a conformant PSU takes to trip
SCP. **The tester's defective DUT may never trip.** A sustained 100–150 A through copper and
joints sized for 52 A×1.25 is a heat/fire path, and **nothing in a CEC interposer opens the
circuit — there is deliberately no fuse in the measurement path.**

- Today: `[M]` §6.13 comparator (EPS/PCIe) and §6.10 ALERT give fast DETECTION (that is the
  product working); `[M]` 12VHPWR has TH1 shunt-row NTC + overtemp self-alarm ruling. Nothing acts.
- Severity: **CRIT**/LOW (in a PC, PSU SCP/OPP is the actuator; on the tester the DUT is the
  suspect).
- Mitigation (**top finding #2**): the ACTUATOR belongs to the tester, not the interposer —
  (a) tester DC-load firmware treats module ALERT/§6.13 flags as a hard load-dump + AC-kill
  input (wiring + firmware, ~$0); (b) a breaker/contactor on the DUT's AC side rated to kill
  a non-conforming PSU (~$15, one per station); (c) publish per-module "do not exceed
  sustained" numbers (the §2.8 design-basis currents) in the tester manual so limits are
  explicit rather than folklore.

### 2.5 Open / lifted ground and ground loops

| Path | Today | Severity T/P | Proposed mitigation |
|---|---|---|---|
| RJ-45 GND (pin 2) opens while VCC stays | `[R]` module still grounded through its PSU harness; CAN shifts common-mode — TJA1051T/3 bus pins are rated to ±42 V-class (NXP datasheet; re-verify exact limits) and CAN is differential | LOW/LOW | none |
| Bench PC ↔ DUT PSU ground loop through a module (USB GND vs PSU GND) | `[M]` interim rule: sacrificial hub/isolator (v1.6.0 §2.9); `[M]` post-v1.6.0 the mux isolates VBUS but **USB GND remains hard-tied to module/PSU GND** (necessarily — single-ended USB) | MED/LOW | make the USB isolator a PERMANENT tester-station fixture, not an interim rule (~$15 ADuM-class isolator dongle); it also removes hum from measurements |
| Chassis bonding: module M3 mounts tie board GND to whatever it is bolted to; a faulty DUT PSU can energize its own chassis | `[M]` mounts are chassis-grounded by design; **nothing on-board can protect against a primary-side fault** — all CEC clamps are 5–24 V class | **CRIT**/LOW | see 2.8 — bench-level AC safety is the only real mitigation; never bolt the module to the DUT's chassis (procedure) |

### 2.6 ESD and line transients

| Path | Today | Severity T/P | Proposed mitigation |
|---|---|---|---|
| DETECT, USB D±, VBUS, KVM ref, PS_ON#/PWR_OK, hub power entry | `[M]` covered: PESD5V0S1BA fleet, USBLC6, SMAJ5.0A, BAT54S — the platform's strongest suit | LOW/LOW | none |
| CAN pair on LONG tester leads (bench wiring, motors/contactors nearby) | `[M]` TJA1051T/3 bus-pin ratings + the DNP CMC position (H3a) with 0 Ω bypasses; termination at hub only | MED/LOW | populate the CMC (the H3a EMC variant, ~$0.30) on TESTER-dedicated modules; keep leads < the §3.1 star-stub basis or re-run the SI bench at tester lead lengths |
| Blade/Mini-Fit power pins (big exposed metal, handled constantly on the tester) | `[M]` no clamps on power pins (correct — bulk energy class); path is copper→PSU | LOW/LOW | handling procedure only |

### 2.7 Back-drive from charged downstream loads (energy stored in the DUT's load side)

`[M]` Output blades connect to GPU/motherboard-class loads holding mF of charged bulk. On
PSU collapse that charge flows BACK through the interposer: passive copper + shunt — no
damage path (`[M]` no polarized/active element in the power path). `[M]` 12VHPWR INA240s
are REF-grounded unidirectional: reverse current reads as zero (a MEASUREMENT blind spot in
exactly the interesting death-transient window, not a damage risk). `[M]` 24-pin MAIN-tap
back-drive into the logic side is blocked by U5 (and doubly post-v1.6.0). Severity: LOW/LOW
damage; MED measurement honesty. Mitigation: none in hardware; document the unidirectional
clip in the tester's data notes (the Pro INA240 path with REF options is the tier answer).

### 2.8 Mains-class faults in the DUT (primary→secondary breakdown, PE lift)

The tester's defining hazard, stated plainly: a PSU with a primary-secondary insulation
fault puts **mains potential on its secondary rails, GND, and chassis**. `[M]` Nothing on
any CEC board addresses this and nothing reasonably could — every protective part on the
boards is a 5–42 V-class semiconductor. In a regular PC this is the PSU's safety
certification's job; on a tester whose input is *uncertified failed hardware*, it must be
assumed live.

- Severity: **CRIT (personnel)**/LOW.
- Mitigation (**top finding #1**, all bench-level, none on-board): RCD/GFCI on the DUT AC
  feed (~$30); isolation transformer for probing work (~$150, standard practice);
  earth-bonded tester frame with the module chassis-ground mounts bonded to IT (turns the
  M3 posture into an asset: fault current trips the RCD instead of finding the operator);
  one-hand/insulated-tool procedure in the tester manual. This belongs in the PSU-tester
  product spec (`psu-tester-exploration-2026-07-14.md`) as a REQUIRED station section.

### 2.9 Smaller items (recorded so they are not lost)

- **Mezz headers J6P/J6C/J6D (DNP):** exposed live +5V_SYS pins if ever populated on a
  bench-handled board — populate only in the mated stack (existing DNP posture is the
  mitigation; note it in the stack doc). LOW.
- **Fan header J2 (12VHPWR, DNP):** pre-shunt tap = un-sensed 12 V if populated; flyback D5
  present `[M]`. Miswiring a fan connector onto CAN-class headers is prevented by JST-PH vs
  KK-2510 incompatibility `[M]` (the BOM's own open item). LOW.
- **DETECT wire cross to a power pin inside a damaged RJ-45 lead:** PESD (5 V clamp) eats
  sustained 12 V with no series R and fails; hub sees it through its 10k pull-up path only
  `[D]` → hub survives, port's DETECT dead. LOW/LOW; per-port PTC already bounds the VCC
  half `[M]`.
- **Polyfuse/eFuse trips reading as "dead module":** already a documented troubleshooting
  note (v1.6.0 §2.9); extend to the hub's per-port F1–F4. LOW.

---

## 3. Ranked top findings (owner surface list)

1. **Mains ingress from a faulted DUT PSU (T-context, CRIT-personnel).** Nothing on-board;
   requires a bench/station safety section in the PSU-tester spec: RCD/GFCI + isolation
   transformer + earth-bonded frame (with our chassis-ground mounts bonded to it) +
   procedure. ~$200/station, non-optional. `[M/R]`
2. **Sustained overcurrent with an OCP-defective DUT (T, CRIT-fire-path).** Interposers
   deliberately contain no series protection; copper/joints are sized to §2.8 sustained
   basis ×1.25, shunt I²R exceeds its ~6 W-class rating above ~110 A (EPS) `[D]`. Actuation
   must live in the tester: module ALERT/§6.13 flags wired as hard load-dump + AC-kill,
   plus an AC-side breaker. ~$15/station + firmware. Publish per-module sustained ceilings.
3. **The hub is the one 5VSB consumer with no overvoltage cutoff (T HIGH / P MED).** A
   sustained cross-railed 12 V on J_PWR burns the SMAJ5.0A TVS, then reaches LP5907/LEDs;
   the v1.6.0 module OV posture (47k/10k → ~6 V) does not yet exist on the hub's own U5/U7
   (OV pins presumed GND-strapped `[M-sweep]`, verify). Two resistors per stage, ~$0.01 —
   propose folding into the same Sonnet pass as action item 6, owner sign-off needed since
   it extends the ratified package. `[M/D/R]`
4. **Reverse polarity / swapped-GND modular cables (T HIGH).** Every part floor is −0.3 V;
   no on-board fix that preserves the measurement role. Tester-side keyed sacrificial
   harnesses + µA-level pre-flight polarity check before load enable. `[M/R]`
5. **Hot-unplug under load at blades/Mini-Fit (T HIGH).** The §2.8 not-for-swapping
   ratification collides with tester swap cadence: arc + contact wear. Tester interlock
   (loads-to-zero before connector ops) + OQ-86/88 contact-R trending promoted to
   tester-critical + daughterboard assemblies stocked as wear parts. `[M]`
6. **TPS2121 unpowered-reverse behavior** — already the ratified v1.6.0 first-article bench
   gate; listed to keep it visible: two load-bearing paths depend on an unspecified
   datasheet state. `[M]`
7. **Measurement blind spots under fault, not damage:** 12VHPWR unidirectional INA240 clips
   reverse (death-transient window); ESP ADC divider over-range at >13 V rails (13 µA clamp
   current, out-of-spec but survivable `[D]`) — add the R76-pattern series R on the next
   beta pass. `[M/D]`

**Explicit non-issues (measured, no action):** PSU turn-on inrush into CEC capacitance
(§2.3 — the boards are deliberately cap-light on sensed rails); INA238 bus pins under any
PSU-class overvoltage (85 V part `[R]`); the −12 V input (divider + BAT54S designed for
abuse); ESD on every signal-class pin (the PESD/USBLC6/SMAJ fleet); ARGB USB backfeed
(true per-source diode-OR `[M]`).
