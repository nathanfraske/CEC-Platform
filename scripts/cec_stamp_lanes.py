#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_stamp_lanes -- stamp a refined cell blueprint across every instance of a
# repeated cell (owner GO 2026-07-11 "stamp them in"; derive-once-stamp-N per
# the uniformity ruling). CONTAINER leg (pcbnew).
#
# Discipline:
#   * Works on a COPY under build/ -- the committed board is the shipped alpha
#     and is never touched by this script.
#   * Per lane: extract the DESTINATION context (stand-ins) from the original
#     board, check the blueprint pose against it, renudge when the context
#     demands (<=0.8mm, no rotation), ESCALATE (skip + report) when even that
#     fails -- never force-fit.
#   * Old cell copper is cleared the way extraction defines cell copper:
#     internal-net tracks wholesale + thin (<0.5mm) port-net tracks fully
#     inside the old cell window.
#   * stamp(lay=True) lays LOCKED copper behind the real collision guard: a
#     cell whose copper would hit foreign copper is refused whole.
#   * EXPECTED aftermath (reported, not hidden): board-level reconnection
#     ratlines on /ISENSEP{n} and +3V3 feeds -- the escape-routing pass (or
#     GUI/FR) reconnects them; the thermal measurement the owner ordered does
#     not depend on those signal stubs.
#
#   sg docker -c "docker compose -f docker/compose.yaml exec -T routing \
#       python3 scripts/cec_stamp_lanes.py --lanes 1,2,3,4,5,6"
import argparse
import copy as _copy
import json
import math
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

BOARD = "beta/12vhpwr-standard/12vhpwr-standard-module.kicad_pcb"
BLUEPRINT = "build/cell-refine/hpwr-RS4-b7/refined-template.json"
OUT_DIR = "build/cell-refine/stamped"
THIN_MM = 0.5                                     # port-net copper below this = cell-owned


def lane_ref_map(n):
    """Blueprint (lane-4) refs -> lane-n refs."""
    return {"RS4": f"RS{n}", "RFH4": f"RFH{n}", "RFL4": f"RFL{n}",
            "CF4": f"CF{n}", "U13": f"U{9 + n}", "C13": f"C{9 + n}"}


def rename_refs(template, ref_map):
    t = _copy.deepcopy(template)
    t["anchor"]["ref"] = ref_map.get(t["anchor"]["ref"], t["anchor"]["ref"])
    t["parts"] = {ref_map.get(r, r): sp for r, sp in t["parts"].items()}
    for bucket in ("ports", "internal_pads"):
        for spec in (t.get(bucket) or {}).values():
            for p in spec.get("pads", []):
                p["ref"] = ref_map.get(p["ref"], p["ref"])
    return t


def clear_old_cell_copper(board, lane, window):
    """Delete the OLD cell's copper (mirrors extraction's cell-copper rule:
    internal nets wholesale, thin port-net copper fully inside the window).
    SWIG discipline, PROBE-VERIFIED 2026-07-11: collect proxies in ONE sweep,
    batch-Remove, and DO NOT call BuildConnectivity() afterwards -- the
    connectivity rebuild after Remove is what poisons every later proxy
    (GetFootprints -> raw SwigPyObject -> segfault); zone refill at the end of
    the apply phase rebuilds connectivity anyway. Read each vector's scalars
    immediately (the 'live GetStart() refs' footgun)."""
    import pcbnew
    internal = {f"/IN{lane}_P", f"/IN{lane}_N"}
    thin_ports = {f"/SENSEP{lane}_HI", f"/SENSEP{lane}_LO", "+3V3"}
    victims = []
    for t in board.GetTracks():
        net = t.GetNetname()
        if t.Type() == pcbnew.PCB_VIA_T:
            continue                              # old cells laid no cell-owned vias
        if net in internal:
            victims.append(t)
            continue
        if net in thin_ports and t.GetWidth() < int(THIN_MM * 1e6):
            s = t.GetStart()
            sx, sy = s.x / 1e6, s.y / 1e6
            e = t.GetEnd()
            ex, ey = e.x / 1e6, e.y / 1e6
            if all(window[0] <= x <= window[1] and window[2] <= y <= window[3]
                   for x, y in ((sx, sy), (ex, ey))):
                victims.append(t)
    for t in victims:
        board.Remove(t)
    return len(victims)


def plan_phase(args):
    """Process A: read ONLY the original board (extract context, renudge where
    the lane demands, produce per-lane stamp data as pure JSON). No mutation."""
    import cec_cell_extract as cx
    import cec_cell_refine as cr

    lanes = [int(x) for x in args.lanes.split(",") if x.strip()]
    os.makedirs(args.out, exist_ok=True)
    bp = json.load(open(args.blueprint))
    bp = _copy.deepcopy(bp)
    bp["vias"] = [{"net_role": "GND", "at_rel_mm": g["at_rel_mm"],
                   "drill_mm": g["drill_mm"], "dia_mm": g["dia_mm"],
                   "layers": ["F.Cu", "B.Cu"]} for g in bp.get("gnd_vias", [])]

    src_index = cx.BoardIndex(args.board)
    plan = {"board": args.board, "blueprint": args.blueprint, "lanes": {}}
    for n in lanes:
        rmap = lane_ref_map(n)
        refs = list(rmap.values())
        anchor = rmap["RS4"]
        t_ctx = cx.extract(args.board, refs, anchor_ref=anchor, index=src_index)
        ax, ay = t_ctx["meta"]["anchor_pos_mm"]
        arot = t_ctx["meta"]["anchor_rot_deg"]
        t_bp = rename_refs(bp, rmap)
        t_bp["standins"] = t_ctx["standins"]
        t_bp["net_roles"] = t_ctx["net_roles"]
        m = cr.CellModel(t_bp)
        status, t_stamp = "verbatim", t_bp
        try:
            routes = cr.synth_routes(m, m.base_pose)
            fails = cr.gates(m, m.base_pose, routes)
        except cr.Refusal as e:
            fails = [str(e)]
        if fails:
            nud = cr.renudge(m, m.base_pose, budget_evals=1500)
            if nud is None:
                plan["lanes"][str(n)] = {"status": "ESCALATE", "reason": fails[:3]}
                continue
            routes2, gv, gs, gm = cr.finalize_cell(m, nud["pose"])
            t_stamp = cr.to_refined_template(m, nud["pose"], routes2)
            t_stamp["internal_tracks"] += [
                {"net_role": "GND", "layer": "F.Cu",
                 "start_rel_mm": [round(sg[0], 4), round(sg[1], 4)],
                 "end_rel_mm": [round(sg[2], 4), round(sg[3], 4)],
                 "width_mm": cr.TRACK_W} for sg in gs]
            t_stamp["vias"] = [{"net_role": "GND", "at_rel_mm": g["at_rel_mm"],
                                "drill_mm": g["drill_mm"], "dia_mm": g["dia_mm"],
                                "layers": ["F.Cu", "B.Cu"]} for g in gv]
            status = "renudged" + ("+gnd:" + ",".join(gm) if gm else "")
        xs, ys = [], []
        for ref in refs:
            bb = src_index.fp(ref).GetBoundingBox()
            xs += [bb.GetLeft() / 1e6, bb.GetRight() / 1e6]
            ys += [bb.GetTop() / 1e6, bb.GetBottom() / 1e6]
        plan["lanes"][str(n)] = {
            "status": status, "template": t_stamp, "at_mm": [ax, ay], "rot": arot,
            "net_map": dict(t_ctx["net_roles"]),
            "window": [min(xs) - 0.5, max(xs) + 0.5, min(ys) - 0.5, max(ys) + 0.5],
        }
    plan_path = os.path.join(args.out, "stamp-plan.json")
    with open(plan_path, "w") as fh:
        json.dump(plan, fh, indent=1)
    print("plan:", plan_path,
          {k: v["status"] for k, v in plan["lanes"].items()})
    return plan_path


def _load(args):
    import pcbnew
    stamped_path = os.path.join(args.out, "12vhpwr-stamped.kicad_pcb")
    return pcbnew, stamped_path, json.load(open(os.path.join(args.out, "stamp-plan.json")))


def phase_copy(args):
    """Subphase 1: make the working copy (no pcbnew)."""
    plan = json.load(open(os.path.join(args.out, "stamp-plan.json")))
    stamped_path = os.path.join(args.out, "12vhpwr-stamped.kicad_pcb")
    shutil.copy(plan["board"], stamped_path)
    for ext in (".kicad_pro", ".kicad_prl", ".kicad_dru"):
        src = plan["board"].replace(".kicad_pcb", ext)
        if os.path.exists(src):
            shutil.copy(src, stamped_path.replace(".kicad_pcb", ext))
    print("copied", flush=True)


def phase_clear(args):
    """Subphase 2 (own process): remove old cell copper for EVERY lane in ONE
    GetTracks sweep + ONE batch Remove, then save and exit. MEASURED
    2026-07-11: iterating GetTracks again after ANY Remove is use-after-free
    roulette on this SWIG build (lane-2 sweep segfaulted after lane-1's
    removals; single-sweep + save survives, matching FR02's discipline)."""
    pcbnew, stamped_path, plan = _load(args)
    board = pcbnew.LoadBoard(stamped_path)
    lanes = {int(n): tuple(lane["window"]) for n, lane in plan["lanes"].items()
             if not lane["status"].startswith("ESCALATE")}
    internal = {net for n in lanes for net in (f"/IN{n}_P", f"/IN{n}_N")}
    thin_by_net = {}
    for n, win in lanes.items():
        for net in (f"/SENSEP{n}_HI", f"/SENSEP{n}_LO"):
            thin_by_net[net] = [win]
        thin_by_net.setdefault("+3V3", []).append(win)
    victims = []
    per_lane = dict.fromkeys(lanes, 0)
    for t in board.GetTracks():
        net = t.GetNetname()
        if t.Type() == pcbnew.PCB_VIA_T:
            continue
        if net in internal:
            victims.append(t)
            lane_n = int("".join(c for c in net.split("_")[0] if c.isdigit()))
            per_lane[lane_n] = per_lane.get(lane_n, 0) + 1
            continue
        wins = thin_by_net.get(net)
        if wins and t.GetWidth() < int(THIN_MM * 1e6):
            s = t.GetStart()
            sx, sy = s.x / 1e6, s.y / 1e6
            e = t.GetEnd()
            ex, ey = e.x / 1e6, e.y / 1e6
            for win in wins:
                if all(win[0] <= x <= win[1] and win[2] <= y <= win[3]
                       for x, y in ((sx, sy), (ex, ey))):
                    victims.append(t)
                    break
    for t in victims:
        board.Remove(t)
    pcbnew.SaveBoard(stamped_path, board)
    with open(os.path.join(args.out, "clear-report.json"), "w") as fh:
        json.dump({"total_removed": len(victims), "internal_by_lane": per_lane}, fh)
    print("cleared", len(victims), flush=True)


def phase_place(args):
    """Subphase 3 (own process): stamp placements + locked copper. No removals
    in this process."""
    import cec_cell_extract as cx
    pcbnew, stamped_path, plan = _load(args)
    board = pcbnew.LoadBoard(stamped_path)
    report = {}
    for n_str, lane in plan["lanes"].items():
        if lane["status"].startswith("ESCALATE"):
            report[n_str] = lane
            continue
        placement, copper = cx.stamp(lane["template"], board,
                                     at_mm=tuple(lane["at_mm"]), rot=lane["rot"],
                                     ref_map={}, net_map=lane["net_map"],
                                     lay=True, apply=True)
        report[n_str] = {"status": lane["status"], "laid": copper.get("laid")}
    pcbnew.SaveBoard(stamped_path, board)
    with open(os.path.join(args.out, "place-report.json"), "w") as fh:
        json.dump(report, fh, indent=1, default=str)
    print("placed", {k: v.get("status") for k, v in report.items()}, flush=True)


def phase_fill(args):
    """Subphase 4 (own process): UnFill-first zone refill (the double-fill
    segfault guard), save, exit."""
    pcbnew, stamped_path, plan = _load(args)
    board = pcbnew.LoadBoard(stamped_path)
    for z in board.Zones():
        z.UnFill()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(stamped_path, board)
    # consolidated report
    cleared = json.load(open(os.path.join(args.out, "clear-report.json")))
    placed = json.load(open(os.path.join(args.out, "place-report.json")))
    by_lane = cleared.get("internal_by_lane", {})
    for n_str in placed:
        if isinstance(placed[n_str], dict):
            placed[n_str]["cleared_internal_tracks"] = by_lane.get(n_str)
    placed["_clear_total"] = cleared.get("total_removed")
    out = {"board": stamped_path, "blueprint": plan["blueprint"], "lanes": placed}
    with open(os.path.join(args.out, "stamp-report.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1), flush=True)


SUBPHASES = {"copy": phase_copy, "clear": phase_clear,
             "place": phase_place, "fill": phase_fill}


def main(argv=None):
    ap = argparse.ArgumentParser(description="stamp the refined blueprint across lanes")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--blueprint", default=BLUEPRINT)
    ap.add_argument("--lanes", default="1,2,3,4,5,6")
    ap.add_argument("--out", default=OUT_DIR)
    ap.add_argument("--phase", default="both",
                    choices=("plan", "both", "copy", "clear", "place", "fill"))
    args = ap.parse_args(argv)
    if args.phase == "plan":
        plan_phase(args)
        return 0
    if args.phase == "both":
        plan_phase(args)
        import subprocess
        for sub in ("copy", "clear", "place", "fill"):
            r = subprocess.run([sys.executable, os.path.abspath(__file__),
                                "--phase", sub, "--out", args.out])
            if r.returncode not in (0,):
                print(f"subphase {sub} FAILED rc={r.returncode}", flush=True)
                return r.returncode
        return 0
    # single subphase: run, flush, hard-exit (pcbnew teardown GC segfaults)
    try:
        SUBPHASES[args.phase](args)
    except BaseException as e:                    # noqa: BLE001
        import traceback
        frames = traceback.extract_tb(e.__traceback__)
        loc = " <- ".join(f"{os.path.basename(f.filename)}:{f.lineno}:{f.name}"
                          for f in frames[-4:])
        print(f"{args.phase} ERROR: {type(e).__name__}: {e} @ {loc}", flush=True)
        sys.stdout.flush()
        os._exit(1)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
