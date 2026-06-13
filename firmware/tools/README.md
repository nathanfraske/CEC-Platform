# Bench tooling (`firmware/tools/`)

Host-side tools for the 12vhpwr proto bench. They replace "open PuTTY, log
everything, extract CSVs by hand, plot offline" with a clean capture → organize
→ analyze pipeline.

```
  device (ESP32-P4 + FPGA + AD7606)
        │  USB-CDC: teleplot lines, command output, ===BURST_CSV=== blocks
        ▼
  cec_bench.py ........ owns the serial port (no dropped lines), sends commands,
        │               splits each capture into its own file + a run manifest
        ▼
  runs/run-<ts>/
    captures/NNN-<hhmmss>-<kind>.csv     one file per fastburst/autoburst/stream
    manifest.md                          every command + capture, with timestamps
    session.log                          raw terminal mirror
    analysis/                            (--analyze) metrics + plots, written for you
        ▲
        │
  cec_capture_analyze.py ... per-MODULE analysis: parses a capture, computes the
                             metrics that matter for THAT module, emits plots +
                             a metrics.md/.json. Reads the MEASURED sample rate
                             from the capture header (never the nominal label).
```

Keep using **TelePlot** for the live 5 Hz monitor — these tools own the **bursts**
and the **record**. This capture→organize→analyze path is the prototype of the
**Concierge** host layer (spec Appendix C); the per-module profiles seed its
analysis stage.

## One-time setup (your bench machine)

```
pip install pyserial numpy matplotlib
```

## A bench session

```
# 0. rebuild the FPGA bitstream + reflash the ESP if firmware changed.
# 1. start the host (Windows COM7 / Linux /dev/ttyACM0). --analyze auto-plots each capture.
python3 cec_bench.py --port COM7 --analyze --script "cal; rate; fastburst"
#    cal   -> zeroes the current channels at idle (run with the GPU idle)
#    rate  -> measures the TRUE native rate (~100k, not the 200k nominal) -- pins the FFT axis
#    fastburst -> a native-rate window; analyzer plots it
# 2. then induce a GPU load and, interactively, type:
autoburst 500 5
#    watches the stream; on a transient > ~0.75 A deviation it freezes the native
#    ring and dumps it. The host saves + analyzes each automatically.
quit
```

Everything lands in `runs/run-<timestamp>/` — captures, the manifest doc, and
(with `--analyze`) the metrics + plots. No manual extraction.

> The scripted sequence uses quiet-detection between commands (good for the
> deterministic `cal`/`rate`/`fastburst`/`stream` setup). `autoburst` waits for a
> transient *you* induce, so run it interactively.

## `cec_bench.py` — capture host

```
python3 cec_bench.py --port PORT [--analyze] [--module 12vhpwr]
                     [--script "cal; rate; fastburst"] [--run-dir DIR]
```
Owns the port (pyserial), mirrors the device output to your terminal, **and** in
the background splits each `===BURST_CSV===` block into `captures/`, appends to
`manifest.md`, and (`--analyze`) runs the analyzer per capture. Type commands as
you would in PuTTY; `quit` to stop.

## `cec_capture_analyze.py` — per-module analysis

```
python3 cec_capture_analyze.py CAPTURE.csv|putty.log [--module 12vhpwr]
                     [--rate HZ] [--index N] [--out DIR]
                     [--analog-rc-hz 15900 --analog-adc-hz 14000]
```
Parses every capture block in the input (a single file or a whole PuTTY log) and,
per the **module profile**, writes `*-time.png`, `*-fft.png`, and `*-metrics.md/.json`.

Each module asks a different question, so analysis is a **profile** (pluggable):

| module | what it computes |
|---|---|
| **`12vhpwr`** (done) | per-PIN imbalance (the melt metric, flagged under load), per-pin mean/peak/RMS, total, rail droop/ripple, load fundamental + floor (FFT at the real rate, analog-ceiling overlay) |
| `atx-24pin` (stub) | per-rail power + energy (INA228 accumulators), rail stability |
| `eps` / `pcie` (stub) | per-cable balance + total power + §6.13 transient events |

### Honest notes (they matter for the numbers)

- **Rate:** the analyzer uses the rate stamped in the capture header. If it says
  `(NOMINAL -- run rate)`, every frequency is flagged ~2× suspect — run `rate` on
  the device first (the conv+read FSM self-limits to ~100k at ÷4, not the 200k
  nominal). `--rate HZ` overrides.
- **Imbalance needs load:** at idle the mean pin current is ~0 (and dominated by
  uncalibrated INA offsets), so the imbalance % is undefined and reported as
  `no_load`. Run `cal`, then capture under GPU load for a real imbalance number.
- **FFT validity:** uniform only for `fastburst`/`autoburst` (FPGA-paced). The
  ESP-paced `burst` has a non-uniform time axis — time-domain + stats only.
- **Analog ceiling** defaults to the perfboard RC (15.9 kHz) × AD7606 (14 kHz) ≈
  9.6 kHz; adjust to your front-end with `--analog-rc-hz` / `--analog-adc-hz`.

## Next

When the firmware stamps a **self-describing header** (module id + channel roles,
on top of the measured rate it already stamps), the analyzer will auto-select the
profile from the capture instead of `--module`. That header + these profiles are
the handoff into Concierge.
