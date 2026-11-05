# Placement probe coverage, not repeated rejected poses

## Completed predecessor

`build/local-length-followup-suite-20260915/suite.json` finished **18:52:56Z**.
Hub worker 213.7 s; VHP worker 695.4 s. All source/hierarchy and engine
guards pass. Neither board entered main routing.

Hub accepted two 0.05-mm capacitor moves: craft failure count stays **five**;
one direct supply distance changes 1.35 to 1.32 mm. This is not closure.
Output SHA `de4a27aa574630d14362f4702e42582dfc69d866d1a6acafb4db73e5b4ef0f60`.
VHP retains exact `3af185f38201c8f9e0b08a3f85204cc40b61e4998fe588b7d82902a3ce32293a`,
one deferred local-cell issue and one priority-route refusal. No new routing
gain. Both completed, body-free reviews are published and visually inspected:

- `pass-local-length-followup-suite-20260915-hub-standard-rev2-962c45aaba`
- `pass-local-length-followup-suite-20260915-12vhpwr-standard-327be99610`

Both IDs were verified in the live dashboard API. They are blocked placements,
not routed/fab candidates. Existing inputs are not replaced by recency alone.

## Measured scheduling defect

Each Hub round generated 2263 eligible proposals, including 48 return-territory
reseats, but tried only one of those 48: the **same capacitor-only C2 move**,
which adds a ground-length violation and worsens the proximity error. Complete
IC-plus-owned-capacitor translations shared a probe group with cheaper IC or
capacitor changes. The second round repeats the rejected C2 pose while an
unrelated C28 0.05-mm improvement changes the overall baseline. This evidence
does not prove that any untested macro is legal; it proves insufficient coverage.

## Generic change

- `cec_local_return_feedback`: complete return-path macros and capacitor-only
  exits have separate topology-derived probe groups. No board/ref/coordinate
  selector was added; frozen placement exclusions and whole-cell ownership stay.
- `cec_placement_probe_coverage`: prefer least-visited proposal poses, with the
  existing blocker-fair selector within each tier. Keep the same finite budget
  and hard geometry/electrical gates. A tried proposal is **not excluded** and
  no pass/failure proof is cached: changed neighbors can make a retry useful.
- `repair_placement_craft` journals coverage and carries scheduling history
  through its rounds/epochs, scoped to one repair invocation. Overlap/switch/
  electrical stage precedence and monotonic acceptance are unchanged. The
  first empty-history selection is identical apart from the new macro groups.
- Registered the new module in the static generic-core audit (73 modules,
  zero core findings). Existing 23 physical / 380 runtime legacy findings remain;
  this is not a claim that the entire legacy pipeline is generic.

## Validation

- `build/probe-coverage-integration-tests-20260915.log`: **286 passed**.
  Synthetic renamed/translated/rotated fixtures cover finite budgets, complete
  cell identity, breadth before repeats, eventual retry, unchanged first-round
  behavior, malformed pose handling and per-invocation epoch history.
- `build/probe-coverage-boundary-tests-v2-20260915.log`: **40 passed**,
  overlapping integration coverage; do not sum as unique tests. An earlier
  boundary command named a nonexistent test file and ran no tests; v2 uses
  the actual `test_pipeline_generalization.py` file.
- `build/probe-coverage-suite-replay-20260915/report.json`: all six current
  inputs/hierarchies unchanged; exact native copper/group rollback on four
  admitted families. PCIe2/3 local cells still pass, Hub/VHP retain their
  prior local failures, EPS/ATX refuse unadmitted interface ECOs. PCIe3 local
  producer remains 0 DRC / 254 to 175 opens, not a new full route.
- `build/probe-coverage-control-comparison-20260915.json`: protected historical
  PCIe2 PCB, complete regression and probes unchanged; only generalization
  evidence differs. Its release holds are not waived.

## One affected full pass

`build/probe-coverage-followup-suite-20260915/suite.json`, harness
`tmp/probe_coverage_followup_20260915.py`: Hub, four workers, 12 trials/round,
1200-s board cap, 600-s priority cap, 16-GiB free floor. Explicit ce61 source
from `build/locked-reconcile-inputs-20260915.json`, not mtime selection.
Inspect the journal and descendants before editing shared engines or dispatching.

Other families were replayed, not falsely reported as live routing workers:
PCIe2 still has 10 opens; PCIe3 is held by priority routing; VHP by priority
routing; EPS/ATX by coupled interface placement/mechanical qualification.
Do not rerun them unchanged to inflate parallel job counts. If the new Hub
pass covers more moves but retains five failures, the next repair must use
the measured rejected macro geometry / coordinated return-portal seating.

## Completed full-pass receipt (19:24Z)

The new pass started **19:20:48Z**, Hub PID **419538**, and finished
**19:24:42Z**; worker elapsed **217.49 s**. No pipeline or power-worker
descendants remain. Source/hierarchy and engine guards pass; free disk 67 GiB.

The scheduling hypothesis is confirmed:

- Return-territory probes: **1 + 1 repeated attempt before**, now **4 + 5**.
- Both rounds select 12 untried proposals; round two carries 12 prior entries,
  has zero revisited selections, and spends the unchanged 12-proposal budget.
- Complete U3/switch-cell translations now receive exact evaluation, including
  automatically coupled C3/L1. Its sampled 0.268/0.333-mm translations preserve
  the internal proximity fault and do not clear local return construction.
- Neither new clearance failures nor worse local craft are accepted. Final
  Hub PCB is **byte-identical de4a** to the previous pass, still **five blockers**.
  Improved coverage is not routing or fab progress. Do not repeat this cohort.

Verified dashboard review:
`pass-probe-coverage-followup-suite-20260915-hub-standard-rev2-cf17c31f74`.
Body-free PNG was inspected at
`C:/Users/Admin/Documents/CEC-Board-Reviews/probe-coverage-followup-suite-20260915/hub-standard-rev2/render.png`.
The same board appearance is intentional retained-best geometry, not an old
source substituted for a new result. It is explicitly BLOCKED / NOT FAB.

While that job ran, PCIe2's 905f route oracle was read without edits. It retains
10 opens across six nets. Older final-completion certificates identify local
locked-copper/pad escape conflicts, but include THRESH (no longer open) and
miss some later final endpoints. **Refresh final endpoint certificates against
the selected PCB before using them for another repair**; that record is not
current complete proof. No fresh routing or source mutation was performed.

Next distinct work: Hub coordinated cell/return-portal seating; current PCIe2
final-certificate refresh and owned escape repair; PCIe3 bounded complete-cell
relocation for priority reach; VHP exact coupled USB escape; EPS/ATX coupled
main/daughterboard 2D fit within existing edge constraints. All remain separate
suite work, not permission to rerun the same failed wave or enlarge mechanics.
