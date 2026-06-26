# atx-24pin-rev3 — respin (SCHEMATIC done; PCB layout is the hand-off)

> **STATUS (2026-06-25):** the rev3 **SCHEMATIC is COMPLETE and is now HIERARCHICAL** — a root
> interconnect sheet + 12 per-IC sub-sheets, replacing the old flat sectioned sheet. It carries every
> rev3 delta the rev2 lacked: the **16-pin mezzanine (J6, CEC_MEZZANINE_16P)**, the **5V/5VSB power
> mux (U5 TPS2121 → +5V_SYS)**, the **§6.13 transient detection**, **C6-MINI-1**, and the **J1.1-open**
> fix. Regenerate with `python3 scripts/gen-24pin-rev3.py` (default = hierarchical into this dir;
> `--flat` = the legacy single sheet). Connectivity is gate-verified **39/39 == the flat netlist**;
> KiCad-10 ERC loads (1 benign C6-CAN-TXD pin_not_driven); per-sheet title blocks filled.
>
> **REMAINING = the PCB layout** (GUI hand-off). The .kicad_pcb here is still the **rev2-scaffold**
> (rev2's placed/routed layout, which has NONE of the new parts). To finish rev3:
> 1. **Update PCB from Schematic** (GUI) to pull the new parts: J6 mezzanine, U5 mux + C50/R50-R53,
>    the §6.13 INA181/TLV7011 cluster, R60/C60, and the 4 M3 GND mounts.
> 2. Place the **mezzanine J6 + 4 M3 mounts on the shared ~74×58 mm frame** (the Hub's 86 mm pattern is
>    too wide for the 83 mm board); the Hub Rev2 socket is the **B.Cu MIRROR** of J6 — net-check the
>    mated pairs (the #1 mezzanine error).
> 3. **Board-to-board gap = 14 mm minimum (owner directive 2026-06-25)** — 14 mm M3 standoffs + a
>    connector with a ≥14 mm mated stack height (see `../../docs/mezzanine-stack-design-2026-06-24.md`
>    §2; the generic 2.0 mm header tops out ~8-11 mm, so a 14-15 mm board-to-board family or tall-pin
>    header is needed). Verify the 14 mm gap clears all facing parts.
> 4. TPS2121 control-pin (OV/PR/CP) datasheet values + the mezzanine/standoff MPN/BOM.
>
> Full spec: **`../../docs/24pin-rev3-respin-2026-06-24.md`** + `../../docs/mezzanine-stack-design-2026-06-24.md`.

Same circuit as [`../atx-24pin`](../atx-24pin) (the canonical 24-pin ATX
interposer); **different PCB layout only** — 24-pin input (J3) with the 24-pin
output (J4) rotated 90° CCW for a right-angle cable exit.

## Known issue (prototype run) — RJ-45 VCC parallels the JST feed

rev2 ties **J1 pin 1 (RJ-45 VCC)** to `+5VSB`, so the module feeds the Hub on
**both** the dedicated JST 5VSB feed **and** its RJ-45 VCC pin, in parallel.
Because the Hub power mux sits only in the JST leg (JST = mux input, RJ-45 VCC =
mux output), a **short RJ-45 patch** makes the RJ-45 the lower-resistance path —
it carries the majority of the bulk current (up to ~1.7 A at 3 A total, over the
**1.5 A RJ-45 contact rating**) and bypasses the mux's PSU/USB OR-ing. Fixed on
rev3 by leaving J1.1 open (spec §2.7 v3.3); rev2 is ordered as-is, so mitigate at
bring-up — any one of:

1. **Long RJ-45 patch (≥1.5–2 m)** on the 24-pin↔Hub link: the conductor
   resistance then exceeds the JST+mux path, so the JST carries the bulk. No mod.
2. **Keep total 5VSB low:** cap the firmware LED budget and don't run all ports
   full-white. Under ~2 A total, even a 50/50 split keeps the RJ-45 VCC well
   under 1.5 A.
3. **Bodge — open J1 pin 1:** lift the RJ-45 VCC pin or knife-cut its trace to
   `+5VSB`, emulating the rev3 fix. Most robust; do this if you'll push full
   load. The module still self-powers from its ATX tap.

**Decision (prototype run):** go with mitigation 2 — keep the **OQ-2 firmware
5VSB cap conservative** (target ~2 A total for the rev2 prototype) so the RJ-45
VCC stays under 1.5 A regardless of patch length. No rev2 bodge and no Hub-side
workaround; the real fix is **24-pin rev3** (J1.1 no-connect). Rule of thumb:
don't run a fully-populated, full-LED system on an un-bodged rev2.

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
