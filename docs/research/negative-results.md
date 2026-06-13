# Negative results and limitations (PP-04)

Drafted **before** the claims were finalized, on purpose: negative results discipline claims. Every
claim in `claims.md` was written to be survivable against the items below. If a claim cannot
survive a negative result here, it does not belong in the paper.

These are *real, observed* negatives from this project — not hypothetical risks. Each cites the
artifact it came from.

---

## NR-1 — VLM seats cannot measure geometry (the measurement-role failure)

**What happened.** The vision seat was originally asked to *measure*: "is this pour clipped /
fragmented?" — an absolute geometric judgment. It failed in two distinct, documented ways:

- In the v1 (naive) VLM bake-off protocol, all three local vision models failed the golden-render
  gate: the judge false-fired on a *conformant* board, and both Qwen3.6 vision workers returned
  empty content on 100% of grammar-constrained calls (thinking-overrun). Source:
  `docs/vlm-bakeoff-2026-06-10.md`.
- Even after the v2 facts-alongside protocol made all three "PASS" the gate, the calibration finding
  was that the seat passes by **restating the deterministic facts fed to it**, not by reading
  geometry: its isolated perception probe on the same image contradicted its facts-present verdict
  (a 0.3 mm via delta is below its reliable visual floor). Source: `docs/vlm-bakeoff-2026-06-10.md`
  calibration insights.
- In the PR #36 validation run, the seat marked all four rounds "clipped" on a model-free render —
  flagging the intact round-1 board as *worse* than the fragmented round-4 — because it was parroting
  the fed `foreign_cross>0` rule, not reading the render. Source:
  `docs/vision-seat-role-rationale-2026-06-11.md` (now superseded by the owner pipeline ruling).

**Consequence for the claims.** This is the founding evidence for C2's seat-confinement: the owner
ruling (`docs/decisions/owner-ruling-vlm-detection-pipeline-2026-06-11.md`) retired the VLM-as-judge
roles entirely and restricted the seat to narration + open-ended anomaly surfacing. The paper must
present this as a *negative result that shaped the architecture*, not hide it. It is the single
clearest demonstration that determinism-dominance was forced by measurement, not chosen for taste.

---

## NR-2 — The loop converges to a local minimum: 0 gate-passing over 34 rounds

**What happened.** The one multi-round full-stack run we have
(`docs/fullstack-run-2026-06-13/measurement.jsonl`, 34 rounds on `eps-8pin`) produced **0
gate-passing rounds**. `kelvin_ok` held on 29/34 rounds (false on rounds 2, 10, 18, 26, 34), but `plane_signal_mm` stayed at 0 on every
round and `drc` never cleared (range 5–28). The DeepSeek-V4 capstone audit verdict was
`local_minimum` (high confidence), root-caused to persistent pour fragmentation on sense nets
`SENSEC2_HI/LO` from foreign signal nets crossing the sense corridors — a constraint-level problem
the loop's allowed levers (router passes, waypoint intents, placement regeneration, scorer
penalties) could not fix. Source: `docs/fullstack-run-2026-06-13/CAPSTONE-v4.md`.

**Consequence for the claims.** This bounds C2 hard: we do NOT claim the loop produces a passing
board. The honest reading is that the deterministic gates correctly *refused to pass* a board that a
seat-driven loop would have been tempted to declare done — which is evidence *for* C2's
determinism-dominance (proxy-satisficed-below-the-gate is correctly a local minimum, per the V4
decline) and *against* any "the loop solves boards" overclaim. The capstone's recommended fix is a
human design escalation (a keepout constraint), which is exactly the human-ratification boundary the
loop is designed to escalate to.

---

## NR-3 — The only actuator was silently dead (this session's finding)

**What happened.** This session found that the item4 corridor-avoid lever — the loop's only
mechanism for *acting on* an avoid-region finding to escape a local minimum — was **silently dead in
two places**: `route_directed` only baked the route-diversity perturb keepout, and
`intent_keepouts()` had **zero callers**, so every avoid-region (the item4 lever and any auditor
"route around corridor" finding) was produced and carried through the pipeline but never applied to
the route. Source: commit `2e95bc0` message; fixed there by wiring `_avoid_to_bake` +
`intent_keepouts()` into `route_directed`'s bake-hints keepouts.

**Consequence for the claims and the schedule.** Two things follow, both important for paper honesty:
1. Any pre-fix multi-round run (including NR-2's 34-round run) reached its `local_minimum` verdict
   with the escape actuator *inert*. We therefore **cannot** attribute NR-2's failure to the loop's
   reasoning alone — the actuation half was broken. NR-2 is a valid negative about *gate discipline*
   but NOT a valid negative about *the loop's ability to escape minima*; that question is reopened.
2. This is itself a methodological negative result worth reporting: in a closed-loop system, an
   actuator that produces and logs an intent but never applies it is indistinguishable from a working
   actuator in every artifact *except the board state*. The taint partition (C1) and the symmetric
   outcome recording (`cec_fs_actuator.DeltaLog`, win/loss/overturn with equal detail) exist partly to
   make this class of silent failure detectable — a delta that is "applied" but never moves the
   control-vs-treatment margin is now a recorded `refuted`/`rolled_back` outcome rather than an
   invisible no-op. **M2 cannot start until the lever is verified live in-loop** (the
   run-loop wiring that applies deltas + the paired treatment/control rounds is the next step).

---

## NR-4 — FEM thermal numbers are uncalibrated until bench (AM-04)

**What happened.** The electrothermal solver's anchors are IPC-2221/2152 chart points and
modifier-derived values (the staging entry `thermal.ipc2152.ref.plane_adjacent`, ONE entry / one
dataset, values flagged owner-verify-pending). The design posture is BLOCKING-with-the-mark:
authority (the gate fires) is separated from accuracy (the number is not yet calibrated). The values
tighten into a ±20% accuracy band only at bench calibration, which has not happened. Sources:
`docs/closed-loop-parity-plan.md` §AM-04; `corpus/staging/general/thermal-ipc2152.json` (1
MODIFIER-DERIVED marker, IPC-2152/2221 chart anchors).

**Consequence for the claims.** The paper must NOT present any `max_T` / thermal-margin figure as a
calibrated physical measurement. C2 explicitly scopes out thermal accuracy. Where a thermal number
appears it carries the calibration mark; the convergence-verdict and gate-pass claims do not depend
on thermal accuracy (they depend on `kelvin_ok` / `drc` / `plane_signal_mm`, which are geometric and
deterministic).

---

## NR-5 — The deep-auditor seat was swapped mid-project (Sonnet → DeepSeek-V4)

**What happened.** The T5 deep auditor / overnight reviewer seat was Sonnet through the 2026-06-11
runs and was replaced by DeepSeek-V4-Flash-284B by owner decision 2026-06-11 (commit `cbb9ef0`).
Rationale: V4's deep-reasoning performance was established and the local-minimum decline behaviour
(the anti-epicycle "this is a local minimum, decline to propose another penalty" call) was what the
auditor role needs; the ~160 GB host-RAM cold load is the accepted cost. Source:
`.claude/memory/deepseek-v4-auditor.md`; `docs/auditor-verifier-disagreement-deep-dive-2026-06-11.md`.

**Consequence for the claims.** This is a *threat to reproducibility* that we report rather than
paper over: any cross-night comparison that spans 2026-06-11 spans a seat swap. C2's
seat-swap-invariance sub-claim turns this from a confound into a (weak, single-instance) data point —
but the M3 ablation must be run entirely on one seat to be clean, and the paper must disclose that the
historical record is not seat-homogeneous.

---

## Limitations (stated up front, must appear in the abstract)

- **N = 1 team.** One operator/owner, one set of design judgments. No inter-team variance.
- **Single reviewer.** All promotions, demotions, and sign-offs route to one human (`@nathanfraske`).
  The "human ratifier tier" is one person; we cannot distinguish the governance design from this
  individual's judgment.
- **One domain, one board family.** All multi-round evidence is on `eps-8pin` (and adjacent EPS/PCIe
  interposers). Claims are stated over this family only. Generalization to other PCB classes, or off
  PCB entirely, is unsupported.
- **No external replication.** Nobody outside this project has reproduced any result. The toolchain is
  pinned (KiCad 10, FR 1.7.0, broker model lineup) and the ledger is reproducible-by-manifest, but
  reproduction has not been *performed* by a third party.
- **Compute is single-box and partly Windows-native.** The deep auditor runs Windows-native llama.cpp
  on a forked build; a replicator without that exact setup gets a different (or absent) deep-auditor
  seat. The deterministic plane (the part the claims actually rest on) is portable; the LLM plane is
  not fully so.
- **Self-evaluation.** The agent writing these docs is a component of the system under study. The
  preregistration (PP-06) and the deterministic gates are the guardrails against this; they are not a
  complete defense.
