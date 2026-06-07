# `cec_pcb` — repo-wide PCB layout toolkit

`scripts/cec_pcb.py` is a shared toolkit any board generator (or an agent working on a
board) can pull on, so the layout abilities we built for the EPS module aren't trapped in
one script. It sits on top of `gen-module-pcb.py`'s emit primitives (which it imports once,
with a no-op board filter, so importing the toolkit never builds a board).

`scripts/gen-eps-condensed.py` is the **worked example** — a thin driver that only supplies
EPS-specific data and calls the toolkit for everything else. Copy its shape for a new board.

## What it gives you

| Area | Functions | What you get |
|---|---|---|
| **Geometry** | `pad_global`, `local_pads`, `courtyard_bbox`, `part_half` | KiCad-rotation-correct pad/courtyard math; optional antenna-keepout trim for RF modules with Wi-Fi unpopulated. |
| **Passives** | `verify_passives`, `auto_cluster`, `place_offsets` | `verify_passives(nets, spec)` proves each part is on its expected net (cluster owner is right). `auto_cluster(P, comps, {ref:(owner,pad)})` parks every decoupler just outside its owner IC's power-pad, courtyard-aware + fanned, with an overlap-relaxation pass — a **structurally-clean starting placement** (returns residual overlaps). `place_offsets(P, {ref:(x,y,rot)})` ships hand-refined coords. |
| **Routing guides** | `guides(routes)` | Routing-candidate guide graphics (12 V pours, Kelvin pairs, the control→sense spine, CAN, USB…) on toggleable user layers — drawn **in the board** so they're visible while routing. Non-copper → no DRC impact. |
| **Visualize** | `routing_plan_png(...)` | A board-accurate matplotlib routing plan: parts (from courtyards) + pours + traces + vias + a legend + side-panel tables (routing order / netclasses / SI). |
| **Rules** | `netclass`, `write_netclasses`, `write_dru` | Fill a board's empty `.kicad_pro` `net_settings` and a matching `.kicad_dru`. |
| **Build** | `build_board`, `export_netlist` | Assemble + write the `.kicad_pcb` (frame + passives + guides + GND zone + edge cuts), with the one-shot "refuse to overwrite a routed board" guard. |

## Minimal driver shape

```python
import cec_pcb as cp

def frame():           # board-specific: ICs/connectors/shunts placed; mounts; logo
    ...                # return W, H, ex, P, mounts, logo  (P: ref -> (x,y,rot))

GEOM = {"C3": ("U1","3"), "C10": ("U10","6"), ...}                 # decoupler -> (owner, power pad)
OWN  = {"C3": ("U1","+3V3","role"), ...}                          # decoupler -> (owner, expected net, role)

def main():
    netf = cp.export_netlist("my-mod", "my-mod-board")
    comps, vals, nets = cp.parse_netlist(netf)
    cp.verify_passives(nets, OWN)
    W, H, ex, P, mounts, logo = frame()
    cp.auto_cluster(P, comps, GEOM, drop_keepout={"U1"})          # or cp.place_offsets(P, table)
    gstr = cp.guides([{ "poly": [...], "layer": "Dwgs.User" }, { "line": [...], "layer": "Eco1.User" }, ...])
    cp.build_board(f"{mod}/board.kicad_pcb", netf, P, mounts, logo, W, H, guides_str=gstr, drop_keepout={"U1"})
    cp.write_netclasses(f"{mod}/board.kicad_pro", [cp.netclass("Power", 0.5, 0.8, 0.4, 5), ...],
                        [("Power", "+3V3"), ("USB", "/USB_D_P"), ...])
    cp.write_dru(f"{mod}/board.kicad_dru", [("Power min width", "track_width (min 0.5mm)", "A.NetClass == 'Power'"), ...])
    cp.routing_plan_png(f"{mod}/routing-plan.png", W=W, H=H, title="...", P=P, comps=comps,
                        pours=[...], traces=[...], vias=[...], tables=[...], legend=[...], mounts=[...])
```

## Notes / conventions

- **`auto_cluster` is a *starting* placement** — structurally clean (0 overlaps on EPS), caps
  on the right power-pin side. Silk text + final spacing are always a GUI-refinement pass; use
  `fixed_overrides={ref:(x,y,rot)}` to pin the few a board wants exact, or `place_offsets` for a
  fully hand-refined board (the EPS driver ships `place_offsets` by default and exposes
  `auto_cluster` behind `--auto`).
- **Matched pairs** are recognized by net name: rename a true differential pair to the `_P`/`_N`
  suffix (e.g. `/USB_D_P` `/USB_D_N`) so KiCad's diff-pair router auto-pairs it, and give it a
  `diff_pair_width`/`diff_pair_gap` netclass. Keep semantically-asymmetric pairs (CAN_H/CAN_L)
  on their standard names and route them coupled. A Kelvin sense pair that shares a force net
  (e.g. `/SENSEC*_HI` / `_LO`) can't be a separable diff-pair — hand-match it.
- **Antenna keepout:** pass `drop_keepout={"U1", ...}` (build + plan + auto_cluster) to trim an
  RF module's antenna-lobe courtyard to its body when Wi-Fi is unpopulated (GND fills under it).
- **One-shot:** `build_board` refuses to overwrite a board that already has tracks/vias unless
  `--force` is on `sys.argv` — the floorplan is a bootstrap, hand-maintained in the GUI after the
  first route.
- **No shared-generator edits:** the toolkit imports `gen-module-pcb.py`'s primitives; it does
  not modify them, so it's safe to use alongside that generator.

# `cec_route` — real-copper routing pass (companion to `cec_pcb`)

Where `cec_pcb.guides()` draws *non-copper* routing hints on user layers, `scripts/cec_route.py`
emits **actual routed copper** through the real KiCad 10 `pcbnew` engine (the same one the GUI
uses) and verifies it with the real DRC + connectivity. This is the engine the **routing
sub-agent** drives. It is NOT hand-edited s-expr — it goes through the real engine, which is why
it's sanctioned (see CLAUDE.md "Sub-agent routing pass — GO-AHEAD").

## `Router` API

```python
import cec_route as cr
r = cr.Router("/tmp/cand/board.kicad_pcb")   # work on a COPY, never the committed floorplan
r.pad("U10", "10")                           # -> (x,y) mm of a pad
r.track("/CAN_H", [r.pad("U2","7"), (88,8), r.pad("J1","3")], "F.Cu", 0.25)
r.via("GND", (24.4, 6.8), drill=0.5, dia=0.9, layers=("F.Cu","B.Cu"))
r.zone("/SENSEC1_HI", [(9.5,8),(25.1,8),(25.1,13),(9.5,13)], layers=("F.Cu",))   # a pour
r.fill()                                     # REAL ZONE_FILLER (kicad-cli cannot do this)
res = r.verify()                             # {n_struct, structural[], n_unconnected, unconnected[]}
```

`verify()` saves + runs `kicad-cli pcb drc` and filters the benign classes (silk + `lib_footprint_*`),
so `n_struct` is the real DRC and `n_unconnected` is the live ratsnest (what's still unrouted).

## Cleanliness rules — candidate routing is CLEAN, not COMPLETE

The point is **not** to route every net. It is to keep the **vital** runs' areas clean and fit the
**non-vital, annoying-to-place** runs (the signal spine, control, CC, etc.) into the leftover space
**without intruding on the vital runs**, terminating each one correctly. The `Router` enforces/verifies:

```python
r.mark_vital("/SENSEC1_HI", "/SENSEC1_LO", "GND")        # R1: these must stay clean
r.keepout("12V_IN1", 9.5,8, 25.1,13, ("F.Cu","B.Cu"))    # reserve the vital areas (pours, Kelvin)
ln = cr.lanes(["/I2C_SDA","/I2C_SCL","/THRESH"], 22.0, 0.4)   # R3: one lane per net, no overlap
hit = r.run("/I2C_SDA", [(57,18), (32,ln["/I2C_SDA"]), (9.3,18)], "F.Cu", 0.22)  # returns keep-out hits
r.to_pad("/I2C_SDA", "U10", "4", (9.3, 18), "F.Cu")      # R4: ends on a layer the pad is ON
...
r.check_keepouts()        # R1/R2: any non-vital run that entered a vital keep-out
r.check_terminations()    # R4: any track ending INSIDE a pad on a layer the pad is NOT on
```

| Rule | What it does |
|---|---|
| **R1 vital keep-out** | `mark_vital()` + `keepout()` reserve the 12 V pour columns, the Kelvin sense windows, and GND fanouts; non-vital runs may not enter them. `run()` reports hits live; `check_keepouts()` verifies. |
| **R2 layer complement** | route non-vital on the layer the vital copper isn't using in a region (F.Cu pour ⇒ signals on B.Cu, and vice-versa; inners stay GND). |
| **R3 lane discipline** | `lanes()` gives each net its own lane (distinct offset) so same-layer runs don't overlap or criss-cross — cross only by a via to the other layer. |
| **R4 clean termination** | `to_pad()` ends a run on a layer its target pad is on; a layer change vias in **clear channel space**, never on a fine-pitch pad, and never a track ending inside a pad on the wrong layer. `check_terminations()` finds that bug. |

Sequence: route the **vital nets first** (reserve their areas), then fit the non-vital runs into the
channels with `run()`/`to_pad()`/`lanes()`, then `check_keepouts()` + `check_terminations()` + `verify()`.

## pcbnew gotchas (baked into the toolkit; know them if you extend it)

These cost the first routing agent real time — both are fixed in `cec_route.py`:
- **Zones:** build the outline by appending **into `z.Outline()` in place**, NOT
  `z.SetOutline(<external SHAPE_POLY_SET>)` — in this KiCad-10 SWIG build `SetOutline` *aliases*,
  so the external poly goes empty when GC'd and `ZONE_FILLER` then **segfaults**. Validity is
  `z.Outline().FullPointCount()`, not `GetOutlineArea()` (the latter reads a stale cache → 0).
- **Re-fill:** `fill()` must `z.UnFill()` every zone before `ZONE_FILLER.Fill()`, or the second
  fill in one process segfaults on an already-filled multi-layer zone.
- `import pcbnew` prints harmless `assert "m_choices…"` / `No enum choices` to stderr — ignore.

## The iterative routing loop (sub-agent passes)

Routing candidates are generated by a **loop of sub-agent passes** that feed each other — the
orchestrator builds/maintains the toolkit and spawns the passes; it does not hand-route:

```
  placement/footprint pass  (cec_pcb.auto_cluster / place_offsets, frame())
            │  floorplan
            ▼
  routing game-plan pass     (cec_pcb.guides + routing_plan_png: layers/widths/vias/waypoints)
            │  plan
            ▼
  ROUTING pass               (cec_route on a COPY: realize the plan as real copper,
            │                  fill pours, verify with the real DRC/connectivity)
            │  routed candidate + SNAG REPORT
            ▼
  feedback ──┬─► placement pass : move/rotate a part, widen a band, fix a pad escape
             └─► game-plan pass : change a net's layer/lane/width, add vias, re-order
            (orchestrator re-spawns the upstream pass, then re-runs the routing pass)
```

Honest expectation: the **deterministic nets route clean headlessly** — split/filled 12V pours,
the GND plane + stitching, Kelvin stubs, the USB diff pair, CAN, short point-to-point. The **dense
crossing signal spine** typically needs a placement/plan revision (the routing pass tells you
exactly what), an external autorouter (Freerouting via Specctra DSN — `java` is present, the jar is
not), or the GUI. The routing pass **reports the required upstream changes; it does not silently
edit placement/footprints/the plan** — that keeps each pass's responsibility clean and the loop
auditable.

# Automated routing system — two-plane architecture (`cec_fr` + `cec_score` + `cec_router`)

The single-pass `cec_route` loop above proved real copper is reachable headlessly, but the dense
spine kept needing a human/GUI/autorouter. The **automated routing system** closes that gap by
splitting routing into a **deterministic plane** (reproducible, no LLM) and a **control plane**
(tiered judgement, pluggable). It drives the *real* KiCad↔Freerouting autorouter through Specctra
DSN/SES, scores every candidate against **hard safety gates**, and records every decision so a run
is reproducible.

```
                        ┌──────────────────────── CONTROL PLANE (tiered judgement, pluggable) ───────────────────────┐
                        │  planner   (Opus)   region/seam plan   ·  manager (Sonnet)  accept|repair|escalate          │
                        │  worker    (Haiku)  cheap param/hint edits  ·  escalator (Opus)  structural re-plan @ K stalls │
                        └───────────────────────────────────────────┬──────────────────────────────────────────────┘
                                                                     │ (default: deterministic policies → runs with NO LLM)
  ┌──────────────────────────────────── DETERMINISTIC PLANE (pure, reproducible) ────────────────────────────────────┐
  │  cec_fr.generate_batch ──► [Candidate, …]  ──► cec_score.score ──► Metrics(+HARD GATES) ──► objective rank        │
  │       │  (KiCad→DSN→Freerouting→SES→KiCad, parallel seeds, vital-area keep-outs baked in)                          │
  │       ▼                                                                                                            │
  │  cec_router.route():  spec_to_dru → plan → per-region {generate→score→gate→judge→repair|escalate} →               │
  │                        serial_merge (seam reconcile) → write_once → INDEPENDENT DRC verdict → DecisionLog(JSON)    │
  └────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Tier 0 — `cec_fr.py`: the Freerouting candidate generator

Round-trips a board through the **real autorouter**: `pcbnew.ExportSpecctraDSN` → Freerouting (headless,
`xvfb-run java -jar`, **pinned v1.7.0** — 1.9.0 is broken headless) → `pcbnew.ImportSpecctraSES` → real
routed copper. This produces genuine tracks/vias `kicad-cli` can DRC, identical in format to GUI routing.

| Function | What it does |
|---|---|
| `ensure_jar(path=None)` | Resolve the FR jar: arg → `$CEC_FREEROUTING_JAR` → `/tmp/fr_1.7.0.jar` → `~/.cache/cec/…` → download the pinned release. |
| `export_dsn(board, dsn)` | `ExportSpecctraDSN(board, dsn)` (headless 2-arg form). |
| `run_freerouting(dsn, ses, *, passes, opt_time, threads, …)` | `xvfb-run java -jar <jar> -de … -do … -mp … -oit …`, **from a `/tmp` workdir** so FR's `logs/` never lands in the repo. Verifies the SES exists+non-empty. |
| `import_ses(board, ses, out, *, fill_zones=True, fix_annular=True, power_pours=())` | `ImportSpecctraSES` + (lay `power_pours`) + (fix thin-annular vias) + **FILL zones** + `SaveBoard`. Fill is essential — SES import lays tracks/vias but never fills pours (only the real `ZONE_FILLER` does); without it every plane via reads `via_dangling` and every plane pad `unconnected` (EPS: DRC 99→53, unconn 71→2). |
| `add_power_pours(board, pours, *, fill=False)` | Lay **additive same-net** copper pours on an ALREADY-ROUTED board (high-current 12V). Laid AFTER the route, a same-net pour can only *add* copper — it can't strand the Kelvin sense that shares the net. (Pour-THEN-route DOES strand it: the pour reshapes FR's global solution. Pour-AFTER-route is the fix.) |
| `derive_power_pours(board, *, margin=1.0, …)` | Auto-find the pour rects from geometry: bbox of each cable net's THT-connector + **2-pad-shunt** pads (INA sense pads excluded, so HI/LO meet only through the shunt). General across the EPS/PCIe interposer family; self-gating no-op on boards without such nets. |
| `normalize_via_annular(board, *, min_annular=0.10, …)` | Fix Freerouting's **thin-annular vias** (FR ignores netclass via sizes) by **shrinking the drill** (copper unchanged → no new clearance; blanket via-enlarge made it worse). EPS: 49 fixed, DRC 53→4. |
| `bake_hints(board, out, *, keepouts=…)` | Add **rule-area keep-out zones** for the vital areas (12V columns, Kelvin windows) — they export into the DSN, so Freerouting *routes around them*. |
| `route_once(board, out, *, hints, power_pours=(), passes, …) → Candidate` | One full pipeline: hints→DSN→FR→SES→(pours+annular-fix+fill)→board. Never raises on a routing failure (returns `Candidate(ok=False, err=…)`). |
| `generate_batch(board, hints, seeds, *, power_pours=(), params, …) → [Candidate]` | One candidate per seed, **in parallel** (`ProcessPoolExecutor`; only strings/dicts cross the boundary, each worker `LoadBoard`s itself). `params` varies effort per seed (FR 1.7.0 has no seed flag → variation is `passes`/`opt_time`/`threads`). |

> **Why Freerouting, not hand-routing the spine?** A single `cec_route` pass collided at **343 structural
> DRC** on the dense EPS spine; the same board through Freerouting (no rules/keep-outs yet) came back at
> **34** — the real autorouter decisively beats single-pass scripting on the crossing nets. The keep-outs +
> netclass rules + the scorer's hard gates are what turn "34, partial" into an accept/repair decision.

## Tier — `cec_score.py`: metrics + HARD GATES

Scores a routed board and applies **non-negotiable safety gates** — a candidate is rejected outright if a
gate fails, *regardless* of how good its other metrics are.

- **`Rules.from_board(board)`** derives, by net-name convention: **Kelvin pairs** (`*_HI`/`*_LO`, the shunt
  sense), **diff pairs** (`*_P`/`*_N`, e.g. USB), **12V nets** (`12V`/`SENSEC*_HI`). Override explicitly when
  a board breaks convention.
- **`score(board, rules) → Metrics`**: `drc` (structural only — same cosmetic filter as `cec_route.verify`),
  `unconnected`, `length`, `vias`, `tracks`, **`kelvin_ok`** (gate), **`diffpair_ok`** (gate), `cu12v`,
  `balance` (F/B copper symmetry), `gates_pass`, and a `detail` dict (per-net breakdown + gate reasons → the
  decision log). A pair "passes" only if **both** members are routed (≥1 track) **and** carry 0 unconnected
  ratlines.
- **`gate(m, rules) → (passed, reasons)`**: human-readable reason per failing gate.
- **`objective(m, weights) → float`** (lower = better): ranks *gate-passing* candidates — weighted penalty on
  DRC, unconnected, length, vias, with a balance reward. `DEFAULT_WEIGHTS` exported.

## Tier — `cec_router.py`: the `route()` orchestration framework

```python
import cec_router as cr, cec_score
spec = cr.Spec(board="…/eps8pin-module.kicad_pcb", out="/tmp/eps-routed.kicad_pcb",
               rules=cec_score.Rules.from_board(board), seeds=(0,1), Kmax=2, max_iters=4)
final, log = cr.route(spec.board, spec)        # deterministic plane runs autonomously
log.to_json("decision-log.json")               # reproducible record of every decision
```

`route()` runs the loop from the architecture's pseudocode:

```
rules = spec_to_dru(spec)                 # netclasses + .kicad_dru (cec_pcb)
plan  = planner(board0, spec)             # regions + seam contracts  (Opus tier)
for region in plan.regions:               # per-region repair loop
    while True:
        cands  = cec_fr.generate_batch(region.board, hints=region.hints, seeds=…)
        scored = rank(cec_score.score(c) for c in cands)      # gate-passing first, then objective
        v      = manager(region, scored)                       # accept | repair      (Sonnet tier)
        if v.accept and best.gates_pass: routed[region] = best; break
        if K >= Kmax: apply_edit(state, escalator(region))     # structural re-plan   (Opus tier), K=0
        else:         apply_edit(state, worker(region, v))     # cheap param/hint edit (Haiku tier), K+=1
merged  = serial_merge(board0, routed, contracts)              # seam reconcile (owner routes each crossing net)
final   = write_once(merged → spec.out)                        # one-shot guard at the write boundary
verdict = independent_drc(final, rules)                        # an INDEPENDENT DRC verdict on the result
return final, DecisionLog                                      # JSON, replayable
```

- **`spec_to_dru(spec)`** writes the board's netclasses + `.kicad_dru` (via `cec_pcb`), so the candidates *and*
  the verifying DRC see the same electrical rules.
- **`apply_edit(state, edit)`** applies a structured edit: `fr_params` (more passes/opt), `keepout`/`drop_keepout`
  (reserve/free a vital area), `seeds`, or `place` (move/rotate a footprint — **placement is sanctioned**, this
  never lays a track; it goes through `pcbnew`).
- **`serial_merge`** composites each region's *owned-net* copper onto the floorplan, honouring **seam contracts**
  (a crossing net is taken from its owner region only, so the seam meets once). A single `all` region → its
  candidate *is* the merged board.
- **`DecisionLog`** records, per iteration: the candidates + their metrics, which was chosen, the verdict + tier,
  the edit applied. `to_json()` → replay the run.

### The control tiers (how the LLM plugs in)

The four control-tier callables — `planner` / `manager` / `worker` / `escalator` — **default to deterministic
policies**, so the whole framework runs **end-to-end with no LLM** (reproducible + testable; the common case,
since most decisions are mechanical "the gates pass → accept" or "bump effort → repair"). The **tiered LLM
realisation** swaps any slot for `make_subagent_policy(decide_fn)`: the orchestrator (Claude itself, the **Opus**
tier) plans the regions and **spawns the appropriate-tier sub-agent** for the harder judgements —

| Tier | Slot | Job |
|---|---|---|
| **Opus** (the orchestrator) | `planner`, `escalator` | Partition the board into regions + seam contracts; after `Kmax` stalls, a *structural* re-plan (re-place a part, split the region, re-spec a seam). |
| **Sonnet** | `manager` | Per-region judge: read the best candidate's metrics + snags → `accept` \| `repair` \| (let the loop escalate). |
| **Haiku** | `worker` | Cheap, high-volume edits during a repair: a targeted keep-out or a param nudge from the snag text. |

The framework stays identical — only the *source of judgement* changes — which is what keeps the run auditable
and the deterministic plane independently verifiable. The default policies are the floor; the sub-agents only
take over a decision when a board actually needs judgement the heuristics can't supply.

### Running it

```bash
python3 scripts/cec_fr.py        # Tier-0 self-test: routes 2 EPS candidates via real Freerouting
python3 scripts/cec_score.py     # scorer self-test: gates a routed vs an unrouted board
python3 scripts/cec_router.py    # end-to-end demo on EPS (deterministic plane, real FR + scoring)
```

Dependency: a Freerouting **1.7.0** jar (`ensure_jar()` downloads the pinned release if it isn't already at
`$CEC_FREEROUTING_JAR`, the OS temp dir, or `~/.cache/cec/`). The jar is **not** vendored (a 4.7 MB binary doesn't
belong in the board repo); the version is pinned in `cec_fr.FR_VERSION`.

**Cross-platform** (the compute plane runs anywhere KiCad + Java do — see `docs/self-hosted-router.md`):
`cec_fr._fr_command()` is platform-aware — on **headless Linux** it wraps Freerouting in `xvfb-run`; on
**Windows/macOS** (and Linux with `$DISPLAY`) it runs `java` directly (no xvfb — Java uses the native display).
All scratch dirs use the OS temp dir (`tempfile.gettempdir()`), never a hardcoded `/tmp`. The worker pool uses the
**`spawn`** start method (required on Windows; also the fork-safety fix on Linux). On **Windows**, `pcbnew` imports
only from KiCad's bundled Python, so use the launcher **`scripts\route.ps1`** (it finds KiCad's `python.exe`,
`kicad-cli`, and `java` for you — no PATH setup); on Linux/macOS run `python3 scripts/cec_router.py` directly.
