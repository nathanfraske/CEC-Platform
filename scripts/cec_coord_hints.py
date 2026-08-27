#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
cec_coord_hints -- T3: compile the co-coordinating router's NEGOTIATED corridors into
FR-binding waypoints (owner GO 2026-07-08 "implement it up... get it in").

The chain: cec_coord_router negotiates all nets simultaneously (PathFinder congestion)
-> this module picks the K nets whose paths cross the most CONTENDED non-escape cells
-> for each, ONE waypoint at a calm cell of its negotiated corridor -> cec_fr02
compiles them as DRC-legal LOCKED stubs -> route_once(protect_nets=...) upgrades them
fix->protect in the DSN (FR 1.7.0 DROPS unprotected fix wires, measured) -> FR routes
those nets THROUGH their negotiated corridors. Keepouts cannot express per-net
reservations (they are net-blind); the locked-stub mechanism is the one FR-binding
per-net channel this pipeline has (FR-02, bench-proven).

The GATE for this whole feature is the pinned-seed A/B (`ab` CLI): the same placement
routed with vs without coordination -- coordination counts ONLY if unconn/DRC improve.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _grid_origin(board_path):
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    bb = b.GetBoardEdgesBoundingBox()
    return bb.GetLeft() / 1e6, bb.GetTop() / 1e6


def coord_intents(board_path, *, k=8, iters=60, grid_mm=0.5, backend="auto",
                  escape_radius=2, exclude_nets_re=None, preferred_nets=None):
    """Run the negotiation and derive <=k single-waypoint intents for the most
    CONTENDED nets. Waypoint = the cell of the net's own negotiated path nearest its
    midpoint that is neither overused nor inside a pin-escape region (we pin the net
    to the calm part of ITS OWN corridor -- never to a conflict cell)."""
    import re
    import pcbnew
    import cec_coord_router as ccr
    import cec_fr02
    conns, H, W, foreign, stackup = ccr.build_problem(
        board_path, grid_mm=grid_mm, detailed=True)
    blocked_cells = stackup.pop("_blocked_cells_by_conn", ())
    res = ccr.route_problem(conns, H, W, grid_mm=grid_mm, iters=iters,
                            foreign_cells=foreign, backend=backend,
                            blocked_cells_by_conn=blocked_cells,
                            L=len(stackup["layer_names"]),
                            layer_names=stackup["layer_names"],
                            allowed_layers=stackup["allowed_layers_by_conn"],
                            cost_mode="fixed")
    usage = res["usage"]
    cap = ccr._capacity(grid_mm)
    # escape mask: cells within escape_radius of any terminal (pin-escape domain)
    term = set()
    for _n, a, b in conns:
        for (_l, y, x) in (a, b):
            for dy in range(-escape_radius, escape_radius + 1):
                for dx in range(-escape_radius, escape_radius + 1):
                    term.add((y + dy, x + dx))

    def _over(l, y, x):
        try:
            return float(usage[l][y][x]) > cap
        except Exception:                                # noqa: BLE001
            return False

    scored = []
    pref = set(preferred_nets or ())
    for i, (net, _a, _b) in enumerate(conns):
        if exclude_nets_re and re.search(exclude_nets_re, net):
            continue
        if pref and net not in pref:
            continue                # REACTIVE mode: hint only nets that actually failed
        path = res["paths_by_conn"][i] or []
        contended = sum(1 for (l, y, x) in path
                        if _over(l, y, x) and (y, x) not in term)
        if contended:
            scored.append((contended, i, net, path))
    scored.sort(key=lambda t: -t[0])
    x0, y0 = _grid_origin(board_path)
    physical_board = pcbnew.LoadBoard(board_path)
    # A protected 0.6 mm mark is long enough to bind the negotiated corridor
    # but small enough to fit dense fanout.  It retains the compiler's exact
    # full-segment clearance check and may move by at most one grid cell.
    coord_stub_len_mm = 0.6
    coord_stub_width_mm = 0.22
    coord_nudge_mm = grid_mm
    intents, seen_nets = [], set()
    for contended, i, net, path in scored:
        if net in seen_nets or len(intents) >= k:
            continue
        mid = len(path) // 2
        # calm cell of its own corridor nearest the midpoint
        cand = sorted(range(len(path)), key=lambda j: abs(j - mid))
        waypoint = None
        for j in cand:
            l, y, x = path[j]
            if _over(l, y, x) or (y, x) in term:
                continue
            layer_name = stackup["layer_names"][l]
            at_mm = [x0 + (x + 0.5) * grid_mm,
                     y0 + (y + 0.5) * grid_mm]
            clear_at = cec_fr02.find_clear_waypoint_mm(
                physical_board, net, layer_name, at_mm,
                stub_len_mm=coord_stub_len_mm,
                width_mm=coord_stub_width_mm,
                nudge_mm=coord_nudge_mm)
            if clear_at is not None:
                waypoint = (l, clear_at)
                break
        if waypoint is None:
            continue
        l, clear_at = waypoint
        intents.append({"net": net,
                        "layers": [stackup["layer_names"][l]],
                        "waypoints": [{"at_mm": [round(clear_at[0], 3),
                                                 round(clear_at[1], 3)]}],
                        "stub_len_mm": coord_stub_len_mm,
                        "width_mm": coord_stub_width_mm,
                        "nudge_mm": coord_nudge_mm,
                        "_contended_cells": contended})
        seen_nets.add(net)
    return {"intents": intents, "negotiation": {
        "residual": res["residual_overuse"], "residual_escaped": res["residual_overuse_escaped"],
        "iters": res["iters_used"], "backend": res["backend"], "wall_s": res["wall_s"],
        "layers": stackup["layer_names"], "cost_mode": res["cost_mode"],
        "congestion": res["congestion"]}}


def stub_board(board_path, out_path, *, k=8, iters=60, grid_mm=0.5, backend="auto",
               preferred_nets=None):
    """coord_intents -> cec_fr02.compile_intents: a COPY of the placement carrying
    DRC-legal LOCKED stubs on the negotiated corridors. Returns the manifest
    (intents + compile result + the nets to protect at DSN time)."""
    import cec_fr02
    ci = coord_intents(board_path, k=k, iters=iters, grid_mm=grid_mm, backend=backend,
                       preferred_nets=preferred_nets)
    if not ci["intents"]:
        return {"nets": [], "compiled": None, **ci}
    comp = cec_fr02.compile_intents(board_path, ci["intents"], out_path)
    nets = sorted({s["net"] for s in comp["stubs"]})
    return {"nets": nets, "compiled": {"stubs": len(comp["stubs"]),
                                       "failures": comp["failures"]},
            "board": out_path, **ci}


def ab_route(placed_board, *, seed=0, passes=8, opt=10, k=8, iters=60,
             fr_timeout=1200, work=None):
    """THE GATE: pinned-seed A/B. Arm A = the oracle recipe as-is; arm B = the same
    placement carrying coord stubs, routed with protect_nets. Same seed, same effort,
    same conjunction. Returns both verdicts + the delta."""
    import tempfile
    import cec_synth_pipeline as csp
    work = work or tempfile.mkdtemp(prefix="cec_coord_ab_")
    os.makedirs(work, exist_ok=True)
    a = csp.route_oracle_grade(placed_board, route=True, seed=seed, passes=passes,
                               opt=opt, fr_timeout=fr_timeout, thermal="lazy",
                               work_dir=os.path.join(work, "A"), keep=True)
    stub = os.path.join(work, "stubbed.kicad_pcb")
    # REACTIVE (first A/B verdict 2026-07-08: blind mid-corridor pins LOST, unconn
    # 99->107 -- 8 hard constraints stole FR freedom it didn't need help with).
    # Hint ONLY nets the bare route actually left unconnected; their negotiated
    # corridor is the coordination signal for exactly the nets that need it.
    failed = set(a.get("unconn_nets") or [])
    man = stub_board(placed_board, stub, k=k, iters=iters,
                     preferred_nets=(failed or None))
    for ext in (".kicad_pro", ".kicad_dru"):
        s = placed_board[:-len(".kicad_pcb")] + ext
        if os.path.isfile(s):
            import shutil
            shutil.copy(s, stub[:-len(".kicad_pcb")] + ext)
    if not man["nets"]:
        return {"a": a, "b": None, "manifest": man,
                "verdict": "NO-OP (no contended nets -> no stubs)"}
    b = csp.route_oracle_grade(stub, route=True, seed=seed, passes=passes,
                               opt=opt, fr_timeout=fr_timeout, thermal="lazy",
                               protect_nets=man["nets"],
                               work_dir=os.path.join(work, "B"), keep=True)
    keys = ("gate", "unconnected", "drc", "kelvin_ok", "diffpair_ok")
    delta = {kk: (a.get(kk), b.get(kk)) for kk in keys}
    better = (b.get("unconnected", 1 << 30) < a.get("unconnected", 1 << 30)) or \
             (b.get("unconnected") == a.get("unconnected")
              and b.get("drc", 1 << 30) < a.get("drc", 1 << 30))
    return {"a": {kk: a.get(kk) for kk in keys}, "b": {kk: b.get(kk) for kk in keys},
            "delta": delta, "manifest": {"nets": man["nets"],
                                         "negotiation": man["negotiation"],
                                         "compiled": man["compiled"]},
            "verdict": "B-BETTER" if better else "A-BETTER-OR-EQUAL", "work": work}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="coord-router -> FR hints (locked stubs) + A/B")
    ap.add_argument("board", help="a PLACED .kicad_pcb")
    ap.add_argument("--ab", action="store_true", help="run the pinned-seed A/B (routes twice)")
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--iters", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--passes", type=int, default=8)
    ap.add_argument("--opt", type=int, default=10)
    a = ap.parse_args()
    if a.ab:
        out = ab_route(a.board, seed=a.seed, passes=a.passes, opt=a.opt, k=a.k,
                       iters=a.iters)
    else:
        out = coord_intents(a.board, k=a.k, iters=a.iters)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
