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
    """Fat force copper -- DELEGATED to the shared cec_force_lanes module (the
    same DRC-proven v7 geometry the fresh-wave materialize lays LOCKED; owner
    rung 2026-07-11 "set and not infringed on"). History + the honest-geometry
    derivation (owner catch: naive doglegs = 160 shorts, solver is DRC-blind)
    live in cec_force_lanes' header and the git log of this file."""
    import pcbnew
    import cec_force_lanes
    probe = os.path.join(args.out, "12vhpwr-force-probe.kicad_pcb")
    board = pcbnew.LoadBoard(probe)
    report = cec_force_lanes.lay_force_lanes(board, lock=True)
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
