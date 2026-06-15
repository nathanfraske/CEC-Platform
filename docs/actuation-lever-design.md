# Full actuation lever — design (plan of record)

_Owner ask, 2026-06-15: "a rule flags a case, then has to pass the clean-evidence gate where the
rule cannot be compared against runs it influenced, tallied, and then if it meets the bar it is
allowed to **steer** the run, but **not gate** it."_

This is the `discover → ratify → enforce` migration's top rung, with **enforce demoted to STEER,
never GATE**. The hard gates (kelvin / diffpair / DRC / conformance) stay deterministic + human
(CLAUDE.md human-ratification boundary, set in stone 2026-06-07).

## The rule lifecycle (4 states)

```
PROPOSED ──flag──▶ CANDIDATE ──clean-evidence bar met──▶ RATIFIED-STEER
  finding /         gathering CLEAN          tallied on runs it             │
  proposed_lever    evidence (rows it        did NOT influence              ▼
  + claimed metric  did not influence)                            steers search, never gates
                          │                                                  │
                          └── fails bar / tripwire ──▶ REFUTED / RETIRED ◀───┘
```

Four invariants, mapped to the owner's words:

1. **Flag** — a rule names a `case` (failure class / locus) **and a claimed metric** it will move
   (one of the A/B axes: `gates_pass`, `kelvin_ok`, `plane_signal_mm`, `drc`, `convergence`).
2. **Clean-evidence gate** — a rule may be scored **only** on outcomes it did not influence. The
   EI-02 control/augmented firewall promoted from advisory to a hard accounting rule, made
   **transitive** over candidate lineage (see the trap below).
3. **Tally** — clean paired (control vs rule-augmented) deltas accumulate **across runs**, persisted
   in the ledger, keyed by rule id.
4. **Steer, not gate** — a ratified rule may reorder candidates / bias `select_deltas` / seed
   placement, and is **structurally forbidden** from writing `gates_pass`, calling a hard checker,
   or shipping/blocking a board.

## What already exists (the embryo) — do not rebuild

- **The clean firewall, in embryo** — `cec_fullstack.lane_for` (control_every) + `lr_view`
  (`cec_fullstack.py:1712`) mask all run-learned steer (`manager_rules`, `scorer_penalties`,
  `refuted_metrics`, finding-deltas) on the **control** lane. Control rows are genuinely
  uninfluenced. Invariant #2 in embryo.
- **In-run settlement** — `pending_deltas` settle against `last_control_metrics` →
  `vindicated | refuted | overturned`; non-vindicated is **rolled back, never ratcheted**
  (`:1989`). `_placement_keep` (`:921`) rejects a move that reads vindicated on the pour-blind
  objective but fragmented the pour (the steer-not-launder prototype). Invariants #2-#4, but
  **per-run, in-memory only**.
- **A/B aggregation** — `ab_aggregate` / `_ab_lane_stats` (`:400`) already split rows by `lane`
  and delta the axes. The per-rule comparator is a refinement of this.
- **Anti-ratchet** — `refuted_metrics` tripwire (PL-06); `cec_policy.clamp` / `scan_banned`
  (the loop can never widen a bound); `promoted/**` CODEOWNERS-gated (owner ratifies the flip).

## The trap that will silently break it — transitive influence lineage

The augmented board **compounds**: a kept move carries forward as the next round's
`placement_base` (`:1754`, "good moves COMPOUND"). So the influence cone is **transitive** — if
rule R is later vindicated against a control baseline, R may be getting credit for gains that an
*earlier* rule's steering set up. A clean-evidence gate that tags only single rows leaks credit.

**Rule:** every candidate carries `influenced_by: {rule_ids}` = (this round's active steers) ∪
(the influence cone of the board it was built from). A (baseline, treatment) pair is **clean
evidence for R** only when `R ∉ influenced_by(baseline)`. Control rows (empty cone) always qualify;
an augmented row may serve as a baseline for R only if R is absent from its whole lineage.

## Implementation — four staged steps (one PR each)

### Step 1 — per-rule transitive influence lineage  *(START HERE)*
- `rule_id(kind, payload)` — stable short hash for each steer kind (`manager_rule`,
  `scorer_penalty`, `finding_delta`, `placement_lever`, `layer_lever`).
- `influence_signature(lr, lane)` — the rule-ids active this round (∅ on control).
- Track a per-run **influence cone**: an augmented round's cone = its signature ∪ the cone of the
  `placement_base` lineage it inherited; carried forward only when the move is **kept**.
- Stamp `influenced_by: [ids]` on the measurement row (alongside `lane`).
- `clean_pairs(rows, rule_id)` — pure comparator returning (clean_baseline_rows, treatment_rows)
  with the firewall enforced (a row with R in its cone is never a baseline for R).
- Host tests: cone transitivity, control-always-clean, firewall exclusion, kept-vs-rolled-back.
- **Additive + non-behavioural** — records lineage + provides the comparator; changes no actuation.

### Step 2 — cross-run persistence + tally
- Route each clean settlement into `cec_ledger` (DF-01/06/07 decision→settle→label) keyed by
  `rule_id`, written to the `corpus/staging` zone.
- `rule_tally(rule_id)` — query the ledger for the rule's clean paired record across runs.

### Step 3 — the graduation bar (statistical, holdout-validated)
- Bar = ≥k **independent** clean pairs + a sign-test / effect-size margin on the claimed metric.
- Per AM-02: the bar threshold is validated on `tests/holdout/`, never tuned on the evidence it
  judges.
- Meets bar → propose promotion (writes to `promoted/**` → CODEOWNERS → owner ratifies).

### Step 4 — the steer-only chokepoint
- A `STEER` registry of ratified rules + one assertion `assert_steer_only(rule)` every actuation
  passes through: may write rank keys / `select_deltas` weights / seeds / placement bias; may
  **never** write `gates_pass` or call a hard checker. Generalize `_placement_keep` into it.
- Hard gates + conformance stay deterministic + human.

## Validation caveat

The lever is **inert on eps** (proven by the 2026-06-15 run: 0 placement moves, all deltas noop —
eps's stall is foreign-signal-in-corridor, a routing/layer problem). To exercise the full loop end
to end, validate on (a) a board where a lever fires — a **Hub**, after step-11 Path-B
generalization — or (b) a **synthetic injected case** with a known-good lever on a fixture, so the
clean-evidence gate has a real signal to tally and graduate.

## Files

- `scripts/cec_fullstack.py` — lifecycle, lane/cone tracking, row stamping, comparator (steps 1-3).
- `scripts/cec_ledger.py` — per-rule clean-evidence persistence (step 2).
- `scripts/cec_policy.py` + `promoted/**` — graduation + owner ratification (step 3).
- `tests/test_actuation_lever.py` — host tests for each step.
- `tests/holdout/` — the never-tune pool for the bar (step 3).
