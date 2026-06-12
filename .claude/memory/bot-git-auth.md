---
name: bot-git-auth
description: "Git in CEC-Platform authenticates + authors as nathanfraske-bot via a PAT on /mnt/e (survives-WSL); not the owner's identity."
metadata: 
  node_type: memory
  type: project
  originSessionId: 481c50f1-03c6-4988-bdb6-aa3ffd3f3706
---

CEC-Platform git is wired (repo-local) to **author and push as `nathanfraske-bot`**,
never the owner — this keeps the CODEOWNERS promotion gate unforgeable (RB-04
consent-integrity).

- Bot PAT lives at **`/mnt/e/secrets/cec-bot.env`** (`CEC_BOT_PAT=` + `CEC_BOT_USER=`),
  off the ephemeral WSL volume per [[env-rebuild-2026-06-12]]'s WSL-ephemeral policy.
  Account `nathanfraske-bot` (id 291401607), classic PAT scopes `repo, workflow`.
- `ops/secrets/git-credential-cec.sh` is the git credential helper serving that PAT;
  `ops/secrets/load-secrets.sh` exports it. `ops/provision.sh` re-wires the helper +
  the bot author identity from the E: file after any rebuild.
- The session-end Stop hook ([[llm-broker]] sibling: `.claude/hooks/session-end.sh`)
  pushes the handoff to `ops/agent-handoff` using this PAT.
- Don't author commits as `nathanfraske <nathanfraske@gmail.com>` here; the bot is
  configured in repo-local git config. PR #51 carries all of this (recovery hardening).
- The token was shared in chat once — rotating it eventually is prudent; a fine-grained
  Contents:write PAT would shrink scope (swap into the same file, no code change).
