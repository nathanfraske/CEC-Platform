# Next-trajectory scoping — HARDWARE / BOARD PROGRAM workstream (raw agent return)

_Scoping fan-out 2026-07-02. One of five; synthesis in `../../next-trajectory-2026-07-02.md`. Agent: sonnet._

## Objectives

- Turn the 114-REQ baseline + detailed BOMs into an executable board program that can go to schematic capture the day the owner ratifies, with zero re-derivation.
- Retire the program's biggest schedule risk first: the MPFS095TS FCVG484 BGA breakout/fab class and its ~18-week lead, independent of ratification timing.
- Establish ONE shared ESP32-P4 + DP83TC814S-Q1 (100BASE-T1) reference block so the four module families implement it once, not four times.
- Vendor the ~30 net-new parts into the repo's `cec-*` library convention now, so schematic capture isn't blocked on footprint/symbol sourcing.
- Sequence module boards off the 12VHPWR Pro board (already schematic-stage, already P4) as the pathfinder.
- Keep every committed-schematic action gated on ratification and the two hard sub-gates (OQ-11 shunts; 12VHPWR Pro DRAFT graduation).

## Board list + sequencing

**Hub**: ENT-NET and ENT-AIR are **one PCB, six SKUs by population only** (REQ-HUB-COMMON-105) — layout never diverges, only fitted uplink/watchdog/2nd-SoC/RJ-11 rows. Long-pole item (FCVG484 BGA, 6-layer 0.8mm class, ~18-wk SoC lead); its prep (breakout study, library intake, RFQ) starts first regardless of ratification date.

**Modules** — all four converge on a uniform **ESP32-P4 + DP83TC814S-Q1 T1 front-end** shared reference sub-circuit (mirrors the platform `lib/` universal-interface pattern), instantiated per family:
1. **12VHPWR ENT** first — smallest delta (identity ≈$0, NTC pair, RS-485→T1 swap, DETECT 4.7k→10k), already P4, already schematic-stage; doubles as the **pathfinder** proving the shared block; must graduate out of DRAFT regardless (REQ-HPWR-002).
2. **EPS ENT** second — shared block + the new ADS131M08 fast-ADC pattern on the simplest (2-cable) interposer.
3. **PCIe ENT** third — same pattern +1/+2 cables; near-zero net-new once EPS lands.
4. **24-pin ENT** last — the only family with no Pro/fast-ADC precedent (full C6→P4 respin + first-time T1), though sensing (INA228) is untouched. Bring-up note: the ENT hub can bench-power off an existing consumer 24-pin for basic power/CAN validation (RJ-45 interface unchanged) — this module is NOT on the hub's bring-up critical path.

## Deliverables

| Deliverable | One-liner | Refs | Effort |
|---|---|---|---|
| FCVG484 breakout/fanout study | 0.8mm 484-ball landing + fanout feasibility on the 6-layer stack, via-in-pad plan | variants-plan §5; bom-a | L |
| LAN9370×2 + RGMII layout study | Dual-switch placement, RGMII skew/length budget, 8-port T1 pinout | master §5; survey 10 | M |
| Power-tree / rail sim | TPS2121 cascade, MIC22705 sizing, ILIM chain, STANDBY hold-up budget | BOM-D | M |
| KiCad library intake (~30 parts) | Vendor MPFS095TS, LAN9370, DP83869HM, DP83TC814S-Q1, MIC22705, DSC1123BL5, W25Q256JV, eMMC FBGA-153, ADS7830/ADS131M08, TPS26621/25940, S32K3x… into `lib/vendor` + `cec-*` per CLAUDE.md | all BOM files | L |
| DFM / panelization plan | 6-layer 0.8mm-BGA fab constraints, impedance (SGMII/USB), ENIG, panel strategy for 6 population variants off one gerber set | variants-plan §5 | M |
| Prototype fab strategy | Fab-house qualification for the new class, proto quantities, DNP matrix | spec sheet §2/§6a | S |
| Shared P4+T1 module reference block | MCU+flash+USB+CAN+DETECT+T1-PHY sub-circuit, designed once, instantiated ×4 | module-ent §0; survey 10 | M |
| 12VHPWR ENT deltas + DRAFT graduation | Identity, NTC pair, T1 swap, ERC/DRC-clean baseline | module-ent §4; REQ-HPWR-002 | M |
| EPS/PCIe ENT fast-ADC block | ADS131M08 (or LTC2358-18) 8-ch simultaneous + T1 front-end | module-ent §2–3 | M / S-M |
| 24-pin ENT MCU respin | C6→P4 + first T1 integration, sensing unchanged | module-ent §1 | M |
| Watchdog block schematic module | S32K3-class + own XO + supervised LDO, MC/MCX only | variants-plan §7; survey 9 | M |
| Mis-plug port-protection block | Survey-11 eFuse/TVS/coupling-cap network, hub + module sides | master §6a | S |

## Can start NOW vs GATED

**NOW** (paper/vendoring, no board commits): library intake; FCVG484 breakout STUDY; LAN9370+RGMII layout study; power-tree sim; DFM/panelization plan; fab-house qualification; long-lead RFQ inquiries (MPFS095TS ~18wk, S32K31x).

**GATED on ratification**: every committed `.kicad_sch`/`.kicad_pcb` — hub capture, the shared block's actual schematic instantiation, all 5 module boards.

**Hard sub-gates**: **OQ-11 must close before ANY ENT module board starts** (module-ent §5.5); **12VHPWR Pro DRAFT graduation** before it's cited as baseline (REQ-HPWR-002).

## Open engineering items inherited from the BOM

| Item | Assignment |
|---|---|
| Power Estimator run (gates final core-buck pick + MAIN_5V ILIM) | hardware/power agent; needs Libero tool access (owner may need to provision) |
| MC-Max ILIM resistor-swap cascade (24.9k→20k) | hardware agent, downstream |
| SPI-boot strap polarity vs DS60001681H Fig 1-7 | hardware agent, at schematic capture |
| SGMII AC-coupling board-side (A/B seam) | hardware agent, at schematic capture |
| DDR fitted vs LIM-only | firmware decision; hardware keeps it population-separable |
| eMMC exact MPN + FBGA-153 density family | sourcing/RFQ agent |
| Watchdog exact S32K31x sibling MPN + price | sourcing/RFQ agent; part-CLASS = owner gate |
| T1 coupling-cap value vs DP83TC814S-Q1 app note | hardware agent — verify survey-10's "≥100V" against TI's app note before lock |

## Dependencies on other workstreams

- **Firmware pinout freeze** before FCVG484 breakout goes study → committed schematic.
- **Security/provisioning**: key-injection fixture header spec before module flashing-front-end layout locks.
- **Validation**: test-point asks (RJ-11 loop, rail-sense, pin-7 edges) folded into layout, not bolted on after.
- **Firmware**: watchdog arbitration architecture informs the S32K3 sibling pick; attestation flow informs pinout.

## Decision points needing the owner

1. **One radio-free build per family serves both postures vs split SKUs** (module-ent §0, unratified). *Lean: one build.*
2. **Fast-ADC choice EPS/PCIe**: ADS131M08 (~$5–8) vs LTC2358-18 (~$18–25). *Lean: ADS131M08 unless a precision REQ forces otherwise.*
3. **Prototype qty + fab house** for the 6-layer/0.8mm-BGA class (JLC-class may not qualify).
4. **EVK-first vs straight-to-board**. *Lean: EVK-first for firmware; board prep in parallel.*
5. **Watchdog part-class ratification** (S32K3 family) — explicit owner gate.
6. **RS-485 backward-compat drop confirmation** (owner-review tag).
7. **DDR fitted vs LIM-only** — joint owner+firmware call.

## Top 5 risks

1. **FCVG484 BGA breakout on 6 layers** may not fan out cleanly alongside SGMII/USB impedance control. *Mitigation: dedicated study now; follow Microchip reference layouts; keep an 8-layer fallback in the DFM plan.*
2. **LAN9370 supply/NDA exposure** — switch datasheets/design-in may be access-gated; the DP83TC814S-Q1 fallback does NOT cover a switch. *Mitigation: confirm open distribution + secure the EVB before layout locks.*
3. **MPFS095TS ~18-week quote-gated lead** — the single biggest schedule risk. *Mitigation: RFQ immediately (pre-ratification); pin-compatible 025T/160T ladder as hedge.*
4. **Single-sourced parts in the stock-risk register** (TPS25940LRVCR, JXD1 MagJack, KH-PCB-6P6C, CL10A225KO8NNNC, TPS7A20 codes). *Mitigation: lock second sources now (Halo HFJ11-1G01E-L12RL, KH-9801/On-Shore PJ006, generic 2.2µF, TPS7A21) before schematic capture.*
5. **OQ-11 shunt closure blocking every module board.** *Mitigation: prioritize OQ-11 as a pre-/immediately-post-ratification task, not a mid-program discovery.*
