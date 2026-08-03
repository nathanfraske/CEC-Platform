#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# PARALLEL-LANE CHANNEL ROUTER (2026-06-18, owner ask). The placement loop floors at ~40 pour clips because
# Freerouting routes the ~15 corridor-SPANNING nets (the +3V3/+5VSB rails + the ESP signals) STRAIGHT through
# the high-current pours. A full keepout strands the dense board; crude waypoint stubs (cec_fr02) over-
# constrain Freerouting (worse). The fix (proven concept: distinct clip nets 14->6): lay the channel-crossing
# of each spanning net as REAL CONNECTED LOCKED COPPER -- a parallel lane in the clear top/bottom channel,
# each net on its own {channel x layer x y-offset} slot so they run parallel and don't collide -- then let
# Freerouting fill the LOCAL pad on-ramps + the non-spanning nets around the locked lanes.
#
# A lane is the through-trunk only; Freerouting connects each pad to the nearest lane point (a short local
# route). Lanes weave around the cable connectors that sit in the channels.
#
# Usage (in the routing container):
#   python3 scripts/cec_channel_route.py --lay-only --board-pcb IN --board beta/eps-8pin-rev3 --out LANES.kicad_pcb
#   python3 scripts/cec_channel_route.py --route    --board-pcb IN --board beta/eps-8pin-rev3 --out ROUTED.kicad_pcb
import argparse
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
MM = 1_000_000


def _geom(board, board_dir):
    """Board geometry: (W,H), corridor bands sorted L->R, channel y-lines, pad map, and the
    connector/courtyard obstacles that sit in the channels (lanes must weave around them)."""
    import cec_synth_pipeline as sp
    bb = board.GetBoardEdgesBoundingBox()
    W, H = bb.GetWidth() / MM, bb.GetHeight() / MM
    P = {fp.GetReference(): (fp.GetPosition().x / MM, fp.GetPosition().y / MM, fp.GetOrientationDegrees())
         for fp in board.GetFootprints()}
    comps = {fp.GetReference(): "%s:%s" % (fp.GetFPID().GetLibNickname(), fp.GetFPID().GetLibItemName())
             for fp in board.GetFootprints()}
    nl = sp.View(sp.Config.load(board_dir)).nl
    model = sp.build_corridor_model(nl, {r: P[r] for r in P}, comps, board_w=W)
    bands = sorted((c.band for c in model.cables if c.formed), key=lambda b: b[0])  # (x0,x1,y0,y1)
    return W, H, bands, model


def _spanning_nets(board, bands):
    """Every non-GND / non-sense net whose pads straddle a corridor band -> it must cross."""
    pads = {}
    for fp in board.GetFootprints():
        for p in fp.Pads():
            nn = p.GetNetname()
            if nn:
                pads.setdefault(nn, []).append((p.GetPosition().x / MM, p.GetPosition().y / MM))
    out = []
    for net, pts in pads.items():
        if not net or net.endswith("GND") or net.endswith("_HI") or net.endswith("_LO") or len(pts) < 2:
            continue
        xs = [x for x, _ in pts]; ys = [y for _, y in pts]
        if any(min(xs) < b[0] and max(xs) > b[1] and max(ys) >= b[2] and min(ys) <= b[3] for b in bands):
            out.append((net, min(xs), max(xs)))
    out.sort()
    return out, pads


def lay_lanes(board, board_dir, *, lane_pitch=0.7, lane_w=0.3, clr=0.45):
    """Lay one LOCKED parallel lane per spanning net through a clear channel. Returns the list of lane nets.
    Distribution: net i -> {top,bottom} x {F.Cu,B.Cu}, stacked by lane index into the channel; the lane runs
    at lane_y from the net's leftmost to rightmost pad x (the through-trunk). Connector pads in the channel
    are obstacles -- a lane that would run over one is nudged deeper into the channel for that net."""
    import pcbnew
    W, H, bands, _model = _geom(board, board_dir)
    if not bands:
        return []
    y_top = min(b[2] for b in bands)                       # pour top -> top channel is y < y_top
    y_bot = max(b[3] for b in bands)                       # pour bottom -> bottom channel is y > y_bot
    spanning, padmap = _spanning_nets(board, bands)
    # obstacles in the channels: every pad with y in a channel (connectors J_IN/J_OUT live there)
    obstacles = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            x, y = p.GetPosition().x / MM, p.GetPosition().y / MM
            if y < y_top or y > y_bot:
                hw = p.GetSize().x / MM / 2 + clr
                obstacles.append((x - hw, x + hw, y))
    laid = []
    for i, (net, x0, x1) in enumerate(spanning):
        slot = i % 4                                       # 0 top/F 1 top/B 2 bot/F 3 bot/B
        lane = i // 4
        top = slot < 2
        layer = pcbnew.F_Cu if slot % 2 == 0 else pcbnew.B_Cu
        # lane_y: start just inside the channel, step deeper per lane index, but pull it to a y that clears
        # any connector pad whose x-span overlaps this net's [x0,x1] (so the trunk doesn't sit on a pad)
        if top:
            ly = max(0.5, y_top - 0.8 - lane_pitch * lane)
            for ox0, ox1, oy in obstacles:
                if oy < y_top and ox1 > x0 - 1 and ox0 < x1 + 1:
                    ly = min(ly, oy - 0.7)                 # tuck above the obstacle (smaller y)
            ly = max(0.5, ly)
        else:
            ly = min(H - 0.5, y_bot + 0.8 + lane_pitch * lane)
            for ox0, ox1, oy in obstacles:
                if oy > y_bot and ox1 > x0 - 1 and ox0 < x1 + 1:
                    ly = max(ly, oy + 0.7)
            ly = min(H - 0.5, ly)
        netobj = board.FindNet(net)
        if netobj is None:
            continue
        pts = [pt for pt in padmap.get(net, [])]            # this net's pad positions
        if not pts:
            continue
        lx0 = max(1.0, min(p[0] for p in pts) - 0.5)
        lx1 = min(W - 1.0, max(p[0] for p in pts) + 0.5)

        def add_track(x1n, y1n, x2n, y2n, lyr):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int(x1n * MM), int(y1n * MM)))
            t.SetEnd(pcbnew.VECTOR2I(int(x2n * MM), int(y2n * MM)))
            t.SetWidth(int(lane_w * MM)); t.SetLayer(lyr); t.SetNet(netobj); t.SetLocked(True)
            board.Add(t)

        def add_via(x, y):
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(int(x * MM), int(y * MM)))
            v.SetDrill(int(0.4 * MM)); v.SetWidth(int(0.7 * MM))
            v.SetNet(netobj); v.SetLocked(True)
            board.Add(v)

        add_track(lx0, ly, lx1, ly, layer)                 # the LANE trunk (between this net's pad columns)
        # RISER from each pad up/down to the lane: F.Cu vertical pad->lane_y (+ via to the lane layer if B.Cu)
        for px, py in pts:
            rx = max(lx0, min(lx1, px))
            add_track(px, py, rx, py, pcbnew.F_Cu)         # short F.Cu jog pad -> riser column
            add_track(rx, py, rx, ly, pcbnew.F_Cu)         # F.Cu riser up/down to the lane y
            if layer != pcbnew.F_Cu:
                add_via(rx, ly)                            # drop to the B.Cu lane
        laid.append(net)
    return laid


def w_lay(board_pcb, board_dir, out_rel):
    import pcbnew
    board = pcbnew.LoadBoard(board_pcb)
    nets = lay_lanes(board, board_dir)
    outp = out_rel if os.path.isabs(out_rel) else os.path.join(ROOT, out_rel)
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
    pcbnew.SaveBoard(outp, board)
    del board
    return {"out": os.path.relpath(outp, ROOT), "lane_nets": nets}


def w_route(board_pcb, board_dir, out_rel, *, passes=20, opt_time=50):
    """Lay locked lanes -> DSN -> force-protect the lane nets -> Freerouting -> import + pours."""
    import pcbnew
    import cec_fr
    import cec_fr02
    wd = tempfile.mkdtemp(prefix="chan_")
    laid = os.path.join(wd, "laid.kicad_pcb")
    board = pcbnew.LoadBoard(board_pcb)
    nets = lay_lanes(board, board_dir)
    pcbnew.SaveBoard(laid, board)
    del board
    dsn, ses = os.path.join(wd, "r.dsn"), os.path.join(wd, "r.ses")
    cec_fr.export_dsn(laid, dsn)
    cec_fr02.force_protect_in_dsn(dsn, sorted(set(nets)))
    cec_fr.run_freerouting(dsn, ses, passes=passes, opt_time=opt_time, timeout=900)
    pours = cec_fr.derive_power_pours(laid)
    outp = out_rel if os.path.isabs(out_rel) else os.path.join(ROOT, out_rel)
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
    cec_fr.import_ses(laid, ses, outp, power_pours=pours)
    return {"out": os.path.relpath(outp, ROOT), "lane_nets": nets}


def main(argv=None):
    ap = argparse.ArgumentParser(description="parallel-lane channel router")
    ap.add_argument("--lay-only", action="store_true")
    ap.add_argument("--route", action="store_true")
    ap.add_argument("--board-pcb", required=True)
    ap.add_argument("--board", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--passes", type=int, default=20)
    ap.add_argument("--opt-time", type=int, default=50)
    a = ap.parse_args(argv)
    bp = a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb)
    bd = a.board if os.path.isabs(a.board) else os.path.join(ROOT, a.board)
    if a.lay_only:
        r = w_lay(bp, bd, a.out)
    else:
        r = w_route(bp, bd, a.out, passes=a.passes, opt_time=a.opt_time)
    print("RESULT=" + json.dumps(r))


if __name__ == "__main__":
    main()
