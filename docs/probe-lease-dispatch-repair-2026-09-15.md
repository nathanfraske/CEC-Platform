# Complete-probe lease dispatch and priority-budget diagnosis

## Why the last PCIe3 pass did no pair work

`build/coupled-cell-followup-suite-20260915/pcie-8pin-3port/02-placement/operation-priority-repair-vtka30r9/report.json`
records 16 attempted placements, 12 legal, three Kelvin screens, **zero pair
probes**. Nine candidates were deferred, not geometrically rejected.

The invocation helper explicitly set a **120-second** priority-repair cap.
At dispatch 96.865 seconds remained, of which 60 were protected for finalists.
Two affected pairs at the unchanged 120 seconds each need a 245-second probe
cohort including setup: 305 seconds remaining including that reserve. The
shortfall was **208.135 seconds**. This was an underfunded run configuration,
not evidence that all nine candidate placements cannot route. Do not repeat it.

## Generic scheduler defect repaired

Independently, minimum-cohort borrowing set the fixed share to exactly one
batch cost, then dispatch subtracted a positive elapsed time and floored the
result. A precisely funded batch could therefore dispatch nothing. Existing
tests held the mock clock still and missed it. Pool setup also occurred before
the scheduler started its clock, effectively renewing the share.

The allocation now anchors its monotonic clock at allocation time. The first
cohort credits only actual already-spent setup time, capped by its declared
setup allowance; full per-pair solver effort and finalist reserve remain intact.
Later cohorts get no such credit. Slow setup cannot renew the lease. Machine-ULP
rounding is handled explicitly at the batch-count division. Every dispatch
records remaining estimate, setup already spent, and final allocation age.
Budget reports now state the minimum remaining time and exact shortfall, and
the outer pipeline journal preserves those reports. No board names, refdes,
coordinates, electrical limits, release gates or physical geometry are involved.

## Validation

- Integration: `build/probe-lease-integration-tests-20260915.log`, **214 passed**.
- Final focused/generalization tests: `build/probe-lease-final-tests-20260915.log`,
  **89 passed** (overlapping coverage; do not add these as 303 unique tests).
- Synthetic clock tests include microsecond and fractional setup, exhausted
  setup allowance, shortened parent deadline, unchanged per-pair effort,
  no duplicate dispatch, worker failure, fixed-share refill, and journal transport.
- Six current hash-bound board families:
  `build/probe-lease-suite-replay-20260915.json`. Actual native board pair counts
  drive simulated-runtime scheduling replays; all sources/hierarchies and
  engine signatures are unchanged. This is **not** physical route admission.
- Protected historical PCIe2 regression:
  `build/probe-lease-control-comparison-20260915.json`: exact PCB hash,
  whole-board regression metrics and all four probes unchanged. Only the
  generalization report differs; existing release holds remain.
- Core generalization audit: 72 checked modules, zero core violations. The
  broader legacy audit still reports 23 physical and 380 runtime findings;
  this does not certify the whole pipeline as fully generic.

## Bounded continuation

`tmp/probe_lease_followup_20260915.py` runs one fresh canonical PCIe3 attempt
with a 600-second repair cap, unchanged 120-second per-pair effort, two workers,
a 2400-second board cap, 16-GiB disk floor and hash-bound input 400ffdd8635e.
Output: `build/probe-lease-followup-suite-20260915/suite.json`.
Check that journal and process tree for live/completed state; do not duplicate it.
Do not edit shared engine code until it exits. Full results publish immutable
body-free dashboard reviews through the standard suite publisher.

Other boards keep the exact previously qualified inputs and documented holds:
PCIe2 stays at its better 905f partial route (0 DRC / 10 opens), not the longer
c6 result with the same opens. Hub and 12VHPWR have unchanged local-cell and
priority-route blockers; EPS/ATX require admitted coupled interface geometry.
Do not spend unchanged full waves on those known physical failures. Kelvin
range move generation/severity scoring remains a separate unimplemented slice.

**Live observation 17:16Z:** dispatched 17:13:39Z, pipeline PID 364685,
parent session 97288. Priority measurement completed in 84.921 seconds;
the next phase is the funded repair operation. No main routing or new geometry
has yet been claimed. Dashboard HTTP 200; 68 GiB free. This observation is not
a substitute for checking the live journal on the next turn.

**17:17Z observed dispatch:** `operation-priority-repair-_g5cnw_l` is live,
worker PID 366755, with its full 600-second lease. Unlike the prior zero-probe
run, cohort 0 dispatched slots 0/1 and completed in about 8.07 seconds; cohort
1 dispatched slots 2/3 with 250.112 seconds left in the fixed probe share.
The progress journal proves real dispatch, not placement improvement yet.
Observe the finished report before selecting any new continuation input.

**17:19Z checkpoint:** first repair round accepted an exact-full-evidence
improvement: critical refusals **12 -> 11**, pair remaining edges **2 -> 1**,
four measured pair probes and two complete finalist evaluations. This is
still a private, non-promotable checkpoint until the operation finishes.
Expected vias improve 139 -> 137 and wire demand 1286144 -> 1249280; forecast
reservation crossings worsen 49 -> 50 and overflow 192639 -> 193919. The
existing critical-first lexicographic policy admits that tradeoff; do not say
every metric improved. Second-round cohort 0 actually dispatched with only
**244.999698 seconds** of its borrowed 245-second share remaining, exercising
the repaired setup-credit branch on a live native run. Its per-pair effort
remains 120 seconds. Do not promote or render this diagnostic checkpoint as
a finished canonical board.

## Other-family failure evidence inspected during the live pass

No shared-code edits were made during this cohort. The prior native reports at
`build/coupled-cell-suite-replay-v2-20260915/` identify these next work classes:

- Hub: four immediate-ground-return construction failures plus the previously
  reported proximity failure. Both owner-first and capacitor-first orders are
  exhausted; every one of 64 ordinary dogbone sites fails via-spot clearance
  for several cells. One capacitor accepts its declared minimum POFV, but the
  guarded same-layer shared link to the owner still fails. A whole-cell
  placement/return-portal search is needed; repeating the two-order search is
  not a new strategy and shrinking the fabrication limits is not a repair.
- 12VHPWR: C7/U1.3's last local supply search stops at **4096 work units in
  1.326 s**, before its ten-second wall budget, with direct distance 2.307 mm
  and unchanged local path bound 3.280 mm. Returned bridge candidates are
  5.750 mm or longer and correctly rejected. Ground returns themselves fit
  in this diagnostic attempt. Thus simply lengthening its wall timeout will
  not help; investigate admissible lower-bound pruning/placement feedback or
  a separately bounded work-effort tier. This is search exhaustion, not a
  no-path proof. Path length here sums planar copper, not full via barrels.

These are diagnostic observations on hash-bound prior native artifacts, not
newly accepted layouts or reasons to move protected power buses.
