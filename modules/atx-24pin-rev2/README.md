# atx-24pin-rev2 — right-angle layout variant

Same circuit as [`../atx-24pin`](../atx-24pin) (the canonical 24-pin ATX
interposer); **different PCB layout only** — 24-pin input (J3) with the 24-pin
output (J4) rotated 90° CCW for a right-angle cable exit.

## Shared schematic (canonical = atx-24pin)
The schematic here is a **synced copy**. The source of truth is
`../atx-24pin/24pin-module.kicad_sch`.

1. Edit the schematic in `../atx-24pin`.
2. Run `./sync-schematic.sh` here to refresh this copy.
3. **Tools → Update PCB from Schematic** in this project's board.

Do not edit this copy directly — `sync-schematic.sh` overwrites it from canonical.

## PCB
Starts as a blank slate: **only J3 and J4 are placed**, on the inherited 1 oz
stackup + netclasses (USB/CAN/Power/HighCurrent) + design rules. Everything else
arrives via *Update PCB from Schematic*, ready to place around the right-angle
header arrangement. (A fresh DRC will show unconnected items until that import.)
