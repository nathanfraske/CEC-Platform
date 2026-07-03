#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# ============================================================================
#  cec_sch_archetypes -- REUSABLE BLOCK TEMPLATES for cec_sch_compose (T4)
# ============================================================================
# Extracted 2026-07-03 from the WORKING compositions -- the hub-enterprise
# 01a-01g compose functions (the hand-built precursors: eFuse template x3,
# divider columns, pull-up hangs, decoupler rails) and the ent-common P4+T1
# leaf compositions (protection chains, crystal blocks, decoupler banks) --
# per the charter's T4 row. Every template here has at least one REAL caller;
# nothing is speculative. Deliberately modest parameterization: a template
# that takes 30 knobs is worse than two similar 60-line functions.
#
# All functions take a cec_sch_compose.Compose collector `c` and work in
# 1.27mm GRID UNITS (the Compose convention). Geometry facts they rely on
# (measured from the vendored libs via cec_sch.pin_table):
#   - R_Small / C_Small / Crystal_Small: pin 1 at local (0,+2.54), pin 2 at
#     (0,-2.54) -> at rot 0 they read VERTICAL, pin 1 up (2u above origin);
#     at rot 90 HORIZONTAL, pin 1 left; rot 180 pin 1 down; rot 270 pin 1
#     right. (The cec_sch_layout rotation convention, round-trip verified.)
#   - D_Schottky: pin 1 = K at local (-3.81,0), pin 2 = A at (+3.81,0) ->
#     rot 270 stands it up with K on TOP (3u above origin) -- the clamp-to-
#     GND orientation (K on the protected node, A down to GND).
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


# ---------------------------------------------------------------------------
# (a2) divider chain -- two vertical resistors in a column with a NAMED tap
# between them, drawn as real wires (the hub eFuse UVLO/OVLO columns and the
# 01g rail-sense columns are the hand-built precursors). Top pin of `rt` and
# bottom pin of `rb` are deliberately NOT consumed: the generic build_leaf
# pass gives them their rail stamp / GND stamp / label per the net tables.
# Callers: ent-common power leaf (UVLO + OVP), cec_sch_archetypes.
# protected_rail below.
# ---------------------------------------------------------------------------
def divider_chain(c, rt, rb, x, y_top, tap=None, tap_ang=180, text_side="left",
                  tap_kind="label"):
    """rt at (x, y_top), rb 8u below; the mid tap wired through a corner
    point that carries the tap label (label binds at a wire endpoint -- the
    two chain segments MEET at the tap point, same pattern the hub's
    compose_efuse used)."""
    c.place(rt, x, y_top)
    c.place(rb, x, y_top + 8)
    c.text_side[rt] = c.text_side[rb] = text_side
    mid = (x, y_top + 4)
    c.wire(c.pin(rt, "2"), mid, c.pin(rb, "1"))
    if tap:
        if tap_kind == "hier":
            c.hier(tap, *mid, tap_ang)
        else:
            c.label(tap, *mid, tap_ang)
    c.use((rt, "2"), (rb, "1"))
    return mid


# ---------------------------------------------------------------------------
# (d1) protection chain -- a jack-pin's series/shunt protection network drawn
# left-to-right: series elements (R rot 90) in the run, shunt elements
# hanging off named node split points (clamp diodes rot 270 = K up, code/
# bleed resistors rot 0 = pin 1 up), ending in a hier export or label. The
# shunts' bottom pins are NOT consumed (generic pass -> GND stamps).
# Extracted from ent-common's DETECT and pin-7 chains (2 real callers).
# ---------------------------------------------------------------------------
def protection_chain(c, src, items, out, out_kind="hier", node_label=None,
                     pitch=6):
    """src: (x,y) start point in u (already-consumed jack-pin location --
    caller consumes the jack pin and, if needed, wires src from it).
    items: sequence of ("series", ref) | ("shunt", ref).
    A shunt ref starting with "D" is a clamp diode (rot 270, K up); anything
    else is a vertical resistor (rot 0, pin 1 up).
    out: net name for the chain end; out_kind: "hier" | "label" | "none"
    ("none" leaves the end bare for the caller -- e.g. an S1 edge-column
    export via c.io(out, side, from_pt=end)).
    node_label: optional net name labeled at the first post-series node.
    Returns the end point (u)."""
    x, y = src
    pts = [src]           # split points along the run (wire endpoints)
    labeled = False
    for kind, ref in items:
        if kind == "series":
            # part center 2u past the current point; run resumes 2u after
            c.place(ref, x + pitch // 2 + 1, y, 90)
            a, b = c.pin(ref, "1"), c.pin(ref, "2")
            c.wire(pts[-1], a)
            c.use((ref, "1"), (ref, "2"))
            x = b[0]
            pts = [b]
        else:
            # shunt hanging below a split point `pitch` further along
            x += pitch
            if ref.startswith("D"):
                c.place(ref, x, y + 3, 270)     # K at (x, y), A at (x, y+6)
                c.use((ref, "1"))
            else:
                c.place(ref, x, y + 2)          # pin1 at (x, y), pin2 below
                c.use((ref, "1"))
            c.wire(pts[-1], (x, y))
            if node_label and not labeled:
                c.label(node_label, x, y, 0)
                labeled = True
            pts.append((x, y))
    end = (x + pitch, y)
    c.wire(pts[-1], end)
    if out_kind == "hier":
        c.hier(out, *end, 0)
    elif out_kind == "label":
        c.label(out, *end, 0)
    return end


# ---------------------------------------------------------------------------
# (a3) pull-up hang -- a horizontal signal run with a pull-up resistor whose
# run-side pin sits ON the run (a split point) and whose rail-side pin is
# left to the generic pass (auto rail stamp). The hub eFuse PG/FLT pull-ups
# are the precursors (there: rail pin "2", rot 180 above the run). Callers:
# ent-common power leaf (FLT), MCU leaf (CHIP_PU/GPIO0), T1 leaf (MDIO/
# INT_N/RESET_N).
# ---------------------------------------------------------------------------
def pullup_hang(c, start, end_x, r, rx=None, rail_pin="1", above=True,
                out=None, out_kind="hier", out_ang=0):
    """start: (x,y) run origin in u (caller consumes the IC pin and this
    draws from it). end_x: run end. r placed so its NON-rail pin lands on
    the run at rx (default: 2u before the end). rail_pin: which pin of `r`
    is the rail side ("1" or "2"). above: rail side above the run (True) or
    below. `out`: optional net exported at the run end (hier/label)."""
    x0, y = start
    if rx is None:
        rx = end_x - 2 if end_x > x0 else end_x + 2
    sig_pin = "2" if rail_pin == "1" else "1"
    # rot so the SIGNAL pin points at the run: pin1 is 2u above origin at
    # rot 0 and 2u below at rot 180 (measured convention, header note)
    if above:
        rot = 0 if rail_pin == "1" else 180
        c.place(r, rx, y - 2, rot)
    else:
        rot = 180 if rail_pin == "1" else 0
        c.place(r, rx, y + 2, rot)
    lo, hi = sorted((x0, end_x))
    assert lo < rx < hi, f"pullup_hang: rx {rx} outside run ({lo},{hi})"
    c.wire(start, (rx, y))
    c.wire((rx, y), (end_x, y))
    c.use((r, sig_pin))
    if out:
        if out_kind == "hier":
            c.hier(out, end_x, y, out_ang)
        else:
            c.label(out, end_x, y, out_ang)
    return (end_x, y)


# ---------------------------------------------------------------------------
# (d2) crystal block -- XTAL_A/XTAL_B pins routed to a horizontal crystal
# with per-side load caps below, all drawn (no label aliasing). Callers:
# ent-common MCU leaf (Y1/C9/C10) + T1-PHY leaf (Y2/C22/C23).
# ---------------------------------------------------------------------------
def crystal_block(c, ic, pin_a, pin_b, xtal, cap_a, cap_b, side="left",
                  far=9, near=5, drop=6, cap_gap=4):
    """pin_a = the ic pin whose net carries xtal pin 1 (+ cap_a);
    pin_b = xtal pin 2 (+ cap_b). `side`: which side of the IC the pins
    exit ('left'/'right'). The FARTHER column serves whichever pin sits
    farther from the crystal row (the outer pin), avoiding any wire
    crossing: outer pin -> far column, inner pin -> near column."""
    (ax, ay) = c.pin(ic, pin_a)
    (bx, by) = c.pin(ic, pin_b)
    assert ax == bx, "crystal_block: expects both pins on one IC column"
    sgn = -1 if side == "left" else 1
    x_far, x_near = ax + sgn * far, ax + sgn * near
    yc = max(ay, by) + drop
    # outer (farther-from-row) pin takes the far column
    if abs(yc - ay) >= abs(yc - by):
        col_a, col_b = x_far, x_near
    else:
        col_a, col_b = x_near, x_far
    xm = (col_a + col_b) // 2
    rot = 90 if col_a < col_b else 270      # xtal pin1 must land on col_a
    c.place(xtal, xm, yc, rot)
    c.wire((ax, ay), (col_a, ay), (col_a, yc))
    c.wire((bx, by), (col_b, by), (col_b, yc))
    yc2 = yc + cap_gap
    c.place(cap_a, col_a, yc2)
    c.place(cap_b, col_b, yc2)
    c.wire((col_a, yc), (col_a, yc2 - 2))
    c.wire((col_b, yc), (col_b, yc2 - 2))
    c.use((ic, pin_a), (ic, pin_b), (xtal, "1"), (xtal, "2"),
          (cap_a, "1"), (cap_b, "1"))


# ---------------------------------------------------------------------------
# (b2) standalone decoupler bank -- a row of bypass caps on a drawn rail
# with a rail stamp at its head; for the case where the caps decouple a
# whole rail rather than one reachable IC pin (a 100+-pin MCU/PHY whose
# power pins are buried mid-column -- attaching the T1 place_decouplers rail
# to such a pin would run the rail drop THROUGH the neighboring pins).
# The IC-pin-anchored variant stays cec_sch_layout.place_decouplers/
# wire_decouplers via Compose.rail (wrapped, not duplicated). Cap GND pins
# are left to the generic pass. Callers: ent-common MCU leaf (C11-C18) +
# T1-PHY leaf (C24-C27).
# ---------------------------------------------------------------------------
def decoupler_bank(c, caps, x, y, rail="+3V3", pitch=4):
    """caps at (x + i*pitch, y), rail wire at y-2 split at every cap pin 1
    (a pin binds only at a wire ENDPOINT -- the rail is emitted as per-tap
    segments, never one long segment over the pins), rail stamp on a 2u
    head stub."""
    ry = y - 2
    head = (x - 2, ry)
    c.wire(head, (x, ry))
    for i, cap in enumerate(caps):
        cx = x + i * pitch
        c.place(cap, cx, y)
        if i + 1 < len(caps):
            c.wire((cx, ry), (cx + pitch, ry))
        c.use((cap, "1"))
    c.stamp(rail, *head, 0)


# ---------------------------------------------------------------------------
# (a) protected rail -- the eFuse template GENERALIZED from the hub's
# compose_efuse (01a/01b/01c, TPS25940 with 5-pin IN/OUT buses, which stay
# hand-composed in gen_hub_enterprise): entry rail with the input cap WIRED
# onto it feeding the protection IC's IN pin(s), UVLO/OVP divider columns,
# app-pin hangs (ILIM R / dVdT C), FLT-style pull-up with an export tap, and
# an output rail with the local cap wired on + the out-net export. Assumes
# the single-IN/single-OUT left-entry/right-exit IC shape (TPS26621-class).
# Caller: ent-common power leaf.
# ---------------------------------------------------------------------------
def protected_rail(c, *, ic, origin, in_pin, out_pin, entry_rail,
                   entry_is_port, in_cap, out_cap, dividers, hangs,
                   pullup, out_net, out_kind="hier", extra_in_pins=()):
    """origin: (x,y) placement for `ic` in u.
    entry_rail: net name of the raw rail; entry_is_port: True -> power
    stamp at the rail head, False -> label. in_cap wired onto the entry
    rail; out_cap onto the out rail. dividers: [(rt, rb, tap_net), ...]
    columns left of the IC. hangs: [(ic_pin, part, net_label), ...] parts
    hung below a corner off right-side app pins. pullup: (ic_pin, r,
    export_net) or None. extra_in_pins: further IC pins strapped to the
    entry rail (e.g. an active-high SHDN tied to its own input rail)."""
    ox, oy = origin
    c.place(ic, ox, oy)
    ipx, ipy = c.pin(ic, in_pin)

    # divider columns, leftmost first, left of the IC entry pin
    for i, (rt, rb, tap_net) in enumerate(dividers):
        divider_chain(c, rt, rb, ipx - 18 + i * 6, ipy - 2, tap_net)

    # entry rail: head stamp/label -> input cap tap -> strap taps -> IN pin
    ry = ipy + 8
    head = (ipx - 14, ry)
    ccx = ipx - 10
    c.place(in_cap, ccx, ry + 2)
    c.wire(head, (ccx, ry))
    c.wire((ccx, ry), (ipx - 4, ry))
    c.use((in_cap, "1"))
    if entry_is_port:
        c.stamp(entry_rail, *head, 180)
    else:
        c.label(entry_rail, *head, 180)
    # riser from the rail into the IN pin
    c.wire((ipx - 4, ry), (ipx - 4, ipy), (ipx, ipy))
    c.use((ic, in_pin))
    for pn in extra_in_pins:
        # strap riser: rail -> up -> into the strapped pin (e.g. SHDN tied
        # to its own input rail = always-armed). Split the entry rail at the
        # riser foot (endpoint-binding rule).
        sx, sy = c.pin(ic, pn)
        c.wire((ipx - 4, ry), (sx - 2, ry))
        c.wire((sx - 2, ry), (sx - 2, sy), (sx, sy))
        c.use((ic, pn))

    # right-side app-pin hangs: pin -> corner -> vertical part below.
    # LOWER pins (larger y) get corners NEARER the IC and UPPER pins farther
    # out, so an upper run passes clear over the lower hangs (the hub eFuse
    # right side is the precursor for this fan shape).
    order = sorted(range(len(hangs)), key=lambda i: -c.pin(ic, hangs[i][0])[1])
    for depth, i in enumerate(order):
        pin, part, netlbl = hangs[i]
        px, py = c.pin(ic, pin)
        hx = px + 10 + 4 * depth
        c.place(part, hx, py + 4)
        if netlbl:
            # split the run AT the label point: a label binds only at a wire
            # endpoint (same measured rule divider_chain documents), so the
            # named node must be a segment boundary, never a segment interior
            c.wire((px, py), (px + 2, py))
            c.wire((px + 2, py), (hx, py), (hx, py + 2))
            c.label(netlbl, px + 2, py, 0)
        else:
            c.wire((px, py), (hx, py), (hx, py + 2))
        c.use((ic, pin), (part, "1"))

    # FLT-class pull-up with export at the run end
    if pullup:
        pin, r, export = pullup
        px, py = c.pin(ic, pin)
        c.use((ic, pin))
        pullup_hang(c, (px, py), px + 18, r, rx=px + 14, rail_pin="1",
                    above=True, out=export,
                    out_kind="hier" if export in c.lf.hier_exports else "label")

    # out rail: OUT pin -> corner down -> rail with out cap tap -> export
    opx, opy = c.pin(ic, out_pin)
    oy2 = opy + 6
    c.wire((opx, opy), (opx + 2, opy), (opx + 2, oy2))
    ocx = opx + 6
    c.place(out_cap, ocx, oy2 + 2)
    c.wire((opx + 2, oy2), (ocx, oy2))
    end = (ocx + 6, oy2)
    c.wire((ocx, oy2), end)
    c.use((ic, out_pin), (out_cap, "1"))
    if out_kind == "hier":
        c.hier(out_net, *end, 0)
    else:
        c.label(out_net, *end, 0)
    return end
