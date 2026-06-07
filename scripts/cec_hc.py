#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_hc -- the DETERMINISTIC HIGH-CURRENT routing pass.
# ============================================================================
# Freerouting doesn't know the high-current intent: it via's the Kelvin sense, taps the
# shunt arbitrarily, and routes foreign signals through the 12V pour (cutting the fill).
# This pass fixes the high-current copper deterministically, run AFTER Freerouting:
#   1. RIP any prior TRACKS/VIAS on the high-current (_HI/_LO) nets -- the pours are ZONES
#      and stay, so the force path is untouched; only FR's via'd/arbitrary sense is removed.
#   2. Lay the Kelvin SENSE TAP from the INNER edge of each shunt pad to the INA238 (the
#      precision CURRENT-SENSE part, §6.8) input pads, F.Cu, no via -- straight + short.
#      DO NO HARM: a tap is laid ONLY if its path is geometrically clear of foreign copper
#      (the INA's own GND pad, a +3V3/GND track in a too-wide gap). A tap that would short
#      is SKIPPED and REPORTED in needs_placement -- a signal for the loop to pull/ROTATE the
#      INA238 hard against the shunt, never a short the router introduces. The coarse INA181
#      detection tap (§6.13) is left to FR / the placement feedback, not forced.
#   3. Re-fill the zones in a FRESH PROCESS (an in-process fill right after the rip+add
#      HARD-CRASHES this KiCad-10 build; a clean child LoadBoard fills fine).
# Pair it with pour_region_keepouts() fed to route_once(hints=...) BEFORE FR, so FR keeps
# foreign signals off the pour layers and the fill stays whole.
#
#   python3 scripts/cec_hc.py <in.kicad_pcb> <out.kicad_pcb>   (--fill <board> = re-fill only)
# ============================================================================
import os, sys, math, shutil, collections

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_fr       # derive_power_pours

MM = 1e6


def _kelvin_stubs(board, hc_nets):
    """[(net, [inner_edge_pt_mm, ina_input_pad_mm]), ...] -- the short F.Cu sense tap from each shunt
    pad's INNER edge (facing the other terminal) to the INA input pad on that net.

    Holds NO pad/footprint SWIG wrappers past the scan: on this KiCad-10 build, RETAINING pad/footprint
    wrappers in a structure and then destroying them (e.g. when this function returns) corrupts the
    board's internal state and HARD-CRASHES the next ZONE_FILLER/UnFill. So everything is reduced to
    plain Python numbers during the single footprint scan -- nothing SWIG outlives this loop."""
    # Per sense net, collect candidate sense-input pads in PRECEDENCE tiers (primitives only -- no SWIG
    # wrappers retained). The precision Kelvin tap goes to the INA238/INA228 CURRENT-SENSE part (§6.8);
    # the coarse INA181 detection CSA (§6.13) and any other U are only used if no INA238 is on the net.
    ina238, ina_other, u_other, shunts = (collections.defaultdict(list), collections.defaultdict(list),
                                          collections.defaultdict(list), [])
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        is_u = ref.startswith("U")
        val = (fp.GetValue() or "").upper()
        is_238 = ("INA238" in val) or ("INA228" in val)
        is_ina = "INA" in val
        padlist = []                                          # [(net, px, py, hw, hh), ...] -- primitives only
        for p in fp.Pads():
            n = p.GetNetname()
            pos, bb = p.GetPosition(), p.GetBoundingBox()     # bbox = BOARD-frame extent (rotation-correct)
            hw, hh = (bb.GetRight() - bb.GetLeft()) / 2.0, (bb.GetBottom() - bb.GetTop()) / 2.0
            padlist.append((n, pos.x, pos.y, hw, hh))
            if n and is_u:
                (ina238 if is_238 else ina_other if is_ina else u_other)[n].append((pos.x, pos.y))
        if ref.upper().startswith("RS") and len(padlist) == 2:
            shunts.append(padlist)
    stubs = []
    for padlist in shunts:
        cen = [(px, py) for (_n, px, py, _hw, _hh) in padlist]
        for i, (net, px, py, hw, hh) in enumerate(padlist):
            if net not in hc_nets:
                continue
            ox, oy = cen[1 - i]
            ix, iy = ox - px, oy - py                         # inner direction (toward the other terminal)
            inn = math.hypot(ix, iy) or 1.0
            ix, iy = ix / inn, iy / inn
            reach = (abs(ix) * hw + abs(iy) * hh) * 0.7       # ~70% of the BOARD-frame half-extent toward
            inner = ((px + ix * reach) / MM, (py + iy * reach) / MM)   # the inner edge -- stays on pad copper
            targets = ina238.get(net) or ina_other.get(net) or u_other.get(net) or []
            for (tx, ty) in targets:                          # tap the inner edge to EACH sense pad on the net
                stubs.append((net, [inner, (tx / MM, ty / MM)]))
    return stubs


def _tap_paths(inner, pad):
    """Candidate tap routes from the shunt inner edge `inner` to the INA input `pad`, BEST FIRST. A
    straight diagonal often clips the pad's neighbour (the INA's GND pin sits next to its sense pins), so
    after the straight try two L-paths whose FINAL leg approaches the pad along an axis (perpendicular
    entry between the pad's row-neighbours -- the clean way into a fine-pitch pad). The do-no-harm gate
    picks the first whose every leg is clear."""
    ix, iy = inner
    px, py = pad
    return [
        [inner, pad],                                        # straight
        [inner, (ix, py), pad],                              # vertical leg, then approach the pad along x
        [inner, (px, iy), pad],                              # horizontal leg, then approach the pad along y
    ]


def kelvin_keepouts(board_path, margin=0.3):
    """FR keepout rects over each shunt<->INA238 GAP (F.Cu only), so Freerouting keeps FOREIGN signals out
    of the Kelvin corridor and the deterministic sense tap lands clean. The rect spans the two parts'
    courtyard gap but is trimmed NOT to cover the INA body (FR must still reach the INA's power/I2C pads).
    Feed to route_once(hints=...). Loaded in its own call (one board load)."""
    board = pcbnew.LoadBoard(board_path)
    pairs = _kelvin_pairs_local(board)
    kos = []
    for k, (sx0, sy0, sx1, sy1) in enumerate(pairs):
        kos.append({"name": "kelvin_%d" % k, "x0": sx0 - margin, "y0": sy0 - margin,
                    "x1": sx1 + margin, "y1": sy1 + margin, "layers": ("F.Cu",), "allow_vias": True})
    return kos


def _kelvin_pairs_local(board):
    """[(x0,y0,x1,y1), ...] -- the mm bbox of the GAP between each shunt's sense pads and its INA238 sense
    pads (the corridor the Kelvin tap runs through). Primitives only (no retained SWIG wrappers)."""
    shunts, inas = [], []
    for fp in board.GetFootprints():
        ref, val = fp.GetReference(), (fp.GetValue() or "").upper()
        is_238 = ("INA238" in val) or ("INA228" in val)
        sense = [(p.GetNetname(), p.GetPosition().x / MM, p.GetPosition().y / MM)
                 for p in fp.Pads() if (p.GetNetname() or "").endswith(("_HI", "_LO"))]
        if ref.upper().startswith("RS") and sense:
            shunts.append(sense)
        elif ref.startswith("U") and is_238 and sense:
            inas.append(sense)
    out = []
    for s in shunts:
        snets = {n for n, _x, _y in s}
        for i in inas:
            if snets & {n for n, _x, _y in i}:
                xs = [x for _n, x, _y in s + i]
                ys = [y for _n, _x, y in s + i]
                out.append((min(xs), min(ys), max(xs), max(ys)))
                break
    return out


def keepouts_from_pours(pours, margin=0.2):
    """Convert derive_power_pours() rects into FR keepout dicts (both outer layers), so Freerouting keeps
    FOREIGN signals out of the 12V pour regions -> the pour fills whole. Feed to route_once(hints=...)."""
    kos = []
    for i, p in enumerate(pours):
        (x0, y0), _, (x1, y1), _ = p["polygon"]
        kos.append({"name": "hc_pour_%d" % i, "x0": min(x0, x1) - margin, "y0": min(y0, y1) - margin,
                    "x1": max(x0, x1) + margin, "y1": max(y0, y1) + margin, "layers": ("F.Cu", "B.Cu")})
    return kos


def pour_region_keepouts(board_path, margin=0.2):
    return keepouts_from_pours(cec_fr.derive_power_pours(board_path), margin)


# ---- clearance geometry (the DO-NO-HARM gate: never lay a Kelvin tap that shorts) -----------------
def _seg_pt_dist(x0, y0, x1, y1, px, py):
    """Min distance (mm) from point (px,py) to segment (x0,y0)-(x1,y1)."""
    dx, dy = x1 - x0, y1 - y0
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return math.hypot(px - x0, py - y0)
    t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / l2))
    return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))


def _seg_seg_dist(ax0, ay0, ax1, ay1, bx0, by0, bx1, by1):
    """Min distance (mm) between two segments; 0 if they cross."""
    d = ((bx1 - bx0) * (ay0 - by0) - (by1 - by0) * (ax0 - bx0))
    den = ((by1 - by0) * (ax1 - ax0) - (bx1 - bx0) * (ay1 - ay0))
    if den != 0:
        ua = d / den
        ub = ((ax1 - ax0) * (ay0 - by0) - (ay1 - ay0) * (ax0 - bx0)) / den
        if 0 <= ua <= 1 and 0 <= ub <= 1:
            return 0.0                                        # they cross
    return min(_seg_pt_dist(ax0, ay0, ax1, ay1, bx0, by0), _seg_pt_dist(ax0, ay0, ax1, ay1, bx1, by1),
               _seg_pt_dist(bx0, by0, bx1, by1, ax0, ay0), _seg_pt_dist(bx0, by0, bx1, by1, ax1, ay1))


def _seg_rect_dist(x0, y0, x1, y1, l, t, r, b):
    """Min distance (mm) from segment (x0,y0)-(x1,y1) to AABB (l,t,r,b); 0 if it enters the box. Using the
    real pad rectangle (not a half-diagonal disc) is essential for fine-pitch pads -- a 0.3mm-wide VSSOP
    pad's half-diagonal is ~0.7mm, which falsely 'blocks' a tap to a 0.5mm-pitch neighbour."""
    if l <= x0 <= r and t <= y0 <= b:
        return 0.0
    if l <= x1 <= r and t <= y1 <= b:
        return 0.0
    return min(_seg_seg_dist(x0, y0, x1, y1, l, t, r, t),     # the 4 rectangle edges
               _seg_seg_dist(x0, y0, x1, y1, r, t, r, b),
               _seg_seg_dist(x0, y0, x1, y1, r, b, l, b),
               _seg_seg_dist(x0, y0, x1, y1, l, b, l, t))


def _obstacle_pads(board):
    """Footprint-pad obstacles as primitives (mm): [(net, l, t, r, b)] -- the pad's REAL bounding box (not
    a half-diagonal disc; a thin fine-pitch pad's half-diagonal grossly overstates it). MUST be read
    BEFORE any board.Remove() -- a rip invalidates the footprint container view (board.GetFootprints()
    then yields raw SwigPyObjects with no .Pads())."""
    pads = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if not p.GetLayerSet().Contains(pcbnew.F_Cu):    # the tap is F.Cu; a B.Cu-only pad can't short it
                continue
            bb = p.GetBoundingBox()
            pads.append((p.GetNetname() or "", bb.GetLeft() / MM, bb.GetTop() / MM,
                         bb.GetRight() / MM, bb.GetBottom() / MM))
    return pads


def _obstacle_tracks(board, exclude_nets=()):
    """Track/via obstacles. MUST be read BEFORE the rip (board.Remove invalidates the track view too);
    pass exclude_nets=hc_nets so the about-to-be-ripped _HI/_LO tracks aren't counted (same-net copper is
    ignored by the clearance gate anyway, but the OTHER sense net's old track would otherwise mis-block).
    Returns (via_boxes as pad tuples (net,l,t,r,b), track segs as [(net, x0,y0,x1,y1, halfwidth)])."""
    vpads, segs = [], []
    for t in board.GetTracks():
        if t.GetNetname() in exclude_nets:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            c = t.GetPosition()                              # a via spans F.Cu -> it CAN short the F.Cu tap
            try:
                r = t.GetWidth(t.TopLayer()) / 2 / MM
            except Exception:
                r = 0.3
            cx, cy = c.x / MM, c.y / MM
            vpads.append((t.GetNetname() or "", cx - r, cy - r, cx + r, cy + r))
        elif t.GetLayer() == pcbnew.F_Cu:                    # only F.Cu tracks short an F.Cu tap (B.Cu is fine)
            s, e = t.GetStart(), t.GetEnd()
            segs.append((t.GetNetname() or "", s.x / MM, s.y / MM, e.x / MM, e.y / MM, t.GetWidth() / 2 / MM))
    return vpads, segs


def _tap_clear(seg, net, pads, segs, laid, halfw=0.125, clear=0.2):
    """True if the candidate tap `seg`=(x0,y0,x1,y1) on `net` keeps `clear` mm from all FOREIGN-net copper
    (pads, tracks, and already-laid taps). Same-net copper can't short, so it's ignored -- this is what
    makes the pass do-no-harm: a tap that would clip a GND pad / cross +3V3 is rejected, not laid."""
    x0, y0, x1, y1 = seg
    for pn, pl, pt, pr, pb in pads:
        if pn == net:
            continue
        if _seg_rect_dist(x0, y0, x1, y1, pl, pt, pr, pb) < halfw + clear:
            return False
    for sn, sx0, sy0, sx1, sy1, hw in segs:
        if sn == net:
            continue
        if _seg_seg_dist(x0, y0, x1, y1, sx0, sy0, sx1, sy1) < hw + halfw + clear:
            return False
    for ln, lx0, ly0, lx1, ly1 in laid:
        if ln == net:
            continue
        if _seg_seg_dist(x0, y0, x1, y1, lx0, ly0, lx1, ly1) < 2 * halfw + clear:
            return False
    return True


def route_high_current(in_path, out_path):
    """Deterministic high-current pass (see module docstring). Returns a summary dict."""
    # Load ONCE. A second pcbnew.LoadBoard in the same process (e.g. via derive_power_pours) corrupts
    # this build's SWIG footprint wrappers (board.GetFootprints() then yields raw SwigPyObjects), so the
    # high-current nets are computed inline here, not from derive_power_pours.
    board = pcbnew.LoadBoard(in_path)
    names = {n.GetNetname() for n in board.GetNetInfo().NetsByNetcode().values() if n.GetNetname()}
    hc_nets = {n for n in names if n.endswith("_HI") or n.endswith("_LO")}
    if not hc_nets:
        shutil.copyfile(in_path, out_path)
        return {"stubs": 0, "note": "no high-current nets"}
    netcode = {n.GetNetname(): n.GetNetCode() for n in board.GetNetInfo().NetsByNetcode().values()}
    fcu = board.GetLayerID("F.Cu")

    # 1. plan the Kelvin stubs + read footprint-pad obstacles FIRST -- board.Remove() below invalidates
    #    the footprint-container view, so read all footprint/pad geometry before ripping.
    stubs = _kelvin_stubs(board, hc_nets)
    obstacle_pads = _obstacle_pads(board)
    via_pads, obstacle_segs = _obstacle_tracks(board, exclude_nets=hc_nets)   # both BEFORE the rip
    obstacle_pads = obstacle_pads + via_pads

    # 2. rip prior TRACKS/VIAS on the high-current nets (the pours are zones -> untouched)
    ripped = 0
    for t in list(board.GetTracks()):
        if t.GetNetname() in hc_nets:
            board.Remove(t)
            ripped += 1

    # 3. lay the Kelvin sense taps: inner shunt edge -> INA238 input, F.Cu, no via -- but ONLY where the
    #    path is geometrically clear of foreign copper (DO NO HARM). A tap that would clip the INA's own
    #    GND pad or cross +3V3/GND in a too-wide shunt<->INA gap is SKIPPED and reported, not laid: that
    #    is a placement signal (move/ROTATE the INA238 hard against the shunt), the loop's job -- never a
    #    short the router introduces. Obstacles were read BEFORE the rip (the rip invalidates the SWIG
    #    track/footprint views) with the hc_nets excluded; same-net copper is ignored -- it can't short.
    w = int(0.25 * MM)
    added, laid, skipped = 0, [], []
    for net, pts in stubs:
        inner, pad = pts[0], pts[-1]
        chosen = None
        for path in _tap_paths(inner, pad):                  # straight first, then the two L approaches
            segs = [((x0, y0), (x1, y1)) for (x0, y0), (x1, y1) in zip(path, path[1:])
                    if math.hypot(x1 - x0, y1 - y0) >= 0.05]
            if segs and all(_tap_clear((a[0], a[1], b[0], b[1]), net, obstacle_pads, obstacle_segs, laid)
                            for a, b in segs):
                chosen = segs
                break
        if not chosen:
            skipped.append(net)
            continue
        for (x0, y0), (x1, y1) in chosen:                    # lay every leg of the clear path
            tr = pcbnew.PCB_TRACK(board)
            tr.SetStart(pcbnew.VECTOR2I(int(x0 * MM), int(y0 * MM)))
            tr.SetEnd(pcbnew.VECTOR2I(int(x1 * MM), int(y1 * MM)))
            tr.SetWidth(w)
            tr.SetLayer(fcu)
            tr.SetNetCode(netcode.get(net, 0))
            board.Add(tr)
            laid.append((net, x0, y0, x1, y1))
        added += 1

    # 4. save the ripped+stubbed board (NO fill yet)
    pcbnew.SaveBoard(out_path, board)

    # 5. RE-FILL in a FRESH PROCESS so the pour carves clearance around the new Kelvin stubs (else the
    #    stale fill shorts them -- DRC found 13 shorts without this). The fill MUST be a separate process:
    #    re-filling IN-PROCESS right after board.Remove() (rip) + board.Add() (stubs) HARD-CRASHES this
    #    KiCad-10 build (access violation in UnFill/ZONE_FILLER, size-0 board, not a catchable Python
    #    exception) -- the repo's standing "destructive edit then in-process follow-up is unreliable"
    #    lesson. A clean LoadBoard in a child re-fills fine.
    filled = _refill_subprocess(out_path)
    return {"stubs": added, "ripped_tracks": ripped, "nets": sorted(hc_nets), "refilled": filled,
            "skipped_taps": sorted(set(skipped)), "skipped_count": len(skipped),
            "needs_placement": sorted(set(skipped))}


def _fill_only(path):
    """Load a board fresh, UnFill + re-Fill every zone, save in place. Run in its OWN process."""
    board = pcbnew.LoadBoard(path)
    board.BuildConnectivity()
    for z in board.Zones():
        z.UnFill()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(path, board)


def _refill_subprocess(path):
    """Re-fill `path`'s zones in a fresh python (this file, --fill mode). True on success."""
    import subprocess
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--fill", path],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write("cec_hc re-fill failed (%s): %s\n" % (r.returncode, (r.stderr or "")[-300:]))
    return r.returncode == 0


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if argv and argv[0] == "--fill":
        _fill_only(argv[1])
        return 0
    out = argv[1] if len(argv) > 1 else argv[0].replace(".kicad_pcb", "-hc.kicad_pcb")
    import json
    result = route_high_current(argv[0], out)
    print(json.dumps(result))                                # machine-readable for the loop
    print("->", out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
