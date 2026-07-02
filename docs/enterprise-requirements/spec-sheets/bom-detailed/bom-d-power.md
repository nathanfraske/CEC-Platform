## BOM-D: Power subsystem

Architecture note up front: the existing Hub Standard **already implements a 2-chip TPS2121 cascade with 3 conceptual inputs** — U5 ORs (5VSB priority > USB/wall-wart-via-NanoKVM), U7 ORs (MAIN_5V priority > U5's output). The ENT hub's mandatory rear-bracket **EXT** feed occupies exactly the low-priority slot the NanoKVM-USB-C wall-wart path already occupies architecturally. So "Priority cascade ×2" is a direct, unmodified carry-forward of the existing 2-chip topology — I did not invent a 3rd mux stage. Whether EXT *replaces* or *coexists with* the NanoKVM-USB-C path physically is flagged in Open Items; it's a board-integration question, not a subsystem-D parts question.

### 1. eFuse fronts (×3: MAIN_5V, 5VSB, EXT) — TPS25940LRVCR

| Ref-class | Qty | Value/Function | MPN | Mfr | Package | Unit@100q [2026-07-02] | Datasheet URL | Notes (reuse LCSC#) |
|---|---|---|---|---|---|---|---|---|
| U_EF1/2/3 | 3 | eFuse, per-source PG/FLT/EN, true reverse block | TPS25940LRVCR | TI | WQFN-20 (3×4mm) | $1.7143 (Digikey) | ti.com/lit/ds/symlink/tps25940.pdf | **Not on JLC basic lib** — LCSC C2867756 shows only 26 pcs, Digikey 55 pcs in stock; see Open Items |
| R_ILIM-MAIN | 1 | ILIM set resistor, MAIN_5V → 3.53A | 0402WGF2492TCE | UNI-ROYAL | 0402, 1% | ~$0.006 [est] | LCSC listing | new value |
| R_ILIM-SB/EXT | 2 | ILIM set resistor, 5VSB/EXT → 2.08A | 0402WGF4222TCE | UNI-ROYAL | 0402, 1% | ~$0.006 [est] | LCSC listing | new value |
| R1 (IN→EN/UVLO) | 3 | UVLO/OVLO divider top | 0402WGF4532TCE | UNI-ROYAL | 0402, 1% | ~$0.006 [est] | LCSC listing | new value, 45.3kΩ |
| R2 (EN/UVLO→OVP) | 3 | UVLO/OVLO divider mid | 0402WGF2801TCE | UNI-ROYAL | 0402, 1% | ~$0.006 [est] | LCSC listing | new value, 2.80kΩ |
| R3 (OVP→GND) | 3 | UVLO/OVLO divider bottom | 0402WGF1002TCE | UNI-ROYAL | 0402, 1% | ~$0.002 [est] | LCSC C25744 | **reuse C25744** (10kΩ, platform pull-up part) |
| C_dVdT | 3 | Soft-start ramp cap | CL05B103KB5NNNC | Samsung | 0402 | ~$0.004 [est] | LCSC C15195 | **reuse C15195** (platform's 10nF, ex-C12 role) |
| R_PG-pullup | 3 | PGOOD open-drain pull-up | 0402WGF1002TCE | UNI-ROYAL | 0402, 1% | ~$0.002 [est] | LCSC C25744 | **reuse C25744**, per task spec |
| R_FLT-pullup | 3 | FLT open-drain pull-up | 0402WGF1002TCE | UNI-ROYAL | 0402, 1% | ~$0.002 [est] | LCSC C25744 | **reuse C25744** |
| C_IN | 3 | Input noise-suppression cap | CL05B104KO5NNNC | Samsung | 0402 | ~$0.003 [est] | LCSC C1525 | **reuse C1525** (platform's 100nF) |
| C_OUT | 3 | Local output bypass (datasheet min 0.1µF) | CL10A105KB8NNNC | Samsung | 0603 | ~$0.006 [est] | LCSC C15849 | **reuse C15849** (platform's 1µF) |

DEVSLP → GND (disables SATA low-power mode, keeps full monitoring active); PGTH → OUT directly (PGOOD = "FET fully enhanced," no dedicated threshold divider — see design note below); IMON left NC (no ADC destination identified — see Open Items). All are direct ties, zero BOM cost.

### 2. Priority cascade (×2) — TPS2121RUXR, unmodified platform reuse

| Ref-class | Qty | Value/Function | MPN | Mfr | Package | Unit@100q [2026-07-02] | Datasheet URL | Notes (reuse LCSC#) |
|---|---|---|---|---|---|---|---|---|
| U_PC1 (stage A) | 1 | ORs 5VSB(priority) vs EXT | TPS2121RUXR | TI | VQFN-HR-12 | ~$0.65 | ti.com/lit/ds/symlink/tps2121.pdf | **reuse C485916**, = existing hub-standard U5 role |
| U_PC2 (stage B) | 1 | ORs MAIN_5V(priority) vs stage-A output | TPS2121RUXR | TI | VQFN-HR-12 | ~$0.65 | ti.com/lit/ds/symlink/tps2121.pdf | **reuse C485916**, = existing hub-standard U7 role |
| C_SS | 2 | Soft-start / input-settling cap | CL10A225KO8NNNC | Samsung | 0603 | $0.007 (LCSC, **currently 0 stock**) | LCSC C23630 | **reuse C23630** — flag stock |
| R_ILIM(PC) | 2 | Output current-limit set | 0402WGF2702TCE | UNI-ROYAL | 0402, 1% | ~$0.006 [est] | LCSC C25771 | **reuse C25771**, 27kΩ (already-fitted platform value) |

Pin ties (per TPS2121 datasheet's own guidance for fixed-priority, non-auto-compare operation — recommend confirming against the as-built hub-standard netlist before layout, since I could not fully re-derive the exact wired nets from the raw `.kicad_sch`): **PR1 → IN1** on each instance (ties priority to the higher-priority input: 5VSB on stage A, MAIN_5V on stage B); **OV1/OV2 → GND** on both instances (per-input OVP is now handled once, upstream, by each source's own TPS25940 OVP divider — this avoids two independent, potentially-mismatched OVP trip points in series); **CP2 → GND** on both instances (disables the automatic highest-voltage-wins comparator mode — required, since the spec is explicit that priority is by fixed assignment, not by "which source happens to read higher," and MAIN_5V/5VSB/EXT are all nominally ~5V and could be within noise of each other).

### 3. Hold-up reservoir

| Ref-class | Qty | Value/Function | MPN | Mfr | Package | Unit@100q [2026-07-02] | Datasheet URL | Notes (reuse LCSC#) |
|---|---|---|---|---|---|---|---|---|
| C_HOLD | 2 | Persist-on-fault hold-up, **chosen** | VKMI2101C472MV | Samxon | SMD can, ⌀16×21mm, 16V | **$0.7291**, 274 pcs in stock | LCSC C487318 | **reuse C487318** — exact part already on shipping Hub Standard (C1) |
| — | (2) | Hold-up, **priced alternate, not populated** | EEVFK1C472M | Panasonic | SMD can, ⌀18×16.5mm, 16V | ~$1.24 @ 50pc (Digikey); LCSC "from $0.9626" [100pc tier unconfirmed] | ti Panasonic / LCSC C401967 | +35–70% cost for no electrical delta vs the Samxon part; see justification below |
| D_ISO | 1 | Reservoir back-feed isolation Schottky | SS14 | MDD | SMA | ~$0.016–0.018 [interpolated from 50+/500+ tiers] | LCSC C2480 | **reuse C2480** — exact platform D1 |
| C_BULK | 1 | 470µF bulk, fast-transient support | RVT1A471M0607 | Lelon | SMD can, 6.3×7.7mm, 10V | ~$0.03–0.05 [100pc estimated from confirmed 10k+ tier $0.0174] | LCSC C335982 | **reuse C335982** — exact platform C_bulk1 |

**Justification, VKMI2101C472MV over EEVFK1C472M**: identical electrical spec (4700µF/16V), Samxon part is the one **actually already sourced and shipping** on Hub Standard (BOM commonality — one hold-up cap SKU across the whole product line, not two), it's ~35–45% cheaper at the confirmed 100pc break, and its LCSC stock (274 pcs) is healthier than what I could confirm for the Panasonic part. The Panasonic EEVFK1C472M is the part CLAUDE.md's prose historically named before the real BOM-sourcing pass corrected it to Samxon — I'm carrying that correction forward rather than reintroducing the more expensive part. Keep Panasonic on file as a second-source qualification if Samxon stock ever craters.

### 4. Hub logic rails (+5V → +3V3, RJ-45/CAN/RS-485/LED/aux domain)

| Ref-class | Qty | Value/Function | MPN | Mfr | Package | Unit@100q [2026-07-02] | Datasheet URL | Notes (reuse LCSC#) |
|---|---|---|---|---|---|---|---|---|
| U_BK | 1 | 3.3V synchronous buck, 2A | TLV62569DBVR | TI | SOT-23-5 | ~$0.068 [interpolated 50+/150+ tiers] | ti.com/lit/ds/symlink/tlv62569.pdf | New — on LCSC/JLCPCB (C141836), 14,320 pcs in stock |
| L1 | 1 | 2.2µH shielded power inductor | VLS252010HBX-2R2M-1 | TDK | 1008 (2.5×2.0mm) | **$0.0644** | LCSC listing | New — LCSC C88527. Isat 2.3A / Irms 1.76A / DCR 120mΩ |
| C_INBK, C_OUTBK | 2 | Buck in/out caps, 10µF | CL10A106MA8NRNC | Samsung | 0603, 25V X5R | ~$0.010–0.014 [est] | LCSC C96446 | **reuse C96446** — exceeds datasheet's 4.7µF-in/10µF-out minimums, one fewer BOM line vs. adding a distinct 4.7µF part |
| R_FB1 | 1 | FB divider top (VOUT node) | 0402WGF4533TCE | UNI-ROYAL | 0402, 1% | ~$0.006 [est] | LCSC listing | New, 453kΩ — sets VOUT≈3.32V |
| R_FB2 | 1 | FB divider bottom (to GND) | 0402WGF1003TCE | UNI-ROYAL | 0402, 1% | **$0.0004+ (confirmed listing)** | LCSC C25741 | New, 100kΩ |
| U_SV | 1 | +3V3 hub-logic-rail supervisor | TPS3839K33DBZR | TI | SOT-23 | ~$0.12 [platform part, price not re-verified this pass] | ti.com/lit/ds/symlink/tps3839.pdf | **reuse C96333** — new *instance*, existing part number |
| — | 0 | Quiet-3V3, **evaluated, not added** | LP5907MFX-3.3/NOPB | TI | SOT-23-5 | — | — | **reuse C80670 if/when needed** — see justification below |

**Buck selection — why TLV62569 over TPS62912/MPM3506**: this rail feeds digital logic (CAN transceiver, LED-chain drive, DETECT-divider references, RJ-45/aux glue) — none of it is a precision analog reference. TPS62912 is a premium 2×2mm-QFN "low-noise/low-ripple" part explicitly aimed at noise-sensitive analog/RF loads, at a real cost/sourcing premium for a benefit this domain doesn't need. MPM3506 is an MPS integrated-inductor module (simpler layout, but historically ~$1–2/unit, not LCSC/JLCPCB-native) — a reasonable choice only if board area is tighter than cost. TLV62569 is LCSC/JLCPCB-native, ~$0.07 vs. TPS62912's likely $0.5–1+ class, 2A rating gives >1.6× margin over the ≥1A ask, and its typical-application circuit is exactly what's tabulated above (2.2µH/10µF is TI's own "++" recommended combination for VOUT≥1.8V).

**TPS3839K33 — what it supervises now**: in the base Hub Standard it supervises the single +3V3 rail feeding the ESP32-S3-WROOM. In the ENT hub, subsystem D's TPS3839K33 instance supervises **this subsystem's own +3V3 rail** — the RJ-45/CAN/RS-485/LED/aux domain (TJA1051T/3 CAN transceiver, SK6812 LED-chain logic, the sense dividers' any digital front-end, NanoKVM aux header logic level). It does **not** supervise the PolarFire SoC's own core/I/O rails (VDD 1.0/1.05V, VDDA25/VDD25, VDDIx per bank) — those have their own multi-rail sequencing requirement (per PolarFire's own Power-Up and Resets User Guide) and are subsystem A's responsibility, per the stated boundary.

**LP5907MFX-3.3 quiet-3V3 split — why not added**: no precision analog reference has been identified within subsystem D's own scope. The rail-sense dividers (item 6) need *a* 3.3V-class reference for whatever eventually digitizes them, but TLV62569's switching ripple (tens of mV pp at light load per its own PSM-mode application curves) is unlikely to matter for a resistor-divider front end feeding a delta-sigma or 10–12 bit ADC. **If** subsystem A's ADC solution turns out to need a quieter reference than the switching buck provides, LP5907MFX-3.3 (C80670, already the exact part used as Hub Standard's U3) is a zero-engineering-risk drop-in post-regulator off the buck's 3.3V rail. Flagging this as contingent rather than pre-adding it.

### 5. Connectors

| Ref-class | Qty | Value/Function | MPN | Mfr | Package | Unit@100q [2026-07-02] | Datasheet URL | Notes (reuse LCSC#) |
|---|---|---|---|---|---|---|---|---|
| J_MAIN | 1 | MAIN_5V power-in | S2B-XH-A(LF)(SN) | JST | 2-pin XH, 2.5mm | **$0.0483** | LCSC listing | **reuse C157931** — exact platform J_5V |
| J_SVB | 1 | 5VSB power-in | S2B-XH-A(LF)(SN) | JST | 2-pin XH, 2.5mm | **$0.0483** | LCSC listing | **reuse C157931** — exact platform J_5VSB |
| J_EXT | 1 | EXT rear-bracket power-in | PJ-002AH | Same Sky (CUI) | THT R/A, 2.1mm ID / 5.5mm OD | **$0.504**, 23,803 pcs in stock | sameskydevices.com/product/resource/pj-002ah.pdf | New — see recommendation below |

**EXT connector recommendation — barrel jack over keyed JST**: recommending the CUI/Same Sky PJ-002AH (5.5×2.1mm, THT right-angle, 5A rated — comfortably over the 2A ILIM ceiling and the ≥3A task floor). Rationale: this port exists specifically for the forensic-recovery / "customer walks up with an external supply" scenario (spec §2.9), where the whole point is that **any generic 5V adapter works** — that argues for the de-facto-universal consumer barrel-jack standard, not a CEC-proprietary keyed JST-VH cable a customer would have to specially source or that CEC would have to bundle. A keyed JST is the *more secure/less-accident-prone* internal choice, but it fights the "any phone charger covers it" design intent stated explicitly in the spec for this exact power path. If polarity-insertion risk on an externally-exposed connector becomes a concern at review, note that barrel jacks are commonly center-positive by convention and that's what should be silkscreened/labeled at the bracket.

### 6. Sense/monitor

| Ref-class | Qty | Value/Function | MPN | Mfr | Package | Unit@100q [2026-07-02] | Datasheet URL | Notes (reuse LCSC#) |
|---|---|---|---|---|---|---|---|---|
| R_SENSE_HI | 4 | Rail-sense divider top (MAIN_5V raw, 5VSB raw, EXT raw, +5V system rail) | 0402WGF4702TCE | UNI-ROYAL | 0402, 1% | ~$0.002 [est] | LCSC C25792 | **reuse C25792** — exact platform 47kΩ |
| R_SENSE_LO | 4 | Rail-sense divider bottom | 0402WGF1002TCE | UNI-ROYAL | 0402, 1% | ~$0.002 [est] | LCSC C25744 | **reuse C25744** — exact platform 10kΩ |
| D_TVS_EXT | 1 | Input TVS, EXT feed only | SMAJ5.0A | Littelfuse | DO-214AC (SMA) | **$0.0868** | littelfuse.com/…/smaj/smaj5-0a | New — LCSC C83329, 35,015 pcs in stock. Vrwm 5V / Vbr 6.4V / Vc 9.2V / 400W pp |

Three dividers tap each **raw** source (upstream of its own eFuse) — resolving the exact granularity gap survey-4 flagged (the as-built `5VSB_SENSE` reads the already-OR'd `PSU_5V` node, so today the design can't distinguish "5VSB gone, wall-wart present" from the reverse). The 4th divider taps the merged **+5V system rail** downstream of the full cascade, confirming what the logic domain actually receives. TVS is populated on EXT only, not MAIN_5V/5VSB — mirrors the platform's existing DETECT-pin philosophy (protect the externally-exposed boundary; the internal PSU-derived rails are a trusted link, per spec §2.4's PoE-protection reasoning).

**Important scope flag**: I verified against the actual PolarFire SoC datasheet (DS00004248E) that **PolarFire SoC has no integrated ADC** — its DC Characteristics section covers only supply-rail and digital-I/O-bank voltages; there is no ADC/analog-comparator entry anywhere in the part's electrical tables. The task asked for dividers "to the PolarFire ADC-capable inputs," but that input doesn't exist on this silicon. I've built the divider hardware above (that's legitimately subsystem-D scope — attenuating a 5V-class rail to a safe input range), but **what digitizes these four divider outputs is unresolved and outside my boundary** (a small external I2C/SPI ADC, a comparator/threshold scheme, or GPIO-adjacent glue would all work — none is specified here). See Open Items.

### 7. Per-SKU population note

**All rows above populate on every SKU** — ENT-NET-B/AIR-B through ENT-*-MCX. REQ-HUB-COMMON-060 (which mandates the 3-source eFuse-fronted priority-OR) is a `REQ-HUB-COMMON`, i.e., binding platform-wide under the one-ENT-line resolution (D-ENT-6), not gated by the base/MC/MC-Max availability ladder. This is a real redundant/monitored *power path*, always present — it is not part of the optional "redundancy pack" bundle in the availability-ladder sense (that bundle, per REQ-HUB-COMMON-103/105, is the independent compute watchdog + dual uplink + voting pair, none of which live in subsystem D).

MC adds nothing to subsystem D beyond what MC-Max's second PolarFire SoC pulls from agent-A's own rails: the 2nd MPFS095TS and its "rails/flash/clocking" (spec-sheet §G) are subsystem A's regulators, fed *from* my +5V system rail, not new subsystem-D parts. The only thing subsystem D needs to confirm is that the +5V rail's current-delivery ceiling has headroom for that added draw — flagged below, since it's a real, unresolved number.

---

## Power-tree sketch

```
                    MAIN_5V (PSU main, tapped post-24pin-5V-sensor)
                       │
                  [SMAJ n/a — trusted internal link, no TVS]
                       │
              R1/R2/R3 divider (UVLO 4.49V / OVLO 5.75V trip)
                       │
                 TPS25940LRVCR  (U_EF1, ILIM 24.9k -> 3.53A typ)
                 PG/FLT -> 10k pull-ups -> [ADC dest: OPEN, see below]
                       │
                       │  IN1 (priority)
                       ▼
5VSB (24-pin JST feed)          ┌─────────────────┐
   │                            │   TPS2121RUXR   │
[R1/R2/R3 divider] ─ TPS25940 ──┤ U_PC1 (stage A) │
   (U_EF2, ILIM 42.2k->2.08A)   │ IN1=5VSB(pri.)  │
                       IN1 ──►  │ IN2=EXT         │──OUT──┐
EXT (PJ-002AH barrel jack)      │ PR1->IN1 CP2->GND│       │
   │                            │ OV1/OV2->GND     │       │
[SMAJ5.0A TVS]                  └─────────────────┘       │
   │                                     ▲                 │
[R1/R2/R3 divider] ─ TPS25940 ───────────┘ IN2             │
   (U_EF3, ILIM 42.2k->2.08A)                               │
                                                              ▼
                                              ┌─────────────────┐
                                              │   TPS2121RUXR   │
                                              │ U_PC2 (stage B) │
                          MAIN_5V(post-eFuse)─┤ IN1=MAIN(pri.)  │
                                              │ IN2=stage-A OUT │──OUT──► +5V SYSTEM RAIL
                                              │ PR1->IN1 CP2->GND│         │
                                              │ OV1/OV2->GND     │         │
                                              └─────────────────┘         │
                                                                          ├──► D_ISO (SS14) ──► C_HOLD (2x4700uF)
                                                                          │                      + C_BULK (470uF)
                                                                          │                      "+5V_HOLD" reservoir
                                                                          │                      (persist-on-fault)
                                                                          │
                                                                          ├──► R_SENSE (47k/10k) ──► [rail-sense, ADC dest OPEN]
                                                                          │
                                                                          └──► U_BK (TLV62569, 2.2uH/10uF) ──► +3V3 HUB LOGIC
                                                                                 supervised by U_SV (TPS3839K33)
                                                                                 -> CAN xcvr / LED chain / DETECT / aux domain

  [3x raw-source sense dividers also tap MAIN_5V / 5VSB / EXT
   upstream of each eFuse -> ADC dest OPEN, same as above]
```

---

## Computed values (per source)

| Source | R_ILIM | I_LIM typ (datasheet range) | UVLO trip, rising (V_UV) | OVLO trip, rising (V_OV) | Power-fail, falling | dVdT ramp time |
|---|---|---|---|---|---|---|
| MAIN_5V | 24.9 kΩ | **3.53 A** (3.25–3.81 A) | **4.49 V** | **5.75 V** | 4.18 V | 4.15 ms |
| 5VSB | 42.2 kΩ | **2.08 A** (1.92–2.25 A) | 4.49 V | 5.75 V | 4.18 V | 4.15 ms |
| EXT | 42.2 kΩ | **2.08 A** (1.92–2.25 A) | 4.49 V | 5.75 V | 4.18 V | 4.15 ms |
| TPS2121 cascade (both stages) | 27 kΩ (existing platform value, unchanged) | ~3.7–3.9 A [interpolated between datasheet's 29.8kΩ→3.5A and 22.1kΩ→4.5A table rows — not a direct table hit] | Internal fixed ~2.65V typ (INx UVLO), not adjustable | — (OV1/OV2 tied GND, disabled — handled upstream) | — | SS = 2.2µF (unchanged) |

**Derivation** (all 3 eFuse UVLO/OVLO dividers use identical R1=45.3kΩ/R2=2.80kΩ/R3=10.0kΩ, chosen to land near a 4.5V UVLO / 5.75V OVLO target for a nominal 5V rail):
- Datasheet Eq.10/11: V(OVPR) = R3/(R1+R2+R3)×V(OV); V(ENR) = (R2+R3)/(R1+R2+R3)×V(UV), both comparators at 0.99V nominal.
- (R1+R2+R3) = 58.1kΩ, (R2+R3) = 12.8kΩ → V(OV) = 0.99×5.81 = 5.75V; V(UV) = 0.99×4.539 = 4.49V.
- Divider string current at 5V: 5V/58.1kΩ ≈ 86µA, vs. ±100nA max EN/OVP pin leakage — >400× the datasheet's "20× leakage" design-margin guidance.
- ILIM: datasheet Eq.4, I(LIM)=89/R(ILIM)[kΩ]; MAIN uses the datasheet's own characterized 24.9kΩ row (typ 3.53A) rather than an independently-rounded value, landing at the low-middle of the requested 3–4A band — see Open Items on MC-Max headroom.
- dVdT: Eq.2, t=8.3×10⁴×V_IN×C(dVdT); C=10nF (reused platform value) at V_IN=5V → 4.15ms. This paces only the eFuse's own small local output cap (1µF, ~1.2mA inrush) — the big 4700µF/470µF reservoir's charge current is separately paced by the downstream TPS2121 stage's own SS pin (2.2µF, unchanged) and ILM ceiling (~3.7–3.9A), exactly as it already works on the shipping Hub Standard.

---

## Cost roll-up (100q, subsystem D total)

| Group | Subtotal |
|---|---|
| 1. eFuse fronts ×3 (IC + support) | ≈ $5.25 |
| 2. Priority cascade ×2 (carried-forward platform parts) | ≈ $1.33 |
| 3. Hold-up reservoir | ≈ $1.53 |
| 4. Hub logic rails | ≈ $0.17 |
| 5. Connectors | ≈ $0.60 |
| 6. Sense/monitor | ≈ $0.12 |
| **Subsystem D total** | **≈ $9.0** |

Reconciles reasonably against the spec-sheet's own top-down §3.D estimate of "≈$10–14" — my bottom-up figure lands slightly under that range, mainly because the per-eFuse support-passive sets came in near $0.04/set (almost entirely reused platform 0402 parts) versus the sheet's $0.35/set placeholder, and because groups 2 and 5's JST/TPS2121 lines are pure carry-forward of parts the base Hub already expenses. **Incremental new spend over the existing Hub Standard baseline** (i.e., excluding the already-budgeted TPS2121 cascade + 2×JST-XH, which cost nothing extra here) is closer to **≈$6.0** — dominated by the 3× TPS25940 ($5.14) and the EXT barrel jack ($0.50).

---

## Open items

1. **Hold-up sizing vs. OQ-56 bench** — unchanged from the base platform: this BOM keeps the existing 2×4700µF + 1×470µF reservoir (now serving 3 sources instead of 2, but sitting in the identical shared-rail position, so its sizing math is unchanged). Survey-4's illustrative calc (ΔQ=C·ΔV, ~50–150ms ride-through at 50–150mA) is *not* a substitute for the actual OQ-56 bench measurement (does the 4700µF genuinely ride a real flash write, including a worst-case sector-erase-then-write sequence). Recommend that bench item happen before treating this reservoir sizing as final for the ENT tier specifically — MC/MC-Max's persist-on-fault payload (tamper log + more telemetry channels than the consumer Hub) may be larger than what the consumer-tier sizing assumed.
2. **EXT connector choice** — recommending PJ-002AH (barrel jack) over a keyed JST-VH/XH on the "any generic 5V adapter should work" design intent in spec §2.9; flagging this as a call worth a quick owner nod given it's externally customer-facing (see full reasoning in section 5).
3. **PolarFire SoC has no ADC** (verified against DS00004248E) — the four rail-sense dividers and any eFuse IMON current-monitor output need a digitization path this subsystem doesn't own. Needs coordination with the compute-core agent: either a small external I2C/SPI ADC (added to *someone's* BOM — arguably subsystem D's since it's serving the power-monitoring function, but not added here without sign-off since it's outside the stated "+5V/+3V3 system domain" boundary), or a different sensing scheme entirely.
4. **MC-Max current headroom, unresolved** — MAIN_5V's ILIM (24.9kΩ → 3.53A typ) is sized against the spec-sheet's own single-SoC estimate ("5–15W all-in `[unv]`" ≈ up to 3A at 5V) with modest margin. MC-Max's 2nd PolarFire SoC (subsystem A) could plausibly push total FULL-posture draw well past that — the spec sheet doesn't have an MC-Max power number yet either. If it does, this is a **resistor value swap, not a redesign** (e.g., 20kΩ → 4.45A typ on MAIN's eFuse, and correspondingly the downstream TPS2121 stage-B's own 27kΩ ILIM (~3.8A) would then become the tighter constraint and need bumping too) — flagging the dependency chain now rather than guessing a number.
5. **eFuse part stock/lead-time risk** — TPS25940LRVCR is thin at both Digikey (55 pcs) and LCSC (26 pcs) at the moment I checked, and is not a JLCPCB assembly-line part (unlike the rest of this BOM, which stays LCSC/JLCPCB-native). For qty-100+ builds this needs a distributor lead-time check ahead of D-ENT-3 lock, similar to the LTC4417 stock caveat survey-4 already flagged for the alternate mux part.
6. **Spec-sheet wording tension (minor, doc-only)** — `hub-ent-spec-sheet.md` §3.D subtitle reads "pack items on MC+/opt," and the §2 Specifications table's "redundancy pack" gloss lists "monitored sources" alongside "dual uplink" as the MC+ bundle contents — which could be misread as gating the eFuse fronts behind the optional pack. REQ-HUB-COMMON-060 itself is unambiguously platform-common (all SKUs), and this BOM follows that. Worth a follow-up wording pass on the spec sheet so a future reader doesn't hit the same ambiguity.
7. **CL10A225KO8NNNC (TPS2121 cascade's SS cap) shows 0 stock at LCSC** at time of check — an existing platform part, not new to this BOM, but worth a general restock flag since it's used across every Hub board.

---

## Sources

- [TPS25940A/TPS25940L datasheet (SLVSCF3A), TI](https://www.ti.com/lit/ds/symlink/tps25940.pdf) — pin functions, block diagram, Eq.4/10/11/12, current-limit table, design procedure (fetched + read directly, 2026-07-02)
- [TPS2120/TPS2121 datasheet (SLVSEA3F), TI](https://www.ti.com/lit/ds/symlink/tps2121.pdf) — pin functions (PR1/OV1/OV2/CP2), current-limit table, VREF/VOFST specs (fetched + read directly, 2026-07-02)
- [TLV62569/TLV62569P datasheet (SLVSDG1C), TI](https://www.ti.com/lit/ds/symlink/tlv62569.pdf) — FB equation, inductor/cap selection table, layout (fetched + read directly, 2026-07-02)
- [PolarFire SoC Data Sheet (DS00004248E), Microchip](https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/DataSheets/PolarFire-SoC-Datasheet-DS00004248.pdf) — DC Characteristics / Recommended Operating Conditions tables checked for ADC presence (fetched + read directly, 2026-07-02)
- [TPS25940LRVCR | DigiKey](https://www.digikey.com/en/products/detail/texas-instruments/TPS25940LRVCR/4915502) — 100pc price + stock (fetched 2026-07-02)
- [TPS25940LRVCR | LCSC C2867756](https://www.lcsc.com/product-detail/Surge-Suppressors_Texas-Instruments-TPS25940LRVCR_C2867756.html) — stock cross-check
- [TLV62569DBVR | LCSC C141836](https://www.lcsc.com/product-detail/C141836.html)
- [VLS252010HBX-2R2M-1 | LCSC C88527](https://www.lcsc.com/product-detail/Inductors-SMD_TDK_VLS252010HBX-2R2M-1_2-2uH-20_C88527.html)
- [PJ-002AH datasheet, Same Sky/CUI](https://www.sameskydevices.com/product/resource/pj-002ah.pdf); [PJ-002AH | DigiKey](https://www.digikey.com/en/products/detail/same-sky-formerly-cui-devices/PJ-002AH/408446) — price-break table fetched 2026-07-02
- [SMAJ5.0A (Littelfuse) | LCSC C83329](https://lcsc.com/product-detail/esd-and-surge-protection-tvs-esd_littelfuse-smaj5-0a_C83329.html)
- [VKMI2101C472MV | LCSC C487318](https://www.lcsc.com/product-detail/C487318.html); [EEVFK1C472M | LCSC C401967](https://www.lcsc.com/product-detail/Aluminum-Electrolytic-Capacitors-SMD_PANASONIC-EEVFK1C472M_C401967.html)
- [RVT1A471M0607 | LCSC C335982](https://www.lcsc.com/product-detail/C335982.html); [SS14 | LCSC C2480](https://www.lcsc.com/product-detail/C2480.html); [S2B-XH-A | LCSC C157931](https://www.lcsc.com/product-detail/C157931.html); [0402WGF1003TCE | LCSC C25741](https://lcsc.com/product-detail/Chip-Resistor-Surface-Mount_UNI-ROYAL-Uniroyal-Elec-0402WGF1003TCE_C25741.html); [CL10A225KO8NNNC | LCSC C23630](https://www.lcsc.com/product-detail/C23630.html)
- Internal: `docs/enterprise-requirements/spec-sheets/hub-ent-spec-sheet.md` §3.D, §4; `docs/enterprise-requirements/research/phase2/survey-4-redundant-power.md`; `docs/enterprise-requirements/hub-enterprise-requirements.md` REQ-HUB-COMMON-050/051/052/060/061/062; `CEC-Platform-Ground-Truth-Spec.md` §2.9; `hubs/hub-standard/bom/bom.csv`; `hubs/hub-standard/hub-standard.kicad_sch`
