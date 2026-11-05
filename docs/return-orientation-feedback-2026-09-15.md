# Complete bypass-macro orientation from failed native return searches

## Prior full pass: observed, not promoted

The rigid-range PCIe3 cohort finished at 21:34:27Z on September 15. It retained
exact input `400ffdd8635e`, with 12 critical-route refusals and no main routing.
The rotated bypass now passes its local craft check, but terminal-order admission
still rejects that alternative. This is a repaired producer, not board closure.
Its verified, visually inspected BLOCKED placement review is
`pass-rigid-range-followup-suite-20260915-pcie-8pin-3port-d6332c79c9`.
Do not repeat that unchanged cohort.

## Distinct Hub cause and generic repair

Read-only native investigation found 152 structured return-search witnesses,
but no multi-reservation seam exits. The proposed overlapping-reservation-union
explanation was unsupported and no fix for it was made.

The return-feedback producer previously offered translations only. It now
accepts a bounded quarter-turn policy and rigidly transforms the IC, all its
assigned bypass capacitors, their orientations and the measured return portal.
It solves the minimum axis exit from the unchanged power reservation after
rotation, or offers rotation alone if the portal is already outside. This is
the assigned bypass macro, not a claim that every regulator circuit dependency
belongs to that macro. Capacitor-only alternatives remain translation-only.
Fixed followers, native requalification and all physical/power gates remain
binding. Owner/orientation interleaving prevents sampled near-duplicate via
exits from consuming the proposal budget before other orientations are tried.

Production dispatch supplies `(0, 90, 180, 270)` through
`local_return_rotation_degrees`; direct callers retain translation-only default
behavior. No board/refdes/coordinate special case, power-bus movement, new
manufacturing allowance, load-budget change or unlock permission was added.

## Evidence before the full pass

- `build/return-orientation-integration-tests-20260915.log`: **189 passed**,
  no skips, 94.16 s. Includes loaded front/back native pad transforms, unchanged
  bypass distance, fixed peers, bounded/fair proposal selection, production
  dispatch, full-pipeline and generalization tests.
- `build/return-orientation-suite-replay-20260915/report.json`: six explicit
  current source lineages, three native workers; all source/hierarchy/engine
  guards hold. Generality passes with zero core violations.
- Hub: same 48-proposal budget, now 34 rotated proposals, **537 native pad
  checks**, 21 courtyard-nonregressing candidates. Two collective local-cell
  probes expose different remaining failures: rotating U3 clears C2's refusal;
  rotating U7 leaves C27 and the unrelated U3/C2 refusal. Neither probe passes
  the whole board. These are search evidence, not admitted placements.
- Other admitted boards have no matching exhausted return-reservation evidence
  and therefore no new proposals. EPS/ATX still fail their interface ECO gate.
- `build/return-orientation-control-comparison-20260915.json`: protected
  historical PCIe2 PCB, full regression object and probes are unchanged; only
  generalization metadata differs. Its existing release holds remain.

## Canonical affected full pass

`build/return-orientation-followup-suite-20260915/suite.json` completed at
**22:11:38Z**, 231.44 worker seconds, with all descendants gone and source,
hierarchy and engine guards true. It used exact source `ce61d1a11de3`.

The final result is **6028ba320d41**, reducing hard placement-craft blockers
**five -> four**. U3/C2 now has a constructible local return. The production
topology adapter also carried the compact switch dependencies and legalized
two neighboring resistors; no one-off coordinates were supplied. U7's three
local return failures and C2's 0.72-mm supply-proximity excess remain. Two
accepted rounds include a small C28 distance improvement; that does not count
as another cleared blocker. No main routing started and no fab result is claimed.

Immutable review, API-verified and visually inspected:
`pass-return-orientation-followup-suite-20260915-hub-standard-rev2-c8632683d9`.
Windows preview:
`C:/Users/Admin/Documents/CEC-Board-Reviews/return-orientation-followup-suite-20260915/hub-standard-rev2/render.png`.

`build/continued-suite-inventory-20260915/report.json` independently rechecks all
six current lineages in three native workers. Its `inputs.json` preserves all
five other explicit sources and replaces only Hub with the journal-verified
6028 output. All guards hold. Hub, VHP and both PCIe boards have no native
pad/courtyard conflicts. PCIe2 remains ten opens with a passing local-cell audit;
PCIe3 local cells pass but its known critical-route hold remains. VHP retains
C7/U1.3's local-access refusal. EPS has 32 pad-short report rows; ATX has 40
pad-short plus 16 pad-clearance rows. These include repeated per-layer/pad
reports, not 32/56 distinct overlapping component pairs. Their interface ECO
holds remain mandatory. No source PCB or schematic was changed by this audit.

The one bounded follow-up is
`build/return-continuation-suite-20260915/suite.json`, explicitly continuing the
improved Hub, 24 craft trials, four workers, 1200-second board cap and 16-GiB
floor. This is justified by the cleared blocker and changed search geometry,
not by tiny distance-only movement. If hard blockers do not improve, do not
chain another identical run. Read the current journal/process state first.
PCIe2 inherited-copper ownership, VHP coupled USB escape, PCIe3 terminal order,
and EPS/ATX coupled fit remain distinct work, not reasons to rerun their
unchanged failures.
