# Hub residual routing: live zone anchors and fixed-via movement domains

## Outcome

The admitted Hub remains at **6 opens and 0 pipeline-qualified structural DRC
violations**. This slice has **no accepted connectivity gain**. A scratch trial
reached five opens, but introduced two qualified structural violations; it was
rejected. Neither that trial nor any replacement board was published as the
reviewed candidate. The Hub is **not fabrication ready**.

Verified input:

`build/residual-clearance-20260925/hub-coordinator-final-verified/final/incumbent/board.kicad_pcb`

SHA-256: `edef0eaf86e226d14c9741362c9f016fef158ed8a2605c3130ff0f880b619962`.

The displayed, independently verified six-open checkpoint remains
[on the dashboard](http://localhost:8090/?id=20260925-hub-standard-rev2-checkpoint-continuation-aa1a3a262c).
Its SHA starts `aa1a3a262c`; it is the prior equivalent closure checkpoint,
not a newly improved output from this slice. Windows-side `/healthz` and the
exact archive ID were verified. No additional dashboard tab was opened.

Evidence below is under `build/residual-closure-20260926/`. Original source
board families were hash-checked and remained unchanged. No power copper,
trace-width rule, clearance rule, fabrication profile, schematic, or BOM was
relaxed or changed to obtain a lower error count.

## Generic changes

### 1. Native filled-zone endpoints

`scripts/cec_zone_endpoint.py` resolves a DRC zone endpoint against the actual
live UUID, net, enabled layer and filled polygon. An outline is not an
electrical attachment. Holes, unfilled zones, stale IDs, rule areas, invalid
coordinates and ambiguous layer claims are refused. A multilayer zone does
not become a fictitious plated layer transition. The result enters the
ordinary width/clearance-guarded route worker.

One Hub residual snapshot named a zone on `+5V_SYS`, which previously had no
supported endpoint resolver. Native DRC can instead name a track on the same
connected island after another load/fill; this is not claimed to explain all
failures on that net. The zone-only diagnostic replay happened to receive a
track witness and therefore exercised no zone target. Actual zone routing is
covered by front/back native synthetic fixtures, not claimed as a Hub closure.

### 2. Fund connected-island alternatives before the primary search expires

The exact-target worker now plans its existing, bounded native-connected-island
alternatives before starting the primary search. If alternatives exist and
the remaining lease permits them, the default split reserves half the time
for them. A primary timeout can now enter that portfolio, not just a quick
no-path result. Alternative trials share the remaining budget fairly.

These are anchors on the **same two native connected components**, not any
nearby pad bearing the same net name. Existing count/distance bounds and
whole-board admission remain. Timeout still means a bounded search refusal,
not proof that no route exists. Tests cover timeout/no-path, disconnected
third-island preservation, and invalid budget fractions.

### 3. Defer support movement by its own net, not unrelated work

The previous board-wide deferral Boolean allowed a retryable window on one
net to suppress every support-component transaction. The scheduler now
partitions existing certified support targets using related same-net windows
and revision-scoped retry history. Legacy targets without a net retain the
conservative behavior. Larger IC-owner moves keep their conservative order.

On the Hub this made the soft-start capacitor eligible while the three
supports with outstanding related route windows remained deferred. No new
component-motion authority was inferred from an unrelated route failure.

### 4. Preserve immutable local-via ownership during component movement

The v69 trial moved a capacitor and left its authored locked ground via in
place, as intended by the existing copper-ownership contract. The via was
smaller than ordinary project through-via limits and qualified only through
the existing local filled/capped-via policy. Moving its owner several
millimetres away destroyed that qualification. Both scratch candidates
closed the signal but failed native admission on the same barrel:

* `annular_width`: one new qualified violation;
* `via_diameter`: one new qualified violation.

The new `scripts/cec_fixed_pofv_mobility.py` derives a necessary movement
domain from **live, qualified, immutable pad-centred small vias**. A proposed
rigid component/companion move must preserve complete land containment or
the existing `LOCAL_POFV_REACH_MM = 1.50` bound. Rotations use native board
coordinates; large lands may retain containment beyond that centre-distance
bound. Ordinary legal vias and explicitly owned generated movable vias are
not assigned this immutable-barrel restriction.

The check runs before spending a native routing trial and again before the
move worker mutates geometry. Invalid poses do not consume the per-target
trial cap. Passing this filter is **not** a via qualification or a route:
actual copper reconnection, land overlap, DRC and all downstream gates still
have to pass. It does not yet model every non-pad-centred dogbone dependency.

On the real current Hub, a read-only replay of the normal generator produced
**144 poses: 143 rejected by the fixed-via domain and one remaining**. That
remaining pose was tried in the v70 normal coordinator and failed component
courtyard and protected-copper clearance checks. Specifically, its new pad
position conflicts with a stationary capacitor and an authored locked power
via. All 1,105 existing copper items remained unmodified in that scratch move.
No invalid trial was admitted.

The parent report formerly kept only attempted moves and dropped the finite
candidate frontier. Support, early-owner and late-owner sweeps now retain
the frontier, compact rejected poses and their reasons, including when no
pose reaches a trial. Large occupancy maps are not duplicated. This is
diagnostic evidence, not cross-revision retry or release authority.

### 5. Remove stale board identity from the diagnostic plotter

`scripts/cec_zoomplot.py` no longer hardcodes an EPS title or particular
component references. It labels the actual board filename and hash, defaults
to native open-pad references, uses available fonts, and paints the
provenance/key above any overlapping drawing geometry. A red pad means
**OPEN**, not a claim that its surrounding geometry is unrouteable. This is a
diagnostic drawing, not a complete six-layer fabrication viewer.

## Measured replays

| Replay | Work budget / elapsed | Admitted result |
| --- | --- | --- |
| Unchanged v67 normal coordinator | 240 s repair / 256.080 s invocation | 6 to 6 opens |
| Individually funded exact-target v68 diagnostic | 66.812 s total | 6 to 6 opens |
| Per-net support scheduler v69 normal coordinator | 240.045 s repair / 255.914 s invocation | 6 to 6; two five-open scratch trials rejected on via qualification |
| Fixed-via domain v70 normal coordinator | 180.045 s repair / 196.298 s invocation | 6 to 6; one remaining support pose rejected before routing |

These use different search budgets; the table is **not a routing speedup
claim**. The v70 round ended at the wall-budget boundary during later atomic
negotiation. It did not exhaust all possible routes or placements.

Machine-readable evidence:

* `coordinator-intake/result.json` and its residual repair report;
* `portfolio-probe/` for individually funded native pairs;
* `coordinator-v69/residual-resume/round-00/certificate-repair.json` for the
  rejected five-open moves and exact DRC identities;
* `coordinator-v70/result.json` and its residual repair report;
* `mobility-domain-v70.json` for the separately labelled **read-only** domain
  replay and all 143 proposal refusals. This supplements the v70 run made
  before the parent-report retention fix; it is not a second routing run.

## Independent spacing and cross-board control

`spacing-v70/summary.json` records a fresh check of **180,270 same-layer trace
pairs**. Native KiCad reports no clearance violation or short. The independent
exact-gap checker still reports **53 positive shortfalls below one nanometre**;
the minimum measured gap is **0.199999927 mm** against 0.20 mm. There are no
shortfalls of at least one nanometre. Its strict `audit_ok` remains **false**;
the findings were not suppressed or rounded into a pass.

Raw native structural messages are not zero: 89 via-diameter, 89 annular-width,
24 copper-edge and four hole-clearance messages are independently qualified
by the existing process/geometry policies. Native project DRC exclusions are
empty. Cosmetic/library messages also remain. Thus “0 qualified structural
DRC” must not be abbreviated to “all raw DRC clear.”

The separate PCIe two-port control was freshly graded and passed native
completion without mutation: **0 opens / 0 qualified structural DRC**, source
family and native copper unchanged, 11.594 s. Source SHA-256:
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
Evidence: `pcie-v70-control/native-control.json`. Its existing pair route-gate
failure remains reported; this is not a new fabrication qualification.

## Tests and next bounded step

The final v70 combined regression replay passed **870 tests, four skipped
opt-in fixtures, and eight subtests** in 163.52 s, including the parent
frontier-retention fix. It is recorded in `regression-v70-final.log`.
The final diagnostic-legend clarification also passed its two focused tests
and the plot was regenerated. Native Hub and PCIe runs above supplement,
rather than replace, the synthetic regression coverage.

The next change should make proposal generation intersect locked-via owner
domains with component/copper occupancy, including rotations about a fixed
pad anchor. Ranking a mostly invalid endpoint-centred pose list and then
replaying it is not useful additional compute. This should remain bounded
and geometry-driven, with no component-name or board-coordinate special case.

There is also an integration boundary to address explicitly before adopting
a moved functional component: `cec_route_checkpoint.preservation()` requires
functional placement unchanged in residual routing. A valid placement
repair needs an upstream placement-revalidation transaction and refreshed
authority, not a weakened additive checkpoint check. This was identified by
code inspection; it did **not** cause this pass's refusals, since no
DRC-clean moved candidate reached that downstream check.

Remaining open nets are `+3V3`, `+5V_SYS`, `/KVM_5V_IN`, `U11_OV1`, `U11_SS`,
and `/USB_VBUS` (the two U11 names use their full hierarchical power-sheet
paths in the native report). This slice does not qualify thermal behavior,
the mechanical stack, electrical budgets, or the remaining release gates.
