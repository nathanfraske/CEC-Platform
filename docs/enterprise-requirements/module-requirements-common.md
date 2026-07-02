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
| REQ-MOD-COMMON-003 | RS-485 streaming (pins 4/5) SHALL be populated on enterprise modules at the Pro sensing tier and above; Standard-tier enterprise builds terminate pair 2 module-side per the locked table. | [LOCKED pin table]; spec §3.2 | I+T | — |

## 2. Identity & provenance — DRAFT

The platform's module identity (DETECT class code + MAC) is a weak integrity anchor
(OQ-44). For a tamper-mandated fleet, per-module identity is the asset-integrity primitive.

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-MOD-COMMON-010 | Each enterprise module SHALL carry a per-unit unique, cryptographically verifiable identity readable by the Hub over the existing link (candidate mechanism: the §2.3 1-Wire ID/EEPROM upgrade path on pin 8 with pin 7 return — explicitly NOT adopted platform-wide; adopted HERE only if D-ENT-5 ratifies). | spec §2.3 upgrade path; OQ-44; audit §3 | I+T | D-ENT-5 |
| REQ-MOD-COMMON-011 | Module identity SHALL bind into the Hub's attestation evidence so a module swap is a detectable, loggable event (component-swap detection at the platform's own granularity — complements TCG Platform-Certificate-style host attestation, does not replace it). | tamper §5; OQ-44 | T | D-ENT-5 |
| REQ-MOD-COMMON-012 | Enterprise module firmware SHALL be signed with the same custody/anti-rollback discipline as the Hub (REQ-HUB-COMMON-010/011). | audit §2 | T | — |

## 3. Radio posture (ENT-AIR load-bearing question) — DRAFT

Every current module MCU (ESP32-S3/C6) is Wi-Fi/BLE-capable silicon. Air-gapped buyers
commonly prohibit RF-capable parts outright, even unused (plan §1a.5).

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-MOD-AIR-020 | ENT-AIR module builds SHALL satisfy the ratified radio posture: either (a) radio-free MCU (Phase-2 research item 8 survey) or (b) documented fused-off/antenna-absent ESP32 posture IF the target-buyer evidence shows it is acceptable. This row cannot leave DRAFT until D-ENT-5 picks (a)/(b). | plan §1a.5; Phase 2.8 | I | D-ENT-5 |
| REQ-MOD-AIR-021 | Whatever posture is ratified, the module SHALL make it externally verifiable (marking + BOM + inspection doc), mirroring REQ-HUB-AIR-101. | plan §1a.5 | I | D-ENT-5 |

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
| REQ-MOD-COMMON-040 | Enterprise module sensing SHALL be offered at the Pro tier (characterization: fast ADC + RS-485 streaming) as baseline, with the Max tier (spectral/FPGA) per family where §6.11/§6.13 defines it; Standard-tier detection front-ends (§6.13 binary transient flag) are the floor. | spec §6.11/§6.13; OQ-57..59 | I | OQ-57..59 |
| REQ-MOD-COMMON-041 | Telemetry SHALL carry per-sample integrity metadata sufficient for the Hub to detect gaps/tampering in the stream (sequence + timestamps; crypto binding evaluated in Phase 2). | tamper §2; audit §3 | T | — |
| REQ-MOD-COMMON-042 | The §6.10 acquisition model (continuous conversion, ~2 s pre-roll ring, ALERT freeze) SHALL be preserved on enterprise builds — the forensic pre-roll is a tamper-relevant feature, not just power QA. | spec §6.10 | T | — |
| REQ-MOD-COMMON-043 | Power-signature fingerprinting features (component-swap/implant screening on the measured rails) MAY be offered but SHALL be positioned as a screening tier only; documentation SHALL state the verified blind spot (dormant implants not exercised during profiling are invisible). | tamper §6 | I | D-ENT-5 |

## 6. Lifecycle & sourcing — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-MOD-COMMON-050 | Enterprise module families SHALL match the Hub lifecycle commitments (REQ-HUB-COMMON-091) including spares of in-path connectors and shunts. | audit §2 | I | D-ENT-3 |
| REQ-MOD-COMMON-051 | Shunt parts SHALL be locked (OQ-11 closes) before any enterprise module board starts — the register cannot carry TBD in-path parts into a tamper-audited product. | OQ-11; spec §6.4 | I | OQ-11 |
