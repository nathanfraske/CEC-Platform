# Current Beta Standard schematic and component-coherence audit

**Status: no source-level electrical blockers -- regenerated from current
source on 2026-08-12. Qualification warnings remain open. PCB fabrication
readiness is deliberately not evaluated.**

Machine-readable evidence is regenerated with
`python3 scripts/cec_beta_electrical_audit.py --scope standard-main --json-out docs/current-beta-standard-main-board-component-audit-2026-08-12.json`.
That snapshot records the exact manifest board list and a SHA-256 digest of
every root/child schematic used for each board. Conclusions in this document
must not be revised without regenerating that evidence first.

This document reviews electrical coherence in the current Standard Beta root
schematics and BOM selections. It asks whether the selected parts, values,
ratings, pin connections, support networks, and interfaces agree with their
manufacturer guidance and with the intended board function.

PCB synchronization, DRC, routing, trace width, placement, stackup, vias,
footprint manufacturability, and assembly process are outside this review.

## 1. Current Beta scope

The authoritative scope comes from the executable
`STANDARD_MAIN_BOARDS` set in `scripts/cec_beta_manifest.py`. The six
current Standard main-board schematics are:

| Board | Current root schematic |
|---|---|
| ATX 24-pin rev3 | `beta/atx-24pin-rev3/24pin-module.kicad_sch` |
| EPS 8-pin rev3 | `beta/eps-8pin-rev3/eps-8pin-rev3.kicad_sch` |
| PCIe 8-pin 2-port | `beta/pcie-8pin-2port/pcie8pin-2port-module.kicad_sch` |
| PCIe 8-pin 3-port | `beta/pcie-8pin-3port/pcie8pin-3port-module.kicad_sch` |
| 12VHPWR Standard | `beta/12vhpwr-standard/12vhpwr-standard-module.kicad_sch` |
| Standard Hub rev2 | `beta/hub-standard-rev2/hub-standard-rev2.kicad_sch` |

ARGB, daughterboards, Tester boards, generated candidate PCBs, archived
projects, Alpha boards, and the obsolete `eps-8pin` product are excluded. All
findings below come from fresh exports of these six root schematics. The Hub
was omitted in the earlier prose revision despite already being a current-wave
manifest board; the executable scope gate now prevents that class of drift.

## 2. Electrical verdict by board

| Board | Schematic/component verdict | Main open items |
|---|---|---|
| ATX 24-pin rev3 | **Mostly coherent; conditional sign-off.** | USB ESD-array VBUS capacitor, TPS2121 OVP dynamic margin/current-limit intent, and ESP32 module decoupling. |
| EPS 8-pin rev3 | **Schematic blockers repaired; conditional electrical sign-off.** | LP5907 effective-capacitance/load-step validation, ESP32 distributed-bulk deviation, and TPS2121 dynamic OVP margin. |
| PCIe 2-port | **Schematic blockers repaired; conditional electrical sign-off.** | LP5907 effective-capacitance/load-step validation, ESP32 distributed-bulk deviation, and TPS2121 dynamic OVP margin. |
| PCIe 3-port | **Same conditional electrical state as 2-port.** | Same shared control/USB cell; the third sensing channel itself is coherent. |
| 12VHPWR Standard | **Mostly coherent; conditional electrical sign-off.** | TPS2121 dynamic OVP margin, output-pigtail schematic representation, INA240 input-filter error budget, and ESP32 module decoupling. |
| Standard Hub rev2 | **Schematic topology and bounded power/hold-up models pass.** | OVP/source-switching bench qualification and OQ-56 hold-up/slow-brownout measurements remain open. |

## 3. Electrical findings requiring reconciliation

### 3.1 Corrections to the earlier review

- ESP32 radio operation is outside the product operating mode. The LP5907 is not
  rejected on generic radio-enabled current guidance; only its capacitor network
  and measured radio-disabled load margin remain open.
- INA181 saturation is not a metrology failure. These channels are binary
  fast-spike detectors; their acceptance criteria are threshold crossing,
  propagation, minimum pulse capture, and recovery/re-arm behavior.
- The earlier blanket EN-RC finding is removed. The exact ESP32-C6-MINI-1
  peripheral schematic uses 10 kOhm/100 nF, exactly matching the C6 boards.
  Espressif separately describes 10 kOhm/1 uF as a usual starting point and
  explicitly says to adjust it to the actual power/reset timing. The S3 board's
  100 nF implementation therefore remains a first-article reset test, not a
  schematic correction.
- The PCIe 47 kOhm / 10 kOhm OVP and missing-TPS2121-IN1-capacitor findings
  were stale. Current source has R15 = 43.2 kOhm, R16 = 10 kOhm, and C45 =
  10 uF from `VCC_RJ45` to ground. The static window now passes, while its
  52 mV worst-corner margin to the LP5907 6.0 V absolute maximum remains an
  explicit dynamic validation item.
- The PCIe LP5907 output network now uses exact Samsung
  CL21A475KAQNNNE / C1779 4.7 uF bulk at C7. The complete nominal output node
  is below 10 uF and input nominal capacitance exceeds output nominal
  capacitance. Exact effective-capacitance and load-step evidence remains open.
- PCIe C41 and R13 now have exact Samsung CL05B104KO5NNNC / C1525 and
  UNI-ROYAL 0402WGF1002TCE / C25744 selections, respectively.
- The EPS direct VBUS diode and missing-protection findings were stale after
  repair. Current source has exact Littelfuse 1206L075/16WR / C371166 feeding
  TPS2121 IN2, `VCC_RJ45` feeding IN1, TPS2121 OUT feeding `+5VSB`, and exact
  UMW USBLC6-2SC6 / C2687116 coverage on D+/D-/VBUS/GND. D2 is absent.
- EPS C7 is now exact Samsung CL21A475KAQNNNE / C1779 4.7 uF. The complete
  nominal LP5907 nodes are 11.1 uF input and 6.5 uF output, and the executable
  radio-disabled load budget is 200.772 mA including 20% margin against the
  regulator's 250 mA capacity.
- 12VHPWR R26/R27 are now exact 43.2 kOhm / 10 kOhm. The static TPS2121
  threshold window passes at 5.287 to 5.948 V; the separate 52 mV dynamic
  guardband qualification remains open.

### 3.2 Open corrections

| ID | Affected boards | Finding | Required electrical disposition | Primary evidence |
|---|---|---|---|---|
| ELEC-02 | ATX, EPS, PCIe 2/3, 12VHPWR | The exact ESP32-C6-MINI-1 and ESP32-S3-MINI-1 peripheral schematics show 22 uF plus 0.1 uF externally at the module supply. The current boards use smaller distributed networks. PCIe now has about 6.5 to 6.8 uF nominal after its LP5907 repair; this is intentionally below the module reference because the product permanently disables the radios and the LP5907 must remain inside its own capacitor envelope. | Treat the present network as an intentional radio-disabled deviation only after calculating effective capacitance and measuring the 3.3 V droop during boot, flash access, maximum CPU/peripheral activity, USB, CAN, and simultaneous sensor conversions. | [ESP32-C6-MINI-1 datasheet Figure 9-1](https://documentation.espressif.com/esp32-c6-mini-1_mini-1u_datasheet_en.html#peripheral-schematics); [ESP32-S3-MINI-1 datasheet Figure 9-1](https://documentation.espressif.com/esp32-s3-mini-1_mini-1u_datasheet_en.html#peripheral-schematics). |
| ELEC-13 | EPS, PCIe 2/3 | C7 is now 4.7 uF, so each complete nominal LP5907 output node is below 10 uF and nominal input capacitance exceeds output capacitance. The exact MLCC effective value and radio-disabled load-step behavior are not yet proven. Executable budgets total 200.772 mA (EPS), 202.752 mA (2-port), and 204.840 mA (3-port), including 20% margin, against 250 mA capacity. | Retain C7 = Samsung CL21A475KAQNNNE / C1779 and validate effective capacitance, startup, thermal margin, and worst-case load steps in the permanent radio-disabled mode. | [LP5907 datasheet](https://www.ti.com/lit/ds/symlink/lp5907.pdf); `scripts/cec_power_budget.py`; current EPS/PCIe root schematics. |
| ELEC-05 | ATX, EPS, PCIe 2/3, 12VHPWR | TPS2121 stages use 43.2 kOhm / 10 kOhm, producing about 5.639 V nominal and 5.287 to 5.948 V at calculated extremes. This passes the static 5.25-to-6.0 V window but leaves only about 52 mV at the worst calculated corner before dynamic overshoot. | Either add meaningful guardband or demonstrate by worst-case transient analysis/bench test that the downstream input never exceeds its absolute maximum. | TPS2121, LP5907, and TLV755P primary datasheets; resistor values are from the current root schematics. |
| ELEC-07 | ATX | USBLC6 D_USB1 pin 5 is tied to connector-side `VBUS_RAW`, but the schematic has no local capacitor on that node; the listed capacitors are after the PTC/ferrite. ST's application topology places the VBUS capacitor at the protection device/connector side. | Add the local VBUS-to-ground capacitor shown by the exact application topology or obtain an exact-device rationale showing it is unnecessary. Qualify the ST part actually listed on ATX rather than borrowing the UMW clone's data. | [ST USBLC6-2 datasheet, typical USB application schematic](https://www.st.com/resource/en/datasheet/usblc6-2.pdf). |
| ELEC-08 | ATX | TPS2121 U5 uses 20 kOhm ILIM, approximately a 4.8 A typical setting, near/above the device's 4.5 A continuous-current rating. U6 uses 100 kOhm, approximately a 1.2 A-class setting. The repository does not show a fault/current budget explaining the much higher U5 setting. | Tie both ILIM selections to the actual maximum load, connector/source limits, thermal limit, and fault-clearing objective. Do not use the device maximum as the default without a system-current need. | [TPS2121 datasheet tables 7-3 and 7-5](https://www.ti.com/lit/ds/symlink/tps2121.pdf#page=6). |
| ELEC-09 | 12VHPWR | J4 is described as an output pigtail but is assigned the same Molex 2191161161 male board-header MPN, symbol intent, and board-header footprint as input J3. Electrically, that does not define the permanent cable conductors, pin mapping, or assembly test. | Represent J4 as a soldered cable/wire landing or an explicit cable assembly, with all six 12 V, six ground, and four sideband conductors mapped. Lock wire gauge, cable connector, and continuity/hipot test requirements in the BOM/drawing. | Current 12VHPWR root schematic; [Molex 2191161161 product record](https://www.molex.com/en-us/products/part-detail/2191161161). |
| ELEC-10 | 12VHPWR | Each INA240A3 channel has matched 10 Ohm series resistors and 470 nF differential capacitance, giving roughly a 16.9 kHz differential pole. TI says input-filter components must be selected carefully, limits the series resistors to 10 Ohm or less, and calculates about 0.33% gain error at 10 Ohm before mismatch/error accumulation. | Decide whether bandwidth/noise benefit justifies the gain and settling error. Include resistor tolerance/TCR, capacitor tolerance, step response, overload recovery, and calibration in the measurement error budget. | [INA240 datasheet section 9.1, input filtering and Table 9-1](https://www.ti.com/lit/ds/symlink/ina240.pdf#page=18). |
| ELEC-12 | Standard mains | DNP CMC/fan options remain in source BOM data, and ATX uses ST USBLC6 while PCIe/12VHPWR use a UMW part with the same generic name. | Produce an electrically explicit fitted/DNP variant list and qualify each exact manufacturer independently. A shared generic value is not substitution approval. | Current root BOM fields; [ST USBLC6-2 datasheet](https://www.st.com/resource/en/datasheet/usblc6-2.pdf). |

### 3.3 Repairs confirmed by the regenerated audit

- **ELEC-01 on EPS is fixed:** the current hierarchy proves the complete
  protected, reverse-blocking dual-source chain and exact D+/D- ESD coverage;
  the legacy D2 is absent. The audit now fails closed on every required pin,
  net, MPN, and LCSC selection.
- **ELEC-03 on EPS is fixed at the nominal-network level:** C7 is exact
  4.7 uF C1779, producing 11.1 uF nominal input and 6.5 uF nominal output.
  The effective-capacitance and load-step qualification remains a warning.
- **ELEC-04 on 12VHPWR is fixed:** R26/R27 are 43.2 kOhm / 10 kOhm and the
  static tolerance window is 5.287 to 5.948 V. ELEC-05 retains the separate
  dynamic-margin question.
- **ELEC-04 on PCIe is fixed:** R15/R16 are 43.2 kOhm / 10 kOhm and the
  static tolerance window is 5.287 to 5.948 V. ELEC-05 retains the separate
  dynamic-margin question.
- **ELEC-06 is fixed:** C45 is an exact 10 uF X5R capacitor from `VCC_RJ45`
  to ground, and all three U4 IN1/IN2/OUT nodes have distinct selected bypass
  capacitors on both PCIe boards.
- **ELEC-11 is fixed:** C41 is Samsung CL05B104KO5NNNC / C1525 and R13 is
  UNI-ROYAL 0402WGF1002TCE / C25744 on both PCIe boards.
- **PCIe regulator capacity is proven at the paper-model level:** executable
  component sums plus the single 20% system margin leave 18.9% capacity on the
  2-port and 18.1% on the 3-port. This does not waive ELEC-13 bench evidence.
- **Hub scope and OVP source are repaired:** the Hub is now in the executable
  Standard-main scope, and U7/U11 use exact 43.2 kOhm / 10 kOhm dividers.
  Its 5VSB dropout/hold-up audit still proves that U8 detects ahead of D1 and
  ahead of the buck regulation floor; OQ-56 remains open.

### 3.4 Confirmed and non-blocking operating assumptions

- Radio is not used on any module. With RF clock-gated, the ESP32-C6-MINI-1
  datasheet reports about 27 mA typical at 160 MHz with peripheral clocks
  disabled and 38 mA typical with all peripheral clocks enabled. Even allowing
  substantial margin for flash and external ICs, a 250 mA LP5907 is a
  reasonable source for EPS/PCIe. This is accepted electrically provided the
  production firmware permanently prevents Wi-Fi, Bluetooth, and 802.15.4
  activation and a first article confirms total peak 3.3 V current and droop.
  Source: [ESP32-C6-MINI-1 current-consumption table](https://documentation.espressif.com/esp32-c6-mini-1_mini-1u_datasheet_en.html#current-consumption-characteristics).
- INA181 channels are intentional binary fast-spike detectors feeding TLV7011
  comparators. They are not waveform-mapping or metrology channels, and their
  analog value is not sampled. Saturation on a sufficiently large spike is
  therefore expected and harmless; the only required range check is that the
  minimum target spike crosses the worst-case comparator threshold and that
  overload recovery meets the required re-arm time. TI explicitly lists the
  TLV7011 for threshold detection and specifies approximately 260/310 ns
  propagation at 100 mV overdrive; the real minimum-pulse requirement must use
  the complete INA181/filter/comparator path. Sources: [INA181](https://www.ti.com/lit/ds/symlink/ina181.pdf)
  and [TLV7011](https://www.ti.com/lit/ds/symlink/tlv7011.pdf#page=7).
- ESP32 EN uses 10 kOhm/100 nF. This exactly matches the C6 module's Figure 9-1.
  Both C6 and S3 documents call 10 kOhm/1 uF a *usual* setting and explicitly
  permit adjustment for the actual ramp and reset sequence. Keep a cold-start,
  brownout, rapid-cycle, and programming reset test, but do not carry this as a
  schematic correction. Sources: [ESP32-C6-MINI-1 Figure 9-1 and reset note](https://documentation.espressif.com/esp32-c6-mini-1_mini-1u_datasheet_en.html#peripheral-schematics)
  and [ESP32-S3-MINI-1 reset note](https://documentation.espressif.com/esp32-s3-mini-1_mini-1u_datasheet_en.html#peripheral-schematics).

## 4. Shared active-component review

| Part and references | Schematic implementation | Verdict |
|---|---|---|
| ESP32-C6-MINI-1-N4: ATX/EPS/PCIe U1 | 3.3 V rail, boot/reset switches, GPIO8 strap, I2C, CAN logic, and USB signals are coherently connected. Radio-disabled active current is 27 to 38 mA typical at 160 MHz depending on peripheral clocks, so both the 500 mA TLV755 and 250 mA LP5907 have credible current margin. | **Supply capacity pass under the permanent radio-disabled assumption. ELEC-02 and effective-capacitance/load-step qualification remain.** |
| ESP32-S3-MINI-1-N4R2: 12VHPWR U1 | TLV755 500 mA-class source and about 11.9 uF nominal distributed capacitance support the reviewed approximately 212 mA worst-case load including margin. Boot/reset/strap connections are coherent. | **Supply capacity pass. ELEC-02 remains the decoupling check.** |
| TJA1051T/3: every U2 | VCC is 5 V, VIO is 3.3 V, GND and high-speed mode are correct for the `/3` variant; TXD/RXD connect to 3.3 V MCU logic. | **Pass.** CAN termination is intentionally system-level and must exist at the bus endpoints. |
| TLV75533PDRVR: ATX U3, 12VHPWR U16 | IN/OUT/EN pin use is correct; at least 1 uF nominal input/output capacitance is provided; output load budgets are below 500 mA. | **Schematic pass.** Exact effective-capacitance and thermal calculations remain sign-off evidence. |
| LP5907MFX-3.3: EPS/PCIe U3 | IN and EN are correctly tied to the 5 V source and OUT feeds 3.3 V. Pinout is correct. EPS/PCIe executable load budgets are 200.772/202.752/204.840 mA including the 20% system margin. Every C7 is now 4.7 uF, bringing each nominal node into range. | **Paper load/cap-network pass; effective-capacitance, startup, and load-step qualification remain open.** |
| TPS2121RUXR: ATX U5/U6, EPS/PCIe U4, Hub U7/U11, 12VHPWR U5 | IN1/IN2/OUT, priority, soft-start, status, CP2/OV2, and current-limit pins are logically coherent. EPS, PCIe, Hub, and 12VHPWR have distinct exact bypass selections on every audited power pin. | **Conditional:** ELEC-05/08 apply. Unpowered reverse behavior and source-switching transients need first-article verification. |
| INA238AIDGSR: ATX U10-U13, EPS/PCIe U10-U12 | Supply, I2C, VBUS, IN+/IN-, and address straps are coherent; ATX's four address combinations are unique. | **Pass.** Firmware must use the correct shunt range/calibration; ATX RS4 requires the wide range for precise measurement above about 1.64 A. |
| INA181A2IDBVR: ATX fast channels, EPS/PCIe U20-U22 | REF is grounded for unidirectional operation, A2 gain is 50 V/V, 3.3 V supply and positive-rail common mode are valid. Outputs feed TLV7011 comparators as binary fast-spike detectors; no analog measurement is taken. | **Pass for the stated purpose.** Verify minimum detectable spike, comparator threshold tolerance, pulse width, propagation delay, and overload recovery rather than linear full-scale accuracy. |
| TLV7011DBVR: ATX fast channels, EPS/PCIe U30-U32 | 3.3 V supply, push-pull output, common filtered threshold, and input/output polarity are coherent. | **Pass.** Comparator threshold range/hysteresis must be included in the protection-detection budget. |
| INA240A3DR: 12VHPWR U10-U15 | 3.3 V supply, REF1/REF2 grounded, high-side 12 V common mode, polarity, and A3 gain are valid. | **Conditional on ELEC-10.** |
| REF3030AIDBZR: 12VHPWR U4 | 3.3 V input, 3.0 V output, and 100 nF input/output capacitors are valid. It is used as a measured calibration reference rather than the ESP32 ADC reference. | **Pass.** |
| SN74LVC1G17DBVR: ATX U4/U8 | DBV pinout, 3.3 V supply, and 5 V-tolerant inputs are appropriate for the ATX control/status signals. | **Pass.** |
| AO3400A: ATX/12VHPWR Q1 | ATX PS_ON# current is trivial. 12VHPWR uses a 3.3 V gate, 100 Ohm gate resistor, default-on pull-up, low-side fan return, and SS34 flyback diode. The part is specified to 48 mOhm maximum at 2.5 V gate drive. | **Topology pass.** Confirm exact fan current and hot loss, but there is no schematic pin/connectivity error in the current root schematic. |
| USBLC6-2SC6 | D+/D- pass-through pins, ground, and VBUS reference are correct on ATX/EPS/PCIe/12VHPWR. | **EPS/PCIe/12VHPWR pass. ATX requires ELEC-07.** |
| 1206L075/16WR PTC and MPZ2012S601AT000 ferrite | The 750 mA hold PTC provides comfortable nominal margin for the sub-500 mA service/control loads; topologies that use the 2 A, 100 mOhm-max ferrite also retain ample current margin. | **Pass where present.** Inrush and ambient derating remain bench/calculation items. |
| PESD5V0S1BA clamps | Nodes and polarities are sensible for DETECT, ATX control, and VBUS clamps. The BOM's supplier identity is not consistently backed by a primary-manufacturer record. | **Conditional.** Lock VRWM, clamp voltage, leakage, capacitance, and pulse rating for the exact supplier part. |

## 5. Current-sense resistor and passive-network review

All shunts in the current design are evaluated as the two-terminal parts listed
in the root schematics/BOMs.

| Board / references | Electrical check | Verdict |
|---|---|---|
| ATX RS1-RS3: Bourns CSS2H 2 mOhm, 5 W | At 20 A, each dissipates 0.8 W and develops 40 mV; values are compatible with INA238 and INA181A2 ranges. | **Pass with exact rail-current and calibration budgets.** |
| ATX RS4: RESI LCSR2512FR025K9L, 25 mOhm, 2 W | At 3 A: 75 mV, 0.225 W. Basic value, tolerance, TCR, and rating are adequate. INA181 saturation on a large event is acceptable for the binary detector; INA238 must use its wide shunt range for precise measurement above about 1.64 A. | **Pass.** |
| EPS/PCIe RS1-RS3: Bourns CSS2H 0.5 mOhm, 6 W | Even at 30 A, dissipation is 0.45 W and shunt voltage is 15 mV; A2 fast-channel output is 0.75 V. | **Pass.** Actual connector/rail limit and calibration must set the software range. |
| 12VHPWR RS1-RS6: Bourns CSS2H 1 mOhm, 5 W | At the Molex 9.2 A/contact rating, each develops 9.2 mV and dissipates about 85 mW; INA240A3 ideal output is about 0.92 V. | **Pass.** Large nominal component margin; filter/calibration issue is ELEC-10. |
| USB-C R8/R9 on every board | Both CC pins use 5.1 kOhm Rd to ground, correctly declaring a USB device/sink. | **Pass.** |
| I2C R3/R4 | 2.2 kOhm pull-ups to 3.3 V are coherent for the short local bus. | **Pass; confirm total bus capacitance at system integration.** |
| EN/boot/strap resistors | 10 kOhm pull-ups are conventional and correctly oriented. The C6 10 kOhm/100 nF EN network matches the exact module peripheral schematic; PCIe C41/R13 now have exact C1525/C25744 selections. | **Schematic/BOM pass; retain first-article reset testing for both C6 and S3.** |
| TPS priority resistors | 100 kOhm / 33 kOhm networks coherently establish the selected source priority. | **Pass.** Verify actual switchover thresholds across tolerance. |
| TPS OVP resistors | ATX, EPS, PCIe, Hub, and 12VHPWR use 43.2 kOhm / 10 kOhm. | **Static selections pass. ELEC-05 and Hub source-switching qualification retain the dynamic questions.** |
| TPS ILIM resistors | ATX U5 20 kOhm; ATX U6 and PCIe/12VHPWR 100 kOhm. | **100 kOhm selections are coherent for a roughly 1 A-class service path; ATX U5 requires ELEC-08.** |
| Threshold R10/C40 or R60/C60 | 10 kOhm and 100 nF filter the PWM-derived common comparator threshold. | **Topology pass.** Firmware PWM frequency/ripple, settling, and comparator threshold tolerance need a calculation. |
| 12VHPWR NTC networks TH1/TH2, R20/R21, C20/C21 | 10 kOhm NTC over 10 kOhm to ground with 100 nF filtering gives a valid ratiometric ADC signal and negligible self-heating at 3.3 V. | **Pass.** Calibration table and fault detection for open/short sensors remain firmware requirements. |
| 12VHPWR rail divider R5/R6/C24 | 47 kOhm / 10 kOhm gives about 2.105 V at 12 V and remains ADC-safe through normal 12 V tolerance; 1 nF filters high-frequency noise. | **Pass.** Add overvoltage-range analysis for the intended fault maximum. |
| ATX -12 V network R74/R75/R76, D5, C64 | 15 kOhm to 3.3 V and 100 kOhm to -12 V level-shift the ADC node to about 1.30 V at -12 V and 2.87 V at 0 V; BAT54S clamps to the 0/3.3 V rails. | **Pass.** Include resistor/clamp leakage and ADC input error in calibration. |
| ESP32 supply MLCCs | The module datasheets show 22 uF plus 0.1 uF externally. Current boards use topology-specific distributed networks; EPS/PCIe are intentionally smaller after bringing the LP5907 nominal output capacitance inside its documented range. | **Conditional radio-disabled deviation under ELEC-02/ELEC-13.** Use effective capacitance and measured supply droop. |
| Other MLCC families | Exact Samsung MPNs are populated for the repaired EPS/PCIe 100 nF, 1 uF, 2.2 uF, 4.7 uF, and 10 uF positions. | **Nominal selections pass; ELEC-07 and effective-capacitance qualification remain where identified.** |

## 6. Connector electrical review

This section covers part rating and schematic pin use only, not footprint,
mounting, stackup, assembly, or mechanical fit.

| Connector | Boards | Electrical disposition |
|---|---|---|
| Molex 39291247, 24-pin | ATX J3 | 13 A/contact class is adequate for the ATX rail allocation when current is distributed across the intended contacts. Pin mapping must be checked against the licensed ATX definition in the final interface review. |
| Molex 87427-0802, 8-pin | EPS inputs/outputs | 13 A/contact gives ample nominal margin for EPS conductors. Four connector instances correctly represent two independent pass-through channels. |
| Molex 45586-0005, 8-pin | PCIe inputs | 9 A/contact provides ample nominal margin for a conventional 150 W PCIe 8-pin allocation. |
| TE 63969-1 blade receptacles | ATX/PCIe outputs | Electrical current class is suitable for the per-contact output allocation. System current sharing and temperature rise remain qualification items, not schematic contradictions. |
| Molex 2191161161, 12V-2x6 male header | 12VHPWR J3 | 9.2 A power-contact rating gives 55.2 A across six 12 V contacts, about 662 W at 12 V before derating. A 600 W allocation is therefore feasible but has limited connector-level thermal margin. J4 is not a valid use of this male-header definition; see ELEC-09. |
| Kinghelm KH-RJ45-58-8P8C | EPS/PCIe/12VHPWR/Hub | CAN_H, CAN_L, DETECT, ground, and module-power mapping are coherent where fitted. The supplier data is weak on VCC contact current and environmental margin, so the low-power control-rail load needs an explicit limit. |
| XKB U262 USB-C | All six | USB 2.0 D+/D-, CC1/CC2, VBUS, ground, and shield intent are coherent. EPS now includes the protected source-selection and D+/D- ESD chain. |

## 7. Electrical sign-off gate

For schematic/component sign-off, each affected finding must be marked
**fixed**, **accepted with a quantified operating limit**, or **removed from
scope**. The evidence packet should contain:

1. a fresh root-schematic netlist and exact fitted/DNP BOM;
2. zero semantic-audit blockers and explicit disposition of ERC warnings that
   can conceal real dangling or multiply-driven nets;
3. worst-case calculations for regulator load, capacitor effective value,
   TPS2121 OVP/ILIM, shunt/amplifier range, comparator thresholds, reset timing,
   connector current, and ADC scaling;
4. exact manufacturer datasheet and orderable part for every fitted item;
5. bench plans for source backfeed, OVP/overshoot, current limit, regulator
   startup/load steps, MCU brownout/reset, sensing saturation/calibration, and
   protection thresholds; and
6. an owner decision approving any deliberate deviation from manufacturer
   guidance, including the operating condition that makes it safe.

This gate makes no statement about whether a PCB can be fabricated or routed.

## 8. Primary references

- Texas Instruments: [TPS2121](https://www.ti.com/lit/ds/symlink/tps2121.pdf), [LP5907](https://www.ti.com/lit/ds/symlink/lp5907.pdf), [TLV755P](https://www.ti.com/lit/ds/symlink/tlv755p.pdf), [INA238](https://www.ti.com/lit/ds/symlink/ina238.pdf), [INA181](https://www.ti.com/lit/ds/symlink/ina181.pdf), [INA240](https://www.ti.com/lit/ds/symlink/ina240.pdf), [TLV7011](https://www.ti.com/lit/ds/symlink/tlv7011.pdf), [REF30](https://www.ti.com/lit/ds/symlink/ref30.pdf), [SN74LVC1G17](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf).
- Espressif: [ESP32-C6-MINI-1 module datasheet and peripheral schematic](https://documentation.espressif.com/esp32-c6-mini-1_mini-1u_datasheet_en.html), [ESP32-S3-MINI-1 module datasheet and peripheral schematic](https://documentation.espressif.com/esp32-s3-mini-1_mini-1u_datasheet_en.html), [ESP32-C6 hardware schematic guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c6/schematic-checklist.html), [ESP32-S3 hardware schematic guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html).
- NXP: [TJA1051](https://www.nxp.com/docs/en/data-sheet/TJA1051.pdf).
- Bourns: [CSS2H-2512](https://www.bourns.com/docs/product-datasheets/css2h-2512.pdf).
- RESI/LCSC: [LCSR2512FR025K9L exact part record](https://www.lcsc.com/product-detail/C494568.html).
- STMicroelectronics: [USBLC6-2](https://www.st.com/resource/en/datasheet/usblc6-2.pdf).
- Alpha & Omega Semiconductor: [AO3400A](https://www.aosmd.com/products/mosfets/low-voltage-mosfets-12v-30v/ao3400a).
- TDK: [MPZ2012S601AT000](https://product.tdk.com/en/search/emc/emc/beads/info?part_no=MPZ2012S601AT000).
- TE Connectivity: [63969-1](https://www.te.com/en/product-63969-1.html).
- Molex: [87427-0802](https://www.molex.com/en-us/products/part-detail/874270802), [45586-0005](https://www.molex.com/en-us/products/part-detail/455860005), [39291247](https://www.molex.com/en-us/products/part-detail/39291247), [2191161161](https://www.molex.com/en-us/products/part-detail/2191161161).

## 9. Review limits

This is a schematic, BOM, component-rating, and manufacturer-guidance review.
It does not substitute for licensed ATX/PCI-SIG/12V-2x6 compliance review,
firmware inspection, SI/PI analysis, environmental qualification, or physical
bench testing. It intentionally makes no PCB-fabrication or layout judgment.
