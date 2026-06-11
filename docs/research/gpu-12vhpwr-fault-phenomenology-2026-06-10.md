# GPU / 12VHPWR Power-Fault Phenomenology — Corpus Dive for CEC (Cluster 6 + Item 4)

## TL;DR
- **The transient the platform hunts is bounded publicly.** At the connector/add-in-card level a 12VHPWR/12V-2x6 card may draw up to **3× sustained power for ≤100 µs, ~2.5× at 1 ms, ~2× at 10 ms** (Intel ATX 3.0 Design Guide, Table 3-1: R = 4 − 0.2171·ln(T µs)); the matching PSU duty-cycle table allows 200%/100µs, 180%/1ms, 160%/10ms. A **10 kHz (100 µs) burst target adequately captures the 1 ms and 10 ms excursion classes that actually heat connectors**, but under-samples the 100 µs/200% class — which deposits negligible I²R energy in connector thermal mass and is a PSU-hold-up problem, not a melting problem.
- **The single-pin-hog fault is real and measured.** der8auer recorded **>22 A (≈264 W, ~half the load) on one 12V wire of a failing RTX 5090 cable** (others at 2/5/11/8/3 A) at a PSU-side socket >140–150 °C, against a **9.2 A/pin (12VHPWR) / 9.5 A/pin (12V-2x6)** spec. A defensible firmware default is **WARN >9.5 A sustained/pin, ALARM >11 A sustained/pin (>1 s) or lane-imbalance ratio >2.0**; the proposed 12 A hog level is sound but slightly loose.
- **The dV/dI connector-degradation trend is real but tier-gated.** Runaway onset for ~9 A power contacts is a **change in contact voltage drop of ~10–30 mV (≈3–4 mΩ rise at 9 A) above a ~0.8 mΩ healthy baseline** (Malucci/Molex). Resolving **~1 mΩ per lane over a days-to-weeks window** gives ~3× early-warning margin. This is **clearly viable on the Pro line (INA228/238, 20-bit + integrated temp comp); marginal/conditional on Standard hardware**, where the series shunt's load-life drift and self-heating TCR (≈ the 1 mΩ signal) are the binding constraint.

---

## Key Findings

### Thread One — the transient

**1. Intel ATX 3.0/3.1 excursion tables are public and authoritative** (edc.intel.com, ATX 3.0 Multi-Rail Desktop Platform PSU Design Guide, document ID 336521, rev 2.1, dated 09/13/2023; classification "Public"). Two tables matter:

- **PSU level (Table 3-3, ">450 W & 12V-2x6 present" column):** 200% @ 100 µs (5% test duty), 180% @ 1 ms (8%), 160% @ 10 ms (12.5%), 120% @ 100 ms (25%), 100% infinite. The "≤450 W / PSUs without 12V-2x6" column is gentler: 150/145/135/110/100%. Worked example (Table 3-4, 1000 W PSU): TE/TC pairs of 100 µs @ 2000 W / 1900 µs @ 917.7 W; 1 ms @ 1800 W / 11.5 ms @ 897.3 W; 10 ms @ 1600 W / 70 ms @ 881.6 W; 100 ms @ 1200 W / 300 ms @ 923.8 W.
- **Add-in card level (Table 3-1):** ratio **R** of average power in interval **T** to max sustained power: **R = 3 for T ≤ 100 µs; R = 4 − 0.2171·ln(T in µs) for 100 µs < T < 1,000,000 µs (1 s).** This evaluates to ~2.5× at 1 ms, ~2× at 10 ms, 1× at 1 s. Derived from PCIe CEM Gen 5 ECN "Power Excursion Limits for 300W-600W PCIe AICs" (Doc# 16495).
- **Discrepancy flag:** secondary sources (Tom's Hardware, Hardware Busters) quote "200% for 100 µs at **10%** duty cycle." The public rev-2.1 guide shows **5%** duty at 100 µs. The 10% figure traces to earlier ATX 3.0 drafts/examples. Use rev-2.1 table values; treat 10% as superseded.

**2. Measured GPU transient spectra (enthusiast scope literature):**

- **ATX 2.x era (RTX 3080/3090):** igor'sLAB measured RTX 3080 average ~320 W with peaks to ~600 W (100 µs-window spike ratio **1.875**) before NVIDIA's driver mitigation, ~520 W after. AMD Vega 56 CrossFire hit **102 A / 10 ms ≈ 1200 W** in FurMark (igor'sLAB). RTX 2080 Ti spikes ~375–400 W with currents staying <33 A.
- **First PCIe-5/ATX-3-designed card (RTX 3090 Ti):** igor'sLAB measured ~480 W average with peaks only ~580 W — the **100 µs spike ratio collapsed to 1.2** (vs. the post-"miracle-driver" RTX 3090's ~1.625) because the 3090 Ti was the first card designed to the excursion spec. This is direct evidence that spec-compliant cards tame the transient.
- **RTX 4090:** at 20 ms PSU-relevant intervals igor'sLAB saw all load peaks "brutally capped at 38 to 39 A" (≈456–468 W) at the connector.
- **RTX 5090 (the current worst case):** igor'sLAB FurMark high-resolution capture (10 µs steps) measured up to ~900 W. TechPowerUp (citing igor'sLAB) gives the full duration-resolved distribution: **"as high as 627.5 W for 10 ms to 20 ms durations; as high as 738.2 W in 5 ms to 10 ms durations; as high as 823.6 W in the 1 ms to 5 ms category; and as high as 901.1 W in spikes under 1 ms."** Tom's Hardware recorded real Cyberpunk-2077 gameplay spikes to 659 W (per Seasonic's analysis). Against a 575 W TGP, the sub-1 ms spike ratio ≈ 901/575 ≈ **1.57** — note that the spike **magnitude falls monotonically as duration lengthens**, exactly the shape the ATX excursion curve anticipates.
- **Measurement-bandwidth context:** igor'sLAB works in three regimes — 20 ms windows (~50 Hz, "what the PSU supervisor sees / shutdown"), 1 ms windows, and 10 µs steps for spike shape. ElmorLabs PMD logs at up to 10 ksps (10 kHz); PMD2 adds native 12VHPWR/ATX24 channels (12V-2x6 max 51 A continuous) with an audible over-current warning and oscilloscope mode.

**3. Frequency-domain / capture verdict (bandwidth × transient-class table):**

| Sampler / analog corner | 100 µs excursion (200%/3× class) | 1 ms excursion (~2.5×) | 10 ms excursion (~2×) | 20 ms+ RMS / thermal |
|---|---|---|---|---|
| 10 kHz burst (100 µs/sample; Nyquist 5 kHz) | **MISS shape / alias risk** (~1 sample; detects elevation only) | **CAPTURE** (~10 samples) | **CAPTURE** (~100 samples) | **CAPTURE** |
| ~16.9 kHz RC corner | passes most pulse energy (≈10 kHz content) — **under-filters for a 5 kHz Nyquist → alias risk** | passes | passes | passes |
| INA238 "clears 10 kHz" (16-bit; 50 µs min conversion ⇒ ~20 kSPS single-ch, Nyquist 10 kHz) | partial | CAPTURE | CAPTURE | CAPTURE |
| Pro "50 kHz × 6" | implementation-dependent (see flag) | CAPTURE | CAPTURE | CAPTURE |

- **Interpretation:** the 100 µs / 200% class deposits negligible I²R energy into a connector's thermal mass; it is a PSU-hold-up / OCP-trip concern, not a connector-melting one. For CEC's mission (connector thermal safety + degradation), the **thermally relevant transients are the 1 ms–10 ms RMS-heating classes, which 10 kHz captures cleanly.** The 10 kHz burst target is therefore defensible for the safety mission.
- **Consistency flag (gates OQ-57):** a 16.9 kHz RC corner in front of a 10 kHz sampler (5 kHz Nyquist) **passes alias-producing content**. Either (a) run the ESP32-S3 SADC faster (tens of kHz–MHz) and decimate — in which case the 16.9 kHz corner is correct anti-alias for the front-end and 10 kHz is the post-decimation report rate; or (b) lower the analog corner to ~2–5 kHz if the ADC genuinely samples at 10 kHz. Resolve and document before sign-off.

**4. Comparator / hog-alarm grounding (measured + specified):**

- **Spec per-pin rating:** **9.2 A/pin (12VHPWR, "H+")** with 30 °C T-rise, all 12 contacts energized (Intel ATX 3.0 guide; Amphenol GS-12-1031; Enermax cable spec). **9.5 A/pin (12V-2x6, "H++")** per Amphenol GS-12-1706 (Minitek Pwr CEM-5: "Operating Current Rating … For Power Pin = 9.5A/pin (12 power and 4 signal pins energized)") and Molex's PCIe-CEM-5 spec; total assembly ≤55 A RMS. The CEM explicitly warns "due to variations in contact resistance, a single pin may see more than 9.2 A."
- **Healthy balanced loading** at 600 W ≈ **8.3 A/pin**. Falcon Northwest measured balanced wires in the nominal 6–8 A band across many FE samples and could not reproduce der8auer's imbalance. A bench cable (overclock.net) showed a marginal spread of 80–130 W (≈6.7–10.8 A) that re-seated to a "near-perfect" 96–109 W (≈8–9.1 A).
- **Failing cable (der8auer RTX 5090):** wires measured at **2 A (24 W), 5 A (60 W), 11 A (132 W), 8 A (96 W), 3 A (36 W), and >22 A (264 W)** by current clamp; the hog wire carried roughly half the total load. GPU-side socket reached 90 °C while the PSU-side socket exceeded 140 °C, "spiking to over 150 degrees Celsius after just four minutes."
- **Industry's own threshold:** ASUS Power Detector+ (GPU Tweak III) "continuously monitors the current on all six sense pins of the 12VHPWR (12+4 pin) connector or 12V-2x6 connector" and alarms: *"ALERT! Power Detector+ reports that one or more 12VHPWR pins exceed 9.2 amps or are at 0 amps. Please check this cable now to avoid potential risks."* This corroborates a per-pin trip near the rating plus an open-pin (0 A) detector.

### Thread Two — the degradation signature

**5. Contact-resistance limits and runaway trajectory:**

- **Healthy / initial resistance:** the Malucci/Molex model uses healthy overall contact resistance **Ro ≈ 0.8 mΩ** (Rms ≈ 0.3 mΩ). Amphenol GS-12-1031: high-power contact resistance ≤0.8 mΩ, low-power ≤1.5 mΩ at rated current initially. Molex Micro-Fit 3.0 family datasheet limit: ≤10 mΩ max (signal-grade, 8.5 A max). "Normal" board-to-board LLCR is 5–15 mΩ.
- **Cable-assembly limit:** **6 mΩ max LLCR per conductor** for the 12V-2x6 cable assembly (igor'sLAB CEM 5.1 coverage), measured footprint-to-50 mm after 30 mating cycles + 20 N side load. *Derivation-class — authoritative source is the paywalled PCIe CEM 5.1; verify against the spec.*
- **Degradation mechanism:** fretting corrosion dominates tin-plated power contacts (Samtec "The Pain of Fretting Corrosion"; connectorsupplier.com). Brittle, insulating tin oxide is repeatedly fractured by micro-motion (thermal cycling, vibration), exposing fresh metal that re-oxidizes and builds an insulating layer → resistance rises → I²R heating → more fretting/oxidation → **positive-feedback thermal runaway** (P = I²R). Elevated temperature accelerates oxidation and Cu-Sn intermetallic growth (ScienceDirect, sustained plateaus near tin's melting voltage).
- **Runaway-onset threshold (the key number):** Malucci & Ruffino, *"Current Rating Power Connectors Using Voltage Drop Criteria"* (Molex white paper, content.molex.com): thermal instability ensues when the **change in contact voltage drop crosses 0.01–0.03 V (10–30 mV)**; statistically averaged **ΔVt ≈ 0.028 V**. At that threshold "metallic contact at the interface drops by more than an order of magnitude" (<10% of initial area), so local current density and heating spike. For the 9 A case, **ΔVt(9) ≈ 0.0322 V**. Runaway then proceeds to the **melting voltage of tin, 0.143 V**. Tests were at 17 A and 20 A (≈2× the 7–9 A rating) on 8-contact tin-plated connectors. The authors stress the threshold is **statistical** — "one cannot in general predict the outcome of an individual contact," which argues for trend/imbalance detection over a single fixed limit.
- **Converting to resistance:** ΔVt(9) ≈ 32 mV / 9.2 A ≈ **3.5 mΩ rise from baseline** triggers runaway onset at the rated current. The actionable window is thus a **~3–4 mΩ per-contact rise above a ~0.8–3 mΩ healthy baseline.**
- **Arithmetic correction for the corpus:** the task's "at 9.2 A each additional mΩ adds ~0.78 W per contact" is wrong. P = I²·ΔR = 9.2² × 0.001 = **0.085 W per mΩ per contact at 9.2 A.** The 0.78 W/mΩ figure only holds near **~28 A** (28² × 0.001 = 0.78 W), i.e., for a hogging pin, not a balanced one. Fix in the corpus entry.
- **Field timeline:** documented 12VHPWR/12V-2x6 melting cases run **weeks to months** between install and failure (e.g., the videocardz RTX 5090 case: inspected every 3 months, melted "after a few weeks of gaming"). Mating-cycle life is only **~30 cycles** (Corsair, Seasonic, Molex Micro-Fit 3.0 "typically 30 cycles"), so frequent re-seating to inspect *accelerates* the very fretting wear it intends to catch.

**6. The actionable delta (dV/dI requirement):**

- The platform observes **total per-lane source impedance** Z_lane = R_contact(GPU) + R_contact(PSU) + R_wire + R_PCB + R_shunt via ΔV/ΔI across natural load steps. The degradation signal is the **change in Z_lane over time** — ideally with slow common-mode terms (wire, shunt, reference) subtracted lane-to-lane so only the contact-localized rise survives.
- **Requirement statement:** *Resolve a ΔR ≈ 1 mΩ change per lane (pin-pair) over a days-to-weeks trending window, against a runaway-onset delta of ~3–4 mΩ above a ~1–3 mΩ healthy baseline.* Resolving 1 mΩ yields ~3× warning margin before the Malucci instability knee. Confidence target: distinguish a 1 mΩ trend from noise + drift at ≥3σ over the window.
- **Derivation vs judgment:** the 3–4 mΩ runaway delta and 10–30 mV onset are **measured/published** (Malucci). The "resolve 1 mΩ over days–weeks at ≥3σ" target is **engineering judgment** anchored on that delta and the weeks-to-months field timeline.

**7. Stability-term table (for the in-house capability budget):**

| Term | Public datasheet value | Source |
|---|---|---|
| REF3030 long-term drift | **24 ppm / 0–1000 h; 15 ppm / 1000–2000 h** (typ) | TI REF30xx datasheet SBVS032I |
| REF3030 temp drift | 50 ppm/°C max (0–70 °C); 75 ppm/°C max (−40…+125 °C) | TI REF30xx datasheet |
| INA240 offset | ±25 µV max | TI INA240 datasheet SBOS662 |
| INA240 gain error / drift | **gain error 0.20% max; gain drift 2.5 ppm/°C max** | TI INA240 datasheet |
| Shunt TCR (metal-element Manganin/Zeranin) | **~10–50 ppm/°C**; thick-film ~100–200 ppm/°C | PCBSync shunt guide |
| Bourns CSS/CSM load-life | **ΔR/R ≤1% for 21,000 h at rated power, 130 °C**; TCR 50 ppm/°C | Bourns App Note N1702 |
| Vishay WSL metal-strip load-life | **±(1.0% + 0.0005 Ω) after 1000 h at rated power, 70 °C**; bias-humidity ±(0.5%+0.5 mΩ) | Vishay doc 30100 (WSL) |
| Vishay WSL component TCR (incl. terminals) | ±75 ppm/°C (7 mΩ–500 mΩ); **±275 ppm/°C at 1–2.9 mΩ; ±400 ppm/°C at 0.5–0.99 mΩ**; element TCR <20 ppm/°C | Vishay doc 30100 |
| INA228/238 ADC | INA228 20-bit, INA238 16-bit Δ-Σ; conversion times 50–4120 µs; INA228 integrated temp sensor (±1 °C) for shunt comp | TI INA228/238 datasheet; ESPHome/RobTillaart docs |
| ESP32-S3 SADC long-term drift | not published as a stability spec | Espressif — gap |

- **Crux for the budget:** the sub-3 mΩ shunt is the weak link. A Vishay-WSL-class 1 mΩ shunt carries a **load-life additive term of ~0.5 mΩ/1000 h** and a **component TCR of ±275 ppm/°C** (copper-terminal-dominated at low ohms). The shunt load-life additive (~0.5 mΩ) is **the same order as the 1 mΩ signal** to be resolved over weeks. By contrast the Bourns CSS/CSM line (1%/21,000 h, 50 ppm/°C) is far better-matched to this duty. REF3030 long-term drift (24 ppm = 72 µV on a 3 V reference) and INA240 gain drift (2.5 ppm/°C) are negligible against the shunt term.

---

## Details — verdict on the dV/dI feature per tier

**Standard hardware (INA240 + ESP32-S3 SADC + REF3030 ratiometric + sub-2 mΩ shunt): marginal / conditional.** Instantaneously the signal (1 mΩ over weeks ≈ 10 mV at 10 A) sits comfortably within INA240/REF3030 capability. The binding constraint is **slow drift of the series shunt** — load-life additive (~0.5 mΩ/1000 h for WSL-class) and self-heating TCR — which is comparable to the trend being resolved. The feature becomes real on Standard only if: **(a)** a metal-element/metal-foil shunt with tight load-life and low TCR is used (Bourns CSS-class 1%/21,000 h beats Vishay-WSL-class for this specific duty); **(b)** shunt self-heating is temperature-compensated; and **(c)** firmware trends per-lane impedance **differentially** (lane-vs-lane and lane-vs-baseline) so shunt/wire/reference common-mode drift largely cancels and only the contact-localized rise remains. Without (a)–(c), a 1 mΩ multi-week trend can be masked by shunt aging.

**Pro line (INA228/INA238 + integrated die-temp sensor + higher resolution/sampling): viable / real.** INA228's 20-bit ADC, integrated temperature sensor (enabling shunt-TCR compensation), and fast logging give clear headroom to resolve a 1 mΩ trend with margin. INA238 (16-bit) is adequate for current/RMS and "clears 10 kHz" Nyquist at its fastest conversion but lacks temperature compensation, making it mid-tier for the *trend* feature specifically.

**My reading:** **Pro = ship the dV/dI trend feature; Standard = ship as "conditional/beta," gated on shunt selection + differential-trending firmware; it is not "not-viable" on either tier.** The in-house stability budget (capability curve vs the 1 mΩ/weeks requirement curve) finalizes the Standard verdict — the curves cross right at the shunt-aging term, so the shunt BOM choice is the deciding variable.

---

## Recommendations

1. **OQ-57 (10 kHz burst target):** **Keep 10 kHz as the RMS/thermal-capture rate.** It cleanly captures the 1 ms and 10 ms excursion classes that actually heat connectors; the 100 µs/200% class is thermally irrelevant to contact melting. **De-scope sub-100 µs waveform reconstruction** (needs ≥100 kHz and aliases at 10 kHz). **Resolve the RC-corner consistency:** either sample the ESP32-S3 SADC at ≥50–100 kHz and decimate to 10 kHz (16.9 kHz corner correct as front-end anti-alias), or drop the analog corner to ~2–5 kHz if the ADC truly runs at 10 kHz. Document the chosen path.
2. **OQ-58 (comparator threshold):** Compute per-pin current = lane current ÷ 2. **WARN >9.5 A sustained/pin; ALARM >11 A sustained/pin for >1 s; CRITICAL on lane-imbalance ratio (max lane ÷ mean lane) >2.0 or any energized lane reading ~0 A (open-pin / hog precursor).** Grounds: 9.2/9.5 A spec rating, der8auer's 22 A failure, ASUS's own 9.2 A + 0 A firmware trip. Mark the underlying derate basis derivation-class (CEM 5.1 paywalled).
3. **OQ-59 (12 A single-pin hog):** The proposed 12 A/pin sustained default is **sound but slightly loose** (~1.3× rating, well below the 22 A failure). **Recommend tightening to 11 A sustained/pin (>1 s) for the hard alarm plus a 9.5 A "elevated" warning and the imbalance-ratio trigger.** Keep 12 A only as an absolute instantaneous-tolerated ceiling if a single scalar threshold is mandated.
4. **dV/dI requirement (sign-off statement):** *Resolve ≥1 mΩ change in per-lane source impedance over a days-to-weeks window at ≥3σ against drift, giving ~3× margin before the ~3–4 mΩ Malucci runaway-onset delta (≈10–30 mV contact-voltage-drop change at rated current).*
5. **Corpus arithmetic correction:** replace "0.78 W per mΩ at 9.2 A" with "**0.085 W per mΩ at 9.2 A; 0.78 W per mΩ only near ~28 A (hog pin)**."
6. **Benchmarks that change the verdict:** if the Standard shunt's measured, temperature-compensated multi-week ΔR (in situ) stays **<0.3 mΩ**, promote Standard dV/dI from conditional to full. If it exceeds **~0.7 mΩ**, restrict the trend feature to Pro only.

## Caveats
- **Paywalled-spec / derivation-class items (verify against the spec):** the 6 mΩ LLCR cable-assembly limit, the per-conductor change-in-resistance failure criterion, and the exact 9.2 vs 9.5 A pin ratings as written in PCIe CEM 5.0/5.1. All values quoted here come from public secondary coverage (igor'sLAB), Intel's public ATX guide, and connector-vendor public specs (Amphenol GS-12-1031/GS-12-1706, Molex) — not the CEM spec itself.
- **Measured vs specified vs judged:** scope spike magnitudes and the 22 A hog are **measured** (igor'sLAB, TechPowerUp, der8auer); excursion tables and pin ratings are **specified** (Intel public guide, vendor specs); the 1 mΩ/weeks dV/dI target and the per-tier viability verdict are **engineering judgment** anchored on measured Malucci thresholds.
- **Gaps:** published GPU current **slew-rate in A/µs at the connector** was not found in public sources (igor'sLAB publishes power/current vs time, not dI/dt) — flag for in-house scope measurement. ESP32-S3 SADC long-term drift is not a published spec — flag for in-house characterization. Vishay's load-life "%+additive-Ω" format is not directly comparable to Bourns' pure-ΔR/R% or to Bourns' 21,000 h duration; normalize before using in the budget.
- **Duty-cycle discrepancy:** Intel rev-2.1 shows 5%/8%/12.5%/25% test duty for the four PSU excursion tiers; the widely-quoted "10% duty at 200%/100 µs" derives from earlier drafts — treat as superseded.
- **der8auer reproducibility:** Falcon Northwest tested "many" RTX 5090 FE cards and could **not** reproduce the 22 A imbalance, reporting balanced loads. The imbalance is real but **not universal** — it correlates with cable mating-cycle history and seating. This is the strongest argument for prioritizing a **trend/imbalance** alarm over a fixed absolute current threshold.