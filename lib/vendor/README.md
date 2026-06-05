# `lib/vendor/` — vendored official & third-party parts

So that **a plain `git clone` is a full-parity, self-contained project**, the
official KiCad (and any third-party) symbols and footprints the design uses are
**copied into the repo here** — not referenced from a machine's globally
installed KiCad libraries. Their 3D models are vendored into
[`../3dmodels/`](../3dmodels), and everything is referenced by
`${KIPRJMOD}`-relative paths. No clone depends on `${KICAD*_3DMODEL_DIR}` or any
absolute path.

Everything here is pinned to the KiCad library release in
[`../../versions.env`](../../versions.env) (`KICAD_LIB_TAG`), which tracks the
pinned KiCad major version.

## Layout

```
lib/vendor/
  <Lib>.kicad_sym        # vendored symbol library (copied from upstream)
  <Lib>.pretty/          # vendored footprint library
    <Footprint>.kicad_mod
```

## Bringing parts in

Use the helper rather than copying by hand, so 3D-model paths get rewritten to
repo-relative form:

```bash
scripts/vendor-libs.sh fetch                      # clone upstream libs at the pinned tag (cached, gitignored)
scripts/vendor-libs.sh add-symbol    Connector    # copy Connector.kicad_sym -> lib/vendor/
scripts/vendor-libs.sh add-footprint Connector_RJ:RJ45_Amphenol_RJHSE  # footprint + its 3D model
scripts/vendor-libs.sh verify                     # no global/absolute paths remain
```

Then add the vendored library to the board's `sym-lib-table` / `fp-lib-table`
using a `${KIPRJMOD}`-relative URI (see [`../templates/`](../templates)).

## Generic / reusable parts vendored here

Some parts are vendored to be pulled into **any** board as needed (not tied to
one design). Datasheets for these are cached in [`../datasheets/`](../datasheets)
and referenced from the symbol's `Datasheet` field.

| Part | Symbol | Footprint | 3D | LCSC / MPN |
|---|---|---|---|---|
| Generic 10 kΩ NTC thermistor (board / connector temp sense) | `cec-vendor:Thermistor_NTC` | `cec-Resistor_SMD:NTC_0402_1005Metric` | `3dmodels/Resistor_SMD.3dshapes/NCP15XH103F03RC.step` | **C77131** / Murata **NCP15XH103F03RC** |

The NTC symbol carries the real part props (Manufacturer / MPN / LCSC /
Datasheet) and a default footprint, so dropping it on a board is BOM-complete.
10 kΩ ±1 % @ 25 °C, B25/50 = 3380 K, 100 mW, −40…+125 °C. Wire it as one leg of a
divider against a fixed 10 kΩ into an MCU ADC channel. (The 12VHPWR Standard
`TH1`/`TH2` are still on the `R_Small` placeholder + generic `R_0402` land — swap
them to this symbol + footprint on their next pass; they are not yet placed on
the PCB, so it is a clean repoint.)

## Rule

Only `${KIPRJMOD}`-relative URIs. `scripts/checklist.sh` (and CI) fail the build
if a design file references a machine-global KiCad path variable or an absolute
path — that is the signal a part still needs vendoring.
