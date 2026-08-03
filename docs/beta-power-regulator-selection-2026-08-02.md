# BETA 3.3 V regulator selection and implementation — 2026-08-02

## Decision

The current BETA schematics use one regulator architecture per electrical need:

| Board | Implemented 3.3 V path | Reason |
|---|---|---|
| `12vhpwr-standard` | `+5VSB` -> TLV62569DBVR, 3.96 V nominal -> TLV75533PDBVR, 3.3 V -> `+3V3` | The six INA240 channels, REF3030, and ESP32 ADC form a precision measurement chain. The buck removes the LP5907 heat/current bottleneck; the post-LDO restores a quiet analog rail and rejects switching ripple. |
| `hub-standard-rev2` | selected `LOGIC_REG_IN` -> TLV62569DBVR, 3.318 V nominal -> `+3V3` | The Hub has source-presence and threshold sensing, but no precision shunt/INA/reference chain. A second post-LDO would add cost and loss without protecting a comparable measurement path. |

There is one EPS design, not a family of EPS variants. This change does not create or depend on an EPS variant.

## Worst-case rail budgets

These are design-review envelopes for wired operation, not measured typical draws. The controller allocation includes active wired firmware operation with wireless disabled. The residual allocation is the sum of every other fitted 3.3 V consumer in the reviewed schematic inventory: sensing/reference devices, CAN/logic, supervisors/comparators, source-management bias, indicator logic, dividers/pull-ups, and housekeeping. A 20% design margin is then applied to the complete subtotal.

| Board | Controller envelope | All remaining rail consumers | Subtotal | 20% margin | Required source current | Qualified source limit | Headroom |
|---|---:|---:|---:|---:|---:|---:|---:|
| 12VHPWR | 160.000 mA | 34.659 mA | 194.659 mA | 38.932 mA | **233.591 mA** | 500 mA, TLV75533 | **53.3%** |
| Hub Rev2 | 160.000 mA | 19.488 mA | 179.488 mA | 35.898 mA | **215.386 mA** | 1.76 A, selected inductor thermal-current rating | **87.8%** |

For the Hub, 1.76 A is deliberately the lower system limit: the VLS252010HBX-2R2M-1 thermal-current rating is below the TLV62569 2 A switch rating. For 12VHPWR, the post-LDO's 500 mA rating is the system limit.

## Setpoints and tolerance stack

TLV62569 uses `VOUT = VFB * (1 + RTOP/RBOTTOM)`.

### 12VHPWR intermediate rail

- Selected divider: 560 kOhm / 100 kOhm, 1%.
- Nominal: `0.600 * (1 + 560/100) = 3.960 V`.
- Worst low, using `VFB = 0.588 V`, low top resistor, and high bottom resistor: `0.588 * (1 + 560*0.99/(100*1.01)) = 3.816 V`.
- Worst high, using `VFB = 0.612 V`, high top resistor, and low bottom resistor: `0.612 * (1 + 560*1.01/(100*0.99)) = 4.108 V`.
- At the worst-low buck corner and a 3.333 V high LDO output, the TLV75533 still has about 483 mV across it. That clears the datasheet's 238 mV maximum dropout specification at 500 mA, even though this board's qualified load is only 233.591 mA.

### Hub output rail

- Selected divider: 453 kOhm / 100 kOhm, 1%.
- Nominal: `0.600 * (1 + 453/100) = 3.318 V`.
- Opposing 1% resistor and feedback-reference corners produce approximately 3.199 V to 3.440 V.

The Hub is therefore a direct switching rail. That is acceptable for its digital logic and coarse threshold/source-health sensing; it is not being represented as a precision analog supply.

## Thermal bounds

The calculations use a conservative 85% buck efficiency design floor rather than a typical curve point. They are paper bounds pending PCB copper and bench correlation.

| Device/location | Conservative dissipation | Package bound | Estimated rise | Estimated junction at 50 C ambient |
|---|---:|---:|---:|---:|
| 12VHPWR TLV75533 | `(3.96-3.3)*0.233591 + 3.96*25uA = 0.1543 W` | DBV `RthetaJA = 231.1 C/W` | 35.6 C | 85.6 C |
| 12VHPWR TLV62569 | about 0.1634 W at the 85% floor | DBV `RthetaJA = 188.2 C/W` | 30.7 C | 80.7 C |
| Hub TLV62569 | about 0.1263 W at the 85% floor | DBV `RthetaJA = 188.2 C/W` | 23.8 C | 73.8 C |
| 12VHPWR 2.2 uH inductor | `I^2 * 0.12 Ohm = 6.55 mW` | maximum DCR bound | small | PCB dependent |
| Hub 2.2 uH inductor | `I^2 * 0.12 Ohm = 5.57 mW` | maximum DCR bound | small | PCB dependent |

The 12VHPWR post-LDO is not thermally free, but it is inside the current and junction-temperature envelope and buys isolation for the precision rail. Adding the same stage to Hub would expend that loss with no equivalent measurement-chain benefit.

## Stability components

- Both bucks use VLS252010HBX-2R2M-1, 2.2 uH.
- 12VHPWR: 10 uF buck input, 10 uF buck output/pre-LDO, and 1 uF TLV75533 output. The distributed `+3V3` network is approximately 11.9 uF nominal.
- Hub: the regulator input and output capacitors are 10 uF. The distributed output network is approximately 20.3 uF nominal. The three cascaded TPS2121 stages now have nine explicit one-per-pin X5R/X7R bypass assignments across IN1, IN2, and OUT; five new 1 uF Samsung CL10A105KB8NNNC / LCSC C15849 parts close the shared-rail ownership gaps at U5 OUT, U11 IN1/OUT, and U7 IN1/IN2.
- All reviewed regulator and device-bypass capacitors now carry exact manufacturer, MPN, LCSC code, package footprint, and manufacturer product-page data in the authoritative schematics. The 100 nF U8 bypass was standardized to Samsung CL05B104KO5NNNC / C1525 in 0402.
- These values are within the reviewed datasheet application ranges. DC-bias derating still belongs in the physical-layout and production-capacitor review.

## Hub hold-up and dropout ordering

The final selected live rail is `+5VSB`. D1 feeds the isolated `+5V_HOLD`
reservoir, and the fitted `RJ_HOLD` path feeds the buck input from that
reservoir. U8 is powered by the held 3.3 V domain but senses `+5VSB` upstream
of D1 through `BLACKOUT_SENSE`, so `PWR_FAIL_INT` asserts before the reservoir
and regulator collapse. TPS3839 remains the final 3.3 V reset backstop.

- R26/R27/R28 set a nominal selected-rail trip of 4.355 V, with bounded 4.060 V to 4.663 V corners and about 0.1715 ms input RC time constant.
- C1 is Ymin VKMI2101C472MV / C487318, 4700 uF nominal and 3760 uF at -20% tolerance. D1 is MDD SS14 / C2480.
- At the reviewed 215.386 mA load including 20% design margin, 4.15 V conservative reservoir start, 3.45 V regulation floor, and 85% conversion floor, sudden-loss hold-up is 11.96 ms.
- Firmware is therefore limited to 10.00 ms from hardware interrupt to durable commit, leaving 1.96 ms calculated margin before load shedding.

This is a bounded paper result, not production proof. OQ-56 must exercise fast
loss and slow brownout, real source decay, capacitor ESR/capacitance over
temperature and aging, load shedding, and measured durable-commit latency.

## Vendor evidence and models

| Item | Repository asset | SHA-256 | Provenance/use |
|---|---|---|---|
| TLV62569 datasheet | `lib/datasheets/TLV62569.pdf` | `1BA6F55DFE678D06D563ACD6632F1F950A497D812270806021097B55CD81D3C4` | TI electrical limits, pinout, application network, package thermal data |
| TLV755P datasheet | `lib/datasheets/TLV755P.pdf` | `7A1B2CCB6233109ACDF404217ED966FFD2A507CE5153366DAE290FA431BD3589` | TI pinout, 500 mA rating, dropout, capacitor range, package thermal data |
| VLS252010HBX-1 data | `lib/datasheets/VLS252010HBX-1.pdf` | `570CAFC5B5DFBA8D38B47374815296E2B52E41956908E5977142D22C8ACDD1A0` | TDK inductance, DCR, saturation and thermal-current parameters |
| TLV62569 transient model | `lib/spice/vendor/TLV62569_TRANS.lib` | `FF1FCD570D0BDD234C5AC1494C827FAC9AEB24714E4DA440FEA329EFABA6448E` | official TI unencrypted PSpice transient model |
| TLV75533P transient model | `lib/spice/vendor/TLV75533P_TRANS.lib` | `965B1877F574DAB28E6E0A3EE9098A75325CF104DDF7CD103FC6307C2A918D34` | official TI unencrypted PSpice transient model |
| Inductor SPICE model | `lib/spice/vendor/VLS252010HBX-2R2M-1.lib` | generated from the cited TDK limits | conservative 2.2 uH plus 0.12 Ohm series model |
| Exact inductor STEP | `lib/3dmodels/Inductor_SMD.3dshapes/VLS252010HBX-2R2M-1.step` | `C85331D868780000BA04F5AB05C3B1007E88B5884CBD09E040E71A3E5C134218` | supplier-distribution CAD for LCSC C88527 |

The exact KiCad symbols are in `lib/vendor/cec-vendor.kicad_sym`; the exact inductor footprint is `lib/vendor/Inductor_SMD.pretty/VLS252010HBX-2R2M-1.kicad_mod`. The behavioral sanity harness resolves the real TLV62569 divider setpoint, while the official vendor transient models are retained for detailed converter work.

## BOM impact

The Hub does not receive a post-LDO. At the reviewed LCSC breaks, TLV62569 plus the inductor and two feedback resistors costs less than the former LP5907 IC by itself; revaluing the two existing capacitors from 1 uF to 10 uF and adding five C15849 mux bypass capacitors makes the whole-board delta modest rather than strictly negative. The five added MLCCs are a low-cost integrity fix, not an analog-cleanup stage.

12VHPWR adds the TLV75533 and the switching inductor/divider around the buck. At approximately 100–200 units, the regulator-stage change is expected to add roughly USD 0.20–0.30 per board before assembly and sourcing variance. The added cost is concentrated in the post-LDO and capacitor changes, not in the buck IC.

## PCB and placement handoff

The committed PCB and `candidate/` boards predate these power-stage schematic changes. They are useful only as historical outline, connector, mount, and routed-copper references until regenerated against the current schematic. They must not be used as the component-inventory or pin/net authority.

- Start from the current BETA schematic/netlist, never from an EPS variant or an older board snapshot.
- 12VHPWR: place the buck input capacitor tight to U3 VIN/GND; keep U3-SW-to-L1 and the output-capacitor return loop compact. Keep the switch node and inductor away from U4 REF3030, U10-U15 INA240 devices, Kelvin routes, and ESP ADC inputs. Place U16 and its output capacitor on the quiet side near the measurement-rail consumers.
- Hub: place U3 near the selected `LOGIC_REG_IN` source and its input return. Keep U3-SW-to-L1 and the output capacitor loop compact. Place the nine explicitly owned TPS2121 capacitors at their assigned IN1/IN2/OUT package pins; C24/C25 and C26/C28 are intentionally separate physical parts on shared nets. Do not inherit the former LP5907 placement semantics blindly.
- Re-run exact schematic/PCB signature freshness, ERC/DRC, local-bypass assignment, buck-loop placement checks, bounded DC sanity, and thermal checks before promoting a candidate.

No fabrication readiness is claimed by this schematic change. Switching-loop layout, EMI, transient response, rail ripple, and junction temperature still need to be verified on the regenerated current board and then on hardware.
