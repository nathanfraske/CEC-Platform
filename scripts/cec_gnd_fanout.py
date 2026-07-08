#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
cec_gnd_fanout -- per-GND-pin via fanout (owner rule, 2026-07-08 evening).

"Each grounding pin should be wired to its own grounding via if possible for maximum
impedance margin. Biggest one is on the MCU." + the refinement: "but ONLY if it reduces
the impedance to ground."

So this is NOT a blind per-pin via stamper. For every SMD GND pad the synthesizer
measures d_now = the distance to its nearest EXISTING ground-plane entry (a GND via or a
GND THT barrel -- both connect to the inner plane), and places a new adjacent via ONLY
when it strictly improves that path:  d_new < min(improve_frac * d_now, d_now - min_gain).
A pad already sitting on a plane entry is left alone (a second via there buys nothing);
a pad SHARING its nearest via with closer pads still gains (its own barrel + shorter
stub). Placement is legality-guarded against ALL foreign copper (pads/tracks/vias, every
crossed layer) + the board edge, worst-pads-first, MCU (ESP32*) pads get priority within
equal distance. Calibration context (build/probe_gnd_vias.py, 2026-07-08): hand hub is
71% dedicated / 1 orphan; hand 12vhpwr tolerates 30 pads past 2.5mm -- hand boards
DISAGREE, so the checker half stays ADVISORY (a distribution report), and the rule's
teeth live in the synthesizer's before/after delta + the DRC guard.

Standalone by design (2026-07-08: wave 12 was mid-run and code-frozen) -- the route
recipe wires it in AFTER the wave completes: synthesize(board) between pour synthesis
and the final fill/DRC.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MM = 1_000_000


def _gnd_entries(board):
    """Existing ground-plane entry points: GND vias + GND THT pad barrels."""
    pts = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND":
            pts.append((t.GetPosition().x / MM, t.GetPosition().y / MM))
    import pcbnew
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == "GND" and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                pts.append((p.GetPosition().x / MM, p.GetPosition().y / MM))
    return pts


def _nearest(pts, x, y):
    d = 1e9
    for px, py in pts:
        d = min(d, math.hypot(px - x, py - y))
    return d


def audit(board_path, *, reach=2.5, board=None):
    """ADVISORY distribution report: per-SMD-GND-pad distance to the nearest plane
    entry, orphan list (d_now > reach), MCU detail. Never a gate (hand boards disagree
    on the tolerable ceiling -- see module docstring)."""
    import pcbnew
    b = board or pcbnew.LoadBoard(board_path)
    entries = _gnd_entries(b)
    rows = []
    for fp in b.GetFootprints():
        is_mcu = "ESP32" in (fp.GetValue() or "").upper()
        for p in fp.Pads():
            if p.GetNetname() != "GND" or p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                continue
            x, y = p.GetPosition().x / MM, p.GetPosition().y / MM
            rows.append({"ref": f"{fp.GetReference()}.{p.GetPadName()}", "mcu": is_mcu,
                         "d_now": round(_nearest(entries, x, y), 2)})
    if not rows:
        return {"ok": True, "n": 0, "note": "no SMD GND pads -- N/A"}
    ds = sorted(r["d_now"] for r in rows)
    orph = [r for r in rows if r["d_now"] > reach]
    mcu = [r for r in rows if r["mcu"]]
    return {"ok": True, "n": len(rows),
            "med": ds[len(ds) // 2], "p90": ds[int(0.9 * (len(ds) - 1))],
            "orphans": len(orph), "orphan_refs": [r["ref"] for r in orph][:10],
            "mcu_pads": len(mcu),
            "mcu_worst": max((r["d_now"] for r in mcu), default=None)}


def _foreign_obstacles(board):
    """(x0,x1,y0,y1) inflatable boxes of every FOREIGN-net copper item + all existing
    vias/THT barrels (same-net too: never overlap barrels), plus track segments."""
    import pcbnew
    boxes, segs = [], []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            box = (bb.GetLeft() / MM, bb.GetRight() / MM, bb.GetTop() / MM, bb.GetBottom() / MM)
            if p.GetNetname() != "GND" or p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                boxes.append(box)
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            bb = t.GetBoundingBox()
            boxes.append((bb.GetLeft() / MM, bb.GetRight() / MM, bb.GetTop() / MM, bb.GetBottom() / MM))
        elif t.GetNetname() != "GND":
            segs.append((t.GetStart().x / MM, t.GetStart().y / MM,
                         t.GetEnd().x / MM, t.GetEnd().y / MM, t.GetWidth() / MM / 2.0))
    return boxes, segs


def _pt_seg_d(px, py, x0, y0, x1, y1):
    vx, vy = x1 - x0, y1 - y0
    wx, wy = px - x0, py - y0
    L = vx * vx + vy * vy
    t = 0.0 if L == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / L))
    return math.hypot(px - (x0 + t * vx), py - (y0 + t * vy))


def _foreign_zone_fills(board):
    """Filled polygons of every FOREIGN-net copper zone (the wave boards carry rail
    FACE POURS -- the first teeth run measured +18 DRC from vias landing inside them)."""
    import pcbnew
    fills = []
    for z in board.Zones():
        if z.GetNetname() == "GND" or not z.IsOnCopperLayer():
            continue
        for lid in z.GetLayerSet().CuStack():
            try:
                poly = z.GetFilledPolysList(lid)
                if poly and poly.OutlineCount() > 0:
                    fills.append(poly)
            except Exception:                            # noqa: BLE001
                pass
    return fills


def _seg_seg_d(a0, a1, b0, b1):
    """Min distance between two segments (0 when they cross) -- the stub must be checked
    along its WHOLE length: a foreign track touching it anywhere gets the new copper
    silently RE-NETTED by KiCad connectivity on save/load (recorded repo footgun; the
    first teeth run produced a /THRESH-netted 'GND' via exactly this way)."""
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2 = cross(b0, b1, a0), cross(b0, b1, a1)
    d3, d4 = cross(a0, a1, b0), cross(a0, a1, b1)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(_pt_seg_d(a0[0], a0[1], b0[0], b0[1], b1[0], b1[1]),
               _pt_seg_d(a1[0], a1[1], b0[0], b0[1], b1[0], b1[1]),
               _pt_seg_d(b0[0], b0[1], a0[0], a0[1], a1[0], a1[1]),
               _pt_seg_d(b1[0], b1[1], a0[0], a0[1], a1[0], a1[1]))


def _stub_legal(x, y, cx, cy, stub_half, boxes, segs, zone_fills, clearance):
    """The pad->via stub as a CAPSULE: exact seg-seg clearance vs every foreign track,
    sampled clearance vs pad boxes + foreign zone fills along the whole run."""
    import pcbnew
    for sx0, sy0, sx1, sy1, half in segs:
        if _seg_seg_d((x, y), (cx, cy), (sx0, sy0), (sx1, sy1)) < half + stub_half + clearance:
            return False
    L = max(1e-6, math.hypot(cx - x, cy - y))
    n = max(2, int(L / 0.2))
    for i in range(n + 1):
        t = i / n
        px, py = x + (cx - x) * t, y + (cy - y) * t
        r = stub_half + clearance
        for bl, br, bt, bb in boxes:
            if bl - r <= px <= br + r and bt - r <= py <= bb + r:
                return False
        pt = pcbnew.VECTOR2I(int(px * MM), int(py * MM))
        for poly in zone_fills:
            if poly.Collide(pt, int(r * MM)):
                return False
    return True


def _spot_legal(x, y, r_need, boxes, segs, edge, zone_fills=()):
    import pcbnew
    x0, y0, x1, y1 = edge
    if not (x0 + r_need <= x <= x1 - r_need and y0 + r_need <= y <= y1 - r_need):
        return False
    for bl, br, bt, bb in boxes:
        if bl - r_need <= x <= br + r_need and bt - r_need <= y <= bb + r_need:
            return False
    for sx0, sy0, sx1, sy1, half in segs:
        if _pt_seg_d(x, y, sx0, sy0, sx1, sy1) < half + r_need:
            return False
    pt = pcbnew.VECTOR2I(int(x * MM), int(y * MM))
    for poly in zone_fills:
        if poly.Collide(pt, int(r_need * MM)):
            return False
    return True


def synthesize(board_path, out_path=None, *, dia=0.6, drill=0.3, clearance=0.25,
               improve_frac=0.6, min_gain=0.5, skip_below=0.8, max_stub=1.8,
               verbose=False):
    """Place ONE dedicated GND via next to each SMD GND pad WHERE IT REDUCES THE
    IMPEDANCE TO GROUND (owner refinement): a via is added only if the best legal spot
    gives d_new < min(improve_frac*d_now, d_now - min_gain), and pads with
    d_now <= skip_below are left alone. Worst-first, MCU pads tie-broken first.
    Returns the report dict; writes out_path (default: in place) only if vias landed."""
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    gnd = b.FindNet("GND")
    if gnd is None:
        return {"added": 0, "note": "no GND net"}
    bb = b.GetBoardEdgesBoundingBox()
    x0e, y0e, x1e, y1e = bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetRight() / MM, bb.GetBottom() / MM
    entries = _gnd_entries(b)
    boxes, segs = _foreign_obstacles(b)
    zone_fills = _foreign_zone_fills(b)
    r_via = dia / 2.0
    r_need = r_via + clearance
    # candidates: worst d_now first; MCU pads first within ~equal distance (owner: the
    # biggest one is on the MCU)
    pads = []
    for fp in b.GetFootprints():
        is_mcu = "ESP32" in (fp.GetValue() or "").upper()
        for p in fp.Pads():
            if p.GetNetname() != "GND" or p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                continue
            x, y = p.GetPosition().x / MM, p.GetPosition().y / MM
            d_now = _nearest(entries, x, y)
            if d_now <= skip_below:
                continue                     # already at a plane entry -- no impedance win
            pads.append((round(d_now, 3), 0 if is_mcu else 1,
                         f"{fp.GetReference()}.{p.GetPadName()}", p, x, y))
    pads.sort(key=lambda t: (-t[0], t[1]))
    added, skipped = [], []
    for d_now, _mcu_rank, ref, p, x, y in pads:
        pb = p.GetBoundingBox()
        hw, hh = pb.GetWidth() / MM / 2.0, pb.GetHeight() / MM / 2.0
        best = None
        for ring in (0.0, 0.3, 0.6, 1.0):
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1)):
                n = math.hypot(dx, dy)
                ux, uy = dx / n, dy / n
                off_x = (hw + r_via + clearance + ring)
                off_y = (hh + r_via + clearance + ring)
                cx, cy = x + ux * off_x, y + uy * off_y
                d_new = math.hypot(cx - x, cy - y)
                if d_new > max_stub or d_new >= min(improve_frac * d_now, d_now - min_gain):
                    continue
                if not (x0e + r_need + 0.3 <= cx <= x1e - r_need - 0.3
                        and y0e + r_need + 0.3 <= cy <= y1e - r_need - 0.3):
                    continue
                own = (pb.GetLeft() / MM, pb.GetRight() / MM, pb.GetTop() / MM, pb.GetBottom() / MM)
                stub_boxes = [bx for bx in boxes if bx != own]
                if _spot_legal(cx, cy, r_need, boxes, segs, (x0e, y0e, x1e, y1e), zone_fills) \
                        and _stub_legal(x, y, cx, cy, 0.125, stub_boxes, segs, zone_fills,
                                        clearance) \
                        and (best is None or d_new < best[0]):
                    best = (d_new, cx, cy)
            if best is not None:
                break                          # closest ring wins; no need to widen
        if best is None:
            skipped.append((ref, d_now, "no legal improving spot"))
            continue
        d_new, cx, cy = best
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(int(cx * MM), int(cy * MM)))
        v.SetDrill(int(drill * MM))
        v.SetWidth(int(dia * MM))
        v.SetNetCode(gnd.GetNetCode())
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        b.Add(v)
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(int(x * MM), int(y * MM)))
        t.SetEnd(pcbnew.VECTOR2I(int(cx * MM), int(cy * MM)))
        t.SetWidth(int(0.25 * MM))
        t.SetLayer(p.GetLayer())
        t.SetNetCode(gnd.GetNetCode())
        b.Add(t)
        # the new via is an entry for every LATER pad (a neighbor may no longer need one
        # -- exactly the "only if it reduces impedance" rule compounding)
        entries.append((cx, cy))
        boxes.append((cx - r_via, cx + r_via, cy - r_via, cy + r_via))
        added.append((ref, round(d_now, 2), round(d_new, 2)))
        if verbose:
            print(f"  + {ref}: d {d_now:.2f} -> {d_new:.2f}mm at ({cx:.2f},{cy:.2f})")
    if added:
        b.Save(out_path or board_path)
    return {"added": len(added), "adds": added[:20], "skipped": len(skipped),
            "skip_detail": skipped[:8],
            "out": (out_path or board_path) if added else None}


def main():
    import argparse
    import json
    ap = argparse.ArgumentParser(description="per-GND-pin via fanout (impedance-reducing only)")
    ap.add_argument("board")
    ap.add_argument("--out", default=None)
    ap.add_argument("--audit-only", action="store_true")
    a = ap.parse_args()
    print(json.dumps(audit(a.board), indent=1))
    if not a.audit_only:
        rep = synthesize(a.board, a.out, verbose=True)
        print(json.dumps({k: v for k, v in rep.items() if k != "adds"}, indent=1))
        print(json.dumps(audit(a.out or a.board), indent=1))


if __name__ == "__main__":
    main()
