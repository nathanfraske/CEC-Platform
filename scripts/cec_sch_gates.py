#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_sch_gates -- ROUND-4 DETERMINISTIC CHECKER/MUTATOR TOOLKIT
# ============================================================================
# Plan of record: docs/standard-tier-review/round4-hier-conversion-2026-07-04.md
# (G6 region-containment/sheet-bounds, G2 symbol-inventory equality, G8 prose
# preservation, + the GND-ladder bus mutation applied to the two flat boards
# that stay flat). ADDITIVE: builds entirely on scripts/cec_sch.py's and
# scripts/cec_sch_layout.py's existing primitives (text/pin-glyph extent
# machinery, the rotate_local + Y-flip convention, the wire/overlap
# detectors) -- no pin math is re-derived here.
import os
import re
import sys
import math
import tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import cec_sch                    # noqa: E402  unmodified low-level primitives
import cec_sch_layout as L        # noqa: E402  T1 layout/mutator engine


def _read(path_or_text):
    """Accept either a file path or already-loaded .kicad_sch text."""
    if "\n" not in path_or_text and os.path.isfile(path_or_text):
        return open(path_or_text).read()
    return path_or_text


# ============================================================================
# PAPER / REGION PARSING (shared by check_region_containment + check_sheet_bounds)
# ============================================================================
_PAPER_MM = {"A5": (210.0, 148.0), "A4": (297.0, 210.0), "A3": (420.0, 297.0),
            "A2": (594.0, 420.0), "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}


def _paper_rect(text):
    """(x0, x1, y0, y1, label) for the sheet's `(paper ...)` clause -- origin
    at (0,0) top-left, KiCad Y-down convention. Supports named sizes
    (A5..A0, landscape by default, `portrait` swaps W/H) and explicit
    `(paper "User" W H)`. None if unparseable."""
    m = re.search(r'\(paper\s+"([^"]+)"(?:\s+(-?[\d.]+)\s+(-?[\d.]+))?'
                  r'(?:\s+(portrait))?\)', text)
    if not m:
        return None
    name, w, h, portrait = m.group(1), m.group(2), m.group(3), m.group(4)
    if name == "User" and w and h:
        width, height = float(w), float(h)
    elif name in _PAPER_MM:
        width, height = _PAPER_MM[name]
    else:
        return None
    if portrait:
        width, height = height, width
    label = f'{name} {width:.0f}x{height:.0f}'
    return (0.0, width, 0.0, height, label)


def _parse_regions(text):
    """[{"title","x0","x1","y0","y1","span"}] for every TOP-LEVEL dashed
    accent-frame rectangle (round-3's "region" convention -- either
    cec_sch.emit_section's or cec_sch_compose.emit_region's form; both emit
    an identical `(rectangle ... (stroke (width W) (type dash)) ...)` block,
    differing only in the caption offset/color, so both are matched the same
    way). The title is whichever top-level free `(text ...)` element sits
    closest to the frame's top-left corner (within a generous 3mm radius --
    covers both the +1.27mm and +1.5mm caption-offset conventions in use)."""
    work = L._strip_lib_symbols(text)
    texts = L._extract_text_elements(text)
    free_texts = [el for el in texts if el["kind"] == "text"]
    regions = []
    for m in re.finditer(r'\(rectangle\n', work):
        s = m.start()
        blk = cec_sch.carve(work, s)
        if "(type dash)" not in blk:
            continue
        sm = re.search(r'\(start\s+(-?[\d.]+)\s+(-?[\d.]+)\)', blk)
        em = re.search(r'\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\)', blk)
        if not (sm and em):
            continue
        x0, x1 = sorted((float(sm.group(1)), float(em.group(1))))
        y0, y1 = sorted((float(sm.group(2)), float(em.group(2))))
        title, best_d = None, 3.0
        for el in free_texts:
            tx, ty = el["at"][0], el["at"][1]
            d = math.hypot(tx - (x0 + 1.27), ty - (y0 + 1.27))
            d = min(d, math.hypot(tx - (x0 + 1.5), ty - (y0 + 1.5)))
            if d < best_d:
                best_d, title = d, el["text"]
        regions.append({"title": title or "<untitled>",
                        "x0": x0, "x1": x1, "y0": y0, "y1": y1,
                        "span": (s, s + len(blk))})
    return regions


def _fully_inside(bbox, rect, tol=1e-6):
    x0, x1, y0, y1 = bbox
    rx0, rx1, ry0, ry1 = rect
    return x0 >= rx0 - tol and x1 <= rx1 + tol and y0 >= ry0 - tol and y1 <= ry1 + tol


def _rects_overlap(a, b, tol=1e-9):
    ax0, ax1, ay0, ay1 = a
    bx0, bx1, by0, by1 = b
    return not (ax1 <= bx0 + tol or bx1 <= ax0 + tol
               or ay1 <= by0 + tol or by1 <= ay0 + tol)


# ============================================================================
# SYMBOL FULL-EXTENT (body + pin reach) -- reuses cec_sch_layout's rotation-
# aware pin math (rotate_local) and its pin-glyph engine (_parse_pin_glyph_lib
# / _pin_glyph_boxes_local); the only NEW parsing here is the body-outline
# union (rectangle + polyline + circle), since cec_sch.sym_body_box only
# covers rectangles and several vendored ICs draw their body as a polyline.
# ============================================================================
def _lib_blocks(text):
    """{lib_id: raw local block text} for every top-level symbol def in
    `(lib_symbols ...)` -- lets callers reuse cec_sch.sym_body_box /
    cec_sch_layout.body_box_abs (which want the raw block) without
    re-deriving their own rectangle/shape parsing."""
    out = {}
    m = re.search(r'\(lib_symbols\b', text)
    if not m:
        return out
    lib_block = cec_sch.carve(text, m.start())
    pos = 0
    while True:
        sm = re.compile(r'\(symbol\s+"((?:[^"\\]|\\.)*)"').search(lib_block, pos)
        if not sm:
            break
        blk = cec_sch.carve(lib_block, sm.start())
        pos = sm.start() + len(blk)
        out[sm.group(1)] = blk
    return out


def _combined_body_extent_local(blk):
    """Local (minx,maxx,miny,maxy) union of rectangle + polyline + circle
    primitives drawn directly in a symbol block -- the real drawn body
    outline (cec_sch.sym_body_box only sees rectangles; several vendored ICs
    draw a polygon outline instead). None if the block draws no shape at all
    (e.g. a bare power-flag glyph, whose reach is pin-derived only)."""
    xs, ys = [], []
    bb = cec_sch.sym_body_box(blk)
    if bb:
        xs += [bb[0], bb[1]]
        ys += [bb[2], bb[3]]
    for pm in re.finditer(r'\(pts\s+((?:\(xy\s+-?[\d.]+\s+-?[\d.]+\)\s*)+)\)', blk):
        for xy in re.finditer(r'\(xy\s+(-?[\d.]+)\s+(-?[\d.]+)\)', pm.group(1)):
            xs.append(float(xy.group(1)))
            ys.append(float(xy.group(2)))
    for cm in re.finditer(r'\(circle\s*\(center\s+(-?[\d.]+)\s+(-?[\d.]+)\)'
                          r'\s*\(radius\s+(-?[\d.]+)\)', blk):
        cx, cy, r = float(cm.group(1)), float(cm.group(2)), float(cm.group(3))
        xs += [cx - r, cx + r]
        ys += [cy - r, cy + r]
    return (min(xs), max(xs), min(ys), max(ys)) if xs else None


def _symbol_extents(text, *, include_power=False):
    """{ref: (x0,x1,y0,y1)} absolute full extent (body outline UNION every
    pin's own connection point UNION visible pin name/number glyph boxes) for
    every symbol instance. Power symbols (#PWR/#FLG) are skipped unless
    include_power=True (region-containment exempts them per the round-4 gate
    spec; sheet-bounds wants them checked too)."""
    work = L._strip_lib_symbols(text)
    blocks = _lib_blocks(text)
    pin_lib = L._parse_pin_glyph_lib(text)
    out = {}
    for s, e, (ox, oy), ref, rot, lib_id, mir in L._symbol_spans(work):
        if ref.startswith("#") and not include_power:
            continue
        xs, ys = [], []
        blk = blocks.get(lib_id)
        local_bb = _combined_body_extent_local(blk) if blk else None
        if local_bb:
            minx, maxx, miny, maxy = local_bb
            for (lx, ly) in ((minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy)):
                rlx, rly = L.rotate_local(lx, ly, rot)
                xs.append(ox + rlx)
                ys.append(oy - rly)
        sym = pin_lib.get(lib_id)
        if sym:
            for p in sym["pins"]:
                rlx, rly = L.rotate_local(p["x"], p["y"], rot)
                xs.append(ox + rlx)
                ys.append(oy - rly)
            if not mir:
                for _k, _t, _n, (x0, x1, y0, y1) in L._pin_glyph_boxes_local(sym):
                    for (lx, ly) in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
                        rlx, rly = L.rotate_local(lx, ly, rot)
                        xs.append(ox + rlx)
                        ys.append(oy - rly)
        if not xs:
            xs, ys = [ox], [oy]
        out[ref] = (min(xs), max(xs), min(ys), max(ys))
    return out


# ============================================================================
# G6a/G6b: REGION-CONTAINMENT + SHEET-BOUNDS CHECKERS
# ============================================================================
def check_region_containment(sch_path):
    """Findings (human-readable strings), each prefixed by class:
      CONTAINMENT -- a non-power, non-text symbol's extent is not fully
                     inside ANY region (only checked on sheets with >=1 region;
                     a sheet with zero regions is exempt entirely).
      STRADDLE    -- a symbol extent overlaps a region's rectangle without
                     being fully inside it (clips the frame).
      REGION-OVERLAP -- two region frames overlap each other.
      REGION-OVERRUN -- a region frame extends beyond the sheet's own paper
                        rectangle.
    Power symbols (#PWR/#FLG) are exempt from CONTAINMENT/STRADDLE (they are
    tiny stamps, not functional-block content)."""
    text = open(sch_path).read()
    regions = _parse_regions(text)
    if not regions:
        return []
    findings = []
    region_rects = [(r["x0"], r["x1"], r["y0"], r["y1"]) for r in regions]
    extents = _symbol_extents(text, include_power=False)
    for ref, bbox in extents.items():
        contained = any(_fully_inside(bbox, rr) for rr in region_rects)
        if not contained:
            findings.append(
                f'CONTAINMENT {ref} extent ({bbox[0]:.2f},{bbox[2]:.2f})-'
                f'({bbox[1]:.2f},{bbox[3]:.2f}) not fully inside any region')
        for r, rr in zip(regions, region_rects):
            if _rects_overlap(bbox, rr) and not _fully_inside(bbox, rr):
                findings.append(
                    f'STRADDLE {ref} extent crosses the boundary of region '
                    f'"{r["title"]}" ({rr[0]:.2f},{rr[2]:.2f})-({rr[1]:.2f},{rr[3]:.2f})')
    for i in range(len(regions)):
        for j in range(i + 1, len(regions)):
            if _rects_overlap(region_rects[i], region_rects[j]):
                findings.append(
                    f'REGION-OVERLAP "{regions[i]["title"]}" '
                    f'({region_rects[i][0]:.2f},{region_rects[i][2]:.2f})-'
                    f'({region_rects[i][1]:.2f},{region_rects[i][3]:.2f}) overlaps '
                    f'"{regions[j]["title"]}" '
                    f'({region_rects[j][0]:.2f},{region_rects[j][2]:.2f})-'
                    f'({region_rects[j][1]:.2f},{region_rects[j][3]:.2f})')
    paper = _paper_rect(text)
    if paper:
        px0, px1, py0, py1, label = paper
        for r, rr in zip(regions, region_rects):
            if not _fully_inside(rr, (px0, px1, py0, py1)):
                findings.append(
                    f'REGION-OVERRUN "{r["title"]}" '
                    f'({rr[0]:.2f},{rr[2]:.2f})-({rr[1]:.2f},{rr[3]:.2f}) extends '
                    f'beyond the {label} sheet (0,0)-({px1:.0f},{py1:.0f})')
    return findings


def check_sheet_bounds(sch_path):
    """Findings: any symbol extent (incl. power symbols), text/label glyph,
    or wire endpoint that falls outside the sheet's own `(paper ...)`
    rectangle. Prefixed OFF-SHEET."""
    text = open(sch_path).read()
    paper = _paper_rect(text)
    if not paper:
        return ['SHEET-BOUNDS: could not parse a (paper ...) clause -- skipped']
    px0, px1, py0, py1, label = paper

    def _out(x0, x1, y0, y1):
        return (x0 < px0 - 1e-6 or x1 > px1 + 1e-6
               or y0 < py0 - 1e-6 or y1 > py1 + 1e-6)

    findings = []
    for ref, bbox in _symbol_extents(text, include_power=True).items():
        x0, x1, y0, y1 = bbox
        if _out(x0, x1, y0, y1):
            findings.append(
                f'OFF-SHEET {ref} extent ({x0:.2f},{y0:.2f})-({x1:.2f},{y1:.2f}) '
                f'outside the {label} sheet (0,0)-({px1:.0f},{py1:.0f})')
    for el in L._extract_text_elements(text):
        x0, x1, y0, y1 = el["bbox"]
        if _out(x0, x1, y0, y1):
            findings.append(f'OFF-SHEET {el["label"][:48]} outside the {label} sheet')
    for seg in L._extract_wires(text):
        for (x, y) in ((seg[0], seg[1]), (seg[2], seg[3])):
            if _out(x, x, y, y):
                findings.append(f'OFF-SHEET wire endpoint ({x:.2f},{y:.2f}) '
                                f'outside the {label} sheet')
    return findings


# ============================================================================
# G2: SYMBOL-INVENTORY EQUALITY (the anti-silent-loss gate: a netlist alone
# can hide a dropped DNP part or a silently-changed property, since DNP parts
# and non-electrical properties carry no netlist connectivity at all).
# ============================================================================
def _sheet_children(text, own_dir):
    """[(child_abs_path)] for every `(sheet ...)` this file instantiates,
    resolved via its `Sheetfile` property relative to `own_dir`."""
    work = L._strip_lib_symbols(text)
    out = []
    for m in re.finditer(r'\(sheet\n', work):
        blk = cec_sch.carve(work, m.start())
        fm = re.search(r'\(property\s+"Sheetfile"\s+"((?:[^"\\]|\\.)*)"', blk)
        if fm:
            out.append(os.path.join(own_dir, L._unescape(fm.group(1))))
    return out


def _inventory_walk(path, out, visited, root_dir):
    path = os.path.abspath(path)
    if path in visited or not os.path.isfile(path):
        return
    visited.add(path)
    text = open(path).read()
    rel = os.path.relpath(path, root_dir)
    work = L._strip_lib_symbols(text)
    for s, e, (ox, oy), ref, rot, lib_id, mir in L._symbol_spans(work):
        if ref.startswith("#"):
            continue
        blk = text[s:e]
        props = {}
        for pm in re.finditer(r'\(property\s+"((?:[^"\\]|\\.)*)"\s+'
                              r'"((?:[^"\\]|\\.)*)"', blk):
            name, val = L._unescape(pm.group(1)), L._unescape(pm.group(2))
            if name == "Reference":
                continue
            props[name] = val
        out[ref] = {
            "lib_id": lib_id, "sheet": rel,
            "value": props.get("Value", ""),
            "footprint": props.get("Footprint", ""),
            "dnp": bool(re.search(r'\(dnp\s+yes\)', blk)),
            "in_bom": not bool(re.search(r'\(in_bom\s+no\)', blk)),
            "on_board": not bool(re.search(r'\(on_board\s+no\)', blk)),
            "props": props,
        }
    for child in _sheet_children(text, os.path.dirname(path)):
        _inventory_walk(child, out, visited, root_dir)


def inventory(project_root_sch):
    """{ref: {"lib_id","sheet","value","footprint","dnp","in_bom","on_board",
    "props": {name: value, ...except Reference}}} for every non-power symbol
    in `project_root_sch` AND every sheet it references, walked recursively
    via each `(sheet ...)`'s Sheetfile property. This is the FULL symbol
    record, not just netlist connectivity -- a DNP'd part or a dropped BOM
    property carries no net membership at all, so a netlist diff alone
    cannot see it (the round-4 G2 rationale)."""
    root_dir = os.path.dirname(os.path.abspath(project_root_sch))
    out, visited = {}, set()
    _inventory_walk(project_root_sch, out, visited, root_dir)
    return out


def check_inventory_equal(a, b):
    """Diff two inventories (each may be a dict from inventory(), or a root
    .kicad_sch path to inventory() first). Returns [] iff identical: same
    ref set, same lib_id/value/footprint/dnp/in_bom/on_board, same full
    property set per ref (name AND value)."""
    if isinstance(a, str):
        a = inventory(a)
    if isinstance(b, str):
        b = inventory(b)
    findings = []
    for r in sorted(set(a) - set(b)):
        findings.append(f'MISSING {r} ({a[r]["lib_id"]}) in baseline, absent from new')
    for r in sorted(set(b) - set(a)):
        findings.append(f'EXTRA {r} ({b[r]["lib_id"]}) in new, absent from baseline')
    for r in sorted(set(a) & set(b)):
        ra, rb = a[r], b[r]
        for key in ("lib_id", "value", "footprint", "dnp", "in_bom", "on_board"):
            if ra[key] != rb[key]:
                findings.append(f'CHANGED {r}.{key}: {ra[key]!r} -> {rb[key]!r}')
        pa, pb = ra["props"], rb["props"]
        for k in sorted(set(pa) - set(pb)):
            findings.append(f'CHANGED {r}.props: dropped {k!r}={pa[k]!r}')
        for k in sorted(set(pb) - set(pa)):
            findings.append(f'CHANGED {r}.props: added {k!r}={pb[k]!r}')
        for k in sorted(set(pa) & set(pb)):
            if pa[k] != pb[k]:
                findings.append(f'CHANGED {r}.props.{k}: {pa[k]!r} -> {pb[k]!r}')
    return findings


# ============================================================================
# G8: PROSE PRESERVATION -- every engineering-content free `(text ...)`
# string from the baseline sheet(s) must survive into the new sheet(s),
# verbatim (after whitespace normalization) or via an explicit waiver.
# ============================================================================
def _norm_ws(s):
    return re.sub(r'\s+', ' ', s).strip()


def _all_prose_strings(paths):
    """{normalized_string: [source_path, ...]} for every free `(text ...)`
    element (captions/notes/region titles -- NOT labels, NOT property
    values) across `paths`."""
    out = defaultdict(list)
    for p in paths:
        text = open(p).read()
        work = L._strip_lib_symbols(text)
        for m in re.finditer(r'\(text\s+"((?:[^"\\]|\\.)*)"', work):
            out[_norm_ws(L._unescape(m.group(1)))].append(p)
    return out


def check_prose_preserved(baseline_sch_paths, new_sch_paths, waivers=()):
    """[missing_string, ...] -- every normalized prose string present in
    `baseline_sch_paths` that is NOT found anywhere in `new_sch_paths` and is
    NOT covered by `waivers` (an iterable of strings, also whitespace-
    normalized before comparison)."""
    base = _all_prose_strings(baseline_sch_paths)
    new = _all_prose_strings(new_sch_paths)
    waived = {_norm_ws(w) for w in waivers}
    return sorted(s for s in base if s not in new and s not in waived)


# ============================================================================
# GND-LADDER BUS MUTATOR (owner item 2: "GND arrays bused to one link on ALL
# boards"). Geometry/detection lives in cec_sch_layout.power_ladder_runs;
# this is the write side. Reuses cec_sch_layout.wire_chain for the actual
# copper (each leg a straight, already-collinear hop between adjacent pins --
# no new pin math) and the real detect_overlaps/check_wire_collisions/
# check_power_glyphs detectors as the collision ground truth, the same
# pattern retrofit_decoupler_adjacency established.
# ============================================================================
def _foreign_geometry(text, exclude_ref):
    """(boxes, pin_pts) -- every OTHER symbol's body keep-out box
    (cec_sch_layout.body_box_abs) and every OTHER symbol's pin connection
    points, in the shape cec_sch.route_L expects. `exclude_ref` (the ladder's
    own symbol) is left out entirely: its own body sits inward of the pin
    tips the chain wire threads through, and its OTHER pins are never
    obstacles for a wire connecting ITS OWN pins."""
    work = L._strip_lib_symbols(text)
    blocks = _lib_blocks(text)
    pin_lib = L._parse_pin_glyph_lib(text)
    boxes, pin_pts = [], set()
    for s, e, (ox, oy), ref, rot, lib_id, mir in L._symbol_spans(work):
        if ref == exclude_ref:
            continue
        blk = blocks.get(lib_id)
        if blk:
            bb = L.body_box_abs(blk, ox, oy, rot)
            if bb:
                boxes.append(bb)
        if ref.startswith("#"):
            pin_pts.add((round(ox, 3), round(oy, 3)))
            continue
        sym = pin_lib.get(lib_id)
        if sym:
            for p in sym["pins"]:
                rlx, rly = L.rotate_local(p["x"], p["y"], rot)
                pin_pts.add((round(ox + rlx, 3), round(oy - rly, 3)))
    return boxes, pin_pts


def bus_power_ladder(sch_path, ref, net="GND", *, out_path=None):
    """MUTATOR: collapse each qualifying cec_sch_layout.power_ladder_runs()
    run on `ref` down to ONE kept #PWR/#FLG stamp (the run's first pin, in
    physical order) plus a single real chain wire threading every pin's own
    connection point (cec_sch_layout.wire_chain -- each leg a straight,
    already-collinear hop; no junction needed beyond the natural two-wire
    joint at the kept end, per wire_chain's own docstring).

    SAFE BY CONSTRUCTION (guard a, "a flag can be the only thing connecting
    two wire islands"): power_ladder_runs only returns pins whose flag is a
    fully isolated single-wire stub (its `_own_flag` check requires degree-1
    at BOTH the pin AND the flag end) -- such a flag can never be the sole
    connector of anything else, so deleting it (while the new chain wire
    keeps the pin itself connected) cannot strand another island.

    HARD GUARD (b, corridor collision): the candidate chain is routed via
    wire_chain against every FOREIGN symbol's body box + pin point on the
    sheet (_foreign_geometry) -- a run whose chain would cross/touch foreign
    geometry is REFUSED (reason "corridor blocked"), and the realized
    candidate is additionally re-checked with the real detect_overlaps /
    check_wire_collisions / check_power_glyphs detectors against the
    pre-mutation baseline (must not increase) before anything is written.

    Returns {"applied": bool, "runs_found": int, "runs_applied": [...],
    "refused": [...], "flags_removed": int}. Callers needing the round-4
    netlist-identity / ERC-count bar should wrap this the same way
    cec_sch_mcp._gated wraps every other mutator (see that module)."""
    text = open(sch_path).read()
    runs = L.power_ladder_runs(text, ref, net)
    if not runs:
        return {"applied": False, "runs_found": 0, "runs_applied": [],
                "refused": [], "flags_removed": 0,
                "reason": "no qualifying ladder run found"}

    baseline_overlap = len(L.detect_overlaps(sch_path))
    baseline_wire = len(L.check_wire_collisions(sch_path)
                        + L.check_power_glyphs(sch_path))
    boxes, pin_pts = _foreign_geometry(text, ref)

    applied, refused, cuts, new_wire_blocks = [], [], set(), []
    for run in runs:
        legs = L.wire_chain(run["points"], boxes=boxes, pin_pts=pin_pts,
                            max_len=1e9)
        if legs is None:
            refused.append({"pins": run["pins"], "reason":
                            "corridor blocked -- chain wire would cross a "
                            "foreign body/pin"})
            continue
        for flag_ref, flag_span, wire_span, _at in run["flags"][1:]:
            cuts.add(flag_span)
            cuts.add(wire_span)
        for (x1, y1, x2, y2) in legs:
            new_wire_blocks.append(cec_sch.emit_wire(x1, y1, x2, y2))
        applied.append({"pins": run["pins"], "kept_flag": run["flags"][0][0],
                        "flags_removed": len(run["flags"]) - 1})

    if not applied:
        return {"applied": False, "runs_found": len(runs), "runs_applied": [],
                "refused": refused, "flags_removed": 0}

    # extend each cut to its own whole line(s) (leading indentation through
    # the trailing newline) so deleting 17 flags doesn't litter the file with
    # 17 blank lines -- purely cosmetic, byte-identical net effect on every
    # OTHER line, verified via the same identity/ERC/detector gate below.
    def _line_span(s, e):
        ls = text.rfind("\n", 0, s) + 1
        le = text.find("\n", e)
        le = le + 1 if le >= 0 else len(text)
        return ls, le

    extended = sorted(_line_span(s, e) for s, e in cuts)
    merged = []
    for s, e in extended:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    cand = text
    for s, e in sorted(merged, key=lambda t: -t[0]):
        cand = cand[:s] + cand[e:]
    insert_at = cand.find("(sheet_instances")
    if insert_at < 0:
        insert_at = len(cand)
    cand = cand[:insert_at] + "\n".join(new_wire_blocks) + "\n" + cand[insert_at:]

    with tempfile.NamedTemporaryFile("w", suffix=".kicad_sch",
                                     delete=False) as f:
        f.write(cand)
        scratch = f.name
    try:
        ov = len(L.detect_overlaps(scratch))
        wr = len(L.check_wire_collisions(scratch) + L.check_power_glyphs(scratch))
    finally:
        os.unlink(scratch)
    if ov > baseline_overlap or wr > baseline_wire:
        return {"applied": False, "runs_found": len(runs), "runs_applied": [],
                "refused": refused + [{"reason":
                    f"post-mutation collision detectors increased "
                    f"(overlap {baseline_overlap}->{ov}, wire {baseline_wire}->{wr})"}],
                "flags_removed": 0}

    open(out_path or sch_path, "w").write(cand)
    return {"applied": True, "runs_found": len(runs), "runs_applied": applied,
            "refused": refused,
            "flags_removed": sum(a["flags_removed"] for a in applied)}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="cec_sch_gates -- round-4 checker/mutator CLI")
    ap.add_argument("--region-containment", metavar="SCH")
    ap.add_argument("--sheet-bounds", metavar="SCH")
    ap.add_argument("--bus-ladder", metavar="SCH")
    ap.add_argument("--ref", metavar="REF", help="symbol ref for --bus-ladder")
    ap.add_argument("--net", default="GND")
    args = ap.parse_args(argv)
    if args.region_containment:
        for f in check_region_containment(args.region_containment):
            print(f)
        return 0
    if args.sheet_bounds:
        for f in check_sheet_bounds(args.sheet_bounds):
            print(f)
        return 0
    if args.bus_ladder:
        if not args.ref:
            ap.error("--bus-ladder requires --ref")
        import json
        print(json.dumps(bus_power_ladder(args.bus_ladder, args.ref, args.net),
                         indent=2))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
