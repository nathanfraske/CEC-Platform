# Current work handoff

## (G8) ROUND-2 IMPLEMENT QUEUE LANDED + SPEEDUP PASS — 2026-07-08 ~15:30 (branch claude/pipeline-consolidation)
ALL 7 G7 implement-queue items landed, each teeth-verified in-container (calibrations REPRODUCED
from the probes, not trusted): (1) PIN-ESCAPE gate boxed0<=4%/le1<=12% (hand 0/0, committed eps
1.71/6.86, fresh 9.06/23.02 FAILS) 411c0c9; (2) COURTYARD-EDGE native-DRU physical_clearance gate
0.8mm floor, exemptions J/H/M/FID/MK/SW/TB/TP/DL/LOGO + ESP32-by-value (antenna-at-edge = hand
pattern) 411c0c9; (3) SILK score/fp = tier-0 sort_key tie-break (hand 0.18-0.43 vs fresh 4.5-5.3)
a8c0c8b; (4) FACING-FRACTION advisory (does NOT separate universally: committed eps 13.7 < fresh-eps
37.5 — advisory only, drives future face() lever) 1e90823; (5) ROUTE-SANITY advisory: per-net detour
<=6.0 + via budget max(10,2*pads) exempting zoned+force nets (12vhpwr lane stitching 10/3-pad,
/SB_CBL_PRES 8; synthetic 53.8x meander + 41-via chain FAIL) 5c8e231; (6) FIDUCIALS: materialize now
EMITS the planned FID1-3 (they were dropped — every fresh board shipped 0!) + quality gate count>=3/
clear>=1.5mm/non-collinear, N/A-without-expect so SB-08 golden unmoved, sabotage teeth 223b95a;
(7) GAP-PROFILE advisory (true-polygon side-filtered; NO bimodality stat was ever computed — the
round-2 read was an eyeballed histogram, committed eps is a counterexample; robust pattern = fresh
non-touching p75<=0.75 vs hand 1.08-1.25) + ROLE-KEEPOUT anneal lever role_clr (soft cost, never
veto), INERT unless params role_keepouts set — activation = fixed-seed cec_lever_eval ablation
(FOLLOWUPS) 24d1461.
SPEEDUP PASS (a1fefe4, profiling scout measured: wave FULLY SERIAL, FR=71-95%/candidate, 24-pin
wave 49.5min/24, checker suite 14.5s): (a) PARALLEL candidate loop (spawn pool, intents re-derived
by name; default 6 workers — the "4-core container" was OMP_NUM_THREADS=4 masking nproc, ALL 18
cores available; CEC_WAVE_WORKERS=1 = comparability runs); verified 4 variants/27.8s at w=2.
(b) LAZY THERMAL (owner directive): solve ONLY when every other gate term passes (would-be winner);
gate=True impossible without a real solve; failing candidate 21.7->4.5s. Silk joins the lazy skip.
(c) THERMAL MIRAGE GUARD — the owner's instinct MEASURED REAL: identical solves returned dT
119/103/174 (GPU) and 0.0/20.8/20.9 (CPU-forced; dT=0 would have gate-PASSED); pyamg path has no
convergence flag. Guard: dT<=0.05 = FAIL + any would-be pass needs a 2nd agreeing solve (worst-of-2
reported). Hand 12vhpwr still passes (23.68). SOLVER root-cause = FOLLOWUPS (probe_thermal_repeat*).
KNOWN CONSEQUENCE: wave-1 eps winner now FAILS the bar (D2 at 0.0mm edge + stranded C9/D2) — eps
wave re-run queued (FOLLOWUPS). GPU/agents answer (owner q): GPU = thermal solves only, during
waves (CEC_THERMAL_GPU_MIN_N=60000 recipe env; idle between); wave loop is FULLY deterministic —
no LLM seats in it; local seats all stopped; exploration panels are where agents run (cost policy:
local-first, workflow agent() calls MUST set model: explicitly — fable-inherit near-miss recorded
in agent-cost-policy memory).

## (G7) OWNER LEVER PASSES — 2026-07-08 evening (branch claude/pipeline-consolidation)
STRICT-ZERO reached earlier (bodies-in-pours 0 x8 seeds, lane pours + fingers, no exemptions).
WAVE 10 (full lane arch, code freeze): best 38 unconn (179->76->55->38), top-6 packed 38-41,
foreign 0. OWNER LEVER PASS 1 (all teeth-verified, committed): gates kelvin-reach(9mm pre-route),
courtyard-overlaps(hard DRC), circuit-completeness(island BFS + fill-on-demand; answers the
owner's FEM question — the solve never checked connectivity), stranded-parts(22mm calibrated,
SW/TP/DL access classes exempt); levers near()/order() intents (inert-unused), SWAP anneal move
(rotate REMOVED — unsound for rot-0 cluster offsets), output-row CENTERING (margins 6.7/6.8),
rigid BOOT/RESET pair (4.5mm), REPAIR_LADDER (6 rungs, pair-separation last). WAVE-10 KELVIN
BLOCKER FIXED: seat INA-filter (rail-sided pairs swept in the mux; all 4 INA181s now 3.8mm,
reach gate green). EXPLORATION ROUND 2 (3 lenses, opus/sonnet) verified findings:
IMPLEMENTED: pour-family + DFM checkers wired ADVISORY (both mis-fire on controls — pour-present
name-matches /DET12V; DFM counts 94 on shipped 12vhpwr; calibration owner-queued) + zone-
connection override assert (gate-ready). TO IMPLEMENT (calibrated, high-value): (1) PIN-ESCAPE
gate — 8-dir 0.3mm corridor probe, <=10-pad fps, hand boards 0.00% vs fresh 23% boxed (all the
sense front-end); (2) COURTYARD-EDGE clearance via NATIVE DRU physical_clearance rule (bbox proxy
false-flags rotated courtyards — the agent PROVED it); fresh has MCU at 0.025mm from edge; floor
1.0mm, hand 12vhpwr tolerates 0.84 (calibration floor); (3) silk score/fp (hand 0.18-0.32 vs
fresh 4.48); (4) facing-fraction metric (drives the backlogged face() lever; hand 29-36% vs fresh
19%); (5) meander ratio + via budget score terms; (6) fiducial quality gate; (7) nearest-gap
bimodality score + role-based variable keep-out lever. NEGATIVE CONTROLS (do NOT pursue):
same-net span, alignment grids, rotation discipline — measured non-separating. BACKLOG STILL:
repeated-cell template, ratline heatmap, corridor-at-scoring, thermal-proxy weight, F/B side +
face() intents, rigid-group legalize. Wave 11 after the implement queue drains.

## (G6) LEVER LANDINGS — 2026-07-08 mid-AM (branch claude/pipeline-consolidation)
ABLATION-DRIVEN, one at a time, multi-seed medians (scripts/cec_lever_eval.py, 8 placements):
LEVER 1 COMMITTED: CAN transceiver seats at the link jack, exempt from anneal + ALL eviction
rounds (can_j1 54.7 -> 4.3mm). LEVER 3 COMMITTED (the big one): RIGID-CLUSTER RE-STAMP -- the
instrumented trace proved evac/mop move a cluster OWNER after its passives were stamped at the
OLD position (U5: 57.4 -> 9.5 -> 32.5 while R52/R53 stayed) = THE root cause of ALL cluster
scatter (decouplers, dividers, ILIM); ownership was never broken (3 inert ownership fixes).
Re-stamp at final owner positions + pour-aware settle: div 31.7 -> 4.7mm, caps 12/34.4 ->
11/25.2. CONTRACT: explicit partition assignment BEATS seat bias (teeth test); 24-pin intents
exclude the CAN from the core sweep. RESIDUALS: (a) box-model unification (settle avoids
placement-time topo boxes, gate checks materialized straddle boxes -- ~10 bodies-in-pours on
eval boards, TODO); (b) comparator distances unchanged (needs the INA181 seat slide lever);
(c) divider-lever variants + fix-B veto still parked in build/wip-*.patch (veto needs a
move-into-region repair path). WAVE 7 RUNNING (refined intents + all levers + 5 craft gates).
EPS NOTE: lever 1 + re-stamp change CABLE-board placements too (eps partition tests updated
expectations hold 47/47; craft gates will re-rank eps fresh candidates on the next eps wave).

## (G5) PLACER-LEVER BATCH — parked 2026-07-08 (ablation required)
Fix A (anchor-vs-anchor J1 clamp) COMMITTED ✓ (J1 overlaps 6->0). Comparator-adjacency gate +
hot-sensitive recalibration COMMITTED ✓. The four-lever batch (fix B containment veto,
divider-pair ownership, CAN-at-connector seat, decoupler re-seat + _park_near) REGRESSED all
metrics when landed together (caps 34->50-56mm, CAN 42->52mm) -- REVERTED, parked as
build/wip-placer-levers.patch (161 lines). Next agent: land ONE lever at a time with the
fixed-seed probe (sense-band intent, compact-s0, measure decoupler/comparator/CAN/divider
distances between each). Mechanism insights: pour-eviction vs electrical adjacency (parking
must dodge pour boxes AND the mop must exempt deliberate seats); containment veto needs a
repair path (move-into-region), else the anneal freezes bad states. Owner-queue: 2 ratified
checker recalibrations pending sign-off.

## (G4) PLACEMENT CAMPAIGN — state at 2026-07-08 early AM (branch claude/pipeline-consolidation)
OWNER PIVOT: "routing is absolutely not the issue... the placer pipeline is always the bottleneck."
LANDED: placement-CRAFT gate terms in the oracle conjunction (calibrated on hand boards, teeth
both ways): decoupler-adjacency <=7mm functional (old eps winner correctly fails -- C1 stranded
62mm), USB/CAN pair skew <=4mm from routed copper, bodies-in-pours HARD gate (fresh-board domain;
hand boards governed by pour-integrity instead). craft_gates=False pins the oracle-mechanics
tests (fixture predates standard; re-freeze follow-up). cec_render: silk OFF everywhere + 3D
bodies at any depth (KIPRJMOD rewrite; RELAYER never Remove -- segfault footgun). Wave 6
(6 intents x 2 strats x 2 seeds): STRUCTURED INTENTS SWEEP TOP 4 -- sense-band-compact-s0 wins
76 unconn @8 passes vs 78 @20 for generic (structure > effort, quantified), foreign 0 everywhere.
EXPLORATORY WORKFLOW (4 dims, verified findings): FIX-NOW BUGS: (1) anchor-vs-anchor collision
UNCHECKED (J1 courtyard swallows sense row + DETECT pin 0.4mm from U11 pads = pre-route short;
legalizer only checks movable-vs-anchor; oracle path never runs the courtyard check); (2) anneal
does NOT enforce region containment (pre-seed + post-clip only -- the anneal undoes intents).
LEVERS TO BUILD: repeated-cell template primitive (hand 12vhpwr: 6 cells at EXACT 17.00mm pitch;
fresh: 5VSB comparator 40.9mm away cross-face); near(X,Y)/face(dir) first-class intents;
along-axis slide in kelvin seat (the INA238 LO-tap blocker); explicit F/B side pin; order() wired
to j_in_pins (computed, never read); swap + rigid-group anneal moves. MAPPINGS UNUSED: corridor
model not consulted at placement scoring; RUDY + unconnected-ratline heatmaps never fed back;
thermal proxy excluded from weights. Divider-pair primitive + connector-local protection affinity
(DETECT D1/R1 41-56mm vs hand 9-14mm). OPUS fundamentals leg running (haiku invented 'overpacking'
-- owner rejected; tier policy updated in agent-cost-policy.md: threshold-producing legs = sonnet
min, opus when gating). PROSE-FIRST discipline (owner flagged silent turns).

## (G+++) 24-PIN ESCALATED REVIEW — state at 2026-07-08 night (branch claude/pipeline-consolidation)
ROLE (owner): I am the ESCALATOR TIER — pipeline halts get diagnosed + fixed by me. Wave 5 (24
variants, ALL unconn 123-187) was the halt; a 30-agent diagnosis workflow (adversarially
verified; NOTE: it sampled a STALE 100x84 artifact, so cross-check numbers, mechanisms were
code-level and valid) + instrumented FR probes drove 6 fix rounds, each committed + on the dash
(tag=fix, cec_escalator_probe.py renders every round like wave variants):
R1: phantom kelvin pair (fabricated /SENSE5V_LO -> gate unpassable; _derive_pairs existence
guard); In2 unroutable (power-KIND layer -> FR refused; inner_power_routing param: In1 GND
plane + In2 'PWR_RT' signal); wrong-shunt corridors (any-2-pad grabbed caps; straddle-first +
RS guard); board-spanning rail boxes (ATX interleave; _x_clusters fan-in per pin group);
dual-sided keepout layer inversion (per-pair B.Cu). R2: same-layer cross-net pour clip.
R3: FR seed pinned in measurements (±30 noise discovered). R4: same-NET zone clip (abutting
tiles); kelvin_sense_pins exclusion UNCONDITIONAL (slid 8mm seats escaped 6mm radius -> FR
routed sense CROSS-FACE, caught by the new sense-side gate); tap reach 6->9. R5: INNER-POUR
architecture (rail pours on In2 + synthesize_force_vias) — placement effect PROVEN (unconn
114->74 @p8) but FR integration incomplete (In2 keepouts don't bind: 116 foreign; stubs need
_tap_foreign_clear: 37 shorts) -> PARKED behind CEC_INNER_POURS=1 (FOLLOWUPS.md). R6 = the
shipping state: face pours, foreign 0/0, unconn ~78@p20 / ~114-132@p8 (fr-seed variance),
thermal dT~45-66 (gate 30; rail currents still cable-class 40A default — config needed).
TRAJECTORY: 179 -> 78 best. REMAINING to gate-clean (priority): (1) inner-pour FR integration
(bake_hints/DSN keepout on inner layers + guarded stubs) — biggest lever; (2) GND fanout
synthesizer (19 isolated F.Cu SMD pads, workflow-verified warranted); (3) placement iteration
(INA181 seats 16-23mm off their shunts; D_USB1-on-U11 pileup; rail-column-vs-pin-group order);
(4) 24-pin rail currents for the thermal gate (manifest config; 40A default over-gates).
Probe harness: scripts/cec_escalator_probe.py; artifacts build/escalator/atx-24pin-rev3/.
COST POLICY (owner, recorded in agent-cost-policy.md): panels LOCAL-first (cec-worker-quality
go-to; deepseek = heavy judgment only, slow); cloud agents cheapest-that-works; fable = exception.

## (G++) 24-PIN OWNER BATCH — 2026-07-08 late (branch claude/pipeline-consolidation)
ALL owner directives landed + committed: J_SIG1 2x5->1x4 (study item 5 CLOSED, no sense-return;
pin order = db J20: 1=-12V 2=PS_ON# 3=PWR_OK 4=GND; alignment contract = collinear with blade
row, pad1 one field pitch past last slot); J3 mouth-out (repair-only rotation flip in
seed_anchors — flips ONLY when default leaves body inboard; eps byte-identical, ablation-proven);
buttons cluster opt-in (buttons_near=usb manifest key); board size 70x55 (owner: too large);
blade row_y pad-extent repair. CRITICAL FIND: U5 (TPS2121) NEVER PLACED on fresh seeds — RUX0012A
+ CEC_12V2x6 footprints were old-format (fp_text) so place() regexes missed position+reference;
kicad-cli fp upgrade fixed. Battery 116/116. Per-side taps/pours DONE earlier (all 4 rails,
straddle-aware cec_fr defaults, 8 sites); sense-side oracle gate DONE (analog-across-faces,
fail-closed, N/A single-sided). WAVE 4 RUNNING (fresh-wave-24pin-4.log, effort 8/10/1200s,
per-variant dash snapshots incl. back-face on new best). Probes seed..seed10 build/24pin-probe/.
NEXT: wave 4 verdict -> iterate placement (known: D_USB1-on-U11 pileup class); shrink pass once
gate-clean; eps 40A envelope copper (mirror pours) queued.

## (G+) 24-PIN MECHANISM PACKAGE — state at 2026-07-08 late (branch claude/pipeline-consolidation)
Items LANDED (each committed + on the dash feed): (a) shunt-straddle kelvin pairs BOTH sites
(+12vhpwr lane-6 /FAN_12V regression caught, gate strengthened, 127/127); (c) J3 role
(pad-majority + force-aware); (f) antenna keepout dropped end-to-end (placer+materialize
consistent, 0 courtyard overlaps); rounded corners/mounts-none/full-overhang params; (b)
shared-bus per-rail corridor former (_shared_bus_topology + spine branch; columns by fan order
at the daughterboard field pitch; blade row contiguous); (e) DUAL-SIDED chains (place(flip)
completed for real parts -- pads mirror + ROT NEGATED (anti-commute), calibrated vs pcbnew
native Flip 3/3 teeth in tests/test_place_flip.py; F.CrtYd swap; back-text mirror justify;
Candidate.back_refs -> build_board(back_refs); alternating rails RS3/RS4 to B; courtyard
overlaps 11->2; cec_score cross-face impossible-short filter). Blade pitch: atx24 interface
moved 4.2->4.7 (receptacle courtyard 4.29 can't pack at 4.2; daughterboard re-pitch
OWNER-QUEUED). REMAINING before the 24-pin wave: per-side kelvin taps + per-side pours in
cec_fr (synthesize_kelvin_taps/tap_channel_keepouts/derive_power_pours are F.Cu-only -- back
rails' taps/pours must go B.Cu keyed off the shunt footprint's IsFlipped); edge_override (d);
F-face free-part pileup (D_USB1 onto seated U11 -- wave/legalize iteration). Probes seed..seed5c
in build/24pin-probe/.

## (G) 24-PIN GROUND-UP REMAKE (2026-07-08, owner ask, branch claude/pipeline-consolidation)
Owner: remake the complete 24-pin from scratch, first pass -- netlists configured right, textbook
datasheet wiring, LIBERAL margin passives, 4x INA181 transient cells (one per rail); PCB strictly
FROM SCRATCH (never the rev2-inherited layout). Board = modules/atx-24pin-rev3 (BETA-2). State:
- **PASS 1 (commit ~e0):** the owner-queue CRITICAL INA238 supply mis-wire fully decoded + fixed
  (daisy-chain wires with power symbols on wire INTERIORS = connect nothing; R3 SDA pull-up cell
  drawn 2.54mm off its pins). All four sensors netlist-verified powered; ERC errors 11->2.
- **PASS 2 (4e677e2):** 6-subsystem datasheet audit (haiku fan-out wf_f9abc66c) with EVERY critical
  adversarially re-verified -- 5 of 7 were agent over-reads (U13 Kelvin CORRECT; 5V cell CORRECT --
  +5V_MAIN is the 5V post-shunt node; TPS2121 near-textbook: IN1=+5V_MAIN priority, PR1 divider
  100k/33k = 4.0V switchover, CSS/ILIM/ST present; TB1-9 TE 63969-1 is the ITERATION-7 owner-
  ratified mate, README header is the stale text). REAL fixes: PR1 label attached (net /PR1);
  IO8 strap pull-up R10 10k->+3V3 (C6 Table 4-3: GPIO8=1 for download boot, no internal pull) +
  no_connect removed, net /IO8_STRAP; 12-cap margin bank (C14-C17 INA238 1uF bulk, C24 ESP 1uF,
  C18-C21 mux input 100n+10u BOTH inputs, C22/C23 -12V 100n+10u, C25 +5V_SYS 22uF) each with
  place-adjacent Note for the layout pass. PS_ON#/PWR_OK pull-ups DECLINED (pass-through, not ours).
  ERC = 1 benign (U2 TXD). 96 comps. bom/bom.csv regenerated; LCSC sourcing of the 13 new passives
  deferred to the BOM pass (FOLLOWUPS; -12V caps need >=25V variants).
- **4x INA181 cells verified**: all four (12V/5V/3V3/5VSB) correctly wired INA181A2 -> TLV7011 ->
  distinct DET GPIOs (U1.28/29/15/16), shared /THRESH RC DAC (R60 10k + C60 100n, fc~159Hz).
  Gain math: A2(50V/V) on 25mOhm 5VSB saturates at ~2.64A ~= the rail max -- full normal range
  measurable, saturation only in gross overcurrent; deliberately kept A2.
- **NEXT:** visual render review (cec_sch_review) + any readability nudges; the SENSE*-vs-SENSEC
  force-net naming generalization in the pipeline; then the FROM-SCRATCH PCB synthesis wave for
  this board (shared-bus per-rail corridors -- the foreign-on-pour checker already reads the new
  rev3 pour architecture as applicable).

## (F) PIPELINE CONSOLIDATION + fresh-board wave (2026-07-07, branch claude/pipeline-consolidation)
Owner directive: consolidate the agent-pipeline branch (claude/placement-corridor, 58 commits) with
beta main (PR #68 = ground basis; beta/README.md = authoritative board manifest), test on the GPU
suite on this box, then run FRESH size-optimized PCBs through the pipeline (never reuse old PCBs;
dual-sided allowed). Cheapest agents for delegation (owner ask). State:
- **MERGE DONE** (92540e7): conflicts were 6 meta files (union-merged, attributed) +
  cec_synth_pipeline.py + pcie-3port PCB (both auto-merged clean, verified: no dup defs, board
  loads 103.5x56.1 = grow preserved + main title block). GPU verified: cupy 14.1.1 on the RTX 5090
  in cec/routing:gpu; SB-08 golden = BYTE-IDENTICAL red vs the branch baseline (owner-gated bands,
  NOT a regression; the bent-tap change later IMPROVED it: unconn 8->6, taps now lay bent).
- **ROOT-SCH FIX** (7d281a9): Config.load used sorted(glob)[0] -> grabbed a LEAF sheet of the
  hierarchical beta boards (eps netlist = 6 of 63 comps, everything downstream inert).
  cec_toolchain.find_root_sch resolves .kicad_pro-stem -> sheet-instantiating -> dir-name;
  wired into Config.load (+ hubs/ + output-daughterboards/ name resolution) + cec_thermal_sources.
- **BLADE FIELDS** (aa1d402 + stride fix): beta modules replaced J_OUT with TB* TE 63969 FASTON
  receptacle FIELDS (D-5a; per-cable 6-slot window = one mating daughterboard; pitch 4.7mm from the
  as-built eps-out-db tab field -- NOTE committed module placeholder row is 4.75 = a 0.25mm
  blind-mate mismatch, FOLLOWUPS). _role/-cable_topology/_seat_blade_fields: blades are power_out
  anchors, the corridor's output end, seated as ONE row with per-window MIRRORED rail-slot choice
  (net->slot is a FREE routing-time variable -- owner: "reorder however you want in rails");
  measured rail triples 0.56mm off their corridor columns, foreign-on-pour 0t/0v.
- **INA238 LO-TAP BLOCKER CLEARED** (aa1d402): the convergent blocker (memory
  ina238-lo-tap-refusal-blocker) -- straight LO stub clips the IC's OWN GND(7)/SDA(6) pads.
  synthesize_kelvin_taps now tries orthogonal DOGLEGS on refusal, every leg guarded by the foreign
  guard AND a new different-sense-net overlap guard (never plow the HI pad); plus a VBUS BRIDGE
  (pad9->pad8 same-net stub -- pad 8 lives inside the tap channel where FR is kept out). Fresh beta
  eps: 10/10 taps laid (2 bent + 2 bridges), refused {}.
- **MEASURED GAP to gate-clean on a first-cut fresh placement**: oracle recipe route leaves ~61
  unconn vs 5 on a PLAIN route -- the recipe KEEPOUTS over-constrain an untuned placement; that
  co-optimization is exactly the wave/intent fan-out's job (mechanism unblocked, not a corpus gap).
- **DASHBOARD** (:8090, cec_dashboard.py): now a LIBRARY EXPLORER -- BETA LINE (BETA-marker dirs +
  daughterboards) / FRESH RUNS (build/**) / SNAPSHOTS timeline; one-click analyze (/api/enqueue);
  build/fresh/** WATCHER auto-archives new boards as they are made. Running detached on 8090.
- **WAVE-1 RESULT (eps-8pin, 24 variants): GATE=TRUE.** Winner periph-left-dataflow-s2
  (fresh synth placement from the beta netlist, routed by the oracle recipe): kelvin+diffpair
  TRUE, drc 0, unconn 0, foreign 0/0, thermal dT 10.2<=30 (REAL solve after the blade-sink
  fix). Needed two geometry-VERIFIED score waivers (cec_score._drop_impossible_pad_artifacts):
  the documented SW2 rotated-footprint false short/mask-bridge (pads 4.36mm apart,
  Collide()==False) and the documented mount-pad-vs-edge finishing class. Published
  build/fresh/eps-8pin/20260707T2018-*.kicad_pcb + wave-report.json; dashboard watcher
  auto-archived it (end-to-end verified). Seed variance is the fan-out's fuel (same intent
  s0..s3 ranged unconn 0..145). NEXT: pcie-2port/3port waves (owner said one board first --
  ASK before launching more), size-shrink pass on the winner, wave-2 with intents on the
  crowded hub-link right side.
- **WAVE MECHANISM** (was: RUNNING): (owner: ONE board first): scripts/cec_fresh_wave.py --boards eps-8pin, 24
  variants (3 intents x 2 strats x 4 seeds) at passes 16/opt 20 in docker-routing-1 (detached,
  log build/fresh-wave-1.log); publishes ONLY the best to build/fresh/eps-8pin/ (watched).
  pcie-2port/3port queued next after the eps read-out.
- **SCOPING (workflow wr4a00l46, 10 boards)**: eps + pcie-2 ready; pcie-3 "CAN_TX break" was a
  haiku over-read (netlist-verified U1.26+U2.1 fine; benign TXD pin_not_driven); atx-24pin-rev3 =
  SENSE*/rail naming + NO Edge.Cuts; 12vhpwr = SENSEP naming (both need the force-net naming
  generalization, FOLLOWUPS has the exact edit list); argb = NO PCB + J1 SATA footprint missing;
  daughterboards tiny (7-12 comps) + trivially routable; hub = 90 comps, no sense machinery.
- **TEST RE-BASELINE PENDING**: merged tree has ~20 failures in test_corridor_model /
  test_placer_oracle / test_foreign_on_pour_gate that are 0 on the pure branch -- they bind to the
  OLD eps geometry; re-baseline against beta boards (or fixtures) after the blade generalization.
  tests/test_placement_session.py needs pytest (absent in container).
- **TEST RE-BASELINE DONE (2026-07-08 tick): 883 tests, failures=1 (owner-gated).** The ~20
  reds were mostly TWO sys.modules polluters, not board drift: test_fs_actuator's bare
  cec_fr02 stub + test_ei01's pcbnew setdefault (discover imports every module before running
  any -> a module-level injection poisons the whole run; both now scoped/conditional). Board
  drift handled via tests/fixtures/eps-8pin-legacy (frozen merge-base eps -- the artifact the
  corridor/keepout/placer/e2e/reconcile/cl25-sync suites encode) + honest expectation updates
  (hub power-header rename; owner's new rev3 PCB legitimately became foreign-on-pour
  APPLICABLE; widegap fixture kelvin genuinely healed by the bent tap). compose.yaml carries
  GIT_CONFIG_* safe.directory for the bind mount. The ONE red = parity-report re-freeze
  (registry 34->38), CODEOWNERS-gated, queued in docs/owner-queue.md.
- NOT pushed yet; PR-ready modulo the owner-gated parity/SB-08 goldens. Push + PR on owner go.


## OWNER DESIGN-BASIS FACTS (2026-07-05, bench-mode thread — record before any Max-tier work)
- **Max slow path (owner)**: one ADC monitors all 6 INA240s → FPGA reads at max, decimates to ~50kHz, ~10kHz usable — BUT those numbers are PROTOTYPE artifacts (flyover wires + hard filter caps); the REAL ceilings = INA240 usable bandwidth + the shunt's inductive corner ("the hard caps to the slow path's maximum"). Fast path = one fast ADC, two differential pairs (shunt + Rogowski coil) at max rate; FPGA consolidates.
- **Arc research recap (owner, matches the June-11 family)**: sustained arcing at our voltage/materials = provably no; MICROARCING not ruled out (only automotive testing exists, wrong voltages — "basically all of it is novel").
- **Voltage tracking: REQUIRED, placement OPEN** (fast-vs-slow path; owner unsure if fast-path V is valuable — note the June-11 verdict's one validated >1MS/s use case is ATX ripple = a VOLTAGE measurement; across-connector differential-V for microarc detection = candidate idea, interposer has both sides). Analysis appending to docs/bench-mode-max-stack-2026-07-05.md §7.
- **Prior art of record**: docs/research/max-instrument-channel-decision-2026-06-11.md + 4 companions (recorded owner ruling, OQ-15/17/18/19) — the Max architecture was ruled 2026-06-11; spec §6.11 text is STALE vs it (owner-pen item, already tracked).
- **Max module architecture (owner, verbatim-class)**: 12VHPWR Max = Rogowski coil + fast and slow ADC dual input → FPGA + MCU on-module. **Owner has a WORKING rough prototype on a Sipeed Tang Primer 25K (GOWIN GW5A-25 class)** — anchors the consumer Max line to GOWIN-class fabric, NOT PolarFire. Fast-path rates/coil part/what-the-prototype-streams = UNVERIFIED pending owner numbers.
- **Tier-paired hubs (owner ruling)**: Max hub ingests Max modules; Pro hub ingests its own tier only (design-point ~900kB/s×8 → USB HS; full-rate requirement dropped from Pro). Bench mode = hub-consolidated (module-direct-USB demoted to fallback).
- **BENCH-MODE + MAX STACK RULED (owner, 2026-07-05: "I agree with everything here and it can be ruled as such")**: docs/bench-mode-exploration-2026-07-05.md (Pro) + docs/bench-mode-max-stack-2026-07-05.md (ruling banner + §7 voltage/ceiling: fast-path V ruled IN — ATX ripple 10Hz-20MHz is a VOLTAGE measurement; slow-path production target ~80-100kHz from INA240 100kHz 2%-THD ceiling + CSS2H "<2nH" 53-318kHz corner bracket; burst-window model since continuous fast raw 100-260MB/s exceeds every link; T1-on-pair-2 carries continuous telemetry at 1.6-8%). Part picks LANDED (docs/max-part-selection-2026-07-05.md, commit 0441091): AD7606B slow / AD9253BCPZ-80 fast / GW5A-25 module FPGA (only budget part w/ 1.6Gbps LVDS-RX; owner NOT locked to GOWIN — "whatever is easiest and cheapest") / ECP5 LFE5U-25F/45F hub FPGA (FOSS toolchain) / LAN8770M T1 / RTL8211F GbE / ESP32-P4; module BOM $150-190, retail $499-599 at the spec's 3.5× precedent.
- Daughterboard shrink LANDED 2026-07-05: 81.2×16.6 / 53.0×14.6 / 34.6×14.6mm (pitches 8.9/8.6/8.2), no mounts, ≤15mm standing height, geometric no-subset-seating proof green.

_Updated 2026-07-05 ~21:10 UTC (branch claude/schematic-work-continue-59pw41, HEAD 0441091, tree clean+pushed)._

## STATE (2026-07-06 ~01:45): ALL AGENTS LANDED. Daughterboards = iteration-4 compact two-band FINAL (21.4/20.0/20.0mm tall, pitch floor 7.10 = clip pad span 6.60+0.5; keying on pitch spread, gap-key alternative offered to owner ~1.5mm saving); ARGB Standard schematic LANDED a444ebd (8 leaves, ERC 0, USB-merge bug caught via netlist, BOM $8.30 raw; RATIFY LIST: OQ-29 S3-MINI basis, RJ45-VCC standby-OR, BAT54S sub, OQ-36 header, SATA consigned); INA238 ruling APPLIED (spec v1.5.0); pricing FINAL ($259/279/299 bundles). AWAITING OWNER: pigtail-vs-3ch (task 13 gate), part-pick reaction, fit-check sample order, INA238 hedge-buy.
- **Daughterboard tab ITERATION 3 in flight (owner sketch, 2026-07-05 ~22:15)**: 63951-1 stays; geometry corrected by owner sketch = legs stacked vertically through the standing board face, flat-L runs horizontally off the face then bends 90° DOWN, descender drops into UP-FACING 3586 clip (slot axis perpendicular to wall line, clip offset = the L standoff); board edge stays clear. Iteration-2 in-plane-hang form REJECTED by owner; my interim straight-fin brief was a misread, fully overridden pre-landing. Agent aa4d9c83 reworking (true-L footprint from TE C=63951, seating model, checker re-derive). Owner-queue 0.27mm item retires on landing. ALSO: owner MODDIY ruling — Molex connectors ~$1 at volume via MODDIY, JLC population no longer a concern (relayed to pricing study, revision pass in flight; v1 tables predate the research package).
- **Agent a97ac9e8 (consumer pricing study)** → docs/pricing-study-2026-07-05.md: Std/Pro Hub+module landed cost (100q/1k, JLC fab+assembly, consigned THT), retail bands, bundles. CORRECTED premise relayed (accepted): Hub sellable WITHOUT 24-pin — runs on USB power (TPS2121 mux), loses guaranteed 5VSB standby unless the motherboard back-feeds USB at soft-off; base bundle repositions on "guaranteed standby" value, Hub-only à-la-carte row with the caveat; §2.9 rail-sense (IO9/IO10) = firmware upsell surface.
- **AWAITING OWNER**: (1) instrumented-pigtail 4th fast-ADC channel vs 3 channels (Max, gates task 13); (2) INA228-vs-INA238 24-pin cost decision (owner-queue row, pricing-study headline); (3) daughterboard iteration-3 result review when it lands.
- **Task 13 (Max/bench spec rev) GATED** on: tab outcome + pigtail answer + owner part-pick reaction (FOLLOWUPS entry added 2026-07-05).

## ROUND 4 — hierarchical conversion of the module boards (2026-07-04, branch claude/schematic-work-continue-59pw41)
- **Plan of record: docs/standard-tier-review/round4-hier-conversion-2026-07-04.md** — read it before touching any consumer schematic. Owner round-4 directive (TODO.md line ~202, 2026-07-04 10:20): multi-sheet division APPROVED ("readability over all else"), GND arrays bused to one link on ALL boards, full rearrange on all except hub+24pin, COST = sonnet/haiku subagents only / deterministic checkers as judge / ONE final render per board / generator-code-once.
- **Strategy**: convert eps-8pin, pcie-8pin-2port, pcie-8pin-3port, 12vhpwr-standard to the hierarchical composed form (one functional block per literal sheet via cec_sch_compose, ent-common = worked example). Hub + 24pin-rev3 stay flat, GND-bus mutation only.
- **MEASURED design facts (this session)**: (1) a root-lane LOCAL label renames a spanning net to "/NAME" exactly (probe on scratch ent-common) → inter-sheet nets keep flat names verbatim; (2) leaf-internal nets rename to "/<sheet>/NAME" — bounded, handled by a group-matched rename map propagated to PCB + netclass patterns with membership-equality asserts; (3) MCP verify_identity is NAME-AWARE (fails on renames) — conversion gate = name-agnostic group compare + committed rename map; (4) ent-common does NOT bus GND (17 per-pin stamps in 04-mcu) — bus is new work via build_leaf layout wires+consumed.
- **PCB sync**: regen changes symbol UUIDs + sheet paths → scripts/cec_pcb_reconcile.py (Wave-1 agent building) relinks footprint (path ...) by ref + renames nets; 12vhpwr is FULLY ROUTED + CI-gated (not DRAFT) → strict DRC parity (0 unconnected / 0 schematic-parity / cosmetic-silk-only), converted LAST after EPS→PCIe prove the chain. fab/ snapshots = frozen alpha, untouched.
- **Waves**: W1+W2 LANDED (toolkit 49b85aa/fb85796; reconcile tool; EPS conversion 336de67+926cc09 — 7 leaves, all gates green, ERC errors 1<baseline 2, G5 waivered at composed-engine floor 1/17/7). KEY MEASURED FACTS: (a) name-pin stub local label = KiCad ERC label_dangling FALSE-POSITIVE (root hier labels ILLEGAL "non-existent parent sheet"; kicad-cli erc_exclusions CLASS-LOOSE — wrong uuid+pos suppressed all 13!) → remedy = per-board .kicad_pro rule_severities.label_dangling=warning written by the DRIVER, real danglers policed by audit-sch (teeth verified); (b) audit-sch.py upgraded HIERARCHY-AWARE (per-dir root-walked instance-path chains + hier/global-label + sheet-pin wire anchors; teeth both ways; hub-enterprise noise collapsed to REAL residuals → FOLLOWUPS: through-body wires, 2 missing lib symbols, small endpoint counts); (c) driver: project name MUST = .kicad_pro basename; mutator battery in-driver (glyph 26→7). **ROUND 4 COMPLETE (2026-07-05 ~06:00, commits through b3787c7)**: all 4 module boards hierarchical (eps/pcie2/pcie3 7 leaves via gen-module-beta.py; 12vhpwr 11-leaf flow partition via gen-12vhpwr-beta.py) — every board zero-rename, identity-exact, ERC errors ≤ baseline, audit ok; 12vhpwr routed PCB reconciled (77 path relinks, copper BYTE-IDENTICAL after net/path strip, DRC parity 19/19, 28 schematic-parity gaps are PRE-EXISTING H3a-splice-vs-PCB sync, resolved by the W9/W12 layout passes); suites 57/57 (flat-era fixtures repointed to git-frozen baselines; reconcile tool handles hierarchical baselines). Renders delivered to owner. GND-bus: hub no-op (already merged), 24pin 18→1, 12vhpwr partial 24→6 (S3-MINI pins not collinear — FOLLOWUP). NOW RUNNING (D-5a implementation wave, owner-ordered): [task 9 agent] blade interface onto main boards (24pin-rev3 hand-splice J4→TB1..9+J_SIG; EPS/PCIe = generator edits + regen w/ modeled-delta assertions; Rev→BETA-2 proposed) ∥ [task 10 agent] modules/output-daughterboards/ projects (atx24/eps/pcie per-cable, TE tabs + TH field + MODDIY DNP alt + keying + M3 chassis mounts, pours via sanctioned toolkit). D-5a study COMPLETE through §8.10 (blade config ratified by owner, spec v1.4.0 APPLIED 03c73fe; library intake landed: Keystone 3586/3557-2 + TE 63849-1 vendored w/ 2 drill corrections + 3557-2 is actually a DUAL fuse-clip housing — flag; fit memo = datasheet-compatible w/ 0.84mm tab tolerance edge case). NEXT after W3: task 9 (blade interface onto main-board schematics — EPS/PCIe now single-leaf edits) + task 10 (daughterboard projects).
- **D-5a RULED (owner, 2026-07-04)**: connector DAUGHTERBOARD for 24-pin/PCIe/EPS output (passive, inter-board connector, MODDIY vertical header OR pigtail population; sellable daughterboard+extension assembly addendum; chassis strain relief). Owner design basis: EPS ~13A/pin sustained → ~52A/cable (4×12V), PCIe ~39A/cable (3×12V), Intel EPS12V spec 336W, transients ≠ sustained. §2.8 spec-revision draft owed AFTER the connector current kill-check clears. Recorded: SYNTHESIS-beta-plan.md D-5a + owner-queue + FOLLOWUPS. Round 4 UNAFFECTED (identity-gated; J_OUT stays as-is until the revision lands separately).
- **Gates G1-G11** enumerated in the plan doc (group-identity, inventory, rename-class, ERC, overlap/wire, containment/bounds, netclass membership, prose, PCB parity, render, BOM equality).
- Stale side note: modules/{eps-8pin,pcie-8pin-2port,pcie-8pin-3port}-rev2 = PRE-BETA 2026-06-24 sectioned-regen experiment dirs, superseded by this pass (owner cleanup flagged in FOLLOWUPS). Post-beta EPS refs incl. new FB1/FB2, FL1 (DNP CMC), D3, R11/R12 bypasses; new nets /CAN_H_RJ /CAN_L_RJ /VBUS_RAW /VCC_RJ45_RAW.
- Round 1-3 readability history + routing-foundation doc: see TODO.md lines 192-201 + docs/standard-tier-review/routing-foundation-2026-07-04.md (landed 9b60b29; TODO entry 200 flipped done this session).

## ENT LINE 2026-07-01..03 — spec v1.2.0 APPLIED, board program running (branch claude/enterprise-modules-planning-zpjmir)
- **BETA SCHEMATIC WAVE COMPLETE (2026-07-03 ~20:30, commit 86afdaf)**: all five consumer boards at Rev BETA-1 — standalone-USB suite (USBLC6+VBUS clamp) + ferrite posture (VBUS bead populated MPZ2012S601AT000/C21519, 5VSB 0R-default, CAN CMC DNP **with the populated-0R-bypass pattern** — a DNP series part opens the path, netlist-blind; broadcast mid-wave) on every module; hub adds J_PWR 3-pin consolidation + TLV7011 comparator (4.28V trip → IO14 RTC-wake, full pin audit) + hold-up ladder DNP provisions (boost = TPS61040/11.51V after the TPS61023 5.5V-ceiling spec error was caught); 12VHPWR fan header w/ proven pre-shunt tap; 24-pin rev3 = beta base, J6 mezzanine contradiction CLOSED (hub-rev2 J_MEZZ evidence; doc was stale, boards consistent — K1 gate cleared), RS4 4-terminal Kelvin, +5VSB/+5V_SYS bug fixed; PCIe×2 got W5 netclass/dru/USB-rename prep. NEXT: W6 routing wave (EPS+PCIe×2 ready), hub+12VHPWR beta layout passes (W9/W12 placement, U4↔U3, keepout drop), D-5a output form = the BOM-freeze gate. BOM-freeze follow-ups: CMC part reconciliation (ACT45B vs ACT1210L), FL1 footprint, 0R stock, U3.EN re-strap at rung-3.
- **AGENT MODEL POLICY (owner, 2026-07-03)**: subagents = Sonnet default, Opus max for hardest engineering; top-tier model orchestrates only, never delegated work. Set model explicitly on EVERY Agent launch.
- **GENERALIZATION PASS COMPLETE (2026-07-03 ~04:30, commits dd995c6 + 43cb70e)**: composition machinery promoted to shared scripts/cec_sch_compose.py (+ cec_sch_archetypes.py, T4 start — 8 archetypes, all with real callers); hub build_lib.py = thin shim, hub regen BYTE-identical. modules/ent-common recomposed as root + 6 literal leaf sheets through the shared engine (dashed frames gone; node-set identity 0/0; ERC 117→91 benign-only; overlaps 0; tests/test_sch_compose.py 4/4). Per-family ENT module projects now start as thin data files over the engine. NOTE agent-ops lesson: two agent crashes on the 64k output cap (giant single-response pattern) — fixed by fresh agent w/ leaf-by-leaf build discipline + ≤250-line incremental writes; kill-and-relaunch beat resuming the poisoned context.
- **Spec v1.2.0 (2026-07-02) APPLIED under nine owner rulings**: one ENT line (posture NET/AIR × availability B/MC/MC-Max × silicon base/HS), new §13.1-13.9 (PolarFire hub, **MPFS095TC Core production baseline** on a part-agnostic SerDes-free FCVG484 land, 095TS = HS option; 100BASE-T1 module link pair-2 on EVERY ENT module incl. 24-pin, uniform ESP32-P4 module MCU, DETECT 10kΩ), §2.3 pin-7 = SYNC/FREEZE + heartbeat challenger (ENT only), OQ-7/14-ENT/53-56 closed, **OQ-11 FULLY closed** (EPS/PCIe 0.5mΩ CSS2H-2512R-L500F, 12VHPWR 1mΩ CSS2H-2512R-1L00F, 24-pin 2mΩ K + WSK2512 25mΩ), OQ-75..81 opened. Registers: 114 REQs lint green; verification matrix wired into checklist.sh. RS-485 dropped from ENT (9th ruling); SBOM = SPDX-native + CycloneDX-derived; ATR = passive-receive-only.
- **Requirements of record**: docs/enterprise-requirements/ (6 registers + ratification/ + research/ + board-program/); security docs at docs/enterprise-security/ (threat model = canonical honest-limits, heartbeat wire protocol CAN 0x7A0-0x7AF + T1 EtherType 0x88B5, untrust state machine, custody 2-of-3 PENDING owner final sign-off); validation pack at docs/enterprise-validation/. Root chart doc ENT-TRUST-AND-VARIANTS.md (Mermaid + SVG exports).
- **ENT HUB SCHEMATIC in flight** (hubs/hub-enterprise/): hierarchical 10-sheet project, generator gen_hub_enterprise.py; sheet 01 power-input CAPTURED (59 parts from BOM-D, check_hub_ent_sch.py exit 0, ERC benign-only; REAL CATCH: BOM-D's CP2→GND rec was wrong vs shipping hub-standard — CP2→IN2 followed, BOM-D corrected). OWNER FORMAT CORRECTION: one functional block per LITERAL sheet → restructure agent (01 → thin parent + 01a-g leaves, netlist-identity required) STILL IN FLIGHT. P4+T1 shared module block agent (modules/ent-common/) STILL IN FLIGHT. Capture order next: 05 (ports) → 04 → 03 → 02; sheet 06 BLOCKED on LAN9370 datasheet (owner), 09 on S32K RM.
- **Schematic-quality charter** (docs/schematic-quality-charter.md, SessionStart-hook-injected): T0 render substrate (cec_sch_render.py — kicad-cli SVG → chromium tiles, orchestrator reads them natively; NEVER `playwright install`, use /opt/pw-browsers chromium via executable_path; pip playwright provisioned by setup-kicad-cli.sh), T1 layout engine (cec_sch_layout.py, rotation round-trip verified, wired decouplers, text-collision nudge), T2 pin-type auditor (cec_sym_audit.py — 191 high findings on cec-ent libs incl. 4 load-bearing MPFS control-pin mistypes; --fix pass DEFERRED until module agent releases lib/cec-ent-mcu; = sheet-02 gate), T3 style linter (cec_sch_lint.py) — ALL LANDED with teeth. NEXT: integrate T1 into gen_hub_enterprise (regen 01a-g, netlist-identity proven), adopt gates 5/6.
- **FCVG484 breakout study BANKED** (board-program/fcvg484-breakout-study-2026-07-03.md + scripts/cec_fcvg484_breakout_study.py + ring CSV): **6-layer OK WITH CONDITIONS** — ~87/484 balls demand, JTAG+SGMII silicon-fixed deep (~23 balls, via-in-pad Type VII on bounded ~35-50 set), needs a NEW finer BGA-fanout .kicad_dru netclass (platform 0.22mm Signal doesn't fit 0.4mm channel); **USB OTG has NO ball in the cached map — genuine gap**, MSSIO tightest bank (28/38); 8-layer triggers: DDR populated, USB deep, no via-in-pad fab, MCX. Both new scopes in FOLLOWUPS.
- **Owner-pending** (docs/owner-queue.md): dev-kit + 3-5× MPFS095TC-FCVG484E hardware order (CUSTOMER-DEMO critical path — a customer exists, prototype = the ask), LAN9370 datasheet + JXD1 ECAD, Libero license, CEC-KVM 5-item decision box, custody final sign-off, mezzanine beyond-AIR review, RFQ send at customer design sign-off.
- Session policies live: TODO.md append-only flips, FOLLOWUPS.md same-turn, commit trailers per CLAUDE. Branch pushes to claude/enterprise-modules-planning-zpjmir only.

---


_Updated 2026-06-14 ~23:00 UTC (PLACER-UPGRADE MV2-MV5 done + audited + pushed, PR #60)._

## PLACER-UPGRADE MV2-MV5 COMPLETE + AUDITED + PUSHED 2026-06-14 ~23:00 UTC (branch claude/placement-corridor, PR #60, HEAD eff0136)
Continued the MV checklist (docs/placer-upgrade-2026-06-14/plan.json) under the anti-overfit charter. Three commits pushed:
- **e3a21de** — committed the prior session's COMPLETED-but-uncommitted placement EI-parity PL-01..PL-10 (durability; it was sitting in the dirty worktree, a WSL-ephemeral near-miss).
- **26d9a77** — MV2-MV5 in scripts/cec_synth_pipeline.py: **MV2** net-aware `_role`/`_connector_net_role`/`_is_rail_net` (a power-only J* -> power_in, fixes J_5VSB) + `oracle_stage1_answers`/`apply_oracle_stage1` (derive size/edge_override/mount/antenna FROM the reference Hub) + `seed_anchors(edge_override=)` 4-edge + `place_mechanical(mount_pos_override)`; **MV3** `oracle_similarity` DIAGNOSTIC (never a rank key — `_candidate_sort_key` excludes it); **MV4** `proxy_score` (==hpwl off-oracle = zero regression; ref-normalized HPWL-dominant composite) + sort-key swap; **MV5** `build_hub_model`/`hub_score` (port_even/antenna/power_cluster/usb_prox, gated to >=2 RJ-45 + ESP). tests/test_placer_oracle.py.
- **eff0136** — consultative-audit remediation: 4 parallel skeptics (geometry/charter/regression/test-rigor) = ALL SHIP-WITH-FIXES, 0 blocker. Fixed H1 (similarity renorm over present terms -> identity 1.0 any board), M2 (sense/ref nets excluded from rails), M3 (edge_override validation), charter MEDIUM (power-loop now TOPOLOGICAL small-fanout, no Hub net-names baked, + cfg override), regression MEDIUM (oracle-failure logging), 2 HIGH test-rigor (MV3/MV4 plan-validation tests) + scramble/sort-key teeth. 41 tests green, checklist exit 0, SB-08 golden NEUTRAL (only the pre-existing owner-gated AM-04 thermal red).
- Validated on the committed Hub: J2-J5 top / J_5V,J_5VSB right / J_KVM,J_USB bottom; outline 98.1x74.1; reference hub_penalty ~0.27 (scores well) vs synth ~0.60 (the placer's measured gap). Status+audit: docs/placer-upgrade-2026-06-14/STATUS.md.
- **HUB TEST RUN DONE 2026-06-14** (in kicad10 container, recipe in STATUS.md "HUB PIPELINE TEST RUN"): place→materialize→render→DRC→score ALL ran. Best residual 4, corridor_cross 0, **similarity 0.705**, **HPWL 1.25× the hand board** (down from 1.84× pre-MV — the oracle frame is the win), hub_penalty 0.373 (antenna term 0.0 = the gap). DRC ~506 cosmetic + ~64 real-structural (tracks residual 4) + 211 unconnected (UNROUTED, route leg not wired). **The placement pipeline WORKS on a real fab-class board with the correct oracle frame.**
- **FULL PIPELINE WIRED + FR NOW ROUTES THE HUB 2026-06-15** (scripts/hub_pipeline_run.py). Three fixes: (1) **on-board OFFSET** — synth cand.P is 0-origin but the committed outline is at (70,90); repositioning to synth coords put parts OFF the board → FR routed nothing (THE unblock); `_reposition_worker` offsets by the board-edge origin. (2) `_seat_antenna_ic` — seats the ESP at its antenna edge as a fixed anchor (off the ganged ports) → residual 4→0; antenna term fixed to use the courtyard near-edge (ref 0.565→1.0, synth 0.0→0.903, hub_penalty 0.373→0.125). (3) two-process GND fill (the pcbnew Remove footgun corrupts the process → fill in a fresh spawn). RESULT: low-effort route_once = **628 tracks / 39 unconnected / kelvin+diffpair pass / len 2240** (was 2/216); committed HAND placement routes 389 wires (baseline). 103 placer tests green.
- **LIVE PANEL auto-repoints + CANDIDATE TIMELINE SCROLLER (scripts/hub_run.sh + cec_dashboard.py)**: the launcher retargets a stable symlink `build/hub-LIVE` -> the run's OUT + ensures cec_dashboard.py is up on :8095 pointed at the symlink. The dashboard follows symlink retargets LIVE (abspath preserves the symlink, per-poll glob) -> every launch auto-repoints with no manual step (proven). The board panel now renders EVERY candidate (placements `hub-cand*` + routed `route-cand*/*-routed`, comma-separated board-glob, cached by mtime) with a scroller (◀/slider/▶/`live`) to step the timeline; each candidate has its own render+per-layer plots (`/board.png?cand=N`, `/layer/<L>?cand=N`, `/api/state.candidates`). Use `bash scripts/hub_run.sh [OUT] [HOURS] [CANDS]` to launch+repoint in one command. Panel: http://localhost:8095. GOTCHAS: (1) the panel MUST run under `sg docker` — its board render shells `docker compose exec routing`, and this box's default shell lacks docker-group access (verified: plain docker DENIED); the launcher uses `sg docker -c`. (2) `timeout` on a docker CLI orphans the container -> the launcher uses `docker run -d --rm` (daemon-managed) + the script's own --hours budget, no outer timeout.
- **NEXT: the HOUR RUN is launching now** (higher FR effort + cec_router repair loop → drive 39 unconnected + DRC down toward a clean routed Hub). Then score routed gates/length vs the committed Hub (2359). Remaining (FOLLOWUPS item 4): tune cec_router seeds/iters/opt to fit the budget (FR is genuinely slow now that it routes); promote materialize_onto_reference into cec_synth_pipeline.materialize. NOTE: `timeout` on a docker CLI orphans the container (leaks CPU) — launch the hour run via the script's own --hours budget, run_in_background, NO outer timeout.

---

_(prior) Updated 2026-06-13 ~08:00Z (DeepSeek-V4 LIVE in the cec_fullstack auditor seat, run launched for the night)._

## TONIGHT (2026-06-13): DeepSeek-V4 auditor + cec_fullstack overnight run — LIVE
Owner ask evolved: "make DeepSeek run in the auditor seat and play nice," then (key correction from owner
watching the dashboard) the overnight run they want is **`cec_fullstack`** (manager panels + seat swap +
T5 auditor), NOT `cec_inloop_audit` (which the old handoff named — that one has only a Sonnet auditor + V4
checkpoint, NO manager panels). Then: brief the manager panel + auditor with the **promoted corpus**, run
for the night unattended. Full V4 detail in memory [[deepseek-v4-auditor]].

**LIVE STATE (relaunch-able):**
- **DeepSeek-V4-Flash-284B** runs **Windows-native** (`E:\toolchain\run-v4-flash.bat` → `0.0.0.0:8007` alias
  `deepseek-v4-flash`; GGUF at `/mnt/e/models/DeepSeek-V4-Flash-GGUF/Q4_K_M-XL/`, 163 GB; experts in host RAM
  ~163 GB working set but only ~73 GB committed/reclaimable, attention+KV on the 5090 ~13 GB). It is REGISTERED
  in the broker (live + vendored `ops/cec-llm-broker/models.json`) as a `managed:false` external backend
  (host `windows-host`→WSL gw, port 8007, vram_gb 13). Broker proxies; never starts/stops/evicts it.
- **The overnight run = `cec_fullstack`**, launched detached via `sg docker` (run PID was 130423):
  `CEC_STREAM_DIR=$PWD/docs/fullstack-run-2026-06-13/streams CEC_VLLM_REVIEWER_MODEL=cec-worker-vision
  setsid nohup python3 scripts/cec_fullstack.py --board eps-8pin --hours 7`. Auditor=deepseek-v4-flash
  (default), v4_every=4. Output: `docs/fullstack-run-2026-06-13/` (run.log, streams/, REVIEW.md, intents/,
  vision/, reviews/, gr01-grid.json, morning bundle).
- **PLAY-NICE solved (GPU + RAM):** V4 (13 GB GPU) + the 25 GB `cec-worker-vision` worker would OOM the 32 GB
  card. FIX: compose `worker-volume-vision` now runs `--n-cpu-moe ${CEC_VISION_NCPUMOE:-99}` (experts in host
  RAM → GPU ~8-10 GB; measured co-resident GPU ~17 GB < 32). Registry vram_gb 25→10. T7 reviewer pointed at
  `cec-worker-vision` (CEC_VLLM_REVIEWER_MODEL) NOT the default gpt-oss-120b (63 GB → would RAM-OOM with V4).
  RAM is at the redline (~1-2 GB Windows free, committed ~86 GB of 268 limit, mild paging ~2-6k pages/sec) —
  the owner's accepted RAM-tight tradeoff; NO hard OOM (V4's pages are reclaimable mmap). To revert when V4 is
  unloaded: `CEC_VISION_NCPUMOE=0` + registry vram_gb back to 25.
- **Corpus briefing (owner ask):** new `cec_fullstack.promoted_corpus_brief(board)` injects the **WHOLE**
  promoted corpus (35 entries from `corpus/promoted/general/*.json`, family-scoped tagged) into T1 intent-
  manager, T4 worker-panel, AND T5 auditor prompts. VERIFIED working — REVIEW.md shows the manager explicitly
  reasoning over the ratified entries (e.g. `thermal.shunt_chassis_tim`, `meas.anchor.ref3030`).
- **Dashboard:** `http://localhost:8095` (was relaunched via `sg docker` so its in-container kicad-cli render
  works — that was the "borked plots": it needs docker-group access). Pointed at `docs/fullstack-run-2026-06-13`.
  Per-role seat panels now stream (`manager:intent`, `panel:safety/finishing/progress`, `cec-worker-vision`,
  `deepseek-v4-flash` auditor) — I threaded `seat=` labels into the T1/T4 `_chat_json` calls.
- **Reasoning capture (owner ask):** every seat's FULL chain-of-thought is in `streams/<seat>.jsonl` (cec_seat_
  stream tees reasoning+content deltas). NEW `scripts/cec_review_doc.py` assembles them into a readable
  `docs/fullstack-run-2026-06-13/REVIEW.md` (per seat, every call, full reasoning). A detached refresher
  regenerates it every 5 min for ~8 h, so it's complete by morning. Re-run any time: `python3
  scripts/cec_review_doc.py --run-dir docs/fullstack-run-2026-06-13`.
- **Also fixed:** `cec_inloop_audit.v4_up()` was broken vs the rebuilt broker (probed `/broker/models` + a
  `m['upstream']` key that no longer exist) — now uses `/v1/models` + host/port. HOOKS: session-start/-end now
  self-sync the committed `.claude/memory/` ↔ ephemeral `~/.claude/.../memory` (the committed handoff had
  drifted stale 2 KB vs 8 KB live).
- **HOW TO CHECK in the morning:** `tail docs/fullstack-run-2026-06-13/run.log` (rounds + V4 auditor every 4th);
  open the dashboard :8095; read REVIEW.md. **Relaunch if down:** the `sg docker ... setsid nohup python3
  scripts/cec_fullstack.py ...` line above (worker stays broker-resident across run restarts).
- **COMMITTED + PUSHED** (cbb9ef0 on `claude/overnight-corpus-preflight`, bot): compose n-cpu-moe, broker
  vram_gb, cec_fullstack corpus+seat-labels, cec_review_doc.py, v4_up fix, hooks. Durable on the remote.
- **CONFIRMED WORKING (monitored to ~03:10):** round 1 completed, V4 T5 auditor fired EVERY round, completed
  NATURALLY (`T5: auditor=repair`, 5.5k reasoning chars captured to deepseek-v4-flash.jsonl), round 2 started.
  The DeepSeek call is NOT stuck — it's just slow: cec_fullstack runs the deep V4 auditor EVERY round
  (`audit()` per-round, NOT gated by V4_EVERY; V4_EVERY=4 is the SEPARATE T8 deep-BATCH auditor) at ~4 tok/s
  over the big corpus-briefed prompt → ~12 min/V4-audit, ~15-20 min/round total. Auditor max_tokens=4096
  (jl.MANAGER_MAX_TOKENS), deepseek_audit timeout=900s. So ~15-20 deeply-audited rounds over 7 h (FEWER but
  DEEPER than the old 100+-round runs — the cost of V4-every-round + the 35-entry brief). NO hard OOM (committed
  ~92 GB of 268 limit; avail 0.6-4.6 GB is just V4's reclaimable mmap; mild paging).
- **THROUGHPUT LEVER (if owner wants more rounds, not deeper):** `CEC_FS_AUDITOR_MODEL=sonnet` (cloud, fast
  per-round T5) keeps V4 only on the T8 every-4th batch; or raise `CEC_FS_V4_EVERY`; or trim the corpus brief
  (promoted_corpus_brief max_chars) so the worker/auditor reason less. NOT changed — owner chose deep+whole-corpus.
- **MONITORING:** owner asked to monitor overnight + fix issues. Benign noise confirmed harmless: T6 vision
  anomaly flags are advisory-only (owner ruling, re-checked by determinism); `property.h(607) m_choices` asserts
  are benign kicad-cli stderr. Watch: run.log advancing (a new `--- round N` every ~15-20 min), RAM committed
  < 268 limit, V4 audits completing not timing out.

## Two PRs opened 2026-06-13 as nathanfraske-bot (idle-time work, owner away from PC)

NOTE on bot push: on a branch off `main` the credential helper `ops/secrets/git-credential-cec.sh`
is ABSENT (it lives on the unmerged PR #51 branch), but the git `--local` config still points at it
-> normal push fails. Workaround used: transient inline helper reading `CEC_BOT_PAT` from
`/mnt/e/secrets/cec-bot.env` (`git -c credential.helper= -c 'credential.helper=!f(){...}; f' push`);
`gh` via `GH_TOKEN`. Real fix = merge PR #51 (lands the helper on main).

- **PR #52 — `claude/am04-electrothermal-mincut`** (AM-04 PR-two model-debt fix in
  `cec_synth_pipeline.electrothermal_solve`): segment-sum -> serial min-cut (`_min_cut`, pour-span
  restricted so zero-current Kelvin stubs don't read as series necks); per-transition via clustering
  for non-poured nets vs distributed `I/total` for poured stitching fields; IPC k by the bottleneck's
  actual layer (rename-proof ID). Micro-board anchor moved to the DERIVATION.md CORRECTED column
  (cross 1.044->0.348, dT 4.8->6.12); 8/8 AM-04 + 18/18 thermal-gates tests pass. **SB-08 golden
  re-freeze left OWNER-GATED** (coupled item-3a CEC_GOLDEN_SYNTH + owner `--thermal-headroom`;
  measured: synth-OFF now correctly EXPOSES the 40A-on-0.2mm-trace fusing the old sum hid; synth-ON
  max_T 120.5C limited by the +5VSB rail, no clamp). `expectations.json` untouched (already red-pending).
  CLAUDE.md model-debt note marked RESOLVED.

- **PR #53 — `claude/corpus-promote-43`** (owner-directed corpus promotion; REVISED 2026-06-13 after two
  owner notes). **35** of 43 human_approved `staging/general` entries -> `promoted/general`, VERBATIM +
  signoff{by:nathanfraske}/promotion{promoted_by:nathanfraske-bot, pr:53}. **status FLIPPED human_approved
  -> promoted**: owner directed that status:promoted be a real machine-readable lifecycle value (not just
  the directory). Implemented as a SCHEMA-contract change (audited + adversarially reviewed via two
  workflows): added "promoted" to STATUSES + lifecycle; promoted-zone lint requires status=promoted; NEW
  staging-zone guard errors on status=promoted in staging (demotion must revert). AUDIT confirmed SAFE --
  the compiler selects blocking-vs-advisory by ZONE (cec_corpus_compile.py:297, cec_facts binding=="gate"),
  never by the status string, so the flip moves nothing in/out of the blocking set. HELD in staging (8):
  4 founders-related (dvdi.requirement_tier_verdict, meas.targets.v1 + the 2 truth_chain rows
  meas.truth_chain.claim_level/spec_wording the owner held this round) + 4 AM-02 fixture-blocked
  (can.termination.hub_split_120r, can.bitrate.classical_500k, thermal.k_ipc.external/internal). REVIEW
  CAUGHT + FIXED: (a) doc landmine in 3 files (README, addendum, closed-loop-parity-plan) wrongly said the
  compiler consumes by status -> corrected to ZONE; (b) BLOCKER -- the 3 AM-02 anchor tests
  (test_{measurement_claims,fault_phenomenology}_corpus, test_stability_budget) loaded entries from
  hard-coded STAGING paths, so the promotion MOVE broke them (42 errors), silently (not in CI). Fixed: all
  3 now merge BOTH zones + wired into kicad-checks.yml + checklist.sh. Re-froze parity (matched=20
  unchanged; corpus_only 301->317 = pre-existing drift + #51 incident entry, NOT the promotion). 0
  tombstones. Lint 0 errors; 7/7 corpus tests pass; CODEOWNERS gates corpus/promoted/ + tests/golden/.
  NOTE the credential helper now works on this branch (post-#51 base), no transient-credential workaround
  needed.

## Dashboard per-seat streaming + overnight prep (2026-06-13, branch claude/dashboard-per-seat-streams, PR #54)
- **Live dashboard REWRITTEN** to show real per-seat streaming (owner ask). New `scripts/cec_seat_stream.py`
  recorder (env-gated `CEC_STREAM_DIR`, per-seat NDJSON, no-op when unset). `cec_judge_local` transport
  now SSE-streams + tees per-seat deltas with a blocking fallback on ANY error; seat labels threaded:
  manager, manager:safety/finishing/progress, worker:<i>, reviewer, scribe, v4-checkpoint, auditor.
  `cec_dashboard` replaced the single thoughts panel with a live per-seat stack (/api/seats, /api/seat).
  cec_inloop_audit defaults+clears `CEC_STREAM_DIR=<run-dir>/streams`; passes it through the container exec.
  Adversarially reviewed (0 blockers; 5 should-fixes folded in). 10/10 judge_local tests (2 new streaming).
  **Dashboard is RUNNING** (setsid, :8090). Relaunch: `setsid python3 scripts/cec_dashboard.py --port 8090
  --run-dir docs/inloop-audit-2026-06-11 > .../dashboard.log 2>&1 < /dev/null &`. SAFETY: CEC_STREAM_DIR
  unset => byte-identical blocking transport (overnight unaffected unless a dashboard run opts in).
- **Overnight run = `cec_inloop_audit.py`**. Launch: `nohup python3 scripts/cec_inloop_audit.py --hours 7
  --board eps-8pin > docs/inloop-audit-2026-06-11/run.log 2>&1 &`. BLOCKED on owner (sudo): the route step
  execs the routing container -> first `sudo docker compose -f docker/compose.yaml up -d routing` (+ `build
  routing` if the WSL wipe dropped the image). To get per-seat streaming tonight, MERGE PR #54 first (or run
  from the branch checkout). Gap: deepseek-v4-flash (V4 morning checkpoint) not in the broker + intentionally
  unloaded for the night -> V4 is a no-op tonight by design.
- **ARCHIVE NOTE**: docs/inloop-audit-2026-06-11/ was cleared concurrently (round-117's 153 files MOVED to
  docs/inloop-audit-2026-06-12-archived-round117/ -- data safe, verified). NOT done by me; I left the
  deletions/archive UNSTAGED (owner's call) and committed only the 5 feature scripts.
- PRs now open (all bot-authored, owner-merge-only): #52 AM-04 (MERGED), #53 corpus (MERGED), #54 dashboard.

_Below: env-rebuild + WSL-ephemeral policy + Windows-native Phase B (2026-06-12)._

## Context
WSL distro reinstalled 2026-06-12 after a failed move to E:. Whole Linux home lost; GGUFs
on `/mnt/e/AI Models` survived. Rebuilt the toolchain + broker from scratch, then implemented
the owner's WSL-ephemeral state policy, then started the Windows-native serving migration.
See [[env-rebuild-2026-06-12]], [[llm-broker]], [[bot-git-auth]], [[windows-native-serving]].

## Done + on the remote (branch `claude/wsl-ephemeral-recovery`, PR #51, authored as nathanfraske-bot)
- **Toolchain rebuilt + verified**: KiCad 10/pcbnew, Python deps, Docker+NVIDIA toolkit (GPU
  in-container), routing image, the cec-llm-broker (end-to-end model boot proven).
- **WSL-ephemeral policy**: CLAUDE.md policy; `ops/provision.sh` (one-shot recovery + 4 smoke
  tests); `.claude/hooks/session-end.sh` Stop hook (pushes handoff+memory to `ops/agent-handoff`
  every session, git-plumbing, never touches the worktree); `.claude/memory/` committed; secrets
  policy + the bot PAT placed at `/mnt/e/secrets/cec-bot.env`; broker VENDORED into
  `ops/cec-llm-broker/`; corpus incident entry (lint-clean).
- **Git authors/pushes as nathanfraske-bot** via `ops/secrets/git-credential-cec.sh`.
- **Windows-native Phase B** (`docs/local-compute-windows-native-migration.md`): mainline
  llama.cpp b9611 CUDA 13.3 on `E:\llama-cpp-win\`; networking verified; broker external-backend
  support (`managed:false`, seat `cec-worker-vision-win:8090`); versions.env pinned; launchers
  vendored at `ops/windows-serving/`.

## BLOCKED / next (Windows-native)
- The Windows binaries fail to load: System32 Microsoft `libomp140.x86_64.dll` lacks
  `__kmpc_dispatch_deinit` and loads before llama.cpp's bundled copy (DotLocal `.local` does NOT
  fix it). **Fix needs ONE elevated action** (owner, when at a console with UAC):
  `copy /Y E:\llama-cpp-win\b9611\libomp140.x86_64.dll C:\Windows\System32\libomp140.x86_64.dll`
  (back up first; bundled is a superset). Or a source build with `GGML_OPENMP=OFF` (needs CUDA>=12.8).
- After the fix: start the server (Task Scheduler `CEC-WorkerVision` via `ops/windows-serving/`),
  then finish **B3** (cold-load + decode medians, Win-native vs drvfs) and **B5** (validate the
  broker proxy end-to-end). The broker seat is already wired.
- The WSL llama.cpp stack is the working production path meanwhile.

## ENTERPRISE/MC REQUIREMENTS PLANNING 2026-07-01 (branch claude/enterprise-modules-planning-zpjmir)
Owner asked to plan the full prod-requirements draft for BOTH enterprise-tier variants (Enterprise + Mission
Critical) covering all modules. Grounding done: (a) spec sweep — both tiers exist ONLY in the §1 tier table,
everything (RJ-11 trust, secure element, redundant power/CAN/uplinks, 1000BASE-T1 OV) is named-but-unspecified
pending OQ-7; Appendix B.5 leaning = no-Linux MCU/RTOS + FPGA/TSN, PolarFire SoC candidate (CONFLICTS with §1
"P4 + secure element" and the $50 BOM); modules are TIER-AGNOSTIC (LOCKED §1/§8) — no Enterprise module SKUs
exist, so the module half is a conformance matrix, not new boards. (b) board sweep — Rev2/rev3 wave all
schematic-complete pending layout (Hub Rev2 + mezzanine socket, 24-pin rev3 C6+§6.13+mux, EPS/PCIe rev2);
mezzanine stack doc = enterprise-relevant integrated form. (c) MCP: GitHub live; Google Drive TOKEN EXPIRED
(owner re-auth needed — FOLLOWUPS + owner-queue). PLAN OF RECORD:
docs/enterprise-mc-requirements-plan-2026-07-01.md (5 phases; D-ENT-1..5 owner gates added to owner-queue §1;
Phase 1 skeleton + Phase 2 research can start now, spec promotion Phase 4 is owner's pen).
NEXT (owner ask, same session): fan-out audit workflow — audit both tiers vs enterprise-customer expectations
+ required integrations (DCIM/Redfish/SNMP/fleet/compliance lenses), synthesize into
docs/enterprise-requirements/research/.
UPDATE 2026-07-01 (same session, owner direction — plan §1a): the "two enterprise variants" are
**ENT-AIR (air-gapped)** and **ENT-NET (networked-but-hardened)** deployment postures, BOTH on
**PolarFire** ("just do the enterprise with PolarFire" — D-ENT-2 resolved-by-direction, spec edit
still owner's pen); BOM targets TBD; modules YES — enterprise module requirements drafted NOW
(one register per family, AIR/NET variant-conditional, radio-silicon question flagged: all current
module MCUs are Wi-Fi/BLE-capable ESP32), boards only after ratification. New D-ENT-6 = variant↔tier
mapping (AIR/NET vs Enterprise/MC labels + where the MC redundancy set lands). Plan doc + owner-queue
updated. Customer/integration fan-out audit workflow STILL RUNNING (8 lenses + skeptics + synthesis,
run wf_81e0153f-4e0) — when it lands, map findings onto the AIR/NET framing and write
docs/enterprise-requirements/research/customer-integration-audit-2026-07-01.md.
UPDATE 2026-07-02: customer/integration audit COMPLETE ->
docs/enterprise-requirements/research/customer-integration-audit-2026-07-01.md (8 lenses + skeptics +
critic + Opus synthesis; raw journals banked in research/raw/). Headline blockers: no northbound
management surface (Redfish/SNMP/OpenMetrics/syslog absent); 1000BASE-T1 is the wrong PHY (standard
1000BASE-T/SFP expected); security = platform-wide legal floor (EU CRA) not a tier differentiator;
fail-passive FMEA for in-power-path interposers unanswered; USB-primary contradicts OOB value on
ENT-NET (variant-conditional); "redundancy" must be fail-DETECTED/observable; BOM must be value-priced
vs $1.5-3k comparables; target-fleet statement needed (BMC-less ATX wedge vs CRPS servers). Tamper
module deep-research resumed on sonnet/opus, STILL RUNNING (wf_1a63a627-2ab) — on completion write
report + fold ranked module concepts into the plan.
UPDATE 2026-07-02 (later): tamper module research COMPLETE (106/106 agents) ->
docs/enterprise-requirements/research/tamper-module-roadmap-2026-07-02.md (7 verified findings,
7 refuted). Five candidate modules folded into plan §3a (owner adopt/decline at Phase 3):
(1) chassis-intrusion + rollback-resistant standby tamper-log module [table stakes];
(2) UWB anti-tamper-radio whole-chassis sensing [differentiator — TENSION: RF emitter vs ENT-AIR
radio-free posture, owner call]; (3) USB/PCIe device inventory/attestation (SPDM/TCG);
(4) power-signature fingerprinting as screening tier (PoC-grade, dormant-implant blind spot);
(5) environmental/standby sensing = commodity, fold into (1). BOTH research tracks now done +
committed. NEXT: Phase-1 drafting — REQUIREMENTS-FORMAT.md + hub register + per-family module
registers + conformance matrix, seeded from the two research reports.
UPDATE 2026-07-02 (Phase 1 DONE): enterprise requirements registers drafted ->
docs/enterprise-requirements/: REQUIREMENTS-FORMAT.md (REQ-<UNIT>-<AIR|NET|COMMON>-NNN schema,
5-column rows, DRAFT->PROPOSED->RATIFIED per section); hub-enterprise-requirements.md (11 sections,
47 REQs: PolarFire identity/attestation, CRA firmware floor, northbound Redfish/SNMPv3/OpenMetrics/
syslog, uplink PHY reversal to standard 1000BASE-T [Phase-4 spec edit], locked-interface carry-ins,
fail-detected redundancy [D-ENT-6], §2.9 graduation, rollback-resistant tamper log, FMEA, lifecycle);
module-requirements-common.md (17 REQs incl. 1-Wire identity D-ENT-5, ENT-AIR radio posture,
fail-passive interposer FMEA, screening-tier fingerprinting) + 4 family delta files (24pin/eps/pcie/
12vhpwr) + module-conformance-matrix.md (legacy SKUs vs enterprise Hub, 3 standing risks).
scripts/cec_req_lint.py (ID/SHALL/verify-vocab/spec-§-resolution; only 'spec §'/'[LOCKED §' segments
resolve) wired into checklist.sh — full checklist EXIT 0. 86 REQs total, all DRAFT pending owner
Phase-3 review. NEXT: Phase-2 research items 1-8 (PolarFire sizing, uplink, RJ-11, redundant power,
RTOS stack, compliance regime, radio-free MCU survey) or owner review of the registers.
UPDATE 2026-07-02 (Phase 2 DONE): all 8 surveys complete + committed ->
docs/enterprise-requirements/research/phase2/ (survey-1..8 + INDEX.md synthesis). Verdicts:
MPFS095TS/FCVG484 (S-suffix=Athena, owner confirm); VSC8662 on MSS-SGMII + MagJack + office-grade
OV (OQ-14 closure proposal); RJ-11 = tamper-loop+dry-contact define (merge w/ OQ-60!); TPS25940
eFuse fronts + kept TPS2121 cascade (as-built granularity gap found: 5VSB_SENSE reads OR'd node);
CAN redundancy = fail-detected ONLY (dual-bus foreclosed by locked link; 6 REQ candidates 054-059);
Zephyr + HSS+MCUboot/wolfBoot two-tier boot + wolfCrypt-FIPS boundary + SNMPv3 prune; CRA dates
confirmed (2026-09-11 reporting RETROACTIVE — platform-wide, Annex III Class I gray zone = new
owner item); radio-free = option (a) STM32G4/P4, fused-off ESP32 DEAD (no Wi-Fi eFuse exists).
CROSS-SURVEY: 5VSB budget collision (PolarFire can't run on 5VSB — MAIN_5V primary, REQ-025 split);
NanoKVM AIR-egress contradiction; ATR-vs-radio-ruling coupling. Owner-queue updated (6 new items);
INDEX.md carries the Phase-3 register edit queue. NEXT: owner Phase-3 review (D-ENT-3/5/6 on the
survey evidence) then register edits + Phase-4 spec promotion.
UPDATE 2026-07-02 (owner rulings applied — resolve-all pass): owner ruled in-session: (a) NOT
selling to EU yet, keep open → CRA = EU-entry-conditional gate (new lint token 'EU-entry';
REQ-HUB-COMMON-094; Annex III question deferred to the EU-entry trigger); (b) NanoKVM = optional
module, excluded from ENT-AIR base builds, customer-attached KVM outside the zero-egress guarantee
(REQ-HUB-AIR-059); (c) "resolve all of these" → adopted: S-suffix MPFS095TS baseline (001),
RJ-11 security-I/O define wins the shell over OQ-60 (033), SNMPv3 pruned (020), radio-free option
(a) STM32G4/P4 + fused-off STRUCK (MOD-AIR-020/021), eFuse-fronted §2.9 + MAIN_5V-primary (060),
power-posture split (new 026), survey-5 REQ 054-058 adopted, compliance split 090→094-099+102 /
091 narrowed (090 tombstoned, IDs never reused), per-module SBOM row (MOD-COMMON-052). Registers
now 100 REQs / lint OK. Owner-queue row rewritten: resolved items recorded; REMAINING: D-ENT-6
mapping, D-ENT-3 RFQs, D-ENT-5 leftovers (1-Wire/provenance/mezzanine/ATR/key-custody/SBOM-format),
wolfSSL FIPS engagement at firmware kickoff, Phase-4 spec revision (owner pen). NEXT: Phase-4
spec-revision drafting for the owner, or D-ENT-6 evidence prep.
UPDATE 2026-07-02 (CEC-KVM + spec revision draft): (1) Owner floated a CEC-built network-hardened
KVM ("NanoKVM Pro PCIe is just a baseboard carrier") — verified: NanoKVM-PCIe = SG2002 carrier
(slot-powered, HW H.264/5), NanoKVM Pro = RK3588; both open-source COTS-SoC carrier designs, so a
CEC carrier + CEC-signed minimal image is feasible. Assessment recorded as plan §3a candidate 6:
honest boundary = a KVM is a Linux-class device (never meets the hub no-Linux bar) → hardening =
CEC image + TLS-only + no cloud + own SBOM/PSIRT + hub keeps treating it untrusted (defense in
depth); killer feature = ENT-AIR no-network variant (visual vantage without egress). Two-step
trajectory (carrier+image first, full SKU second). Adoption = OQ-75 in the spec draft.
(2) SPEC REVISION v1.2.0 DRAFTED → docs/spec-revision-v1.2.0-draft-2026-07-02.md (10 surgical
edits: new §13 enterprise line, §1 table rewrite, tier-agnostic amendment, OQ-7/OQ-14-ent/
OQ-53..56-ent closures, OQ-60 disentangle, new OQ-75..78; 2 owner decision boxes: D-ENT-6 mapping
[recommended ENT-NET=3, ENT-AIR=4+redundancy-std] and OQ-75 KVM step order). Queued in owner-queue
§3. NEXT: owner applies/approves the spec edits; then CLAUDE.md + hub READMEs + register Phase-4
gate flips ride the same change (EDIT 10 list).
UPDATE 2026-07-02 (second owner ruling — D-ENT-6 RESOLVED): "both of these guys being in ENT ...
with a SKU differentiator" + MC gets an INDEPENDENT COMPUTE WATCHDOG and an optional FAIL-FUNCTIONAL
tri-tier design with a VOTING PAIR as the maximum variant. Recorded: ONE enterprise line, orthogonal
SKU axes — posture (ENT-NET/ENT-AIR) x availability (base fail-detected / MC = watchdog + redundancy
pack / MC-Max = voting pair, hub-compute-plane-scoped fail-functional; sensing stays single-path).
Landed: plan §1a.6; REQ-HUB-COMMON-103 (watchdog) /104 (voting pair) /105 (SKU ladder+identifiability);
all D-ENT-6 gates flipped (103 REQs lint OK); spec draft v1.2.0 updated (EDIT 2 one-line ENT table,
new §13.8 availability ladder, OQ-79 opened, decision boxes now just OQ-75); owner-queue updated.
KVM: cited recs list DUE AT OQ-75 KICKOFF (FOLLOWUPS entry). Survey 9 (watchdog part class + voting
topology, sonnet, background) IN FLIGHT -> commit to research/phase2/ on landing + refine REQ-103/104
if warranted. NEXT after survey 9: owner applies v1.2.0; EDIT-10 follow-through rides that change.
UPDATE 2026-07-02 (spec sheets + BOMs): docs/enterprise-requirements/spec-sheets/ —
hub-ent-spec-sheet.md (6-SKU matrix NET/AIR x base/MC/MCX; full spec table traced to REQs/surveys;
engineering BOM by subsystem A-G w/ per-SKU roll-up: NET-B ~\$180-235, AIR-B ~\$172-225, MC +\$8-27,
MCX +\$152-208 parts-only @100q [est/RFQ]; 8-port Pro-base working baseline flagged; watchdog row TBD
pending survey 9; PCB class jump note) + module-ent-spec-sheets.md (common deltas incl. ONE
radio-free-build-serves-both-postures recommendation [needs owner ratify]; 24pin=G431 ~cost-neutral;
EPS/PCIe = Pro tier w/ ADS131M08 baseline +\$12-19, DETECT->4.7k; 12VHPWR = existing Pro design +\$1-3;
7 cross-family open rows incl. OQ-76 identity + fast-ADC choice + INA240 count). Survey 9 STILL IN
FLIGHT -> update hub sheet §F + REQ-103/104 on landing. NEXT: survey 9 landing; owner: v1.2.0 apply,
one-build recommendation, OQ-76/79 calls.
UPDATE 2026-07-02 (survey 9 landed + applied): research/phase2/survey-9-availability-ladder.md —
watchdog = small safety-MCU class, S32K3 non-lockstep REC (Zephyr-native; Hercules TMS570LS0432
$8.24 / AURIX TC222L $9.53 alternatives; TPS3813K33 $1.51 backstop option; part-class = OWNER GATE
mirroring D-ENT-2); "independent" concretized (own oscillator + own PG-monitored LDO off arbitrated
5VSB; two-tier escalation: soft reset -> MAIN_5V eFuse EN force-STANDBY); 2oo2+watchdog-arbiter
VALIDATED (fabric-arbiter rejected: shares die/rails); checkpointed-NOT-lockstep sync (PCIe NTB
[firmware confirm] + private 3-node CAN w/ 2x TJA1051T/3; NO shared flash/DDR); voted boundary =
tamper-log writes + Appendix-D actuation ONLY (northbound reconnect-tolerated, CAN session-
continuous); N/N-1 rollout diversity = common-mode mitigation (not fix); NO SIL/ASIL claims;
MC adder ~$22-35, MC-Max +$150-195 + unpriced PCB-class step. APPLIED: REQ-103/104/105 refined
(lint OK), spec sheet §F/G + roll-ups updated, variants plan §7/§8 updated, INDEX verdict 9 added.
STILL IN FLIGHT: 4 subsystem BOM agents (A compute / B uplink / C module-IF+base / D power) ->
assemble docs/enterprise-requirements/spec-sheets/hub-ent-bom-detailed.md on landing (+ MC/MCX
block F/G from survey 9 parts: S32K3xx + TPS3813K33 + 2x TJA1051T/3 + XO + LDO).
UPDATE 2026-07-02 (THIRD OWNER RULING — T1 module link): "replacing the RS-485 with 100BASE-T
for bidirectional + sub microsecond" → ENT module streaming = 100BASE-T1 single-pair on locked
pair 2 (pins 4/5), bidirectional, sub-µs fleet TIME SYNC (PTP/gPTP; sub-µs = SYNC not latency —
frame ~7µs; ns FREEZE stays OQ-60 trigger). DETECT = locked 10k CAN+T1 class. OQ-20 ENT-resolved;
RS-485 stays consumer Pro. PROPAGATED: plan §1a.7 (3rd ruling); REQ-HUB-COMMON-043 rewritten
(DUAL-MODE ports: T1 primary + RS-485 RX compat, DETECT-selected — compat-drop = owner sub-choice)
+ NEW REQ-HUB-COMMON-106 (sub-µs sync, fabric PTP timestamps) → 104 REQs lint OK;
REQ-MOD-COMMON-003 rewritten (T1 + RMII-MAC MCU consequence: G4 has no MAC → P4/STM32H5, survey 10);
REQ-MOD-COMMON-040 tier reworded; module spec sheets updated (streaming rows, DETECT 10k, MCU rows,
EPS delta swaps THVD1450→T1 PHY); spec draft: new §13.2a + OQ-80. SURVEY 10 IN FLIGHT (T1 PHY parts,
hub 8-port fabric MAC/switch architecture + LE budget, PTP accuracy, P4-vs-H5, dual-mode cost).
HUB BOM IMPACT PENDING: BOM-C's RS-485 §3 becomes the dual-mode/compat question; 8× T1 PHY rows +
fabric data plane land with survey 10. BOM agents A/B/D still in flight (A's children: MIC22705 =
Icicle/Discovery VDD-core design-in; W25Q128JVSIQ verified [SSIQ/SNIQ phantom]; LP5907 can't do
1.05V VDDA → TPS7A20 line; TPS62131/32 for 1.8/3.3 fixed).
UPDATE 2026-07-02 (DETAILED BOM ASSEMBLED): all four subsystem BOMs landed + committed ->
spec-sheets/bom-detailed/{bom-a-compute,bom-b-uplink,bom-c-module-if-base-secio,bom-d-power}.md
+ MASTER hub-ent-bom-detailed.md (rev 0.1). Key reconciliations (parent BOM-A missed its own
children's findings — they reported to me directly): VDD core = MIC22705YML-TR (7A, BOTH kits'
actual part — kills the 3A headroom risk; MPM3833C keeps the light rails); ONE DSC1123BL5 125MHz
LVDS osc ALL SKUs (kit-verified shared MSS/SGMII refclk; BOM-A's 50MHz Y1 deleted, NET-only
population corrected); flash upgraded W25Q256JV per REQ-107; JTAG = FTSH-105 (kit J23) + adapter
note; cross-cutting external ADC resolved = ADS7830-class assigned to subsystem C. Per-SKU parts
totals (pre-T1, no DDR): NET-B ~\$199-248 / NET-MC ~\$224-283 / NET-MCX ~\$379-483 / AIR-B
~\$181-229 / AIR-MC ~\$190-247 / AIR-MCX ~\$340-440. Stock-risk register (9 rows) + 14
phantom/corrected parts logged. PENDING: survey 10 (T1) -> master §5 restructure (8x hub T1 PHYs,
dual-mode vs compat-drop, module RMII MCU) + BOM-C §3 conditional. Open: Power Estimator run,
SPI-strap polarity, SGMII AC-coupling seam, DDR decision, eMMC MPN, S32K31x sibling RFQ.
UPDATE 2026-07-02 (FOURTH OWNER RULING — mis-plug fail-safe): with a real 1000BASE-T jack on
ENT-NET, a live-network/PoE cable into a MODULE port is now foreseeable misuse. NEW
REQ-HUB-COMMON-110 + REQ-MOD-COMMON-053 (109 REQs lint OK): withstand 802.3 signaling AND 57V PoE
(all modes/polarities incl. passive injectors), NO damage, self-recovering, detected+alarmed+logged,
verified by injection TEST both ends. Spec draft: §2.4 ENT re-scope block added (consumer
ratification STANDS; ENT build delta only). Baseline per-pin analysis: CAN ok (TJA1051 ±58V —
verify continuous), DETECT dies (PESD not continuous-rated -> series element), pin1 5VSB needs
60V-class blocking (hub sources / module receives into 6.5V-max LDO!), pin7 needs defined
treatment, T1 pair per PHY fault rating. SURVEY 11 IN FLIGHT (protection network parts + costs +
compliant-PSE detection analysis + test procedure; feeds survey 10's PHY pick + BOM-C/module BOMs).
UPDATE 2026-07-02 (SURVEY 10 APPLIED): T1 link resolved -> research/phase2/survey-10-t1-module-link.md.
Hub 8-port architecture = 2x LAN9370 (4-port T1 switch, integrated PHYs + 802.1AS/1588v2 HW
timestamps, \$7.21 ea) -> 2 fabric RGMII bridge MACs (~5% LE) — beats soft-switch (17-33% LE vs thin
vendor docs), SJA1110 (6-port cap+NDA), KSZ9897 (dead end, confirmed). Module PHY DP83TC814S-Q1
\$2.39 default (TJA1103 \$1.49+1588 NDA-flagged). Module MCU = ESP32-P4 UNIFORM (reuses 12VHPWR Pro
NRE; H563 fallback). RS-485 COMPAT DROPPED on ENT ports (survey rec, owner-review tag — consumer Pro
streaming dark on ENT per §8 pattern, CAN unaffected; saves \$9-30/hub; conformance matrix updated).
Sub-µs = design target (802.1AS <1µs/7-hop vs our 1-2; HW stamps every stage; 6.72µs frame time
verified) — BENCH VERIFY before claiming REQ-106 met. Net hub delta +\$14-24 all SKUs; module
+\$3.0-4.2. REQ-043/003/106 refined (110 REQs lint OK); master BOM §5 resolved, per-SKU totals now
NET-B \$213-272 .. AIR-MCX \$354-464. STILL IN FLIGHT: survey 11 (mis-plug protection — its T1-pair
answer now targets the DP83TC814/LAN9370 MDI fault ratings).
UPDATE 2026-07-02 (FIFTH OWNER RULING — pin-7 suitors cleared + identity mechanism): (1) 1-Wire
identity OUT — replaced by the poke-and-ack topology + MCU-resident-key challenge-response over
CAN/T1 (OQ-76 resolved-by-direction; ≈$0 parts; module sheets identity row updated); (2) DETECT
Kelvin return OUT (unneeded); (3) pin-7 SYNC/FREEZE ADOPTED (REQ-112 PROPOSED→ADOPTED, gate now
Phase-4 spec edit — locked-table change formalizes at v1.2.0; OQ-81 marked resolved-by-direction);
(4) NEW REQ-HUB-COMMON-113: module validation is inherently untrusted → hub cross-validates every
module across >=2 independent surfaces (DETECT class + poke-and-ack, CAN challenge, T1 checks,
power-signature consistency) and alarms on inconsistency — the owner's cross-dimensional-analysis
rationale captured as a requirement. 112 REQs lint OK. STILL IN FLIGHT: survey 11 (mis-plug
protection; its pin-7 answer = driven-line case now).
UPDATE 2026-07-02 (SURVEY 11 APPLIED — detailed-BOM package now COMPLETE end-to-end): last
in-flight agent landed -> research/phase2/survey-11-misplug-failsafe.md. Key findings applied:
(a) module pin 1 is a 5VSB INPUT so a series diode CANNOT protect it (fault current flows the
normal direction) — active 60V auto-retry eFuse required, TPS26621DRCT baseline $2.07
(REQ-MOD-COMMON-053 rewritten); (b) TJA1051T/3 = ±58V CONTINUOUS DC datasheet-confirmed (CAN pins
covered as-is); (c) hub-side +$5.6/all-SKUs protection rows in master BOM §6a (SS110 replaces
SS16 [60V margin], SMAJ58A, DETECT series R, pin-7 network, T1 CMC + ≥100V series coupling caps
[the actual DC-block] + PESD2ETH100); module +$2.7 streaming / +$2.15 24-pin; (d) REQ-HUB-
COMMON-110 gains resettable-not-one-time-fuse parenthetical; (e) pin-7 reconciliation note: survey
predates the 5th ruling, so bleed-R treatment becomes series R + LOW-CAP clamp sized to pass the
≤100ns SYNC edge (schematic-capture task); (f) per-family injection-test procedure (survey §h).
Per-SKU totals now NET-B $219-278 / NET-MC $244-313 / NET-MCX $399-513 / AIR-B $201-259 / AIR-MC
$210-277 / AIR-MCX $360-470. 112 REQs lint OK. NOTHING left in flight — the owner asks (spec
sheet + complete detailed BOM both hub variants + module drafts) are DELIVERED. Next milestones
are owner-gated: v1.2.0 spec application, D-ENT-5 remaining line items, D-ENT-3 RFQ pass,
REQ-111 PD-on-uplink adopt/decline.
UPDATE 2026-07-02 (PIN-7 HEARTBEAT CHALLENGER — owner exploration, drafted PROPOSED): owner
floated pin 7 ALSO as a heartbeat challenger (hub challenges over pin 7; trusted module answers
per signed-firmware-prescribed method; no answer → automatically untrusted). Drafted as
REQ-HUB-COMMON-114 (challenger: nonce over CAN/T1 compute-then-respond, hardware-timed answer on
pin 7, single-digit-µs window = distance-bounding-lite → PORT-BOUND + TIMING-BOUND, the only
port-bound crypto surface for CAN-only 24-pin; N=3@1Hz miss → auto-UNTRUSTED: quarantine-tagged
telemetry, alarm+tamper-log, MC-Max vote exclusion, re-admit only via full re-attestation;
legacy-claim = demotion not bypass; FREEZE level-dominant never masked; jam = fail-secure) +
REQ-MOD-COMMON-013 (responder: timer output-compare/ETM hardware edge, dormant on non-challenging
hubs — locked graceful-degrade preserved; ≈$0 parts). ARCHITECTURE consequence folded into
REQ-112 + v1.2.0 OQ-81: ENT hub pin 7 becomes PER-PORT point-to-point into PolarFire fabric
(wired-OR semantics via deterministic fabric relay) — buys challenge discrimination, survey-11
mis-plug containment, sub-ns inter-port skew; module electrical contract unchanged. REQ-113
surface list +heartbeat. Owner-queue D-ENT-5 row: adopt/decline pending (like REQ-111). Honest
residual recorded: proves key+port+real-time, NOT firmware integrity; extracted-key attacker
must still answer at the port in hardware time. 114 REQs lint OK.
UPDATE 2026-07-02 (SIXTH OWNER RULING — "review these addendums and implement"): BOTH addendums
ADOPTED + implemented. (1) Heartbeat: REQ-HUB-COMMON-114 + REQ-MOD-COMMON-013 PROPOSED→ADOPTED
(gate now Phase-4 spec edit, rides the v1.2.0 pin-7 table edit); REQ-114's "only port-bound
surface for CAN-only families" rationale REWORDED (no CAN-only ENT family remains) to
"independent of the T1 stack — does not share fate with a dark/compromised T1 path".
(2) 24-pin T1: REQ-MOD-COMMON-003 now covers EVERY ENT family (24-pin included; rationale:
validation surfaces on the fleet's most load-bearing validator + gPTP + fleet logistics, NOT
bandwidth); ESP32-P4 UNIFORM across all four families (G431 pick superseded; REQ-MOD-AIR-020
baseline updated; survey-10 P4-vs-H5 sub-choice thereby resolved); DETECT 10k across the line;
REQ-MOD-COMMON-053 T1 protection now every family (+$2.7/module uniform, master BOM §6a);
24-pin ENT BOM delta recomputed +$5-7 → ~$40-44 class (hub side $0, ports already T1);
family registers EPS/PCIE/HPWR-002 got the T1-replaces-RS-485 rider; spec-draft §13.2a
extended (6th ruling + survey-10 T1-only correction of its stale dual-mode text). ALSO swept
pre-existing survey-10 drift the review exposed: OQ-5 marked MOOT for the ENT hub (stays a
consumer-Pro question) in conformance-matrix/hub-spec-sheet/variants-plan; BOM-C §3 RS-485
bank marked SUPERSEDED (master §5 reconciliation governs); variants-plan block diagram +
IO-budget gained the T1 and per-port pin-7 fabric rows; hub spec-sheet §C subtotal honest
($30-46 incl. T1 plane). REMAINING PROPOSED-pending: only REQ-HUB-NET-111 (PD-on-uplink).
114 REQs lint OK.
UPDATE 2026-07-02 (SEVENTH RULING — "I sign off"): MPFS095TC (PolarFire SoC Core) = the ENT hub
PRODUCTION BASELINE, conditional on FAE confirming Core retains PUF secure boot + user TRNG +
tamper detectors (failure reverts to the S ladder); MPFS095TS = the HS POPULATION OPTION on the
same part-agnostic SerDes-free FCVG484 land (Athena/DPA for high-assurance channels). Applied:
REQ-001 rewritten (gate D-ENT-3), REQ-030 (uplink SHALL NOT depend on fabric SerDes — MSS-GEM
SGMII if Core retains it, else RGMII; DP83869 serves both), REQ-104 (MCX state-sync = fabric/
LVDS, PCIe/NTB dead on Core + was unvalidated), hub spec-sheet §2 compute+security rows + §3.A
part row, master BOM §3a (TC rung = PRODUCTION BASELINE; TS drought row no longer gates),
v1.2.0 draft (§13.1 + tier-table row + intro), owner-queue f3 RESOLVED (TC prototype buy 3-5
= proceed w/ dev-kit order; 250TS hedge = optional HS-early-stock only). Sourcing context:
research/sourcing-alternatives-2026-07-02.md (3-lane survey + the TC finds). ALSO IN FLIGHT:
the suite-review reconciliation agent applying the 20 verified findings (F01 + math cluster
F04/F12/F13 + partial batch already committed; remainder commits at agent completion — check
git status; findings report at scratchpad/suite-review-report.md, workflow wf_fd0ca2c2-929).
UPDATE 2026-07-02 (NEXT-TRAJECTORY SCOPED + SUITE REVIEW IN FLIGHT): (1) Owner asked for a
full-suite fan-out review (Standard/Pro/Max/ENT) — Workflow wf_fd0ca2c2-929 RUNNING (10 sonnet
lenses -> opus triage -> adversarial verify -> opus synthesis); on completion: apply confirmed
fixes + report. Resume via scriptPath+resumeFromRunId if killed; journal at the workflow
transcript dir. (2) Owner asked to "parallelize and scope the next trajectory" — DONE: 5
parallel sonnet scopes banked at docs/enterprise-requirements/research/next-trajectory/
scope-{firmware-fabric,security-protocols,board-program,validation-compliance,
ratification-package}.md + synthesis docs/enterprise-requirements/next-trajectory-2026-07-02.md
(5 workstreams A-E; dependency graph; start-now list of 11 items; owner decision queue §4 w/
minimal-unblock-boards set = REQ-111 + RS-485 nod -> v1.2.0 -> OQ-11 -> Phase-5; NEW owner
spend asks mirrored to owner-queue: dev-kit/EVB order ~$600-900 + Libero license; engineering
defaults agents proceed on listed in §4; waves 0-3). Wave-0 exit criterion: suite-review
findings patched BEFORE the ratification brief freezes. NEXT concrete agent work (wave 0):
ratification brief + 6 decision one-pagers, CEC-KVM cited-recs (FOLLOWUPS promise), RFQ
package, threat model + key hierarchy + heartbeat protocol DRAFT, verification-matrix
generator, bench specs, KiCad library intake (~30 parts), FCVG484 breakout study.
UPDATE 2026-07-02 (~19:30 — WAVE 0 COMPLETE + PRODUCT MATRIX): owner approved wave-0 ("go
ahead") + asked for a product matrix map. DELIVERED, all committed/pushed: (1)
docs/enterprise-requirements/product-matrix-2026-07-02.md (3 ENT axes: posture x availability
x silicon; 6 hub SKUs x base/HS = 12 configs one PCB; 5 module SKUs; cross-compat table). (2)
WAVE 0, five parallel agents ALL LANDED: ratification/ratification-brief-2026-07-02.md (5 nods
+ 7 real reviews, one-pager each in briefs/; minimal unblock-boards chain: REQ-111 + RS-485
nod -> v1.2.0 -> OQ-11 -> Phase-5; OQ-11 R-vs-K verified = genuinely distinct alloy series);
ratification/rfq-package-2026-07-02.md (26 quote lines, MPFS quoted as ONE family = allocation
lever, 6 formal FAE questions gating the 7th-ruling TC condition); research/
cec-kvm-recommendations-2026-07-02.md (10 cited recs + 5-item decision box; PREMISE CORRECTED:
NanoKVM Pro = integrated AX630C board, the carrier architecture is the RISC-V NanoKVM-PCIe);
enterprise-security/threat-model-2026-07-02.md (CANONICAL honest-limits: P4 no-SE residual,
DETECT = only key-independent surface, TC-baseline no-DPA-claim, two-chip seam, pin-7 timing
PROVISIONAL) + key-hierarchy-custody-2026-07-02.md (7 custody decisions OWNER-ACTION-marked;
separate tamper-log key recommended outright); scripts/cec_req_verify_matrix.py +
docs/enterprise-validation/ (114/114 REQs mapped, hash-rot teeth stress-tested, --check NOT
yet wired into checklist.sh — deliberate, pending human review of the seed map). OWNER QUEUE
now: ratification brief review, RFQ send-out, KVM recs sign-off, dev-kit order + TC prototype
buy, Libero license. NEXT agent work (wave 0 tail / wave 1 prep): bench specs + FMEA templates
+ process docs (validation scope), heartbeat protocol spec draft, KiCad library intake, FCVG484
breakout study, wire verify-matrix into checklist after seed-map review.
UPDATE 2026-07-02 (~19:45 — EIGHTH RULING, owner walked the ratification brief): N3 RFQ
RATIFIED but send HELD for a CUSTOMER design sign-off (new external gate!) + "stand up a
prototype for them to review" -> prototype-demo-plan-2026-07-02.md (dev-kit federation rig =
customer demo, ~$1-1.3k basket now the critical path); N4 KVM kicked off; N5 Phase-5 strict
gate; R1 REQ-111 DECLINED (tombstoned, verify I, gate —); R2 v1.2.0 SIGNED OFF — application
STAGED behind the N1 RS-485 confirm (sequencing b-before-a); R3 OQ-11 delegated (Bourns
default, engineering pick) -> selection agent running -> oq-11-shunt-selection-2026-07-02.md;
R4 provenance = evidence-source-only (recorded in REQ-007); R5 mezzanine ADOPTED (REQ-24PIN-
020 rewritten; stacked SKU ENT-AIR-only, beyond-AIR + consumer-side implications = 2 new
FOLLOWUPS); R7 custody direction ratified (offline M-of-N, procedure doc then final signoff).
ANSWERED-PENDING-PICK (answers in the reply of record + owner-queue): N1 (rec: confirm drop —
dual-mode = unauthenticated unprecedented analog bridge, conflicts w/ pins-4/5 DC block, no
install base; CAN degrade already "allows" the module), N2 (rec: SPDX native via west +
CycloneDX derived-on-demand when PSIRT wants VEX), R6 (rec REVISED: passive-receive-only RF
NET-only, DEFER the active emitter — intentional-radiator certs $25-75k class buy only
dormant-implant detection). NEXT: when N1 confirmed -> APPLY v1.2.0 to the Ground-Truth spec
(big careful edit, signed off); OQ-11 sheet lands -> record closure; brief status block at top
of ratification-brief-2026-07-02.md is the live scoreboard.
UPDATE 2026-07-02 (~21:00 — SPEC v1.2.0 APPLIED, PHASE 4 COMPLETE IN SUBSTANCE): the
Ground-Truth spec is at v1.2.0 (all 10 draft edits applied + verified: req-lint green =
all 114 register spec-refs resolve, corpus-lint green). OQ-11 FULLY CLOSED same-day
(delegated: EPS/PCIe 0.5mΩ CSS2H-2512R-L500F, 12VHPWR 1mΩ CSS2H-2512R-1L00F; R/K series
don't overlap). Phase-4 gates flipped (REQ-030/112/114/MOD-013 satisfied; MOD-051
satisfied; MOD-031 narrowed to OQ-10/12). CLAUDE.md header now v1.2.0. Wave-0 tail ALL
landed (8 bench/FMEA + 5 process docs + 3 security drafts; custody ceremony 2-of-3 →
OWNER FINAL SIGN-OFF pending). KiCad intake manifest landed
(docs/enterprise-requirements/board-program/kicad-intake-manifest-2026-07-02.md: ~36
net-new rows, 5 fan-out groups A-E; easyeda2kicad v1.0.1 INSTALLED this session —
NOTE: pip install on the ephemeral box, re-install after container recycle; OQ-11 shunts
= zero library work; owner-download list: LTC2358 deferred, JXD1 check-SnapEDA-first;
eMMC + S32K3x rows blocked on MPN decisions). NEXT: launch intake groups A-D + the
group-E MPFS-BGA-script-gen/LAN9370 workstream; then project scaffolds + the shared
P4+T1 reference block schematic; PR to main = the formal Phase-4 CODEOWNERS act (owner
opens on request). Owner pending: hardware order (demo critical path), KVM decision box,
Libero license, custody final sign-off, mezzanine beyond-AIR review, RFQ send at
customer sign-off.
UPDATE 2026-07-02 (~21:35 — ENT HUB SCHEMATIC STARTED, owner directive): hierarchical
multi-sheet capture per hubs/hub-enterprise/SCHEMATIC-PLAN.md (10 sheets: 01 power-input,
02 compute-core [MPFS multi-unit], 03 rails, 04 storage, 05 module-ports, 06 T1-dataplane,
07 uplink [capture BOTH SGMII+RGMII options pending the Core FAE answer], 08 secio-aux,
09 watchdog [S32K344 working part, MC-DNP], 10 voting-pair LAST; one schematic serves all
SKUs via DNP matrix; verification protocol = ERC + scripted netlist assertions
[scripts/check_hub_ent_sch.py, grows per sheet] + conformance checks + BOM cross-check).
FOUR library agents running, COLLISION-SAFE (each owns ONE new symbol file:
lib/cec-ent-{power,net,compute,mcu}.kicad_sym; footprints file-per-part; NO lib-table
edits — I consolidate registration after they land): power/protection group (TPS25940,
MIC22705, TPS26621, SS110, SMAJ58A, DSC1123, W25Q256, ADS7830, RJ-11), net group
(DP83869HM, DP83TC814, JXD1 [skip-if-login-walled], CMC, PESD2ETH100, RClamp, GDT,
LAN9370 ONLY if public pinout — else flag), MPFS FCVG484 GENERATOR
(scripts/gen_mpfs_fcvg484_lib.py from the Microchip ball table, multi-unit symbol w/
SerDes unit annotated NC-on-Core, BGA-484 footprint, 484-ball assertion + 10-ball
spot-check), MCU group (ESP32-P4 orderable-form finding feeds module BOMs, S32K344
[may skip], ADS131M08, generic JEDEC FBGA-153 eMMC land [two-source verify]). NEXT on
their landing: consolidate sym-lib-table/fp-lib-table registration, scaffold the
hub-enterprise KiCad project (root + sheet files), capture sheet 01 per the plan order,
verify per protocol, commit per sheet. easyeda2kicad NOTE: pip-installed on the
EPHEMERAL box — reinstall after container recycle (pip install easyeda2kicad).
UPDATE 2026-07-02 (~23:30 — SCHEMATIC-QUALITY CHARTER + HOOK, owner directive): the owner wants
generated schematics at hand-authored quality with all tooling scoped/implemented + a start hook
at the charter. DONE: docs/schematic-quality-charter.md (T1 layout engine [rotations/wires/
decouplers/text — BUILDING], T2 pin-type auditor [BUILDING — its cec-ent findings = the sheet-02
gate], T3 style linter [BUILDING — hand-vs-generated comparison table is its evidence], T4
composition engine [SCOPED, after T1 integrates], T5 golden sheets [SCOPED], T6 VLM render seat
[SCOPED, workstation-only]; principles: netlist-identity invariance, teeth-first, calibrate-
don't-guess, GUI top rung). Hook: .claude/hooks/schematic-quality-context.sh registered in
settings.json SessionStart (injects the charter head; smoke-tested). ALSO IN FLIGHT: the
one-block-per-sheet RESTRUCTURE agent (owner format correction: sheet 01 → thin parent + 01a-g
leaves, no dashed frames, netlist-identity required, plan §1 amended w/ leaf breakdowns incl.
05a-port ×8 instanced). FOUR agents running total. Integration order on landing: restructure
commits first → T1 integrates → regenerate 01a-g → gates 5/6 adopted → sheet-02 gates on T2
audit → capture continues 05→04→03→02.

## Daughterboard connector iteration 6 — STUDY DONE (2026-07-06, branch claude/schematic-work-continue-59pw41)
Feasibility study only, NO .kicad_* edits (per owner brief). Full record: docs/standard-tier-review/blade-fit-check-2026-07-04.md **addendum 6** + owner-queue D-5a item (e). Verdicts: Keystone 3522 = best floor (4.1mm; legs in-line with slot per p.47 derivation) but DEAD — our 6.35±0.08 blade doesn't reliably enter its closed 6.4mm fuse-width window (0.05 nominal clearance, −0.16 worst); Hunt A (fuse-blade-format RA PCB tab) = empty class. FIND (Hunt B): **TE FASTON .250 PCB receptacle 63968-1 (LIF) / 63969-1 (LCSC C2961150, stock 5; DigiKey depth)** — designed for exactly our 6.35×0.81 tab (thickness = design centre), vertical top entry (app spec 114-2156), 22.9A @30°C-rise, floor ≈4.2 (across-thickness depth un-dimensioned ~3.4–3.7 → FOLLOWUPS). If picked: joint counts re-ratify (atx24 10 / pcie-2 12 / pcie-3 18), boards shrink to ~52.7–56.9/28.0/20.0–30.0mm. 4 TE docs vendored to lib/datasheets/. OWNER PICKS before any regen; stand-pat 3557 stays sound.

## Daughterboard iteration 7 — REGEN LANDED (2026-07-06, owner-ratified TE 63969-1)
Owner ratified addendum-6 + orientation requirement (receptacle hole pair aligned with the blade's holes). PROVEN from TE_63969_customer_drawing_revE.pdf (byte-identical to study download): hole pair ∥ tab width ∥ wall normal ⊥ row, plan-congruent with the 63951-1's Ø1.40/5.08 leg holes — checker-asserted (§3b + §3a rot-0). Depth stays UN-DIMENSIONED (3.7 est; >4.0 ⇒ atx24 falls back to 6.3 pitch — #1 sample item). Counts re-ratified at 22.9A/125%: atx24 10 (3V3 ×2; GND ×4 = 127% hairline surfaced), eps 6/cable, pcie 6/cable (3/polarity). Pitches 4.2/4.7/5.2; boards atx24 61.0×21.4 / eps 28.5×20.0 / pcie 31.0×20.0 (pcie grows honestly). atx24: descents jog to computed mid-gaps (x0+2.1 mod 4.2; old phase-3.15 trick dies at 4.2), SR pads repacked 2×3 + extent owned by W (SR6-on-edge caught by DRC). Seating: float 12.41, receptacle top (8.38) cleared 4.03; detent NOT engaged at nominal (friction-only retention possible — sample). MAIN BOARDS: all TBs property-swapped to 63969-1/C2961150 + adds netlist-verified (24pin TB10→/SENSE3V3_LO; pcie-2 TB15/16/25/26; pcie-3 +TB35/36; TB<cable><idx> next-free), main-board BOM TB lines fixed (were STALE at 3586 since Task 9), ERC unchanged 1 pin_not_driven each. Gates: ERC 0 ×3, DRC 0/0 sev-error ×3 (silk-only at full), checker 113 OKs, keying teeth verified (pcie=4.8 sabotage fails). New fp TE_63969_FASTON_Receptacle_250_Vertical_THT; memo addendum 7; READMEs bannered; CLAUDE.md block; owner-queue (e) RULED. J_SIG 1×4 rework still deferred (D.6). Not committed by me (auto-committer snapshots).

## Daughterboard iteration 8 — EXPLORATION closed STAND PAT (2026-07-06)
Owner ratified iteration-7 density, directed an ampacity/size hunt. Study only (blade-fit memo addendum 8): count-threshold ladder derived (≥24.4A → pcie 4 joints; 30A → atx24 8 but two new 125.0% at-line joints; ≥32.5 → eps 4); 82004 re-mined (Style A = only 0.81-tab receptacle, 22.9A = line rating, no .187 receptacle exists); Zierick read in full (their "25A .250" search hits are TABS — caught; real THT receptacle 1022 = 20A dead, SMT universal 1237 = 25A but ~6.5mm body → atx24 balloons, SMT retention, dead net); bigger-blade dead (no .375 PCB receptacle/tab; maxi-clip ratings don't transfer to half-width blade); b2b power re-checked (mPOWER 18A dead; PwrBlade+/MULTI-BEAM/Ten60 30-48A = erases ALL bare-part sample items but $13-26/module = 3-6x band → premium rung; REDCUBE PLUG 120A over band). VERDICT: STAND PAT on 63969-1/63951-1 — class ceiling + tightest floor. Owner-queue (e) + TODO updated. No .kicad_* or lib change (no strong candidate earned a datasheet vendor).

## Daughterboard iteration 9 — TAB-side study closed (2026-07-06, receptacle frozen)
Study only (addendum 9). Straight-tab class (incl. 63849-1) + SMT tabs (Zierick 25A) killed in-architecture (blade axis/orientation); RA .250 table has exactly 3 members — the one live variant is **TE 928814-1** (CD vendored: TE_928814_solder_tab_63x08.pdf; blade 16.0 vs 20.32 → float 8.3/stack −4.1mm; Ø1.7 detent hole 4.45 from tip = lands INSIDE the 63969 engagement zone, possible real retention; caveats: band centre ~4.45 → receptacle near-roll ~0.7mm off the wall + board edge dips 0.1 below rcpt top at nominal float (re-derive float if adopted), blade 0.8±0.05 wider than the mate's 0.785–0.835, loose-piece only, not LCSC) → recommended as a ~20pc ADD to the OQ-86 sample order, drop-in upgrade if it passes. PCB-EDGE-FINGER worked seriously: stack ~19mm (−13!), −22 tabs, BUT thickness band unpassable at catalog fab classes (JLC ±0.1/±0.05 both fail 0.785–0.835; thickness chained to 0.8 — can't stiffen), ampacity fine at 4oz (1.78mm² vs blade 1.44; 2oz = 0.89 marginal-thermally-ok), contact metallurgy off-label (hard gold + bevel; ENIG wears through) → compaction ENDGAME gated on a bench program + owner posture ruling ("the tab does the reaching" reversal). Side-flip formally dead (no vertical-face-mountable receptacle exists). Beta stands pat on 63951-1. Owner-queue (e) + TODO updated. No .kicad_* edits.

## Iteration 10 — edge-finger deep-dive STUDY DONE (2026-07-06)
No .kicad_* edits. Record: blade-fit-check-2026-07-04.md addendum 10 + owner-queue D-5a iteration-10 sentence. NEW kill-weight finding (addendum 9 missed it): fingers put the blade width IN the board plane -> receptacle rotates 90° -> 7.49mm width -> ~8.0mm row pitch -> boards ~91/46/46mm (+50% length) vs −11.5mm stack. Thickness band unpassable at all PUBLISHED fab classes (JLC/PCBWay ±0.1 @0.8mm verified; full TE SKU table vs PCB classes = none fit; sort-to-band 25–50% EST yield = only catalog unlock). dt_ipc: 2oz×2 = 5.0°C / 4oz×2 = 1.6°C @18.32A — conduction passes, interface is the gate (0.34W spec vs 3.4W worn). Hard gold @0.8 = PCBWay only (no bevel ≥1.2 rule; soft loss); JLC = ENIG flash <10 cycles, bevel OK, ≥50mm finger edge. 4oz answer: JLC has NO 4oz tier (2-layer 1/2/2.5/3.5/4.5oz; 4L capped 2oz); PCBWay 4oz orderable; quotes sandbox-unreachable -> owner recipe §I.5 + coupon spec §I.7 (~$30–60, returns thickness distribution + real invoices). RECOMMENDED: do not adopt for beta; coupons optional with OQ-86 order; posture re-ruling conditional only.

## FEM blade-interconnect audit DONE (2026-07-06, code pass)
Joint element landed (cec_synth_pipeline: JointSpec/joint_solve, TE 63951/63969 factory, Rth calibrated to the 22.9A/30C TE datum, worn 10mOhm case, gate teeth; anchors 15/15; additive contract proven — eps/pcie solver outputs byte-identical to pre-change, atx24 differs only on the intentional -12V fix). cec_dcir gained src/sink terminal overrides. FULL-STACK FINDINGS: joints all pass (worst atx24 GND 18.6C = the 127% hairline); **F1: atx24-out-db In2 0.3mm lanes carry full rail aggregates = FUSING (384mV/11.5W @30A on +5V, 2.5D runaway) — REGEN REQUIRED, owner-queued**; F2: eps/pcie board-level dT 217/117C at worst-case basis in still-air/no-sink model — OQ-86 soak gates the disposition (model check numbers: 17.3A→17C, 18.3A→19C, 22.9A→30C, several-mOhm contact = worn signature). Doc: docs/standard-tier-review/blade-interconnect-thermal-2026-07-06.md; 3 daughterboard READMEs corrected (dated). SB-08 unaffected by construction (no -12V/joints on eps-8pin); re-run in-container next session per practice.

## 2026-07-06 (late) — Thermal wave-1 arc LANDED, heading to PR+merge (owner: "PR this and merge")
- T1b verified (166/166 thermal family). Integration: THERMAL_SOURCES + THERMAL_CONNECTOR_SCENARIOS added to REGISTRY_OPTIONAL (advisory, fail-safe); electrothermal_solve/physics_gates UNTOUCHED → SB-08 golden + test_am04_anchors byte-identical (golden calls electrothermal_solve directly, bypassing the cascade). No test references REGISTRY_OPTIONAL.
- atx24-out-db F1 fix VERIFIED (I ran the DC-IR leg the crashed agent aa4d9c83 was on): +5V 384→62.6mV, cold joule 592W→3.82W. F1 resolved; F2 (board-level no-sink) remains = parity w/ eps/pcie, soak-gated, NOT relaxed.
- eps/pcie solid-joint fix (owner "you have thermal reliefs as well"): route_simple() → ZONE_CONNECTION_FULL, dT −40% both. All 3 daughterboards now solid.
- ENT KVM carrier (crashed agent aa6907e2): GND↔LT_INT merge FIXED — R48/R49 shared a compose row, stubs overlapped @ y161.29; moved R49 y66→54. GND 147/LT_INT 3. 11 residual ERC all cosmetic (MCU-GPIO bidirectional pin-type ×6 + U7 ganged outputs ×4 + dup PWR_FLAG). DRAFT.
- Both crashed agents (aa4d9c83 F1, aa6907e2 KVM) died on Fable-5 limit; I finished their work on Opus.
- Thermal maps rendered → docs/standard-tier-review/thermal-maps/ (matplotlib pip-installed this session; not in base python).
- NEXT after merge: standard-bundle "sell it" chart (owner ask); Task 13 Max spec rev (owner part-stamp gated).
