# 12VHPWR Pro module — lead Pro module

Pro-tier per-rail sensing module for the 12VHPWR / 12V-2x6 connector, and the
**lead case** for the Pro module design. BOM target **$98–$99** (100-qty).
Canonical detail in spec [§6](../../CEC-Platform-Ground-Truth-Spec.md).

| Item | Decision |
|---|---|
| Tier | Pro |
| MCU | ESP32-P4 |
| Per-pin current sensing | INA240A3 analog current-sense amps on per-pin shunts |
| ADC | LTC2358-18, 8-channel simultaneous-sampling 18-bit SAR (sub-ms inter-pin timing) |
| Rail voltage | 47k/10k divider into one LTC2358 channel |
| Streaming | ~50 kHz × 6 channels, about 900 kB/s, over RS-485 (pair 2), module → Hub |
| Control | CAN-FD (pair 3) |
| Reference | Per **OQ-3** — local REF3033 recommended (Path B) |
| Connector | RJ-45 8P8C, locking boot (universal interface) |
| Protection | No per-pin PoE/over-voltage protection (Standard/Pro, §2.4); TVS + series-R is Enterprise/MC only (OQ-8) |
| DETECT | Precision resistor pin 8 → GND; code per **OQ-6** |
| BOM target | $98–$99 (100-qty) |

**Graceful degrade (expected):** in a Standard Hub this module runs CAN control
and event telemetry normally; its streaming pair is connected at the jack but
stays dark because the Standard Hub populates no RS-485 receiver (spec §6 / §7).

## Open questions touching this board

- **OQ-3:** precision reference path. Local REF3033 (Path B, recommended) vs.
  distributed AUX_REF on pin 7 (Path A). Treat AUX_REF as provisional until
  locked.
- **OQ-4:** if Path A is chosen, whether this module is restricted to
  characterized CEC cable lengths.
- **OQ-6:** module-ID resistor value for this module type/tier.

## Status

Library-driven schematic capture can be drafted in-repo (then verified with ERC
and the netlist); PCB routing geometry is done in the KiCad 10 GUI. Project files
land here, with project-local library tables pointing at `../../lib` via
`${KIPRJMOD}`.
If this board's schematic derives from the stale 12VHPWR design, carry over the
Mini-Fit-Jr → RJ-45 re-cut and re-verify the pinout.
