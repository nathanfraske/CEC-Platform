# Full-stack validation run — end-to-end data packet

**Run:** `cec_fullstack.py --board eps-8pin --rounds 4` · **window:** 2026-06-11 14:07 → 16:22 CT (~2h16m) · **PID 253518**
**Outcome:** 4 candidates, **0 gate-passing, 0 finalists, 0 rules admitted** (7 proposals, all refuted), verifier budget **14/200**.
**Best DRC:** 5 (28→14→8→5), `gates_pass=false` every round. **Best board (human + zone metrics):** round 1.

This directory is the complete, unedited record of one closed-loop run — every tier's input,
output, and (for the cloud Sonnet seats) the full thinking/tool-call transcript. Analysis
write-up: [`../auditor-verifier-disagreement-deep-dive-2026-06-11.md`](../auditor-verifier-disagreement-deep-dive-2026-06-11.md) (11 lessons + evidence index).

## How to read a single round end-to-end
For round N, follow the data in pipeline order:
1. **T0 congestion** → `gr01-grid.json` (hotspots + contested nets; seeds net priority — round 1 only, reused after)
2. **T1 intent manager** → `intents/round-00N.json` (net selection + relational waypoints; the owned routing lever)
3. **T2–T3.5 route+gate+FEM** → row N of `measurement.jsonl` (drc / unconnected / kelvin_ok / max_T / objective)
4. **T4 panel** → the `T4 panel:` line for that round in `../fullstack-run-2026-06-11-validation.log`
5. **T5 auditor (cloud Sonnet)** → `findings/round-00N-sonnet.json` (verdict + reasoning + lever)
   and **the full thinking** → `findings/round-00N-sonnet.stream.jsonl`
6. **T5 verifier (CL-24, 3 seats + arbiter)** → `verifier/round-00N.json` (per-seat verdict + reason + the refute)
7. **T6 pour integrity** → `vision/pour-r00N.json` (deterministic facts; vision seat down/timeout all run)
   + the board render `vision/pour-rN.png`
8. **admitted state after the round** → `live-rules.json` (penalties / rules / **rejections**)

## File-by-file

| File | Tier | What it is |
|---|---|---|
| `../fullstack-run-2026-06-11-validation.log` | all | the run's stdout — every tier line, every broker 502/503/timeout, round boundaries |
| `measurement.jsonl` | T2–3.5 | **the metrics spine** — one row/round (sha, intents_src, passes/opt, panel, gates_pass, kelvin_ok, drc, unconnected, max_T, objective, verifier_final, verifier_spent, n_rules, pour_clipped(_nets), pour_vision, v4_risk) |
| `gr01-grid.json` | T0 | GR-01 congestion grid: 20 hotspots, contested-net order |
| `intents/round-00{1,2,3,4}.json` | T1 | FR-02 intent manager output — net + waypoints. r1–3 **live model**; **r4 fallback** (broker 503 + JSONDecodeError) |
| `findings/round-00{1,2,3,4}-sonnet.json` | T5 auditor | Sonnet finding: `verdict`, `reasoning`, `failure_class`, `scorer_penalty`, `manager_rule` |
| `findings/round-00{1,2,3,4}-sonnet.stream.jsonl` | T5 auditor | **FULL thinking + tool-call transcript** of each Sonnet auditor turn (the "every thinking token" for the in-loop reasoner; ~116–145 KB each) |
| `findings/round-003-v4batch.json` | T8 | deepseek-V4 batch auditor — **declined** (502'd live); the proxy-vs-goal "local minimum" call |
| `verifier/round-00{1,2,3,4}.json` | T5 verifier | CL-24 3-seat panel (spec-conformance / evidence-provenance / actuation-space) + `arbiter` (r1) + `final` + `contention` |
| `vision/pour-r00{1,2,3,4}.json` | T6 | pour-integrity facts (islands / area_mm2 / foreign_cross); `skipped`/`error` = vision seat down |
| `vision/pour-r{1,2,3,4}.png` | T6 | per-round board render (NOTE: 3D-body render — carries the kicad-cli rotated-footprint artifact; see deep-dive "vision-render hygiene") |
| `live-rules.json` | admit/reject | active penalties (pre-seeded defaults), `manager_rules: []`, `injections: []`, the **7 rejections** |
| `reviews/end-of-run-best.json` | T7 | end-of-run corpus-fit reviewer on best candidate r4 — **`no_opinion`** (reviewer 503'd, did not run) |
| `bundle.json` | run | run-level rollup (gate_passing, pour_clip_summary, final_penalties, rejections, verifier budget, charter_status) |

## Seat scorecard (which tiers actually thought, live)
- **T1 intent manager** — live rounds 1–3, **fallback round 4** (broker 503)
- **T5 auditor (cloud Sonnet)** — live all 4 rounds ✓ (the only consistently-live LLM reasoning)
- **T5 verifier (CL-24)** — live all 4 rounds ✓, but every `final` was a **2-of-3 QUORUM** (spec-conformance dark — empty corpus — every round; round-2 also a seat timeout)
- **T6 vision** — **down/timeout all 4 rounds** (deterministic pour facts used)
- **T8 V4 batch** — **502'd, declined** (round 3)
- **T7 end-of-run reviewer** — **503'd, no_opinion** (never ran)

The run's limiting factor was **broker model-swap latency + 502/503/timeout on the single
5090**, not reasoning or compute. The reviewer-tier seats (T6/T7/T8) were all starved of
GPU and never rendered a live verdict.
