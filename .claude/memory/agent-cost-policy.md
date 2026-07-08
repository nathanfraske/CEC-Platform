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

**How to apply:** in Workflow/Agent calls, default `model: 'haiku'` for mechanical
extraction/counting/verify legs; `'sonnet'` for judgment-heavy diagnosis or synthesis
legs; omit model (inherit = fable) ONLY when the leg genuinely needs top-tier reasoning
— treat that as the exception needing a reason. Adversarial-verify passes are usually
haiku. Related: [[v4-seat]] for the local V4 auditor tier as a free-ish deep seat.
