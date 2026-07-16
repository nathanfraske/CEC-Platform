# Placement EI-parity implementation — adversarial audit brief

READ-ONLY AUDIT. Do NOT modify any file, do NOT run git checkout/stash/commit, do NOT mutate the worktree.
Only READ. Worktree (branch claude/placement-corridor): `/home/nathan/cec-placement`. The full uncommitted
diff is at `/home/nathan/cec-placement/docs/placement-audit-2026-06-14/impl.diff` (1010 lines). Read it first,
then read the surrounding source under `/home/nathan/cec-placement/scripts/` and `.../tests/` for context.

## What was built (PL-01..PL-10)

Made PLACEMENT a first-class EI-instrumented actuating tier in the cec_fullstack A/B loop, with parity to the
routing levers. Before, the `cec_fs_actuator` 'replace' Delta was INERT (intent=None, no consumer); now the
loop can MOVE PARTS (evict a sensitive body out of a foreign high-current corridor band), lane-gated + settled
+ rolled back like the routing corridor-avoid.

Pieces (file:function):
- **cec_fs_actuator.py**: `_placement_intent()` builds a LIVE intent for a 'replace' Delta (ref-target or
  net-target); `finding_to_delta` + `v4_structural_escape` populate it; `Delta.as_record` summarizes it
  compactly. The FENCE (`is_fenced`) still refuses a pinned/Kelvin/sense target BEFORE the intent is built.
- **cec_place.py**: `nearest_evict_delta()` (the ONE canonical band-edge displacement, dedup'd from the two
  former inline copies); `apply_corridor_evict()` gains a `fence` param (refuse a fenced ref at the lever) +
  returns a `restore` record (pre-move poses); `restore_poses()` (rollback); `_cluster()` now sorted.
- **cec_router.py**: `corridor_evict_repair()` now emits `place_cluster` (was the cap-blind `place_nudge`) +
  skips a structural RS*/J* ref; `apply_edit` gains a `place_cluster` case delegating to `apply_corridor_evict`.
- **cec_overnight_directed.py**: `route_one_worker` + `_exec_route_one` + the CLI thread a
  `--board-pcb-override` so the augmented lane routes a moved floorplan COPY; None -> committed (default).
- **cec_fullstack.py**: `apply_placement_move()` (in-container, mirror `layer_stagger`): resolves the offending
  body + band from `corridor_violations`, RE-CHECKS the fence (2nd wall via `is_fenced`), evicts on a per-round
  COPY of the COMMITTED floorplan -> `build/fullstack/placed-r{N}.kicad_pcb` (placement edits the SOURCE, never
  routed copper). `_placement_source_for()` (control NEVER sees the override). `run()` wiring: `placement_base`
  (promoted moved floorplan), `pending_placement` {prev_base,override,delta_id}, `refuted_placement_keys`; the
  ACTUATOR BUILD block applies a kept 'replace' delta (one in flight, not in refuted set) -> sets
  `placement_base` + pending; the SETTLE block settles it through the existing kind-opaque DeltaLog
  (gate_metric `objective_base`) with a TWO-PHASE promotion (vindicated -> keep/compound; refuted/overturned ->
  revert `placement_base` to `prev_base` + anti-ratchet) and a control-round revert; `_placement_row_fields` +
  `placement_moved_rate` in the A/B table; `real_anchor_ratio` `placement_moved` kwarg (an applied move = +1
  DETERMINISTIC anchor, model unchanged).

## Invariants the implementation claims (ATTACK these)

1. **NO gate-launder**: a placement move that fragments a /SENSEC pour cannot be credited. CLAIM: inherited --
   cec_fullstack ~line 1761 folds `pour_integrity_ok` into `gates_pass` for EVERY round; the moved board routes
   through the SAME `_exec_route_one` path, so a fragmented move gets `gates_pass=False` -> cannot vindicate
   (gate-pass dominates `settle_outcome`). VERIFY the fold runs on the override-routed board + that `cur_metrics`
   reads the folded value at settle time.
2. **CONTROL lane stays signed-only**: a control round routes the COMMITTED board (never the override) and never
   moves; `_placement_source_for('control',...)` returns committed. VERIFY no leak (override path, carry, build
   block all augmented-gated).
3. **FENCE holds across BOTH walls** (host `finding_to_delta` is_fenced + in-container `apply_placement_move`
   is_fenced + the lever `apply_corridor_evict` fence param) -- a pinned/Kelvin/sense/shunt part is NEVER moved.
4. **TWO-PHASE rollback / no ratchet**: vindicated promotes/compounds; refuted/overturned/control reverts
   `placement_base` to `prev_base` + adds the hypothesis to `refuted_placement_keys`.
5. **The committed floorplan on disk is NEVER mutated** (placement edits a per-round COPY).
6. **Determinism**: sorted cluster + reproducible eviction geometry + a fresh in-container LoadBoard/Save/del-board
   (the 4 pcbnew SWIG footguns).
7. **Additive/opt-in**: no replace delta -> `placement_base` None -> routes committed exactly as today.

## Verified so far (do not re-litigate, but CHALLENGE if you find a hole)

checklist host suites PASS; +27 host tests green both orders; e2e 6/6 incl. a REAL in-container
`apply_placement_move` leg; SB-08 byte-identical to the committed baseline (the 253.2 max_T fail is a
PRE-EXISTING owner-gated AM-04 red, not from this work).

## Your job

Find REAL defects -- correctness bugs, broken invariants, race/timing errors in the `run()` state machine, fence
holes, launder paths, determinism hazards, or test tautologies/missing teeth. Default to SKEPTICISM but every
finding must cite file:line/function + concrete evidence + a refutation attempt (why it might NOT be a bug).
Prefer a few HIGH-CONFIDENCE findings over many speculative ones.
