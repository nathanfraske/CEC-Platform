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
