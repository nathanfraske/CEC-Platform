# Endpoint-only process domain and inline reservation counterfactual

## Generic repair, not board closure

The precision endpoint fallback tried only the selected process's preferred
0.35 mm land / 0.25 mm drill. The shared fabrication policy already permits a
0.30 mm land / 0.20 mm drill as an endpoint-only alternative. Native inspection
shows the current narrow USB connector lands on Hub, PCIe3 and 12VHPWR contain
and clear that smaller geometry while rejecting the preferred land. This does
not authorize reducing ordinary signal or high-current via dimensions.

`cec_precision_route._route_coupled_endpoint_pofv` now consumes the same bounded
`local_pofv_geometry_candidates` policy as local decoupler construction. It
preserves the preferred attempt, then retries the process floor only after an
endpoint geometry refusal, before inner routing or return-field construction.
The failed attempt removes its new barrels before retrying. Actual inherited
barrels are reused by identity, never resized or duplicated. All native pad,
full-land, all-layer copper, hole-spacing and process checks still apply.
Both members use the same requested geometry and the original shared deadline.
An inner-route or return-field failure is not retried with smaller barrels.

Failure evidence now records actual pad-containment decisions and the native
via-spot blocker, instead of only saying that POFV is unqualified. Separately,
the four bounded ribbon witnesses retain their `reservation` predicate; it was
previously omitted from individual failing legs even though the solver used it.
There are no board, reference, coordinate or net-name exceptions.

## Measured current-board result

- `build/endpoint-pofv-domain-probe-20260916.json` checks exact loaded-native
  endpoint lands on four admitted families. EPS/ATX are refused at their
  unchanged interface-ECO gate, not counted as native passes.
- `build/endpoint-pofv-suite-20260916/report.json` compares preferred-only and
  current selected-USB routing in four isolated workers. 12VHPWR now gets past
  connector endpoint qualification in two layer attempts and reaches the
  actual inner-route search. That search still refuses. Its other leg still
  fails MCU all-layer via clearance. Pair completion remains false.
- Native MCU evidence identifies a **locked B.Cu power-path segment** under
  its USB endpoint. Both allowed POFV diameters fail that same physical test;
  smaller vias cannot make a through barrel ignore the back copper. This is
  evidence for off-pad escape/placement investigation, not permission to move
  that bus, use an undeclared blind via or claim global unroutability.
- Hub/PCIe2/PCIe3 retain their successful selected USB results. Independent
  scoring and per-net/layer copper comparison find **identical final geometry,
  poses, DRC, opens and pair/Kelvin results on all four comparisons**:
  `build/endpoint-pofv-suite-20260916/native-comparison.json`. PCIe2 retains
  0 DRC / 9 opens. Other partial diagnostics are not full-board routing results.
- No new candidate is promoted or published, and no duplicate full wave is
  justified. Canonical inputs remain `build/route-finish-next-inputs-20260916.json`.

## Rejected explanation: synthetic inline reservations alone

Before the repair, a private counterfactual removed only future-inline launch
hints while leaving native physical guards active. It used both routing orders
and the same time budget. VHP still failed both orders with no completed leg.
The experiment found extra locally accepted stubs, not a completed route.
Thus the hints are not the sole remaining blocker and their removal was **not
integrated**. Evidence: `build/inline-reservation-ablation-20260916/report.json`.
All six source/hierarchy signatures stayed unchanged; only four families were
admitted for the native experiment. Do not rerun this unchanged counterfactual.

## Validation

`build/endpoint-pofv-final-tests-20260916.log`: **244 passed and two subtests**,
14.91 seconds. Loaded-native fixtures cover renamed, translated, quarter-turned
front/back endpoints; old preferred-only refusal; process-floor success; full
land and foreign inner-copper negative cases; preferred fast-path retention;
deadline exhaustion; complete partial-via rollback; retained authored copper
and groups; save/reload; and inherited-barrel reuse without resize/duplication.
The geometry unit tests stub downstream routing/return construction explicitly;
they are not claims of native whole-board DRC or return-field signoff.

Historical PCIe2 PCB SHA, full regression object and all four probes remain
unchanged: `build/endpoint-pofv-control-comparison-20260916.json`. Core generality
passes with zero core findings; broader legacy release findings remain. An
initial synthetic back-layer fixture used a borrowed layer-set temporary and
aborted; retaining the native layer-set object corrected that test fixture.
The final passing tests above supersede that failed test run.

All native replay/control workers have completed. No shared production scripts
were edited during the cohort. No fixed bus, placement, schematic, load budget,
process definition or mechanical interface was modified. Roughly 66 GiB remains
free, above the 16-GiB floor. Next work should consume the exact fixed-copper
access dependency or advance the other independent board holds; no identical
full-wave retry is authorized by this unchanged board result.
