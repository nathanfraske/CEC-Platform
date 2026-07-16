# Tester Max — main board

DRAFT — no schematic yet. Design basis: docs/psu-tester-exploration-2026-07-14.md
(§6 addendum), docs/psu-tester-architecture-sketch-2026-07-16.md (§8/§8a),
docs/max-part-selection-2026-07-05.md (the digitizer lane of record),
testers/DESIGN-SHEET.md.

Tester Pro superset + the Max digitizer lane ON-BOARD: 4× 20 MHz AC-coupled
AFE → mux → AD9253-80 → GW5A-25 (LVDS), ESP32-P4, ONE 100BASE-T1 PHY (module
link, DETECT 10 kΩ CAN+T1 code), OVP characterization firmware on the same
TPS55289 stage, second fast-channel slice position. 2 kW ballast = population
option. Digitizer-on-main (not mezzanine) to keep the 65 MS/s LVDS short —
revisit only if the Max-module program ships a reusable mezzanine.
