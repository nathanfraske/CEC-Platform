#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Shared board-render helper (owner ask 2026-07-08: silk OFF so renders are readable).

kicad-cli pcb render has no per-layer toggle headless, so no_silk renders load the board,
strip all silkscreen (footprint refs/values + silk graphics + board-level silk drawings)
from an in-memory COPY, save to a temp file, and render that. The source board is never
touched. Used by the wave snapshots, the escalator probe, and the dashboard.

CLI: python3 scripts/cec_render.py BOARD OUT [--side top|bottom] [--silk] [--timeout N]
"""
import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def render(board_path, out_png, *, side="top", no_silk=True, no_bodies=False, timeout=180):
    """Render board_path to out_png. no_silk strips silkscreen on a temp copy first.
    Returns out_png on success, None on failure. Needs pcbnew + kicad-cli (container)."""
    src = str(board_path)
    tmp = None
    try:
        if no_silk or no_bodies:
            import pcbnew
            b = pcbnew.LoadBoard(src)
            if b is None:
                return None
            silk = {pcbnew.F_SilkS, pcbnew.B_SilkS} if no_silk else set()
            # RELAYER, never Remove(): pcbnew Remove() on footprint children SEGFAULTS this
            # SWIG build (recorded footgun). The 3D render ignores user layers, so moving
            # silk items to Cmts.User hides them identically.
            for fp in b.GetFootprints():
                fp.Reference().SetVisible(False)
                fp.Value().SetVisible(False)
                for g in fp.GraphicalItems():
                    try:
                        if g.GetLayer() in silk:
                            g.SetLayer(pcbnew.Cmts_User)
                    except Exception:                      # noqa: BLE001
                        pass
            for d in b.GetDrawings():
                try:
                    if d.GetLayer() in silk:
                        d.SetLayer(pcbnew.Cmts_User)
                except Exception:                          # noqa: BLE001
                    pass
            # temp copy lives NEXT TO the source: 3D model paths are ${KIPRJMOD}-relative,
            # so a /tmp copy renders bare copper with no component bodies (measured).
            fd, tmp = tempfile.mkstemp(suffix=".kicad_pcb", prefix="cec_nosilk_",
                                       dir=os.path.dirname(os.path.abspath(src)) or None)
            os.close(fd)
            pcbnew.SaveBoard(tmp, b)
            # 3D model paths are ${KIPRJMOD}/../../lib/... (boards 2 levels below the repo
            # root). Build artifacts live at arbitrary depths, so rewrite to the absolute
            # repo lib in the DISPOSABLE copy -- bodies render from anywhere.
            root = os.path.dirname(HERE)
            doc = open(tmp).read().replace("${KIPRJMOD}/../../lib/", root + "/lib/")
            if no_bodies:
                # strip 3D model references (owner ask 2026-07-08: bodies hide the
                # copper/pads during wave review) -- s-expr (model ...) blocks removed
                # from the DISPOSABLE copy only.
                out_doc = []
                depth = 0
                i = 0
                while i < len(doc):
                    j = doc.find("(model ", i)
                    if j == -1:
                        out_doc.append(doc[i:])
                        break
                    out_doc.append(doc[i:j])
                    d = 0
                    k = j
                    while k < len(doc):
                        if doc[k] == "(":
                            d += 1
                        elif doc[k] == ")":
                            d -= 1
                            if d == 0:
                                break
                        k += 1
                    i = k + 1
                doc = "".join(out_doc)
            open(tmp, "w").write(doc)
            src = tmp
        r = subprocess.run(["kicad-cli", "pcb", "render", "-o", str(out_png),
                            "--side", side, src],
                           capture_output=True, timeout=timeout)
        return str(out_png) if (r.returncode == 0 and os.path.isfile(str(out_png))) else None
    except Exception:                                      # noqa: BLE001
        return None
    finally:
        if tmp and os.path.isfile(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("board")
    ap.add_argument("out")
    ap.add_argument("--side", default="top", choices=("top", "bottom"))
    ap.add_argument("--silk", action="store_true", help="keep silkscreen (default: stripped)")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()
    out = render(args.board, args.out, side=args.side, no_silk=not args.silk,
                 timeout=args.timeout)
    print(out or "RENDER FAILED")
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())


def hex_panel(board_path, out_png, *, side_pngs=None, timeout=300):
    """Owner ask 2026-07-15: the per-variant dash tile as a 3x2 array --
    col 1: FRONT render over BACK render (back mirrored into front orientation so
           features align across the row -- and labeled as such on-tile),
    col 2: F.Cu plot over B.Cu plot (layer 1 / layer 4, board coordinates),
    col 3: In1.Cu over In2.Cu (the inner pair),
    cells butted together with distinct divider rules. Returns out_png or None.
    Plots via kicad-cli svg + rsvg-convert (both in the routing container)."""
    import subprocess
    import tempfile
    try:
        from PIL import Image, ImageDraw, ImageOps
    except Exception:                                   # noqa: BLE001
        return None
    wd = tempfile.mkdtemp(prefix="cec_hex_")
    tiles = {}
    # 1. side renders (reuse if the caller already made them)
    for side in ("top", "bottom"):
        p = (side_pngs or {}).get(side)
        if not p or not os.path.isfile(p):
            p = os.path.join(wd, side + ".png")
            if not render(board_path, p, side=side, no_bodies=True):
                return None
        tiles[side] = p
    # 2. layer plots
    for key, layer in (("l1", "F.Cu"), ("l4", "B.Cu"), ("l2", "In1.Cu"), ("l3", "In2.Cu")):
        svg = os.path.join(wd, key + ".svg")
        r = subprocess.run(["kicad-cli", "pcb", "export", "svg", "--layers",
                            layer + ",Edge.Cuts", "--page-size-mode", "2",
                            "--exclude-drawing-sheet", "-o", svg, board_path],
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0 or not os.path.isfile(svg):
            return None
        png = os.path.join(wd, key + ".png")
        subprocess.run(["rsvg-convert", "-w", "900", "-o", png, svg],
                       capture_output=True, timeout=timeout)
        if not os.path.isfile(png):
            return None
        tiles[key] = png

    def board_crop(p):
        im = Image.open(p).convert("RGB")
        # crop the render's grey margins: board pixels are the non-background extent
        import numpy as _np
        a = _np.asarray(im).astype(int)
        bg = a[2, 2]
        mask = (abs(a - bg).sum(axis=2) > 40)
        ys, xs = _np.where(mask)
        if len(xs) < 100:
            return im
        return im.crop((xs.min(), ys.min(), xs.max(), ys.max()))

    top = board_crop(tiles["top"])
    bot = ImageOps.mirror(board_crop(tiles["bottom"]))     # into FRONT orientation
    l1 = board_crop(tiles["l1"]); l4 = board_crop(tiles["l4"])
    l2 = board_crop(tiles["l2"]); l3 = board_crop(tiles["l3"])
    CW = 760
    def fit(im):
        return im.resize((CW, int(im.height * CW / im.width)))
    cols = [(fit(top), fit(bot)), (fit(l1), fit(l4)), (fit(l2), fit(l3))]
    rowh = [max(c[0].height for c in cols), max(c[1].height for c in cols)]
    DIV = 5
    W = CW * 3 + DIV * 4
    H = sum(rowh) + DIV * 3 + 26
    out = Image.new("RGB", (W, H), (16, 18, 22))
    d = ImageDraw.Draw(out)
    labels = [("FRONT", "BACK (mirrored to front orientation)"),
              ("L1 F.Cu", "L4 B.Cu"), ("L2 In1", "L3 In2")]
    for ci, (imt, imb) in enumerate(cols):
        x = DIV + ci * (CW + DIV)
        out.paste(imt, (x, DIV))
        out.paste(imb, (x, DIV + rowh[0] + DIV))
        d.text((x + 4, DIV + 2), labels[ci][0], fill=(255, 210, 90))
        d.text((x + 4, DIV + rowh[0] + DIV + 2), labels[ci][1], fill=(255, 210, 90))
    for i in range(4):                                    # vertical rules
        x = i * (CW + DIV)
        d.rectangle([x, 0, x + DIV - 1, H], fill=(90, 95, 105))
    for y in (0, DIV + rowh[0], DIV + rowh[0] + DIV + rowh[1]):
        d.rectangle([0, y, W, y + DIV - 1], fill=(90, 95, 105))
    d.text((DIV + 4, H - 20), os.path.basename(board_path), fill=(170, 175, 185))
    out.save(out_png)
    return out_png
