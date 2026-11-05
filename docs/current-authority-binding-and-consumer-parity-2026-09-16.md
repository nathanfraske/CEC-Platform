# Current authority binding and routing/FEM parity

## Root cause and reusable repair

The current-domain reader passed a board-family hint as the artifact path to
the thermal configuration adapter. For current 12VHPWR, the adapter could then
not see that `/SENSEP6_HI` was now `/FAN_12V`. The old reader discarded that
absent name before considering its declared J3-to-RS6 endpoints. It covered
15 of 16 configured paths. The thermal entry point normally reads the actual
artifact and already selected `/FAN_12V`; this was not proof that it had been
omitting that lane's heat.

`cec_current_binding.resolve` is a product-neutral native identity resolver
now shared by current-domain routing/signoff and the thermal solver. It:

- Prefers exact or unique hierarchical names; recovers an absent name only
  when complete declared source/sink connectivity identifies one native net.
- Rejects ambiguous names/nets, missing or duplicate required references,
  off-net required endpoints, conflicting overrides, and multiple current
  contracts mapped to one conductor. Currents are never silently overwritten
  or summed. Structured refusal evidence retains the configured identity.
- Distinguishes required terminals from alternative candidate banks. Both
  routing and thermal injection now select the bank members actually on the
  net. The latter previously read only `refs_src`/`refs_sink`, ignoring banks.
- Preserves physical injection-face restrictions and does not mutate caller
  configuration, any PCB geometry, electrical budgets, stackups or margins.
- Fails before a thermal field is allocated when current identity is invalid.
  The width checker no longer swallows a resolver failure and falls back to
  an empty current map.

Native net identity is **not** copper connectivity or a fabrication pass.
Unrouted or undersized paths still fail independent connectivity/width checks.

## Design-current provenance is separate from thermal scenario current

The existing lane thermal scenario is 8.33 A. The existing board-local route
design basis is 9.2 A with a 1.25 geometry factor. Neither was changed. A
renamed conductor must retain its declared design-rule identity as well as its
thermal scenario identity; otherwise the alias would fall back to 8.33 A for
route sizing. Configuration overrides now retain `design_current_net`, and
the generic current-contract consumer follows that explicit provenance.
Conflicting native/declared design contracts are refused rather than guessed.

The qualified VHP replay applies the same existing 2.239 mm outer-layer width
criterion to lane six as the other lanes. It also verifies that reading the
configuration by family hint or actual path produces identical routing widths.
There is no new current value, fan-load assumption or permission to reroute
the protected power buses.

## Evidence

`build/current-binding-qualified-suite-20260916/report.json`: four concurrent
native board-family checks, six source/hierarchy identities verified. VHP now
has all **16/16** configured domains; Hub retains 12, PCIe2 retains its three
explicit plus four inferred domains, PCIe3 its three plus six inferred domains.
Routing and thermal net/endpoint mappings agree on all four. EPS and ATX remain
explicitly interface-held, not untested passes. All sources are unchanged.

VHP's independent current-width check still refuses twelve force paths,
including the newly covered lane. PCIe2's width check passes; PCIe3 is still a
floorplan and its Kelvin placement refusal remains. No gate was weakened.

Synthetic tests cover aliases, candidate banks, hierarchy ambiguity, duplicate
or missing refs, load collisions, invalid currents, current-margin provenance,
and the production width-gate failure path. A real loaded-native thermal fixture
solves with both an exact name and a renamed name/candidate bank: temperature
arrays and Joule heat are identical, with nonzero injection and no dropped net.
This is a regression fixture, not thermal qualification of the production boards.

Final integration: **466 tests and four subtests pass**, 142.61 seconds,
`build/current-binding-complete-tests-20260916.log`. No skipped tests.
Protected PCIe2 control: `build/current-binding-qualified-control-20260916.json`;
exact comparison: `build/current-binding-control-comparison-20260916.json`.
The PCB hash, complete regression object and every probe are identical to the
preceding filtered-sense control. Only generalization metadata changes because
the new neutral resolver is added to the audited core; that core audit passes.
The protected control retains 0 DRC / 0 opens and its prior broader release
holds. This is not the current nine-open PCIe2 route being silently replaced.

## Continuation

Keep `build/route-finish-next-inputs-20260916.json` and its exact source hashes.
No full route wave, placement change, candidate promotion or new preview was
produced by this repair. The dashboard was reachable on 8090. The existing
15-minute suite review/repair heartbeat remains active and reads the suite
ledger. Do not rerun exhausted placement cohorts merely because intake proof
has changed. Next physical work remains priority/local-cell access recovery,
PCIe2's nine residual opens, and coupled EPS/ATX mating geometry; preserve
frozen buses and paired-interface authority. Review genuinely changed native
outputs before publishing new body-free previews.
