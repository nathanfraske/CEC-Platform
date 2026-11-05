# Resumable finite placement search, not cached rejection

## Root cause

The craft loop already sampled less-visited proposals within one invocation.
The priority loop did not: its first non-acceptance terminated all remaining
funded rounds, and the next identical call selected the same first batch.
Neither path retained usable search ordering across pipeline continuations.
This makes a bounded sampler look like a global plateau without exhausting its
generated menu. The latest PCIe3 integration pass illustrates the distinction:
16 moves selected, four pair probes measured, five deferred, no full finalist.
That is not a no-path proof.

## Shared repair

- Priority sampling uses the existing least-visited policy, with the existing
  critical-owner/direct-physical selector applied inside each visit tier.
  Original frozen-plan filtering still precedes the expensive trial quota.
- On a measured no-gain sample, another caller-funded round may inspect
  unvisited proposals. Native failures, incomplete/deferred exact probes, an
  exhausted finite menu, and the existing round/deadline limits stop the loop.
  Acceptance remains strict whole-board monotonic improvement. History never
  excludes a proposal or supplies a physical pass/fail result.
- Both repair coordinators export validated, JSON-safe proposal counts. The
  full pipeline writes a small `*.placement-search.json` sibling containing
  separate craft/priority ordering and the pre-repair PCB SHA. Normal artifact
  copying carries it forward. A changed PCB discards old ordering. Invalid or
  unreadable optional history starts an empty search; the normal native
  loaders/physical gates remain mandatory. Failed history writes are logged.
- History is included in source provenance, but excluded from baseline route
  evidence dependencies because writing an ordering receipt does not change
  the incumbent's electrical geometry. It grants no commit, routing, release,
  or no-path authority. Rollback of geometry does not erase completed work
  accounting. A changed accepted result retains the old key intentionally,
  ensuring the next geometry gets fresh ordering.

No board names, reference designators, coordinates, fabrication limits or
electrical limits select this production behavior. No power-plan redesign or
route unlocking was added.

## Validation and bounded current-board experiment

`build/priority-frontier-final-tests-20260916.log`: **350 passed** in 104.94 s.
Coverage includes renamed/translated fixtures, strict trial/round budgets,
second-batch improvements, no-gain/incumbent preservation, incomplete probes,
deadline refusal, malformed history, byte-bound copy/resume, separate scopes,
and existing certificate, route evidence, frozen-plan, full-pipeline,
cooptimization durability and finalization regressions. The original 232-test
focused suite overlaps this result; counts must not be added.

`build/priority-frontier-suite-20260916/` is the completed concurrent native
experiment. It used the explicit six-family current continuation manifest,
does not edit sources, and compares saved power/pair prefixes after work.
PCIe2 also gets fresh final-PCB residual certificates. Four families may run
repairs; EPS and ATX retain their paired-interface holds. The historical fab
review PCIe2 control runs independently. This is not a full routing-wave claim.

Legacy Hub reports lack a complete list of the old 32 scheduled poses. Only
their actually retained best-per-family pose records can seed history; the
experiment explicitly records this partial legacy coverage. PCIe3's last
unchanged pass contains all 16 selected poses. Newly generated reports retain
complete counts, so future continuations do not need that forensic inference.

Do not advance canonical inputs or publish unchanged boards as new results.
Completed results: PCIe3 sampled 16 previously unrecorded poses (32 cumulative),
but stays at eight critical refusals. Hub sampled 32 distinct poses beyond its
13 retained legacy records, but stays at three craft blockers. VHP probed 12
pair variants and remains at one critical refusal. PCIe2's two proposed moves
were **rejected by independent saved-board qualification**: reconstruction
dropped 996 non-retained copper items and raised opens 9 -> 168. Read
[the ownership-boundary repair](placement-copper-ownership-boundary-2026-09-16.md).
Its source remains 0 DRC / nine opens. Both interface holds persist. All six
source/hierarchy signatures and the pass engine were unchanged; historical
PCIe2 control replay exactly matches. No new layout is promoted or pictured as
progress. These reports demonstrate search accounting and exposed a regression,
not board closure.
