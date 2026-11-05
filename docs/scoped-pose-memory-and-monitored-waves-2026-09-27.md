# Scoped pose memory and monitored waves — 2026-09-27

## Authority and live work

This continues `native-fill-stability-and-hub-four-open-handoff-2026-09-27.md`.
The starting Hub for this slice was the **four-open** archive
`build/board-archive/20260927-hub-standard-rev2-checkpoint-continuation-73f69a72cb/board.kicad_pcb`,
SHA256 `73f69a72cb9f87e8881225792d7bf45bbfc1705d78b4c90a88a8aed58e6cd1ec`.
Full independent revalidation first accepted the **three-open** archive
`build/board-archive/20260927-hub-standard-rev2-checkpoint-continuation-6e2c76caa8/board.kicad_pcb`,
SHA256 `6e2c76caa80ff3aa1e4505706d552ed4b32a115e54c721d1c13b9e6f9cda66b8`.
The latest independently accepted Hub is now the **two-open** archive
`build/board-archive/20260927-hub-standard-rev2-checkpoint-continuation-3907452465/board.kicad_pcb`,
SHA256 `390745246590805a36995cdbc141b4627c5557edb3170b44c6a22de525c89ad1`.
It has zero qualified structural DRC and no incumbent-gate regressions.
This is routing progress, **not fabrication qualification**.
Do not substitute a candidate by date, modification time, or a browser tab.

Evidence root: `build/pose-history-20260927/`.
Completed WSL user service: `cec-hub-residual-v73-20260927-a.service`.
It ran the existing `tmp/replay_residual_waves_20260926.py` against that
exact source, with **three 180-second residual leases**, complete fresh
incumbent/admission grading between leases, and production history persistence.
The service has a 20-minute outer cap, an 8-GiB process-group memory ceiling,
and group-wide termination with a ten-second grace period. It does not repeat
the unbounded global-router fallback. It is a residual-stage campaign, not a
new start-to-finish manufacturing qualification.

At launch the source hashes were checked, no older campaign was running, and
the WSL filesystem had 59 GiB available. The service writes `hub-waves.log`;
`hub-waves/summary.json` and each `wave-NN/result.json` record completed work.
A missing final report is an interrupted/failed run, not a completed wave.
Do not edit shared solver scripts while this service or a successor is active.

The control is the immutable PCIe two-port review board:
`build/board-archive/20260831T2253-pcie-8pin-2port-final-fab-review-v103/board.kicad_pcb`,
SHA256 `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
Its fresh native replay writes `pcie-control/native-control.json`.

## Generic change and its boundaries

`cec_route_pose_history.py` adds a small, sanitized placement-pose hint set
to the existing compact route-search handoff. Repair revision was
`2026-09-27-scoped-placement-pose-history-v73`; the subsequent bounded
support-chain admission fix uses `2026-09-27-bounded-support-chain-proof-v74`.
The subsequent fresh-support scheduling fix uses
`2026-09-27-fresh-support-deferral-refresh-v75`. Old-revision hints expire.
The following revision was `2026-09-27-live-support-net-connectivity-v76`.
The subsequent native pad-contact proof uses
`2026-09-27-native-pad-contact-branch-proof-v77`.

The scope binds exact PCB bytes, project/rule/frozen-family contents, native
engine version, search budget and recipe, and support-movement limits.
KiCad's project display filename and the private frozen-state pathname are
not geometry; their changes alone do not erase useful history. Other policy
changes invalidate it. An implicit/missing project declines pose caching.

Only measured rejected poses in nested placement sweeps are carried. Generic
worker errors and interrupted transactions remain retryable; explicit bounded
pose-restoration outcomes can advance the finite menu. An accepted geometry
change resets pose hints. Companion-cell membership is part of pose identity.
The shared serialized history remains at most 48 KiB (reader cap: 64 KiB).
Malformed/nonfinite/oversized keys are discarded, never executed.

These hints schedule work only. They do not establish route impossibility,
grant permission to move a component, alter dimensions/clearance, suppress a
native DRC, or bypass full support-placement and protected-copper admission.
There is no board name, reference designator, net name, or coordinate repair
recipe in the helper.

Initial regression: **452 passed**, including 243 focused history/coordinator
tests (overlapping sets, not 695 unique tests). Coverage includes a real
coordinator writer/reader handoff advancing a two-pose breadth menu, rule
changes reopening it, native front/back/translated/rotated board copies,
unmeasured IPC, companion identity, oversized Unicode, and protected-fill/
route-checkpoint/placement regressions. The two initial fixture errors were
an unsupported KiCad LSET constructor; fixtures now use the installed native
`AddLayer` API. They were not pipeline failures.

## Monitor continuation contract

The user explicitly replaced periodic monitoring with completion-driven
follow-up. The existing heartbeat `cec-board-suite-review-and-repair` is
**PAUSED**. Do not reactivate it or create another timer.

`scripts/cec_systemd_completion_event.py` subscribes to systemd's user D-Bus
signals for one exact unit and invocation, with no polling loop.
`scripts/cec_wave_completion_bridge.mjs` receives that terminal event and sends
one continuation to the original task through the installed, unmodified app
MCP adapter (`cec_codex_app_events.mjs`). There is no separate agent/model,
app-server daemon, or new task. A persistent exclusive claim prevents duplicate
dispatch; an uncertain acknowledgement is recorded and not blindly retried.

The end-to-end test is in `event-bridge-test/state.json`: the test unit exited,
the adapter acknowledged the send, and the explicitly labelled test message
arrived in this task. A test event is not board progress. Future bounded wave
or plateau-stop jobs must each have their own exact-invocation listener armed
before this turn ends. Their terminal event prompts result review, never
automatic promotion based solely on exit status. Keep the computer and Codex
app running; this is not guaranteed across a reboot/app restart. Delivery and
listener failures remain in each event evidence directory.

At each wake:

1. Read this handoff and newer recorded continuations; inspect the named
   service, journals and actual live processes. Never duplicate active work.
2. If work is healthy and incomplete, stay quiet. If finished, inspect every
   worker/admission result, preserved source hashes, pose-history intake and
   the actual next-wave history, not just an exit code or claimed score.
3. Promote/publish only a freshly graded, independently admitted improvement.
   Preserve the latest admitted archive until then. Verify models-off top/bottom and
   six-layer dashboard assets against the exact accepted hash. Never describe
   partial routing, a false release gate, or thermal-not-qualified as fab ready.
4. If a bounded cohort gains neither connectivity nor new measured search
   coverage, diagnose its generic cause before another identical cohort. Do
   not increment visit counters and call that coverage. Repeated worker errors
   require repair; they are not a reason to mark an untested pose exhausted.
5. Continue useful bounded work from the verified selected family, carrying
   its production sidecar. Use a unique output/service name and a hard outer
   deadline. Keep a 16-GiB free-space floor, cap disposable trials, preserve
   accepted boards and forensic evidence, and do not erase unrelated work.
6. A solver change needs synthetic regression plus fresh PCIe control replay.
   When another suite board has a current, hash-bound route-ready source, it
   may advance too; do not route an interface ECO or mechanically unqualified
   old placement. The latest board-suite ledger owns that cohort, not a guess.
7. Notify only on admitted progress, a meaningful failure/regression, a review
   artifact or a required decision. A plateau requires a new diagnosis or
   measured search coverage, not an endless identical completion/relaunch loop.
   Honor a user stop immediately and do not arm another completion listener
   when the work is complete or no safe useful next step remains.

## Results

The PCIe native control completed in 10.744 seconds: **zero opens, zero
qualified structural DRC**, source-family hashes unchanged and exact native
copper inventory unchanged. Its pre-existing `pairs_ok: false` remains visible
and correctly prevents a zero-airwire result from implying routing/fab signoff.

Hub wave 0 completed its 180.055-second worker lease with **four opens and zero
qualified structural DRC**, no admitted gain, and unchanged source authority.
It measured ordinary/deep/negotiation work, retained the measured USB_VBUS
timeout and net scheduling history, and kept an interrupted negotiation worker
retryable. No support pose was tried in that first wave (three supports were
still deferred), so do not claim native pose-frontier advancement yet.
The actual wave-1 input received the exact compact history. All three waves
have now finished in 593.782 seconds, with no independently admitted gain.
The final worker proposed four to three opens and zero qualified structural
DRC, but placement admission rejected deletion of a second, pruned stub
segment after the pad-incident segment was rebuilt. The accepted archive
therefore remained at four opens. The saved proposal is evidence, not an
accepted board:
`hub-waves/wave-02/residual-resume/round-00/certificate-repaired.kicad_pcb`.

Two generic causes were found and addressed before repeating work:

- Frozen-state JSON contained an absolute skeleton pathname, which made copied
  families falsely invalidate pose history. Scope now binds the referenced
  skeleton's actual bytes, not that staging pathname. All three actual wave
  copies were replayed and produced equal authority scopes after the fix.
- The independent support-branch proof recognized only one pad-incident
  segment. It now derives an exact endpoint-connected, unbranched, acyclic
  chain on one net/layer, rooted at exactly one moved SMD pad. The existing
  eight-deleted-item maximum remains; locked/grouped tracks, vias, rewrites,
  ambiguous owners, floating chains and lost original native members remain
  refused. All other placement, protected-copper, fill and fresh grading
  gates are still mandatory. This does not authorize arbitrary cleanup.

The scope/event regression completed with 455 passing tests. A subsequent
focused chain/scope/event regression passed 112 tests (overlapping sets, not
additive). Fresh full candidate revalidation and broader regression are
recorded separately below. The final PCIe scope-fix control took 10.930 seconds,
still zero opens/zero qualified structural DRC, with its source family and
native copper unchanged and pre-existing `pairs_ok: false` still visible.

Append later measured cohort results below; do not infer connectivity gain
from implementation tests or scheduling counters.

## Three-open admission and event-driven successor

`chain-revalidation/native-control.json` independently accepted four to three
opens, with no gate regressions and both input families unchanged. The
support-chain proof retained all 18 original surviving native members and
found no other parent-copper changes. All 20 protected filled-layer checks
lost zero area/polygons at **zero tolerance**. Remaining nets are `/KVM_5V_IN`,
`/POWER INPUT + SOURCE SELECTION/U11_OV1`, and `/USB_VBUS`.

The expanded chain/placement/coordinator regression passed **342 tests** in
121.50 seconds (`regression-chain-proof.log`). These overlap earlier sets;
do not sum counts. `pcie-chain-control/native-control.json` took 10.802 seconds,
confirmed zero opens/zero qualified structural DRC and unchanged native copper
and source family. Its pre-existing pair qualification issue remains visible.

The three-open archive has models-off top/bottom and all six copper views;
the exact board hash is bound in `chain-revalidation/published.json`.
Viewer: <http://localhost:8090/?id=20260927-hub-standard-rev2-checkpoint-continuation-6e2c76caa8>.
Still-open release gates include routing, courtyard edge, injection and thermal
qualification; this archive must not be labelled fab-ready.

The successor is one **180-second residual wave** from that three-open archive:
WSL service `cec-hub-residual-v74-20260927-b.service`, invocation
`9521b92def4a49e98284dd683dd41ece`, with a 600-second outer runtime bound,
8-GiB process-group memory ceiling and ten-second termination grace period.
Evidence is `build/event-driven-hub-20260927-b/`; `waves/summary.json` and
`wave.log` are the result authority. The exact-invocation callback configuration
is `event-bridge.json`; delivery state is `event/state.json`. Its hidden Windows
listener was launched as PID 26088. Confirm the recorded `armed` state, rather
than inferring readiness from merely launching the process. It was read back
**armed at 17:05:51 UTC**, matching the exact service invocation above, with
empty stderr. The new three-open archive was also verified in the dashboard
API. Completion or a
bounded plateau/failure stop wakes this same task to review the evidence and
decide the next useful action. It does not poll every five minutes.

## First real completion callback and history continuation

The cohort-b callback arrived in this task with `service_completed`, exit zero,
and persisted delivery state `sent`. Its 193.919-second native replay retained
three opens/zero qualified structural DRC and unchanged source authority; no
new board was promoted. It measured two distinct USB negotiation topologies
(surface-first and bridge-first), both timeouts, and one U11_OV1 surface-first
geometric refusal. The U11_OV1 bridge-first attempt reached the overall wall
budget and remains retryable, not exhausted. KVM negotiation was not reached.

This is the first measured wave against the changed three-open geometry, not
a closed search frontier. Its exact hash-bound production `board.route-search.json`
was verified. Feeding that history through the production scheduler changes
the next negotiation order to **KVM, U11_OV1, USB**, so a bounded continuation
is justified without a solver/rule change or an invented visit count.

Successor cohort c uses
`build/event-driven-hub-20260927-b/waves/wave-00/baseline/incumbent/board.kicad_pcb`
and its intact sidecars (same accepted board hash), with one 180-second residual
lease. Service: `cec-hub-residual-v74-20260927-c.service`; invocation:
`07ef3265c8204820987650f5671ba0bd`. Outer runtime remains 600 seconds, memory
8 GiB, and termination grace ten seconds. Evidence and one-shot event config
are under `build/event-driven-hub-20260927-c/`. Do not rerun from the archive
and lose this scheduling evidence. Check actual next intake/results before
claiming new search coverage; no support pose has yet been tried on this
three-open family.

## Fresh-evidence support scheduling repair

Cohort c finished in 194.314 seconds, still three opens/zero qualified structural
DRC and unchanged source family. It did measure KVM's deep routing search and
U11_OV1's previously interrupted bridge-first negotiation. There was no admitted
gain. Crucially, the forecast KVM negotiation did **not** run: fresh route
certificates classified that target as `wide_or_high_current`, removing its
old negotiation window. Placement nevertheless remained deferred using the
earlier window list. This was a scheduling mismatch, not proof of a globally
unroutable route or permission to change the protected power bus.

The generic v75 fix reconsiders previously deferred, untried support/net
identities after fresh route certification, before spending the rest of the
slice on unrelated negotiations. It invokes the native support planner again;
an absent old window alone does not authorize a move. A freshly retained
same-net window still takes precedence. Missing/failed fresh planning cannot
be mistaken for an empty window set. At most two supports/two poses each are
tried through the unchanged relocation transaction, with original movement,
decoupling, copper/fill and full-board gates. The first adoption ends the slice
and invalidates every pre-move route window. Partial results remain in
`plan.post_route_support_refresh`; rejection history uses the existing scoped
pose ledger. No Hub/refdes/net/coordinate exception was added.

`build/fresh-support-refresh-20260927/regression.log`: **378 passed** in 7.27
seconds, including new scheduling regressions for renamed identities, fresh
coordinates, same-net ordering, missing plans, lost targets, earlier attempts,
budget limits, bounded breadth, authority propagation and adoption remeasurement.
A read-only native replay of the actual saved fresh certificates retained C23
as eligible on KVM while keeping C10 deferred on U11_OV1. These references are
observations, not implementation constants. `pcie-control/native-control.json`
under the same evidence root is the fresh immutable cross-board control; check
its actual fields before promotion. The latest accepted Hub remains `6e2c76caa8`.

The v75 PCIe replay completed in 11.573 seconds: zero opens/zero qualified
structural DRC, exact native copper and input family unchanged. Existing
`pairs_ok: false` remains visible and does not confer fresh fab qualification.
The next real validation wave is `cec-hub-residual-v75-20260927-d.service`,
invocation `72473b57f2c94efb86f7a023224042f7`, under
`build/event-driven-hub-20260927-d/`. It uses cohort c's exact selected family,
one 180-second lease, 600-second outer bound, 8-GiB memory limit and ten-second
termination grace. Old v74 search hints correctly expire under the new
algorithm revision. Its one-shot callback uses the sibling `event-bridge.json`
and `event/state.json`. Inspect the actual refreshed support sweep on completion;
test success and a planned eligible target are not a native routing gain.

## Whole-support-net connectivity repair

Cohort d completed in 194.644 seconds. The v75 refresh genuinely ran two native
support poses, not just scheduler counters. Both closed the KVM connection but
introduced a ground open, so the worker correctly rejected both and kept the
three-open board. Scoped history retained exactly the two measured rejected
poses; 122 generated poses remained unvisited. This is measured search progress,
not an accepted connectivity improvement. Source authority remained unchanged.

The detailed evidence exposed a second generic defect: the exact-pair worker
put a support net in `support_closed_nets` when just one pad-to-anchor pair
closed. The parent then skipped whole-support-net completion. A moved component
can previously have joined multiple islands; restoring one branch does not
prove its complete return graph is restored. The final native score caught the
new ground open, so this defect did not reach the accepted board.

Revision `2026-09-27-live-support-net-connectivity-v76` now records exact-pair
success separately as `support_anchor_closed_nets`, measures live native
`support_components_after` for every affected support net, and populates
`support_closed_nets` only for a graph with exactly one component. Missing nets
remain unqualified. Unresolved support nets use the existing bounded
canonical-breadth/deep completion portfolio, with all usual geometry/current,
clearance, copper-preservation and full admission checks. No power/current
design assumption or per-board coordinate was changed.

`build/support-net-connectivity-20260927/regression.log`: **386 tests passed**
in 6.66 seconds. New native front/back, translated/rotated and renamed-net
fixtures distinguish a restored local pair from a third disconnected island,
verify genuinely closed graphs, and reject both missing-net and falsely claimed
pair closure. An initial fixture iterator error was corrected; the missing-net
case also verified and hardened the native map's missing-key behavior. The
immutable PCIe replay is under that evidence root's `pcie-control/`. Its actual
zero-open/zero-qualified-DRC result and unchanged source/copper must remain part
of promotion review; its pre-existing pair gate remains visible.

The v76 control was verified at 11.574 seconds: zero opens/zero qualified
structural DRC, source SHA256 still `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`,
native copper/input family unchanged, `pairs_ok: false` still visible.
Successor wave: `cec-hub-residual-v76-20260927-e.service`, invocation
`9ea92e184b9b449984c0e66c7bdc3719`, evidence
`build/event-driven-hub-20260927-e/`. It continues cohort d's exact selected
family with one 180-second lease, 600-second outer cap, 8-GiB memory limit and
ten-second stop grace. The changed repair revision intentionally expires the
old measured-pose hints so the corrected restoration algorithm can retest
those poses. Event config/state are `event-bridge.json` and `event/state.json`.
No accepted source or new render has changed since the three-open archive.

## Exact pad-copper contact ownership

Cohort e completed in 138.366 seconds. The v76 worker measured two GND
components after local anchor reconnection, correctly invoked whole-net support
completion, and closed the remaining ground edge in 0.606 seconds. Its first
pose then reached **two opens and zero qualified structural DRC**. Independent
placement admission still rejected it, so that worker score alone did not
replace the accepted three-open archive.

The independent refusal was another generic geometry-model mismatch: a removed
original trace terminated 47 nm away from the moved pad's exact center, well
inside its actual 0.9-by-0.95-mm copper land. Center-coordinate equality missed
that legitimate incident branch. Revision v77 proves ownership using native
effective pad-copper containment with **zero collision tolerance**, not a
numerical epsilon or inflated bounding box. Exactly one moved SMD pad must own
exactly one terminal contact of a bounded simple chain. All original surviving
native members still have to reconnect; locked/grouped copper, vias, rewrites,
cycles, ambiguous contacts and oversized deletion sets remain refused.

`build/native-pad-contact-20260927/regression.log`: **394 passed** in 6.91 seconds.
New native tests cover off-center contact, circle-bounding-box false positives,
outside points and lost boundaries on front/back, rotated/translated fixtures.
The saved two-open worker proposal is being independently revalidated under
`build/native-pad-contact-20260927/revalidation/`, against exact accepted source
`6e2c76caa8`; do not promote it until `native-control.json` says accepted and
the fresh PCIe control in that evidence root is checked. The saved proposal is
`build/event-driven-hub-20260927-e/waves/wave-00/residual-resume/round-00/certificate-repaired.kicad_pcb`.

Full revalidation **accepted three to two opens**, with no gate regressions
and both source families unchanged. Both rebuilt incident contacts preserve
all 316 original surviving native ground members. All 20 protected-fill checks
lost zero area/polygons at zero tolerance. PCIe control: zero opens/zero qualified
structural DRC, source/copper unchanged, 11.183 seconds. Its existing pair gate
remains visible. The accepted Hub still requires U11_OV1 and USB_VBUS closure,
courtyard-edge correction and injection/thermal qualification; not fab-ready.

The two-open archive has models-off top/bottom plus all six copper plots;
`build/native-pad-contact-20260927/revalidation/published.json` binds them to
SHA256 `390745246590805a36995cdbc141b4627c5557edb3170b44c6a22de525c89ad1`.
The top render was visually inspected and the exact archive ID was verified in
the live dashboard API (HTTP 200):
<http://localhost:8090/?id=20260927-hub-standard-rev2-checkpoint-continuation-3907452465>.
The separate saved-board trace-clearance audit is
`build/native-pad-contact-20260927/trace-clearance.json/summary.json` (the harness
treats its output argument as a directory); retain its strict
diagnostics and do not conflate native structural DRC with a release signoff.

The strict trace-gap audit tested 187,316 pairs: 53 sub-database-unit shortfalls,
none at least one nm, minimum gap 0.199999927 mm, no DRC exclusions. Its strict
`audit_ok` remains false; raw native/profile-qualified counts are retained in
the report, not hidden behind the zero qualified-structural count. Source
family remained unchanged. This is not a fabrication signoff.

Two-open successor: `cec-hub-residual-v77-20260927-f.service`, invocation
`4be408167a2944409a0d85ce7365f075`, evidence `build/event-driven-hub-20260927-f/`.
It starts from the exact two-open archive above, with one 180-second worker
lease, a 600-second outer limit, 8-GiB memory cap and ten-second stop grace.
Its one-shot callback config/state are `event-bridge.json` and `event/state.json`;
the original five-minute heartbeat remains paused. New geometry correctly
starts a new pose-history scope. Review actual results before continuation.

## Immutable polish boundary and stalled-wave progress

Cohort f's exact-invocation callback successfully woke this task. Its 194.857-s
run did not improve connectivity. The worker reported a cosmetic-only change
but the independent continuation guard rejected it: four locked parent tracks
on four unrelated nets had been shortened. Their UUIDs were not authorized
generated copper. The accepted archive remains `3907452465`, two opens and
zero qualified structural DRC; no failed candidate was published.

Forensic native inventories pinpointed the shared backtrack/duplicate cleanup.
It proved overlapping copper area but did not check whether the trimmed
primitive was locked. Area equivalence is not permission to rewrite a precision
prefix. Revision `2026-09-27-immutable-polish-boundary-v78` now:

- refuses locked backtrack trims and duplicate removals unless that exact item
  has explicit authority, preserving protected duplicates when both are locked;
- applies the same exact-item lock policy to fabrication width normalization;
- independently compares native locked-item identity and complete geometry
  after every polish variant, so a good DRC count cannot waive unauthorized
  deletion, movement, width/net change or unlocking;
- skips cosmetic-only polish on an open incumbent when no real repair was
  accepted, preventing cosmetic rewrites from masquerading as route progress
  or discarding useful search history.

`build/immutable-polish-20260927/regression.log`: **431 passed** in 7.65 seconds.
New synthetic/native tests cover translated/rotated front/back overlaps,
locked duplicates, explicit-item permission, width policy, independent rejection
of five mutation classes and stalled-versus-closed polish scheduling. Two old
degenerate-prune mock fixtures initially failed because they still modeled
`Remove` rather than the existing native UUID/`Delete` lifetime contract; their
fixture API was brought up to date, without weakening production deletion.

Real private-family polish replays are in that evidence root's `hub-replay/`
and `pcie-polish-replay/`. The Hub retained all **688** locked prefix members,
two opens/zero qualified structural DRC, 37.116 seconds. PCIe retained all
**481** locked prefix members, zero opens/zero qualified structural DRC,
26.589 seconds. Accepted cosmetic trials are test artifacts only; neither
authoritative archive was replaced. Fresh `pcie-control/native-control.json`
independently confirmed unchanged native copper/input family and the original
`2f09d276...59388` hash, zero opens/zero qualified structural DRC, 12.499 seconds.
Its pre-existing `pairs_ok` failure remains visible, not waived.

The next bounded wave starts from cohort f's selected two-open family, not its
rejected cosmetic candidate. The repair revision change deliberately invalidates
old rejection hints; current geometry and native authority still determine
eligible work. Keep the heartbeat paused and arm exactly one service-completion
callback. No identical no-gain campaign may be restarted without inspecting
actual new coverage, fresh support scheduling and failure evidence.

Successor `cec-hub-residual-v78-20260927-g.service` is invocation
`f98ce81c5c9d498bb539304b3131c6de`, evidence root
`build/event-driven-hub-20260927-g/`. One 240-second worker lease, 720-second
outer cap, 8-GiB memory cap and ten-second stop grace. Its callback configuration
is `event-bridge.json`, with `event/state.json` the live receipt. Current free
WSL space was 59 GiB; this slice's validation artifacts occupy 4.1 MiB.

### Cohort g completion and bounded frontier continuation

Cohort g completed in **149.640 seconds** (worker 135.869 seconds). No electrical
closure: accepted Hub stays at two opens and zero qualified structural DRC,
exact SHA256 `390745246590805a36995cdbc141b4627c5557edb3170b44c6a22de525c89ad1`.
Input families stayed unchanged. The v78 polish scheduling behaved as intended:
`changed: false`, `route_polish.skipped: no_repair_progress`; no unauthorized
cosmetic rewrite or failed parent-preservation handoff occurred.

The first v78 route probe measured U11_OV1's finite surface attempt and bridge
timeout; C10 was correctly deferred before this new-revision evidence existed.
`tmp/preview_residual_schedule_20260927.py` evaluated the actual persisted
selected-family history against the fresh certified plan and returned C10
eligible, with no deferred support. That is **new untested search coverage**,
not a no-path proof or permission to loosen any placement bound. The next wave
must continue this exact selected family and revision so the generic scheduler
can try its first support poses. Inspect actual pose attempts/history afterward;
if they never run or no new measured coverage occurs, diagnose instead of
launching an identical campaign. No new board/render was promoted.

Successor: `cec-hub-residual-v78-20260927-h.service`, invocation
`cff0cb63384b476eb966f94450680f5d`, evidence root
`build/event-driven-hub-20260927-h/`. Same 240-second worker/720-second outer
budget, 8-GiB cap and one exact-invocation callback. Source is g's selected
`waves/wave-00/baseline/incumbent/board.kicad_pcb` with saved search history,
not an old schematic, placement seed or rejected polish candidate.

### Cohort h: real closure exposed a misplaced cosmetic stage

Cohort h completed in 232.897 seconds, worker 207.037 seconds. Actual support
placement ran: the first C10 pose failed preflight; the second closed U11_OV1
and restored its support graph, reaching **one open (USB_VBUS), zero qualified
structural DRC** in the worker. This is NOT yet an admitted board improvement.
The unchanged selected parent remains `3907452465`, two opens.

Independent placement revalidation refused `existing_copper_changed`. The
post-repair global polish had chamfered many unrelated unlocked traces before
the local support-branch proof ran. Locked copper remained intact (the prior
fix held), but more than 100 changed parent primitives correctly exceeded that
proof's bounded eight-branch scope. Increasing that bound or exempting the
cosmetics would weaken the ownership boundary and was not done.

The generic fix compares native component pose signatures before polishing.
Any placement-changing proposal now reports `placement_revalidation_required`
and leaves global cosmetics to the later coordinator finish stage, after the
whole placement transition is admitted. An unavailable pose comparison also
defers polish. Even a zero-open worker result cannot skip this boundary. No
route geometry rule, decoupling bound, branch limit or search recipe changed;
v78 route-search history stays valid because only the post-search stage order
changed. The saved one-open h artifact remains rejected; re-run the transaction
from h's exact unchanged selected family, not by reversing arbitrary old polish.

`build/placement-polish-boundary-20260927/regression.log`: **438 tests passed**
in 7.43 seconds. Added native unchanged/translated/rotated/flipped footprint
fixtures and tests that even connected placement proposals defer cosmetics.
The fresh PCIe native control lives under the same root's `pcie-control/`.
No new dashboard board has been published pending independent admission.

Fresh PCIe control passed in 10.417 seconds: zero opens/zero qualified
structural DRC, unchanged native copper/input family and exact original hash.
The pre-existing pair qualification failure is still visible. Read-only saved
history preview confirmed the next bounded replay still schedules C10 first;
the failed global cosmetic proposal is not used as its source.

Successor: `cec-hub-residual-v78-20260927-i.service`, invocation
`4832297070dc4c7f81141bed6e6ba7f5`, evidence `build/event-driven-hub-20260927-i/`.
It retains the 240-second worker, 720-second outer and 8-GiB memory limits,
with one exact service-completion callback. Inspect actual independent
placement admission before calling the worker's one-open proposal progress.

### Cohort i: complete placement proof, but genuine electrical regressions

Cohort i completed in 224.781 seconds, worker 174.472 seconds. Global polish
correctly deferred. The independent support-placement, protected copper and
fill transition **passed**, but full native grading rejected the one-open
proposal on three existing electrical gates: `decouple_ok`,
`decoupler_cell_ok`, `netclass_geometry_ok`. Accepted Hub still has two opens.

Actual diagnostics: the moved bypass capacitor's nearest applicable owner
ground pad is 2.622 mm away versus the existing 2.500-mm return limit. Its
supply-copper path is 3.098 mm versus the existing 2.740-mm local limit. Two
preserved `/USB_VBUS` segments are 0.45 mm wide versus the existing 1.00-mm Power
class; the placement change invalidated their local endpoint-neckdown
qualification. Their group name alone does not make them legal under
the independent physical neckdown classifier. No distance, width or classifier
exception was changed. The one-open i proposal is retained as rejected evidence.

Root cause: the component transaction's local acceptance used structural
DRC/connectivity but omitted the final pipeline's decoupler and dimensional
authorities. Revision `2026-09-27-support-craft-authority-v79` adds shared
`cec_support_craft_gate` to initial, refreshed, expanded and endpoint-owner
transactions. It receives the same declarative policy as final grading. A
conservative native return-geometry preflight rejects overlong returns before
expensive reconnection, ignoring intentionally removed supply copper. Final
native adjacency, whole bypass-cell and netclass checks compare passing gates
and new/worsened fault identities before a pose can be committed. Transient
measurement failures remain retryable rather than poisoning the pose cache.
The adjacency oracle now exposes its complete violation list for machines;
the existing twelve-item human summary is unchanged. No refdes, board name or
special coordinate is used by these rules.

`build/support-craft-gate-20260927/regression.log`: **451 passed**, 7.72 seconds;
the separate non-overlapping `decoupler-regression.log`: **55 passed**, 0.74 s.
Native replay of the rejected Hub proposal reproduced the early return fault
and all three final gate regressions in 8.438 s. Native PCIe gate replay passed
unchanged in 6.974 s. Fresh PCIe residual control: zero opens/zero qualified
structural DRC, unchanged source/copper and original hash, 10.245 s; existing
pair qualification failure remains visible. Both input families stayed intact.

Next use a bounded two-wave v79 cohort: the revised recipe safely invalidates
old rejection hints, and the second wave can consume newly measured ordering
history instead of restarting it. The replay harness now stops the cohort
immediately on worker/admission errors, placement-revalidation refusal, final
independent refusal, source-fill drift or insufficient revalidation budget;
those need a callback review rather than an automatic identical second trial.
No new dashboard board is authorized until independent admission actually wins.

Successor: `cec-hub-residual-v79-20260927-j.service`, invocation
`b3edb30862f94a56b5e6e23b65c8b5c8`, evidence `build/event-driven-hub-20260927-j/`.
At most two 240-second worker waves, 900-second outer cap, 8-GiB memory cap,
ten-second stop grace. Its exact-invocation event callback fires on real cohort
completion/failure. Source is i's unchanged selected two-open family, never its
electrically rejected one-open proposal. Periodic heartbeat stays paused.

### Cohort j: early electrical rejection works; fix finite-frontier bookkeeping

Both j waves completed in 310.178 seconds without an admitted change. The
accepted board/source families remain unchanged at two opens/zero qualified
structural DRC. Wave 1 tried the first two C10 poses: the first retained its
physical DRC refusal; the formerly misleading one-open pose was rejected on
native return geometry in **2.997 seconds**, before expensive reconstruction.
Four other fixed-via-domain poses remain unvisited. No one-open proposal was
promoted and no release gate was weakened.

Two scheduling omissions were visible in the actual reports. The compact pose
writer recognized the older physical preflight but not the new electrical
preflight, so only one of the two measured rejections survived. Also the old
placement-slice end rule assumed rejected poses would be forgotten and replayed
the same costly route searches despite valid scoped pose memory and unvisited
poses. Both are now generalized: explicit native electrical rejection evidence
is remembered; malformed/unknown/worker-error evidence is not. A current valid
scope plus a newly measured rejection and a finite unvisited frontier ends the
slice after route-window precedence, letting the next bounded wave use its
remaining menu. Unscoped, exhausted, target-only or worker-error-only sweeps
still fall through. Accepted geometry continues to require native admission.
Search geometry/policy did not change, so valid v79 history is retained.

`build/craft-frontier-memory-20260927/regression.log`: **517 passed**, 8.02 s.
Tests exercise both electrical measurement stages, invalid/empty evidence,
error retries, scoped versus unscoped and exhausted versus unvisited frontiers.
The native PCIe replay lives under that root's `pcie-control/`; inspect its
unchanged-source/copper and zero-open/zero-qualified-DRC result before launching
the successor. Continue from j wave 1's selected family, not a rejected child.
One historical electrical pose was absent from its saved compact hints, so it
may be measured once more before the corrected writer retains it; do not inject
unverified hints or call that repetition new coverage.

PCIe control verified: zero opens/zero qualified structural DRC, unchanged
source family/native copper and original hash, 10.320 seconds; original pair
qualification issue remains. Successor is
`cec-hub-residual-v79-20260927-k.service`, invocation
`ef55046d304044349d1188972663ec04`, evidence `build/event-driven-hub-20260927-k/`.
At most two 240-second workers, 900-second outer cap, 8-GiB cap and one exact
completion callback. Same source/policy scope, no design dimension changes.

### Cohort k: search memory and bounded slice progress verified

Cohort k completed two waves in 158.852 seconds; workers took 62.528 and 69.123
seconds. It did not improve the accepted two-open board. Three genuinely new
poses were tested and physically rejected; the one electrical pose omitted
from old compact hints was remeasured once as expected, then retained. Compact
measured keys grew **one -> three -> five**, with the same exact source/rules/
policy scope. The second wave skipped the first three keys. Finite unvisited
count is now **one**, so one further single wave has actual remaining coverage.
Native craft checks and saved-family immutability stayed intact; no stale or
failed render was published. The new slice ending avoided the repeated broad/
deep routing passes while there were still remembered unvisited poses.

Forensic correction: the two dimensional violations in cohort i were not newly
generated tracks. Their UUIDs `4321a508-f618-4e1c-bbad-c5ae115a039a` and
`ad200837-1ecd-4a8a-b918-b4d1f2b41e68` already exist in the accepted `3907452465`
source with identical 0.45-mm copper; changing the capacitor pose caused them
to lose the independently measured local-neckdown qualification. Preserve
this placement/copper dependency; do not infer permission to widen or unlock
them, nor use group names as a waiver. Several other poses collided with
preserved copper and were correctly rejected. The prior paragraph is corrected.

After the last finite pose is measured, do not restart this exhausted menu.
Inspect actual blockers and use a genuinely different generalized search
degree of freedom if needed. A finite menu exhaustion is not proof that the
board is globally unroutable, and does not authorize clearance/return waivers.

Final-current-menu run: `cec-hub-residual-v79-20260927-l.service`, invocation
`3724a3d321f84cd481bb12efc7c089cf`, evidence `build/event-driven-hub-20260927-l/`.
One 240-second worker only, 720-second outer cap, 8-GiB memory cap. Starts from
k wave 1's selected exact two-open family plus its five measured pose keys.
One-shot completion callback is configured; the periodic heartbeat is paused.

### Cohort l: exhausted menu exposes a foreign-blocker proposal bug

The last pose was physically refused (eight qualified trial DRC); l completed
in 170.300 seconds. All six fixed-via-domain legacy poses are now measured.
Accepted board remains two opens/zero qualified structural DRC, unchanged
input families. Do not replay that exhausted menu as new coverage.

Root cause found in `_occupancy_relocation_candidates`: it required the moving
support to carry `target_net` even for `away_from_endpoint`. That target is the
obstructed route, while the certificate deliberately names a **foreign-net**
support. The early return bypassed the existing away-field, fixed-via-domain
and mobility-graph generators entirely. This is why the worker only received
the twelve crude legacy offsets despite more capable geometry code existing.

Revision `2026-09-27-foreign-support-occupancy-v80` uses the nearest native
copper land as a geometric anchor for an away-moving blocker. Toward-endpoint
supports still require electrical membership. Pad nets, ownership, immutability,
support displacement, fixed-via, decoupling, width, clearance, copper/fill and
independent admission gates are unchanged. Native tie-breaking is deterministic.
Search geometry changed, so old recipe hints expire rather than being relabeled.

Five synthetic tests reproduced the bug before the fix. All nine new tests
pass afterward, including translated/renamed/front/back/rotated supports,
unchanged source bytes, toward-owner membership, locked/immutable components
and actual small fixed-via constraints. Combined focused regression:
**549 passed in 8.68 s**, `build/foreign-support-occupancy-20260927/regression.log`.
Native read-only Hub preview with the exact saved worker policy now generates
112 candidates, of which 106 satisfy the existing support/fixed-via domains:
16 away-field, 48 fixed-via, 36 mobility-graph and six legacy poses. Thus 100
geometry-generated proposals were previously silently unreachable. This is
search coverage, NOT an admitted placement or route improvement.

`build/foreign-support-occupancy-20260927/hub-native-preview.json` contains that
1.608-second replay and confirms unchanged input families. Fresh PCIe native
control passed in 10.847 seconds: zero opens/zero qualified structural DRC,
unchanged source/native copper and exact original hash. The pre-existing pair
qualification issue remains visible. No new dashboard board was published.

The next bounded two-wave cohort must start from l's unchanged selected family,
never from a rejected one-open proposal. It exercises v80 with a fresh recipe
history and admits only a full independent improvement. No periodic wakeups;
one exact-invocation completion callback will review its measured frontier.

Successor: `cec-hub-residual-v80-20260927-m.service`, invocation
`3846335e03bf47d5815a5e89f0ec766d`, evidence `build/event-driven-hub-20260927-m/`.
Two 240-second workers maximum, 900-second outer cap, 8-GiB cap and ten-second
stop grace. Exact input SHA was verified as `3907452465...` before launch.

### Cohort m: restored geometry search exercised, no admitted improvement yet

Two waves finished in 215.350 seconds (workers 133.505 and 55.076 seconds).
The first established current-recipe same-net timeout history; the second
actually tried two newly reachable geometry poses. Both were physically
rejected before routing: the away-field pose produced eight qualified DRC,
and the fixed-via pose produced one clearance violation against preserved
copper. Native return-geometry checks passed for both; those checks alone do
not establish electrical or physical validity. Their exact rejected keys were
saved under the current source/authority/policy scope. There are 104 unvisited
domain-eligible proposals, not 104 legal placements. The two-open accepted
board, source family and dashboard remain unchanged.

No solver code changed after the 549-test/PCIe replay. A bounded three-wave
successor can test at most six further poses using this saved history instead
of repeating the first two. After that cohort, review recurring physical
blocker identities and candidate ranking; do not mechanically drain this large
menu through repeated no-gain cohorts. Continue to distinguish finite proposal
coverage from board improvement, and preserve every native admission boundary.

Successor: `cec-hub-residual-v80-20260927-n.service`, invocation
`74fd9dfb25984e50b794d7cf5275d23a`, evidence `build/event-driven-hub-20260927-n/`.
Three 240-second worker waves maximum, 1200-second outer cap, 8-GiB cap, one
exact completion callback. Source m wave 1 hash is unchanged `3907452465...`.

### Cohort n: local via-escape evidence and private support-cell topology

Three waves completed in 228.410 s, workers 72.844/64.204/51.797 s. All six
poses were new: three passed placement preflight but could not close the
target, two failed physical clearance, one failed native return geometry.
Pose memory advanced without replaying earlier keys. No independent board
improvement: accepted Hub remains two opens/zero qualified structural DRC.

A read-only 106-pose straight-ray experiment took 2.762 s and did not provide
a useful ranking improvement. It was NOT installed as a production heuristic.
Evidence is `build/support-escape-ranking-20260927/native-ray-probe.json`.
Straight-ray blockage alone does not identify which endpoint prevents the
actual multilayer path, and is never a no-path proof.

Generic bridge diagnostics now count origin/local-POFV seats, ordinary via
guard failures, legal barrel trials, canonical/maze launch failures, per-layer
seat availability and middle-route failures. Counts are bounded, scalar and
private to one immutable plan. Observing them does not change search order,
operations, permissions or budgets. New regressions compare traced/untraced
operations and call order for barrel, launch, middle-route and successful
outcomes. No timeout or empty sampled frontier becomes an impossibility proof.

Native forensic replays on private families corrected the initial attribution:
the IC endpoint has **one valid local POFV launch** in both the physically legal
failed pose and the older electrically invalid one-open pose. The failed pose
has **zero seats at the divider-resistor end**: 159 ordinary barrel positions
passed the via guard but their canonical launches failed, and 32 bounded deep
launch retries failed too. The older one-open proposal has four local POFV
seats at that same resistor endpoint. Neither diagnostic proposal is promoted.
See `refused-native-trace/native-trace.json` and
`rejected-one-open-native-trace/native-trace.json` under the same evidence root.
Both source families stayed unchanged. Counts are search evidence, not a
waiver of the older proposal's actual decoupling/neckdown failures.

This exposed a separate generic planner omission: a clear passive opposite a
trapped owner was only eligible on an exactly two-pad net. A private divider
junction has three pads, so the valid R37/R38 cell was misclassified as a
shared multi-drop node and omitted. `cec_support_cell_topology.py` now accounts
for every native terminal: exactly one specified owner pin plus at most three
unlocked, ungrouped, two-terminal SMD supports within the existing 3-mm local
cell radius. Shared/multi-owner buses, additional owner pins, distant members,
mechanical anchors, THT, oversized or locked/grouped cells are refused. All
required members are carried together; final motion/copper/craft/admission
limits are unchanged. No board, reference, coordinate or electrical-value
exception was added.

Revision is `2026-09-27-private-support-cell-topology-v81`; geometry search
changed, so v80 rejection hints expire normally. Synthetic ablation reproduces
the old omission; translated/renamed/back-side and malformed/shared-cell cases
are covered. Combined regression: **697 passed and 8 subtests passed**, 11.24 s,
`build/private-support-cell-20260927/regression.log`. Fresh native PCIe control
took 11.304 s: zero opens/zero qualified structural DRC, unchanged source/native
copper and original hash; its old pair qualification issue remains visible.

Exact-policy Hub replan took 4.151 s, source families unchanged. It now proposes
R37 with required companion R38 before the existing C10 obstruction target,
with 152 bounded motion-domain-eligible proposals. These are not validated
placements. See `build/private-support-cell-20260927/hub-native-preview.json`.
The next cohort must exercise this genuinely new degree of freedom and inspect
the actual cell transaction, rather than blindly drain the C10 offset menu.
The dashboard stays on the same admitted hash until independent grading wins.

Successor: `cec-hub-residual-v81-20260927-o.service`, invocation
`5b7ef0235edf4059af97567257c3c731`, evidence `build/event-driven-hub-20260927-o/`.
At most two 240-second worker waves, 900-second outer cap, 8-GiB cap, ten-second
stop grace and one exact completion callback. Source n wave 2 hash was verified
unchanged as `3907452465...` before starting. Periodic heartbeat remains paused.

### Cohort o: actual private-cell trials, complementary endpoint blockage

Two waves completed in 252.540 s; workers 136.243 and 89.695 s. The first
established the new recipe's route history. The second tried two R37/R38 cell
poses and two C10 poses. The C10 poses were safe remeasurements after recipe
invalidation, not new geometric coverage. Both whole-cell poses were new.
The first hit fixed clearance/hole constraints. The second initially collided
with one policy-movable unlocked USB_VBUS branch; bounded evacuation removed
that branch, and the follow-up physical preflight passed. Target routing still
failed, so that entire speculative transaction was discarded.

The new bridge counters showed the opposite-end distinction clearly: the
rotated divider gained one local POFV seat, but the IC endpoint had none.
The earlier C10-only move had one IC seat but no divider seat. This suggests
coupled placement dependencies; it is not proof that all isolated poses fail.
Current accepted Hub is still two opens/zero qualified structural DRC with
unchanged input families. Nothing was published to the dashboard.

Four exact v81 rejection keys persisted. There remain 150 unvisited divider
cell proposals and 104 C10 proposals, not physically/electrically approved
placements. Allow one further bounded batch of untried poses with the same
history/recipe; if complementary-endpoint failure persists, do not drain both
menus mechanically. The next meaningful degree of freedom is a bounded
independent two-cell transaction, not simply forcing every member through one
rigid displacement. It must preserve/rebuild every incident branch, verify
intermediate electrical non-regression, and obtain full original-parent
independent admission only after a complete improvement. This is NOT yet
implemented or authorized as an admission bypass. Before introducing compound
transactions, audit pose-hint identity for effective required companions and
target context; historical compact keys lack that additional context and must
never be guessed into permission or silently reused for a different cell.

No solver code changed after the 697-test/8-subtest and PCIe native control.
Any following run retains every clearance, decoupling, neckdown, copper/fill,
motion and branch-preservation boundary, and the event-driven wakeup scheme.

Successor: `cec-hub-residual-v81-20260927-p.service`, invocation
`f939f5f19c4345c6984ccbe5407f8e73`, evidence `build/event-driven-hub-20260927-p/`.
At most three 240-second workers, 1200-second outer cap, 8-GiB cap, one exact
completion callback. Source o wave 1 remained `3907452465...` at launch.

### Cohort p: isolated search stopped; contextual memory and via-domain repair

All three waves completed without admission in 500.900 seconds. The selected
Hub remains exactly `3907452465...`, two opens/zero qualified structural DRC.
The R37/R38 poses that cleared placement still failed the target route; the
C10 trials repeated the complementary-endpoint obstruction or failed physical
or electrical preflight. No dashboard replacement was published. Another
identical isolated-pose menu-draining cohort was NOT launched.

Full craft replay of the earlier C10-only 0-degree/(0,+0.375 mm) intermediate
rejected it: tangent-supply proximity excess 0.526978 mm versus 0.25 mm and
loss of the original ground via's diameter/drill qualification. Its apparent
IC escape improvement is not a valid seed for another accepted transaction.
See `build/compound-support-preflight-20260927/c10-restored-craft.json`.
The fixed ground via has no surviving native producer receipt. Exact lineage
resolution works; there is no evidence permitting that locked via to move.
No locks, fabricated provenance, dimensions or final rules were changed.

Two generic fixes are now revision
`2026-09-27-contextual-pose-and-fixed-via-overlap-v82`:

* Rejection keys bind the effective required/expanded companions, target net,
  exact endpoint/access choice, motion and operation limits. Ref-only legacy
  hints and incomplete/unscoped raw reports remain retryable. Producer receipt
  contents and the explicit authored baseline also enter the source scope.
  Contextual hashes keep bounded storage without leaking enormous nested maps.
* The immutable small-via motion filter now checks native partial land overlap
  using the inverse rigid transform. It requires containment or disjointness,
  in addition to the existing reach constraint. A cheap filter passing is
  still not a reconstructed-dogbone or electrical qualification.

Native replay confirms that the exact C10/+0.375-mm pose is now refused before
routing as `immutable_local_via_partial_pad_overlap`, with unchanged inputs.
See `build/contextual-pose-domain-20260927/old-pose-replay.json`. This is the same
physical defect previously discovered only by the late dimensional authority,
not a stronger or weaker fab rule. The revised live proposal preview is in the
same directory. Finite proposal counts do not mean legal placements.

Combined regression: **751 passed, eight subtests passed**, 11.78 seconds.
Fresh immutable PCIe control: 11.085 seconds, original hash/native copper/source
family unchanged, zero opens/zero qualified structural DRC. Its pre-existing
pair-check failure remains visible. Evidence is in the same v82 directory.

### Next bounded experiment: two independently displaced support cells

`cec_compound_support_candidate.py` constructs exactly two disjoint native
two-terminal-SMD cells in a NEW private family, sharing the original parent's
four-reference/six-mm/eight-incident-track limits. Required companions cannot
be dropped. Each step re-resolves exact copper provenance. All recorded
incident boundaries remain restoration obligations; a refused second step
cannot publish the first as an incumbent. This is candidate construction,
NOT a new admission bypass or a completed production coupled-search stage.
Ten native translated/back-side/budget/refusal tests pass; the combined
compound/event/lineage focused suite passes 41 tests.

`tmp/probe_compound_support_20260927.py` will test at most 12 independent pose
pairs from current native planner targets, at most three detailed route trials,
with a 420-second internal budget. It performs existing geometry/DRC preflight,
bounded exact unlocked-branch evacuation/restoration where authorized, zero
protected-fill erosion, exact support/target reconnection and full electrical
craft measurement. It never publishes a board. Any promising result still
requires full independent original-parent placement/copper/fill/route admission
before it can replace `3907452465...`. A refused/interrupted partial remains
diagnostic only. Do not mechanically repeat this finite batch on completion.

The five-minute heartbeat remains PAUSED. The actual service completion event
will resume this task once; no periodic model polling or new task/agent.

Successor experiment: `cec-hub-compound-v82-20260927-q.service`, invocation
`2b3e86fb178d4eb990a0bc4dd63737d2`, evidence
`build/event-driven-hub-20260927-q/probe/`. At most 540 seconds outer runtime,
8-GiB memory cap, ten-second stop grace. Source is p wave 2's unchanged selected
incumbent. The callback is attached to this exact invocation, not its name alone.

### Cohort q: no gain; native incidence and internal-cell admission mismatch

The actual completion event resumed this task. q finished in 145.692 seconds:
12 compound constructions, ten physical-placement refusals, one electrical
geometry refusal and one post-evacuation route/restoration refusal. No candidate
was admitted; accepted Hub remains unchanged at two opens/zero qualified
structural DRC. Trial 11 closed neither the target nor the displaced USB_VBUS
branch; its exact support restoration also left a ground obligation open.
Do not reuse any q board as an incumbent or electrically valid intermediate.

Forensics found a real generic incidence bug: R37's USB_VBUS trace endpoint is
at `(63864998,63879999)` nm, while its pad centre is `(63864999,63879999)` nm.
The endpoint lies in the native land but the placement mover used exact centre
equality. It missed the incident branch, later classified it as an obstruction,
and attempted restoration against the old moving-pad position. The trace is
also grouped; grouped copper was disallowed by independent placement admission
even though the placement-obstacle stage could propose its removal.

Revision `2026-09-27-native-incident-pad-contact-v83` now uses native zero-margin
pad-copper contact, net and layer identity for incident tracks and internal-cell
terminals. Off-centre unlocked/ungrouped branches retain their actual far-end
obligation. Locked/grouped incident tracks remain byte-exact and retain their
actual old contact as an anchor. Grouped tracks cannot be evacuated during a
placement transaction. A native interior pad/trunk contact does not grant a
tap split or rip-up: the entire trunk remains fixed and one real native endpoint
is a restoration obligation. Ambiguous contacts remain refused. No tolerance,
group-name permission, artificial provenance or clearance waiver was added.

A second producer/admission mismatch was found: the mover already rigidly
transformed internal passive-cell paths, but independent branch admission
could prove only deleted/rebuilt incident chains. The new
`cec_rigid_cell_preservation.py` re-infers internal paths from the original
board, checks exact common transforms and identical net/layer/width/lock
properties, excludes grouped/locked/power/foreign-contact paths, and requires
every original native connected member to remain connected. It shares the
existing eight-changed-item bound; it trusts no worker UUID allowlist.
Arbitrary edits, missing boundaries or a one-nanometre non-rigid track deviation
are refused. All original full placement, copper, fill, craft and route gates
still apply. This proof is integrated into generic placement admission.

Native replay of q trial 11 under v83 now records the exact previously missed
R37 contact and independently proves the R37/R38 internal rigid transform at
zero coordinate tolerance. The COMPLETE branch proof correctly remains failed
until external support connections are restored. Source families were unchanged.
Evidence: `build/native-incident-contact-20260927/hub-contact-replay-v2/`.
An earlier replay rejected an unhandled interior ground contact; that led to
the preserved-trunk handling above, not removal or weakening of that boundary.

Full combined regression: **866 passed, eight subtests passed**, 12.53 seconds
in `build/native-incident-contact-20260927/regression-final.log`.
PCIe native control remains original hash, zero opens/zero qualified structural
DRC and unchanged native copper/source family; existing pair qualification
failure remains visible. See `pcie-control-final/native-control.json` there.

The next private compound experiment is justified by these contact/admission
fixes. It prioritizes individually measured physical preflight passes from the
same exact source, not by reference-specific coordinates. These are ordering
hints only: every pair must run all current native gates again. Required-cell
identity is respected, electrical-failure hints rank later, and no historical
pass or old rejection key authorizes/skips a current transaction. This changes
the tested pair order rather than repeating q's identical batch. The coupled
search itself remains experimental candidate generation, not an integrated
normal-wave strategy or a fab qualification.

Successor: `cec-hub-compound-v83-20260927-r.service`, invocation
`ff8f5b3d5ca8468f8389e57684d108ed`, evidence
`build/event-driven-hub-20260927-r/probe/`. Same unchanged p wave 2 source,
12 paired proposals/three detailed routes maximum, 420-second internal and
540-second outer budgets, 8-GiB cap, ten-second stop grace. One exact-invocation
completion callback; no periodic monitor. The separate ranking regression
passes; the final unchanged PCIe native control took 11.478 seconds.

### Cohort r: unchanged board, useful restoration proof and endpoint-search gap

The exact completion event resumed this task again. r completed in 117.379
seconds. All 12 compound constructions succeeded, but eleven were refused by
physical placement. Trial 8 cleared physical preflight and restored all five
explicit support anchors. Its whole GND net was connected; USB_VBUS still had
the original two components. The U11_OV1 target remained open. Final native
score was zero qualified structural DRC/two opens, but full electrical craft
correctly rejected a new C10 tangent-supply proximity excess of 0.320535 mm
against the unchanged 0.250000 mm limit. Nothing was admitted or published.
This is evidence that v83 fixed the stale support-anchor restoration failure,
not evidence that the compound placement is electrically acceptable.

Trial 8's native bridge diagnostics expose one legal seat at the IC and zero
at the moved resistor endpoint. It tried 133 legal barrel locations at that
end, with 101 canonical-stub refusals and 32 maze-stub refusals; no timeout.
These are bounded search outcomes, not an impossibility proof. The reported
original pair coordinates are historical witnesses: the actual certificate
and bridge origin correctly rebind to the moved native pad. There is no
stale-pad-coordinate route bug here. Trial 0's apparent clearance failure is
a genuine C10/R37 courtyard collision, not a routing problem.

### v84: share certified-island attachment search with component relocation

The generic via-target worker already planned alternative attachment points
on the two native-connected endpoint islands and reserved time for them.
The component-relocation worker did not: it called only the exact witness-pair
router. Thus moving a support cell silently lost an existing routing degree
of freedom, including the cell's other connected pads/tracks/vias.

`2026-09-27-shared-certified-island-closure-v84` extracts that finite portfolio
into `_close_certificate_component_pair` and uses it from BOTH via-target and
component/support reconnection. The same native item graph authorizes at most
six alternative pairs, within the existing eight-mm endpoint shift domain;
one wall-clock budget is shared with a reserved alternative slice. The solver
never substitutes a third same-net island, retries a non-search authority
failure, moves existing copper, relaxes clearance/width/POFV, or bypasses final
placement/copper/fill/craft/route admission. No board name, refdes or coordinate
special case was added. The experimental two-cell generator is still not an
integrated production wave strategy.

Synthetic native regressions cover renamed/translated/back-side boards,
toward/away support roles, a timed-out or exhausted primary witness, preserved
original copper, exclusion of a disconnected same-net island, invalid bounded
domains, and a ten-second lease split into 5/2.5/2.5-second attempts. The full
combined regression passes **896 tests plus eight subtests in 12.69 seconds**.
Fresh immutable PCIe replay is **10.775 seconds**, zero opens/zero qualified
structural DRC, exact original family/native copper unchanged. Its pre-existing
pair-check failure remains visible; this is not new fab approval. Evidence:
`build/shared-island-closure-20260927/{regression.log,pcie-control/}`.

Accepted Hub remains `3907452465...`, two opens/zero qualified structural DRC,
NOT fab ready. The next bounded native residual wave is justified by the new
shared attachment search, not by repeating r's 12 compound pairs. It starts
from p wave 2's unchanged selected incumbent, retains production history,
uses a 240-second residual budget and one wave, and must independently admit
any gain. One actual service completion event resumes this task; the old
five-minute heartbeat remains PAUSED. Do not repeat an exhausted unchanged
frontier without new diagnostic evidence or a tested generic correction.

Successor: `cec-hub-islands-v84-20260927-s.service`, invocation
`a0080cf666b443fa9f5a288072dcd71e`, evidence
`build/event-driven-hub-20260927-s/waves/`. Outer runtime 600 seconds, 8-GiB
memory cap and ten-second process-group stop grace. Completion bridge is
configured for this invocation only. The source/archive Hub and immutable
PCIe SHA256 values were rechecked immediately before launch and matched.

### Cohort s: no board gain; missing within-wave placement handoff

s completed in 151.142 seconds (137.675 seconds inside its 240-second residual
budget). Accepted Hub stayed two opens/zero qualified structural DRC and all
source-family files were unchanged. The shared certified additive path ran:
it tried two alternative pairs for U11_OV1 and five for USB_VBUS. Neither
closed. No component relocation was tried, so this run does NOT yet establish
that v84 improves live relocated-cell routing.

The initial support schedule deferred R37/R38 and C10 to the same-net route
window. The existing support refresh happened BEFORE the final atomic route
trials; it still deferred them. Those trials then returned a measured refusal
and a measured timeout, and the wave finished without revisiting placement,
despite approximately 102 seconds remaining in its residual budget. Saved
history could unlock placement next wave, but this was an avoidable within-wave
handoff gap, not a physical no-path proof or a reason to loosen design limits.

### v85: bounded same-wave support handoff after failed negotiations

`2026-09-27-inwave-support-handoff-v85` adds one post-negotiation refresh from
the newest live refusal ledger and a fresh native negotiation plan. It runs
only after the negotiation sweep admits NO geometry and reports no admissible
negotiation. Only attempts made since that fresh sweep started supply ordering
history; stale predecessor outcomes do not grant motion. A measured timeout
or bounded exhaustion changes scheduling, never placement/copper authority.
Worker errors do not count as measured search. All ordinary current native
targets, motion budgets, craft gates and final independent admission remain.

The earlier and later refresh share at most two distinct support targets,
at most two poses each. Already-tried targets cannot be retried by the second
refresh. Separate artifact prefixes preserve both sets of forensic evidence.
An admitted change or a newly measured resumable pose slice stops the local
placement phase for remeasurement; there is no added unbounded retry loop.

Full combined regression: **901 passed plus eight subtests**, 12.52 seconds.
Fresh immutable PCIe replay: **10.282 seconds**, zero opens/zero qualified
structural DRC, original family/native copper unchanged, existing pair-check
failure still visible. Evidence: `build/inwave-support-handoff-20260927/`.
Its `native-preview.json` replays s's final ledger on the exact unchanged Hub:
the fresh native planner now finds zero eligible copper-negotiation windows
and both support cells eligible. Thus current evidence is available without
waiting for another full routing pass. Preview took 0.866 seconds and changed
no source-family file; it is ordering evidence, not an admitted board.

The next one-wave production residual replay uses s's selected unchanged
incumbent, a 240-second residual budget, 600-second outer runtime, 8-GiB cap
and ten-second stop grace. Check actual `post_negotiation_support_refresh`
attempts, scoped history and every native admission gate on completion.
Hub remains `3907452465...`, two opens/zero qualified structural DRC, NOT fab
ready. No board was published. The five-minute heartbeat remains PAUSED;
the successor has one actual exact-invocation completion callback only.

Successor: `cec-hub-handoff-v85-20260927-t.service`, invocation
`6bfa391090f947a6a9c20f650c6856e8`, evidence
`build/event-driven-hub-20260927-t/waves/`. Source is s wave 0's selected
unchanged incumbent. The WSL volume had 59 GiB available at launch.

### Cohort t: within-wave handoff verified, four physical refusals retained

t completed in **181.813 seconds** (168.275 seconds inside the residual worker).
The new post-negotiation support handoff actually ran: two R37/R38 rigid-cell
poses and two C10 poses were measured, all against native physical preflight.
All four were correctly refused. R37/R38 collided with the preserved KVM_5V_IN
via or the preserved grouped USB_VBUS neckdown. C10 collided with preserved
U11_ILM/USB_VBUS/GND copper. These are genuine shorts/clearance/mask conflicts,
not missing layers or permission to move fixed power/other source groups.
Because none passed physical preflight, component-stage v84 attachment routing
still has not been exercised on a physically admitted live candidate.

The worker stopped at `placement_slice_complete` with real measured, unvisited
pose frontiers. It retained **four source-scoped contextual rejection keys**
in the selected `board.route-search.json`, revision v85. No source family
changed; accepted Hub remains two opens/zero qualified structural DRC, hash
`3907452465...`, NOT fab ready. No candidate was published.

The successor keeps the SAME solver revision and exact effort/motion/route
context. It starts from t's selected unchanged incumbent with those four keys,
so continuing the finite frontier does not require replaying those measured
poses or resetting route-stage cost history. At most three ordinary residual
waves, 240 seconds each, 900-second outer runtime, 8-GiB cap, ten-second stop
grace. Verify real `prior_skipped` counts and newly measured contextual keys;
unchanged visit counters or repeated identical poses are not progress. Stop
and diagnose any admission error or exhausted/non-advancing frontier. This is
bounded frontier continuation, not proof that any untried layout is valid.
No new solver edits or validation claims accompany this cohort.

Successor: `cec-hub-frontier-v85-20260927-u.service`, invocation
`da1e4b39217744c3a72b757bf4edec20`, evidence
`build/event-driven-hub-20260927-u/waves/`. Exactly one service-completion
callback is attached; the five-minute heartbeat stays PAUSED.

### Cohort u: routing of moved cells exercised, no admitted closure

u completed three waves in **375.682 seconds**. Native worker times were
113.331, 84.491 and 137.701 seconds. All selected boards remained two opens and
zero qualified structural DRC, same exact `3907452465...` copper. The normal
schedule reached supports early and consumed prior keys: intake counts 4, 9,
13; final selected sidecar contains 17 contextual keys. Three distinct primary
support poses passed physical preflight and entered detailed reconnection,
including v84's native-connected island alternatives. None closed the target.
All private rejected poses remain diagnostic, not board/fab candidates.

The history was not wholly repeating, but two C10 preflights were redundant:
t's final ledger reversed the pair and omitted optional diagnostic fields,
while u's initial ledger carried the opposite pair order and richer fields.
The full route-search key correctly distinguished those search contexts, but
the same fixed physical collision did not require another native trial.
Other repeated coordinates represented DIFFERENT effective cells (for example
C10 alone versus C10 plus R37, or R37/R38 versus that cell plus C_SS3); those
must remain distinct. Do not report all equal coordinates as repeated work.

### Physical rejection cache v1; geometric search stays v85

`cec_route_pose_history.physical_key` adds a separate `physical-pose-v1` domain.
It binds the moved reference, effective companion set, target net, rigid pose
and native operation limits, inside the existing exact board/rules/receipt/
motion-policy scope. It is recorded ONLY for a completed failing native
physical preflight with explicit new faults, successful copper-inventory
proof, matching moved cell, and classified FIXED clearance/short/mask/courtyard
conflicts. A route failure, electrical craft failure, movable collision,
incomplete proof, worker error or accepted move grants no such exclusion.
Those still use the unchanged full route-context key. Native rule and final
admission gates are untouched. A physically cached rejection does not consume
the next trial slot; reports expose `physical_prior_skipped` separately.

The forensic replay in `build/physical-pose-cache-20260927/forensic-key-comparison.json`
confirms the two redundant C10 checks match the new physical key while the
new R37 poses do not. It writes NO production history and promotes nothing.
Source PCB hashes match. The native geometric search revision deliberately
remains **v85**: this is additional stage-specific bookkeeping, not a change
to candidate geometry, routing, motion authority or fab policy. Existing
source-scoped route keys stay valid; no opaque old key is migrated or guessed.

The complete combined suite passes **920 tests plus eight subtests**. Initial
full-suite failures were eleven exact-report expectations missing the new
zero-valued counter, not solver regressions; those expectations were extended
without weakening their existing bounds. Additional malformed-proof tests
verify fail-closed behavior. Fresh immutable PCIe control is **10.593 seconds**,
zero opens/zero qualified structural DRC, unchanged native copper/source family;
existing pair qualification failure remains visible. See the regression and
native-control files in `build/physical-pose-cache-20260927/`.

The next bounded cohort resumes u wave 2's selected board and 17 valid v85
route keys, without resetting them. At most three waves/240 seconds each,
900-second outer bound, 8-GiB cap and ten-second stop grace. Confirm history
intake and actual new physical/route coverage. If the same endpoint-seat
bottleneck persists, investigate geometric proposal/access resolution rather
than mechanically expanding/restarting a finite menu. No accepted board has
changed; Hub remains two opens and is NOT fab ready. Event-driven only.

Successor: `cec-hub-physical-cache-20260927-v.service`, invocation
`7f747a53a1254cdb96b3121f2e3fd8a2`, evidence
`build/event-driven-hub-20260927-v/waves/`. Final full-suite rerun with retained
search revision v85: **920 plus eight subtests passed in 11.97 seconds**.
One exact-invocation completion callback; five-minute heartbeat still PAUSED.

### Cohort v: fixed-conflict cache worked; no board gain

v completed three waves in **287.136 seconds**. All twelve new primary support
placements failed native physical preflight; no selected board improved.
Accepted Hub remains exactly `390745246590805a36995cdbc141b4627c5557edb3170b44c6a22de525c89ad1`,
two opens and zero qualified structural DRC, NOT fab ready. Input families did
not change. History intake was 17/25/33; the final selected incumbent contains
**41** valid rejection keys. The physical-cache skip counter reached four for
each support in wave 2. Repeated checking of proven fixed conflicts has been
reduced, but this is not electrical closure. Do not run another identical
three-wave cohort merely to exhaust the old menu.

### Fine native contained-land proposal domain

Read-only native inspection found a concrete sampling gap. The current fixed
ground barrel is 0.35 mm wide in a 0.90 by 0.95 mm land: the inscribed radial
containment slack is **0.275 mm**, whereas the first nonzero coarse dogbone
ring was **0.375 mm**. The zero-offset sample plus dogbone-reach rings miss
small placements that can preserve full via-in-pad containment.

`cec_fixed_pofv_mobility.contained_land_proposals` now generates bounded fine
poses from each actual native land size and fixed barrel diameter. It samples
four fractions, eight directions and allowed cardinal rotations, with owner
and candidate caps. Dimensional slack is only a proposal scale: every pose is
checked using native pad containment at the actual integer displacement, then
against **all** immutable owners of the moved rigid cell. No proximity-based
ownership, board/refdes case, new via permission, clearance reduction or
replacement of existing native validation is introduced. These proposals feed
the existing occupancy/mobility ranking and ordinary physical, craft,
connectivity, copper-preservation and independent admission gates.

Synthetic regressions cover renamed and translated footprints, both board
sides, rectangular/circular/rounded lands, source immutability, actual native
via qualification, no-slack/generated/unlocked exclusions, bounded input
validation and deterministic prefixes. The combined suite passes **959 tests
plus eight subtests in 12.94 seconds**. Fresh immutable PCIe control is
**10.457 seconds**, zero opens/zero qualified structural DRC, unchanged native
copper and source family. Its pre-existing pair qualification failure is not
waived; this is not a new fabrication approval.

Evidence: `build/contained-land-search-20260927/`, especially `regression.log`,
`pcie-control/native-control.json`, and `native-preview.json`. The exact-source
proposal preview took 4.796 seconds without mutating input families. Fine
contained-land candidates now occupy ranks 2 and 3 in the obstruction support
menu, so this is an exercised search domain rather than an unreachable helper.
Ranking is still only a heuristic, not proof of physical/electrical legality.

The per-pose native search/operation semantics remain v85. This additive
proposal generator supplies NEW poses; it does not invalidate the measured
results for existing poses under the same exact source/policy/effort scope.
Keep the 41 valid old keys. Do not migrate opaque keys or reset history merely
because the new geometry samples were added.

Next experiment: **one** ordinary 240-second residual wave from v wave 2's
selected incumbent, with a 480-second outer limit, 8-GiB cap and ten-second
stop grace. Verify that contained-land proposals really reach native preflight
and reconnection; capture their complete failure stage if they do not improve
the board. Do not automatically repeat an identical no-gain cohort. Any
proposed winner still requires original-parent independent admission before
publication. No accepted artifact or dashboard selection has been changed.
The exact service-completion callback, not a periodic monitor, continues work.

Successor: `cec-hub-contained-land-20260927-w.service`, invocation
`bc0178ffdcb04d73b841f68a71d83d2b`, evidence
`build/event-driven-hub-20260927-w/waves/`. One exact-invocation completion
callback; five-minute heartbeat remains PAUSED.

### Cohort w: fine placements are physically viable, target still open

w completed its single wave in **118.306 seconds**; the residual worker used
103.996 of its 240-second allowance. Neither selected copper nor source family
changed: accepted Hub is still two opens/zero qualified structural DRC, exact
`3907452465...`, NOT fab ready. No rejected board was published.

The two new contained-land placements really reached native reconnection.
Both passed electrical geometry and physical preflight and restored **3/3**
disturbed support anchors. GND remains one connected component and USB_VBUS
retains its original two components; anchor restoration is not reported as
whole-net closure. Both target attempts still refused. The two other attempted
support-cell placements failed physical preflight.

The first fine-pose trace gives useful limits: U11 had zero legal via seats
after completing the tested local domain, while the far divider endpoint ran
out of its slice with zero seats. No global impossibility was proved. Native
connected-island alternatives were tried, but each received only about two
seconds. Increasing time cannot by itself certify a geometrically blocked
pin, so do not describe this result as just a timing problem.

### v86: reclaim unused support leases once, inside the original deadline

A distinct generic scheduler defect is demonstrated by the same trace. The
35-second exact-reconnection worker fairly allocates roughly 8.75 seconds to
the target before restoring three branches. Those branches complete quickly,
yet it returned after **10.264 seconds** and discarded the unused lease.

`_exact_relocated_connections_worker` now gives a timed-out target **one**
larger retry after all exact support-anchor obligations finish. The same two
live native islands, routing rules, source groups and final admission gates
apply. It reclaims only time remaining inside the original worker deadline,
retains the 20-second per-pair cap by default, and requires at least one second
of additional search allowance. It does not retry a completed no-path search,
invalid endpoint, failed support restoration, successful target, disabled
policy or an equal/smaller remaining lease. Reports preserve both attempts and
why recovery ran or did not. No full-net closure is inferred from anchor counts.

New options are bounded/validated before native access. Synthetic tests use
renamed, translated and backside native fixtures, prove same-island scope,
one retry at most, total shared deadline, exact support obligation handling,
success/failure accounting and negative cases. The combined suite passes
**979 tests plus eight subtests in 13.16 seconds**. Fresh immutable PCIe replay
is **10.680 seconds**, zero opens/zero qualified structural DRC with byte-stable
source family and unchanged native copper. Existing pair qualification is not
waived. Evidence: `build/reclaimed-support-budget-20260927/`.

This DOES change per-pose search semantics, so algorithm revision is now
**2026-09-27-reclaimed-support-budget-v86**. Old scoped histories are not
silently reused or migrated. To avoid blindly restarting a large rejected
menu, the next experiment is a **single private replay of w's already
physically clear first fine pose**, against the exact w source. It repeats
the same 35-second exact-worker budget under v86 and records whether the
reclaimed lease changes the outcome. This is diagnostic construction, not
independent admission, a selected seed or publication. The helper now also
rejects a mismatched report/source hash and prints compact diagnostics.

If there is no gain, inspect the actual completed endpoint-seat and same-layer
search evidence; do not restart the same native replay indefinitely. A target
closure is only a possible improvement and still owes full original-parent
placement, branch, protected copper/fill, electrical craft and route admission.

Successor diagnostic: `cec-hub-reclaimed-budget-20260927-x.service`, invocation
`d84eb2a23d71416cb4ea4102419b1178`, evidence
`build/event-driven-hub-20260927-x/replay/native-trace.json`. 180-second outer
limit, 8-GiB cap, ten-second stop grace; one exact-invocation completion callback.
Five-minute heartbeat remains PAUSED.

### x completed: unused budget reclaimed; geometric refusal remains

The single private replay finished in **27.413 seconds**. It restored 3/3
support anchors and used a second 20-second target lease out of 24.692 seconds
remaining. The result changed from a short-slice timeout to
`certificate_pair_no_exact_clear_path`, `timed_out: false`. Both endpoints
finished the tested local via-seat domain with zero seats, and native-island
alternatives also failed. This is a useful diagnostic distinction, **not** a
global no-route proof and not an electrical improvement. Accepted Hub remains
two opens/zero qualified structural DRC. Input families are unchanged; the
private replay is not a routed candidate or publishable seed.

The run was short enough to expose a callback-startup race. It completed and
systemd collected the transient unit before the listener subscribed, so the
old listener raised `NoSuchUnit`. This turn reviewed the actual output itself;
do not resend x's existing claim or pretend it delivered a completion callback.

### Fast-completion wakeups now retain exact invocation identity

New `scripts/cec_retained_wave_run.py` is the default launch path for future
event-driven jobs. It always sets `RemainAfterExit=yes`, bounded runtime and
memory, ten-second stop grace, separate per-job logs and a new output directory.
It records the actual InvocationID in `launch.json`. Do not drop back to a raw
unretained transient launch. The retained completed unit uses no worker PID.
After callback delivery and review, verify the exact invocation and MainPID=0
before stopping that completed unit to release its retained metadata.

`cec_systemd_completion_event.py` recognizes retained `active/exited` only with
the explicit retention flag and nonzero native exit timestamp, still bound to
the exact InvocationID. A missing unit now emits a structured
`unit_unavailable/requires_result_review` event instead of crashing silently;
it is never reported as successful completion. No timer or periodic task wake
was added. A live test launched `/usr/bin/true`, waited until it had exited,
and then successfully obtained `service_completed` with its retained exact
invocation. The deliberately missing-unit test produced review-needed rather
than success. The completed synthetic unit was stopped after verifying PID=0.

The final combined suite passes **991 tests plus eight subtests in 13.29
seconds** (`build/reclaimed-support-budget-20260927/regression-final.log`).
The previous 10.680-second immutable PCIe control is still the current v86
solver control; subsequent edits only affect diagnostic ordering/launch/event
handling, not its PCB. No source board, fab gate or accepted archive changed.

Next bounded experiment: independently move the two native-certified support
cells together using `cec_compound_support_candidate`, the new fine land poses,
and current gates. The diagnostic coordinator now accepts at most twelve
explicit prior reports as **ordering hints only**, each checked against the
exact input PCB hash and effective cell identity. It can reuse known physical
preflight results from earlier cohorts to avoid prioritizing already-poor
individual seats, but EVERY new combination must rerun native geometry,
preflight, fill, connectivity/restoration and electrical craft checks. No
combination is skipped or approved from history; malformed dimensions,
missing ownership and source changes remain hard failures.

The experiment has at most twelve pair proposals, three detailed reconnections,
420 seconds internally/540 seconds externally, and no automatic publication.
All successes remain speculative until independent admission against the
original parent. This tests a new coupled geometry domain; it must not become
an identical no-gain replay loop. Keep the current two-open archive on the dash.

Retained successor: `cec-hub-fine-compound-20260927-y.service`, invocation
`c987f3be8f994c039b0f317707ecd6c3`, evidence
`build/event-driven-hub-20260927-y/probe/summary.json`. The new retained launcher
wrote `launch.json`; one exact-invocation callback is attached. After completion
review, verify that invocation and MainPID=0 before stopping its retained unit.

### y: coupled native trial closed no net; late proximity refusals exposed

y finished all twelve pair proposals in **184.971 seconds**. Nine were refused
by physical preflight. Three passed physical preflight and restored **5/5**
support anchors, but target routing still refused without a timeout and each
failed electrical craft. All three ended at two opens/zero qualified structural
DRC; no potential gain, admission or publication. Source families are unchanged.

The craft defect was consistent: supply-proximity excess for the moved bypass
was **0.315470 mm** or **0.376191 mm**, above the existing **0.250000-mm** limit.
The prior early gate tested absolute ground distance only and let those
placement-dependent failures consume full physical/routing effort. This is a
missing early constraint, not permission to relax the proximity requirement.
The retained callback delivered successfully. After checking the exact y
invocation and MainPID=0, its completed retained unit was stopped.

### v87: conservative necessary proximity bound before routing

`cec_support_craft_gate.proximity_geometry_faults` uses the current authority's
native pin coordinates and raw package-derived tangent reference. It rejects
only when **both** existing proximity modes must fail: isolated supply proximity
and the optimistic complete-loop mode that future qualified dual via-in-pad
returns might allow. This avoids mistaking a temporarily disconnected return
in a staging board for proof that a valid future return cannot be restored.

The new bound uses the actual configured supply/loop limits and the existing
return-constrained reference helper. It deliberately defers shared-pin cases,
rail-to-rail cells, missing geometry and ambiguous references to the full final
oracle. It grants no electrical acceptance, copper movement, via or clearance
authority. Coordinates/raw references avoid display-rounding artifacts.
The final craft oracle is unchanged. Revision is now
**2026-09-27-proximity-preflight-v87**; do not migrate stale pose-search keys.

The native replay reconstructed all three y placements from the exact accepted
parent and caught **3/3** before any router invocation in **12.140 seconds**,
with no new bound failures on the parent and no input-family changes. This is
not an apples-to-apples total wave speedup measurement. Temporary reconstruction
families were automatically cleaned; only compact evidence remains in
`build/proximity-preflight-20260927/native-replay/native-preflight.json`.
The combined suite passes **1,007 tests plus eight subtests in 13.89 seconds**.
Fresh immutable PCIe control is **11.486 seconds**, zero opens/zero qualified
structural DRC, source family and native copper unchanged; its existing pair
qualification issue remains. See `build/proximity-preflight-20260927/`.

The next diagnostic enables bounded geometry ordering before the eight-pose
individual menu cap. At most 24 poses per cell, eight preferred passes per cell,
and a shared 120-second allowance are measured using temporary native boards.
An individually rejected or unmeasured pose is DEPRIORITIZED, never excluded or
used to reject a compound pose from history: a second moved cell can change
its context. Every proposed combination repeats current full gates. Keeping
all input candidates avoids making the screening heuristic an admission rule.

This changes which geometrically plausible seats reach the same twelve-pair /
three-route experiment. Overall 420-second internal and 540-second service
bounds remain. Do not rerun the old identical combination list without this
new evidence. Accepted Hub stays two opens/zero qualified structural DRC,
`3907452465...`, NOT fab ready; keep the accepted archive on the dashboard.

Retained successor: `cec-hub-geometry-ranked-20260927-z.service`, invocation
`8bbda68ca8dd494eb4f6f7fff3da9002`, evidence
`build/event-driven-hub-20260927-z/probe/summary.json`. One exact completion
callback; verify its identity/PID before releasing the completed unit metadata.

### z: better electrical poses, still no admitted routing gain

z completed in **254.195 seconds**, with all source families unchanged. Native
geometry ordering measured 22 C10 poses for eight passes and eight R37-cell
poses for eight passes. Twelve compound proposals were tested; nine failed
physical preflight. Three passed physical AND final electrical craft, restored
all five support anchors, and retained zero qualified structural DRC. This
improves on y's late proximity failures, but none closed the target: all remain
at **two opens**. Their exact local route domains completed without a timeout
and reported no legal pin seats. No trial was adopted or published. The
accepted Hub is still `3907452465...`, NOT fab ready. The z callback delivered;
its exact completed invocation/PID were verified and the retained unit stopped.

### v88: endpoint-owner search and independent admission scope agree

The ordinary w report revealed an entirely disabled degree of freedom. Its
certified endpoint-owner planner selected U11 with C26/C10/C22 and D6 with
R10/C_SS3. The stage supports three-to-sixteen-pad SMD owners, but the shared
motion envelope required **exactly two pads for every member**. All sixteen
legacy poses per owner failed scope before physical or routing work; occupancy
generation was also suppressed by the same early filter. Independent placement
admission had the same two-pad restriction. Target planning was not evidence
that any actual owner trial had run.

`cec_support_motion.limits` now has a validated, bounded owner-only pad limit,
defaulting to two. Only the endpoint-owner stage selects the existing small-IC
scope, before occupancy generation AND final pose filtering. Companions remain
two-pad SMD parts. Locks, groups, policy-fixed parts, holes, the total four-ref
bound and six-mm per-member motion bound remain enforced. The planner counts
the owner in that total (previously it could propose owner plus four supports),
and propagates a tighter configured ref count when present.

Independent admission does not trust a planner/mover claim. It infers the moved
small owner from native source/candidate populations and refuses multiple ICs.
`endpoint_owner_connectivity` requires at least one newly connected original
pad on an owner net, and retention of every surviving native member of every
original owner-pad connected component. A neutral move, new free stub, lost
return, changed identity, immutability violation or oversized owner is refused.
The existing eight-item independent copper-rebuild limit, exact component/pad
identity, protected fill, source policy, power snapshot, physical/craft checks
and final native route grade are unchanged. Search still has a historical
64-branch owner-work ceiling; that is NOT an admission allowance, and any
result outside the independent eight-item bound remains invalid.

Revision: **2026-09-27-endpoint-owner-scope-v88**. Do not guess-migrate old pose
history across this semantic change. Forty-two new synthetic/native cases cover
renamed and transformed/back-side fixtures, owner versus companion scope,
planner cardinality, pre-generation and post-generation filtering, immutable
boundaries, native connectivity benefit and the independent transaction.
Combined validation: **1,049 tests plus eight subtests**, **13.82 seconds**.
Fresh immutable PCIe replay: **11.2 seconds**, zero opens/zero qualified
structural DRC, source family and native copper unchanged. Its pre-existing
pair qualification failure remains visible; no new fabrication approval.

The read-only native preview replays the old recorded targets against the
exact accepted source to verify scope behavior, not to authorize a move. U11:
70 generated/motion-eligible, 54 fixed-via-eligible. D6: 80 generated, 72
motion-eligible, 68 fixed-via-eligible. Previously both had zero. Preview took
**4.33 seconds**, no routing or file-family mutation. Evidence and regression
log: `build/endpoint-owner-scope-20260927/`. Production must still derive fresh
refusal evidence before searching these owners.

One normal residual wave is running under retained service
`cec-hub-endpoint-owner-20260927-aa.service`, exact invocation
`090f5fdb54a24e158e12bc8058e0c7b7`. Evidence root:
`build/event-driven-hub-20260927-aa/waves/`. It has a 240-second residual lease,
480-second external limit and 8-GiB memory ceiling. Source is w's exact
`3907452465...` baseline, not a private compound trial. One actual completion
event wakes the same task; the five-minute heartbeat stays paused. Review real
scheduled owner attempts, refusals and independent admission before any new
cohort or dashboard publication. Release the retained unit only after checking
the exact invocation and MainPID=0. Storage remains about 59 GiB free.

### aa: valid owner menu, bounded stage handoff rather than native owner trial

aa completed in **182.171 seconds**, no improvement, source families unchanged:
accepted Hub still two opens/zero qualified structural DRC. Three of four
post-negotiation support trials failed physical DRC; the fourth was refused by
the new early proximity check in **2.33 seconds**, before routing. The v88 scope
fix generated 70 U11-cell poses with 54 fixed-via-eligible, but **scheduled zero
owner trials** in this wave. The effort log explains why: after the bounded
support pass, the existing coordinator deliberately sets
`placement_slice_complete` at `post_negotiation_support_refresh`. It had spent
12 of 64 trial slots and 168.730 of 240 worker seconds. A planned owner target
or a valid menu is still NOT evidence that owner routing ran.

Do not assume this is another global-budget defect: the same pipeline has an
early support/owner phase for the next wave, selected by measured predecessor
history. The first v88 run correctly discarded stale v85 search history. aa
now stores seven valid scoped rejection keys and the relevant measured
negotiation timeout in its selected baseline `board.route-search.json`. Its
board SHA remains exactly `3907452465...`. Continuing from that family should
select the early placement phase and skip the already rejected poses. No
solver code or bounds were changed merely to bypass this intentional handoff.
If the next wave still schedules no owner trial, inspect the actual history
intake and stage condition before another run.

aa's actual completion callback delivered. After verifying its exact invocation
and MainPID=0, the retained unit was stopped. The successor is one bounded
normal residual wave using aa's selected baseline WITH current history:
`cec-hub-owner-continuation-20260927-ab.service`, invocation
`cdbf80476c1b4a68b4e2f526dab8d4a5`. Evidence:
`build/event-driven-hub-20260927-ab/waves/`. Same 240-second residual lease,
480-second service limit and 8-GiB ceiling. One event-driven completion callback;
five-minute heartbeat remains paused. No new board published or dashboard tab.

### ab: history handoff worked; native IC trials exposed ownership assumptions

ab finished in **132.957 seconds**, no admitted improvement, input families
unchanged. It consumed all seven valid v88 history keys and selected the early
support/owner phase, as intended. Both certified owners received one native
trial. The scheduler was NOT disabled; no workaround or budget reset was made.
One support proposal passed physical preflight but still failed to close the
target; another failed physical DRC, and two failed early electrical geometry.

Both owner moves refused within 0.36 seconds at incident-pad ownership:
U11 had three traces wholly contained within a moved pad and two traces shared
by moved pads. D6 had eight contained and two shared traces. These traces were
not eligible for the independently proved internal rigid-path transform, and
the branch inspector's unique-owner rule rejected the entire move. None had
to be assigned new ownership: keeping their original geometry is sufficient
provided all affected pads restore their original native connections.
ab's exact completed invocation/PID were checked and its retained unit stopped.

### v89: ambiguous ownership becomes a fixed native boundary, not edit authority

`cec_pad_incident_tracks.inspect` now conservatively preserves contained and
shared traces. Native pad shape at zero margin, net/layer identity and actual
native connectivity must agree. A wholly contained trace contributes an
actual, deterministic source endpoint as an anchor. Each pad touching a shared
trace contributes its own contact obligation. Such traces receive
`fixed_boundary=True`; the mover retains their entire native copper exactly,
even if an existing producer receipt could otherwise permit changes. Absent
native connectivity still fails. Independently proved internal rigid chains
remain a separate case; this does not authorize arbitrary trunk transforms.

The inspector accepts iterable pad inputs safely. Twenty-six new cases cover
contained/shared/overlapping contacts, renamed parts, translated back-side
boards, ordinary/locked/grouped/producer-tagged copper, exact retention,
separate restoration obligations, actual disconnection before repair and
native reconnection after it. Negative tests refuse non-native contacts.
Existing ambiguity tests now assert immutable boundary behavior rather than
expecting a blanket refusal. No final placement, DRC, craft, source-copper/fill,
native original-component retention or independent admission bound is waived.

Revision **2026-09-27-fixed-shared-pad-boundary-v89**. Combined suite:
**1,075 tests plus eight subtests**, **13.65 seconds**. Fresh immutable PCIe
control: **11.602 seconds**, zero opens/zero qualified structural DRC, source
family/native copper unchanged. Its prior pair qualification issue remains.

Private native reconstruction of the two ab owner poses now succeeds and
preserves all **15 previously ambiguous tracks exactly**. U11 changes only two
other parent copper items; D6 changes three, both below the independent eight-
item bound. Both pass early electrical geometry. This is construction and
geometry evidence, NOT routing or final physical/admission evidence. Replay
took **9.596 seconds**, made no source-family changes, invoked no router and
cleaned temporary families. Evidence: `build/fixed-pad-boundaries-20260927/`.

Accepted Hub remains `3907452465...`, **two opens / zero qualified structural
DRC**, NOT fab ready. No new archive or dashboard image. A bounded two-wave
normal residual cohort now exercises fresh v89 evidence and the subsequent
history-driven IC stage; do not migrate stale v88 pose keys. Retained service
`cec-hub-fixed-boundaries-20260927-ac.service`, invocation
`efcc5b5f094346a48e605ba5629801cf`; evidence
`build/event-driven-hub-20260927-ac/waves/`. Limits: 240 seconds per residual
lease, 720 seconds externally, 8 GiB RAM. Source is ab's unchanged accepted
baseline. One actual completion callback wakes this task, no polling. Check
physical/craft outcomes, complete restoration and independent original-parent
admission before retaining anything. About 59 GiB free at launch; preserve the
16-GiB floor. Five-minute heartbeat remains paused.

### ac: source-preserving IC moves now reach real physical checks

ac completed two normal waves in **324.587 seconds**, no admitted gain and no
input-family mutations. Wave zero refreshed current-revision evidence; wave
one consumed seven current scoped keys and ran the early owner phase. Both
native IC moves now pass construction and early electrical geometry. Their
first poses failed actual clearance checks, correctly:

- U11 cell: C26's ground land moves too near a retained PSU_5V_KVM stub.
- D6 cell: its supply land moves too near retained USB_D_N copper; R10 also
  collides with generated USB_CC2 copper. The fixed USB conflicts prevent
  treating this as a simple generated-trace evacuation.

No source trace was unlocked, spacing relaxed or candidate admitted. These are
legitimate physical refusals, not evidence requiring another solver exception.
The post-run family stores **18 current v89 scoped rejection keys**; the exact
board remains `3907452465...`. Only one eligible IC pose per owner has received
physical testing so far. Continue the finite measured frontier, rather than
restart stale menus or infer global impossibility. Support proposals skipped
two and one known physical poses respectively in wave one; history is active.
ac's exact completed invocation/PID were checked and its retained unit stopped.

A three-wave normal residual continuation is running without solver edits:
`cec-hub-physical-frontier-20260927-ad.service`, invocation
`5e5cea6c2ac1434ea414a89c82987c3a`, evidence
`build/event-driven-hub-20260927-ad/waves/`. It starts from ac wave-01's accepted
baseline WITH the 18-key history, same v89 revision. Bounds: 240 seconds per
residual lease, three waves, 960 seconds externally, 8 GiB memory. Source hash
verified, about 59 GiB free. One actual completion callback; the five-minute
heartbeat stays paused. Check whether subsequent trials are genuinely new and
whether they pass physical/craft and full native admission before any further
cohort. Accepted Hub remains two opens/zero qualified structural DRC, NOT fab
ready, no new archive or dashboard tab.

### ad: real frontier advancement, plus one costly history-loss repeat

ad completed three waves in **478.403 seconds**, no admitted board gain or
source-family changes. History intake advanced **18 → 28 → 35** and finished
with **44** scoped keys. Most native proposals were new: nine physical DRC
refusals, six early electrical-geometry refusals and three failed target-route
transactions appeared in the primary sweeps. One target-route transaction was
an identical repeat across waves, consuming **64.733 seconds** (about 14% of
the cohort). The same-coordinate expanded cell with an extra companion was a
distinct search, not the duplicate; effective cell identity was checked.

The repeated base-cell search key was absent from the previous wave's saved
history despite a completed 64.752-second native refusal. Its report had
**48,823** nested diagnostic containers. The history extractor's whole-tree
depth-first traversal exhausted its 20,000-container guard before reaching the
owning decision row. The subsequent 29,843-container report happened to visit
the row earlier and retained it. This was a reporting-volume scheduling defect,
not missing native rejection evidence or a legitimate changed search scope.
The exact completed ad invocation/PID were verified and its retained unit stopped.

### Decision-envelope history repair: diagnostics cannot starve decisions

`cec_route_pose_history._decision_records` now follows decision envelopes
(`plan`, `sweep`, `attempts`, and explicit route-aware expansion) rather than
recursing through every native copper/certificate/occupancy measurement. New
stage names work through the common sweep schema. A completed attempt is read
before its subordinate expansion; its large diagnostic payload is opaque.
Actual nested worker errors still reopen the exact pose, while lookalikes
inside native measurements cannot create or cancel decision records.

Traversal bounds remain finite. If the decision-envelope walk itself exceeds
depth, width, count or list limits, extraction produces no partial rejection
proof and merging clears the prior exclusions with `scan_incomplete=True`.
This avoids hiding an unvisited error that should reopen a formerly rejected
pose. The native replay extracts all **six decision records** from each of the
two problematic reports and recovers the previously missed base-cell rejection.
Old report/history files are not rewritten. Evidence:
`build/pose-decision-scan-20260927/native-history-replay.jsonl`.

Sixteen new regressions cover large sibling and row diagnostics, reordered
fields, nested transaction errors, diagnostic impostors, future stage names,
incomplete/cyclic envelopes and accepted rows. Combined suite: **1,091 tests
plus eight subtests**, **14.39 seconds**. Fresh immutable PCIe replay:
**10.988 seconds**, zero opens/zero qualified structural DRC, native copper and
source family unchanged. Its earlier pair-qualification problem remains.

The geometry/search engine, key identity and scope semantics did not change:
revision deliberately remains **2026-09-27-fixed-shared-pad-boundary-v89**, and
its valid native rejection keys remain usable. This is not an authority/key
migration or a waiver of any final gate. No accepted Hub improvement yet:
`3907452465...`, two opens/zero qualified structural DRC, NOT fab ready.

Three bounded continuation waves now use ad wave-02's exact accepted geometry
and **44-key** history: `cec-hub-decision-history-20260927-ae.service`, invocation
`4fafcd08336a43acb402c9992a91cf11`; evidence
`build/event-driven-hub-20260927-ae/waves/`. Same 240-second per-wave residual
lease, 960-second external bound, 8 GiB RAM and about 59 GiB free. A single
actual completion event wakes this task; five-minute heartbeat stays paused.
Verify actual identity skipping and fresh physical/route outcomes before any
successor. Do not mistake different companion cells for duplicates or repeated
nearby micro-poses for meaningful layout progress without inspecting them.

### ae: no expensive duplicate; one IC pose restores 24 anchors but no target

ae completed three waves in **402.286 seconds**, no admitted gain or input-family
mutations. History intake advanced **44 → 54 → 64**; the expensive duplicated
R37 base-cell search did not recur. Identical coordinates alone are still not
duplicate identities when required companions or endpoint/search context differ.
The final wave tried a U11-cell translation that passed physical preflight and
restored **all 24 support anchors**. Target closure still returned
`certificate_pair_no_exact_clear_path`, without a timeout. No global no-route
claim follows from that bounded local domain. Other poses failed genuine
clearance or electrical proximity checks. Accepted Hub remains at two opens.
ae's exact completed invocation/PID were checked and its retained unit stopped.

### v90: owner grouping requires signal or supply affinity, not ground alone

Native inspection found that the endpoint-owner planner's `owner_nets` included
common returns when selecting the nearest two-terminal companions. D6's chosen
R10 and C_SS3 shared **only GND** with it; they were not a functional support
cell, but were being dragged into USB_CC2 and other obstacles. U11's C26, C10
and C22, by contrast, each share a genuine owner supply as well as ground.
This is a graph-association defect, not a clearance rule to relax.

The planner now requires a shared **non-ground signal or supply** using the
existing generic return-net classifier. Ground-only proximity does not create
motion coupling. It does NOT remove parts, undo their routing, or waive
decoupler assignments/proximity: full geometry and final electrical craft gates
continue to validate every move. Locks/groups, native via boundaries, four-ref
and six-mm limits, eight-item independent copper bound, frozen fills and all
native admission remain unchanged.

Revision: **2026-09-27-signal-affinity-owner-cell-v90**. Cell-selection semantics
changed, so old v89 keys are not guess-migrated. Twelve new tests cover renamed
parts, six standard return aliases and back-side geometry: a closer unrelated
ground-only part cannot consume the bounded cell's true supply-support slot.
Combined validation: **1,103 tests plus eight subtests**, **14.79 seconds**.
Fresh immutable PCIe native control: **11.158 seconds**, zero opens/zero
qualified structural DRC, source family and native copper unchanged. Its prior
pair-qualification issue remains visible.

Before/after native evidence is in `build/owner-association-20260927/`. Fresh
native planning retains U11's three companions and selects **D6 alone**, with
109 fixed-via-eligible poses versus 68 previously. This is a larger legal motion
proposal domain, not placement or routing approval. The after preview took
**5.239 seconds**, no routing or source-family changes. It rechecks the native
endpoint geometry against the exact source-bound refusal record.

Two normal bounded waves now exercise v90 fresh evidence and its next-wave
history handoff: `cec-hub-owner-affinity-20260927-af.service`, invocation
`f44ab0e260854220ac67605dba87bde1`; evidence
`build/event-driven-hub-20260927-af/waves/`. Source is ae wave-02's exact
unchanged accepted baseline `3907452465...`, NOT a neutral private IC pose.
Bounds: 240 seconds per residual lease, two waves, 720 seconds externally,
8 GiB RAM; about 59 GiB free. One real completion event wakes the task. The
five-minute heartbeat remains paused. No board republished; still two opens/
zero qualified structural DRC, NOT fab ready. Check actual grouping, physical
and craft outcomes, full restoration and independent admission before promotion.

### af: grouping corrected, but bounding-box ranking selects physical conflicts

af finished two waves in **323.213 seconds**, both no progress; accepted Hub
remains `3907452465...`, two opens/zero qualified structural DRC. Input families
were unchanged. Wave-01 tried D6 alone as intended, but the selected pose failed
physical admission with 23 authored-copper collisions. U11's selected cell pose
also failed on the retained PSU stub. R37/R38 reached target routing without
closing the target; C10 poses failed necessary electrical proximity checks.
The completed exact invocation and zero PID were verified and the retained
unit stopped. No private candidate was published or adopted.

### Native land/copper ranking, not package bounding-box assumptions

`cec_pose_copper_score.NativePoseCopperScore` measures actual native pad shapes
against saved tracks, vias and stationary pads on their shared copper layers.
It uses both items' saved-project netclass/native local clearance and the board
floor, counts new contacts separately from existing contacts, and retains
incident copper in its snapshot: touching a movable pad is not deletion
authority. Same-net copper is not a foreign obstacle; net-zero copper is.
Stationary lands and unreceipted locked items receive fixed-obstacle priority.
Explicit generated-item evidence affects ordering only, never edit authority.

The reversible native transform covers all members of a bounded rigid cell
and restores their poses in `finally`, including on native exceptions. The
snapshot keeps its native owners alive. Zones, spatial custom rules, all
physical/craft checks, refill, complete restoration and independent original-
parent admission remain mandatory. The new measurement is **ranking only**:
it neither removes a candidate nor declares it legal, and it may conservatively
count copper a later proven local transaction can move.

Both the individual occupancy menu and the combined endpoint/mobility menu
rank these native contacts before approximate package-box overlap/copper-hit
counts. Those approximate measurements remain secondary hints. The mobility
graph's four-member capacity now explicitly includes its owner, preventing a
fifth member from being proposed when no separate motion filter is supplied.

Read-only native replay of the identical source/certificate targets, **1.439
seconds**, shows the former first U11 pose has **one** new native contact and
the former first D6 pose has **18**. Both first-ranked replacements have
**zero** under this advisory measurement. D6's legal-looking tiny moves had
previously lost to a package bounding-box overlap, while the distant selected
pose crossed actual retained conductors. This is useful candidate-selection
evidence, **not a routed-board improvement or a full physical pass**. Evidence:
`build/native-pose-ranking-20260927/{before,comparison}.json`.

Thirty-one new regressions exercise native front/back rotated geometry,
translated/renamed parts, same-net/net-zero cases, layer spans, through vias,
incident copper, stationary and companion lands, both sides' saved-project
clearance, native-error rollback, bounded cells and real occupancy top-K order.
Combined suite: **1,134 tests plus eight subtests**, **14.84 seconds**. Fresh
immutable PCIe native control: **11.574 seconds**, zero opens/zero qualified
structural DRC, source family and native copper unchanged. Its existing
pair-qualification issue remains visible. Evidence lives under
`build/native-pose-ranking-20260927/`.

Repair revision deliberately remains **2026-09-27-signal-affinity-owner-cell-v90**:
only proposal ordering changed, not the feasibility or execution of an exact
existing pose. Valid prior failure keys remain usable; no history reset or
guessed migration is necessary. Do not mistake fewer predicted contacts for
route closure, and do not launch endless micro-pose cohorts if native routing
continues to show no useful new frontier.

Two bounded normal continuation waves now exercise that measured ranking
improvement: `cec-hub-native-pose-ranking-20260927-ag.service`, invocation
`ff1c4ee9fd3e4ad38c9406f3d7704116`. Source is af wave-01's unchanged accepted
baseline, preserving v90 history. Evidence:
`build/event-driven-hub-20260927-ag/waves/`. Bounds: 240 seconds per residual
lease, two waves, 720 seconds external, 8 GiB RAM; about 59 GiB free. ATX pair
authority, ATX board, immutable PCIe and source Hub hashes were rechecked before
launch and match the established values. A single actual completion event
wakes this task; five-minute heartbeat remains paused. Check actual physical
and electrical pass rates and routing gain before any successor. No board has
been republished; two opens/zero qualified structural DRC, NOT fab ready.

### ag completion: real preflight improvement, still a routing plateau

ag completed both waves in **511.920 seconds** without an accepted board gain.
Both summaries retain two opens/zero qualified structural DRC and unchanged
input families. Scoped history grew **22 → 28** keys. The exact invocation
`ff1c4ee9fd3e4ad38c9406f3d7704116` was verified completed with `MainPID=0`, then
the retained service was stopped. The one-shot completion callback delivered
successfully; there is no active routing job or successor callback now.

The ranking change worked beyond the advisory preview: wave-01's U11 cell
passed placement and necessary electrical-geometry preflight, restored **24/24
support anchors**, then refused the target. D6's candidate included R10 as an
explicit mobility-graph obstacle expansion (not the old ground-only affinity
grouping), passed those preflights and restored **19/19 anchors** on both its
initial and post-evacuation searches. Neither target closed. Preflight acceptance
is not final layout admission: U11 still required handling generated-copper
conflicts, and no candidate reached independent promotion.

Both target searches initially timed out on their short allocated leases and
used the existing single larger recovery lease after complete support
restoration. Those **20-second** recoveries finished with
`certificate_pair_no_exact_clear_path`, `timed_out=false`, within their bounded
component-pair/alternate-attachment domains. U11 used 0.2-mm trace width and
0.2-mm clearance; USB VBUS used its existing 1.0-mm width, 0.2-mm clearance and
enabled endpoint-neckdown policy. None of these rules was relaxed. These are
**local search refusals, not global impossibility proofs**.

D6 later hit `WorkerPoolStalled` with a **six-second effective allowance** in
the remaining optional repair sequence. The current error text does not name
that exact child operation; do not claim it proves a native crash or identifies
the missing route. Its error remains retryable, not an authoritative physical
rejection. U11's completed measured refusal remains cached. Lower support
trials either failed necessary decoupling geometry or still did not close the
target. Accepted Hub stays exactly `3907452465...`, NOT fab ready.

No automatic successor was launched: repeatedly testing nearby tiny poses has
not closed either target, despite now reaching physical preflight and restoring
the support connections. Further useful work is **route-access/certificate
analysis and bounded transaction scheduling**, not another identical placement
cohort or relaxation of spacing/current/frozen-copper constraints. The next
continuation should inspect those exact route certificates and capture the
child-operation identity for deadline failures before deciding a new frontier.
No private/neutral candidate was adopted, no board was republished, and the
five-minute heartbeat remains paused. Compact inspection helper:
`tmp/summarize_wave_decisions_20260927.py`.

### v91: critical-target scheduling and bounded failure-cause diagnostics

The next human-authorized continuation implemented a generic scheduling repair,
not another board-specific displacement. `_exact_relocated_connections_worker`
previously divided its first target allowance equally with all support anchors:
the recorded U11 and D6 moves received only **1.40 / 1.75 seconds** before those
supports were reconstructed. The new `target_budget_fraction=0.6` reserves a
meaningful first target attempt while leaving support time inside the **same
35-second transaction and 20-second per-pair ceiling**. Every support anchor
still must restore; target closure alone cannot pass admission. Fraction zero
is an explicit equal-share ablation, not a board-specific switch. Invalid
fractions fail closed. Reports expose actual per-attempt budgets and the policy.

Revision is now **2026-09-27-critical-target-budget-v91** because execution of
an exact pose changed. Retain old evidence, but do not guess-migrate v90
feasibility failures into the new revision. `_spawn_apply` now records the exact
worker operation, requested/effective seconds and parent-deadline limitation
when a supervised worker stalls. Relocation reports retain this typed evidence
as `worker_failure`; argument payloads are not logged, and a timeout remains
retryable rather than a physical no-path verdict.

Bridge diagnostics now include bounded via-refusal histograms by endpoint,
search tier, reason and layer. They observe the existing guard verdict without
additional geometry queries, detailed blocker snapshots, changed candidate
order or relaxed rules. Counts distinguish hole spacing/coincident drilling,
pad-land exclusion, protected pour reservations and foreign copper. Existing
full-detail reports remain opt-in. These counts are **trial refusals**, not
distinct objects or DRC totals; zero seats is not a global impossibility proof.

Validation: **1,172 tests plus eight subtests passed in 16.48 seconds**.
Fresh immutable PCIe control: **11.659 seconds**, zero opens/zero qualified
structural DRC, native copper and input family unchanged. Its existing
pair-qualification failure remains visible. Evidence:
`build/critical-target-budget-20260927/regression-final.log` and
`build/critical-target-budget-20260927/pcie-control-final/`.

Native equal-share/critical-first comparison used copies of the same recorded,
physically preflighted poses, original-parent policy and untouched prepared
geometry. U11 reconstructed **24/24** support anchors in **26.961 → 25.500 s**;
D6 reconstructed **19/19** in **28.377 → 26.107 s**. Neither target closed.
Combined routing time decreased about **6.7% in this small diagnostic**, not a
general performance guarantee or a connectivity gain. Total experiment took
130.302 s. See `native-ab-v2/summary.json` beneath the evidence directory;
`tmp/replay_critical_target_budget_20260927.py` reproduces the source-bound test.

Read-only U11 same-layer probes at **0.5 / 0.2 / 0.1 mm grid** found no path
within the same copper/width/clearance rules, completing without timeout in
0.105 / 0.531 / 1.828 s. Short rays show limited immediate escape, unlike the
long 1.25-mm rays alone; therefore neither the diagnostic nor a coarse-grid
refusal proves global unrouteability. Evidence: `grid-probe-owner-00-v3/`.

The new native bridge-cause replay also closes neither target while restoring
all **24/24 and 19/19** supports. U11's ordinary-seat refusal counts include
pad exclusions, hole spacing, front/inner copper and B.Cu protected pour
reservations. D6's include front/inner copper, pad exclusions and hole spacing.
Some bare via positions are legal, but **zero usable stub-plus-via seats** were
found at the required endpoints. Both expanded bridge phases completed without
budget exhaustion. See `bridge-causes/summary.json` and per-cell reports;
`tmp/replay_bridge_failure_causes_20260927.py` reproduces this private replay.
No private board was admitted or published, and accepted Hub remains exactly
`3907452465...`: **two opens / zero qualified structural DRC, NOT fab ready**.
Existing craft, injection, thermal and strict-trace qualifications remain.

One bounded normal integration cohort is justified to exercise v91 scheduling
and diagnostics through the production coordinator, not an indefinite repeat
of the same small poses. Preserve source-copper/frozen-pour/locked-via/current/
clearance/decoupling gates, four-ref/six-mm motion and eight-parent-item bounds.
The next callback must compare actual accepted gain and failure-stage evidence
before any successor. Candidate follow-up is certified endpoint escape and
obstruction/topology analysis, not merely more time or arbitrary global grid
refinement. No changes to dogbone sampling or fabrication dimensions were made
in this slice. Hub, immutable PCIe and ATX pair/board authority hashes were
rechecked unchanged; 58 GiB is free and the 16-GiB floor remains required.

Normal integration cohort launched as
`cec-hub-critical-target-budget-20260927-ah.service`, exact invocation
`7e818d1f49cd4526856265a7d171ea0e`. Evidence is under
`build/event-driven-hub-20260927-ah/`; two waves, 240-second residual leases,
720-second external bound, 8 GiB memory. A one-shot exact-completion listener
is configured; verify `event/state.json` before claiming it is armed. The
five-minute heartbeat remains **PAUSED**. Do not present an unchanged board as
a new candidate, and do not promise continuation across app exit or reboot.

Listener verified **armed** at `2026-09-28T02:05:12.220Z` for the exact ah
invocation; Windows Node PID 30844, empty listener stderr. The matching service
was verified **active/running**, MainPID 1978969. This is a live completion
subscription, not a promise based only on a configured file.

### ah completion and v92: cooperative deadlines and compact launch coverage

ah completed successfully in **505.396 seconds**: two waves, **no accepted
gain**, both two opens/zero qualified structural DRC, input families unchanged.
The exact invocation `7e818d1f49cd4526856265a7d171ea0e` was verified successful,
active/exited with MainPID zero, then stopped. The callback receipt is `sent`.
U11 again passed required placement/craft preflight and restored 24/24 anchors;
D6 restored 19/19 twice, but neither missing target closed. The new diagnostic
identified D6's later failure precisely: `_exact_relocated_connections_worker`
requested a **35-second outer lease**, parent-clamped to **16.261 seconds**,
while its **30-second internal search budget** was not shortened. This was an
actual deadline propagation mismatch, not proof that the board is impossible.

The generic `_spawn_apply(..., search_budget_arg=...)` contract now explicitly
propagates a parent-clamped lease into a cooperative worker's named positional
budget argument. All seven production relocated-reconnect call sites opt in.
The original outer-minus-inner reserve (five seconds at these sites) is kept
for native import/finalization; the hard supervisor still enforces its original
deadline. No argument is guessed by numeric value or callable/board/refdes
name. Invalid contracts reject before dispatch. If no funded search remains,
a typed, diagnosed budget failure returns without spawning. Reports retain
both requested/effective search and worker budgets. A hard native stall can
still be killed; graceful completion is not guaranteed by a cooperative lease.

Pose history now treats parent-clipped reconnect results as retryable even
when the worker returned gracefully. It walks only bounded execution-report
envelopes, not large native diagnostic payloads. This prevents a partially
funded recipe from poisoning exact/physical pose rejection memory. Full-lease
measurements retain their previous caching behavior; no release gate changes.

Native ablation on the same prepared D6 copy and **16.261-second parent limit**:
old supervisor-only path was killed in **16.283 s**; cooperative path returned
in **13.195 s**, with an **11.261-second search allowance**, target unclosed,
13/19 supports restored and six explicitly budget-exhausted. This is a useful
incomplete report, **not an acceptable candidate**. See
`build/critical-target-budget-20260927/cooperative-native/summary.json` and
`tmp/replay_native_cooperative_budget_20260927.py`.

A read-only sub-0.5-mm probe found a real omitted search domain: **four usable
ordinary-via launches** at the USB-VBUS inner-layer endpoint, versus zero in
the old domain. The opposite endpoint still refuses. `_dogbone_offset_ladder_mm`
now appends 19 positions from **0.025 to 0.475 mm** after the old domain, retaining
existing successful seat preferences. This is a bounded local search step,
not a fabrication resolution claim or altered drill/land/current/clearance rule.
The exact native guards still qualify every origin, stub and barrel. No global
grid refinement or power-pour change was made.

Ten new compact-seat regressions include rotated/back-side native geometry,
legacy-domain negative controls, retained foreign clearance, unchanged earlier
successful seats and an emitted fixture passing native KiCad DRC with zero
errors/opens. The full Hub replay now reports four launch seats at that endpoint
and still restores **24/24 and 19/19** supports, but neither target closes.
U11/D6 reconnect times were **28.204 / 28.510 s**; added search has a bounded cost,
not a measured speedup. Evidence: `short-seats/` and `compact-seats-native/`
beneath the same evidence directory. All these diagnostic boards are private.

Revision is **2026-09-27-cooperative-budget-and-compact-seats-v92**, because both
search scheduling and candidate coverage changed. No guessed migration of old
pose-feasibility keys. Final suite: **1,264 tests plus eight subtests passed in
17.41 s**, `regression-v92-complete.log`. Fresh immutable PCIe control:
**11.670 s**, zero opens/zero qualified structural DRC, native copper/source
family unchanged, existing pair qualification still failing. Its evidence is
`pcie-control-v92/`. Hub, PCIe, ATX board and active pair hashes were rechecked
unchanged; 58 GiB free. Accepted Hub remains `3907452465...`, **two opens, NOT
fab ready**. No unchanged dashboard publication or duplicate tab was created.

One bounded production integration cohort is warranted by the measured new
launch domain and tested budget correction. Do not repeat cohorts indefinitely
for cosmetic/timing-only changes. If it plateaus, trace the remaining certified
pad escape obstruction back to the placement/escape/ownership stage which
created it; do not simply keep increasing duration, offset density or board
dimensions. Preserve all original-parent copper, craft, protected-fill, current,
clearance, native connectivity and independent admission gates.

Integration cohort launched as
`cec-hub-compact-launch-budget-20260927-ai.service`, invocation
`a1c4cec1e1db4e08b3227b9a4dd470d4`. Evidence:
`build/event-driven-hub-20260927-ai/`. It uses ah wave-01's unchanged accepted
baseline, two 240-second residual leases, 720-second external timeout and 8 GiB
RAM. Its exact-completion callback is configured; verify actual listener state
before claiming it is armed. The periodic heartbeat stays paused.

Listener verified **armed** at `2026-09-28T02:30:37.903Z` for the exact ai
invocation; Windows Node PID 30156, empty stderr. Matching service verified
**active/running**, MainPID 1992781. Periodic automation rechecked **PAUSED**.

### ai completion: future non-pair pin access before priority routing

ai completed two waves in **508.185 seconds**, again **no accepted gain**:
two opens, zero qualified structural DRC and unchanged input families. Exact
invocation `a1c4cec1e1db4e08b3227b9a4dd470d4` was verified successful with
MainPID zero and stopped. Its one-shot callback was confirmed `sent` at
`2026-09-28T02:38:43.070Z`. The compact launch domain did not close either
target. U11 and D6 trials restored 24/24 and 19/19 supports; a later reconnect
with only 2.659 seconds left correctly refused to spawn because its five-second
finalization reserve was unfunded. Do not repeat this residual cohort unchanged.

Upstream native forensics distinguishes two obstructions:

- **U11_OV1 / U11.5:** C10's GND land blocks the sampled 1.25-mm escape. The
  current preflight actually reports this pin blocked, but the older aggregate
  gate omits packages with more than ten pads and the explicit critical gate
  tests only three named controls. U11 has twelve pads. C10's existing pin-7
  assignment and measured supply/ground craft distances remain authoritative;
  moving it away is not permission to waive decoupling qualification. The
  observed board is evidence of an escape obstruction, not complete historical
  attribution to a particular original placement transaction.
- **USB_VBUS / D6.5:** its surface launch can fit at the already-authorized
  local neckdown width, but locked USB pair tracks on In2.Cu run underneath
  the pad and consume its through-via column. A finite 25-um contained-pad
  sample found 962 failed barrel probes, not a proof that no route exists.
  Removing only that pair in memory restores one guarded port; restoring the
  actual copper loses exactly that port. No accepted copper was removed.

New generic production module **`cec_future_pin_access.py`** reserves a
native-guarded prospective POFV column for a scarce, still-isolated non-pair
SMD pin on a package carrying the active pair. It uses declared fabrication
geometry, actual pad containment, project width/clearance, eight bounded escape
rays, all-layer copper, rule areas, holes and edge guards. Through-hole pins,
one-terminal nets, other declared pair nets and pins already attached through
same-net native geometry to another pad or real barrel do not acquire redundant
via obligations. The emitted reservation applies across the copper stack.
There are no Hub/refdes/pin-count/coordinate allowlists. This is a bounded
preventive access contract, not ampacity, full routability or release authority.
Ordinary vias or off-center launch alternatives are not yet planned by it.

`cec_precision_route.py` now passes those reservations to pair planning and
independently rechecks them before and after final package/support generation.
Lost access refuses the whole newly generated transaction; rollback preserves
inherited copper. Pair-order negotiation does not waive non-pair access.
Package preclosure currently lacks a proactive avoid argument; if it consumes
a reserved column, the independent gate refuses it rather than accepting it.
Incomplete planning is a named retryable budget refusal, never a no-path claim.
The shared `cec_fr._pad_local_escape` helper replaces duplicate formulas in the
last-mile and certificate paths without changing the existing width authority.
Residual revision remains v92: this feature does not justify resetting old
pose history and rerunning the same downstream micro-moves.

A native regression exposed a KiCad hazard: calling either connectivity build
method can propagate a touching pad's net onto a foreign track. This new access
guard therefore does **not** rebuild connectivity. It walks same-net exact
shape contacts read-only, and tests assert the copper inventory remains exact.
A dead stub or foreign-net bridge is not accepted as an existing escape.

Validation under `build/endpoint-access-forensics-20260927/`:

- `regression.log`: **823 tests plus ten subtests passed in 16.78 s**. Native
  cases cover rotated/back-side and 6-/16-pad packages, inner-layer obstruction,
  same-net path reuse, false foreign bridges, declared process limits, budget
  failure, independent pair refusal and rollback through the production entry.
- `future-pin-hub-v2/summary.json`: latest native replay, exactly one recovered
  then lost port (D6.5); both source bytes and native inventories unchanged.
  The earlier `future-pin-hub/` report is superseded by the same-net path walk.
- `future-pin-pcie/summary.json`: all three derived pairs need no new port
  reservations; existing access is reused, no redundant barrels requested.
- `pcie-control/native-control.json`: fresh **10.701-second** immutable PCIe
  replay, zero opens/zero qualified structural DRC, source family and native
  copper unchanged. Its pre-existing `pairs_ok:false` remains visible; this is
  not renewed full fab signoff.
- `upstream/report.json`, `neckdown/summary.json`, `contained-pad/summary.json`:
  native obstruction/launch ablations. No unproven POFV neckdown relaxation was
  implemented merely because a narrower surface stub exists.

Next useful frontier is a bounded upstream pair replay, not another residual
cohort. `tmp/replay_future_pin_pair_route_20260927.py` selects the implicated pair
from the counterfactual access loss, removes only that pair's copper on a
private copy and exercises the production precision entry with fixed existing
power reservations. It compares every retained parent track/via and all native
placements, as well as source-family and engine hashes. This deliberately
counterfactual deletion is **not** inherited locked-copper replacement authority
and cannot be admitted or published as a winner. The plan-only native smoke
passed in 1.116 seconds (`pair-replay-plan/summary.json`). A successful private
route still needs an independently justified upstream reconstruction/ownership
transaction and all normal admission, including full-board pair/DRC/craft gates.

Accepted Hub is still SHA256 `390745246590805a36995cdbc141b4627c5557edb3170b44c6a22de525c89ad1`,
**two opens, zero qualified structural DRC, NOT fab ready**. Raw fabrication,
craft, thermal, injection, pair and strict-trace findings remain visible. No
new accepted board or dashboard image was published. Keep the periodic monitor
paused; use only an exact completion subscription for a justified successor.
Latest storage check: 58 GiB free; retain the 16-GiB floor.

Bounded upstream replay **aj** launched as
`cec-hub-future-pin-pair-replay-20260927-aj.service`, exact invocation
`1aa83c8451b04fffb1416f3f353d5d60`, evidence beneath
`build/event-driven-hub-20260927-aj/`. Pair search is capped at 240 seconds,
the service at 540 seconds and 8 GiB. It consumes ai wave-01's accepted baseline
and retains 540 fixed power reservation obstacles. No board dimensions,
placements, rules, accepted files or non-pair inherited copper are authorized
to change. Its private pair ablation is explicitly not release authority.

Exact completion listener verified **armed** at `2026-09-28T03:18:22.272Z`,
Windows Node PID 30776, empty stderr. The matching service was verified
**active/running**, MainPID 2008680, exact invocation above. The five-minute
automation was independently reread **PAUSED**. Hub/PCIe/ATX/active-stack
authority hashes were rechecked unchanged. This is a one-shot live completion
subscription, not periodic model polling or a promise of reboot recovery.

### aj completion: measured one-open result and generic owned-pair handoff

aj completed successfully in **147.936 seconds**. Exact invocation
`1aa83c8451b04fffb1416f3f353d5d60` was verified active/exited, MainPID zero,
ExecMainStatus zero and stopped. The production precision solver rebuilt the
USB pair with **44 new items**, replacing 66 pair items in the private ablation.
All **1,067 non-pair parent items**, placements and input family remained exact.
The recovered D6.5 column survived. Pair-local checks passed; no refusal was
reported. This was useful upstream progress, not another downstream plateau.

Fresh full route grading of the private pair-only result found **two opens,
zero qualified structural DRC and pairs_ok true**. The ordinary production
`_lastmile_worker` then used the recovered access, added just **three items**,
and closed USB_VBUS. Its private result is **one open / zero qualified
structural DRC**, pairs_ok true, parent copper/placements/source unchanged,
measured in **16.005 seconds** including fresh grading. Remaining open is
U11_OV1. Evidence under `build/endpoint-access-forensics-20260927/`:
`pair-replay-grade/`, `pair-replay-finish/`, and `pair-replacement-boundary/`.

The complete boundary replay took **23.841 seconds**. Power fill has zero loss;
component/pad population, project policy and design rules are unchanged; full
physical placement passes. The ordinary additive continuation guard correctly
remains **false** because the 66 old USB pair items are no longer present.
It was not relaxed or relabeled as passing.

The next generic production slice adds:

- `cec_priority_dependency.pair_scope_plan`: extracted the existing closed,
  independently qualified signal-pair ownership logic. Placement witnesses keep
  their old typed checks; a scope alone is never release permission.
- `cec_future_pin_access.replacement_witness`: reproduce a pair-owned column
  obstruction on the actual immutable source. The only counterfactual removal
  is one closed qualified pair, bounded at 256 original items. A valid native
  column must appear after removal, disappear against original copper, and name
  actual blocking UUIDs in that pair. Other targets, unqualified pairs, missing
  native evidence and oversized/incomplete searches are refused. No board/refdes
  or coordinate recipes. This bound is for a complete atomic pair, not an
  increase to the separate eight-item ordinary local repair budget.
- `cec_route_pair_admission`: a separate full proof path. It requires strict
  native open reduction, zero qualified structural DRC, every other original
  item exact, unchanged placements/outline/component definitions/project/rules,
  no protected power fill loss, exact frozen power authority, full physical
  placement, all original pair physics, and complete native connectivity of the
  recovered non-pair net. It reproduces the obstruction independently and issues
  the existing proof-bound priority-replacement receipt. Native net relabeling
  and unrelated new copper reject. No weakening of `checkpoint.preservation`.
- `cec_pair_access_repair`: one bounded upstream construction trial before
  repeating residual micro-moves. It searches at most eight qualified pairs for
  a typed witness, reconstructs at most one complete pair with fixed power
  reservations, runs ordinary completion on recovered nets, and calls the new
  independent handoff. A 390-second default worker lease and hard supervisor
  cover discovery, a <=240-second pair solve, <=60-second completion and proof.
  The coordinator separately budgets grading/revalidation and finish reserves.
- `_resume_route_residuals` consumes this stage only for a fresh fully graded,
  pair-qualified routed incumbent with opens. A proved gain ends that lease;
  it does not immediately repeat the downstream plateau. `_route_stage` freshly
  revalidates the pair transition against its own original parent before
  selection, retains it as progress-only, and still runs normal guarded polish.

Native `pair-access-qualification/revalidation.json` **passed** on the exact
private one-open result, including a sealed source-bound replacement receipt.
That proves the new handoff itself; canonical automatic dispatch, independent
outer revalidation, selection and polish are the next integration run. Do not
publish the diagnostic source as a production winner merely because this proof
passed. The accepted/dashboard Hub remains `3907452465...`, two opens, until
that full coordinator result is independently checked and published.

Validation: **168 focused tests plus sixteen subtests**, then **1,007 broader
tests plus twenty-six subtests in 18.42 s** (`pair-access-regression.log`).
Fixtures cover rotation/back-side, renamed 16-pad packages, source immutability,
typed obstruction reproduction, complete pair closure, power/unqualified/
unrelated/reassigned-net rejection, explicit inventory bounds, required proof
fields, fresh grade regression and coordinator priority. Existing receipt,
placement, checkpoint, pair, bridge and certificate tests remain passing.
Fresh PCIe control: **10.776 s**, zero opens/zero qualified structural DRC,
copper/source unchanged, pre-existing pair qualification still visible. See
`pcie-pair-access-control/native-control.json`. Residual revision remains v92;
no pose-memory reset or geometry-rule relaxation was introduced. 58 GiB free.

Canonical integration run **ak** launched as
`cec-hub-owned-pair-access-20260927-ak.service`, invocation
`7b86037a80374cfda09d3851d32e2672`. It runs the existing
`tmp/replay_route_stage_20260926.py` on the unchanged accepted two-open baseline,
not on the diagnostic one-open candidate. This exercises normal discovery,
construction, independent inner/outer handoffs, fresh grading, selection and
guarded progress polish. Evidence: `build/event-driven-hub-20260927-ak/route/`.
External bound 720 seconds, 8 GiB, no restart. Verify final `oracle.json`,
`native-control.json`, `candidate-summary.json` and outer pair-access proof
before publishing any changed dashboard candidate.

Exact callback verified **armed** at `2026-09-28T03:40:13.057Z`, Windows Node
PID 18100, empty stderr. Matching service **active/running**, MainPID 2014622,
exact invocation above. The periodic automation was reread **PAUSED**.
Hub/PCIe/ATX board and active-stack authority hashes remain unchanged.

### ak completion: automatic one-open winner selected and published

The normal `_route_stage` integration completed in **226.489 seconds** and
selected origin `route_pair_access_repair`: **one open, zero qualified
structural DRC**, `pairs_ok: true`, no regression in previously passing gates.
Current accepted progress board is
`build/event-driven-hub-20260927-ak/route/winner.kicad_pcb`, SHA256
`93473ae90afbd84cf5f71a8118750a2e2325efe3c3f6b0fd5955ce36d28c99b1`.
USB_VBUS is connected. `/POWER INPUT + SOURCE SELECTION/U11_OV1` remains open.
This supersedes the two-open `3907452465...` routing progress baseline, not
the source schematic or immutable manufacturing controls.

Independent inner and outer owned-pair admissions both passed. The outer proof
is `route/candidate-000023-pair-access/revalidation.json`, source-bound receipt
`67d55a57a484f0a29a49b09081a98d6370a9e4e285adb7913b1a242116719f81`.
All twenty protected power-fill layer entries have **zero copper loss** at
zero tolerance. Full physical placement passes, source/project/rule authority
is unchanged, and selected winner bytes equal the outer-admitted candidate.
Polish correctly reported `no_safe_craft_gain`; no cosmetic gain is claimed.

The exact ak invocation was verified exited/success/MainPID zero and stopped.
Its one-shot callback delivered successfully. No successor is running at this
point, and the periodic monitor remains paused. PCIe immutable control, ATX
placement, and active stack hashes were freshly rechecked unchanged.

Published archive ID:
`20260927-hub-standard-rev2-checkpoint-continuation-93473ae90a`.
Dashboard:
`http://localhost:8090/?id=20260927-hub-standard-rev2-checkpoint-continuation-93473ae90a`.
The existing browser tab was navigated to this exact ID and its loaded panel
inventory verified: top/bottom models-off renders and all six copper plots.
Top and bottom renders are also copied to the Windows-visible folder
`C:\Users\Admin\Documents\CEC-Board-Reviews\hub-one-open-93473ae90a\`.

**NOT fab ready**: the open, C37 courtyard-to-edge clearance (0.475 mm versus
0.8 mm), current injection qualification, and pending thermal qualification
remain. Raw manufacturing/craft/strict-trace findings are not hidden by the
qualified structural DRC count. The prior strict-trace numerical result is
not a fresh audit of this new winner. Next work is the generic upstream
pin-access/placement boundary for the remaining native endpoint, not blind
repetition of exhausted residual poses or rule/decoupling relaxation.

### Articulated owner escape: bounded proposal search, not a rule waiver

The remaining native endpoint is U11.5. Its straight escape is obstructed by
C10's ground land; moving the IC and all nearby support capacitors rigidly
preserves that obstruction. The legacy aggregate escape check skips packages
above ten pads, but a private-pin guard and a newer native preflight already
exist. This investigation does not prove which historical placement operation
introduced the obstruction. C10's qualified supply assignment is U11.7, not
U11.6; the accepted decoupling and ground-return limits must remain intact.

New production module `cec_owner_escape_articulation.py` derives tangent gap
centres from native lands, trace width and clearances. Within an explicitly
authorized small-IC endpoint-owner transaction it proposes moving the owner
and non-obstructing supports while keeping the obstructing support stationary,
or an owner-only alternative. Scope remains at most four refs, six millimetres,
one small IC, and the existing incident-copper budget. Default two-pad support
scope does not widen. Proposals carry no admission authority; every fixed-via,
craft, physical-DRC, reconnection and original-parent preservation gate remains.
No board, reference or coordinate recipe is part of this production generator.

`cec_certificate_repair` incorporates those proposals, native-copper scores
their actual moving subset, and distinguishes an explicit empty companion set
from an inherited rigid set in candidate identity. Revision is now
`2026-09-27-articulated-owner-pin-lanes-v93`; this represents a genuinely changed
proposal algorithm, not a reset intended to repeat the same exhausted search.
`cec_compound_support_candidate` now passes its already validated small-owner
pad scope to the native mover and explicitly refuses two independent IC owners.
Independent support projection remains diagnostic, not automatic integration.

Native trials on the exact accepted one-open board remain **rejected**:
owner-only movement clears the lane but worsens two other decoupler links;
moving those supports with the owner conflicts with a fixed return via.
Independent fixed-via projection produced three craft-geometry-passing private
layouts, but all three failed full native physical DRC against existing copper.
No rejected layout was routed, adopted or published. Evidence is under
`build/owner-articulation-20260927/{preview-v2,preview-v3,projected,qualified}/`.
The first `preview/` had an empty report wrapper and is superseded, not evidence
of a successful test. Source board families remained unchanged throughout.

Validation: **413 focused tests passed**, then **576 broader tests plus sixteen
subtests passed in 4.29 seconds** (`broad-regression.log`). Native fixtures cover
renamed/transformed front/back packages, bounded ownership, immutable/grouped/
through-hole refusal, reversible pose probes, subset propagation and candidate
identity. Existing pair receipts, checkpoint admission and event listeners pass.

The fresh normal PCIe 2-port control completed in **70.856 seconds**, with zero
opens, zero qualified structural DRC and no regression in previously passing
gates. The existing guarded polish selected a private `incumbent_polish`
candidate; do not claim its selected copper was byte-identical. Immutable
archived inputs remain byte-identical. Pre-existing `pairs_ok` and pending
`thermal_ok` are still failures; this is not a fresh fab-release certification.
Evidence: `build/owner-articulation-20260927/pcie-control/native-control.json`.
Accepted Hub, immutable PCIe, ATX placement and active stack authority hashes
were all rechecked unchanged. Free disk remains 58 GiB; minimum floor 16 GiB.

The next bounded normal coordinator replay tests v93 dispatch on the accepted
one-open Hub. A plateau is not permission to relaunch identical cohorts or to
relax fixed-via, decoupling, protected power or trace-spacing requirements.

Replay **al** launched as `cec-hub-articulated-owner-20260927-al.service`,
exact invocation `9815d67c769d493ca692ffffec1f3967`, MainPID 2035173.
Source is the exact accepted ak winner; evidence directory is
`build/event-driven-hub-20260927-al/route/`. External cap is 720 seconds and
8 GiB, no restart. The one-shot Windows bridge PID 14600 was verified **armed**
at `2026-09-28T04:12:28.317Z`, with empty stderr and matching service
active/running. Callback config/state are `event-bridge.json` and
`event/state.json` in that run directory. The periodic automation was freshly
read as **PAUSED**. No al outcome or improvement is asserted until completion
and independent review of its actual selected board and preservation evidence.

### al completion: safe polish gain and a witnessed owner-stage starvation

al completed successfully in **455.289 seconds** (455.293 including final
printing). The exact invocation was verified terminal, MainPID zero, then
stopped; its one-shot callback delivered. Connectivity did **not** improve:
one U11_OV1 open, zero qualified structural DRC, `pairs_ok: true`. Existing
guarded fabrication polish selected `incumbent_polish`, reducing reported
route length **2484.75 -> 2466.74 mm** (18.01 mm, approximately 0.72%); vias
remain 192. This is a small routing cleanup, not electrical closure.

The newly accepted progress source is
`build/event-driven-hub-20260927-al/route/finish-comparison/incumbent/board.kicad_pcb`,
SHA256 `a7635e0730894727f2f9bfcafe208dbf057bcc767276c7825c7190b414bcd71d`.
The sibling route `winner.kicad_pcb` has identical bytes, but continuation should
prefer the selected source named in `oracle.json` to retain its scoped history.
Independent native verification (`polish-boundary.json`, 24.72 seconds) proves
all twenty protected-fill layer entries lose zero copper at zero tolerance,
unchanged placements/population/project/rules/frozen authority, full physical
placement, retained parent copper and qualified pair physics. Input families
were unchanged. Current injection, thermal, courtyard-edge and remaining raw
manufacturing/craft checks remain blocking; this board is **NOT fab ready**.

Published archive and verified existing dashboard tab:
`20260927-hub-standard-rev2-checkpoint-continuation-a7635e0730`.
Top/bottom models-off renders and all six copper layers are present. Windows
copies: `C:\Users\Admin\Documents\CEC-Board-Reviews\hub-polished-a7635e0730\`.

The repair worker itself exhausted its **180.01-second** budget without ever
dispatching an endpoint-owner candidate. Same-net route windows deferred both
supports, so the early-owner stage was skipped. After additive/deep/atomic
route retries, two R37 peer moves took **45.342 and 32.453 seconds**. The next
fixed-via filtering child received only **0.125 seconds**, hit the parent
deadline, and stopped the repair. This was scheduling starvation, not evidence
that the newly added articulated owner proposals had been tried and failed by
the normal coordinator. Separate diagnostic rejections remain valid.

Generic scheduling correction: `_endpoint_owner_lane_plan_worker` now requires
the ordinary live small-owner certificate **and** fresh native articulated
pad-lane proposals before allowing owner work ahead of same-net route retries.
`_early_owner_targets` matches both owner and refused net. Without that witness,
the previous conservative fixed-point ordering remains. The early transaction
uses those exact bounded proposals through normal fixed-via, craft, physical,
reconnect and independent admission, with an eight-parent-branch cap. It cannot
authorize a moved component or weakened rule. Logical-slice and scoped pose
memory mechanisms remain; algorithm revision stays **v93** (no memory reset).

Tests: **323 focused** passed, then **684 tests plus sixteen subtests** passed
in **122.23 seconds**, including full coordinator regressions. Native renamed,
translated, rotated/front/back fixtures prove a missing certificate, absent
physical obstruction or immutable owner cannot preempt route ordering. Evidence:
`build/owner-articulation-20260927/scheduling-broad-regression.log`.

Fresh PCIe scheduling control completed in **71.884 seconds**: zero opens,
zero qualified structural DRC, no regression in previously passing gates and
immutable source family unchanged. Private polish was selected; existing
`pairs_ok` and pending `thermal_ok` remain failed. Evidence:
`build/owner-articulation-20260927/pcie-scheduling-control/native-control.json`.
Immutable PCIe, ATX placement and active stack hashes were rechecked unchanged.

Normal integration wave **am** is running from the exact selected al board
and its scoped history: `cec-hub-native-lane-priority-20260927-am.service`,
invocation `9fd3d23462224525bcb144709bdaf65e`, MainPID 2055207. Output:
`build/event-driven-hub-20260927-am/route/`. Bounds remain 720 seconds and 8 GiB,
no restart. Windows one-shot listener PID 30236 was verified **armed** at
`2026-09-28T04:32:17.475Z`, empty stderr, exact matching active/running service.
Periodic monitor freshly verified **PAUSED**. No result from am is claimed yet.
Inspect the actual owner-stage dispatch, remaining candidate menu and timing
on completion; do not infer a successful scheduling fix from unit tests alone.

## am completion; persisted-frontier handoff and electrical pose ordering

The exact am invocation completed successfully and was stopped only after its
terminal identity and MainPID zero were verified. Whole-run time was **413.248
seconds**. The incumbent was retained byte-for-byte at **a7635e0730**: one open
`/POWER INPUT + SOURCE SELECTION/U11_OV1`, zero qualified structural DRC,
`pairs_ok=true`, 2466.74 mm routing length and 192 vias. No duplicate board image
was published. This remains a routing checkpoint, **not a fab candidate**.

The native pad-lane scheduling change actually ran: U11's early owner proposal
was tried before global route replay and rejected by native electrical craft
in **17.546 seconds**. The residual worker completed a finite placement slice
in **157.566 seconds**. However, the outer coordinator interpreted unchanged
copper as `no_progress` and still dispatched global routing. The rest of the
413-second run did not improve the board. This is a second scheduling boundary
defect, not a claim that the geometry is now routable.

Generic corrections:

- `_placement_slice_frontier` in `cec_full_pipeline` requires a source-bound,
  current-revision scope, a measured refusal actually persisted in history,
  at least one newly remembered pose, and an unvisited finite menu. It honors
  the worker's `placement_slice_complete` without starting global routing.
  Repeated receipts, timeouts, stale identities, exhausted menus, missing
  evidence and contradictory accepted/unchanged reports retain the fallback.
  This grants scheduling authority only; it cannot accept any geometry.
- `cec_support_pose_rank` reads native bypass coordinates and the existing
  electrical limits once per target. It stably demotes pure translations that
  predict new/worsened return or proximity faults. Explicit stationary versus
  carried companions and changes in the nearest actual ground pin are handled.
  Rotations, shared/ambiguous supply assignment and missing geometry stay
  unknown. **Every candidate survives**; no prediction creates a rejection
  cache entry or replaces native craft/physical/route admission.
- Ranking runs after motion/fixed-via and scoped-history filtering, before the
  bounded native transaction budget. No board names, refdes, coordinates,
  clearances, BOM currents or rule exceptions are embedded in either feature.
  Revision **v93** is unchanged: prior measured refusals are not reset.

Read-only native evidence:
`build/owner-articulation-20260927/craft-ranking-native.json`.
The actual C10 menu contains 140 unvisited eligible poses: 64 predicted
nonregressing, 46 regressing and 30 unknown. The previous first was a positive
x/y translation; the new first is the existing fixed-via-derived
(-0.097227,+0.097227) mm translation. This is derived ordering evidence, **not
placement or route approval**. All candidate identities survived permutation
and every input authority file stayed unchanged. The real am report also
passes the new frontier receipt with five newly saved contextual/physical keys.

Validation: **772 tests plus sixteen subtests** passed in **129.43 seconds**;
an additional coordinator no-geometry-change case passed with the focused
30-test residual suite. Logs:
`build/owner-articulation-20260927/craft-frontier-regression.log`.
Native PCIe control completed in **76.228 seconds**, zero opens, zero qualified
structural DRC, no source changes. The preexisting pair gate and pending
thermal qualification remain failed; this is not a new fab qualification.
Evidence: `build/owner-articulation-20260927/pcie-craft-frontier-control/`.
Immutable PCIe, ATX placement and active stack hashes match the previous audit.

Bounded normal-coordinator wave **an** launched from the exact am winner and
its persisted search history. Service `cec-hub-craft-frontier-20260927-an.service`,
invocation `6ada4cd1228346f5bfba3d51e877c135`; 720 seconds, 8 GiB, no restart.
Output: `build/event-driven-hub-20260927-an/route/`. No an result is claimed here.
On completion verify actual chosen pose, native craft result, outer
`placement_frontier_progress` versus full-route fallback and whole-run timing.
The five-minute monitor remains PAUSED. Retain the known accepted dashboard
until a genuinely changed selected board passes independent preservation.

The an one-shot listener (Windows PID 7632) was verified **armed** at
`2026-09-28T04:55:45.298Z`, empty stderr, with exact matching active/running
service MainPID 2071940. The current accepted dashboard URL returned HTTP 200.
This is the existing local completion bridge, not a built-in desktop WSL event
trigger; keep the computer and app running. No restart recovery is implied.

## an completion; endpoint-independent native geometry history

Wave **an** completed in **175.194 seconds**, versus am's 413.248 seconds.
The actual coordinator honored `placement_frontier_progress`, retained the
incumbent and did not dispatch global routing. This is an observed run-time
reduction, not a controlled benchmark: the sampled placement work also differed.
The board stayed byte-identical at **a7635e0730**, one open, zero qualified
structural DRC, `pairs_ok=true`, 2466.74 mm and 192 vias. No new render/fab
candidate was published. Exact terminal invocation and MainPID zero were
verified before stopping the retained an service.

The new ranking was exercised by the real coordinator. Both the C10-only and
C10+R37 (-0.097227,+0.097227) mm proposals passed native electrical geometry
and physical preflight, then failed target reconnection (47.887 and 30.626 s).
The preflight's track-dangling counts were temporary removed-branch artifacts;
no altered trial was accepted. The residual worker ended after 130.013 s.
Remaining native refusal diagnostics still include the selector's neighboring
lands, C10 supply/GND and nearby divider lands; passing placement is not proof
of an open pin-escape aperture.

Another repeated-work cause was proved. The U11 owner-alone +0.75 mm x pose
was tried again and failed native craft in 17.133 s. Its source, authority,
policy scope, companion set and movement bounds were identical, but the
diagnostic route endpoint changed from R37.2 to a track endpoint. The existing
route-context key therefore differed. This was **not** lost scope/history:
the real sidecar grew from five to eight keys correctly.

Generic fix: `cec_route_pose_history` now has a separate
`craft-geometry-pose-v1` key for a measured native **geometry preflight**
rejection. It binds actual moved owner/companions, displacement, net and full
movement/search bounds within the existing exact board/rule/policy scope, but
does not bind the incidental route endpoint. It requires successful native
copper-ownership evidence and matching actual cell membership, plus recognized
return/proximity faults with no routed-gate loss. Routed craft admission,
prediction-only results, incomplete evidence and worker errors cannot create
this stronger key. Worker errors can reopen it. Geometry or authority changes
invalidate it normally. The existing physical and route keys keep their prior
semantics; **v93** is unchanged and old compatible keys survive.

Native proof replay compiled exactly **one** newly expressible geometry key
from the completed an report into a **private byte-identical** continuation
copy (eight to nine keys), using the production history writer. Original an
family unchanged. Evidence and report hash:
`build/owner-articulation-20260927/geometry-history-native/replay.json`.
A real `_attempt_footprint_relocation` filter with a changed diagnostic
endpoint skipped that exact pose: generated 1, geometry-history-skipped 1,
scheduled 0, no geometry changes. Evidence: sibling `native-filter-proof.json`.
This is proof-backed history compilation, not a manually invented refusal or
new layout. The ordinary writer now emits the same key for future native
geometry rejections automatically.

Validation: **785 tests plus sixteen subtests** passed in **120.64 seconds**.
Log: `build/owner-articulation-20260927/geometry-cache-regression.log`.
Fresh PCIe native regression replay **72.723 seconds**, zero opens and zero
qualified structural DRC; source unchanged, only the preexisting `pairs_ok`
and pending `thermal_ok` remain failed. Evidence:
`build/owner-articulation-20260927/pcie-geometry-cache-control/`.
PCIe, ATX placement and active stack immutable hashes remain unchanged.

Normal coordinator wave **ao** launched from
`build/owner-articulation-20260927/geometry-history-native/board.kicad_pcb`.
Service `cec-hub-geometry-memory-20260928-ao.service`, invocation
`402c60d7bf8f4b579a7706d241c82320`; output
`build/event-driven-hub-20260928-ao/route/`, 720 s/8 GiB, no restart.
No ao result is claimed yet. Inspect geometry-history skip counts and actual
trial poses. If further small cap translations fail the same native pin
aperture, prioritize a generic pin-aperture/fixed-via/craft-aware proposal
improvement over blindly walking the remaining menu. Do not infer an exact
no-path proof from the bounded planner or weaken spacing/decoupling rules.

The ao listener (Windows PID 17840) was verified **armed** at
`2026-09-28T05:06:50.491Z`; stderr empty, exact matching active/running service
MainPID 2081375. Periodic monitor freshly verified PAUSED. Accepted dashboard
returned HTTP 200. No board update or ao success is implied by these checks.

## ao/ap completion; native support aperture and scheduling repair (2026-09-28)

ao completed in **181.457 s** (residual work **134.230 s**), with the accepted
board unchanged at **a7635e0730**: one open, zero qualified structural DRC,
`pairs_ok=true`, 2466.74 mm and 192 vias. The new geometry-history key skipped
the already measured +0.75 mm owner pose. Two smaller support moves passed
native geometry and physical preflight but again failed target reconnection.
Exact completed invocation/MainPID zero were verified before stopping ao.

The remaining aperture is coupled: moving a support land enough to clear a
trace does not necessarily clear a via, while the supply-pin proximity limit
and a fixed ground via constrain the remaining degrees of freedom. Diagnostic
native probes found a legal *local* proposal, not a completed or admitted board.
`pin-aperture-derived-probe-v4.json` supersedes earlier diagnostic probes; v2
did not restore the support before testing its second geometry and must not be
used as evidence. Production replay evidence is
`build/owner-articulation-20260927/native-pin-aperture-menu-v2.json`: three
proposals in 2.727 s, smallest displacement first, source families unchanged.

Generic additions:

- `cec_pad_face_launch`: finite cardinal launches on actual convex SMD lands,
  including transverse points inside the same native pad. No invented via
  geometry or clearance exception; unsupported custom shapes yield no proposal.
- `cec_support_pin_aperture`: derive support displacement from the native
  obstructing land and approved via envelope; intersect it with the existing
  decoupling proximity domain. Require unchanged motion/fixed-return-via,
  electrical-geometry prediction, native trace, all-layer barrel and hole guards.
  Generate bounded proposals only; restore all in-memory changes before return.
- The local dogbone bridge tries pad-face launches only after the established
  center-based tier finds no seats. Existing successful plans retain precedence.
  The independent local-POFV validator already accepts a direct bounded trace
  starting anywhere on the actual owning land; its rules were not loosened.
- The repair recipe is now **v94** because the actual routing search gained a
  new launch topology. Old route-failure scope is intentionally invalidated by
  that capability change, not reset merely to retry a failed pose.

The current profile's preferred 0.35/0.25 mm and existing qualified local
0.30/0.20 mm geometries remain unchanged. The production proposal with the least
motion shifts the blocking capacitor by (-0.200062,+0.159998) mm and offers a
same-pad offset launch; those coordinates are measured output, not constants
in production code. No final routing, thermal, or fabrication claim follows.

Tests before scheduling repair: **930 passed plus 24 subtests**, 134.28 s, log
`build/owner-articulation-20260927/pin-aperture-full-regression.log`.
Native fixtures exercise four rotations and both board sides, renamed parts
and translated coordinates, immutable/fixed-via/proximity constraints, foreign
inner copper, edge and length guards, and independent emitted-via validation.
Fresh PCIe control took **82.167 s**, zero opens/qualified structural DRC,
source unchanged; preexisting `pairs_ok` and pending `thermal_ok` still fail.
This is regression evidence, not a new PCIe fabrication certification.

Normal Hub wave **ap**, invocation `2782f781296b4e0bac233a163cdae6f8`, completed
in **104.442 s**, unchanged. It exposed a coordinator omission: the certified
support was deferred behind same-net route windows, while the owner-land
witness preempted them and spent the slice on an owner move. Thus ap did not
actually test the new support aperture. Its zero aperture count belongs to
the owner stage, not proof that support proposals are absent. ap was reviewed
in the active turn; no redundant completion callback was armed. Exact terminal
identity and MainPID zero were checked before stopping its retained service.

`_native_support_aperture_schedule` now probes at most two already-certified,
deferred supports, under ten-second per-worker and outer-wave bounds. A fresh
native aperture witness may promote only its matching support/net. Failed,
malformed or timed-out probes preserve route-first ordering. The finite menu
is passed to the normal relocation transaction; no admission gate, history
rule, movement bound or fabrication profile changes. v94 remains unchanged.
Focused regression: **310 tests passed**, log
`build/owner-articulation-20260927/aperture-schedule-regression.log`.

Hub wave **aq** uses ap's unchanged winner and scoped history through the normal
coordinator. Service `cec-hub-aperture-schedule-20260928-aq.service`, exact
invocation `e26b4d6b21b247a7950ca7ba77ac4777`, output
`build/event-driven-hub-20260928-aq/route/`, bounded 720 s/8 GiB, no restart.
Full regressions and a fresh PCIe replay are running alongside it. No aq
placement, routing improvement or release result is claimed in this section.

### aq live residual findings; witnessed menus must also rank eligible supports

The first scheduling repair passed **936 tests plus 24 subtests in 135.49 s**.
Fresh PCIe native control: **81.910 s**, zero opens/qualified structural DRC,
source unchanged, only preexisting `pairs_ok` and pending `thermal_ok` failed.
Evidence: `aperture-schedule-full-regression.log` and
`pcie-aperture-schedule-control/` under `build/owner-articulation-20260927/`.

aq's residual phase finished unchanged at **180.982 s**, but the outer route
stage is still running at this note. Fresh certificates made R37 and C10 both
eligible, so the deferred-only probe had no targets. Two R37 speculative moves
used **57.678 s** and **53.127 s**, before C10's actual aperture trial was reached.
The small C10 proposal passed native electrical geometry and physical checks,
and **restored all three disturbed support connections** (USB_VBUS and GND
each one native component). The target stayed open: its lease was only
**5.930 s**, constrained by the nearly exhausted parent budget. The subsequent
target-recovery worker was correctly *not dispatched*: only **3.588 s** remained
against a 5 s finalization reserve. This is an incomplete budget-limited trial,
not a measured geometric rejection or evidence that the new aperture cannot
route. No changed copper/placement was accepted.

The generic scheduler now inspects up to two certified supports across both
eligible and deferred lists. A fresh witnessed aperture menu ranks before
speculative support moves even when both were already eligible. The finite
menu is reused by the transaction, avoiding duplicate native proposal work;
the unaffected target ordering is stable. Worker failures still cannot become
permanent pose refusals. New unit coverage uses renamed supports and verifies
this exact starvation case. Focused tests: **311 passed**; full regression and
fresh PCIe v2 control are running. v94 remains unchanged because this is
scheduling, not a different route/geometry recipe.

The exact aq completion listener, Windows PID **15444**, was verified **armed**
at `2026-09-28T05:37:57.161Z`; bridge stderr empty. It watches invocation
`e26b4d6b21b247a7950ca7ba77ac4777`, not an interval. The periodic monitor remains
PAUSED. Its prompt directs the next continuation to read newer sections here.

### aq completed; ar gives the witnessed support its first full trial

aq finished in **465.050 s**. The accepted winner is still byte-identical
**a7635e0730**, one open and zero qualified structural DRC. Its global reroute
did not improve on the parent; the original family stayed unchanged. The
one-shot event was delivered once (`event/state.json: sent`). Exact completed
invocation/MainPID zero were verified before stopping the retained aq service.
No new board/render was published.

The eligible-support ordering fix passed **937 tests plus 24 subtests in
136.22 s**, log `aperture-schedule-v2-full-regression.log`. The final fresh PCIe
coordinator replay took **82.511 s**: zero opens/qualified structural DRC,
unchanged source, only preexisting `pairs_ok` and pending `thermal_ok` failed.
Evidence: `pcie-aperture-schedule-v2-control/native-control.json`. These paths
are under `build/owner-articulation-20260927/`. `git diff --check` passes for
this slice. No PCIe, ATX or stack authority was modified.

Normal Hub wave **ar** launched from aq's unchanged winner and v94 history.
Service `cec-hub-witness-first-20260928-ar.service`, exact invocation
`195fa0c6b81547a6abd7a945487fc36e`, output
`build/event-driven-hub-20260928-ar/route/`, bounded 720 s/8 GiB, no restart.
Inspect that the measured support is first and receives the normal target
lease, then follow native target and support restoration evidence. A local
aperture witness, a timeout, or restored support nets alone is not closure.
The still-incomplete aq attempt must not become a permanent pose refusal.
No ar result is claimed yet; only publish an independently admitted genuinely
changed winner. Existing accepted Hub remains not fabrication-ready.

ar's one-shot listener, Windows PID **21056**, was verified **armed** at
`2026-09-28T05:43:22.085Z`, with empty bridge stderr and matching active/running
invocation/MainPID 2112529. Free workspace storage is **58 GiB**, above the
16 GiB floor. Periodic monitoring remains paused. The local PC/app must stay
running for the callback; this is not reboot-safe orchestration.

### ar completed; complementary access and independent electrical companions

ar finished in **228.431 s** (residual phase **178.520 s**) without changing
accepted Hub **a7635e0730**: one open, zero qualified structural DRC. The new
scheduler did give C10's measured aperture the first full **35 s search / 40 s
worker** lease. Its small displacement passed physical/electrical geometry
and restored all three support connections. The target still refused without
a timeout: U11.5 now had **one legal local POFV launch**, but R37.2 and the
native-connected R38.1/track alternatives had no usable seats. This is actual
opposite-end access evidence, not another parent-budget starvation. The ar
completion was reviewed; the exact terminal invocation/MainPID zero were
verified before its retained service was stopped.

Private feasibility probes (none are admitted placements, published boards,
or normal coordinator improvements):

| Probe | Seconds | Native result |
|---|---:|---|
| as | 157.240 | C10 plus rigid R37/R38 move restored 6/6 support connections, 0 qualified DRC, target still open; remaining poses physically refused |
| at | 126.607 | Native via-access-derived translations, 12 finite combinations, all physically refused |
| au | 130.328 | Added whole-cell 180-degree poses, 12 combinations, all physically refused; connector courtyard and fixed copper conflicts |
| av | 258.401 | Keep proven R38 companion stationary, move R37; three routed trials obtained legal seats at both target ends but each ended with 4/5 supports restored, 2 opens and 2 qualified DRC, so all rejected |

Evidence respectively under `build/coupled-aperture-probe-20260928-as/probe/`,
`build/dual-aperture-probe-20260928-at/probe/`,
`build/oriented-aperture-probe-20260928-au/probe/`, and
`build/independent-support-probe-20260928-av/probe/`. Each `summary.json`
records exact source identity, finite budgets and unchanged input families.
av service `cec-hub-independent-support-probe-20260928-av.service`, invocation
`50d21735977d414fb59506f669ce0ad7`, exited successfully and was stopped only
after exact terminal identity/MainPID zero verification. No listener was
needed for these probes: their results were reviewed in the active turn.

`cec_endpoint_via_access.py` now produces finite geometry-derived passive
poses from actual all-layer via clearance, approved fabrication geometries,
actual moving pads, full-cell copper scoring and native body-boundary events.
It does not emit copper or grant placement/routing admission. It remains an
experimental producer used by these private probes, **not yet integrated into
the normal coordinator**. The source-free preliminary field is not ownership
authority: every returned site is rechecked on the actual temporarily moved
land and the original native board is restored.

`cec_support_cell_topology.stationary_partition` distinguishes complete
electrical terminal accounting from mandatory rigid mechanical motion. Only
a fresh, exact private-cell topology proof can keep an explicitly declared
electrical companion stationary. Real groups, locks, shared buses, ambiguous
owners and nonlocal companions refuse. The compound constructor independently
re-proves the partition, refuses conflicting moves, records every disturbed
branch and checks stationary poses against the original parent. No support
connection, full-board gate or copper/placement authority is waived.

Validation: **996 tests plus 24 subtests passed in 138.23 s**,
`build/owner-articulation-20260927/independent-support-full-regression.log`.
Fresh normal PCIe coordinator replay **82.023 s**, zero opens/qualified DRC,
unchanged source, same preexisting `pairs_ok` and pending `thermal_ok` failures;
`pcie-independent-support-control/native-control.json` in that same directory.
The articulated endpoint menu produced eight current-source proposals in
15.707 s, with zero advisory body overlaps or new fixed-copper conflicts;
that local evidence did **not** qualify their routing.

av's exact diagnostics identify the next distinct problem: both target ends
have seats (one at U11 and eight total at the moved R37), but all tested
single-layer and multilayer middle paths refuse. The stationary R38 branch
also still needs a restored connection. Do not just repeat av: inspect the
middle-search trace and the USB_VBUS netclass regression. A private exact
reconstruction is running at
`build/owner-articulation-20260927/independent-middle-trace/`, produced by
`tmp/trace_compound_middle_20260928.py`. No result is claimed here yet.
The accepted/published Hub remains unchanged and **not fabrication-ready**.

### v95: canonical multilayer graph and future-power guard parity

The exact private reconstruction confirmed legal short moves at the new
endpoint seats, but the prior middle router failed. A resolution control at
the same placement tested each failing F.Cu/B.Cu/SIG2 single-layer middle
path at the default grid and **0.25, 0.125 and 0.0625 mm**; all refused.
Evidence: `build/owner-articulation-20260927/middle-resolution-control/`.
Finer resolution alone is not the demonstrated repair.

Two generic omissions were found in `_multilayer_maze_lastmile_ops`:

- The single-layer search allowed exact 45-degree hops, but the multilayer
  fallback was Manhattan-only and lacked endpoint-residue diagonal axes.
- Its planar moves checked existing native copper but not the future-power
  reservation guard used by the single-layer search. Its via guards did
  check those reservations; that did not protect intervening track segments.

The multilayer search now uses the existing exact octilinear neighbour
function, bounded one-hop endpoint-aligned axes, Euclidean hop lengths and
admissible length/heuristic bounds, positive-direction collinear collapse,
and the same future-power reservation check on every full-width hop. Via,
layer-role, clearance, hole, edge and final admission requirements are
unchanged. It also records bounded middle-search diagnostics: visited area,
closest approach, touched search-window boundary, rejected edge/copper/power
hops, finite examples, and deadline versus bounded-graph exhaustion. These
are explicitly **not global no-path proofs or release authority**.

This is an actual route-capability/guard change, so refusal-history revision
is now **2026-09-28-octilinear-multilayer-guard-v95**. No arbitrary history
reset was used to repeat an identical search. New synthetic coverage checks
translated/reflected off-grid diagonals with an intermediate layer change,
length bounds shorter than Manhattan distance, native future-pour collision
checks, blocked diagonals and correct timeout reporting.

The exact same private reconstruction now closes the **U11-to-R37 target
segment** in its normal guarded search. It still restores **4/5** support
obligations: the stationary R38 branch remains disconnected. Native scoring
is **one open and two qualified structural findings**, both `track_dangling`
(the retained old signal branch and a USB_VBUS stub). Do not confuse these
with the raw via-size/annular warnings: the moved USB pad via independently
passes the native same-net POFV geometry proof. The USB_VBUS width-craft
regression observed in av still needs a fresh craft/cleanup investigation;
this probe does not waive it or establish a finished candidate. Evidence:
`build/owner-articulation-20260927/octilinear-middle-trace/{exact,score}.json`.
The private trace's exact-reconnect time was **51.871 s**. Nothing was admitted
or published; the accepted Hub is still **a7635e0730**, one open, zero
qualified structural DRC, and not fabrication-ready.

Focused validation: **123 passed plus 8 subtests in 2.28 s**. Full validation:
**1017 passed plus 24 subtests in 133.18 s**. Logs are
`multilayer-graph-regression.log` and `multilayer-full-regression.log` under
`build/owner-articulation-20260927/`. Fresh PCIe coordinator control:
**79.018 s**, unchanged source, zero opens/qualified DRC, same preexisting
`pairs_ok` and pending `thermal_ok` failures; evidence in
`pcie-multilayer-guard-control/native-control.json`. Slice `git diff --check`
passes. The endpoint-via placement producer and compound trial remain
experimental; only the reusable routing graph/guard change is integrated
into normal routing.

Normal Hub wave **aw** is running through the coordinator from ar's unchanged
winner. Service `cec-hub-octilinear-middle-20260928-aw.service`, exact invocation
`1bfac41d6db040a885cc54a461294d88`, output
`build/event-driven-hub-20260928-aw/route/`, bounded **720 s / 8 GiB**, no restart.
Review actual current certificates and target/support closure before choosing
another experiment; do not substitute private segment closure for a full
board result. Moved supports still require independent original-parent
placement/copper/fill proof before promotion. The dashboard responded HTTP
200 on port 8090 and workspace free space is 58 GiB. Periodic monitoring
remains paused; an exact one-shot listener is being armed for aw.

aw listener Windows PID **30096** was verified **armed** at
`2026-09-28T06:36:27.374Z`; bridge stderr is empty and the matching service is
active/running, MainPID **2146279**, invocation
`1bfac41d6db040a885cc54a461294d88`. Accepted Hub, PCIe control, ATX placement
and stack-authority SHA256s were rechecked unchanged. The periodic automation
remains PAUSED. The project helper watches the actual systemd completion,
not a timer or built-in desktop event trigger. The PC/app must stay running;
this callback is not reboot-safe. Official product guidance was checked at
<https://learn.chatgpt.com/docs/automations> without changing product settings.

### aw unchanged; whole-cell articulation and original-parent branch boundaries

aw completed in **446.809 s**, unchanged accepted Hub **a7635e0730**, one
open and zero qualified structural DRC. Its residual phase used **180.011 s**.
It tried C10's witnessed aperture first but could not restore the target in
that single-support pose. Later effort reached an inflight worker with only
**0.077 s** of its requested 90 s available; this is a budget interruption,
not a native no-path proof. The normal pipeline did not use the experimental
compound placement producer. Exact terminal identity/MainPID zero were
verified before stopping aw. No new board or render was published.

The private v95 reconstruction proves the middle-route improvement, but
leaving R38 stationary strands the shared divider branch. The next bounded
constructor supports **2-4 independent cells within the existing four-ref,
6 mm displacement and eight-removed-track envelope**. An electrical companion
may move independently only with reciprocal declarations and fresh native
private-cell proofs from the same original owner/net. Undeclared peers,
mechanical groups, locks, conflicting stationary declarations and missing
terminals still refuse. This is not arbitrary connector or IC motion.

New `cec_compound_boundaries.py` addresses sequential-staging phantom anchors:
when the complete isolated copper branch between two moved SMD pads is
removed, its old midpoint must not remain a target. Native original-parent
shape contacts must prove exactly those two pads, with no external track,
via, extra terminal or same-net zone contact. Unknown removed copper refuses.
Only then are the two transient midpoint obligations replaced by one exact
live pad-to-pad obligation. The exact-restoration worker consumes those live
identities. Complete final native net connectivity, geometry, copper/fill,
craft and independent original-parent placement admission remain mandatory.

Private trial **ax**, service `cec-hub-independent-cell-probe-20260928-ax.service`,
invocation `deee9f8cc9bd451bbd090cf14f9a25a5`, completed **173.645 s**. It
successfully constructed and proved the original R37/R38 internal branch
rebinding, but **all 12** complete placements were physically refused. The
first pair genuinely overlapped courtyards and shorted foreign pads. Native
gates caught it. The finite individual menus had clustered both independently
moved resistors in the same pocket; rerunning those lists cannot help.
Exact terminal identity/MainPID zero were verified before stopping ax.
Evidence: `build/independent-cell-probe-20260928-ax/probe/`.

The experimental endpoint-access producer now has an explicit optional
spatial-diversity mode. It preserves the best quality tier, then samples
separated positions instead of spending all slots on adjacent lattice points.
Quality is measured once per candidate, not repeatedly inside farthest-point
selection. Diversity occurs before the native expensive-site cap and again
at the returned-menu cap. All moved-pad/fabrication/native-clearance checks
still run. Normal producer defaults are unchanged. The private multi-cell
driver ranks finite joint combinations by advisory body overlap and shared
endpoint distance; actual physical DRC remains authoritative. v95 remains
the normal router revision; these placement experiments are not integrated
or accepted pipeline placements yet.

Validation: **1037 tests plus 24 subtests passed in 138.83 s** at
`build/owner-articulation-20260927/diverse-cell-full-regression.log`. The last
additional conservative same-net-zone guard was separately covered by the
latest focused **227 passing tests in 2.78 s**, `diverse-cell-final-focused.log`.
Fresh PCIe normal control: **80.799 s**, zero opens/qualified structural DRC,
source unchanged, same preexisting `pairs_ok` and pending `thermal_ok` terms;
`pcie-diverse-cell-control/native-control.json`. Slice diff checks pass.

Private trial **ay** is running from aw's exact unchanged winner/report:
service `cec-hub-diverse-cell-probe-20260928-ay.service`, invocation
`cdf3bd200a5143888562aed69dd22f4f`, output
`build/diverse-cell-probe-20260928-ay/probe/`. Limits remain **12 proposals,
3 route trials, 420 s search, 540 s service / 8 GiB**. The first physical
proposals were refused; no ay improvement is claimed yet. Review its precise
completed evidence before deciding a successor. A `potential_gain` alone is
not admission: moved supports still need full original-parent proof and the
normal coordinator's full validation. Do not promote the old private replay
or republish unchanged a763 bytes. The accepted Hub remains not fab-ready.
An exact one-shot completion listener is being armed for ay; periodic
monitoring remains paused. Storage remains above the 16 GiB floor.

### ay/az: joint geometry finally closes the private graph; admission still refuses

ay finished **172.673 s**, all 12 proposals physically refused. The first
R37/R38 pair had overlapping courtyards and **0.1901 mm actual clearance
against 0.2000 mm required**. Its exact callback was sent at
`2026-09-28T06:59:23.023Z`; terminal identity/MainPID zero were verified and
the retained service stopped. Spatially diverse independent menus alone do
not solve joint placement. No board was admitted or published.

New generic `cec_joint_pose_frontier.py` derives bounded separating contact
events from the native geometry of **all proposed poses together**, including
stationary bodies/foreign pads and, in the final version, saved native
track/via shapes with project/local clearance resolution. It retains the
original 6 mm/four-ref domain, caps cumulative adjustment at 1 mm, depth at
two by default, and explores a finite frontier. It never moves stationary
objects or removes copper. A shifted pose loses its old via-access/copper
witness; native reconstruction, route proof and independent admission remain
mandatory. Conservative bounding envelopes order/propose, never qualify.

Private trial **az** used joint body/pad refinement before the saved-copper
extension. Service `cec-hub-joint-contact-probe-20260928-az.service`, invocation
`34018bbd655a4817b1c0ccb1f5058915`, completed **186.661 s** at its three-route
trial limit. Trials **03, 04 and 05 each closed the target and all seven
support obligations**, yielding **zero unconnected / one qualified DRC**.
The remaining defect was the original USB_VBUS pad neck
`14f574c6-144c-4e1c-a121-c3ef48b73f6c`, now dangling and no longer width-qualified
after its owner moved. The earlier three proposals hit authored copper, not
each other. This motivated adding native saved-copper constraints. az's
exact terminal identity/MainPID zero were checked before stopping it.

Private qualification **ba**, invocation `6f1d47eb496b436190906172ef227d6d`,
completed **22.016 s**. It exercised the existing production dangling cleanup
on a new private copy of az trial 03. Cleanup removed the old unlocked track,
then its now-dangling **locked** USB via
`e0a4b171-281f-46c7-8813-196e8270e3e8`. Result: **zero opens / zero qualified
DRC and nonregressing craft**, but independent original-parent admission
**refused** `not_an_isolated_placement_transition`: the locked-copper prefix
was no longer preserved. This refusal is correct. Do not publish or admit
`build/compound-qualification-20260928-ba/qualification/cleaned/board.kicad_pcb`.
The source, proposed family and accepted board remained unchanged. ba was
stopped only after verifying its exact terminal identity/MainPID zero.

The root cause is now an explicit placement dependency: an immutable grouped
narrow escape remains qualified only while its real owning pad contact is
retained. Native-connected island alternatives can restore the logical net
while leaving this protected narrow tail behind. New
`cec_protected_neck_pose.py` captures actual pad contact on a grouped,
below-class-width neck, filters contact-losing proposals, and generates
half-turns about the owning pad centre. No pin/net exchange, extra clearance,
width waiver, group deletion or permission to remove protected vias is added.
Both endpoint-access menus and joint refinement respect this contact domain.
Joint refinement now also sees saved copper; it may conservatively overcount
incident branches, but never presumes removal authority. These are still
experimental private compound producers, not integrated normal coordinator
support moves. Normal router revision remains v95.

The private probe now calls the same exact-DRC cleanup stage as the production
support transaction, closing a diagnostic/production parity gap. A resulting
`potential_gain` still owes **full original-parent** placement/copper/fill and
normal coordinator selection; zero counts alone are never sufficient.
`tmp/qualify_compound_candidate_20260928.py` is a reusable diagnostic wrapper
for these existing gates, not a publisher.

Validation: final relevant suite **735 passed in 7.71 s**, including native
translated/front/back fixtures, protected track/via obstacles, contact-centred
rotations, native circular-pad exclusion, cumulative motion bounds, stable
source bytes and source restoration on error. Eleven old candidate-frontier
mock tests initially failed because their worker stub/report schema predated
the production pose-ranking and craft-history fields. The fixtures were
updated to assert those current fields, with no production gate weakened.
Logs: `build/owner-articulation-20260927/joint-protected-neck-regression.log`.
Fresh PCIe normal-coordinator control after initial joint refinement took
**80.245 s**, zero opens/qualified DRC, unchanged source and the same existing
`pairs_ok`/`thermal_ok` failed terms. It predates the last saved-copper/contact
extension; those are covered by the final synthetic suite, not a claimed
successful PCIe exercise of the private compound feature.

Accepted Hub remains **a7635e0730**, one open and zero qualified structural
DRC, not fab-ready. Hub/PCIe/ATX/stack authority hashes were checked unchanged.
No replacement board/render was published. Dashboard HTTP 200; 58 GiB free.

Bounded successor **bb** is running from aw's exact source/report with native
joint-copper and protected-neck contact constraints. Service
`cec-hub-protected-joint-probe-20260928-bb.service`, invocation
`e9c8a3e59bd24c94a3b8459fd2d6a126`, output
`build/protected-joint-probe-20260928-bb/probe/`; 12 proposals, three route
trials, 420 s search, 540 s service / 8 GiB, no restart. Review whether the
contact-preserving endpoint menu is nonempty before another search. A refused
or empty menu is not a global no-path proof. Do not broaden the locked-copper
guard to admit ba. An exact one-shot listener is being armed; periodic
monitoring remains PAUSED. Official guidance was checked at
<https://learn.chatgpt.com/docs/automations>; the project bridge requires the
computer/app running and is not reboot-safe or a built-in desktop event task.

### bb fails early on an empty menu; bounded alternative mobile-member test

bb completed **50.991 s**, `one_native_pose_menu_empty`, no route trials. The
one-shot listener PID **29396** sent the completion event once at
`2026-09-28T07:22:15.921Z`, empty stderr, and the event was reviewed in the
same active turn. Exact terminal identity/MainPID zero were verified before
stopping bb. Its completed callback is consumed; do not rearm it.

This is not a global no-path result: requiring a legal through-via aperture
on every independently moving member overconstrains a private electrical
cell. One member can remain at its protected escape while the other provides
the changed access. `cec_support_cell_topology.articulated_primaries` now
enumerates the at-most-three native members of the same original proved
private cell, with fresh owner/net/complete-terminal/stationary partition
proof for each. No undeclared/remote/shared-bus member is substituted.
The private driver may test the next member only when the first member's
endpoint menu is empty; it does not silently fall back to unqualified rigid
poses. Menu identities/counts and empty-menu attribution are now persisted.
Normal pipeline integration is still deferred until a full native admission
succeeds. Final related tests **740 passed in 7.62 s**:
`build/owner-articulation-20260927/mobile-primary-regression.log`.

New **bc** tests that choice with the same original accepted parent and
source-scoped refusal evidence. Service
`cec-hub-mobile-primary-probe-20260928-bc.service`, invocation
`5704f273c483429eb7119421c20ff6a5`, output
`build/mobile-primary-probe-20260928-bc/probe/`, same 12/3/420 s search and
540 s / 8 GiB service bounds. It leaves the nonselected private member
stationary and still performs original-parent construction, protected-fill,
native placement, exact target/support restoration, production cleanup and
craft/native DRC checks. No accepted source changed. A successful private
`potential_gain` must go through `cec_route_placement_admission.prepare` and
full coordinator validation before any publication. Never promote az/ba
just because their private open count is zero. A one-shot actual-completion
listener is being armed for bc, with periodic monitoring still PAUSED.

bc listener Windows PID **22468** was verified **armed** at
`2026-09-28T07:26:06.729Z`, empty stderr. The exact matching invocation was
active/running, MainPID **2183299**. This is the only pending completion
callback; ay/bb callbacks have already been consumed. No periodic task was
enabled. Keep the app and machine running for this local project helper.

### bc completion and v96: an omitted ordinary-barrel escape domain

bc completed **209.085 s**, `bounded_route_budget`. Trials 00/03/06 all
preserved the stationary protected USB escape but failed the target and one
of six support connections: **2 opens / 0 qualified structural DRC**.
Its completion was consumed and exact terminal invocation/MainPID zero were
verified before stopping the retained service. No accepted source changed.

Read-only reconstruction after the companion vacated its old site still gave
zero protected-contact via-access poses for the stationary member in all
three cells (**32.328 s**). This does not support adding a conditional
placement-menu feature. `conditioned-mobile-menu/summary.json` records it.

Endpoint bridge diagnostics instead showed legal ordinary barrels but no
legal launch within the original 4-mm sampled domain. Four exact failed
launches remained refused with finer .25/.1-mm grids. A native 8-mm domain
probe found an exactly guarded .2-mm launch at **7.106 mm**, in **3.105 s**,
without installing copper or relaxing a guard. Evidence:
`build/owner-articulation-20260927/bc-stub-counterfactual/` and
`bc-stub-domain.json`. This is a found local path, not whole-route admission
or a global impossibility claim for any unsearched region.

Shared `cec_fr._lastmile_bridge` now tries one **4-8 mm, .5-mm-pitch** annulus
only when the original local SMD search found no seats and maze/lattice search
is allowed. `cec_escape_frontier` bounds the proposals and shares expensive
search across directions instead of spending every attempt at nearest sites
behind one obstacle. `max_seat_radius_mm=4` retains the old domain; bounds
cannot exceed 8. Ordinary barrel geometry, native copper/hole clearance,
future power reservations, complete launch guards, length and wall limits
remain unchanged. Local successes never enter the fallback. No board name,
reference, net or coordinate is special-cased. Revision **v96**.

Validation: **933 tests + 8 subtests passed in 18.35 s**, including native
rotated/front/back inner-bus obstructions, preserved locked originals,
ordinary-via minima, exact canonical trace geometry, bounded direction
diversity, short-route limits and future-pour refusal. Fresh PCIe full normal
coordinator replay **79.079 s**, **0 opens / 0 qualified structural DRC**,
source family unchanged; existing `pairs_ok` / `thermal_ok` failed terms
remain. It is a nonregression control, not a newly fab-qualified PCIe board.
Evidence: `expanded-escape-regression.log`, `pcie-expanded-escape-control/`.

### bd: zero-open private candidate; be refuses a segmented pad-root proof

The same bounded compound pilot under v96 finished **150.587 s** with
`potential_gain`:

- Trial 00 closed the original target, 5/6 supports, **1 open / 0 DRC**.
  Its support attempt timed out at an 11.556-s lease; 21.718 s remained after
  other supports finished. This is a separate bounded-budget-recovery lead,
  not a reason to rerun the successful trial or loosen routing rules.
- Trial 03 closed target and **6/6 supports**, **0 opens / 0 qualified
  structural DRC**, craft nonregression, original input families unchanged.
  It remains a private candidate until independent original-parent admission.

Output: `build/expanded-escape-probe-20260928-bd/probe/trial-03/board.kicad_pcb`.
Service `cec-hub-expanded-escape-probe-20260928-bd.service`, invocation
`1bda2f4731cf4ad79ed68920c345a37e`. Exact completion listener Windows PID
**30652** was verified armed and delivered once during the active turn.
The event was consumed; exact terminal identity/MainPID zero verified and
service stopped. No pending bd callback remains.

Independent **be** cleanup/placement qualification took **18.83 s**. It
confirmed 0/0, craft nonregression and **all protected original copper
preserved**, unlike ba. It refused `existing_copper_changed` because the
branch ownership proof required exactly one native contact node per pad.
An old two-segment GND branch had a .228-mm segment entirely within the
same roundrect land, so it had two valid contained nodes at a unique root.
This is not authority to delete a protected via or accept a through-pad path.
Source geometry: `build/owner-articulation-20260927/bd-branch-roots.json`.
be invocation `de972f097f7a4ce8995fce589d3cba67` was verified terminal/MainPID
zero then stopped. No callback was armed for be.

### v97: prove a contiguous native convex-land root prefix

`cec_support_branch_preservation` now recognizes a contiguous prefix inside
one native convex land, with exactly one terminal root. Native containment
uses zero tolerance; only rectangle/circle/oval/roundrect shapes qualify.
Custom/concave assumptions, separated re-entry, an interior/through-pad
owner, locks, groups, deleted vias and any missing original connected member
still refuse. No deletion receipt is trusted. The same eight-item bound,
unique owner and full surviving-member connectivity proof remain mandatory.
Final relevant suite **947 tests + 8 subtests passed in 17.82 s**, including
new translated/back-side positive and adversarial pad-prefix cases.
`pad-prefix-proof-tests.log`: 123 passes; `convex-root-regression.log`: full
related result. Routing geometry is unchanged from v96; revision **v97**
marks the added independent proof capability.

Independent successor **bf** is running on the same original a763 parent
and bd trial03: `cec-hub-convex-root-qualification-20260928-bf.service`,
invocation `53797a1ef4ef476bbe47c1adebc031ab`, directory
`build/convex-root-qualification-20260928-bf/qualification/`, 300 s / 8 GiB.
It must pass original-parent placement/branch/fill/authority gates and full
coordinator grading. Neither private zero counts nor the new root proof is
publication authority. A normal coordinator selection and final verification
are still owed before replacing the accepted dashboard board. Accepted Hub
is still **a7635e0730**, one open / zero qualified structural DRC, not fab-ready.
Compound proposal integration remains experimental; the ordinary escape
fallback itself is in the shared production router. Periodic task stays
PAUSED. Official automation guidance was refreshed at
<https://learn.chatgpt.com/docs/automations>; the existing project completion
bridge is not a built-in arbitrary desktop event trigger and needs app/PC on.

### bf passes independent admission; normal coordinator bg in progress

bf completed **48.068 s**. `placement-revalidation/revalidation.json` is
**ok**: all original protected copper, all surviving native members of the
five changed unlocked branch segments, protected fill, exact component/pad
definitions, frozen power authority, complete physical placement and source
rules pass. The only moved references inferred independently are C10/R38;
the original protected R37 USB escape remains stationary. No exception was
added for these names or their geometry. The accepted parent and all controls
were rehashed unchanged. Exact bf invocation/MainPID zero verified; stopped.

`graded-oracle.json`: **0 opens / 0 qualified structural DRC**, 2507.56 mm,
196 vias, routing complete, pairs/decoupling/netclass/pin-escape gates pass.
Compared with accepted a763: one fewer open, +40.82 mm / +4 vias. These are
pre-final-coordinator metrics. `courtyard_edge_ok`, `injection_ok`, and
`thermal_ok` still fail: C37 .475 vs .8 mm, no complete current-injection
model, thermal deliberately skipped while other release gates fail.
This is explicitly **not fabrication signoff**.

Normal `_route_stage` successor **bg** runs from the independently revalidated
bf `placement-revalidation/board.kicad_pcb`, not an unadmitted scratch board.
Output `build/zero-open-coordinator-20260928-bg/route/`, service
`cec-hub-zero-open-coordinator-20260928-bg.service`, invocation
`7163f78447804407870fe2b521f12fcf`, 600 s / 12 GiB, no restart. It performs
normal selection/finish/history. Final verification must preserve its immediate
bf source and the independent original-a763-to-bf proof chain before publishing
as a routing checkpoint. `tmp/verify_polish_boundary_20260927.py` is appropriate
only against the bf parent if that last boundary has unchanged placement.
No new accepted image/board has yet been published. An actual-completion
listener is being armed for bg; periodic task remains PAUSED.

### bg selected, independently verified, and published: routing closed

**Later fabrication continuation:** see
`docs/hub-fab-readiness-and-field-thermal-audit-2026-09-28.md` for checkpoint
`4aba00e18b`, automatic field repair, exact remaining release blockers and the
conditional thermal screen. The zero-open bg result below is preserved history,
not the newest review checkpoint.

bg completed **65.375 s** and selected `incumbent_polish`. The selected board
and `route/winner.kicad_pcb` have SHA256
**4a5856a5eda920bf3d5778a661f3cd77d6ca5c5e277ddb7ab059f92b3a5a1730**.
Final counts are **0 opens / 0 qualified structural DRC**, **2506.02 mm /
196 vias**. Relative to the original accepted a763 checkpoint this removes
the last open at a cost of **39.28 mm and four vias**. Normal finishing saved
1.54 mm from the independently admitted bf precursor. Pairs, decoupling,
decoupler cells, netclass geometry and pin escape pass. This is routing
closure, not an unqualified claim of zero manufacturing issues.

`build/zero-open-coordinator-20260928-bg/final-boundary.json` independently
passed in **25.134 s** against the immediate bf parent. It confirms unchanged
placement, population, rules and power authority, preservation of protected
parent copper and native fill, and full physical/pair checks. The complete
proof chain is the original a763 parent -> independently admitted bf placement
transition -> bg coordinator finish. Release authority remains **false**.

Published archive:
`build/board-archive/20260928-hub-standard-rev2-checkpoint-continuation-4a5856a5ed/`.
The board family, source-bound independent proofs, front/back models-off PNGs,
and all six native copper-layer SVGs are included. Dashboard:
<http://localhost:8090/?id=20260928-hub-standard-rev2-checkpoint-continuation-4a5856a5ed>.
HTTP and an existing in-app browser tab were checked; the new SHA, zero-open
counts, front image and eight render/layer panels were verified. Windows
review copies are in
`C:\Users\Admin\Documents\CEC-Board-Reviews\hub-zero-open-4a5856a5ed\`.
The displayed verdict is `ROUTING COMPLETE / FAB QUALIFICATION PENDING`;
the dashboard's diagnostic/failed-gate badge is not a fabrication approval.

The remaining release gates are unchanged: **C37 courtyard-edge .475 mm vs
.8 mm**, **current-injection qualification missing**, and **thermal skipped
while the other gates fail**. Fresh route sanity also reports four covered
backtrack advisories and one detour; these were not erased or counted as
qualified structural DRC. Full raw DRC/manufacturing debt still requires
review. No thermal result or load budget was invented.

The bg one-shot completion bridge (Windows PID 30000) sent its event once at
07:54:50.267Z. That event was consumed in the active turn. The exact bg
invocation was confirmed terminal with MainPID zero before stopping the
service. All bd/bf/bg work is complete; **no routing job or pending completion
callback remains** and the periodic task was not reactivated. Do not run
unchanged zero-open routing waves merely to keep a process busy.

Next useful slices are a bounded fabrication-blocker audit/repair preserving
this checkpoint, then integration of the experimental compound proposal
producer into normal automatic coordination with the same independent
source-bound admission. The shared extended ordinary-via escape and convex
pad-root proof are production-generic; the compound producer is still
experimental and must not be described as fully unattended integration.
