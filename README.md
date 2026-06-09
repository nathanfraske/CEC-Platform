# CEC Platform

**CEC is a modular PC power-telemetry system.** Per-rail sensing modules connect
to a central Hub over a single commodity cable (RJ-45). The Hub aggregates
telemetry and forwards it to the host PC over USB. Four tiers — **Standard,
Pro, Enterprise, Mission Critical** — are built from one fundamental design with
progressively populated features.

Modules are **tier-agnostic and degrade gracefully**: any module works in any
Hub, with higher-tier features going dormant when the Hub cannot service them
and activating, without replacement, when the module is moved to a capable Hub.

This repository holds the **KiCad 10 hardware design sources** (schematics,
layouts, the shared component library), the fabrication snapshots, and the
tooling that checks them.

> **Ground truth.** [`CEC-Platform-Ground-Truth-Spec.md`](CEC-Platform-Ground-Truth-Spec.md)
> is the canonical specification and holds precedence over everything else,
> including [`CLAUDE.md`](CLAUDE.md). Read the spec before making any design
> decision. Spec revision: **v1.1.0 (2026-06-09), controlled baseline** (semantic
> versioning; the pre-release v1.0–v3.11 working log is retained in spec §11.1).
> Working-summary revision: **2026-06-09**.

---

## Boards

| Board | Directory | Tier | MCU | Ports | Host link | BOM target (100q) |
|---|---|---|---|---|---|---|
| Hub Standard | [`hubs/hub-standard`](hubs/hub-standard) | 1 | ESP32-S3-WROOM-1-N16R8 | 4 | USB Full Speed | ~$36 |
| Hub Pro | [`hubs/hub-pro`](hubs/hub-pro) | 2 | ESP32-P4 | 8 | USB High Speed | ~$45 |
| Hub Enterprise | [`hubs/hub-enterprise`](hubs/hub-enterprise) | 3 | ESP32-P4 + secure element | n/a | USB HS (+ optional 1000BASE-T1) | ~$50 |
| Hub Mission Critical | [`hubs/hub-mission-critical`](hubs/hub-mission-critical) | 4 | ESP32-P4 + crypto | n/a | redundant uplinks | ~$80 |
| 24-pin ATX module | [`modules/atx-24pin`](modules/atx-24pin) (+ [`atx-24pin-rev2`](modules/atx-24pin-rev2), the current line) | Standard | per module spec | – | – | $35 |
| EPS 8-pin module | [`modules/eps-8pin`](modules/eps-8pin) | Standard | per module spec | – | – | $32 |
| PCIe 8-pin 2-port | [`modules/pcie-8pin-2port`](modules/pcie-8pin-2port) | Standard | per module spec | – | – | $38 |
| PCIe 8-pin 3-port | [`modules/pcie-8pin-3port`](modules/pcie-8pin-3port) | Standard | per module spec | – | – | ~$42 |
| 12VHPWR Standard module | [`modules/12vhpwr-standard`](modules/12vhpwr-standard) | Standard | per module spec | – | – | $49 |
| 12VHPWR Pro module (lead) | [`modules/12vhpwr-pro`](modules/12vhpwr-pro) | Pro | ESP32-P4 | – | – | $98–$99 |

Enterprise and Mission Critical are specified at platform-summary level only
until first customer requirements land (see **OQ-7**).

---

## The universal interface (LOCKED)

Every board — every Hub, every module, every tier — uses the same **shielded
RJ-45 (8P8C)** connector with a **locking boot** as the default shipped variant.
Mini-Fit Jr is retired platform-wide. The shared parts that implement this
interface (RJ-45 FTP jack, SK6812 LED chain, ESP32 module, power input — plus
the optional Enterprise/MC over-voltage protection network, OQ-8) live in [`lib/`](lib) so one change propagates
to every board.

### Pin allocation

| Pin | Cat5e pair | T568B color | CEC function | Tiers |
|---|---|---|---|---|
| 1 | Pair 1 | White-orange | VCC (+5VSB power) | All |
| 2 | Pair 1 | Orange | GND (power return) | All |
| 3 | Pair 3 | White-green | CAN1_H (control + low-rate telemetry) | All |
| 4 | Pair 2 | Blue | STREAM_P (RS-485 data, module → Hub) | Pro+ |
| 5 | Pair 2 | White-blue | STREAM_N (RS-485 data, module → Hub) | Pro+ |
| 6 | Pair 3 | Green | CAN1_L | All |
| 7 | Pair 4 | White-brown | AUX_REF (precision reference) | Pro+, pending OQ-3 |
| 8 | Pair 4 | Brown | DETECT / module-ID (analog single-wire sense) | All |

- **Power.** VCC is +5VSB on a single pin; GND returns on a single pin (no
  paralleling). Hubs take **bulk 5VSB on a dedicated 2-pin power-in connector**
  from the 24-pin module (spec §2.7) and distribute it to ports over RJ-45 VCC, so
  no single jack carries the trunk and per-port VCC stays comfortable. The RJ-45
  connector is still rated **≥ 1.5A**, and firmware **caps aggregate SK6812 LED
  current** (OQ-2). The VCC series protection resistor is sized together with the
  power budget, not independently.
- **Control — CAN.** All control and command traffic lives entirely on CAN, on
  pair 3, for every tier. Classical CAN at 500 kbps on Standard; CAN-FD on Pro
  and above. Transceiver TJA1051T/3; fixed **120 Ω split termination at the Hub**.
- **Streaming — RS-485.** High-bandwidth telemetry only, one direction
  (module → Hub), on pair 2. Present on **Pro modules and Pro+ Hubs only**;
  Standard leaves pair 2 unused and terminated at the module side.
- **DETECT.** Analog single-wire identity and presence sense: a precision
  resistor from pin 8 to GND on each module, read by the Hub through a fixed
  pull-up to VCC as an ADC divider. Open line ≈ VCC = no module. Resistor code
  table pending (OQ-6).
- **Protection.** Standard and Pro do **not** populate per-pin PoE/over-voltage
  protection — accidental PoE injection isn't a design target there. A per-pin
  TVS array plus series limiting resistors (PoE-survivable to ~57V) is an open
  question for Enterprise/Mission Critical (OQ-8).

See spec [§2](CEC-Platform-Ground-Truth-Spec.md) for the full interface detail.

---

## Repository layout

```
cec-platform/
  lib/                       # shared library: the locked universal interface
    cec.kicad_sym            #   symbols (authored in the KiCad Symbol Editor)
    cec.pretty/              #   footprints (RJ-45 FTP jack, SK6812, ESP32, power input; protection net is Enterprise/MC, OQ-8)
    3dmodels/                #   3D models referenced by footprints
  hubs/
    hub-standard/            # Tier 1 — ESP32-S3, 4 ports, classical CAN, USB FS
    hub-pro/                 # Tier 2 — ESP32-P4, 8 ports, classical CAN + RS-485, USB HS
    hub-enterprise/          # Tier 3 — platform-summary only for now (OQ-7)
    hub-mission-critical/    # Tier 4 — platform-summary only for now (OQ-7)
  modules/
    atx-24pin/               # Standard (superseded line)
    atx-24pin-rev2/          # Standard (current 24-pin line)
    eps-8pin/                # Standard
    pcie-8pin-2port/         # Standard (2 ports / 4 connectors)
    pcie-8pin-3port/         # Standard (3 ports / 6 connectors)
    12vhpwr-standard/        # Standard
    12vhpwr-pro/             # Pro (lead Pro module)
  fab/                       # tagged release snapshots of exactly what was sent to the board house
  corpus/general/            # cross-project rules corpus (SB-13; linted for provenance)
  tests/                     # pipeline unit tests + the golden-board regression (SB-08)
  docker/                    # the routing-container compute plane (kicad-cli/pcbnew 10 + JRE)
  scripts/                   # kicad-cli wrappers, CI helpers, and the agentic routing/synthesis plane
  CEC-Platform-Ground-Truth-Spec.md   # canonical spec (precedence over all)
  CLAUDE.md                  # operating guidance / working summary of the spec
  README.md
  LICENSE  NOTICE            # Apache-2.0
```

Each board is its own KiCad project. The universal-interface parts are sourced
from `lib/` rather than duplicated per board, and library tables use
project-relative paths (`${KIPRJMOD}`) — **never** absolute paths.

---

## Toolchain

- **KiCad 10** (current stable, 10.0.x series). The `.kicad_*` file format is
  forward-only: a board saved in 10 will not open in 9. Keep every local install
  and any CI/container on the same major version.
- **`kicad-cli`** ships with KiCad and runs headless; it must be on `PATH`. For
  CI or a container, use the official KiCad Docker image rather than a full GUI
  install.

### Checks and outputs

Wrapper scripts in [`scripts/`](scripts) drive `kicad-cli`. Each prefers a local
`kicad-cli` and otherwise falls back to the official KiCad Docker image
(override the tag with `KICAD_IMAGE`, default `kicad/kicad:10.0`).

```bash
# Electrical rule check (schematic). Exit 0 = clean, 5 = violations.
scripts/erc.sh hubs/hub-standard/hub-standard.kicad_sch

# Design rule check (layout). Exit 0 = clean, 5 = violations.
scripts/drc.sh hubs/hub-standard/hub-standard.kicad_pcb

# Connectivity netlist and BOM, for checking against the spec.
scripts/netlist.sh hubs/hub-standard/hub-standard.kicad_sch
scripts/bom.sh     hubs/hub-standard/hub-standard.kicad_sch

# Top-side render for a quick silk/placement look.
scripts/render.sh  hubs/hub-standard/hub-standard.kicad_pcb

# Fab package (gerbers + drill + pick-and-place) into the gitignored build/ dir.
scripts/fab.sh     hubs/hub-standard/hub-standard.kicad_pcb

# CI sweep: ERC over every schematic, DRC over every layout. A board with a
# fab/<board>-* snapshot is ALWAYS checked, DRAFT marker or not; the gate fails
# on ERROR-level violations (warnings stay visible in the build/ reports).
scripts/check-all.sh

# Repo hygiene: no Mini-Fit Jr footprints, no absolute library paths, and the
# corpus provenance lint (corpus/general/ + scripts/constraints/).
scripts/checklist.sh
```

Reports and fab outputs are written under `build/` (gitignored). Fab packages
are committed only as tagged release snapshots under `fab/<rev>/`.

### The agentic routing / synthesis plane (Python)

The deterministic compute plane plus its control-plane hooks (see
[`scripts/README-cec_pcb.md`](scripts/README-cec_pcb.md) and
[`docs/self-hosted-router.md`](docs/self-hosted-router.md) for depth):

| Script | Role |
|---|---|
| `scripts/cec_fr.py` | Freerouting candidate generator (DSN/SES round-trip, pours after route, via normalize) |
| `scripts/cec_score.py` | scorer + HARD gates (Kelvin `_HI/_LO`, diff `_P/_N`), one cosmetic DRC filter, `drc_types`/`drc_loci` |
| `scripts/cec_router.py` | the `route()` orchestration loop + decision log (what `route.yml` runs) |
| `scripts/cec_route.py` | pcbnew real-copper hand-routing primitives for the sub-agent routing pass |
| `scripts/cec_dispatch.py` | compute-as-tools (`request_candidates`) + the budgeted `agent_route` tier loop |
| `scripts/cec_synth_pipeline.py` | the synthesis pipeline: cascade stages, placer, physics (IPC electrothermal), `run_pipeline` |
| `scripts/cec_constraints.py` / `cec_hc.py` / `cec_place.py` / `cec_dcir.py` / `cec_loop.py` | constraint registry + checkers, high-current pass, placer, DC-IR, the place→route→check self-correction loop |
| `scripts/cec_ledger.py` | SB-01 durable run ledger + determinism manifest (sibling `cec-runs` repo) |
| `scripts/cec_golden.py` | SB-08 golden-board pipeline regression (run before merging `scripts/**` changes) |
| `scripts/cec_corpus_lint.py` | SB-13/14 corpus provenance lint (wired into `checklist.sh`) |

Self-hosted workflows: `.github/workflows/route.yml` (Route) and `synth.yml`
(Synthesize: `run` / `sweep` / `candidates` modes) — manual `workflow_dispatch`
only; both append the run verdict to the job Summary. On this development box
the same plane runs in the `docker/` routing container
(`docker compose -f docker/compose.yaml run --rm --no-deps routing ...`).

### Self-contained & reproducible (clone parity)

A plain `git clone` is a full-parity project — no dependency on a machine's
global KiCad libraries:

- **Pinned toolchain.** The KiCad version is pinned in
  [`versions.env`](versions.env) (major 10, the 10.0.x series); the scripts and
  CI read it. The `.kicad_*` format is forward-only.
- **Vendored parts.** Official and third-party symbols/footprints are copied into
  [`lib/vendor/`](lib/vendor) and their 3D models into
  [`lib/3dmodels/`](lib/3dmodels), all referenced by `${KIPRJMOD}`-relative
  paths. `scripts/vendor-libs.sh` brings them in at the pinned library tag.
- **Enforced.** `scripts/checklist.sh` (run in CI) fails if any design file uses
  a machine-global `${KICAD*_DIR}` or an absolute path — the signal that a part
  still needs vendoring.

---

## Design-review checklist

A recurring pass, enforced in part by `scripts/checklist.sh`:

- No Mini-Fit Jr footprints remain anywhere; all module-to-Hub connectors are
  RJ-45 8P8C.
- Pinout on every board matches the locked pin allocation table above.
- PoE/over-voltage protection is not populated on Standard/Pro; on Enterprise/MC
  it follows OQ-8.
- The RS-485 pair (pins 4 and 5) and its receivers exist only on Pro and above;
  Standard leaves pair 2 unused and terminated at the module side.
- CAN termination is a fixed 120 Ω split at the Hub.
- Power-netclass trace width covers the trunk worst case; the firmware LED
  current cap is reflected in the design intent.
- Libraries and 3D models are vendored in-repo and referenced by
  `${KIPRJMOD}`-relative paths only (no machine-global or absolute paths).
- BOM totals are in line with the spec targets.

---

## Open questions

Design decisions that are **not** settled in the spec. Do not assume an answer;
surface it. Summarized here, full text in spec [§9](CEC-Platform-Ground-Truth-Spec.md).

| ID | Topic | Spec recommendation |
|---|---|---|
| OQ-1 ✓ locked | Hub bulk power → dedicated 2-pin +5VSB power-in from the 24-pin module; RJ-45 VCC distributes per-port (spec §2.7) | Resolved 2026-05-30 |
| OQ-2 | LED current cap value and max LED state to budget | Confirm a firmware cap |
| OQ-3 | Precision reference: distributed AUX_REF (pin 7) vs. local REF3033 | Path B (local REF3033) |
| OQ-4 | Cable-length SKUs and any-length policy | Pending; interacts with OQ-3 |
| OQ-5 | RS-485 topology: per-port point-to-point vs. shared multidrop | Per-port (working basis) |
| OQ-6 | Module-ID resistor encoding table | Pending module/tier list |
| OQ-7 | Fully specify Enterprise/Mission Critical now, or summary-level | Summary-level for now |
| OQ-8 | Per-pin PoE/over-voltage protection on Enterprise/MC (TVS + series-R, ~57V); Standard/Pro don't populate it | Pending Ent/MC requirements |

Two consequences worth calling out for layout work:

- With **OQ-1 locked** (dedicated 2-pin power-in), the full 5VSB trunk runs on the
  dedicated power-in and the Hub's internal distribution, while each RJ-45 VCC pin
  carries only one module. The **power-netclass minimum trace width** and the
  board `.kicad_dru` still wait on **OQ-2** (the LED cap) to fix the worst-case
  current.
- **AUX_REF on pin 7** is provisional pending **OQ-3**; treat it as such.

---

## Status

This is an early-stage hardware repository. The directory structure, shared-
library home, tooling, CI, and documentation are in place. The KiCad design
artifacts land per board over time: symbols, library-driven schematics, and
library tables can be drafted in-repo (then verified with ERC and the exported
netlist), while **PCB routing geometry** is done interactively in the KiCad 10
GUI.

**Carried action item:** the Hub Standard and 12VHPWR schematics still show
Mini-Fit Jr footprints and must be re-cut to RJ-45 before any board order. They
are the stale artifacts; the spec is current.

---

## Contributing

- The spec wins. If a change to a locked decision seems warranted, propose a
  spec revision first rather than diverging in a board.
- Do not resolve an open question (OQ-1…OQ-7) by assumption — surface it.
- Keep library paths project-relative (`${KIPRJMOD}`); never commit absolute
  paths. Vendor any official/third-party part you use
  (`scripts/vendor-libs.sh`) so a clone stays self-contained, and keep the
  toolchain on the pinned KiCad 10 (`versions.env`).
- Run `scripts/check-all.sh` and `scripts/checklist.sh` before pushing layout or
  schematic changes.
- Commit fab outputs only as tagged release snapshots under `fab/<rev>/`, not as
  routine churn.

---

## License

Copyright 2026 Nathan M. Fraske.

Licensed under the **Apache License, Version 2.0**. You may not use the files in
this repository except in compliance with the License. See [`LICENSE`](LICENSE)
for the full text and [`NOTICE`](NOTICE) for attribution; a copy of the License
is also available at <http://www.apache.org/licenses/LICENSE-2.0>.

Unless required by applicable law or agreed to in writing, work distributed
under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
CONDITIONS OF ANY KIND, either express or implied.
