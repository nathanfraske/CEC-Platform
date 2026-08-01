# ARGB Controller Standard (8-channel)

> **Rev BETA-1, DRAFT.** This is the first design pass on the ARGB Controller
> Standard — there is no alpha lineage (unlike the sensing modules, which had
> validated prototype boards before their own beta pass). **Schematic only —
> no `.kicad_pcb` exists yet.** See the `DRAFT` marker file for the exact
> conditions to clear before this board is ratified.

Standard-tier (8-channel) addressable-LED controller per spec [§7](../../CEC-Platform-Ground-Truth-Spec.md).
Unlike the Section 6 sensing modules, this board sources its own power (SATA
5V-direct) and is designed to run fully standalone with nothing plugged into
the Hub architecture — CAN link and Hub integration are optional, not
required, per spec §6.14/§7.5. Hierarchical schematic built with
`scripts/cec_sch_compose.py` (the `ent-common`/round-4 pattern) via
`scripts/gen-argb-standard.py`; regenerate with
`python3 scripts/gen-argb-standard.py --force`.

| Item | Decision | Spec basis |
|---|---|---|
| Channels | 8 | §7.1 |
| Power feed | SATA 15-pin, 5V-direct, fat/ganged 5V+GND (no 12V/3.3V wires) | §7.2 LOCKED |
| Input front end | P-FET reverse-polarity (Q1, AO4407A) → PPTC fuse (F1) → NTC inrush (RT1) → `+5V_LED_IN` | §7.2 LOCKED approach; RT1/F1/Q1 exact values are a working basis |
| Sensing | Total-rail shunt (RS1, 5 mΩ) → INA180A2 (U4, gain 50 V/V) → MCU ADC | §7.4 LOCKED direction; value is a working choice, math in §2 below |
| LED output | One 74AHCT244 octal buffer (U5); per channel: series R → BAT54S hot-plug clamp → PESD5V0S1BA TVS → 1×4 header | §7.3 LOCKED approach; BAT54S substitutes for the spec's named BAT54W (§4 below) |
| Control | CAN-only, TJA1051T/3 (U2), no module termination, H3a-pattern DNP CMC (FL1) + populated 0Ω bypass (R6/R7) | §7.5 LOCKED |
| DETECT | 2.2 kΩ (R4) — CAN-only comm-class code | §7.5 / §2.3, OQ-6 resolved |
| Hub link | RJ-45 8P8C shielded FTP, locking boot (J2) | §2.1 |
| Standalone / USB | USB-C (J3) — flash/debug + data path, no power feed from USB alone into the LED rail | §6.14, §7.5 |
| Status LED | 1× SK6812MINI status pixel (DL1), level-shifted through U6 (Hub Standard's own circuit, verbatim) — included per the brief's discretion, populated (not DNP) | n/a (added value, not spec-mandated) |
| MCU | ESP32-S3-MINI-1-N4R2 (U1) — **working basis, OQ-29 is OPEN platform-wide** | §7.1 (MCU "pending, see OQ-29") |
| BOM target | ~$14–20 (electronics, preliminary) | §9 |

## Block map (8 leaves + thin parent)

| # | Leaf | Contents |
|---|---|---|
| 01 | `01-power-input` | SATA 15-pin (J1) → Q1 (P-FET) → F1 (PPTC fuse) → RT1 (NTC) → `+5V_LED_IN`; R2/R3 rail-voltage divider |
| 02 | `02-sense` | RS1 (shunt) + U4 (INA180A2) → `+5V_LED` (the measured, post-shunt rail every downstream block uses) |
| 03 | `03-hub-link` | J2 (RJ-45 FTP) + DETECT chain (D1 ESD / R4 code / R5 poke tap) + FB1 bead onto `+5VSB_RJ` |
| 04 | `04-can` | U2 (TJA1051T/3) + FL1 (CMC position, DNP) with the H3a-pattern R6/R7 0Ω bypass |
| 05 | `05-mcu` | U1 (ESP32-S3-MINI-1-N4R2) + BOOT/RESET (SW1/SW2) + 3-way logic-power diode-OR (D2/D3/D4) → U3 (LP5907 3V3 LDO) |
| 06 | `06-led-outputs` | U5 (74AHCT244) + 8× (series R, BAT54S clamp, PESD TVS, ARGB header) |
| 07 | `07-usb-flash` | J3 (USB-C) + D6 (USBLC6-2SC6 ESD/EMC) + VBUS front end (D5/FB2/C10) + CC pulldowns (R18/R19) |
| 08 | `08-status` | DL1 (SK6812MINI) + U6 (level shift) — optional/populated |

---

## §1 — MCU selection (OQ-29, working basis, NOT locked)

**ESP32-S3-MINI-1-N4R2** (U1) is a **working basis**, not a locked decision.
OQ-29 (ARGB Controller MCU selection) is open platform-wide across all three
ARGB tiers. Rationale for this pick specifically:

- The S3's **LCD/I2S parallel peripheral** can drive all 8 WS2812/SK6812-class
  channels with hardware-timed, low-jitter output (the same technique the
  popular WLED/ESPHome LED-driver firmware ecosystem already leans on for
  ESP32-S3), which matters for clean multi-channel ARGB timing without
  bit-banging every channel on a software loop.
- It is the **same exact part** already used and sourced on `12vhpwr-standard`
  (`C3013941`), so it rides an existing, verified footprint/pinout/decoupling
  precedent rather than introducing a new MCU family into the repo.
- Native USB (no external USB-UART bridge needed) matches the standalone /
  USB-flash posture this board is designed for (§6.14).

**Flagged risk:** `docs/pricing-study-2026-07-05.md` records this part as
**out of stock at LCSC as of 2026-07-05** (same finding independently affects
`12vhpwr-standard`, which is unaffected on its own C6-based siblings). This is
a platform-wide, already-known sourcing risk, not something new introduced by
this board — flagging it here so it isn't rediscovered. Alternatives an
owner/coordinator might weigh at ratification: ESP32-C6-MINI-1 (cheaper, in
stock at 2,220+ per that same study, but no native LCD/I2S peripheral — would
need a different multi-channel LED-drive strategy) or RP2040/CH32V307-class
parts with PIO-style peripherals purpose-built for WS2812 timing.

### GPIO / pad map (verified against the exported netlist)

| U1 pad | Net | Role |
|---|---|---|
| 3 | `+3V3` | logic supply |
| 4 | `Net-(U1-IO0)` | GPIO0 / BOOT (SW1) |
| 5 | `/ISENSE_TOTAL` | ADC, INA180A2 output |
| 6 | `/VRAIL_5V_DIV` | ADC, rail-voltage divider tap |
| 7 (IO3) | — | unconnected/spare |
| 8–15 | `/LED1_DATA` … `/LED8_DATA` | 8 channel data outputs (→ U5 74AHCT244 inputs) |
| 16 | `/DETECT_SENSE` | poke-and-ack tap (R5) |
| 21 | `/CAN_TX` | → U2 (TJA1051T/3) |
| 22 | `/CAN_RX` | → U2 |
| 23 | `/USB_D_N` | native USB, via D6 clamp |
| 24 | `/USB_D_P` | native USB, via D6 clamp |
| 25 | `/STATUS_LED_DATA` | → U6 → DL1 |
| 45 | `Net-(U1-EN)` | EN / RESET (SW2) |
| 17–20, 26–44 (excl. 39/40) | — | unconnected/spare — headroom for firmware iteration |

Pad numbers (not GPIOxx labels) are given because that is what the exported
netlist actually verifies; cross-reference the ESP32-S3-MINI-1 datasheet pad
table for the corresponding GPIO number before writing firmware.

---

## §2 — Current-sensing headroom math (RS1 + U4)

Spec §7.4 locks the **direction** (total-rail shunt + INA180A2 into the MCU
ADC) but not the shunt value; **RS1 = 5 mΩ / 2 W / ±1%** (Milliohm
`HoYLR2512-2W-5mR-1%`, 2512 package) is this board's working choice, sized
against the §7.1 **~7 A** Standard-tier ceiling:

- **Shunt power dissipation at the 7 A ceiling:** P = I²R = 7² × 0.005 =
  **0.245 W** — about 12% of RS1's 2 W rating, i.e. roughly **8× headroom**
  (the shunt itself could carry ~20 A before hitting its 2 W rating).
- **INA180A2 (gain A2 = 50 V/V) output at 7 A:** V_shunt = 7 × 0.005 = 35 mV;
  V_out = 35 mV × 50 = **1.75 V** — about 53% of a 3.3 V ADC's full-scale range
  at the steady-state ceiling, leaving headroom to measure transients above
  7 A before the ADC (not the amplifier) saturates: full-scale corresponds to
  3.3 V / 50 / 0.005 = **13.2 A**, comfortably above the shunt-enforced ceiling.
- Net result: the value gives the auto-LED-count / boot-self-test / fault-
  localization features of §7.4 a usable signal-to-range ratio at the rated
  ceiling while retaining real margin against a transient without either the
  shunt cooking or the ADC clipping outright.

This is a **working choice**, not a locked spec value — an owner/firmware
pass may want to retune it once real per-channel current-draw profiles (LED
count × color mix × brightness) are measured on a populated strip.

---

## §3 — Logic-power diode-OR: the RJ-45 5VSB leg is a PROPOSAL

Spec §7.2 says the controller "derives its 3.3V logic from the same 5V feed
(or USB VBUS when on USB alone, for bench flashing)" — i.e. **two** sources.
This board's `05-mcu` leaf builds a **three**-way diode-OR (D2/D3/D4, all SS34)
into U3 (LP5907 3V3 LDO):

1. **D2 — `+5V_LED` (SATA-derived, post-shunt).** Spec-mandated, primary.
2. **D4 — `VBUS` (USB-C, bench flashing).** Spec-mandated.
3. **D3 — `+5VSB_RJ` (Hub RJ-45 pin 1, via FB1 bead).** **NOT in the spec text
   — added here as a proposal.** Rationale: if the module is plugged into a
   Hub but its own SATA feed is not yet connected (e.g. bench bring-up, or a
   fault has opened Q1/F1), CAN control and DETECT/telemetry can still come up
   off the Hub's 5VSB rather than requiring the module fully dead. Trade-off
   being flagged, not assumed: this pulls a small logic-only current onto the
   Hub's RJ-45 VCC pin, which spec §7.2 explicitly says this module should
   otherwise present "negligible load" on. The draw is logic-only (an idle
   ESP32 + LDO, not the LED rail — the LED output stage has no path back to
   this diode-OR), so it should be small relative to the RJ-45 VCC per-port
   budget (OQ-2), but this is a **flagged addition beyond the locked spec
   text**, not a ratified decision — an owner should confirm whether this
   third leg is wanted before this board leaves BETA, or whether the module
   should instead stay logic-dead with no SATA/USB power present.

---

## §4 — BAT54S substitutes for the spec-named BAT54W (verified)

Spec §7.3 names **"BAT54W"** as the per-channel DATA-first hot-plug clamp
("a BAT54W dual Schottky as the DATA-first hot-plug clamp... it kills the
powered hot-plug back-feed where a strip plugged in live back-powers its own
controller through its protection diode"). **BAT54W is not a real dual-diode
part under that exact name** in the parts search done for this board — the
BAT54 family's common SOT-23-3 dual-Schottky variants are **BAT54S**
(series-connected: two diodes sharing one node) and **BAT54C** (common-
cathode). The described behavior — a series element between DATA and the
strip that blocks a live strip's back-feed while still passing the level-
shifted data signal through — is what a **series** dual-diode topology gives,
so **BAT54S** was substituted.

**Pinout verified two ways**, not assumed from the part name alone:

1. By rendering the vendored `cec-vendor:BAT54S` symbol and reading the drawn
   pin roles directly.
2. By the exported netlist: `BAT54S` pin 1 = anode → `GND`, pin 2 = cathode →
   `+5V_LED`, pin 3 = tap → the per-channel `LEDn_HDR` node (the DATA line
   after the series resistor). This is the standard BAT54S internal topology
   (two anodes tied to pin 1, two cathodes independently on pins 2/3, i.e. a
   single series-conducting path pin1→pin3 with pin 2 as the other diode's
   cathode) applied as: pin 1 clamps the DATA node to GND on an under-voltage
   event, pin 2 clamps it to +5V_LED on an over-voltage event — the dual-
   direction ESD/hot-plug clamp behavior the spec text describes, just under
   the real, sourceable part name.

Per-line **PESD5V0S1BA** (not the spec-named PESD5V0S1UL) is the TVS: this
follows the platform-wide UL→BA correction already locked in `CLAUDE.md`
(§2.4 v2.0 note — the UL LCSC listing is DFN1006/SOD-882 only; BA is the
SOD-323 sibling the rest of the platform's boards are laid out for), applied
here proactively rather than shipped with the stale part and fixed later.

---

## §5 — ARGB strip header: OQ-36 (mechanical) is open; header itself is a stand-in

Spec §7.3: "The strip connector is the standard 5V VDG addressable header,
three used positions on a keyed 4-position shroud. Automatic retention and
anti-offset keying are carried as the mechanical layer (OQ-36)." A real
**keyed, 3-used/4-position ARGB VDG header does not exist as a stocked LCSC
part** (searched for this board; nothing matching the keyed-shroud, reverse-
polarity-proofed ARGB connector family turned up). Each of the 8 channel
headers (J4–J11) is therefore a **plain, unkeyed 1×4 2.54 mm THT header**
(Ckmtw `B-2100S04P-A110`) as a schematic-level stand-in:

- Pin 2 (the real connector's removed/keyed position) is left with **no net**
  — the generic pass emits its `no_connect` flag, matching the "3 used
  positions" the spec describes electrically, even though this stand-in
  header has no physical keying to prevent a reversed plug.
- **OQ-36 (mechanical: retention, anti-offset keying, chassis) is OPEN** and
  owned outside this schematic pass (per the DRAFT marker, tracked to the
  owner). Swapping in a real keyed part later is a footprint-only change —
  the electrical intent (3 active positions, DATA/+5V_LED/GND, pin 2 idle) is
  already correct and would not need re-wiring.

---

## §6 — Other flagged/working-basis decisions

- **SATA input connector (J1) is CONSIGNED.** No credible LCSC line for a
  board-mount, right-angle, 15-pin male SATA power connector turned up in the
  search done for this board. The schematic uses a generic `Conn_01x15`
  symbol with **no footprint assigned** pending a real sourcing decision —
  source directly from a connector house (e.g. the KLS1-SATA family) at BOM
  lock. This board's BOM line for J1 carries no LCSC number and is estimated,
  not quoted (see the BOM section below).
- **Fat/ganged SATA cable is a required accessory, not a BOM line here.** Spec
  §7.2: "CEC ships this fat cable in the box" — the cable that bonds the SATA
  connector's three 5V contacts to one thick conductor (and grounds to
  another) is what makes the ~7 A ceiling safe on stock SATA contacts. That
  cable is a separate accessory/SKU, not a component on this board, and is
  **not included** in this schematic or its BOM.
- **Inrush element: NTC chosen over a load switch.** Spec §7.2 allows either
  ("a controlled inrush element (load switch or NTC)"). RT1 (Nanjing Shiheng
  `MF72-5D-20`) was chosen over a MOSFET-based load switch (e.g. a hot-swap
  controller or a simple P-FET soft-start) because: (a) it is a single
  passive part with no gate-drive/timing circuit to design and verify, (b) at
  this board's modest ~7 A / single-rail scale the NTC's steady-state I²R
  loss and the fact that it stays in-circuit (not a bypassed/switched
  element) are acceptable trade-offs against the load-switch's added parts
  count and complexity, and (c) it mirrors the simpler end of what other
  Standard-tier CEC modules already do. A load switch would give a faster,
  more repeatable inrush profile and zero steady-state resistance once
  switched over — worth reconsidering if bench data shows the NTC's warm-up
  behavior (resistance drops as it heats, so repeated fast power-cycling
  doesn't get the same inrush protection as a cold start) is a real problem
  in practice.
- **RJ-45 shielded FTP jack (J2)** uses the platform-locked
  `cec:RJ45_FTP_Shielded_Horizontal` (Kinghelm KH-RJ45-58-8P8C, `C2683360`)
  per spec §2.1 — same part as Hub Standard / EPS / 12VHPWR-Standard, SH1/SH2
  tied to GND (both-end shielding+grounding).
- **DETECT (R4 = 2.2 kΩ)** matches the CAN-only comm-class code (§2.3, OQ-6
  resolved) — module type/tier ride CAN enumeration, not a new DETECT code
  (per spec §7.5, explicitly: "no new DETECT code is added").
- **Status LED (DL1/U6) is populated, not DNP** — included per this task's
  discretion, not a spec mandate: cheap, reuses Hub Standard's own proven
  level-shift circuit verbatim, and a standalone board (no Hub/host UI
  present) benefits the most from a local at-a-glance health indicator.

---

## Standalone posture (§6.14 / §7.5)

This board is designed to be **fully usable with nothing plugged into the Hub
architecture**: USB-C (J3) is the bench-flash and data path, native ESP32-S3
USB, no external bridge chip. Per spec §7.5, open-software integration is a
**firmware** concern (Adalight-over-USB-CDC for a driver-free OpenRGB path, a
SignalRGB JS plugin, optionally an upstream OpenRGB C++ driver) — this
schematic provides the hardware (USB-C data path, per-channel current
sensing, the 8 buffered outputs) that firmware needs to present each channel
as its own zone or as one concatenated Adalight strip; no firmware exists yet
and none of that logic lives in this deliverable.

---

## Verification (gates run against this schematic)

All of the following were run against the committed generated output and are
reported as measured, not assumed:

- **`kicad-cli sch erc`** on the full hierarchy (`argb-standard-module.kicad_sch`):
  **0 errors**, 123 warnings — every warning is one of two documented-benign
  classes platform-wide (`lib_symbol_mismatch`, generator lib-cache noise;
  `pin_to_pin`, KiCad's Unspecified/Passive/Bidirectional pin-type strictness
  noise). No other violation class appears.
- **Exported netlist** (`kicad-cli sch export netlist`): 103 nets, all 81
  components present (none silently dropped by a leaf load failure). Spot-
  verified net-by-net: the SATA bus (`J1` pins 7/8/9 + `Q1` source), `Q1`
  drain → `F1` → `RT1` → `+5V_LED_IN`, the gate pulldown, all 8
  `LEDn_DATA`/`LEDn_BUF`/`LEDn_HDR` groups (no cross-channel contamination),
  `CAN_H_RJ`/`CAN_L_RJ` (correctly separate nets, bridged only through the
  populated H3a bypass resistors), `CAN_TX`/`CAN_RX`, the USB-C `VBUS`/`D+`/
  `D-`/`CC1`/`CC2` group (correctly five separate nets, not the one merged
  blob an earlier iteration produced), `+5V_LED` (25 members), `+5VSB_RJ`,
  `+3V3`, and `GND` (92 members spanning every leaf).
- **`scripts/audit-sch.py`**: **clean** — 0 findings (`wire_through_body`,
  `unconnected_wire_endpoint`, `label_dangling`, `symbol_overlap`,
  `endpoint_off_grid`, `missing_lib_symbol`, `instance_path_mismatch`,
  `bare_uuid`) across all 8 leaves and the thin parent.
- **`scripts/cec_sch_gates.py --region-containment` / `--sheet-bounds`**:
  **clean** across all 8 leaves and the thin parent (one long `04-can`
  caption that ran past the A4 sheet's right edge was split into two shorter
  caption lines to fix it — an embedded newline does not work here because
  the shared `cec_sch_layout._unescape` helper does not decode `\n`, so two
  separate `caption()` calls were used instead).

## BOM

`bom/bom.csv` (generic tracking format) and
`bom/argb-standard-module-BOM-jlcpcb.csv` (JLCPCB upload format — Comment/
Designator/Footprint/LCSC, rows with no LCSC number excluded) are generated
from the schematic via `kicad-cli sch export bom` with a custom field/grouping
list matching the convention already used elsewhere in this repo (e.g.
`modules/12vhpwr-standard/bom/`).

**Every LCSC part number in the BOM was checked** — either against the live
LCSC listing directly, or by cross-referencing the same manufacturer part
number already sourced on another board in this repo — and **six real
errors were found and fixed** in the process (all in the generator, not
hand-patched into the output):

| Ref(s) | Was (wrong) | Fixed to | The wrong number actually was |
|---|---|---|---|
| DL1 | `C2841455` | `C5149201` | an unrelated 4.7pF 0201 ceramic cap |
| U6 | `C7526` | `C113521` | a stale/404ing listing |
| C1 | `C96446` | `C49066` | a 10µF **0603** cap (wrong value + wrong package vs. the intended 100µF 1210) |
| R2 | `C25900` | `C25792` | a 4.7kΩ resistor (one decade off vs. the intended 47kΩ — this is the rail-divider top resistor) |
| R10–R17, R20 (9×) | `C25131` | `C25104` | a 68Ω resistor (wrong value vs. the intended 330Ω, on all 9 LED-series-resistor positions) |
| C7, C8, C9 | `C15849` | `C29936` | a different (though electrically similar) Samsung 1µF 0603 variant |

After the fixes, a full cross-check (every MPN in this BOM against the same
MPN's LCSC number on every other board's BOM in this repo) shows **zero
remaining mismatches**.

**Cost estimate: ≈ $8.30 raw component cost** at roughly-100-piece LCSC
pricing (most line items priced against the live LCSC listing; the ~20
smallest 0402/0603/0805 jellybean passives are reasoned estimates in the
$0.003–$0.03 range, not individually spot-priced — they are too small to
meaningfully move the total). This sits **below** the spec §9 "~$14–20
(electronics, preliminary)" band. Flagged delta drivers, not a claim that the
spec figure is wrong:

- This is **raw LCSC catalog pricing only** — it does not include JLCPCB's
  per-unique-part "Extended part" assembly/setup fee (this board has roughly
  15–20 Extended, non-Basic parts), which is a real per-order cost a raw
  per-unit rollup does not capture.
- **J1 (SATA connector) has no real quote** — the $0.75 used above is a
  placeholder estimate for a consigned, connector-house-sourced part; the
  fat/ganged SATA cable accessory (§6 above) is not costed at all here.
  This is the largest single line-item uncertainty in the estimate.
  Uncertainty range roughly ±$0.50–1.50 on this line.
- No PCB fabrication cost is included (this deliverable has no PCB yet).
- The same "raw-parts total lands meaningfully under the platform's own BOM
  target" pattern shows up on other boards in this repo (e.g.
  `12vhpwr-standard`'s own raw-JLC-parts figure of ~$21 against its $49
  target), consistent with those targets already budgeting headroom for
  assembly fees, PCB fab, and margin beyond raw component cost — so this
  board landing under its own $14–20 figure is not, on its own, a red flag.

## Open questions touching this board

- **OQ-29 (OPEN, platform-wide):** ARGB Controller MCU selection. This
  board's ESP32-S3-MINI-1-N4R2 is a working basis (§1 above), not locked.
- **OQ-36 (OPEN):** ARGB mechanical — retention, anti-offset keying, chassis.
  The 8× strip headers are a plain unkeyed stand-in (§5 above).
- **OQ-30 / OQ-35:** per-channel sensing and the Pro/Max 12V-buck feed do not
  apply to this Standard-tier board (total-rail-only sensing, 5V-direct feed
  are both LOCKED at this tier per §7.1/§7.4).
- **OQ-2 (total 5VSB current cap):** touched by the §3 proposal above (the
  RJ-45 5VSB logic-power leg) — an owner call on whether that leg is wanted
  bears on this budget, however small the draw.
- *(OQ-6 DETECT encoding is RESOLVED — this board's 2.2 kΩ CAN-only code is
  correct and not a new addition.)*

## Repository conventions followed

- Project-local library tables (`sym-lib-table`, `fp-lib-table`) point at
  `../../lib` via `${KIPRJMOD}` — no machine-global or absolute paths.
- All new/reused footprints resolve against the existing vendored libraries;
  no new vendoring was required beyond what earlier CEC boards already
  brought in (the RJ-45 FTP jack, TS-1088 buttons, PESD5V0S1BA, SK6812MINI,
  TJA1051T/3, and USB-C receptacle footprints/3D models are all already
  vendored in `lib/`).
- No absolute paths, no machine-global library nicknames.
