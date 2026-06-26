#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_sch_layout -- GENERAL signal-flow schematic placement, so a generated schematic
# reads left-to-right instead of landing on cec_sch.build_schematic's naive 5-col grid.
# This is the algorithmic replacement for the per-board hand-tuned gen-modules.layout():
# it needs no refdes conventions, only the netlist.
#
# Method (a simplified Sugiyama layered layout, the standard model for schematics):
#   1. Build a flow graph: parts are nodes; a shared net makes an edge -- EXCEPT power/
#      ground rails (named +.., GND, or fanning out to many parts), which connect
#      everything and carry no flow direction, so they are excluded from the edges (but
#      remembered for clustering).
#   2. Owner each 2-pin passive to the IC/connector it shares a signal edge with (its
#      decoupling/support cluster), and pull it out of the backbone.
#   3. Layer the backbone (x) by BFS distance from the input connectors; OUT* connectors
#      and unreached sinks go to the right.
#   4. Order within each layer (y) by the barycenter (mean neighbor order) heuristic, a
#      few sweeps, to reduce wire crossings.
#   5. Park each owned passive in a small fan beside its owner.
#
#   from cec_sch_layout import flow_placement
#   placement = flow_placement(parts, nets, used)   # {ref: (x_mm, y_mm)}
import re
from collections import defaultdict, deque

GRID = 1.27
_RAIL = re.compile(r"(^\+|GND$|_GND$|5V|3V3|VBUS|VSB|VCC|VDD|VRAIL|VVDD)", re.I)


def _snap(v):
    return round(v / GRID) * GRID


def _leaf(net):
    return net.rsplit("/", 1)[-1]


def flow_placement(parts, nets, used, *, col_w=60.0, row_h=30.0, x0=63.5, y0=50.8,
                   rail_fanout=6):
    """Return {ref: (x_mm, y_mm)} for every ref in `parts`. `used` maps (lib,name) ->
    {'pins': {...}} so pin counts classify connectors / ICs / passives."""
    def npins(r):
        lib, name = parts[r][0], parts[r][1]
        return len(used[(lib, name)]["pins"])

    is_conn = lambda r: r[:1].upper() == "J"
    is_pass = lambda r: npins(r) <= 2 and not is_conn(r)
    is_ic = lambda r: npins(r) >= 4 and not is_conn(r)

    # 1) flow edges, excluding rails -----------------------------------------------------
    edges = defaultdict(set)
    rail_members = defaultdict(set)
    for net, conns in nets.items():
        refs = sorted({c[0] for c in conns if c[0] in parts})
        if _RAIL.search(_leaf(net)) or len(refs) > rail_fanout:
            for r in refs:
                rail_members[r].add(net)
            continue
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                edges[refs[i]].add(refs[j])
                edges[refs[j]].add(refs[i])

    # 2) own passives to an adjacent IC (preferred) or any neighbour ---------------------
    owner = {}
    for r in parts:
        if not is_pass(r):
            continue
        nb = list(edges[r])
        ics = [x for x in nb if is_ic(x)]
        conns = [x for x in nb if is_conn(x)]
        owner[r] = ics[0] if ics else (nb[0] if nb else (conns[0] if conns else None))

    # Pure-DECOUPLING passives touch only rails (no signal edge) -> own them to a
    # rail-sharing IC, load-balanced so they don't all pile onto the ESP (which shares
    # every rail). Without this they have no owner and spill into one ugly column.
    ics_all = [r for r in parts if is_ic(r)]
    load = defaultdict(int)
    for o in owner.values():
        if o is not None:
            load[o] += 1
    for r in parts:
        if not is_pass(r) or owner.get(r) is not None:
            continue
        my = rail_members.get(r, set())
        best, bestkey = None, None
        for x in ics_all:
            s = len(my & rail_members.get(x, set()))
            if s <= 0:
                continue
            key = (s, -load[x])                          # most shared rails, then least loaded
            if bestkey is None or key > bestkey:
                bestkey, best = key, x
        if best is not None:
            owner[r] = best
            load[best] += 1

    backbone = [r for r in parts if not (is_pass(r) and owner.get(r) is not None)]
    bbset = set(backbone)

    # 3) layer (x) by BFS distance from input connectors --------------------------------
    conns = [r for r in backbone if is_conn(r)]
    left = [r for r in conns if "OUT" not in r.upper()] or conns
    layer = {r: 0 for r in left}
    dq = deque((r, 0) for r in left)
    while dq:
        r, d = dq.popleft()
        for x in edges[r]:
            if x in bbset and x not in layer:
                layer[x] = d + 1
                dq.append((x, d + 1))
    maxL = max(layer.values(), default=0)
    for r in backbone:                                  # unreached: sinks right, else end
        if r not in layer:
            layer[r] = maxL + 1
    for r in conns:                                     # OUT connectors hug the right edge
        if "OUT" in r.upper():
            layer[r] = max(layer.values(), default=0) + 1 if backbone else 1
    maxL = max(layer.values(), default=0)

    # 4) within-layer order (y) by barycenter, a few sweeps -----------------------------
    bylayer = defaultdict(list)
    for r in backbone:
        bylayer[layer[r]].append(r)
    order = {}
    for L in bylayer:
        for i, r in enumerate(sorted(bylayer[L])):
            order[r] = i
    for _ in range(6):
        for L in sorted(bylayer):
            def bary(r):
                ns = [order[x] for x in edges[r] if x in order]
                return (sum(ns) / len(ns)) if ns else order[r]
            bylayer[L].sort(key=bary)
            for i, r in enumerate(bylayer[L]):
                order[r] = i

    pos = {}
    for L in bylayer:
        for i, r in enumerate(bylayer[L]):
            pos[r] = (_snap(x0 + L * col_w), _snap(y0 + i * row_h))

    # 5) park owned passives in a fan beside the owner ----------------------------------
    fan = defaultdict(int)
    spill = 0
    for r in parts:
        if r in pos:
            continue
        o = owner.get(r)
        if o in pos:
            ox, oy = pos[o]
            k = fan[o]; fan[o] += 1
            side = -1 if k % 2 else 1                    # alternate above / below
            dy = side * row_h * 0.5 * (1 + k // 2)
            dx = 19.05 + (k % 3) * 7.62                  # to the IC's right, 3-wide spread
            pos[r] = (_snap(ox + dx), _snap(oy + dy))
        else:                                            # ownerless -> a tidy spill column
            pos[r] = (_snap(x0 + (maxL + 1) * col_w), _snap(y0 + spill * row_h * 0.5))
            spill += 1
    return pos


def preview(board="eps-8pin", *, render=True):
    """Generate <board> with the auto-layout into a SCRATCH schematic (never the committed
    one) and optionally render it for review. Returns the scratch path. The iteration loop:
    tweak flow_placement -> preview -> Read the render -> repeat."""
    import os, shutil, importlib.util, sys
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    spec = importlib.util.spec_from_file_location("gen_modules", os.path.join(here, "gen-modules.py"))
    gm = importlib.util.module_from_spec(spec); spec.loader.exec_module(gm)
    import cec_sch
    base = dict(gm.MODS)[board]
    parts, nets = gm.build(board)
    used = cec_sch.load_symbols(gm.LIBS, parts)
    fps = {r: gm.footprint_for(r, *parts[r]) for r in parts}
    auto = flow_placement(parts, nets, used)
    print(f"{board}: parts={len(parts)} body-overlap auto={overlaps(auto, used, parts)} "
          f"hand={overlaps(gm.layout(board, parts), used, parts)}")
    root = os.path.dirname(here)
    out = os.path.join(root, "build", "sch-layout", f"{base}-auto.kicad_sch")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    shutil.copy(os.path.join(root, "modules", board, f"{base}.kicad_sch"), out)   # seed uuid
    cec_sch.build_schematic(out, f"{base}-auto", parts, nets, used, gm.LIBS, paper="A3",
                            power_ports={"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3"},
                            powerflag_nets=["+5VSB", "GND"], nc_skip={("U1", "4")},
                            placement=auto, wire_nets=[f"SENSE{l}_HI" for l, _ in gm.RAILS[board]],
                            footprints=fps)
    if render:
        import cec_sch_review
        cec_sch_review.review(out, erc=False)
    print(f"scratch: {os.path.relpath(out, root)}")
    return out


def overlaps(pos, used, parts, *, pad=2.0):
    """Cheap QA: count pairs whose symbol body boxes overlap (lower is better)."""
    import cec_sch
    boxes = {}
    for r, (ox, oy) in pos.items():
        bb = cec_sch.sym_body_box(used[(parts[r][0], parts[r][1])]["block"])
        if bb:
            boxes[r] = (ox + bb[0] - pad, ox + bb[1] + pad, oy - bb[3] - pad, oy - bb[2] + pad)
    refs = list(boxes)
    n = 0
    for i in range(len(refs)):
        ax0, ax1, ay0, ay1 = boxes[refs[i]]
        for j in range(i + 1, len(refs)):
            bx0, bx1, by0, by1 = boxes[refs[j]]
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                n += 1
    return n


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Auto-layout preview: generate a board with "
                                 "flow_placement into a scratch schematic + render it.")
    ap.add_argument("board", nargs="?", default="eps-8pin")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()
    preview(a.board, render=not a.no_render)
