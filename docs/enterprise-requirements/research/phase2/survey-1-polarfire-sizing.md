# Survey 1: PolarFire SoC sizing

Grounded against `docs/enterprise-requirements/hub-enterprise-requirements.md` (REQ-HUB-COMMON-001/002/003/006) and `docs/enterprise-mc-requirements-plan-2026-07-01.md` §1a/Phase-2-item-1, and against spec Appendix B.3/B.5 (PolarFire SoC as the consolidated Enterprise/MC candidate). D-ENT-2 (architecture) is already resolved to PolarFire by owner direction — this survey sizes the specific part and prices the compute subsystem for the D-ENT-3 BOM re-baseline.

## Bottom line

**Recommend MPFS095T(S) as the primary target, laid out in the FCVG484 (19×19 mm, 0.8 mm pitch, 484-ball) package, with MPFS025T(S) as a same-footprint cost-reduced fallback.** Rationale:

- **FCVG484 is pin-compatible across MPFS025T / MPFS095T / MPFS160T** ("Devices in the same package type are pin compatible" — Microchip PolarFire SoC Product Overview DS60001656A, Table 2-1/notes). One PCB land pattern spans a 7x logic-element range (23K→161K), so the board doesn't need a respin to grow into a bigger switch/fabric workload later — the same pattern already used elsewhere in this platform (ESP32-S3→C6→C3 on one footprint).
- **025T is the cheapest-viable floor** (~23K LE, smallest package option FCSG325 11×11 mm/0.5 mm pitch, ~$45–50 at 100q est.) — enough hard-RISC-V control plane plus a modest fabric data plane, but only 2 SERDES lanes in the smallest package and 4 in FCVG484, which may be tight if the "TSN-switch data plane" ambition grows beyond the two hardened MSS GbE MACs.
- **095T is the headroom pick** (~93K LE, same FCVG484 footprint, ~$125–135 at 100q est.) — 4× the fabric of 025T for the switch/timestamping/offload logic the spec's data-plane role implies, without jumping to the 160T/250T tier's larger, pricier packages (FCSG536/FCVG784/FCG1152).
- **160T/250T/460T are oversized for a Hub compute chip alone.** 250T is the part actually used on the $489 Icicle Kit dev board (whole-board price, not chip price); 460T is not a standard-priced/stocked part at all — DigiKey/Mouser require a manufacturer-approved quote, consistent with it being reserved for real switch-ASIC-class fabric loads, not a telemetry-Hub control plane. Neither looks justified unless Mission Critical's redundant-everything data plane needs materially more transceiver lanes/DDR bandwidth than Enterprise — flag as a MC-specific question, not resolved here.
- **A plain (non-SoC) PolarFire FPGA + Mi-V soft RISC-V core is not the cheaper answer.** At matched fabric size, the non-SoC MPF100T (~100K LE, ~$193 qty1) costs about the same as the SoC MPFS095T (93K LE, ~$189 qty1) — the hard 5-core RV64GC complex, PUF, and (on S parts) the Athena crypto coprocessor come essentially bundled at no extra silicon premium. A soft core would also burn fabric LEs the data plane wants and run far below the hard cores' 667 MHz. No point in the family favors non-SoC+soft-core for this application.

**Load-bearing open item, not a recommendation call:** whether REQ-HUB-COMMON-001's "crypto coprocessor" requires the DPA-hardened Athena TeraFire block specifically changes the part suffix (see "S vs T" below) — this needs an explicit owner/security read before D-ENT-3 locks a BOM line.

## Comparison table — PolarFire SoC family

Source: Microchip *PolarFire SoC Product Overview* DS60001656A, Table 2‑1 (read directly from the primary-source PDF).

| | MPFS025T | MPFS095T | MPFS160T | MPFS250T | MPFS460T |
|---|---|---|---|---|---|
| Logic elements (4-LUT+DFF) | 23K | 93K | 161K | 254K | 461K |
| Math blocks (18×18 MACC) | 68 | 292 | 498 | 784 | 1420 |
| LSRAM blocks (20 kb) | 84 | 308 | 520 | 812 | 1460 |
| Total RAM | 1.8 Mb | 6.7 Mb | 11.3 Mb | 17.6 Mb | 31.6 Mb |
| High-speed SERDES lanes (250 Mbps–12.7 Gbps) | 4 | 4 | 8 | 16 | 20 |
| PCIe Gen2 EP/RP | 2 | 2 | 2 | 2 | 2 |
| Total FPGA I/O (HSIO+GPIO) | 108 | 276 | 312 | 372 | 468 |
| MSS DDR data bus width | 16-bit | 32-bit | 32-bit | 32-bit | 32-bit |
| Smallest package | FCSG325 (11×11 mm, 0.5 mm, 325-ball) | FCSG325 or FCSG536 (16×16 mm, 0.5 mm) | FCSG536 | FCSG536 | FCG1152 only (35×35 mm, 1.0 mm) |
| FCVG484 (19×19 mm, 0.8 mm) available | Yes | Yes | Yes | No | No |
| Standard/orderable at usual distributors | Yes | Yes | Yes | Yes (Icicle Kit part) | **No — quote-only** |

MSS (RISC‑V complex), common to every density: four 64-bit RV64GC (RV64IMAFDC) application cores + one RV64IMAC monitor core, all Fmax 667 MHz, 3.0 CoreMarks/MHz; 2 MB shared L2 (cache, or a **Loosely Integrated Memory / deterministic-scratchpad mode** — relevant to a DDR-optional design, see below); integrated 36-bit DDR4/DDR3/LPDDR4/LPDDR3 controller with SECDED; 128 KB on-die eNVM for boot; 2× GbE MACs, USB 2.0 OTG, MMC 5.1, 2× CAN 2.0, QSPI, 5× UART, 2× SPI, 2× I2C. Fabric is **flash-based (non-volatile), so it needs no external configuration PROM at all** — the design is fully functional standing alone on power-up, unlike an SRAM FPGA. [Microchip PolarFire white paper; PolarFire SoC Booting and Configuration UG0881]

### Security grade: the S-suffix distinction (load-bearing)

The block diagram in DS60001656A footnotes the crypto block explicitly: **"DPA-Safe Crypto co-processor supported in S devices."** Independent search corroboration states it more bluntly: non‑S ("T") parts do not carry the integrated Athena TeraFire F5200B hardware at all; only **S-suffix parts** (MPFS025TS, MPFS095TS, MPFS160TS, MPFS250TS, MPFS460TS — S exists across the whole density range, confirmed via Microchip product pages/distributor listings for 025TS/095TS/250TS/460TS, 160TS corroborated but less directly verified [unverified]) carry the Athena TeraFire coprocessor (RSA/ECC/AES/SHA/HMAC, CNSA-suite support, side-channel/DPA-resistant countermeasures, licensed such that the customer needs no separate Rambus DPA license). Spot pricing suggests the S premium is modest, not a different cost class (e.g., MPFS025TS-1FCVG484I ≈ £61 vs MPFS025T-FCVG484I ≈ $65 — different currency/temp grade, so only a rough signal, [unverified] as an apples-to-apples multiplier). **Recommendation: budget for the S-suffix part (MPFS095TS in FCVG484) as the working assumption**, since spec Appendix B.3 explicitly wants "an Athena crypto coprocessor" and REQ-HUB-COMMON-001 ties the part selection to a crypto coprocessor requirement — but this must be confirmed against the exact requirement wording at Phase 3/4, not assumed silently.

Both grades offer **Industrial temperature (−40 °C to 100 °C Tj)**, which is the sane choice for a Hub product (Military −55 °C to 125 °C exists but is unnecessary here); all price quotes above are for I-temp parts.

## Realistic unit pricing (distributor spot-check, retrieved 2026-07-02 — treat as estimates, not a quote)

DigiKey qty-1 / qty-25 prices for the Industrial-temp, FCVG484-package SKU of each density (an apples-to-apples package/temp cut across the family):

| Part | Qty 1 | Qty 25 | Qty 100 (extrapolated, [estimate]) |
|---|---|---|---|
| MPFS025T-1FCVG484I | $64.98 (E-temp sibling: $59.06 qty1 / $47.99 qty25) | ~$48–52 | ~$40–50 |
| MPFS095T-1FCVG484I | $189.49 | $153.96 | ~$125–140 |
| MPFS160T-1FCVG484I | $279.51 | not published | ~$190–220 |
| MPFS250T-1FCVG484I | $368.98 | not published | ~$250–290 |
| MPFS460T | **no standard price — "requires a manufacturer-approved quote," non-cancelable/non-returnable, custom lead time** | — | [unverified, likely $500–900+] |

These FPGA-class parts do not show DigiKey/Mouser price breaks past qty 25 online; the qty-100 column is a linear extrapolation of the observed ~19% qty-1→25 step, **not a quoted number** — get a real distributor/factory RFQ before D-ENT-3 locks a BOM line, especially since 250T/460T already show "quote required" behavior even at low quantities, which is typical for allocated FPGA product.

Sanity anchors: PolarFire SoC Discovery Kit (a minimal dev board around a smaller device) retails ~$132 ($99 academic); the BeagleV-Fire SBC (MPFS025T, plus DDR/eMMC/Ethernet/USB/connectors/assembly) retails at $150; the Icicle Kit (MPFS250T, full-featured dev board) retails at $489 — all whole-board retail prices, useful only as order-of-magnitude checks on the component-level numbers above.

## Libero licensing reality

Libero SoC Design Suite has four tiers: **Evaluation** (free, full functionality, cannot program a device), **Silver** (free, program-capable, obtained via a MicrochipDirect "Generate Free License" flow, renews **annually**), **Gold** and **Platinum** (paid, broader device/IP support). Direct evidence that Silver covers our sizing range: *"Developing on the PolarFire SoC Icicle kit requires a Libero Silver license, which is free of charge"* — and the Icicle Kit uses **MPFS250T**, the largest standard-priced part in our comparison set, so Silver plausibly covers 025T/095T/160T/250T. One older release note flags a Silver/Gold-specific CoreFIFO generation quirk on `MPF*TS_ES` (engineering-sample, non-SoC) parts — a narrow, dated caveat, not a blanket restriction. **Libero supports 64-bit Linux as well as Windows**, which fits this repo's containerized-toolchain posture (parallel to the KiCad Docker pattern) better than initially expected. The real friction point versus this repo's "fully vendored, offline-reproducible" KiCad philosophy: **Libero licenses are free but node-locked and require annual regeneration through a Microchip account**, not a static file that can be vendored into the repo the way `lib/vendor/` works today — a real (if modest) disaster-recovery-policy gap worth a line in the WSL-ephemeral policy once a PolarFire board program starts. Exact Gold pricing and the FlashPro6 production-programmer cost were not pinned down this pass [unverified].

## Boot / PUF / secure-boot / Athena / CAVP

- **Secure boot**: three options — Microchip factory secure boot, **user-defined PUF-protected secure boot**, or direct eNVM boot. PUF-protected key storage is a base-family feature (dual integrated PUF listed as a general Security Feature, not S-gated).
- **Crypto coprocessor**: Athena TeraFire (EXP-)F5200B, RSA/ECC/AES/SHA/HMAC, CNSA-suite support — **gated to S-suffix parts** per the finding above.
- **CAVP**: multiple sources assert CAVP-certified algorithms and reference a "Table 1-1: NIST CAVP Validation Numbers" in the *PolarFire Family FPGA Security User Guide*, and separately that "more than a dozen" CAVP certifications exist across the TeraFire-core product line. **I could not directly pull the actual certificate numbers or confirm they're current** (the security user guide PDF didn't extract cleanly, and a NIST CAVP database cross-check wasn't completed this pass) — **[unverified, needs a follow-up pull of the actual cert numbers from CSRC.NIST.gov before REQ-HUB-COMMON-006/091 attestation claims cite a specific certificate]**.
- **Design-flow assurance**: Microchip's single-chip cryptography Design Separation Methodology was reviewed by the UK NCSC (cited in spec Appendix B.3 already); found corroborating press coverage but not the underlying assessment report itself.
- **Anti-tamper**: system controller tamper alarm asserts a fabric-visible signal on detected errors; user logic can command IO-disable, lockdown, reset, or zeroization via the tamper response path — directly relevant to REQ-HUB-COMMON-070/071.
- FIPS 140-3 module-boundary status (relevant to REQ-HUB-COMMON-090) was **not confirmed either way this pass** — [unverified], feeds Phase-2 research item 7 (compliance regime scan), not resolved here.

## Power draw class — and the 5VSB collision

Hard numbers were not obtainable without running Microchip's Power Estimator tool (not available in this environment). The one concrete anchor found is a marketing figure: **"At 1.3 W, PolarFire SoC delivers 6,500 CoreMarks"** — that is the MSS (RISC-V complex) benchmark power alone, not full-device power with fabric/DDR/SERDES/PHYs active. **[Estimate, not a datasheet table value]**: a real design with a modest fabric data-plane workload, one DDR channel, and active GbE MACs likely lands in the **low-to-mid single-digit watts, plausibly 3–10 W** depending on fabric utilization and SERDES activity — this needs a real Power Estimator run before it's load-bearing.

**This is the important finding for this platform regardless of the exact number**: even the 1.3 W MSS-only anchor is already several times the entire existing Hub Standard's typical draw (an ESP32-S3 class board on a 250 mA-class LP5907 LDO), and a real Enterprise design will draw meaningfully more. The platform's §2.9 architecture assumes the **Hub can run fully on the shared/capped 5VSB rail** (OQ-2's LED-budget-driven cap, ~2.5 A shared 5VSB with margin). A PolarFire-class Hub almost certainly **cannot run its full compute load on 5VSB alone** the way Standard/Pro Hubs do — it likely needs **MAIN_5V (the §2.9 PSU-main source) as its primary/only source for full operation**, with 5VSB realistically sufficient only for a minimal standby posture (e.g., the E51 monitor core plus a trickle of fabric, not the full RTOS+data-plane workload). This directly interacts with:
- **REQ-HUB-COMMON-025** (host-down operation on standby power) — may need to be split into "full telemetry/logging on standby power" vs "full compute on standby power," rather than assumed as one undifferentiated capability.
- **REQ-HUB-COMMON-060/061/062** (§2.9 three-source priority-OR, 5VSB budget, persist-on-fault flush) — the power-budget arithmetic underlying OQ-53..56 needs to be redone with a PolarFire-class load, not the ESP32-class load it was scoped against.

Flagging this as a hard interaction to carry into Phase 3, not resolving it here.

## Minimum companion parts — the real BOM adder

| Category | Need | Notes |
|---|---|---|
| FPGA fabric configuration | **None** | Flash-based fabric is self-contained; no external config PROM (a real saving vs. an SRAM FPGA of similar class). |
| RTOS/bare-metal firmware image | Small external QSPI NOR flash recommended (tens of Mbit) | The 128 KB on-die eNVM is boot-stage sized; a real signed RTOS image with A/B anti-rollback slots (REQ-HUB-COMMON-010) likely wants external QSPI. ~$0.30–1 at 100q. |
| Working RAM (DDR) | **Open question, possibly skippable** | The 2 MB L2 has a documented "Loosely Integrated Memory (LIM) mode for deterministic access," and the fabric itself carries 1.8–17.6 Mb of LSRAM/µSRAM depending on density. Since REQ-HUB-COMMON-002 explicitly excludes Linux, a lean RTOS/bare-metal control plane may run entirely without external DDR, which would delete a real BOM line (DRAM + termination + a DDR PHY layout burden). **Needs firmware-team confirmation before assuming either way** — flagged, not resolved. If DDR is needed: commodity LPDDR4/DDR4 at modest density, ~$3–8 at 100q. |
| Power rails | **3–5 regulators**, not one | VDD core (1.0/1.05 V), VDDA (must be a *quiet* linear regulator — datasheet-mandated), VDDI/VDDAUX (must share one regulator per bank per the Board Design Guidelines), plus sequencing. Renesas publishes dedicated ISL-family reference designs for (RT-)PolarFire/PolarFire SoC power, and Monolithic Power's MPM3695 power-module family is a plausible point-of-load candidate. Est. $8–20 at 100q in discrete point-of-load parts; more if a single multi-rail PMIC module is used for schedule/space instead. |
| Clocking | Reference oscillator(s) for the 8 PLLs/DLLs | ~$1–3. |
| Ethernet PHY(s) | External PHY per hardened GbE MAC (RGMII/SGMII) | Overlaps Phase-2 item 2 (1000BASE-T uplink survey) — do not double-count; sourced there. |
| Production programming | JTAG header for the design cycle; **FlashPro6 programmer** for factory programming | Header is a per-unit BOM cent-item; FlashPro6 is a one-time capital tool cost, not per-unit [price unverified this pass]. |
| Decoupling/passives | Materially more than the platform's existing boards | A 325–1152-ball BGA needs dozens of decoupling caps under/near the package — an assembly-count and yield consideration even though each part is cheap (~$3–8 bulk at 100q, but real cost is placement/inspection, not part price). |

**Total compute-subsystem BOM adder estimate at 100q, chip + companions, excluding the uplink PHY (surveyed separately) and excluding PCB fabrication-class delta:**
- **MPFS025TS/FCVG484 build**: roughly **$60–90** (chip ~$45–50 + companions ~$15–40, wider if DDR is needed).
- **MPFS095TS/FCVG484 build (recommended)**: roughly **$150–190** (chip ~$125–140 + companions ~$25–50).
- A 160T/250T build would likely run **$220–350+** and forces the bigger FCVG784/FCG1152 packages.

**Not captured in the parts-only numbers above, but real cost**: the jump from the existing platform's simple 4-layer 1.6 mm boards to a BGA-hosting board is very likely a **6+ layer, controlled-impedance stackup** (DDR and SERDES routing), plus 0.5–0.8 mm-pitch BGA assembly (reflow/possibly X-ray inspection) — a genuine step up in PCB fabrication class and assembly cost that belongs in the D-ENT-3 value-based costing (REQ-HUB-COMMON-092) alongside the parts BOM, not folded into the per-chip numbers above.

## Risks / unknowns (explicit, for Phase 3)

1. **S-suffix requirement is unconfirmed against the exact REQ-HUB-COMMON-001 text** — costed both ways above; needs an owner/security call before D-ENT-3 locks a line.
2. **CAVP certificate numbers not independently verified against NIST CSRC** — the family's CAVP claims are well-attested in secondary sources but I could not pull the primary certificate table this pass.
3. **FIPS 140-3 module-boundary status unconfirmed** — feeds Phase-2 item 7, not resolved here.
4. **Total device power is an estimate, not a datasheet number** — needs an actual Microchip Power Estimator run once a target fabric utilization (TSN switch scope) is known.
5. **5VSB-vs-MAIN_5V collision** (see Power section) is a real architecture question for §2.9/OQ-53..56, sized against an ESP32-class load today.
6. **DDR-optional design is speculative** — plausible from the L2 LIM-mode + fabric-SRAM capacity, but unconfirmed against a real RTOS/TLS/networking footprint.
7. **Qty-100 pricing is extrapolated, not quoted** — distributor price breaks for this part class stop publishing past qty 25 online; get a real RFQ.
8. **160TS existence confirmed only indirectly** (a search-engine synthesis, not a direct product-page hit like 025TS/095TS/250TS/460TS) — low risk, but worth a direct Microchip product-page check if 160T is ever considered.
9. **Package/I-O tradeoff**: the smallest package (FCSG325) exposes only 2 SERDES lanes on 025T/095T; if the TSN-switch ambition needs more than the two hardened MSS GbE MACs, FCVG484 (4 lanes) or bigger is required — factor into the final footprint choice alongside the pin-compatibility argument above.

## Feeds

- **D-ENT-3** (BOM re-baseline) — directly, via the priced part-class comparison and the compute-subsystem BOM adder estimate above.
- **REQ-HUB-COMMON-001** (PolarFire part selection, PUF secure boot, crypto coprocessor) — part-class recommendation + the S-suffix flag.
- **REQ-HUB-COMMON-002** (RTOS/bare-metal control plane, fabric data-plane offload) — confirms the hard-RISC-V-plus-fabric split is available at the recommended density; the DDR-optional question feeds the control-plane sizing.
- **REQ-HUB-COMMON-003** (per-device crypto identity rooted in the PolarFire key store) — PUF/sNVM key-storage capability confirmed as a base-family feature.
- **REQ-HUB-COMMON-006** (signed attestation evidence of firmware measurement chain) — digest-integrity-check capability confirmed; CAVP certificate specifics still needed before this can cite a certificate number.
- **REQ-HUB-COMMON-025 / -060 / -061 / -062** (host-down/standby operation, §2.9 power architecture, 5VSB budget) — flagged as needing rework against a PolarFire-class power draw, not resolved.
- Indirectly informs the **D-ENT-2 formal spec-edit close** (Phase 4), by substantiating the owner-directed PolarFire choice with a specific part class.

## Sources

- [PolarFire® SoC Product Overview (DS60001656A), Mouser-hosted PDF](https://www.mouser.com/datasheet/2/268/Microsemi_Microchip_PolarFire_SoC_FPGA_Product_Ove-1879322.pdf) — primary source for the Product Family Table, packaging table, block diagram (incl. the S-device crypto footnote), MSS/FPGA/security feature lists.
- [PolarFire® SoC Product Overview, Microchip-hosted mirror](https://ww1.microchip.com/downloads/en/DeviceDoc/Polarfire_SOC_Product_Overview.pdf)
- [PolarFire® SoC Data Sheet DS00004248](https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/DataSheets/PolarFire-SoC-Datasheet-DS00004248.pdf)
- [PolarFire® SoC FPGAs product page, Microchip](https://www.microchip.com/en-us/products/fpgas-and-plds/system-on-chip-fpgas/polarfire-soc-fpgas) — power/CoreMarks figure.
- [PolarFire SoC FPGA Board Design Guidelines User Guide](https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/UserGuides/PolarFire_SoC_FPGA_Board_Design_Guidelines_User_Guide_VB.pdf) — VDD/VDDA/VDDI/VDDAUX rail rules.
- [PolarFire Family Memory Controller User Guide](https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/UserGuides/PolarFire_FPGA_PolarFire_SoC_FPGA_Memory_Controller_User_Guide_VB.pdf) — DDR4/DDR3/LPDDR4/LPDDR3 support.
- [PolarFire™ Non-Volatile FPGA Family white paper](https://ww1.microchip.com/downloads/aemdocuments/documents/fpga/ProductDocuments/SupportingCollateral/microsemi_polarfire_fpga_family_white_paper.pdf) — no external config PROM.
- [PolarFire SoC FPGA Booting and Configuration UG0881](https://ww1.microchip.com/downloads/aemdocuments/documents/fpga/ProductDocuments/UserGuides/microsemi_polarfire_soc_fpga_booting_and_configuration_user_guide_ug0881_eap2_v2.pdf)
- [Military-Grade Security by Design, Microchip](https://www.microchip.com/en-us/products/security/military-grade-security-by-design)
- [Microsemi/Athena TeraFire press release ("S class" crypto coprocessor)](https://www.prnewswire.com/news-releases/microsemi-and-athena-announce-the-terafire-hard-cryptographic-microprocessor-for-polarfire-s-class-fpgas-providing-advanced-security-features-300435552.html)
- [PolarFire FPGAs Single-Chip Crypto Design Flow reviewed by UK NCSC](https://electronicsmaker.com/microchips-polarfire-fpgas-single-chip-crypto-design-flow-successfully-reviewed-by-the-united-kingdom-governments-national-cyber-security-centre)
- [Libero SoC free Silver license — Microchip online docs](https://onlinedocs.microchip.com/oxy/GUID-DED68D42-4F99-40F3-A46A-FD5607E13490-en-US-9/GUID-1A762DDA-2968-4A3D-959B-D7A8E6DA2600.html)
- [Libero SoC Design Suite Licensing, Microchip](https://www.microchip.com/en-us/products/fpgas-and-plds/fpga-and-soc-design-tools/fpga/licensing)
- [Libero SoC Design Suite Versions, Microchip](https://www.microchip.com/en-us/products/fpgas-and-plds/fpga-and-soc-design-tools/fpga/libero-software-later-versions)
- [Mi-V RISC-V Soft CPUs, Microchip](https://www.microchip.com/en-us/products/fpgas-and-plds/system-on-chip-fpgas/mi-v/soft-cpus) — Apache 2.0 soft-core licensing.
- [PolarFire SoC Icicle Kit, Crowd Supply](https://www.crowdsupply.com/microchip/polarfire-soc-icicle-kit) — $489 board price, LPDDR4/SPI-flash/eMMC BOM detail.
- [PolarFire SoC Icicle Kit User Guide](https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/UserGuides/microchip_polarfire_soc_fpga_icicle_kit_user_guide_vb.pdf) — PAC1934 power-rail-sense PMIC.
- [BeagleV-Fire announcement, CNX Software](https://www.cnx-software.com/2023/11/03/beaglev-fire-sbc-features-microchip-polarfire-risc-v-soc-fpga-support-beaglebone-capes/) — $150 SBC using MPFS025T.
- [Renesas ISLRTPFDEMO1Z power reference design for (RT-)PolarFire](https://www.renesas.com/en/design-resources/reference-designs/islrtpfdemo1z)
- [Renesas ISL71148VMREFEV2Z voltage-monitor reference design for PolarFire SoC](https://www.renesas.com/en/design-resources/reference-designs/isl71148vmrefev2z)
- DigiKey product pages (pricing spot-checks, retrieved 2026-07-02): [MPFS025T-FCVG484E](https://www.digikey.com/en/products/detail/microchip-technology/MPFS025T-FCVG484E/16028828), [MPFS095T-1FCVG484I](https://www.digikey.com/en/products/detail/microchip-technology/MPFS095T-1FCVG484I/15219733), [MPFS160T-1FCVG484I](https://www.digikey.com/en/products/detail/microchip-technology/MPFS160T-1FCVG484I/15520454), [MPFS250T-1FCVG484I](https://www.digikey.com/en/products/detail/microchip-technology/MPFS250T-1FCVG484I/15520374), [MPFS250T-FCVG484EES (quote-required)](https://www.digikey.com/en/products/detail/microchip-technology/MPFS250T-FCVG484EES/15520492), [MPFS460T-FCG1152EPP](https://www.digikey.com/en/products/detail/microchip-technology/MPFS460T-FCG1152EPP/15520481), [MPF200T-FCG784I (non-SoC)](https://www.digikey.com/en/products/detail/microchip-technology/MPF200T-FCG784I/7356228).
- [MPFS025TS product page, Microchip](https://www.microchip.com/en-us/product/mpfs025ts) — confirms S-variant exists at the smallest density.
