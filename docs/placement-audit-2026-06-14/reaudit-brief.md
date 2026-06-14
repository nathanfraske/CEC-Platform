# Placement EI-parity — FOCUSED RE-AUDIT brief (confirm fixes closed the findings)

READ-ONLY. Do NOT modify files or run git write/checkout. Worktree: `/home/nathan/cec-placement`.
The post-fix diff is at `/home/nathan/cec-placement/docs/placement-audit-2026-06-14/impl-v2.diff`. Read it
+ the source under `scripts/`. The first audit (verdict needs-work) found these; each now has a fix — your
job is to VERIFY closure and check the fixes introduced NO new defect.

## Fixes to verify

- **BLOCKER-01 (gate-launder)** — fixed KIND-AWARE (not by changing shared `settle_outcome`, which would
  break legitimate routing-delta progress-crediting). New pure helper `cec_fullstack._placement_keep(verdict,
  pour_integrity_ok)` returns True only if `verdict=='vindicated' AND pour_integrity_ok is not False`. The
  run() placement-settle block computes `keep = _placement_keep(oc.verdict, cur_metrics['pour_integrity_ok'])`
  and `launder = vindicated and not keep`; a launder-blocked move sets status rolled_back, reverts
  `placement_base` to prev_base, and anti-ratchets the hypothesis. `cur_metrics` now carries
  `pour_integrity_ok`. VERIFY: a vindicated-on-objective_base move that fragmented a pour (pour_integrity_ok
  False) is NEVER promoted; routing-delta semantics are UNCHANGED (settle_outcome untouched).
- **FENCE-01 + TEST-RIGOR-01** — `cec_router.corridor_evict_repair` now gains a `fence` param, derives the
  LOCKED sense ICs (union of all cables' `sense_ics`) from `_board_corridor_model`, skips a violation whose
  ref is a sense IC / RS*/J* / in `fence['refs']`, iterates to the first MOVABLE violation, and stamps
  `fence` into the place_cluster edit; `apply_edit` passes `fence=edit.get('fence')` to
  `apply_corridor_evict`. New tests: manager moves the ESP (U1, movable) and REFUSES a fenced sense IC (U10).
  VERIFY: the locked Kelvin/§6.13 sense ICs (U10/U11/U20/U21) can NEVER be evicted by the manager tier;
  the lever still works for non-sense bodies.
- **AUDIT-PL4-001 (CONTROL_EVERY<=0 deadlock)** — new settle branch: `pending_deltas and last_control_metrics
  is None and lane=='augmented'` drops the unsettled deltas + reverts placement_base + clears
  pending_placement, releasing the one-in-flight guard. VERIFY: no deadlock in continuous-augmented mode;
  no regression to routing-delta handling in normal (CONTROL_EVERY>0) operation.
- **MED-02 (silent override-missing fallback)** — run() now, before the augmented route, checks
  `os.path.isfile(placement_base)`; if missing it reverts placement_base + drops the unsettled placement
  delta (so it is never credited against a committed-routed round) + clears pending_placement. VERIFY: a
  missing override cannot produce a false A/B credit.
- **CTRL-01** — `_placement_source_for` is now called with the concrete `ovd.BOARD_PCB[board]` (not None);
  the override arg is passed only when it differs from committed. VERIFY contract honored, control still
  routes committed.
- **SWIG-01** — `del b` added after Save in apply_edit place_cluster.
- **AUDIT-PL4-003** — a kept-but-not-actuated placement delta is now marked status 'skipped' + logged.
- **TEST-RIGOR-02/03, DETERMINISM-01** — e2e no_corridor cases; nearest_evict_delta edge/determinism cases.

## Verification already done (host)
checklist exit 0 / host suites pass; test_fs_actuator 26, test_ei02_control_lane 32, test_prompt_audit_fixes
34, test_corridor_model 62 all green; e2e 8/8 incl. real container legs (placed/fenced/no_corridor).

## Your job
Confirm each fix CLOSES its finding with a concrete code citation, and look hard for NEW defects the fixes
introduced — especially: (a) does the AUDIT-PL4-001 branch wrongly drop ROUTING (avoid) deltas in normal
operation? (b) does the MED-02 pre-check interact correctly with the settle timing? (c) does FENCE-01's
sense_ics fence over-block a legitimately movable body or under-block a locked one? (d) is `_placement_keep`'s
`pour_integrity_ok is not False` (vs truthy) the right predicate? Report only HIGH-CONFIDENCE issues.
