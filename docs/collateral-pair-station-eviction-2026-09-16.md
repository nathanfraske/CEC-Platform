# Complete pair stations during collateral placement eviction

## Root cause and generic change

A whole regulator/capacitor cell could clear a power-dependent return obstruction
by evicting one passive into a vacated seat. The local craft admission passed,
but the eviction split a differential endpoint across two independently moved
packages. The downstream important-route gate caught the consequence; the local
repair generator did not preserve the endpoint it was disturbing.

`cec_placement_station_groups` now obtains physical endpoint membership from the
same live-board derivation as the precision router. Overlapping memberships are
closed transitively and deterministically. At the craft variant boundary, a
secondary translation includes the complete station, preserving all relative
positions and orientations. Unavailable ownership, missing members, fixed members
or conflicting transforms reject the collateral variant. No board, refdes, net
or target coordinate is encoded in this new rule.

This applies after both one-passive and bounded macro legalization and before
the existing fixed-authority, overlap, bounds, copper, native-pad and electrical
admission checks. It does not unlock copper or replace those gates. Intentional
primary station re-seating remains the primary solver's responsibility; this is
not a claim that all primary placement search is now globally route-aware.
Each round records the source board hash, derived groups, expanded variants and
refusals. The source authority is read from that round's materialized incumbent,
not an earlier candidate or a guessed package pairing.

## Validation

`build/station-eviction-tests-v2-20260916.log`: **256 tests pass**, including
renamed synthetic members, rotations, locked/missing members, conflicting
transforms, transitive groups, primary intent preservation, native front/back
footprints, existing craft admission and pair semantics. The first test run had
two fixture failures from an incorrect KiCad layer-set constructor; those were
corrected in the test, without changing production behavior.

The expanded full-pipeline, frozen-placement, native-cell, protected-prefix and
search-policy regression run has **444 passing tests**, one existing KiCad SWIG
deprecation warning, 130.07 seconds. Log:
`build/station-eviction-combined-tests-20260916.log`.

Four board families replayed concurrently with identical complete physical
reports. The Hub, PCIe2, PCIe3 and 12VHPWR each expose a live split station and
pass propagation plus locked-member negative controls. EPS/ATX remain held by
their unadmitted mating-interface ECOs; they are not counted as routed or as
passing the physical replay. All six source/hierarchy identities are unchanged.
Evidence: `build/station-eviction-replay-20260916/report.json`.

The retained PCIe3 counterfactual expands 13 collateral variants, evaluates 15
legal variants and accepts one repair. Both resistors in the split station move
together. Local craft is clean after a fresh power rebuild, but independent
priority qualification still has **11 failures**. CAN_H still has detour ratio
2.176366 against the unchanged 2.0 limit; preserving station geometry alone does
not choose a good global seat. **No diagnostic is promoted.**

Evidence:

- `build/station-eviction-cell-screen-20260916/report.json`
- `build/station-eviction-priority-check-20260916/report.json`
- `build/station-eviction-qualified-comparison-20260916.json`

The immutable PCIe2 control retains identical complete probe and regression
reports, including 0 DRC / 0 opens and its pre-existing broader release holds.
Generalization verdicts/findings are unchanged; its checked-module inventory now
also includes the new shared helper. This is regression parity, not fabrication
approval. The receipt explicitly checks that expected inventory-only difference.

## Concurrent full-pass review

The user requested all boards simultaneously. One bounded six-job campaign
tested this new engine from `build/bound-return-next-inputs-20260916.json`:
`build/station-eviction-suite-20260916`, launched by
`tmp/station_eviction_suite_20260916.py`. Each board has four craft workers,
16 trials, a 600-second priority allowance and a 1,200-second total job ceiling.
The campaign retains the 16 GiB disk floor. No unchanged automatic repeat is
authorized. All jobs completed by 10:27:07Z (17 minutes campaign wall time).

Full-pass previews were published as each job finished to the dashboard and
`C:/Users/Admin/Documents/CEC-Board-Reviews/station-eviction-suite-20260916`.
The current continuation remains unchanged: no result demonstrated an accepted
closure improvement. No load, thermal, clearance, mechanical
envelope, interface, source schematic or fabrication limit was changed.

Completed-job review:

| Board | Elapsed seconds | Result |
| --- | ---: | --- |
| EPS | 67.1 | Fixed terminal pad shorts; partial placement only. |
| ATX24 | 244.9 | Fixed terminal pad conflicts; partial placement only. |
| Hub | 221.8 | Same canonical PCB hash, three local-cell blockers retained. |
| PCIe3 | 770.0 | Same canonical PCB hash, eleven critical-route failures retained. |
| 12VHPWR | 793.0 | Same canonical PCB hash, one critical-route failure retained; local C7 return remains explicitly deferred, not solved. |
| PCIe2 | 1017.8 | Detailed routing completed; 0 DRC / 9 opens, still blocked. One more via and 2.6383 mm more copper than the incumbent; not adopted. |

All six published top views and PCIe2 bottom were inspected. No geometry was adopted from
this cohort. The earlier canonical Hub gain is already in the input plan.
Independent receipt `build/station-eviction-suite-qualified-20260916.json`
verifies journals/review hashes, all source/hierarchy and engine identities,
and PCIe2's native score, protected prefix, qualified pairs and local cells.
The final gallery is mirrored to `CEC-Board-Reviews/station-eviction-suite-20260916/all-boards.png`.
All workers/tests/diagnostics finished; about 66 GiB remains free.
The user was asked asynchronously whether the EPS/ATX fixed span should remain
the constraint for alternative terminals or whether modest paired span growth
may be investigated. No dimensional or part-selection change follows without
that decision and a complete paired fit check.

## Additional read-only investigations during the cohort

`build/route-incumbent-compare-20260916/report.json` grades the retained PCIe2
incumbent and the preceding full-pass proposal using the same real oracle with
`route=False`, identical lazy-thermal mode and copied bound sidecars. Both source
and grading-copy PCB hashes remain unchanged. Every gate term and complete
selection rank is equal. The newer proposal has 387 versus 386 vias and
1,656.95 versus 1,654.31 mm of trace, still 0 DRC / 9 opens. Inspection of
`_route_stage` confirms its ensemble selects only newly generated candidates;
it does not include the incoming routed artifact. Failed-candidate ranking also
omits these secondary copper costs. This is evidence for a future generic
incumbent-retention/tie-break repair, not permission to promote the extra copper.
No selection code was changed during the live cohort.

The short-pair detour probe in
`build/short-pair-qualification-probe-20260916/report.json` confirms a second
ordering issue: `_route_paired_stub` accepts a locally legal complete CAN pair
that fails the later 2.0 detour contract. A disposable in-process adapter applies
the existing complete-pair check before that search class returns, removes only
the rejected attempt's new copper and lets the remaining classes run. It still
has 11 critical failures: CAN exhausts clear-corridor alternatives and CAN_J1
exhausts its deadline. The probe is **not integrated** as a claimed closure fix,
and no result is promoted. Merely moving a check earlier did not solve this case;
the bounded local route/placement domain still needs a useful alternative.
