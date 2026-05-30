# `fab/` — release fabrication snapshots

This directory is **tracked on purpose**. It holds the exact package that was
sent to the board house, frozen per release, so any shipped board can be
reproduced bit-for-bit.

## Convention

- Snapshot fab outputs under `fab/<rev>/` **only at a tagged release** — not as
  routine churn on `main`.
- `<rev>` matches the release tag (for example `fab/hub-standard-v1.2/`).
- A snapshot is the complete board-house package: gerbers, drill files,
  pick-and-place (position) file, the BOM as sent, and any fab notes / stackup.

## Working outputs vs. snapshots

Day-to-day, generate fab outputs into the gitignored `build/` directory with
`scripts/fab.sh` (or `kicad-cli jobset run`). Those are regenerable from source
and are **not** committed. Only the release snapshot is copied here and tracked.

```
fab/
  <release-tag>/
    gerbers/
    drill/
    <board>-pos.csv
    <board>-bom.csv
    notes.md        # stackup, finish, panelization, board-house, order date
```
