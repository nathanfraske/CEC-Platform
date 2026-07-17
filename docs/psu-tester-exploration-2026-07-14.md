# PSU-tester board exploration — a representative DC load for shop PSU testing (2026-07-14)

**EXPLORATION ONLY — PROPOSED. No spec, schematic, board, CLAUDE.md, or owner-queue file
touched.** Owner ask (verbatim intent): *"what if we made a 'PSU tester' board that all the
modules can plug into, and it effectively acts as a representative DC load for PSU testing
inside shops — targeting repair/PC shops specifically? There is no product in a sub-$10K price
range that allows for proper LOAD testing on PSUs to that extent to my knowledge, so that may
be invaluable."*

Provenance: market prices and spec numbers below were gathered by web research on 2026-07-14;
every external claim carries its URL inline. Forum-era price figures (SunMoon, 2008–2013) are
flagged as such. Intel spec numbers are from the ATX 3.1-aligned design guide PDF (doc #336521
Rev 2.1a, Nov 2023, <https://cdrdv2-public.intel.com/336521/336521_Rev2p1a.pdf>). Internal
facts are cited to repo docs; the enabling 24-pin control-signal work is
`docs/standard-tier-review/atx24-sense-wire-interaction-study-2026-07-14.md` (PS_ON#
open-drain drive, PWR_OK µs edge-timestamping, −12 V measurement — schematic-only adds on
`atx-24pin-rev3`, owner decision box §7 of that study).

**Why the platform is unusually positioned:** the CEC modules ARE the instrumentation half of
a PSU test station — INA238 per-rail (24-pin: 12 V/5 V/3V3/5VSB), INA238 per-cable
(EPS/PCIe), INA240 per-pin (12VHPWR, 6 pins + rail divider), §6.13 comparator transient
detection, all reporting over CAN to a Hub that can already sequence a PSU on with no
motherboard (PS_ON# drive + PWR_OK timing, per the 07-14 study). What's missing is exactly one
thing: **a controllable, representative DC load**. This document sizes that missing piece.

---

## 1. Market scan — what exists, at what real prices

### 1a. The $10–50 "PSU testers" (voltage-only, zero load)

These plug into the 24-pin/EPS/PCIe connectors, apply essentially no load (a token few
hundred mA at most), and display rail presence/voltage and PG timing on an LCD. They cannot
detect regulation collapse under current — a PSU that reads perfect on all of them can still
crash a PC at 600 W.

| Product | Price | Source |
|---|---|---|
| Thermaltake Dr. Power III (ATX12V 3.1, reads 12+4-pin SENSE sideband) | $44.99 | <https://thermaltakeusa.com/products/dr-power-iii-ac-069-oo1nan-a1> |
| Thermaltake Dr. Power III Pro (ATX 3.1) | $49.99 launch | <https://www.techpowerup.com/350491/thermaltake-intros-dr-power-iii-pro-tester-for-atx-3-1-psus> |
| Rexus PST-3 LCD tester | $12.70 | <https://www.newegg.com/p/pl?d=power+supply+tester> |
| EN-Labs 1.8" LCD 20/24-pin tester | $17.49 | same Newegg listing |
| Amazon-generic class (Comidox/HDE/JacobsParts) | ~$13–25 | <https://www.amazon.com/HDE-Power-Supply-Tester-PCI/dp/B005UZHB6G> |

One step up that is still **not a load**: the **PassMark Inline PSU Tester (PM123), $456**
(1–4 qty; $387 at 11+) — inline per-rail V/I/power + ATX timing measurement between the PSU
and a *real running PC*; the PC is the load
(<https://www.passmark.com/products/inline-psu-tester/price.php>,
<https://www.passmark.com/products/inline-psu-tester/index.php>,
review <https://www.techpowerup.com/review/passmark-inline-psu-tester/>). No 12VHPWR cable in
the standard kit. Note this is the closest existing product to the CEC modules' own function
(instrumentation, no load) — and it retails at $456 for less per-point measurement than a
Complete System bundle carries.

### 1b. Programmable electronic DC loads (general-purpose, per-box)

| Load | Street price | V / A / W | Notes |
|---|---|---|---|
| Kunkin KP184 | ~$113–157 AliExpress, $191 Banggood | 150 V / 40 A / 400 W | budget king; RS-485 scripting (<https://usa.banggood.com/KP184-DC-Electronic-Load-Battery-Capacity-Tester-RS485-or-232-400W-150V-40A-AC220V-Professional-Battery-Tester-p-1974346.html>) |
| ITECH IT8512+ | $351 gray / ~$525–783 US channel | 120 V / 30 A / 300 W | <https://edv-automation.com/product/it8512/>, <https://www.circuitspecialists.com/itech-dc-electronic-loads> |
| Maynuo M9712 | €599–625 | 150 V / 30 A / 300 W | <https://www.welectron.com/Maynuo-M9712-Electronic-Load> |
| Rigol DL3021 / DL3031 | $549 / $999 | 40 A/200 W / 60 A/350 W, 15 kHz dynamic | <https://www.saelig.com/product/dl3021.htm>, <https://www.saelig.com/product/dl3031.htm> |
| Siglent SDL1020X-E / SDL1030X-E | $574 / $1,012 | 30 A, 200/300 W, 25 kHz dynamic | <https://siglentna.com/dc-electronic-load/sdl1000x/> |
| BK Precision 8600 | $1,584 | 30 A / only 150 W | wrong $/W for 12 V (<https://www.testequipmentdepot.com/bk-precision-8600-120v30a150w-programmable-dc-electronic-load.html>) |
| Chroma 63600 series | 63600-5 mainframe €2,040; 63640-80-80 module (80 V/80 A/400 W) €2,690 ea | modular | the class real PSU labs run (<https://www.datatec.eu/de/en/chroma-63640-80-80-module-dc-lasten>, <https://www.chromausa.com/product/modular-dc-electronic-load-63600/>) |

**Stack math for one 1000 W ATX 3.1 PSU** (12 V ≈ 80 A split across ATX+EPS+PCIe+12VHPWR,
5 V 20 A, 3.3 V 20 A, 5VSB 3 A, −12 V 0.3 A). Every mainstream bench load is *power*-limited
at 12 V (a "30 A" 300 W box sinks only 25 A at 12 V), so the 12 V rail alone eats 3–5 boxes:

- **Budget floor** — 5× Kunkin KP184: ≈ **$750–950** delivered; no calibration, no transient
  engine, RS-485-only scripting.
- **Gray ITECH** — 6× IT8512+: ≈ **$2,100** (double via US channels).
- **Reputable bench** — 3× Rigol DL3031 + 2× DL3021 ≈ **$4,100**; Siglent equivalent ≈ $5,200.
- **Lab grade** — Chroma 63600-5 + 3× 63640-80-80 + minors ≈ **€11–13k+ (~$13–16k)** per
  station, and this is the only tier with the slew and per-channel sync for the ATX 3.1
  excursion profiles (Rigol tops out at 15 kHz dynamic, Siglent 25 kHz).

**The fixturing gap is real and confirmed:** nobody sells high-current ATX-connector-to-load
fixturing. The $8–15 "ATX breakout boards" are bench-supply converters with 1.25 A polyfuses
and banana jacks (<https://www.seeedstudio.com/ATX-breakout-board-bench-power-supply.html>,
<http://dangerousprototypes.com/docs/ATX_Breakout_Board>) — useless at 40–80 A. Shops that do
this today crimp Mini-Fit pigtails into ring lugs by hand
(<https://forum.allaboutcircuits.com/threads/pc-psu-diy-load-tester-looking-for-the-right-cheap-components.172418/>).

### 1c. Professional ATX-specific test systems

- **Chroma 8000/8010 ATS** — the industry reference; rack ATE with AC source, DC loads,
  timing/noise analyzer (100 MHz noise BW), test executive; what PSU vendors use for ATX 3.x
  compliance (<https://www.chromaate.com/en/product/switching_power_supply_ats_8000_198>;
  Thermaltake's published GF3 ATX 3.0 report is a Chroma 8000 output:
  <https://file.thermaltake.com/file/qig/Toughpower_GF3_1350W_ATX_3_0_Test_Report.pdf>; Intel's
  own lab uses it: <https://www.chromausa.com/chroma-test-systems-fill-the-bill-for-atx12vo-power-supply-testing/>).
  Citable cost anchors: Tom's Hardware's 2010 lab build put a Chroma load mainframe + 4
  modules at roughly $9,000 (<https://www.tomshardware.com/reviews/psu-test-equipment,2657.html>);
  Jon Gerow (jonnyGURU), 2010: "Go the Chroma route and you could spend almost $10K," with
  100% US-rep markup (<https://forums.anandtech.com/threads/load-testing-and-recording.2098055/>).
  The oft-repeated "$100k+ rig" figure is **not citable as a published sentence anywhere we
  found** — but it IS defensible arithmetic from Cybenetics' posted equipment inventory (three
  Chroma stations + backup, each ~12 load modules + 3–4 kW AC sources + power analyzers +
  a hemi-anechoic chamber: <https://www.cybenetics.com/index.php?option=testing-equipment>) —
  call it $40–80k/station before the acoustics.
- **SunMoon SM-series (Taiwan)** — the historical reviewer/refurb-line ATX ATE and the closest
  thing to a prior product in exactly our niche. JonnyGuru ran an SM-8800; GamersNexus still
  tests on an SM-8800 + SM-220
  (<https://gamersnexus.net/hwreviews/3413-walmart-great-wall-power-supply-benchmark-review>).
  SM-268 class: ~33 A per 12 V input, "not suitable for testing power supplies above 900 W"
  (<https://www.hardwaresecrets.com/hardware-secrets-power-supply-test-methodology/2/>).
  Forum-era prices: SM-268 ≈ **$1,500**, SM-8800 ≈ **$3,000** new / ~$2,000 used
  (<https://forums.anandtech.com/threads/load-testing-and-recording.2098055/>,
  <https://hardforum.com/threads/for-sale-sun-moon-8800-atx-power-tester.1783561/>). SunMoon
  still lists the SM-268ATE (<http://www.sunmoontec.com/download-en/down38.html>) and runs an
  AliExpress storefront (<https://www.aliexpress.com/store/1101339229>) — but there is **no
  Western distribution with posted prices**, no ATX 3.x transient engine on record, and the
  design and UI predate 12VHPWR entirely. Fast Auto FA-828ATE is the other Taiwanese maker,
  quote-only (<http://www.fastauto.com.tw/english/Untitled-2.htm>).
- **Chinese ATE/aging racks** — Dongguan Chuangrui and Alibaba's ~700-listing showroom
  (<https://www.powersupplytestsystem.com/products.html>,
  <https://www.alibaba.com/showroom/power-supply-load-tester.html>): $1–3k-class ATX aging
  racks plausibly exist but are quote-only; **unverified** (flagged, OQ list).

### 1d. Open-source / DIY

- Kerry Wong's 400 W-continuous (1 kW peak, 100 A) linear-MOSFET load on IXTK90N25L2 — the
  most-referenced DIY design; single-channel, not ATX-aware
  (<http://www.kerrywong.com/2017/01/15/a-400w-1kw-peak-100a-electronic-load-using-linear-mosfets/>).
- Re:load Pro — open-source USB active load, only 25 W
  (<https://github.com/arachnidlabs/reload-pro>).
- Hackaday.io "ATX Power Supply Tester" — 5-channel voltage readout incl. −12 V, **no load**
  (<https://hackaday.io/project/174062-atx-power-supply-tester>).
- IRFP250+LM358 active-load builds ~120 W (<https://hackaday.com/2020/02/11/build-your-own-active-load/>);
  multi-rail MOSFET-bank forum builds on EEVblog/Badcaps, none productized
  (<https://www.eevblog.com/forum/projects/dummy-load-for-atx-ps-testing/>).
- **Gap:** no open project replicates a multi-rail ATX ATE with programmed load patterns, and
  none even attempts the ATX 3.x transient profile.

### 1e. Verdict on the owner's sub-$10k-gap claim

**Substantially TRUE, with two honest qualifications.** (1) A shop CAN assemble multi-rail
static load capability under $10k today — ~$750 in no-name Kunkins, ~$2–5k in reputable bench
loads — but only with hand-made connector fixturing, no ATX-aware automation, no spec
profiles, no report output, and no transient engine. (2) The niche HAS been served before:
SunMoon sold exactly this product class at $1.5–3k (forum-era pricing) and still nominally
sells the SM-268ATE — but with no Western channel, no posted prices, no 12VHPWR, and no
ATX 3.x. **The precise gap that is genuinely empty in 2026: a turnkey, ATX-connector-native,
multi-rail load tester with per-pin instrumentation, ATX 3.x-aware test profiles (excursion,
hold-up-adjacent, PWR_OK timing), and a printable verdict — under $10k, under $5k, or at any
Western-channel price at all.** The cheapest credible multi-rail static setup today is
~$750–950 (Kunkin stack + DIY wiring); the cheapest credible *ATX 3.1-transient-capable*
setup is Chroma-class at ~$13k+.

---

## 2. What "proper load testing" means — the pass/fail numbers

All from Intel doc #336521 Rev 2.1a (ATX 3.1) unless noted
(<https://cdrdv2-public.intel.com/336521/336521_Rev2p1a.pdf>; browsable:
<https://edc.intel.com/content/www/us/en/design/ipla/software-development-platforms/client/platforms/alder-lake-desktop/atx-version-3-0-multi-rail-desktop-platform-power-supply-design-guide/2.1/psu-power-excursion/>).

**Static regulation (Table 4-2):** 12 V **+5 %/−7 %** (11.20–12.60 V; the −7 % low end is an
ATX 3.x change specifically to allow power excursions), 5 V ±5 %, 3.3 V ±5 %, 5VSB ±5 %,
−12 V ±10 % **and optional** (Table 4-2 note 3; optional since the 2012 Rev 1.3). At the PCIe
aux/12V-2x6 connectors: +5 %/−8 % (Table 3-5).

**Power excursion (§3.1.2 Table 3-3)** — % of rated power, pulse-train tested with cycle RMS
= rated power, for PSUs >450 W with 12V-2x6:

| Excursion | Duration | Test duty cycle |
|---|---|---|
| **200 %** | 100 µs | 5 % |
| **180 %** | 1 ms | 8 % |
| **160 %** | 10 ms | 12.5 % |
| **120 %** | 100 ms | 25 % |

(≤450 W/no-12V-2x6 class: 150/145/135/110 %.) Voltage must stay inside Table 4-2 throughout.
Worked 1000 W example (Table 3-4): 2000 W for 100 µs, then 1900 µs at 917.7 W. Duty cycles
were 10/20/25/50 % in original ATX 3.0 (Rev 2.0) and changed in Rev 2.01
(<https://edc.intel.com/content/www/us/en/design/ipla/software-development-platforms/client/platforms/alder-lake-desktop/alder-lake-desktop/atx-version-3-0-multi-rail-desktop-platform-power-supply-design-guide/2.0/psu-power-excursion/>).
Connector-level (PCIe CEM 5.1 via Table 3-1): ≤3.0× total card power for T ≤ 100 µs — a 600 W
12V-2x6 card may excurse to 1800 W — permitted only through the 12V-2x6/card-edge, explicitly
not on legacy 6/8-pin aux. **Slew (Table 4-4): 5.0 A/µs on all 12 V rails** (12V-2x6-class
PSUs; 2.5 A/µs without), 1.0 A/µs on 5 V/3.3 V, 0.1 A/µs on 5VSB/−12 V; the 12V-2x6 interface
itself is capped at 5.0 A/µs (Table 3-5 note 1). Dynamic step sizes (Table 4-3): 12V1 40 %
required/70 % recommended of rated amps, PCIe rails 100→300 % steps, minors 30 %, repetition
50 Hz–10 kHz, with Table 4-7 capacitive loads (3300 µF on 12 V/5 V/3.3 V/5VSB, 330 µF −12 V).

**Hold-up (Table 4-8):** ATX 3.1 requires **12 ms at 100 % load**; recommends **17 ms at 80 %**.
ATX 3.0 and every ATX12V before it required 17 ms at full load; Cybenetics still scores
against 17 ms (<https://www.cybenetics.com/data/Cybenetics%20PSUs%20Test%20Protocol_en.pdf>).

**PWR_OK timing (Table 4-10):** T1 power-on <200 ms required (500 ms legacy), T2 rail rise
0.2–20 ms monotonic, **T3 PWR_OK delay 100–250 ms required** (100–500 legacy), T4 rise <10 ms,
**T5 AC-loss→PWR_OK-deassert >11 ms required (was >16 ms through ATX 3.0)**, **T6
PWR_OK-deassert→rails-out-of-spec >1 ms** (the early-warning contract). PWR_OK electricals:
TTL, <0.4 V @ 4 mA sink (Table 4-11). Sequencing: 12 V,5 V ≥ 3.3 V always; ≤20 ms spread to
regulation (§4.2.8). A good secondary walkthrough:
<https://www.lttlabs.com/articles/2026/04/08/psu-timing-requirements>.

**Protections (§4.5):** OVP required with fixed trip windows (Table 4-13): 12 V
**13.4/15.0/15.6 V** min/nom/max, 5 V 5.74/6.3/7.0, 3.3 V 3.76/4.2/4.3. SCP required (short =
<0.1 Ω; latch; PSU must survive; 5VSB must withstand an indefinite short). OCP required but
**no numeric trip range in the Intel spec** — Cybenetics' pass convention is ≤130 %
single-rail / ≤135 % multi-rail (protocol PDF above). OTP required. Output UVP is not an
Intel numeric requirement (PWR_OK deassert is the spec mechanism).

**Cross-load:** the only REQUIRED corner in ATX 3.x is the power-up cross-load (§4.3.2): PSU
must start and assert PWR_OK with **12 V ≤ 0.1 A while 5 V/3.3 V carry 0–5 A**; 0 A minimum
load on 12V2 is required (Table 4-9). Cybenetics' methodology runs ≥1450 combinations as a
characterization sweep (protocol PDF above) — a shop needs the corner, not the sweep.

**Ripple (Table 4-6):** 120 mV p-p on 12 V/−12 V, 50 mV on 5 V/3.3 V/5VSB, band 10 Hz–20 MHz,
measured on a 20 MHz-BW scope with 0.1 µF ceramic + 10 µF electrolytic at the connector.

**5VSB:** ±5 %, 3.5 A peak for ≤500 ms (USB wake), ≥3 A continuous recommended, OCP required,
standby efficiency floors (≥75 % @ 1.5 A/0.55 A, ≥45 % @ 45 mA) (§4.3.4, Table 4-5).

### 2a. Ranked by shop value ("is this PSU good/bad/marginal?")

1. **Static per-rail load at label + regulation** — the core verdict; catches aged/failing
   units that pass every $13 tester. Highest value per dollar of hardware.
2. **Transient excursion behavior** — "PC restarts in games" is the modern #1 PSU complaint;
   even a partial excursion test (150–200 % pulses on 12 V) separates ATX 3.x-honest units
   from relabeled stock. Second only because it's harder to build.
3. **Hold-up / PWR_OK early-warning** — "random reboots" diagnosis. Note the split (§3d
   below): T6 (>1 ms warning) is verifiable purely DC-side; the absolute 12/17 ms number needs
   AC-side switching.
4. **Protection sanity: OCP/OPP/SCP trip + recover** — does it shut down instead of melting,
   and does it come back. (OVP is NOT testable with a load — see §3d honesty note.)
5. **PWR_OK timing windows + power-up cross-load corner** — "won't POST" diagnosis; free once
   the 24-pin module timestamps edges.
6. **5VSB health** (2–3 A + 3.5 A peak) — standby-rail failures are a classic no-boot cause;
   nearly free to add.
7. **Ripple** — honestly the one place a sub-$10k box concedes to a Chroma station: spec
   ripple is a 20 MHz-BW scope measurement. Failing-cap PSUs often show ripple before droop,
   so this matters; we can ship a bandwidth-limited go/no-go *indicator*, never a spec number
   (§3d).

---

## 3. Architecture options

**Common frame for all options — how CEC modules plug in.** The tester is a powered chassis
(not a bare board) carrying, per PSU cable: a female input that the module's output assembly
mates into. The modules sit inline exactly as designed: PSU cable → module input header
(the ATX-standard Mini-Fit/12V-2x6 headers, spec §2.8) → module → output daughterboard +
extension assembly (the productized OQ-89 SKU) → tester load input. The tester itself joins
the CAN bus as one more module (ESP32-C6 + TJA1051T/3 + 2.2 kΩ DETECT, all locked platform
patterns), so the Hub orchestrates the whole sequence: PS_ON# assert via the 24-pin rev3
drive FET → rails up → PWR_OK edge timestamped to µs → load profile steps over CAN → INA
telemetry logged → verdict + printable report on the host. The instrumentation accuracy story
is the modules' existing one (±0.5–1 %-class, INA238/INA240 + firmware cal) — no new sensing
is designed for the tester; the tester board only needs coarse self-protection sensing.
Channel plan (full config): 24-pin (12 V ~10 A honoring the 6 A/circuit ATX bar, 5 V 20 A,
3.3 V 20 A, 5VSB 3.5 A, −12 V 0.3 A switched resistor), 2× EPS ~300 W each, 2–3× PCIe 150 W
each, 12V-2x6 600 W (50 A). Installed sink: **~850 W (base) / ~1600 W (full)**.

**The thermal reality is identical for all options and dominates the product.** Every watt
the PSU makes, the tester turns to heat. Airflow to carry it (Q = ṁ·cp·ΔT; CFM ≈ 1.76·W/ΔT):

| Test level | ΔT_air 20 °C | ΔT_air 30 °C | Exhaust temp @ 25 °C intake |
|---|---|---|---|
| 850 W | 75 CFM | 50 CFM | 45–55 °C |
| 1600 W | 141 CFM | 94 CFM | 45–55 °C |

850 W continuous is a space heater on high; 1600 W is a full space heater plus a hair dryer.
Concretely: 850 W = 2–3× 120 mm fans at real static pressure through heatsink tunnels; 1600 W
= 4× 120 mm or 2× high-RPM server fans, ducted, and it will be *loud* (bench-room, not
front-counter, acoustics). Chassis class: 3–4U rack box or ~450×350×150 mm desktop with
through-tunnel airflow, hot-surface grille, and 50 °C+ exhaust clearly labeled. This is the
platform's first product where enclosure/thermal engineering is the majority of the work.

### 3a. Switched resistive banks (relays/FETs + power resistors)

Binary-weighted resistor steps per rail group (e.g., 12 V steps of 1/2/4/8/16 A), switched by
cheap 25 V FETs (no linear operation — switch only). BOM class: 1600 W tested needs ~3200 W
installed resistor rating at 50 % derating ≈ 32× 100 W aluminum-shell parts ($4–8 ea) ≈
**$150–300 in resistors + ~$50 switching + plate/duct** — the cheapest sink per watt by far.
Reality: steps are coarse; current varies with rail voltage (I = V/R, so "load at exactly
40.0 A" is approximate); no CC regulation, no slew control; transient testing limited to
crude step-on/step-off (which is still di/dt-fast and diagnostic, but not the spec profile).
Perfectly adequate for §2a items 1, 5, 6 and OCP-by-steps. Size/thermal: the full heat load
above, in resistor bodies that run 150–250 °C surface without generous airflow — the touch-
safety problem at its worst.

### 3b. Linear FET electronic load channels (the standard e-load approach)

Per channel: linear-mode-rated MOSFETs (the DIY-proven IXYS linear L2 parts, e.g.
IXTK90N25L2 as in Kerry Wong's 400 W build,
<http://www.kerrywong.com/2017/01/15/a-400w-1kw-peak-100a-electronic-load-using-linear-mosfets/>),
op-amp CC loop against a shunt (a discipline this repo already owns), DAC or filtered PWM
setpoint from the MCU. Rule-of-thumb 100–150 W continuous per TO-247 linear device with
forced air; so 850 W ≈ 7–9 devices across 6–8 channels, 1600 W ≈ 12–16. Hazard: paralleled
linear FETs current-hog (Vgs-threshold tempco) → per-device source ballast + per-device
temperature sensing mandatory (thermal-runaway is THE failure mode of this class). BOM class:
$60–100 per 300 W channel (FETs $10–20 ea, op-amp/DAC/shunt, heatsink+fan share) → **$500–900
electronics for the full channel set, plus the same chassis/airflow burden**. Buys: true CC/CR
modes, programmable ramps for OCP characterization, clean cross-load corners, moderate-speed
dynamic stepping (kHz-class easily; the 5 A/µs spec slew needs the dedicated channel in 3c).

### 3c. Hybrid — resistive bulk + FET vernier + ONE fast transient channel (recommended)

The engineering-optimal split: resistors carry the boring 70–80 % of the heat (cheapest,
most robust watts), a modest linear FET bank (~300–400 W total) provides CC trim, ramps, and
cross-load precision, and **one** purpose-built fast channel on the 12 V/12V-2x6 path does
the ATX 3.1 excursion profile. Sizing the fast channel honestly against §2's numbers: for a
1000 W unit, the 200 %/100 µs point is a step from ~918 W baseline to 2000 W — a **~90 A step
at ~12 V, rising ≤5 A/µs (18 µs ramp), 100 µs on, 1900 µs off**. Energy per pulse is trivial
(0.2 J); the constraints are pulse SOA (3–4 paralleled linear FETs with ballast — 100 µs SOA
at 12 V is hundreds of amps for this class), loop bandwidth (~500 kHz), and **wiring
inductance** (at 5 A/µs, every µH costs 5 V — the fast channel must sit millimeters from its
connector, low-inductance bus, and the PSU's own cable inductance is part of the measured
system, as the spec intends). This is genuinely the hardest subsystem in the product and the
one that separates us from every sub-$10k option in §1 — Rigol/Siglent dynamic modes top out
around 15–25 kHz toggling and no ATX profile; the spec profile is today Chroma-station
territory. **Bench-gate it** (prototype the single channel before promising the tier).
BOM class for the hybrid: resistive bulk $200–300 + FET vernier $300–500 + fast channel
$150–250 + MCU/CAN/aux $50 + connectors/wear-heads $80 + chassis/fans/heatsinks $250–400 →
**~$1,050–1,600 BOM at the 1600 W/transient config; ~$650–950 for an 850 W static-only base**.

### 3d. Buy-vs-build: host commodity e-load modules

Two sub-options. (i) Carrier board hosting Chinese CC-load modules (Atorch DL24-class 180 W,
$30–60): rejected — firmware/reliability/no-slew, and the integration cost exceeds building
3b's channels. (ii) **"Bring your own bulk load" escape hatch: worth keeping** — the tester
speaks Modbus/RS-485 out to Kunkin KP184-class boxes
(<https://usa.banggood.com/KP184-DC-Electronic-Load-Battery-Capacity-Tester-RS485-or-232-400W-150V-40A-AC220V-Professional-Battery-Tester-p-1974346.html>)
so a shop that already owns loads can use the tester as fixturing+instrumentation+sequencer
only. Cheapens the entry SKU; complicates support; decision for the owner (OQ list).

### 3e. Safety (all options)

- **DC-side only, SELV**: every rail ≤12.6 V (+5 % of 12.6 max OVP test is out of scope —
  see honesty note below); no mains inside the product. This keeps it out of most
  certification pain — but NOT out of product-safety scope entirely: at 850–1600 W of
  deliberate heat, touch-temperature limits (IEC 62368-1 class: ~70 °C metal accessible
  parts), hot-air exhaust, and flammability of the enclosure are real engineering
  requirements even if formal listing is deferred.
- **Energy dump / fault modes**: the energy source is the PSU under test, which has its own
  OCP/SCP — and exercising those IS the product. Tester-side: per-channel fusing, per-heatsink
  temperature sensors, firmware watchdog that de-gates every load FET, and gate pull-downs so
  the unpowered/crashed default is NO LOAD (the same default-released philosophy as the
  PS_ON# drive FET in the 07-14 study). Linear-FET thermal runaway is designed out with
  ballast + per-device sensing (3b).
- **SCP testing is spec-sanctioned scary**: shorting a rail (<0.1 Ω crowbar FET) is a
  required-behavior test the PSU must survive by spec (§4.5.2) — but a defective unit can
  vent. The enclosure and the operator instructions must assume a PSU failure happens on the
  bench (fire-resistant bay, "stand clear" workflow). This is a liability posture question
  for the owner, not just engineering.
- **Connector wear is a consumable, by physics**: Mini-Fit Jr and 12V-2x6 are ~30-mating-cycle
  parts (PCIe CEM/product-line convention; the melt-prone 12V-2x6 especially). A shop does
  hundreds of cycles a year. Answer: the PSU-facing wear surfaces live on **replaceable
  fixture heads** — which is exactly the module daughterboard+extension assembly already
  productized as a SKU (OQ-89). Recurring revenue AND honest engineering; the tester never
  solders a PSU-facing connector to its own board.
- **The hold-up test needs AC-side switching — flagged, two paths**: (i) **Descope v1
  (recommended)**: purely DC-side, the module can still verify the T6 early-warning contract
  (PWR_OK fell >1 ms before rails left regulation — both edges are module-visible) and
  *relative* hold-up between units, with the operator pulling AC manually. The absolute
  12/17 ms number needs the AC-cut instant. (ii) **Tier-2 accessory**: an external, separately
  enclosed AC interrupter (zero-cross-aware SSR + AC-presence sense, reporting the cut
  timestamp over the same CAN/USB) — keeps mains out of the main product's cert scope but IS
  itself a mains product (its own listing burden). Note phase-angle matters: a naive relay box
  has ±8.3 ms half-cycle uncertainty — useless against a 12 ms limit; the accessory must be
  phase-controlled. Owner decision (OQ list).
- **Honesty notes on what a load CANNOT test**: **OVP** requires *sourcing* voltage into the
  rail — a sink cannot trigger it; a Chroma station does it with sources. We do not claim OVP
  verification. **OTP** requires heat-soaking the PSU — out of scope. **Ripple** per spec is
  20 MHz-BW scope work (Table 4-6); the INA238 path is 1 kHz-averaged and even the 12VHPWR
  Pro's LTC2358 tops out at 200 ksps — we can ship an AC-coupled, bandwidth-limited ripple
  *indicator* (comparator against the 120/50 mV thresholds) plus the spec's 0.1 µF+10 µF
  bypass fixture and a scope BNC tap per rail, and we say "indicator + scope tap," never a
  spec-grade ripple number.

---

## 4. Product shape

**Target price:** anchor against §1's honest alternatives — $750–950 buys uncalibrated boxes
plus a weekend of crimping; $2–5k buys reputable loads with zero fixturing/automation;
$13k+ buys transients. A turnkey box with fixturing, automation, per-pin instrumentation,
and a printed verdict earns the space between: **$1,995–2,495 for the base (850 W static +
protections + timing), $2,995–3,495 with the transient engine and 1600 W ballast** — i.e.,
squarely "SunMoon SM-8800 money, 2026 capability." At the §3c BOM classes ($650–950 base /
$1,050–1,600 full) plus modules, this holds the repo's ~3× landed retail convention
(`docs/pricing-study-2026-07-05.md` §4).

**Tiers:**
- **Tier 1 "Shop Kit"** — tester chassis (850 W, resistive bulk + FET vernier) + Hub + 24-pin
  + EPS + PCIe-2 + 12VHPWR-Std modules + patch/feed + fixture heads. Tests: static/regulation,
  OCP/OPP/SCP, PWR_OK windows, power-up cross-load, 5VSB (incl. 3.5 A peak), −12 V presence,
  T6 early-warning, connector-temperature soak (the 12VHPWR per-pin melt watch). Report
  output = the shop's customer-facing deliverable.
- **Tier 2 "ATX 3.1 transient module"** — the §3c fast channel (+$800–1,200), bench-gated.
- **Tier 3** — 1600 W ballast expansion + AC-interrupter accessory (absolute hold-up), if the
  mains-accessory decision goes that way.

**Composition with existing SKUs:** the tester consumes an (almost) stock Complete System
bundle as its measurement front end (bundle retail $309–$349 today, $399 loaded —
`docs/pricing-study-2026-07-05.md` §4) — the shop's modules are not captive: the same modules
un-dock and go into a customer build for in-situ diagnosis, which no competitor's ATE can do.
Prereq dependencies on the platform roadmap: the 24-pin rev3 PS_ON#/PWR_OK/−12 V adds
(07-14 study, owner decision pending), the OQ-89 daughterboard+extension assemblies (the
fixture heads), and an OQ-85 firmware-contract chapter for the test-sequencer profiles.

**Dev effort (honest):** this is the platform's first kilowatt-class thermal/enclosure
product — the electronics are mostly known disciplines (shunts, CC loops, CAN, the repo's
electrothermal solvers apply directly to the load board's own copper), but the chassis,
airflow, acoustics, wear-head mechanics, and the fast channel are new. Estimate 2–3 board
spins + enclosure iterations, ~6–12 months to a sellable Tier 1, Tier 2 gated on a
single-channel transient prototype. Firmware (sequencer + report) is a real sub-project.

**The honest wedge/moat:** (1) instrumentation density no ATE has at any price — per-pin
current + temperature on the melt-prone 12VHPWR during a 600 W soak is a Chroma station
add-on fixture (cf. the 55 A 16-pin thermal fixture in
<https://www.hwcooling.net/en/this-is-the-complete-atx-3-0-power-supply-test-lineup/>); we
get it free from the module. (2) Automation: one button → PS_ON# → full sequence → printed
customer report. (3) Price/channel: a real Western-channel product where SunMoon never was.
(4) The modules double as in-PC diagnostic tools. **What we must NOT claim:** Chroma-class
accuracy (we are ±0.5–1 %-class, not 0.05 %), spec-grade ripple, OVP/OTP verification, or
"ATX 3.1 compliance certification" — the language is "spec-derived test profiles /
indicative," never "certifies." Overclaiming here is the fastest way to lose the trust the
instrumentation story earns.

---

## 5. Risks / unknowns / open questions (decision-ready, for the owner)

1. **Market validation** — how many repair shops pay $2–3.5k for PSU verdicts? Is the channel
   direct, distributor, or refurb-chain B2B? (The refurb/aging-line segment — SunMoon's
   historical customer — may be bigger than walk-in repair.) Suggest: 5–10 shop interviews
   before any board work.
2. **Liability posture** — the product deliberately drives failing PSUs to their protection
   limits on a bench; a defective unit can vent/burn. Enclosure bay rating, operator workflow,
   disclaimers, insurance — needs a real review before launch, not after.
3. **Transient-channel bench gate** — commit Tier 2 only after a single-channel prototype
   demonstrates ~90 A/100 µs pulses at ≤5 A/µs into a live PSU with acceptable regulation
   measurement. This is the product's hardest engineering and its sharpest differentiation.
4. **Hold-up decision** — descope to T6-only (DC-side, recommended v1) vs build the
   phase-controlled AC-interrupter accessory (a mains product with its own cert scope)?
5. **Ripple posture** — indicator channel + scope BNC taps (recommended) vs omit entirely?
6. **Fixture-head consumables** — confirm the OQ-89 daughterboard+extension assemblies as the
   wear-head SKU (30-cycle connectors, shop does hundreds/yr); price the replacement head.
7. **Certification scope for a DC-only 1600 W heat box** — what listing (if any) does the
   shop channel demand (UL/CE/FCC-15B unintentional radiator per the platform posture)?
   Touch-temp and hot-exhaust compliance engineering happens regardless.
8. **Tester MCU architecture** — full CAN module (ESP32-C6 + locked platform patterns,
   recommended: it inherits DETECT/standalone-USB/§6.14 for free) vs dumb analog chassis
   driven by the Hub?
9. **"Bring your own load" Modbus out** (§3d.ii) — support burden vs cheaper entry SKU?
10. **Competitive check** — buy an SM-268ATE from SunMoon's AliExpress storefront
    (<https://www.aliexpress.com/store/1101339229>) and get quotes from two Alibaba
    aging-rack vendors to verify (or kill) the unproven $1–3k-Chinese-rack risk before
    committing pricing.
11. **OCP characterization adequacy** — is the 1 kHz-averaged INA path sufficient to
    timestamp trip events, or do the §6.13 comparator front-ends need to be the trip-time
    reference? (Likely yes-with-§6.13; verify on bench.)
12. **Acoustics target** — bench-room-only (cheap, loud) vs front-counter-tolerable
    (expensive airflow engineering)? Sets the chassis budget.
13. **Scope creep fence** — this document deliberately does NOT propose efficiency/PFC
    testing (needs AC-side power measurement — Chroma/Cybenetics territory,
    <https://www.cybenetics.com/data/Cybenetics%20PSUs%20Test%20Protocol_en.pdf>) or
    acoustic scoring. Confirm the fence.

**Biggest single risk:** market size at the price point (Q1) — the engineering is credible
and the gap is real, but SunMoon's niche history suggests this class sells in the hundreds,
not tens of thousands; the counterweight is that the modules amortize the instrumentation
across the consumer line, so the tester's incremental engineering is mostly the load + box.

---

## 6. ADDENDUM — TIER RULING + numbers (owner, 2026-07-14, same day)

**Owner ruling:** the tester ships as **Pro and Max tiers only**. No Standard tester now —
"Standard is not the shop spec anyway, that's our general one"; a Standard tester happens
later only if demand shows up (the §4 Tier-1 850 W "Shop Kit" config is therefore SHELVED as
the possible future Standard, not the launch product). **Pro = capable of the proper testing**
(the full spec-derived suite including the transient engine). **Max = capable of doing it
ALL, properly, to the level of the Max modules** (the §6.11/§6.13-ladder data-at-all-costs
tier).

### Tier definitions

**PSU Tester Pro** — everything §2 calls proper, load-side: 1600 W continuous hybrid sink
(§3c), the ONE fast transient channel running the full ATX 3.1 excursion profile
(200/180/160/120 % @ 100 µs–100 ms, ≤5 A/µs — bench-gated per OQ-3), cross-load corners,
OCP/OPP/SCP trip characterization with §6.13-comparator timestamping, PWR_OK T1/T3/T6 timing
(T5/absolute hold-up = relative-only without the AC accessory), 5VSB + −12 V, the 12VHPWR
per-pin melt-watch soak, ripple *indicator* + scope BNC taps, one-button sequence + customer
report. Instrumentation = the standard module set (12VHPWR-Pro swap-in optional).

**PSU Tester Max** — Pro plus everything a load-side box can honestly add, matching the Max
modules' data model:
1. **HF acquisition subsystem**: per-rail AC-coupled 20 MHz front ends into a muxed
   50–65 MSPS digitizer (P4/FPGA capture) → **spec-grade ripple** (real Table 4-6 numbers
   with the 0.1 µF+10 µF fixture, retiring the indicator-only fence at this tier),
   excursion-regulation waveforms, per-cable spectral capture (the Max-module data model,
   applied tester-side). BOM +$150–250.
2. **Second fast channel / switch matrix** — the excursion profile at any 12 V interface
   (12V-2x6 AND EPS), not just one path. +$150–250.
3. **OVP trip verification** via a current-limited programmable sourcing stage (drives the
   rail into the Table 4-13 windows: 12 V 13.4/15.6, 5 V 5.74/7.0, 3.3 V 3.76/4.3) —
   retiring the "a sink cannot test OVP" fence at this tier. +$60–120.
4. **Phase-controlled AC-interrupter accessory bundled** (separately-enclosed mains box,
   §3e path ii) → **absolute hold-up** (12 ms @100 % / 17 ms @80 %) and true T5. +$80–150
   BOM, own cert scope.
5. **Pro/Max module instrumentation set** (12VHPWR Pro + EPS/PCIe Pro-class). DEPENDENCY,
   honest: EPS/PCIe Pro are bounded-not-built and the Max modules are spec-PROPOSED (§6.11);
   the Max tester either launches "Max-ready" on Pro modules or waits for that line.
6. Optional 2000 W ballast (flagship 1600 W+ units; 200 % pulses ≈ 3.2 kW handled as pulse
   SOA, not continuous). +$100–150 + thermal.

Still out of scope at BOTH tiers (physics/product fences, unchanged): OTP (heat soak),
efficiency/PFC scoring (AC-side measurement), "certifies ATX 3.1" language.

### The numbers

| | **Pro** | **Max** |
|---|---|---|
| Tester BOM (§3c basis) | $1,050–1,600 | $1,490–2,370 (adds 1–4, 6) |
| Tester landed (+~18–20 % asm/test/freight) | $1,250–1,900 | $1,760–2,800 |
| Instrumentation (landed, pricing-study figures) | ~$115 (12VHPWR-config system) | ~$250–350 (Pro-class set, est.) |
| **Package landed** | **$1,365–2,015** | **$2,010–3,150** |
| **List target** | **$3,495 tester-only / $3,995 w/ modules** | **$5,995–6,995 (w/ modules + AC accessory)** |
| Implied multiple | 2.0–2.9× | 2.2–3.0× |
| Competitive anchor | SunMoon-money, 2026 capability; only sub-$10k box with the spec transient profile | ~half a Chroma-class entry; nothing else load-side-complete under $10k |
| Thermal | 1600 W / ~141 CFM, 3–4U (identical both tiers) | same (+2000 W option) |
| Timeline | 6–12 mo to sellable (fast-channel bench gate first) | Pro + 4–6 mo (digitizer, OVP source, AC accessory; module-line dependency) |

Margin honesty: the platform's ~3.0× landed convention holds only at the low-mid BOM end;
at the high end these prices run 2.0–2.4× — either accept capital-equipment-class multiples
(1.8–2.5× is industry-normal for test gear) or hold the line with BOM discipline to
≤$1,250/$2,300 landed. Owner call at pricing lock, not now. The §5 OQ list stands unchanged
— OQ-1 (shop interviews) and OQ-10 (competitive buy/quote) still gate everything, now with
two price points to validate instead of three.
