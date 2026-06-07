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


def _overlaps(board, fp, exclude, clear=0.4):
    """Minimal legalization guard: ref of the nearest non-excluded footprint within `clear` mm of fp
    (so a move stops before piling a part on top of another)."""
    for o in board.GetFootprints():
        if o is fp or o.GetReference() in exclude or not list(o.Pads()):
            continue
        if _pad_dist(fp, o) < clear:
            return o.GetReference()
    return None


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


def apply_adjacent(board, a_ref, b_ref, max_mm, margin=0.5, step=0.4, max_move=20.0):
    a, b = _fp(board, a_ref), _fp(board, b_ref)
    if not a or not b:
        return None
    cluster = _cluster(board, a)
    exclude = {a_ref, b_ref} | {c.GetReference() for c in cluster}
    start = _pad_dist(a, b)
    moved = 0.0
    stopped = ""
    while _pad_dist(a, b) > max_mm - margin and moved < max_move:
        ax, ay = _mm(a.GetPosition().x), _mm(a.GetPosition().y)
        bx, by = _mm(b.GetPosition().x), _mm(b.GetPosition().y)
        ux, uy = bx - ax, by - ay
        nn = math.hypot(ux, uy) or 1.0
        dx, dy = ux / nn * step, uy / nn * step
        _move(a, dx, dy)
        for c in cluster:
            _move(c, dx, dy)
        hit = _overlaps(board, a, exclude)
        if hit:                                  # legalize: back off and stop before colliding
            _move(a, -dx, -dy)
            for c in cluster:
                _move(c, -dx, -dy)
            stopped = "blocked by %s" % hit
            break
        moved += step
    return {"op": "adjacent", "a": a_ref, "b": b_ref, "moved_mm": round(moved, 2),
            "moved_refs": [a_ref] + [c.GetReference() for c in cluster],
            "pad_mm": "%.2f->%.2f" % (start, _pad_dist(a, b)), "note": stopped}


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
        if not applied:
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
