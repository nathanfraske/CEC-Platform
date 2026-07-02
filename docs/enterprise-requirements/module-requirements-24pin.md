# Enterprise module requirements — 24-pin ATX family (deltas)

_All sections DRAFT. Inherits `module-requirements-common.md`. Baseline hardware = the
rev3 respin (ESP32-C6 + §6.13 front-end + TPS2121 +5V_SYS mux + mezzanine base header)._

## 1. Role & sensing — DRAFT

The 24-pin is the platform's energy accountant (only family with hardware energy/charge
accumulators) and the bulk-power source for the Hub — both are enterprise-load-bearing.

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-24PIN-COMMON-001 | Sensing SHALL be 4× INA228 (12V/5V/3V3/5VSB) with the §6.4 shunt set (2 mΩ ×3, 25 mΩ 5VSB), Kelvin-sensed. | [LOCKED §6.1/§6.4] | I+T | OQ-11 (parts) |
| REQ-24PIN-COMMON-002 | Hardware energy/charge accumulation SHALL be exposed as auditable counters; reporting SHALL state the OQ-13 scope honestly (24-pin rails only, never presented as total-system energy). | spec §6.1; OQ-13 | T+I | OQ-13 |
| REQ-24PIN-COMMON-003 | The §6.13 per-rail transient detection front-end (INA181 + TLV7011 → FREEZE) SHALL be populated; the C6 GPIO budget SHALL be verified to bound the monitored-rail count before layout. | spec §6.13; rev3 doc | I+T | — |

## 2. Power topology (Hub-coupled) — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-24PIN-COMMON-010 | The module SHALL source Hub bulk 5VSB on the dedicated 2-pin feed with its own RJ-45 VCC (J1.1) left open, per the locked §2.7 topology. | [LOCKED §2.7] | I+T | — |
| REQ-24PIN-COMMON-011 | The MAIN_5V tap feeding the Hub's §2.9 priority-OR SHALL be taken downstream of the 5V INA228 shunt so Hub draw is accounted in system 5V (OQ-13 consistency). | CLAUDE.md item 0(b); spec §2.9 | I+T | — |
| REQ-24PIN-COMMON-012 | Fail-passive analysis (REQ-MOD-COMMON-030/031) SHALL additionally cover the dual Mini-Fit Jr headers and the bridging-cable path (§2.8) at full ATX load. | spec §2.8; audit §1.4 | A+T | — |

## 3. Mezzanine (integrated enterprise form) — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-24PIN-COMMON-020 | If D-ENT-5 adopts the mezzanine form, the 24-pin SHALL carry the male stack header (16-pin 2.00 mm) with the STREAM pair populated for Pro forward-compat, and the stacked unit SHALL pass the standoff/GND-bond + 8 mm gap mechanical checks. | mezzanine design doc; plan §3a context | I+T | D-ENT-5 |
