# Connector Micro-Arcing Likelihood and the Sampling-Rate Value Curve

**Status:** research-grade, derivation-class where marked. Not a spec document; feeds corpus
entries and open questions, never amends the spec directly.
**Date:** 2026-06-11
**Provenance:** deep-research run 2026-06-11, three owner-scoped deliverables, adversarial
panel review pending at vendoring. Companion documents in this series:
`docs/research/dc-series-arc-signatures-2026-06-11.md` (the 12 V arc-sustainability and
band verdict this document builds on), `docs/research/oq10-vertical-transitions-2026-06-11.md`,
and `docs/research/gpu-12vhpwr-fault-phenomenology-2026-06-10.md`.
**Gates fed:** OQ-16/OQ-17/OQ-18 follow-on, OQ-15 (Max positioning), OQ-19 (Max compute),
the Max fast-capture architecture decision, and the Tier A/Tier B sensing roadmap.

## Citation convention

Every numeric claim carries a bracketed reference. Tiers, per the repository research
convention: **T1** peer-reviewed journal or archival conference; **T2** standards body,
national laboratory, or government record; **T3** manufacturer datasheet, product
specification, or official design guide (authoritative for that component or interface);
**T4** enthusiast, trade-press, or third-party-lab material, admitted as corroboration
only, never load-bearing. Claims the run could not pin to a primary source are listed in
the Verification Register and marked VERIFY inline.

---

## Deliverable 1: Micro-arcing and showering-arc likelihood in the PC environment

### 1.1 The physics boundary this document inherits

The companion arc-signatures document established, from contact physics, that a sustained
series arc at 12 V DC is marginal to impossible: minimum arc voltages for common contact
metals cluster at roughly 11 to 16 V (silver 11 to 12.5 V, gold 15 V at 0.38 A minimum
current) [16], and the 42 V automotive arc-fault literature exists precisely because 14 V
marginally sustains arcs where 42 V readily does [1][6-companion]. What remains physically
available at 12 V is the micro-arc regime: with nanosecond-capable instrumentation,
intermittent arcs of 5 to 100 ns duration are documented below the classical minimum arc
voltage and current, down to a material-dependent limiting current generally below 100 mA
[16, citing Ben Jemaa 1984/2002 and Hasegawa 2005]. VERIFY: tin and copper Vmin/Imin
specifically; the primary table confirmed covers noble metals, and the 12 to 16 V framing
for Cu/Sn rests on the noble-metal cluster plus secondary sources pending Holm (1967) or
Slade (2014, ch. 9) [V-1].

### 1.2 Mechanical preconditions: fretting onset thresholds versus the PC environment

The controlling variable for fretting corrosion is slip amplitude relative to a
normal-force-dependent threshold. Park, Narayanan and Lee ran tin-on-copper-alloy
contacts at amplitudes from plus-minus 5 to plus-minus 25 µm (extended work to 90 µm), 3
to 20 Hz, 0.5 N normal load, 0.1 to 0.5 A, tracking time to a 100 mΩ resistance
threshold; notably the 5 µm slip reached the threshold faster than 25 µm because
oxidation confines to a smaller percolation area [3]. The threshold displacement
amplitude separating stabilized partial slip (effectively infinite electrical life) from
gross slip (coating wear and degradation) is linearly proportional to contact normal
force [10, VERIFY full citation]. A temperature study of tin-plated brass at 298 to 373 K
under 0.85 N found contact resistance rising rapidly and intermittently with fretting
cycles, with failure life dropping as temperature rose [9, VERIFY full citation]. The
review framing places electrical-contact fretting in the sub-100 µm slip regime [11].

Against those thresholds, the PC case presents:

- **HDD vibration:** tonal at the rotational frequency, 90 Hz at 5400 RPM and 120 Hz at
  7200 RPM, plus broadband seek impulses [23, T4]; isolation literature works the 5 to
  500 Hz band [8].
- **Fan vibration:** torque-ripple energy concentrating above 300 to 500 Hz; a 6000 RPM
  fan produces a 100 Hz fundamental plus harmonics [24][25, patents, T4-adjacent].
- **Thermal-cycling micro-motion:** differential expansion at the connector from
  documented load-cycle temperature swings (roughly 30 °C idle to 90 °C and beyond at
  degraded contacts) produces micro-slip that connector-reliability sources place in the
  10 to 100 µm range, overlapping the fretting-onset band [26, T4][27, T4]. This is the
  most credible micro-motion source inside a PC, ahead of fan and HDD vibration.

**Honest gap:** no published vibration spectrum or measured connector micro-slip
amplitude exists for PC power connectors specifically. Every threshold above transfers
from automotive and tribology work on the same Mini-Fit-class tin-plated copper contact
system. The PC fretting case is plausible by material analogy, never directly measured
[V-2].

### 1.3 Electrical observables under energized micro-motion

Three nested signal classes, in order of likelihood and literature strength:

1. **Contact-resistance and voltage-drop rise (dominant, well validated).** Contact
   voltage climbs from under 20 mV (clean constriction) through hundreds of mV (fritting
   and melting regime) as fretting wear accumulates [1][2]; resistance fluctuates
   repetitively between 100 and 3500 mΩ in late-stage fretting (40,000 to 70,000 cycles
   in the current-load study) [7]. Intermittence detection methodology dates to Murrell
   and McCarthy [4].
2. **Micro-breaks during vibration (validated in qualification testing).** Automotive
   and connector qualification monitors discontinuities of at least 1 µs duration during
   vibration (EIA-364-28; USCAR-2 rev 8), with nanosecond-class event detection per
   EIA-364-87 [13][14]. The USCAR chassis profile (1.81 g RMS) is far harsher than a PC
   interior. Micro-interruptions in tin Mini-Fit-class contacts under vibration are
   real and measured, manifesting as resistance spikes rather than arcs.
3. **Short arcs and showering arcs (real, late-stage, conditional).** Ben Jemaa and
   Carvou observed short arcs "for the first time in fretting under power" at 20 V and 3
   A, only in the final degradation stage, attributed to bounce, proposed (their hedge,
   preserved here) as a wear-accentuating mechanism [1]. The showering-arc lineage
   (Curtis 1940; Atalla 1953 to 1955) establishes the preconditions: an inductive
   circuit, contact opening, and enough stored inductive energy for the L di/dt kick to
   repeatedly re-break the gap [5][6]. A 12 V rail feeding a short, low-inductance
   harness into a capacitive VRM input at a connector that is not being opened is a poor
   showering-arc circuit; the precondition is largely absent in steady-state operation.

### 1.4 Per-connector likelihood ranking

| Rank | Connector | Contact class, normal force | Current versus rating | Geometry and load balance | Field history | Micro-arc expectation |
|---|---|---|---|---|---|---|
| 1 | 12VHPWR / 12V-2x6 | Micro-Fit-class CEM-5, 3.0 mm pitch; Micro-Fit normal force specified 375 gf max per contact [19] | 9.2 A/pin rated [17]; roughly 8.3 A/pin nominal at 600 W, about 90 percent utilized | 6 power pins internally commoned on the GPU side, so single-pin contact loss is invisible to the card and current crowds onto surviving pins | Documented melting failures; CPSC recall of CableMod angled adapters cited 272 incident reports across roughly 25,300 units, about 1.07 percent [15]; subsequent RTX 5090 FE socket melting corroborated [30, T4] | Highest: highest fractional current, smallest margin, collapse mode concentrates current |
| 2 | EPS 8-pin | Mini-Fit Jr, 4.20 mm pitch, tin; 0.49 N minimum normal force, 30 mating cycles, 10 mΩ contact resistance [18] | Typically well below rating | 4 separate power circuits | Essentially no field arc or melt reports | Low |
| 3 | PCIe 8-pin | Mini-Fit Jr family, tin | Roughly 30 to 60 percent of rating | 3 power circuits | Essentially no field reports | Low |
| 4 | ATX 24-pin | Mini-Fit Jr, mixed rails | Typically 30 to 60 percent of rating across many pins | Many pins, low per-pin current | None | Lowest |

Mini-Fit Jr vibration qualification allows discontinuities up to 1 µs at 1.5 mm
peak-to-peak, 10 to 55 Hz, 2 hours per axis [18]. The 12VHPWR family's mating-cycle life
of roughly 30 to 40 cycles [29, T4, consistent with the Molex 30-cycle tin spec [18]]
means inspection-by-reseating consumes the very wear budget it tries to protect, the
inspection paradox already encoded in the corpus.

### 1.5 Bottom line per connector

- **12VHPWR / 12V-2x6:** design detection here, and the literature-supported signal is
  per-pin current imbalance plus contact-resistance and voltage-drop trending, never arc
  capture. Micro-arcs, if they occur, are a 5 to 100 ns lagging indicator of a contact
  that resistance trending would already have flagged. Field event-rate data for PC
  connectors does not exist; no product claim may state arc rates [V-3].
- **EPS, PCIe, 24-pin:** contact-resistance trending is the only supported signal;
  micro-arcing is not an expected phenomenon at their current fractions.
- The 1.07 percent CPSC adapter incident rate [15] is the only quantified field failure
  prior in this document and applies to one adapter product line, never to the connector
  class generally.

---

## Deliverable 2: The sampling-rate-versus-diagnostic-value curve

### 2.1 The curve

| Rate | Newly accessible phenomena | Detect versus resolve | Diagnostic value |
|---|---|---|---|
| 1 S/s | Thermal drift, energy totals, degradation trends (hours to months), capacitor aging and electromigration trends (months to years) | Resolves trends | High for health and fleet monitoring |
| 10 S/s | Coarse load states, idle/load transitions | Resolves slow load change | Moderate |
| 100 S/s | Per-second dynamics, fan/pump RPM-correlated envelope | Detects low-frequency mechanical modulation envelope | Moderate |
| 1 kS/s | Rectification ripple envelope (100/120 Hz) [17], millisecond hold-up events [21] | Detects 100/120 Hz; resolves ms transients | High |
| 10 kS/s | ATX transient response, GPU 100 µs to 10 ms excursion envelopes [17][31], coil-whine-band onset | Detects and partially resolves GPU transient classes | High; the knee for consumer-relevant load dynamics |
| 100 kS/s | PSU switching ripple (25 to 150 kHz) detected or aliased [17]; fretting micro-break envelopes; fast transient edges | Detects switching ripple; resolves µs transients | Moderate-high; the 1 mΩ shunt inductive corner near 80 kHz begins limiting fidelity (companion doc) |
| 1 MS/s | VRM switching fundamentals (250 kHz to about 1 MHz) resolved [VRM range, T3-class, VERIFY representative controller citations V-4] | Resolves VRM switching | Moderate; mostly signal-integrity rather than health |
| 10 MS/s | VRM harmonics, EMC-band content | Resolves HF harmonics | Low for telemetry; the Sandia null result (no arc-versus-baseline separation, 100 kHz to 5 MHz) applies [12] |
| 100 MS/s and beyond | Individual 5 to 100 ns micro-arc waveforms [16]; signal-integrity and EMC lab work | Resolves single arc events | Negligible for power-integrity telemetry; oscilloscope territory, never a fleet sensor |

### 2.2 Phenomenon timescales and minimum rates

- **Rectification ripple, 100/120 Hz.** ATX limits 120 mV p-p on 12 V rails, 50 mV on 5
  V, 3.3 V, 5VSB [17]. Detect near 1 kS/s; resolve near 10 kS/s.
- **Switching ripple, 25 to 150 kHz consumer class.** The design guide defines ripple
  and noise over 10 Hz to 20 MHz, measured with a 20 MHz bandwidth oscilloscope [17];
  the 20 MHz figure is a measurement-bandwidth convention, never a claim that diagnostic
  content extends there. Detect or alias near 100 kS/s; resolve near 300 kS/s to 1 MS/s.
- **Hold-up and transient response, ms class.** ATX 3.1 relaxed full-load hold-up from
  17 ms to 12 ms, with 17 ms recommended at 80 percent load [21, T4 vendor knowledge
  base; VERIFY against the design guide revision at vendoring, V-5]. Resolve near 1 kS/s.
- **GPU load transients.** The ATX 3.0 excursion classes (3x at or below 100 µs, the
  logarithmic curve to 1 s) and the measured RTX 5090 duration-resolved spike table are
  carried in the fault-phenomenology document; detect at 10 kS/s, resolve the fastest
  edges near 1 MS/s [17][31][companion doc].
- **Inrush, sub-ms to ms.** Resolve near 10 kS/s.
- **Micro-arc bursts, 5 to 100 ns single events [16].** Resolving the waveform needs 100
  MS/s and faster. Detecting an envelope or rate signature at a degrading contact, as a
  statistical rise in noise or voltage variance, is plausible at kHz to tens-of-kHz
  rates, and no validated PC method exists [V-3]. The distinction between resolving an
  event and detecting its envelope is the load-bearing distinction of this deliverable.
- **Degradation trends.** 1 S/s and slower; this is where dV/dI lives.
- **Capacitor aging via ripple-RMS growth.** Periodic 1 to 10 kS/s sampling, trended over
  months.
- **Fan, pump commutation, coil-whine-correlated oscillation.** Audible band; detect at
  10 to 40 kS/s.

### 2.3 The flattening verdict

For a current and voltage power-integrity telemetry sampler, the diagnostic value curve
flattens at roughly **1 to 2 MS/s**. Three independent ceilings converge there: the VRM
harmonic ceiling near 1 MHz is already resolved; Sandia measured no arc-versus-baseline
spectral separation from 100 kHz to 5 MHz with a 10 MHz capture chain, recommending
detection below 100 kHz [12]; and the platform's own front end (1 mΩ shunt inductive
corner near 80 kHz, INA240 bandwidth 400 kHz at minus 3 dB) caps usable fidelity well
before the sampler does [20][companion docs]. Faster instrumentation is legitimate for
signal-integrity and EMC lab work, and it is not telemetry: no documented PC power
phenomenon yields additional health-diagnostic information to a fielded current or
voltage sampler above this rate. VERIFY: the Sandia null transfers from PV voltages
(hundreds of volts); whether any 12 to 48 V arc spectral measurement contradicts it is
the open falsification path, registered as follow-up R-1 below [V-6].

### 2.4 Aliasing, honestly

An undersampled switching ripple folds to a low-frequency alias that misleads if read as
real frequency content, while its RMS energy remains captured and is diagnostically valid
for amplitude trending (capacitor aging). Rule for the platform: aliased energy serves
amplitude and RMS trend metrics, never frequency claims, unless the band is properly
resolved. For micro-arc bursts, an aliased or enveloped signature could flag elevated
variance and cannot be inverted to an event count without validation that does not yet
exist [V-3].

---

## Deliverable 3: The phenomena-band table

### 3.1 Tier A: current platform reach

Sensing basis: milliohm shunts with INA240-class amplifiers at tens-of-kS/s effective
bandwidth, per-pin and per-rail voltage, the dV/dI impedance trend, NTC temperature,
INA228-class energy and charge accumulation [20].

| Band or timescale | Phenomenon | Diagnoses | Segment | Tier A sensor |
|---|---|---|---|---|
| Months to years | Capacitor aging (ripple-RMS growth) | PSU end of life | Fleet, server, enthusiast | Periodic ripple RMS via shunt and INA |
| Hours to months | Electromigration, fretting buildup, contact-resistance creep | Connector and solder degradation | All | dV/dI trend, per-pin voltage drop |
| DC to 100 Hz | Per-pin current imbalance | 12VHPWR pin loss, load-balance failure | Enthusiast, repair, fleet | Per-pin shunt current |
| 100/120 Hz | Rectification ripple | Bulk capacitor and input-stage health | Enthusiast, repair | Shunt and voltage at 1 to 10 kS/s |
| ms | Hold-up, transient response | PSU dynamic adequacy | Enthusiast, server | Voltage at 1 kS/s |
| 1 µs to 10 ms | GPU load transients and excursions | PSU sizing, crash diagnosis | Enthusiast, overclock | Shunt and voltage at 10 kS/s to the front-end limit |
| Continuous | Energy and charge accumulation | Thermal-stress dosimetry, efficiency | Fleet, server | INA228-class registers |
| Continuous | Connector temperature | Hot-pin early warning | All, especially 12VHPWR | NTC at the connector |

### 3.2 Tier B: exploratory, beyond the shunt

| Sensor | Unique reach | Adjacent-domain literature | Feasibility note |
|---|---|---|---|
| Rogowski coil, HF current transformer | 100 kHz to 10 MHz di/dt content | Validated for arc detection in AC and higher-voltage DC contexts; cannot measure DC, needs an integrator | Low value here: the Sandia null [12] removes the band's information content at low voltage, and per-pin integration around six commoned pins is impractical |
| Capacitive, E-field pickup | Fast dV/dt edges | EMC near-field probing | Low: redundant with voltage sensing, no unique health signal |
| Acoustic, ultrasonic | Arc acoustic emission, coil-whine signature | Strong in HV switchgear partial-discharge practice; no low-voltage micro-arc acoustic literature exists [V-7] | Low and speculative; coil-whine correlation is a comfort metric, never safety |
| Thermal imaging, distributed temperature | Spatial hot-pin localization | Mature in electrical inspection | Moderate; per-connector NTC already captures the actionable signal at far lower cost |
| Fluxgate, Hall DC current sensing | Non-contact per-conductor DC current | Mature, commodity | Moderate; an alternative transducer for galvanic isolation, never a new phenomenon |
| Partial-discharge RF sensing | PD pulses | PD is an insulation phenomenon above roughly 1 kV and does not occur at 12 V; no low-voltage micro-arc RF literature exists [V-7] | Not applicable; flagged explicitly |

### 3.3 Defensible new capabilities, and the flagged non-starters

The literature supports deeper exploitation of Tier A far more than any Tier B sensor.
The three most defensible new capabilities:

1. **High-rate per-pin contact-resistance and voltage-drop trending for 12VHPWR
   imbalance and fretting onset.** Basis: the contact-voltage fluctuation studies [1][2]
   and intermittence-detection methodology [4]. Reachable with existing shunt and INA
   hardware at higher effective sampling.
2. **Per-pin energy and charge accumulation as thermal-stress dosimetry.** Basis: the
   thermal-runaway loop in the connector aging literature [27, T4 framing over T1
   mechanisms in companion docs]; INA228-class registers already on platform [20].
3. **Per-connector NTC thermal trending with hot-pin alerting.** Basis: the documented
   localized-heating-precedes-failure pattern in the 12VHPWR field history [15][30, T4
   corroboration only].

Flagged as plausible-sounding and unsupported: counting individual micro-arc events as a
health metric (no validated method, no event-rate data) [V-3]; HF or Rogowski arc
detection at 12 V (contradicted by the Sandia null) [12]; acoustic micro-arc detection at
low voltage (no literature) [V-7]; RF partial-discharge sensing at 12 V (physically
inapplicable) [V-7].

---

## Verification Register

| ID | Claim needing primary-source confirmation | Current basis | Action |
|---|---|---|---|
| V-1 | Vmin/Imin for tin and copper specifically (the 12 to 16 V framing) | Noble-metal cluster in Ney Table 1-3 [16] plus secondary sources | Acquire Slade, Electrical Contacts (2014) ch. 9 or Holm (1967); upgrade the entry on confirmation |
| V-2 | PC-case connector micro-slip amplitude and vibration spectrum | Transferred from automotive and tribology analogues [3][9][10][26] | Bench: instrumented thermal-cycle micro-motion measurement, or accept the analogy with the flag permanent |
| V-3 | Micro-arc event rates and any envelope-detection method for PC connectors | No literature exists | Bench-only; variance-envelope proxy requires instrumented teardown validation before any claim |
| V-4 | Representative VRM switching-frequency range citations (250 to 600 kHz mainstream, to about 1 MHz) | Controller-class common knowledge, uncited in the run | Pin two or three representative controller datasheets at vendoring |
| V-5 | ATX 3.1 hold-up relaxation (12 ms full load) | Vendor knowledge base [21, T4] | Verify against the Intel design guide revision text |
| V-6 | Transfer of the Sandia 100 kHz to 5 MHz null from PV voltages to 12 V | [12], PV system, hundreds of volts | Follow-up dive R-1: any 12 to 48 V DC arc spectral characterization (automotive 42 V PowerNet era, telecom 48 V, aerospace 28 V) |
| V-7 | Absence of low-voltage acoustic and RF micro-arc detection literature | Negative search result | Standing flag; revisit only if such literature emerges |
| V-8 | Sandia 2011 report authorship | This run attributes Strauch, Kuszmaul, Bower; the companion arc-signatures document attributes Johnson, Pahl, Luebke et al., SAND2011-3871C | Reconcile the exact report number and author list at vendoring; both may exist as related documents |

## Corpus-entry candidates

1. Fretting-onset slip thresholds (5 to 125 µm regime, partial-slip versus gross-slip
   boundary, normal-force proportionality), A-class pinned to [3][10][11] after V-citation
   completion.
2. Contact-voltage degradation staircase (under 20 mV clean, hundreds of mV fritting, 100
   to 3500 mΩ late-stage fluctuation), A-class pinned to [1][2][7].
3. Showering-arc preconditions (inductive circuit, contact opening) and their absence in
   steady-state 12 V harnesses, A-class pinned to [5][6].
4. Micro-arc regime parameters (5 to 100 ns, limiting current below 100 mA), pinned to
   [16] with the V-1 upgrade path.
5. Per-connector risk ranking with the commoned-pin collapse mechanism, H/decision citing
   this document, [15][17][18][19].
6. The sampling flattening verdict (1 to 2 MS/s telemetry ceiling, three converging
   limits), H/decision citing this document, [12][16][20], with V-6 as its falsification
   hook.
7. The aliasing rule (aliased energy serves amplitude trending, never frequency claims),
   H/decision, this document.
8. Tier A capability table rows as judge-context entries; Tier B non-starters as
   negative-scope entries so future sessions do not re-litigate them.
9. CPSC field-rate prior (1.07 percent, one adapter line, scope-limited), pinned to [15].

## Follow-up research register

| ID | Question | Type | Priority |
|---|---|---|---|
| R-1 | Low-voltage (12 to 48 V) DC arc spectral characterization: does any automotive 42 V, telecom 48 V, or aerospace 28 V measurement contradict the 100 kHz to 5 MHz null at PC-class voltages? | Deep research | High; the falsification path for the Max fast-chain de-scope |
| R-2 | Slade (2014) ch. 9 / Holm (1967) acquisition and Cu/Sn Vmin/Imin verification | Source acquisition (the IPC-2152 pattern) | High, cheap |
| R-3 | Field failure-rate priors per connector class from CPSC and RMA-adjacent records, feeding OQ-40 outcome-label priors and product claims | Mini-dive | Medium |
| R-4 | Thermal-cycling micro-slip transfer model for the 12VHPWR harness geometry (CTE-driven slip estimate against the [3][10] thresholds) | Derivation plus modeling | Medium, optional |
| R-5 | EIA-364-87 nanosecond-discontinuity methodology pull, as input to the bench rig that would validate the variance-envelope proxy (V-3) | Standards desk task | Medium, bench-coupled |

## References

**Tier 1, peer-reviewed and archival**
[1] Ben Jemaa, N., Carvou, E. "Electrical contact behaviour of power connector during
fretting vibration." Proc. 52nd IEEE Holm Conference on Electrical Contacts, 2006.
[2] Carvou, E., Ben Jemaa, N. "Statistical Study of Voltage Fluctuations in Power
Connectors During Fretting Vibration." IEEE Transactions on Components and Packaging
Technologies 32(2), 2009.
[3] Park, Y.W., Sankara Narayanan, T.S.N., Lee, K.Y. "Fretting corrosion of tin-plated
contacts." Tribology International 41(7), 2008, pp. 616-628.
[4] Murrell, S., McCarthy, S.L. "Intermittence Detection in Fretting Corrosion Studies."
Proc. 43rd IEEE Holm Conference on Electrical Contacts, 1997.
[5] Curtis, A.M. "Contact Phenomena in Telephone Switching Circuits." Bell System
Technical Journal 19(1), 1940.
[6] Atalla, M.M. "Arcing of Electrical Contacts in Telephone Switching Circuits, Part I:
Theory of the Initiation of the Short Arc." Bell System Technical Journal 32, 1953;
Parts II and III, 1954-1955.
[7] "The influence of current load on fretting of electrical contacts." Wear, 2008.
VERIFY author list at vendoring.
[8] Yap, F.F., et al. "Design and analysis of vibration isolation systems for hard disk
drives." Journal of Magnetism and Magnetic Materials 303, 2006.
[9] Tin-plated brass elevated-temperature fretting study, 298 to 373 K, 0.85 N.
Materials/Wear, 2016-2017. VERIFY full citation (V-register).
[10] Normal-force-proportional threshold-amplitude study, 2017. VERIFY full citation.
[11] "Fretting in Electrical/Electronic Connections: A Review." IEICE Transactions on
Electronics E92-C, 2009.

**Tier 2, standards and national laboratory**
[12] Sandia National Laboratories. "Photovoltaic DC Arc Fault Detector Testing at Sandia
National Laboratories," 2011 (10 MHz capture; no arc-versus-baseline separation 100 kHz
to 5 MHz; detection recommended below 100 kHz). Authorship reconciliation per V-8.
[13] EIA-364-28 (vibration testing) and EIA-364-87 (nanosecond event detection),
Electronic Components Industry Association.
[14] SAE/USCAR-2, revision 8: Performance Specification for Automotive Electrical
Connector Systems.
[15] U.S. Consumer Product Safety Commission. Recall of CableMod 12VHPWR angled adapters,
February 2024: 272 incident reports across approximately 25,300 units.

**Tier 3, manufacturer and interface authority**
[16] Pitney, K.E. Ney Contact Manual. Deringer-Ney, reprint edition 2022. Section
1.9.2.3 and Table 1-3, citing Holm (1967), Ben Jemaa (1984, 2002), Hasegawa (2005).
[17] Intel. ATX 3.0 Multi-Rail Desktop Platform Power Supply Design Guide, doc 336521,
rev 2.1 (2023): 9.2 A per pin at 30 °C rise; power-excursion classes; ripple limits;
hold-up.
[18] Molex. Mini-Fit Jr product specification PS-87427 class documents: 0.49 N minimum
normal force, 30 mating cycles, 10 mΩ contact resistance, vibration discontinuity limit
1 µs.
[19] Molex. Micro-Fit 3.0 product specification: 3.00 mm pitch, 375 gf maximum normal
force per contact.
[20] Texas Instruments. INA240 datasheet (400 kHz bandwidth at minus 3 dB); INA228
datasheet (energy and charge accumulation registers).
[21] Seasonic knowledge base: ATX 3.1 hold-up revision (12 ms full load, 17 ms at 80
percent). T4-adjacent vendor documentation; verify per V-5.

**Tier 4, corroboration only, never load-bearing**
[23] 45Drives blog, "Everything you Need to Know about Hard Drive Vibration" (90/120 Hz
tonal figures). Accessed 2026-06-11.
[24] US Patent 7,481,116, fan-vibration measurement (torque-ripple band above 300 to 500
Hz).
[25] US Patent 8,000,839, active vibration cancellation in computer systems (fan
fundamental and harmonics).
[26] Smiths Interconnect white paper, "Understanding Fretting Corrosion in Ruggedized
Backplane Connectors," 2025.
[27] Patsnap Eureka, "High-Voltage Connector Thermal Rise: Contact Resistance, Aging,
and Safety Margins." Accessed 2026-06-11.
[29] Wikipedia, "12VHPWR" (30 to 40 mating-cycle framing; consistent with [18]).
[30] der8auer, Gamers Nexus, Tom's Hardware, Cybenetics: 12VHPWR field-failure narrative
and PSU ripple test practice. Corroboration only.
[31] PCI-SIG CEM 5.0 (10 ms 2x average-power window), paywalled; carried via [17].
Derivation-class.
