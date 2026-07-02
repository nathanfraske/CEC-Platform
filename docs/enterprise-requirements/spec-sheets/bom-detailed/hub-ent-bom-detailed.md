# ENT hub — detailed engineering BOM, master assembly

_Status: DRAFT rev 0.1 (2026-07-02). This assembles the four subsystem BOM passes
(`bom-a-compute.md`, `bom-b-uplink.md`, `bom-c-module-if-base-secio.md`, `bom-d-power.md`)
plus the survey-9 MC/MC-Max block and the REQ-107..109 storage rows into per-SKU totals,
and RECONCILES the cross-subsystem findings. Line-item detail (every passive, computed
values, datasheet links) lives in the four subsystem files — this master carries only
what changes when they meet. Prices 100q, dated 2026-07-02; `[RFQ]`/`[est]` as marked.
Survey 10 (100BASE-T1 module link) is RESOLVED into §5._

## 1. Reconciliations (parent/child + cross-subsystem divergences, resolved here)

| Topic | Divergence | Resolution (working baseline) |
|---|---|---|
| VDD-core buck | BOM-A picked MPM3833C (3A, $2.08, LCSC-native) with a flagged headroom risk (core est. 1.5–3.0A vs 3A ceiling); its child researcher found **MIC22705YML-TR (7A, $3.62@25)** is the actual VDD-core part on BOTH Microchip kits (Icicle + Discovery — same 095T die as ours) | **MIC22705YML-TR for VDD core** (kit precedent + kills the headroom risk before a Power Estimator run exists); MPM3833C stays for VDD18/VDD25/3V3-domain where currents are housekeeping-class. Revisit only if the Power Estimator run shows core <2A |
| MSS/SGMII reference clock | BOM-A fitted TWO oscillators (50 MHz single-ended Y1 all-SKUs + 125 MHz diff Y2 NET-only, Abracon AX3D — flagged out of stock); its child verified from BOTH kit schematics that **one 125 MHz LVDS oscillator (DSC1123BL5-125.0000, $2.38–2.56, in stock) drives MSS_REFCLK_IN_P/N and serves MSS + SGMII together** (same Bank-5 pin pair) | **One DSC1123BL5-125.0000, populated ALL SKUs** (MSS boot needs the refclk regardless of SGMII use — this also corrects BOM-A's NET-only population for Y2). SiTime SIT9120 family = Microchip's own named second source. Y1 (50 MHz) deleted unless schematic capture shows a separate fabric clock need |
| Boot flash density | BOM-A priced W25Q128JV (16 MB, $2.04); the storage ruling (REQ-HUB-COMMON-107) upgraded the NOR tier to 32 MB class | **W25Q256JV** (FIQ SOIC-16 $3.00 / EIQ WSON-8 $3.21, child-verified; JV not JW — 3.3 V part). Child also verified the SS/SN suffix variants BOM-A's brief named are phantoms |
| JTAG header | Child recommended TE 103310-1 (0.1" THT, FlashPro-ribbon-native, $1.61@125); BOM-A picked Samtec FTSH-105-01-L-DV-K (1.27 mm, the Icicle's actual J23, $0.97 LCSC, needs the FP adapter kit) | **FTSH-105-01-L-DV-K** (kit precedent + LCSC-native + smaller); note the FlashPro adapter-kit requirement in the bring-up plan; 103310-1 recorded as the ribbon-native alternate |
| External ADC (cross-cutting) | Three subsystems independently confirmed the PolarFire has **no on-die ADC**; DETECT ×8 + rail-sense ×4 + RJ-11 loop + eFuse IMON all need a read path | **ADD one ADS7830IPWR-class I2C 8-ch ADC (~$1.00, LCSC C161747) + one analog mux or a 2nd unit** (12+ channels total). Assigned to subsystem C ownership (it serves the port/sense domain); BOM-C's LM393 window comparator on the RJ-11 loop stays (independent alarm path even if the ADC-scan firmware is down) |
| VDDA quiet LDOs | BOM-A extrapolated TPS7A2010/TPS7A2025 decivolt SKUs (existence-unverified at distributors); child confirmed the 1.05 V code exists in TI's list but is thin-stocked | Keep **TPS7A20-family** with exact-SKU confirmation at RFQ; fallback = adjustable TPS7A21 if the fixed codes are unstocked. (LP5907 CANNOT serve VDDA — 1.2 V floor, child-verified) |

## 2. Per-SKU parts roll-up (100q, verified where the subsystem files say so)

| Block | NET-B | NET-MC | NET-MCX* | AIR-B | AIR-MC | AIR-MCX* |
|---|---|---|---|---|---|---|
| A — compute core (no DDR; MIC22705 swap +$1.5; 256 Mb flash +$1.1) | $153–198 | $153–198 | $153–198 | $148–189 | $148–189 | $148–189 |
| A-opt — DDR block (firmware confirm) | +$7–11 | | | | | |
| Storage — eMMC (REQ-108/109) | $5–9 (8 GB) | $5–9 | $5–9 | $9–16 (32 GB) | $9–16 | $9–16 (–64 GB) |
| B — uplink ×N (verified $16.78 ea) | $16.8 | $33.6 | $33.6 | — | — | — |
| C — module IF + base + sec-I/O (verified $14.14) + ADC row (~$1.2) | $15.3 | $15.3 | $15.3 | $15.3 | $15.3 | $15.3 |
| D — power (verified ≈$9.0) | $9.0 | $9.0 | $9.0 | $9.0 | $9.0 | $9.0 |
| F — watchdog block (survey 9: S32K3-class + XO + LDO + optional TPS3813) | — | $8–17 | $8–17 | — | $8–17 | $8–17 |
| G — voting pair (2nd A-block + sync: PCIe/NTB passives + 2× TJA1051T/3) | — | — | +$155–200 | — | — | +$150–193 |
| T1 module data plane (§5: 2× LAN9370 + port front-ends − RS-485 bank) | +$14–24 | +$14–24 | +$14–24 | +$14–24 | +$14–24 | +$14–24 |
| Mis-plug port protection (§6a, survey 11) | +$5.6 | +$5.6 | +$5.6 | +$5.6 | +$5.6 | +$5.6 |
| **Parts total (no DDR)** | **≈ $219–278** | **≈ $244–313** | **≈ $399–513** | **≈ $201–259** | **≈ $210–277** | **≈ $360–470** |

_*MCX = with the voting-pair option fitted. NOT included above: PCB fab/assembly class
(6+ layer, 0.8 mm BGA — order $15–40/unit [unv]) and NRE (FIPS library license,
compliance labs, Libero ops). Product pricing is value-based per D-ENT-3 — cost floors._

## 3. Stock-risk register (re-check at RFQ; all flagged by the subsystem passes)

| Part | Risk | Second source / action |
|---|---|---|
| MPFS095TS-1FCVG484I | Quote-gated, 18-wk lead | RFQ early; pin-compatible 025T/160T ladder is the schedule hedge |
| TPS25940LRVCR | 55/26 pcs at DigiKey/LCSC; not JLC-native | Lead-time check ahead of D-ENT-3; TPS25940A sibling |
| VSC8662 | **NRND — designed out** (BOM-B) | DP83869HM promoted primary |
| JXD1-0001NL MagJack | 400 pcs DigiKey | Halo HFJ11-1G01E-L12RL (deep stock, at the 1500 Vrms floor) |
| KH-PCB-6P6C RJ-11 | ~150 pcs LCSC | KH-9801/KH-9752 siblings; On-Shore PJ006 |
| CL10A225KO8NNNC (SS cap) | 0 stock LCSC (platform-wide part) | Any 2.2 µF/0603/X5R ≥10 V equivalent |
| AX3DAF1-125.0000T3 | Out of stock | **Resolved by reconciliation** — DSC1123BL5 primary |
| TPS7A20 1.0/1.05/2.5 V codes | Existence real, stock unconfirmed | Confirm at RFQ; TPS7A21 adjustable fallback |
| MT53E LPDDR4 | Thin-to-zero everywhere (DRAM market) | Only matters if DDR fitted; re-verify at firmware decision |

## 4. Phantom/corrected parts caught by this pass (why the detail level pays)

TPS62911, TPS62138, ISL8021/80212/80213, LP5907MFX-ADJ, W25Q128JVSSIQ/SNIQ,
RClamp0524P (obsolete → PA), MAX6369 (EOL), MPM3833C-AEC (doesn't exist),
VSC8662 (NRND per Microchip's own schematic), MP2315GJ-Z (NRND → -P/S-P),
25 MHz-crystal assumption on VSC8662 (it wanted 125 MHz — moot), LP5907-for-VDDA
(1.2 V floor — physically impossible), ESP32 BOOT-strap pattern (doesn't exist on
PolarFire), VTT-for-LPDDR4 (not required — on-die termination).

## 5. RESOLVED — survey 10 (100BASE-T1 module link) — subsystem C restructure

| Change | Rows | Cost |
|---|---|---|
| ADD: 2× **LAN9370-I/KCX** (4-port T1 switch, integrated PHYs + 802.1AS/1588v2 HW timestamping) → 2 fabric RGMII/MII bridge MACs (~5% LE) | hub | $14.42 |
| ADD: 8× OPEN-Alliance CMC (TDK ACT1210L-201-2P) + 8× PESD2ETH100-T + AC-coupling | hub | $4.6–14.7 |
| REMOVE: BOM-C §3 RS-485 receiver bank (8× THVD1450 + term/bias) — **RS-485 compat DROPPED** (survey 10 rec, owner-review tag; consumer Pro streaming goes dark on ENT ports per the §8 pattern, CAN unaffected) | hub | −$4.93 |
| **Net hub delta from the T1 ruling** | | **≈ +$14–24** |
| Module side (per streaming module): DP83TC814S-Q1 ($2.39; TJA1103 $1.49+1588 NDA-flagged alt) + CMC + ESD + coupling | module sheets | +$3.0–4.2/module |
| Module MCU: **ESP32-P4 uniformly** (reuses the 12VHPWR Pro reference design; STM32H563 fallback) | module sheets | tracked there |

Add the net T1 delta to every SKU column in §2 (+$14–24; AIR included — module ports exist
on both postures). Sync accuracy = design target (802.1AS <1 µs class, HW timestamps at
every stage), bench-verified before REQ-106 is claimed as met.

## 6a. RESOLVED — survey 11 (mis-plug fail-safe, 4th ruling) — port protection rows

Hub side (×8 ports, ≈ **+$5.6/hub**, all SKUs): SS110 series Schottky on each pin-1 VCC
(100 V — SS16's 60 V is too thin over 57 V) + SMAJ58A tail-risk TVS + DETECT series R
(~10 k 1206; §2.3 code table recomputes, stays monotonic, firmware-recalibrated) + pin-7
network + the T1-pair network (CMC $0.376 + ≥100 V coupling caps [the DC-blocking element]
+ PESD2ETH100 low-C TVS). Module side: **TPS26621DRCT 60 V auto-retry eFuse** ahead of the
LDO ($2.07 — a diode cannot protect a power INPUT; auto-retry satisfies self-recovery) +
DETECT/pin-7 + T1 network ⇒ ≈ +$2.7/streaming module, +$2.15/24-pin. Confirmed:
TJA1051T/3 = ±58 V CONTINUOUS DC (datasheet; beware the TJA1050's lower rating in
secondary sources). Compliant PSEs likely never energize our ports (signature reject) —
corroborating only; passive injectors remain the binding case. Injection-test procedure
(both polarities, 60-min sustained, 5–10× repeat, unattended-recovery pass criteria) =
survey 11 §h, run combined with the REQ-MOD-031 fault-injection program.
**Pin-7 reconciliation (survey predates the 5th ruling):** pin 7 is now the SYNC/FREEZE
driven line — replace the bleed-R treatment with series R + LOW-CAPACITANCE clamp sized so
the ≤100 ns sync edge survives the protection network (schematic-capture task).

## 6. Open items consolidated (beyond the subsystem files' own lists)

1. Power Estimator run (Microchip tool) — the one number gating the core-buck final pick
   and the MAIN_5V ILIM value (BOM-D's resistor-swap dependency chain).
2. MC-Max FULL-posture draw → MAIN eFuse ILIM 24.9k→20k swap + cascade ILIM bump (BOM-D).
3. SPI-boot strap polarity (BOM-A open item 5 — "getting this backward affects whether
   the board boots"): confirm at schematic capture against DS60001681H Fig 1-7.
4. SGMII AC-coupling board-side: subsystem A/B seam — resolve at schematic capture.
5. DDR vs LIM-only: firmware decision; the DDR block is population-separable.
6. eMMC exact MPN + the FBGA-153 single-land density family: RFQ pass.
7. Watchdog exact non-lockstep S32K31x sibling MPN + price: RFQ (survey 9 priced the
   S32K344 ceiling).
