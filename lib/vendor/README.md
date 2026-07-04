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
| Keystone 3586 SMT universal-entry blade clip (30 A, top & side entry, 1 electrical node) | `cec-vendor:Keystone_3586_Blade_Clip` | `cec-Connector_Blade:Keystone_3586_SMD_Universal_Blade_Clip` | `3dmodels/Connector_Blade.3dshapes/Keystone_3586_SMD_Universal_Blade_Clip.step` | **C238113** / Keystone **3586** |
| Keystone 3557-2 THT "2 in 1" blade-clip holder (30 A/position, **2 independent electrical nodes**, not a single clip) | `cec-vendor:Keystone_3557-2_Blade_Clip_2Pos` | `cec-Connector_Blade:Keystone_3557-2_THT_Universal_Blade_Clip_2Pos` | `3dmodels/Connector_Blade.3dshapes/Keystone_3557-2_THT_Universal_Blade_Clip_2Pos.step` | **C352820** / Keystone **3557-2** |
| TE FASTON .250×.032 PCB solder tab (male, mates the Keystone clips above) | `cec-vendor:TE_63849-1_FASTON_Tab` | `cec-Connector_Blade:TE_63849-1_FASTON_Tab_250x032_THT` | `3dmodels/Connector_Blade.3dshapes/TE_63849-1_FASTON_Tab_250x032_THT.step` | **C86469** / TE **63849-1** |

The NTC symbol carries the real part props (Manufacturer / MPN / LCSC /
Datasheet) and a default footprint, so dropping it on a board is BOM-complete.
10 kΩ ±1 % @ 25 °C, B25/50 = 3380 K, 100 mW, −40…+125 °C. Wire it as one leg of a
divider against a fixed 10 kΩ into an MCU ADC channel. (The 12VHPWR Standard
`TH1`/`TH2` were repointed to this symbol + footprint on 2026-06-05, from the
`R_Small` placeholder + generic `R_0402` land — ERC clean, netlist-verified
TEMP1→IO13 / TEMP2→IO14 with wires preserved; pull onto the PCB via
Update-PCB-from-Schematic.)

The three blade-interface parts (ratified 2026-07-04, owner sign-off;
`docs/standard-tier-review/output-daughterboard-study-2026-07-04.md` §8.9–§8.10)
are vendored per the same pattern: footprints pulled via `easyeda2kicad` from
their LCSC C-numbers, upgraded to KiCad-10 with `kicad-cli fp upgrade`, then
**hand-corrected against the manufacturer's own dimensioned drawing** (cached
below) — the auto-derived export is not trusted blindly (see the 45586
row-pitch note elsewhere in this repo). Corrections made: 3557-2's 4 THT drill
holes were 1.8 mm as exported vs 1.6 mm (.063″) on Keystone's dwg — corrected;
the 63849-1 tab's 2 THT drill holes were 1.6 mm as exported vs 1.40 mm ±0.05
(⌀.055″) on TE's dwg C=63849 — corrected (this one matters: the barbed tab
shank is a press/interference fit into that hole ahead of soldering). Pad
*numbers* were also rewritten so footprint copper reflects true electrical
topology: 3586's 3 SMD pads (2 legs + a support foot) all carry pad number `1`
(one node); 3557-2's 4 THT pads were split `1`/`1`/`2`/`2` (two independent
clip positions in one housing — **not** a 2-terminal series part, see the
symbol's `Description` property and the fit-check memo below); 63849-1's 2 THT
pads were already both `1` as exported (correct). Datasheets cached as
`Keystone_3586.pdf`, `Keystone_3557-2.pdf`, `TE_63849-1.pdf` in
[`../datasheets/`](../datasheets) — all are the manufacturer's own dimensioned
drawing (Keystone dwg no. 3586 rev D / Keystone catalog M55 p.41 / TE dwg
C=63849), not marketing copy. Fit-check memo (tab-vs-clip compatibility,
retention practice at 30 A):
`docs/standard-tier-review/blade-fit-check-2026-07-04.md`. **Not yet consumed
by any board** — no board `fp-lib-table`/`sym-lib-table` references
`cec-Connector_Blade` yet; add the two table lines (see
[`../templates/README.md`](../templates/README.md)) when a board first places
one of these parts.

## Rule

Only `${KIPRJMOD}`-relative URIs. `scripts/checklist.sh` (and CI) fail the build
if a design file references a machine-global KiCad path variable or an absolute
path — that is the signal a part still needs vendoring.
