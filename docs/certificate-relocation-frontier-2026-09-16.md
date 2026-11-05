# Truthful certificate-relocation frontier — September 16

## Native observation and generic correction

The previous slice exposed a foreign support obstruction in current PCIe2.
This continuation tried only **new** poses, skipping the four already recorded
against the exact same canonical source and target. It requested eight poses,
but the existing nonproductive-prefix guard stopped after six. The old report
then said `candidate_exhausted`, although two generated poses were unvisited.

That is an evidence defect: the finite per-call work bound is not exhaustion of
the generated proposal menu, much less proof that the geometry is unroutable.
`_attempt_footprint_relocation` now reports generated, prior-skipped, scheduled
and unvisited primary poses on success and failure. It distinguishes
`nonproductive_prefix_budget`, `candidate_trial_budget`, explicit global effort
stops and actual finite-menu `candidate_exhausted`. All receipts explicitly set
`exhaustion_is_no_path_proof: false`.

Search order, six-pose early stop, caller trial/wall limits and all native
acceptance/rollback checks are unchanged. The counters describe primary poses;
a nested mobility expansion has its own receipt. Skipped history outside the
current generated menu does not inflate the frontier count. There is no board,
reference, net or coordinate selector. This changes reporting, not geometry or
search behavior, so repair algorithm revision v45 is intentionally retained.

## Verification

- **295 tests and eight subtests passed** in 17.65 s:
  `build/certificate-frontier-final-tests-20260916.log`.
  The smaller initial suite had 208 passing tests; those results overlap.
- Eleven new regression cases exercise the actual transaction loop with
  renamed/translated inputs: six-pose early termination, ordinary trial limit,
  zero budget, exhausted finite menu, explicit global effort stop, and prior
  skipped poses. Native worker calls are stubbed only in these scheduling tests;
  the existing loaded-native launch/reconnect suite is included separately.
- Concurrent native proposal enumeration / zero-budget dispatch on four board
  families passes in `build/certificate-frontier-replay-v2-20260916/report.json`.
  All six source/hierarchy hashes and the engine signature remain exact; EPS
  and ATX retain their interface-ECO holds. This is **not four route runs**.
- Historical PCIe2 board SHA, complete regression and probes match exactly.
  Generalization debt remains 23 physical / 380 runtime; the entire pipeline
  remains unqualified for release.
- The first enumeration harness compared JSON lists with dataclass tuples and
  consequently did not recognize prior poses. No geometry ran in that harness.
  V2 normalizes that comparison and asserts every reused key is accounted for.
  Only V2 qualifies history reuse; the original receipt is retained.

## Bounded physical result

The additional real production transactions are:

| Receipt | New poses | Wall time | Outcome |
|---|---:|---:|---|
| `build/endpoint-launch-transaction-v3-20260916/report.json` | 6 | 25.309 s | Five exact-route refusals, one preflight DRC rejection |
| `build/endpoint-launch-transaction-v4-20260916/report.json` | 2 | 8.518 s | Two exact-route refusals |

The final transaction uses the newly corrected reporting and reports 12
generated poses, ten prior skips, two scheduled, zero unvisited. No previous
pose was rerun. Together with the prior four-pose receipt, the currently
generated single-obstruction menu has now been sampled without an accepted
move. This does **not** exhaust compound placement/copper transactions or prove
that the net has no route.

PCIe2 remains **0 DRC / 9 opens**. No PCB, power bus or canonical cohort advances;
there is no new preview to publish. No generated-locked-copper authority was
granted. Do not restart this twelve-pose single-obstruction menu unchanged.

## Suite continuation

Retain `build/priority-coopt-next-inputs-20260916.json`. Other families remain
at their independently verified prior gates: PCIe3 ten priority refusals,
Hub three craft blockers, VHP one USB priority refusal, and EPS/ATX paired
interface holds. This slice's native enumerations do not replace those full
gate reports. Current PCIe3 top/bottom body-free placement previews were
inspected again; they are still blocked placements, not new routed boards.

The next constructive work is complete-cell/multiple-obstacle repair with
verified producer ownership, or a genuinely different proposal domain. For
PCIe3, inspect the recorded finalist craft failures and coupled return repair
before spending another full priority probe budget: existing range proposals
can reduce Kelvin distance failures but fail other craft gates. Do not relax
the approved 9-mm reach, bypass full-board rechecks, move fixed power buses,
or repeat rejected single-return experiments.

No slice worker remains. Approximately 65 GiB remains free, above the 16-GiB
floor. The existing board-suite heartbeat remains active; no unchanged-board
notification or duplicate dashboard candidate is warranted.
