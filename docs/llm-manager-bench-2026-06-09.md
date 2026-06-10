# LLM manager-tier bench — 2026-06-09 (record of results)

The post-lineup question — *which local model does the manager/reviewer tier progress with?* —
was settled by two bench tracks run on 2026-06-09. **Provenance note:** the raw run logs lived in
`/tmp/cec-bench/` and were LOST to a WSL restart on 2026-06-10. What survives verbatim is
`build/bench-gptoss.log` (reproduced below) and the bench driver (promoted to
`scripts/cec_bench_manager.py`); the M2.7 numbers below are from the session record written at
bench time. Re-run the verdict bench any time — it is cheap (`BENCH_MODEL=<model> python3
scripts/cec_bench_manager.py`, broker boots the backend on demand).

## Track 1 — manager VERDICT bench (the pipeline's real judgment task)

Three differentiated contexts (correct call differs: accept / repair / escalate), production
`SYSTEM` + `VERDICT_SCHEMA`, single call, temp 0, json_schema grammar.

**gpt-oss-120b (cec-manager-fast)** — surviving raw log (`build/bench-gptoss.log`, direct :8001):

```
=== MANAGER BENCHMARK :: ggml-org/gpt-oss-120b-GGUF @ http://localhost:8001/v1 ===
  accept    expect=accept    got=accept     OK | 74 tok in 9.7s = 7.6 tok/s
  repair    expect=repair    got=repair     OK | 94 tok in 6.4s = 14.6 tok/s
  escalate  expect=escalate  got=escalate   OK | 327 tok in 17.0s = 19.2 tok/s
  -> 3/3 correct | aggregate 495 tok in 33.2s = 14.9 tok/s avg ; 11.1s/verdict
```

## Track 2 — reasoning bench (hard quantitative trap problem, 6 runs)

From the bench-time session record (raw logs lost):

| | gpt-oss-120b MXFP4 | MiniMax-M2.7 229B UD-Q3_K_XL |
|---|---|---|
| Result | **~9.5/10 COMPLETE, single call, 3.7k tok / 172 s** — caught both traps, quantified worst-case corners, clean actionable answer | Truncated **twice with NO answer**: entire budget burned in `reasoning_content`, EMPTY `content` at 8k AND 14k caps; a "think shorter" directive made thinking LONGER (59 KB) |
| Warm decode | 21.4–22.3 tok/s | 12.9–13.0 tok/s |
| Footprint | ~63 GB RAM (experts), ~6–9 GB VRAM — coexists with the worker in page cache | 102 GB RAM (pins most of the 122 GiB page cache), ~28 GB VRAM |
| Cold load | ~6.5 min (warm-ish cache; fully-cold 9p is slower) | ~10.5 min |
| Known trait | may catch an issue in thinking yet OMIT it from the final answer (caught a planted spec inconsistency internally, didn't surface it) — mine `reasoning_content` when auditing | adversarial AUDITOR strength: rumination enumerates assumption branches; found 4 real prompt defects incl. the planted inconsistency. **Verified protocol: miner→scribe** (harvest `reasoning_content`, second EDITOR call at temp 0.3–0.4 + presence_penalty ~0.8 + ≥4k tokens → complete 9.5/10 in ~3.6k tok/~5 min). **Decode-loop hazard:** never temp ≤0.2 without presence penalty |

## Verdict (wired in 2026-06-10, branch `claude/manager-tier-wiring`)

- **Out-of-loop REVIEWER tier default = `cec-manager-fast` (gpt-oss-120b)** — single-call
  reliability on bounded-JSON judgments, ~2× faster per completed judgment, coexists with the
  worker in RAM across overnight ROUTE/REVIEW alternation.
- **`cec-manager` (MiniMax-M2.7) = opt-in deep AUDITOR** (`CEC_VLLM_REVIEWER_MODEL=cec-manager`):
  adversarial audits / spec-linting where the trace is the deliverable. Made programmatically
  usable by the production guards in `cec_judge_local._chat_json`: automatic miner→scribe recovery
  on empty-content overrun + model-conditional sampling floors (temp ≥0.3, presence_penalty 0.8).
- **In-loop manager tier stays worker-class** — panels interleave with worker calls every route
  iteration; a big manager there would broker-swap models per iteration.

Unit coverage: `tests/test_judge_local_scribe.py`. Tier wiring details: CLAUDE.md "LLM BROKER"
done-item, TIER WIRING paragraph.
