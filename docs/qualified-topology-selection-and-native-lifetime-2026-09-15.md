# Qualified topology selection and native copper lifetime — 2026-09-15

## Outcome and limits

The retained 12VHPWR diagnostic now reconstructs CAN_INT successfully, with
independent critical-prefix proof. Whole-pair coupling improves **33.3% to
66.7%** (60% minimum unchanged); skew improves **3.876134 to 3.034187 mm**
(4.0-mm limit unchanged). Both tree edges are connected. Native counts move
from **3 DRC / 228 opens to 3 DRC / 224 opens**, preserving all parent copper
and every placement. This is NOT whole-board or fabrication admission.

Final native replay: `build/qualified-topology-replay-20260915-final/`.
Operation elapsed 38.514 s; source/hierarchy, diagnostic-family and engine
signatures all unchanged. `result.json` has `ok=true`, independent `proof.ok=true`,
`admission_scope=critical-prefix`, and **`release_accepted=false`**.
The diagnostic uses a previously journaled placement offer and is not promoted
directly into BETA. Canonical producer-to-handoff replay remains necessary.

## Root cause: success was declared before the selection criterion

`_route_multidrop_topologies` returned the first fully connected candidate after
geometry, detour and skew checks. Duplicate-pad ownership, normalization,
whole-pair coupling and plated-terminal returns were checked only afterward.
When coupling rejected that candidate, the caller rolled the pair back but
never resumed the remaining topology orders. No extra compute could select
those already implemented alternatives through that control flow.

The existing final qualification statements were mechanically extracted into
`_qualify_pair_candidate`, with AST-equivalence checked during extraction.
The multidrop selector now calls this same authority before accepting each
complete direct or layered candidate. Failed candidates roll back and the
remaining bounded domain can be tried. The original final qualification and
independent checkpoint/refill/physics checks remain in place. No threshold,
clearance, width, layer, power priority or routing authority was relaxed.

The default native domain still has at most two orders and the layered domain
at most three alternatives, sharing the original absolute deadline. No budget
reset or indefinite retry was added. In the saved VHP case, backbone-first is
rejected and the existing local-first order succeeds. No board/refdes/coordinate
exception or new placement is embedded in the solver.

## Root cause: loaded native objects need native disposal

Qualification can normalize/delete temporary package-pad links. Retrying a
topology therefore needs their exact UUID/geometry restored, while also
removing rejected signal copper and supporting return vias. A scoped
`CopperSnapshot` now supplies that parent state and preserves group membership.
Only transaction-created temporary copper is passed by the production caller;
source power and earlier owned pairs are outside this replaceable scope.

A six-board in-memory stress audit exposed another issue: `board.Remove()`
hands a loaded borrowed proxy to Python ownership, whose finalization can
over-decrement KiCad's SWIG type-registry reference. The initial audit failed
with bare `SwigPyObject` returns and a native teardown crash. Pinning the
registry, disabling GC, and using `RemoveNative` plus Python ownership did not
resolve it. Substituting the repository's existing permanent native-disposal
helper did. The small born-owned fixtures had not reproduced this loaded-object
failure mode.

`cec_native_items.discard_items` is now used by snapshot restoration and all
16 permanent-discard sites in `cec_precision_route` (including rollback,
candidate probes, normalization and final rejection). This reuses an existing
general lifetime fix; it does not grant new permission to delete copper. The
previous deletion scopes remain unchanged. Static regression coverage now
includes both modules to prevent reintroducing `Remove` for permanent discard.

The first canonical cohort was intentionally stopped before shared edits:
`build/qualified-topology-suite-20260915/interruption-decision.json`.
Hub and VHP parents exited 143 through their owned-operation cleanup; PCIe3 had
already completed blocked after 255.797 s. The coordinator finished at
07:04:16Z, all process descendants were checked gone, and all source/engine
guards remained unchanged. Its previews are unchanged BLOCKED placements,
not new routed candidates. This was an engineering cancellation, not evidence
that those placements are impossible.

## Validation

* Ten dedicated topology/snapshot tests pass, including native coupling
  rejection followed by acceptance, all-rejected/exception rollback, deadline
  and attempt bounds, layered candidate gating, idempotent complete native
  qualification, and loaded/grouped track-and-via roundtrips in a subprocess.
  The latter checks registry reference balance through repeated restoration,
  ordinary rollback, garbage collection and normal interpreter shutdown.
* `build/qualified-topology-native-audit-20260915-final.json`: exact in-memory
  geometry, UUID and group roundtrips across all six current source families:
  466 VHP + 28 ATX + 176 Hub + 741 PCIe2 = **1,411 copper items**; EPS/PCIe3
  inputs contain no tracks/vias. All six have topology-derived multidrop
  applicability. This is compatibility/applicability evidence, not route or
  mating admission. All source/hierarchy hashes and engine checks pass.
* `build/qualified-topology-control-20260915-final.json`: historical PCIe2
  SHA, board regression and every probe exactly equal
  `build/supported-menu-control-20260915.json`. Its pre-existing strict release
  failures remain; unchanged does not mean newly fabrication-qualified.
* Broader precision-consumer sweep: **959 passed, 33 subtests**, one existing
  SWIG deprecation warning, 73.10 s, in
  `build/qualified-topology-integrated-tests-20260915-final-b.log`.
  The first broad sweep found five test-double failures because two synthetic
  board adapters exposed Remove but not Groups/Delete; those adapters now
  model native permanent-discard semantics. No production fallback to unsafe
  Remove was introduced to satisfy tests.

## Suite boundaries

Hub, VHP and PCIe3 are the affected canonical follow-up targets. PCIe2 retains
its previously recorded partial routed result (0 DRC / 12 opens), separately
from the historical zero-open control. EPS and ATX still require the qualified
coupled mating ECO: no wider edge span, smaller lands or independently moved
daughterboard half is silently substituted. The ATX root also has the recorded
invalid closed-outline issue. This slice does not claim to repair those gates.

## Corrected canonical replay — now complete

`build/qualified-topology-suite-20260915-final/suite.json`, started
**2026-09-15T07:11:50Z**. Three parallel jobs, two workers per board, same
1200-s priority / 1800-s board bounds and 16-GiB free-space floor. Initial
native process IDs: VHP 18713, Hub 18714, PCIe3 18715; all were checked live.
This is a fresh output directory using the same six-family hash-bound input
plan, not a resumed mixed-engine run. The earlier cancelled cohort remains
immutable. Check current journal AND processes before any new dispatch or
shared engine edit. Pass previews publish independently as each board finishes
to the port-8090 dashboard and Windows
`C:/Users/Admin/Documents/CEC-Board-Reviews/qualified-topology-suite-20260915-final`.

### 07:29 observed results

Hub completed blocked in 681.836 s; PCIe3 in 238.217 s. Both outputs equal
their inputs, with source/hierarchy and engine guards passing. Their body-free
views were visually checked in
`all-boards-f2e12f37925f3a22.png` (VHP is explicitly a running/no-preview card).
Hub's two physical-valid pair replacements still construct only one of six
CAN tree edges. PCIe3's two funded offers have `craft_failed_terms` containing
`power_body_clearance`; its detailed evidence says exact current territory is
unroutable for `/SENSEC1_HI`, with no direct body-collision violations. The
reserved-copper/terminal-field obstruction needs diagnosis, not an assumed
body nudge or relaxed current geometry.

The live VHP canonical handoff now passes beyond the former failure:
`02-placement/operation-priority-power-replan-e_q7b9x3/checkpoint.json` records
`current_trial.priority_dependency_rebuild.ok=true`, reason
`pair_dependency_rebuilt`, and physical/post-authority checks true.
Its `candidate/priority-dependency-01/checkpoint.json` has independent prefix
proof, unchanged parent copper and placement, 66.7% whole-pair coupling and
3.034187-mm skew. Counts are 3 DRC / 224 opens, versus 3 / 228 before. This
validates the normal producer-to-reconstruction path, not only the earlier
isolated replay. Full candidate measurement is still running; acceptance and
promotion have NOT been claimed. The worker's 97.1% portal-ribbon log is a
local metric and must not be presented as whole-pair coverage.

During the same review the power-replan operation completed in **293.365 s**:
`report.json` now has `changed=true`, `accepted_count=1`, and
`stop_reason=power_replan_candidate_accepted`. Its full trial is accepted as
`strict_post_power_authority_improvement`, with rebuilt dependency and physical
checks intact. This supersedes the pending checkpoint observation above.
Two critical-route refusals remain in `result_evidence`; the parent pipeline
is still completing placement checks. An accepted intermediate repair is not
whole-board placement/routing/fabrication admission, and no final board winner
or release is claimed before the parent journal completes.

### Final outcome: outer ownership handoff is missing

The suite completed at **07:33:52Z**. VHP elapsed 1253.104 s; source/hierarchy
and engine guards pass for all three boards, and no processes remain. All
published outputs equal their inputs. VHP's parent stage failed after the
accepted intermediate repair: `checkpoint_authored_prefix` passed the original
`power_prefix_owner` into `_admit_materialized_power_prefix`, which still
required the old CAN_H_INT / CAN_L_INT geometry (18 / 14 missing primitives).
Its separate `qualified_pairs` check correctly reports the reconstructed pair
connected and physics-qualified. The error is a stale exact-copper ownership
contract, not permission to ignore missing power or arbitrary changed copper.

The accepted artifact and full proof are retained under
`12vhpwr-standard/02-placement/operation-priority-power-replan-e_q7b9x3/candidate/power-replan-finalists/finalist-zx856g88`.
The next fix must transfer ownership through a source-bound, explicitly scoped
accepted-replacement receipt, prove all retained copper again, and handle board
rollback and contract rollback together. Merely recapturing the changed board
would weaken the power guard and is not an acceptable fix. Neither the final
guard nor the ownership transition has been relaxed/changed in this review.

The final immutable previews are
`C:/Users/Admin/Documents/CEC-Board-Reviews/qualified-topology-suite-20260915-final/all-boards-ddbc194fa1f081fb.png`.
They are unchanged BLOCKED placements; the successful intermediate repair must
not be advertised as a final board winner. This final section supersedes all
earlier live/pending observations above.
