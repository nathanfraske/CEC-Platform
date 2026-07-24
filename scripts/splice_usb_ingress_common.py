#!/usr/bin/env python3
# Shared helpers for the 2026-07-24 USB-ingress TPS2121 mux splice scripts
# (docs/usb-ingress-bom-delta-2026-07-24.md; spec v1.6.0 Sec 6.14 / 2.9).
#
# Built on cec_sch.py's primitives (carve/emit_symbol/emit_wire/emit_label/
# emit_global_power/pin_table). Adds the three surgical moves this delta needs
# that cec_sch.py itself does not provide, generalizing the pattern already used
# by scripts/splice_hub_rev2_polyfuse.py (remove_power_symbol_at) to also cover
# plain labels and whole-symbol deletion by refdes:
#
#   - remove_symbol(txt, ref)        delete an existing component entirely
#   - remove_terminal_at(txt, x, y)  delete whatever sits at a stub end (a
#                                    (label ...) or a power-symbol (symbol ...))
#   - rename_label_at(txt, x, y, new_name)  change a label's net name in place,
#                                    anchored by its exact coordinate so no
#                                    other same-named label elsewhere moves
#
# All of these refuse loudly (SystemExit) rather than guess, matching the
# discipline of every prior splice script in this repo.
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cec_sch  # noqa: E402

GRID = cec_sch.GRID
STUB = cec_sch.STUB
f = cec_sch.f


def gsnap(v):
    return round(v / GRID) * GRID


def carve_from_marker(txt, marker_start_idx):
    """carve() starting at a raw index that may point at leading whitespace
    (e.g. the '\\t' before '(symbol') -- carve() tolerates this (it only starts
    counting parens once it sees '(') and returns the whitespace-inclusive
    slice, exactly like every existing splice script relies on."""
    return cec_sch.carve(txt, marker_start_idx)


def find_symbol_block(txt, ref):
    """Locate the *unique* (symbol ...) instance whose Reference property is
    exactly `ref`. Returns the block text (including its own leading '\\t').
    Refuses if zero or more than one match -- ambiguity is a bug to fix by
    hand, never to guess through."""
    needle = f'(property "Reference" "{ref}"'
    starts = [m.start() for m in re.finditer(re.escape(needle), txt)]
    # a Reference property can appear verbatim only once per real component
    # instance in these files (BOM child refs aren't used here), but guard anyway
    blocks = []
    for pm in starts:
        # the property always sits inside the nearest preceding "\t(symbol\n"
        sidx = txt.rindex("\t(symbol\n", 0, pm)
        blk = carve_from_marker(txt, sidx)
        if pm < sidx + len(blk):
            blocks.append((sidx, blk))
    if len(blocks) == 0:
        raise SystemExit(f"REFUSE: no symbol with Reference={ref!r} found")
    if len(blocks) > 1:
        raise SystemExit(f"REFUSE: {len(blocks)} symbols with Reference={ref!r} found (ambiguous)")
    return blocks[0]


def remove_symbol(txt, ref):
    """Delete the whole (symbol ...) instance for `ref`. Returns (new_txt, block)."""
    _sidx, blk = find_symbol_block(txt, ref)
    if txt.count(blk) != 1:
        raise SystemExit(f"REFUSE: block for {ref!r} is not uniquely matched in the file text")
    return txt.replace(blk, "", 1), blk


def _unique_at(txt, x, y):
    """Find the ONE element-DEFINING '(at x y ...)' at this exact point -- i.e.
    a symbol's own placement (the line right after its '(lib_id ...)') or a
    label's own placement (the line right after its '(label "NAME"' opener).
    A plain coordinate-substring scan over-matches: every HIDDEN property on a
    symbol (Footprint/Datasheet/Description/...) is stamped with the SAME (at
    x y 0) as the symbol's own origin, so those must be excluded here rather
    than counted as ambiguity."""
    at_txt = f"(at {f(x)} {f(y)} "
    pat = re.compile(
        r'(?:\(lib_id "[^"]*"\)\n\t\t|\(label "[^"]*"\n\t\t)' + re.escape(at_txt)
    )
    matches = list(pat.finditer(txt))
    if len(matches) == 0:
        raise SystemExit(f"REFUSE: nothing at ({x},{y}) -- expected coordinate not found")
    if len(matches) > 1:
        raise SystemExit(f"REFUSE: coordinate ({x},{y}) is ambiguous (matches more than once)")
    m = matches[0]
    return m.end() - len(at_txt)


def remove_terminal_at(txt, x, y):
    """Remove whatever single stub-end element -- a (label ...) or a
    power-symbol (symbol (lib_id "cec-power:...")) instance -- has its OWN
    placement at exactly (x, y). Returns (new_txt, kind, info) where kind is
    'label' (info=old net name) or 'power' (info=(ref, value))."""
    idx = _unique_at(txt, x, y)
    lab_i = txt.rfind('\t(label "', 0, idx)
    sym_i = txt.rfind("\t(symbol\n", 0, idx)
    start = max(lab_i, sym_i)
    if start < 0:
        raise SystemExit(f"REFUSE: no enclosing (label/(symbol found before ({x},{y})")
    blk = carve_from_marker(txt, start)
    if not (start <= idx < start + len(blk)):
        raise SystemExit(f"REFUSE: located block does not actually contain ({x},{y})")
    if txt.count(blk) != 1:
        raise SystemExit(f"REFUSE: terminal block at ({x},{y}) is not uniquely matched")
    new_txt = txt.replace(blk, "", 1)
    if start == lab_i:
        m = re.match(r'\t\(label "([^"]*)"', blk)
        return new_txt, "label", (m.group(1) if m else None)
    else:
        refm = re.search(r'\(property "Reference" "([^"]+)"', blk)
        valm = re.search(r'\(property "Value" "([^"]*)"', blk)
        return new_txt, "power", (refm.group(1) if refm else "?", valm.group(1) if valm else "?")


def remove_wire_between(txt, x1, y1, x2, y2):
    """Remove the (wire (pts (xy x1 y1) (xy x2 y2))...) segment, trying both
    endpoint orders (KiCad does not guarantee which end was drawn first)."""
    for a, b in (((x1, y1), (x2, y2)), ((x2, y2), (x1, y1))):
        # both needles are anchored to start exactly AT the '(' of '(wire' --
        # so the block's own start is always exactly one char (the leading
        # '\t') before the match, never found via a backward-bounded search
        # for "\t(wire\n" (that needle extends past `idx` itself and a
        # `rfind(..., 0, idx)` can't find a match straddling its own bound).
        needle = (f"(wire\n\t\t(pts\n\t\t\t(xy {f(a[0])} {f(a[1])}) (xy {f(b[0])} {f(b[1])})\n\t\t)")
        idx = txt.find(needle)
        if idx < 0:
            # also try the single-line compact form cec_sch.emit_wire produces
            needle2 = f"(pts (xy {f(a[0])} {f(a[1])}) (xy {f(b[0])} {f(b[1])}))"
            idx = txt.find(needle2)
            if idx < 0:
                continue
            start = txt.rfind("\t(wire", 0, idx)
        else:
            start = idx - 1
        if start < 0 or txt[start] != "\t":
            continue
        blk = carve_from_marker(txt, start)
        if not (start <= idx < start + len(blk)):
            continue
        if txt.count(blk) != 1:
            raise SystemExit(f"REFUSE: wire ({x1},{y1})-({x2},{y2}) block is not uniquely matched")
        return txt.replace(blk, "", 1)
    raise SystemExit(f"REFUSE: no wire found between ({x1},{y1}) and ({x2},{y2})")


def remove_pin_stub(txt, pins, ref, num, ox, oy):
    """Remove an EXISTING part's own stub wire + whatever terminal (label or
    power-symbol) sits at its end, computed from its pin table + placement.
    Returns (new_txt, kind, info) as remove_terminal_at."""
    ax, ay, dx, dy = pin_pt(pins, num, ox, oy)
    bx, by = gsnap(*stub_end(ax, ay, dx, dy))
    txt = remove_wire_between(txt, ax, ay, bx, by)
    return remove_terminal_at(txt, bx, by)


def rename_label_at(txt, x, y, new_name):
    """Change a (label "OLD" (at x y ...) ...) to (label "NEW" ...) in place,
    anchored by its exact coordinate. Returns (new_txt, old_name)."""
    idx = _unique_at(txt, x, y)
    start = txt.rfind('\t(label "', 0, idx)
    if start < 0 or not (start <= idx):
        raise SystemExit(f"REFUSE: no (label at ({x},{y})")
    blk = carve_from_marker(txt, start)
    if not (start <= idx < start + len(blk)):
        raise SystemExit(f"REFUSE: located label block does not contain ({x},{y})")
    m = re.match(r'\t\(label "([^"]*)"', blk)
    if not m:
        raise SystemExit(f"REFUSE: block at ({x},{y}) is not a (label ...)")
    old_name = m.group(1)
    new_blk = blk.replace(f'(label "{old_name}"', f'(label "{new_name}"', 1)
    if txt.count(blk) != 1:
        raise SystemExit(f"REFUSE: label block at ({x},{y}) is not uniquely matched")
    return txt.replace(blk, new_blk, 1), old_name


def pin_pt(pins, num, ox, oy):
    """Absolute (x, y, dx, dy) of pin `num` for a part placed at (ox, oy),
    ROTATION 0 ONLY (every new part in this delta is placed unrotated).
    Mirrors cec_sch.pin_abs's math without needing its parts/used/placement
    machinery."""
    lx, ly, ang, _length = pins[num]
    ax, ay = ox + lx, oy - ly
    dx = -math.cos(math.radians(ang))
    dy = math.sin(math.radians(ang))
    return ax, ay, dx, dy


def stub_end(ax, ay, dx, dy, length=STUB):
    return ax + dx * length, ay + dy * length


def label_angle(dx, dy):
    return 0 if dx > 0 else (180 if dx < 0 else (270 if dy < 0 else 90))


def wire_and_label(pins, ref, num, ox, oy, net):
    """Stub a part's pin out to a same-sheet text label. Returns the two
    emitted elements joined by '\\n'."""
    ax, ay, dx, dy = pin_pt(pins, num, ox, oy)
    bx, by = stub_end(ax, ay, dx, dy)
    bx, by = gsnap(bx), gsnap(by)
    return "\n".join([
        cec_sch.emit_wire(ax, ay, bx, by),
        cec_sch.emit_label(net, bx, by, label_angle(dx, dy)),
    ])


def wire_and_global_label(pins, ref, num, ox, oy, net):
    """Stub a part's pin out to a GLOBAL label (project-wide by name, crosses
    sheet boundaries -- cec_sch.emit_global_label's documented purpose)."""
    ax, ay, dx, dy = pin_pt(pins, num, ox, oy)
    bx, by = stub_end(ax, ay, dx, dy)
    bx, by = gsnap(bx), gsnap(by)
    return "\n".join([
        cec_sch.emit_wire(ax, ay, bx, by),
        cec_sch.emit_global_label(net, bx, by, label_angle(dx, dy)),
    ])


def wire_and_power(pins, ref, num, ox, oy, symname, project, root, pwr_ref, rot=None):
    """Stub a part's pin out to a global power-symbol instance (GND / +5VSB /
    etc). rot defaults to 0 for GND (points down) and 180 otherwise (points
    up), matching cec_sch.build_schematic's own convention."""
    ax, ay, dx, dy = pin_pt(pins, num, ox, oy)
    bx, by = stub_end(ax, ay, dx, dy)
    bx, by = gsnap(bx), gsnap(by)
    if rot is None:
        rot = 0 if symname == "GND" else 180
    return "\n".join([
        cec_sch.emit_wire(ax, ay, bx, by),
        cec_sch.emit_global_power(symname, bx, by, project, root, pwr_ref, rot),
    ])


def noconnect_pin(pins, ref, num, ox, oy):
    """A genuine no_connect flag AT the pin's own connection point (no stub)."""
    ax, ay, _dx, _dy = pin_pt(pins, num, ox, oy)
    return cec_sch.emit_noconnect(ax, ay)


def wire_between(pins_a, ref_a, num_a, ox_a, oy_a, pins_b, ref_b, num_b, ox_b, oy_b, net):
    """Two parts' pins, each stubbed out to their OWN label instance carrying
    the same net name (the house style throughout this codebase: connectivity
    is name-matched, not geometrically routed)."""
    return "\n".join([
        wire_and_label(pins_a, ref_a, num_a, ox_a, oy_a, net),
        wire_and_label(pins_b, ref_b, num_b, ox_b, oy_b, net),
    ])


def get_pin_table(txt, lib_id):
    """pin_table() for a symbol already embedded in this file's own lib_symbols."""
    m = re.search(r'\(symbol "' + re.escape(lib_id) + r'"', txt)
    if not m:
        raise SystemExit(f"REFUSE: lib_symbol {lib_id!r} not embedded in this file")
    blk = cec_sch.carve(txt, m.start())
    return cec_sch.pin_table(blk)


def ensure_lib_symbol(txt, lib_id, donor_path):
    """If `lib_id` (e.g. 'cec-vendor:TPS2121RUXR') is not already embedded in
    this file's lib_symbols, copy its block verbatim from `donor_path` (another
    board that already carries it) and insert it just before the lib_symbols
    section's closing marker. Returns (new_txt, was_added)."""
    needle = f'(symbol "{lib_id}"'
    if needle in txt:
        return txt, False
    donor = open(donor_path).read()
    dm = re.search(re.escape(needle), donor)
    if not dm:
        raise SystemExit(f"REFUSE: donor {donor_path} does not carry {lib_id!r} either")
    blk = cec_sch.carve(donor, dm.start())
    # insert right before the lib_symbols section's own closing "\t)" -- find it
    # as the first "\n\t)\n" AFTER "\t(lib_symbols" that appears before the
    # first non-lib_symbols top-level content (a symbol/wire/label instance).
    ls_start = txt.index("\t(lib_symbols")
    close_idx = txt.index("\n\t)\n", ls_start)
    new_txt = txt[:close_idx + 1] + "\t\t" + blk + "\n" + txt[close_idx + 1:]
    return new_txt, True
