# EPS 8-pin module

Standard-tier per-rail sensing module for the EPS (CPU) 8-pin connector. BOM
target **$32** (100-qty). See spec [§8](../../CEC-Platform-Ground-Truth-Spec.md).

| Item | Decision |
|---|---|
| Tier | Standard |
| MCU | Per module spec (not yet detailed in the ground-truth spec) |
| Connector | RJ-45 8P8C, locking boot (universal interface) |
| Control | CAN on pair 3 (classical at 500 kbps in a Standard Hub) |
| Streaming | RS-485 **not populated** (Standard); pair 2 terminated at the module side |
| DETECT | Precision resistor pin 8 → GND; code per **OQ-6** |
| Protection | TVS array + series limiting resistors on every RJ-45 pin (PoE-survivable, §2.4) |
| BOM target | $32 (100-qty) |

## Open questions touching this board

- **OQ-6:** module-ID resistor value for this module type/tier.

## Status

KiCad project, schematic, and layout are authored in the KiCad 10 GUI and land
here, with project-local library tables pointing at `../../lib` via `${KIPRJMOD}`.
