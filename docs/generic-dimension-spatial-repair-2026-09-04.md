# Bounded dimension-aware spatial repair — 2026-09-04

## Outcome

Implemented a product-neutral spatial actuator in `scripts/cec_dimension_repair.py`,
and wired it into `cec_full_pipeline._route_stage` before fabrication polish.
The immutable PCIe fab-review control and current 24-pin candidate were replayed
on copies. Neither source was edited or promoted. The pipeline code is changed;
these test proposals are **not new fab-review approvals**.

| Current-check metric | PCIe 2-port control → proposal | 24-pin candidate → proposal |
| --- | --- | --- |
| Netclass dimension findings | 50 → 44 | 4 → 0 |
| Unqualified same-net via/pad overlaps | 7 → 5 | 28 → 28 |
| Structural DRC | 0 → 0 | 27 → 27 |
| Unconnected | 0 → 0 | 97 → 97 |
| Via count | 226 → 226 | 187 → 187 |
| Copper route length | 1242.073 → 1244.226 mm | 2590.139 → 2590.139 mm |
| Independent fab blockers | 1 → 1 | 16 → 16 |

Of the PCIe dimension improvement, two findings are the previous slice's safe
track normalization (50 → 48). This new spatial actuator repairs two vias,
removing four more findings (48 → 44: diameter and drill are separate findings)
and two assembly overlaps. Both repaired vias now use 0.9/0.5 mm land/drill.
One relocation re-proves two bounded 0.4 mm endpoint tracks; no existing
netclass, process floor, or pin-escape limit was relaxed.

The 24-pin result is a negative-control replay for the new spatial actuator:
there were no refused via enlargements to repair. Its four pre-existing width
findings were cleared by normalization, not by the spatial solver. Therefore
this is not evidence of new spatial closure on the 24-pin board.

## Generic implementation

1. **Consume live dimension refusals.** The shared normalizer runs on a throwaway
   board as a classifier. Its blocked enlargement UUIDs are mapped back to the
   exact current artifact; unrelated safe normalization is not mixed into an
   individual spatial transaction.
2. **Capture the electrical boundary and ownership.** Record every endpoint
   branch, layer, width, pad contact, and nearby retained-track contact. A via
   can be connected by copper area even when no track ends at its center.
   Retained tracks are not moved: their nearby real endpoints become connection
   anchors. Remote contacts, arc contacts, zone-only stitches, plated-pad layer
   transitions, precision nets, and unsupported owners are explicitly deferred.
3. **Search with final dimensions.** Candidate seats come from actual pad
   envelopes and a bounded radial fallback. Exact pad/assembly shapes, foreign
   copper on all enabled layers, hole spacing, board edges, and future power
   reservations filter the seats. The self-via is excluded only from its own
   hole-spacing preview.
4. **Rebuild and re-prove.** Captured branches stay on their original layers.
   New tracks use orthogonal/45-degree geometry and the shared class/board
   contract. Supported endpoint-group membership is removed before rebuilding;
   replacements get membership only after the existing independent neckdown
   verifier passes. Unknown groups and authored locks are not unlocked. The
   actuator does not alter the project's existing rule text to grant a waiver.
5. **Admit transactionally.** Refill zones, then independently measure score,
   constraint, and fabrication evidence in isolated workers. Require a strict
   reduction in dimension-fault identities and no new dimension, assembly, or
   structural DRC identity. Preserve connectivity and pair/Kelvin gates, route
   quality counts, and fabrication checks. Existing unrelated constraint
   failures may disappear, but changed/new failure details are conservatively
   rejected. Analysis errors or incomplete dimension identities fail closed.
6. **Bound work and preserve authority.** Defaults are eight targets, 32 seats
   each, a 2 mm spatial radius, and a 120 s production wall budget (240 s maximum
   in the pipeline wrapper). A timeout terminates the worker process group.
   Temporary storage holds only a current/trial pair and is cleaned afterward.
   Source PCB and executable sidecar hashes are checked before atomic adoption;
   a concurrent source or authority edit prevents commit.

The route journal includes this actuator's implementation closure and enable/
wall-budget policy in its cache key. Its report is retained in both the route
stage result and `oracle.json`. `CEC_DIMENSION_REPAIR=0` explicitly disables
the stage; `CEC_DIMENSION_REPAIR_WALL_S` controls its bounded effort.

## Additional failure exposed and fixed

The replay runner accepted `--board-hint`, but originally propagated it only
to selected probes. Scoring/constraint descendants on anonymous copy paths
could omit the board's current-domain authority. The runner now exports the
explicit identity into **every** worker, overriding unrelated ambient identity.
The production actuator receives `cfg.board` explicitly too.

The first two new replay directories are superseded for outer-probe comparison
by **v3**. Their outer constraint summaries omitted the existing PCIe
`trace-width-high-current` blocker. The spatial actuator's internal admission
already inherited the correct identity and included that blocker; no candidate
was admitted by hiding it. The corrected v3 outer probes show all eight existing
PCIe release-blocker categories, including both undersized USB-power paths.

Constraint payloads now carry exact track/via UUIDs for dimension findings and
via + footprint + pad UUIDs for assembly overlaps. Counts remain available,
but a lower total cannot disguise a different via becoming nonconforming.

## Evidence and bounds of the result

Final experiment reports:

- `build/dimension-spatial-pcie2-v3/report.json`
- `build/dimension-spatial-atx-v3/report.json`
- `build/pcie2-fab-review-dimension-spatial-regression.json` — untouched control

The PCIe actuator tested **189 seats**, admitted two repairs, and stopped after
its finite candidate list. Other trials were refused: 167 land checks, one
unroutable branch, and 19 failed escape proofs. Failed proof details include the
existing 1.5 mm escape budget and fragment-count limit. These are diagnostic
requests for a larger, bounded owning-cell reconstruction—not permission to
inflate those limits or move a named reference by hand.

Batching seat probes in a warmed worker reduced measured actuator time from
79.189 s to 54.792 s (~31%) for the same 189 seats and two accepted repairs.
This is one replay comparison, not a controlled universal speedup benchmark.
Independent acceptance measurements remain isolated and unchanged.

**637 tests passed, plus 11 subtests**, in the final integration run:
`build/dimension-spatial-final-integration-tests.log`. The new synthetic suite
has 25 cases, including translated/renamed designs, three-layer incident
branches on a six-layer stack, locked-owner invalidation/reproof, failed-proof
rollback, mid-segment contacts, stale geometry and class authority, fault swaps,
worker hint propagation, batched bounded search, deadline cleanup, and concurrent
source-sidecar edits. Pipeline tests check invocation and persisted reporting.
Compilation and `git diff --check` also pass.

The new generic core has **zero static product/refdes selectors**. The audit
still reports 23 pre-existing physical-engine selectors and 380 runtime
selector occurrences across 97 modules. Full-pipeline generic acceptance
remains false; this slice does not relabel the inherited debt as solved.

Source hashes remain:

- PCIe: `d6bc7c2df081a5c9f8ec32da8586071464c5fe8ba8dc3383c17ffdcb809789ea`
- 24-pin: `8aab506082a449acceac53fc5752876f90e14e0ca2556a8110d1c1e20915301b`

No new thermal or mechanical qualification was performed. The remaining PCIe
release blockers include USB/pair geometry, interference, bypass placement,
current-path widths, assembly overlaps, dimensional debt, and sense-body/pour
placement. The next spatial slice should rebuild a bounded **whole escape cell**
when no individual via seat can satisfy its existing local proof, preserving
all fixed contacts and independently proving the replacement before adoption.
