"""Planted-defect battery for the deterministic render-diff pre-pass (owner ruling 2026-06-11).

Builds the battery to the head-two dive's spec: plant each defect class on a copy of a
known-good reference board, render the MODEL-FREE copper, diff vs the reference render, and record
whether the pre-pass catches it (a diff region overlaps the planted site). Plus the CLEAN-PAIR
control (false-positive rate) and the FACTS-WRONG conflict case. Reports per-class recall + FP rate
(the AOI convention). Run in the routing container (pcbnew + scipy + rsvg).

  docker exec docker-routing-1 python3 /workspace/scripts/cec_defect_battery.py \
      --board build/route/enforce-2port/pcie-8pin-2port-routed.kicad_pcb

BENCHMARK GATE (owner ruling): the pre-pass must hit >=99% per-class catch on the enumerable
classes, or the diff/morphology is fixed before any VLM work.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import pcbnew                                                    # noqa: E402
import cec_render_diff as rd                                     # noqa: E402
import cec_dfm_check as dfm                                      # noqa: E402

MM = 1_000_000


def render_modelfree(board_path, out_png):
    """DIRECT in-container model-free copper render (kicad-cli SVG of F.Cu/B.Cu/Edge.Cuts ->
    rsvg-convert PNG). Same output as cec_fullstack.render_copper_zone but called directly, since
    the battery runs INSIDE the routing container (the host-side docker-exec wrapper would nest)."""
    # ZOOM: a min-feature trace (~0.1-0.2 mm) is sub-pixel at the SVG's native 96dpi, so morphology
    # erodes it and the pre-pass misses it (detection difficulty scales with defect-to-pixel ratio,
    # per the dive). Rasterize at high zoom so a 0.2 mm feature is several px. Edge.Cuts is unchanged
    # by copper plants, so page-size-mode 2 keeps reference+candidate PIXEL-REGISTERED.
    zoom = os.environ.get("CEC_DIFF_ZOOM", "8")
    svg = out_png.rsplit(".", 1)[0] + "-copper.svg"
    subprocess.run(["kicad-cli", "pcb", "export", "svg", "--layers", "F.Cu,B.Cu,Edge.Cuts",
                    "--exclude-drawing-sheet", "--page-size-mode", "2", "-o", svg, board_path],
                   capture_output=True, text=True, timeout=180)
    if not os.path.exists(svg):
        return False
    subprocess.run(["sh", "-c", f"rsvg-convert --zoom {zoom} -o '{out_png}' '{svg}' "
                    f"|| convert -density {int(float(zoom)*96)} '{svg}' '{out_png}'"],
                   capture_output=True, text=True, timeout=120)
    return os.path.exists(out_png)


def _track(b, x0, y0, x1, y1, width_mm, layer=pcbnew.F_Cu, net=0):
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(pcbnew.VECTOR2I(int(x0 * MM), int(y0 * MM)))
    t.SetEnd(pcbnew.VECTOR2I(int(x1 * MM), int(y1 * MM)))
    t.SetWidth(int(width_mm * MM))
    t.SetLayer(layer)
    t.SetNetCode(net)
    b.Add(t)
    return t


def _empty_spot(b):
    """A board-interior point with no copper nearby (for isolated-copper plants)."""
    bb = b.GetBoardEdgesBoundingBox()
    return (bb.GetCenter().x / MM, bb.GetTop() / MM + 3.0)


# --- plant functions: each returns the planted site bbox_mm [x0,y0,x1,y1] ----------------------
def plant_spurious_copper(b, size=1.0):
    x, y = _empty_spot(b)
    _track(b, x, y, x + size, y, size)                           # a fat isolated copper dab
    return [x - 0.6, y - 0.6, x + size + 0.6, y + 0.6]


def plant_spur(b, size=1.2):
    # a spur is a short stub sprouting off a real track. Sprout it from the track MIDPOINT,
    # PERPENDICULAR to the track, so it extends into open copper-free space (a stub collinear with
    # the track, or rooted at a pad/via, gets masked in the diff by the copper it overlaps).
    import math
    t = next((t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"
              and t.GetLength() > 1.5 * MM), None)
    s, e = t.GetStart(), t.GetEnd()
    mx, my = (s.x + e.x) / 2 / MM, (s.y + e.y) / 2 / MM
    dx, dy = (e.x - s.x) / MM, (e.y - s.y) / MM
    L = math.hypot(dx, dy) or 1.0
    px, py = -dy / L, dx / L                                     # unit perpendicular
    ex, ey = mx + px * size, my + py * size
    _track(b, mx, my, ex, ey, 0.2, t.GetLayer(), t.GetNetCode())
    return [min(mx, ex) - 0.4, min(my, ey) - 0.4, max(mx, ex) + 0.4, max(my, ey) + 0.4]


def plant_sliver(b, length=1.5):
    x, y = _empty_spot(b)
    _track(b, x, y, x + length, y, 0.06)                         # a thin copper wedge
    return [x - 0.4, y - 0.4, x + length + 0.4, y + 0.4]


def plant_short(b):
    ts = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
    a, c = ts[0], ts[min(5, len(ts) - 1)]
    ax, ay = a.GetStart().x / MM, a.GetStart().y / MM
    cx, cy = c.GetStart().x / MM, c.GetStart().y / MM
    _track(b, ax, ay, cx, cy, 0.3)                               # bridge two tracks
    return [min(ax, cx) - 0.5, min(ay, cy) - 0.5, max(ax, cx) + 0.5, max(ay, cy) + 0.5]


def plant_open(b):
    t = next((t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"
              and t.GetLength() > 2 * MM), None)
    s, e = t.GetStart(), t.GetEnd()
    bb = [min(s.x, e.x) / MM, min(s.y, e.y) / MM, max(s.x, e.x) / MM, max(s.y, e.y) / MM]
    b.Remove(t)                                                  # delete a track = open
    return [bb[0] - 0.3, bb[1] - 0.3, bb[2] + 0.3, bb[3] + 0.3]


def plant_stale_fill(b, size=2.0):
    # gap class: change copper while the deterministic FACTS stay correct -> the render diverges
    # from the reference even though pour_facts() would report the old (stale) value. Catchable by
    # the render-diff (render vs reference), NOT by a facts-only checker -- the conflict case.
    x, y = _empty_spot(b)
    _track(b, x, y + 2, x + size, y + 2, size)
    return [x - 0.6, y + 2 - 0.6, x + size + 0.6, y + 2 + 0.6]


def _long_track(b, min_len=2.0):
    return next((t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"
                 and t.GetLength() > min_len * MM), None)


def plant_mousebite(b):
    # classical six: a bite of copper missing from a connection -> necking. Re-lay a long track as
    # 3 collinear pieces with a NARROW (<MIN_CONN) middle. Trips DFM connection_width AND the
    # render-diff (copper removed along the necked edges).
    import math
    t = _long_track(b)
    s, e = t.GetStart(), t.GetEnd()
    layer, net, w = t.GetLayer(), t.GetNetCode(), t.GetWidth() / MM
    sx, sy, ex, ey = s.x / MM, s.y / MM, e.x / MM, e.y / MM
    dx, dy = ex - sx, ey - sy
    p1 = (sx + dx * 0.42, sy + dy * 0.42)
    p2 = (sx + dx * 0.52, sy + dy * 0.52)
    b.Remove(t)
    _track(b, sx, sy, p1[0], p1[1], w, layer, net)
    _track(b, p1[0], p1[1], p2[0], p2[1], 0.08, layer, net)      # the bite (necked)
    _track(b, p2[0], p2[1], ex, ey, w, layer, net)
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    return [mx - 0.5, my - 0.5, mx + 0.5, my + 0.5]


def plant_pinhole(b, gap=0.25):
    # classical six: a tiny copper void. Min-feature absence -- excise a short piece from a track's
    # middle (a render-diff absence at the floor of feature size).
    t = _long_track(b, min_len=3.0)
    s, e = t.GetStart(), t.GetEnd()
    layer, net, w = t.GetLayer(), t.GetNetCode(), t.GetWidth() / MM
    sx, sy, ex, ey = s.x / MM, s.y / MM, e.x / MM, e.y / MM
    dx, dy = ex - sx, ey - sy
    import math
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    c = 0.5
    cx, cy = sx + dx * c, sy + dy * c
    b.Remove(t)
    _track(b, sx, sy, cx - ux * gap / 2, cy - uy * gap / 2, w, layer, net)
    _track(b, cx + ux * gap / 2, cy + uy * gap / 2, ex, ey, w, layer, net)
    return [cx - 0.4, cy - 0.4, cx + 0.4, cy + 0.4]


def plant_acid_trap(b, leg=1.2):
    # gap class: an acute copper wedge (KiCad's native gap -> the custom rule). Root a stub at a real
    # track ENDPOINT so that vertex has two same-net legs only ~20deg apart -> a <40deg wedge the
    # custom acid-trap rule fires on (AND the render-diff sees the added copper).
    import math
    t = _long_track(b)
    s, e = t.GetStart(), t.GetEnd()
    ex0, ey0 = e.x / MM, e.y / MM                                # the endpoint we sprout from
    ox, oy = (s.x - e.x) / MM, (s.y - e.y) / MM                  # outward dir at e (back along track)
    L = math.hypot(ox, oy) or 1.0
    ux, uy = ox / L, oy / L
    ang = math.radians(20)                                       # stub 20deg off the track's own leg
    rx = ux * math.cos(ang) - uy * math.sin(ang)
    ry = ux * math.sin(ang) + uy * math.cos(ang)
    sx2, sy2 = ex0 + rx * leg, ey0 + ry * leg
    _track(b, ex0, ey0, sx2, sy2, 0.2, t.GetLayer(), t.GetNetCode())
    return [min(ex0, sx2) - 0.4, min(ey0, sy2) - 0.4, max(ex0, sx2) + 0.4, max(ey0, sy2) + 0.4]


def plant_unexpected_keepout(b, r=1.5):
    # gap class: copper cleared where it should be present (a stray keepout's effect) -> a region of
    # ABSENCE. Delete the tracks passing through a small window. Caught by render-diff (absence).
    bb = b.GetBoardEdgesBoundingBox()
    cx, cy = bb.GetCenter().x / MM, bb.GetCenter().y / MM
    victims = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"
               and abs(t.GetStart().x / MM - cx) < r and abs(t.GetStart().y / MM - cy) < r]
    for t in victims[:6]:
        b.Remove(t)
    return [cx - r, cy - r, cx + r, cy + r]


def plant_corridor_anomaly(b, length=2.0):
    # gap class: unexpected copper intruding into a reserved (should-be-clear) corridor. Add a track
    # crossing an empty interior band. Caught by render-diff (added copper where none is expected).
    bb = b.GetBoardEdgesBoundingBox()
    x = bb.GetCenter().x / MM
    y = bb.GetBottom() / MM - 3.0                                # a clear band near the bottom edge
    _track(b, x - length / 2, y, x + length / 2, y, 0.3)
    return [x - length / 2 - 0.5, y - 0.5, x + length / 2 + 0.5, y + 0.5]


def plant_wrong_net_fill(b):
    # gap class: copper joined to the WRONG net -- a fill bridging two different-net conductors.
    # Caught by render-diff (added copper) AND DFM shorting_items (a NEW short).
    ts = [t for t in b.GetTracks() if t.GetClass() == "PCB_TRACK"]
    nets = {}
    for t in ts:
        nets.setdefault(t.GetNetCode(), t)
    keys = [k for k in nets if k > 0][:2]
    if len(keys) < 2:
        keys = list(nets)[:2]
    a, c = nets[keys[0]], nets[keys[1]]
    ax, ay = a.GetStart().x / MM, a.GetStart().y / MM
    cx, cy = c.GetStart().x / MM, c.GetStart().y / MM
    _track(b, ax, ay, cx, cy, 0.5)                               # a wide bridge -> wrong-net join
    return [min(ax, cx) - 0.5, min(ay, cy) - 0.5, max(ax, cx) + 0.5, max(ay, cy) + 0.5]


PLANTS = {                                                       # classical six + the gap classes
    "open": plant_open,
    "short": plant_short,
    "mousebite": plant_mousebite,
    "spur": plant_spur,
    "pinhole": plant_pinhole,
    "spurious_copper": plant_spurious_copper,
    "sliver": plant_sliver,
    "acid_trap": plant_acid_trap,
    "unexpected_keepout": plant_unexpected_keepout,
    "corridor_anomaly": plant_corridor_anomaly,
    "wrong_net_fill": plant_wrong_net_fill,
    "stale_fill_conflict": plant_stale_fill,
}


def _overlap(region_bbox_px, site_bbox_px):
    ax0, ay0, ax1, ay1 = region_bbox_px
    bx0, by0, bx1, by1 = site_bbox_px
    return not (ax1 < bx0 or bx1 < ax0 or ay1 < by0 or by1 < ay0)


def _edges_mm_inproc(board_path):
    """Board-edge bbox as plain floats (left, top, w, h)."""
    bb = pcbnew.LoadBoard(board_path).GetBoardEdgesBoundingBox()
    return [bb.GetLeft() / MM, bb.GetTop() / MM, bb.GetWidth() / MM, bb.GetHeight() / MM]


def _sub(*args):
    """Run a pcbnew sub-op in a FRESH interpreter -> exactly one board load per process (repeated
    LoadBoard in one interpreter returns invalidated SWIG proxies; the recorded pcbnew footgun)."""
    p = subprocess.run([sys.executable, os.path.abspath(__file__), *args],
                       capture_output=True, text=True, timeout=240)
    # scan from the end for the last JSON-parseable line: pcbnew prints SWIG "memory leak" teardown
    # lines AFTER our print when a plant Removes tracks, so [-1] is not reliable.
    for line in reversed(p.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
    return {"error": (p.stderr or p.stdout or "no output")[-300:]}


def _mm_bbox_to_px(site_mm, edges, shape):
    left, top, bw, bh = edges
    H, W = shape
    sx, sy = W / bw, H / bh
    return [(site_mm[0] - left) * sx, (site_mm[1] - top) * sy,
            (site_mm[2] - left) * sx, (site_mm[3] - top) * sy]


def _dfm_key(v):
    return (v["type"], round(v["pos_mm"][0] / 0.3), round(v["pos_mm"][1] / 0.3))


def run(board_path, workdir):
    ref_pcb = os.path.abspath(board_path)
    ref_png = os.path.join(workdir, "reference.png")
    if not render_modelfree(ref_pcb, ref_png):
        return {"error": "reference render failed (rsvg/kicad-cli?)"}
    edges = _sub("--edges", ref_pcb)                            # subprocess: one board load per proc
    ref_dfm = {_dfm_key(v) for v in dfm.dfm_check(ref_pcb)}      # DFM baseline (subtract per candidate)
    rows = []
    # high-res render -> small features survive; open_iter=0 keeps min-feature defects (the renders
    # are deterministic + identical except the plant, so no AA jitter -> lowering min_area is safe).
    dp = {"thresh": 40, "min_area_px": 4, "open_iter": 0, "close_iter": 1}
    # clean-pair control -> render-diff false-positive rate; DFM FP is 0 by construction (baseline-sub)
    clean = rd.render_diff(ref_png, ref_png, **dp)
    rows.append({"class": "CLEAN_CONTROL", "caught": None, "diff_regions": clean["n_regions"],
                 "new_dfm": 0, "note": "false-positive check: must be 0"})
    for cls in PLANTS:
        cand = os.path.join(workdir, f"{cls}.kicad_pcb")
        res = _sub("--plant", cls, ref_pcb, cand)               # subprocess: load->plant->save->site
        if not isinstance(res, list):
            rows.append({"class": cls, "caught": None,
                         "error": f"plant: {res.get('error') if isinstance(res, dict) else res}"})
            continue
        site_mm = res
        cand_png = os.path.join(workdir, f"{cls}.png")
        if not render_modelfree(cand, cand_png):
            rows.append({"class": cls, "caught": None, "error": "render failed"})
            continue
        # layer 1: render-diff vs the frozen reference
        d = rd.render_diff(cand_png, ref_png, **dp)
        site_px = _mm_bbox_to_px(site_mm, edges, d["shape"])
        diff_hit = any(_overlap(r["bbox_px"], site_px) for r in d["regions"])
        # layer 2: DFM, baseline-subtracted (only NEW violations), mapped to px, overlap with site
        new_dfm = [v for v in dfm.dfm_check(cand) if _dfm_key(v) not in ref_dfm]
        dfm_px = dfm.violations_to_px(new_dfm, edges, d["shape"])
        dfm_hit = any(_overlap(p["bbox_px"], site_px) for p in dfm_px)
        layers = ([("diff" if diff_hit else None), ("dfm" if dfm_hit else None)])
        caught_by = [x for x in layers if x]
        rows.append({"class": cls, "caught": bool(caught_by), "caught_by": caught_by,
                     "diff_regions": d["n_regions"], "new_dfm": len(new_dfm),
                     "new_dfm_types": sorted({v["type"] for v in new_dfm}),
                     "site_px": [round(v, 1) for v in site_px]})
    enum = [r for r in rows if r["class"] != "CLEAN_CONTROL" and r.get("caught") is not None]
    caught_n = sum(1 for r in enum if r["caught"])
    fp = next((r["diff_regions"] for r in rows if r["class"] == "CLEAN_CONTROL"), None)
    recall = caught_n / len(enum) if enum else 0.0
    report = {"reference": os.path.relpath(ref_pcb, ROOT), "n_classes": len(enum), "rows": rows,
              "per_class_recall": f"{caught_n}/{len(enum)}", "recall_pct": round(recall * 100, 1),
              "false_positive_regions": fp,
              "benchmark_gate": ">=99% per-class catch + 0 false positives (owner ruling)",
              "verdict": ("PASS" if enum and caught_n == len(enum) and fp == 0
                          else "FAIL -- fix diff/morphology/DFM before any VLM work")}
    return report


if __name__ == "__main__":
    # subprocess dispatch (one board load per interpreter -- the pcbnew footgun). These print a single
    # JSON line on stdout consumed by _sub().
    if len(sys.argv) >= 3 and sys.argv[1] == "--edges":
        print(json.dumps(_edges_mm_inproc(sys.argv[2])))
        sys.exit(0)
    if len(sys.argv) >= 5 and sys.argv[1] == "--plant":
        _cls, _ref, _out = sys.argv[2], sys.argv[3], sys.argv[4]
        _b = pcbnew.LoadBoard(_ref)
        _site = PLANTS[_cls](_b)
        _b.Save(_out)
        print(json.dumps(_site))
        sys.exit(0)

    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="build/route/enforce-2port/pcie-8pin-2port-routed.kicad_pcb")
    ap.add_argument("--out", default="docs/det-inspection/defect-battery.json")
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as wd:
        rep = run(os.path.join(ROOT, a.board), wd)
    outp = os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    json.dump(rep, open(outp, "w"), indent=1)
    for r in rep.get("rows", []):
        by = "+".join(r.get("caught_by", [])) or "-"
        print(f"  {r['class']:<22} caught={str(r.get('caught')):<5} by={by:<9} "
              f"diff={r.get('diff_regions')} new_dfm={r.get('new_dfm')} "
              f"{','.join(r.get('new_dfm_types', []))}"
              + (f"  ERR {r['error']}" if r.get("error") else ""))
    print(f"\nper-class recall {rep.get('per_class_recall')} ({rep.get('recall_pct')}%), FP regions "
          f"{rep.get('false_positive_regions')} -> {rep.get('verdict')}")
    print(f"artifact -> {a.out}")
