# Shared pair junctions and foreign-clearance contract

## Root causes and changes

1. A native multidrop branch created another filled/capped signal via at a
   shared endpoint already used by the backbone. Same-net copper exemption
   allowed duplicate drilling. The endpoint solver now resolves exactly one
   same-net barrel with the required real layer span and independently legal
   ordinary or contained-POFV dimensions. Existing vias stay outside rollback.
   Reused transitions still require reference-return qualification.

2. The generic new-via guard now rejects occupied origins and insufficient
   finished-hole spacing even on the same net. In-place geometry normalization
   must identify the exact existing via UUID, position and net; that exception
   cannot excuse a second barrel or a missing/mismatched object.

3. Pair helper defaults could undercut a declared pair clearance. All entry
   points now resolve the maximum of the declaration, explicit request and
   board floor. The two observed native violations had an additional cause:
   CAN's own clearance was 0.20 mm, but adjacent Power12V-class copper required
   0.25 mm. Both direct and indexed generic collision checks now consume the
   obstacle's clearance too. The spatial query inflates by the largest stored
   clearance; the exact predicate then applies each object's own value.

   The exact sibling project provides an independent floor alongside native
   KiCad class/local clearance. This matters when pcbnew retains earlier/default
   project settings in a long-lived process. Parsed projects have a bounded
   path/stat-keyed cache; changed or invalid project authority cannot silently
   reuse the previous result. Invalid authority fails before the shape loop.

4. Native-tree completion now checks accumulated copper skew before selecting
   the tree, allowing the next bounded edge order/topology to run on failure.
   The existing final independent skew check remains. Native bounded terminal
   drops now share the layered solver's explicit fanout policy, but only when
   **each member's actual newly routed copper** fits the declared length bound.
   The airline length alone is insufficient. Whole-pair coupling, connectivity,
   return, detour, clearance and saved-artifact admission remain mandatory.

No board IDs, reference designators or coordinate exceptions are used in these
changes. No current budget, fabrication dimension, clearance, board outline,
mating-width limit or whole-pair electrical limit was relaxed.

## Causal evidence (not board promotion)

The historical failed CAN candidate remains immutable. On a disposable copy,
removing just its two exactly duplicated barrels changed structural DRC from
15 to 5 with 220 opens unchanged. The remaining findings were three inherited
copper-edge violations and two new clearances. The eight via-diameter/annulus
messages were caused by ambiguous duplicate geometry defeating exact POFV
qualification, not proof that the board's selected POFV process was unavailable.
This copy still violates whole-pair skew and is not an admitted route.

Evidence: `build/pair-junction-ablation-20260913/report.json`.

The two native clearance witnesses have actual gaps 0.205 and 0.245 mm against
0.250 mm required. Replaying the old shape predicate accepts both. The corrected
direct/indexed predicates reject both without modifying the source artifact.
Evidence: `build/pair-junction-clearance-witnesses-20260913.json`.

An intermediate 12VHPWR production recovery completed one critical-only backend
wave (40.767 s), retaining its incoming prefix and source/engine identity. CAN
and USB did not close. This was before the final obstacle-clearance correction;
it is not evidence of final-engine closure. Evidence:
`build/pair-junction-recovery-20260913/12vhpwr/recovery.json`.

## Regression scope

Native/synthetic tests cover exact identity, same-net duplicate and near-hole
rejection, foreign/malformed/insufficient-span barrels, shared-junction reuse,
rollback, caller-clearance floors, foreign pad/track/via clearance with and
without spatial indexing, changed project authority, accumulated skew retry,
and actual-copper fanout bounds. The via-normalization positive test now uses
enough space for legal widening; its previous 0.33 mm pitch left only 0.08 mm
clearance after growth. A separate negative test requires refusal at that pitch.

Final native trials, protected-control comparison and broad regression results
are recorded below after completion. No residual-routing or fab admission is
implied by a successful unit test or a connected diagnostic pair.

## Final native trials

Both completed recoveries used unchanged input/source/engine identities, one
critical-only backend wave, and bounded constructive pair searches. Both kept
placement and the protected incoming copper prefix intact. Neither admitted a
new complete pair or entered residual/general routing.

| Board | Native saved result | Interpretation |
| --- | --- | --- |
| 12VHPWR | 224 opens, 3 inherited DRC findings, unchanged PCB hash | No additional routing closure. External CAN native/backbone and layered junction search still refuses; USB flow-through escape remains incomplete. |
| Hub | 281 to 254 raw opens, zero DRC | **Refill only, not routing improvement.** No new tracks/vias. CAN trunk and USB physical-pad ownership remain incomplete. |

The backend-wave portions took 40.516 s (12VHPWR) and 28.486 s (Hub), excluding
their preceding constructive searches and verification. These times must not
be presented as whole-recovery runtimes. Evidence:
`build/pair-junction-final-recovery-20260913/{12vhpwr,hub}/recovery.json`.

The Hub refill-only control produces **exactly the same PCB bytes** as its wave
output (SHA256 `0219d3c1e8325999cfc73d8c2330bdae844f24406501bf22aa087142ab58746c`).
It removes no geometry and creates no tracks/vias. An intermediate progress
update reported the raw 27-open reduction; the causal control corrected that
interpretation before promotion. This is not evidence of improved routing.

`cec_route_progress` is the fifth generic repair: every future critical recovery
creates a disposable refill control and reports raw versus refill-adjusted
connectivity changes, added/removed copper items, and qualified routing credit.
An open-count reduction caused solely by fill cannot receive routing credit.
This reporting-only addition was integrated **after** the two native trials;
its production control/comparison functions were replayed on both saved trials,
not claimed to have run inside those earlier jobs. The replay independently
finds zero added/removed tracks/vias and zero qualified routing progress for both.
Evidence: `build/pair-junction-progress-replay-20260913/report.json` and
`build/pair-junction-hub-refill-control-20260913/report.json`.
The final replay distinguishes an already-filled identical input as `unchanged`
from a changed fill cache as `refill_only`:
`build/pair-junction-progress-final-replay-20260913/report.json`.

Protected PCIe control: all four probes exactly equal the prior report, retaining
zero DRC, zero opens, 615 tracks and 226 vias. Broader release remains false.
Its SHA256 remains
`d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`.
Evidence: `build/pair-junction-final-control-20260913.json`.

The earlier broad regression passed 1,087 tests, with three skips, one SWIG
deprecation warning and ten subtests. The additional progress-attribution tests
and native replays passed separately. Prior failed fixture/normalization runs
remain recorded; they were not relabelled as passing.

Both new dashboard entries and image endpoints returned HTTP 200 from Windows.
They are labelled BLOCKED and NOT FAB SIGNOFF. Their top/bottom no-body renders
show actual completed critical-wave outputs, not substituted older boards.
The gallery was visually inspected at
`C:/Users/Admin/Documents/CEC-Board-Reviews/pair-junction-20260913/critical-boards-96b4c564b1e03723.png`.

No new six-board campaign was run: the PCIe power-corridor and EPS/ATX fixed
mating-geometry blockers have not changed. Board outlines and mating limits
remain unmodified. The next constructive work is junction/escape selection
under the now-consistent obstacle, shared-barrel and whole-pair contracts;
repeating the same unchanged waves is not a substitute for that work.

## Completed verification

- Final combined regression: **1,093 passed**, three skipped, one SWIG warning,
  ten subtests, 117.64 seconds. Includes the reporting-only addition and its
  changed/invalid-project and no-routing-credit regressions. Evidence:
  `build/pair-junction-complete-tests-20260913.log`.
- Final-engine protected-control replay: all four probes exactly equal the
  prior control; generalization probe passes, broader release remains false.
  Evidence: `build/pair-junction-complete-control-20260913.json`.
- Native progress replay: Hub `refill_only`; 12VHPWR `unchanged`; zero qualified
  routing credit for either. No source board was overwritten.
- `git diff --check` passes. All launched routing/tests/replay jobs have ended;
  no unattended repeat batch remains. Approximately 74 GiB remain free in WSL.
- No commit/push, outline expansion, part/MPN change or fabrication-policy
  waiver was made in this slice. Existing unrelated worktree edits are retained.
