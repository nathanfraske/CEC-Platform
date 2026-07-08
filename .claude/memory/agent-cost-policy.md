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
seats at :8080 (all on the owner's 5090 box, ~free): `cec-worker` (Qwen3.6-35B, 4 slots,
volume), `cec-worker-quality` (27B dense, per-call quality), `cec-manager-fast`
(gpt-oss-120b), `deepseek-v4-flash` (deep auditor, see [[v4-seat]] /
[[deepseek-v4-auditor]]). Drive them from Bash via the broker's OpenAI-compatible API or
the existing harnesses (scripts/cec_judge_local.py, cec_v4_task.py) — a panel leg that is
"read evidence, judge, return JSON" belongs there, not on a cloud subagent. Cloud agents
only when the leg needs tool use / file access / agentic loops the local seats can't do:
then `haiku` default, `sonnet` for judgment-heavy legs, fable/inherit ONLY when truly
needed (exception-with-a-reason).
