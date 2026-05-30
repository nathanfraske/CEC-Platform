# EPS 8-pin module

Standard-tier per-rail sensing module for the EPS (CPU) 8-pin connector. BOM
target **$32** (100-qty). See spec [§8](../../CEC-Platform-Ground-Truth-Spec.md).

| Item | Decision |
|---|---|
| Tier | Standard |
| MCU | ESP32-S3-MINI-1 (locked; same as Hub Standard) |
| Connector | RJ-45 8P8C, locking boot (universal interface) |
| Control | CAN on pair 3 (classical at 500 kbps in a Standard Hub) |
| Sensing | 1× INA238 on the 12V rail — 16-bit I²C current/voltage, ≥1 kHz |
| Streaming | RS-485 **not populated** (Standard); pair 2 terminated at the module side |
| DETECT | Precision resistor pin 8 → GND; code per **OQ-6** |
| Protection | No per-pin PoE/over-voltage protection (Standard/Pro, §2.4); TVS + series-R is Enterprise/MC only (OQ-8) |
| BOM target | $32 (100-qty) |

## Open questions touching this board

- **OQ-6:** module-ID resistor value for this module type/tier.

## Status

Library-driven schematic capture can be drafted in-repo (then verified with ERC
and the netlist); PCB routing geometry is done in the KiCad 10 GUI. Project files
land here, with project-local library tables pointing at `../../lib` via
`${KIPRJMOD}`.
