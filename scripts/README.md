# `scripts/` — kicad-cli wrappers and CI helpers

Thin, portable Bash wrappers around `kicad-cli`, plus CI and vendoring helpers.
Every script calls through [`kicad-cli.sh`](kicad-cli.sh), which prefers a local
`kicad-cli` and otherwise runs the official **KiCad Docker image** (image and tag
pinned in [`../versions.env`](../versions.env) as `KICAD_IMAGE`, default
`kicad/kicad:10.0`). Reports and outputs go to
the gitignored `build/<board>/` directory.

| Script | Does | Usage |
|---|---|---|
| `kicad-cli.sh` | Wrapper: local `kicad-cli`, else Docker | `scripts/kicad-cli.sh <args…>` |
| `erc.sh` | Electrical rule check (schematic) | `scripts/erc.sh <board.kicad_sch>` |
| `drc.sh` | Design rule check (layout) | `scripts/drc.sh <board.kicad_pcb>` |
| `netlist.sh` | Export netlist (check vs. pin table) | `scripts/netlist.sh <board.kicad_sch>` |
| `bom.sh` | Export BOM (check vs. spec targets) | `scripts/bom.sh <board.kicad_sch>` |
| `render.sh` | Top-side PNG render | `scripts/render.sh <board.kicad_pcb>` |
| `fab.sh` | Gerbers + drill + pick-and-place → `build/` | `scripts/fab.sh <board.kicad_pcb>` |
| `check-all.sh` | ERC every schematic, DRC every layout (CI) | `scripts/check-all.sh` |
| `checklist.sh` | Repo hygiene: no Mini-Fit Jr, in-repo relative lib/3D paths (CI) | `scripts/checklist.sh` |
| `vendor-libs.sh` | Vendor official/3rd-party parts + 3D models for clone parity | `scripts/vendor-libs.sh fetch` (then `add-symbol`/`add-footprint`/`add-3dmodel`/`verify`) |

`erc.sh` / `drc.sh` follow `kicad-cli` conventions: **exit 0 = clean, 5 =
violations**, other = tool error. `check-all.sh` aggregates those and is a clean
no-op until boards exist.

## Examples

```bash
# One board
scripts/erc.sh hubs/hub-standard/hub-standard.kicad_sch
scripts/drc.sh hubs/hub-standard/hub-standard.kicad_pcb

# Everything, the way CI runs it
scripts/check-all.sh
scripts/checklist.sh

# Pin the toolchain image explicitly
KICAD_IMAGE=kicad/kicad:10.0 scripts/check-all.sh
```

## Notes

- Keep the container's KiCad on the same major version as the project (**KiCad
  10**); the file format is forward-only. The pin lives in
  [`../versions.env`](../versions.env) (sourced by these scripts; CI uses the
  same image tag).
- `vendor-libs.sh` copies official/third-party parts and their 3D models into the
  repo at the pinned `KICAD_LIB_TAG`, so a plain clone is self-contained.
- `fab.sh` writes working outputs to `build/`. Release packages are snapshotted
  to `fab/<rev>/` at a tag, not produced here as churn.
- If a board defines a `.kicad_jobset`, prefer `kicad-cli jobset run` for fab
  outputs so settings match the GUI (confirm flags with `kicad-cli jobset run -h`).
