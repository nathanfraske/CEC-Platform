# CLAUDE.md

Operating guidance for Claude Code working in the CEC platform repository.

## Ground truth and precedence

`CEC-Platform-Ground-Truth-Spec.md` is the canonical specification and holds
precedence over everything else, including this file. Where this file and the
spec disagree, the spec wins, and this file should be updated to match. Treat
this file as a working summary plus operating instructions, and read the spec
before making any design decision.

Spec revision reflected here: 2026-05-30.

## What this project is

CEC is a modular PC power-telemetry system. Per-rail sensing modules connect to
a central Hub over a single commodity cable (RJ-45). The Hub aggregates
telemetry and forwards it to the host PC over USB. Four tiers (Standard, Pro,
Enterprise, Mission Critical) are built from one fundamental design with
progressively populated features. Modules are tier-agnostic and degrade
gracefully: any module works in any Hub, with higher-tier features going dormant
when the Hub cannot service them and activating without replacement when moved
to a capable Hub.

## Repository layout

```
cec-platform/
  lib/                       # shared library: the locked universal interface
    cec.kicad_sym            # symbols
    cec.pretty/              # footprints (RJ-45 FTP jack, SK6812, ESP32, power input; protection net is Enterprise/MC, OQ-8)
    3dmodels/
  hubs/
    hub-standard/
    hub-pro/
    hub-enterprise/          # platform-summary only for now (OQ-7)
    hub-mission-critical/    # platform-summary only for now (OQ-7)
  modules/
    atx-24pin/
    eps-8pin/
    pcie-8pin/
    12vhpwr-standard/
    12vhpwr-pro/
  fab/                       # tagged release snapshots of exactly what was sent to the board house
  scripts/                   # kicad-cli wrappers and CI helpers
  CLAUDE.md
  .gitignore
```

The universal-interface parts (the RJ-45 jack, the SK6812 chain, the ESP32
module, the power input — plus the optional Enterprise/MC over-voltage protection
network, OQ-8) live in `lib/` so a change propagates to every board instead of
being redrawn per board.
Use project-relative library paths (`${KIPRJMOD}`) in `sym-lib-table` and
`fp-lib-table`. Never commit absolute library paths.

## Boards

| Board | Directory | Tier | MCU | Ports | Host link | BOM target (100q) |
|---|---|---|---|---|---|---|
| Hub Standard | hubs/hub-standard | 1 | ESP32-S3-MINI-1-N16R2 | 4 | USB Full Speed | ~$36 |
| Hub Pro | hubs/hub-pro | 2 | ESP32-P4 | 8 | USB High Speed | ~$45 |
| Hub Enterprise | hubs/hub-enterprise | 3 | ESP32-P4 + secure element | n/a | USB HS (+ optional 1000BASE-T1) | ~$50 |
| Hub Mission Critical | hubs/hub-mission-critical | 4 | ESP32-P4 + crypto | n/a | redundant uplinks | ~$80 |
| 24-pin ATX module | modules/atx-24pin | Standard | ESP32-S3-MINI-1 | - | - | $35 |
| EPS 8-pin module | modules/eps-8pin | Standard | ESP32-S3-MINI-1 | - | - | $32 |
| PCIe 8-pin module | modules/pcie-8pin | Standard | ESP32-S3-MINI-1 | - | - | $38 |
| 12VHPWR Standard module | modules/12vhpwr-standard | Standard | ESP32-S3-MINI-1 | - | - | $49 |
| 12VHPWR Pro module (lead) | modules/12vhpwr-pro | Pro | ESP32-P4 | - | - | $98 to $99 |

Every board uses the RJ-45 connector defined below. Enterprise and Mission
Critical are specified at platform-summary level only until first customer
requirements land (OQ-7); the Enterprise tier additionally carries an RJ-11 trust
channel and a secure element, and Mission Critical adds redundant power, CAN, and
trust.

## Locked decisions (do not change without explicit instruction)

These are settled in the spec. Do not alter them, and flag any schematic,
layout, or BOM that contradicts them.

Connector and physical interface:
- Module-to-Hub connector is RJ-45 (8P8C) for all tiers, all modules, all Hubs.
  Mini-Fit Jr is retired platform-wide.
- Locking-boot RJ-45 is the default shipped variant. Mechanical-keyed variants
  remain available for high-security deployments. Shielded (FTP) jacks on Hub and
  modules.
- PoE/over-voltage protection is not populated on Standard or Pro: the TVS array
  and series limiting resistors are omitted, since accidental PoE injection is not
  a design target for those tiers. For Enterprise and Mission Critical it is an
  open question (OQ-8). Where protection is populated (only under OQ-8), size the
  VCC series resistor together with the power budget, since it trades protection
  against 5VSB headroom at the far end of a cable.
- Connector must have a documented current rating of at least 1.5A.
- Hub bulk power comes in on a dedicated 2-pin +5VSB power-in connector, separate
  from the RJ-45 interface, fed from the 24-pin ATX module; the Hub then
  distributes 5VSB to its ports over the RJ-45 VCC pin. Locked for every Hub
  (resolves OQ-1). RJ-45 VCC therefore carries per-port distribution only, not
  the trunk. Use the simplest 2-pin part rated for the full Hub trunk with margin
  (working selection: 2-pin JST-XH, >=3A); never Mini-Fit Jr.

Pin allocation (LOCKED; pin 7 use and DETECT encoding still pending):

| Pin | Cat5e pair | T568B color | CEC function | Tiers |
|---|---|---|---|---|
| 1 | Pair 1 | White-orange | VCC (+5VSB power) | All |
| 2 | Pair 1 | Orange | GND (power return) | All |
| 3 | Pair 3 | White-green | CAN1_H (control plus low-rate telemetry) | All |
| 4 | Pair 2 | Blue | STREAM_P (RS-485 data, module to Hub) | Pro+ |
| 5 | Pair 2 | White-blue | STREAM_N (RS-485 data, module to Hub) | Pro+ |
| 6 | Pair 3 | Green | CAN1_L | All |
| 7 | Pair 4 | White-brown | AUX_REF (precision reference) | Pro+, pending OQ-3 |
| 8 | Pair 4 | Brown | DETECT / module-ID (analog single-wire sense) | All |

- Pair 3 (pins 3 and 6) is the T568B split pair and stays twisted in the cable.
  Standard tier leaves pair 2 (pins 4 and 5) unused, terminated at the module
  side.
- DETECT (pin 8) is an analog single-wire identity and presence sense: a
  precision resistor from pin 8 to GND on each module, read by the Hub through a
  fixed pull-up to VCC as a divider on an ADC channel. An open line reads near
  VCC and means no module. The resistor code table is pending (OQ-6).

Communication:
- All control and command traffic lives entirely on CAN, on pair 3, for every
  tier. CAN carries control plus low-rate telemetry.
- Classical CAN at 500 kbps on Standard; CAN-FD on Pro and above, on the same
  pair. Transceiver: TJA1462A (run in classical mode on Standard). Termination:
  fixed 120 ohm split at the Hub.
- RS-485 carries high-bandwidth telemetry streaming only, one direction, module
  to Hub, on pair 2. It carries no control traffic. Present on Pro modules and
  Pro+ Hubs only. Standard does not populate it.

Per-tier hardware:
- Hub Standard: ESP32-S3, 4 ports, classical CAN, USB Full Speed. v1.1 decisions
  carry forward (LP5907 LDO, 4700 uF aluminum-polymer hold-up, 1 ohm 1 W inrush
  resistor, SS14 reverse-polarity Schottky, TPS3839K33 supervisor, 7x SK6812
  MINI-E LED chain, GPIO0 hidden service button, 4x M2.5 chassis-grounded
  mounting, 4-layer 1.6 mm ENIG matte-black PCB, identity by factory MAC plus
  database with no eFuse or secure element).
- Hub Pro: ESP32-P4, 8 ports, CAN-FD plus RS-485 streaming receivers (one
  receiver per port as the working basis, pending OQ-5), USB High Speed.
  Bulk power on the dedicated 2-pin +5VSB power-in connector (OQ-1, spec §2.7).
  Otherwise follows the Hub Standard base.
- 12VHPWR Pro module: ESP32-P4, INA240A3 per-pin current-sense amps on per-pin
  shunts, LTC2358-18 8-channel simultaneous-sampling 18-bit SAR ADC, 47k/10k
  rail-voltage divider into one LTC2358 channel, about 900 kB/s streaming
  (roughly 50 kHz x 6 channels) over RS-485, CAN-FD control.
- Standard modules (24-pin ATX, EPS 8-pin, PCIe 8-pin, 12VHPWR Standard):
  ESP32-S3-MINI-1; per-rail sensing via INA238 (16-bit I2C current/voltage
  monitor), one per sensed rail on the module I2C bus, sized for >=1 kHz polling.
  24-pin senses 12V/5V/3V3/5VSB; the others sense the single 12V rail. No CAN
  termination (Hub-only).

LED current:
- SK6812 aggregate current must be capped in firmware (global brightness or
  current budget) so the worst case stays within the connector rating with
  margin. Seven SK6812 at full white draw on the order of 0.4A per board, and a
  Hub plus several full-white downstream modules can push aggregate draw toward
  2A. With bulk power on the Hub's dedicated 2-pin power-in (OQ-1 resolved), that
  draw no longer concentrates on a single RJ-45 VCC pin, but it is still capped
  in firmware (OQ-2).

Cross-tier behavior:
- A module never fails to function in any Hub. A Pro module in a Standard Hub
  runs CAN control and event telemetry normally; its streaming pair is connected
  at the jack but stays dark because the Standard Hub populates no RS-485
  receiver. This is the intended graceful-degrade behavior and is expected.

## Open questions (do NOT assume; flag or ask)

These are unresolved in the spec. Do not silently pick an answer. If a design
choice depends on one of these, surface it and ask, or implement it behind a
clearly labeled branch or variant.

- OQ-1 (RESOLVED 2026-05-30): Hub bulk power input. Locked to a dedicated 2-pin
  +5VSB power-in connector on every Hub, separate from the RJ-45 interface, fed
  from the 24-pin ATX module; the Hub distributes 5VSB to its ports over the
  RJ-45 VCC pin. See spec §2.7. This removes the single-pin trunk constraint.
- OQ-2: LED current cap value and the maximum LED state to budget for.
- OQ-3: Precision reference path. Path A (distributed AUX_REF on pin 7,
  calibrated per cable length, with local RC filtering) versus Path B (local
  REF3033 on each Pro module, freeing pin 7). Spec recommendation: Path B. Until
  this is locked, treat AUX_REF on pin 7 as provisional.
- OQ-4: Cable length SKUs and whether Pro modules are allowed on arbitrary user
  cables. Interacts with OQ-3.
- OQ-5: RS-485 topology. One receiver per Hub port (point-to-point, working
  basis) versus a shared multidrop bus across ports.
- OQ-6: Module-ID encoding. The full list of module types and tiers that need
  distinct analog ID codes, needed to finalize the pin 8 resistor table.
- OQ-7: Whether to fully specify Enterprise and Mission Critical now or keep them
  at platform-summary level.
- OQ-8: PoE/over-voltage protection for Enterprise and Mission Critical. Standard
  and Pro do not populate per-pin TVS + series-resistor protection (§2.4); decide
  whether Enterprise/MC populate it (PoE-survivable to ~57V) for their deployment
  environments.

## Active action item

The Hub Standard and 12VHPWR schematics still show Mini-Fit Jr footprints and
must be re-cut to RJ-45 before any board order. Treat those schematics as the
stale artifacts and the spec as current. After a re-cut, verify that no Mini-Fit
Jr footprint remains and that the eight RJ-45 pins map exactly to the pin
allocation table above.

## KiCad environment

- Target KiCad 10 (current stable in the 10.0.x series). Do not save project
  files with an older major version; the file format is forward-only and a board
  saved in 10 will not open in 9. Keep the local install and any CI or container
  on the same major version.
- `kicad-cli` ships with KiCad and runs headless. It must be on PATH wherever
  Claude Code runs. For CI or a container, use the official KiCad kicad-cli Docker
  image rather than a full GUI install.
- Library paths are project-relative via `${KIPRJMOD}`.
- Pinned toolchain version lives in `versions.env` (KiCad major pinned to 10, the
  10.0.x series); the scripts and CI read it. The `.kicad_*` format is
  forward-only.
- The repo is self-contained for clone parity: official and third-party parts are
  vendored into `lib/vendor/`, their 3D models into `lib/3dmodels/`, all
  referenced by `${KIPRJMOD}`-relative paths — no machine-global libraries.
  `scripts/vendor-libs.sh` brings parts in at the pinned library tag. Never
  reference `${KICAD*_3DMODEL_DIR}` or absolute paths.

## Commands to use

Run from a board directory and substitute the board file name. ERC and DRC
return exit code 0 on a clean run and 5 when violations exist, and emit JSON for
parsing.

```bash
# Electrical rule check (schematic)
kicad-cli sch erc --exit-code-violations --format json -o erc.json BOARD.kicad_sch

# Design rule check (layout)
kicad-cli pcb drc --exit-code-violations --format json -o drc.json BOARD.kicad_pcb

# Netlist: verify connectivity against the locked pin allocation table
kicad-cli sch export netlist -o BOARD.net BOARD.kicad_sch

# BOM: cross-check against the per-board target and the spec BOM summary
kicad-cli sch export bom -o BOARD-bom.csv BOARD.kicad_sch

# Visual check: an image to inspect silk and placement
kicad-cli pcb render -o BOARD-top.png BOARD.kicad_pcb

# Fab outputs (generate into the gitignored /build/ working dir)
kicad-cli pcb export gerbers -o ../../build/BOARD/gerbers/ BOARD.kicad_pcb
kicad-cli pcb export drill   -o ../../build/BOARD/gerbers/ BOARD.kicad_pcb
kicad-cli pcb export pos     -o ../../build/BOARD/BOARD-pos.csv BOARD.kicad_pcb
```

If a `.kicad_jobset` is defined for a board, prefer regenerating all fab outputs
with `kicad-cli jobset run` so settings match the GUI. Confirm exact flags with
`kicad-cli jobset run -h`.

## What Claude should do

- Run ERC and DRC, parse the JSON, and report exactly which nets, footprints, or
  clearances are at fault.
- Verify connectivity from the exported netlist against the locked pin
  allocation table (for example, confirm pin 8 lands on the DETECT resistor
  divider, and confirm pins 4 and 5 carry the RS-485 pair only on Pro+ boards).
- Cross-check the exported BOM against the per-board target and the spec BOM
  summary, and flag drift.
- Author and maintain design rules (`.kicad_dru`) and netclasses. Define a power
  netclass with a minimum trace width sized for the 5VSB trunk worst case: the
  dedicated 2-pin power-in and the Hub's internal 5VSB distribution carry the full
  trunk (toward 2A on the 8-port Pro), while each RJ-45 VCC pin carries only one
  module's draw. DRC then flags any power trace that is too thin. (Final width
  still depends on the OQ-2 LED cap.)
- Maintain the shared library and the vendored libraries (`lib/vendor/`,
  `lib/3dmodels/`), the library tables (project-relative), CI, jobsets, and
  documentation, and keep this file in sync with the spec.
- Confirm universal-interface parts are sourced from `lib/` rather than
  duplicated per board.

## What Claude should NOT do

- Do not hand-edit PCB routing geometry — traces, vias, or component placement
  coordinates — in `.kicad_pcb`. Routing and layout are done interactively in the
  KiCad GUI. This is the boundary that stays in the GUI.
- Editing `.kicad_sch` IS allowed: drafting and tidying a schematic, especially
  library-driven, is reasonable. Treat it as real work, though — wire-to-pin
  connections and junctions are where edited or generated schematics break, so
  after any schematic edit verify with ERC and the exported netlist that every
  pin is connected and there are no stray or overlapping junctions.
- Do not resolve any open question (OQ-1 through OQ-7) by assumption. Surface it
  and ask.
- Do not change a locked decision. If a change seems warranted, propose a spec
  revision first; the spec is ground truth.
- Do not commit generated outputs to `main` as routine churn. Snapshot fab
  outputs under `fab/<rev>/` only at a tagged release.

## Project-specific verification checklist

Use this as a recurring review pass:
- No Mini-Fit Jr footprints remain anywhere; all module-to-Hub connectors are
  RJ-45 8P8C.
- Pinout on every board matches the locked pin allocation table.
- PoE/over-voltage protection is not populated on Standard/Pro; on Enterprise/MC
  it follows OQ-8.
- RS-485 pair (pins 4 and 5) and its receivers exist only on Pro and above;
  Standard leaves pair 2 unused and terminated at the module side.
- CAN termination is a fixed 120 ohm split at the Hub.
- Power netclass trace width covers the trunk worst case (the dedicated 2-pin
  power-in and Hub 5VSB distribution carry the trunk; RJ-45 VCC is per-port); the
  firmware LED current cap is reflected in the design intent.
- Libraries and 3D models are vendored in-repo and referenced by
  `${KIPRJMOD}`-relative paths only — no machine-global or absolute paths.
- BOM totals are in line with the spec targets.
