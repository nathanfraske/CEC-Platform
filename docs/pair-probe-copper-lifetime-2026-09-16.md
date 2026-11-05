# Opposite-member copper lifetime in local pair probes

## Generic defect and repair

`cec_precision_route._route_paired_stub` accepted a reusable package-shape cache
from the enclosing portal search, but also stored opposite-member **tracks and
vias** in that cache. The enclosing search emits and rolls back pair copper
between calls. An index from a previous call could therefore miss newly emitted
opposite-member copper, or retain ghost copper after rollback. In-place changes
to coordinates, width, net, layer or arc midpoint were also invisible.

The local solve now owns its own track/via shape indexes. Fixed package-pad and
foreign-copper indexes remain reusable under their existing immutable-package /
foreign-geometry contract. Each member's track index is still built once per
local solve, not once per path leg. Exact native clearance, pair spacing,
octilinearity, heading, topology and final DRC predicates are unchanged.

This is a physical search/admission correctness repair, with no board, component,
net-name or coordinate exception. It is **not established as the cause of the
current VHP, PCIe3 or Hub holds**. The production portal screen rolls back its
temporary transition field before fan-in screening; do not claim those field
probes alone populated a ghost index. The vulnerable boundary is reuse of
opposite-member copper across distinct local solves with different live copper.

## Loaded-native negative controls

`tests/test_pair_probe_cache_lifetime.py` tests addition, removal, motion, width
growth, net change, layer change, arc-midpoint change and through-via movement.
Each case uses renamed nets, translated/rotated geometry and front, back or
internal copper. A warm-up probe creates the shared-cache state; the board is
edited, then its next probe is compared with a fresh exact native guard.

All **24 loaded-native cases** agree after the fix. Reinstating the old shared
track cache in isolated function memory reproduces a stale clearance result in
every case. Rollback uses the existing native lifetime helper; source bytes are
unchanged. Cases include both false acceptance and false refusal.

The combined suite passes **177 tests and two subtests** in 13.34 seconds:
`build/pair-cache-lifetime-final-tests-20260916.log`. It includes current pair
flow-through, ribbon, physical-prefilter and generalization coverage.

## Current-source concurrent replay

`build/pair-cache-lifetime-suite-20260916/report.json` compares old/current local
cache behavior on the exact six-source plan
`build/route-finish-next-inputs-20260916.json`, with four isolated workers and
40-second selected-pair bounds. All source/hierarchy and engine hashes remain
unchanged. EPS and ATX retain their interface-ECO refusal before routing.

| Family | Old/current selected-pair outcome | Elapsed old / current |
| --- | --- | --- |
| Hub | pair passes; 38 generated items in private probe | 4.224 / 4.247 s |
| PCIe2 | existing pair retained; no new copper | 0.408 / 0.406 s |
| PCIe3 | 48 items emitted, but independent pair gate still fails | 4.039 / 4.047 s |
| 12VHPWR | pair refused and generated copper rolled back | 23.805 / 23.807 s |

These timings are one bounded experiment, not a speedup claim. Four independent
native old/current comparisons show **identical copper geometry, poses, DRC,
connectivity, tracks/vias, lengths, Kelvin and differential-pair score results**:
`build/pair-cache-lifetime-suite-20260916/native-comparison.json`.
No private diagnostic is promoted or published as a newly routed board.

Historical PCIe2 control bytes, complete `board_regression` and all `probes` are
identical to the preceding control; see
`build/pair-cache-lifetime-control-comparison-20260916.json`.
The declared generic core passes; existing broader release holds remain.

## Next physical work

No full wave is justified by unchanged board results in this replay. All workers
are complete; retain the same six-source plan and published reviews. The VHP
flow-through refusal remains on the second leg through its protector; native
witnesses identify MCU/package pads among blockers, and clear transition fields
alone have not yielded complete fan-ins. A distinct next search-domain study is
**obstacle-derived local fan-in bends**, not another portal-seat-only sweep or
larger unchanged wave. The current finite fan-in menu uses endpoint fractions
and fixed detour distances; any added geometry-derived candidates must preserve
all current native/whole-pair gates and first demonstrate actual reachability.
Other families retain their independent priority/craft/interface obligations.
