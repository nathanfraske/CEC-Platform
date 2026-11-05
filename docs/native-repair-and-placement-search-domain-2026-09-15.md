# Native repair lifetime and measured placement-search domain

## Implemented, generic and bounded

Certificate repair still had eight permanent-discard loops using native
`BOARD.Remove`, outside the earlier audited native cleanup modules. The paths
include track reroute, negotiation, target retreat, split-support swaps,
partial-pair cleanup, via relocation, footprint relocation and dangling-via
pruning. They now use the shared permanent-discard operation, detach selected
group members and capture UUIDs before invalidating native aliases. Negotiation
collects all aliases before destruction; via relocation finishes its unsupported
incident-branch screen before discarding any track. Electrical removal authority
and transactional admission were not broadened. This is a runtime reliability
fix, not permission to unlock inherited local cells.

New subprocess tests exercise real loaded-board reroute, negotiation, grouped
retreat, via relocation and grouped dangling-via cleanup repeatedly, including
normal interpreter exit and preservation of source files. The reference-count
test calibrates KiCad's separate positive per-`Add` reference retention with a
plain native add; it checks that permanent removal does not consume registry
references. It does not claim the native `Add` behavior was repaired.

A second distinct search defect was confirmed on the current PCIe3 placement:
measured Kelvin endpoint deficits reach **11.526898 mm**, but proposal generation
silently discarded every deficit above the default **6 mm** local-step cap.
The number of proposals was already bounded; that cap was not an electrical
limit. New `cec_placement_search_domain.relocation_radius` derives the maximum
translation from the candidate outline's bounding-box diagonal, with any
explicit policy cap still binding. Invalid dimensions/caps fail closed. The
existing independent outline, clearance, complete-cell, frozen-power, craft,
priority and post-power admission checks remain unchanged.

Range moves translate the complete movable follower group. A fixed follower
blocks the group. A second directional bug is fixed: axis-only proposals now
point toward the fixed peer even when the **source**, rather than destination,
endpoint is the movable one. No board/refdes/coordinate exception was added.
The tap synthesizer's existing 9-mm reach limit was not changed or presented as
a newly verified electrical standard. The counts-only final ranking is unchanged;
partial range improvement without a completed critical-route improvement is not
newly admitted.

## Validation

- `build/search-domain-integration-tests-20260915.log`: **377 passed**, 13 skipped,
  16 subtests passed, 98.53 seconds. Includes placement oracle/full pipeline,
  priority dependencies/generalization, native disposal and certificate repair.
  The narrower 150-test native run overlaps this count. Translation/rotation,
  renamed endpoints, either fixed endpoint, fixed followers, explicit caps and
  invalid dimensions are covered. The 13 skipped legacy Hub-oracle tests require
  a missing older committed-board fixture (`HUB_PCB`); they are not opt-in routed
  passes. `build/search-domain-skip-reasons-20260915.log` records the reason.
  Fresh current-lineage native replay below is separate coverage, not a claim
  that those 13 fixture-specific tests ran.
- `build/search-domain-suite-replay-v2-20260915/report.json`: three workers replay
  all six explicit source/hierarchy lineages, preserving source bytes and engine
  hashes. Four admitted boards use the actual native Kelvin producer on private
  loaded copies, then both old-cap and new-domain proposal generation. EPS/ATX
  retain the interface-ECO admission hold. Version 1 had a harness-only projection
  error (reading string `refused` labels instead of `refused_details`) and is
  superseded, not evidence of zero PCIe3 failures.
- PCIe3 has nine current native range refusals. Eligible range proposals increase
  **26 -> 52**; none moves a fixed member. These are proposals, not admitted poses
  or closed nets. Hub, VHP and PCIe2 have no Kelvin range refusals in this replay.
- `build/search-domain-control-comparison-20260915.json`: protected historical
  PCIe2 PCB, complete regression and probes unchanged; only generalization
  evidence differs. CLI exit 1 remains its existing release holds.
- Generality: 75 core modules, zero core findings. No power-budget, schematic,
  thermal, fabrication-profile, terminal geometry or bus-routing change.
- `build/certificate-native-negative-control-20260915.log`: six tests passed,
  including an isolated negative control which reinstates legacy native detach
  only in that test process and demonstrably fails the registry-balance check.
  Five tests overlap the larger run; the negative control is additional.

The optional retained-track screen in
`build/search-domain-retained-screen-v2-20260915.json` has **zero captured prefix
items** on this placement. Its 52/52 clear count is therefore vacuous, not
evidence that the moves clear the frozen power reservations. The actual full
pipeline below retains those reservation, courtyard and regenerated-authority
gates. Do not use that diagnostic as placement admission.

## Follow-up and remaining work

Affected full-pass journal: `build/search-domain-followup-suite-20260915/suite.json`.
Read its live state and process tree before editing shared engines. This pass
uses exact current PCIe3 **400ffdd8635e** with a 1200-second cap, four workers and
the normal full gate chain. Do not repeat the unchanged Hub/VHP/EPS/ATX cohorts
merely because their native replay remains held. Their prior blockers remain.

The full pass started **20:44:02Z**, coordinator child PID **449107**. Its first
16-trial screen selected pair-related poses and no Kelvin range pose. The next
round did reach three Kelvin range trials, including a newly reachable
11.23-mm translation/rotation of a complete owner/follower cell. That scoped
native probe reduced Kelvin refusals from nine to eight, but its finalist failed
craft admission; it is not an accepted board improvement. The initial operation
reports a 12 -> 11 critical-refusal pair improvement, which still requires the
independent post-power boundary before promotion. A second priority operation
is active; inspect the final journal before claiming any net/board progress.

Primary report:
`02-placement/operation-priority-repair-69me3g9w/report.json` under the full-pass
directory. Inspect completed physical screening/craft rejections before blaming
router effort. The next gap may be complete-cell orientation/localization, not
another larger radius. Do not extend this cohort or rerun it unchanged.

PCIe2 durable complete-local-cell ownership remains a separate unfinished
feature. Its current 905f board still has ten opens. Group labels and UUID
presence/absence alone do not authorize inherited local-copper rebuilding.
The native lifetime fix makes those future repair paths safer; it is not itself
closure of their ownership contract. No new fab candidate is claimed.
