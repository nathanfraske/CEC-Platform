# Preserve routed work at the placement reconstruction boundary

## Reproduced failure, not an accepted board

The concurrent finite-frontier transaction produced a PCIe2 placement proposal
whose route forecast improved: blocked-access count 2 -> 1, then forecast
reservation crossings 39 -> 36. It did **not** improve the actual routed board.
Fresh physical measurement found three new decoupler return failures. Native
readback and final-PCB residual measurement explain why:

| Metric | Canonical input | Rejected private proposal |
| --- | ---: | ---: |
| Tracks/arcs/vias combined | 1,133 | 137 |
| Vias (included above) | 386 | 23 |
| Copper zones | 16 | 16 |
| Native unconnected items | 9 | 168 |
| Hard craft blockers | 0 | 3 |

The two local footprint changes did not physically create all those opens.
`_materialize_rehydrated_board` invoked schematic synchronization with
`--rip-all-copper`, retaining only its exact power/qualified-critical prefix.
The generic `allow_routed` permission had been incorrectly treated as authority
to discard everything outside that prefix. Re-materializing the baseline first
also made the proposal's relative craft comparison blind to lost existing
local returns. Protected-prefix equality was true, but it did not mean that
**all existing routed work** survived.

Evidence: `build/priority-frontier-suite-20260916/pcie-8pin-2port/forensic.json`,
`after-residual.json`, and `rebound-physical.json`. Rebinding source authority
does not clear the failures. No canonical source or historical fab-review
control was changed; no rejected result was promoted or published as progress.

## Generic fix and deliberate boundary

`cec_placement_route_prefix.rehydration_coverage` inventories every native
track/arc/via against the materializer's retained net set and individually owned
item UUIDs. Merely being locked is not permission to discard or retain an
unqualified signal. `allow_routed` still permits read-only pose/proposal
inspection; the candidate carries the coverage report.

Before any output copy, directory creation, native mutation or schematic-sync
subprocess, `_materialize_rehydrated_board` reloads the actual source and
requires complete coverage. Otherwise it raises a structured
`UnownedRoutedCopper` refusal. It checks fresh source contents, not just a
cached candidate flag. The priority adapter reports
`routed_copper_requires_owned_transaction` before spending trial compute.
No blanket copper-unlock or bypass option was added. A genuinely copper-free
placement and an entirely retained prefix can still be reconstructed.

Native current-cohort readback finds the same latent problem on 12VHPWR: **228
existing Kelvin trace objects across twelve IN nets** were outside the retained
materializer prefix. Its preceding proposal batch accepted no move, so the
canonical board did not lose them. The new early guard now protects that work.
Hub's 157 native routed objects are all retained; PCIe3 has no routed objects.
EPS/ATX keep their separate unadmitted paired-interface holds.

This is a safety/applicability repair, **not a connectivity improvement**. The
next constructive route-owner transaction must explicitly own the affected
component group and its connected local copper, preserve all unrelated copper,
reconnect that group's terminals, and pass fresh DRC/connectivity, exact power,
qualified-pair and decoupler checks before committing. A placement forecast is
not a replacement for that transaction.

## Validation

- Initial focused guard/route/ordering tests: 84 passed. Further regression
  exposed three legitimate read-only pose consumers and a test that explicitly
  expected ordinary copper stripping. Enforcement was moved to the destructive
  materialization boundary, while the priority adapter retains early refusal.
  The native test now asserts both in-place and new-output refusal are
  byte-preserving, while retaining its positive copper-free and locked-power
  cases.
- An older power-replan fixture also still supplied a two-field ranking key to
  a complete-schema comparison. The fixture now supplies the existing declared
  key width; no production ranking rule changed.
- `build/placement-copper-ownership-replay-v2-20260916/report.json` passes the
  actual loaded-native constructor, materializer and adapter boundaries on
  four current families, preserves the two interface holds, and reproduces
  historical PCIe2 hash, complete regression and all probes exactly. Rejected
  output files are never created. All six source/hierarchy identities and the
  frozen engine remain unchanged during replay.
- Broad final regression: **485 tests and 16 subtests pass in 138.98 s**, in
  `build/placement-copper-ownership-final-tests-20260916.log`. The earlier
  focused/ordering suites overlap this result; their counts are not additive.
  The generic core passes; broader
  pipeline legacy debt remains 23 physical / 380 runtime findings, with
  `full_pipeline_generic=false` and `release_ok=false`.
