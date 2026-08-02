# ATX 24-pin rev3 placement and routing guide

## Status and authority

This guide applies to the current BETA schematic. It supersedes the earlier
four-layer and Quilter-oriented notes that occupied this file. The governing
fabrication and mating decisions are recorded in
`docs/decisions/owner-session-2026-08-01.md`. Device rules are in
`docs/standard-tier-review/STANDARD-DESIGN-SHEET.md`.

The schematic has passed the current error-level ERC and bounded DC topology
checks. Placement and routing are not closed. The checked-in candidate does not
exactly match the current schematic because C50 still has the old footprint.
No placement, route, pour, DRC, or FEM result from that candidate is release
evidence until the PCB is synchronized.

All wireless functions are excluded from this board family. The 3.3 V supply
qualification must use a reviewed worst-case load budget for the wired firmware
mode and every fitted load on that rail.

## Six-layer contract

Use the pipeline profile `jlcpcb_6l_pofv_high_current` with this modelled copper:

| Layer | Role | Finished copper |
| --- | --- | ---: |
| F.Cu | Signal and power | 0.0700 mm |
| In1.Cu | Ground reference plane | 0.0152 mm |
| In2.Cu | Signal routing | 0.0152 mm |
| In3.Cu | Power routing and pours | 0.0152 mm |
| In4.Cu | Ground reference plane | 0.0152 mm |
| B.Cu | Signal and power | 0.0700 mm |

The router may route ordinary traces on F.Cu, In2.Cu, In3.Cu, and B.Cu. It may
not route them on In1.Cu or In4.Cu. Both ground planes must remain continuous
under signal return paths except for reviewed unavoidable antipads.

At equal resistance and current, a 0.0152 mm conductor requires
2.289473684 times the width of a 0.0348 mm conductor. This is only a geometry
ratio. It does not replace the current-density and thermal gates, and it does
not establish that a routed neck is acceptable.

The public JLCPCB data reviewed for this audit supports the 0.0152 mm inner
copper buildup and 1 oz or 2 oz outer options. The exact `JLC06162H-3313`
selector name came from the owner decision record and still requires
order-screen verification before release.

## Via rules

- Use plated through vias only.
- Blind, buried, stacked, staggered, and microvias are not approved.
- Same-net via-in-pad is permitted only when the PCB declares the approved
  POFV profile and the complete via land is contained inside the SMD pad.
- A via touching a different-net pad, a through-hole pad, or a pad boundary is
  not a POFV pickup and remains a collision.
- POFV is a routing and pickup tool. It does not waive annular-ring, drill,
  current-density, thermal, or assembly checks.

## Placement order

1. Lock the board outline, J3 and J4 cable interfaces, segmented J6P/J6C/J6D,
   and the shared H1 datum. H1 is a fitted plated M2 GND lug and must coincide
   with the Hub mate.
2. Place each shunt in the direct force-current path between its input and
   output connector contacts. Do not send load current through a Kelvin tap.
3. Place each current-sense amplifier and its matched input network at its
   shunt. Route the two sense taps from the shunt terminal copper as a pair.
4. Place protection and source-selection parts at the rail nodes they protect.
   Keep their input, output, and ground loops local.
5. Place the 3.3 V regulator with its selected input and output capacitors at
   the regulator pins. Do not add the ESP reference bulk capacitor until the
   LP5907 output-capacitance conflict has an approved resolution.
6. Place one device-qualified bypass capacitor at each IC supply pin or supply
   group. A capacitor elsewhere on the same named rail is not proof of local
   bypassing.
7. Route USB and CAN only after their reference planes and connector locations
   are fixed. Route low-speed housekeeping after the force-current, Kelvin,
   protection, and differential paths are locked.

## Power pours

The current placement contract asks for `+3V3`, `+5VSB`, and `+5V_MAIN` on
In3.Cu. The slab generator must obtain current from the reviewed board current
table or thermal configuration. Missing current, conflicting current, a missing
anchor, an overlapping allocation, or a minimum-width failure must stop the
run.

The current candidate does not pass that boundary. A diagnostic run found
minimum-width failures on `+3V3` and `+5VSB`. The thermal configuration also
claims 5 A for `+5VSB` where the board specification claims 0.5 A, and 25 A for
`+5V_MAIN` where the specification claims 20 A. Those values require owner
review. The pipeline must not silently choose either source.

## Device and passive release gates

- LP5907 input and output capacitors require exact selected parts, effective
  capacitance evidence, and a complete 3.3 V load budget below the regulator's
  250 mA rating with approved margin.
- Each INA238 requires its local supply bypass and the shunt, filter, and alert
  topology specified by its channel.
- Each TLV7011 and logic gate requires the datasheet-conditioned local bypass.
- TPS2121 IN1, IN2, and OUT nodes require close selected X5R or X7R bypassing.
- Protection thresholds, divider tolerance, connector MPNs, voltage ratings,
  dielectric, package, and assembly state must be selected in CAD and BOM.
- Decouplers are placed by the supplied pin and return loop, not by reference
  number order or general proximity to the IC body.

## Release boundary

The next physical pass must first synchronize C50 and regenerate the candidate.
It must then pass exact schematic freshness, strict slab allocation, route
completion, error-level DRC, laid-copper connectivity, current-density, thermal,
and mating checks. The present candidate is not a fabrication package.
