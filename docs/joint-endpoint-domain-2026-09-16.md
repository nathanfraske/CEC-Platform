# Joint endpoint domain: complete-contract counterfactual

September 16, 2026, 13:14 UTC. Diagnostic only; no production integration,
board promotion, or changed design authority.

## Current inputs, not the older counterfactual

Inputs are exactly the PCIe3 and 12VHPWR rows in
`build/bound-return-next-inputs-20260916.json`. Parameters/configuration come
from their last full-pass priority operation evidence, with authored-prefix
and board route authority rebound on disposable copies. The six input PCB and
hierarchy signatures and shared engine all remain unchanged.

The earlier ribbon-order note's six-P/32-N, 2.176366x CAN witness belongs to
the **retained diagnostic board**, not canonical PCIe3. The current canonical
CAN witness has **three P and 27 N** individually native-clear paths. Its
shortest P is 7.956181 mm over a 3.841402 mm span: **2.071166x**. No ordering
can select a below-2.0 P member from this finite domain. That is a domain gap,
not evidence that the entire board is unroutable.

The observer captured 332 calls / 187 distinct domains for PCIe3 and 628 /
427 for VHP, with no omitted domains. Calls are not distinct failed nets.
Evidence: `build/joint-escape-domain-probe-20260916/report.json` and its
per-board reports; launcher `tmp/joint_escape_domain_probe_20260916.py`.

## Bounded inward-run translation

On paths with antiparallel first/last legs, translate all internal vertices
together toward the endpoints, retaining fixed endpoints and internal shapes.
The probe tries 16 fractional offsets on up to four shortest members in each
of at most four applicable domains. Every trial retains octilinearity,
no-reverse-bend, original exact native segment clearance, and all original
joint-pair admission checks. Original paths remain available. This is an
additive finite-domain experiment, not a new admission waiver.

PCIe3 gained 19 native-clear P paths in the salient domain, bringing the best
selected member detour to **1.977756x**. VHP gained none in its four sampled
overlong domains. The observer-only run returned the original selection;
`build/joint-escape-slide-probe-20260916/report.json` is not a closure result.

The second run actually returned the refined choices to the private priority
pipeline: `build/joint-escape-slide-admission-20260916/report.json`.
PCIe3 remains **11 -> 11** refused important routes (84.185 seconds), and VHP
**1 -> 1** (75.637 seconds). Both workers completed. All six input/hierarchy
signatures and engine were checked unchanged at completion. Launcher:
`tmp/joint_escape_slide_probe_20260916.py`, `CEC_SLIDE_ADMIT=1`.

## Exact downstream refusal, not a hidden success

The refined PCIe3 CAN route passes saved-copper detour and post-closure
geometry/partner-pad checks, but then fails the existing coupling contract:
0.0% coupled coverage, 7.597357 mm uncoupled length versus a 6.609231 mm
geometry-derived local-fanout budget. The normal floor is 60%. The independent
check correctly refuses and removes the provisional route. The other CAN_J1
pair still has no clear coupled corridor; nine Kelvin refusals remain.

An exhaustive replay of **all 22 x 27 = 594** combinations in the expanded
salient domain confirms that changing the objective alone cannot fix it:

| Finite-domain check | Passing combinations |
| --- | ---: |
| Mutual crossing/clearance/coherence | 594 |
| 2.0x member detour | 17 |
| Declared local skew | 384 |
| Existing coupling contract | 0 |
| All these local contracts together | 0 |

Among detour/skew-passing choices, the closest replay has 12% coupling and
6.685675 mm uncoupled versus 6.609231 mm allowed. The shortfall is **not**
permission to relax the budget. This replay uses captured native-clear member
provenance and existing production coupling functions; it does not reload a
board or certify reference-plane, return-path, whole-board, or fab readiness.
Evidence: `build/joint-escape-complete-contract-probe-20260916.json`;
launcher `tmp/joint_escape_complete_contract_probe_20260916.py`. Its initial
report-write attempt used an incorrect helper name and failed before writing;
the corrected run completed successfully. KiCad emitted existing enum-choice
diagnostic warnings on import; no boards were loaded or modified.

## Next bounded slice

Do **not** integrate the slide-only prototype as a closure fix, repeat its
unchanged domain, or launch another identical full suite. A useful next solver
slice must construct the two member paths together around the same obstacles,
with coupling included during proposal generation/admission, while preserving
native member guards, skew, detour, endpoint direction and immutable buses.
An obstacle-derived shared corridor/visibility domain is a concrete candidate.
Test synthetic displaced/split endpoints and trapped domains first, then these
two source-bound probes and the historical PCIe2 regression; retain all final
independent gates. Full-board admission is required before any publication.

Hub/local-power access remains a separate coupled dependency; EPS/ATX retain
their existing mechanical authority hold. Keep the canonical continuation
plan and dashboard/gallery unchanged. No production code or board geometry
was changed during this diagnostic.
