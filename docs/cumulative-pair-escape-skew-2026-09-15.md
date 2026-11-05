# Cumulative local pair-escape objective — 2026-09-15

## Measured defect and generic repair

The owned-anchor diagnostic constructed two CAN_INT tree edges, but their
individually acceptable positive P-minus-N differences compounded to
4.450497 mm, exceeding the existing 4.0-mm whole-pair limit. The local joint
escape scorer considered only the new edge, not copper already constructed.

`cec_precision_route._route_paired_stub` now measures existing native straight
copper using the shared signoff length convention and passes the **signed**
difference into the bounded joint escape objective. The scorer ranks the
projected cumulative difference. Opposite-sign differences can compensate;
same-sign differences cannot silently restart the skew budget at every leg.
Diagnostics retain the incoming signed mismatch and selected projected skew.

This applies to joint detour escapes, with a default-zero parameter for other
callers. It is not complete global path-length optimization: fast direct and
ribbon choices are unchanged. The scoring term is soft; intermediate prefixes
are not given a new hard rejection rule. Existing normalized native whole-pair
skew, coupling, detour, DRC, placement and preserved-copper checks remain
mandatory. No board/refdes/coordinate exception, limit relaxation, source ECO,
power-bus change or added production tuning meander is involved.

## Native retained-input A/B evidence

Input comes from the recorded trial, not modification time:
`build/owned-anchor-context-replay-20260915/operation-priority-power-replan-sx4ga8_q/candidate/priority-dependency-01-input/trial-01.kicad_pcb`.
The replay verifies original source SHA, all footprint poses after the exact
journaled trial, and retained copper against a freshly derived release plan.
This is a disposable diagnostic, not a promoted production placement.

| Measurement | Before | Cumulative objective |
| --- | ---: | ---: |
| Constructed tree edges | 2/2 | 2/2 |
| P copper length | 10.817413 mm | 10.817413 mm |
| N copper length | 6.366916 mm | 6.941279 mm |
| Whole-pair mismatch | 4.450497 mm, fail | 3.876134 mm, pass |
| Skew limit | 4.0 mm | 4.0 mm |
| Pair/board qualification | rejected | rejected |

`build/cumulative-escape-skew-replay-20260915-b/replay.json` completed in
16.243 s. All six source/hierarchy signatures, diagnostic artifact family and
shared engine signature remained unchanged during execution. Its `result.json`
contains independent geometry/detour/skew passes and the next refusal:
33.3% coupled coverage against the existing 60% floor, with 7.211608 mm
uncoupled length against the existing 2.0-mm absolute allowance. No route was
admitted. The 0.574363-mm skew reduction does not mean board closure.

## Next cause established before another scoring change

`build/local-pair-domain-audit-20260915-c/` passively captures the actual local
candidate menus, then evaluates them **after** the native solve. It reproduces
the exact same final mismatch and coupling refusal. Total audited time was
26.993 s; source and engine signatures are unchanged. This is bounded local
domain evidence, not proof that no legal global route or placement exists.

* Penultimate final menu: 704 combinations, 322 mutually legal; best coupling
  within the skew limit was 58.333%, equal to the selected choice.
* Last final menu: 35 combinations, all mutually legal; every choice has 0%
  local coupling, including alternatives within the cumulative skew limit.

Thus a coupling weight alone cannot fix these retained menus. Next investigate
correlated member-path generation, failed ribbon/portal witnesses and shared
trunk/fanout alternatives. Preserve same-layer clearances, short escape budgets
and final coupling authority. Do not relabel separated traces as a pair.

Failed diagnostic attempts are retained: the first skew harness compared
five-value footprint records with three-value poses and stopped before work;
the first domain audit mishandled an optional skew limit; its second attempted
enumeration inside a local search deadline and was rejected. The final harness
normalizes poses and defers enumeration until after routing. None of these
harness failures is a native-route result or authorized a source modification.

## Tests and cross-board control

* `build/cumulative-escape-skew-integrated-tests-20260915.log`: **269 passed,
  18 subtests**, one existing warning. Exhaustive argmin parity across rotations,
  both mismatch signs, shuffled menus and limits; compensation and nonfinite
  rejection; native multilayer existing-copper handoff; frozen-copper,
  dependency reconstruction, probe cohorts and prefix regressions.
* `build/cumulative-escape-skew-control-20260915.json`: historical PCIe2 SHA,
  board regression and every probe exactly equal the preceding
  `owned-anchor-context-control-20260915.json`. Its pre-existing stricter
  release failures remain; unchanged is not a new fab signoff.
* `build/cumulative-escape-skew-native-audit-20260915.json`: all **six** selected
  board roots and hierarchies unchanged; native signed-copper measurements
  finite for **16** derived pairs. Compatibility evidence, not qualification.

## Completed cohort and follow-up

`build/owned-anchor-suite-20260915/suite.json` finished at
2026-09-15T04:49:02Z. Hub: 684.687 s; 12VHPWR: 1094.163 s. Neither output was
admitted or changed from its source. Both engine/source guards passed.
Hub's two physically valid power proposals each constructed only 1/6 CAN tree
edges before search-budget exhaustion. 12VHPWR reproduced the owned-pair
reconstruction blocker. Failure is not evidence of geometric infeasibility.

The final immutable gallery is
`C:/Users/Admin/Documents/CEC-Board-Reviews/owned-anchor-suite-20260915/all-boards-7e0e740d27fd4953.png`.
It was visually inspected; these are unchanged BLOCKED placements, not new
routed boards. Dashboard HTTP returned 200 on Windows this continuation.

The live canonical cohort is `build/cumulative-escape-suite-20260915/suite.json`,
started 2026-09-15T05:06:01Z. Coordinator PID 3261625 and board PIDs
3261629 / 3261630 / 3261631 were verified running. It is
using the exact inputs from `build/parallel-suite-inputs-20260914.json` for
Hub, 12VHPWR and PCIe3 concurrently. Check journal and live processes before
any dispatch or shared engine edit. Three jobs, two workers per board,
1200-s priority operation limits, 1800-s board deadlines, 16-GiB free-space
floor; about 70 GiB currently free. Immutable previews publish per completed
pass to the dashboard and Windows `CEC-Board-Reviews/cumulative-escape-suite-20260915`.

PCIe2's latest partial route remains 0 DRC / 12 opens and is not rerun for an
unchanged unrelated blocker. EPS/ATX still require a coupled qualified mating
ECO before routing; existing dimensions, edge-span limits and land geometry
remain protected. No six-board closure claim is made.
