# Rail virtual-anchor repair and event-driven wave A review

## Completed wave A

The exact-invocation callback delivered once, with an acknowledged send at
`2026-09-28T18:47:21.415Z`. No timer was involved. The suite service completed;
the board process exited 2 for placement-admission refusal, not a crash.

- Elapsed board job: 1,170.189 seconds (19.5 minutes).
- Source and engine signatures stayed unchanged during the pass.
- Input SHA: `1b08b39ec4756879c7a25e7f56a1b6c42c7f8c329a316d6dc092bea5ab4b7eb3`.
- Output SHA: `c7ce02137aecaf7c937d3365638754d667d8dcd7741b842d49ddbf8354d09035`.
- Output: `build/event-driven-atx-20260928-a/atx-24pin-rev3/02-placement/board.kicad_pcb`.
- Two 128-trial rounds; one accepted topology-derived U4/C62 cell reorientation.
  Native placement geometry remains clear and the active decoupling violation
  is removed. This is a placement improvement, not power or signal closure.
- Force-rail construction remains 1/4, with three refusals. Routing admission
  remains false. The canonical private exact-power diagnostic also ran.

The model-free board preview was inspected. The new ID is present in the live
dashboard catalog, labeled **placement / BLOCKED / NOT FAB SIGNOFF**:

[Wave A placement](http://localhost:8090/?id=pass-event-driven-atx-20260928-a-atx-24pin-rev3-71dcf29038).

## Causal defect and reusable repair

The rail detour solver required every generated elbow to remain at its old
coordinate. One sink collector's virtual bend was itself inside forbidden
space. A path search between those fixed points therefore failed immediately,
even though the bend is not a physical terminal. Increasing search time did
not address this constraint error.

`cec_rail_detour` now optionally contracts virtual degree-two vertices only
when both incident edges have identical width and layer. It retains explicit
anchors, physical contacts, via-array sites, branch junctions, width changes,
layer transitions and cycles. The existing exact configuration-space search,
independent collision guard, deadline, width, layer and whole-plan refusal
remain unchanged. Other callers retain the old conservative behavior unless
they explicitly opt in and supply their physical anchors.

`cec_force_rails` supplies actual same-net pad locations and every declared
via-array center as anchors. Failed constructors now retain their detour
endpoint legality and available-versus-required via counts in the additive
`construction_evidence` field of the rail report. Previously these diagnostics
were only retained for successfully constructed rails, precisely hiding the
causes of the refused cases. Both materialization paths persist this evidence;
the existing string refusal and all admission checks remain intact.

No board names, reference selectors, coordinates or current reductions were
added to the neutral repair engine. No footprint, fixed mating seat, outline,
or preserved existing power copper was moved by the repair.

## Private native construction replay

Corrected before/after diagnostics are
`build/event-driven-atx-20260928-diagnostic-b/probe.json` and the `-c`/`-d`
siblings. They load the exact wave-A board, capture and preserve the existing
power prefix, and test construction in memory without saving or promoting a
candidate. The first `diagnostic-a` harness incorrectly read a verification
report as the prefix contract; it is **excluded** from the comparison. No
source board was modified by any diagnostic.

- Before: one existing rail preserved, three construction refusals.
- After: that rail remains preserved, one additional rail constructs, and two
  refusals remain. This is **1/4 to 2/4 at the constructor level only**.
- The newly constructed 3.3 V path retains its declared width and uses a
  fabrication-profile-declared routing layer. Physical terminals did not move.
- The result reproduces with the production two-second per-rail detour budget.
- Remaining causes include insufficient legal sites for the 12 V source via
  array and a standby transition point obstructed by a switch pad. Those are
  real physical-anchor constraints, not virtual bends to discard.

This does not certify current capacity, actual filled connectivity, all input
pin pickups, thermal behavior, DRC, routing readiness or fabrication release.
The older constructor can report partial pin pickup; only the downstream
exact-power and native board checks may admit the board. The next full pass
must check whether the construction gain survives those authorities.

## Validation and next pass

244 tests pass across detours, force rails, rail geometry, full orchestration,
power diagnostics, frozen-power rematerialization, prefix ownership, pouring,
policy sealing and locked residue. Synthetic tests cover translation, reversed
edge declaration, blocked fixed anchors, branches, width/layer transitions,
cycles and degenerate edges. A native mini-board fails with virtual-bend
relaxation disabled and constructs with it enabled, with identical pad poses.

Read-only replay of the immutable PCIe2 control remains 0 DRC, 0 opens,
0 blocking route-craft issues and 0 non-octilinear routes; its SHA is unchanged
at `2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
Evidence: `build/event-driven-atx-20260928-control/control.json`.
The generic-core audit passes; the full legacy runtime still has 378 findings.
No whole-pipeline generic-release or fab-release claim is made.

Wave B starts from the actual wave-A output, not an older canonical board.
It uses a short eight-trial/two-round full pass to exercise the new constructor
and exact admission before funding more broad placement search. Its service
and one-shot callback are recorded in `docs/atx-event-driven-waves-2026-09-28.md`.

## Full-pass B outcome: constructor gain was not retained

Wave B completed in 72.746 seconds with board exit 2. Its log confirms the
new constructor ran and produced 2/4 rails in the private craft baseline.
However, the resumed craft stage reused the incoming board's old
`carried_initial_evidence` after rematerializing that baseline. It generated
zero placement proposals and reported no accepted pose change. The final
board therefore retained the incoming bytes and the old 1/4 rail report.

This is **not an accepted board-level 2/4 improvement**. The output remains
`c7ce02137aecaf7c937d3365638754d667d8dcd7741b842d49ddbf8354d09035`, with the
same three force-rail refusals and no signal-routing admission. All source
and engine stability checks passed, and the existing prefix stayed intact.
The stale initial measurement is reused at the first-round baseline in
`cec_synth_pipeline.repair_placement_craft`; the next generic integration
repair must bind reused evidence to the actual rematerialized artifact and
explicitly evaluate reconstruction-only gains even when footprint poses do
not move. Such a gain still needs a guarded native transaction and must not
be committed merely because a constructor reports an extra rail.

This integration defect is distinct from the two remaining physical-anchor
failures found in the private replay. Do not spend another identical wave
expecting either issue to disappear. B's new dashboard record explicitly
reports `output_identical_to_input: true`:

[Wave B, unchanged retained placement](http://localhost:8090/?id=pass-event-driven-atx-20260928-b-atx-24pin-rev3-15cb390be6).

The request to launch B's hidden Windows callback helper was rejected by the
execution-policy layer before execution. No `delivery/claim.json` or
`delivery/state.json` was created for B. B finished while this task was still
active, so its result was reviewed directly here. Do not claim the B callback
is armed, delivered, or will continue unattended. No next wave is launched.
The old heartbeat remains paused; restoring a timer is not an authorized
substitute for the requested event-driven continuation.
