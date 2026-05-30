# 24-pin ATX module

Standard-tier per-rail sensing module for the 24-pin ATX connector. BOM target
**$35** (100-qty). See spec [§8](../../CEC-Platform-Ground-Truth-Spec.md).

| Item | Decision |
|---|---|
| Tier | Standard |
| MCU | ESP32-S3-MINI-1 (locked; same as Hub Standard) |
| Connector | RJ-45 8P8C, locking boot (universal interface) |
| Power out | Dedicated 2-pin +5VSB power-out to the Hub (§2.7); sized for the full Hub trunk with margin |
| Control | CAN on pair 3 (classical at 500 kbps in a Standard Hub) |
| Streaming | RS-485 **not populated** (Standard); pair 2 terminated at the module side |
| DETECT | Precision resistor pin 8 → GND; code per **OQ-6** |
| Protection | No per-pin PoE/over-voltage protection (Standard/Pro, §2.4); TVS + series-R is Enterprise/MC only (OQ-8) |
| BOM target | $35 (100-qty) |

## Open questions touching this board

- **OQ-1 (locked 2026-05-30):** this module is the **bulk-power source** for the
  Hub. It feeds +5VSB to the Hub over a dedicated 2-pin power-in connector
  (separate from RJ-45); the Hub then distributes 5VSB to all ports over RJ-45
  VCC (spec §2.7). Size this module's 2-pin power-out path for the full Hub trunk
  with margin.
- **OQ-6:** module-ID resistor value for this module type/tier.

## Status

Library-driven schematic capture can be drafted in-repo (then verified with ERC
and the netlist); PCB routing geometry is done in the KiCad 10 GUI. Project files
land here, with project-local library tables pointing at `../../lib` via
`${KIPRJMOD}`.
