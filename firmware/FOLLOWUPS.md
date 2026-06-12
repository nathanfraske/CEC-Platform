# Firmware follow-ups

Tracked deferred work for the `firmware/` tree. Nothing here is a build
blocker — the build gate (RTL sim + all three IDF apps) is green. This
file absorbs `cec-24pin-idf/FOLLOWUPS.md` at the consolidation (the
per-app file is gone); the EPS-parity section of that file is dissolved
by construction — the trees are one tree now.

## Consolidation findings (2026-06-12 run — stop-and-report log)

Findings the integration runbook required surfacing rather than fixing
silently, plus the deliberate behavioral deltas the merge introduced.

- **F-1 — ESP-IDF pin moved to v6.0.1.** No single IDF version builds
  all three apps as imported: v5.3 (the runbook's pin) cannot resolve
  `esp_driver_twai` (first ships in v5.5) for eps-8pin; v5.5 lacks
  `tx_queue_remaining` + `twai_node_transmit_wait_all_done`, both used
  by the eps CAN code (`CEC_CAN_ENABLED=1`, live on the bench at
  125 kbps); v6.0.1 — the version the eps README itself pins — builds
  eps and 12vhpwr-proto untouched, and broke only atx-24pin's
  `cec_cli.c` legacy `esp_vfs_usb_serial_jtag.h` include (removed in
  6.0), which the C2 superset merge replaced with the eps
  `driver/usb_serial_jtag_vfs.h` lines anyway. Verified matrix:

  | app | v5.3.2 | v5.5.1 | v6.0.1 |
  |---|---|---|---|
  | atx-24pin | OK | OK | OK after the cec_cli VFS swap |
  | eps-8pin | FAIL (no esp_driver_twai) | FAIL (twai API gaps) | OK |
  | 12vhpwr-proto | OK | OK | OK |

  CI pins `espressif/idf:v6.0.1`; `versions.env` records it. The pin
  stays within the runbook's stated "v5.3 or newer" precondition.
- **F-2 — `cec_state_t` name conflict (C3's named stop trigger).** The
  24-pin used the name for the PSU-state ENUM (NVS-persisted via the
  L3 profile blobs); eps used it for its shared-measurement STRUCT. A
  C header cannot union those. Resolution: the enum keeps the name
  (persisted side, older lineage); the eps struct is renamed
  `cec_shared_state_t` — a pure compile-time rename across six eps
  sites with zero persisted-byte impact. All enumerator numeric values
  across the merged header are frozen (the `cec_nvs` guardrail).
- **F-3 — G1 expectation reversed.** Both apps were already
  dual-stream TelePlot (eps pioneered the CH340K UART transport; the
  24-pin adopted it), so `CONFIG_CEC_TELEMETRY_UART0` defaults ON in
  BOTH s3 apps' `sdkconfig.defaults` (the runbook expected
  "atx-24pin only"; gating eps off would have regressed it).
- **F-4 — deliberate behavioral deltas** (all conservative, none on the
  TelePlot USB-CDC byte contract):
  - eps's incidental rejection of any burst trigger in the first
    `cooldown_ms` after boot is gone (the engine adopted the 24-pin's
    `last_complete != 0` cooldown guard); the very first burst is now
    un-gated on both apps.
  - the per-burst "zero-artifact replacements: N" log line is gone
    (the carry-forward mitigation itself is kept, now in the 24-pin's
    `hs_fill`); engine ESP_LOG diagnostics follow the eps wording.
  - the 24-pin CLI now sets explicit console line endings (eps
    behavior): CR/CRLF input accepted (strict superset; `help` works
    from TelePlot's send box), and TX=LF means CLI responses and the
    JTAG-console TelePlot FALLBACK path emit bare `\n` (the primary
    UART TelePlot path was always raw `\n` and is unchanged).
  - eps emit helpers gained the 24-pin's truncation clamp (previously
    a truncating format would pass snprintf's would-be length straight
    to the writer).
- **F-5 — residual in-component constants** (semantics, not board
  wiring; the E3 rule targets pins/thresholds of a specific board):
  `cec_classifier.c` load bands (5/12/22 A, 0.5 A std) and
  `cec_state.c` PSU bands (1.0/10.5 V, 40/32/150/130 W). Hoist into
  app config when a second consumer needs different values.
- **F-6 — runbook-vs-CLAUDE.md conflict, reported not picked silently:**
  CLAUDE.md's standing rule says owner-queue items land in
  `docs/owner-queue.md` in the same change; the runbook's guardrail
  allows only `firmware/**`, one workflow, and the named doc touches.
  This file + the PR body carry the handoff items; folding them into
  the owner queue is left to the owner.

## Code-review cleanup (lint) — carried from cec-24pin-idf

The original L-items, re-evaluated against the merged engine where
Phase D required it (L2/L4/L5). Verdicts are one of closed-by-design /
still-present / needs-bench-measurement.

| # | Status | Item |
|---|---|---|
| L1 | **CLOSED (Phase E2)** | Layer 2 fed raw `0.0` instants on failed reads while its EMA held last-good (spurious ~5 V TRANSIENT on a sustained 5VSB I²C dropout). Fixed at the 24-pin call sites: the held EMA is fed as the instant on a failed read. |
| L2 | **STILL-PRESENT (as configured) — fix landed, latent; bench to flip** | The HS callback pacing still busy-spins via `taskYIELD` on the 24-pin because its FreeRTOS tick is the 100 Hz default and 1 kHz pacing can't be expressed in ticks. The merged engine automatically switches to `vTaskDelayUntil` when the tick is fine enough — set `CONFIG_FREERTOS_HZ=1000` (as eps already does) to engage it. That flip changes HS sample-edge timing, so it's a bench-verified change, not a silent one. Watchdog margin meanwhile is unchanged from v0.5.9 behavior. |
| L3 | open (unchanged) | `cec_nvs_save_blob` runs synchronously in the 50 Hz supervisor loop; flash erase/write stalls both cores for multi-hundred ms every 5 min when profiles are dirty. Move to a low-priority one-shot task. |
| L4 | **STILL-PRESENT** | Check-then-set on `s_busy` in the (now canonical eps) trigger enqueue isn't atomic; the binary semaphore swallows the double-give, so worst case remains a misleading "burst triggered" log. A short critical section or CAS closes it. |
| L5 | **STILL-PRESENT-BY-DESIGN (24-pin) / closed-in-practice (eps)** | The 24-pin keeps `snapshot_pre_at_trigger=false` and keeps pushing through the burst window (v0.5.9 semantics), so a dump can still contain torn/overwritten rows. eps avoids it structurally: its sample task skips pushes while `cec_capture_is_busy()` and the engine snapshots ring indices at trigger time. The shared engine supports both postures per app config. |
| L6 | open (unchanged) | `v_12v_rate` is a raw ΔV over the 50-sample history compared against a "V/s" threshold — correct only because 50 × 20 ms = exactly 1 s. Divide by the real window seconds or static-assert the coupling. |
| L7 | **ADDRESSED-IN-MERGE** | The all-zero-rails carry-forward is kept (now in the 24-pin's `hs_fill` via the engine's prev-row argument) with the comment refreshed for the post-DMA reality; the per-burst replacement-count log is gone. |

## Adoption / integration items

- **atx-24pin onto the shared top-layer detection (E4):**
  `cec_detection.c` / `cec_classifier.c` compile unused there — its
  main loop runs its own (non-equivalent) orchestration: per-rail
  severity tracking, per-(state,rail) L3 profiles, swing detectors,
  shutdown mute. Adoption means mapping those onto the ctx model.
- **cec_comms on the 24-pin** (carried from the old A4/G item): the
  component is shared now; the 24-pin still needs its CAN wiring,
  frame layout / IDs for its payload, and a comms task when CAN ships
  there (rev2 hardware).
- **`CEC_CAN_ENABLED` rides the shared `cec_state.h` (=1):** all three
  apps compile the esp_twai node code, which requires IDF >= 6.0 (see
  F-1). Consider Kconfig-ifying it at the next comms pass so a
  CAN-less app can drop the dependency.
- **`CEC_NUM_CABLES=2` in the shared header:** a per-board cable count
  belongs in app config when a >2-cable board (PCIe 3-port firmware)
  arrives.
- **12vhpwr-proto:** flip `CONFIG_CEC_PROTO_RAW_CONSOLE` default off
  once bring-up step 3 passes on hardware; the TelePlot loop + CLI
  `frame` command are already built and verified to compile.

## Bench items (need hardware attached)

- CLI smoke (`help` + each app's commands over the console) on both s3
  apps post-merge — deferred from C2.
- Capture parity runs against the v0.5.9 baseline (same PSU, same
  workloads) — the Phase D acceptance bar; CI proves builds only.
- `CONFIG_FREERTOS_HZ=1000` trial on the 24-pin (closes L2).
- eps: first-boot bursts are now permitted (see F-4) — observe boot-ramp
  trigger noise with the detectors' existing gates.

## Human handoff (owner)

- Archive `cec-24pin-idf` and `cec-eps-idf` on GitHub after this PR
  merges, tag each `archived-pre-monorepo`, push a final README pointer
  (runbook A5).
- Optionally fold this section + the bench items into
  `docs/owner-queue.md` (see F-6 for why this run didn't).

## Hardware-driven (carried)

- ACS712 → INA226 swap on all 24-pin rails (planned). Fixes the
  residual trim drift and the i_5v zero-load noise, and brings the
  per-rail current path onto the same I²C device family as 5VSB.
  Brings a runtime INA226 cal command with it.

## Validation backup

The original Arduino-ESP32 firmware at v0.5.9 remains the frozen
validation backup in its current home, untouched by the consolidation;
parity comparisons keep running against it until the bench items above
retire it.
