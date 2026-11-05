# Local route length is a search constraint, not a late veto

## Completed priority/power regression-guard pass

`build/authority-physical-followup-suite-20260915/suite.json` finished
**18:10:41Z**, board-worker elapsed **1151.752 s**, all descendants gone and
all source/hierarchy/engine guards passed. All three provisional pair
improvements failed the newly required post-power physical check. The existing
bounded alternate/exclusion loop restored the exact **400ffdd8635e** PCIe3
input: local craft passes, 12 priority failures remain, no main routing.
This verifies automatic regression prevention, not a board-quality gain.
No more unchanged PCIe3 waves are justified by that result.

Verified immutable placement review ID:
`pass-authority-physical-followup-suite-20260915-pcie-8pin-3port-3d983195e1`.
Top body-free Windows image:
`C:/Users/Admin/Documents/CEC-Board-Reviews/authority-physical-followup-suite-20260915/pcie-8pin-3port/render.png`,
SHA **2b44e3a9c2621c9332a0309d875081d41f4be066ba81b2acc956752543d12f7e**.
Visually inspected; correct source hash, BLOCKED placement, not a route or
fab signoff. Dashboard archive API resolves the exact ID.

## Implemented board-neutral search repair

Local supply and shared-return links previously rejected an overlong path
*after* the router returned its first collision-free path. That could hide a
shorter legal alternative. POFV/ordinary bridges similarly spent work finding
paths which could never meet the caller's unchanged local-length limit.

The optional `max_length_nm` now travels through guarded canonical paths,
single-layer maze, POFV/mixed-seat bridge, ordinary bridge and multilayer maze.
It is derived from the existing local-cell limit, not a newly relaxed bound.

- Reject overlong canonical candidates before expensive geometry tests,
  then continue to shorter alternatives.
- Use admissible Euclidean remaining-distance bounds for octilinear paths
  and Manhattan bounds for the Manhattan multilayer maze.
- Reserve actual endpoint-stub copper length before searching the middle;
  impossible seat pairs and endpoint detours are pruned before maze work.
- Count planar copper exactly as the existing caller did; routing via-penalty
  costs are not substituted for physical length.
- Preserve all native edge, foreign-copper, frozen-power, profile-qualified
  via, width/neckdown and complete-board DRC gates. Unbounded callers retain
  prior behavior. Invalid bounds fail closed. Bounded exhaustion remains
  unproved, not a declaration that no physical route exists.

Files: `scripts/cec_fr.py`, `scripts/cec_decoupler_cell.py`,
`tests/test_local_route_length.py`. No board/refdes/coordinate exception added.

## Validation and measured limits

- Broad integration: **340 passed and eight subtests** in
  `build/local-length-integration-tests-20260915.log`.
- Final focused/native tests: **168 passed and eight subtests** in
  `build/local-length-final-tests-20260915.log` (overlaps broad coverage).
- A rotated/translated native fixture previously chose a legal 10-mm path;
  the unchanged 4.05-mm limit now makes it find the valid 4-mm alternative.
  Native maze tests verify lower-bound pruning, finite effort and unchanged
  foreign-copper rejection. No trial copper is added to those fixtures.
- Final six-family replay:
  `build/local-length-suite-replay-v2-20260915/report.json`: all inputs and
  hierarchies unchanged; native rollback exact for four admitted families;
  EPS/ATX retain the interface ECO hold. PCIe2/PCIe3 remain locally clean,
  Hub retains five local/proximity failures, VHP retains C7/U1.3.
  PCIe3's native pre-route producer still passes 0 DRC / 254 -> 175 opens,
  the same local construction result as before, not a new full route.
- `build/local-length-v2-control-comparison-20260915.json`: protected
  historical PCIe2 hash, complete regression and four probes unchanged;
  only generalization evidence differs. No release hold waived.

The read-only CPU-effort ablation
`build/local-length-effort-probe-20260915/report.json` tested 4096, 16384 and
65536 work units on Hub and VHP concurrently. **Neither improves its local
failure count.** At 65536 VHP's last C7 search actually completes its bounded
menu after 30339 units (about 0.789 s) without a legal path inside 3.280 mm.
This is not global no-path proof, but increasing its wall timeout is not the
next repair. Production remains at 4096 units; the experimental overrides
exist only in the read-only helper. Do not increase defaults without benefit.

## One bounded affected-placement experiment

Journal: `build/local-length-followup-suite-20260915/suite.json`;
harness `tmp/local_length_followup_20260915.py`. Concurrent **Hub and VHP**,
four workers each, 1200-s board limits, 600-s priority cap, 16-GiB free floor,
exact inputs from `build/locked-reconcile-inputs-20260915.json`.

Hypothesis: shorter-path selection may qualify placement proposals previously
rejected by a late locality veto, even though the unchanged source layouts
remain blocked. Run this **once** to measure the changed search, not as a
repetition of fixed-placement extra-effort probes. Do not launch another
unchanged cohort if it plateaus. Next work should be coordinated whole-cell
seating / return-portal placement with preserved buses, or coupled EPS/ATX
mechanical fit. Keep the engines fixed until this cohort exits. Standard
publisher emits verified body-free reviews on completion; no current new
board improvement or fab readiness is claimed.

**18:40Z launch receipt:** started **18:40:32Z**, Hub PID **396343** and
VHP PID **396344**, parent session **15392**. Both are running; 68 GiB free.
Keep shared engines fixed until both and their descendants finish. This
receipt is historical; inspect the current journal before the next action.
