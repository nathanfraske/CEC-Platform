# Tester Max — main board

> **STOP WORK — mandatory gate (2026-08-10).** This design must not advance,
> inherit present Standard/Pro cells, or be fabricated until
> `docs/tester-stop-work-reconciliation-gate-2026-08-10.md` is explicitly
> released.

DRAFT — no schematic yet. Design basis: docs/psu-tester-exploration-2026-07-14.md
(§6 addendum), docs/psu-tester-architecture-sketch-2026-07-16.md (§8/§8a),
docs/max-part-selection-2026-07-05.md (the digitizer lane of record),
testers/DESIGN-SHEET.md.

Tester Pro superset + the Max digitizer lane ON-BOARD: 4× 20 MHz AC-coupled
AFE → mux → AD9253-105 → GW5A-25 (LVDS), ESP32-P4, ONE 100BASE-T1 PHY (module
link, DETECT 10 kΩ CAN+T1 code), OVP characterization firmware on the same
TPS55288-class stage, second fast-channel slice position. 2 kW ballast option
RETIRED (owner 2026-07-16) → **Max-W (~3,000 W Workstation) is a population
variant of this same board** — +banks/verniers/+1 DAC80508, 4× HPWR fixture
positions, 6-fan two-lane W chassis, ganged dual fast channels (sketch §13,
BOM §3c). Front-panel main LCD + per-bay deck LCDs (sketch §5 displays).
Digitizer-on-main (not mezzanine) to keep the 65 MS/s LVDS short — revisit
only if the Max-module program ships a reusable mezzanine.
