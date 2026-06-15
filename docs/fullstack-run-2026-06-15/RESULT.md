# Full-pipeline overnight run — RESULT (eps-8pin, 2026-06-15)

_Written 2026-06-15 ~15:15 UTC, after the run completed._

## Summary

Clean, complete, **negative** result. The run **proved the agentic infrastructure** but
**produced no gate-passing board and no measurable lift over control.**

- **Duration:** full 10 h budget. Round 1 at 22:57 (local CDT) → DONE at 09:10, **46 rounds**.
  **0 tracebacks / crashes** (`grep -ic traceback|exception|fatal|crash run.log` = 0).
- **Output:** `0 gate-passing, 0 Pareto finalists, 0 rules promoted, 0 rejections`.
  eps stalled where it always does: `gates=FAIL, kelvin_ok=True, drc≈18`.
- **Watchdog** self-terminated at 8 h (07:18) by design (crash-relaunch only); the run
  carried on to its own 10 h deadline. Both processes have exited.

## A/B (EI-02 control vs augmented) — no signal

| metric | control (n=11) | augmented (n=35) | delta |
|---|---|---|---|
| gates_pass_rate | 0.0 | 0.0 | 0.0 |
| kelvin_ok_rate | 1.0 | 1.0 | 0.0 |
| convergence | 0.0 | 0.0 | 0.0 |
| drc_mean | 18.364 | 18.2 | −0.164 (noise) |
| real_anchor_ratio_mean | 0.8094 | 0.812 | +0.0026 |
| **placement_moved_rate** | **0.0** | **0.0** | **0.0** |

The augmented tier bought nothing over signed-only routing on this board — as predicted.

## Why: the placement levers are inert on eps; the real blocker is pour-clip

- **Placement actuators never moved anything.** All 34 `ACTUATOR` events were
  `kind=noop — "unmapped lever: 'None'"`; `placement_moved_rate = 0.0` in both arms.
  This confirms the standing caveat: eps's stall is **foreign-signal-in-corridor**
  (a routing/layer problem), not a placement problem, so the body-in-band lever has
  nothing to grip.
- **The actual ceiling is pour fragmentation / clipping.** Bundle:
  `pours clipped by routed traces in 40/46 rounds — needs a notched-corridor keepout
  or re-pour-after-route`. Typical late round: `/SENSEC2_LO` fragmented into 2 islands,
  `foreign_cross 19`; FEM conductor-over-temp on the broken sense copper. The layer-stagger
  lever nibbles at this (flips then safe-reverts, gates stay False — no launder) but does
  not close it.

## Shadow evidence actuator (deepseek-v4-flash auditor, EI-02 shadow arm)

By design the auditor's `proposed_lever` is **advisory/noop** (the EI-02 self-influence
proof — owner-confirmed, do not make it actuate). So it produced evidence that was recorded
and never acted on. The evidence is the interesting part:

- **It ran 11 batches** (every 4 rounds, `v4_every=4`) plus the per-round Sonnet finder.
- **Early (round 4):** `risk=low`, flagged "absence of rule injections" as a DRC-class
  pattern an owned lever (rule injection) could act on. The one substantive proposal.
- **Rounds 8 → 44 (7 of the last 8 batches):** `local_minimum_risk=high` **and
  `declined=true`** — it correctly diagnosed the loop as stuck in a local minimum
  (gates never pass, DRC oscillating 10–26 = noise) and **stood down rather than invent
  fixes.** Round 44 verbatim: *"the DRC fluctuations appear to be noise rather than a
  systematic issue. Restraint is warranted to avoid contributing epicycles."*
- **The per-round Sonnet finder** *did* root-cause correctly each round
  (e.g. r2: "/SENSEC2_LO pour fragmented into two islands … root cause is placement-related
  … a placement eviction of a blocking sensitive body could merge the pour") and proposed a
  `placement_eviction` lever — but every one of the 46 deltas resolved to the noop shadow
  lever, so none actuated.

**Net read of the shadow seat:** it behaved *well* — honest local-minimum diagnosis,
deliberate restraint, no hallucinated fixes. That is the positive finding from this run:
the auditor seat is trustworthy under a stalled loop. It just had no live lever to pull.

## T7 capstone review — did not validate (benign fail-safe)

The end-of-run `corpus_fit_review` returned `no_opinion` with concern
`insufficient_data: FileNotFoundError`. Root cause: T7 passes the **best candidate's
decision-log path** (`rec["log"]`) to `corpus_fit_review` → `_cf_load` → `json.load(open(path))`,
but `best` was **round 3**, whose transient `build/route` artifact was pruned ~43 rounds
earlier. The open() raised `FileNotFoundError`, caught at the fail-safe → `no_opinion`. The
fail-safe worked, but the capstone validated nothing. **Fix (FOLLOWUPS):** persist the best
candidate's log into the run dir before T7, or reconstruct the review facts from the retained
`measurement.jsonl` row instead of re-reading the transient candidate log.

## What would actually move eps

1. **Notched-corridor keepout + re-pour-after-route** (close the 40/46-round pour-clip) — the
   real next step, a routing/keepout change, not placement.
2. Or run the full pipeline against a board where the placement lever bites (a **Hub**, once
   step-11 Path-B generalization lands), so the placement actuators have something to grip.
