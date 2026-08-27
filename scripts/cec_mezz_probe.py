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
under the shared center-aligned dead-bug reflection. Never re-derive seats from point
clearances again.

Method:
  1. Load one recent PLACED wave board per side (anchors are seed-stable; small
     jellybean passives are soft obstacles -- the wave re-grinds them around datum).
  2. Rasterize hard/soft obstacle maps from footprint courtyards (fallback bbox).
  3. For each segment (courtyard WxH) x rotation {0,90}: legal <=> the envelope +
     margin clears every HARD obstacle on BOTH boards (shared point -> per-board
     frame via each board's center, reflected on the Hub for the dead-bug mate)
     and stays inside both outlines with edge margin.
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
PAIR_MIN_X = 18.0     # top structural pair must straddle center by this much
PAIR_X_SKEW = 12.0    # |left| vs |right| top-seat imbalance ceiling
PAIR_Y_SKEW = 8.0     # top structural pair vertical mismatch ceiling
ROW_MIN_Y = 12.0      # top/bottom support rows stay meaningfully separated

# Hard obstacles are the genuinely immovable mechanical/rail skeleton only:
# edge connectors, the ATX blade row, and the rail shunts.  U1/U2 and C1 are
# large macros but remain placeable around an authoritative stack datum;
# freezing their seed positions here would turn a placer limitation into a
# false board-size floor.  H1 is itself part of the stack datum and is derived
# after the three signal/power segments.  LEDs, debug switches and fiducials
# are likewise per-seed movers.
HARD_RE = re.compile(r"^(J\d|J[A-Z_]|TB\d|RS\d)")

# function targets per segment: per-board ANATOMY refs whose centroid defines the
# region the segment wants to be near. DETECT: hub port-1 jack J2; 24-pin R1 (the
# 2.2k DETECT code resistor). Power: hub U7; 24-pin J3 (+5V_SYS arrives
# through the J6P stack segment and is selected by U7).
TARGETS = {"J6P": {"hub": ["U7"],    "p24": ["J3"]},
           "J6C": {"hub": ["U2"],    "p24": ["U2"]},
           "J6D": {"hub": ["J2"],    "p24": ["R1"]}}


def _board_model(path):
    import pcbnew
    b = pcbnew.LoadBoard(path)
    bb = b.GetBoardEdgesBoundingBox()
    x0, y0 = bb.GetX() / 1e6, bb.GetY() / 1e6
    W, H = bb.GetWidth() / 1e6, bb.GetHeight() / 1e6
    hard, soft, pos, seg_geom, lug_geom = [], [], {}, {}, {}
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref in SEG_ENV or ref == "H1":
            # Preserve each side's REAL origin-relative courtyard at every
            # supported orientation. Header/socket origins are asymmetric;
            # a centered WxH approximation can certify two fields that KiCad
            # correctly reports as overlapping.
            old_pos = fp.GetPosition()
            old_rot = fp.GetOrientationDegrees()
            by_rot = {}
            for ang in (0, 90, 180, 270):
                fp.SetPosition(pcbnew.VECTOR2I(0, 0))
                fp.SetOrientationDegrees(float(ang))
                cb = fp.GetCourtyard(fp.GetLayer()).BBox()
                by_rot[ang] = (cb.GetX() / 1e6, cb.GetY() / 1e6,
                               (cb.GetX() + cb.GetWidth()) / 1e6,
                               (cb.GetY() + cb.GetHeight()) / 1e6)
            fp.SetPosition(old_pos)
            fp.SetOrientationDegrees(old_rot)
            if ref == "H1":
                lug_geom = by_rot
            else:
                seg_geom[ref] = by_rot
            continue                          # re-deriving these
        # H1 is a movable fourth stack support.  It is soft during the segment
        # search and is validated jointly once the new compact contract is
        # chosen; a seed-era lug position must not set the board-size floor.
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
    # The probe is also the board-size arbiter, so its mating frame is the
    # actual candidate outline.  A compiled-in nominal frame silently tested
    # stale coordinates during shrink sweeps and could approve off-board pads.
    frame_w, frame_h = W, H
    model = {"x0": x0, "y0": y0, "W": W, "H": H,
             "frame_W": frame_w, "frame_H": frame_h,
             "cx": x0 + frame_w / 2, "cy": y0 + frame_h / 2,
             "hard": hard, "soft": soft, "pos": pos,
             "seg_geom": seg_geom, "lug_geom": lug_geom, "path": path}
    # 24-PIN FORCE-RAIL REGION: the probe substrates are PLACED, UNROUTED
    # boards, so the deterministic rail corridors are invisible as copper.
    # Reconstruct them from the actual footprint-pad geometry through the SAME
    # public planner used by placement; never paste coordinate snapshots here.
    if "24pin" in os.path.basename(path) or "atx" in os.path.basename(path).lower() \
            or any(r.startswith("TB") for r in pos):
        import cec_force_rails
        rails = cec_force_rails.discover_rails(b)
        j3_ys = [q[2] for rail in rails for q in rail.get("j3", ())]
        rail_boxes = cec_force_rails.rail_placement_boxes(
            rails, max(j3_ys) if j3_ys else y0 + 8.0, alt=True,
            include_inner=True)
        # rail_placement_boxes follows the placement-box tuple convention
        # (x0, x1, y0, y1); obstacle geometry is (x0, y0, x1, y1).
        model["hard"] = hard + [(bx0, by0, bx1, by1)
                                for bx0, bx1, by0, by1 in rail_boxes]
        # SHUNT-ROW WALK BAND (seg4 forensic 2026-07-23): the rail walk's right
        # bound clamps on ANY anchor whose pad-extended box clips y in H/2+-9,
        # and the sense cells themselves span y row-7.7..row+11.5 about the
        # seeded row (H/2+1.8, measured 29.3@H55) across the walk span. J6C's
        # v3 seat (dc 11.2,12.6) landed in this band, walled the walk at
        # x~39 and crushed the column pitch 12->5.38/8.0 (the INA|shunt
        # refusal class). Segments must clear the whole band: y from the
        # planner's trigger edge (H/2-9, -1.0 guard) down to the cell TLV
        # reach (+12.1 incl. clearance), x over the walkable span.
        # y matches the planner's calibrated cell band [H/2-6.5, H/2+13.9]
        # (with a 1.0 trigger guard on the top edge). x-hi 62.0: an anchor whose
        # box starts past 62.6 (band + probe MARGIN) clamps the walk's _rb to
        # >=55.6, which still admits every J3 pin-group column target (<=~55)
        # at full pitch under the backward pull-back.
        model["hard"].append((x0 + 8.0, y0 + H / 2 - 7.5,
                              x0 + 62.0, y0 + H / 2 + 13.9))
    return model


def _board_model_multi(paths):
    """Merge N same-board substrates (comma-list): UNION of hard/soft obstacle
    boxes = the INTERSECTION of legal seat space across placements. Single-
    substrate derivation is hostage to one seed's satellite positions (the v3
    J6D hub-side lesson, 2026-07-23); requiring joint legality across several
    seeds is what makes a contract seat wave-stable. Frames must match."""
    models = [_board_model(p) for p in paths]
    base = models[0]
    for m in models[1:]:
        if abs(m["W"] - base["W"]) > 0.1 or abs(m["H"] - base["H"]) > 0.1:
            raise SystemExit(f"substrate frame mismatch: {m['path']} "
                             f"{m['W']}x{m['H']} vs {base['W']}x{base['H']}")
        base["hard"] = base["hard"] + m["hard"]
        base["soft"] = base["soft"] + m["soft"]
        # positions: keep the first substrate's (targets only need a centroid)
    base["paths"] = paths
    return base


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


def _candidates(seg, boards, assembly_dc=None):
    """All jointly-legal (dc, rot) for one segment. dc = shared-frame offset."""
    assembly_dc = assembly_dc or {}
    w0, h0 = SEG_ENV[seg]
    # Shared frame spans the OVERLAP (the smaller board's extent about the
    # center). dc is canonical on the ATX face. The populated Hub is physically
    # reflected about X when mated, so its obstacle probe coordinate uses -dx.
    # Reflection changes 0deg to 180deg but does not change the rectangular
    # envelope dimensions; a 90deg field stays 90deg.
    hw = min(b["frame_W"] for b in boards.values()) / 2 - EDGE
    hh = min(b["frame_H"] for b in boards.values()) / 2 - EDGE
    out = []
    # Grid is anchored on the assembly datum, not the negative outline edge.
    # That makes true +/-X bilateral seats and a centerline field representable
    # when the board half-width is not an integer grid multiple.
    ix0, ix1 = math.ceil(-hw / GRID), math.floor(hw / GRID)
    iy0, iy1 = math.ceil(-hh / GRID), math.floor(hh / GRID)
    for ix in range(ix0, ix1 + 1):
        dx = ix * GRID
        for iy in range(iy0, iy1 + 1):
            dy = iy * GRID
            for rot in (0, 90):
                ok, softn, dist = True, 0, 0.0
                for side, b in boards.items():
                    ax, ay = assembly_dc.get(side, (0.0, 0.0))
                    # dc is a point in the assembled-stack frame. Convert it
                    # back into each board's native coordinates about that
                    # board's own assembly-center offset. The dead-bug Hub
                    # reflects X; Y is translated but not reflected.
                    side_dx = (-(dx - ax) if side == "hub" else dx - ax)
                    side_dy = dy - ay
                    cx, cy = b["cx"] + side_dx, b["cy"] + side_dy
                    actual_rot = int((180 - rot) % 360) if side == "hub" else rot
                    geom = b.get("seg_geom", {}).get(seg, {}).get(actual_rot)
                    if geom is None:                 # old probe substrate fallback
                        w, h = (w0, h0) if rot == 0 else (h0, w0)
                        geom = (-w / 2, -h / 2, w / 2, h / 2)
                    box = (cx + geom[0], cy + geom[1],
                           cx + geom[2], cy + geom[3])
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
    return sorted(out, key=lambda c: c["score"])


def _asym(pts):
    """Min distance between the point set and its own 180-rotated image (about the
    shared center = origin of dc space). Large => visibly one-way."""
    rot = [(-x, -y) for (x, y) in pts]
    return round(min(math.hypot(a[0] - b[0], a[1] - b[1]) for a in pts for b in rot), 1)


def _balanced_support(a, b, c):
    """Require a compact but mechanically balanced four-point stack.

    J6P/J6D form the upper pair.  J6C is the lower electrical seat and H1 is
    placed at its X mirror, producing a symmetric lower pair without making
    the electrically keyed three-connector pattern 180-degree ambiguous.
    """
    px, py = a["dc"]
    cx, cy = b["dc"]
    dx, dy = c["dc"]
    if not (px <= -PAIR_MIN_X and dx >= PAIR_MIN_X):
        return False
    if not (py >= ROW_MIN_Y and dy >= ROW_MIN_Y and cy <= -ROW_MIN_Y):
        return False
    if abs(abs(px) - abs(dx)) > PAIR_X_SKEW or abs(py - dy) > PAIR_Y_SKEW:
        return False
    if abs(cx) < PAIR_MIN_X:
        return False
    return True


def derive(hub_pcb, p24_pcb, top=400, min_spread=None, asym_min=None,
           hub_assembly_dx=0.0, hub_assembly_dy=0.0):
    min_spread = MIN_SPREAD if min_spread is None else min_spread
    asym_min = ASYM_MIN if asym_min is None else asym_min
    hub_paths = str(hub_pcb).split(",")
    p24_paths = str(p24_pcb).split(",")
    boards = {"hub": _board_model_multi(hub_paths),
              "p24": _board_model_multi(p24_paths)}
    # STABILITY TIERS (2026-07-23, measured: the 74x55 24-pin's jointly-stable
    # free space holds only ONE large-segment pocket + one J6D pocket, so a
    # fully substrate-stable 3-set does not exist -- W-grow is the owner-queue
    # lever). Tier-STABLE = legal on the UNION skeleton of every substrate;
    # tier-FALLBACK = legal on the first substrate only (a per-seed-grind seat
    # whose residual conflicts the pre-route gates name). derive() prefers
    # all-stable and admits AT MOST ONE fallback member.
    assembly_dc = {"p24": (0.0, 0.0),
                   "hub": (hub_assembly_dx, hub_assembly_dy)}
    cands = {s: _candidates(s, boards, assembly_dc) for s in SEG_ENV}
    b1 = {"hub": _board_model(hub_paths[0]), "p24": _board_model(p24_paths[0])}
    cands1 = {s: _candidates(s, b1, assembly_dc) for s in SEG_ENV}
    stable_keys = {s: {(c["dc"], c["rot"]) for c in cands[s]} for s in SEG_ENV}
    for s in SEG_ENV:
        merged, seen = [], set()
        for c in cands[s] + cands1[s]:
            k = (c["dc"], c["rot"])
            if k in seen:
                continue
            seen.add(k)
            merged.append(dict(c, stable=(k in stable_keys[s])))
        cands[s] = merged
    for s, cs in cands.items():
        if not cs:
            raise SystemExit(f"NO jointly-legal seat for {s} -- widen search/relax")
    def _env_box(seg, cand, side, board):
        dx, dy = cand["dc"]
        ax, ay = assembly_dc[side]
        side_dx = (-(dx - ax) if side == "hub" else dx - ax)
        side_dy = dy - ay
        actual_rot = int((180 - cand["rot"]) % 360) if side == "hub" else cand["rot"]
        geom = board.get("seg_geom", {}).get(seg, {}).get(actual_rot)
        if geom is None:
            w0, h0 = SEG_ENV[seg]
            w, h = ((w0, h0) if cand["rot"] == 0 else (h0, w0))
            geom = (-w / 2, -h / 2, w / 2, h / 2)
        return (board["cx"] + side_dx + geom[0],
                board["cy"] + side_dy + geom[1],
                board["cx"] + side_dx + geom[2],
                board["cy"] + side_dy + geom[3])

    def _lug_box(cand, side, board):
        dx, dy = cand["dc"]
        ax, ay = assembly_dc[side]
        side_dx = (-(dx - ax) if side == "hub" else dx - ax)
        side_dy = dy - ay
        actual_rot = 180 if side == "hub" else 0
        geom = board.get("lug_geom", {}).get(actual_rot)
        if geom is None:
            geom = (-2.85, -2.85, 2.85, 2.85)
        return (board["cx"] + side_dx + geom[0],
                board["cy"] + side_dy + geom[1],
                board["cx"] + side_dx + geom[2],
                board["cy"] + side_dy + geom[3])

    best = None
    for a in cands["J6P"][:top]:
        for b in cands["J6C"][:top]:
            for c in cands["J6D"][:top]:
                pts = [a["dc"], b["dc"], c["dc"]]
                if not _balanced_support(a, b, c):
                    continue
                if min(math.hypot(p[0] - q[0], p[1] - q[1])
                       for i, p in enumerate(pts) for q in pts[i + 1:]) < min_spread:
                    continue
                # SEGMENT-vs-SEGMENT legality (2026-07-23): the old 22mm spread
                # floor masked that nothing checked the segments against EACH
                # OTHER -- at lower spreads the "best" sets physically overlap.
                seat_set = (("J6P", a), ("J6C", b), ("J6D", c))
                if any(any(not _clear(boxes[i], boxes[i + 1:], MARGIN)
                           for i in range(2))
                       for side, board in boards.items()
                       for boxes in [[_env_box(s, c2, side, board)
                                      for s, c2 in seat_set]]):
                    continue
                # H1 mirrors J6C across the assembly center.  Validate its
                # real plated-land courtyard against both boards' immutable
                # skeleton and all three new connector courtyards.
                lug = {"dc": (-b["dc"][0], b["dc"][1]), "rot": 0}
                lug_soft = 0
                lug_ok = True
                for side, board in boards.items():
                    lb = _lug_box(lug, side, board)
                    if (lb[0] < board["x0"] + EDGE
                            or lb[2] > board["x0"] + board["W"] - EDGE
                            or lb[1] < board["y0"] + EDGE
                            or lb[3] > board["y0"] + board["H"] - EDGE
                            or not _clear(lb, board["hard"], MARGIN)):
                        lug_ok = False
                        break
                    seg_boxes = [_env_box(s, c2, side, board)
                                 for s, c2 in seat_set]
                    if not _clear(lb, seg_boxes, MARGIN):
                        lug_ok = False
                        break
                    lug_soft += _soft_pressure(lb, board["soft"])
                if not lug_ok:
                    continue
                asym = _asym(pts)
                if asym < asym_min:
                    continue
                n_stable = sum(1 for c2 in (a, b, c) if c2.get("stable"))
                if n_stable < 2:
                    continue                      # at most ONE fallback member
                balance = abs(abs(a["dc"][0]) - abs(c["dc"][0])) \
                    + abs(a["dc"][1] - c["dc"][1])
                score = (a["score"] + b["score"] + c["score"]
                         + 3.0 * lug_soft + 2.0 * balance - 0.5 * asym)
                key = (-n_stable, score)
                if best is None or key < best["key"]:
                    best = {"key": key, "score": round(score, 1), "asym": asym,
                            "balance_penalty": round(balance, 1),
                            "n_stable": n_stable, "J6P": a, "J6C": b,
                            "J6D": c, "H1": dict(lug, soft=lug_soft)}
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
    ap.add_argument("--top", type=int, default=120,
                    help="maximum scored candidates per segment considered by the joint set solver")
    ap.add_argument("--hub-assembly-dx", type=float, default=0.0,
                    help="Hub assembly-center X offset from the ATX center (mm); "
                         "native Hub X is reflected about this offset")
    ap.add_argument("--hub-assembly-dy", type=float, default=0.0,
                    help="Hub assembly-center Y offset from the ATX center (mm)")
    a = ap.parse_args()
    best, top5, boards = derive(a.hub, a.p24, top=a.top,
                                min_spread=a.min_spread,
                                asym_min=a.asym_min,
                                hub_assembly_dx=a.hub_assembly_dx,
                                hub_assembly_dy=a.hub_assembly_dy)
    rep = {"probe_boards": {k: b["path"] for k, b in boards.items()},
           "assembly_dc": {"p24": [0.0, 0.0],
                           "hub": [a.hub_assembly_dx, a.hub_assembly_dy]},
           "chosen": best, "per_segment_top5": top5,
           "board_frames": {k: {"outline_W": b["W"], "outline_H": b["H"],
                                "nominal_W": b["frame_W"],
                                "nominal_H": b["frame_H"]}
                            for k, b in boards.items()}}
    print(json.dumps(rep, indent=1))
    if a.json:
        json.dump(rep, open(a.json, "w"), indent=1)
    print("\nCONTRACT BLOCK:")
    for s in ("J6P", "J6C", "J6D"):
        c = best[s]
        print(f'        {{"ref": "{s}", "dc": {c["dc"]}, "rot": {c["rot"]}}},'
              f'   # target_dist {c["target_dist"]} soft {c["soft"]}')
    print(f'GROUND_LUG dc={best["H1"]["dc"]} soft={best["H1"]["soft"]}')
    print(f'# pattern asymmetry (min self-vs-180-image distance): {best["asym"]}mm')


if __name__ == "__main__":
    main()
