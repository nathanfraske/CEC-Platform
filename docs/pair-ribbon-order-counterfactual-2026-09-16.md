# Pair proposal ordering: bounded negative result

Two simultaneous disposable probes tested whether short-pair ribbon proposals
were selecting excessive coupling at the cost of unnecessary length. Existing
legacy and octilinear candidate sets were retained and only their ordering was
changed in worker memory: preserve skew / coupling feasibility, then prefer
lower maximum member detour and total length before excess coupling. All native
collision, ownership, coupling, skew, detour and physical admission gates stayed
unchanged. No production script was edited.

Evidence: `build/pair-ribbon-cost-probe-20260916/report.json`; per-family full
evidence and bounded event witnesses are in that directory. The launcher is
`tmp/pair_ribbon_cost_probe_20260916.py`. Each worker had a 330-second deadline,
with an enclosing 420-second process limit and a 16 GiB disk floor. The event
list stops at 200 witnesses per worker: the displayed `reordered_domains` field
is the retained witness count, not the total number of altered domains.

| Input | Time | Prior priority failures | Result |
| --- | ---: | ---: | ---: |
| PCIe3 retained post-power / collateral-station diagnostic | 87.258 s | 11 | 11 |
| Current hash-bound 12VHPWR placement | 76.835 s | 1 | 1 |

The PCIe3 diagnostic is intentionally the same qualified-input counterfactual
used in the previous station investigation, **not** a newly adopted canonical
board. All six canonical source / hierarchy identities and the shared engine
signature remained unchanged. No geometry is promoted; this ordering prototype
is not integrated. Do not repeat this test or launch a full wave on its result.

## What the evidence distinguishes

PCIe3 CAN's final certificate reports no selected ribbon. Its accepted local
proposal instead came from `_joint_endpoint_escape`: six physically admitted
P paths and 32 N paths, with 192 paired combinations ranked by the existing
exact objective. The selected P member remains 6.905888 mm versus a 3.173128 mm
endpoint MST, or 2.176366x against the unchanged 2.0 limit. Merely reordering
ribbon proposals cannot shorten a path selected by that different search class.
This establishes a bounded-domain result, not global route impossibility.

VHP retains its USB flow-through access refusal. Prior independently measured
endpoint evidence already identifies locked back-copper obstruction beneath the
MCU escape; changing candidate preference does not give a through via permission
to ignore it. The previous process-floor and inline-reservation counterfactuals
must not be repeated or weakened.

## Separate read-only ownership lead

The current PCIe2 final-completion certificate identifies an obstructed local
soft-start escape at the regulator. Among its native blockers is a 0.9 mm GND
via plus its short return track. Both UUIDs occur in the existing hash-bound
local-cell producer screen as generated members of the regulator's bypass cell:

- producer evidence: `build/local-cell-producer-lineage-screen-20260915.json`
- current refusal: `build/station-eviction-suite-20260916/pcie-8pin-2port/04-route/oracle.json`
  under `completion_report.final_completion.refused_details`

The old screen compared an earlier ancestor, not today's canonical file. It is
a concrete provenance lead only. Next ownership work must rebind the **complete
cell**, all reused/shared dependencies and current source geometry, then test
atomic reconstruction and independent requalification. Matching a via UUID is
not authorization to shrink it or delete its track. The ordinary return geometry
comes from the current GND netclass; a smaller off-pad barrel cannot be assumed
legal just because endpoint-only POFV is permitted. Preserve the high-current
buses, pair ownership, current policy and all unrelated copper.
