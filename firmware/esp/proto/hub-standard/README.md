# CEC Hub Standard prototype (CAN bring-up + CAN-OTA bridge)

A bench prototype on the **Lonely Binary ESP32-S3-WROOM-1 N16R8** + a
**SN65HVD230** CAN transceiver. It is the Hub control plane: a 4-port
multi-module **aggregator** (forwards telemetry to the host over USB), a
**CAN-OTA bridge** (re-flash modules over CAN), 4-port **DETECT poke-and-ack**
port mapping, and **cross-module FREEZE co-capture**. It is wired to the real
Hub board's pin map (see below). Still missing vs. the production Hub: the
SK6812 status LEDs and the §2.9 subsystem-power management.

## Wiring

| Signal | ESP32-S3 | SN65HVD230 |
|---|---|---|
| CAN TX | IO17 | D (pin 1) |
| CAN RX | IO18 | R (pin 4) |
| 3V3 / GND | 3V3 / GND | VCC / GND |
| Rs (slope) | — | pin 8 → GND for 500k; via 10k for 125k (breakout default) |

Plus the 4 DETECT lines on **IO4–IO7** (one per port, each with a 10 kΩ pull-up
to 3V3) — see the DETECT section below.

Bus: **CAN_H/CAN_L** to each module's TJA1051T/3, **120 Ω termination at both
ends**, **all nodes at the same bitrate** (125 kbps default; see below).

Console is the native USB Serial/JTAG (the one USB-C). It carries the telemetry
log + CSV, the TelePlot series, and the `ota`/`caninfo`/`detect`/`freeze`/`rearm`
commands.

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

## DETECT analog sense + poke-and-ack — 4 ports (`detect` command)

Mirrors the real Hub Standard board (`hubs/hub-standard`): each of the 4 ports'
DETECT line (RJ-45 pin 8, carried by the cable) goes to **one ESP32 ADC1 pin**
with its own external **10 kΩ pull-up to 3V3**. That one pin does both jobs —
ADC input to read the divider (comm class), and a momentary push-pull output to
poke. Wire the dev board per the board map:

| Hub port | Jack | DETECT pin | ADC |
|---|---|---|---|
| 0 | J2 | **IO4** | ADC1_CH3 |
| 1 | J3 | **IO5** | ADC1_CH4 |
| 2 | J4 | **IO6** | ADC1_CH5 |
| 3 | J5 | **IO7** | ADC1_CH6 |

(CAN moved to **IO17/IO18** to free IO4/IO5 for DETECT — the real-board pins.
Pin map in `cec_config.h` / `sdkconfig.defaults`.)

**Analog sense.** A module's pin-8 carries a code resistor to GND; against the
Hub's 10 kΩ pull-up the divider encodes the comm class (spec §2.3): 2.2 kΩ →
~0.60 V CAN-only, 4.7 kΩ → ~1.06 V CAN+RS485, 10 kΩ → ~1.65 V CAN+100BT1, two
reserved; open ≈ 3.3 V (empty), short ≈ 0 V (fault). Read per port at boot.

**Poke-and-ack maps each port.** `detect` walks all 4 ports: it reads each
port's class, then *pokes* that one line (4 rising edges) and waits ~200 ms for
the module on it to **ack over CAN** (a `MOVED` frame, ID 0x120). Poking one
port at a time makes the ack unambiguous, so the Hub binds **physical port →
module** and prints the map:

```
DETECT port map (4 ports):
  port0:  595 mV  CAN-only(2.2k)    -> legacy (no poke ack; known-but-unbound)
  port1: 1055 mV  CAN+RS485(4.7k)   -> EPS (id 1) BOUND
  port2: 3300 mV  absent(open)      (empty)
  port3:  595 mV  CAN-only(2.2k)    -> 12VHPWR (id 3) BOUND
```

A module with a high-Z pin-8 GPIO tap (the EPS/PCIe/12VHPWR scaffolds tap IO10)
senses the poke and acks. The **24-pin has no tap** (MINI-1 pads under the
shroud) so it never acks — the designed **safe fallback**: the Hub still reads
its comm class and reports the port *legacy / known-but-unbound*. OQ-28 (sense
method) is the spec-favored **digital edge** read.

## Cross-module FREEZE co-capture (`freeze` / `rearm`, §6.10)

Any one module's trip freezes **every** module's capture ring on a common
timeline, so a single rail's event captures the whole system. It rides CAN, no
spare-pin hardware (`cec_freeze`):

1. The tripping node freezes its own ring, then broadcasts a high-priority
   **FREEZE** frame (`0x010` — lowest ID, wins arbitration, lands first).
2. Every other node sees it in its **CAN RX ISR** and timestamps the instant
   there (the alignment point), then freezes its ring in a task. Alignment is
   within ~1 bit-time (µs at 500k); the task latency is absorbed by the modules'
   2 s pre-roll.
3. Each module dumps its frozen window (the existing burst dump over its own
   USB); the host overlays them on the FREEZE instant.
4. **RE-ARM** (`0x011`) re-arms everyone after read-out.

**Hub commands:**
- `freeze` — broadcast a system-wide FREEZE (every module freezes + dumps). The
  Hub originates with id `0xFE`.
- `rearm` — broadcast RE-ARM.

A **module-originated** FREEZE (the 24-pin/EPS on a local anomaly; the 12VHPWR
scaffold on a per-pin imbalance) lands at the Hub too and is surfaced to the
host as a `CECFRZ,<ts_ms>,<origin_port>,<cause>` line, so a host capture can be
aligned across every module on the FREEZE instant.

**Bench test:** with the 24-pin (and/or EPS) on the bus, type `freeze` on the
Hub → each module logs `FROZEN by port 0xFE (manual)` and fires a `cocapture`
burst dump on its own USB. Then `rearm`. Trip a real anomaly on the 24-pin and
the Hub prints a `CECFRZ` line while the other modules dump in sync.

The scaffolds (no ring buffer yet) participate with a log only; the 24-pin and
EPS do the real `cec_capture` dump.
