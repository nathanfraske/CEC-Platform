# Pipeline solver & improvement roadmap (standing answer)

_Owner ask (2026-07-08): "leave [the scoped solvers] in an easy to find place for when I ask
'what other solvers can we add, or what improvements can we make to the pipeline' again."
THIS IS THAT PLACE. Update it whenever a solver/improvement lands or a new one is scoped;
memory entry [[pipeline-solver-roadmap]] and FOLLOWUPS point here._

## Solver inventory — what the loop has TODAY (2026-07-08)

| Solver | Where | Backend | Status |
|---|---|---|---|
| 2.5D thermal field solve (per-layer conduction, via coupling, sub-grid traces) | `cec_thermal2d.py` via `_oracle_thermal` | GPU cupy CG/AMG, scipy fallback | GATING (with the mirage guard: dT≈0 fail + double-solve confirm). **Known defect: non-deterministic** — root-cause open (FOLLOWUPS; pyamg `ml.solve` returns unconverged iterates flagless, dT swung 21↔174 on one artifact) |
| Analytic electrothermal (IPC-2221 Picard, serial min-cut cross-section, per-via split) | `cec_synth_pipeline.electrothermal_solve` | CPU closed-form | Lumped fallback / synth-pipeline gate |
| Closed-form Z0/Zdiff (Hammerstad-Jensen + edge-coupled approx) vs the committed stackup | `cec_impedance.audit_impedance` | CPU instant | ADVISORY (landed 2026-07-08). First finding: USB netclass = 91.3Ω vs 90 target (+1.4%, validated); **CAN = 91–105Ω vs 120 target platform-wide** (fine at 500k; the 1Mbps option's SI bench would care) |
| Kelvin loop-area (∫separation·dl along routed force/sense pairs) | `cec_impedance.audit_kelvin_loops` | CPU instant | ADVISORY (landed 2026-07-08; calibrate bands before gating) |
| Crosstalk parallel-run proxy (sense victims vs rail/switching aggressors, same layer ≤0.4mm, <15°) | `cec_impedance.audit_crosstalk` | CPU instant | ADVISORY (landed 2026-07-08) |
| GND-fanout synthesizer (per-GND-pin via, IMPEDANCE-REDUCING ONLY) + audit | `cec_gnd_fanout.py` | CPU | Teeth-verified standalone; recipe wiring queued (FOLLOWUPS) |
| RUDY congestion grid / corridor model / pair-skew / min-pour-cross-section | `cec_router` / `cec_score` / `cec_constraints` | CPU geometric | In the loop |

## Scoped, NOT yet built — ranked by leverage

1. **PDN / IR-drop / TRUE ground-impedance map** (the big synergy). The same Laplacian
   machinery as `cec_thermal2d` solves the DC voltage field: swap thermal conductivity for
   electrical σ, heat sources for pad current injections → per-pad voltage drop + a real
   impedance-to-ground map. Directly implements the owner's "only if it reduces the
   impedance to ground" (replaces `cec_gnd_fanout`'s nearest-entry distance heuristic with a
   measurement) and gives rail IR-drop margins. GPU-ready on the existing cupy CG/AMG
   backend; grids identical to thermal. **PREREQ: root-cause the thermal solver
   nondeterminism first — shared backend.** Effort: days (mostly reuse).
2. **SPICE — LANDED 2026-07-08 (pilot)** (`cec_spice.py`, owner GO). ngspice ships in the
   KiCad image; behavioral cells; sec6.13 detection-chain pilot teeth-verified (trip exact
   vs analytic; 5VSB saturation 2.599A refines the 2.64A hand math; MC band 3.7%).
   REMAINING: per-board R/C extraction from the real netlist (values are spec-side
   constants today), more cells (dividers/REF/hold-up ladder), checklist/MEASURE wiring.
   Original scope, kept for context: ngspice (apt-installable in the container) simulating the
   analog cells against reality: the §6.13 detection chain (shunt → INA181 gain → TLV7011 +
   THRESH PWM-DAC: does the trip threshold land where firmware expects?), dividers + RC
   filter corners, REF ratiometrics, hold-up ladder — WITH MONTE CARLO over R/C tolerances
   (the hand gain-saturation analysis for the 5VSB INA181A2, done by a solver instead).
   Runs once per SCHEMATIC change (the MEASURE/ERC_BOM stage), not per placement candidate —
   CPU-cheap. **Friction (the honest cost): vendor models.** TI ships PSpice-encrypted
   models for INA181/INA238/TLV7011 that ngspice cannot run → the cells need behavioral
   macromodels (VCVS + GBW for the CSA, behavioral comparator) built + validated against
   datasheet numbers once. What SPICE is NOT: a board/field solver — it knows no layout
   geometry; board-side value only arrives when fed extracted parasitics (see #1/#3).
   Pilot: the 24-pin rev3 4-rail detection chain. Effort: 1-2 days incl. macromodels.
3. **2D electrostatic cross-section field solver** (atlc-style) for EXACT Z0/Zdiff of
   routed geometry — arbitrary cross-sections, solder-mask aware, replaces the ±10%
   closed-form coupled term. Reuses the cupy CG/AMG backend; small grids, GPU-trivial.
   Build when Max-tier LVDS work starts (AD9253→GW5A @1.6Gbps — the family's first truly
   impedance-critical link). Effort: days.
4. **Partial-inductance / loop-L estimator** upgrade of the loop-area advisory (Rosa/Grover
   closed forms on the sampled loop) — feeds §6.13 transient front-end + EMC arm. Hours.
5. **AC skin-effect resistance for shunt/force paths** (marginal — near-DC sensing). Low.

### Placer port question (owner asked 2026-07-08: Rust + CUDA?)

PROFILED (build/profile_placer.py, cProfile on the 24-pin synth): placement = ~3.9s of a
~124s candidate (~3%) — a Rust/CUDA port does NOT move wave latency; FR (Java, 71-95%) is
the wall. The hot spot is ONE function: `legalize_pack.cost()` = 92% of placement time
(629k calls, 94M pure-Python abs() calls of AABB arithmetic; the anneal itself is 0.28s).
Rungs, cheapest-first:
1. **numpy-vectorize `legalize_pack.cost()` — MEASURED 2026-07-08** (prototype
   `scripts/cec_legalize_fast_proto.py`, record/replay bench on 38 REAL calls, 2 boards x
   2 seeds): **12.3x on the 24-pin (3.27s -> 0.27s), 5.5-5.8x on eps, 100% output-identical**
   (positions <1e-9, residuals equal — the argmin/first-zero semantics match sequential).
   Integration queued post-wave-13 (code freeze).
2. **cupy the same arrays** = GPU batch evaluation (the arrays are identical) — matters
   only at rung-3 scale.
3. **Rust/CUDA placer = a SEARCH-SCALE lever, not a latency port**: thousands of parallel
   anneal chains + batched AABB cost would change the wave's SHAPE (screen 1e4-1e6
   placements by proxy, route only survivors — seed spread IS the fuel, 2026-06-30
   finding). Justified only when the pipeline is placement-QUALITY-bound after the FR
   levers (REST reuse, pre-route screen) land. Exploratory; revisit when a wave's best is
   placement-limited rather than routing-limited.

### Co-coordinating router (owner ask 2026-07-08: paths aware of each other; GPU?)

**PROTOTYPED + MEASURED** (`scripts/cec_coord_router_proto.py`): PathFinder-style
NEGOTIATED-CONGESTION global router — every net's cost includes every other net's
present-sharing + history (the literal "each path aware of the other attempts" mechanism,
VPR lineage). All-nets-simultaneous (N,H,W) wavefront relax; same code numpy/cupy.
On the REAL wave-12 board (180 two-pin connections, 118x141 grid @0.5mm):
**GPU 15.3s vs CPU 123.9s = 8.1x, identical results** — and the GPU time is still
dominated by HOST-side per-iteration path recovery (sequential Python + device->host
copies), so the recoverable ceiling is much higher. The owner's GPU instinct pays again
(the thermal-solve precedent). NOT converged in 20 iters (residual overuse 1693) — the
capacity model is naive (cap=1/cell; pad cells counted as overuse). NEXT: capacity ~2
traces/0.5mm cell + pad-cell exclusion + GPU path recovery (batched greedy descent) +
more iters; then OUTPUT = per-net corridors + congestion map compiled into FR bake_hints/
keepouts (FR keeps detailed routing — this COORDINATES it, replacing nothing). Cheap
sibling rung: wave-level coordination — aggregate completed variants' unrouted/congestion
loci into later candidates' hints (the "mappings feedback" backlog item).

## Pipeline improvements — non-solver (same standing list)

- **Thermal solver nondeterminism root-cause** — the one KNOWN-DEFECT gate. Repro scripts
  `build/probe_thermal_repeat*.py`. (FOLLOWUPS, top priority before any new backend user.)
- **GND-fanout recipe wiring** — `cec_gnd_fanout.synthesize()` between pour synthesis and
  final fill/DRC + audit as advisory verdict field. (FOLLOWUPS; teeth done.)
- **Oracle checker consolidation** — ~15-20 redundant `pcbnew.LoadBoard`s + 2 mergeable
  kicad-cli DRC spawns per candidate (~1.5-2.5s/candidate measured). (FOLLOWUPS.)
- **Freerouting REST server wiring** — `docker-freerouting-1` idle 3 weeks;
  `CEC_FREEROUTING_URL` env exists, `cec_fr` never reads it. Session reuse + live progress
  → stage-0 pre-kill becomes possible. Large. (FOLLOWUPS.)
- **Pre-route gate screen** — placement-only gates could skip the FR route (71-95% of
  candidate cost) for doomed placements; costs failure-ranking fidelity. Opt-in design
  sketched. (FOLLOWUPS.)
- **Role-keepout lever ablation** — mechanism landed inert; needs the fixed-seed
  cec_lever_eval protocol to activate. (FOLLOWUPS.)
- **Intent-seat lifecycle formalization** — proposals currently steer the next wave only;
  fold their W/L record into the actuation-lever clean-evidence tally
  (docs/actuation-lever-design.md) so a repeatedly-winning proposal class can graduate.
- **Pour lever** — make copper pours first-class MUTABLE actuation objects (a `PourPlan` the
  placer asks for and the router rebuilds/notches on FR feedback), replacing today's one-shot
  stateless post-route synthesis and killing the box-model duality debt as a side effect. SCOPED
  (5-stage plan, DRAFT awaiting owner review): docs/pour-lever-scoping-2026-07-08.md.

## Decision log

- 2026-07-08: cheap wins built (`cec_impedance.py`); PDN + 2D-electrostatic + SPICE scoped
  (this doc); owner seat policy for in-loop agents = cec-worker-quality nothink (measured
  18.5s warm vs gpt-oss 628s + an invented-region proposal); vision = tool-fed, excessively
  sparing, winner-only advisory.
