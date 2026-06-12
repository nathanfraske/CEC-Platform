"""DRC/DFM detection layer -- the second half of the deterministic pre-pass (owner ruling 2026-06-11,
docs/decisions/owner-ruling-vlm-detection-pipeline-2026-06-11.md).

Where the render-diff (cec_render_diff) catches a board's DELTA vs its frozen known-good reference,
this layer catches absolute MANUFACTURABILITY violations on a SINGLE board with no reference -- the
case a freshly synthesized board (no prior golden) presents. It leans on KiCad's native DFM checks
and fills KiCad's one native gap with a custom rule:

  * native (run via kicad-cli pcb drc): copper_sliver, isolated_copper (dead copper), the
    connection_width minimum (necking / mousebite / starved connection), clearance, shorting_items.
    We FORCE the min-connection-width check on with a DFM .kicad_dru regardless of board settings,
    and read everything at --severity-all.
  * custom acid-trap rule (KiCad has no acute-angle predicate): a geometric scan for an acute copper
    wedge -- two same-net track segments leaving a shared vertex with < ACID_DEG between their
    outward directions, the pocket where etchant pools. This is "the one native gap" the owner named.

Returns violations as {type, severity, pos_mm, desc} and, given a render shape + board, the same list
mapped to pixel sites so the battery can fuse it with the render-diff regions (caught = either layer).

  from cec_dfm_check import dfm_check
  v = dfm_check("board.kicad_pcb")        # [{type, severity, pos_mm:[x,y], desc}, ...]
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

MM = 1_000_000
ACID_DEG = 40.0          # acute-angle threshold (deg between outward dirs); BELOW 45 so the routine
#                          45-degree router bend does not fire -- an acid trap is a substantially
#                          sub-45-degree copper wedge. Even so this rule over-fires in ABSOLUTE terms
#                          (benign convergences at pads); it is meant to run reference-baseline-
#                          subtracted (the battery does this), where benign junctions cancel.
MIN_CONN_MM = 0.13       # min connection width -> catches necking/mousebite/sliver in connected copper

# DFM-relevant native DRC types; cosmetic/library noise is dropped (silk_*, lib_footprint_issues, etc.)
DFM_TYPES = {"clearance", "shorting_items", "copper_sliver", "isolated_copper",
             "connection_width", "track_width", "hole_clearance", "copper_edge_clearance",
             "solder_mask_bridge", "starved_thermal", "via_dangling", "hole_near_hole"}

_DFM_DRU = f"""(version 1)
(rule "dfm-min-connection-width"
   (constraint connection_width (min {MIN_CONN_MM}mm))
   (severity error))
(rule "dfm-min-track-width"
   (constraint track_width (min 0.1mm))
   (severity warning))
"""


def _native_drc(board_path):
    """Run kicad-cli pcb drc with the DFM .kicad_dru forcing the connection-width check on."""
    work = tempfile.mkdtemp(prefix="cec_dfm_")
    try:
        bp = os.path.join(work, "board.kicad_pcb")
        shutil.copy(board_path, bp)
        # a sibling <board>.kicad_dru is auto-loaded by kicad-cli for that board
        open(os.path.join(work, "board.kicad_dru"), "w").write(_DFM_DRU)
        out = os.path.join(work, "drc.json")
        subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "--severity-all",
                        "--refill-zones", "--units", "mm", "-o", out, bp],
                       capture_output=True, text=True, timeout=240)
        if not os.path.exists(out):
            return []
        d = json.load(open(out))
        rows = []
        for v in d.get("violations", []):
            if v.get("type") not in DFM_TYPES:
                continue
            items = v.get("items", [])
            if not items:
                continue
            # average the cited item positions for a representative location
            xs = [it["pos"]["x"] for it in items if "pos" in it]
            ys = [it["pos"]["y"] for it in items if "pos" in it]
            if not xs:
                continue
            rows.append({"type": v["type"], "severity": v.get("severity", "error"),
                         "pos_mm": [sum(xs) / len(xs), sum(ys) / len(ys)],
                         "desc": v.get("description", "")})
        return rows
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _acid_traps(board_path):
    """Custom acid-trap rule, run in a SUBPROCESS so dfm_check does NO in-process pcbnew (concurrent
    pcbnew boards in one interpreter collide -- the SWIG footgun the battery hits holding a board)."""
    p = subprocess.run([sys.executable, os.path.abspath(__file__), "--acid-only", board_path],
                       capture_output=True, text=True, timeout=180)
    try:
        return json.loads(p.stdout)
    except (ValueError, json.JSONDecodeError):
        return []


def _acid_traps_inproc(board_path):
    """The actual acute-wedge scan (only safe as the sole board load in its interpreter)."""
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    # group segment endpoints by quantized vertex + net
    verts = {}                                                   # (qx,qy,net) -> [outward dir vectors]
    Q = 50_000                                                   # 0.05 mm quantization
    for t in b.GetTracks():
        if t.GetClass() != "PCB_TRACK":
            continue
        s, e = t.GetStart(), t.GetEnd()
        net = t.GetNetCode()
        for a, o in ((s, e), (e, s)):                            # at endpoint a, outward dir toward o
            key = (round(a.x / Q), round(a.y / Q), net)
            dx, dy = (o.x - a.x), (o.y - a.y)
            L = math.hypot(dx, dy)
            if L:
                verts.setdefault(key, []).append((dx / L, dy / L, a.x, a.y))
    rows = []
    for (_, _, _), dirs in verts.items():
        for i in range(len(dirs)):
            for j in range(i + 1, len(dirs)):
                d1, d2 = dirs[i], dirs[j]
                cos = max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1]))
                ang = math.degrees(math.acos(cos))
                if ang < ACID_DEG:                               # acute wedge between two same-net legs
                    rows.append({"type": "acid_trap", "severity": "warning",
                                 "pos_mm": [d1[2] / MM, d1[3] / MM],
                                 "desc": f"acute copper wedge {ang:.0f}deg < {ACID_DEG:.0f}deg"})
    # de-dup by quantized location
    seen, uniq = set(), []
    for r in rows:
        k = (round(r["pos_mm"][0], 1), round(r["pos_mm"][1], 1))
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def dfm_check(board_path):
    """All DFM violations on a single board: native DRC (DFM-relevant types) + the custom acid trap."""
    return _native_drc(board_path) + _acid_traps(board_path)


def violations_to_px(violations, edges, shape, halo_mm=0.6):
    """Map each violation pos_mm to a px bbox (halo box) for overlap testing against diff regions.

    edges = (left_mm, top_mm, width_mm, height_mm) of the board-edge bbox, captured as plain floats
    by the caller BEFORE any later LoadBoard (a held pcbnew bbox proxy dies on the next board load)."""
    left, top, bw, bh = edges
    H, W = shape
    sx, sy = W / bw, H / bh
    out = []
    for v in violations:
        cx = (v["pos_mm"][0] - left) * sx
        cy = (v["pos_mm"][1] - top) * sy
        hx, hy = halo_mm * sx, halo_mm * sy
        out.append({"v": v, "bbox_px": [cx - hx, cy - hy, cx + hx, cy + hy]})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("--acid-only", action="store_true",
                    help="emit only the acid-trap scan as JSON (subprocess-isolation entry point)")
    a = ap.parse_args()
    bp = a.board if os.path.isabs(a.board) else os.path.join(ROOT, a.board)
    if a.acid_only:
        print(json.dumps(_acid_traps_inproc(bp)))
        sys.exit(0)
    vs = dfm_check(bp)
    import collections
    c = collections.Counter(v["type"] for v in vs)
    print(json.dumps({"n": len(vs), "by_type": dict(c), "violations": vs}, indent=1))
