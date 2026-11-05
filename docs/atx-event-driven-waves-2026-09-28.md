# Event-driven 24-pin waves, 2026-09-28

## User request and continuation contract

Run current 24-pin waves and wake the existing task on each completion or
plateau. This uses the existing one-shot systemd D-Bus listener and the local
Codex app-tool bridge, not a periodic model monitor. The old
`cec-board-suite-review-and-repair` heartbeat remains **PAUSED**.

Each service owns one bounded full pass. A terminating no-gain/plateau,
admission refusal, failure, or deadline therefore produces a completion event.
The listener does not infer board quality from a successful process exit:
the suite can finish successfully while the board remains blocked. Inspect
the suite result and native evidence on every wake. This is not a continuous
mid-solver plateau detector.

After each event, measure the result, publish the exact artifact, and choose
the next useful bounded pass. A repeated unchanged refusal requires a generic
causal repair or demonstrated new search coverage before another launch; do
not run an identical search indefinitely. Preserve incumbents, source-family
authority, protected copper, approved current margins, and mating geometry.
Do not change solver files while any wave is using them. If a new design
decision is needed, stop and ask rather than weaken admission.

## Initial pass A

- Board: `atx-24pin-rev3`, current BETA hierarchy.
- Source: `build/atx-hub-closure-20260928/atx-wave05/02-placement/board.kicad_pcb`.
- Source SHA-256: `1b08b39ec4756879c7a25e7f56a1b6c42c7f8c329a316d6dc092bea5ab4b7eb3`.
- Retained compact outline: 78 x 95 mm; no replacement placement requested.
- Unit: `cec-atx-event-20260928-a.service`.
- Invocation: `f5fd9b673bff418bb1ff3641012b97f8`.
- Launch evidence: `build/event-driven-atx-20260928-a-launch/launch.json`.
- Results: `build/event-driven-atx-20260928-a/suite.json` and the
  `atx-24pin-rev3/` child directory.
- Canonical full pipeline via `cec_board_suite.py`, one board, eight-worker
  ceiling, 128 craft trials, two rounds, one epoch, eight routing passes if
  placement/power admission succeeds, 180-second priority-repair budget.
- Board job deadline: 1,800 seconds. Service hard deadline: 1,920 seconds,
  allowing bounded shutdown/publication time. Memory cap: 16 GiB.
- Minimum free storage at dispatch: 16 GiB; approximately 58 GiB was free.

This expands the search beyond the immediately preceding four-trial diagnostic
pass and the older 64-trial pass. More compute is not itself an improvement;
the first wake must check whether the extra trials actually explored useful
new states. The prior power-construction failures remain real blockers until
new native evidence proves otherwise. Detailed signal routing is not claimed
to have begun merely because this full pipeline pass is running.

## Callback identity and operation

Existing task: `019fc466-54b1-7df0-9636-a6e801d73219`.

Windows configuration:
`C:\Users\Admin\Documents\New project\event-driven-atx-20260928-a\bridge-config.json`.

Windows delivery evidence:
`C:\Users\Admin\Documents\New project\event-driven-atx-20260928-a\delivery\state.json`.

The hidden Windows helper runs `scripts/cec_wave_completion_bridge.mjs`.
It inherits the current task identity and local app-tools connection, verifies
that it can read this task, then subscribes to the exact service invocation.
The installed app-tools adapter is used unchanged. A persistent exclusive
claim prevents duplicate dispatch. An uncertain delivery acknowledgement
must be inspected, not blindly retried.

For each subsequent pass, use a fresh service, launch directory, configuration,
and delivery directory. Bind the callback to the **actual** invocation from
`launch.json`. Verify `state.json` is `armed` for that identity before leaving
it unattended. A retained completed invocation can also be delivered if the
job finishes before listener attachment.

Keep the computer and Codex app running. This local bridge does not promise
survival across a Windows/app restart. On recovery, inspect the job and
delivery state before starting anything new; do not duplicate an uncertain
send or an active wave. No new recurring timer, new task, model server,
or paid API service is involved.

## Validation

- Installed app-tools read-only task probe succeeded for this exact task.
- `tests/test_systemd_completion_event.py` and
  `tests/test_retained_wave_run.py`: **14 passed**.
- Source board SHA was rechecked immediately before launch.
- Callback verified **armed** at `2026-09-28T18:28:53.104Z` for the exact
  invocation above; hidden Windows bridge PID was `32920`. The stderr log
  was empty. Treat the delivery state as authoritative, not this historical PID.
- Service verified `active/running`. Current-BETA source intake passed in
  12.8 seconds; placement round one generated 818 states and selected 128
  for evaluation. This is a running placement search, not routing admission.
- Physical baseline and remaining blockers are documented in
  `docs/hub-return-closure-and-atx-power-wave-2026-09-28.md`.

The Hub and immutable PCIe2 control were not edited or relaunched for this
campaign setup. No fabrication readiness is implied by the monitoring setup.

## Completion A and pass B

A delivered its callback exactly once at `2026-09-28T18:47:21.415Z`.
The board was blocked after 1,170.189 seconds, despite the suite service
exiting successfully. Its accepted decoupling improvement, unchanged three
rail refusals, causal virtual-bend repair and 244-test validation are recorded
in `docs/rail-virtual-anchor-repair-2026-09-28.md`.

Pass B uses the canonical `--continue-suite` lineage from A, whose output SHA
is `c7ce02137aecaf7c937d3365638754d667d8dcd7741b842d49ddbf8354d09035`.
No old board was substituted. This is a changed-engine verification pass,
not an unchanged broad placement retry.

- Service: `cec-atx-event-20260928-b.service`.
- Invocation: `2a8f182bfd0441a1a006e0157508f5f9`.
- Launch: `build/event-driven-atx-20260928-b-launch/launch.json`.
- Suite: `build/event-driven-atx-20260928-b/suite.json`.
- One board; eight-worker ceiling; eight trials/two rounds/one epoch;
  eight route passes only if placement/power admission succeeds.
- Board budget: 900 seconds; hard service budget: 1,020 seconds;
  16 GiB memory cap; 16 GiB free-space floor (57 GiB available at launch).
- Windows callback configuration:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-b\bridge-config.json`.
- Windows callback evidence:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-b\delivery\state.json`.

Review the exact-power/native result at the next wake. A constructor improvement
alone must not promote an electrically incomplete or thermally unqualified
board. The monitor remains one-shot and event-driven, with no periodic timer.

### Final disposition of B

B completed in 72.746 seconds and was reviewed directly in the still-active
task. The hidden Windows helper launch was **rejected by execution policy**
before execution. Its configuration exists, but no claim or delivery state
exists: **B was never armed**. Do not launch that obsolete configuration now
or replay its already-reviewed completion. No subsequent job is running.

The board output is unchanged from A. The new constructor reached 2/4 inside
the private craft baseline, but stale incoming craft evidence and pose-only
change accounting did not retain it. The full output remains 1/4 constructed,
with three refusals. See `docs/rail-virtual-anchor-repair-2026-09-28.md` for the
next generic integration fix. No electrical gain is claimed from the shorter
runtime, and no routing or fabrication admission was bypassed.

Before another unattended pass, the background helper launch must be allowed
and a fresh invocation's listener must be verified armed. Do not work around
the execution-policy rejection through another launch mechanism or reactivate
the periodic heartbeat. The first callback's successful delivery remains
valid evidence, but is not evidence that the second listener exists.

## User-authorized retry and pass C

The user replied "Should be allowed" and authorized a normal retry of the
hidden Windows listener launch. B is already reviewed; do not launch its old
configuration or duplicate that event. C uses a fresh service/invocation and
delivery claim. No alternate policy-bypass launch mechanism is used.

Before C, the stale-evidence and reconstruction-only retention defects were
repaired generically; see `docs/placement-reconstruction-evidence-2026-09-28.md`.
The new run uses B's exact retained SHA and the same 78 x 95 mm mechanical
envelope, 8-worker ceiling, 8 trials/2 rounds/1 epoch, 900-second board budget,
1,020-second service cap, 16 GiB memory cap and 16 GiB free-space floor.

Expected paths (launch/state receipts, not this paragraph, prove execution):

- Service: `cec-atx-event-20260928-c.service`.
- Launch: `build/event-driven-atx-20260928-c-launch/launch.json`.
- Results: `build/event-driven-atx-20260928-c/suite.json`.
- Windows configuration:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-c\bridge-config.json`.
- Delivery state:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-c\delivery\state.json`.

Check the reconstruction receipt at completion: better constructor counts
must not override a native regression. Keep the prior incumbent if refused;
repair the evidenced cause before another identical wave.

### C launch verified

- Actual invocation: `9c63a271f2844cc2965ff27525b34488`.
- Normal `Start-Process -WindowStyle Hidden` launch succeeded; bridge PID 2812
  was running and its stderr was empty at verification.
- Delivery state was **armed** at `2026-09-28T19:24:31.334Z`, bound to the
  exact invocation above. The service was independently `active/running`.
- This proves C's listener is attached, not that C has passed or completed.
  Read its later delivery and suite receipts for the eventual result.

## C reviewed; D uses the safer B incumbent

C's callback was acknowledged once at `2026-09-28T19:27:42.788Z`. The board
remained placement-blocked after 211.543 seconds. It gained a partial rail
but introduced three structural routing findings and two return-access
failures. Its exact rendered artifact remains available as a blocked
experiment, not promoted progress. See
`docs/composed-craft-admission-2026-09-28.md` for metrics, cause and tests.

Normal accepted placement moves now pass the same composed copper/native
guard as reconstruction-only candidates. Pass D deliberately continues from
**B**, SHA `c7ce02137aecaf7c937d3365638754d667d8dcd7741b842d49ddbf8354d09035`,
not C's regressed artifact. It uses 32 trials/round, two rounds, one epoch,
eight-worker ceiling, 900-second board budget, 1,020-second service cap,
16 GiB memory limit, and the unchanged 16 GiB free-space floor.

- Unit: `cec-atx-event-20260928-d.service`.
- Launch receipt: `build/event-driven-atx-20260928-d-launch/launch.json`.
- Suite: `build/event-driven-atx-20260928-d/suite.json`.
- Windows configuration:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-d\bridge-config.json`.
- Delivery state:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-d\delivery\state.json`.

This is a changed-admission verification and a larger finite proposal sample,
not evidence that construction has been repaired. After a repeated refusal,
fix the recorded landing/return-access constructor cause before a further
wave; do not repeatedly re-launch this portfolio. Old periodic heartbeat is
still PAUSED. Launch/state receipts must prove the new run and watcher.

### D launch verified

- Actual invocation: `691b12ef6b4b4dbfb7ac1f4223d922f3`.
- Hidden bridge PID 29396; empty stderr at verification.
- Delivery state **armed** at `2026-09-28T19:39:36.771Z` for that exact
  invocation; independently verified service `active/running`.
- Free WSL storage remained approximately 57 GiB. No source board, protected
  incumbent, Hub board or immutable PCIe2 control was overwritten.

## D reviewed; actual transition construction repaired before a further wave

D's callback was acknowledged once at `2026-09-28T19:47:07.944Z`. The composed
guard correctly rolled back its proposal and restored B exactly: there was no
accepted routing progress. A larger identical retry was not launched.

Instead, the constructor's silently omitted landing patches and disconnected
optional mirror proposals were traced and repaired generically. See
`docs/transition-landing-construction-2026-09-28.md`. The private replay retains
all 20 required new barrels and drops opens from 377 to 371 without increasing
the 5 structural or 2 route-quality findings, but still adds two return-access
failures. It is not an incumbent or a fab candidate. Those failures remain a
strict veto at the full-pass commit boundary.

The next pass uses the unchanged B incumbent and the corrected constructor,
not C or a diagnostic artifact. Only one bounded changed-engine pass is
authorized in this continuation; another plateau needs a causal return-access
construction fix before retrying. The periodic heartbeat remains PAUSED.

### E launch contract

E continues from `build/event-driven-atx-20260928-b/suite.json`, whose retained
PCB is also D's exact final PCB. It uses 8 trials per round, two rounds, one
epoch, an eight-worker ceiling, 900-second board budget, 1,020-second service
cap, 16 GiB memory cap and the existing 16 GiB minimum-free-storage floor.
This tests the repaired constructor end to end; no release gate is relaxed.

- Unit: `cec-atx-event-20260928-e.service`.
- Launch receipt: `build/event-driven-atx-20260928-e-launch/launch.json`.
- Suite: `build/event-driven-atx-20260928-e/suite.json`.
- Expected Windows configuration:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-e\bridge-config.json`.
- Expected delivery state:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-e\delivery\state.json`.

Record the actual invocation and `armed` receipt after launch. The completion
callback must inspect native landing evidence and the composed commit receipt,
not interpret a successful systemd suite exit as a routed/fab-ready board.

### E launch verified

- Actual invocation: `091db78e719b4461a340e7c63c3c6b45`.
- Normal hidden bridge launch succeeded, PID 32872; stderr was empty.
- Delivery state was **armed** at `2026-09-28T20:13:16.760Z`, bound to that
  exact invocation. The service was independently `active/running`.
- This is a custom local completion listener, not a periodic heartbeat or a
  built-in desktop event automation. It wakes the current task once the
  bounded pass exits, including a plateau/refusal exit. It requires the PC,
  WSL and app to remain running; no reboot persistence is claimed.
- D's actual model-free image endpoint returned HTTP 200, image/png,
  63,829 bytes, and was visually inspected before linking it. Its repeated
  board geometry is intentional rollback, not an old-board selection bug.

## E reviewed; return-aware constructor repaired before F

E's callback was acknowledged once at `2026-09-28T20:17:06.482Z`. The board
remained placement-blocked after 247.239 seconds and the composed guard
retained B byte-for-byte. No accepted progress is attributed to E. Its exact
model-free dashboard image was verified HTTP 200, image/png, 63,751 bytes,
and visually inspected.

The causal repair now feeds measured future ground-return reservations into
shared-rail construction and clips only new landing outlines around native
foreign objects and those reservations after outline cleanup. An exposed
optional-mirror endcap false-junction defect was also fixed. See
`docs/return-aware-rail-construction-2026-09-28.md` for the exact private replay,
scope limitations, 403 passing tests and unchanged PCIe2 0/0 native control.
The private replay has 371 opens versus 377, unchanged five structural and two
route-quality findings, all 38 prior return sites preserved and no declared
foreign-pour incursions. It is still partial construction, not an incumbent.

### F launch contract

One bounded changed-engine F starts from B's suite and uses 8 trials per
round, two rounds, one epoch, an eight-worker ceiling, 900-second board budget,
1,020-second service cap, 16 GiB memory cap and 16 GiB free-space floor.
Remaining free WSL storage before launch was approximately 57 GiB.

- Unit: `cec-atx-event-20260928-f.service`.
- Launch receipt: `build/event-driven-atx-20260928-f-launch/launch.json`.
- Suite: `build/event-driven-atx-20260928-f/suite.json`.
- Expected Windows configuration:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-f\bridge-config.json`.
- Expected delivery state:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-f\delivery\state.json`.

Launch and armed receipts, not this contract, prove that the pass and watcher
are running. The one-shot callback must inspect actual composed admission and
native evidence, not count private/proposed geometry as progress or confuse
suite exit zero with board readiness. The old periodic heartbeat stays PAUSED.

### F launch verified

- Actual invocation: `c77e660b76234e28953f2afce5d43486`.
- Normal hidden Windows bridge launch succeeded, PID 32584; stderr empty.
- Delivery state **armed** at `2026-09-28T20:40:00.816Z`, bound to the exact
  invocation above. Independently verified service `active/running`, main
  PID 2703355. This is launch/attachment evidence, not acceptance evidence.
- The next wake is the bounded pass's terminal event (including a plateau
  exit), not a five-minute timer. PC, WSL and app must remain running.
- The exact E dashboard view was queued in this task's browser panel.

## F reviewed; G is a changed-engine safety/composition verification

F's composed reconstruction was accepted: opens 377 to 371, unchanged five
scorer-filtered structural identities, source and engine stable. The board
still has only two constructed rail objects and remains placement-blocked.
Its retained SHA is
`9181a3a43781b69cf20e3688ba17e1f90b772b23f90f5455cb0b13d81d75a016`.

F's event reached this task although its Windows acknowledgement timed out;
the delivery state remains `delivery_unknown`. Do not retry that event.
See `docs/rail-transition-search-2026-09-28.md` for the observed delivery,
accepted F metrics, subsequent rejected diagnostic and generic repairs.

G uses F's retained suite with the same finite resource limits: 8 trials per
round, two rounds, one epoch, eight-worker ceiling, 900-second board budget,
1,020-second service cap, 16 GiB memory cap and 16 GiB free-space floor.
The repaired private replay currently retains F unchanged; this full pass
verifies integration/safety, not a promised routing improvement. No identical
retry is allowed after G without a demonstrated causal change.

- Unit: `cec-atx-event-20260928-g.service`.
- Launch receipt: `build/event-driven-atx-20260928-g-launch/launch.json`.
- Suite: `build/event-driven-atx-20260928-g/suite.json`.
- Windows configuration:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-g\bridge-config.json`.
- Delivery state:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-g\delivery\state.json`.

Launch and armed receipts must be recorded after successful attachment. Keep
the old heartbeat paused and do not edit solver files while G is active.

### G launch verified

- Actual invocation: `a5a563fe01d04f04a0646438d5a44fa7`.
- Normal hidden bridge launch succeeded, PID 31804; stderr empty.
- Exact-invocation delivery state **armed** at `2026-09-28T21:10:42.374Z`.
- Independently verified service `active/running`, main PID 2715357.
- Prelaunch regression: 422 tests and two subtests passed in 137.41 seconds;
  immutable PCIe2 control unchanged at zero scored structural DRC/opens.
- Hub incumbent and active Hub/ATX pair hashes remain unchanged. WSL had
  approximately 57 GiB free. The periodic heartbeat remains PAUSED.
- Launch/attachment evidence is not a claim that G has passed or advanced
  routing. The next continuation must inspect G's actual acceptance receipt.

## G reviewed; demonstrated constructor progress before H

G retained F exactly after 125.301 seconds: 371 opens, five scored structural
findings, two route-quality blockers and 2/4 constructed rail objects. Its
one-shot callback was acknowledged at `2026-09-28T21:12:01.227Z`. No repeat
portfolio was launched until a causal repair produced a natively admitted
private improvement.

See `docs/construction-placement-feedback-2026-09-28.md` for the generic
construction-to-placement feedback, native pad collision, layer-local pickup,
exact-proposal handoff and actual-contact graph fixes. Rejected intermediate
proposals were rolled back, not counted as progress. The final private trial
has 366 opens, unchanged five structural findings and no new topology fault;
standby input 1/1, 3/4 constructed rails, all 97 protected items and all 38
prior future ground-return sites preserved. Hub, paired authority and PCIe2
v103 remain unchanged. This is not signal routing or fabrication admission.

One bounded H integration continuation may now start from G's retained suite.
The separate fresh-footprint text-generation failure discovered in the wider
regression is documented above; H resumes native geometry and does not use
that failed fresh-materialization path. Do not describe all tests or all
pipeline paths as clean.

- Unit: `cec-atx-event-20260928-h.service`.
- Launch receipt: `build/event-driven-atx-20260928-h-launch/launch.json`.
- Suite: `build/event-driven-atx-20260928-h/suite.json`.
- Resource limits: 900-second board budget, 1,020-second service cap,
  16 GiB memory cap, 16 GiB free-space floor, eight-worker ceiling and
  bounded eight-trial/eight-pass command budget.
- Windows configuration:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-h\bridge-config.json`.
- Expected delivery state:
  `C:\Users\Admin\Documents\New project\event-driven-atx-20260928-h\delivery\state.json`.

Launch and armed receipts must follow; this section alone is not proof of
execution. No shared solver edits while H runs. A plateau must lead to
causal analysis, never an identical automatic retry. Keep the periodic
heartbeat PAUSED and do not resend any prior event.

### H launch and listener verified

- Actual invocation: `dd6ec85d3b16476997748768e38480a1`.
- Retained service independently verified `active/running`, main PID 2768757.
- Hidden Windows listener PID 30048, stderr empty.
- Exact-invocation delivery state **armed** at `2026-09-28T22:03:23.456Z`.
- Final resumed-path regression: 457 tests and two subtests passed in
  59.04 seconds. Fresh PCIe2 control remained unchanged at 0/0 and zero
  route-quality blockers. The separately documented fresh-generation test
  failure remains open and was not included in that resumed-path count.
- Approximately 57 GiB free before launch; G, Hub, PCIe2 and active pair
  hashes were rechecked. No other wave was running.
- The next task wake is H's terminal event, including a plateau/refusal
  exit. It is a custom local one-shot listener, not timer polling; the PC,
  WSL and desktop app must remain running. No reboot persistence is claimed.
- H has only launch/attachment evidence at this point. Inspect its actual
  admission and board before attributing any private-trial improvement to H.

### H completion verified

H finished in 117.298 seconds. Its one-shot terminal event was acknowledged
at `2026-09-28T22:04:37.653Z` for the exact invocation above; do not resend it.
No wave remained active at inspection. The periodic heartbeat remains paused.

The full pipeline accepted a constructor-only improvement: **371 to 366
opens**, unchanged five scorer-filtered structural findings, unchanged two
route-quality blockers, zero non-octilinear segments and no new topology-net
fault. All 97 protected copper items were retained. Source/engine identity,
current intake and paired-interface compilation passed. Placement geometry
passed, but force-rail craft admission still blocks signal routing. This is
not a routed or fabrication-ready board.

- Board: `build/event-driven-atx-20260928-h/atx-24pin-rev3/02-placement/board.kicad_pcb`.
- SHA256: `a953564dd236bde8b5b503aee7cf110abce0d07c5b362b342911716569a854f0`.
- Native read-only score: `build/event-driven-atx-20260928-h-native-score/control.json`.
- Verified dashboard: `http://localhost:8090/?id=pass-event-driven-atx-20260928-h-atx-24pin-rev3-6453391655`.
- Its exact render was visually inspected and served HTTP 200, `image/png`,
  66,177 bytes. The board's SHA and blocked status appear in the viewer.

The standby rail has input coverage 1/1 and its two-barrel transition. Two
other retained rails are preserved, not newly certified for complete input
current. The fourth rail still refuses its required six-barrel source field.

A read-only comparison of the legacy pad circles against native pad shapes
disproved the hypothesis that circles alone caused this refusal: the best
attempted field has three legal sites under either model. Retained foreign
power tracks block most other sites. No identical H replay is justified by
this result; a changed transition proposal must first demonstrate a safe,
natively admitted gain without moving protected copper or reducing ratings.

### H follow-up completed; no unproductive I wave

See `docs/joint-transition-field-search-2026-09-28.md` for the generic
footprint parser, full-width transition search, field-only repair dispatch,
landing-site prefilter, joint source/sink validation and bounded diagnostics.
Final regression: 496 passed, one skipped, two subtests; PCIe2 immutable
control unchanged at zero scored structural DRC/opens/route blockers.
The long legacy fresh-board test was interrupted and remains unverified.

The final eight-trial private replay generated 108 proposals and tested eight
(seven geometrically legal) but admitted no craft improvement. H was retained
byte-for-byte. It reached the actual sink-route obstruction; an admitted
source-field preview alone is not a completed rail. No I wave or replacement
listener was launched. H's listener delivered successfully and exited; the
periodic heartbeat remains paused. Resume only with a useful causal topology
repair, not an identical replay of this sampled failure.
