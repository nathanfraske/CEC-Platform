# Thermal-solve completeness — blind enumeration + synthesis (2026-07-06)

**Method (owner directive):** two agents, different disciplinary lenses (thermo-fluids/mechanical;
electrical/EM/materials/reliability), each given ONLY the 11-item considered-inventory below —
no repository access, no knowledge of the implementation — and asked to exhaustively enumerate
what is MISSING for a final, maximal-fidelity, compute-heavy solve. Their full reports are
Appendices A and B. This synthesis identifies convergences (items both lenses found
independently = highest signal), diffs them against the coverage-audit gap list in
`blade-interconnect-thermal-2026-07-06.md` §1, and stages a roadmap.

## The considered inventory (the agents' only input)

1. 2.5D per-layer rasterized copper conduction; vertical coupling via barrels only.
2. Via barrel cross-sections; cluster/proportional current splits.
3. Joule heating with rho(T) to a fixed point; runaway/fusing detection.
4. DC currents from the design-basis role model; min-cut bottleneck analysis; J ceilings.
5. DC IR-drop field solve.
6. Discrete shunt I2R sources.
7. Connector joints: contact R (nominal + worn) + conductor geometry; calibrated to the vendor rating datum.
8. IPC-2221/2152 anchors/gates.
9. Uniform ambient; still-air natural convection; one board's TIM/baseplate model.
10. Steady-state only.
11. <=30C rise @125% gates, per-element verdicts.

## Convergences (found independently by BOTH blind lenses)

| # | Item | Thermo-lens | Electrical-lens | Class |
|---|---|---|---|---|
| X1 | Radiation entirely absent (15-30% of still-air heat rejection) | D1-D3 | I1 | Tier-1 add |
| X2 | Real airflow / non-uniform + load-elevated ambient (case CFD at the limit) | C1-C4, E1-E2, H1 | I2, E5 | Tier-1 param sweep -> Tier-3 CFD |
| X3 | Cable/harness as a THERMAL conductor loading the connector joint from outside | H2 | I4 | Tier-1 (1D fin model) |
| X4 | Force-coupled contact resistance: heat->expansion/creep->force->R->heat (runaway loop) | G1, G2 | B4 | Tier-2 (vendor spring data) |
| X5 | Manufacturing tolerance on copper thickness / via plating vs as-drawn | A5 | C1, C2 | Tier-1 (corner runs) |
| X6 | Monte Carlo / UQ against the hard 30C gate (confidence, not point-pass) | K5, K4 | F1, F2 | Tier-1 wrapper (compute-heavy) |
| X7 | Transient/duty-cycle thermal response to real bursty loads (ratcheting; small-mass overshoot) | I1, I2 | H1, A5 | Tier-2 (thermal-RC + load traces) |
| X8 | Solder-joint fidelity (interface resistance, void content) | A6 | C3 | Tier-1 |
| X9 | Thermal-cycling fatigue at the gated joints (Coffin-Manson class) | G3 | B2 | Tier-2 (needs X7) |
| X10 | Full heat-source inventory beyond shunts (LDO, LEDs, MCU, ICs) | B1-B3 | G5 | Tier-0 |

## Highest-value UNIQUE items per lens

**Electrical lens (Appendix B):**
- **E3 — unequal current sharing across nominally-parallel pins from contact-R variance** — the
  industry's actual documented 12VHPWR melt mechanism; replaces the assumed even A/pin split with
  a resistor-network solve over an R distribution; the gate re-evaluated at worst-single-pin.
  SYNERGY: the 12VHPWR module's per-pin INA240s MEASURE exactly this in the field — the model
  and the product cross-validate.
- **E1 — N-1 element loss** (one blade/via opens; survivors re-checked) — the redundancy
  rationale is unassessed without it. Cheap: existing solver run N times.
- **E2 — partial-seat point contact** (assembly-defect scenario; localized runaway).
- **E4 — fault/surge I2t withstand** beyond the steady gate.
- **Section G — the instrument-accuracy loop**: shunt TCR, amplifier/reference drift, thermal
  EMF at Kelvin junctions — all as consumers of the solve's OWN temperature outputs. Nearly
  free; directly quantifies "how wrong are the readings when hot" — the product's core promise.
- A2/H2 — impedance-based (not DC-R) transient sharing across parallel paths (PEEC class).
- B1/D2 — PCB-copper electromigration life at flagged hotspots (data-gap: PCB Black's params).

**Thermo lens (Appendix A):**
- **F3 — the connector housing as an insulating, air-blocking cavity around the gated joint**
  (bare-joint-to-ambient may be non-conservative). NOTE: our bare-clip/receptacle config has no
  housing — but the daughterboard/main-board gap geometry plays the same role; model the real
  local air cavity.
- **E3 — wake/recirculation behind the standing daughterboard** (its only convective surface may
  sit in its own dead zone).
- A4 — spreading/constriction resistance at small sources (shunt pads, blade tips).
- D2 — per-region emissivity map from the SAME board files already rasterized (matte-black mask
  ~0.9 vs bare metal ~0.05).
- K1/K2/K3 — numerical V&V: grid convergence, one-off 3D-FEM benchmark of the 2.5D model,
  bench thermography validation (ties to the AM-04 calibration latch + OQ-86 soak).
- H3 — finite chassis (the sink heats up under whole-system load).
- F4 — multi-board assembly as ONE coupled domain (main + joint + daughterboard).

## Diff vs the coverage audit's own gap list (blade-interconnect doc §1)
The audit (repo-aware) had already named: connector joints (since implemented), solder joints,
THT barrel conduction, component-body sources, radiation, convection realism, transient loads,
tolerance treatment. Every audit gap was independently re-found by at least one blind lens
(cross-validation of the audit itself). The blind lenses ADDED beyond the audit: the
force-coupled contact runaway loop (X4), unequal parallel-pin sharing (E3), N-1 redistribution,
I2t fault withstand, the instrument-accuracy loop (G), impedance-based transient sharing,
electromigration life, the housing/cavity + wake geometry items, emissivity mapping, chassis
finiteness, and the formal V&V program.

## Roadmap — the staged path to the "final super compute-heavy solve"

- **Tier 0 (consumers of existing output; days):** full heat-source inventory (X10); absolute-T
  vs material limits (Tg/UL); instrument-accuracy loop G1-G5 (shunt TCR %-error, thermal-EMF at
  computed gradients, amp/ref drift at local T); per-region emissivity map extraction.
- **Tier 1 (wrappers + boundary terms; weeks):** radiation term (X1); orientation-correct
  convection correlations + parametric airflow sweep (X2, cheap half); cable 1D-fin boundary
  (X3); solder interface/void derates (X8); tolerance corner runs (X5); E1 N-1 sweep; E3
  resistor-network unequal-sharing with R distributions; E4 I2t check; Monte Carlo wrapper (X6 —
  compute-heavy in count, trivial in machinery).
- **Tier 2 (new machinery; months):** transient thermal-RC driven by real load traces (X7) +
  impedance-based transient splits (A2/PEEC); force-coupled contact model (X4 — NEEDS vendor
  spring stress-relaxation data, else bench-derived); local 3D FEM at joints (A3); fatigue (X9);
  V&V program (K1-K3 — grid convergence + one 3D benchmark + bench thermography against the
  OQ-86 soak).
- **Tier 3 (the super-solve; the compute-heavy endgame):** full-case conjugate CFD with fans,
  GPU/PSU plumes, obstruction geometry (X2 full); multi-board unified domain (F4); Monte Carlo
  over the whole stack. Research-grade parked items: asperity-level contact (G2-thermo),
  PCB electromigration kinetics (data gap), fretting kinetics (vendor data gap).
- **Data acquisition (gates several tiers):** real GPU/CPU current traces (percentile-based
  worst case, F3-elec); vendor spring/relaxation + fretting data; fab tolerance capability data;
  mission profiles. The OQ-86 bench soak doubles as the first K3 validation point and the E3
  contact-R-distribution measurement.


---

# Appendix A — blind report, thermo-fluids/mechanical lens (verbatim)

# Blind Completeness Review: Electro-Thermal Solve Gaps

Reasoning purely from first-principles thermal/fluid/mechanical domain knowledge applied to the stated power class (tens of watts, tens of amps DC, PC-case environment, 30°C-rise gate at 125% sustained current). Organized by physical category, each item with mechanism, materiality, and modeling requirement.

---

## A. Conduction (solid) — beyond the current 2.5D layer model

**A1. True through-thickness conduction via dielectric (not just via barrels).**
(a) Heat spreading through FR4 core/prepreg between copper layers not connected by a via. (b) FR4 has ~0.3–0.5 W/m·K through-plane conductivity — three orders below copper, but nonzero. (c) Matters for smoothing local hot spots near a shunt or IC pad where the nearest via cluster is not directly beneath the source; a 2.5D via-only coupling model can overstate local peak ΔT by not letting the dielectric "leak" heat sideways-then-down. (d) A resistor-network augmentation adding vertical dielectric conductance per raster cell, or spot-check against a full 3D FEA reference.

**A2. Anisotropic dielectric properties (glass-weave conductivity skew, resin-rich vs. glass-rich regions).**
(a) FR4 conductivity varies with local glass-fiber fraction and weave orientation. (b) In-plane vs. through-plane anisotropy, plus lot variation. (c) Second-order at this power class; only matters for tie-breaking marginal-pass hot spots. (d) Requires either measured material anisotropy data or acceptance of the isotropic-average simplification with a documented uncertainty band.

**A3. Component package conduction as parasitic heat spreaders/sinks.**
(a) IC packages (MCU module, INA238/240, CAN transceiver, LDO) conduct heat through their own leadframe/exposed-pad into the board, and back out through their plastic body to air. (b) Package thermal resistance (θJC, θJA) and lead conduction. (c) Materially changes the local field near ICs sitting close to a shunt (a nearby regulator or MCU package acts as an unmodeled fin or, conversely, an unmodeled co-located heat source — see B-category). (d) Component-level compact thermal models (2-resistor or DELPHI-style) coupled into the board mesh.

**A4. Constriction/spreading resistance at small hot-source footprints.**
(a) A 2512 shunt or a blade-tab pad is small relative to the copper pour it feeds heat into; classical spreading-resistance theory (concentrated source on a finite-thickness plate) predicts a real ΔT adder beyond a naive "average flux over pad area" treatment. (c) Can matter at exactly the locations the gate cares about (shunt hot spot, joint hot spot) — these are precisely small-source-on-large-plane geometries. (d) Analytical spreading-resistance correction or fine local mesh refinement at every discrete source.

**A5. As-manufactured copper thickness/cross-section variance.**
(a) Plating tolerance (±10–20% typical on nominal 1–2 oz), etch undercut, trace edge roughness. (b) Directly scales resistance and therefore both I²R and cross-sectional current-density ceiling. (c) At a hard 30°C/125% gate, a 15% thin-side copper tolerance is a first-order margin eater, not a rounding error. (d) Either a documented worst-case-thin design margin, or statistical treatment (see K/UQ below).

**A6. Solder-joint interface resistance at shunt-to-pad and connector-to-pad.**
(a) Solder fillet is a distinct material (different k, different geometry) between the discrete heat source and the copper plane. (c) Small ΔT itself, but relevant where the joint model (item 7 in the given list) meets the board copper model — a seam in the two sub-models that could double-count or under-count resistance at the interface. (d) Explicit interface thermal resistance term at every discrete-source-to-plane transition.

**A7. Current crowding at trace corners / pad-to-trace necks (geometric, not just min-cut).**
(a) 90° bends and abrupt width transitions concentrate current density above the "average cross-section" value used in min-cut analysis. (b) Field-crowding at reentrant corners. (c) Real effect at every right-angle trace bend on these boards (a lot of them, per the daughterboard/lane-corridor routing described in this project's own history); could produce a local hot line-segment the min-cut/average-cross-section approach misses entirely. (d) A true 2D (or 2.5D) current-density field solve (which the tool may already effectively be doing via its IR-drop solve, item 5 in the given list — worth explicitly confirming that the *thermal* source term is fed from the *spatially resolved* J² map rather than a per-net-average I²R lump).

---

## B. Heat-source completeness (Joule + non-Joule)

**B1. Full component power-dissipation inventory beyond shunts.**
(a) MCU (active/idle power), CAN transceiver (quiescent + switching), LDO/linear regulator dropout×current, ESD/protection diode leakage, status LEDs (addressable RGB draw real current — the project's own docs note ~0.4 A/board at full white). (b) Ordinary Joule/switching dissipation in every active part, not just the sense path. (c) An LDO dropping, say, 1.7 V at several hundred mA is a fraction-of-a-watt point source in a small SOT-23 footprint — locally significant even if trivial to total board power. LEDs at sustained high brightness are a real, easily-overlooked concentrated source. (d) Per-part power budget from datasheet + operating point, injected as additional discrete sources in the same framework already used for shunts.

**B2. Capacitor ESR/ripple heating under real (non-ideal) supply ripple.**
(a) Bulk and decoupling capacitors dissipate I²·ESR under ripple current, especially at switching-regulator outputs. (c) Usually small at this scale but should be confirmed negligible rather than assumed. (d) ESR from datasheet × estimated ripple current RMS.

**B3. Sense-chain self-heating feedback on the boards' own measurement accuracy.**
(a) The INA-class amplifier's own die self-heating shifts its gain/offset, and a shunt's own temperature rise changes its TCR — both feed back into the *accuracy* the platform promises, distinct from the pass/fail thermal gate. (c) Relevant because this platform's core value proposition is measurement accuracy; a thermal solve that only asks "does it exceed 30°C" without asking "how much does 30°C of self-heating bias the reading" is leaving a related, cheap-to-answer question unaddressed. (d) Couple the thermal solve's local shunt/IC temperature output back through the sensor's published TC/thermal-drift specs.

**B4. Thermoelectric (Seebeck) offset at Kelvin-sense junctions under steep local gradients.**
(a) Dissimilar-metal junctions (solder/copper/shunt element) in a strong local temperature gradient produce a small parasitic EMF. (c) Almost certainly negligible in magnitude, but worth a one-line dismissal with numbers rather than silent omission, given this is precisely a precision Kelvin-sense board.

---

## C. Convection (natural + forced)

**C1. Actual case airflow field replacing "uniform still-air" or a single ho.**
(a) Real PC cases have fans (intake/exhaust), producing a highly non-uniform, non-still local velocity field. (b) Forced/mixed convection vs. natural convection changes local ho by a factor of 3–10×. (c) This is likely the single largest lever on the final ΔT number at this power class — a still-air assumption could be wildly conservative in a well-ventilated build, or non-conservative in a stagnant recirculation pocket exactly where a perpendicular daughterboard creates a wake. (d) Either (i) a parametric ho sweep spanning still-air through typical case-fan velocities with sensitivity reporting, or (ii) full conjugate CFD of a representative case model (fans, vents, neighboring components) — a genuinely compute-heavy step (3D RANS CFD, meshing the case interior).

**C2. Board/daughterboard orientation-dependent natural convection.**
(a) Horizontal vs. vertical plate natural-convection correlations differ substantially (this project's own history shows a pivot to *vertical* card-on-edge daughterboards). (c) Directly affects the daughterboard's only realistic passive-cooling path since it has no dedicated heat sink. (d) Orientation-correct correlation (vertical plate vs. horizontal-plate-facing-up/down) or CFD, not a single generic ho.

**C3. Board-to-board channel/proximity effects.**
(a) Closely spaced parallel boards (main board + daughterboard, or adjacent modules) form a convective channel with entrance effects, reduced ho on facing surfaces, possible chimney (stack) effect for vertical assemblies. (c) The stated architecture (daughterboard standing off the main board at a defined float height) is exactly this geometry. (d) Channel-flow natural/mixed-convection correlations or local CFD of the two-board gap.

**C4. Conjugate heat transfer (two-way solid/air coupling) vs. fixed boundary ho.**
(a) A fixed convection coefficient ignores local air heating downstream of a hot component (thermal wake), which raises effective local ambient for downstream features. (c) Matters when multiple heat sources sit in a flow path (e.g., several shunts along one air stream). (d) CHT solver (solid + fluid domains solved together) rather than a lumped-ho boundary condition — significant compute increase over the current 2.5D approach.

**C5. Nested-enclosure convection for the "enclosed product" SKUs.**
(a) An enclosed metal/printed case around the board creates a secondary, much-lower-airflow internal cavity; heat must first convect/radiate to the inner case wall, conduct through the case wall, then convect/radiate externally. (c) A completely different (and generally worse) thermal regime than an open board in case airflow — this is explicitly called out in the input as "one board has a case-cooling model," implying the others may not, and even that one model may only capture the TIM/baseplate conduction path, not the internal-cavity convection above it. (d) Two-tier BC: internal natural convection (often the bottleneck) + wall conduction + external convection/radiation, ideally CHT.

**C6. Fan-failure / degraded-airflow design margin scenario.**
(a) Standard reliability practice checks thermal margin under a failed/degraded cooling condition (N-1 fan), not just nominal airflow. (c) A board validated only at "typical case airflow" could silently fail the gate if a user has no case fans, an unusual case, or a fan dies. (d) Re-run the same solve at the still-air limit as an explicit bounding case (cheap once C1's machinery exists).

---

## D. Radiation (currently entirely absent)

**D1. Surface-to-ambient/enclosure radiative exchange.**
(a) Radiative heat transfer between board/component surfaces and surrounding case walls or neighboring boards. (b) Stefan-Boltzmann law with surface emissivity and geometric view factors. (c) At the delta-Ts and absolute temperatures involved here (~70–100°C surfaces, room-temp-ish surroundings), radiation can plausibly carry 15–30% of total heat rejection in a still-air-dominated regime — a non-trivial fraction of margin against a hard 30°C gate that is currently simply given away. This matters *more*, not less, wherever convection is weak (still-air default, or the nested enclosure of C5). (d) A view-factor/radiosity network (or full ray-traced Monte Carlo radiosity for the enclosed case interior) using measured/estimated emissivities.

**D2. Surface finish/emissivity fidelity.**
(a) Matte black solder mask (~0.9 emissivity, per this project's own stated black ENIG boards) vs. bare copper/gold pads (~0.03–0.1) vs. silkscreen coverage fraction. (c) An order-of-magnitude emissivity spread across a single board's surface directly scales D1's contribution; treating the whole board as one emissivity value could be meaningfully wrong. (d) Per-region emissivity map from the actual copper/mask/silk layer stack-up (available from the same board files already being rasterized for copper).

**D3. Radiative shielding/multiple-reflection in an enclosed metal case.**
(a) A metal enclosure interior can specularly reflect radiation, effectively "trapping" heat rather than passing it straight to the wall (single-bounce assumption underestimates internal temperature). (c) Relevant specifically to the enclosed-product SKUs and any daughterboard sitting close to a shielding can. (d) Multi-bounce radiosity solve rather than single view-factor pass, if the enclosure is specular/reflective rather than diffuse.

---

## E. Fluid dynamics / system-level CFD

**E1. Full 3D case CFD (fans, vents, obstructions, cable routing).**
(a) The actual airflow pattern inside a real PC case: fan curves, intake/exhaust vent placement, obstruction by drive cages/cable bundles/other boards. (c) Determines the *real* local ho and local air temperature at each module's actual mounting location — a single "configurable uniform ambient + still air" abstraction cannot represent this. (d) 3D RANS CFD (k-ω SST or similar) of a representative case model; a genuinely heavy compute step, likely the most expensive addition on this whole list.

**E2. GPU/PSU exhaust plume raising local ambient for the power-adjacent modules.**
(a) The EPS/PCIe/12VHPWR modules and daughterboards physically sit at or near the GPU and PSU — i.e., right next to the two hottest components in the whole PC. Their exhaust plumes can push local air well above the nominal case-ambient figure used as a single global boundary condition. (c) This is arguably the most application-specific realism gap: these are precisely the modules living closest to real hot neighbors, and are exactly the modules whose sustained-current joints are being safety-gated. (d) Either a CFD-derived local ambient map (from E1) or a conservative documented ambient offset applied specifically to power-adjacent module locations.

**E3. Recirculation/dead-zone/wake pockets behind a perpendicular daughterboard.**
(a) A card-on-edge daughterboard standing off the main board creates a bluff-body wake in the local flow — potentially a stagnant low-ho pocket exactly where its only heat-shedding surface is. (c) Directly relevant to the stated "floating daughterboard, no dedicated heat sink, friction-retained" mechanical architecture — its cooling budget depends entirely on getting this right. (d) Local CFD around the connector/daughterboard assembly, not a board-level average ho.

**E4. Transient/time-varying airflow (fan RPM tracking system load).**
(a) Case fan speed is not constant; it ramps with system thermal load, correlating (with lag) to the very GPU/PSU loading that also drives the sense boards' own worst-case current. (c) A coincidence-of-worst-cases question: does peak electrical load correlate with *reduced* airflow (fans still ramping up) at the moment of peak dissipation? (d) Coupled transient CFD + thermal, or at minimum a documented worst-case correlation assumption.

---

## F. Geometry fidelity (beyond 2.5D rasterization)

**F1. True 3D copper features lost in per-layer rasterization.**
(a) Pour corner rounding/chamfering, thermal-relief spokes at through-hole pads, teardrops at via/pad transitions, copper thieving/hatch fill for panel balance. (c) Thermal reliefs in particular *reduce* local cross-section right at a via/pad junction — exactly the kind of local bottleneck the "min-cut" analysis is trying to catch, and easy to miss if the raster resolution or import step doesn't preserve reliefs faithfully. (d) Verify the rasterization pipeline preserves relief/teardrop geometry at native resolution, or explicit min-cut check at every thermal-relief spoke set.

**F2. Component bodies as airflow obstructions/redirectors (not just heat sources).**
(a) Tall electrolytic capacitors, connector housings, and the daughterboard assembly itself physically block and redirect local air, independent of their role as heat sources. (c) Feeds directly into C3/E3 above — a purely thermal model without airflow obstruction geometry can't get local ho right near tall components. (d) 3D CAD-level obstruction geometry as input to any CFD/CHT step.

**F3. Connector housing as a local thermal-insulating cavity.**
(a) The plastic connector housing around a blade/receptacle joint is low-conductivity and low-emissivity, effectively wrapping the highest-current-density joint in the whole system in an insulating shroud that also blocks direct air access and radiative view to the joint contact itself. (c) Potentially the most consequential geometry-fidelity gap on this list, because it sits exactly at the element the gate is built around (per-joint verdicts). A joint model that gets contact resistance right (item 7 given) but assumes the joint radiates/convects freely to ambient — when it's actually enclosed in plastic — could be substantially non-conservative. (d) Explicit thermal model of the housing cavity (small enclosed-air conduction/convection + housing-wall conduction to whatever it touches), not a bare-joint assumption.

**F4. Multi-board assembly as one coupled thermal system.**
(a) Main board + daughterboard + connector should be solved as one continuous domain (conduction across the joint, shared local air, mutual radiation view), not as two independently-gated boards with an idealized joint boundary condition stitching them. (c) Cross-board conduction/radiation coupling could shift where the true hot spot sits (e.g., a main-board plane acting as an unmodeled heat sink or heat source for the daughterboard). (d) Single unified mesh/domain spanning both boards and the connector.

---

## G. Mechanical / structural coupling (thermo-mechanical-electrical loop)

**G1. CTE-mismatch-driven contact-force change at the blade/receptacle joint.**
(a) Copper blade, brass/phosphor-bronze receptacle spring, and plastic housing have different coefficients of thermal expansion; as the joint heats, differential expansion changes the spring normal force at the contact. (b) Contact resistance is strongly force-dependent (Holm constriction theory — resistance scales roughly as force^-0.5 to force^-1 depending on regime), so this is a genuine two-way coupling: temperature changes force changes resistance changes heat generation. (c) This is exactly the mechanism underlying "vendor-spec nominal + a degraded scenario" in the current model — replacing that with a physically-coupled force-dependent model would test whether *self-heating itself* can push a joint from nominal into the degraded regime, a materially different (and more alarming) failure mode than an externally-imposed "worn" derate. (d) Coupled thermo-mechanical FEA (housing/spring deflection under thermal expansion) feeding a force-dependent Holm-type contact-resistance law, iterated with the thermal solve to a joint fixed point.

**G2. Micro-scale contact-resistance model (Holm/Greenwood-Williamson) vs. lumped nominal value.**
(a) Real contact resistance arises from a population of discrete asperity contact spots, each with its own constriction resistance and possible thin oxide/film resistance, not a single macroscopic value. (c) Determines *where within the joint footprint* the hottest micro-spot is, and how resistance evolves with wear/fretting — directly relevant to a connector class explicitly chosen partly for high (not low) insertion force, where asperity behavior at first mate vs. after cycling could differ a lot. (d) Asperity-population contact model (data-hungry — needs surface roughness/hardness inputs — genuinely a research-grade addition, listed here for completeness even though likely impractical at production timelines).

**G3. Thermal-cycling fatigue / creep at solder joints and board flex.**
(a) Repeated thermal cycling induces CTE-mismatch stress at solder joints (shunt-to-pad, connector-to-board) and can induce board warpage. (c) A reliability/lifetime question, not the immediate 30°C-rise gate — but relevant to the same joints the gate protects, over the product's service life. (d) Thermal-cycle fatigue life estimate (e.g., Coffin-Manson/Engelmaier) using the solve's own predicted ΔT swing as the driving cyclic strain input.

**G4. Board warpage effect on TIM/chassis mount interface quality.**
(a) A board bowing under its own thermal gradient can locally reduce contact pressure/area at a chassis mounting point, degrading the very TIM interface the case-cooling model relies on. (c) A second-order but real feedback specifically on the one board already claiming a case-cooling benefit — worth checking that benefit isn't itself sensitive to a warpage this same solve predicts. (d) Coupled thermal-structural (bimetallic-strip-style) deflection estimate feeding back into TIM contact-area assumption.

**G5. Mounting-torque/assembly-variance effect on TIM thermal resistance.**
(a) TIM interface resistance is a strong, nonlinear function of applied clamp pressure; real assembly torque varies from unit to unit. (c) The single case-cooling model's claimed benefit is only as good as its assumed (uniform, ideal) clamp pressure — production variance could erode it. (d) TIM resistance-vs-pressure curve (from TIM datasheet) combined with a torque tolerance range, ideally as a sensitivity/UQ input (see K).

**G6. Floating-daughterboard strain-relief loading as a joint-integrity risk.**
(a) A daughterboard retained only by connector friction fit, with cable strain relief pulling on it externally, imposes a mechanical load directly onto the same joint being thermally gated — a bending/pull load superimposed on the thermal-cycling load of G1. (c) Directly named as an open item in this project's own documentation (strain-relief pull-force numbers still owed); from a pure thermal-fidelity standpoint, this is the mechanical loading condition most likely to change the joint's actual (as-installed) contact geometry away from whatever was assumed in the thermal model. (d) Structural load case analysis of the cable pull force on the joint, feeding into G1's force-dependent contact model.

---

## H. Boundary-condition realism / system integration

**H1. Non-uniform, multi-zone ambient rather than one global number.**
(a) Real case-internal air temperature is spatially non-uniform (hot near GPU/PSU, cooler near intake) and rises over a session. (c) Already covered thermally in E2; listed here as a boundary-condition modeling requirement specifically — replace the single scalar ambient input with a spatial (and possibly temporal) ambient field. (d) CFD-derived ambient map, or at minimum per-module documented ambient offsets by physical location in a reference case.

**H2. Cable harness as a conductive heat path crossing the system boundary.**
(a) The PSU-side input cable and GPU-side output cable/pigtail are metallic conductors of nontrivial cross-section connecting the module electrically *and thermally* to the PSU internals and the GPU vicinity respectively. Heat can conduct along the wire into or out of the board through the very same connector the electrical/thermal joint model already covers. (c) This is a genuine, currently-absent heat path directly at the input/output connectors — exactly where the gate's per-joint verdicts live. A hot PSU or hot GPU cable run could inject conducted heat into the joint from outside the board's own current-carrying budget. (d) 1D fin/lumped conduction model of the cable (length, gauge, insulation, connected-end temperature) as an added boundary condition at each connector.

**H3. Finite chassis thermal mass/resistance rather than an ideal infinite sink.**
(a) The metal case chassis that a mount-point TIM path relies on is itself a finite thermal mass with its own resistance to the room, and heats up under sustained system load from every other component, not just this board. (c) The case-cooling model's benefit assumes the chassis is available as a "cool" sink; under sustained whole-system load the chassis itself may already be elevated, eroding the assumed ΔT headroom. (d) Chassis-to-room external convection/radiation boundary condition with a finite, temperature-dependent chassis node rather than a fixed-temperature ideal sink.

**H4. Multi-rail loading correlation realism.**
(a) The gate applies 125% of "sustained worst case" per rail — worth asking whether all rails hitting 125% simultaneously is physically realistic (PSU/GPU total power budget may anti-correlate some rail currents) or whether it's a deliberately conservative independent-worst-case envelope. (c) Changes whether the *combined* board temperature field (multiple simultaneous hot joints/shunts, mutual heating) is being tested at a realistic or an overly-conservative (or, if correlation is missed, insufficiently conservative) combined condition. (d) A documented, ideally power-budget-derived, correlated multi-rail loading scenario set, run through the same solver as an additional case beyond independent per-rail worst-case.

**H5. Sealed vs. vented enclosure internal air exchange (enclosed products).**
(a) Whether an enclosed product's case is fully sealed or has any vent path determines whether internal air can exchange with the ambient case air at all, which fundamentally changes the internal convection regime from C5. (c) A binary modeling-assumption question that changes the whole internal boundary-condition class. (d) Confirm enclosure venting design and select sealed-cavity vs. vented-cavity internal convection treatment accordingly.

---

## I. Transient / time-domain

**I1. Steady-state-only vs. real bursty/duty-cycled loading.**
(a) Real GPU/system loads are highly transient (rendering bursts), not a flat sustained current. (b) Thermal mass provides low-pass filtering of short bursts, but sufficiently long or high-duty-cycle bursts can still ratchet the *time-averaged* temperature toward (or past) the nominal steady-state prediction, and short-but-frequent bursts test a different failure mode (peak transient hot-spot exceeding steady prediction locally, especially at small thermal-mass elements like a shunt or a thin blade tip) than steady-state. (c) Matters most at the smallest-thermal-mass elements (the connector joint, the shunt) which have the shortest time constants and could locally overshoot between duty cycles even if the board-average steady-state prediction looks fine. (d) Transient thermal solve (time-stepped, same spatial model) driven by a representative realistic load profile (duty cycle, burst amplitude/period) rather than a single flat sustained value.

**I2. Thermal time-constant characterization per element.**
(a) Time to reach a given fraction of steady-state rise, per element (board copper mass vs. small shunt vs. connector joint — likely very different time constants). (c) Useful cross-check against the platform's own electrical transient-detection scheme (§6.13-style fast detection) — knowing the thermal lag tells you whether an electrically-flagged transient event could ever manifest as a real thermal excursion before it's cleared, or whether thermal risk is dominated by sustained conditions only (as currently assumed) or also by repeated-transient ratcheting. (d) Step-response extraction from the transient model in I1, reported per gated element.

**I3. Power-on inrush as a repeated cyclic thermal stress.**
(a) PSU inrush current spikes at every power cycle are a repeated (not sustained) stress on the same joints/traces. (c) Unlikely to threaten the 30°C sustained gate directly, but contributes to the fatigue accounting in G3. (d) Bound the inrush magnitude/duration and fold into the cyclic-fatigue estimate rather than the sustained-rise gate.

---

## J. Material/manufacturing fidelity

**J1. Material property uncertainty (copper resistivity, FR4 conductivity, contact resistance) as distributions, not point values.**
(a) Every material property fed into the solve today (implicitly) is a nominal/typical value; real parts have manufacturer tolerance bands. (c) At a hard pass/fail gate this determines whether "passes at nominal" is actually "passes with 95% confidence" or "passes only if every tolerance lands favorably." (d) See K/UQ below — this is the data-input half of that.

**J2. FR4 Tg/decomposition and continuous-use temperature limits as a separate safety check.**
(a) The 30°C-rise gate is a functional/reliability design target, distinct from the material's absolute safe-operating-temperature limit (resin glass-transition or UL continuous-use rating). (c) Worth an explicit "and is the absolute hot-spot temperature also comfortably below the material's rated limit" check, independent of whether the 30°C-rise criterion is met (a board could pass the rise gate at a high ambient and still approach a material limit). (d) Compare predicted absolute peak temperature (not just rise) against FR4/solder-mask/connector-plastic continuous-use ratings.

**J3. Connector plating condition (tin vs. gold) and its distinct long-term contact-resistance drift behavior.**
(a) Tin-plated contacts are far more susceptible to fretting-corrosion resistance growth than gold; this affects which "degraded" scenario multiplier is realistic. (c) Directly relevant to whatever plating the actual blade/receptacle parts use. (d) Plating-specific fretting/oxidation contact-resistance-growth model rather than a generic single "worn" derate.

---

## K. Numerical methodology / verification & validation

**K1. Mesh/raster resolution convergence study.**
(a) Is the copper rasterization grid demonstrably fine enough at high-gradient regions (via clusters, shunt pads, joint contacts) and coarse enough elsewhere for tractable compute? (c) Without a documented grid-convergence check, the reported "hottest node" value carries unquantified numerical error that could be comparable to the 30°C gate's margin. (d) Standard grid-convergence-index (GCI) study — halve/double raster resolution locally and confirm the gated verdicts don't change.

**K2. 2.5D-vs-full-3D benchmark.**
(a) The whole approach is explicitly a reduced-order 2.5D approximation (via-only vertical coupling). (c) Should be validated at least once against a full 3D FEA/FVM reference on a representative sub-geometry (e.g., one shunt-plus-vias cluster) to bound the approximation error being carried everywhere else. (d) One-off full 3D reference solve as a calibration/validation anchor, not a routine per-board step.

**K3. Empirical-vs-physical validation against real measured hardware.**
(a) The current anchors (IPC-2221/2152) are themselves empirical bulk correlations for generic trace geometries, not a first-principles validation of *this specific* board's geometry, materials, and connectors. (c) A model that only checks itself against the same class of empirical correlation it's trying to supersede risks correlated blind spots (both could share the same simplifying assumptions, e.g., neither may capture the connector-housing insulating-cavity effect of F3). (d) Physical bench validation: thermocouple or IR-thermography measurement on a real populated board at controlled current, ambient, and airflow, compared point-by-point against the solve's predicted field.

**K4. Sensitivity analysis / ranked input importance.**
(a) Formal ranking of which inputs (ambient, contact resistance, copper thickness, airflow) move the final margin most. (c) Directs limited validation/measurement effort toward the inputs that actually matter, rather than uniformly polishing everything. (d) One-at-a-time or Sobol-style sensitivity sweep across the existing solver.

**K5. Uncertainty quantification / probabilistic margin against the hard gate.**
(a) Propagate the distributions from J1 (material properties), G5 (assembly torque/TIM variance), and manufacturing tolerances (A5 copper thickness) through the solve via Monte Carlo or worst-case tolerance stack-up, rather than reporting one deterministic ΔT number against a hard 30°C cutoff. (c) Converts "passes at 22.95°C rise" into "passes with X% confidence given real manufacturing/assembly variance" — directly answers whether the observed margin (e.g., the ~7°C headroom noted in this project's own case-cooling result) is robust or fragile. (d) Monte Carlo wrapper around the existing deterministic solve (compute-heavy: hundreds to thousands of re-solves, though each individual solve is already fast per the existing tool) or a faster worst-case/RSS tolerance stack-up as a cheaper substitute.

**K6. Solver robustness near the fusing/runaway boundary.**
(a) The existing Picard fixed-point iteration for ρ(T) is noted as clamped for runaway detection; worth confirming convergence behavior is checked across a *sweep* approaching that boundary, not just at nominal operating points, since that's exactly where the nonlinearity is strongest and iterative methods are most prone to slow/false convergence. (d) Convergence-diagnostic sweep from nominal current up to the fusing threshold, checking iteration count and residual behavior, not just the pass/fail outcome.

---

## The board/world boundary (explicit synthesis)

Pulling the above into one coherent list of what crosses "the board" itself:

- **Airflow** (C1–C4, E1–E4): case fan field, local ho, neighboring-plume-elevated local air temperature, obstruction/wake geometry from cables and adjacent boards.
- **Neighboring hardware**: GPU/PSU as both elevated-ambient sources (E2) and physical/radiative obstructions (D3, F2).
- **Cables**: dual role as electrical conductors already modeled, and as unmodeled *thermal* conduction paths in/out of the system at input and output connectors (H2), plus mechanical strain-relief loading onto the joint (G6).
- **Mounting/chassis**: finite thermal mass and resistance rather than an ideal sink (H3), TIM interface quality as a function of real assembly torque and board warpage (G4/G5), plus parasitic conduction through mounting screws bypassing the intended TIM path.
- **Enclosures** (for enclosed products): a full nested-cavity conjugate problem (C5) with its own internal convection/radiation regime, sealed-vs-vented boundary condition (H5), and potential specular multi-reflection (D3).
- **The floating daughterboard specifically**: its *only* heat paths are back through the connector joint (G1/F3) and direct convection/radiation off its own small area (C2) — there is no dedicated heat-sink path by design, making the joint's contact-resistance fidelity and the local airflow/wake condition (E3) unusually load-bearing for that one assembly.

---

## Top 10 priorities for THIS application (ranked)

1. **Real airflow / forced-vs-still-air boundary condition (C1, E1).** Single biggest lever on the actual ΔT number — a uniform still-air assumption could be off by 3–10× in either direction depending on real case ventilation.
2. **Connector joint contact-resistance fidelity, force-coupled (G1, G2, J3).** The gate is built around per-joint verdicts on a connector class already flagged internally as sample-gated with unresolved retention/force questions; getting this wrong invalidates the headline result.
3. **Radiation heat transfer, currently entirely absent (D1, D2).** Plausibly 15–30% of total heat rejection in the still-air-dominated regime that currently gets zero credit or zero risk assessment either way.
4. **Complete heat-source inventory beyond shunts (B1).** LEDs, regulators, and MCU/transceiver dissipation are real, easily-overlooked, spatially concentrated sources the current model appears to skip entirely.
5. **Local ambient elevation from neighboring GPU/PSU (E2, H1).** These specific modules live physically closest to the two hottest things in the whole PC; a single global "configurable ambient" is the least realistic assumption for exactly this application.
6. **Connector housing as an insulating, air-blocking cavity around the hottest joint (F3).** Sits exactly at the gated element; a bare-joint-to-ambient assumption could be significantly non-conservative if the real joint is shrouded in low-k, low-emissivity plastic.
7. **Cable-conducted heat crossing the connector boundary (H2).** A real thermal path directly at the same interface the gate cares about, currently entirely unmodeled.
8. **Uncertainty quantification against the hard 30°C gate (K5, J1, A5).** A deterministic point estimate against a hard pass/fail threshold is only as good as its confidence level — worth knowing whether the reported margin is robust or a coin-flip under real manufacturing variance.
9. **Thermo-mechanical coupling at the floating daughterboard (G1, G6).** The specific friction-retained, no-dedicated-heat-sink mechanical architecture makes contact-force stability under thermal expansion and cable strain load unusually consequential here.
10. **2.5D-vs-3D and grid-convergence validation (K1, K2).** Cheap relative to the rest of this list, and it's the sanity check that everything else (including items 1–9) is even being computed on a numerically trustworthy foundation.

---

# Appendix B — blind report, electrical/EM/materials-reliability lens (verbatim)

# Blind Completeness Review: Electro-Thermal Solve for Consumer PC Power-Rail Instrumentation Boards

Reasoning from first principles only, given the stated scope (2.5D per-layer copper conduction, via barrel modeling, Joule self-heating with ρ(T) fixed-point, DC IR-drop field solve, discrete shunt heat sources, connector joint contact-resistance with two states, IPC empirical anchors, uniform-ambient still-air convection with one TIM/baseplate exception, steady-state only, 125%/30°C gate).

The current model is a solid **DC, steady-state, single-point-nominal, two-state-contact** electro-thermal solver. Everything below is either (1) frequency/time-domain physics it cannot see because it is DC/steady-state, (2) distributions it cannot see because it uses nominal point values, (3) failure/degradation trajectories it cannot see because it has no time axis beyond a single fixed-point iteration, or (4) the fact that the boards' own measurement fidelity depends on the very temperatures the solver computes, and nothing closes that loop.

---

## A. Electrical / EM effects — frequency-dependent and parasitic

**A1. Skin and proximity effect at ripple/transient frequencies**
(a) Frequency-dependent AC resistance rise in copper conductors and via barrels. (b) At DC the current fills the full cross-section; at the switching-ripple and transient frequencies riding on top of the DC rail (GPU VRM switching in the hundreds of kHz–low MHz, transient edges with µs rise times), skin depth in copper shrinks to tens of µm, and paralleled conductors (F.Cu+B.Cu mirrored lanes, paralleled shunts) redistribute current non-uniformly via proximity effect. (c) Materially changes answers wherever effective AC resistance exceeds the DC value used in I²R heating during the ripple/transient component of the duty cycle, and corrupts fast current reconstruction from shunt voltage. (d) Requires a frequency-domain (or time-domain FDTD/PEEC) extraction of AC resistance vs frequency for the relevant geometries, convolved with the real current spectrum; compute class: 3D quasi-static EM solver per critical geometry, not full-board.

**A2. Parasitic inductance and impedance-based (not resistance-based) transient current sharing**
(a) Every trace, via, and blade connector carries parasitic inductance. (b) The steady-state model splits current across parallel vias/blades by DC resistance (or geometry) ratio; under fast di/dt this is wrong — current splits by *impedance*, and the lowest-inductance path (often the geometrically shortest or outermost one) carries a disproportionate share of any fast transient. (c) This matters exactly where the design assumes N parallel current-carrying elements share load "evenly" (via clusters, multi-blade joints) — a transient can concentrate well above 1/N share on one member even though the DC/RMS budget looks fine. (d) Requires PEEC or partial-inductance extraction per parallel-path cluster, driven by a real di/dt current source, feeding a local transient thermal-capacity check (see H2).

**A3. True 3D current crowding at geometric discontinuities (the 2.5D→3D gap)**
(a) Per-layer 2.5D lateral solve with via-barrel-only vertical coupling structurally cannot resolve 3D current crowding at connector pad-to-blade transitions, via breakout fillets, and shunt terminal solder fillets. (b) Current density peaks locally at these 3D discontinuities well above the layer-averaged value the 2.5D solve reports. (c) This is precisely where real high-current-connector designs fail in the field (localized melting at a single pin/pad, not across a whole plane) — a 2.5D min-cut model can show comfortable margin while a 3D corner hotspot is already near fusing. (d) Requires locally-refined 3D FEM (current-density + Joule heating) at each identified "critical joint" from the min-cut analysis — not full-board 3D, just targeted sub-domains; moderate compute (per-joint FEA, seconds–minutes each).

**A4. Magnetic coupling between adjacent current loops (crosstalk into Kelvin sense loops)**
(a) Mutual inductance between adjacent shunt/current loops on multi-cable boards (e.g., a 3-cable PCIe daughterboard). (b) A fast di/dt in one cable's loop induces a differential-mode voltage in a neighboring Kelvin sense loop via mutual coupling, independent of any real current in that neighbor. (c) Corrupts instantaneous current reading on adjacent channels specifically during a transient on one channel — a measurement-integrity issue that looks like real current if uncorrected. (d) Requires mutual-inductance extraction (PEEC/loop-area based) between all near-parallel high-current loops and Kelvin sense loops; low-to-moderate compute.

**A5. Fast-transient local hotspot vs the sustained-I²R gate**
(a) A sub-ms current spike at a thin bottleneck (a min-cut neck, a small via) can locally exceed the *instantaneous* current-density-to-fusing threshold even when the RMS/sustained average is well inside the 125% gate. (b) Local thermal mass at a thin feature is small, so its local time constant is short — it can track a fast transient's peak far more than the bulk average implies. (c) Matters most at exactly the features flagged by the min-cut analysis as narrowest (documented in this codebase as recurring: "single-layer narrow lane" neck findings). (d) Requires the transient current-sharing model (A2) coupled to a local lumped thermal-capacitance model per bottleneck feature, evaluated against real GPU/CPU transient current traces, not the DC design-basis scalar.

**A6. EMI / ground-bounce / common-mode coupling into sense circuitry**
(a) Switching noise from the GPU VRM and PSU couples capacitively/inductively into sense traces and ADC references. (b) Not a thermal effect, but corrupts the readings the "instrument" produces, especially during exactly the high-di/dt events the thermal model cares about. (c) Matters whenever fast-transient current measurement is the deliverable (transient-visibility ladder / FREEZE trigger features in this class of design). (d) Requires a signal-integrity/EMC simulation (common-mode injection, CMRR-vs-frequency of the sense amplifier) — separate discipline from the thermal solve but shares the same current-transient stimulus.

---

## B. Materials science and aging

**B1. Electromigration in vias and thin traces**
(a) DC current stress in copper conductors, most severe in the narrowest features (thin via barrels, the "lane corridor" single-layer segments). (b) Sustained current density near or above safe electromigration thresholds causes void nucleation/growth at grain boundaries over months–years, raising local resistance and eventually opening the conductor. (c) Matters at every via/trace the min-cut analysis flags as near its density ceiling — over product life (years), not at t=0, the margin can erode even if today's DRC/thermal check passes. (d) Requires Black's-equation-class lifetime prediction fed by the min-cut current-density map; needs an assumed activation energy and current-density exponent for PCB copper (less standardized than IC electromigration data — a real data gap).

**B2. Solder-joint thermal fatigue (Coffin-Manson)**
(a) CTE mismatch between copper/solder/component at solder joints (shunt terminations, connector THT joints, via barrel-to-pad transitions). (b) Daily PC power-on/off cycling plus load-driven ΔT cycling flexes these joints; cumulative low-cycle fatigue cracks the solder over years. (c) Matters most at the *highest-ΔT* joints identified by the thermal solve itself (the shunt solder fillet typically sees the largest local ΔT swing) — this should be a direct consumer of the thermal solve's own output, not a separate spec check. (d) Requires Coffin-Manson (or Engelmaier) fatigue-life calculation using the actual per-joint ΔT cycle amplitude/count from a realistic mission profile; low compute, but needs joint-specific ΔT time series, which requires H1 (transient thermal model) as a prerequisite.

**B3. Intermetallic compound (IMC) growth and joint resistance drift**
(a) Cu-Sn intermetallic layers grow at solder interfaces over time, accelerating with temperature (Arrhenius). (b) IMC is more resistive and brittle than either parent metal; joint resistance rises slowly over years, and joint fatigue life drops. (c) Matters at every solder joint in the sustained-high-temperature power path (shunt terminals, connector THT barrels) — a joint that meets item 7 (contact resistance) "spec nominal" at manufacture is not the same joint at year 3 in a warm case interior. (d) Requires Arrhenius-accelerated IMC thickness-vs-time model with resistance-vs-IMC-thickness correlation (published Cu-Sn IMC growth kinetics exist; less commonly tied to resistance for exactly this kind of joint — some data-gap risk).

**B4. Connector contact-spring stress relaxation / creep — the thermal-runaway feedback loop**
(a) Blade-clip retention normal force depends on the spring temper of the clip material (phosphor bronze/beryllium copper typical). (b) Sustained elevated temperature (from the joint's own I²R heating) relaxes the spring via creep, permanently reducing contact normal force; lower normal force → higher contact resistance → more local heating → more relaxation. (c) This is a genuine **positive feedback loop** and is arguably the single most safety-relevant omission for a blade/clip-connector design carrying tens of amps continuously in an enclosed product — it converts a marginal-but-passing joint at t=0 into a runaway joint at year 2–3, exactly the failure mode publicly documented in other high-current PC-power blade/latch connectors. (c-cont) Materially changes the answer whenever the joint's calculated ΔT is a meaningful fraction of the clip alloy's stress-relaxation-onset temperature at the design's continuous-duty timescale (years). (d) Requires the clip alloy's stress-relaxation curve (force retention % vs temperature vs time) coupled back into the two-state contact-resistance model as a continuous function of the joint's own computed operating temperature and elapsed time — i.e., the *contact resistance model must consume the thermal solve's own output as a feedback input*, not run as an independent nominal/worn pair.

**B5. Fretting corrosion / plating wear at vibration-exposed contacts**
(a) Micro-motion (chassis vibration, fan vibration, thermal-cycling-induced micro-slip) wears through thin tin/gold plating at the contact interface, exposing base metal to oxidize. (b) Progressive contact-resistance increase, distinct from and additive to B4. (c) Matters for any board mounted where vibration reaches the connector (fan-adjacent, case-panel-adjacent) over years of service. (d) Requires a vibration-exposure assumption (from PC chassis mounting) and a fretting-corrosion resistance-growth model (empirical, vendor-connector-specific — typically only available from connector qualification data, another data-gap risk).

**B6. Shunt resistor long-term drift (independent of TCR)**
(a) The resistive element and its terminations undergo slow permanent resistance drift from internal stress relaxation, independent of the reversible TCR effect already implicitly needed for measurement (see G1). (b) Manifests as a slow multi-year calibration bias, typically specified as a "long-term stability" datasheet parameter (e.g., ppm/1000 hr at rated power). (c) Matters for the instrument's long-term calibration accuracy claim, not for thermal safety margin. (d) Requires the shunt vendor's long-term-stability spec integrated over the device's power-on hours at its actual (thermal-solve-computed) operating temperature, since stability specs are usually rated-power/rated-temperature dependent.

**B7. Tin whisker growth / electrochemical migration**
(a) Pure-tin or near-pure-tin finishes can grow conductive whiskers over years, and dense high-field-gradient areas under humidity+bias can dendritically migrate. (b) Low probability but non-zero risk of an unplanned short. (c) Relevant mainly to the *unenclosed* vs *enclosed* product distinction called out in this design family (dust/humidity exposure differs) — should be a materials-finish decision informed by, not corrected by, the thermal solve. (d) Qualitative risk flag rather than a numeric model; informs finish selection (matte Sn vs SnPb vs Ni-underlayer) rather than the thermal solve itself.

**B8. FR4/laminate property drift approaching Tg under sustained elevated temperature**
(a) FR4's mechanical and CTE properties change as operating temperature approaches its glass-transition temperature. (b) Increases CTE mismatch-driven via-barrel fatigue stress (feeds back into B1/B2) and can locally soften the laminate near the hottest features. (c) Only matters if the thermal solve's peak local temperatures approach the laminate's Tg minus margin — worth an explicit check against the actual laminate spec, since standard FR4 Tg (130–140°C) is not infinitely far from the fusing/runaway temperatures already being flagged in this design's own review notes. (d) Simple check: compare solve's peak local temperature against laminate Tg with margin; if margins are thin, feed into B1/B2 fatigue-rate acceleration.

---

## C. Manufacturing variability and tolerances

**C1. Copper thickness / etch-factor tolerance vs the as-drawn cross-section**
(a) Fabricated copper thickness has real tolerance (commonly ±10–20% depending on IPC class) and etch undercut narrows trace width from the drawn value. (b) The min-cut cross-section the solve uses is the *nominal drawn* geometry, not the as-built one. (c) Directly threatens margin at exactly the narrowest, most bottlenecked features the min-cut analysis already flags as tight — a design passing at nominal cross-section by a small margin could fail at the process's low-tolerance corner. (d) Requires either a worst-case corner run or (better) a Monte Carlo draw of copper thickness/etch-factor per layer, feeding the existing min-cut solve (see F1).

**C2. Via barrel plating thickness variability**
(a) Electroplated copper in via barrels has manufacturing variance, worse at high aspect ratio (deep/narrow vias plate thinner at mid-barrel — the "dog-bone" effect). (b) As-built via resistance/cross-section can differ meaningfully from the nominal value the solve assumes. (c) Matters most for the current-carrying via clusters already identified as thermally significant (item 2 in the existing list) — this is the manufacturing-tolerance twin of that item, currently treated as deterministic. (d) Requires plating-thickness-vs-aspect-ratio process capability data from the fab, applied as a distribution (or minimum-guaranteed IPC-6012 class value) rather than nominal drawn drill/pad geometry.

**C3. Solder joint void content at shunt and connector terminations**
(a) Wave/reflow solder joints have IPC-class-acceptable void content that constricts the actual current-carrying and heat-conducting path through the joint. (b) A joint within IPC acceptance can still have meaningfully reduced effective cross-section vs the "solid" nominal assumption. (c) Matters at the discrete high-current joints (shunt terminals, connector THT) where the whole point of the model is to catch marginal joints. (d) Requires either X-ray/void-content sampling data fed as a statistical derating factor on joint conductance, or a conservative IPC-acceptance-limit void assumption in the joint model.

**C4. Connector mating tolerance / contact-force stack-up**
(a) Actual contact normal force and wipe distance depend on the full dimensional tolerance stack-up of blade thickness, clip jaw geometry, and insertion depth — this design family's own review notes flag a real measured tolerance concern (blade thickness vs clip design-center). (b) The current model's "spec nominal + worn scenario" is a bimodal simplification; real assembly-to-assembly variability in as-mated contact resistance is continuous, not two points. (c) Matters directly for whether a given assembled unit sits near the "worn" state *on day one* rather than only after years of service — i.e., the two states should really be endpoints of a distribution, not a binary choice. (d) Requires a contact-resistance-vs-normal-force model (from connector vendor characterization or bench measurement) combined with a Monte Carlo draw over the tolerance stack-up (see F1); ties directly to the open "sample fit-check" item already flagged as owner-gated in this design family.

**C5. Shunt resistor batch tolerance (R, TCR, thermal EMF)**
(a) Even within a graded tolerance class, real production lots show correlated variation in resistance, TCR, and parasitic thermal-EMF beyond the single datasheet nominal. (b) Feeds directly into measurement accuracy (G1/G4) as well as the I²R heat-source calculation (item 6). (c) Matters for both thermal margin (a slightly-high-R shunt in a hot corner of the tolerance band dissipates more) and instrument accuracy simultaneously. (d) Requires lot-sampling data or a manufacturer-supplied distribution (not just min/max) for Monte Carlo propagation.

---

## D. Degradation / reliability physics — life-trajectory modeling

**D1. Continuous time-dependent contact-resistance trajectory**
(a) A single function R_contact(t) driven by the combined mechanisms in B4/B5/B3, rather than the current two-state (nominal/worn) model. (b) Captures the actual shape of degradation (is it linear? does it accelerate? is there a knee?) which matters for warranty-period risk assessment. (c) Matters whenever the design's continuous-service life (years, always-on PC) is long enough for creep/fretting/IMC growth to materially move the joint away from its as-built state — which for a continuously-powered PC accessory is essentially guaranteed. (d) Requires combining B3/B4/B5 kinetics into one time-domain reliability model, ideally driven by an assumed real mission profile (hours/year powered, ambient distribution, vibration exposure) rather than a lab-bench single point.

**D2. Electromigration void-growth kinetics at flagged hotspots (Black's equation)**
(a) Time-to-failure prediction (median life + distribution) for the specific vias/traces the min-cut analysis flags as highest current density. (b) Converts a static "passes DRC today" result into "expected service life before this feature is at risk." (c) Matters specifically for the narrowest engineered features (thin lane corridors, small-diameter high-current-carrying vias) called out elsewhere in this design line as tight by design choice. (d) Requires Black's equation parameters calibrated (or conservatively assumed) for PCB copper geometries — a genuine literature/data gap versus IC electromigration, where this is well characterized.

**D3. Mission-profile-based reliability synthesis (physics-of-failure MTTF)**
(a) Combine every degradation mechanism above (B1–B8) into an overall predicted failure-rate/MTTF for the power-path components specifically, using a real PC usage mission profile (power-on hours/year, ambient histogram, thermal-cycle count/year). (b) Gives a defensible answer to "what's the expected life of this joint/via/shunt in a real PC" rather than a pass/fail snapshot. (c) Matters for warranty and field-return-rate planning, and for deciding whether any single mechanism above dominates and deserves disproportionate design margin. (d) Requires either a MIL-HDBK-217-class parametric model (crude but standardized) or a bottom-up physics-of-failure synthesis of the individual mechanism models above (more accurate, much more compute and data-dependent).

---

## E. Fault and off-nominal scenarios

**E1. Loss of one member of a parallel current-carrying cluster**
(a) The design uses N parallel joints/vias per rail by design (documented ratified joint counts per cable/connector class in this design family). (b) If one via cracks, one blade partially unseats, or one joint's resistance rises sharically (per D1) to effective open, the remaining N−1 paths must carry the full current — re-solve current redistribution and check the survivors against both the sustained 125% gate *and* transient/fusing thresholds on the now-higher-stressed survivors. (c) Matters as a genuine safety case: the whole rationale for N-way redundant joints is defeated if a single-failure re-distribution isn't checked — an N-1 path might individually be fine at 1/N current but not at 1/(N−1). (d) Requires re-running the DC IR-drop/min-cut solve with each single element (and plausible double-element) removed in turn — an N-choose-1 (and optionally N-choose-2) sensitivity sweep on top of the existing solver; moderate compute (existing solver run N times).

**E2. Partial-seat / high-resistance single-point contact (assembly-defect scenario)**
(a) A blade not fully seated in its clip (marginal insertion depth, contamination, tolerance-stack-up outlier) creates point contact rather than full-face contact, with resistance far above even the "worn" nominal. (b) Concentrates essentially all the joint's heat into a tiny contact spot with poor local heat-spreading. (c) This is the textbook mechanism behind publicized high-current-connector melting incidents in adjacent products (partial mate → localized resistance → localized runaway) and is directly relevant given this design family already carries an open "sample fit-check" item on exactly this connector interface. (d) Requires a localized-contact-spot thermal model (small contact-patch heat source into the blade/clip thermal mass, not a uniform-joint-resistance assumption) parameterized by insertion-depth/mate-quality as a variable, swept from nominal to worst-plausible-but-passing-mechanical-inspection.

**E3. Unequal current sharing across nominally-parallel pins/cables (contact-resistance-variance driven)** — *the dominant real-world failure mode for this connector class*
(a) When multiple pins/cables are assumed to carry an equal share of a rail's current (as the design-basis "X A/pin × N pins" sizing does), real per-pin/per-cable contact resistance is never identical — small resistance differences across "parallel" current paths cause genuinely unequal current sharing, and the highest-resistance path (which, perversely, is also the one most likely to be degrading per B4/B5) draws *less* current only if resistances differ purely resistively; under real per-pin driver-side impedance and cable-length variance, the opposite can also occur. (b) This exact mechanism (unequal per-pin sharing driven by contact-resistance variance) is the root cause publicly attributed to the 12VHPWR/12V-2x6 connector melting incidents in the wider industry — i.e., not a hypothetical for this specific application, but the known failure mode of the connector class this design directly uses and derives from. (c) Materially changes the answer anywhere the model currently assumes an even A/pin split for sizing joint counts and gate margins — a "125% of *average* per-pin current" gate can still allow one real pin to sit at 160–200% of average under plausible contact-resistance mismatch. (d) Requires a current-sharing model driven by a *distribution* of per-pin/per-cable contact resistance (from C4/C5) solved simultaneously (a resistor-network solve, not an assumed even split), with the gate re-evaluated against the resulting worst-single-pin current, not the average.

**E4. Fault/surge current transient (I²t withstand) beyond the steady 125% gate**
(a) A PSU or GPU fault event (short, VRM failure, hot-plug arc) can dump a large fault current for a brief duration far above the sustained design basis. (b) The existing gate is steady-state 125% of sustained current; it has no concept of a short-duration high-magnitude pulse's I²t energy absorption. (c) Matters for personnel/fire safety, not routine operating margin — a board that never has trouble at 125% sustained can still be at risk from an unmitigated fault-current pulse if nothing upstream limits it fast enough. (d) Requires an I²t withstand rating for every conductor/joint in the fault current's path (from manufacturer let-through data or IPC-2152 pulse correlations) compared against the actual fault-current magnitude/duration expected from the upstream PSU's protection characteristics — a transient thermal-capacity check, not a steady-state one.

**E5. Degraded-cooling boundary conditions**
(a) The current boundary condition is uniform fixed ambient + still-air natural convection (with one board's TIM/baseplate exception). (b) Real PC interiors see dust accumulation reducing effective convection, fan failure removing case airflow the "still air" assumption may already be optimistically better than actual, and case-internal ambient that rises with GPU/CPU load rather than staying fixed. (c) Matters because the 30°C-rise gate's absolute pass/fail depends heavily on the ambient assumption, and real field ambient is a distribution, not a constant — a board margin-passing at a lab-bench 25°C ambient can be much closer to the edge at a realistic 40–45°C loaded-case interior. (d) Requires either CFD-informed convection coefficients for realistic case airflow scenarios, or at minimum a swept/distributed ambient boundary condition rather than a single fixed value (ties to F1/F3).

**E6. Wear-then-fault combined scenario**
(a) Repeated connector mate/unmate cycles (a plausible field scenario — GPU swaps, cable management) wear plating per B5, and *then* a subsequent high-current event occurs on the now-degraded contact. (b) Combines an aging trajectory with an off-nominal load event — neither pure aging-at-nominal-load nor pure fault-at-nominal-contact-resistance captures this. (c) Matters for enthusiast/DIY users who re-seat connectors more than the "install once" assumption. (d) Requires composing D1 (contact resistance vs mate cycles) with E4-style fault/high-load analysis at the degraded resistance value rather than the as-built one.

---

## F. Statistical treatment

**F1. Monte Carlo propagation of all tolerance and aging distributions**
(a) Replace the single deterministic pass through copper thickness, via plating, contact resistance, shunt tolerance/TCR, and ambient temperature with distributions for each, propagated through the existing solver. (b) Produces a margin *distribution* (e.g., a Cpk or 3σ/6σ confidence that the 30°C-rise gate is met) instead of a single binary pass/fail on nominal inputs. (c) Matters because several of the tolerance sources above (C1–C5) can individually shift margin by double-digit percentages, and their combination could turn a comfortably-passing nominal case into a design that fails at a real, non-negligible fraction of manufactured units. (d) Requires wrapping the existing steady-state solver in a Monte Carlo (or at least a structured worst-case-corner DOE) outer loop; compute cost scales with sample count × existing per-run cost — the single largest compute-class increase on this list, but the most direct way to actually answer "does this meet the gate" with confidence rather than just "at nominal."

**F2. Sensitivity / global importance analysis**
(a) Rank which input distribution (copper thickness? via plating? contact resistance? ambient?) dominates the margin uncertainty computed in F1. (b) Turns a Monte Carlo result into an actionable design/process lever (e.g., "tighten via plating spec" vs "the copper tolerance barely matters"). (c) Matters for cost-effective margin improvement rather than blanket over-design. (d) Requires a Sobol/variance-based or simpler one-at-a-time sensitivity sweep on top of F1's Monte Carlo runs; modest additional compute given F1 is already running.

**F3. Statistical (mission-profile-derived) worst-case current instead of a fixed design-basis scalar**
(a) The current "sustained worst case" (e.g., a design-basis A/pin figure) is a single engineering judgment number. (b) Real GPU/CPU current draw is a stochastic time series; the relevant "worst case" for a *sustained*-rating gate should really be something like a 99.9th-percentile sustained-window statistic derived from real load traces, not a single assumed constant. (c) Matters because the entire 125%-of-sustained-worst-case gate is only as good as that worst-case number's fidelity to actual field usage. (d) Requires real (or credible synthetic) GPU/CPU power-draw time-series data, processed into a percentile-based sustained-current statistic — an input-data acquisition task as much as a modeling one.

---

## G. Measurement / instrumentation physics — closing the temperature↔accuracy loop

The solve computes real temperatures at real locations on the board. **Nothing in the current list feeds those temperatures back into what the board's own sensors report.** For an *instrument*, this is arguably the largest single gap, because a design can pass every thermal-safety gate while silently reporting current/voltage numbers that are wrong by a material percentage under exactly the conditions (high sustained load, hot board) the user most needs accurate data.

**G1. Shunt TCR-driven reading error as a function of the solve's own computed shunt temperature**
(a) Shunt resistance shifts with temperature per its TCR spec; both self-heating (already computed, item 6) and ambient rise shift it away from the calibration-time value. (b) Every °C of shunt temperature rise not compensated in firmware directly appears as a proportional current-reading error. (c) Matters most exactly under the sustained-high-current conditions the thermal solve is built to characterize — i.e., the instrument is least accurate precisely when the user most wants to trust it. (d) Requires taking the solve's own per-shunt temperature output and running it through the shunt's TCR spec to produce an explicit %-error number, checked against the system's stated accuracy budget — a direct, cheap consumer of existing solver output that is currently not connected to anything.

**G2. Current-sense amplifier drift with temperature**
(a) Input offset voltage drift, gain drift, and CMRR degradation vs temperature and common-mode voltage, per the sense IC's datasheet. (b) Compounds with G1 in the total measurement error budget. (c) Matters more at the IC's *local* temperature (which includes its own self-heating, see G5) than at a generic board-ambient figure. (d) Requires the datasheet drift coefficients applied at the solve's computed local temperature at the IC's actual placement, not a spec-sheet room-temperature accuracy number.

**G3. ADC / voltage-reference drift vs temperature**
(a) Reference TCR and ADC INL/DNL both shift with temperature. (b) Adds a further term to the total measurement uncertainty budget, and interacts with any ratiometric-reference compensation scheme already in use. (c) Matters at the reference/ADC's actual computed board location and temperature, not a generic spec figure — especially relevant where a ratiometric scheme is used specifically to cancel *some* of this drift, since its residual error still depends on real temperature. (d) Requires component-level TCR/INL data applied at the solve's local temperature output for that specific board location.

**G4. Thermal EMF (Seebeck) error at dissimilar-metal junctions in the Kelvin sense path**
(a) Any temperature *gradient* across a junction of dissimilar metals (solder/copper/resistive-alloy shunt element, connector blade/clip material pairs) generates a parasitic thermoelectric voltage directly in series with the signal being measured. (b) At the µV-level shunt voltages typical of low-value current-sense resistors, thermal EMF can be a non-trivial fraction of full-scale signal — and it is directly, causally driven by the same thermal gradients the solve computes across the board. (c) Matters most for the lowest-value shunts (the highest-current rails) and for any Kelvin path spanning a real ΔT between its two ends — precisely the situation the electro-thermal solve is built to characterize but currently reports nothing about. (d) Requires Seebeck-coefficient data for the actual dissimilar-metal pairs at each junction in the sense path, applied to the solve's own computed ΔT across that junction — again, a direct, previously-unused consumer of existing solver output.

**G5. Current-sense IC self-heating coupled into the local board thermal field**
(a) The sense IC dissipates its own (small but nonzero) power and has a package thermal resistance (θJA/θJC) to the local board. (b) Its actual junction temperature is board-local-ambient (from the main solve) *plus* its own self-heating rise — not simply the board-average temperature the "discrete heat sources" treatment (item 6) implies for shunts. (c) Matters because G2/G3's drift coefficients should be evaluated at the IC's *own* temperature, which can run measurably hotter than nearby board copper if it sits near a hot shunt or high-current pour. (d) Requires modeling the sense IC as an additional discrete heat source (small, but with its own θJA) superimposed on the local board field the main solve already produces — a small addition to the existing item-6 framework, not a new solver class.

**G6. Sense-path bandwidth vs real di/dt — can the instrument even see what the model computes?**
(a) The full sense chain (shunt inductance/ESL, amplifier bandwidth, ADC sample rate/multiplexing) has a finite bandwidth. (b) If that bandwidth is below the frequency content of real transients (A2/H2), the instrument physically cannot resolve the fast events whose thermal risk this whole exercise is trying to characterize. (c) Matters as a systems-level sanity check: there's limited value in a highly detailed transient thermal model if the product's own sensors are blind to the transients being modeled — worth explicitly stating as a scope boundary. (d) Requires comparing the sense chain's actual bandwidth/sample rate against the frequency content of the transient current profiles used in H1/H2 — a straightforward systems check, not a new physics model.

**G7. Long-term calibration drift (aging × instrumentation coupling)**
(a) Combines B6 (shunt long-term stability) and IC/reference long-term drift specs with the device's actual accumulated thermal history (from D1's mission profile). (b) Answers whether the instrument stays within its stated accuracy spec over years of field use without recalibration, not just at t=0. (c) Matters for any accuracy claim made about the product over its warranty/service life. (d) Requires integrating component long-term-drift specs over the device's actual time-at-temperature history as computed by the (now transient, per H1) thermal model.

---

## H. Dynamic / transient thermal-electrical modeling (steady-state → time domain)

**H1. Transient thermal-RC response to real load time-series**
(a) The solve is steady-state only; GPUs/CPUs draw highly dynamic, bursty current with duty cycles ranging from sub-second gaming-load spikes to sustained multi-minute compute loads. (b) Real copper/FR4/connector thermal mass low-pass-filters instantaneous power, so peak instantaneous current does not map 1:1 to peak temperature — but a high-duty-cycle burst pattern can still *ratchet* average board temperature above what a naive "average current" steady-state calculation would predict, depending on the ratio of burst period to the board's thermal time constant. (c) Matters anywhere the actual field current profile isn't well-approximated by a single constant "sustained worst case" — which, for GPU/CPU rails, is essentially always. (d) Requires converting the existing steady-state solver into (or wrapping it with) a lumped or distributed thermal-RC network (using real copper/FR4/connector thermal capacitance) driven by representative real or synthetic GPU/CPU power traces over representative mission windows (seconds to minutes); compute class: time-domain FEA/lumped-network simulation, meaningfully heavier than the existing fixed-point steady solve but not full 3D transient FEA if a calibrated lumped-RC reduction of the existing 2.5D model is used.

**H2. Frequency/impedance-dependent transient current sharing (see A2)** — listed here again because it is the electrical *input* that H1's thermal model needs: without knowing how a fast transient actually splits across parallel conductors (by impedance, not DC resistance), the local hotspot risk (A5) that a transient thermal model would reveal can't be correctly located. (d) Requires PEEC/impedance extraction (A2) feeding directly into the H1 transient thermal network as the true per-path current-time input, rather than an evenly-split assumption.

---

## I. Boundary-condition / heat-path completeness (rounding out the thermal model itself)

**I1. Radiative heat transfer**
(a) At board temperatures in the 70–100°C range (well above ambient), radiation to cooler surrounding surfaces (case walls, other components) is a non-trivial fraction of total heat rejection — commonly 15–30%+ in still-air enclosures. (b) The current convection-only (plus one board's TIM/baseplate) boundary condition likely overstates temperature rise somewhat by omitting this path, or understates it if surface emissivity/finish assumptions are wrong. (c) Matters most for the *enclosed*-product variants explicitly called out in this design family, where radiative view factors to a cooler metal case wall are a real, calculable heat-rejection path. (d) Requires adding a radiative boundary term (view-factor + emissivity-dependent) to the existing boundary condition, especially for enclosed-product configurations; moderate addition to the existing thermal solve.

**I2. Non-uniform, geometry/orientation-dependent convection & realistic case airflow**
(a) The current "uniform ambient, still-air natural convection" boundary condition uses a single convection coefficient regardless of board orientation, local geometry, or the fact that most PC cases have *some* airflow from other fans even in a "passive" configuration for this specific board. (b) Natural-convection correlations are strongly geometry/orientation dependent, and any incidental case airflow substantially changes effective h vs true still air. (c) Matters for the absolute accuracy of the 30°C-rise number, which is the entire pass/fail gate — a systematically optimistic or pessimistic h changes every verdict on this list. (d) Requires either CFD (for a real case geometry) or at minimum orientation/size-corrected empirical natural-convection correlations (Churchill-Chu class) rather than a single flat h, plus a documented "worst realistic case-airflow" scenario alongside the nominal one (ties to E5).

**I3. Chassis/standoff conduction path for every board, not just the one with TIM/baseplate**
(a) Every board is mechanically mounted to a metal chassis via standoffs/mounting hardware, which is itself a conduction heat-rejection path (however small) beyond board-plane conduction and convection/radiation to air. (b) Currently modeled for only one board in the family. (c) Matters proportionally more for smaller/denser boards where standoff conduction is a larger fraction of total heat rejection relative to board convective surface area. (d) Requires extending the existing TIM/baseplate conduction-path methodology to every board's actual mounting-hardware thermal resistance, even where it's a secondary (not primary) path.

**I4. Cable/harness thermal coupling at the connector boundary**
(a) The "far side" of every connector joint is a length of cable/wire harness that itself self-heats under sustained current and thermally loads the joint from the other direction. (b) The connector joint's boundary condition currently presumably treats the far side as a fixed or simplified thermal sink; in reality cable self-heating raises that boundary temperature under sustained high current, reducing the joint's effective heat-sinking. (c) Matters at every high-current connector interface, particularly under the sustained-worst-case condition the whole gate is built around. (d) Requires a simple cable self-heating model (wire gauge, insulation, bundle effects) providing a realistic (not fixed-ambient) boundary temperature at each connector joint, rather than treating the joint as if its far side always sits at ambient.

---

## Top 10 Priorities for THIS Application (ranked)

1. **E3 — Unequal current sharing across nominally-parallel pins/cables driven by real contact-resistance variance.** This is the actual documented failure mechanism behind melting incidents in the exact connector class (high-current blade/multi-pin, assumed-even-split) this design derives from — the single highest safety-relevance gap on the list.

2. **E2 — Partial-seat / high-resistance single-point contact.** The other half of the same real-world failure class; directly relevant given this design family's own still-open connector fit-check item, and the mechanism (localized ignition-risk hotspot from an assembly-tolerance outlier) is not captured by a two-state nominal/worn contact model.

3. **B4 — Contact-spring stress relaxation/creep thermal-runaway feedback loop.** The physical mechanism that converts a marginal-but-passing joint at manufacture into a field failure years later; without closing this loop, a "passes at t=0" result says nothing about year 2–3, and the design is continuously-powered.

4. **H1 — Transient thermal-RC response to real GPU/CPU load profiles.** The steady-state-only assumption is a poor match to the actual load class (bursty, highly dynamic); without it, neither peak-instantaneous nor duty-cycle-ratcheted temperature risk is assessed at all.

5. **A2/H2 — Impedance-based (not DC-resistance-based) transient current sharing across parallel paths.** Directly threatens the assumed-even-split logic behind every "N parallel joints/vias" design decision in this family the moment a fast transient (not steady load) is considered.

6. **E1 — Single parallel-path-element failure and current redistribution.** The whole rationale for N-way redundant joints is only as good as its behavior when one member degrades or fails; currently unassessed.

7. **G1/G4 — Shunt TCR error and thermal-EMF error as explicit functions of the solve's own computed temperatures.** These boards are instruments; the thermal solve already computes exactly the temperatures and gradients needed to answer "how wrong are the readings under load," and currently nothing consumes that output for accuracy — a nearly-free extension of existing solver output with high user-facing relevance.

8. **F1 — Monte Carlo propagation of tolerance/aging distributions.** A single-nominal-point pass at a 30°C/125% gate says little about the confidence that the *population* of manufactured boards meets it; this is the difference between "the design passes" and "we know what fraction of units pass."

9. **C1/C2 — Real manufacturing tolerance on copper thickness and via plating vs as-drawn nominal cross-section.** Directly threatens the credibility of the existing min-cut analysis at exactly the narrow, already-tight features this design line repeatedly identifies as bottlenecks.

10. **E4 — Fault/surge I²t withstand beyond the steady-state 125% gate.** The only item on this list addressing genuine electrical-fault safety (as opposed to routine operating margin) — a board can pass every steady-state and transient-load check above and still be unassessed against a PSU/GPU fault-current pulse.