# Native obstruction, landing and topology closure

## Current status and completed campaign

This is a bounded generic repair of the current hierarchical BETA pipeline,
not a board-specific relocation script or fabrication approval. ATX gained an
admitted native construction. 12VHPWR gained a safe repair scope but no admitted
board improvement. No electrical load budget, current-path width, required
via count, clearance, outline, output interface or Hub/ATX pairing was relaxed.

The completed normal ATX suite pass continued the September 28 J journal, not the
private diagnostic copy. It must reconstruct and independently admit the new
placement, then attempt the remaining stages. The private probe copied older
stage sidecars; those are not new pipeline-stage provenance and must not be
used to publish a completed pass or bypass continuation checks.

The normal full-pass campaign has stopped; `MainPID=0` and `SubState=exited`:

- Unit: `cec-atx-native-closure-20261001-a.service`.
- Invocation: `d357c30fdac94cd1847ab690c75f4db1`.
- Output: `build/atx-native-closure-20261001-a/suite.json`.
- Retained launch: `build/atx-native-closure-20261001-a-launch/launch.json`.
- Windows one-shot listener:
  `C:/Users/Admin/Documents/New project/atx-native-closure-20261001-a/`.
- Six-worker ceiling, 10 GiB memory cap, 1,800-second board budget and
  1,920-second service cap; 24 craft trials, two craft rounds, one epoch,
  16 routing passes and 600-second priority-placement repair allowance.
- Minimum free repository space: 16 GiB. Actual launch checks found 32 CPU
  threads, 27 GiB WSL RAM, 26 GiB available RAM and approximately 57 GiB free.
- No source promotion. Completed stage previews mirror to
  `C:/Users/Admin/Documents/CEC-Board-Reviews/atx-native-closure-20261001-a/`.
- No production campaign remains active. 12VHPWR is not blindly repeated.

The installed app adapter is now `codex-app-tools/0.1.5/server.mjs`; the older
September 28 `0.1.4` path no longer exists. A fresh read-only adapter probe
passed. The new listener's `delivery/state.json` records `armed` for the exact
invocation above, with no listener error. The normal pass has reproduced
4/4 construction in its log; that intermediate message alone is not stage
admission. The listener is one-shot and will dispatch only this run's terminal
event, not periodic unchanged-state notifications.

Do not edit shared scripts, library/source boards or paired authority while
that campaign is active. The periodic heartbeat stays paused. The existing
custom one-shot completion bridge is used, with a new unit, invocation and
delivery directory; previously delivered September 28 events must not be resent.

## Verified lineage and controls

| Artifact | SHA256 |
| --- | --- |
| ATX J placement input | `a953564dd236bde8b5b503aee7cf110abce0d07c5b362b342911716569a854f0` |
| 12VHPWR retained placement input | `e9fd08b171747ac1eb3b6cb567036b4047218f29935410d876eedba465872323` |
| New private ATX admitted construction | `a32ce3058a0c48ac7da58954bcb806fef46fb0251a39d0f23cedebe9d5b1d4ca` |
| Immutable PCIe2 v103 | `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388` |
| Hub incumbent | `166b9b63d88fb7b06e6710d76f08157d3412e7bea8139992fd60d9d9a1277a87` |
| Hub/ATX paired authority | `dfbeccb8eca4331c53c92c95b77d82dea03d4d8f396effda2860ca1d99882463` |

The fresh intake receipts are under
`build/closure-preflight-20261001/<board>/preflight.json`. Current source
signatures, manifest intake and intended placement-resume provenance pass.
The ATX mating row compiles; 12VHPWR has no declared paired row. Original board
bytes, the PCIe2 control, Hub incumbent and paired authority remain unchanged.

## Four reusable repair slices

1. **Complete obstruction sets, instead of serial first-hit moves.** The
   native pad/hole guard still uses its fast first-hit admission path. A
   separate complete diagnostic snapshot records every native pad hit across
   one proposed principal conductor, with pad identity, segment, layer, net,
   width and clearance. A bounded joint-placement proposal consumes only
   complete pad snapshots, resolves owner/decoupler closure, and refuses fixed,
   unavailable or oversized groups. It reuses the normal placement domain,
   protected regions and admission checks. Group proposals receive a share of
   the existing trial budget, not an unbounded new loop. Completeness here is
   specifically for pad/hole obstacles, not all tracks, vias or reservations.

2. **Exact noncontact placement scope with original copper retained.** A
   resumed board with ordinary unowned sense copper previously hit a blanket
   ownership refusal. The optional native pose-only scope now freezes original
   copper and its attached footprints, report/blueprint dependencies, locked
   and non-SMD members, zone-coupled pads and geometry-bearing boundaries.
   Eligible detached SMD poses can be proposed without claiming entire nets
   or discarding original tracks. Exact native serialization/readback and
   immutable-copper checks remain mandatory. Configuration is copied before
   binding, so local immutable-member policy cannot leak into later callers.

3. **Full circular landing containment, not miter erosion.** A source-field
   via was falsely rejected by negative-buffer miter geometry near a reentrant
   notch. The actual center-to-boundary distance was approximately 0.606643 mm,
   exceeding the unchanged 0.495 mm required land radius plus margin. Both
   proposal screening and native filled-copper qualification now use covered
   center plus exact Euclidean boundary distance, including interior holes.
   Invalid copper/dimensions still fail closed. No copper is grown, repaired,
   or substituted for the actual fill; complete fields and connection to their
   primary conductor must still qualify.

4. **Repair acute virtual backtracks before committing new rails.** Removing
   the false landing refusal exposed a genuine new acute backtrack in a
   proposed rail. The generic bounded detour solver can now repair clear but
   acutely backtracking unanchored degree-two equal-width chains. Actual pad
   contacts, branches, width/layer transitions and explicit anchors remain
   fixed. Full-width obstacle checks and the normal native admission still
   apply. Existing protected copper is not rewritten. Topology failure now
   retains uncommitted construction/landing evidence without saving a partial
   failed construction as a candidate.

None of these runtime rules contains a board/refdes/coordinate exception.
Synthetic tests include translated/reversed geometry, fixed-member refusals,
owner/cap closure, retained ordinary copper, reentrant notches, holes and
edges, topology anchors, branches and opt-out behavior.

## Measured replays, including unsuccessful ones

| Replay | Time | Actual outcome |
| --- | --- | --- |
| ATX complete blocker groups | 67.509 s | Fresh legal groups, no admission; exposed post-fill landing refusal |
| ATX exact landing distance | 87.56 s | Four rails planned, native admission refused a new acute backtrack |
| ATX landing plus topology | 89.956 s | Native reconstruction admitted; 4/4 rail objects; 366 to 360 opens; 5 to 5 scored structural DRC |
| 12VHPWR exact noncontact scope | 295.070 s | 8 trials, 7 legal; 0 accepted; 4 inconclusive critical probes; board byte-identical |

The accepted ATX artifact and proof are in
`build/closure-atx-group-topology-20261001/`. Its 119-item protected power
prefix and fixed/mechanical domain are unchanged. The new acute backtrack is
absent, with no new route-topology fault. Two pre-existing route-quality
blockers remain. The 78 by 95 mm outline is unchanged. `routing_admitted` is
false: four constructed rail objects are not a full electrical/current,
thermal, routing or fabrication qualification.

ATX refusal-only boards under `closure-atx-landing-forensics-20261001` and
`closure-atx-distance-proposal-20261001` are diagnostic artifacts, never
publishable winners.

12VHPWR evidence is in `build/closure-vhp-noncontact-20261001/`. The 506 native
track/via items include 228 ordinary sense items outside the rehydrated prefix;
all remain intact. The derived domain has 46 eligible members from 110, with
attached/dependent members frozen. Opens remain 220 and scored structural DRC
remain zero. Seven precision probes ran at a recorded 120-second per-pair
limit; four exhausted their search budget. This is inconclusive search, not
proof of geometric impossibility. Do not blindly repeat the same menu/effort
or describe the scope repair as a routed-board improvement.

## Tests and cross-board regression

- Final combined safety run: **581 tests and two subtests passed**, 183.74 s.
- Runner, completion-event, suite and review-delivery checks: **54 passed**.
  These are separate runs, not an aggregate count of unique tests.
- `git diff --check` passed.
- Fresh immutable-control receipt:
  `build/closure-topology-control-20261001.json`.
- PCIe2 remains byte-identical with zero opens, zero scored DRC, no route-craft
  blockers, and no fabrication-geometry blockers. Its score diff-pair and
  Kelvin gates remain true. Full constraint release still fails for the two
  previously identified issues: RS1 inner Kelvin departure and 80% adjacent
  filled-ground coverage on CAN versus the 95% policy. They were not created
  by this slice and are not waived.
- The neutral-core generalization audit passes. The whole pipeline is still
  classified `generic_core_with_legacy_physical_and_integration_debt`, with
  **378 runtime and 23 physical legacy-selector findings**. Neither
  `full_pipeline_generic` nor `release_ok` is true. Do not label the entire
  old pipeline generic or fab-qualified on the strength of these four fixes.

An inspected no-body render of the admitted private ATX construction is at
`C:/Users/Admin/Documents/CEC-Board-Reviews/closure-20261001/ATX-4-rails-placement.png`.
The header includes its actual hash and not-routed/not-fab-qualified status.
The normal suite published its own hash-verified blocked placement checkpoint,
described below; no older board or fabricated journal was substituted.

## Full-pass completion and the next generic boundary repair

The exact invocation completed and its one-shot callback was acknowledged
once. The coordinator exited normally, but its board pipeline failed with
exit code 1 after **429.530 seconds**. `qualification_valid=false`.
Source input bytes, all source signatures and the engine signature remained
unchanged throughout. A service-success event is not board acceptance.

The normal pass reproduced **360 opens, five scored structural DRC and two
route-quality blockers** in both the archived checkpoint and saved placement
board. Its published checkpoint SHA256 is
`dc8e0b42372d664a7155aeb8831d729f25aeaeba33f61820b9bf06c7bc9d6563`.
The dashboard correctly labels it `placement-checkpoint:craft | BLOCKED`,
with `checkpoint_hash_verified=true`, `release_authority=false`, and no
fabrication signoff. `journal_hash_verified=false` describes the failed
placement stage, not a stale checkpoint: the separate checkpoint certificate
verifies this exact PCB. Dashboard catalog intake and both top/bottom PNG
endpoints returned HTTP 200; both images were generated from this attempt.

Viewer:
`http://localhost:8090/?id=pass-atx-native-closure-20261001-a-atx-24pin-rev3-cd1b57988f`.
Windows previews:
`C:/Users/Admin/Documents/CEC-Board-Reviews/atx-native-closure-20261001-a/atx-24pin-rev3/`.

The causal chain is now distinguishable from construction-object count:

1. Four raw force-rail objects construct, with the admitted six-open gain.
2. The independent full current-domain planner cannot find the required
   `/SENSE3V3_HI` input path from the connector/shunt authority. The existing
   thermal-config contract is **20 A, margin 1.25, effective demand 25 A**;
   none of these values was changed. Recorded planner widths are approximately
   6.535523 mm on F/B copper and 78.297619 mm on the two allowed inner routing
   layers. These are conservative planner outputs, not new vendor ratings or
   proof of thermal qualification. Existing relief diagnostics found no path
   on the retained topology; one outer-layer diagnostic budget was exhausted.
   This is not a mathematical proof of board infeasibility.
3. The resulting complete-placement state has **zero frozen nets**, no
   admitted exact-power certificate, and provisional local copper. The exact
   power gate refuses it as `complete_frozen_power_authority_missing`.
4. Recovery entered ordinary priority placement with unbound power authority.
   Prefix capture correctly rejected the unadmitted local copper, but the
   untyped `ValueError` escaped and became a `worker_failed` process error
   instead of an actionable power-dependency refusal.

The fifth generic fix adds `UnadmittedLocalCopper` with typed, non-authorizing
evidence. The priority adapter reports
`unadmitted_local_copper_requires_owned_recovery`, identifies the blocked
`frozen_power_authority` stage and requires an owned local-copper transaction
plus fresh power qualification. It does not turn rejected local copper into
ownership, fall back to destructive rehydration, waive the power gate, or
enter route-placement search. Other unexpected integrity errors still
propagate; this is not a blanket exception handler.

Five new synthetic cases reproduced the failure before the fix and passed
after it. Two further worker-entrypoint tests verify that successful report
delivery (process exit zero) still serializes `ok=false`, `changed=false` and
`release_authority=false`. The actual failed worker was replayed with its
exact board/config/params/baseline into a new receipt:
`build/atx-unadmitted-local-worker-replay-20261001.json`. It now returns that
structured refusal in about half a second without changing its source PCB or
granting admission. The incomplete power path remains unresolved.

Expanded safety validation: **594 tests plus two subtests passed**, 206.49 s.
The later focused run including both worker-entrypoint cases passed **69**;
these overlapping runs are not additive unique-test counts. The refreshed
PCIe2 control `build/local-authority-control-20261001.json` remains identical:
zero opens/DRC, retained route/fabrication gates, and only the two pre-existing
full-constraint release blockers. Generalization counts remain 378/23, with
`release_ok=false`. `git diff --check` passed.

No identical full wave has been restarted. The next physical slice is
**current-qualified multi-terminal input access / full-width layer-transition
planning**, including the actual retained-copper obstruction domain. It must
verify the model and current basis, preserve the incumbent priority buses,
and prove complete native filled-power connectivity before important-signal
or ordinary routing admission. Moving a named component or accepting four
construction objects as a complete current contract is not the fix.

## Physical connectivity and measured serial-work repair

Five further shared changes were implemented in the October 1 continuation:

1. **Require physical layer joins.** `_preconnect_merge` previously fused
   every same-net raster overlap across layers as if it were a plated barrel.
   The planner now inventories actual PTH pads and vias, limits each join to
   that item's occupied planning layers, and separates physical terminal
   anchors from projected tracks. It does not turn NPTHs or two surface lands
   into barrels. A merged group's track-attachment growth is seeded from
   copper on that particular layer, not the projected cross-layer hull.
2. **Reject disconnected exact configuration-space components early.** The
   Manhattan search now avoids visibility-graph construction for endpoints
   in proven-disjoint legal regions. The cache is private to the exact layer
   space, bounded, and invalidated by reconstruction. It uses no expanded
   polygon or raster approximation; touching boundaries keep the prior exact
   `covers` behavior. This is a necessary-condition rejection, not a route,
   current, or fabrication admission.
3. **Retain bounded connector escape neighborhoods.** A connector wider than
   25 mm used to lose its entire multi-pin terminal approach field. Such a
   connector now receives local pad-centred tiles with the same maximum span.
   Foreign obstacles and the existing contiguous-neck length, width, current
   and native admission gates still apply. No whole-connector copper is
   invented. Translated/rotated fixtures prove this is not an ATX exception.
4. **Remove global-graph rebuilding from geometry-only return proofs.** A
   sampled live 12VHPWR process was rebuilding KiCad connectivity inside
   `_existing_return`, before parallel pair probes began. That function's
   explicit track/via path and actual-filled-polygon proofs consume no global
   connectivity cache. The redundant rebuild and portal-discovery rebuild
   were removed; each lookup still reads live geometry, including after
   addition, movement, removal or rollback. Transaction-boundary rebuilds
   and independent native final admission remain in place.
5. **Carry nested search interruption evidence before projection.** The
   precision producer and preflight compactor now scan the complete refusal
   tree before shortening it. The shared `cec_search_completion` core retains
   bounded witnesses for explicit deadline/budget/round-limit flags, legacy
   refusal/reason/status messages and positive rejection-count evidence.
   Candidate ranking treats these as inconclusive rather than measured
   geometric failures; exact negative caching uses the same policy. A false
   parent pair-budget flag cannot hide a nested interruption. Qualified
   successes are not rejected because an earlier optional attempt timed out,
   and unmeasured baseline pairs cannot contaminate a scoped probe's verdict.
   Finite grid exhaustion, zero timeout counts and positive unfinished portal
   domains alone are not classified as timeouts. The aggregate scans every
   node even after its witness/trace storage limit. This grants no copper or
   release authority.

Paired native local-cell audits, excluding only generated UUIDs and timing
fields from semantic comparison:

| Input | Legacy audit | Updated audit | Global rebuilds | Substantive proof differences |
| --- | --- | --- | --- | --- |
| Retained 12VHPWR | 4.196 s | 3.281 s | 37 to 5 | 0 |
| ATX saved placement | 4.565 s | 3.374 s | 49 to 1 | 0 |

These are approximately 22% and 26% improvements to the measured audit,
**not whole-pipeline speedup claims**. Both input files were byte-unchanged and
the native copper/group inventory was exactly restored. Comparison receipts:
`build/vhp-local-cell-speed-comparison-20261001.json` and
`build/atx-local-cell-speed-comparison-20261001.json`.

The exact ATX planner still fails corridor 3 to 8 for `/SENSE3V3_HI` after
these repairs. Its possible terminal attachments have no common exact legal
component on any single planning layer. A separate diagnostic removing the
categorical front-copper restriction also failed: that restriction alone is
not the cause. The baseline, physical-connectivity, bounded-field and
front-policy diagnostic receipts are under the corresponding
`build/atx-*-20261001/` directories. They are read-only forensics and never
grant authority or publishable copper. The original 20 A plus 1.25-margin
current contract and incumbent buses remain intact.

The BOM's [Molex 39291247 catalog](https://www.molex.com/en-us/products/part-detail/39291247?display=pdf)
was checked; it lists a 13 A maximum per contact. That catalog maximum alone
does not establish an operating load split among parallel input pins. This is
an engineering inference, not a manufacturer load-sharing specification. No
equal-sharing assumption, new per-pin load, or reduced rail budget was added.
Current-qualified branching/layer-transition planning remains the next ATX
physical boundary, not another ordinary-signal routing wave.

The first funded private 12VHPWR attempt
`cec-vhp-funded-priority-20261001-b.scope` was deliberately terminated after
profiling identified the repeated work. Both its staged PCB and original
input still had SHA256
`e9fd08b171747ac1eb3b6cb567036b4047218f29935410d876eedba465872323`.
Its sampled stack is retained in
`build/closure-vhp-funded-priority-20261001-b/serial-bottleneck.txt`.
It is not a completed wave or a candidate improvement.

A distinct replay after the geometry-only audit repair completed under
`cec-vhp-geometry-priority-20261001-c.scope` (invocation
`bcce342562954a978cfd2978545860bd`), with eight trial slots, eight-worker
ceiling, 240-second requested pair probes and a 960-second enclosing budget.
Seven legal candidates reached the parallel probe cohort, with zero accepted
placement changes, in 510.925 s. Parallel probe wall time was 231.201 s and
aggregate worker time was 1,517.287 s. Phase and sampled stack evidence are
durable under `build/closure-vhp-geometry-priority-20261001-c/`. Both source and
staged board retained the exact `e9fd08b...` hash. It does not promote source
or grant release; original ordinary copper stays protected. A requested
14 GiB systemd memory ceiling was supplied, but the user manager's memory
accounting properties are unavailable, so enforcement is not asserted from
those properties. Observed aggregate process RSS was comfortably below
available WSL memory. This remains a bounded private replay, not a full suite
completion or an event-listener campaign.

All seven saved probe rows incorrectly said `proof_complete=true` and
`outcome=measured`, while their bounded traces retained explicit nested portal
deadline exhaustion. The retrospective, non-mutating receipt
`build/vhp-search-completion-reclassification-20261001.json` finds **seven
inconclusive probes and seven false-complete classifications**. Original
receipt and source bytes were unchanged. This does not rerun or retroactively
admit the candidates; the old top-level whole-pair budget flag is preserved.
The live fix sends that evidence into the existing
`critical_probe_budget_inconclusive` stop path, avoiding a false geometric
plateau and further unvisited-proposal retries under the same insufficient
evaluation budget.

Native blocker provenance is retained in
`build/vhp-blocked-copper-provenance-20261001.json`. Observed sense-input copper
is already electrically connected in the locked native subgraph, but is not
part of the power authority or qualified high-speed prefix. It cannot be
silently discarded by a pose-only placement repair. These bounded portal
observations are causal leads, not exhaustive proof of the sole obstruction.

Two bounded causal experiments were completed without promoting anything:

- `build/vhp-owned-signal-counterfactual-20261001-c/`: resolve input identity
  using the same declared current-authority adapter as production, then remove
  both members of the two implicated input pairs **only in a private copy**.
  All 76 removed items remain reconstruction obligations. The exact priority
  power prefix and all placements were preserved, and the original source
  stayed byte-unchanged. At 230.046 s the full USB pair remained refused and
  inconclusive. Removing that sense copper alone does not qualify the route.
  The earlier `a`/`b` helper attempts refused their scope before editing copper;
  their initial default name-only topology query omitted the declared current
  authority and is not evidence of a production topology failure.
- `build/vhp-focused-chain-checkpoint-20261001/`: keep **all** original copper,
  but spend the same requested 240-second pair budget on one bank/order branch
  rather than divide it across the whole alternative menu. The normal saved-
  board checkpoint and admission path returned `no_new_complete_owned_pair`
  after 99.661 s. Other branches are explicitly deferred, so this is not an
  exhaustive impossibility proof or a comparable whole-pipeline speed result.

Both experiments found some coupled corridors but neither qualified the
complete inline USB topology. No discarded/partial route was published as a
current board. The remaining signal slice needs exact endpoint/whole-chain
evidence and, if necessary, a fully owned sense-reconstruction transaction;
simply removing old tracks or increasing timeouts is not a demonstrated fix.
ATX still requires current-qualified multi-terminal/layer-transition power
access before it may enter ordinary routing. No per-pin load was invented.

Fresh, isolated scorer receipts `build/vhp-retained-score-20261001.json` and
`build/atx-retained-score-20261001.json` confirm the unchanged incumbents:
12VHPWR has **220 opens / 0 scored DRC**; ATX has **360 opens / 5 scored DRC**.
Both retain false Kelvin/pair/overall scorer gates and are not fab candidates.
No accepted board-level connectivity improvement is claimed for these new
experiments. Their geometry, source identity and search-completion evidence
are progress in diagnosis/engine reliability, not electrical closure.

Final combined safety run: **884 tests and two subtests passed**, with one
honest integration skip, 203.56 s. New teeth cover false projected crossings,
real/native PTH and via joins, NPTH/non-plated refusal, layer-specific attach
growth, narrow disconnections, valid detours, boundary contact, cache rebuild,
large/rotated/translated connector tiles, live local-copper mutations and full-
tree search completion before bounded projection/negative caching.
The refreshed PCIe2 receipt
`build/native-search-completion-control-20261001.json` confirms the immutable
control board remains byte-identical,
with zero opens and zero scored DRC and retained craft/fabrication geometry.
Only its two pre-existing full-constraint release blockers remain. No strict
signoff gate was waived; whole-pipeline generic/release acceptance stays false.

## Joint signal/return-field closure (later October 1 slice)

The retained failure tree exposed a real ordering defect, not simply an
underfunded search: a legal inner signal ribbon consumed the connector's
remaining ground-return pocket. The parent endpoint refusal projection also
discarded the downstream `return_refusal` / `return_evidence` records, so the
top-level receipt looked like ordinary corridor congestion. Private native
counterfactual receipts under `build/vhp-return-*20261001*/` established that
complete legal return seats existed before the new ribbon but not after it.
Those diagnostic boards are not admission or release artifacts.

The production repair is bounded and geometry-derived:

- `cec_pair_return_field.py` proposes finite, local-frame return seats and
  complete one/two-member coverage sets. Transforms, caps and interrupted
  searches are explicit; finite sampling never claims a no-path proof.
- `cec_precision_route.py` keeps the normal ribbon-first construction. Only
  when a completed ribbon cannot obtain its mandatory return field does it
  roll back its own child copper, native-qualify the field first, and reroute
  the ribbon around those real barrels. At most two attempts share the
  original deadline. Inherited copper and placement are immutable.
- Fine return-seat refinement is funded at that dependency backtrack, not
  multiplied across every coarse portal screen. Via dimensions, drill spacing,
  edge/foreign-copper clearance, reach and reference rules are unchanged.
  Non-spanning blind ground vias cannot stand in for through return barrels.
- Endpoint refusals preserve the bounded downstream guard evidence. Completed
  predecessor-leg evidence remains visible when a successor fails, explicitly
  as local solver evidence rather than whole-pair/release authority.

The first focused replay with the repair completed the long first leg but
properly refused a successor via-in-pad because the committed back-side power
bus occupied that barrel column. It was not a reason to move the power bus.
The ordinary full bank/order menu then found a different valid schedule:
reverse the inline bank orientation and route the short MCU-side leg first
on the surface, followed by the connector leg with joint inner-route/return
planning. No production bank/order override, source copper deletion, placement
nudge, new layer, process exemption or relaxed gate was used.

### Accepted saved-board result

`build/vhp-joint-return-full-menu-20261001/report.json` records the normal
production search completing in **130.578 s**. Independent saved-board
admission qualifies the complete USB pair and all ten physical signal pads:

- **220 -> 212 opens**, **0 -> 0 scored DRC** against a freshly refilled parent.
- All parent copper preserved (zero missing items), all placements unchanged,
  source byte-identical.
- USB whole-pair coupling 83.3%, skew 3.535 mm; existing kind-specific gates
  remain unchanged.
- A follow-up native physical-pair audit also passes CAN and CAN_INT, with
  full adjacent-ground coverage and no missing return vias for all three
  pairs. CAN_INT's existing bounded endpoint fan-in contract, not a new
  coupling waiver, governs its shorter geometry.

The accepted PCB is
`build/vhp-joint-return-full-menu-20261001/checkpoint/pair-00/referenced.kicad_pcb`,
SHA256
`a55651e779c57a6ccabbb01615acbe69040355f6b4a2c65e4f23e4ac70874a00`.
Its executable artifact signature is
`6f8c338ec236076c33b7cd7847611d6c0f12125c844821fa73223faf6efb6f61`.
The receipt binds PCB, project/rules and cell/pour sidecars. This is only
**critical-prefix admission**: `residual_allowed=false` and
`release_accepted=false`. It is not a placement admission journal, routed-board
completion or fab signoff. Canonical source boards were not replaced.

The immutable no-component-body top/bottom review is available on the
[dashboard](http://localhost:8090/?id=critical-vhp-joint-return-full-menu-20261001-a55651e779c5)
and under
`build/board-archive/critical-vhp-joint-return-full-menu-20261001-a55651e779c5/`.
The archive PCB matches the exact admitted hash; its banner and metadata
identify the limited scope and 212 remaining opens. Catalog, panel and Windows
localhost access were checked. No older board was substituted, FEM was not
run by this preview, and no placement journal was fabricated.
All six native copper-layer SVGs are also attached to this exact review, with
individual hashes and the admitted source-board hash. `native-in2-copper.png`
is a portable preview of the actual saved inner copper, not thermal-solver
geometry. The optional raster preview initially lacked the Python CairoSVG
module; the existing `rsvg-convert` tool produced it without installing or
changing dependencies. Native SVG publication itself had already completed.

### Remaining boundary and regression evidence

`build/vhp-joint-return-priority-boundary-20261001.json` confirms the normal
critical compiler reuses all now-owned physical CAN/USB pairs in 0.272 s.
The global scorer still fails for inherited non-octilinear sense/power copper
and the open fan-power branch; its `_P/_N` connectivity/craft gate includes
the ordinary current-monitor input pairs. This is not a new failure of the
qualified USB/CAN paths. Those inherited source items are still protected;
fixing them requires an owned repair transaction, not silent deletion or a
false partial-checkpoint promotion.

A normal canonical continuation was launched at
`build/vhp-joint-return-continuation-20261001/` from the explicit admitted
derived PCB, with source intake and all actual placement/route admission
stages still active, a 900-second enclosing budget, and at most two parallel
route candidates. It does not use `--route-only-probe` or a synthetic placement
journal, and it does not request replacement placement. Its completed
pipeline journal, not the launch, determines whether residual routing is
admitted. **The pass completed and stopped before broad routing**: source
intake passed in 19.0 s, placement passed in 142.6 s with the exact accepted
PCB hash unchanged, then multiresolution preflight refused in 45.4 s.
CAN/USB remained qualified; the sole authoritative-grid critical refusal is
the `/VBUS_RAW` connector-to-protection-device obligation. An ordinary
overvoltage-threshold pin's missing long straight ray is separately a warning,
not this gate failure. Neither another unchanged full wave nor a preflight
waiver was issued.

`build/vhp-native-vbus-obligation-20261001/report.json` records one bounded,
explicit-obligation native tier derived from that preflight receipt. With
other incoming copper protected, the backend timed out at 90 s. Total probe
time including independent validation was 98.282 s. It retained **212 opens /
0 scored DRC**, all parent copper, all placements and qualified pairs; the
incomplete/no-improvement candidate was not admitted or published.
`build/vhp-native-vbus-search-completion-20261001.json` uses the production
full-tree interruption classifier to mark this **inconclusive**, not an
exhaustive geometric impossibility. The original receipt remains unchanged.

The read-only native column receipt
`build/vhp-vbus-pad-columns-20261001.json` identifies a more specific local
lead: at the protection device's VBUS land, the ordinary 0.6/0.3 mm via land
would violate clearance to an accepted USB inner trace. The existing declared
POFV menu's 0.35/0.25 and 0.30/0.20 mm geometries have native-clear local seats;
the connector's narrower supply lands also have process-contained 0.30/0.20 mm
seats. These are local candidate checks, **not current-capacity qualification,
a remote route proof or admission**. No small power via was inserted and no
load/budget was invented. The next reusable boundary is qualified compact
power-terminal escape, including real current/via requirements and global
composition, so the preflight/native backend can use a legal process-aware
launch rather than retry the default barrel or move important copper.

ATX remains **360 opens / 5 scored DRC** at its unchanged incumbent. The
native 25 A current-qualified power-access boundary described above is still
unresolved; no equal-sharing assumption, new per-pin budget, alternate-MST
fiction or repeated unchanged ordinary wave was added.

The broad joint-return safety run passed **548 tests and two subtests** in
28.14 s. After the final predecessor-evidence change, the follow-up receipt /
generalization run passed **78 tests** in 13.93 s (overlapping coverage, not
an additive test total). Native pocket/transform tests retain exact fabrication
guards; controller unit stubs are not represented as independent full-board
qualification. The accepted saved-board transaction supplies that integration
evidence. `git diff --check` passed.

`build/joint-return-pcie2-final-control-20261001.json` confirms the immutable
PCIe2 review control remains byte-identical, with **zero opens / zero scored
DRC**, retained scorer, route-craft and fabrication gates. Only its two
pre-existing full-constraint release blockers remain: RS1 inward Kelvin
departure and CAN adjacent-ground coverage (80% versus its 95% gate).
No signoff gate was waived. The new neutral return-field core audits clean;
the larger inherited pipeline still has 378 runtime and 23 physical selector
violations, so `generic_pipeline_acceptance=false` remains honest.

## Rated native preflight escape and local-cell continuation

### Native recovery is construction, not a preflight waiver

`cec_preflight_native_recovery.py` now selects only explicitly declared
critical unroutable obligations from the full preflight receipt (or its
critical-only placement projection). It calls the existing guarded native
constructor on a private child with the existing source/sink current contract,
per-layer width requirements and selected process geometry. It does not invent
load budgets, move parts, relax clearance, overwrite the incoming board or
claim thermal/fabrication release.

The `/VBUS_RAW` contract remains **750 mA with the existing 1.25 geometry
margin**, not a newly allocated per-contact load. The production native worker
at `build/vhp-production-native-preflight-20261001-c/` physically closed the
whole net in 44.785 s. Its saved child has **208 opens / zero scored DRC**,
down from 212, with 24 new tracks and four new vias. All 12 strict admission
terms passed, including the independently reloaded native connectivity,
parent copper, placements, current-width checks for new copper, process
geometry and every previously qualified CAN/USB pair. The exact admitted PCB
SHA256 is
`2bb64ca5920c5e6140cdf847b8fbcc187cd47777dc7fc78e0cc966357ab94674`.
Trace-width qualification is not a complete via/current/thermal signoff.

The worker's initial parent controller failed after this successful operation;
that controller error was reproduced and fixed by tests. The later normal
full-pipeline replay, not the worker receipt alone, proves the handoff. Two
earlier 0.5 mm preflight probes passed by GPU-assisted finer-grid prediction;
those probes added no copper and are not counted as construction progress.

The normal preflight stage always reruns whole-board prediction on an admitted
saved child. It passes the actual child to routing only when the ordinary
full gate passes. Immutable request identity covers the source PCB, project,
rules, executable pour/cell/rail authorities, priority-replacement, power-prefix
and route-lineage receipts, effort policy, explicit target set and engine
closure. A changed child or authority invalidates reuse; an unchanged refused
request is not blindly repeated. Worker crashes/timeouts retain their failure
stack and cannot promote a partial positive receipt.

### Early placement misclassification was repaired

The first full replay (`...full-pipeline-20261001-d`) treated the same raster
VBUS refusal as a reason for a 600-second placement search. That private
experiment was stopped, retaining its diagnostic evidence. The generic
placement boundary now funds one native additive escape before attempting a
placement ECO, but only for explicit raster-only critical refusals with no
declaration, terminal-access or fanout errors. Commit requires the complete
preflight, refreshed route authority and actual placement-priority gate to
pass. Failure restores the complete artifact family and configuration.

`build/vhp-native-recovery-full-pipeline-20261001-e/` then completed real source
intake, placement and route preflight in 17.196, 278.275 and 7.645 s,
respectively. It committed the native escape without moving components or
running the 600-second placement search. Detailed-route coordination ran for
105.035 s, but **stopped at the local-decoupler priority stage, before broad
Freerouting**. The clean incumbent remained at 208 opens. Independent signoff
withheld release and generated no Gerbers. Stage entry is not represented as
a successful broad routing wave.

The hash-bound 208-open review has top/bottom no-body renders and all six actual
KiCad copper exports on the
[dashboard](http://localhost:8090/?id=native-12vhpwr-standard-20261001-2bb64ca5920c).
Catalog and both Windows-localhost top/inner image endpoints returned HTTP 200.
The source hash, panel hashes and non-release scope are in the immutable
archive summary. FEM was not used to generate this review.

### Shared supply barrel failure, not a component-placement recipe

The full route refusal initially reported 15/16 local cells, 165 opens and 32
new via/plane clearance findings. Two causal defects were separated:

1. A single refused cell suppressed zone refill for all otherwise generated
   trial copper. The other cells were therefore scored against stale GND
   fills. The wrapper now refills any trial containing new copper, including
   refused trials, before recording measurements. A real baseline replay at
   `build/vhp-local-cell-replay-4096-20261001-a/` confirmed **165 opens / zero
   scored DRC** after refill. All 32 findings were stale-fill artifacts, not
   32 newly constructed physical collisions. The incomplete cell population
   still correctly rolled back.
2. Multiple bypass values share one assigned IC supply pin. The earlier cell
   had already placed a qualified supply barrel at that pin. The next cell's
   constructor tried to insert a second drill at the same origin, correctly
   hit the duplicate-hole guard, and unsuccessfully searched for an off-pad
   detour. The source-only column probe looked clear, while the saved rejected
   contextual child showed that earlier same-net barrel. This distinction is
   recorded in `build/vhp-refused-cell-context-columns-20261001.json`.

The eightfold work-only counterfactual (`...local-cell-replay-32768...`) and
20 small cap-pose counterfactuals did not solve the unchanged topology. None
was admitted as a placement transition. No reference-specific move, wider
board, new supply budget or discarded ground return was implemented.

The native supply constructor now reuses an existing **unique, exact-centre,
same-assigned-net through barrel** only after re-proving ordinary or local
POFV geometry, annular-ring requirements, layer span, board edge and all-layer
native copper/hole guards. Wrong-net, duplicate, off-centre and unqualified
barrels are rejected. The original object/UUID is retained; the new cell does
not create, resize, delete or claim ownership of another drill. Two already
qualified endpoint columns can require track operations only.

A related generic channel blind spot was repaired: bounded obstacle-derived
axes now include actual foreign vias and traces on the searched layer, not
only pads. Projected clearance inflation is included when recognizing
staggered throats. Short orthogonal channel candidates are tried after
historically working paths and before expensive maze expansion, with every
existing exact copper, future-power, edge and locality guard unchanged. Cheap
layer/via topologies precede queue search under **one shared work and wall
lease**. The shared-ground-only role keeps its existing search ordering.

`build/vhp-local-cell-shared-column-replay-20261001-c/` exercised the production
constructor and saved/refilled the actual child. **All 16 cells passed** in
5.021 s, reducing **208 to 162 opens with zero scored DRC**. It generated 77
items, including 28 required GND vias. The formerly refused supply link used
77 of its unchanged 4096 work units, retained the existing owner barrel and
added one capacitor barrel. Its class-width 0.5 mm SIG2 path is 3.150 mm,
within the unchanged 3.280 mm locality bound. This is still a local PI prefix,
not a completed or thermally qualified board.

`build/vhp-local-cell-shared-column-preservation-20261001.json` independently
proved parent copper preservation, every previously qualified physical pair,
identical component placements and outline, unchanged power-zone declarations
and monotonic native score. The saved child SHA256 is
`1569851cc471274f7d1a74c45c9701b83c3ea6ed95900561f93d14664351505e`.
Source and candidate families remained unchanged during the proof.

Failed local-cell families are now retained before rollback with their exact
board hash, measured score and fill status. Their explicit diagnostic scope
grants neither checkpoint nor release authority. The route failure link uses
that child instead of showing the restored parent alongside child counts.

### Safety and coordinator replay

The final combined safety run at
`build/native-preflight-shared-cell-safety-20261001.log` passed **740 tests and
12 subtests** in 146.32 s. It includes strict preflight-cache/transaction cases,
partial-refill failure cases, rotated native via-throat fixtures, shared supply
column construction, both-endpoint reuse, invalid-column refusal and bounded
tier scheduling. Controller stubs are not presented as full native board
qualification; the saved-board replay and independent preservation receipt
provide that integration evidence. `git diff --check` passed.

The final PCIe2 control
`build/native-shared-cell-pcie2-final-control-20261001.json` remains
byte-identical at SHA256
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`, with **zero
opens / zero scored DRC**, 749 tracks, 197 vias and 1199.913 mm track length.
Scorer, fabrication and route-craft gates remain retained. The only full
constraint release failures are its same two pre-existing RS1 inner-departure
and CAN adjacent-ground-coverage blockers. No gate was waived. The neutral
cores audit clean, while the broader inherited selector debt still prevents
claiming complete generic pipeline acceptance.

A fresh normal coordinator replay from the 208-open parent completed at
`build/vhp-shared-cell-full-pipeline-20261001-f/` with a 1000-second enclosing
budget, one explicit seed and a 180-second broad-router budget. This exercises
the actual integrated constructor rather than seeding it with the standalone
162-open child or fabricating a placement journal. Placement and preflight
passed in 135.054 and 7.071 s. Recorded stage time was 349.725 s: intake
19.484 s, detailed routing 173.602 s, independent signoff 14.419 s and withheld
evidence 0.095 s. The checkpoint recovery retained **162 opens / zero scored
DRC**, 596 tracks and 74 vias. All 16 local bypass cells passed in the integrated
path. Relative to the 212-open input of this slice, 50 opens were removed
(23.6%). The broad Freerouting backend did **not** start; this is priority-prefix
progress, not a completed broad routing wave or fabrication release.

The next transaction refused at `priority_current_route`. It pruned 103 tracks
and one via from its private proposal, then attempted 15 domains. That proposal
regressed from 162 opens / zero scored DRC to 194 opens / 58 dangling findings;
it was rejected. The exact retained winner SHA256 is
`3a4c1ae11390d3647fa881ac8d7ca7e37a5d169fe99762c6a0ead00387f0fe33`.
`build/vhp-integrated-checkpoint-preservation-20261001-f.json` independently
proved preservation against the 208-open parent: all parent copper, qualified
physical pairs, functional placements, outline and power-zone declarations
remained retained. Both artifact families were unchanged. Qualification is
still limited to the accepted prefix; the full release conjunction failed.

The read-only probe `build/vhp-retained-current-owner-probe-20261001.json`
distinguishes the next physical problem from a mere routing-search shortage.
All 12 carried main current domains are connected and recognized as locked
owners, but they fail the existing rated-subgraph width check: narrow launches
and contacts disappear from the graph at the unchanged **9.2 A design basis
times 1.25 geometry margin**, requiring 2.239333 mm on the selected outer
copper. The actual runtime configuration contains no parallel-current contract
for 12VHPWR; no equal-current-sharing assumption or smaller power budget was
introduced. The legacy 8.33 A thermal direction inventory does not replace
the hardened dimensional design basis. `/FAN_12V` here is the endpoint-bound
force-domain alias of `/SENSEP6_HI`, not permission to treat the path as a
small fan-control load. Raw native connectivity/lock status is insufficient
current qualification. Blanket under-width pruning also removes branch
copper; the next owner-construction slice must distinguish genuine trunk
bottlenecks from monitoring leaves and preserve accepted geometry rather than
repeat this unchanged destructive proposal.

The current completed pass is published at
`http://localhost:8090/?id=pass-build-12vhpwr-standard-1ea5087661` with both
no-body renders and all six native copper plots. The ordinary
`cec_pass_review.publish` path now inventories the actual enabled stack and
binds each successful SVG to the same saved PCB hash. Failed layer export or
unknown inventory is explicit; no guessed stack, older picture, FEM filler
or release authority is substituted. Windows loopback health, archive membership
and the In4 image endpoint returned successfully. The publisher regression
suite passed 29 tests, including actual 2/4/6-layer inventory, partial-export
failure, inventory failure and mutation-before-catalog refusal. The subsequent
expanded combined regression is recorded separately; counts are not added
across overlapping test runs.

ATX is unchanged: its current-qualified 25 A force-access boundary is not
addressed by this small-supply-barrel repair, and no unchanged ATX wave was
repeated. WSL still has approximately 57 GiB free; no model download, dependency
installation, source schematic/BOM edit or expansive generated-data cleanup
was required for this slice.

## Parallel pipeline review and bounded follow-up repairs

Three explicitly requested, read-only review tracks examined runtime,
authority/physical correctness, and unattended recovery. Their findings were
joined against the real F coordinator artifacts, not inferred from a dashboard
image. The reviews did not write design files, invent power budgets or launch
new waves. The parent implemented and tested only the bounded corrections
listed below. Larger changes remain recommendations, not completed features.

### Measured wasted work and the actual compute boundary

The F coordinator's recorded stage total is 349.725 s. Placement (135.054 s)
and detailed routing (173.602 s) account for 88.3% of it. Detailed routing still
fails before the broad router starts, so adding GPU throughput to the broad
router cannot explain or cure this particular delay.

Two fiducial operations cost 30.136 s and 27.239 s. Their effective request,
native board hash and inspected authority inputs are identical, and neither
operation changes placement. The conservative reuse opportunity is the
**second 27.239 s only**, approximately 7.8% of the recorded F stage total.
The first operation still establishes its evidence. This is an opportunity
identified from saved timestamps, not an implemented or benchmarked cache.
A safe same-run reuse key must bind the full native PCB, present AND absent
authority/rule sidecars, effective policy, operation mode, relevant code
closure, and actual loaded footprint-library geometry. Configured footprint
paths alone are insufficient. Reuse only a successful, source-stable no-op;
never reuse a rolled-back, timed-out or skipped operation. Full placement and
signoff gates remain required.

The saved current-domain worker calls cost 55.767 s in total. Twelve failed
fast/exact pairs cost 35.102 s; eleven `SENSE*` pairs alone cost 32.069 s,
including 16.683 s of exact retry. These calls targeted Kelvin-shared force
nets that `synthesize_lastmile` intentionally does not search. Their ordinary
search counters were zero. The native protection is correct; the caller's
actuator choice was wrong. This is not proof that the board is impossible to
route, nor a reason to permit arbitrary sense taps.

On this pass the actual native congestion probe used approximately 2.705
million work cells, below its existing 12-million-cell GPU crossover, and the
whole preflight stage took 7.071 s. The reviewed machine exposes 32 logical
CPU workers and a 12 GiB RTX 4080 Laptop GPU, but this receipt does not show
GPU starvation as the primary blocker. Prefer independent, immutable CPU
candidate cohorts and deterministic shared-prefix reuse first. Sequential
mutations of one incumbent must not run concurrently. A local LLM manager is
not required to detect these explicit capability, deadline or plateau states.

### Corrections implemented after the review

1. **Parallel recovery carries physical geometry and authentic identities.**
   `_compile_declared_parallel_power_geometry` now receives the original
   geometric pours explicitly, separately from normalized planner asks.
   This removes its undefined `power_pours` reference and preserves every
   multipolygon/peer territory. Terminal witnesses are dictionaries, so
   physical `(net, ref, pad)` deduplication replaces the invalid hash-based
   dictionary deduplication. The first witness's nested evidence is copied,
   and each witness must match its enclosing refused net. Malformed or stale
   peer-owner evidence refuses the joint recovery before any escape mutation.
   Existing three-planner/two-recovery bounds remain unchanged. A partial or
   unsuccessful assignment still cannot be materialized or promoted.

2. **Capability refusal precedes current pruning and retry.**
   `cec_fr.lastmile_route_capability` and the ordinary router consume the same
   native Kelvin-pair inventory. An excluded net may instead carry a complete,
   already qualified input prefix: the bound domain must be complete, native
   source/sink connectivity and current-width proof must both be affirmative,
   and uncertified same-net copper zones cannot supply the shortcut's current
   ownership. Qualified prefixes are excluded from BOTH pruning and routing
   allowlists, including in a mixed tier with pending ordinary rails. Ground,
   foreign-net and rule-area zones do not trigger this conservative capacity
   refusal. A same-net zone may be incidental rather than actually needed;
   without a certified pour receipt or zone-free rated counterfactual, its
   input capacity is simply not proven by this shortcut. This does not claim
   physical impossibility. Final all-domain native and width gates still run.

   The atomic tier refuses an excluded domain that needs repair or lacks
   qualified input ownership before physical pruning or worker launch.
   It retains an
   exact input copy and emits `kelvin_owned_requires_force_operator`,
   `retryable=false`, and `physical_feasibility=not_assessed`. The late tier
   and direct current worker enforce the same boundary. A typed nonretryable
   worker response cannot receive an identical exact retry. Eligible ordinary
   domains retain their existing fast/exact portfolio and clearance guards.
   This does not implement the missing force operator or bypass the tier.

   `build/fanout-current-capability-replay-20261001/receipt.json` replayed this
   actual generic entry point against the saved F winner. It identified 12
   excluded domains among 15 requested domains in **4.701138 s**, with zero
   current worker attempts. The output is byte-identical at SHA256
   `3a4c1ae11390d3647fa881ac8d7ca7e37a5d169fe99762c6a0ead00387f0fe33`, and
   the source authority family remained unchanged. This is a capability-only
   replay, not a new full-wave benchmark, physical impossibility certificate
   or fabrication qualification. The earlier 0.074-second capability-only
   probe preceded the final independent current-input proofs; it is not the
   final implemented guard's benchmark.

3. **Unknown current-width results fail ownership admission.**
   Both priority-current admission sites require the width check to return
   affirmative `True`; `None`, `False` and malformed truthy values cannot
   grant a completed rated owner. Missing fabrication/current evidence is
   not a success. This closes a latent generic admission bug; it does not
   change any current budget or dimensional margin.

4. **Direct monitoring does not exempt a bound force trunk.**
   The native shared-INA regression exposed a blanket sense-name exemption in
   `trace-width-high-current`: adding a direct monitor could make an unchanged
   undersized force trunk pass. Complete source/sink-bound current domains now
   go through the rated subgraph even when they share a direct sense net name.
   A wide independent trunk with a thin monitoring leaf still passes; a thin
   load-bearing cut fails. The positive and negative native fixtures use real
   `_HI/_LO` discovery and assert that the actual sense inventory includes the
   force net. The mixed-tier regression checks a nonempty, locked three-item
   exact-copper prefix, not an empty/vacuous preservation contract.

### Next generic slices, in priority order

- **Force-owned constructive operation.** The existing width checker models
  a rated subgraph correctly, but physical blanket pruning deletes thin
  monitoring/local branches that may remain legal beside a rated trunk. In F
  all 103 removed tracks were locked, and none were restored by the narrow
  local-branch exception. Build a read-only rated-graph/min-cut witness first,
  then propose additive rated force copper on a private copy while preserving
  every existing branch and owned prefix exactly. Final proof must exclude
  all under-width graph edges and still connect the specified source/sink.
  Require independent width, Kelvin topology, clearance/refill, placement,
  power-prefix and whole-board monotonic admission. Existing signal-only
  replacement receipts cannot authorize power resizing. Refuse a forbidden
  or physically blocked constructive operation rather than changing an
  immutable bus or assuming parallel current sharing.
- **Enclosing deadline ownership.** Current-prune/current-route raw subprocess
  calls do not honor the existing operation/campaign deadline, and the
  single-candidate in-process dispatch lacks the multi-candidate outer
  watchdog. Use the existing operation supervisor and a shared non-renewable
  lease, reserve final certification time, terminate owned descendants and
  distinguish `deferred_budget` from physical no-path. Fifteen domains must
  not receive fifteen independently renewed timeout budgets.
- **Durable, model-free campaign cursor.** Persist the incumbent family hash,
  blocker identity fingerprint, tried repair families, conclusive versus
  inconclusive outcomes and consumed budget. An unchanged completed failure
  is valid cached evidence, not permission to resume the same failed search
  with a fresh lease. Dispatch only a new funded family or a causal
  source/engine/policy change. A timeout is not a plateau or proof of
  impossibility. Keep event-driven completion rather than periodic model
  polling.
- **Resume identity and safe no-op reuse.** Bind the resolved Freerouting
  version/JAR hash, native KiCad version, applicable repair-policy values and
  stage-specific code closure. Existing keys omit some effective engine
  choices but overinvalidate on unrelated Python edits. Keep diagnostic
  output paths/deadline epoch out of physical authority; exclude UI-only
  `.kicad_prl` state from journal authority while still carrying it for
  convenience. Implement the exact fiducial no-op fingerprint described
  above with mutation/add/delete/library and concurrent-change regressions.
- **Atomic per-stage lineage.** F has four attributed blockers and 241
  unattributed findings; `full_fail_stack=false` is the honest result.
  Checkpoint stages currently do not carry complete UUID mutation events.
  Publish compact input/output hashes and verified created/modified/removed
  UUID owner deltas atomically with each admitted checkpoint, and join the
  trace to that exact receipt. Do not infer mutation ownership from a net
  name or assign inherited defects to an observed stage. Test interruption,
  missing/mismatched receipts and unknown inherited objects.
- **Event-bridge recovery.** The exclusive completion claim is made before
  connection/arming; a crash there can strand a wave. Distinguish claimed,
  armed, proven-pre-dispatch, in-flight and delivered states. Only a proven
  never-sent request can be recovered automatically. A delivery-unknown send
  remains nonretryable without a sink acknowledgement or idempotency key.
  Never create duplicate wakeups merely because a send timed out.

These changes should remove wasted work and make bounded unattended progress
explicit, but they do not make current physical refusals disappear by fiat.
Raw connected/locked pours also need rated ownership/provenance before they
may suppress a current repair. That separate authority hardening remains open.

### Regression evidence

The earlier expanded constructor/publisher safety run passed 800 tests and
14 subtests in 147.25 s (`build/native-shared-cell-review-safety-20261001.log`).
It predates the fan-out repairs and is not presented as their final regression.
The parallel recovery slice passed 150 tests and three subtests, with one
existing skip (`build/fanout-parallel-recovery-safety-20261001.log`). The
subsequent ownership/last-mile/native-geometry slice passed 142 tests and ten
subtests (`build/fanout-ownership-safety-20261001.log`). During that slice an
inherited test asserted an obsolete human error phrase; it now asserts the
unchanged structured `native_geometry_regression` kind AND nonempty introduced
conflict identities. The actual refusal was not relaxed. Overlapping test
counts must not be added together.

The final broader suite passed **619 tests and 17 subtests**, with one existing
skip and seven dependency deprecation warnings, in 10.46 s
(`build/fanout-final-safety-20261001.log`). It includes the final input-owner
qualification, narrow shared-force rejection, rated trunk/thin-leaf acceptance,
mixed-tier prefix preservation, uncertified-zone refusal, ordinary last-mile,
bounded parallel recovery, native preflight, local cells, route checkpoints,
operation budgets and dashboard publisher regressions. Counts are not added
to preceding overlapping runs. `git diff --check` passed.

`build/fanout-final-pcie2-control-20261001.json` replayed the retained control
after the final corrections. Its SHA256 remains
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`, with **zero
opens / zero scored DRC**, 749 tracks, 197 vias and 1199.913 mm track length.
Score, fabrication, Kelvin/differential scorer and route-craft terms remain
retained. Full release still fails ONLY its same two pre-existing RS1
inner-departure and CAN adjacent-ground-coverage findings. The regression
process's nonzero exit reflects that release conjunction, not a new board
mutation or waived gate. Broad inherited selector debt also still prevents
claiming complete generic pipeline acceptance.

Neither corrected capability refusal nor an unavailable width result can
grant release authority. The 12VHPWR incumbent remains **162 opens / zero
scored DRC**, and is not fabrication ready. ATX has not received an unchanged
futile wave during this review. No new dashboard board was published because
the accepted native artifact is byte-identical, not a newly routed candidate.

## Parallel continuation: runtime, reuse, event integrity, and force diagnostics

This continuation implements and cross-reviews the preceding audit slices.
It does not replace the accepted board with a rejected experiment, alter a
current budget, or claim that additional elapsed runtime means physical progress.

### Runtime ownership and exact configuration carriage

Current-prune/current-route workers now use the existing operation supervisor.
Every nested operation inherits the enclosing deadline and finalization reserve;
budget exhaustion is `deferred_budget`/`inconclusive`, not physical no-path.
Malformed receipts and crashed workers remain infrastructure failures. Typed
evidence survives the oracle handoff, and interrupted candidates are withheld
from publication. Unique diagnostic directories and bounded inline log tails
survive the relevant temporary-candidate cleanup boundary.

Cross-checking the actual caller exposed an additional gap: standalone
single-candidate runs did not establish an enclosing lease at all. The canonical
single candidate now runs through `cec_route_candidate_worker.py` and the same
generic watchdog policy as the ensemble, clamped to any shorter parent deadline.
The worker receives the effective source/configuration whitelist, including
explicit `net=None`, pins, profile and source overrides; ensemble payloads now
preserve those too. Numerical seeds, existing seed-axis behavior, checkpoints,
incumbent retention and physical admission remain unchanged.

This hard wall covers the isolated candidate, not the entire standalone route
stage or job. Incumbent grading/residual resume precede that boundary, and
checkpoint recovery/final polish follow it. Suite-launched jobs retain their
existing whole-job deadline. That distinction must not be hidden behind a
blanket claim that all standalone work is globally bounded.

### Measured invocation-local fiducial reuse

Only an error-free, completed, source-stable fiducial no-op can be reused inside
the same placement invocation. The fingerprint binds the PCB, present/absent
authority and rules, effective options/configuration/environment, resolved
footprint bytes, runtime and all local Python modules. Failed, rolled-back,
timed-out, mutating or concurrently changed work does not seed reuse. This is
not a persistent resume cache and grants no downstream signoff authority.

The final saved-request replay is
`build/vhp-fiducial-reuse-replay-20261001-c/replay.json`:

- First native call: **29.578514 s**.
- Identical second call: **0.235323 s**, with reuse explicitly recorded.
- Exactly **one native worker**; source and working dependencies unchanged.
- About **29.34 s** avoided for this repeated operation, not a measured
  whole-wave throughput increase.

An earlier replay overlapped a safety edit and correctly refused the repeat
with `working dependencies changed; no repeat permitted`. That failed timing
experiment is retained separately; it was not counted as a successful reuse.

### Event-driven follow-up integrity

The completion bridge now makes append-only, exclusive generation claims.
Recovery requires confirmed death of the prior owner followed by a fresh read
of its pre-dispatch evidence. This ordering matters: reading an old `armed`
state before checking the PID could otherwise race a final dispatch and exit.
A durable exclusive dispatch marker is written immediately before the actual
MCP tool request, after initialization and tool discovery. A missing send
acknowledgement remains `delivery_unknown` and cannot be retried blindly.

Connection/listener failures and proven pre-dispatch transport failures have
bounded retries. A listener must arm within ten seconds; after arming it waits
for the actual event, without periodic model polling. Its stdin pipe is owned
by the Windows bridge, so EOF stops the WSL listener. Drained stdout is handled
before process closure, malformed protocol objects fail normally, and unknown
or mismatched event identities cannot trigger a continuation.

An independent review reproduced a separate D-Bus race: `GetAll(Unit)` could
describe invocation A while `GetAll(Service)` supplied invocation B's result.
The listener now brackets service properties with two matching unit snapshots,
bounded to three attempts. An unstable snapshot requests review rather than
claiming success. Failed state and missing invocation cannot become successful
completion. These tests use fake transports/buses, not real task messages.
Safe relaunch and bounded listener recovery are implemented; reboot persistence
and receiver-side exactly-once delivery are not claimed.

### Preserve electrical and source authority

`cec_force_current.py` provides a generic read-only rated trace graph/cut
diagnosis and a bounded additive proposal API. It never prunes or replaces the
input. Native fixtures exercise renamed and rotated layouts, actual four-wire
Kelvin cut vertices, preserved UUIDs/placements/rules, and independently checked
refill, DRC identities, current width and topology. Existing gates reject the
tested capacity bypass for new protected-net route-craft faults, even when its
width is adequate. Correction from the next review: this is an acute/backtrack
and heading audit, not a general cycle detector; rejection of that fixture
must not be described as proof of a universal no-loop policy. There is no
inferred parallel-layer, via, or zone capacity credit.

Cross-review also found input-identity issues in the new prototype: differently
named sibling project rules could disappear on copying; a separate thermal-hint
PCB was not bound; the short code list missed consumed dependencies; and a CLI
report destination could collide with an input. The final implementation binds
all 403 local Python files and explicit external/thermal authority, refuses
unresolved project-copy authority, and rejects protected output aliases
(including symlinks/hardlinks) and output trees containing declared authority.
These corrections do not weaken electrical qualification. The proposal API is not
yet an automatic canonical-wave actuator: whole-net ownership must be bound
explicitly before that integration.

Final code-bound real-board probes:

| Probe | Existing required outer width | Bounded plans | Result |
| --- | ---: | ---: | --- |
| 12VHPWR `/SENSEP1_HI` | 2.5 mm project floor | 7 | Refused; no additions |
| ATX `/SENSE3V3_HI` | 6.535523 mm, existing 20 A basis x 1.25 margin | 8 | Refused; no additions |

The VHP source launch disk at `(14.500001, 2.891499)` mm conflicts with
neighboring locked `/SENSEP2_HI` copper; the direct chord also meets J3.7 GND.
For ATX, sampled launch disks at `(66.099999, 92.5)` and `(61.899999, 92.5)` mm
fail the outline guard; J3.3 GND additionally obstructs the latter launch/chord.
These locations are native diagnostic witnesses, not product-specific repair
conditions. Receipts identify the actual obstacle UUIDs and scope the witness
to sampled segments/endpoints; they do not claim global physical impossibility.

Evidence is under `build/force-current-{vhp,atx}-proposal-20261001-c/receipt.json`
and `build/force-current-{vhp,atx}-diagnosis-20261001-c.json`. Proposal times were
1.780302 s and 1.680031 s respectively. Rejected children are byte-identical to
their sources; source-family and code identities remain unchanged. All twelve
inspected VHP domains and four inspected ATX domains lack rated qualification.
The sixth VHP input domain is the bound `/FAN_12V` alias, not a small-load waiver.

### Current board evidence

Fresh isolated scoring reports are
`build/fanout-next-vhp-score-20261001.json` and
`build/fanout-next-atx-score-20261001.json`:

| Artifact | Opens | Scored DRC | Tracks | Vias |
| --- | ---: | ---: | ---: | ---: |
| Retained 12VHPWR F winner | 162 | 0 | 596 | 74 |
| Retained ATX placement | 360 | 5 | 106 | 48 |
| PCIe two-port v103 control | 0 | 0 | 749 | 197 |

The 12VHPWR and ATX source hashes remain respectively
`3a4c1ae11390d3647fa881ac8d7ca7e37a5d169fe99762c6a0ead00387f0fe33` and
`d65131ca9aa7a29091dbeca4455b245faf601a64eb3bb3ede305ddfd5dd037a5`.
No accepted physical improvement is claimed in this continuation.

`build/fanout-next-final-pcie2-control-20261001.json` retains the same PCIe hash and
all prior score/fabrication/craft terms. Full release still fails only the
pre-existing RS1 inner-departure and CAN adjacent-ground-coverage checks.
The static generic-core gate now also includes the new force, fiducial reuse,
event listener and isolated candidate helpers. Inherited whole-runtime selector
debt remains visible; the full pipeline is not declared generically qualified.

### Final validation and remaining work

`build/fanout-next-final-safety-20261001.log` and its XML report record **704
passed tests and 66 subtests** in 75.03 s, with seven existing dependency
deprecation warnings. This includes the current/force/identity/budget/fiducial/
event/publisher/board-suite and preserved-prefix regressions. Its event runner
also executes 31 Node cases; the same 31 cases passed directly on Windows.

The separate runtime integration run passed **393 tests**, including all 85
full-pipeline tests, in 134.69 s. The final force-focused run passed 120 tests
and two subtests, including 49 force tests. These overlap the broad suite and
must not be summed into an inflated total. Native force fixtures use nonzero
Kelvin cut-vertex checks, not vacuous empty inventories.

The next physical capability needed is capacity-qualified terminal access under
the preserved power/pair ownership policy, followed by explicit atomic actuator
integration. Full-width planar bridges alone did not resolve the actual tested
launches. A legal neckdown or other transition needs its own electrical/thermal
qualification; neither a width waiver nor inferred current splitting is a fix.
Persistent campaign cursors, complete per-stage UUID lineage, and remaining
effective-engine/resume identity work are still open. No unchanged full wave
was launched or new dashboard layout advertised as physical progress in this
pass. Existing source boards, budgets and BOM were not changed; no commit was
made from the inherited dirty worktree.

## Native pad-surface access continuation

The next bounded search slice found an actual false refusal: the force bridge
operator only tried pad centers. A full-width round endpoint may hit a nearby
pin or the board edge at that center while a point elsewhere on the SAME
unchanged copper land is legal. This is not permission to reduce current,
shrink a required trace, move a power bus, add a via, or substitute a neckdown
exception for electrical qualification.

### Implemented reusable geometry and admission

- `cec_pad_surface_access.py` proposes a finite native interior-copper menu.
  `ERROR_INSIDE` polygons and every contour/hole boundary, the actual native
  drill shape, enabled/flashed layers and NPTH exclusion own the decision.
  Missing geometry has no bounding-rectangle fallback. The default 50 um
  interior contact disk is a search/contact witness, **not** an ampacity or
  terminal-spreading model. A reported 1 nm numerical guard excludes tangency.
- The force operator keeps the cheap center menu, then reserves work for
  surface alternatives. Full-width endpoint screening applies to both the
  old and new anchors, so an obstructed center cannot monopolize the fallback.
  Physical-terminal pairs are interleaved; source/sink identities include the
  physical pad, not just a potentially cloned UUID.
- Work is explicitly bounded: at most 128 pads, 256 retained surface anchors,
  512 pairing anchors, 32,768 pair examinations and 64 retained alternatives
  per physical pair/layer. There is an inherited deadline throughout. These
  are bounded search menus, never global no-path certificates. Foreign native
  indexes are reused only within the unchanged bridge-planning snapshot.
- A separate saved-board contact ledger is required. Its accepted-attempt IDs
  must account for the exact serialized additions once each. Paths, pad/track
  identities, layers, net identity, integer nanometre width, fixed contact
  inset and incident newly added track endpoints are independently replayed.
  Empty, stripped, stale or malformed receipts cannot turn into a pass.
- The existing preservation, exact refill, current-width, independent rated
  graph, whole-board DRC/admission and available legacy topology checks remain.
  Unknown or unexercised direct Kelvin coverage is now explicitly `ok:null`,
  with a qualification gap, not an empty green check. Losing existing coverage
  also refuses admission.

Parallel review supplied executable counterexamples for three defects in the
first implementation: center-only work consuming the reserved surface budget,
blocked center/surface pairs starving viable surface/surface pairs, and an
empty contact ledger passing vacuously. A fourth regression proves that width
must be replayed in integer nm: converting 1,000,007 nm to display mm and back
with `ceil` can wrongly require 1,000,008 nm. All were repaired generically.

### First source-bound physical probes

`build/force-surface-vhp-20261001-a/receipt.json` found a 2.5 mm F.Cu bridge for
`/SENSEP1_HI` in 6.729705 s: three added segments and eight attempted plans.
The independent rated graph changed from disconnected to connected, the
current-width checker passed, and all 790 original serialized items, all
sidecars and placements remained exact. The whole-board result remained
**162 opens / zero scored DRC**. This is a repaired rated path on an already
natively connected force net, not a reduction of the open count. The canonical
incumbent was not replaced. The original source hash remained
`3a4c1ae11390d3647fa881ac8d7ca7e37a5d169fe99762c6a0ead00387f0fe33`.

`build/force-surface-atx-20261001-a/receipt.json` found two partial segments at
the unchanged 6.535523 mm outer-layer width, but could not join every required
terminal in its 16-plan budget. It refused the whole candidate. The saved ATX
source remained `d65131ca9aa7a29091dbeca4455b245faf601a64eb3bb3ede305ddfd5dd037a5`;
the accepted baseline remains **360 opens / five scored DRC**. Partial copper
is diagnostic output, not a new accepted placement/routing checkpoint.

There is stronger local ATX evidence than a failed sampled grid. On J3.2 and
J3.12, a round full-width endpoint whose center stays inside the retained pad
cannot meet the existing outline and foreign-copper guards. With the actual
95 mm bottom edge, 0.5 mm edge guard and conservative radius 3,267,761 nm, the
necessary center boxes are respectively
`[60549999,90650000,63249999,91232239]` and
`[18549999,90650000,21249999,91232239]` nm. Native-confirmed 10 um interior
points on the foreign J3.14 (-12V) and J3.24 (GND) lands are respectively
`[61393749,88615108]` and `[19393749,88615108]` nm. The greatest squared
distance to any necessary-box corner is 10,295,038,733,661 nm2, below radius
squared 10,678,261,953,121 nm2, on both outer faces, even before clearance.
The boxes use the **full native shape bounds**, not an inscribed polygon's
smaller bounds. This excludes this endpoint representation only; it does not
prove that the board, a properly qualified copper transition, or the existing
terminal is electrically impossible.

### Filtered Kelvin coverage discovered during validation

The first VHP proposal's legacy direct cut-vertex count was zero both before
and after. This was a real scope gap: a same-net connector/shunt/INA triple
does not exist on the filtered INA240 lanes. Saved `oracle.json` also reports
`kelvin_ok:false`; its legacy reach and side checks are N/A, not an independent
filtered no-bypass qualification. The proposal's initial no-new-fault result
must not be mistaken for completed Kelvin signoff.

With the actual bound board hint, native inspection resolves all six typed
lineages, all 24 same-net copper demands are connected, and all 12 shunt-to-
filter departures are perpendicular and on the intended inner faces, before
and after. The complete source and private candidate retain those facts.
A native graph omitting only the shunt PAD object still finds connector
reachability for all 12 force-side filter terminals on both boards. That graph
does **not** clip the portions of traces lying within the removed pad, so this
is conservative isolation-unproved evidence, not a claimed physical bypass.
Its already-saturated result also cannot detect an additional same-terminal
bypass by simply comparing fault sets.

The remaining capability is an independently exercised filtered Kelvin proof,
with actual copper cut semantics and exact source/engine binding, before
canonical automatic promotion of this force-repair operator. Private proposals
do not grant fabrication, terminal/barrel ampacity, or thermal release.
No electrical budget, BOM, pad geometry, protected bus or native source board
was changed by this slice.

### Frozen-code validation, 2026-10-02

The read-only `cec_force_sense_evidence.py` observer now records typed filtered
lineage, individual native same-net copper demands, native inner departures,
and the explicitly **non-clipped** shunt-pad-omitted reachability separately.
It grants neither Kelvin isolation nor electrical/fabrication release. Unknown,
partial and inapplicable coverage remain distinct from success. Its inner-pad
threshold comes from the existing compiled constraint policy, not a new design
number; the 0.4 mm thin-trace classifier is identified as the existing checker's
implementation convention. Tests cover filled-zone islands, layer transitions,
ambiguous native identities, source/code drift, bounds and output collisions.

The force source-family guard also binds the compiled `params.json`, including
its absence. Both the final report destination and its atomic temporary path
are protected against source, policy, code, symlink and hardlink aliases.
This closes report-writing and stale-policy loopholes without changing a board.

After production code was frozen, final fresh-directory replays produced:

| Probe | Time | Physical result | Retained baseline |
| --- | ---: | --- | --- |
| 12VHPWR `/SENSEP1_HI` | 5.401405 s | Three 2.5 mm F.Cu segments; independent rated path and saved contact replay pass | 162 opens / 0 scored DRC |
| ATX `/SENSE3V3_HI` | 1.764054 s | Two partial 6.535523 mm segments; complete domain not joined; proposal refused | 360 opens / 5 scored DRC |
| PCIe two-port control | Independent full control replay | Board and all score/craft/fabrication terms unchanged | 0 opens / 0 scored DRC |

The final private VHP candidate is
`build/force-surface-vhp-20261002-b/candidate/winner.kicad_pcb`, SHA256
`cb0fc22058bdb75a3e5f3a6414f6c95c0df255fdb2882cea5784b7694ff3ea5a`.
Its receipt reports `direct_kelvin_check_not_exercised`, `ok:null` for that
legacy check, and no fabrication release authority. Its unchanged open count
must not be presented as connectivity closure. Neither this private candidate
nor the refused ATX diagnostic child replaced a canonical checkpoint.

Both final proposal receipts record unchanged source family, code, existing
copper and placements. Receipts are
`build/force-surface-vhp-20261002-b/receipt.json` and
`build/force-surface-atx-20261002-b/receipt.json`.
Fresh typed sense receipts are
`build/force-surface-sense-source-20261002.json` and
`build/force-surface-sense-child-20261002.json`. Both finish with stable source
and engine identity: six resolved inputs, 24/24 connected same-net demands,
12/12 valid inner departures, zero legacy direct Kelvin checks exercised,
and 12/12 observed non-clipped connector-reachable legs. The latter remains
isolation **unknown**, not a new physical fault or an isolation pass.

`build/surface-pcie2-control-20261002-b.json` preserves board SHA256
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`,
749 tracks, 197 vias and 1199.913 mm routed length. The same two independent
release blockers remain: RS1 pad 2 inner departure and 80% adjacent-ground
coverage on the affected CAN pair against the existing 95% requirement.
The generic-core static gate passes, including both new modules; inherited
whole-runtime/physical selector debt remains visible. Its nonzero full-release
exit is expected and is not relabeled a complete pipeline qualification.

Final validation:

- `build/force-surface-final-20261002.{log,xml}`: **168 passed**, one existing
  pcbnew deprecation warning, 79.71 s. Covers force proposals, native pad access,
  typed sense evidence and generic-core registration.
- `build/surface-runtime-safety-20261002.{log,xml}`: **645 passed and 66
  subtests**, seven existing dependency warnings, 32.17 s. This separate suite
  covers runtime budgets, recovery, authority, event handling, fiducial reuse,
  preserved prefixes, admission and board-suite/publisher safety.
- The agent's 143-test evidence run and earlier focused runs overlap these
  results; they are not added again to the total.

Next admission work is actual clipped-copper filtered Kelvin isolation proof,
then controlled force-operator integration. ATX additionally needs a
capacity-qualified terminal transition beyond the disproved full-width
in-pad-endpoint representation. No current splitting, width waiver, geometry
growth, or whole-board no-path claim was substituted for that missing capability.

### Filtered Kelvin copper-cut admission, 2026-10-02

This slice implements the clipped-copper proof left open above. It supersedes
the earlier isolation-unknown conclusion for the tested VHP source and child;
it does not retrospectively qualify the earlier proposal or the board suite.
No source PCB, placement, BOM, current budget, clearance, or protected bus was
modified. All routed changes remain private proposals.

`cec_kelvin_copper_cut.py` subtracts the actual shunt-pad region from every
same-net conductor polygon, including track caps and saved filled zones.
Removing a PAD graph vertex or clipping only trace centrelines is not a
substitute. Both native and definite geometric terminal connectivity must
exist before the cut, so an already-open sense path cannot pass vacuously.
Conservative upper/lower copper models distinguish proven geometric isolation,
a definite geometric bypass, and unknown. Layer islands remain separate;
supported plated barrels join layers, whereas NPTH holes never do. The 1 um
native polygon approximation and 2 nm numerical guard are geometry processing
bounds, not manufacturing clearance or electrical design margins.

The native conversion interfaces are documented by KiCad for
[pads](https://docs.kicad.org/doxygen/classPAD.html) and
[tracks](https://docs.kicad.org/doxygen/classPCB__TRACK.html). The receipts bind
the exercised runtime: KiCad 10.0.5, Shapely 2.1.2, and GEOS 3.13.1. Unsupported
partial/modified drill stacks, non-enclosed plated bores, unlinearized polygon
arcs, unfilled zones, unsupported copper graphics, or exhausted work bounds
produce unknown, not a pass. Only a simple single-face SMD source-pad cut is
currently supported. This is geometric sense/force isolation evidence, not
terminal ampacity, thermal, full Kelvin, or fabrication qualification.

`cec_force_sense_evidence.admit_changed_net` now requires a stable, complete
typed lineage and absolute post-change evidence for every affected leg,
including filtered intermediate nets. It binds source and sense terminals to
the selected physical identities and force terminals to current authority;
every actual same-net demand must be connected and the inner departure valid.
An unchanged fault set cannot waive a pre-existing failure. The force operator
enforces this gate for both additive proposals and already-rated/no-op returns,
using its remaining supervisor lease. Exact saved-board replay and final
verification must refer to one post-refill candidate-family epoch.

Parallel adversarial review also closed false-pass paths involving exhausted
authority iterators, duplicate drill identities, disconnected custom-pad
islands, nominal unflashed lands, partial barrel stacks, offset/undersized
lands, filled/capped bore assumptions, omitted late deadline checks, substituted
positive receipts from another leg, and mixed saved-candidate epochs. These are
covered by synthetic regressions; no refdes/coordinate exception was added to
the production verifier or admission policy.

Fresh saved-board results on the final implementation:

| Probe | Evidence | Remaining state |
| --- | --- | --- |
| VHP source and admitted private child | 12/12 clipped sense legs pass on each; stable source/code/candidate epoch | 162 opens / 0 scored DRC |
| VHP `/SENSEP1_HI` force proposal | Three 2.5 mm F.Cu segments accepted in 8.420758 s, including scoped Kelvin admission | Private child only; no connectivity-count reduction |
| ATX current placement | All 16 legs unknown because baseline native connectivity is incomplete; final read-only replay 0.874432 s | 360 opens / 5 scored DRC |
| PCIe two-port archived control | Legacy control remains 0 opens / 0 scored DRC and byte-for-byte unchanged | New independent cut audit: 2 pass, 2 fail, 4 unknown |

The two PCIe2 failures are **two sense inputs on one physical net**, not two
independent net defects: U10 IN- and U20 IN- on `/SENSEC1_LO`. After subtracting
RS1 pad 2, a definite lower-model copper path still reaches the two TB11 lands.
The witness includes existing filled copper on F.Cu and B.Cu and real plated
connections. This is a Kelvin sense path bypassing the intended pad tap, **not
a claimed short across the shunt resistor**. The four other unknown legs have
upper/lower connectivity disagreement and are not silently accepted.

This newly detected issue predates this slice. The archived PCIe2 board was
not repaired, overwritten, or relabeled to make its control pass. Its legacy
release report still has the previously recorded RS1 inner-departure and CAN
adjacent-ground blockers, but those two findings are no longer the complete
known qualification debt. Legacy `cec_score.kelvin_ok` has not been replaced
throughout the pipeline: this slice adds a read-only all-board observer and
enforcement at the private force-proposal boundary. Canonical wave integration
and whole-board release aggregation remain separate work.

Final validation and receipts:

- `build/kelvin-cut-stable-final-20261002.{log,xml}`: **404 passed**, one existing
  pcbnew deprecation warning, 115.47 s. Covers polygon/barrel topology, typed
  admission, source/candidate identity, force proposals, native pad access,
  current capability/deadlines, operation handoff, stage admission, generic
  registration, and the fabrication-review regression harness. Earlier focused
  runs overlap this total and are not added to it.
- `build/force-kelvin-vhp-20261002-d/receipt.json`: accepted private candidate
  `candidate/winner.kicad_pcb`, SHA256
  `f61d8b5cb885021b6ad98971207e50e3affc3a7aa8fc8a87596ad2e6a75b5671`.
  The before/after sense evidence and single affected-leg admission are stored
  with the proposal.
- `build/kelvin-copper-atx-source-20261002-stable.json`: stable read-only ATX
  evidence; open connectivity correctly prevents isolation qualification.
  The bounded force attempt in `build/force-kelvin-atx-20261002-c/receipt.json`
  remains refused as `bounded_no_legal_rated_path`, with two partial segments.
- `build/kelvin-cut-pcie2-stable-control-20261002.json`: unchanged legacy
  score/craft/fabrication terms; 749 tracks, 197 vias; expected nonzero release
  result. Generic-core registration passes; whole-runtime generic debt remains.
- `build/kelvin-copper-pcie2-source-20261002-stable.json`: stable independent
  cut evidence, 4.498993 s, with physical terminal identities, native conductor
  UUIDs, layer/barrel paths, and component bounds for the new findings.
- Final copper-cut implementation SHA256:
  `3d55ffa457782b312fb79f321a6d93e9206fdb0ab8f7eeeef4a14e77bba316e4`.

Next work is a generic repair for genuine shared sense/force copper contact,
resolution of the remaining inconclusive geometry, and a capacity-qualified
force-domain terminal transition for ATX. Integrate the operator into canonical
atomic admission only with these proofs preserved. Keep the archived PCIe2
control immutable; any physical repair must be a separately identified child.
This slice improves detection and proposal safety, not board closure counts.

### Force-separated sense branches and exterior rated launches, 2026-10-02

This continuation adds reusable construction rules, not a board-specific
coordinate patch. `cec_kelvin_force_separation.audit_path` screens proposed
sense copper against actual saved same-net force fills, broad tracks, plated
pads and vias. Electrical net equality is no longer an exemption from sense /
force separation. The actual source-pad cut is the sole permitted common
region. Unknown native fill/geometry/deadline evidence refuses construction.
The screen is now called by the normal Kelvin tap generator and its refusal
certificate records the obstructing conductor identities. It supplements,
rather than replaces, complete post-refill clipped-copper isolation evidence.

`cec_kelvin_branch_repair.py` is a separate supervised private operator. It
selects a typed, proven defective branch from saved native lineage, derives
bounded cardinal/chamfered alternatives from real obstacles, and preserves
the original net, width, layer and lock state. Its source-family-bound receipt
names every removed and added UUID. All other serialized primitives, actual
force fills, board settings and sidecars must remain exact; unsupported
ownership, ambiguous branches or mixed source/code/candidate epochs refuse.
This operator is not yet a canonical-wave repair or release authority.

The PCIe2 root cause is now localized: the 0.25 mm F.Cu branch
`f9c5fc84-1cc9-4b0a-a233-caae3d4f4be1` intersects actual force fill
`4ef744d6-e042-5fb4-9018-e9e996174adf` outside RS1 pad 2. Its definite lower-
model overlap is 0.372543069 mm2. The independently modeled VBUS pin/tie was
not the ingress. Two input failures referred to this one shared branch defect.

One fresh private trial, `build/kelvin-branch-pcie2-20261002-private-a`, replaced
two identified branch segments with three locked same-width chamfered
segments. The final saved/refilled child is
`candidate/board.kicad_pcb`, SHA256
`cc7437cb287e749c2a9804880937ef2323628303efe3344e1730cfee3710be23`.
All retained primitives and force fills remained exact; refill was stable.
The trial took 13.106476 s with seven planned alternatives, no automatic
retry. Native demand connectivity stayed 8/8; valid inner departures improved
7/8 -> 8/8; opens and scored DRC remained zero. Clipped isolation changed
**2 pass / 2 definite fail / 4 unknown -> 2 pass / 0 definite fail / 6 unknown**.
The definite overlap was removed, but absolute affected-leg isolation was
still unknown, so admission correctly remained false. The conservative model
has an upper-only 4 nm contact strip at the retained shunt-pad boundary; this
is recorded separately from a definite physical overlap, not waived.

The exact refused child is visible at
`http://localhost:8090/?id=pass-build-pcie-8pin-2port-95227f25a4` as **BLOCKED /
NOT FAB SIGNOFF**, with no-body top/bottom renders and all six actual native
copper plots. The live dashboard catalog returned the same candidate SHA.
No historical incumbent was substituted for this diagnostic output.

`cec_pad_surface_access.sample_caps` also adds bounded exterior endpoint-cap
anchors: the center need not lie inside a pad if the full rated endpoint cap
contains a verified native interior contact disk. Planned center and contact
witness are separate and are replayed against the saved newly added segment.
The 0.05 mm contact disk, required width, current margin, native clearances,
edge guards and same-net leaf guards are unchanged. This is geometric access,
not terminal ampacity or thermal qualification.

The initial fresh ATX proposal `build/force-cap-atx-20261002-a/receipt.json`
retained the 6.535523 mm floor and 0.2 mm clearance. It found legal external
launches unavailable to the old in-pad-center search and joined J3.1/J3.2/
J3.13, reducing native rated components 5 -> 3. J3.12 and RS3.1 remained
separate. After 16 attempts in 3.381 s it returned a bounded search refusal,
not a global impossibility proof. Its two private added segments and all 307
original items passed saved contact/preservation replay, but the incomplete
plan returned before exact refill, whole-board and scoped-Kelvin admission.
Those absent gates are not described as passed.

The trial additionally exposed a generic portfolio starvation bug: J3.12 had
legal anchors but received no pair attempt before repeated alternatives
consumed the bounded attempt budget. Component-pair fairness and explicit
eligible/tested/untested coverage are the next bounded correction; current
operator use remains private until canonical atomic integration is done.

Validation to this point:

- `build/kelvin-branch-final-20261002.{log,xml}`: **240 passed**, one existing
  pcbnew warning, 23.88 s. Includes all new branch/force-separation tests,
  clipped-copper and typed admission, departure/topology, generalization and
  archived-control harness regressions. Earlier 40/110-test runs overlap
  this set and are not added to it.
- The exterior-cap focused pad/force suites separately passed **150 tests**;
  these are disjoint from the 240-test command above.
- `build/kelvin-branch-pcie2-control-20261002.json`: archived control remains
  byte-for-byte SHA256 `2f09d276...9388`, 749 tracks, 197 vias, 0 opens and
  0 scored DRC. Score, route craft and fabrication terms are retained;
  pre-existing constraint release still fails. The stronger independent
  isolation findings are additional debt, not erased by the legacy score.
- `build/kelvin-branch-vhp-source-control-20261002.json`: stable fresh
  12VHPWR read-only replay, all 12 clipped legs pass in 1.990689 s.
- Generic-core registration passes; whole-runtime generic acceptance and
  board-suite fabrication qualification remain false.

No source PCB, placement, schematic, BOM, power budget, clearance, protected
bus or archived regression control was changed in this continuation.

### Certified straight-edge bounds and fair portfolio replay, 2026-10-02

The bounded follow-up resolved both causes identified above. It did not
reduce `GUARD_NM=2`, native curve approximation, fabrication clearance,
current margin or required trace width. The earlier A receipts remain
immutable evidence of their original code epoch; they were not relabeled.

The retained PCIe2 source spine and force fill have no native contact after
the actual shunt-pad subtraction: independent KiCad integer Boolean
subtraction gave 1.225 mm separation. The 4 nm strip came from independently
inflating fill and contracting the source cut along a common exact straight
edge. `cec_kelvin_copper_cut._source_cut` now refines a lower source-cut bound
only with certified interior rectangles of supported cardinal, zero-offset
RECT/ROUNDRECT SMD pads. Layer-specific native parameters, inward rounding
of odd sizes, exact integer convex-hull/half-plane containment and rational
containment of the returned vertices are required. Curved corners and
unsupported pad geometry keep their original conservative bounds.

`_filled_shape` intersects an upper filled-zone envelope only with the exact
integer coordinate extrema of its native linear filled polygon. Every actual
edge is a convex combination of its native endpoints, so this bounding box
is a certified superset, not a snapped approximation. Actual native material
and the unchanged lower fill must remain contained. Source/zone geometry and
native identity are re-read before any positive result. A moved/replaced pad
or zone cannot register a new identity epoch to evade the old certificate.
The proposal guard uses the same helpers; absolute affected-leg admission
requires `exact_linear_identity_verified=true`.

KiCad's [PAD polygon API](https://docs.kicad.org/doxygen/classPAD.html) and
[native pad implementation](https://docs.kicad.org/doxygen/pad_8cpp_source.html)
document the layer-specific dimensions, orientation, corner radius and
inside/outside curve conversion. Installed KiCad 10.0.5 native replay, rather
than an assumed online version, binds these receipts. Regressions preserve
real 1 nm / 1 um protrusions and exterior point/corner contacts. Unsupported
noncardinal/offset/custom geometry does not receive an exact-core waiver.

Independent review found and closed the mutable-identity cache escape above.
The combined suite also exposed an inconsistent GEOS auxiliary predicate on
native refilled pours: `envelope.covers(refined)` could be false while the
corresponding difference was empty. That unnecessary upper-envelope
monotonic condition was removed; retaining extra upper copper is conservative.
Actual-native/lower-material containment, validity, certified bounds and
identity verification stayed mandatory. Four rotated native-refill cases
now exercise the integration, not only hand-authored rectangles.

The fresh private B repair was admitted in **16.068064 s**, with seven
alternatives and no automatic retry:

- Receipt: `build/kelvin-branch-pcie2-20261002-private-b/receipt.json`.
- Final refilled child: `candidate/board.kicad_pcb`, SHA256
  `395e30622e21d6f573388dcd5c0c3bb7e4025d8df6849fea5469541c8440e319`.
- On the refined verifier, unchanged source isolation is 6 pass / 2 definite
  fail / 0 unknown; the child is **8 pass / 0 fail / 0 unknown**. Both U10 IN-
  and U20 IN- changed from fail to pass. All physical identities are verified.
- Inner departures: **7/8 -> 8/8**. Native demand connectivity remains 8/8;
  opens and scored DRC remain **0 -> 0**.
- Whole-board non-regression and absolute scoped two-leg admission pass.
  Native refill: 13 zones, two identical passes, zero tolerance. Exactly two
  tracks replaced by three; every other primitive, force fill, setting and
  sidecar remains exact. Source/code/environment/candidate epochs are stable.
- This is an admitted private geometric repair, **not full electrical,
  thermal, full-Kelvin or fabrication qualification**. The archived control
  was not overwritten or promoted.

The fresh 50-check constraint release probe on B is still blocked by CAN
`/CAN_H_J1` / `/CAN_L_J1`: actual filled adjacent-GND coverage is **80%**
against the existing **95%** requirement. The prior RS1 inner-departure
blocker is no longer reported. This is the remaining blocker in that
constraint probe, not a claim that every other board-release authority is
qualified. Evidence is in
`build/kelvin-branch-pcie2-private-b-constraints-20261002.json`.

The exact B child is published at
`http://localhost:8090/?id=pass-build-pcie-8pin-2port-be36104a3e`, with all six
native copper layers and no-body top/bottom renders. It remains visibly
**BLOCKED / NOT FAB SIGNOFF** because the board constraint release failed,
even though the private branch operator was admitted.

The force portfolio now schedules by current native demand-component pair,
not merely by physical endpoint/anchor. Untried pairs precede repeated
alternatives; history is rebound by physical identity after a native merge.
Center-only pairs remain eligible when surface alternatives exist elsewhere.
The global attempt budget is not renewed. Per-epoch/final receipts expose
eligible, tested and untested pairs; truncated inventories remain unknown,
not a physical-unreachability claim.

One fresh ATX B trial used the same 16-attempt / 90-second bound and unchanged
6.535523 mm width floor:

| Search evidence | Initial A | Fair B |
| --- | --- | --- |
| Distinct component pairs before merge | 3/10 | 10/10 |
| Distinct component pairs after merge | 1/3 | 3/3 |
| J3.12 attempts | 0 | 8 |

All retained eligible pairs now received attempts, but not every geometric
alternative was exhausted. B took 3.549820 s and still refused as
`bounded_no_legal_rated_path`. Its physical added geometry is unchanged from
A: two full-width segments join J3.1/J3.2/J3.13; J3.12 and RS3.1 remain
separate. All 307 original primitives and source/code identities remain exact.
Final whole-board/refill/scoped-Kelvin admission was not reached. Receipt:
`build/force-cap-atx-20261002-b/receipt.json`. This closes the scheduling bug,
not ATX routing or terminal-ampacity qualification; do not repeat the same
portfolio as if its coverage were still missing.

Final stable-code validation:

- `build/force-sense-integration-final-20261002.{log,xml}`: **493 passed in
  167.64 s** in one combined command. Includes exterior-cap/force fairness,
  all new guard/branch/cut/scope tests, legacy Kelvin topology/departure,
  generalization and fabrication-review regression. Earlier focused totals
  overlap this final count and are not added to it.
- `build/force-sense-pcie2-control-final-20261002.json`: archived source SHA
  remains `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`;
  749 tracks, 197 vias, 0 opens / 0 scored DRC. Score/craft/fabrication terms
  are retained, inherited constraint release still fails as expected.
- `build/force-sense-vhp-control-final-20261002.json`: stable read-only
  12VHPWR replay, **12/12 clipped legs pass**, 2.215294 s.
- `build/force-cap-vhp-20261002-final/receipt.json`: one fresh different-board
  force proposal also admitted on the final engine in **10.580283 s**. Three
  additive segments; all 790 original items, settings, sidecars and source /
  code identities remain exact. Source and private child both retain **12/12**
  clipped-leg passes; absolute affected-leg and whole-board non-regression
  admission pass. This is a cross-board retained capability, not a reduction
  in closure counts: opens remain **162 -> 162**, scored DRC **0 -> 0**.
  Private child SHA256
  `2676b5b65ee8c1701cc0838aeda6b25c1ca590105b1cb5ad7e0eec75e1589b36`;
  no canonical promotion or whole-board fabrication claim.
- Final cut SHA: `943be71702ac7154d1124327c54040390cf5da711f79ac7edb46894030f6f4a2`.
  Final force operator SHA:
  `7352773435a813bd170c85b48f3e0e8b614eae6a7509257213864fbed5b37c7f`.
- Generic-core registration passes. Canonical atomic integration of the
  private force/branch operators and whole-runtime generic acceptance remain
  incomplete. The new tap-generation guard is integrated; this is not a
  claim that normal unattended waves now use every private capability.

Next causal work: satisfy real CAN reference-plane continuity without changing
its 95% rule, and qualify a legal ATX force-domain terminal transition / route
representation rather than reducing its current floor or waiving protected
sense-leaf contacts. Keep candidate admission and source-family authority
explicit when integrating these private operators into canonical waves.

## Follow-up policy

Review each exact completion/plateau event once. Check source/engine stability,
actual saved board hash, native admission, counts and failed identities before
calling anything progress. Preserve the incumbent if admission fails. If ATX
does not advance, identify the new causal stage before another wave. For
12VHPWR, retain the independently admitted complete USB prefix and inspect the
normal continuation's next admission boundary; do not repeat the resolved USB
search or silently discard inherited sense/power copper. Never weaken an
important-route, clearance, current, decoupling, mating or release gate to
obtain a green report. The PC, WSL and Codex app must stay running for this
local bridge; reboot persistence is not claimed.

## 2026-10-02 priority continuation: Hub / ATX before 12VHPWR

This section supersedes the current-status claims above, not their historical
receipts. Canonical boards, source schematics, policy and accepted controls were
not overwritten. Intermediate native repair, manufacturing qualification and
release are separate verdicts. Build-level coordinates below are agent-selected
declarative proposals, not selectors embedded in the generic engines.

### Integrated and tested generic changes

- `cec_priority_force_dispatch.py` now provides the bounded, additive rated
  pre-pour fallback before ordinary-worker refusal is pruned. It binds the full
  saved family, requested domains, source policy, environment and code epoch;
  requires native receiving/current/Kelvin evidence; preserves the incumbent on
  refusal; and caches unchanged requests rather than repeating searches.
- `cec_saved_family_repair.py` strictly encodes trusted native evidence tuples
  as JSON arrays before creating a durable record. Invalid keys, nonfinite
  numbers and policy values are not stringified or accepted. The original
  failure ledger and cached replay remain intact.
- `cec_force_current.py` now guards full-width tracks against native board and
  footprint track-forbidden areas, including their actual layers and polygon
  holes, in endpoint menus, direct/maze construction and saved contact replay.
  Unsupported area geometry refuses; a footprint-only or via-only prohibition
  is not silently converted into a track prohibition.
- `cec_fab_native_geometry.py` independently checks circular and rotated slotted
  drills, including same-net pairs, with typed process/board/factory floors and
  bounded, fail-closed handling. It is registered in the generic-core audit.
  `cec_fab_check.py` restores required factory severities on disposable copies,
  treats owner-named exceptions as claims rather than factory approval, and
  reports native caps/ignored checks/unsupported geometry as incomplete.
- The solver now stamps temperature-operation completion separately from net
  injection. A temperature timeout can retain a cool earlier field without
  dropping any net. Overlay, dashboard, legacy-cache display, the routing
  oracle and its independent confirmation now refuse such a partial field.
  This does not qualify numerical convergence or package junction temperature.
- Independent full-pipeline signoff uses `cec_fab_check.blocking_count`, not a
  manually maintained subset which omitted opens and artifact acid traps.

Fresh common-frozen regression: **1,283 passed in 212.20 s**, plus three pytest
subtests, across 42 named groups. Evidence:
`build/priority-hub-atx-stable-tests-20261002.xml`. The earlier 1,033-test run is
an earlier epoch, not an additional disjoint total. Generic-core registration
passes; whole-runtime maturity/integration debt and release are not thereby
declared complete. No broad unattended campaign was started in this pass.

### Actual saved-board progress

| Artifact | Native opens | Scored DRC | Actual authority |
| --- | ---: | ---: | --- |
| Hub B `0f0c9b068373...` | 0 | 0 | Private, not admitted for release |
| ATX selected placement `96d68a8f1e70...` | 360 | 5 | Private placement, structural nonregression |
| ATX partial route `22c5f3ae5fb2...` | 359 | 5 | Explicitly UNADMITTED: complete current/sense proof fails |
| 12VHPWR current prefix `325ee4e80b64...` | 162 | 0 | Independently received additive prefix, not board closure |

ATX placement first moved U3/C1/C2 as a rigid group 6 mm left, then C15 and
the D1/R1 group to open a native-clear 6.535523 mm corridor. The second saved
transaction preserves all 154 original copper primitives and settled fills,
passes complete native placement, 378 actual Hub-B mating checks, and all 14
bypass assignments. Standard power-independent state rebind changes exactly
the six authorized component poses. Existing silk-report identity exchanges
remain diagnostics, not a manufacturing pass.

The seven newly constructed partial-current segments reduce one open, but
J3.12 remains in a separate rated component. U12.10 and U63V31.3 are genuinely
disconnected from RS3.1 before and after: a clipped proof must not mistake this
unknown baseline for a verified sense branch. The original locked force cap
`d19a43df...` also overlaps every tested positive-sense departure outside the
shunt pad. A detached, ownership-bound endpoint replacement plus the shifted
new cap leaves both sense branches clear; it has not been saved or promoted.

An outer-layer frontier screen explains the remaining ATX plateau rather than
spending more unchanged seeds. At the actual 20 A aggregate basis and 1.25
margin, F.Cu and B.Cu fixed-obstacle chains separate J3.12 from the other domain
terminals even after ordinary movable SMDs are omitted. This is a statement
about the supported full-width representation, not arbitrary multilayer board
infeasibility. A concrete B.Cu completion has nine of ten segments clear; its
sole crossing is blocked by two protected 5 V trunks and their exact patches.
Those 5 V domains also require 6.535523 mm at the unchanged owner contract.
Next work is an explicitly scoped pre-pour crossing reservation and qualified
terminal-face regeneration, not unverified via current credit. See
`build/atx-outer-frontier-20261002-a/{receipt,chain-witnesses,transition-feasibility,transition-scope}.json`.

Hub B corrects C37's edge margin to 0.825 mm (0.8 mm required), repairs its
owned ground branch and passes the current ATX-body/vertical/vent screen.
It is still private: one real C37/D8 reference-silk collision exists and an
independent drill inventory found adjacent RJ-45 shield slots overlapping by
0.099998 mm. KiCad's native round-hole provider skipped that slot pair; zero
scored DRC was not coverage of this defect.

Detached Hub row planning now uses 16.90 mm pitch, passes actual mating and
foreign-power-pour clearance, and retains protected VCC declarations. All 20
affected signal intervals have native-clear plans (45 owned old segments,
143 other tracks retained). Surface-material attachment, not reduced
clearance, resolved two boundary cases. Two return seats and a full-class
1.0 mm outer VCC_P3 path were screened using the actual 0.5 A x 1.25 demand;
no new via or barrel-sharing credit is used. A saved/refilled transaction,
95% reference-plane proof and explicit power-bearing state replacement remain
required. Normal power-independent safe-sync is correctly inapplicable.

12VHPWR's canonical pre-pour fallback was exercised once in 35.227641 s and
independently received in 7.270961 s. Three additive 2.5 mm F.Cu segments
preserve all 790 originals, settings and sidecars, with 12/12 native clipped
legs retained. Sizing uses the actual **9.2 A**, 1.25 margin, 30 C rise and
project floor, not the topology binding's nominal 8.33 A. Dashboard artifact:
`pass-build-12vhpwr-standard-eb75958e3c`; counts remain 162 opens and zero scored
DRC. This is current-prefix progress, not routing completion or thermal release.

### Manufacturing truth and retained controls

One 5.686 s frozen read-only comparison preserved all three full input families
and all 413 production Python files. Hole inventories complete; full factory
evidence remains incomplete because both native silk categories hit 199-record
caps and filled-legend features are not yet fully supported.

| Input | Hole findings | Legend-dimension records | Opens | Factory complete |
| --- | ---: | ---: | ---: | --- |
| Hub B | 11 | 316 | 0 | false |
| ATX selected placement | 8 | 387 | 360 | false |
| Archived PCIe2 final-fab-review v103 | 32 | 164 | 0 | false |

These expose inherited manufacturing debt, not geometry mutations to the PCIe
control. Counts are records, not deduplicated physical defects. Hub includes
the RJ slot overlap, two mixed pad/via gaps and eight H1 satellite-ring gaps;
ATX includes the same eight H1 gaps, FID3 in an opposing-capacitor reservation
and two acid-trap records. All three have two USB NPTH gaps of 0.1651 mm versus
the current 0.20 mm factory floor. A source 0.15 mm owner exception is not
supplier approval. Regular-pad hole spacing is at least 0.45 mm; the selected
filled/capped mixed-hole process requires greater than 0.45 mm. References:
[JLC capabilities](https://jlcpcb.com/capabilities/pcb-capabilities) and
[POFV process](https://jlcpcb.com/news/free-via-in-pad-6-20-layer-pcbs-pofv).

Reports: `build/factory-rigor-native-controls-20261002-a/{comparison,hub,atx,pcie2_archive}.json`.
The actual M2 satellite radius proposal is 1.65 -> 1.76 mm: central 2.2 mm
drill, 4.4 mm contact land, mounting centers and courtyards remain fixed;
nominal minimum hole gap becomes 0.46 mm. Drill voids really move, so this is
not falsely labeled identical material. No generic guard or manufacturer
limit is weakened to qualify the proposal.

The first fine-grid Hub field diagnostic timed out in the temperature phase
and its build-level JSON report also failed on internal layer-pair tuple keys.
Neither failure was a thermal pass. Reporting now encodes those physical
layer pairs explicitly and latches partial-operation status. Existing source
heat budgets remain unchanged; unverified component/package models, uncovered
active references and minimum barrel plating/current-sharing qualification
remain explicit release limits. Average supplier plating is not a guaranteed
minimum, and a board-field image is not a junction-temperature certificate.

### Later same-pass receiving: saved Hub row and scoped topology fix

One 63.826 s private Hub row transaction saved/refilled
`build/hub-row-private-bundle-20261002-a/hub/board.kicad_pcb`, SHA256
`abbcc8afa81df5612230f206b85178665c927482b25f159888caf7a5dbb242db`.
It is explicitly **REFUSED**, not promoted or wave-ready:

- Native opens remain zero, but three new dangling-track findings exist.
- CAN reference coverage is 100%, coupling 81.3% passes the unchanged 60%
  floor, but skew 6.348 mm fails 4 mm and four acute/covered backtracks exist.
- Complete native drill findings improve 11 -> 1. The 16.90 mm row and H1's
  1.76 mm satellite radius remove the slot/M2 issues; the original USB S1/via
  gap is still an unresolved manufacturing blocker.
- Definite lower-copper GND reach proves all 131 original pads and both newly
  seated return vias with all 295 physical drills modeled. This proves positive
  reach only, not isolation, ampacity or fabrication.
- All 12 current domains retain source/sink connectivity. VCC_P3 additionally
  gains trace-only rated connectivity at the unchanged 0.5 A x 1.25 contract.
- 1,185 retained track/via primitives remain exact. Protected power loses zero
  native material; VCC_P2's terminal fills grow locally on F.Cu and PWR during
  refill. Authored outlines/settings remain exact, not all filled bytes.
- Three newly enumerated silk findings replay as exactly unchanged physical
  collisions, not a count-only exception. Source families and the original
  construction code epoch stayed unchanged through receiving.

An independent native forensic reproduced the exact three dangling findings.
Two are real retained unused trace tails after interior side taps; the third
is a physically connected short overlap whose native endpoint heuristic
credits its other end. None intersects any of the 295 native drill capsules;
none qualifies for zero-physical-material deletion. Twenty-four rotated,
translated, mirrored and direction-reversed native fixtures pass expectations.
Four disposable saved CLI fixtures reproduce dangling counts 2/1/0/0, all
with zero opens. Reports: `build/hub-dangling-forensics-20261002-a/`.

The first detached follow-up is still blocked and is **not a newer saved
board**. It removes the original three dangling ends but exposes a retained
H leaf, keeps two H acute bends and has 5.451 mm skew. Reference remains 100%
and coupling 79.9%. It passes 378 actual current ATX `96d68a8f...` checks;
that binding is distinct from the saved row's former `007484d8...` peer and
380 checks. No failed pair preflight was allowed to consume another save,
refill or whole-50 solve merely to reproduce a known failure.

The generic causal fix changes `cec_route_quality.analyze_board`: a UUID scope
now filters **findings**, never the incident graph. Retained tracks still own
junction angles and degree. Single-track heading/arc findings stay scoped;
unrelated inherited defects remain excluded from a local report. Before this
fix, scoped tests missed a new-to-retained backtrack and invented a two-leg
vertex after discarding a third retained branch. Red native tests reproduced
19 failures (including 16 transformed subtests). Fresh bounded precision,
staged-route, craft, copper-normalization and fab-review consumers pass:
**230 tests plus 18 subtests in 1.49 s**. This includes the earlier focused
100-test run; do not add the overlapping totals. New frozen source:
`cec_route_quality.py` SHA256
`9e89dafe79999de869095cc52ee1180bd20b452f8fb60a64b76173a8eedf27ea`.
The earlier 1,283-test common run predates this single source correction.

A 0.600 s read-only native semantic replay checks Hub source/row, latest ATX,
12VHPWR prefix and the archived PCIe2 v103 fab-review control. All-UUID scope
equals the full graph and empty scope has no findings on all five; every input
family and all 413 source files remain unchanged. PCIe2's whole craft remains
clean; the actual Hub row now exposes three mixed new/retained junctions in
created-only scope. This is a semantic/craft replay, not a full manufacturing
or full-pipeline replay. Report:
`build/route-scope-native-replay-20261002-a.json`.

### ATX coordinated crossing proposal and remaining authority boundary

The bounded native pre-pour hypothesis has a concrete planar solution after
the exact two 5 V transition-face/patch replacements: all ten corrected
0/45/90 B.Cu segments pass detached full-width foreign/edge/keepout screens at
6.535523 mm, with zero new vias. C65V1's 0.6 mm rigid east shift preserves all
25 bypass assignments and passes native holes/courtyards/rule areas and actual
peer screens. Its supply and both GND returns are missing before and after;
this is not a completed decoupler. Existing 5 V field contact reaches 9/10 via
faces, matching the incomplete source; alternatives reaching all ten fail
unchanged sense separation and are refused. Existing 5 mm trunk and barrel
capacity debt is not converted into a current grant. Native read-only work
consumed 6.624/60 s; no ATX PCB was saved by this hypothesis.

`build/atx-prepour-crossing-20261002-a/construction-hypothesis.json` binds five
old track UUIDs, two B.Cu patch UUIDs, full path/cap/witness coordinates, C65's
ownership and mandatory independent receiving. It is not an executable or
accepted receipt. Its historical epoch is preserved; fresh native receiving
must bind the later scoped-graph epoch before any new saved candidate.

Both row and power-crossing work expose the same real authority boundary:
`cec_priority_replacement_receipt` deliberately authorizes only closed
qualified signal-prefix replacement with unchanged placement;
`cec_route_placement_admission` deliberately authorizes power-independent
support motion. Neither truthfully admits these power-bearing transitions.
They remain unchanged. A separate generic saved-proof-bound power/contact
placement transition must preserve original receipts and bind exact allowed
changes, native retained boundaries/contacts/current/model policy, all actual
peer and critical-pair proofs, source family and code epoch. Until that exists
and the geometry qualifies, private construction is not canonical authority.

### Dashboard receiving

The current Hub row diagnosis is published under
`pass-priority-closure-review-20261002-a-hub-standard-rev2-f4e4b32949`, explicitly
BLOCKED, 0 opens / 3 scored DRC. The exact saved PCB hash is journaled and the
eight F/B/no-body and all-six-layer panels were fetched from Windows localhost
and matched byte-for-byte to their immutable artifacts. No old board fallback,
FEM filler or AI-generated copper view is used.

The updated dashboard runs on port 8090 in the bounded WSL user service
`cec-dashboard-priority-20261002`, with restart-on-failure, 2 GiB maximum memory
and heavyweight build watching disabled. Windows HTTP returns 200 and the new
partial/legacy-temperature-field warning is present. This is service recovery
while WSL is alive, not a claim of Windows-reboot persistence.

### Final same-pass receiving: physically closed Hub routing candidate

The rejected row above remains immutable historical evidence. A distinct saved
and refilled child now exists at
`build/hub-row-private-bundle-20261002-b/hub/board.kicad_pcb`, SHA256
`a5cbdd0a96a28737c4cc29cbbad0b18882e3a8a086ed91e7cc1bc6c5fcd94420`.
Its one saved worker consumed 60.452 s. The complete saved native receiving
has **0 opens, 0 scored routing DRC, 0 dangling endpoints**, all 50 constraints
passing, and no critical CAN craft defects. CAN_H length is 148.344721 mm;
CAN_L is 150.052875 mm; rounded skew is 1.708 mm, coupling 79.3%, and reference
coverage 100%. This is routing-stage evidence, not fabrication release.

The heading-state endpoint roadmap found a legal bent channel between two
obstacles whose uniform horizontal corridor intervals do not overlap. That
is why a single-channel heuristic failed; it was not proof of physical
impossibility. Removing only the proved unused upper CAN_L entry suffix
reduced excess length. The first shortened boundary retained a source gap
0.074 nm below the 0.2 mm clearance floor. A width-derived 62,500 nm outward
offset gave actual margin; the minimum was not waived. All 20 positive native
material boundaries and 87 new route guards pass in the saved/refilled file.

This final CAN transaction replaces 41 owned signal segments with 51 new
ones. All 1,216 retained copper primitives, 1,373 retained native items, every
filled zone, original power/ground geometry, pad definitions and poses remain
exact relative to the rejected-row source. All 295 drill geometries and
43,365 native drill pairs are inventoried. Original 131 GND pads and the new
row returns retain positive native contact. The current/model gate and 12
native authority-contact domains pass; this is not a claim that all 12
trace-only width graphs pass or that barrel/package thermal capacity has
been qualified.

Remaining Hub blockers are explicit: the power-bearing placement transition
has no lawful derived-state receipt; five ordinary craft advisories remain;
one factory mixed-hole clearance violation remains at J_USB.S1 and via
`5da80ff8`; legend evidence is incomplete (316 dimension records, 12 unsupported
records, native capped reports); and thermal/component qualification is not
complete. The existing generic normalization tool correctly refuses to
silently delete locked current-group members merely to clean a report.
No authority receipt was fabricated, and `accepted` and `canonical_wave_ready`
remain false. Kelvin replay is complete but not applicable to this Hub's
zero typed current-sense inputs, not an applicable isolation failure.

A separate 5.665 s detached ordinary-craft review proves four material-neutral
deletion hypotheses (three exact collinear containments, one rational/native
capsule containment despite a 1 nm centreline difference). They are locked
members of `CEC_LOCAL_ENDPOINT_NECKDOWN` and still require explicit group and
frozen-power replacement authority. Hypothetical removal has 0 opens and 0
dangling ends, leaving the real DETECT4 acute bend. The DETECT4 advisory was
introduced in the rejected row and retained in the final CAN child; it is not
being relabelled as inherited from the earlier `0f0c9b...` board. A 441-seat,
width-derived local USB return search finds no legal central site against
actual GND netclass, copper, pad/drill and factory hole rules. This finite
search is not a no-path proof; a previous micron-margin proposal remains
diagnostic only. No additional PCB was saved by that review. Evidence:
`build/hub-row-private-bundle-20261002-b/ordinary-craft-readonly-proposal/proposal.json`.

### Final same-pass receiving: ATX saved power-face construction

One actual saved/refilled ATX construction now exists at
`build/atx-prepour-construction-20261002-a/candidate-UNADMITTED/board.kicad_pcb`,
SHA256 `f14600a337407a4ffbfeee11a7c071e324e3c39887e827658e28067430d5ad70`.
It is not the earlier overlay/hypothesis or partial-route child. Cumulative
detached work consumed 12.200 s; save/refill/proofs consumed 6.748 s.
**Opens improve 360 to 352; scored DRC remains 5 to 5.** All 560 raw native DRC
identities remain exactly unchanged, with no new or removed identities.
Changed/touched craft faults, new native dangling ends and zero-length new
tracks are all zero. Existing whole-board dangling and manufacturing debt
is not erased by those scoped statements.

The construction contains 21 new 6.535523 mm tracks and 20 new 0.25 mm sense
tracks, exactly five original track and two B.Cu patch replacements, one
actual native-netted +5 V SOLID landing, and C65V1's rigid 0.6 mm east move.
There are no new vias or removed original copper UUIDs. Outside declared
ownership, all native copper, authored/filled zones, barrel geometry, poses
and complete companions are exact. The 3.3 V high-side native authority domain
improves from three components to one; its width-only and all-pad graphs
improve five to one. All 27 pair-connectivity comparisons across the complete
nine current domains show zero loss of previously connected terminal pairs.

The SOLID landing is real saved material, with 33.5333656 mm2 conservative
lower fill and a finite 0.05 mm interior-pad witness. Nine of ten existing
field faces contact it, matching the incomplete source; no tenth contact or
zone/barrel current capacity is invented. The high-side finite track has
10/10 field contacts and 1.119735 mm separation from the new sense branch.
Four affected clipped Kelvin legs pass (U12.p/U63V31.p and U11.n/U65V1.n).
U11.p/U65V1.p remain unknown: the 5 V high-side authority still has five
physical components. Existing rail/barrel capacity and C65 supply/return
completion are still unqualified. No full-board current qualification or
power-replacement/state receipt is issued.

One evidence harness mistake was root-caused, not patched over: its original
`saved_diagnostic.py:104` used `preserve_unconnected=True`, which
`cec_stage_admission.evaluate` explicitly documents for cosmetic-only passes.
That mode naturally refuses the 360-to-352 routing improvement and removal
of `/SENSE3V3_HI` from the open-net set. A separate 0.113 s exact-saved-score
replay uses the unchanged ordinary repair mode (`require_strict=True`,
`preserve_unconnected=False`, no open growth, no new-net/DRC exemptions).
It accepts `strict_structural_improvement` with no reasons; all 27 native
pair-delta comparisons independently agree. No production admission gate,
original PCB or original receipt was edited. Endpoint signature change is
forensic, not itself a hard gate. Geometric repair-score acceptance remains
distinct from the missing qualified power/state receipt. Evidence:
`build/atx-prepour-construction-20261002-a/admission-mode-forensic.json`, SHA256
`fa3c8453b900ca7cf62a28aaf5c43d1a1397f595f78838e76838674663287061`.

### Latest private stack and exact dashboard receiving

The two latest saved constructions above are also rechecked **against each
other**, not only their earlier peers. Read-only production assembly gates
pass all 378 body/contact checks, three contact groups, dead-bug transform,
standoff/vertical engagement, and both C37/C1 vent reservations. Vent
clearance remains 4.3 to 6.5 mm against 3 mm minimum. All source/peer families,
contract and the complete 413-file production epoch remain unchanged. The
1.119 s report is
`build/priority-closure-review-20261002-b/latest-stack-receiving.json`, SHA256
`61c713773281b9cfc10eb1e6fa72c6dd9cc096ff68d97cdc1967f1fe4b158a70`.
This is geometric qualification of the stated nominal/tolerance model, not
sample fit or power/fabrication release.

Both new boards have independent, exact-sha journaled private dashboard
publications, explicitly BLOCKED/state-unadmitted:

- Hub: `pass-priority-closure-review-20261002-b-hub-standard-rev2-b2298ae82f`,
  0 opens / 0 scored routing DRC.
- ATX: `pass-priority-closure-review-20261002-b-atx-24pin-rev3-e55b2b0219`,
  352 opens / 5 scored routing DRC.

Every front/back no-body image and all six native copper-layer plots was
fetched through Windows `localhost:8090` and matched SHA256 byte-for-byte to
its immutable native artifact: 16/16 panels exact. The root reviewed both
saved-board six-layer views and the ATX before/after construction view. The
app-open requests returned queued, so no claim is made that the tabs are
already visible in the user's focused window. There is no older-board
fallback, proposal-as-routed-board presentation, or FEM-only invented copper.
Archived PCIe2 v103 remains unchanged at SHA256
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.

## October 2/3: retained USB connector, physical ground completion and bounded routing

The owner correctly challenged a proposed external-source USB-C replacement:
the shipped-source ATX board was already fabricated with locating holes.
The local comparison confirms that shipped ATX J5 and current Hub J_USB have
identical 22 pad/drill geometry records, including the nominal 0.165102 mm
copper-to-locating-hole gap. The current XKB U262-161N-4BVC11/C319148 drawing
also contains those locating posts and lands. This is inherited geometry,
not a new Hub placement defect and not a general prohibition on locating holes.
The current published factory NPTH-to-copper floor is 0.20 mm; two gaps fall
below it (four below the separate project floor). A successful prior order
is relevant evidence, but the exact accepted ATX CAM/order exception has not
been recovered. No manufacturing waiver, drill shrink or land trim is invented.
The existing connector is retained; no replacement/BOM change is authorized
or performed. The earlier Molex suggestion is not established as necessary.
Evidence: `build/hub-usbc-authority-20261003-a/prior-fabrication-comparison.json`,
SHA256 `d52ff942e8a42ae95fa387848798dcf2a3fa7e041ba11953e300d6ec50584fe8`.
The bounded search and replacement screen remain separate historical evidence.

### Latest Hub: saved ordinary craft and ground return

The saved Hub child is
`build/hub-detect-usb-private-bundle-20261003-a/hub/board.kicad_pcb`, SHA256
`9a768731396f1148cb83172e74708e5ba994b244320e8e4f0961e1d41fc237c2`.
It contains the actual small DETECT4 chamfer and USB ground dogbone/via, not
a proposal overlay. Native receiving finds 0 opens, 0 scored routing DRC,
0 dangling ends and all 50 constraints passing. All 131 original ground
terminals retain positive material reach; all 295 actual drill inventories
and 43,365 pairs are checked with no hole-spacing findings. Power geometry
is unchanged. Factory legend/USB-gap, frozen-state/power authority and
physical/current/thermal qualification debt remain; raw inherited native
DRC is 769, not zero. Routing closure is not fab sign-off.

### ATX: 352 -> 339 -> 203 -> 180 opens, no new DRC

One field-guarded ordinary transaction saved 23 tracks and closed 13 opens,
to 339, at SHA256
`6b8b0617742d88d7d72fd330b2813d0b53d2027a9d573be61792c2bf48691976`.
The earlier 338-open trial introduced field-coupling defects and remains
rejected, not silently promoted as the winner. The generic proposal guard
checks candidate routes before committing them; new signal-via/ground-reference
changes remain explicitly unsupported without exact detached refill evidence.
Production ordinary completion uses that guard. The unchanged archived PCIe2
native/field control also replays without a regression.

The next saved construction adds the two actual profile GND planes and 93
process-qualified local ground portals, closing 136 further opens (339 -> 203).
Saved child: `build/atx-ground-portals-20261003-a/candidate-private/board.kicad_pcb`,
SHA256 `67f848d711d6896da69bef9af8164b7306c5370d95e0d43807a72fb05f4a90a2`.
Each new barrel positively contacts both filled planes; 111 native pad/barrel
contacts are witnessed. The source contained no actual GND tracks/vias/zones,
so historical sidecar local-via records were not treated as physical copper.
Original power copper, fills, placements and all unaffected current graphs
remain exact. Local POFV process ownership is explicit; no general clearance,
width, hole-spacing or current exception is added.

The original receiving refusal is preserved. It compared a native cut's
workload counter (`vertices_examined`) as if it were physical evidence, and
the new unrelated drill contours increased that count. The bounded typed
comparator in `cec_force_sense_evidence.compare_clipped_isolation` ignores only
validated elapsed time and workload-count values at their exact native paths.
Statuses, cut/contact geometry, isolation witnesses, bounds, incomplete fields,
budgets and refusals remain significant; unknown stays unknown. 82 focused
tests pass. This comparator is consumed by the build receiver; canonical
absolute affected-leg admission is unchanged, and dispatch integration is not
claimed. A separate immutable semantic receipt accepts GND structural scope
only (4 verified / 12 unknown Kelvin legs), SHA256
`31d869b104ac0dcd1c720d123fee647575b26bde23775334d8bcac463d410314`.

One final bounded ordinary pass uses the production net selector plus explicit
retained supply/pair/Kelvin ownership exclusions, not a broad voltage substring
over hierarchical sheet names. In 38.14 s routing / 86.49 s total, it saves 75
tracks across 18 nets, 23 joins, 0 new vias; opens improve 203 -> 180. Latest:
`build/atx-ordinary-broader-20261003-a/candidate-private/board.kicad_pcb`, SHA256
`0573608211fb3d74483ce7af195f8347310bd041cfefca30f30e951198b0f980`.
All 515 original native UUID records, pad/pose/settings, power/GND definitions
and fills, nine current graphs, unmodified net graphs, sidecars and Hub mating
remain exact. DRC identities stay 560 -> 560 (5 scored), field 0 -> 0,
touched craft/new dangling 0, and no new full50 failure IDs. Eight inherited
mount hole findings and nine full50 failures remain. Strict ordinary structural
receiving passes; no power-state/fab/wave authority is issued. Receipt SHA256
`26b7f87b8ff9375f988ad473899446e2c03f68bea9cc5adb2b46a7a108b43eb7`.

The main remaining search cost is repeated unsupported via/reference proposals,
not an exhausted overall routing lease or proved physical impossibility:
15,053 such alternatives, 17 actual field blockers and 18 per-net frontiers
hit their two-second bounds. Supply opens (+3V3 52, +5V_SYS 11, +5VSB 7,
+5V_MAIN 6), 20 GND opens and USB/CAN/Kelvin scopes remain distinct. A wider
last-mile retry cannot replace the missing priority current/terminal authority.
The reviewed ATX 20 A aggregate, 1.25 margin and 30 C rise remain unchanged;
actual selected outer/inner copper is 70/15.2 micrometers. Full rated-width
terminal launch feasibility and coherent per-contact allocation are still
required, not substituted with Default-width supply traces.

### Generic manufacturing repairs, with scope and cross-board limits

`cec_legend_repair` is wired into `cec_fab_repair.repair`: visible native legend
height/stroke minima are repaired without moving/rotating/hiding/deleting text,
changing strings or electrical/mechanical geometry. Locked items need explicit
ownership. Filled circles and supported cardinal rectangle cores have native
minimum-feature proofs; unsupported filled polygons stay unknown. Detached,
saved/reloaded exact cross-board previews remove dimension findings Hub
316 -> 0, ATX 387 -> 0, PCIe2 164 -> 0, with source hashes unchanged and a
second-pass no-op. They do not resolve silk collisions, clipping or placement.
These are unadmitted dimension previews, not fab candidates.

`cec_mounting_contract` now owns a parameterized radial stitch repair, also
wired into the factory-repair entry. Exact declared mounting role/BOM-position
exclusion selects mounts, never arbitrary connector arrays; locked geometry
requires explicit authority. Only satellite positions can move within the
unchanged central land. Bore, central contact, screw/hardware envelope, pose,
pad size/drill/net/layers and courtyard are unchanged. The vendored slim M2
mount now uses a 1.8 mm satellite radius, providing nominal 0.50 mm spacing
without increasing its 4.4 mm contact or 6.5 mm courtyard. Native rounding
cannot reduce the mandatory floor; already compliant mounts are not enlarged
merely to add a repair guard. Reverse-primary-drill span unknowns remain unknown.

Production cross-board detached replay proves whole-board serialization returns
exactly to the original when the declared satellite moves are reversed:
ATX 8 hole findings -> 0 (8 moves), Hub 0 -> 0 (no move), archived PCIe2
32 -> 0 (32 moves). No board is saved by these cross-replays, the archive is
unchanged, and the latest ATX 180-open child still contains the eight inherited
findings pending an independently received repair. Evidence lives under
`build/mounting-integrated-cross-20261003-a/`. The combined headless mount/fab,
legend, typed-sense and lazy-field group passes 273 tests in 10.45 s;
69 focused native mount/legend cases pass separately. No full interactive suite.

### Actual-copper thermal runtime: completed F, not thermal qualification

The thermal raster gate now checks every requested native terminal component
before solving. A lost coarse contact can trigger bounded witnessed refinement,
but neither invented copper nor blanket eight-neighbor shortcuts. The Hub's
exact joined thin diagonal needed 0.125 mm rasterization; all 12 domains then
retain native/raster connectivity. Streaming keeps all 354 net/layer copper
pairs: 72 active dense arrays, 282 inactive losslessly packed masks. Thermal
conductance, overlay and inactive-temperature contributions are not omitted.

E's 321.094 s attempt timed out before one temperature iteration. Passive
stack traces root-caused two eager `setdefault(..., np.zeros(full_grid))`
allocations inside per-edge loops. The frozen lazy-allocation fix changes only
allocation timing, not equations/dtype/order/current/cooling; 380 tests plus
5 subtests pass, including exact-array parity and allocation-count tests.
The bounded microbenchmark improves Joule mapping 0.404110 -> 0.004909 s and
current mapping 0.159302 -> 0.005948 s; these are not board-level speed ratios.

One fresh F solve on exact Hub `9a768...`, with the identical reviewed heat,
current and cooling recipe, completes in 102.899703 s: three temperature
iterations, operation/temperature-computed flags true, all 12 currents injected,
no missing/dropped nets, numerical current/energy conservation verified.
All source/family/helper and 415 production-code files are unchanged during F.
It models 128.300272 C peak at 50 C ambient, in U7's board-contact patch;
0.569511 W copper plus 3.304781 W components, 3.874292 W total. This is an
unqualified diagnostic, not a component-junction temperature or thermal pass/fail
for the actual intended operating mode. Mutually exclusive mux inputs are
still combined, D1 upstream extraction is omitted, 16 source/package models
remain unverified, and barrel minima/contact models and mesh convergence are
unqualified. No budget/current/cooling reduction is used to manufacture a pass.

Sampled worker high-water is 3,410,208 KiB, not a guaranteed 2 GiB RSS limit;
the 2 GiB preallocation bound is a reservation estimate, not an OS process cap.
F evidence: `build/hub-exact-field-screen-20261003-f/field-screen.json`, SHA256
`8dd6bb14691ed6564daeedaadb8efd7a6b996498274d62c24c97695605c087fe`.
The root and solver agent inspect the actual six-layer copper/thermal overlay
and source heat maps. Its contrast range is not the actual peak, and its long
header is clipped: neither should be presented as a qualified thermal certificate.
No unchanged retry is dispatched; native workers are stopped after receiving.

### Current dashboard truth

The exact saved Hub is published BLOCKED at
`pass-priority-closure-review-20261003-a-hub-standard-rev2-b56bcddf03`
(0 opens / 0 scored routing DRC). The saved 203-open ATX intermediate is at
`pass-priority-closure-review-20261003-b-atx-24pin-rev3-9cfb3d6471`.
Both sets of front/back images plus six copper SVGs are fetched through
Windows localhost:8090 and match all 16 artifact hashes exactly.
The latest 180-open ATX is separately published BLOCKED at
`pass-priority-closure-review-20261003-c-atx-24pin-rev3-ebe4fe606b`;
its output hash binds the actual `057360...` saved child, not an older fallback.
The latest ATX front/back and six native layer panels also pass Windows HTTP
SHA256 receiving, 8/8 exact (24/24 across the three publications above).
All images remain private construction reviews. Neither board is fab-ready;
no external assembly order, upload, token request or fabrication waiver occurs.

## October 3: actual pour protection, explicit supply contracts and native THT export

This slice responds to the requirement that real power copper, rather than
small fallback traces or invented fill, must supply the intended terminals,
and that Freerouting must not add transitions for connections already proved
through actual plated holes. It does not mark the Hub or ATX fab-ready.
Source boards, archived controls and prior receipts are retained unchanged.

### Generic power-distribution adapter and the independently received ATX prefix

`cec_current_topology.distributed_supply_contracts` reads the existing executable
load contract. `cec_distributed_supply` consumes it in the existing
`priority_power_distribution` tier of `cec_synth_pipeline`, not as an ordinary
Default-width Freerouting fallback. Required width includes the full contracted
load, actual layer copper, allowed rise and project/process floors. Force-owned,
Kelvin, differential-pair and reference-ground scopes remain distinct.
Missing supply budgets produce typed deferrals; no current or contact sharing
is guessed, no reviewed margin is reduced, and no new neckdown exception exists.

The current ATX +3V3 contract is 0.2048376 A including its existing 20 percent
margin. Its planar routes require the unchanged 0.20 mm project/process floor.
These are low-current regulator distribution branches, not replacements for
the unchanged 20 A, 1.25-margin force-bus contract. The source has no saved
+3V3/+5V_SYS/+5VSB distribution pour; the +3V3 rectangle in the pour plan remains
intent, not actual filled copper or qualified power-state evidence. Remaining
high-current terminal leaves and unrated supplies cannot use this adapter as
an admission waiver. The current implementation deliberately does not grant
barrel/zone current capacity or create layer transitions.

Construction uses bounded attempts/deadlines, supported single-face pads,
finite native contacts, actual outline/rule-area/foreign-copper/field guards,
and separate connectivity data without relabeling the board's nets. Saved-board
receiving preserves every old native item and fill plus placement, companion
files, current graphs, other-net graphs, mating and typed Kelvin evidence.
An incomplete accepted private prefix is retained explicitly as incomplete;
the production tier cannot silently advance or fall through to ordinary routing.

The first private A trial closed 37 opens but crossed two tracks into an
arbitrarily named +5V_MAIN landing. Its refill changed an existing fill and six
typed Kelvin geometry records. The no-incursion/preservation gates rejected A.
It is retained under `build/atx-distributed-supply-20261003-a/`, not selected.

The cause was name-dependent route reservation, not a lack of board space.
Actual non-reference zone outlines now protect direct and cached route checks,
obstruction analysis and DSN keepouts independently of private naming prefixes.
Partly filled/unfilled power intent stays protected. Actual reference-plane
role/net may yield as a plane; a misleading `GND Plane` name on a non-ground
net does not. Same-net routing is allowed, unknown/collision-error geometry
fails closed, and this broader guard does not authorize removing arbitrary zones.

The corrected B candidate, produced from exact source SHA256
`0573608211fb3d74483ce7af195f8347310bd041cfefca30f30e951198b0f980`, has SHA256
`7a0d3318bc0ef2f4a6deb0ec11a787a2695aff2c2ad7e08dac1b24fd9098c3b6`:

- 37 additional joins, 78 new 0.20 mm F.Cu tracks, zero new vias or zones;
  180 -> 143 opens, a 20.6 percent reduction.
- +3V3 native components 53 -> 16; its remaining 15 opens are not hidden.
- Scored routing DRC 5 -> 5 and raw native DRC 560 -> 560, with no introduced
  structural identities, field/craft failures or native dangling failures.
- All 590 original copper items and filled geometry remain exact. Nine current
  graphs and typed Kelvin evidence remain unchanged: four passes, zero failures,
  twelve unknown legs. Unknown is not qualification.
- Eight inherited mounting-satellite manufacturing findings remain. The earlier
  detached generic mounting repair has not been admitted to this candidate.

Production and independent receipts are
`build/atx-distributed-supply-20261003-b/production-proposal.json` and
`build/atx-distributed-supply-20261003-b/receiving-receipt.json`.
The bounded search took 6.440 s and 256 attempts; original independent
receiving took 62.104 s. This is accepted private structural progress, not a
completed power-distribution tier, qualified frozen power state, wave or release.

### Actual plated-barrel and saved-fill proof before excluding router pins

`cec_fr` now distinguishes a supported plated through-hole/full-span via from
an NPTH, multilayer-masked SMD or partial/secondary/backdrilled hole. Required
track/pad contacts must meet actual copper outside all drill voids. Outer
primary endpoints reversed by a physical footprint flip are the same complete
through span; this supersedes the earlier blanket reverse-primary unknown in
the mounting paragraph above. Unsupported spans still remain unknown. This
geometric contact proof does not certify barrel ampacity or contact resistance.

`filled_tht_exclusion_pins` reads actual saved inner fill and annular material,
subtracts actual holes, verifies every physical duplicate-pad alias and groups
contacts only through proved supported barrels. It retains an accessible
logical router representative for every filled connected component. Isolated,
sole, uncovered or unknown pins stay routable. Bounds on inventories, vertices,
time and native identity prevent an unsupported/expired observation from
silently suppressing an open. Original boards are never saved or refilled.

KiCad's native fractured fill chains exposed another false-unknown path.
The contact-only fallback unfractures a snapshot and uses a 2 nm native inward
guard. Native subtraction must prove zero exterior material relative to the
original saved polygon before accepting the lower-bound contact polygon.
Unfracture alone was measurably different and was not accepted as equivalence.
No `buffer(0)`, grid snapping, fill rewrite or area-tolerance admission is used.
Exact native membership, UUID/net/layer and filled-geometry epoch are rechecked.
The stricter Kelvin isolation model is not replaced by this contact proof.

### Real DSN replay exposed and repaired a duplicate-pad alias bug

Real opt-in export found that the old pin-removal regex removed the `S1` portion
of duplicate USB shield tokens such as `J_USB-S1@1`, leaving orphan `@1` tokens.
Balanced DSN syntax alone missed that failure. The replacement lexer operates
only on whole network pin atoms, respects quoted strings, and binds duplicate
aliases to the actual native board. Prefix neighbors, image-library tokens,
literal `@` pad numbers and non-network text are not substring-matched.
Ambiguous/incomplete alias inventories fail before modifying the export.
The Kelvin, force and THT export call sites all supply that native identity.

Final-epoch real cross-board DSN replay under
`build/native-tht-dsn-cross-replay-20261003-d/` proves:

| Board | Excluded logical ports | Whole exported alias tokens removed | Kept component representatives |
| --- | ---: | ---: | ---: |
| Hub | 25 | 28 | 6 |
| ATX | 22 | 27 | 1 |
| Archived PCIe2 control | 15 | 20 | 1 |

Exactly the requested tokens disappear, no new tokens appear, representatives
remain, and opt-out re-export to the same private destination is byte-identical.
All original board/family hashes and 416 production-code identities remain
fixed; the archived PCIe2 control is not saved/refilled/updated. Neither a THT
exclusion nor an export replay grants power-state or fabrication authority.
Summary SHA256:
`628aea486f064615d404c96219783879e3a484923ece932dd86d0eff3dc20671`.

### Final receiving, review publication and explicit remaining debt

The final frozen production epoch passes 392 focused headless tests plus ten
subtests in 5.99 s. Native/synthetic cases cover arbitrary refs/nets/rotations,
zone names, drill voids/unsupported spans, actual fractured fill, identity drift,
DSN aliases, bounded refusal and source-net/preservation parity. Scoped
`git diff --check` passes. No full interactive multiprocessing suite is run.

Read-only post-DSN receiving separately compares all 50 constraints on the
exact 180-open parent and saved 143-open child under the final code. There are
zero new failure IDs and exact retention of old items/fills; source families,
code and native report hashes are unchanged. The child still has nine inherited
constraint failures: this is a successful non-regression comparison, not 50
green design gates. The initial recorder used dictionary indexing on a Metrics
dataclass and stopped after evaluation; only reporting access was corrected.
A fresh receiving directory preserves that failed recorder's evidence.
The corrected read-only check finishes in 34.627960 s, performs zero construction
proposals and never saves/refills a board. Receipt:
`build/post-dsn-supply-receiving-20261003-b/receiving.json`, SHA256
`42b290611300fc7719c70e8db31dd14baa4f7bc1854c699b455e3216e23f4df3`.

The new exact ATX review is BLOCKED at
`pass-priority-closure-review-20261003-d-atx-24pin-rev3-7a5dca4507`.
Its source/output hash is the saved B child above. Windows localhost receiving
matches both renders and all six copper panels, 8/8 hashes; the root visually
inspects the actual front render. Publication receiving is
`build/priority-closure-review-20261003-d/atx-24pin-rev3/independent-publication-receiving.json`.
The earlier 180-open review remains separately available, not overwritten.

Hub saved copper remains at SHA256
`9a768731396f1148cb83172e74708e5ba994b244320e8e4f0961e1d41fc237c2`,
with zero opens and zero scored routing DRC, not fab qualification. Its original
USB footprint and inherited manufacturing/power-state/current/thermal questions
remain. Read-only native audit also identified a locked DETECT3 four-branch via
with two short direct stubs to an actual connector PTH. The existing cleanup
only owns supported two-track collapses and must not blindly delete that locked
four-branch fanout. Three tracks fully covered by same-net pour are observations,
not deletion or current-capacity authority. This slice prevents new unproved
THT transitions; it does not claim all historical redundant traces are removed.

The next generic work is rated supply layer/terminal transitions and qualified
remaining power branches, plus independently owned redundant-fanout retirement
and manufacturing admission. The strict current, copper, Kelvin and release
gates remain in force. No unchanged waves, new thermal qualification, sourcing
change, fabrication waiver, external upload, commit or assembly order occurs.

## October 3: rated track anchors, live maze wiring and PTH fanout receiving

The root performs the implementation, tests, native construction, independent
receiving and publication in this slice. One bounded read-only helper is
explicitly launched on `gpt-6.1-sol`; no Astra helper is launched or resumed.
Previously completed agents are not restarted. This follows the user's
preference to use the primary agent more than helpers.

### Reusable construction and importer fixes

`cec_distributed_supply` now offers existing, terminal-connected, full-current
track endpoints and midpoints as planar routing anchors, not only pad centers.
Anchors must have actual same-net native copper contact, meet the explicit
layer width contract and exclude actual drilled voids. Isolated copper,
undersized branches, unsupported item types/spans and identity drift are not
accepted. Native launch screening rejects blocked access before repeated path
construction. The candidate menu is streamed and bounded to 2,048 anchors and
65,536 pair checks. An exhausted menu is incomplete search, not a no-path proof.
Independent saved-board replay checks every accepted contact after export.

The core solver already had bounded maze routing, but its public proposal
worker and real pipeline did not forward that effort. Both now forward
`allow_maze` and `max_pair_s`; the pipeline defaults are enabled and 0.25 s per
pair. Public inputs are strictly validated. This does not enable unqualified
new-via bridges, current neckdowns, force-domain takeover, source-pour changes
or release authority. Existing full aggregate-current and receiving gates stay
in force. Actual +3V3 authority remains 0.2048376 A with its previously derived
margin already included, and a 0.20 mm minimum track width. No new budget is
invented for +5V_SYS; +5VSB remains owned by its aggregate current domain.

`cec_fr` now has a bounded shared native PTH fanout witness. Every participating
layer needs a short direct contact with actual supported plated material,
outside all real drill voids, and all incident branches must remain connected
without the redundant via. Generic multi-branch retirement uses that witness;
the importer uses the same witness before recreating a transition. It is
geometric evidence, not barrel ampacity. Power, ground, current-domain,
coupled/sensitive and same-net zone-owner cases remain protected. Locked via
retirement requires separate explicit authority; the default is still false.
No branch track is moved, relayered or unlocked by this cleanup.

Synthetic native tests cover arbitrary identities, four rotations and both
faces, undersized or isolated track rejection, drilled voids, contact/layer/net
drift, public maze parameter forwarding, protected roles, missing PTH contact,
unsupported via spans, locked-default refusal, bounded refusal and importer
non-recreation. The final frozen epoch passes **450 focused tests plus 15
subtests in 6.64 s**. Scoped `git diff --check` passes. The full interactive
multiprocessing suite is not run.

### Actual ATX saved construction: 143 to 140 to 135 opens

| Private trial | Opens | +3V3 terminal components | Accepted joins | New tracks | Search time | Total receiving time |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Rated track anchors | 143 to 140 | 16 to 13 | 3 | 7 | 14.938968 s | 60.563546 s |
| Public bounded maze | 140 to 135 | 13 to 8 | 5 | 29 | 20.984083 s | 72.793590 s |

Both are independently received private prefixes, not complete routing stages.
Neither trial adds a via or zone, necks a current track, moves a placement,
changes an original power pour or rewrites an old item. All nine current-domain
graphs, other-net connectivity, typed Kelvin evidence and original settings/
sidecars remain unchanged. There are no introduced raw DRC identities, field,
dangling, craft or full50 failure IDs. Scored DRC remains five. The two timed
trials use different input connectivity and effort; they are not a controlled
whole-pipeline speedup benchmark.

This slice closes eight of 143 opens, approximately 5.6%. Cumulatively, the
180-open distributed-supply parent is down to 135, or 25% fewer opens. Seven
+3V3 intercomponent joins are still needed; the other remaining opens are not
automatically classified as supply work. Full50 remains 27 PASS, nine FAIL,
three DECLARED and 11 N/A on both sides of the maze trial. Its inherited
failures are high-current-corridor-keepout, no-foreign-on-high-current-pour,
min-pour-cross-section, sense-body-clear-of-pour, usb-diffpair-routed-coupled,
high-speed-pair-physical-integrity, trace-width-high-current,
ic-power-ground-connected and board-routing-complete. Non-regression is not
fifty green design gates or power/fabrication qualification.

The saved 135-open board is
`build/atx-rated-track-maze-20261003-a/proposal/candidate/board.kicad_pcb`, SHA256
`4abf7ead3cf4ddb26af71f3d03f948a32ab6fe11427c563137b2eb9eda12ecc6`.
Its receiving receipt is
`build/atx-rated-track-maze-20261003-a/receiving.json`; the earlier anchor-only
receipt is `build/atx-rated-track-anchors-20261003-a/receiving.json`.

The exact new BLOCKED review is
`pass-priority-closure-review-20261003-e-atx-24pin-rev3-97969eab55`.
Source and published PCB hashes match. Windows localhost receiving matches
both native renders and all six native copper panels, 8/8 hashes. The root
visually inspects both sides of that actual saved board. All earlier reviews
remain separate and are not overwritten. Publication receiving is
`build/priority-closure-review-20261003-e/atx-24pin-rev3/independent-publication-receiving.json`.

### Hub: valid local PTH witness, but refill probe stays unadmitted

The root makes one separately identified private cleanup probe using explicit
locked-retirement authority. Generic discovery removes the redundant DETECT3
via `0e59fe32-bf91-4f2e-b66a-6e2aa78d9942`; both direct layer stubs and both
longer branches remain byte-identical. Actual connector J4.8 plated material
connects all four branches without that via. Importer replay creates zero vias
and records one PTH fanout junction waiver. Sixteen other candidate vias remain
protected or lack sufficient local evidence.

After an actual refill and save, only the filled polygons of the two inner GND
zones change. No other item, zone configuration, board setting or old track
changes. The probe stays at zero opens and zero scored routing DRC, with zero
introduced raw native DRC identities, zero new dangling/field/full50 failures
and unchanged typed/clipped sense evidence. Raw native findings remain 769.
Full50 is 30 PASS, three DECLARED and 17 N/A before and after; that does not
qualify inherited manufacturing, thermal, current or release debt. Whole craft
is already false before this probe and is not represented as a new green gate.

However, the strict reference-fill receiver refuses the probe. Native
source-minus-child subtraction reports a three-vertex 372 nm^2 sliver in each
changed GND zone, around x=35.8 mm, away from the retired via at x=14.3 mm.
Child-minus-source reports the same triangle with opposite winding, alongside
the expected local clearance fill. The inverse signed sliver suggests a native
Boolean/fractured-polygon discrepancy; it is not proof that actual copper was
removed, and it is not proof of harmless equivalence. No area tolerance, shape
normalization, fill edit or relaxed gate is used to admit it. The 0.75 mm local
observation window is not a manufacturing/current qualification rule.

The probe therefore stays **unadmitted and quarantined**, not selected as the
current Hub and not published as a fab candidate. Receipt and finite delta
diagnosis are `build/hub-pth-fill-receiving-20261003-a/receiving.json` and
`build/hub-pth-fill-receiving-20261003-a/loss-diagnostic.json`. The initial
cleanup receipt is `build/hub-pth-fanout-retirement-20261003-a/receiving.json`.
Probe SHA256 is
`a6e7aa6bf8b17cb6e5844582af88f4cb951de2f28c2190d4af2dc230312d02a4`.
All original source families and production code remain unchanged during
receiving; the current Hub remains at SHA256
`9a768731396f1148cb83172e74708e5ba994b244320e8e4f0961e1d41fc237c2`.
The archived PCIe2 control remains at SHA256
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.

### Next ownership boundaries

Further supply layer transitions require explicit actual barrel/current and
refill/reference evidence; fabrication-sized vias alone do not grant that
capacity. Remaining force rails, coupled routes and unknown supply contracts
need their own existing owners, not a 3V3 routing waiver. The Hub still needs
its USB factory-gap disposition and consistent thermal/power-state/current
qualification. The quarantined native fill discrepancy needs exact geometry
proof before cleanup promotion. No unchanged waves, source fabrication waiver,
new BOM choice, new thermal qualification, external upload, commit, source-board
selection or assembly order occurs in this slice.

## Native trace-contour diagnosis and bounded construction, 2026-10-03

### The screenshots show actual copper, not a dashboard artifact

The four supplied wide-trace examples are checked against native PCB items and
fresh saved-board top/bottom renders. Two separate mechanisms are present:
covered/reversed track legs, and short or unequal-width native PCB_TRACK
capsules. The latter retain round endcaps even when their centerlines are
Manhattan. One ATX track is approximately 0.087 mm long but 6.535523 mm wide;
its 3.2677615 mm end radius explains the large blob. Changing only the renderer
or the small-signal chamfer pass cannot repair that physical shape. Circular
plated connector lands and ordinary via pads are not treated as style errors.
Yellow lines in screenshots are not assumed to be copper without native layer
and item evidence.

`cec_power_contours.audit_board` provides bounded, read-only native hot spots
with net/layer/item UUIDs, actual width and endcap extent. Incomplete inspection
is unknown, not clean. Whole-board route craft and power-contour review are
separate terms: canonical centerlines do not imply clean wide contours. Final
independent signoff now requires a completed clean power-contour review in
addition to every existing electrical, factory and hardware gate. The current
38 Hub and 40 ATX findings are owner-review requests, not 78 new electrical DRC
violations and not permission to trim rated copper.

The pure `rectilinear_profile` planner constructs constant-width Manhattan
profiles with explicit caps and rejects diagonal, zero-length and backtracking
inputs. It does not materialize or qualify replacement power copper. No wide
power contour is replaced in this slice. The real next boundary is land-anchored
power-owner reconstruction with post-fill cross-section, clearance, current,
field and clipped Kelvin receiving. Width reduction to hide a blob, filler
copper added solely to satisfy FEM, and a cosmetic rendering mask remain
prohibited.

### Generic native cleanup and failure prevention

R2 exact backtrack normalization stops relying on rounded endpoints or a
five-degree equivalence assumption. It retains the widest conductor rather
than retiring a wider leg in favor of a locked narrow one. R9 dead-tail cleanup
is bounded and refuses ambiguous same-net contacts, zones and protected
ownership. R2c offers a bounded projected, slightly widened narrow remainder
only for the valid narrow-long/wider-short geometry; it does not assert exact
copper equality and requires independent field receiving. The inverse-width
Hub case is correctly refused rather than necking its wide trunk.

R2d retires a wholly contained narrower track only after exact rational
endpoint-to-segment capsule containment and an independent native
ERROR_OUTSIDE(old) minus ERROR_INSIDE(retained-wide) check at 1 nm curve error
produce zero outlines. There is no area tolerance or endpoint-rounding waiver.
The wider UUID, geometry, width and ownership remain intact. Sparse per-net,
per-layer receiver indexing and explicit candidate UUID scope keep work
bounded. Locked and grouped copper require explicit source-derived retirement
authority; the pipeline cannot infer it from a group name. These are
parameterized geometry/ownership rules, not board/refdes/coordinate engine
exceptions. Group receiving preserves the full frozen group except exactly
declared retired member UUIDs.

Last-mile proposal craft is checked before native emission against retained
and proposed copper. A path menu may try another legal canonical construction
instead of saving a newly introduced backtrack and discovering it later.
Unknown or capped preflight is not acceptance. Protected-pair geometry evidence
is scoped to actual pair member UUIDs and omits diagnostic elapsed time; an
unrelated ordinary route cannot change the pair identity. A separate whole-board
craft gate still catches such ordinary defects. Rollback logging now lists the
actual failed gates: a field-receiving failure cannot be misleadingly reported
as the stage decision `accepted`. False or unknown field evidence restores the
original PCB byte stream.

### Received saved-board improvements, not fab signoff

| Private received child | Actual improvement | Native non-regression | Remaining contour review |
| --- | --- | --- | --- |
| Hub | Four covered/backtracking artifacts removed; whole craft now clean | 0 opens, 0 scored routing DRC; 769 inherited raw findings unchanged | 38 hot spots |
| ATX | Two exact overlaps removed, then 135 to 131 opens with 27 new signal segments | 5 scored DRC and 560 inherited raw findings unchanged; no new native fault identities | 40 hot spots |

The final Hub child is
`build/trace-contour-receiving-20261003-f/hub-private/board.kicad_pcb`, SHA256
`d4df470cc994042a9668705208762fb439dc8debf1f95156063ca081fdd90b07`.
Its last change removes the 0.2 mm narrow prefix entirely covered by the
0.399999 mm wide track, despite a 1 nm non-collinearity. The wide track is
unchanged. Original pad/pose/settings/sidecar data, native zone definitions,
saved fills, terminal graphs, current paths, pair and typed/clipped Kelvin
evidence are preserved. No refill is performed. The final receiving takes
24.085751 seconds and reports no errors. Earlier three-artifact receiving is
`build/trace-contour-receiving-20261003-c/receiving.json`; the final exact native
containment receiver is
`build/trace-contour-receiving-20261003-f/receiving.json`. This does not admit the
previously quarantined PTH-refill probe or resolve its native Boolean sliver.

The final ATX child is
`build/atx-ordinary-contour-epoch-20261003-d/candidate-private/board.kicad_pcb`,
SHA256 `d06b56630d1c430f8dbfc70d60005b9aa38c4860c89fffa563a941cfef449453`.
Actual saved/refilled receiving closes four ordinary control connections:
ATX_PWROK, ATX_PSON, GPIO0 and EN. It adds no via or zone and leaves existing
pads, placements, power pours, all nine current-domain graphs, other-net
graphs, physical pair evidence, factory-hole evidence and typed/clipped Kelvin
evidence unchanged. It introduces no craft, field, raw DRC or full50 failure
identities. Full50 remains 27 PASS, nine FAIL, three DECLARED and 11 N/A; these
are not fifty passing design gates. Receipt is
`build/atx-ordinary-contour-epoch-20261003-d/receiving-receipt.json`.

The archived PCIe2 review source remains SHA256
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
Private replay of the new R2/R9/R2c/R2d operators is a no-op with exact source
preservation. It has zero new contour findings. This regression control is not
new Kelvin/factory/hardware qualification for that inherited board.

### Avoiding a known-useless routing portfolio

On the same immutable 135-open ATX source, the first last-mile search spends
36.966810 seconds constructing 13,413 new-via proposals whose refill/shield
evidence is unsupported, and closes nothing. A capability preflight now skips
that unsupported proposal class before expensive dogbone/maze enumeration.
Actual existing THT/via barrel contacts on their real layers remain available;
the guard is not weakened and skipped exploration is not a no-path proof.

The same-source second trial takes 13.230514 seconds, roughly 64% less search
time, but two new craft artifacts correctly prevent saving that trial. A third
trial passes craft but exposes an unrelated protected-pair diagnostic identity
bug and is also not saved. Both failed trials are retained as evidence, not
published winners. The final independently received ATX trial starts from the
two-overlap-normalized source and takes 17.730346 seconds of search and
80.059009 seconds including saved-board receiving. These measurements support
the avoided-work mechanism; they do not claim a 64% full-pipeline speedup.
All trials are bounded, with distinct immutable source/code/candidate epochs.

### Tests and verified current dashboard outputs

The final focused group passes **302 tests and eight subtests** in 4.50 seconds.
It covers rotated/mirrored synthetic geometry, locked/grouped authority,
protected widths, native containment, proposal craft, existing THT layer
access, field unknowns, byte-exact rollback, deterministic pair evidence and
independently withholding contour/factory/hardware signoff. A separate current,
distributed-supply, PTH-return, stage/suite-admission and copper-preservation
group passes **373 tests** in 142.82 seconds. No interactive unbounded full
multiprocessing suite is used, and the existing source/control families remain
read-only.

The root visually inspects both sides of the actual final Hub and ATX children.
The power blobs are visibly still present and are not described as repaired.
Both reviews are published as **BLOCKED / NOT FAB SIGNOFF**, with no 3D bodies
and native plots for all six copper layers:

- Hub: `pass-priority-contour-review-20261003-a-hub-standard-rev2-4f8ae27603`.
- ATX: `pass-priority-contour-review-20261003-a-atx-24pin-rev3-d422a47223`.

Windows localhost receiving fetches the actual two PNG and six SVG panels per
board; all 16 response-byte hashes match their saved-board publication receipts.
The receipts are under
`build/priority-contour-review-20261003-a/<family>/independent-publication-receiving.json`
and `windows-http-receiving.json`. Old reviews are not overwritten. Neither
publication nor the cleanup result resolves Hub USB factory-gap disposition,
consistent power-state/current/thermal/hardware qualification, or the ATX
remaining opens and inherited full50 failures. No fab-ready claim, new power
budget, part substitution, external upload, assembly order, commit or push is
made in this slice.

## 2026-10-03: explicit native rectilinear conductor owner and receiving

### Exact starting snapshots and the count correction

The current Hub input is still SHA256
`d4df470cc994042a9668705208762fb439dc8debf1f95156063ca081fdd90b07`.
Its independently recomputed contour count is **36**, not the 38 quoted in the
preceding publication. This is a publication correction, not two extra physical
repairs. ATX remains SHA256
`d06b56630d1c430f8dbfc70d60005b9aa38c4860c89fffa563a941cfef449453`,
with 131 opens, five scored DRC and 40 contour findings. All source/control
families remain unchanged throughout this slice.

`cec_pass_review.measure_native_geometry` now measures native opens and bounded
power-contour findings from the exact hash-journaled snapshot being displayed.
It preserves campaign-reported counts separately, labels mismatches visibly,
and does not call a campaign's scored DRC an independent preview measurement.
An incomplete audit is not zero findings. This fixes the class of child preview
inheriting an older parent's count without silently rewriting old reviews.

### Generic explicit ownership, real fill and the priority finding

`cec_rectilinear_copper` is a new bounded owner, separate from ordinary signal
polish and additive force repairs. It accepts explicitly owned, single-net,
single-layer Manhattan track UUIDs, exact native group/lock permissions and an
existing caller-supplied width contract. It emits solid native copper with a
Manhattan outline, not a display/FEM overlay. It never reduces a selected source
width or grants current, thermal, factory or release qualification.

The square-ended envelope conservatively contains each old native capsule.
It does **not** shrink the old lollipop extents or qualify a flush pad landing.
Foreign native pads, tracks and vias inside a proposed outline are refused
before generation, even if the filler would void them. This check is replayed
at materialization and receiving, so moved obstacles cannot bypass a stale
plan. No body/refdes/coordinate exception or plane-role guess is used.

The first real Hub fill is rejected because its new priority-zero patch omits
0.4515582157055 mm2 of the old capsule. Native forensic diagnosis proves that
the priority-four **same-net** existing pour already supplies that region;
this is not a narrow clearance or permission to waive copper loss. The receipt
now proves every complete 1 nm `ERROR_OUTSIDE` old capsule inside the union of
the new actual native fill and exact unchanged, hash-bound supporting native
same-net fills. Supporting outlines, fill polygons, UUID/net/layer and priority
are replayed. Unfilled outlines, wrong-net copper, a changed supporting fill,
arcs, bounded-out data and a one-nanometre copper-loss hole cannot grant credit.
No original pour priority is escalated and original pours are not refilled.

The existing current graph has a strictly opt-in resident-subset witness API:
it replays that complete native enclosure on the current board and separately
checks the existing per-layer current/project dimensional authority. The ghosts
are not PCB tracks added to the board. Arbitrary zone area, vias, parallel
sharing and new load/current assumptions receive no credit; default additive
force behavior remains unchanged.

### Same contact evidence is not identical primitive counts or new qualification

`cec_force_sense_evidence.compare_contact_preservation` compares complete bound
same-scope native observations against an explicit received track/zone UUID
transformation manifest. Native graph count deltas must match that manifest
exactly. Physical terminals, current authority, contact states, coverage,
unknown/refusal states and departures still compare exactly; native geometric
clipped isolation is independently checked. Native tuple pin arrays normalize
to their JSON arrays without scalar coercion. Equal unknown remains unknown.
This is a preservation comparator, not a new Kelvin admission API.

ATX trials show two distinct reasons to refuse: one rectangle enters a reserved
region around a foreign connector pad; a later obstacle-free rectangle changes
the geometric witness identities on `/SENSE3V3_HI`. Its affected native isolation
checks still pass, but the exact clipped-copper certificate does not remain
identical. That is **not** diagnosed as a newly proved bypass. The trial remains
quarantined until a scoped changed-geometry certificate rebinder can qualify
the affected evidence without laundering other unknown legs.

The private caller now compiles unsupported typed force rails from the actual
resolved lineage before geometry generation, using the owner's existing
explicit exclusion mechanism. This final ATX preflight stops without a save in
2.877 seconds instead of replaying an unchanged unsupported trial. All 40 ATX
contour findings lie on those typed force rails. No board is routed around a
failed gate and no part, width or design budget is changed to claim success.

### Actual result, control replay, tests and fresh visual receiving

The final Hub private trial is independently received at SHA256
`bcba4e1eeae3ca00988881b6569acc87516a0e5a1aa10022a719c6eca410535d`:
**36 to 35** contour findings, **zero to zero** opens and **zero to zero**
scored routing DRC. Raw native findings remain 769. Pads/poses, original zone
outlines/fills, terminal/current graphs, group ownership, board settings,
companions, pair/field and typed/clipped evidence are preserved. No new native
fault identities or full50 failure IDs are introduced. This is one received
contour repair, not wholesale cleanup or electrical closure progress.

ATX's current source is unchanged: 131 opens, five scored DRC, 560 raw native
findings and 40 contour findings. Rejected trials are not promoted or pictured
as current winners. PCIe2's immutable archived control remains SHA256
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`;
it has zero contour findings and the source-family replay is an exact no-op.
This does not requalify its inherited Kelvin/factory/hardware debt.

The final focused suite passes **242 tests** in 2.08 seconds. It includes native
save/refill across rotations, mirrors and both sides, explicit ownership,
stale/fake contracts, real priority clipping, wrong/changed supporting copper,
1 nm loss rejection, obstacle preflight/replay, actual native lineage and strict
contact/cut evidence. The separate force-current subset passes **205 tests**
with 37 deselected in 103.92 seconds before the final contact-comparator-only
extension; it is not added to the focused count or claimed as a full interactive
suite. `git diff --check` is clean.

Fresh reviews are:

- Hub: `pass-owned-contour-review-20261003-a-hub-standard-rev2-030872bab3`.
- Explicit unchanged current ATX:
  `pass-owned-contour-review-20261003-a-atx-24pin-rev3-83c0c3d44e`.

Both are **BLOCKED / NOT FAB SIGNOFF**. Windows localhost response-byte
verification matches all 16 actual panel hashes: two no-body PNG sides and six
native copper SVG layers per board. Receipts are under
`build/owned-contour-review-20261003-a/<family>/windows-http-receiving.json`.
The root inspects the top images; remaining oversized contours are visibly
present and are not claimed fixed. Old publications are not overwritten.

The new conductor owner is not yet an automatically promoted production stage.
Full power-state/source-authority rebinding, affected typed geometric certificate
rebinding, factory/process, thermal and hardware qualification remain required.
The next useful slice is that generic certificate/authority rebinder alongside
ATX connectivity closure, not more unchanged contour waves. No source selection,
new current budget, fabrication release, commit, external upload or overnight
run is performed in this slice.

## 2026-10-03: generic additive connectivity and critical-route handoff repairs

This follow-on slice is construction progress, **not ATX fabrication closure**.
The immutable current ATX source is still
`d06b56630d1c430f8dbfc70d60005b9aa38c4860c89fffa563a941cfef449453`.
The independently received private child is
`915d4c44104cb987de56b9195e3440d08eea87776f21b9be64c23f6541efdaaa`, at
`build/atx-ordinary-field-corrected-20261003-w/proposal/board.kicad_pcb`.

### Measured PCB progress and unchanged debt

Native opens fall **131 to 113**, a reduction of **18 (13.7%)**:
two short CAN connections, eleven GND joins, four component-budgeted +3V3
distribution joins, and one ordinary PSON_GATE join. Actual connected-component
counts change as follows: GND 21 to 10, +3V3 8 to 4, each short CAN member 2 to 1,
and PSON_GATE 3 to 2. These are native saved-copper joins, not renamed ratlines,
plotting overlays, or completion inferred from matching net names.

The five scored routing DRC findings, **560 raw native findings**, and **40
power-contour review findings** remain unchanged. The complete 50-check registry
remains **27 PASS / 9 FAIL / 3 DECLARED / 11 N/A**. There are no new native fault
identities, new full50 failure IDs, or new field blockers. All original native
items, physical pad poses, settings, companion bytes, and original zone
outlines/fills are preserved. Every old physical terminal partition and
previously admitted current path is preserved; component partitions may merge,
never split. Current budgets and widths are not reduced.

Typed/clipped Kelvin replay remains **16 expected, 4 checked/passed, 12 UNKNOWN,
0 failed** on both source and child. Preserving those unknown states is not
electrical qualification. The final current-engine receipt is
`build/atx-additive-receiving-20261003-y/receiving.json`; it accepts private
receiving and explicitly grants no source-selection, power, or release authority.

### Reusable engine changes and the underlying failures

- Ordinary completion now recognizes hierarchical and tokenized supply rails
  (including signed/NEG/VSB forms) before permitting signal finishing. Unbudgeted
  supply nets are not quietly joined at a default signal width. Ordinary ADC
  and detection signals containing voltage numbers are not misclassified.
- Pair planners reject reverse bends down to native nanometre geometry and
  proper same-net self-crossings before committing a candidate. Generated
  corner normalization must strictly reduce native craft identities without
  worsening a retained angle or adding a crossing against unchanged neighbors.
- Distributed-supply search fairly schedules component/layer frontiers rather
  than repeatedly spending the entire finite attempt budget on the nearest
  dense island. Plans and launch proofs are reused only within one unchanged
  native copper epoch and invalidated after a real join. Bounded search is not
  a proof of global impossibility.
- The field checker previously called conductors 12–16 mm apart a "crossing"
  because they lay inside a wide bus's conservative 3W search envelope. The
  approximately-perpendicular crossing rule now requires actual finite copper
  capsule overlap in XY. Nearby parallel-run, clearance, actual GND shielding,
  and 95% coverage rules remain unchanged. Parallel overlap is symmetric in
  operand order in both proposal and saved-board receiving.
- Complete pair transactions now audit the final normalized native additions
  against the parent on an isolated, freshly refilled copy of the existing
  GND zones. The source's power fills are not rewritten. Copper net identities
  are checked across native fill, so connectivity propagation cannot conceal a
  fault. A real connected signal barrel cutting a reference plane is tested;
  a stale filled-zone cache cannot qualify it. Pair coupling is measured over
  **all old and new pair copper**, not only the attractive new subpath.
- The precision ladder no longer depends on the caller remembering a locked-
  net list before recognizing a complete pair. It proves every physical land
  on native connectivity, checks the full pair physics and field interactions,
  and reuses only a qualified existing route. Connected-but-invalid pairs,
  disconnected copper islands, dishonest lock claims, missing profiles, and
  bounded/unknown evidence remain explicit repair debt. Valid reused pairs
  carry completion evidence into the generic residual coordinator and its
  native completion revalidation; an unlocked-but-valid source is not silently
  left available for rewriting. Source geometry and lock flags are unchanged.
- Ground-return certificates previously chose a repair stage from the pad-
  center failure alone, hiding locked conductors blocking later dogbones. The
  certificate now retains bounded measured native objects and site provenance
  from ordinary and compact-process trials. Pad exclusions have exact pad and
  footprint UUIDs and copper layers. Temporary cell copper remains distinct
  from inherited authority. Certificates authorize neither blocker mutation
  nor a global no-path conclusion.

These rules use native geometry, declared process/current contracts, and
explicit ownership. Shared engines contain no ATX/Hub refdes or coordinate
repair exception added by this slice. The board-specific workbench only selects
the explicit private input and records trials.

### Cross-board regression and remaining work

The final control receipt is
`build/cross-board-routing-replay-20261003-y/receiving.json`. Both controls are
exact native copper/lock no-ops with unchanged physical pair and field evidence:

- PCIe2 immutable archived SHA
  `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`:
  two qualified pairs reused, zero items generated, one inherited CAN physical
  repair refusal. Opens/scored DRC remain zero; registry remains 32 PASS /
  3 FAIL / 3 DECLARED / 12 N/A. Its inherited cross-section, Kelvin departure,
  and CAN reference-plane debt is not requalified by this replay.
- Current Hub private child SHA
  `bcba4e1eeae3ca00988881b6569acc87516a0e5a1aa10022a719c6eca410535d`:
  both valid pairs reused, zero items generated/refused, zero opens/scored DRC;
  registry remains 30 PASS / 3 DECLARED / 17 N/A. Raw 769 native and 35 contour
  findings remain separate from this nonregression result.

An earlier detached control trial unnecessarily retried existing pairs and
changed the detached PCIe copper. It was never saved/promoted to the immutable
control. Its failed receipt is retained, not rewritten into a pass; the native
preflight and residual handoff corrections above address that cause.

The final focused routing/field/ownership/cell suite passes **580 tests** and
four subtests in 7.35 seconds. This is one selected suite, not a sum of repeated
overlapping runs and not the full interactive repository suite. Native field
checks include a newly introduced crossing, an actual connected barrel cutting
a reference plane, legacy debt preservation, missing identity, rotations and
renamed/hierarchical nets. The affected staged coordinator handoff is checked
alongside real native completion/revalidation tests.

The local-ground forensic pass tries fourteen still-unserved physical pads and
adds no unqualified vias. Its actual report now identifies inherited locked
objects on **11 of those 14** failed searches; three remain local placement/
route-access cases. It does not infer that every sampled failure has the same
cause, move a trunk, or force a barrel through a power bus. Evidence is under
`build/atx-ground-obstructions-20261003-x/search-receipt.json`.

The remaining ATX blockers include USB and CAN_BUS construction, stranded IC
power/ground, missing/empty complete frozen power-geometry authority, rated force
paths and the measured SENSE12V_HI cross-section, twelve unknown Kelvin legs,
factory/process disposition, and contour cleanup. +5V_SYS, 5VSB_MUX, the port
supply, and ATX_NEG12V still lack executable selected current contracts in this
input; defaults are not authorization to invent them. The +3V3 joins use the
existing 0.2048376 A component-load budget including its existing 20% margin.

The next useful work is strict native power-state/affected-certificate rebinding
and whole-cell access/placement repair with owned regeneration, preserving
priority trunks and stack/mating constraints. Repeating unchanged local-route
waves is not a substitute for that upstream repair. No candidate is promoted
to final fab review, no current/factory gate is weakened, and no unattended run
is left operating by this slice.

The final review is
`pass-atx-additive-review-20261003-y-atx-24pin-rev3-147863e275` at
`http://localhost:8090/?id=pass-atx-additive-review-20261003-y-atx-24pin-rev3-147863e275`.
The Windows HTTP replay independently matches all eight response-byte hashes
to the journaled panels: both no-body renders and all six native copper SVGs.
The dashboard archive API includes that exact selectable ID with eight panels
and verdict BLOCKED. The root visually inspects both sides of the same PCB
hash; its remaining oversized/bubbly power contours are visible and not claimed
fixed. Old previews and rejected trials are not overwritten. The final code
epoch has no additional engine changes after receiving; the source and archived
control families remain unchanged. App panel opening returns queued, so no claim
is made that the user's foreground browser has navigated automatically.

## 2026-10-03: refill-aware additive routing and exact-object receiving

### Accepted result and immutable lineage

The accepted input for this slice is
`build/atx-ordinary-field-corrected-20261003-w/proposal/board.kicad_pcb`, SHA256
`915d4c44104cb987de56b9195e3440d08eea87776f21b9be64c23f6541efdaaa`.
The final independently received private child is
`build/atx-fast-native-finalized-20261003-ah/candidate-private/board.kicad_pcb`,
SHA256 `ba6f24e756b40cb536f33bb7e11f632876776693045e3ffc1ba3248f987cff15`.

Native unconnected items fall **113 -> 104**, nine additional closures in this
slice. The preceding slice reduced 131 -> 113; the cumulative reduction across
both slices is 27, not nine plus a second count of the same routes. Native raw
DRC remains 560, scored DRC remains five, and power-contour review findings
remain forty. No new native fault IDs, registry failure IDs, or field blockers
are admitted. The full fifty-check registry remains 27 PASS / 9 FAIL /
3 DECLARED / 11 N/A. This is **not fab signoff**.

The native closures are I2C_SDA (one), I2C_SCL (two), GPIO0 (one), the fast
sensing THRESH net (one), regulator EN (one), DET5V (one), DET5VSB (one), and
GND (one). The last GND closure uses three planar segments and no new via;
it does not qualify every decoupler's immediate ground return. New signal
barrels elsewhere use the declared qualified process, not a globally lowered
ordinary-via minimum.

Final receiving evidence is
`build/atx-fast-native-receiving-20261003-ai/receiving.json`. It independently
checks exact original geometry, poses/pads, board settings, source-plus-delta
ground refill, exact-object rules, saved native connectivity, inherited current
paths, typed contacts, clipped Kelvin copper, pair evidence, field interactions,
native DRC and the registry. Source, candidate and archived control families
remain unchanged while receiving; the engine epoch is stable.

### Generic causes repaired, not board-specific exceptions

The ordinary completion engine previously treated new vias as unsupported by
its planar field-proposal checker. This correctly avoided trusting stale
reference-plane copper, but it also prevented qualified multilayer proposals
from being assessed at all. The planar checker stays strict. A separate
`cec_field_coupling.assess_proposed_route` path now admits bounded actual native
through-via proposals only after private source-plus-additions reconstruction,
refill of existing GND zones, and comparison of old and new field interactions.
It checks interactions between retained routes as well as those involving the
new route: a nominally neutral barrel can cut shielding between two existing
sensitive conductors. Missing evidence, unsupported geometry, exhausted budgets,
and failed refill remain UNKNOWN/refused, never a speculative pass.

The shared `cec_fr.synthesize_lastmile` caller explicitly requests and uses that
native-refill capability. Existing THT barrels remain reusable; it does not add
an unnecessary layer-change via merely because an endpoint occupies several
layers. New-via size/drill/span and net identity are validated before creating
the isolated snapshot. Protected power fills are not regenerated by this
proposal receiver, and no selected current budget is changed.

A synthetic fault exposed a second, independent cause: the convenience
`pcbnew.SaveBoard` operation can build connectivity and propagate net identities
while serializing a touching trial. That could conceal a field fault by
relabeling two distinct conductors as the same net. Field snapshots now use the
non-normalizing native `PCB_IO_KICAD_SEXPR` writer and verify exact UUID/net/
geometry inventories of the caller and freshly reloaded snapshot. Native fill
must preserve those identities too. A shorted or relabeled snapshot is refused;
it cannot become good field evidence. The same protection and caller's declared
netclass resolver apply to saved-board additive receiving. This is a focused
field-snapshot fix, not a claim that every repository save call was rewritten.

Whole-board field work is also bounded by explicit object, interaction and
sampling limits plus a deadline. Deadline/unsupported-arc results are explicit
unknown evidence. The fast and normal search passes use different portfolios
and parents, so their timings are not presented as a controlled speedup result.

### Rejected trial, legitimate refill, and local rule delivery

The first 113 -> 106 raw trial was **rejected**, not published as a winner.
Its stale GND fill and absent matching compact-via rule increased raw native
DRC from 560 to 622. That failed receipt remains under
`build/atx-native-refill-receiving-20261003-aa`; passing planar geometry alone
did not overrule final native DRC.

The new shared `cec_additive_route_receiving` module finalizes into a fresh
private family, refills only existing GND zones, and binds the qualified
`CEC_LOCAL_POFV_SIGNAL_VIA` group's exact members to the existing generic
process rule. Original power fills, tracks, drills, locks, poses, settings and
non-rule companions remain protected. The receiver independently rebuilds the
expected child from the immutable source and exact new native primitives,
replays that GND refill and rule generation, then compares saved geometry and
rule bytes. It permits neither a blanket filled-zone waiver nor an arbitrary
group/project/rule rewrite. Existing local group membership may grow only by
new individually requalified native vias; undersized annuli, stale fills,
changed outlines and extra broad clearance waivers are refused.

Normal `cec_fr.import_ses` now binds the exact-object local-via rule **after**
source companion copying, so a copied older rule file cannot erase the rule for
newly generated qualified members. Its existing final native refill remains in
place. An ordering regression exercises that real importer handoff; the change
is not confined to the ATX workbench.

The refilled/rule-bound 106-open trial passes independent receiving. A bounded
ground pass then closes one more connection in 6.74 seconds, and a bounded
ordinary pass closes another in 36.13 seconds. Both intermediate children are
received before the final 104-open child is selected. These timings cover
search, not full qualification/publication. No rejected trial overwrites an
accepted input.

### Tests, cross-board replay, and visible result

The final focused suite passes **623 tests and eight subtests** in 7.11 seconds.
This is one selected suite, not a sum of overlapping repeated runs or the full
interactive repository suite. New regressions exercise retained-route shield
cuts, renamed/classified nets, serialization identity, invalid vias, failed
refill, timeouts, actual last-mile via construction, exact additive ground
reconstruction, monotone owned groups, annulus limits, project/rule protection,
and the normal importer ordering. Shared rules contain no new ATX/Hub refdes or
coordinate repair special case.

The final unchanged-control replay is
`build/cross-board-native-refill-replay-20261003-af/receiving.json`:

- Archived PCIe2 SHA
  `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`
  retains zero opens/scored DRC/contours, generates no items, and reuses two
  physically qualified pairs. Its inherited CAN repair refusal and three
  registry failures remain explicit: current cross-section, Kelvin departure,
  and CAN reference-plane coverage. The archive's old fab-review name is not
  fresh release qualification.
- Hub private SHA
  `bcba4e1eeae3ca00988881b6569acc87516a0e5a1aa10022a719c6eca410535d`
  retains zero opens/scored DRC, 769 raw native findings and 35 contours,
  generates no items, and reuses both qualified pairs. Its private source and
  manufacturing/release limitations are not promoted away by this replay.

The fresh review is
`http://localhost:8090/?id=pass-atx-native-refill-review-20261003-aj-atx-24pin-rev3-623ae12e1c`.
Windows HTTP receiving matches the response bytes for **all eight** journaled
panels: top/bottom no-body renders and all six native copper-layer plots. Every
panel is bound to the final `ba6f24e7...` board and explicitly marked BLOCKED /
NOT FAB SIGNOFF. Both actual rendered sides are visually inspected; inherited
bubbly/oversized power contours are still present and are not claimed repaired.
Opening the app browser returns queued, so foreground navigation is not assumed.

### Remaining upstream blockers

The nine remaining registry failures, 104 opens, five scored native DRC
findings, forty contour findings and twelve unknown of sixteen expected Kelvin
legs still prevent release. Four Kelvin legs remain checked/passed, zero failed;
twelve unknown is not a Kelvin pass. Locked wide native power copper blocks
many local ground-access sites, and the purported complete frozen power-state
metadata is empty/failed rather than a usable placement authority. Current
cross-section/force-path failures and missing selected local supply contracts
must not be bypassed by ordinary narrow traces. USB/CAN_BUS construction and
owned whole-cell return access remain real work.

This slice changes no component positions, board size, priority power trunks,
selected budgets, architecture, mating interfaces or factory limits. The next
useful stage is native power-authority rebinding and owned whole-cell access
repair, with affected-route regeneration and full receiving. Repeating an
unchanged local search cannot fix an inherited locked bus occupying a legal
barrel site. No overnight job or new automation is left operating, no board is
promoted to fab review, and this slice is saved locally but not committed/pushed.

## 2026-10-03: native-obstruction return-placement feedback

### Result: a repaired proposal stage, no newly accepted ATX closure

The accepted ATX child remains the 104-open board at
`build/atx-fast-native-finalized-20261003-ah/candidate-private/board.kicad_pcb`,
SHA256 `ba6f24e756b40cb536f33bb7e11f632876776693045e3ffc1ba3248f987cff15`.
This slice does **not** claim another accepted routing improvement or fab
readiness. Its fresh independent baseline has five scored DRC, 560 raw native
findings, forty power contours, and nine failed registry checks.

The upstream feedback gap is real: failed ground searches retained native
track/via identities and dimensions, but the return-placement solver consumed
only rectangular pour reservations. Against the exact current ATX craft
measurement, that old proposal family produced zero moves. The repaired family
produces 96 bounded proposals across five failed cell owners. These are moves
to evaluate, not 96 valid placements or connections. Evidence is under
`build/atx-native-return-feedback-20261003-am` (the fresh native measurement is
retained under `...-ak/measured-decoupler.json`).

### Generalized construction and receiving changes

- `cec_placement_search_domain.axis_exits_from_copper_union` intersects actual
  rounded straight-track capsules and via circles with axial search lines,
  then merges overlapping intervals with guard rectangles. A diagonal's empty
  bounding-box corners are not falsely treated as conductor, and crossing a
  tessellation seam does not become a legal exit. A through-via portal sees
  obstacles on every copper layer, not just the component's mounting side.
- `cec_local_return_feedback.bound_native_obstacles` binds geometry to the
  measured input PCB's SHA and rechecks it after loading. Observed blocker
  UUID/net/layer/lock/dimensions must match that saved native object. Stale cell
  poses and tentative construction copper cannot claim inherited authority.
  Unsupported objects remain the native evaluator's responsibility. The
  capsule set is expressly proposal geometry, not complete clearance proof or
  replacement power authority.
- Failed lead rays can inform a whole-cell reseat even though they are not
  usable dogbone launches in the original pose. Owned bypasses move rigidly
  with their owner, fixed members stay fixed, and capacitor-only rotations
  keep the measured supply pad anchored. Search has explicit native object,
  motion, proposal and intersection budgets. Repeated portal intersections
  are cached within a single cell's immutable proposal evaluation.
- The normal `cec_synth_pipeline._placement_craft_move_specs` handoff now reads
  this bound native geometry and emits the same generic return-access family.
  It retains complete native placement/craft admission; no board name, refdes,
  coordinate or power-trunk exception is added to shared rules.
- `cec_additive_route_receiving.receive` retains strict original-pose equality
  by default. An explicit fixed-supply-rotation mode independently infers
  selected two-land GND bypass ownership from the source, requires an exact
  native supply anchor and quarter-turn with no flip, and replays the full
  native footprint transform. It also requalifies a saved immediate return or
  the existing locality-bounded shared entry to the selected owner's ground
  land. KiCad's native pivot and pose APIs serialize some angle representatives
  differently; each accepted representation must match an exact independent
  native replay, not arbitrary angle/property normalization. This geometric
  proof cannot overrule whole-board DRC, craft, current, mating or release gates.

The existing power-guard code already refuses a `placement_scope: complete`
state with no frozen conductors. A new regression preserves that behavior;
this is not described as a newly fixed empty-state bug. The ATX empty/failed
power metadata remains invalid. Native obstruction proposals do not turn it
into current-rated frozen authority.

### Trials and the actual rejection stack

Two bounded fixed-supply rotations are tried in private families:

- The 90-degree trial constructs an owned local supply/return cell and reaches
  103 opens. After ground refill, exact-object rule finalization and independent
  receiving, it is **rejected**: scored DRC rises five -> seven and raw native
  findings 560 -> 562. C20's GND land is only 0.075 mm from R59's +5V_MAIN
  land against the actual 0.200 mm netclass clearance, and their courtyards
  overlap. Changed silk creates additional distinct native fault identities;
  those too remain explicit. Lower opens and a received supply anchor do not
  excuse the new faults.
- The opposite rotation fails local return construction and reaches 105 opens.
  It also remains an unadmitted trial, never a replacement incumbent.

The first trial's finalized PCB is
`build/atx-fixed-supply-finalized-20261003-an/candidate-private/board.kicad_pcb`,
SHA256 `85dec1af131370a10125a3ece8e0c527cf749bccd3d6482ffb9e24a890a99de1`.
The explicit failed receiving stack is
`build/atx-fixed-supply-receiving-20261003-ao/receiving.json`. Original priority
power copper, supply anchor, board settings and typed/clipped Kelvin evidence
are preserved, while raw pose equality is correctly false. The receiver grants
neither fab status nor permission to ignore the clearance/courtyard findings.

A separate fuller ordinary-route portfolio runs from the accepted 104-open
parent, not from either bad placement. It closes zero connections in 74.91
seconds and leaves source bytes unchanged. Its receipt is
`build/atx-ordinary-expanded-refill-20261003-aq/search-receipt.json`. That
unchanged portfolio is stopped rather than rescheduled indefinitely.

### Regression evidence and next upstream work

The final focused suite passes **557 tests and four subtests** in 4.54 seconds,
one selected run, not a sum of repeated overlapping suites. Coverage includes
native and renamed/rotated/back-side capsules, diagonal and round-end geometry,
unsampled other-layer obstacles, identity/pose/budget failures, actual production
dispatch, supply-anchor reconstruction, incompatible component/property edits,
unqualified barrels, and preservation of the existing empty-authority refusal.

`build/cross-board-return-reseat-replay-20261003-aw/receiving.json` confirms the
current engine epoch and unchanged archived PCIe2/Hub routing and full registry
states. Read-only production feedback dispatch also generates zero new moves
on both controls and preserves their saved families, in
`build/pcie2-native-return-feedback-control-20261003-ar/receiving.json` and
`build/hub-native-return-feedback-control-20261003-as/receiving.json`. Existing
PCIe2 current/Kelvin/CAN-reference debt and Hub private/manufacturing limitations
remain unqualified; this replay does not erase them.

The remaining placement work is a complete owned-cell transaction with affected
local-route regeneration and independently rebound authority, not merely a
clear via point or an arbitrary capacitor coordinate patch. The existing
support-branch preservation machinery must still refuse unrelated, locked,
grouped or current-bearing prefix mutation. No priority trunk is unlocked or
rerouted by this slice. Budgets, architecture, board dimensions, output/mating
geometry and factory limits are unchanged. No newly accepted PCB or rejected
trial is published as a fresh winner; the last exact 104-open dashboard review
remains selected. Changes and failed/plateau receipts are saved locally; no
unattended job, automation, release promotion or Git push is created here.

## 2026-10-03: accepted ATX opens reduced from 104 to 81

This section supersedes the preceding 104-open review selection, not its
historical rejection evidence. The immutable PCB source is
`build/atx-fast-native-finalized-20261003-ah/candidate-private/board.kicad_pcb`,
SHA256 `ba6f24e756b40cb536f33bb7e11f632876776693045e3ffc1ba3248f987cff15`.
No original footprint, pad, priority-current track, power-fill intent,
outline or mating geometry was moved or replaced.

### Independently received result

The accepted composed candidate is
`build/atx-composed-finalized-20261003-cs/candidate-private/board.kicad_pcb`,
SHA256 `5386d6b63a3c443b9944b61eede29e950b8796b78855f14bc3157dd82ae87d8d`.
`build/atx-composed-receiving-20261003-ct/receiving.json` independently receives
**104 -> 81 opens: 23 actual connections, 22.12 percent reduction**. Native
raw findings remain **560**, scored DRC remains **5**, and contour reviews
remain **40**. No new native fault identity, full-registry failure, field
blocker, current-path regression or typed/clipped Kelvin change was admitted.
The full registry remains 27 PASS / 9 FAIL / 3 DECLARED / 11 N/A. Four of
sixteen expected Kelvin legs are verified; twelve remain UNKNOWN. This is
partial routing progress, **not fabrication or release signoff**.

The independently accepted progression was 104 -> 103 -> 101 -> 100 ->
93 -> 85 -> 81. Connections from separate child trials were never summed.
The final source-plus-delta receiving covers every addition together.

### Generic construction repairs

- `cec_copper_reuse` subtracts only exact integer-collinear intervals already
  occupied by retained straight same-net/same-layer copper of at least the
  proposed width. It preserves retained UUIDs and geometry, proposed vias and
  the material union. Nearby, narrower, foreign-net/layer and unsupported
  geometry cannot supply reuse credit. Last-mile admission and emission both
  consume the actual uncovered delta; native component reduction is still
  required. This fixes covered-backtrack proposals without a craft waiver.
- Package preclosure now applies the same field admission to direct, U,
  ordinary bridge, asymmetric and atomic two-member pair proposals. New
  barrels are checked through isolated native GND refill, including retained
  interactions. Unknown/refused evidence cannot commit. The two-row
  flow-through case can propose a symmetric direct POFV bridge with local
  returns when the face route is electrically unsuitable. No board, reference
  or coordinate case was added to that algorithm.
- Newly emitted, live-geometry-qualified local POFV barrels now enter the
  existing exact-object ownership group. Finalization binds its native DRU;
  receiving independently re-proves incoming barrels. Ordinary board minima
  and the selected filled/capped process limits were not changed.
- ATX's declarative routing policy now includes the previously omitted USB
  service chain's existing 0.75 A geometry envelope, with 125 percent margin
  applied once. The selected F1 is 1206L075/16WR / C371166, matching the
  current hierarchical source and the platform's documented service cell.
  This does not make PTC hold current a guaranteed clamp, invent a component
  load, change the wireless-disabled budget, or qualify inrush, fault response
  or barrels. Main rail ceilings remain 20 A / 20 A / 12 A / 3 A.

The bounded rated-supply workbench used the shared per-layer dimensional
compiler, checked every added trace against its full conservative envelope
and admitted no undersized/undeclared additions. All nine USB supply-chain
opens closed. The last long fuse-to-ferrite connection required the ordinary
non-fast bridge/maze search; the preceding canonical-only proposal had no
global no-path proof. Other connections include package ties, actual ground
returns, +3V3 distribution and source-typed scalar/signal completion. The
source-typed scalar parser remains a private workbench experiment, not a
claim that all source-role dispatch is integrated into production.

Two 93-open trials were rejected before the final accepted one: the first
introduced four unshielded USB/sense-bus interactions, and the second omitted
native ownership for eight otherwise process-qualified POFV barrels, creating
24 new native dimensional findings. Neither was promoted or counted.

### Regression and publication evidence

The final selected focused run passes **314 tests and 24 subtests**, with two
explicitly deselected pre-existing expired-budget tests. One of those expects
an empty synthetic pair to be labeled `preexisting-locked`; the current
precision path correctly does not grant complete-route authority from a
bare net-name lock assertion. It failed before any local constructor could
be called, and was not weakened to make this slice pass. New local-link tests
cover four rotations, renamed nets/packages, unknown field evidence,
two-row shielded alternatives and exact incoming POFV ownership.

`build/atx-closure-crossboard-20261003-cq/receiving.json` replays actual routing
on the immutable archived PCIe2 control and the Hub private control. Both
retain zero opens / zero scored DRC, exact native copper and pair/field
evidence, and create no new items. Existing PCIe2 current/Kelvin/CAN-reference
debt and Hub private/manufacturing limitations remain unqualified.

[Exact 81-open routing review](http://localhost:8090/?id=pass-atx-81-open-review-20261003-cv-atx-24pin-rev3-3bc0761b30)
is published from that received hash. Its publication receipt is
`build/atx-81-open-review-20261003-cv/atx-24pin-rev3/independent-publication-receiving.json`;
all six plots derive only from native saved copper, not illustrative slabs.
The reviewed top view was visually inspected. This archive is explicitly
BLOCKED / NOT FAB SIGNOFF, not a stale production-board substitution.

### Remaining failure stack

The saved native island inventory in `build/atx-81-islands-20261003-cw.json`
has 81 terminal-only opens and **zero orphan-only components**: these cannot
be made to disappear by deleting disconnected debris. They comprise 39
supply/rail opens, 15 shared force/sense opens, four ground opens, six USB/CAN
bus opens and seventeen remaining scalar/control opens. Some supply stages
still lack an executable load/branch contract; missing authority is not
permission to apply a signal width or infer load from regulator capacity.

`build/atx-usb-pair-after-preclosure-20261003-cu/search-receipt.json` is a
bounded plateau, not another accepted closure. A short connector/protector
leg is constructed under the inline-leg-only solver gate, but the longer
protector/MCU leg exhausts its deadline. The atomic chain rolls back all
new copper and retains 81 opens. Local success has only 56.1 percent coupled
coverage and no whole-chain authority. The next upstream work is a qualified
source-bound branch-current ledger and endpoint/layer-aware long-pair search,
potentially with independently received bounded subchain checkpoints;
simply retaining a solver-local leg would not be sufficient. No unattended
job, automation, release promotion, commit or push was created in this slice.

## 2026-10-03: the two marked circular landings become native chamfers

This is a **shape-only private review**, not another routing wave or fabrication
signoff. It starts from the independently received 81-open ATX board above:

- Source: `build/atx-composed-finalized-20261003-cs/candidate-private/board.kicad_pcb`,
  SHA256 `5386d6b63a3c443b9944b61eede29e950b8796b78855f14bc3157dd82ae87d8d`.
- Received candidate: `build/atx-purposeful-landings-20261003-dh/candidate-private/board.kicad_pcb`,
  SHA256 `d7b674787109818cc3c8047d96d44f3400c446732f4737067e87689cb0bb2496`.
- Independent saved-board receiving: `build/atx-purposeful-landings-20261003-dh/receiving.json`.

The user's two highlighted lobes have different native causes. The upper
`+5V_MAIN` lobe is an authored circular solid zone. The lower `/SENSE5V_HI`
lobe is a 6.535523 mm-wide straight track only 1.299999 mm long: its round
caps dominate its appearance. Neither was a rendering-only blob. Drilled
pads, via annular rings and mounting holes were deliberately not squared.

### Reusable construction and strict receiving

`cec_rectilinear_copper` now constructs integer-native square or 45-degree
chamfer envelopes. Its outward-only support-plane grid changes construction
coordinates, not existing widths, pads or placements. A new source-retaining
mode leaves the original rated track and its exact UUID/width/position in
place underneath an actual solid native cover. Later routing/current stages
therefore see the real original rated track; they do not need a synthetic
replacement capacity witness. The former retiring mode remains available
under its existing contract.

`cec_rounded_landing` is the bounded same-zone owner for compact convex filled
landings. It changes the native outline in place while preserving the exact
zone UUID, net, layer, process, priority, clearance, connection, minimum
feature thickness and ownership. These reusable owners take native identities
and declared width/ownership contracts; their engine code contains no ATX,
reference-designator or coordinate special case. The private review harness
selects the two explicit user-highlighted objects. This is an explicit owner
request, not a claim that autonomous whole-board contour cleanup is complete.

The square proposal was refused because its new corner would intrude on a
foreign ground track; a 45-degree chamfer was independently checked instead.
Only the modified upper zone and the new lower cover were filled. Original
tracks, vias, footprint poses, pads, terminals, groups, dimensions, other
zones, project companions and current-path graphs remain exact. No global
power or ground refill was used.

The first diagonal receiving trials exposed KiCad's real filled-edge
quantization, not a plotting artifact. The final lower cover declares and
hash-binds a 4 nm outward construction envelope for its actual filled edge.
Saved fill must lie inside that explicit domain, whose foreign-copper
clearance is checked. This is **not** a copper-loss or clearance tolerance:
every conservative source conductor must remain wholly covered, and the
regressions still reject even 1 nm of source copper loss. Existing rated
widths and the 0.25 mm same-net zone feature floor were not relaxed.

`cec_force_sense_evidence.compare_contour_preservation` freshly applies the
absolute clipped-copper admission to the two already-positive `+5V_MAIN`
physical legs. Their geometric cuts still pass. A PAD-vertex-only graph
deletion observes new paths through the expanded landing without actually
subtracting the pad's copper geometry; that diagnostic observation is not
treated as a geometric Kelvin cut. Rebinding those bounded observations is
permitted only after fresh positive absolute geometric proof, with exact
authority/physical-leg inventories and observation counters. Unresolved or
failed cuts cannot use this path. All twelve unresolved Kelvin legs remain
**UNKNOWN**; no current, thermal, sharing or release qualification is inferred.

### Results, regression coverage and publication

The same saved-board receiver reports **81 to 81 opens**, **5 to 5 scored
DRC** and **560 to 560 raw native findings**, with no new native fault ID,
full-registry failure ID or field blocker. The full registry remains
27 PASS / 9 FAIL / 3 DECLARED / 11 N/A. This slice closes no new connection.

The shared power-contour audit now detects compact rounded native zones as
well as short wide tracks and unequal-width joins. On the exact same source
it reports **41 reviews**, versus **39** on the candidate: the circular-zone
finding is gone and the lower round cap is wholly enclosed in actual native
chamfered copper. The old 40-review count did not inspect zones. Actual
source-retaining copper coverage, not an owner-name assertion or a fake
outline, is required to remove a visible cap review. The remaining 39 reviews
are still disclosed, not silently declared repaired.

The expanded audit caught a real integration regression: the proposed-route
read-only board adapter did not expose retained native zones. It now forwards
`Zones()` from the real board. The final focused suite passes **589 tests and
24 subtests**, retaining the same two explicitly deselected inherited
expired-budget cases described above; this is not a claim that full CI is
green. Tests exercise all cardinal rotations, mirroring/backside placement,
renamed nets, stale/rehashed plans, ownership, source retention, holes,
foreign copper, actual saved native fill, 1 nm loss rejection and strict
unknown/authority/cut handling.

`build/purposeful-landing-controls-20261003-di/receiving.json` replays the final
code on the immutable archived PCIe2 fabrication-review control and the Hub
private control. Both retain zero opens / zero scored DRC, exact native
copper, physical pair and field evidence, with zero new native items. Their
inherited electrical/manufacturing limitations remain unqualified.

[Exact chamfered-landing board review](http://localhost:8090/?id=pass-atx-purposeful-landings-review-20261003-dj-atx-24pin-rev3-f639435f14)
has a fresh top and bottom native no-body render and all six copper-layer
plots, all bound to candidate SHA256 `d7b674787109818c...`. Both full renders
and a native close-up were visually inspected. All eight live HTTP panel
responses were fetched and their bytes matched the archive hashes. The
top, bottom and detail PNGs were copied into the real Windows directory
`C:/Users/Admin/Documents/CEC-Board-Reviews/atx-purposeful-landings-review-20261003-dj/`
and each mirror's hash was checked. The detail's source/crop/hash receiving
is `build/atx-purposeful-landings-review-20261003-dj/detail/visualization-receiving.json`;
it magnifies existing native CAD pixels or crops the unchanged native SVG
view window, and creates no illustrative copper. The dashboard tab request
was queued by the app; the live HTTP verification, not that queue, proves
the panels are served correctly. The archive remains **BLOCKED / NOT FAB
SIGNOFF**. No automation, source promotion, commit or push was made here.

## 2026-10-03: incoming 12 V join and exact-count centered field

The next user-highlighted item was the incoming front-layer trace's rounded
end at the six-barrel bank. The lower ten-barrel field also needed to be
centered in its native front landing. This continuation starts from the
already received `d7b674787109818c...` candidate above, not an older board.
The accepted private continuation is:

- `build/atx-centered-link-chamfer-20261003-du/candidate-private/board.kicad_pcb`
- SHA256 `e0dbf1484d4ac7fc724bf10167c0a3016dade13fa3c7469187977676124be457`
- Receiving: `build/atx-centered-link-chamfer-20261003-du/receiving.json`

### Causes and reusable construction

The legacy field generator took the first N seats of a ring-ordered grid.
Ten seats became a nine-seat block plus a side outlier. The production
`cec_force_rails` site selector now tries bounded, centered, exact-count
portfolios from `cec_via_field_layout` before its existing obstacle-qualified
fallback. The count, pitch, reach, barrel dimensions and full-layer landing
checks are still required. Shape evidence distinguishes an actual centered
180-degree-symmetric field from an obstacle-qualified asymmetric fallback;
neither observation is an electrical rating or release qualification.

The explicit native relocation owner retains every barrel identity, drill,
diameter, type, span and lock, binds its real same-net support tracks, checks
foreign pad/track/via clearance on every copper layer, and can only expand
declared other-side landing zones outward. A new saved receiver verifies
complete actual copper around every barrel on both landing layers. It never
credits a phantom slab, an unfilled outline, approximate area, or a removed
barrel as successful placement.

The incoming pair of tracks measured 3.00 mm against the existing compiled
12 A, 1.25-margin, front-layer width floor of 3.2305914619680833 mm. This
continuation does not invent a load or recalculate the agreed budget. The
owned link recompiles those two existing native tracks to **3.230592 mm**
(upward integer rounding), retaining their UUIDs/net/layer/ownership and all
physical pads, barrels, main buses and other tracks. A bounded 0/45/90
portfolio lands on an actual barrel, with its entire annular envelope inside
the real rated conductor. It does not require an arbitrary free-ended circle
or insist that a wide conductor's centerline end be at the via center.

The two source tracks are enclosed in one native chamfered zone. Separate
overlapping same-net covers were rejected: native filling voided part of one
cover around its sibling, and the exact enclosure receiver correctly found
missing copper. The reusable explicit convex-support cover derives every
0/45/90 face from the union of the actual owned source capsules. It preserves
their real width, performs foreign-copper checks, and refuses rehashed
arbitrary contours. The original real tracks remain present; no ghost
current capacity is claimed.

The lower ten-barrel bank is now centered at (48.55, 54.1125) mm. It is an
exact 180-degree-symmetric, opposite-corner-omitted 4-by-3 lattice, not a claim
of a complete rectangular array or reflection symmetry about both axes.
All ten 0.9/0.5 mm through barrels and the existing rated front conductor are
retained. The back landing expands only as received by the native owner.
The front conductor is not narrowed to the hole field's width: symmetry
alone is not authority to reduce current-rated copper or barrel count.

The upper ten-barrel bank cannot be centered at the current front landing
center: every bounded candidate collides with `/SENSE3V3_LO` copper on
In2.Cu. The six-barrel incoming field likewise cannot be centered in its
current clipped patch with full native annular coverage. Both remain
unchanged. A future joint landing/field proposal must preserve the existing
current and main-bus constraints rather than move a priority rail solely for
appearance.

### Local ground receiving is not global fill normalization

Moving through barrels requires the two dedicated ground planes to receive
their new clearance holes. A global KiCad fill also changed small, unrelated
features far from this field. The strict source-outside-region comparison
rejected `...-dr`; those changes were not waived. The reusable local-ground
owner now constructs only actual source native copper outside the declared
old/new barrel clearance windows, plus actual KiCad-refilled native copper
inside them. It changes no plane outline or configuration, saves no invented
plane geometry, and independently receives the resulting saved native fill.
The exact source/candidate native differences outside those windows are
empty; inside them no old clearance hole is reused in place of the actual
new native refill. No full-board power refill was performed.

KiCad's fractured fill-hole bridges are retained and hash-bound as native
representation. This does not relax the simple-polygon supporting-zone
checks, simplify old copper, grant an area tolerance, or qualify unresolved
geometry. The separate locality differences remain strict, and tests reject
even a one-nanometre loss in the received fill.

### Verification and visible handoff

The saved continuation retains **81 opens / 5 scored DRC / 560 raw native
findings**, with no new native fault ID, registry failure ID, field blocker,
lost terminal connection, rated current component, pad/placement change,
sidecar change, or ownership change outside the explicit construction.
Typed physical/Kelvin evidence remains preserved, with unresolved legs still
UNKNOWN. This local geometry slice closes no additional connection and is
**not fab signoff or a new thermal/current-sharing qualification**.

The local harness passes a PCB path as its electrical hint; its mount-policy
reader expects the canonical board identifier instead. Consequently both
source and candidate registry receipts show 26 PASS / 9 FAIL / 3 DECLARED /
11 N/A / 1 ERROR (`mount-holes-present-clear`, identity-format mismatch).
That common error is disclosed, not counted as a mount qualification or
silently called PASS. The independent native pad/pose/settings preservation
checks remain exact. Canonical-identifier replay is required for the final
mount qualification; this candidate stays BLOCKED.

The final focused suite passes **813 tests and 26 subtests**, with the same
two inherited expired-budget cases explicitly deselected. Added synthetic
coverage exercises exact-count fields, all cardinal rotations/mirroring,
actual saved native links and fills, stale/rehashed owners, unchanged wider
source widths, all-layer obstacles, real supporting-track identity, full
annular coverage, local ground provenance, and one-nanometre loss rejection.
This is not a full-CI claim. Current-code replay in
`build/purposeful-centered-controls-20261003-dv/receiving.json` retains exact
native copper, pair/field evidence, zero opens / zero scored DRC and zero
generated items on both archived PCIe2 and Hub private controls. Their
inherited limitations are not newly qualified.

[Incoming join and centered lower field review](http://localhost:8090/?id=pass-atx-centered-link-review-20261003-dw-atx-24pin-rev3-dad101a2d9)
is bound to SHA256 `e0dbf1484d4ac7fc...`. The top render and native close-up
were visually inspected. Windows mirrors are in the real directory
`C:/Users/Admin/Documents/CEC-Board-Reviews/atx-centered-link-review-20261003-dw/`,
with individually verified source/mirror hashes. The app tab request was
queued, so it is not treated as evidence of a visible browser tab. No source
promotion, commit, push, automation or additional routing campaign was made.

## 2026-10-03 generic search acceleration and full signal-layer continuation

### Retained result and immutable inputs

The preceding 81-open continuation is the immutable source for this slice:
`build/atx-centered-link-chamfer-20261003-du/candidate-private/board.kicad_pcb`,
SHA256 `e0dbf1484d4ac7fc724bf10167c0a3016dade13fa3c7469187977676124be457`.
The independently received continuation is
`build/atx-unused-transition-finalized-20261003-ev/candidate-private/board.kicad_pcb`,
SHA256 `3282641efa772a70b18e11f5a9c497255b6473a5d15291f1aa4ce827e70f5248`.

ATX improves from **81 to 79 opens**, retaining **5 scored DRC / 560 raw
native findings**. One connection on the THRESH net and the remaining
ATX_PWROK connection close. The former uses fourteen new track legs and three
vias; the latter uses ten legs and two vias. These are net-scoped calls to
the shared router, not reference-designator or coordinate-specific routing
repairs. Independent receiving in
`build/atx-unused-transition-receiving-20261003-ew/receiving.json` accepts the
private continuation with no new native fault ID, registry failure ID or
field blocker. Original pads, poses, settings, protected power conductors
and prior native terminal/current partitions remain preserved. Existing
ground-plane clearance changes are independently received by reconstructing
the immutable source plus additions and replaying native ground filling;
this is not a blanket fill-difference waiver.

The registry remains **27 PASS / 9 FAIL / 11 N/A / 3 DECLARED**. Fresh typed,
clipped Kelvin receiving preserves **4 PASS / 12 UNKNOWN / 0 FAIL** across
the sixteen expected legs. The 39 inherited power-contour review findings
remain. This board is **not fab-ready**, and no load, thermal, current-sharing,
field, pair, mechanical or release gate was weakened or newly qualified.

### Causes and reusable changes

- The policy reader now resolves canonical identifiers, aliases and owned
  PCB/directory path hints consistently, while rejecting unknown,
  cross-owner, malformed and misfiled identities. Canonical-name and PCB-path
  replay agree on the current ATX registry. The earlier common mounting
  reader ERROR is now a narrow policy PASS, not new stack fit qualification.
- The new immutable planar search guard prunes same-layer parallel
  aggressor/victim obstacles using the existing angle, overlap and separation
  rules. It has bounded snapshots and scalar bridge diagnostics. Different
  layers and point-like objects are not declared safe by this prefilter;
  complete native/refilled field receiving remains mandatory.
- The shared field classifier now interprets a structured net-class record
  through its declared `name`, rather than tokenizing its serialized geometry
  metadata. Previously, the ordinary KiCad `diff_pair_width` property made a
  Default-class dictionary look like a DIFF class to the new prefilter.
  Malformed explicit class identities fail closed. This repairs that new
  prefilter's false obstacles; it does not dismiss earlier genuine field
  refusals or relax the existing sensitive-net protection rules.
- The multilayer maze reuses exact foreign-copper and drill snapshots within
  one immutable plan. Previously, transition-via tests rebuilt native copper
  and rescanned drills at thousands of grid nodes. Each new plan gets fresh
  snapshots, including after same-count native geometry moves. The actual
  copper/hole predicates and final receiving are unchanged.
- Multilayer fallback now has the complete authorized non-plane signal-layer
  pool, independently of the preferred direct-bridge layer. A failed direct
  F.Cu bridge no longer excludes a legal F.Cu segment inside a multilayer
  detour. Endpoint access, plane exclusions, widths, drill clearance and
  field receiving remain native and contract-bound.
- Selected paths omit a newly proposed endpoint transition via only when the
  actual selected first/last track and endpoint stub already share an
  endpoint-owned layer. The normalized proposal is rechecked. Existing source
  vias and necessary middle transitions are never removed or waived.

### Bounded trials, performance and regression evidence

Initial bounded passes made no connection improvement. After snapshot reuse,
the ordinary pass in `build/atx-fast-native-transition-20261003-ek/` took about
122 seconds and reduced 81 opens to 80. The subsequent full-layer pass
proposed 79, but independent receiving in
`build/atx-full-signal-receiving-20261003-es/receiving.json` rejected a new
dangling endpoint via. The receiver was not weakened. The generic selected
endpoint-via repair then rerouted the affected net in approximately 6.7
seconds with two rather than three vias. The final whole-source receiving
above retains 79 opens with the original raw finding count. The rejected
three-via candidate is not a continuation source.

The exact-operation benchmark in
`build/native-via-exact-parity-benchmark-20261003-ej.json` compares 96
deterministic native via-site probes on the immutable source. Exhaustive and
indexed guards give identical verdicts for all 96 sites, accepting 37 each,
without source mutation. Measured time is 3.5049 seconds versus 0.0798 seconds,
or approximately **44 times faster for that via-site guard operation**.
This is not a whole-router or end-to-end pipeline speedup claim.

The final focused suite passes **534 tests and 56 subtests**. It covers
structured class parity/fail-closed behavior, production detours, exact
cached-versus-exhaustive native geometry, fresh snapshots, complete signal
layer pools, unnecessary endpoint-via omission, native receiving, current
and sense evidence, pair/field protections and route craft. This is not a
full-CI claim. Focused diff whitespace checks pass.

Current-code cross-board receiving in
`build/full-signal-endpoint-controls-20261003-eu/receiving.json` leaves the
archived PCIe2 fab-review control and the current Hub private control at
**zero opens / zero scored DRC**, with no source mutation or newly generated
ordinary, supply or pair items. Their existing physical pair/field evidence
and inherited review limitations remain unchanged. Neither control's
inherited status is promoted to release qualification by this replay.

### Visible handoff and next owners

[Current 79-open ATX continuation](http://localhost:8090/?id=pass-atx-full-signal-review-20261003-ex-atx-24pin-rev3-50b834b18e)
is tied to the exact accepted candidate above. Publication and independent
publication receiving are under `build/atx-full-signal-review-20261003-ex/`.
The live delivery receipt, `live-dashboard-receiving.json`, independently
checks health, the unique catalog identity and exact HTTP image-byte hashes
for all eight panels: top and bottom renders plus all six native copper
layers. HTTP 200 alone is not considered successful delivery.

Real Windows copies of both native renders are hash-verified and visually
inspected in
`C:/Users/Admin/Documents/CEC-Board-Reviews/atx-full-signal-review-20261003-ex/`.
Top render SHA256 is
`97d45a911af8e9233c9e8d4d6e2c094bc3d0e4e38cb9140e115105b6e6ab03b6`;
bottom render SHA256 is
`1588e840c94d49df97b4a70b9e7a79728b256452bd2bbfcd24a4ccb530b88767`.
These are native candidate views, not synthetic copper or a stale seed.

The original native open ledger in `build/atx-open-ledger-20261003-dx.json`
separates current-domain, specialized supply/sense, ordinary, physical-pair
and ground debt. This slice closes two ordinary connections, not the
protected power or specialized sense/pair construction. Next work must
address qualified local pin escapes and their placement/ownership causes,
and explicit protected-current/supply contracts, rather than repeatedly
retrying the same bounded maze or moving a priority power bus to force a
pass. Missing supply budgets must not be invented. No BETA/source promotion,
commit, push or release-authority change was made in this slice.

## 2026-10-03 follow-up: whole-run contours and native pad landings

This is a bounded copper-style slice, not an open-closure or fabrication
qualification claim. The immutable input is the accepted 79-open continuation
at `build/atx-unused-transition-finalized-20261003-ev/candidate-private/board.kicad_pcb`,
SHA256 `3282641efa772a70b18e11f5a9c497255b6473a5d15291f1aa4ce827e70f5248`.
The independently received child is
`build/atx-final-native-run-repairs-20261003-fm/candidate-private/board.kicad_pcb`,
SHA256 `ef4f6208f763adbece6387f7a4ff6648d7bbbcfcab3f3eb476ac624fce2f49f1`.
Its receiving receipt is in the same directory. Both retain **79 opens,
5 scored DRC and 560 raw native findings**, with no new native fault identities,
full-registry failures or field blockers. Existing terminal/current partitions,
physical pair evidence and scoped typed contact evidence are preserved. The
registry remains 27 PASS / 9 FAIL / 11 N/A / 3 DECLARED. It is not fab-ready.

### Generic causes and repairs

- `cec_power_contours` now detects wide equal-width elbows as well as short
  capsules and unequal-width joins. A named zone or dashboard appearance is
  not suppression authority: the complete real capsule must be inside actual
  saved same-net filled copper. Native contacting-run requests bind the full
  component and its lock/group identities. A separately compiled resident
  width floor can exclude an unresolved narrow launch without pretending that
  it was widened or qualified.
- `cec_rectilinear_copper` now supports exact integer concave fill domains.
  The empty space inside a hook is retained rather than convex-hulled across.
  Source capsules remain real native tracks; no invented FEM copper or virtual
  current capacity is credited. Construction and independent saved receiving
  freshly derive the profile from native source strokes and bound source zones;
  a rehashed extra copper slab is rejected. Foreign actual filled zones are
  checked along with real pads/tracks, and unfilled foreign copper remains
  unknown rather than being inferred from an outline.
- `cec_pad_landing` reconstructs only an explicitly owned pad-center terminal
  overhang. The native pad geometry, unchanged nonterminal endpoint, existing
  dimensional floor and full-width overlap into the real pad are bound and
  independently received. A same-net pickup on the discarded excess, a drill,
  unsupported angle/shape, stale source, rehashed witness or even one nanometre
  of overlap loss refuses the proposal. This is not general dead-end trimming.
- Same-priority intersecting native owners now request consolidation before
  filling or expensive whole-board receiving. The additive owner cannot
  renumber an existing zone or hide its intersection. Canonical source-landing
  unions retain intentional concavities; bounded step closures may only add
  copper while respecting actual foreign copper and source-zone clearance.
- Multi-net construction receives the actual native filled prefix before
  installing the next owner. An authored but unfilled previous contour is not
  treated as obstacle evidence. The unknown-fill guard is not bypassed.

The accepted child repairs the four-track +5VSB run, the seven-track resident
3.3 V loop, and the four-track 12 V return run. Two physical pad landings are
received. The 12 V return uses the existing **3.230592 mm** compiled floor;
its old round cap could not simply be widened in place because that would
encroach on a real 3.3 V signal. Only the pad-center overhang is shortened,
and native full-width contact into the unchanged shunt pad is proved. The
other narrow power launches and inherited electrical/thermal debt are not
qualified by these repairs.

The older classifier counted 39 ATX style findings. Adding the previously
missing equal-width-elbow class yields 89 on the exact unchanged input, not
50 newly introduced board defects. Under that same expanded classifier, the
accepted child has **76** findings (31 short capsules, 42 wide elbows and
3 unequal-width joins), versus 34 / 50 / 5 on the input. This is 13 fewer
review findings, not 13 closed electrical connections or a DRC reduction.

### Fourth user-highlighted spot: not accepted or published

The upper 12 V diagonal/via landing remains unchanged. Its convex enclosure
would encroach on **D5 pad 1, GND**, as captured in
`build/atx-upper-landing-obstruction-20261003-fh.json`. A canonical, concavity-
preserving source-landing trial avoided that pad, but whole-board native DRC
in `build/atx-native-notched-landing-20261003-fi/receiving.json` rejected an
intersection with the existing same-priority contour owner. The trial retained
79 opens but introduced a native `zones_intersect` identity, so it was not
accepted, used as a continuation, or published. The next appropriate owner
is native same-owner zone consolidation with old filled-copper/contact/current
preservation, not an extra overlay, priority escalation or clearance waiver.

### Validation and visible handoff

The final focused groups pass **916 tests and 56 subtests**: 382 native contour,
pad-landing and contact tests plus 534 routing/current/pair/field tests. This
includes rotations, mirrors, front/back layers, native saved fills, intentional
notches, foreign filled zones, same-priority owner collisions, exact overlap
loss, rehashed slabs and multi-net fill prefixes. This is not a full-CI claim.

`build/contour-final-routing-controls-20261003-fk/receiving.json` replays the
archived PCIe2 fab-review and Hub private controls under the final code epoch.
Both retain zero opens / zero scored DRC, exact native copper and unchanged
physical pair/field evidence, with no newly generated ordinary/supply/pair
items. Their inherited review limitations remain; neither is promoted to
release qualification. Expanded contour detection does not mutate a control.

The fresh review is under `build/atx-native-run-review-20261003-fl/` and is
bound to the accepted child SHA above, not the refused upper-landing trial or
an older board seed. Native closeup rendering uses a fresh saved F.Cu export
without silk text; every copper path is retained and only review viewports
change. Publication and live HTTP panel byte-hash receipts accompany the
review. No BETA/source promotion, commit, push or release-authority change
was made in this slice.

### Final keeper-consolidation follow-up and final code epoch

The shared contour owner now has an explicit native-keeper consolidation mode.
It requires the keeper's own lock/group authority and retains its UUID, native
group, priority, clearances, minimum feature size, solid connection and all old
filled copper. It is not additive overlap or priority renumbering. Construction
and independent saved receiving derive the new profile from the immutable old
keeper and declared source strokes/landings. Missing old fill and any lower-
priority filling of an unchanged higher-priority landing's clearance void
remain refusals. Rotations, mirrors, both outer layers, stale/rehashed source,
configuration changes, one-nanometre loss and lock identity have regressions.

The actual ATX keeper trials `build/atx-native-owner-consolidation-20261003-fo/`
and `build/atx-native-owner-consolidation-20261003-fq/` remain unadmitted.
The first exact deficit was a one-nanometre-wide sliver on an authored diagonal.
An explicitly declared outward construction margin addressed that edge without
an area tolerance, but native refill still retessellated an old clearance
boundary and lost a small positive region. Independent diagnostic geometry in
`build/atx-keeper-final-loss-inventory-20261003-fu.json` agrees it is positive
loss, not just a spurious native Boolean. The same trial also has native
lower-priority fill in the unchanged source landing's **0.5 mm** clearance void.
The source was unchanged and the trial was not saved or published. A synthetic
native-fill regression reproduces this same-net zone-priority behavior: a
passing global minimum alone cannot prove the stronger regional void survived.
The receiver explicitly refuses it rather than assuming native fill is enough.

The final accepted three-spot child, reconstructed under the final code epoch,
is `build/atx-native-run-final-epoch-20261003-ft/candidate-private/board.kicad_pcb`,
SHA256 `9dba45099c0868353859a9d0d8374f5b748227690eeefeed0a194279bc6fa214`.
Its receipt supersedes the earlier three-spot child as the current-code handoff.
It retains **79 opens / 5 scored DRC / 560 raw native findings**, no new fault,
registry-failure or field-blocker identities, exact terminal/current partitions
and scoped typed evidence. Its expanded contour count is **89 to 76**. The
upper user-highlighted landing is still unchanged and explicitly labelled so;
no claim is made that all four spots or the whole ATX board are closed.

The combined final focused suite passes **941 tests and 56 subtests** under
that code epoch, not full CI. Current-code archived controls are in
`build/contour-keeper-controls-20261003-fr/receiving.json`; PCIe2 and Hub remain
zero opens / zero scored DRC with exact native copper, physical pair/field
evidence and no generated ordinary/supply/pair items. Existing inherited
limitations remain unqualified. The final publication is under
`build/atx-native-run-final-review-20261003-fv/`, with its live eight-panel byte-
hash receipt. Native copper closeups are under
`build/atx-native-final-closeups-20261003-fw/`. These references bind the exact
final accepted child, not either refused keeper trial or an older board seed.

### 2026-10-04: regional native-fill ownership and scoped-router execution

The upper `/SENSE12V_HI` landing has a separately received construction in
`scripts/cec_regional_fill.py`. Its policy binds the exact immutable source
keeper, real retained rated tracks, all relevant same-net higher-priority
regions, their native filled copper and their actual fabrication configuration.
The source higher-priority field's **0.5 mm** clearance void is not replaced by
the lower keeper's **0.2 mm** minimum. Raw same-net native refill can soften
that stronger void even while global minimum-clearance checks pass; the
construction subtracts the actual protected regional void from additions.

The existing positive source contour is retained verbatim as a native filled
record. There is no area/nanometre-loss waiver. This avoids the measured one-
nanometre facet loss produced by native Boolean retessellation. These records
are a physical set union, not additional thickness or a second current credit.
New additions are native-compiled copper only, must retain the existing
minimum-feature floor and must reach actual source copper. Generated hairline
fringes and floating islands are removed; incumbent copper is not eroded.
Island indices are reset before installing the reordered fill records.
`cec_native_fill_geometry.py` handles exact saved native hole-bridge identity
without simplifying or interpreting repeated bridge vertices as area loss.

Independent receiving reloads immutable source geometry and recompiles the
owned native zone on a separate native save/load copy. Changed source/fill,
priority/process, invented or rehashed region bindings, one-nanometre tampering,
missing source context and unowned refill bypasses are refused. Saved native
rotation/mirror/front/back regressions exercise this path. A passing local
construction is not current, Kelvin, thermal or fabrication qualification.

All selected-zone compilation now passes through `cec_zone_fill.compile_selected`:
native priority ordering, bounded scope/deadline and exact two-pass settling.
The AST regression caught raw filler bypasses in the new owner and two older
receivers; the callers were repaired, not allowlisted. A global unowned refill
detects overlapping positive source-preserving records and refuses **before**
UnFill. The declared owner and immutable-source receiving must be replayed;
the full automatic pipeline does not yet have authority to discard that recipe.

Final-code regional receiving is
`build/atx-regional-landing-20261004-i/receiving.json`. The accepted native
child remains SHA256
`15767fdbafb4e482a404283b9a6aff7c0e66129b439e359d3459b1cf06beb20d`,
from the explicit three-spot parent
`9dba45099c0868353859a9d0d8374f5b748227690eeefeed0a194279bc6fa214`.
It preserves all original rated/terminal partitions, poses, pads, board settings,
sidecars, physical pair/field evidence and scoped typed sense evidence. Native
DRC has no new finding identities and the full 50-check registry has no new
failure identities. **79 opens / 5 scored DRC / 560 raw findings / 76 contour
review findings** remain. The 50 statuses remain 27 PASS / 9 FAIL / 11 N/A /
3 DECLARED. Clipped sense evidence remains 4 PASS / 12 UNKNOWN, not 16 qualified.
The landing repair is not an improvement in opens.

`build/regional-fill-controls-20261004-d/receiving.json` receives archived PCIe2
and the private Hub control under the same final code. Both retain zero opens /
zero scored DRC, exact source/native copper and no generated routing items.
PCIe2 retains one inherited pair refusal and its pre-existing qualification
debt. The Hub control is not thereby promoted to production or fabrication.

The scoped detailed-router investigation exposed a different execution issue.
On the pinned `freerouting-1.7.0-cec3` jar, **`-oit` is an improvement threshold,
not seconds; zero does not disable optimization**. A live JVM stack from the
150-second timed-out trial was in post-route optimization. This observation
does not prove every normal production wave used the same mistaken setting.

`cec_dsn_routing_settings.py` and `cec_fr02.set_postroute_in_dsn` now provide an
explicit, opt-in native postroute setting. The bounded quote-aware edit keeps
every byte outside the owned execution scope exact and refuses ambiguous,
duplicate, malformed or timed-out input. Settings must follow all layer
definitions and precede the first plane: the pinned parser ignores a late
settings scope. A newly created settings object uses the parser's integer
constructor, whose unspecified layer flags, via flags and costs are zero.
Consequently a new scope declares the complete signal-layer/via/cost search
profile and keeps power-plane layers inactive. This is a declared search
profile, **not equivalence to absent-settings heuristics** and not a relaxed
physical rule. Existing authored settings are not silently changed. Normal
waves retain their previous execution settings unless their owner opts in.

The 2.7-second partial-profile smoke run disabled routing and is explicitly
**excluded from valid speedup claims**. The corrected native-backend synthetic
tests actually close a same-layer signal and an opposite-side signal requiring
a via, then check native DRC and immutable source bytes. Test footprints have
valid library identities; anonymous empty footprint IDs are not a valid SES
import fixture. The opt-in test command uses `CEC_TEST_NATIVE_FR=1`.

The valid complete-profile ATX reconstruction performed eight backend passes
in about 49 seconds, but a saved proposal in
`build/atx-scoped-regional-20261004-g/proposal/board.kicad_pcb` is **rejected**.
It reduced native opens provisionally from 79 to 72 while adding 152 items,
but independent receiving found 111 new native finding identities, scored DRC
116, new field/pour-incursion failures and unacceptable route craft. This
proposal is not the dashboard's accepted board and does not improve the best
board. Neither this changed search profile nor its export scope is an apples-
to-apples speed benchmark against the earlier 150-second trial.

The causal export/projection mismatch is explicit: removing several ordinary
nets' old routes from the detached export allows their new routes to cross
each other's originals, which the actual monotone-addition parent retains.
The bounded workbench now refuses multi-net reconstruction in that mode.
A single net may omit its own ordinary copper while **all foreign nets remain
frozen obstacles**. Production input copper, parts and pours are never deleted.
The KiCad 10 via UUID property is read-only; native Duplicate identity is checked
rather than assigned through an unavailable setter. These are workbench fixes,
not a claim that a complete autonomous routing-stage contract is integrated.

The first single-net trial, `build/atx-scoped-regional-20261004-h/`, selected
one real `/THRESH_PWM` open generically from the native open inventory. It added
nothing and remained at 79 opens in 11.6 seconds. Its backend still reported
37 incompletes initially, demonstrating why backend counts are not trusted as
native board connectivity or as proof of eligible routing scope. Excluded
backend additions are not projected into the parent. Further work must address
actual source-aware pin escape and backend ownership, not repeat cosmetic
waves or weaken admission until a raw-count reduction passes.

Final focused validation under that frozen code passes **725 tests and
29 subtests in 142.99 seconds**, including both enabled real pinned-backend
fixtures; this is not full CI. The source-preserving native landing/control
receipts above were regenerated under the same final code, not reused across
an unverified code change. No production board, schematic or BOM was edited,
no release gate was waived, and no Git stage/commit/push was performed.

The final accepted-board publication is
`build/atx-regional-review-20261004-c/atx-24pin-rev3/` with dashboard ID
`pass-atx-regional-review-20261004-c-atx-24pin-rev3-c16278cad2`.
`build/atx-regional-review-20261004-c/live-dashboard-receiving.json` verifies
all eight actual HTTP panel bodies against their native file hashes: both
PNG sides and all six copper layers. Four native copper-only closeups are
bound to that exact review in `build/atx-regional-closeups-20261004-c/`.
The geometry is intentionally identical to the accepted regional candidate,
not the unsafe 72-open experiment or a claim of fresh routing progress.

## 2026-10-04 continuation: two accepted joins and native cover reconstruction

This continuation starts from the immutable 79-open regional candidate
`build/atx-regional-landing-20261004-i/candidate-private/board.kicad_pcb`,
SHA256 `15767fdbafb4e482a404283b9a6aff7c0e66129b439e359d3459b1cf06beb20d`.
It is not the rejected lower-open export experiment. Existing component/pad
positions, real bus tracks, current budgets, board size, sidecars and source
boards remain unchanged.

### Accepted connectivity, not backend incomplete counts

A scoped backend trial retaining the complete native foreign pin/copper
context produced a provisional 76-open result. Independent saved receiving
rejected its new CAN_TX field-coupling defect: a 45-degree crossing against
the inner 5VSB return with insufficient actual reference-plane shielding.
The entire newly generated CAN_TX addition was quarantined, without removing
any original source copper. The remaining ordinary additions close one
DET12V and one I2C_SCL gap: **79 to 77 native opens**, with no new native fault,
full-registry failure, field blocker, pair change or typed Kelvin regression.
I2C_SDA has partial added copper but no credited complete-net closure.

Final frozen-code receiving is
`build/atx-full-context-receiving-20261004-d/receiving.json`, for candidate
`build/atx-full-context-field-probe-20261004-a/proposal/board.kicad_pcb`,
SHA256 `31586b8cdffab371ca6f7efce35dfe0746a5100c2477044731ecea80446dfb9e`.
All old native items and prior terminal/current partitions are preserved.
The raw native DRC inventory remains 560, the scored structural count remains
5, and the full registry remains 27 PASS / 9 FAIL / 11 N/A / 3 DECLARED.
Typed clipped physical evidence remains 4 PASS and 12 UNKNOWN of 16 expected
sense legs; this is not thermal/ampacity or release qualification.

Another three-pass backend trial also produced a rejected CAN_TX completion,
but its failure was different: one newly added through-via punched a clearance
hole in the actual In1 ground fill that shields two unchanged CAN_H/CAN_L
routes from SENSE3V3_LO. The failed interaction records contained only OLD
track identities, so an endpoint-only new-track repair portfolio could not
identify the new copper responsible. This was not the first trial's 5VSB
crossing. A bounded diagnostic ablation of each new via identifies exactly
one new barrel whose removal eliminates both new field blockers; that
removal is deliberately an incomplete diagnostic, never a valid route or
admitted board. Evidence is `build/atx-crossing-portfolio-20261004-c/report.json`.
A subsequent field-guarded bounded native completion
pass closes zero more opens in 24.6 seconds. The separate local ground-return
trial checks four actual disconnected terminals and creates no new return.
These zero-progress/rejected trials are not reported as accepted closure.
Pin-exclusion/full-context selection changes in the root workbench are NOT a
claim that production lacked obstacle guards: the existing production staged
export already has its own guarded keepouts. Backend incomplete counts remain
untrusted, and the full autonomous pipeline is not declared complete here.

### Generic geometry fixes and unchanged actual conductors

`cec_rectilinear_copper` now supports opt-in bounded canonical jog cover,
integer 0/45/90 geometry, occupied-space checks and independent native
zero-loss receiving. Small cosmetic steps may be covered only within the
declared displacement/area bound; large placement pockets are not bridged.
Top-return and upper-12V cover cleanups pass complete saved-board receiving.

The compound native-fill adapter preserves literal multiple outlines, holes
and serialization bridges. Regional fill can operate on its own prior output
without pretending that a compound native polygon is a simple outline.
Repeated passes preserve every explicitly retained original source record.

An additional explicit owned-keeper reconstruction can discard excess old
cleanup-cover pixels while retaining ALL enclosed actual native tracks at
their exact original widths, endpoints, layers, identities, locks and groups.
It is not blanket power-plane trimming authority. Complete native stroke
membership is independently rederived against the immutable old owner during
planning, construction and saved receiving. Whole-board terminal, current,
Kelvin, field, pair, DRC and full-registry receiving remain mandatory.

The 5VSB elbow now uses a compact square profile rebuilt from its four actual
unchanged power tracks, removing the earlier pointed excess shoulder.
Final receiving: `build/atx-recompiled-keeper-20261004-e/receiving.json`.
Published candidate:
`build/atx-recompiled-keeper-20261004-e/candidate-private/board.kicad_pcb`,
SHA256 `3279a02be835a590bd4e60301aef79692a2ee1eff3e10e4bc63c376c227d30bf`.
The accepted shape change remains at 77 opens / 5 scored blockers. It does
not claim that every lower terminal overhang or crooked/off-center landing
has been fixed.

### Refusals expose the unresolved geometric causes

The lower-right keeper rebuild initially refills a higher-priority native
landing's clearance void. The separately bound conductor-preserving regional
policy clips native compiled additions to those actual protected regions,
does not append the superseded cover, retains no unproved floating anchor,
and independently regenerates the exact expected saved fill. Unlike the
default source-preserving policy, it does not claim literal old-cover retention.
Its ATX trial still refuses actual-stroke enclosure for one original 6.535523
mm conductor. The missing-cover diagnostic is saved in
`build/atx-recompiled-keeper-20261004-d/receiving.json`; its detached geometry
is explicitly `UNADMITTED-native-geometry.kicad_pcb`, not the published board.
No copper-loss tolerance, hidden capacity or weakened regional clearance is
used to admit it. Endpoint/landing reconstruction still needs attention.

The upper +5V_MAIN physical field contains ten barrels across the two native
landings. The top octagon fully contains only eight disks; its bounding-box
prefix finds nine. This discrepancy explains why a visually plausible prefix
can be off-center and omit a barrel without being an actual complete field.
Read-only disk evidence is
`build/atx-upper-field-native-inventory-20261004-a.json`.

The generic actual-barrel frame constructor refuses incomplete or asymmetric
source inventories. The coupled field/center-landing owner can alternatively
derive symmetric exact-count seats around the COMPLETE joint native inventory's
integer centroid, with unchanged barrels/spans, all-layer foreign clearance,
an explicit existing current-width floor, unchanged other-side source fill,
and local ground-window receiving. A rehashed oversized frame or missing
barrel cannot authorize construction. The ATX attempt in
`build/atx-owned-field-center-receiving-20261004-a/receiving.json` refuses a
real +3V3 track collision. The earlier fixed-landing-center attempt separately
refuses an actual inner-layer 3.3V return bus. These are bounded constructor
refusals, not board-impossibility proofs and not accepted field repairs.
No field barrel has been moved or removed in the published candidate.
These APIs are generic and opt-in; their task-workbench exercise does not
represent completed integration of an unattended whole-board closure stage.

### Frozen-code verification and actual visual delivery

Focused validation passes **867 tests plus 29 subtests in 148.84 seconds**.
This includes rotations, mirroring, front/inner/back copper, literal compound
native fills, saved/refilled owner reconstruction, complete symmetric barrel
frames, coupled exact-count fields, protected regional voids, foreign copper,
malformed/rehashed declarations and immutable source behavior. This is not
full CI; the real pinned-backend fixtures from the earlier 725-test run were
not rerun in this focused group.

`build/atx-closure-polish-controls-20261004-b/receiving.json` replays the
immutable PCIe2 fab-review archive and Hub private control under the same
frozen code. Both retain zero native opens and zero scored DRC with exact
native copper and source identities. Inherited qualification debt is retained,
not promoted to fabrication release.

Current publication:
`build/atx-closure-polish-review-20261004-c/atx-24pin-rev3/`, dashboard ID
`pass-atx-closure-polish-review-20261004-c-atx-24pin-rev3-3ab92670a1`.
It is visibly BLOCKED, not fab-ready. Its live delivery receipt verifies all
eight actual HTTP bodies: both PNG sides and all six native copper layers.
Four copper-only native SVG viewports in
`build/atx-closure-polish-closeups-20261004-b/` are bound to this exact board
hash; unresolved lower-right and upper-array views are explicitly labeled.
No old image, synthetic conductor, renderer filler or rejected lower-open
board substitutes for the published candidate. No production input board,
schematic or BOM was changed and no Git stage/commit/push was performed.

### Later accepted causal-via repair: 77 to 76 opens

The rejected second backend fragment was projected onto the separately
received square-elbow parent without changing any original item. The new-via
ablation diagnosis then guided a bounded new-copper-only repair: relocate the
causative new barrel by 0.6 mm and reconstruct its incident NEW escape tracks
as chamfered 0/45/90 legs, retaining their fixed outer endpoints, widths and
layers. Other offsets hit actual copper, craft or field refusals. No old CAN
or sense track was moved, no hole was deleted from an admitted route, and no
reference-plane sampling policy was weakened.

`build/atx-crossing-portfolio-20261004-e/report.json` records the diagnosis,
bounded construction attempts and independently finalized proposal. The
task workbench initially supplied native track objects to the read-only
craft-proposal API; its contract instead requires geometry rows and a board
without the proposed tracks. That harness call was corrected before testing
the construction, not treated as a physical routing impossibility. This
late workbench is not covered by the 867-test production-module group and
does not claim completed autonomous repair integration.

Independent whole-board receiving in
`build/atx-causal-via-receiving-20261004-a/receiving.json` accepts **77 to 76
native opens** by joining the two CAN_TX components. Across this continuation
the admitted change is **79 to 76**, not the lower count of any rejected
backend export. Raw native findings remain 560 and scored DRC remains 5.
There is no new native fault, full-registry failure, field blocker, pair
regression or typed Kelvin regression. All actual source tracks, pad/pose
identities, protected power fills, dimensional contracts and old terminal
partitions are preserved; only independently replayed native GND antipads
change with the new barrels. Unchanged clipped sense evidence is still
4 PASS / 12 UNKNOWN of 16 expected legs, not release qualification.

Latest received private board:
`build/atx-crossing-portfolio-20261004-e/finalized-private/board.kicad_pcb`,
SHA256 `45ddc95c975d466775dc8a21209ff3c64b34cd902a1300fdf8da3e921e14d9c1`.
Latest dashboard ID:
`pass-atx-causal-via-review-20261004-a-atx-24pin-rev3-d63c219116`.
`build/atx-causal-via-review-20261004-a/live-dashboard-receiving.json`
again verifies all eight actual HTTP panel bodies, including every copper
layer. Native copper-only closeups in
`build/atx-causal-via-closeups-20261004-a/` bind to this exact board hash.
It remains BLOCKED, not fab-ready.

A complete ten-barrel centering trial with a tighter 1.0 mm pitch still
refuses actual In3 sense-return collisions; its count, barrel dimensions,
existing landing and full all-layer clearance were not reduced. Receipt:
`build/atx-centered-field-compact-receiving-20261004-a/receiving.json`.
The lower-right overhang and upper off-center field therefore remain
unresolved; the square 5VSB elbow and top-return cover improvements are
retained. This is not permission to pretend an unchanged round annular pad
or unchanged obstructing conductor has disappeared from a render.

The separate native supply-bridge workbench tests the two remaining isolated
3.3 V supply terminals against the existing executable 0.2048376 A aggregate
budget, with full contract widths on every proposed layer, no inferred
sharing or neckdown and the same centralized POFV/hole/foreign-copper guards.
It does not qualify a barrel's current rating or invent another rail's load.
`build/atx-rated-supply-bridge-20261004-a/report.json` stops after 40.04 seconds
with no constructed route: origins/local POFV escapes are blocked by actual
backside/inner copper, and sampled legal remote barrel positions lack a
legal face-layer launch. The bounded menu is not an exhaustive no-path proof.
Repeated endpoint-seat searches and pin-access/placement relief remain
actionable next work, rather than recycling identical whole-board waves.

### Below-50 attempt, 2026-10-04: accepted 76 to 55, target not reached

Independent saved-board receiving accepts the monotone chain **76 -> 67 ->
60 -> 57 -> 55**. The cumulative receipt is
`build/atx76-to55-cumulative-receiving-20261004-a/receiving.json` (33.39 seconds).
Every original native terminal partition and current path is preserved. Raw
native findings remain 560, scored DRC remains 5, and no new native finding,
full-registry failure or field blocker is admitted. Clipped Kelvin evidence
remains 4 PASS / 12 UNKNOWN of 16 expected legs. This is 21 retained closures,
not fabrication signoff and not achievement of the requested below-50 target.

Retained board:
`build/atx57-passive-junction-native-20261004-a/board.kicad_pcb`, SHA256
`0fe95afe0f1599bb7dc9af209e58a4ebf370171aa983b9b140a3a961e2f59378`.
Dashboard ID:
`pass-atx55-verified-closure-review-20261004-a-atx-24pin-rev3-1c9312eb97`.
`build/atx55-verified-closure-review-20261004-a/live-dashboard-receiving.json`
verifies both live PNG sides and all six copper-layer SVG HTTP bodies against
their exact native publication hashes. Older 67-open panels are not reused as
the 55-open result. Placement and protected power-bus copper remain frozen.

Reusable changes and their limits:

- Exact DSN layer activation can restrict a detached search to declared signal
  layers without changing other DSN geometry/rules or enabling a disabled
  layer. The private probes use F.Cu/SIG2/B.Cu; this does not claim that every
  unattended ordinary-routing caller has been converted to that option.
- Additive receiving independently reconstructs source-plus-native additions,
  including existing ground antipads and exact-object POFV rules. New force
  authority joins must appear in the separately sized graph; inherited thin
  copper and unknown sense evidence do not become qualified by connectivity.
- Planar distribution uses existing explicit current budgets, full required
  widths throughout every new leg, and native finite pad/track contacts.
  Drilled terminals can share one actual copper face only after an independent
  native land-minus-drill check and a single-face graph. No barrel, pad, zone,
  parallel-current sharing or neckdown ampacity certificate is implied.
- A complete, high-impedance resistor-only junction can override a misleading
  voltage substring for routing ownership. The entire terminal inventory must
  consist of unambiguous two-land canonical resistor footprints,
  parsed values at least 1 kohm, and a different real net on the other land.
  Current contracts and precision/pair ownership still take precedence. This
  releases the three-resistor negative-rail divider to ordinary routing; it
  does not release the actual negative-12 V pass-through power rail.
- Frontier scheduling no longer charges same-island/wrong-layer anchor pairs
  to its useful-pair inventory. It still checks traversal deadlines, reports
  incomplete inventories honestly, and filters drill-centre/non-material
  contacts before spending route attempts. On the retained ATX, the 3.3 V
  frontier inventory is now complete at 2,495 useful checks rather than
  truncated at 65,536 mostly internal checks. Four invalid port drill-centre
  anchors are excluded up front. This improves coverage, not a measured
  wall-clock speedup or a no-path proof: the 59.01-second continuation still
  constructs zero new joins and remains at 55.

The routing basis explicitly records the existing shared 2.5 A Hub allocation
and a conservative 3 A SYS/MUX conductor envelope including a 0.5 A local
allowance. It is not 2.5 A per alternate header, a new component-load budget,
a regulator rating used as load, a TPS2121 fault-current clamp, inrush
qualification or an increase to owner-ratified main-rail ceilings. USB-only
service keeps its separate 0.75 A design basis. Included load margin is not
applied a second time. The all-terminal full-aggregate producer remains
conservative at fine-pitch power-input pins; load-backed individual branch
roles/qualified local power escapes are not yet implemented.

Rejected lower counts remain explicitly unadmitted:

- The unrestricted native backend's 33-open export creates native faults,
  power/reference-layer incursions, undersized current joins and coupling
  failures. Independent safe-net projections, not that export, produce the
  retained chain.
- A ground-only 56-open projection intersects a frozen +5V_MAIN backside
  landing. A CAN-only 55-open projection adds under-width pair copper and
  unshielded aggressor/victim interactions. Both are rejected.
- Certificate-derived rescheduling of seven ordinary obstruction nets removes
  107 ordinary ungrouped tracks while keeping power/pair copper fixed, but its
  54-open proposal loses existing DET5V and SDA terminal partitions and adds
  five native faults. The first independent screen is
  `build/atx55-blocker-reschedule-screen-20261004-a/screen.json`. Restoring all
  originals and projecting only its new clock/threshold/strap copper produces
  52 opens but nine shorts/crossings/clearance faults and route-craft issues.
  Neither experiment is received or published as progress.
- A dedicated native CAN search, with USB outside the transaction scope,
  confirms the bus pair is derived correctly but finds no qualified corridor
  in 57.07 seconds. It does not generate or admit any copper. Existing local
  CAN pair qualification is not a certificate for the remaining bus segment.
- Local and nearby shared-entry ground attempts create no new route. Canonical
  typed tap continuation reproduces five already-connected branches without
  reducing opens; these duplicate proposals are not retained.

Fresh cross-board replay in
`build/atx-below50-frontier-controls-20261004-a/receiving.json` preserves the
archived PCIe2 fab-review and Hub control with zero native opens, zero scored
DRC and exactly unchanged native copper. Their existing qualification scope
and debt remain unchanged. No Git stage/commit/push or production source-board,
schematic or BOM edit is made during this attempt. Workbench experiments are
not represented as a fully integrated autonomous closure stage.

The final focused group passes **376 tests in 5.36 seconds**, covering the
DSN layer parser, current-join receiving, exact additive/refill replay,
force/sense evidence transformations, ordinary ownership, native pad access,
distribution/frontier scheduling and fixed-supply rotation receiving. This
is not full CI; the existing KiCad SWIG deprecation warning remains visible.

The next causal actuator must restore every prior ordinary connection while
replanning only its proven obstructing corridor, or qualify real local
power-pin branch access from existing load authority. Global opens alone are
not an admission metric. Repeating identical endpoint/whole-board waves,
relaxing spacing, accepting thin power routes or discarding lost partitions
would not satisfy that requirement.

## Native continuation and pre-emission repair gates, 2026-10-04

The independently received continuation reduces **55 to 51 native opens**.
It retains 18 new native items on GND, +5VSB, USB_D_P and USB_D_N, closing
one component gap on each net. All earlier terminal/current partitions,
protected power copper, placement, settings and load budgets are retained.
The board is
`build/atx55-native-sb-usb-ground-subset-20261004-a/board.kicad_pcb`, SHA256
`3a5db7e83cc84edab75bdce6e12ee38742eb2c45a40aafc1899608fb9984e40f`.
This is four additional closures, **not achievement of below 50** and not
USB-pair completion, Kelvin qualification or fabrication release. The earlier
received chain was 76 -> 67 -> 60 -> 57 -> 55; these retained additions bring
the native open count to 51 without accepting the raw router's lower count.

The native-context backend's all-open inventory contains 139 new items and
reports 35 opens. It remains unadmitted: alternate supply conductors and
measurement/current paths cannot be projected as default-width ordinary
routes. Only source-plus-additions subsets that pass independent saved-board
receiving are published. A subsequent dedicated USB continuation from the
51-open parent exhausts its coupled search budget with zero generated items
and no source changes. It is not recorded as progress or a no-path proof.

### Generic causal repairs

`cec_route_proposal_guard.RouteProposalGuard` supplies a plan-local native
material/craft/field preflight for exact negotiated closure and displaced
branch restoration in `cec_certificate_repair`. It subtracts retained
collinear material, checks the exact material that will actually be emitted,
and refuses incomplete/expired craft or field evidence. New barrel proposals
receive actual private ground-refill field assessment. The route builder must
construct a fresh guard after mutation, not reuse a stale SWIG/spatial
snapshot. Fallback negotiated last-mile calls also explicitly enable their
existing field guard, and multilayer maze search receives only the declared
signal-layer authority. These are bounded operators, not a board/refdes or
coordinate recipe and not a claim that the entire pipeline is centralized.

The trigger was a negotiated 54-open proposal that preserved native terminal
partitions and added no native DRC faults, but added three interference
blockers and a retained-copper backtrack. It is rejected by the independent
screen. Replaying the same bounded negotiated menu with the new preflight
produces no candidate: refusing that invalid shortcut is a correctness gain,
not an open closure or a routing speedup. Ordinary conductor retirement still
needs its own complete receiving contract; no retired-trace candidate is
admitted in this slice.

`cec_fr._via_spot_clear` no longer treats a caller's `contained_layers` hint
as permission to skip foreign-copper checks. A native same-net SMD land may
have been moved or may carry inherited geometry debt; pad containment alone
does not establish clearance. Every enabled copper layer now receives the
same exact collision probe in both cached and uncached paths. Process
dimensions and pad/hole qualification remain separate requirements. Clean
qualified contained seats remain usable, and source copper is never changed
by the check.

A private fixed-anchor capacitor rotation demonstrates the failure: its
provisional 50-open export shorts the moved ground land/barrel to retained
GPIO copper and overlaps the MCU courtyard. Its initial private helper also
failed to bind three compact-via factory-rule constraints; return-topology
ownership alone is not process permission. The export is rejected. With the
stricter layer check, all three bounded quarter-turn attempts refuse before
generating any via. There is no production fixed-signal capacitor-rotation
actuator or receiving exemption added here.

The final focused regression group passes **502 tests and 12 subtests in
7.91 seconds**. It includes rotated/renamed, front/back, cached/uncached native
fixtures, real ground-return emission, negotiated proposal gates, restoration,
material reuse, field refill, compact process returns and last-mile routing.
This is not full repository CI; the existing SWIG warning remains. Cross-board
replay is in `build/atx51-preflight-via-controls-20261004-a/receiving.json`:
the archived PCIe2 fab-review control and Hub control retain exact native
copper, zero opens and zero scored DRC, with their existing qualification
scope/debt unchanged. The replay does not prove negotiated routing convergence
on a board that has no outstanding opens.

The next work is bounded local pin/corridor reconstruction with complete
restoration receiving, and load-backed local power-pin escapes. The native
F.Cu close-ups in `build/atx51-native-open-spots-20261004-a/` show actual
retained copper boxing in the remaining ground/reference exits. They are
diagnostic native views, not a proof that no placement or route can work.
More identical whole-board waves, weakened clearances, moved power buses or
count-only admission are not substitutes for those missing actuators.

The final code-bound 55 -> 51 recheck is
`build/atx51-preflight-via-receiving-20261004-a/receiving.json`: accepted private
receiving, zero new native/field/full-registry failures, 560 unchanged raw
native findings, 5 scored DRC, full registry 27 PASS / 11 N/A / 9 FAIL /
3 DECLARED, and clipped evidence still 4 PASS / 12 UNKNOWN of 16 legs.
Final dashboard ID:
`pass-atx51-preflight-via-review-20261004-a-atx-24pin-rev3-6eb38f3da5`.
`build/atx51-preflight-via-review-20261004-a/live-dashboard-receiving.json`
verifies all eight live PNG/SVG bodies against the exact publication hashes.
It remains visibly BLOCKED / NOT FAB SIGNOFF. Repeated publication of the
same retained geometry is not counted as another board improvement.

## October 4: aligned four-channel sense-row placement draft, no outline growth

The requested 12 V sense stage now has a checked private fourth seat to the
left of the existing 5VSB / 5 V / 3V3 row. The immutable routed parent is
`build/atx51-local-PI-cleanup-composed-20261004-a/board.kicad_pcb`, SHA256
`1c792635362991371bea0e6b9f5c86d67aa0959f5864003d75c1d4c0dca92192`.
It remains the 51-open control; this placement study is not another reduction
in its open count. The parent contains the earlier bounded C612V1 / C63V31
local PI cleanup, not a substituted old schematic or board family.

`scripts/cec_cell_row.py` derives row pitch and internal core geometry from
declared source roles. The ATX-specific membership and two explicitly
superseded reservation UUIDs live in
`beta/atx-24pin-rev3/placement-intents/four-rail-sense-row.json`, not in the
solver. Native selected-device ownership carries the bypass followers with
their owners. Part values, rail-specific nets, address wiring, pad definitions
and board faces are not copied from the neighboring channels. Renamed and
rotated synthetic fixtures exercise the same source-derived operation.

The first perfectly aligned 12 V seat passes 2-D placement but fails the
independent dead-bug stack check beneath Hub C37. Two older, FP-only,
provisional rectangles also over-reserve space relative to the current
hash-pinned capacitor body and full native vent rules. An explicit private
reservation transition replaces only those two outlines with their existing
stronger all-four-exclusions vent-guard outlines. This requires a passing
source assembly, exact policy/contract/pair/peer hashes, uniquely matched
current projected vents, containment inside the old reservations and exact
preservation of all other material. It cannot retire a copper exclusion,
delete by zone name, change a component height or lower a vent/tolerance
bound. The current vent guards themselves remain exact. Design allocations
and first-article qualification limitations remain in force.

The contact-derived cooperative fit slides all four cells and twelve owned
bypasses **2.044981 mm to the right**, without changing their 12 mm pitch or
row height. Only two native-conflict-derived unowned small supports need
additional translations: C14 0.644982 mm and D_USB1 0.559982 mm. The solver
contains neither of those refdes nor a coordinate recipe. It refuses to
independently pack a selected owner/bypass support cell, preserving complete
cell ownership. One generic 1-D contact-menu defect was also fixed: blocked
or orthogonally irrelevant obstacle events no longer consume the shortlist
before the nearest actually legal contact.

The final draft is
`build/atx-four-rail-row-placement-draft-20261004-f/board.kicad_pcb`, SHA256
`e048d5c8a098dd3cb4623dc3d15f8303435f710d5c2fe431077d56a0f0da94ed`.
Its exact-source receiving report `placement-draft.json` records **zero native
placement faults, zero native no-footprint-rule hits, 373 passing paired
assembly checks**, verified mating contacts/hardware and unchanged vent
clearance 4.3–6.5 mm against the existing 3 mm minimum. All component
definitions and unrelated saved native UUID nodes are exact, including the
outline, connectors, tracks/vias and power/ground zone fills. This is a
placement improvement within the existing outline, not an outline-size
reduction or routed-board admission.

Obsolete incident routing is deliberately exposed, not silently accepted.
After moving the row, a retained ground branch overlaps the new I2C SCL land;
native `LoadBoard` propagates that net onto three old ground tracks and one
via in memory. The strict production field-snapshot writer catches and still
refuses this. The separate placement-only writer preserves the authored raw
file identities, records every load-only delta and grants **no routing or
release authority**. Its exact saved-node check confirms the raw retained
ground objects were not renamed. All moved cells require incident
copper reconstruction, fresh immediate ground returns, qualified high-current
shunt connections, and ordinary full receiving before any promotion. Frozen
power, placement or pair receipts from the routed parent are not copied or
rebound. The accepted 51-open parent and dashboard winner remain unchanged.

Validation passes **726 focused tests in 170.01 seconds**, including the
117-test row/stack/packing subset, with the existing SWIG deprecation warning.
This is bounded focused coverage, not whole-repository CI. The new polygon
transition test also exposed a SWIG pointer-lifetime fault in an initial
`SetOutline` implementation; copying into the existing owned native polygon
fixes it, including rollback. No crashing version was applied to the parent.
`git diff --check` passes. Fresh code-bound read-only cross-board replay in
`build/cell-row-routing-replay-controls-20261004-b/receiving.json` retains
PCIe2 and Hub at zero opens / zero scored routing DRC, exact copper and their
unchanged qualification debt. It is not a claim that all full-registry gates
pass or that this new ATX placement is fab ready.

`placement.png` and `sense-row-review.png` in the final draft directory are
native F.Fab/F.CrtYd/Edge.Cuts placement-only views; old routing is not shown.
The compact review crop clearly states that status. The full native plot is
retained beside it. No browser or board-view tab was opened by this study.

## October 4: generic row-local reconstruction and retained-power preflight

The approved aligned placement now enters a real, bounded local-copper
reconstruction stage. This is **not a routed replacement or fab admission**.
The retained 51-open / 5-scored-DRC parent above remains byte-for-byte unchanged.
No dashboard winner, schematic, component definition, outline, power budget,
fabrication rule or existing qualification gate was replaced by this slice.

Two independent source-derived defects were exposed. The original row fitter
measured courtyards and the dead-bug stack, but did not screen the new lands
against retained power tracks and barrels. Also, a short route that was safe
inside a source cell could cross foreign copper when rigidly moved into its
new seat. Mechanical placement PASS is not either of those copper proofs.

`scripts/cec_cell_copper_preflight.py` checks exact retained conductor UUIDs
using native pad/track/arc/via effective shapes on every enabled copper layer
and the actual minimum/netclass clearance. Same-net contact is not a current
rating. Missing identity, unknown scope and exhausted budgets refuse. Its
bounded translation search restores source poses exactly and supports an
independent mechanical oracle; a failed finite search cannot establish that
the board needs to grow. The trial domain did not produce a copper-clear,
mechanically passing replacement for this row, so no outline growth or
clearance waiver was used.

`scripts/cec_cell_row_rebuild.py` imports **only independently verified poses**
from the saved approved draft. All electrical/physical source material comes
from the immutable routed parent, never the draft loader's propagated net
labels. Source native pad incidence and complete short-cell topology derive
the exact small-edge recompile scope. Locked small local edges require an
explicit opt-in; grouped edges, protected power/pair nets, wide trunks,
unowned interior taps, arcs and barrels cannot become deletions by that opt-in.
Single-source-land kernels require sole native pad ownership and exact
endpoint boundaries. External pad-leg span uses the native board diagonal
or an explicit bounded policy, not the separate 8 mm internal-chain limit.
Every original terminal/surviving-junction partition and external cut remains
a mandatory restoration obligation, not a successful route merely because an
old edge was retired.

Before carrying an owned internal chain, the destination checker tests it
against foreign pads, retained tracks/barrels/arcs, actual filled zones and
native track keepouts. If any edge is blocked, the complete source-owned
chain goes to reconstruction instead of carrying half a colliding route.
This check is deterministic and budgeted. A negative fixture exposed a KiCad
10 SWIG trap: `PCB_TRACK(source_track)` is a parent-taking constructor, not
a geometric copy. It produced an empty unnetted diagnostic track and missed
a crossing. Explicit native prototype construction fixes that, and blocker
reports retain original source identities rather than random prototype UUIDs.

Receiving rechecks both the saved draft and resulting construction placement,
native no-footprint reservations and paired stack under the **original source
assembly policy**. Its contract/pair/peer dependencies are hash-bound; losing
the policy in a draft cannot turn the stack check into N/A. The reconstruction
receipt retains implementation-file hashes and complete source/draft saved
families. No old frozen power/placement/pair receipts or skeletons are copied
or rebound; only the project/rule companions travel to the private child.
The strict saved-copper writer remains unchanged.

The pipeline-facing row CLI now always emits retained-power preflight and a
specific blocked stage. `--reconstruct-local-copper` creates a separate
unadmitted child only after placement receiving, and
`--allow-owned-locked-local-recompile` requires that explicit stage. The
standalone rebuild CLI consumes an existing approved hash-bound draft. Neither
entry point publishes a board or starts ordinary routing on an unsafe prefix.

The full placement-plus-reconstruction CLI was exercised in
`build/atx-four-rail-row-integrated-recompile-20261004-f/`. The final
implementation-bound reconstruction is
`build/atx-four-rail-row-final-local-recompile-20261004-g/board.kicad_pcb`, SHA256
`ed212a582cd650917b9511654c5666472ede08f0b79076a15801e3431ced77e6`.
It safely carries 4 internal tracks and retires 74 exact owned obsolete local
edges. All unrelated native UUID nodes, all vias and wide power copper remain
exact. Saved copper identity now passes strictly; there is no relabeling to
silence a short. Both draft and constructed placement have zero placement/
reservation failures and **373 passing paired assembly checks**.

| Artifact | Native opens | Scored routing DRC | Raw short findings |
| --- | ---: | ---: | ---: |
| Retained routed control | 51 | 5 | 0 |
| Approved placement-only draft | 132 | 276 | 67 |
| Unadmitted local reconstruction | 135 | 223 | 44 |

These figures are not a claimed routing improvement over the retained
control. The construction also has 86 mask-bridge, 37 clearance, 17 hole,
41 dangling-track and 2 dangling-via findings, alongside inherited cosmetic/
library findings, for 779 raw findings total. No track-crossing finding remains;
the naive earlier carry trial had introduced five. **13 native land-to-retained
power-track/barrel contacts still block the new row**, and 124 recorded source
incident boundaries remain restoration obligations. Exact IDs, nets, layers
and overlaps are in `cell-row-rebuild.json`; independent measurements are in
`native-drc.json` and `native-metrics.json`. The latter does not grant admission.

The next required stage is a source-owned **power-terminal/landing recompile**
with fresh rated-current and Kelvin/copper-cut receiving, followed by local
bypass/ground returns and signal reconstruction. Ordinary thin traces cannot
replace the configured force-current paths, and more ordinary routing waves
cannot cure pads seated over retained power landings. This slice intentionally
stops before such a wave; it does not move or shrink a current field as a
cosmetic fix, invent via capacity, or transfer the old frozen authority.

Final focused validation: **469 tests pass in 8.18 seconds**, including 81
row/rebuild/preflight tests and existing packing, assembly, preservation,
ordinary/additive receiving, POFV, local power replay and decoupler coverage.
Python compilation and tracked/untracked whitespace checks pass. This is
focused coverage, not whole-repository CI; the known KiCad SWIG deprecation
warning remains.

Current read-only routing/full-registry controls are refreshed in
`build/cell-row-final-routing-replay-controls-20261004-e/receiving.json`.
PCIe2 and Hub retain **0 opens / 0 scored routing DRC**, exact native copper,
no generated route material and unchanged qualification debt: PCIe2 32 PASS /
12 N/A / 3 FAIL / 3 DECLARED; Hub 30 PASS / 17 N/A / 3 DECLARED plus the known
122 contour findings. They are not newly qualified by this slice. Separate
native local-cell replay in
`build/cell-row-final-native-recompile-replay-controls-20261004-c/receiving.json`
executes no-op and 0.05 mm bypass translations on PCIe2, Hub and ATX51, preserving
every source native conductor/terminal partition and all copper, introducing
no new retained-power contacts, and restoring source native poses exactly.
All file controls remain unchanged. No board/dashboard tabs were opened.

## 2026-10-04: native sense coverage, auxiliary straps and bounded manual placement

This slice retains the routed ATX parent rather than promoting a tidy but
electrically regressed row. The independently received, final-code private
child is `build/atx51-precision-sense-coverage-current-20261004-p/board.kicad_pcb`,
SHA256 `1d3608e1f1f8f50704be1296609824d37def5dada7c4abbc71eb7086d38c9c2c`.
Its parent is `build/atx51-local-PI-cleanup-composed-20261004-a/board.kicad_pcb`,
SHA256 `1c792635362991371bea0e6b9f5c86d67aa0959f5864003d75c1d4c0dca92192`.
These are partial routing artifacts, not final placements or fab candidates.

| Saved native measure | Parent | Private child |
| --- | ---: | ---: |
| Unconnected items | 51 | 48 |
| Scored routing DRC | 5 | 5 |
| All raw DRC findings | 560 | 560 |
| Newly introduced native DRC findings | — | 0 |

The improvement is exactly three locked, guarded surface measurement straps;
all original footprint poses, force conductors and unrelated copper remain
unchanged. `completion.json` records strict saved-copper/additive receiving,
unchanged source family and unchanged implementation epoch. Its
`eligible_for_full_receiving` flag means only that the improved child can be
fully checked. It does **not** grant routing, current, Kelvin or release
authority, and copied historical sidecars are not rebound to the new board.

### Generic changes and what the actual run demonstrated

- `cec_sense_auxiliary` constructs local same-net package connections only
  for declared INA238/INA228 VBUS/IN− roles, with exact unique live pin/net
  identities, one surface SMD face, short 0/45/90 paths, native foreign-copper,
  edge/keepout/future-power guards, and native post-contact proof. It never
  changes schematic nets or grants force-current capacity. The part roles
  come from [TI INA238 pin functions](https://www.ti.com/lit/ds/symlink/ina238.pdf)
  and [TI INA228 pin functions](https://www.ti.com/lit/ds/symlink/ina228.pdf).
  The actual precision entry point closes three package straps; the fourth
  device's existing strap is covered and receives no duplicate copper.
- Kelvin coverage no longer equates a locked input-side stub with a completed
  shunt-to-input leg. A private native same-net contact graph must reach the
  matching shunt. A complete unlocked source leg also counts as covered.
  Unknown fill/identity/contact remains a named refusal; native contact is
  deliberately not Kelvin isolation qualification.
- All source-contact demands are measured in a separate bounded read-only
  phase **before** route construction. The first implementation's interleaved
  loop let expensive early path-refusal diagnostics consume the 10-second
  contact deadline and starve later coverage checks. The final actual ATX
  run resolves all 16 typed input contacts: 6 connected, 10 disconnected,
  **zero deadline-unknown contacts**. It emits zero duplicate Kelvin taps;
  the former entry point had emitted five redundant taps without closing an
  open. A synthetic virtual-clock regression exercises this exact starvation
  failure without sleeps or a board-specific case.
- Precision geometry locking is no longer whole-net routing ownership.
  Complete native locked-subgraph ownership is required before excluding a
  generated net from subsequent routing. The three local straps are locked,
  but their mixed force/sense nets remain explicitly `partial_locked_nets`.
  Their disconnected force and typed-sense consumers are not silently frozen
  out of later stages. This does not make a force net eligible for ordinary
  thin routing; the current and typed-terminal authorities are unchanged.
- Fully contained off-centre POFV seats are now proposed from native pad
  geometry when the pad-centre barrel is obstructed. Each proposal still
  needs the existing factory POFV profile, actual land containment, all-layer
  copper/drill/edge and surface-stub clearance, caller limits and final
  transaction receiving. Equal-length bridge candidates prefer shorter
  surface escapes, not gratuitously long escapes to shorten only the inner
  span. Native rotated/back-side synthetic fixtures exercise the construction
  and transaction refusal. This capability has **not** yet closed an extra
  ATX open: the R10 endpoint's finite inset domain remains blocked.
- Cell packing accepts bounded explicit supplemental sites and an independent
  read-only retained-copper oracle after mechanical legality. Only a literal
  Boolean acceptance is permitted. These are reusable proposal hooks, not
  permission to retire power copper or declare a finite search globally
  impossible.

### Manual placement and route probes: rejected rather than hidden

A minimum-motion row trial kept all three existing rail cells and their
power ports fixed and moved only seven members of the new 12 V cell. It was
mechanically clear, but its strict local reconstruction produced **74 opens /
45 scored DRC / 10 shorts**, versus 135/223/44 for the previous whole-row
reconstruction. That is an improvement *between rejected row trials*, not
an improvement over the 51-open routed parent. The retained obstacles include
live source-owned power/signal consumer branches; deleting them to make a
placement fit would lose source terminal partitions. Neither row child is
promoted. No board growth or clearance waiver was used.

Explicit small passive-pose proposals were also received against exact
source identities, all original conductor/terminal partitions and unchanged
unrelated material. The least disruptive trial remained **48 opens / 5 scored
DRC**, but introduced five silk-overlap findings and closed nothing. A broader
trial regressed to 49 opens / 12 scored DRC and lost source partitions.
Those are rejected placement proposals, not hidden automatic repairs.

Separate supply, local-ground, pair, strap and control-net probes did not
improve the 48-open child. Native endpoint diagnostics retain the actual
layer and reason: e.g. In2.Cu foreign copper excludes candidate barrels,
nearby pad/drill spacing excludes others, and surface escapes remain blocked.
Some long control-net trials had skipped the maze because of a 30 mm search
threshold. Explicit 100 mm maze eligibility and a 10-second per-net budget
were tested on DETECT, DET3V3 and PSON_GATE; none closed an additional open.
These bounded failures are not proof of global unroutability or need for a
larger outline. The requested next placement cleanup needs source-owned
landing/consumer-branch reconstruction, not another identical ordinary wave.

### Full gates and cross-board regression

Fresh complete evidence is in
`build/atx48-sense-coverage-qualification-20261004-q/` and its matching parent
replay. All 16 same-net sense contacts are assessed: 6 pass and 10 fail.
Inner-departure coverage remains 6 checked / 10 unknown; clipped isolation
remains **4 pass / 12 unknown**. Equal scoped clipped evidence is non-regression
of that incomplete evidence, never qualification of the other 12 legs.

The full 50-row registry changes from **27 PASS / 11 N/A / 9 FAIL / 3 DECLARED**
to **26 PASS / 11 N/A / 10 FAIL / 3 DECLARED**. The additional flag is the legacy
no-connector-tap checker: a previously bare, open input was skipped, whereas
the new package strap is now a visible tree without a shunt origin. The
native contact audit already reports the original missing shunt contacts.
The new flag is preserved, not waived or described as a qualified Kelvin
route. Source force/placement authority is also still stale or unavailable;
power completeness, physical USB/CAN, current-path and pour qualification
remain blocked. Ratline witness changes are not newly proved power failures;
all original saved copper is independently preserved. The child is not
fully admitted and is not release-ready.

Final control replay is
`build/sense-aux-coverage-final-controls-20261004-p/receiving.json`.
PCIe2 and Hub retain **0 opens / 0 scored routing DRC**, exact native copper
and zero generated additions with the new Kelvin/auxiliary stage enabled.
Their qualification states remain PCIe2 32 PASS / 12 N/A / 3 FAIL / 3 DECLARED,
Hub 30 PASS / 17 N/A / 3 DECLARED, including the Hub's existing 122 contour
findings. These are regression controls, not newly fabricated or qualified
boards.

Final focused validation: **766 tests pass in 14.27 seconds**, spanning the
new capabilities plus existing row/rebuild/preflight, packing, assembly,
exact native preservation, ordinary/additive receiving, decoupling, critical
pair and current-supply receiving tests. Python compilation and whitespace
checks are separate finishing checks. No whole-repository CI claim is made;
the KiCad SWIG deprecation warning remains. No dashboard/browser tabs were
opened, no source control board was modified, and no source current budget,
via rating, factory rule or release gate was reduced.

## 2026-10-04: blocked-access escalation, 48 to 46 opens, and remaining limits

This slice retained two additional ATX connections, not a fab-ready board.
The primary hold-up is a missing automatic escalation from an obstructed
terminal into source-owned local-cell/consumer-branch reconstruction. Ordinary
waves repeatedly search a fixed geometry that cannot supply the proposed
surface escape or all-layer barrel. The new bounded tools below are reusable,
but they are not yet automatically selected by every wave frontier.

### Exact retained lineage and independent receiving

1. The 48-open parent is
   `build/atx51-precision-sense-coverage-current-20261004-p/board.kicad_pcb`,
   SHA-256 `1d3608e1f1f8f50704be1296609824d37def5dada7c4abbc71eb7086d38c9c2c`.
2. Ordinary future-land preclear followed by a stationary-land support pivot
   retained **47 opens / 5 scored DRC / 560 raw DRC** at
   `build/atx48-automatic-preclear-pivot-current-final-20261004-z/candidate/board.kicad_pcb`,
   SHA-256 `60f5f0380894e63656116706cacfd224afe79832d4b9e5ebce66e6e7029dc418`.
   The exact source-owned ordinary I2C_SDA segment was retired and its cut
   boundaries restored before applying the R10/R60 support-pose recipe. The
   IO8_STRAP join adds three tracks and two process-qualified POFV vias.
3. A source-derived isolated RC-return pivot retained **46 opens / 5 scored
   DRC / 560 raw DRC** at
   `build/atx47-rc-return-retained-final-20261004-ac/trial-0/board.kicad_pcb`,
   SHA-256 `3f21294a33e1c3a38e9023b69d2e8bd1adc9169da27f2939ccbaacd1b5152743`.
   C61 rotates 180 degrees about its exact stationary ordinary GPIO0 land.
   Its formerly isolated ground land gains a 1.055 mm dogbone, one track and
   one 0.35 mm diameter / 0.25 mm drill qualified POFV via. C61 is an RC
   support capacitor, not one of the assigned device decouplers; this separate
   receiving contract cannot authorize moving selected bypass capacitors.

Final read-only current-code chain refreshes are
`build/native-access-final-preclear-receiving-20261004-aj.json`,
`build/native-access-final-support-receiving-20261004-aj.json` and
`build/native-access-final-rc-receiving-20261004-aj.json`. All are complete and
accepted, with unchanged source/candidate families and code epochs. The
receivers preserve all original conductor/terminal partitions and unrelated
material, independently replay the exact native source transforms and new
copper, and check native DRC, physical placement and field non-regression.
Process membership and the exact saved via-rule family are replayed, not
rebound from another board.

The native DRC reporter can change which inherited silk overlaps it lists.
Only exact unchanged authored items with positively established native
collision are classified as inherited. This is not a waiver or a claim that
the raw DRC reporter is exhaustive. The retained raw 560 findings are not
being presented as a clean manufacturing report.

### Generic capabilities, and what is still recipe-driven

- `cec_native_rule_areas.py` supplies shared native track-permission checks
  for board and footprint rule areas, including full trace capsules, holes,
  concavities and actual layers. `cec_fr.py` applies these in both cached and
  one-shot routing checks. A track-permission boundary does not acquire an
  extra foreign-net clearance; actual copper spacing is unchanged.
- `cec_future_pose_clearance.py` reserves detached native future lands only
  while restoring exact eligible ordinary-track cut boundaries. It excludes
  power, Kelvin/sense, pairs, vias and protected material. Explicit locked
  retirement permission must match the actual bounded obstruction inventory.
  The original component poses remain fixed through this received prefix;
  temporary reservations are removed before saving.
- `cec_support_pivot.py` and `cec_support_pivot_receiving.py` construct and
  independently receive bounded stationary-land two-SMD support pivots. The
  constructor divides its ten-second aggregate routing lease among the actual
  affected nets. The ATX R10/R60 pose recipe is hash-bound data in
  `build/atx-control-fixed-land-pivot-20261004-i.json`, not a reference or
  coordinate special case in the algorithms. However, the full wave planner
  did not automatically derive that two-component recipe; this is a genuine
  remaining autonomy gap.
- `cec_rc_return_pivot.py` automatically derives a finite source-based menu
  of eligible isolated RC capacitors and quarter-turn pivots. The separate
  receiver requires an exact stationary ordinary land, source-isolated ground,
  bounded immediate ground additions, original partitions and the qualified
  saved process. It does not widen the bypass, current or Kelvin contracts.

These tools do not transfer placement, routing, assembly or release authority
to a candidate merely because a local connection was accepted.

### Native evidence of the remaining pin-access cage

`build/atx46-native-sensor-escape-layers-20261004-t.png` and its matching JSON
show the actual native material on all six copper layers. U65V1 ground pin 5
is enclosed on the front by its adjacent supply and measurement lands and
nearby measurement/sense routes. A 6.535523 mm wide rear SENSE3V3_HI bus
excludes the proposed through-barrel under that area. U65VSB1 has a similar
surface/inner-layer obstruction. Adding layers or allowing an unchecked
barrel does not solve this local geometry. The priority force bus remains
fixed; local cells and owned measurement/consumer leaves need reconstruction.

The inspection helper initially omitted a weakly-simple fractured ground-fill
contour rejected by its polygon conversion. It was corrected to rasterize
literal native winding and holes. The planes were not empty. This ignored
inspection helper is not a production dashboard repair or a field certificate;
the strict clipped-copper isolation path still refuses unsupported material.

The typed Kelvin branch constructor also refuses reconstruction while exact
source pour-first/frozen-geometry authority is missing and clipped isolation
is unknown. Removing or rebinding these states to manufacture a pass is not
permitted. Their repair is part of the next ownership/authority slice.

### Correct power diagnostics without changing approved load budgets

`cec_power_connectivity.py` inventories stable native pad-UUID components
using a private native connectivity graph, without renetting or saving the
board. It includes every passive/header pad on a selected supply domain, even
when the rail has a hierarchical non-voltage name. IC roles come from checked
manufacturer/package maps, actual native electrical types or the existing
declared supply contract. Absence from a capacitor-assignment catalog is not
evidence that a pin is a signal. Unresolved roles fail closed.

`cec_device_power_roles.py` is deliberately separate from capacitor requirements.
The [TPS2121 datasheet](https://www.ti.com/lit/ds/symlink/tps2121.pdf) identifies
OUT pins 1 and 8. Both now enter the power inventory and must share their
specified output domain; this adds no redundant output-capacitor requirement.
The retained ATX, PCIe2 and Hub sources already connect their two OUT pads
to the same net. The omission was in the checker inventory, not proof of an
omitted schematic connection.

Additional reviewed package maps follow primary pin tables in the
[INA238](https://www.ti.com/lit/ds/symlink/ina238.pdf),
[LP5907](https://www.ti.com/lit/ds/symlink/lp5907.pdf),
[TLV62569](https://www.ti.com/lit/ds/symlink/tlv62569.pdf) and
[TLV755P](https://www.ti.com/lit/ds/symlink/tlv755p.pdf) datasheets. These are
bounded package maps, not a claim of a universal manufacturer pin library.
Control/address and measurement inputs are not mislabeled as supply pins.
Missing, unnetted or grounded known supplies, missing known grounds and
inconsistent common output domains are explicitly checked.

The final ATX report has 43 affected IC/net groups across fragmented supply
and ground domains. This does **not** mean 43 ICs have isolated supply lands.
Only four truly one-terminal islands, grouped into three IC targets, become
local `power_escape` directives: U5 supply pin 2, U65V1 supply pin 6 and ground
pin 5, and U65VSB1 ground pin 5. Larger disconnected domains become typed
`power_net_partition` work. An empty local target set can no longer fall back
to all ICs in `cec_loop.py`. Six actual IC supply/ground domains remain
fragmented; passive/header-only distribution is also retained in the inventory.
No power connectivity diagnostic establishes energization, ampacity or release.

No approved current, margin, copper thickness, barrel rating or factory rule
was changed. The final legacy current-model report still includes stale
aggregate width inference (including 78.298 mm); this is unresolved authority
debt, not a new instruction to apply aggregate load to each local branch.

### Bounded search measurements: faster diagnostics, not further closure

The ordinary post-return probe
`build/atx46-bounded-ordinary-after-return-20261004-x/trial.json` retained no
additional join: 15 refusals and three named per-net timeouts, 9.358 seconds.

The approved-current distribution probe before cache repair tried 199
alternatives, closed none and retained 46 opens. Its report was 11,321,865
bytes because full launch inventories were repeated on each attempt. The
same-source bounded replay after repair tried 212 alternatives, closed none
and retained 46 opens; its report was 1,093,900 bytes. Evidence is in
`build/atx46-complete-approved-distribution-20261004-x/trial.json` and
`build/atx46-cached-approved-distribution-20261004-y/trial.json`.

`cec_distributed_supply.py` now shares a native graph per net in one unchanged
epoch, invalidates all search graphs after every retained join, and records
append-only exact-epoch launch inventories rather than repeating them. The
replay used four graph builds and 208 cache hits. The ten-second search lease
is unchanged; total process/save times were 11.10 and 11.21 seconds. This is
about 6.5% more alternatives and 90.3% less report storage in this one paired
measurement, not a cross-board performance benchmark or a closure speedup.
Physical/current/field refusals remain enforced and are not global no-path
proofs. Repeating these unchanged waves is not the next closure strategy.

### Final qualification, regression controls and next action

`build/atx46-manufacturer-power-closure-final-qualification-20261004-ai/`
contains fresh native DRC, all 50 checks and clipped native sense evidence.
The result is **46 opens / 5 scored DRC / 560 raw DRC** and
**26 PASS / 11 N/A / 10 FAIL / 3 DECLARED**. All 16 typed sense inputs are
assessed: same-net contact is 6 PASS / 10 FAIL; inner departure is
6 PASS / 10 UNKNOWN; clipped isolation is 4 PASS / 12 UNKNOWN. Missing frozen
power-pour authority, current-path qualification, physical USB/CAN and these
sense failures remain explicit blockers. There is no fab or release claim.

Current-code control replay is
`build/native-access-manufacturer-power-final-controls-20261004-ai/receiving.json`.
The immutable PCIe2 v103 fab-review control and retained private Hub control
both keep **0 opens / 0 scored routing DRC**, exact native copper and source
families, and zero generated additions. Their full-registry states remain
PCIe2 32 PASS / 12 N/A / 3 FAIL / 3 DECLARED and
Hub 30 PASS / 17 N/A / 3 DECLARED. The Hub retains its existing 122 contour
findings. These are unchanged regression controls, not new Hub closure or
new manufacturing qualification.

Final focused validation: **406 tests pass in 50.37 seconds** across 16
native-rule, pose/RC receiving, power-role/connectivity, THT/POFV, supply,
constraint and dispatch modules. The endpoint synthetic fixture was corrected
from overlapping 0.8 mm lands at 0.75 mm pitch to legal 1.0 mm pitch; no
production clearance guard was weakened. Python compilation, scoped tracked
whitespace checks and new-source trailing-whitespace checks also passed.
This is not whole-repository CI. The KiCad SWIG deprecation warning remains.

The next bounded slice is source-owned local cell/measurement-leaf rebuilding
with the priority bus fixed, independent terminal-partition and current/Kelvin
receiving, and refreshed exact power/placement authority. After that, complete
the physical USB/CAN work and rerun qualification. Automatic frontier selection
and source-derived proposal generation need to connect these tools into the
normal loop; more blind waves alone will not provide that missing behavior.
No control/BETA board was replaced, no commit or push was made, and no
dashboard/browser tab was opened during this slice.

## 2026-10-05: package-role audit, actual body geometry and source-contact repair

The retained routing gain for this continuation is still **48 to 46 opens**.
The subsequent trials described below do not add an accepted connection.
The current private ATX source is now
`build/atx46-native-body-restored-20261004-bb/candidate/board.kicad_pcb`, SHA-256
`1ebf29b0cff4f7b012bfa26b9947dc7767fa935de16f5f8b50d31b8f22291757`.
It has the restored full physical MCU footprint, not the earlier cropped
module-body source. Its native copper remains unchanged by that correction.
No BETA or archived control was promoted/replaced.

### Manufacturer roles and physical geometry are distinct authorities

The requested read-only component audit covered 77 fitted ICs and three
MOSFETs across seven main-board schematic roots. It did not establish an IC
pin-function wiring defect within that checked scope. Exact selected-package
contracts now distinguish INA181 DBV from DCK and INA240 D from PW; an MPN,
displayed family or footprint contradiction is refused instead of guessed.
The actual selected power/measurement roles feed connectivity, local access,
pair semantics, sense topology, force evidence and the constraints registry.

**Correction to the earlier log:** INA181 DBV pin 2 is the true GND pin;
pin 5 is REF. An explicitly grounded REF is a separate `ground_reference`
task, not a second manufacturer ground pin. DCK has a different pin map.
The [manufacturer pin-function table](https://www.ti.com/lit/ds/symlink/ina181.pdf)
is the basis; a power-like net name or proximity to a capacitor is not.
The TJA1051T/3 S control input likewise is not a chip-ground pin just because
the schematic ties it low. TLV755 DRV exposed ground is included in its
package contract. No new aggregate current or power-budget number was invented.

Selected IC-to-board parity was checked on the ATX retained source, immutable
PCIe2 control, private Hub control and current manifest EPS/PCIe3 boards.
The current 12VHPWR staging PCB requires normalization before exact PCB parity
can be claimed: its status remains **unknown**, not a substituted old board.

The six current Standard-main-board policies now explicitly opt out of the
unused RF antenna keepout as requested. This does not remove actual package
bodies, assembly courtyards or explicitly authored physical edge contracts.
The legacy numeric MCU courtyard crop and implicit RF-edge placement heuristic
were removed; the independent physical-body receiver requires the full native
vendored footprint. The restored ATX body passes physical receiving without
changing any copper, terminal pose, priority bus or board outline. The cropped
predecessor is retained only as a failing control, not used for new routing.

Native incident-track inspection now uses a private connectivity graph rather
than normalizing live-board nets through inherited shorts. The same rule
applies to the future-seat/reference-link constructor. This prevents a
diagnostic or planning operation from relabeling protected source copper.

### Exact source contact, not a broad same-net exemption

The measurement-leaf guard incorrectly reduced an existing retained T-junction
to a circular point aperture. Even a replay of the original native source
trace could fail `unowned_same_net_contact`: the actual orthogonal junction
has more contact area than that circle. This was a checker/search defect,
not proof that the source junction or all subsequent detours were impossible.

`cec_measurement_leaf.py` now binds the aperture to the immutable source's
last owned narrow edge. Only named retained TRACK/ZONE boundaries receive
that exact source contact region, with the existing numerical error reserve.
Unrelated same-net copper and new contact along a retained landing remain
forbidden. The independent receiver derives the aperture again from its
source; the worker cannot supply a wider landing exemption. Rotated same-width
and wide-boundary T-junctions, missing/tampered contact metadata and new
unowned overlap are covered by native synthetic tests. Actual U65V1 measurement
pins 3 and 4 now both pass exact-original-path replay. A private translated
cell can find one previously blocked path, but its other required path still
fails; that translated placement is **not admitted**.

### Source-derived reference preclear and bounded multilayer reconstruction

`cec_future_pose_clearance.py` now supports a source-selected, isolated,
explicitly grounded manufacturer REF terminal. Its destination must be the
assigned bypass return already connected to the package's true GND pin. It
reserves a full-class orthogonal local link; callers cannot invent its net,
endpoints, capacitor, package role or geometry. The new API and CLI independently
receive an ordinary-route prefix only. They do **not** emit that ground link
or claim it has closed a terminal.

The constructor first tries the face layer, then uses the existing native
guarded bridge/multilayer router on profile-authorized non-plane signal layers.
The complete track/via proposal must pass field and craft checks before native
emission. Ordinary via minima, exact through-barrel/hole clearance, legal
local POFV ownership, source terminal partitions and final native DRC remain
mandatory. Search stays within a ten-second lease; a refused attempt is not a
global no-path proof. Temporary permission polygons are removed on every exit.

An optional source-cut extension follows only exact degree-two ordinary track
joints, at most 16 additional edges and 10 mm of added source-route length.
It stops at pads, vias, branches, arcs, groups, wide/protected routes and
midsegment contacts. Locked extensions require their explicit source IDs;
this is not a spatial rip-up or a blanket unlock. A synthetic board with a
face-layer barrier reconnects through two legal vias and passes independent
saved-board receiving without live-source connectivity normalization.
Renamed and rotated manufacturer-qualified fixtures also revealed and fixed
a separate U-prefix dependency in bypass assignment: known device/package
requirements now survive an imported or renamed IC reference.

Actual ATX trials remained refused:

- `build/atx46-ground-reference-multilayer-preclear-20261005-m/probe.json`:
  zero legal via seats at both original I2C cut ends; 832 canonical seats were
  rejected by native copper, pad/hole and rule-area guards, not a timeout.
- `build/atx46-ground-reference-expanded-source-cut-20261005-q/probe.json`:
  the source-derived five-track cut reaches U10/U11 SDA pad anchors. Six legal
  via seats are found at one end, but none can escape the U11 endpoint under
  the actual retained copper/clearance contract. The constructor closes zero;
  the ordinary receiver refuses the incomplete reconstruction.
- The other isolated REF link intersects protected power/measurement material
  and is refused before retirement. No power bus, force landing or barrel is
  moved or made narrower to get a pass.

These outputs are **unadmitted probes**, not winners or new routing progress.
The next meaningful routing action is a source-derived neighboring-pin/route
access transaction at the inaccessible IC launch, with unchanged priority
buses and full independent replay. Repeating either unchanged cut is not a
new experiment. Normal-loop automatic frontier selection/placement recovery
still needs to consume these bounded operators; this slice does not claim a
fully autonomous start-to-finish closure pipeline.

### Current-code immutable controls

`build/native-source-junction-reference-final-controls-20261005-t/receiving.json`
replays the current code with exact board hashes and isolated native grading:

| Source | Native opens | Scored / raw DRC | Full registry | Physical geometry |
| --- | ---: | --- | --- | --- |
| PCIe2 v103 archive | 0 | 0 / 489 | 32 PASS, 12 N/A, 3 FAIL, 3 DECLARED | PASS |
| Private Hub control | 0 | 0 / 769 | 30 PASS, 17 N/A, 3 DECLARED | PASS |
| ATX full-body retained source | 46 | 5 / 560 | 26 PASS, 11 N/A, 10 FAIL, 3 DECLARED | PASS |

All source families, native copper and the bound production-code epoch remain
unchanged during this replay. The cropped ATX predecessor still fails physical
geometry as intended. The independent full-body repair receiver also passes.
Zero routing opens on the controls do not remove their existing qualification
debt; ATX is not fab-ready. No release, current, Kelvin or manufacturing gate
was weakened and no dashboard/browser tab was opened.

Focused source-reference/leaf/bypass/connectivity/decoupler validation before
the final API additions: **201 passed** in 24.50 seconds. Final reference-preclear
API and extension module: **54 passed** in 17.26 seconds. The KiCad SWIG
deprecation warning remains. Broader current-code regression results are
recorded separately below; these counts are not whole-repository CI.

Final broad validation for the current production-code epoch:
`build/source-reference-final-broad-regression-20261005-t.log` — **1,185 passed**,
one SWIG deprecation warning, 154.95 seconds, across 37 targeted native-geometry,
placement, routing, receiving, current/Kelvin, physical-body and constraint
modules. Production-source compilation and scoped tracked whitespace checks
also pass. This is a bounded regression group, not the entire repository CI.

The hand-reviewed all-six-layer view of the inaccessible U11 launch is
`build/atx46-inaccessible-I2C-launch-native-layers-20261005-u.png` and its JSON
sidecar. It is extracted from the exact full-body source above, has no native
geometry conversion errors, and verifies that the saved source remains
unchanged. It displays only actual saved copper; it is neither a FEM model nor
current, field, thermal or factory signoff. The source pin row, adjacent power
feed and inner/back copper must be considered together in the next access
transaction rather than assuming an unused layer automatically permits a
through barrel.

## 2026-10-05 — layer-fair orphan access and exact private proposal receipts

### Received private checkpoint: 46 to 45 opens

The automatic source-isolated support constructor now produces a real,
independently received ATX connection. The retained **private repair checkpoint**
is:

`build/atx45-source-isolated-received-checkpoint-20261005-aj/trial-0/candidate/board.kicad_pcb`

SHA-256:
`63f60284d42679c1a181acb27f91442549439661025e27302b7fad7f272b3848`.

Its immutable parent remains the full-body source
`build/atx46-native-body-restored-20261004-bb/candidate/board.kicad_pcb`, SHA-256
`1ebf29b0cff4f7b012bfa26b9947dc7767fa935de16f5f8b50d31b8f22291757`.
The cropped predecessor is not a routing seed.

This is not a BETA promotion, automatic routing admission or fab-ready board.
The private checkpoint is the source for the next bounded repair transaction;
the immutable 46-open parent and other controls are preserved.

The source-derived transaction re-seats a completely isolated ordinary
two-land resistor and connects `/THRESH_PWM`. The recipe happens to select R60
on this board, but the production selector contains no board/refdes/coordinate
exception. Both actual source lands must be isolated, including from foreign
copper; no connected source terminal, power, sense or differential-pair land
may move under this operator. Its exact pose is derived from native legal
barrel apertures and complete-owner occupancy, with four cardinal orientations
and a finite 6 mm movement envelope. Original priority buses, copper and
terminal partitions survive independent source-plus-pose-plus-additions replay.

Evidence:

- `build/atx45-source-isolated-received-checkpoint-20261005-aj/receiving.json`:
  the complete constructor/receiver passes, source and code stay unchanged.
  The construction slice takes 8.062 seconds and closes one connection with
  twelve track segments and two qualified local POFV signal vias.
- `build/atx45-isolated-checkpoint-full-review-20261005-ak/receiving.json` and
  `independent-receiving.json`: independent saved-board review passes; actual
  native opens decrease **46 to 45**, scored DRC remains **5**, raw DRC remains
  **560**, physical placement passes, and no new native DRC or field blockers
  are admitted.
- Full-registry status remains **26 PASS, 11 N/A, 10 FAIL, 3 DECLARED**. There
  are no new failing checks. Existing power/ground, pair, Kelvin and frozen
  power-authority failures remain open; ordinary connection receiving does
  not qualify them. No new current/load/thermal budget was invented here.

### Generic defects repaired

1. **Live connectivity normalization.** Last-mile component counting and
   closure now use a fresh private native graph. A planning/closure query may
   not relabel inherited foreign shorts or alter frozen source nets. The
   regression deliberately makes live `BuildConnectivity` fail and checks
   source net/geometry preservation through an actual closure.
2. **No automatic legal re-seat for a fully isolated ordinary support.**
   `cec_orphan_support_access.py` derives targets, cardinal poses and finite
   recipes from native source geometry. It delegates construction to the
   existing preclear/pivot router and always uses independent receiving.
   Whole-body occupancy and both lands are checked before expensive routing.
   The scoped mode does not broaden the anchor-preserving receiver's default
   authority or authorize connected/source-power moves.
3. **Layer starvation.** The bridge router previously spent its deep endpoint
   maze menu on one layer before considering another. It now tries canonical
   breadth on each authorized layer, then interleaves deep seat-pair ranks.
   The first working canonical path retains its previous geometry/order.
   Bounded misses remain misses, not proofs that no route exists.
4. **Micro-hop interference blindness.** Per-grid-hop guards could accept a
   sequence of short segments whose manufactured straight run violates the
   parallel-exposure rule. Single- and multilayer maze states now retain
   straight-run origin/width, check accumulated exposure and revalidate the
   collapsed native segments. Rotated and back-layer fixtures use actual
   authoritative field review rather than mocked connectivity.
5. **Late unshieldable adjacent-layer rejection.** Planar search now prunes
   conclusive same-layer parallel exposure and cross-layer interactions where
   the approved stack has no intermediate dedicated ground layer. It uses
   the existing authoritative parallel/crossing thresholds. A declared GND
   role is not a fabricated shielding receipt: actual filled-ground evidence
   is still required by final independent field review.
6. **The same positive proposal reviewed three times until timeout.** The
   `...stack-aware-20261005-ae` probe passed whole-field review twice, then
   lost the identical connection to the third review's deadline. The new
   `cec_proposal_receipt_memo.py` reuses only completed positive receipts for
   the exact normalized ordered geometry within one unchanged private plan.
   Context binds native material serialization, live rule floors, resolved
   contracts, original family companions and active fab profile. Mutations
   invalidate it; refusals/unknowns are never cached as success. The actual
   received rerun assesses that proposal once and records two exact hits.
   Saved-board/native/placement/full-registry receiving still runs separately.
7. **Partial native DRC lists mistaken for new unrelated silk defects.**
   The first improved board was correctly rejected pending proof of 98 newly
   enumerated `silk_over_copper` rows on unchanged source parts. The receiver
   now positively witnesses exact authored source pad/text identities and
   native collision. For mask findings its conservative witness requires
   source copper contact, mask exposure and unchanged nonnegative resolved
   expansion. Moved geometry, absent/negative/changed mask, mask-only near
   misses, unknown identities and non-silk fault types remain new/unknown.
   All inherited collisions remain manufacturing/legibility debt, not waived
   release checks. The source and child inventories are captured once for
   this comparison rather than rebuilt for every finding.

The common last-mile router consumes the graph, layer-fairness, interference
and exact-receipt fixes directly. The new source-isolated re-seat operator is
a bounded CLI/agent constructor; the regular wave scheduler does **not yet**
automatically dispatch it. Do not describe this as a fully autonomous generic
start-to-finish placer/router. Scheduler integration must preserve exact source
epochs, finite exploration/plateau behavior and independent receiving.

### Regression and visual evidence

`build/native-orphan-exact-receipt-final-controls-20261005-ai/receiving.json`
passes current-code replay on the immutable PCIe2, Hub, full-body ATX and
deliberately cropped ATX controls. Source families, native copper and the
production-code epoch stay unchanged. PCIe2 remains **0 opens / 0 scored DRC**,
Hub remains **0 / 0**, and their existing qualification status is unchanged.
The cropped ATX control still fails physical geometry; full-body receiving
still passes.

Current-code bounded regressions:

- `build/orphan-exact-receipt-final-broad-regression-20261005-al.log`:
  **844 passed**, 27 modules, 272.87 seconds.
- `build/orphan-exact-receipt-independent-gates-retest-20261005-ap.log`:
  **150 passed**, 5 independent receiving/current/Kelvin/stage modules,
  22.25 seconds.
- `build/orphan-exact-receipt-kelvin-import-regression-20261005-aq.log`:
  **16 passed**, the dependent Kelvin separation module, 0.62 seconds.

Total: **1,010 passed across 33 selected modules**, not whole-repository CI.
The KiCad SWIG deprecation warning remains. The first extra Kelvin run had
93 setup errors before its assertions: pytest interpreted a helper named
`setup` as an xunit hook and supplied a module instead of a board path. The
helper and its dependent import were renamed to `native_board_fixture`;
all of those native tests now actually execute and pass. No production gate
was weakened to repair the test harness.

The final suite includes renamed, rotated, back-side, source-short, locked,
grouped, protected-net, metadata, unsafe-mask, changed-material/rule/context
and deadline/unknown fixtures. Automatic source-derived construction plus
saved receiving is tested under the explicitly selected POFV process, not
with an implicit default-process via-in-pad exception.

`build/atx45-threshold-highlight-native-layers-20261005-ao.png` and its JSON
sidecar show the received connection in pink across all six actual saved
copper layers. The view has no geometry conversion errors and does not mutate
the checkpoint. This is visual inspection evidence, not current/thermal or
factory signoff. No dashboard/browser tab was opened.

### Next bounded closure work

The ordinary threshold connection is received; its other comparator-tree
branch remains open. The remaining higher-count mux/supply and high-current
islands require their declared rated/current construction and frozen authority,
not ordinary skinny last-mile traces. USB/CAN require complete paired route
and return-path receiving. Inaccessible IC launches require source-owned
neighbor/escape transactions rather than cutting priority buses or repeating
the same failed via menu. The new checkpoint must be used explicitly by hash
so that the next repair does not restart from the old 46-open source.

## 2026-10-05 — source-typed pin access, rated preclear and fair repair leases

### Actual received gain: 45 to 44 opens, not single-digit closure

The best retained private ATX repair checkpoint is now:

`build/atx44-support-field-independent-checkpoint-20261005-cd/candidate/board.kicad_pcb`

SHA-256:
`1e54699eb7529813c07a144b6349bcb55f7c72b146cbb9768b9e6387b21727ee`.

Its exact source is the 45-open checkpoint in the preceding section. A
separately received, full-existing-load-rated planar supply preclear prefix is:

`build/atx45-rated-source-pose-preclear-20261005-bl/preclear-0/candidate/board.kicad_pcb`

SHA-256:
`2bf70ff9b538b3b1d18874dc946198b2ac775483205628e9ccd89361965da195`.

The prefix itself still has 45 opens. The subsequent source-isolated R7
re-seat and ordinary `/DETECT_SENSE` completion supply the one actual gain.
Do not credit rejected rotations, advisory poses, unsaved scratch geometry or
the larger synthetic regression count as additional board routing progress.

The final current-code replay is
`build/atx44-final-source-typed-full-review-20261005-cx/receiving.json`.
Both the source-to-rated-prefix and prefix-to-support transactions are
independently received. Saved source, prefix, candidate, their source families
and the production-code epoch remain unchanged during receiving. Results:

| Checkpoint | Native opens | Scored / raw DRC | Full registry | Physical geometry |
| --- | ---: | --- | --- | --- |
| Retained source | 45 | 5 / 560 | 26 PASS, 11 N/A, 10 FAIL, 3 DECLARED | PASS |
| Rated planar prefix | 45 | 5 / 560 | 26 PASS, 11 N/A, 10 FAIL, 3 DECLARED | PASS |
| Received support checkpoint | 44 | 5 / 560 | 26 PASS, 11 N/A, 10 FAIL, 3 DECLARED | PASS |

There are no new independently received native faults or field blockers.
The unaltered five scored faults remain manufacturing debt, not waived errors.
The complete module physical body is retained despite the explicit decision
not to enforce the unused RF antenna keepout. The checkpoint is **not** a BETA
promotion, routing admission, current/Kelvin qualification, or fab-ready board.

### Reusable implementation changes

- `cec_cell_row_rebuild.py`: opt-in cardinal cell rotations, with actual native
  pad transforms and refusals for unsupported internal rigid copper. Rotations
  do not transfer placement authority or authorize lost source connections.
- `cec_device_power_roles.py` and `cec_fr.py`: positively identified scalar
  GPIO series-support semantics can override a misleading ordinary-net name.
  This requires actual selected package pin roles and an exact native two-land
  resistor/terminal witness. Current, measurement, paired and power ownership
  remain protected; there is no ATX/refdes/coordinate case in this classifier.
- `cec_pair_semantics.py` and `cec_fr.py`: unresolved current-monitor packages
  conservatively hold their terminal nets outside ordinary completion. An
  ambiguous part cannot acquire an invented input pair or silently fall through
  to ordinary routing.
- `cec_local_branch_access.py` and `cec_ground_reference_access.py`: optional
  native-connected true-ground alternatives and stationary manufacturer-defined
  ground-reference returns. The original bypass assignment stays authoritative;
  a reference pin is not automatically a supply-decoupling owner.
- `cec_rated_supply_detour.py`: bounded planar preclear at the **existing full
  load rating**, exact retirement replay, preserved external cut partitions and
  future-land reservations. Replacement paths connect actual retained external
  anchors, rather than requiring obsolete internal bends to be rebuilt inside
  the reserved destination. No force-bus rip-up, vias, neckdowns, new load
  assumption or power-zone alteration is authorized by this operator.
- `cec_support_field_reflow.py` and support receiving: explicit bounded
  cardinal Reference/Value reflow, preserving text identity, visibility, font,
  size, thickness, layer and mirrored state. Independent reconstruction copies
  only allowed text poses and then compares the complete footprint. Native
  saved DRC still decides acceptance; readable labels are not hidden to pass.
- `cec_support_pivot.py`: each net in a finite support cohort receives its own
  ten-second construction lease, rather than an early difficult net consuming
  the entire cohort budget. At most eight nets can enter, so aggregate work is
  bounded at eighty seconds. Each subprocess/tool yield remains ten seconds.
- `cec_orphan_support_access.py`: opt-in pivots about a positively proved
  stationary, connected land. Actual native fixed-land shape/net/layer identity
  must be unchanged, and both physical pose and original conductor partitions
  still require independent receiving. Default isolated-support behavior stays
  unchanged.
- Late support-field refusal now preserves the actual **unadmitted** trial
  board, construction trace, exact SHA and reason. It no longer leaves a
  misleading unchanged pre-pose copy as the apparent candidate or loses the
  routing trace that preceded the later refusal.

These are bounded constructors/receivers plus shared-routing protections.
The new placement/preclear operators are not all automatically dispatched by
the regular wave scheduler. This is still not an autonomous, start-to-finish
closure claim. Board coordinates and selected refdes in private recipes are
input data, not production-code repair special cases.

### Package verification and current-code regression

The first broad run had 1,199 passes and three failures in an old ordinary-net
fixture whose INA240 part omitted selected MPN and package identity. The
existing authoritative package catalog was not changed. TI's local
`lib/datasheets/INA240.pdf`, Rev. C, page 3, Table 6-1 and Figures 6-1/6-2 were
rendered and visually checked: SOIC D uses IN+/IN- pins 8/1, while TSSOP PW uses
2/3. The fixture now identifies the actual selected package and correct pins;
the ambiguous-package negative fixture proves conservative ordinary-route
exclusion. No gate was weakened to make the fixture pass.

Final selected-module regression, with no production-code changes between
the receiving/control runs and these tests:

- `build/source-typed-closure-final-broad-regression-20261005-cu.log`:
  **1,207 passed**, 32 modules, 247.07 seconds.
- `build/source-typed-closure-independent-gates-20261005-cy.log`:
  **297 passed**, nine additional modules, 154.59 seconds.

Total: **1,504 passed across 41 selected modules**, not whole-repository CI.
The KiCad SWIG deprecation warning remains. The focused native fixtures include
package ambiguity, source/fixed-land identity, rotated/back-side geometry,
explicit process permission, finite budgets, rejected field metadata changes
and saved failed-trial observability.

`build/source-typed-closure-final-cross-controls-20261005-cv/receiving.json`
passes unchanged-source/current-code replay on PCIe2, Hub, full-body ATX and
the deliberately cropped ATX negative control. PCIe2 remains **0 opens /
0 scored DRC**, Hub remains **0 / 0**. Their inherited qualification state is
unchanged. The cropped ATX still fails physical geometry and the full-body
repair receiver still passes. These controls were not rerouted or promoted.

### Remaining obstruction and next source-owned work

Only **seven of the remaining 44 native opens** are eligible for ordinary
completion. Most remaining opens are owned supply, current, sense or paired
connections; routing them as arbitrary thin ordinary traces is not closure.

The other moved R7 terminal remains open on `/DETECT`. Its actual through-via
menu has no legal seat at the retained pose because front and back foreign
copper jointly obstruct the launch. Spare inner routing layers do not make a
through barrel legal. The recent isolated I2C completion similarly produced
zero additions (`build/atx44-i2c-native-completion-20261005-cw/receiving.json`).
These bounded failures are not a proof that no alternative board layout exists.

Whole sense-cell rotations, grounded-reference returns, anchored pivots and
additional source-rated aperture trials did not produce further received ATX
gains. Attempts that lost measurement/source partitions, had no legal native
barrel access, or failed physical/craft/readable-field receiving remain rejected.
Do not repeatedly rerun the same unchanged candidate menu and call it progress.

The next useful slice is a source-owned neighbor/escape transaction, followed
by rated local-branch and complete paired-route construction. The full registry
also continues to flag missing frozen high-current geometry authority,
current/Kelvin continuity and pair/return-path debt. The existing live load
contracts must be preserved; missing explicit negative-12-V authority or
qualified barrel-plating data must not be substituted with a guessed rating.
Priority force buses are not moved to make ordinary completion easier.

No dashboard/browser/board tab was opened during this slice. Use the explicit
44-open checkpoint and SHA above for the next repair; do not restart from a
46-open archive, a cropped-body source or an unreceived trial.

## 2026-10-05 large residual sweep: received 44 to 43, not broad closure

The larger sweep started from the independently received **44-open** checkpoint
above. The earlier thin tied-enable 43-open trial was not an admissible replacement:
it added an undersized power item inside an already failing current-width check.
The new preferred **private, non-regressive** checkpoint is instead:

- Board: `build/atx44-refined-margin-supply-5sys-20261005-ef/candidate/board.kicad_pcb`
- SHA-256: `4502a784bae837159c6e84b5393ea34e82d2e9ca43de17386c751ef1771b57b3`
- Fresh final receiving: `build/atx43-large-sweep-final-independent-review-20261005-er/receiving.json`
- Result: **43 native opens, 5 scored / 560 raw DRC**, physical geometry PASS;
  **26 PASS, 11 N/A, 10 FAIL, 3 DECLARED** in the full registry.

The accepted transaction adds seven front-copper segments at the unchanged
existing load-derived width (approximately 0.477370 mm). It connects the actual
native TLV755P EN/IN copper without introducing vias, neckdowns, new current
assumptions, footprint movement, source-power movement or zone alteration.
The successful production search used the existing **0.5 mm grid with a 4 mm
margin**, not a finer grid. Its required detour lay outside the old 2 mm window.
Finite fine-grid capability was also added and tested, but is not the cause of
this accepted gain.

Independent receiving proves saved source/candidate family and code identities,
exact additive material, complete native source contacts and supply-contract /
conductor-partition replay. There are **no new native fault objects or field
blockers**. The complete current-debt inventories remain **121 to 121 fault
objects**, not zero. Consequently this result does **not** establish current
qualification, Kelvin qualification, routing admission, BETA promotion or fab
readiness. The ten full-registry failures and five scored manufacturing faults
remain open, not waived.

### Where the remaining 43 opens belong

Fresh source-native classification is recorded in
`build/atx43-full-span-ordinary-sweep-20261005-em/receiving.json`:

| Required closure owner | Native opens | Why an ordinary trace sweep cannot own them |
| --- | ---: | --- |
| Current-domain power and GND | 18 | Preserve source/sink, shunt and current-carrying copper contracts |
| Distributed supplies | 10 | Preserve the existing load-derived width and actual native source contacts |
| Ordinary signals | 7 | Eligible, but sampled escapes / detours still fail or exhaust their finite lease |
| USB / CAN paired paths | 4 | Need complete coupled-path, transition and return-path receiving |
| Negative 12 V | 4 | No explicit source current authority; a guessed legacy rating is not permission |
| Total | 43 | These are native unconnected entries, not 43 independent nets |

Thus **28 of 43** are power/ground-owned, and only seven are ordinary-completion
work. Extra signal layers do not remove foreign copper from all-layer through
barrels or complete an unbuilt power/source/sensing branch.

### Reusable search and receiving changes

- `cec_fr.py`: opt-in finite local maze refinement at 0.2/0.1 mm after coarse
  search failure, sharing the original deadline, work budget, full width,
  foreign-copper/edge/reservation guards and complete-path validator. Failure
  remains a bounded search refusal, never a physical no-path certificate.
- `cec_distributed_supply.py`: validated, parameterized 4 mm maze margin and
  bounded refinement propagation. Existing current contracts remain exact.
- `cec_fr.py`: canonical single-layer breadth precedes a bounded early
  multilayer pilot, before deep Cartesian seat search consumes the lease.
  The pilot examines at most the explicit finite seat-pair count, uses 35% of
  the remaining finite lease, cannot recurse, and retains the same native
  via/process/clearance/field/craft checks. The historical late fallback stays
  available. Direct bridge calls retain their old default; last-mile calls use
  a two-pair pilot only when maze work and an explicit lease permit it.
- `cec_ground_reference_access.py`: linear-return construction uses actual
  SMD copper-surface identity. KiCad's `PAD.GetLayer()` can still report front
  copper on a flipped pad; it is not sufficient surface authority.
- `cec_future_pose_clearance.py` and `cec_rated_supply_detour.py`: opt-in,
  source-bound manufacturer-ground destinations support stationary reference
  repair while retaining the original bypass assignment. No permission to
  move or rip up a priority force bus is introduced.
- `cec_device_power_roles.py` / `cec_tied_control_access.py`: positively
  selected device/package EN-to-IN semantics with native source contacts,
  finite construction and independent receiving. TI TLV755P Rev. SBVS320D
  page 6 was checked; enable input current is typical, not a maximum. That
  number is deliberately not promoted to a branch-current rating.
- `cec_constraints.py` / `cec_current_debt.py`: current-width failures now
  expose complete typed native-item / current-domain inventories, without
  the old twenty-item truncation. Receiving compares exact fault identities,
  current basis, widths and source/rated conductor state, not merely whether
  the same named check still fails. This gate is wired into the new tied-control
  receiver and these closure receiving workbenches; it is not yet a claim that
  every older pipeline receiver dispatches it.

The underwidth negative control is explicitly rejected by
`build/rejected-atx43-current-debt-regression-20261005-eo/receiving.json`:
121 to 122 current fault objects, with the new `+5V_SYS` In2.Cu item identified
by native UUID. Its native open count improved, but current debt regressed.
The source and trial remain untouched and the rejected board must not become
the next seed.

These implementations contain no ATX/refdes/coordinate repair special case.
Source-bound private recipes are input data. The new constructors are not all
automatically dispatched by the regular wave scheduler; this is not an
unattended end-to-end closure claim.

### Broad construction results and finite stop

The supply sweep tried all four explicitly rated distributed-supply nets.
Only the full-width EN/IN join was received. Remaining supply searches added
no accepted material. Separate CAN and USB coupled-path trials on that saved
43-open source likewise added nothing before their finite leases expired:
`build/atx43-large-native-can-sweep-20261005-ei/trial.json` and
`build/atx43-large-native-usb-sweep-20261005-ei/trial.json`.

The broader ordinary sweep gave each of the five eligible nets its own
ten-second lease and expanded the maze distance allowance from a local-support
radius to an explicit 100 mm whole-board maximum. Previously three long
ordinary connections never entered maze search. No smaller clearance, thinner
trace or unauthorized layer was substituted. The expanded pass produced
**zero additions**. Endpoint diagnostics show zero sampled legal barrel seats
for several launches; other launches reach multilayer search but exhaust their
lease without a complete guarded path. A separate opt-in local mesh-refinement
experiment also produced zero additions:
`build/atx43-local-mesh-escape-sweep-20261005-eq/receiving.json`.
Neither failure proves that a different placement or coordinated reroute is
impossible.

Repeated unchanged ordinary sweeps are therefore stopped. The next substantive
work must be coordinated source-owned local branch / neighboring placement
repair, complete paired paths, and restoration of the missing frozen
high-current geometry authority. Actual priority power copper remains fixed;
clearance, current and manufacturing gates remain active. Missing negative-12-V
current authority or barrel-plating qualification must not be filled with a
guess.

Final current-code regression:

- `build/closure-large-sweep-broad-regression-20261005-ep.log`:
  **675 passed**, 31 selected modules, 143.84 seconds.
- Focused early-multilayer/bridge regression:
  `build/early-multilayer-sweep-regression-20261005-el.log`, **136 passed**.
  These overlap the broad set and are not summed as unique tests.
- `build/closure-large-sweep-cross-controls-20261005-en/receiving.json`:
  unchanged PCIe2 and Hub native **0 opens / 0 scored DRC**, unchanged inherited
  full-registry states; cropped ATX negative still fails physical geometry,
  full-body ATX passes, and saved native material/source families are unchanged.

This is selected regression, not whole-repository CI. No board/dashboard/browser
tab was opened, no source/control board was edited, and no BETA artifact was
promoted during this larger sweep.

### Queued reviewer polish: round stroke end overhanging a shunt land

Reviewer reference: `codex-clipboard-797509f1-8207-4461-bcfd-bafa5d9d964f.png`
(2026-10-05). The saved-native front-copper view shows the circular end cap of
a wide diagonal force stroke extending beyond the rectangular shunt pad. This
is actual track geometry, not a plotting filler. Queue this for the next
polish round after power/ground closure: compile a source-owned rectangular or
45-degree-chamfered terminal landing that removes the unnecessary circular
overhang, with independent native cross-section/contact/clearance receiving.
Do not change the component's qualified pad geometry, shrink a required load
path, or treat appearance alone as ampacity evidence. Apply the treatment by
geometry/terminal role, not a hard-coded board reference or coordinate.

## Coordinated power/ground pass, 2026-10-05

The immutable source for this pass is the full-body 43-open child:
`build/atx44-refined-margin-supply-5sys-20261005-ef/candidate/board.kicad_pcb`,
SHA256 `4502a784bae837159c6e84b5393ea34e82d2e9ca43de17386c751ef1771b57b3`.
The source-derived inventory is in
`build/atx43-coordinated-power-ground-inventory-20261005-es/`.
Native terminal partitions distinguish actual stranded IC supply/reference
pins from high-impedance measurement terminals and from unproved rated paths
through filled copper. A rated-path refusal is not automatically an open
load-current connection. Typical datasheet input-bias figures were not made
into maximum branch-current budgets.

### Shared defects repaired

- Local assigned supply links now use the existing sustained-current contract,
  its unchanged geometry margin, and the active fabrication profile instead
  of treating a small netclass as the entire current-width authority. Inner
  layers whose required width exceeds the chosen body width are excluded.
  This does not qualify new or old via barrels.
- The emitter uses the shared land-major/clearance-aware bounded pad escape.
  Independent current receiving re-proves exact generated short prefixes at
  manufacturer-typed supply lands. It excludes aggregate source/sink domains,
  measurement lands, unknown packages, arbitrary thin bodies, missing full-width
  throats, remote paths, branches and over-fragmented components. The existing
  1.5 mm ceiling remains active. This is local geometry-policy receiving, not
  a new measured current/thermal qualification of the device land.
- Stationary ground-reference construction can choose the assigned bypass
  return as well as the owner's true ground pin, but only when source-native
  connectivity independently proves those returns already belong to the same
  grounded component. A nearby arbitrary GND pad is not destination authority.
- Fine maze refinement is explicit and shares the original work/wall lease.
  Refined supply work requires a finite positive wall bound no greater than
  ten seconds. Ordinary preclear retains its two-second planar reservation
  and total operation bound; unsuccessful menus are not no-path proofs.

### Actual saved improvement and independent review

An early 0.2 mm-only supply trial reduced the native count but added three
current-width faults and was rejected:
`build/atx43-assigned-power-cell-sweep-20261005-ey/trial-0/board.kicad_pcb`.
It is not a continuation seed.

The corrected generic constructor connects the source-assigned TPS2121 IN1
land to its bypass on F.Cu, preserving every prior copper item and component
pose. Its 1.766 mm simple used chain has a 0.477370 mm full-width body and
three independently re-proved short 0.2 mm escape fragments totaling 0.566 mm.
It creates no barrels and does not move any power bus. The existing supply
authority remains 3 A with the existing 1.25 geometry margin.

The retained private result is **43 -> 42 native opens**:
`build/atx43-fine-rated-power-cell-sweep-20261005-fc/trial-0/board.kicad_pcb`,
SHA256 `824d4e8718d04468dfba5b873c4f0659f6cdb5eda9f11cf32781a9541e3774d3`.
The original construction packet recorded a then-present receiver API error;
it is preserved rather than rewritten. The fresh final-code review is
`build/atx42-power-ground-final-independent-review-20261005-fk/receiving.json`.
It independently re-derives source bypass ownership, actual isolated terminal
gain, complete used-chain geometry, current floor and pad-prefix eligibility,
exact additive replay, craft, native DRC, field coupling, physical placement,
the full rule registry, and immutable source/candidate/code identities.

Final review passes with no new native fault identities or field blockers.
Both source and child have **5 scored / 560 raw DRC**, physical placement PASS,
and **26 PASS / 11 N/A / 10 FAIL / 3 DECLARED** in the full 50-rule registry.
Current-debt inventory stays **121 -> 121**, with no new or worsened fault
objects. Existing whole-board current, Kelvin, power-pour, USB and connectivity
failures remain; the child is not fab-ready or release-qualified.

### Remaining bottleneck; no unchanged-loop retry

The additive canonical Kelvin pass
`build/atx43-coordinated-kelvin-sweep-20261005-et/` added no accepted material.
Its native blockers are neighboring supply, signal and existing reference
branches, not a reason to reduce clearance or guess monitor current limits.
The per-layer plots in
`build/atx43-native-reference-copper-20261005-eu/` are actual saved native pad,
track, and filled-zone polygons, with no filler copper.

The stationary reference-ground preclear in
`build/atx43-coordinated-reference-ground-sweep-20261005-ev/` likewise made no
accepted gain. One INA181 REF is caged between an under-body +3V3 branch and an
I2C branch; the back face is occupied by actual priority force copper. Retiring
only the ordinary I2C branch does not free a legal second endpoint seat.
The remaining reference/supply repairs require coordinated local branch
reconstruction or role-aware reseating, while preserving full physical bodies
and power copper. A repeated unchanged additive wave is not useful here.
The separate missing multi-pin high-current input manifold still requires its
actual frozen geometry/current authority, not an assumed equal current split.

Final selected regression:
`build/current-supply-ground-final-regression-20261005-fj.log`, **266 passed**
across nine modules (29.61 seconds). This includes rotated/flipped/renamed
positive supply fixtures, forged/remote/branched/measurement/aggregate negative
prefixes, inner-layer width exclusions, grounded bypass-alternative receiving,
and finite refinement-bound tests. It is selected regression, not whole-repo CI.

Final-code cross-board controls:
`build/current-supply-ground-final-controls-20261005-fl/receiving.json` passes
with immutable saved source families and code epoch. PCIe2 and Hub remain at
native **0 opens / 0 scored DRC**, with their inherited full-registry states
unchanged. The cropped-body ATX negative still fails physical placement;
the full-body ATX control passes physical placement. Both remain at 46 opens
and 5 scored DRC. This replay does not promote the Hub or alter an archived
fab-review candidate's qualification status.

No board browser tab was opened, no archived control or BETA board was edited,
and no fab or release status was granted. The queued circular-overhang polish
above remains a separate later operation, not part of this current receiving.

## 2026-10-05: source-typed power terminals and exact main-rail bottlenecks

### Retained saved-board improvement: 42 -> 41 native opens

The parent remains the immutable full-body 42-open checkpoint:

`build/atx43-fine-rated-power-cell-sweep-20261005-fc/trial-0/board.kicad_pcb`

SHA256 `824d4e8718d04468dfba5b873c4f0659f6cdb5eda9f11cf32781a9541e3774d3`.

The independently reviewed private child is:

`build/atx42-board-floor-control-bridge-20261005-gc/candidate/board.kicad_pcb`

SHA256 `a74a948572d3235a09420850bdbc612b1ee50088c6e7bf3443e3e2bf398def6f`.

The actual +5VSB native component already contained the mux input and its
capacitor; a representative airwire must not be interpreted as an isolated
capacitor. The newly joined island is the populated R55/R57 control divider.
Its opposite nodes are positively typed manufacturer control inputs, not
unknown loads or measurement pins. The feed uses the unchanged source-connected
C54 land and R57 land, two fully contained profile-permitted 0.5/0.3 mm POFV
seats meeting ordinary board minima, and a simple 0.2 mm bottom-face branch.
The existing 3 A x 1.25 source/shunt trunk retains its full-width obligation.
This does not rate the old source-connected capacitor pickup or qualify
the whole standby rail. No main-bus item, footprint, schematic or old via moves.

Fresh final-code receiving and all 50 registered checks are recorded at
`build/atx41-power-final-full-registry-20261005-ha/receiving.json`.
Source and child remain **5 scored / 560 raw DRC**, physical placement PASS,
and **26 PASS / 11 N/A / 10 FAIL / 3 DECLARED**. There are no new native
fault identities or field blockers, and immutable source/candidate/code
identities are confirmed. This is a private routing prefix, not fab readiness.

The actual production entry independently reproduces **42 -> 41** under
the final code at
`build/atx42-production-terminal-entry-replay-20261005-hd/receiving.json`.
That replay's different UUID-bearing child is a separately received private
trial, not a replacement for the full-registry-reviewed checkpoint above.

### Generic rules, not a divider-specific repair

- `cec_power_terminal_access` derives stranded native electrical islands,
  existing full-current source/sink trunks, alternate terminals on one island,
  finite interior contacts, and exact pad-to-track projections. A source-typed
  resistor/control motif may use the existing branch floor; measurement,
  power-input, unknown, connector, DNP and zero-ohm cases cannot acquire that
  exemption. Only that non-load motif may use the contained two-seat bridge.
  Its receiver re-derives source ownership, consumes every new edge/seat,
  checks native DRC/current debt/physical/craft/field evidence, and refuses
  extra copper, changed widths or whole-net frozen leases.
- The synthesis coordinator invokes the bounded terminal tier before ordinary
  distribution. Caller-owned/future-pour nets remain excluded. A retained
  prefix never reports `completed_nets`, freezes the rail, or grants current
  or release qualification. Ordinary aggregate-distribution exclusions remain.
- Small explicit full-load logic-supply detours may use finite finer search and
  optional **at most 4 mm total** degree-two source-cut extension. Real pads,
  barrels, zones, tees, groups, changed widths and force domains stop extension;
  all old native partitions and exact unowned objects still require receiving.
- Stationary REF repairs may use either source-verified endpoint of the same
  grounded component: the bypass return or actual manufacturer ground. The
  historical bypass-first lease remains first; a refused lease may try the
  owner-ground alternative under the same finite deadline/trial cap. Every
  new ground edge must belong to one simple fully used return chain.
- Thin measurement-leaf search retains exact first-junction/land contact and
  forbidden same-net contact checks while opting into finite local refinement.
  Its actual SMD layer-set, not a stale `PAD.GetLayer()` after flipping, selects
  the native face.

### Better power failure attribution is not repaired ampacity

`cec_measurement_current_branch` positively identifies manufacturer non-load
input leaves meeting the original project/process floor. Their collective
removal must leave **every native current-terminal partition unchanged**.
A declared current terminal, under-class width, unknown role, changed native
partition, incomplete inventory or exhausted proof cannot receive that role.
No numeric input load, current sharing, barrel/zone capacity or release
qualification is inferred.

The old current inventory included thin measurement leaves merely because
their rail's independent main path still failed. Reclassification removes
that misleading repair attribution, but does not fix the main conductor.
Final-code source and child both have **111 -> 111** fault objects; the older
**121** count used the previous classification. The same **six main-current
domain failures remain failures**, not a claimed 10-object physical repair.
Source-typed proof and full unmodified failing-domain evidence are stored in
`build/atx41-source-typed-power-branches-20261005-gw.json`.

Five domains have original native connectivity but lose source/sink continuity
after underwidth copper is excluded: +5V_MAIN, /SENSE12V_HI, /SENSE12V_LO,
/SENSE3V3_LO and /SENSE5VSB_LO. /SENSE5V_HI also has a pre-existing open.
The design currents, margins, selected fabrication profile and layer-specific
width equations are unchanged. Inner-layer requirements cannot be presented
as if they were outer-layer bus widths or silently replaced with guessed splits.

The exact +5V_MAIN forensic replay in
`build/atx41-main-power-native-cut-20261005-gk/forensic.json` includes actual
native filled zones and plated pads. Its original authority component is
connected; after underwidth exclusion the shunt and four physical output
terminal legs are five distinct components. The existing wide bus narrows
into 1.25 mm terminal feeds; filled patches around the shunt do not provide
a poured output-terminal manifold. A zone somewhere on the same net is not
source-to-terminal capacity proof. Layer images in
`build/atx41-main-power-native-views-20261005-gm/` plot saved native copper
and voids directly, not FEM filler, nominal corridor boxes or substituted pours.

### Bounded no-gain trials and next power-owner work

The rated ground-reference trials `...-gq` and `...-gs` and stationary
measurement/reference trials `...-gu` and `...-gx` retain **no candidate**.
They are finite unknown/no-gain results, not global no-path proofs or reasons
to retry an identical wave indefinitely. The two remaining INA181 references
have distinct exact front-face blockers: one source-owned measurement branch,
one explicitly budgeted logic-supply branch. Through-via seats are additionally
blocked by actual inner/back copper. The buses may not be displaced simply
to manufacture a via seat.

Next construction must address the source-bound main terminal/manifold and
actual post-fill current path with the power owner, and coordinated local
amplifier-cell reconstruction/reseating for the ground cages. Keep terminal
and mating geometry, current margins, physical bodies, Kelvin isolation,
minimum native pour cross-sections, and fabrication/thermal/release checks.
Neither extra signal waves nor a blanket thin-trace exemption can qualify
these physical power failures.

### Final-code regression and archived controls

`build/power-terminal-current-ground-final-tests-20261005-hb.log` records
**481 passed** across 14 selected modules (270.95 seconds), including rotated,
flipped and renamed inputs; no-load versus power/unknown roles; real underwidth
current-path negatives; exact native partitions; ordinary/process via floors;
whole-net-owner exclusions; finite refinement/cut extension; forged changes;
production stage integration; and the generic-engine audit. This is selected
regression, not whole-repository CI or full-pipeline electrical qualification.

`build/power-terminal-current-ground-final-controls-20261005-hc/receiving.json`
confirms unchanged code epoch and immutable control families. PCIe2 remains
**0 opens / 0 scored DRC / 32 PASS / 12 N/A / 3 FAIL / 3 DECLARED**. Hub remains
**0 opens / 0 scored DRC / 30 PASS / 17 N/A / 3 DECLARED**. The cropped-body ATX
negative still fails physical placement; the full-body control still passes.
Both ATX controls retain 46 opens and 5 scored DRC. No archived control,
BETA source, BOM, schematic or release status changes, and no board-view
browser tab opens as part of these runs.

## 2026-10-05: owned force finalization and native 12 V output prefix

### Physical current-width improvement, not an open-count improvement

The retained incumbent is still the full-body 41-open board at
`build/atx42-board-floor-control-bridge-20261005-gc/candidate/board.kicad_pcb`,
SHA256 `a74a948572d3235a09420850bdbc612b1ee50088c6e7bf3443e3e2bf398def6f`.

The new **UNADMITTED private native candidate** is
`build/atx41-12v-output-owned-finalization-20261005-hm/candidate/board.kicad_pcb`,
SHA256 `d9c653f665c47459fcfb7deedfbc3785d8dff61fc2943fc3ca899faaaefa85e8`.
It is not a new incumbent, fab candidate, qualified power rail or release.

The existing generalized constant-width force constructor joined the actual
RS1 output land to all four physical TB1 lands. Four component joins produce
six native front-copper segments at 3.230592 mm width, using positively checked
pad-surface contacts rather than treating crowded pad centres as the only
possible endpoints. The unchanged authority is 12 A with 1.25 geometry margin;
the width model, layer thickness, terminal identity and design budgets did not
change. No current division between terminal legs or layers was assumed.

Final-code independent receiving is saved at
`build/atx41-12v-output-final-native-review-20261005-hu/receiving.json`.
The width-based native source-to-all-terminal graph now passes for
`/SENSE12V_LO`: **six failing current domains become five**, and **111 current
fault objects become 106**, with no new or worsened current fault. This is a
real added-copper improvement, not the earlier non-load classification change.
It is still a width-model/connectivity result, not current, DCIR, thermal,
Kelvin or whole-rail qualification.

Native opens remain **41**, scored/raw DRC remain **5/560**, physical placement
passes, no new native fault identity or field blocker appears, and all 50
registered checks remain **26 PASS / 11 N/A / 10 FAIL / 3 DECLARED**. Every
original track, placement, protected power polygon, project rule and sidecar
remains exact. The native route-craft check passes, but it does not supersede
the owner's still-queued circular-cap/overhang and purposeful-landing polish.
Native F/B plots are at `build/atx41-12v-output-native-views-20261005-hp/`;
no board browser tab was opened.

### Generic finalization repair and independent transaction receiving

The first valid native full-width plan failed while a global refill attempted
to recompile protected overlapping power zones without their declared owner.
That was an operator-scope error, not evidence that the newly constructed
track path was blocked. The failing receipt is retained at
`build/atx41-12v-output-fullwidth-20261005-hk/receipt.json`.

`cec_force_current` now finalizes its segment-only transaction by replaying
existing GND fill only, saving a non-normalized native snapshot, and having
`cec_additive_route_receiving` independently reconstruct the exact source plus
exact additions. It has no authority to reshape or refill protected power
polygons. Strict preservation remains the default; explicit ground-fill mode
allows only modifications positively reproduced by the independent receiver.
The aggregate priority-force receiver applies the same evidence boundary.
Changed original tracks, widths, outlines, unrelated copper or project
sidecars still refuse. This is not a zone-name whitelist or an unchanged-DRC
waiver, and it grants no power or release qualification.

Renamed and rotated synthetic power fixtures exercise the production worker
with native overlapping power fills; an accidental global refill is made to
fail the test. Real track-only GND-antipad changes are accepted only after
exact reconstruction. Tampered fill, outline, old width, wrong-net additions,
sidecars and non-boolean opt-in cases remain negative controls.

### Fail-closed geometry queries and diagnostic parity

The shared maze snapshot guard previously continued past a failed native
foreign-copper collision query and could return `True` (clear). It now returns
`False` (not qualified) for that unknown. The diagnostic twin also retains
the object's identity and `geometry_unknown` status; endpoint escape logs
must not call that ray clear or count it as a positively proved physical
obstruction. This bug is found by source inspection, not asserted to be the
cause of any particular board's existing DRC fault.

Synthetic raw and spatially indexed tests cover zone/track/pad/NPTH geometry,
collision and broadphase exceptions, rotated paths, successful empty collision
queries and refusal certificates. The selected native-guard test group records
**148 passed** at
`build/native-foreign-geometry-failclosed-regressions-20261005-hq.log`.

### Exact remaining barriers and finite no-gain searches

The `/SENSE12V_LO` scoped Kelvin admission still refuses:
`affected_sense_copper_demand_not_verified`. U10.9 and U612V1.4 remain genuinely
disconnected from their typed RS1.2 source. They have no proved native thin
inner-pad departure. Connecting the load-bearing bus is not permission to
mark those independent measurement demands connected or Kelvin-qualified.

A separate exact-source test of the existing production Kelvin constructor
refuses before construction: its inherited pour-first state declares
`placement_scope=complete` but has no frozen power nets/polygons. The guard's
`complete frozen power authority is empty` refusal is retained at
`build/atx41-12v-native-kelvin-authority-refusal-20261005-hw/probe.json`.
The state was not deleted, re-labelled, bypassed or populated with synthetic
copper. A new native power owner must build and qualify real geometry before
it can publish complete frozen authority; the disconnected typed sense cells
also require a real source-to-input reconstruction. No identical wave retry
can substitute for either missing precondition.

The standby output has a separate actual bottleneck: its 3 A x 1.25 long
inner-layer path contains 0.8-1.5 mm copper against a 5.719034 mm inner-layer
requirement. Bounded 0.2 mm-grid front searches with 5/15 mm margins and a
back-face search through existing plated transitions produce no selected
candidate. Receipts `...-hh`, `...-hi` and `...-hj` retain those refusals; they
are not global impossibility proofs or via-capacity qualification. Design
currents, layer budgets and existing main buses were not weakened or moved.

The public ten-second force-proposal supervisor deferred the final HM trial
during evidence collection, so it does not report an admitted candidate.
The separately saved native prefix above was independently reviewed under the
final code. A staged evidence handoff must preserve the remaining operation
lease and exact identity; silently extending deadlines or accepting partial
evidence is not a speedup.

### Immutable final-code board controls

The combined final-code selected regression records **453 passed** in 150.90
seconds at `build/current-owned-finalization-and-native-guards-final-20261005-ht.log`
(ten test modules). This includes force construction/admission, aggregate
dispatch, exact additive receiving, current-debt negatives, pad-surface access,
unknown-collision refusal, last-mile routing, cached native geometry and bounded
maze refinement. It is selected regression, not whole-repository CI.

`build/current-finalization-and-native-guards-controls-20261005-hv/receiving.json`
confirms the final code epoch and all immutable board families are unchanged.
PCIe2 retains **0 opens / 0 scored DRC / 32 PASS / 12 N/A / 3 FAIL / 3 DECLARED**;
the private Hub control retains **0 opens / 0 scored DRC / 30 PASS / 17 N/A /
3 DECLARED**. Both old ATX controls retain **46 opens / 5 scored DRC**; the
cropped-body negative still fails physical placement and the full-body control
still passes. These are nonregression controls, not new fab qualifications.
No BETA schematic, BOM, archive or saved board-control edit is part of this slice.

## 2026-10-05: break the repair plateau without hiding current debt

### Pipeline contract defects, rather than another unchanged wave

This slice separates permission to perform bounded construction from electrical
qualification. It does not relax fabrication, current, mechanical-stack, field,
Kelvin, or release gates. No board/refdes/coordinate exception was added to the
production changes below.

1. The producer's `placement_scope=complete` describes a complete component
   population, not a successful power solve. The earlier empty-freeze refusal
   needs that distinction: this ATX state has a positive, finite failed planner
   receipt with zero emitted geometry. `cec_power_guard_geometry.solve_status`
   now calls this **deferred**, never qualified or frozen. Contradictory/missing
   receipts still fail closed, and all declared future Kelvin territories remain
   reservations. Existing native power copper remains a real obstacle.
2. Ordinary residual scheduling required zero DRC and at most 32 opens, so the
   actual 41-open/5-DRC incumbent could not enter repair. A fresh, complete
   UUID-based native fault inventory now permits a bounded additive portfolio.
   Its receipt binds the exact board family, parameters and code epoch; it is
   work eligibility, not a waiver or a release certificate. An improvement
   must preserve fault identities and receive a fresh full oracle.
3. Additive receiving demanded authority to replace an unresolved local power
   cell merely to retain it. A retention-only prefix now preserves actual
   source copper/qualified pairs without granting local reconstruction rights.
   An independent source-plus-exact-additions replay rebuilds existing GND fill
   only. Protected power fill, terminals, functional poses and other authority
   files remain exact. Existing exact-object POFV rules may extend only to
   qualified new via UUIDs, not inherited or unrelated material.
4. A generated `board.drc.json` diagnostic became a new saved-family companion,
   invalidating the very receipt the worker was trying to prove. Diagnostics
   now live outside the PCB authority namespace. They cannot become ownership
   or construction inputs through a filename accident.
5. The repair caller compared the routed board to itself as its authored origin,
   producing zero generated-item scope. A bounded, hash-matched declared
   placement origin with equal native electrical-terminal identities recovers
   the real ancestry. On this ATX it identifies 494 eligible locked generated
   items, not permission to remove power/Kelvin/coupled copper. The origin hash
   is checked again at exit. A 120-second negotiated replay made no further
   gain and stopped; that result is not a physical impossibility proof.
6. The optical allocator ignored actual pad/footprint permission areas. FID3
   therefore occupied the opposing-capacitor mechanical guard, causing two
   native DRC faults which routing could never repair. The shared rule-area
   reader now supplies both native permission types, including footprint-local
   areas, polygon holes and concavities. Front-side optical placement respects
   those exact shapes; routing-only and opposite-face areas are not blanket
   exclusions. Assembly-only receiving permits exact translations of real
   unconnected optical marks, with no changes to other copper, pads, fills,
   rules, functional parts, or non-optical placement authority. Native saving
   does not propagate/relabel copper nets.

### Actual evidence, including the result that was withdrawn

The initial additive portfolio reduced **41 to 39 opens**, with 5 scored DRC
unchanged. `build/atx41-known-debt-breadth-20261005-ik/breadth.json` records the
finite search and source/code preservation; independent native/full-registry
receiving at `build/atx39-known-debt-independent-receiving-20261005-im/` accepted
that private work checkpoint. It is not a fab candidate.

The first real canonical grading/resume pass (`...-is`) reached 37 opens/3
scored DRC in 359.818 seconds. The optical relocation removed the two actual
mechanical keepout faults. However, **the 37-open result is withdrawn from
selection**, despite its earlier native/full50-name receiving result.

Detailed comparison found three new `+5V_SYS` width-fault objects: a front
segment below the existing 0.477369 mm requirement and two inner segments
below 5.719034 mm. Both requirements come from the ratified 3 A, 1.25-margin
contract and actual declared stackup; no new load or margin was invented.
Adding a connection can also invalidate an old bounded-escape classification,
so exact preservation of the old segment bytes alone is insufficient.

The full50 failed-check name `trace-width-high-current` stayed FAIL while its
fault inventory grew from six domain failures to those same six plus three
trace faults. Comparing only failed check names hid the regression. The
existing generic `cec_current_debt` object/severity comparator was present but
not wired into this additive path. It now runs in worker admission, again at
independent canonical admission, and in the full receiving harness. The
signal-width constructor also defers every positively modelled supply to the
existing current-rated producers, even when its ordinary netclass is 0.2 mm.
It neither assumes a branch load nor claims a via/current rating.

`build/atx37-rejected-exact-current-debt-20261005-iy.json` freshly rejects all
three faults with complete, source/candidate/code-stable evidence. This is a
real-board negative control, not just a synthetic assertion. The earlier
`...-is`/`...-iv` files are retained as historical receipts from before that
integration repair, not authority to select their candidate.

Renamed synthetic supplies, stale/partial/changed debt receipts, new current
objects under the same failed label, worsened dimensions or changed current
authority, native keepout permissions/holes, and forbidden optical/copper/pad
mutations are covered by regression tests. Passing work admission never makes
the inherited current debt qualified.

The final-code controls at
`build/atx-stall-exact-current-final-controls-20261005-ja/receiving.json` retain
the exact PCIe2 and private Hub hashes and **0 opens/0 scored DRC**. Their
full50 status distributions remain respectively 32 PASS/12 N/A/3 FAIL/3
DECLARED and 30 PASS/17 N/A/3 DECLARED. Both 46-open ATX controls are unchanged;
the cropped-body negative still fails physical placement, and the full-body
control still passes. The code epoch and every source family are unchanged.

The final-code canonical grading/resume pass at
`build/atx39-canonical-exact-current-resume-20261005-iz/receiving.json` reduced
the safe 39-open/5-scored-DRC checkpoint to **38 opens/3 scored DRC**, in
307.757 seconds. The two optical keepout faults were repaired before the
bounded additive portfolio closed one more negative-12 V connection. Its
remaining budget stop is not a proof that no legal route exists. The selected
private work checkpoint is
`build/atx39-canonical-exact-current-resume-20261005-iz/resume/breadth-admission/incumbent/board.kicad_pcb`,
SHA-256 `efa384009f119fcd892a71cbd24397a5eea398a5475110365fc31d61a8afc611`.

Fresh independent receiving under the final code at
`build/atx38-exact-current-final-independent-receiving-20261005-jd/receiving.json`
accepted that identical candidate hash with no failed receiving terms, no new
native fault identities, no new field blockers, and a complete exact-current
comparison with no new or worsened faults. Source/candidate families and the
code epoch remained unchanged. It still has 558 raw DRC messages, the same
26 PASS/11 N/A/10 FAIL/3 DECLARED full50 distribution, and only 4 of 16 typed
Kelvin legs checked/passing (12 unknown). **Release authority remains false.**
Relative to the turn's immutable 41-open/5-scored-DRC starting checkpoint,
this is three fewer opens and two fewer scored DRC violations, not electrical
or fabrication closure.

The final-code regression log
`build/atx-stall-exact-current-final-regression-20261005-jb.log` records
**924 passed, one warning, in 272.42 seconds** across 24 relevant modules.
The safe 38-open checkpoint supersedes the earlier 39-open private checkpoint;
the withdrawn 37-open trial remains only a negative-control artifact.

### Remaining priority work is upstream construction

The ATX still has a deferred, unqualified high-current plan, six failing main
current domains, twelve unknown typed Kelvin legs, incomplete USB/CAN pair
topology, and fragmented IC supply/return groups. Continuing to connect those
with ordinary signal-width copper would conceal the problem rather than close
it. The next construction unit must repair the typed power/measurement cell
and produce real rated outer-layer/transition geometry and source-to-input
Kelvin evidence before downstream completion. Existing current budgets, main
bus geometry, stack keepouts and source controls were not weakened or moved.
No BETA schematic, BOM, board, archive, commit or push is part of this slice.

## Thirty-open target: verified 38 to 34, not yet achieved (2026-10-05)

The request began from the selected 38-open/3-scored-DRC private checkpoint,
SHA-256 `efa384009f119fcd892a71cbd24397a5eea398a5475110365fc31d61a8afc611`.
Three independently received additive constructions reduced it to **34
opens/3 scored DRC**. No original bus, pad, pose, power-pour declaration,
manufacturing rule or load budget was changed. These are private work
checkpoints, not a completed current tier or fabrication candidates.

| Construction | Native gain | Independently received child |
| --- | --- | --- |
| Fair ordinary native-demand portfolio | Negative-12 V, 2 to 1 islands | `build/atx38-fair-frontier-breadth-20261005-jn/candidate/board.kicad_pcb` (37 opens) |
| Native-open-first distributed supply frontier, unchanged full aggregate width | System-port supply, 3 to 2 islands | `build/atx37-rated-native-frontier-trial-20261005-jz/candidate/board.kicad_pcb` (36 opens) |
| Existing native full-current surface constructor | +5 V post-shunt force terminals, 5 to 3 islands; 6.535523 mm conductors | `build/atx36-rated-force-frontier-trial-20261005-kd/candidate/board.kicad_pcb` (34 opens) |

The selected 34-open board hash is
`44315bcdb0ba4002388be96edc4a90e8490ae71fa99ac38a004feeae00ce9a78`.
Final-code independent whole-chain receiving at
`build/atx38-to34-whole-chain-independent-receiving-20261005-kx/receiving.json`
accepted the immutable 38-to-34 comparison with **24 additive native items**,
zero new native fault identities, zero new full50 failures, no new field
blockers, and a complete exact-current-debt comparison with no new or
worsened faults. Its receipt hash is
`0976733bde06b428774e5487b52d59c0b6576db6b0368c05ec0b81f1346319cd`.
Raw DRC remains 558; full50 remains 26 PASS/11 N/A/10 FAIL/3 DECLARED.
Typed Kelvin remains 4 passing/12 unknown/0 failing of 16 expected legs.
Inherited six-main-domain current debt remains unqualified.

### Reusable implementation changes

- Source-bound native demand enumeration now recovers opens omitted by the
  optional 32-detail diagnostic sample. Exact UUID/layer/dimensional evidence
  is reconstructed from the saved source; this is demand, not route permission.
- Ordinary targets interleave distinct nets and fund never-sampled frontiers
  before partially sampled ones. Unchanged native epochs keep finite search
  history across batches; a per-batch expiration does not prematurely declare
  plateau while useful portfolio time remains. Adoption resets stale history.
- The rated planar constructor prioritizes genuinely disconnected native
  islands ahead of width-qualified fragments of an already connected rail.
  Every new conductor still uses the complete unchanged aggregate current
  width. Its source-plus-delta save refills ground only, never power pours.
- Expanded exact-pair pin escapes can opt into the existing 0.2/0.1 mm local
  maze tiers only under a finite shared deadline. Width, all-layer via,
  fabrication, clearance, craft and field gates are unchanged.
- Certified alternate-attachment discovery now uses a fresh private KiCad
  contact graph. It neither trusts a stale cached graph nor calls a board
  rebuild that can propagate pad nets onto inherited touching foreign copper.
  A synthetic foreign touching track remains on its original net; an actual
  newly added same-net attachment is discovered without changing the board.

The focused final-code suite at
`build/native-frontier-complete-regressions-20261005-kv.log` has **365 passing
tests**, one existing SWIG warning, across six routing/receiving modules.
Final-code controls at
`build/native-frontier-island-cross-board-controls-20261005-kw/receiving.json`
are unchanged: archived PCIe2 and private Hub retain 0 opens/0 scored DRC;
both 46-open ATX controls retain 5 scored DRC. The cropped-body negative still
fails physical checking, the complete-body control still passes, and source
families and the code epoch remain exact. This is regression evidence, not
whole-board release qualification.

### Bounded refusals and the next construction boundary

The 34-open native source was also tried with finer rated supply escapes,
40-second USB/CAN coupled portfolios, source-derived passive pivots, fresh
native island alternatives (283.686 seconds), and endpoint-boundary axes with
fair per-net leases. None produced a new retainable closure. The safe board
was not overwritten by their unchanged or refused proposals. Budget expiry
is not a physical no-path proof; repeating those identical menus is not a
next step.

Read-only per-layer diagnostics at
`build/atx34-compact-native-seat-diagnostic-20261005-kn.json` and
`build/atx34-scalar-native-seat-diagnostic-20261005-kt.json` distinguish blocked
pin-to-barrel launches from middle-path failures. The SCL controller contacts
have no retained legal launch in the sampled native domains; power tracks on
other layers and already-present return dogbones participate in the blockage.
For the two source-typed reference grounds,
`build/atx34-cell-link-obstructions-20261005-kj.json` identifies the specific
thin measurement/supply branches crossing their local return corridors.
Clearing one branch without restoring its owning topology is not admissible.

The next useful construction unit is coordinated source-owned local branch
and return escape repair (including the existing dogbone when it is the
blocker), or a completely source-typed power/measurement-cell replan. It must
restore every affected ordinary/rated/measurement obligation and receive the
complete composite. The full-current producer's all-or-nothing qualification
must not be weakened merely to label a partially improved net complete.

`build/atx-stall-selected-safe-checkpoint-20261005-je.json` now selects the
independently received 34-open private board and explicitly records the
30-open target as **not met**. Four more verified closures are required. No
BETA board, schematic, BOM, control board, commit, push, memory update, or
new browser/board tab was made by this slice.

## Typed local source-cut transaction: verified 34 to 33 (2026-10-05)

The private resume selector now points to
`build/atx34-class-sized-address-scl-composite-20261005-lp/candidate/board.kicad_pcb`,
SHA256 `626e67ea8d9daea8c06ad12d3f3f4e10090b20226828dec52df2cd0e445fd144`.
The final-code independent receipt is
`build/atx34-to33-final-bound-proof-receiving-20261005-mk/receiving.json`,
SHA256 `085e313b0fc85c88482aac17f787ae4e009a07ee7563420250e06eddcf97caf2`.
It accepts **34 to 33 opens**, retaining **3 scored DRC / 558 raw violations**.
Full50 remains 26 PASS / 11 N/A / 10 FAIL / 3 DECLARED; typed copper-cut
evidence remains 4 passed / 12 unknown / 0 failed. Existing current, pair,
field, source-terminal partitions and protected power copper are preserved.
This does not qualify inherited current debt, unknown Kelvin inputs or fab release.
The requested maximum of 30 opens is still **not met**: three more accepted
closures are needed. This slice gains one closure, not five; the earlier
38-to-34 work accounts for the other four in the retained resume chain.

### Root cause and admitted construction

The first SCL controller launch was obstructed by a full-budget 3.3 V branch
and an ordinary ground via belonging to a manufacturer-typed address strap.
Removing either obstacle without restoring its source obligation was not
admissible. A complete private transaction reseats the existing 0.6/0.3 mm
ground root by 0.225 mm, rebuilds only that address strap, reconstructs the
small supply branch at its unchanged full-load width and adds the scalar
escape. Decoupler returns are not lengthened; main buses and power fills are
not regenerated. The first proposal used an undersized SCL via and failed
netclass receiving; the selected proposal uses the unchanged class minima.

Production receiving additions are source-typed, not refdes/coordinate recipes:

- `cec_ground_strap_rebuild`: only ground-tied manufacturer address/reference
  leaves; at most eight uniform thin edges and 12 mm of source path. An
  otherwise unbranched ordinary root may move by at most 1 mm with identical
  barrel geometry, or a logical leaf may reconnect to an immutable shared
  mesh junction. All surviving partitions, saved plane contacts and existing
  immediate ground returns are preserved. Ground/power pins are not eligible.
  Grounded analog-reference returns cannot use an address strap's bounded
  length allowance: they must remain no longer than their actual source path.
- `cec_rated_branch_repair`: at most eight explicit small planar source edges,
  with unchanged distributed-load authority and full-load width. New scalar
  copper must meet the actual source netclass and fabrication minima; an
  assumed per-branch load or power-via capacity is not authority.
- `cec_source_cut_chain`: at most four individually retyped saved phases,
  followed by an independent original-source-minus-exact-cuts-plus-additions
  replay. Later phases cannot retire earlier reconstruction. Field and typed
  contact receiving use the actual original source and independently proved
  track/via inventories, not a worker-supplied waiver or a cut-away baseline.

These are generic transaction receivers. The finite constructor workbenches
in `build/` remain private experiments; this slice does not claim that their
candidate discovery is already an integrated unattended pipeline operator.

### Regression and refusal evidence

`build/typed-cut-final-bound-reuse-complete-regressions-20261005-mj.log` has **516 passing
tests**, including 49 new source-cut cases. The new tests cover renamed and
rotated geometry, immutable shared trunks, loss of native contacts, altered
source/poses, inappropriate ground roles, missing/changed load authority,
undersized scalar/rated/ground copper, nonlengthening reference returns,
ambiguous/incomplete phase manifests and input changes during cached rebinding.
`build/typed-cut-final-bound-proof-cross-board-controls-20261005-ml/receiving.json` retains
archived PCIe2 and private Hub at 0 opens / 0 scored DRC with no added copper
or changed input families. Their prior Full50 states remain unchanged; those
controls are not a new fabrication qualification.

### Bounded proof reuse: repair the audit stall without changing its gates

The stricter final audit reproduced an implementation/runtime defect: the
same already-completed structural cut-chain proof was recomputed inside a
10-second field-check lease and again during contact and final receiving.
`build/atx34-to33-final-strict-independent-receiving-20261005-mf/receiving.json`
preserved every measured/native/physical comparison but correctly refused
admission because its field subcheck expired (10.260696 seconds).

The receiver now retains at most four **complete positive process-local**
structural proofs. Every reuse freshly binds all source/intermediate/candidate
families, rule/project/compiled-policy files, engine code, CEC context and live
receiver functions, then repeats the binding before returning. The receipt is
defensively copied; no failed/partial worker packet is cached, no proof is
persisted across processes, and any source/context change invalidates reuse.
Injected input changes during rebinding fail closed, not with a stale positive
flag. Independent current, field, pair, native DRC and Kelvin checks still run.
The workbench primes the cut proof in its own bounded stage so field checking
does not spend its lease redundantly rebuilding it.

The final accepted receipt completes in **38.652817 seconds**, with its field
stage independently passing in **1.516305 seconds**. The preceding timeout
attempt took 60.123 seconds. These are observed audit-run timings, not a
controlled overall-routing-wave speedup benchmark; no 10-second limit or
electrical/fabrication gate was increased or relaxed.

The bounded native breadth pass at
`build/atx33-received-native-residual-breadth-20261005-lw/breadth.json` returned
33 unchanged after 91.099 seconds. Nearby candidates for the remaining SCL
launch are blocked by protected copper on other layers, including a wide
force lane and a long control track. A source-typed shared-ground leaf
reconstruction was received locally but produced no complete routing gain,
so it was not selected. These sampled refusals are not global no-path proofs.

A separate manufacturer-typed planar measurement-to-pour experiment produced
32 native opens, but its complete receipt
`build/atx34-to32-whole-typed-independent-receiving-20261005-ma/receiving.json`
**rejected** it. U10's positive input became connected to broad force copper
away from the declared RS1 pad-1 common region; the lower native copper model
proved a Kelvin bypass. The candidate also failed finite whole-chain/field
receiving deadlines. Neither a lower DRC-open count nor the exposed inherited
geometry grants Kelvin authority. The next sensing construction must use the
exact declared shunt pad and preserve isolation, rather than treating arbitrary
same-net filled copper as an interchangeable target. A coordinated source-typed
cell/force-contour replan may be required if no isolated launch can be received.

No BETA source, schematic, BOM, control board, commit, push, memory update or
browser/board tab was changed by this slice. Only the private accepted selector
advanced; rejected and no-gain proposals were left unselected.

## Search throughput and actual retained-shield obstruction: verified 33 to 32 (2026-10-06)

The private resume selector now selects
`build/atx33-ordinary-nonplane-power-corridor-20261005-mq/candidate/board.kicad_pcb`,
SHA256 `89352b7f00c26300600344aa8127814d91459ec7565024e4140b6db4eef4cf5a`.
The independently accepted final-code receipt is
`build/atx33-to32-final-search-pareto-receiving-20261006-pp/receiving.json`,
SHA256 `1e4fb47096d3b3575791b9fdb740e190ef95ce362bd36ec7c5b337d145177828`.
It accepts **33 to 32 native opens**, retaining **3 scored DRC / 558 raw
violations**, with no new native fault, Full50 failure, or new/worsened
current fault. Full50 remains 26 PASS / 11 N/A / 10 FAIL / 3 DECLARED;
typed native copper-cut checks remain 4 passed / 12 unknown / 0 failed.
All saved source families and the code epoch remained exact during receiving.
The receipt took 33.557 seconds across individually bounded stages; no
individual command timeout was raised above 10 seconds.

The requested maximum of **30 opens is not met**. This logical slice gains
one independently accepted closure, not three. Neither of the 31-open
proposals below is selected or credited as progress. This board is not fab
ready, and inherited current/Kelvin/pair debt is not qualified by this gain.

### What actually closed

The remaining ordinary threshold branch to the resistor gained a legal native
island port and used enabled non-plane routing copper on the PWR layer. The
private constructor positively excludes supply, sense, pair, clock and
pour-owned signals from this ordinary-scalar choice. Existing bus conductors,
part poses and power fills are immutable. Using this layer for an eligible
ordinary scalar is a private search policy in this trial, not a change to the
production default ordinary-layer eligibility or a permission for arbitrary
power/sense routing.

### Reusable search changes and their integration boundary

- `cec_field_search.PlanarSearchGuard` now has a conservative spatial broad
  phase and a bounded, plan-local integer-geometry memo. Every survivor still
  uses the same exact predicate. Neutral-net inactive guards no longer create
  accumulated collinear field-run state in the existing completion search.
- The multilayer maze supports explicitly bounded weighted ordering and
  canonical exact-terminal capture. Weighting changes search order, not
  legality or length limits, and carries no shortest-path certificate. The
  exact terminal tail must pass the complete native hop, length and
  accumulated field-run checks. Non-default search modes require a hard
  deadline of at most 10 seconds.
- `_lastmile_bridge` can explicitly choose a secondary 4--8 mm ordinary-via
  annulus independently for either endpoint. It no longer has to reuse a
  legal-but-dead local via seat in this explicit mode. Actual THT/barrel layer
  access is retained; class-sized ordinary barrels stay 0.6/0.3 mm.
- Optional neutral-state dominance discards a state only when a live state at
  the same XY/layer has no more distance or vias and enough cost advantage to
  cover the next turn. Just-arrived-via transition restrictions remain
  distinct. Active field/run-history searches do not use this merging.
- `RetainedShieldSearchGuard` derives bounded reservations from actual filled
  source GND at already shielded risky interaction samples. It screens new
  non-GND via antipads before route generation. An unfilled zone, stackup role
  or nominal GND layer is not shielding evidence. This conservative zero-loss
  pruning can reject a feasible solution; it is not a no-path, field-pass,
  ampacity or release proof. The saved/refilled full-board checker remains
  authoritative.
- Native Kelvin/force-cut search obstacles are compiled from clipped source
  copper and the exact declared common shunt aperture, with bounded identity
  and deadline checks. Arbitrary same-net pour contact does not grant a
  sensing branch Kelvin authority.

The planar-guard indexing/memo and inactive-state reduction are used by the
existing production completion path. Weighted ordering, terminal capture,
secondary annuli, neutral dominance, retained-shield pruning and compiled
force-cut experiments are generic bounded primitives exercised by private
portfolios here. They are **not yet integrated unattended discovery/replan
operators**. The constructors in `build/` do not establish that the entire
pipeline now autonomously resolves these cases.

### Measured speedup, not an overall-wave claim

`build/atx32-field-search-parity-benchmark-20261005-nw/benchmark.json` compares
8,000 actual-board field queries with all decisions identical. The original
predicate took 0.591434 seconds; indexing/memo took 0.223230 seconds, a
**2.649x predicate speedup**. Related-segment checks fell from 511,616 to
33,330. This is not a measured whole-wave speedup or improved closure rate.
Neutral dominance additionally pruned repeated maze states in bounded trials,
but neither its uncontrolled runtime observation nor an expired search proves
that a complete legal route exists or does not exist.

### Why the next two native closures were not accepted

A mixed endpoint-domain DET3V3 trial generated a complete 31-open proposal in
about 14 seconds:
`build/atx32-mixed-domain-det3v3-portfolio-20261005-pa/candidate/board.kicad_pcb`,
SHA256 `430e4d3d87dfd8a621ea538110a9c46caa0ae7ba2a2805bcfb987d67d9dadd5f`.
The independent whole-board receipt at
`build/atx32-to31-mixed-portfolio-independent-receiving-20261005-pe/receiving.json`
**rejects** it: native DRC and current/Kelvin comparisons do not regress, but
Full50 gains an aggressor/victim field-coupling failure. A new 0.6/0.3 mm via
at (46, 33) cuts filled In1 GND shielding between retained CAN_L copper and a
retained sense-force lane. Checking only the new signal's own field role
misses this retained-to-retained interaction. Nearby native-legal via moves
still fail the actual refilled shield test or cannot reconnect their native
incident paths. A PSON proposal similarly has a retained-CAN shielding loss
and a new long parallel interaction; its 31 opens are also not accepted.

The new retained-shield synthetic fixture reproduces the important causal
case: a via is legal by ordinary native clearance, its unrelated signal is
neutral, but its actual filled-plane antipad creates a field failure between
two retained nets. The new search guard rejects that via before generation;
the full receiver independently detects it when the guard is omitted.

The source-derived local reference/supply inventory also identifies pads
with no legal sampled launch: wide retained copper on B.Cu blocks one
reference return, and retained PWR-layer copper blocks its supply barrel.
Other controller/comparator launches have no outer-annulus seat at the
tested class/stub geometry. These are real multilayer placement/escape
conflicts, not evidence that six routing layers are insufficient. No source
bus was pushed aside, reduced in width, or credited with an invented lower
branch load to hide them.

Repeating the same static endpoint menus is not the next repair. The next
construction boundary is a **source-typed complete local-cell or paired
escape replan**, restoring every affected supply, immediate return,
measurement and output boundary before whole-board admission. The last
bounded shield-aware THRESH/DETECT port portfolio at
`build/atx32-shield-aware-output-port-portfolio-20261006-pm/probe.json`
produced no new candidate and is recorded as no gain, not a physical
impossibility proof.

### Final-code verification and unchanged controls

`build/atx-search-final-exact-regressions-20261006-pn.xml` records **320 passing
tests, zero failures and zero errors** in the focused escape-frontier, field
search, retained-shield, Kelvin-force separation, multilayer graph, landing
frame, snapshot and route-field gate suites. Tests cover renamed/rotated/back
transforms, actual filled-plane loss, native illegal terminal tails, bounded
parameter refusal, direction/via/length dominance, and field-history
preservation. The landing-frame helper was renamed so pytest does not
mistake it for an xunit setup hook; its 54 previously setup-errored cases now
actually run. An earlier broader interrupted batch is not reported as a
complete suite pass.

`build/atx-search-final-exact-controls-20261006-po/receiving.json` independently
replays archived PCIe2 and private Hub with 0 opens / 0 scored DRC, zero
generated copper, unchanged native copper and unchanged input families.
PCIe2 retains its inherited Full50 32 PASS / 12 N/A / 3 FAIL / 3 DECLARED;
private Hub retains 30 PASS / 17 N/A / 3 DECLARED. These exact controls are
regression evidence, not new fabrication or stack qualification.

No BETA source, schematic, BOM, control board, commit, push, memory update,
or new browser/board tab was changed. The verified private resume checkpoint
is 32, and the 30-open target remains explicitly unmet.

## Atomic complete-cell planning and early access refusal (2026-10-06)

**No new accepted closure in this slice. ATX remains 32 opens / 3 scored DRC
/ 558 raw violations. The below-30 goal is not achieved. No unfinished
placement snapshot was promoted to the resume selector.**

The unchanged safe board remains
`build/atx33-ordinary-nonplane-power-corridor-20261005-mq/candidate/board.kicad_pcb`,
SHA256 `89352b7f00c26300600344aa8127814d91459ec7565024e4140b6db4eef4cf5a`.
Final-code independent source replay is recorded at
`build/atx-atomic-cell-exact-source-receiving-20261006-qg/receiving.json`,
SHA256 `c955ed6daae20920107f7d68485dc25c798d5cd0c59892da09f25b3e2dd7bc1b`.
Native violations, Full50 failures, current debt, source/control families and
typed Kelvin evidence do not regress. Source is compared with itself, so
its progress/admission bit is correctly false; this is not a new repair.
Kelvin remains 16 expected / 4 checked and passed / 0 failed / 12 unknown.

### Reusable implementation, not board-coordinate repair rules

- `cec_joint_connection_search` chooses a compatible candidate for every
  obligation together: minimum-remaining-values ordering, forward checking,
  pair-conflict caching and bounded backtracking. It can undo an early short
  choice that consumes a future escape. A complete-selection oracle can
  reject a whole combination. Exhaustion, timeout, ambiguous callback or
  changed input exports no partial selection and no physical no-path claim.
- `cec_cell_escape_replan` derives device/unique-bypass ownership and every
  native contact before motion. It supports bounded unlocked SMD poses,
  guarded menus, real layer/width/drill-spacing conflicts, source-bound
  packets and rollback on failed construction. Supply widths use existing
  declared current authority per layer, never a new typical-current budget.
  Wide/grouped force copper, barrels and component definitions remain exact.
- `cec_measurement_leaf.plan_ground` owns only a sole thin manufacturer-typed
  ground departure up to its first native mesh junction. The earlier
  first-pad-segment cut could leave obsolete escape segments obstructing a
  moved cell. Forks, groups, wide conductors, interior taps and missing
  boundaries refuse. Every old component/surviving junction still needs
  restoration; this is not whole-GND-net rip-up/current authority.
- Mandatory local return-access failures now reject a pose before unrelated
  rerouting. Deferred obligations are explicitly not attempted, not failed
  routes or global impossibility proofs. Diagnostics identify actual layer,
  net and native conductor UUID. Search budget is apportioned among the
  obligations; a leaf cannot starve every supply/ground menu. Per-obligation
  timeout is recorded instead of escaping as an uncaught whole-cell error.

The new TLV7011 DBV pin contract is selected only by TLV7011DBVR/DBVT plus a
matching SOT-23-5 footprint. [TI SLVSDM5F, pin-functions table](https://www.ti.com/lit/ds/symlink/tlv7011.pdf)
identifies OUT=1, VEE=2, IN+=3, IN-=4, VCC=5. VEE is power_return, not an
assumed universal GND pin; ground-leaf ownership additionally requires its
actual native net to be GND. DPW/unknown packages, contradictory identities
and unpackaged family names do not borrow the table. No load rating or BOM
change was inferred from quiescent-current data.

### Actual native trials: why courtyard legality was insufficient

`build/root_atomic_cell_escape_trial_20261006.py` discovers the blocked source
owner and a downstream scalar-input IC from actual native connectivity and
manufacturer roles. Pose arguments are private trial parameters, not
production board/ref/coordinate dispatch. The initial downward whole-stage
trial `build/atx32-atomic-complete-cell-20261006-pr/probe.json` fails native
pad/courtyard checks against retained regulator/capacitors. The upward trial
`build/atx32-atomic-upper-cell-20261006-ps/probe.json` did not restore the
negative measurement departure. Neither result is a board no-route proof.

Later complete-cell poses pass pad/courtyard checks but fail immediate,
process-qualified return construction. The exact final-code trial is
`build/atx32-atomic-cell-exact-fast-refusal-20261006-qh/probe.json`, SHA256
`afe66d67bb14164b662448e74dc4c5117faf4c4b69e808e54b80131165ac7e08`.
Its first attempted return's native pad-centre obstructions are:

- PWR: locked 0.2 mm ATX_PWROK trace,
  `d9a81f68-8e48-43c9-b5ca-2401ac2dcd9c`.
- B.Cu: retained 6.535523 mm SENSE3V3_HI trunk,
  `9922cbef-0665-4468-bbc0-227fc54d4eb1`.

The existing return producer also rejects sampled dogbones on native
stub/barrel, pad-process and drill-spacing checks. These are all-layer
placement/escape conflicts despite legal courtyards. Early refusal defers
17 obligations and uses 0.684299 s of menu work. The earlier same-pose menu
at `build/atx32-atomic-complete-cell-fair-menus-20261006-pw/probe.json` spent
10.022248 s. This is approximately 14.6x faster rejection of this invalid
pose's menu, **not** a measured speedup of an accepted routing wave.

### Exact-code tests, controls and unfinished authority boundary

`build/atx-atomic-cell-exact-regressions-20261006-qe.xml`, SHA256
`d1cd47851e70e450730a80240571f4cb2bcdef1994bb6a56ffc4e888f7e7dfa7`, records
**412 passed / 0 failed / 0 errors** in 46.18 s. Coverage includes renamed
owners/nets, quarter-turn conflicts and ground departures, scarce future
escapes, full-selection rejection, forged/partial/stale construction,
callback mutation, bounded budgets, source widths and unchanged material.

`build/atx-atomic-cell-exact-controls-20261006-qf/receiving.json`, SHA256
`a0b4624265072e14707266229679cc3db02558b4a579e2dae0f99a4155f56b3f`, replays
PCIe2 and the private Hub without new copper, source-family changes or
field/pair regressions. Both remain 0 opens / 0 scored DRC. Inherited Full50
status remains PCIe2 32 PASS / 12 N/A / 3 FAIL / 3 DECLARED; private Hub
30 PASS / 17 N/A / 3 DECLARED. These are no-regression controls, not release.

**This is a source-typed construction/search slice, not a completed automatic
IC-pose rescue operator in unattended waves.** No ATX trial yielded a
complete source-partition-restoring selection. Pose generation must use
actual all-layer return/escape corridors, not only free front-layer space and
courtyards. Finished IC motion plus ground/measurement-leaf retirement still
needs an independent exact-pose/source-delta, placement, PI, rated-current,
field, pair and clipped-Kelvin receiver before wave admission. Calling the
planar measurement-leaf tier from a joint selector does not grant it
multilayer Kelvin-retirement authority. Do not bypass this boundary or count
an unfinished lower-open snapshot as progress.

No BETA board, schematic, BOM, source bus width/position, release gate,
commit/push, memory or browser/board tab was changed by this slice.

## All-layer pose access, exact component contacts and source-channel portals (2026-10-06)

**Accepted ATX delta in this pass: zero.** The selected immutable checkpoint
remains `build/atx33-ordinary-nonplane-power-corridor-20261005-mq/candidate/board.kicad_pcb`,
SHA256 `89352b7f00c26300600344aa8127814d91459ec7565024e4140b6db4eef4cf5a`:
32 native opens, 3 scored DRC, 558 raw findings. The target of at most 30 opens
was not met. No incomplete moved-cell snapshot was promoted or substituted
for the checkpoint. These are private construction/planning diagnostics,
not fabrication qualification or proof that the board cannot be routed.

### Generic construction/search changes

- `cec_escape_pose_frontier` projects actual foreign copper on **every**
  enabled layer, drill spacing, native courtyard obstacles and board bounds
  into manufacturer-ground-pad translation events. Free front-layer area is
  not sufficient. Cardinal complete-cell transforms preserve native relative
  geometry. Source-selected bypass followers may rotate and choose a closer
  actual supply-pin-relative seat instead of rigidly translating an obsolete
  capacitor position. Exact live courtyards and existing process-qualified
  immediate returns decide the proposals; finite proposal exhaustion is not
  a physical no-path certificate. No board/ref/coordinate dispatch was added.
- `cec_native_track_ports` generates strictly integer, actual straight-track
  centreline contacts. `cec_certificate_repair` independently resolves the
  native UUID/net/point and rejects off-centre or out-of-segment requests.
  A coordinate near a line is not a valid electrical attachment certificate.
- `cec_native_component_ports` derives alternative attachment points only
  from the exact source-seeded **existing native connected component**.
  Unrelated same-net islands and forged seed sets refuse. Original cut
  contacts remain receiving obligations. This does not grant whole-net or
  Kelvin-pickup ownership, thinner widths or new barrel authority.
- `cec_cell_escape_replan` uses those real component contacts for external
  connections while preserving existing per-layer load widths. An explicit
  non-plane power-role search option never includes actual ground planes;
  coupled connections cannot borrow the ordinary scalar menu. The ordinary
  default is unchanged. Whole-cell completion, not a partial menu, is required.
- `cec_native_via_frontier` proposes a finite set of new ordinary barrel
  sites from native all-layer copper and holes. Regional bounding/capsule
  proposal geometry avoids duplicating thousands of curve vertices before
  search. Every retained proposed site still passes actual native all-layer
  copper, edge, reservation, pad and drill-spacing checks. Proposal geometry
  is not an admission approximation or a fabrication/current waiver.
- `cec_measurement_leaf_bridge` keeps source-owned thin manufacturer-input
  leaf widths and named pickup contacts. Both new tracks and barrels must
  avoid acquiring unnamed same-net force material. Old exclusively owned
  channel suffixes can be **re-proposed new copper**, with new legal portal
  sites sought around their internal vertices as well as the original pickup.
  This is not credit for ghost copper or fictitious existing via access.
  Lease exhaustion refuses a query without converting it into a global
  no-path or successful reconstruction result. Multilayer measurement
  reconstruction still needs independent saved-source retirement receiving.
- `cec_rated_supply_detour` now funds a bounded portfolio of actual planar
  contacts on each retained source-cut component. It no longer has to
  reattach at an obstructed obsolete bend. It still retires only the exact
  small positively contracted full-load source scope, emits the unchanged
  full-load outer-layer width, preserves all old native boundaries/partitions,
  and uses its existing independent saved-board receiver. There is **no**
  new via, force-bus, inferred-load or arbitrary supply-retirement permission.

### Actual ATX outcomes and local visual evidence

`build/atx32-native-ground-court-frontier-20261006-qq/` found two complete
owner/bypass poses with legal courtyards and immediate factory-qualified
ground-entry menus. Earlier courtyard-only proposals collided with native
SIG2/PWR/B.Cu copper when their ground barrels were evaluated. Legal pose
planning is not a routed candidate.

For the first legal pose, exact component-port discovery changed the retained
bypass supply connection from zero choices to **48 native-guarded choices**.
The local supply menu has three choices and all three ground obligations have
one choice each. Both original measurement leaves and the downstream
comparator connection remain without a complete admitted reconstruction.
This is additional planning capability, **not** a decrease in opens or a
measured speedup of an accepted wave.

Relevant finite receipts:

- `build/atx32-native-component-channel-cell-20261006-qx/probe.json`:
  legal physical pose, 48 retained supply alternatives, incomplete selection.
- `build/atx32-region-native-source-portal-cell-20261006-qz/probe.json`:
  real all-layer portal proposals and two positive-input surface escape
  attempts; middle routes refused. No candidate saved as a completed result.
- `build/atx32-native-measurement-reference-replan-20261006-ra/probe.json`:
  retiring the sole positive measurement leaf crossing the source owner's
  ground/reference path allowed proposing a reference strap, but restoring
  that measurement channel with the IC left in place failed. A partial
  reference-only improvement is not admissible.
- `build/atx32-native-portal-scalar-breadth-20261006-rd/`:
  bounded DETECT/DET3V3 search with exact interior contacts, native new-via
  portals and retained-shield checks found no complete candidate.
- `build/atx32-authorized-power-role-cell-20261006-rh/probe.json`:
  including the factory-authorized non-plane power role did not complete the
  moved cell. Neither existing power buses nor ground planes were changed.
- `build/atx32-reference-exact-component-rated-preclear-20261006-rj/receiving.json`:
  source-owned full-load 3.3 V branch preclear with real retained-component
  contacts still found no legal planar reconstruction. The other owner's
  conflicting measurement copper cannot borrow rated-supply authority.
- `build/atx32-source-channel-event-deep-cell-20261006-rl/probe.json`:
  separate bounded up-to-10-second deep leases for the three empty obligations,
  including internal source-channel event portals and the non-plane power
  role, still yielded no complete partition-restoring selection. Repeating
  the short-wave search without changing the source-derived escape topology
  is not a demonstrated route to progress.

Native KiCad SVG/PNG local per-layer inspections are saved under
`build/atx32-native-cell-layer-review-20261006-rc/` and
`build/atx32-native-reference-cell-layer-review-20261006-rk/`. Their receipts
bind the exact MQ source hash. These are plots of actual saved native copper,
without refills or synthetic FEM slabs. The sources did not change, and no
browser/board-view tab was opened.

The local obstruction is not simply the number of available layers. Wide
protected force trunks shadow through-via sites, while surface sense leaves,
ground meshes and adjacent device lands constrain the escape channels.
Separately legal IC, capacitor, ground and signal menus are insufficient;
their complete combination must preserve every original connected component
and pickup. The next construction authority boundary remains whole-cell
escape/leaf reconstruction plus independently replayed IC motion, source
retirement, local PI, current, field, pair and clipped-Kelvin checks. The new
pose/frontier/measurement tier is **not yet an automatically admitted IC-pose
repair in unattended waves**. Do not claim that this pass completed it.

### Exact final-code validation

`build/atx32-exact-component-portal-final-regressions-20261006-rn.xml` records
**491 passed, 0 failed, 0 errors**, in 102.24 seconds. It includes renamed and
quarter-turned source contacts, actual inner-layer ground obstacles, follower
placement against actual supply pins, qualified ground construction, exact
current widths, independent rated-detour receiving, unrelated same-net island
rejection, forged/off-centre contacts, incomplete/stale selection, rollback,
ordinary non-plane policy, source retirement and inherited release boundaries.

`build/atx32-exact-component-portal-final-controls-20261006-rm/receiving.json`,
SHA256 `502cf80b8b909569ee58442288153d316def2d65263f21fb8add883c42a36c18`,
replays PCIe2 and the private unadmitted Hub with unchanged native copper,
source families and code epoch. Both remain 0 opens / 0 scored DRC. Inherited
Full50 remains PCIe2 32 PASS / 12 N/A / 3 FAIL / 3 DECLARED and private Hub
30 PASS / 17 N/A / 3 DECLARED. These are no-regression controls, not fabrication
release claims or accepted reroutes of those boards.

`build/atx32-portal-final-source-receiving-20261006-ro/receiving.json`, SHA256
`582abc533787ecec55a8976c081053481c8e58bf9cc13ce300e2e23301680600`, freshly
checks unchanged ATX MQ against itself using final code. It confirms 32 opens,
558 raw findings, no new native/Full50/field faults, exact preserved source
families and no measured progress. Typed clipped-Kelvin remains 16 expected,
4 checked/passed, 0 failed, 12 unknown. Self-replay correctly has
`accepted_private_receiving=false` because no improvement was made.

This pass changed generic pipeline code, tests and diagnostics only. No BETA
PCB/schematic/BOM, source bus geometry/rating, release rule, selector,
commit/push, memory, installation or dashboard tab was changed. No new
unfinished routing wave was left running by this pass.

## Source-owned joint returns and scalar reconstruction (2026-10-07)

**No admitted open-count gain in this pass: ATX remains 32 opens / 3 scored
DRC / 558 raw findings.** No private incomplete pose was promoted. The safe
source remains `build/atx33-ordinary-nonplane-power-corridor-20261005-mq/candidate/board.kicad_pcb`,
SHA256 `89352b7f00c26300600344aa8127814d91459ec7565024e4140b6db4eef4cf5a`.
The directory name is historical; freshly received native metrics, not its
name, establish the 32-open state. The safe selection JSON was not changed.

### Reusable changes, not reference-specific placement rules

- Ground planning now derives a directed entry from the actual uniquely
  selected bypass and manufacturer-typed low-power owner. Its capacitor must
  retain an independently proven immediate return within the existing 0.8 mm
  limit. A short visible owner-ground link may use that entry; a ground-strapped
  reference/address input may use the same package's typed ground in turn.
  Every required root/peer is a separate mandatory obligation. Fresh native
  construction rejects changed assignment, loose worker-authored bounds,
  missing links/barrels and floating dependency cycles. This is not a
  switching-regulator layout policy or a ground/current qualification waiver.
- A source-selected capacitor can now connect to a nearby **real retained
  barrel** through guarded full-class surface copper. Existing barrel UUID,
  dimensions, position, net and lock remain unchanged; no duplicate hole is
  created. The route must fit the unchanged immediate-return budget, and the
  barrel must pass actual all-layer copper, drill, edge and process checks.
  Native proof/insertion exceptions remove trial links, not source copper.
- IC motion can now reconstruct an exclusive thin unlocked output-to-input
  link wholly owned by included moving devices. Manufacturer roles, actual
  endpoint identity, native-contact linearity and bounded scope are required.
  Fixed third-party endpoints, shared branches, grouped/locked copper,
  protected current domains and coupled pairs do not acquire this permission.
  The whole-source partition check still demands restoration before a complete
  construction can be proposed. No board/refdes/coordinate special case is in
  this rule; the experimental pose JSON is diagnostic input only.
- Source-leaf inference recognizes multiple exact endpoint-linear segments
  inside one elongated SMD land as one departure, while retaining fork, gap,
  group, width, zero-edge/cycle and unowned-contact refusals. A ground dogbone's
  overlapping retained barrel is a fixed boundary, never retireable copper.
  A tiny supply leaf separately requires the unchanged **full rail** current
  contract and actual rated width; no guessed per-IC load is substituted.
- Stationary owner witnesses no longer cause unrelated measurement/ground
  departure retirement when only their selected bypass moves. INA238 VBUS
  pin 8 is distinguished from shunt inputs 9/10, following TI's INA238
  datasheet Table 4-1; it cannot borrow thin shunt-leaf authority. Existing
  unrouted measurement lands are explicitly recorded as debt, not completed
  routes. Internal two-land measurement boundaries follow their actual final
  owner lands, not obsolete absolute source coordinates.
- Pose proposals include continuous native courtyard boundary events, rather
  than only cardinal radial seats, for coordinated owner assemblies and
  selected capacitor followers. These are read-only bounded proposals, not
  placement/routing admission. Actual native courtyard and ground checks
  remain necessary; no bus moves or automatic outline enlargement follow.
- Ground menus run in source-role dependency order: immediate roots, owner
  ground, then reference/address links. The experimental deep-search driver
  now respects upstream refusal and does not fund unattempted dependent
  routes or erase untouched ground domains.

### Actual ATX findings and finite trial outcome

The old output-to-input segment between two included moving devices was being
treated as a fixed obstruction. Source-owned scalar reconstruction now removes
that obsolete segment only while creating a mandatory replacement obligation.
Three selected capacitor returns can each reach the same retained qualified
barrel through short guarded links without adding vias. This is **local
constructability**, not three closed opens on an admitted board.

`build/atx32-joint-source-owned-cell-final-construction-20261007-v/probe.json`
binds the unchanged source and final production code. It produces one choice
for each of the three immediate capacitor returns, then refuses the comparator
ground obligation in 0.767 s. The comparator's proposed ground land conflicts
with the protected `/SENSE5V_HI` filled copper; its barrel is also shadowed by
the actual back-layer force trunk. Native F/B inspection is stored under
`build/atx32-joint-source-owned-scalar-layer-review-20261007-q/`. This is real
saved KiCad copper, not a FEM plotting slab. That pose is not route-ready and
the entire atomic selection is rejected. Dependent measurement, supply and
signal obligations are explicitly deferred, not claimed impossible.

An earlier diagnostic incorrectly spent roughly 100 additional seconds
deepening deferred scalar/measurement menus after the upstream ground refusal.
That driver defect is repaired; the final trial exits before doing those
searches. This is avoided work on a rejected pose, **not a controlled
whole-wave speedup or faster accepted-board routing measurement**.

Another earlier pose placed a new output land against a retained old ground
barrel. Native save/reload identity correctly refused KiCad's resulting net
relabel. The serializer/identity guard was not relaxed. All retained barrels,
source power geometry, current loads and minimum clearances remain protected.

### Final-code regression and independent controls

- `build/atx32-joint-source-owned-cell-final-regressions-20261007-r.xml`:
  **558 passed / 0 failed / 0 errors**, 85.94 s; SHA256
  `71767666c2ce2af8b9d00528661809bac207fc57d63d8fd44e1e5c18a2617bf5`.
  It includes renamed/quarter-turned scalar ownership, long-land native contact,
  retained-barrel reuse and negative process/inner-copper/hole tests, directed
  ground dependencies, unchanged-load supply scope, stationary owners,
  private rollback and existing independent routing/current/field checks.
- `build/atx32-joint-source-owned-cell-final-controls-20261007-s/receiving.json`:
  SHA256 `91bdd076923a9a7f4779a3d0dd6b7c3b0cc0c9490df51c140f86f2a7f7459ed1`.
  PCIe2 fab-review archive and the private **unadmitted** Hub remain
  0 opens / 0 scored DRC with exact native copper/source families and unchanged
  final code. Their inherited Full50 results remain respectively 32 PASS /
  12 N/A / 3 FAIL / 3 DECLARED, and 30 PASS / 17 N/A / 3 DECLARED. This is a
  no-regression replay, not a new fabrication-release claim.
- `build/atx32-joint-source-owned-cell-final-source-receiving-20261007-t/receiving.json`:
  SHA256 `5f0320e0e840111028d10f8dcd2c232d155abfe97659a75192d57b34a3c979eb`.
  Exact source self-receiving confirms 32 opens / 3 scored DRC / 558 raw,
  unchanged settings/sidecars/pads/fills/partitions, no new native/field/Full50
  faults, and preserved source/control families and final code. Typed clipped
  Kelvin remains 16 expected / 4 checked and passed / 0 failed / 12 unknown.
  It correctly reports no measured progress and no accepted new candidate.

Whole-cell motion is still a **private construction tier**, not an automatic
admitted unattended-wave repair. Independent saved-board receiving for changed
IC poses and source-measurement/scalar retirement, followed by current, local
PI, field, pair and Kelvin receiving, remains required. Complete restoration of
every affected supply/signal/measurement connection is still unsolved for the
tested pose. Repeating that rejected pose is not a plan for closing ATX.

This pass changed generic scripts/tests and private diagnostics only. No BETA
board/schematic/BOM, accepted source geometry/load, release gate, selector,
control board, commit/push, memory, installation or dashboard tab was changed.
No new unfinished routing wave was left running.

## Surface-aware source-owned bypass search and churn repairs (2026-10-07)

### Accepted checkpoint and actual progress boundary

The ATX selection remains
`build/atx33-ordinary-nonplane-power-corridor-20261005-mq/candidate/board.kicad_pcb`,
SHA256 `89352b7f00c26300600344aa8127814d91459ec7565024e4140b6db4eef4cf5a`:
**32 opens / 3 scored DRC / 558 raw DRC**. This slice closes **no additional
admitted opens**. The selector is unchanged and ATX is not fabrication-ready.
The raw inventory includes 199 silk overlaps, 199 silk-over-copper findings,
129 library-footprint findings, 24 silk-edge findings, four hole-clearance
findings, two dangling tracks and one dangling via; it is not 558 copper shorts.
Full50 remains 26 PASS / 11 N/A / 10 FAIL / 3 DECLARED. Typed clipped Kelvin
remains 16 expected / 4 checked and passed / 0 failed / 12 unknown. Existing
current and release debts have not been qualified away.

### Generic changes retained by this slice

- Surface placement and continuous translation events now use actual native
  stationary lands, tracks, filled zones, protected power outlines, copper
  graphics and applicable placement keepouts. Copper on a different layer
  does not become a fictional body keepout; the separate return producer
  still checks a barrel on every real copper layer. Unfilled/unknown native
  geometry fails closed. Ground-zone refill exclusion must be explicit and
  carries a later native receiving obligation; it does not waive power pours.
- Rectangular land translation uses a bounded boundary-segment Minkowski
  sweep, including holes, rather than a whole-obstacle convex hull or pad
  circumscribed circle. Only individual swept segments are convex-hulled to
  avoid invalid floating-point quadrilaterals. Useful narrow concavities and
  clearance pockets remain available for exact native follow-up checks.
- Owner poses receive separate bounded grants instead of the first pose
  spending the complete portfolio. Capacitor ground attempts are bounded
  independently. Fixed copper is warm only within one follower search and is
  rebuilt after each accepted capacitor. Current pad shapes are re-queried
  after quarter turns. No process-global stale native-geometry cache is used.
- Followers first try their actual proposed native seat and then real
  supply-pin-relative cardinal and courtyard/copper boundary events. Failure,
  timeout and unexpected construction exceptions restore every selected
  follower, including earlier successful moves and temporary rotations.
- A moved capacitor may retire only its source-selected exclusive thin ground
  stub or its full-rail-rated exclusive supply stub. Ownership is rederived
  from the manufacturer's actual supply pin, unique bypass assignment and
  native contact topology. Shared forks, interior taps, grouped/wide copper,
  root barrels and unqualified current scope remain retained/refused. Existing
  vias are fixed boundaries, never disposable stubs. No guessed per-device
  load, whole-net copper waiver or board/refdes/coordinate rule is introduced.
- Native capacitor-library identity supports renamed imported capacitors while
  retaining legacy C-reference behavior. A unitless resistance value is not
  sufficient capacitor identity. A stationary IC is an assignment witness:
  its good existing rated supply feed, as well as its unrelated measurement
  and ground departures, is no longer retired merely because a bypass moves.
  Its stationary pads remain real obstacles to moving components; an
  assignment witness is not an unplaced follower excluded from the surface
  collision snapshot. This caller-scope boundary has a regression test.
- After final follower poses are chosen, the owner frontier reconstructs a
  fresh private board from the immutable source and the final freshly derived
  cuts. It no longer validates the final pose against an earlier over-cut or
  under-cut draft. Complete native contact restoration remains mandatory.
- Cross-board replay exposed a numerical false rejection on the archived
  PCIe2 board: two valid 0.200 mm pad/ground-track gaps became 199996 nm after
  both polygon envelopes received their 2 nm guards. Only guard-band
  PAD/track/via/arc queries may use the actual native collision check at the
  full unchanged clearance. Protected zone outlines, holes and rule areas do
  not acquire this fallback. Quarter-turned tests accept the exact floor and
  still reject genuinely 1 nm and 100 nm undersized gaps.

These changes are bounded construction/proposal helpers, not an independently
admitted automatic changed-IC wave operator. They are not registered as a
successful unattended repair just because a private pose looks legal.

### Measured private ATX construction result

The old occupied pocket is now rejected by actual same-face copper screening
in approximately 0.82 s, before routing. Intermediate nominal 10 s portfolios
examined five owner poses instead of one in each of four quarter-turn runs
after warm local snapshots and fair grants were added. This is measured search
coverage on those intermediate diagnostics, not a fivefold whole-wave speedup
or a benchmark of every later code change.

A newly ground-access-qualified pose was found in approximately 3.26 s.
Fresh final-code complete construction is recorded in
`build/atx32-surface-owned-bypass-final-construction-20261007-bb/probe.json`
(SHA256 `9b52c4bed84d5f9aa74f2aa0fa477e0b3cea665a916d419f0a23c54c8fc2a66c`).
Its mandatory domains have:

| Obligation | Choices | Outcome |
| --- | ---: | --- |
| Three immediate/shared ground obligations | 1 / 2 / 1 | Native proposals available |
| Selected local supply connection | 3 | Native proposals available |
| Capacitor's rated supply rejoin | 48 | Actual retained source component required |
| Two source measurement pickup restorations | 0 / 0 | Still blocked in the bounded searches |
| Comparator-output boundary restoration | 0 | Still blocked in the bounded search |

The full atomic transaction is rejected: there is no new routed candidate and
no selector/admission change. The sense pickups are actual retained front-layer
track junctions, not THT lands or existing vias that can silently provide other
layer access. Their all-layer barrel shadows and exact source pickup apertures
remain protected. The comparator has legal endpoint seats but its tested
middle searches do not complete a path. Empty finite menus or a graph reaching
its search window boundary are **not physical no-path proofs**.

Source inspection also confirms each tested INA181 true ground pin 2 is already
connected to the saved GND-plane mesh, while its ground-strapped reference pin 5
is isolated. Future stationary-owner reconstruction must preserve that exact
existing component and explicitly repair the isolated reference; it must not
waive immediate capacitor return rules or demand redundant new barrels just
to rediscover a retained source connection. This source-return-aware repair
and independent receiving for owned capacitor-stub retirement are not declared
completed by this slice. Alternatively, coordinated IC motion still requires
solving every original sense/scalar escape before a pose can be accepted.

### Final-code evidence and scope controls

- `build/atx32-surface-owned-bypass-final-regressions-20261007-ax.xml`:
  **634 passed / 0 failed / 0 errors**, 82.28 s; SHA256
  `58afde3b974cd3da338948bfab3e889235dab92f1c5c09863d2700f9f2d7bc77`.
  The focused native geometry, source ownership, private rollback, scheduling,
  current, field, pair, pose and routing-receiving suite includes the new
  renamed/quarter-turned capacitor supply/ground, shared-fork/barrel refusal,
  fixed-source feed, cache-epoch, final-material rebuild and exact-floor tests.
- `build/atx32-surface-owned-bypass-final-controls-20261007-ay/receiving.json`:
  SHA256 `72f02f31cb551841b3c6c0de4e7e06a937d64e451bec346e248cf0fb40965496`.
  PCIe2 archive and the private **unadmitted** Hub retain 0 opens / 0 scored
  DRC, exact native copper/source families, identical physical pair/field
  evidence and unchanged final code. No new routes/vias are emitted. Their
  inherited Full50 and Hub's 122 contour-review findings remain unchanged;
  neither replay confers new fabrication-release authority.
- `build/atx32-surface-owned-bypass-final-native-cross-replay-20261007-ba/replay.json`:
  SHA256 `903b305be9711669717a785b949a9782b24e804125a181215726c019fc4f7ffc`.
  The new surface/source-cut event APIs themselves are replayed on actual
  manufacturer-typed owners selected from all three saved boards, not only
  exercised through old zero-open routing helpers. Source/native/code bindings
  remain exact and all three source surface screens pass. Shared/non-linear
  PCIe2 leaves and Hub interior-barrel contacts stay refused/retained. Hub and
  ATX produce finite event menus; PCIe2 motion does not borrow a new retirement
  policy merely to make the replay return a pose. This is not cross-board
  successful routing or release qualification.
- `build/atx32-surface-owned-bypass-final-source-receiving-20261007-az/receiving.json`:
  SHA256 `e6bfd82b719b5a9c445bb4db4c023111b03aeb3fb5f4e31ab1b7781f9e27711f`.
  Full native DRC/Full50/current/pair/field/Kelvin self-receiving confirms the
  accepted 32-open source, exact settings/sidecars/pads/fills/partitions,
  unchanged source/control/code families, and no new native/field/Full50
  failures. It explicitly reports no measured progress and no admitted new
  candidate; zero failures in self-receiving are not fabrication readiness.

Only generic scripts/tests, this report and bounded private diagnostics were
changed. No BETA schematic/BOM/board, accepted source load or geometry,
selector, control board, release gate, installation, memory or dashboard tab
was changed. Changes remain uncommitted in the existing dirty worktree. No
unfinished worker or new blind unattended wave is left running by this pass.

## Accepted multilayer closure and stationary access follow-up (2026-10-07)

### Actual accepted progress: 32 to 31 opens

At this checkpoint the private ATX selector pointed to
`build/atx32-multilayer-field-portfolio-20261007-bi/candidate/board.kicad_pcb`,
SHA256 `5709f765dc4853a307278f95602c7e72e59eef3a2b9c56c9f66f5ee93804517e`.
The preceding 32-open source remains unchanged. The new candidate closes
`/DET3V3` between the MCU and comparator through a bounded multilayer native
port search. **This request admits one additional closure, not a bulk sweep.**

| Saved-board result | Source | Accepted private candidate |
| --- | ---: | ---: |
| Native opens | 32 | 31 |
| Scored DRC | 3 | 3 |
| Raw DRC | 558 | 558 |
| Full50 PASS / N/A / FAIL / DECLARED | 26 / 11 / 10 / 3 | 26 / 11 / 10 / 3 |
| Typed Kelvin passed / unknown | 4 / 12 | 4 / 12 |
| Existing current-width fault objects | 109 | 109 |

The final-code independent receipt is
`build/atx32-to31-final-code-receiving-20261007-bx/receiving.json`, SHA256
`388ecefc89137afb248389649bd9488af5fb53acd8c4835a52f82a961b0c90a4`.
It accepts private progress with no new native DRC identities, Full50 failure
identities, field blockers or new/worsened current debt. Saved native pair,
terminal partition and clipped Kelvin evidence is preserved. The 25 added
native items are 20 tracks and five vias; their route-craft check passes.
No existing track, via, pad, component pose, board dimension or power fill is
changed. Two GND-zone fills change only through the independently replayed
native ground refill. This is not an all-original-items-exact claim.

At this checkpoint the <=30-open intermediate target was unmet by one connection. Existing
Full50, current, pair and unresolved Kelvin debts remain real. **ATX is not
fabrication-ready.** No BETA source board/schematic/BOM is replaced by this
private selection.

### Generic search changes, without a board-specific placement recipe

- Complete native field preflight includes the endpoint portal copper as well
  as the connecting route. A new portal is not installed first and then used
  to hide its effect on retained-to-retained shielding. Planar searches use
  the same field guard as their connecting legs. This private workbench
  exercises the existing bounded weighted/capture/multilayer primitives; it
  is not a newly registered unattended discovery operator.
- Stationary source-owned branch repair funds individual isolated supply or
  reference tasks before their joint cohort. A ground-only repair need not
  reserve an unrelated supply corridor that it will not construct. Both the
  source-verified owner ground and assigned bypass remain explicit choices.
  Ownership, native boundary restoration and receiving are unchanged.
- Orthogonal detour menus can shift both cross axes and include both departure
  orientations. They canonicalize redundant forward-collinear vertices and
  reject immediate backtracking, so the finite 96-path budget funds distinct
  physical proposals. Quarter-turned renamed fixtures cover the new tier.
- Rejected local geometric queries share one exact private source-minus-leaf
  snapshot per proposal, with native binding checked after each query. Actual
  construction reloads the immutable source and rechecks that binding. No
  index is carried across a constructed trial or moved pose. A mutating-query
  regression proves the warm snapshot cannot supply admission authority.

Final source replay
`build/atx31-warm-single-port-branch-access-20261007-bw/receiving.json`
checks 111 guarded paths from two private retired snapshots, versus the prior
61-path trial that never reached its maze. The final replay reaches one native
maze too, but every proposal remains blocked and **it closes no further open**.
Menus and scheduling changed together; this is not a controlled whole-wave
speedup measurement or a physical no-path proof.

### Remaining causal barriers found, rather than another blind wave

Native inspection confirms that the two isolated INA181 reference returns
have already connected true-ground pins, but their direct same-face paths
cross either a source measurement branch or a small shared rated supply
branch. The supply is still sized for the unchanged approved aggregate
0.2048376 A contract, including the existing margin; no guessed per-IC load
or force-bus retirement is authorized.

The existing rated preclear can include the small degree-two continuation and
restore its real external pad/junction boundaries. Nevertheless the tested
planar reconstruction does not find a path. Pad-centre reference vias are also
blocked on B.Cu by the existing wide power bus. One first-layer report names
an ordinary comparator trace, but removing that trace in a private diagnostic
reveals the retained B.Cu bus underneath: clearing only the first reported
obstacle is insufficient. That bus is retained, not rerouted to make a via fit.

`build/atx31-rated-reference-source-preclear-20261007-bs/probe.json` and
`build/atx31-reference-via-ordinary-preclear-20261007-bt/probe.json` preserve
these refusals. Both yield **no new candidate**. Independent I2C-clock and
threshold trials likewise fail at endpoint layer access; they are not new
admissions. The next construction needs a complete source-owned local cell
replan or a different independently legal endpoint access, with all affected
measurement, output, supply and ground obligations restored atomically.

### Final-code regression and immutable controls

- `build/atx31-final-generic-regressions-20261007-ca.xml`: **769 passed, zero
  failures/errors**, 115.73 s; SHA256
  `520e21ace653ee589b2df873431bce6b9b9506ae45f61f9e98b187774f0f72af`.
  This is the focused 28-module geometry/search/current/field/receiving suite,
  not the entire repository suite.
- `build/atx31-final-generic-controls-20261007-bz/receiving.json`: SHA256
  `2b7b9947106655ee8b0aee7d4b038c34174cdb86fd55aef84f5a8a9af22c9392`.
  PCIe2 archive and the private unadmitted Hub retain zero opens and scored
  DRC, exact native copper and source families, identical pair/field evidence
  and unchanged final code. No new control routes or vias are emitted.
  Inherited PCIe2 pair debt and Hub's 122 contour-review findings remain
  unqualified; their replay does not promote either board to fabrication.

The accepted 31-open checkpoint and its final-code evidence were recorded in
`build/atx-stall-selected-safe-checkpoint-20261005-je.json`. Generic source/tests
and this report remain uncommitted in the existing dirty worktree. No dashboard
board tab, installation, memory entry or fabrication release was created. All
bounded jobs from this pass have completed; no blind wave is left running.

## Accepted fixed-land support closure and composed receiving (2026-10-07)

### Measured progress: 31 to 30 opens

The current private ATX selection is
`build/atx31-fixed-pivot-exact-replay-20261007-dw/candidate/board.kicad_pcb`,
SHA256 `e1a06204fae8e2245ddd4e1d6aea8f9bab748c4130e170b0e0ac3f4db0716c12`.
The immutable preceding 31-open source remains unchanged. This slice accepts
**one additional closure**, `/HUB LINK + CAN + STACK/DETECT`, and meets the
interim <=30-open target. It is not a bulk closure or fabrication signoff.

| Independent saved-board result | Source | Accepted private candidate |
| --- | ---: | ---: |
| Native opens | 31 | 30 |
| Scored DRC | 3 | 3 |
| Raw native DRC findings | 558 | 558 |
| Full50 PASS / N/A / FAIL / DECLARED | 26 / 11 / 10 / 3 | 26 / 11 / 10 / 3 |
| Existing current-width fault objects | 109 | 109 |
| Typed Kelvin passed / unknown | 4 / 12 | 4 / 12 |

The full independent receipt is
`build/atx31-to30-independent-receiving-20261007-eb/receiving.json`, SHA256
`6d540ca131aab7026e8ed36bf9fddf172208032dffea8b2f645e236a9d5acf8d`.
It accepts measured private progress in 44.67 s, with zero new native DRC
identities, Full50 failure identities, field blockers or new/worsened current
faults. Every prior native terminal partition and received physical pair,
current-path and clipped Kelvin obligation is preserved. Existing unknowns
are not converted to passes. **ATX is still not fabrication-ready.**

### Source-defined construction, not a board-coordinate repair rule

Two short 0.2 mm front-layer ordinary `+3V3` branch segments are retired and
rebuilt around an independently checked fixed-land support pivot. Their
actual external pad/junction boundaries are restored, at the unchanged
approved aggregate 0.2048376 A contract including the existing margin. No
guessed local load, thinned force conductor or moved force bus is accepted.

The selected two-terminal support is R7. Its connected `/DETECT_SENSE` land
stays exactly at (43.015, 35.4891) mm; a 180-degree fixed-land pivot presents
its previously orphaned DETECT land to a legal escape. This is a source-bound
private construction example, not an R7/refdes/coordinate clause in a generic
engine. The footprint definition, pad nets and non-pose metadata remain exact;
only independently authorized pose and bounded readable-field changes are
replayed. The final accepted chain lists its explicit phases in
`build/atx31-to30-fixed-land-phases-20261007-dz.json`.

A geometry-first native pilot finds the escape that the tested early
field-pruned searches did not. The **complete** proposed copper, including
portals and its changed local source, must separately pass native/refilled
field and physical checks before construction, and then full saved-board
receiving. This does not waive coupling rules or prove every early pruning
decision is wrong. The pilot is exercised by the private portfolio; automatic
discovery/integration of that search policy is not claimed complete.

Original board dimensions, protected force geometry, source loads, BETA
schematic/BOM/source boards and immutable PCIe2/Hub controls are unchanged.
Two ground fills change only through independent source-plus-construction
native refill replay. One support pose and two ordinary supply tracks change
under their positive typed receipts; an all-original-items-exact claim would
be false.

### Generally reusable repairs and their actual integration boundaries

- Native port menus preserve ranked choices while funding distinct physical
  exits and real layer-access categories. Their limits are explicit and they
  neither merge nearby contact coordinates nor invent layer access. Renamed,
  rotated, layer-diverse and exact-coordinate fixtures cover the new helper.
- Opt-in field-search dominance preserves layer/heading/run-origin state and
  compares cost, path length and via use. It never erases the field guard's
  run-length memory; the neutral search default is unchanged. This is a
  bounded primitive, not a measured whole-wave speedup or unattended operator.
- Rated supply-detour proposals run a complete retained-junction craft check
  before choosing a geometric path. A failed acute source join spends the
  next finite alternative instead of constructing a predictably refused path.
- Native route-craft junction inventory recognizes <=1 um endpoint aliases
  only when actual same-net, same-layer conductor shapes contact. Whole
  clusters must fit that bound: no transitive alias growth, snapping or source
  topology mutation. Hidden third branches still retain their true degree.
- `cec_additive_portal_compaction.py` is integrated into the common production
  native-additions save path. It can remove only newly added ordinary copper
  exactly covered by retained equal/wider collinear copper and newly added
  single-layer, non-transition barrels. Native before/after partitions of all
  remaining same-net terminals/conductors must be equal before atomic removal.
  One-nanometre offset, larger width, old/grouped/power-owned items and a via
  bridging separated same-layer pieces are refused or retained. Missing fill
  evidence, deadline or any failed partition proof leaves the board unchanged.
- The typed source-cut chain now composes an **already independently received**
  fixed-land orphan-support pivot with rated branch reconstruction. Whole
  original-source replay permits only those recorded poses and explicit cuts;
  hidden component motion, metadata changes, repeated pose owners or untyped
  connected-land translation remain refused. Geometry/field/route-evidence
  consumers bind the same exact source, candidate, code and lease mode.
- Explicit per-phase leases keep each independent phase and whole-chain replay
  at <=10 s. The default aggregate lease is unchanged; opt-in work is finite
  (at most four phases plus replay, <=50 s). This two-phase chain has a 30 s
  total bound. Separate full-board receiving still checks every release gate.

### Refusals that prevented false progress

An unnecessary new via beside the retained THT connector had only a front-layer
branch; independent saved DRC caught it. The common portal compactor removed
that new redundant via and its covered new stub, not retained source copper.
An earlier constructor rotated hidden footprint metadata with native `Rotate`;
exact fixed-land receiving rejected it. The corrected private constructor uses
the same `SetOrientationDegrees` plus fixed-pad translation as the production
pivot constructor, and passes exact footprint replay. No receive exception was
added to accept the bad metadata. Another whole-chain trial exhausted its
aggregate replay deadline and was not selected; opt-in independently bounded
phase leases were then tested before the accepted full replay.

Small ground/reference, I2C and threshold trials still find blocked endpoint
access. Fine planar searches fail quickly without a legal escape, so simply
adding CPU time to the same menus would not address the observed barrier.
These finite failures are not physical no-path proofs. Next construction must
replan complete source-owned local cells and pair escapes while preserving
every affected sensing, supply, ground and scalar obligation atomically.

### Final-code tests and immutable board controls

- `build/atx30-combined-generic-regressions-20261007-ec.xml`: **990 passed, zero
  failures/errors/skips**, 166.56 s; SHA256
  `bac0411fea6e24d028d59068345d1f23c6721ca26f92d54687a9ff33ac9d4449`.
  This is the focused 35-module native geometry/search/current/field/typed
  receiving suite, not the entire repository suite.
- `build/atx30-cross-board-controls-20261007-ed/receiving.json`: SHA256
  `44dc575025a9042e9ed9f76dceac191f40847c5de49ece4707bf8952729d9be3`.
  Both the PCIe2 fab-review archive and private unadmitted Hub retain zero
  opens/scored DRC, exact native copper/families and unchanged pair/field
  evidence. No new control joins, tracks or vias are emitted. PCIe2's inherited
  pair refusal and Hub's 122 contour-review findings remain unqualified.

The 30-open selector and evidence are recorded in
`build/atx-stall-selected-safe-checkpoint-20261005-je.json`. The current BETA
source is not overwritten. Source/tests/report remain uncommitted in the
existing dirty worktree. No installation, memory edit or fabrication release
is performed; no dashboard tab is automatically opened. All bounded receiving
and test jobs have completed, with no blind unchanged wave left running.

The passive dashboard review is
`http://localhost:8090/?id=pass-atx30-received-fixed-land-review-20261007-ee-atx-24pin-rev3-c326cb19c4`.
Independent publication binds the accepted board SHA above and measures 30
opens, 3 scored DRC and 80 inherited contour-review findings, with no count
mismatch or native-geometry error. It remains labelled BLOCKED, not fab-ready;
the explanatory text explicitly identifies received branch/pivot construction
instead of falsely claiming unchanged source placement. Publication receipt:
`build/atx30-received-fixed-land-review-20261007-ee/atx-24pin-rev3/independent-publication-receiving.json`,
SHA256 `f62142140208fbc3672826306e9bed9443c604d30d98193a090b64e7668cfcfc`.
The existing Windows localhost dashboard returned HTTP 200. No new board-view
tab was opened.

## Joint native access and corrected pour ownership checks (2026-10-07)

### Outcome: no further physical closure; false execution failures removed

The selected private ATX remains the same **30-open, 3-scored-DRC** board,
SHA256 `e1a06204fae8e2245ddd4e1d6aea8f9bab748c4130e170b0e0ac3f4db0716c12`.
This pass closes **zero additional opens** and makes no fabrication-ready
claim. The preceding 31-to-30 construction was re-received under the final
code; revalidation is not a second closure.

| Saved-board evidence | Before this slice | Fresh final-code result |
| --- | ---: | ---: |
| Native opens / scored DRC | 30 / 3 | 30 / 3 |
| Raw native DRC findings | 558 | 558 |
| Full50 PASS / N/A / FAIL / DECLARED | 26 / 11 / 10 / 3 | 26 / 14 / 7 / 3 |
| Existing current-width fault objects | 109 | 109 |
| Typed Kelvin passed / unknown | 4 / 12 | 4 / 12 |

The three changed Full50 results are **execution/applicability corrections**,
not three repaired electrical defects. A complete pour-first state explicitly
containing both `frozen_nets=[]` and `pours=[]` declares no frozen execution
owner; it does not declare that the board contains no copper. The checker now
recovers the actual native front/back force-zone outlines in that case,
independently of a producer's zone-name spelling. It reaches the existing
shared-bus applicability decision rather than failing before that decision.
Partial/missing ownership declarations still refuse. Native concavities are
retained; unsupported holes/arcs refuse instead of becoming rectangular
plotting slabs. No pad-derived imaginary pour is permitted for this explicitly
unowned state, and native recovery explicitly grants **no capacity rating**.
The old sidecarless producer-name/derivation behavior remains unchanged.

The seven remaining failing categories are routing completion, IC power/ground
connectivity, current-width/path qualification, pour cross-section, Kelvin
pickup qualification, USB coupled routing, and USB/CAN physical pair integrity.
The 3 scored dangling findings are not simply detached debris: native read-only
inspection finds their locked power copper/barrel connected to real retained
terminals. Blind removal is not justified. Neither the old width debt nor the
12 unknown Kelvin inputs is downgraded or hidden.

### Generic construction/search repairs

The following changes contain no board/refdes/coordinate dispatch rule:

- Ground-pose proposal domains can explicitly use a manufacturer's true ground
  root and its unique source-selected bypass entry. A reference is not invented
  as an independent barrel root. Directed ground/reference links, the actual
  bypass, immediate return and every complete-cell obligation still require
  their independent live checks.
- An opt-in joint pose domain projects actual same-face pad/copper clearances
  before ranking. It operates on a physically source-cut private snapshot;
  worker-supplied retired UUIDs cannot suppress live obstacles. Typed measurement
  roots also project possible immediate access away from **same-net force
  material**, without granting any new measurement pickup aperture.
- Conservative native spatial broadphases and a function-local immutable
  shape cache keep a bounded local proposal from converting unrelated copper
  repeatedly. Outline reservations and actual fills have distinct cache keys;
  no cache carries across a pose/copper epoch. This avoided the observed
  200,000-vertex refusal without increasing that work limit. No controlled
  whole-wave speedup is claimed.
- Measurement layer-access search reserves work for alternate strategies,
  proves source-channel stubs before deep bridges, retains a shortest guarded
  suffix per physical portal, and divides the remaining lease among ready
  portals. Previously one unsuccessful portal could consume the remainder.
  Native frontier calls can now opt into angularly diverse proposals rather
  than spending their small site menu on one nearby trunk corner. Default
  nearest-first order is unchanged for other callers.
- Native orthogonal channel proposals have a bounded compound-axis fallback
  after the historical candidates. It can leave a pin row and re-enter a
  source channel without an arbitrary diagonal; each whole leg and completed
  path still passes the original native/contact/field/length predicates.
- Complete-cell scalar-boundary and measurement-portal constructors now enable
  the already-supported bounded early multi-layer pilot. Supplying several
  layers alone had not enabled that pilot. Its operation, layer, source-contact
  and final receiving limits are unchanged; it is not automatic IC-motion or
  release authority.

### Actual board trials and why a new pose was not adopted

One sensing-cell proposal passes actual pad/courtyard screening and all its
immediate ground-return checks. Its full construction still has empty domains
for both original measurement pickups and the scalar-output boundary. It is
not selected, saved as a routed winner, or published as board progress.

`build/atx30-early-three-dimensional-cell-construction-20261007-fq/probe.json`
shows that the repaired constructor really enters its multi-layer pilot. One
bounded graph reaches its window boundary and remains approximately 3.95 mm
from the required portal; this is an explicit finite-search limitation, not a
physical no-path proof. A separately bounded 8 mm window diagnostic
(`build/atx30-bounded-expanded-cell-window-20261007-fw/probe.json`) likewise
produces no complete candidate. It is not promoted to a default larger board
or relaxed geometry rule.

The actual filled copper after the authorized private cuts was inspected per
non-plane layer in
`build/atx30-joint-cell-native-copper-20261007-fb.png`. That image is labelled
**diagnostic, unaccepted and not routed** and binds its exact private native
board hash. No invented FEM/plotting material or 3D model is included.

Other completed bounded trials preserve the same source/code:

- `build/atx30-source-row-channel-diagnosis-20261007-fg/probe.json`: reference
  return plus source-owned planar measurement reconstruction, no candidate.
- `build/atx30-finite-ordinary-closure-pass-20261007-fl/probe.json` and
  `build/atx30-native-source-net-closure-pass-20261007-fn/probe.json`: native
  threshold, clock and PSON port portfolios, no accepted additional join.
- `build/atx30-full-rated-supply-pass-20261007-fs/receipt.json`: explicit approved
  aggregate contracts on +3V3, +5V_SYS, 5VSB_MUX and +5V_SYS_PORT; zero joins.
  The contracts were not replaced by guessed local currents or thin defaults.
- `build/atx30-native-power-terminal-pass-20261007-el/receiving.json`: six force
  domains lack a positively rated trace trunk for this trace-only terminal
  producer. The refusal is retained; unqualified pours cannot silently become
  rated trunks just to let an input/divider connect.

These unchanged configurations are at a bounded plateau. Repeating their
same port menus is not the next construction step. Placement must account for
the original measurement/source-boundary escape paths, not only ground and
surface legality, and a complete successful IC-motion transaction still needs
independent typed receiving before adoption. Force-current/pour and whole-pair
qualification remain separate unresolved fabrication gates.

### Final evidence and preserved controls

- `build/atx30-final-slice-receiving-20261007-ft/receiving.json`, SHA256
  `e64caa38be8e5b9fa1c08b858e715d22e3024484fc49eb3133229da883b2a9f3`:
  accepted private revalidation, 43.90 s, exact current-debt comparison
  complete, zero new/worsened current faults, no new native DRC/field/Full50
  blocker identities, original partitions and the existing received Kelvin
  evidence preserved. Source/candidate families, control and code unchanged.
- `build/atx30-final-slice-generic-regressions-20261007-fv.xml`, SHA256
  `92be31963908c9eb2b5e59e184fab70048ebfa825439e1d397543eb7e06372a9`:
  **1,066 passed, zero failures/errors, one skipped**, 213.16 s. This is a
  focused search/geometry/current/field/receiving suite, not the whole repo.
  The skipped legacy Hub-file fixture is absent; the synthetic empty-board
  and explicit-unowned/native-pour fail-closed tests are executed.
- `build/atx30-final-slice-cross-board-controls-20261007-fu/receiving.json`,
  SHA256 `f7cb2da557874991b766e5542026346db866be1055259743c74e78940a127c85`:
  PCIe2 archive and the private unadmitted Hub preserve zero opens/scored DRC,
  exact native copper/families and pair/field evidence, with no new generated
  tracks/vias/joins. Inherited PCIe2 qualification debt and Hub's 122 contour
  findings are not qualified by this replay.

The private resume selector now records the **zero-open, zero-unwaived-DRC and
fully qualified fabrication target**, rather than treating the old <=30-open
interim milestone as task completion. This slice makes no BETA source/BOM/
schematic/control-board edit, installation, memory edit, commit or release.
Existing unrelated dirty work is preserved. No board-view tab is opened and
no blind unchanged routing wave remains running at the end of this pass.

## Complete-cell pose rejection and independent terminal approaches (2026-10-07)

### Outcome and qualification boundary

The selected ATX board is **unchanged: 30 opens, 3 scored DRC findings and 558
raw findings**, SHA256
`e1a06204fae8e2245ddd4e1d6aea8f9bab748c4130e170b0e0ac3f4db0716c12`.
This continuation closes **zero additional opens**. Full50 remains 26 PASS /
14 N/A / 7 FAIL / 3 DECLARED. The 109 current-width fault objects and 12 unknown
typed Kelvin inputs remain unresolved, not qualified or downgraded.

Two generic changes were implemented and tested. Neither dispatches by board,
reference designator or a fixed coordinate:

1. `cec_maze_channels.orthogonal_channel_paths` has an explicitly bounded
   independent-approach tier. A five-leg Manhattan path can leave and approach
   two terminals on different axes instead of being restricted to the old
   three/four-leg menus. The historical menu remains the identical prefix.
   At most two times `max_axes` cubed additional proposals are allowed, with
   `max_axes <= 8`. Existing native clearance, layer, contact, length, field
   and complete-path checks still decide every proposal. The common guarded
   last-mile router enables this tier only in its existing finite refinement
   mode; no raw diagonal or relaxed clearance is introduced.
2. `cec_cell_escape_replan.complete_connection_screen` and the strict
   `cec_escape_pose_frontier` mode screen **all** source-derived connections
   before a private pose can be called complete. They rederive the source cut
   and actual private draft, require every obligation domain, solve compatible
   joint copper, restore every surviving native source partition with exact
   moved-pad identity mappings, and prove that every ground obligation reaches
   an actual saved filled ground plane. A legal barrel alone is not a return.
   Native trial operations are rolled back on success, refusal and partial
   construction exceptions. A first ground-only success no longer stops the
   complete-mode frontier before later poses have been considered.

The second change is a **proposal screen**, not an independently received IC
motion operator or an unattended complete-placement stage. The legacy
ground-only mode stays compatible but explicitly reports that remaining
connection obligations are still required. No saved-board, placement, current,
Kelvin or release authority follows from either proposal mode. The existing
typed cut chain still accepts only its separately received narrow phase kinds;
it has not gained arbitrary connected-IC motion authority.

### Actual ATX trials: diverse poses still do not construct a complete cell

The ground/surface workbench was extended to retain multiple distinct proposals
per cardinal rotation, not repeatedly fund its first ground-accessible pose.
`build/atx30-distinct-full-cell-pose-portfolio-20261007-fx/probe.json` finds 12
ground-accessible proposals, three per rotation. They are not routing-ready
placements or selected routed candidates.

Fresh complete-cell screening of eight distinct proposals is recorded in
`build/atx30-complete-connection-pose-cohort-20261007-gh/probe.json`:
**0 complete / 8 tested**. Both source-typed measurement pickup menus and the
scalar-output boundary menu remain empty in every tested pose. One also lacks
a local supply connection despite passing its ground/courtyard screen.
Every test has a separate finite <=10-second lease and preserves the selected
source family and code. These results are finite-search refusals, **not proof
that no legal route exists**. No diagnostic pose is promoted or published.

Separate deep trials of other rotations and the source-channel/ordinary-net
constructors also produced no candidate:

- `build/atx30-distinct-cell-construction-20261007-fy-1/probe.json`,
  `build/atx30-distinct-cell-construction-20261007-fy-3/probe.json`, and
  `build/atx30-distinct-cell-construction-20261007-fy-5/probe.json`.
- `build/atx30-independent-approach-cell-20261007-gb/probe.json`.
- `build/atx30-independent-source-channel-pass-20261007-ga/probe.json` and
  `build/atx30-independent-channel-scalar-breadth-20261007-gd/probe.json`.

### Retained ground material is an actual blocker, not a plotting slab

The source-channel forensic in
`build/atx30-independent-pickup-axis-forensic-20261007-gc/probe.json` records
the actual native obstacles for terminal-derived five-leg paths. In this
specific diagnostic, the source-selected C65V1 ground fan-out crosses a
possible +5V_MAIN measurement escape. Its source track
`c953a17f-7e27-4235-8bc6-cd90543b180b` runs from (57.1393, 42.5098) to
(54.9350, 44.7141) mm. The retained ground track
`e1d65085-9529-47d3-a329-0cff0bdc7b32`, from (56.5000, 39.8176) to
(56.5000, 49.0000) mm, contacts its **interior**. That is a real shared native
junction, not an exclusive capacitor stub. These coordinates identify evidence
only; they are not a production routing or retirement rule.

A bounded exclusive-fan-out prototype correctly refused that interior tap.
It was not retained as a production feature and granted no cuts. A separate
read-only diagnostic,
`build/atx30-shared-ground-departure-native-audit-20261007-gl/probe.json`,
removes each of the capacitor's two direct departures individually in fresh
unsaved private snapshots. Each removal preserves every surviving source
partition, all 122 existing ground-return paths found within 3.5 mm, and the
diagnostic field-blocker identities. **The selected capacitor itself has no
proved existing return within that reach**; preservation of other returns
does not qualify its local bypass loop. This test is not a saved/refilled
ground-cut receipt, does not rate current/barrel capacity, and does not
authorize jointly removing both departures.

The next causal construction boundary is a source-typed joint cell/ground
return reconstruction with explicit shared junction restoration, followed by
independent IC-motion and whole-board receiving. Treating these source ground
edges as arbitrary disposable obstacles or rerunning the same ground-only
poses would not solve that boundary safely. Power-pour/current and whole-pair
qualification remain separate unresolved fabrication gates.

### Final-code evidence

- `build/atx30-complete-cell-final-generic-regressions-20261007-gi.xml`, SHA256
  `5b886f053ff07971c0c20c66480a129eccb47e9c3d41dcfed41846afb1e4ac4b`:
  **1,089 passed, zero failures/errors, one skipped**, 174.06 seconds. The
  existing missing legacy-Hub fixture is the skip; the new real-native
  complete-cell and independent-approach tests execute. New tests cover all
  cardinal rotations, renamed owners, connectivity preservation, failed
  construction cleanup, forged/stale drafts, absent ground material,
  underplanned terminals, continued pose search and explicit finite flags.
  The synthetic fixture supplies its approved assignment/current-domain
  inventory; routing, geometry, native partitions and joint solving are real.
  This is a focused suite, not the entire repository suite.
- `build/atx30-complete-cell-final-receiving-20261007-gk/receiving.json`, SHA256
  `c8dceb60d77ce756c94695cb2238c5f536582118ba9ff8d85829e798dd78dd80`:
  accepted private revalidation, 41.98 seconds, zero new/worsened current
  faults, no new native DRC/field/Full50 blockers, original source partitions
  and received Kelvin evidence preserved. Source/candidate/control families
  and code unchanged. This revalidates the preceding 31-to-30 construction;
  it is **not another open closed in this continuation**.
- `build/atx30-complete-cell-final-controls-20261007-gj/receiving.json`, SHA256
  `4fb33456068b63e37b04fbe409ebc09c61aee6cfecab97e7d80313504766e824`:
  the immutable PCIe2 fab-review archive and private unadmitted Hub control
  retain zero opens/scored DRC, exact native copper and zero new generated
  items/joins. PCIe2 keeps its inherited pair refusal and Full50 qualification
  debt; Hub keeps its 122 contour findings. Replay is not new release approval.

No BETA board, schematic, BOM, bus geometry or control-board file was changed.
No board-view tab was opened, no unchanged blind routing wave is left running,
and no release or fabrication-ready claim is made.

## 2026-10-08 — accepted ATX continuation from 30 to 14 opens

The current private resume checkpoint is
`build/atx-stall-selected-safe-checkpoint-20261005-je.json`. Its selected board
is `build/atx15-port-full-board-native-frontier-20261008-afq/UNADMITTED-waypoint/board.kicad_pcb`,
SHA256 `95bb113a8fc7998bb83539eead990fa1353deb7f74896b7bd0a8d6d272eecc8a`.
This is actual saved native copper, not a rendering-only route. The accepted
progression is 30 → 29 → 28 → 27 → 25 → 23 → 22 → 21 → 20 → 19 → 18 → 17
→ 16 → 15 → 14. Sixteen opens closed; **zero is not achieved**.

### Reusable production changes, not private coordinate rules

- Source-typed partial measurement-input inventory identifies an isolated
  package input separately from an already-connected force net.
- Explicit bounded multilayer transition budgets retain the default policy
  and limit optional middle-route barrels to 0–8.
- Leg-granular strict repaired-input evidence independently receives a real
  repaired leg while unreached peer failures remain UNKNOWN. Changed peer
  departures are never silently waived.
- Actual native exclusive package-input trees can traverse qualified plated
  barrels and permitted layers; those non-load branches do not rate a force
  bus, invent a lower load budget, or credit barrel ampacity.
- Native plated THT/via layer transitions count as existing connectivity;
  no redundant barrel is added merely to satisfy a single-layer graph.
- Manufacturer ground-tied reference returns have a bounded exact source
  linear-chain receiver. Replacements cannot get longer, remove a mesh or
  branch, or worsen a proved existing local ground return.
- A changed shared source contact triggers independent absolute re-admission
  of every affected repaired input cohort. This resolves witness-count changes
  without permitting an unproved peer pickup.
- An explicit finite native-board search envelope uses saved Edge.Cuts for
  the search domain, never for copper or clearance authority. Real edge/hole,
  full-width, field, native connectivity and final saved-board checks remain
  mandatory. Default helper behavior is unchanged; final ordinary completion
  can use the bounded mode. Power, measurement and pairs retain typed ownership.

The late connector-power closure demonstrated a real search-domain defect:
the endpoint-local window excluded a needed detour around unchanged retained
buses. A wider finite search produced the 15-to-14 candidate. Native-envelope
regressions exercise rotated/reversed unrelated-net fixtures, retained THT
layer access, blocked full walls, unavailable outlines, expired work leases,
literal flags and unchanged length/width/edge limits. A separate supply escape
still exhausts its reachable geometric component with the **whole saved board**
in scope; widening a window does not dissolve its native copper cage.

### Independently received physical progress

The standby-monitor supply/reference reconstruction and source-inner-face
measurement leg now raise typed clipped Kelvin coverage to **10 PASS / 6
UNKNOWN**, 16 expected. Its coordinated preclears preserve every original
terminal partition. The two mux island closures retain the declared 3 A rail
load, 1.25 geometry margin and 477370 nm outer-layer width. One uses an explicit
factory-qualified 0.35/0.25 mm local SMD dogbone barrel. No new barrel-current
or thermal qualification is claimed. Connector power reuses actual retained
THT layer access and preserves protected bus geometry.

Final-epoch evidence at this checkpoint:

- `build/atx14-final-native-envelope-code-receiving-20261008-agd/receiving.json`,
  SHA256 `7bdba414c86d5a286416bfb7ff1346b741d637340b253bde41e23e8f2d95f575`:
  accepted 15-to-14 revalidation, 47.85 s, no new native DRC, field, Full50 or
  current-width faults; all source/candidate/control families and code unchanged.
- `build/atx-native-envelope-and-current-integrity-regressions-20261008-aga.xml`,
  SHA256 `920f766a4b13e15a858c313d10fe8559f44ed7cb9037ad93cb20af8865db1a7b`:
  **742 passed, zero failures/errors/skips**, one upstream SWIG deprecation
  warning, 80.97 s. This is the focused changed-stack suite, not the whole repo.
- `build/atx14-native-envelope-cross-board-controls-20261008-agc/receiving.json`,
  SHA256 `a7c57fff73aaff580d7a0d1d261ae37a030be7679c863b6cd81797fc3a16d437`:
  immutable PCIe2 archive and private Hub retain zero opens/scored DRC, exact
  native copper, no new items/ordinary joins/supply joins, and two reused native
  pairs each. Their inherited qualification debt remains unqualified.

ATX remains at **14 opens / 3 scored DRC / 558 raw findings**, Full50
**26 PASS / 14 N/A / 7 FAIL / 3 DECLARED**, and **103 inherited current-width
faults**. Remaining blockers include the jointly fenced monitor reference and
supply ports, two USB and two CAN members, a system-supply island, two input
force-terminal joins, a long scalar escape and incomplete negative measurement
branches. Native bus, barrel/current, thermal, whole-pair and release gates are
not weakened. This is a recoverable private candidate, **not fab approval**.

No main/BETA board, schematic, BOM or archived control was edited. No board or
browser tab was opened, and no unchanged blind wave is left running.

## Independently received 11-open checkpoint, 2026-10-08

The private ATX progression now reaches **30 to 11 opens**, nineteen closed.
The selected saved board is
`build/atx13-to11-negative-three-volt-canonical-inward-inputs-20261008-akc/UNADMITTED-waypoint/board.kicad_pcb`,
SHA256 `538878e9fa5d0be9a6cda0ded24dc26102eff619b2dd2de03fa45b087be6cc67`.
Zero opens and fabrication readiness are **not achieved**.

Two additional generic production policies were implemented and exercised:

- A manufacturer-resolved two-land bypass-return reseat preserves every real
  all-layer ground contact and surviving partition, including retained narrow
  opposite-surface branches. The new return cannot be longer; a mesh, unrelated
  ground branch, power return, or bulk-cap connection cannot be retired.
- An actual source-owned cardinal shunt endpoint can retract collinearly while
  keeping its width and far boundary unchanged. A deterministic source-width
  collector is independently reconstructed inside the original native copper
  and actual shunt pad. Unsupported inward round-cap copper is removed, not
  treated as a valid Kelvin pickup. Added zones have exact replay authority,
  not a blanket zone allowance or fabrication waiver. Inherited inadequate
  bus width remains inadequate and is not qualified by this geometric repair.

The actual three-volt negative-input cohort now connects both package inputs
through the proper native inward shunt land. Its typed source cut also includes
a real full-load supply reconstruction and a shortened bypass-ground return;
every affected repaired source contact was re-admitted. Typed clipped Kelvin
coverage improves from 11 PASS / 5 UNKNOWN to **13 PASS / 3 UNKNOWN** of sixteen.

Final current-code evidence:

- `build/atx13-to11-current-epoch-independent-receiving-20261008-akk/receiving.json`,
  SHA256 `8da6f5de8206938012f1c9897bdffec8134bc192a8423b6373f5a8a7c44b2298`:
  accepted, 70.4 s, unchanged **3 scored / 558 raw DRC**, Full50 **26 PASS /
  14 N/A / 7 FAIL / 3 DECLARED**, and 103 to **102 inherited current-width
  fault objects**, with no new or worsened native, current, field or pair faults.
- `build/native-endcap-and-current-closure-full-regressions-20261008-aki.xml`,
  SHA256 `a9309bf4a1a28f4bf8326fbc2242b190a8943bff2860b6d3f39cc476fa8d59af`:
  **930 passed**, zero failures/errors/skips, focused changed-stack tests.
- `build/atx11-native-endcap-source-copper-cross-board-controls-20261008-akj/receiving.json`,
  SHA256 `b0939dc72b6d83ff9ba70ac31ce4165e493bcb417ba664b7ee3b2759078c8ea1`:
  immutable PCIe2 and private Hub controls retain zero opens/scored DRC and
  exact original copper; no new route items, joins or qualification credit.

Private staged endpoint tooling now uses nearest-integer native coordinates,
and supports qualified contained SMD barrels before complete multi-layer
construction. Every such staged barrel must join the final new route and pass
whole-packet craft, native-field, ground-refill and independent receiving checks.
The current long USB/CAN search deadline refusals and control-route portal
searches are finite unsuccessful attempts, **not proofs of physical no-path**.
No main/BETA board, schematic, BOM or archived control was changed, and no
board/browser tabs were opened after runs. Current, barrel, thermal and release
qualification remain open.
