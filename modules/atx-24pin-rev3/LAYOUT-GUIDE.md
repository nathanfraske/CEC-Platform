# 24-pin ATX Interposer — Placement & Routing Priority

Why rev1 felt chaotic: power, analog sensing, and digital were interleaved, so
the 15–20 A rails, the precision Kelvin sense, and the MCU all fought for the
same space. The fix is to **zone the board and lock the spine first**, then let
the easy stuff fill in around it.

## Mental model: one spine, three zones
- **Power spine (high-current):** J3 (PSU in) → RS1/RS2/RS5/RS6 shunts →
  J4 (mobo out, 90° CCW). The dominant feature — lay it first; everything orbits it.
- **Sense clusters (analog):** each INA228 + its shunt + 100 nF, hugging the spine.
- **Digital island:** ESP32 (U1) + LDO (U3) + CAN (U2) + USB-C (J5) + housekeeping,
  kept *off* the spine so the 20 A return currents don't run under the MCU/analog.

## Do these yourself — high priority (an autorouter won't infer the intent)

**1. Mechanical anchors — place these first.** J3, J4 (90° CCW), J1 (RJ-45 → Hub),
J5 (USB-C), J2 (5VSB → Hub). These are set by the enclosure and cable exits, not by
electrons. Lock them; the layout grows around them.

**2. The power spine (J3 → shunts → J4).** Wide top+bottom pours + the In2 plane,
shunts in-path. Spread your ~25 vias/rail *along* the current path (don't clump
them — clumping is what the parallel-derate punishes). Keep rail necks
**> ~4 mm/layer on the 20 A rails** (5 V, 3 V3); 12 V/5VSB are easy. This is the
I²R + thermal heart — clean here = clean everywhere.

**3. Kelvin sense — the accuracy bit (§6.8).** Each INA228 hard against its shunt.
Sense taps come **off the shunt's terminal copper**, short, tightly parallel,
**top layer only** — never down a via and back (that folds via inductance into the
measurement). Equal-length Vin+/Vin−, 100 nF at the INA. *This is the #1 thing an
autorouter gets wrong — hand-place and hand-route it, or hard-lock it.*

**4. Logic supply.** 5VSB → LP5907 (U3) → 3 V3 → ESP32, in/out caps local, short
loop. D1 (USB ORing Schottky) by the 5VSB node.

**5. Diff pairs.** `USB_D+/USB_D-` (J5↔U1): the 90 Ω pair — short, matched,
referenced to the In1 ground plane; recompute width/gap for the 1 oz stack first.
`CAN1_P/CAN1_N` (U2↔J1): short + parallel (PCB-Z non-critical — the cable's twisted
pair + the Hub's 120 Ω split are the controlled medium; **no termination on the
module**).

**6. Decoupling.** Every IC's bypass caps right at the pin, short return to In1.

## Hand to Quilter — lock the above, then let it route the rest
Once the spine + sense clusters + connectors are locked, Quilter is great at the
tedious low-speed digital web:
- **INA228 I²C bus** — SDA/SCL/ALERT from all four to the ESP32, plus the pull-ups.
- **CAN control** — TXD/RXD ESP32 ↔ U2.
- **Housekeeping** — 74LVC1G17 (U4/U5), service/boot switches (SW1/2), status LED
  (D2), DETECT resistor (R1 → pin 8), spare ESP32 GPIO, boot/I²C pull-ups.
- **Ground stitching + copper-fill cleanup** outside the spine.

### What to actually give it
1. The **schematic** (rev2 synced copy) + your **L-shaped board outline**.
2. The project **netclasses/rules** — but first set the **HighCurrent** min-width and
   the **USB/CAN** diff width+gap for the 1 oz stack.
3. Your **locked placements** (connectors, shunts, INA228s) as fixed, plus
   **keepouts**: the high-current spine, the ESP32 antenna, the Kelvin regions.
4. Mark the **pre-routed nets** (spine, Kelvin, diff pairs) so it routes *around*
   them, not through them.

**The split: you own analog + high-current + mechanical intent; Quilter owns the
digital tedium.** Lock the spine and the sense clusters and the chaos goes away —
everything else is just filling gaps.

## High-current rails: beat the criss-cross with the stack
The ATX pinout scatters each rail across non-adjacent pins at *both ends* of the
connector (+5 V on 4/6/21/22/23, +3.3 V on 1/2/12/13, +12 V on 10/11, +5VSB on 9,
GND on 8 scattered pins), so any single-layer pour for a rail spans the whole
connector and overlaps the others. Don't fight it in 2D — use the stack as a
vertical interchange:

- **One spanning rail per layer.** Only 12 V/5 V/3.3 V span (5VSB = 1 pin, GND =
  plane), and you have F.Cu/In2/B.Cu besides the In1 GND plane. Pins via *straight
  down* to their rail's layer; rails cross on *different layers* (vias, not weaves).
  The shunt bridges on top: pin → via to rail layer → via up to shunt → via back
  down → out to J4. 5 V and 3.3 V (two clusters each) most want a dedicated layer.
- **In1 stays a solid GND plane** — the 8 GND pins just via to it; GND leaves the
  criss-cross and stays the return path + diff-pair reference.
- **Distribute the shunts inline** on each rail's lane — four shunts clustered
  centrally force every rail to converge then fan out (a crossing generator).
- **Align clusters, not pin numbers:** place/rotate J4 so its 5 V/12 V/3.3 V
  clusters sit near J3's same-rail clusters, and keep the J3↔J4 span short.
