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

> ✅ **12V‑2×6 footprint LOCKED (2026-06-05).** `lib/cec.pretty/CEC_12V2x6_Horizontal`
> is now the **official Molex footprint** — Molex **219116** PCIe CEM5 12V‑2×6
> right‑angle THT header, MPN **2191161161** (T&R) = **2191160161** (tray), doc
> 2191160001‑SD — vendored from Molex's KiCad export, pads remapped to the schematic
> numbering: **1–6 = +12V** (row adjacent to the signal pins), **7–12 = GND** (outer
> row), **13–16 = sideband S1–S4**. Real geometry: 3 mm pitch, power drill 1.07 mm /
> 1.52 mm pad, signal drill 0.61 mm / 1.14 mm pad; **9.2 A/power pin**, 12 V.
>
> Two follow‑ups: **(1) safety —** the connector is symmetric (both rows are just
> "POWER"); +12V vs GND is the system/CEM assignment, so **verify pins 7–12 = GND**
> (i.e. 1–6 = +12V) against PCIe CEM5.1 / the target GPU before powering, since the
> schematic ties 7–12 to the GND plane. **(2) board pickup —** the board still
> carries the old approximate land; in KiCad do **Update Footprints from Library**
> to pull this one (converts + remaps nets by pad number), then orient **J3 rot 180
> / J4 rot 0** (this footprint's mouth is on +y, so that puts the mouth out the edge
> with GND toward the shunts). The real ~1.5 mm pad gaps let the +12V lanes neck
> between the GND barrels (vs the old ~0.6 mm approximate that trapped them).

## Open questions touching this board

- **OQ-8:** rail accuracy — the ESP32-S3 ADC path caps at ~±1%; accept, or add a
  local REF3033 (→ ~±0.3–0.5%).
- **OQ-11:** per-pin shunt part (1 mΩ, §6.4).
- *(OQ-6 module-ID encoding resolved — CAN-only = 2.2 kΩ.)*

## High-current 12V routing — fanned per-pin lanes

See **`12vhpwr-routing-plan.png`** (regenerate with
`scripts/gen-hpwr-routing-plan.py`) — it carries the full to-placement top-down,
the four-wire Kelvin detail, the 4-layer stackup, and the width/via/stitch tables.
The 6×+12V pins carry ~**8.3 A each** (600 W ÷ 12 V = 50 A); **uneven sharing is
what melts these connectors**, so the module gives each pin its own 1 mΩ shunt +
INA240 and keeps the six 12V lanes symmetric so it adds no imbalance (and detects
any). Routing spec (laid in the GUI — the generator only sets placement):

- **Lanes / fan-out:** J3 and J4 are 12V‑2×6 connectors with a fixed **3 mm pin
  pitch**, centered on the power section; the six +12V lanes **fan out symmetrically
  to a ~6 mm SENSE pitch**, so each lane gets its OWN column — in-line shunt → RC
  filter → INA240 stacked straight down (no staggering, short in-column Kelvin) —
  then **fan back in** to J4. **J4 is placed rot 180°** (mouth out the bottom edge =
  correct OUT orientation, mirroring J3 at the top); since the six +12V pins are
  electrically interchangeable (all common to the GPU 12V plane, current already
  measured at each shunt upstream), each lane's load side is mapped to the J4 +12V
  pad directly below it (pin 6−*j*) so the lanes still **don't cross** despite the
  180. The symmetric fan keeps the lanes in equal-length pairs; if the small inner/outer
  length spread matters, length-match the straight section in the GUI (the 1 mΩ
  shunt + connector-contact R dominate, so it's minor).
- **Width (IPC-2221, 2 oz outer):** design to the **contact** rating, not nominal —
  Micro-Fit+ ≈ 9.5–13.5 A/contact → **13 A/pin**. Route each lane **2.5 mm on F.Cu,
  mirrored 2.5 mm on B.Cu, paralleled** (≈13 A at <10 °C rise; ≥3.0 mm if a B.Cu
  mirror is interrupted). **12V on both 2 oz outers; GND solid on In1 + In2** (1 oz,
  set BOTH inner pours to GND). Stack is **12V / GND / GND / 12V**, so it's the GND
  pair that sits in the middle (sandwiched by the two 12V outers); each 12V lane
  runs **directly against a GND plane** (F.Cu over In1, B.Cu under In2) → its return
  image-current flows in that plane right beneath the lane → small loop area, low
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
4-layer, **2 oz outer / 1 oz inner**, **~58 × 80 mm** — the 12V‑2×6 power path runs
TOP→BOTTOM down the centre-left (J3 IN top → 6 **fanned** per-pin lanes, each with
its in-line shunt → RC filter → INA240 → bypass → J4 pigtail OUT bottom); the
ESP + CAN + LDO + flash front end + RJ-45/USB-C fill the RIGHT. The six +12V lanes
**fan out from J3/J4's 3 mm pin pitch to a ~6 mm sense pitch** so each lane gets its
own column (in-column shunt/filter/INA, short Kelvin, no staggering). The **plug
connectors overhang their board edge** so a cable seats without the board fouling
the plug overmold while the solder pads stay on-board: **J3** (PSU 12V‑2×6 IN, top-
centre) overhangs the **top** edge ~3 mm; **J1** (RJ-45) and **J5** (USB-C) overhang
the **right** edge. **J4** (12V‑2×6 OUT) is **rot 180°** so its mouth/body overhang
the **bottom** edge too (correct OUT orientation, mirroring J3); the +12V load nets
are remapped to the reversed pins (pin 6−*j*, interchangeable) so the lanes stay
non-crossing. It's a captive soldered pigtail (wires exit the bottom). **Three M3 corner mounts**
(TL/TR/BL) — the RJ-45's big jack body fills the bottom-right corner, and the three
through-hole connectors anchor that side. The **per-lane sense passives are now
placed** (RFH/RFL/CF input filter + the INA bypass C10–C15); **component values are
on F.SilkS**. **DRAFT** marker present; DRC is **clean of structural hits** (0 copper
shorts / clearance / courtyard / copper-edge) — the remaining silk-overlap warnings
are the dense values-on-silk + tight placement, a GUI silk-refinement task. Next in
GUI: *Update PCB from Schematic* to pull the remaining **control-side decoupling**
(C1–C8, R1/R2/R7, D1), then route + pour (§6.8 Kelvin, §6.7 high-current).
Project-local library tables point at `../../lib` via `${KIPRJMOD}`.
