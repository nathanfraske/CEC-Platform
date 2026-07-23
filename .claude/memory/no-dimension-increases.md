---
name: no-dimension-increases
description: Owner ruling 2026-07-23 — dimensions only ever shrink; two-sided population before any growth; growth needs exhausted-ideas + explicit sign-off. PC-case size is a hard constraint.
metadata:
  type: feedback
---

Owner ruling (2026-07-23, refined same day): "The only dimensional changes should be
shrinking when possible, unless we've actually exhausted every possible idea and I
sign off on increasing the dimensions. I would rather make them two sided boards
than increase the dimensions. Size is a huge constraint inside a PC case."

**Why:** boards live inside PC cases — area is a hard product constraint, and board
growth as a solver escape valve compounds (the BGA class would balloon "to the size
of motherboards").

**How to apply — the escalation order for placement/routing pressure:**
1. Machinery first: smarter seat search (sub-cell windows), joint derivation,
   pour/flood coverage, rung completion, better use of existing area.
2. TWO-SIDED population (dual_sided) before any dimension change — note the
   24-pin's single-sided state is a 2026-07-19 per-board ruling; two-sided is the
   sanctioned escalation rung when machinery is exhausted, per-board, surfaced.
3. Dimension GROWTH only after every idea is demonstrably exhausted AND the owner
   explicitly signs off. Never propose it as a convenience lever.
Shrinking is always welcome when it doesn't cost function (the 24-pin shrink-study
precedent). Supersedes the W-grow owner-queue row (retired 2026-07-23).
