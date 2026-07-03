# atx-24pin-rev3 — BETA-1 (schematic-complete; PCB layout not started)

> **STATUS (2026-07-03, beta schematic wave, K2 ruling):** the schematic is now **BETA-1**
> (see the title block and `docs/standard-tier-review/beta-splices/atx-24pin.md` for the full
> record). This pass: (1) closed the K1 gate — the J6 mezzanine pin-map contradiction between
> this board's netlist and `docs/mezzanine-stack-design-2026-06-24.md` — in the SCHEMATIC's
> favor (the design doc was corrected; rev3's J6 and `hubs/hub-rev2`'s J_MEZZ already agreed
> with each other, so no re-pin was needed or done); (2) fixed RS4 (the 25 mOhm 5VSB shunt) onto
> a true 4-terminal Kelvin land (`CEC_SHUNT_4T` + the Vishay WSK2512 footprint, matching the
> alpha board's RS6 treatment — was a 2-pad land conflating current path and INA228 sense taps);
> (3) added the H3/H3a standalone-mode suite (USBLC6-2SC6 USB ESD, a VBUS clamp, a populated
> VBUS ferrite bead, a 0R-default port-entry bead on +5V_SYS, and a DNP CAN common-mode-choke
> position with a parallel 0R bypass so CAN stays continuous unpopulated); (4) marked the J4
> ATX output connector's form as **WORKING BASIS** pending the D-5a owner ruling (still the
> placeholder male Mini-Fit Jr header); (5) discovered and fixed a real pre-existing defect: J2
> (the Hub-power JST) was still wired to the stale `+5VSB` input net instead of the mux's
> `+5V_SYS` output, contradicting the respin doc's own stated intent.
>
> **PCB is UNTOUCHED** — still byte-identical to `../atx-24pin-rev2`'s fully-placed/routed
> layout, which predates all of the above (no mux, no mezzanine header, no C6, no H3 suite, no
> Kelvin RS4). Layout starts FRESH from this schematic; the `DRAFT` marker stays in place (CI
> correctly skips PCB-side checks) until that pass happens. Do not run "Update PCB from
> Schematic" expecting a small diff — treat the PCB as needing a full new placement/route pass.
>
> Earlier scaffold history (2026-06-24, respin design + build) is preserved below for
> provenance; the "synced copy, do not edit directly" convention it describes is now STALE —
> this schematic has been hand-spliced far beyond a sync copy and IS the source of truth for
> this board going forward (rev2 stays frozen/ordered, unrelated to this file).

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
