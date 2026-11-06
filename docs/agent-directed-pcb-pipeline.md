# Frontier-directed PCB workbench

The canonical layout workflow is `python3 scripts/cec_agentic_workbench.py`
(or `PYTHONPATH=src python3 -m cec_pipeline`). The frontier model authors the
layout; the software constructs and independently receives that decision.
It does not invoke a model API, incur background model billing, or run an
unbounded placement/routing search.

The native backend requires KiCad 10's Python interpreter with `pcbnew`,
`wx`, NumPy, SciPy and Shapely; tests additionally require pytest in that same
interpreter. On the Debian/Ubuntu KiCad environment these are the
`python3-numpy`, `python3-scipy`, `python3-shapely` and `python3-pytest` packages. Do not copy
compiled geometry wheels from a different host Python into its path. The
dedicated CI installs these inside its disposable KiCad container so fresh
receiver/pytest subprocesses see the same dependencies as the parent.
Node.js also executes the inspector's small UI contract tests; it is not a
layout worker or background model runtime.

## Responsibilities

| Layer | Home | Responsibility |
| --- | --- | --- |
| Author and review | Frontier model / direct tools or MCP | Choose functional cells, topology, symmetry, corridors, geometry and next action |
| Control plane | `src/cec_pipeline/` | Exact intake, private jobs, bounded execution, durable campaign, selection |
| Construction | `geometry.py`, `cells.py`, `power.py`, `construction.py` | Compile explicit native geometry; no hidden search or electrical authority |
| Independent receiving | `receivers.py`, `safety.py`, retained `scripts/cec_*.py` | Rederive cuts, ownership, current requirements, native material and physical evidence |
| Review publication | `ops/cec_publish_agentic_review.py`, `scripts/cec_suite_inspection.py` | New hash-bound suite receipts and trackpad-friendly native inspection |
| Historical experiments | `experiments/legacy_2026/` | Preserved dated helpers with origins; not the active API |
| Runtime | User-selected workspace / ignored `.cec/` | Jobs, SQLite journal, logs, caches and plots, never authoritative source |

The retained validators are compatibility backends, not parallel competing
orchestrators. Their historical source interfaces remain stable for existing
tests. New orchestration belongs in the package, not another dated root script.

The legacy self-hosted Route/Synthesize jobs, overnight wrappers, local wave
manager and wave wakeup bridge are removed. `cec-compute` is no longer in
the project MCP configuration. Retained library modules refuse their former
standalone autonomous CLI launches; import compatibility does not authorize
running an old wave. The complete retirement inventory is
`legacy-job-retirement-2026-11-05.json`. Model files and hardware libraries
are not deleted, and shared receivers/regression fixtures remain intact.

`ops/systemd/cec-inspection.service` is the supported local inspection
service. It serves the explicitly published snapshot on localhost:8091 with
`--inspection-only --no-watch`: no archive crawler, wave watcher or solver.
The former port-8090 dashboard service is disabled. Re-publication remains an
explicit, hash-bound operation, not a background scan of old candidates.
On Windows, the systemd unit alone does not keep WSL running, as documented by
[Microsoft](https://learn.microsoft.com/en-us/windows/wsl/systemd). The existing
`CEC-WSL-Keepalive` logon task must be running for idle browser availability;
its sleep process consumes no solver/model compute. Do not restart the old
dashboard bootstrap or a retired wave manager to keep the inspector alive.

## Tools

The direct and MCP surfaces share one dispatcher and exact operation schemas.

| Tools | Purpose |
| --- | --- |
| `boards`, `inspect`, `issues` | Exact nine-board intake, native UUID/pin/net/pose inventory, paged causal issue maps with a legend |
| `row`, `grid`, `plan_cell` | Compile model-selected alignment and centered grids; expose source-owned connection obligations before construction |
| `stage` | Author an atomic private transaction with an explicit rationale and exact source SHA |
| `check`, `validate`, `status` | One independent check or a finite background checklist, with concrete failure stacks |
| `render` | Actual saved native before/after copper, optional Fab/silk guides and bounded MCP PNG images |
| `verdict`, `select`, `fork` | Require evidence, record model visual review, then adopt the checked child as the campaign parent |
| `campaign` | Durable decisions and completion/failure events; failed identical decisions cannot loop |

There is no arbitrary shell/Python tool. `--schemas` exports the full vocabulary.
All geometry uses integer nanometres. Board-specific coordinates are work
orders, not implementation exceptions.

### Received refinement outcomes

Craft receiving compares individual physical findings, not their aggregate
count. Identity binds defect kind, net, copper face and exact native locus;
reconstructed UUIDs, explanatory prose and incident iteration order do not
change the identity. New locations/types and worse typed measurements refuse,
even if more defects disappeared elsewhere. Unlocated, unknown, partial,
inconsistent or non-finite observations refuse rather than becoming clean
evidence. Existing debt is explicit and is not qualified by nonregression.

Craft rows returned by `issues` expose `target_issue_id`. The optional
`stage.target_issue_ids` list names up to 32 exact-source targets that must
actually disappear. Improving a target without clearing it is not completion;
changing a claimed target cannot disguise an identical failed geometry retry.
This outcome contract does not imply that every possible electrical,
placement or thermal objective is covered.

Field receiving has its own semantic outcome contract. Exact conductor
geometry, effective per-conductor electrical roles and measured interactions
identify a blocker; UUIDs are lookup evidence, not its identity. Incomplete or
contradictory reports, policy changes, same-count defect substitution and
changed retained blockers refuse. `issues.target_field_issue_id` and
`stage.target_field_issue_ids` identify exact-source field blockers that must
disappear. Clearing one crossing cannot compensate for creating another.
The whole-board checker uses contiguous collinear copper runs rather than
serialization fragments, so subdividing a trace cannot hide its parallel
overlap. This is bounded geometric nonregression, not continuous-field or EMC
qualification.

Every actuator also receives `pair_integrity`. Scope is independently derived
from saved conductor, pad and filled-zone geometry; shared reference or
terminal changes conservatively recheck all complete declared pairs. An
ordinary-net-only change can prove that pair geometry is unchanged without
replaying irrelevant pair measurements. One aggregate killable 8-second lease
covers both boards and every scoped pair. Timeouts and unavailable evidence
refuse. Both measurements use the **source** policy path. The retained checker
has legacy defaults, which are disclosed assumptions, not new source-qualified
limits. Its saved-fill reference samples are not a continuous return-path or
electromagnetic proof; this is pair-semantic nonregression, not SI signoff.

Cell preview and construction expose explicit `reference_group_uuids` authority
for recognized source-owned readable reference maps. Cardinal motion transports
the complete source map, and saved receiving independently reconstructs its
expected AST. Unrelated locked groups remain exact. An exactly stationary
grouped contextual owner needs no moving authority; that does not authorize
moving or unlocking its group. This enables useful connected-cell decisions
without stripping reviewer annotations or bypassing copper ownership.

A source-assigned bypass may name its exactly stationary device as context,
even if that device has through-hole lands or locked/grouped geometry. Its
unique source owner/pin/net and literal unchanged pose are recompiled; only
the moving bypass enters the cut domain. This grants no device motion,
unlocking or arbitrary-context authority. A zero-cut move may retain every
original conductor without adding redundant copper, but every local supply,
immediate Ground return, current contract and surviving partition still has
to pass. Native connectivity through a remote plane is not a local bypass
path. A missing bounded explicit supply proof remains a refusal.

The saved receiver independently checks the native projected scope before
restoring literal unowned Source nodes into its expected reconstruction.
Writer reordering of an unrelated field is not a geometry mutation, but a
changed pad, lock, global, group or other unowned node still refuses. Only a
well-formed group's UUID quote spelling is normalized during cardinal writer
comparison; group membership and final saved Source AST remain exact.

Component values and full part names belong on Fab/BOM, not silkscreen.
The shared footprint emitter now keeps Value on the correct physical Fab
face, with its text, pose, visibility and lands intact. The inspector reports
actual visible Value/MPN field counts by layer and distinguishes optional Fab
guides from printed silk; references and functional markings are preserved.

## Received construction capabilities

* `replace_chain`: ordinary-signal shortening with source ports, launch
  tangents, width, face, native process and lock strength retained. Rejects
  exposed-material no-ops, foreign copper, edges and keepouts.
* `repair_chain`: one field-targeted ordinary-signal chain, with explicit
  geometry and a finite additional-length allowance (at most 16 mm).
  Source ports, width, process, locks and source launch/arrival tangents on
  the same face remain mandatory. Relayering requires two exact existing
  through-barrels and a source-declared signal face; no new hole or rated
  power, Ground, Kelvin or pair authority is inferred. Known manufacturing
  profiles are checked against the complete actual saved buildup before
  deriving their canonical layer roles, including compound `SIG/PWR` roles.
  Independent `route_contract` receiving checks the saved path and allowance
  in addition to ordinary native-delta receiving. The named field fault must
  clear without new craft or field debt. `replace_chain` remains shortening
  only; a repair does not silently weaken that actuator.
* `place_cell`: explicit cardinal poses for up to eight functional owners,
  plus model-authored restoration routes to retained barrels. Source-owned cuts and connection obligations
  are recompiled; saved receiving checks surviving partitions, decoupler
  ownership/returns, unchanged current, Kelvin, fields and declared assembly
  contracts. Pose-only disconnected moves cannot be selected.
* `power_contour`: real filled square or 45-degree-chamfered source-retaining
  contours, with source-derived current width, native material/neck, Kelvin
  and field receiving. Original rated conductors remain.
* `power_route`: bounded full-current planar shortening on the source width
  and face. Exact native ports, boundaries, partitions and current contract
  replay independently. It cannot claim new layer-sharing or barrel capacity.
  The explicit cut may be a connected tree rather than only a two-terminal
  chain; every branch contact must still survive saved native receiving.
  Omitting a short redundant tail must not leave a dangling remnant.
* `bank_collector`: literal same-net pad-bank collector with solid actual
  saved fill and deliberate chamfers. Original pads and support conductors
  remain. Its outline does not create a new current rating.
* `ground_plane_extension`: extend one exact existing Ground-zone outline,
  retaining its layers, settings, holes and all other native objects. Actual
  saved copper must retain every original filled component; added copper must
  join original saved Ground material and exactly match an independent native
  selected-zone refill from immutable Source. An area threshold cannot stand
  in for that proof: a substituted sub-feature-width neck is rejected.
  No arbitrary zone replacement, detached
  filler, additional via/layer sharing or current/thermal qualification is
  inferred. Full current, Kelvin, field, pair, assembly and native checks still
  apply. Use this to recover unused return-plane space, not to claim a smaller
  PCB outline.
* `outline_trim`: move one explicitly named outer edge inward, either on a
  four-segment rectangle or a bounded orthogonal perimeter whose selected
  straight edge joins two native quarter-circle corners. Rounded trims
  translate those corners without changing their radii and shorten the two
  neighboring straight sides; unrelated recesses and internal footprint
  cutouts remain literal. The other objects, hole/part positions, power copper and
  zone outlines/settings remain literal; only existing Ground fill may be
  clipped within the changed-edge strip and its source clearance setback.
  Saved receiving checks the exact three (rectangle) or five (rounded) updated edge primitives, conservative
  native material and valid closed occupied-face courtyard envelopes, no added Ground material and no remote
  Ground removal. Rounded clipping uses only the native removed laminate
  expanded by source copper clearance plus a received 10 um guard, with
  1 um offset chord error. Signed native rings verify cutouts without relying
  on KiCad's whole-poly self-intersection flag for valid hole sets. Source
  joints admit at most 2 nm adjacency, with no snapping. Native/physical
  checks remain mandatory: straight-edge envelopes alone cannot qualify a
  translated rounded corner. This bounded tier does not move mounting
  interfaces, alter cutouts, handle arbitrary curved outlines or establish
  washer, mating or thermal qualification.

The November 5 compaction/refinement pass exercises both new actors on actual
checkpoint boards and ordinary cleanup on four distinct main boards. See
`docs/evidence/20261105-compaction-refinement/` for quantitative results and
known fabrication/thermal debt. Review acceptance is not a release decision.

Kelvin preservation first attempts an exact non-interference proof for unrelated
track-only edits. Both fresh full-denominator manifests must agree on all
lineage, terminal and authority contracts; every other native object, hole,
via, fill, edge, setting and project companion must remain exact. A changed
force/sense net, unresolved lineage, or broader edit cannot use this proof.
It preserves existing evidence without replaying irrelevant clipped cuts;
it never establishes absolute Kelvin qualification. Relevant changes still
owe physical replay, and native DRC/current/fields/assembly checks remain
mandatory in either case.

Relevant Kelvin replay now uses the existing exact per-input/leg shards through
`kelvin.py`: two native workers total for the pair, each process capped at 9.7 s
with a 9.1 s internal budget, inside a finite 45 s checklist. Both sides require
a fresh full manifest, every physical leg, one legacy diagnostic and the
independent fresh-manifest coverage join. Missing, stale, timed-out or duplicate
constituents refuse; failed/unknown physical cuts remain visible. Source and
candidate family identities are checked across both replay and the later native
transform comparison. This removes the whole-board replay time bottleneck
without adding physical authority or raising any native constituent deadline.

The [simulation/refinement pass](simulation-refinement-pass-2026-11-05.md)
records current thermal and electrical model limits. Thermal solves now refuse
nonfinite or wrongly shaped temperature fields, exhausted nonlinear iteration
and the last-resort linear solve when its existing residual check fails. SPICE
preserves exact schematic net identities under simulator case folding and
requires every requested operating-point voltage/current to be finite and
consistent. These checks establish numerical integrity, not missing package,
contact, cooling, parasitic or operating-case physics.

Mixed-authority macros are separate transactions, not one opaque batch.
`add_connections` supplies model-authored ordinary-control/Ground tracks and
through-vias before connected pose reconstruction. It retains all source
conductors, checks actual per-island terminal rooting, source partitions,
Ground-return nonregression and native via process/clearance, then still owes
native DRC, current, Kelvin, fields and assembly checks. It does not add rated
power/pair routes, infer barrel capacity, or create a new process exception.
`place_cell.vias` is consequently empty; an unreceived barrel cannot hide in a
pose move. A single closed capability catalog owns mandatory gate sets and is
tested against the exposed construction schemas.
The old unreceived `align_group` and arbitrary `reshape_zone` mutation tools
are no longer exposed. Rows compile into connected-cell requests instead.

Explicit routes/vias can express interleaved and cross-layer designs only
within the source-owned receiving scope. Unqualified high-current transfers,
missing process exceptions, locked/grouped objects outside the explicit cut,
unsupported IC moves or an incomplete source contract **remain refusals**.
The interface does not magically make every possible PCB edit qualified.

## End-to-end operating contract

1. Read the pinned source, functional owners and requirements; inspect native
   geometry and layer plots. Equal-value parts are not automatically one cell.
2. State the root cause. Author exact poses/cuts/paths. Preview cell obligations
   before choosing restoration routes.
3. Stage a private child. No source PCB, rules, dimensions or budget is changed.
4. Validate the exact saved child. At most two receiver workers and two finite
   checklist coordinators run per workspace. Each native constituent retains
   its existing <=10-second lease; composed checklists have finite watchdogs.
5. Inspect the concrete refusal if a check fails or expires. Change the design
   or scope; prose-only changes cannot bypass failed-action memory. Changed
   receiving code/family/table permits explicit reevaluation, not a claim of
   geometric replanning. Three recent failures of the latest source of one
   board produce a replanning signal; interleaved boards and historical sources
   cannot manufacture or conceal it. This is not a no-path proof.
6. Inspect actual native before/after plots. Saved copper differences determine
   the required layers and regions, including changed Ground fill. `render`
   defaults to a useful changed-copper crop, not the drawing sheet; multiple
   views accumulate without overwriting other crops or layers. Selection and
   publication independently require every delta region to be covered, exact
   before/after SVG pairs, hashes and actual SVG viewports. A valid image of an
   unrelated corner cannot stand in for review. This establishes evidence
   relevance, never proof of model attention or electrical qualification.
7. Select the child, optionally `fork` it as the next working parent. A separate
   publisher makes a fresh suite review receipt; originals remain immutable.

The SQLite decision/event journal survives restart and verifies its hash chain.
Each workspace also durably binds the exact original receipt path and SHA.
Reopening it, including the finite validation worker and publisher, cannot
follow a changed Git/dashboard pin. Explicitly selecting another base requires
a new workspace; adopting a checked child still uses `fork`. Legacy unbound
workspaces with jobs require an explicit checkpoint/SHA whose base matches
every job; mixed or missing bases refuse before publication. Untouched suite
rows always come from this bound receipt, not whichever pin is current later.
Source observations alone may be reused, keyed to source/family/code/library/
native-tool identity. Raw report hashes are checked again. Changed candidates
never inherit native geometry checks. Code changes invalidate prior jobs.
Semantic source/BOM/library-body inputs, the selected physical peer and
hashed CEC/KiCad policy environment are bound too; changing one invalidates
the job rather than silently reusing its old authority.

Assembly nonregression compares typed native fault identities and signed
clearances/offsets, not only top-level failure categories. A new collision
cannot hide under an existing collision category; worsened known margins and
incomplete/opaque observations are refusals. Unchanged inherited assembly
faults remain debt, not approval. The no-declared-contract result remains
explicitly unqualified.

The visual material manifest presently covers native tracks, pads, vias and
saved zone fills. Copper artwork is protected from these actors by literal
transaction ownership, not independently reviewed by that manifest. Any future
artwork actuator must extend the observer before gaining selection authority.

## Running locally

Use a complete source checkout in WSL with KiCad 10.x, wx/pcbnew, and the
existing native reporting build. This is a source/editable-install workflow,
not a standalone wheel containing the CAD backend and hardware libraries.

```sh
python3 scripts/cec_agentic_workbench.py --workspace .cec/campaign --call boards
python3 scripts/cec_agentic_workbench.py --workspace .cec/campaign --call inspect \
  --json '{"board":"hub-standard-rev2","limit":8}'
python3 scripts/cec_agentic_workbench.py --workspace .cec/campaign --call stage \
  --json-file /absolute/path/to/reviewed-work-order.json
python3 scripts/cec_agentic_workbench.py --workspace .cec/campaign --call validate \
  --json '{"job":"<exact 24-character token>"}'
```

The default is `checkpoints/current.json`, not file age or an author's private
review directory. `--checkpoint` requires its exact `--checkpoint-sha256`.
The portable control retains all nine PCBs, actual footprint
libraries, fresh native reports and original provenance.

Omit `--call` for MCP stdio. The project `.mcp.json` includes `cec-layout`;
a client still needs to load/restart that project configuration in the WSL
environment. No user-wide client setting or authentication policy is changed.

`ops/cec_publish_agentic_review.py --workspace ... --job <selected-token>
--output <fresh-directory>` creates review-only lineage. Publishing the
inspection index is a deliberate separate operator action.
The publisher also accepts `--checkpoint` with `--checkpoint-sha256` for an
explicit matching legacy intake. These options cannot rebase an existing
bound campaign or waive any candidate/visual/physical check.

Read-only placement studies are separate from construction/admission:

```sh
PYTHONPATH=src:scripts python3 -m cec_pipeline.repack \
  --request docs/evidence/20261105-costed-repack/top-edge-request.json \
  --output /outside/repo/paired-preview.json --plot /outside/repo/paired-preview.png
PYTHONPATH=src:scripts python3 -m cec_pipeline.bridges \
  --request docs/evidence/20261105-busbar-pilot/atx-request.json \
  --output /outside/repo/bridge-preview.json --plot /outside/repo/bridge-preview.png
```

The frontier supplies each pose; neither tool searches placements or saves a
modified PCB. Paired repack checks the declared body/vent/mating envelopes and
evidence-defined connector exit mouths. Bridge trials bind actual saved copper,
lands, holes, component reservations and source conductor-current margins.
They report nominal mechanical rejection and base/netclass land-clearance
screens, not custom-rule DRC, complete connections or thermal qualification.
A hole is a conservative potential lead envelope, not a known solder/lead
height. The stack's overall gap cannot clear a local collision automatically.

A real metal bridge is a two-terminal assembly component, **not a PCB copper
zone or a net-tie fiction**. Adoption needs its real schematic/BOM, explicit
assembly-level conductor model, source-owned current paths, Kelvin isolation,
joint/thermal proof, toleranced fit and measured package benefit. Two separate
nets can have zero native opens while that assembly obligation remains missing.
The provisional footprint has only its two real solder lands; no copper span.

## Layout and qualification policy

Ordinary signals use purposeful 0/45/90 headings with 45-degree transitions,
not stair-step reversals or gratuitous hard 90s. Power uses compact cardinal
banks and deliberate chamfers; actual filled cross-sections and source
requirements outrank attractiveness. Centered via plans grant no ampacity.

Align repeated functional cells, not all capacitors of one value. Owner-pin
distance and immediate ground return outrank a cosmetic grid. Preserve
mating keys, courtyards, vents and dead-bug stack contracts.

Compact board area is an explicit frontier objective: usable space inside a
computer case is scarce. Prefer packing related functional cells into orderly
rows, bringing bypasses and returns toward their owners, consolidating shared
support stages and removing unnecessary perimeter routing before choosing a
smaller outline. Compare actual saved width, height and laminate area against
the parent; tighter-looking contents alone are not a board-size reduction.
Evaluate the complete mating assembly, including connector access, mounting
hardware and opposing bodies, before counting perimeter space as removable.
The current outline actor covers a conservative inward trim of one edge
of an existing rectangle or supported rounded orthogonal perimeter, with
internal cutouts preserved. Coordinated hole/interface moves and arbitrary
outlines still need tools receiving the complete changed mechanical and
electrical scope. This is a tooling gap, not a restriction on the user's
authorization to compact the boards. A plane fill following the
outline is not itself a compaction limit: distinguish repourable plane copper
from protected current paths and fixed physical constraints. Preserve loaded
current/thermal evidence and all existing
clearances: less cooling area cannot be assumed harmless. In particular, the
EPS daughterboard's failed nominal thermal screen requires return-loss and
installed-boundary review before compressing its power paths further.

High-speed/RF treatment is interface-specific: impedance, pair spacing/skew,
continuous return plane, transitions and ESD come first. Curves and ground
fences are not universal requirements and are never silently added from a
net-name guess.

Zero native opens/errors, nonregression or a selected review child is **not**
thermal/current/EMC, barrel, mating or fabrication approval. EPS's retained
field-policy debt remains visible. Fabrication finishing and manufacturing
release remain separate gated stages; no Gerbers or fab release are emitted
by the workbench.

## Verification

Flat reinforcement trials live in `cec_pipeline.flatbars`, separate from
raised bridges. A flat soldered bar has no assumed routing tunnel underneath
it. Its one continuous land is real PCB copper; its metal is never substituted
into saved PCB fills or credited as a native-net union. Manufacturer maximum
dimensions, provisional land/courtyard, explicit solder-height allocation and
both source-hashed board poses are checked together. Actual placed native pad
polygons must match the analyzed land. Temporary footprints exist only in
private in-memory boards, never in a promoted review source. Reports check
native land/drill/rule-area conflicts and the paired stack, but retain unknown
ampacity, assembly process and routed-board status.

Example: `python3 -m cec_pipeline.flatbars --request
docs/evidence/20261105-busbar-candidates/atx-3v3-flat-request.json --output
/outside/repo/flatbar-report.json`. The current mechanically fitting trial is
**electrically obstructed**, not admitted. Its result must not be summarized
as a ready board or used to retire the original power conductor. The paired
read-only preview supports 32 explicitly posed owners per board; the connected
placement actor still permits only eight. That difference grants no THT
transport authority.

`cec_pipeline.conductors.solve` is a separate, bounded lumped DC/steady-state
electrothermal kernel for explicitly declared bar, joint and PCB branches.
It calculates unequal sharing, temperature-dependent resistance, Joule heat
and heat rejection, checking electrical and thermal conservation. Distributed
solder contacts require multiple actual contact branches; two terminal joints
cannot stand in for an arbitrary continuous solder seam. No default material,
joint, convection, cooling or ambient parameters are supplied. Floating nodes,
unphysical values, resistance extrapolation and nonconvergence fail closed.
Its analytic regression fixtures are **not** board simulation results. This
kernel is not wired into admission: parameter evidence, native contact binding,
full assembly Kelvin/bypass checking and independent current receiving remain
required before it can justify replacing native copper.

The active busbar/compaction checkpoint is
`docs/evidence/20261105-busbar-candidates/decision.json`. It preserves rejected
5 V locations as well as the conditional 3V3 option, and distinguishes body
envelope compaction from unchanged laminate and any unproven busbar benefit.

`cec_pipeline.drafts` materializes explicitly authored, source-hashed paired
engineering drafts for larger coordinated reconstruction, including THT owners.
This is deliberately **not** a new accepted placement actuator. It keeps the
review incumbents immutable and cannot promote a draft. Poses, existing-track
redraws and existing-via translations are explicit bounded inputs; no nets,
widths, layers, drill dimensions, locks or manufacturing rules are substituted.
Only the named native nodes are spliced back into the source, with round-trip
copper and metadata checks. `--refill` uses the native deterministic filler and
splices zone nodes only; a wholesale command-line save is not trusted to retain
board fabrication properties. New-only output directories and source checks
before construction and completion prevent accidental source replacement.

Reproduce the first connected paired step with `PYTHONPATH=src:scripts python3
-m cec_pipeline.drafts --request
docs/evidence/20261105-connected-repack/j6c-connected.json --directory
/new/private/directory --refill`. The durable result is under
`experiments/repack/j6c-connected-20261105`, **not** `checkpoints/current.json`.
Both boards have fresh zero-open/zero-error native reports. Hub pair
nonregression passes; ATX numeric pair metrics improve but its conservative
receiver still rejects changed inherited reference-coverage debt. Full bus-bar
construction, current/thermal/assembly receiving, complete coordinated
placement and further compaction remain open. This step changes neither board
outline nor assembled Z and earns no bus-bar compaction credit.

`tests/test_agentic_*.py` covers geometry, protocol parity, durable campaigns,
source/cache identities, native connected construction, power construction,
portable controls and process ownership. Positive native fixtures are exercised
under rotation, mirroring and opposite faces; hostile/incomplete changes fail.
Explicit synthetic current fixtures are not production ratings.

`python3 ops/cec_regression.py --out /outside/repo/regression.xml` runs fresh
current test modules in short-lived processes. It binds source and actual
checkpoint inputs, limits workers/RSS, never consumes ignored `build/` code,
and never credits partial interrupted XML or a prior test pass.

## References

The [November 5 agentic research and blind-spot review](agentic-pcb-research-review-2026-11-05.md)
records version-pinned primary research, its limitations, missing outcome and
context tooling, and a ten-task repair benchmark ladder. The complementary
[PCB physics and methodology review](pcb-physics-methodology-review-2026-11-05.md)
inventories actual interfaces, process exceptions, impedance/return/PDN/CAN
gaps and separate release holds. Proposed checks in these reports are not
silently counted as implemented or qualified.

The local transport follows [OpenAI's MCP guidance](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
and the [MCP stdio/tool contract](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).
The physical validators and controlled CEC specification remain authoritative;
a model-authored rationale cannot waive them.
