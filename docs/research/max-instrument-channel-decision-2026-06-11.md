# Max Instrument Channel: Decision Rationale and Wideband Front-End Engineering

**Status:** research-grade plus a recorded owner ruling. Feeds corpus entries and OQ
dispositions; spec edits ride the normal owner-pen channel, never this document.
**Date:** 2026-06-11
**Provenance:** the above-100-kHz instrument-value dive (2026-06-11) plus the owner
ratification session of the same date. Companion documents:
`docs/research/connector-microarcing-and-sampling-value-2026-06-11.md` (the sampling
value curve and follow-up register this closes against),
`docs/research/dc-series-arc-signatures-2026-06-11.md`,
`docs/research/low-voltage-arc-spectra-r1-2026-06-11.md` (the R-1 falsification dive),
`docs/research/gpu-12vhpwr-fault-phenomenology-2026-06-10.md`.
**Gates fed:** OQ-15 (Max positioning), OQ-17 (fast-capture chain), OQ-18 (HF sense
element), OQ-19 (compute and memory), the Max power architecture, and the bench
protocol register.

## Citation convention

Same as the series. T1 peer-reviewed or archival conference; T2 standards body,
national laboratory, or government record; T3 manufacturer datasheet, official design
guide, or interface specification; T4 enthusiast, trade press, or third-party-lab
material, corroboration and market-demand evidence only, always marked. Claims not yet
pinned to a primary source carry VERIFY flags into the Verification Register.

---

## 1. The instrument-value verdict this ruling rests on

The hail-mary dive asked whether anything electrically measurable above 100 kHz on PC
power rails carries instrument value with no failure-prevention story. Its findings,
condensed with their citations:

1. **One validated, observable, market-demanded use case survives above 1 to 2 MS/s:
   spec-faithful ATX ripple and noise measurement.** The Intel ATX design guide defines
   output ripple and noise over 10 Hz to 20 MHz, measured with a 20 MHz bandwidth
   oscilloscope, outputs bypassed at the connector with a 0.1 µF ceramic and a 10 µF
   electrolytic, with pass limits of 120 mV p-p on 12 V rails and 50 mV on 5 V, 3.3 V,
   and 5VSB [I-1, T2/T3]. Every PSU certification lab and reviewer measures exactly
   this today with bench scopes and electronic loads [I-7, T4].
2. **Load-transient edge and slew characterization is real, unserved, and observable at
   the connector**, and it lives below a few MS/s: the ATX excursion classes and the
   stated 5 A/µs twelve-volt slew bound imply edge content to roughly 350 kHz for a
   1 µs edge by the 0.35/t_r rule [I-1][I-2, T2/T3]. Published GPU dI/dt at the
   connector does not exist; the gap is documented across this series.
3. **The most novel candidate, connector-side VRM phase fingerprinting, failed the
   observability gate as measured fact and remains an unmeasured cell as physics.**
   Per-phase GPU VRM switching sits at 250 kHz to 1.2 MHz [I-3, T3]; interleaving and
   the on-board input capacitor bank are designed to confine that ripple to the board
   [I-4, T3/T4]; and no published measurement of residual switching ripple on a PC 12 V
   harness exists in any tier [documented absence]. One counter-prior is recorded
   honestly: automotive CISPR 25 requires conducted-emission limits on 12 V DC lines
   from 150 kHz to 108 MHz precisely because switching loads emit onto supply harnesses
   unless deliberately filtered to a standard [I-5, T2], and PC GPUs face no such
   requirement on their power input. The cell is therefore unmeasured rather than
   closed.
4. **The market comparable proves the instrument framing sells and reveals the gap.**
   The ElmorLabs PMD2 at 99 USD sells per-connector power logging to reviewers and
   enthusiasts with a scope mode that is in truth a slow logger, kHz-class effective
   [I-6, T4]. Nobody sells true wideband in-harness capture. The bench alternative is
   a several-hundred-euro scope plus a current probe plus a load [I-7, T4].
5. **Nothing in any dive supports six per-pin fast channels.** The surviving use cases
   are rail-level voltage phenomena and one current transient path. One shared
   wideband voltage-plus-current channel, switchable across connectors, covers
   everything that survives.

## 2. Owner ruling and rationale (recorded 2026-06-11)

**Ruling:** the Max tier builds research-grade capture capability. One shared wideband
instrument channel, voltage plus current, 20 MHz-class analog bandwidth, fast-ADC
sampled. The six-channel per-pin fast array is dead. Per-pin sensing stays at
telemetry rates and remains the dV/dI and imbalance domain. Capability ships;
unvalidated claims do not.

**The epistemic basis, stated precisely so the ruling cannot drift.** "No literature
means untested, not wrong" is true cell by cell, never wholesale. Two kinds of unknown
exist in this series and they license different things. Constrained unknowns are cells
bounded by adjacent measurements and physics: the 12 to 14 V arc spectrum is unmeasured,
and every measured neighbor from 28 V to PV voltages clusters below 100 kHz with
contact physics pointing the same direction, so the expectation is set even where the
cell is empty. Genuinely unmeasured unknowns are cells nobody has looked at: residual
VRM switching content on a PC harness has no measurement in any tier, the physics
argument against it is a prior rather than a verdict, and the CISPR 25 counter-prior
keeps it live. The ruling builds capability for the second kind without claiming
results in either kind.

**The engineering basis: the Max is the instrument that closes its own open
questions.** Every dive in this series ended by demanding a measurement that does not
exist: the R-1 verdict wants 10 to 20 MS/s capture of 12 V micro-arc events; the
instrument dive wants a wideband probe on a real GPU harness to settle the VRM-residue
cell; the dI/dt gap wants exactly this chain. A Max carrying research-grade capture is
its own bench rig, and first articles run the characterization protocols the research
demanded. Both outcomes convert to value: content found above the known bands unlocks
features in firmware on hardware already in the field, and content absent becomes
CEC-published nulls for cells the literature never filled, citable in the corpus and
in marketing. This is the actuation-into-physical-reality-and-back loop the pipeline
philosophy has been missing, expressed in silicon, and it is coherent with the
made-on-quality BOM ruling: instrument-grade headroom is the same product identity.

**Three binding conditions ride the ruling.**

1. **Channel configuration: one, never six.** The evidence re-points the fast path
   rather than deleting it. The validated instrument case wants more rate on one
   voltage channel than the original array offered per channel; nothing wants per-pin
   HF. OQ-17's one-versus-six question is answered: one shared wideband channel.
2. **Honest cost accounting, including software.** The capability forces the FPGA, the
   capture RAM, the wideband tap, and the 5VSB power fight; capability without the
   firmware and analysis software to use it is dead silicon. The analysis software is
   budgeted as part of the channel or the channel is not built.
3. **Claims discipline per the cluster-5 statement-form rules.** Untested cuts both
   ways: hardware may be capable of a band while the product claims only validated
   results in it. Judge tiers assert nothing above the validated bands until CEC bench
   data exists. The marketing failure mode this kills was already buried once with arc
   detection; it stays buried.

## 3. Front-end engineering: collecting the sample past the inductive corner

The owner question: do we just need a better shunt, and how do we get past the
inductive corner? The short answer is that no purchasable shunt escapes the corner at
this resistance value, the corner is escaped by compensation, deconvolution, or a
different sensor class, and a better-characterized shunt makes the escape clean.

### 3.1 Why shunt shopping cannot solve it

The corner sits at f_c = R / (2 pi L). At 1 mΩ and 2 nH that is 79.6 kHz, the figure
carried throughout this series. For a resistive shunt to stay flat to 20 MHz at 1 mΩ,
the ESL would need to satisfy L = R / (2 pi f) = 1e-3 / (2 pi times 2e7), which is
approximately 8 picohenries. That is two to three orders of magnitude below any
discrete current-sense part; the Bourns CSS2H-2512 class is specified below 2 nH and
reverse-geometry parts reach the few-hundred-picohenry range at best [F-1, T3,
VERIFY exact reverse-geometry ESL figures at part selection]. A lower-ESL geometry
(reverse 0612, wide-terminal metal strip, tight Kelvin loop layout) moves the corner
from 80 kHz toward 300 kHz to 1 MHz, which is worth having because it improves the
accuracy of every method below, and it never reaches the band alone. The corner is a
calibration problem and a sensor-architecture problem, never a procurement problem.

One reframe matters before the methods: above the corner the shunt has not stopped
working, it has changed jobs. Its voltage becomes V = L dI/dt plus the resistive term,
meaning it is a di/dt sensor with a known, fixed, measurable transfer function
Z(f) = R + j 2 pi f L. Everything below exploits that rather than fighting it.

### 3.2 Route A: digital deconvolution of the existing shunt (zero added series parts)

Capture the raw shunt voltage through a wideband low-noise differential amplifier into
the fast ADC, then divide by the known Z(f) in the FPGA (a fixed one-pole equalizer:
multiply by 1 / (R + j omega L), implementable as a first-order IIR shelf). Per-unit
calibration extracts the actual R and L at bring-up: drive a known current step or
swept stimulus through the lane, fit the response, store both constants in the cal
record alongside SHUNT_CAL. The inductive rise is an SNR gift at high frequency
(12.6 mΩ per amp at 1 MHz versus 1 mΩ at DC), so sensitivity improves exactly where
the resistive signal would have starved; the noise-limited region is the low end,
where the existing INA240 telemetry path already owns the measurement. Requirements:
a wideband front-end amplifier (the INA240's 400 kHz bandwidth retires on this path; a
high-GBW fully-differential or instrumentation-grade video-class amplifier replaces
it, selection is an OQ), AC coupling so the 9 to 55 A DC pedestal does not consume
ADC range (the arc-signatures dive already established AC-coupled 14 to 16 bit
practice for exactly this reason), and stability of L over temperature and life,
which is unverified and flagged [V-3]. Cost: amplifier plus passives, board area
nil, firmware equalizer trivial against the FPGA already present.

### 3.3 Route B: analog pole-zero compensation (the classic fix)

Place an RC network across the shunt sense pair such that R_c times C_c equals L over
R, the shunt's own time constant, which at 2 nH over 1 mΩ is 2.0 µs (for example
2.0 kΩ and 1 nF). The network's pole cancels the shunt's ESL zero and the amplifier
sees a flattened response, the standard practice in wideband and hot-swap current
sensing [F-2, T3, VERIFY: pin the canonical TI and Analog Devices application notes on
shunt parasitic-inductance compensation at vendoring; the technique is textbook, the
citation should be exact]. The weakness is the match: the datasheet gives a bound
(below 2 nH), never a value, and layout contributes loop inductance the part number
never sees, so the network is tuned per design and ideally verified per unit, and
residual error grows with the mismatch as frequency rises. Route B typically buys one
to two clean decades past the corner, which covers the transient-slew use case
comfortably and runs out before 20 MHz. It pairs naturally with Route A: compensate
coarsely in analog, equalize the residue digitally.

### 3.4 Route C: PCB Rogowski di/dt pickup, blended with the shunt path

An air-core PCB-embedded Rogowski loop coupled to the lane carries no DC, never
saturates, costs board traces, and outputs M dI/dt with a mutual inductance set by
geometry, restored to current by an integrator (active analog or digital in the
FPGA). Published power-electronics practice uses PCB-embedded Rogowski coils for
switching-current measurement at multi-MHz bandwidth [F-3, T1, VERIFY: pin two or
three archival PCB-Rogowski papers at vendoring; the field is established, the exact
citations are not yet in this repository]. The instrument current path then becomes a
crossover pair: shunt plus INA240 owns DC to roughly 50 kHz, the Rogowski-integrator
path owns roughly 10 kHz to 20 MHz and beyond, and complementary filters in the FPGA
blend them, tied together by the same injected-step calibration as Route A. This is
also the formal closure of OQ-18's dedicated low-inductance element or separate di/dt
pickup clause: the answer is yes for the one instrument channel, and the element is a
coil, never a second shunt.

### 3.5 Rejected for this board: inline CT and Hall hybrids

The commercial wideband current-probe architecture (Hall or fluxgate for DC plus CT
for AC) is the right answer for a clamp instrument and the wrong one inline: a CT on
a 55 A DC lane needs a gapped core sized for the bias, the Hall path duplicates what
the shunt already does better, and both add magnetics, mass, and cost the board does
not want. Recorded as considered and rejected, so future sessions do not re-litigate.

### 3.6 The voltage channel is the easy half, with one method note

The validated use case (ATX ripple) is a voltage measurement and never meets the
inductive corner: an AC-coupled divider into a wideband FET-input buffer to 20 MHz
serves it directly. One method-fidelity note for the claims discipline: the ATX
measurement convention bypasses the output at the connector with a 0.1 µF ceramic and
a 10 µF electrolytic as part of the defined method [I-1, T2/T3]. An in-system
instrument either lands footprints for that pair at its measurement point or documents
the deviation and names its figure measured-per-CEC-method rather than
ATX-method-faithful. The spec wording entry carries whichever is chosen.

### 3.7 Recommended architecture and the ADC decision

Recommended: Route A plus Route C on the single instrument current path (deconvolved
shunt for the low and mid band and calibration anchor, PCB Rogowski for the top band,
blended digitally), Route B as the fallback if the wideband amplifier or the coil
underperforms, and the AC-coupled divider voltage path alongside. Two ADC options go
to the owner with the tradeoff stated plainly:

- **A1, spec-faithful:** a single dual-channel ADC at 50 to 65 MS/s class, 12 to 14
  bit, sampling V and I simultaneously. Honors the full 10 Hz to 20 MHz ATX band.
- **A2, carry the existing proposal at reduced scope:** one ADC342x-class dual channel
  at 25 MS/s, Nyquist 12.5 MHz. Covers all transient content, the dominant ripple
  fundamentals and harmonics, and most spike energy, and cannot claim full ATX-method
  bandwidth; the deviation is documented and the ripple figure is named accordingly.

Either option is one ADC, never four; the quad array is retired in both. PSRAM and
capture-depth sizing under OQ-19 re-derives from the chosen rate times two channels,
which at A2 is roughly half the originally budgeted sustained capture rate.

## 4. Bench protocol additions

1. **Per-unit Z(f) extraction:** a known current step (a MOSFET-switched resistive
   step-load jig, cheap to build, no precision required because the board measures its
   own step) fitted in firmware to extract R and L per instrument lane at bring-up;
   constants stored with the cal record. This jig also serves the drift benchmark's
   load-step profile, one build, two protocols.
2. **The VRM-residue measurement (closes the unmeasured cell from section 1.3):**
   first-article Max on a real GPU harness under gaming and synthetic load, capture
   the full band, publish the spectrum either way. Decision threshold carried from
   the instrument dive: a clean N-times-f_sw line or residue above roughly one percent
   of DC reopens the fingerprinting question; absence is the published null.
3. **The R-1 12 V micro-arc characterization:** the degraded-connector rig from the
   R-1 dive, captured at the instrument channel's full rate, real connector
   metallurgy, 1 to 9 A. First articles run it as both product validation and the
   novel datapoint the literature lacks.

## 5. OQ dispositions recorded by this document

- **OQ-17:** one shared wideband V plus I instrument channel; ADC option A1 or A2 per
  owner choice; six-channel fast array retired. Sequencing note satisfied: the band
  decision no longer waits on bench arcs, because the arc justification is closed and
  the instrument justification stands on its own.
- **OQ-18:** the 1 mΩ shunt alone is insufficient above its corner by two to three
  orders of magnitude against the band; resolved by deconvolution plus a PCB Rogowski
  di/dt element on the single instrument channel; per-pin lanes unaffected.
- **OQ-15 input:** the Max positions as the instrument-grade flagship; the capture
  chain's justification is instrument value plus self-characterization, never arc
  detection; power and BOM consequences re-derive from the one-channel architecture.
- **OQ-19 input:** capture-rate and PSRAM sizing re-derive from one dual-channel ADC
  at the chosen rate.

## 6. Corpus-entry candidates

1. The inductive-corner law and the 8 pH impossibility result (param plus rule,
   derivation from F-1 and the arithmetic in 3.1).
2. The shunt-as-di/dt-sensor reframe with Z(f) = R + j omega L as the equalization
   target (rule, this document).
3. Route B's pole-zero relation R_c C_c = L/R with the per-design tuning caveat
   (rule, VERIFY app-note pin).
4. The one-channel ruling and the six-channel retirement (H/decision, this document,
   citing the instrument dive).
5. The claims-discipline clause binding capability to validated bands (H/decision,
   joins the cluster-5 statement-form family).
6. The ATX bypass-method fidelity rule for any published ripple figure (rule, I-1).
7. The considered-and-rejected record for inline CT and Hall (negative-scope entry).

## 7. Verification Register

| ID | Claim needing confirmation | Current basis | Action |
|---|---|---|---|
| V-1 | Reverse-geometry and wide-terminal shunt ESL figures (few hundred pH class) | Vendor characterization practice, unpinned | Pin datasheet values at part selection |
| V-2 | Canonical pole-zero compensation references | Textbook practice, T3 app-note class | Pin exact TI and ADI app notes at vendoring |
| V-3 | CSS2H ESL stability over temperature and life | Unverified; datasheet gives a bound only | Per-unit extraction at bring-up plus a drift check riding the shunt benchmark |
| V-4 | PCB Rogowski archival citations and achievable M tolerance | Established field, citations not yet in repo | Pin two or three T1 papers; prototype coil M calibration on first article |
| V-5 | Wideband amplifier selection (noise floor against 1 mΩ signals to 20 MHz) | Open engineering choice | OQ at Max schematic time |
| V-6 | ADC option A1 part landscape at 50 to 65 MS/s dual-channel | Open | Survey at Max schematic time |

## References

**Instrument-dive sources carried forward (numbering local to this document)**
[I-1] Intel, ATX 3.0 / ATX12VO Desktop Platform Power Supply Design Guide: output
ripple and noise definition (10 Hz to 20 MHz, 20 MHz oscilloscope, 0.1 µF plus 10 µF
connector bypass), per-rail limits, transient excursion classes, 5 A/µs slew bound.
T2/T3.
[I-2] Rise-time-to-bandwidth relation BW approximately 0.35 / t_r, standard
measurement practice. T3/T4 class; uncontroversial.
[I-3] onsemi NCP81610 multiphase controller datasheet: 250 kHz to 1.2 MHz per-phase
switching, eight-phase GPU class. T3.
[I-4] Multiphase input-capacitor ripple cancellation and input-filter attenuation
practice (EDN; passive-components.eu; vendor app notes). T3/T4.
[I-5] CISPR 25:2021 Ed. 5, conducted emissions on 12 V DC lines, 150 kHz to 108 MHz,
5 µH LISN method. T2.
[I-6] ElmorLabs PMD2 product documentation and forum ADC disclosures; PowerSensor3,
arXiv:2504.17883 (2025) for measured PMD sampling limits. T4 and T1 respectively.
[I-7] Reviewer and lab methodology: Cybenetics protocol, Tom's Hardware and igorsLAB
rigs, Rigol DHO800-class pricing. T4, market-demand evidence.

**Front-end sources**
[F-1] Bourns CSS2H-2512 datasheet (ESL below 2 nH bound); reverse-geometry
current-sense part class. T3; V-1 pins exact figures.
[F-2] Shunt parasitic-inductance pole-zero compensation, TI and Analog Devices
application-note class. T3; V-2 pins exact documents.
[F-3] PCB-embedded Rogowski coil switching-current measurement literature. T1 field;
V-4 pins exact papers.

**Documented absences inherited from the series**
No published VRM switching residue measurement on a PC 12 V harness; no published GPU
dI/dt at the connector; no 12 to 14 V DC arc spectral characterization. All three are
first-article measurement targets under section 4.
