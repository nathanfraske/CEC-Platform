# Pipeline solver & improvement roadmap (standing answer)

_Owner ask (2026-07-08): "leave [the scoped solvers] in an easy to find place for when I ask
'what other solvers can we add, or what improvements can we make to the pipeline' again."
THIS IS THAT PLACE. Update it whenever a solver/improvement lands or a new one is scoped;
memory entry [[pipeline-solver-roadmap]] and FOLLOWUPS point here._

## Solver inventory — what the loop has TODAY (2026-07-08)

| Solver | Where | Backend | Status |
|---|---|---|---|
| 2.5D thermal field solve (per-layer conduction, via coupling, sub-grid traces) | `cec_thermal2d.py` via `_oracle_thermal` | GPU cupy CG/AMG, scipy fallback | GATING. Nondeterminism defect FIXED 2026-07-17 (unconverged-iterate guards + determinism golden `tests/test_thermal2d_determinism.py` — the PDN prereq is CLEARED). Injection accounting added 2026-07-22 (`nets_requested/dropped/absent` on every stamp; a dropped configured net = FAIL "INJECTION INCOMPLETE" — kills the partial-injection mirage where an OPEN rail read cooler than a routed one) |
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
1. **numpy-vectorize `legalize_pack.cost()` — LANDED (f23b6d7, 2026-07-08)**: synth_one
   3.9s -> 0.83s, output-identical proven twice (38 recorded calls proto + 11/11 in-tree
   fast-vs-`_legalize_pack_seq`). Original measurement: 12.3x on the 24-pin legalize calls.
2. **cupy the same arrays** = GPU batch evaluation (the arrays are identical) — matters
   only at rung-3 scale.
3. **Rust/CUDA placer = a SEARCH-SCALE lever, not a latency port**: thousands of parallel
   anneal chains + batched AABB cost would change the wave's SHAPE (screen 1e4-1e6
   placements by proxy, route only survivors — seed spread IS the fuel, 2026-06-30
   finding). Justified only when the pipeline is placement-QUALITY-bound after the FR
   levers (REST reuse, pre-route screen) land. Exploratory; revisit when a wave's best is
   placement-limited rather than routing-limited.

**2026-07-10 scoping verdict (owner ask "should we write a shader for the placer"): NO —
and not close.** Post-vectorization placement is ~0.8s of a 45-300s candidate (<2%; FR
measured medians from `build/worklog.jsonl` n=784: eps 44.7s, pcie-2 71s, 24-pin 199s,
12vhpwr 241s). The placer's remaining pure-Python hot loop is `anneal_macros.cost()`
(O(parts) AABB scan per move x 2500 moves, ~0.3s) — numpy-vectorizing IT is the cheap
rung that buys 10-50x MORE anneal iterations in the same wall (a packing-QUALITY lever,
same trick as legalize). The GPU-batch-anneal search-scale case is real but double-gated:
(a) the wave currently FR-routes every variant (no proxy prune), so generating 100x more
candidates buys nothing until the prune/adjudicate split is wired into `cec_fresh_wave`
(`place_candidates`+`adjudicate_candidates` exist, `hub_pipeline_run` uses them, the wave
driver bypasses them); (b) the cheap proxy doesn't predict routability (the documented
false-summit). Packing-CORRECTNESS levers found the same pass: `place_edge` has NO
edge-fit check (overflowing connector sets silently run past the board edge — reproduced
in a unit test), the anneal has no rotation move (needs rotated cluster templates), and
`params["anchor_roles"]` reached `_classify` but not `seed_anchors` edge seating (the
12vhpwr J3/J4 side-column bug, FIXED 2026-07-10 w/ regression tests). Dead code:
point-relaxation `legalize()` has zero callers.

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

**STATUS 2026-07-10 (scoping re-audit): built, gated, and the gate says NO — shelve
pending a redesigned hint form.** The production build (`scripts/cec_coord_router.py`,
002be14) is complete per its design (capacity model, terminal exemption, 2-layer+via,
H/V bias, pres ramp, chunked negotiation, best-so-far, GPU-resident descent) and honest:
residual floors ~130 (eps) / ~500 (24-pin), and CHUNKING trades the un-chunked 8.1x GPU
batch win down to **1.73x at production settings** (its own commit message). The T3
bridge (`scripts/cec_coord_hints.py`) + pinned-seed A/B exist and RAN: **the A/B gate
FAILED TWICE** (`build/coord_ab_result.out`, `build/coord_ab_reactive.out`: verdict
A-BETTER-OR-EQUAL; reactive arm unconn 96->101, drc 104->109 — locked mid-corridor stubs
stole FR freedom it didn't need help with). Tension to keep visible: the owner
blind-picked the COORDINATED arm against the metrics (build/coord-blind key, G13). Next
variant if revived: advisory keepout-avoidance instead of locked stubs, fewer nets.
DURABILITY GAP: the teeth (`build/teeth_coord_router.py`) and both A/B verdicts live in
gitignored `build/` — promote to `tests/`/docs before any revival. **Shader verdict: a
fused relax RawKernel (+ dropping the per-sweep `xp.all` host sync) could plausibly take
the GPU leg 12.8s -> 1-2s, but do NOT write it until a hint form passes its own A/B gate
— it would optimize a component that currently loses.**

### GPU runtime reachability + the shader question (2026-07-10 scoping pass)

**Finding: every GPU path is currently UNREACHABLE — the whole pipeline silently runs CPU
fallbacks.** cupy AND pyamg are absent from the persistent `docker-routing-1` container
(and the host); the base `docker/Dockerfile.routing` never installed them (only
numpy/scipy/requests), they were only ever runtime-`pip install`ed into live containers
and lost on every recreate (bit us 2026-06-20, 07-08, 07-09/G14 — matplotlib/shapely
same class). Consequence today: `cec_thermal2d` falls PAST GPU-AMG and PAST CPU-pyamg-AMG
all the way to plain scipy Jacobi-CG (~4260 iters @217k cells vs AMG's ~10-15) — solves
still complete, just 10-100x slower, with no warning. The GPU recipe itself is committed
and proven: `docker/Dockerfile.routing-gpu` (cupy-cuda12x==14.1.1[ctk] + pyamg, the [ctk]
extra is REQUIRED for sm_120 Blackwell JIT, ~153s one-time warmup measured 2026-06-16) +
`docker/compose.gpu.yaml` overlay (nvidia device reservation + BLAS thread caps); the
built `cec/routing:gpu` image (8.98GB) is still on disk; nvidia-container-toolkit
verified working against the 5090 (compute cap 12.0) on 2026-07-10. Durable fixes (in
order): (1) bake pyamg+matplotlib+shapely into the BASE `Dockerfile.routing` (restores
CPU-AMG, the biggest win per the 2026-06-20 note "the win was AMG, not the GPU") --
**LANDED 2026-07-11** (Dockerfile edited; base-image rebuild picks it up, and the :gpu
image chains FROM it); (2) add the `:gpu` image build + overlay mention to
`ops/provision.sh` (today a disaster-rebuild silently drops the GPU path) -- **LANDED
2026-07-11** (step 5b builds cec/routing:gpu); (3) never runtime-pip into the container
again. GPU container STOOD UP 2026-07-11 (compose.gpu.yaml overlay live: cupy 14.1.1 +
pyamg 5.3.0 + 5090 visible in docker-routing-1). The unconverged-iterate guard also
landed same day (see the defect note in the table).

**Shader (custom CUDA kernel) verdicts by engine:**
- **FEM/thermal — the only engine where kernel work is even pending.** The V-cycle apply
  is already GPU (library ops); the remaining bottleneck is pyamg's CPU setup, and the
  half-built answer is `scripts/cec_gmg_bench.py`: matrix-free GEOMETRIC multigrid with a
  hand-written red-black Gauss-Seidel **cupy RawKernel** (i.e. the shader already exists
  in prototype), Galerkin coarse ops (hand-rediscretized coarse ops DIVERGED — recorded
  in-file). No committed verdict yet. ORDER OF OPERATIONS: fix the solver nondeterminism
  first (capture `residuals=` at `cec_thermal2d.py:546` + reject unconverged + precond
  staleness rebuild, ~1h — the 2026-07-10 FEM audit's #1), bake the deps, THEN decide GMG.
  Note thermal is currently lazily SKIPPED in waves (gate=False short-circuits → dT=None
  on every recent candidate), so GPU thermal buys the fine-density/deepen regime and
  gate-passing boards, not today's wave latency.
- **Router — no.** FR is external Java (can't shader it; its levers are REST reuse +
  effort targeting + the prune). Our own coord router is cupy-capable but fails its A/B
  gate (above) — a fused relax kernel is future work gated on a hint form that wins.
- **Placer — no** (see the placer-port verdict above: <2% of candidate cost; the levers
  are anneal-cost vectorization, packing-correctness fixes, and the prune/adjudicate
  split — all CPU-cheap).

## BGA-READINESS (owner directive 2026-07-23: "we have multi-BGA chip boards coming up, so something's gotta give to get it better at figuring out routing/placements")

Context: the current stack (FR 1.7.0-cec2 + deterministic pre-lay + the wave) strains on a
108-part hub with 2 signal layers; the upcoming board class (ENT PolarFire MPFS095TC on
FCVG484 = 484-ball 0.8mm BGA, ESP32-P4 hubs/Pro modules) is a different league — BGA
escape/fanout, 6+ layer stackups, length-matched buses. The measured lesson of this month
points ONE direction: every durable win came from moving copper OUT of the stochastic
router INTO the deterministic plane (locked rails, authored cells, pour compiler, tap
synthesis). FR's role has been shrinking toward "jellybean interconnect only" — and that is
exactly the right shape for BGA work, because BGA fanout is the MOST deterministic routing
there is (dogbone/via-in-pad patterns per ring, escape channels per quadrant are formulaic).

Rungs (owner picks funding order; A+B are the recommendation):
- **A. BGA fanout/escape generator on the deterministic plane** (build): per-ring dogbone +
  escape-channel synthesis as locked copper (the authored-cell pattern generalized), stackup-
  aware (ring depth -> layer assignment), emitted pre-FR exactly like rails/cells today. FR
  then routes only channel-to-channel interconnect. This is OUR proven pattern and no
  external router does it better than a generator can.
- **B. Escape-aware placement terms** (extend the wave): courtyard/escape-corridor
  reservation around BGA macros (the walk-band lesson generalized), per-quadrant fanout
  budget as a placement score term. Without this the placer will park jellybeans in escape
  channels and no router survives it.
- **C. Router re-evaluation for the interconnect residual** (evaluate, don't assume): FR
  2.x fork surgery (we already maintain a fork; the 2.2.4 blockers — normalize hang, no
  seed axis — are patchable in principle), KiCad 10 IPC-API scripted routing (kipy — no
  headless P&S exposure today, watch upstream), commercial/ML (DeepPCB-class) as a paid
  benchmark only. Gate any adoption on the FR-01-style epoch protocol (byte-determinism,
  bench parity, seed diversity).
- **D. Stackup/DRU authoring for 6-layer** (prereq for A): layer-pair plan + via classes
  (blind/buried decision is a SPEC/owner item), netclass coverage synthesized from the
  schematic role map instead of hand patterns (the 2026-07-23 pattern-coverage gap made
  the case).

Sizing note: A+B are weeks-scale on the existing codebase (the cell/rail machinery is the
harness); C is open-ended and should trail A/B since the interconnect residual shrinks as
the deterministic plane grows.

## Pipeline improvements — non-solver (same standing list)

- **ACTUATION-SPACE DEEP DIVE (owner ask 2026-07-08, orchestrator's own analysis):
  docs/actuation-space-2026-07-08.md** — the organizing insight (pass-form SHRINKS
  problems until stronger tools apply) + ten actuations: staged-FR via DSN net-tiering
  (machinery exists), FR minimal patch set (seed flag kills the measured ±30 noise —
  the honest 'rewrite FR' answer), snag->constraint compiler, hand-cell extractor,
  GUI-parity locks, milestone-gated residual router, per-region exact placement,
  GPU batch anneal, kipy zone ops, per-pass blind hooks. Ranked shortlist inside.

- **PASS-FORM PLACEMENT+ROUTING (owner directive 2026-07-08, THE structural redesign):
  docs/pass-form-plan.md** — ordered passes w/ progressive locking, per-pass teeth,
  precision-first routing (kelvin/pairs/pours deterministic + protected, FR residual-only
  = TPC generalized into the active pipeline), the blueprint cell primitive. Research
  base: industry pass list + repo self-mining (headline: TPC exists, proven, and the wave
  pipeline bypasses it). Staged S1-S5.

- **Thermal solver nondeterminism root-cause** — the one KNOWN-DEFECT gate. Repro scripts
  `build/probe_thermal_repeat*.py`. (FOLLOWUPS, top priority before any new backend user.)
- **GND-fanout recipe wiring** — `cec_gnd_fanout.synthesize()` between pour synthesis and
  final fill/DRC + audit as advisory verdict field. (FOLLOWUPS; teeth done.)
- **Oracle checker consolidation** — ~15-20 redundant `pcbnew.LoadBoard`s + 2 mergeable
  kicad-cli DRC spawns per candidate (~1.5-2.5s/candidate measured). (FOLLOWUPS.)
- **Freerouting REST server wiring — LANDED 2026-07-22, as the CEC FORK server** (owner
  directive: REST serves our 1.7.0-cec2 jar, not the official 2.x image, which is a
  different router behind a freerouting.app auth wall and binds 127.0.0.1 as shipped).
  `scripts/cec_fr_server.py` job API executes `cec_fr.run_freerouting` per job (all env
  knobs + plateau-kill + tree-kill identical); `cec_fr` reads `CEC_FREEROUTING_URL`
  (route verdicts re-raise, infra falls back to local loudly; `CEC_FR_REST=0` opts out);
  compose `freerouting` service = the server, `CEC_FR_SERVER_WORKERS=6` is the box-wide
  FR concurrency governor. PROVEN: REST-vs-local SES byte-identical (eps), SB-08 golden
  through REST = identical pre-existing signature, 12 contract tests. Not built: warm-JVM
  reuse (1.7.0 is batch-mode) and richer server-side pre-kill policies.
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
- 2026-07-10 (scoping pass, owner ask "shader for router/placer/FEM + placer parallelization
  /packing"): NO shaders now anywhere — FEM first fixes determinism + dep-bake (GPU currently
  unreachable everywhere, silent CPU fallback), coord-router kernel gated on a hint form that
  passes its A/B (two losses recorded), placer <2% of candidate cost. Throughput levers ranked
  instead: (1) wire prune→adjudicate into cec_fresh_wave (~8x fewer FR calls), (2) FR REST
  reuse (server idle 3 weeks), (3) merge ~20 redundant per-candidate LoadBoards + 3-4 DRC
  spawns, (4) board-level wave concurrency w/ global JVM cap, (5) anneal-cost vectorization
  for packing quality. FEM completeness audit delivered (see §FEM in the 2026-07-10 handoff /
  scoping report): physics-rich, gate-worthy only with the mirage guard; #1 = the residuals
  fix. Placer packing-correctness: seed_anchors role_overrides gap FIXED (12vhpwr J3/J4),
  place_edge fit check + rotation-move templates queued.
