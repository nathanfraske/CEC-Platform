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

## Received construction capabilities

* `replace_chain`: ordinary-signal shortening with source ports, launch
  tangents, width, face, native process and lock strength retained. Rejects
  exposed-material no-ops, foreign copper, edges and keepouts.
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
* `bank_collector`: literal same-net pad-bank collector with solid actual
  saved fill and deliberate chamfers. Original pads and support conductors
  remain. Its outline does not create a new current rating.

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
   or scope; do not retry the identical failed decision. Three recent failed
   decisions produce a replanning signal, not a success or a no-path proof.
6. Inspect actual native before/after plots. Selection requires both those
   hash-bound plots and all capability-specific gates.
7. Select the child, optionally `fork` it as the next working parent. A separate
   publisher makes a fresh suite review receipt; originals remain immutable.

The SQLite decision/event journal survives restart and verifies its hash chain.
Source observations alone may be reused, keyed to source/family/code/library/
native-tool identity. Raw report hashes are checked again. Changed candidates
never inherit native geometry checks. Code changes invalidate prior jobs.
Semantic source/BOM/library-body inputs, the selected physical peer and
hashed CEC/KiCad policy environment are bound too; changing one invalidates
the job rather than silently reusing its old authority.

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
The November 4 portable control retains all nine PCBs, actual footprint
libraries, fresh native reports and original provenance.

Omit `--call` for MCP stdio. The project `.mcp.json` includes `cec-layout`;
a client still needs to load/restart that project configuration in the WSL
environment. No user-wide client setting or authentication policy is changed.

`ops/cec_publish_agentic_review.py --workspace ... --job <selected-token>
--output <fresh-directory>` creates review-only lineage. Publishing the
inspection index is a deliberate separate operator action.

## Layout and qualification policy

Ordinary signals use purposeful 0/45/90 headings with 45-degree transitions,
not stair-step reversals or gratuitous hard 90s. Power uses compact cardinal
banks and deliberate chamfers; actual filled cross-sections and source
requirements outrank attractiveness. Centered via plans grant no ampacity.

Align repeated functional cells, not all capacitors of one value. Owner-pin
distance and immediate ground return outrank a cosmetic grid. Preserve
mating keys, courtyards, vents and dead-bug stack contracts.

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

The local transport follows [OpenAI's MCP guidance](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
and the [MCP stdio/tool contract](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).
The physical validators and controlled CEC specification remain authoritative;
a model-authored rationale cannot waive them.
