# Placer-upgrade anti-overfit charter (owner directive, 2026-06-14)

Using the fab-ready Hub as a reference must NOT teach the placer "the way this board exists." A rule learned
from one board with no underlying *why* is a Class-H single-observation; promoting it to a general rule is
the corpus-poisoning over-fit the DF-05/07 anti-ratchet firewall exists to stop. The reference Hub is treated
like the **holdout set** (`tests/holdout/`): **validate against it, never tune toward it.**

## The three hard rules (apply to every MV item)

1. **Rules encode the WHY, not the WHERE.** Every domain term is a net-derived *physical/electrical*
   principle whose value the placer DERIVES from whatever board it is placing — never a constant copied from
   the reference.
   - ✅ "minimize the variance of consecutive identical-connector gaps" (ganged RJ-45 jacks get uniform pitch
     for panel cutouts + cable clearance + matched length). The placer finds the pitch that fits the board.
   - ❌ "RJ-45 pitch = 18.5mm" (the Hub's value).
   - ✅ "a PCB-antenna part radiates off a board edge with a copper keepout" (RF principle).
   - ❌ "the ESP goes at (x,y) on the top edge."

2. **The reference is VALIDATION, never an optimization target.**
   - Similarity-to-reference (MV3) is a **diagnostic** — reported, never a rank/score key. Optimizing it
     drives toward copying the board.
   - Proxy calibration (MV4) uses the reference only to NORMALIZE term *scale* (so HPWL/RUDY/thermal are
     commensurate). The relative weights encode universal priorities (routability > congestion), not "what
     makes this board win." No weight-regression-to-one-board (defer Tier-B until many routed candidates
     exist; even then, regress onto the PHYSICS — routed length — not onto board identity).

3. **Per-board REQUIREMENTS ≠ generalizable RULES.** A board's outline/size, which edge a connector group
   faces, and mount coordinates are board-specific *inputs* (legitimate, same status as a spec line). They
   may be derived from the reference AS INPUTS, but are tagged board-specific and NEVER laundered into a
   universal rule. The general rule is "external connectors group on an edge by function"; *which* edge is a
   per-board input.

## How each MV item complies

- **MV1** (netlist→materialize): pure infra, no rule. ✅
- **MV2** (Stage-1 from the reference): split into (a) a GENERAL fix — `_role` classifies connectors by NET
  FUNCTION correctly (the buggy J_5VSB mis-key), the WHY being "function determines edge-grouping"; (b) the
  per-board edge/outline/mount assignment as a tagged board-specific INPUT derived from the reference, NOT a
  rule. The general edge-grouping principle is what generalizes; the specific edge is board input.
- **MV3** (similarity): a DIAGNOSTIC only. Hard ceiling: it must never enter the sort/score key.
- **MV4** (proxy into selection): RUDY/thermal/HPWL are universal physical proxies; the reference only sets
  the normalization scale. HPWL-dominant defaults; no per-board weight regression.
- **MV5** (domain terms): each term is a net-derived geometric principle with a stated WHY (uniform-pitch
  variance; antenna-off-edge; power-input-chain cohesion for loop-area/IR-drop; diff-pair endpoint proximity
  for length-match). No hardcoded reference values; the reference only confirms a principled term scores the
  hand board well (e.g. its port-gap variance ≈ 0).

## Corpus boundary

If any placer rule is ever promoted to the corpus, it cites its physical WHY (Class A standard / B
spec-derived). "Observed on the Hub" is Class H (single-observation) and may never become a general rule. A
term whose only justification is "it makes the output match the reference" is rejected at intake.
