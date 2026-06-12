# Secrets policy — never WSL-only

WSL volumes are ephemeral (see CLAUDE.md "WSL-ephemeral state policy"). A secret
that lives only in the WSL filesystem (e.g. `~/.config/gh/hosts.yml`) is **lost on
every reinstall** and must never be the sole copy of a load-bearing credential.

## The rule

The agent bot PAT (used by the session-end handoff hook to push to the
`ops/agent-handoff` branch) must live in **one of**:

1. **A Windows-side secrets file mounted read-only into WSL** — the default:
   - Put it at `E:\secrets\cec-bot.env` (survives a WSL wipe; on a different
     Windows drive layout, set `CEC_SECRETS_FILE`).
   - Reachable from WSL at `/mnt/e/secrets/cec-bot.env`.
   - Contents (one line):
     ```
     CEC_BOT_PAT=github_pat_xxx_a_fine_grained_PAT_with_contents-write_on_CEC-Platform
     ```
   - Lock it down on Windows (the file is plaintext-on-disk; a fine-grained PAT
     scoped to **contents:write on `CEC-Platform` only** limits blast radius).

2. **The Windows credential store** (`cmdkey` / Credential Manager), read via
   a Windows helper. Heavier to wire; the E: file is the supported default.

## How it is consumed

`ops/secrets/load-secrets.sh` sources the file if present and exports
`CEC_BOT_PAT`. The handoff hook (`.claude/hooks/session-end.sh`) calls it and uses
the PAT for the push; if the PAT is absent it falls back to the WSL-local `gh`
credential **with a warning** (that fallback is exactly the disposable-state
failure mode this policy exists to kill — fix it by placing the file).

## OWNER ACTION REQUIRED (one-time)

The PAT cannot be created or placed by the agent. To complete the policy:

1. Create a fine-grained GitHub PAT: repo `nathanfraske/CEC-Platform`,
   **Contents: Read and write** (no other scopes).
2. Save it as `E:\secrets\cec-bot.env` in the `CEC_BOT_PAT=...` form above.

Until then the handoff hook still works via the WSL-local `gh` login, but that
copy does not survive a reinstall — so this is the one remaining single-point-of-
loss after the 2026-06-12 recovery.
