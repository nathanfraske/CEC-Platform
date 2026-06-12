#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# SessionStart hook, two duties:
#
# 1) MANDATORY MEMORY HANDOFF (all sessions, owner directive 2026-06-10): inject the
#    persistent-memory work-in-flight handoff (current-work-handoff.md) + the memory
#    index (MEMORY.md) as additionalContext, so every new agent/session picks up
#    in-flight work and never repeats completed tasks. Emitted as the hook's ONLY
#    stdout (JSON) — everything else goes to stderr.
#
# 2) Claude Code on the web: make kicad-cli available so ERC/DRC/netlist/BOM work in
#    remote sessions. Thin wrapper around the reusable scripts/setup-kicad-cli.sh.
#    Synchronous: on a cold container the session waits for the install (a few
#    minutes); the post-hook container snapshot is then cached, so warm sessions hit
#    the idempotent fast-path and skip it. Local (GUI) dev boxes are untouched.
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# --- 1) memory handoff injection (stdout = the hook JSON, nothing else) -------------
# Memory lives under ~/.claude/projects/<sanitized-project-path>/memory. Derive the
# sanitized dir from the project root; fall back to the canonical main-checkout dir
# (worktrees sanitize to a different name but share the same project memory).
derived="$HOME/.claude/projects/$(echo "$root" | tr '/.' '--')/memory"
canonical="$HOME/.claude/projects/-home-nathan-CEC-Platform/memory"
memdir="$derived"; [ -d "$memdir" ] || memdir="$canonical"

python3 - "$memdir" <<'PY' 2>/dev/null || true
import json, os, sys
md = sys.argv[1]

def rd(name, cap):
    try:
        with open(os.path.join(md, name)) as f:
            t = f.read()
        return t[:cap] + ("\n[...truncated by session-start hook...]" if len(t) > cap else "")
    except OSError:
        return None

handoff = rd("current-work-handoff.md", 12000)
index   = rd("MEMORY.md", 4000)
parts = ["MANDATORY STARTUP CONTEXT (project SessionStart hook, owner directive "
         "2026-06-10): before doing ANY work, take the persistent memory into account "
         "so you pick up in-flight work and never repeat completed tasks. Memory dir: "
         + md + " — and UPDATE current-work-handoff.md there in the same turn as any "
         "significant work step (it is the cross-agent handoff)."]
if handoff:
    parts.append("=== current-work-handoff.md (work in flight - READ FIRST) ===\n" + handoff)
else:
    parts.append("(no current-work-handoff.md yet - if you start multi-step work, "
                 "create it there and keep it current)")
if index:
    parts.append("=== MEMORY.md (memory index - open any entry relevant to your task) ===\n" + index)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                         "additionalContext": "\n\n".join(parts)}}))
PY

# --- 2) remote-only kicad-cli provisioning (stdout redirected: keep the JSON clean) --
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ]; then
  bash "$root/scripts/setup-kicad-cli.sh" 1>&2 || true
fi

# --- 3) remote-only firmware toolchain (iverilog + ESP-IDF v6.0.1 s3/p4) ------------
# Provisioned for the firmware/ tree's build gate (RTL sim + the three IDF apps).
# Same caching story as kicad-cli: cold container pays once, warm snapshot skips.
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] && [ -x "$root/firmware/tools/setup-esp-idf.sh" ]; then
  bash "$root/firmware/tools/setup-esp-idf.sh" 1>&2 || true
fi
exit 0
