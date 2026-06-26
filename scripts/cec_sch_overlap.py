#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_sch_overlap -- a "DRC for schematic readability": find where symbol bodies and TEXT
# (references, values, net labels, global/hier labels, power-port text, free text) overlap,
# so the generator (cec_sch_hier) and a human can SEE and FIX the clutter. Pure geometry off
# the .kicad_sch s-expr -- no KiCad needed.
#
#   from cec_sch_overlap import overlaps_in_file, plot
#   bad = overlaps_in_file("block_U1.kicad_sch")          # list of overlapping pairs
#   plot("block_U1.kicad_sch", "overlap_U1.png", bad)     # boxes map, overlaps in red
#
#   .venv/bin/python scripts/cec_sch_overlap.py eps-8pin  # report+map every hier sheet
import argparse, glob, math, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAR_W = 0.95        # stroke-font advance / glyph height (KiCad ~1.0 incl. inter-char gap)
PAD = 0.12           # shrink every box this much so a clean abut isn't flagged


# ---- a small s-expression parser (KiCad files are well-formed) -----------------------------
def parse_sexp(text):
    toks = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', text)
    pos = 0

    def build():
        nonlocal pos
        node = []
        while pos < len(toks):
            t = toks[pos]; pos += 1
            if t == '(':
                node.append(build())
            elif t == ')':
                return node
            else:
                node.append(t.strip('"') if t.startswith('"') else t)
        return node
    while pos < len(toks) and toks[pos] != '(':
        pos += 1
    pos += 1
    return build()


def _children(node, tag):
    return [c for c in node if isinstance(c, list) and c and c[0] == tag]


def _child(node, tag):
    for c in node:
        if isinstance(c, list) and c and c[0] == tag:
            return c
    return None


def _at(node):
    a = _child(node, "at")
    if not a:
        return None
    rot = float(a[3]) if len(a) > 3 else 0.0
    return float(a[1]), float(a[2]), rot


def _font_h(node):
    eff = _child(node, "effects")
    if eff:
        font = _child(eff, "font")
        if font:
            sz = _child(font, "size")
            if sz:
                return float(sz[2])
    return 1.27


def _hidden(node):
    eff = _child(node, "effects")
    return bool(eff and any(c == "hide" or (isinstance(c, list) and c[:2] == ["hide", "yes"]) for c in eff))


def _justify(node):
    eff = _child(node, "effects")
    j = _child(eff, "justify") if eff else None
    return set(j[1:]) if j else set()


def _text_box(s, x, y, rot, h, just):
    """Approximate axis-aligned bbox (x0,y0,x1,y1) of a text string anchored at (x,y)."""
    w = max(len(s), 1) * h * CHAR_W
    horiz = (round(rot) % 180) == 0
    ex, ey = (w, h) if horiz else (h, w)
    # horizontal placement from justify on the long axis
    if "left" in just:
        x0, x1 = x, x + ex
    elif "right" in just:
        x0, x1 = x - ex, x
    else:
        x0, x1 = x - ex / 2, x + ex / 2
    y0, y1 = y - ey / 2, y + ey / 2
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _body_boxes(root):
    """lib_id -> local body bbox (minx,miny,maxx,maxy) from its lib_symbols rectangles."""
    out = {}
    libs = _child(root, "lib_symbols")
    if not libs:
        return out
    for sym in _children(libs, "symbol"):
        name = sym[1]
        xs, ys = [], []
        stack = [sym]
        while stack:
            n = stack.pop()
            for c in n:
                if isinstance(c, list):
                    if c and c[0] == "rectangle":
                        s, e = _child(c, "start"), _child(c, "end")
                        if s and e:
                            xs += [float(s[1]), float(e[1])]
                            ys += [float(s[2]), float(e[2])]
                    else:
                        stack.append(c)
        if xs:
            out[name] = (min(xs), min(ys), max(xs), max(ys))
    return out


def elements(sch_path):
    return elements_text(open(sch_path).read())


def elements_text(text):
    """Every drawable element: {kind, owner, text, box, origin?}. box is abs (x0,y0,x1,y1) mm;
    origin is the owning symbol's (x,y) for movable value/reference text."""
    root = parse_sexp(text)
    bodies = _body_boxes(root)
    els = []
    for node in root:
        if not isinstance(node, list) or not node:
            continue
        tag = node[0]
        if tag == "symbol":
            lib = _child(node, "lib_id")
            at = _at(node)
            if not lib or not at:
                continue
            x, y, rot = at
            ref = ""
            for p in _children(node, "property"):
                if p[1] == "Reference":
                    ref = p[2]
            bb = bodies.get(lib[1])
            if bb:                                   # body box rotated + Y-flipped to abs
                pts = []
                for cx in (bb[0], bb[2]):
                    for cy in (bb[1], bb[3]):
                        r = math.radians(rot)
                        rx = cx * math.cos(r) - cy * math.sin(r)
                        ry = cx * math.sin(r) + cy * math.cos(r)
                        pts.append((x + rx, y - ry))
                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                els.append({"kind": "body", "owner": ref, "text": ref,
                            "box": (min(xs), min(ys), max(xs), max(ys))})
            for p in _children(node, "property"):    # Reference / Value text
                if p[1] in ("Reference", "Value") and not _hidden(p) and p[2]:
                    pa = _at(p)
                    if pa:
                        els.append({"kind": p[1].lower(), "owner": ref, "text": p[2],
                                    "origin": (x, y), "field": p[1],
                                    "box": _text_box(p[2], pa[0], pa[1], pa[2], _font_h(p), _justify(p))})
        elif tag in ("label", "global_label", "hierarchical_label", "text"):
            at = _at(node)
            if at and len(node) > 1 and isinstance(node[1], str):
                s = node[1]
                els.append({"kind": tag, "owner": s, "text": s,
                            "box": _text_box(s, at[0], at[1], at[2], _font_h(node), _justify(node))})
    return els


def _hit(a, b):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ax0 += PAD; ay0 += PAD; ax1 -= PAD; ay1 -= PAD
    bx0 += PAD; by0 += PAD; bx1 -= PAD; by1 -= PAD
    ix = min(ax1, bx1) - max(ax0, bx0)
    iy = min(ay1, by1) - max(ay0, by0)
    return ix * iy if (ix > 0 and iy > 0) else 0.0


def overlaps_in(els):
    """Pairs of elements whose boxes overlap. Skips a symbol's own ref/value vs its own body
    (expected) and body-vs-body of the SAME ref. Returns [(a, b, area)] sorted worst-first."""
    out = []
    for i in range(len(els)):
        for j in range(i + 1, len(els)):
            a, b = els[i], els[j]
            if a["owner"] and a["owner"] == b["owner"] and "body" in (a["kind"], b["kind"]):
                continue                              # a part's own label sitting on itself
            area = _hit(a["box"], b["box"])
            if area > 0.4:
                out.append((a, b, round(area, 2)))
    return sorted(out, key=lambda t: -t[2])


def overlaps_in_file(sch_path):
    return overlaps_in(elements(sch_path))


def _move_field(text, ref, field, nx, ny):
    """Rewrite the (at) of one symbol's Value/Reference property, scoped to its block."""
    import cec_sch as C
    for m in re.finditer(r'\n\t\(symbol\n', text):
        s = m.start() + 1
        blk = C.carve(text, s)
        if re.search(r'\(property "Reference" "%s"' % re.escape(ref), blk):
            newblk = re.sub(
                r'(\(property "%s" "[^"]*"\s*)\(at [^)]*\)' % re.escape(field),
                lambda pm: f'{pm.group(1)}(at {C.f(nx)} {C.f(ny)} 0)', blk, count=1)
            return text[:s] + newblk + text[s + len(blk):]
    return text


_OFFS = [(dx, dy) for d in (8.89, 12.7, 17.78, 22.86, 27.94, 33.02, 38.1, 45.72)
         for dx, dy in ((0, -d), (0, d), (-d, 0), (d, 0), (-d, -d), (d, -d), (-d, d), (d, d))]


def fix_file(sch_path, max_moves=120):
    """Move VALUE/REFERENCE text (free text -- never labels, so connectivity is untouched) to
    the nearest clear spot: out of FOREIGN overlaps AND off the symbol's OWN body (default
    offsets land inside a big IC, over its pin names). Each field moves at most once (so it
    terminates); unplaceable fields are skipped, not aborted. Returns (before, after) counts."""
    text = open(sch_path).read()
    before = len(overlaps_in(elements_text(text)))
    tried = set()
    for _ in range(max_moves):
        els = elements_text(text)
        own_body = {o["owner"]: o["box"] for o in els if o["kind"] == "body"}
        flagged = set()
        for a, b, _ in overlaps_in(els):
            flagged |= {id(a), id(b)}

        def need(e):
            if not e.get("origin") or (e["owner"], e["field"]) in tried:
                return 0.0
            foreign = max((_hit(e["box"], o["box"]) for o in els if o is not e and o["owner"] != e["owner"]),
                          default=0.0)
            own = _hit(e["box"], own_body.get(e["owner"], (0, 0, 0, 0)))
            return (foreign if id(e) in flagged else 0.0) + own
        movable = [(need(e), e) for e in els]
        movable = [(s, e) for s, e in movable if s > 0.4]
        if not movable:
            break
        _, e = max(movable, key=lambda se: se[0])
        ox, oy = e["origin"]
        h = e["box"][3] - e["box"][1] or 1.27
        others = [o["box"] for o in els if o is not e]
        placed = next(((ox + dx, oy + dy) for dx, dy in _OFFS
                       if not any(_hit(_text_box(e["text"], ox + dx, oy + dy, 0, h, set()), ob) > 0.1
                                  for ob in others)), None)
        tried.add((e["owner"], e["field"]))          # at most one move per field -> terminates
        if placed:
            text = _move_field(text, e["owner"], e["field"], *placed)
    open(sch_path, "w").write(text)
    return before, len(overlaps_in(elements_text(text)))


def plot(sch_path, out_png, bad=None, width=1500):
    from PIL import Image, ImageDraw, ImageFont
    els = elements(sch_path)
    bad = overlaps_in(els) if bad is None else bad
    flagged = set()
    for a, b, _ in bad:
        flagged.add(id(a)); flagged.add(id(b))
    xs = [e["box"][0] for e in els] + [e["box"][2] for e in els]
    ys = [e["box"][1] for e in els] + [e["box"][3] for e in els]
    if not xs:
        return None
    minx, miny, maxx, maxy = min(xs) - 4, min(ys) - 4, max(xs) + 4, max(ys) + 4
    sc = width / (maxx - minx)
    W, H = int((maxx - minx) * sc), int((maxy - miny) * sc) + 30
    im = Image.new("RGB", (W, H), (255, 255, 255))
    g = ImageDraw.Draw(im, "RGBA")
    try:
        f = ImageFont.truetype("arial.ttf", 11)
    except Exception:
        f = ImageFont.load_default()
    X = lambda v: (v - minx) * sc
    Y = lambda v: (v - miny) * sc + 30
    g.text((8, 8), f"{os.path.basename(sch_path)}  overlaps={len(bad)}", fill=(0, 0, 0), font=f)
    col = {"body": (120, 120, 120), "reference": (40, 120, 40), "value": (40, 120, 40)}
    for e in els:
        x0, y0, x1, y1 = e["box"]
        bad_el = id(e) in flagged
        c = (220, 0, 0) if bad_el else col.get(e["kind"], (60, 90, 200))
        g.rectangle([X(x0), Y(y0), X(x1), Y(y1)], outline=c, width=2 if bad_el else 1,
                    fill=(220, 0, 0, 40) if bad_el else None)
    for a, b, _ in bad:                               # red link between overlapping pair centers
        ca = ((a["box"][0] + a["box"][2]) / 2, (a["box"][1] + a["box"][3]) / 2)
        cb = ((b["box"][0] + b["box"][2]) / 2, (b["box"][1] + b["box"][3]) / 2)
        g.line([X(ca[0]), Y(ca[1]), X(cb[0]), Y(cb[1])], fill=(220, 0, 0, 160), width=1)
    im.save(out_png)
    return out_png


def _sheets(board):
    if board.endswith(".kicad_sch") and os.path.isfile(board):
        return [board]
    d = os.path.join(ROOT, "build", "sch-hier")
    cands = glob.glob(os.path.join(d, "*", f"*{board.split('-')[0]}*hier.kicad_sch"))
    base = os.path.dirname(cands[0]) if cands else None
    if not base:
        base = next((p for p in glob.glob(os.path.join(d, "*")) if os.path.isdir(p)), None)
    return sorted(glob.glob(os.path.join(base, "*.kicad_sch"))) if base else []


def main(argv=None):
    ap = argparse.ArgumentParser(description="Detect symbol/text overlaps in schematic sheets.")
    ap.add_argument("board", help="board name (hier sheets under build/sch-hier) or a .kicad_sch path")
    ap.add_argument("--plot", action="store_true", help="also write an overlap map per sheet")
    ap.add_argument("--fix", action="store_true", help="relocate overlapping value/ref text in place")
    a = ap.parse_args(argv)
    sheets = _sheets(a.board)
    if not sheets:
        print(f"no sheets for {a.board!r}"); return 1
    total = 0
    for s in sheets:
        if a.fix:
            b0, b1 = fix_file(s)
            print(f"{os.path.basename(s):34} fix: {b0:3} -> {b1:3} overlaps")
            total += b1
            if a.plot:
                plot(s, os.path.join(os.path.dirname(s), "_overlap_" +
                                     os.path.splitext(os.path.basename(s))[0] + ".png"))
            continue
        bad = overlaps_in_file(s)
        total += len(bad)
        tag = "  ".join(f"{a_['kind']}:{a_['text'][:10]!r}/{b_['kind']}:{b_['text'][:10]!r}"
                        for a_, b_, _ in bad[:4])
        print(f"{os.path.basename(s):34} overlaps={len(bad):3}   {tag}")
        if a.plot:
            out = os.path.join(os.path.dirname(s), "_overlap_" +
                               os.path.splitext(os.path.basename(s))[0] + ".png")
            plot(s, out, bad)
    print(f"TOTAL overlaps across {len(sheets)} sheets: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
