# Thermal/Electrical Gate Constants for the CEC PCB Design-Rule Corpus: Derivation and Sourcing

## TL;DR
- All five gates are physically defensible, but three are mis-typed: **dT_max (30°C)** and **T_max (105°C)** should be **KEPT** but re-expressed as a coherent triple (ambient + rise ≤ ceiling); the **100 A/mm²** density gate must be **SPLIT by geometry class** (via barrel vs external vs internal trace); and the **400 A/mm²** fusing gate must be **CONVERTED to a (J, t) curve**, because a flat A/mm² fusing number is meaningless without a time base — Onderdonk shows 400 A/mm² is the copper melting density for a **≈0.5 second** adiabatic pulse.
- Every chart-class number traces to the paywalled IPC-2152/IPC-2221; we cite public derivations (Jouppi/Olson tutorials, Brooks/Adam UltraCAD papers, smps.us interpolation, Saturn/Sierra/AtlasPCB calculator docs) and mark each "verify against IPC-2152." The key coherence finding: at a conservative PC-case design ambient of 50°C, a 30°C copper rise puts copper at 80°C, comfortably under the 105°C ceiling — and that ceiling is correctly set by the **lowest-rated BOM part (the 105°C aluminum electrolytic capacitor)**, not by FR-4.
- Platform protection (PSU OCP, TPS2121 current limit) clears faults in milliseconds to ~500 ms, far faster than the copper fusing time at any realistic operating density (operating density is ~5–12× below the fusing density even at the slowest 500 ms window). So the fusing gate is a forensic/worst-case backstop, not primary protection; the **+20°C transient allowance** is the thing that must actually survive real fault durations and needs a time constant attached.

## Key Findings

1. **dT_max = 30°C is a temperature-RISE limit, not an absolute temperature.** Final copper temperature = local board temperature (case ambient + neighbor/plane/component heating) + rise. IPC-2152 publishes current-capacity curves at discrete rise points; public sources confirm these are 10°C, 20°C, 30°C and up to 100°C. A 30°C rise is the upper end of "general-purpose" and is coherent with the 105°C ceiling given a researched PC-case ambient.
2. **T_max = 105°C is correctly derived as "minimum BOM rating minus margin," and the floor part is the 105°C aluminum electrolytic capacitor — not FR-4.** Standard FR-4 (Tg 130–140°C, ~110°C continuous) and the Schottky diodes (125°C junction) sit above it; the 105°C cap and the connector housing operating rating are the binding constraints.
3. **The +20°C transient allowance has no meaning without a time constant.** PCB trace thermal time constants run from ~1 s (fine traces) to ~100 s (a full PCB in a PC). Platform protection trips in ms to ~500 ms — generally well inside the trace thermal time constant — so the +20°C bucket survives most fault classes, but each transient class needs its own (ΔT, τ) pair.
4. **A single flat 100 A/mm² density gate is physically wrong because density limits are scale-dependent** (small conductors shed heat better per unit volume/perimeter). It must be split into via barrel (~75 A/mm² at 10°C rise from the in-hand analysis), external trace, and internal trace, each carrying a different allowable density at a chosen rise.
5. **Onderdonk's adiabatic relation makes 400 A/mm² a single point on a J–t curve: ~400 A/mm² is the copper melting density for a ≈0.5 s pulse from a 20°C start.** It rises to ~900 A/mm² at 100 ms and ~2,900 A/mm² at 10 ms, and falls to ~130 A/mm² at 5 s. Valid only for pulses under ~1 s (conservative to ~10 s) — the adiabatic window.

## Details

### Constant 1 — dT_max = 30°C steady-state copper rise

**What the public IPC-2152 material actually shows.** IPC-2152 (2009) presents current capacity as families of curves at discrete temperature-rise values. Public sources confirm the published rise points are 10°C, 20°C, 30°C and upward to 100°C: AtlasPCB's IPC-2152 guide states "IPC-2152 specifies current capacity for a given temperature rise above ambient (typically 10°C, 20°C, or 30°C rise)," and PCBSync notes "IPC-2152 provides data for temperature rises from 10°C to 100°C, but most designs target 10-20°C rise." The Saturn PCB Toolkit help text confirms the standard has "two separate charts for finding conductor (or via) current vs. temperature rise" — a "conservative" chart (which is actually the old IPC-2221 internal-trace curve) and a "universal" chart (IPC-2152 Figure 5-2, 3 oz copper on 0.070" polyimide). Jack Olson's public IPC-2152 tutorial confirms the standard deliberately uses the term **"local board temperature"** rather than ambient: "the temperature rise of the trace is going to be higher than all of the contributing factors combined… ambient temperature plus all of the other heat sources of nearby components and traces."

**Relationship.** Final copper temperature = local board temperature + ΔT_rise, where local board temperature = case ambient + heating from neighbors/planes/components. This is the critical correction: the 30°C is added on top of an already-elevated local board temperature, not on top of room ambient.

**PC-case internal ambient (researched).** Public enthusiast measurements cluster around 27–39°C internal air under load with good airflow: a Tom's Hardware forum measurement reported ~33°C typical, "as hot as 39°C under load" with ~27°C room ambient; an Overclockers forum user measured 27–30°C internal during 2K/165 Hz gaming. These are well-ventilated cases. A conservative design ambient for a power-telemetry board mounted near high-current paths and PSU heat should use the upper end. **Recommended design ambient: 50°C** to cover hot rooms (30–35°C), poor airflow, and local board heating — consistent with the task's 35–50°C bracket. PCBSync's IPC-2152 guide makes the principle explicit: "Never forget that trace temperature equals ambient plus rise—a 20°C rise in a 60°C enclosure puts your trace at 80°C."

**Coherence check.** Local ambient 50°C + 30°C rise = 80°C copper — below the 105°C ceiling with 25°C of headroom, and below standard FR-4's continuous limit. Even an aggressive 50°C ambient + 30°C rise + 20°C transient = 100°C, still under 105°C. The gate is coherent. If the design ambient were pushed to 55°C, steady-state 30°C rise reaches 85°C and the transient touches 105°C — that is the threshold at which the rise budget should be cut to 20°C.

**Conservatism direction.** Public sources uniformly state IPC-2221 charts are MORE conservative than IPC-2152 measured data. PCBSync, verbatim: "The IPC-2221 internal conductor chart was created by simply halving the current values from the external chart—an assumption with no empirical backing. IPC-2152 demonstrated that internal traces can carry current levels much closer to external traces than previously believed." IPC-2152 generally permits narrower traces / predicts lower temperatures, and studies comparing IPC-2152 predictions to measurements show it tends to overestimate required width by 10–20% (built-in conservatism). **Therefore a gate built on IPC-2221-style numbers errs safe.** *(Derivation-class: exact chart points are paywalled — verify against IPC-2152 Figure 5-2 when a copy is acquired.)*

**Recommended documented operating point:** ΔT_rise = 30°C maximum on copper; design local-board ambient = 50°C; resulting maximum copper temperature = 80°C steady-state, 100°C with the +20°C transient. For internal layers, RayPCB's IPC-2152 guidance states "internal traces typically require 20-30% more width than external traces for the same current capacity" (AtlasPCB phrases it as "carry 50–70% of external trace current for the same temperature rise"); note IPC-2152 found internal traces run nearer free-air behavior, so the old "halve it" rule is too harsh.

### Constant 2 — T_max = 105°C absolute ceiling

**Derivation rule:** T_max(board) = min over BOM of {component rated max temperature} − margin. Floor values from public datasheets:

| Component | Public rating | Source | Notes |
|---|---|---|---|
| 105°C aluminum electrolytic cap | Category temp −25 to +105°C; **load life 2,000 h at 105°C** (Nichicon GL series); spec "met when D.C. bias plus rated ripple current is applied for 2000 hours at 105°C" | Nichicon GL datasheet (e-gl.pdf) | **Floor part.** Arrhenius "10°C rule" (life doubles per 10°C drop): at 80°C, life ≈ 2000 × 2^((105−80)/10) ≈ 11,300 h; at 95°C only ~4,000 h |
| Molex Mini-Fit Jr / Mini-Fit family connector | 105°C operating (solid-brass/phos-bronze terminals); rating "includes 30°C terminal temperature rise at maximum rated current" | Molex PS-5556-004, PS-45750-001 | Formed-brass terminal variant only −40 to +80°C; current rating is at 30°C T-rise over ambient |
| 12VHPWR / 12V-2×6 power pins | "Minimum 9.2 A per pin/position with a limit of 30 °C T-rise above ambient temperature conditions at 12 V dc with all twelve contacts activated" | Intel ATX 3.0 design guide / PCIe CEM 5.1 (via igorslab.de) | The 30°C connector T-rise is a hard spec limit; mirrors the trace 30°C rise gate. Total assembly ≤ 55 A; ≤6 mΩ LLCR/contact |
| SS14 Schottky | TJ −65 to +125°C | onsemi / Vishay SS14 datasheets | Above the cap |
| SB120 Schottky | TJ +125°C (Vishay 88715, onsemi/Fairchild Rev. C); +150°C (Diodes Inc DS23022, Diotec) — **conflict** | manufacturer datasheets | Above the cap regardless of which value |
| Standard FR-4 | Tg 130–140°C; continuous MOT historically 130°C (UL/ANSI), now up to 150°C with LTTA data | I-Connect007 (Shengyi); multiple fab sources | Design rule: continuous op temp ≥ 20–25°C below Tg → ~110°C for Tg 130 |
| Nylon (PA66) connector housing | UL94V-0 thermoplastic; rating tied to connector temp spec | Molex/Amphenol specs | Bounded by connector 105°C / 30°C-rise spec |

**Finding:** The 105°C ceiling is set by the **105°C electrolytic capacitor**, matched by the connector housing operating rating. FR-4 (~110°C continuous for Tg 130) is slightly above; the Schottkys (125°C) and standard logic are well above. So **105°C is the correct min-of-BOM value, with effectively zero explicit margin against the cap and ~5°C against FR-4 continuous.** The real design target should keep steady-state copper and local board temperature comfortably below 105°C (the 80°C operating point gives 25°C margin and keeps cap life in the multi-thousand-hour range).

**Recommendation:** Keep T_max = 105°C, documented as min-of-BOM, with an explicit margin statement: steady-state local board temperature target ≤ 85°C so that even with the +20°C transient the cap's 105°C is not exceeded. If high-Tg FR-4 (170°C) is adopted, the floor remains the capacitor, so 105°C does not move. *(FR-4 continuous-temperature guidance is public; specific UL RTI listings are part-number specific — verify the chosen laminate's UL RTI.)*

### Constant 3 — Transient allowance +20°C with time constant

**Trace/via thermal time constants (public).** Brooks/Adam (UltraCAD, via EDN) note a trace's full-board equilibrium takes "5 to 10 minutes or so," but the trace's own constant is far shorter. A peer-reviewed PC-motherboard analysis (IEEE SEMI-THERM) found "the time constant of a PCB in a typical PC application is in the order of 100 seconds" for the board mass; individual fine traces have constants from ~1 s to ~10 s (Salitronic: "typically milliseconds to seconds depending on geometry"). A first-order RC thermal model applies: ΔT(t) = ΔT_final·(1 − e^(−t/τ)), with τ = R_th·C_th. Vias, being copper cylinders embedded in FR-4, have short constants (sub-second to a few seconds) but poor steady-state dissipation.

**(a) Generic pulse classes.** Because adiabatic heating dominates for pulses ≪ τ, a trace tolerates large transient currents for short windows. For pulses far shorter than τ (~1–10 s for traces), use transient/heat-capacity analysis, not steady-state ampacity. The +20°C transient bucket is appropriate for events in the **0.1 s – few-second** range; sub-100 ms events could tolerate far more than 20°C without damage, while events longer than ~10 s approach steady state and should be governed by the 30°C steady-state gate.

**(b) Platform fault classes (public datasheet/spec values):**

| Fault source | Trip/response time | Source |
|---|---|---|
| TI TPS2121 power mux | Adjustable current limit during startup/switchover; fast-switchover and inrush control; current-limit response in µs–ms range | TI TPS212x datasheet (Rev. F) |
| ATX/EPS PSU OCP | "several tens of milliseconds (or longer)" near threshold; few ms with large overdrive; **EPS12V: 17 A rail trips at ≤25.5 A peak, minimum 500 ms** | Keysight OCP characterization (7 ms at 12 A / 113 ms at 6 A on a 5 A limit); SSI EPS12V Design Guide v2.92 |
| PSU PWR_OK / hold-up | ≥17 ms hold-up; PWR_OK delay 100–500 ms | ATX spec (Tom's Hardware "PSUs 101") |
| PPTC / polyfuse | Thermal device: ~0.7 s at 3 A / ~2 s at 2 A (2016L075); some SMD ~13–20 ms at 50 A; near I_trip can be tens of seconds | Littelfuse, Eaton TN 11055, Circuit Cellar |
| Capacitive inrush | Controlled by mux soft-start; tens of µs to ms | TPS2121 inrush control |

**Mapping.** The slowest mandatory protection is PSU OCP at up to ~500 ms (and "tens of ms or longer" near the threshold). PPTCs can take seconds near I_trip. Both are well inside a trace thermal time constant of 1–100 s, so copper does not reach its steady-state temperature during a fault that protection ultimately clears — but a near-threshold over-current that persists ~500 ms is exactly the case the +20°C transient must cover.

**Recommended (ΔT, τ) pairs per class (derivation-class):**
- **Fast electronic limit (TPS2121, SCP), event < 10 ms** → copper rise negligible; no transient budget needed (the fusing curve governs — see Constant 5).
- **PSU OCP near threshold, 0.1–0.5 s** → assign ΔT_transient = +20°C with τ ≈ 2–5 s (a 0.5 s event then reaches only ~10–25% of ΔT_final).
- **PPTC / sustained marginal overload, 1–10 s** → boundary case; +20°C with τ ≈ 5–10 s, and beyond ~10 s defer to the 30°C steady-state gate.

*(Verify trace-specific τ by thermal simulation or the IPC-2152 transient appendix; bench-measure with a current step on a populated lane.)*

### Constant 4 — J_max = 100 A/mm² current-density gate

**Why a flat A/mm² limit is wrong.** Allowable current density is scale-dependent: heat generation scales with cross-sectional area (volume per unit length) while dissipation scales with surface/perimeter, so a small conductor has a higher surface-to-volume ratio and tolerates higher density. Brooks/Adam demonstrate this directly — narrower traces shed heat better (a wider "thermal plume" relative to width) and reach the fusing temperature later than wider ones at the same density. A single 100 A/mm² number can therefore only be correct for one geometry/rise point.

**Geometry-class values (public, derivation-class):**
- **Via barrel:** barrel area ≈ π × drill × plating. In-hand CEC analysis: 0.3 mm drill, 1 oz plating → ~0.033 mm² barrel, ~2.5 A at 10°C rise → ~75 A/mm². Public via data corroborate the order of magnitude: a 0.3 mm via with ~20 µm plating ≈ 0.8–1.0 A at 10°C rise (QueenEMS), rising to ~1.5–3 A at higher rise/plating (Sierra Circuits, Bestpcb). The in-hand ~75 A/mm² is consistent once rise and plating are matched. Vias run 20–30% hotter than an equal-area surface trace because they are embedded in FR-4.
- **External trace:** from I = k·ΔT^0.44·A^0.725 (IPC-2221, k = 0.048 external), density falls as area grows (the 0.725 exponent). Worked public example (smps.us / IPC-2152): 10 A at 20°C rise → ~500 mil² ≈ 0.32 mm² → ~31 A/mm². So external-trace allowable density at the operating rise is on the order of 35–60 A/mm² for the ~1–10 A conductors on these boards — well below 100 A/mm² (smaller, higher-rise traces run higher).
- **Internal trace:** k = 0.024; needs ~2.6× the area of an external trace for the same current/rise, so allowable density is roughly 50–60% of the external value. IPC-2152 found the true internal penalty smaller than the old halving rule, but design-conservative practice is to keep the lower value.

**Reconciliation with in-hand numbers.** The ~75 A/mm² via density and the ~2.5 A per-via figure at 10°C rise are internally consistent and are the binding small-geometry case. At 20 vias/lane carrying 9.2 A (~0.46 A/via), the array has ~5.4× headroom on count (20 × 2.5 A = 50 A capacity vs 9.2 A demand) and ~6× on per-via current.

**Recommendation — replace the single 100 A/mm² gate with scoped limits at the 30°C operating rise (derivation-class; verify against the IPC-2152 via/microvia appendix):**
- **Via barrel: ≤ 75 A/mm²** (matches in-hand analysis; cross-check against the fab's *guaranteed-minimum* plating, not nominal).
- **External trace: ≤ ~60 A/mm²** for conductors in the 1–10 A range (scale-dependent; smaller traces may exceed this).
- **Internal trace: ≤ ~35 A/mm².**
The flat 100 A/mm² should be retired: it is non-conservative for vias and traces at the operating rise and conflates three different geometries.

### Constant 5 — Fusing limit 400 A/mm² rebuilt as (J, t)

**Onderdonk (original form, via Brooks/Adam UltraCAD and Babrauskas):**
I = A·√[ log₁₀((Tm − Ta)/(234 + Ta) + 1) / (S·33) ], A in circular mils, S in seconds, Tm = 1083°C. Brooks/Adam reduce it, for a 20°C reference and area in **square mils**, to:
**t = 0.0346·(A/I)²**, equivalently **I²t = constant** (the classic I²t fuse rating) and **(I/A)·√t = 0.186** in mil² units.

**Preece (steady fusing, no time):** I = a·d^1.5 (a = 10244 for copper, d in inches) = 12277·A^0.75 (A in in²). Babrauskas confirms Onderdonk runs ~17% below the modern thermophysical value and reproduces the 3/2-power form. Stauffacher (1928) is the earliest published reference to Onderdonk's relation.

**Converted to current density vs time (copper):** with A in mm², J[A/mm²] = (1/√6.4516×10⁻⁴)·√(0.0346/t) = 1550·√(0.0346/t):

| Pulse time | J_fuse (A/mm²), 20°C start | J_fuse (A/mm²), ~80°C start (≈×0.94) |
|---|---|---|
| 10 ms | ~2,880 | ~2,710 |
| 100 ms | ~910 | ~860 |
| 0.5 s | ~408 | ~385 |
| 1 s | ~288 | ~272 |
| 5 s | ~129 | ~122 |

**Where flat 400 A/mm² is correct:** 400 A/mm² is the Onderdonk melting density for a **≈0.5 second** adiabatic pulse from a 20°C start (≈0.55 s from an 80°C start). Stated plainly: **the existing 400 A/mm² gate silently assumes a ~0.5 s fault.** Elevated start temperature lowers the fusing density only ~5–6% (the k-ratio √(1.47/1.65) ≈ 0.94 between 70–80°C and 20°C starts), so a warm board does not dramatically change the curve.

**Adiabatic validity window:** Onderdonk assumes no conduction/convection/radiation. Sources say it is invalid beyond ~10 s, and Adam notes cooling effects can matter in as little as 1–2 s. Brooks/Adam simulation shows the equation is conservative: verbatim, "thermal simulation models suggest that the actual fusing times can be 1.5 to 6.0 times longer than Onderdonk suggests (and more considering the restrictive assumptions of the models)" — i.e., real traces survive longer (or, equivalently, fuse at higher current) than Onderdonk predicts, so a gate built on it errs safe. **Use Onderdonk only for pulses ≲ 1 s; treat 1–10 s as a conservative lower bound; beyond 10 s revert to steady-state ampacity.**

**Cross-check vs platform fault durations (Constant 3b):** PSU OCP clears in ms-to-500 ms; at the slowest 500 ms window the fusing density is ~408 A/mm², and at a fast trip of <100 ms it is >900 A/mm². The CEC lanes operate at ~75 A/mm² (via) and tens of A/mm² (trace). **Operating density is ~5–12× below the fusing density even at the slowest 500 ms protection window**, so protection clears faults with large margin before copper approaches melting. The fusing gate is a forensic/worst-case backstop, not the primary protection.

**Recommendation:** Replace flat 400 A/mm² with the **(J, t) curve J = 1550·√(0.0346/t) A/mm² (20°C start; ×0.94 for an 80°C start)**, stored as an I²t-style limit with the adiabatic-validity caveat (valid <1 s, conservative to 10 s), and document that 400 A/mm² corresponds to the 0.5 s point. *(This item does NOT depend on the paywalled standard — Onderdonk and Preece are fully public; only the underlying IPC test method TM-650 2.5.4.1A is referenced for the trace data.)*

## Recommendations

**Stage 1 — immediate corpus edits (no new data needed):**
- Rewrite dT_max and T_max as one coherent block: "Local board design ambient = 50°C; max steady-state copper rise = 30°C → 80°C copper; +20°C transient → 100°C; absolute ceiling = 105°C set by the lowest-rated BOM part (105°C electrolytic capacitor)." Sign as **KEEP-with-provenance**.
- Retire the flat 100 A/mm² gate; replace with three scoped limits (via ≤75, external ≤~60, internal ≤~35 A/mm² at 30°C rise). Sign as **SPLIT-by-geometry**.
- Replace flat 400 A/mm² with the Onderdonk (J, t) curve and note the 0.5 s correspondence. Sign as **CONVERT-to-time-dependent**.

**Stage 2 — verification when an IPC-2152 copy is acquired:** Confirm the 10/20/30°C curve points, the internal-vs-external correction factors, and the via/microvia appendix values against the actual figures. Re-derive the scoped density limits from the real Figure 5-2 at 30°C rise. Expected change is small and in the safe direction (IPC-2152 permits more current than IPC-2221).

**Stage 3 — bench validation:** Thermocouple a populated 12VHPWR lane at 9.2 A in a closed case to measure true local board ambient and copper rise; measure the actual trace thermal time constant with a current step. This replaces the derivation-class τ values in Constant 3 with measured ones.

**Thresholds that change the recommendations:**
- If measured in-case ambient exceeds **55°C**, cut the steady-state rise budget from 30°C to 20°C (otherwise the transient touches 105°C).
- If a high-Tg laminate or 125°C-rated capacitors are adopted, the BOM floor — and thus T_max — can rise above 105°C; re-run min-of-BOM.
- If protection is ever slower than ~1 s (e.g., a PPTC chosen near its I_trip), the fusing (J, t) curve becomes design-relevant rather than forensic; size copper so operating density is ≥3× below the fusing density at the actual clearing time.

## Summary Table

| Constant | Current value | Recommended disposition | Draft corpus-entry statement |
|---|---|---|---|
| **dT_max** | 30°C copper rise | KEEP as-is with provenance (it is a rise, not absolute) | "Maximum steady-state copper temperature rise = 30°C above local board temperature (IPC-2152 publishes 10/20/30°C rise curves; derivation-class, verify Fig. 5-2); with a 50°C design ambient this yields 80°C copper, leaving 25°C margin to the 105°C ceiling." |
| **T_max** | 105°C ceiling | KEEP as-is with provenance; document as min-of-BOM | "Absolute board temperature ceiling = 105°C, set by the lowest-rated BOM part — a 105°C aluminum electrolytic capacitor (Nichicon GL: 2,000 h load life at 105°C); FR-4 (~110°C continuous) and Schottky junctions (125°C) sit above it; keep steady-state ≤85°C so the +20°C transient cannot exceed it." |
| **Transient allowance** | +20°C above steady state | CONVERT to time-dependent (ΔT, τ) pairs | "Transient copper allowance = +20°C above steady state, valid for fault events ~0.1–10 s (PSU OCP ≤500 ms per EPS12V v2.92; PPTC seconds), with τ ≈ 2–10 s by trace geometry; events <10 ms are governed by the fusing curve, not this budget." |
| **J_max** | 100 A/mm² flat | SPLIT by geometry class | "Replace flat 100 A/mm² with scoped current-density limits at 30°C rise: via barrel ≤75 A/mm² (matches in-hand 0.3 mm/1 oz analysis), external trace ≤~60 A/mm², internal trace ≤~35 A/mm² (derivation-class from IPC-2221/2152; verify via appendix)." |
| **Fusing limit** | 400 A/mm² flat | CONVERT to (J, t) curve | "Replace flat 400 A/mm² with the Onderdonk adiabatic curve J_fuse = 1550·√(0.0346/t) A/mm² (20°C start; ×0.94 at 80°C); 400 A/mm² = the 0.5 s point; valid for pulses <1 s, conservative to 10 s; operating density is 5–12× below this at the slowest protection window." |

## Caveats
- **Every chart-derived number is derivation-class.** IPC-2152 and IPC-2221 figures are paywalled; all chart values here come from public derivations (Jouppi/Olson tutorials, Brooks/Adam UltraCAD papers, smps.us interpolation, Saturn/Sierra/AtlasPCB calculator docs) and must be re-verified against the standard's actual figures before final sign-off. The Onderdonk and Preece relations and the connector/component datasheet values are fully public and **not** derivation-class.
- **Source disagreements flagged:** (1) SB120 junction temperature is +125°C (Vishay 88715, onsemi/Fairchild Rev. C) or +150°C (Diodes Inc DS23022, Diotec) — use +125°C as the conservative value, though either is above the capacitor floor. (2) FR-4 continuous max operating temperature is historically 130°C (UL/ANSI) but UL now allows up to 150°C with long-term thermal-aging data — the conservative ~110°C (Tg−20°C) value is used. (3) The "halve external for internal" rule (IPC-2221) is contradicted by IPC-2152 measurements showing internal traces run near free-air behavior; the corpus uses the conservative lower density. (4) Internal-trace width penalty is quoted as both "20–30% more width" (RayPCB) and "carry 50–70% of external current" (AtlasPCB) — both are public approximations of the same paywalled curves.
- **Brooks/Adam caution:** real traces fuse 1.5–6× slower than Onderdonk predicts, so the (J, t) curve is conservative (safe) — use it only as a do-not-exceed backstop, never to justify smaller copper. A fused trace is a destructive, one-time event: never return a fused board to service.
- **Connector caveat:** the 12VHPWR/12V-2×6 30°C T-rise spec and the well-documented melting failures mean the connector, not the PCB copper, is often the real thermal weak point; board design rules cannot protect a poorly-seated connector.
- The PC-case ambient figures are enthusiast forum measurements, not a controlled study; the 50°C design ambient is a conservative engineering choice, not a measured value for the CEC enclosure. Validate by bench measurement (Stage 3).