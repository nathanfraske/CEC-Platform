# Hub Pro

Tier 2 of 4. 8 ports, CAN-FD plus RS-485 streaming receivers, USB High Speed.
Canonical detail in spec [§5](../../CEC-Platform-Ground-Truth-Spec.md). Shares
the Hub Standard base (regulator, hold-up, supervisor, LEDs, PCB approach,
identity) unless a future revision says otherwise.

| Item | Decision |
|---|---|
| Tier | 2 of 4 |
| MCU | ESP32-P4 (USB HS resolves the streaming bandwidth ceiling) |
| Ports | 8× RJ-45 8P8C, locking boot |
| Protocol | CAN-FD on the control pair, plus RS-485 streaming receivers |
| Streaming receivers | One RS-485 receiver per port (working basis, OQ-5) |
| Termination | Fixed 120 Ω split at the Hub |
| Host link | USB High Speed |
| Bulk power | Dedicated 2-pin +5VSB power-in from the 24-pin module (§2.7, OQ-1 locked); rated for the full 8-port trunk with margin |
| LEDs | SK6812 chain, firmware current cap (OQ-2); the 8-port Pro has the largest aggregate budget, now carried by the dedicated 2-pin power-in (§2.7) |
| BOM target | ~$45 (100-qty) |

## Open questions touching this board

- **OQ-1 (locked 2026-05-30):** the Hub takes bulk 5VSB on a dedicated 2-pin
  power-in connector from the 24-pin module (spec §2.7); the former 8-port
  single-VCC-pin trunk limit is removed. The power-in connector is rated for the
  full trunk with margin.
- **OQ-3:** the Hub sources REF3033 for AUX_REF (pin 7) **only if Path A** is
  chosen. Path B (local reference per module) is recommended and frees pin 7.
- **OQ-5:** per-port point-to-point vs. shared multidrop RS-485.
- **OQ-2:** firmware LED current cap.

## Status

Library-driven schematic capture can be drafted in-repo (then verified with ERC
and the netlist); PCB routing geometry is done in the KiCad 10 GUI. Project files
land here with project-local library tables pointing at `../../lib` via
`${KIPRJMOD}`. The power-netclass minimum trace width and `.kicad_dru` rules wait
on OQ-2 (the LED cap).
