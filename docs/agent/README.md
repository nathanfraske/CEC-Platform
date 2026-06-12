# `docs/agent/`

Agent operational state under the **WSL-ephemeral state policy** (CLAUDE.md,
owner directive 2026-06-12).

- **`handoff.md`** — the cross-session agent handoff. It is **not** maintained on
  `main`; the session-end `Stop` hook (`.claude/hooks/session-end.sh`) regenerates it
  and pushes it, with a snapshot of durable memory, to the dedicated
  **`ops/agent-handoff`** branch every session. Read the latest there:

  ```bash
  git fetch origin ops/agent-handoff
  git show origin/ops/agent-handoff:docs/agent/handoff.md
  ```

  This guarantees the handoff always exists on the remote — never only on the
  ephemeral WSL volume (the one casualty of the 2026-06-12 distro wipe).

- Durable agent memory is snapshotted into `.claude/memory/` (committed) by the same
  hook; user-level `~/.claude` is disposable.
