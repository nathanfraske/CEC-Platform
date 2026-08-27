# Route-aware placement and closure pipeline

Date: 2026-08-08  
Scope: generalized placement/routing infrastructure, exercised on the current
`beta/hub-standard-rev2` six-layer board.

The current end-to-end stage diagram, implementation coverage matrix, bypass
cell contract, and blocker-provenance contract live in
`docs/openroad-style-pcb-pipeline-coverage-2026-08-09.md`.

## Release rule

The new stages are advisory or candidate-generating until the ordinary physical
oracle accepts them. They never waive DRC, ratlines, pair quality, Kelvin
topology, trace/via geometry, decoupling, fabrication, or thermal gates.

An automatic copper repair is adopted only when all of these are true:

1. the repair is derived from an exact refusal certificate;
2. locked, pair, Kelvin/sense, plane-layer, and wide trunk copper is protected;
3. the post-repair `(unconnected, DRC)` tuple improves strictly;
4. Kelvin and differential-pair gates do not regress; and
5. the complete board is rescored in a fresh KiCad process.

## Implemented feature set

### Route-aware placement

- Every selected placement is materialized and checked for octilinear pin
  escape, BGA/array fanout feasibility, legal routing layers, ground reference,
  and negotiated capacity.
- The production wave prune uses a coarse-to-fine analysis by default. The
  coarse result can reject obviously bad candidates quickly, but only the fine
  result is authoritative.
- Placement ranking is legality first, then blocked fanout, blocked ordinary
  pins, unreachable connections, terminal-exempted capacity overuse, raw
  overuse, and finally the existing HPWL/RUDY/corridor proxies.
- Bounded local repair considers evidence-named blockers first. It tries a
  generalized 180-degree orientation swap and small deterministic shifts,
  carries owned bypass followers with their device, checks real courtyards and
  board edges, and refuses any move that worsens device-specific decoupling.
- Repair now runs for bounded rounds. Every accepted move is re-materialized so
  a newly exposed obstruction can drive the following round. The outer loop
  independently enforces a strictly decreasing full physical evidence key.

### Critical-first placement and routing

- Design intent can declare safety/control selectors that impedance and width
  cannot infer. Selectors resolve to one exact hierarchical PCB net; missing or
  ambiguous selectors fail closed.
- Placement ranking is tiered: coupled/high-speed pairs, declared critical
  controls, pin escape, power distribution, then residual connections. A
  blocked critical launch invokes bounded placement/orientation repair and is
  a hard pre-route rejection if it remains.
- The route sequence is executable, not metadata: deterministic precision
  pairs first, declared controls alone at elevated effort second, and broad
  residual routing only after both stages pass independent connectivity and
  structural-DRC checks.
- Reversible-connector A/B data lands and inline flow-through package lands are
  closed atomically before a pair may claim success. The pair is refused and
  rolled back unless locked copper physically owns every pad on both members.
- Ownership is cumulative across tier imports. Every previously owned net is
  re-locked, and its normalized copper geometry is fingerprinted before and
  after the new tier. A changed earlier route refuses the tier instead of
  silently handing damaged copper to the residual router.
- The CLI now enters the selected BETA placement policy before compiling the
  route recipe. Previously the recipe could be compiled with generic defaults
  and executed later under Hub environment flags, producing a plausible but
  internally inconsistent wave.

### Smart congestion router

- The negotiated router uses fixed integer costs and deterministic work
  ordering on CPU or CUDA.
- Legal layers are derived from the actual stackup. The Hub analysis uses
  `F.Cu`, `In2.Cu`, `In3.Cu`, and `B.Cu`; the two solid ground planes are not
  signal-routing layers.
- Per-iteration telemetry records active connections, chunks, unreachable
  connections, raw/effective overuse, the best iteration, improvement, and
  stall age. Trace publication is bounded to 64 rows.
- Optional plateau termination is deterministic and is used by preflight. It
  does not change the detailed Freerouting route unless explicitly enabled for
  that route.
- Per-layer reports distinguish raw terminal overlap from terminal-exempted
  routed-capacity overuse. This prevents THT/plane-connected pads from looking
  like required surface traces and prevents raw pad-field overlap from being
  misreported as a routing conflict.
- Coarse-to-fine reports state whether the levels agree. A coarse zero with a
  nonzero fine result is a visible false summit, never a pass waiver.

### Certificate-driven closure

- The last-mile router emits exact endpoint, layer, pad, via, and track blocker
  certificates when its bounded canonical/via/maze search fails.
- `cec_certificate_repair.py` ranks exact offending track UUIDs and performs
  isolated same-layer local surgery. It first tries one segment, then a bounded
  degree-two branch (`pin neck -> trunk -> pin neck`) and a multi-resolution
  maze/bridge fallback.
- Track width, clearance, pin neck, edge, and collision rules are preserved.
  Future-route endpoint corridors are reserved when feasible; if the hard
  reservation makes the existing blocker itself impossible to repair, that
  result is reported and the unreserved DRC-only repair may still be considered
  under the strict global acceptance rule.
- The production route oracle invokes this stage only for a structural DRC with
  refusal certificates. Unconnected-only boards feed placement/congestion
  learning rather than speculative copper surgery.
- pcbnew mutation, fill, and scoring run in fresh spawned processes to avoid
  stale SWIG proxies in long-lived workers.

### Rail-object ownership

- `Config.load()` imports the current BETA board contract for production
  route-swarm calls. The Hub no longer falls through to generic cable-board
  defaults.
- Placement `.pourplan.json` and `.railreport.json` sidecars follow every
  renamed board/workspace copy. Exact placement signatures remain mandatory.
- Explicit `placer_ask` and `rail_compiler` polygons survive unrelated changes
  to cable-only derivation flags; automatic pours are still recompiled when a
  geometry-relevant recipe changes.
- Short stable ask names resolve only to one unambiguous current hierarchical
  PCB net. The current Hub resolves all eight requests onto their full KiCad
  names; ambiguous suffixes fail closed.
- Reservation, DSN ownership, pickup synthesis, over-under realization, fill,
  and final scoring now consume one compiled plan. An explicit over-under ask
  is not rejected for lacking a bond before the lane and its vias exist.
- With reservation plus pickup construction active, every pad on a successfully
  reserved rail belongs to the rail object and is removed from the ordinary FR
  problem. A no-path rail removes no pins. This eliminates the former
  self-conflict where FR was asked to route power pads around their own frozen
  corridors.
- Temporary board cleanup includes the executable plan/report sidecars, so
  these correctness changes do not accumulate stale storage.

### Dashboard and reports

- The dashboard plots all six physical copper layers and a congestion panel for
  every legal routing layer.
- Archive analysis runs the same multi-resolution preflight used by placement.
  The congestion badge exposes effective overuse, best iteration, stall age,
  plateau state, and coarse/fine results.
- Reports preserve per-layer effective and raw capacity, hotspots, iteration
  trace, multiresolution authority/agreement, certificate attempts, accepted
  track UUIDs, metrics before/after, and wall time.

## Hub measurements

### Critical-first admission and ownership

The old wave-139 placement now fails preflight in about 5 seconds because U5
pad 4 (`GND`) has no legal critical launch. Before the hard gate, an equivalent
route consumed roughly five minutes before returning 22--26 opens. The fresh
`plain-dataflow-s0` placement has no critical pair refusal, no unresolved
critical selector, no critical blocked pad, and no modeled unreachable
connection. Its only blocked ordinary launch is U7 pad 5 (`U7_OV1`).

The fresh placement was then exercised through only the priority stages (the
large residual intentionally omitted):

| Stage | Wall time | Structural DRC | Unconnected | Physical result |
|---|---:|---:|---:|---|
| Precision USB pair | <1 s | 0 | 269 | 42 locked items; all A/B and ESD lands owned |
| Three declared controls | 5.4 s | 0 | 233 | 33 new locked items; all three controls complete |

The declared controls are `/BLACKOUT_SENSE`,
`/HOLD-UP + 3V3 REGULATOR/COMP_THRESH`, and `/PWR_FAIL_INT`. All five priority
nets (the two USB members plus the three controls) satisfy the full locked-pad
ownership predicate. The USB signature is byte-for-byte geometry-equivalent
across the control import: 42 items before and after, with every one still
locked. Differential-pair validation remains green.

This exercise also exposed and fixed a prior false positive. The old precision
pass selected only one of each USB-C reversible A/B data lands, so the pair
looked coupled while broad FR still had to add the other two connector legs.
Likewise, the staged importer only promised ownership by convention. The
precision stage now completes and verifies every physical pair pad, while the
staged importer enforces cumulative geometry and lock state.

A full diagnostic route from the fresh placement, started before those final
ownership fixes were loaded, reached 21 opens and one clearance error in
469.7 seconds. It is explicitly rejected as evidence of release quality: its
residual stage altered USB geometry. It remains useful only for locating the
next capacity problems around USB VBUS, U11, and the reserved rail corridors.

The corrected end-to-end orchestration was then run on the same placement. It
entered residual routing with **74 exact priority items on five fully owned
nets**. After eight FR passes, selected-board last-mile, and certificate repair,
it finished at 24 opens and two structural errors; Kelvin and differential-pair
gates pass, but the board is correctly rejected. Most importantly, the final
priority signature exactly equals the pre-residual signature, including 20
USB-DN items, 22 USB-DP items, and 32 control-route items. The broad router and
all post-processors changed none of them.

The numerically better pre-fix 21/1 result was therefore a false comparison: it
earned those numbers by letting the residual rewrite an incomplete USB pair.
The corrected 24/2 result is the first honest full-route baseline for this
placement. Its remaining failures are concentrated in USB VBUS and the U11/
PSU-5V-KVM area, two dangling vias, two foreign vias inside the laid
PSU-5V-KVM rail, and high-current +5VSB segments outside their own fill.

### Controlled certificate repair

Input: `build/route-aware-slice4/hub-s4011-owned-routed.kicad_pcb`

| State | Unconnected | Structural DRC | Kelvin | Diff pair | Vias |
|---|---:|---:|---|---|---:|
| Earlier controlled candidate | 14 | 2 | pass | pass | 135 |
| Route-aware placement candidate | 13 | 1 | pass | pass | 136 |
| Certificate-repaired candidate | 13 | 0 | pass | pass | 136 |

The accepted repair removed the exact `/USB_VBUS` offender plus its two narrow
neck segments and replaced three segments with six guarded canonical segments.
It added no vias. The two pin escapes are 0.2998 mm wide and 1.5 mm long. Total
local source length increased by 1.2 mm; the full-board DRC improved from one to
zero without changing the unconnected count.

`/MCU + USB SERVICE PORT/USB_CC1` remains refused. Its refreshed certificate
shows the connector pin field, the routed USB pair, VBUS breakout, and the R9
ground pad as the local topology. This is now classified as a placement/breakout
ordering problem, not a reason to force an illegal final trace.

### Coarse-to-fine capacity

Input: the same seed-4011 placed board, grid 1.5 mm then 0.75 mm.

| Level | Wall time | Best iteration | Effective overuse | Outside pin escapes |
|---|---:|---:|---:|---:|
| Coarse 1.5 mm | 1.53 s | 4 | 0 | 0 |
| Fine 0.75 mm | 38.13 s | 6 | 164 | 143 |

The levels explicitly disagree. Fine-grid effective overuse by layer is:

| Layer | Effective | Raw | Overused cells |
|---|---:|---:|---:|
| F.Cu | 48 | 168 | 48 |
| In2.Cu | 25 | 25 | 25 |
| In3.Cu | 18 | 18 | 18 |
| B.Cu | 73 | 73 | 71 |

The raw top-copper bias is real, but after terminal exemptions B.Cu is the
largest capacity contributor. The fine trace improved from 392 at iteration 1
to 172 at iteration 2 and 164 at iteration 6, then oscillated to 181/188. That
distinguishes useful convergence from a plateau.

### Production route exercise

The current-BETA hierarchical fixture was exercised through four controlled
single-seed production routes. These are A/B stages, not cherry-picked release
claims:

| Production slice | FR time | Final unconnected | Structural DRC | Rail result |
|---|---:|---:|---:|---|
| Current recipe, compiled plan accidentally absent | 189.1 s | 8 | 0 | no planned zones; four power nets remain |
| All asks restored, but pre-bond circularly drops three | 397.9 s | 22 | 3 | reserved capacity not fully realized; rejected |
| Reservation + corrected rail ownership | 243.0 s | 16 | 1 | all 8 searches realized; zero pour incursion; independent topology still fails |
| Same rails synthesized only after signal route | 186.4 s | 14 | 6 | 5 foreign tracks + 1 via inside laid rails; rejected |

The failed middle slice was useful: it proved that restoring sidecars without
fixing ownership can make a router worse. It reserved 486 corridor rectangles
but excluded only seven pads, then dropped +5VSB, +5V_HOLD, and PSU_5V_KVM
before lane synthesis. The corrected contract excludes 51 pads only after all
eight searches succeed, defers all eight explicit asks to lane synthesis, and
realizes nine lane segments with one bridge via. Every configured Hub rail is
absent from the corrected KiCad residual list. That is not treated as final
electrical proof: the archive current-injection audit still finds +5V_SYS and
VCC_P2 on disconnected copper islands, and cannot resolve source/sink terminals
for +5V_HOLD. The implementation therefore reports the search as realized but
keeps the board failed on independent end-to-end rail validation.

The corrected reserved route is still not a release board. Its residual is 16
ratlines across 13 signal nets (including `/USB_VBUS` x4) plus one structural
clearance error. The stronger USB gate also catches 53.23 mm skew, asymmetric
layer/via use, an In3 segment without an adjacent ground reference, missing
return vias, and 6.4% coupled coverage. U7.1 remains 9.79 mm from its nearest
owned bypass capacitor. These are placement/breakout constraints on this
fixture; the rail-object implementation must not hide them by overlapping a
post-route pour.

The earlier generic route-swarm control had 21 unconnected. Loading the actual
current-BETA recipe plus bounded last-mile repair reduced that to 8/0 when the
rail plan was absent. The complete rail contract trades that false electrical
summit for honest power ownership at 16/1. Release remains withheld in every
production slice.

## Runtime and storage policy

- Wide placement candidates use the host CPU concurrently; pcbnew work uses
  spawn isolation.
- CUDA is selected only beyond the measured crossover. At the Hub's 0.75 mm
  work size CPU is faster; larger grids use the deterministic integer CUDA
  backend.
- Preflight artifacts are compact JSON plus one PNG. Candidate materialization
  and mutation trials live in temporary directories and are deleted on exit.
- Dashboard archives only selected review candidates. No wave duplicates,
  Freerouting logs, or dense grid tensors are retained in the repository.

## Verification

- Focused generalized + Hub regression suite: **307 passed, 17 skipped**.
- All changed Python modules compile with `python3 -m py_compile`.
- `git diff --check` is clean for the implementation, tests, and this report.
- Dashboard service responds on `http://localhost:8090/`; the controlled 13/0
  candidate archive contains the 3D render, congestion map, current/thermal
  plots, and F/In1/In2/In3/In4/B copper panels.
- Every production experiment ran through the ordinary release conjunction and
  was withheld; no test or A/B result promoted a dirty PCB.

## Next engineering targets

1. Feed the 486-rectangle rail reservation into placement reranking. The rail
   implementation now works, but the selected placement was optimized without
   paying for its real surface landings and signal escape loss.
2. Correct the U7 bypass placement at source; routing cannot repair a 9.79 mm
   device-decoupler ownership violation or its remaining clearance conflict.
3. Add a mixed scheduling policy only when it can prove both outcomes: reserve
   high-current trunks first, but permit an already-routed low-current branch
   to suppress a redundant lane. The post-route-only A/B is explicitly unsafe.
4. Promote current-injection completeness to a direct rail-object adoption
   gate, not merely an archive/thermal failure, so a path-found lane with
   disconnected source/sink islands is rejected before candidate ranking.
5. Use the measured plateau trace in the route-effort allocator. A candidate
   should earn later passes only when telemetry or fine-grid capacity predicts
   useful progress.
6. Make post-route rail/via cleanup consume the same foreign-copper admission
   map as rail pathfinding. The corrected full route still placed two foreign
   vias inside the PSU-5V-KVM rail and left two dangling vias after zone reap.

## 2026-08-09 generalized closure slices

The next implementation pass moved the Hub-only lessons into declarative and
board-agnostic pipeline boundaries:

- `pipeline-policy.json` is now loaded by placement, preflight, waves, the
  dashboard, and the unattended controller. Critical control nets and complete
  current-injection admission no longer depend on which entry point ran.
- completion/refusal certificates now become bounded rotation, escape-ray, and
  blocker-relief placement proposals. Their coordinates are evidence, never
  hard-coded board policy; exact materialization remains authoritative.
- outline compaction is compact-first but ranks legality and route capacity
  ahead of area, with geometrically distinct larger fallbacks.
- the plateau controller has a finite family ladder (seed diversity,
  certificate repair, smaller outlines, broader shortlist, precision effort)
  and an explicit exhausted stop.
- staged critical routing now compiles locked copper, reservations, and
  fiducial working fields into one fail-closed obstacle set. This fixed the
  measured PWR_FAIL_INT-to-FID3 structural regression.
- protected-copper reconciliation is transactional. Any increase in ratlines
  or structural DRC restores the pre-reconcile board byte stream.
- board-edge guards are continuous by default. The legacy connector-body-sized
  access window is opt-in because it let unrelated tracks run parallel to the
  edge under an overhanging connector.
- decoupler ownership and stranded functional parts are now placement-ranking
  terms and pre-route hard admissions. A finite evidence-directed repair moves
  only the measured capacitor/owner or part/electrical-neighbor relationship.

### Controlled current-Hub results

All measurements below use the current hierarchical BETA source, the same
86 x 74 mm outline, and seed 4011.

| Slice | Before | After | Interpretation |
|---|---:|---:|---|
| Shared critical policy, residual capacity | 248 | 227 | 8.5% fewer residual overuse units |
| Shared critical policy, protected connections | 8 | 17 | all three declared controls now reserve capacity |
| Certificate placement repair | 1 blocked critical launch | 0 | C22 accepted at 180 degrees; other evidence unchanged |
| Electrical craft repair | 1 bypass + 1 stranded | 0 + 0 | C1 rejoined RJ_HOLD; C15 reseated at U7 |
| Craft repair future overflow | 40,300 | 40,300 | no route-capacity regression |
| Craft repair future critical conflicts | 52 | 52 | no critical-corridor regression |

The electrical craft key improved from `(0, 1, 1, 6.908, 25.853)` to
`(0, 0, 0, 0, 0)` in two accepted rounds. The exact current artifact is under
`build/route-aware-slice7/craft-s4011/`.

The composed run under `build/route-aware-slice7/combined-s4011/` then accepted
C22 at 180 degrees while retaining the clean craft key. Critical blocked
launches improved 1 -> 0 and ordinary blocked launches 3 -> 2; future overflow
(40,300), critical corridor conflicts (52), expected vias (123), wire demand
(2,041,856), and residual overuse (12 escaped / 48 raw) were unchanged.

The first deeper residual route was diagnostic only: it ended at 23
unconnected and 12 structural DRC. After the continuous edge guard and the
composed craft/certificate placement repair, the same controlled route ended
at **21 unconnected and one clearance DRC**. The ten perimeter-clearance errors
are gone, but connectivity-first ranking still keeps the retained
12-unconnected / 3-DRC incumbent. The new candidate is retained as evidence,
not promoted as a release board.

The staged critical-control tier itself passed after the fiducial fix. The
remaining completion certificates localize the plateau to connector escape
and dense local copper around USB-C, GND/power continuity, and CAN pair skew.
The protected-net reconciliation also proved its rollback contract in the live
route: removing two +5VSB, two PSU_5V_KVM, and ten +5V_HOLD segments would have
worsened 22/1 to 26/2, so the exact pre-reconcile board was restored. The new
craft gate rejects the formerly invalid placement in 2.6 seconds rather than
spending roughly seven minutes routing a candidate that cannot pass the final
conjunction.

Physical bottom rendering confirms the normal back-footprint transform already
mirrors the padless logo across Y and reads `CEC` correctly from the exposed
back. An additional mirror was rendered as an A/B and correctly rejected
because it makes the lettering backward.

Verification for these slices: **163 passed, 5 skipped** across the policy,
certificate, compaction, search, route-preflight, staged-routing, thermal,
dashboard, placement-craft, wave-prune, and flip-contract suites. All touched
Python modules compile.

## 2026-08-09 route finishing: chamfers and teardrops

Route finishing is now a general, transactional pipeline stage rather than a
Hub-specific cleanup. The search router remains Manhattan for speed, then the
finisher replaces only proven ordinary unlocked right-angle corners with short
45-degree chamfers. It skips pad/via launches, junctions, locked copper, wide
power trunks, coupled pairs, Kelvin nets, declared critical controls, and any
change that fails exact edge or foreign-copper clearance. Whole-board scoring
restores the original byte stream if connectivity, the unconnected-net set,
DRC, Kelvin topology, or differential-pair quality regresses.

On the current Hub diagnostic route the finisher recognized 63 right-angle
corners and safely chamfered 36. Connectivity and DRC remained exactly 21/1;
Kelvin and pair gates remained true. The result is retained at
`build/route-aware-slice7/hub-combined-routed-chamfered.kicad_pcb` as measured
evidence, not as a release candidate.

Modern KiCad teardrop metadata is now audited and enabled by the same route
oracle. The conservative default targets mechanically useful PTH and ordinary
through-via transitions where an actual same-net track terminates on a
materially larger land. SMD teardrops are opt-in, and coupled pairs, Kelvin,
12 V/high-current, locked, and declared critical nets are excluded. Automatic
enablement is `release` mode: candidates are always audited, but copper is only
changed after zero unconnected and zero DRC.

Current-line authored/routed copper audit:

| Board | Conservative targets | Breakdown | Already enabled |
|---|---:|---:|---:|
| 12VHPWR Standard | 105 | 11 PTH / 94 via | 0 |
| ATX24 output daughterboard | 14 | 14 PTH | 0 |
| Hub controlled route | 35 | 7 PTH / 28 via | 0 before A/B |
| Other current rev3/daughterboard PCBs | 0 | no eligible routed junctions yet | 0 |

The forced Hub A/B enabled all 35 conservative targets and persisted them in
`build/route-aware-slice7/hub-combined-routed-chamfered-teardrops.kicad_pcb`.
The transaction preserved 21 unconnected, one DRC, Kelvin true, and pair true.
This validates the mechanism while the production `release` policy correctly
defers adoption until the board itself closes at 0/0.

The next pipeline slice should consume completion certificates as localized
negotiated rip-up windows. The present plateau is concentrated around USB-C
endpoint escape, CAN bundle reservation/skew, and power/GND island continuity;
another undirected global wave is less valuable than rerouting the blocking
local topology while preserving already accepted critical copper.

## 2026-08-09 localized negotiated rip-up

The certificate repair stage now performs an atomic target-first transaction:

1. rank only final, still-unconnected refusal certificates;
2. remove a bounded set of exact certificate-named, unlocked ordinary tracks;
3. route the refused net through the vacated local window;
4. restore every displaced branch with its original width and a bounded detour;
5. refill and admit only a whole-board structural improvement with no new
   unconnected net, DRC increase, Kelvin regression, or pair regression.

Locked copper, coupled pairs, Kelvin/sense geometry, plane layers, and wide
power trunks remain immutable. Overlapping certificate hits on the same
degree-2 branch are coalesced before removal. KiCad track removal, target
routing, and restoration execute in three fresh processes because the KiCad 9
SWIG containers become invalid after multiple removals in one interpreter.
Timeouts and worker errors return the original artifact instead of aborting an
unattended wave.

The original one-segment repairer tried 80 hypotheses in 162.988 seconds and
accepted none: 61 had no local path, 15 were neutral relocations rejected
before the target could claim the corridor, and four regressed connectivity.
The policy-equivalent negotiated run tried three complete windows in 52.123
seconds and accepted one. It coalesced three certificate hits into a five-track
+3V3 branch, closed one GND connection, then restored +3V3 with three tracks and
no vias. The Hub improved from **21 unconnected / 1 DRC** to **20 / 1**;
Kelvin and coupled-pair gates remained true.

A deliberately deeper second iteration on the accepted board reached a clean
plateau at 20/1. Two candidate transactions closed 5V_SYS_SENSE but made
TEMP_HUB newly unconnected and were rejected by the debt-swap gate. Two more
closed their target but could not restore every displaced branch. The remaining
USB refusals are dominated by fixed connector pads, shield lands, locked USB
pair copper, and power pours; this is placement/escape evidence rather than a
reason to allow broader blind rip-up.

Measured artifacts and reports are under `build/route-aware-slice8/`. The
accepted diagnostic board is `hub-negotiated-production.kicad_pcb`; it is not a
release promotion because it remains at 20 unconnected and one DRC.

## 2026-08-09 USB pseudo-stub and reviewer issue evidence

The short left-facing feature beside the Hub MCU was electrically connected,
not a dangling branch. It was a hairpin in the protected USB pair: the grid
router allowed a fractional-cell centerline backstep near a rotated endpoint,
then constant-offset mitering amplified that small reversal into a conspicuous
D- excursion. Precision escapes now select the shortest clear monotonic
candidate, and grid routes shortcut a reverse centerline kink only when the
complete pair envelope remains clear of board edges, keepouts, and foreign
copper. Any indispensable reversal is refused to the next routing tier.

Re-routing only the protected USB pair on the accepted negotiated board removed
the hairpin, reduced pair skew from **3.496 mm to 0.542 mm**, and reduced the two
members from 65.788/69.284 mm to 64.214/64.756 mm. The pair still reports 90-ohm
nominal/measured geometry, is fully locked and pad-owned through D6 and the
reversible USB-C lands, and preserves the board's **20 unconnected / 1 DRC**,
Kelvin true, and differential-pair true admission state. The diagnostic artifact
is `build/route-aware-slice8/hub-usb-monotonic-v3.kicad_pcb`.

The dashboard now produces an `issues.svg` panel from the exact same DRC JSON
used for its gate badges. Accepted structural DRC copper/loci are red,
unconnected copper/loci are amber, and implicated components are outlined in
magenta; the legend includes live counts. Whole affected nets are deliberately
faint while UUID-named offending items are strong, so a large GND net provides
ownership context without masking the actual gap. On the current Hub this maps
one structural +5V_SYS/C15 clearance error, 20 unconnected items across 17 nets,
and 24 implicated components.

## 2026-08-09 USB pseudo-stub forensic and closed-loop prevention

The defect was not introduced by the negotiated last-mile repair. A geometric
replay of every PCB in `build/route-aware-slice8/` found the same four
protected-net acute backtracks in `hub-cert-baseline.kicad_pcb`, every
negotiation/certificate derivative, and `hub-negotiated-production.kicad_pcb`.
The first successful monotonic reroute (`hub-usb-monotonic-v2.kicad_pcb`) is the
first artifact in that lineage with zero protected-net topology faults.

The historical logs did contain a related warning, but not the defect itself:
earlier waves repeatedly reported that the precision pair corridor was refused
and handed to the staged fallback router. Once a fallback or inherited board
had connected both USB nets, the ordinary score saw zero USB ratlines and no
foreign-net DRC. `high_speed_pair_summary()` also allowed 3.81 mm USB skew, so
the measured 3.496 mm mismatch remained inside that independent gate. The
fabrication cleanup was not a substitute: its `repair_backtracks()` recognizes
only duplicate/covered near-collinear segments and reported the same count on
the defective and corrected boards. No stage recorded acute-junction topology,
so the visual pseudo-stub had no machine-readable evidence to propagate.

The closed-loop correction has four layers:

1. `cec_precision_route` rejects non-monotonic pad escapes and reverse bends
   before copper is emitted.
2. `cec_route_quality` independently audits exact same-net/same-layer,
   degree-two track junctions. An opening below 89 degrees is a doubled-back
   route; geometry inside a duplicate-pad footprint is excluded so reversible
   USB-C and flow-through component closure is not false-flagged.
3. `cec_score` makes topology faults on Kelvin/USB/CAN pair nets hard pair-gate
   failures, prices ordinary-net faults in candidate ranking, and carries the
   full evidence into decision logs. `cec_precision_route` repeats the audit on
   only the copper created by that invocation and fails its admission contract
   before broad routing can protect malformed copper.
4. The dashboard Issue Map renders route-topology evidence in cyan alongside
   DRC, unconnected copper, and implicated components.

Forensic replay now gives the expected discriminator: the old production board
is `diffpair_ok=False` with four blocking topology faults; the corrected board
is `diffpair_ok=True` with zero blocking topology faults. Five ordinary-net
backtracks remain as ranked cleanup evidence.

The next repair audit exposed a second pipeline issue. Applying the previous
monolithic fabrication repair to the corrected Hub reduced ordinary route
artifacts from five to three but increased unconnected items from 20 to 21 due
to the zone-priority slice. Backtrack-only cleanup preserved 20 unconnected.
`repair_admitted()` now evaluates conservative and full repair slices on
isolated copies, re-scores each in a fresh process (avoiding KiCad SWIG registry
contamination), and publishes only a DRC/connectivity/pair/topology
non-regression winner. On the measured Hub it selects `copper_cleanup`, keeps
DRC/unconnected at 1/20, preserves both pair gates, rejects the regressive full
slice, and reduces ordinary topology findings from five to three.

## 2026-08-09 clean-sheet EPS pipeline trial

`eps-8pin-rev3` was selected as the smallest current BETA board that still
exercises six-layer placement, Kelvin ownership, USB/CAN pair routing, power
pours, fabrication cleanup, thermal analysis, publication, and dashboard
evidence.  Its source board begins with 48 footprints, no tracks/vias, seven
structural DRC findings, and 183 unconnected items.  The first complete run
generated six placements, pruned two, and attempted four.  Three candidates
were rejected at placement craft because the +5VSB/GND 10 uF bulk capacitor C6
was 24.4--43.0 mm from its nearest electrical neighbor.  The fourth reached
critical routing and was correctly rejected by the pair-physics gate.

That trial exposed three independent implementation faults rather than one
opaque end-state failure:

1. Two sense-monitor ICs can share one shunt terminal.  Kelvin synthesis
   independently emitted their common launch segment twice, yielding two exact
   duplicate and two fully covered protected-net stubs.  Synthesis now plans
   all segments, sorts longest-first, and prunes only fully collinear covered
   same-net/same-layer segments before copper emission.  On EPS the Kelvin
   result changed from 24 segments with four topology findings to 20 segments,
   four explicitly pruned, and zero topology findings.
2. The staged router allowed critical pairs on every ordinary routing layer.
   It therefore produced a connected USB pair on `In3.Cu`, whose declared role
   is PWR and which lacks an adjacent GND reference.  Pair-only tiers are now
   restricted to stackup-declared signal layers immediately adjacent to a
   dedicated GND plane: F.Cu, In2.Cu, and B.Cu for the EPS profile.
3. The initial enforcement passed KiCad canonical names such as `In3.Cu` into
   a DSN whose board-visible aliases were `PWR`, `GND`, `SIG2`, and `GND2`.
   The intended policy appeared in the report but the DSN mutation matched
   nothing.  The stage now translates canonical names to exported aliases,
   accepts quoted or bare DSN tokens, verifies every forbidden layer is marked
   power, and fails closed if the deck does not contain the asserted policy.

Refused USB and CAN pairs are also routed in separate sequential tiers, with
all prior precision copper re-locked and geometry-verified between tiers.  On
the same EPS placement this eliminated PWR-layer use and asymmetric USB layer
sets.  It did not paper over the remaining physical problems: USB has four
transition vias without a nearby GND return and only 2.7% coupled-route
coverage; the best measured CAN attempt still misses its coupling/reference
targets.  All protected topology findings remain zero.

The placement trial found a policy-wiring gap as well.  The generalized
monotonic electrical-craft repair existed, but defaulted off on boards without
a local `pipeline-policy.json`; only the detector ran.  Fresh waves now give
that repair a default 24-proposal budget unless a board overrides it.  In the
repeat run it automatically repaired four previously stranded EPS placements
to a zero-violation craft key before routing.  Five of six candidates reached
the precision/staged routing stage instead of three being discarded at
placement.

The final report preserves each stage's `error`, `reasons`, route-topology
evidence, and gate-term vector.  The measured failure is consequently
actionable: the next slice is a coupled-pair fallback that owns P/N together,
adds matched transition vias plus adjacent GND returns as one transaction, and
reserves the pair envelope in future-congestion placement.  Repeating global
waves before that owner exists would only sample the same deterministic
pair-physics refusal.

The first refreshed dashboard archive revealed the same state-contamination
class at a different boundary: thermal/FEM completed, but the subsequent KiCad
score in that interpreter raised an ASCII decode error on non-ASCII board text,
leaving valid temperature images with no gate badges or issue map.  Dashboard
gate scoring and issue rendering now run in a dedicated fresh process after
FEM, use one shared DRC JSON, and transport stdout explicitly as UTF-8 with
replacement only for diagnostic noise.  The isolated replay reports 1 DRC,
20 unconnected, Kelvin/pair true, three ordinary topology advisories, and
emits the cyan topology overlay instead of silently omitting the panel.
