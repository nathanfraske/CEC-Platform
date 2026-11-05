# Committed power reservations during pair reconstruction — 2026-09-15

## Completed cohort and exact finding

`build/nested-budget-suite-20260914/suite.json` completed. Hub took 618.1 s,
12VHPWR 999.0 s and PCIe3 304.2 s. All three remained blocked at placement;
all source, hierarchy and engine hashes were unchanged. The immutable reviews
are correctly marked BLOCKED, with unchanged input boards, not newly routed
or fabrication-qualified boards:

- [Hub](http://localhost:8090/?id=pass-nested-budget-suite-20260914-hub-standard-rev2-4547b0b149)
- [12VHPWR](http://localhost:8090/?id=pass-nested-budget-suite-20260914-12vhpwr-standard-1b9b6d9b1c)
- [PCIe3](http://localhost:8090/?id=pass-nested-budget-suite-20260914-pcie-8pin-3port-f2040ac712)

The repaired operation budget worked: Hub's worker completed in 566.5 s,
rather than being killed at the old outer cap. Trial 3 passed power, physical
checks, actual CAN construction and independent partial-pair signoff. The
refilled pair proof measured 254 → 242 opens with DRC unchanged at 12. These
are diagnostic trial counts, **not improvement of an admitted Hub board**.
Pair connectivity/physics, retained copper and poses also passed the final
recheck, but its power re-admission failed. Trial 4 constructed a connected
pair but failed independent pair physics and was also correctly rejected.

The retained trial artifacts made a direct before/after replay possible:
`build/priority-handoff-forensic-20260915/receipt.json`. Both sides bind the
same complete power state. The pre-pair board passes exact power admission;
the post-pair board fails with CAN tracks crossing reserved +5VSB and
port-power territory. The error excerpt lists twelve tracks and is capped at
twelve; it is not a total-incursion count. Thus this was **not lost sidecar data**. Regenerating
power after that conflict then failed to fit a required two-via power bridge.
No rejected board was promoted.

## Shared repair

The critical constructor had no explicit bound recipe context. Its reservation
compiler depends on environment-scoped policy, and the default critical-first
mode intentionally omits negotiable future-power corridors. That is incorrect
for a reconstruction which already owes a committed exact power solution.

1. An explicit frozen-power reconstruction context revalidates the current
   board's sibling authority, binds its exact path and enables power-first
   reservations. Stale inherited environment cannot substitute another board's
   state. The environment is restored on success or exception. Missing or
   disabled committed authority refuses before routing.
2. Both atomic priority-dependency rebuilding and canonical critical recovery
   use this context. Recovery's tiered fallback is covered too. Each newly
   admitted pair parent is rebound; ordinary pre-power callers retain their
   existing policy.
3. Local paired-escape enumeration now includes reservations in each member's
   clearance predicate. It can choose a legal alternative instead of selecting
   a shortest blocked escape and only rejecting it afterward. The final
   reservation check remains as an independent defensive boundary.
4. Constructor journals retain reservation policy, binding, fingerprint,
   corridor and keepout counts. Failed power regeneration now retains the
   preceding exact-admission failure and original binding rather than hiding
   the initiating cause behind the final planner error.

No bus dimensions, current/via requirements, clearances, pair quality limits,
placement coordinates or interfaces were relaxed. No new board/refdes selector
was introduced. This change enforces existing power ownership; it does not
clip or reroute power to accommodate the pair.

## Verification

- `build/committed-power-integrated-tests-20260915.log`: **299 passed**, plus
  seventeen subtests. The earlier 158-test focused set overlaps and is not
  added. Synthetic cases include four rotated native local routes which find
  legal alternatives around reserved power, blocked-terminal rollback,
  layer-specific access, stale-environment restoration and missing-authority
  refusal.
- `build/committed-power-cross-board-20260915.json`: read-only replay across
  all six explicit inputs. Hub, PCIe2 and PCIe3 have bindable stored states;
  their 504, 434 and 642 projected reservation rectangles respectively all
  reject a crossing test segment. This is reservation-context verification,
  not three successful full routes. The stored 12VHPWR input, EPS and ATX did
  not bind a complete state; none was invented. The canonical pipeline must
  establish authority before those constructors run. All six sources and
  hierarchies, the engine and caller environment were unchanged.
- `build/committed-power-control-20260915.json`: historical PCIe2 board hash,
  board regression and all four probe objects exactly match the preceding
  control. Its pre-existing release failures remain visible, including
  pair/craft checks; unchanged results are not a present-day fabrication pass.
- `build/committed-power-generalization-20260915.json`: sixty neutral modules,
  zero core selector violations; legacy physical/runtime findings remain
  23/380. Whole-pipeline generic maturity is still false.
- `git diff --check` passed. Free space was 71 GiB, above the 16-GiB floor.

## Current follow-up

Canonical replay: `build/committed-power-suite-20260915/suite.json`. The
launcher verifies all six explicit source/hierarchy identities and runs Hub,
12VHPWR and PCIe3 concurrently with three jobs, two workers each, twelve
placement trials, eight route passes, 1,800-second board limits and the storage
floor. Check this journal and live processes before any restart or engine edit.
Body-free immutable completion previews go to the dashboard and
`C:/Users/Admin/Documents/CEC-Board-Reviews/committed-power-suite-20260915/`.

EPS/ATX still require a coupled interface-geometry solution, not a routing
waiver. PCIe2's latest admitted continuation remains 0 DRC / 12 opens and its
unchanged exhausted search was not rerun. The next independent diagnostic
slice remains bounded finalist-key attribution for placement ranking, described
in the preceding report; do not weaken ranking without that evidence.
