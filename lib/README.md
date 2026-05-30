# `lib/` — shared CEC library (the locked universal interface)

This is the single home for the parts that implement CEC's **universal
RJ-45 interface**, so a change propagates to every board instead of being
redrawn per board. Boards reference these via project-relative library tables
(`${KIPRJMOD}`), never by duplicating the parts locally.

## Contents

| Path | What it holds |
|---|---|
| `cec.kicad_sym` | Symbol library — RJ-45 FTP jack, TVS + series-resistor protection net, SK6812 LED, ESP32 module, power input, and the other shared symbols. |
| `cec.pretty/` | Footprint library (`.kicad_mod`) — the matching land patterns. |
| `3dmodels/` | 3D models referenced by the footprints. |

## Authoring

`cec.kicad_sym` and the footprints in `cec.pretty/` are authored in the **KiCad
10 Symbol Editor / Footprint Editor** — not by hand-editing s-expressions. This
directory is the agreed location for them; the files themselves are added from
the GUI as the universal-interface parts are drawn.

## Wiring a board to this library

In each board's `sym-lib-table` / `fp-lib-table`, add project-relative entries,
for example:

```
(lib (name "cec")(type "KiCad")(uri "${KIPRJMOD}/../../lib/cec.kicad_sym")(options "")(descr "CEC shared symbols"))
(lib (name "cec")(type "KiCad")(uri "${KIPRJMOD}/../../lib/cec.pretty")(options "")(descr "CEC shared footprints"))
```

Adjust the `../..` depth to the board's location (`hubs/<board>` and
`modules/<board>` are both two levels below the repo root). **Never commit
absolute library paths.**

## Locked interface parts

Per the spec (§2) and `CLAUDE.md`, the shared parts include:

- **RJ-45 (8P8C) shielded (FTP) jack**, locking-boot default variant.
- **Per-pin protection network**: TVS array plus series limiting resistors on
  every pin, sized to survive accidental PoE injection up to ~57V. The VCC
  series resistor is sized together with the power budget (§2.4–2.5).
- **SK6812 LED** (the chain; aggregate current is firmware-capped, §2.5 / OQ-2).
- **ESP32 module** footprint(s) (ESP32-S3 on Standard, ESP32-P4 on Pro+).
- **Power input** parts for the +5VSB rail.
