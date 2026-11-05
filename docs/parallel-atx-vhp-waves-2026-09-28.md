# User-requested parallel ATX and 12VHPWR waves

## Peer map and completed campaign: consult before any continuation

Both actual search peers below are now complete; no new campaign is running.
ATX I completed an unchanged, read-only admission audit. The corrected ATX
search was **J**, unit `cec-atx-parallel-20260928-j.service`, invocation
`cc074fd2e1bc4ed8912ac72d3f40f673`, output
`build/atx-vhp-parallel-20260928-atx-j/suite.json`.
Its peer is `cec-vhp-parallel-20260928-a.service`, invocation
`72b483b4add04ed68ca015c87c752fa0`, output
`build/atx-vhp-parallel-20260928-vhp/suite.json`.
The already-armed VHP callback mentions I; that peer reference is superseded
by J here. Both exact-invocation callbacks were delivered once. Do not resend
them or restart the same plateau. See the completion review below.

## Scope and verified inputs

After the H follow-up stopped without an admitted gain, the user explicitly
requested simultaneous waves for the 24-pin ATX and 12VHPWR boards. This is a
new bounded two-board search, not a claim that either board is route-ready.
No new agent/task, paid model service, or periodic timer is created.

Read `docs/joint-transition-field-search-2026-09-28.md` for the ATX blocker
and `docs/recovery-finalization-and-return-hole-snapshots-2026-09-20.md` for
the reviewed 12VHPWR lineage. Do not substitute canonical staging PCBs or old
boards discovered by modification time.

| Board | Explicit input | SHA256 |
| --- | --- | --- |
| ATX | `build/event-driven-atx-20260928-fullwidth-transition-probe-v3/board.kicad_pcb` | `a953564dd236bde8b5b503aee7cf110abce0d07c5b362b342911716569a854f0` |
| 12VHPWR | `build/verified-edge-continuation-20260920/12vhpwr-standard/02-placement/board.kicad_pcb` | `e9fd08b171747ac1eb3b6cb567036b4047218f29935410d876eedba465872323` |

ATX's private output is byte-identical to accepted H. Its separately stored,
byte-bound craft-search history contains eight visited poses. That history
provides ordering only, never cached admission. This pass expands the bounded
batch from eight to 24 trials and reuses that history to seek new candidates.
It is not a repeat of the same eight-trial private run, nor evidence that a
new native improvement already exists.

12VHPWR's prior full pass was September 20. The explicit lineage journal and
its preceding edge-repair proof select the same board hash. A bounded suite
journal inventory found no later 12VHPWR suite continuation. Its entire prior
source signature still matches current files, including the hierarchical
BETA schematics. The shared solver has since changed. Its stale placement
history is rejected, not relabeled as valid. The known starting blockers are
USB priority routing and a deferred local interconnect; the last recorded
open count is 220, not a current post-run result.

Fresh preflight receipts for both:
`build/atx-vhp-parallel-preflight-20260928/<board>/preflight.json`.
Both pass manifest/current-source intake, project-rule/electrical checks and
the mechanical dispatch gate. All input bytes and prior source signatures
remain unchanged. ATX's paired row compiles; 12VHPWR has no declared paired row.
These receipts do not waive placement, rail, pair, native DRC or release gates.

## Resource and execution policy

The live host exposes 32 CPU threads, 27 GiB WSL RAM and approximately 57 GiB
free repository storage. Two independent retained systemd service jobs run
concurrently, each with:

- Six worker ceiling; nested BLAS/OpenMP capped by the existing suite runner.
- 10 GiB memory cap, keeping combined caps below WSL RAM.
- 1,800-second board budget; 1,920-second hard service cap.
- 24 craft trials per batch, two rounds, one epoch; 16 routing passes.
- 600-second critical-placement recovery allowance, still bounded by the
  board deadline and finalization reserves.
- 16 GiB minimum free-space floor; isolated output directories, no automatic
  PCB/source promotion and no fabricated signoff.

Launches:

- ATX unit: `cec-atx-parallel-20260928-i.service`.
  Output: `build/atx-vhp-parallel-20260928-atx/suite.json`.
  Receipt: `build/atx-vhp-parallel-20260928-atx-launch/launch.json`.
- 12VHPWR unit: `cec-vhp-parallel-20260928-a.service`.
  Output: `build/atx-vhp-parallel-20260928-vhp/suite.json`.
  Receipt: `build/atx-vhp-parallel-20260928-vhp-launch/launch.json`.

Do not edit shared scripts, libraries, source boards, paired authority or
electrical budgets while either job runs. Review the finished peer read-only
if its event arrives first; shared repairs wait until both have stopped.
Preserve H, the immutable PCIe2 v103 control and the Hub incumbent.

## Completion and plateau wakeups

The existing local one-shot systemd event bridge attaches separately to each
exact invocation and sends to this same authorized task. It has been verified
against the installed app adapter with a read-only probe. This is the existing
custom local event integration, not a built-in desktop app-event trigger.
The five-minute heartbeat remains paused. PC, WSL and app must remain running;
no reboot persistence is claimed.

Windows evidence/config directories:

- `C:\Users\Admin\Documents\New project\atx-vhp-parallel-20260928-atx`.
- `C:\Users\Admin\Documents\New project\atx-vhp-parallel-20260928-vhp`.

On completion, inspect actual source/engine stability, stage admission,
native counts, failed-net identities, search history and candidate acceptance.
Publish the exact completed-board dashboard images and verify their image
endpoints. A process-success event is not routing or fabrication approval.
Stop repeated plateaus; do not launch another identical campaign merely
because a callback fired. Never resend an uncertain prior delivery.

## Actual launch and corrected ATX continuation

Both initial retained service launches succeeded. ATX I invocation
`e5d98bde7ce84b05b5bc9e9ae287f43c` completed after 43.383 seconds; its exact
completion callback was acknowledged at `2026-09-28T23:57:10.048Z`.
12VHPWR A was independently running with PID 2825928 and a 10 GiB memory cap;
its listener recorded `armed` at `2026-09-28T23:57:09.982Z`.

I exposed a launch-preflight omission, not a new geometry plateau. The private
ATX diagnostic copy had the right bytes and search history but no adjacent
placement-stage provenance. The canonical safety rule therefore treated its
tracks as an arbitrary routed input and reported `routed_input_read_only`.
No craft trials ran. The initial current-source/mechanical preflight did not
test whether the intended resumed repair mode would actually be enabled.

I's saved PCB is byte-identical to H, and its real completed placement journal
now verifies that exact artifact. J uses the normal `--continue-suite`
contract from I, without `--replace-placement`, new certificates, edited
source boards, or weakened gates. Its new preflight additionally requires
placement-resume provenance and confirms the same eight matched prior poses.
Receipt: `build/atx-vhp-parallel-preflight-20260928/atx-continuation-j/preflight.json`.
The corrected preflight helper lives under `tmp/`; no shared solver changed
while VHP was running. I's source, engine and output identities all remained
unchanged. Its force-rail craft gate remains blocked, not waived.

J launch receipt:
`build/atx-vhp-parallel-20260928-atx-j-launch/launch.json`.
It retains the same six-worker, 10 GiB, 1,800-second job/1,920-second service
bounds and expanded 24-trial batches. Its Windows listener evidence is under
`C:\Users\Admin\Documents\New project\atx-vhp-parallel-20260928-atx-j`.
The replaced I listener has already sent once and must not be restarted.

Validation in this turn: 71 suite/launcher/event/history tests passed, plus
two digest-bound placement-resumption tests (83 deselected). The recorded
launch correction is not a claimed PCB improvement. Confirm real search
dispatch and listener arming separately before reporting J as searching.

### Verified concurrent execution

At the next live check, J and VHP A both reported `active/running`, with main
PIDs 2831138 and 2825928 respectively and `MemoryMax=10737418240` each.
J passed current source intake, published its unadmitted seed checkpoint,
and actually dispatched craft round one: **108 generated, 24 selected**.
This confirms correction of the read-only launch, not an accepted gain.
VHP had entered its critical-only priority recovery, with worker evidence at
`build/atx-vhp-parallel-20260928-vhp/12vhpwr-standard/02-placement/priority-recovery-1ugobw33/worker.log`.

J listener Windows PID 9812 recorded `armed` at
`2026-09-29T00:03:54.605Z`, for its exact invocation. VHP's separate listener
remained armed for its original invocation. Neither listener had a stderr
failure. Leave shared pipeline code frozen until both stop; completion
callbacks, not periodic model polling, trigger the next review.

I's unchanged blocked preview was published as
`pass-atx-vhp-parallel-20260928-atx-atx-24pin-rev3-fc8dd6b746`.
Its exact dashboard `render` endpoint returned HTTP 200 with PNG content.
It is an unchanged audit image, not J's in-flight result or a routed candidate.

## Completion review and one bounded generic follow-up

J finished in **254.026 seconds**. It reused eight prior poses and attempted
**48 genuinely new poses**, 46 geometrically legal, with **zero accepted
improvements**. Its PCB is byte-identical to H. Fresh native score: **366
unconnected, five scored structural findings** (two items-not-allowed, two
track-dangling, one via-dangling). Three of four force-rail objects remain;
the missing complete rail still blocks placement admission.

12VHPWR A finished in **722.877 seconds**, also byte-identical to its reviewed
input. Fresh native score: **220 unconnected, zero scored structural findings**.
USB remains unqualified; critical-only fallback stopped on repeated
unadmitted pair geometry. Subsequent placement recovery refused to reconstruct
over **228 existing sense-trace items** across the twelve `/IN*_P/N` nets.
Its exact ownership certificate retains 278 of 506 total track/via items and
reports `routed_copper_requires_owned_transaction`. This is a real ownership
boundary, not permission to delete those traces. C7's local interconnect is
still explicitly deferred, not resolved by a clean physical placement gate.

Both journals verify current source intake, unchanged source inputs and an
unchanged engine throughout their runs. Both service success events mean the
coordinator completed, not that board admission passed. Native score receipts
are `native-score.json` under each suite directory.

Exact published views, both inspected with PNG endpoints returning HTTP 200:

- [ATX J unchanged/blocked](http://localhost:8090/?id=pass-atx-vhp-parallel-20260928-atx-j-atx-24pin-rev3-d252c96811)
- [12VHPWR A unchanged/blocked](http://localhost:8090/?id=pass-atx-vhp-parallel-20260928-vhp-12vhpwr-standard-b94dc2fc32)

After both peers stopped, the generic construction solver gained a bounded
two-step obstruction proposal. See
`docs/bounded-construction-sequences-2026-09-28.md` for implementation,
synthetic/native evidence, control limitations and the next causal work.
The private replay also retained the exact incumbent. There is no new routing
or fabrication claim, no queued identical wave, and no active completion
listener after these acknowledged one-shot deliveries. Periodic monitoring
remains paused.
