# Failed-construction feedback into bounded placement

## Verified starting point

G completed in 125.301 seconds and retained F byte-for-byte:
`9181a3a43781b69cf20e3688ba17e1f90b772b23f90f5455cb0b13d81d75a016`.
It had no accepted placement or reconstruction change: 371 opens, five
scorer-filtered structural findings, two route-quality blockers and two of
four constructed rail objects. This is not routing or fabrication admission.

The one-shot G callback was acknowledged at `2026-09-28T21:12:01.227Z` for
invocation `a5a563fe01d04f04a0646438d5a44fa7`. The periodic heartbeat remains
paused. The exact G render was inspected and its HTTP endpoint returned 200,
`image/png`, 66,253 bytes. Its dashboard ID is
`pass-event-driven-atx-20260928-g-atx-24pin-rev3-c517236475`.

The identical top-level suite `engine_sha256` was investigated. That field
hashes only the suite coordinator. The actual per-board engine signature
hashes all script modules and differed between F and G:

- F: `5d6d790aa70b5122bcaa82c3ee59af8b117fdf957e3855e3519de743f2883734`
- G: `81244bb37047a91bb6ca53e8a8216f3c70219869052a8f7e3c2a9350ceb4b89b`

G's log confirms a fresh materialization and fresh craft evidence. No stale
code/cache explanation was established; do not present that suspicion as fact.

## Causal missing connection

The rail constructor returned human-readable pad/copper refusals. Placement
dispatched `force_rail_placement`, but its move generator only understood
actual copper-territory violations. An unbuilt conductor has no such copper.
In addition, the craft adapter discarded structured construction evidence.
G consequently generated zero placement proposals in 0.006 seconds. More
identical waves or larger routing budgets could not repair that missing link.

The generic repair consists of:

1. Bounded, structured native-pad obstruction witnesses for attempted primary
   rail segments: obstacle identity, actual layer, endpoints, width and
   clearance. Rejected internal search alternatives create no obligations.
2. Forwarding those construction witnesses through craft evidence.
3. `cec_construction_feedback.placement_regions`, which converts only explicit
   failed pad collisions into temporary proposal regions for the existing
   bounded seat solver. It never parses refusal prose or grants admission.
4. Existing fixed/rigid-group, bypass-group, outline, native placement,
   protected-copper and composed reconstruction checks remain mandatory.

No board key, component reference, coordinate exception, new current budget,
width reduction, dimension increase or mating change was added to this path.
The new module is included in the audited generic core. Legacy runtime debt
remains explicit; this does not claim that the entire older pipeline is free
of board-specific rules.

## First private replay: actionable but correctly rejected

`build/event-driven-atx-20260928-construction-feedback-probe` generated 108
proposals, selected eight, and found eight placement/craft improvements. The
constructor identified SW2 as movable and RS2 as protected, from measured
evidence rather than any newly hard-coded reference. The selected automatic
move constructed a third rail object. Its input pickup remained absent.

The final composed native check rejected that candidate: opens fell from 371
to 367, but structural findings increased from five to six. It restored the
entire incumbent artifact family byte-for-byte. No rejected trial was promoted.
The diagnostic took 107.439 seconds; its source remained unchanged.

An exact replay of the automatically selected poses is retained separately in
`build/event-driven-atx-20260928-construction-feedback-rejected`. Native DRC
identifies a new zero-length +5VSB track at the collapsed collector. This is
distinct from the previously rejected cross-layer-alias short. Both are real
producer defects caught by the unchanged final admission guard.

## Native geometry follow-up

The force-rail pad collider used a circle with radius equal to half the pad's
maximum dimension. This overblocks elongated pads sideways, yet underblocks
rectangular corners. It also inferred SMD layer presence from the relative
route tag. The shared detour model redundantly added the same circle on top
of its already conservative pad bounding boxes.

`cec_native_pad_obstacles.Index` now snapshots KiCad's native per-layer pad
shapes, respects local/netclass clearance and NPTH holes, and fails closed on
unavailable geometry. The constructor uses this for track/pad collision. The
redundant detour circles are removed; the shared obstacle model, complete
native DRC and final artifact admission remain in place. The separate legacy
via-array candidate screen is still conservative and is not claimed fixed by
this track/pad change.

Collapsed primary conductor segments are not emitted as native tracks.
Coordinates and widths are consistently rounded to native integer units.
This does not authorize removing a nonzero primary path, omitting required
vias, or treating a missing input pickup as a complete power path.

Synthetic tests cover translated/rotated/renamed geometry, retained widths,
fixed placement, coupled bypass movement, unsupported witnesses, rectangular
corners, elongated-pad channels, actual-layer presence, plated barrels, local
clearance, NPTH drills and collapsed primary-segment emission.

## Layer-local pickup feasibility

Private v2 again refused a 367-open candidate with one added dangling track.
Removing the zero-length duplicate did not establish the missing input: the
nonzero source collector was still open. This was not counted as progress.

The collector span was computed from input-access failures on the initial
layer, then reused for other-layer fallbacks. A contact blocked by existing
copper on one layer was excluded even when its alternate layer was clear.
The detailed retargeter could not undo that loss using its wider fallback
width. The existing short-neck pickup grammar was never tried on that layer.

Each source layer now evaluates its own pickup feasibility and full-width
collector span. No new pickup width or current budget was introduced: this
uses the existing 1.4 mm direct / up-to-1.0 mm dogleg grammar, whose actual
current/thermal qualification is still required. Tests verify the original
layer's collapsed span does not contaminate a face-layer collector connecting
both real contacts. Per-layer spans are logged in construction evidence.

## Retain the proposal; do not rerun the search at commit

Private v3 produced a 3/4-rail reconstruction with the standby input connected
1/1, without moving any footprints. But commit invoked the time-bounded
constructor again and got a 2/4-rail result. The unchanged guard rejected it
for no Pareto craft improvement. The exact successful proposal had already
been deleted with its temporary directory. This is a handoff defect, not
proof that the first result was safe or manufacturing-qualified.

`cec_materialized_candidate` preserves the exact constructor-only proposal in
a quota-bounded in-memory bundle (16 MiB maximum). It binds source/policy/
environment identity, all script hashes, component positions/faces and every
captured artifact byte. Stale source, policy, pose, engine or bundle content
refuses before writes. Only the known placement/power sibling family may be
replayed; uncaptured external skeletons cannot be silently imported.

The final coordinator stages those bytes inside its existing rollback
transaction and reruns native DRC, actual craft, source intake, locked-prefix,
fixed-domain, frozen-authority, foreign-pour and route-quality checks. It does
not reuse any acceptance certificate. Renamed report basenames and skeleton
pointers use the existing sidecar-copy adapter. Placement-move proposals retain
their existing certification path; this slice specifically fixes the newly
observed constructor-only handoff.

Unit tests delete the temporary proposal before replay, reject changed inputs
and corrupted/oversized/escaping bundles, and prove that a replayed candidate
still rolls back on native regression. The feedback/native-pad/layer-local
regression passed 542 tests and two subtests before this handoff addition.

## Actual-contact graph normalization

The exact retained v4 proposal reduced opens to 366, but fresh native checks
found two new dangling tracks and a new `/SENSE5VSB_LO` route-topology fault.
It was rejected, restoring G. A diagnostic reproduction retained the native
artifact and DRC in
`build/event-driven-atx-20260928-construction-forensic-v4/exact-proposal`.

The source dogleg joined the collector 2.1 mm away from the pin's original
column, leaving an obsolete collector tail. Relocating the sink transition
left a 1.767767 mm out-and-back branch at the old virtual junction; repeated
declarations also duplicated several sink runs. Neither is a real terminal.

`cec_conductor_proposal.normalize_terminal_paths` normalizes only a single-net
uncommitted proposal after actual pickups and transitions are known. It splits
at real same-layer junctions, merges coincident coverage at its widest existing
width and removes unanchored degree-one branches only from sufficiently
anchored components. Native pads/existing copper, explicit required array
sites and actual cross-layer transitions remain protected. Under-anchored
paths and cycles are retained, not erased to disguise missing connectivity.
Layer aliases are resolved by the caller. Existing protected native tracks,
vias, footprints and current budgets are never edited by this helper.

Synthetic tests cover rotation, translation, reversed declaration order,
overlapping widths, real branch crossings versus other-layer crossings,
layer aliases, required transitions/arrays, incomplete graphs and bounds.
A native KiCad fixture independently verifies removal of a dangling tail
without losing either physical contact. The helper is registered in the
audited generic core.

## Accepted private integration trial

`build/event-driven-atx-20260928-construction-feedback-probe-v5` completed in
45.249 seconds and passed the unchanged composed native admission. Its board
hash is `22d821b5829e037e32fbe37507cdf8fb21c536d53e7fde142bb3c890725f64bb`.
It has 366 opens versus G's 371, unchanged five scored structural findings,
no new route-topology fault and three of four constructed rail objects. The
standby input is actually picked up 1/1. The source/craft/fixed-domain checks
passed and all 97 prior protected copper items were retained. This was a
constructor-only improvement: no footprint poses or board dimensions moved.

Fresh return-access comparison retained all 38 previously accepted sites;
ten pre-existing return-site refusals remain. There are no declared
foreign-pour parts/tracks/vias before or after. Those facts do not imply
complete decoupling/grounding, thermal qualification or fabrication approval.
The fourth rail still refuses its required six-via source field and alternate
paths. Preserved partial rails still need complete input-current coverage.

## Validation and continuation limits

The feedback-only regression passed 415 tests and two subtests. Before graph
normalization, the combined regression passed 555 tests and two subtests.
Graph/force/detour/parallel coverage initially passed 69 tests and two subtests;
the later native graph fixture and generalization tests passed 24 tests.

A broader 459-test selection exposed a separate fresh-generation failure:
`tests/test_rail_walk_floor.py::TestEndToEndPitch::test_seg4_seed_pitches_and_refusal_classes`.
It fails in `gen-module-pcb.py:place`, before force-rail construction, because
the line-greedy metadata-removal regex erases the top-level layer when a valid
footprint places `(version ...) (generator ...) (layer ...)` on one line.
The current slim M2 hardware footprint uses that format. This is a recorded
open fresh-materialization defect, not a waived test or evidence that the
whole pipeline is clean. The resumed native-board path used by G and the
accepted private replay does not use that footprint-text generator. An
initial native test-fixture binding error was separately fixed and rerun.

The final resumed-path selection (graph, force rails, rail geometry, native
pad obstacles, construction feedback, return proposals, stage admission,
parallel copper, suite admission, detours, generalization, transition search,
placement reconstruction, exact materialized candidates, craft admission and
transition landings) passed 457 tests and two subtests in 59.04 seconds. It
does not include the separate fresh-generation rail-walk test above. The
changed-file whitespace check passed.

Fresh PCIe2 replay after graph normalization remains 0 structural DRC,
0 opens, 0 route-quality blockers and 0 non-octilinear findings, byte-identical
to its archived source. The generalization gate reports `generic_core_ok=true`
and 378 unchanged legacy runtime findings, not zero legacy debt. Evidence:
`build/event-driven-atx-20260928-conductor-proposal-control/control.json`.

The PCIe2 v103 control remains the immutable comparison board:
`2f09d2765bacc5281a52fc7b6afaafa06078fb3aa1c1c2be037b708edd059388`.
Hub incumbent `166b9b63d88fb7b06e6710d76f08157d3412e7bea8139992fd60d9d9a1277a87`
and active pair `dfbeccb8eca4331c53c92c95b77d82dea03d4d8f396effda2860ca1d99882463`
were rechecked unchanged. The ATX outline remains 78 x 95 mm.

Only a private candidate with actual native/craft non-regression justifies a
new bounded wave. Do not repeat an unchanged plateau, hand-move a named part,
waive dangling tracks, or claim constructed rail-object counts as input/current
qualification. Source escape, complete input coverage and required via-field
landing still need independent evidence.

## Subsequent H review and bounded repair

H accepted the 366-open improvement. The subsequent parser/transition/field
repairs and their final 496-test regression are recorded in
`docs/joint-transition-field-search-2026-09-28.md`. The parser exception above
is fixed in focused/native fixtures; its expensive legacy fresh-board
end-to-end test was interrupted and remains unverified. The last private
repair tried eight generic placement candidates without an admitted gain;
H remains the incumbent and no identical next wave was launched.
