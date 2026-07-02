# Enterprise module requirements — 12VHPWR family (deltas, Std/Pro ladder)

_All sections DRAFT. Inherits `module-requirements-common.md`. This is the flagship
forensic family for the enterprise buyer: per-pin visibility on the melt-prone connector
no BMC or PDU can see (audit competitive finding). Baseline hardware: 12VHPWR Standard
(routed, fab-direction: 6× INA240 per-pin + divider + REF3030 + NTC pair) and 12VHPWR Pro
(ESP32-P4 + LTC2358-18 + RS-485, schematic stage, $98–99)._

## 1. Sensing ladder — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HPWR-COMMON-001 | Per-pin current sensing SHALL be 6× INA240 on 1 mΩ shunts; Standard adds the REF3030 ratiometric correction and the NTC board/ambient pair (dT-above-ambient reporting). | [LOCKED §6.1/§6.4]; spec v3.7/v3.8 notes | I+T | OQ-11 |
| REQ-HPWR-COMMON-002 | The enterprise sensing tier SHALL be the Pro (LTC2358-18 simultaneous 18-bit, ~900 kB/s RS-485 streaming, CAN control, DETECT 4.7 kΩ); the Pro board SHALL graduate out of DRAFT (ERC/DRC-clean) before enterprise requirements ratification references it as baseline. | spec §6.1; 12vhpwr-pro README | I+T | — |
| REQ-HPWR-COMMON-003 | Pin-hog/imbalance detection SHALL alarm on sustained per-pin outliers (the FEM-verified case: a 12 A hog is a ~58% instant electrical outlier on one INA240 channel before thermal shows it) — this is both a safety and a tamper-relevant signature. | CLAUDE.md item 4 FEM findings | T | — |
| REQ-HPWR-COMMON-004 | 12VHPWR Max (per-pin HF/arc-band capture, FPGA branch) remains PROPOSED behind OQ-15..21/OQ-60; if adopted for the enterprise line, its 100BASE-T1 module interconnect question (OQ-20) SHALL be decided together with the Hub uplink PHY reversal (REQ-HUB-NET-030) so the platform does not carry two conflicting T1 stories. | spec §6.11; OQ-15..21/60; audit §4 | I | OQ-20 |

## 2. Sideband & connector integrity — DRAFT

| ID | Requirement | Trace | Verify | Gate |
|---|---|---|---|---|
| REQ-HPWR-COMMON-010 | The four 12V-2x6 sideband pins (SENSE0/1, CARD_PWR_STABLE, CARD_CBL_PRES#) SHALL pass through AND be monitored/reported over CAN (cable capability + present/stable state) per the v3.4 tap design. | spec §6.1 v3.4 | T | — |
| REQ-HPWR-COMMON-011 | The +12V/GND row assignment on the symmetric 12V-2x6 SHALL be verified against PCIe CEM5.1 / target GPU before any powered build (a swap shorts 12 V to GND) — carried as an explicit pre-power checklist item on every rev. | [LOCKED §2.8 safety note] | I | — |
| REQ-HPWR-COMMON-012 | Fail-passive/FMEA (REQ-MOD-COMMON-030/031) SHALL cover the board-mount header + captive pigtail form at 600 W-class load with the production cooling model declared (metal case TIM path), publishing both cooled and still-air bounds per the item-4 precedent. | spec §2.8; CLAUDE.md item 4 | A+T | — |
