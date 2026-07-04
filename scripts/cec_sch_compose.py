#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_sch_compose -- HIERARCHICAL SCHEMATIC COMPOSITION ENGINE (shared)
# ============================================================================
# Promoted 2026-07-03 from hubs/hub-enterprise/build_lib.py (T4 start, per the
# schematic-quality charter): the board-AGNOSTIC mechanisms for assembling a
# genuine multi-level hierarchy (root -> thin parent -> leaf sheets, or a
# root that IS the thin parent) out of composed leaf layouts. Reuses
# scripts/cec_sch.py's low-level primitives (symbol embedding, pin geometry,
# wire/label/power-port emission) and scripts/cec_sch_layout.py (the T1
# engine: rotation-aware pin math, place_decouplers/wire_decouplers,
# nudge_texts) but supplies its OWN top-level orchestration because
# cec_sch.build_schematic() assumes a flat, single-sheet project (its own
# file IS the project root). First proven on hubs/hub-enterprise (sheet 01:
# root -> 01-power-input thin parent -> 01a..01g leaves); generalization
# proof: modules/ent-common (root-as-thin-parent -> 6 leaves).
#
# Addressing rules (KiCad 10 hierarchical sheet addressing):
#   - A component's `instances.path` is the chain of SHEET-SYMBOL uuids from
#     the PROJECT ROOT's own uuid down through every intervening sheet symbol
#     to the sheet symbol that places the leaf's file, e.g.
#     "/<ROOT_UUID>/<01-in-root-uuid>/<01a-in-01-uuid>".
#   - A file's OWN `sheet_instances` footer path is that SAME chain but
#     WITHOUT the leading ROOT_UUID segment (root's own identity is implicit;
#     only sheet-symbol uuids are listed), e.g. "/<01-in-root-uuid>/<01a-in-01-uuid>".
#   - A file's own top-level `(uuid ...)` header is a private identity for
#     that file alone -- never referenced elsewhere, does not need to be
#     stable, but is kept fixed by callers for deterministic regeneration.
#   - `hierarchical_label`s inside a file correspond, by NAME, to `pin`s on
#     the `(sheet ...)` block that instantiates that file one level up. The
#     established convention (hub-enterprise, preserved here) is that every
#     crossing uses shape "output" on both ends.
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import cec_sch  # noqa: E402
import cec_sch_layout  # noqa: E402  -- the T1 layout engine (charter integration)

# Paper sizes (mm, landscape) for the content-centering pass.
PAPER = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0)}

# Accent colors (docs/schematic-composition-standard.md S13; verified rendered
# by the pinned kicad-cli 10 SVG export -- stroke:#1A5FB4 confirmed): muted
# blue captions, dark-green notes/region titles, per the Nuand reference.
CAPTION_COLOR = (26, 95, 180, 1)
NOTE_COLOR = (21, 96, 61, 1)


def _color_sexpr(color):
    if not color:
        return ""
    r, g, b, a = color
    return f" (color {r} {g} {b} {a})"


def emit_caption(text, x, y, size=2.0, color=CAPTION_COLOR, bold=True):
    """Bold section caption (standard S3): one per functional block."""
    esc = (text.replace("\\", "\\\\").replace('"', '\\"')
           .replace("\n", "\\n"))     # KiCad stores multi-line text as literal \n
    boldpart = " (thickness 0.35) (bold yes)" if bold else ""
    return (f'\t(text "{esc}"\n\t\t(exclude_from_sim no)\n'
            f'\t\t(at {cec_sch.f(x)} {cec_sch.f(y)} 0)\n'
            f'\t\t(effects (font (size {cec_sch.f(size)} {cec_sch.f(size)})'
            f'{boldpart}{_color_sexpr(color)}) (justify left top))\n'
            f'\t\t(uuid "{cec_sch.u()}")\n\t)')


def emit_note(text, x, y, size=1.27, color=NOTE_COLOR):
    """Free-text design note / computed-value annotation (standard S10)."""
    return emit_caption(text, x, y, size=size, color=color, bold=False)


def emit_region(title, x0, y0, x1, y1, color=NOTE_COLOR):
    """Dashed accent frame + colored title grouping a sub-function WITHIN a
    sheet (standard S11 -- an accent, never a substitute for a real sheet)."""
    return (
        f'\t(rectangle\n\t\t(start {cec_sch.f(x0)} {cec_sch.f(y0)})\n'
        f'\t\t(end {cec_sch.f(x1)} {cec_sch.f(y1)})\n'
        f'\t\t(stroke (width 0.1524) (type dash){_color_sexpr(color)})\n'
        f'\t\t(fill (type none))\n\t\t(uuid "{cec_sch.u()}")\n\t)\n'
        + emit_caption(title, x0 + 1.27, y0 + 1.27, size=1.6, color=color))


# ===========================================================================
# Leaf -- one functional-block sheet: its own parts/nets/composed layout.
# (Promoted from gen_hub_enterprise.py's Leaf; pure data holder.)
# ===========================================================================
class Leaf:
    def __init__(self, id_, filename, sheetname, desc):
        self.id = id_
        self.filename = filename
        self.sheetname = sheetname
        self.desc = desc
        self.parts, self.nets, self.footprints, self.props = {}, {}, {}, {}
        self.placement, self.nc_skip = {}, set()
        self.hier_exports = {}       # net -> ("output", (ref, pin))
        self.powerflag_nets = []
        self.layout = None           # composed drawn structure (see build_leaf)

    def add_part(self, ref, lib, name, value, x, y, fp, props=None):
        self.parts[ref] = (lib, name, value)
        self.placement[ref] = (x, y)
        self.footprints[ref] = fp
        if props:
            self.props[ref] = props

    def net(self, name, *conns):
        self.nets.setdefault(name, [])
        for c in conns:
            self.nets[name].append(c)


# ===========================================================================
# Compose -- collects a leaf's composed structure in 1.27mm GRID UNITS and
# emits the mm-space `layout` dict build_leaf consumes. Coordinates designed
# in grid units guarantee every wire endpoint, pin, and junction lands
# exactly on the schematic grid; the leaf builder then centers the whole
# composition on the page. Pin math is cec_sch_layout.pin_abs_rot (rotation
# round-trip verified). (Promoted from gen_hub_enterprise.py's _Compose.)
# ===========================================================================
class Compose:
    def __init__(self, lf, libs):
        self.lf = lf
        self.used = cec_sch.load_symbols(libs, lf.parts)
        self.wires, self.labels, self.power = [], [], []
        self.hier_at, self.consumed, self.text_side = {}, set(), {}
        self.rails = []
        self.texts, self.regions = [], []
        self.io_sides, self.io_from = {}, {}

    def place(self, ref, xu, yu, rot=0):
        assert ref in self.lf.parts, ref
        U = cec_sch.GRID
        self.lf.placement[ref] = (xu * U, yu * U, rot)

    def place_pin(self, ref, num, xu, yu, rot=0):
        """Place `ref` so that PIN `num` lands exactly at (xu, yu) -- the
        flow-baseline primitive (standard S2: chains align by PIN ROW, not by
        symbol origin). Rotation uses the validated cec_sch_layout convention."""
        assert ref in self.lf.parts, ref
        U = cec_sch.GRID
        lib, name, _v = self.lf.parts[ref]
        lx, ly, _a, _l = self.used[(lib, name)]["pins"][num]
        rlx, rly = cec_sch_layout.rotate_local(lx, ly, rot)
        self.lf.placement[ref] = (xu * U - rlx, yu * U + rly, rot)
        return self.pin(ref, num)

    def caption(self, text, xu, yu, size=2.0):
        """Bold section caption (standard S3), top-left anchored."""
        U = cec_sch.GRID
        self.texts.append(("caption", text, xu * U, yu * U, size))

    def note(self, text, xu, yu, size=1.27):
        """Design note / computed-value annotation (standard S10). Text must
        come from EXISTING desc/BOM knowledge -- never a new claim."""
        U = cec_sch.GRID
        self.texts.append(("note", text, xu * U, yu * U, size))

    def region(self, title, x0u, y0u, x1u, y1u):
        """Dashed accent frame + title around a sub-function (standard S11)."""
        U = cec_sch.GRID
        self.regions.append((title, x0u * U, y0u * U, x1u * U, y1u * U))

    def io(self, net, side, from_pt=None):
        """Declare an off-sheet net for the EDGE-ANCHORED I/O column pass
        (standard S1): its hierarchical label is gathered into the sheet's
        left/right column, wired from the anchor-pin stub (default) or from
        `from_pt` (grid units -- a composed wire endpoint, e.g. a chain end)."""
        assert net in self.lf.hier_exports, net
        assert side in ("left", "right"), side
        U = cec_sch.GRID
        self.io_sides[net] = side
        if from_pt is not None:
            self.io_from[net] = (from_pt[0] * U, from_pt[1] * U)

    def pin(self, ref, num):
        """Pin connection point of a placed (possibly rotated) part, in u."""
        U = cec_sch.GRID
        pl = {r: (v if len(v) == 3 else (*v, 0)) for r, v in self.lf.placement.items()}
        ax, ay, _dx, _dy = cec_sch_layout.pin_abs_rot(pl, self.used, self.lf.parts, ref, num)
        return round(ax / U), round(ay / U)

    def pin_out(self, ref, num):
        """(pin point in u, outward unit vector) -- for stub math."""
        U = cec_sch.GRID
        pl = {r: (v if len(v) == 3 else (*v, 0)) for r, v in self.lf.placement.items()}
        ax, ay, dx, dy = cec_sch_layout.pin_abs_rot(pl, self.used, self.lf.parts, ref, num)
        return (round(ax / U), round(ay / U)), (dx, dy)

    def wire(self, *pts_u):
        U = cec_sch.GRID
        for (x1, y1), (x2, y2) in zip(pts_u, pts_u[1:]):
            assert x1 == x2 or y1 == y2, f"non-Manhattan wire {pts_u}"
            self.wires.append((x1 * U, y1 * U, x2 * U, y2 * U))

    def label(self, net, xu, yu, ang):
        U = cec_sch.GRID
        self.labels.append((net, xu * U, yu * U, ang))

    def stamp(self, sym, xu, yu, rot):
        U = cec_sch.GRID
        self.power.append((sym, xu * U, yu * U, rot))

    def hier(self, net, xu, yu, ang=0):
        assert net in self.lf.hier_exports, net
        U = cec_sch.GRID
        self.hier_at[net] = (xu * U, yu * U, ang)

    def use(self, *pins):
        self.consumed.update(pins)

    def rail(self, ic, pin, caps, side="above", pitch=5.08, rise=7.62):
        """Decoupler-cluster archetype: a row of caps placed + WIRED at their
        owning IC's power pin through the T1 engine's place_decouplers/
        wire_decouplers pair (wrapped, not duplicated -- build_leaf realizes
        the plan post-centering so rail geometry and the translation can't
        drift apart). Marks the rail pins consumed."""
        self.rails.append({"ic": ic, "pin": pin, "caps": list(caps),
                           "side": side, "pitch": pitch, "rise": rise})
        self.use((ic, pin))
        for cap in caps:
            self.use((cap, "1"), (cap, "2"))

    def done(self):
        self.lf.layout = {
            "wires": self.wires, "labels": self.labels, "power": self.power,
            "hier_at": self.hier_at, "consumed": self.consumed,
            "text_side": self.text_side, "decoupler_rails": self.rails,
            "texts": self.texts, "regions": self.regions,
            "io_sides": self.io_sides, "io_from": self.io_from,
        }
        # every ref must have been explicitly (re)placed by the compose pass
        for r in self.lf.parts:
            assert len(self.lf.placement[r]) == 3, f"{self.lf.id}: {r} not composed"


def hier_label(name, shape, x, y, angle):
    just = "left" if angle in (0, 270) else "right"
    return (f'\t(hierarchical_label "{name}"\n'
            f'\t\t(shape {shape})\n'
            f'\t\t(at {cec_sch.f(x)} {cec_sch.f(y)} {angle})\n'
            f'\t\t(effects (font (size 1.27 1.27)) (justify {just}))\n'
            f'\t\t(uuid "{cec_sch.u()}")\n\t)')


def title_block(title, comment1="", comment2="", comment3="", rev="DRAFT",
                date="2026-07-02"):
    lines = ['\t(title_block\n',
             f'\t\t(title "{title}")\n',
             f'\t\t(date "{date}")\n',
             f'\t\t(rev "{rev}")\n',
             '\t\t(company "CEC")\n']
    for i, c in enumerate((comment1, comment2, comment3), 1):
        if c:
            lines.append(f'\t\t(comment {i} "{c}")\n')
    lines.append('\t)')
    return "".join(lines)


def _norm_placement(placement):
    """(x,y) or (x,y,rot) -> gridsnapped (x,y,rot) 3-tuples (rotation-aware
    placement, T1 integration: cec_sch_layout.pin_abs_rot consumes these)."""
    out = {}
    for r, v in placement.items():
        if len(v) == 2:
            x, y = v
            rot = 0
        else:
            x, y, rot = v
        gx, gy = cec_sch.gridsnap(x, y)
        out[r] = (gx, gy, rot % 360)
    return out


def _part_extent(used, parts, placement, ref, pad=8.0):
    """Absolute (xmin,xmax,ymin,ymax) covering the part body (or pin extents
    when the symbol draws no body rectangle) + `pad` for stubs/labels/stamps."""
    lib, name, _v = parts[ref]
    x, y, rot = placement[ref]
    bb = cec_sch_layout.body_box_abs(used[(lib, name)]["block"], x, y, rot)
    xs, ys = [], []
    if bb:
        xs += [bb[0], bb[1]]; ys += [bb[2], bb[3]]
    for pnum in used[(lib, name)]["pins"]:
        ax, ay, _dx, _dy = cec_sch_layout.pin_abs_rot(placement, used, parts, ref, pnum)
        xs.append(ax); ys.append(ay)
    return (min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad)


def _emit_symbol2(ref, lib, name, val, x, y, rot, pins, project, root, used_entry,
                  fp="", props=None, text_side="right"):
    """Rotation-aware symbol emission with COMPACT, geometry-aware Reference/
    Value field placement (vs cec_sch.emit_symbol's fixed +/-15.24mm offsets
    that read as floating text on a compact sheet):
      - 2-pin part, pins vertical  -> ref/value beside the body (text_side),
        left-justified, so the vertical wire stays clear;
      - 2-pin part, pins horizontal -> ref/value stacked ABOVE the body
        (wires typically run at pin level and hang below);
      - everything else (ICs)      -> ref/value stacked ABOVE the body/pins.
    Field text is deliberately anchored close; the cec_sch_layout nudge pass
    (charter T1 item 4) resolves any residual text-text collision."""
    val = cec_sch.fmt_value(name, val)
    props = props or {}
    pinblk = "\n".join(f'\t\t(pin "{n}" (uuid "{cec_sch.u()}"))' for n in pins)
    ds = props.get("Datasheet", "")
    extra = "".join(
        f'\t\t(property "{k}" "{v}" (at {cec_sch.f(x)} {cec_sch.f(y)} 0) '
        f'(effects (font (size 1.27 1.27)) (hide yes)))\n'
        for k, v in props.items()
        if k not in ("Datasheet", "Reference", "Value", "Footprint") and v)

    # pin geometry (absolute) for the field-placement decision
    tmp_place = {ref: (x, y, rot)}
    tmp_parts = {ref: (lib, name, val)}
    pin_pts = [cec_sch_layout.pin_abs_rot(tmp_place, {(lib, name): used_entry}, tmp_parts, ref, n)[:2]
               for n in pins]
    bb = cec_sch_layout.body_box_abs(used_entry["block"], x, y, rot)
    if bb:
        xmin, xmax, ymin, ymax = bb
    else:
        xmin = min(p[0] for p in pin_pts); xmax = max(p[0] for p in pin_pts)
        ymin = min(p[1] for p in pin_pts); ymax = max(p[1] for p in pin_pts)
        # pins stick out past the body; pull the estimate in by a pin length
        if xmax - xmin > 10:
            xmin += 5.08; xmax -= 5.08
    G = cec_sch.GRID
    if len(pins) <= 2 and abs(pin_pts[0][0] - pin_pts[-1][0]) < 0.01:
        # vertical 2-pin passive: fields beside the body, Value DIRECTLY
        # under Reference on the same side (standard S5 -- one convention)
        side = 1 if text_side == "right" else -1
        fx = (xmax + G) if side > 0 else (xmin - G)
        just = "left" if side > 0 else "right"
        fields = [("Reference", ref, fx, y - G, just),
                  ("Value", val, fx, y + G, just)]
    elif len(pins) <= 2:
        fields = [("Reference", ref, x, ymin - 5 * G, None),
                  ("Value", val, x, ymin - 3 * G, None)]
    else:
        fields = [("Reference", ref, x, ymin - 4 * G, None),
                  ("Value", val, x, ymin - 2 * G, None)]
    # KiCad renders a field at (symbol rotation + field angle): measured via
    # SVG export (rot-90 R_Small: field angle 0 -> rotate(-90) vertical text,
    # field angle 90 -> horizontal). Compensate so fields always read
    # horizontally regardless of the part's rotation.
    fang = 90 if (rot % 180) == 90 else 0
    fld = "".join(
        f'\t\t(property "{fn}" "{fv}" (at {cec_sch.f(fx)} {cec_sch.f(fy)} {fang}) '
        f'(effects (font (size 1.27 1.27))'
        + (f' (justify {fj})' if fj else "") + '))\n'
        for fn, fv, fx, fy, fj in fields)
    return (
        "\t(symbol\n"
        f'\t\t(lib_id "{lib}:{name}")\n'
        f"\t\t(at {cec_sch.f(x)} {cec_sch.f(y)} {cec_sch.f(rot % 360)})\n\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n"
        "\t\t(fields_autoplaced yes)\n"
        f'\t\t(uuid "{cec_sch.u()}")\n'
        f"{fld}"
        f'\t\t(property "Footprint" "{fp}" (at {cec_sch.f(x)} {cec_sch.f(y)} 0) '
        f'(effects (font (size 1.27 1.27)) (hide yes)))\n'
        f'\t\t(property "Datasheet" "{ds}" (at {cec_sch.f(x)} {cec_sch.f(y)} 0) '
        f'(effects (font (size 1.27 1.27)) (hide yes)))\n'
        f"{extra}"
        f"{pinblk}\n"
        f'\t\t(instances\n\t\t\t(project "{project}"\n\t\t\t\t'
        f'(path "/{root}" (reference "{ref}") (unit 1))\n\t\t\t)\n\t\t)\n'
        "\t)")


def _emit_power2(sym, x, y, rot, project, root, ref):
    """Like cec_sch.emit_global_power but with the Value text placed on the
    GRAPHIC side of the symbol (away from the wire), so a stamp at the top of
    a riser doesn't drop its name text onto the wire below it. Graphic-above
    happens at rot 0 for rail/flag symbols (local +y art) and rot 180 for GND
    (local -y art)."""
    graphic_above = (rot % 360 == 0) if sym != "GND" else (rot % 360 == 180)
    vy = y - 5.08 if graphic_above else y + 5.08
    return (
        "\t(symbol\n"
        f'\t\t(lib_id "cec-power:{sym}")\n'
        f"\t\t(at {cec_sch.f(x)} {cec_sch.f(y)} {rot})\n\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n"
        f'\t\t(uuid "{cec_sch.u()}")\n'
        f'\t\t(property "Reference" "{ref}" (at {cec_sch.f(x)} {cec_sch.f(y - 2.54)} 0) '
        f'(effects (font (size 1.27 1.27)) (hide yes)))\n'
        f'\t\t(property "Value" "{sym}" (at {cec_sch.f(x)} {cec_sch.f(vy)} 0) '
        f'(effects (font (size 1.27 1.27))))\n'
        f'\t\t(pin "1" (uuid "{cec_sch.u()}"))\n'
        f'\t\t(instances\n\t\t\t(project "{project}"\n\t\t\t\t'
        f'(path "/{root}" (reference "{ref}") (unit 1))\n\t\t\t)\n\t\t)\n'
        "\t)")


def _port_rot(port, dx, dy):
    """Stamp rotation so the symbol GRAPHIC extends AWAY from the wire the
    stamp terminates: a rail stamp above an upward stub reads arrow-up; below
    a downward stub, arrow-down. (The old fixed 0/180 rule drew an upward
    rail stamp's art back down over its own stub.)"""
    if port == "GND":
        return 180 if dy < 0 else 0          # stub upward -> art up, else down
    return 0 if dy < 0 else 180              # rail: stub upward -> art up


_WIRE_XY = re.compile(r'\(xy\s+(-?[\d.]+)\s+(-?[\d.]+)\)')


def _auto_junctions(wire_strs, pin_pts, explicit=()):
    """Junction dots derived from the FINAL wire set: a dot wherever >=3 wire
    ends meet, or where 2 wire ends meet AT a component pin (a T onto a pin).
    Simple corners (2 ends, no pin) get no dot. Explicit junction strings
    (e.g. from cec_sch_layout.wire_decouplers) are merged, deduped by coord."""
    ends = {}
    for w in wire_strs:
        pts = _WIRE_XY.findall(w)
        for sx, sy in (pts[0], pts[-1]):
            key = (round(float(sx), 2), round(float(sy), 2))
            ends[key] = ends.get(key, 0) + 1
    pinset = {(round(px, 2), round(py, 2)) for px, py in pin_pts}
    have = set()
    out = []
    for j in explicit:
        m = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\)', j)
        if m:
            have.add((round(float(m.group(1)), 2), round(float(m.group(2)), 2)))
        out.append(j)
    for pt, n in sorted(ends.items()):
        if pt in have:
            continue
        if n >= 3 or (n == 2 and pt in pinset):
            out.append(cec_sch_layout.emit_junction(*pt))
            have.add(pt)
    return out


def _snap(v):
    return round(v / cec_sch.GRID) * cec_sch.GRID


def _route_io_columns(io_sides, attach, bbox, body_boxes, pin_pts,
                      hier_exports, existing_ends):
    """Standard S1: gather off-sheet hier labels into aligned edge columns.

    For each side, nets sort by attach-point Y; each gets a row in the column
    (>= 2.54mm pitch) and a nested lane in the gutter between the content edge
    and the column, so no two I/O wires ever cross each other (monotonic rows
    x nested lanes -- same argument as build_thin_parent's lane router). The
    wire is real drawn copper from the attach point (a stub/chain endpoint on
    the net), so netlist identity is preserved by construction. Every segment
    is checked against symbol body boxes and interior pin hits, and every NEW
    endpoint against foreign pins/wire-ends (an endpoint coincidence would
    MERGE nets); a violation raises -- the composition must adjust, the router
    never silently mis-wires.

    Returns (wire_tuples, hier_tuples): [(x1,y1,x2,y2)], [(net,x,y,ang)]."""
    G = cec_sch.GRID
    x0, x1, _y0, _y1 = bbox
    wires, hier = [], []
    new_ends = set(existing_ends)
    for side in ("left", "right"):
        nets = sorted((n for n, s in io_sides.items()
                       if s == side and n in attach),
                      key=lambda n: (attach[n][1], n))
        if not nets:
            continue
        sgn = -1 if side == "left" else 1
        edge = x0 if side == "left" else x1
        col = _snap(edge + sgn * (len(nets) + 2) * 2 * G)
        rows, prev = [], None
        for n in nets:
            ry = _snap(attach[n][1])
            if prev is not None and ry - prev < 2 * G:
                ry = prev + 2 * G
            rows.append(ry)
            prev = ry
        for i, n in enumerate(nets):
            bx, by = attach[n]
            ry = rows[i]
            lane = col - sgn * (i + 1) * 2 * G
            if abs(by - ry) < 1e-6:
                segs = [(min(col, bx), by, max(col, bx), by)]
                pts = [(col, ry)]
            else:
                segs = [(min(lane, bx), by, max(lane, bx), by),
                        (lane, min(by, ry), lane, max(by, ry)),
                        (min(col, lane), ry, max(col, lane), ry)]
                pts = [(lane, by), (lane, ry), (col, ry)]
            for (sx1, sy1, sx2, sy2) in segs:
                for bb in body_boxes:
                    if cec_sch._seg_hits_box(sx1, sy1, sx2, sy2, bb):
                        raise SystemExit(
                            f"io column: net {n} wire ({sx1},{sy1})-({sx2},{sy2})"
                            f" crosses a symbol body -- adjust the composition")
                for (px, py) in pin_pts:
                    on_h = abs(py - sy1) < 1e-6 and sx1 + 1e-6 < px < sx2 - 1e-6
                    on_v = abs(px - sx1) < 1e-6 and sy1 + 1e-6 < py < sy2 - 1e-6
                    if (on_h and abs(sy1 - sy2) < 1e-6) or (on_v and abs(sx1 - sx2) < 1e-6):
                        raise SystemExit(
                            f"io column: net {n} wire passes through pin at "
                            f"({px},{py}) -- adjust the composition")
            for pt in pts:
                key = (round(pt[0], 2), round(pt[1], 2))
                if key in pin_pts or key in new_ends:
                    raise SystemExit(
                        f"io column: net {n} endpoint {pt} coincides with a "
                        f"foreign pin/wire end -- adjust the composition")
            if abs(by - ry) < 1e-6:
                wires.append((bx, by, col, ry))
            else:
                wires.append((bx, by, lane, by))
                wires.append((lane, by, lane, ry))
                wires.append((lane, ry, col, ry))
            for pt in pts:
                new_ends.add((round(pt[0], 2), round(pt[1], 2)))
            hier.append((n, col, ry, 180 if side == "left" else 0))
    return wires, hier


def _center_shift(bbox, paper, margin=15.0, bias_y=-3.81):
    """Grid-snapped (dx,dy) translating content bbox to the paper center
    (slightly high, clear of the title block), clamped to the frame margin."""
    x0, x1, y0, y1 = bbox
    pw, ph = PAPER[paper]
    dx = (pw - (x1 - x0)) / 2 - x0
    dy = (ph - (y1 - y0)) / 2 - y0 + bias_y
    dx = max(dx, margin - x0)
    dy = max(dy, margin - y0)
    g = cec_sch.GRID
    return round(dx / g) * g, round(dy / g) * g


def _powerflag_anchors(powerflag_nets, placement, power_ports, project,
                       path_prefix, pwr_ref, wires, labels, flags, bbox=None):
    """The power-flag anchor block archetype: ONE tidy block of PWR_FLAG +
    power-port (or label) stamp pairs on short vertical wires at the
    content's BOTTOM-LEFT on a fixed pitch (standard S7 -- never orphan
    islands floating in dead space). A net that enters only on passive/
    power-input pins (e.g. +5VSB and GND off a connector) has no driving
    source, so ERC raises power_pin_not_driven; the PWR_FLAG marks it
    externally driven. One implementation; every leaf on every board is a
    caller via powerflag_nets."""
    if bbox is not None:
        base_x = _snap(bbox[0])
        base_y = _snap(bbox[3] + 7.62)
    else:
        base_y = round((max(p[1] for p in placement.values()) + 19.05) / cec_sch.GRID) * cec_sch.GRID
        base_x = round((min(p[0] for p in placement.values())) / cec_sch.GRID) * cec_sch.GRID
    # pitch: wide enough for the longest horizontal label among non-port
    # nets (a labeled rail gets a HORIZONTAL label at the wire top -- the old
    # vertical-90 label ran down over its own wire and whatever sat below)
    lbl_nets = [n for n in powerflag_nets if n not in power_ports]
    pitch = max(15.24, _snap(max((len(n) for n in lbl_nets), default=0) * 1.35 + 5.08))
    for i, net_name in enumerate(sorted(powerflag_nets)):
        sx = base_x + i * pitch
        ty, by_ = base_y, base_y + 10.16
        wires.append(cec_sch.emit_wire(sx, ty, sx, by_))
        port = power_ports.get(net_name, net_name)
        if port == "GND":
            flags.append(_emit_power2("PWR_FLAG", sx, ty, 180, project, path_prefix, pwr_ref("#FLG")))
            flags.append(_emit_power2(port, sx, by_, 0, project, path_prefix, pwr_ref("#PWR")))
        elif net_name in power_ports:
            flags.append(_emit_power2(port, sx, ty, 180, project, path_prefix, pwr_ref("#PWR")))
            flags.append(_emit_power2("PWR_FLAG", sx, by_, 0, project, path_prefix, pwr_ref("#FLG")))
        else:
            labels.append(cec_sch.emit_label(net_name, sx, ty, 0))
            flags.append(_emit_power2("PWR_FLAG", sx, by_, 0, project, path_prefix, pwr_ref("#FLG")))


def build_leaf(parts, nets, footprints, props, placement, nc_skip,
               power_ports, powerflag_nets, hier_exports, sections,
               libs, project, path_prefix, sheet_instances_path, own_uuid,
               page, out_path, paper="A2", title=None, comment1="",
               pwr_base=0, layout=None, global_nets=None, name_pin_nets=None):
    """Write one leaf schematic (a functional block with real components).

    `path_prefix` is the FULL chain of sheet-symbol uuids (starting with the
    project ROOT_UUID) leading down to this file, used for every component's
    `instances.path`. `sheet_instances_path` is that same chain WITHOUT the
    leading root uuid, used for this file's own `sheet_instances` footer.
    Both are plain strings already joined with "/" by the caller -- this
    function does not know or care how deep the hierarchy is.

    `layout` (T1 integration, 2026-07-03) is the leaf's COMPOSED drawn
    structure, expressed in the same local frame as `placement` (everything is
    translated together by the centering pass):
      wires:      [(x1,y1,x2,y2), ...] real wire segments (decoupler rails,
                  divider chains, pin buses -- drawn connectivity, not labels)
      labels:     [(net, x, y, ang), ...] extra local labels on those wires
      power:      [(sym, x, y, rot), ...] explicit power-symbol stamps
      hier_at:    {net: (x, y, ang)} hierarchical-label positions overriding
                  the anchor-pin stub default
      consumed:   {(ref,pin), ...} pins whose connectivity IS a drawn wire --
                  the generic stub+label/stamp pass skips them
      text_side:  {ref: 'left'|'right'} field-text side for vertical passives
      junction_strs: pre-emitted junction s-exprs (wire_decouplers output);
                  everything else is derived by _auto_junctions
    Placement values may be (x,y) or (x,y,rot); rotations use the empirically
    validated cec_sch_layout convention (round-trip-verified pin math).

    `global_nets` (optional): net names that connect PROJECT-WIDE via a real
    KiCad `global_label` at every stub occurrence -- NO sheet-pin/hier-label
    plumbing at all (bypasses `hier_exports`/`power_ports` for that net
    entirely). Use this for a genuine multi-leaf BUS (e.g. a CAN bus tapped
    by several sibling leaves plus a shared transceiver leaf) that
    `build_thin_parent`'s 1:1/2-endpoint sheet-pin fan-out cannot express.

    `name_pin_nets` (optional, round-4 A2 -- docs/standard-tier-review/
    round4-hier-conversion-2026-07-04.md): an iterable of net names that are
    otherwise INTERNAL to this leaf (not already in `hier_exports`) but must
    be force-exported anyway, so the zero-rename policy can give them a root
    stub + local label carrying their exact original bare name (see
    `build_thin_parent`'s "singles" case, which already does this for any
    net with exactly one leaf pin that is not a `root_exports` climber).
    For each such name a hierarchical_label is added at that net's FIRST
    connection point (`nets[net_name][0]`, deterministic -- insertion order),
    shape "output", exactly like a hand-authored `hier_exports` entry -- the
    caller must also declare a matching sheet pin on this leaf's box in the
    `build_thin_parent` call (that function's own `name_pin_nets` parameter
    automates this half). A name already present in `hier_exports` is left
    untouched (no duplicate export). Probe-verified naming: this mechanism
    took /04-mcu/FLASH_CS -> /FLASH_CS in the ent-common scratch probe.
    """
    placement = _norm_placement(placement)
    used = cec_sch.load_symbols(libs, parts)
    hier_exports = dict(hier_exports or {})
    for _net_name in (name_pin_nets or ()):
        if _net_name in hier_exports:
            continue
        _conns = nets.get(_net_name)
        if not _conns:
            raise SystemExit(f"{path_prefix}: name_pin_nets net {_net_name!r} "
                              f"not found in this leaf's nets")
        hier_exports[_net_name] = ("output", _conns[0])
    global_nets = set(global_nets or ())
    if global_nets:
        bad = global_nets & set(power_ports)
        assert not bad, f"global_nets overlaps power_ports: {bad}"
        bad = global_nets & set(hier_exports)
        assert not bad, f"global_nets overlaps hier_exports: {bad}"
    layout = layout or {}
    consumed = set(layout.get("consumed", ()))
    hier_at = dict(layout.get("hier_at", {}))
    text_side = dict(layout.get("text_side", {}))
    io_sides = dict(layout.get("io_sides", {}))
    io_from = {n: list(p) for n, p in layout.get("io_from", {}).items()}

    lay_wires = [list(w) for w in layout.get("wires", ())]
    lay_labels = [list(l) for l in layout.get("labels", ())]
    lay_power = [list(p) for p in layout.get("power", ())]
    lay_texts = [list(t) for t in layout.get("texts", ())]
    lay_regions = [list(r) for r in layout.get("regions", ())]

    # guard: a pin must not be in two nets
    seen = {}
    for net_name, conns in nets.items():
        for c in conns:
            if c in seen:
                raise SystemExit(f"pin {c} in two nets: {seen[c]} and {net_name}")
            seen[c] = net_name
    for c in consumed:
        if c not in seen:
            raise SystemExit(f"layout consumes pin {c} that is in no net")

    # ---- CENTERING (the owner's "put them in the middle of the sheets"):
    # preview the content bbox from part extents + composed geometry + the
    # powerflag anchor block, then translate placement AND layout together.
    xs, ys = [], []
    for ref in parts:
        x0, x1, y0, y1 = _part_extent(used, parts, placement, ref)
        xs += [x0, x1]; ys += [y0, y1]
    for w in lay_wires:
        xs += [w[0], w[2]]; ys += [w[1], w[3]]
    for l in lay_labels:
        xs += [l[1], l[1] + (12 if l[3] in (0,) else 0)]; ys.append(l[2])
    for p in lay_power:
        xs.append(p[1]); ys += [p[2] - 5, p[2] + 5]
    for net_name, (hx_, hy_, hang_) in hier_at.items():
        xs += [hx_, hx_ + (len(net_name) * 1.4 if hang_ == 0 else 0)]
        ys.append(hy_)
    for t in lay_texts:
        _kind, ttxt, tx, ty, tsz = t
        longest = max((len(ln) for ln in ttxt.split("\n")), default=1)
        xs += [tx, tx + longest * tsz * 1.02]
        ys += [ty, ty + (ttxt.count("\n") + 1) * tsz * 1.6]
    for r in lay_regions:
        xs += [r[1], r[3]]; ys += [r[2], r[4]]
    # content bbox BEFORE reserving io-column gutters (columns hang off it)
    cx0, cx1 = min(xs), max(xs)
    for side in ("left", "right"):
        k = sum(1 for s in io_sides.values() if s == side)
        if k:
            gut = (k + 3) * 2 * cec_sch.GRID
            lbl = max((len(n) for n, s in io_sides.items() if s == side)) * 1.4 + 4
            if side == "left":
                xs.append(cx0 - gut - lbl)
            else:
                xs.append(cx1 + gut + lbl)
    if powerflag_nets:
        pf_y = max(p[1] for p in placement.values()) + 19.05
        pf_x = min(p[0] for p in placement.values())
        xs += [pf_x, pf_x + (len(powerflag_nets) - 1) * 15.24 + 5]
        ys += [pf_y, pf_y + 17]
    dx, dy = _center_shift((min(xs), max(xs), min(ys), max(ys)), paper)

    placement = {r: (x + dx, y + dy, rot) for r, (x, y, rot) in placement.items()}
    for w in lay_wires:
        w[0] += dx; w[2] += dx; w[1] += dy; w[3] += dy
    for l in lay_labels:
        l[1] += dx; l[2] += dy
    for p in lay_power:
        p[1] += dx; p[2] += dy
    for t in lay_texts:
        t[2] += dx; t[3] += dy
    for r in lay_regions:
        r[1] += dx; r[3] += dx; r[2] += dy; r[4] += dy
    for p in io_from.values():
        p[0] += dx; p[1] += dy
    hier_at = {n: (x + dx, y + dy, a) for n, (x, y, a) in hier_at.items()}
    junction_strs = []  # wire_decouplers-style pre-emitted junctions are NOT
    # translatable strings; leaves compose those rails via layout["decoupler_
    # rails"] below instead, so nothing is lost by starting empty here.

    # decoupler rails composed via the T1 engine (cec_sch_layout
    # place_decouplers/wire_decouplers): the generator passes the PLAN inputs,
    # the caps are placed+wired HERE (post-shift frame) so the rail geometry
    # and the centering translation can't drift apart.
    for rail in layout.get("decoupler_rails", ()):
        plan = cec_sch_layout.place_decouplers(
            placement, used, parts, rail["ic"], rail["pin"], rail["caps"],
            side=rail.get("side", "above"), pitch=rail.get("pitch", 5.08),
            rise=rail.get("rise", 7.62))
        rail["_plan"] = plan

    body = [_emit_symbol2(r, *parts[r][:2], parts[r][2], *placement[r],
                          used[(parts[r][0], parts[r][1])]["pins"],
                          project, path_prefix, used[(parts[r][0], parts[r][1])],
                          footprints.get(r, ""), props.get(r),
                          text_side.get(r, "right"))
            for r in parts]

    extra = []
    need_syms = set(power_ports.values())
    if powerflag_nets:
        need_syms.add("PWR_FLAG")
    for sym, _x, _y, _rot in lay_power:
        need_syms.add(sym)
    for sym in sorted(need_syms):
        extra.append(cec_sch._power_block(libs, sym))

    wires, labels, flags, hlabels = [], [], [], []
    # pwr_base gives each sheet a disjoint #PWR/#FLG numbering block so refs
    # stay unique across the flattened hierarchy (duplicate refs across leaves
    # trip kicad-cli's "schematic has annotation errors" warning).
    pwr_seq = [pwr_base]

    def pwr_ref(prefix):
        pwr_seq[0] += 1
        return f"{prefix}{pwr_seq[0]:02d}"

    # composed structure first: real wires, their labels, their stamps
    for x1, y1, x2, y2 in lay_wires:
        wires.append(cec_sch.emit_wire(x1, y1, x2, y2))
    for net_name, lx, ly, lang in lay_labels:
        labels.append(cec_sch.emit_label(net_name, lx, ly, lang))
    for sym, px, py, prot in lay_power:
        flags.append(_emit_power2(sym, px, py, prot, project, path_prefix,
                                  pwr_ref("#PWR")))
    for net_name, (hx_, hy_, hang_) in hier_at.items():
        shape = hier_exports[net_name][0]
        hlabels.append(hier_label(net_name, shape, hx_, hy_, hang_))

    for rail in layout.get("decoupler_rails", ()):
        rw, rj, rp = cec_sch_layout.wire_decouplers(
            rail["_plan"], placement, used, parts, project, path_prefix,
            lambda prefix="#PWR": pwr_ref(prefix))
        wires += rw
        junction_strs += rj
        flags += rp

    glabels = []
    io_attach = {n: tuple(p) for n, p in io_from.items()}
    for net_name, conns in nets.items():
        is_global = net_name in global_nets
        port = None if is_global else power_ports.get(net_name)
        hx = None if is_global else hier_exports.get(net_name)
        hier_anchor = hx[1] if hx and net_name not in hier_at else None
        for ref, pin in conns:
            if (ref, pin) in consumed:
                continue
            ax, ay, dx_, dy_ = cec_sch_layout.pin_abs_rot(placement, used, parts, ref, pin)
            bx, by = ax + dx_ * cec_sch.STUB, ay + dy_ * cec_sch.STUB
            wires.append(cec_sch.emit_wire(ax, ay, bx, by))
            lang = 0 if dx_ > 0 else (180 if dx_ < 0 else (270 if dy_ < 0 else 90))
            if is_global:
                glabels.append(cec_sch.emit_global_label(net_name, bx, by, lang))
            elif hier_anchor is not None and (ref, pin) == hier_anchor:
                if net_name in io_sides and net_name not in io_attach:
                    # standard S1: the hier label moves to the edge column;
                    # the io router below wires it from this stub end.
                    io_attach[net_name] = (bx, by)
                else:
                    hlabels.append(hier_label(net_name, hx[0], bx, by, lang))
            elif port:
                flags.append(_emit_power2(port, bx, by, _port_rot(port, dx_, dy_),
                                          project, path_prefix, pwr_ref("#PWR")))
            else:
                labels.append(cec_sch.emit_label(net_name, bx, by, lang))

    # ---- content bbox + pin/body geometry (post-shift), for the io column
    # router, the powerflag block and the caption/note emission
    pin_pts = []
    body_boxes = []
    for ref, (lib, name, _v) in parts.items():
        x, y, rot = placement[ref]
        bb = cec_sch_layout.body_box_abs(used[(lib, name)]["block"], x, y, rot)
        if bb:
            body_boxes.append(bb)
        for pin in used[(lib, name)]["pins"]:
            ax, ay, _dx, _dy = cec_sch_layout.pin_abs_rot(placement, used, parts, ref, pin)
            pin_pts.append((ax, ay))
    cxs, cys = [], []
    for ref in parts:
        e = _part_extent(used, parts, placement, ref)
        cxs += [e[0], e[1]]; cys += [e[2], e[3]]
    for w in lay_wires:
        cxs += [w[0], w[2]]; cys += [w[1], w[3]]
    content_bbox = (min(cxs), max(cxs), min(cys), max(cys))  # ELECTRICAL bbox (io router)
    for _k, ttxt, tx, ty, tsz in lay_texts:      # captions/notes are content too
        longest = max((len(ln) for ln in ttxt.split("\n")), default=1)
        cxs += [tx, tx + longest * tsz * 1.02]
        cys += [ty, ty + (ttxt.count("\n") + 1) * tsz * 1.6]
    for r in lay_regions:
        cxs += [r[1], r[3]]; cys += [r[2], r[4]]
    full_bbox = (min(cxs), max(cxs), min(cys), max(cys))     # + annotation (pf block)

    if io_sides:
        missing = sorted(n for n in io_sides if n not in io_attach)
        if missing:
            raise SystemExit(f"io column: nets with no attach point (anchor "
                             f"consumed and no io_from): {missing}")
        pin_set = {(round(px, 2), round(py, 2)) for px, py in pin_pts}
        wire_ends = set()
        for w in wires:
            for sx, sy in _WIRE_XY.findall(w):
                wire_ends.add((round(float(sx), 2), round(float(sy), 2)))
        io_wires, io_hier = _route_io_columns(io_sides, io_attach, content_bbox,
                                              body_boxes, pin_set, hier_exports,
                                              wire_ends)
        for (x1, y1, x2, y2) in io_wires:
            wires.append(cec_sch.emit_wire(x1, y1, x2, y2))
        for (net_name, hxx, hyy, hang) in io_hier:
            hlabels.append(hier_label(net_name, hier_exports[net_name][0],
                                      hxx, hyy, hang))

    if powerflag_nets:
        _powerflag_anchors(powerflag_nets, placement, power_ports, project,
                           path_prefix, pwr_ref, wires, labels, flags,
                           bbox=full_bbox)

    ncs = []
    for ref, (lib, name, _v) in parts.items():
        for pin in used[(lib, name)]["pins"]:
            if (ref, pin) in seen or (ref, pin) in nc_skip:
                continue
            ax, ay, _dx, _dy = cec_sch_layout.pin_abs_rot(placement, used, parts, ref, pin)
            ncs.append(cec_sch.emit_noconnect(ax, ay))

    junctions = _auto_junctions(wires, pin_pts, junction_strs)

    # captions / notes / region accent frames (standard S3/S10/S11) -- pure
    # annotation, no electrical effect
    annot = []
    for kind, ttxt, tx, ty, tsz in lay_texts:
        annot.append(emit_caption(ttxt, tx, ty, size=tsz) if kind == "caption"
                     else emit_note(ttxt, tx, ty, size=tsz))
    for rtitle, rx0, ry0, rx1, ry1 in lay_regions:   # NB: never shadow `title`
        annot.append(emit_region(rtitle, rx0, ry0, rx1, ry1))

    # NOTE: per the owner's 2026-07-02 format correction, leaf sheets carry NO
    # dashed-frame section graphics -- the sheet itself (one file, one proper
    # title) IS the grouping. `sections` is accepted for signature symmetry
    # with the pre-restructure generators but is expected empty/None here.
    section_gfx = "\n".join(cec_sch.emit_section(lbl, *box) for lbl, box in (sections or {}).items())

    title_blk = title_block(title or out_path, comment1) if title else ""

    content = (
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
        f"\t(uuid \"{own_uuid}\")\n\t(paper \"{paper}\")\n"
        + (title_blk + "\n" if title_blk else "")
        + f"{cec_sch.lib_symbols_section(used, extra)}\n"
        + (section_gfx + "\n" if section_gfx else "")
        + ("\n".join(annot) + "\n" if annot else "")
        + "\n".join(body) + "\n"
        + "\n".join(wires) + "\n"
        + ("\n".join(junctions) + "\n" if junctions else "")
        + "\n".join(labels) + "\n"
        + ("\n".join(hlabels) + "\n" if hlabels else "")
        + ("\n".join(glabels) + "\n" if glabels else "")
        + ("\n".join(flags) + "\n" if flags else "")
        + ("\n".join(ncs) + "\n" if ncs else "")
        + f'\t(sheet_instances\n\t\t(path "/{sheet_instances_path}"\n\t\t\t(page "{page}")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
    open(out_path, "w").write(content)
    return {"parts": len(parts), "nets": len(nets), "labels": len(labels),
            "hlabels": len(hlabels), "glabels": len(glabels), "wires": len(wires),
            "flags": len(flags), "junctions": len(junctions), "nc": len(ncs)}


def _sheet_pin_block(name, shape, x, y, angle):
    # Field order matters here: verified empirically against a real,
    # KiCad-authored hierarchical reference project that (at) (uuid) (effects)
    # is what a working sheet pin looks like. (at) (effects) (uuid) -- this
    # function's order until this fix -- parses without a syntax error but
    # the pin silently fails to participate in net connectivity (kicad-cli
    # ERC reports label_dangling/unconnected_wire_endpoint on everything
    # wired to it, and the netlist shows it as its own isolated single-node
    # net). Root's own sheet-01 pins (build_root, unchanged elsewhere in this
    # file) never wire anything to their pins, so that latent bug never
    # surfaced there.
    #
    # Justify: the pin NAME must render INSIDE the box. Measured on renders
    # (2026-07-03): angle 0 (right edge) + justify left draws the name
    # OUTSIDE, colliding with whatever sits at the stub end; justify right
    # pulls it inside. Angle 180 (left edge) is the mirror case.
    just = "right" if angle == 0 else "left"
    return (f'\t\t(pin "{name}" {shape}\n'
            f'\t\t\t(at {cec_sch.f(x)} {cec_sch.f(y)} {angle})\n'
            f'\t\t\t(uuid "{cec_sch.u()}")\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (justify {just}))\n\t\t)')


def _sheet_block(uuid_, x, y, w, h, sheetname, sheetfile, project, root_uuid, page, pins=()):
    pin_txt = ("\n" + "\n".join(pins) + "\n") if pins else "\n"
    return (
        f'\t(sheet\n'
        f'\t\t(at {cec_sch.f(x)} {cec_sch.f(y)})\n'
        f'\t\t(size {cec_sch.f(w)} {cec_sch.f(h)})\n'
        f'\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n'
        f'\t\t(fields_autoplaced yes)\n'
        f'\t\t(stroke (width 0.1524) (type solid))\n'
        f'\t\t(fill (color 0 0 0 0.0000))\n'
        f'\t\t(uuid "{uuid_}")\n'
        f'\t\t(property "Sheetname" "{sheetname}"\n'
        f'\t\t\t(at {cec_sch.f(x)} {cec_sch.f(y - 1.5)} 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (justify left bottom))\n\t\t)\n'
        f'\t\t(property "Sheetfile" "{sheetfile}"\n'
        f'\t\t\t(at {cec_sch.f(x)} {cec_sch.f(y + h + 1.5)} 0)\n'
        f'\t\t\t(effects (font (size 1.27 1.27)) (justify left top))\n\t\t)'
        f'{pin_txt}'
        f'\t\t(instances\n\t\t\t(project "{project}"\n'
        f'\t\t\t\t(path "/{root_uuid}"\n\t\t\t\t\t(page "{page}")\n\t\t\t\t)\n'
        f'\t\t\t)\n\t\t)\n\t)'
    )


def _root_captured_sheet_block(hier_exports, sym_uuid, sheetname, sheetfile,
                                geom, page, project, root_uuid, pin_pitch=5.588):
    """One CAPTURED (real, pinned) sheet box for the root -- shared by the
    main sheet and any `extra_sheets` (2026-07-03, sheet-05 generalization:
    the root used to see exactly ONE captured subtree; it may now carry
    several, each with its own export list/geometry/page)."""
    x, y, w, h = geom
    names = list(hier_exports.keys())
    pin_blocks = []
    for i, name in enumerate(names):
        shape = hier_exports[name][0]
        # X must land EXACTLY on the box's right edge (x + w) -- do not
        # gridsnap it (verified empirically: a sheet pin whose X is off the
        # box edge by even a fraction of a mm, e.g. via naive gridsnapping,
        # silently fails to bind to the box's boundary in kicad-cli's
        # connectivity resolution -- it still LOOKS fine and ERC still runs,
        # but the pin never joins its net; see build_thin_parent below, where
        # this bug was actually exercised and root-caused, since these root
        # pins currently have nothing wired to them so it stays dormant here).
        px, py = x + w, cec_sch.gridsnap(0, y + 8 + i * pin_pitch)[1]
        pin_blocks.append(_sheet_pin_block(name, shape, px, py, 0))
    return _sheet_block(sym_uuid, x, y, w, h, sheetname, sheetfile,
                         project, root_uuid, page, pin_blocks)


def build_root(hier_exports, project, root_uuid, sheet01_sym_uuid,
               placeholder_uuids, placeholder_titles, out_path,
               title_block_str, legend_str, main_sheetname, main_sheetfile,
               paper="A3", main_geom=(20, 20, 70, 92), pin_pitch=5.588,
               placeholder_grid=((140, 220), (20, 65, 110, 155)),
               placeholder_size=(70, 35), first_placeholder_page=3,
               extra_sheets=None):
    """Write the project root: a sheet instance for the main captured subtree
    (with hierarchical-label pins matching its exports) + placeholder sheet
    symbols (no pins -- nothing captured there yet). Board-specific text
    (title block, legend) is supplied by the caller.

    `extra_sheets` (2026-07-03, sheet-05 generalization): an optional list of
    further CAPTURED (pinned, non-placeholder) sheets, each a dict
    {hier_exports, sym_uuid, sheetname, sheetfile, geom=(x,y,w,h), page}.
    The root previously assumed exactly one captured subtree ("01") plus a
    grid of placeholders; a second capture (e.g. "05") needs its own box and
    export-pin list without disturbing sheet 01's pins/geometry, so this
    generalizes the single-main-sheet path into a list while leaving the
    default (no extra_sheets) byte-identical to the prior behavior."""
    s01_x, s01_y, s01_w, s01_h = main_geom
    sheets = [_root_captured_sheet_block(hier_exports, sheet01_sym_uuid,
                                          main_sheetname, main_sheetfile,
                                          main_geom, "2", project, root_uuid,
                                          pin_pitch)]
    for extra in (extra_sheets or ()):
        sheets.append(_root_captured_sheet_block(
            extra["hier_exports"], extra["sym_uuid"], extra["sheetname"],
            extra["sheetfile"], extra["geom"], extra["page"], project,
            root_uuid, extra.get("pin_pitch", pin_pitch)))

    # placeholder sheets: grid, no pins
    grid_x, grid_y = placeholder_grid
    page = first_placeholder_page
    for idx, num in enumerate(sorted(placeholder_uuids)):
        sx = grid_x[idx % len(grid_x)]
        sy = grid_y[idx // len(grid_x)]
        name, _desc = placeholder_titles[num]
        sheets.append(_sheet_block(placeholder_uuids[num], sx, sy,
                                    placeholder_size[0], placeholder_size[1],
                                    name, f"{name}.kicad_sch",
                                    project, root_uuid, str(page)))
        page += 1

    content = (
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
        f"\t(uuid \"{root_uuid}\")\n\t(paper \"{paper}\")\n"
        f"{title_block_str}\n"
        "\t(lib_symbols\n\t)\n"
        + "\n".join(sheets) + "\n"
        + legend_str + "\n"
        + '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
    open(out_path, "w").write(content)


def build_placeholder(num, sheet_sym_uuid, name, desc, project, page, out_path,
                       paper="A4", comment1="CAPTURE PENDING", body_tail=""):
    """Write a minimal, valid, empty placeholder sheet: a title block +
    a 'capture pending' note, no components, no hierarchical labels yet.
    `sheet_sym_uuid` is the SAME uuid used for this sheet's `(sheet ...)` block
    in the root (there are no internal symbols here to need a distinct file
    identity, so the header uuid and the sheet_instances path share it)."""
    content = (
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
        f"\t(uuid \"{sheet_sym_uuid}\")\n\t(paper \"{paper}\")\n"
        '\t(title_block\n'
        f'\t\t(title "{num}-{name.split("-",1)[1] if "-" in name else name}")\n'
        '\t\t(date "2026-07-02")\n'
        '\t\t(rev "DRAFT")\n'
        '\t\t(company "CEC")\n'
        f'\t\t(comment 1 "{comment1}")\n'
        '\t)\n'
        "\t(lib_symbols\n\t)\n"
        f'\t(text "{name} -- CAPTURE PENDING\\n\\n{desc}\\n\\n{body_tail}"\n'
        '\t\t(at 20 20 0)\n'
        '\t\t(effects (font (size 2 2)))\n'
        f'\t\t(uuid "{cec_sch.u()}")\n\t)\n'
        f'\t(sheet_instances\n\t\t(path "/{sheet_sym_uuid}"\n\t\t\t(page "{page}")\n\t\t)\n\t)\n'
        '\t(embedded_fonts no)\n)\n')
    open(out_path, "w").write(content)


# ---------------------------------------------------------------------------
# thin-parent assembly: a sheet file whose ONLY content is `(sheet ...)`
# instances for its own leaf files, wired together (by name-matched labels,
# exactly like a normal net -- KiCad merges same-named local labels within
# one sheet regardless of physical routing) plus, for any net that must climb
# further up to the grandparent, one `hierarchical_label` per such net. No
# components, no dashed frames -- the owner's 2026-07-02 format correction:
# "each functional block literally on its own sheet", so this file's only job
# is fan-out/fan-in of sheet pins. A thin parent may also BE the project root
# (own_sheet_sym_uuid=None): then there is no grandparent, root_exports is
# empty, and the file's sheet_instances footer is the root's own "/" page 1.
# ---------------------------------------------------------------------------
def build_thin_parent(leaves, root_exports, project, root_uuid, own_sheet_sym_uuid,
                       own_uuid, out_path, title, paper="A3",
                       global_power_exports=None, libs=None, pwr_base=0,
                       gp_block_xy=None, page="2", title_comments=None,
                       lane_labels=False, name_pin_nets=None):
    """
    leaves: ordered list of dicts, each:
        {id, sym_uuid, filename, sheetname, page, x, y, w, h,
         pins: [(net_name, shape, side), ...]}   # side in {'right','left'}
    root_exports: set of net names that ALSO need a hierarchical_label in
        THIS file reaching further up (matching a pin on `own_sheet_sym_uuid`
        as it appears in the grandparent/root file). Shape is always
        "output", matching every pin already declared there (the established
        HIER_EXPORTS convention). Pass an empty set when this parent IS the
        project root.
    own_sheet_sym_uuid: the uuid of THIS file's `(sheet ...)` block one level
        up, or None when this thin parent IS the project root file (then the
        sheet_instances footer is `/` page 1 and component-style instance
        paths are just the root uuid).
    global_power_exports: {net_name: power_symbol_name} for root-exports that
        are REAL KiCad global power nets (`(power global)` symbols, which
        connect project-wide by name alone, with NO hierarchical-label
        plumbing needed at all). Every leaf that uses one of these nets
        places its OWN ordinary global power symbol (unchanged, same as any
        other net in POWER_PORTS) -- so unlike the other root_exports, THESE
        have no leaf sheet-pin to anchor to here. The root-facing
        hierarchical_label instead gets its OWN local global power symbol
        stamped right next to it: that symbol is the SAME already-
        project-wide net (electrically identical to every leaf's copy), and
        its presence is what keeps the hierarchical_label from reading as
        label_dangling. Needs `libs` (for the "power" library).

    T1-integration layout (2026-07-03, the owner's "not ugly spread out"
    correction): a net shared by exactly TWO leaf boxes is a REAL DRAWN
    WIRE between the two sheet pins (source on a right edge, destination on a
    left edge -- left-to-right flow), routed on a per-destination lane
    column with a deterministic no-crossing order; a net with ONE leaf pin
    gets its hierarchical label DIRECTLY at the pin stub (no label-alias
    pair). Everything is grid-aligned (box origins/sizes included, so the
    sheet-pin-must-sit-exactly-on-the-box-edge rule and the 1.27mm grid are
    satisfied SIMULTANEOUSLY -- the old off-grid-edge ERC/lint noise is gone
    by construction), then the whole composition is centered on the page.

    `lane_labels` (round-4 A1, opt-in, default False -- unused leaves prior
    output byte-identical): when True, every 2-endpoint lane (a net wired
    source-box -> dest-box, i.e. the `pairs` case below) that is NOT also a
    `root_exports` climber additionally carries a LOCAL label with the net's
    ORIGINAL bare name, tapped off the lane exactly like a `root_exports`
    hierarchical-label tap (same geometry: a short perpendicular stub clear
    of the lane corridor) -- probe-verified (round-4 plan doc, "Measured
    facts" #1): a root local label wins the net name outright ("/NAME"),
    so a lane that would otherwise regenerate as a hierarchy-scoped name
    keeps its exact flat-schematic name instead.

    `name_pin_nets` (round-4 A2, opt-in): {leaf_id: [net_name_or_(net_name,
    side), ...]} -- for each entry, if that leaf's `pins` list does not
    already declare the net, a pin (net_name, "output", side) is appended
    automatically (side defaults to "right"). Pairs with `build_leaf`'s own
    `name_pin_nets` parameter, which forces the matching hierarchical_label
    inside the leaf; once the pin exists here, the ordinary `singles` case
    below already produces the root stub + LOCAL label with the original
    bare name (probe-verified: no further special-casing needed).
    """
    global_power_exports = global_power_exports or {}
    is_root = own_sheet_sym_uuid is None
    G = cec_sch.GRID
    STUB = cec_sch.STUB

    if name_pin_nets:
        for leaf in leaves:
            for entry in name_pin_nets.get(leaf["id"], ()):
                net_name, side = entry if isinstance(entry, tuple) else (entry, "right")
                if any(n == net_name for n, _s, _sd in leaf["pins"]):
                    continue
                leaf["pins"] = list(leaf["pins"]) + [(net_name, "output", side)]

    # ---- pin coordinates (local frame; per-side stacking, 5.08 pitch)
    net_pins = {}   # net -> [(px, py, side, leaf_index)]
    for li, leaf in enumerate(leaves):
        cnt = {"right": 0, "left": 0}
        leaf["_pins"] = []
        for net_name, shape, side in leaf["pins"]:
            i = cnt[side]; cnt[side] += 1
            px = leaf["x"] + (leaf["w"] if side == "right" else 0)
            py = leaf["y"] + 7.62 + i * 5.08
            leaf["_pins"].append((net_name, shape, side, px, py))
            net_pins.setdefault(net_name, []).append((px, py, side, li))

    wires = []      # (x1,y1,x2,y2)
    labels = []     # (net, x, y, ang)
    hier = []       # (net, x, y, ang)

    # ---- single-pin nets: hier label directly at the stub end
    singles = {n: p[0] for n, p in net_pins.items() if len(p) == 1}
    for net_name, (px, py, side, _li) in sorted(singles.items()):
        ex = px + STUB if side == "right" else px - STUB
        wires.append((px, py, ex, py))
        if net_name in root_exports:
            hier.append((net_name, ex, py, 0 if side == "right" else 180))
        else:
            labels.append((net_name, ex, py, 0 if side == "right" else 180))

    # ---- two-pin nets: real drawn wires, per-destination lane columns.
    # Lane order rule (derived + checked for zero crossings on this fan-in
    # shape): within one destination box, the LOWER source gets the lane
    # NEARER the destination edge.
    pairs = {n: p for n, p in net_pins.items() if len(p) == 2}
    for n, p in sorted(net_pins.items()):
        if len(p) > 2:
            raise SystemExit(f"build_thin_parent: net {n} on {len(p)} sheet pins -- "
                              "only 1:1 leaf wiring is composed; split it or add labels")
    by_dst = {}
    for net_name, p in sorted(pairs.items()):
        (sx, sy, sside, _sli), (txx, tyy, tside, tli) = sorted(p, key=lambda q: q[0])
        if sside != "right" or tside != "left":
            raise SystemExit(f"build_thin_parent: net {net_name} pin sides must be "
                              f"right(source)->left(dest), got {sside}->{tside}")
        by_dst.setdefault(tli, []).append((net_name, sx, sy, txx, tyy))
    hier_tapped = set()
    for tli, group in sorted(by_dst.items()):
        group.sort(key=lambda g: -g[2])            # lower source first
        for k, (net_name, sx, sy, txx, tyy) in enumerate(group):
            lane = txx - 5.08 - k * 2.54
            is_root_export = net_name in root_exports
            # A1: a lane not climbing further still gets tapped for its LOCAL
            # label when lane_labels is on -- same tap geometry, so the
            # existing corridor-clearance shape is reused rather than
            # re-derived. lane_labels default False keeps `tap` identical to
            # the prior `net_name in root_exports` for every existing caller.
            want_label = lane_labels and not is_root_export
            tap = is_root_export or want_label
            # BUG (round-4, measured): the default offset 7.62 is EXACTLY 3x
            # the per-net lane pitch (2.54), so tapx(k) == lane(k+3) exactly
            # -- a k-th net's tap stub sits precisely on the (k+3)-th net's
            # own lane line. Harmless while every prior caller (ent-common,
            # hub-enterprise) only ever taps <=3 members of one destination
            # group at once; lane_labels (round-4 A1) can tap MANY members of
            # one group simultaneously (measured: eps-8pin's 5-member
            # 05-sensing destination group shorted THRESH_PWM/I2C_SDA/
            # I2C_SCL/DETC1/DETC2 together via this exact collision). Once a
            # group reaches 4+ members the 3x coincidence becomes reachable,
            # so switch to a HALF-STEP offset (2.5x the pitch) that can never
            # equal an integer multiple -- tapx(k) == lane(k') would need
            # (k'-k) == 2.5, never an integer. Groups of <4 keep the exact
            # prior geometry (byte-identical output; the collision cannot
            # occur there since k+3 is out of range).
            tapx = lane - (6.35 if len(group) >= 4 else 7.62)
            if sy == tyy and not tap:
                wires.append((sx, sy, txx, tyy))
            else:
                # split the source horizontal AT the tap point -- a wire
                # endpoint binds only end-to-end; a drop onto a segment
                # interior silently dangles (measured: ERC label_dangling +
                # unconnected_wire_endpoint on the first try of this code)
                if tap:
                    wires.append((sx, sy, tapx, sy))
                    wires.append((tapx, sy, lane, sy))
                    wires.append((tapx, sy, tapx, sy + 5.08))
                    if is_root_export:
                        hier.append((net_name, tapx, sy + 5.08, 0))
                        hier_tapped.add(net_name)
                    else:
                        labels.append((net_name, tapx, sy + 5.08, 0))
                else:
                    wires.append((sx, sy, lane, sy))
                wires.append((lane, sy, lane, tyy))
                wires.append((lane, tyy, txx, tyy))

    # ---- global power exports: stamp + hier label rows, a tidy block
    if global_power_exports:
        if gp_block_xy is None:
            gp_block_xy = (max(l["x"] + l["w"] for l in leaves) - 30,
                           max(l["y"] + l["h"] for l in leaves) + 15)
        gpx = round(gp_block_xy[0] / G) * G
        gpy = round(gp_block_xy[1] / G) * G
    gp_rows = []    # (net, wire, stamp xy, hier xy)
    for i, net_name in enumerate(sorted(global_power_exports)):
        hy = gpy + i * 7.62
        wires.append((gpx - STUB, hy, gpx, hy))
        gp_rows.append((net_name, gpx - STUB, hy))
        hier.append((net_name, gpx, hy, 0))

    covered = set(singles) | hier_tapped | set(global_power_exports)
    missing = sorted(root_exports - covered)
    if missing:
        raise SystemExit(f"build_thin_parent: root_exports not reachable by any leaf "
                          f"pin stub, wired tap, or global_power_exports: {missing}")

    # ---- wires must not cross any sheet box (teeth for the lane arithmetic)
    for (x1, y1, x2, y2) in wires:
        for leaf in leaves:
            box = (leaf["x"] + 0.5, leaf["x"] + leaf["w"] - 0.5,
                   leaf["y"] + 0.5, leaf["y"] + leaf["h"] - 0.5)
            if cec_sch._seg_hits_box(x1, y1, x2, y2, box):
                raise SystemExit(f"build_thin_parent: wire ({x1},{y1})-({x2},{y2}) "
                                  f"crosses sheet box {leaf['sheetname']}")

    # ---- centering on the page
    xs, ys = [], []
    for leaf in leaves:
        xs += [leaf["x"], leaf["x"] + leaf["w"]]
        ys += [leaf["y"], leaf["y"] + leaf["h"] + 4]
    for (x1, y1, x2, y2) in wires:
        xs += [x1, x2]; ys += [y1, y2]
    for (net_name, hx_, hy_, hang_) in hier:
        xs += [hx_, hx_ + (len(net_name) * 1.4 + 4) * (1 if hang_ == 0 else -1)]
        ys.append(hy_)
    for (net_name, lx_, ly_, lang_) in labels:
        xs += [lx_, lx_ + (len(net_name) * 1.4 + 4) * (1 if lang_ == 0 else -1)]
        ys.append(ly_)
    dx, dy = _center_shift((min(xs), max(xs), min(ys), max(ys)), paper)

    def sx_(v): return v + dx
    def sy_(v): return v + dy

    # ---- emission (shifted frame)
    sheets = []
    for leaf in leaves:
        pins_blocks = []
        for net_name, shape, side, px, py in leaf["_pins"]:
            # X sits EXACTLY on the box edge (grid-aligned by construction
            # now, but never re-snapped independently of the box: a sheet pin
            # off its box edge silently drops from the netlist -- verified
            # empirically during the 2026-07-02 re-sheeting).
            ang = 0 if side == "right" else 180
            pins_blocks.append(_sheet_pin_block(net_name, shape, sx_(px), sy_(py), ang))
        sheets.append(_sheet_block(leaf["sym_uuid"], sx_(leaf["x"]), sy_(leaf["y"]),
                                    leaf["w"], leaf["h"],
                                    leaf["sheetname"], leaf["filename"],
                                    project, root_uuid, leaf["page"], pins_blocks))

    flags = []
    pwr_seq = [pwr_base]

    def pwr_ref(prefix):
        pwr_seq[0] += 1
        return f"{prefix}{pwr_seq[0]:02d}"

    wire_strs = [cec_sch.emit_wire(sx_(x1), sy_(y1), sx_(x2), sy_(y2))
                 for (x1, y1, x2, y2) in wires]
    label_strs = [cec_sch.emit_label(n, sx_(x), sy_(y), a) for (n, x, y, a) in labels]
    hlabels = [hier_label(n, "output", sx_(x), sy_(y), a) for (n, x, y, a) in hier]
    gp_inst_path = root_uuid if is_root else f"{root_uuid}/{own_sheet_sym_uuid}"
    for net_name, px, py in gp_rows:
        # component-style instances path (full chain from the true root),
        # matching how every regular part inside a leaf sheet is addressed
        # -- NOT the single-hop convention that sheet_instances/sheet-pins
        # need (see the notes above/in this function's docstring).
        flags.append(_emit_power2(global_power_exports[net_name], sx_(px), sy_(py),
                                  180, project, gp_inst_path,
                                  pwr_ref("#PWR")))
    junctions = _auto_junctions(wire_strs, [])
    wires, labels = wire_strs, label_strs

    extra_syms = []
    if global_power_exports:
        for sym in sorted(set(global_power_exports.values())):
            extra_syms.append(cec_sch._power_block(libs, sym))
    lib_symbols_section = ("\t(lib_symbols\n" + "\n".join(cec_sch.reindent(s, 2) for s in extra_syms) + "\n\t)\n") \
        if extra_syms else "\t(lib_symbols\n\t)\n"

    if title_comments is None:
        title_comments = (
            "Thin parent sheet -- sheet-symbol fan-out/fan-in ONLY, no "
            "components, per the owner's 2026-07-02 format correction",
            "Leaf sheets: " + ", ".join(l["sheetname"] for l in leaves))
    title_blk = title_block(title, *title_comments)

    footer_path = "/" if is_root else f"/{own_sheet_sym_uuid}"
    footer_page = "1" if is_root else page
    content = (
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
        f"\t(uuid \"{own_uuid}\")\n\t(paper \"{paper}\")\n"
        f"{title_blk}\n"
        f"{lib_symbols_section}"
        + "\n".join(sheets) + "\n"
        + "\n".join(wires) + "\n"
        + ("\n".join(junctions) + "\n" if junctions else "")
        + ("\n".join(labels) + "\n" if labels else "")
        + ("\n".join(hlabels) + "\n" if hlabels else "")
        + ("\n".join(flags) + "\n" if flags else "")
        + f'\t(sheet_instances\n\t\t(path "{footer_path}"\n\t\t\t(page "{footer_page}")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
    open(out_path, "w").write(content)
    return {"leaves": len(leaves), "nets": len(net_pins), "wired_nets": len(pairs),
            "root_exports": len(root_exports),
            "global_power": len(global_power_exports)}
