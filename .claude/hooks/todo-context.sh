#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# SessionStart hook (owner directive 2026-06-13): maintain TODO.md as the LIVE list of what the agent is
# actively working on -- checkbox form, APPEND-ONLY (items are never deleted; completed/obsolete ones stay
# as a timestamped history with a tombstone). (1) ensures TODO.md exists, (2) injects the standing policy.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
F="$ROOT/TODO.md"

if [ ! -f "$F" ]; then
  cat > "$F" <<'EOF'
# TODO

The LIVE list of what the agent is ACTIVELY working on, in checkbox form. **APPEND-ONLY** — items are
never deleted; completed / obsolete ones stay as a timestamped history.

Format:
- `- [ ] [added YYYY-MM-DD HH:MM] <task>` — active
- `- [x] [added YYYY-MM-DD HH:MM · done YYYY-MM-DD HH:MM] <task>` — completed (left in place)
- `- [~] [added YYYY-MM-DD HH:MM · obsolete YYYY-MM-DD HH:MM → <tombstone>] <task>` — obsolete, with a
  tombstone pointing where it went (e.g. `FOLLOWUPS.md "<entry>"`, `PR #N`, `docs/owner-queue.md`, another line)

Distinct from FOLLOWUPS.md (deferred / non-blocking backlog) and docs/owner-queue.md (owner-action items).

## Active

EOF
fi

INSTR='TODO POLICY (project SessionStart hook): maintain TODO.md at the repo root as the LIVE list of what you are ACTIVELY working on right now, in checkbox form. When you START an active task, append `- [ ] [added <YYYY-MM-DD HH:MM>] <task>`. NEVER delete an item — when it is DONE, flip it to `- [x]` and append `· done <YYYY-MM-DD HH:MM>`; when it becomes OBSOLETE, flip to `- [~]`, append `· obsolete <YYYY-MM-DD HH:MM> → <tombstone>` and point the tombstone at where it went (a FOLLOWUPS.md entry, a PR #, docs/owner-queue.md, or another line). Completed/obsolete items STAY as a timestamped history — append-only, never deleted. Keep the active (unchecked) set small and current; update it in the SAME turn as the work. Distinct from FOLLOWUPS.md (deferred backlog) and docs/owner-queue.md (owner-action items). TODO.md already exists (this hook ensures it).'

python3 - "$INSTR" <<'PY' 2>/dev/null || true
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))
PY
