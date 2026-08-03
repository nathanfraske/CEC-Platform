# hub-standard-rev2 — current hierarchical BETA

The authoritative schematic is `hub-standard-rev2.kicad_sch` and its six
functional leaves. Flat Hub schematics are archived under `old-revisions/` and
must not be used as BETA placement inputs.

## Dead-bug 24-pin stack contract

- Native Hub top view: `J2`–`J5` are packed on the left edge with their cable
  mouths facing left. The Hub is reflected to mate, so the installed assembly
  presents all four mouths on the right when the 24-pin input is bottom and the
  output field is top.
- Hub F.Cu faces ATX F.Cu. The Hub B.Cu is outward/user-visible.
- `J6P/J6C/J6D` use Samtec `SSQ-10x-03-G-D` Hub-side sockets. They mate with
  ATX `TSW-10x-17-G-D` long-post headers at an 18 mm board gap.
- The populated H1 ground lug uses an M2.5 plated/exposed land, Harwin
  `R25-1001802` 18 mm conductive standoff, and two M2.5x6 mm screws.
- The approximately 14 mm RJ-45 body has 4 mm nominal vertical margin to the
  opposing board surface.
- `DL1`–`DL5` and `DL7` are the six genuine reverse-mount SK6812MINI-E devices
  on F.Cu; obsolete outlier `DL6` exists only in the archived flat revision.
  Every emitter has a rounded Edge.Cuts aperture and its own rigidly coupled
  100 nF bypass capacitor. They shine through to B.Cu.
- `LOGO1` is B.Cu copper in the LED ring. BOOT and RESET remain on F.Cu at the
  accessible right edge, avoiding a second-side PCBA operation. Side-entry
  USB-C connectors stay on the exposed board edge.

CAN remains on J6C. The no-CAN FREEZE alternatives were assessed without an
electrical change in `docs/atx-hub-can-freeze-assessment-2026-08-03.md`.
