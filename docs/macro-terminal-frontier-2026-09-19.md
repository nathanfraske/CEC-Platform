# Bounded placement search: retain the final frontier

## Outcome and scope

The shared bounded macro legalizer no longer discards a legal placement found
on its final permitted expansion. This is a search-correctness fix, not a new
board-specific placement or a relaxation of electrical admission. No canonical
board, hierarchy, power budget, outline, current-carrying pour, or release status
changed. **There is no newly admitted routing candidate in this slice.**

The concurrent six-board replay and historical PCIe2 control are recorded in
`build/macro-frontier-suite-20260919/report.json`. Continue from
`build/additive-first-next-inputs-20260917.json`, not any private diagnostic PCB.

## Root cause and repair

`cec_synth_pipeline._placement_bounded_macro_legalizations` recognized goals
only at the beginning of an iteration. The last expansion could generate a
zero-conflict state, then hit `max_steps` before recognizing it. Increasing the
budget sometimes hid the defect; it did not repair the boundary condition.

The helper now inspects the already bounded final beam, rechecking introduced
overlaps and supplied frozen-copper collisions. It performs no extra expansion,
keeps the existing variant cap and deterministic ordering, and changes no earlier
success path. A trace field, `terminal_frontier_goals`, identifies recovered goals.
The caller's exact native, frozen-power, craft and routing gates still apply.

Six new synthetic/native tests cover bounded depths 1/2/4, rigid owner/follower
translation, an immovable obstruction, and saved/reloaded front/back native pad
envelopes. Before repair, three of the six failed. After repair all six pass.
No board name, reference designator, or coordinate is used as a production case.

## Cross-board replay and limitations

PCIe3's 35 previously colliding joint-terminal proposals were subjected to a
new bounded collateral-placement domain: four steps, beam width six, at most two
variants per primary. A local counterfactual removed only the final-frontier fix
from the helper; it did not globally patch the pipeline.

| Measurement | Before | After |
|---|---:|---:|
| Geometric legalizations returned | 21 | 29 |
| Exact physical/electrical survivors | Not asserted | 0 |

Seventeen final-frontier goals were recognized across five primaries, producing
eight extra returned variants after the existing caps. These numbers are search
coverage, **not** additional connections or completed boards.

This diagnostic geometric stage did not supply frozen power envelopes to the
beam; it used the exact frozen domain immediately afterward. Of its 29 variants,
28 failed frozen-power placement admission. The remaining saved native trial
passed courtyard and mechanical checks but separated a detector comparator from
its amplifier by 8.5 mm against the existing 8 mm limit. That is the general
dependency-closure problem; do not fix it by moving one named comparator or
increasing the limit. All 29 were rejected before priority routing.

Evidence:

- `build/macro-frontier-suite-20260919/pcie-8pin-3port/trials.json`
- `build/macro-frontier-suite-20260919/pcie-8pin-3port/trial-22-0.physical.json`
- Trial SHA-256 `37af28eb4f66dd1c7f20ee423ee728c8b156a3977331623242e34953d702ee80`

The replay completed pair-station collateral groups in its harness. That is not
evidence that every production route-preflight caller now does so: craft repair
already invokes this helper, while the inspected route-preflight collateral path
does not. Full electrical dependency closure remains work to integrate and test.

Current PCIe2, Hub and 12VHPWR probes remained unchanged; the Hub still has its
two local ground-return blockers and one regulator-input proximity blocker.
EPS/ATX remain held for their coupled interface ECO. All six source/hierarchy
signatures and the historical PCIe2 control match the current receipt, including
its previously detected sideways-Kelvin defect. Core generic audit passes; the
full inventory still reports 23 physical and 380 runtime generalization issues.
These are not a clean-release claim.

## A regression-fixture failure exposed native save mutation

The broad test run initially returned 814 passes and one failure in a preexisting
frozen-via negative test. Its two deliberately overlapping, differently named
via nets could be merged by `pcbnew.SaveBoard` **before** the guard under test ran.
Asserting each net immediately before and after saving localized the mutation.

A native-only fresh-process reproduction used two overlapping 0.9 mm vias,
without a CEC routing or placement engine. Normal net-code assignment, direct
net-object assignment, explicit net codes and retained Python object lifetimes
all reproduced the merge. This is observed KiCad 10.0.5 save behavior on an
invalid synthetic short, not evidence that the current six boards were corrupted.
The winning merged net can vary, explaining why the old fixture was intermittent.

For these tests' point-in-time byte snapshots, the helper now uses
`PCB_IO_MGR.Save(KICAD_SEXP, ...)`, which bypasses the convenience save's
connectivity rebuild. It asserts UUID-to-net bindings are unchanged. The native
serializer retained both nets in 500 fresh fixtures. Both actual overlap and a
separate non-touching clearance violation are covered; no guard was weakened.
Production serialization was not replaced in this slice.

Evidence:

- `build/frozen-via-fixture-stress-20260919.json`
- `build/native-save-net-{default,object,explicit,hold,raw}-20260919.json`
- `build/macro-frontier-frozen-fixture-tests-20260919.log`: 20 pass
- `build/macro-frontier-wide-tests-v3-20260919.log`: **817 pass, two subtests pass**
  in 62.15 seconds; only the existing KiCad SWIG deprecation warning

The first two broad failures and the net-binding localization run are retained,
not overwritten. A future shared native-I/O integrity boundary should compare
intended connectivity before and after normalization; do not globally substitute
a low-level serializer without qualifying legitimate connectivity rebuilds.

## Next bounded slice

1. Put fixed power envelopes and complete electrically coupled collateral groups
   into candidate generation, then retain exact downstream admission. Include
   detector/amplifier relationships, bypass ownership, and paired stations.
2. Integrate the same collateral contract into the relevant craft and route
   feedback callers; test synthetic cases and all six boards plus the immutable
   historical PCIe2 control. Preserve intentional primary transformations.
3. Continue changed Hub local-return and 12VHPWR USB-escape geometry domains in
   parallel. Do not replay the exhausted 35-proposal collateral domain unchanged,
   erase Hub's 125-pose history, or bypass the EPS/ATX interface hold.

No new image was published because no candidate passed admission. The dashboard
must not substitute this rejected diagnostic board for a routed winner.
