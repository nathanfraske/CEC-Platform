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

## Full-load capacitor-tree completion

`cec_force_current.py propose --include-bypass-terminals` optionally includes
populated, native two-land surface capacitors between the requested rail and
the explicit return net in the additive power tree. It retains the original
source/sink current contract, uses the unchanged full aggregate current and
project width on every new segment, and keeps measurement/control taps out of
this capacitor-terminal scope. It is not permission for a neckdown, via
capacity assumption, smaller branch-current estimate, or capacitor/board
release qualification.

The saved-family repair dispatcher accepts the boolean option
`include_bypass_terminals`; its independent receiver re-derives the capacitor
inventory and rated graph from the actual saved candidate. A primary-only
qualified diagnosis cannot accept an incomplete capacitor tree or no-op.
The mode is opt-in: existing force-only behavior and immutable-net refusals
stay unchanged. Completing an incomplete prelaid frozen prefix also requires
the separate `--complete-frozen-prefix` permission and exact primitive and
sidecar preservation. A refused partial child is construction evidence, not a
routed-board admission.

## Native body and explicit owner-reach reservations

`cec_assembly_envelope.footprint_planar_envelope` keeps a missing courtyard
from making a component invisible. It reports the native courtyard or a
conservative, explicitly identified fabrication-graphic envelope; placement
callers may include actual facing lands in that fallback. Missing body
graphics fail closed. A fallback is not a newly qualified library courtyard.

`same_net_terminal_gap_mm` measures real copper-edge distance to an explicitly
bound, same-net owner pad bank. It does not guess bypass ownership, acceptable
inductance or current sharing. A reseating caller can bound the saved gap by
the original gap while retaining native body, copper, barrel and mating checks.
Context-packing refusal witnesses include the trial translation and both
actual posed bounds; diagnostics never relax the collision model or grant
admission to an incomplete cell.

## Explicit displaced reservoir source branches

`cec_explicit_shunt_leaf.plan_supply` takes exact native support and owner-pad
UUIDs plus an explicit return net. It validates a fitted two-land SMD capacitor,
the manufacturer's actual input/output role and complete multi-land terminal
bank. It does not assign the capacitor to the nearest IC or require that an
already-displaced reservoir be inside the normal bypass-assignment radius.

The shared native leaf walker inventories only the exclusive thin old feed up
to its first stationary native junction. Shared forks, grouped/wide copper,
interior taps and all barrels stay fixed. `receive_source_plan` independently
re-derives source ownership and the unchanged full-rail current width before
any cut. An undersized old feed is recorded as debt, never certified or reused
at its old width. The packet cannot be sent to measurement-leaf routing: a
complete separately rated replacement, all original partition restorations,
new placement/power receipts and saved-board receiving remain mandatory.
This is an opt-in reconstruction primitive, not automatic routing admission.

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
- **Antenna keepout:** disable the RF rule-area policy or select a reviewed body-only
  footprint when wireless is unused. Legacy `drop_keepout` arguments do not shrink the
  physical courtyard: padless substrate remains a real component body. Copper may be
  allowed under an unused antenna without allowing another component inside the module.
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

Round-trips a board through the **real autorouter**: `pcbnew.ExportSpecctraDSN` → Freerouting (headless)
→ `pcbnew.ImportSpecctraSES` → real routed copper. This produces genuine tracks/vias `kicad-cli` can DRC,
identical in format to GUI routing.

**Version-parametric + hash-pinned (FR-01):** the active release resolves from `$CEC_FR_VERSION`
(module default in `cec_fr.FR_VERSION`; the ledger manifest reads it, so a version change is
automatically an AM-03 epoch boundary). Pinned releases live in `FR_RELEASES` with sha256 pins —
a hash mismatch on a conventional cache path or fresh download is a hard error. **1.7.0** runs
`xvfb-run java -jar` (Java 17+; 1.9.0 was broken headless). **2.2.4** is compiled for **Java 25**;
on an older JVM (the routing container has 21) `cec_fr` automatically falls back to the official
hash-pinned jpackage **app-image** (bundled JRE 25, Linux), and 2.x runs TRUE headless
(`--gui.enabled=false`, no xvfb) with analytics off (`-da`) and per-run `--user_data_path`.

| Function | What it does |
|---|---|
| `ensure_jar(path=None, version=None)` | Resolve the FR jar for a release: arg → `$CEC_FREEROUTING_JAR` (explicit → trusted, hash logged) → `/tmp/fr_<v>.jar` → `~/.cache/cec/…` (conventional → **pin-verified**) → download + pin-verify. |
| `ensure_appimage(version=None)` | Resolve (download+extract+verify) the official Linux app-image launcher for releases needing a newer JRE than PATH `java`. |
| `export_dsn(board, dsn)` | `ExportSpecctraDSN(board, dsn)` (headless 2-arg form). |
| `run_freerouting(dsn, ses, *, passes, opt_time, threads, …)` | `xvfb-run java -jar <jar> -de … -do … -mp … -oit …`, **from a `/tmp` workdir** so FR's `logs/` never lands in the repo. Verifies the SES exists+non-empty. |
| `import_ses(board, ses, out, *, fill_zones=True, fix_annular=True, power_pours=())` | `ImportSpecctraSES` + (lay `power_pours`) + (fix thin-annular vias) + **FILL zones** + `SaveBoard`. Fill is essential — SES import lays tracks/vias but never fills pours (only the real `ZONE_FILLER` does); without it every plane via reads `via_dangling` and every plane pad `unconnected` (EPS: DRC 99→53, unconn 71→2). |
| `add_power_pours(board, pours, *, fill=False)` | Lay **additive same-net** copper pours on an ALREADY-ROUTED board (high-current 12V). Laid AFTER the route, a same-net pour can only *add* copper — it can't strand the Kelvin sense that shares the net. (Pour-THEN-route DOES strand it: the pour reshapes FR's global solution. Pour-AFTER-route is the fix.) |
| `derive_power_pours(board, *, margin=1.0, …)` | Auto-find the pour rects from geometry: bbox of each cable net's THT-connector + **2-pad-shunt** pads (INA sense pads excluded, so HI/LO meet only through the shunt). General across the EPS/PCIe interposer family; self-gating no-op on boards without such nets. |
| `normalize_via_annular(board, *, min_annular=0.10, …)` | Fix Freerouting's **thin-annular vias** (FR ignores netclass via sizes) by **shrinking the drill** (copper unchanged → no new clearance; blanket via-enlarge made it worse). EPS: 49 fixed, DRC 53→4. |
| `bake_hints(board, out, *, keepouts=…)` | Add **rule-area keep-out zones** for the vital areas (12V columns, Kelvin windows) — they export into the DSN, so Freerouting *routes around them*. |
| `route_once(board, out, *, hints, power_pours=(), passes, …) → Candidate` | One full pipeline: hints→DSN→FR→SES→(pours+annular-fix+fill)→board. Never raises on a routing failure (returns `Candidate(ok=False, err=…)`). |
| `generate_batch(board, hints, seeds, *, power_pours=(), params, …) → [Candidate]` | One candidate per seed, **in parallel** (`ProcessPoolExecutor`; only strings/dicts cross the boundary, each worker `LoadBoard`s itself). `params` varies effort per seed (FR has no seed flag → variation is `passes`/`opt_time`/`threads`; NOTE 2.x documents `-oit` as the optimizer improvement threshold in **percent**, not a time). |

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

Dependency: the pinned Freerouting release (`ensure_jar()` downloads + sha256-verifies it if it isn't already at
`$CEC_FREEROUTING_JAR`, the OS temp dir, or `~/.cache/cec/`). The artifacts are **not** vendored in-repo (multi-MB
binaries don't belong in the board repo); version + sha256 pins live in `cec_fr.FR_VERSION` / `cec_fr.FR_RELEASES`,
overridable per-run via `$CEC_FR_VERSION` (each version change is an AM-03 epoch event in the ledger manifest).

**Cross-platform** (the compute plane runs anywhere KiCad + Java do — see `docs/self-hosted-router.md`):
`cec_fr._fr_command()` is platform-aware — on **headless Linux** it wraps Freerouting in `xvfb-run`; on
**Windows/macOS** (and Linux with `$DISPLAY`) it runs `java` directly (no xvfb — Java uses the native display).
All scratch dirs use the OS temp dir (`tempfile.gettempdir()`), never a hardcoded `/tmp`. The worker pool uses the
**`spawn`** start method (required on Windows; also the fork-safety fix on Linux). On **Windows**, `pcbnew` imports
only from KiCad's bundled Python, so use the launcher **`scripts\route.ps1`** (it finds KiCad's `python.exe`,
`kicad-cli`, and `java` for you — no PATH setup); on Linux/macOS run `python3 scripts/cec_router.py` directly.

## Native tied-control access and current-role receiving

`cec_tied_control_access.py` constructs a bounded, additive enable connection only
when `cec_device_power_roles` positively identifies the manufacturer, package,
pin roles and existing EN-to-IN net assignment. Its target is the exact input's
**native retained component**, not an arbitrary nearby island of the same net.
Planar and qualified local cross-layer candidates share a finite lease; the
independent receiver reconstructs source capture sites and checks every new
item, native connectivity, original partitions, route craft, field coupling and
current debt. Existing source copper, placements, pours and outlines remain intact.

`cec_control_current_branch.py` separates an exclusive local control leaf from
the shared rail's aggregate width requirement. Removing all such leaves must
preserve **every other same-net land partition**; the retained boundary must
already reach the selected device input. Package ambiguity, current-terminal
ownership, downstream loads, unknown source authority, unqualified transitions,
foreign group ownership, process-floor violations or incomplete native proofs
grant no exemption. The shared power path keeps its original current contract.
No typical datasheet current is substituted for a guaranteed maximum, and this
classification does not qualify the barrel, electrical behavior or fab release.

Regression fixtures cover cardinal rotations, flipped components, planar and
two-transition capture, unrelated same-net islands, aggregate/distributed source
authority, collective partition cuts and a downstream load that must retain its
power-width obligation. Private board trials still require full native DRC,
matched-stack checks and unchanged cross-board controls before review selection.

## Native plated supply endpoints and current-prefix replay

The local supply constructor reuses an actual plated through-hole pad as a
layer-transition contact when its drill and native copper mask span the enabled
stack. It does not create a redundant dogbone/barrel beside that contact. NPTH,
surface-only, undrilled and partial-stack lands cannot grant this access. The
current-sized route and all native foreign-copper, hole and locality guards remain
mandatory. Reuse does not qualify the existing connector barrel's ampacity.

For explicitly enabled additive endpoint receiving, a narrow supply-pin prefix
can equal a small project class while being below the larger executable current
floor. The receiver rederives that floor from an explicit design identity and
requires the same manufacturer-positive supply-pin, native full-width throat,
bounded-length and unbranched topology used by current checking. Unknown current
authority, aggregate force domains, arbitrary thin copper and group labels alone
are refused; the shared rail's current contract is not changed. Ordinary signal
and whole-current supply construction remain distinct scopes.

## Buffered digital GPIO semantics

A two-terminal native net from an exactly selected digital-buffer output to a
manufacturer-known scalar GPIO need not be an analog pickup merely because its
name contains `SENSE`. The supported output witness currently requires the
selected SN74LVC1G17 DBV MPN, matching SOT-23-5 footprint and complete five-land
pin inventory; the table comes from the [TI pin functions](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf).
The existing scalar GPIO witness uses the [Espressif module pin table](https://documentation.espressif.com/esp32-c6-mini-1_mini-1u_datasheet_en.pdf).
No net name, reference or coordinate selects this rule. Extra loads, unknown or
contradictory packages, drilled lands, DNP parts and pour ownership refuse it.
Kelvin, pair, USB, clock, power and specialized netclass exclusions still apply;
field admission still treats the named signal as sensitive. This is proposal
classification, not voltage, edge-rate, firmware-direction or release approval.

The source-bound 2026-10-10 trial retained the split/interleaved power collector
and both outlines, and used no additional drilled transitions. Exact native
receiving reduced ATX opens from 16 to 14 and Hub opens from 44 to 43, with no new
native or field faults. The focused current-code replay passed 1,350 tests;
archived PCIe2 and historical Hub controls remained unchanged. This is not an
all-repository green-test claim: eight existing decoupler/current-test failures
were reproduced in a read-only ablation without the new PTH reuse, recorded in
`build/plated-reuse-existing-cell-test-causal-receiving-20261010-dyn.json`.
The candidates retain electrical, current/thermal, DRC and release debt and are
not fab-ready. The saved additive-chain composition tool replays geometry and
lineage, rather than pretending historical routing was regenerated; each composed
candidate still needs fresh whole-chain native, current, field and stack checks.

## Source-bound contour motion and joint text layout

`cec_owned_contour_refresh` now requires the actual immutable source board in
both `materialize(..., source=...)` and `receive(..., source=...)`. Exact source
track rows and the whole source geometry binding are replayed independently.
An outline rounded onto a contour grid cannot establish the original endpoint
coordinates; rehashing a proposal is not source evidence, even for a 1 nm edit.

`cec_owned_pad_bank_refresh` derives a small chamfered landing from a complete
native source-pad/lead inventory after an externally received placement move.
It keeps source dimensions, ownership, solid connection and clearance settings.
Retaining the leads does **not** preserve the effective width of the old pour:
apparently excess area may be electrically necessary. A pad-only cover or a
cover extending over the retained leads is geometric construction only. Any
retired source area requires fresh saved-board current-debt receiving, clipped
Kelvin evidence and matched-stack checking before selection. Geometry/DRC alone
must not admit it, and no parallel-current division is inferred.

`cec_future_power_reservations` protects future whole-source routing corridors
while a private repair cohort is reconstructed. Widths come from complete
native current domains. Reservations are temporary obstacles, not copper or
capacity: remove them before fill, save, DRC, FEM or receiving, and assert their
UUIDs are absent. They neither authorize a route nor qualify a new barrel.

`cec_support_field_reflow.construct_changed_components` keeps independent text
regions out of a shared eight-owner budget while solving neighboring owners
jointly. It offers bounded, diverse backtracking and native glyph/mask collision
checks without changing strings, fonts, thickness, visibility or layers.
Non-silkscreen values remain unchanged. Failed transactions restore copied
scalar angles and positions, not mutable native angle proxies. The existing
single-choice API remains the default; native saved-board DRC still receives
every result. These operators are board/refdes/coordinate independent; caller
packets select finite native objects and never constitute admission authority.

### SMD cohort transport and frozen-priority preflight

`cec_smd_macro_transport.apply(source, candidate, ...)` is a provisional,
translation-default adapter for source-bound SMD placement proposals. It carries
actual pad-owned POFV barrels and their direct dogbones with their owners,
preserving all barrel/track dimensions, identities and process groups. It
re-proves both source and destination local process ownership. It cannot
authorize an arbitrary grouped route, THT/mating change or a new barrel. An
explicit ordinary free-barrel proposal also needs positive source typing and
all real incident endpoint contacts. Boundary seeds are mandatory rewrites,
not saved physical routes or permission to thin power copper.

Opt-in `allow_cardinal_rotations=True` permits exact quarter-turn poses. Native
cloned source lands provide the geometry expectation; each actual land and
owned barrel trajectory stays within the explicit motion bound. Dogbones and
barrels follow the same rigid owner transform, including on back-side owners.
External boundary leads still require reconstruction and independent native
partition/clearance receiving. The option does not seize grouped routes or
authorize a new via. Unrelated component, pad, factory and group identity must
remain unchanged.

Run `cec_macro_priority_preflight.inspect` before boundary reconstruction. The
source's board-design-basis current contracts and existing locked native pours
define priority copper. New pad/barrel seats are screened on **every enabled
copper face** against actual source material. A seat that drills an inner
power bus is refused early; the pipeline must propose another seat or invoke
a separately owned, fully current-received power transaction. Silkscreen and
fabrication text must not expand the electrical motion audit window. Full
saved-board DRC, retained partitions, current, Kelvin, coupling, stack and
outline checks still own admission; neither adapter grants fabrication release.

The separate opt-in `extend_owned_local_power_escapes=True` admits only tiny
extensions for proposal screening: a re-proved, uniquely contained native POFV
owner moves at most 1 mm, and its ungrouped escape retains its exact width and
**every original swept-disk copper point**. Exact integer collinearity and
interval containment establish that proof without approximating round caps.
A shortened, shifted, re-netted or thinned strip is refused. The private caller
must perform fresh saved-board whole-source current-debt receiving before
selecting any such result. This is not permission to move a main bus, rework a
pour, infer parallel current sharing, or relax factory/clearance/Kelvin gates.

### Existing ordinary body-tee preparation

`cec_native_body_tee_split` exposes an existing via-to-track-body contact as two
collinear native edges. It permits only positively typed ordinary nets and
ungrouped canonical tracks, with an exact interior integer projection and a
real native contact. Equal-width capsule union preserves all original copper;
the via, footprints, pours, groups, fabrication profile and track width remain
unchanged. This grants no authority to move a via or accept a later route.

Saved receiving rebuilds the split independently from the original source,
compares the complete native document and sidecars, and checks every retained
source partition. A body-tee with a fractional projection, protected owner,
different net, or no contact is refused. The subsequent pose/routing operation
still needs native DRC, source-current, coupling, Kelvin, stack and outline
receiving. Preparing graph edges does not qualify thermal or barrel capacity.

### Whole native branch/body reconstruction

`cec_native_branch_forest` proposes bounded whole-edge transactions before
endpoint-chain simplification. Body closure is explicit opt-in, uses actual
native copper contacts, and stops at width, owner, allocation and obstructed
terminal boundaries. It retains exact real terminal centers; an overlapping
two-port loop can become one canonical route. Mixed source locks require
explicit lock tightening and never become unlocked routes.

Only literal tracks already scheduled for reconstruction may be omitted from
the provisional obstacle snapshot. Pads, barrels, holes, artwork and reserved
power pours remain obstacles; the exclusions do not carry into saved DRC or
current receiving. The private caller must preserve all source partitions,
run whole-source current nonregression, and receive Kelvin, coupling, mating,
outline and factory constraints before selecting a result. Source widths and
current contracts are unchanged; no barrel capacity or parallel sharing is
inferred. The SMD macro's optional `maximum_ordinary_vias` remains capped at
eight, defaults to four, and preserves every existing source/contact guard.

### Full-width cross-face bus access proposals

`cec_crossface_bus_frontier.native_frontier` snapshots the real native
foreign-copper inventory on every enabled face, using explicit caller-owned
outer-face widths and a complete, legal normal/front-inner-back proposal via.
Conservative polygonized free-space components propose transitions between
the two outer faces. Each representative transition centre must independently
pass the existing native all-face land, drill-field and edge guards. Inner
lands are never omitted or counted as current-carrying parallel branches.

This is a bounded search diagnostic, not a new routing or admission gate.
Its component graph can expose a useful cross-face chain or identify nearby
unjoined components and the actual native objects blocking their shortcut.
A negative result, exhausted budget or unsampled transition is NOT a no-path
proof. Positive components are not actual constructed tracks: complete native
octilinear legs, source-current capture, saved connectivity, current, Kelvin,
pair/reference, assembly and fabrication receiving remain mandatory. The
geometry never authorizes moving a source pin, deleting a via, narrowing a
bus, dividing current by layer count or accepting unknown qualification.

`tests/test_crossface_bus_frontier.py` covers rotated/reflected two-transition
chains, exact boolean native callbacks, bounded/expired/invalid requests,
all six native padstack faces, immutable source geometry and factory floors.

### Optional saved-source finishing stages

`cec_native_keeper_extension_stage.py` offers a bounded automatic portfolio
for an existing, actually contacting purposeful power zone. It preserves all
original track strokes, old filled copper, source process settings and source
locks. `cec_native_keeper_extension_receiving.py` independently replans and
replays the entire saved transaction from its original parent, including the
GND-only refill. The explicit `retain_existing_keeper_lock` policy keeps an
incumbent zone's own lock independent of retained tracks' locks; it never
unlocks either. Ambiguous owners, foreign copper and unsupported holed
corridors still refuse. This cannot narrow a bus or grant parallel ampacity.

The stage first screens up to `--max-screen-requests` actual source scopes
(default 128, maximum 256). Only scopes with exactly one actual filled native
keeper spend the separate `--max-requests` construction budget. This avoids
starving later compatible regions behind a prefix of unowned requests. The
screen uses the planner's own native-contact oracle; it grants no editing or
electrical authority. All skipped, ambiguous and unexamined scopes remain
explicit in the receipt. Every selected scope is replanned against the current
saved board, so an earlier extension cannot silently resolve a later ownership
ambiguity. A bounded screen is not a global no-path or contour-clean verdict.

Its explicit `--retain-existing-keeper-group` mode can preserve an existing
keeper's native group independently of the source tracks' native groups.
It applies only to original-fill-preserving, non-retiring extensions, never
recompile or source cuts. The plan separately binds `group_uuid` and
`retained_source_group_uuid`; construction and saved receiving rederive both
from actual native objects. Group records, memberships and every source track
remain immutable. This is not permission to reparent, merge or unlock groups.

`cec_exact_overlap_stage.py` normalizes only saved overlapping straight tracks
with identical fabrication and ownership fields. Locks need the explicit
`--allow-locked-source` grant; grouped tracks are not eligible. Every trial
starts from the same original source, proves reciprocal exact capsule union
and immutable unrelated state, and runs uncapped native DRC. Newly exposed
warnings withdraw their implicated source scopes, never disappear into a
score threshold. The finite retry is capped at eight trials and 32 requests.

`--normalization exact_duplicates` discovers repeated equal-endpoint capsules
even at multi-way forks, which the two-leg turn audit intentionally does not
classify. It requests complete fabrication-identical duplicate components
within the same finite budget and stops before any collinear prefix trim.
Reciprocal saved-copper equivalence, unchanged native partitions, current
debt, fields and absolute clipped cuts still own admission. Fewer duplicate
objects is structural improvement, not shorter physical copper or a shorter
ground return. Native DRC observes disposable family copies because KiCad
can create editor-local `.kicad_prl` companions during a nominally read-only
check; the frozen source and received candidate must remain untouched.

Both command-line operators require `--source`, its actual
`--expected-source-sha256`, `--board-hint`, a qualified uncapped
`--reporting-build`, and a fresh `--out` directory. They require zero source
opens because these are optional finishing operations, not open-closure
substitutes. A bounded portfolio being `complete` does not mean all contour
or route-craft findings are clean. Independent native partitions, unchanged
current debt, fields and absolute clipped-copper evidence remain mandatory.

These are explicit composable pipeline operators, not new default monolithic
synthesis writers. Callers must still grade the saved result against the
right peer, assembly/factory/release gates, and original-source lineage.
Neither operator changes a production selector or declares a board fab-ready.

The keeper extension's optional `--retained-native-track-material` is narrower
than fill-only enclosure: only an original-fill-preserving, non-retiring
extension may include its exact unchanged real source tracks in the material
preservation union. Independent saved native fill replay is still required.
Partial fill-only coverage is reported separately; exposed caps remain visible
to the unchanged contour auditor. No ghost route, clearance/area tolerance,
additional capacity, current sharing or claim of all-contours-clean is granted.
The strict fill-only receiving default is unchanged.

The keeper operator's explicit `--allow-signed-native-keeper` can also extend
one compatible existing `CEC_NATIVE_POWER_CONTOUR_REGIONS` zone. Its actual
UUID, original name, process settings, lock, group, tracks and old filled
copper must remain exact. This is not permission to rename arbitrary pours,
retire owners, bridge holes, merge distinct owners or change current capacity.
`--request-scope local_findings` requests bounded actual one/two-track native
capsule/elbow scopes when a whole component is obstructed; the default is
still `components`. Saved source replay and all current/field/DRC/absolute-cut
receivers remain mandatory, and only a strict actual contour improvement is
accepted.

`cec_source_solid_keeper_stage.py` uses the same non-retiring, source-fill-
preserving receiver for literal existing solid owners, independent of their
generator name. The lower-level keeper API can select an exact contacting
`source_zone_uuid` only with explicit source-solid retention. It derives the
priority from that immutable source owner (including nonzero priorities),
never from a requested new priority; equal-priority overlap still requires
consolidation. Clearance, feature floor, solid connection, source tracks,
positive old fill, lock/group and stronger native voids remain exact.

The explicit `contour_max_jog_nm` policy adds only bounded canonical corner
closures. Its native obstacle checks use the same declared signed-hole policy
in planning, materialization and saved-source replay. Actual foreign fill and
clearance still prevent closure; unsupported or changed geometry still
refuses. No source width, current allocation, clearance, layer role or release
gate is relaxed. A zero coarse contour count does not establish that finer
contours, signal bends, ground returns or fabrication qualification are done.

For that explicit retained-owner mode, native filled-polygon identities can
retain KiCad's literal hole-bridge vertices instead of rejecting their
representation. They are not simplified, buffered or ignored; every native
foreign-copper clearance check still runs. The optional
`--source-diagonal-quantum-nm 1` covers existing nominal diagonals whose integer
axis deltas differ by one nanometre, without moving endpoints or changing
widths. New routes and authored cover edges still require exact 0/45/90
geometry. Every such input's entire capsule must be covered by actual saved
fills, even if retained-material mode is also enabled. Default is zero; this
does not grant a clearance, copper-loss, current or fabrication tolerance.

`cec_native_ordinary_tree` supplies bounded, read-only multi-port branch
proposals over actual retained native components. Existing plated barrels and
alternate copper layers can join ports without new routes. NPTH holes and
planning disks cannot. The constructor must independently verify ordinary-net
eligibility, its complete literal cut, every saved boundary/partition, native
DRC, current debt, fields and absolute cuts. A proposed spanning tree is not an
admitted route or source-removal authority.

The power contour audit can explicitly include long terminal caps with
`audit_board(..., include_terminal_caps=True)`. The old aspect-ratio-limited
audit is still its default and cannot establish that all bus ends are clean.
The expanded audit checks literal source cap geometry, same-face native pads,
real forward continuations and canonical purposeful saved fills. A bbox,
opposite-layer copper, a named-but-unfilled zone or coincident duplicate track
cannot hide a terminal. Pad visibility is only style evidence, never barrel,
contact, current or fabrication qualification. Deadlines remain incomplete.

`cec_native_keeper_extension_stage.py --request-scope terminal_caps` feeds
only these geometry-derived requests to the existing keeper operator, but
grades the complete expanded contour inventory before and after each change.
It retains every source track, width, old keeper fill and ownership/process
record. Native DRC and full saved current/field/partition/clipped-cut receiving
remain mandatory; no current division, source trimming or filler-zone overlap
is authorized by this request scope.

Native ordinary preclear also retains literal face obligations at source cut
boundaries. An unchanged trace tip with no other same-face contact, or a via
losing its old face contact, cannot be replaced by a distant point on its
globally connected component. Search menus and complete operation predicates
enforce exact new centreline incidence on that face; their cache keys include
the current boundary requirements. Existing PTH lands retain their genuine
plated-face alternatives. Fine interior grids are explicit during refined
long-path searches; the existing deadlines and all saved receivers remain.

Use `cec_force_sense_evidence.native_copper_transform_inventory` to derive a
contact-comparison ledger from the real source and child boards. KiCad's
`GetTracks()` includes vias and arcs: via UUIDs must occur in the parent route
inventory as well as the via subset. The helper refuses undeclared identity
deltas and reused identities with changed kind/net. It grants no permission
for same-UUID geometry edits or any source cut; literal saved receiving and
fresh absolute evidence still decide acceptance. The comparator is unchanged.

`cec_contained_one_face_barrel_stage.py` diagnoses real uncapped native
`via_dangling` objects and tries at most eight exact-source retirements.
The separate `cec_contained_one_face_barrel_retirement` receiver requires
exactly one actual copper-contact face, including inner routing faces, and
the complete conservative via disk inside one retained native track, SMD
land or saved filled polygon. A bounding box, zone outline, another face,
surface bridge, neighboring barrel or unassigned copper cannot supply that
proof. Source lock/direct-group permissions are explicit; locked/nested
groups and typed dependency annotations remain protected. Only the selected
barrels and an independently replayed existing GND refill may change. Fresh
whole-source partitions, drilled-terminal graphs, unchanged current-debt,
field and absolute clipped-cut checks must pass, followed by uncapped native
DRC with no new faults or opens. Native observation uses private identical
families so KiCad cannot write a preferences cache into source authority.
This supplies no current-sharing, plated-barrel, thermal or release credit.

An explicit `--allow-leaf-cleanup` enables a compound source transaction,
not permission to chase arbitrary dangling power traces. Native source
proposals can include at most one exact short (at most 1 mm long and wide)
stem per barrel, touching the barrel axis at one end and retained full-width
track endpoints at the other. Its entire native body must be pad/zone-free,
with no foreign, interior-branch or unassigned-copper contact. A surviving
body, never the retired stem, must still contain the whole via disk. Source
stem locks and membership are independently checked; typed dependencies stay
protected. Coupled-pair members require their own receiver and cannot use
this compound shortcut. Only the complete barrel-plus-stem transaction can be received
against the original saved source. A standalone via removal that exposes a
new native dangling-track warning is rejected, never accepted as progress.
`--maximum-barrels` is an explicit finite work lease (1–8), not a rule waiver.

`cec_distributed_loop_retirement.plan(..., allow_source_inner_layers=True)`
explicitly extends the existing exact supply-loop cut to source-authorized
inner routing faces. Reference-plane cuts stay excluded. Every selected
stroke must meet that face's unchanged complete aggregate-load width floor;
the operation never divides load by the number of layers. Existing outer
cut permissions are not revoked merely because outer GND pours exist.
Actual saved terminal partitions, full-width same-face joins, drilled
graphs and literal replay remain mandatory. Default outer-only behavior is
unchanged. `cec_native_supply_tail_trim.propose` can suggest exact on-stroke
shortening at integral intersections with real retained full-width source
tracks; it cannot round a near-contact into a connection or authorize a cut.
When a private diagnostic exposes another old tail or unused barrel, expand
the bounded original-source scope and receive the complete transaction; do
not waive the new warning or promote the latest private prefix as a baseline.

For a persisted supply-loop proposal, call `rederive_saved_plan` on the
unchanged source board. Catalog tuples become JSON arrays during storage;
the helper reconstructs the complete fresh source plan, requires exact
canonical JSON equality and returns that new plan to the existing strict
receivers. It does not normalize changed numbers, margins, geometry, roles,
source bindings or extra fields, and does not itself admit a candidate.

`cec_rated_overlap_tail_stage.py` handles a distinct case from exact-union
normalization: two overlapped source strokes can conceal an obsolete common
end, so deleting the shorter one alone creates a native dangling warning.
The stage derives strict collinear coverage, then tries source-owned removal
AND exact on-stroke shortening to real retained full-width joins as one
transaction. Only a positive existing conservative aggregate-load contract
may own this cut; no net names, reference designators, guessed branch currents
or coordinates grant authority. Every accepted cumulative trial is rebuilt
and received against the same original source, with full-load terminal joins,
current/field/cut preservation and uncapped native DRC. A new warning is
rejected rather than hidden by an intermediate source or a weighted score.

Its explicit `--include-acute-excursions` mode applies the same full-load
receiving to a short source-owned acute corner excursion and exact on-stroke
trim of its partner. Geometry alone never authorizes the deletion. Default
overlap-only behavior and all specialized-net/source/current gates remain.

`cec_multi_keeper_contour_stage.py` handles actual source strokes touching
two or more compatible registered native contour owners. It compares every
serialized process setting, retains all source tracks and fills, and joins
the authored owners only along the actual source stroke envelopes. A new
overlay or arbitrary bounding rectangle is not consolidation. Disconnected
authored unions, group changes, mixed process/lock settings, foreign copper,
old-fill loss, and any new native DRC fault are refused. Independent receiving
replays the whole saved transaction and rechecks current debt, coupling and
absolute clipped cuts. Neither operation grants new parallel-layer current
capacity, thermal qualification or fabrication/release authority.

The multi-owner stage's explicit `--fill-policy source_preserving_regions`
retains each incumbent filled polygon as an exact positive native record,
including holes and island flags. New material is a feature-filtered, anchored
subset of an actual KiCad fill, clipped to bound stronger regional voids.
It cannot adopt floating islands, fill a protected void, replace a missing
source record with a rounded Boolean approximation, or fabricate copper from
a renderer. The independent whole saved replay regenerates the exact records;
native DRC, current/coupling and absolute clipped cuts still decide acceptance.
The default fresh-native-refill mode is unchanged. A later unowned global
refill is not allowed to silently discard this source-preserving ownership.
The additional explicit `--clip-native-additions` option intersects ONLY a
fresh native addition with the derived authored domain before feature and
anchor filtering. Zero spill is still mandatory; this is not a numerical
tolerance or permission to clip incumbent copper. Old producer plans without
the option retain their exact original construction and independent replay.
`--native-addition-inset-nm` may conservatively inset that NEW clipping mask
by 0 to 10 nm to avoid integer-intersection boundary slivers. It is not a
clearance change or a copper-loss tolerance: no incumbent point is moved,
zero added spill is still required, and all exact saved-source/current/cut
receiving remains mandatory. The default zero-inset producer is unchanged.

The shared `save_native_additions` emitter also calls
`cec_new_track_body_echo.compact` before saving. It can drop a NEW plain track
only when outward-native target geometry is completely covered by inward
retained original-track and fixed through-via lands. Subtracting the same
fixed holes preserves that physical subset relation. Original conductors,
barrels, grouped or mask-bearing tracks, and conditional via lands are never
retired. This prevents a new ground dogbone from doubling back over an old
wider return; saved native connectivity/current/field/cut receiving remains
mandatory and this constructor step has no admission or release authority.

The native ordinary-tree default work leases remain 32 source tracks and eight actual ports.
Explicit `maximum_source_tracks`/`maximum_ports` leases can bound construction
at up to 128 tracks and 16 ports. The ordinary saved receiver separately
accepts `max_retired_tracks` up to 128, still defaulting to 32. A larger lease
does not authorize power/pair/sense/ground cuts, grouped-source edits, changed
widths or poses, extra barrel authority, or lost native terminals. The same
exact source-minus-cut replay, complete surviving partitions, native DRC,
current/field and absolute-cut checks are required. These are finite compute
limits, not electrical design-rule changes.

`cec_native_ordinary_tree.construct` is an optional untrusted PRIVATE-board
constructor. It tries bounded actual cross-component port pairs, recomputes
native connectivity after every real branch, and includes explicit fine
interior search grids and maximal-run field-search pruning. An unavailable
nearest pair does not invalidate other bridges or prove global no-path.
The native component quotient also keeps each source via's actual face-contact
obligation: connectivity through another face cannot silently leave that
unchanged barrel dangling after the cut. Exact retained native face witnesses
are recomputed after each branch. Missing via contacts require a guarded real
branch, even if all ports already share a cross-layer component; an unchanged
PTH pad alone never creates this extra routing obligation.
Conservative cross-layer pruning can overconstrain a proposal; it grants no
shielding pass. Failure rolls back every proposed addition. Success never
cuts source copper or grants route admission: exact source subtraction,
uncapped native DRC, whole current/field/partition and absolute-cut receivers
still decide the saved candidate.

The signed native-contour receiver accepts an explicit `sense_timeout_s`
work lease in `(0, 60]` seconds (default remains 10). Source and candidate
both use that lease; partial or unbound evidence still refuses. This is an
algorithm budget, not the command polling interval or permission to skip
legs. A larger board must finish all its declared cut evidence before a
cosmetic contour can be received.

The overlap stage's optional `--retain-per-item-locks` separates only the
physical coverage comparison from editor lock bits. Every surviving source
UUID must keep its literal original lock fields. Width, layer, net, mask and
unknown fabrication fields still compare exactly; group ownership and the
explicit mutation lock grant remain separate requirements.

The overlap stage also exposes the existing `--overlap-policy retire_covered`
constructor: a wholly redundant straight track can be retired instead of
shortening its neighbor. The default is still `preserve_junctions`. Both
policies require the same reciprocal saved physical union, native DRC,
source-current/field/partition and absolute-cut receiving. The retirement
option cannot be combined with a different normalization mode. Newly exposed
dangling warnings remain failures; equal apparent copper or a lower issue
count never waives them.

The optional `--normalization strict_containment` mode can instead retire a
narrow straight track strictly inside one unchanged wider source track. It
proves rational whole-capsule coverage with a positive integer-nanometre
margin and independently subtracts native outward-old polygons from native
inward-survivor polygons. Every surviving UUID and all other serialized state
remain unchanged, including locks, masks, unknown fields, fills and widths.
No area tolerance, approximate endpoint coverage, inferred current sharing,
zone-as-capacity substitution or native-fill-margin change is permitted.
Discovery is untrusted and bounded; the saved receiver, complete native DRC,
surviving conductor partitions, current debt, fields and absolute clipped
cuts still own admission. The default remains equal-width exact overlap.

Saved-source local-via receiving can explicitly enable
`allow_source_track_body`: a direct SMD-owned subinterval of one existing
canonical source track may own a via on its interior. Exact lattice
projection, actual native contact, original reach and all existing process /
pad-overlap rules still apply. `allow_native_track_body` similarly enables a
direct-return observation only when actual native copper covers the complete
path. Neither option is a proximity, width, impedance or barrel-capacity
certificate. Constructor defaults remain endpoint-based; the new observation
must not silently change an in-pad-first placement/route strategy.

`cec_scalar_corner_stage.py` is an optional saved-source finishing operator
for ordinary-signal right-angle corners. It reuses the existing native
contact-preserving constructor and positive ordinary-net catalog; it does
not treat power, GND, pairs, sense, clocks or zone-owned nets as scalar
permission. Up to 16 requests / 32 original tracks are constructed in one
batch, with exact UUID retirement, unchanged fabrication fields, source lock
restoration, GND-only refill, uncapped native DRC and one whole-source
ordinary/current/field/absolute-Kelvin receiving transaction. Every retry
restarts from the same source and withdraws actual implicated scopes when a
new native fault appears. A fault with no source attribution refuses.

The CLI requires `--source`, `--expected-source-sha256`, `--board-hint`,
`--reporting-build`, and a fresh `--out`. Locked source permission is
explicit (`--allow-locked-source`); grouped source remains excluded. The
default minimum chamfer retreat is 50000 nm; `--minimum-chamfer-nm 20000`
permits an explicitly smaller *style* retreat without changing trace width,
clearance, fab geometry or a pad/via launch. Both cardinal and diagonal
90-degree corners use the same native geometry and contact guards.

The scheduler reports actual same-net/same-layer body tees separately, with
native conductor witnesses, rather than retrying them as cosmetic failures.
A matching bbox, another net/layer or an absent native contact grants no tee
exemption. Stage receipts include elapsed construction/native/independent
receiving times. `all_eligible_corner_requests_clean` is only the declared
ordinary/floor scope, not all special-net corners, trace craft, power
contours, electrical qualification or fabrication readiness. This stage does
not promote a selector or silently add another monolithic synthesis writer.

## Fixed-port pair miter refinement

`cec_pair_craft_reflow.py --operation fixed_port_miter` explicitly selects a
bounded source-derived three-edge 45/cardinal/45 operation. It grows an
invisible inner flat by an even integer length and removes half that length
from each diagonal axis, retaining both endpoints and the full source width.
The exact shortening is `growth * (sqrt(2) - 1)`; no rounded endpoint, added
drill, moved terminal, new current budget or length waiver is involved.

This is not permission to shorten one member of a perfectly matched pair.
Source physical preflight remains required, and the saved whole-bus receiver
must retain non-worsening skew, each member's continuous coupling deficit,
all three physical sampling contracts, references, source process fields,
native contacts, current, field, clipped-cut and uncapped DRC evidence. If
shortening would increase skew, the proposal remains refused. Selecting an
operation only bounds the search portfolio; it cannot bypass receiving.

`--operation balanced_fixed_miters` selects an atomic two-member version for
nearby same-face, same-axis native motifs. It requires at least one actual
invisible source flat and exposes all affected inner flats. Identical even
integer growth on both members gives exactly equal radical shortening, so
skew is algebraically unchanged at four fixed ports. The unchanged counterpart
may already have a visible, larger flat; it is not narrowed or given a new
width/current allocation. The source process is replayed separately for each
net. Full native clearance, contacts, coupling, references, current, fields,
absolute cuts and DRC remain mandatory; a joint geometry certificate alone
does not admit a route or qualify a pair.

## Same-drill reference-return land fallback

Endpoint-POFV paired routing now prefers its ordinary ground-return via,
then permits one smaller land only at the source board's absolute
diameter/annular-ring floor. `pair_return_via_geometry_candidates` clamps the
preferred drill to the board minimum and retains that exact drill throughout
the menu. It never changes an inherited via, a signal-via geometry, a rated
power-transfer array, the fabrication process or a current-capacity budget.

Each failed field is rolled back before the next geometry is attempted.
Both attempts share the original deadline and retain the same native
foreign-copper, drill-spacing, edge, per-member reach and reference-contact
guards. Preferred success or an already-covered transition adds no fallback
via. Receipts identify the actual geometry and all bounded attempts. The
saved whole-pair refill, DRC, coupling and reference checks still decide
whether the complete result can be accepted; a legal local return seat alone
is not a qualifying route or a fabrication-ready board.

`tests/test_pair_return_land_fallback.py` covers absolute floors, same-drill
invariance, partial/exception/deadline rollback and loaded native apertures
under rotation/reflection, including reference-contact, hole-spacing and
return-reach refusals. Real-board replay must also preserve immutable controls.

## Fine capsule contours and native hole-bridge obstacles

`cec_native_capsule_zone_stage.py --min-width-mm 0.5` explicitly extends the
contour inventory below its default 1 mm work floor. This changes selection
and progress measurements only. The original complete current domain,
per-face rated width, native clearance, source-capsule containment, field,
absolute-Kelvin and uncapped DRC checks still own every proposal. In
`--retain-source-tracks` mode, all original conductors remain literal native
objects; the new saved contour grants no additional current capacity.

Native filled polygons sometimes encode real holes with repeated bridge
vertices. The contour obstacle guard now accepts that encoding only after
the existing exact-edge decoder proves its topology and zero native copper
loss/spill on a private clone. It hashes the original representation and
never changes the source fill, calls make-valid/buffer, treats a hole as a
solid bounding box, or weakens clearance. Malformed/overlapping bridges and
exhausted proofs still refuse. Authored outlines retain their strict ring
guard. `tests/test_native_fill_contour_guard.py` covers transformed actual
native obstacles and full saved finer-contour transactions.

For compound fills, bridge validation is per declared positive native polygon,
not one concatenated edge inventory across all polygons. Separate source
contours can overlap or share edges without being malformed inside one ring.
The guard copies literal native chains, proves the copy unchanged (including
zero edges), and validates every component under one shared vertex/polygon
bound and deadline. It retains the complete original fill identity and runs
collision/clearance checks on that original compound fill. No source polygon
is deduplicated or ignored: a positive copper island inside a peer's hole is
still a real obstacle. `tests/test_compound_native_fill_guard.py` exercises
that distinction, malformed-component refusals and exact support receipts.

## Literal body-contact ports and retained ground-path sharing

`cec_native_track_partition.py` exposes an already existing same-net/face
track contact using equal-width, collinear fragments. Requests identify exact
source/peer UUIDs, integer contact points and source-lock permission. The
independent saved receiver reconstructs every fragment and proves the complete
source capsule union is unchanged. This role-neutral preparation creates no
physical routing improvement and grants no later copper-cut/current authority.

`cec_native_ground_span_reflow.plan(..., maximum_extra_nm=0,
reuse_retained_source=True)` can then replace an independently owned,
already-plane-redundant small surface GND span with a simple fixed-port path
that uses literal retained full-width tracks. Only uncovered collinear
intervals are emitted. The complete path must not grow, actual trace material
must decrease, and original process/contact/return/partition proofs remain
mandatory. Nearby copper, thinner tracks, zone fills and plated barrels never
substitute for a full-width surface interval. The default span contract is
unchanged; this is an explicit agent-construction API, not an enabled normal
coordinator hook or a fabrication qualification. Whole saved current, field,
uncapped native DRC, absolute Kelvin, mating and release checks remain required.

The transformed native and hostile saved-delta tests are
`tests/test_native_track_partition.py` and
`tests/test_retained_ground_span_reuse.py`. A metadata-only partition must
never be counted as a shorter physical return or new copper capacity.

## Load-rated supply-corner finishing

`cec_rated_supply_corner_finish.py` reuses the native contact-preserving miter
geometry without reclassifying a supply as ordinary. Its independent saved
owner requires an unchanged, positive, complete distributed-load contract,
the full layer-specific width and existing margin, then replays all saved
geometry/process fields and the separate rated-branch receiver. Main force
nets, groups, launches, plane routes, new barrels, poses and source-load edits
are excluded. Explicit source-inner-face and lock permissions do not relax
any current or clearance floor. Batches are bounded to 16 corners/32 source
tracks; unchanged corners and finite refusal evidence must not become silent
waivers or endless waves. Whole current, coupling, native DRC, Kelvin, mating
and release receiving still follow this construction API. This does not yet
enable a normal coordinator hook. Native tests are in
`tests/test_rated_supply_corner_finish.py`.

## Fixed-supply bypass return pivots

`cec_bypass_ground_pivot.py` owns a bounded 180-degree pivot of one positively
selected, manufacturer-modeled low-power bypass capacitor around its entire
unchanged native supply land. The existing owner-to-capacitor supply path
must survive, the actual ground return to an unchanged plane-connected
barrel must shorten, and only uncovered full-class surface GND intervals
are added. No hole, main bus, converter/bulk ownership, current budget or
ordinary-net reclassification is introduced. The receiver independently
reconstructs the complete saved board, rebinds only that literal ground-pad
identity, and compares all original native conductor partitions. Every
other component, original trace, plane and barrel remains unchanged.

`cec_pin1_marker_reseat.py` is a separate preparation for a small neighboring
package pin-1 silk triangle or circle. Only a bounded translation is owned;
shape, stroke, fill, orientation, package pose and unique nearest-pin-1
association survive. Actual native source and independently reconstructed
prospective pad-mask and silk geometry must both clear. This preparation
does not grant copper or placement authority. A whole-board native DRC
remains mandatory even when the electrical pivot preflight passes.

These are explicit source-bound construction APIs, not automatically enabled
coordinator stages or fabrication qualifications. Whole current, coupling,
uncapped native DRC, absolute Kelvin and actual matched-stack receiving are
still required. Transformed native and hostile saved-delta regressions are
`tests/test_bypass_ground_pivot.py` and `tests/test_pin1_marker_reseat.py`.

## Native pair terminal-lobe removal

`cec_pair_terminal_lobe.py` removes bounded, source-declared pair detours whose
two full-width ports fit inside the same literal native SMD pad. Every uncut
same-net contact must also remain inside that pad; bboxes, global plane
connectivity and rounded-corner proximity cannot grant removal. The receiver
reconstructs the whole saved subtraction, preserves every surviving native
conductor partition, checks complete pair connectivity, continuous coupling
and the existing physical metrics at three sample grids. No new copper,
barrel, pose, reference sheet or current budget is introduced. This is an
explicit agent-construction API; normal coordinator adoption and full-board
DRC/current/field/Kelvin/stack/release gates remain separate requirements.

The existing release oracle deliberately omits detour ratios below its
2 mm endpoint-MST span. Fresh pair diagnostics now declare that applicability
with the unrounded native span. Local metric receiving accepts N/A only when
both fresh source and candidate retain that exact authority; absent evidence,
changed thresholds, boundary mistakes and one-sided nulls still fail closed.
No detour or coupling limit is relaxed. Native and hostile-delta regressions
are `tests/test_pair_terminal_lobe.py` and
`tests/test_pair_detour_metric_applicability.py`.

## Retained Ground portals and literal track-entry shortcuts

The complete-cell follower frontier now includes bounded, supply-distance-aware
capacitor seats around actual saved through-Ground barrels. Those proposals
retain the existing 3.5 mm supply-assignment and 0.8 mm octilinear-return budgets;
they grant neither a new hole nor a fabrication exception. The live courtyard,
surface, process and complete-cell receivers still decide every seat.

`cec_retained_ground_barrel_clearance.clear` checks all enabled copper faces
using a conservative envelope of the actual existing circular lands. It does
not apply ordinary *new-hole* creation floors to a retained POFV barrel; the
caller must independently prove ordinary geometry or live local POFV ownership
with the proposed strokes present. Authored power-zone outlines remain the
default. Only a literal unchanged saved barrel can use its existing native
antipad, through the existing source-frozen-fill context. Every saved zone,
stack, profile and barrel identity must match; current foreign pads, tracks,
drills and copper graphics remain obstacles on every face. This does not allow
a new or relocated hole to perforate a bus.

`cec_ground_return_shortcut.plan` and `receive` optionally take
`target_track_uuid` as well as the existing reference-barrel UUID. The requested
path must end on the exact integer centreline of that actual same-face Ground
track, already connected to the source terminal and reference barrel. This
avoids duplicating the rest of an existing Ground trunk. An identified bounded
unbranched source departure is excluded: it needs reflow, not an added parallel
triangle. The saved receiver must independently prove a shorter whole return,
unchanged source conductors and partitions, and no worse trace craft; a short
local proposal is not proof of an improved complete return.

The local departure includes physically connected Ground siblings on the same
native package. Meeting another pin of that package is not a foreign-load
boundary. Both track-body and barrel targets on that departure are excluded;
a numerically shorter parallel triangle still requires actual local reflow,
not another additive chord.

Automatic Ground-shortcut discovery now considers these literal native track
entries alongside barrel centres. It funds both kinds fairly within the same
bounded target portfolio, excludes the source's unbranched departure, and
temporarily constructs each proposed path to measure the **whole** return
before offering it. Every temporary item is removed even if observation fails.
The emitted link length is not credited as the complete return length.

The stage visits up to three distinct source-bound cohorts when the longest
cohort offers no repair. Each discovery wave retains its independent ten-second
limit; an explicit finite cursor advances past already-observed qualified
terminals rather than restarting the same plateau. This is search coverage,
not a no-path certificate or any change to current/process/clearance policy.
Saved phase receipts retain the exact target-track UUID through independent
receiving, followed by unchanged whole-board current, field, native DRC and
clipped-copper checks. Original copper, holes, outlines and poses remain fixed.

The `--minimum-return-mm` option is a search floor, not an electrical pass
criterion. The default 3 mm search cannot inspect otherwise repairable shorter
returns. After a source-bound long-return portfolio plateaus, a finishing pass
may explicitly try lower finite floors (for example 1.5 mm, then 0.5 mm), with
the same candidate, cohort and deadline bounds. Do not repeatedly restart an
unchanged source at a floor that already produced no accepted offer. Preserve
that receipt and advance the finite portfolio instead; a no-offer result is
still not a global no-path or return-necessity proof. A successful shortcut
must report the original and saved complete return measurements, not merely
its new track length. Additive shortcuts do not claim removed copper length.

Track-entry construction is an explicit agent API, not a newly enabled normal
coordinator stage. Neither a lower witness counter nor a failed finite search
qualifies electrical performance, global shortest paths, necessity or release.
Whole current, field, uncapped native DRC, clipped Kelvin and matched-stack
receiving remain mandatory. Native transform/hostile-delta coverage is in
`tests/test_bypass_ground_portal_events.py`,
`tests/test_retained_ground_barrel_clearance.py`, and
`tests/test_ground_shortcut_native_track_entry.py`.

### Source-owned macro boundary compilation

`cec_cell_macro_requests.compile(source, poses, board_hint=...)` derives a
complete private SMD macro and its typed reconstruction demands. It does not
save a PCB or grant routing, placement, current or fabrication admission.
The original exact cell-cut plan remains separate from projected native ports.
Additional changed small edges must independently qualify as ordinary signals
or retain a complete existing full-current source contract. Ground trunks,
unknown/specialized nets, larger conductors and arbitrary groups gain no cut
permission from being in the way of a pose.

Physical source-owned barrels and their rigid native Ground dogbones travel
as complete process-qualified pickups. The contact frontier retains those
pickups instead of deleting their dogbones and then rejecting their now-bare
barrels. Shared-fork ports follow the exact retained native barrel identity;
an obsolete coordinate or a nearby same-net object is not a replacement port.
When a formerly retained edge becomes an explicit typed reconstruction edge,
its old demand is composed only at the exact same original pad endpoint.

`cec_cell_ground_cut_boundaries.requests` can receive explicit transported
source-barrel proofs for comparison identities. It independently re-proves
native dimensions, layers, groups, the same SMD owner and its exact cardinal
transform, together with any retained rigid pickup. This cannot authorize
moving a hole, weakening a factory floor or skipping a stationary fragment.
Every original partition, current/pair/field/Kelvin contract and actual stack
still needs independent saved-candidate receiving after complete construction.
Native front/back/cardinal, forged-port, lost-pickup, current-contract and
read-only complete-request coverage is in `tests/test_cell_macro_requests.py`.

Current-debt receiving does not turn a partial timed branch classification
into a complete new-copper fault inventory. An explicitly incomplete native
measurement, monitor, control or consumer classification remains unknown for
debt comparison, without lowering aggregate current/width requirements.
Comparing the exact same saved path/family uses one fresh complete snapshot
and an independent copy of its result; distinct saved paths still receive
two native evaluations even when their PCB bytes match. Source-family and
code identity are checked after receiving in either case. Tests are in
`tests/test_current_debt_snapshot_reuse.py`.

### Reserved-pour contact events and saved complete-cell reconstruction

`cec_reserved_pour_pose_events.propose` derives bounded cardinal translations
from the literal native reserved-zone contours on each actual pad face. A
filled antipad, misleading zone name or the zone's enclosing rectangle cannot
grant a seat. The contact frontier includes simultaneous surface and plated-
barrel events, and scores their independent remaining conflicts for ordering.
Every final offered pose still needs a fresh complete source plan and all
native pose/barrel predicates. An exhausted frontier is not a no-path proof.

`cec_complete_cell_receiving.receive` independently infers a saved owner/bypass
transaction from actual native motion and the original bypass assignments.
It replays the source-owned cuts and poses, receives exact additive copper and
native Ground refill, checks full unchanged current contracts and actual
local supply/return paths, and preserves every surviving original terminal
and copper-only partition plus all previously known short Ground returns.
This bounded operator does not permit new or transported barrels. It accepts
no caller-authored deletion list or guessed load. Whole-board native DRC,
current, field/pair, clipped Kelvin and the actual matched stack remain separate
mandatory gates; this receiver grants no fabrication or release authority.
Retained full-class Ground track bodies may satisfy a local return with no
new copper only after exact centreline interval, full native pad-entry disk,
barrel-axis web, live process/all-layer clearance and every declared actual
reference contact pass. Refinement construction explicitly requests
`require_trace_craft_nonregression=True` to apply the existing whole-parent
trace-craft gate during complete joint selection: an overlapping backtrack
is retried before publication. The backwards-compatible default still
provides only the documented topology/local-return proposal, not craft
qualification. Whole-parent saved receiving always retains its mandatory
craft gate regardless of this proposal-search option.
The explicit native-body return observer compares a proved direct body path
against a still-live old endpoint path even when both fit the observation
radius. A longer diagnostic radius therefore cannot conceal a shorter real
body return. The default endpoint-only observer is unchanged, and neither
observation grants full-width, plated-barrel or release qualification.
Coverage is in `tests/test_reserved_pour_pose_events.py`,
`tests/test_cell_contact_frontier.py` and `tests/test_complete_cell_receiving.py`.

Complete-cell local supplies also have a bounded native same-face detour tier
after the fixed path portfolio. It routes between the actual typed owner and
capacitor terminals, retaining the unchanged source-current contract, full
class/current width and existing local path-length bound. Native copper,
board-edge and priority-reservation guards remain active; the tier cannot
introduce a via, use another face or replace a terminal with a distant same-net
contact. Failed finite searches are not no-path proofs. Source-anchored saved
cell and whole-parent receiving remain mandatory. Native front/back/cardinal,
current/width/locality, disconnected-result and deadline tests are in
`tests/test_local_supply_native_detours.py`.

### Complete cell scope, input straps and literal no-connect intent

`cec_measurement_auxiliary_cut.plan` identifies an existing short package
strap only from the manufacturer auxiliary-input table, both actual same-net
lands and a literal native centre-to-centre stroke. A differently sized
external sense departure is separately source-owned by
`cec_measurement_leaf.plan_with_auxiliary_strap`; neither stroke hides the
other. Same-net contact outside the two real lands, unknown/partial packages,
groups, wide copper and ambiguous parallel straps refuse. Complete cell
reconstruction emits distinct mandatory requests for the strap and departure,
with their original widths. It does not reclassify a measurement as ordinary
power or infer an input current. Native front/back/cardinal and hostile-source
coverage is in `tests/test_measurement_auxiliary_cut.py`.

An isolated terminal is not automatically an open requiring a new route, nor
is a net called `unconnected` automatically exempt. `cec_source_no_connect`
requires one exact current-schematic symbol with matching reference, value,
MPN and footprint, one actual pin/marker coincidence, no wire/label/other-pin
contact, and no native same-net conductor or second land. Current BETA roots
come from the manifest; ambiguous or missing hierarchies never fall back to
an old flat sheet. Every consulted schematic is hash-bound and checked again
by both complete construction and saved receiving. Unmarked isolated signals
still refuse. This preserves declared intent, not electrical qualification.
Coverage is in `tests/test_source_no_connect.py`.

Complete source-owned Ground forks can reconstruct the existing Ground strap
of a moving package's manufacturer-typed address pin when reached through real
owned source metal. An address pin alone still cannot start such a cut or
become an inferred Ground/current role. The native fixed ports, every retained
mesh fragment, all original local returns, plated barrels and full-width
current contracts remain mandatory. Explicit fork work budgets are bounded
at 32 tracks/32 mm; the direct small-fork defaults remain narrower. A complete
atomic cell tier requests the larger bounded portfolio but still refuses a
union over its separate 64-track transaction limit. This increases search
scope, not physical clearances or deletion authority.

`rebuild_projected_ground=True` opts into re-deriving moving Ground leaves or
forks instead of retaining an old projected Ground entry as a routing wall.
It owns only positively proved source strokes, never a barrel, zone or whole
net. Exact stationary native lands remain protected. Construction and saved
receiving rederive the same policy, and the normal immediate-entry and
whole-source Ground nonregression checks are unchanged. Coverage is in
`tests/test_ground_return_fork.py` and
`tests/test_projected_ground_rebuild_policy.py`.

`cec_native_cell_pose_domains.propose` builds finite native per-face domains
and solves the complete cohort jointly. Explicit `fixed_refs` must match the
literal source poses; these anchors stay obstacles to every moving member,
not fictitious new placements into their own existing copper reservations.
Fixed-terminal supply/Ground distance relations filter candidates before an
orientation spends its finite choice quota. Otherwise a rotated domain can
be filled with already impossible lexicographic ties. Full foreign clearance,
prospective all-layer Ground barrels, courtyards, holes and fresh native offer
receiving remain required. These are proposals, not constructed/admitted
boards or a global no-path proof. Coverage is in
`tests/test_native_cell_pose_domains.py`.

### Complete Source-owned cell/barrel construction and saved replay

`cec_complete_macro_cell` connects the native macro compiler to complete
construction and independent saved-board receiving. Existing process-qualified
barrels and their proved factory dogbones follow the same exact cardinal
owner transform. Source pad/track/barrel identities, groups, dimensions,
every surviving original partition and every known local Ground return are
independently checked. Native geometry is checked on all actual copper faces,
including drilled-hole clearance. Priority-copper motion is not authorized.
Construction and receiving have explicit independently bounded stages of at
most 10 seconds; a partial path, timeout or an unreceived saved delta is never
a placement/routing pass. Whole-board DRC, source current, fields, Kelvin,
actual matched stack, thermal, process and fabrication gates remain separate.

The constructor reuses an exactly identical same-net/same-face/same-width
native track instead of drawing it twice for two obligations. Merely
overlapping, narrower or cross-face copper is not interchangeable. A new
Ground via must serve an actual bounded explicit-copper local-return request;
plane-wide connectivity alone cannot authorize an unrelated extra stitch.

Macro ports preserve every old native contact. If a via moves but another
conductor at its old contact stays fixed, the compiler emits separate mandatory
reconnection targets. A proved factory dogbone receives its real rigid
transform, not a fictitious old absolute attachment. A leaf endpoint can also
touch two retained track capsules while its centre lies on only one; exact
surviving pad/track/barrel connectivity proves the other contact without
distance snapping, zones, moving Source pads or retired tracks bridging the
proof. Native whole-partition receiving still checks the final result.

Small existing Ground boundary leads can be reconstructed only at positively
typed complete low-power Source terminals or their Source-owned barrels.
Unknown/collector/high-current lands refuse. An existing manufacturer-address
pin wired to Ground remains an address pin, and reconnects its literal old
strap; this does not infer a new Ground role, an aggregate injection budget or
ownership of a shared Ground trunk. Direct Ground-fork root policy above is
unchanged. The compiler has a finite composite work bound: its original base
cut is at most 64 edges, and at most eight independently typed additional
edges per selected footprint (maximum 64), for a total at most 128; constructive
requests remain bounded at 64. These are work limits, not relaxed current,
width, clearance or physical-ownership gates.

`cec_native_cell_pose_domains.propose(..., transport_source_barrels=True)`
includes the actual owned barrel copper, drilled holes and retained pickup in
the owner's pose domain. It does not leave these objects as fictitious fixed
obstacles, double-invent a future Ground barrel for an already carried entry,
or allow a carried via to masquerade as a stationary target. Each proposed
joint layout receives a fresh compiler/native/priority replay. An active
reference needs an explicit moving seed; literal unchanged references must
be declared in `fixed_refs`. No offered geometry is a routed board.

Native front/back/cardinal, exact shared-contact and hostile saved/material
coverage is in `tests/test_complete_macro_cell.py`,
`tests/test_cell_macro_requests.py` and `tests/test_native_cell_pose_domains.py`.

### Dominated local Ground dogbone cleanup

`cec_redundant_ground_dogbone.discover/plan/subtract/receive` can remove one
existing generated local Ground via and its single surface departure when a
strictly shorter, qualified direct dogbone already serves the same actual
two-land capacitor Ground pad. This is deletion-only, not mesh pruning or
permission to delete ordinary stitching vias. Exact native contacts must show
no other owner, inner departure, surface-zone contact or external junction.
Both reference planes need continuous saved-copper witnesses after removing
the old departure and again after final refill. The saved receiver independently
replays the subtraction, native group serialization, all surviving partitions,
and every already-known Ground return. Ordinary via dimensions do not excuse
partial SMD-pad overlap. Current, field, clipped-Kelvin, native DRC, assembly
and final release receiving remain mandatory and unchanged.

`tests/test_redundant_ground_dogbone.py` covers native front/back and four
rotations, actual discovery, ordinary-via partial overlap, source/group/part
tampering, unknown fills, and preservation of the retained entry.

Detailed scalar and typed Ground-boundary surface searches also inspect a
bounded portfolio of actual already-connected contacts. A valid first route
does not prove that the remaining joint obligations can use it. The original
named pair remains first; nearest alternative native lands and plated contacts
receive bounded maze work before track aliases consume the portfolio. All
original component/bridge choices and native partition obligations remain.
The shared surface lease is still at most two seconds inside the unchanged
ten-second connection lease; there are no new current, clearance, via or
reference-layer exceptions. `tests/test_component_surface_maze_portfolio.py`
covers actual front/back/cardinal detours, an already-present surface offer,
strict alternative endpoint/width/length/45-degree validation and work bounds.

Complete macro compilation also preserves complete original Ground paths for
positively typed stationary terminals when a qualified reference barrel keeps
its exact native geometry. The finite graph uses real same-face source metal,
not net-name equivalence or a UUID-only position test. A fresh Ground-fork plan
may shrink only its own cut; other owners and every final saved partition,
physical return, current, field and DRC check remain authoritative. This does
not approve a dangling stub or an ownerless small process-qualified barrel.
See `tests/test_stationary_ground_forest.py`.

Explicit stationary Ground barrels can reuse their original filled power-pour
antipads. Every original barrel dimension/group/process proof is rederived;
complete serialized foreign/reserved zone authorship and fill must stay exact.
Only ordinary unreserved Ground-plane filled polygons may have been refilled
before the read-only probe. No zone changes during the probe, new power-pour
hole, moved barrel or clearance exemption is allowed. See
`tests/test_stationary_ground_antipad.py`.

`cec_native_cell_pose_domains.propose(..., search_origins_mm=...)` can search
a different bounded region without pretending that an invalid search centre
is a compilable reconstruction pose. The valid seed still owns the complete
Source cut/transform. The swept obstacle inventory includes the entire new
translation and rotated-member envelope; immutable anchors cannot be moved
by this option. Every actual offer recompiles and receives its own native
Ground columns, Source barrels, partitions, courtyards and clearances under
the unchanged Source displacement and stage limits. Search regions are not
placement or routing admission. `tests/test_native_pose_search_origins.py`
covers native front/back/cardinal offers, exact immutable inputs, finite
regions, complete obstacle envelopes and original displacement bounds.
The envelope also includes world-fixed signal-port correction during native
rotation; geometric cancellation at the seed cannot hide that later sweep.
`tests/test_pose_search_world_offset_envelope.py` covers that case separately.

Detailed surface contact scheduling now explicitly receives the caller's
permitted routing faces. A fixed target barrel's expanded layer list cannot
consume the alternative-barrel quota with same-face track aliases: actual
common-face alternatives are funded before those aliases. This only orders
real discovered contacts; it invents no layer access, plane exception, via,
current budget or receiving authority. The original named pair and complete
connection/partition obligations remain mandatory.

`cec_qualified_courtyard_restore` restores only a missing SMD courtyard from
a reviewed package contract in `lib/vendor-data/footprint-courtyards/`.
Manufacturer evidence, the template and complete native local land pattern
are hash-bound; package IDs and part values must match. The courtyard contains
the reviewed body and actual lands with the declared clearance and grid.
It is not a copper-derived guess. Unsupported geometry, partial courtyards,
changed package data and ambiguous identities fail closed; existing valid
courtyards are not replaced.

The saved receiver independently strips only the four new authored courtyard
lines and compares every remaining native node against a no-op Source save.
Pads, copper/fills, annotation fields, model transforms, component poses,
rules and sidecars remain exact. Authored line centres are authoritative:
KiCad's inset DRC courtyard cache is checked for closure, not copied as the
physical envelope. Scratch transforms have real temporary board ownership,
including back-side native flips. Full placement, DRC, current, Kelvin,
matched-stack and release receiving remain separate mandatory gates.
`tests/test_qualified_courtyard_restore.py` covers front/back/cardinal and
octilinear transforms, data/land-pattern identity, stale plans, no-op handling,
partial geometry, and unowned saved changes.

Complete ordinary two-terminal RC lead reconstruction can explicitly opt in
to Source-declared, Ground-referenced signal layers with
`allow_source_signal_inner_layers=True`. The default remains outer-layer
only. The original retired lead must still be the complete, positively typed,
outer-face ordinary RC chain; this does not authorize power, measurement,
clock or differential-pair reconstruction. Replacement faces are the
intersection of the actual Source fabrication profile's non-power routing
layers and referenced signal layers, never a candidate's claimed stack.
Source netclass width floors (including renamed/canonical layer aliases)
remain mandatory, as do standard through-via geometry and the two-transition
limit. Malformed profiles, per-layer widths and non-boolean permissions fail
closed. Saved receiving independently checks owned placement/Ground motion,
neighbor annotation reflow, complete original connectivity and every unowned
native object. Whole-board current, DRC, Kelvin, Ground-return, pair/reference
and matched-stack gates remain separate requirements. See
`tests/test_ordinary_rc_source_signal_faces.py` for saved cardinal/part/profile
replays and hostile-input coverage; `cec_ordinary_rc_reconstruction.receive`
does not grant fabrication or release authority.
