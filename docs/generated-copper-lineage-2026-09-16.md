# Durable generated-copper lineage across routing continuations

## Root cause and scope

Certificate repair formerly treated a locked object as pipeline-generated
only when its UUID was absent from the immediate authored baseline. A routed
continuation already contains earlier generated copper, so resetting that
baseline loses its provenance. Conversely, comparing against a different
board with disjoint UUIDs could incorrectly authorize every lock.

This is distinct from route quality: generated copper is still subject to
protected-power, coupled-pair, geometry and whole-board acceptance rules.

## Implemented

`cec_route_copper_lineage` records the **explicit before/after producer delta**
in a `.route-lineage.json` sidecar. It requires the same native electrical
terminal identities (footprint/pad UUIDs, refs, values, packages and pad nets).
An empty or unrelated baseline cannot supply ownership. The receipt records
input/output SHA-256 values, producer identity and exact item fingerprints.

Certificate repair now resolves surviving receipt members as well as a
matching explicit baseline. A rename or unrelated placement edit does not
erase genuine provenance. Changed net, geometry, layer, width, via span,
per-layer via diameter, drill, arc midpoint or electrical identity invalidates
the affected claim. Lock bits alone grant nothing. Corrupt/missing receipts
grant no additional authority. These are provenance receipts, not cached DRC
passes or fabrication certificates.

The route oracle records provenance before certificate repair and after final
copper finishing. The common artifact-family copier retains it, removes stale
destination-only permissions when copying a source without a receipt, and
source/measurement dependency signatures include the sidecar.

Conservative limit: a changed inherited UUID is **not automatically
reauthorized**. An explicit owned-mutation receipt is a remaining slice. A
native synthetic integration test demonstrates that a saved generation
receipt enables the correct locked three-segment rigid-cell move, preserves
unrelated authored copper, and then refuses to reuse its old geometry receipt.

## Current-suite replay: no new board closure

`build/route-copper-lineage-replay-v2-20260916/report.json` checks the four
current families concurrently, retains both coupled-interface holds, and
replays the historical PCIe2 control. All six canonical sources/hierarchies and
the frozen engine remain unchanged. Historical board hash, complete regression
and probes match exactly. No canonical sidecar is edited or new board promoted.

The known PCIe2 producer journal supplies an exact matching prior input; this
recovers **22 added, currently unlocked objects** into a private receipt.
It does **not** recover the 1,111 older locked items. Those require their real
earlier producer lineage. The other three families are identity/no-generation
controls and correctly gain no permission. No native current-board group move
or extra routing wave is claimed from this replay.

Read-only inventory also confirms the recipe PCB files cannot stand in for
these normalized continuation baselines: their native terminal identities
differ. This does not by itself prove the hierarchical schematics are stale;
normalization can regenerate native identities. The resolver correctly refuses
that shortcut rather than granting all current locks.

## Safe-frontier results

The separate Hub/PCIe3 continuation has **completed** in
`build/safe-frontier-continuation-20260916/report.json`:

| Board | New sampled poses | Result | Wall time |
| --- | ---: | --- | ---: |
| PCIe3 | 16, no revisits | Unchanged; eight priority refusals; four pair probes, no full finalist; remaining probes inconclusive under budget | 265.373 s |
| Hub | 32, no revisits | Unchanged; the same three craft blockers | 291.264 s |

Their latest matching ordering receipts now contain **48 / 77** recorded poses,
respectively (the Hub's earliest legacy history remains partial). Keep the
canonical `build/frozen-priority-next-inputs-20260916.json`; only copy these
receipts into future private work. Do not relaunch another identical placement
batch solely because a heartbeat fires, and do not show unchanged renders as
new board progress.

Next constructive work is the explicitly owned mutation/reconnection boundary
and recovery of actual earlier generated-copper lineage where available, or a
different measured physical proposal. Do not use blanket unlocks, fabricated
empty baselines, exhausted single-obstacle moves, or placement reconstruction
that strips unrelated routes. EPS/ATX still require a coupled mating solution.

## Validation

The final broad native regression passed **518 tests** in **140.75 s**, after
the owned-cell integration case, producer-digest validation and complete
via-diameter fingerprint. Evidence:
`build/route-copper-lineage-final-v2-tests-20260916.log`. The earlier 517-test
pass overlaps; counts are not additive. All native replay/test workers have
finished, and no unchanged placement batch was relaunched.
The final native suite replay is the v2 report above. Legacy generic debt
remains 23 physical / 380 runtime findings, with `release_ok=false` and
`full_pipeline_generic=false`.
