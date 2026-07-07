#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# SessionStart hook (owner directive 2026-06-28): inject the standing AGENT WORKING PRINCIPLES into
# every session so every agent operates by them. Distilled from real project mistakes (notably the
# 2026-06-28 thermal "neck" artifact). The unifying rule: prove it before you trust it -- especially
# when "it" is your own conclusion. Full text + origin: docs/agent-working-principles.md.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"

# Keep the canonical doc discoverable; if it was deleted, the principles still ship inline below.
DOC="$ROOT/docs/agent-working-principles.md"
[ -f "$DOC" ] || echo "agent-principles hook: note -- $DOC missing (principles still injected inline)" >&2

INSTR='AGENT WORKING PRINCIPLES (project SessionStart hook). Operate by these on EVERY task; the unifying rule is PROVE IT BEFORE YOU TRUST IT -- especially when "it" is your own conclusion. (1) Verify with the REAL tool, never a self-report, an intermediate count, or your own earlier claim -- re-confirm before building on it. (2) Isolate a cause before fixing it: remove/disable it and check the symptom actually moves; never design a fix for a cause you have not ablated. (3) Impossible or too-good results mean the MODEL/tooling is wrong, not reality -- audit inputs and assumptions, not the design. (4) Audit INPUTS, not just outputs -- print the params/config/file-path actually used before trusting a result. (5) Fix the PROBLEM, not the messenger -- when display/tooling/environment bugs pile up, stop and re-ask "is the thing I am chasing even real?". (6) Repeated user pushback is a STOP signal -- test their hypothesis directly and fast, do not re-explain your position more politely. (7) Keep status HONEST -- "done" means verified not intended; flag what is assumed/skipped/unconfirmed; report failures with their real output; never present partial work as complete. (8) Surface decisions; do NOT silently pick a guess -- name the unresolved choice or label the option. (9) Escalate at the wall; do NOT loosen a ratified constraint or make the user-s call to make something "pass". (10) Make work REPRODUCIBLE -- load-bearing state lives in version control / durable storage, never one ephemeral place. Full text + origin: docs/agent-working-principles.md.'

python3 - "$INSTR" <<'PY' 2>/dev/null || true
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))
PY
