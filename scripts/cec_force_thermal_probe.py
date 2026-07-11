#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_force_thermal_probe -- the owner's stamps-first THERMAL probe (2026-07-11:
# "remove all those other odd components and just run the fat traces to and from
# the shunts to the 12V pins, and then the sense pins through as well. Then run
# the full thermal solve on it... they are what stops us from being a ball of
# slag").
#
# Takes a laddered board (6 blueprint cells laid + locked), STRIPS it to the
# power path (J3/J4 + the six sensing cells + fiducials; locked cell copper
# kept, everything else removed), LAYS the fat force copper (J3 12V pin ->
# shunt HI, shunt LO -> J4 pin, 2.5mm F.Cu doglegs -- the alpha lane doctrine;
# pours are the escalation if the solve says so), adds the inner GND return
# planes, fills, and hands the board to the dashboard analyzer (full 2.5D
# field solve + temperature/current panels + gates).
#
# SWIG discipline (cec_stamp_lanes lessons): one mutation class per process;
# collect-then-batch-Remove; never touch board API after Remove beyond
# SaveBoard; os._exit after pcbnew work; UnFill before re-Fill.
#
#   python3 scripts/cec_force_thermal_probe.py --board <laddered.kicad_pcb>
#   (drives strip -> lay -> fill subprocesses, then archive via the dashboard)
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

OUT_DIR = "build/force-thermal-probe"
KEEP_PREFIXES = ("J3", "J4", "RS", "RFH", "RFL", "CF", "FID")
KEEP_EXACT = {f"U{n}" for n in range(10, 16)} | {f"C{n}" for n in range(10, 16)}
LANE_W_MM = 2.5                                   # alpha lane doctrine (2oz outer)


def _keep(ref):
    return ref in KEEP_EXACT or any(ref.startswith(p) and (p not in ("RS",) or ref[2:].isdigit())
                                    for p in KEEP_PREFIXES)


def _hi_net(n):
    return "/FAN_12V" if n == 6 else f"/SENSEP{n}_HI"


def phase_strip(args):
    import pcbnew
    probe = os.path.join(args.out, "12vhpwr-force-probe.kicad_pcb")
    shutil.copy(args.board, probe)
    for ext in (".kicad_pro", ".kicad_prl", ".kicad_dru"):
        src = args.board.replace(".kicad_pcb", ext)
        if os.path.exists(src):
            shutil.copy(src, probe.replace(".kicad_pcb", ext))
    board = pcbnew.LoadBoard(probe)
    doomed_fp = [fp for fp in board.GetFootprints() if not _keep(fp.GetReference())]
    # copper: keep LOCKED (the cells' laid blueprint copper), drop the rest
    doomed_tr = [t for t in board.GetTracks() if not t.IsLocked()]
    for fp in doomed_fp:
        board.Remove(fp)
    for t in doomed_tr:
        board.Remove(t)
    pcbnew.SaveBoard(probe, board)
    print(f"stripped: {len(doomed_fp)} parts, {len(doomed_tr)} unlocked copper items",
          flush=True)


def phase_lay(args):
    """Fat force copper, HONEST GEOMETRY (owner catch 2026-07-11: the naive
    doglegs shorted the inboard GND barrel rows + plowed through the cells'
    sense copper -- 160 real shorts; the field solver meshes per-net and is
    DRC-blind, so it 'solved cleanly' anyway). Alpha lane doctrine instead:
      HI  (F.Cu): 12V pad -> half-pitch jog -> 1.0mm NECK through the 1.48mm
                  GND-barrel gap -> 2.5mm run down the lane -> RS.1.
      LO  (B.Cu): RS.2 -> F.Cu spokes -> 4-via field (0.9/0.5) beside the pad
                  (clearance-searched vs the cell's copper) -> 2.5mm B.Cu run
                  (empty under the single-face cells) -> neck through J4's GND
                  row -> J4 12V pad (THT reaches B.Cu)."""
    import pcbnew
    probe = os.path.join(args.out, "12vhpwr-force-probe.kicad_pcb")
    board = pcbnew.LoadBoard(probe)
    MM = 1_000_000
    fcu, bcu = board.GetLayerID("F.Cu"), board.GetLayerID("B.Cu")
    nets = {str(k): v for k, v in board.GetNetInfo().NetsByName().items()}

    pads = []                                     # (ref, num, net, x, y)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for p_ in fp.Pads():
            pos = p_.GetPosition()
            pads.append((ref, p_.GetNumber(), p_.GetNetname(), pos.x / MM, pos.y / MM))

    lock_vias = []                                # cell GND stitching barrels
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T and t.IsLocked():
            pos = t.GetPosition()
            lock_vias.append((pos.x / MM, pos.y / MM))
    lock_segs = []                                # cell copper (foreign clearance checks)
    for t in board.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T and t.IsLocked():
            s_ = t.GetStart()
            sx, sy = s_.x / MM, s_.y / MM
            e_ = t.GetEnd()
            ex, ey = e_.x / MM, e_.y / MM
            lock_segs.append((t.GetNetname(), sx, sy, ex, ey))

    def track(net, x1, y1, x2, y2, w, layer):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(int(x1 * MM), int(y1 * MM)))
        t.SetEnd(pcbnew.VECTOR2I(int(x2 * MM), int(y2 * MM)))
        t.SetWidth(int(w * MM))
        t.SetLayer(layer)
        ni = nets.get(net)
        if ni is not None:
            t.SetNet(ni)
        board.Add(t)

    def via(net, x, y):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(int(x * MM), int(y * MM)))
        v.SetDrill(int(0.5 * MM))
        v.SetWidth(int(0.9 * MM))
        ni = nets.get(net)
        if ni is not None:
            v.SetNet(ni)
        board.Add(v)

    def neck_path(net, p_from, p_to, gnd_row_y, xn, layer, toward_y, fan_end_y):
        """p_from (connector pad) -> jog to the ASSIGNED barrel gap xn -> 1.0mm
        neck through the GND row -> ONE diagonal to the lane column, ending at
        the common fan line fan_end_y -> 2.5mm vertical to p_to. Unique xn per
        lane (1-3 fan left, 4-6 right) = crossing-free by construction."""
        fx, fy = p_from
        tx, ty = p_to
        y_pre = gnd_row_y - toward_y * 1.9        # neck entry/exit 1.9mm off the row
        y_post = gnd_row_y + toward_y * 1.9
        track(net, fx, fy, fx, fy + toward_y * 0.8, 1.4, layer)
        track(net, fx, fy + toward_y * 0.8, xn, y_pre, 1.0, layer)
        track(net, xn, y_pre, xn, y_post, 0.95, layer)            # the neck
        # MANHATTAN NESTED FAN (v4 -- the shared-band diagonals of v3 crossed):
        # vertical at xn to this lane's OWN horizontal band, horizontal to the
        # lane column, vertical to the pad. Bands nest outer->inner, so legs
        # cannot intersect by construction.
        track(net, xn, y_post, xn, fan_end_y, 2.5, layer)
        track(net, xn, fan_end_y, tx, fan_end_y, 2.5, layer)
        track(net, tx, fan_end_y, tx, ty, 2.5, layer)

    def clear_spot(x, y, lane_x):
        """Via site must clear cell pads (foreign) + locked cell copper by 0.65."""
        for ref, num, net, px, py in pads:
            if ref.startswith(("J3", "J4")):
                continue
            if abs(px - x) < 1.35 and abs(py - y) < 1.35 and not net.startswith("/SENSEP")                     and net != "/FAN_12V":
                return False
        for vx, vy in lock_vias:
            if (vx - x) ** 2 + (vy - y) ** 2 < 1.45 ** 2:
                return False
        for net, sx, sy, ex, ey in lock_segs:
            # coarse point-to-segment distance
            dx, dy = ex - sx, ey - sy
            L2 = dx * dx + dy * dy or 1e-9
            t_ = max(0.0, min(1.0, ((x - sx) * dx + (y - sy) * dy) / L2))
            qx, qy = sx + t_ * dx, sy + t_ * dy
            if (qx - x) ** 2 + (qy - y) ** 2 < 0.85 ** 2:
                return False
        return True

    j3_gnd_y = None
    j4_gnd_y = None
    j3_gnd_xs = [x for r, n, net, x, y in pads if r == "J3" and net == "GND"]
    j4_gnd_xs = [x for r, n, net, x, y in pads if r == "J4" and net == "GND"]
    if j3_gnd_xs:
        j3_gnd_y = sorted(y for r, n, net, x, y in pads if r == "J3" and net == "GND")[0]
    if j4_gnd_xs:
        j4_gnd_y = sorted(y for r, n, net, x, y in pads if r == "J4" and net == "GND")[0]

    report = {}
    for n in range(1, 7):
        hi, lo = _hi_net(n), f"/SENSEP{n}_LO"
        rs1 = next(((x, y) for r, pn, net, x, y in pads if r == f"RS{n}" and net == hi), None)
        rs2 = next(((x, y) for r, pn, net, x, y in pads if r == f"RS{n}" and net == lo), None)
        j3p = [(x, y) for r, pn, net, x, y in pads if r == "J3" and net == hi]
        j4p = [(x, y) for r, pn, net, x, y in pads if r == "J4" and net == lo]
        if not (rs1 and rs2 and j3p and j4p):
            report[n] = "MISSING PADS"
            continue
        p12 = min(j3p, key=lambda q: abs(q[0] - rs1[0]))
        p4 = min(j4p, key=lambda q: abs(q[0] - rs2[0]))
        gap_dir = -1.5 if n <= 3 else 1.5         # unique gap per lane, outward spread
        rank = (n - 1) if n <= 3 else (6 - n)     # 0 = outermost = earliest band
        neck_path(hi, p12, rs1, j3_gnd_y, p12[0] + gap_dir, fcu, +1.0,
                  fan_end_y=j3_gnd_y + 3.2 + 2.9 * rank + (1.45 if n > 3 else 0.0))
        # LO: via field beside RS.2, clearance-searched
        lane_x = rs2[0]
        sites = []
        for dy in (1.3, 2.0, 2.7, 3.4, 4.1):
            for dx in (-1.7, 1.7, -1.0, 1.0, 0.0):
                if len(sites) >= 4:
                    break
                cx, cy = lane_x + dx, rs2[1] + dy
                if clear_spot(cx, cy, lane_x) and all(
                        (cx - a) ** 2 + (cy - b) ** 2 >= 1.15 ** 2 for a, b in sites):
                    sites.append((cx, cy))
        for cx, cy in sites:
            via(lo, cx, cy)
            track(lo, rs2[0], rs2[1], cx, cy, 1.0, fcu)           # spoke (same-net over cell ok)
            track(lo, cx, cy, lane_x, cy, 1.2, bcu)               # short lateral into the lane
        if sites:
            sy = max(b for a, b in sites)
            track(lo, lane_x, min(b for a, b in sites), lane_x, sy, 2.0, bcu)
            y_h = j4_gnd_y - 3.2 - 2.9 * rank - (1.45 if n > 3 else 0.0)
            xn4 = p4[0] + gap_dir
            track(lo, lane_x, sy, lane_x, y_h, 2.5, bcu)          # lane vertical
            track(lo, lane_x, y_h, xn4, y_h, 2.5, bcu)            # nested band
            track(lo, xn4, y_h, xn4, j4_gnd_y - 1.9, 2.5, bcu)
            track(lo, xn4, j4_gnd_y - 1.9, xn4, j4_gnd_y + 1.9, 0.95, bcu)  # neck
            track(lo, xn4, j4_gnd_y + 1.9, p4[0], p4[1], 1.5, bcu)          # into the pad
        report[n] = {"vias": len(sites)}
    pcbnew.SaveBoard(probe, board)
    print("laid honest force copper:", json.dumps(report), flush=True)


def phase_fill(args):
    import pcbnew
    probe = os.path.join(args.out, "12vhpwr-force-probe.kicad_pcb")
    board = pcbnew.LoadBoard(probe)
    for z in board.Zones():
        z.UnFill()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(probe, board)
    print("zones filled", flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="force-path thermal probe builder")
    ap.add_argument("--board", required=True, help="a laddered .kicad_pcb (cells laid+locked)")
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--phase", default="all", choices=("all", "strip", "lay", "fill"))
    args = ap.parse_args(argv)
    os.makedirs(args.out, exist_ok=True)
    if args.phase == "all":
        import subprocess
        for sub in ("strip", "lay", "fill"):
            r = subprocess.run([sys.executable, os.path.abspath(__file__),
                                "--board", args.board, "--out", args.out, "--phase", sub])
            if r.returncode != 0:
                print(f"phase {sub} FAILED rc={r.returncode}", flush=True)
                return r.returncode
        print("probe built:", os.path.join(args.out, "12vhpwr-force-probe.kicad_pcb"),
              flush=True)
        return 0
    try:
        {"strip": phase_strip, "lay": phase_lay, "fill": phase_fill}[args.phase](args)
    except BaseException as e:                    # noqa: BLE001
        import traceback
        fr = traceback.extract_tb(e.__traceback__)[-2:]
        print(f"{args.phase} ERROR: {type(e).__name__}: {e} @ "
              + " <- ".join(f"{f.name}:{f.lineno}" for f in fr), flush=True)
        sys.stdout.flush()
        os._exit(1)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
