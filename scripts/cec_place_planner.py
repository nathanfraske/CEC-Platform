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
            "region_boxes": _region_boxes(model, W, H),
            "corridor_cross": len(crossings)}


def w_apply(board_pcb, moves, out_rel, board_dir=None):
    """Apply LLM moves (ref -> x,y[,rot]) then legalize against the true courtyards; write out_rel.
    Reuses cec_synth_pipeline.legalize_pack so an overlapping proposal is resolved, never shipped raw.
    CLUSTER-CARRYING: when an IC moves, its OWNED decoupling passives move by the SAME delta -- otherwise
    a passive carrying a crossing net (+3V3/+5VSB/I2C pull-up) is stranded behind and the net still clips
    (the measured reason a foreign-IC-only cluster only reached 62 clips). Owner map from derive_passive_spec
    (netlist) when board_dir is given, else a passives-stay fallback."""
    import pcbnew
    import cec_synth_pipeline as sp
    board = pcbnew.LoadBoard(board_pcb)
    bb = board.GetBoardEdgesBoundingBox()
    W, H = bb.GetWidth() / 1e6, bb.GetHeight() / 1e6
    P, comps = _board_P_comps(board)
    owner = {}                                              # passive ref -> owner IC (for cluster-carrying)
    if board_dir:
        try:
            nl = sp.View(sp.Config.load(board_dir)).nl
            ics = [r for r in P if r[:1] == "U" and not r.startswith("SW")]
            pas = [r for r in P if r[:1] in ("R", "C") and r[1:2].isdigit()]
            owner = {pref: own for pref, (own, _pad) in sp.derive_passive_spec(nl, pas, ics).items()}
        except Exception:                                  # noqa: BLE001 -- ownership is best-effort
            owner = {}
    by_owner = {}
    for pref, own in owner.items():
        by_owner.setdefault(own, []).append(pref)
    applied = []
    for mv in moves:
        ref = mv.get("ref")
        if ref not in P:
            continue
        x = float(mv.get("x", P[ref][0])); y = float(mv.get("y", P[ref][1]))
        rot = float(mv.get("rot", P[ref][2]))
        x = max(0.5, min(W - 0.5, x)); y = max(0.5, min(H - 0.5, y))   # keep on-board
        dx, dy = x - P[ref][0], y - P[ref][1]
        P[ref] = (x, y, rot)
        applied.append(ref)
        for pref in by_owner.get(ref, []):                 # carry the owned passive cluster by the SAME delta
            if pref in P:
                px, py, prot = P[pref]
                P[pref] = (max(0.5, min(W - 0.5, px + dx)), max(0.5, min(H - 0.5, py + dy)), prot)
                applied.append(pref)
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


def _tile_into_box(refs, cyfn, box, *, gap=0.6):
    """Shelf-tile *refs*' courtyards into *box*=[x0,y0,x1,y1] (biggest-first, row-wrapped). cyfn(ref) ->
    (cx,cy,hw,hh) = courtyard centre-offset + half-extent at the placed rotation. Returns origin-target
    moves [{ref,x,y}] (origin = courtyard top-left placement - the centre offset). w_apply's legalize then
    snaps to the nearest free slot, so a slightly-overflowing box just spills to legalize, never overlaps."""
    x0, y0, x1, y1 = box
    order = sorted([r for r in refs], key=lambda r: -(cyfn(r)[2] * cyfn(r)[3]))
    moves, x, y, row_h = [], x0, y0, 0.0
    for r in order:
        cx, cyy, hw, hh = cyfn(r)
        w, h = 2 * hw, 2 * hh
        if x + w > x1 and x > x0:                            # wrap to the next shelf row
            x, y, row_h = x0, y + row_h + gap, 0.0
        ox = x + hw - cx
        oy = max(y0 + hh - cyy, min(max(y0, y1 - hh) - cyy, y + hh - cyy))
        moves.append({"ref": r, "x": round(ox, 2), "y": round(oy, 2)})
        x += w + gap
        row_h = max(row_h, h)
    return moves


def _region_boxes(model, W, H, *, margin=1.0):
    """Named PLACEMENT REGIONS for the LLM partition -- the spatial channels foreign logic can occupy
    WITHOUT its nets being forced to straddle a high-current corridor pour. Derived from the formed
    corridors (band = x0,y0,x1,y1; the pour spans only the band's y-range, so above/below it is clear):
      left/right  = left of the leftmost / right of the rightmost corridor (full board height)
      spine{k}    = the vertical gap BETWEEN corridor k and k+1 (reaches the inner-edge sense ICs of both
                    neighbours without crossing either pour) -- may be narrow
      top/bottom  = the horizontal channel ABOVE / BELOW all the pours (full board width) -- the clear
                    route-around path a power rail uses to feed every corridor's sense ICs
    A region narrower/shorter than a tiny floor is omitted (no false handle for the LLM)."""
    bands = sorted((c.band for c in model.cables if c.formed), key=lambda b: b[0])  # band=(x0,x1,y0,y1)
    if not bands:
        return {"right": [round(W * 0.5, 1), margin, round(W - margin, 1), round(H - margin, 1)]}
    yb_top = min(b[2] for b in bands)                        # highest pour top y0 (clear above)
    yb_bot = max(b[3] for b in bands)                        # lowest  pour bottom y1 (clear below)
    boxes = {}
    if bands[0][0] - margin - margin > 3:
        boxes["left"] = [margin, margin, round(bands[0][0] - margin, 1), round(H - margin, 1)]
    multi = len(bands) > 2
    for i in range(len(bands) - 1):
        gx0, gx1 = bands[i][1] + margin, bands[i + 1][0] - margin   # corridor i right edge .. corridor i+1 left edge
        if gx1 - gx0 > 3:
            boxes[f"spine{i + 1}" if multi else "spine"] = [round(gx0, 1), margin, round(gx1, 1), round(H - margin, 1)]
    boxes["right"] = [round(bands[-1][1] + margin, 1), margin, round(W - margin, 1), round(H - margin, 1)]
    if yb_top - margin - margin > 3:
        boxes["top"] = [margin, margin, round(W - margin, 1), round(yb_top - margin, 1)]
    if H - margin - (yb_bot + margin) > 3:
        boxes["bottom"] = [margin, round(yb_bot + margin, 1), round(W - margin, 1), round(H - margin, 1)]
    return boxes


def _foreign_refs(P, model):
    """The movable foreign ICs/diodes (NOT corridor anchors J*/RS*/sense-INAs)."""
    corridor_refs = {p for c in model.cables for p in ({c.shunt} | set(c.sense_ics))}
    corridor_refs |= {r for r in P if r.startswith("J")}
    return [p for p in sorted(P)
            if p not in corridor_refs and p[:1] in ("U", "D", "L", "Q", "Y", "X") and not p.startswith("SW")]


def _shelf_moves(board_pcb, board_dir, region="right", refs=None, *, gap=0.6):
    """DETERMINISTIC shelf-pack TARGETS for the partition materializer (the lever the 2026-06-16 auditor
    run pointed at). The auditor reasons the partition CORRECTLY but emitting ABSOLUTE (x,y) per IC gets
    scrambled by legalize+route -- so let the LLM own only the PARTITION and let THIS lay it out cleanly.
    region='right'|'left' or a named _region_boxes region or an explicit 'x0,y0,x1,y1' box; refs (optional)
    overrides the auto foreign-IC set."""
    import pcbnew
    import cec_synth_pipeline as sp
    board = pcbnew.LoadBoard(board_pcb)
    bb = board.GetBoardEdgesBoundingBox()
    W, H = round(bb.GetWidth() / 1e6, 1), round(bb.GetHeight() / 1e6, 1)
    P, comps = _board_P_comps(board)
    nl = sp.View(sp.Config.load(board_dir)).nl
    model = sp.build_corridor_model(nl, {r: P[r] for r in P}, comps, board_w=W)
    boxes = _region_boxes(model, W, H)
    if region in boxes:
        box = boxes[region]
    elif "," in region:
        v = [float(t) for t in region.split(",")]; box = [v[0], v[1], v[2], v[3]]
    else:                                                   # 'right'/'left' fall back to the named box
        box = boxes.get("right" if region != "left" else "left", [W * 0.5, 1.0, W - 1.0, H - 1.0])
    pack = [r for r in (refs if refs else _foreign_refs(P, model)) if r in P]

    def cy(ref):
        try:
            return sp._courtyard_info(comps.get(ref, ""), P[ref][2])
        except Exception:                                  # noqa: BLE001
            return (0.0, 0.0, 1.0, 1.0)

    moves = _tile_into_box(pack, cy, box, gap=gap)
    del board
    return {"moves": moves, "region_box": [round(v, 1) for v in box], "packed": [m["ref"] for m in moves]}


def w_partition(board_pcb, assign, out_rel, board_dir):
    """REGION-AWARE partition materializer (2026-06-17). *assign* = [{ref, region}] from the LLM: each
    foreign IC assigned to a named _region_boxes region. Tile each region's refs into its box (deterministic,
    clean -- no absolute-coord scramble), collect the moves, then w_apply (carry owned passives + legalize).
    This is the representation the auditor needed: it reasons the partition (regions) correctly, this executes
    it. Unknown regions / unassigned foreign ICs are left where they are."""
    import pcbnew
    import cec_synth_pipeline as sp
    board = pcbnew.LoadBoard(board_pcb)
    bb = board.GetBoardEdgesBoundingBox()
    W, H = round(bb.GetWidth() / 1e6, 1), round(bb.GetHeight() / 1e6, 1)
    P, comps = _board_P_comps(board)
    nl = sp.View(sp.Config.load(board_dir)).nl
    model = sp.build_corridor_model(nl, {r: P[r] for r in P}, comps, board_w=W)
    boxes = _region_boxes(model, W, H)

    def cy(ref):
        try:
            return sp._courtyard_info(comps.get(ref, ""), P[ref][2])
        except Exception:                                  # noqa: BLE001
            return (0.0, 0.0, 1.0, 1.0)

    by_region = {}
    for a in assign:
        ref, reg = a.get("ref"), a.get("region")
        if ref in P and reg in boxes:
            by_region.setdefault(reg, []).append(ref)
    moves, used = [], {}
    for reg, refs in by_region.items():
        moves.extend(_tile_into_box(refs, cy, boxes[reg], gap=0.6))
        used[reg] = refs
    del board
    if not moves:
        return {"error": "no valid region assignments", "regions": sorted(boxes)}
    ap = w_apply(board_pcb, moves, out_rel, board_dir=board_dir)
    ap["regions_used"] = {k: len(v) for k, v in used.items()}
    return ap


def w_pack(board_pcb, out_rel, board_dir, region="right", refs=None):
    """Single-region partition MATERIALIZER: deterministic shelf-pack of a ref set into one region, then
    w_apply. The LLM owns WHICH refs (the partition); geometry is deterministic."""
    sm = _shelf_moves(board_pcb, board_dir, region=region, refs=refs)
    ap = w_apply(board_pcb, sm["moves"], out_rel, board_dir=board_dir)
    ap["packed"] = sm["packed"]; ap["region_box"] = sm["region_box"]
    return ap


def _score_routed(routed_board):
    """Score an ALREADY-routed board: kelvin/diffpair/drc/unconnected + the ACTUAL foreign F.Cu clips into
    the high-current pours. Runs in its OWN process (see w_measure) -- loading a board after a route+pour+
    keepout pipeline in the same process corrupts pcbnew SWIG state (later LoadBoard returns a bare
    SwigPyObject), so the score MUST be a fresh interpreter."""
    import pcbnew
    import cec_score
    m = dataclasses.asdict(cec_score.score(routed_board))
    rb = pcbnew.LoadBoard(routed_board)
    Z = {}
    for z in rb.Zones():
        nn = z.GetNetname()
        if (nn.endswith("_HI") or nn.endswith("_LO")) and z.IsOnLayer(pcbnew.F_Cu):
            sp_ = z.GetFilledPolysList(pcbnew.F_Cu); bb = z.GetBoundingBox()
            Z[nn] = {"isl": sp_.OutlineCount(), "bb": [bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()],
                     "x": 0, "nets": {}}
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
                z["nets"][tn] = z["nets"].get(tn, 0) + 1     # the ACTUAL foreign net clipping this pour
    del rb
    clip_nets = sorted({(tn, base.lstrip("/")) for base, z in Z.items() for tn in z["nets"]})
    return {"kelvin_ok": bool(m.get("kelvin_ok")), "diffpair_ok": bool(m.get("diffpair_ok")),
            "gates_pass": bool(m.get("gates_pass")), "drc": m.get("drc"), "unconnected": m.get("unconnected"),
            "clips": sum(z["x"] for z in Z.values()), "fragmented_pours": sum(1 for z in Z.values() if z["isl"] > 1),
            "clip_nets": [{"net": n, "pour": p} for n, p in clip_nets]}


def w_measure(board_pcb, passes, opt_time, keepout=False):
    """Route the placement, then SCORE IN A SEPARATE SUBPROCESS: kelvin/drc/unconnected + the ACTUAL foreign
    F.Cu clips into the high-current pours. keepout=True routes WITH the corridor keepout (forces foreign
    signals AROUND the corridors via the clear top/bottom channels). The route and score MUST be different
    processes -- a route+pour(+keepout) pipeline leaves pcbnew SWIG state such that a same-process LoadBoard
    for scoring returns a bare SwigPyObject (the documented footgun); the fresh interpreter is the fix and
    is what lets the keepout path score at all."""
    import pcbnew
    import cec_fr
    b = pcbnew.LoadBoard(board_pcb)
    pours = cec_fr.derive_power_pours(board_pcb, board=b)
    _names = {n.GetNetname() for n in b.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    _kp = [(h, h[:-3] + "_LO") for h in sorted(_names) if h.endswith("_HI") and (h[:-3] + "_LO") in _names]
    del b
    hints = cec_fr.corridor_keepouts(board_pcb, kelvin_pairs=_kp, nets_12v=[]) if keepout else []
    routed = os.path.join(tempfile.mkdtemp(), "routed.kicad_pcb")
    c = cec_fr.route_once(board_pcb, routed, hints=hints, power_pours=pours, passes=passes, opt_time=opt_time)
    if not (c.ok and c.board):
        return {"error": f"route failed: {getattr(c, 'err', None)}"}
    # score in a FRESH interpreter (SWIG state hygiene)
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--score-board", c.board],
                       capture_output=True, text=True, timeout=300)
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("RESULT_JSON="):
            return json.loads(ln[len("RESULT_JSON="):])
    return {"error": f"score subprocess failed rc={r.returncode}: {((r.stdout or '') + (r.stderr or ''))[-400:]}"}


# ====================================================================== HOST: the LLM planner seat
MOVE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["moves"],                                  # diagnosis + rationale OPTIONAL -> shorter output,
    "properties": {                                         # avoids the cluster pass truncating mid-JSON
        "diagnosis": {"type": "string", "description": "the global placement problem you see"},
        "moves": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["ref", "x", "y"],
            "properties": {
                "ref": {"type": "string"},
                "x": {"type": "number", "description": "new centre x in mm"},
                "y": {"type": "number", "description": "new centre y in mm"},
                "rot": {"type": "number", "description": "rotation in degrees (optional)"},
                "rationale": {"type": "string"},
            }}},
    },
}

PARTITION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["assignments"],                            # region-NAME assignment, not coords -> robust,
    "properties": {                                         # un-truncatable, and the materializer packs cleanly
        "diagnosis": {"type": "string", "description": "the partition you chose and why"},
        "assignments": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["ref", "region"],
            "properties": {
                "ref": {"type": "string"},
                "region": {"type": "string", "description": "exactly one of the named PLACEMENT REGIONS"},
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


def _trim_context(context):
    """Trim the analyzed context for the planner: keep the SIGNIFICANT, movable parts (connectors J*,
    shunts RS*, ICs U*, diodes/inductors) -- the decoupling passives (R*/C*) follow their owner IC via
    legalize, so the LLM should not place them individually. Smaller prompt -> a faster, sharper call."""
    def sig(ref):
        return not (ref[:1] in ("R", "C") and ref[1:2].isdigit())   # drop R<n>/C<n> passives
    t = dict(context)
    t["parts"] = [p for p in context.get("parts", []) if sig(p["ref"])]
    return t


def plan_cluster(context, best_measure, model=None, timeout=420, temperature=0.2):
    """HOST: the PARTITION/CLUSTER plan -- the big structural jump. Diagnosis (2026-06-16): the clip gap is
    ~15 foreign nets straddling the corridors, ~13 of them AVOIDABLE (ESP-side power/CAN/I2C/USB/EN/detect).
    The fix is to move EVERY foreign (non-corridor) part to ONE side in a single coherent layout so only the
    ~2-3 inherent detection-chain crossings remain. The LLM does the global partition; the placer +
    legalize do the geometry. One good partition should drop clips far in one step (vs incremental crawl)."""
    import cec_judge_local as jl
    corridors = context.get("corridors", [])
    right_x = max((c["band"][2] for c in corridors), default=context["outline"]["W"] * 0.55) + 2.0
    W = context["outline"]["W"]; H = context["outline"]["H"]
    corridor_refs = set()
    for c in corridors:
        corridor_refs |= {c.get("shunt")} | set(c.get("sense_ics", []))
    corridor_refs |= {p["ref"] for p in context.get("parts", []) if p["ref"].startswith("J")}
    foreign = [p["ref"] for p in context.get("parts", [])
               if p["ref"] not in corridor_refs and p["ref"][:1] in ("U", "D", "L", "Q", "Y", "X")]
    user = (
        "BOARD CONTEXT:\n" + json.dumps(_trim_context(context), indent=1)[:7000] + "\n\n"
        + ("BEST ROUTE: kelvin_ok=%s clips=%s\n\n" % (best_measure.get("kelvin_ok"),
           best_measure.get("clips")) if best_measure else "")
        + "FULL RE-CLUSTER (the structural fix). The clip gap is ~15 FOREIGN nets crossing the corridors; "
        "~13 are AVOIDABLE (all ESP-side: +3V3/+5VSB/VBUS/CAN/I2C/USB/EN/DETECT). Move EVERY foreign IC to "
        "the RIGHT region x in [%.0f, %.0f] (y in [2, %.0f]), packed as a tight cluster on the ESP side of "
        "BOTH corridors, so those nets live entirely to the right and only the ~2-3 inherent detection "
        "crossings remain. Foreign ICs to place on the right: %s. Keep the corridor parts "
        "(J_IN*/J_OUT*/RS*/the sense INAs in each corridor) fixed. Give a move (x,y) for EACH foreign IC "
        "above, spread so they don't stack. OMIT rationales -- give ref,x,y only. Return moves."
        % (right_x, W - 2, H - 2, foreign[:24])
    )
    sysmsg = _PLANNER_SYSTEM + "\nThis is the CLUSTER pass: produce a COMPLETE coherent layout of the "\
        "foreign logic on one side, not a few tweaks. Output ref,x,y per move; no rationale text."
    return jl._chat_json(sysmsg, user, MOVE_SCHEMA, name="placecluster",
                         model=model or "cec-worker", timeout=timeout, max_tokens=2600,
                         temperature=temperature, nothink=True)


def plan_moves(context, best_measure, model=None, timeout=360, feedback=None, temperature=0.0):
    """HOST: ask the planner seat for placement moves to improve on the BEST board so far.
    *best_measure* is the best board's route (kelvin/clips/clip_nets -- the ACTUAL offenders). *feedback*
    (optional) is the last REGRESSED attempt {moves, from_clips, to_clips} so the planner tries a DIFFERENT
    approach instead of repeating a move-set that made it worse (with temperature>0 for diversity)."""
    import cec_judge_local as jl
    clip_line = ""
    if best_measure and best_measure.get("clip_nets"):
        clip_line = ("ACTUAL POUR CLIPS on the current best board (routed-truth -- the REAL offenders, not "
                     "the airwire proxy): " + json.dumps(best_measure["clip_nets"][:24]) + "\n"
                     "Each is a FOREIGN net whose routed F.Cu trace cuts a high-current pour. PRIMARY GOAL: "
                     "drive these to 0. For each, place its endpoints so the net routes ENTIRELY on ONE side "
                     "of that pour -- the detection chain shunt->amp(INA181)->comparator->ESP must stay LOCAL "
                     "to its OWN cable's side until past the LAST corridor. Kelvin is already met; do NOT "
                     "drag a sense IC away from its shunt to chase a clip.\n")
    fb_line = ""
    if feedback:
        # feedback["moves"] is a list of REF STRINGS (the driver records moved_refs uniformly for both the
        # partition and refine tiers) -- use them directly; do NOT treat them as move dicts.
        fb_line = ("YOUR LAST ATTEMPT REGRESSED: moving %s took clips %s->%s. Try a DIFFERENT approach -- "
                   "move different parts / a different side; do not repeat those moves.\n"
                   % ((feedback.get("moves") or [])[:8],
                      feedback.get("from_clips"), feedback.get("to_clips")))
    user = (
        "BOARD CONTEXT (best placement so far; decoupling R*/C* passives omitted -- they follow their IC):\n"
        + json.dumps(_trim_context(context), indent=1)[:7000] + "\n\n"
        + ("BEST ROUTE: kelvin_ok=%s clips=%s drc=%s\n" % (best_measure.get("kelvin_ok"),
           best_measure.get("clips"), best_measure.get("drc")) if best_measure else "")
        + clip_line + fb_line + "\n"
        + "Propose the placement MOVES that drive the ACTUAL pour clips toward 0 (keep each clipping net on "
        "one side of its corridor) while KEEPING kelvin (sense ICs stay against their shunts). Keep "
        "J_IN*/J_OUT*/RS* fixed. Be decisive; terse rationales. Return diagnosis + moves."
    )
    return jl._chat_json(_PLANNER_SYSTEM, user, MOVE_SCHEMA, name="placeplan",
                         model=model or "cec-worker", timeout=timeout, max_tokens=2000,
                         temperature=temperature, nothink=True)


_AUDITOR_SYSTEM = _PLANNER_SYSTEM + (
    "\n\nYou are the AUDITOR -- the DEEP-REVIEW tier above the fast worker, which has PLATEAUED (every "
    "recent attempt regressed or barely moved). You see the FULL attempt history. Do NOT propose a "
    "variation on what already failed. Diagnose the STRUCTURAL reason the clips are stuck, then propose a "
    "STRUCTURALLY DIFFERENT full placement (a different partition / arrangement of the significant ICs) to "
    "escape the local optimum -- a hand-tuned board reaches ~3 clips, so a much better arrangement EXISTS.")


def plan_audit(context, best_measure, history, model=None, timeout=300, temperature=0.3):
    """The AUDITOR tier: a MORE CAPABLE seat (cec-worker-quality, Qwen 27B dense + nothink) that reviews
    the WHOLE trajectory on a deep plateau and proposes a STRUCTURALLY DIFFERENT placement to escape the
    local optimum the fast worker is stuck in. Fires rarely (deep plateau), so its higher latency is fine."""
    import cec_judge_local as jl
    traj = [{"r": h["round"], "moved": h.get("moves"), "clips": (h.get("measure") or {}).get("clips"),
             "kelvin": (h.get("measure") or {}).get("kelvin_ok"), "accepted": h.get("accepted")}
            for h in history[-12:]]
    user = (
        "BEST PLACEMENT (decoupling R*/C* passives omitted -- they follow their IC):\n"
        + json.dumps(_trim_context(context), indent=1)[:6000] + "\n\n"
        + "BEST: kelvin_ok=%s clips=%s. ACTUAL clipping nets: %s\n"
        % (best_measure.get("kelvin_ok"), best_measure.get("clips"),
           json.dumps(best_measure.get("clip_nets", [])[:20])) + "\n"
        + "ATTEMPT HISTORY (the worker is PLATEAUED -- {moved}=refs it moved, clips=resulting clips):\n"
        + json.dumps(traj) + "\n\n"
        + "The clips are STUCK at %s. Diagnose the STRUCTURAL reason, then propose a STRUCTURALLY DIFFERENT "
        "full placement (move the significant ICs to a different partition/arrangement than anything above) "
        "to break the plateau toward ~3 clips. Keep J_IN*/J_OUT*/RS* fixed and sense ICs against their "
        "shunts (kelvin). Return diagnosis + moves." % best_measure.get("clips")
    )
    return jl._chat_json(_AUDITOR_SYSTEM, user, MOVE_SCHEMA, name="placeaudit",
                         model=model or "cec-worker-quality", timeout=timeout, max_tokens=2600,
                         temperature=temperature, nothink=True)


def plan_partition(context, best_measure, model=None, timeout=300, temperature=0.2, history=None, deep=False):
    """REGION-AWARE partition plan (2026-06-17 -- the fix for the auditor's execution ceiling). The LLM
    assigns each foreign IC to a NAMED REGION (left/spine/right/top/bottom from _region_boxes) -- a small,
    robust, un-scrambleable decision it reasons CORRECTLY -- and w_partition tiles each region deterministically
    (no absolute-coord legalize+route scramble that capped the hill-climb at clips=48). deep=True is the
    AUDITOR variant: a more-capable seat sees the whole plateaued trajectory and must pick a STRUCTURALLY
    different region assignment. The key structural fact handed to the model: the pours span ONLY the corridor
    band's y-range, so the TOP/BOTTOM channels reach EVERY corridor's inner-edge sense ICs without crossing."""
    import cec_judge_local as jl
    rb = context.get("region_boxes", {})
    corr_anchor = {c.get("shunt") for c in context.get("corridors", [])} | \
                  {ic for c in context.get("corridors", []) for ic in c.get("sense_ics", [])}
    foreign = [p["ref"] for p in context.get("parts", [])
               if p["ref"][:1] in ("U", "D", "L", "Q") and not p["ref"].startswith("SW")
               and p["ref"] not in corr_anchor]
    region_help = "\n".join("  %s = [x0,y0,x1,y1]=%s  (%.0f x %.0f mm)"
                            % (k, v, v[2] - v[0], v[3] - v[1]) for k, v in rb.items())
    traj_line = ""
    if deep and history:
        traj = [{"r": h["round"], "clips": (h.get("measure") or {}).get("clips"), "moved": h.get("moves")}
                for h in history[-12:]]
        traj_line = ("\nThe worker is PLATEAUED. ATTEMPT HISTORY (moved=refs, clips=result): "
                     + json.dumps(traj) + "\nChoose a region assignment STRUCTURALLY DIFFERENT from those.\n")
    clip_line = ""
    if best_measure and best_measure.get("clip_nets"):
        clip_line = "ACTUAL POUR CLIPS to eliminate: " + json.dumps(best_measure["clip_nets"][:24]) + "\n"
    user = (
        "BOARD CONTEXT (decoupling R*/C* passives omitted -- they FOLLOW their owner IC automatically):\n"
        + json.dumps(_trim_context(context), indent=1)[:6000] + "\n\n"
        + "PLACEMENT REGIONS -- assign each foreign IC to exactly ONE. A net stays CLEAN (no pour clip) when "
        "all its pads land in regions a router can connect WITHOUT crossing a corridor pour. The pours span "
        "ONLY each corridor band's y-range, so a part in TOP or BOTTOM can feed EVERY corridor's inner-edge "
        "sense IC via the clear channel above/below the pours -- that is how the shared rails reach both "
        "corridors without clipping:\n" + region_help + "\n\n"
        + ("BEST: kelvin=%s clips=%s drc=%s\n" % (best_measure.get("kelvin_ok"),
           best_measure.get("clips"), best_measure.get("drc")) if best_measure else "")
        + clip_line + traj_line + "\n"
        + "Assign EACH of these foreign ICs to a region: %s\n" % foreign[:24]
        + "Strategy: the shared rails (+3V3/+5VSB/GND) feed sense ICs in BOTH corridors -- route them via a "
        "TOP/BOTTOM channel, so put their source (LDO) and the ESP where that works. Keep each cable's "
        "detection chain (shunt->INA181->comparator->ESP) LOCAL to its cable's side until past the last "
        "corridor. Return diagnosis + assignments (ref+region only)."
    )
    sysmsg = (_AUDITOR_SYSTEM if deep else _PLANNER_SYSTEM) + (
        "\nThis is the REGION-PARTITION pass: assign each foreign IC to a NAMED region; a deterministic "
        "packer materializes each region (you do NOT give coordinates). Output ref+region per assignment.")
    return jl._chat_json(sysmsg, user, PARTITION_SCHEMA, name="placepartition",
                         model=model or ("cec-worker-quality" if deep else "cec-worker"),
                         timeout=timeout, max_tokens=2200, temperature=temperature, nothink=True)


# ====================================================================== HOST: the iterate driver
def run(board_dir, rounds, *, model=None, auditor=None, seeds=(0, 1, 2, 3), out_dir=None, passes=16,
        opt_time=32, from_board=None, deadline=None, keepout=False):
    import time
    import cec_synth_pipeline as sp                          # noqa: F401  (ensure path)
    out_dir = out_dir or os.path.join("build", "place-planner")
    os.makedirs(os.path.join(ROOT, out_dir), exist_ok=True)
    board_name = os.path.basename(board_dir.rstrip("/"))
    strategies = ["dataflow", "thermal_separated", "compact"]

    def log(m):
        print(f"[planner] {m}", flush=True)

    # 0. start board: a deterministic seed, OR continue the hill-climb from a given board (--from-board,
    #    e.g. a prior run's best) so progress compounds across runs instead of re-seeding from scratch.
    if from_board:
        seed_out = from_board
        log(f"continue from: {seed_out}")
    else:
        seed_out = f"{out_dir}/{board_name}-r0.kicad_pcb"
        s = _exec_worker(["--seed", "--board", _rel(board_dir), "--out", seed_out,
                          "--seeds", ",".join(map(str, seeds)), "--strategies", ",".join(strategies)])
        if s.get("error"):
            log(f"seed failed: {s['error']}"); return {"error": s["error"]}
        log(f"seed: {seed_out} corridor_cross={s.get('corridor_cross')} ({s['W']}x{s['H']}mm)")
    def score(meas):
        # FAB-READINESS objective: (1) kelvin is HARD (never accept a board that loses it); (2) minimize
        # the SUM clips+drc -- a SMOOTH scalarization that values BOTH pour-integrity (clips) and
        # manufacturability (drc) and gives a real gradient toward both-low. It naturally dominates the
        # clips=48/drc=28 trap (sum 76) with a balanced clips=47/drc=19 (66) and rewards driving either
        # down; (3) raw clips as the tiebreak (pour integrity is the headline we're chasing). A hard DRC
        # ceiling was tried first and rejected -- it threw away a clips=47 win for a near-miss drc=19 and
        # gave no gradient among over-ceiling boards. Lower = better.
        if not meas.get("kelvin_ok"):
            return (1, 1e9, 1e9)
        clips = meas.get("clips", 9999) or 9999
        drc = meas.get("drc", 9999) or 9999
        return (0, clips + drc, clips)

    ko_flag = ["--keepout"] if keepout else []               # route every measure WITH the corridor keepout
    if keepout:
        log("corridor keepout ENABLED (foreign nets forced around the corridors via top/bottom channels)")
    # measure the SEED -> the first best
    seed_meas = _exec_worker(["--measure", "--board-pcb", seed_out, "--passes", str(passes),
                              "--opt-time", str(opt_time)] + ko_flag)
    best = {"board": seed_out, "measure": seed_meas, "score": score(seed_meas)}
    log(f"r0 (seed): kelvin={seed_meas.get('kelvin_ok')} clips={seed_meas.get('clips')} "
        f"drc={seed_meas.get('drc')}")
    history = [{"round": 0, "board": seed_out, "measure": seed_meas, "accepted": True}]
    feedback = None                                          # last regressed attempt -> diversify the next plan

    for rnd in range(1, rounds):
        if deadline and time.time() >= deadline:
            log(f"r{rnd}: wall-clock deadline reached -> stop"); break
        # HILL-CLIMB: always plan FROM the best board, accept the candidate only if it improves.
        ctx = _exec_worker(["--analyze", "--board-pcb", best["board"], "--board", _rel(board_dir)])
        if ctx.get("error"):
            log(f"r{rnd} analyze failed: {ctx['error']}"); break
        # TIERED ESCALATION by plateau depth. The STRUCTURAL tiers (round-1 + mid-plateau re-partition, and
        # the deep-plateau AUDITOR) now emit a REGION PARTITION (named-region assignment) materialized cleanly
        # by w_partition -- NOT absolute coords, which legalize+route scrambled (the 2026-06-17 finding: the
        # auditor reasons the partition right but can't execute coords). The refine tier keeps absolute moves
        # for small nudges. A seat parse failure / empty plan RETRIES the next round (never ends the run).
        streak = feedback.get("streak", 0) if feedback else 0
        mode = "apply"
        try:
            if streak >= 6:
                plan = plan_partition(ctx, best["measure"], model=auditor, history=history, deep=True)
                kind = "PARTITION-AUDIT"; mode = "partition"
            elif rnd == 1 or 3 <= streak < 6:
                plan = plan_partition(ctx, best["measure"], model=model)
                kind = "partition"; mode = "partition"
            else:
                temp = min(0.9, 0.4 + 0.2 * streak)
                plan = plan_moves(ctx, best["measure"], model=model, feedback=feedback, temperature=temp)
                kind = f"refine t={temp}"
        except Exception as e:                              # noqa: BLE001 -- a seat parse/transport failure
            log(f"r{rnd}: planner seat failed ({type(e).__name__}: {str(e)[:80]}) -> retry next round")
            feedback = {"moves": [], "from_clips": best["measure"].get("clips"),
                        "to_clips": best["measure"].get("clips"), "streak": (feedback.get("streak", 0) + 1) if feedback else 1}
            continue
        cand = f"{out_dir}/{board_name}-r{rnd}.kicad_pcb"
        if mode == "partition":
            items = (plan or {}).get("assignments") or []
            moved_refs = sorted({a.get("ref") for a in items if a.get("ref")})
            log(f"r{rnd}: {kind}(from best clips={best['measure'].get('clips')}) "
                f"'{(plan or {}).get('diagnosis','')[:70]}' -> {len(items)} assign")
            if not items:
                feedback = {"moves": [], "from_clips": best["measure"].get("clips"),
                            "to_clips": best["measure"].get("clips"), "streak": streak + 1}
                continue
            ap = _exec_worker(["--partition", "--board-pcb", best["board"], "--out", cand,
                               "--assign", json.dumps(items), "--board", _rel(board_dir)])
        else:
            moves = (plan or {}).get("moves") or []
            moved_refs = [m.get("ref") for m in moves]
            log(f"r{rnd}: {kind}(from best clips={best['measure'].get('clips')}) "
                f"'{(plan or {}).get('diagnosis','')[:70]}' -> {len(moves)} move(s)")
            if not moves:
                feedback = {"moves": [], "from_clips": best["measure"].get("clips"),
                            "to_clips": best["measure"].get("clips"), "streak": streak + 1}
                continue
            ap = _exec_worker(["--apply", "--board-pcb", best["board"], "--out", cand, "--moves", json.dumps(moves),
                               "--board", _rel(board_dir)])
        if ap.get("error"):
            log(f"r{rnd} apply failed: {ap['error']} -> retry next round")
            feedback = {"moves": [], "from_clips": best["measure"].get("clips"),
                        "to_clips": best["measure"].get("clips"), "streak": streak + 1}
            continue
        cmeas = _exec_worker(["--measure", "--board-pcb", cand, "--passes", str(passes), "--opt-time", str(opt_time)] + ko_flag)
        csc = score(cmeas)
        improved = csc < best["score"]
        log(f"r{rnd}: candidate kelvin={cmeas.get('kelvin_ok')} clips={cmeas.get('clips')} "
            f"drc={cmeas.get('drc')} -> {'ACCEPT (new best)' if improved else 'reject (keep best)'}")
        history.append({"round": rnd, "board": cand, "measure": cmeas, "moves": moved_refs,
                        "kind": kind, "accepted": improved})
        if improved:
            best = {"board": cand, "measure": cmeas, "score": csc}
            feedback = None
        else:
            streak = (feedback.get("streak", 1) + 1) if feedback else 1
            feedback = {"moves": moved_refs, "from_clips": best["measure"].get("clips"),
                        "to_clips": cmeas.get("clips"), "streak": streak}
        # CONVERGED = fab-ready: kelvin + pour-integrity (clips<=6) + DRC near the finishing floor (<=8).
        bm = best["measure"]
        if bm.get("kelvin_ok") and (bm.get("clips") or 99) <= 6 and (bm.get("drc") or 99) <= 8:
            log(f"r{rnd}: kelvin + clips<=6 + drc<=8 -> CONVERGED (fab-ready)"); break
    log(f"DONE: best kelvin={best['measure'].get('kelvin_ok')} clips={best['measure'].get('clips')} "
        f"drc={best['measure'].get('drc')} -> {best['board']}")
    json.dump({"best": best, "history": history},
              open(os.path.join(ROOT, out_dir, f"{board_name}-result.json"), "w"), indent=1, default=str)
    return {"best": best, "history": history}


def main(argv=None):
    ap = argparse.ArgumentParser(description="LLM-guided placement loop")
    ap.add_argument("--run", action="store_true", help="HOST driver")
    ap.add_argument("--seed", action="store_true"); ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--measure", action="store_true")
    ap.add_argument("--score-board", default=None, help="score an already-routed board (fresh-process score)")
    ap.add_argument("--pack", action="store_true", help="deterministic shelf-pack a partition into a region")
    ap.add_argument("--partition", action="store_true", help="region-aware partition: --assign [{ref,region}]")
    ap.add_argument("--assign", default=None, help="JSON [{ref,region}] region assignments for --partition")
    ap.add_argument("--region", default="right", help="pack region: right|left|spine|top|bottom|x0,y0,x1,y1")
    ap.add_argument("--refs", default=None, help="explicit partition refs (comma list); default=all foreign ICs")
    ap.add_argument("--board"); ap.add_argument("--board-pcb"); ap.add_argument("--out")
    ap.add_argument("--moves"); ap.add_argument("--seeds", default="0,1,2,3"); ap.add_argument("--strategies",
                    default="dataflow,thermal_separated,compact")
    ap.add_argument("--rounds", type=int, default=6); ap.add_argument("--model", default=None,
                    help="worker seat (per-round refine/cluster); default cec-worker (Qwen3.6 + nothink)")
    ap.add_argument("--auditor", default=None,
                    help="auditor seat (deep-plateau structural review); default cec-worker-quality")
    ap.add_argument("--passes", type=int, default=16); ap.add_argument("--opt-time", type=int, default=32)
    ap.add_argument("--keepout", action="store_true", help="measure WITH the corridor keepout (force around)")
    ap.add_argument("--from-board", default=None, help="continue the hill-climb from this board (vs re-seed)")
    ap.add_argument("--hours", type=float, default=None, help="wall-clock deadline in hours (stop after)")
    ap.add_argument("--out-dir", default=None, help="output dir for candidates (default build/place-planner)")
    a = ap.parse_args(argv)
    if a.score_board:
        _emit(_score_routed(a.score_board if os.path.isabs(a.score_board) else os.path.join(ROOT, a.score_board)))
    elif a.run:
        import time
        deadline = (time.time() + a.hours * 3600) if a.hours else None
        run(a.board, a.rounds, model=a.model, auditor=a.auditor, passes=a.passes, opt_time=a.opt_time,
            from_board=a.from_board, out_dir=a.out_dir, deadline=deadline, keepout=a.keepout)
    elif a.seed:
        _emit(w_seed(os.path.join(ROOT, a.board), a.out, [int(s) for s in a.seeds.split(",")], a.strategies.split(",")))
    elif a.analyze:
        _emit(w_analyze(os.path.join(ROOT, a.board_pcb) if not os.path.isabs(a.board_pcb) else a.board_pcb,
                        os.path.join(ROOT, a.board)))
    elif a.apply:
        _emit(w_apply(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                      json.loads(a.moves), a.out,
                      board_dir=os.path.join(ROOT, a.board) if a.board else None))
    elif a.pack:
        _emit(w_pack(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                     a.out, os.path.join(ROOT, a.board), region=a.region,
                     refs=[r.strip() for r in a.refs.split(",")] if a.refs else None))
    elif a.partition:
        _emit(w_partition(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                          json.loads(a.assign), a.out, os.path.join(ROOT, a.board)))
    elif a.measure:
        _emit(w_measure(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                        a.passes, a.opt_time, keepout=a.keepout))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
