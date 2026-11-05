# Shared route-dimension solver — 2026-09-04

## Implemented

`scripts/cec_route_dimensions.py` is the shared dimensional authority for
ordinary routing, priority-current routing, import normalization and signoff.
It has no board/refdes/coordinate selectors. It compiles requirements rather
than declaring that every requested geometry fits the current placement.

- One hierarchy-aware netclass resolver with explicit-assignment precedence.
  Routing and signoff previously used different pattern matching. An ambiguous
  project, malformed authority or invalid number now fails closed rather than
  quietly producing a smaller default.
- Ordinary via dimensions combine class diameter/drill, board minima and the
  annular-ring floor. Increasing drill cannot leave an undersized annular ring.
- Aggregate trunk widths use layer-specific copper and the same existing
  current model as signoff, preserving current-budget margin provenance. A
  budget that already includes margin does not receive another factor of 1.25.
- Local branches remain distinct from aggregate trunks. Full net current is
  not imposed on every capacitor or logic branch. Existing bounded pin-escape,
  Kelvin and independently qualified precision ownership rules remain active.
- Explicit profile-qualified, fully pad-contained through vias may use the
  filled/capped process. A repair candidate never shrinks existing via copper,
  and requires actual pad containment, foreign-copper clearance, hole spacing
  and board-edge checks. Merely having six layers does not opt into POFV.
- Normalization now checks proposed growth **before mutation**, including split
  track bodies. In-place changes that do not fit are refused with UUID, net,
  required dimensions, obstacle evidence and `reroute_required_no_in_place_growth`.
  Locked copper is not modified by this finishing stage.

Integration points: `cec_fr` project resolution and normalization;
`cec_synth_pipeline` priority-current resolvers; `cec_current_topology` current
width contracts; `cec_constraints` class/current signoff; `cec_fab_profile`
ordinary via floors and finite POFV dimension validation. The existing shared
hole-spacing helper gained explicit self-via exclusion for resize previews.
The new core module is included in `cec_generalization_gate`.

## Important regression discovered and prevented

The first PCIe normalization trial appeared to reduce dimensional violations
from 50 to 34 with zero DRC and zero unconnected nets. It nevertheless created
an additional unqualified same-net via-in-pad overlap (7 -> 8). DRC does not by
itself prove assembly-process suitability. That trial was never adopted.

The pre-mutation growth checks prevent this debt swap. The final safe result
is **50 -> 48**, not 34. Seven requested via enlargements are refused rather
than turning nonconforming geometry into new pad/assembly faults. The exact
refusals are in the replay report. None of those sites passed the bounded
pad-contained POFV repair alternative either; they require spatial/owner repair.

## Final bounded cross-board replay (v4)

Experiments operate on copies; neither source board was changed or promoted.
The replay preserves `.kicad_pro`, `.kicad_dru`, pour plans, pour-first state and
other board-owned sidecars through the existing copy boundary. Earlier v1 lacked
pour ownership and is superseded; v2 is the unsafe-growth trial; v3/v4 apply the
growth guards, with v4 also exercising the process-qualified candidate selector.

| Metric | PCIe 2-port control | Current 24-pin candidate |
| --- | --- | --- |
| Netclass dimensional violations | 50 -> 48 | 4 -> 0 |
| Structural DRC | 0 -> 0 | 27 -> 27 |
| Unconnected | 0 -> 0 | 97 -> 97 |
| Unqualified via-in-pad overlaps | 7 -> 7 | 28 -> 28 |
| Normalization changes | 2 track sections; 9 endpoint splits; no resized vias | 4 track widths |
| Via enlargement refusals | 7 | 0 |
| Newly repaired qualified POFV vias | 0 | 0 |

PCIe retains eight release blocker categories; the 24-pin loses its netclass
blocker but remains incomplete. The 24-pin DRC/unconnected figures are reported
as measured, not implied to be fab-ready. PCB length/route paths were unchanged
by the dimensional trials. PCIe track count increased 615 -> 624 because of
the nine bounded neckdown splits, not additional routed paths.

Final reports:

- `build/dimension-replay-pcie-8pin-2port-v4/report.json`
- `build/dimension-replay-atx-24pin-rev3-v4/report.json`

Archived PCIe source:
`build/board-archive/20260831T1619-pcie-8pin-2port-v113-zero-open-v43/board.kicad_pcb`

SHA-256: `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`.

The unchanged archive's four release probes also matched the preceding slice
exactly (`build/pcie2-fab-review-dimension-contract-regression.json` versus
`build/pcie2-fab-review-rail-contract-regression.json`). The final copy's before
probe confirms the same 0/0 baseline and existing blockers with full sidecars.

## Tests and limits

20 new parameterized test cases cover hierarchy, explicit precedence, malformed
authority, class/board/annular combination, margin provenance, trunk/branch
separation, actual imported-via repair/idempotence, sidecar-preserving replay,
new same-net pad/hole faults, foreign-copper growth and explicit POFV repair.
The profiled synthetic case repairs a 0.35/0.15 mm via to 0.35/0.25 mm without
enlarging copper; the same unprofiled case is refused.

**612 tests passed**, plus 11 subtests, across the final focused and integration
runs. Validation logs: `build/dimension-contract-focused-tests.log` and
`build/dimension-contract-final-integration-tests.log`.

This is not a new thermal/FEM qualification, a complete spatial rerouter, or a
claim that every legacy geometry emitter already consumes the new contract.
The existing IPC-2221-based sizing model was reused, not newly validated here.
Full-pipeline generic release is still false (the separate legacy-selector
debt remains). The proposals are diagnostic artifacts, not adopted fab candidates.

## Next bounded step

Implemented in the follow-up [bounded spatial-repair slice](generic-dimension-spatial-repair-2026-09-04.md):
two PCIe via repairs admitted on a copy; dimensional findings 50 -> 44 overall,
same-net via/pad overlaps 7 -> 5, with 0 DRC / 0 opens retained. That report
also documents a replay identity-propagation fix and the remaining owner limits.

Consume `refused_growth` as a spatial-repair request: reconstruct an endpoint
escape or move its via using the solved final dimensions before locking it.
For locked undersized features, repair must invalidate/recompile the owning
cell and re-prove its connectivity/precision contract; ordinary normalization
must not silently override it. Admission must compare individual fault
identities and assembly violations, not just DRC totals or blocker categories.
