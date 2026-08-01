---
name: codex-exec-auditor
description: "How to use the Codex CLI auditor on this box — direct `codex exec`, never the rescue subagent for multi-step work"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 630cde1d-5693-42e5-9d5b-092ae1fcc8ce
  modified: 2026-07-19T07:02:44.443Z
---

Owner added the Codex CLI to the repertoire (2026-07-19) as a second-opinion
auditor/implementer while Claude works the pipeline.

**Why:** an independent frontier-model audit pass over in-flight loop work
(reservation models, generalizability questions, correctness landmines).

**How to apply:**
- Invoke DIRECTLY via Bash: `codex exec -m gpt-5.6-sol -c model_reasoning_effort=max --sandbox read-only "<prompt>"`
  (owner's chosen model + effort; drop `--sandbox read-only` only when Codex
  should edit). `codex exec resume --last` continues the same session.
- The `codex:codex-rescue` subagent is a SINGLE-ACTION forwarder only (owner:
  "rescue is for single action things") — it cannot poll, fetch results, or
  iterate; do not use it for audits/tasks that need follow-through.
- Background jobs started through the plugin runtime are polled with
  `node ~/.claude/plugins/cache/openai-codex/codex/<ver>/scripts/codex-companion.mjs status <task-id> --json`.
- Ground audit prompts with file:line citation requirements + read-only
  action-safety rules (the 2026-07-19 rail-loop audit prompt is the template).
