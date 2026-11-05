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
- `J6P/J6C/J6D` use Samtec `SSQ-10x-01-G-D` short-tail Hub-side sockets. They mate with
  ATX `TSW-10x-17-G-D` long-post headers at a **provisional 22 mm** board gap.
- The previous 18 mm/M2.5 hardware is rejected: it over-inserts these connectors.
  ASB-2022E supports and SSCF-M2-5-A2 screws are now selected for qualification;
  this is not an order/release approval. The paired CAD uses 2.2 mm plated M2 holes / 4.4 mm ground lands;
  retained historical boards are not silently rewritten.
- The approximate 14 mm RJ45 body has 8 mm nominal space to bare opposing PCB
  at that target gap. Opposing bodies, tolerances and cable access still require
  qualification; this is not an assembly release.
- `DL1`–`DL5` and `DL7` are the six genuine reverse-mount SK6812MINI-E devices
  on F.Cu; obsolete outlier `DL6` exists only in the archived flat revision.
  Every emitter has a rounded Edge.Cuts aperture and its own rigidly coupled
  100 nF bypass capacitor. They shine through to B.Cu.
- `LOGO1` is B.Cu copper in the LED ring. BOOT and RESET remain on F.Cu at the
  accessible right edge, avoiding a second-side PCBA operation. Side-entry
  USB-C connectors stay on the exposed board edge.

CAN remains on J6C. The no-CAN FREEZE alternatives were assessed without an
electrical change in `docs/atx-hub-can-freeze-assessment-2026-08-03.md`.

## Latest stack ECO / placement handoff (2026-09-22)

The authoritative hierarchy and both BOMs now fit C1+C37, two Lelon
VZH472M1CTR-1816 / C249940 reservoirs. The actual-footprint paired study is
documented in `docs/hub-atx-3d-placement-qualification-2026-09-22.md` and pinned by
`docs/hub-atx-stack-placement-inputs-20260922.json`. Use those exact paired
inputs for the next placement work, not the earlier mechanical-only preview.
They are unrouted study inputs, not automatic winners or fabrication signoff.
The KiCad/CadQuery complete-population envelope model passes its declared
bounds. Candidate scoring checks the pinned peer and both vent reservations.
Supplier REF tolerances, assembled fit, cable/latch sweeps and bench tests
remain physical-release requirements.
