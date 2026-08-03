# BETA 3.3 V regulator selection and implementation — revised 2026-08-03

## Decision

| Board | Implemented path | Decision basis |
|---|---|---|
| `12vhpwr-standard` | `+5VSB` -> TLV75533PDRVR -> `+3V3` | Direct 500 mA high-PSRR LDO in the thermal-pad DRV package. It removes the LP5907 current/thermal bottleneck without adding a switch node beside the six-channel measurement chain. |
| `hub-standard-rev2` | held `LOGIC_REG_IN` -> TLV62569DBVR + 2.2 uH -> `+3V3` | Direct buck. Hub has no precision INA/reference chain, and energy conversion down to 3.45 V preserves useful shutdown hold-up. No post-LDO is fitted. |

The superseded 12VHPWR buck-plus-post-LDO proposal is not the selected design.
It solved the small-package LDO heat problem but was unnecessarily complex.
There is one EPS design, not an EPS variant family.

## Component-by-component worst-case budgets

The executable source of record is `scripts/cec_power_budget.py`. These are
wired-mode qualification envelopes. The owner-locked BETA firmware has radios
disabled. The 160 mA controller envelope already exceeds the Espressif
107.9 mA modem-sleep/all-clocks figure plus 10 mA flash-access allowance; a
20% system margin is then applied once to the full component subtotal.

### 12VHPWR Standard

| Consumer | Quantity x maximum | Budget |
|---|---:|---:|
| ESP32-S3-MINI wired controller envelope | 1 x 160.000 mA | 160.000 mA |
| INA240 | 6 x 2.400 mA | 14.400 mA |
| TJA1051 VIO | 1 x 0.500 mA | 0.500 mA |
| REF3030 | 1 x 0.059 mA | 0.059 mA |
| RESET and BOOT pull-ups, both asserted | 2 x 0.330 mA | 0.660 mA |
| fan gate and tach pull-ups, both low | 2 x 0.330 mA | 0.660 mA |
| two temperature dividers, upper bound | 2 x 0.330 mA | 0.660 mA |
| **Subtotal** | | **176.939 mA** |
| **20% design margin** | | **35.388 mA** |
| **Required source current** | | **212.327 mA** |

TLV75533 capacity is 500 mA: 42.5% utilized and 57.5% remaining after the
system margin.

### Hub Standard Rev2

| Consumer | Quantity x maximum | Budget |
|---|---:|---:|
| ESP32-S3-WROOM wired controller envelope | 1 x 160.000 mA | 160.000 mA |
| TJA1051 VIO | 1 x 0.500 mA | 0.500 mA |
| TPS3839 supervisor | 1 x 0.0005 mA | 0.0005 mA |
| TLV7011 comparator | 1 x 0.010 mA | 0.010 mA |
| four DETECT pull-ups, all low | 4 x 0.330 mA | 1.320 mA |
| RESET and BOOT pull-ups, both asserted | 2 x 0.330 mA | 0.660 mA |
| temperature divider, upper bound | 1 x 0.330 mA | 0.330 mA |
| HUB_3V3 sense divider | 1 | 0.0579 mA |
| comparator threshold divider | 1 | 0.1571 mA |
| comparator hysteresis path | 1 | 0.0033 mA |
| buck feedback divider | 1 | 0.0060 mA |
| **Subtotal** | | **163.045 mA** |
| **20% design margin** | | **32.609 mA** |
| **Required source current** | | **195.654 mA** |

The conservative converter capacity remains the inductor's 1.76 A thermal
rating, below the buck IC's 2 A rating: 11.1% utilized and 88.9% remaining.

## Why the old LDOs are not enough

The problem is not only nameplate current. The limiting corner is simultaneous
5.25 V input, full qualified load, 50 C ambient, and the package thermal path.
Quiescent power is small relative to the load term and is omitted below.

| Case | Dissipation | RthetaJA | Estimated Tj at 50 C | Result |
|---|---:|---:|---:|---|
| 12VHPWR LP5907 SOT-23 | `(5.25-3.3)*0.212327 = 0.414 W` | 193.4 C/W | **130.1 C** | exceeds 125 C operating limit; only 15.1% current-rating headroom |
| 12VHPWR TLV75533 DRV WSON | same 0.414 W | 100.2 C/W | **91.5 C** | selected; 57.5% current headroom |
| Hub LP5907 SOT-23 | `(5.25-3.3)*0.195654 = 0.382 W` | 193.4 C/W | **123.8 C** | essentially at the 125 C limit before PCB/environment uncertainty |
| Hub TLV62569 buck | about 0.114 W at the 85% efficiency floor | 188.2 C/W | **71.4 C** | selected; layout/bench correlation still required |

The direct thermal-pad LDO is therefore the right 12VHPWR answer: it is quiet,
uses fewer parts than the buck/post-LDO cascade, and is thermally credible. The
Hub remains a buck because its issue is hold-up as well as heat.

## Hub dropout detection and hold-up ordering

The final selected live rail is `+5VSB`. D1 feeds the isolated `+5V_HOLD`
reservoir and the fitted `RJ_HOLD` path feeds the buck from that reservoir. U8
is powered by held `+3V3` but senses live `+5VSB` upstream of D1 through
`BLACKOUT_SENSE`. Therefore `PWR_FAIL_INT` asserts on source dropout while the
reservoir and regulator are still alive. TPS3839 remains the final 3.3 V reset
backstop; regulator dropout is not the normal shutdown trigger.

The deterministic model is `scripts/cec_hub_holdup.py`:

- 4700 uF nominal, 3760 uF at -20% tolerance;
- conservative reservoir start 4.15 V;
- buck regulation floor 3.45 V and 85% efficiency floor;
- qualified 195.654 mA load;
- **13.167 ms sudden-loss hold-up**, leaving **3.167 ms** over the 10 ms durable-commit budget;
- dropout-detect trip: 4.355 V nominal, bounded 4.060 V to 4.663 V.

For comparison, the LP5907 guaranteed floor is approximately
`3.3*1.02 + 0.25 = 3.616 V`. The same minimum reservoir and load produce only
**10.262 ms**, just 0.262 ms above the commit budget before ESR, aging,
temperature, source decay, and load-transient uncertainty. Increasing bulk
capacitance could recover margin, but costs more volume than keeping the buck.
OQ-56 remains the required hardware proof.

## Selected parts, CAD and vendor assets

| Item | Selection / repository asset |
|---|---|
| 12VHPWR regulator | TLV75533PDRVR, LCSC C2861750, WSON-6 exposed pad |
| Symbol | `lib/vendor/cec-vendor.kicad_sym` (`TLV75533PDRVR`, exact DRV pin map) |
| Footprint | `lib/vendor/Package_SON.pretty/WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm.kicad_mod` |
| 3D model | `lib/3dmodels/Package_SON.3dshapes/WSON-6-1EP_2x2mm_P0.65mm_EP1x1.6mm.step` |
| Datasheet | `lib/datasheets/TLV755P.pdf` |
| Transient model | `lib/spice/vendor/TLV75533P_TRANS.lib` |
| INA240 datasheet | `lib/datasheets/INA240.pdf` |
| Hub buck | TLV62569DBVR, LCSC C141836 |
| Hub inductor | VLS252010HBX-2R2M-1, LCSC C88527 |

The WSON footprint and STEP model are vendored from the official KiCad
libraries. The behavioral sanity harness uses the actual DRV pins 6=IN and
1=OUT; the official TI transient model remains available for detailed work.

## BOM comparison

At the reviewed LCSC quantity break, TLV75533PDRVR is about USD 0.228. The
discarded 12VHPWR cascade was approximately USD 0.25 before its two feedback
resistors and assembly cost (buck + DBV LDO + inductor). The selected direct
LDO also removes the buck, inductor, two feedback resistors, switch node, and
intermediate capacitor.

Hub's TLV62569 plus inductor is about USD 0.132 before two low-cost feedback
resistors, below the thermal-pad LDO IC alone. It needs no post-LDO because no
precision analog measurement domain is supplied from this rail.

## Layout contract

- 12VHPWR: expose U16 pad 7 to a local ground copper area and thermal vias;
  place C1 at IN/GND and C2 at OUT/GND; keep the regulated rail and REF3030/
  INA240 Kelvin paths away from 12 V switching edges and connector current.
- Hub: keep U3 VIN/SW/L1/C3/GND switching loop compact; place the selected-rail
  reservoir and D1 path for low impedance; keep U8 sensing attached to live
  `+5VSB` upstream of D1.
- The current hierarchy is the schematic/netlist authority. Committed PCB and
  `candidate/` copies that predate these changes are not placement authority.

No fabrication readiness is claimed by this schematic change. ERC, DRC,
placement-loop checks, hold-up testing, ripple, transient response, and thermal
measurements still gate board promotion.
