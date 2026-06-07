#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_plot -- a board-accurate COPPER PLOT for human review (PIL, no matplotlib).
# ============================================================================
# Draws the routed copper the way a reviewer wants to see it (the matte-black 3D
# render hides traces): F.Cu red / B.Cu blue / inner faint, vias, pads, the
# decorative LOGO copper, and the structural DRC violations classified by the
# finishing classifier (real short = red X, finishing/known-false = grey O).
#
#   from cec_plot import copper_plot
#   copper_plot("board.kicad_pcb", "out.png", title="...")
# ============================================================================
import os, sys, json, re, subprocess, tempfile

import pcbnew
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_dispatch   # _locus_is_finishing, _bracket_nets, _fp_refs

_COSMETIC = ("silk_overlap", "silk_over_copper", "silk_edge_clearance",
             "lib_footprint_mismatch", "lib_footprint_issues")
_LCOL = {pcbnew.F_Cu: (214, 40, 40), pcbnew.B_Cu: (40, 90, 214),
         pcbnew.In1_Cu: (120, 180, 120), pcbnew.In2_Cu: (180, 120, 180)}
_ORDER = [pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.F_Cu, pcbnew.B_Cu]


def _mm(v):
    return v / 1e6


def _font(sz, bold=True):
    for n in (("arialbd.ttf", "arial.ttf") if bold else ("arial.ttf",)):
        try:
            return ImageFont.truetype(n, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def _drc(path):
    out = os.path.join(tempfile.gettempdir(), "cec_plot_drc_%d.json" % os.getpid())
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", out, path], capture_output=True)
    try:
        return json.load(open(out))
    except Exception:
        return {}


def copper_plot(board_path, out_png, title=None, width=1700):
    b = pcbnew.LoadBoard(board_path)
    bb = b.GetBoardEdgesBoundingBox()
    minx, miny = _mm(bb.GetLeft()) - 3, _mm(bb.GetTop()) - 3
    maxx, maxy = _mm(bb.GetRight()) + 3, _mm(bb.GetBottom()) + 3
    scale = width / (maxx - minx)
    top = 64
    W, H = int((maxx - minx) * scale), int((maxy - miny) * scale) + top
    im = Image.new("RGB", (W, H), (250, 250, 250))
    g = ImageDraw.Draw(im)

    def X(x):
        return (x - minx) * scale

    def Y(y):
        return (y - miny) * scale + top

    def P(pt):
        return (X(_mm(pt.x)), Y(_mm(pt.y)))

    g.text((12, 8), title or os.path.basename(board_path), fill=(0, 0, 0), font=_font(21))
    g.text((12, 38), "top-down, both copper layers (KiCad orientation)", fill=(90, 90, 90), font=_font(15, False))

    for s in b.GetDrawings():
        if s.GetLayer() != pcbnew.Edge_Cuts:
            continue
        try:
            if s.GetShape() == pcbnew.SHAPE_T_RECT:
                a, c = P(s.GetStart()), P(s.GetEnd())
                g.rectangle([min(a[0], c[0]), min(a[1], c[1]), max(a[0], c[0]), max(a[1], c[1])], outline=(0, 0, 0), width=2)
            else:
                g.line([P(s.GetStart()), P(s.GetEnd())], fill=(0, 0, 0), width=2)
        except Exception:
            pass

    for fp in b.GetFootprints():
        for pad in fp.Pads():
            c, sz = P(pad.GetPosition()), pad.GetSize()
            w, h = _mm(sz.x) * scale / 2, _mm(sz.y) * scale / 2
            ls = pad.GetLayerSet()
            f, bk = ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu)
            col = (222, 206, 140) if (f and bk) else ((232, 184, 184) if f else (184, 202, 236))
            g.rectangle([c[0] - w, c[1] - h, c[0] + w, c[1] + h], fill=col)
        if fp.GetReference().upper().startswith("LOGO"):
            for it in fp.GraphicalItems():
                try:
                    if it.GetLayer() in (pcbnew.F_Cu, pcbnew.B_Cu) and it.GetShape() == pcbnew.SHAPE_T_POLY:
                        ol = it.GetPolyShape().Outline(0)
                        pts = [(X(_mm(ol.CPoint(i).x)), Y(_mm(ol.CPoint(i).y))) for i in range(ol.PointCount())]
                        if len(pts) >= 3:
                            g.polygon(pts, fill=(255, 178, 76))
                except Exception:
                    pass

    bylayer, vias = {}, []
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_TRACE_T:
            bylayer.setdefault(t.GetLayer(), []).append((P(t.GetStart()), P(t.GetEnd()), _mm(t.GetWidth()) * scale))
        elif t.Type() == pcbnew.PCB_VIA_T:
            try:
                dia = _mm(t.GetWidth(t.TopLayer()))
            except Exception:
                dia = 0.6
            vias.append((P(t.GetPosition()), dia * scale / 2))
    for ly in _ORDER + [k for k in bylayer if k not in _ORDER]:
        for s, e, w in bylayer.get(ly, []):
            g.line([s, e], fill=_LCOL.get(ly, (150, 150, 150)), width=max(1, int(round(w))))
    for c, r in vias:
        g.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=(35, 35, 35))

    real = fin = 0
    for v in _drc(board_path).get("violations", []):
        if v["type"] in _COSMETIC:
            continue
        where = re.sub(r"\s+", " ", " ".join(it.get("description", "") for it in v.get("items", [])))
        isf = cec_dispatch._locus_is_finishing({"type": v["type"], "where": where})
        try:
            p = v["items"][0]["pos"]
            c = (X(p["x"]), Y(p["y"]))
        except Exception:
            continue
        if isf:
            r = 8
            g.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], outline=(110, 110, 110), width=2)
            fin += 1
        else:
            r = 11
            g.line([(c[0] - r, c[1] - r), (c[0] + r, c[1] + r)], fill=(230, 0, 0), width=3)
            g.line([(c[0] - r, c[1] + r), (c[0] + r, c[1] - r)], fill=(230, 0, 0), width=3)
            real += 1

    from PIL.ImageDraw import Draw  # noqa: F401
    items = [((214, 40, 40), "F.Cu track"), ((40, 90, 214), "B.Cu track"), ((35, 35, 35), "via"),
             ((255, 178, 76), "LOGO copper"), ((230, 0, 0), "REAL short = %d" % real),
             ((140, 140, 140), "finishing/false = %d" % fin)]
    lx, ly0, f = W - 250, top + 10, _font(15, False)
    g.rectangle([lx - 10, ly0 - 8, W - 8, ly0 + 20 * len(items)], fill=(255, 255, 255), outline=(0, 0, 0))
    for i, (col, lab) in enumerate(items):
        yy = ly0 + i * 20
        if "REAL" in lab:
            g.line([(lx, yy + 3), (lx + 14, yy + 13)], fill=col, width=3)
            g.line([(lx, yy + 13), (lx + 14, yy + 3)], fill=col, width=3)
        else:
            g.rectangle([lx, yy + 3, lx + 14, yy + 13], fill=col, outline=(60, 60, 60))
        g.text((lx + 22, yy), lab, fill=(0, 0, 0), font=f)

    im.save(out_png)
    return out_png


def render_3d(board_path, out_png, side="top"):
    subprocess.run(["kicad-cli", "pcb", "render", "-o", out_png, "--side", side,
                    "--quality", "high", "--background", "opaque", "-w", "1600", "-h", "1100", board_path],
                   capture_output=True)
    return out_png if os.path.isfile(out_png) else None


if __name__ == "__main__":
    bp = sys.argv[1]
    copper_plot(bp, sys.argv[2] if len(sys.argv) > 2 else "copper.png")
