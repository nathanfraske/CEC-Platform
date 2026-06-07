#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_zoomplot -- annotated FULL + ZOOM plots of a problem area, for a human decision (PIL).
# ============================================================================
# Copper (F.Cu red / B.Cu blue), vias (GND escape via = green ring), pads (numbered +
# net-labelled in the zoom), the Kelvin keepout (orange dashed), and the DRC-unconnected
# pins HIGHLIGHTED in red -- so a reviewer sees WHY a pad is boxed (its 0.5mm-pitch
# neighbours + the keepout) and can decide the fix.
#
#   python3 scripts/cec_zoomplot.py <board.kicad_pcb> <out_prefix> [zoom_ref ...]
# ============================================================================
import os, sys, json, subprocess, tempfile, re

import pcbnew
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_hc   # _kelvin_pairs_local

MM = 1e6
FCU, BCU = pcbnew.F_Cu, pcbnew.B_Cu
LCOL = {FCU: (214, 40, 40), BCU: (40, 90, 214)}


def _mm(v):
    return v / MM


def _font(sz, bold=True):
    for n in (("arialbd.ttf", "arial.ttf") if bold else ("arial.ttf",)):
        try:
            return ImageFont.truetype(n, sz)
        except Exception:
            pass
    return ImageFont.load_default()


def _unconnected(path):
    out = os.path.join(tempfile.gettempdir(), "zoom_drc_%d.json" % os.getpid())
    subprocess.run(["kicad-cli", "pcb", "drc", "--format", "json", "-o", out, path], capture_output=True)
    try:
        j = json.load(open(out))
    except Exception:
        return set()
    pins = set()
    for u in j.get("unconnected_items", []):
        for it in u.get("items", []):
            m = re.search(r"Pad (\S+) \[([^\]]+)\] of (\w+)", it.get("description", ""))
            if m:
                pins.add((m.group(3), m.group(1)))
    return pins


def _collect(board):
    pads, tracks, vias = [], [], []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            ls = p.GetLayerSet()
            pads.append(dict(ref=fp.GetReference(), pad=p.GetPadName(), net=p.GetNetname() or "",
                             l=_mm(bb.GetLeft()), t=_mm(bb.GetTop()), r=_mm(bb.GetRight()), b=_mm(bb.GetBottom()),
                             f=ls.Contains(FCU), bk=ls.Contains(BCU)))
    for tr in board.GetTracks():
        if tr.Type() == pcbnew.PCB_VIA_T:
            try:
                d = _mm(tr.GetWidth(tr.TopLayer()))
            except Exception:
                d = 0.6
            vias.append(dict(cx=_mm(tr.GetPosition().x), cy=_mm(tr.GetPosition().y), dia=d, net=tr.GetNetname() or ""))
        elif tr.Type() == pcbnew.PCB_TRACE_T:
            s, e = tr.GetStart(), tr.GetEnd()
            tracks.append(dict(x0=_mm(s.x), y0=_mm(s.y), x1=_mm(e.x), y1=_mm(e.y),
                               w=_mm(tr.GetWidth()), layer=tr.GetLayer(), net=tr.GetNetname() or ""))
    return pads, tracks, vias


def _render(pads, tracks, vias, keepouts, unconn, view, label_refs, highlight, title, out_png, px_w=1500, top=80):
    x0, y0, x1, y1 = view
    scale = px_w / (x1 - x0)
    W, H = int((x1 - x0) * scale), int((y1 - y0) * scale) + top
    im = Image.new("RGB", (W, H), (250, 250, 250))
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))            # for translucent keepout fill
    g, go = ImageDraw.Draw(im), ImageDraw.Draw(ov)

    def X(x):
        return (x - x0) * scale

    def Y(y):
        return (y - y0) * scale + top

    g.text((12, 10), title.split("\n")[0], fill=(0, 0, 0), font=_font(17))
    for i, ln in enumerate(title.split("\n")[1:]):
        g.text((12, 36 + i * 18), ln, fill=(70, 70, 70), font=_font(13, False))

    for k in keepouts:                                      # translucent orange + dashed edge
        go.rectangle([X(k[0]), Y(k[1]), X(k[2]), Y(k[3])], fill=(255, 170, 60, 32))
    im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
    g = ImageDraw.Draw(im)
    for k in keepouts:
        for yy in (Y(k[1]), Y(k[3])):
            for xx in range(int(X(k[0])), int(X(k[2])), 8):
                g.line([xx, yy, xx + 4, yy], fill=(210, 130, 0), width=1)
        for xx in (X(k[0]), X(k[2])):
            for yy in range(int(Y(k[1])), int(Y(k[3])), 8):
                g.line([xx, yy, xx, yy + 4], fill=(210, 130, 0), width=1)

    for t in tracks:                                        # tracks
        if max(t["x0"], t["x1"]) < x0 or min(t["x0"], t["x1"]) > x1 or max(t["y0"], t["y1"]) < y0 or min(t["y0"], t["y1"]) > y1:
            continue
        g.line([X(t["x0"]), Y(t["y0"]), X(t["x1"]), Y(t["y1"])], fill=LCOL.get(t["layer"], (150, 150, 150)),
               width=max(1, int(t["w"] * scale)))
    for p in pads:                                          # pads
        if p["r"] < x0 or p["l"] > x1 or p["b"] < y0 or p["t"] > y1:
            continue
        col = (222, 206, 140) if (p["f"] and p["bk"]) else ((232, 184, 184) if p["f"] else (184, 202, 236))
        boxed = (p["ref"], p["pad"]) in unconn and p["ref"] in highlight
        g.rectangle([X(p["l"]), Y(p["t"]), X(p["r"]), Y(p["b"])], fill=col,
                    outline=((210, 0, 0) if boxed else (110, 110, 110)), width=(3 if boxed else 1))
        if p["ref"] in label_refs:
            cx, cy = (X(p["l"]) + X(p["r"])) / 2, (Y(p["t"]) + Y(p["b"])) / 2
            g.text((cx, cy - 6), "%s.%s" % (p["ref"], p["pad"]), fill=(20, 20, 20), font=_font(10), anchor="mm")
            g.text((cx, cy + 6), p["net"].lstrip("/"), fill=((150, 0, 0) if boxed else (30, 30, 90)),
                   font=_font(9, False), anchor="mm")
        if boxed:
            g.text(((X(p["l"]) + X(p["r"])) / 2, Y(p["t"]) - 9), "BOXED", fill=(200, 0, 0), font=_font(10), anchor="mm")
    for v in vias:                                          # vias
        if v["cx"] < x0 or v["cx"] > x1 or v["cy"] < y0 or v["cy"] > y1:
            continue
        r = v["dia"] / 2 * scale
        isg = v["net"] == "GND"
        g.ellipse([X(v["cx"]) - r, Y(v["cy"]) - r, X(v["cx"]) + r, Y(v["cy"]) + r], fill=(35, 35, 35),
                  outline=((0, 180, 60) if isg else (90, 90, 90)), width=(3 if isg else 1))
    im.save(out_png)
    return out_png


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    path, prefix = argv[0], argv[1]
    zoom_refs = argv[2:] if len(argv) > 2 else ["U11", "RS2"]
    board = pcbnew.LoadBoard(path)
    pads, tracks, vias = _collect(board)
    unconn = _unconnected(path)
    keepouts = [(k[0] - 0.3, k[1] - 0.3, k[2] + 0.3, k[3] + 0.3) for k in cec_hc._kelvin_pairs_local(board)]
    eb = board.GetBoardEdgesBoundingBox()
    full = (_mm(eb.GetLeft()) - 2, _mm(eb.GetTop()) - 2, _mm(eb.GetRight()) + 2, _mm(eb.GetBottom()) + 2)

    # FULL
    full_png = _render(pads, tracks, vias, keepouts, unconn, full, set(), set(),
                       "EPS routed_0 -- FULL board   (F.Cu red / B.Cu blue / GND escape via = green ring / Kelvin keepout = orange)\n"
                       "the two INA238 boxed-power regions are the left (U10+RS1) and middle (U11+RS2) shunt clusters",
                       prefix + "-full.png", px_w=1700, top=60)

    # ZOOM
    zps = [p for p in pads if p["ref"] in zoom_refs]
    view = (min(p["l"] for p in zps) - 2.5, min(p["t"] for p in zps) - 3.2,
            max(p["r"] for p in zps) + 2.5, max(p["b"] for p in zps) + 3.2)
    zoom_png = _render(pads, tracks, vias, keepouts, unconn, view, set(zoom_refs),
                       {r for r in zoom_refs if r.startswith("U")},
                       "EPS routed_0 -- ZOOM %s : why the INA238 +3V3/GND are boxed in\n"
                       "red-outlined pads = DRC-UNCONNECTED (stranded);  orange dashed = Kelvin keepout (no foreign F.Cu);  green-ring via = GND escape to plane"
                       % "+".join(zoom_refs), prefix + "-zoom.png", px_w=1400, top=80)
    print(full_png)
    print(zoom_png)
    print("unconnected pins of zoom refs:", sorted(p for p in unconn if p[0] in zoom_refs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
