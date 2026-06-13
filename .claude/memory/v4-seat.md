---
name: v4-seat
description: DeepSeek-V4-Flash is a usable PANEL/sub-agent seat (a tier above Sonnet); hand it tasks sync via cec_v4_task.py or async via the idle queue cec_v4_queue.py + Stop hook.
metadata: 
  node_type: memory
  type: reference
  originSessionId: 8df0c678-aa2a-4db5-831e-98ee5344dfeb
---

Owner directive 2026-06-13: treat **DeepSeek-V4-Flash** (broker model `deepseek-v4-flash`, served Windows-native
on :8007, proxied by the broker on :8080) as a usable seat on ANY panel — **basically a tier above a Sonnet
sub-agent** (deep local reasoning, slow ~7 tok/s decode). It is loaded + resident; use its spare cycles.

**Two ways to hand it a task:**
- **Synchronous (a panel seat):** `python3 scripts/cec_v4_task.py --prompt-file P [--system-file S]
  [--schema-file J -> grammar-constrained JSON] [--out R.json] [--max-tokens N] [--timeout S]`. Returns
  `{content, reasoning, usage, elapsed_s}`; recovers V4's deep-reasoner empty-content (answer stranded in
  `reasoning_content`) to the reasoning tail. `cec_v4_task.v4_up()` guards. Verified live (8.3s for a tiny task).
  NOTE Workflow `agent()` can't be set to a non-Claude model, so V4 is NOT a `model:` override on a workflow
  agent — invoke it via this script (a Bash step / a Claude agent calling it), or via the queue below.
- **Idle async (handed-off while nothing else runs):** `python3 scripts/cec_v4_queue.py enqueue --prompt ...
  [--system ...] [--label ...]` drops a task under `docs/v4-queue/pending/`; `run-idle` processes ONE when the
  box is idle (V4 up + no ACTIVE local route/run [cec_fullstack/cec_inloop/cec_router/cec_synth] + single-runner
  lock), results to `docs/v4-queue/done/`. `status` shows pending/done/v4_up/box_idle. Cloud Claude workflows do
  NOT count as busy (no local GPU). **Hook:** the Stop hook `.claude/hooks/v4-idle-queue.sh` (registered in
  `.claude/settings.json`) kicks `run-idle` detached when I go idle — so V4 drains the queue on spare cycles.

**When to use V4 vs a Claude sub-agent:** hand V4 deep, latency-tolerant analysis / audit / review / research
where its rumination beats a Sonnet seat and a ~10 min turnaround is fine; use the queue for fire-and-forget.
Restart V4 if down: `E:\toolchain\run-v4-flash.bat` (see [[deepseek-v4-auditor]]); broker wiring in [[llm-broker]].
