# Guarded endpoint roadmap prototype

September 16, 2026. This is a disposable solver prototype, not integrated
production routing, a new canonical board, or fabrication approval.

## Measured result

A bounded octilinear roadmap supplies legal paths that the fixed endpoint
template menu never enumerated. In a native priority measurement of canonical
PCIe3, the prototype reduces refused important routes from **11 to 10**:
the local CAN pair is no longer refused, while CAN_J1 and nine Kelvin routes
remain refused. There are zero additional route-quality refusals. Wall time
was **84.317 seconds**. Concurrent 12VHPWR remains **one refused priority
route**, in **76.904 seconds**. These are preflight results, not full-board
DRC/connectivity/fabrication admission or an accepted placement replacement.

The salient PCIe3 domain expands from three P / 27 N paths to seven / 30.
Of 210 combinations, 80 pass the tested local geometric, detour, skew and
coupling predicates. The selected proposal has:

- P length **4.276701 mm**, N length **3.097721 mm**;
- maximum member detour **1.113318x**, versus the template's **2.071166x**;
- local skew **1.178980 mm**;
- sampled coupled coverage **64.5%**, versus the rejected slide-only proposal's 0%.

The candidate is returned into the existing private native priority pipeline;
its resulting refused-pair list contains only CAN_J1. This goes beyond the
previous geometric-only slide result but does **not** establish independent
saved-board signoff. No changed board was promoted or published.

Receipt: `build/joint-escape-roadmap-probe-20260916/report.json`; detailed
events and priority evidence are in its per-board directories. All six
canonical input PCBs/hierarchies and the shared production engine were
hash-checked unchanged on completion. Both workers finished. Artifacts occupy
about 3.5 MiB; roughly 65 GiB remains free. Canonical continuation remains
`build/bound-return-next-inputs-20260916.json`.

## Prototype design and bounds

`tmp/endpoint_roadmap_prototype_20260916.py` is a parameterized proposal helper.
It searches eight-direction states from the exact source pad, with exact
octilinear end hooks to avoid snapping the destination. Native member clearance
is mandatory for every edge and again after chamfering. Optional opposite-
member paths add a coupling-proximity cost and an exact spacing guard; this
cost cannot waive clearance. Heading state excludes direction reversals.
Endpoints, native copper and all component placements remain fixed.

The diagnostic launcher `tmp/joint_escape_roadmap_probe_20260916.py` adds 0.4
and 0.2 mm roadmap candidates, then up to two opposite-member anchored
queries per member. Each query is bounded to 3,500 visits / three seconds;
each domain to 22 seconds and a four-domain per-board cap. Calls also obey
the existing router deadline. The source-bound two-worker run had a 440-second
job / 480-second outer limit and 16-GiB storage floor. No shared production
script was edited during the run.

This is sampled finite-domain search, not an unroutability proof, and has no
board, refdes, net-name or coordinate selector in the geometry helper. The
diagnostic selects real pairs from their native declarations. Complete local
candidate checks precede returning an alternative; the production pipeline's
unchanged whole-route checks still decide its qualification.

## Tests and limits

**Ten tests pass** in `build/joint-escape-roadmap-tests-20260916.log`, including
exact off-grid endpoints, deterministic bounded search, trapped source,
clearance after chamfer, opposite-member spacing, deadlines, translations,
rotations/reflection, and a saved/reloaded native KiCad foreign-copper fixture.
The fixture verifies that foreign copper is neither crossed nor modified.
Initial fixture setup exposed KiCad pruning an unused signal net and its LSET
constructor overload; adding real endpoint pads and using the repository's
`LSET().AddLayer` pattern fixed the fixture. Final tests pass with only the
existing KiCad SWIG deprecation warning.

Remaining work before production integration:

1. Scope the fallback to appropriate complete local-pair obligations; do not
   impose a whole-pair detour/coupling test on arbitrary unfinished portals.
2. Make search budgets explicit, preserve fast paths, validate all numeric
   inputs, and prevent duplicate search in an immutable solve. A cache must
   include guard/board geometry identity, not coordinates alone.
3. Preserve the existing full objective and all endpoint heading, gap, skew,
   clearance and native ownership checks; retain the incumbent on failure.
4. Simplify collinear grid runs only with exact requalification. Do not claim
   the raw prototype polylines are polished release routing.
5. Add production integration/native rollback tests, run the historical PCIe2
   control and cross-family physical replay, then measure the two current
   families again. Only an independently qualified full pass may establish a
   new board continuation or dashboard candidate.

No full cohort was restarted. Hub local-power dependencies and EPS/ATX coupled
interface holds remain separate; the prototype changes none of their policy,
power budgets, dimensions, mating geometry, or fixed buses.
