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

## Git authenticates + authors as the bot

`ops/secrets/git-credential-cec.sh` is a git credential helper that serves the
`nathanfraske-bot` PAT (from the file above) for `github.com` pushes, and
`ops/provision.sh` wires it repo-locally along with the bot author identity:

```bash
git config --local user.name  nathanfraske-bot
git config --local user.email <id>+nathanfraske-bot@users.noreply.github.com
git config --local credential.https://github.com.helper ""        # reset gh login
git config --local --add credential.https://github.com.helper \
    "$PWD/ops/secrets/git-credential-cec.sh"
```

So the agent's commits + pushes are the bot, never the owner — which keeps the
CODEOWNERS promotion gate unforgeable (RB-04 consent-integrity). After a WSL
rebuild, `bash ops/provision.sh` re-establishes all of this from the `E:` file.

## Status (2026-06-12)

**Done** — the owner placed the `nathanfraske-bot` PAT at `/mnt/e/secrets/cec-bot.env`
(token id verified: account `nathanfraske-bot`, scopes `repo, workflow`). Git is
wired to author + push as the bot; verified by a bot-authored push.

> Note: the supplied token is a **classic** PAT (`repo, workflow` — broad). A
> fine-grained PAT scoped to **Contents: write on `CEC-Platform` only** would
> shrink the blast radius; swap it into the same file when convenient (no code
> change). The token was shared in chat, so rotating it eventually is prudent.
