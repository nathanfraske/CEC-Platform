# Pour lever — scoping / plan of record (DRAFT — SCOPING, awaiting owner review)

_Owner ask, 2026-07-08 (verbatim intent): "implement a pour lever into the pipeline... so the
placer and router can ask for a new pour and it can be nudged around and re-built as needed when
it gets to that point."_

Copper pours become **first-class, mutable actuation objects** in the place→route→check loop:
requestable by the placer ("this rail wants a pour here"), reshapeable as placement evolves, and
rebuildable on router feedback (FR fails a region → notch / reshape / relocate the pour and retry)
— instead of today's one-shot, stateless post-route synthesis.

This document is a **binding-point map + schema + staged plan**, verified against the code (every
claim is `file:line`-anchored). It is READ-ONLY scoping — nothing here is built yet. Wave 13 is
running under a pipeline-file code freeze; every stage that touches `cec_fr.py` /
`cec_synth_pipeline.py` / `cec_router.py` lands **after** the freeze.

---

## TL;DR — the recommended architecture (10 sentences)

1. Pour geometry is **already effectively one source** — `cec_fr._pour_boxes_core`
   (`scripts/cec_fr.py:878`), reached through `derive_power_pours` (`:1011`) and the lane-mode
   `corridor_keepouts` (`:1153`) — but it is re-derived **statelessly** from board geometry at five
   independent call sites, which is the box-model duality debt.
2. Introduce a **`PourPlan`** object (a list of `PourSpec` primitives: net, layers, shape, region,
   priority, notch, provenance) that **all five consumers compile from**, killing the duality debt
   as a side effect and giving the lever a state to mutate.
3. The PourPlan **compiles two ways** from one geometry: PRE-ROUTE it emits keepout reservations
   (`bake_hints`, `scripts/cec_fr.py:2447`) FR routes around; POST-ROUTE it emits additive same-net
   copper (`add_power_pours`, `:717`) laid **after** FR connects everything — preserving the
   load-bearing pour-after-route ordering invariant (`:730`).
4. The **placer asks** for a pour declaratively via a new `PlacementSession.pour(net, region_hint,
   …)` that appends to `cfg.params["pour_asks"]` — the exact inert-when-unused channel `near_intents`
   / `order_intents` already use (`cec_placement_session.py:220`, read in `synth_one` at
   `cec_synth_pipeline.py:4320`/`:4331`).
5. Auto-derivation from geometry (today's `derive_power_pours` behaviour, sized off §6.4 rail
   currents) stays the DEFAULT plan; asks are additive/override on top, so a board with no ask
   compiles byte-identically.
6. The **router asks for a rebuild** through a new `apply_edit` type `pour_reshape` +
   a `MANAGER_REPAIRS` entry (`cec_router.py:630`) that reads FR feedback (foreign-on-pour records /
   unconnected loci) and emits a notch / shrink / relocate / drop-layer edit — the same repair-ladder
   slot `corridor_evict_repair` (`:575`) already occupies.
7. **Rebuild mechanics: always rebuild the pour copper on a fresh board load, never mutate a filled
   zone's outline in place** — `add_power_pours` only ever *adds* `ZONE` objects, and a measured
   `ZONE_FILLER` refill is **~0.09 s cold / 0.02 s warm** (eps, 6 zones / 583 tracks), so the pour
   half of a rebuild is free; the cost is the FR re-route (~70–95 % of a ~124 s candidate).
8. Two rebuild tiers follow from that: a **cheap** tier (post-route reshape that does not change what
   FR must avoid → re-materialize + refill only, ~0.1 s) and a **full** tier (keepout geometry
   changed → re-run FR).
9. Serialization uses a **`<board>.pourplan.json` sidecar** written at `materialize`
   (`cec_synth_pipeline.py:6077`) and read by `_oracle_hints_pours` (`:4566`), because only
   `board_path` strings cross the `materialize → route_oracle_grade → route_once` and spawn-worker
   (`:4429`) boundaries; declarative asks ride `cfg.params` and need no sidecar.
10. Prove it with a **pinned-seed A/B** (control = today's stateless derive; treatment = the lever
    with a router rebuild enabled) on the 24-pin (where lanes fire) and eps (byte-identical
    regression), scored on foreign-on-pour / unconn / thermal dT / bodies-in-pours, and route the
    router-rebuild class through the existing **steer-not-gate** chokepoint `assert_steer_only`
    (`cec_fullstack.py:668`).

---

## 1. Binding-point map — the current machinery (verified anchors)

### 1.1 The one geometry, five stateless consumers

Pour geometry is derived by ONE pure core and consumed by five call paths that each re-derive it
from the board / placement independently:

| # | Consumer (stage) | Function | Anchor | Reads geometry from |
|---|---|---|---|---|
| C1 | **Placement settle / evac** | `_pour_boxes_unified` → `cec_fr._pour_boxes_core` | `cec_synth_pipeline.py:3447` → `cec_fr.py:878` | placement `P` pads (`pad_global` + `_pad_is_tht`) |
| C2 | **Pre-route keepouts** | `corridor_keepouts` (lane mode) → `derive_power_pours` | `cec_fr.py:1153` → `:1011` | loaded board pads |
| C3 | **Post-route copper** | `derive_power_pours` → `add_power_pours` | `cec_fr.py:1011` → `:717` | loaded board pads |
| C4 | **Bodies-in-pours HARD gate** | `_oracle_bodies_in_pours` → `derive_power_pours` | `cec_synth_pipeline.py:5438` → `cec_fr.py:1011` | board zones (preferred) else derived boxes |
| C5 | **Thermal solve** | `electrothermal_solve` (reads `board.Zones()`) | `cec_synth_pipeline.py:6479` | materialized zones on the routed board |

The **pure core** — the natural compile target for a PourPlan:

```
_pour_boxes_core(names, kelvin_pairs, pads_by_net, padcount, flipped, bbox,
                 inner_layer, *, margin=1.0, layer="F.Cu")   # cec_fr.py:878
  pads_by_net = {net: [(ref, x_mm, y_mm, is_tht)]}
  → returns [ {"net":…, "layer":"F.Cu"|"B.Cu"|"In2.Cu", "polygon":[(x0,y0),(x1,y0),(x1,y1),(x0,y1)]} ]
```

Its heuristic (`cec_fr.py:889`–`1007`): for each Kelvin `*_HI`/`*_LO` pair, the box is the bbox of that
net's HEAVY pads (THT connector + the 2-pad shunt's own pad on that net; the small SMD INA sense pads
are **excluded** so HI and LO never overlap — they meet only through the shunt). Per-x-cluster fan-in
(`_x_clusters`, `:936`), per-side B.Cu selection off the shunt face (`:901`), the `SHUNT_GAP_MM` notch
(`_open_shunt_notch`, `:954`), the optional lane geometry (`_cluster_lanes`, `:839`, env
`CEC_POUR_LANES` at `:937`), and a final same-layer overlap clip (`:959`).

**The duality debt (2026-07-08, TODO ~12:20 + `build/wip-box-unify-synthside.patch`):** C1 (settle)
historically avoided topo-derived boxes while C4 (gate) checked straddle-derived clipped boxes, so
re-stamped caps kept landing in gate boxes the settle never saw — the cross-board craft blocker. The
WIP patch routes C1 through `_pour_boxes_core` too (`_pour_boxes_unified` docstring,
`cec_synth_pipeline.py:3449`–`3452`). The PourPlan **completes** this: all of C1–C4 become consumers
of one compiled plan rather than each re-deriving.

### 1.2 The pre-route / post-route split (the ordering the lever must preserve)

`route_once` (`cec_fr.py:2554`) is the whole pipeline in one call:

```
bake_hints(keepouts=hints)   # cec_fr.py:2595  — PRE-ROUTE reservations FR sees in the DSN
  → export_dsn → run_freerouting
  → import_ses(power_pours=power_pours)   # cec_fr.py:2617 — POST-ROUTE additive copper + fill
```

- **PRE-ROUTE (keepout reservations):** `corridor_keepouts` (`:1095`) → `bake_hints` (`:2447`) writes
  rule-area zones (`SetIsRuleArea(True)`, `SetDoNotAllowTracks(True)`, `allow_vias`/`block_fills`
  flags at `:2491`/`:2496`). Under `CEC_POUR_LANES` these keepouts are **exactly the lane pour
  shapes** (`:1153`–`1166`, commit `006bdb6`: "route-time keepouts ARE the lane shapes… one geometry
  source for pours, settle, gate, AND route-time keepouts"). This is already the pour-lever contract
  in embryo.
- **POST-ROUTE (copper):** `import_ses` (`:2363`) lays `add_power_pours(power_pours, fill=False)`
  (`:2409`), optional In2 force-via bridge (`:2421`), `normalize_via_annular` (`:2428`), then a
  single `UnFill()→ZONE_FILLER.Fill()` (`:2430`–`2435`).

The pour-after-route invariant is **load-bearing** (`add_power_pours` docstring, `cec_fr.py:730`):
_"These pours are laid AFTER Freerouting has already connected every net… The earlier pour-THEN-route
ordering DID strand the sense, because the pour reshaped Freerouting's GLOBAL solution… two
pipeline-grade attempts both regressed the kelvin_ok gate that way."_

### 1.3 Where the plan is assembled today (the single choke both stages already share)

`_oracle_hints_pours(board_path)` (`cec_synth_pipeline.py:4566`) is the **one function** that assembles
`(hints, pours, rules)` for a placement — tap-channel keepout (`:4574`), corridor keepout (`:4581`),
edge keepout (`:4587`), and `derive_power_pours` (`:4590`). `route_oracle_grade` (`:5582`) calls it at
`:5630` and passes the result to `cec_fr.route_once(power_pours=pours, …)` at `:5632`. **`materialize`
(`:6077`) does NOT lay power pours** — it writes only the GND zone — so pours are purely a route-time
concern today. `_oracle_hints_pours` is where the compiled PourPlan plugs in.

### 1.4 The router repair repertoire (where a rebuild verb slots in)

- `apply_edit(state, edit)` (`cec_router.py:216`) — edit types today: `place`, `place_nudge`,
  `place_rotate` (`:260`), `place_cluster`. **No pour-mutation edit exists.**
- `MANAGER_REPAIRS` (`cec_router.py:630`) — ordered `(name, fn)` strategies:
  `kelvin_inversion` (`:479`), `corridor_evict` (`:575`), `part_nudge`. Each returns an
  `apply_edit`-ready dict; the loop stops at the first hit.
- The route loop applies edits at `cec_router.py:1281`–`1283` (worker) / `:1274` (escalator) and
  re-runs `generate_batch(hints=state.hints, power_pours=spec.power_pours, …)` at `:1251`.
  **`state.hints` (pre-route) and `spec.power_pours` (post-route) are set ONCE** (`spec.power_pours =
  cec_fr.derive_power_pours(...)` at `:1542`) and never mutated by a repair — the gap the lever fills.
- The two-pass-corridor (TPC) machinery (`cec_router.py:855`–`968`) already does a route → rip →
  re-route with pour reshaping, and it does zone/track removal **only in a subprocess** (`_TPC_RIP_CHILD`,
  `:870`; comment at `:857`: "removing tracks then SaveBoard corrupts pcbnew's NetInfo SWIG proxies for
  the rest of THIS interpreter… so isolating it keeps the FR pipeline clean"). This is the precedent
  for the footgun-safe rebuild.

### 1.5 The gates the lever must not launder (verified severities)

| Checker (id) | Anchor (reg / chk) | Class |
|---|---|---|
| `no-foreign-on-high-current-pour` / `foreign_on_pour_summary` | `cec_constraints.py:104` / `:892` / `:865` | **HARD** (router fold + intake) |
| `high-current-pour-integrity` | `:98` / `:948` | **HARD** |
| `high-current-pour-present` | `:86` / `:922` | **HARD (strong)** |
| `sense-body-clear-of-pour` (bodies-in-pours) | `:167` / `:1364` | **HARD (strong)** |
| `high-current-corridor-keepout` | `:82` / `:1089` | **HARD (strong)** |
| `kelvin-sense-from-inner-pad` / `-no-connector-tap` | `:136` / `:1158`, `:147` / `:1259` | **HARD (strong)** |
| `netclass-geometry-conformance` | `:312` / `:1841` | **HARD** |
| `min-pour-cross-section` | `:124` / `:1122` | **ADVISORY (proposed)** |

`no-foreign-on-high-current-pour` detection is geometric, not DRC-derived (`_foreign_pour_records`,
`:810`; foreign = any net not the pour's own or an INA sense net, GND/rails included). `min-pour-
cross-section` runs the `cec_dcir` field solve and, on FAIL, _"emits a 'reserve more pour' placer
keepout"_ (`:1124`) — i.e. the checker family **already speaks in pour-reshape terms**; the lever is
the actuator that closes that loop. The bodies gate (`_chk_sense_body_clear`, `:1364`) materializes
boxes via `derive_power_pours` (`:1388`) — it too becomes a PourPlan consumer.

### 1.6 The parked inner-pour cousin (`CEC_INNER_POURS`)

`derive_power_pours` (`cec_fr.py:1049`) and `corridor_keepouts` (`:1121`) both scan for a `PWR_RT`
signal layer and target `In2.Cu`; `import_ses` bridges shunt pads to In2 via `synthesize_force_vias`
(`:1331`, wired at `:2421`). Marked **experimental / OFF**: comment at `cec_fr.py:1051`–`1055`
_"placement effect proven (unconn 114→74@p8) but FR integration incomplete — In2 keepouts don't bind
in FR (116 foreign) + force stubs need [`_tap_foreign_clear`, `:1569`]. OFF until done."_ `layers` is
already a per-`PourSpec` field, so the PourPlan **absorbs** inner pours as a first-class layer option;
the FR-DSN In2-binding fix stays a separate follow-up (it is a DSN-export problem, orthogonal to the
plan object).

---

## 2. `PourPlan` schema (the owner of pour state)

A pure-data object (dataclass of plain types → picklable, JSON-serializable) living in a **new
`scripts/cec_pourplan.py`** so it imports cleanly from both `cec_fr` and `cec_synth_pipeline` without
a cycle.

```python
@dataclass
class PourSpec:
    net: str                       # "/SENSEC1_HI" etc.
    layers: tuple[str, ...]        # ("F.Cu",) | ("B.Cu",) | ("In2.Cu",) | ("F.Cu","B.Cu")
    shape: str                     # "lane" | "corridor" | "rect" | "notched"
    region: tuple|None = None      # (x0,y0,x1,y1) mm hint; None = auto-derive from pads
    priority: int = 2              # zone priority above GND(0)
    notch: dict|None = None        # {"at":(x,y), "gap_mm":6.5, "vertical":True} — the shunt window
    exempt_nets: tuple = ()        # nets allowed to live inside (own-rail eviction exemption)
    min_thickness: float = 0.25
    island_removal: int = 0
    provenance: str = "derived"    # "derived" | "placer_ask" | "router_ask" | "human"
    frozen: bool = False           # human-ratified geometry the loop may not mutate

@dataclass
class PourPlan:
    specs: list[PourSpec]
    board_sig: str                 # placement hash — plan is valid only for this placement
    recipe: dict                   # {pour_lanes, shunt_gap_mm, corridor_fcu_only, lane_w_json, inner}

    # --- constructors ---
    @classmethod
    def from_board(cls, board_path, *, asks=(), recipe=None) -> "PourPlan":
        """DEFAULT plan = today's derive_power_pours geometry (auto-derived from §6.4 rail
        pads), then apply placer/router `asks` (add / override / reshape). asks=() → byte-identical
        to derive_power_pours today."""

    # --- the two compiles (one geometry, two artifacts) ---
    def keepout_hints(self) -> list[dict]:   # PRE-ROUTE: bake_hints-ready {name,x0,y0,x1,y1,layers,allow_vias,block_fills}
    def pour_polygons(self) -> list[dict]:   # POST-ROUTE: add_power_pours-ready {net,layer,polygon,priority,...}
    def evac_boxes(self) -> list[tuple]:     # PLACEMENT: (net,x0,x1,y0,y1) for _evacuate_pours / gate

    # --- the mutation verbs (the lever's actuation surface) ---
    def notch(self, net, at, gap_mm): ...        # widen/relocate the un-poured shunt window
    def shrink(self, net, edge, mm): ...         # pull a pour edge back off a congested region
    def relocate(self, net, region): ...         # move a lane/box to a new hint region
    def drop_layer(self, net, layer): ...        # F.Cu+B.Cu → F.Cu only (foreign escapes under)
    def add(self, spec: PourSpec): ...           # placer/router asks a pour geometry wouldn't derive
```

**Why this kills the duality debt:** `_pour_boxes_core` becomes the private geometry kernel that
`PourPlan.from_board` calls once; `keepout_hints()` / `pour_polygons()` / `evac_boxes()` are three
*views* of the same `specs`. C1–C4 (§1.1) all consume a plan view instead of independently calling
`derive_power_pours`, so the settle, the gate, the keepout, and the copper are geometrically identical
**by construction** — no drift possible.

---

## 3. The ask/rebuild APIs

### 3.1 Placer ASK (declarative, inert-when-unused)

Add to `PlacementSession` (`cec_placement_session.py`), mirroring `near()` (`:107`) / `order()`
(`:115`):

```python
def pour(self, net, *, region_hint=None, layers=("F.Cu",), shape="lane", priority=2):
    """Request a pour on `net`. region_hint=None → auto-derive from the net's pads (default
    behaviour). Compiles through cfg.params['pour_asks']; inert when unused (golden safety)."""
    self._pour_asks.append({...}); return self
```

`_cfg_dict` (`:220`) adds `d["params"]["pour_asks"] = self._pour_asks` — the identical channel
`near_intents` (`:222`) / `order_intents` (`:224`) use, so it **serializes through `synth_one` for
free** (read at `cec_synth_pipeline.py:4320`/`:4331`; the new read sits beside them). `synth_one`
builds its plan as `PourPlan.from_board(board, asks=cfg.params.get("pour_asks") or ())` and hands
`plan.evac_boxes()` to the evac/mop loop (`:4212`) in place of the raw `_pour_boxes_unified` call.

**Auto-derivation stays the default.** The current `derive_power_pours` heuristic (sized off §6.4 rail
currents via `_lane_width_mm`, `cec_fr.py:826`) IS the default plan; an ask only *adds* a pour the
geometry wouldn't derive (a rail with no 2-pad shunt straddle), *overrides* a derived pour's shape/
layers, or *pins* a region. No ask → `from_board(asks=())` → byte-identical to today (the golden
guarantee).

### 3.2 Router REBUILD (a repair verb in the existing ladder)

New `apply_edit` type in `cec_router.py:216`:

```python
elif t == "pour_reshape":              # {net, op:"notch|shrink|relocate|drop_layer|add", ...}
    state.pour_plan.<op>(...)          # mutate the plan (state, not the board)
    state.hints        = state.pour_plan.keepout_hints()   # recompiled PRE-ROUTE reservation
    spec.power_pours   = state.pour_plan.pour_polygons()   # recompiled POST-ROUTE copper
```

New `MANAGER_REPAIRS` entry (append to `cec_router.py:630`), a sibling of `corridor_evict_repair`:

```python
def pour_rebuild_repair(board_path, rules=None, metrics=None):
    """Read FR feedback and ask a pour rebuild. If foreign_on_pour records exist → notch/shrink
    the offended pour or drop_layer to let the foreign net escape under it; if a high-current net
    is left unconnected in a pour region → relocate/widen. FENCE: never touch a `frozen` spec
    (human-ratified) or change a pour's net. Returns a 'pour_reshape' edit or None."""
    recs = cec_constraints.foreign_on_pour_summary(board_path)   # cec_constraints.py:865
    ...  # map the offended pour + locus → the cheapest reshape op
```

This fits the route→snag→revise loop unchanged: the manager returns the edit, `apply_edit`
recompiles `state.hints` + `spec.power_pours` from the mutated plan, and the next `generate_batch`
iteration (`:1251`) re-routes against the new geometry. It is the **corridor-evict analogue for the
pour itself** — where `corridor_evict_repair` moves a *body* out of a corridor, `pour_rebuild_repair`
moves the *pour* off a foreign trace.

### 3.3 The checker-driven ask (closing the existing hint)

`min-pour-cross-section` already _"emits a 'reserve more pour' placer keepout"_ on FAIL
(`cec_constraints.py:1124`). Wire that emission to a `PourSpec` widen/add ask, so a DC-IR failure
directly requests more copper. This is the tightest coupling and the clearest win — the checker names
the deficiency, the lever fixes it, the checker re-verifies.

---

## 4. Ordering — what is pre-route vs post-route, what re-runs on a rebuild

| Phase | Artifact | From PourPlan | When |
|---|---|---|---|
| Placement settle | evac boxes | `plan.evac_boxes()` | every placement candidate (`synth_one`) |
| Pre-route | keepout reservations | `plan.keepout_hints()` → `bake_hints` | before each FR route |
| **FR route** | routed copper | (FR routes AROUND the keepouts) | the expensive step |
| Post-route | additive pour copper + fill | `plan.pour_polygons()` → `add_power_pours` | after FR connects everything |
| Check | gates + thermal | plan views (C4) + materialized zones (C5) | after materialization |

**On a router rebuild ask, what re-runs depends on the op:**

- **Full tier — keepout geometry changed** (`relocate`, `add`, `drop_layer`, a notch that changes
  what FR must avoid): recompile `keepout_hints()` → **re-run FR** (the pour must be routed around
  differently) → re-materialize `pour_polygons()` + refill. Cost ≈ one FR route (~124 s on the 24-pin
  per the roadmap; dominates).
- **Cheap tier — copper-only change** (`shrink`/`notch` that only alters the post-route fill, not
  what FR avoided): keep the routed board, re-materialize `pour_polygons()` + refill only. Cost ≈
  **0.1 s** (measured, §5). This is the "nudge it around" case the owner's phrasing implies — a pour
  moved within the space FR already left clear.

This preserves the pour-after-route invariant absolutely: the *copper* is never laid before FR; only
the *keepout reservation* (which is not copper) precedes FR, exactly as lane mode already does today.

---

## 5. Nudge/rebuild mechanics under the recorded footguns

**Measured refill cost (in-container, temp copy of `build/overnight-directed/eps-8pin-r8.kicad_pcb`,
6 zones / 583 tracks / 49 footprints):** `ZONE_FILLER.Fill` = **0.091 s cold, 0.021 s warm**. The pour
half of a rebuild is effectively free; the budget is spent entirely on the FR re-route (full tier) or
saved entirely (cheap tier).

**Reshape strategy: rebuild the pour copper on a FRESH board load, never in-place outline mutation.**
This is already how `add_power_pours` works — it only ever *creates and adds* `ZONE` objects
(`cec_fr.py:752`–`772`) on the board `import_ses` freshly loaded (`board_path`, `:2617`); it never
removes or mutates a live zone. A rebuild therefore = re-run `route_once`/`import_ses` from the
placement board with the new `pour_polygons()`. In-place outline mutation of an already-filled zone is
**not needed and not recommended**, because the fill is cheap and in-place mutation walks straight into
the footguns.

Footgun compliance:

| Footgun | Rule | How the design honors it |
|---|---|---|
| (a) Zone removal corrupts NetInfo → SwigPyObject/segfault | Never `board.Remove(zone)` in the live interpreter | The lever **never removes a zone**. `add_power_pours` only adds. A reshape discards the whole routed board and re-derives copper on a fresh `LoadBoard` (`import_ses`). If a stale routed pour must be stripped (TPC-style), it runs in a **subprocess** (precedent: `_TPC_RIP_CHILD`, `cec_router.py:870`; comment `:857`). `synthesize_power_copper` states the invariant verbatim (`cec_fr.py:2239`). |
| (a′) `SetOutline` aliases → empty outline → segfault | Append into `z.Outline()` in place, never `SetOutline` | Reuse the existing safe pattern (`add_power_pours:764`, `bake_hints:2514`, `cec_route.py:123`). PourPlan emits polygons; the append happens in the vetted callee. |
| (a″) Double-fill in one process segfaults | `UnFill()` before `ZONE_FILLER.Fill()` | Every fill path already does this (`cec_fr.py:774`, `:2430`, `:2264`, `:2299`, `cec_route.py:216`). The lever adds no new fill site — it feeds `import_ses`, which owns the fill. |
| (b) Pour-then-route strands sense taps | Copper only AFTER route | §4: the plan emits *keepouts* pre-route (not copper) and *copper* post-route. Invariant unchanged. |
| (c) A through-via anti-pad severs a thin same-Y lane | Lane geometry must not be cut by a via/anti-pad | Lane pours carry their own band + notch-exempt fingers (`_cluster_lanes`, `cec_fr.py:839`); a reshape preserves the finger geometry (never a `shrink` that removes a finger). `foreign_on_pour` (`:892`) + `high-current-pour-integrity` (`:948`) re-check after every rebuild. |
| (d) KiCad re-nets copper touching a foreign net on save/load | Same-net-only additive pours; verify after | `add_power_pours` sets the net code explicitly (`:759`) and pours are same-net; the post-rebuild `foreign_on_pour` gate catches any re-net. |
| (e) Fill in a fresh spawn if the process previously Removed items | Isolate remove+fill in a subprocess | Only the (optional) stale-pour strip removes; it is subprocess-isolated (see (a)). The normal rebuild loads fresh, so its fill is clean. |

---

## 6. Staged implementation plan

Each stage is independently landable and teeth-verifiable. **Freeze note:** stages 1, 2, 4 touch the
hot pipeline files (`cec_fr.py`, `cec_synth_pipeline.py`, `cec_router.py`) — they must land **after**
wave 13's code freeze. Stage 3 also edits `materialize`/`_oracle_hints_pours` (post-freeze). Stage 5 is
mostly a new eval script (lower conflict). Sequence: **1 → (2 ∥ 3) → 4 → 5**; stage 1 is the refactor
everything depends on.

### Stage 1 — `PourPlan` object + compiler (pure refactor, zero behavior change)
- New `scripts/cec_pourplan.py`: `PourSpec`/`PourPlan`, `from_board`, the three compile views.
  `_pour_boxes_core` (`cec_fr.py:878`) becomes its geometry kernel.
- Re-point the five consumers (§1.1) at plan views: `derive_power_pours`/`corridor_keepouts`
  (`cec_fr.py:1011`/`:1153`), `_pour_boxes_unified`/`_oracle_hints_pours`/`_oracle_bodies_in_pours`
  (`cec_synth_pipeline.py:3447`/`:4566`/`:5438`).
- **Teeth:** `plan.pour_polygons()` and `plan.keepout_hints()` byte-identical to today's
  `derive_power_pours` / `corridor_keepouts` on eps + 24-pin (golden fixture, `asks=()`). The box-model
  duality is closed by construction (settle boxes == gate boxes).
- **Effort:** 2–3 days. **Touches:** cec_fr.py, cec_synth_pipeline.py (×3), new cec_pourplan.py.
  **Conflicts freeze.**

### Stage 2 — placer ASK API (declarative, inert-when-unused)
- `PlacementSession.pour(...)` → `cfg.params["pour_asks"]` (`cec_placement_session.py:220`); `synth_one`
  reads it into `PourPlan.from_board(asks=…)` beside the `near`/`order` reads
  (`cec_synth_pipeline.py:4320`).
- **Teeth:** a `pour()` ask on a no-shunt rail produces a new pour box + the placer evacuates bodies
  from it (`_evacuate_pours`, `:3531`); no ask → byte-identical placement. Host test in
  `tests/`.
- **Effort:** 1–2 days. **Touches:** cec_placement_session.py, cec_synth_pipeline.py, cec_pourplan.py.
  **Conflicts freeze.**

### Stage 3 — PourPlan serialization sidecar
- Write `<board>.pourplan.json` in `materialize` (`cec_synth_pipeline.py:6077`); `_oracle_hints_pours`
  (`:4566`) loads it, falling back to `from_board` when absent (so old boards still route).
- **Teeth:** sidecar round-trips through the spawn pool (`:4429`); `route_oracle_grade` reads an
  identical plan whether from sidecar or `from_board`.
- **Effort:** ~1 day. **Touches:** cec_synth_pipeline.py (materialize, _oracle_hints_pours),
  cec_pourplan.py. **Conflicts freeze (light).**

### Stage 4 — router REBUILD verb (the actuation lever)
- `apply_edit` type `pour_reshape` (`cec_router.py:216`) + `pour_rebuild_repair` in `MANAGER_REPAIRS`
  (`:630`). `state.pour_plan` added to the route `state`; on the edit, recompile `state.hints` +
  `spec.power_pours`. Two rebuild tiers (§4).
- The edit passes the steer-not-gate chokepoint `assert_steer_only` (`cec_fullstack.py:668`) — it may
  reshape/reorder but must never write `gates_pass`; success is judged by the SAME hard gates
  (foreign-on-pour, pour-integrity, thermal dT) re-run after.
- **Teeth:** inject a foreign trace across a 24-pin pour → `pour_rebuild_repair` emits a notch/drop-layer
  → re-route drives `foreign_on_pour` n_tracks+n_vias to 0 while `kelvin_ok` holds; a reshape that would
  neck the pour below `min-pour-cross-section` is refused.
- **Effort:** 3–4 days. **Touches:** cec_router.py, cec_pourplan.py, (advisory) cec_fullstack.py.
  **Conflicts freeze.**

### Stage 5 — eval harness + graduation wiring
- New `scripts/cec_pour_lever_eval.py`: pinned-seed A/B (control = stateless derive; treatment = lever +
  router rebuild) on 24-pin + eps, per §7. Route the router-rebuild class into the actuation-lever
  clean-evidence tally (`docs/actuation-lever-design.md`) so a repeatedly-winning rebuild op graduates
  CANDIDATE → RATIFIED-STEER; graduation stays owner-gated (`promoted/**`).
- **Teeth:** A/B shows the lever moves foreign-on-pour / dT on the fixture; control byte-identical;
  `assert_steer_only` holds on every emitted edit.
- **Effort:** ~2 days. **Touches:** new eval script + (advisory) cec_fullstack.py tally hooks.
  **Low freeze conflict** (mostly new file).

Total: ~9–12 working days across 5 stages.

---

## 7. Eval protocol (proving the lever helps)

Mirror the coord-router A/B (`docs/pipeline-solver-roadmap.md` §"Co-coordinating router") — pinned
seeds, identical placement, one variable:

- **Control:** today's path (`derive_power_pours` stateless, no rebuild).
- **Treatment:** PourPlan + `pour_rebuild_repair` enabled.
- **Boards:** 24-pin rev3 (`CEC_POUR_LANES=1`, `shunt_gap_mm=16` — where lanes fire and bodies-in-pours
  was the hard blocker) as the *does-it-help* board; eps-8pin as the *regression* board (must stay
  byte-identical with `asks=()` and no rebuild trigger — the golden guarantee).
- **Metrics (from `route_oracle_grade`, `cec_synth_pipeline.py:5818`):** `foreign_ok` +
  `foreign_on_pour` n_tracks/n_vias (`cec_constraints.py:865`), `unconnected`, thermal `dt` /
  `thermal_ok`, `bodies_in_pours` (`_oracle_bodies_in_pours`, `:5438`), `min-pour-cross-section` DC-IR
  peak density (`:1122`), and the composite `gate` / `sort_key`.
- **Primary claim:** on the 24-pin fixture, a lever-enabled run reaches `foreign_on_pour == 0` with
  fewer re-routes (or reaches it where control cannot), with `kelvin_ok` / `bodies_in_pours` held.
- **Safety claim:** control lane byte-identical; every rebuild edit passes `assert_steer_only`.

---

## 8. Risks / open questions the owner must rule on

1. **Is a router-initiated pour rebuild a "design change" under the human-ratification boundary?**
   (CLAUDE.md "constraint loop's human-ratification boundary — SET IN STONE".) **Proposed rule:**
   *reshaping* an auto-derived pour — notch / shrink / relocate / drop-layer, same net, geometry only —
   is **inside loop autonomy** (it is the same class as the already-autonomous `corridor_evict_repair`,
   the `CEC_CORRIDOR_FCU_ONLY` B.Cu drop, and lane synthesis). *Adding* a pour on a net the plan
   wouldn't derive, *dropping* a required pour, or *changing a pour's net* is a **design change →
   escalate to the human**. Owner must confirm this line, especially: does `drop_layer` (F.Cu+B.Cu →
   F.Cu) count as in-loop? (Precedent says yes — `CEC_CORRIDOR_FCU_ONLY` already does it — but it does
   change the copper topology.)
2. **Steer-not-gate integrity.** The rebuild must never make a failing board pass by *hiding* a
   violation — e.g. shrinking a pour below cross-section to dodge `foreign_on_pour`. **Ask:** should
   `min-pour-cross-section` (today ADVISORY, `cec_constraints.py:124`) be **promoted to a hard gate on
   a rebuilt pour** so a reshape cannot neck the copper to cheat the foreign gate? The pour-lever is
   the first *live* caller of `assert_steer_only` (`cec_fullstack.py:668`), which has had "no live
   actuation caller yet" (actuation-lever design §"Implementation status") — owner should bless it as
   the graduation exemplar.
3. **Inner-pour cousin scope.** The PourPlan makes `In2.Cu` a first-class layer (absorbs
   `CEC_INNER_POURS`), but FR keepout binding on In2 is the known-incomplete piece (`cec_fr.py:1051`).
   **Ask:** does stage 1 also carry the In2 FR-binding fix (`_tap_foreign_clear` + DSN inner-layer
   keepout), or does the inner-pour work stay parked and only inherit the schema? (Recommendation:
   inherit the schema, keep the FR-binding fix a separate follow-up.)
4. **Rebuild budget / loop bound.** A full-tier rebuild costs one FR route. **Ask:** cap rebuilds per
   region (proposed: fold into the existing `Kmax` / `max_iters` budget, `cec_router.py:1271`/`:1286`,
   so a pour rebuild counts as a repair iteration and can't spin the loop).

---

## 9. Files touched (summary)

- **New:** `scripts/cec_pourplan.py` (the object + compiler), `scripts/cec_pour_lever_eval.py` (A/B),
  `tests/test_pourplan.py`.
- **`scripts/cec_fr.py`:** `_pour_boxes_core` (`:878`) becomes PourPlan's kernel; `derive_power_pours`
  (`:1011`) / `corridor_keepouts` (`:1153`) become plan views.
- **`scripts/cec_synth_pipeline.py`:** `_pour_boxes_unified` (`:3447`), `_oracle_hints_pours` (`:4566`),
  `_oracle_bodies_in_pours` (`:5438`), `synth_one` (`:3869`, read `pour_asks`), `materialize` (`:6077`,
  write sidecar).
- **`scripts/cec_placement_session.py`:** `pour()` ask + `_cfg_dict` plumb (`:220`).
- **`scripts/cec_router.py`:** `apply_edit` `pour_reshape` (`:216`), `pour_rebuild_repair` +
  `MANAGER_REPAIRS` (`:630`), `state.pour_plan` in the route loop (`:1251`).
- **`scripts/cec_fullstack.py`:** (advisory) route the rebuild class through `assert_steer_only`
  (`:668`) + the clean-evidence tally.

_End of scoping draft. Awaiting owner review before any implementation._
