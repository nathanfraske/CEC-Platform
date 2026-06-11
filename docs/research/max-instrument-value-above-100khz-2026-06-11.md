# Above-100-kHz Instrument Value for PC Power Telemetry: A Scoping Verdict for CEC's "Max" Tier

## TL;DR
- **Mostly no, with one narrow yes.** Setting failure prevention aside, the only genuinely instrument-grade, market-validated use case above ~1–2 MS/s is **spec-faithful ATX ripple-and-noise measurement** (Intel's 10 Hz–20 MHz band), which needs analog bandwidth to 20 MHz and a sample rate of roughly 50–100 MS/s on **one shared AC-coupled voltage channel** — not six fast current channels. Every other above-100-kHz candidate is either not observable at the connector or has no published precedent.
- **The most novel candidate — connector-side VRM phase/interleave fingerprinting — fails the observability gate.** A targeted literature sweep found **no published measurement** of VRM switching-frequency ripple current surviving onto the 12 V harness, and the entire PC power-measurement ecosystem (Powenetics v2 at 1000 S/s, ElmorLabs PMD at 5–34 kS/s, igorsLAB's scope rig at ~100 kS/s) is deliberately band-limited below the 300 kHz–1.2 MHz switching regime. Interleaving plus the card's input capacitor bank confine that ripple to the board.
- **Recommendation: kill the six-channel fast array. Build at most ONE shared wideband voltage+current "instrument" channel** (20 MHz analog BW, ~50–100 MS/s) and market it as an in-system ripple/transient scope — or, if that channel cannot be justified commercially, fall back to telemetry-only at 1–2 MS/s. The original arc-detection-derived quad-ADC-at-20–25-MSPS architecture has no surviving justification.

## Key Findings

1. **ATX ripple/noise is the one defensible instrument use case, and its requirements are well-defined.** Intel's ATX design guide (ATX 3.0 / ATX12VO, "Output Ripple Noise – REQUIRED") states verbatim: *"Ripple and noise are defined as periodic or random signals over a frequency band of 10 Hz to 20 MHz. Measurements must be made with an oscilloscope with 20 MHz of bandwidth. Outputs should be bypassed at the connector with a 0.1μF ceramic disk capacitor and a 10 μF electrolytic capacitor to simulate system loading"* (T2/T3). Pass limits from the DC Output Noise/Ripple table: **120 mV peak-to-peak on +12 V, 50 mV on +5 V and +3.3 V, 120 mV on −12 V, 50 mV on +5VSB**. This is exactly what every PSU reviewer and certification lab measures today.

2. **Spec fidelity requires ~20 MHz analog bandwidth and ~50–100 MS/s — far above 1–2 MS/s, but on a voltage channel, not a current channel.** The 20 MHz ceiling exists specifically to capture switching-edge and diode reverse-recovery spike content; the switching fundamental for consumer PSUs is far lower (secondary-side FETs typically 20–300 kHz). A faithful instrument therefore needs an AC-coupled wideband **voltage** tap, which is a different front end from CEC's shunt-plus-INA240 current chain.

3. **The VRM-fingerprinting use case — the most novel — is not observable at the connector.** Multiphase GPU/CPU VRMs switch at **250 kHz–1.2 MHz per phase** — the onsemi NCP81610 datasheet (a controller explicitly "optimized for new generation computing and graphics processors," "Compliant with NVIDIA OVR4i+ Specifications") specifies *"250 kHz to 1.2 MHz Switching Frequency (8 Phase)"* (T3). Their pulsed input current is largely cancelled by interleaving and absorbed by the on-board input capacitor bank before reaching the harness. My targeted search confirmed there is **no published measurement** of this ripple at the cable, and the standard reviewer tools cannot see it.

4. **High-frequency EMC/conducted-emission monitoring has a strong precedent (automotive CISPR 25, 150 kHz–108 MHz on 12 V DC lines), but a 10–25 MS/s chain covers only a sliver of it and cannot replace a LISN + EMI receiver.** Per CISPR 25:2021 (Ed. 5), conducted-emission measurements span *"150 kHz to 108 MHz using peak and average detectors"* using a 5 µH LISN on the reference ground plane (T2). This is a plausible-but-weak "rough spectral monitor" pitch, not a compliance instrument.

5. **Capacitor-health-via-ripple and PDN-resonance characterization both drift back toward health monitoring or are marginal at the connector.** They bound the band but do not create new instrument demand.

6. **Load-transient slew-rate measurement is real and unserved, but it lives below 1 MHz for the edges ATX 3.x actually specifies.** A 5 A/µs / 1 µs-class edge implies content only to ~350 kHz; this is reachable by a modest fast channel, and it is the strongest *secondary* reason to build the single wideband channel.

## Details

### A. Phenomena Inventory (each candidate, above 100 kHz)

**Candidate 1 — ATX ripple & noise (spec-faithful).**
- *Band / generator:* 10 Hz–20 MHz; switching fundamental (consumer secondary FETs ~20–300 kHz) plus HF spike content from switching edges and diode reverse recovery (the reason the 20 MHz limit exists).
- *Observable at connector?* **Yes** — this is a voltage-ripple measurement, and the ATX method explicitly measures at the connector with defined bypass caps. CEC's connectors sit exactly where the spec says to measure.
- *Instrument today / price:* 20-MHz-capable oscilloscope + electronic load. Rigol DHO800 (100 MHz, 1.25 GS/s, 12-bit, 25 Mpts) from roughly €330–550; Cybenetics uses PicoScope 4444 and Siglent SDS2104X-Plus.
- *Buyer:* PSU reviewers, certification labs (Cybenetics, Tom's Hardware, TechPowerUp, Hardware Busters), PSU manufacturers, system integrators.
- *Literature:* Intel ATX design guide (T2/T3); Cybenetics test protocol (T4); Teledyne LeCroy / Tektronix / CUI probing notes (T3/T4).
- **Verdict: validated-and-observable.** This is the anchor use case.

**Candidate 2 — Connector-side VRM input-current spectral analysis (phase-count fingerprinting, interleave quality, dead-phase detection, fSW-vs-temperature drift).**
- *Band / generator:* N × per-phase switching frequency; per-phase 250 kHz–1.2 MHz (NCP81610, T3), effective input ripple at N times that.
- *Observable at connector?* **No (gating failure).** Interleaving minimizes input-capacitor RMS current and the on-board MLCC+bulk bank sources the pulsed current locally; an LC input filter set at ~1/10 fSW gives ~40 dB attenuation at the fundamental. A dedicated literature sweep found **no published oscilloscope capture or conducted-emission spectrum of switching-frequency ripple current/voltage on a PC 12 V cable at the connector.** The reviewer tool ecosystem is band-limited well below this regime: Powenetics v2 samples at 1000 S/s (Hardware Busters: *"we achieved the desired 1000 samples per second data polling rate, from ALL sensors, for both voltage and current"*; 1 mV / 5 mA resolution); ElmorLabs PMD internal ADC ~34 kHz but host-library-limited to ~10 Hz, with researchers achieving only ~5 kS/s via custom loggers (Doekemeijer et al., "PowerSensor3," arXiv:2504.17883, 2025: *"while PMD has an internal sampling frequency of 34 kHz, PMD's (Windows-only) host library limits updates to a sampling frequency of 10 Hz. Yang et al. developed their own data logger to achieve a sampling frequency of 5 kHz"*); igorsLAB's transient scope rig uses 10 µs intervals (~100 kS/s, ~50 kHz Nyquist).
- *Literature:* multiphase input-cap cancellation (EDN, Analog Devices — T3/T4); capacitor condition monitoring (IEEE TPEL/IE reviews — T1) as the *closest validated analog*, but those works observe the capacitor's *own* ripple, not a remote harness measurement.
- **Verdict: not-observable-at-the-connector / novel-and-unvalidated.** This kills the headline novelty.

**Candidate 3 — Load-transient edge / slew-rate characterization.**
- *Band / generator:* ATX 3.x excursions — per Intel ATX 3.0 (via Tom's Hardware): *"power supplies with the 12VHPWR connector must be able to handle up to 200% of their rated power for at least 100μs, 180% for 1ms, 160% for 10ms, and 120% for 100ms"*; +12V slew rate, per Intel, *"should not exceed 5A/μs"* for the 12VHPWR connector (2.5 A/µs for ≤450 W units without it). By the 0.35/Tr rule, a 1 µs edge ⇒ ~350 kHz; a sub-µs edge ⇒ low MHz.
- *Observable at connector?* **Yes** — these are large-signal current/voltage events on the harness, exactly where CEC measures. Published GPU data is magnitude-vs-duration (igorsLAB), not dI/dt; a real magnitude+duration+slew histogram does not exist publicly.
- *Instrument today / price:* 4-channel scope + DC current probes (Tom's Hardware used a HAMEG HMO3054 500 MHz with HZO50 probes; microsecond resolution). ElmorLabs PMD2 ($99) cannot capture this — its effective per-channel rate is in the kHz. (Powenetics v2's 12VHPWR sensors are rated *"up to 60A sustained and up to 150A power spikes of up to 1 ms to cover the PCIe 5.0 transient response scenarios"* — millisecond envelope, not dI/dt.)
- *Buyer:* reviewers, PSU manufacturers, transient-compatibility enthusiasts.
- **Verdict: validated-and-observable, but sub-MHz.** Strongest secondary justification for a single fast channel; does NOT need 20 MS/s+.

**Candidate 4 — HF spike / conducted-emission monitoring (1–50 MHz).**
- *Band / generator:* switching-edge and diode reverse-recovery spikes; CISPR conducted-emission band 150 kHz–30 MHz (commercial) / **150 kHz–108 MHz (automotive CISPR 25 on 12 V DC lines with 5 µH LISNs** — directly relevant DC-line precedent, T2).
- *Observable at connector?* **Partially** — differential-mode content is observable, but quantitative, calibrated measurement needs a LISN and EMI receiver. A 10–25 MS/s chain (Nyquist 5–12.5 MHz) covers only the lowest part of the 150 kHz–30 MHz band.
- *Buyer:* EMC pre-compliance labs, manufacturers (noise-source localization).
- **Verdict: plausible-but-unvalidated** as a rough monitor; cannot be a compliance instrument.

**Candidate 5 — Capacitor/filter health via switching-ripple amplitude trending.**
- *Band:* PSU switching frequency, straddling 100 kHz. ESR-driven ripple growth is a published condition-monitoring field (IEEE TPEL/IE; Lahyani et al. measure ripple at the switching frequency — T1).
- *Observable at connector?* Partially for the PSU's own output ripple; **drifts back toward health monitoring**, which the owner has set aside.
- **Verdict: validated technique, but out of scope (health), included only to bound the band.**

**Candidate 6 — Other (spread-spectrum signatures, PDN resonance/ringing, TDR on cables, PLC crosstalk).**
- *Spread-spectrum:* SSFM spreads switching energy ±~10%; detectable in principle but only if switching content reaches the connector (it doesn't — see Candidate 2).
- *PDN resonance / hot-plug ringing:* harness inductance against load input capacitance can ring (kHz–low-MHz); observable at hot-plug/large transients, but no market pays to measure it on PCs.
- *TDR / PLC:* no PC-market precedent.
- **Verdict: not-observable or no-market.**

### B. Observability Analysis (the gate)

The single question that decides the VRM-fingerprinting case is whether differential-mode switching-noise from a multiphase VRM propagates through its input capacitor bank into the supply harness. The physics and the literature both say **no, not meaningfully**:
- Multiphase interleaving is explicitly designed to cancel input-capacitor RMS current; design literature notes the input-cap RMS current can be "substantially eliminated" at favorable duty cycles (EDN, T4).
- An input LC filter sized at ~1/10 fSW provides ~40 dB at the fundamental (passive-components.eu, T3/T4); the on-board MLCC+bulk bank sources the high-frequency pulsed current locally.
- **Direct measurement evidence is absent.** No igorsLAB, TechPowerUp, Tom's Hardware, or EMC source publishes residual switching-frequency ripple at the connector; the standard tools are band-limited below it. This is a documented absence and a deliverable in itself.

Because observability fails, every diagnostic built on it (phase-count fingerprint, interleave quality, dead-phase detection, fSW-vs-temperature) is **novel-and-unvalidated and likely not physically reachable** from CEC's measurement point. A connector-side spectral fingerprint is therefore **not** a usable repair-shop tool today; repair shops use thermal cameras, multimeters, and manual probing on the board itself.

### C. Instrument-Market Evidence (T4, load-bearing for demand)

- **ElmorLabs PMD2 — the category-defining comparable.** Priced at **$99** (the predecessor PMD is listed at $45–60), sold explicitly to "enthusiasts, overclockers, and reviewers." It sits between PSU and load on EPS, PCIe 8-pin, ATX 24-pin, and 12VHPWR, with an OLED and USB-C logging "oscilloscope functionality." Its internal ADC runs ~285.7 kHz but is multiplexed across 8 channels and historically I2C/host-limited to ~10 kS/s. **Crucially, it does not resolve switching-frequency or fast-transient content — its "scope mode" is a slow logger.** This proves the *instrument framing sells*, and also reveals an unserved gap: nobody offers a true wideband in-harness capture.
- **Oscilloscope + current-probe stack today:** a Rigol DHO800-class scope (100 MHz, 1.25 GS/s, 12-bit) at roughly €330–550 plus a competent DC current probe (often comparable to or exceeding the scope's cost) — a multi-hundred-to-low-thousand-dollar stack, plus an electronic load for proper ripple/transient work. (For reference, the reviewer-grade Powenetics v2 logging system is priced at €975 per arXiv:2504.17883.)
- **Lab methodology:** Cybenetics measures ripple per the ATX 20 MHz method (PicoScope 4444, Siglent SDS2104X-Plus) and runs ATX 3.x transient tests; Tom's Hardware historically used a 500 MHz HAMEG rig with current probes for microsecond-resolution current.
- **Reading:** demand for *power-as-a-tool* is real and growing (PMD2's existence and reception), but the demand that's proven is for **per-connector power/current logging and ripple/transient visualization**, not for above-MHz spectral analysis.

### D. The Verdict (structured)

**(a) Is there any value above 1–2 MS/s? Narrowly, yes — for one use case only.**
- ATX ripple/noise (Candidate 1): **yes**, needs 20 MHz BW ⇒ ~50–100 MS/s. This is the only above-1–2-MS/s use case that is simultaneously observable, validated, and market-demanded.
- Transient slew (Candidate 3): yes to value, but the edges ATX 3.x specifies need only ~350 kHz–low-MHz BW (≈1–5 MS/s) — it does **not** drive the sample rate above a few MS/s.
- VRM fingerprinting (Candidate 2): **no** — fails observability.
- EMC monitor (Candidate 4): marginal; 10–25 MS/s covers only the band's bottom and isn't a compliance tool.

**(b) Sample rate / analog bandwidth each surviving case justifies:**
- Spec-faithful ripple: **20 MHz analog BW, ~50–100 MS/s** (to honor the 10 Hz–20 MHz definition and resolve spike content). AC-coupled.
- Transient slew + envelope: 1–5 MS/s, ~350 kHz–1 MHz BW.

**(c) Channel configuration — the decisive architecture point.** No surviving use case needs six per-pin fast channels. Ripple is a **rail-level voltage** phenomenon (one shared AC-coupled wideband voltage channel per rail-of-interest, realistically one switchable channel). Transient slew needs one current + one voltage channel. **One shared wideband voltage+current "instrument" channel, multiplexed/switchable across connectors, covers everything that survives.** The six-channel fast array is unjustified.

**(d) Sensing-front-end implication.** The existing chain dies above its limits: the **~80 kHz shunt inductive corner** (response becomes di/dt-dominated) and the **400 kHz INA240 bandwidth** both fall far short of 20 MHz. A wideband instrument channel must instead provide:
- **Voltage ripple:** an **AC-coupled resistive divider / wideband FET-input buffer** (rail-probe-style split AC/DC path) to 20 MHz, the way bench ripple measurement is done.
- **Current (for transients):** a **compensated/current-transformer or wideband current-sense** path, since the milliohm shunt + INA240 cannot reach the needed bandwidth. For switching-frequency *current* the point is moot (not observable); for transient dI/dt a CT or a properly compensated shunt to ~1 MHz suffices.

## Recommendations

**Stage 1 — Decide on the single instrument channel (the only real choice).**
- **Option A (recommended if a credible "in-system ATX-ripple + transient scope" market case exists): build ONE shared wideband voltage+current channel** — 20 MHz analog BW, ~50–100 MS/s, AC-coupled divider front end for ripple, CT/compensated path for transient current, switchable across connectors. Market it as an instrument (the way the PMD2 and bench scopes sell), with **no failure-prevention story**. This unlocks spec-faithful ripple, transient slew/envelope, and a rough low-MHz noise monitor.
- **Option B (recommended if the channel can't pay for itself): telemetry-only at 1–2 MS/s.** This already captures all validated health/diagnostic value and all ATX 3.x transient *magnitude-duration* classes; it forgoes only spec-fidelity ripple and dI/dt.
- **Option C — REJECT: the original six-channel fast array (quad ADCs at 20–25 MSPS, per-pin).** Its arc-detection justification is dead, no surviving use case needs per-pin fast channels, and the headline novelty (VRM fingerprinting) fails observability.

**Stage 2 — Validate Option A before committing silicon.** Run one bench experiment: instrument a real GPU's 12VHPWR/PCIe connector with a wideband current probe + spectrum analyzer and a wideband voltage tap, under gaming/FurMark and transient load. **Benchmark that flips the decision:** if measurable switching-frequency ripple current (say >1% of DC, or a clean N×fSW line above the noise floor) appears at the connector, reopen Candidate 2; if it does not (the expected result), Candidate 2 stays dead and the channel is justified by ripple+transients alone.

**Stage 3 — Position commercially against the PMD2.** The defensible differentiator is **true wideband in-harness capture** (20 MHz ripple + microsecond transients) that the $99 PMD2 and slow loggers cannot do — but price/complexity must be weighed against a ~€330–550 bench scope that already does ripple. If CEC cannot beat the scope-plus-load stack on convenience or in-system fidelity, default to Option B.

## Caveats
- **Documented absences are findings, not gaps to paper over.** No public source measures VRM switching ripple at the PC connector; no public GPU dI/dt-at-connector dataset exists; no published GPU 12 V-input conducted-emission spectrum was found. These absences are load-bearing for the "kill the fast chain" verdict.
- **PMD2 internal sample-rate figures (~285.7 kHz ADC, ~10 kS/s host)** come from a vendor forum post and predecessor docs (T4); the ~34 kHz internal / 10 Hz host / 5 kHz custom-logger figures are from arXiv:2504.17883 (academic). Treat as indicative.
- **Rigol/probe and Powenetics pricing** is approximate and regional; the directional point (a multi-hundred-dollar to ~€1k stack) holds.
- **Consumer-PSU switching-fundamental range (20–300 kHz)** is from reviewer/vendor methodology (T4) and varies by topology (LLC resonant, etc.).
- The EMC-monitor case (Candidate 4) rests on automotive CISPR 25 precedent (T2) being *analogous*, not on a PC-specific validated method.
- This analysis assumes CEC's stated front-end limits (80 kHz shunt corner, 400 kHz INA240) and connector-side measurement point as given.

## Source Documentation (tiered, ranked by load-bearing weight)

**T2 — Standards / national-lab / government**
1. Intel ATX 3.0 / ATX12VO Desktop Power Supply Design Guide, "Output Ripple Noise – REQUIRED" and DC Output Noise/Ripple table (edc.intel.com; cdrdv2-public.intel.com/613768). *Carries:* the 10 Hz–20 MHz band, 20 MHz scope, 0.1 µF/10 µF bypass method, and per-rail ripple limits — the anchor of Candidate 1 and the (b)/(c) requirements.
2. Intel ATX 3.0 spec, DC Output Transient Step Sizes / Slew Rate tables (via Tom's Hardware; Cybenetics-hosted PDF). *Carries:* the 200%/180%/160%/120% excursion brackets and 5 A/µs slew — Candidate 3 band.
3. CISPR 25:2021 Ed. 5, conducted-emission method 150 kHz–108 MHz with 5 µH DC LISNs (In Compliance Magazine; TESTUPS; Com-Power LI-550C). *Carries:* the DC-line conducted-emission precedent for Candidate 4.

**T1 — Peer-reviewed**
4. Doekemeijer et al., "PowerSensor3," arXiv:2504.17883 (2025). *Carries:* PMD 34 kHz-internal/10 Hz-host/5 kHz-custom sampling and the €975 Powenetics v2 price — the observability-gate instrument-bandwidth evidence.
5. IEEE TPEL / Industrial Electronics capacitor condition-monitoring reviews; Lahyani et al. (ripple-at-switching-frequency ESR monitoring). *Carries:* Candidate 5 as the closest validated analog to VRM spectral diagnostics.

**T3 — Datasheets / design guides / interface specs**
6. onsemi NCP81610 datasheet (ncp81610-d.pdf). *Carries:* GPU/CPU VRM per-phase 250 kHz–1.2 MHz switching frequency — Candidate 2 band.
7. passive-components.eu "Input filters / Buck converter design"; Analog Devices and TI EMI app notes. *Carries:* ~40 dB input-filter attenuation at ~10× fSW and DM/CM split — observability physics.

**T4 — Trade press / reviewer methodology (market-demand + corroboration)**
8. ElmorLabs PMD/PMD2 product pages + forum ADC post; VideoCardz. *Carries:* $99 price, connector set, ~285.7 kHz/10 kS/s scope-mode limit — category-defining comparable.
9. Hardware Busters / Cybenetics (Powenetics v2 1000 S/s, 1 mV/5 mA; test protocol; PicoScope/Siglent). *Carries:* reviewer-tool bandwidth and lab ripple/transient methodology.
10. igorsLAB (10 µs transient rig; magnitude-vs-duration GPU data) and Tom's Hardware (HAMEG HMO3054 + HZO50 methodology). *Carries:* connector-side measurement state of the art and absence of dI/dt data.
11. EDN/EEPower (multiphase input-cap cancellation; rise-time↔bandwidth 0.35/Tr); Rigol DHO800 product/pricing pages. *Carries:* interleave cancellation, the rise-time math, and the cost stack.

**Searches / source classes that came back EMPTY (documented absences):**
- Oscilloscope capture or spectrum of switching-frequency ripple current/voltage on a PC 12 V cable/connector — none found in reviewer or EMC literature.
- Published differential-mode conducted-emission spectrum measured on a real desktop GPU's 12 V input — none found (method exists; GPU-specific measurement not published).
- Named per-card GPU 12 V-input bulk-capacitance totals and measured switching-frequency insertion loss — only qualitative/partial data.
- Published GPU current slew-rate (dI/dt) at the connector — confirmed absent (prior dives; reaffirmed here).
- Any commercial product or market evidence for connector-side VRM phase-fingerprinting as a repair/diagnostic tool — none; repair shops use thermal cameras, multimeters, manual probing.