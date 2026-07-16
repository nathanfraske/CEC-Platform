# Tester Pro — main board

DRAFT — no schematic yet. Design basis: docs/psu-tester-exploration-2026-07-14.md
(§6 tier ruling), docs/psu-tester-architecture-sketch-2026-07-16.md (REV B),
docs/psu-tester-bom-draft-2026-07-16.md, testers/DESIGN-SHEET.md.

1600 W hybrid sink. Compute: ESP32-P4 + TJA1051T/3 + RS-485 stream TX
(DETECT 4.7 kΩ, the Pro CAN+RS-485 code). 8× L2 vernier CC loops (DAC80508
setpoints), R-bank switching, SCP crowbars, OVP-A stage (RULED: TPS55289
check-grade), §6.13-pattern trip comparators, USB-C PD self-power. Hosts the
fast-channel slice (separate board, testers/fast-channel-slice/) at the
12V-2x6 position. ST/Pro/Max shared blocks come from lib/ per platform rule.
