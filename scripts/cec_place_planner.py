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
#   python3 scripts/cec_place_planner.py --run --board beta/eps-8pin-rev3 --rounds 6

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
    # forward the measure-shaping CEC_* flags into the container exec (host env -> -e), so a run launched
    # with e.g. CEC_ROUTE_UNDER=1 actually reaches w_measure inside the container.
    env_flags = []
    for _k in ("CEC_ROUTE_UNDER", "CEC_NO_EDGE_KEEPOUT", "CEC_FR_PLANE_POLICY"):
        if _k in os.environ:
            env_flags += ["-e", f"{_k}={os.environ[_k]}"]
    cmd = COMPOSE + ["exec", "-T"] + env_flags + ["routing", "python3",
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
            "region_boxes": _region_boxes(model, W, H, ox=bb.GetLeft() / 1e6, oy=bb.GetTop() / 1e6),
            "corridor_cross": len(crossings)}


def w_apply(board_pcb, moves, out_rel, board_dir=None, orient=False, faces=None):
    """Apply LLM moves (ref -> x,y[,rot]) then legalize against the true courtyards; write out_rel.
    Reuses cec_synth_pipeline.legalize_pack so an overlapping proposal is resolved, never shipped raw.
    CLUSTER-CARRYING: when an IC moves, its OWNED decoupling passives move by the SAME delta -- otherwise
    a passive carrying a crossing net (+3V3/+5VSB/I2C pull-up) is stranded behind and the net still clips
    (the measured reason a foreign-IC-only cluster only reached 62 clips). Owner map from derive_passive_spec
    (netlist) when board_dir is given, else a passives-stay fallback.
    JOINT position+ORIENTATION (orient=True, the co-opt): after positioning each moved IC, rotate it for
    pin-facing AT ITS NEW POSITION (sense->shunt for kelvin; spanning pads -> the channel via _best_pin_rot,
    using a per-ref *faces* directive from the seat when given) BEFORE the legalize -- so the legalize
    reserves the ROTATED extent (position+rotation co-designed in one pass, not sequentially patched)."""
    import pcbnew
    import cec_synth_pipeline as sp
    board = pcbnew.LoadBoard(board_pcb)
    bb = board.GetBoardEdgesBoundingBox()
    W, H = bb.GetWidth() / 1e6, bb.GetHeight() / 1e6
    P, comps = _board_P_comps(board)
    nl = None
    owner = {}                                              # passive ref -> owner IC (for cluster-carrying)
    if board_dir:
        try:
            nl = sp.View(sp.Config.load(board_dir)).nl
            ics = [r for r in P if r[:1] == "U" and not r.startswith("SW")]
            pas = [r for r in P if r[:1] in ("R", "C") and r[1:2].isdigit()]
            # FUNCTIONAL ownership: connectors (J*) + shunts (RS*) are valid cluster anchors too, so
            # the I/O passives (CC pull-downs, DETECT ESD) carry with their connector, not a far IC.
            anchor_refs = {r for r in P if r[:1] == "J" or r.startswith("RS")}
            _spec, _ = sp.derive_passive_spec(nl, pas, ics, anchor_refs=anchor_refs)
            owner = {pref: own for pref, (own, _pad) in _spec.items()}
        except Exception:                                  # noqa: BLE001 -- ownership is best-effort
            owner = {}
    by_owner = {}
    for pref, own in owner.items():
        by_owner.setdefault(own, []).append(pref)
    # HARD ANCHORS -- never let a move (esp. a refine-tier absolute move, which can name ANY ref) relocate a
    # FIXED part: the connectors (J* -- RJ-45/USB/cable IN/OUT belong at the board edge) and each cable's
    # shunt (RS*) + sense ICs (INA*, which MUST sit at their shunt for a short Kelvin tap -- kelvin_ok only
    # checks the sense net ROUTES, not its length, so without this the loop relocates them and games clips).
    protected = {r for r in P if r.startswith("J")}
    try:
        nl2 = nl if nl is not None else (sp.View(sp.Config.load(board_dir)).nl if board_dir else None)
        if nl2 is not None:
            model = sp.build_corridor_model(nl2, {r: P[r] for r in P}, comps, board_w=W)
            for cab in model.cables:
                protected.add(cab.shunt)
                protected |= set(cab.sense_ics)
    except Exception:                                      # noqa: BLE001 -- fall back to J*-only protection
        pass
    applied = []
    for mv in moves:
        ref = mv.get("ref")
        if ref not in P or ref in protected:               # drop moves that target a fixed anchor
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
    # JOINT ORIENTATION: rotate each moved IC for pin-facing at its NEW position, BEFORE legalize so the
    # rotated extent is what gets spaced. Done on the loaded board (set the new position first, then score).
    if orient and nl is not None:
        faces = faces or {}
        model = sp.build_corridor_model(nl, {r: P[r] for r in P}, comps, board_w=W)
        shunt_of = _sense_shunt_map(model, P)
        for ref in [r for r in dict.fromkeys(applied) if r[:1] == "U" and not r.startswith("SW")]:
            fp = board.FindFootprintByReference(ref)
            if fp is None:
                continue
            fp.SetPosition(pcbnew.VECTOR2I(int(P[ref][0] * 1e6), int(P[ref][1] * 1e6)))   # new pos first
            br = _best_pin_rot(fp, shunt_of.get(ref), H, face=faces.get(ref, "auto"))
            P[ref] = (P[ref][0], P[ref][1], br)
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
    outp = os.path.join(ROOT, out_rel)
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
    pcbnew.SaveBoard(outp, board)
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


def _region_boxes(model, W, H, *, ox=0.0, oy=0.0, margin=1.0):
    """Named PLACEMENT REGIONS for the LLM partition -- the spatial channels foreign logic can occupy
    WITHOUT its nets being forced to straddle a high-current corridor pour. Derived from the formed
    corridors (band = x0,y0,x1,y1; the pour spans only the band's y-range, so above/below it is clear):
      left/right  = left of the leftmost / right of the rightmost corridor (full board height)
      spine{k}    = the vertical gap BETWEEN corridor k and k+1 (reaches the inner-edge sense ICs of both
                    neighbours without crossing either pour) -- may be narrow
      top/bottom  = the horizontal channel ABOVE / BELOW all the pours (full board width) -- the clear
                    route-around path a power rail uses to feed every corridor's sense ICs
    A region narrower/shorter than a tiny floor is omitted (no false handle for the LLM)."""
    # ox/oy = the board's top-left origin (default 0 for back-compat with origin-0 boards like eps). The
    # corridor BANDS are already board-absolute; only the board-EDGE references must be offset by ox/oy, or a
    # board placed away from (0,0) (e.g. the 24-pin rev2 at (95,62)) tiles parts OFF the board -> unroutable.
    x0e, y0e, x1e, y1e = ox + margin, oy + margin, ox + W - margin, oy + H - margin   # inset board edges
    bands = sorted((c.band for c in model.cables if c.formed), key=lambda b: b[0])  # band=(x0,x1,y0,y1)
    if not bands:
        return {"right": [round(ox + W * 0.5, 1), round(y0e, 1), round(x1e, 1), round(y1e, 1)]}
    yb_top = min(b[2] for b in bands)                        # highest pour top y0 (clear above)
    yb_bot = max(b[3] for b in bands)                        # lowest  pour bottom y1 (clear below)
    boxes = {}
    if bands[0][0] - margin - x0e > 3:
        boxes["left"] = [round(x0e, 1), round(y0e, 1), round(bands[0][0] - margin, 1), round(y1e, 1)]
    multi = len(bands) > 2
    for i in range(len(bands) - 1):
        gx0, gx1 = bands[i][1] + margin, bands[i + 1][0] - margin   # corridor i right edge .. corridor i+1 left edge
        if gx1 - gx0 > 3:
            boxes[f"spine{i + 1}" if multi else "spine"] = [round(gx0, 1), round(y0e, 1), round(gx1, 1), round(y1e, 1)]
    boxes["right"] = [round(bands[-1][1] + margin, 1), round(y0e, 1), round(x1e, 1), round(y1e, 1)]
    if yb_top - margin - y0e > 3:
        boxes["top"] = [round(x0e, 1), round(y0e, 1), round(x1e, 1), round(yb_top - margin, 1)]
    if y1e - (yb_bot + margin) > 3:
        boxes["bottom"] = [round(x0e, 1), round(yb_bot + margin, 1), round(x1e, 1), round(y1e, 1)]
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
    boxes = _region_boxes(model, W, H, ox=bb.GetLeft() / 1e6, oy=bb.GetTop() / 1e6)
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


def w_partition(board_pcb, assign, out_rel, board_dir, orient=False):
    """REGION-AWARE partition materializer (2026-06-17). *assign* = [{ref, region, face?}] from the LLM:
    each foreign IC assigned to a named _region_boxes region (position) and optionally a *face* directive
    (up/down/left/right/auto) saying which way its spanning pads should point (orientation). Tile each
    region's refs into its box, then w_apply with the per-ref faces -> JOINT position+orientation co-design
    (orient=True). Unknown regions / unassigned foreign ICs are left where they are."""
    import pcbnew
    import cec_synth_pipeline as sp
    board = pcbnew.LoadBoard(board_pcb)
    bb = board.GetBoardEdgesBoundingBox()
    W, H = round(bb.GetWidth() / 1e6, 1), round(bb.GetHeight() / 1e6, 1)
    P, comps = _board_P_comps(board)
    nl = sp.View(sp.Config.load(board_dir)).nl
    model = sp.build_corridor_model(nl, {r: P[r] for r in P}, comps, board_w=W)
    boxes = _region_boxes(model, W, H, ox=bb.GetLeft() / 1e6, oy=bb.GetTop() / 1e6)

    def cy(ref):
        try:
            return sp._courtyard_info(comps.get(ref, ""), P[ref][2])
        except Exception:                                  # noqa: BLE001
            return (0.0, 0.0, 1.0, 1.0)

    by_region, faces = {}, {}
    for a in assign:
        ref, reg = a.get("ref"), a.get("region")
        if ref in P and reg in boxes:
            by_region.setdefault(reg, []).append(ref)
            f = a.get("face")
            if f in ("up", "down", "left", "right", "auto"):
                faces[ref] = f
    moves, used = [], {}
    for reg, refs in by_region.items():
        moves.extend(_tile_into_box(refs, cy, boxes[reg], gap=0.6))
        used[reg] = refs
    del board
    if not moves:
        return {"error": "no valid region assignments", "regions": sorted(boxes)}
    ap = w_apply(board_pcb, moves, out_rel, board_dir=board_dir, orient=orient, faces=faces)
    ap["regions_used"] = {k: len(v) for k, v in used.items()}
    return ap


def w_pack(board_pcb, out_rel, board_dir, region="right", refs=None):
    """Single-region partition MATERIALIZER: deterministic shelf-pack of a ref set into one region, then
    w_apply. The LLM owns WHICH refs (the partition); geometry is deterministic."""
    sm = _shelf_moves(board_pcb, board_dir, region=region, refs=refs)
    ap = w_apply(board_pcb, sm["moves"], out_rel, board_dir=board_dir)
    ap["packed"] = sm["packed"]; ap["region_box"] = sm["region_box"]
    return ap


def _is_sense_net(nn):
    return bool(nn) and (nn.endswith("_HI") or nn.endswith("_LO"))


def _best_pin_rot(fp, shunt_xy, H, *, face="auto", w_kelvin=12.0, w_power=1.0):
    """Pick + apply the best rotation in {0,90,180,270} for *fp* AT ITS CURRENT POSITION. Sense pads
    (_HI/_LO) are pulled toward *shunt_xy* (kelvin, heavy weight). The SPANNING pads (not GND, not sense)
    are pushed by *face*: 'up'/'down'/'left'/'right' point their centroid to that side of the IC (so the
    router runs them out that edge's channel -- the seat's joint position+orientation handle); 'auto'
    points them to the nearer top/bottom edge (the deterministic default). Mutates fp to the winner;
    returns the rotation. This is the shared core of w_orient (whole board) and w_apply's joint placement."""
    import pcbnew  # noqa: F401  (fp is a pcbnew object; ensure module present)
    pads = list(fp.Pads())
    c = fp.GetPosition(); cx, cyc = c.x / 1e6, c.y / 1e6
    best_rot, best_sc = fp.GetOrientationDegrees(), 1e18
    for rot in (0.0, 90.0, 180.0, 270.0):
        fp.SetOrientationDegrees(rot)
        sc = 0.0
        sx = sy = 0.0
        n = 0
        for p in pads:
            nn = p.GetNetname()
            if not nn:
                continue
            pos = p.GetPosition(); px, py = pos.x / 1e6, pos.y / 1e6
            if shunt_xy and _is_sense_net(nn):
                sc += w_kelvin * (((px - shunt_xy[0]) ** 2 + (py - shunt_xy[1]) ** 2) ** 0.5)
            elif not nn.endswith("GND") and not _is_sense_net(nn):
                sx += px; sy += py; n += 1
        if n:
            spx, spy = sx / n, sy / n                       # spanning-pad centroid at this rotation
            if face == "up":
                sc += w_power * (spy - cyc) * 4              # want centroid ABOVE the IC centre (small y)
            elif face == "down":
                sc += w_power * (cyc - spy) * 4
            elif face == "left":
                sc += w_power * (spx - cx) * 4
            elif face == "right":
                sc += w_power * (cx - spx) * 4
            else:                                           # auto: toward the nearer top/bottom channel
                sc += w_power * min(max(spy, 0.0), max(H - spy, 0.0))
        if sc < best_sc - 1e-9:
            best_sc, best_rot = sc, rot
    fp.SetOrientationDegrees(best_rot)
    return best_rot


def _sense_shunt_map(model, P):
    """{sense_ic_ref -> its cable's shunt (x,y)} for the kelvin pull in _best_pin_rot."""
    out = {}
    for cab in model.cables:
        if cab.shunt in P:
            sxy = (P[cab.shunt][0], P[cab.shunt][1])
            for ic in cab.sense_ics:
                out[ic] = sxy
    return out


def w_orient(board_pcb, out_rel, board_dir, *, w_kelvin=12.0, w_power=1.0):
    """PIN-LEVEL placement (the clips=24 last-mile fix, 2026-06-17). The region partition gets the right
    SIDE but not the right ORIENTATION: a net clips when its source pad faces INTO a corridor so the
    router's short path goes THROUGH the pour. The hand board reaches ~3 clips by ROTATING each IC so its
    spanning-net pads face the clear top/bottom CHANNEL (router then runs them along the channel, around the
    pour) and each sense IC's _HI/_LO pads face its SHUNT (kelvin). This pass picks, per significant IC, the
    best rotation (see _best_pin_rot). Position is UNCHANGED (so kelvin seating and the partition are
    preserved); only orientation turns. The measure validates (rejects if kelvin breaks)."""
    import pcbnew
    import cec_synth_pipeline as sp
    board = pcbnew.LoadBoard(board_pcb)
    bb = board.GetBoardEdgesBoundingBox()
    H = bb.GetHeight() / 1e6
    W = bb.GetWidth() / 1e6
    P, comps = _board_P_comps(board)
    nl = sp.View(sp.Config.load(board_dir)).nl
    model = sp.build_corridor_model(nl, {r: P[r] for r in P}, comps, board_w=W)
    shunt_of = _sense_shunt_map(model, P)                   # sense IC -> its cable's shunt (kelvin target)
    # ICs to orient: every U* (sense ICs + ESP/CAN/LDO/comparators); shunts are R* so already excluded
    ics = [r for r in P if r[:1] == "U" and not r.startswith("SW")]
    oriented = []
    for ic in ics:
        fp = board.FindFootprintByReference(ic)
        if fp is None:
            continue
        cur = fp.GetOrientationDegrees()
        best_rot = _best_pin_rot(fp, shunt_of.get(ic), H, face="auto", w_kelvin=w_kelvin, w_power=w_power)
        if abs(best_rot - cur) > 0.1:
            oriented.append({"ref": ic, "rot": best_rot, "was": round(cur, 1)})
    # De-overlap ONLY the rotated NON-SENSE ICs (a 90/270 turn can make their courtyard overlap a
    # neighbour -> DRC). Sense ICs are EXCLUDED: nudging them off their shunt is what made the earlier
    # blanket legalize backfire (kelvin routing degraded -> drc 16->18). Sense ICs are small + ~square so
    # rotation barely changes their extent; leave them pinned to the shunt.
    movers = [o["ref"] for o in oriented if o["ref"] not in shunt_of]
    if movers:
        Pn = {fp.GetReference(): (fp.GetPosition().x / 1e6, fp.GetPosition().y / 1e6, fp.GetOrientationDegrees())
              for fp in board.GetFootprints()}
        cyinfo = {}
        for r in Pn:
            try:
                cyinfo[r] = sp._courtyard_info(comps.get(r, ""), Pn[r][2])
            except Exception:                              # noqa: BLE001
                cyinfo[r] = (0.0, 0.0, 1.0, 1.0)
        sp.legalize_pack(Pn, movers, cyinfo, W, H, clr=0.4)
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            if ref in movers:
                x, y, _r = Pn[ref]
                fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
    outp = os.path.join(ROOT, out_rel)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    pcbnew.SaveBoard(outp, board)
    del board
    return {"out": out_rel, "oriented": oriented}


def w_kelvin_seat(board_pcb, out_rel, board_dir, *, offset=4.0, step=3.5):
    """Seat each sense IC TIGHT against its shunt's INNER (board-centre) edge so the Kelvin tap is SHORT.
    The deterministic placer leaves some INAs far from their shunt (measured: one 46mm away), and kelvin_ok
    only checks the sense net ROUTES, not its length -- so a long, useless tap silently passes and the loop
    gamed it. This snaps every sense IC to its shunt + orients its sense pads toward it; the loop then PROTECTS
    them there (anchor enforcement in w_apply). Applied to the seed before the loop starts."""
    import pcbnew
    import cec_synth_pipeline as sp
    board = pcbnew.LoadBoard(board_pcb)
    bb = board.GetBoardEdgesBoundingBox()
    W, H = bb.GetWidth() / 1e6, bb.GetHeight() / 1e6
    P, comps = _board_P_comps(board)
    nl = sp.View(sp.Config.load(board_dir)).nl
    model = sp.build_corridor_model(nl, {r: P[r] for r in P}, comps, board_w=W)
    shunt_of = _sense_shunt_map(model, P)
    cx = W / 2.0
    seated = []
    for cab in model.cables:
        if cab.shunt not in P:
            continue
        sx, sy = P[cab.shunt][0], P[cab.shunt][1]
        sign = 1.0 if sx < cx else -1.0                     # inner edge = toward the board centre
        for i, ic in enumerate(sorted(cab.sense_ics)):
            fp = board.FindFootprintByReference(ic)
            if fp is None or ic not in P:
                continue
            nx = max(1.0, min(W - 1.0, sx + sign * (offset + step * i)))
            ny = max(1.0, min(H - 1.0, sy + (-3.0 if i == 0 else 3.0)))   # stagger the (usually 2) ICs in y
            fp.SetPosition(pcbnew.VECTOR2I(int(nx * 1e6), int(ny * 1e6)))
            _best_pin_rot(fp, shunt_of.get(ic), H)          # sense pads -> the shunt
            P[ic] = (nx, ny, fp.GetOrientationDegrees())
            seated.append({"ref": ic, "shunt": cab.shunt, "x": round(nx, 1), "y": round(ny, 1)})
    movers = [s["ref"] for s in seated]
    if movers:                                              # de-overlap the seated ICs (vs shunt + each other)
        cyinfo = {}
        for r in P:
            try:
                cyinfo[r] = sp._courtyard_info(comps.get(r, ""), P[r][2])
            except Exception:                              # noqa: BLE001
                cyinfo[r] = (0.0, 0.0, 1.0, 1.0)
        sp.legalize_pack(P, movers, cyinfo, W, H, clr=0.3)
        for fp in board.GetFootprints():
            if fp.GetReference() in movers:
                x, y, _r = P[fp.GetReference()]
                fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6)))
    outp = os.path.join(ROOT, out_rel)
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
    pcbnew.SaveBoard(outp, board)
    del board
    return {"out": out_rel, "seated": seated}


def finish_gnd_plane(board, *, berth_mm=0.6, edge_margin_mm=0.3, refill=True):
    """Finish the GND plane(s) correctly (owner-caught, 2026-06-19):
      (1) EXTEND each GND zone to the board edge (inset edge_margin_mm) -- so a GROWN board's plane fills the
          new outline instead of staying the old size and leaving a bare strip at the grown edge (the grow
          lever moved footprints + Edge.Cuts but left the inner planes behind).
      (2) BERTH: give the high-current 12V pins a wider clearance (berth_mm) so the GND plane keeps a spacer
          around them instead of pouring up to the default ~0.3mm gap. Only THT pins actually penetrate the
          inner GND plane, so the berth bites on the connector/shunt 12V pins (SMD INA pads are surface-only).
      (3) SOLID-connect the 12V-return GND connector pins (ZONE_CONNECTION_FULL, no thermal relief) for the
          lowest-impedance, best-cooled return path (the owner's earlier 'solid fills not thermal reliefs').
    Assumes a full-board GND plane (true for the cable interposers -- antenna keepout dropped). Mutates the
    board in place; returns (n_zones_extended, n_berth_pins, n_solid_gnd_pins)."""
    import pcbnew
    bb = board.GetBoardEdgesBoundingBox(); m = int(edge_margin_mm * 1e6)
    rect = [(bb.GetLeft() + m, bb.GetTop() + m), (bb.GetRight() - m, bb.GetTop() + m),
            (bb.GetRight() - m, bb.GetBottom() - m), (bb.GetLeft() + m, bb.GetBottom() - m)]
    berth = int(berth_mm * 1e6)
    nz = 0
    for z in board.Zones():
        if z.GetNetname() == "GND":
            ol = z.Outline()
            try:
                ol.RemoveAllContours()
            except Exception:                                  # noqa: BLE001 -- older SHAPE_POLY_SET API
                while ol.OutlineCount() > 0:
                    ol.DeletePolygon(0)
            ol.NewOutline()
            for (x, y) in rect:
                ol.Append(int(x), int(y))
            if berth_mm > 0:
                # the BERTH: the GND POUR keeps this gap from every other-net pad/trace, incl. the 12V pins.
                # Applied as the ZONE clearance (the fill respects it) -- NOT pad-local-clearance, which
                # Freerouting IGNORES while routing and then DRC flags every nearby 0.25mm trace (the bug that
                # spiked drc_placement 0->50 on a clean board and confounded the whole shrink sweep).
                z.SetLocalClearance(berth)
            nz += 1
    nb = ns = 0
    for fp in board.GetFootprints():
        conn = fp.GetReference().startswith("J_")
        for p in fp.Pads():
            nn = p.GetNetname()
            is12v = ("SENSEC" in nn) or nn in ("+12V", "12V") or nn.endswith("_HI") or nn.endswith("_LO")
            if is12v:
                nb += 1                                        # counted for the report; the berth is the zone clr
            elif conn and nn.endswith("GND"):
                p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL); ns += 1
    if refill:
        for z in board.Zones():
            z.UnFill()
        try:
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        except Exception:                                      # noqa: BLE001 -- geometry is already set; fill is a bonus
            pass
    return nz, nb, ns


def _smart_repack(newP, anchors, movers, nl, comps, nW, nH):
    """Connectivity-aware re-pack of the foreign MOVERS into (nW,nH) with the ANCHORS fixed and rotations
    PRESERVED (the orient pass set them for pin-facing). Seeds at the movers' CURRENT positions (gentler than a
    grid seed -> stays near the already-routable structure), barycentric-relaxes each toward its net neighbours
    (short nets), then legalizes against the true courtyards. Mutates newP in place. Beats the greedy
    nearest-free-slot pack for routability: short nets -> Freerouting leaves far fewer clearance violations on
    the tighter board, which is what lets the shrink keep going instead of stalling at drc_p~50."""
    import cec_synth_pipeline as sp
    nbrs = sp._adjacency(nl)
    P = {r: tuple(newP[r]) for r in newP}                       # anchors + movers at their current (shrunk) pos
    for _ in range(50):
        for r in movers:
            ns = [P[n] for n in sorted(nbrs.get(r, ())) if n in P]   # neighbours incl. the FIXED anchors
            if not ns:
                continue
            tx = sum(p[0] for p in ns) / len(ns)
            ty = sum(p[1] for p in ns) / len(ns)
            P[r] = (0.6 * tx + 0.4 * P[r][0], 0.6 * ty + 0.4 * P[r][1], P[r][2])   # pull to neighbours, keep rot
    cyinfo = {}
    for r in P:
        try:
            cyinfo[r] = sp._courtyard_info(comps[r], P[r][2]) if r in comps else (0.0, 0.0, 1.0, 1.0)
        except Exception:                                       # noqa: BLE001
            cyinfo[r] = (0.0, 0.0, 1.0, 1.0)
    sp.legalize_pack(P, movers, cyinfo, nW, nH, clr=0.35)
    for r in movers:
        if r in P:
            newP[r] = list(P[r])


def _scale_at_split(board_pcb, out_rel, board_dir, *, delta, direction, repack=None):
    """Core of the GROW (delta>0) / SHRINK (delta<0) levers. Pick a SPLIT line and RIGIDLY translate everything
    beyond it -- AND the far board edge -- by delta. The near half stays fixed; the far half slides, so the
    channel AT the split changes width by exactly |delta| while every other relative position (corridor pours,
    kelvin seats, the routable structure) is preserved -- a rigid translation. Sense ICs follow THEIR SHUNT's
    side of the split so a sense IC never detaches from its shunt (kelvin invariant). finish_gnd_plane re-fits
    the GND plane(s) to the new edge. GROW never overlaps; SHRINK can, so we return the courtyard-overlap count
    (>0 = the shrink crushed parts together) for the caller to gate on.
      direction W: split at the widest inter-corridor SPINE -> the gap the signals route THROUGH to reach the
                 inner-edge sense ICs (corridor-left fixed, right slides).
      direction H: split just below the pours -> the bottom channel + its logic."""
    import pcbnew
    import cec_synth_pipeline as sp
    import cec_pcb
    board = pcbnew.LoadBoard(board_pcb)
    bb = board.GetBoardEdgesBoundingBox()
    W, H = bb.GetWidth() / 1e6, bb.GetHeight() / 1e6
    P, comps = _board_P_comps(board)
    nl = sp.View(sp.Config.load(board_dir)).nl
    model = sp.build_corridor_model(nl, {r: P[r] for r in P}, comps, board_w=W)
    shunt_of = _sense_shunt_map(model, P)                       # sense IC -> its cable's shunt (x,y)
    bands = sorted((c.band for c in model.cables if c.formed), key=lambda b: b[0])   # (x0,x1,y0,y1)
    axis = 0 if str(direction).upper() == "W" else 1
    if axis == 0:                                              # W: split at the WIDEST inter-corridor spine
        if len(bands) >= 2:
            gaps = [((bands[i][1] + bands[i + 1][0]) / 2.0, bands[i + 1][0] - bands[i][1])
                    for i in range(len(bands) - 1)]
            split = max(gaps, key=lambda g: g[1])[0]
        else:
            split = W * 0.5
    else:                                                     # H: split just below the pours
        split = (max(b[3] for b in bands) + 1.5) if bands else H * 0.5

    def shift_of(ref):
        c = (shunt_of[ref][axis] if ref in shunt_of else P[ref][axis])   # sense IC follows its shunt's side
        return delta if c > split else 0.0

    shifted = []
    newP = {r: list(v) for r, v in P.items()}                 # track shifted positions for the overlap check
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        sh = shift_of(ref)
        if sh:
            pos = fp.GetPosition()
            fp.SetPosition(pcbnew.VECTOR2I(int(pos.x + sh * 1e6), pos.y) if axis == 0
                           else pcbnew.VECTOR2I(pos.x, int(pos.y + sh * 1e6)))
            shifted.append(ref)
            if ref in newP:
                newP[ref][axis] += sh
    for d in board.GetDrawings():                             # move the far board edge by delta
        if board.GetLayerName(d.GetLayer()) != "Edge.Cuts":
            continue
        for getter, setter in (("GetStart", "SetStart"), ("GetEnd", "SetEnd")):
            try:
                pt = getattr(d, getter)()
            except Exception:                                 # noqa: BLE001 -- non-segment Edge.Cuts shape
                continue
            if (pt.x if axis == 0 else pt.y) / 1e6 > split:
                getattr(d, setter)(pcbnew.VECTOR2I(int(pt.x + delta * 1e6), pt.y) if axis == 0
                                   else pcbnew.VECTOR2I(pt.x, int(pt.y + delta * 1e6)))
    nW, nH = (W + delta, H) if axis == 0 else (W, H + delta)

    def _count_over():
        try:
            return len(cec_pcb._overlaps({r: tuple(v) for r, v in newP.items()}, comps, set(newP)))
        except Exception:                                     # noqa: BLE001
            return -1

    n_over = _count_over()                                    # courtyard-overlap count = the SHRINK feasibility wall
    relegalized = False
    # anchors = anything that must NOT be re-packed off its spot: EVERY connector (J* -- cable J_IN/J_OUT, the
    # 12VHPWR J3/J4, the Hub's edge connectors J2..J_USB; they mate externally / carry the corridors), the shunts
    # (RS*), and the sense ICs (kelvin). Connectors MAY overhang the edge (the cable plugs in from outside) --
    # everything else (the MOVERS: logic, passives, the copper logo) must stay ON the board. Generalised from the
    # eps/PCIe-only "J_" so the lever runs on the 12VHPWR + the Hub too.
    anchors = {r for r in newP if r and r[0] == "J" or r.startswith("RS") or r in shunt_of}
    movers = [r for r in newP if r not in anchors and r in comps]
    if delta < 0 and repack and n_over and n_over > 0:
        # a rigid shrink crushed parts together. RE-PACK only the foreign movers (anchors stay so the corridors +
        # kelvin survive) so the logic flows into the smaller outline. The board is re-routed afterwards, so a
        # re-pack is fine.  smart = connectivity-aware (short nets); greedy = nearest-free-slot nudge (default).
        try:
            if repack == "smart":
                _smart_repack(newP, anchors, movers, nl, comps, nW, nH)
            else:
                cyinfo = {r: (sp._courtyard_info(comps.get(r, ""), newP[r][2] if len(newP[r]) > 2 else 0.0)
                              if r in comps else (0.0, 0.0, 1.0, 1.0)) for r in newP}
                sp.legalize_pack(newP, movers, cyinfo, nW, nH, clr=0.4)
            for fp in board.GetFootprints():
                r = fp.GetReference()
                if r in movers and r in newP:
                    fp.SetPosition(pcbnew.VECTOR2I(int(newP[r][0] * 1e6), int(newP[r][1] * 1e6)))
            n_over = _count_over(); relegalized = True
        except Exception:                                     # noqa: BLE001 -- re-pack is best-effort; keep the rigid result
            pass
    # ON-BOARD check (shrink only): a MOVER whose courtyard pokes past the board edge means the shrink went too
    # far -- the floor-hunt MUST stop here, else logic + the logo clip off the edge (the owner-caught PCIe-2
    # failure). Connectors (anchors) are excluded -- they're allowed to overhang. Uses the same courtyard the
    # overlap check uses, with a footprint-bbox fallback for parts without a courtyard (e.g. the copper logo).
    n_off = 0
    if delta < 0:
        ebb = board.GetBoardEdgesBoundingBox()
        EL, ER, ET, EB = ebb.GetLeft() / 1e6, ebb.GetRight() / 1e6, ebb.GetTop() / 1e6, ebb.GetBottom() / 1e6
        fp_by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
        for r in movers:
            try:
                x0, x1, y0, y1 = cec_pcb.courtyard_bbox(comps[r], *newP[r])
            except Exception:                                 # noqa: BLE001 -- no courtyard (logo) -> use the fp bbox
                fp = fp_by_ref.get(r)
                if fp is None:
                    continue
                bx = fp.GetBoundingBox()
                x0, x1, y0, y1 = bx.GetLeft() / 1e6, bx.GetRight() / 1e6, bx.GetTop() / 1e6, bx.GetBottom() / 1e6
            if x0 < EL - 0.4 or x1 > ER + 0.4 or y0 < ET - 0.4 or y1 > EB + 0.4:
                n_off += 1
    fz = finish_gnd_plane(board)                              # re-fit the GND plane(s) to the new edge (+ 12V berth +
    #                                                          solid GND returns) -- on a shrink it tightens, on a grow
    #                                                          it extends; either way the inner planes track the edge.
    outp = os.path.join(ROOT, out_rel) if not os.path.isabs(out_rel) else out_rel
    os.makedirs(os.path.dirname(outp) or ".", exist_ok=True)
    pcbnew.SaveBoard(outp, board)
    del board
    return {"out": os.path.relpath(outp, ROOT), "delta": delta, "direction": str(direction).upper(),
            "split": round(split, 1), "new_W": round(nW, 1), "new_H": round(nH, 1), "shifted": sorted(shifted),
            "overlap": n_over, "offboard": n_off, "relegalized": relegalized,
            "gnd_plane": {"zones_extended": fz[0], "berth_pins": fz[1], "solid_gnd_pins": fz[2]}}


def w_grow(board_pcb, out_rel, board_dir, *, delta=5.0, direction="W"):
    """THE LAST LEVER of the loop: scale the board UP ~delta mm so the (now-fast) hill-climb can re-converge with
    more channel room. A rigid translation -> NO new courtyard overlap, so no legalize (which would scramble the
    routable placement, the 2026-06-17 finding). Thin wrapper over _scale_at_split with a positive delta."""
    return _scale_at_split(board_pcb, out_rel, board_dir, delta=abs(delta), direction=direction)


def w_shrink(board_pcb, out_rel, board_dir, *, delta=5.0, direction="W", repack=None):
    """REVERSE-GROW: scale the board DOWN ~delta mm (narrow the widest channel / bottom gap) to find how small the
    board can get. Unlike grow, a shrink CAN collide -> the returned 'overlap' (courtyard-pair count) is the
    feasibility signal: 0 = the shrink fit, >0 = it crushed parts together so the caller reverts. With
    repack='smart' (or 'greedy'), overlaps from the rigid shrink are resolved by RE-PLACING the foreign parts
    (anchors stay -> kelvin survives) so the sweep can push PAST the rigid wall: 'smart' is connectivity-aware
    (short nets -> still routes at the tighter size -> HUNTS the true floor), 'greedy' is a fast nearest-free-slot
    nudge. shrink_sweep() walks this down. Thin wrapper over _scale_at_split with a negative delta."""
    return _scale_at_split(board_pcb, out_rel, board_dir, delta=-abs(delta), direction=direction, repack=repack)


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
    # LEVER A (2026-06-17): split the DRC. copper_edge_clearance is a FREEROUTING ARTIFACT -- it has no
    # board-edge-clearance awareness and routes tracks against Edge.Cuts (it dominated 100% of the count and
    # made the loop reject real clip wins). It's a ROUTE-time concern (fixed by the lever-B edge keepout),
    # NOT placement quality, so report drc_placement = drc - copper_edge_clearance for the loop to optimise,
    # while keeping the raw drc + the edge count visible.
    drc_raw = m.get("drc") or 0
    drc_edge = (m.get("drc_types") or {}).get("copper_edge_clearance", 0)
    return {"kelvin_ok": bool(m.get("kelvin_ok")), "diffpair_ok": bool(m.get("diffpair_ok")),
            "gates_pass": bool(m.get("gates_pass")), "drc": drc_raw, "drc_edge": drc_edge,
            "drc_placement": max(0, drc_raw - drc_edge), "unconnected": m.get("unconnected"),
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
    hints = list(cec_fr.corridor_keepouts(board_pcb, kelvin_pairs=_kp, nets_12v=[])) if keepout else []
    # LEVER B (default ON): board-edge keepout so Freerouting keeps tracks off Edge.Cuts (no edge-clearance
    # awareness otherwise -> the copper_edge_clearance artifact). CEC_NO_EDGE_KEEPOUT=1 disables for A/B.
    if os.environ.get("CEC_NO_EDGE_KEEPOUT", "0") != "1":
        hints += cec_fr.edge_keepout(board_pcb)
    routed = os.path.join(tempfile.mkdtemp(), "routed.kicad_pcb")
    c = cec_fr.route_once(board_pcb, routed, hints=hints, power_pours=pours, passes=passes, opt_time=opt_time)
    if not (c.ok and c.board):
        return {"error": f"route failed: {getattr(c, 'err', None)}"}
    score_target = c.board
    # ROUTE-UNDER finishing pass (CEC_ROUTE_UNDER=1): the deterministic, completeness-preserving layer-swap
    # (scripts/cec_layer_swap.py) moves the foreign F.Cu segments that clip a SENSEC pour DOWN to B.Cu under
    # the F.Cu-only pour (board-legal vias, collision-guarded, reverts unsafe). It runs in its OWN process
    # (SWIG hygiene), and the loop then scores the UNDER board -> the placement is optimised for how much
    # route-under it ENABLES (less B.Cu congestion under the pours = more swaps = fewer clips). A swap failure
    # or empty result falls back to the plain routed board, so it can only help, never break the measure.
    if os.environ.get("CEC_ROUTE_UNDER", "0") == "1":
        under = os.path.join(os.path.dirname(c.board), "routed-under.kicad_pcb")
        su = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "cec_layer_swap.py"),
                             c.board, under, "0.2", "0.25"],
                            env={**os.environ, "GROW_MM": "0"}, capture_output=True, text=True, timeout=300)
        if su.returncode == 0 and os.path.exists(under):
            score_target = under
    # score in a FRESH interpreter (SWIG state hygiene)
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--score-board", score_target],
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
                "face": {"type": "string", "enum": ["up", "down", "left", "right", "auto"],
                         "description": "which way this IC's spanning pads (+3V3/+5VSB/signals) should point "
                                        "so the router runs them out that edge's channel; 'up'/'down' = the "
                                        "top/bottom channel, 'auto' = nearest. Omit = auto."},
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
        "ALL connectors (every J* -- the RJ-45/USB/cable IN+OUT belong at the BOARD EDGE), the shunts (RS*) "
        "and the sense INAs (they MUST stay seated at their shunt) FIXED -- NEVER move those. Move only the "
        "foreign logic (ESP/CAN/LDO/comparators + their passives). Be decisive; terse rationales. Return diagnosis + moves."
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
        traj_line = ("\nThe worker is PLATEAUED and EVERY recent attempt REGRESSED -- do NOT repeat any of "
                     "their groupings. ATTEMPT HISTORY (moved=refs, clips=result): " + json.dumps(traj)
                     + "\nPick a region assignment STRUCTURALLY DIFFERENT from all of the above: put the ESP "
                     "(U1) and the power source (LDO) in a region NONE of these used, and try splitting the "
                     "per-cable detection comparators to OPPOSITE channels (one top, one bottom).\n")
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
        "corridor.\n"
        + "ALSO set each IC's FACE (joint orientation): which way its spanning pads (+3V3/+5VSB/signals) "
        "should point so the router runs them out that edge's CHANNEL instead of through a pour -- 'up' for "
        "the top channel, 'down' for the bottom, 'auto' for nearest. An IC near the top edge whose rails "
        "should leave upward = face 'up'. This is the lever that turns a clip into a clean channel route. "
        "Return diagnosis + assignments (ref + region + face)."
    )
    sysmsg = (_AUDITOR_SYSTEM if deep else _PLANNER_SYSTEM) + (
        "\nThis is the REGION-PARTITION pass: assign each foreign IC to a NAMED region; a deterministic "
        "packer materializes each region (you do NOT give coordinates). Output ref+region per assignment.")
    # the DEEP (auditor) tier runs HOT (0.75) for diversity -- on a plateau it kept emitting an identical
    # partition at low temp; high temp + the anti-repeat history is what breaks the repetition loop.
    eff_temp = 0.75 if deep else temperature
    return jl._chat_json(sysmsg, user, PARTITION_SCHEMA, name="placepartition",
                         model=model or ("cec-worker-quality" if deep else "cec-worker"),
                         timeout=timeout, max_tokens=(3000 if deep else 2200), temperature=eff_temp, nothink=True)


# ====================================================================== HOST: the iterate driver
def run(board_dir, rounds, *, model=None, auditor=None, seeds=(0, 1, 2, 3), out_dir=None, passes=16,
        opt_time=32, from_board=None, deadline=None, keepout=False, orient=False,
        max_grows=3, grow_delta=5.0):
    import time
    import cec_synth_pipeline as sp                          # noqa: F401  (ensure path)
    out_dir = out_dir or os.path.join("build", "place-planner")
    out_abs = os.path.join(ROOT, out_dir)
    os.makedirs(out_abs, exist_ok=True)
    board_name = os.path.basename(board_dir.rstrip("/"))
    strategies = ["dataflow", "thermal_separated", "compact"]
    # self-describe the run IN its out-dir so the live dashboard auto-tracks it (run.log = step feed,
    # measurement.jsonl = convergence series; the boards already land here). Dashboard discovers the
    # running --out-dir and reads these -- no manual --run-dir.
    _runlog = open(os.path.join(out_abs, "run.log"), "a", buffering=1)
    _meas = open(os.path.join(out_abs, "measurement.jsonl"), "a", buffering=1)

    def log(m):
        line = f"[planner] {m}"
        print(line, flush=True)
        try:
            _runlog.write(line + "\n")
        except Exception:                                       # noqa: BLE001 -- logging must never crash the run
            pass

    def measure_row(rnd, meas, verdict):
        # one convergence row per round, mapped to the dashboard's column names (penalty_total=clips is the
        # headline pour-integrity metric; drc=drc_placement excludes the edge artifact; live_objective=score)
        try:
            dp = meas.get("drc_placement"); dp = meas.get("drc") if dp is None else dp
            _meas.write(json.dumps({"round": rnd, "verdict": verdict,
                "kelvin_ok": meas.get("kelvin_ok"), "drc": dp, "drc_raw": meas.get("drc"),
                "unconnected": meas.get("unconnected"), "penalty_total": meas.get("clips"),
                "live_objective": (meas.get("clips") or 0) + (dp or 0) + 5 * (meas.get("unconnected") or 0)}) + "\n")
        except Exception:                                       # noqa: BLE001
            pass

    def orient_board(b):
        # PIN-LEVEL pass: rotate each IC in place so spanning-net pads face the top/bottom channel and sense
        # pads face the shunt (kelvin). Applied to the seed + every candidate so the loop optimises in the
        # oriented space; the measure validates (a kelvin-break or drc-spike candidate is rejected).
        if not orient:
            return b
        o = _exec_worker(["--orient", "--board-pcb", b, "--out", b, "--board", _rel(board_dir)])
        if o.get("error"):
            log(f"  orient warn: {o['error'][:80]}")
        elif o.get("oriented"):
            log(f"  oriented {len(o['oriented'])} IC(s): {[x['ref'] for x in o['oriented']]}")
        return b

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
        # FAB-READINESS objective, lexicographic, gives a gradient in BOTH regimes (esp. needed with the
        # corridor keepout, which can strand routing -> kelvin=False / high unconnected):
        #   kelvin=False : (1, unconnected, clips+drc)   -- among BROKEN boards prefer FEWER unrouted nets,
        #                  a gradient that climbs back toward a fully-routable (kelvin-true) placement.
        #   kelvin=True  : (0, clips+drc_p+5*unconnected, clips) -- minimize the SUM (pour integrity AND the
        #                  PLACEMENT-relevant DRC; heavy unconnected penalty so a not-fully-routed board never
        #                  beats a routed one), clips as the tiebreak (the headline metric).
        # LEVER A: drc_p = drc_placement (drc MINUS copper_edge_clearance) -- the raw drc is ~100% a
        # Freerouting edge-routing artifact (no board-edge awareness), so optimising it made the loop reject
        # real clip wins; the edge clearance is a route-time concern (lever B). Lower = better.
        # NB: `x or 9999` is WRONG here -- 0 is a LEGITIMATE (ideal) value for drc_p/unconn/clips, and `0 or
        # 9999` == 9999 clobbers it. Lever A made drc_placement=0 the common good case, which exposed this:
        # use an explicit None check so a clean board scores low instead of catastrophically high.
        def _v(x):
            return 9999 if x is None else x
        clips = _v(meas.get("clips"))
        dp = meas.get("drc_placement")
        drc_p = _v(meas.get("drc") if dp is None else dp)
        un = _v(meas.get("unconnected"))
        if not meas.get("kelvin_ok"):
            return (1, un, clips + drc_p)
        return (0, clips + drc_p + 5 * un, clips)

    ko_flag = ["--keepout"] if keepout else []               # route every measure WITH the corridor keepout
    orient_flag = ["--with-orient"] if orient else []        # JOINT position+orientation in every materialize
    if keepout:
        log("corridor keepout ENABLED (foreign nets forced around the corridors via top/bottom channels)")
    if orient:
        log("JOINT pin-level ORIENT ENABLED (materialize co-designs position+rotation; seat sets per-IC face)")
    # KELVIN-SEAT the sense ICs onto their shunts FIRST (the placer leaves some far -> long taps that game
    # kelvin_ok), THEN the loop protects them there. Always-on correctness step (no-op without cables).
    ks = _exec_worker(["--kelvin-seat", "--board-pcb", seed_out, "--out", seed_out, "--board", _rel(board_dir)])
    if ks.get("seated"):
        log(f"kelvin-seated {len(ks['seated'])} sense IC(s) to their shunts: "
            f"{[(s['ref'], s['shunt']) for s in ks['seated']]}")
    elif ks.get("error"):
        log(f"kelvin-seat warn: {ks['error'][:80]}")
    # INITIAL CLUSTER (fresh seed only): a raw deterministic seed scatters the foreign logic (corridor_cross
    # ~15) so it won't route fully (kelvin=False/unconn~12) and the loop crawls. Pack the foreign ICs to one
    # side as the start -> measured unconn 12->1, drc_p 20->1 (routable) -> the loop refines from there. A
    # --from-board start is already placed, so skip it.
    if not from_board:
        pk = _exec_worker(["--pack", "--region", "right", "--board-pcb", seed_out, "--out", seed_out,
                           "--board", _rel(board_dir)])
        if pk.get("packed"):
            log(f"initial cluster: packed {len(pk['packed'])} foreign IC(s) to the right region")
        elif pk.get("error"):
            log(f"initial pack warn: {pk['error'][:80]}")
    # NB: do NOT blanket-orient the seed -- an un-validated whole-board rotate disrupts the routable
    # seat+pack start (measured: unconn 1->11). The per-round materialize orients MOVED ICs and the measure
    # validates each (a routability-hurting rotation is rejected), so orientation enters the loop safely there.
    # measure the SEED -> the first best
    seed_meas = _exec_worker(["--measure", "--board-pcb", seed_out, "--passes", str(passes),
                              "--opt-time", str(opt_time)] + ko_flag)
    best = {"board": seed_out, "measure": seed_meas, "score": score(seed_meas)}
    # best_overall = best ACROSS ALL board sizes (the grow lever resets `best` to a fresh larger board so the
    # hill-climb re-anchors there even if it momentarily scores worse; best_overall keeps the global winner so a
    # grow that doesn't pan out never costs us the pre-grow result). grows = grow-lever firings so far.
    best_overall = dict(best)
    grows = 0
    log(f"r0 (seed): kelvin={seed_meas.get('kelvin_ok')} clips={seed_meas.get('clips')} "
        f"drc_p={seed_meas.get('drc_placement')}(raw={seed_meas.get('drc')},edge={seed_meas.get('drc_edge')}) "
        f"unconn={seed_meas.get('unconnected')}")
    measure_row(0, seed_meas, "seed")
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
        # THE LAST LEVER (deepest tier): a plateau so deep even the auditor (streak>=6) can't break it -> the
        # placement is wedged at THIS board size. Scale the board up by grow_delta and re-anchor the hill-climb
        # on the larger board (alternating W=widen-spine / H=taller-channels), letting the now-fast loop
        # re-converge with more channel room. best_overall preserves the pre-grow result, so a grow is pure
        # upside. Fires at most max_grows times (compounding +grow_delta each), then the loop rides on the auditor.
        if max_grows and grows < max_grows and streak >= 8:
            gdir = ("W", "H")[grows % 2]
            gcand = f"{out_dir}/{board_name}-grow{grows + 1}.kicad_pcb"
            gr = _exec_worker(["--grow", "--board-pcb", best["board"], "--out", gcand, "--board", _rel(board_dir),
                               "--grow-delta", str(grow_delta), "--grow-dir", gdir])
            if gr.get("error"):
                log(f"r{rnd}: grow #{grows + 1} failed: {gr['error'][:80]} -> fall through to plan")
            else:
                gm = _exec_worker(["--measure", "--board-pcb", gcand, "--passes", str(passes),
                                   "--opt-time", str(opt_time)] + ko_flag)
                gsc = score(gm)
                grows += 1
                log(f"r{rnd}: GROW #{grows} {gdir}+{grow_delta}mm -> {gr.get('new_W')}x{gr.get('new_H')}mm "
                    f"(split={gr.get('split')}, shifted {len(gr.get('shifted', []))} parts) -> "
                    f"kelvin={gm.get('kelvin_ok')} clips={gm.get('clips')} "
                    f"drc_p={gm.get('drc_placement')} unconn={gm.get('unconnected')}")
                measure_row(rnd, gm, f"grow-{gdir}")
                better = gsc < best_overall["score"]
                history.append({"round": rnd, "board": gcand, "measure": gm, "kind": f"grow-{gdir}",
                                "accepted": better})
                best = {"board": gcand, "measure": gm, "score": gsc}     # re-anchor on the larger board
                if better:
                    best_overall = dict(best)
                    log(f"r{rnd}:   grow improved the GLOBAL best (clips {gm.get('clips')})")
                feedback = None                                          # reset plateau; let the larger board work
                continue
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
                               "--assign", json.dumps(items), "--board", _rel(board_dir)] + orient_flag)
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
                               "--board", _rel(board_dir)] + orient_flag)
        if ap.get("error"):
            log(f"r{rnd} apply failed: {ap['error']} -> retry next round")
            feedback = {"moves": [], "from_clips": best["measure"].get("clips"),
                        "to_clips": best["measure"].get("clips"), "streak": streak + 1}
            continue
        cmeas = _exec_worker(["--measure", "--board-pcb", cand, "--passes", str(passes), "--opt-time", str(opt_time)] + ko_flag)
        csc = score(cmeas)
        improved = csc < best["score"]
        log(f"r{rnd}: candidate kelvin={cmeas.get('kelvin_ok')} clips={cmeas.get('clips')} "
            f"drc_p={cmeas.get('drc_placement')}(raw={cmeas.get('drc')},edge={cmeas.get('drc_edge')}) "
            f"unconn={cmeas.get('unconnected')} "
            f"-> {'ACCEPT (new best)' if improved else 'reject (keep best)'}")
        history.append({"round": rnd, "board": cand, "measure": cmeas, "moves": moved_refs,
                        "kind": kind, "accepted": improved})
        measure_row(rnd, cmeas, "accept" if improved else "reject")
        if improved:
            best = {"board": cand, "measure": cmeas, "score": csc}
            if csc < best_overall["score"]:                  # the global winner across all board sizes
                best_overall = dict(best)
            feedback = None
        else:
            streak = (feedback.get("streak", 1) + 1) if feedback else 1
            feedback = {"moves": moved_refs, "from_clips": best["measure"].get("clips"),
                        "to_clips": cmeas.get("clips"), "streak": streak}
        # CONVERGED = fab-ready: kelvin + fully routed (unconn<=2) + pour-integrity (clips<=6) + PLACEMENT
        # DRC near the finishing floor (<=8). Edge-clearance is excluded (route-time, lever B). NB: explicit
        # None checks, not `x or 99` -- 0 is the IDEAL value (a converged board is clips=0/unconn=0/drc_p=0)
        # and `0 or 99`==99 would make a PERFECT board never register as converged.
        bm = best_overall["measure"]                         # converge on the GLOBAL best (any board size)
        _bdp = bm.get("drc_placement"); _bdp = bm.get("drc") if _bdp is None else _bdp
        if (bm.get("kelvin_ok") and (bm.get("unconnected") if bm.get("unconnected") is not None else 99) <= 2
                and (bm.get("clips") if bm.get("clips") is not None else 99) <= 6
                and (_bdp if _bdp is not None else 99) <= 8):
            log(f"r{rnd}: kelvin + unconn<=2 + clips<=6 + drc_placement<=8 -> CONVERGED (fab-ready)"); break
    log(f"DONE: best kelvin={best_overall['measure'].get('kelvin_ok')} clips={best_overall['measure'].get('clips')} "
        f"drc={best_overall['measure'].get('drc')} ({grows} grow(s)) -> {best_overall['board']}")
    json.dump({"best": best_overall, "history": history},
              open(os.path.join(ROOT, out_dir, f"{board_name}-result.json"), "w"), indent=1, default=str)
    return {"best": best_overall, "history": history}


# ====================================================================== HOST: the SHRINK sweep (reverse-grow)
def shrink_sweep(board_dir, start_board, *, out_dir=None, passes=16, opt_time=32,
                 start_delta=5.0, min_delta=1.0, clip_tol=25, drc_tol=4, max_steps=40, deadline=None, repack="greedy"):
    """REVERSE-GROW SWEEP -- 'how small can the board get?'. From a converged, ROUTABLE board, rigidly SHRINK the
    slack (narrow the widest channel / bottom gap), route+score each step, and keep shrinking until it 'starts
    causing issues': a courtyard overlap (parts collide), kelvin breaks, a net goes unrouted, or DRC/clips degrade
    past tol. Greedy: shrink each direction at the current step size while it stays valid, then drop to a finer
    step (5->3->2->1mm) to squeeze the last mm; stop when even min_delta makes no progress. Records the
    size-vs-quality CURVE and the smallest still-valid board. Writes run.log + measurement.jsonl into out_dir so
    the live dashboard auto-tracks the shrink. Heavy steps run in the routing container via _exec_worker."""
    import time
    out_dir = out_dir or os.path.join("build", "place-planner-shrink")
    out_abs = os.path.join(ROOT, out_dir); os.makedirs(out_abs, exist_ok=True)
    out_rel = _rel(out_abs)                                      # repo-relative: the container worker resolves
    #                                                             --out/--board-pcb against ROOT (= /workspace there)
    board_name = os.path.basename(board_dir.rstrip("/"))
    start_abs = start_board if os.path.isabs(start_board) else os.path.join(ROOT, start_board)
    start_rel = _rel(start_abs)
    _runlog = open(os.path.join(out_abs, "run.log"), "a", buffering=1)
    _meas = open(os.path.join(out_abs, "measurement.jsonl"), "a", buffering=1)

    def log(m):
        line = f"[shrink] {m}"; print(line, flush=True)
        try:
            _runlog.write(line + "\n")
        except Exception:                                       # noqa: BLE001
            pass

    def meas_row(step, m, verdict):
        try:
            dp = m.get("drc_placement"); dp = m.get("drc") if dp is None else dp
            _meas.write(json.dumps({"round": step, "verdict": verdict, "kelvin_ok": m.get("kelvin_ok"),
                "drc": dp, "drc_raw": m.get("drc"), "unconnected": m.get("unconnected"),
                "penalty_total": m.get("clips"), "W": m.get("_W"), "H": m.get("_H"),
                "live_objective": (m.get("clips") or 0) + (dp or 0) + 5 * (m.get("unconnected") or 0)}) + "\n")
        except Exception:                                       # noqa: BLE001
            pass

    def measure(b):
        return _exec_worker(["--measure", "--board-pcb", b, "--passes", str(passes),
                             "--opt-time", str(opt_time), "--board", _rel(board_dir)]) or {}

    def shrink(src, out, delta, dirn):
        args = ["--shrink", "--board-pcb", src, "--out", out, "--board", _rel(board_dir),
                "--shrink-delta", str(delta), "--shrink-dir", dirn]
        if repack:
            args += ["--repack", repack]                        # re-place foreign parts past the rigid wall
        return _exec_worker(args, timeout=1800) or {}

    # ---- baseline: route the start board + probe its size (delta=0 shrink to a temp returns new_W/new_H) ----
    base = measure(start_rel)
    base_kelvin = base.get("kelvin_ok")                         # None/True for a no-kelvin board (the Hub); the
    #                                                            sweep only REQUIRES kelvin if the start board has it.
    routed = base.get("unconnected") is not None and not base.get("error")
    if not routed or base_kelvin is False:
        log(f"baseline {start_rel} NOT routable (kelvin={base_kelvin} unconn={base.get('unconnected')} "
            f"err={str(base.get('error'))[:80]}) -- shrink needs a valid routed start")
        return {"error": "baseline not routable", "baseline": base}
    probe = shrink(start_rel, os.path.join(out_rel, f"{board_name}-size-probe.kicad_pcb"), 0, "W")
    W0, H0 = probe.get("new_W"), probe.get("new_H")
    base["_W"], base["_H"] = W0, H0
    base_clips = base.get("clips") or 0; base_drc = base.get("drc_placement") or 0
    base_unconn = base.get("unconnected") or 0                  # gate relative to the start, not absolute 0 (a
    log(f"baseline: {W0}x{H0}mm (area {(W0 or 0) * (H0 or 0):.0f} mm^2)  clips={base_clips} "
        f"kelvin={base.get('kelvin_ok')} drc_p={base_drc} unconn={base.get('unconnected')}")
    meas_row(0, base, "baseline")
    curve = [{"step": 0, "dir": "-", "delta": 0, "W": W0, "H": H0, "clips": base_clips,
              "kelvin": base.get("kelvin_ok"), "drc_p": base_drc, "unconn": base.get("unconnected"), "valid": True}]

    def valid(m):                                               # "no worse than the start": kelvin holds (if the
        if base_kelvin and not m.get("kelvin_ok"):              # start had it), no NEW unrouted nets, DRC + clips
            return False                                        # within tolerance.
        return ((m.get("unconnected") or 0) <= base_unconn
                and (m.get("drc_placement") or 0) <= base_drc + drc_tol
                and (m.get("clips") or 0) <= base_clips + clip_tol)

    cur, curW, curH = start_rel, W0, H0
    deltas = [d for d in (float(start_delta), 3.0, 2.0, 1.0) if d >= min_delta] or [float(min_delta)]
    step = 0; stop = False; passno = 0
    while not stop and step < max_steps:                         # MULTI-PASS: re-sweep until a full pass finds nothing --
        passno += 1; progressed = False                         # shrinking one axis frees room on the other.
        for delta in deltas:
            if stop:
                break
            for dirn in ("W", "H"):                              # shrink each axis at this step while it stays valid
                while step < max_steps:
                    if deadline and time.time() > deadline:
                        log("deadline reached -- stopping"); stop = True; break
                    step += 1
                    cand = os.path.join(out_rel, f"{board_name}-shrink{step}.kicad_pcb")
                    sh = shrink(cur, cand, delta, dirn)
                    nW, nH, ov = sh.get("new_W"), sh.get("new_H"), sh.get("overlap")
                    off = sh.get("offboard") or 0
                    if sh.get("error"):
                        log(f"step {step} {dirn}-{delta}mm: shrink failed: {str(sh.get('error'))[:70]}"); break
                    rep = " (re-packed)" if sh.get("relegalized") else ""
                    if ov is None or ov > 0 or off > 0:           # parts collide OR a mover clips the edge -> wall here
                        why = (f"OVERLAP={ov} (parts collide)" if (ov is None or ov > 0)
                               else f"OFFBOARD={off} (logic/logo clips the edge)")
                        log(f"step {step} {dirn}-{delta}mm -> {nW}x{nH}mm  {why}{rep} -> stop {dirn}@{delta}mm")
                        curve.append({"step": step, "dir": dirn, "delta": delta, "W": nW, "H": nH, "valid": False,
                                      "repacked": bool(sh.get("relegalized")), "reason": why}); break
                    m = measure(cand); m["_W"], m["_H"] = nW, nH
                    ok = valid(m)
                    curve.append({"step": step, "dir": dirn, "delta": delta, "W": nW, "H": nH, "clips": m.get("clips"),
                                  "kelvin": m.get("kelvin_ok"), "drc_p": m.get("drc_placement"),
                                  "unconn": m.get("unconnected"), "repacked": bool(sh.get("relegalized")), "valid": ok})
                    meas_row(step, m, f"{dirn}-{delta}{'ok' if ok else 'bad'}")
                    if ok:
                        cur, curW, curH = cand, nW, nH; progressed = True
                        log(f"step {step} {dirn}-{delta}mm -> {nW}x{nH}mm (area {nW * nH:.0f}){rep}  clips={m.get('clips')} "
                            f"kelvin={m.get('kelvin_ok')} drc_p={m.get('drc_placement')} unconn={m.get('unconnected')}  ACCEPT")
                    else:                                        # routing degraded -> revert, this axis is done at this step
                        log(f"step {step} {dirn}-{delta}mm -> {nW}x{nH}mm  clips={m.get('clips')} kelvin={m.get('kelvin_ok')} "
                            f"drc_p={m.get('drc_placement')} unconn={m.get('unconnected')}  ISSUE -> revert, stop {dirn}@{delta}mm")
                        break
        if not progressed:                                       # a whole pass with no accepted shrink -> at the floor
            break
        log(f"pass {passno}: now {curW}x{curH}mm -> re-sweeping (an axis may have freed the other)")
    a0 = (W0 or 0) * (H0 or 0); a1 = (curW or 0) * (curH or 0)
    red = round(100 * (1 - a1 / a0), 1) if a0 else 0
    log(f"DONE. MIN ROUTABLE {curW}x{curH}mm (area {a1:.0f} mm^2) vs start {W0}x{H0} ({a0:.0f}) -> {red}% smaller "
        f"in {step} steps. board: {cur}")
    return {"start_board": start_rel, "start_W": W0, "start_H": H0, "area_start": round(a0),
            "min_board": cur, "min_W": curW, "min_H": curH, "area_min": round(a1),
            "area_reduction_pct": red, "steps": step, "curve": curve}


def main(argv=None):
    ap = argparse.ArgumentParser(description="LLM-guided placement loop")
    ap.add_argument("--run", action="store_true", help="HOST driver")
    ap.add_argument("--seed", action="store_true"); ap.add_argument("--analyze", action="store_true")
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--measure", action="store_true")
    ap.add_argument("--score-board", default=None, help="score an already-routed board (fresh-process score)")
    ap.add_argument("--pack", action="store_true", help="deterministic shelf-pack a partition into a region")
    ap.add_argument("--partition", action="store_true", help="region-aware partition: --assign [{ref,region}]")
    ap.add_argument("--orient", action="store_true", help="pin-level orientation pass (rotate ICs for pin-facing)")
    ap.add_argument("--kelvin-seat", action="store_true", help="snap each sense IC to its shunt (short tap)")
    ap.add_argument("--grow", action="store_true", help="scale the board up by --grow-delta in --grow-dir (W|H)")
    ap.add_argument("--grow-delta", type=float, default=5.0, help="mm to grow per step (default 5)")
    ap.add_argument("--grow-dir", default="W", help="grow direction: W (widen spine) | H (taller channels)")
    ap.add_argument("--max-grows", type=int, default=3, help="run loop: cap on board-grow lever firings")
    ap.add_argument("--shrink", action="store_true", help="worker: scale the board DOWN by --shrink-delta in --shrink-dir")
    ap.add_argument("--shrink-sweep", action="store_true", help="HOST: walk a routable board DOWN to its minimum size")
    ap.add_argument("--shrink-delta", type=float, default=5.0, help="mm per shrink step (sweep starts here, drops to 1)")
    ap.add_argument("--shrink-dir", default="W", help="shrink direction: W (narrow spine) | H (shorter channels)")
    ap.add_argument("--min-delta", type=float, default=1.0, help="sweep: smallest shrink step before stopping")
    ap.add_argument("--clip-tol", type=int, default=25, help="sweep: max clip increase over baseline still 'valid'")
    ap.add_argument("--drc-tol", type=int, default=4, help="sweep: max drc_placement increase over baseline still 'valid'")
    ap.add_argument("--max-steps", type=int, default=40, help="sweep: cap on shrink steps")
    ap.add_argument("--repack", choices=["none", "greedy", "smart"], default=None,
                    help="shrink: how to clear the overlaps a rigid shrink creates -- 'smart' (connectivity-aware "
                    "re-place, HUNTS the true floor), 'greedy' (fast nearest-free-slot nudge), or 'none'/omit "
                    "(rigid-only = the no-rework minimum). --shrink-sweep defaults to smart.")
    ap.add_argument("--with-orient", action="store_true", help="apply/partition: co-design rotation jointly")
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
    ap.add_argument("--loop-orient", action="store_true", help="apply the pin-level orient pass each round")
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
            from_board=a.from_board, out_dir=a.out_dir, deadline=deadline, keepout=a.keepout,
            orient=a.loop_orient, max_grows=a.max_grows, grow_delta=a.grow_delta)
    elif a.seed:
        _emit(w_seed(os.path.join(ROOT, a.board), a.out, [int(s) for s in a.seeds.split(",")], a.strategies.split(",")))
    elif a.analyze:
        _emit(w_analyze(os.path.join(ROOT, a.board_pcb) if not os.path.isabs(a.board_pcb) else a.board_pcb,
                        os.path.join(ROOT, a.board)))
    elif a.apply:
        _emit(w_apply(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                      json.loads(a.moves), a.out,
                      board_dir=os.path.join(ROOT, a.board) if a.board else None, orient=a.with_orient))
    elif a.pack:
        _emit(w_pack(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                     a.out, os.path.join(ROOT, a.board), region=a.region,
                     refs=[r.strip() for r in a.refs.split(",")] if a.refs else None))
    elif a.partition:
        _emit(w_partition(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                          json.loads(a.assign), a.out, os.path.join(ROOT, a.board), orient=a.with_orient))
    elif a.orient:
        _emit(w_orient(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                       a.out, os.path.join(ROOT, a.board)))
    elif a.kelvin_seat:
        _emit(w_kelvin_seat(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                            a.out, os.path.join(ROOT, a.board)))
    elif a.grow:
        _emit(w_grow(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                     a.out, os.path.join(ROOT, a.board), delta=a.grow_delta, direction=a.grow_dir))
    elif a.shrink:
        _rp = None if a.repack in (None, "none") else a.repack
        _emit(w_shrink(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                       a.out, os.path.join(ROOT, a.board), delta=a.shrink_delta, direction=a.shrink_dir,
                       repack=_rp))
    elif a.shrink_sweep:
        import time, glob as _glob
        deadline = (time.time() + a.hours * 3600) if a.hours else None
        _rp = "greedy" if a.repack is None else (None if a.repack == "none" else a.repack)
        # Resolve the START board: --board-pcb if given, else the .kicad_pcb inside the --board dir
        # (the lever used to crash with TypeError: isabs(None) when --board-pcb was omitted).
        _start = a.board_pcb
        if not _start and a.board:
            _hits = sorted(_glob.glob(os.path.join(ROOT, a.board, "*.kicad_pcb")))
            _start = _hits[0] if _hits else None
        if not _start:
            _emit({"error": "shrink-sweep needs --board-pcb, or --board pointing at a dir with a .kicad_pcb"})
            return
        _start = _start if os.path.isabs(_start) else os.path.join(ROOT, _start)
        _emit(shrink_sweep(a.board, _start,
                           out_dir=a.out_dir, passes=a.passes, opt_time=a.opt_time, start_delta=a.shrink_delta,
                           min_delta=a.min_delta, clip_tol=a.clip_tol, drc_tol=a.drc_tol, max_steps=a.max_steps,
                           deadline=deadline, repack=_rp))
    elif a.measure:
        _emit(w_measure(a.board_pcb if os.path.isabs(a.board_pcb) else os.path.join(ROOT, a.board_pcb),
                        a.passes, a.opt_time, keepout=a.keepout))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
