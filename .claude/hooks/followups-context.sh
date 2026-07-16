#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# SessionStart hook (owner directive 2026-06-13): make sure NO non-blocking follow-up is ever dropped.
# (1) ensures FOLLOWUPS.md exists at the repo root, and (2) injects a standing instruction telling the
# agent to always record deferred / pending-authorization / consider-later side notes there.
set -uo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
F="$ROOT/FOLLOWUPS.md"

if [ ! -f "$F" ]; then
  cat > "$F" <<'EOF'
# FOLLOWUPS

Standing backlog of **deferred / pending / consider-later** items — anything non-blocking the agent
chose not to do now but should revisit. Maintained by the agent per the SessionStart followups policy.

Format: `- [YYYY-MM-DD] <item> — <why / context / where>`

Conventions:
- This is for NON-BLOCKING items only. Blocking work is finished in-turn, not parked here.
- Owner-action items (decisions / GitHub rituals / bench tasks) go to `docs/owner-queue.md`, not here.
- Remove an item when it's done, or when it graduates into a real task / PR / owner-queue entry.
EOF
fi

INSTR='FOLLOWUPS POLICY (project SessionStart hook): whenever you DEFER an action, note something PENDING future authorization, or jot a "consider later" / "touch on this later" side note — ANY non-blocking item that should be revisited — you MUST append it to FOLLOWUPS.md at the repo root in the SAME turn you raise it, as a dated bullet: `- [YYYY-MM-DD] <item> — <why / context / where to resume>`. Never drop a non-blocking follow-up; it always lands in FOLLOWUPS.md (the standing backlog). This is distinct from: blocking work (finish it now, do not park it) and owner-action items (those go to docs/owner-queue.md). When you complete or promote a follow-up, remove its line. FOLLOWUPS.md already exists (this hook ensures it).'

python3 - "$INSTR" <<'PY' 2>/dev/null || true
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))
PY
