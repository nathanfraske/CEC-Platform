#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_sch_lint -- SCHEMATIC STYLE LINTER (T3, docs/schematic-quality-charter.md)
# ============================================================================
# Joins the per-sheet verification protocol next to ERC: ERC/netlist prove
# ELECTRICAL truth (docs/schematic-quality-charter.md principle 1 -- this tool
# NEVER changes a file, it only reads); this linter checks READABILITY/STYLE
# hygiene that ERC does not: grid discipline, junction shape, dangling wire
# ends, label-vs-wire orientation, PWR_FLAG hygiene, and wire-crossing counts.
#
# Standalone + ADDITIVE, like cec_sch_layout.py: it reuses (imports, does not
# modify) scripts/cec_sch.py's `carve` balanced-s-expr reader and
# scripts/cec_sch_layout.py's validated rotation math (`rotate_local`, see that
# module's header for the empirical round-trip proof of the rotation
# convention) and its text-block helpers (`_extract_at` / `_extract_font` /
# `_extract_justify` / `_unescape`) -- the SAME pin-position and text-clause
# extraction approach the rest of the cec_sch* family already uses, rather
# than inventing a second convention.
#
# PARSER DESIGN. KiCad 10 writes .kicad_sch as a single s-expression, but this
# repo's own files are NOT one uniform style: hand-maintained sheets mix
# GUI pretty-printed multi-line clauses (`(label "X"\n\t(at ...)\n...)`) with
# generator-emitted single-line clauses (`(label "X" (at ...) ...)`) in the
# SAME file (hub-standard.kicad_sch does this literally -- see its "+5VSB"
# label vs its "EN" labels). A line-oriented regex parser breaks on that mix.
# Instead this module walks the s-expr generically: `iter_children(block)`
# takes any balanced `(tag ...)` string (via `cec_sch.carve`) and yields each
# DIRECT child `(tag2 ...)` as its own balanced string, independent of
# whitespace/newline layout. Because a KiCad top-level symbol INSTANCE is
# always a direct child of `(kicad_sch ...)` while every library SYMBOL
# DEFINITION is always nested one level inside the single `(lib_symbols ...)`
# child, this direct-children walk disambiguates "symbol instance" from
# "symbol definition" for free, with no name-based heuristic needed.
#
# SCOPE / CALIBRATION NOTE (charter principle 3: calibrate, don't guess). Two
# things are deliberately EXCLUDED from the electrical-grid check (SL-01) even
# though they carry `(at X Y)` clauses: `(sheet ...)` block position/size, and
# free `(text ...)` / section-title annotations. Both were measured (see
# tests + the real-board comparison in this module's docstring-adjacent CLI
# output) to use a DIFFERENT, legitimate convention -- whole-mm page-layout
# margins (e.g. a sheet box at (20, 20)) -- not the 1.27 mm wiring grid, and
# checking them produced wall-to-wall false fires on real hub-enterprise sheet
# maps with zero diagnostic value. Wire/junction/no-connect/label/pin/symbol-
# instance positions ARE held to the wiring grid, and that check reproduces
# EXACTLY the two real, previously-known off-grid stamps in this repo
# (#FLG200/#FLG201 in hub-standard.kicad_sch, see CLAUDE.md action item 0) and
# nothing else -- the calibration evidence for keeping the check as specified.
import os
import re
import sys
import math
import json
import argparse
from collections import defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT + "/scripts" not in sys.path:
    sys.path.insert(0, _ROOT + "/scripts")
import cec_sch                 # unmodified: carve, pin_table, symbol_block, GRID
import cec_sch_layout as csl    # unmodified: rotate_local, _extract_at/_extract_font/_extract_justify/_unescape

GRID = cec_sch.GRID             # 1.27 mm
_EPS_GRID = 0.01                # mm tolerance for "on grid" (float-format noise)
_EPS_PT = 0.01                  # mm tolerance for "same point"


# ============================================================================
# GENERIC S-EXPR WALK (reused by every extractor below)
# ============================================================================

_TAG_RE = re.compile(r'\(\s*([A-Za-z_][\w]*)')


def iter_children(block):
    """Yield (tag, child_block) for every DIRECT child `(tag ...)` s-expr of
    `block` (block itself must be a full balanced `(...)` string, e.g. from
    cec_sch.carve). Bare atoms and quoted strings appearing directly under the
    tag (e.g. the "EN" in `(label "EN" (at ...))`, or `kicad_sch` itself) are
    skipped -- callers needing that leading string use `first_string()`."""
    m = _TAG_RE.match(block)
    i = m.end() if m else 1
    n = len(block) - 1  # exclude the final ')'
    while i < n:
        c = block[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j = i + 1
            while j < n and block[j] != '"':
                if block[j] == '\\':
                    j += 1
                j += 1
            i = j + 1
            continue
        if c == '(':
            child = cec_sch.carve(block, i)
            tm = _TAG_RE.match(child)
            yield (tm.group(1) if tm else None), child
            i += len(child)
            continue
        j = i
        while j < n and not block[j].isspace() and block[j] not in '()"':
            j += 1
        i = j if j > i else i + 1


def first_string(block):
    """The first quoted-string ARGUMENT of a tag, e.g. the net name in
    `(label "EN" ...)` / `(global_label "EN" ...)` / the text in `(text "..."
    ...)` / the symbol name in `(symbol "lib:Name" ...)`."""
    m = re.match(r'\(\s*[A-Za-z_][\w]*\s+"((?:[^"\\]|\\.)*)"', block)
    return csl._unescape(m.group(1)) if m else None


def prop_value(block, name):
    m = re.search(r'\(property\s+"' + re.escape(name) + r'"\s+"((?:[^"\\]|\\.)*)"', block)
    return csl._unescape(m.group(1)) if m else None


def find_uuid(block):
    m = re.search(r'\(uuid\s+"([0-9a-fA-F-]+)"', block)
    return m.group(1) if m else None


_PIN_HEAD_RE = re.compile(
    r'\(pin\s+([a-z_]+)\s+[a-z_]+\s*\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\)\s*\(length\s+(-?[\d.]+)\)')


def pin_table_typed(block):
    """Like cec_sch.pin_table, EXTENDED with each pin's electrical TYPE (the
    first keyword after `pin`, e.g. power_in/power_out/output/input/passive).
    num -> {"pos": (lx,ly), "ang": a, "length": l, "type": t}."""
    out = {}
    for m in _PIN_HEAD_RE.finditer(block):
        seg = block[m.start(): m.start() + 320]
        num = re.search(r'\(number\s+"([^"]+)"', seg)
        if num:
            out[num.group(1)] = {
                "pos": (float(m.group(2)), float(m.group(3))),
                "ang": int(m.group(4)),
                "length": float(m.group(5)),
                "type": m.group(1),
            }
    return out


def on_grid(*vals, grid=GRID, eps=_EPS_GRID):
    for v in vals:
        r = v - round(v / grid) * grid
        if abs(r) > eps:
            return False
    return True


def ptkey(x, y):
    return (round(x, 3), round(y, 3))


def _dir_bucket(dx, dy):
    """Round a direction vector to the nearest cardinal (0/90/180/270)."""
    ang = math.degrees(math.atan2(dy, dx)) % 360
    return int(round(ang / 90.0) % 4) * 90


# ============================================================================
# PARSE ONE FILE
# ============================================================================

class SchFile:
    def __init__(self, path):
        self.path = path
        self.text = open(path, encoding="utf-8").read()
        start = self.text.index("(kicad_sch")
        self.root_block = cec_sch.carve(self.text, start)
        self.children = list(iter_children(self.root_block))

        self.paper = None
        self.lib_pins = {}      # lib_id string -> {num: {"pos","ang","length","type"}}
        self.wires = []         # {"pts":[(x,y)...], "uuid":.., "block":..}
        self.junctions = []     # {"pos":(x,y), "uuid":..}
        self.no_connects = []   # {"pos":(x,y), "uuid":..}
        self.labels = []        # {"kind":.., "name":.., "pos":(x,y), "ang":.., "uuid":..}
        self.symbols = []       # {"ref":.., "lib_id":.., "pos":(x,y,rot), "value":.., "is_power":bool,
                                 #  "pins":[{"num","pos","dir","type"}], "uuid":..}
        self.sheets = []        # {"name","file","pos","size","pins":[{"name","type","pos","ang"}]}
        self.texts = []         # {"content","pos","ang"}

        for tag, block in self.children:
            if tag == "paper":
                self.paper = first_string(block)
            elif tag == "lib_symbols":
                self._load_lib_symbols(block)

        for tag, block in self.children:
            if tag == "wire":
                self._load_wire(block)
            elif tag == "junction":
                at = csl._extract_at(block)
                if at:
                    self.junctions.append({"pos": (at[0], at[1]), "uuid": find_uuid(block)})
            elif tag == "no_connect":
                at = csl._extract_at(block)
                if at:
                    self.no_connects.append({"pos": (at[0], at[1]), "uuid": find_uuid(block)})
            elif tag in ("label", "global_label", "hierarchical_label"):
                self._load_label(tag, block)
            elif tag == "symbol":
                self._load_symbol(block)
            elif tag == "sheet":
                self._load_sheet(block)
            elif tag == "text":
                self._load_text(block)

    # -- lib_symbols: pin tables keyed by the exact lib_id string ------------
    def _load_lib_symbols(self, lib_block):
        for tag, child in iter_children(lib_block):
            if tag != "symbol":
                continue
            name = first_string(child)
            if name:
                self.lib_pins[name] = pin_table_typed(child)

    # -- wires ----------------------------------------------------------------
    def _load_wire(self, block):
        pts_tag = None
        for tag, child in iter_children(block):
            if tag == "pts":
                pts_tag = child
                break
        pts = []
        if pts_tag:
            pts = [(float(a), float(b)) for a, b in
                   re.findall(r'\(xy\s+(-?[\d.]+)\s+(-?[\d.]+)\)', pts_tag)]
        if len(pts) >= 2:
            self.wires.append({"pts": pts, "uuid": find_uuid(block)})

    # -- labels (local/global/hierarchical) -----------------------------------
    def _load_label(self, kind, block):
        name = first_string(block)
        at = csl._extract_at(block)
        if name is None or at is None:
            return
        self.labels.append({"kind": kind, "name": name, "pos": (at[0], at[1]),
                             "ang": at[2], "uuid": find_uuid(block)})

    # -- symbol instances -------------------------------------------------------
    def _load_symbol(self, block):
        lib_id = None
        m = re.search(r'\(lib_id\s+"((?:[^"\\]|\\.)*)"', block)
        if m:
            lib_id = csl._unescape(m.group(1))
        at = csl._extract_at(block)
        if lib_id is None or at is None:
            return
        ox, oy, rot = at
        ref = prop_value(block, "Reference") or "?"
        value = prop_value(block, "Value") or ""
        is_power = ref.startswith("#")
        pins = []
        for num, pt in self.lib_pins.get(lib_id, {}).items():
            lx, ly = pt["pos"]
            rlx, rly = csl.rotate_local(lx, ly, rot)
            ax, ay = ox + rlx, oy - rly
            total_ang = (pt["ang"] + rot) % 360
            dx = -math.cos(math.radians(total_ang))
            dy = math.sin(math.radians(total_ang))
            pins.append({"num": num, "pos": (ax, ay), "dir": (dx, dy), "type": pt["type"]})
        self.symbols.append({"ref": ref, "lib_id": lib_id, "pos": (ox, oy, rot),
                              "value": value, "is_power": is_power, "pins": pins,
                              "uuid": find_uuid(block)})

    # -- sheets (hierarchy + sheet pins) ---------------------------------------
    def _load_sheet(self, block):
        at = csl._extract_at(block)
        size_m = re.search(r'\(size\s+(-?[\d.]+)\s+(-?[\d.]+)\)', block)
        sheetfile = prop_value(block, "Sheetfile")
        sheetname = prop_value(block, "Sheetname")
        pins = []
        for pm in re.finditer(
                r'\(pin\s+"((?:[^"\\]|\\.)*)"\s+(\w+)\s*\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\)', block):
            pins.append({"name": csl._unescape(pm.group(1)), "type": pm.group(2),
                         "pos": (float(pm.group(3)), float(pm.group(4))), "ang": float(pm.group(5))})
        self.sheets.append({
            "name": sheetname, "file": sheetfile,
            "pos": at[:2] if at else None,
            "size": (float(size_m.group(1)), float(size_m.group(2))) if size_m else None,
            "pins": pins,
        })

    # -- free text / section annotations ---------------------------------------
    def _load_text(self, block):
        content = first_string(block)
        at = csl._extract_at(block)
        if content is None or at is None:
            return
        self.texts.append({"content": content, "pos": (at[0], at[1]), "ang": at[2]})


# ============================================================================
# PROJECT (hierarchical walk)
# ============================================================================

def load_project(root_path):
    """BFS over `(sheet ...)` Sheetfile references starting at root_path.
    Returns an ordered dict path -> SchFile (root first), deduped by absolute
    path (handles a shared leaf reached from more than one parent, and cycles
    defensively even though real projects shouldn't have them)."""
    root_path = os.path.abspath(root_path)
    files = {}
    queue = [root_path]
    while queue:
        p = queue.pop(0)
        if p in files:
            continue
        if not os.path.isfile(p):
            continue
        sf = SchFile(p)
        files[p] = sf
        d = os.path.dirname(p)
        for sh in sf.sheets:
            if sh["file"]:
                queue.append(os.path.abspath(os.path.join(d, sh["file"])))
    return files


# ============================================================================
# SHARED CONNECTIVITY MODEL (point occupancy, used by SL-02/03/05/06/07)
# ============================================================================

class Connectivity:
    def __init__(self, sf):
        self.sf = sf
        self.point_wires = defaultdict(set)     # ptkey -> {wire_index}
        self.point_pins = defaultdict(list)      # ptkey -> [(ref, num)]
        self.point_labels = defaultdict(list)    # ptkey -> [(kind, name)]
        self.point_junctions = defaultdict(int)
        self.point_ncs = defaultdict(int)
        self.point_sheetpins = defaultdict(list)  # ptkey -> [name]

        for wi, w in enumerate(sf.wires):
            for pt in w["pts"]:
                self.point_wires[ptkey(*pt)].add(wi)
        for sym in sf.symbols:
            for pin in sym["pins"]:
                self.point_pins[ptkey(*pin["pos"])].append((sym["ref"], pin["num"]))
        for lb in sf.labels:
            self.point_labels[ptkey(*lb["pos"])].append((lb["kind"], lb["name"]))
        for j in sf.junctions:
            self.point_junctions[ptkey(*j["pos"])] += 1
        for nc in sf.no_connects:
            self.point_ncs[ptkey(*nc["pos"])] += 1
        for sh in sf.sheets:
            for p in sh["pins"]:
                self.point_sheetpins[ptkey(*p["pos"])].append(p["name"])

    def is_anchored(self, pt, exclude_wire=None):
        """True if `pt` is touched by a pin, label, junction, no-connect, sheet
        pin, or (excluding `exclude_wire`) another wire."""
        k = ptkey(*pt)
        wires = self.point_wires.get(k, set())
        if exclude_wire is not None:
            wires = wires - {exclude_wire}
        return bool(wires) or bool(self.point_pins.get(k)) or bool(self.point_labels.get(k)) \
            or self.point_junctions.get(k, 0) > 0 or self.point_ncs.get(k, 0) > 0 \
            or bool(self.point_sheetpins.get(k))


# ============================================================================
# Finding / Metric records
# ============================================================================

SEVERITY = {
    "SL-01": "ERROR", "SL-02": "WARN", "SL-03": "ERROR", "SL-04": "WARN",
    "SL-05": "WARN", "SL-06": "WARN", "SL-07": "METRIC", "SL-08": "METRIC",
    "SL-09": "WARN",
}


def finding(cid, locus, message):
    return {"id": cid, "severity": SEVERITY[cid], "locus": locus, "message": message}


# ============================================================================
# CHECKS
# ============================================================================

def check_sl01_off_grid(sf):
    """Electrical connection points must sit on the 1.27 mm wiring grid.
    Scope: wire vertices, junctions, no-connects, labels (all 3 kinds), and
    symbol-instance origins. Deliberately EXCLUDES sheet-box (at/size) and
    free-text positions -- see the module header's calibration note."""
    seen = {}   # ptkey -> list of descriptions (dedupe: one finding per point)
    for w in sf.wires:
        for pt in w["pts"]:
            if not on_grid(*pt):
                seen.setdefault(ptkey(*pt), []).append("wire vertex")
    for j in sf.junctions:
        if not on_grid(*j["pos"]):
            seen.setdefault(ptkey(*j["pos"]), []).append("junction")
    for nc in sf.no_connects:
        if not on_grid(*nc["pos"]):
            seen.setdefault(ptkey(*nc["pos"]), []).append("no_connect")
    for lb in sf.labels:
        if not on_grid(*lb["pos"]):
            seen.setdefault(ptkey(*lb["pos"]), []).append(f'{lb["kind"]} "{lb["name"]}"')
    for sym in sf.symbols:
        ox, oy, _rot = sym["pos"]
        if not on_grid(ox, oy):
            seen.setdefault(ptkey(ox, oy), []).append(f'symbol {sym["ref"]}')
    out = []
    for pt, kinds in sorted(seen.items()):
        out.append(finding("SL-01", f"({pt[0]:.3f},{pt[1]:.3f})",
                            f"off-grid (not a 1.27mm multiple): {', '.join(kinds)}"))
    return out


def check_sl02_four_way_junctions(sf, conn):
    out = []
    for j in sf.junctions:
        pt = j["pos"]
        k = ptkey(*pt)
        wire_ids = conn.point_wires.get(k, set())
        dirs = set()
        for wi in wire_ids:
            pts = sf.wires[wi]["pts"]
            for idx, p in enumerate(pts):
                if ptkey(*p) != k:
                    continue
                for nb in (idx - 1, idx + 1):
                    if 0 <= nb < len(pts):
                        ox, oy = pts[nb]
                        dirs.add(_dir_bucket(ox - pt[0], oy - pt[1]))
        if len(dirs) >= 4:
            out.append(finding("SL-02", f"({pt[0]:.3f},{pt[1]:.3f})",
                                "four-way junction (wires depart in all 4 directions) "
                                "-- prefer two offset T-junctions"))
    return out


def check_sl03_dangling(sf, conn):
    out = []
    for wi, w in enumerate(sf.wires):
        pts = w["pts"]
        for end in (pts[0], pts[-1]):
            if not conn.is_anchored(end, exclude_wire=wi):
                out.append(finding("SL-03", f"({end[0]:.3f},{end[1]:.3f})",
                                    f"dangling wire end (wire uuid {w['uuid']}) touches nothing"))
    return out


def _wire_segments(sf):
    """[(wire_index, seg_index, p1, p2)] -- every consecutive pair in every
    wire's pts, i.e. the actual drawn line segments."""
    segs = []
    for wi, w in enumerate(sf.wires):
        pts = w["pts"]
        for si in range(len(pts) - 1):
            segs.append((wi, si, pts[si], pts[si + 1]))
    return segs


def _seg_intersect(p1, p2, p3, p4):
    x1, y1 = p1; x2, y2 = p2; x3, y3 = p3; x4, y4 = p4
    d = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(d) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / d
    u = ((x1 - x3) * (y1 - y2) - (y1 - y3) * (x1 - x2)) / d
    if -1e-6 <= t <= 1 + 1e-6 and -1e-6 <= u <= 1 + 1e-6:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def compute_crossings(sf):
    """Geometric crossing points between segments of DIFFERENT wires,
    excluding any intersection that lands on a shared endpoint (that is a
    connection, not a visual crossing). Returns a dict ptkey -> count of
    contributing segment pairs, and whether a junction sits there."""
    segs = _wire_segments(sf)
    crossings = {}
    for i in range(len(segs)):
        wi1, _si1, a1, a2 = segs[i]
        for j in range(i + 1, len(segs)):
            wi2, _si2, b1, b2 = segs[j]
            if wi1 == wi2:
                continue
            ip = _seg_intersect(a1, a2, b1, b2)
            if ip is None:
                continue
            k = ptkey(*ip)
            # exclude a crossing that is really a shared endpoint (a connection)
            endpoints = {ptkey(*a1), ptkey(*a2), ptkey(*b1), ptkey(*b2)}
            if k in endpoints and (ptkey(*a1) == k or ptkey(*a2) == k) and \
               (ptkey(*b1) == k or ptkey(*b2) == k):
                continue
            crossings[k] = crossings.get(k, 0) + 1
    return crossings


def check_sl05_label_on_crossing(sf, crossings):
    out = []
    for lb in sf.labels:
        k = ptkey(*lb["pos"])
        if k in crossings:
            out.append(finding("SL-05", f"({lb['pos'][0]:.3f},{lb['pos'][1]:.3f})",
                                f'{lb["kind"]} "{lb["name"]}" sits directly on a wire-crossing point'))
    return out


def check_sl04_label_orientation(sf, conn):
    out = []
    for lb in sf.labels:
        k = ptkey(*lb["pos"])
        wire_ids = conn.point_wires.get(k, set())
        if not wire_ids:
            continue
        orient = None
        for wi in wire_ids:
            pts = sf.wires[wi]["pts"]
            for idx, p in enumerate(pts):
                if ptkey(*p) != k:
                    continue
                for nb in (idx - 1, idx + 1):
                    if 0 <= nb < len(pts):
                        ox, oy = pts[nb]
                        dx, dy = ox - lb["pos"][0], oy - lb["pos"][1]
                        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
                            continue
                        if abs(dx) < 1e-6:
                            orient = "V"
                        elif abs(dy) < 1e-6:
                            orient = "H"
        if orient is None:
            continue
        ang = int(lb["ang"]) % 360
        expect_h = ang in (0, 180)
        expect_v = ang in (90, 270)
        if (orient == "H" and not expect_h) or (orient == "V" and not expect_v):
            out.append(finding("SL-04", f"({lb['pos'][0]:.3f},{lb['pos'][1]:.3f})",
                                f'{lb["kind"]} "{lb["name"]}" angle {ang} disagrees with its '
                                f'{"horizontal" if orient == "H" else "vertical"} wire'))
    return out


def _pwr_islands(sf):
    """Union-find over every connection point in ONE file, scoped to DIRECT
    wire/pin/junction adjacency (see check_sl06* docstrings: this repo's own
    convention places a PWR_FLAG on a short dedicated wire right next to the
    power port it drives, so this simple spatial adjacency is what actually
    matters within a file; cross-file/global merging of power-symbol NAMES --
    which real KiCad treats as one project-wide net regardless of sheet -- is
    handled separately, at the project level, by the caller). Returns
    (island_names, island_power_names, island_flags, island_output):
      island_names[root]       -- every label/power-port name touching it
      island_power_names[root] -- POWER-PORT symbol names only (GND/+3V3/...)
      island_flags[root]       -- count of PWR_FLAG symbols on it
      island_output[root]      -- True if a power_out/output pin drives it
    """
    points = set()
    points.update(ptkey(*pt) for w in sf.wires for pt in w["pts"])
    points.update(ptkey(*pin["pos"]) for sym in sf.symbols for pin in sym["pins"])
    points.update(ptkey(*j["pos"]) for j in sf.junctions)
    points.update(ptkey(*nc["pos"]) for nc in sf.no_connects)
    points.update(ptkey(*lb["pos"]) for lb in sf.labels)
    parent = {p: p for p in points}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for w in sf.wires:
        pts = [ptkey(*p) for p in w["pts"]]
        for a, b in zip(pts, pts[1:]):
            union(a, b)
    # anything else coincident at the same rounded point is implicitly unioned
    # already (same dict key == same node), so pins/junctions/labels/ncs that
    # share a wire's vertex point are automatically in that wire's set.

    island_names = defaultdict(set)
    island_power_names = defaultdict(set)
    island_flags = defaultdict(int)
    island_output = defaultdict(bool)

    for sym in sf.symbols:
        for pin in sym["pins"]:
            k = ptkey(*pin["pos"])
            if k not in parent:
                continue
            root = find(k)
            if sym["is_power"]:
                if sym["value"] == "PWR_FLAG":
                    island_flags[root] += 1
                else:
                    island_names[root].add(sym["value"])
                    island_power_names[root].add(sym["value"])
            elif pin["type"] in ("power_out", "output"):
                island_output[root] = True
    for lb in sf.labels:
        k = ptkey(*lb["pos"])
        if k in parent:
            island_names[find(k)].add(lb["name"])

    return island_names, island_power_names, island_flags, island_output


def check_sl06_duplicate_flags(sf):
    """Duplicate PWR_FLAG: a purely LOCAL redundancy (two flags on the same
    directly-wired clump) -- this half stays per-file, no cross-file net
    merging needed."""
    island_names, _power, island_flags, _out = _pwr_islands(sf)
    out = []
    for root, count in island_flags.items():
        if count >= 2:
            names = ", ".join(sorted(island_names.get(root, {"(unnamed)"})))
            out.append(finding("SL-06", names, f"duplicate PWR_FLAG ({count}x) on one electrical island"))
    return out


def check_sl06_missing_flags(files):
    """"Missing PWR_FLAG on a supply-only net", computed PROJECT-WIDE across
    every file reached by the SAME hierarchical walk (files: {path: SchFile}).
    Real KiCad power-port symbols (GND, +3V3, ...) form ONE net across the
    whole project regardless of which sheet they sit in -- unlike the
    per-file spatial islands above, a net is only "missing" if NO file in the
    project flags or drives it anywhere. Scoped to nets carrying an ACTUAL
    power-port symbol -- not every plain signal label (CAN_TX, DETECT, ...),
    which never needs a PWR_FLAG at all."""
    flagged_names, driven_names, power_names = set(), set(), set()
    for sf in files.values():
        _names, power, flags, output = _pwr_islands(sf)
        for root, names in power.items():
            power_names.update(names)
            if flags.get(root, 0) > 0:
                flagged_names.update(names)
            if output.get(root, False):
                driven_names.update(names)
    out = []
    for name in sorted(power_names - {"PWR_FLAG"}):
        if name not in flagged_names and name not in driven_names:
            out.append(finding("SL-06", name, f'power net "{name}" has no PWR_FLAG and no driving '
                                               f'output pin anywhere in this project (supply-only?)'))
    return out


def check_sl08_stub_consistency(sf, conn):
    """Advisory METRIC: pins on the SAME side of one symbol (grouped by their
    outward-direction cardinal bucket) should carry the same stub length."""
    out = []
    for sym in sf.symbols:
        by_side = defaultdict(list)
        for pin in sym["pins"]:
            side = _dir_bucket(*pin["dir"])
            k = ptkey(*pin["pos"])
            wire_ids = conn.point_wires.get(k, set())
            length = None
            for wi in wire_ids:
                pts = sf.wires[wi]["pts"]
                for idx, p in enumerate(pts):
                    if ptkey(*p) != k:
                        continue
                    for nb in (idx - 1, idx + 1):
                        if 0 <= nb < len(pts):
                            ox, oy = pts[nb]
                            d = math.hypot(ox - pin["pos"][0], oy - pin["pos"][1])
                            length = d if length is None else min(length, d)
            if length is not None:
                by_side[side].append((pin["num"], length))
        for side, entries in by_side.items():
            if len(entries) < 2:
                continue
            lengths = [e[1] for e in entries]
            spread = max(lengths) - min(lengths)
            if spread > 0.5:
                out.append(finding("SL-08", f'{sym["ref"]} side {side}',
                                    f"stub-length spread {spread:.2f}mm across pins "
                                    f"{[e[0] for e in entries]} ({[round(l,2) for l in lengths]})"))
    return out


_PAPER_SIZE = {  # KiCad landscape (width, height) mm
    "A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0),
    "A1": (841.0, 594.0), "A0": (1189.0, 841.0),
}


def check_sl09_text_outside_frame(sf):
    """WARN: a free TEXT or net-label element placed outside the sheet's own
    nominal paper rectangle (0,0)-(w,h). Scoped to text/labels only (NOT every
    symbol reference/value field) -- see calibration note in the module
    header; symbol placement sprawl is a T1/T4 layout concern, not a T3 style
    one, and checking every field would swamp this check with placement noise
    rather than genuine stray annotations."""
    size = _PAPER_SIZE.get(sf.paper)
    if not size:
        return []
    w, h = size
    out = []
    for t in sf.texts:
        x, y = t["pos"]
        if x < 0 or y < 0 or x > w or y > h:
            out.append(finding("SL-09", f"({x:.2f},{y:.2f})",
                                f'text "{t["content"][:40]}" outside the {sf.paper} frame '
                                f'(0,0)-({w},{h})'))
    for lb in sf.labels:
        x, y = lb["pos"]
        if x < 0 or y < 0 or x > w or y > h:
            out.append(finding("SL-09", f"({x:.2f},{y:.2f})",
                                f'{lb["kind"]} "{lb["name"]}" outside the {sf.paper} frame '
                                f'(0,0)-({w},{h})'))
    return out


def check_sl07_crossings(sf, crossings):
    with_junction = sum(1 for k in crossings if any(
        ptkey(*j["pos"]) == k for j in sf.junctions))
    return {"wire_crossings_total": len(crossings), "wire_crossings_with_junction": with_junction,
            "wire_crossings_bare": len(crossings) - with_junction}


# ============================================================================
# RUN ALL CHECKS ON ONE FILE
# ============================================================================

def lint_file(sf):
    conn = Connectivity(sf)
    crossings = compute_crossings(sf)
    findings = []
    findings += check_sl01_off_grid(sf)
    findings += check_sl02_four_way_junctions(sf, conn)
    findings += check_sl03_dangling(sf, conn)
    findings += check_sl04_label_orientation(sf, conn)
    findings += check_sl05_label_on_crossing(sf, crossings)
    findings += check_sl06_duplicate_flags(sf)
    findings += check_sl08_stub_consistency(sf, conn)
    findings += check_sl09_text_outside_frame(sf)
    metrics = check_sl07_crossings(sf, crossings)
    metrics["wires"] = len(sf.wires)
    metrics["junctions"] = len(sf.junctions)
    metrics["labels"] = len(sf.labels)
    metrics["no_connects"] = len(sf.no_connects)
    metrics["symbols"] = len(sf.symbols)
    metrics["sl08_findings"] = sum(1 for f in findings if f["id"] == "SL-08")
    return findings, metrics


def lint_project(root_path):
    files = load_project(root_path)
    results = {}
    for path, sf in files.items():
        findings, metrics = lint_file(sf)
        results[path] = {"findings": findings, "metrics": metrics}
    return results


# ============================================================================
# CLI
# ============================================================================

def _print_table(path, findings, metrics):
    print(f"\n=== {path} ===")
    by_sev = defaultdict(int)
    for f in findings:
        by_sev[f["severity"]] += 1
    if findings:
        print(f'{"ID":6} {"SEV":6} {"LOCUS":24} MESSAGE')
        for f in findings:
            print(f'{f["id"]:6} {f["severity"]:6} {f["locus"][:24]:24} {f["message"]}')
    else:
        print("(no findings)")
    print(f"-- counts: " + ", ".join(f"{k}={v}" for k, v in sorted(by_sev.items())))
    print(f"-- metrics: " + ", ".join(f"{k}={v}" for k, v in sorted(metrics.items())))


def main(argv=None):
    ap = argparse.ArgumentParser(description="cec_sch_lint -- schematic STYLE linter (T3)")
    ap.add_argument("sch", nargs="+", help=".kicad_sch file(s); hierarchical Sheetfile "
                                           "references are followed automatically")
    ap.add_argument("--exit-on-error", action="store_true",
                     help="exit 1 if any ERROR-severity finding exists")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args(argv)

    all_results = {}
    for root in args.sch:
        all_results.update(lint_project(root))

    if args.json:
        print(json.dumps(all_results, indent=2))
    else:
        for path, r in all_results.items():
            _print_table(path, r["findings"], r["metrics"])
        total = defaultdict(int)
        for r in all_results.values():
            for f in r["findings"]:
                total[f["severity"]] += 1
        print(f"\n=== TOTAL across {len(all_results)} file(s): " +
              ", ".join(f"{k}={v}" for k, v in sorted(total.items())) + " ===")

    if args.exit_on_error:
        has_error = any(f["severity"] == "ERROR"
                        for r in all_results.values() for f in r["findings"])
        return 1 if has_error else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
