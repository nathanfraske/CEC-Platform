# Next-trajectory scoping — FIRMWARE + FPGA FABRIC workstream (raw agent return)

_Scoping fan-out 2026-07-02. One of five; synthesis in `../../next-trajectory-2026-07-02.md`. Agent: sonnet._

## Objectives

- Stand up the RISC-V/Zephyr toolchain and two-tier boot chain (HSS → wolfBoot/MCUboot → Zephyr) on off-the-shelf PolarFire dev kits so board bring-up is firmware-ready on day one, not firmware-blocked.
- Build the FPGA fabric IP library — RGMII MAC bridge ×2, pin-7 SYNC/FREEZE relay + heartbeat-challenge timer, gPTP timestamp capture, MC-Max voter/arbiter — in Libero SoC + simulation, decoupled from the physical board.
- Establish the uniform ESP32-P4 module firmware base (T1 PHY driver, RMII, hardware PTP, pin-7 heartbeat responder, poke-and-ack DETECT, CAN) shared across all four ENT module families.
- Resolve the firmware/software half of the open engineering items pre-board: SPI-boot strap polarity, DDR-vs-LIM decision, external-ADC (ADS7830-class) DETECT/rail-sense scan driver.
- Produce the identity/attestation pipeline (PUF-rooted IDevID provisioning, Athena driver, SBOM/PSIRT tooling, attestation-evidence format) ready to burn into first silicon.
- Keep every deliverable board-layout-agnostic: dev-kit- and simulation-validated now, ported to the real Hub schematic only after ratification.

## Deliverables

1. **Boot chain prototype** (HSS → wolfBoot/MCUboot → Zephyr, signed + anti-rollback) — REQ-HUB-COMMON-001/002/010/011/014 — **L**
2. **Zephyr BSP skeleton** (fork of `mpfs_icicle`/discovery board files toward a future `cec_hub_ent` board) — REQ-HUB-COMMON-002 — **M**
3. **Fabric IP: RGMII MAC bridge ×2** for the two LAN9370 T1 switches (~5% LE) — REQ-HUB-COMMON-043 — **M**
4. **Fabric IP: pin-7 SYNC/FREEZE relay + heartbeat-challenge timer block** (any-port→all rebroadcast, hardware-timed response window) — REQ-HUB-COMMON-112/113/114, REQ-MOD-COMMON-013 — **M**
5. **Fabric IP: MCX voter/arbiter + checkpointed state-sync logic** — REQ-HUB-COMMON-104 — **L** (novel, checkpointed not lockstep)
6. **External ADC driver** (ADS7830-class I2C, DETECT ×8 + rail-sense scan loop) — REQ-HUB-COMMON-042 — **S**
7. **LAN9370 driver + 802.1AS/gPTP bring-up** — REQ-HUB-COMMON-043/106 — **M**
8. **ESP32-P4 uniform module firmware base** (DP83TC814S-Q1 T1 driver, RMII, PTP, pin-7 responder, poke-and-ack, CAN) — REQ-MOD-COMMON-003/010/013 — **L** (shared across 4 families)
9. **Identity/attestation pipeline** (PUF IDevID provisioning, Athena driver, signed attestation-evidence exporter) — REQ-HUB-COMMON-001/003/006/007 — **L**
10. **SBOM/PSIRT tooling + wolfCrypt FIPS-OE engagement kickoff** — REQ-HUB-COMMON-014/097 — **S**
11. **Watchdog challenge-response protocol spec + reference impl** (part TBD; any Cortex-M kit) — REQ-HUB-COMMON-103 — **M**
12. **STANDBY-posture/persist-on-fault firmware model** — REQ-HUB-COMMON-025/026/062/071 — **M**

## Can start NOW vs GATED

**NOW** (dev-kit or simulation only): 1, 2 (skeleton), 3, 4 (simulation), 6, 7 (EVB bring-up), 8, 9 (software layer; PUF hardware caveat), 10, 11 (protocol + ref impl), 12 (state machine).

**GATED**: fabric IP hardware integration (real RGMII to real LAN9370, 8-port pin-7 skew, MCX NTB link) — on the Hub board existing; DETECT end-to-end timing — on board; PUF/Athena hardware validation — on S-suffix sample availability (decision 1); watchdog final integration — on OQ-79 + board; MCX NTB feasibility — on MSS-NTB firmware confirm (may need 2 Icicle Kits); DDR-path work — on the DDR-vs-LIM decision.

## Pre-board de-risk path

1. **Order**: 2× PolarFire SoC **Discovery Kit** (MPFS095T-1FCSG325E, ~$132 ea — closest die match to the target 095T, cheapest, in stock); 1× **Icicle Kit** (MPFS250T, ~$489–600) ONLY if PCIe/NTB or bigger-fabric spike is needed; 2× ESP32-P4 dev boards (ESP32-P4-Function-EV-Board class); 1× **EVB-LAN9370**; 1× ADS7830-class breakout; FlashPro programmer; Libero SoC + SoftConsole.
2. **Toolchain first**: Libero, SoftConsole, west/Zephyr; HSS → wolfBoot → Zephyr signed "hello world" on the Discovery Kit — validates the whole boot-chain plumbing before any custom fabric IP.
3. **Fabric IP skeleton**: synthesize RGMII bridge + pin-7 relay/heartbeat blocks in Libero, simulate, load onto Discovery fabric, loop back with GPIO/logic analyzer.
4. **LAN9370 in isolation**: drive EVB-LAN9370 over SPI/MDIO/RMII — register access, switching, 802.1AS timestamps — in parallel with step 3.
5. **ESP32-P4 module base**: RMII + DP83TC814S-Q1 breakout on the P4 dev board; confirm hardware 1588/PPS in ESP-IDF with a real T1 link to the EVB-LAN9370 — the first true end-to-end gPTP path.
6. **ADC + PUF spikes last**: ADS7830 scan-loop timing on the Discovery Kit; PUF/Athena demo — flag immediately if the non-S/FCSG325 kit won't expose what the S-suffix FCVG484 target needs.
7. **Defer** the MC-Max NTB/PCIe spike until 1–6 land (most expensive, lowest-priority tier).

## Dependencies on other workstreams

- **Security-protocol specs**: key custody (REQ-011, D-ENT-5), attestation wire format, enrollment format — identity pipeline's external contract needs them.
- **Board program**: pin/bank assignment, DDR-vs-LIM, SPI-boot strap confirm — IP is portable, pinout/memory map are not.
- **Validation/compliance**: FIPS/wolfCrypt OE engagement starts now in parallel (vendor conversation, not code); mis-plug injection consumes firmware-side detection logic once boards exist.
- **Owner ratification**: watchdog part class (OQ-79), dev-kit strategy, Phase-4 pin-7 edit — upstream of "final" firmware; prototypes proceed on working assumptions.

## Decision points needing the owner

1. **Dev-kit strategy vs S-suffix/package mismatch**: Discovery Kits (non-S, FCSG325) now vs RFQ a real `MPFS095TS-1FCVG484I` sample vs Icicle. *Lean: 2× Discovery now for toolchain/RTOS; RFQ a real 095TS sample the moment PUF/Athena bring-up needs it.*
2. **Zephyr vs bare-metal for the E51 monitor core** (watchdog/force-STANDBY timing guarantees). *Lean: Zephyr per REQ-002, confirm at bring-up.*
3. **Watchdog exact MPN** (OQ-79 open): prototype protocol-first on any Cortex-M kit. *Lean: proceed protocol-first, defer MPN to RFQ.*
4. **DDR vs LIM-only firmware architecture**. *Lean: LIM-only first, DDR as additive config once the decision lands.*
5. **MC-Max NTB spend** (~$1000+ two-Icicle spike pre-board for a later-tier SKU). *Lean: defer; not on the base/MC critical path.*

## Top 5 risks

1. **S-suffix/package mismatch on dev kits** — PUF/Athena work may not transfer. *Mitigation: RFQ a real sample / FAE die-parity confirm before deep PUF integration.*
2. **Zephyr MPFS driver maturity thin** (fabric MACs, eMMC, external ADC) vs the vendor's Linux-first ecosystem. *Mitigation: spike the exact driver set on the Discovery Kit before committing; HSS+bare-metal fallback.*
3. **No precedent for bridging 2× LAN9370 into custom fabric MACs** — from-scratch Libero IP, unknown LE/timing closure. *Mitigation: validate LAN9370 on its EVB independently first, isolating switch risk from fabric-bridge risk.*
4. **External-ADC scan latency** across DETECT ×8 + rail-sense + RJ-11 may not meet mis-plug detection expectations. *Mitigation: measure worst-case I2C scan-loop timing on the Discovery Kit now.*
5. **MSS NTB support unvalidated** — if it can't do the checkpointed mode, REQ-104's MC-Max assumption breaks. *Mitigation: spike or FAE query BEFORE the Phase-4 edit locks MC-Max architecture.*
