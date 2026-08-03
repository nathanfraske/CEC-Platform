# Persist-on-fault firmware contract — Hub Standard

Spec basis: §2.9 (subsystem power management, persist-on-fault),
`docs/standard-tier-review/beta-lock-register-2026-07-03.md` §L (H1 comparator →
IO14, H2 hold-up ladder, G3 budget), OQ-56 (bench verification), OQ-85 / SB-07
(firmware-contract set).

**Status: UPDATED 2026-08-02 for the current BETA buck and selected-rail
dropout detector.** The hardware trigger now observes the final selected
`+5VSB` rail ahead of D1 and C1, rather than waiting for regulator dropout.
The conservative sudden-loss bound below is calculated, not bench-measured;
OQ-56 may move it. A re-test/re-model updates this file, the Kconfig default,
and (owner pen) spec §L together. The **trigger-to-durable-commit budget is the
binding term** until the owner re-ratifies it.
The location of this file (`firmware/contracts/`) is provisional under OQ-85 /
SB-07 ("where firmware contracts are authored and versioned" is an open
decision) — the content binds regardless of where the file ends up.

## Current-BETA bounded sudden-loss model (2026-08-02)

The current Hub Standard uses Ymin VKMI2101C472MV C1 (4700 µF nominal,
3760 µF at -20% tolerance), MDD SS14 D1, and a TLV62569 buck feeding the
reviewed 3.3 V load. With the 215.386 mA worst-case load including 20% design
margin, 4.15 V conservative reservoir start, 3.45 V reviewed regulation floor,
and 85% conversion floor, the energy model gives **11.96 ms** to the regulation
floor. A **10.00 ms** end-to-end budget therefore retains **1.96 ms** model
margin before any load shed.

The earlier 2026-07-15 16–26 ms SPICE table described the pre-buck assumptions
and remains historical evidence only; it is not the acceptance bound for this
current-BETA topology. Neither calculation is a bench result. OQ-56 must cover
fast loss and slow brownout, the actual source decay, C1 ESR/capacitance across
temperature and aging, real load shedding, and durable flash completion.

## Contract terms (binding on the Hub persist implementation)

1. **End-to-end budget — ≤ 10 ms from hardware trigger to durable commit.** On
   the TLV7011 selected-`+5VSB` dropout interrupt at IO14, the persist path
   completes ISR entry, load shedding, flash programming, the commit/index
   record, and durable-completion acknowledgement within
   `CONFIG_CEC_PERSIST_WRITE_BUDGET_MS` (default **10**, component `cec_nvs`).
   The legacy option name is retained for configuration compatibility, but its
   contract meaning is the complete trigger-to-durable interval.
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

## Feasibility inside 10 ms (to confirm on the bench, OQ-56 remainder)

ESP32-S3-WROOM quad-NOR page program (256 B) is ~0.3–0.7 ms through
`esp_flash`; the contract payload (term 2: tail + index, ≤ ~2 KB nominal) is
therefore plausible inside 10 ms only when the region is already erased and
the path is tightly bounded. There is no claimed timing margin until measured.
Still owed by OQ-56 on the bench:
the hold-up decay itself (validate the SPICE table above on real hardware),
ISR-entry-to-first-write latency, real WROOM flash throughput under our cache
config, and the PSU-side 5VSB decay shape.

## Tier outlook — owner disclosure 2026-07-16 (supercap plan)

Owner (PSU-tester thread, recording verbatim intent): *"5VSB + 5V_PSU +
5V_USB are all muxed in and we have a ~25ms hold up cap in just the
standard, and we're planning supercaps in the Pro and Max modules that
would give us tens of seconds."*

- **Standard tier**: this contract as written — the current 11.96 ms
  conservative sudden-loss bound forces the ≤10 ms program-only gasp. Nothing here
  relaxes.
- **Pro and Max (PLANNED, not yet on any board):** supercap hold-up with a
  **tens-of-seconds** window flips the persist class entirely — from
  gasp (tail + index only) to a *leisurely full-state persist*: full rings,
  captures, even in-window sector erases become legal. That tier gets ITS
  OWN contract authored when the supercap hardware lands on real boards;
  the exact board scope (which Pro/Max boards — modules, Hub Pro, testers)
  is confirmed at that design pass. Spec fold (§2.9/§L) is an owner-pen
  item, queued in `firmware/FOLLOWUPS.md`.

## Scope limits

- Binds the **beta Hub Standard** persist feature (the board with the TLV7011 →
  IO14 comparator, §L/H1). The alpha Hub has no comparator: it runs the
  continuous background commits but makes no guaranteed-gasp claim (ADC-polling
  the MAIN_5V divider is explicitly inadequate as the primary trigger — §L/H1
  rationale).
- Modules are out of scope **today**: Standard-tier modules carry no hold-up
  contract; their rings dump live over USB/CAN (§6.10). The owner-planned
  Pro/Max supercap hold-up (Tier outlook above) will bring those boards their
  own contract when the hardware lands.
- OQ-13 energy counters persist as ordinary background-commit clients under
  term 2 — no special gasp claim.
