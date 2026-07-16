# PSU tester — component-class research (MCU/FPGA verdicts + prior art)

Web research 2026-07-16 (every external claim carries its URL inline, repo
research-doc convention). Builds on the canonical
`docs/psu-tester-exploration-2026-07-14.md` (§3 architecture + §6 owner tier
ruling: Pro/Max only, both 1600 W, Pro carries the fast excursion channel) and
the platform part studies (`docs/max-part-selection-2026-07-05.md`). Owner ask:
*"what class of components would we honestly need… What MCU? Does the Max
and/or the Pro need an FPGA?"*

**REV B (owner, 2026-07-16 — supersedes REV A's hub-role reading; see the
architecture-sketch REV B banner):** the tester is **a module** — it plugs
into the Hub as part of a bench suite (never inside a PC), speaks DETECT
4.7 kΩ (Pro) / 10 kΩ (Max) per the locked §2.3 codes, and carries its OWN
tier uplink: RS-485 streaming (Pro) / bidirectional 100BASE-T1 (Max) for its
pulse-actual waveforms. It also runs standalone over its own USB-C
(monitoring + PD self-power, §6.14 posture). **MCU verdicts stand — ESP32-P4
both tiers** — now for the tier-module reason (a Pro-class streaming module
is P4 by platform precedent: the 12VHPWR Pro). Max carries ONE T1 PHY (the
§13.2a module pattern), NOT a LAN9370 switch (that was hub-role hardware).
FPGA verdicts unchanged (none on Pro; GW5A-25 on Max, digitizer only). The
REV A tester-absorbs-Hub consolidation ("Bench Unit") is preserved as a
deferred field-test variant — sketch §9 item 7.

## 0. Verdicts up front

| | **Tester Pro** | **Tester Max** |
|---|---|---|
| MCU | ~~ESP32-C6~~ → **ESP32-P4** (REV B: Pro-tier streaming-module pattern — sources its RS-485 stream, USB-HS standalone port; still a full CAN module per OQ-8) | **ESP32-P4 + GW5A-25 FPGA** + one 100BASE-T1 PHY (module link) — the Max-module compute stack reused verbatim |
| FPGA | **NO.** Nothing in a Pro tester needs one: load regulation is per-channel *analog* CC loops; sequencing/profiles are ms-class MCU timer work; the 100 µs excursion pulses are timer-gated with *analog* slew shaping | **YES — but only for the HF digitizer** (50–65 MS/s LVDS capture is FPGA territory, same as the Max module; nothing else in the box justifies it) |
| Setpoints | 8-ch 16-bit SPI DAC (DAC80508 class) — mandatory anyway: the C6 has no true DAC peripheral (only the sigma-delta SDM PDM output, <https://docs.espressif.com/projects/esp-idf/en/stable/esp32c6/api-reference/peripherals/sdm.html>) | same + digitizer lane |
| Load FETs | Linear-rated (extended-FBSOA) **"Linear L2"-class** devices for every linear-mode stage; commodity FETs allowed ONLY as on/off bank switches | same |

The deep pattern: **this product needs almost no exotic silicon** — it is
op-amps, linear-rated FETs, power resistors, one SPI DAC, and the platform's
own sensing/CAN parts. The two genuinely hard subsystems (fast channel, Max
digitizer AFE) are hard in *analog design and layout*, not in component
exoticism — exactly what the prior art below says.

## 1. Prior-art shelf (the lineage we're adapting to ATX)

**The fast transient channel has a direct, famous ancestor pair:**
- Jim Williams, Linear Technology **AN104** — "Load Transient Response Testing
  for Voltage Regulators": the FET-based closed-loop load-transient generator
  (DC-bias + waveform inputs, gate-drive peaking/damper/loop-trim discipline)
  <https://www.analog.com/media/en/technical-documentation/application-notes/an104f.pdf>;
  open-hardware re-implementation: <https://github.com/eez-open/ltc-an104-transient-tester>.
- Jim Williams **AN133** — "A Closed-Loop, Wideband, **100 A** Active Load"
  ("brute force marries controlled speed") — our ~90 A/100 µs excursion pulse
  is *this circuit's* duty cycle, retargeted at an ATX harness
  <https://www.analog.com/media/en/technical-documentation/application-notes/an133f.pdf>.

**Linear-mode FET doctrine (why commodity FETs are banned from linear duty):**
- IXYS **IXAN0068**, "Linear Power MOSFETs — Basics and Applications" (the
  e-load/FBSOA reference) <https://www.mikrocontroller.net/attachment/327601/Linear_Power_MOSFETS_Basic_and_Applications.pdf>;
  the **Linear L2** product line exists precisely for programmable loads
  <https://www.littelfuse.com/products/power-semiconductors/discrete-mosfets/n-channel-linear/l2.aspx>,
  <https://www.digikey.com/en/product-highlight/i/ixys/linear-l2-mosfets>.
- The **Spirito effect** (hot-spot thermal instability of modern high-gm FETs
  at high VDS/low ID — the linear-mode killer): ADI SOA/hot-swap treatment
  <https://www.analog.com/en/resources/technical-articles/mosfet-safe-operating-area-and-hot-swap-circuits.html>,
  Infineon AN-1155 <https://www.infineon.com/dgdl/Infineon-Linear_Mode_Operation_of_Radiation_Hardened_MOSFETS-ApplicationNotes-v01_01-EN.pdf?fileId=8ac78c8c84f2c0670184f501d5c01463>,
  Nexperia IAN50006 <https://www.nexperia.com/applications/interactive-app-notes/IAN50006_Power_MOSFETs_in_linear_mode>,
  NASA TM-2010-216684 <https://ntrs.nasa.gov/api/citations/20100014777/downloads/20100014777.pdf>.

**Commercial teardowns (what the market actually builds):**
- Kunkin KP184 (the $150 box): commodity **IRFP250M** run linear — and an
  EEVblog thread of owners retrofitting linear-rated FETs after failures; the
  cautionary tale in one part number
  (<https://www.voltlog.com/best-affordable-electronic-load-kunkin-kp184-review-voltlog-299/>,
  <https://www.eevblog.com/forum/projects/linear-mosfets-for-kunkin-kp184/>).
- Array 3711A (Kerry Wong teardown): OP07 precision loops + 6× paralleled
  IRF3205 with deliberately-matched ballast traces for current share
  <http://www.kerrywong.com/2018/11/05/teardown-of-an-array-3711a-300w-dc-electronic-load/>.
- Rigol DL3021: EEVblog #1023 teardown
  <https://www.eevblog.com/2017/09/18/eevblog-1023-rigol-dl3021-electronic-load-teardown/>.
- Kerry Wong's 400 W/1 kW-peak DIY load on IXTK90N25L2 (already cited in the
  canonical doc) <http://www.kerrywong.com/2017/01/15/a-400w-1kw-peak-100a-electronic-load-using-linear-mosfets/>.

**Loop/setpoint architecture from first-tier vendors:**
- TI **TIDA-01525**: DAC80508 (8-ch 16-bit SPI) + precision op-amps as a
  programmable current source — the setpoint pattern, one DAC for the whole
  static channel set <https://www.ti.com/tool/TIDA-01525>.
- CC-loop stability practice (gate-C vs op-amp output-inductance resonance;
  series gate R + integrator C + snubber): community canon
  <https://electrical.codidact.com/posts/277301>; the precision-current-driver
  literature (Libbrecht–Hall lineage) <https://arxiv.org/pdf/1604.00374>.

**AC interrupter class:** phase-timed mains cutting requires **random/instant
turn-on (non-zero-cross) SSRs** — zero-cross parts cannot fire mid-cycle by
design <https://www.celduc-relais.com/en-us/zero-cross-or-random-relay-what-are-the-differences/>.

## 2. Component classes by subsystem

**2a. Bulk sink (both tiers, ~70–80 % of the watts).** Aluminum-shell
wirewound resistors, 100 W class, chassis-mounted, run at ≤50 % rating
(canonical §3a math stands: ~$150–300 covers 1600 W tested). Switched by
commodity logic-level NFETs in pure on/off duty (25–40 V, mΩ-class,
LCSC-jellybean — switching duty is Spirito-safe) with per-bank blade fuses.
Relays rejected (contact wear at shop duty cycles).

**2b. Linear vernier + fast channel FETs (the one non-negotiable part class).**
Extended-FBSOA linear-rated devices only — the L2 class. Verified sourcing:
**IXTK90N25L2 is LCSC-stocked (C2831650, ~$40, TO-264)** — the exact
Kerry-Wong part, JLC-orderable
<https://www.lcsc.com/product-detail/C2831650.html>; cheaper TO-247 L2
siblings (IXTH75N10L2 class) live at DigiKey/Mouser
<https://www.mouser.com/en/new/ixys/ixys-mosfet-with-fbsoa> — exact SKU ladder
is a sourcing-pass item. Rules from the prior art: ~100–150 W continuous per
TO-247/TO-264 device with forced air; **per-device source ballast + per-device
NTC** (platform NCP15XH103 / C77131) because paralleled linear FETs
current-hog (IXAN0068); vernier ≈ 3–4 devices (~300–400 W), fast channel
3–4 more sized by 100 µs pulse SOA, not continuous watts.

**2c. CC loops (per channel).** Precision op-amp (OP07 lineage → modern
OPA2186/OPA2277 class; the Array 3711A ships on OP07s) closing current
feedback on a shunt; compensation per §1's stability canon (series gate R,
output-to-inverting-input C, snubber where needed). Sense shunts: the
platform's own CSS2H-2512 family for low-current channels; the 40–50 A load
channels want 4-terminal power shunts (class decision at schematic time —
same Kelvin doctrine as §6.8).

**2d. Setpoints.** One **DAC80508-class 8-ch 16-bit SPI DAC** drives every
static channel's CC reference (TIDA-01525 pattern). The C6 offers no true DAC
(SDM/PDM only), so the external DAC is architecturally forced and better
anyway (16-bit monotonic, one REF). Slow channels could run filtered LEDC PWM,
but one 8-ch DAC at ~$3–6 removes the ripple/filter-lag question entirely.

**2e. The fast excursion channel (Pro AND Max — canonical §6 ruling).**
AN104/AN133 architecture retargeted: level DAC sets pulse amplitude; MCU
timer gates the pulse train (100 µs/1 ms/10 ms/100 ms @ the Table 3-3 duty
cycles — trivially inside GPTimer resolution); an **analog slew shaper**
enforces ≤5 A/µs (the 18 µs ramp is analog, not software); wideband loop =
fast op-amp (OPA810 class) + gate-drive stage into the ballasted L2 bank;
millimeters-scale low-inductance bus to the connector (every µH costs 5 V at
5 A/µs — canonical §3c). Bench gate unchanged: single-channel prototype
before any Tier-2 claim.

**2f. Trip timestamping / OCP staircase.** Reuse the platform §6.13 pattern
verbatim: INA181 + TLV7011 comparator per monitored rail into MCU capture
inputs — answers canonical §5 OQ-11 (yes, the comparators are the trip-time
reference; the 1 kHz-averaged INA path is the wrong clock for trip edges).

**2g. Control plane (Pro).** REV B: **ESP32-P4 + TJA1051T/3 + ONE RS-485
transceiver (its own module-side stream TX) + 4.7 kΩ DETECT** — the tester
is a Pro-tier module in the bench suite; the Hub keeps its job. Sequencing,
DAC writes, fan/thermal supervision, watchdog de-gate (gate pull-downs =
no-load on crash, canonical §3e) are ms-class; the RS-485 stream carries the
fast channel's pulse-actual waveform; USB-HS = the standalone/monitoring
port with PD self-power. **Still no FPGA on Pro.**

**2h. Max additions.**
- **HF digitizer lane = the Max module's, verbatim**: AD9253-80 quad 14-bit
  80 MS/s (LCSC C578831) → **GW5A-25** (LCSC C45617374) → ESP32-P4 — one RTL/
  firmware lineage with the Max module program (`docs/max-part-selection-
  2026-07-05.md`); the tester's per-rail AC-coupled 20 MHz front ends mux
  into it for spec-grade Table 4-6 ripple + excursion-regulation waveforms.
  This is the ONLY reason the Max tester carries an FPGA.
- **OVP sourcing stage**: **TPS55289** — I²C buck-boost, 0.8–22 V in 10 mV
  steps, programmable output current limit to 6.35 A in 50 mA steps, its own
  OVP/SCP <https://www.ti.com/product/TPS55289> — covers every Table 4-13
  trip window (12 V: 13.4–15.6 V; 5 V: 5.74–7.0; 3.3 V: 3.76–4.3) behind a
  series relay/diode so it only ever *sources into* the rail under test.
- **AC-cut timing — REVISED to the SENSE POD (see sketch §3c):** CEC builds
  NO mains-path product. The cut = any commodity listed relay/SSR box
  (zero-cross release = deterministic cut phase) driven from an isolated
  SELV trigger jack; the timing truth = the CEC AC sense pod: capacitive
  E-field pickup + split-core clamp CT (both non-contact/isolated by
  construction) + comparator (TLV7011-class, the platform part) → tester
  timestamp on the CAN MARK timeline; Max routes the pod analog into an AFE
  channel for sample-exact capture. The earlier random-fire-SSR product item
  is RETIRED — phase repeatability comes free from the commodity box's
  zero-cross release, and the measurement never depended on controlling the
  cut anyway.

**2i. Thermal/protection (both tiers).** Per-heatsink NTCs (C77131), PWM fan
drive + tach, per-channel fusing, and the firmware watchdog whose failure
default is de-gated/no-load. The platform's electrothermal solver applies
directly to the load board's own copper (canonical §4).

## 3. Open sourcing items (feed the BOM-lock pass)

1. L2 SKU ladder: price/stock sweep TO-247 vs TO-264 (IXTH75N10L2 /
   IXTK90N25L2 / siblings) across LCSC + DigiKey; pulse-SOA check at the
   90 A/100 µs point for the fast-channel parts specifically.
2. DAC80508 LCSC/JLC availability (TI parts are hit-or-miss there).
3. 4-terminal 50 A-class load shunt selection (Kelvin, TCR).
4. Fast-loop op-amp pick (OPA810 vs alternatives) + gate-drive stage.
5. AC sense pod parts: split-core clamp CT class (SCT-013-family or
   smaller), pickup electrode geometry vs IEC cord types, edge-comparator
   thresholds; candidate resellable listed trigger box (IoT-relay class).
6. FT600Q/FT601Q LCSC sourcing (inherited unknown from the Max egress ruling
   — only relevant if the Max tester exports raw waveforms at volume).
