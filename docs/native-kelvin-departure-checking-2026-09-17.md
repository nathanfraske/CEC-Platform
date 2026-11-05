# Native Kelvin departure checking — 2026-09-17

## Independent production gate

`cec_constraints._chk_kelvin_inner` now calls the reusable, read-only
`cec_kelvin_departure.audit_pad_departures`. The old predicate accepted a
near-pad endpoint on the inward half even when the track then ran backwards
through the force pad. It also used a circumscribed distance envelope as input
contact. Neither proved the required electrical geometry.

The replacement uses native same-layer pad/track copper collision, bounded
boundary bisection and a storage-direction-independent departure vector. It
requires departure from the inward face along its normal, following the existing
owner tap-form ruling, not a new manufacturing allowance. Existing 0.1 mm inner
projection and 0.001 mm heading tolerance are retained. Internal pad segments do
not masquerade as departures; through-pad segments and unsupported pad shapes
or offsets fail closed when contacted.

Branch scope matters: remove the source pad and track portions contacting it
before finding which departures reach actual current-input pads. A separate
voltage-only branch does not inherit the Kelvin-input rule. If it rejoins a
sense tree outside the source, it does. Other native pads may bridge copper
pieces; an overlapping pad cannot silently reintroduce the removed force node.
Receipts retain exact exits, copper UUIDs, unreachable input UUIDs and native
contact paths to each reached input. No generator is called to justify its own
geometry. No board, reference or coordinate special case was added.

The existing topology adapter still selects two-terminal shunts and known
INA input functions; this slice does not claim universal part discovery or
filtered-input-resistor traversal. Missing thin contacts remain N/A in this
particular checker, not a board-level pass. Other connectivity, bypass, layer,
via and release gates remain mandatory. The registry's old claim that N/A can
never occur has been corrected to match measured behavior.

## Cross-board native replay

`build/kelvin-departure-production-cohort-20260917/report.json` contains the
concurrent read-only replay of all six canonical boards, the historical PCIe2
control and three rejected/private PCIe3 prefixes. Every source, hierarchy and
copper inventory is unchanged.

| Input | New checker result | Meaning |
|---|---|---|
| Current PCIe2, five-open continuation | Pass, four shunt terminals | Existing admitted Kelvin copper retained; still five opens overall |
| PCIe3 canonical placement | N/A, floorplan | Not routed; not a pass |
| Hub | N/A, no shunt/sense nets | No applicable direct Kelvin topology |
| 12VHPWR | N/A, no direct thin stub resolved | Existing filtered topology outside this adapter; no new qualification claim |
| EPS | N/A, floorplan | Interface ECO hold unchanged |
| ATX | Three present terminal trees pass | Two missing contacts are still absent; interface ECO hold unchanged |
| Historical PCIe2 archive | One newly exposed departure failure | Existing copper defect, not a geometry regression |

The earlier PCIe3 94-/96-item prefixes now independently fail the wrong exits.
The corrected 87-item prefix has one correctly departing tree, but does not
reach every required input; it correctly remains rejected. These are diagnostics,
not continuation inputs, and no preview/winner was promoted.

## Historical control finding — do not suppress or silently rebaseline

The historical zero-DRC/zero-open control contains two branches at RS1 pad 2.
One properly departs inward to U20.4. The other departs sideways to **U10.9,
INA238 IN-**, not its voltage-only input. The native source-cut graph proves:

`0476a856-ed3f-4fcf-a34c-f9016a01e26e` (sideways departure)
→ `e69c6c39-42c8-4639-b398-259e9a2df85a`
→ input pad `550616bd-ec0b-5372-9a0a-ecba6628eaeb`.

The track runs (30.9012, 26.27) to (26.0912, 26.27) mm while the pad's inward
normal is (0, -1). Actual native contact ends at approximately
(29.124454, 26.27) mm. Its 4.810 mm transverse displacement is not a perpendicular
launch. The other good branch cannot hide it.

`build/kelvin-departure-control-20260917/comparison.json` records the full
regression replay: board hash, board-regression result, score, route-quality and
fabrication probes all match the prior control. Only the constraint probe gains
`kelvin-sense-from-inner-pad`; no previous blocker changed or disappeared. It
remains zero counted DRC/zero opens and still fails broader release, now for one
additional verified reason. The archive was not edited and its result was not
waived. For future detector-parity comparisons use this current receipt while
retaining the older comparison as evidence of the intentionally stricter gate;
the old blanket `probes == old_probes` assertion should no longer be reported
as passing.

## Tests and continuation

`build/kelvin-departure-wide-tests-20260917.log`: **438 tests and two subtests
pass in 16.19 s**. This includes 53 tests in the new module, not 438 new tests.
Coverage includes saved/reloaded rotations, front/back faces, track reversal,
cap-only pad contact, real branches, wrong departures, near-input misses,
voltage-only exclusion, external reconnection, pad-mediated connectivity,
overlapping force-node rejection and production constraint invocation.
The 94-test focused run is a subset, not additive.
After adding the new module to the protected generic-core list, the final
generic-guard/departure run also passes 62 tests (overlapping coverage):
`build/kelvin-departure-final-guard-tests-20260917.log`.

Core generic audit still passes; the inherited full-pipeline audit still has
23 physical / 380 runtime issues. Source dimensions, power authority, current
budgets and manufacturing profiles were not changed. No routing worker remains
running; approximately 64 GiB remains free.
`build/kelvin-departure-final-audit-20260917.json` confirms the new module has
no selector findings and all six board/hierarchy identities still match.
The Windows-side dashboard GET at port 8090 returns 200.

Next bounded work is joint range/inward terminal-cell placement using measured
PCIe3 refusals, plus genuinely changed Hub/VHP escape geometry. Do not repeat
unchanged exhausted portal domains, erase Hub's 125-pose history or promote a
partially routed prefix. Canonical manifest remains
`build/additive-first-next-inputs-20260917.json`. EPS/ATX still await the same
coupled-interface decision; do not mutate one mating half or invent clearance.
