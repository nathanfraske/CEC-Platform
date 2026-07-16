# CEC 12VHPWR Standard module — firmware scaffold

ESP32-S3-MINI-1; six INA240 per-pin current-sense amps into the S3 ADC + a
47k/10k rail divider + NTCs (spec §6.1/§6.4). **No FPGA** — the GW5A/AD7606
fast path is Pro-tier and up.

## Status: scaffold (ready for sensor bring-up)
Builds, enumerates on the Hub, and exercises the aggregator with **placeholder**
data. The only per-board code to fill in is `read_sensors()` in `main.c` (the
marked block) — wire the INA240 ADC reads, the rail divider, and the NTC. The
runtime, CAN telemetry, CAN-OTA, and poke-ack are already done via the shared
`cec_module` helper.

## What it sends over CAN
The 6 per-pin currents are folded into the 4-channel telemetry summary
(`cec_telem`): `rail` (12V V + total current), `imax`, `imin`, `spread`, plus
temp and total power, at 5 Hz. The **10 kHz per-pin detail stays local** — the
S3 SAR is ~83 kSps shared (~12 kSps/ch for 7 channels ≈ 6 kHz Nyquist), so the
fast content is grabbed by `capture_burst()` (a §6.10 stub) on a trigger, not
streamed. An imbalance (a pin >40% over the per-pin mean) sets a flag and fires
the burst — the §6.13 detection thesis (the electrical outlier leads the
thermal one).

## Identity
`module_id` is the Hub port (0..3); default **3** (24-pin=0, EPS=1, PCIe=2,
12VHPWR=3 makes a clean 4-module bench). Poke-and-ack can rebind it.

## Bring-up
```sh
# 1. One-time USB flash (lays down the OTA partition layout)
idf.py -p <port> flash monitor
# 2. Thereafter, re-flash over CAN through the Hub (see proto/hub-standard):
python3 firmware/tools/can_ota_push.py <hub_port> build/cec_12vhpwr_standard.bin
```

**Verify against the schematic before bring-up:** the CAN TX/RX pins
(placeholder IO17/IO18), the INA240 ADC channels, the rail-divider pin, the NTC
pins, and the poke-ack DETECT tap (`CEC_CFG_DETECT_TAP_GPIO`, default IO10) —
all in `main/cec_config.h`.
