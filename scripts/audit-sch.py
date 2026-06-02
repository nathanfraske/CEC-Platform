#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Static connectivity audit for generated .kicad_sch files, without kicad-cli.
# Reconstructs every placed pin's absolute position from the library symbols and
# checks the geometry that KiCad ERC cares about and that bit us before:
#
#   - no_connect must sit exactly on a pin             (else: no_connect_dangling)
#   - label must sit on a pin or a wire endpoint       (else: label_dangling)
#   - each wire endpoint must hit a pin, a label, or    (else: unconnected_wire_endpoint)
#     another wire endpoint
#   - every wire end / label / no_connect is on the 1.27 mm grid (else: endpoint_off_grid)
#
# Exit 0 if all audited sheets are clean, 1 otherwise. This is a regression guard
# for the generators, NOT a replacement for `kicad-cli sch erc`.
#
#   python3 scripts/audit-sch.py [sheet.kicad_sch ...]   # default: hubs + modules
import re, math, sys, glob, os

G = 1.27
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def carve(t, i):
    d = 0; ins = esc = False; j = i
    while j < len(t):
        c = t[j]
        if ins:
            if esc: esc = False
            elif c == '\\': esc = True
            elif c == '"': ins = False
        else:
            if c == '"': ins = True
            elif c == '(': d += 1
            elif c == ')':
                d -= 1
                if d == 0: return t[i:j+1]
        j += 1

_LIBS = {}
def libs():
    if not _LIBS:
        for p in glob.glob(f"{ROOT}/lib/*.kicad_sym") + glob.glob(f"{ROOT}/lib/vendor/*.kicad_sym"):
            _LIBS[p] = open(p).read()
    return _LIBS

def find_sym(name):
    for t in libs().values():
        i = t.find(f'(symbol "{name}"')
        if i >= 0:
            return carve(t, i)
    return None

def lib_pins(block):
    out = {}
    for m in re.finditer(r'\(pin\s+\w+\s+\w+\s*\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\)', block):
        seg = block[m.start():m.start()+260]
        num = re.search(r'\(number "([^"]+)"', seg)
        if num:
            out[num.group(1)] = (float(m.group(1)), float(m.group(2)), int(m.group(3)))
    return out

def sym_body_box(block):
    """Body bounding box from rectangles only (drawn outline) — wire keep-out."""
    xs, ys = [], []
    for m in re.finditer(r'\(rectangle\s*\(start\s+(-?[\d.]+)\s+(-?[\d.]+)\)\s*\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\)', block):
        xs += [float(m.group(1)), float(m.group(3))]
        ys += [float(m.group(2)), float(m.group(4))]
    return (min(xs), max(xs), min(ys), max(ys)) if xs else None

def seg_hits_box(x1, y1, x2, y2, box, pad=-0.2):
    """True if axis-aligned segment intersects rect box (shrunk by pad so a wire
    grazing the body edge to reach a pin is allowed)."""
    bx0, bx1, by0, by1 = box[0]-pad, box[1]+pad, box[2]-pad, box[3]+pad
    if abs(y1-y2) < 1e-6:
        if not (by0 <= y1 <= by1): return False
        lo, hi = sorted((x1, x2)); return not (hi <= bx0 or lo >= bx1)
    if abs(x1-x2) < 1e-6:
        if not (bx0 <= x1 <= bx1): return False
        lo, hi = sorted((y1, y2)); return not (hi <= by0 or lo >= by1)
    return False

def ongrid(x, y):
    return abs((x/G)-round(x/G)) < 1e-6 and abs((y/G)-round(y/G)) < 1e-6

def R(v):
    return round(v, 3)

def sym_extent(block):
    """Local bounding box (minx,maxx,miny,maxy) from pins + body rectangles."""
    xs, ys = [], []
    for m in re.finditer(r'\(pin\s+\w+\s+\w+\s*\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\)', block):
        xs.append(float(m.group(1))); ys.append(float(m.group(2)))
    for m in re.finditer(r'\(rectangle\s*\(start\s+(-?[\d.]+)\s+(-?[\d.]+)\)\s*\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\)', block):
        xs += [float(m.group(1)), float(m.group(3))]
        ys += [float(m.group(2)), float(m.group(4))]
    if not xs:
        return (0, 0, 0, 0)
    return (min(xs), max(xs), min(ys), max(ys))

def audit(path):
    s = open(path).read()
    # --- KiCad structural invariants (a violation here is what crashes the GUI
    #     on save, even though ERC/connectivity look fine) ---
    top = re.search(r'\(uuid\s+"?([0-9a-fA-F-]{36})"?\)', s)
    top_uuid = top.group(1) if top else None
    bare_uuid = re.findall(r'\(uuid\s+[0-9a-fA-F][0-9a-fA-F-]{35}\s*\)', s)  # unquoted
    inst = re.findall(r'\(project "([^"]*)"\s*\(path "([^"]+)"\s*\(reference "([^"]+)"', s)
    want_path = "/" + (top_uuid or "")
    inst_bad = [(proj, p, ref) for (proj, p, ref) in inst
                if p != want_path or proj == ""]
    # Every instantiated symbol must have its definition cached in the sheet's
    # (lib_symbols ...) block. A missing one renders as a "??" placeholder box in
    # eeschema (pins/graphics absent), even though connectivity/instances look ok.
    _li = s.find("(lib_symbols")
    _libsec = ""
    if _li >= 0:
        _d = 0
        for _j in range(_li, len(s)):
            if s[_j] == '(': _d += 1
            elif s[_j] == ')':
                _d -= 1
                if _d == 0:
                    _libsec = s[_li:_j+1]; break
    _embedded = set(re.findall(r'\n\t\t\(symbol "([^"]+)"', _libsec))
    _used = set(re.findall(r'\(lib_id "([^"]+)"\)', s))
    missing_lib_symbol = sorted(_used - _embedded)
    pin_pts = set()
    boxes = []        # (ref, x0, x1, y0, y1) absolute, for overlap detection
    body_boxes = []   # (x0, x1, y0, y1) body rectangles only, wire keep-outs
    for m in re.finditer(r'\(symbol\n\t\t\(lib_id "([^"]+)"\)\n\t\t\(at (-?[\d.]+) (-?[\d.]+) (\d+)\)(.*?)\n\t\)', s, re.S):
        libid, ox, oy, rot, tail = m.group(1), float(m.group(2)), float(m.group(3)), int(m.group(4)), m.group(5)
        lib_ns, _, name = libid.partition(":")
        # power symbols (PWR_FLAG, GND, +3V3, +5VSB ...) are 1-pin, pin at origin.
        # Our vendored library uses the cec-power nickname; KiCad's built-in is
        # power. Accept both.
        if lib_ns in ("power", "cec-power"):
            pin_pts.add((R(ox), R(oy))); continue
        blk = find_sym(name)
        if not blk:
            return None, [f"library symbol not found: {name}"]
        ca, sa = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        # Hand layouts rotate/mirror symbols, so transform every local coord
        # (pins AND extents) by mirror-then-rotate, not just the pins.
        mir = re.search(r'\(mirror (\w+)\)', tail)
        mir = mir.group(1) if mir else None
        def place(lx, ly):
            if mir == 'y': lx = -lx
            elif mir == 'x': ly = -ly
            return (R(ox + (lx*ca - ly*sa)), R(oy - (lx*sa + ly*ca)))
        def abox(ext):                      # rotate the 4 corners -> AA bbox
            x0, x1, y0, y1 = ext
            pts = [place(x0, y0), place(x1, y0), place(x0, y1), place(x1, y1)]
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            return (min(xs), max(xs), min(ys), max(ys))
        for _num, (lx, ly, _a) in lib_pins(blk).items():
            pin_pts.add(place(lx, ly))
        ref = re.search(r'\(property "Reference" "([^"]+)"', tail)
        bx = abox(sym_extent(blk))
        boxes.append((ref.group(1) if ref else "?", bx[0], bx[1], bx[2], bx[3]))
        bb = sym_body_box(blk)
        if bb:
            body_boxes.append(abox(bb))
    wends = []
    segs = []
    for m in re.finditer(r'\(wire \(pts \(xy (-?[\d.]+) (-?[\d.]+)\) \(xy (-?[\d.]+) (-?[\d.]+)\)\)', s):
        x1, y1, x2, y2 = (float(m.group(k)) for k in (1, 2, 3, 4))
        wends += [(R(x1), R(y1)), (R(x2), R(y2))]
        segs.append((x1, y1, x2, y2))
    labels = [(R(float(x)), R(float(y))) for x, y in
              re.findall(r'\(label "[^"]+" \(at (-?[\d.]+) (-?[\d.]+)', s)]
    ncs = [(R(float(x)), R(float(y))) for x, y in
           re.findall(r'\(no_connect \(at (-?[\d.]+) (-?[\d.]+)', s)]
    from collections import Counter
    wc = Counter(wends); lset = set(labels)
    overlaps = []
    for i in range(len(boxes)):
        for j in range(i+1, len(boxes)):
            a, b = boxes[i], boxes[j]
            # <= so edge-adjacent boxes (0-area touch, normal in dense hand
            # layouts) aren't flagged; only real positive-area overlap counts.
            if not (a[2] <= b[1] or b[2] <= a[1] or a[4] <= b[3] or b[4] <= a[3]):
                overlaps.append(f"{a[0]}&{b[0]}")
    wire_through_body = [seg for seg in segs
                         if any(seg_hits_box(*seg, b) for b in body_boxes)]
    res = {
        "no_connect_dangling": [p for p in ncs if p not in pin_pts],
        "label_dangling": [p for p in labels if p not in set(wends) and p not in pin_pts],
        "unconnected_wire_endpoint": [p for p in wends if p not in pin_pts and p not in lset and wc[p] < 2],
        "endpoint_off_grid": [p for p in (wends+labels+ncs) if not ongrid(*p)],
        "symbol_overlap": overlaps,
        "wire_through_body": wire_through_body,
        "instance_path_mismatch": inst_bad,   # crashes KiCad on save
        "bare_uuid": bare_uuid,               # KiCad 10 writes UUIDs quoted
        "missing_lib_symbol": missing_lib_symbol,  # renders as "??" in eeschema
    }
    return res, []

def main(argv):
    targets = argv[1:] or (sorted(glob.glob(f"{ROOT}/hubs/*/*.kicad_sch")) +
                           sorted(glob.glob(f"{ROOT}/modules/*/*.kicad_sch")))
    status = 0
    for path in targets:
        res, errs = audit(path)
        name = os.path.relpath(path, ROOT)
        if errs:
            print(f"FAIL {name}: {errs}"); status = 1; continue
        bad = {k: len(v) for k, v in res.items() if v}
        if bad:
            print(f"FAIL {name}: {bad}")
            for k, v in res.items():
                for p in v[:4]:
                    print(f"      {k} @ {p}")
            status = 1
        else:
            print(f"ok   {name}  (pins/labels/wires/no-connects all coincident, on-grid)")
    return status

if __name__ == "__main__":
    sys.exit(main(sys.argv))
