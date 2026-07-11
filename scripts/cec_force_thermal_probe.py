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
    import pcbnew
    probe = os.path.join(args.out, "12vhpwr-force-probe.kicad_pcb")
    board = pcbnew.LoadBoard(probe)
    MM = 1_000_000
    fcu = board.GetLayerID("F.Cu")
    nets = {str(k): v for k, v in board.GetNetInfo().NetsByName().items()}

    def pads_of(net):
        out = []
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            for p in fp.Pads():
                if p.GetNetname() == net:
                    pos = p.GetPosition()
                    out.append((ref, p.GetNumber(), pos.x / MM, pos.y / MM))
        return out

    def lay(net, pts):
        ni = nets.get(net)
        laid = 0
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(int(x1 * MM), int(y1 * MM)))
            t.SetEnd(pcbnew.VECTOR2I(int(x2 * MM), int(y2 * MM)))
            t.SetWidth(int(LANE_W_MM * MM))
            t.SetLayer(fcu)
            if ni is not None:
                t.SetNet(ni)
            board.Add(t)
            laid += 1
        return laid

    report = {}
    for n in range(1, 7):
        hi, lo = _hi_net(n), f"/SENSEP{n}_LO"
        hp = pads_of(hi)
        lp = pads_of(lo)
        rs_hi = next(((x, y) for r, pn, x, y in hp if r == f"RS{n}"), None)
        rs_lo = next(((x, y) for r, pn, x, y in lp if r == f"RS{n}"), None)
        j3 = [(x, y) for r, pn, x, y in hp if r == "J3"]
        j4 = [(x, y) for r, pn, x, y in lp if r == "J4"]
        laid = 0
        if rs_hi and j3:
            px, py = min(j3, key=lambda q: abs(q[0] - rs_hi[0]))   # nearest 12V pin
            mid_y = py + 0.35 * (rs_hi[1] - py)
            laid += lay(hi, [(px, py), (px, mid_y), (rs_hi[0], mid_y + 0.25 * (rs_hi[1] - py)),
                             (rs_hi[0], rs_hi[1])])
        if rs_lo and j4:
            px, py = min(j4, key=lambda q: abs(q[0] - rs_lo[0]))
            mid_y = py + 0.35 * (rs_lo[1] - py)
            laid += lay(lo, [(px, py), (px, mid_y), (rs_lo[0], mid_y + 0.25 * (rs_lo[1] - py)),
                             (rs_lo[0], rs_lo[1])])
        report[n] = {"hi_segs+lo_segs": laid,
                     "hi_pads": len(hp), "lo_pads": len(lp)}
    # inner GND return planes (THT connector pins reach them directly)
    gnd = nets.get("GND")
    bb = board.GetBoardEdgesBoundingBox()
    x0, y0 = bb.GetLeft() + int(0.5 * MM), bb.GetTop() + int(0.5 * MM)
    x1, y1 = bb.GetRight() - int(0.5 * MM), bb.GetBottom() - int(0.5 * MM)
    made = 0
    for lname in ("In1.Cu", "In2.Cu"):
        lid = board.GetLayerID(lname)
        if lid < 0 or gnd is None:
            continue
        exists = any(z.GetNetname() == "GND" and lid in z.GetLayerSet().Seq()
                     for z in board.Zones())
        if exists:
            continue
        z = pcbnew.ZONE(board)
        z.SetLayer(lid)
        z.SetNet(gnd)
        o = z.Outline()
        o.NewOutline()
        for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            o.Append(px, py)
        board.Add(z)
        made += 1
    pcbnew.SaveBoard(probe, board)
    print(f"laid force copper: {json.dumps(report)}; gnd planes added: {made}", flush=True)


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
