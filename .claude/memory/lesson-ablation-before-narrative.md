---
name: lesson-ablation-before-narrative
description: Ablation-test a named cause before designing a fix; impossible numbers = model bug; repeated owner pushback = stop and test.
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 6a1b6a2a-dfb9-4421-89b6-0ca014fb9552
---

Hard lesson from the 2026-06-28 thermal session: I spent a whole session designing a
B.Cu mirror to fix ~1435C "shunt-funnel necks" that were a pure ARTIFACT — the solver
was pushing 40A through 0.2mm kelvin sense-tap traces that carry no current. Removing
those traces dropped the peak 1067C -> 62C. The board never had a thermal problem.

**Why:** I built a tall narrative (necks -> mirror -> cooling models -> a multi-turn
render saga) on top of one unverified claim ("the necks are real"), ignored a
physically impossible number (1435C > copper's 1085C melting point), fixed peripheral
messengers (GPU bug, wrong-board dashboard, color-scale crush) and mistook that for
progress, trusted the solver's OUTPUT without auditing its INPUT (what current path it
modeled), and answered the owner's repeated "are you sure?" with more polished versions
of the wrong story instead of testing it.

**How to apply:**
- The instant you NAME a cause, ABLATE it: remove X, re-run, compare. "Delete and
  re-solve" is the most decisive tool there is. Never design a fix for a cause you
  haven't isolated this way. (The owner forced this; do it unprompted.)
- A physically impossible number (fusing temp, negative R, 99% confidence) = audit the
  MODEL, not the design. Print the model's inputs (currents, source/sink, h_eff,
  whatever `_prepare_filled`-style prep it does) before trusting outputs.
- Repeated pushback from someone who knows the artifact is a STOP signal — test their
  hypothesis directly and fast, don't re-explain your conclusion.
- When peripheral/tooling bugs pile up, re-ask "is the thing I'm fixing even real?"
  A better view of a wrong model is still wrong.

Full write-up: docs/lessons-thermal-neck-artifact-2026-06-28.md (in the cec-placement
worktree / claude/placement-corridor). Related: [[cec-thermal2d-field-solver]],
[[thermal-gate-required]].
