# ENT Hub schematic — capture plan (2026-07-02)

_Owner directive: hierarchical capture, each subsystem labelled on its own sheet with all
its sub-components. One schematic serves all six SKUs + the HS silicon option via the
population/DNP matrix (REQ-105); MCX's second-SoC sheet is captured LAST (a replicate of
the proven compute sheet — avoids double rework). Sources of record: master BOM
(`docs/enterprise-requirements/spec-sheets/bom-detailed/`), variants plan (block diagram,
IO budget, edge map), the registers. DRAFT until every sheet passes the verification
protocol below._

## 1. Sheet map (hierarchical)

| # | Sheet | Contents (all sub-components on-sheet) | BOM src | Population |
|---|---|---|---|---|
| 00 | `hub-enterprise.kicad_sch` (root) | Sheet instances, inter-sheet hierarchical labels, power flags, title/DNP legend | — | all |
| 01 | `01-power-input` | 3× TPS25940 eFuse fronts (MAIN_5V/5VSB/EXT, PG/FLT/EN) → 2× TPS2121 cascade → +5V_SYS; hold-up bank + persist-flush sense; 3V3 buck; per-source 47k/10k rail-sense dividers; J power connectors | BOM-D | all |
| 02 | `02-compute-core` | MPFS095Tx FCVG484 (multi-unit symbol: MSS / fabric banks / SerDes-NC / power), boot straps (SPI-boot polarity per DS60001681H), DEVRST_N, FTSH-105 JTAG, DSC1123BL5 clock, decoupling field | BOM-A | all (TC base / TS = HS fit) |
| 03 | `03-compute-rails` | MIC22705YML-TR core buck (1.0/1.05 V), bank rails 1.8/2.5/3.3, quiet VDDA LDOs, sequencing/PG chain | BOM-A | all |
| 04 | `04-storage` | W25Q256JV QSPI NOR (A/B FW + tamper log); eMMC 5.1 FBGA-153 (JEDEC-standard ballout — generic land, density per SKU); pull-ups/straps | BOM-A; REQ-107..109 | all |
| 05 | `05-module-ports` | 8× RJ-45 FTP (SH→GND), TJA1051T/3 + 120 Ω split term, per-port: DETECT ladder + PESD5V0S1BA + series R, pin-7 network (series R + low-C clamp, fabric GPIO), 5VSB distribution, SS110 + SMAJ58A port protection, ADS7830 DETECT/rail-sense ADC (I2C) | BOM-C + §6a | all |
| 06 | `06-t1-dataplane` | 2× LAN9370 (4-port T1 each): MDI front-ends ×8 (CMC + ≥100 V coupling caps + PESD2ETH100), RGMII ×2 → fabric bank pins, MDIO/MDC, straps, clocks, rails | master §5; survey 10 | all |
| 07 | `07-uplink` | DP83869HM ×1(×2 MC+): MSS-SGMII (or RGMII per the Core FAE answer — capture BOTH pin options, strap-selected), JXD1 MagJack, RClamp0524PA + GDT, PHY rails/straps | BOM-B | NET (2nd = MC+) |
| 08 | `08-secio-aux` | RJ-11 security I/O (EOL loop sense comparator + isolated dry-contact out), NanoKVM aux 5-pin JST-PH (ratiometric 3V3 ref per the platform pattern), SK6812 chain + AHCT buffer, service button, board NTC | BOM-C §5; platform reuse | RJ-11: AIR default/NET on-request; KVM: NET |
| 09 | `09-watchdog` | S32K344 (working part; exact sibling at RFQ) + own XO + supervised LDO + challenge/force-STANDBY GPIO + private CAN | spec-sheet §F; survey 9 | MC/MCX only (DNP on base) |
| 10 | `10-voting-pair` | 2nd MPFS socket = replicate of 02/03/04 + fabric/LVDS state-sync link + private 3-node CAN | REQ-104 | MCX only — CAPTURED LAST |

Net-naming: platform conventions (`/CAN_H`, `_P/_N` diff pairs for RGMII/SGMII/T1,
`SENSE*`, `+5V_SYS`, per-port prefixes `P1..P8_`). DNP: SKU population via BOM
fields (the fab DNP matrix), never schematic variants.

## 2. Verification protocol (every sheet, before it counts as done)

1. `kicad-cli sch erc --exit-code-violations` — clean apart from documented-benign classes.
2. Netlist export + scripted connectivity assertions (the repo's netlist-verified
   pattern): a `scripts/check_hub_ent_sch.py` grows one assertion block per sheet
   (e.g. every RJ-45 pin 8 → its DETECT ladder + ESD; pin-7 → series R → fabric GPIO;
   TJA1051 → pins 3/6 on all 8 ports; eFuse PG chain; RGMII pin-map vs the LAN9370
   datasheet map).
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
