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

**WORKFLOW/AGENT MODEL PIN (owner 2026-07-08, after a Fable-fleet near-miss killed by
hand):** Workflow `agent()` calls INHERIT THE SESSION MODEL unless `model:` is set — every
workflow agent() and Agent launch MUST carry an explicit model per the tiers above.

**IN-PIPELINE seats (owner 2026-07-08 evening):** for agent legs INSIDE the wave/pipeline
loop, SPEED beats giant-model quality — seat = `cec-worker-quality` (27B dense,
GPU-resident, no swaps) with **nothink** inputs; giants (gpt-oss-120b / M2.7 / V4-flash)
are quality but too slow for a loop ("unless you can show otherwise — still worth
testing"; bench harness scripts/cec_wave_intents.py, numbers in the 2026-07-08 session).
**Vision seats (same message):** even the best VLMs are "notably bad at PCB
design/defects" — a vision agent must be TOOL/facts-FED (v2 facts-alongside protocol) and
used **excessively sparingly**: published-winner-only sanity check, always advisory.

**Schematic-change delegation (owner directive 2026-07-15):** straightforward
schematic changes (part insertions, net splices with a specified expected delta)
go to a SONNET 5 agent at STANDARD effort — the tooling it needs is stood up as
MCPs (cec-schematic = cec_sch_mcp with the netlist-identity rail; cec-compute =
cec_compute_mcp) plus the splice-script pattern (scripts/splice_*.py precedents,
ERC + netlist-diff verification with the EXPECTED delta stated up front). The
orchestrator audits the verification artifacts and commits.

