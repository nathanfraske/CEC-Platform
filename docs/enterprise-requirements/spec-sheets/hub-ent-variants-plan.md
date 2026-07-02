# ENT hub — board plan, both variants (working baseline)

_Status: DRAFT pre-design plan (2026-07-02). One PCB design carries all six SKUs
(REQ-HUB-COMMON-105); ENT-NET vs ENT-AIR differ by POPULATION, never by layout. Companion:
`hub-ent-spec-sheet.md` (spec + subsystem BOM) and `hub-ent-bom-detailed.md` (assembling
from the subsystem BOM passes + survey 9)._

## 1. Block architecture

```
                          ┌────────────────────────────────────────────────┐
 MAIN_5V ──[eFuse]──┐     │  PolarFire SoC MPFS095TS (FCVG484)             │
 5VSB    ──[eFuse]──┼─[TPS2121 ×2 cascade]─→ +5V_SYS ─→ rails             │
 EXT(rear)─[eFuse]──┘          │                 │      ┌─ MSS RISC-V ×5   │
                            [hold-up]         [3V3 buck]│   (Zephyr)       │
                                                        │┌─ fabric: data    │
 8× RJ-45 module ports ── CAN (TJA1051T/3, split term) ─┤│  plane, voter    │
   │  DETECT ×8 ─ resistor ladders → ADC/GPIO           ││  (MCX), timestmp │
   │  RS-485 ×8 ─ receivers ─────────────→ fabric/UART ─┘│                  │
   └─ 5VSB per-port VCC                                  │ eNVM+QSPI: A/B FW│
                                                         │ + tamper log     │
 NET only: MSS-SGMII ─→ GbE PHY ─→ MagJack ─→ [uplink 1]│ PUF/Athena/IDevID│
           (MC+: 2nd PHY port → [uplink 2])              └───────┬──────────┘
 USB (device) ── provisioning/local                              │
 RJ-11 security I/O ── loop-in (EOL) / dry-contact-out ── always-on domain
 NanoKVM aux (JST-PH 5p) ── UART + shared 5V (NET-populated; AIR header-only)
 MC+:  independent WATCHDOG (own clock + supervised rail) ── liveness/force-STANDBY
 MCX:  2nd MPFS095TS + sync link + voted-output boundary (arbiter w/ watchdog)
```

## 2. Power tree (two postures, one tree)

- Sources: MAIN_5V (primary) / 5VSB / EXT — each behind a TPS25940-class eFuse
  (PG/FLT/EN) → TPS2121 cascade → **+5V_SYS**.
- +5V_SYS → (a) 3V3 buck ≥1A (RJ-45 domain, CAN, RS-485, LEDs, aux); (b) the PolarFire
  regulator set (1.0/1.05 core, 1.8/2.5 banks, quiet VDDA LDOs, SGMII rails — BOM-A);
  (c) PHY rails (BOM-B, NET only); (d) watchdog supervised rail (MC+); (e) 2nd-SoC set
  (MCX).
- **STANDBY posture** = 5VSB/EXT only: firmware gates the fabric/PHY/second-SoC loads;
  guaranteed loads = MSS monitor core class + QSPI persist path + tamper capture + RJ-11
  alarm drive. Hold-up: 2× 4700 µF + 470 µF bulk ahead of the persist path.
- Rail-sense: per-source dividers to ADC-capable inputs (fail-detected monitoring).

## 3. IO / bank budget (coarse, FCVG484)

| Domain | Signals | Bank class |
|---|---|---|
| CAN | TXD/RXD + STB | 3.3 V MSS/fabric GPIO |
| DETECT ×8 | 8 analog-capable inputs (µPolarFire has no native ADC — **plan row: external ADC or comparator ladder for DETECT**; the platform's ESP32 ADC trick does not carry over. Working baseline: one 8–12 ch SPI ADC, added to BOM-C open items) | 3.3 V |
| RS-485 ×8 | 8 RX (+DE if ever TX) → fabric UARTs | 3.3 V |
| SGMII | 1 lane (MSS) + PHY MDIO/MDC, ×2 ports via dual-port PHY | SERDES/3.3 V |
| USB | MSS USB 2.0 OTG | dedicated |
| QSPI, JTAG, straps | MSS | 1.8/3.3 V |
| RJ-11 | loop sense (comparator/ADC input) + relay drive | 3.3 V |
| Watchdog | heartbeat out, health UART/I2C, FORCE_STANDBY in (from WD), WD_ALIVE | 3.3 V |
| MCX pair | sync link (SGMII lane 2 or LVDS fabric pair) + cross-heartbeats | fabric |

**Newly-surfaced plan item (real):** the PolarFire has no on-die ADC-per-GPIO like the
ESP32 hubs — DETECT's analog read and the rail-sense dividers need an external ADC row
(SPI, 10+ ch) or a comparator-ladder redesign. Carried as an open row to the detailed BOM.

## 4. Edge / connector map (working)

- **Front edge**: 8× RJ-45 module ports in two ganged groups of 4 (SK6812 chain between).
- **Rear edge**: uplink MagJack(s) ×1–2 (NET; blue bezel + silkscreen per REQ/survey 2),
  RJ-11 security I/O (distinct color, labeled — never adjacent to module ports), USB-C,
  EXT feed connector, MAIN_5V + 5VSB JST inputs (board-internal side acceptable).
- **Interior**: NanoKVM aux JST-PH; JTAG; BOOT-mode strap header; M3 ×4 chassis-grounded.
- AIR population: uplink area unpopulated (visible bare land = the inspection story),
  RJ-11 populated.

## 5. Stackup / fab class

6-layer 1.6 mm baseline: L1 sig/BGA fanout, L2 GND, L3 pwr (core rails), L4 pwr/sig,
L5 GND, L6 sig. Controlled impedance for SGMII (100 Ω diff) + USB (90 Ω). 0.8 mm BGA
via-in-pad/filled as needed under FCVG484. ENIG. A step above every existing platform
board — new fab class (already flagged in the spec sheet cost notes).

## 6. Population plan per SKU (delta from full-fit)

| Subsystem | NET-B | NET-MC | NET-MCX | AIR-B | AIR-MC | AIR-MCX |
|---|---|---|---|---|---|---|
| Uplink PHY+jack #1 | ✔ | ✔ | ✔ | — | — | — |
| Uplink port #2 (dual-PHY 2nd MagJack) | — | ✔ | ✔ | — | — | — |
| Watchdog block | — | ✔ | ✔ | — | ✔ | ✔ |
| 2nd SoC + rails + sync | — | — | ✔(opt) | — | — | ✔(opt) |
| RJ-11 loop I/O | opt | opt | opt | ✔ | ✔ | ✔ |
| NanoKVM aux (header) | ✔ | ✔ | ✔ | header only | header only | header only |
| eFuse fronts ×3 / hold-up / 3V3 | ✔ all SKUs | | | | | |
| eMMC density (one FBGA-153 land) | 8 GB | 8 GB | 8 GB | 32 GB | 32 GB | 32–64 GB |

## 7. MC / MC-Max growth notes

- Watchdog block (survey 9): S32K3-class MCU (owner gate) + own XO + own PG-monitored LDO
  off the arbitrated 5VSB rail + optional TPS3813 backstop; force lines = soft reset first,
  then the MAIN_5V eFuse EN (hard force-STANDBY); placed at the SoC reset/strap corner.
- MCX second SoC: mirrored placement across the sync links — PCIe/NTB lane (checkpointed
  state mirror; NTB support = firmware confirm) + a private 3-node CAN segment (2×
  TJA1051T/3; SoC-A/SoC-B/watchdog) for heartbeat/arbitration; FULL companion duplication
  (no shared flash/DDR); voted boundary = tamper-log writes + Appendix-D actuation only,
  northbound/CAN active-standby (survey 9 §2.3).
- Common-mode honesty: identical firmware defeats voting for software faults — mitigation
  = diversity-staged rollout (N / N-1 canary across the pair, survey 9 §5), stated as a
  mitigation, never a fix; dissimilar-redundancy is NOT claimed. A compromised signing key
  hitting both members is explicitly out of scope (key-custody item, D-ENT-5).

## 8. Open plan rows

1. DETECT/rail-sense external ADC (new — PolarFire has no ESP32-style ADC) → detailed BOM.
2. Watchdog part-class = owner gate (S32K3 rec); arbiter = the watchdog (settled, survey 9).
3. RS-485 receiver topology (×8 point-to-point baseline) → OQ-5.
4. DDR fitted vs LIM-only → firmware confirm (affects stackup margin).
5. Port count 8 (Pro-base) → confirm at program start.
6. Mezzanine (OQ-77) interaction with the ENT board — not planned into rev 1.
