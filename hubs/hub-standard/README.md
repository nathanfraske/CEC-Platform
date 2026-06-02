# Hub Standard

Tier 1 of 4. The mainstream Hub: 4 ports, classical CAN, USB Full Speed.
Canonical detail in spec [§4](../../CEC-Platform-Ground-Truth-Spec.md). All
v1.1 decisions carry forward unchanged **except connector and cabling**.

| Item | Decision |
|---|---|
| Tier | 1 of 4 |
| MCU | ESP32-S3-WROOM-1-N16R8 (16 MB flash + 8 MB PSRAM; antenna keepout honored for future Wi-Fi). MINI-1 has no 16 MB SKU, so the aggregation Hub uses WROOM; modules stay on MINI-1. |
| Ports | 4× RJ-45 8P8C, locking boot (was Mini-Fit Jr 12-circuit) |
| Protocol | Classical CAN @ 500 kbps over the CAN-FD-capable TJA1462A |
| Termination | Fixed 120 Ω split at the Hub |
| Host link | USB Full Speed |
| Bulk power | Dedicated 2-pin +5VSB power-in from the 24-pin module; distributes to the 4 ports over RJ-45 VCC (§2.7, OQ-1 locked) |
| RS-485 | **Not populated** (Standard); pair 2 unused, terminated at the module side |
| Regulator | LP5907 LDO |
| Hold-up | 4700 µF aluminum-polymer bulk cap |
| Inrush | 1 Ω 1 W series resistor |
| Reverse polarity | SS14 Schottky |
| Supervisor | TPS3839K33 with divider |
| Storage / identity | ESP32-S3-WROOM-1 internal 16 MB flash + 8 MB PSRAM; factory MAC + database (no eFuse, no secure element) |
| LEDs | 7× SK6812 MINI-E RGB chain, firmware current cap (§2.5 / OQ-2) |
| Service button | Hidden, GPIO0 (download mode) |
| Mounting | 4× M2.5 corner holes, chassis-grounded |
| PCB | 4-layer 1.6 mm, ENIG, matte black |
| BOM target | ~$36 (100-qty) |

## Open questions touching this board

- **OQ-1 (locked 2026-05-30):** the Hub takes bulk 5VSB on a dedicated 2-pin
  power-in connector from the 24-pin module and distributes 5VSB to its 4 ports
  over RJ-45 VCC (spec §2.7). The single-pin trunk concern is resolved.
- **OQ-2:** firmware LED current cap value / max LED state to budget.

## Status

> **Status (2026-06 — WIP draft; the `DRAFT` marker skips ERC/DRC):** RJ-45
> re-cut COMPLETE (no Mini-Fit Jr remains; 4 ports + the 2-pin `CEC_PWR_IN_2P`
> 5VSB power-in). MCU now specified as **ESP32-S3-WROOM-1-N16R8** (v1.8; symbol +
> footprint vendored, antenna keepout honored). PCB layout not started.
> Remaining before fab: swap the schematic MCU symbol MINI-1 -> WROOM-1 (re-maps
> the GPIO pins), namespace the remaining stock footprints to `cec-*` for clone
> parity, clear the 2 ERC errors, then lay out.

Library-driven schematic capture can be drafted in-repo (then verified with ERC
and the netlist); PCB routing geometry is done in the KiCad 10 GUI. Project files
land here (`hub-standard.kicad_pro` / `.kicad_sch` / `.kicad_pcb`) with
project-local `sym-lib-table` / `fp-lib-table` pointing at `../../lib` via
`${KIPRJMOD}`.
