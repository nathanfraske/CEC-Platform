# Enterprise module requirements — PCIe 8-pin family (deltas, 2-port + 3-port)

_All sections DRAFT. Inherits `module-requirements-common.md`. Baseline hardware = PCIe
rev2 SKUs (ESP32-C6 + per-cable INA238 ×2/×3 + §6.13 front-end)._

## 1. Sensing ladder — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-PCIE-COMMON-001 | Base sensing SHALL be per-cable INA238 (2 or 3 cables per SKU, 3 = spec upper bound) on 0.5 mΩ shunts with the §6.13 detection front-end. | [LOCKED §6.1/§6.4]; spec §6.13 | I+T | OQ-11 |
| REQ-PCIE-COMMON-002 | The enterprise sensing tier SHALL be PCIe Pro per §6.13 (fast ADC + RS-485); PCIe Max (spectral, possibly sharing the 12VHPWR Max FPGA data plane) stays PROPOSED behind OQ-59. | spec §6.13; OQ-58/59 | I | OQ-58 |
| REQ-PCIE-COMMON-003 | GPU-rail transient events SHALL carry §6.10 pre-roll and per-cable attribution into the Hub event log (GPU power forensics is a named differentiator for the workstation-fleet buyer). | spec §6.10; audit §1 (competitive) | T | — |

## 2. In-path integrity — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-PCIE-COMMON-010 | Fail-passive/FMEA coverage (REQ-MOD-COMMON-030/031) SHALL include per-cable shunt vertical transitions and the Molex 45586 in/out headers at rated current, per SKU cable count. | spec §6.7; OQ-10/12 | A+T | OQ-10/12 |
