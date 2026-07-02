#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_sch_layout -- SCHEMATIC LAYOUT-QUALITY ENGINE (standalone, additive)
# ============================================================================
# The owner's ask: generated schematics should read as REAL DRAWN STRUCTURE --
# rotated parts in their natural orientation, real wires to adjacent parts,
# collision-free text -- instead of leaning on net-label aliasing for every
# connection. This module is ADDITIVE: it EXTENDS/REUSES scripts/cec_sch.py's
# primitives (load_symbols, pin_table, route_L, emit_wire/emit_label/
# emit_global_power, lib_symbols_section, gridsnap, GRID, STUB, u, f, carve)
# WITHOUT modifying cec_sch.py, gen-modules.py, or hubs/hub-enterprise/
# gen_hub_enterprise.py. Integration into those generators is a later pass.
#
# Five abilities, each independently usable:
#   1. ROTATION-AWARE PLACEMENT   -- pin_abs_rot() / body_box_abs() / natural
#      orientations for 2-pin passives.
#   2. LOCAL WIRE ROUTING         -- wire_adjacent(): real Manhattan wire
#      segments between two CLOSE pins (falls back to a label past a distance
#      threshold -- long hauls staying labels is correct schematic style).
#   3. DECOUPLER ADJACENCY        -- derive_owners() ports cec_pcb/
#      cec_synth_pipeline's netlist-driven PCB ownership concept to schematic
#      space; place_decouplers() + wire_decouplers() place + WIRE (not label)
#      a row of decouplers next to their owning IC's power pin.
#   4. TEXT-COLLISION ENGINE      -- text_bbox() (calibrated against a REAL
#      kicad-cli sch export svg measurement, see the CALIBRATION section)
#      -> detect_overlaps(path) (a CHECKER that works on ANY .kicad_sch) and
#      nudge_texts(path) (deterministic collision resolution restricted to
#      symbol Reference/Value field text -- pins/wires/labels are never
#      moved, since a label MUST stay exactly at its wire's endpoint to stay
#      electrically connected).
#   5. CLI                        -- `--check-overlaps` (a cosmetic gate any
#      sheet-verification protocol can adopt) and `--nudge` / `--demo`.
#
# ---------------------------------------------------------------------------
# ROTATION CONVENTION (the load-bearing fact this module is built on)
# ---------------------------------------------------------------------------
# Library symbol pins are authored in a Y-UP local frame; cec_sch.pin_abs's
# rot=0 case converts to the schematic's Y-DOWN frame with a plain Y flip
# (ax = ox+lx, ay = oy-ly). This module generalizes to a rotated instance
# `(at ox oy ROT)`. The convention was NOT assumed -- it was determined
# empirically (2026-07-02) by round-tripping a rotated part through the real
# KiCad engine: R_Small's two pins sit on the local Y axis only (0,+2.54) and
# (0,-2.54), so a sign error in the rotation formula SWAPS pin 1 and pin 2 --
# a discriminating test. Two hypotheses were built (standard math CCW rotation
# applied to the Y-up local coordinates BEFORE the Y-flip, vs. the mirror
# image, i.e. negated angle) as tiny schematics with a wire from OUR computed
# pin position to a uniquely-named label, then `kicad-cli sch export netlist`
# was used as ground truth: if our computed position for "pin 1" does not
# coincide with where KiCad's OWN independent pin-position computation places
# the real pin 1, the label lands on the wrong pin (or nothing) in the
# exported netlist. Result at rot in {0, 90, 180, 270} (see
# tests/test_sch_layout.py::test_rotation_roundtrip, which re-runs this same
# probe as a pass/fail test): the CCW hypothesis reproduces the correct
# pin-1/pin-2 correspondence at EVERY rotation; the mirror (CW) hypothesis
# swaps pins 1 and 2 at 90 and 270. So:
#
#     rlx = lx*cos(rot) - ly*sin(rot)
#     rly = lx*sin(rot) + ly*cos(rot)      (standard math CCW, on Y-up local coords)
#     ax  = ox + rlx
#     ay  = oy - rly                        (Y-flip to schematic frame, same as rot=0)
#
# This generalizes cec_sch.pin_abs exactly (its rot=0 case is rlx=lx, rly=ly).
# ---------------------------------------------------------------------------
import os, re, sys, math, argparse
from collections import defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT + "/scripts" not in sys.path:
    sys.path.insert(0, _ROOT + "/scripts")
import cec_sch  # the existing, UNMODIFIED schematic-emit primitives this module builds on


# ============================================================================
# 1) ROTATION-AWARE PLACEMENT
# ============================================================================

def rotate_local(lx, ly, rot):
    """Rotate a LOCAL (library, Y-UP) point by `rot` degrees. See the module
    docstring for the empirical validation of this convention."""
    a = math.radians(rot % 360)
    ca, sa = math.cos(a), math.sin(a)
    return (lx * ca - ly * sa, lx * sa + ly * ca)


def pin_abs_rot(placement, used, parts, ref, num):
    """Like cec_sch.pin_abs, generalized to a rotated instance: placement[ref]
    = (x, y, rot). Returns (ax, ay, dx, dy) -- the pin's absolute connection
    point and its outward (away-from-body) unit vector."""
    lib, name, _ = parts[ref]
    lx, ly, ang, _length = used[(lib, name)]["pins"][num]
    ox, oy, rot = placement[ref]
    rlx, rly = rotate_local(lx, ly, rot)
    ax, ay = ox + rlx, oy - rly
    total_ang = (ang + rot) % 360
    dx = -math.cos(math.radians(total_ang))
    dy = math.sin(math.radians(total_ang))
    return ax, ay, dx, dy


def body_box_abs(block, ox, oy, rot):
    """Absolute keep-out box (xmin,xmax,ymin,ymax) for a placed, possibly
    rotated symbol body, built from cec_sch.sym_body_box's LOCAL rectangle
    union. None if the symbol draws no rectangle (some ICs use polylines)."""
    bb = cec_sch.sym_body_box(block)
    if not bb:
        return None
    minx, maxx, miny, maxy = bb
    xs, ys = [], []
    for (lx, ly) in ((minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy)):
        rlx, rly = rotate_local(lx, ly, rot)
        xs.append(ox + rlx); ys.append(oy - rly)
    return (min(xs), max(xs), min(ys), max(ys))


def _rotate_about(px, py, cx, cy, rot):
    """Rotate absolute point (px,py) about center (cx,cy) by `rot` degrees,
    using the SAME validated convention as rotate_local (converted through
    the Y-up local frame and back)."""
    dx, dy = px - cx, py - cy
    lx, ly = dx, -dy
    rlx, rly = rotate_local(lx, ly, rot)
    return cx + rlx, cy - rly


# Natural orientations for 2-pin passives. Verified via cec_sch.pin_table
# against lib/vendor/cec-vendor.kicad_sym: R_Small and C_Small both place pin
# 1 at local (0,+2.54) and pin 2 at local (0,-2.54) -- i.e. at rot=0 they
# already read VERTICAL, pin 1 "up"/pin 2 "down". That is the natural
# decoupler orientation (rail on top, GND on bottom); rotating 90 degrees
# reads HORIZONTAL -- the natural in-line series-element orientation (e.g. a
# filter series R sitting directly between two other pins on the same line).
ROT_VERTICAL = 0
ROT_HORIZONTAL = 90


def natural_rotation(role):
    """role: 'decoupler' | 'divider' (both vertical, rail-to-GND) | 'series'
    (horizontal, in-line). Unknown roles default to vertical."""
    return {"decoupler": ROT_VERTICAL, "divider": ROT_VERTICAL,
            "series": ROT_HORIZONTAL}.get(role, ROT_VERTICAL)


def emit_symbol_rot(ref, lib, name, val, x, y, rot, pins, project, root,
                     fp="", props=None, body_half=None):
    """Like cec_sch.emit_symbol, but the instance carries a real rotation
    (cec_sch.emit_symbol hardcodes rot=0). Reference/Value field text is
    offset in absolute Y by the part's (rotated) body half-height + a fixed
    clearance, so at ANY rotation the field text starts outside the body --
    detect_overlaps()/nudge_texts() catch whatever is still left colliding."""
    val = cec_sch.fmt_value(name, val)
    props = props or {}
    pinblk = "\n".join(f'\t\t(pin "{n}" (uuid "{cec_sch.u()}"))' for n in pins)
    ds = props.get("Datasheet", "")
    extra = "".join(
        f'\t\t(property "{k}" "{v}" (at {cec_sch.f(x)} {cec_sch.f(y)} 0) '
        f'(effects (font (size 1.27 1.27)) (hide yes)))\n'
        for k, v in props.items()
        if k not in ("Datasheet", "Reference", "Value", "Footprint") and v)
    half = body_half if body_half is not None else 12.7
    off = max(half + 2.54, 3.81)
    return (
        "\t(symbol\n"
        f'\t\t(lib_id "{lib}:{name}")\n'
        f"\t\t(at {cec_sch.f(x)} {cec_sch.f(y)} {cec_sch.f(rot % 360)})\n\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n"
        "\t\t(fields_autoplaced yes)\n"
        f'\t\t(uuid "{cec_sch.u()}")\n'
        f'\t\t(property "Reference" "{ref}" (at {cec_sch.f(x)} {cec_sch.f(y - off)} 0) '
        f'(effects (font (size 1.27 1.27))))\n'
        f'\t\t(property "Value" "{val}" (at {cec_sch.f(x)} {cec_sch.f(y + off)} 0) '
        f'(effects (font (size 1.27 1.27))))\n'
        f'\t\t(property "Footprint" "{fp}" (at {cec_sch.f(x)} {cec_sch.f(y)} 0) '
        f'(effects (font (size 1.27 1.27)) (hide yes)))\n'
        f'\t\t(property "Datasheet" "{ds}" (at {cec_sch.f(x)} {cec_sch.f(y)} 0) '
        f'(effects (font (size 1.27 1.27)) (hide yes)))\n'
        f"{extra}"
        f"{pinblk}\n"
        f'\t\t(instances\n\t\t\t(project "{project}"\n\t\t\t\t'
        f'(path "/{root}" (reference "{ref}") (unit 1))\n\t\t\t)\n\t\t)\n'
        "\t)")


# ============================================================================
# 2) LOCAL WIRE ROUTING
# ============================================================================

def emit_junction(x, y):
    return (f'\t(junction (at {cec_sch.f(x)} {cec_sch.f(y)}) (diameter 0) '
            f'(color 0 0 0 0) (uuid "{cec_sch.u()}"))')


def wire_adjacent(pa, pb, boxes=(), pin_pts=frozenset(), max_len=25.4):
    """Real Manhattan wire segments directly between two ABSOLUTE pin points
    (reuses cec_sch.route_L, the existing 1-2 bend L-router with keep-out and
    foreign-pin avoidance), for CLOSE pairs only. Returns None -- the caller
    should fall back to a net label -- if no clean L-route exists, or if the
    routed length exceeds `max_len` (a long haul staying a label is correct
    schematic style, not a routing failure)."""
    pa = (round(pa[0], 3), round(pa[1], 3))
    pb = (round(pb[0], 3), round(pb[1], 3))
    segs = cec_sch.route_L(pa, pb, boxes, pin_pts)
    if segs is None:
        return None
    length = sum(math.hypot(x2 - x1, y2 - y1) for x1, y1, x2, y2 in segs)
    if length > max_len:
        return None
    return segs


def wire_chain(points, boxes=(), pin_pts=frozenset(), max_len=25.4):
    """Route a LINEAR CHAIN of >=2 absolute points pairwise (p0-p1, p1-p2, ...)
    -- e.g. a divider chain rail->R1->node->R2->GND. Returns None if any leg
    fails; otherwise the full segment list. Each interior point (shared by two
    legs) is a natural electrical joint; the caller adds a junction dot there
    only if a THIRD wire (a tap) also lands on it -- see wire_decouplers for
    the T-junction pattern."""
    segs = []
    for a, b in zip(points, points[1:]):
        leg = wire_adjacent(a, b, boxes, pin_pts, max_len=max_len)
        if leg is None:
            return None
        segs.extend(leg)
    return segs


# ============================================================================
# 3) DECOUPLER ADJACENCY (ports cec_pcb/cec_synth_pipeline's netlist-driven
#    PCB ownership concept to schematic space)
# ============================================================================

_POWER_NET = re.compile(r"(^|/)(GND|\+?3V3|\+?5VSB|\+?5V|VBUS|VCC|\+?12V)$", re.I)


def is_power_net(n):
    """A global power/GND rail, or a sense FORCE net (*_HI/_LO) -- 'power-like'
    for ownership purposes so a filter cap doesn't bind to a shunt as though
    the shunt were a signal owner. Same rule cec_synth_pipeline's PCB-side
    derive_passive_spec uses (_is_power_net), ported here unchanged."""
    base = n.rsplit("/", 1)[-1]
    return bool(_POWER_NET.search(n)) or base in ("GND",) or n.endswith(("_HI", "_LO"))


def _owner_pin(nets, owner, shared_nets):
    """A pin number of `owner` sitting on one of `shared_nets`, preferring a
    power pin (so a decoupler parks at the owner's power-pin edge -- mirrors
    the PCB side's _owner_pad)."""
    cand = []
    for n in shared_nets:
        for r, p in nets.get(n, []):
            if r == owner:
                cand.append((1 if is_power_net(n) else 0, p))
    if not cand:
        return None
    cand.sort(reverse=True)
    return cand[0][1]


def derive_owners(nets, passive_refs, ic_refs):
    """SCHEMATIC-SPACE port of cec_synth_pipeline.derive_passive_spec (the
    PCB-side auto_cluster ownership deriver): ref -> (owner_ic, owner_pin).
    A passive's owner is the IC it shares the most non-power SIGNAL nets with
    (a filter cap binds to its sensing IC); a passive on ONLY power/GND nets
    (a plain decoupler) is BALANCED across the ICs sharing that rail, so
    decoupling doesn't pile onto one IC. `nets`: the same {name: [(ref,pin),
    ...]} dict the CEC generators already build (see gen-modules.py)."""
    nets_of = defaultdict(set)
    for n, conns in nets.items():
        for r, _p in conns:
            nets_of[r].add(n)
    ic_nets = {ic: nets_of.get(ic, set()) for ic in ic_refs}
    load = {ic: 0 for ic in ic_refs}
    spec = {}
    for pref in passive_refs:
        pnets = nets_of.get(pref, set())
        if not pnets:
            continue
        sig = []
        for ic, icn in ic_nets.items():
            signals = [n for n in (pnets & icn) if not is_power_net(n)]
            if signals:
                sig.append((len(signals), ic))
        if sig:
            owner = max(sig)[1]
        else:
            pwr_ics = [ic for ic, icn in ic_nets.items() if pnets & icn]
            if not pwr_ics:
                continue
            owner = min(pwr_ics, key=lambda ic: load[ic])
            load[owner] += 1
        pin = _owner_pin(nets, owner, pnets & ic_nets[owner])
        if pin:
            spec[pref] = (owner, pin)
    return spec


def place_decouplers(placement, used, parts, ic, ic_pin, caps, *,
                      side="above", pitch=5.08, rise=7.62):
    """Place `caps` (2-pin, already present in `parts`, in the natural
    ROT_VERTICAL orientation) in a ROW next to `ic`'s `ic_pin` (its owning
    power pin, e.g. from derive_owners()). Mutates `placement` (adds each cap
    at (x, y, rot)). Returns a wiring PLAN dict for wire_decouplers() to turn
    into real copper -- er, real wires (rail + GND stubs), not labels."""
    ax, ay, _dx, _dy = pin_abs_rot(placement, used, parts, ic, ic_pin)
    row_y = ay - rise if side == "above" else ay + rise
    x0 = ax + pitch
    for i, cap in enumerate(caps):
        placement[cap] = (x0 + i * pitch, row_y, ROT_VERTICAL)
    return {"ic": ic, "ic_pin_xy": (ax, ay), "caps": list(caps), "side": side}


def wire_decouplers(plan, placement, used, parts, project, root, pwr_ref):
    """Realize a place_decouplers() plan as REAL structure: a horizontal rail
    wire tapped down (side='above') or up (side='below') into every cap's
    rail pin ('1') PLUS the IC's own power pin -- with a junction dot at every
    INTERIOR tap (a true T-junction: KiCad requires the explicit dot whenever
    3+ wire-ends meet at a point) -- and a GND stub + power-port symbol under
    every cap's ground pin ('2'). `pwr_ref` is a zero-arg callable minting a
    fresh "#PWRnn" reference (see cec_sch.build_schematic's pwr_ref/pwr_seq).
    Returns (wires, junctions, power_symbols) -- three str lists to splice
    into the sheet body."""
    ax, ay = plan["ic_pin_xy"]
    side = plan["side"]
    taps = []
    for cap in plan["caps"]:
        px, py, _dx, _dy = pin_abs_rot(placement, used, parts, cap, "1")
        taps.append((cap, px, py))
    outer_y = (min if side == "above" else max)(t[2] for t in taps)
    rail_y = outer_y - cec_sch.STUB if side == "above" else outer_y + cec_sch.STUB
    xs = [ax] + [t[1] for t in taps]
    x_lo, x_hi = min(xs), max(xs)
    ends = {round(x_lo, 3), round(x_hi, 3)}

    wires = [cec_sch.emit_wire(x_lo, rail_y, x_hi, rail_y),   # the rail itself
             cec_sch.emit_wire(ax, ay, ax, rail_y)]            # the IC's drop
    junctions = []
    if round(ax, 3) not in ends:
        junctions.append(emit_junction(ax, rail_y))
    for cap, px, py in taps:
        wires.append(cec_sch.emit_wire(px, py, px, rail_y))
        if round(px, 3) not in ends:
            junctions.append(emit_junction(px, rail_y))

    power_syms = []
    for cap in plan["caps"]:
        gx, gy, gdx, gdy = pin_abs_rot(placement, used, parts, cap, "2")
        bx, by = gx + gdx * cec_sch.STUB, gy + gdy * cec_sch.STUB
        wires.append(cec_sch.emit_wire(gx, gy, bx, by))
        power_syms.append(cec_sch.emit_global_power("GND", bx, by, project, root,
                                                     pwr_ref(), 0))
    return wires, junctions, power_syms


# ============================================================================
# 4) TEXT-COLLISION ENGINE
# ============================================================================
#
# CALIBRATION (measured, not guessed): a real `kicad-cli sch export svg` was
# rendered on a set of representative ref/value strings ("C10", "100nF", "R1",
# "10kOhm", "U1", "INA240A3", "GND") at the repo's uniform font size 1.27mm.
# KiCad's SVG output carries an exact `textLength` attribute per <text> (its
# own layout engine's precomputed advance width for that exact string+size),
# so this is a measurement, not a rendering guess. Per-character advance
# widths ranged ~1.14mm ("INA240A3", narrow run of caps+digits) to ~1.37mm
# ("U1"), averaging ~1.29mm across the representative set -- i.e. a width
# factor of ~1.016x the font size. That is well ABOVE a naive monospace-TTF
# guess of ~0.75x: KiCad's stroke ("Newstroke") font runs wide. Height is not
# independently measured (would need per-glyph path-bbox extraction from the
# SVG's <path> data, not just the <text> tag); 1.30x the font size is used as
# a safe upper bound (cap height + margin for the occasional descender/
# ascender) for the mostly-uppercase/digit ref/value/label text this repo
# generates. See tests/test_sch_layout.py::test_font_calibration for the
# probe that reproduces the measurement.
CHAR_WIDTH_FACTOR = 1.02     # mm advance width per character, per mm of font size
CHAR_HEIGHT_FACTOR = 1.30    # mm vertical extent, per mm of font size (approx.)


def text_bbox(text, size, x, y, angle=0, justify_h=None, justify_v=None):
    """Approximate absolute bbox (xmin,xmax,ymin,ymax) of schematic text
    anchored at (x,y), font `size` (mm), rotated by `angle` (0/90/180/270),
    with KiCad justify (h in left/right/None=center, v in top/bottom/
    None=center). Multi-line text (embedded newlines) uses the longest line
    for width and n_lines for height."""
    lines = text.split("\n") or [""]
    width = max((len(ln) for ln in lines), default=1) * size * CHAR_WIDTH_FACTOR
    height = len(lines) * size * CHAR_HEIGHT_FACTOR
    if justify_h == "left":
        x0, x1 = x, x + width
    elif justify_h == "right":
        x0, x1 = x - width, x
    else:
        x0, x1 = x - width / 2, x + width / 2
    if justify_v == "top":
        y0, y1 = y, y + height
    elif justify_v == "bottom":
        y0, y1 = y - height, y
    else:
        y0, y1 = y - height / 2, y + height / 2
    if angle % 360 == 0:
        return (x0, x1, y0, y1)
    corners = [(x0, y0), (x0, y1), (x1, y0), (x1, y1)]
    rc = [_rotate_about(cx, cy, x, y, angle) for cx, cy in corners]
    rxs = [c[0] for c in rc]; rys = [c[1] for c in rc]
    return (min(rxs), max(rxs), min(rys), max(rys))


def _bbox_overlap(a, b, margin=0.0):
    ax0, ax1, ay0, ay1 = a; bx0, bx1, by0, by1 = b
    return not (ax1 <= bx0 - margin or bx1 <= ax0 - margin
                or ay1 <= by0 - margin or by1 <= ay0 - margin)


_TEXT_KINDS = (
    ("property", re.compile(r'\(property\s+"((?:[^"\\]|\\.)*)"\s+"((?:[^"\\]|\\.)*)"')),
    ("label", re.compile(r'\(label\s+"((?:[^"\\]|\\.)*)"')),
    ("global_label", re.compile(r'\(global_label\s+"((?:[^"\\]|\\.)*)"')),
    ("hierarchical_label", re.compile(r'\(hierarchical_label\s+"((?:[^"\\]|\\.)*)"')),
    ("text", re.compile(r'\(text\s+"((?:[^"\\]|\\.)*)"')),
)


def _unescape(s):
    return s.replace('\\"', '"').replace("\\\\", "\\")


def _strip_lib_symbols(text):
    """Blank out the `(lib_symbols ...)` block (same length, so byte offsets
    elsewhere stay valid) -- its symbol definitions use LOCAL untransformed
    coordinates and must not be scanned as if they were placed instances."""
    m = re.search(r'\(lib_symbols\b', text)
    if not m:
        return text
    block = cec_sch.carve(text, m.start())
    return text[:m.start()] + (" " * len(block)) + text[m.start() + len(block):]


def _extract_at(block):
    m = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+(-?[\d.]+))?\)', block)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2)), float(m.group(3) or 0)


def _extract_font(block):
    m = re.search(r'\(font\b.*?\(size\s+([\d.]+)\s+([\d.]+)\)', block, re.S)
    if not m:
        return 1.27
    return float(m.group(1))


def _extract_justify(block):
    m = re.search(r'\(justify([^)]*)\)', block)
    if not m:
        return None, None
    toks = m.group(1).split()
    h = "left" if "left" in toks else ("right" if "right" in toks else None)
    v = "top" if "top" in toks else ("bottom" if "bottom" in toks else None)
    return h, v


def _is_hidden(block):
    """True if THIS element's effects clause carries a hide flag -- either
    the compact `(hide yes)` this repo's generators emit, or the bare `hide`
    token native kicad-authored files use."""
    i = block.rfind("(effects")
    if i < 0:
        return False
    seg = cec_sch.carve(block, i)
    return bool(re.search(r'\bhide\b', seg))


def _symbol_spans(work):
    """[(start, end, (ox,oy), ref)] for every schematic SYMBOL INSTANCE in
    `work` (lib_symbols already blanked). Used to find a property's parent
    symbol (its origin, for the nudge push-direction, and its ref, for
    reporting/ordering)."""
    spans = []
    for m in re.finditer(r'\(symbol\n', work):
        s = m.start()
        block = cec_sch.carve(work, s)
        at = _extract_at(block)
        if not at:
            continue
        refm = re.search(r'\(property\s+"Reference"\s+"((?:[^"\\]|\\.)*)"', block)
        spans.append((s, s + len(block), (at[0], at[1]), refm.group(1) if refm else "?"))
    return spans


def _origin_containing(spans, offset):
    for s, e, origin, ref in spans:
        if s <= offset < e:
            return origin, ref
    return None, None


def _extract_text_elements(text, *, with_spans=False):
    """Parse every VISIBLE Reference/Value property, net label (label/
    global_label/hierarchical_label), and free text element in a .kicad_sch,
    skipping the lib_symbols section (library-local coordinates) and any
    hidden field. Returns a list of dicts: kind, text, label (human string),
    at (x,y,ang), size, justify, bbox, ref (owning symbol ref, properties
    only) -- plus, if with_spans, at_span (byte offsets of the `(at ...)`
    clause, for nudge_texts to text-splice) and origin (owning symbol's
    placement, for the push direction)."""
    work = _strip_lib_symbols(text)
    spans = _symbol_spans(work) if with_spans else None
    elems = []
    for kind, pat in _TEXT_KINDS:
        for m in pat.finditer(work):
            block = cec_sch.carve(work, m.start())
            if _is_hidden(block):
                continue
            at = _extract_at(block)
            if not at:
                continue
            x, y, ang = at
            size = _extract_font(block)
            jh, jv = _extract_justify(block)
            ref = None
            if kind == "property":
                pname, pval = m.group(1), _unescape(m.group(2))
                if pname not in ("Reference", "Value"):
                    continue
                content = pval
                label = f'{pname}="{pval}"'
            else:
                content = _unescape(m.group(1))
                label = f'{kind}:"{content}"'
                pname = kind
            if not content:
                continue
            bbox = text_bbox(content, size, x, y, ang, jh, jv)
            el = {"kind": kind, "name": pname, "text": content, "label": label,
                  "at": (x, y, ang), "size": size, "justify": (jh, jv), "bbox": bbox}
            if with_spans:
                at_m = re.search(r'\(at\s+(-?[\d.]+)\s+(-?[\d.]+)(?:\s+(-?[\d.]+))?\)', block)
                el["at_span"] = (m.start() + at_m.start(), m.start() + at_m.end())
                if kind == "property":
                    origin, oref = _origin_containing(spans, m.start())
                    el["origin"] = origin or (x, y)
                    el["ref"] = oref
                label = f'{label} [{el.get("ref")}]' if kind == "property" else label
                el["label"] = label
            elems.append(el)
    return elems


def detect_overlaps(sch_path, margin=0.0):
    """Text-vs-text collision CHECK on ANY .kicad_sch: symbol Reference/Value
    properties, net labels, and free text (e.g. cec_sch.emit_section titles).
    Hidden elements are skipped. Returns a list of (elemA, elemB) dict pairs
    whose bboxes overlap, each dict carrying kind/text/label/at/bbox."""
    text = open(sch_path).read()
    elems = _extract_text_elements(text)
    pairs = []
    for i, a in enumerate(elems):
        for b in elems[i + 1:]:
            if _bbox_overlap(a["bbox"], b["bbox"], margin):
                pairs.append((a, b))
    return pairs


def nudge_texts(sch_path, out_path=None, *, step=1.27, max_push=16, margin=0.2):
    """Deterministic collision resolution for symbol Reference/Value FIELD
    TEXT ONLY -- pins, wires, and net labels are NEVER moved (a label must
    stay exactly at its wire's endpoint to stay electrically connected; a pin
    obviously can't move without moving the part). For each property that
    currently collides with something, push it straight out along ITS OWN
    existing offset direction from the parent symbol's origin, in `step`
    increments, up to `max_push` steps; if still colliding at the far end,
    flip to the opposite side once. Resolution runs entirely in memory
    against the full text-element set (so a move that clears one collision
    but creates another against an as-yet-unmoved neighbor is still caught),
    then patches ONLY the moved `(at X Y ANG)` clauses into the file text (a
    targeted splice, not a full re-serialize). Returns (n_moved,
    n_still_colliding)."""
    text = open(sch_path).read()
    elems = _extract_text_elements(text, with_spans=True)

    def collides(e):
        for o in elems:
            if o is e:
                continue
            if _bbox_overlap(e["bbox"], o["bbox"], margin):
                return True
        return False

    to_fix = sorted((e for e in elems if e["kind"] == "property" and collides(e)),
                    key=lambda e: (e.get("ref") or "", e["name"]))
    for e in to_fix:
        ox, oy = e["origin"]
        x, y, ang = e["at"]
        if abs(x - ox) > abs(y - oy):
            dirx, diry = (1.0 if x >= ox else -1.0), 0.0
        else:
            dirx, diry = 0.0, (1.0 if y >= oy else -1.0)
        moved = False
        for flip in (1, -1):
            fx, fy = dirx * flip, diry * flip
            saved_bbox, saved_at = e["bbox"], e["at"]
            for k in range(1, max_push + 1):
                nx, ny = x + fx * step * k, y + fy * step * k
                e["bbox"] = text_bbox(e["text"], e["size"], nx, ny, ang, *e["justify"])
                if not collides(e):
                    e["at"] = (nx, ny, ang)
                    moved = True
                    break
            if moved:
                break
            e["bbox"], e["at"] = saved_bbox, saved_at
        e["_moved"] = moved

    still = sum(1 for e in elems if e["kind"] == "property" and collides(e))

    edits = [(e["at_span"][0], e["at_span"][1],
              f'(at {cec_sch.f(e["at"][0])} {cec_sch.f(e["at"][1])} {cec_sch.f(e["at"][2])})')
             for e in to_fix if e.get("_moved")]
    edits.sort(key=lambda t: -t[0])
    out = text
    for s, en, newat in edits:
        out = out[:s] + newat + out[en:]
    open(out_path or sch_path, "w").write(out)
    return sum(1 for e in to_fix if e.get("_moved")), still


# ============================================================================
# DEMO -- a small, self-contained sheet exercising every ability above
# ============================================================================

def build_demo(out_path):
    """Build build/sch-layout-demo.kicad_sch: an IC (INA240) with 4 REAL-WIRED
    decouplers on its V+ pin (place_decouplers/wire_decouplers), plus a
    REAL-WIRED resistor-divider chain (+3V3 -> R1 -> node -> R2 -> GND) with a
    tapped filter cap at the node (a T-junction, wire_adjacent x2 + a manual
    junction dot) -- i.e. genuine drawn structure, not label aliasing. Returns
    a small stats dict. Uses only real vendored parts (cec-vendor.kicad_sym)."""
    libs = {"cec-vendor": open(f"{_ROOT}/lib/vendor/cec-vendor.kicad_sym").read(),
            "power": open(f"{_ROOT}/lib/vendor/cec-power.kicad_sym").read()}
    parts = {
        "U1": ("cec-vendor", "INA240", "INA240A3"),
        "C1": ("cec-vendor", "C_Small", "100n"),
        "C2": ("cec-vendor", "C_Small", "100n"),
        "C3": ("cec-vendor", "C_Small", "100n"),
        "C4": ("cec-vendor", "C_Small", "100n"),
        "R1": ("cec-vendor", "R_Small", "10k"),
        "R2": ("cec-vendor", "R_Small", "10k"),
        "C5": ("cec-vendor", "C_Small", "1n"),
    }
    used = cec_sch.load_symbols(libs, parts)
    project = "sch-layout-demo"
    root = cec_sch.u()

    placement = {
        "U1": (101.6, 127.0, 0),
        "R1": (152.4, 111.76, 0),
        "R2": (152.4, 127.0, 0),
        "C5": (167.64, 119.38, 0),
    }
    plan = place_decouplers(placement, used, parts, "U1", "6", ["C1", "C2", "C3", "C4"], side="above")

    body = [emit_symbol_rot(r, parts[r][0], parts[r][1], parts[r][2], *placement[r],
                            used[(parts[r][0], parts[r][1])]["pins"], project, root)
            for r in parts]

    pwr_seq = [0]
    def pwr_ref(prefix="#PWR"):
        pwr_seq[0] += 1
        return f"{prefix}{pwr_seq[0]:02d}"

    wires, junctions, power_syms = wire_decouplers(plan, placement, used, parts, project, root, pwr_ref)
    ic_ax, ic_ay = plan["ic_pin_xy"]
    rail_y = pin_abs_rot(placement, used, parts, plan["caps"][0], "1")[1] - cec_sch.STUB

    boxes = [bb for bb in (body_box_abs(used[(parts[r][0], parts[r][1])]["block"], *placement[r])
                          for r in parts) if bb]
    pin_pts = set()
    for r in parts:
        for pnum in used[(parts[r][0], parts[r][1])]["pins"]:
            ax, ay, _dx, _dy = pin_abs_rot(placement, used, parts, r, pnum)
            pin_pts.add((round(ax, 3), round(ay, 3)))

    r1_top = pin_abs_rot(placement, used, parts, "R1", "1")[:2]
    r1_bot = pin_abs_rot(placement, used, parts, "R1", "2")[:2]
    r2_top = pin_abs_rot(placement, used, parts, "R2", "1")[:2]
    r2_bot = pin_abs_rot(placement, used, parts, "R2", "2")[:2]
    c5_top = pin_abs_rot(placement, used, parts, "C5", "1")[:2]
    c5_bot = pin_abs_rot(placement, used, parts, "C5", "2")[:2]

    seg1 = wire_adjacent(r1_bot, r2_top, boxes, pin_pts)
    seg2 = wire_adjacent(r1_bot, c5_top, boxes, pin_pts)
    if seg1 is None or seg2 is None:
        raise SystemExit("build_demo: divider chain routing failed (unexpected at this fixed layout)")
    wires += [cec_sch.emit_wire(*s) for s in seg1]
    wires += [cec_sch.emit_wire(*s) for s in seg2]
    junctions.append(emit_junction(*r1_bot))     # 3 wire-ends meet at the divider node

    bx, by = r1_top[0], r1_top[1] - cec_sch.STUB
    wires.append(cec_sch.emit_wire(r1_top[0], r1_top[1], bx, by))
    power_syms.append(cec_sch.emit_global_power("+3V3", bx, by, project, root, pwr_ref(), 180))
    for (px, py) in (r2_bot, c5_bot):
        bx, by = px, py + cec_sch.STUB
        wires.append(cec_sch.emit_wire(px, py, bx, by))
        power_syms.append(cec_sch.emit_global_power("GND", bx, by, project, root, pwr_ref(), 0))

    # tie U1's decoupler rail onto the SAME +3V3 global net (a bare power port
    # is pin type power_in -- it does not by itself satisfy ERC's "driven by
    # an Output Power pin" rule; a genuine regulator output would normally do
    # that job, but this toy demo has none, so +3V3/GND both get an explicit
    # PWR_FLAG below, same convention as cec_sch.build_schematic's
    # powerflag_nets stamp).
    rx, ry = ic_ax, rail_y - cec_sch.STUB
    wires.append(cec_sch.emit_wire(ic_ax, rail_y, rx, ry))
    power_syms.append(cec_sch.emit_global_power("+3V3", rx, ry, project, root, pwr_ref(), 180))
    junctions.append(emit_junction(ic_ax, rail_y))   # now a true 3-way: rail + IC drop + +3V3 tap

    flag_x, flag_y = placement["U1"][0] - 25.4, placement["U1"][1] + 40.64
    wires.append(cec_sch.emit_wire(flag_x, flag_y, flag_x, flag_y - cec_sch.STUB))
    power_syms.append(cec_sch.emit_global_power("PWR_FLAG", flag_x, flag_y - cec_sch.STUB,
                                                project, root, pwr_ref("#FLG"), 180))
    power_syms.append(cec_sch.emit_global_power("GND", flag_x, flag_y, project, root, pwr_ref(), 0))
    wires.append(cec_sch.emit_wire(flag_x + 12.7, flag_y, flag_x + 12.7, flag_y - cec_sch.STUB))
    power_syms.append(cec_sch.emit_global_power("PWR_FLAG", flag_x + 12.7, flag_y - cec_sch.STUB,
                                                project, root, pwr_ref("#FLG"), 180))
    power_syms.append(cec_sch.emit_global_power("+3V3", flag_x + 12.7, flag_y,
                                                project, root, pwr_ref(), 0))

    used_pins = {("U1", "6")}
    fully_used_refs = {"C1", "C2", "C3", "C4", "R1", "R2", "C5"}
    ncs = []
    for r in parts:
        if r in fully_used_refs:
            continue
        for pnum in used[(parts[r][0], parts[r][1])]["pins"]:
            if (r, pnum) in used_pins:
                continue
            ax, ay, _dx, _dy = pin_abs_rot(placement, used, parts, r, pnum)
            ncs.append(cec_sch.emit_noconnect(ax, ay))

    need_syms = {"GND", "+3V3"}
    extra_blocks = [cec_sch._power_block(libs, s) for s in sorted(need_syms)]
    content = (
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
        f"\t(uuid \"{root}\")\n\t(paper \"A4\")\n"
        f"{cec_sch.lib_symbols_section(used, extra_blocks)}\n"
        + "\n".join(body) + "\n"
        + "\n".join(wires) + "\n"
        + ("\n".join(junctions) + "\n" if junctions else "")
        + ("\n".join(power_syms) + "\n" if power_syms else "")
        + ("\n".join(ncs) + "\n" if ncs else "")
        + "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    open(out_path, "w").write(content)
    return {"parts": len(parts), "wires": len(wires), "junctions": len(junctions),
            "power_symbols": len(power_syms), "nc": len(ncs)}


# ============================================================================
# 5) CLI
# ============================================================================

def _cli_check_overlaps(path, threshold):
    pairs = detect_overlaps(path)
    for a, b in pairs:
        print(f"OVERLAP: {a['label']} @ ({a['at'][0]:.2f},{a['at'][1]:.2f})  <->  "
              f"{b['label']} @ ({b['at'][0]:.2f},{b['at'][1]:.2f})")
    print(f"{len(pairs)} overlapping text pair(s) in {path}")
    return 1 if len(pairs) > threshold else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="cec_sch_layout -- schematic layout-quality engine")
    ap.add_argument("--check-overlaps", metavar="SCH",
                     help="report colliding text pairs; exits nonzero above --threshold")
    ap.add_argument("--threshold", type=int, default=0,
                     help="max allowed overlap count before nonzero exit (default 0)")
    ap.add_argument("--nudge", metavar="SCH", help="apply nudge_texts() to SCH")
    ap.add_argument("--out", metavar="PATH", help="output path for --nudge (default: in place)")
    ap.add_argument("--demo", metavar="PATH", help="build the demo sheet at PATH")
    args = ap.parse_args(argv)
    if args.check_overlaps:
        return _cli_check_overlaps(args.check_overlaps, args.threshold)
    if args.nudge:
        n_moved, still = nudge_texts(args.nudge, args.out)
        print(f"nudged {n_moved} field(s); {still} still colliding")
        return 0
    if args.demo:
        stats = build_demo(args.demo)
        print(f"demo written to {args.demo}: {stats}")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
