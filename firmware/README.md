# CEC-Platform firmware tree

Drop this directory into `CEC-Platform/firmware/`. One repo, one SHA, one
coherent hardware-plus-firmware state: pin maps live next to the KiCad
projects that define them, and fab-gate punchlists pin both at once.

## Layout and the criss-cross mechanics

```
firmware/
  rtl/
    common/          shared Verilog; consumed by relative path from any target
      cec_spi_slave.v
    12vhpwr-proto/        12VHPWR perfboard prototype (GW5A-25, Tang Primer 25K dock)
      top.v          acquisition FSM + ESP link
      tb_top.v       self-checking sim (AD7606 stub + ESP master stub)
      12vhpwr-proto.cst   dock 2x20 GPIO field pin map
    fpgamax/         (later) production target; reuses rtl/common
  esp/
    components/      shared ESP-IDF components; every app sees them via
                     EXTRA_COMPONENT_DIRS in its project CMakeLists
    proto/           PROTOTYPE apps (dev-board/perfboard rigs):
      12vhpwr/         ESP32-P4-NANO readout app for this prototype
      atx-24pin/       ESP32-S3 dev-board rig (24-pin)
      eps-8pin/        ESP32-S3 dev-board rig (EPS)
    (flat esp/<name> is reserved for production apps matching modules/<name>)
  tools/             host-side Python (decoders, cal) as they appear
```

RTL criss-cross is file-list based: targets reference `../common/*.v`
directly, and the Gowin project for each target adds the same files. ESP
criss-cross is the IDF component system: drop a component under
`esp/components/<name>/` with its own CMakeLists and every app picks it up
with no submodules, no packaging, no version skew. The first shared pieces to
extract as real components once v0 stabilizes: the frame protocol
(header/seq/payload) and the calibration math.

The AGPL seam stays architectural: nothing here links against
cec-support-agent. Telemetry crosses to the diagnostic pipeline as serial
data and log artifacts only.

## 12vhpwr-proto v0: what it does

Fabric (verified by simulation in this tree): 200 ns RESET pulse after POR,
CONVST paced at 1 kSPS (parameter), BUSY tracked through 2FF sync, 64-clock
dual-line serial read at 12.5 MHz (V1-V4 off D7, V5-V8 off D8, capture
late-high, launch on falling per the AD7606 serial interface), 8x16 frame
latch guarded against tearing while the ESP is mid-read, and an oversampled
mode-0 SPI slave presenting 18 bytes: `0xA5, seq, V1..V8` MSB first. DRDY is
level-high while an unread frame waits and clears on a completed read.

ESP32-P4: SPI master at 4 MHz (keep at or under 5 MHz, the slave is
oversampled at 50 MHz), polls DRDY, pulls a frame, checks the header, prints
all eight channels as raw codes and volts at 152.59 uV/LSB, about 5 Hz.

## Build and run

Sim (CI-able, no vendor tools):

    cd rtl/12vhpwr-proto
    iverilog -g2012 -o tb tb_top.v top.v cec_boxcar_decim.v cec_native_detect.v ../common/cec_spi_slave.v && vvp tb
    # expect: PASS: decimator average, LIVE seq, BURST ring, STREAM dropcount

Bitstream: Gowin EDA V1.9.9Beta-4 or newer (Yosys 0.33 does not target GW5A).
New project, device GW5A-LV25MG121, add `top.v`, `cec_boxcar_decim.v`,
`../common/cec_spi_slave.v`, and `12vhpwr-proto.cst`, synthesize, place-route,
program the dock over its USB-C.

ESP app:

    cd esp/proto/12vhpwr
    idf.py set-target esp32p4
    idf.py build flash monitor

IDF v5.3 or newer for ESP32-P4 support.

## Acceptance: bring-up step 3

With the module powered, dock programmed, ESP flashed, grounds common via
the T15 Y:

1. BUSY pulses about 4 us at the CONVST cadence (OS = 000 as built).
2. Console streams frames with an advancing seq and a stable 0xA5 header.
3. Screw-bus inputs jumpered to the screw-bus GND read within a few LSB of
   code 0.
4. An AA battery across one input reads near code 9800 (1.5 V / 152.59 uV);
   sign flips when reversed.

Symptom decoder lives in the build doc (section 13) and the session notes:
parallel-mode silence on D7, BUSY-width oddities, half/double codes, and
sane/garbage alternation each point at one specific strap.

## CI sketch (GitHub Actions, path-filtered)

```yaml
on:
  push:
    paths: ['firmware/**']
jobs:
  rtl-sim:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: sudo apt-get update && sudo apt-get install -y iverilog
      - run: |
          cd firmware/rtl/12vhpwr-proto
          iverilog -g2012 -o tb tb_top.v top.v cec_boxcar_decim.v cec_native_detect.v ../common/cec_spi_slave.v
          vvp tb | tee sim.log
          grep -q '^PASS' sim.log
  esp-build:
    runs-on: ubuntu-latest
    container: espressif/idf:v5.3
    steps:
      - uses: actions/checkout@v4
      - run: |
          cd firmware/esp/proto/12vhpwr
          idf.py set-target esp32p4 build
```

Hardware checks keep their own workflows with their own path filters; a
firmware push never rebuilds the KiCad gates and vice versa.

## Honest status

The RTL is simulation-verified in this tree against a behavioral AD7606 and
a behavioral ESP master. The ESP app follows current IDF v5 master-driver
API but has not been compiled here; expect at most include-level fixups on
first build. Timing closure on the GW5A is trivial at these clock rates but
is the Gowin tool's word, not the simulator's.
