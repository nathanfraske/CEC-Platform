# ENT hub compute — sourcing alternatives survey (2026-07-02)

_Owner ask: "any other alternatives that would work for us — even other parts — with
better than a 30-week non-stocked target?" Three parallel research lanes (sonnet agents,
distributor stock verified same-day). Conclusion folded into master BOM §3a; decision
rows on owner-queue (f3). All stock numbers are point-in-time 2026-07-02._

## The bar: requirements the part(s) must serve

Zephyr-capable hard processor (NO Linux by design) · fabric for 2× RGMII MAC bridges +
precision timing (~5–10K LE min) · secure boot + anti-rollback · PUF-class identity
preferred · DPA-resistant crypto preferred (the S-suffix Athena posture, owner-ratified)
· industrial temp · no radio · BGA fabbable ~6 layers · low power (5V telemetry hub).

## Everything measured IN STOCK today (all lanes combined)

| Part | Stock | Price @1 | Lead | What it is |
|---|---|---|---|---|
| MPFS250TS-FCVG484I | 64 (DigiKey) | $399.74 | 30wk restock | Pin-compatible S-suffix SoC — the zero-design-change hedge |
| **PIC64GX1000-V/FCS** (industrial) | **47 (DigiKey)** | $36.03 | 30wk restock | The PolarFire SoC MSS as a standalone MPU (same 4×U54+E51 cluster, HSS lineage, UPSTREAM Zephyr board support, advertised DPA protection + tamper detectors; PUF wording unconfirmed — FAE question) |
| PIC64GX1000-C/FCS (commercial) | 52 (DigiKey) | $32.43 | 30wk restock | Same, commercial temp |
| **MPF050TC-FCSG325I** | **176 (DigiKey)** | $74.40 | **4wk** | PolarFire Core fabric-only FPGA, 48K LE — the fabric half of a two-chip shape; also the §6.11 Max-tier data-plane candidate |
| STM32H573RIT6 | 2,538 (DigiKey) | $8.48 | 15wk | Zephyr-native MCU w/ TrustZone/SAES/PKA — no fabric; our documented module fallback family |
| S32K344EHT1MMMST | 760 (DigiKey) | $20.39 | 16wk | HSE_B security MCU (our watchdog family) — no fabric |
| MPFS250TS-1FCSG536I | 19 (DigiKey) | $450.14 | 30wk | S-suffix SoC in the FORK package (0.5mm — new board + harder fab class) |
| MPFS095T-FCSG325E | 4 (DigiKey) | $145.73 | 30wk | Non-S, COMMERCIAL temp, fork package — prototype trivia only |
| XC7Z010-1CLG400I | 420 (DigiKey) | $83.56 | 52wk restock | Zynq-7000 — NO PUF, NO DPA crypto (posture downgrade), thin Zephyr |
| XCZU1CG-1SBVA484I / ZU2CG | 46 / "in stock" | $339–350 | 40wk | Zynq US+ CG — HAS PUF + credible Zephyr-on-R5, but several watts + 8–10-layer stackup + Vivado |

Measured DRY (does NOT beat the bar): every 095-density MPFS FCVG484 variant (S and
non-S; non-S = 52wk), MPFS160TS (authorized), MPFS160TLS (preorder 2027-02), Lattice
ECP5 industrial (0/47wk) and commercial (0/40wk), CertusPro-NX (38 pcs/40wk),
SmartFusion2 industrial (0/30wk+, also architecture-fail: M3@166MHz, 2013-era, no PUF),
i.MX RT1170 (backordered across variants), XC7Z020/7007S (0/52wk), Cyclone V SoC
(per-SKU lottery, no PUF, NRND flags; lifecycle-extended to 2045 but that fixes supply,
not security fit), Agilex 3/5 (press-release "orderable", no distributor stock found —
assume allocation queue), Gowin (LCSC-only channel; supply-chain-origin no-go for a
tamper-audited US-market security product; GW1NSR fabric also below the LE floor).

## Lane verdicts

**Lane 1 — Microchip-native.** The standout: **PIC64GX1000 + MPF050TC** (~$110 combined
silicon, both stocked). PIC64GX IS the PolarFire SoC MSS spun out — near-1:1 firmware
reuse (same HSS/Zephyr lineage; PIC64GX even has upstream `pic64gx_curiosity_kit` board
support), and the fabric RTL ports ~1:1 into the MPF050's PolarFire-family fabric under
the same Libero toolchain. Costs vs single-chip MPFS: two BGAs + interconnect fanout; a
REAL new inter-chip link to design and verify (MSS↔fabric is on-die AXI in the MPFS; here
it's board traces — RGMII/SPI/parallel — and a new attack/validation surface for a
tamper-audited product); the MPF Core line's security-feature completeness (bitstream
protection tier) and PIC64GX PUF presence both need FAE confirmation. SmartFusion2:
fails availability AND architecture. No Microchip statement found on the MPFS drought —
treat as open-ended.

**Lane 2 — cross-vendor SoC-FPGAs.** Nothing matches PolarFire's combination (PUF + DPA
+ mature no-Linux RTOS + low power) at better availability. Closest technical match =
Zynq US+ ZU1CG/2CG (real PUF, Zephyr-on-R5) but thin stock, several watts, 8–10-layer
stackup, full Vivado bring-up. Best stock = Zynq-7000 Z-7010 (420 pcs) but it requires
FORMALLY dropping the PUF/DPA requirement — a locked-decision-adjacent security-posture
change, not a substitution. Declined as anything but a documented emergency shape.

**Lane 3 — two-chip MCU+FPGA.** MCU side is healthy (STM32H573 2.5k pcs; S32K344 760)
but the FPGA side is AS DRY as the SoC — the only in-stock fabric part is Microchip's
own MPF050TC, so a cross-vendor two-chip shape solves nothing the Microchip pairing
doesn't solve better with more reuse. Best-in-lane pairing if ever forced: STM32H573 +
MPF050TC (two secure-boot chains to bind, two toolchains).

## LATE-BREAKING (same session): the PolarFire SoC **Core (TC)** line — owner finds

The owner found the real unlock on DigiKey: **MPFS095TC-FCVG484E** (100 pcs, $119 @100,
~1-month lead), **MPFS095TC-FCSG325E** (100 pcs, $109 @100), **MPFS025TC-FCSG325E**
(good stock, $43.70 @100) — all ~1-month ship. The **TC = PolarFire SoC Core** line
(2025 launch): a cost-optimized family that KEEPS the RISC-V MSS complex and the
fabric, ELIMINATES the high-speed SerDes/PCIe transceivers, spans 48K–460K LE, and is
offered in our exact FCVG484 package. A Microchip PCN also lists **MPFS095TC-FCVG484I**
(industrial) as a production device — stock/price unverified, add to the RFQ. This
explains the drought pattern: Microchip's fresh production is ramping the Core line
while the original T/TS line sits in allocation.

Fit against our design (three deltas, one open confirm):
1. **No SerDes/PCIe.** Our fabric plane (2× RGMII MACs to the LAN9370s, pin-7 blocks,
   voter) never touches SerDes. The 1000BASE-T uplink is the question: if the MSS GEM
   SGMII pairs survive on Core (they are MSS-bank, not fabric-XCVR — LIKELY retained,
   FAE-confirm), the uplink is unaffected; if not, the DP83869HM uplink PHY also speaks
   RGMII via fabric GPIO — a pin-budget change, not an architecture change. The MC-Max
   NTB/PCIe state-sync idea dies on Core — but it was already flagged unvalidated, and
   the fabric/LVDS link alternative was the hedge anyway.
2. **No S (Athena/DPA) option visible in the Core line.** REQ-HUB-COMMON-001's
   owner-ratified Athena posture cannot be met on a TC part. What remains (FAE-confirm
   against the Core datasheet): the base-family system-controller security — secure
   boot, SRAM-PUF, bitstream protection, tamper flags. Runtime crypto would fall
   entirely to wolfCrypt software on the MSS — which is ALREADY our FIPS
   embedded-module story; what is genuinely lost is hardware DPA side-channel
   resistance on runtime crypto. Relaxing REQ-001 is an OWNER decision, not a
   substitution.
3. **E temp grade** (TJ 0–100 °C) vs our I-grade baseline — fine for bench/prototypes
   and plausibly fine for an inside-the-chassis product; the PCN'd FCVG484I closes
   this if stocked.

What this means concretely:
- **Prototype silicon: solved.** MPFS095TC-FCVG484E is near-ideal bring-up silicon on
  the production land: same package, same MSS, same fabric primitives, $119, one month
  — every piece of firmware/fabric/board work transfers to a later TS production part.
  It cannot validate the Athena path or (pending confirm) SGMII — everything else yes.
- **Design-for-part-agnosticism (recommendation):** lay out the FCVG484 land with NO
  SerDes dependency (uplink on MSS SGMII if Core retains it, else RGMII) so ONE board
  accepts 025/095/160/250 × T/TS/TC — the whole ladder becomes interchangeable and the
  part decision stays open until buy time. Ball-map compatibility TC-vs-TS in FCVG484
  to be verified at the breakout study (expect SerDes balls NC on TC).
- **Production fork (owner's call, not asked yet):** if the Athena requirement is ever
  relaxed, 095TC at ~$119 is a third of the 250TS hedge price with real availability.
  Until then production intent stays 095TS via factory-direct RFQ.

## Ranked recommendation (synthesis)

1. **Prototype on MPFS095TC-FCVG484E now** (owner find): buy 3–5 (~$360–600) with the
   dev-kit order — production-land bring-up silicon at 1-month lead; production intent
   stays 095TS (factory-direct RFQ, Athena intact). The 250TS hedge buy (f3) becomes
   OPTIONAL insurance for early production rather than the only silicon path — owner
   may downscale it.
2. **Design the FCVG484 land part-agnostic** (no SerDes dependency) so the T/TS/TC ×
   025/095/160/250 ladder is interchangeable on one board — the supply question then
   never blocks layout again.
3. **Factory-direct RFQ covers the whole family:** 095TS (production intent) +
   MPFS095TC-FCVG484I (industrial Core — PCN'd, closes the E-grade question) + 160TS/
   250TS/(025TS) + PIC64GX/MPF050TC. FAE questions attached: MSS-GEM SGMII retention on
   Core, Core-line security feature set (secure boot/PUF/bitstream), TC-vs-TS FCVG484
   ball-map, PIC64GX PUF, MPFS drought outlook.
4. **PIC64GX1000 + MPF050TC stays the DESIGNED two-chip FALLBACK** (both stocked):
   (a) add both parts + the PIC64GX Curiosity Kit to the RFQ/dev-kit order — the
   firmware investment transfers ~1:1 in BOTH directions (same MSS), so this de-risks
   at near-zero marginal firmware cost; (b) FAE questions to attach: PIC64GX PUF
   presence, MPF Core-line security completeness, MPFS FCVG484 supply outlook;
   (c) the two-chip trust-boundary seam goes to the threat-model doc (workstream B) so
   the fallback is security-reviewed BEFORE it's ever needed.
5. **Cross-vendor: documented and declined.** Zynq-7000 = posture downgrade (owner
   decision at minimum); ZU+ CG = stackup/power/toolchain cost with no stock advantage
   over the Microchip pairing. Revisit only if BOTH Microchip paths fail.

Sources: DigiKey product pages per part (see the lane agents' inline citations, retained
in the session record); Microchip PIC64GX1000 product page + Zephyr
`pic64gx_curiosity_kit` docs + PIC64GX HSS GitHub; AMD XAPP1175 (Zynq-7000 secure boot)
+ Zynq US+ security wiki (PUF); Altera lifecycle-2045 PR; Zephyr Zybo board docs.
