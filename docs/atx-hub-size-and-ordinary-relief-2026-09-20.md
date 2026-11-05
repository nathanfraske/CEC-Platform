# ATX/Hub dimensions, restored output spacing, and ordinary corridor feedback

## Current authority and scope

Use `build/ordinary-relief-next-inputs-20260920.json`. All six retained input
PCBs and their hierarchy signatures are unchanged from the native-assembly
handoff. No source CAD, terminal pitch, outline, daughter interface, BOM, power
budget or acceptance threshold was changed in this turn. No candidate was
promoted. The plan remains held against unchanged automatic waves.

The owner questioned whether ATX had grown and whether its daughter-terminal
spacing had regressed again. Native readback, saved before/after geometry and
an actual paired-outline screen answer those questions below. An independently
zoomed board render is not a dimensional comparison.

## Native dimension and terminal comparison

| Artifact | Native outline | Interpretation |
| --- | --- | --- |
| Current retained ATX | 82 × 95 mm | Same as the preceding retained ATX pass |
| Current retained Hub | 84 × 80 mm | ATX is 2 mm narrower and 15 mm taller |
| September 11 developed ATX | 86 × 95 mm | The later ATX width shrank by 4 mm; height did not grow |

ATX has 15.92% more rectangular-envelope area than the current Hub (7790 versus
6720 mm²). Actual native areas include rounded-corner deductions and are
7784.624 and 6714.624 mm² respectively. This does not establish either board
as optimally compact. The 95 mm carrier rationale used a **74 mm nominal Hub**;
the actual selected Hub is 80 mm tall. That stale nominal proof does not qualify
the actual assembly.

The current ATX row matches the saved pre-compression row, within native rounding:

| Adjacent terminals | Current/original pitch | Current lateral copper-envelope gap | Native courtyard gap |
| --- | ---: | ---: | ---: |
| TB6 / TB4 | 10.5 mm | 1.10 mm | 1.81 mm |
| TB4 / TB2 | 8.0 mm | 0.50 mm | 1.11 mm |
| TB2 / TB1 | 8.0 mm | 0.50 mm | 1.11 mm |
| TB1 / TB5 | 8.0 mm | 0.50 mm | 1.11 mm |
| TB5 / TB9 | 10.0 mm | 0.60 mm | 1.31 mm |

The September 11 bad ECO had reduced the middle pitches to 7.0 mm and created
0.5 mm overlapping copper envelopes. That compressed geometry is **not** the
current retained board. The dimensioned detail groups each terminal's pads
with one color; close legs belonging to one part must not be mistaken for
two adjacent parts. These are nominal/native geometry measurements, not an
incoming-sample or 3D hardware qualification.

Evidence: `build/atx-hub-size-spacing-20260920/report.json`. It records input
hashes, native outlines, terminal inventories, paired datums and source stability.

## Actual stack access remains wrong

The existing independent `cec_assembly_access` screen was rerun on the actual
current pair. All four mating datums agree on reflection in X followed by
translation (86.0, 9.8) mm. The transformed Hub silhouette occupies
(2.0, 9.8) to (86.0, 89.8) mm in ATX coordinates.

Against the existing 1.2 mm planar access requirement:

| Port | Measured gap from mated Hub | Result |
| --- | ---: | --- |
| TB6, TB9 | 0.105 mm each | Insufficient guard |
| J_SIG1 | −6.315 mm | Inside the Hub silhouette |
| J3, 24-pin input | −5.195 mm | Inside the Hub silhouette |

The four smaller power terminals each have 1.405 mm, passing this specific
planar test. These findings are **not** claims of a body collision across the
18 mm stack height. They are failure of the owner's requirement to keep cable
and daughterboard interfaces outside the Hub outline.

The old September 12 review had already identified this coupled-layout defect;
it remains unresolved. Individual-board zero courtyard/copper/edge counts do
not include this paired check. The independent paired screen is still not
wired into per-board admission; that integration and a joint compact-placement
search remain required, not claimed complete here. Preserve the restored
terminal pitch. Do not enlarge ATX or shrink it independently merely to work
around the stale nominal stack calculation. Any movement of shared mezzanine
datums or daughter contacts must be reconciled on both mating members.

## Generic ordinary-layer corridor feedback implemented

`cec_pour_plan` now routes both bundled and ordinary-layer failures through the
same diagnostic producer. Ordinary no-path/blocked-endpoint/width/neck failures
previously supplied no relief map, leaving placement with no repair proposals.

The implementation:

- Rebuilds counterfactual space with the original width, allowed layer region,
  approach geometry and exact raster/neck guard. It no longer drops `f_allow`
  or substitutes a hard-coded 0.6 mm guard in diagnosis.
- Reuses candidate neck acceptance: a found but excessively undersized path
  cannot be advertised as a successful relocation witness.
- Diagnoses ordinary failures only when the corridor has no valid candidate,
  avoiding expensive diagnosis of a failed layer when another layer works.
- Clears stale corridor feedback on replanning and caches duplicate
  obstacle-removal queries.
- Caps production diagnosis at 2 seconds / 48 attempts per failed layer;
  light mode uses 1 second / 8 attempts. Inner path-search loops observe the
  diagnostic deadline. Native geometry operations may slightly overrun a
  cooperative deadline; the enclosing job deadline is still the hard bound.
- Preserves proven witnesses when diagnosis exhausts its budget. Untested or
  interrupted broad-removal questions remain `null`/untested, never false
  no-path claims. Fixed mechanical objects and reserved copper remain present.
- Performs one all-movable-removal counterfactual before a bounded small-cut
  search can spend its entire budget. It is diagnosis only, not a mass move,
  permission to remove protected geometry or a proof of global routability.

No board/refdes/coordinate-specific planner rule was added. Direct diagnostic
calls accept explicit budget parameters; production full/light defaults are
shared by both planner branches.

## Live results, including the runtime failure

The first live attempt was stopped at 167.99 seconds while its full diagnostic
beam was still consuming substantial CPU. It produced no accepted output;
its preview is an interrupted checkpoint, not a finished placement. This
exposed the need for the explicit diagnostic budget above.

The budgeted EPS pipeline pass completed in **97.29 seconds**, with placement
taking approximately 82.5 seconds. Its PCB hash is exactly unchanged:
`c13cdca9785e0bcf9d90211f2153dc6eb85c1d542406544acd01d9bb11964536`.
It retains zero native assembly/pad-copper/pad-edge findings, but the same
three power corridor failures and zero accepted placement repairs. No routing
started. Do not call the time difference a routing speedup or compare an
interrupted attempt as if it had completed.

After prioritizing the broad counterfactual, a final **read-only 33.38-second
replay** of the same EPS placement completed all twelve all-movable-removal
queries (three failing corridors × four layers). None found an acceptable
path. The small-cut searches still exhausted their budget. This is evidence
to investigate fixed-terminal escape, reserved power topology, layer-domain
restrictions and path-search completeness before further moving unrelated
components. It is **not** a mathematical proof that the board cannot route,
nor authority to narrow a declared-current corridor or change current budgets.

The final broad-query scheduling change was tested by read-only replay, not
a third full placement wave. Evidence:

- `build/ordinary-layer-relief-pass-20260920/suite.json`: interrupted first trial.
- `build/ordinary-layer-relief-bounded-pass-20260920/suite.json`: completed bounded pass.
- `build/ordinary-relief-final-diagnosis-20260920/report.json`: final broad queries.
- `build/ordinary-relief-final-diagnosis-20260920/craft.json`: complete evidence.

## Validation and views

Final validation: **282 tests and two subtests passed; four tests skipped**,
one pcbnew deprecation warning. Coverage includes ordinary-layer feedback,
categorical allowed regions, fixed owners, overlong neck rejection, diagnostic
exhaustion semantics, cached/proven cuts, physical geometry, mating rows,
assembly access and pipeline boundaries. The six retained inputs remain native
physical-clean and source-stable. The historical routed PCIe two-port control's
board hash, regression results and probes remain unchanged, including its
pre-existing broader qualification defect.

- `build/ordinary-relief-final-tests-20260920.xml`
- `build/ordinary-relief-final-crossboard-20260920/report.json`
- [ATX/Hub inspection dashboard](http://localhost:8090/?id=pass-atx-hub-size-spacing-review-20260920-atx-24pin-rev3-24933afa3f)
- [Dimensioned inspection panel](http://localhost:8090/img?id=pass-atx-hub-size-spacing-review-20260920-atx-24pin-rev3-24933afa3f&panel=dimensioned-inspection)
- [Completed EPS diagnostic pass, unchanged PCB](http://localhost:8090/?id=pass-ordinary-layer-relief-bounded-pass-20260920-eps-8pin-rev3-cd49fe43a7)

Native previews and the dimensioned panel were inspected locally. The inspection
dashboard's native render and added panel both returned HTTP 200 image/png from
Windows. The panel is explicitly a read-only CAD comparison, not a new route.
