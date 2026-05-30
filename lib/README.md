# `lib/` — shared CEC library (the locked universal interface)

This is the single home for the parts that implement CEC's **universal
RJ-45 interface**, so a change propagates to every board instead of being
redrawn per board. Boards reference these via project-relative library tables
(`${KIPRJMOD}`), never by duplicating the parts locally.

## Contents

| Path | What it holds |
|---|---|
| `cec.kicad_sym` | Symbol library — RJ-45 FTP jack, SK6812 LED, ESP32 module, power input, the 2-pin power-in connector, and other shared symbols (over-voltage protection net is Enterprise/MC only, OQ-8). |
| `cec.pretty/` | Footprint library (`.kicad_mod`) — the matching land patterns. |
| `3dmodels/` | 3D models referenced by footprints (project + vendored), via `${KIPRJMOD}`-relative paths. |
| `vendor/` | Vendored official/third-party symbol & footprint libraries, pinned, for clone parity. |
| `templates/` | Starting-point `sym-lib-table` / `fp-lib-table` for new boards. |

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

## Self-contained for clone parity

The repo vendors what it uses so a plain `git clone` builds without any global
KiCad libraries: official/third-party parts go in [`vendor/`](vendor), their 3D
models in [`3dmodels/`](3dmodels), all referenced by `${KIPRJMOD}`-relative
paths. `scripts/vendor-libs.sh` brings parts in at the pinned `KICAD_LIB_TAG`
([`../versions.env`](../versions.env)); `scripts/checklist.sh` fails the build if
any design file uses a machine-global `${KICAD*_DIR}` or absolute path.

## Locked interface parts

Per the spec (§2) and `CLAUDE.md`, the shared parts include:

- **RJ-45 (8P8C) shielded (FTP) jack**, locking-boot default variant.
- **Per-pin protection network (Enterprise/MC only, OQ-8)**: a TVS array plus
  series limiting resistors sized to survive accidental PoE injection up to ~57V.
  Standard and Pro do not populate it (§2.4).
- **SK6812 LED** (the chain; aggregate current is firmware-capped, §2.5 / OQ-2).
- **ESP32 module** footprint(s) (ESP32-S3 on Standard, ESP32-P4 on Pro+).
- **Power input** parts for the +5VSB rail.
