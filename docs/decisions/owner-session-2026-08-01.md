# Owner decisions, 2026-08-01

This record governs the six-layer fabrication and Hub-to-24-pin mezzanine work.
It supersedes the optional-M2 language in the 2026-07-22 structural mezzanine
study. In this record, M2 means the metric fastener and plated mounting land,
not an M.2 edge-card socket.

## Six-layer fabrication profiles

The high-current modules and ATX 24-pin board use the 1.6 mm JLCPCB
`JLC06162H-3313` buildup:

| Layer | Role | Finished copper used by the models |
| --- | --- | ---: |
| F.Cu | Signal and power | 0.0700 mm |
| In1.Cu | Ground plane | 0.0152 mm |
| In2.Cu | Signal | 0.0152 mm |
| In3.Cu | Power routing and pours | 0.0152 mm |
| In4.Cu | Ground plane | 0.0152 mm |
| B.Cu | Signal and power | 0.0700 mm |

The Hub uses the 1.6 mm JLCPCB `JLC06161H-3313` buildup. It does not need the
high outer copper weight:

| Layer | Role | Finished copper used by the models |
| --- | --- | ---: |
| F.Cu | Signal | 0.0350 mm |
| In1.Cu | Ground plane | 0.0152 mm |
| In2.Cu | Signal | 0.0152 mm |
| In3.Cu | Power routing and pours | 0.0152 mm |
| In4.Cu | Ground plane | 0.0152 mm |
| B.Cu | Signal | 0.0350 mm |

The automatic router may use F.Cu, In2.Cu, In3.Cu, and B.Cu. It must not route
ordinary traces on In1.Cu or In4.Cu. The two ground planes remain reference
planes.

The approved process uses plated through vias only. Same-net via-in-pad is
allowed only when the board declares the matching POFV profile, the via is
through-board, its drill and annular ring pass the profile, and the full via
land is contained inside the SMD pad. Blind, buried, and microvias are not part
of these profiles.

The field electrical and thermal models must use the selected buildup's exact
copper thickness. In particular, the 0.0152 mm inner copper is not modelled as
nominal 1 oz or nominal 0.5 oz copper. At equal current and resistance target,
a 0.0152 mm inner conductor needs 2.289473684 times the width of a 0.0348 mm
conductor. This is a geometry ratio, not a claim that the resulting trace has
passed first-article thermal validation.

## Segmented mezzanine and fitted M2 ground lug

The segmented scheme remains the selected Hub-to-24-pin connection. J6P, J6C,
and J6D retain the shared position and pin-role contract from
`docs/mezz-structural-segments-2026-07-22.md`.

One coincident H1 land is required on each board at the shared mating-frame
seat. Each H1 is a 2.2 mm plated M2 hole with a 4.4 mm GND land exposed on both
outer faces. Conductive M2 hardware is fitted in the assembled stack, so the
fastener forms an inter-board ground-lug bond as well as a mechanical support.
It supplements the GND contacts in J6P, J6C, and J6D. It is not the sole normal
current-return path.

The placement pipeline may omit optional corner mounts when a real component
occupies the corner, but it may not omit or move this shared H1 datum. The
pre-route mating gate must reject either board if H1 is absent, not GND, not
plated through every copper layer, masked on either contact face, the wrong
diameter, or not coincident with its mate.

The CAD contract does not prove contact resistance or long-term mechanical
reliability. The first article still needs the specified mating fit check plus
a ground-bond resistance check before and after the peel, shake, and thermal
cycle work. Hardware finish, washer style, torque, and an acceptance resistance
must be selected from measured samples or supplier data before they become
production values.

## ESP32 operating scope

All ESP32 devices in the BETA board family operate with wireless functions
disabled. There is no wireless-enabled BETA variant. Placement guidance and
power qualification must use the wired firmware mode.

This decision removes wireless transmit-current comparisons from the electrical
audit. It does not by itself qualify the 250 mA LP5907. Each board still needs a
reviewed worst-case 3.3 V current budget for the controller, sensing, CAN, logic,
and housekeeping loads, including operating tolerance and approved margin.
