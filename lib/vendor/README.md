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

## Rule

Only `${KIPRJMOD}`-relative URIs. `scripts/checklist.sh` (and CI) fail the build
if a design file references a machine-global KiCad path variable or an absolute
path — that is the signal a part still needs vendoring.
