# `lib/templates/` — project library-table templates

Starting-point `sym-lib-table` and `fp-lib-table` for a new board. They wire the
board to the in-repo libraries with **project-relative `${KIPRJMOD}` paths only**,
which is what keeps a clone self-contained (see [`../vendor/`](../vendor)).

## Use

Copy both files into the board's project directory:

```bash
cp lib/templates/sym-lib-table lib/templates/fp-lib-table hubs/hub-standard/
```

`${KIPRJMOD}` resolves to the board's own directory. Every board sits **two
levels** below the repo root (`hubs/<board>/`, `modules/<board>/`), so the
shared library is `${KIPRJMOD}/../../lib`. If you ever nest a board deeper, fix
the `../..` depth to match.

KiCad may renumber the `(version N)` field when it first saves the project —
that is normal and harmless.

## Adding a vendored library

When `scripts/vendor-libs.sh` adds an official/third-party part under
`lib/vendor/`, add a matching line to the board table. For example, in
`sym-lib-table`:

```
  (lib (name "Connector")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Connector.kicad_sym")(options "")(descr "Vendored, pinned"))
```

and in `fp-lib-table`:

```
  (lib (name "Connector_RJ")(type "KiCad")(uri "${KIPRJMOD}/../../lib/vendor/Connector_RJ.pretty")(options "")(descr "Vendored, pinned"))
```

## Rule

Only `${KIPRJMOD}`-relative URIs — never an absolute path and never a global
`${KICAD*_DIR}` variable. `scripts/checklist.sh` (and CI) enforce this.
