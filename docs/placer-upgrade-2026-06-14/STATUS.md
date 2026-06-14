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

## VERIFICATION

- `tests/test_placer_oracle.py`: 31 tests (logic host-side + pcbnew-gated on the committed Hub), green
  both test orders; wired into `scripts/checklist.sh`. `tests/test_corridor_model.py` 62 green (sort-key
  refactor + `_role` nl-arg are non-regressive). Full `checklist.sh` exit 0 ("host suites pass").
- Pre-merge: SB-08 golden in-container (CLAUDE.md scripts/** gate) — placement-only changes, expected
  unchanged.
