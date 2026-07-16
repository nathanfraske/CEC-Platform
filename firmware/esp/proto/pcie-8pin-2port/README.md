# CEC PCIe 8-pin 2-port module — firmware scaffold

ESP32-S3-MINI-1 interposer; one INA238 per cable over I2C (per-cable
granularity), **2 cables**, 0.5 mOhm shunts; plus the §6.13 per-cable
transient-detection front end (INA181 + comparator → firmware threshold →
FREEZE). Spec §6.1/§6.4/§6.13.

## Status: scaffold (ready for sensor bring-up)
Builds, enumerates on the Hub, and exercises the aggregator with **placeholder**
data. Fill in `read_sensors()` in `main.c` (the marked block) — the per-cable
INA238 bus-voltage + current reads and the §6.13 DET latches. The runtime, CAN
telemetry, CAN-OTA, and poke-ack are done via the shared `cec_module` helper.
`main.c` is shared verbatim with the 3-port SKU; only `cec_config.h` differs.

## What it sends over CAN
Per-cable current + bus voltage on channels `cbl0`/`cbl1`, total power, temp, at
5 Hz (`cec_telem`). The §6.13 detection flags ride the status byte.

## Identity
`module_id` is the Hub port (0..3); default **2** (24-pin=0, EPS=1, PCIe=2,
12VHPWR=3). Poke-and-ack can rebind it.

## Bring-up
```sh
# 1. One-time USB flash (lays down the OTA partition layout)
idf.py -p <port> flash monitor
# 2. Thereafter, re-flash over CAN through the Hub:
python3 firmware/tools/can_ota_push.py <hub_port> build/cec_pcie_2port.bin
```

**Verify against the schematic:** CAN TX/RX (placeholder IO17/IO18; the v3.10
spec puts the C6 CAN on IO20/21, but the as-built board is S3), the I2C pins +
INA238 addresses, the §6.13 DET/threshold pins, and the poke-ack tap
(`CEC_CFG_DETECT_TAP_GPIO`, default IO10) — all in `main/cec_config.h`.
