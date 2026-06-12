# 12VHPWR prototype — FPGA (GW5A) bring-up

The acquisition fabric for the 12VHPWR prototype: a Gowin **GW5A-25** on a
**Tang Primer 25K** dock, reading an **AD7606** (8-ch, serial mode) and
presenting frames to the ESP32-P4 over SPI. This directory is the RTL +
pin constraints; the ESP readout app is [`../../esp/proto/12vhpwr`](../../esp/proto/12vhpwr).

> **Two chips, two toolchains.** The bitstream is built **by hand in
> Gowin EDA** (closed vendor GUI — there is no open headless flow for
> GW5A; Yosys 0.33 doesn't target it). The repo carries the *source* you
> feed Gowin, plus an `iverilog` **simulation** gate (CI + the build
> gate) that proves the *logic*. The bitstream itself is your manual
> step, every time.

## Files

| File | Role |
|---|---|
| `top.v` | acquisition FSM + ESP SPI-slave link (the synthesizable top) |
| `../common/cec_spi_slave.v` | shared oversampled SPI slave (FPGA-Max reuses it) |
| `tb_top.v` | self-checking testbench (behavioral AD7606 + ESP master) |
| `12vhpwr-proto.cst` | dock 2×20 GPIO-field pin constraints (renamed from v0 `proto12v.cst`; ball map unchanged) |

## Prerequisites (one-time)

1. **Gowin EDA** — *Education* (free) or *Standard* edition, **V1.9.9Beta-4
   or newer** (older builds don't target GW5A). Download from gowin.com;
   it needs a free license file (the Education license is node-locked to
   your MAC — request it from Gowin, drops in under Help → License).
2. The Tang Primer 25K dock + its **USB-C** (carries both the programmer
   and the dock's power).
3. The ESP32-P4-Module-DEV-KIT with its own USB-C (for the readout app —
   separate cable, separate chip).

## Build the bitstream (Gowin EDA)

1. **File → New → FPGA Design Project.** Device: **GW5A-LV25MG121C8/I7**
   (part `GW5A-25`, package MG121). Pick the exact speed grade your dock
   carries if prompted; logic is identical for this design.
2. **Add Files:** `top.v`, `../common/cec_spi_slave.v`, and
   `12vhpwr-proto.cst`. (Add the `.v` by relative path or copy them in —
   either is fine; keep `cec_spi_slave.v` shared if you can.)
3. **Set `top` as the top module** (Project → Configuration, or it
   auto-detects since the module is named `top`).
4. **Synthesize → Place & Route.** Timing closes trivially at these
   clocks; if PnR reports an unconstrained-clock warning on `clk50`,
   it's cosmetic for a 50 MHz design (add a 50 MHz clock constraint to
   silence it).
5. **Program:** Programmer → scan → load the generated `.fs` to **SRAM**
   for bench iteration (volatile, fastest), or **embedded flash** to
   make it survive a power cycle. Program over the dock's USB-C.

The 8 top-level I/O are fully constrained — verified: every `top.v` port
has exactly one `IO_LOC` and there are no stray constraints, so PnR won't
stop on an unassigned pin.

## Wiring (verified against both `12vhpwr-proto.cst` and the ESP app)

>  **ESP-side pins RE-MAPPED (bench finding 2026-06-12, resolved).** The v0
>  ESP GPIO map (20–24) collided with the P4's flash/PSRAM MSPI bus
>  (IO_MUX: GPIO22=DBG_PSRAM_CK, 23=DBG_PSRAM_CS, …) and **hung the P4** at
>  `gpio_config` — it was simulation-verified only, never run on silicon.
>  The link now uses **GPIO 1–5** (plain-GPIO-only, no flash/PSRAM/Ethernet/
>  console/strap function, all exposed on the DEV-KIT header). The FPGA-ball
>  ↔ dock-field side and the AD7606 table are unchanged — only which ESP
>  header pin each jumper lands on moved. See `firmware/FOLLOWUPS.md`.

**ESP32-P4 ↔ GW5A link** — these five must be jumpered from the
ESP32-P4-Module-DEV-KIT GPIO header → dock field. The ESP-app GPIO and
the FPGA ball were cross-checked and **agree on every signal**:

| FPGA signal | dock ball | dock field silk | ESP P4 GPIO | direction |
|---|---|---|---|---|
| `esp_sclk` | F2 | T13 | GPIO1 | ESP → FPGA |
| `esp_mosi` | B2 | T14 | GPIO2 | ESP → FPGA (unused in v0) |
| `esp_miso` | C2 | B14 | GPIO3 | FPGA → ESP |
| `esp_cs_n` | F1 | B13 | GPIO4 | ESP → FPGA |
| `esp_drdy` | A1 | B12 | GPIO5 | FPGA → ESP |

**GW5A ↔ AD7606** (per the `.cst` + doc §9; the AD7606 module silk is
RST/CA/CS/RD/BUSY/D7/D8):

| FPGA signal | dock ball | AD7606 silk | direction |
|---|---|---|---|
| `adc_reset`  | F7  | RST   | FPGA → ADC |
| `adc_convst` | J8  | CA (CONVST A) | FPGA → ADC |
| `adc_cs_n`   | L9  | CS    | FPGA → ADC |
| `adc_sclk`   | L10 | RD/SCLK | FPGA → ADC |
| `adc_busy`   | K8  | BUSY  | ADC → FPGA |
| `adc_douta`  | K9  | D7 (DOUTA, V1–V4) | ADC → FPGA |
| `adc_doutb`  | K10 | D8 (DOUTB, V5–V8) | ADC → FPGA |
| `clk50`      | E2  | (dock 50 MHz osc) | → FPGA |

**Grounds common** between the P4 DEV-KIT, the dock, and the AD7606 module
(the v0 build used the T15 Y-ground). AD7606 **OS straps = 000** (no
oversampling, ±5 V, internal ref) — the FSM's 64-clock serial read
assumes it.

## Bench bring-up sequence

```
1. Program the GW5A first  (so it's pacing CONVST and can raise DRDY).
2. Flash + monitor the ESP:
     cd ../../esp/proto/12vhpwr
     idf.py set-target esp32p4 build flash monitor
   Expect: "12vhpwr-proto v0: waiting on DRDY"  then  seq lines ~5 Hz.
```

The app ships the **v0 raw console loop by default**
(`CONFIG_CEC_PROTO_RAW_CONSOLE=y`) — the exact path the simulation
verified. Its `printf` output is mirrored to the P4's USB-C (UART0
primary + USB-Serial-JTAG secondary console), so `idf.py monitor` shows
the stream. (The CLI `frame` command's *input* rides UART0 under this
default; for typing commands over USB-C, set
`CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` in the app's `sdkconfig.defaults`
after step 3 below — leave it as-is for the first smoke.)

## Acceptance (v0 bring-up steps)

1. **BUSY** pulses ~4 µs at the CONVST cadence (OS=000 as built).
2. Console streams frames with an **advancing `seq`** and a stable
   **`0xA5`** header.
3. Screw-bus inputs **jumpered to screw-bus GND** read within a few LSB
   of **code 0**.
4. An **AA battery** across one input reads near **code 9800**
   (1.5 V ÷ 152.59 µV/LSB); the sign flips when reversed.

## Symptom → cause

| Symptom | Likely cause |
|---|---|
| `waiting on DRDY` forever | DRDY not wired (A1↔GPIO5), or the FPGA isn't programmed / not pacing (check BUSY on a scope) |
| `bad header 0x..` (not 0xA5) | SPI bit-alignment — CS/SCLK swap, or SPI clock too fast (keep ≤ 5 MHz; the slave needs fabric ≥ 5× SPI, and fabric is 50 MHz so ≤ 10 MHz is the hard ceiling) |
| `seq` frozen | FSM stuck — BUSY never asserting (CONVST or BUSY mis-wired), or grounds not common |
| All channels ≈ same garbage | DOUTA/DOUTB (D7/D8) swapped or one not wired; or OS straps ≠ 000 (changes the serial frame length) |
| Half/double codes | SCLK count or edge phase off — scope `adc_sclk` vs `adc_busy`; this is the one thing the sim can't vouch for (see below) |

## What the simulation does and doesn't prove

`iverilog -g2012 -o tb tb_top.v top.v ../common/cec_spi_slave.v && vvp tb`
(run by CI + the build gate; expect `PASS`) exercises the FSM, the frame
latch, the DRDY handshake, and the ESP SPI slave against **behavioral**
AD7606 and ESP-master models. It proves the *logic and protocol*. It
does **not** prove (a) the real AD7606's serial-interface *timing*
against this FSM — scope `adc_sclk`/`adc_douta` first if codes look
wrong — or (b) GW5A timing closure, which is the Gowin tool's word, not
the simulator's. Both are bench-confirmed, not sim-confirmed.
