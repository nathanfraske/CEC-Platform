# Generic escape-cell reconstruction and native-lifetime repair

Date: 2026-09-04. Status: implemented and regression-tested; diagnostic
proposals only, not a fabrication release or a claim of full-pipeline closure.

## What changed

1. **Bounded whole-cell reconstruction.** `scripts/cec_escape_cell.py` follows
   connected narrow tracks outward from a failed via escape. It can absorb
   unlocked tracks and the supported, independently re-provable endpoint
   neckdown owner. It does not move pads, other vias, full-width trunks,
   authored locks, or unknown precision owners. The default window is 2 mm,
   with at most 24 mutable tracks and 128 retained proof primitives.
2. **Real local connectivity instead of one route per recorded contact.** The
   cut boundary includes track-body, pad, via, and unmatched endpoint contacts.
   Retained same-layer copper can prove that several anchors need only one
   replacement connection. Vias and pours cannot merge these proof islands;
   global ground connectivity is not accepted as a local return-path proof.
   Primitive/window overflow refuses the repair rather than truncating proof.
3. **Shorter legal neckdowns.** The shared guarded route helper can try no
   neckdown, then bounded shorter prefixes, before spending the entire existing
   escape allowance. It retains the original width, length cap, foreign-copper,
   future-pour, board-edge, octilinear, and independent endpoint-proof checks.
   Existing callers retain their prior behavior unless they opt in.
4. **Correct destruction and bounded workers.** Discarded tracks now use native
   `Delete`, not detach-for-reuse `Remove`. Search workers process at most eight
   seats each, then the supervisor resumes at the next untried seat. The total
   target/seat/wall budgets do not reset. Python tracebacks, native exit codes,
   and fatal-signal diagnostics are retained without being buried by repeated
   image-handler warnings. A nonzero worker exit is never accepted, even if it
   wrote a superficially successful response.

The actuator in `scripts/cec_dimension_repair.py` tries this fallback only
after a direct branch reconstruction is unroutable or fails its endpoint
proof. It still requires independent DRC/connectivity, constraint-identity,
assembly, route-quality, and fabrication nonregression before adoption.
Unknown owners and boundaries changed by earlier repairs are deferred. No
refdes, net-name, coordinate, or board-family selection was added to the core.
The existing full-pipeline dimension-repair stage invokes this actuator.

## Native failure: diagnosis and correction

The first extended replay exposed a genuine native lifetime defect, not a
placement refusal. A later load returned a bare `SwigPyObject`; process
cleanup could subsequently segfault. The first observed failure was at load
33, but reducing the batch reproduced it at load 9. **This is not an established
KiCad board-load limit.** Forty read-only loads worked, and keeping boards or
the runtime capsule alive did not correct the underlying reference imbalance.

A native debugger breakpoint on the SWIG capsule destructor and a mutation
prefix bisect isolated the loss to removal of the incident tracks. The local
KiCad 10 binding implements `Remove` by detaching an item and setting the
borrowed proxy's `thisown` flag. Its later Python-owned destruction consumed a
registry reference it did not own in this replay. These tracks were never
going to be reused. `Delete` instead destroys them through the native container
and clears the proxy pointer. The same refusal batch then finished normally,
with the registry reference count preserved.

This is fixed at the generic discard operation, not by adding extra registry
pins, ignoring exit failures, enlarging a board, or skipping a problematic net.
The synthetic regression exercises both ordinary and expanded cells, forces
routing refusal after deletion, repeats it eight times in a child process,
checks registry-reference balance, reloads a real BOARD, and checks that the
source family stayed byte-identical.

Diagnostic evidence is retained under `build/escape-cell-*`, particularly
`escape-cell-prefix-probe.log`, `escape-cell-gdb-origin.log`, and
`escape-cell-delete-lifecycle.log`. Initial crash runs are superseded by the
completed replay below. Other uses of `Remove` require an ownership audit:
detach-and-reattach operations must not be blindly changed to deletion.

## Measured board replay

Completed full-control replay: `build/escape-cell-pcie2-v4/report.json`.
Source: archived PCIe 2-port fab-review control
`build/board-archive/20260831T1619-pcie-8pin-2port-v113-zero-open-v43/board.kicad_pcb`.

| Metric | Archived control | Previous spatial slice | New completed replay |
| --- | ---: | ---: | ---: |
| Netclass dimension findings | 50 | 44 | 38 |
| Via/pad overlap findings | 7 | 5 | 2 |
| Structural DRC | 0 | 0 | 0 |
| Unconnected | 0 | 0 | 0 |
| Tracks | 615 | 628 | 612 |
| Vias | 226 | 226 | 226 |
| Route length, mm | 1242.073 | 1244.226 | 1245.030 |

The full replay completed in 77.024 seconds, tried 122 seats, and admitted
five via repairs: the prior two ordinary repairs plus **three cell repairs**.
The three cells reduced 8, 13, and 7 recorded anchors to 3, 3, and 1 proven
local islands respectively. The first two rebuilt 15 and 14 tracks. One later
target was safely deferred because the earlier reconstruction changed its
captured boundary. There was no worker failure or wall-budget exhaustion.

The final-code incremental replay,
`build/escape-cell-pcie2-incremental-final/report.json`, independently starts
from the previous slice's 44-finding proposal and confirms the same **44 to
38** result. It admits exactly the three additional cells in **53.322 seconds**
over 93 seats, with no worker failure, no new blocker categories, unchanged
source bytes, and zero DRC/opens. This separates the new slice's gain from the
two ordinary via repairs already credited to the previous slice.

Relative to the previous slice, dimension findings fell by 6 (13.6%) and
overlaps by 3 (60%). Relative to the archived control they fell by 12 and 5.
Route length increased only 0.804 mm relative to the previous proposal while
16 redundant/split track primitives were removed. This is a small local
repair, not a new full-board route.

The eight existing release-blocker categories remain. The existing one fab
acid-trap finding, five route-craft advisories, and nine non-octilinear track
findings remain unchanged. No new blocker category was introduced; admission
also checked individual dimension and assembly identities and detailed other
failures, rather than relying only on aggregate counts.

### Cross-board control

`build/escape-cell-hub-v2/report.json` replays the same code and independent
checks against the manifest's current Standard Hub candidate. The existing
normalizer clears its netclass-geometry blocker, but the spatial planner has
no eligible targets. Structural DRC stays **5**, unconnected stays **13**,
and the fab checker stays at four blocking DRC findings. No new constraint
blocker category appears. This is a negative-control/nonregression replay,
not proof of positive cell-repair portability or Hub closure. Renamed and
translated synthetic six-layer layouts provide the positive geometry tests.

Neither original was modified. Verified hashes:

- PCIe control: `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`
- Hub candidate: `769f20bed0f0735c7ad86dbc97c315e8333c7318d3e05ff065d84130ba6f67dc`

## Tests and remaining scope

`build/escape-cell-final-tests.log`: **657 tests passed, plus 11 subtests**,
in 77.05 seconds. The focused dimension/cell suite has 45 cases. Coverage
includes translated/renamed cells, exact area contacts, immutable ownership,
same-layer island proofs, plane/via exclusions, shortened neckdowns, refusal
rollback, native ownership lifetime, bounded search resumption, crash rejection,
source concurrency, full-pipeline invocation, routing, decoupling, dimensions,
fabrication profiles, and stage admission. Compilation and `git diff --check`
pass.

`build/escape-cell-generic-audit.json`: the declared generic core passes with
zero static product/refdes selectors. **Full-pipeline generic acceptance is
still false:** 23 inherited physical-engine selectors and 380 runtime
occurrences remain, now across 98 checked runtime modules.

Next bounded work should cover dependency-aware replanning of invalidated
local boundaries and reconstruction through additional explicitly supported
precision owners. It must preserve the same whole-cell proof and independent
admission, without unlocking arbitrary copper. Separately, audit permanent
discard versus detach/reuse at other native removal call sites. Current
evidence does not establish fabrication readiness, new thermal qualification,
mechanical qualification, or complete closure on any additional board family.
