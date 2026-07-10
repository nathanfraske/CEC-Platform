---
name: dashboard-activity-feed
description: The dash (:8090) has an ACTIVITY feed — log EVERY visual artifact/work stage via cec_worklog so the owner can verify without asking.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 76e486b3-8c72-4f10-8c1b-209e5aecb01b
---

Owner directive (2026-07-08): "make the dash actually show all your work and when it is
happening so I can visually verify — it's becoming a constant back and forth."

**How to apply:** whenever you produce a visual artifact (render, thermal study, schematic
overview, routed board PNG) or start/finish a long stage, log it IN THE SAME BREATH:
`python3 scripts/cec_worklog.py "<title>" --tag schematic|pcb|wave|study|audit|fix
--detail "..." --image <repo-rel.png>` (or `from cec_worklog import log`). Events land in
`build/worklog.jsonl`; the dashboard's ACTIVITY section merges them with the last 30 git
commits (committed work shows automatically) and serves images via /artifact.
cec_fresh_wave auto-logs start/best. The dashboard is [[dashboard-fixed-port]] 8090.

**Why:** the owner verifies visually on the dash; work that isn't surfaced there generates
back-and-forth and erodes the autonomous loop's value.
