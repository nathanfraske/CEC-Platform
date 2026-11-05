# Bounded power-replan handoff and retained failure stack — 2026-09-15

## Completed producer result

`build/probe-scope-suite-20260915/suite.json` completed in 350.461 s on the
explicit PCIe3 source. It admitted no new placement. The corrected partial
probe accounting reduced early claimed improvements from eight to one and
avoided the previously losing full finalist. Four pair probes ran; three
further proposals were deferred by conservative complete-probe budgeting,
not proven infeasible. The source PCB, hierarchy and engine were unchanged.

The useful Kelvin move reached the power-replan handoff, but the outer
co-optimization journal discarded its detailed trial failures. This made the
next decision depend on repeating a native operation instead of reading its
evidence. The source is still SHA256
`d97d5dbc933676665f43fdf141f8239d8035fb4c35838b6817cf5cc0de42c6ee`.

## Shared repair

- Power replanning now uses the same isolated, supervised operation boundary
  as other priority placement work. It has a configurable timeout, clamped
  by enclosing operation/campaign deadlines, with durable progress and logs.
- A private board/artifact family is the worker input. Promotion requires an
  accepted result and unchanged original PCB, project, rules and power-family
  hashes. A concurrent rule edit is preserved and prevents promotion.
- The worker dispatches directly to the in-process implementation rather
  than recursively launching itself. Already-isolated terminal recovery also
  uses this direct implementation.
- Every trial retains its reason, timing and full report. The outer summary
  retains a durable report pointer. Fully measured candidates also preserve
  both ordered keys, the decisive field and up to two exact diagnostic bundles
  (64 MiB per bundle, at least 16 GiB free). These artifacts confer no release
  or promotion authority.

No placement coordinates, power budgets, rail widths, routing limits or
acceptance keys were changed by this slice. It applies to the shared producer,
not a PCIe-specific selector.

## Tests and protected control

`build/power-replan-isolation-integrated-tests-20260915.log`: **213 passed,
15 subtests passed**, 68.34 s. The smaller preceding set had 148 passed;
the counts overlap and must not be added. Coverage includes worker dispatch,
private staging, configurable budget, full-family drift, rejected/accepted
promotion, report persistence, full-pipeline and priority-dependency paths,
finalist attribution, pair scopes, local PI, budget and genericity checks.

`build/power-replan-isolation-control-20260915.json` matches the prior
`probe-scope-control-20260915.json` exactly for the protected PCIe2 SHA,
board regression and all four probes. Its pre-existing release, pair, craft
and fabrication failures remain; unchanged evidence is not present-day fab
qualification. All six input/hierarchy hashes stayed unchanged in the native
handoff replay. `git diff --check` passed.

## Native handoff replay

`build/power-replan-isolation-replay-20260915/` completed in **99.385 s** under
a 600-second diagnostic cap. Operation `operation-priority-power-replan-1wam9004`
evaluated two proposals, retained one full finalist and accepted neither.

1. **Kelvin cell range closure:** pads, courtyards and constraints passed.
   Craft refused only `power_body_clearance`. No actual body/terminal/decoupler
   collision was reported; `/SENSEC1_HI`'s derived corridor failed, and the
   placement preflight deliberately substituted a non-solving fallback with
   reason `placement body preflight requires exact territory`. This alone
   does not prove the full exact-power compiler can or cannot realize it.
2. **Pair endpoint owner-cell reseat:** exact power and post-power physical
   checks passed. Critical refusals stayed 11 and remaining pair edges stayed
   one. The first decisive ranking field was reservation crossings **49 to
   50**, correctly rejecting the candidate despite some later improvements
   (overflow 193992 to 187487; expected vias 137 to 129). A different earlier
   finalist was rejected by critical refusals 11 to 12; these are distinct
   trials, not contradictory explanations of the same failure.

The second exact candidate SHA is
`8309a43ea761d88198ae84384ba54496382f684d07b6df4853476a42a2464ebe`.
Its 1,312,140-byte baseline/candidate bundle is under the operation's
`candidate/power-replan-finalists/finalist-8miqfkm7/`, with `receipt.json` and
`evidence.json`. None of this diagnostic geometry replaced a review candidate.

## Exact-power diagnostic and next decision

`build/exact-territory-probe-20260915/probe.json` is a disposable full-authority
probe of the first proposal, not a production gate waiver. The outer deadline
is 600 seconds; the authority operation requested 1800 but received only
583.797 seconds after the enclosing reserve. It **exhausted that budget** in
583.931 s. The preserved native stack was in `_repair_parallel_pour_placement`,
enumerating alternate exact Manhattan corridors; it did not complete power
authority or reach the post-physical/priority checks. All sources and engine
hashes stayed unchanged, and the owned process exited. This is inconclusive,
not an impossibility proof. Full authority must succeed, then
post-power physical and complete priority checks must pass before any future
transaction can consider promotion. Until proved, do not turn the preflight
message into permission to bypass the gate.

## Suite disposition

The dashboard returned HTTP 200 from Windows this continuation. The immutable
[PCIe3 placement review](http://localhost:8090/?id=pass-probe-scope-suite-20260915-pcie-8pin-3port-1f617a7b63)
still shows the unchanged, blocked placement; it is not a new routed board.

PCIe2's latest partial continuation remains 0 DRC / 12 opens. Hub remains at
committed-power pair reconstruction; 12VHPWR retains CAN-search and USB
flow-through blockers. Their unchanged exhausted full campaigns were not
duplicated for this observability/isolation slice. EPS and ATX remain blocked
by actual fixed terminal-pad conflicts and a coupled mating ECO. The user was
asked whether wider interfaces may be evaluated jointly; pending an answer,
the current span/dimension constraints remain binding. No mating half was
independently moved and no terminal land was shrunk.

Next useful work is to distinguish incomplete power-preflight analysis from
an exact realization failure. The next shared slice schedules still-unmeasured
pair proposals using actual unused time within the original fixed probe share;
see [bounded cohort refills](probe-cohort-refill-2026-09-15.md). A budget-deferred
proposal is not evidence of infeasibility or a reason for an unlimited retry loop.
