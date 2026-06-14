# Seat bake-off — findings + data-chosen defaults (2026-06-13)

The 2-D `{prompt VARIANT × MODEL}` bake-off (`scripts/cec_seat_bakeoff.py`) for the full-stack loop's
text seats. **Owner scope (2026-06-13): producers-only** — the OBJECTIVE deterministic score is the
PRIMARY decider, so we ran the producer matrix + report and deferred the secondary quality-judge panel
(the deep-reasoner judges, deepseek ~4 tok/s + MiniMax, make the literal 6-judge panel ~1–2 days).

## Matrix (objective correctness across the 3 fixed cases: kelvin-fail / drc-residual / gate-pass)

Producers: cec-worker-vision (local worker tier), sonnet + opus (cloud), deepseek-v4-flash (local
auditor tier — T5 only, the seat it runs in production). Score = schema-conformance WITHOUT the scribe
crutch + seat correctness (T1 real-ref & fence respect; T4 the safety lens never accepts a gate-fail;
T5 failure_class steering + priceable-metric respect) + latency. Mean correctness across models, with
the spread (max−min across models) flagging OVERFIT-prone formats.

| Seat | variant | mean corr | spread | note |
|---|---|---|---|---|
| **T1 intent** | **json-skeleton** | **1.00** | **0.00** | best — 1.00 every model, fastest (6–13s) |
| T1 intent | current | 0.89 | 0.33 | solid |
| T1 intent | terse | 0.67 | **1.00** | **OVERFIT/DANGER — 0% schema on cec-worker-vision** (the worker can't form valid intents from the terse prompt) |
| **T4 panel** | **terse** | **1.00** | **0.00** | best — generalizes |
| T4 panel | current | 0.89 | 0.33 | safe alternative; opus JSON hiccup |
| T4 panel | json-skeleton | 0.89 | 0.33 | opus JSON hiccup |
| **T5 auditor** | **decision-tree** | **1.00** | **0.00** | best — generalizes, fast (5–17s) |
| T5 auditor | terse | 1.00 | 0.00 | ties decision-tree |
| T5 auditor | current | 0.95 | 0.15 | strong |
| T5 auditor | json-skeleton | 0.89 | 0.17 | weakest for T5 (0.83–0.85 on cloud) |

_(deepseek-v4-flash T5 row pending — its 12 producer calls re-run with the token fix, ~2 h; refines the
LOCAL auditor recommendation only, NOT the cloud default.)_

## Headline finding — the best format is SEAT-DEPENDENT
No single format wins everywhere: **json-skeleton is BEST for T1 but WORST for T5**; **terse is great for
T4/T5 but breaks the local worker on T1** (0% schema). So the prompt FORMAT must be chosen per seat, not
globally — a terse-everything or skeleton-everything rewrite would regress a seat.

## Data-chosen defaults (NOT assumption)

Per-seat winning variant (to fold into the live cec_fullstack prompts on a future tuning pass; validate
on `tests/holdout/` per AM-02, not these tuning cases):
- **T1 intent manager → `json-skeleton`** (lead with the JSON skeleton + a worked example). Avoid `terse`.
- **T4 worker panel → `terse`** (compact per-lens checklist). `current` is the safe fallback.
- **T5 auditor → `decision-tree`** (explicit failure_class branching). `terse` ties; avoid `json-skeleton`.

`--seats cloud` model defaults (the off-box fast-iteration mode that flips workers→cloud): the objective
scores SATURATE at 1.00 for the good variants on both cloud models, so reliability + latency decide:
- **worker/generation tier (T1, T4) → sonnet** — 30/30 clean; opus had 2 `--output-format json` replies
  with no parseable JSON object (the cloud-shim extraction missed them) → a minor reliability ding on opus.
- **reasoning/auditor tier (T5) → opus** — opus `decision-tree` = 1.00; matches the FOLLOWUP's preliminary
  "reasoning→Opus-4.8" and now DATA-CONFIRMS it.

## Actionable side-findings
- **Cloud-shim robustness:** opus occasionally returns a `claude -p --output-format json` reply whose
  `result` has no clean JSON object (2/30 here, both T4) → `_extract_json_obj` raises. Harden the shim
  (firmer JSON-only instruction or a retry) before relying on `--seats cloud` with opus on the panel seat.
- **Thinking models need headroom:** deepseek-v4-flash failed 8/8 at a 1200-token budget (burned it all
  on reasoning at ~4 tok/s, never reached JSON). Fixed → per-model budget (deep reasoners 8000/3000).
  This is also a standing reminder: a thinking model as a grammar-constrained seat needs the
  miner→scribe recovery (the production `deepseek_audit` path), which the bake-off deliberately disables
  to MEASURE raw schema-conformance.

## Caveats / scope
- Objective scores are largely saturated because the 3 fixed cases have fairly determinate correct
  answers; the differences that matter are where a format BREAKS a model (terse→worker on T1; opus JSON
  hiccups). The deferred judge panel would add a finer quality gradient — re-run `judge` later if a
  closer call between tied variants is needed.
- This bake-off TUNED on 3 cases; per AM-02 the chosen variants must be validated on held-out cases
  before promoting into the live prompts.
