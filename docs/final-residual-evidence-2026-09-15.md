# Final-board residual evidence and continuation ownership screen

## Root cause and implemented boundary

The route oracle returned `cand.params.import_report` as its completion report
after subsequent certificate repair, local-via repair, cleanup and final scoring.
Its final DRC blockers were current, but the detailed endpoint certificates
consumed by placement feedback were not necessarily current. On the selected
PCIe2 905f PCB, the old `final_completion` contains four certificate rows,
including THRESH (now connected), while final connectivity has ten opens on
six nets. This is incomplete/stale diagnostic coverage, not evidence that DRC
silently accepted an open board.

Implemented generically:

- `cec_final_residual.measure` runs fresh native DRC against the actual saved
  board and performs a read-only endpoint-ray/foreign-copper survey. It resolves
  endpoint UUIDs to loaded native pads/tracks/vias/zones, uses project branch
  width/clearance, and binds PCB/project/rules/power-state hashes before/after.
  Resolved unique sibling projects are bound too. It never saves or alters PCB
  copper, claims a route search ran, proves no-path, or grants release authority.
- Every open is indexed. Optional geometry details are bounded to 32 endpoints
  pairs / ten seconds between pairs; capped, stale-UUID and failed details are
  explicit. Native DRC runs under the enclosing worker's overall deadline.
  Surface-only pad escape hints cannot borrow clear rays from another layer;
  THT endpoints advertise their actual enabled copper span.
- The final route oracle publishes this source-bound snapshot, checks its
  connectivity count against the final scorer, and refuses the release
  conjunction on a failed/inconsistent snapshot. Placement-only grading marks
  this extra routed-snapshot requirement inapplicable, not a new routing pass.
- Final endpoint observations join dashboard/failure-stack events by UUID,
  with references into the completion report. Association does not claim which
  stage created the defect. Historical stage attempts are preserved separately.
- Both `cec_completion_evidence` and `cec_certificate_repair` prefer the final
  snapshot. Failed/partial/empty fresh evidence does not fall back to stale
  attempts. A later genuine live probe explicitly supersedes that snapshot.
  The production subprocess dispatcher recognizes fresh-only report payloads.
- Native endpoint kinds retain the established `pad`/`trk`/`via`/`arc`/`zone`
  protocol, rather than raw uppercase KiCad class names that would hide pads
  from endpoint-owner planning. No board/refdes/coordinate override was added.

## Validation receipts

- `build/final-residual-final-tests-v4-20260915.log`: **209 passed, four skipped**,
  27.68 s. The skipped tests are opt-in minute-scale legacy router fixtures;
  no full new routing wave is claimed. Earlier 116/207/208-test runs overlap.
  New loaded-native fixtures cover translated/rotated/renamed geometry, foreign
  copper, clean connectivity without fab signoff, THT versus SMD access,
  immutable source checks, stale UUIDs, bounded partial coverage, both feedback
  consumers, production dispatch, and source-associated (not causal) tracing.
- `build/final-residual-suite-replay-v4-20260915/report.json`: six explicitly
  bound BETA lineages, three parallel workers. Every source/hierarchy and engine
  guard passes. Four admitted families receive native diagnostics and read-only
  track/negotiation/owner plans; EPS/ATX retain interface-ECO admission refusal.
- `build/final-residual-v2-control-comparison-20260915.json`: historical PCIe2
  PCB, full regression object and probes unchanged. Only generalization evidence
  differs. Existing release holds remain. Generality: 74 core modules / zero
  core findings, unchanged 23 physical and 380 runtime legacy findings.

| Exact current input | Fresh open inventory | Geometry coverage | Meaning |
| --- | ---: | ---: | --- |
| PCIe2 905f | 10 | 10 / 10 | Partial routed board, unchanged |
| PCIe3 400ff | 254 | 32 / 254 | Placement/pre-route inventory, not routed regression |
| Hub ce61 | 242 | 32 / 242 | Placement inventory, still craft blocked |
| VHP 3af1 | 220 | 32 / 220 | Placement inventory, still priority-route blocked |
| EPS rev3 | Not measured downstream | Not admitted | Coupled interface ECO hold |
| ATX rev3 | Not measured downstream | Not admitted | Coupled interface ECO hold |

The native surveys took about 1.1–2.2 seconds each. PCIe2 covers all ten current
open pairs on +3V3, +5VSB, I2C_SDA, VBUS, U4_OV1 and U4_SS in **1.55 s**.
Both consumers and the trace builder see ten current records. Some native
ratline endpoints differ from the older oracle despite equal total counts;
same-net association alone is not enough to reuse an old endpoint certificate.

These are diagnostics, not promoted board candidates. No new PCB geometry,
schematic, load budget, footprint, fabrication process or interface was changed.
No historical archive was rewritten or presented as a new full-pass output.

## Next distinct repair: preserve rebuildable ownership across continuations

`build/final-residual-ownership-screen-20260915.json` binds the current PCIe2
905f board and the earlier **journal-verified** fbaa placement baseline.
All **60** certificate-named immutable track blockers are already present in
that placed baseline; **18** carry `CEC_LOCAL_ENDPOINT_NECKDOWN` group labels.
Fresh read-only planning with no newly granted unlock authority yields no
track or negotiation windows, and four bounded endpoint-owner proposals.
Those proposals are NOT admitted placements or routing progress.

Code evidence: `_generated_locked_route_uuids` treats only locked UUIDs absent
from the explicit `authored_baseline` as generated/rebuildable in that invocation.
`route_oracle_grade` supplies `placed`, which can already contain prior routed
copper on continuation. This explains why inherited local copper is outside
that repair eligibility set. The prior actual repair ledger nevertheless had
58 newly eligible UUIDs in its own generation; do not describe it as having
zero eligible work altogether.

Next work should investigate durable, content-bound producer/ownership receipts
for **complete local cells** across continuation imports. Labels alone cannot
authorize unlocking. Distinguish fixed power buses, accepted coupled/Kelvin
routes, authored copper, and explicitly reconstructible generated local copper;
require exact old-prefix preservation or a qualified complete-cell replacement
with independent DRC, locality, connectivity and full-score rollback. Do not
globally unlock the 60 blockers or rerun the identical wave expecting a new
result. Existing native `board.Remove` sites in older certificate-repair paths
also need scoped safe-disposal review before exercising new destructive branches.

Other independent work remains Hub coordinated return-portal seating, PCIe3
priority-reach cell relocation, VHP coupled USB escape, and coupled EPS/ATX
main/daughterboard fit within existing dimensions. No engine workers remain
at this receipt; check live journals/processes before the next change. Disk
free space remains about 67 GiB, above the 16-GiB floor.
