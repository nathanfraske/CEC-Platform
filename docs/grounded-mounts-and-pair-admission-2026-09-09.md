# Grounded mounting and critical-route admission slice

## Authority and requested changes

Continue the corrected 58 x 72 mm hierarchical 12VHPWR checkpoint, not a
historical schematic or a regenerated power layout. Input:
`build/12vhpwr-power-priority-restored-20260909/trial-00/board.kicad_pcb`.
The source has 103 electrical components, four mounts and three fiducials.
All 12 hierarchical source hashes and the protected control hashes are checked
by this slice's closeout. No schematic, electrical BOM or canonical PCB changed.

The owner requested grounded plated M2 mounting holes and identified a coin-like
object in a power lane. That object was an assembly fiducial, not a power part.

## Durable implementation

- The board policy now explicitly declares PTH, GND and the plated 2.2 mm M2
  footprint, while retaining the four mounting datums, 6 mm hardware envelope
  and both-face 6.5 mm courtyard. The new footprint has a 6 mm contact pad and
  eight 0.4 mm stitching bores. All lands are pad 1, GND, solid zone connection.
  Mount reference silkscreen is explicitly hidden in the library and board
  policy so corner datums do not put their default reference text off-board.
  Installed screw, washer, torque and stack-height qualification are not implied.
- `cec_mounting_contract.reconcile` updates only caller-declared mount identities,
  retaining position, rotation, face and lock state. It uses the native deletion
  lifetime adapter. Wrong net, drill type and thermal connection settings fail
  the mount checker. Fresh generation and resumed materialization use the same
  declaration.
- Authored placement copper no longer prevents fiducial repositioning. Explicit
  placement-resume permission and native track/via/filled-zone obstacles are
  required. Arbitrary routed boards retain the default no-move behavior. The
  optical-clearance oracle now checks copper, not only other footprint pads.
- Placement flow-through checks now share a pair-name parser supporting `_P/_N`,
  `_DP/_DM` and `_D+/_D-`, including hierarchy. Recognition does not assign an
  impedance or waive a routing constraint.
- Virtual multidrop junction runways use legal octilinear headings. Previously
  arbitrary neighbor bearings created direct-only exits which their own route
  guard necessarily rejected. The regression fails on the former implementation.
- Local-star admission normalizes covered duplicate tracks before checking
  route quality. Otherwise a duplicate concealed a two-ray acute reversal as a
  three-track branch until final cleanup, after all long edges had been routed.
  Pairwise reassignment uses this same admission, not a weaker replacement test.
- Bounded portal screening interleaves both physical P/N orders within each
  depth/direction bucket. The actual connector previously received 46 candidates
  of one ordering and only two of the opposite ordering. Exact geometry remains
  the acceptance authority.
- Production placement admission discovers critical pairs even when optional
  placement reranking is disabled. A zero reranking budget must not suppress
  readiness checks for pairs the production router itself will require.
  Discovery errors propagate; already-routed inputs retain read-only semantics.
- Render validation additionally rejects sparse pad-only frames spanning a large
  bounding box. The caller now honors validation failure after native renderer
  retries, even if the final process returned exit zero. These are artifact
  checks, not alterations to the board or a synthesized review image.

None of these mechanisms selects this board, a reference designator, MPN or
coordinate. The board-specific mount declaration and experiment artifact paths
remain explicit board inputs, not hidden engine rules.

## Evidence and rejected experiments

Evidence root: `build/12vhpwr-grounded-mount-routing-20260909`.

`02-placement` contains the plated mounts and relocated fiducials. Its native
score is 4 DRC / 250 opens, 415 tracks, 12 vias, 837.8186 mm. The predecessor
was 12 DRC / 246 opens. Four additional open GND terminals are expected until
the newly electrical mounts meet filled planes. The removed DRC categories
were fiducial shorts/clearance/mask bridges and the former NPTH rule-area issues.
The remaining four are three copper-edge clearances and one pad-pad clearance.

`04-admission` passed placement craft with one local-cell copper-access deferral,
but its priority gate was skipped because no reranking policy was enabled. Its
`stage.json` is therefore placement-only evidence, **not routing admission**.
The shared gate fix was implemented after this observation. `05-readiness` is
the bounded replay using the corrected gate; consult `readiness.json` for its
actual result rather than reusing `stage.json`'s placement-only `ok`.

The normal dedicated-plane stage produced `ground-plane/board.kicad_pcb` from
`04-admission`, with 4 DRC / 228 opens. In1.Cu and In4.Cu each fill as one region
at 93.215% coverage. Every one of the nine lands of each declared mount touches
filled GND on both planes. The fill did not alter any routed primitive.

The octilinear junction fix alone let CAN_INT connect both tree edges in about
15.6 seconds, but final cleanup exposed two acute reversals. That transaction
was rejected. Earlier normalized-star checks now reject it before long-edge
routing. A doubled junction menu did not produce an admitted result; the larger
default was removed. A disposable direct-terminal-tree experiment connected
CAN_INT without crossing or angle faults, but only achieved 36.8% coupled
coverage against the existing 60% requirement. It was **not** integrated into
production or promoted. Its saved experimental PCB is not an accepted board.

The initial test launcher lacked a multiprocessing entry-point guard, causing
workers to rerun the launcher against its disposable output. It was corrected
and rerun in a new output directory. Input and canonical boards were untouched;
`03-admission` is failed-launch evidence and must not be selected.

## Regression status

- `build/mount-route-final-suite-20260909.log`: 353 passed across pair routing,
  flow-through placement, mount geometry, fiducials, route quality, parallel
  links, full-pipeline stage logic, ownership and generalization tests.
- `build/grounded-mount-render-tests-20260909.log`: 37 dashboard/render tests
  passed; the subsequent mount-reference policy assertions also pass.
- `build/grounded-mount-pcie-regression-20260909.json`: immutable PCIe control
  score and broader blocker list exactly equal the previous replay: 0 DRC,
  0 opens, 615 tracks, 226 vias, 1242.073 mm. Existing broader release failures
  remain; this is not new unconditional fab approval.
- `closeout.json`: all 103 electrical footprint pad/net/size identities and
  the protected source/control hashes are unchanged. The protected power
  geometry contract retains all 199 original primitives.

The final visible review uses `final-preparation-v2/board.kicad_pcb`; its snapshot is
content-addressed under `review-<board SHA prefix>`. `review-mount-fields.json`
records the first mechanical-field update, and `result.json` records the final
replay, mechanical fields and filled-plane contact proof. The Windows dashboard artifact URL was tested
for HTTP 200 and `image/png`; the local copy matches the generated image hash.

This slice is not fabrication or thermal qualification. The exact priority
routes, residual routing, remaining DRC, signal integrity and final manufacturing
gates must still pass. Review renders are explicitly labelled not routing-admitted.

## Completed corrected-gate replay

`readiness.json` finishes with `ok: false`, `priority_route_gate.applicable: true`
and three critical route refusals. One topology-directed, joint bypass-station
move was accepted: remaining critical-pair tree edges decreased from six to
five. No complete critical-pair transaction became accepted. CAN_INT now proves
one edge but fails the FL1-to-split-link edge; external CAN still fails a split
station junction; USB still exhausts the second flow-through leg's bounded
search. These are routing/search refusals, not proof that the board is physically
impossible to route. No routing or manufacturing gate was waived.

The final checkpoint includes that accepted placement, freshly filled GND
planes, the explicit mount-field policy, all four verified grounded mounts and
all 199 original power primitives. Its native score remains 4 DRC / 228 opens,
415 tracks, 12 vias and 837.8186 mm. The source and controls remain unchanged.
Final PCB SHA-256:
`bcc97e34166f558344c922d3ab206facf2e0236471680b085f8281dd505181e0`.

`build/mount-route-final-all-tests-20260909.log` records 390 passing tests on the
final implementation, including the mechanical reference visibility policy.
The bounded run has ended; there is no unattended wave left running. Nothing
was promoted to a routed or fabrication-review candidate.
