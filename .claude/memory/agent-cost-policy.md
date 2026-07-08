---
name: agent-cost-policy
description: Owner rule for delegation cost — cheapest agent that still does the job well; fable/inherit reserved for truly-needed
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 76e486b3-8c72-4f10-8c1b-209e5aecb01b
---

Owner directives (2026-07-07 "least expensive agents for when you delegate please";
2026-07-08 "use the cheapest possible agents that still get the job done well, you can
use yourself but reserve that for when it is truly needed").

**Why:** compute spend on agent models is the ONE place cheapest-possible is the rule
(CLAUDE.md: quality-first applies to the boards, never to agent-model spend).

**How to apply:** PANELS/FAN-OUT GO LOCAL FIRST (owner 2026-07-08: "keep as many of the
panelists to my local machine as possible... every panel at 3M+ tokens uses all of my
budget immediately; we have the cec-worker-quality tier for that anyway"). Local broker
seats at :8080 (all on the owner's 5090 box, ~free). **Seat picking (owner 2026-07-08):**
`cec-worker-quality` (27B dense, **GPU-resident** by design) is the MAIN GO-TO for
quick/fast judgment calls; `cec-worker` (Qwen3.6-35B, 4 slots, **mostly RAM-resident** so
it can PANELIZE without evicting the GPU seat -- owner 2026-07-08) for parallel volume; the HUGE seats —
`deepseek-v4-flash` (~6-7 tok/s, slow ~160GB cold load; see [[deepseek-v4-auditor]] /
[[v4-seat]]) and `cec-manager` — canNOT be fire-and-forget: reserve for heavy-heavy
judgment calls only, and expect load latency. Drive them from Bash via the broker's
OpenAI-compatible API or
the existing harnesses (scripts/cec_judge_local.py, cec_v4_task.py) — a panel leg that is
"read evidence, judge, return JSON" belongs there, not on a cloud subagent. Cloud agents
only when the leg needs tool use / file access / agentic loops the local seats can't do:
then `haiku` default, `sonnet` for judgment-heavy legs, fable/inherit ONLY when truly
needed (exception-with-a-reason).

**Tier-quality caveat (owner 2026-07-08):** haiku INVENTS on open-ended measurement/
calibration legs (fabricated an "overpacking" concern from hand-board analysis). Legs whose
output becomes a THRESHOLD or design principle run at sonnet minimum, opus when they gate;
haiku stays for mechanical extraction/verify with narrow rubrics. When a cheap leg's finding
drives a decision, re-derive it at a higher tier first ("grain of salt" rule).
