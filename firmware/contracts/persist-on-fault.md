# Persist-on-fault firmware contract — Hub Standard

Spec basis: §2.9 (subsystem power management, persist-on-fault),
`docs/standard-tier-review/beta-lock-register-2026-07-03.md` §L (H1 comparator →
IO14, H2 hold-up ladder, G3 budget), OQ-56 (bench verification), OQ-85 / SB-07
(firmware-contract set).

**Status: STARTED 2026-07-15 (owner direction).** The numbers below are
SPICE-SIMULATED (not bench-measured) and are the numbers of record *right now*;
bench testing (OQ-56) may move them, and a re-test/re-sim updates the table, the
Kconfig default, and (owner pen) spec §L together. The **write budget is the
binding term** until the owner re-ratifies it.
The location of this file (`firmware/contracts/`) is provisional under OQ-85 /
SB-07 ("where firmware contracts are authored and versioned" is an open
decision) — the content binds regardless of where the file ends up.

## Simulated ride-through (owner SPICE run, 2026-07-15)

Hub Standard hold-up C1 (4700 µF, Samxon/Ymin VKMI2101C472MV, LDO-fed,
D1-Schottky-isolated reservoir), 5V-loss to unusable-rail, no load shed —
**provenance: SPICE simulation, not bench measurement**:

| Hub load          | SPICE ride-through |
|-------------------|--------------------|
| 80 mA (base)      | ~26 ms             |
| 120 mA (typical)  | ~23 ms             |
| 240 mA (worst case) | ~16 ms           |

These simulated windows supersede the §L back-of-envelope *estimates* ("~25 ms
full-tilt (150 mA) / 36 ms nominal / 65–75 ms after the load-shed ISR
(70–85 mA)") and the G3 rough budget (≈60 ms @ ~100 mA) as the numbers of
record. At comparable low/typical loads the simulated window is roughly a third
of the estimated one (26 ms @ 80 mA vs 65–75 ms @ 70–85 mA estimated), which is
why the write budget below is far tighter than §L implied. They are NOT a bench
result: OQ-56's bench verification remains fully open and includes validating
this SPICE decay model on real hardware. Folding the simulated numbers into the
spec's §L row is an owner-pen spec edit (queued in `firmware/FOLLOWUPS.md`).

## Contract terms (binding on the Hub persist implementation)

1. **Write budget — ≤ 15 ms of flash programming at typical load.** On the
   power-fail trigger (beta Hub: TLV7011 5V-drop comparator → RTC-wake GPIO
   IO14, §L/H1) the persist path completes *all* flash writes within
   `CONFIG_CEC_PERSIST_WRITE_BUDGET_MS` (default **15**, component `cec_nvs`).
   15 ms is deliberately chosen *below the 16 ms worst-case simulated window*,
   so the gasp that meets budget at typical load (≥ 8 ms slack at 23–26 ms)
   also survives the 240 mA worst case even before load shed helps.
2. **No bulk dump.** The gasp writes ONLY the RAM tail + a commit/index record
   (a few KB at most). All history (events, frozen windows, counters) reaches
   flash during normal operation via **continuous background commits** — the
   ring lives mostly on flash already (§L term 3). A bulk buffer flush does not
   fit any measured window and is out of contract.
3. **Program-only gasp.** The persist region is kept **pre-erased ahead of the
   write head** during normal operation; the fault path never erases (§L
   term 2 — one NOR sector erase is tens-to-hundreds of ms, over budget by
   itself).
4. **Load shed on ISR entry** (§L term 1): the persist ISR sheds sheddable load
   first (LEDs, port 5VSB distribution per the OQ-2 posture). Shedding *adds*
   margin above the no-shed curves in the table; the budget must hold without
   it (the 16 ms worst-case row is unshed).
5. **Exclusive flash ownership during the gasp.** Background commits and every
   other NVS/flash writer are suspended; nothing else may touch flash until the
   commit record lands. Corollary: background commits run in a low-priority
   task, never a hot loop (this is also the fix shape for FOLLOWUPS lint item
   L3 — the synchronous `cec_nvs_save_blob` in the 50 Hz supervisor).
6. **Boot-side verification.** Next boot validates the commit record (CRC +
   monotonic index); a torn tail is discarded back to the last good commit. A
   torn gasp must never corrupt previously committed history.
7. **Single-source constant.** The budget lives in one place —
   `CONFIG_CEC_PERSIST_WRITE_BUDGET_MS` (`cec_nvs` Kconfig). A re-test updates
   the Kconfig default, the table above, and (owner pen) spec §L in the same
   change. Firmware must take the value from Kconfig, never re-hardcode it.

## Feasibility inside 15 ms (to confirm on the bench, OQ-56 remainder)

ESP32-S3-WROOM quad-NOR page program (256 B) is ~0.3–0.7 ms through
`esp_flash`, so 15 ms covers roughly 3–6 KB of programming plus ISR latency and
one task hop. The contract payload (term 2: tail + index, ≤ ~2 KB nominal)
therefore carries ~2× internal headroom *inside* the budget, which itself has
8–11 ms of simulated slack at typical load. Still owed by OQ-56 on the bench:
the hold-up decay itself (validate the SPICE table above on real hardware),
ISR-entry-to-first-write latency, real WROOM flash throughput under our cache
config, and the PSU-side 5VSB decay shape.

## Scope limits

- Binds the **beta Hub Standard** persist feature (the board with the TLV7011 →
  IO14 comparator, §L/H1). The alpha Hub has no comparator: it runs the
  continuous background commits but makes no guaranteed-gasp claim (ADC-polling
  the MAIN_5V divider is explicitly inadequate as the primary trigger — §L/H1
  rationale).
- Modules are out of scope: they carry no hold-up contract; their rings dump
  live over USB/CAN (§6.10).
- OQ-13 energy counters persist as ordinary background-commit clients under
  term 2 — no special gasp claim.
