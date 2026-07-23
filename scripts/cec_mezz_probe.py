#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""cec_mezz_probe -- joint-legality seat derivation for the structural mezz segments.

Owner directives (2026-07-23): the three segments sit NEAR the circuitry whose nets
they carry (power by power entry, comms by the CAN side, ID by the detect side), the
PATTERN is asymmetric so the stack only assembles one way intentionally, and segments
may ROTATE (0/90 envelope) to fill whatever space is available.

The 2026-07-22 lesson this tool encodes (FOLLOWUPS): seat legality is PART-SIZE
dependent -- the probe models each segment's REAL courtyard envelope (from its
vendored footprint) at every candidate (position x rotation), jointly on BOTH boards
under the shared center-aligned no-flip frame. Never re-derive seats from point
clearances again.

Method:
  1. Load one recent PLACED wave board per side (anchors are seed-stable; small
     jellybean passives are soft obstacles -- the wave re-grinds them around datum).
  2. Rasterize hard/soft obstacle maps from footprint courtyards (fallback bbox).
  3. For each segment (courtyard WxH) x rotation {0,90}: legal <=> the envelope +
     margin clears every HARD obstacle on BOTH boards (shared point -> per-board
     frame via each board's center) and stays inside both outlines with edge margin.
  4. Score = joint distance to the segment's FUNCTION targets (per-board anatomy
     refs, read from the boards) + soft-obstacle pressure; pick the best seat set
     subject to MIN PAIRWISE SPREAD (stability) and ASYMMETRY (the 180-degree-
     rotated pattern must not land near the original -- intentional insertion).
  5. Emit the chosen contract block + the full report (JSON).

Run in the routing container (pcbnew):
    python3 scripts/cec_mezz_probe.py --hub <placed.kicad_pcb> --p24 <placed.kicad_pcb>
"""
import argparse
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

# segment courtyard envelopes (mm), measured from the vendored footprints'
# CrtYd (2.54 pitch, 0.25 courtyard margin per KLC): 2-row width 7.62, length
# (n_cols-1)*2.54 + 5.08. Verified against the .kicad_mod files at vendor time.
SEG_ENV = {"J6P": (7.62, 10.16),   # 2x3
           "J6C": (7.62, 12.70),   # 2x4
           "J6D": (7.62, 7.62)}    # 2x2
MARGIN = 0.6          # clearance beyond courtyard vs hard obstacles (mm)
EDGE = 1.2            # min courtyard-to-outline margin
GRID = 1.0            # candidate grid pitch (mm)
MIN_SPREAD = 22.0     # min pairwise segment distance (stability triangle width)
ASYM_MIN = 8.0        # min distance pattern<->its own 180-rotated image (keying)

# hard-obstacle refs: the seed-stable anchors + macro parts. Everything else is a
# SOFT obstacle (jellybeans the wave re-seats around datum pins).
HARD_RE = re.compile(r"^(J\d|J[A-Z_]|TB\d|U1$|U2$|C1$|DL\d|SW|H\d|FID|RS\d|F\d)")

# function targets per segment: per-board ANATOMY refs whose centroid defines the
# region the segment wants to be near. DETECT: hub port-1 jack J2; 24-pin R1 (the
# 2.2k DETECT code resistor). Power: hub J_PWR; 24-pin J3 (5VSB arrives there).
TARGETS = {"J6P": {"hub": ["J_PWR"], "p24": ["J3"]},
           "J6C": {"hub": ["U2"],    "p24": ["U2"]},
           "J6D": {"hub": ["J2"],    "p24": ["R1"]}}


def _board_model(path):
    import pcbnew
    b = pcbnew.LoadBoard(path)
    bb = b.GetBoardEdgesBoundingBox()
    x0, y0 = bb.GetX() / 1e6, bb.GetY() / 1e6
    W, H = bb.GetWidth() / 1e6, bb.GetHeight() / 1e6
    hard, soft, pos = [], [], {}
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref in SEG_ENV or ref == "H1":
            continue                          # re-deriving these
        r = fp.GetCourtyard(fp.GetLayer())    # SHAPE_POLY_SET; may be empty
        try:
            cb = r.BBox()
            box = (cb.GetX() / 1e6, cb.GetY() / 1e6,
                   (cb.GetX() + cb.GetWidth()) / 1e6, (cb.GetY() + cb.GetHeight()) / 1e6)
            if cb.GetWidth() == 0:
                raise ValueError
        except Exception:                     # noqa: BLE001 -- fallback: fp bbox
            fb = fp.GetBoundingBox()
            box = (fb.GetX() / 1e6, fb.GetY() / 1e6,
                   (fb.GetX() + fb.GetWidth()) / 1e6, (fb.GetY() + fb.GetHeight()) / 1e6)
        (hard if HARD_RE.match(ref) else soft).append(box)
        p = fp.GetPosition()
        pos[ref] = (p.x / 1e6, p.y / 1e6)
    model = {"x0": x0, "y0": y0, "W": W, "H": H, "cx": x0 + W / 2, "cy": y0 + H / 2,
             "hard": hard, "soft": soft, "pos": pos, "path": path}
    # 24-PIN FORCE-RAIL LANE REGION (2026-07-23): the probe substrates are PLACED,
    # UNROUTED boards, so the rail corridors (laid at materialize, reserved by
    # _force_rail_boxes) are invisible as footprints -- without this, the probe
    # happily seats a segment mid-lane where the 5V/12V spines run (the RS3-class
    # collider). Conservative DRAFT box = the Option-A lane span (x0+5..x0+39,
    # full height); a rail-plan-derived precise set is the refinement rung.
    if "24pin" in os.path.basename(path) or "atx" in os.path.basename(path).lower() \
            or any(r.startswith("TB") for r in pos):
        model["hard"] = hard + [(x0 + 5.0, y0, x0 + 39.0, y0 + H)]
    return model


def _clear(box, obstacles, m):
    ax0, ay0, ax1, ay1 = box
    for (bx0, by0, bx1, by1) in obstacles:
        if ax0 - m < bx1 and ax1 + m > bx0 and ay0 - m < by1 and ay1 + m > by0:
            return False
    return True


def _soft_pressure(box, obstacles):
    n = 0
    ax0, ay0, ax1, ay1 = box
    for (bx0, by0, bx1, by1) in obstacles:
        if ax0 < bx1 and ax1 > bx0 and ay0 < by1 and ay1 > by0:
            n += 1
    return n


def _candidates(seg, boards):
    """All jointly-legal (dc, rot) for one segment. dc = shared-frame offset."""
    w0, h0 = SEG_ENV[seg]
    # shared frame spans the OVERLAP (the smaller board's extent about the center)
    hw = min(b["W"] for b in boards.values()) / 2 - EDGE
    hh = min(b["H"] for b in boards.values()) / 2 - EDGE
    out = []
    dx = -hw
    while dx <= hw:
        dy = -hh
        while dy <= hh:
            for rot in (0, 90):
                w, h = (w0, h0) if rot == 0 else (h0, w0)
                ok, softn, dist = True, 0, 0.0
                for side, b in boards.items():
                    cx, cy = b["cx"] + dx, b["cy"] + dy
                    box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
                    if (box[0] < b["x0"] + EDGE or box[2] > b["x0"] + b["W"] - EDGE
                            or box[1] < b["y0"] + EDGE or box[3] > b["y0"] + b["H"] - EDGE
                            or not _clear(box, b["hard"], MARGIN)):
                        ok = False
                        break
                    softn += _soft_pressure(box, b["soft"])
                    tp = [b["pos"][r] for r in TARGETS[seg][side] if r in b["pos"]]
                    if tp:
                        tx = sum(p[0] for p in tp) / len(tp)
                        ty = sum(p[1] for p in tp) / len(tp)
                        dist += math.hypot(cx - tx, cy - ty)
                if ok:
                    out.append({"dc": (round(dx, 1), round(dy, 1)), "rot": rot,
                                "score": round(dist + 3.0 * softn, 2),
                                "soft": softn, "target_dist": round(dist, 1)})
            dy += GRID
        dx += GRID
    return sorted(out, key=lambda c: c["score"])


def _asym(pts):
    """Min distance between the point set and its own 180-rotated image (about the
    shared center = origin of dc space). Large => visibly one-way."""
    rot = [(-x, -y) for (x, y) in pts]
    return round(min(math.hypot(a[0] - b[0], a[1] - b[1]) for a in pts for b in rot), 1)


def derive(hub_pcb, p24_pcb, top=400, min_spread=None, asym_min=None):
    min_spread = MIN_SPREAD if min_spread is None else min_spread
    asym_min = ASYM_MIN if asym_min is None else asym_min
    boards = {"hub": _board_model(hub_pcb), "p24": _board_model(p24_pcb)}
    cands = {s: _candidates(s, boards) for s in SEG_ENV}
    for s, cs in cands.items():
        if not cs:
            raise SystemExit(f"NO jointly-legal seat for {s} -- widen search/relax")
    best = None
    for a in cands["J6P"][:top]:
        for b in cands["J6C"][:top]:
            for c in cands["J6D"][:top]:
                pts = [a["dc"], b["dc"], c["dc"]]
                if min(math.hypot(p[0] - q[0], p[1] - q[1])
                       for i, p in enumerate(pts) for q in pts[i + 1:]) < min_spread:
                    continue
                asym = _asym(pts)
                if asym < asym_min:
                    continue
                score = a["score"] + b["score"] + c["score"] - 0.5 * asym
                if best is None or score < best["score"]:
                    best = {"score": round(score, 1), "asym": asym,
                            "J6P": a, "J6C": b, "J6D": c}
    if best is None:
        raise SystemExit("no seat SET satisfies spread+asymmetry -- relax knobs")
    return best, {s: cs[:5] for s, cs in cands.items()}, boards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hub", required=True)
    ap.add_argument("--p24", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--min-spread", type=float, default=MIN_SPREAD,
                    help="min pairwise segment distance; the R2 M2 vertex (H1) "
                         "carries the polygon width when this relaxes")
    ap.add_argument("--asym-min", type=float, default=ASYM_MIN)
    a = ap.parse_args()
    best, top5, boards = derive(a.hub, a.p24, min_spread=a.min_spread,
                                asym_min=a.asym_min)
    rep = {"probe_boards": {k: b["path"] for k, b in boards.items()},
           "chosen": best, "per_segment_top5": top5,
           "board_frames": {k: {"W": b["W"], "H": b["H"]} for k, b in boards.items()}}
    print(json.dumps(rep, indent=1))
    if a.json:
        json.dump(rep, open(a.json, "w"), indent=1)
    print("\nCONTRACT BLOCK:")
    for s in ("J6P", "J6C", "J6D"):
        c = best[s]
        print(f'        {{"ref": "{s}", "dc": {c["dc"]}, "rot": {c["rot"]}}},'
              f'   # target_dist {c["target_dist"]} soft {c["soft"]}')
    print(f'# pattern asymmetry (min self-vs-180-image distance): {best["asym"]}mm')


if __name__ == "__main__":
    main()
