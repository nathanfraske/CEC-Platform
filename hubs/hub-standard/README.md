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

- **OQ-1 (critical):** inherited basis is bulk power from the 24-pin module over
  the RJ-45 VCC pin. Confirm vs. a dedicated PSU input before trusting the
  single-pin trunk budget.
- **OQ-2:** firmware LED current cap value / max LED state to budget.

## Status

> ⚠ **Carried action item:** the Hub Standard schematic still shows **Mini-Fit
> Jr** footprints and must be **re-cut to RJ-45** before any board order. After
> the re-cut, verify no Mini-Fit Jr footprint remains and that the eight RJ-45
> pins map exactly to the locked pin allocation table.

KiCad project, schematic, and layout are authored in the KiCad 10 GUI and land
here (`hub-standard.kicad_pro` / `.kicad_sch` / `.kicad_pcb`) with project-local
`sym-lib-table` / `fp-lib-table` pointing at `../../lib` via `${KIPRJMOD}`.
