# 12VHPWR Standard module

Standard-tier per-rail sensing module for the 12VHPWR / 12V-2x6 connector. BOM
target **$49** (100-qty). See spec [§8](../../CEC-Platform-Ground-Truth-Spec.md).

| Item | Decision |
|---|---|
| Tier | Standard |
| MCU | Per module spec (not yet detailed in the ground-truth spec) |
| Connector | RJ-45 8P8C, locking boot (universal interface) |
| Control | CAN on pair 3 (classical at 500 kbps in a Standard Hub) |
| Streaming | RS-485 **not populated** (Standard); pair 2 terminated at the module side |
| DETECT | Precision resistor pin 8 → GND; code per **OQ-6** |
| Protection | TVS array + series limiting resistors on every RJ-45 pin (PoE-survivable, §2.4) |
| BOM target | $49 (100-qty) |

> ⚠ **Carried action item:** the 12VHPWR schematic still shows **Mini-Fit Jr**
> footprints and must be **re-cut to RJ-45** before any board order (spec
> reconciliation note; `CLAUDE.md` active action item). After the re-cut, verify
> no Mini-Fit Jr footprint remains and that the eight RJ-45 pins map exactly to
> the locked pin allocation table.

## Open questions touching this board

- **OQ-6:** module-ID resistor value for this module type/tier.

## Status

Library-driven schematic capture can be drafted in-repo (then verified with ERC
and the netlist); PCB routing geometry is done in the KiCad 10 GUI. Project files
land here, with project-local library tables pointing at `../../lib` via
`${KIPRJMOD}`.
