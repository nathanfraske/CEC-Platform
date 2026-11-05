# Content-bound placement reconstruction, 2026-09-28

## Cause and bounded repair

ATX event wave B reconstructed a better force-rail baseline internally, then
reused the incoming board's craft report without checking its identity. With
no accepted footprint move it also discarded the reconstructed copper. The
published board consequently remained byte-identical to A (1/4 rails), even
though the constructor's private diagnostic reached 2/4. Neither result was
routing or fabrication admission.

The generic craft boundary now reuses incoming evidence only on an exact
content/policy/sidecar identity match. Any reconstructed artifact with a
different identity receives fresh full craft evidence. Unbound, failed, or
mid-measurement-mutated evidence is not reused.

A reconstruction-only improvement is separately marked as a proposal. The
coordinator can retain it without a footprint move, but only after a bounded
native transaction proves all of the following:

- Strict improvement with no worsening of any active craft key term.
- Native component/pad geometry, faces, copper-layer count and complete board
  contours are unchanged; source schematic intake still passes.
- Previously protected copper and qualified pairs remain intact.
- Frozen power authority, if present, is unchanged and still valid.
- Fresh native DRC identities, connectivity, Kelvin/pair gates, route quality,
  and foreign-on-pour counts do not regress.
- Native placement evidence exists and introduces no new physical conflicts.

On refusal or exception, the incumbent PCB and its complete small authority
family are restored. The transaction now includes cell reports and prefix
checks as well as rail reports, project rules, plans and skeletons. The
top-level result describes the retained incumbent after rollback, never the
discarded improved-looking proposal. Construction is not electrical/thermal
qualification; all later routing and release gates remain mandatory.

No board/refdes/net-name/coordinate exception or clearance relaxation was
added. The new guard is included in the generic-core static audit.

## Validation before event wave C

- 26 focused reconstruction tests passed, covering stale/missing identities,
  same-pose progress, independent native regression vetoes, authority changes,
  whole-family rollback, exceptions, missing evidence, and native pad/outline
  changes.
- The placement identity, frozen power, policy seal, route prefix and full
  pipeline group passed 151 tests (including the first 25 focused tests).
- Craft placement, stage admission, event listener and retained launcher
  passed 235 tests.
- The immutable PCIe2 v103 control remained byte-identical at SHA-256
  `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`:
  0 structural DRC, 0 unconnected, 0 route-blocking, 0 non-octilinear routes.
  This read-only control is not a new full fabrication signoff.
- Generic-core audit passed. The broader runtime inventory still reports 378
  inherited findings; this slice does not claim those are eliminated.
- Control evidence: `build/event-driven-atx-20260928-reconstruction-control/`.

Wave C is the real ATX integration test, using B's exact retained board via
`--continue-suite`. Do not claim an ATX gain until its committed native output
and rollback/acceptance receipt have been inspected.
