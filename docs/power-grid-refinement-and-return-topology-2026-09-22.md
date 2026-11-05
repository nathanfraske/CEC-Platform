# Power-grid refinement and return-topology replay — 2026-09-22

Status: **generic engine repairs validated; Hub routing admission remains blocked**.
Follow-on to `prefreeze-local-pi-and-bridge-landings-2026-09-22.md`.
No protected placement, board outline, current budget, clearance, or release
threshold was changed. No repeated unattended wave was started.

## Implemented changes

1. **Requalify reused via-in-pad returns from native geometry.** A newly created
   qualified return was labelled `via-in-pad`, but an identical return loaded
   from the exact copper handoff became merely `covered`. The proximity checker
   consequently switched physical metrics at a stage boundary. Reuse now retains
   its action label and adds separately qualified topology, via identity, native
   land dimensions, and fabrication-profile evidence. Both sides of the board are
   supported. A nearby via, through-hole pad, blind via, foreign-net via, or
   unqualified fabrication profile cannot obtain this classification. No new
   copper or relaxed distance limit is needed for this correction.
2. **Bounded per-net power-grid refinement.** A failed over-under connection can
   retry at finer resolution while retaining all previously awarded prospective
   copper and via ledgers. Successful nets are not re-solved. The pre-freeze and
   post-priority production callers enable two refinement levels, with a 500,000
   grid-cell ceiling checked before allocating fine masks. Public primitive
   defaults remain opt-in. The original physical terminal escape distance and
   top-layer landing distance survive refinement; their cell counts no longer
   shrink the physical policy. Each reservation consumer uses its net's actual
   grid rather than interpreting fine coordinates against the base grid.
   Bridge refusals remain fatal after the finite budget, with serializable
   refinement evidence. Whole-board native fill/admission remains mandatory.
3. **Run native geometry regressions in WSL.** Three existing via/pad/large-barrel
   tests checked for a Docker marker in addition to native pcbnew availability.
   They were silently skipped in this functioning WSL installation. Their guard
   now checks the capability they actually use, and all three execute successfully.

Production changes are in `cec_decoupler_cell.py`, `cec_slab_pour.py`, and
`cec_synth_pipeline.py`; regressions are in `test_return_topology_replay.py`,
`test_power_grid_refinement.py`, and the existing `test_pour_plan.py`. No product,
reference-designator, or board-coordinate selector was added to those changes.

## What improved, and what did not

| Hub evidence | Protected prior partial composition | Normal refined solve | Reordered diagnostic |
| --- | ---: | ---: | ---: |
| Search-model power paths | 6/8 | 6/8 | 8/8 |
| Domains connected after exact fill | 6/8 | 6/8 | 7/8 |
| Structural DRC errors | 0 | 0 | 0 |
| Unconnected items | 202 | 202 | 201 |
| Entire requested power set admitted | No | No | No |
| Ordinary signal routing started | No | No | No |

The last column is **rejected diagnostic evidence, not an incumbent or a routing
winner**. It is not a seven-domain certificate obtained by waiving the eighth.
The original six-domain partial prefix and compact paired source manifest remain
the protected baselines. This slice does not claim a new routed/fab-ready board.

### Decoupling

The historical U4.3/C4 0.285 mm isolated-supply finding was caused by lost return
topology. Its qualified complete-loop excess is 0.189 mm against the unchanged
0.250 mm limit. The same corrected checker exposes a different real blocker:
U1.2/C36 has **0.650 mm complete-loop excess versus 0.250 mm**. It was not waived.
U1's other assigned cell, C11, measures 0.244 mm and passes that same rule.

Fresh native reload/re-audit is stable for **14 Hub cells and 25 ATX cells**, with
source PCB bytes unchanged. ATX's constructor-only probe still constructs all
25 assigned cells with no new non-deferred structural regression. This does not
qualify its complete power routing or substitute for final filled-plane checks.

### Power allocation and the exact failure stack

Uniformly refining the whole Hub was not an improvement: 0.4 mm lost an existing
domain, while 0.2 mm exchanged a previously connected port for another one.
Per-net refinement prevents that exchange, but did not itself close the two
missing domains against the already allocated copper.

An isolation probe then removed other *prospective* allocations, without saving
or promoting its output. The port domain could be searched at both resolutions;
the PSU domain could be searched at 0.2 mm with the original physical escape
allowance. Thus board area alone is not the demonstrated cause. Allocation
contention and endpoint realization must be addressed before enlarging it.

One further diagnostic changed only solve order: failed domains first, then
declared current descending. It found all eight paths without moving components
or losing the other domains in the search model. Exact fill exposed the gap:

1. The raster solver reports the PSU path found.
2. Real filled copper leaves U7 pad 2 disconnected from the U11 pad 1/8 component.
3. The existing guarded additive repair tries two local neckdown candidates.
4. Both are refused as `unqualified_generated_endpoint_neckdown`, specifically
   `no_full_width_throat` (reported 1.25 mm local neck, existing 1.5 mm length
   limit). Being short enough is insufficient without a qualified wide exit.
5. Exact admission refuses `protected_rail_open_after_exact_fill_and_guarded_repair`.

The solve-order override is **an experiment only**, not a production ordering
policy. It must not be integrated as an unchecked search-count optimization.
The next generic slice should combine bounded allocation negotiation with
pad-to-full-width landing validation before freeze, preserving the incumbent
unless complete exact admission succeeds. Separately, the remaining collective
MCU bypass-cell packing must improve without trading proximity for overlaps.

## Bounded full-pass result

One full Hub attempt completed source intake and stopped at placement admission.
Its craft pass generated a finite 1,274-proposal menu and evaluated eight new
proposals; none was admitted. The remaining blocker was U1.2/C36 above. The
record explicitly says the neighborhood is **not exhausted**; eight rejected
samples are not proof that placement is impossible. Placement stage time was
184.9 seconds, plus 15.8 seconds for intake. No automatic repeat was scheduled.

## Controls and mechanical preservation

- PCIe 2-port fresh replay retains **0 DRC errors, 0 unconnected items, passing
  fabrication and route-craft non-regression terms**, and identical control bytes.
  Its existing full-release findings remain: RS1 Kelvin departure geometry and
  CAN adjacent filled-ground coverage. Full release therefore still reports false.
- The declared Hub/ATX paired body/vent screen passes and all **18 contacts**
  register under the existing dead-bug transform. Physical sample, supplier and
  tolerance, cable/latch, thermal, bench hold-up, and fabrication qualifications
  remain open. No blanket mechanical/electrical qualification is claimed.
- The core generic-module audit passes. The historical full-pipeline generic
  audit remains false; these repairs do not relabel the entire legacy engine.
- Hub remains 84.49 × 72.2 mm; the compact ATX remains 78 × 95 mm. No source
  promotion, board enlargement, manual component move, commit, or push was made.

## Evidence

All current receipts are under `build/hub-atx-route-entry-20260922/`:

- `final-tests-v2.log`: **330 passed**, zero skipped, two dependency deprecation
  warnings, 147.01 seconds, on the final code.
- `final-logging-tests.log`: 72 focused tests including serializable bounded failure evidence.
- `hub-adaptive-power/probe.json`: normal refined solve and exact admission.
- `hub-return-replay.json`, `atx-return-replay.json`: stable native reload checks.
- `replayed-measurement/physical-recheck.json`: corrected proximity measurement.
- `atx-local-replay/report.json`: constructor-only ATX check.
- `allocation-forensic/counterfactual.json`: isolated-net diagnostic, not authority.
- `hub-contention-order/probe.json`: rejected whole-board reorder experiment.
- `hub-contention-order/exact-failures/trial-p8t6v464/exact-state.json`: complete
  exact connectivity and refused endpoint-repair evidence.
- `hub-full-pass/02-placement/board.placement.json`: full-pass placement blocker,
  proposal coverage, collision evidence and stop reason.
- `pair-validation/paired-progress-validation.json`: declared mechanical screen.
- `pcie2-regression-final.json`, `generalization.json`: control/audit results.

The prior report's U4 proximity result is historical. Its old
`hub-quantized-power/physical-recheck.json` was refreshed during this investigation
and now contains the corrected check; no old PCB or frozen state was changed.
The dedicated current measurement above is the unambiguous current receipt.

The dashboard contains the actual rejected exact-fill artifact, with model-free
top and bottom renders, explicit failed/non-release lineage, and no routing claim:

`http://localhost:8090/?id=20260922-hub-standard-rev2-power-contention-REJECTED-b0ff276e72`

Artifact SHA256: `b0ff276e72a299bee0112f8717f55319f5a1e36d3102bd8e97111fc265fc1cba`.
The Windows-side page and image requests return HTTP 200, and the live archive
catalog contains the exact ID and both render panels. The app opening request was
queued; HTTP/catalog checks, not that request, establish availability.

Protected input SHA256 values remain unchanged:

- Pair manifest: `dfbeccb8eca4331c53c92c95b77d82dea03d4d8f396effda2860ca1d99882463`.
- Hub v8: `cbfe6b6f1e105a001356bad4c5e730d527264ed26618965cfd4a5f55380cd1b7`.
- Compact ATX v3: `83799200c0dae6ddd158d66de1e43d548a34547bd59b8d29539d929ac3d7814b`.
- PCIe 2-port control: `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
