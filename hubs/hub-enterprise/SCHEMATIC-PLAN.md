# ENT Hub schematic — capture plan (2026-07-02, format-corrected same day)

_Owner directive: hierarchical capture, each subsystem labelled on its own sheet with all
its sub-components. One schematic serves all six SKUs + the HS silicon option via the
population/DNP matrix (REQ-105); MCX's second-SoC sheet is captured LAST (a replicate of
the proven compute sheet — avoids double rework). Sources of record: master BOM
(`docs/enterprise-requirements/spec-sheets/bom-detailed/`), variants plan (block diagram,
IO budget, edge map), the registers. DRAFT until every sheet passes the verification
protocol below._

**FORMAT CORRECTION (owner ruling, 2026-07-02, same day as the original plan): sheet 01's
first capture pass put all seven of its functional blocks on ONE sheet as dashed-frame
SECTIONS ("weird sub-sheets", the owner's words) — not what "each subsystem labelled on
its own sheet" meant. The corrected, binding rule for every subsystem, 01 through 10:**

> **A subsystem is a thin PARENT sheet (sheet-symbol instances only — no components, no
> dashed-frame section graphics) that fans out to one LEAF sheet PER FUNCTIONAL BLOCK.**
> Each leaf is its own file with its own proper title. A block that repeats identically
> (an RJ-45 port, a T1 PHY lane, a second MPFS socket) is ONE leaf file INSTANTIATED
> multiple times — the classic KiCad repeated-sheet pattern — not one leaf per repetition.

Sheet 01 was rebuilt to this rule (root → `01-power-input.kicad_sch` thin parent →
`01a-efuse-main` / `01b-efuse-5vsb` / `01c-efuse-ext` / `01d-cascade` / `01e-holdup` /
`01f-buck-3v3` / `01g-rail-sense`, seven leaves, one per functional block) — same parts,
same nets, same wiring as the original capture; only the sheet boundaries moved. See
`build_lib.py`'s module docstring and `gen_hub_enterprise.py` for the addressing rules
this relies on, and `scripts/check_hub_ent_sch.py` for the verification (ERC, a flattened
netlist electrical-equivalence check against the pre-correction capture, and a per-leaf
title/no-dashed-frame check). Sheets 02–10 have not been captured yet; the leaf
breakdowns below are the PLANNED split for each, to be captured directly in the corrected
form (no interim flat/dashed-frame draft).

## 1. Sheet map (hierarchical, thin-parent-plus-leaves)

| # | Parent sheet | Leaf sheets (one per functional block; ×N = one leaf file, N instances) | BOM src | Population |
|---|---|---|---|---|
| 00 | `hub-enterprise.kicad_sch` (root) | — (root itself: sheet instances, title/DNP legend; no leaves of its own) | — | all |
| 01 | `01-power-input` (thin parent, **CAPTURED**) | `01a-efuse-main` (TPS25940, MAIN_5V) · `01b-efuse-5vsb` (TPS25940, 5VSB) · `01c-efuse-ext` (TPS25940 + SMAJ5.0A + PJ-002AH, EXT) · `01d-cascade` (2× TPS2121 priority cascade) · `01e-holdup` (reservoir + isolation diode) · `01f-buck-3v3` (TLV62569 + TPS3839K33 supervisor) · `01g-rail-sense` (4× 47k/10k dividers) | BOM-D | all |
| 02 | `02-compute-core` | `02a-mpfs-core` (MPFS095Tx FCVG484 multi-unit symbol: MSS/fabric banks/SerDes-NC/power) · `02b-boot-straps` (SPI-boot polarity per DS60001681H, DEVRST_N) · `02c-jtag` (FTSH-105 header) · `02d-clock` (DSC1123BL5 + decoupling) | BOM-A | all (TC base / TS = HS fit) |
| 03 | `03-compute-rails` | `03a-core-buck` (MIC22705YML-TR, 1.0/1.05 V) · `03b-bank-rails` (1.8/2.5/3.3 V regs) · `03c-vdda-ldo` (quiet analog LDOs) · `03d-sequencing` (PG chain) | BOM-A | all |
| 04 | `04-storage` | `04a-qspi-nor` (W25Q256JV, A/B FW + tamper log) · `04b-emmc` (eMMC 5.1 FBGA-153, JEDEC-standard ballout, density per SKU) · `04c-straps` (shared pull-ups/straps) | BOM-A; REQ-107..109 | all |
| 05 | `05-module-ports` | `05a-port` **×8** (one RJ-45 FTP port: jack SH→GND, DETECT ladder + PESD5V0S1BA + series R, pin-7 network, 5VSB distribution, SS110 + SMAJ58A protection — identical per instance, the repeated-sheet case) · `05b-can-frontend` (TJA1051T/3 + 120 Ω split term, shared bus) · `05c-detect-adc` (ADS7830 I2C DETECT/rail-sense ADC, shared) | BOM-C + §6a | all |
| 06 | `06-t1-dataplane` | `06a-lan9370-core` **×2** (switch core, RGMII → fabric bank pins, MDIO/MDC, straps/clocks/rails — one per LAN9370) · `06b-mdi-frontend` **×8** (CMC + ≥100 V coupling caps + PESD2ETH100 — one per T1 port, 4 per switch) | master §5; survey 10 | all |
| 07 | `07-uplink` | `07a-dp83869-phy` **×1 (×2 MC+)** (MSS-SGMII or RGMII per the Core FAE answer — capture both pin options, strap-selected) · `07b-magnetics-protection` (JXD1 MagJack + RClamp0524PA + GDT) | BOM-B | NET (2nd PHY = MC+) |
| 08 | `08-secio-aux` | `08a-rj11-secio` (EOL loop sense comparator + isolated dry-contact out) · `08b-nanokvm-aux` (5-pin JST-PH, ratiometric 3V3 ref per the platform pattern) · `08c-argb-service` (SK6812 chain + AHCT buffer + service button + board NTC) | BOM-C §5; platform reuse | RJ-11: AIR default/NET on-request; KVM: NET |
| 09 | `09-watchdog` | `09a-watchdog-core` (S32K344 + own XO + supervised LDO + challenge/force-STANDBY GPIO) · `09b-private-can` (its own CAN transceiver + term, isolated from the platform bus) | spec-sheet §F; survey 9 | MC/MCX only (DNP on base) |
| 10 | `10-voting-pair` | replicate of 02/03/04's OWN leaf split for the 2nd MPFS socket (`10-02a-mpfs-core` etc.) + `10a-sync-link` (fabric/LVDS state-sync) + `10b-private-can` (3-node CAN) — captured LAST, per the no-double-rework rule | REQ-104 | MCX only — CAPTURED LAST |

Net-naming: platform conventions (`/CAN_H`, `_P/_N` diff pairs for RGMII/SGMII/T1,
`SENSE*`, `+5V_SYS`, per-port prefixes `P1..P8_`). DNP: SKU population via BOM
fields (the fab DNP matrix), never schematic variants.

## 2. Verification protocol (every sheet, before it counts as done)

1. `kicad-cli sch erc --exit-code-violations` — clean apart from documented-benign classes.
   A thin parent + its leaves adds one class to that documented-benign set:
   `endpoint_off_grid` (warning-only) — a leaf sheet-pin's X must sit exactly on its
   box's real edge, not gridsnapped, for kicad-cli to bind it into the flattened net at
   all (see `build_lib.py`'s notes); the resulting stub wire is then off the cosmetic
   1.27 mm grid by construction.
2. Netlist export + scripted connectivity assertions (the repo's netlist-verified
   pattern): a `scripts/check_hub_ent_sch.py` grows one assertion block per sheet
   (e.g. every RJ-45 pin 8 → its DETECT ladder + ESD; pin-7 → series R → fabric GPIO;
   TJA1051 → pins 3/6 on all 8 ports; eFuse PG chain; RGMII pin-map vs the LAN9370
   datasheet map), PLUS a whole-hierarchy check that is thin-parent-format-aware: every
   leaf file exists, carries no components on its parent and no dashed-frame graphics on
   itself, and the flattened netlist's component count and connectivity-group count are
   asserted against the known-good baseline (a re-sheeting must never change the wiring).
3. `python3 scripts/cec_synth_pipeline.py --stage CONFORMANCE`-class locked-decision
   checks where applicable (pin table, DETECT codes, no-Mini-Fit rule).
4. BOM cross-check against the master BOM lines (the bom skill) — every sheet's refs
   reconcile to their subsystem BOM section.
5. DRAFT marker stays until all sheets pass 1–4 + the intake gate.

## 3. Capture order (dependency-driven)

01 power-input (all-reuse parts, unblocks bench thinking) → 05 module-ports (platform
reuse-heavy) → 04 storage → 03 rails → 02 compute-core (needs the generated MPFS
symbol — the long pole) → 06 T1 (needs LAN9370) → 07 uplink → 08 sec-I/O → 09 watchdog
→ 10 voting pair. Sheets are independent files; capture parallelizes once symbols exist.

## 4. Library prerequisites (the actual gate — fan-out running)

Per `docs/enterprise-requirements/board-program/kicad-intake-manifest-2026-07-02.md`:
group agents vendor into SEPARATE new symbol files (`lib/cec-ent-*.kicad_sym`) to avoid
merge collisions (footprints/3D are file-per-part, safe); sym-lib-table registration is
a single consolidation pass afterwards. The MPFS FCVG484 symbol+footprint are
SCRIPT-GENERATED from the packaging UG ball map (484 pins → multi-unit symbol; the
SerDes bank emitted as an explicit NC unit per the part-agnostic SerDes-free land rule).
