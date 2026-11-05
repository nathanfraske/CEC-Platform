# Fixed-share pair-probe cohort refill — 2026-09-15

## Reproduced scheduling defect

The completed PCIe3 producer allocated 555.530 s for pair probes, initially
funding four of seven proposals at two workers and a worst-case estimate of
245 s per two-job batch. Its four probes consumed only 128.503 worker-seconds
in total, yet the coordinator permanently deferred the other three. It did
not reconsider dispatch after the initial batch completed. The corresponding
12VHPWR operation allocated 465.666 s, dispatched two proposals, consumed
250.777 worker-seconds and deferred eleven. These are worker-time totals,
not elapsed wall-time or whole-pipeline speedups.

Evidence: `probe-scope-suite-20260915/.../operation-priority-repair-v05vbi2w/report.json`
for PCIe3, and `reservation-index-suite-20260915/.../operation-priority-repair-bk8zpy33/report.json`
for 12VHPWR. Neither timeout nor deferred proposal establishes geometric
infeasibility. The old one-time worst-case dispatch quota stranded available
compute while useful, already-materialized proposals were still unmeasured.

## Generic repair

`cec_operation_budget.run_probe_cohorts` consumes the existing allocation and
ordered finite job list. After a cohort finishes, it can fund previously
unsubmitted jobs from **actual remaining time in the original share**. Every
new cohort still needs its full unchanged worst-case per-pair/batch estimate.
The allocation, enclosing deadline and finalist reserve are never renewed.
There is no decrease in probe effort, no repeat of a submitted slot and no
geometry-specific rule. A worker/protocol failure stops refills without a
serial retry. Budget supervision remains the hard timeout backstop.

The shared placer keeps the same process pool alive for subsequent cohorts,
retains canonical slot-ordered result processing, and performs the same full
finalist/physical/power checks. Incomplete probes cannot gain admission. The
native and outer co-optimization reports retain dispatched/deferred slot lists,
cohort wall times, original share and stop reason. This fixes scheduling, not
the geometric/pair-construction failures themselves.

## Verification and live follow-up

The focused suite passed **134 tests** in 54.07 s. Synthetic checks cover
fast refills (seven jobs instead of four inside the same 555-second share),
full-cost jobs leaving the remainder deferred, parent deadline/finalist
reserve, worker failure without retry, missing/duplicate result identities,
single-worker and finite unbounded-window cases, invalid budgets and outer
journal persistence. The integrated suite passed **226 tests and 15 subtests**
in 66.55 s (`build/probe-cohort-refill-integrated-tests-20260915.log`). Counts
overlap the focused set. `build/probe-cohort-refill-control-20260915.json`
exactly matches `power-replan-isolation-control-20260915.json` for the protected
PCIe2 board SHA, board regression and all four probes. Its pre-existing broader
release failures remain; this is non-regression, not renewed fab qualification.
`git diff --check` passed.

Completed canonical follow-up (2026-09-15T03:35:18Z to 03:51:40Z):
`tmp/probe_cohort_refill_followup_20260915.py`, writing
`build/probe-cohort-refill-suite-20260915/suite.json`. Coordinator PID 3217861;
initial board PIDs 3217864 and 3217865 have exited. Inspect current
processes and the newest suite ledger before any shared engine edit or launch.
It tests PCIe3 and 12VHPWR concurrently, with two workers per board, 1200-second
priority-operation caps, 1800-second board deadlines and a 16-GiB storage floor.
All six explicit current-BETA source/hierarchy hashes are checked before
dispatch. The suite records source/engine identity, preserves release gates
and publishes immutable body-free reviews on completion.

The scheduling fix worked natively, but **neither board admitted a new
placement**. PCIe3 dispatched all seven probes (previously four), using two
cohorts of 64.801 s and 8.752 s within the original 559.669-second share. Its
whole pass took 235.305 s; that is a different evaluation path, not a controlled
whole-wave speedup claim. The two retained Kelvin moves still failed physical
power-territory admission. 12VHPWR dispatched four probes (previously two),
using 247.706 s of its original 531.319-second share, and left nine deferred.
All four encountered the unchanged CAN search timeout, so none was eligible
for finalist admission. Its complete pass took 944.870 s.

Source boards, complete source hierarchies and engine hashes remained unchanged.
Both output hashes exactly match their inputs. The immutable body-free gallery
`all-boards-0bf9dbf7b2de46a3.png` was inspected; its cards correctly say PLACEMENT,
BLOCKED and NOT FAB SIGNOFF. Verified review links:

- [12VHPWR placement](http://localhost:8090/?id=pass-probe-cohort-refill-suite-20260915-12vhpwr-standard-21827dc653)
- [PCIe3 placement](http://localhost:8090/?id=pass-probe-cohort-refill-suite-20260915-pcie-8pin-3port-4ab5a994a3)

Windows copies are in `C:/Users/Admin/Documents/CEC-Board-Reviews/probe-cohort-refill-suite-20260915/`.
The next shared slice addresses the owned-anchor proposals discarded before
these probes: [typed atomic handoff](owned-anchor-replacement-handoff-2026-09-15.md).

Hub's committed-power pair-reconstruction blocker is upstream of this probe
quota; an identical exhausted Hub campaign would not test the new behavior.
PCIe2 remains at 0 DRC / 12 opens in its latest continuation. EPS/ATX remain
behind actual terminal-pad conflicts and the coupled mating ECO. No unrelated
board geometry, current budget, high-current bus or span limit changed.
