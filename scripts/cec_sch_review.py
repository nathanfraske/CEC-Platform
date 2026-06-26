#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_sch_review -- render a KiCad schematic to images so an agent (or human) can
# VISUALLY review it, instead of only reasoning over raw netlist/s-expr geometry.
#
# This is prototype #1 from the 2026-06-25 KiCad-integration research (see
# .claude memory: kicad-integration-landscape): the "render the schematic and
# look at it yourself" loop. It needs NO KiCad plugin -- kicad-cli already exports
# the schematic to SVG; we rasterize with cairosvg (libcairo is on the box; this
# is the no-sudo equivalent of the project's rsvg-convert path) and tile so that
# pin names / net labels / values stay legible after the agent harness downscales
# an image (~1568 px long edge).
#
# Output per sheet:
#   - <sheet>.full.png      high-DPI raster (source of truth)
#   - <sheet>.overview.png  downscaled to <=1568 px  -> macro LAYOUT review
#   - <sheet>.r{R}c{C}.png   native-res tiles (<=~1550 px) -> pin-level DETAIL
#   - manifest.json          paths + ERC summary, in agent-Read order
#
# Run under the repo venv (has cairosvg):  .venv/bin/python scripts/cec_sch_review.py <board>
import argparse, glob, json, math, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_PX = 1568          # agent image-downscale long edge; overview targets this
DEFAULT_SCALE = 2.4        # cairosvg scale over the kicad SVG (~96dpi A3 -> ~230dpi)
DEFAULT_TILE_PX = 1550     # keep each tile's long edge at/under this for legibility


def find_sch(board):
    """Resolve a board NAME (dir under modules/ or hubs/) or a path to a .kicad_sch.
    Skips backups and the kicad-cli '-bak'/cache files."""
    if board.endswith(".kicad_sch") and os.path.isfile(board):
        return os.path.abspath(board)
    cands = []
    for area in ("modules", "hubs"):
        cands += [p for p in glob.glob(f"{ROOT}/{area}/{board}/*.kicad_sch")
                  if "-bak" not in p and "_autosave" not in os.path.basename(p)]
    if not cands:
        have = sorted(os.path.basename(os.path.dirname(p))
                      for p in glob.glob(f"{ROOT}/modules/*/") + glob.glob(f"{ROOT}/hubs/*/"))
        raise FileNotFoundError(f"no .kicad_sch for '{board}' under modules/ or hubs/ (have: {have})")
    return os.path.abspath(sorted(cands)[0])


def run_erc(sch):
    """kicad-cli sch erc -> compact summary {violations, by_severity, top:[...]}.
    Never raises -- ERC failure is data for the review, not an error here."""
    out = os.path.join(os.path.dirname(sch), "_erc_review.json")
    try:
        subprocess.run(["kicad-cli", "sch", "erc", "--exit-code-violations",
                        "--severity-all", "--format", "json", "-o", out, sch],
                       capture_output=True, text=True, timeout=300)
        data = json.load(open(out))
    except Exception as e:                                  # noqa: BLE001
        return {"available": False, "note": f"ERC skipped: {e}"}
    finally:
        if os.path.exists(out):
            os.remove(out)
    sev, top = {}, []
    for sheet in data.get("sheets", []):
        for v in sheet.get("violations", []):
            s = v.get("severity", "unknown")
            sev[s] = sev.get(s, 0) + 1
            if len(top) < 25:
                top.append({"severity": s, "type": v.get("type"),
                            "desc": (v.get("description") or "")[:160]})
    return {"available": True, "violations": sum(sev.values()), "by_severity": sev, "top": top}


def export_svgs(sch, outdir):
    """kicad-cli exports one SVG per sheet into outdir; return them sorted."""
    os.makedirs(outdir, exist_ok=True)
    for f in glob.glob(os.path.join(outdir, "*.svg")):
        os.remove(f)
    r = subprocess.run(["kicad-cli", "sch", "export", "svg", "-o", outdir, sch],
                       capture_output=True, text=True)
    svgs = sorted(glob.glob(os.path.join(outdir, "*.svg")))
    if not svgs:
        raise RuntimeError(f"kicad-cli produced no SVG:\n{r.stdout}\n{r.stderr}")
    return svgs


def _bounds(length, max_px, overlap):
    """1-D tile bounds covering [0,length) in <=max_px chunks with fractional overlap."""
    n = max(1, math.ceil(length / max_px))
    if n == 1:
        return [(0, length)]
    step = length / n
    ov = int(step * overlap)
    out = []
    for i in range(n):
        lo = max(0, int(round(i * step)) - ov)
        hi = min(length, int(round((i + 1) * step)) + ov)
        out.append((lo, hi))
    return out


def rasterize_and_tile(svg, stem, scale, tile_px, overlap):
    """SVG -> full.png + overview.png + native-res tiles. Returns the sheet manifest."""
    import cairosvg
    from PIL import Image
    full = f"{stem}.full.png"
    cairosvg.svg2png(url=svg, write_to=full, scale=scale)
    im = Image.open(full).convert("RGB")
    W, H = im.size

    overview = f"{stem}.overview.png"
    f = min(1.0, HARNESS_PX / max(W, H))
    (im if f == 1.0 else im.resize((max(1, int(W * f)), max(1, int(H * f))), Image.LANCZOS)).save(overview)

    xs, ys = _bounds(W, tile_px, overlap), _bounds(H, tile_px, overlap)
    tiles = []
    multi = len(xs) * len(ys) > 1
    for r, (y0, y1) in enumerate(ys):
        for c, (x0, x1) in enumerate(xs):
            if not multi:
                break
            p = f"{stem}.r{r}c{c}.png"
            im.crop((x0, y0, x1, y1)).save(p)
            tiles.append({"path": os.path.relpath(p, ROOT), "row": r, "col": c,
                          "box_px": [x0, y0, x1, y1]})
    return {"svg": os.path.relpath(svg, ROOT), "full_png": os.path.relpath(full, ROOT),
            "overview_png": os.path.relpath(overview, ROOT), "size_px": [W, H],
            "grid": [len(ys), len(xs)], "tiles": tiles}


def review(board, outdir=None, scale=DEFAULT_SCALE, tile_px=DEFAULT_TILE_PX,
           overlap=0.06, erc=True):
    sch = find_sch(board)
    name = os.path.splitext(os.path.basename(sch))[0]
    outdir = outdir or os.path.join(ROOT, "build", "sch-review", name)
    os.makedirs(outdir, exist_ok=True)
    svgs = export_svgs(sch, outdir)
    sheets = [rasterize_and_tile(svg, os.path.join(outdir, f"sheet{i}"), scale, tile_px, overlap)
              for i, svg in enumerate(svgs)]
    manifest = {"board": board, "sch": os.path.relpath(sch, ROOT),
                "erc": run_erc(sch) if erc else {"available": False, "note": "skipped"},
                "sheets": sheets,
                "read_order": ["For each sheet: Read overview_png (macro layout), "
                               "then each tile r0c0..rNcM (pin-level detail).",
                               "Pair with the ERC summary; report issues as "
                               "<sheet>/<region> + what is wrong + a fix."]}
    mpath = os.path.join(outdir, "manifest.json")
    json.dump(manifest, open(mpath, "w"), indent=2)
    return mpath, manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render a KiCad schematic to tiled PNGs for visual review.")
    ap.add_argument("board", help="board name (modules/ or hubs/) or path to a .kicad_sch")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--scale", type=float, default=DEFAULT_SCALE)
    ap.add_argument("--tile-px", type=int, default=DEFAULT_TILE_PX)
    ap.add_argument("--overlap", type=float, default=0.06)
    ap.add_argument("--no-erc", action="store_true")
    a = ap.parse_args(argv)
    mpath, m = review(a.board, a.outdir, a.scale, a.tile_px, a.overlap, erc=not a.no_erc)
    n_tiles = sum(len(s["tiles"]) for s in m["sheets"])
    erc = m["erc"]
    print(f"manifest: {os.path.relpath(mpath, ROOT)}")
    print(f"sheets: {len(m['sheets'])}  tiles: {n_tiles}  "
          f"grid: {[s['grid'] for s in m['sheets']]}")
    if erc.get("available"):
        print(f"ERC: {erc['violations']} violations  {erc['by_severity']}")
    for s in m["sheets"]:
        print(f"  overview: {s['overview_png']}  ({s['size_px'][0]}x{s['size_px'][1]} px)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
