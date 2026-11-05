# Explicit owned copper motion and recovered repair domains

## Generic implementation

A rigid support-cell move now transfers existing generated-item provenance
only after checking the complete native copper inventory. The new receipt
cannot spread to unrelated items or to the rest of a net. Positional permission
cannot change net, layer, width, drill, via span/per-layer diameters, item type
or lock policy. Electrical terminal identities must remain unchanged.

The certificate footprint worker snapshots before mutation, applies its
bounded declared move/removal set, verifies the inventory and then stages the
native PCB and updated receipt. A failed native save leaves both original files
alone. A failed receipt publication restores both original files byte-for-byte.
A changed input/receipt after capture refuses publication. Process interruption
between the two atomic renames leaves stale geometry fingerprints, not new
permission for the modified copper. Whole-board admission remains outside this
private producer transaction.

The route oracle's final provenance capture also retains a separately completed
owned-mutation receipt. It no longer silently erases the newly reissued geometry
just because that UUID existed in the continuation's original input. Unreceipted
edits still lose their claim. No electrical/physical rule was relaxed.

**528 tests pass in 141.10 s**, in
`build/owned-copper-motion-final-tests-20260917.log`. Positive native synthetic
tests cover the complete persisted-receipt -> locked three-segment group motion
-> renamed/continued producer path. Negative tests cover unrelated changes,
conductor-property changes, stale snapshots and both publication failure points.

## Concurrent native replay, not new routing candidates

`build/owned-copper-motion-replay-20260917/report.json` replays four current
families plus the two interface holds and the historical PCIe2 control. In one
**private, deliberately perturbed PCIe2 scope fixture**, an already proven
generated trace is moved 0.125 mm to verify the exact declaration/receipt/native
readback; every unrelated object and protected prefix stays exact. This fixture
is **not** an improving route, a placement candidate, a fabrication result or a
dashboard preview. The other families gain no producer authority. Failed native
saves preserve their exact PCB/receipt pairs.

All six canonical source/hierarchy identities and the pass engine remain exact;
the historical control's hash, full regression and probes match. No source or
candidate is promoted by this replay.

## Recovery of actual historical production lineage

The current PCIe2 producer chain was followed through explicit input/output
hashes and verified campaign journals, with one documented legacy source-hash
join. No modification-time selection or old schematic fallback was used.
Each before/after native electrical identity and object geometry is revalidated.
The walk is bounded and stops at an unsupported record; it does not invent the
missing ancestor or treat an empty board as the authored baseline.

- `build/recorded-route-ancestry-v2-20260917.json`: six exact links, ending at
  `build/local-pofv-auto-stage-20260914/board.kicad_pcb`.
- `build/recovered-route-lineage-v2-20260917/report.json`: private receipts
  recover **370 currently locked generated objects** in the unchanged current
  PCIe2 geometry. The final copy is `stage-06.kicad_pcb`, still the canonical
  SHA `10cf3682c1d7e5e62756733f4a6798fc51d818cf6a5c16d449a2ef41612ff0c9`.
  This is a provenance advance, not 370 new routes or permission to modify
  high-current/coupled copper. The remaining older locks are not reclassified.
- `build/recovered-repair-domain-v2-20260917.json`: native planning finds **one
  newly authorized via domain and one newly authorized branch-negotiation
  domain**. Both concern a generated detector-net obstacle to an open 3V3
  connection. The old single-obstacle footprint menu remains exhausted.

## Bounded constructive follow-up

`build/recovered-domain-transactions-20260917/` ran these **two new domains
concurrently** on separate exact-current PCIe2 copies. It did not replay the
old footprint menu or launch unchanged Hub/PCIe3 placement batches. Each uses
the existing guarded generic repair engine, protected copper/pair checks,
fresh whole-board scoring and, if changed, independent full physical checks.
The command runner is `tmp/recovered_domain_transactions_20260917.py`.

Both branches have **finished without adoption**. The branch negotiation took
51.548 s and logged two `blocked_net_search_timeout` results. The via branch
took 95.015 s: both native via re-seats completed, but each subsequent whole-net
completion exceeded its 45-s worker allowance. Neither is a proof of geometric
impossibility. Both final artifacts remain byte-identical to their current input
at **0 DRC / nine opens**; all six sources/hierarchies and the engine stayed
exact. No new board render or continuation was promoted.

The next specific issue to audit is the via repair's target handoff:
`plan_congestion_via_repairs` reads a binary endpoint certificate but emits only
the target net, via and direction data. `_attempt_congestion_via_relocation_impl`
then calls `_lastmile_worker` for the whole net. Unlike footprint relocation,
this path does not forward the exact certified pair to the first close attempt.
That loss of target scope is verified in code; whether it explains these
timeouts needs an exact-pair replay and better per-pair progress evidence.
Do not simply rerun the same 45-s whole-net attempts or mark them no-path.

The other five boards retain their current guards/holds. Keep
`build/frozen-priority-next-inputs-20260916.json` authoritative until an actual
improvement passes review. For further private tests of these newly proven
domains, carry the matching receipt from the recovered `stage-06` family;
its PCB geometry is exactly current, not a newer placement. Broader generic debt remains
23 physical / 380 runtime findings; no full generic/fab qualification is claimed.
