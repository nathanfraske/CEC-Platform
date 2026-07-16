# Enterprise module requirements — EPS 8-pin family (deltas)

_All sections DRAFT. Inherits `module-requirements-common.md`. Baseline hardware = EPS
rev2 (ESP32-C6 + per-cable INA238 + §6.13 detection front-end, FTP jack)._

## 1. Sensing ladder — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-EPS-COMMON-001 | Base sensing SHALL be per-cable INA238 (2 cables) on 0.5 mΩ shunts with the §6.13 binary transient detection front-end. | [LOCKED §6.1/§6.4]; spec §6.13 | I+T | OQ-11 |
| REQ-EPS-COMMON-002 | The enterprise sensing tier SHALL be EPS Pro per §6.13 (INA238 + INA240 + simultaneous fast ADC on the Pro MCU), mirroring the 12VHPWR Pro architecture — with the §6.13 RS-485 streaming leg replaced by 100BASE-T1 on the ENT build (REQ-MOD-COMMON-003; RS-485 remains the consumer Pro definition); EPS Max (spectral) stays PROPOSED behind OQ-59. | spec §6.13; REQ-MOD-COMMON-003; OQ-58/59 | I | OQ-58 |
| REQ-EPS-COMMON-003 | Per-cable transient events SHALL carry pre-roll capture per §6.10 and land in the Hub tamper/event log with cable attribution (CPU-rail forensics for the tamper buyer). | spec §6.10; tamper §2 | T | — |

## 2. In-path integrity — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-EPS-COMMON-010 | Fail-passive/FMEA coverage (REQ-MOD-COMMON-030/031) SHALL include the ~40–55 A per-cable shunt vertical transitions (OQ-10 form) and the Mini-Fit Jr in/out headers at rated current. | spec §6.7; OQ-10/12 | A+T | OQ-10/12 |
