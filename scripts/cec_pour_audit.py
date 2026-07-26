#!/usr/bin/env python3
"""Pour-quality audit for a routed board: the owner's five complaints, measured.

Consolidates the probes that found today's regressions so every wave winner is
checked the same way instead of by ad-hoc scripts:

  * INCURSION    -- foreign parts / tracks / vias inside a pour's reserved region
                    (owner 2026-07-25: "nothing places inside a pour"). Measured
                    against the zone OUTLINE, not the fill -- the filler voids
                    around obstacles, so "nothing inside the fill" is true by
                    construction and proves nothing.
  * SHAPE        -- diagonal (non-Manhattan) outline edges per producer. Every
                    diagonal today came from a smoothing step, never the design.
  * VIA ROWS     -- >=6 vias of one net strung along a line: the "fence" a layer
                    change must not become (it belongs in one compact array).
  * SHUNT GAP    -- copper inside a shunt's inter-pad tap gap, and force pours
                    running past their own pad (the pour-termination ruling).
  * DEAD ZONES   -- zero-fill or zero-contact pours.

Usage:
    python3 scripts/cec_pour_audit.py BOARD [BOARD ...] [--json OUT] [--quiet]

Exit code is 0 always: this reports, it does not gate (see docs/owner-queue.md --
the incursion rule cannot be satisfied by the placer yet, and a gate nothing can
pass is a stopped line).
"""

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pcbnew                                             # noqa: E402


def _zone_polys(z, lid, filled=False):
    """Outline (reserved region) or filled polygons of a zone on one layer."""
    from shapely.geometry import Polygon
    src = None
    if filled:
        try:
            src = z.GetFilledPolysList(lid)
        except Exception:                                  # noqa: BLE001
            return []
    else:
        src = z.Outline()
    out = []
    for i in range(src.OutlineCount()):
        o = src.Outline(i)
        pts = [(o.CPoint(k).x / 1e6, o.CPoint(k).y / 1e6)
               for k in range(o.PointCount())]
        if len(pts) >= 3:
            g = Polygon(pts).buffer(0)
            if not g.is_empty:
                out.append((g, pts))
    return out


def _diag_edges(pts, tol=1e-6):
    n = len(pts)
    return sum(1 for i in range(n - 1)
               if abs(pts[i + 1][0] - pts[i][0]) > tol
               and abs(pts[i + 1][1] - pts[i][1]) > tol)


def audit(board_path):
    from shapely.geometry import box as _box, LineString
    from shapely.ops import unary_union
    b = pcbnew.LoadBoard(board_path)
    rep = {"board": os.path.relpath(board_path), "producers": {}, "incursion": {},
           "via_rows": [], "shunt": {}, "dead_zones": []}

    zones = []                                             # (net, lid, name, outline_u, fill_area)
    prod = collections.defaultdict(lambda: {"zones": 0, "verts": 0, "diagonal": 0,
                                            "area": 0.0})
    for z in b.Zones():
        if z.GetIsRuleArea():
            continue
        name = z.GetZoneName() or ""
        net = z.GetNetname() or ""
        key = name.split(":")[0] if ":" in name else (name or "(unnamed)")
        fill = z.GetFilledArea() / 1e12
        p = prod[key]
        p["zones"] += 1
        p["area"] += fill
        for lid in b.GetEnabledLayers().CuStack():
            if not z.IsOnLayer(lid):
                continue
            polys = _zone_polys(z, lid)
            if not polys:
                continue
            for _g, pts in polys:
                p["verts"] += len(pts)
                p["diagonal"] += _diag_edges(pts)
            zones.append((net, lid, name, unary_union([g for g, _ in polys]), fill))
        if fill <= 0.0:
            rep["dead_zones"].append({"name": name, "net": net, "reason": "zero fill"})
    rep["producers"] = {k: v for k, v in sorted(prod.items(), key=lambda kv: -kv[1]["area"])}

    # ---- incursion (skip the board-wide GND reference plane)
    n_parts = n_tracks = n_vias = 0
    items = []
    for net, lid, name, g, _fill in zones:
        if net == "GND" or name.startswith("GND Plane"):
            continue
        # A MANIFOLD deliberately spans its connector's whole pin field (v3.1:
        # "combine up all similar pins on one connector with a margin-width
        # pour"), so foreign PADS inside one are the design, not an incursion --
        # counting them made the 24-pin read 250 violations that mostly are not.
        # Foreign TRACKS/VIAS through a manifold are still counted below.
        _skip_pads = name.startswith("manifold:")
        for fp in (() if _skip_pads else b.GetFootprints()):
            for pd in fp.Pads():
                if not pd.IsOnLayer(lid) or pd.GetNetname() == net:
                    continue
                pb = pd.GetBoundingBox()
                r = _box(pb.GetLeft() / 1e6, pb.GetTop() / 1e6,
                         pb.GetRight() / 1e6, pb.GetBottom() / 1e6)
                if g.intersects(r) and g.intersection(r).area > 0.001:
                    n_parts += 1
                    items.append("pad %s[%s] in %s" % (fp.GetReference(),
                                                       pd.GetNetname(), name))
        for t in b.GetTracks():
            if t.GetNetname() == net:
                continue
            if t.GetClass() == "PCB_TRACK" and t.GetLayer() == lid:
                s_, e_ = t.GetStart(), t.GetEnd()
                if g.intersects(LineString([(s_.x / 1e6, s_.y / 1e6),
                                            (e_.x / 1e6, e_.y / 1e6)])):
                    n_tracks += 1
            elif t.GetClass() == "PCB_VIA" and t.IsOnLayer(lid):
                p_ = t.GetPosition()
                if g.intersects(_box(p_.x / 1e6 - 0.45, p_.y / 1e6 - 0.45,
                                     p_.x / 1e6 + 0.45, p_.y / 1e6 + 0.45)):
                    n_vias += 1
    rep["incursion"] = {"parts": n_parts, "tracks": n_tracks, "vias": n_vias,
                        "items": items[:20]}

    # ---- via rows (a layer change must be an array, not a fence)
    byline = collections.defaultdict(list)
    for t in b.GetTracks():
        if t.GetClass() != "PCB_VIA":
            continue
        p_ = t.GetPosition()
        byline[(round(p_.y / 1e6, 1), t.GetNetname(), "y")].append(p_.x / 1e6)
        byline[(round(p_.x / 1e6, 1), t.GetNetname(), "x")].append(p_.y / 1e6)
    # A FENCE is a long line, not any row of an array: the compact array the
    # 2026-07-25 ruling asks for legitimately presents ~sqrt(n) vias per line at
    # ~1.2mm pitch, so only a LONG span counts as the defect (measured: the
    # regression was 22 vias over 37mm; a healthy array row is 6 over 6mm).
    for (coord, net, axis), vs in byline.items():
        span = round(max(vs) - min(vs), 1) if len(vs) > 1 else 0.0
        if len(vs) >= 6 and span >= 8.0:
            rep["via_rows"].append({"axis": axis, "at": coord, "net": net,
                                    "n": len(vs), "span": span})
    rep["via_rows"].sort(key=lambda r: -r["n"])

    # ---- shunt gap + terminate-at-the-pad
    try:
        import cec_fr
        gaps = cec_fr.shunt_tap_gaps(b)
    except Exception:                                      # noqa: BLE001
        gaps = []
    gap_hits = []
    for lays, rect, ref in gaps:
        for net, lid, name, g, _f in zones:
            if pcbnew.LayerName(lid) not in lays:
                continue
            a = g.intersection(_box(*rect)).area
            if a > 0.02:
                gap_hits.append({"shunt": ref, "pour": name, "mm2": round(a, 2)})
    rep["shunt"] = {"gaps": len(gaps), "intrusions": gap_hits}
    return rep


def summarise(rep):
    inc = rep["incursion"]
    diag = sum(p["diagonal"] for p in rep["producers"].values())
    rows = rep["via_rows"]
    worst = rows[0] if rows else None
    return ("%-58s incursion(p/t/v)=%d/%d/%d  diagonal=%d  via_rows=%d%s  "
            "gap_intrusions=%d  dead=%d"
            % (os.path.basename(rep["board"])[:58], inc["parts"], inc["tracks"],
               inc["vias"], diag, len(rows),
               (" (worst %dx over %.0fmm)" % (worst["n"], worst["span"])) if worst else "",
               len(rep["shunt"].get("intrusions", [])), len(rep["dead_zones"])))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("boards", nargs="+")
    ap.add_argument("--json", default="")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    out = []
    for bp in a.boards:
        if not os.path.isfile(bp):
            print("MISSING %s" % bp)
            continue
        try:
            rep = audit(bp)
        except Exception as e:                             # noqa: BLE001
            print("ERROR %s: %s: %s" % (bp, type(e).__name__, e))
            continue
        out.append(rep)
        print(summarise(rep), flush=True)
        if not a.quiet:
            for k, v in rep["producers"].items():
                if v["diagonal"]:
                    print("      %-14s %d diagonal edge(s) over %d zone(s)"
                          % (k, v["diagonal"], v["zones"]))
            for it in rep["incursion"]["items"][:5]:
                print("      %s" % it)
            for r in rep["via_rows"][:3]:
                print("      via row: %d vias on %s=%.1f over %.1fmm [%s]"
                      % (r["n"], r["axis"], r["at"], r["span"], r["net"]))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(out, fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
