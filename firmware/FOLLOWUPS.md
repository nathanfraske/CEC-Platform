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

## Bench bring-up findings (12vhpwr proto on real P4 silicon, 2026-06-12)

The v0 ESP app was simulation-verified only, never run on hardware; the
first silicon bring-up (ESP32-P4-Module-DEV-KIT, **ESP32-P4NRW32 SoC, rev
v1.3 early silicon**) surfaced five real issues, all now fixed (1-4
ESP-side, 5 FPGA/Gowin-side):

1. **Chip-revision floor (FIXED, commit landed).** IDF v6.0.1 defaults the
   P4 min revision to v3.1 (production); the bench chip is v1.3 -> illegal-
   instruction boot loop. Fixed: `CONFIG_ESP32P4_REV_MIN_100=y` in the
   proto sdkconfig.defaults (v1.0 floor, forward-compatible to v3.x).
2. **Console transport (FIXED).** Proto inherited the IDF P4 default UART0
   console; the DEV-KIT's exposed native USB-C is the USB-Serial-JTAG -> the
   printf banner was invisible. Fixed: `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`.
3. **v0 SPI pin map collided with the P4 flash/PSRAM bus (FIXED, re-pinned
   to GPIO 1-5).** The v0 link pins (GPIO 20-24: sclk20/mosi21/miso22/cs23/
   drdy24) sit on the P4 MSPI bus -- the IO_MUX names GPIO22=DBG_PSRAM_CK,
   23=DBG_PSRAM_CS, 28/29/30=PSRAM D/Q/WP, and the P4NRW32 has 32 MB
   in-package PSRAM there. `gpio_config(GPIO 24)` HANGS the CPU (breaks the
   flash the code runs from; no panic possible). cec_fpga_link_init was made
   non-fatal + instrumented to localize this. FIX (landed): re-pinned all 5
   FPGA-link signals to **GPIO 1-5** (sclk1/mosi2/miso3/cs4/drdy5) -- plain-
   GPIO-only per the P4 IO_MUX (no flash/PSRAM/Ethernet/console-UART/strap
   function), all exposed on the DEV-KIT header. Updated main/cec_config.h
   (PROTO_PIN_*) AND the rtl/12vhpwr-proto/README wiring table (the dock
   jumpers move with the ESP pins); the FPGA .cst (dock<->FPGA balls) and the
   AD7606 table are unaffected -- only the ESP<->dock link side changed. The
   non-fatal + instrumented init from the diagnosis is kept (a stuck link now
   logs and continues instead of boot-looping). Re-jumper at the bench per the
   new GPIO column, then reflash.
4. **DRDY idle-poll starved IDLE -> task watchdog (FIXED).** With the link
   finally up, the v0 wait-loop `vTaskDelay(pdMS_TO_TICKS(1))` in the
   DRDY-low branch rounds to **0 ticks** at the IDF default 100 Hz tick rate,
   so `vTaskDelay(0)` never yields; while DRDY stays low (FPGA not pacing yet)
   `main` spins at 100% on CPU0 and IDLE0 starves -> TWDT reset at ~5 s. Fixed:
   both loops now `vTaskDelay(PROTO_DRDY_POLL_TICKS)` (>= 1 tick, 10 ms @ 100 Hz
   << the ~200 ms frame period). printf output bytes unchanged (the teleplot/
   raw-console byte contract holds). This also makes the "waiting on DRDY" state
   stable so the FPGA side can be brought up without the board resetting.
5. **Gowin Place & Route rejected clk50/esp_mosi on dedicated config pins
   (FPGA side; FIXED via project config).** On the GW5A, ball E2 (`clk50`)
   is a CPU/SSPI config pin and B2 (`esp_mosi`) is an I2C pin; the fitter
   refuses a user signal on a dedicated pin until it's released (errors
   PR2017 "cannot be placed … dedicated pin" + PR2028). Fix: Project →
   Configuration → Place & Route → Dual-Purpose Pin → check "Use SSPI as
   regular IO" + "Use CPU as regular IO" + "Use I2C as regular IO" (leave
   MSPI/JTAG UNCHECKED — those are the boot/program pins). This is a Gowin
   project setting, not a `.cst` directive, so it lives in the local Gowin
   project rather than the repo; recorded in the rtl/12vhpwr-proto README
   build steps. The `.cst` ball map is unchanged and correct — **E2 is the
   dock's 50 MHz oscillator** (physically wired there; it just doubles as a
   config pin), so the pin is released, not relocated.

## Continuous decimated stream (12vhpwr proto, pieces 1+2, 2026-06-13)

The two-rate plan ("stream at 20-25 kSPS, burst at 200k for oversampling +
decimate"). Root cause of the ~13 kHz live ceiling is the per-frame
console/teleplot path, NOT the SPI link (`fastburst` already sustains the link
at the native rate) — confirmed by the bench polling experiment. LANDED + sim-
verified (RTL sim PASS: decimator average, LIVE, BURST, STREAM dropcount):

- **A1 — SCLK ceiling resolved analytically.** The `cec_spi_slave` 3-FF sync +
  edge detect on `sclk_s[2:1]` needs ≥2 fabric clocks per SCLK half-period:
  **fabric/4 = 12.5 MHz is the hard edge**, fabric/5 = 10 MHz the margin; 15 MHz
  (fabric/3.33, 1.67 clk/half) does NOT recover. `PROTO_LINK_CLOCK_HZ` set to
  12.5 MHz (the valid bench re-run point; back off to 10 if headers corrupt).
- **Piece 1 — boxcar decimator** (`rtl/12vhpwr-proto/cec_boxcar_decim.v`): 8
  parallel signed accumulators, M-sample average (`>> log2(M)`, M power-of-two),
  feeds the FIFO not the slave. DECIM_M is a top.v parameter beside NATIVE_HZ
  (A2: M tracks native, retune to keep the stream ~25 kSPS — NOT pinned to either
  FSM speed). Boxcar/sinc caveat documented in the module header (OK only because
  the ~14 kHz analog ceiling sits far below native Nyquist).
- **Piece 2 — free-running stream FIFO + per-session dropped-sample counter**
  (top.v): producer = decimator at native/M, consumer = ESP one frame/transaction.
  A 0x55 MOSI command selects the stream source (LIVE/BURST paths untouched). The
  frame's seq byte carries the saturating dropcount (FIFO overrun = ESP behind);
  header 0x5A = underrun (FIFO empty, stale). So a stall is a NUMBER in the record
  (C2). ESP side: `cec_fpga_link_read_stream()` + the `stream [N]` CLI (tight
  block drain off the console path; reports dropcount/underruns/rate). Teleplot
  output bytes UNCHANGED (D1 contract held).

STILL OPEN (deliberately deferred — not in pieces 1+2):
- **Overlapped-read FSM (native ~107k -> ~195k).** Would lift oversampling 2x->
  2.8x (M 4->8). NOT built: it must overlap the AD7606 convert under the previous
  read, and the single-bank AD7606's register-overwrite hazard is a SILICON-TIMING
  property an idealized-stub sim can't de-risk — bench-gated. The decimator/FIFO
  already work at any native rate, so this is an oversampling refinement, not a
  blocker. ("measured native rate" is itself a bench number, not a sim number.)
- **Piece 3 — output framing (BLOCKED on owner's tooling decision).** A true
  continuous telemetry stream to the host can't be per-sample teleplot ASCII.
  Default rec: keep teleplot as a decimated ~1-2 kHz display tap (byte-identical),
  log the 25k as a compact binary record. The C4 acquisition/console TASK SPLIT
  lands with this (its console output IS the framing question). Do not touch the
  teleplot contract until the owner calls binary-vs-decimated-teleplot.
- **Multi-frame-per-CS slave** (C3 optimization): the current slave is one frame
  per CS; the `stream` drain amortizes the EXPENSIVE part (per-frame teleplot) via
  a tight block loop, but a slave that reloads `frame` per FRAME_BITS within one CS
  would further cut the per-CS tax (~1-2 us/frame). Minor; bench-measure first.
- **BRAM budget**: burst ring + stream FIFO ≈ 0.57 Mbit. Confirm against the
  GW5A-25 BSRAM at Gowin P&R; drop STREAM_DEPTH (1024 = ~40 ms still ample) if tight.
- **Bench re-run** at 12.5 MHz to confirm the print-path diagnosis (rate stays
  ~13 kHz on the LIVE path despite +25% link bandwidth) and to measure the real
  native rate + the `stream` dropcount under load.

## Bench instruments: cal + auto-burst + rate (12vhpwr proto, 2026-06-13)

cal + auto-burst are ESP-only (reflash only); `rate` adds a small FPGA counter
(bitstream rebuild). All build + gate green.

- **`rate [ms]`** -- measures the TRUE native sample rate. A free-running 32-bit
  native-frame counter in top.v (increments every cap_stb, even when frozen) is
  read via a new 0x33 STATUS mode (header 0x5C, count[31:16] in ch0 / [15:0] in
  ch1; MSB=0 so it can't trip the 0xFF burst freeze). The ESP reads it twice over
  a known interval -> the real rate. Fixes the ~2x error from the nominal label:
  the conv+read FSM self-limits to ~100k at /4, not the 200k PROTO_NATIVE_HZ
  nominal, so an FFT scaled to 200k is 2x high. fastburst + autoburst now stamp
  proto_measured_native_hz() into the CSV header (marked measured/nominal); the
  analyzer must use that, never the nominal. This is the seed for the
  self-describing-capture header (module id + real rate + channel roles) that
  the per-module analyzer + Concierge need.

- **`cal [N]`** -- per-channel zero offset. Averages N no-load frames and sets
  each AMP channel's bias to its measured 0-A output (per-channel INA offset; the
  single provisional 2.40 V can't null them all). VOLT/RAW (vrail) left alone.
  Runtime `proto_cal_*` offsets in cec_config.c (auto-seed from PROTO_CH_CAL).
  DEFERRED: NVS-persist (offsets are lost on reboot); SPAN (V_PER_A) fit against
  a known current still owner/bench (vrail is confirmed, the amps' gain is not).
- **`autoburst <thresh_codes> [ntrig]`** -- the §6.10/§6.13 event-capture model in
  firmware: drain the decimated stream, per-channel software EMA baseline, and on
  a deviation > threshold freeze the native ring and dump it (detail + pre-roll;
  ~655 codes/A). Detection BW ~ the stream (a few kHz) = all the perfboard anti-
  alias passes; the transient lands near the dump TAIL (reactive freeze, pre-roll
  model). DEFERRED: FPGA-side native-rate detector (catches the 6-13 kHz band the
  ESP stream can't, closer to the §6.13 comparator) + a runtime-settable threshold
  over a MOSI write; runtime EMA-K; center the trigger via FPGA post-roll.

## FPGA native-rate detector (RTL, 2026-06-13)

`rtl/12vhpwr-proto/cec_native_detect.v` -- the FPGA half of the §6.10/§6.13
event-capture model the `autoburst` DEFERRED note above calls for. Module +
self-checking sim (`tb_native_detect.v`, PASS) AND now WIRED INTO `top.v`
(2026-06-13); the `tb_top` gate exercises the full path and PASSes. Add
`cec_native_detect.v` to the gate file list (done in CLAUDE.md / firmware-ci.yml /
both READMEs / tb_top header).

AS-BUILT top.v protocol (compile-time config for now -- runtime-over-MOSI is the
next increment): a STICKY arm latch driven by MOSI command bytes -- `0x44` arms,
`0x46` disarms+clears (both MSB=0 so they never trip the 0xFF freeze; STATUS/BURST
polls do NOT disarm it). On a trip the detector freezes the ring DET_POSTROLL=
DEPTH/2 frames later (CENTERED) via a `det_frozen` flag that survives status polls;
the mux was reordered so `0x33` STATUS is readable EVEN while frozen (else the
trip is unreadable), and the ring read-pointer only advances on a real 0xFF read,
not on a poll. STATUS frame V3 = `{tripped, det_frozen, 6'b0, trip_ch[7:0]}` (V1/V2
rate counter unchanged, so `rate` still works). ESP flow: send 0x44 (arm) -> poll
0x33 (V3.bit15 = tripped) -> 0xFF read the centered dump -> 0x46 then 0x44 to
re-arm. DEFAULTS: DET_THRESH=500 codes (~0.75 A), DET_KSHIFT=6 (tau ~64 frames),
DET_MASK=8'b0011_1001. CHANNEL MAP (verified in the gate): the frame packs
{shA,shB}=V1..V8 with V1 HIGH, so detector ch i = V(8-i) -- the currents V3/V4/V5/V8
land on detector ch 5/4/3/0; tb_top injects on V3 and checks trip_ch bit5.

What it does: runs at `cap_stb` on the same packed bus as `cec_boxcar_decim`;
per-channel single-pole EMA baseline (high-res accumulator, seeds to the first
sample so NO warm-up trip); trips on |sample - baseline| > THRESH for any masked
channel -> fires on a global transient AND a sudden per-pin imbalance shift (the
contact-resistance early-warning measured on the bench 2026-06-13). The win over
the ESP `autoburst`: a POSTROLL counter waits N native frames before asserting
`freeze`, so the event lands CENTERED in the ring (POSTROLL = DEPTH/2) instead of
tail-loaded. Config (THRESH / K_SHIFT / CH_MASK / POSTROLL) are module INPUTS, so
the deferred runtime-config (MOSI-written threshold / EMA-K) is just how `top.v`
drives them -- no module change. Cheap in RAM: reuses the existing BSRAM ring +
a pointer + 8 per-channel EMA accs (the SSRAM headroom from the version-B part).

REMAINING (bench, not blocking the gate): (1) FPGA bitstream rebuild + reflash.
(2) ESP `detect` CLI -- DONE 2026-06-13: `detect [timeout_ms]` arms (0x44), polls
0x33 for V3.bit15, reports which pin via trip_ch (detector ch i -> ESP idx 7-i),
drains the centered 0xFF ring like `fastburst`, then disarms (0x46);
cec_fpga_link gained `_detect_arm()`/`_detect_clear()`. Builds clean under the IDF
gate. (3) BENCH-TUNE the four compile-time constants for the real GPU: DET_THRESH
(start ~0.75 A, lower until it catches a real OCCT edge without false-firing),
DET_KSHIFT (baseline tau), DET_MASK (confirm the V(8-i) map on real captures).
(4) NEXT INCREMENT = runtime config over MOSI (multi-byte write) so threshold/k/
mask are tunable WITHOUT a bitstream rebuild -- the whole point of the FPGA path;
deferred to keep this integration small. (5) BRAM unchanged (detector adds only 8
EMA accs + a counter, no new buffer); re-confirm at Gowin P&R anyway. Two NOTES
recorded while building:
`expect` and `cross` are reserved -g2012 keywords (renamed `chk`/`hits`); a task
that reuses a test's loop iterator clobbers it (give tasks their own integer).

## Bench host tooling (firmware/tools/, 2026-06-13)

Host-side, replaces PuTTY-log + hand-extraction + manual matplotlib. The
capture->organize->analyze path is the Concierge (Appendix C) precursor.

- **cec_bench.py** -- owns the serial (no PuTTY line-drops), sends commands /
  scripts a setup sequence, splits each ===BURST_CSV=== block into
  runs/<ts>/captures/ + a manifest.md, and (--analyze) runs the analyzer per
  capture. Needs pyserial (bench machine only). Not unit-tested here (no serial
  device); syntax-checked, the user validates on the bench.
- **cec_capture_analyze.py** -- per-MODULE analysis (the user's "different
  analysis per module"). Core (parse + FFT-at-measured-rate + time-domain) +
  pluggable Profile; 12vhpwr DONE (per-pin imbalance flagged under load, rail
  droop, load fundamental w/ analog-ceiling overlay), atx-24pin/eps/pcie are
  STUBS. VALIDATED here: idle real capture -> "no_load" (no false flag); a
  synthetic loaded board with an i4 hog -> "IMBALANCE 23.5% FLAG". Uses the
  header's MEASURED rate; flags NOMINAL captures ~2x suspect.
- DEFERRED: the atx-24pin/eps/pcie profiles (energy / per-cable / §6.13 events);
  the firmware self-describing header (module id + channel roles) so the analyzer
  auto-selects the profile instead of --module; optional unified live+burst viewer
  (held -- TelePlot covers live).

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
- **12vhpwr-proto console routing (pre-bench note):** the app keeps the
  v0 default esp32p4 console — UART0 primary with USB-Serial-JTAG as
  the SECONDARY console — so the raw smoke-test loop's printf output IS
  visible over the board's USB-C (`idf.py monitor`), exactly as v0
  intended. CLI *input* (`frame`), however, binds to stdin = UART0 as
  configured; to type commands over the USB-C instead, set
  `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` in the app's
  sdkconfig.defaults (deliberately NOT flipped pre-bench: the smoke
  test should run the exact v0-default console arrangement first).

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
