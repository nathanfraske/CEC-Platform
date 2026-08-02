# Hub Standard BETA rev2 placement and routing guide

## Status and authority

This guide applies to `beta/hub-standard-rev2`. It replaces the historical
four-layer Hub guide. The governing fabrication and mating decisions are in
`docs/decisions/owner-session-2026-08-01.md`. Device rules are in
`docs/standard-tier-review/STANDARD-DESIGN-SHEET.md`.

The Hub schematic is closed at the current error-level ERC and bounded DC
topology boundary. Placement is deliberately left open for redesign. The
checked-in candidate is stale at U5, U7, and U11 and still has DRC,
unconnected-copper, pour, and field-model failures. It is not a fabrication
candidate.

All wireless functions are excluded from this board family. The 3.3 V supply
qualification must use a reviewed worst-case load budget for the wired firmware
mode and every fitted rail load.

## Source topology

- U5, U7, and U11 form the current TPS2121 cascade.
- CP2 pin 3 is tied low at every stage. The exported netlist therefore proves
  the fixed source priority `MAIN_5V > 5VSB > USB > KVM` at the bounded DC
  topology level.
- L2 is DNP and excluded from the BOM. No inductance value is needed.
- Each TPS2121 IN1, IN2, and OUT node requires a selected close X5R or X7R
  bypass capacitor. The present schematic does not satisfy every node.
- The SPICE harness does not prove switchover transient response, protection
  thresholds, reverse-current dynamics, thermal behavior, or fault energy.

## Six-layer contract

Use the pipeline profile `jlcpcb_6l_pofv_signal` with this modelled copper:

| Layer | Role | Finished copper |
| --- | --- | ---: |
| F.Cu | Signal | 0.0350 mm |
| In1.Cu | Ground reference plane | 0.0152 mm |
| In2.Cu | Signal routing | 0.0152 mm |
| In3.Cu | Power routing and pours | 0.0152 mm |
| In4.Cu | Ground reference plane | 0.0152 mm |
| B.Cu | Signal | 0.0350 mm |

The router may use F.Cu, In2.Cu, In3.Cu, and B.Cu. It may not place ordinary
traces on In1.Cu or In4.Cu. Both ground planes must remain continuous under
signal return paths except for reviewed unavoidable antipads.

At equal resistance and current, a 0.0152 mm conductor requires
2.289473684 times the width of a 0.0348 mm conductor. The current-density and
thermal gates remain mandatory because this ratio does not account for copper
spreading, necks, vias, contact resistance, temperature, or enclosure cooling.

## Via rules

- Use plated through vias only.
- Blind, buried, stacked, staggered, and microvias are not approved.
- Same-net via-in-pad is permitted only under the declared POFV profile when the
  complete via land is inside the SMD pad.
- The pickup synthesizer may center a qualified POFV in a suitable pad. If that
  is impossible, it may use a guarded adjacent via and stub. If neither is
  geometrically safe, it must report a placement failure.

## Segmented mezzanine and ground lug

J6P, J6C, and J6D remain the selected segmented Hub-to-24-pin scheme. H1 is a
mandatory coincident plated M2 GND land on both boards. Conductive hardware is
fitted, so H1 supplements the connector ground contacts as an inter-board
ground bond. It is not the sole normal return path.

Lock the three connector segments and H1 before automatic placement. The mating
gate must reject missing, moved, masked, unplated, dimensionally wrong, or
noncoincident H1 geometry.

## Placement order

1. Lock J6P/J6C/J6D, H1, all external ports, board outline, and enclosure-driven
   access points.
2. Place the U5/U7/U11 source cascade and hold-up network as a compact power
   cell. Keep each source path direct and each bypass loop local.
3. Place the 3.3 V regulator with its exact selected input and output
   capacitors. Do not add the ESP reference bulk capacitor until the LP5907
   output-capacitance conflict has an approved resolution.
4. Place port power switching, CAN front ends, USB circuitry, monitoring, and
   logic in repeated functional cells. Each cell must retain a direct ground
   return and one-to-one local bypass coverage.
5. Reserve In3.Cu corridors and safe vertical pickups before routing ordinary
   signals. Do not assume a same-net named zone reaches an SMD pad.
6. Route USB and CAN over a continuous reference plane. Route housekeeping only
   after the source, protection, power pickup, and differential paths are fixed.

## Current Hub pour contract

The Hub asks for eleven In3.Cu slabs:

- `+5VSB`
- `/5VSB_RAW`
- `/PSU_5V`
- `/PSU_5V_KVM`
- `/MAIN_5V_RAW`
- `/USB_VBUS`
- `/+5V_HOLD`
- `/VCC_P1`
- `/VCC_P2`
- `/VCC_P3`
- `/VCC_P4`

The standalone runner now takes this list from the current placement contract,
not from stale zones in a candidate. It removes inherited slabs, creates safe
pickups where possible, and rebuilds the allocation. It stops on missing
current, current-source conflict, missing anchors, overlap, or a minimum-width
failure.

A live ripped-board diagnostic created 40 pickups, including 28 qualified POFV
pickups and 12 guarded stub vias. It then stopped because the present placement
could not provide every required anchor and minimum-width corridor. In
particular, `/PSU_5V` and `/PSU_5V_KVM` had no usable inner anchor with the
current pad geometry. This is a placement redesign requirement, not permission
to reduce the design current or relax the pour floor.

## Device and passive release gates

- LP5907 qualification requires exact selected stability capacitors, effective
  capacitance evidence, and a complete 3.3 V load budget below 250 mA with
  approved margin.
- Every IC supply pin or supply group requires the device-qualified local
  bypass. Rail-level capacitance elsewhere does not satisfy that rule.
- TPS2121 bypassing must be checked per IN1, IN2, and OUT node.
- Protection thresholds, divider tolerance, voltage rating, dielectric,
  package, connector MPN, and assembly state must be explicit in CAD and BOM.
- Decouplers must minimize the supplied-pin to capacitor to return loop. Their
  placement is checked after the PCB is synchronized, not inferred from the
  schematic net name.

## Closure boundary

For now, the Hub is closed only at schematic, error-level ERC, and bounded DC
topology SPICE. A future placement redesign must synchronize U5, U7, and U11,
then pass strict pours, routing, error-level DRC, laid-copper connectivity, FEM,
and mating checks. No current physical result supports fabrication release.
