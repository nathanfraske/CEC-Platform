# Hub residual routing: clearance, fair search, and frozen pour voids

## Verified improvement and scope

The verified Hub moves from **7 to 6 opens**, retaining **0 qualified
structural DRC violations**. It is still **not fabrication ready**. These
counts are pipeline-qualified structural counts, not a claim that raw KiCad
emits no messages; the raw/qualified distinction is detailed below.

Original seven-open authority:

`build/residual-union-20260925/hub-final-verified/final/incumbent/board.kicad_pcb`

SHA-256: `2d21dd744742287026209353f5ba0470556da9b7919cdb0d9653c4f1f7785ca1`.

Independently admitted six-open board:

`build/residual-clearance-20260925/hub-six-verified/final/incumbent/board.kicad_pcb`

SHA-256: `aa1a3a262ce5e7211589c80c98de7090fc3d6d635f5c0fa74a67b8a83bd572bd`.

The normal residual coordinator independently reproduced the same closure
on September 26, without an injected route or target. Its separately
verified output is
`build/residual-clearance-20260925/hub-coordinator-final-verified/final/incumbent/board.kicad_pcb`,
SHA-256 `edef0eaf86e226d14c9741362c9f016fef158ed8a2605c3130ff0f880b619962`.
The earlier six-open archive remains the displayed review checkpoint;
reproducing the same closure is not counted as a second repaired connection.

One 1.0 mm, 0.20 mm-wide ordinary trace closes U7_OV1. No existing copper,
functional component pose, outline, project/rule authority, or power-zone
declaration was changed. All **684 protected input copper items** and the
qualified USB/CAN pairs pass preservation. No formerly passing route-oracle
gate was lost. The ATX PCB and active Hub/ATX authority manifest remain
unchanged; this slice is not a new schematic, stack, thermal, or power-budget
qualification.

## Root causes and reusable repairs

### Fair negotiation scheduling and compact resume history

The negotiation planner already round-robined nets, but a subsequent global
priority sort undid that fairness. Multiple alternative cuts on the same
difficult rail could consume the lease before another net received a window.
The new schedule ranks net groups, then round-robins their windows.

Real completed negotiation searches now contribute bounded per-net visit
counts to the compact `route_search_history` payload used by the coordinator.
Startup/IPC failures do not count as sampled geometry. History is revision
scoped and bounded to 256 nets and 1,000,000 visits per net. Counts affect
ordering only, never clearance, eligibility, impossibility claims, or
placement/release authority. A window's surface/bridge variants remain a
bounded local portfolio.

The v64 coordinator replay took **715.279 s** and retained the original
seven-open incumbent. It is explicitly a plateau, not credited as routing
progress. It included a global-router fallback after the residual round;
it was not two successful residual rounds.

### Local filled/capped dogbone search

The existing independent fabrication validator allows a direct, bounded
SMD-owned filled/capped dogbone, but this bridge implementation offered its
small POFV geometry only at the pad centre. The new separate local tier uses
the existing **1.50 mm** ownership bound and profile geometry candidates.
It requires a live same-net SMD owner, one direct octilinear leg, all-layer
foreign-copper/hole/edge clearance and no partial pad overlap. It does not
offer a barrel smaller than its launch trace width. Ordinary remote/lattice
via minima are unchanged.

Planning and independent live reproof share the ownership predicate. The
search does not mutate copper. Native tests cover rotated/back-side cells,
loaded save/reload ownership, missing process authority, wrong net/layer,
partial overlaps, foreign copper on outer/inner layers, reserved pours,
same-net hole spacing, finite budgets and general bridge integration.

A legal small landing exists at one Hub SS endpoint, but neither the cheap
nor the 20-second-per-net deeper replay closed a complete net on this seven-
open intake. This feature is **not** credited with the measured 7 -> 6 gain.

### Existing pour-clearance voids, without cutting power copper

The decisive refusal was caused by an authored power-pour contour covering
space that was already empty in its actual saved copper fill. The ordinary
router correctly treats the contour as reserved; globally replacing that
obstacle with the filled polygon would be too permissive.

`cec_frozen_pour_void.py` therefore provides a deliberately narrow additive
case: a direct octilinear connection between two current same-net SMD lands,
within a parameterized 2.0 mm domain, using the declared width/clearance and
normal native foreign-object and edge checks. The whole trace plus its
clearance envelope must already miss every intersected protected fill.
Missing/empty fills fail closed. No general pour-avoidance guard is weakened.

Native DRC named the end of an existing resistor-attached track rather than
the resistor land. The existing bounded native-connected-island planner
supplies alternative anchors on those **same two components**; nearby
same-net pads are not assumed connected. Short certified pairs are tried
before distant ones instead of inheriting arbitrary native report order.

Before editing, a no-edit native refill must first preserve every protected
pour/layer's saved copper. Eligibility is rechecked against that refreshed
control. After adding the trace and save/refill, a second independent native
integer-polygon subtraction compares every protected pour/layer against the
control. Both transitions prove **zero lost polygons and zero lost area**
across all **20** entries, with zero geometric tolerance. This is stronger
than merely leaving the authored outlines alone. Normal whole-board DRC,
additive invariants, and the independent route oracle still determine
adoption. A failing no-edit control is refused, not accepted as a new baseline.

The production additive planner/search/admission path selected and closed
the target itself. No board name, component reference, measured coordinate,
net spelling or UUID is hard-coded into the production repair. Synthetic
tests also reject a 10 nm by 10 nm copper loss, an unfilled reservation,
non-octilinear geometry, stale pad coordinates and stricter clearance rules.

The first full coordinator replay (v66, **729.982 s**) retained seven opens:
its strict post-refill proof caught two tiny lost polygons totaling 8,230
square nanometres on an unrelated back-layer pour. The closure pour itself
lost no copper. This rejection remains recorded; no numerical allowance was
introduced. Separate no-edit refill controls and a copy replay reproduced
zero-loss fills. These observations identify refill-state sensitivity, but
do not establish the lower-level KiCad cause conclusively.

The explicit two-transition control above is revision
`2026-09-26-frozen-fill-control-v67`. A normal coordinator residual replay
with the production recipe and one 90-second repair round selected the
closure itself and admitted **7 -> 6**. Total invocation time was **125.933 s**,
including grading/admission overhead. This is a bounded residual replay,
not a new full placement-to-fabrication run or a like-for-like speed comparison
with the earlier runs that included a global-router fallback. Both exact
fill proofs passed, additive invariants passed, and independent final grading
found no gate regression. Tests also verify that no-edit control copper loss
is rejected rather than waived.

## Trace spacing and raw native accounting

`cec_trace_clearance.py` is an independent read-only exact integer/rational
audit of **different-net, same-layer straight traces**. It subtracts both
half-widths and uses the larger declared netclass clearance plus any caller
floor. It does not exempt pair names. Native DRC remains necessary for
custom rules, pads, vias, zones and arcs; this diagnostic is not a replacement
for release signoff or a new fabrication waiver.

The six-open candidate has **180,270** tested trace pairs. The active class
clearance is **0.200 mm**; the smallest geometric gap is
**0.199999927 mm**, a **0.073 nm** shortfall. There are 53 exact negative
margins, all below one KiCad database unit (1 nm), and **zero shortfalls of
1 nm or more**. Those same 53 boundary-rounding comparisons already existed
on the input; the new trace introduced none. The strict exact diagnostic
retains `audit_ok: false` rather than hiding those comparisons.

Raw native DRC reports **no trace-clearance or shorting violations**, and
the project has **no DRC exclusions**. It does still report these existing
structural rows, all handled by the established live geometry/profile
qualification logic:

| Raw category | Raw count | Retained qualified count |
|---|---:|---:|
| via diameter | 89 | 0 |
| annular width | 89 | 0 |
| copper-edge clearance | 24 | 0 |
| hole clearance | 4 | 0 |

Existing silkscreen/library messages also remain. No clearance rule,
profile minimum, exclusion list or qualifier was relaxed in this slice.
The dashboard badge and newly generated image headers now explicitly say
**qualified DRC** or **qualified structural DRC**. Older reports' shorthand
"0 DRC" must be read in that qualified sense, not as zero raw messages.

## Evidence, control and review

Evidence root: `build/residual-clearance-20260925/`.

- `frozen-void-connected-probe/result.json`: actual additive selection,
  7 -> 6 admission, zero-copper-loss proof and unchanged-source-family proof.
- `hub-six-verified/`: independent before/after grades, signoff, save hygiene,
  source identities and protected-prefix/placement/pair/power preservation.
- `controlled-residual-replay/`: v67 production coordinator selection and
  admission, including both exact 20-entry zero-loss controls.
- `hub-coordinator-final-verified/`: separate final regrade of the coordinator
  output: six opens, no lost passing gate, all 684 protected items preserved.
- `intake-clearance-accounted/`, `six-clearance/`, and `coordinator-clearance/`:
  independent gap results and complete native reports, including raw-to-
  qualified accounting. Both six-open outputs have the same spacing results.
- `local-bridge-probe/` and `local-bridge-deep/`: bounded unsuccessful
  complete-net probes; no claimed closure from a legal endpoint alone.
- `pcie-v67-control/`: fresh native replay of the PCIe two-port review
  source: **0 qualified structural violations / 0 opens**, native copper and
  input family unchanged, **11.649 s**. Its source SHA is
  `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
  The current oracle still flags its existing `pairs_ok` gate and the
  coordinator declines to resume it as a closed-board release. This control
  proves no connectivity/copper regression, not fresh fabrication approval.

The selected regression suite finished with **849 passed, four skipped,
eight subtests passed**, in **168.75 s** (`regression-v67.log`). The four
skips are opt-in minute-scale real-router fixtures; the Hub coordinator and
PCIe native replay above were executed separately. The v67-focused fill
control suite passed 180 tests. `git diff --check` was clean.

The hash-bound six-open review archive is
`20260925-hub-standard-rev2-checkpoint-continuation-aa1a3a262c`.
Both model-free images and all six native copper panels were served with
nonempty HTTP 200 responses from Windows. The live dashboard was restarted
through its existing service, and its corrected qualified-count label was
verified on port 8090.

Remaining open nets: +3V3, +5V_SYS, KVM_5V_IN, U11_OV1, U11_SS, USB_VBUS.
Existing courtyard-edge, injection/thermal, route-geometry/interference,
hardware and draft-source release blockers remain visible. This report does
not turn a routing checkpoint into a fab candidate.
