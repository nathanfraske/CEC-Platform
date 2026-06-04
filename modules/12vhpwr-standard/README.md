# 12VHPWR Standard module

Standard-tier **per-pin** sensing module for the **12VHPWR / 12V‑2×6** (PCIe CEM
5.x, 600 W GPU) connector. BOM target **$49** (100-qty). See spec
[§6.1](../../CEC-Platform-Ground-Truth-Spec.md).

| Item | Decision |
|---|---|
| Tier | Standard |
| MCU | ESP32-S3-MINI-1-N4R2 (locked; same MINI-1 as the other modules) |
| Hub link | RJ-45 8P8C shielded FTP, locking boot (J1) |
| Power connector | **12V‑2×6** (Molex Micro‑Fit+ / Amphenol Minitek, 16‑ckt: 6×+12V, 6×GND, 4 sideband). **J3 = board-mount right‑angle MALE header** (the PSU 12V‑2×6 cable plugs in). **J4 = captive OUTPUT pigtail** (a 12V‑2×6 cable soldered to the board, female plug → GPU). There is **no stock board‑mount female** 12V‑2×6 (it only exists as a cable plug), so this male‑in / soldered‑pigtail‑out is the minimal‑mated‑pair inline form (§2.8). |
| Sensing | **Per-pin**: six **INA240** current-sense amps, one across each +12V pin's **1 mΩ** shunt (RS1–6), feeding the ESP32-S3 ADC (IO1–6) directly — **no I²C sensing bus**. REF1/REF2 → GND (unidirectional forward). A **47k/10k divider** (R5/R6) brings the rail voltage into a 7th ADC channel. Accuracy ~±1% (see **OQ-8**). |
| Input filter | Per-channel **anti-alias / transient RC** on each INA240 input: matched **10 Ω** series Rf on IN+/IN− (RFH1–6 / RFL1–6) + a **470 nF** differential cap (CF1–6). **fc = 1/(2π·2·Rf·Cdiff) ≈ 16.9 kHz**, so the ~10 kHz GPU transients this pass targets pass at ~−1.3 dB and HF is rolled off ahead of the ADC. Rf held at 10 Ω + matched (TI's INA240 ceiling) → negligible gain/CMRR error. *(Optional ~47 nF common-mode caps deferred — OQ-8.)* |
| Sideband | The four **12V-2×6 sense pins** (13–16: SENSE0, SENSE1, CARD_PWR_STABLE, CARD_CBL_PRES#) pass straight through J3→J4 **and** each taps a free ESP32-S3 GPIO (IO8/9/11/12) via a **1 kΩ** series R (R10–R13), so firmware can read the cable's advertised power capability + present/stable state and report it over CAN. |
| Streaming | RS-485 **not populated** (Standard); pair 2 terminated module-side |
| DETECT | 2.2 kΩ precision (R1) — CAN-only code (§2.3, OQ-6 resolved); poke-and-ack tap R7 → IO10 (OQ-28) |
| Protection | No per-pin PoE/over-voltage (Standard/Pro, §2.4 v2.0); low-cap ESD diode D1 (PESD5V0S1UL) on DETECT pin 8 |
| Flash/debug | USB-C (J5) on the ESP32-S3 native USB + BOOT/RESET buttons (SW1/SW2); VBUS ORs into +5VSB via D2 (SS34); CC1/CC2 = 5.1 kΩ |
| BOM target | $49 (100-qty) |

> ⚠ **Lock the 12V‑2×6 footprint before fab.** `lib/cec.pretty/CEC_12V2x6_Horizontal`
> is an **approximate** land (3.0 mm pitch, 2×6 power + 4 sideband) built from
> public dims — the part-data hosts are network-blocked. Lock it to the **Molex
> 219116 (2191160161 right-angle) / Amphenol Minitek Pwr CEM‑5** datasheet (or
> import via `easyeda2kicad` on an open network), same as the Hub FTP jack.

## Open questions touching this board

- **OQ-8:** rail accuracy — the ESP32-S3 ADC path caps at ~±1%; accept, or add a
  local REF3033 (→ ~±0.3–0.5%).
- **OQ-11:** per-pin shunt part (1 mΩ, §6.4).
- *(OQ-6 module-ID encoding resolved — CAN-only = 2.2 kΩ.)*

## High-current 12V routing — per-pin interleave

See **`12vhpwr-routing-plan.png`** (regenerate with
`scripts/gen-hpwr-routing-plan.py`) — it carries the full to-placement top-down,
the four-wire Kelvin detail, the 4-layer stackup, and the width/via/stitch tables.
The 6×+12V pins carry ~**8.3 A each** (600 W ÷ 12 V = 50 A); **uneven sharing is
what melts these connectors**, so the module gives each pin its own 1 mΩ shunt +
INA240 and keeps the six 12V lanes symmetric so it adds no imbalance (and detects
any). Routing spec (laid in the GUI — the generator only sets placement):

- **Lanes / interleave:** the 2512 shunts (3.2 mm) won't fit the 3.0 mm pin pitch
  in one row, so they're **staggered into two rows** (RS1/3/5 / RS2/4/6) rotated
  90°. Each lane runs **straight down its pin column → in-line shunt → the matching
  J4 pad**, so all six lanes are **equal length (~77 mm) = balanced**.
- **Width (IPC-2221, 2 oz outer):** design to the **contact** rating, not nominal —
  Micro-Fit+ ≈ 9.5–13.5 A/contact → **13 A/pin**. Route each lane **2.5 mm on F.Cu,
  mirrored 2.5 mm on B.Cu, paralleled** (≈13 A at <10 °C rise; ≥3.0 mm if a B.Cu
  mirror is interrupted). **12V on both 2 oz outers; GND solid on In1 + In2** (1 oz,
  set BOTH inner pours to GND) so each lane is sandwiched by GND → low loop
  inductance. GND return = poured plane (never neck it).
- **Vias:** all current-carrying vias **0.5 mm drill / 0.9 mm pad (~2 A @10 °C,
  ~3 A @20 °C)**. Stitch F.Cu↔B.Cu **every ~5 mm down each lane**, with a **field of
  5–6** at every shunt terminal and **3–6 around each J3/J4 through-hole power pin**.
  Tie In1/In2/outer-GND on a **~5 mm grid** (denser ~3 mm ring at the connectors).
  Signal/sense vias 0.3/0.6 mm (~1 A) — avoid them on the Kelvin pair.
- **Kelvin sense (§6.8):** INA240A3 (gain 100) → 1 mΩ × 8.3 A × 100 = 0.83 V
  (13 A → 1.3 V). **Sense taps off the INNER shunt-terminal edges** (excludes pad/
  solder/trace IR drop); force current on the OUTER ends. The pair carries ~no
  current → run it **thin (0.20–0.25 mm)** as a **tight matched-length pair over the
  In1 GND plane**, kept off / perpendicular to the 12V lanes, with the RC input
  filter (RFH/RFL 10 Ω + CF 470 nF) placed **at the INA pins**. A GND guard-via
  fence alongside the pair is cheap insurance (the 12V here is essentially DC, so
  coupling is low, but the signal is only 8–13 mV).

## Status

Schematic generated by `scripts/gen-modules.py`; the initial PCB floorplan by
`scripts/gen-module-pcb.py` (one-shot — hand-maintained in the GUI afterwards):
4-layer, **2 oz outer / 1 oz inner**, **slim ~44 × 92 mm** inline stick (tightened
from 46 × 104) — the 12V‑2×6 power path runs down the LEFT (J3 IN top → 6 per-pin
shunts + INA240 → J4 pigtail OUT bottom), the ESP + CAN + LDO + flash front end +
RJ-45/USB-C fill the RIGHT. The **plug connectors overhang their board edge** so a
cable seats without the board fouling the plug overmold while the solder pads stay
on-board for support: **J3** (PSU 12V‑2×6 IN) is pushed up so its right-angle
shroud/mouth (≈9.5 mm deep, footprint-local −y) overhangs the **top** edge by ~3 mm
with the 12V pads ~6.5 mm in; **J1** (RJ-45) and **J5** (USB-C) overhang the
**right** edge. **J4 keeps J3's rotation (not 180°)** so all six +12V lanes run
straight + equal-length (uneven sharing melts 12VHPWR); it's a captive soldered
pigtail, so its wires just exit the bottom edge. Two M3 mounts sit above/below the
14 mm ESP on the clear right edge (the 12V‑2×6 connectors fill the left corners).
**Component values are now on F.SilkS** (the generator was defaulting them to the
footprint name on the non-plotted F.Fab layer). **DRAFT** marker present; DRC is
clean of structural hits (0 copper shorts / clearance / courtyard / edge) — the
remaining silk-overlap warnings are the dense values-on-silk + tight placement, a
GUI silk-refinement task. Next in GUI: *Update PCB from Schematic* to pull the
remaining passives (decoupling, the 18 INA input-filter R/C — RFH/RFL/CF — and the
4 sideband tap resistors R10–R13), fan the 6 shunts out from the 3 mm connector
pitch, then place/route + pour (§6.8 Kelvin, §6.7 high-current). Project-local
library tables point at `../../lib` via `${KIPRJMOD}`.
