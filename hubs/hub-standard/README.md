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
| Hold-up | 4700 µF / 16 V aluminum electrolytic on the isolated `+5V_HOLD` node (Panasonic EEVFK1C472M, LCSC C401967, CP_Elec_16x17.5). Chemistry corrected "polymer" → electrolytic, **ratified spec v1.9** (4700 µF polymer is unobtainable; electrolytic is right for a diode-isolated reservoir feeding the LDO). |
| Surge cap | 470 µF on the shared `+5VSB` distribution rail (rides out module load-steps; LCSC C116423, CP_Elec_6.3x7.7) |
| Inrush | 1 Ω 1 W series resistor |
| Reverse polarity | SS14 Schottky |
| Supervisor | TPS3839K33 with divider |
| Storage / identity | ESP32-S3-WROOM-1 internal 16 MB flash + 8 MB PSRAM; factory MAC + database (no eFuse, no secure element) |
| LEDs | 7× SK6812 MINI-E RGB chain, firmware current cap (§2.5 / OQ-2) |
| Service button | Hidden, GPIO0 (download mode) |
| Mounting | 4× M3 corner holes, chassis-grounded (`cec-MountingHole:MountingHole_3.2mm_M3_Pad_Via` — pad + stitching vias to the In1 GND plane; PC-standard fastener, spec v1.10) |
| PCB | 4-layer 1.6 mm, ENIG, matte black |
| BOM target | ~$36 (100-qty) |

## Open questions touching this board

- **OQ-1 (locked 2026-05-30):** the Hub takes bulk 5VSB on a dedicated 2-pin
  power-in connector from the 24-pin module and distributes 5VSB to its 4 ports
  over RJ-45 VCC (spec §2.7). The single-pin trunk concern is resolved.
- **OQ-2:** firmware LED current cap value / max LED state to budget.

## Status

> **Status (2026-06 — schematic complete, ERC-clean, ready for layout; the
> `DRAFT` marker still skips CI ERC/DRC until layout starts):** RJ-45 re-cut
> COMPLETE (4 ports + the 2-pin `CEC_PWR_IN_2P` 5VSB power-in). MCU is
> **ESP32-S3-WROOM-1-N16R8** (symbol + footprint vendored, antenna keepout
> honored). 5VSB front-end built: TPS2121 mux (PSU/USB OR-in) → SS14 isolation
> diode → 4700 µF hold-up on the isolated `+5V_HOLD` node → LP5907; 470 µF
> `C_bulk` surge cap on the shared `+5VSB`; blackout-sense divider → GPIO8.
> **Two wiring bugs fixed pre-layout:** (1) USB D+ was shorted to CAN TX/RX at
> the ESP32; (2) DETECT pull-ups (R5–R8) pulled to +5VSB instead of +3V3
> (§2.3 / ADC over-range). **ERC: 0 errors.** Netclasses (Power/USB/CAN), the
> `.kicad_dru`, and `LAYOUT-GUIDE.md` are in. Layer count confirmed **4** (for
> the L2 ground plane / EMC — see LAYOUT-GUIDE.md). PCB layout not started.
> Remaining before fab: lay out per the guide, then drop the `DRAFT` marker.

Library-driven schematic capture can be drafted in-repo (then verified with ERC
and the netlist); PCB routing geometry is done in the KiCad 10 GUI. Project files
land here (`hub-standard.kicad_pro` / `.kicad_sch` / `.kicad_pcb`) with
project-local `sym-lib-table` / `fp-lib-table` pointing at `../../lib` via
`${KIPRJMOD}`.
