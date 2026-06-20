# CEC Hub Standard prototype (CAN bring-up + CAN-OTA bridge)

A bench prototype on the **Lonely Binary ESP32-S3-WROOM-1 N16R8** + a
**SN65HVD230** CAN transceiver. Nothing else is attached — this is purely a
CAN node to prove module→Hub signalling end to end, and a bridge for flashing
a module over CAN. It is **not** the production Hub firmware (no port
management, host USB protocol, LEDs, or power management).

## Wiring

| Signal | ESP32-S3 | SN65HVD230 |
|---|---|---|
| CAN TX | IO5 | D (pin 1) |
| CAN RX | IO4 | R (pin 4) |
| 3V3 / GND | 3V3 / GND | VCC / GND |
| Rs (slope) | — | pin 8 → GND for 500k; via 10k for 125k (breakout default) |

Bus: **CAN_H/CAN_L** to the 24-pin's TJA1051T/3, **120 Ω termination at both
ends**, **both nodes at the same bitrate** (125 kbps default; see below).

Console is the native USB Serial/JTAG (the one USB-C). It carries the
telemetry log, the TelePlot series, and the `ota`/`caninfo` commands.

## Bitrate

`CONFIG_CEC_CAN_BITRATE_BPS = 125000` (sdkconfig.defaults). 125k is the
reliable bench rate — the SN65HVD230 breakout is slope-controlled (Rs via 10k
to GND) and bus-offs at 500k unless **Rs is bridged straight to GND**. 500k is
the platform spec target. The 24-pin must use the **same** rate.

## Two jobs

### 1. Multi-module aggregator (display_task)
Brings TWAI up in **normal mode** so it **ACKs the bus** — which is what lets a
module's transmits complete (a lone transmitter with no ACKer bus-offs). Then
it **consolidates up to `CEC_MAX_MODULES` (4) modules** on the one bus and
forwards everything over USB to the host for analysis.

Each module sends the 3-frame telemetry burst (`cec_telem.h`) in its own
**CAN-ID block** (so the bus is collision-free with 4 ports):

| Traffic | CAN ID |
|---|---|
| anomaly / event | `0x100 + module_id` |
| poke-ack MOVED | `0x120` |
| **telemetry** | **`0x200 + instance*0x10 + sub`** (sub: 0 RAILS_V, 1 RAILS_I, 2 STATUS) |
| CAN-OTA | `0x340–0x342` |

So port 0 = `0x200–0x202`, port 1 = `0x210–0x212`, … The Hub demuxes by
instance into a per-port table, and on each module's STATUS frame emits the
consolidated output two ways:

- **TelePlot**, namespaced per port: `m0_12v_v`, `m0_12v_i`, …, `m1_cbl0_i`, …
  (channel labels are module-type-specific — 12v/5v/3v3/5vsb for the ATX24,
  cbl0/cbl1 for the EPS, ch0..3 otherwise).
- **A parseable CSV record line per update**, greppable by its prefix:

  ```
  # CECTLM,ts_ms,port,type,seq,v0,i0,v1,i1,v2,i2,v3,i3,temp_c,p_w,flags
  CECTLM,12345,0,0x01,42,12.01,5.20,5.00,1.10,3.30,2.40,5.01,0.30,41,180.5,0x03
  ```

A 1 Hz human summary lists every active port + the aggregate power, and a port
that goes quiet past `CEC_HUB_MODULE_TIMEOUT_MS` is reported dropped. The
`status` flags byte is module-type-defined (ATX24: PS_ON/PWR_OK/SHUTTING_DOWN;
EPS: the `CEC_FLAG_*` over-current/fault bits).

> The 24-pin is port 0 and the EPS defaults to port 1 (`CEC_DEFAULT_MODULE_ID`);
> set each module's `module_id` distinct (0..3) for its Hub port.

### 2. CAN-OTA bridge (`ota` command)
Flashes the 24-pin over CAN. ESP32-S3 has **no ROM CAN bootloader**, so this is
an **application OTA**: the running 24-pin app writes the streamed image to its
inactive OTA slot (`esp_ota_*`), validates it, flips the boot selector, and
reboots. The protocol lives in `firmware/esp/components/cec_comms/cec_canota.*`
(one source of truth, shared sender/receiver; stop-and-wait, CRC32-checked).

Data path: **host —(USB-CDC hex lines)→ Hub —(CAN)→ 24-pin**. The Hub buffers
the whole image in its 8 MB PSRAM, verifies CRC32, then streams it.

#### One-time: convert the 24-pin to OTA partitions
The 24-pin moved from a single-`factory` to an OTA layout (`ota_0`/`ota_1`/
`otadata`), so it needs **one USB flash** to convert (offsets moved):

```sh
cd firmware/esp/proto/atx-24pin
idf.py -p <24pin_port> flash      # USB, once; lays down the new partition table
```

#### Flash the Hub (once)
```sh
cd firmware/esp/proto/hub-standard
idf.py -p <hub_port> flash
```

#### Then flash the 24-pin over CAN, repeatedly
Build a new 24-pin image (e.g. bump the version string so you can see it land),
then push it through the Hub:

```sh
cd firmware/esp/proto/atx-24pin && idf.py build
python3 firmware/tools/can_ota_push.py <hub_port> \
        firmware/esp/proto/atx-24pin/build/cec_24pin.bin
```

`<hub_port>` is the **Hub's** USB port (not the 24-pin's). The script computes
size + CRC32, drives the Hub's `ota` command, streams the hex, and relays the
Hub's progress. At 125 kbps a ~0.3 MB image is ~2 min (stop-and-wait). On
success the 24-pin prints `OTA complete … booting 'ota_1'` and reboots; a bad
image is rejected at CRC/validation (and the bootloader rolls back a broken
image that never marks itself valid).

Manual alternative (no host script): in the Hub console type
`ota <size> <crc32hex>` then paste the image as hex lines.

## DETECT analog sense + poke-and-ack (`detect` command)

The DETECT line is RJ-45 pin 8. With the full RJ-45 cable it reaches the Hub
end already, so only a small Hub-side rig is needed (defaults in
`cec_config.h`, change to suit):

| Part | Connection |
|---|---|
| 10 kΩ pull-up | 3V3 → DETECT node (the Hub's pull-up) |
| ADC read | DETECT node → **IO1** (ADC1_CH0) — reads the divider |
| Poke driver | DETECT node → **IO2** (idle hi-Z; pulses HIGH to perturb) |

**Analog sense (works on this bench).** The 24-pin's pin-8 carries a 2.2 kΩ to
GND; against the Hub's 10 kΩ pull-up that's ~0.60 V = the **CAN-only** comm
class. The Hub reads + classifies it (spec §2.3): open ≈ 3.3 V (absent),
short ≈ 0 V (fault), 2.2 k / 4.7 k / 10 k / 22 k / 47 k codes in between. Read
at boot and via the `detect` command.

**Poke-and-ack + safe fallback.** `detect` reads the class, then *pokes* the
line (4 rising edges) and waits ~200 ms for a module to **ack over CAN** (a
`MOVED` frame, ID 0x120). A module with a high-Z pin-8 GPIO tap (EPS/PCIe do,
on IO10) senses the edges and acks, binding its identity to this port.

The **24-pin has no tap** — its MINI-1 GPIO pads are under the shroud, so none
can be added — so it **never acks**. That is the designed **safe fallback**:
the Hub times out and reports the port as *legacy / known-but-unbound* (still
known from CAN, still read for comm class from the divider). So on this bench
`detect` shows the **comm class read working** and the **fallback working**;
the positive ack path is exercised later on an EPS/PCIe (which can tap). The
module-side responder firmware is built and shared (`cec_pokeack`), started
inert on the 24-pin (`CEC_POKEACK_TAP_NONE`).

OQ-28 (sense method) is implemented as the spec-favored **digital edge** read.
