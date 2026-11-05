# Retained-copper support before menu truncation — 2026-09-15

## Completed evidence, no new admitted board

The octilinear PCIe3 cohort finished at 2026-09-15T05:44:52Z in 234.228 s.
Its output is identical to the input; source/hierarchy and engine guards pass.
The two power-handoff proposals still fail physical checks. Its verified
body-free preview is
`C:/Users/Admin/Documents/CEC-Board-Reviews/octilinear-ribbon-suite-20260915/all-boards-5115ca9123c71710.png`.
It was visually inspected as a BLOCKED placement, not a routed/fab board.

`build/link-support-replay-20260915/` also completed, changed=false, with all
source/engine guards unchanged. Both extra link placements pass physical and
post-authority physical checks and connect 2/2 tree edges, but final coupling
rejects them at 31.2% and 31.1% against 60%. Their skew is within the unchanged
4.0-mm limit. These results establish physically usable alternatives below
the old beam cutoff; they do NOT establish route/fab readiness or justify
waiving coupling. No result is promoted.

## Generic implemented change

The old producer sorted joint placement choices by distance and kept 32
before the retained-copper gate. On the recorded native menu, 30 of those 32
could not satisfy that necessary screen. Eight more screened offers existed
below the cutoff, hidden from the consumer even though two tested examples
passed full physical checks.

`cec_supported_candidates.select_ranked` is a reusable bounded ordered selector:
apply a necessary-condition predicate before keeping the supported prefix.
It retains objective order, separate selection/check limits and diagnostics;
predicate exceptions and truthy error objects fail closed. An exhausted check
budget is explicitly inconclusive, not proof that nothing fits. With no
predicate, historical prefix semantics are unchanged. It grants no admission.

`cec_priority_dependency.placement_support_predicate` binds actual frozen
copper and caches only private retained contexts. A proposal must either
preserve everything normally, or qualify for the existing scoped signal-pair
replacement and clear all remaining power/other-pair/return copper. No relaxed
contract is returned to the producer; normal ownership, reconstruction and
physical checks still run later.

The source-owned two-link route-feedback producer is the first consumer.
Its joint menu remains capped at 32, with at most 256 necessary-condition
checks (`placement_retained_support_checks`). The earlier per-member domain
limits are unchanged. The ordinary frozen screen, two-offer handoff budget,
native route reconstruction, final physical authority and quality key remain
unchanged. There are no board/refdes/coordinate exceptions, board-size changes
or hand-positioned components. Other callers retain their old behavior unless
they supply the predicate explicitly.

The production journal now retains `parallel_link_retained_support` per-group
counts, check/selection limits, and stop reason. The new producer screen is
not a replacement for full route or placement admission.

## Regression and native replay

* `build/supported-menu-integrated-tests-20260915.log`: **352 passed,
  18 subtests**, one existing KiCad SWIG warning. Includes delayed supported
  choices below a small beam, exact objective order, bounded/no-predicate/
  expired/error behavior, native-scope predicate wiring, two-link selection
  before a single-slot cap, existing frozen ownership, pair geometry and
  reconstruction/probe/prefix tests.
* `build/supported-menu-control-20260915.json`: historical PCIe2 board SHA,
  regression and all probes exactly equal the octilinear-ribbon control.
  Pre-existing strict release failures are unchanged, not newly qualified.
* `build/supported-menu-native-audit-20260915-b.json`: all six source families
  unchanged, engine unchanged; **26 power anchors remain immovable**.
  On VHP, 333 joint choices exist; the bounded selector checks 256, rejects
  246 and retains **10 instead of 2**. This exactly matches the independent
  earlier native-screened prefix. The unfiltered first-32 menu has exactly
  identical placement tuples. Check-limit exhaustion is recorded; the
  remaining 77 candidates are not claimed exhausted or infeasible.

The ATX root's existing Edge.Cuts do not form a valid closed outline, so its
placement-menu replay is explicitly unavailable; its source and retained-
copper checks still run. No footprint-derived rectangle or invented outline
was substituted. EPS/ATX remain blocked pending the coupled mating ECO.
The first audit attempt stopped at that existing outline error; the final
audit records it explicitly instead of treating it as a successful menu test.

The six-board replay finds this particular source-owned group in VHP only.
This is a generic topology rule, not a claim that every feature applies to
every board. The separate selector and retained-copper predicate are reusable
by other bounded placement producers. No cross-board closure gain is claimed.

## Current follow-up and next work

Canonical producer-to-handoff validation:
`build/supported-menu-suite-20260915/suite.json`, started at
2026-09-15T06:09:17Z; coordinator PID 3294635 and board PID 3294637 were
verified live. It is an exact VHP continuation from
`build/parallel-suite-inputs-20260914.json`, one job / two workers, original
1200-s priority and 1800-s board deadlines, 16-GiB free-space floor. Immutable
pass previews publish to the dashboard and Windows
`CEC-Board-Reviews/supported-menu-suite-20260915`. Check the journal and live
processes before dispatching or editing shared scripts. Do not duplicate it.

The octilinear PCIe3 cohort, extra-link diagnostic and supported native audit
are complete. Hub/PCIe3 have no applicable two-link group and their unchanged
full waves are not repeated for this selector slice. PCIe2 remains the
protected historical control and latest partial 0 DRC / 12 opens. EPS/ATX
dimensions, edge spans and qualified lands remain fixed pending paired
mechanical work. All current load budgets and power buses are preserved.

Next route issue remains coupled-path construction/quality propagation:
physical link placements can connect both members, yet the local tree accepts
separated branches and final coupling rejects the transaction. Inspect why
the local success prevents or exhausts the shared-corridor alternatives;
do not merely increase waves or weaken final coverage.
