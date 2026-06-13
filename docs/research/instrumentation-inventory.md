# Instrumentation inventory (PP-07)

One table mapping **every number the paper will claim** → **the mechanism that produces it** →
**its current status**. The rule: **zero rows may read "hope to compute later."** Every row has a
named, existing or in-progress mechanism. A number with no mechanism does not appear in the paper.

Status vocabulary:
- **DONE** — mechanism exists, runs, and has produced data we can point at.
- **BUILDING** — mechanism is specified and partially implemented; the metric is not yet measurable
  end-to-end. Each BUILDING row names the precondition that flips it to DONE.
- **EXISTS** — the raw signal is already emitted by a running mechanism; only the aggregation/analysis
  is left (and that aggregation is preregistered or trivial).

| # | Number the paper claims | Mechanism that produces it | Where it lives | Status | Precondition to flip / note |
|---|---|---|---|---|---|
| 1 | **Control-vs-augmented gate-pass A/B** (the EI-02 result: does the augmented tier buy anything) | `cec_overnight`/`cec_fullstack` runs both lanes on frozen inputs; lane field + per-round `corpus_state`; two-proportion test per `prereg-control-lane.md` | `measurement.jsonl` (lane-tagged) + analysis script | **BUILDING** (EI-02) | Flips to DONE when: NR-3 lever verified live in-loop; `lane` field added to rows; ≥20 nights / ≥600 non-excluded rounds collected per PP-06 §6. |
| 2 | **Per-entry calibration state + untainted corroboration** (an entry's thermal/physical anchor is calibrated; its support is from rounds that did not themselves depend on it) | `ThermalResult.calibration` + `_calibration_state()` reading CL-13 ledger labels (AM-04); corroboration = ledger rows whose `corpus_state.promoted_tree` predates the entry | `cec_ledger` labels + AM-04 calibration latch | **BUILDING** (EI-03) | Flips to DONE at bench calibration (AM-04 ±20% band) AND when the untainted-corroboration query over `corpus_state` is implemented. Until then the number carries the calibration mark (NR-4). |
| 3 | **`real_anchor_ratio`** (fraction of corpus anchors that are real measured/bench data vs MODIFIER-DERIVED or chart-extracted placeholders) | Count over corpus entries of provenance markers (`MODIFIER-DERIVED`, chart-anchor, vs `source.type: bench`/`measured`) | `corpus/{promoted,staging}/**/*.json` provenance fields | **BUILDING** (EI-07) | Flips to DONE when the provenance taxonomy is finalized and the counter is committed. Today: e.g. `thermal-ipc2152.json` carries 1 MODIFIER-DERIVED marker + IPC-2221/2152 chart anchors — the ratio is computable now but the taxonomy/counter is not yet frozen. |
| 4 | **Gate-pass rate** (fraction of rounds where the deterministic gates pass) | `cec_score` deterministic gates (`kelvin_ok`, `diffpair_ok`, `drc`, `unconnected`) → `gates_pass` per round, appended to the ledger and to `measurement.jsonl` | `cec_ledger` rows + `measurement.jsonl` | **EXISTS** | Raw signal emitted every round (34-round run: 0/34). Only per-lane aggregation (row 1) is left, and it is preregistered. |
| 5 | **Convergence-verdict distribution** (`local_minimum` / `converged` / … over runs) | DeepSeek-V4 capstone audit per run → `verdict` + confidence; also per-round `verdict_type` field | `measurement.jsonl` (`verdict_type`, `v4_risk`); `CAPSTONE-v4.{md,json}` per run | **EXISTS** | Capstone emitted per run (current run: `local_minimum`, high conf). Distribution is just the categorical tally over runs (row 1 / PP-06 §4). |
| 6 | **Owner override rate** (fraction of agent-proposed promotions/decisions the owner reverses or declines) | SB-09 owner-override capture: owner sign-off / decline recorded against the proposing ledger decision (`decisions/`, `settle`/`label`) | `cec_ledger` decision + settle/label records | **BUILDING** (SB-09) | Flips to DONE once a body of owner sign-off events exists (M1 onward). Mechanism (decision→settle→label) is DONE; the data accumulates with real promotions. |
| 7 | **Promotion latency** (wall-clock from an entry first proposed in `staging/` to its signed merge into `promoted/`) | git timestamps (first staging commit → promotion PR merge) joined with the ledger decision that proposed it | git history + `cec_ledger` decision records | **BUILDING** | Flips to DONE at M1 (first signed promotion gives the first latency datum). Both timestamp sources exist now; there is simply no promotion to measure yet. |
| 8 | **`corpus_state` taint partition** (every round/run is exactly partitionable into knowledge-influenced vs uninfluenced) | `cec_ledger.corpus_state()` — `promoted_tree`/`staging_tree` git tree ids + `live_rules_sha`/`manager_rules_sha`/`adv_set_sha` content hashes, written on every append and every measurement row | `cec_ledger.py:corpus_state`; every `cec_ledger` row; `measurement.jsonl` `corpus_state` | **DONE** (EI-01) | Pin written on every round (EI-01 landed in `bb0f4bd`). NOTE: the cited `docs/fullstack-run-2026-06-13` run PREDATES this wiring (its rows carry no `corpus_state`); the field appears in `measurement.jsonl` from the first post-`bb0f4bd` run onward. The *exactness* claim (C1) is testable directly against this field; no further mechanism needed. |

## Cross-checks against the claims

- **C1** (signature custody + dark-seat + taint) is carried by rows **8 (DONE)**, **6**, **7**, and the
  partition-check inside row **1**. Its custody half also depends on M1 (first signed promotion) — a
  *milestone*, not a missing instrument.
- **C2** (determinism-dominant evaluation) is carried by rows **4 (EXISTS)** and **5 (EXISTS)**, with
  the quantitative "what augmentation buys" content in row **1 (BUILDING)** and the seat-swap-invariance
  sub-claim measured in the M3 ablation (a run design, not a new instrument).

## No-orphan audit

Every metric named in `claims.md` and `prereg-control-lane.md` appears as a row above:
`gates_pass` (4), `kelvin_ok`/`drc`/`unconnected` (4, same deterministic mechanism),
`plane_signal_mm` (emitted on every measurement row — same `cec_score`/`pour_facts` mechanism as row 4,
reported under PP-06 §4 secondary), convergence-verdict distribution (5), `corpus_state` partition (8),
`real_anchor_ratio` (3), per-entry calibration + untainted corroboration (2), owner override rate (6),
promotion latency (7), the control/augmented A/B (1). **No metric in the claims or prereg lacks a row;
no row reads hope-to-compute-later.**
