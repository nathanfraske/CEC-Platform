#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_place -- the CONSTRAINT-DIRECTED placement-refinement loop.
# ============================================================================
# Closes the placement side of the self-correcting loop: take an existing board,
# run the constraint registry (cec_constraints) to get TYPED DIRECTIVES, apply
# them as placement moves, legalize, re-check, and repeat until the actionable
# FAILs clear (or escalate). This is the consumer for cec_constraints.directives().
#
# Directive -> placement operation:
#   separate(a,b,min_mm)  -> push a (and its owned local-passive cluster) away from b
#   adjacent(a,b,max_mm)  -> pull a toward b
#   pin(target,x,y,rot)   -> set position/rotation
#   region(target,edge)   -> move to a board edge          (TODO)
#   align(parts,axis)     -> snap to a common axis/pitch    (TODO)
#   keepout(region)       -> reserve area for routing       (recorded, not a move)
#
# It moves a COPY of the board (never the committed floorplan), and re-checks with
# the real registry each pass -- the same discipline as the router loop.
#
#   python3 scripts/cec_place.py --board <module> [--demo] [--out DIR]
# ============================================================================
import os, sys, math, json, shutil, collections

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_constraints as K   # registry + checkers + directives()


def _mm(v):
    return v / 1e6


def _nm(v):
    return int(round(v * 1e6))


def _fp(board, ref):
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            return fp
    return None


def _pad_dist(a, b):
    return K._min_pad_dist_mm(a, b)


def _owner_pad_dist(a, b):
    """(min A-pad<->B-pad distance on a SHARED net, the target B-pad position) -- the actual bypass
    loop the decoupling checker measures. Falls back to footprint centres if there is no shared net,
    so the cap is pulled toward the IC's POWER pad, not just its nearest (often GND) pad."""
    POWER = ("+3V3", "+5VSB", "VBUS", "VREF", "+3.3", "VDD", "VCC")
    best, tgt = 1e9, None
    for pa in a.Pads():
        na = pa.GetNetname() or ""
        if not any(p in na.upper() for p in POWER):   # the POWER net only (match the checker, not GND)
            continue
        for pb in b.Pads():
            if pb.GetNetname() == na:
                d = math.hypot(_mm(pa.GetPosition().x - pb.GetPosition().x),
                               _mm(pa.GetPosition().y - pb.GetPosition().y))
                if d < best:
                    best, tgt = d, pb.GetPosition()
    if tgt is None:
        return _pad_dist(a, b), b.GetPosition()
    return best, tgt


def _cluster(board, fp, cluster_mm=4.0):
    """The footprint's owned LOCAL passives -- C*/R* within cluster_mm that share a net with it
    (its decoupling / local network). These travel WITH the part so the cluster stays intact."""
    fnets = {(p.GetNetname() or "") for p in fp.Pads()} - {""}
    out = []
    for o in board.GetFootprints():
        r = o.GetReference()
        if o is fp or not (r.startswith("C") or r.startswith("R")):
            continue
        onets = {(p.GetNetname() or "") for p in o.Pads()} - {""}
        if (fnets & onets) and _pad_dist(fp, o) <= cluster_mm:
            out.append(o)
    return out


def _move(fp, dx_mm, dy_mm):
    p = fp.GetPosition()
    fp.SetPosition(pcbnew.VECTOR2I(p.x + _nm(dx_mm), p.y + _nm(dy_mm)))


def _pad_union_bbox(fp):
    """Copper extent (mm AABB) = union of the footprint's pad bboxes -- the collision-relevant geometry
    (NOT GetBoundingBox, which includes silk/value text and is far too large)."""
    xs, ys = [], []
    for p in fp.Pads():
        pb = p.GetBoundingBox()
        xs += [_mm(pb.GetLeft()), _mm(pb.GetRight())]
        ys += [_mm(pb.GetTop()), _mm(pb.GetBottom())]
    if not xs:
        bb = fp.GetBoundingBox()
        return (_mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom()))
    return (min(xs), min(ys), max(xs), max(ys))


def _crtyd_bbox(fp):
    """The footprint's COURTYARD bbox (the real keep-away DRC uses for courtyards_overlap); falls back
    to the pad-copper extent if no courtyard is defined."""
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        try:
            poly = fp.GetCourtyard(layer)
            if poly and poly.OutlineCount() > 0:
                bb = poly.BBox()
                return (_mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom()))
        except Exception:
            pass
    return _pad_union_bbox(fp)


def _overlaps(board, fp, exclude, clear=0.1):
    """Legalization guard: ref of a non-excluded footprint whose COURTYARD comes within `clear` mm of
    fp's courtyard (true collision test -- the pad-CENTRE-distance version let copper overlap because
    it ignored pad size, which created real +3V3<->GND / sense<->GND shorts)."""
    a = _crtyd_bbox(fp)
    for o in board.GetFootprints():
        if o is fp or o.GetReference() in exclude or not list(o.Pads()):
            continue
        if _box_gap(a, _crtyd_bbox(o)) < clear:
            return o.GetReference()
    return None


def _shove(board, fp, ux, uy, exclude, max_shove=4.0, step=0.4):
    """MAKE-ROOM: push fp along (ux,uy) until it clears every non-excluded part. Returns the distance
    shoved, or 0.0 (reverted) if it cannot clear within max_shove -- bounded, so no runaway cascade."""
    n = math.hypot(ux, uy) or 1.0
    ux, uy = ux / n, uy / n
    moved = 0.0
    while moved < max_shove:
        _move(fp, ux * step, uy * step)
        moved += step
        if not _overlaps(board, fp, exclude):
            return moved
    _move(fp, -ux * moved, -uy * moved)
    return 0.0


def _on_board(board, fp):
    bb = board.GetBoardEdgesBoundingBox()
    l, t, r, b = _mm(bb.GetLeft()), _mm(bb.GetTop()), _mm(bb.GetRight()), _mm(bb.GetBottom())
    c = fp.GetPosition()
    return l + 1 <= _mm(c.x) <= r - 1 and t + 1 <= _mm(c.y) <= b - 1


# ---- directive appliers ----------------------------------------------------
def apply_separate(board, a_ref, b_ref, min_mm, margin=0.8, step=0.4, max_move=12.0):
    """Push a away from b (along the b->a axis), carrying a's owned cluster, until the min pad-to-pad
    distance >= min_mm + margin (matching the hot-sensitive-separation checker's metric)."""
    a, b = _fp(board, a_ref), _fp(board, b_ref)
    if not a or not b:
        return None
    ax, ay = _mm(a.GetPosition().x), _mm(a.GetPosition().y)
    bx, by = _mm(b.GetPosition().x), _mm(b.GetPosition().y)
    ux, uy = ax - bx, ay - by
    n = math.hypot(ux, uy) or 1.0
    ux, uy = ux / n, uy / n
    cluster = _cluster(board, a)
    exclude = {a_ref, b_ref} | {c.GetReference() for c in cluster}
    start = _pad_dist(a, b)
    moved = 0.0
    stopped = ""
    while _pad_dist(a, b) < min_mm + margin and moved < max_move and _on_board(board, a):
        _move(a, ux * step, uy * step)
        for c in cluster:
            _move(c, ux * step, uy * step)
        hit = _overlaps(board, a, exclude)
        if hit:                                  # legalize: back off and stop before colliding
            _move(a, -ux * step, -uy * step)
            for c in cluster:
                _move(c, -ux * step, -uy * step)
            stopped = "blocked by %s" % hit
            break
        moved += step
    return {"op": "separate", "a": a_ref, "b": b_ref, "moved_mm": round(moved, 2),
            "cluster": [c.GetReference() for c in cluster],
            "moved_refs": [a_ref] + [c.GetReference() for c in cluster],
            "pad_mm": "%.2f->%.2f" % (start, _pad_dist(a, b)), "note": stopped}


def _adj_score(a, b):
    """RANKING metric for an adjacency candidate (lower = better). Sum of the per-shared-net nearest
    pad-pair distances between a and b. PREFERS power nets if any are shared (the decoupling-loop metric
    -- keeps cap placement identical to the power-pad-only behaviour); otherwise uses ALL shared nets, so
    a sense IC <-> shunt candidate is rewarded for bringing BOTH its sense pads (IN+/IN-, i.e. _HI AND _LO)
    to the shunt at once -- the orientation that faces the input pads at the shunt inner edge wins."""
    POWER = ("+3V3", "+5VSB", "VBUS", "VREF", "+3.3", "VDD", "VCC")
    per_net = {}
    for pa in a.Pads():
        na = pa.GetNetname() or ""
        if not na:
            continue
        for pb in b.Pads():
            if pb.GetNetname() == na:
                d = math.hypot(_mm(pa.GetPosition().x - pb.GetPosition().x),
                               _mm(pa.GetPosition().y - pb.GetPosition().y))
                per_net[na] = min(per_net.get(na, 1e9), d)
    if not per_net:
        return _pad_dist(a, b)
    pw = {n: d for n, d in per_net.items() if any(p in n.upper() for p in POWER)}
    return sum((pw or per_net).values())


def apply_adjacent(board, a_ref, b_ref, max_mm, margin=0.5):
    a, b = _fp(board, a_ref), _fp(board, b_ref)
    if not a or not b:
        return None
    # Place a CLEAR-but-CLOSE to b, searching POSITION *and* ROTATION. A straight slide stalls when the
    # target is reachable from one side only, and a fixed orientation can't face a multi-pad IC's input
    # pads at its neighbour. So: SEARCH a ring of candidate centres around b's relevant pad AND a set of
    # candidate rotations, scoring each clear pose by _adj_score (the shared-net pad loop). For a
    # decoupling cap this reduces to the old power-pad behaviour; for an INA238 <-> shunt it lets the part
    # ROTATE so IN+/IN- (the _HI/_LO sense pads) both end up against the shunt inner edge (user's call --
    # rotation is a valid test option). _overlaps includes b, so a can never land a pad on it.
    start, tgt = _owner_pad_dist(a, b)
    if start <= max_mm - margin:
        return {"op": "adjacent", "a": a_ref, "b": b_ref, "moved_mm": 0.0, "rot": None, "moved_refs": [a_ref],
                "shoved": [], "pad_mm": "%.2f->%.2f" % (start, start), "note": "already ok"}
    px, py = _mm(tgt.x), _mm(tgt.y)
    orig, orot = a.GetPosition(), a.GetOrientationDegrees()
    rots = []
    for r in (orot, 0.0, 90.0, 180.0, 270.0):                # current first, then the cardinals (deduped)
        rr = round(r % 360.0, 1)
        if rr not in rots:
            rots.append(rr)
    # SIZE-AWARE ring: two big parts (a 3mm INA238 next to a 3mm shunt) can't sit within 3.5mm
    # centre-to-centre without a courtyard overlap, so the ring must reach out past the sum of their
    # half-extents. A tiny decoupling cap still finds its clear pose at a small radius and early-breaks,
    # so extending the ceiling only ADDS candidates (the closest clear one wins).
    ah = _crtyd_bbox(a)
    bh = _crtyd_bbox(b)
    reach = (max(ah[2] - ah[0], ah[3] - ah[1]) + max(bh[2] - bh[0], bh[3] - bh[1])) / 2.0
    best, bestd = None, 1e9                                   # best = (cx, cy, rot)
    for rad in _arange(1.0, max(3.5, reach + 3.0), 0.5):
        for rot in rots:
            a.SetOrientationDegrees(rot)
            for ang in range(0, 360, 20):
                cx = px + rad * math.cos(math.radians(ang))
                cy = py + rad * math.sin(math.radians(ang))
                a.SetPosition(pcbnew.VECTOR2I(_nm(cx), _nm(cy)))
                if _overlaps(board, a, {a_ref}):
                    continue
                dd = _adj_score(a, b)
                # tie-break toward the ORIGINAL rotation so a symmetric part isn't flipped gratuitously
                dd += 0.05 * (abs(((rot - orot + 180) % 360) - 180) / 90.0)
                if dd < bestd:
                    bestd, best = dd, (cx, cy, rot)
        if best and bestd <= max_mm - margin:
            break
    if best:
        a.SetOrientationDegrees(best[2])
        a.SetPosition(pcbnew.VECTOR2I(_nm(best[0]), _nm(best[1])))
        moved = math.hypot(_mm(a.GetPosition().x - orig.x), _mm(a.GetPosition().y - orig.y))
        rot_applied = None if round(best[2], 1) == round(orot, 1) else best[2]
    else:
        a.SetOrientationDegrees(orot)
        a.SetPosition(orig)
        moved, rot_applied = 0.0, None
    end, _ = _owner_pad_dist(a, b)
    note = "" if end <= max_mm else "no clear spot within %.1fmm of %s" % (max_mm, b_ref)
    return {"op": "adjacent", "a": a_ref, "b": b_ref, "moved_mm": round(moved, 2), "rot": rot_applied,
            "moved_refs": [a_ref], "shoved": [], "pad_mm": "%.2f->%.2f" % (start, end), "note": note}


def _kelvin_pairs(board):
    """[(shunt_ref, ina238_ref), ...] -- each RS* shunt paired with the INA238/INA228 CURRENT-SENSE part
    that shares one of its _HI/_LO sense nets (the §6.8 precision Kelvin pair). The coarse INA181
    detection CSA is intentionally NOT paired here -- it is a secondary tap, left to the router."""
    shunts, inas = {}, []
    for fp in board.GetFootprints():
        ref, val = fp.GetReference(), (fp.GetValue() or "").upper()
        nets = {p.GetNetname() for p in fp.Pads() if p.GetNetname()}
        if ref.upper().startswith("RS"):
            shunts[ref] = {n for n in nets if n.endswith("_HI") or n.endswith("_LO")}
        elif ref.startswith("U") and ("INA238" in val or "INA228" in val):
            inas.append((ref, nets))
    pairs = []
    for sref, snets in shunts.items():
        for iref, inets in inas:
            if snets & inets:
                pairs.append((sref, iref))
                break
    return pairs


def tighten_kelvin(in_path, out_path, max_mm=2.0):
    """Pull+ROTATE each INA238 hard against its shunt (short Kelvin loop, §6.8), tighter than the ratified
    5mm PASS bar -- an optimisation so the deterministic Kelvin tap (cec_hc) is a short, straight,
    DRC-clean segment. Run BEFORE the decoupling refine so the caps re-cluster to the INA's final tight
    position (no oscillation). Rips the moved INAs' signal nets for re-route. Returns the applied moves."""
    shutil.copyfile(in_path, out_path)
    board = pcbnew.LoadBoard(out_path)
    applied, moved_refs = [], []
    for shunt_ref, ina_ref in _kelvin_pairs(board):
        r = apply_adjacent(board, ina_ref, shunt_ref, max_mm)
        if r and r.get("moved_mm", 0.0) > 0.0:
            applied.append(r)
            moved_refs += r.get("moved_refs", [])
    if moved_refs:
        _ripup_signal_nets(board, sorted(set(moved_refs)))
    board.Save(out_path)
    return applied


def apply_pin(board, target, x, y, rot=None):
    fp = _fp(board, target)
    if not fp:
        return None
    fp.SetPosition(pcbnew.VECTOR2I(_nm(x), _nm(y)))
    if rot is not None:
        fp.SetOrientationDegrees(rot)
    return {"op": "pin", "target": target, "to": (x, y, rot), "moved_refs": [target]}


def _ripup_signal_nets(board, refs):
    """Hand the moved parts' SIGNAL nets back to the router: delete their tracks/vias so they re-route
    around the new placement. Planes / power rails / high-current force nets are KEPT (a part move
    shouldn't rip the GND plane or the 12V pours). This is the placement->routing handoff."""
    KEEP = ("GND", "+3V3", "+5V", "+12V", "VBUS", "VCC", "12V", "SENSEP", "_HI", "_LO")
    nets = set()
    for r in refs:
        fp = _fp(board, r)
        if not fp:
            continue
        for p in fp.Pads():
            n = p.GetNetname() or ""
            if n and not any(k in n.upper() for k in KEEP):
                nets.add(n)
    removed = 0
    for t in list(board.GetTracks()):
        if t.GetNetname() in nets:
            board.Remove(t)
            removed += 1
    return sorted(nets), removed


def _arange(a, b, step):
    out, x = [], a
    while x <= b:
        out.append(x)
        x += step
    return out


def _box_gap(a, b):
    """Edge-to-edge gap (mm) between two AABBs (l,t,r,b); 0 when they overlap or touch."""
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return math.hypot(dx, dy)


def _scale_logo(logo, factor):
    """Shrink the decorative logo's copper graphics about its origin (the logo is resizable).
    Best-effort -- a failure just leaves the logo full-size."""
    o = logo.GetPosition()
    for gi in list(logo.GraphicalItems()):
        try:
            ps = gi.GetPolyShape()
        except Exception:
            ps = None
        if ps is None:
            continue
        try:
            for oi in range(ps.OutlineCount()):
                ch = ps.Outline(oi)
                for pi in range(ch.PointCount()):
                    p = ch.CPoint(pi)
                    ch.SetPoint(pi, pcbnew.VECTOR2I(o.x + int((p.x - o.x) * factor),
                                                    o.y + int((p.y - o.y) * factor)))
            gi.SetPolyShape(ps)
        except Exception:
            pass


def relocate_logo_to_clear(board_path, margin=0.6, save=True):
    """The decorative LOGO is movable/resizable, so the clean fix for a logo<->routing conflict is to
    move it OUT of the traffic: relocate it to the clearest open board region and return an FR keepout
    rect over its new location (so the router still never crosses it). Returns the keepout dict, or None."""
    board = pcbnew.LoadBoard(board_path)
    logo = next((fp for fp in board.GetFootprints()
                 if fp.GetReference().upper().startswith("LOGO")), None)
    if not logo:
        return None
    bb = logo.GetBoundingBox()
    w, h = _mm(bb.GetWidth()), _mm(bb.GetHeight())
    eb = board.GetBoardEdgesBoundingBox()
    l, t, r, b = _mm(eb.GetLeft()), _mm(eb.GetTop()), _mm(eb.GetRight()), _mm(eb.GetBottom())
    obxs = []                                              # other footprints' bboxes (mm)
    for fp in board.GetFootprints():
        if fp is logo or not list(fp.Pads()):
            continue
        fb = fp.GetBoundingBox()
        obxs.append((_mm(fb.GetLeft()), _mm(fb.GetTop()), _mm(fb.GetRight()), _mm(fb.GetBottom())))

    def _clearance(cx, cy, ww, hh):
        box = (cx - ww / 2, cy - hh / 2, cx + ww / 2, cy + hh / 2)
        return min((_box_gap(box, o) for o in obxs), default=1e3)

    # the logo is RESIZABLE: try the full size first, shrink only if nothing fits clear.
    best, best_score, scale = None, -1.0, 1.0
    for s in (1.0, 0.75, 0.55, 0.4):
        ww, hh = w * s, h * s
        bb_, bs_ = None, -1.0
        for cx in _arange(l + ww / 2 + margin, r - ww / 2 - margin, 1.5):
            for cy in _arange(t + hh / 2 + margin, b - hh / 2 - margin, 1.5):
                g = _clearance(cx, cy, ww, hh)
                if g > bs_:
                    bs_, bb_ = g, (cx, cy)
        if bb_ and bs_ >= margin:                          # a non-overlapping spot at this size
            best, best_score, scale = bb_, bs_, s
            break
    if not best:
        return None                                        # nowhere clear even shrunk -> leave it
    if scale < 1.0:
        _scale_logo(logo, scale)
        w, h = w * scale, h * scale
    # SetPosition sets the footprint ORIGIN; offset so the logo's bbox CENTRE lands at `best`
    cur, cen = logo.GetPosition(), bb.GetCenter()
    logo.SetPosition(pcbnew.VECTOR2I(_nm(best[0]) + (cur.x - cen.x), _nm(best[1]) + (cur.y - cen.y)))
    if save:
        board.Save(board_path)
    return {"name": "logo_keepout", "layers": ("F.Cu", "B.Cu"),
            "x0": best[0] - w / 2 - margin, "y0": best[1] - h / 2 - margin,
            "x1": best[0] + w / 2 + margin, "y1": best[1] + h / 2 + margin}


def apply_directive(board, d):
    t = d.get("type") or d.get("directive")
    try:
        if t == "separate" and d.get("a") and d.get("b"):
            return apply_separate(board, d["a"], d["b"], float(d.get("min_mm", 8.0)))
        if t == "adjacent" and d.get("a") and d.get("b") and _fp(board, d["b"]):
            return apply_adjacent(board, d["a"], d["b"], float(d.get("max_mm", 3.5)))
        if t == "pin" and d.get("target") and d.get("x") is not None:
            return apply_pin(board, d["target"], float(d["x"]), float(d["y"]), d.get("rot"))
    except Exception as e:
        return {"op": t, "error": repr(e)}
    return None   # region/align/keepout/rename -> not a single-part move (handled elsewhere)


# ---- the refinement loop ---------------------------------------------------
MOVABLE = ("separate", "adjacent", "pin")


def _check(board_path, ctx):
    """Re-check via a FRESH subprocess. pcbnew's in-process state is unreliable after destructive
    board edits (Remove/Save leave swig objects dangling), so a same-process re-check can MIS-READ
    the board. A clean child process is the trustworthy verdict (the cec_fr / cec_router discipline)."""
    import subprocess
    args = [sys.executable, os.path.join(ROOT, "scripts", "cec_constraints.py"), board_path, "--json"]
    if ctx.get("radio"):
        args.append("--radio")
    r = subprocess.run(args, capture_output=True, text=True)
    try:
        blob = json.loads(r.stdout[r.stdout.index("["):])[0]
        return blob.get("verdicts", []), blob.get("directives", [])
    except Exception:
        return [], []


def _fails(verdicts):
    return {v["id"]: v["detail"] for v in verdicts if v.get("status") == "FAIL"}


def refine(in_path, out_path, ctx=None, max_iters=4):
    """cec_constraints -> directives -> apply movers (+ rip moved signal nets for re-route) -> re-check,
    looped on a COPY. Every re-check is a fresh subprocess (clean board state)."""
    ctx = ctx or {}
    shutil.copyfile(in_path, out_path)
    history = []
    for it in range(max_iters):
        _, ds = _check(out_path, ctx)
        movers = [d for d in ds if (d.get("type") or d.get("directive")) in MOVABLE]
        if not movers:
            history.append({"iter": it, "applied": [], "note": "no actionable mover directives"})
            break
        board = pcbnew.LoadBoard(out_path)
        applied = [a for a in (apply_directive(board, d) for d in movers) if a]
        moved_refs = sorted({r for a in applied for r in a.get("moved_refs", [])})
        ripped, n_removed = _ripup_signal_nets(board, moved_refs) if moved_refs else ([], 0)
        board.Save(out_path)
        del board
        history.append({"iter": it, "applied": applied,
                        "ripped_for_reroute": ripped, "tracks_removed": n_removed})
        # stop when a pass makes no real progress (e.g. remaining caps are blocked by their IC)
        if not applied or sum(a.get("moved_mm", 0.0) for a in applied) < 0.1:
            break
    verdicts, _ = _check(out_path, ctx)
    return verdicts, history


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="cec_place -- constraint-directed placement refinement")
    ap.add_argument("--board", default="12vhpwr-standard")
    ap.add_argument("--radio", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "place"))
    a = ap.parse_args(argv)

    import glob
    cands = [p for p in glob.glob(os.path.join(ROOT, "modules", a.board, "*.kicad_pcb"))
             if "-routed" not in p and ".merged." not in p]
    src = sorted(cands)[0]
    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, os.path.basename(src).replace(".kicad_pcb", "-refined.kicad_pcb"))
    ctx = {"radio": a.radio}

    bverd, _ = _check(src, ctx)
    print("BEFORE  FAILs:", sorted(_fails(bverd)))
    verdicts, hist = refine(src, out, ctx)
    print("\nREFINE LOG:")
    for h in hist:
        for ap_ in h.get("applied", []):
            print("  iter%d:" % h["iter"], json.dumps(ap_))
        if h.get("ripped_for_reroute"):
            print("  iter%d: ripped %d tracks on %s -> hand to router"
                  % (h["iter"], h["tracks_removed"], h["ripped_for_reroute"]))
        if h.get("note"):
            print("  iter%d: %s" % (h["iter"], h["note"]))
    after = _fails(verdicts)
    fixed = set(_fails(bverd)) - set(after)
    print("\nRESOLVED by the placer loop:", sorted(fixed))
    print("REMAINING FAILs:", sorted(after))
    print("refined board ->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
