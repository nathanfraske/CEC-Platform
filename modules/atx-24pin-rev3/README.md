# atx-24pin-rev3 — BETA-2 (output-architecture revision; PCB layout not started)

> **STATUS (2026-07-04, spec §2.8 v1.4.0 output-architecture revision, owner-ratified):** the
> schematic is now **BETA-2**. J4 (the Mini-Fit Jr 24-circuit MALE output header, previously
> marked WORKING BASIS pending the D-5a ruling) is **DELETED** — it retires the two-male-header
> output form and the female-to-female 24-pin ATX bridging-cable premise that went with it.
> Output rails now cross the ratified **all-Keystone/TE connector-daughterboard interface**
> (`docs/standard-tier-review/output-daughterboard-study-2026-07-04.md` §8.9–§8.10,
> `docs/standard-tier-review/blade-fit-check-2026-07-04.md`): **9 blade-joint receptacles**
> (`TB1`–`TB9` — FINAL PART per iteration 7, 2026-07-06, owner-ratified: **TE 63969-1** FASTON
> .250 PCB receptacle, LCSC C2961150; the Keystone 3586/3557 mentioned below in this
> paragraph's original text were interim picks, retired to vendored fallbacks — the full
> selection chain lives in each TB's Note property + blade-fit-check-2026-07-04.md addendum 7, one per ratified joint — 12V×1,
> 5V×2, 3.3V×1, 5VSB×1, GND×4), each a single-pin part landing on the SAME post-shunt rail
> node its share of J4 used to carry (`TB1`→`/SENSE12V_LO`, `TB2`/`TB3`→`+5V_MAIN`,
> `TB4`→`/SENSE3V3_LO`, `TB5`→`/SENSE5VSB_LO`, `TB6`–`TB9`→`GND`), plus **one 2×5 2.54 mm
> signal header** (`J_SIG`, `cec:CEC_CONN_2x5` on the vendored
> `cec-Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical` footprint) carrying the
> flat schematic's actual J4 signal set — pin 1 = PS_ON#, pin 2 = PWR_OK, pin 3 = −12V, pin 4 =
> GND (local reference), pins 5–10 reserved/no-connect. The header's signal list was derived
> from the CURRENT flat netlist, not invented: no 5VSB-sense/remote-sense net exists on this
> board's J4 today, so none is populated. **Sense-return contacts are explicitly NOT added** —
> the output-daughterboard study's §5 decision box (e) is still open with the owner. The mating
> daughterboard (TE 63849-1 `.250"` FASTON tabs, LCSC C86469) is a separate, not-yet-created
> deliverable; this board only carries the main-board half of the interface. Netlist-verified
> before/after: every other net on this board (INA228 sense taps, the TPS2121 mux, the LP5907
> LDO, etc.) is byte-for-byte unchanged — only the 8 real rail/signal nets J4 touched gained
> their replacement member(s), plus the trivial per-pin unconnected-net churn from J4's dropped
> NC pin and J_SIG's 6 new reserved pins. `bom/bom.csv` regenerated (`kicad-cli sch export
> bom`); `fp-lib-table` gained `cec-Connector_Blade` and `cec-Connector_PinHeader_2.54mm`.
> ERC/audit-sch introduce zero new errors and zero new finding CLASSES — the only new warnings
> are the same well-documented benign `lib_symbol_mismatch` noise every other power-port
> instance on this board already produces (proportional to the net new GND/+5V_MAIN power-port
> count), and the pre-existing 1 `pin_not_driven` error (U2 CAN TXD) and pre-existing
> `wire_through_body`/`missing_lib_symbol` audit findings are untouched, unrelated to this
> change.
>
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

Originated as the same circuit as [`../atx-24pin`](../atx-24pin) (the canonical
24-pin ATX interposer) with a different PCB layout only — 24-pin input (J3)
with a right-angle cable exit. That premise is now STALE for the output side:
this schematic has since diverged (BETA-1/BETA-2 hand-splices) and no longer
carries a 24-pin output header at all — see the BETA-2 status block above.

## Output architecture (§2.8 v1.4.0, BETA-2)

Input (J3, PSU side) is unchanged: a Molex Mini-Fit Jr 24-circuit male header.
Output no longer uses a board-mount male header + bridging cable. Instead the
module's 9 rail/return nodes each land on their own Keystone 3586 SMT
universal-entry blade clip (`TB1`–`TB9`) — the main-board half of the
connector-daughterboard interface. The clips mate with TE 63849-1 `.250"`
FASTON tabs on a passive daughterboard (a separate deliverable, not yet
created in this repo); see `docs/standard-tier-review/output-daughterboard-
study-2026-07-04.md` and `blade-fit-check-2026-07-04.md` for the ratified
joint counts, the fit-check, and the two remaining owner bench gates (gang
mating-force measurement; clip-cluster confirm-soak/thermal-cycle contact-R
trend) before first fab. The low-current ATX standards circuits (PS_ON#,
PWR_OK, −12V) ride a separate 2×5 2.54 mm signal header (`J_SIG`) instead of
a blade clip; see the BETA-2 status block for its exact pin map.

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
