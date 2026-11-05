# Critical prefix retention and exact endpoint reachability

## Implemented boundary

`cec_critical_checkpoint` makes partial critical routing an explicit, independently
qualified artifact, not an `ok=true` shortcut for the whole board. The recovery
runner constructs each pending declared pair from its last admitted parent and
then sends only unfinished pair tiers to the staged backend. A failed sibling
never becomes the next parent. Full constructive/physical qualification remains
mandatory before residual routing.

Checkpoint admission requires new completed P/N ownership, native connectivity,
independent physics for every completed pair including earlier pairs, fresh zone
fill, unchanged placement, preservation of **all** parent track/via geometry,
and repository-wide DRC/open/ownership monotonic admission. The saved PCB and
sidecars are hash-bound; recovery additionally binds original source inputs and
engine files. The placement coordinator accepts a partial artifact only after
a normally completed recovery and verified identities. It retains that boundary
instead of immediately invalidating it with another placement optimization.

Selecting one pair still reserves the future declared pairs' launch regions.
The precision save wrapper supports this explicit transaction scope. The public
read-only preflight API remains read-only.

The final exact-boundary measurement now analyzes the saved artifact directly
when the caller attests a pipeline-authored prefix and exact authority is bound.
It does not convert that artifact back to a placement proposal and strip/rebuild
its critical copper. Prospective/unbound placement evaluation retains the old
materialization path. Source/context sealing remains mandatory in both paths.

`cec_pair_skew` centralizes the existing USB/CAN signoff limits. Generation now
checks accumulated actual copper lengths after the entire pair, including
earlier copper and terminal finishing, and atomically rolls back both members
and their new supporting returns on failure. Independent signoff uses the same
numeric contract. No skew, clearance, via, current or coupling limit was relaxed.

## Exact connectivity versus a raster prediction

Grid terminal records now carry physical pad UUIDs as well as ref, pad number
and coordinates. A failed coarse connection can be discharged only when its
exact endpoints are in one native connected copper component. A shared net name,
zone object, logical duplicate pin number or nearby coordinate is insufficient.
The raw failures and their native proof are retained in preflight evidence.
This does not qualify widths, impedance, current capacity or a whole net's other
branches, and does not change final DRC/connectivity requirements.

Synthetic native tests include top versus bottom SMD connectivity, plated-pad
cross-layer connectivity, incomplete stubs, stale endpoint identities, connected
zone fill versus two disconnected islands in one zone object, and disconnected
locked pair stubs despite an otherwise positive mocked physics report.

## Verified initial results

- Production 12VHPWR recovery independently admitted CAN-internal: 228 to 224
  opens, native DRC unchanged at three existing copper-edge findings. All parent
  copper and component poses were preserved.
- Two subsequent critical-only backend waves started from that admitted parent
  and omitted CAN-internal from their pending tiers. External CAN and USB did
  not close. The repeated-unadmitted-geometry guard stopped further identical
  waves. Original source inputs and engine signatures remained unchanged.
- Initial combined regression: 767 passed, one SWIG deprecation warning, two
  subtests; additional native negative/connectivity tests passed afterward.
- Protected PCIe 2-port control: all four probes exactly equal the previous
  control report, retaining zero DRC and zero opens. Its existing broader
  release failure is not cleared by these changes.
- Direct retained-Hub preflight replay reports zero coarse unreachable edges,
  including before any existing-copper discharge; therefore that replay does
  **not** demonstrate that the new discharge rule fixes the two earlier Hub
  refusals. The fully materialized pipeline context must be evaluated separately.
- A 300-second-budget external-CAN diagnostic stopped after 135.063 seconds
  without admission. More budget alone did not close it. A bounded-terminal
  policy-parity experiment connected the pair after 66.004 seconds, but native
  saved-artifact verification rejected 7.461 mm skew against the existing 4 mm
  limit and DRC growth from 3 to 15 (via diameter/annulus, co-located holes and
  clearance). That policy relaxation was **not integrated**. It exposed the
  missing aggregate skew check which is now fixed; per-leg coupling was never
  sufficient evidence of whole-pair qualification.

Evidence: `build/critical-prefix-recovery-20260913/12vhpwr/`,
`build/critical-checkpoint-regression-20260913.log`,
`build/critical-checkpoint-control-20260913.json`,
`build/hub-native-full-reachability-20260913.json`,
`build/critical-prefix-effort-20260913/`.

## Full suite pass

`build/critical-checkpoint-suite-20260913/` runs all six current main boards from
explicit retained inputs, with four concurrent board jobs, 24 craft trials,
four requested routing passes and 1,800-second job caps. The campaign has ended;
the final skew/measurement/reporting refinements were integrated afterward and
tested separately. All six campaign source-input and engine signatures stayed
unchanged. **No main board entered residual/general routing in this pass.**

| Board | Elapsed | Retained outcome |
| --- | ---: | --- |
| 12VHPWR | 903.3 s | CAN-internal prefix copied into the real placement output; both fallback waves preserved it; two other pairs remain unqualified. |
| Hub | 506.9 s | Unchanged; CAN and two critical PSU_5V_KVM reachability edges remain. |
| PCIe 2-port candidate | 308.7 s | Unchanged; two power-corridor failures remain. |
| PCIe 3-port | 1,108.1 s | Last decoupler violation cleared in a retained checkpoint; three power corridors remain. Extra post-finalization repair cycle was explicitly interrupted, not reported as completed or qualified. |
| EPS | 15.0 s | Fixed terminal geometry blocks placement; no replacement board output. |
| ATX 24-pin | 15.6 s | Fixed terminal geometry blocks placement; no replacement board output. |

PCIe 3-port checkpoint SHA256 is
`642dea078a3f1b485ca32428b9a89452bbda318f22efce6c549024ebdd3dbb6b`.
Fresh independent measurement confirms zero pad/courtyard faults, zero detection
and decoupler violations, and unchanged power failures on SENSEC1_HI,
SENSEC1_LO and SENSEC3_LO. The earlier checkpoint had one decoupler violation.
Evidence: `build/critical-prefix-pcie3-checkpoint-measure-20260913.json`.

12VHPWR output SHA256 is
`1b1da8a82c3899d70ea3b81abd69be25f98a378dae72170281cc8c31009b85f6`.
Fresh-copy/refill/native revalidation of the actual published output passes
partial admission with 228 to 224 opens, unchanged three DRC findings, unchanged
placement and all parent copper preserved. This is not merely a solver-local
diagnostic. Evidence: `build/critical-prefix-final-assurance-20260913/proof.json`.

The final production exact-artifact priority measurement completed in 131.074 s,
reused CAN-internal ownership, and still refused external CAN and USB. Native
endpoint evidence discharged four false raster failures on already-connected
SENSEP3/SENSEP4 HI/LO edges; two ordinary planning failures remain and critical
global unreachable count is zero. The saved measurement includes this evidence
and a complete source/engine baseline certificate. Evidence:
`build/critical-prefix-final-native-measure-20260913.json`.

The Hub's two failures reproduce under the actual bound production policy even
without rematerialization. Native source-board connectivity does not qualify
those edges. They must not be waived as already connected merely because a
separate frozen-power authority reports a planned connection.

All six dashboard pages and their actual render endpoints returned HTTP 200
from Windows. The content-addressed no-body gallery was visually inspected:
`C:/Users/Admin/Documents/CEC-Board-Reviews/critical-checkpoint-suite-20260913/all-boards-c9e2e4f62ce04d6a.png`.
EPS/ATX are explicit no-output cards, not substituted older renders. PCIe 3-port
is labelled as a blocked craft checkpoint.

EPS and ATX 24-pin retain fixed terminal-pad conflicts. Their existing board
width and mating-datum limits, vendor pad geometry and current requirements are
unchanged. These conflicts are not waived to launch a router.

## Remaining generic work

- Coordinate whole-pair skew and native layer/via ownership during search,
  before accepting an attractive first leg; avoid manufacturing duplicate or
  unqualified endpoint barrels. The independent checkpoint gate now catches
  these failures but does not magically solve them.
- Resolve the contract between Hub's frozen power plan, physical source-board
  connections and global route prediction, preserving the priority power paths.
- Solve the PCIe current-corridor/cell obstructions and the EPS/ATX joint mating
  geometry within existing limits; do not hide these behind more residual waves.
- Share placement plateau history across post-finalization repair phases. The
  PCIe 3-port interruption was deliberate bounded operation, not an implemented
  cross-phase plateau fix.

No files were deleted, no component/current/fabrication policies were relaxed,
and the protected zero-open PCIe control was not edited. Approximately 74 GiB
remain free in WSL. No recurring wave automation was created.

## Final regression

- **780 tests passed**, one KiCad SWIG deprecation warning and two subtests,
  in 104.71 s: `build/critical-prefix-final-tests-v2-20260913.log`.
- An older test expected attested copper to be rematerialized. It was updated
  to require exact-file analysis and explicitly prohibit that destructive
  rehydration path; the prior failed run remains recorded, not overwritten.
- The new aggregate-skew regression exercises the real precision transaction
  boundary and verifies rollback of both members and their supporting GND
  copper when otherwise-accepted local legs exceed the whole-pair limit.
- All four final protected-control probes exactly equal the previous report:
  `build/critical-prefix-final-control-20260913.json`. Board SHA256 remains
  `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`.
  Its zero DRC/zero opens are unchanged; broader release status remains false.
- `git diff --check` passes. Every launched campaign/diagnostic is stopped or
  complete; the dashboard remains running. No routing job was left unattended.
