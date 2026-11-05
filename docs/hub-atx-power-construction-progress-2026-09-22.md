# Hub / ATX power-construction slice — 2026-09-22

## Scope and authority

This continues the current-beta, hash-pinned dead-bug pair in
`docs/hub-atx-active-placement-pair.json`. It does not replace that authority,
promote a fabrication candidate, change the approved two-capacitor reservoir,
relax a current/width/clearance rule, or waive physical qualification.

Neither board has yet been admitted to detailed signal routing. The useful
result is closure of several pipeline defects at the placement/power boundary,
not a completed board.

## Generic repairs

1. **One generated-power body-reservation policy.** `cec_power_body` supplies
   the mounting-face foreign-body reservations to exact planning, raster
   planning, final polygon clipping, and the placement checker. Previously the
   raster fallback could propose copper that the final body check rejected.
   Existing own-net/interface exemptions are unchanged; this is not a blanket
   ban on inner-layer copper beneath surface components.

2. **Exact package-local copper handoff.** `cec_power_local_replay` captures
   only the generator's reported item identities. Integer-nanometre geometry,
   net names, locks and fabrication groups travel with a terminal fingerprint.
   A later frozen-power stage reuses that copper rather than attempting a
   different local route around new reservations. Stale terminals, changed
   identities, duplicate geometry and lost ownership refuse. Native DRC,
   current-domain and width admission remain separate mandatory checks.

3. **Fill-seam consolidation across all owned producer types.** The existing
   same-net/same-fill union-preserving repair recognized ordinary pours but
   excluded `pourfirst:` parents. Their thin orthofill patches remained separate
   zones and produced two native copper-sliver findings. Consolidation now uses
   the materializer's shared generated-zone vocabulary. It preserves the exact
   intended outline union, holes, priorities relative to foreign copper, and
   fill settings. Its evidence includes patch bounds, net and layer.

4. **Bounded width-preserving rail detours.** `cec_rail_detour` searches actual
   XY clearance space before a rail gives up on a layer. It retains every
   endpoint, transition and intermediate branch, full width, and declared
   layer. Native edges, holes, rule areas and existing copper are obstacles;
   a blocked fixed transition still refuses. Search has a configurable per-rail
   budget. The widening compiler consumes accepted source/sink segments rather
   than reverting to the obstructed ideal spine. Synthetic fixtures cover
   translated geometry, branch preservation, blocked junctions and timeout;
   a native constructor integration test verifies a foreign-barrel detour.

5. **Coordinator state invalidation on replacement.** Replacement evaluation
   cleared derived power bindings in candidate copies but left the coordinator
   pointing to the previous attempt. Final craft therefore re-reported an old
   body/pour collision. Replacement now retires those four derived bindings
   for every downstream consumer while retaining electrical policy, immutable
   copper-prefix checks and all source files. The retired binding is recorded.

6. **Schedule measured ground-return failures after power construction.** The
   post-power repair dispatcher recognized body conflicts only. It now also
   dispatches native structured exhausted ground-return searches to the existing
   generic placement repair. Prose-only or successful searches cannot trigger
   it. The existing bounded pass count, monotonic admission and no-op stop stay
   in force; this does not defer an already failed constructor to routing.

7. **Admit the composed placement/power transaction.** The v7 test exposed
   a remaining feedback defect: repair improved the placement against the old
   power state, then regeneration introduced more failed return cells. A new
   outer transaction snapshots the complete PCB/sidecar family and configuration.
   It accepts only measured hard-craft progress with valid physical checks,
   exact power admission, and retention of the previously protected domains.
   Regression, no progress, or an exception restores the entire previous
   state and stops that branch. This fixes an actual stage-composition issue;
   it is not a coordinate repair or permission to reroute an accepted trunk.

## Measured results

### Hub

The exact power diagnostic constructs six of eight coarse current paths. For
those six protected source/sink domains, exact native fill now has **zero opens
and zero structural DRC findings**. Before these changes, the same placement
left a protected source pin disconnected; the first repaired replay then
exposed two copper slivers, subsequently cleared by union-preserving seam
consolidation. These results are domain proofs, not all-terminal net completion.

The v6 full pass confirms the repaired behavior through the production boundary:
body/pour clearance passes, exact power admission passes, and the state path is
the current attempt's sibling file rather than the previous attempt. Its
placement stage finished in 104.5 seconds. The isolated power replay was about
18.2 seconds; that is not a whole-pipeline performance benchmark.

Two coarse paths remain absent: `VCC_P2` and `PSU_5V_KVM`. The v6 candidate had
four blocking local decoupler-return searches: C28/U7.2, C26/U11.1, C27/U7.7
and C15/U7.1.
The intermediate exact power board has 267 remaining connections across all
nets; it is not a finished signal-routing result.

The v7 post-power-dispatch experiment first reduced return failures from four
to three, but a later composed replan increased them to five. It is retained
as a rejected diagnostic, not a promoted result.

The v8 real-pipeline verification completed its placement stage in 402.2 seconds.
The first composed repair reduced failed return searches **4 -> 3**, retaining
all six protected power domains and passing exact power admission. The next
proposal produced five failures and failed exact power admission; the joint
guard rejected it, restored the earlier PCB/sidecars/configuration, and stopped
after two passes with `joint_regression_rejected`. This is the desired bounded
behavior, not permission to continue an unproductive wave loop.

The retained 84.49 x 72.2 mm v8 candidate has valid pad bounds, zero native
courtyard conflicts, passing body/pour clearance and passing exact power
authority. Its three remaining local return blockers are C26/U11.1, C27/U7.7
and C28/U7.2. Detailed signal routing is still refused. Evidence is under
`build/hub-atx-power-routing-20260922-v8/hub-standard-rev2`; the placement report
records both the accepted and rejected joint admission keys and reasons.
A separate fresh-process read-only placement recheck of the restored PCB
confirmed the same three blockers, valid pad bounds, clear courtyards and clear
body/pour checks (`build/hub-atx-power-routing-20260922-v8/restored-physical-recheck.json`).
Its PCB hash remained identical to the published preview after the recheck.

### ATX

The rebuilt 82 × 95 mm seed constructs **two of four** force rails, versus one
on the earlier 78 × 95 mm compact candidate. This is a tradeoff, **not** a
monotonic replacement of the compact incumbent. The 78 mm candidate is retained
unchanged. An additive replay on that compact candidate preserved all existing
copper and added no new rails; it did not silently reroute the accepted trunk.

The 82 mm trial has zero native courtyard conflicts, but source-transition and
sink-transition conflicts remain (RS1 and RS4). It also retains local return and
decoupler-proximity findings. A request to reconstruct the older partially
routed candidate refused with 38 unpreserved copper items; no ownership gate
was bypassed. The clean retry used the exact current stack placement seed.

The v6 ATX placement stage finished blocked after 356.1 seconds. No detailed
signal-router wave was launched for this unadmitted placement.

## Mechanical and regression evidence

The v6 trial pair was checked together, then the final v8 Hub was checked against
the retained **78 mm compact ATX**: all 18 contacts register with matching roles,
and the declared opposing-body, vent, hardware and vertical screens pass.
Both board files and the active-pair manifest stayed unchanged by these checks.
The final receipt is
`build/hub-atx-power-routing-20260922-v8/compact-pair-validation/paired-progress-validation.json`.
This does not replace supplier tolerance, incoming-sample, cable/latch sweep,
thermal, hold-up bench, or fabrication qualification.

The PCIe two-port control remains byte-identical at SHA256
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
The final post-transaction replay (`pcie2-joint-regression.json`) has 0 DRC,
0 opens, 0 fabrication blockers and 0 route-craft issues.
The stronger release replay still reports the existing Kelvin-departure and
CAN return-plane-coverage findings. The product-neutral core static gate passes;
the legacy full-runtime generic audit still fails. Neither is represented as a
blanket release/generic-pipeline pass.

Broad and focused test receipts, exact rejected/admitted diagnostics and final
control replay are retained under `build/hub-atx-power-routing-20260922-v5`.
The final combined suite passed **430 tests**, with **3 skipped** and
**3 subtests passed**, in 193.24 seconds. Scoped `git diff --check` is clean.
After adding the joint transaction, its pipeline/replay/seam suite passed
**125 tests**, including eight joint-progress/rollback fixtures, in 123.10 seconds.
Test suites overlap and their counts must not be added. Existing unrelated
working-tree changes were retained; this slice was not committed or pushed.

## Immutable placement previews

These are hash-verified, no-component-body **placement / blocked / not fab
signoff** previews. No older successful board was substituted. Windows HTTP
checks returned 200 for both top and bottom images of each v6 preview and the
final v8 Hub. The live dashboard health check identifies v8 as its latest entry.

- [Hub v8, retained joint-progress candidate](http://localhost:8090/?id=pass-hub-atx-power-routing-20260922-v8-hub-standard-rev2-d4d48abd27)
  SHA256 `cbfe6b6f1e105a001356bad4c5e730d527264ed26618965cfd4a5f55380cd1b7`.
- [ATX 82 mm diagnostic v6](http://localhost:8090/?id=pass-hub-atx-power-routing-20260922-v6-atx-24pin-rev3-fafd4055f4)
  SHA256 `7542b126037dcabd70e4430bfcfc6d2836c0e5adc21dfca13f35ad16ae2028ae`.

The next physical-design work is joint placement/transition-seat solving for
the still-blocked return cells and rail terminals, followed by exact power and
priority-route admission. It must not shrink the current budgets, move an
accepted trunk, grow the compact board by default, or rename an unadmitted
placement as a routed/fabrication candidate.
