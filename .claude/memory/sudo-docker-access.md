---
name: sudo-docker-access
description: Sudo + docker access for the agent (run the container-based overnight loops); secret value lives in a file, never inline here.
metadata: 
  node_type: memory
  type: reference
  originSessionId: 013729e2-c8f1-48ef-9248-e6794f400ac7
---

The owner granted the agent sudo + docker access (2026-06-14) to run the container-based
overnight loops (`cec_fullstack` / `cec_overnight*`, which do `docker compose exec routing ...`).

- **Sudo password** lives ONLY in **`/mnt/e/secrets/cec-sudo.env`** as `CEC_SUDO_PASS=<value>` — the value
  is NEVER written into this file or any committed/snapshotted file (the session-end Stop hook mirrors this
  live ~/.claude memory into the git-tracked .claude/memory/ AND pushes to `ops/agent-handoff`, so an inline
  value leaks to the remote — that hook is what reverted an earlier redaction of the in-tree copy only).
  Load + use non-interactively: `set -a; . /mnt/e/secrets/cec-sudo.env; set +a; echo "$CEC_SUDO_PASS" | sudo -S -p '' <cmd>`.
  Off the ephemeral WSL volume per the WSL-ephemeral policy. drvfs is 0777 so it can't be chmod 600 (same
  caveat as [[bot-git-auth]]'s cec-bot.env).
- **Docker**: the owner authorized elevating the agent into the `docker` group (done via
  `usermod -aG docker nathan`). A fresh login session has the group; in an existing agent shell that
  predates it, wrap docker commands in **`sg docker -c "<cmd>"`** (the group is active in that
  subshell, and a `setsid`/`nohup` child inherits it). The routing + freerouting containers run via
  `docker/compose.yaml` (the [[llm-broker]] is a separate systemd unit on :8080).
- Host-side routing also works without docker (java 21 + the FR jar at
  `~/.cache/cec/freerouting-1.7.0.jar` + pcbnew + kicad-cli) — only `cec_fullstack`'s `_exec_py`
  hardwires the container.
