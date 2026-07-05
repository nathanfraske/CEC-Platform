# Max-stack part selection study (slow ADC / fast ADC / module FPGA / hub FPGA / MCU) — 2026-07-05

**STUDY ONLY — no spec, schematic, board, CLAUDE.md, or owner-queue file is touched. Feeds the next
controlled spec rev.** Executes the owner-requested "REMAINING PICKS" line of the 2026-07-05 ruling
banner atop `docs/bench-mode-max-stack-2026-07-05.md`, plus the same-day owner broadening: **the
FPGA slots are vendor-open** ("not locked in GOWIN in any way — whatever is easiest and cheapest and
makes sense"). Design basis carried forward, not re-derived: that doc (ruled architecture: slow path
= one ADC over all 6 INA240 outputs → FPGA decimation, ~80–100 kHz production usable/ch per §7.3's
INA240-100kHz-THD / shunt-~79.6kHz-corner pair; fast path = one fast ADC, **4 differential inputs**:
shunt, Rogowski coil, rail-V, across-connector dV; Max hub = fabric + ESP32-P4, N×100BASE-T1 ingest,
GbE egress; owner prototype = Sipeed Tang Primer 25K / GW5A-25), `docs/bench-mode-exploration-
2026-07-05.md` (LTC2358-18/ADS131M08 rate verifications), and `docs/research/max-instrument-channel-
decision-2026-06-11.md` (ruled fast-ADC class **A1 = 50–65 MS/s, 12–14 bit** / **A2 = 25 MS/s
ADC342x-class, 12–14 bit**, §3.7; Route A+C; V-5 amp / V-6 ADC registers). Recommendations feed
OQ-17/OQ-21 (and OQ-15/19/20/59 inputs); they do not close them — owner's pen per the platform rule.

**Method/sourcing.** Prices/stock pulled 2026-07-05 (one pass) from LCSC/Digi-Key/Mouser listings
and the jlcsearch LCSC-catalog mirror; LCSC-first per platform convention. Anything unreachable is
**UNVERIFIED** with reason. Spot prices and thin stocks move — re-verify at BOM lock.

## 1. Slow ADC (6 ch, ~80–100 kHz usable/ch production target)

Implied raw rate: the ruled posture is oversample-and-decimate in fabric (the platform's own §6.13
convention), so delivering 80–100 kHz usable honestly wants raw ≥2.5× the band — **≥250 ksps/ch
floor, 400–800 ksps/ch comfortable** (relaxed anti-alias, decimation gain). Simultaneous sampling is
required, not optional: the slow plane is the per-pin imbalance/dV/dI comparison domain, so the six
channels must be phase-aligned — internally-muxed scanners are disqualified as a class.

| Part | Arch / res | Rate/ch (6-ch) | Interface | Price 1 / 100 | Stock | Source |
|---|---|---|---|---|---|---|
| **AD7606B (RECOMMENDED)** | 8-ch true-simul SAR, 16-bit | 800 ksps/ch | parallel **or** serial SPI | $18.91 / $14.66 | 3,022 (LCSC C398827) | ADI page + LCSC, 2026-07-05 |
| LTC2358-18 (Pro's part) | 8-ch true-simul SAR, 18-bit | 250 ksps/ch @6ch en. (200 @8) | serial CMOS or **LVDS** | $78.79 / $58.51 (DK) | 158 (DigiKey); **no LCSC listing at all** | datasheet tables per `bench-mode-exploration.md` §1; DK 2026-07-05 |
| ADS131M08 | 8-ch ΔΣ, 24-bit | 32 ksps/ch (8-ch; fewer-ch uplift UNVERIFIED-by-quote, arch. says no) | SPI | $11.59 / $8.39 | 161 (LCSC C2685451) | TI page + LCSC, 2026-07-05 |
| MAX11046 | 8-ch true-simul SAR, 16-bit | 250 ksps/ch | **parallel-only** 20 MHz bus | $49.74 / ~$34.89@259 (DK) | 812 DK / 1 LCSC | ADI page + DK, 2026-07-05 |
| ADS8688 | 1 SAR + internal mux, 16-bit | ~62.5 ksps/ch (500 ksps aggregate) | SPI | $4.28–9.48@1 (listing discrepancy, unresolved) | LCSC (two listings) | TI page + LCSC, 2026-07-05 |

**Commonality evaluated first, per the brief:** reusing the Pro's LTC2358-18 buys inventory/corpus
commonality — but three measured facts cut against it *for the Max specifically*: (a) absent from
LCSC entirely (DigiKey-only, 158 units — a break in the LCSC-first assembly flow and a thin
production channel); (b) at 250 ksps/ch it sits exactly at the 2.5× floor of the 100 kHz target
(anti-alias must roll off inside 100→125 kHz — steep), where AD7606B's 800 ksps gives 8×
oversampling (~+1.5 bit ENOB recovery at the decimated rate, relaxed AA); (c) the Max slow path is
**FPGA-ingested** (ruled), so the Pro's P4 driver does not transfer — the ingest RTL is new either
way, reducing commonality to inventory only. AD7606B is ¼ the price, LCSC-native with 19× the
stock; parallel and serial modes both suit any candidate fabric. Honest counterpoints: 16-bit
native vs 18 (and a 0–3.3 V INA240 output uses only part of its bipolar ±5 V-class span — a
front-end gain/scale consideration, ~1.5 bit of span, partly bought back by the 8× OSR; the LTC's
SoftSpan fits tighter); and a flagged **LCSC-vs-DigiKey spread** (~$19 vs ~$47 @1) to reconcile at
BOM lock. ADS131M08 fails the target ~3× and dies here (it may remain the EPS/PCIe-Pro OQ-58
candidate — different rate class, unaffected). ADS8688 disqualified (muxed). MAX11046 clears but
is parallel-only, pricier, LCSC-absent. **Recommendation: AD7606B**, LTC2358-18 named alternative
if the owner weights 18-bit + Pro inventory commonality above rate margin + LCSC nativeness — that
trade is exactly OQ-21's decision.

## 2. Fast ADC (4 differential ch, ruled A1/A2 class)

Ruled class carried, not invented: A1 = 50–65 MS/s / 12–14 bit (full 10 Hz–20 MHz ATX band);
A2 = 25 MS/s / 12–14 bit (Nyquist 12.5 MHz, documented "measured-per-CEC-method" deviation).
Scaled 2→4 differential inputs per the 2026-07-05 ruling (shunt, coil, rail-V, connector-dV).

| Part | Ch × res | Grades | Output | LVDS pairs (4 ch) | Price / stock | Source |
|---|---|---|---|---|---|---|
| **AD9253 (RECOMMENDED, -80 grade)** | quad, 14-bit | 80/105/125 MS/s | serial LVDS (ANSI-644) | **~6 pairs total** (4 data + DCO + FCO) | -80: $41.67@1, 117 LCSC (C578831); -105: $66.49@1/$62.99@30, ~87–420 (C514281); -125: $84@1, 8 (C514282); DK commercial -125: 0 stock | ADI DS + LCSC/jlcsearch + DK, 2026-07-05 |
| AD9633 | quad, 12-bit (verified quad) | 80/105/125 | serial LVDS (same family; pin-detail UNVERIFIED) | ~6 | $185.16@1 DK, stock **5**; no LCSC | ADI page + DK, 2026-07-05 |
| ADS5242 | quad, 12-bit | 65 MS/s (= A1's exact point) | serialized LVDS | ~6–7 | **UNVERIFIED — no LCSC/DK/Mouser listing found despite TI "ACTIVE"** | TI page, 2026-07-05 |
| ADS4245 (2× dual) | 2× dual, 14-bit | 125 | DDR LVDS (16-clk latency, TI DS) | ~30 (2 chips) | $62.69–90.77@1 LCSC, stock 5–33 | TI DS + LCSC, 2026-07-05 |
| AD9648 (2× dual) | 2× dual, 14-bit | 105/125 | parallel/interleaved LVDS | heavier still | $141.15@1 DK, 36; no LCSC | ADI DS + DK, 2026-07-05 |

**Recommendation: AD9253BCPZ-80** (quad 14-bit 80 MS/s, 48-LFCSP). It is the nearest **orderable**
quad realization of A1 — no 50–65 MS/s quad at 12–14 bit is actually buyable today (ADS5242
unobtainable; AD9633 5-units/pricier at lower resolution) — sitting slightly *above* the ruled
50–65 band, which honors A1's intent (Nyquist 40 MHz ≥ the 20 MHz ATX band); it can also be clocked
down into the ruled band (50–65 MS/s → 0.80–1.04 Gbps/lane; pipeline minimum-rate floor UNVERIFIED,
check datasheet). Its serial-LVDS frame (16 bit × Fs) at 80 MS/s = **1.28 Gbps/lane** — the number
that becomes the module-FPGA input gate in §3. Four channels cost only ~6 LVDS pairs vs ~30 for any
2×-dual DDR-LVDS build, at half the price. **Data rate into fabric** (rate × 2 B packed × 4 ch):
80 MS/s → **640 MB/s = 5.12 Gbps** continuous-equivalent — reconfirming the ruled burst-only shape
(on-chip fabric RAM buffers well under 1 ms; external capture memory required, §3/§6). **ATX-band
honesty:** the sampling side fully covers 10 Hz–20 MHz at A1/-80 (front-end analog BW remains the
open V-5 amplifier selection); an A2-class 25 MS/s build would band-limit to 12.5 MHz and must
carry the ruled "measured-per-CEC-method" label — and since no orderable quad exists below the
AD9253 class, A2's savings do not materialize at 4 channels. Flags: -80 stock 117 (thin for
production); DK commercial -125 out of stock — do an ADI lifecycle check before lock (UNVERIFIED).

## 3. Module FPGA — VENDOR-OPEN scan (owner directive 2026-07-05)

Criteria in the owner's order: **EASIEST** (toolchain/licensing), **CHEAPEST** (real prices),
**MAKES SENSE** (must deserialize the §2 pick: 4× serial-LVDS at 1.28 Gbps/lane at the -80 grade,
or ≥1.04 Gbps if the ADC is pinned at 65 MS/s; plus decimation DSP + T1 MAC + buffering). HDL ports
across vendors — prototype continuity is a tiebreaker, not a lock.

| Part (module-class) | LUT | LVDS-in vs the ADC gate | Toolchain (EASIEST) | Price 1 / best break | LCSC stock | Source |
|---|---|---|---|---|---|---|
| **GOWIN GW5A-25 MG121 (RECOMMENDED)** | 23,040 LUT4, 28 DSP, 1,008 Kbit BSRAM, 6 PLL, ~36 LVDS pairs | **RX 1.6 Gbps — takes 1.28 G with margin** | Gowin EDA Standard: license-gated, free of charge (secondary sources, ~Sep 2024; UNVERIFIED vs primary); Sipeed license server confirmed | $46.88 / $44.55@30 | 485 (C45617374) | Gowin Arora-V page + LCSC, 2026-07-05 |
| Lattice ECP5 LFE5U-25F BG256 | 24 K LUT, 28 mult, 1,008 Kbit | generic DDR-geared LVDS ~800 Mbps class (commonly cited, UNVERIFIED-by-table); SerDes only on LFE5UM — **fails 1.28 G; even 50 MS/s (800 M) = zero margin** | **Full FOSS flow (Yosys/nextpnr/prjtrellis) — no license at all; easiest of all** | **$5.42–7.39** (-6/-7 grade) | 79 + 383 (C5272996/C1550762) | Lattice family docs + LCSC, 2026-07-05 |
| AMD Artix-7 XC7A35T | 33 K LC, 90 DSP | HR-bank LVDS RX ~1.25 Gbps class (DS181, commonly cited, UNVERIFIED-by-table) — takes 65 MS/s (1.04 G) with margin; 1.28 G marginal-over | Vivado free tier covers 7-series (vendor-stated); heavy proprietary install | ~$40–70 class by package/grade (DK snippet range; per-tier UNVERIFIED) | LCSC carriage unconfirmed | DK listings, 2026-07-05 |
| Efinix Trion T20 | 20 K | MIPI hard cores 1.5 Gbps are MIPI-specific; generic LVDS rate UNVERIFIED | Efinity: free license (vendor-stated) | UNVERIFIED (LCSC C485171 exists, price not extracted) | UNVERIFIED | Efinix/DK pages, 2026-07-05 |
| Intel Cyclone 10 LP | 16–25 K LE | LVDS RX sub-1G class (UNVERIFIED-by-table) | Quartus Lite free (vendor-stated) | UNVERIFIED this pass | UNVERIFIED | DK catalog, 2026-07-05 |

**Module verdict: GW5A-25 stays, now on merit, not lock-in** — it is the only budget part whose
verified LVDS-RX ceiling (1.6 Gbps) takes the recommended AD9253-80 with real margin; prototype
continuity (Tang Primer 25K) is the tiebreaker. ECP5 wins EASIEST+CHEAPEST decisively but fails
MAKES-SENSE on this ADC's input rate (usable only by pinning the ADC at 50 MS/s with zero interface
margin, or switching to a pin-heavy 2×-dual DDR ADC whose LCSC stock is 1–6 units). Artix-7 is
technically viable at 65 MS/s but costs the same-or-more than GOWIN with no confirmed LCSC channel.
Watch items on the pick: DSP=28 (naive parallel 4-ch FIR wants 16–32+ multipliers; time-multiplexed
MAC sharing makes it workable — flag, not insufficient); BSRAM buffers only ~0.2 ms at 640 MB/s →
**external HyperRAM/DDR3-class capture memory required** (QSPI PSRAM verified cheap at $2.94 —
APS6404L, C5333729 — but its ~84 MB/s-class write path cannot absorb the burst; specific part
UNVERIFIED — open line, OQ-19; GW5A supports DDR3 per Gowin). Family facts: line is 25/60/138 only;
GW2A = older non-Arora-V lineage; GW5AST-138 real (hard RISC-V) but no bare-chip price confirmed.
Channel anomaly stated honestly: the bare GW5A-25 ($44–47) prices above a whole Tang Primer 25K
board (~$19–29 retail) — volume/direct-Gowin channel likely differs (UNVERIFIED).

## 4. Hub FPGA + PHYs (N=4 / N=8) — VENDOR-OPEN; recommendation moves to ECP5

The hub job has **no fast-LVDS requirement at all** (N× RMII @50 MHz + one RGMII @125 MHz DDR +
aggregation/buffering) — so §3's ECP5 disqualifier vanishes, and the owner's easiest/cheapest
criteria dominate. Soft-MAC sizing (estimates by analogy — no vendor 100BASE-T1 MAC IP in Gowin's
catalog; ~800–1,500 LUT per T1 MAC by analogy to 1G MAC IP at ~1,488 LUT): N=4 ≈ 12–18 K LUT,
N=8 ≈ 20–30 K LUT.

**RECOMMENDED: Lattice ECP5 — LFE5U-25F-7BG256I at N=4 ($7.39@1, stock 383, LCSC C1550762);
LFE5U-45F-7BG256I at N=8 ($12.54@1, stock 75, C1550826; 44 K LUT).** Same caBGA256 footprint both
sizes → one hub layout scales N=4→N=8 by part swap. The BG256 package class clears the 100+-I/O
need N=8 RMII+RGMII+MDIO implies (exact per-SKU I/O count UNVERIFIED — pin-map check before
commit). FOSS toolchain (no license server anywhere in the hub build), and mature open GbE-MAC
precedent (LiteEth-class) exists on this exact family. This also **dissolves the GOWIN N=8
blocker**: GW5A-25's only stocked package (BGA121, ~82 I/O) cannot pin an N=8 hub, GW5A-60 has no
stocked distributor channel at all, and the 4–6× price delta ($44.55 vs $7.39/$12.54) buys nothing
the hub job uses. Spec Appendix B.2 already named ECP5 the "strongest contender against Gowin" on
the open-toolchain argument — this converges with it. Honest trades surfaced: (a) two fabric
vendors in one program (GOWIN module + Lattice hub) = two toolchains; the all-GOWIN alternative is
blocked at N=8 by package channel, the all-ECP5 alternative is blocked at the module by input rate
— the split is the "makes sense" answer, owner's HDL ports either way; (b) SRAM-fabric static draw
on the always-on budget (spec §6.11 v3.8 note) applies to BOTH vendors — the hub FPGA power
posture (gate on host-present?) is a design gate this study leaves open.

| Slot | Part | Key facts | Price 1 / 100 | Stock | Source |
|---|---|---|---|---|---|
| **T1 PHY (RECOMMENDED)** | Microchip **LAN8770M** | 100BASE-T1 (802.3bw), MII/RMII (RGMII = LAN8770R), VQFN-32/36 | $4.12 / $3.33 (DK); LCSC C5236053 $4.70/$4.45 **OOS** | 370 DK / 0 LCSC | Microchip brief DS00002550C + DK/LCSC, 2026-07-05 |
| T1 PHY alt | 88Q2110 (Marvell→**Infineon**, divested 2025-08) | 100/1000BASE-T1 dual-rate, RGMII/SGMII, QFN-40, AEC-Q100 | $5.36 / $3.67 (LCSC C39105882) | **1,470 LCSC** | Infineon page + LCSC, 2026-07-05 |
| ENT contrast (not for Max) | LAN9370 (4×T1-PHY switch) | 64-QFN confirmed; the ENT §13.2a part | $8.96 / $7.21 (DK) | **0 DK (4-wk)**; no LCSC; JLC C6072400 ~$14@100 | DK/JLC, 2026-07-05 |
| **GbE PHY (RECOMMENDED)** | Realtek **RTL8211F-CG** | RGMII confirmed, WQFN-40 | $1.52 / $1.04 (980+: $0.89) | **58,235 LCSC** (C187932) | Realtek page + LCSC, 2026-07-05 |

LAN8770 recommended on cost + single-rate right-sizing + Microchip-T1 lineage continuity with ENT;
its LCSC line being OOS (DigiKey posture meanwhile) vs the 88Q2110's real LCSC stock at $3.67@100
makes the Infineon part a genuinely viable LCSC-native fallback despite its automotive-grade
posture. Each **Max module** also carries one T1 PHY — counted in the module BOM. The GbE host
port needs magnetics/magjack (allowance below).

## 5. MCU

**ESP32-P4 confirmed** — already the §6.11 Max-table pick and the platform's uniform Pro/ENT
posture (§13.2a/§13.6 P4-uniform rulings); nothing found arguing otherwise. Orderable form: bare
chip only (no module confirmed): **ESP32-P4NRW32** (in-package 32 MB PSRAM — matches §6.11's "P4
with PSRAM"), LCSC C22387510, QFN-104: $5.72@1 / **$4.47@100**, stock **455 (thin — flag)**.

## 6. BOM roll-ups (100-qty where findable; allowances marked; ranges honest)

**(a) 12VHPWR Max module** (dual-board §6.11 construction; selected parts + platform carryovers):

| Line | Basis | 100q est. |
|---|---|---|
| Fast ADC AD9253BCPZ-80 | $41.67@1 LCSC; 100q break UNVERIFIED | $35–42 |
| Slow ADC AD7606B | $14.66@100 LCSC | $14.66 |
| FPGA GW5A-25 MG121 | $44.55@30 LCSC (deepest break) | $42–47 |
| MCU ESP32-P4NRW32 | $4.47@100 LCSC | $4.47 |
| T1 PHY LAN8770M | $3.33@100 DK | $3.33 |
| 6× INA240A3DR | 6 × $1.87 single-qty (C2060584, CLAUDE.md pass); 100q lower UNVERIFIED | $7–11.2 |
| 6× CSS2H-2512R-1L00F shunt | 6 × $0.3457@100 (LCSC C4175647; stock 2,911) | $2.07 |
| REF3033 | $0.34@150 (LCSC C36658) | $0.34 |
| Rogowski: PCB-embedded coil + ADA4897-1 integrator + passives | coil = board copper ≈$0; amp $1.61@100 (C208560, OOS flag); passives est. | ~$2 |
| 4× wideband diff front-end amps (V-5 OPEN — no part chosen) | ALLOWANCE, UNVERIFIED class | $8–16 |
| Capture memory (HyperRAM/DDR3-class; QSPI PSRAM too slow, §3) | ALLOWANCE, part UNVERIFIED | $3–6 |
| FPGA config flash | allowance | ~$1 |
| Power tree (2–3 TPS7A-class LDOs + FPGA-core buck + 12V-present gating, §6.11) | allowance | $5–8 |
| Connectors: 2× 12V-2x6 (Molex 2191161161, consigned — est.), RJ-45 ($0.23@150, C2683360), USB-C, board-to-board pair | allowance (12V-2x6 + B2B UNVERIFIED) | $6–9 |
| CAN (TJA1051T/3 ~$0.40) + protection/NTC/buttons/passives | platform carryover + allowance | $4–6 |
| 2× PCB (analog 4L 2 oz + digital 6L) | allowance, fab-quote dependent | $8–14 |
| **Module total** | | **≈ $150–190 (mid ≈ $170)** |

Context: the old §6.11 indicative BOM was $140–170 (pre-ruling, uncosted); this lands at/just above
its top — the adders are the 4-wide fast front end, the FPGA, and T1. It stays **under §6.11's own
$200 "six-channel scope front end" decline threshold** — but not by much — while buying a different
instrument than the one declined (4 simultaneous wideband differential inputs + fabric, vs 6×
continuous per-pin scope). Choosing the LTC2358-18 alternative (+$44) pushes ≈ $195–235, across it.

**(b) Max hub, N=4:** ECP5 LFE5U-25F $7.39 + P4NRW32 $4.47 + 4× LAN8770 $13.32 + RTL8211F $1.04 +
4× RJ-45 $0.92 (verified subtotal **$27.14**) + GbE magjack allowance $2–4 + power front end
(§2.9-class cascade + FPGA buck) $5–8 + buffer memory ~$3 + CAN/ESD/LEDs/USB-C/supervisor/hold-up
~$6–9 + 6L PCB $6–10 + config flash $1 → **≈ $50–70 (mid ≈ $58)**.

**(c) Max hub, N=8:** ECP5 LFE5U-45F $12.54 + 8× LAN8770 $26.64 + 8× RJ-45 $1.83 + RTL8211F $1.04
+ P4 $4.47 (verified subtotal **$46.52**) + scaled allowances (~$28–40) → **≈ $75–95 (mid ≈ $85)**.
(The pre-broadening GOWIN-only answer had this at $120–175 dominated by an unverified GW5A-60 line
— the vendor-open scan is what made N=8 costable at all.)

## 7. Retail bands (convention, NOT policy — ranges only)

Platform anchors: 12VHPWR **Pro BOM target $98–99** (spec §6/README; no Pro retail stated
anywhere); old §6.11 Max line **$140–170 BOM → $499–599 retail**, i.e. the platform's own prior
estimate embeds an **≈3.5× multiplier** (499/140, 599/170). Applying convention multipliers to the
rolled-up ranges, explicitly as convention:

| Item | BOM (this study) | 2.5× | 3× | ≈3.5× (platform's own precedent) |
|---|---|---|---|---|
| 12VHPWR Max module | $150–190 | $375–475 | $450–570 | $525–665 |
| Max hub N=4 | $50–70 | $125–175 | $150–210 | $175–245 |
| Max hub N=8 | $75–95 | $190–240 | $225–285 | $265–335 |

The module's existing **$499–599 target remains inside the 3–3.5× band of this BOM** — the ruled
architecture does not break the published price story. Hub-Max has no prior anchor; N=4 reads as a
$149–249-class product, N=8 $229–349-class. No false precision.

## 8. Slots with no good LCSC-carried part + verification register

- **LTC2358-18: absent from LCSC entirely** (the decisive commonality counter-fact, §1).
- **Quad fast ADC below 80 MS/s: does not exist orderable** (ADS5242 active-but-unobtainable;
  AD9633 5 units) — A2-at-quad-width is effectively unavailable (§2).
- **GW5A-60/-138 bare chips + any GW5A-25 package above BGA121: no stocked distributor channel** —
  now moot for the hub (ECP5 pick) but still the module's growth-path constraint (§3/§4).
- **LAN8770 LCSC line OOS** (DK-only today); LAN9370 LCSC-absent + DK 0-stock (ENT's problem, noted).
- **HyperRAM/DDR3 capture memory + V-5 wideband diff amps: no part selected** — open engineering
  lines (allowances only), to close at Max schematic time.
- Thin stocks to watch at production: AD9253-80 (117), GW5A-25 (485), ESP32-P4 (455), shunt
  (2,911), ECP5-45F (75), ADA4897-1 (OOS). UNVERIFIED items carried: AD9253 100q price + lifecycle
  + min-clock; AD9633 frame detail; ADS8688/AD7606B listing discrepancies; ECP5 ~800 Mbps and
  Artix-7 ~1.25 Gbps LVDS-input ceilings and BG256 per-SKU I/O counts (commonly-cited class
  figures, not table-verified this pass — **verify before any vendor flip**); Artix-7/Trion/
  Cyclone-10 pricing detail; Gowin Standard-license-free claim (secondary only); GW5A resource
  cells (not per-datasheet-table verified); 88Q2110 DK/Mouser pricing; 12V-2x6/B2B connectors and
  every "≈/est." power/PCB allowance line.

**Sources:** LCSC pages C4175647, C2683360, C45617374, C398827, C2685451, C187932, C22387510,
C36658, C5333729, C5236053, C39105882, C208560, C578831/C514281/C514282 (jlcsearch mirror),
C1550762/C5272996 (LFE5U-25F), C1550826 (LFE5U-45F), C485171 (T20); Digi-Key listings
(LTC2358ILX-18, AD9253/AD9633/AD9648, MAX11046, LAN8770M-I/PRA, LAN9370-I/KCX, XC7A35T/XC7S25
class); Mouser (GW5A UG324 non-stocked); ADI/TI/Microchip/Realtek/Infineon/Gowin/Lattice/Efinix
product pages and datasheets as named inline; Gowin Arora-V family page (resource table); Sipeed
wiki + community docs (license server; Gowin-EDA-free-since-2024 secondary claim); in-repo:
`bench-mode-max-stack-2026-07-05.md`, `bench-mode-exploration-2026-07-05.md`,
`max-instrument-channel-decision-2026-06-11.md`, spec §6.11/§13.2a/Appendix B.2, the
12vhpwr-standard BOM CSV, and CLAUDE.md sourcing notes. All web figures pulled 2026-07-05.
