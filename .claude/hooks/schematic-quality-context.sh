#!/usr/bin/env bash
# SessionStart hook: inject the schematic-quality charter pointer (owner directive 2026-07-02).
root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
charter="$root/docs/schematic-quality-charter.md"
[ -f "$charter" ] || exit 0
python3 - "$charter" <<'PY'
import json, sys
p = sys.argv[1]
head = open(p).read().split("## The tool ladder")[0].strip()
ctx = ("SCHEMATIC QUALITY CHARTER (project SessionStart hook, owner directive 2026-07-02): "
       "before ANY schematic-generation work, READ docs/schematic-quality-charter.md — the "
       "plan of record for making generated schematics hand-authored quality (tool ladder "
       "T1-T6, non-negotiable principles: netlist-identity invariance, teeth-first checkers, "
       "calibrate-don't-guess, GUI stays the top rung). Update its Status column in the same "
       "change that lands a tool.\n\n=== charter head ===\n" + head)
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                         "additionalContext": ctx}}))
PY
exit 0
