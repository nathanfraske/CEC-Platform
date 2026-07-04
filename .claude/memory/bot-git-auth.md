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

**FAILURE MODE SEEN + GUARDED (2026-06-13, owner directive "push as the bot, not me — set it in stone"):**
a fresh clone that has NOT had `ops/provision.sh`'s git-auth step applied inherits the GLOBAL helper
`credential.https://github.com.helper = !/usr/bin/gh auth git-credential`, which is logged in as the
**owner (`nathanfraske`)** — so `git push` is attributed to the owner even though commits are bot-authored.
The fix is the repo-LOCAL wiring (reset `credential.https://github.com.helper ""` then `--add` the bot
helper); `git credential fill` for github.com must return `username=nathanfraske-bot`.
- **In-stone guard:** `ops/hooks/pre-push` (committed) → installed to `.git/hooks/pre-push` by
  `ops/provision.sh` (unconditional). It runs `git credential fill` and **ABORTS any github.com push that
  would authenticate as anyone but `nathanfraske-bot`** (allows the session-end `x-access-token:<PAT>@`
  URL). Verified: allows the bot-wired repo, aborts the owner-gh fallback.
- **Before any push from a new clone:** confirm `git credential fill <<<'protocol=https\nhost=github.com\n\n'`
  → `username=nathanfraske-bot`, or run `bash ops/provision.sh`. The pre-push hook now enforces this.

**THE `gh` CLI IS A SEPARATE IDENTITY (2026-06-13).** Git *pushes* go through the bot credential helper,
but the `gh` CLI authenticates as whoever `gh auth` is logged in as — on this box the **OWNER
(`nathanfraske`)**. So `gh pr create/comment/edit` and `gh api` (e.g. changing a PR base) are attributed
to the OWNER unless you override the token. This was the real attribution leak the owner noticed (the git
pushes were already the bot, verified by PushEvent actors).
- **Use `ops/secrets/gh-bot.sh` for ALL agent gh operations** — it execs `gh` with `GH_TOKEN=<bot PAT>`
  so the action is the bot (refuses to fall back to the owner if the PAT is absent). e.g.
  `./ops/secrets/gh-bot.sh pr comment 56 --body ...`. Plain `gh ...` = the owner; do not use it for writes.
- Both guards (pre-push hook + gh-bot wrapper) shipped on branch `claude/bot-push-guard` (PR #57).
