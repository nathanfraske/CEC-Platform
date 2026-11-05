# Bounded native repair and exact escape-probe diagnostics

## Scope

Generic operation supervision and exact-geometry search, with no product,
reference-designator, coordinate, or power-bus exception. Protected input:
`build/12vhpwr-pair-search-20260909/checkpoint/board.kicad_pcb`.
The archived PCIe 2-port control remains a regression input, not a newly
qualified fabrication release.

## Why the preceding campaign did not advance

`build/current-suite-routing-20260910-g` exhausted its 1,800-second campaign
budget. Source intake succeeded. Two critical-only recovery waves took 43.376
and 42.673 seconds, retained the 4-DRC/228-open parent, and stopped on repeated
unadmitted geometry. The subsequent placement co-optimization called an
isolated repair with another 1,800-second allowance. That child did not know
the parent had already spent several minutes preparing and testing the board.
Its output was buffered and its working evidence was temporary. The campaign
correctly reported budget exhaustion, but its stage journal still said
placement was running. These are execution/reporting defects, not evidence of
a newly routed or admitted board.

## Operation supervision

- Isolated operations now retain a live log, current phase, phase history,
  bounded stack samples, elapsed time, exit code, and terminal reason beside
  their candidate. Repair phases also checkpoint trial/finalist boundaries.
- Child allowances are capped by the remaining campaign deadline with a
  cleanup reserve. Placement repair defaults to 600 seconds; critical-only
  recovery defaults to 900 seconds. Both remain explicit policy parameters.
- Timeout and parent cancellation terminate the owned process group; they
  never target unrelated jobs. Completed search rejection (exit 2) is distinct
  from a worker crash and does not imply electrical admission.
- Isolated placement repair writes a disposable board family. Only a completed
  accepted change is copied back; failed or interrupted saves cannot damage
  the caller's incumbent. Source hash changes during the operation block
  promotion.
- The suite reconciles any still-running stage after observing its process
  exit. A timed-out stage cannot remain displayed as running, or count as a
  completed admission.

The first diagnostic replay exposed a defect in the new logger itself:
Python's asynchronous traceback dumper crashed at its first 60-second sample
(exit -11; the WSL fault address resolved to `_Py_DumpTracebackThreads`).
Periodic sampling was replaced with a Python/GIL-held sampler; native fatal
fault reporting remains enabled. The replacement retained complete samples
beyond that point. The original diagnostic and its failure are preserved,
not counted as a router regression.

## Exact search findings

The durable stack samples place the expensive work in initial baseline
preflight, inside coupled-pair portal fan-in and bounded endpoint escape.
Boolean segment probes were invoking the complete diagnostic admission path:
all four guards and foreign-blocker identity extraction, even after a guard
had already refused the leg. Repeated legs repeated this work.

A native synthetic counterexample also shows the zone broadphase incorrectly
inflated its search box by only the zone's local clearance. A 0.25 mm actual
gap therefore escaped a route's 0.40 mm requirement when the zone specified
0.10 mm. The exact KiCad collision call refused it, but the preliminary box
filter prevented that call. Both boolean admission and blocker attribution
must use the stricter route/zone clearance.

The correction covers both indexed snapshots and the uncached direct guard,
including its through-via caller. Synthetic native checks require both paths
to refuse the insufficient gap and retain a legally spaced path. The local
escape search now shares the same four exact predicates with its diagnostic
path, short-circuits only on refusal, and caches up to 4,096 exact
endpoint/partner results within one immutable solve. No cache survives a
board mutation or changes layer/width/clearance policy. Direct refusal
witnesses retain full blocker attribution. A repeated-leg regression reduces
22 geometry calls to 3 and 22 diagnostic collections to 2; this synthetic
call-count improvement is not an end-to-end speed claim.

The counterexamples are retained in:

- `build/escape-probe-counterexample-20260910.log`
- `build/zone-broadphase-counterexample-20260910.log`
- `build/bounded-priority-trace-20260910/`
- `build/bounded-priority-trace-20260910-v2/`

No timeout, skipped check, successful worker exit, or reduction in diagnostic
overhead is a routing or fabrication pass. Independent saved-board admission
remains required before a candidate can advance.

## Validation and measured limits

Final focused regression: **294 passed and 10 subtests passed**, with one
KiCad SWIG deprecation warning, in 60.98 seconds. This includes real process
timeout/cancellation, rejected-worker and accepted-change isolation,
invalid-budget refusal, exact native clearance counterexamples, paired
escape routing, and the anti-overfit gate. The new operation supervisor is
included in the generic-core audit. `git diff --check` passed for the slice's
touched files. Evidence: `build/bounded-escape-final-tests-20260910-v2.log`.

The final PCIe control replay remains **0 DRC / 0 opens / 615 tracks / 226
vias**, with identical board SHA-256, identical score, and the same complete
constraint report with eight existing blockers. It still fails broader
fabrication release. Evidence:
`build/bounded-escape-pcie-control-20260910-v2.json`.

The equal-budget diagnostic comparison (indexed-clearance correction and
escape memoization, before the subsequent uncached-guard alignment) exhausted
300.132 and 300.165 seconds. The first reached trial index 7; the second index
8, both out of 16. Baseline wall-timestamp deltas were 228.401 and 223.941
seconds. This single comparison is a small change, not a demonstrated overall
speedup. Both preserve the protected source and produce no admitted change.
All three diagnostic directories, including the failed logger experiment,
occupy approximately 4.8 MiB together; 77 GiB remained free in WSL.

The next bottleneck is budget composition and repeated constructive baseline
work. Measurement already establishes route evidence, but a fresh isolated
repair rehydrates without it and spends most of its allowance reconstructing
the baseline before screening alternatives. Any future reuse must bind the
PCB, project/rules, source hierarchy, routing policy, and engine; an evidence
key based only on board geometry is insufficient. Placement screening effort
also needs to leave a deliberate budget for proposals and finalists without
reducing independent final-route or saved-board admission requirements.

Comparison details: `build/bounded-escape-closeout-20260910.json`.

The final canonical critical-recovery adapter replay completed normally in
**129.123 seconds**, including preparation and validation, inside its explicit
180-second allowance. Its two routing phases took **43.963 and 44.894
seconds**. All three coupled-pair tiers were refused by physical admission in
both waves. The saved results remain **4 DRC / 228 opens**, with zero foreign
incursions on laid power pours, unchanged protected prefix, and unchanged
footprint poses. The second wave stopped on `repeated_unadmitted_geometry`.
The adapter correctly classified exit 2 as a completed but rejected search,
not a crash or successful board admission. Source board, full declared source
inputs, and engine signatures remained unchanged. No candidate was promoted.
Evidence: `build/bounded-final-recovery-20260910/result.json`.

This slice therefore improves clearance correctness, failure visibility,
interruption safety, and local search efficiency; it does **not** reduce the
board's remaining DRC/open counts. The bounded diagnostic and recovery jobs
are finished, rather than left looping on the same rejected geometry.
