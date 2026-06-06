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
