# ENT Hub — specification sheet + engineering BOM (working baseline)

_Status: DRAFT, pre-design engineering baseline (2026-07-02). Authority: the requirement
registers (`../hub-enterprise-requirements.md`, 103 REQs) + the v1.2.0 spec-revision draft
§13 + owner rulings 2026-07-01/02. All prices are 100-qty estimates dated 2026-07-02 from
the Phase-2 surveys — directional, `[RFQ]` = re-quote before D-ENT-3 lock, `[unv]` =
unverified. This is a COST-FLOOR parts view; product pricing is value-based per D-ENT-3
and is NOT derived from these numbers. The sourced KiCad BOM supersedes this file once the
board program starts._

## 1. SKU matrix

One board design; SKUs differ by population + firmware policy (REQ-HUB-COMMON-105:
externally identifiable). Posture × availability:

| SKU | Uplink PHY(s) | Network populated | Watchdog | Voting pair | Redundancy pack | RJ-11 sec-I/O | NanoKVM aux |
|---|---|---|---|---|---|---|---|
| ENT-NET-B (base) | 1× 1000BASE-T | Yes | — | — | option | on request | populated |
| ENT-NET-MC | 2× 1000BASE-T | Yes | Yes | — | standard | on request | populated |
| ENT-NET-MCX | 2× 1000BASE-T | Yes | Yes | Yes | standard | on request | populated |
| ENT-AIR-B (base) | — | **No PHY populated** | — | — | option | **populated** | header only (no KVM) |
| ENT-AIR-MC | — | No PHY populated | Yes | — | standard | populated | header only |
| ENT-AIR-MCX | — | No PHY populated | Yes | Yes | standard | populated | header only |

## 2. Specifications

| Domain | Specification | Trace |
|---|---|---|
| Compute | Microchip **PolarFire SoC — production baseline MPFS095TC (Core line)**, FCVG484 (19×19, 0.8 mm), industrial preferred (095TC-FCVG484I PCN'd; E-grade for prototypes); 4× RV64GC + 1× RV64IMAC @ 667 MHz, 2 MB L2 (LIM-capable), 93K LE-class fabric, 128 KB eNVM; **part-agnostic SerDes-free land** — one board accepts 025/095/160/250 × T/TS/TC (7th ruling; conditional on the Core security-block FAE confirms) | REQ-001; owner ruling 2026-07-02 (7th); survey 1 |
| Security silicon | Baseline (all SKUs): PUF key store, secure boot, anti-tamper responses (Core-line retention = the REQ-001 FAE-confirm condition); IDevID (802.1AR-class) provisioned at manufacture; runtime crypto = wolfCrypt validated module. **HS population option: MPFS095TS fitted (Athena TeraFire, DPA-resistant crypto)** — same land, orderable for high-assurance/defense channels | REQ-001/003/097; owner ruling 2026-07-02 (7th) |
| Boot/update | System Controller + HSS (high-ceremony) → MCUboot/wolfBoot-class A/B with monotonic anti-rollback (routine OTA / offline signed bundles) | REQ-010..013; survey 6 |
| Firmware | Zephyr RTOS (in-tree PolarFire), no Linux; wolfCrypt-class crypto (FIPS = embeds-validated-module posture); `west spdx` SBOM per release | REQ-002/014/097; survey 6 |
| Storage | Two-tier: QSPI NOR 32 MB class (W25Q256JV-class; A/B firmware + rollback-resistant tamper log) + **eMMC 5.1 on one FBGA-153 land, density per SKU — NET: 8 GB (≥72 h store-and-forward, ~5 days at 1.4 GB/day); AIR: 32 GB baseline / 64 GB option (≥30-day local retention + ≥1k event captures)**; bulk store encrypted at rest (PolarFire-rooted keys) + signed segment chain; external DDR **TBD** (LIM may suffice) | REQ-062/070/107..109; survey 1/4 |
| Module interface | **8× RJ-45 FTP** (Kinghelm KH-RJ45-58 class), locked pin table; classical CAN 500k shared bus, 120 Ω split termination; DETECT per §2.3 + PESD per port; 100BASE-T1 streaming/sync serviced per port via 2× LAN9370 switches (supersedes RS-485, REQ-043); 5VSB per-port distribution. _Port count = Pro-base working baseline; confirm at board program._ | REQ-040..045 |
| Uplink (NET) | Standard IEEE 802.3 **1000BASE-T**: MSS-SGMII → **DP83869HM** PHY (PRIMARY — BOM-B verified: VSC8662 is NRND per Microchip's own Icicle schematic, ~50 pcs stock; MC dual-uplink = full per-uplink duplication, 2 discrete PHYs/SGMII lanes), Pulse JXD1-0001NL MagJack (2250 VDC isolation, integrated Bob-Smith + LEDs), RClamp0524PA TVS + Bourns 2038-class GDT (office grade); visually distinct from module ports. SFP studied-deferred. 1000BASE-T1 factory option only. | REQ-030/031; survey 2; BOM-B |
| Local interfaces | USB (sensing/provisioning on NET; primary local on AIR); NanoKVM aux header (5-pin JST-PH); RJ-11 **security I/O**: supervised tamper-loop in + isolated dry-contact alarm out, protocol-free | REQ-032/033/059 |
| Northbound (NET) | Redfish-aligned REST subset + OpenMetrics + syslog-TLS; RBAC (viewer/operator/admin) + config audit log; SNMPv3 deferred/commercial | REQ-020..023 |
| Power | 3-source priority-OR: **MAIN_5V (primary) > 5VSB > external rear-bracket feed (mandatory)**; per-source TPS25940-class eFuse fronts (PG/FLT, EN self-test, reverse block) → TPS2121 cascade; postures: **FULL** (MAIN_5V; est. 5–15 W all-in `[unv — Power Estimator run needed]`) / **STANDBY** (5VSB budget; telemetry+log+tamper guaranteed); persist-on-fault flush from ≥2× 4700 µF hold-up (supercap escalation gated on OQ-56 bench) | REQ-026/052/060..062; surveys 1/4 |
| Availability ladder | MC: + independent compute watchdog (own clock/supervised rail, force-STANDBY + log + alarm; part per OQ-79/survey 9) + redundancy pack (dual uplink, monitored sources). MC-Max: + fail-functional **voting pair** (2nd MPFS095TS, voted outputs, watchdog-arbitrated, bumpless; hub compute plane only) | REQ-050/051/057/103..105 |
| Tamper/log | Rollback-resistant event log (monotonic counter), survives power-off/unplug, standby capture, SIEM-forwardable (NET) / local surface (AIR) | REQ-070..073 |
| Compliance | EMC EN 55032/35-class + IEC 62368-1 per revision; IEC 62443-4-2 SL-2 (EDR) designed-to; CRA = EU-entry-conditional; federal-channel artifacts on demand | REQ-094..099/102 |
| Mechanical/PCB | 6+ layer controlled-impedance, 0.8 mm BGA class (a step up from the platform's 4-layer boards); M3 chassis-grounded mounts; SKU labeling per REQ-105 | survey 1 |

## 3. Engineering BOM (working baseline, by subsystem)

Population key: **all** / NET / MC+ (MC and MC-Max) / MCX (MC-Max only) / opt.

### A. Compute core (all SKUs)

| Qty | Part (working baseline) | Function | Unit [est] | Trace |
|---|---|---|---|---|
| 1 | **MPFS095TC-FCVG484I** (production baseline, 7th ruling; E-grade $119 measured for prototypes) — HS option: MPFS095TS-1FCVG484I fitted instead ($125–140 `[RFQ]`, factory-direct) | SoC (compute+fabric+security) | $110–130 `[RFQ]` | REQ-001; owner ruling 2026-07-02 (7th); master BOM §3a |
| 1 | QSPI NOR 256 Mb W25Q256JV-class (SOIC-16 FIQ $3.00 or WSON-8 EIQ $3.21, LCSC-verified) | A/B firmware + tamper-log region | $3.0–3.2 | BOM-A child (verified); survey 1/6 |
| 1 | eMMC 5.1, FBGA-153 one-land: 8 GB (NET) / 32–64 GB (AIR) industrial | bulk telemetry store (encrypted, signed segments) | 8 GB ~$5–9 / 32 GB ~$9–16 `[unv, RFQ]` | REQ-107..109 |
| 0–1 | LPDDR4/DDR4, modest density | working RAM — **TBD** (LIM may suffice) | $3–8 if fitted | survey 1 |
| 3–5 | Regulators (VDD 1.0/1.05 V, quiet-LDO VDDA, VDDI/AUX banks; Renesas/MPS ref designs) + sequencing | PolarFire rails | $8–20 set | survey 1 |
| 1–2 | Reference oscillators | PLL/DLL clocking | $1–3 | survey 1 |
| — | BGA decoupling field + JTAG header | — | $3–8 | survey 1 |
| **Subtotal** | | | **≈ $145–180** (no DDR) | |

### B. Uplink (NET SKUs; ×2 on MC+)

| Qty | Part | Function | Unit [est] | Trace |
|---|---|---|---|---|
| 1 | **DP83869HMRGZR** (PRIMARY; VSC8662 NRND — BOM-B verified) | SGMII GbE PHY | $7.98 (verified 100q) | BOM-B |
| 1–2 | Pulse JXD1-0001NL MagJack (2250 VDC; Halo HFJ11-1G01E 2nd source) | magnetics + jack | $5.95 (verified 100q) | BOM-B |
| — | 2× RClamp0524PA + Bourns 2038-15-SM GDT + LDOs/crystal/passives | ESD/surge + PHY support | $2.9 (verified) | BOM-B |
| **Subtotal** | | | **≈ $16.8 per uplink VERIFIED** (2nd uplink on MC+: +$16.8 — full duplication, no dual-port sharing) | |
| — | _ENT-AIR: subsystem NOT populated (inspection-verifiable absence)_ | | −$6–14 | REQ-024 |

### C. Module interface (all SKUs; 8-port baseline)

| Qty | Part | Function | Unit [est] | Trace |
|---|---|---|---|---|
| 8 | RJ-45 FTP Kinghelm KH-RJ45-58-8P8C (C2683360) | module ports, SH→GND | ~$0.6 ea | platform lock §2.1 |
| 1 | TJA1051T/3 (C38695) | CAN transceiver, shared bus | $0.40 | platform lock §3.1 |
| — | 120 Ω split termination (60.4×2 + 4n7) | CAN term at hub | $0.05 | §3.1 |
| 8 | PESD5V0S1BA (C5261083) | DETECT pin-8 ESD, per port | $0.03 ea | §2.4 lock |
| 2 | LAN9370 4-port 100BASE-T1 switches + port front-ends (SUPERSEDES the RS-485 receiver bank — survey 10, T1-only REQ-043; detailed rows in bom-b/master §5) | module streaming/sync data plane, every ENT family per the 6th ruling | net +$14–24/hub vs the RS-485 bank | REQ-043; survey 10 |
| — | DETECT pull-up networks, 5VSB per-port distribution, port LEDs/SK6812 chain (platform base) | — | $2–4 | §2.5 |
| **Subtotal** | | | **≈ $9–10 base** (module IF + platform base + sec-I/O, reconciled to bom-c's corrected ≈$9.21 verified total, RS-485 bank excluded) **+ T1 data plane priced separately at +$19–29 gross** (master BOM §5 — kept as its own line, not folded into this subtotal; the earlier "$30–46 incl. T1" framing double-counted against the master's T1 row and against the master's now-corrected C row, and is superseded) | |

### D. Power subsystem (ALL SKUs — the eFuse-fronted 3-source path is platform-common per REQ-060, NOT part of the optional MC redundancy pack)

| Qty | Part | Function | Unit [est] | Trace |
|---|---|---|---|---|
| 2 | TPS2121RUXR (C485916) | priority cascade | $0.65 ea (LCSC) | survey 4; as-built §2.9 |
| 3 | TPS25940LRVCR | per-source eFuse front (PG/FLT/EN) | $1.71 ea | survey 4 |
| 3 sets | eFuse support passives | ILIM/UVLO dividers, pull-ups | $0.35/set | survey 4 |
| 2 | 4700 µF 16 V (VKMI2101C472MV, Samxon, LCSC C487318 — reuses the exact part already shipping on Hub Standard C1; EEVFK1C472M priced alternate, not populated, ~35–70% costlier for no electrical delta, per bom-d §3) | hold-up (persist-on-fault) | ~$0.73 ea | survey 4; OQ-56; bom-d §3 |
| 3 | Input connectors (JST-XH class: MAIN_5V, 5VSB, rear-bracket ext feed) | 3 sources | $0.3–0.5 ea | REQ-052; OQ-54 |
| — | Hub logic rails (3V3/1V8 bucks/LDOs, distinct from A's PolarFire set) | — | $2–4 | — |
| opt | LTC4417IGN (alternative single-chip prioritizer, +3 PFETs) | owner-selectable swap | +$8–9 net | survey 4 |
| **Subtotal** | | | **≈ $10–14** | |

### E. Security I/O + local interfaces (all)

| Qty | Part | Function | Unit [est] | Trace |
|---|---|---|---|---|
| 1 | RJ-11 6P6C jack | security I/O port | $0.3–0.5 | REQ-033; survey 3 |
| 1 | Opto-MOSFET or reed relay + EOL sense network + PESD | isolated dry-contact out + supervised loop in | $0.8–1.8 | survey 3 |
| 1 | USB-C front end (USBLC6-2SC6 + CC network; platform base) | host/local USB | $0.5–1 | §4 base |
| 1 | 5-pin JST-PH S5B-PH-K-S (C157923) | NanoKVM aux header | $0.15 | §2.9/OQ-51 |
| **Subtotal** | | | **≈ $2–3.5** | |

### F. MC additions (MC + MC-Max)

| Qty | Part | Function | Unit [est] | Trace |
|---|---|---|---|---|
| 1 | **Independent compute watchdog — small safety MCU** (survey 9 rec: NXP S32K3-class non-lockstep, Zephyr-native — S32K344 ceiling $12.30; STM32G431 budget option ~$4.2; Hercules TMS570LS0432 $8.24 / AURIX TC222L $9.53 alternatives; part-class = owner gate) | liveness challenge-response, health watch, two-tier force-STANDBY, log+alarm | $4–12.3 `[OQ-79 owner gate]` | REQ-103; survey 9 |
| 1 | Watchdog independence set: own crystal/XO + own PG-monitored LDO + isolating buffers on force lines | independence guarantee | $2–3 | REQ-103; survey 9 |
| 1 | TPS3813K33 backstop supervisor (watches the watchdog) — optional | layered defense | $1.51 (+$0.5 support) | survey 9 §1.4 |
| 1 | 2nd uplink PHY+MagJack+protection set (NET only) | dual uplink | $6–9 | REQ-057 |
| **Subtotal** | | | **≈ $8–27** | |

### G. MC-Max additions

| Qty | Part | Function | Unit [est] | Trace |
|---|---|---|---|---|
| 1 | 2nd MPFS095TS + FULL companion duplication (own flash, own rails, own clocking — no shared boot/working memory between members, by rule) | voting-pair member | $150–190 `[RFQ]` | REQ-104; survey 9 §2.2 |
| — | Inter-SoC PCIe/NTB sync link (AC caps + routing; NTB support = firmware confirm, fallback raw SERDES P2P) | checkpointed state mirror | $1–3 | survey 9 §2.2 |
| 2 | TJA1051T/3 (private 3-node arbitration CAN: SoC-A + SoC-B + watchdog; separate from module bus) | heartbeat/arbitration, diverse from PCIe link | $0.40 ea | survey 9 §2.2 |
| **Subtotal** | | | **≈ $152–195** (+ unpriced PCB-class step-up: 2× BGA + doubled controlled-impedance routing) | |

### Roll-up (parts only, 100q, working baseline — NOT product pricing)

_Re-summed 2026-07-02 against the corrected C/T1/mis-plug accounting (F04/F11/F12/F13):
subsystem C is now the $9–10 base + the T1 data plane priced separately at +$19–29 gross
(not folded together), and the mis-plug row is the +$2.5–3 net-new hub-side portion (the
T1-pair network it used to re-enumerate is captured once, in the T1 row). These figures are
reconciled to `bom-detailed/hub-ent-bom-detailed.md` §2, which governs if the two ever
disagree again._

| SKU | Parts subtotal [est] |
|---|---|
| ENT-NET-B | ≈ **$214–274** |
| ENT-AIR-B | ≈ **$198–256** (no uplink) |
| ENT-NET-MC / ENT-AIR-MC | ≈ **$239–307** / **$206–273** |
| ENT-*-MCX | ≈ **$394–507** / **$356–466** (+ PCB-class step-up, unpriced) |

Plus, NOT in the parts rows: **PCB fab + assembly class jump** (6+ layer controlled
impedance, 0.8 mm BGA reflow/inspection) — order $15–40/unit at 100q `[unv, class
estimate]`; NRE (Libero seat/licensing ops, FIPS library license $7.5k+/SKU-class if
wolfSSL commercial, compliance lab invoices per survey 7 cost classes) sits in D-ENT-3
value pricing, not here.

## 4. Open rows (TBD register for this sheet)

1. Watchdog part-class OWNER GATE (survey 9 rec: S32K3 non-lockstep; alternatives Hercules/AURIX; exact non-lockstep S32K31x sibling MPN+price = RFQ) — OQ-79.
2. DDR fitted or LIM-only — firmware-team confirmation (survey 1).
3. ~~RS-485 receiver topology (OQ-5)~~ MOOT for the ENT hub — T1-only per survey 10 (2× LAN9370 switched, every port concurrent by construction); OQ-5 remains a consumer-Pro-hub question.
4. Port count (8 = Pro-base working baseline) — confirm at board program start.
5. Voter/arbiter = the watchdog (survey 9: fabric-resident arbiter rejected — shares the SoC die/rails, not independent); MSS PCIe NTB-mode support = firmware confirm.
6. Supercap escalation for hold-up — gated on the OQ-56 bench measurement.
7. RJ-11 isolation/surge sizing (stronger-than-internal-grade question) — survey 3 flag.
8. All `[RFQ]`/`[unv]` prices — formal distributor RFQ pass before D-ENT-3 lock.
