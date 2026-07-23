---
name: no-dimension-increases
description: Owner ruling 2026-07-23 — never grow board dimensions to escape placement/routing pressure; solve within the frame.
metadata:
  type: feedback
---

Owner ruling (2026-07-23, during the seats-v4/W-grow discussion): "I don't want to
increase any dimensions anywhere if we do not absolutely need to, there is room on
the boards and we can fit it. If we are already throwing in the dimension towel on
this simple of a board, the BGA boards are going to be the size of motherboards.
Quit it."

**Why:** board growth is the easy escape valve for placement/routing pressure, and
the habit compounds — every solver shortfall becomes area. The upcoming multi-BGA
boards make the discipline load-bearing.

**How to apply:** never propose or apply a W/H grow (BOARD_WH, wedge measurements,
SHUNT_GAP-style runtime grows beyond what exists) as a fix for seat/walk/route
infeasibility. The levers are machinery instead: smarter seat search (sub-cell
windows), joint derivation, pour/flood coverage, rung completion. A dimension
change requires the owner's explicit "absolutely needed" sign-off FIRST — the old
"one-line veto" posture is inverted. Supersedes the W-grow owner-queue row
(retired 2026-07-23). Related: [[agent-cost-policy]], the seats-v4 FOLLOWUPS entry.
