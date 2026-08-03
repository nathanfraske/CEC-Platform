#!/usr/bin/env python3
"""Annotated corridor plots: committed best-hand eps board vs the Phase 2 synth placement.
Shows part courtyards, the formed high-current bands (shaded), and the foreign signal nets that
cross them (red) -- visualizing the cc=6 inherent-floor finding."""
import sys
import os
from collections import defaultdict

sys.path.insert(0, "scripts")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import cec_synth_pipeline as sp
import cec_pcb
import pcbnew

EPS = "beta/eps-8pin-rev3/eps-8pin-rev3.kicad_pcb"
OUT = "build/corridor-plots"


def board_nl(path):
    b = pcbnew.LoadBoard(path)
    comps, nets, P = {}, defaultdict(list), {}
    for fp in b.GetFootprints():
        r = fp.GetReference()
        comps[r] = sp.Comp(ref=r, value=fp.GetValue(), footprint=fp.GetFPIDAsString())
        pos = fp.GetPosition()
        P[r] = (pos.x / 1e6, pos.y / 1e6, fp.GetOrientationDegrees())
        for pad in fp.Pads():
            if pad.GetNetname():
                nets[pad.GetNetname()].append((r, pad.GetPadName()))
    return sp.Netlist(comps=comps, nets=dict(nets)), P, {r: c.footprint for r, c in comps.items()}


def pads_by_net(nl, P, comps):
    out = defaultdict(list)
    for net, nodes in nl.nets.items():
        for ref, pin in nodes:
            if ref not in P or ref not in comps:
                continue
            try:
                out[net].append(cec_pcb.pad_global(ref, pin, {ref: P[ref]}, comps))
            except Exception:
                out[net].append((P[ref][0], P[ref][1]))
    return dict(out)


def crossing_nets(pbn, bands, corridor_nets, W):
    """List (net, base, y) for each (foreign signal, formed band) through-cross."""
    usable = {b: r for b, r in bands.items() if sp._band_formed(r, W)}
    out = []
    for net, pts in pbn.items():
        if net in corridor_nets or len(pts) < 2:
            continue
        if sp._corridor_net_role(net, corridor_nets) != "signal":
            continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
        for base, (X0, X1, Y0, Y1) in usable.items():
            if by1 >= Y0 and by0 <= Y1 and bx0 < X0 and bx1 > X1:
                out.append((net, base, bx0, bx1, sum(ys) / len(ys)))
    return out


def draw(ax, title, nl, P, comps, W, H):
    model = sp.build_corridor_model(nl, P, comps, board_w=W)
    pbn = pads_by_net(nl, P, comps)
    cc = sp.corridor_cross_count(pbn, model.bands, model.corridor_nets, board_w=W)
    # board outline
    ax.add_patch(Rectangle((0, 0), W, H, fill=False, ec="black", lw=1.5))
    # formed bands (shaded), with labels
    for cab in model.cables:
        x0, x1, y0, y1 = cab.band
        col = "#ff9966" if cab.formed else "#cccccc"
        ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=col, ec="#cc5500",
                               alpha=0.45, lw=1.0, zorder=1))
        ax.text((x0 + x1) / 2, y1 + 0.6, cab.base.replace("/SENSEC", "cable "),
                ha="center", va="bottom", fontsize=7, color="#aa3300")
    # part courtyards
    for ref, (x, y, rot) in P.items():
        if ref not in comps:
            continue
        try:
            cx0, cx1, cy0, cy1 = cec_pcb.courtyard_bbox(comps[ref], x, y, rot)
        except Exception:
            continue
        key = ref.startswith(("J_", "RS", "U1", "U2", "U20", "U21", "U30", "U31", "J1", "J5"))
        ax.add_patch(Rectangle((cx0, cy0), cx1 - cx0, cy1 - cy0, fill=False,
                               ec="#3366cc" if key else "#aaaaaa",
                               lw=1.0 if key else 0.5, zorder=3))
        if key:
            ax.text((cx0 + cx1) / 2, (cy0 + cy1) / 2, ref, ha="center", va="center",
                    fontsize=5.5, color="#1133aa", zorder=4)
    # crossing nets (red lines through the bands)
    seen = {}
    for net, base, bx0, bx1, yy in crossing_nets(pbn, model.bands, model.corridor_nets, W):
        ax.plot([bx0, bx1], [yy, yy], color="red", lw=1.2, alpha=0.8, zorder=5)
        seen.setdefault(net, yy)
    for net, yy in seen.items():
        ax.text(W - 1, yy, net, ha="right", va="center", fontsize=5.5, color="red", zorder=6)
    ax.set_title("%s   —   corridor_cross = %d" % (title, cc), fontsize=10)
    ax.set_xlim(-3, W + 3); ax.set_ylim(H + 4, -3)   # invert y (KiCad)
    ax.set_aspect("equal"); ax.set_xlabel("mm", fontsize=7)
    ax.tick_params(labelsize=6)


def main():
    os.makedirs(OUT, exist_ok=True)
    # committed board
    nlc, Pc, cmc = board_nl(EPS)
    eb = pcbnew.LoadBoard(EPS).GetBoardEdgesBoundingBox()
    Wc, Hc = eb.GetWidth() / 1e6, eb.GetHeight() / 1e6
    # synth Phase 2 placement WITH connector overhang (the fix): connectors at edges, corridor
    # spans full height, residual 0
    cfg = sp.Config.load("eps-8pin", params={"connector_overhang": "edge"})
    cd = {k: getattr(cfg, k) for k in ("board", "profile", "pins", "params",
                                       "dir", "sch", "net", "pcb", "bom_csv")}
    cand = sp.synth_one(cd, 96.0, 37.0, "thermal_separated", 3)
    nls = sp.View(cfg).nl
    cms = sp._fp_of(nls)

    fig, axes = plt.subplots(2, 1, figsize=(11, 9))
    draw(axes[0], "COMMITTED best-hand eps-8pin (reference)", nlc, Pc, cmc, Wc, Hc)
    draw(axes[1], "Phase 2 SYNTH + connector OVERHANG (thermal_separated s3, residual 0)", nls,
         {r: cand.P[r] for r in cand.P}, cms, 96.0, 37.0)
    fig.suptitle("eps-8pin high-current corridors (shaded) + foreign signals that CROSS them (red)\n"
                 "With connector OVERHANG the cable ports seat at the edges -> the corridor spans the "
                 "full height and the placement is DRC-clean (residual 0)", fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    p = os.path.join(OUT, "eps-corridor-overhang.png")
    fig.savefig(p, dpi=130)
    print("wrote", p)


if __name__ == "__main__":
    main()
