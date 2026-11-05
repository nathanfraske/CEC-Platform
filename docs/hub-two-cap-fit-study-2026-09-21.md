# Hub two-cap placement/expansion study - 2026-09-21

## Result and owner decision

Follow-up: the owner accepted this two-cap direction. An opposing ATX placement
with both guarded cap reservations clear and no ATX outline growth is recorded in
[the ATX clearance placement study](atx-two-cap-clearance-placement-2026-09-21.md).
It is a separate unrouted candidate, not an assembled-stack release.

**A zero-outline-growth planar placement was found:** the Hub remains **84 x
80 mm**, adding **0 mm width, 0 mm height and 0 mm2 PCB area**. The two caps
do not fit with every other component frozen; the witness translates ten
existing parts in four groups. This demonstrates available planar room, not
completed routing or a qualified assembled stack.

The owner rejected the supercapacitor option on cost on 2026-09-21. It is no
longer an active candidate. Prior supercap calculations are retained only as
historical research; do not initiate its sourcing or implementation.

![Before and after courtyard packing](../build/hub-two-cap-fit-20260921/two-cap-comparison.png)

Gold is a capacitor body and conservative land/courtyard reservation. Blue is
a translated existing group; gray is unchanged. The outline is identical.
This is a placement diagram, not a render of completed new copper routing.

## Exact sources

Authority is `build/ordinary-relief-next-inputs-20260920.json`, the same retained
pair used by the preceding height and reservoir studies:

- Hub: `build/bound-return-hub-pass-20260916/hub-standard-rev2/02-placement/board.kicad_pcb`; SHA256 `de0e0e81c87b13824a43b336b068c17d85392eedbcef3fb15d105d0fbd66f98f`.
- ATX: `build/native-assembly-placement-pass-20260920/atx-24pin-rev3/02-placement/board.kicad_pcb`; SHA256 `cb851d4dd9c7418e53ee316c26e7fac4fbd99cb8b55bfa8f77c89b249e807773`.

Hashes and source hierarchy signatures are checked before and after the run.
No active board, hierarchy, BOM, source load, stack contract or routing was
written. The existing Hub contains 116 footprints and 157 track/via objects;
those tracks have **not** been adapted to the proposed moved placements.

## What was packed

Two **Lelon VZH472M1CTR-1816 / C249940**, each 4700 uF / 16 V, are proposed in
parallel on the existing isolated `+5V_HOLD` reservoir, not on the upstream
`C_bulk1` node. Their electrical connection is a future schematic ECO, not
already implemented by this geometry study.

The current manufacturer catalog drawing, printed page 115, was visually
reviewed. It gives an 18 mm can, +0.5 mm diameter tolerance, and 16.5 +/-0.5 mm
height. Thus the body screen uses 18.5 mm diameter and 17 mm height, before
seating/assembly tolerances. The drawing also includes wider base/terminal
geometry: merely placing two nominal 18 mm circles is insufficient.

For this conservative study each part reserves **23.2 x 20.2 mm**: catalog
20.2 mm span plus an extra 1 mm per side terminal allowance, then 0.5 mm per
side courtyard on that axis; 19.2 mm package span plus 0.5 mm per side on the
other. The extra terminal reservation is a conservative study assumption,
not a claimed manufacturer's recommended pad size. These rectangles reserve
room for lands/assembly but are **not released solder land patterns**. Final
pad/toe/heel geometry must be checked against the supplied exact part.

This is larger than the preceding rough 42 x 21 mm pair planning rectangle.
Here the capacitors are split into two open regions, reserving 937.28 mm2 in
total instead of requiring one uninterrupted side-by-side rectangle. Existing
space is reused; reserved component area does not equal required PCB growth.

## Search and resulting placements

The search tested **114,796** rectangular seat/orientation combinations on a
0.25 mm grid inside the actual rounded outline with a 0.25 mm board-edge
reserve. None were clear with all other parts frozen. Allowing the four
declared groups yielded 15 candidate seats and 54 nonintersecting cap pairs.
The first ranked pair admitted a legal bounded relocation of all displaced
groups. The solver is translation-only and preserves intra-group geometry.
Its numeric coordinates are outputs of the search, not hand-entered repairs.

| Proposed capacitor | Native Hub center X, Y (mm) | Rotation | Reserved bounds X/Y (mm) |
| --- | --- | --- | --- |
| Hold-up A | 36.10, 60.60 | 0 degrees | X 24.50-47.70; Y 50.50-70.70 |
| Hold-up B | 73.35, 40.60 | 90 degrees | X 63.25-83.45; Y 29.00-52.20 |

| Existing group | Parts | Translation X, Y (mm) |
| --- | --- | --- |
| Upstream bulk/fuse | C_bulk1, F5 | +7.3942, -4.6040 |
| Buck local cluster | U3, C2, C3, L1, R39, R40 | +1.5010, -18.3465 |
| Input diode | D8 | -3.5617, -0.0221 |
| Late fiducial | FID3 | -0.0025, +2.9963 |

RJ45s, USB/KVM connectors, mezzanines, switches, MCU, LED arrangement, backside
logo and mounting datum remain fixed. The buck's local input/output capacitors,
inductor and resistors move together, preserving their relative distances and
rotations. This avoids breaking their existing local placement while making
room; it does not certify that the original cluster is electrically optimal.
The fiducial still needs assembly/reviewer acceptance in its new location.

The group identifiers are study inputs tied to this schematic. The geometry
search does not contain board-specific relocation coordinates or exceptions.
This is a bounded study utility, **not** a new integrated generic production
placement stage or evidence of a cross-board routing improvement.

## What passes, and what does not yet

Passes in the study:

- All new capacitor reservations and moved courtyards stay inside the unchanged
  outline with the selected edge reserve.
- **Zero newly introduced courtyard intersections** between changed items and
  other front-side footprints, or between the capacitors.
- Intra-group relative vectors and all untouched geometry are unchanged.
- No front-side footprint-prohibition rule areas were present; the check is
  explicit rather than silently skipping such areas.
- Synthetic feasible and impossible packing checks pass; the source board
  hashes/hierarchy signatures are unchanged.
- Existing electrical-model suite: **10 tests and 7 subtests pass**.

Not yet passed: final footprint qualification, schematic/BOM ECO, rerouting,
full native DRC, thermal assessment and assembled two-board clearance.
Existing placement/route defects are not waived by zero new courtyard overlaps.

## Stack height remains the important conditional

This finding concerns **width/height in the PCB plane**, not total assembly
thickness. The previous 18 mm board-face gap was already invalid for the
connector engagement assumptions and original 21 mm capacitor. The approximately
22 mm target is still provisional: it is 4 mm above that old gap, but is not
an additional lift caused specifically by having two capacitors rather than one.

At 22 mm, a 17 mm cap leaves 5 mm only to a **bare** opposite PCB. The native
anchor transform (`x_ATX = 86 - x_Hub`, `y_ATX = y_Hub + 9.8`) projects:

- Hold-up A over ten ATX courtyard witnesses, mainly small regulator/mux and
  passive parts.
- Hold-up B over seventeen ATX courtyard witnesses, including ATX U1
  ESP32-C6-MINI-1 and SW1. Neither cap body reservation overlaps an opposing
  RJ45 or bolt-terminal courtyard in this nominal projection.

Courtyard overlap is not proof of a body collision. In particular, the native
ATX MCU footprint has no usable F.Fab body envelope in the current inspection;
do not silently treat that missing envelope as zero height or clear space.
Its actual body position/maximum height, switch height, cap vent clearances,
board bow and seating tolerances must be checked at a corrected mating pose.
The prior same-contact registration errors in J6P/J6C/J6D remain unresolved.
Consequently this report does **not** approve either 18 mm or 22 mm assembly
spacing, or promise zero growth after all three-dimensional constraints.

## Electrical work retained for the next ECO

The previous two-cap model, unchanged, predicts approximately 15.23-18.15 ms
in the documented aged-capacitance and ESR sensitivity cases, against 10 ms
persistence before subtracting firmware/detector overhead. These are not
guaranteed all-temperature measurements.

The pair asks for about 4.68 A **only in a hypothetical** 4.15 V rise in 10 ms at
maximum capacitance. The September 22 source review found the fitted 2.2 uF CSS
parts imply roughly 40 V/s / 125 ms to 5 V from TI's typical slew table, not
10 ms; see the [ECO review](hub-atx-cap-eco-access-closure-2026-09-22.md).
Revisit worst-case ramp/source sharing and verify startup; do
not copy the old soft-start setting without that test. Keep dropout detection
upstream of the reservoir so source loss, not buck dropout, triggers shutdown.

Next: resolve paired contact registration and the height/vent envelopes, then
create a disposable native two-cap ECO candidate, select/verify final lands,
and reroute/recheck it. Do not promote the diagram itself into fab review.

## Reproduce and inspect

From the WSL repository:

```sh
.venv/bin/python tmp/hub_two_cap_fit_20260921.py
.venv/bin/python -m pytest -q tests/test_reservoir_screen.py tests/test_hub_holdup.py
```

Artifacts: `build/hub-two-cap-fit-20260921/fit-result.json`,
`two-cap-comparison.png` and `baseline.png`. The full JSON retains each
opposing courtyard witness and any available F.Fab projection evidence.

Source dimensional drawing: [Lelon 2026 catalog, printed page 115](https://www.lelon.com.tw/upload/guides/2026%20Capacitor%20Catalog20260409094538.pdf),
also retained at `tmp/pdfs/hub-single-dual-reservoir-20260920/lelon-2026-catalog.pdf`.
