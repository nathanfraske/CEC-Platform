# FOLLOWUPS

Standing backlog of **deferred / pending / consider-later** items — anything non-blocking the agent
chose not to do now but should revisit. Maintained by the agent per the SessionStart followups policy.

Format: `- [YYYY-MM-DD] <item> — <why / context / where>`

Conventions:
- This is for NON-BLOCKING items only. Blocking work is finished in-turn, not parked here.
- Owner-action items (decisions / GitHub rituals / bench tasks) go to `docs/owner-queue.md`, not here.
- Remove an item when it's done, or when it graduates into a real task / PR / owner-queue entry.

## Observability
- [2026-06-13] DeepSeek-V4 LIVE thinking stream: add a `--stream` mode to `cec_v4_task.py` — request
  `stream:true` (SSE), parse `choices[].delta.content` + `delta.reasoning_content`, and write deltas to a
  live `.stream.jsonl` (mirror cec_fullstack's `streams/*.jsonl` delta format) so V4's reasoning can be
  `tail -f`'d / shown in the dashboard in real time. Fixes the "can't watch V4 live" gap (the one-shot
  urllib call only yields at the end). VERIFY FIRST: the broker passes SSE through UNBUFFERED, and
  llama-server emits `reasoning_content` as streaming deltas (a server flag may be needed; if it only
  streams `content`, the deep-reasoner's thinking won't show). Pairs with the seat bake-off (watch the
  judges reason live). — owner ask 2026-06-13.

## Off-box / model-portability
- [2026-06-13] Off-box "fast iteration" seat mode (`--seats cloud`): cloud-seat shim in
  `cec_judge_local._chat_json` (route a cloud-Claude model name via `claude -p --model <m>
  [--effort <lvl>] --output-format json` with the schema, instead of the broker) + a cec_fullstack
  flag flipping workers→Sonnet / reasoning→Opus-4.8 (effort knob `CEC_FS_REASON_EFFORT=high|max`,
  default high for latency). LATENCY-sensitive test runs only — local broker stays the overnight
  default (that's the whole point of the local wiring). — owner ask 2026-06-13.
- [2026-06-13] Cross-model SEAT bake-off (`scripts/cec_seat_bakeoff.py`, mirror `cec_vlm_bakeoff.py`).
  **2-D matrix per seat: {prompt VARIANTS} × {models}.** For each seat (T1 intent / T4 panel / T5
  auditor; maybe T7/T8) author several prompt variants (different ideas/formats: current prose,
  terse-checklist, few-shot, decision-tree, JSON-skeleton-led, etc.) and run EACH variant on FIXED
  captured round-inputs across {cec-worker-vision, deepseek-v4, sonnet, opus}. Score per (seat,variant,
  model): schema-conformance (no scribe crutch), correctness (real-ref & fence respect, failure_class
  routing incl. placement, priceable-metric respect, lens sensibility), latency, + a MULTI-MODEL QUALITY
  JUDGE PANEL to cut LLM bias: judges = {opus, sonnet (cloud); qwen, gpt-oss-120b/cec-manager-fast,
  deepseek-v4, MiniMax-M2.7/cec-manager (local)} -- MiniMax is RETIRED from CEC paths but still
  REGISTERED in the broker catalog (confirmed 2026-06-13), so usable as a judge; adds another distinct
  family for spread. HARDWARE: THREE heavy host-RAM local models now (deepseek-v4 ~160GB, MiniMax ~102GB
  +~10.5min cold boot, gpt-oss MXFP4 experts-in-RAM) on ONE 5090 -> they CANNOT co-reside. The bake-off
  MUST run local judges SEQUENTIALLY through the broker, BATCHING all of one model's judgments into a
  single residency (amortize the cold boot, esp. MiniMax's ~10.5min) then idle-reap before the next.
  Cloud judges (opus/sonnet) run concurrently off-box. The broker arbitrates VRAM/RAM (swaps conflicting
  model out, in-flight finishes) so this is swap/cold-boot WALL-CLOCK cost, not an OOM -- fine for an
  OFFLINE eval (not latency-sensitive); LEAVE-ONE-OUT (a model never
  judges its own output -> no self-preference); BLIND to producer identity (anonymize which model wrote
  the output); RUBRIC-anchored (score the fixed criteria, not vibes); aggregate by MEDIAN + report
  inter-judge AGREEMENT (high spread => untrustworthy subjective score, defer to the objective metrics).
  Objective metrics stay the PRIMARY decider; the judge panel is the secondary quality signal.
  Output = variant×model matrix per seat -> best format PER model AND which formats GENERALIZE vs are
  overfit (the nothink/scribe assumptions, model-specific phrasings). GUARDS the P1-P12 / P5-P6 prompts.
  **This whole sequence (cloud-seat shim + bake-off + variant sweep) is its OWN PR** (branch e.g.
  claude/seat-bakeoff), separate from the prompt-audit fix PRs. Pick the `--seats cloud` defaults from
  the matrix, not assumption. — owner anti-overfit + 2-D-variant point 2026-06-13.
