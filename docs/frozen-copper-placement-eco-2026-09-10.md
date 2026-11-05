# Frozen-copper placement ECO materialization

## Outcome and authority

Implemented the frozen-power materialization slice identified by the preceding
pair-portal/rotation investigation. The pipeline now retains approved locked
power copper while rebuilding mutable placement/routing candidates, rather
than deleting it, regenerating it, and only then discovering that it changed.

**The current BETA 12VHPWR is still not route-ready.** No candidate was promoted,
no placement was accepted, and no connections were gained in this slice.

- Authoritative input: `build/12vhpwr-pair-search-20260909/checkpoint/board.kicad_pcb`.
- SHA-256: `3a0deb439290e8b7646b1b736e2947d5c1a711d0b3e4f17b7919c0c5b3da0e28`.
- Native score remains **4 DRC / 228 opens / 415 tracks / 12 vias / 837.8186 mm**.
- All 12 hierarchy files and four authority controls still match prior hashes.
- Outline, priority buses, placement, mounting lands and source board are unchanged.

Read-only closeout evidence: `build/frozen-prefix-20260910/closeout.json`.
An unchanged image is deliberately not presented as a new board candidate.

## Reusable implementation

### Reject incompatible movement before expensive reconstruction

`scripts/cec_frozen_copper.py` provides a native, layer-aware geometry context
for selected nets' locked tracks/vias. It applies board/requested and project
netclass clearances, detects pads already anchored to retained conductors, and
checks proposed footprint poses against foreign fixed copper. It restores
temporary poses in a `finally` block and caches isolated result copies.

The placement repair path screens proposals before selecting its finite trial
set, then checks again after macro legalization. Reports retain proposed poses
and native conflict witnesses for deterministic reproduction. An attached
frozen interface cannot silently move; a previously unattached same-net pad
may establish a new contact. No board name, refdes or coordinate exception is
embedded in the new engine module; it is included in the generalization audit.

### Preserve the protected source of truth

The routed schematic synchronization accepts explicit `preserve_locked_nets`
(repeatable CLI `--preserve-locked-net`). Before mutating anything it rejects
incompatible pad assignments, package replacements, removed interfaces and new
schematic pad interfaces on the frozen nets. Every selected net must actually
have retained locked copper. The explicit no-preservation destructive mode is
unchanged.

Only mutable copper is stripped. Authored zone declarations survive, stale
fills are cleared, and native zone filling runs after placement and mutable
copper reconstruction. Blueprint stamping resolves unique hierarchical aliases
before excluding frozen nets. Force-lane/rail generators retain fully frozen
groups and explicitly refuse partially frozen groups; they do not silently
regenerate half a protected topology.

The existing exact geometry-prefix contract still checks the source and final
result. Net names or item counts alone are never used as the preservation
certificate. Materialization uses a sibling staging directory and promotes
matching sidecars first, then the PCB last, with atomic per-file replacement.
A materializer failure before promotion cannot overwrite an in-place incumbent.
This is not a multi-file atomic transaction; sidecar identity checks remain
necessary if promotion itself is interrupted.

### Scope limits

This early native screen is not full DRC, thermal, zone, hole, signal-integrity
or fabrication admission. Pad/package topology checks do not electrically
qualify changed component values or MPNs. Existing downstream checks remain
required. Deliberate power-topology replacement needs explicit authority; a
placement repair must not reshape the priority buses to make room.

## Tests and native preservation proof

Two disjoint suites completed:

- **254 passed** in the frozen-copper, critical-route, blueprint, force-rail,
  schematic-sync and placement-admission tests.
- **474 passed, 13 skipped, 2 subtests passed** in the full-pipeline,
  generalization, certificate-repair, placement-oracle, route-preflight,
  precision-flow-through and portal-feedback tests.

Total: **728 tests and two subtests passed; 13 skipped**. Logs:
`build/frozen-copper-native-complete-tests-20260910.log` and
`build/frozen-copper-broad-tests-20260910.log`.

New synthetic coverage includes front/back/inner-layer pad conflicts, THT/via
stack behavior, anchor immutability, same-net extensions, pose rollback, cache
isolation, alias-aware regeneration exclusion, selective versus destructive
sync, stale-interface refusal without writing, and failure after a materializer
has written its staging output. That last regression was demonstrated red
against direct in-place materialization before adding staging.

The final staged native baseline was saved and reloaded, then independently
checked:

- All **199** protected primitives survive exactly; no additional selected-net
  primitives appear.
- Native score equals the original baseline.
- Authored zone declarations are unchanged; the refilled dedicated ground
  planes pass the existing continuity/coverage audit.
- H1–H4 each retain all nine pad contacts to both dedicated GND planes: eight
  mount/plane records, 72 contact checks.

Evidence: `build/frozen-prefix-20260910/baseline-final.json` and `closeout.json`.
The PCIe two-port control remains byte-identical with **0 DRC / 0 opens**;
its complete measured score and eight pre-existing broader release blockers
are unchanged. This is a regression pass, not new unconditional fab approval.
Evidence: `build/frozen-prefix-pcie-regression-20260910.json`.

## Bounded production replay

The same source and one-round, 12-proposal, 90-second pair-budget repair was
replayed without power replanning. Up to two full finalists were allowed.

| Metric | Previous slice | This slice |
| --- | ---: | ---: |
| Selected proposals | 12 | 12 |
| Protected-power materialization failures | 8 | 0 |
| Reached exact critical-route probes | 4 | 9 |
| Improved critical-route key | 0 | 0 |
| Accepted candidates | 0 | 0 |
| Total wall time | 512.72 s | 368.27 s |
| Materialization wall-time subtotal | 288.47 s | 94.86 s |

This run used **28.2% less wall time** and performed more useful exact probes.
It is a single replay comparison, not a controlled benchmark: the existing
eligible-work pool used eight exact-probe workers instead of four. Aggregate
worker CPU time increased as more probes ran; this is not a claim of lower
total CPU consumption.

The native prefilter checked 933 proposals, rejected 102, and retained 831.
After selecting 12, two were rejected for fixed-copper conflicts introduced by
macro legalization and one failed courtyard legalization. All nine remaining
candidates reached exact routing; none improved the critical-route key.
No full finalist was evaluated, and the rejected replay output is byte-identical
to the source.

Evidence: `build/frozen-prefix-20260910/replay.json` and
`build/frozen-prefix-replay-20260910.log`. The bounded replay preceded the final
staging-only wrapper addition; that wrapper was subsequently verified by the
full tests and the final staged native baseline above. No second broad wave
was needed to validate the save-isolation change.

## Next bounded slice

Preservation failure is no longer consuming this candidate budget. The next
measured obstacles are the exact pair router:

- CAN_INT baseline detours exceed the 2x endpoint-MST limit (2.48x and 4.27x).
- CAN cannot construct a layered paired junction at its resistor station.
- USB exhausts the first flow-through-leg coupled-route deadline at the ESD
  escape. All nine alternatives still refuse three pairs, with four or six
  remaining critical edges.

The next work should isolate these junction/escape failures with exact replay
fixtures and bounded search diagnostics, then repair reusable topology/search
logic. Do not relax coupling, clearances, the protected-power contract or
candidate acceptance to manufacture an apparent connectivity improvement.
