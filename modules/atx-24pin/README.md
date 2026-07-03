# 24-pin ATX module

Standard-tier per-rail sensing module for the 24-pin ATX connector. BOM target
**$35** (100-qty). See spec [§8](../../CEC-Platform-Ground-Truth-Spec.md).

## Directory-naming reality — read this before touching any of the three `atx-24pin*` dirs

Measured 2026-07-03 (`docs/standard-tier-review/atx-24pin.md`) against the live
`.kicad_sch`/`.kicad_pcb` files, not the directory names — the naming is misleading:

- **`modules/atx-24pin/` (this directory, no suffix)** is the **SHIPPED, ORDERED,
  ALPHA-line board** — straight-through layout, 110.2 × 75.7 mm, `J3`/`J4` both
  vertical. This is what physical units were fabbed from.
- **`modules/atx-24pin-rev2/`** is **NOT a copy of the shipped board.** It is the
  90°-rotated ("L") shrink STUDY, 83.1 × 79.2 mm — a design exploration, never
  fabbed.
- **`modules/atx-24pin-rev3/`** is the respin scaffold. Its **SCHEMATIC** is a
  fresh, verified rebuild (DETECT 2.2 kΩ, D1 ESD diode, FTP RJ-45 jack, `CAN_H`/
  `CAN_L` rename, J1 pin-1 no-connect — all confirmed live in the netlist). Its
  **PCB**, however, is byte-identical to `atx-24pin-rev2/`'s — i.e. rev3's layout
  has **not been started**; it still carries the old ESP32-S3 footprint/placement,
  no mux, no mezzanine header, no C6. Treat rev3 as **schematic-complete,
  layout-not-started**.

Per CLAUDE.md's 2026-07-03 alpha/beta convention: `atx-24pin/` is the **ALPHA**
line (validated prototype, as shipped); any refinement (rev3 or a future
"rev3a") lands as a **BETA** revision under that flag — alpha artifacts are never
overwritten.

| Item | Decision |
|---|---|
| Tier | Standard |
| MCU | ESP32-S3-MINI-1 (locked; same as Hub Standard) |
| Connector | RJ-45 8P8C, locking boot (universal interface) |
| Power out | Dedicated 2-pin +5VSB power-out to the Hub (§2.7); sized for the full Hub trunk with margin |
| Control | CAN on pair 3 (classical at 500 kbps in a Standard Hub) |
| Sensing | INA238 per rail (12V / 5V / 3.3V / 5VSB) — 16-bit I²C current/voltage, ≥1 kHz |
| Streaming | RS-485 **not populated** (Standard); pair 2 terminated at the module side |
| DETECT | Precision resistor pin 8 → GND; **OQ-6 LOCKED v1.7** — 24-pin is CAN-only, code = 2.2 kΩ (R1, backported to this schematic 2026-07-03; was a literal `"R_ID (OQ-6)"` placeholder before) |
| Protection | No per-pin PoE clamp (Standard/Pro, §2.4 RESOLVED v2.0); low-cap ESD diode on DETECT pin 8 (D3, LOCKED v2.0) — added to canonical, lands on rev3; Enterprise/MC over-voltage on the external uplink (OQ-7) |
| Reset | ESP32-S3 internal BOD + EN RC; no external supervisor (Hub-only part, §4) |
| BOM target | $35 (100-qty) |

## Open questions touching this board

- **OQ-1 (locked 2026-05-30):** this module is the **bulk-power source** for the
  Hub. It feeds +5VSB to the Hub over a dedicated 2-pin power-in connector
  (separate from RJ-45); the Hub then distributes 5VSB to all ports over RJ-45
  VCC (spec §2.7). Size this module's 2-pin power-out path for the full Hub trunk
  with margin.
- **OQ-6 (RESOLVED v1.7):** module-ID resistor value for this module type/tier —
  24-pin is CAN-only, 2.2 kΩ. R1 backported to this schematic 2026-07-03 (was a
  literal placeholder value, never carrying the locked code).

## Next revision (rev3) — TODO

The ordered **rev2 is as-built and frozen**. Carry these to the next fab. **Status
update, 2026-07-03:** all four items below are now confirmed **DONE in the rev3
SCHEMATIC** (verified live in the netlist) — the rev3 PCB layout has simply not
been started yet (see the directory-naming section above), so nothing here is a
live TODO against rev3's schematic; it remains a real TODO against rev3's PCB and
against `atx-24pin/` (this shipped board), which was not itself changed:

- **DETECT pin-8 ESD diode (D3):** now in the canonical schematic (spec §2.4 v2.0
  — low-capacitance ESD on pin 8 → GND for hot-plug insertion ESD). rev2 shipped
  **without** it; rev3 picks it up. Footprint `cec-Diode_SMD:D_SOD-323` still
  needs assigning in the footprint pass (working part PESD5V0S1UL).
- **Poke-and-ack DETECT sense tap (deferred):** add the high-Z tap from pin 8
  (~100 kΩ) to a spare ESP32-S3-MINI-1 GPIO so the module can sense a Hub
  DETECT-line poke and ack over CAN (spec §2.3 v2.6). **All 65 MINI-1 pins are
  currently assigned**, so this needs a deliberate GPIO reallocation at the rev3
  rework: free up / pick an ADC-capable GPIO, route pin 8 → 100 kΩ → that GPIO,
  and add a `DETECT_SENSE` net. The EPS / PCIe / 12VHPWR-std modules already do
  this on IO10 (via `gen-modules.py`); the 24-pin is hand-maintained so it's
  manual here. Tap value and sense method are **OQ-28**.
- **RJ-45 VCC pin no-connect (dual-feed fix, spec §2.7 v3.3):** drop **J1 pin 1
  (RJ-45 VCC)** off the module's `+5VSB` net. The 24-pin self-powers from its own
  ATX 5VSB tap, so it never needs the Hub's distributed VCC; tying J1.1 to +5VSB
  makes the RJ-45 VCC **parallel the dedicated JST feed**, and since the Hub power
  mux sits only in the JST leg, a short patch makes the RJ-45 the lower-resistance
  path → it hogs the bulk current on the 1.5 A contact and bypasses the mux. Leave
  J1.1 open; keep RJ-45 GND/CAN/DETECT. One-net change.
- Do **not** run `sync-schematic.sh` until you intend rev2's copy to track these
  — rev2 is ordered; keep it as-built unless you respin it.

## Status

Library-driven schematic capture can be drafted in-repo (then verified with ERC
and the netlist); PCB routing geometry is done in the KiCad 10 GUI. Project files
land here, with project-local library tables pointing at `../../lib` via
`${KIPRJMOD}`.
