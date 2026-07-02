# Enterprise module requirements — COMMON register (all families)

_All sections DRAFT. Schema: `REQUIREMENTS-FORMAT.md`. Owner direction (plan §1a.4):
enterprise modules ARE made — requirements now, boards after ratification. Per-family
deltas live in `module-requirements-{24pin,eps,pcie,12vhpwr}.md`. NOTE: variant-specific
module hardware amends the LOCKED tier-agnostic principle — that amendment is a Phase-4
owner act; until then every row here is a proposal._

## 1. Link & platform conformance (locked carry-ins) — DRAFT

Enterprise modules stay on the universal interface — the enterprise-ness is in identity,
integrity, and build posture, not a new connector.

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-MOD-COMMON-001 | Module-to-Hub link SHALL be RJ-45 8P8C FTP per the locked pin table; classical CAN 500 k; no module-side CAN termination; DETECT resistor per the §2.3 code table; pin-8 ESD diode populated. | [LOCKED §2.1/§2.3/§2.4/§3.1] | I+T | — |
| REQ-MOD-COMMON-002 | An enterprise module SHALL function in ANY Hub (Standard through enterprise) with graceful degrade; enterprise-only features go dormant, never faulting the link. | [LOCKED §1/§8] | T | — |
| REQ-MOD-COMMON-003 | Enterprise streaming modules SHALL carry **100BASE-T1 single-pair Ethernet on pair 2 (pins 4/5)** — bidirectional, replacing the Pro-tier RS-485 for the ENT line (owner ruling 2026-07-02 3rd; RS-485 remains the consumer Pro tier) — with DETECT = the locked 10 kΩ CAN+100BASE-T1 class, and SHALL participate in the fleet sub-µs time synchronization (REQ-HUB-COMMON-106). MCU: **ESP32-P4 uniformly** across the RMII-needing streaming families (survey 10: RMII + hardware 1588/PTP timestamps + PPS confirmed in ESP-IDF; reuses the already-paid 12VHPWR Pro QFN-104 reference design instead of adding a third toolchain; STM32H563-class = documented price-competitive fallback ~$4.29–4.74; STM32G4 confirmed unable — no MAC-integrated 100BASE-T1 part exists). Module T1 front-end: DP83TC814S-Q1 default PHY ($2.39; TJA1103 $1.49 + 1588 is cheaper but NDA-flagged — clear with NXP first) + OPEN-Alliance CMC + AC coupling + PESD2ETH100 (~$3.0–4.2/module). Non-streaming enterprise builds (24-pin) stay CAN-only, pair 2 terminated per the locked table. | owner ruling 2026-07-02 (3rd); spec §2.3/§6.11; OQ-20 (ENT-resolved) | I+T | — |

## 2. Identity & provenance — DRAFT

The platform's module identity (DETECT class code + MAC) is a weak integrity anchor
(OQ-44). For a tamper-mandated fleet, per-module identity is the asset-integrity primitive.

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-MOD-COMMON-010 | Each enterprise module SHALL carry a per-unit cryptographically verifiable identity via an MCU-resident device key exercised by Hub challenge-response over CAN and/or the T1 link — NO new identity hardware (owner ruling 2026-07-02 5th: the 1-Wire ID/EEPROM path is OUT, replaced by the poke-and-ack topology + link-layer challenge; ≈$0 parts). The DETECT poke-and-ack tap SHALL serve as the physical-layer liveness/anti-spoof surface accompanying the cryptographic challenge. | owner ruling 2026-07-02 (5th); OQ-44/76 resolved-by-direction | I+T | — |
| REQ-MOD-COMMON-011 | Module identity SHALL bind into the Hub's attestation evidence so a module swap is a detectable, loggable event (component-swap detection at the platform's own granularity — complements TCG Platform-Certificate-style host attestation, does not replace it). | tamper §5; OQ-44 | T | — |
| REQ-MOD-COMMON-012 | Enterprise module firmware SHALL be signed with the same custody/anti-rollback discipline as the Hub (REQ-HUB-COMMON-010/011). | audit §2 | T | — |
| REQ-MOD-COMMON-013 | PROPOSED (owner exploration 2026-07-02, adopt/decline pending — pairs REQ-HUB-COMMON-114): ENT modules SHALL implement the **pin-7 heartbeat responder**: edge capture + open-drain drive on pin 7; the response is a hardware-timed edge/pulse pattern derived from the module device key + the per-challenge nonce, by the signed-firmware-prescribed method. Implementation contract: the nonce rides CAN/T1 ahead of the timing window (compute-then-respond — crypto compute time never sits in the timed path); the response edge is scheduled by hardware timer compare (STM32G4 output-compare / ESP32-P4 timer+ETM class), so response determinism is a timer-peripheral property, not a firmware-loop property. Graceful degrade BOTH directions (locked §1/§8 preserved): on a Hub that never challenges (Standard/Pro/consumer), the responder stays dormant and the module functions normally; a legacy module (pin 7 NC) is never challenged — the REQ-HUB-COMMON-114 auto-untrust policy binds only to modules whose attested class claims pin-7 capability. ≈$0 parts (GPIO + existing timer peripheral). | owner exploration 2026-07-02; REQ-HUB-COMMON-114; REQ-MOD-COMMON-010/012 | T | D-ENT-5 |

## 3. Radio posture (ENT-AIR load-bearing question) — DRAFT

Every current module MCU (ESP32-S3/C6) is Wi-Fi/BLE-capable silicon. Air-gapped buyers
commonly prohibit RF-capable parts outright, even unused (plan §1a.5).

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-MOD-AIR-020 | ENT-AIR module builds SHALL use radio-free MCUs — option (a) RESOLVED by owner ruling 2026-07-02. Working baseline: STM32G4 family (G431-class for the digital/I2C families; G474-class for 12VHPWR-Std, evaluating on-die comparator absorption of the §6.13 TLV7011), with ESP32-P4 (radio-free, already the platform Pro MCU) for Pro-tier builds. The fused-off/antenna-absent ESP32 posture is STRUCK: no Wi-Fi-disable eFuse exists on S3/C6, no radio-absent SKU exists, and it fails inspection-without-powering (survey 8). | plan §1a.5; survey 8; owner ruling 2026-07-02 | I | — |
| REQ-MOD-AIR-021 | The radio-free build SHALL be externally verifiable without powering the unit (distinct MCU part marking + BOM/CPL + no antenna keepout region), mirroring REQ-HUB-AIR-101. | plan §1a.5; survey 8 | I | — |

## 4. Fail-passive interposer guarantee — DRAFT

Audit blocker #4, and it lands hardest on modules: they sit IN SERIES with 40–55 A DC
paths. This is the first question every mission-critical buyer asks.

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-MOD-COMMON-030 | An enterprise module SHALL be fail-passive with respect to the monitored power path: no single module fault (MCU dead, sensor shorted, firmware crash, link severed, 5VSB lost) may interrupt, degrade, or destabilize the pass-through power delivery. | audit §1.4 | A+T | — |
| REQ-MOD-COMMON-031 | Each family SHALL ship an FMEA/FMEDA covering the in-path elements (shunts, connectors, PCB copper) with fault-injection test evidence, plus the §6.6/§6.7 thermal/vertical-transition analyses at rated current. | audit §1.4; spec §6.6/§6.7; OQ-10/12 | A+T | OQ-10/11/12 |
| REQ-MOD-COMMON-032 | In-path connector/copper margins SHALL meet the platform thermal gates at the family's rated current with the production cooling model declared (the 12VHPWR precedent: TIM/case coupling stated, still-air bound published as the conservative number). | CLAUDE.md item 4 precedent | A+T | — |

## 5. Sensing tier & data integrity — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-MOD-COMMON-040 | Enterprise module sensing SHALL be offered at the Pro-class characterization tier (fast ADC, streamed over the 100BASE-T1 link per REQ-MOD-COMMON-003) as baseline, with the Max tier (spectral/FPGA) per family where §6.11/§6.13 defines it; Standard-tier detection front-ends (§6.13 binary transient flag) are the floor. | spec §6.11/§6.13; OQ-57..59 | I | OQ-57..59 |
| REQ-MOD-COMMON-041 | Telemetry SHALL carry per-sample integrity metadata sufficient for the Hub to detect gaps/tampering in the stream (sequence + timestamps; crypto binding evaluated in Phase 2). | tamper §2; audit §3 | T | — |
| REQ-MOD-COMMON-042 | The §6.10 acquisition model (continuous conversion, ~2 s pre-roll ring, ALERT freeze) SHALL be preserved on enterprise builds — the forensic pre-roll is a tamper-relevant feature, not just power QA. | spec §6.10 | T | — |
| REQ-MOD-COMMON-043 | Power-signature fingerprinting features (component-swap/implant screening on the measured rails) MAY be offered but SHALL be positioned as a screening tier only; documentation SHALL state the verified blind spot (dormant implants not exercised during profiling are invisible). | tamper §6 | I | D-ENT-5 |

## 6. Lifecycle & sourcing — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-MOD-COMMON-050 | Enterprise module families SHALL match the Hub lifecycle commitments (REQ-HUB-COMMON-091) including spares of in-path connectors and shunts. | audit §2 | I | D-ENT-3 |
| REQ-MOD-COMMON-051 | Shunt parts SHALL be locked (OQ-11 closes) before any enterprise module board starts — the register cannot carry TBD in-path parts into a tamper-audited product. | OQ-11; spec §6.4 | I | OQ-11 |
| REQ-MOD-COMMON-053 | Enterprise module RJ-45 jacks SHALL fail safe against the same mis-plug set as REQ-HUB-COMMON-110 (live switch cable / 57 V passive PoE, both modes and polarities): no hardware damage, self-recovering. Module-side exposure differs from the hub: pin 1 is the module's 5VSB INPUT — a series diode CANNOT protect it (fault current flows the normal direction; survey 11): an active ≥60 V OVP eFuse with AUTO-RETRY is required (TPS26621-class working baseline, $2.07); DETECT carries the module's code resistor (series element ahead of it — the §2.3 code table recomputes for the added series R, firmware-recalibrated); CAN pins covered by the TJA1051T/3 (±58 V CONTINUOUS DC, datasheet-confirmed). The 100BASE-T1 protection network (CMC + ≥100 V series coupling caps [the actual DC-blocking element] + low-C TVS) applies ONLY to streaming families carrying the REQ-003 PHY; the 24-pin's pair-2 termination needs voltage-tolerant passive treatment only. A resettable/auto-retry element satisfies self-recovery; a one-time fuse does not. Verified by injection test per family (survey 11 §h procedure). | owner ruling 2026-07-02 (4th); REQ-HUB-COMMON-110 | T | — |
| REQ-MOD-COMMON-052 | Each enterprise module family SHALL ship an SBOM per firmware release and be covered by the platform PSIRT/CVD process from the first enterprise release; on any EU market placement these become CRA-bound per REQ-HUB-COMMON-094 (modules are separately-marketed components with their own obligations). | survey 7; owner ruling 2026-07-02 | I | — |
