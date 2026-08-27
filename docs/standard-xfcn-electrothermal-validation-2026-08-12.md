# Standard XFCN electro-thermal validation — 2026-08-12

## Disposition

**PROTOTYPE ELECTRICAL GEOMETRY PASS / production release remains blocked.**
Every daughterboard now has complete copper connectivity, solid power-pad
connections, and passes its per-net cold copper-path budget. The isolated-board
30 °C rise screen still fails because it deliberately supplies no terminal,
cable, fastener, or enclosure heat path. That result is not overridden: release
still requires a correlated 3-D assembly model or representative hardware data.

The complete machine-readable sweep is in
`output/xfcn-electrothermal-20260812/results.json`; the generated detailed table
is in the adjacent `report.md`.

## Authority and modeled geometry

- Current boards only:
  `beta/output-daughterboards/atx24-out-db/atx24-out-db-board.kicad_pcb`,
  `beta/output-daughterboards/eps-out-db/eps-out-db-board.kicad_pcb`, and
  `beta/output-daughterboards/pcie-out-db/pcie-out-db-board.kicad_pcb`.
- ATX exact declared 1.6 mm four-layer copper: 0.070 mm on all four layers.
  This selects JLCPCB's supported 2 oz inner construction: 4-layer, 1.6 mm,
  JLC3313, and 2 oz outer copper. EPS and PCIe retain 0.070/0.035/0.035/0.070
  mm. See JLCPCB's [copper-weight constraint](https://jlcpcb.com/help/article/jlcpcb-copper-weight).
- Nominal corner: 50 °C ambient, 25 µm PTH plating, declared copper, natural
  convection plus radiation, and 0.2 mΩ per bolted interface.
- Conservative corner: 60 °C ambient, copper at 80% nominal, 20 µm PTH plating,
  restricted natural convection, low radiation, and 0–1.0 mΩ interface sweep.
- Target currents: ATX +12 V 20 A, +5 V 37.5 A, +3V3 30 A, +5VSB 7.5 A,
  aggregate GND 72.5 A; EPS +12 V/GND 65 A; PCIe +12 V/GND 48.75 A.
- Current is introduced only on the physical `F.Cu` terminal-contact face.
  Other layers are reached only through real modeled PTH/via barrels.
- The ATX cold-path result was repeated at 0.25 and 0.20 mm. Total copper loss
  was 4.429 W and 4.417 W respectively; every per-net path passed both meshes.

The 2.5-D model includes actual filled copper/traces, temperature-dependent
copper resistivity, spatially distributed via/PTH barrel resistance, lateral copper/FR4 conduction,
natural convection, and radiation. It does **not** include a 3-D terminal body,
screw, washer, cable, enclosure, or measured interface constriction. Values
above the 105 °C gate are fail indicators, not qualified destructive-temperature
predictions.

## Solid-fill verification

KiCad reports `ZONE_CONNECTION_FULL` for every ATX, EPS, and PCIe daughterboard
power zone. Each XFCN bolt pad inherits that solid setting and has no thermal or
THT-thermal local override. A reusable regression gate now enforces this in
`cec_xfcn_contract.audit_daughterboard_solid_power_connections()`.

## Isothermal 20 °C copper diagnosis

| Board | Net | Current | Copper R | Drop | Copper heat |
|---|---|---:|---:|---:|---:|
| ATX | +12V | 20.0 A | 1.649 mΩ | 32.97 mV | 0.659 W |
| ATX | +5V | 37.5 A | 0.726 mΩ | 27.22 mV | 1.021 W |
| ATX | +3V3 | 30.0 A | 0.691 mΩ | 20.74 mV | 0.622 W |
| ATX | +5VSB | 7.5 A | 4.734 mΩ | 35.51 mV | 0.266 W |
| ATX | GND | 72.5 A | 0.354 mΩ | 25.65 mV | 1.860 W |
| EPS | +12V | 65.0 A | 0.057 mΩ | 3.73 mV | 0.242 W |
| EPS | GND | 65.0 A | 0.226 mΩ | 14.69 mV | 0.955 W |
| PCIe | +12V | 48.75 A | 0.169 mΩ | 8.23 mV | 0.401 W |
| PCIe | GND | 48.75 A | 0.223 mΩ | 10.86 mV | 0.530 W |

ATX cold copper loss fell from 15.98 W to 4.43 W without enlarging its 54 x
21.3 mm outline. The repair moves signal cuts to legal edge channels, aligns the
+12 V and +3V3 terminals with their load fields, widens the +5VSB escape, and
uses the supported 2 oz inner construction. A fail-closed field gate now stores
per-layer current-density arrays and ranked bottleneck coordinates, so a future
connected-but-pinched fill cannot pass merely because KiCad reports continuity.
None of these cold-path results releases the unmodeled bolted assembly thermally.

## Contact-system decision

The intended primary electrical and thermal joint is:

`plated terminal face` ↔ `clean, flat, exposed F.Cu clamp land`

The screw supplies preload. The washer on the opposite `B.Cu` face distributes
that preload; washer/screw conductance is not counted as a parallel current or
heat path. Do not add a soft thermal pad, conductive elastomer, grease,
carbon-filled sheet, or unspecified conforming electrical interposer. Those
materials introduce unqualified resistance and creep/relaxation mechanisms.

The current ENIG declaration is acceptable only as a prototype fabrication
description, not as proof of a qualified serviceable bolted-power finish. If
direct contact cannot meet the measured resistance, temperature, and retention
limits, use a qualified rigid plated copper contact plate/coin or compression
limiter/busbar, or move to a purpose-designed power connector. Do not solve a
failed contact by inserting a generic soft pad.

## Remaining release evidence

1. Measure at least five incoming terminals of each MPN for face flatness,
   plating, thread depth, screw engagement, washer geometry, and board datum.
2. Define the exact screw, flat/spring washer or Belleville stack, locking
   method, torque tool, inspection mark, and reuse policy without exceeding the
   0.5 N·m T34069 or 1.0 N·m TTR thread limits.
3. Run four-wire end-to-end resistance and temperature-rise coupons at the
   documented currents, including unequal-current parallel-pair rejection.
4. Repeat after thermal cycling, vibration/handling, cable service, and torque
   retention checks; inspect laminate compression, pad lift, solder cracking,
   fretting, and resistance drift.
5. Correlate the 2.5-D model to the coupon or perform a full 3-D conjugate
   terminal/board/cable/enclosure solve before changing this gate to pass.
