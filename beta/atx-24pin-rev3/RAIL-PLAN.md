# 24-pin Interposer — Rail / Spine Plan (rev2)

Real topology from the netlist. Connector is a **2×12** (J3 = PSU in, J4 = mobo
out); pins **1–12 = top row, 13–24 = bottom row**. Each rail: J3 pins (HI / shunt
input) → shunt → J4 pins (LO / shunt output). GND = In1 plane. One INA228 per rail.

## Per-rail map

| Rail | Imax | J3 in-pins | J4 out-pins | Shunt | INA | Haul layer |
|---|---|---|---|---|---|---|
| **+12 V** | 15 A | 10, 11 | 10, 11 | RS1 (2 mΩ, 2-term) | U10 | **F.Cu (local)** |
| **+5 V** | 20 A | 4, 6, 21, 22, 23 | same | RS2 (2 mΩ, 2-term) | U11 | **In2.Cu (dedicated)** |
| **+3.3 V** | 20 A | 1, 2, 12, 13 | same | RS5 (2 mΩ, 2-term) | U12 | **B.Cu (dedicated)** |
| **+5VSB** | 3 A | 9 (= +5VSB) | 9 | RS6 (25 mΩ, **4-term**) | U13 | **F.Cu (local)** |
| **GND** | — | 3,5,7,15,17,18,19,24 | same | — | — | **In1.Cu plane** |

## Layer scheme — the anti-criss-cross core
- **In1 = solid GND plane.** Untouched; all 8 GND pins via straight to it. GND
  leaves the criss-cross entirely.
- **In2 = +5 V plane, B.Cu = +3.3 V plane.** The two *spread* 20 A rails get
  dedicated planes so they never cross (different layers). Per rail: J3 pins via
  down → plane gathers → via up to the shunt (F.Cu) → through shunt → via down →
  plane fans → via up to J4 pins.
- **F.Cu = +12 V + +5VSB (local) + shunts + Kelvin + digital.** 12 V (pins 10/11)
  and 5VSB (pin 9) are compact, so short top-side hops — they don't span.
- **Via fields** at every connector pin and both shunt terminals (~25/rail, spread
  along the path, not clustered). The shunt-terminal vias carry full rail current.

## Kelvin sense (per §6.8)
- **RS1 / RS2 / RS5 (2-terminal CSS2H):** U10/U11/U12 Vin+/Vin− tap **off the shunt's
  terminal copper in layout** — short, parallel, top layer only.
- **RS6 (4-terminal WSK2512):** U13 wires to RS6's **dedicated sense pads** (2/3).
- 100 nF at each INA; Vbus (pin 8) sits on the LO/output side.

## Placement notes
- Each **shunt inline** on its rail's path (RS1 by 12V, RS2 in the 5V flow, RS5 in
  3V3, RS6 by 5VSB) — **do not** cluster all four centrally.
- Each **INA hard against its shunt.**
- **+5VSB (HI) also feeds J2 (→ Hub) and the LP5907** — branch it at the +5VSB node
  *before* RS6 (only the mobo-bound 5VSB goes through the shunt).
- **90° J4 rotation:** place J4 so its 5 V (21–23) and 3.3 V clusters land near
  J3's, to shorten the In2/B.Cu plane runs. The layer separation handles any
  residual crossing regardless of rotation, so optimize for span, not pin-alignment.
