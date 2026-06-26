#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_thermal_plot -- overlay the analytic electrothermal FEM (cec_synth_pipeline.
# electrothermal_solve) onto a board-accurate copper plot, so an agent/human can SEE
# the hot spots in-project. The board-side companion to cec_sch_review: render the
# physics as a heatmap rather than reading a JSON of per-net dT.
#
# Each high-current net's copper (tracks + filled pours) is colored by its temperature;
# vias inherit their net's heat; the RS* shunt dissipators are marked at their footprint
# with their I^2R temperature; signal/zero-current copper is drawn faint for context. A
# colorbar + a header (max_T / max_dT / ambient, ADVISORY-uncalibrated per AM-04) + a
# side table of the hottest nets / worst vias / shunts complete the picture.
#
# Run on a ROUTED + POURED board (thermal is meaningless on a bare floorplan):
#   .venv/bin/python scripts/cec_thermal_plot.py build/route/eps-8pin/eps-8pin-routed.kicad_pcb \
#         --board eps-8pin --metric T
import argparse, os, sys

import pcbnew
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_synth_pipeline as sp

_RAMP = [(0.00, (40, 70, 200)), (0.25, (30, 170, 205)), (0.50, (45, 180, 70)),
         (0.75, (240, 200, 40)), (1.00, (220, 45, 40))]   # blue->cyan->green->yellow->red


def _heat(t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    for (a, ca), (b, cb) in zip(_RAMP, _RAMP[1:]):
        if t <= b:
            f = (t - a) / (b - a) if b > a else 0.0
            return tuple(int(round(ca[i] + (cb[i] - ca[i]) * f)) for i in range(3))
    return _RAMP[-1][1]


def _mm(v):
    return v / 1e6


def _font(sz, bold=True):
    for n in (("arialbd.ttf",) if bold else ("arial.ttf",)):
        try:
            return ImageFont.truetype(n, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def thermal_plot(board_path, out_png, *, board=None, res=None, metric="T",
                 width=1700, net_currents=None, cable_current=None, ambient=None, title=None):
    """Render board_path's copper colored by the electrothermal result. metric: 'T'
    (absolute °C) or 'dT' (rise over ambient). cable_current overrides the per-cable A
    (set it to the per-PIN current on per-pin boards like the 12VHPWR). Returns (out_png, res)."""
    if res is None:
        cfg = sp.Config.load(board or board_path)
        if net_currents:
            cfg.params["net_currents"] = net_currents
        if cable_current is not None:
            cfg.params["cable_current_A"] = cable_current
        res = sp.electrothermal_solve(board_path, cfg, ambient=ambient)

    b = pcbnew.LoadBoard(board_path)
    bb = b.GetBoardEdgesBoundingBox()
    minx, miny = _mm(bb.GetLeft()) - 3, _mm(bb.GetTop()) - 3
    maxx, maxy = _mm(bb.GetRight()) + 3, _mm(bb.GetBottom()) + 3
    scale = width / (maxx - minx)
    top, sidebar = 78, 320
    W = int((maxx - minx) * scale) + sidebar
    H = int((maxy - miny) * scale) + top
    im = Image.new("RGB", (W, H), (252, 252, 252))
    g = ImageDraw.Draw(im)
    heat = Image.new("RGBA", (W, H), (0, 0, 0, 0))     # translucent copper-heat overlay
    hg = ImageDraw.Draw(heat)

    def X(x):
        return (x - minx) * scale

    def Y(y):
        return (y - miny) * scale + top

    def P(pt):
        return (X(_mm(pt.x)), Y(_mm(pt.y)))

    # --- value range over the metric -------------------------------------------------
    field = {n: d.get("T_peak", d.get("T")) if metric == "T" else d.get("dT_transient", 0) + d.get("dT", 0)
             for n, d in res.nets.items()}
    vmin = res.ambient if metric == "T" else 0.0
    vmax = (res.max_T if metric == "T" else res.max_dT) or (vmin + 1.0)
    if vmax <= vmin:
        vmax = vmin + 1.0

    def colof(net):
        v = field.get(net)
        return None if v is None else _heat((v - vmin) / (vmax - vmin))

    # --- header ----------------------------------------------------------------------
    g.text((12, 8), title or "thermal: " + os.path.basename(board_path), fill=(0, 0, 0), font=_font(22))
    g.text((12, 40), f"metric={metric}   ambient {res.ambient:.0f}°C   "
                     f"max_T {res.max_T:.1f}°C   max_dT {res.max_dT:.1f}°C   "
                     f"[{res.calibration}, ADVISORY analytic IPC model]",
           fill=(90, 90, 90), font=_font(15, False))

    # --- board outline ---------------------------------------------------------------
    for s in b.GetDrawings():
        if s.GetLayer() != pcbnew.Edge_Cuts:
            continue
        try:
            if s.GetShape() == pcbnew.SHAPE_T_RECT:
                a, c = P(s.GetStart()), P(s.GetEnd())
                g.rectangle([min(a[0], c[0]), min(a[1], c[1]), max(a[0], c[0]), max(a[1], c[1])],
                            outline=(0, 0, 0), width=2)
            else:
                g.line([P(s.GetStart()), P(s.GetEnd())], fill=(0, 0, 0), width=2)
        except Exception:
            pass

    # --- filled pours: the dominant high-current copper, colored by net heat ---------
    for z in b.Zones():
        col = colof(z.GetNetname())
        if col is None:
            continue
        for layer in z.GetLayerSet().Seq():
            try:
                poly = z.GetFilledPolysList(layer)
            except Exception:
                continue
            for oi in range(poly.OutlineCount()):
                ol = poly.Outline(oi)
                pts = [(X(_mm(ol.CPoint(i).x)), Y(_mm(ol.CPoint(i).y))) for i in range(ol.PointCount())]
                if len(pts) >= 3:
                    hg.polygon(pts, fill=col + (120,))

    # --- tracks: heat color for current-carrying nets, faint grey otherwise ----------
    vias = []
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_TRACE_T:
            col = colof(t.GetNetname())
            w = max(1, int(round(_mm(t.GetWidth()) * scale)))
            if col is None:
                g.line([P(t.GetStart()), P(t.GetEnd())], fill=(205, 205, 205), width=w)
            else:
                hg.line([P(t.GetStart()), P(t.GetEnd())], fill=col + (235,), width=w)
        elif t.Type() == pcbnew.PCB_VIA_T:
            try:
                dia = _mm(t.GetWidth(t.TopLayer()))
            except Exception:
                dia = 0.6
            vias.append((P(t.GetPosition()), dia * scale / 2, colof(t.GetNetname())))

    im = Image.alpha_composite(im.convert("RGBA"), heat).convert("RGB")
    g = ImageDraw.Draw(im)

    for c, r, col in vias:
        g.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=(col or (60, 60, 60)),
                  outline=(25, 25, 25))

    # --- shunt dissipators: mark at the footprint with their I^2R temperature --------
    sh_by_ref = {s["ref"]: s for s in res.shunts}
    for fp in b.GetFootprints():
        s = sh_by_ref.get(fp.GetReference())
        if not s:
            continue
        c = P(fp.GetPosition())
        col = _heat((s["T"] - vmin) / (vmax - vmin)) if metric == "T" else _heat(s["dT"] / vmax)
        g.ellipse([c[0] - 9, c[1] - 9, c[0] + 9, c[1] + 9], outline=(20, 20, 20), width=2, fill=col)
        g.text((c[0] + 12, c[1] - 8), f"{s['ref']} {s['T']:.0f}°C ({s['P_W']:.2f}W)",
               fill=(20, 20, 20), font=_font(14, True))

    _legend(im, W, sidebar, top, H, res, metric, vmin, vmax)
    im.save(out_png)
    return out_png, res


def _legend(im, W, sidebar, top, H, res, metric, vmin, vmax):
    g = ImageDraw.Draw(im)
    x0 = W - sidebar + 14
    # vertical colorbar
    bx, by, bw, bh = x0, top + 16, 26, 240
    for i in range(bh):
        t = 1.0 - i / (bh - 1)
        g.line([(bx, by + i), (bx + bw, by + i)], fill=_heat(t))
    g.rectangle([bx, by, bx + bw, by + bh], outline=(0, 0, 0))
    unit = "°C" if metric == "T" else "°C rise"
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        v = vmin + (vmax - vmin) * frac
        yy = by + int((1 - frac) * (bh - 1))
        g.line([(bx + bw, yy), (bx + bw + 5, yy)], fill=(0, 0, 0))
        g.text((bx + bw + 9, yy - 7), f"{v:.0f}", fill=(0, 0, 0), font=_font(13, False))
    g.text((bx, by - 16), f"{metric} ({unit})", fill=(0, 0, 0), font=_font(14, True))

    # side table: hottest nets, worst vias, shunts
    ty = by + bh + 24
    f, fb = _font(13, False), _font(14, True)

    def row(label, val, col=None):
        nonlocal ty
        if col:
            g.rectangle([x0, ty + 2, x0 + 11, ty + 13], fill=col, outline=(60, 60, 60))
        g.text((x0 + (16 if col else 0), ty), label, fill=(0, 0, 0), font=f)
        if val is not None:
            g.text((x0 + 200, ty), val, fill=(0, 0, 0), font=f)
        ty += 18

    g.text((x0, ty), "hottest nets", fill=(0, 0, 0), font=fb); ty += 20
    hot = sorted(res.nets.items(), key=lambda kv: -(kv[1].get("T_peak", kv[1]["T"])))[:7]
    for net, d in hot:
        T = d.get("T_peak", d["T"])
        col = _heat((T - vmin) / (vmax - vmin)) if metric == "T" else _heat(d["dT"] / vmax)
        row(net.rsplit("/", 1)[-1][:22], f"{T:.0f}°C  {d['J']:.0f}A/mm2", col)
    if res.shunts:
        ty += 6; g.text((x0, ty), "shunts (I^2R)", fill=(0, 0, 0), font=fb); ty += 20
        for s in sorted(res.shunts, key=lambda s: -s["T"])[:4]:
            row(f"{s['ref']} {s['I']:.0f}A", f"{s['T']:.0f}°C  {s['P_W']:.2f}W")
    if res.vias:
        ty += 6; g.text((x0, ty), "worst vias", fill=(0, 0, 0), font=fb); ty += 20
        for v in res.vias[:4]:
            row(f"{v['net'].rsplit('/',1)[-1][:14]}", f"{v['T']:.0f}°C  {v.get('J',0):.0f}A/mm2")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Heatmap a routed board from the electrothermal FEM.")
    ap.add_argument("board_path", help="path to a ROUTED + POURED .kicad_pcb")
    ap.add_argument("--board", default=None, help="module name for Config (defaults to board_path's dir)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--metric", choices=["T", "dT"], default="T")
    ap.add_argument("--width", type=int, default=1700)
    ap.add_argument("--ambient", type=float, default=None)
    ap.add_argument("--cable-current", type=float, default=None,
                    help="per-cable A (use the per-PIN current on per-pin boards, e.g. 9.2 for 12VHPWR)")
    a = ap.parse_args(argv)
    out = a.out or os.path.join(ROOT, "build", "thermal",
                                os.path.splitext(os.path.basename(a.board_path))[0] + f".{a.metric}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    out, res = thermal_plot(a.board_path, out, board=a.board, metric=a.metric,
                            width=a.width, ambient=a.ambient, cable_current=a.cable_current)
    print(f"thermal plot: {os.path.relpath(out, ROOT)}")
    print(f"max_T {res.max_T}°C  max_dT {res.max_dT}°C  ambient {res.ambient}°C  "
          f"nets {len(res.nets)}  vias {len(res.vias)}  shunts {len(res.shunts)}  [{res.calibration}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
