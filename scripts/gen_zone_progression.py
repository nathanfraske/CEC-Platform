"""zone-progression.png -- CL-24 lesson 7 made visible
(docs/auditor-verifier-disagreement-deep-dive-2026-06-11.md, "Empirical centerpiece").

The eps SENSEC2 routing loop drove its PROXY (DRC count) down 28->5 across four rounds while the
physical GOAL got worse: pour islands rose 4->7 (1/net = intact), total pour copper fell 394->352 mm2,
and cable-2 sense copper fell 197->155 mm2 (-21%). Proxy and goal move in STRICT OPPOSITION -- the
scorer's pick (round 4, lowest DRC) is the physically worst board; the human's pick (round 1) is best.
This plot draws that opposition so it reads at a glance.

Data is the deep-dive's measured table (the source of truth), kept inline with that citation.
Rendered with PIL (matplotlib is in neither the host nor the cec/routing:kicad10 image; PIL is):
    docker exec docker-routing-1 python3 /workspace/scripts/gen_zone_progression.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "fullstack-run-2026-06-11-validation", "zone-progression.png")

# deep-dive table (rounds 1-4). DRC = scorer proxy (down looks "better"); the rest = physical goal.
ROUNDS = [1, 2, 3, 4]
DRC = [28, 14, 8, 5]                  # proxy the optimizer minimized
ISLANDS = [4, 5, 6, 7]               # 1/net = intact; rising = fragmenting (WORSE)
COPPER = [394, 374, 361, 352]        # total pour copper mm2 (falling = WORSE)
CABLE2 = [197, 173, 171, 155]        # cable-2 sense copper mm2 (-21%, WORSE)
HUMAN_PICK, SCORER_PICK = 1, 4

W, H = 980, 620
M = {"l": 86, "r": 96, "t": 96, "b": 84}           # plot margins
RED, BLUE, GREEN, PURPLE, GREY, INK = (
    (192, 57, 43), (36, 113, 163), (39, 174, 96), (125, 60, 152), (86, 101, 115), (32, 32, 32))


def _font(sz, bold=False):
    for p in (f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
              f"/usr/share/fonts/truetype/liberation/LiberationSans{'-Bold' if bold else '-Regular'}.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, sz)
    return ImageFont.load_default()


def main():
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    x0, x1 = M["l"], W - M["r"]
    y0, y1 = M["t"], H - M["b"]

    def px(r):                                          # round -> x pixel
        return x0 + (r - ROUNDS[0]) / (ROUNDS[-1] - ROUNDS[0]) * (x1 - x0)

    def py_left(v, vmax=32):                             # DRC (left axis) -> y
        return y1 - v / vmax * (y1 - y0)

    def py_right(v, vmax=9):                             # islands (right axis) -> y
        return y1 - v / vmax * (y1 - y0)

    f_sm, f_md, f_lg, f_bd = _font(13), _font(15), _font(18), _font(15, bold=True)

    # axes box + round gridlines
    d.rectangle([x0, y0, x1, y1], outline=(200, 200, 200))
    for r in ROUNDS:
        d.line([(px(r), y0), (px(r), y1)], fill=(238, 238, 238))
        d.text((px(r), y1 + 8), f"round {r}", font=f_sm, fill=INK, anchor="ma")
    # left ticks (DRC)
    for v in (0, 8, 16, 24, 32):
        d.text((x0 - 8, py_left(v)), str(v), font=f_sm, fill=RED, anchor="rm")
    # right ticks (islands)
    for v in (0, 3, 6, 9):
        d.text((x1 + 8, py_right(v)), str(v), font=f_sm, fill=BLUE, anchor="lm")

    # pick markers
    for r, col, lbl in ((HUMAN_PICK, GREEN, "human pick\n(best board)"),
                        (SCORER_PICK, PURPLE, "scorer pick\n(lowest DRC,\nworst pours)")):
        d.line([(px(r), y0), (px(r), y1)], fill=col + (0,))
        for dy in range(y0, y1, 10):                    # dotted vertical
            d.line([(px(r), dy), (px(r), dy + 4)], fill=col, width=1)
        anch = "la" if r == HUMAN_PICK else "ra"
        d.multiline_text((px(r) + (6 if r == HUMAN_PICK else -6), y0 + 4), lbl,
                         font=f_sm, fill=col, anchor=anch, spacing=2)

    # DRC line (proxy)
    drc_pts = [(px(r), py_left(v)) for r, v in zip(ROUNDS, DRC)]
    d.line(drc_pts, fill=RED, width=3)
    for (x, y), v in zip(drc_pts, DRC):
        d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=RED)
        d.text((x, y - 10), str(v), font=f_bd, fill=RED, anchor="md")

    # islands line (goal) + copper annotations
    isl_pts = [(px(r), py_right(v)) for r, v in zip(ROUNDS, ISLANDS)]
    for i in range(len(isl_pts) - 1):                   # dashed
        a, b = isl_pts[i], isl_pts[i + 1]
        d.line([a, b], fill=BLUE, width=3)
    for (x, y), isl, cu, c2 in zip(isl_pts, ISLANDS, COPPER, CABLE2):
        d.rectangle([x - 5, y - 5, x + 5, y + 5], fill=BLUE)
        d.text((x, y + 9), str(isl), font=f_bd, fill=BLUE, anchor="ma")
        d.multiline_text((x, y + 28), f"Σ{cu}mm²\ncbl2 {c2}", font=f_sm, fill=GREY,
                         anchor="ma", spacing=1, align="center")

    # axis titles
    d.text((x0, y1 + 34), "DRC count (scorer proxy, ↓ = 'better')  — RED", font=f_md, fill=RED)
    d.text((x1, y1 + 34), "pour islands (1/net = intact, ↑ = fragmenting)  — BLUE",
           font=f_md, fill=BLUE, anchor="ra")
    # title
    d.text((W // 2, 26), "Proxy improves, goal degrades — the loop optimized DRC into a worse board",
           font=f_lg, fill=INK, anchor="ma")
    d.text((W // 2, 52), "CL-24 lesson 7  (eps SENSEC2 run, 2026-06-11)", font=f_md, fill=GREY, anchor="ma")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    im.save(OUT)
    print(f"wrote {os.path.relpath(OUT, ROOT)}  ({os.path.getsize(OUT)} bytes, {W}x{H})")


if __name__ == "__main__":
    main()
