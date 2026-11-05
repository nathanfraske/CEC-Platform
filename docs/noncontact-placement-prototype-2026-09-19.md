# Non-contact SMD placement proposal — 2026-09-19

## Status: tested materializer, experimental integration disabled

`cec_noncontact_placement` can move a detached SMD without reconstructing,
stripping, qualifying or acquiring ownership of unrelated routed copper.
This addresses a different operation from the existing routed-prefix
rehydrator, which rightly refuses copper outside its reconstruction contract.
The new path is **not enabled by default**. Craft integration requires the
explicit `placement_noncontact_resume` experiment parameter; no board policy
sets it. The original ownership refusal remains in force for normal runs.

The bounded production-engine experiment admitted **zero** moves. No source,
canonical candidate, schematic, route, mating geometry, dimension or budget
changed. This slice is not VHP closure, route progress or fabrication approval.
Do not rerun that unchanged experiment.

## Native proof and restrictions

- Hash-bound source and rule files; unchanged population, outline and faces.
- Only unlocked, hole-free SMD footprints without copper graphics, cutouts
  or footprint zones. Any board zone on a pad's layer conservatively refuses
  motion, even if it is distant. There is no unproved refill operation.
- Original and proposed pad contact with **any** existing track, arc, via or
  other footprint pad refuses motion, including same-net contacts. Coupled
  attached devices need a different route-owned transaction.
- The proposal is loaded and saved using native KiCad. Every existing copper
  UUID, geometry, layer, net and lock state must survive. Restoring only the
  moved poses in a diagnostic reload must reproduce the entire original
  native serialization, catching unrelated object/net/save-time changes.
- The source is never overwritten by the low-level materializer. The outer
  materialization adapter stages atomic output even when there is no qualified
  prefix. UUID normalization is skipped for this exact-preservation path.
- Equivalent wrapped rotations (for example -90 and 270 degrees) compare
  equally. Native clearance and complete craft checks remain mandatory.

## Experiment and the unresolved handoff

`build/noncontact-edge-placement-20260919/report.json` records an initial
bounded 32-proposal VHP experiment. It passed the former blanket ownership
barrier without removing any copper, but accepted nothing. Of 1,822 generated
proposals, 32 were selected; 16 were geometrically legal. Only the first four
full trials ran before the bounded evaluation reserve stopped the remainder.
Three returned a wrapped-angle comparison error; that implementation defect
is now corrected and covered by native -90/270-degree tests.

The experiment also exposed an **unfinished evidence handoff**: the strict
materializer intentionally does not regenerate or copy blueprint/rail
construction reports. Its output therefore lacks required construction
evidence and must fail craft admission. Copying those reports blindly would
be unsafe. Their physical member scope, immutable native copper and member
poses must be proved before a source-bound report can be carried/rebound.
This is why automatic fallback was disabled again after the experiment.

The private launcher's scratch path also lacked explicit thermal/current
policy identity. Its full measurement reported unresolved current-input
topology even on the unchanged baseline. Read-only measurement on the actual
canonical path resolves **all six** filtered input chains, including the
renamed fan-rail anchor. Evidence:
`build/pad-edge-placement-20260919/attachment-study.json`. Do not claim that
harness-only result as a new six-channel physical board defect, infer policy
from a scratch basename, or change approved current numbers to clear it.

That study also confirms the two edge-failing packages have no existing
track/via attachments. This alone is not placement admission or proof of
zone, neighboring-pad, decoupler and mechanical safety.

## Validation and next bounded slice

- **358 focused tests pass**:
  `build/noncontact-placement-tests-final-20260919.xml`.
- **25 native/protocol tests pass** after tightening the peer-pad test to
  distinguish new contact from existing attachment:
  `build/noncontact-native-tests-final-20260919.xml`.
- `build/noncontact-placement-final-suite-20260919/report.json`: all six
  source/hierarchy signatures unchanged, native geometry results identical,
  historical PCIe2 board hash/regression/probes identical. This is a
  regression replay, not six successful placement repairs.
- Generic-core audit passes, including the new module. Wider release debt
  remains. `git diff --check` passes.

Next: qualify scoped construction-evidence retention, bind the authoritative
board policy explicitly in the experiment, and preflight cheap native edge
improvement before expensive craft trials. The selected short translations
also need review against the actual clearance deficit; a broad repeated wave
is not the next step. Keep the experimental flag off until this handoff and
the full independent saved-board checks are proved.

An early unit-test-only use of KiCad `Format()` lacked an output formatter and
crashed that disposable test process. It was replaced with the existing
direct native serializer route. Core dumps were disabled; no source board or
production worker was involved. All final tests and workers finished.
