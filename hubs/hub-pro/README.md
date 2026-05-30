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
| LEDs | SK6812 chain, firmware current cap — **8-port Pro is the binding case** for the trunk budget (§2.5) |
| BOM target | ~$45 (100-qty) |

## Open questions touching this board

- **OQ-1 (critical):** the 8-port Pro is the **binding case** — 8 downstream
  modules through one VCC pin is the limiting current path. A dedicated PSU power
  input removes the constraint; do not assume the single-pin trunk.
- **OQ-3:** the Hub sources REF3033 for AUX_REF (pin 7) **only if Path A** is
  chosen. Path B (local reference per module) is recommended and frees pin 7.
- **OQ-5:** per-port point-to-point vs. shared multidrop RS-485.
- **OQ-2:** firmware LED current cap.

## Status

KiCad project, schematic, and layout are authored in the KiCad 10 GUI and land
here, with project-local library tables pointing at `../../lib` via
`${KIPRJMOD}`. The power netclass minimum trace width and `.kicad_dru` rules
wait on OQ-1 / OQ-2.
