#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# RAIL-BUS pre-route experiment (2026-06-18, owner ask): the placement loop converges to ~clips=40, the
# residual being the shared rails (+3V3/+5VSB) that Freerouting routes STRAIGHT THROUGH the high-current
# pours (clipping them). Freerouting alone can't be forced around (a hard keepout strands the dense board).
#
# This routes the rails as a BUS through the CLEAR zones using cec_fr02 waypoint intents (NET-SPECIFIC
# guidance -- locked stubs the net must pass through -- NOT a global keepout): a trunk along the top/bottom
# channel + a dip through the centre gap to reach both corridors' inner-edge sense ICs without crossing a
# pour, then route_directed lets Freerouting fill the signals AROUND the locked rail trunk.
#
# Usage (in the routing container):
#   python3 scripts/cec_rail_bus.py --board-pcb build/.../X.kicad_pcb --board beta/eps-8pin --out OUT.kicad_pcb
import argparse
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def rail_intents(board_pcb, board_dir, *, rails=("+3V3", "+5VSB"), all_spanning=False):
    """Waypoint intents that route nets through the CLEAR channels around the pours (net-specific guidance,
    not a global keepout). rails-only pins the two power rails; all_spanning=True DISTRIBUTES every net that
    straddles a corridor across the top/bottom channels at staggered y-lanes -- because the simple rail-bus
    just shifts the congestion (the channels can't hold the rails AND the ~15 signals at once), so EVERY
    spanning net needs a channel slot. Sense (_HI/_LO) + GND are excluded (they belong in the pour/plane)."""
    import pcbnew
    import cec_synth_pipeline as sp
    board = pcbnew.LoadBoard(board_pcb)
    bb = board.GetBoardEdgesBoundingBox()
    W, H = bb.GetWidth() / 1e6, bb.GetHeight() / 1e6
    P = {fp.GetReference(): (fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6, fp.GetOrientationDegrees())
         for fp in board.GetFootprints()}
    comps = {fp.GetReference(): "%s:%s" % (fp.GetFPID().GetLibNickname(), fp.GetFPID().GetLibItemName())
             for fp in board.GetFootprints()}
    nl = sp.View(sp.Config.load(board_dir)).nl
    model = sp.build_corridor_model(nl, {r: P[r] for r in P}, comps, board_w=W)
    bands = sorted((c.band for c in model.cables if c.formed), key=lambda b: b[0])  # (x0,x1,y0,y1)
    y_top = min(b[2] for b in bands) if bands else 0
    y_bot = max(b[3] for b in bands) if bands else H
    if not bands:
        del board
        return []
    top_y = max(0.6, y_top - 1.5)
    bot_y = min(H - 0.6, y_bot + 1.5)

    def is_sense(n):
        return n.endswith("_HI") or n.endswith("_LO")

    if not all_spanning:
        gaps = [((bands[i][1] + bands[i + 1][0]) / 2.0, bands[i + 1][0] - bands[i][1])
                for i in range(len(bands) - 1)]
        gap_x = max(gaps, key=lambda g: g[1])[0] if gaps else W / 2.0
        gap_mid_y = (y_top + y_bot) / 2.0
        del board
        out = []
        for k, net in enumerate(rails):
            trunk_y = top_y if k % 2 == 0 else bot_y
            wps = [{"at_mm": [round(W * f, 1), round(trunk_y, 1)]} for f in (0.12, 0.3, 0.5, 0.7, 0.88)]
            wps.append({"at_mm": [round(gap_x, 1), round(gap_mid_y, 1)]})
            out.append({"net": net, "layers": ["F.Cu"], "waypoints": wps, "width_mm": 0.4})
        return out

    # ALL-SPANNING: find every non-GND/non-sense net whose pads straddle a corridor band (left of x0 AND
    # right of x1, overlapping its y-range) -> it must cross, so give it a channel lane.
    pads_by_net = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn:
                pads_by_net.setdefault(nn, []).append((p.GetPosition().x / 1e6, p.GetPosition().y / 1e6))
    del board
    spanning = []
    for net, pts in pads_by_net.items():
        if not net or net.endswith("GND") or is_sense(net) or len(pts) < 2:
            continue
        xs = [x for x, _ in pts]; ys = [y for _, y in pts]
        if any(min(xs) < b[0] and max(xs) > b[1] and max(ys) >= b[2] and min(ys) <= b[3] for b in bands):
            spanning.append(net)
    spanning.sort()
    # DISTRIBUTE across 4 tracks per lane: {top,bottom} x {F.Cu,B.Cu}. The channel is clear of pour on BOTH
    # outer layers, so using B.Cu doubles capacity -> 15 nets fit ~4 y-lanes instead of ~8, and the lanes
    # don't crowd the 5mm channel (the drc=25 single-layer failure). Wider 0.8mm stagger for clearance.
    intents = []
    for i, net in enumerate(spanning):
        slot = i % 4                                        # 0=top/F 1=top/B 2=bot/F 3=bot/B
        lane = i // 4
        top = slot < 2
        layer = "F.Cu" if slot % 2 == 0 else "B.Cu"
        base = top_y if top else bot_y
        ly = base + (-0.8 * lane if top else 0.8 * lane)
        ly = max(0.5, min(H - 0.5, ly))
        wps = [{"at_mm": [round(W * f, 1), round(ly, 1)]} for f in (0.2, 0.4, 0.6, 0.8)]
        intents.append({"net": net, "layers": [layer], "waypoints": wps, "width_mm": 0.25})
    return intents


def main(argv=None):
    ap = argparse.ArgumentParser(description="rail-bus pre-route experiment")
    ap.add_argument("--board-pcb", required=True)
    ap.add_argument("--board", required=True, help="module dir (netlist/Config)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--passes", type=int, default=16)
    ap.add_argument("--opt-time", type=int, default=40)
    ap.add_argument("--dump-intents", action="store_true")
    ap.add_argument("--all-spanning", action="store_true", help="guide EVERY corridor-spanning net, not just rails")
    a = ap.parse_args(argv)
    bp = a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb)
    bd = a.board if os.path.isabs(a.board) else os.path.join(ROOT, a.board)
    intents = rail_intents(bp, bd, all_spanning=a.all_spanning)
    if a.dump_intents:
        print("INTENTS=" + json.dumps(intents))
    import cec_overnight_directed as ovd
    workdir = tempfile.mkdtemp(prefix="railbus_")
    routed, stubs, params = ovd.route_directed(bp, intents, 0, workdir,
                                               passes=a.passes, opt_time=a.opt_time, perturb_on=False)
    outp = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
    import shutil
    shutil.copy2(routed, outp)
    print("ROUTED=" + json.dumps({"out": os.path.relpath(outp, ROOT), "n_stubs": len(stubs),
                                  "rails": [i["net"] for i in intents]}))


if __name__ == "__main__":
    main()
