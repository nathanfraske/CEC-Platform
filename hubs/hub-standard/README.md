# Hub Standard

Tier 1 of 4. The mainstream Hub: 4 ports, classical CAN, USB Full Speed.
Canonical detail in spec [§4](../../CEC-Platform-Ground-Truth-Spec.md). All
v1.1 decisions carry forward unchanged **except connector and cabling**.

| Item | Decision |
|---|---|
| Tier | 1 of 4 |
| MCU | ESP32-S3-MINI-1-N16R2 |
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
| Storage / identity | ESP32-S3 internal 16 MB flash; factory MAC + database (no eFuse, no secure element) |
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

> ⚠ **Carried action item:** the Hub Standard schematic still shows **Mini-Fit
> Jr** footprints and must be **re-cut to RJ-45** before any board order. After
> the re-cut, verify no Mini-Fit Jr footprint remains and that the eight RJ-45
> pins map exactly to the locked pin allocation table.

Library-driven schematic capture can be drafted in-repo (then verified with ERC
and the netlist); PCB routing geometry is done in the KiCad 10 GUI. Project files
land here (`hub-standard.kicad_pro` / `.kicad_sch` / `.kicad_pcb`) with
project-local `sym-lib-table` / `fp-lib-table` pointing at `../../lib` via
`${KIPRJMOD}`.
