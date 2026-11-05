# Placement certificate parity and bounded local-search work

Continuation of `sampled-return-seats-and-consumer-ownership-2026-09-15.md`.
This is a generic solver/evidence repair, not a new routing or fab claim.

## Completed follow-up, not an active campaign

`build/return-seat-feedback-suite-20260915/suite.json` finished at
**12:24:02Z**. Both boards retained unchanged source/hierarchy/engine signatures.
Hub took 188.07 s and retained its input: two proposed craft improvements were
rolled back by the frozen-power dependency guard. PCIe3 took 63.83 s and stopped
on worker/final-certificate score disagreement. Neither produced an admitted
new placement. Do not relaunch these unchanged jobs or present their seed
checkpoint previews as new geometry.

## Reproduced cause

`build/craft-identity-reproduction-20260915/suite.json` reproduced the same
PCIe3 exception in one bounded instrumented attempt, finished **12:53:15Z**.
Its evidence now survives temporary-directory cleanup:
`build/placement-certificate-failures/failure-00/manifest.json`.
The complete bundle retains **1,975,997 bytes** of exact inputs, both
certificates and the candidate pose. Source inputs and the engine were unchanged.

The expected and actual PCB bytes match. The sole project-file difference is
`.meta.filename` for the two temporary stems; rules and power-state bytes
match. The worker proves C12/U12's supply access; the coordinator refuses the
same connection because its **0.75 s** local search expires at **0.763749 s**.
This is a scheduling-sensitive search cutoff, not a changed placement or a
proved impossible path. Component names identify this reproduction only;
there is no component selector in the repair.

The separate read-only `build/craft-parity-forensic-20260915/report.json`
evaluated all six current family inputs and the isolated positive PCIe3 trial
with uncached false/true/false diagnostic modes. Five families agreed; both
PCIe3 artifacts varied despite identical input identities. All PCB sources
and engine files were unchanged. This independently rules out a changed
input as the explanation for that repeated-board score variation.

## Generic changes

1. `cec_placement_evidence_identity` fingerprints PCB, project/rules, cell and
   rail reports, pour state/plan/skeleton, file-backed config and scoped CEC
   environment. Environment values are hashed, not dumped. Mid-measurement
   input changes fail closed and are never cached.
2. A craft certification disagreement retains both exact available artifact
   families and certificates before raising. Immutable claimed slots cap
   retention at 16 bundles, each with a 64-MiB copied-input ceiling. No old
   evidence is silently evicted; quota/changed-input failures are explicit.
   A failed certificate still cannot publish a placement winner.
3. `cec_search_budget` provides scoped, nested deterministic work accounting.
   Candidate/queue-expansion checkpoints share the same work allowance through
   local canonical paths, planar/multilayer mazes, POFV and ordinary via seats.
   Other router callers retain their existing deadline behavior outside a
   scoped work budget.
4. The local supply constructor and placement oracle share a default **4096
   search-checkpoint** limit and separate **10 s** emergency wall guard, both
   API parameters. Exhaustion records work used and reason and explicitly
   does not prove no path. No electrical dimension, clearance, allowed layer,
   locality bound, protected power ownership or fabrication check is relaxed.

The cache gap was real but is **not** claimed as the cause of this captured
failure. Likewise, finite search exhaustion is not an exhaustive geometric
impossibility proof. Work budgets still need runtime tuning on larger boards.

## Final-code validation

Before the work-budget change, focused evidence/craft tests passed 246 tests
and integration/native tests passed 210; these overlap and are not additive.
The protected archived PCIe2 SHA, full board-regression object and all probes
were unchanged; only the generalization inventory changed. Its prior strict
release failures remain. These are not final validation of the later budget
change.

Completed final-code checks:

- `build/search-budget-integration-20260915.log`: **434 passed, 89.58 s**.
- `build/search-budget-routing-tests-20260915.log`: **106 passed**, plus eight
  subtests, 4.44 s. These two file selections are disjoint.
- `build/search-budget-parity-20260915/report.json`: all six current family
  artifacts plus the isolated PCIe3 candidate have identical uncached
  fast/full/fast keys; all PCB sources and the engine remain unchanged.
  PCIe3's retained source is consistently at two local-access failures and
  the isolated improved candidate at one. This proves scoring parity for the
  replay, not full placement/routing admission of the isolated candidate.
- `build/search-budget-control-comparison-20260915.json`: protected PCIe2
  SHA, complete board-regression object and all audit probes exactly match
  the prior control. Only the generalization inventory differs. Archived
  0 DRC / 0 opens / 615 tracks / 226 vias remain intact; strict release holds
  still stand.
- `build/search-budget-generality-20260915.json`: **70 core modules, zero core
  violations**, with **380 broader runtime findings** still outstanding.
  This is not a claim that the whole integration layer is generic or finished.

## Bounded affected-family follow-up

Harness `tmp/search_budget_followup_20260915.py` checks the completed tests,
seven-artifact parity proof, protected control and all six source signatures
before dispatch. Output: `build/search-budget-followup-suite-20260915/suite.json`.
It runs Hub and PCIe3 concurrently, two workers each, 12 trials/two craft
rounds, eight routing passes if admission succeeds, a 600-s per-board budget,
120-s priority allowance and 16-GiB free floor. No diagnostic PCB is seeded.
Check the live journal/processes before editing engines or launching anything
else. Completed pass previews publish automatically; a blocked seed is labeled
as such, never advertised as a new routed candidate.

Dispatched **13:02:44Z**, Hub PID **221140**, PCIe3 PID **221139**, parent
session **86559**. Both passed source intake and entered their first bounded
craft generation. These are live launch observations, not completion claims.

**Completed 13:06:09Z.** PCIe3 retained a full craft repair, two local-access
failures to one, while Hub rolled two incompatible proposals back. See
`frozen-placement-search-domain-2026-09-15.md` for results, verified reviews
and the next generic search-domain slice. The launch paragraph is historical.

## Suite state preserved

- PCIe2: retained partial routed incumbent, previously 0 DRC / 12 opens;
  no new routing run or release claim in this slice.
- PCIe3: instrumented certification failure, pending fixed-engine replay.
- Hub: frozen-power consumer/return placement holds remain; no accepted move.
- 12VHPWR: latest verified placement retained; USB corridor/local-access
  obligations remain. No old-board substitution or unchanged long rerun.
- EPS and ATX: coupled terminal/mating geometry still lacks a qualified fix
  within the locked spans; ATX also lacks required source power authority.
  They must not enter routing by ignoring those gates.
