# 12VHPWR Standard module

Standard-tier **per-pin** sensing module for the **12VHPWR / 12V‑2×6** (PCIe CEM
5.x, 600 W GPU) connector. BOM target **$49** (100-qty). See spec
[§6.1](../../CEC-Platform-Ground-Truth-Spec.md).

| Item | Decision |
|---|---|
| Tier | Standard |
| MCU | ESP32-S3-MINI-1-N4R2 (locked; same MINI-1 as the other modules) |
| Hub link | RJ-45 8P8C **shielded FTP**, locking boot (J1) — Kinghelm **KH-RJ45-58-8P8C** (LCSC **C2683360**), the same already-sourced jack as the Hub (§2.1; 2026-06-06). Drop-in on the routed 1.27 mm land (pads 1–8 identical to the old 54602). |
| Power connector | **12V‑2×6** (Molex Micro‑Fit+ / Amphenol Minitek, 16‑ckt: 6×+12V, 6×GND, 4 sideband). **J3 = board-mount right‑angle MALE header** (the PSU 12V‑2×6 cable plugs in). **J4 = captive OUTPUT pigtail** (a 12V‑2×6 cable soldered to the board, female plug → GPU). There is **no stock board‑mount female** 12V‑2×6 (it only exists as a cable plug), so this male‑in / soldered‑pigtail‑out is the minimal‑mated‑pair inline form (§2.8). |
| Sensing | **Per-pin**: six **INA240** current-sense amps, one across each +12V pin's **1 mΩ** shunt (RS1–6), feeding the ESP32-S3 ADC (IO1–6) directly — **no I²C sensing bus**. REF1/REF2 → GND (unidirectional forward). A **47k/10k divider** (R5/R6, **0.1%**) brings the rail voltage into a 7th ADC channel. With the **REF3030 ratiometric reference** (U4, v3.8) accuracy is **~±0.3–0.5%** on V and all six I (see **OQ-8** + the Voltage-ref row). |
| Input filter | Per-channel **anti-alias / transient RC** on each INA240 input: matched **10 Ω** series Rf on IN+/IN− (RFH1–6 / RFL1–6) + a **470 nF** differential cap (CF1–6). **fc = 1/(2π·2·Rf·Cdiff) ≈ 16.9 kHz**, so the ~10 kHz GPU transients this pass targets pass at ~−1.3 dB and HF is rolled off ahead of the ADC. Rf held at 10 Ω + matched (TI's INA240 ceiling) → negligible gain/CMRR error. *(Optional ~47 nF common-mode caps deferred — OQ-8.)* |
| Sideband | The four **12V-2×6 sense pins** (13–16: SENSE0, SENSE1, CARD_PWR_STABLE, CARD_CBL_PRES#) pass straight through J3→J4 **and** each taps a free ESP32-S3 GPIO (IO8/9/11/12) via a **1 kΩ** series R (R10–R13), so firmware can read the cable's advertised power capability + present/stable state and report it over CAN. |
| Temperature *(v3.7)* | **2× NTC 10k** (Murata **NCP15XH103F03RC** / LCSC **C77131**, 0402) into spare ESP32-S3 **ADC2** channels (this module never uses Wi-Fi, so ADC2 is free): **TH1** in the **12V power section by the shunt row** (board/shunt temperature), **TH2** ambient at a cool edge. Each is an NTC / 10 kΩ (R20/R21) / 100 nF (C20/C21) divider → **IO13 / IO14**; firmware reports temperature and **ΔT above ambient**. Purpose is **measurement quality + board health**: compensate the shunt-TCR / INA240-gain drift on the per-pin current readings, and flag 12V-section overheating — then board temp + per-pin current + rail voltage **fuse** to infer the off-board GPU-side condition. **Board-only**; a pigtail/GPU-plug NTC (the direct GPU-contact read) is **deferred**. Spec [§6.1](../../CEC-Platform-Ground-Truth-Spec.md). |
| Voltage ref *(v3.8)* | **REF3030** (U4, 3.0 V, SOT-23) measured on **ADC1 IO8** for **ratiometric correction** — firmware ratios out the ESP-ADC gain/reference drift, lifting the rail divider **and** all six current channels from ~±1% to **~±0.3–0.5%** (with **0.1%** R5/R6). Bypass C22 (OUT) + C23 (IN). The deliberate **middle ground** below the Pro's LTC2358-18; the REF3030 (3.0 V) is *measured* by the ADC, unlike the Pro's REF3033 (3.3 V) which feeds the LTC2358 ref. IO8 was freed by moving the SENSE0 sideband tap → **IO15**. See **OQ-8**. |
| Streaming | RS-485 **not populated** (Standard); pair 2 terminated module-side |
| DETECT | 2.2 kΩ precision (R1) — CAN-only code (§2.3, OQ-6 resolved); poke-and-ack tap R7 → IO10 (OQ-28) |
| Protection | No per-pin PoE/over-voltage (Standard/Pro, §2.4 v2.0); low-cap ESD diode **D1 = PESD5V0S1BA** (SOD-323, LCSC **C5261083**) on DETECT pin 8 — corrected from the non-SOD-323 PESD5V0S1UL on the 2026-06-06 sourcing pass |
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

- **OQ-8 (RESOLVED, v3.8 — revises the v3.7 no-ref call):** rail accuracy — a
  **REF3030** (3.0 V) ratiometric reference (U4), measured by the ESP ADC1, lifts
  the rail divider **and** all six current channels from ~±1% to **~±0.3–0.5%**
  (0.1% R5/R6) — the **middle ground** between the bare divider and the Pro's
  precision instrument. It's the *reference*, not a second ADC or a sensing bus, so
  Standard stays the fast firehose, just accurate + stable (stability is what makes
  a connector-degradation / dV·dI source-impedance trend real). Full simultaneous
  precision stays the Pro (LTC2358-18 + REF3033). Note: Standard REF3030 = 3.0 V
  (*measured* by the ADC); Pro REF3033 = 3.3 V (feeds the LTC2358 ref).
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

## Routing status (2026-06-05)

**Part audit — all clear.** Every vendored symbol used on this board (and in the
shared lib) had its pin#→name mapping checked against the manufacturer datasheet:
INA240 (1=IN−, 2=GND, 3=REF2, 4=NC → tied to GND, which the datasheet sanctions,
5=OUT, 6=V+, 7=REF1, 8=IN+), INA226/228/238 (identical DGS VSSOP‑10), TJA1051T/3,
LP5907, ESP32‑S3‑MINI‑1, RJ‑45, USB‑C, the 12V‑2×6, and the rest — **all correct,
no mis‑wires.** (Cosmetic‑only notes are in the repo CLAUDE.md.)

**High‑current path — DONE.** All six +12V lanes carry end‑to‑end: J3 +12V → shunt
on **F.Cu** (2.5 mm, fanned 3→6 mm), shunt → J4 +12V on **B.Cu** (2.5 mm). Lane 3's
full sense chain is routed as the reference.

**Remaining — 47 ratlines, all sense/signal** (see **`12vhpwr-route-plan.png`**,
regenerate with `scripts/gen-hpwr-route-status.py`):
- All six **INA OUT → ESP ADC IO1–6** (ISENSEP1–6).
- **Kelvin taps** off the inner shunt‑terminal edges → RFH/RFL, and **RC filter →
  INA IN+/IN−**, on lanes 1, 2, 4, 5, 6 (route them like the finished lane 3):
  0.25 mm matched pair over the In1 GND plane, ⊥ to the 12V lanes, filter at the INA.

**Before re‑checking DRC** (current DRC = 47 unconnected + 291 violations):
- **Fill All Zones (B).** 252 of the violations are `clearance`/`hole_clearance`
  reading *actual 0.000 mm* — that is **stale GND‑pour** (kicad‑cli cannot refill),
  not real shorts. Set **both** inner zones to GND.
- Delete **18 dangling vias + 3 dangling track stubs**.
- **Update PCB from Schematic** — syncs U2 value (the PCB still shows the old
  *TJA1462A*; the schematic is already *TJA1051T/3*, C38695; footprint identical).
- **Outline fixed:** the Molex 12V‑2×6 footprint's mouth/latch profile was on
  Edge.Cuts (read as a malformed board outline); moved to Dwgs.User in the library
  and in J3/J4 (invalid_outline 4→0).

**Note — J4 orientation:** with the official Molex footprint J4 is **rot 0°** (mouth
out the bottom edge) and J3 is **rot 180°** (mouth out the top); this supersedes the
"J4 rot 180°" wording in the Status paragraph above.

## BOM / JLC sourcing (2026-06-06)

Every component is sourced to an LCSC part (written into the schematic symbol
`LCSC`/`MPN`/`Manufacturer` props) and exported in `bom/`:
`bom.csv` (tracking) + `12vhpwr-standard-BOM-jlcpcb.csv` (Comment/Designator/Footprint/LCSC).
**~$21/board** in JLCPCB parts (single-qty pricing) + the consigned Molex 12V‑2×6 —
comfortably under the **$49** target; cost is dominated by **6× INA240A3DR ($1.87 ea =
$11.24)**, the **ESP32 ($4.59)**, and the **6× 1 mΩ shunts ($0.52 ea)**.

Pinouts datasheet-verified this pass (INA240 SBOS662C, LP5907 SNVS798Q, ESP32‑S3‑MINI‑1
Table 3‑1, REF3030 SBOS392K, TJA1051 NXP) — all symbol pin maps correct.

Caveats / flags carried into ordering:
- **J3/J4 (12V‑2×6, Molex 219116 / 2191161161): NOT in the JLCPCB catalog → consigned /
  hand‑soldered** (J4 is a captive pigtail anyway). Left with no LCSC by design.
- **J1 RJ‑45 → shielded FTP (Kinghelm KH‑RJ45‑58‑8P8C / C2683360), shared with the Hub**
  (2026-06-06). This both resolves the old 54602's stock≈7 problem and moves the module to
  the §2.1 platform FTP jack. **Drop‑in on the routed contacts** — pads 1–8 are pad‑identical
  (1.27 mm, (0,0)…(8.89,−2.54)); the committer only needs *Update Footprints from Library*
  on J1 (8 contacts preserved). The mounting pegs land ~0.1 mm off (same holes, now NPTH);
  the jack adds two shield‑tab pads SH1/SH2. **Shield grounding: SH1/SH2 tied to GND — both
  ends shielded AND grounded.** Hub and module share the PC chassis on a short RJ‑45, so
  both‑end grounding is the right choice (it's what makes the shield effective at HF; the
  ground loop is negligible since the chassis already bonds both grounds via the M3 mounts).
  Wired in the schematic (3 wires + GND #PWR926 + a junction at J1's right edge; ERC clean,
  SH1/SH2 now on the GND net). On the PCB the committer ties the two shield tabs into the
  GND pour during *Update Footprints from Library*.
- **RS1–6 shunt = CSS2H‑2512R‑1L00F (C4175647): the spec §6.4 candidate, OQ‑11 still
  OPEN** — sourced as the spec's named part, NOT a locked decision (flagged on each RS in
  the schematic `Note` prop). Stock ≈ 2.8k (~460 boards).
- **INA240A3DR (C2060584): SOIC‑8 D part** (the PW/TSSOP pinout differs — never order PW).
  Stock ≈ 1.7k → ~290 boards; re-check for volume.
- **SW1/SW2 → TS‑1088‑AR02016 (C720477, XKB), shared with the Hub** (2026-06-06, Basic,
  cheaper than the EVQ). The land **changes** (EVQ‑PU = 4 pads at ±2.625/±0.85; TS‑1088 =
  2 pads at ±2.18/0), so it is **not** a drop‑in: the committer must *Update Footprints from
  Library* and **re‑place + re‑route SW1/SW2** (trivial — 2 buttons, GPIO0/EN + GND each).
- 10 Basic / 13 Extended unique lines. Datasheet‑URL props not yet populated (informational).
