# Preregistration — EI-02 control-vs-augmented lane (PP-06)

**Status: PREREGISTERED. This document must be commit-timestamped in git BEFORE any
lane-tagged round exists.** Check `git log -- docs/research/prereg-control-lane.md` against the
first appearance of a `lane` field in any `measurement.jsonl` or ledger row. If lane-tagged data
predates this commit, this preregistration is VOID and the experiment must be re-designed and
re-registered.

This registers the EI-02 control lane: an A/B that measures **what, if anything, the augmented
(corpus + auditor-actuator) tier buys** over a signed-only control, on identical board inputs, with
the actuator (item4 corridor-avoid lever, NR-3) verified live in-loop first.

---

## 0. Preconditions (must all hold before round 1)

1. **NR-3 closed.** The item4 corridor-avoid lever is verified to actually apply to the route
   in-loop (an avoid intent lands as a real `bake_hints` rule-area zone AND the routed board's copper
   reflects it). Until this holds, an "augmented" round is indistinguishable from a control round and
   the experiment is meaningless.
2. **Lane field added.** Every `measurement.jsonl` row and every `cec_ledger` round carries a `lane`
   field ∈ {`control`, `augmented`} AND the EI-01 `corpus_state` pin. Rows without both are excluded
   (see §5).
3. **Frozen inputs.** The board netlist + placement floorplan + toolchain manifest (KiCad pin, FR
   1.7.0, broker model lineup) are frozen for the duration; a manifest change ends the dataset and
   starts a new one.

## 1. Hypothesis

**H1 (the thing being tested):** the augmented tier — promoted-corpus briefing of the
intent/panel/auditor seats PLUS the bounded/fenced/control-gated finding-to-actuator harness
(`cec_fs_actuator`) applying corridor-avoid deltas — produces measurably better routing outcomes on
identical inputs than a signed-only control that runs the same deterministic plane with no
corpus brief and no auditor-driven deltas.

**H0 (null):** the augmented tier produces no measurable improvement on the preregistered primary
metric (the deterministic plane dominates; the augmentation is decorative).

A null result is a publishable negative (it bounds C2 and is reported in `negative-results.md`), not
a failure of the experiment.

## 2. Lanes (the two conditions)

- **control (signed-only):** the deterministic plane (place → FR route → score → check) runs with NO
  promoted-corpus brief injected into the seats and NO auditor-finding deltas applied. Seats may still
  *run* (for narration/logging) but their `proposed_lever` output is recorded-and-inert. The corpus
  state is pinned but not briefed.
- **augmented:** identical deterministic plane, PLUS (a) the promoted-corpus brief injected into the
  T1 intent / T4 panel / T5 auditor seats, and (b) `cec_fs_actuator` deltas (corridor-avoid,
  bounded ≤2/round, Kelvin/pinned-fenced, control-gated, rolled back if not vindicated) applied to the
  next round's route.

Both lanes run the SAME board, SAME placement, SAME seeds policy, SAME toolchain manifest. The ONLY
difference is the corpus brief + the actuator.

## 3. Lane assignment rule (locked)

**Every Nth round is a signed-only control; the rest are augmented.** Specifically: **N = 3** — every
3rd round (rounds 3, 6, 9, …) is `control`; rounds in between are `augmented`. Rationale: this gives a
1:2 control:augmented split (≈33% control), enough control mass to estimate the baseline while
spending most compute on the condition of interest. The assignment is **deterministic by round
index**, not random — so it is auditable and not gameable by the agent (the agent cannot choose which
rounds are controls).

**Pairing for the actuator's internal control-gate is distinct from this lane.** `cec_fs_actuator`
already pairs each *applied delta* against an *uninfluenced control round* to decide
vindicated/refuted (NR-3). That per-delta control is an internal mechanism; the EI-02 lane here is the
**experiment-level** A/B. Both are recorded; do not conflate them in analysis.

## 4. Metrics

### Primary (the one the success criterion is stated on)
- **`gates_pass`** (boolean per round) — the deterministic gate verdict. Primary because it is the
  loop's actual objective and is fully deterministic.

### Secondary (reported, not the success gate)
- **`kelvin_ok`** (boolean) — sense-pair routing gate.
- **`plane_signal_mm`** (mm) — the plane/signal separation metric; 0 on the entire pre-lane run, so
  any movement off 0 is itself informative.
- **`drc`** (count) — structural DRC hit count.
- **convergence-verdict distribution** — the per-run capstone verdict
  ∈ {`local_minimum`, `converged`, `diverged`, …} from the DeepSeek-V4 capstone audit, as a
  categorical distribution over runs per lane.

### Derived
- **rounds-to-first-gate-pass** (or censored at run end if never) — per run, per lane.
- **`corpus_state` partition check** — every analyzed row's `corpus_state` pin must distinguish its
  lane; a row whose pin does not is an integrity failure (and excluded, §5) — this is also the C1
  taint-exactness probe running inline.

## 5. Exclusion rules (locked, applied before any analysis)

A round is excluded iff ANY of:
- it lacks a `lane` field OR lacks an EI-01 `corpus_state` pin;
- its toolchain manifest differs from the frozen manifest (§0.3);
- it is an infrastructure-failure round: a seat went dark due to broker/timeout/OOM (recorded as a
  dark-seat QUORUM with a dark-reason) AND that darkness changed which lever was available — i.e. an
  augmented round that silently degraded to control behaviour is excluded, not relabeled;
- the actuator's fence refused the only available delta (`status: refused`) AND no other delta applied —
  this round did not actually receive the augmented treatment.

A run (sequence of rounds) is excluded iff its frozen-input precondition (§0.3) was violated mid-run.
Exclusions are logged with reason; the excluded count per lane is reported (a large augmented-exclusion
count is itself a finding about actuator/fence robustness).

## 6. Run count and duration (locked)

- **Target: 30 nights** (the M2 milestone), each night a bounded run on the frozen board.
- **Minimum analyzable:** ≥ 20 nights AND ≥ 600 non-excluded rounds total AND ≥ 180 non-excluded
  control rounds. Below this the dataset is reported as underpowered and no success/null verdict is
  declared.
- Each night runs to its existing deadline-bounded budget (the `cec_overnight` driver); we do NOT
  tune the per-night budget to chase a result.

## 7. Success criterion (locked, one-sided)

The augmented tier is declared to **buy something** iff, on the non-excluded dataset:
> the augmented lane's per-round `gates_pass` rate exceeds the control lane's by an absolute margin of
> **≥ 10 percentage points**, AND a two-proportion test (control vs augmented `gates_pass` rate) is
> significant at **α = 0.05** after the exclusion rules, AND the augmented lane's
> convergence-verdict distribution shows a strictly higher fraction of non-`local_minimum` verdicts.

If `gates_pass` is 0 in BOTH lanes (the pre-lane run's reality — see NR-2), the primary criterion is
**undefined**; the experiment then falls back to the **pre-registered secondary success criterion**:
the augmented lane achieves `plane_signal_mm > 0` on a strictly higher fraction of rounds than control,
significant at α = 0.05. If neither primary nor secondary criterion is met, the registered conclusion
is **H0 not rejected: the augmented tier buys nothing measurable on this board family** — a reported
negative result.

## 8. What is NOT preregistered (and therefore exploratory)

Any metric, subgroup, or comparison not listed in §4 is **exploratory** and will be labeled as such in
the paper. In particular: per-seat reasoning quality, time-to-converge as a continuous outcome, and any
post-hoc partition of the augmented lane by *which* delta fired are exploratory. We will not promote an
exploratory finding to a claim without a fresh preregistration.

## 9. Analysis-blinding and agent-integrity notes

- The lane assignment (§3) is deterministic by round index, so the agent running the loop cannot
  steer which rounds become controls.
- The success criterion (§7) and exclusions (§5) are fixed here, before data; the analysis script that
  computes them is committed before the dataset is complete and is itself path-gated under review.
- The agent writing the analysis is part of the system under study (Limitation: self-evaluation). The
  fixed criterion + deterministic gates + commit-ordering are the guardrails; they are disclosed, not
  claimed to be airtight.
