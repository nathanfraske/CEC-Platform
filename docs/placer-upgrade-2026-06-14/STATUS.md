# Placer-upgrade MV checklist — implementation status (2026-06-14)

Plan of record: `plan.json`. Governing constraint: `anti-overfit-charter.md` (the reference is the
holdout — VALIDATE against it, never tune toward it). All work in `scripts/cec_synth_pipeline.py`
unless noted; tests in `tests/test_placer_oracle.py` (+ `tests/test_corridor_model.py` unchanged).

## DONE

- **MV1 — netlist → materialize** (prior session): `_ensure_netlist_path` + `materialize()` sch-export
  fallback. A Hub candidate now writes a `.kicad_pcb` (the FileNotFoundError blocker is gone).

- **MV2 — oracle Stage-1 derivation.**
  - *(general, principled)* `_role(ref, value, fp, nl=None)` + `_connector_net_role` + `_is_rail_net`:
    a bare `J*` connector is classified by the FUNCTION of its nets — a power-only connector (rails +
    GND) is `power_in`, a data connector is `host`. Fixes the J_5VSB mis-key (no `IN` substring). The
    WHY ("function determines edge-grouping") generalizes; WHICH edge is a per-board input.
  - *(per-board input)* `oracle_stage1_answers(cfg, ref_pcb)` derives `size_target_wh`, `edge_override`
    (each connector binned to its nearest reference edge), `mount_pos_override` (board-relative coords),
    `antenna_edge` + `respect_antenna_keepout`. `apply_oracle_stage1(cfg)` fills cfg.params via
    `setdefault` (human answers override the oracle). `seed_anchors(edge_override=)` consumes the map and
    now places over ALL FOUR edges (was top/bottom/right only). `place_mechanical(mount_pos_override)`.
  - Validated on the committed Hub: J2–J5→top, J_5V/J_5VSB→right, J_KVM/J_USB→bottom; outline 98.1×74.1;
    antenna left; the map round-trips back through `seed_anchors` to the reference's own edges.

- **MV3 — reproduce-the-reference similarity (DIAGNOSTIC).** `oracle_similarity(cand, ref_pl, nl)` →
  (score, detail) over four structural terms (connector-edge match / anchor distance bucket /
  IC-cluster tightness ratio / HPWL closeness). `Candidate.similarity` + `similarity_detail`, computed
  in `place_candidates` only when a reference is set, printed in the top-3. **Never a rank key**
  (`_candidate_sort_key` deliberately excludes it — a test enforces this). Identity = 1.0, scramble < 1.

- **MV4 — proxy_score composite.** `proxy_score(proxy, weights, ref_proxy)`: with NO reference it
  returns EXACTLY `proxy['hpwl']` (zero behaviour change on boards without an oracle); with a reference
  each term is normalized by the reference's value (the reference sets only SCALE) and combined
  HPWL-dominant (`hpwl 1.0 / rudy 0.25 / thermal 0.15 / hub 0.5`). Sort key swapped to
  `(residual, corridor_cross, proxy_score)`; knobs in `cfg.params['proxy_weights']`.

- **MV5 — Hub-domain structural terms (measurement + selection).** `build_hub_model` + `hub_score`:
  `port_even` (uniform RJ-45 pitch + on-edge), `antenna` (PCB-antenna lobe off a board edge),
  `power_cluster` (muxed-5V input-loop cohesion — excludes sense nets + edge connectors, linear `1−frac`,
  no magic divisor so it never red-by-design penalizes the hand board), `usb_prox` (USB↔ESP). Gated to
  fire only on ≥2 ganged RJ-45 ports + an ESP (cable/sensing modules inert). Folds into `proxy_score`
  via `hub_penalty` at a small weight. The reference scores well on every term (hub_penalty ≈ 0.27);
  the synth output scores worse (≈ 0.60) — the diagnostic correctly discriminates the gap.

## DEFERRED (the generative closers — measurement is in, generation is the next lever) → FOLLOWUPS

- MV5 power-cluster **cohesion placement sweep** (a barycentric pull on the mux/hold-up/LDO group) and
  the **antenna-edge ESP seed** (bias the ESP toward its derived antenna edge): the terms MEASURE these
  gaps and the sort applies SELECTION pressure, but no pass yet GENERATES candidates that close them.
  Per the plan, MV5 is measurement-first ("add the term, watch similarity rise, keep what helps").
- The L-tier items (L1 route leg, L2 Tier-B routed-length calibration, L3/L4 compaction/coupling,
  L7 validation gate) are post-MV.

## HUB PIPELINE TEST RUN (2026-06-14, in the kicad10 container) — IT WORKS

Recipe (reproducible; build/hub-test/ is gitignored):
```
docker run --rm -v $PWD:/work -w /work cec/routing:kicad10 python3 -c "
import sys; sys.path.insert(0,'scripts'); import cec_synth_pipeline as S
cfg=S.Config.load('hubs/hub-standard')
cfg.params['oracle_reference_path']='hubs/hub-standard/hub-standard.kicad_pcb'
S.elicit_requirements(cfg,{'antenna_keepout':True}); S.apply_oracle_stage1(cfg)
W,H=cfg.params['size_target_wh']
S.run_sweep(cfg,[(W,H)],strategies=S.STRATEGIES,seeds=(0,1),out_dir='build/hub-test',render=True)"
```
Stages exercised: Stage-1 oracle derivation → place_candidates (6) → materialize → render → DRC. ALL ran.

Result (best = thermal_separated/seed1):
- **frame correct**: size 98.1×74.1 derived; 8 connector edges from the oracle; materialized 80-part board 98.2×74.2; render written.
- **residual 4, corridor_cross 0** (near-legal placement).
- **similarity 0.705** vs the reference's 1.0; **HPWL 2498.6 = 1.25× the hand board's 2001.8** (down from the pre-MV ~1.84× — the oracle frame is the win). The reference proxy_score (~1.53) correctly ranks below the synth best (1.871) — MV4 calibration is well-posed.
- **hub_terms**: port_even 1.0, power_cluster 0.91, usb_prox 0.597, **antenna 0.0** (the ESP did not land on its left edge — the MV5 generative-closer gap, see FOLLOWUPS). hub_penalty 0.373.
- **DRC 575**: ~506 COSMETIC (silk_overlap 199 / silk_over_copper 199 / silk_edge 27 / lib_footprint 81); ~64 real-structural (shorting 9, courtyards_overlap 4, copper_edge 17, solder_mask_bridge 9, pth/npth_in_courtyard 30) tracking the residual-4 overlaps; **211 unconnected = UNROUTED** (the route leg L1 is not wired — this is placement-only).

VERDICT: the place→materialize→render→DRC→score pipeline is functional on a real fab-class board with the
correct oracle-derived frame and a quantified gap. To reach a clean routed Hub the remaining levers are the
MV5 generative closers (esp. antenna-edge ESP seed) + a legalizer tightening (residual 4 → 0) + the route
leg (L1). All in FOLLOWUPS.

## FULL PIPELINE (place→route→check) WIRED + ROUTING THE HUB (2026-06-14)

`scripts/hub_pipeline_run.py` runs the route leg (FOLLOWUPS L1): place (oracle) → materialize →
route (cec_router/Freerouting) → score (gates+DRC) → electrothermal, budget-bounded, in the kicad10
container. THREE real gaps were found + fixed; FR now routes the Hub.

- **FIX 1 — materialize onto the reference stackup.** `build_board`'s from-scratch output is NOT
  DSN-exportable (KiCad's Specctra exporter silently returns False — committed Hub+eps export fine,
  build_board output does not). `materialize_onto_reference()` COPIES the committed Hub (real netclasses
  / 4-layer stackup / mounts / logo preserved — the owner's "base stackup = committed Hub"), repositions
  the 80 synth components, rips the routing, FILLS the zones fresh. Done in TWO spawn subprocesses
  (reposition+rip, then fill) — `bd.Remove()` corrupts the process's pcbnew SWIG state (a later
  LoadBoard returns a raw SwigPyObject; the recorded footgun), so the fill must be a fresh process.
- **FIX 2 — on-board offset (THE unblock).** `cand.P` is in a 0-origin synth frame, but the committed
  outline sits at (70,90); repositioning to synth coords put every component OFF the board → FR can't
  route off-board parts (1 wire). `_reposition_worker` now offsets by the board-edge origin → parts land
  inside the outline.
- **FIX 3 — antenna-edge ESP seat (residual + routability).** The synth placer dropped the large ESP
  courtyard center-board onto the ganged top ports → 3 overlaps (residual 4) → overlapping copper FR
  can't route around. `_seat_antenna_ic` seats the PCB-antenna IC against its antenna edge as a fixed
  anchor (RF principle: the lobe radiates off-board; the edge is the per-board antenna_edge input), kept
  in `ics` for its decoupling cluster but excluded from the anneal → residual 4→**0**. Also fixed the
  antenna TERM to measure the courtyard's near edge, not the footprint origin (reference 0.565→1.0,
  synth 0.0→0.903, synth hub_penalty 0.373→0.125).
- **RESULT (FR routes the Hub):** at LOW effort (passes 6 / opt 10) the reposed synth Hub routes to
  **628 tracks / 103 vias / 39 unconnected**, kelvin_ok + diffpair_ok True, length 2240mm (vs the hand
  board's 2359). Was 2 tracks / 216 unconnected before the fixes. The committed HAND placement routes to
  389 wires / 127-change pass#1 (the reference baseline). Higher effort + the full cec_router repair loop
  (the hour run) drives the 39 unconnected + DRC down further.

NET: the full place→route→check pipeline produces a real routed Hub on the base stackup. An hour-long
run is now worthwhile (higher FR effort + multi-candidate + repair → toward a clean routed Hub).

## CONSULTATIVE AUDIT (4 parallel skeptics, 2026-06-14) + REMEDIATION

Dimensions: geometry/math · anti-overfit charter · regression/integration · test rigor. All four
verdicts: **SHIP-WITH-FIXES, 0 BLOCKER, 0 HIGH-on-the-committed-path**. Findings verified + fixed:

- **H1 (geometry)** `oracle_similarity` identity wasn't 1.0 on boards missing a term's inputs (the
  weights summed to 1.0 but an absent term scored 0). FIXED: renormalize over PRESENT terms; identity
  is 1.0 on any board, absent terms reported as -1.0. (+test_sparse_board_identity_is_one.)
- **M2 (geometry)** `_is_rail_net` matched sense/ref nets with a voltage token (`/KVM_3V3_REF`,
  `/MAIN_5V_SENSE`) → a connector could mis-key power_in. FIXED: `_PWR_NOT_INPUT` now excludes
  sense/detect/ref/flag from rails (shared with the power-loop test). (+test_sense_ref_tap_makes_connector_host.)
- **M3 (geometry)** an invalid/typo `edge_override` value silently DROPPED a connector. FIXED:
  case-fold + validate against {top,bottom,left,right}, warn-and-fall-back to the role default.
  (+test_invalid_edge_override_does_not_drop_connector.)
- **MEDIUM (charter)** `_PWR_INPUT_NET` baked the Hub's literal net names into a general path
  (laundering WHERE not WHY). FIXED: `_power_input_nets` derives the front-end loop TOPOLOGICALLY
  (small-fanout rail nets = point-to-point inputs, not the distributed plane) + a per-board
  `cfg.params['power_input_nets']` override. Reproduces the exact front-end cluster on the Hub with no
  Hub names. (+test_power_loop_is_topological_not_named.)
- **MEDIUM (regression)** the oracle guards swallowed failures silently. FIXED: `_tc.warn_once` in
  `apply_oracle_stage1` / `_oracle_reference` / the similarity except (a broken reference is now visible).
- **2 HIGH (test rigor)** the plan's MV3/MV4 validation criteria were untested. ADDED Hub-gated tests:
  `test_mv4_reference_ranks_at_or_near_lowest_proxy` (reference proxy_score ≤ every synth) +
  `test_mv3_reference_outscores_every_synth_candidate`. MV2 mount round-trip + RJ-45 pitch now tested.
- **MEDIUM/LOW (test rigor)** strengthened scramble per-term teeth (+cluster-only scramble) and the
  sort-key teeth (`test_similarity_not_even_a_tiebreaker` — equal proxy_score, differing similarity).
- **LOW (charter)** port_even is now a scale-free coefficient-of-variation; the antenna divisor + the
  port_even knee carry documented board-relative WHYs.

NOT changed (documented design, not defects): **M4** MV5 hub terms are inert off-oracle by design
(the proxy_score==hpwl zero-regression invariant; generative use is the deferred closer → FOLLOWUPS);
the **24-pin J2 host→power_in** off-oracle reclassification is the net-aware `_role` being *more*
correct (eps + all placer-target boards byte-identical; the 24-pin is hand-maintained, not a placer
target). Suite grew 31→41 tests.

## VERIFICATION

- `tests/test_placer_oracle.py`: 31 tests (logic host-side + pcbnew-gated on the committed Hub), green
  both test orders; wired into `scripts/checklist.sh`. `tests/test_corridor_model.py` 62 green (sort-key
  refactor + `_role` nl-arg are non-regressive). Full `checklist.sh` exit 0 ("host suites pass").
- Pre-merge: SB-08 golden in-container (CLAUDE.md scripts/** gate) — placement-only changes, expected
  unchanged.
