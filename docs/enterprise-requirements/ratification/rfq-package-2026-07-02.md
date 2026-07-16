# ENT hub — RFQ package (wave-0)

_Status: DRAFT, wave-0. Owner-approved; **D-ENT-3** (the RFQ-batch authorization) is queued
as a nod (`docs/owner-queue.md` row (d)) — this package is what gets sent the moment that
nod lands. Grounded in `docs/enterprise-requirements/spec-sheets/bom-detailed/hub-ent-bom-detailed.md`
(master BOM, esp. §3 stock-risk register + §3a MPFS sourcing ladder), its four subsystem
passes (`bom-a-compute.md` .. `bom-d-power.md`), `module-ent-spec-sheets.md`, and
`research/sourcing-alternatives-2026-07-02.md`. All target prices are the 100q figures
those documents already verified or estimated, dated 2026-07-02; nothing here re-derives a
price — the RFQ's job is to get real quotes against those figures, not guess new ones.
Qty breaks requested at **100q and 1kq** throughout (pilot run → production step)._

## 0. Cover note (attach as the RFQ's cover letter / first email)

**Who we are / what this is for:** CEC is shipping a modular PC power-telemetry platform
(Hub + per-rail sensing modules) across four tiers (Standard/Pro/Enterprise/Mission
Critical). This RFQ is for the **Enterprise-tier Hub and its module family** — a
security-hardened, tamper-evident fleet product (PolarFire SoC RISC-V compute, dual
100BASE-T1 module fabric, RJ-11 trust-channel I/O, redundant power). We are not a
one-shot hobbyist order: this is a **design win moving through a real pilot-to-production
funnel** — **100q pilot builds now, 1,000+ units/quarter production intent within the
year**, with an Enterprise-Air and Enterprise-Net posture split and an optional
dual-PolarFire "voting pair" SKU on top. We want every line below quoted at both
breaks so we can plan the ramp, and we want lead-time and allocation answers now,
while we're still small, rather than discovering them at the production order.

**The part-agnostic-land story (why this is attractive for allocation):** for the
compute silicon specifically (§1a), our board is being laid out **part-agnostic across
the whole PolarFire/PolarFire-SoC FCVG484 family** — no SerDes dependency, one footprint
accepting the 025/095/160/250 density ladder across the T/TS/TC suffix lines. That means
**we are not asking you to allocate us one exact SKU** — we can commit to the *family*
and let final density/suffix selection track whatever you can actually deliver at volume.
For a vendor managing allocation across a shortage, a customer who can absorb supply
across four interchangeable SKUs instead of demanding one is a materially easier
commitment to make — we'd like that flexibility reflected back in the quote (see the
allocation ask in §1a).

**What we need back:** unit price at 100q and 1,000q, real lead time (not a distributor
"request a quote" placeholder), lifecycle status/roadmap position, and — where flagged —
an allocation commitment. FAE technical questions are attached as Appendix A; please
route to an applications engineer alongside the commercial quote.

---

## 1. Quote-request lines, grouped by vendor/channel

### 1a. Microchip — factory-direct / authorized rep

_Compute-plane FPGA/SoC family (BOM-A `hub-ent-bom-detailed.md` §3a) — request the **whole
ladder on one RFQ**, not a single-part quote, per the part-agnostic-land story above._

| MPN | Qty breaks | Target price (100q) [source] | Ask |
|---|---|---|---|
| **MPFS095TS-1FCVG484I** | 100q, 1kq | $130–165 `[RFQ]` (BOM-A U1; survey-1 same-day pull: $189.49 qty1 / $153.96 qty25) | **Production-intent baseline.** Confirmed dry at every distributor (Mouser non-stocked ~12-wk factory est; DigiKey/Mouser/Octopart block scripted price-break reads). Factory-direct/rep leads (30–52 wk per distributor "mfr standard") are worse than Mouser's 12-wk factory estimate — need YOUR real factory lead + price, and an **allocation ask**: what quantity can you commit to a 100q pilot → 1kq/quarter production ramp, and on what timeline? |
| **MPFS095TC-FCVG484I** | 100q, 1kq | ~$119 @100 extrapolated from the E-grade pull (DigiKey ~100 pcs E-grade $119@100, ~1-month lead) [§3a "7th ruling" row] | Industrial-grade Core-line part is PCN'd but stock/price unverified at distributor level — please confirm real stock, price, and ship date. This is our **production-baseline candidate** (see FAE Q1/Q3 in Appendix A on what's retained vs. the TS line). |
| **MPFS095TC-FCVG484E** | 100q (5–10 for prototype top-off), 1kq | ~$119 @100 (DigiKey confirmed live, 100 pcs, ~1-month lead) [§3a] | Confirm continuity of supply at this grade/price through our pilot window — this is our bring-up silicon and we want price stability while TS/TC production intent is being decided. |
| **MPFS160TS-(1)FCVG484I** | 100q, 1kq | mid-ladder rung, price TBD at quote [§3a "Mid rung"] | Authorized-distribution stock only — an independent broker's claimed 101 pcs is provenance-unacceptable for a tamper-audited trust-anchor part (counterfeit-surface concern); please quote your own authorized channel only. |
| **MPFS250TS-FCVG484I** | 100q (hedge buy: 5–10 units as insurance), 1kq | $399.74 @1 (DigiKey, 64 pcs, 30-wk restock) [§3a "In stock NOW"] | Pin-compatible S-suffix hedge/prototype part — confirm 100q/1kq pricing and whether restock lead improves with a standing PO. |
| **MPFS025T-FCVG484I** (and confirm **025TS orderability**) | 100q, 1kq | $64.98 @1 non-S shown (DigiKey, 2 pcs, 30-wk) [§3a "Low rung"] | Cost-down rung IF a 025TS (S-suffix) line exists — please confirm whether 025TS is orderable in FCVG484 at all, and if so price/lead. |
| **PIC64GX1000-V/FCS** (industrial) | 100q, 1kq | $36.03 @1 (DigiKey, 47 pcs, 30-wk restock) [sourcing-alternatives survey, Lane 1] | Designed **two-chip fallback** (PIC64GX MSS + MPF050TC fabric) — quote alongside the primary SoC ladder so both paths are priced in parallel; include the **PIC64GX Curiosity Kit** dev board. |
| **MPF050TC-FCSG325I** (fallback pair, paired with PIC64GX1000) | 100q, 1kq | $74.40 @1 / $60.45 @25 (DigiKey, 176 pcs, 4-wk lead) [sourcing-alternatives survey] | Healthy stock, quote for volume continuity as the fallback-pair fabric half. |
| **LAN9370-I/KCX** — **×2 per Hub board** | 100q → 200 units/board-run, 1kq → 2,000 units | $14.42 combined for 2 units per §5 of the master BOM (i.e. ~$7.21/ea) [master BOM §5] | 4-port 100BASE-T1 switch w/ integrated PHYs + 802.1AS/1588v2 HW timestamping — **confirm open (non-NDA) distribution** at both qty breaks, and **request an EVB** for bring-up/bench validation ahead of board spin. |

### 1b. Texas Instruments

| MPN | Qty breaks | Target price (100q) [source] | Ask |
|---|---|---|---|
| DP83869HMRGZR | 100q, 1kq | $7.98 (DigiKey, 1,439 pcs in stock) [BOM-B] | Confirm 1kq price break and lead-time stability — this is the primary GbE uplink PHY (promoted from VSC8662 fallback; see BOM-B lifecycle verdict). Also confirm the wider −40 to +125 °C temp grade holds at volume. |
| DP83TC814S-Q1 | 100q, 1kq | $2.39 [module-ent-spec-sheets §0/§1/§2, survey 10] | Per-module 100BASE-T1 PHY across all four ENT module families (24-pin/EPS/PCIe/12VHPWR) — confirm lead time at the module-family volume (each Hub port = 1 module = 1 PHY; 8 ports/hub). |
| TPS25940LRVCR — **×3 per Hub board** (MAIN_5V, 5VSB, EXT eFuse fronts) | 100q → 300 units, 1kq → 3,000 units | $1.7143 (DigiKey, but only 55 pcs in stock at DigiKey / 26 pcs LCSC) [BOM-D §1] | **Lead-time/stock check is the binding ask here** — this part is thin at both channels and not JLCPCB-native. Need a real committed lead time at 300–3,000-unit quantities before D-ENT-3 lock; TPS25940A sibling as a named fallback (confirm pin/feature compatibility and price delta). |
| TPS26621DRCT — **×1 per module**, all four ENT module families | 100q → 100+ units (1/module × pilot module count), 1kq → 1,000+ | $2.07 [module-ent-spec-sheets §0 "mis-plug fail-safe"] | 60V auto-retry eFuse ahead of each module's LDO. Confirm stock/lead at module-fleet volume (this part appears once per module across four families, so real quantity scales with module mix, not just Hub count — flag this to the rep). |
| INA-family carry-overs: **INA228** (24-pin, ×4/module), **INA238** (EPS/PCIe, per-cable), **INA240A3** (12VHPWR + EPS/PCIe fast path, per-pin/per-cable) | 100q, 1kq | Platform-established prices (already sourced on consumer/Pro BOMs; INA240A3DR ~$1.87 per prior hub-standard-family sourcing pass) | These are **existing platform volume parts** — request a **volume-tier quote across the whole family** (228/238/240) reflecting the combined draw from Standard + Pro + ENT lines, not just this RFQ's module count. Confirm the ENT ladder doesn't push any of the three off a price break. |
| ADS131M08 (EPS/PCIe ENT fast-ADC working baseline) | 100q, 1kq | $5–8 `[unv]` [module-ent-spec-sheets §2, spec §6.13] | 8-ch simultaneous 24-bit ΔΣ ADC — confirm real 100q/1kq price (currently unverified/estimated) and stock; this is the cost-vs-precision fork against LTC2358-18 (item below), so both need real numbers to close OQ-21-adjacent choice. |
| ADS7830IPWR | 100q, 1kq | ~$1.00 `[directional]` (LCSC C161747) [BOM-C §5 "comparator note"; hub-ent-bom-detailed §1 reconciliation row] | 8-ch I2C ADC — candidate DETECT/rail-sense/RJ-11-loop digitization path (PolarFire has no on-die ADC). Confirm price/stock at both breaks; also **request an eval breakout board** for bring-up (already flagged as a dev-kit item on the owner queue). |
| LTC2358-18 (12VHPWR ENT/Pro fast-ADC, spec'd alternative) | 100q, 1kq | ~$18–25 `[unv]` [module-ent-spec-sheets §5 open row 3] | 8-ch simultaneous 18-bit SAR — quote alongside ADS131M08 so the cost-vs-precision decision is made against two real numbers, not two estimates. |
| TPS7A20-family (TPS7A2010/TPS7A2018/TPS7A2025/TPS7A2050 decivolt SKUs) | 100q, 1kq | TPS7A2018 $963430-verified / TPS7A2050 verified; TPS7A2010/2025 unverified [BOM-A U7/U8] | Confirm the exact 1.0V and 2.5V decivolt SKUs (TPS7A2010PDBVR / TPS7A2025xDBVR) exist as orderable parts with real stock — see the second-source ask in §3 below if they don't. |

### 1c. NXP

| MPN | Qty breaks | Target price (100q) [source] | Ask |
|---|---|---|---|
| TJA1051T/3 — **platform volume across every board/module** | 100q, 1kq (aggregate across Standard/Pro/ENT Hub + all module families) | $0.40 (LCSC C38695) [platform-established; hub-ent-bom-detailed §2 row C, reused everywhere] | This is the **highest-unit-count part on the whole platform** (one per Hub port group + one per module, across four tiers). Request a **platform-aggregate volume quote**, not a per-board line — we want NXP's best price at true fleet volume, and a stock/lead-time commitment that scales past 1kq without a requote. |
| S32K31x non-lockstep sibling (exact MPN TBD — watchdog block, survey 9 priced the S32K344 ceiling) | 100q, 1kq | S32K344EHT1MMMST priced as the ceiling: $20.39 (DigiKey, 760 pcs, 16-wk) [sourcing-alternatives survey; master BOM §6 open item 7] | **This is an open ask, not a confirmed part** — we need the exact non-lockstep S32K31x-family sibling MPN (our watchdog block, hub-ent-bom-detailed §2 block F, MC/MC-Max only) plus its 100q/1kq price. Please recommend the specific part number that best matches "non-lockstep, HSE_B-class security MCU, no fabric" for a supervisory watchdog role. |
| PESD5V0S1BA (Nexperia — note: Nexperia, not NXP; grouped here as the platform's protection-diode line for RFQ convenience) | 100q, 1kq (aggregate — DETECT ×8/hub + LOOP_IN_A/B ×2/hub + every module's DETECT pin) | $0.03 (LCSC C5261083) [BOM-C §1/§5, platform-locked v2.0] | Same platform-aggregate volume ask as TJA1051T/3 — this part appears on every Hub port and every module's DETECT line across the whole product line. |

_(Note: PESD5V0S1BA is a Nexperia part, not NXP — kept in this group for RFQ-routing
convenience since Nexperia and NXP quotes are often handled by the same distribution
rep; split into its own line item if your rep requires it.)_

### 1d. Others — storage, oscillators, magnetics, connectors

| MPN | Qty breaks | Target price (100q) [source] | Ask |
|---|---|---|---|
| eMMC, FBGA-153, **exact MPN ask** — 8/32/64 GB industrial | 100q, 1kq | $5–9 (8 GB) / $9–16 (32/64 GB) `[est]` [master BOM §2 "Storage" row; REQ-108/109] | **No exact MPN has been picked yet — this is the primary ask.** Please recommend/quote a specific FBGA-153 industrial-temp eMMC part family spanning 8/32/64 GB (single-land, board-compatible across densities per REQ-107) with real 100q/1kq pricing at each density. |
| W25Q256JV (FIQ SOIC-16 or EIQ WSON-8) | 100q, 1kq | FIQ $3.00 / EIQ $3.21 [master BOM §1 "Boot flash density" reconciliation] | Confirm **JV suffix specifically** (3.3V part) — NOT JW; the SS/SN density variants named in an earlier draft were confirmed phantoms, do not requote those. |
| DSC1123BL5-125.0000 | 100q, 1kq | $2.38–2.56 [master BOM §1 "MSS/SGMII reference clock" reconciliation] | 125 MHz LVDS oscillator, populated on **every SKU** (drives MSS_REFCLK_IN_P/N — gates MSS boot regardless of SGMII use). Confirm stock depth at 1kq; SiTime SIT9120 family is Microchip's own named second source (see §3 below). |
| JXD1-0001NL MagJack (Pulse Electronics) | 100q, 1kq | $5.95 (DigiKey 553-3266-ND, 400 pcs) [BOM-B] | Primary shielded GbE MagJack, 2250 VDC isolation. **Stock depth (400 pcs) is thin for anything past 100q — request a 1kq lead-time commitment explicitly**, and quote the Halo second source (below) in parallel. |
| Halo HFJ11-1G01E-L12RL (MagJack second source) | 100q, 1kq | $5.01 @100 (3,103 pcs stock) [BOM-B; master BOM §3 stock-risk register] | Confirm as a qualified drop-in second source for JXD1-0001NL — note it sits exactly at the 1500 Vrms isolation floor (JXD1 has real margin at 2250 VDC), so we need your confirmation this still clears our isolation requirement before treating it as interchangeable. |
| Connectors: FTSH-105-01-L-DV-K (JTAG, Samtec), KH-RJ45-58-8P8C (Kinghelm, module ports ×8/hub), KH-PCB-6P6C (Kinghelm, RJ-11 security I/O), S2B-XH-A / PJ-002AH (power-in, JST/Same-Sky) | 100q, 1kq | $0.967 / $0.60 / $0.08 / $0.0483 / $0.504 respectively [BOM-A/C/D] | Standard confirmatory quote at both breaks; KH-PCB-6P6C specifically flagged thin (~150 pcs at LCSC) — see second-source ask in §3. |

---

## Appendix A — FAE question set (attach as a formal technical attachment, route to Microchip applications engineering)

These derive from master BOM §3a and the REQ-001 (Athena/S-suffix) ratification condition
that gates the production-baseline choice between the TS and TC lines. **Do not resolve
these by assumption — they gate a real architecture decision (§1a above).**

1. **Core-line (TC) security block retention.** Does the PolarFire SoC **Core** family
   (MPFS095TC-FCVG484, and the ladder generally) retain the base-family system-controller
   security block from the T/TS line — specifically **SRAM-PUF-based secure boot**, the
   **user-accessible TRNG**, and the **tamper detectors**? This is the condition our 7th
   ruling put on adopting TC as the production baseline; TC losing this block cancels the
   ruling. (Runtime DPA/Athena crypto is understood to be TC's tradeoff — this question is
   about the base secure-boot/PUF/tamper chain only, not DPA.)
2. **MSS-GEM SGMII retention on Core.** Does removing the high-speed SerDes/PCIe
   transceivers on the Core line also remove the MSS-GEM's SGMII capability, or is SGMII a
   separate MSS-bank function that survives independent of the SerDes transceivers? This
   determines whether our 1000BASE-T uplink stays on SGMII or needs to move to RGMII via
   fabric GPIO on a TC part (a pin-budget change, not an architecture change, per our own
   analysis — but we want Microchip's confirmation, not our inference).
3. **TC-vs-TS FCVG484 ball-map compatibility.** For a board laid out to accept both the TC
   and TS lines in the same FCVG484 land (our part-agnostic design intent, §1a), which
   balls differ between the two? Specifically: **are the SerDes-related balls simply NC
   (no-connect) on TC**, or are they repurposed/reassigned for other functions? We need
   this confirmed before our breakout study locks the footprint.
4. **PIC64GX PUF presence.** For PIC64GX1000 (our designed two-chip fallback, both
   V/industrial and C/commercial grades) — does the datasheet's "advertised DPA protection
   + tamper detectors" language extend to a **confirmed PUF-based identity/key** feature,
   or is PUF wording absent/ambiguous versus the full PolarFire SoC MSS? (Our own survey
   flagged this as "PUF wording unconfirmed" — this is the direct ask to close it.)
5. **MPFS FCVG484 supply outlook.** What is Microchip's own account of the MPFS095TS
   drought (12-wk-to-52-wk factory estimates depending on suffix, no authorized distributor
   stock found in any density at 095) — is this allocation-driven, fab-capacity-driven, or
   something else, and what is the realistic timeline to normal stock? We are asking this
   directly because no public Microchip statement was found in our own research pass.
6. **Libero licensing for the Power Estimator.** What Libero SoC license tier (and cost) is
   required to run the **Power Estimator** tool against our design — this is the single
   open number gating our VDD-core buck final pick (headroom risk flagged in BOM-A) and
   the MAIN_5V eFuse ILIM value (BOM-D's resistor-swap dependency chain). We'd like this
   answered quickly since it's blocking two other engineering decisions.
7. **MSS USB 2.0 OTG ball location on FCVG484.** (Added 2026-07-03 from our breakout
   study, `docs/enterprise-requirements/board-program/fcvg484-breakout-study-2026-07-03.md`.)
   Which FCVG484 balls carry the MSS USB 2.0 OTG interface (ULPI or on-chip PHY pins) on
   MPFS095TC/TS? Our cached ball map (derived from a taped-out FCVG484 design) names no
   USB ball at all, and MSSIO — the likeliest home — is our tightest bank (28 of 38 balls
   already committed at baseline). The answer determines whether USB stays inside our
   6-layer escape budget or becomes an 8-layer trigger; we need it before the sheet-02
   pin-assignment freeze. A pointer to the 095T-specific PPAT (package pin assignment
   table) would close this and question 3 together.

---

## Appendix B — Second-source asks (per the stock-risk register, master BOM §3)

| Primary part | Risk flagged | Second source to qualify | Ask |
|---|---|---|---|
| JXD1-0001NL (MagJack) | 400 pcs at DigiKey | **Halo HFJ11-1G01E-L12RL** | See §1d above — confirm isolation margin (1500 Vrms floor vs. JXD1's 2250 VDC) is acceptable, and quote as an interchangeable BOM alternate at both qty breaks. |
| KH-PCB-6P6C (RJ-11 jack) | ~150 pcs at LCSC | **On-Shore Technology PJ006-6P6C** (also Kinghelm siblings KH-9801-6P6C / KH-9752-6P6C) | Quote as a qualified drop-in second source for the RJ-11 security-I/O jack; confirm footprint/pinout compatibility with the Kinghelm part at both breaks. |
| TPS7A2010/TPS7A2025 (decivolt quiet LDOs) | Existence real per naming convention, stock/price unconfirmed | **TPS7A21 (adjustable)** | If the fixed-voltage decivolt SKUs are thin or unconfirmed at RFQ, quote the adjustable TPS7A21 family as the fallback — same TI quiet-LDO class, set via external FB divider. |
| CL10A225KO8NNNC (2.2 µF/0603 SS cap, platform-wide part — 0 stock at LCSC at time of check) | 0 stock LCSC | **Any 2.2 µF / 0603 / X5R ≥10V equivalent** | This is a generic commodity value used across the platform (TPS2121 cascade soft-start cap, among others) — please quote any qualified 2.2 µF/0603/X5R/≥10V part as a like-for-like substitute; we are not tied to a specific manufacturer here, only the electrical spec. |

---

## Notes for whoever sends this

- Every price above is carried forward from the four subsystem BOM passes and the master
  reconciliation — this package does not introduce new numbers, only requests real quotes
  against the ones already researched. Where a document marked a price `[est]`, `[unv]`,
  or `[directional]`, that flag is preserved here so the RFQ reader (and whoever reviews
  the quotes that come back) knows which lines are "verify this" vs. "confirm this."
- The MPFS ladder (§1a) is the long lead-time item and the one clock-sensitive line in
  this whole package — per the owner queue, **authorizing this RFQ is itself the D-ENT-3
  decision**; the factory-direct MPFS request should go out first/separately if there is
  any delay finalizing the rest of the package, since its lead time is the real long pole.
- LAN9370 and TPS25940LRVCR both carry an explicit **stock/allocation** ask, not just a
  price ask — flag these to whoever is tracking RFQ responses so they don't get read as
  routine confirmatory quotes.
