# Quilter Constraint Set — 24-pin Interposer rev2

Lock these before handing the board to Quilter, so it routes the digital tedium
and leaves the analog / high-current / mechanical work alone. The test: how much of
the "let Quilter route" bucket it nails vs what you reclaim by hand.

## 1. Lock placements (fixed — Quilter must not move)
- **Connectors (mechanical/cable):** J3, J4 (90° CCW), J1 (RJ-45), J5 (USB-C), J2 (5VSB→Hub).
- **Shunts inline:** RS1 (12 V), RS2 (5 V), RS5 (3.3 V), RS6 (5VSB).
- **INAs at their shunts:** U10, U11, U12, U13.
- **U1 (ESP32)** region, so the antenna keepout is fixed.

## 2. Pre-route, then lock (Quilter routes around these)
- **Rail planes** per RAIL-PLAN.md: +5 V on In2, +3.3 V on B.Cu, +12 V/+5VSB on
  F.Cu, GND on In1.
- **Kelvin sense:** each INA's Vin+/Vin−/Vbus to its shunt (top, local).
- **Diff pairs:** `USB_D+`/`USB_D-` (90 Ω) and `CAN1_P`/`CAN1_N`.

## 3. Netclasses (already in the project — set widths first)
| Class | Nets | Do before Quilter |
|---|---|---|
| **HighCurrent** | RAIL12V/5V/3V3/5VSB_* | poured planes; set the via size + a fat track min-width |
| **Power** | +5VSB | wide trace — ~2.5 A to J2/Hub + the LDO |
| **USB** | USB_D+/USB_D- | recompute diff width+gap for 90 Ω on the **1 oz** stack |
| **CAN** | CAN1_P/CAN1_N | short; stock diff is fine |
| **Default** | +3V3 (logic), GND, DETECT, EN, GPIO0, + all auto-named control nets | Quilter routes |

Notes:
- `+3V3` (LP5907 logic output) is in **Default** — fine at the LDO's 250 mA;
  widen only if you want margin.
- The I²C bus, ALERT, and CAN TXD/RXD are **auto-named → Default** — fine to let
  Quilter route. (Label them only if you want them in a dedicated class.)

## 4. Keepouts
- The **high-current spine** region — no digital routing through it.
- The **ESP32 antenna** — no copper under it.
- The **Kelvin sense** zones at each shunt.

## 5. Let Quilter route (the delegate bucket)
- **INA228 I²C bus** — SDA/SCL/ALERT, U10–U13 ↔ U1, plus pull-ups.
- **CAN control** — TXD/RXD, U1 ↔ U2.
- **Housekeeping** — 74LVC1G17 (U4/U5), switches (SW1/2), LED (D2), DETECT (R1→pin 8),
  GPIO0/EN boot, spare GPIO.
- **Ground stitching + copper fill** outside the spine.

## Workflow / test loop
1. In KiCad: lock §1, pre-route §2, set §3 widths, draw §4 keepouts + the L-outline.
2. Hand Quilter the project.
3. Review what it returns:
   - Did it disturb any **locked** placement / pre-routed net? (should not)
   - Is the **I²C / CAN / housekeeping** routing sane?
   - Watch for it threading **digital through the spine** or **copper under the
     antenna** — reclaim those by hand.
4. The split holds: **you own the spine + sense + diff pairs; Quilter earns its
   keep on the digital web.** Whatever it routes badly there tells you exactly what
   to hand-route on the next board.
