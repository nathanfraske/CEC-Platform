# CLAUDE.md

Operating guidance for Claude Code working in the CEC platform repository.

## Ground truth and precedence

`CEC-Platform-Ground-Truth-Spec.md` is the canonical specification and holds
precedence over everything else, including this file. Where this file and the
spec disagree, the spec wins, and this file should be updated to match. Treat
this file as a working summary plus operating instructions, and read the spec
before making any design decision.

Spec revision reflected here: v1.6 (2026-05-31).

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
| 24-pin ATX module | modules/atx-24pin | Standard | ESP32-S3-MINI-1 | - | - | $35* |
| EPS 8-pin module | modules/eps-8pin | Standard | ESP32-S3-MINI-1 | - | - | $32 |
| PCIe 8-pin module | modules/pcie-8pin | Standard | ESP32-S3-MINI-1 | - | - | $38 |
| 12VHPWR Standard module | modules/12vhpwr-standard | Standard | ESP32-S3-MINI-1 | - | - | $49 |
| 12VHPWR Pro module (lead) | modules/12vhpwr-pro | Pro | ESP32-P4 | - | - | $98 to $99 |

Every board uses the RJ-45 connector defined below. Enterprise and Mission
Critical are specified at platform-summary level only until first customer
requirements land (OQ-7); the Enterprise tier additionally carries an RJ-11 trust
channel and a secure element, and Mission Critical adds redundant power, CAN, and
trust.

*The 24-pin $35 target predates the v1.4 move to four INA228 parts (spec §8);
expect a modest increase over the INA238 baseline. Revisit once shunt parts
(OQ-11) and the INA228 line cost are quoted.

## Locked decisions (do not change without explicit instruction)

These are settled in the spec. Do not alter them, and flag any schematic,
layout, or BOM that contradicts them.

Connector and physical interface:
- Module-to-Hub connector is RJ-45 (8P8C) for all tiers, all modules, all Hubs.
  Mini-Fit Jr is retired as the module-to-Hub interconnect and as the Hub
  bulk-power connector platform-wide. (It is NOT banned from a module's PSU-side
  power path: the 24-pin ATX module legitimately uses Molex Mini-Fit Jr headers
  there — that is the ATX standard connector, spec §2.8. See below.)
- Locking-boot RJ-45 is the default shipped variant. Mechanical-keyed variants
  remain available for high-security deployments. Shielded (FTP) jacks on Hub and
  modules.
- PoE/over-voltage protection: the spec (§2.4) LOCKS per-pin over-voltage
  protection (TVS array + series limiting resistors, PoE-survivable to ~57V) on
  EVERY RJ-45 pin of every Hub and module, platform-wide. The current boards do
  NOT populate it on Standard or Pro — this is a recorded spec-versus-board
  DIVERGENCE (OQ-14), not a settled decision. Do not treat the board state as
  ground truth: the spec requirement stands until OQ-14 ratifies the drop or
  restores the protection. Whether Enterprise/MC populate it is the second half
  of OQ-14. Where protection is populated, size the VCC series resistor together
  with the power budget, since it trades protection against 5VSB headroom at the
  far end of a cable.
- Connector must have a documented current rating of at least 1.5A.
- Hub bulk power comes in on a dedicated 2-pin +5VSB power-in connector, separate
  from the RJ-45 interface, fed from the 24-pin ATX module; the Hub then
  distributes 5VSB to its ports over the RJ-45 VCC pin. Locked for every Hub
  (resolves OQ-1). RJ-45 VCC therefore carries per-port distribution only, not
  the trunk. Use the simplest 2-pin part rated for the full Hub trunk with margin
  (working selection: 2-pin JST-XH, >=3A); never Mini-Fit Jr.

Module PSU-side power-path connectors (spec §2.8, LOCKED v1.6 — distinct from the
RJ-45 module-to-Hub interface above):
- 24-pin ATX module is a power-path interposer with TWO Molex Mini-Fit Jr (5569)
  24-circuit MALE headers: input J3 (PSU side) and output J4 (motherboard side).
  No board-mount FEMALE 24-pin ATX receptacle exists as a standard part, so both
  module connectors are male, the same gender as the motherboard header. The
  PSU's own (female) cable plugs onto J3 directly; the run from J4 to the
  motherboard needs a dedicated FEMALE-TO-FEMALE 24-pin ATX bridging cable (a
  female receptacle on each end, since J4 and the motherboard are both male
  headers), supplied by CEC as a platform SKU. Convention: board headers are
  male, the inserting cable end is female. Both J3 and J4 are the Molex 5569
  right-angle male footprint — do not "fix" one to female.
- 12VHPWR modules (Standard and Pro) solder their 12VHPWR (12V-2x6) connector(s)
  directly to the board (board-mounted); no detachable pass-through header and no
  bridging cable. On the melt-prone high-current connector this removes a
  mated-contact pair from the power path.

Pin allocation (LOCKED; DETECT encoding still pending):

| Pin | Cat5e pair | T568B color | CEC function | Tiers |
|---|---|---|---|---|
| 1 | Pair 1 | White-orange | VCC (+5VSB power) | All |
| 2 | Pair 1 | Orange | GND (power return) | All |
| 3 | Pair 3 | White-green | CAN1_H (control plus low-rate telemetry) | All |
| 4 | Pair 2 | Blue | STREAM_P (RS-485 data, module to Hub) | Pro+ |
| 5 | Pair 2 | White-blue | STREAM_N (RS-485 data, module to Hub) | Pro+ |
| 6 | Pair 3 | Green | CAN1_L | All |
| 7 | Pair 4 | White-brown | Reserved spare (no distributed reference; OQ-3 resolved) | All |
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
  ESP32-S3-MINI-1; no CAN termination (Hub-only). Per-module sensing differs by
  connector (spec §6.1, §6.2):
  - 24-pin ATX: 4x INA228 (20-bit, 195 uV bus LSB, internal energy/charge
    accumulators), one per rail — 12V, 5V, 3V3, 5VSB. The INA228 is a pin- and
    footprint-compatible (VSSOP-10) drop-in for the INA238. IMPLEMENTED in the
    24-pin schematic.
  - EPS 8-pin: INA238 per cable (per-cable granularity), 2 cables populated.
    IMPLEMENTED.
  - PCIe 8-pin: INA238 per cable, 3 cables populated (spec upper bound).
    IMPLEMENTED.
  - 12VHPWR Standard: six INA240 per-pin current-sense amps into the ESP32-S3
    ADC (GPIO1..6), plus a 47k/10k rail-voltage divider into a 7th ADC channel
    (GPIO7). No I2C sensing bus. REF1/REF2 tied to GND (unidirectional forward
    sensing). Accuracy ~+/-1%, see OQ-8. IMPLEMENTED.
  - Acquisition (spec §6.10): the digital-sensor modules (24-pin, EPS, PCIe) run
    their INA228/INA238 in continuous-conversion mode with a per-sensor ~2 s ring
    buffer of 1 kHz averaged samples (pre-roll), and use the ALERT pin as the
    threshold detector / buffer-freeze trigger. (Firmware concern; the ALERT net
    is left available at the part in the schematic.)
  - Shunt values (spec §6.4, LOCKED; parts pending OQ-11): 24-pin 12V/5V/3V3 =
    2 mΩ, 24-pin 5VSB = 25 mΩ; EPS and PCIe per-cable = 0.5 mΩ; 12VHPWR per-pin =
    1 mΩ. IMPLEMENTED in the generator/boards. Low-TCR precision metal-element
    shunts, four-wire Kelvin sense (§6.8) — Kelvin geometry is a layout (GUI)
    task, not in the generated schematic.

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

- OQ-1 (RESOLVED, v1.3): Hub bulk power input. Locked to a dedicated 2-pin
  +5VSB power-in connector on every Hub, separate from the RJ-45 interface, fed
  from the 24-pin ATX module; the Hub distributes 5VSB to its ports over the
  RJ-45 VCC pin. See spec §2.7. This removes the single-pin trunk constraint.
- OQ-2: Total 5VSB current cap (broadened from an LED-only cap). Confirm the
  firmware cap on total CEC 5VSB draw (LED budget is the main lever) and the max
  LED state to budget for, sized within the JST-XH rating and the shared ~2.5A
  5VSB rail with margin. See spec §2.5.
- OQ-3 (RESOLVED, v1.1): Precision reference path. Local REF3033 on each Pro
  module; NO distributed reference; pin 7 is a reserved spare. See spec §3.3.
  (Do not treat pin 7 as AUX_REF anymore.)
- OQ-4: Cable length SKUs and whether Pro modules are allowed on arbitrary user
  cables. Interacts with OQ-3.
- OQ-5: RS-485 topology. One receiver per Hub port (point-to-point, working
  basis) versus a shared multidrop bus across ports.
- OQ-6: Module-ID encoding. The full list of module types and tiers that need
  distinct analog ID codes, needed to finalize the pin 8 resistor table.
- OQ-7: Whether to fully specify Enterprise and Mission Critical now or keep them
  at platform-summary level.
- OQ-8: 12VHPWR Standard rail accuracy. Sensing through the ESP32-S3 ADC (INA240
  + 47k/10k divider) caps accuracy near +/-1%. Accept that, or add a local
  REF3033 to that one board (improves to ~+/-0.3 to 0.5%, INL-limited).
- OQ-9: EPS/PCIe transient capture. The INA238 averages out ms transients;
  decide whether bundled EPS/PCIe need an INA240-style fast path or averaged
  total power suffices.
- OQ-10: Bundled-shunt vertical transition (copper coin vs filled-via field vs
  plated slot) for the ~40 to 55A EPS/PCIe per-cable shunt sites. See §6.7.
- OQ-11: Per-module shunt part selection (value, TCR, tolerance, package, power)
  per the §6.4 shunt table.
- OQ-12: Per-module high-current stackup (L3-rails-with-via-detour vs top-layer-
  rails) per high-current module. See §6.7.
- OQ-13: Energy reporting scope. 24-pin INA228 gives hardware energy/charge on
  all four rails; decide whether energy is scoped to that 24-pin/standby figure
  or extended to total system energy (firmware integration on EPS/PCIe/Pro). The
  24-pin energy is partial and must not be presented as total.
- OQ-14: PoE/over-voltage protection scope (spec-vs-board divergence). (a) Standard
  and Pro: §2.4 LOCKS per-pin protection platform-wide, but current boards drop
  it — ratify the drop or restore the protection. (b) Enterprise/MC: decide
  whether to populate per-pin TVS + series resistors (PoE-survivable to ~57V).
  This subsumes the old OQ-8 PoE question, renumbered so it does not collide with
  the 12VHPWR Standard accuracy question now at OQ-8.

## Active action items

Open item (surface before acting; do not assume the open question):

1. PoE/over-voltage protection (§2.4 / OQ-14): UNRESOLVED spec-vs-board
   divergence — the spec locks per-pin protection platform-wide; current boards
   drop it on Standard/Pro. Do not add or formally drop protection until OQ-14 is
   decided.

Done (kept for context):
- Mini-Fit Jr -> RJ-45 re-cut COMPLETE on every board's module-to-Hub interface
  (after any future edit, verify no Mini-Fit Jr is used for the module-to-Hub
  link or Hub bulk power, and the eight RJ-45 pins match the pin allocation
  table). EXCEPTION: the 24-pin ATX module's PSU-side power path (J3/J4) is
  Mini-Fit Jr by design (ATX standard, §2.8) — that is correct, not a leftover.
- 24-pin INA238 -> INA228 swap IMPLEMENTED; KiCad-10 library modernization and
  the cec-power nickname are in.
- EPS/PCIe per-cable sensing (EPS x2, PCIe x3) and the 12VHPWR Standard 6x INA240
  per-pin redesign IMPLEMENTED in gen-modules.py (INA240 symbol vendored).
- §6.4 shunt values applied across the generator/boards.
- Still firmware/layout work (not schematic): the §6.10 acquisition model and the
  §6.8 Kelvin shunt geometry.

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
- Library-table NICKNAMES must be namespaced `cec` / `cec-*` (e.g. the vendored
  `Package_SO.pretty` is registered as `cec-Package_SO`, not `Package_SO`). A bare
  stock nickname collides with the same-named machine-global KiCad library, which
  on another PC can shadow the in-repo copy and break footprint lookup (this bit
  us once: an old global `Package_SO` lacking `VSSOP-10_3x3mm_P0.5mm` shadowed the
  vendored one, so the INA228 footprints "could not be found"). The `.pretty`/
  `.kicad_sym` FOLDER names stay stock; only the table nickname is prefixed.
  `scripts/vendor-libs.sh verify` enforces this (fails on any non-`cec` nickname).

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
- All module-to-Hub connectors are RJ-45 8P8C and no Mini-Fit Jr is used for the
  module-to-Hub link or Hub bulk power. (The 24-pin ATX module's PSU-side power
  path J3/J4 ARE Molex Mini-Fit Jr by design — §2.8 — and the 12VHPWR module's
  12V-2x6 connector is soldered to the board; neither is a violation.)
- Pinout on every board matches the locked pin allocation table (pin 7 is a
  reserved spare, NOT AUX_REF).
- PoE/over-voltage protection: spec §2.4 LOCKS it platform-wide; current boards
  drop it on Standard/Pro as an OPEN divergence (OQ-14). Flag the divergence;
  do not silently add or remove protection until OQ-14 is decided.
- Module sensing matches §6.1: 24-pin = 4x INA228; EPS = per-cable INA238 (1-2);
  PCIe = per-cable INA238 (up to 3); 12VHPWR Standard = 6x INA240 per-pin +
  divider; 12VHPWR Pro = INA240 + LTC2358-18. (EPS/PCIe/12VHPWR-Std boards still
  need this reconciliation — see Active action items.)
- Shunt values match the §6.4 table (24-pin 2 mΩ / 5VSB 25 mΩ; EPS/PCIe 0.5 mΩ;
  12VHPWR 1 mΩ), Kelvin-sensed.
- RS-485 pair (pins 4 and 5) and its receivers exist only on Pro and above;
  Standard leaves pair 2 unused and terminated at the module side.
- CAN termination is a fixed 120 ohm split at the Hub.
- Power netclass trace width covers the trunk worst case (the dedicated 2-pin
  power-in and Hub 5VSB distribution carry the trunk; RJ-45 VCC is per-port); the
  firmware LED current cap is reflected in the design intent.
- Libraries and 3D models are vendored in-repo and referenced by
  `${KIPRJMOD}`-relative paths only — no machine-global or absolute paths.
- BOM totals are in line with the spec targets.
