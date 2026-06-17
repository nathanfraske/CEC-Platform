#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# LLM-GUIDED PLACEMENT LOOP -- the actuation-lever pattern pointed at PROACTIVE placement planning.
#
# WHY (owner instinct, proven 2026-06-16): a fully deterministic placer + router cannot close the loop.
# A fresh deterministic eps placement routes cleanly (drc 3 / unconn 2) but fails on PLACEMENT QUALITY:
# kelvin_ok=False (the INA isn't seated for a clean sense tap) and 62 foreign clips into the high-current
# pours. The corridor problem is a GLOBAL graph min-cut (a foreign net whose endpoints straddle a corridor
# crosses it regardless of body nudging), which a local barycentric/anneal placer provably can't solve.
#
# This loop puts an LLM in the placement seat -- it reasons about the global topology a local placer can't:
# seat each INA's sense pins against its shunt (fix Kelvin) and PARTITION the foreign logic so foreign nets
# don't straddle corridors (fix pour integrity). Loop: deterministic seed -> ANALYZE (corridors/crossings/
# kelvin) -> LLM PLAN (moves) -> APPLY+legalize -> MEASURE (route+score) -> iterate, keeping the best.
#
# DUAL MODE (like cec_overnight_directed): the heavy steps (--seed/--analyze/--apply/--measure) run IN the
# routing container (pcbnew + Freerouting); the host --run driver invokes them via `docker compose exec`
# and calls the cloud LLM planner seat host-side. Run the driver from the host:
#   python3 scripts/cec_place_planner.py --run --board modules/eps-8pin --rounds 6

import argparse
import dataclasses
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

# --------------------------------------------------------------------------- container exec (host side)
try:
    import cec_overnight_directed as _ovd
    COMPOSE = _ovd.COMPOSE
    CONTAINER_ROOT = _ovd.CONTAINER_ROOT
except Exception:                                            # host without the module path -> defaults
    COMPOSE = ["docker", "compose", "-f", os.path.join(ROOT, "docker", "compose.yaml")]
    CONTAINER_ROOT = "/workspace"


def _exec_worker(args, timeout=1200):
    """HOST: run THIS script's worker mode inside the routing container; return parsed JSON marker."""
    cmd = COMPOSE + ["exec", "-T", "routing", "python3",
                     f"{CONTAINER_ROOT}/scripts/cec_place_planner.py"] + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out = (r.stdout or "") + ("\n" + r.stderr if r.returncode else "")
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("RESULT_JSON="):
            return json.loads(ln[len("RESULT_JSON="):])
    return {"error": f"worker rc={r.returncode}: {out[-600:]}"}


def _emit(obj):
    print("RESULT_JSON=" + json.dumps(obj, default=str))


# ====================================================================== IN-CONTAINER WORKER (pcbnew)
def _rel(path):
    return os.path.relpath(os.path.abspath(path), ROOT)


def w_seed(board_dir, out_rel, seeds, strategies):
    """Deterministic seed: place_candidates -> best -> materialize to a real board."""
    import pcbnew
    import cec_synth_pipeline as sp
    pcb = os.path.join(board_dir, [f for f in os.listdir(board_dir) if f.endswith(".kicad_pcb")][0])
    b = pcbnew.LoadBoard(pcb)
    bb = b.GetBoardEdgesBoundingBox()
    W, H = round(bb.GetWidth() / 1e6, 1), round(bb.GetHeight() / 1e6, 1)
    del b
    cfg = sp.Config.load(board_dir)
    cands = sp.place_candidates(cfg, W, H, strategies=strategies, seeds=tuple(seeds), max_workers=1)
    best = min(cands, key=sp._candidate_sort_key)
    sp.materialize(best, cfg, os.path.join(ROOT, out_rel))
    return {"out": out_rel, "W": W, "H": H, "corridor_cross": best.corridor_cross, "residual": best.residual}


def _board_P_comps(board):
    """{ref:(x,y,rotdeg)} positions + {ref:libid} footprints from a loaded board."""
    P, comps = {}, {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        P[ref] = (fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6, fp.GetOrientationDegrees())
        fid = fp.GetFPID()
        comps[ref] = f"{fid.GetLibNickname()}:{fid.GetLibItemName()}"
    return P, comps


def w_analyze(board_pcb, board_dir):
    """The placement CONTEXT the LLM planner reasons on: outline, parts (role/pos/size), corridors,
    the foreign nets crossing each corridor (the partition violations), and the per-cable Kelvin-tap
    geometry. Pure geometry (no route) so it is cheap; MEASURE adds the routed kelvin_ok/drc/clips.
    *board_dir* is the ORIGINAL module dir (its .net / Config), distinct from the working board_pcb."""
    import pcbnew
    import cec_pcb
    import cec_synth_pipeline as sp
    board = pcbnew.LoadBoard(board_pcb)
    bb = board.GetBoardEdgesBoundingBox()
    W, H = round(bb.GetWidth() / 1e6, 1), round(bb.GetHeight() / 1e6, 1)
    nl = sp.View(sp.Config.load(board_dir)).nl
    P, comps = _board_P_comps(board)

    # parts: role + position + courtyard half-extent
    parts = []
    for ref in sorted(P):
        c = nl.comps.get(ref, sp.Comp(ref))
        role = sp._role(ref, c.value, c.footprint, nl=nl) or "passive"
        x, y, rot = P[ref]
        try:
            cx, cy, hw, hh = sp._courtyard_info(comps.get(ref, ""), rot)
        except Exception:
            hw = hh = 1.0
        parts.append({"ref": ref, "role": role, "value": (c.value or "")[:24],
                      "x": round(x, 1), "y": round(y, 1), "w": round(2 * hw, 1), "h": round(2 * hh, 1)})

    # corridors (the formed high-current bands) + per-cable sense IC + shunt
    model = sp.build_corridor_model(nl, {r: P[r] for r in P}, comps, board_w=W)
    corridors = []
    for cab in model.cables:
        x0, x1, y0, y1 = cab.band
        corridors.append({"base": cab.base, "hi": cab.hi, "lo": cab.lo, "shunt": cab.shunt,
                          "sense_ics": sorted(cab.sense_ics), "formed": cab.formed,
                          "band": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]})

    # crossings: which FOREIGN net straddles which corridor (the min-cut violations) -- the predicate
    # from corridor_cross_count, but reporting the (net, corridor) pairs so the LLM can target them.
    pads_by_net = {}
    for net, nodes in nl.nets.items():
        pts = []
        for ref, pin in nodes:
            if ref in P and ref in comps:
                try:
                    pts.append(cec_pcb.pad_global(ref, pin, {ref: P[ref]}, comps))
                except Exception:
                    pts.append((P[ref][0], P[ref][1]))
        if pts:
            pads_by_net[net] = pts
    corridor_nets = model.corridor_nets
    bands = {c.base: c.band for c in model.cables if c.formed}
    crossings = []
    for net, pts in pads_by_net.items():
        if net in corridor_nets or len(pts) < 2:
            continue
        if sp._corridor_net_role(net, corridor_nets) != "signal":
            continue
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        for base, (X0, X1, Y0, Y1) in bands.items():
            if max(ys) >= Y0 and min(ys) <= Y1 and min(xs) < X0 and max(xs) > X1:
                # which refs sit each side -> the LLM knows what to move/cluster
                left = sorted({r for r, _ in nl.nets.get(net, []) if r in P and P[r][0] < X0})
                right = sorted({r for r, _ in nl.nets.get(net, []) if r in P and P[r][0] > X1})
                crossings.append({"net": net, "corridor": base, "left_refs": left, "right_refs": right})

    # Kelvin-tap geometry: distance from each cable's sense IC to its shunt (small = clean tap)
    kelvin = []
    for cab in model.cables:
        sh = cab.shunt
        for ic in sorted(cab.sense_ics):
            if sh in P and ic in P:
                d = round(((P[sh][0] - P[ic][0]) ** 2 + (P[sh][1] - P[ic][1]) ** 2) ** 0.5, 1)
                kelvin.append({"cable": cab.base, "sense_ic": ic, "shunt": sh, "ic_to_shunt_mm": d})

    return {"outline": {"W": W, "H": H}, "parts": parts, "corridors": corridors,
            "crossings": crossings, "kelvin_tap": kelvin,
            "corridor_cross": len(crossings)}


def w_apply(board_pcb, moves, out_rel):
    """Apply LLM moves (ref -> x,y[,rot]) then legalize against the true courtyards; write out_rel.
    Reuses cec_synth_pipeline.legalize_pack so an overlapping proposal is resolved, never shipped raw."""
    import pcbnew
    import cec_synth_pipeline as sp
    board = pcbnew.LoadBoard(board_pcb)
    bb = board.GetBoardEdgesBoundingBox()
    W, H = bb.GetWidth() / 1e6, bb.GetHeight() / 1e6
    P, comps = _board_P_comps(board)
    applied = []
    for mv in moves:
        ref = mv.get("ref")
        if ref not in P:
            continue
        x = float(mv.get("x", P[ref][0])); y = float(mv.get("y", P[ref][1]))
        rot = float(mv.get("rot", P[ref][2]))
        x = max(0.5, min(W - 0.5, x)); y = max(0.5, min(H - 0.5, y))   # keep on-board
        P[ref] = (x, y, rot)
        applied.append(ref)
    # legalize ONLY the moved parts against everything (movers yield to fixed neighbours)
    cyinfo = {}
    for r in P:
        try:
            cyinfo[r] = sp._courtyard_info(comps.get(r, ""), P[r][2])
        except Exception:
            cyinfo[r] = (0.0, 0.0, 1.0, 1.0)
    sp.legalize_pack(P, applied, cyinfo, W, H, clr=0.45)
    # write back
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if ref in P:
            x, y, rot = P[ref]
            fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
            fp.SetOrientationDegrees(rot)
    pcbnew.SaveBoard(os.path.join(ROOT, out_rel), board)
    del board
    return {"out": out_rel, "applied": applied}


def w_measure(board_pcb, passes, opt_time):
    """Route the placement (no keepout/intents -- pure route) + score: kelvin_ok, drc, unconnected,
    and the ACTUAL foreign F.Cu clips into the high-current pours (the pour-integrity signal)."""
    import pcbnew
    import cec_fr
    import cec_score
    b = pcbnew.LoadBoard(board_pcb)
    pours = cec_fr.derive_power_pours(board_pcb, board=b)
    del b
    routed = os.path.join(tempfile.mkdtemp(), "routed.kicad_pcb")
    c = cec_fr.route_once(board_pcb, routed, hints=[], power_pours=pours, passes=passes, opt_time=opt_time)
    if not (c.ok and c.board):
        return {"error": f"route failed: {getattr(c, 'err', None)}"}
    m = dataclasses.asdict(cec_score.score(c.board))
    # actual clips
    rb = pcbnew.LoadBoard(c.board)
    Z = {}
    for z in rb.Zones():
        nn = z.GetNetname()
        if (nn.endswith("_HI") or nn.endswith("_LO")) and z.IsOnLayer(pcbnew.F_Cu):
            sp_ = z.GetFilledPolysList(pcbnew.F_Cu); bb = z.GetBoundingBox()
            Z[nn] = {"isl": sp_.OutlineCount(), "bb": [bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()], "x": 0}
    for t in rb.GetTracks():
        if t.GetClass() != "PCB_TRACK" or t.GetLayer() != pcbnew.F_Cu:
            continue
        tn = t.GetNetname(); s = t.GetStart(); e = t.GetEnd()
        for nn, z in Z.items():
            if tn == nn or tn.endswith("GND"):
                continue
            l, tp, r, bm = z["bb"]
            if min(s.x, e.x) <= r and max(s.x, e.x) >= l and min(s.y, e.y) <= bm and max(s.y, e.y) >= tp:
                z["x"] += 1
    del rb
    return {"kelvin_ok": bool(m.get("kelvin_ok")), "diffpair_ok": bool(m.get("diffpair_ok")),
            "gates_pass": bool(m.get("gates_pass")), "drc": m.get("drc"), "unconnected": m.get("unconnected"),
            "clips": sum(z["x"] for z in Z.values()), "fragmented_pours": sum(1 for z in Z.values() if z["isl"] > 1)}


# ====================================================================== HOST: the LLM planner seat
MOVE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["diagnosis", "moves"],
    "properties": {
        "diagnosis": {"type": "string", "description": "the global placement problem you see"},
        "moves": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["ref", "x", "y", "rationale"],
            "properties": {
                "ref": {"type": "string"},
                "x": {"type": "number", "description": "new centre x in mm"},
                "y": {"type": "number", "description": "new centre y in mm"},
                "rot": {"type": "number", "description": "rotation in degrees (optional)"},
                "rationale": {"type": "string"},
            }}},
    },
}

_PLANNER_SYSTEM = (
    "You are the PLACEMENT PLANNER for a CEC power-telemetry interposer PCB. You reason about GLOBAL "
    "placement topology a local/deterministic placer cannot. The board is a high-current interposer: each "
    "cable is a vertical CORRIDOR J_IN (top) -> SHUNT -> J_OUT (bottom); that band is filled by a SOLID "
    "high-current copper POUR on F.Cu+B.Cu (the only routable layers -- the inner layers are GND planes). "
    "TWO hard placement-quality goals:\n"
    "1. CLEAN KELVIN: each cable's sense IC (INA*) must sit IMMEDIATELY ADJACENT to its shunt's INNER "
    "(board-facing) edge so the Kelvin sense tap is short and does not cross the corridor. Minimise "
    "ic_to_shunt_mm.\n"
    "2. CORRIDOR PARTITION (the min-cut): a FOREIGN signal net whose pads straddle a corridor (pads both "
    "LEFT and RIGHT of the band, overlapping its y-range) is FORCED to cross the solid pour and CLIP it "
    "(the 62-clip failure). Move the parts so foreign nets do NOT straddle any corridor: cluster the shared "
    "logic (ESP/U1, CAN, the per-cable detection amps' downstream) so each foreign net lives entirely on "
    "ONE side of every corridor, OR open a clear top/bottom channel so it can route around. The cable "
    "connectors (J_IN*/J_OUT*) and shunts (RS*) are FIXED corridor anchors -- do NOT move them.\n"
    "Output absolute mm moves (board origin top-left, x right, y down) within the outline. Move only what "
    "you must; every move needs a rationale tied to goal 1 or 2."
)


def plan_moves(context, prev_measure, model=None, timeout=360):
    """HOST: ask the planner seat for placement moves given the analyzed context + last measure.
    Uses the local broker (a RAW single json-schema completion) -- NOT `claude -p`, which is the agentic
    Claude Code harness and runs a tool-using loop that times out on a substantial prompt. cec-manager-fast
    (gpt-oss-120b) is the manager-class fast seat; a cloud model name routes through _is_cloud if ever wanted."""
    import cec_judge_local as jl
    user = (
        "BOARD CONTEXT (current placement):\n" + json.dumps(context, indent=1)[:9000] + "\n\n"
        + ("LAST ROUTE MEASURE: " + json.dumps(prev_measure) + "\n\n" if prev_measure else "")
        + "Propose the placement MOVES that (1) seat each sense IC against its shunt for a clean Kelvin "
        "tap and (2) eliminate the corridor crossings (the `crossings` list -- each names the net + which "
        "refs are left/right of the band). Keep J_IN*/J_OUT*/RS* fixed. Return diagnosis + moves."
    )
    return jl._chat_json(_PLANNER_SYSTEM, user, MOVE_SCHEMA, name="placeplan",
                         model=model or "cec-manager-fast", timeout=timeout)


# ====================================================================== HOST: the iterate driver
def run(board_dir, rounds, *, model=None, seeds=(0, 1, 2, 3), out_dir=None, passes=16, opt_time=32):
    import cec_synth_pipeline as sp                          # noqa: F401  (ensure path)
    out_dir = out_dir or os.path.join("build", "place-planner")
    os.makedirs(os.path.join(ROOT, out_dir), exist_ok=True)
    board_name = os.path.basename(board_dir.rstrip("/"))
    strategies = ["dataflow", "thermal_separated", "compact"]

    def log(m):
        print(f"[planner] {m}", flush=True)

    # 0. deterministic seed
    seed_out = f"{out_dir}/{board_name}-r0.kicad_pcb"
    s = _exec_worker(["--seed", "--board", _rel(board_dir), "--out", seed_out,
                      "--seeds", ",".join(map(str, seeds)), "--strategies", ",".join(strategies)])
    if s.get("error"):
        log(f"seed failed: {s['error']}"); return {"error": s["error"]}
    log(f"seed: {seed_out} corridor_cross={s.get('corridor_cross')} ({s['W']}x{s['H']}mm)")
    cur = seed_out
    best = {"board": None, "score": (1, 9999, 9999)}         # (gate_fail, clips, drc) lower=better
    history = []

    for rnd in range(rounds):
        ctx = _exec_worker(["--analyze", "--board-pcb", cur, "--board", _rel(board_dir)])
        if ctx.get("error"):
            log(f"r{rnd} analyze failed: {ctx['error']}"); break
        meas = _exec_worker(["--measure", "--board-pcb", cur, "--passes", str(passes), "--opt-time", str(opt_time)])
        log(f"r{rnd}: corridor_cross={ctx.get('corridor_cross')} | route kelvin={meas.get('kelvin_ok')} "
            f"gates={meas.get('gates_pass')} drc={meas.get('drc')} clips={meas.get('clips')} "
            f"unconn={meas.get('unconnected')}")
        sc = (0 if meas.get("gates_pass") else 1, meas.get("clips", 9999) or 9999, meas.get("drc", 9999) or 9999)
        history.append({"round": rnd, "board": cur, "measure": meas, "corridor_cross": ctx.get("corridor_cross")})
        if sc < best["score"]:
            best = {"board": cur, "score": sc, "measure": meas}
        if meas.get("gates_pass"):
            log(f"r{rnd}: GATES PASS -> converged"); break
        if rnd == rounds - 1:
            break
        plan = plan_moves(ctx, meas, model=model)
        moves = (plan or {}).get("moves") or []
        log(f"r{rnd}: planner '{(plan or {}).get('diagnosis','')[:80]}' -> {len(moves)} move(s)")
        if not moves:
            log(f"r{rnd}: no moves -> stop"); break
        nxt = f"{out_dir}/{board_name}-r{rnd + 1}.kicad_pcb"
        ap = _exec_worker(["--apply", "--board-pcb", cur, "--out", nxt,
                           "--moves", json.dumps(moves)])
        if ap.get("error"):
            log(f"r{rnd} apply failed: {ap['error']}"); break
        cur = nxt
    log(f"DONE: best gates={best.get('measure',{}).get('gates_pass')} "
        f"clips={best.get('measure',{}).get('clips')} -> {best.get('board')}")
    json.dump({"best": best, "history": history},
              open(os.path.join(ROOT, out_dir, f"{board_name}-result.json"), "w"), indent=1, default=str)
    return {"best": best, "history": history}


def main(argv=None):
    ap = argparse.ArgumentParser(description="LLM-guided placement loop")
    ap.add_argument("--run", action="store_true", help="HOST driver")
    ap.add_argument("--seed", action="store_true"); ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--measure", action="store_true")
    ap.add_argument("--board"); ap.add_argument("--board-pcb"); ap.add_argument("--out")
    ap.add_argument("--moves"); ap.add_argument("--seeds", default="0,1,2,3"); ap.add_argument("--strategies",
                    default="dataflow,thermal_separated,compact")
    ap.add_argument("--rounds", type=int, default=6); ap.add_argument("--model", default=None)
    ap.add_argument("--passes", type=int, default=16); ap.add_argument("--opt-time", type=int, default=32)
    a = ap.parse_args(argv)
    if a.run:
        run(a.board, a.rounds, model=a.model, passes=a.passes, opt_time=a.opt_time)
    elif a.seed:
        _emit(w_seed(os.path.join(ROOT, a.board), a.out, [int(s) for s in a.seeds.split(",")], a.strategies.split(",")))
    elif a.analyze:
        _emit(w_analyze(os.path.join(ROOT, a.board_pcb) if not os.path.isabs(a.board_pcb) else a.board_pcb,
                        os.path.join(ROOT, a.board)))
    elif a.apply:
        _emit(w_apply(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                      json.loads(a.moves), a.out))
    elif a.measure:
        _emit(w_measure(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                        a.passes, a.opt_time))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
