# CEC PCIe 8-pin 3-port module — firmware scaffold

ESP32-S3-MINI-1 interposer; one INA238 per cable over I2C, **3 cables** (the
spec upper bound), 0.5 mOhm shunts; plus the §6.13 per-cable transient-detection
front end. Spec §6.1/§6.4/§6.13.

Identical to the 2-port SKU but for the third cable — `main.c` is shared
verbatim (loops over `PCIE_NUM_CABLES`); only `cec_config.h` differs (cable
count, the third INA238 address, the third DET pin).

## Status: scaffold (ready for sensor bring-up)
Builds, enumerates on the Hub, and exercises the aggregator with **placeholder**
data. Fill in `read_sensors()` in `main.c` — the per-cable INA238 reads + the
§6.13 DET latches. Runtime, CAN telemetry, CAN-OTA, and poke-ack are done via
the shared `cec_module` helper.

## What it sends over CAN
Per-cable current + bus voltage on channels `cbl0`/`cbl1`/`cbl2`, total power,
temp, at 5 Hz (`cec_telem`).

## Identity
`module_id` is the Hub port (0..3); default **2** (shares the "PCIe port" role
with the 2-port SKU — a hub carries one PCIe SKU). Poke-and-ack can rebind it.

## Bring-up
```sh
# 1. One-time USB flash (lays down the OTA partition layout)
idf.py -p <port> flash monitor
# 2. Thereafter, re-flash over CAN through the Hub:
python3 firmware/tools/can_ota_push.py <hub_port> build/cec_pcie_3port.bin
```

**Verify against the schematic:** CAN TX/RX (placeholder IO17/IO18), the I2C
pins + the three INA238 addresses, the three §6.13 DET pins, and the poke-ack
tap (`CEC_CFG_DETECT_TAP_GPIO`, default IO10) — all in `main/cec_config.h`.
