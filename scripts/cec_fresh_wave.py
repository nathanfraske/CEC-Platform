#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
cec_fresh_wave -- the fresh-board synthesis WAVE driver (2026-07-07).

For each named beta board: fan out placement variants (strategy x seed x partition
intent) through PlacementSession, grade EVERY variant with the route-oracle (the
real post-route accept conjunction: kelvin AND diffpair AND drc-finishing AND
foreign==0 AND thermal AND routing-complete), keep the best by the oracle
sort_key, and publish ONLY the winner to build/fresh/<board>/ -- the dashboard's
watch glob -- so accepted boards appear in the browser as they are made.
Working candidates stay in build/fresh-work/<board>/ (NOT watched; the dashboard
must not GPU-analyze every loser).

Run INSIDE the routing container:
    python3 scripts/cec_fresh_wave.py --boards eps-8pin,pcie-8pin-2port
        [--seeds 0,1,2,3] [--passes 16] [--opt 20] [--out build/fresh]

The variant set is deliberately structure-first (the 2026-06-30 placer-feasibility
finding: partitions/intents move the needle, absolute-coord jitter does not).
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

import cec_synth_pipeline as csp                       # noqa: E402
from cec_placement_session import PlacementSession     # noqa: E402

# Working W x H per board (mm): the committed boards' envelope as the STARTING size
# (the shrink pass comes after a gate-clean baseline exists; SHUNT_GAP may grow H).
BOARD_WH = {
    "eps-8pin": (96.0, 37.0),
    "pcie-8pin-2port": (86.5, 44.0),
    "pcie-8pin-3port": (103.5, 56.0),
}


def _intents():
    """Named structure-first partition intents. Each takes a session and mutates it."""
    def none(s):
        return s

    def periph_right(s):
        s.half("periph", "x", 0.58, 1.00)
        s.half("cables", "x", 0.00, 0.58)
        s.assign(s.peripheral_ics(), "periph")
        return s

    def periph_left(s):
        s.half("periph", "x", 0.00, 0.42)
        s.half("cables", "x", 0.42, 1.00)
        s.assign(s.peripheral_ics(), "periph")
        return s

    return [("plain", none), ("periph-right", periph_right), ("periph-left", periph_left)]


def run_board(board, seeds, passes, opt, out_root, work_root):
    W, H = BOARD_WH.get(board, (100.0, 44.0))
    os.makedirs(os.path.join(work_root, board), exist_ok=True)
    results = []
    for iname, intent in _intents():
        for strat in ("dataflow", "compact"):
            for seed in seeds:
                label = f"{iname}-{strat}-s{seed}"
                t0 = time.monotonic()
                try:
                    s = PlacementSession(board, W=W, H=H, strat=strat, seed=seed)
                    intent(s)
                    out = os.path.join(work_root, board, f"{label}.kicad_pcb")
                    v = s.grade(out=out, keep=True, passes=passes, opt=opt,
                                unconn_finish_tol=2)
                    v["label"] = label
                    v["placed"] = out
                    results.append(v)
                    print(f"[wave] {board} {label}: gate={v.get('gate')} "
                          f"kelvin={v.get('kelvin_ok')} unconn={v.get('unconnected')} "
                          f"foreign={v.get('foreign',{}).get('tracks')}t "
                          f"dT={((v.get('thermal') or {}).get('dT'))} "
                          f"({round(time.monotonic()-t0,1)}s)", flush=True)
                except Exception as e:                              # noqa: BLE001
                    print(f"[wave] {board} {label}: ERROR {type(e).__name__}: {e}", flush=True)
    if not results:
        return None
    results.sort(key=lambda v: tuple(v.get("sort_key") or (9,)))
    best = results[0]
    # publish ONLY the winner (routed board if the route produced one, else the placement)
    pub_dir = os.path.join(out_root, board)
    os.makedirs(pub_dir, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M")
    src = best.get("routed") if best.get("routed") and os.path.isfile(str(best.get("routed"))) \
        else best.get("placed")
    dst = os.path.join(pub_dir, f"{ts}-{best['label']}.kicad_pcb")
    if src and os.path.isfile(str(src)):
        import shutil
        shutil.copy(str(src), dst)
        base = str(src)[:-len(".kicad_pcb")]
        for ext in (".kicad_pro", ".kicad_dru"):
            if os.path.isfile(base + ext):
                shutil.copy(base + ext, dst[:-len(".kicad_pcb")] + ext)
    report = {"board": board, "ts": ts, "W": W, "H": H, "passes": passes, "opt": opt,
              "published": os.path.relpath(dst, ROOT) if src else None,
              "best": {k: best.get(k) for k in
                       ("label", "gate", "kelvin_ok", "diffpair_ok", "drc", "unconnected",
                        "unconn_critical", "foreign", "thermal_ok", "sort_key", "reasons")},
              "ranking": [{"label": v["label"], "gate": v.get("gate"),
                           "sort_key": v.get("sort_key")} for v in results]}
    with open(os.path.join(pub_dir, f"{ts}-wave-report.json"), "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(f"[wave] {board} BEST={best['label']} gate={best.get('gate')} -> {dst}", flush=True)
    return report


def main():
    ap = argparse.ArgumentParser(description="fresh-board synthesis wave (run in-container)")
    ap.add_argument("--boards", default="eps-8pin")
    ap.add_argument("--seeds", default="0,1,2,3")
    ap.add_argument("--passes", type=int, default=16)
    ap.add_argument("--opt", type=int, default=20)
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "fresh"))
    ap.add_argument("--work", default=os.path.join(ROOT, "build", "fresh-work"))
    a = ap.parse_args()
    seeds = [int(x) for x in a.seeds.split(",") if x.strip() != ""]
    for board in [b.strip() for b in a.boards.split(",") if b.strip()]:
        run_board(board, seeds, a.passes, a.opt, a.out, a.work)


if __name__ == "__main__":
    main()
