#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# cec_sch_hier -- generate a HIERARCHICAL schematic: one sub-sheet per IC with its
# supporting passives grouped around it, and a root sheet that instantiates the blocks
# and holds the connectors. Owner direction: "make each component have a sub-sheet with
# its supporting components grouped around it; make sure text doesn't overlap."
#
# Built on cec_sch's PROVEN flat per-sheet emission (symbols/wires/labels/power ports that
# our real boards use), NOT kicad-sch-api -- which generates valid hierarchical STRUCTURE
# but mis-maps our custom symbols' pin geometry, so its connectivity is unreliable (found
# 2026-06-25). The ONLY new s-expr here is the hierarchical wrapper:
#   - symbol instance paths are "/<root_uuid>/<sheet_uuid>" on a sub-sheet (cec_sch.emit_symbol
#     already takes that path base as its `root` arg);
#   - cross-sheet signal nets are GLOBAL labels (global across the whole hierarchy by name);
#     power rails are power ports (also global by name); block-internal nets are local labels;
#   - the root carries one (sheet ...) block per IC.
#
# CORRECTNESS GATE: verify() asserts the hierarchical netlist's net->pin membership equals
# the FLAT generator's. Run it before trusting the output.
#
#   .venv/bin/python scripts/cec_sch_hier.py eps-8pin        # generate + verify + render
import argparse, datetime, glob, importlib.util, math, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import cec_sch as C

_POWER = re.compile(r"(^\+|GND$|_GND$|5V|3V3|VBUS|VSB)", re.I)

AUTHOR = "Nathan M. Fraske"
COMPANY = "Critical Error Computing L.L.C."
REV = "A"
DATE = datetime.date.today().isoformat()    # generation date; override via build_hier(date=...) / --date


# ---- hierarchical s-expr the flat emitter doesn't have -------------------------------------
def emit_global_label(net, x, y, ang):
    just = "left" if ang in (0, 270) else "right"
    return (f'\t(global_label "{net}" (shape input) (at {C.f(x)} {C.f(y)} {ang})\n'
            f'\t\t(fields_autoplaced yes)\n'
            f'\t\t(effects (font (size 1.27 1.27)) (justify {just}))\n'
            f'\t\t(uuid "{C.u()}")\n'
            f'\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {C.f(x)} {C.f(y)} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (justify left) (hide yes)))\n'
            f'\t)')


def emit_junction(x, y):
    return f'\t(junction (at {C.f(x)} {C.f(y)}) (diameter 0) (color 0 0 0 0) (uuid "{C.u()}"))'


def emit_sheet(name, filename, x, y, w, h, sheet_uuid, project, root_uuid, page):
    return ('\t(sheet\n'
            f'\t\t(at {C.f(x)} {C.f(y)})\n\t\t(size {C.f(w)} {C.f(h)})\n'
            '\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n'
            '\t\t(fields_autoplaced yes)\n'
            '\t\t(stroke (width 0.1524) (type solid))\n\t\t(fill (color 0 0 0 0.0000))\n'
            f'\t\t(uuid "{sheet_uuid}")\n'
            f'\t\t(property "Sheetname" "{name}" (at {C.f(x)} {C.f(y - 0.7116)} 0)\n'
            '\t\t\t(effects (font (size 1.27 1.27)) (justify left bottom)))\n'
            f'\t\t(property "Sheetfile" "{filename}" (at {C.f(x)} {C.f(y + h + 0.5846)} 0)\n'
            '\t\t\t(effects (font (size 1.27 1.27)) (justify left top)))\n'
            f'\t\t(instances\n\t\t\t(project "{project}"\n'
            f'\t\t\t\t(path "/{root_uuid}" (page "{page}"))\n\t\t\t)\n\t\t)\n'
            '\t)')


def _abs_bodybox(bb, ox, oy, rot):
    pts = []
    for cx in (bb[0], bb[1]):
        for cy in (bb[2], bb[3]):
            r = math.radians(rot)
            pts.append((ox + cx * math.cos(r) - cy * math.sin(r), oy - (cx * math.sin(r) + cy * math.cos(r))))
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _ov(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _stub_for_label(ax, ay, dx, dy, text, is_g, bodyboxes, skip, avoid=()):
    """Lengthen a pin's label stub until the label text clears every FOREIGN symbol body AND
    every already-placed label (a global label needs ~3 extra chars for its flag). Returns
    (bx, by, box)."""
    w = (len(text) + (3 if is_g else 0)) * 1.27 * 0.72
    horiz = abs(dx) > abs(dy)
    first = None
    for k in range(13):
        bx, by = ax + dx * (C.STUB + k * 1.27), ay + dy * (C.STUB + k * 1.27)
        if horiz:
            x0, x1 = (bx, bx + w) if dx > 0 else (bx - w, bx)
            box = (x0, by - 0.7, x1, by + 0.7)
        else:
            y0, y1 = (by, by + w) if dy > 0 else (by - w, by)
            box = (bx - 0.7, y0, bx + 0.7, y1)
        if first is None:
            first = (bx, by, box)
        body_hit = any(r != skip and _ov(box, bb) for r, bb in bodyboxes.items())
        if not body_hit and not any(_ov(box, ab) for ab in avoid):
            return bx, by, box
    return first


def build_sheet_file(out_path, project, parts, nets, used, libs, *, instance_path, file_uuid,
                     placement, paper="A4", power_ports=None, powerflag_nets=(),
                     global_nets=(), extra_blocks=(), rotations=None, pre_wires=(),
                     handled_pins=(), junctions=(), extra_terms=(),
                     title="", rev=REV, date=DATE):
    """Emit ONE .kicad_sch (root or sub-sheet) using cec_sch primitives. instance_path is the
    symbol-instance path base (root_uuid, or root_uuid/sheet_uuid for a sub-sheet); file_uuid
    is the file's own uuid. global_nets get global labels; power nets get power ports.
    rotations: {ref: deg} per-symbol rotation. pre_wires: ready s-expr wire strings (the
    direct decoupler<->IC wires). handled_pins: (ref,pin) already connected by a pre_wire ->
    no label/port emitted (the IC side keeps its terminator; the passive side is silent)."""
    power_ports = power_ports or {}
    global_nets = set(global_nets)
    rotations = rotations or {}
    handled_pins = set(handled_pins)
    placement = {r: C.gridsnap(*placement[r]) for r in parts}

    extra = []
    need = set(power_ports.values())
    if powerflag_nets:
        need.add("PWR_FLAG")
    for sym in sorted(need):
        extra.append(C._power_block(libs, sym))

    body = [C.emit_symbol(r, parts[r][0], parts[r][1], parts[r][2], *placement[r],
                          used[(parts[r][0], parts[r][1])]["pins"], project, instance_path, "",
                          rot=rotations.get(r, 0))
            for r in parts]

    bodyboxes = {}
    for r in parts:
        bb = C.sym_body_box(used[(parts[r][0], parts[r][1])]["block"])
        if bb:
            bodyboxes[r] = _abs_bodybox(bb, *placement[r], rotations.get(r, 0))

    seen = {c: net for net, conns in nets.items() for c in conns}
    wires, labels, flags, placed_labels = list(pre_wires), [], [], []
    seq = [0]

    def pref(p):
        seq[0] += 1
        return f"{p}{seq[0]:02d}"

    for net, conns in nets.items():
        leaf = net.rsplit("/", 1)[-1]
        port = power_ports.get(net) or power_ports.get(leaf)
        is_g = net in global_nets or leaf in global_nets
        for ref, pin in conns:
            if (ref, pin) in handled_pins:
                continue
            ax, ay, dx, dy = C.pin_abs(placement, used, parts, ref, pin, rotations)
            ang = 0 if dx > 0 else (180 if dx < 0 else (270 if dy < 0 else 90))
            if port:
                bx, by = ax + dx * C.STUB, ay + dy * C.STUB
                wires.append(C.emit_wire(ax, ay, bx, by))
                flags.append(C.emit_global_power(port, bx, by, project, instance_path,
                                                 pref("#PWR"), 0 if port == "GND" else 180))
            else:                                        # label stub lengthens to clear bodies + labels
                bx, by, lbox = _stub_for_label(ax, ay, dx, dy, leaf, is_g, bodyboxes, ref, placed_labels)
                placed_labels.append(lbox)
                wires.append(C.emit_wire(ax, ay, bx, by))
                labels.append(emit_global_label(leaf, bx, by, ang) if is_g
                              else C.emit_label(leaf, bx, by, ang))

    for t in extra_terms:                            # consolidated power-bus terminators
        if t[0] == 'port':
            flags.append(C.emit_global_power(t[1], t[2], t[3], project, instance_path, pref("#PWR"), t[4]))
        elif t[0] == 'glabel':
            labels.append(emit_global_label(t[1], t[2], t[3], t[4]))
        else:
            labels.append(C.emit_label(t[1], t[2], t[3], t[4]))

    if powerflag_nets and placement:
        bx0 = min(ox for ox, _ in placement.values())
        by0 = round((max(oy for _, oy in placement.values()) + 25.4) / C.GRID) * C.GRID
        for i, net in enumerate(sorted(powerflag_nets)):
            sx, ty, byy = bx0 + i * 25.4, by0, by0 + 10.16
            wires.append(C.emit_wire(sx, ty, sx, byy))
            port = power_ports.get(net, net)
            if port == "GND":
                flags.append(C.emit_global_power("PWR_FLAG", sx, ty, project, instance_path, pref("#FLG"), 180))
                flags.append(C.emit_global_power(port, sx, byy, project, instance_path, pref("#PWR"), 0))
            else:
                flags.append(C.emit_global_power(port, sx, ty, project, instance_path, pref("#PWR"), 180))
                flags.append(C.emit_global_power("PWR_FLAG", sx, byy, project, instance_path, pref("#FLG"), 0))

    ncs = []
    for ref, (lib, name, _v) in parts.items():
        for pin in used[(lib, name)]["pins"]:
            if (ref, pin) in seen or (ref, pin) in handled_pins:
                continue
            ax, ay, _dx, _dy = C.pin_abs(placement, used, parts, ref, pin, rotations)
            ncs.append(C.emit_noconnect(ax, ay))

    juncs = [emit_junction(x, y) for x, y in junctions]
    tblock = C.emit_title_block(title=title, rev=rev, date=date, company=COMPANY, comments=[AUTHOR])
    content = (
        '(kicad_sch\n\t(version 20260306)\n\t(generator "eeschema")\n\t(generator_version "10.0")\n'
        f'\t(uuid "{file_uuid}")\n\t(paper "{paper}")\n'
        f"{tblock}\n"
        f"{C.lib_symbols_section(used, extra)}\n"
        + "\n".join(body) + "\n"
        + ("\n".join(juncs) + "\n" if juncs else "")
        + ("\n".join(wires) + "\n" if wires else "")
        + ("\n".join(labels) + "\n" if labels else "")
        + ("\n".join(flags) + "\n" if flags else "")
        + ("\n".join(ncs) + "\n" if ncs else "")
        + ("\n".join(extra_blocks) + "\n" if extra_blocks else "")
        + '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
    open(out_path, "w").write(content)


# ---- partitioning + net classification ----------------------------------------------------
def partition(parts, nets, used):
    def npins(r):
        return len(used[(parts[r][0], parts[r][1])]["pins"])
    is_conn = lambda r: r[:1].upper() == "J"
    is_pass = lambda r: npins(r) <= 2 and not is_conn(r)
    is_ic = lambda r: npins(r) >= 4 and not is_conn(r)

    edges = {r: set() for r in parts}
    rails = {r: set() for r in parts}
    for net, conns in nets.items():
        refs = sorted({c[0] for c in conns if c[0] in parts})
        if _POWER.search(net.rsplit("/", 1)[-1]) or len(refs) > 6:
            for r in refs:
                rails[r].add(net)
            continue
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                edges[refs[i]].add(refs[j]); edges[refs[j]].add(refs[i])

    ics = [r for r in parts if is_ic(r)]
    owner = {}
    for r in parts:
        if is_pass(r):
            sig = [x for x in edges[r] if is_ic(x)]
            owner[r] = sig[0] if sig else None
    load = {ic: 0 for ic in ics}
    for o in owner.values():
        if o:
            load[o] += 1
    for r in parts:
        if not is_pass(r) or owner.get(r):
            continue
        best, key = None, None
        for ic in ics:
            s = len(rails[r] & rails[ic])
            if s and ((key is None) or (s, -load[ic]) > key):
                key, best = (s, -load[ic]), ic
        if best:
            owner[r] = best; load[best] += 1

    sheet_of = {}
    for r in parts:
        sheet_of[r] = r if is_ic(r) else (owner[r] if is_pass(r) and owner.get(r) else "ROOT")
    blocks = {}
    for r, s in sheet_of.items():
        blocks.setdefault(s, []).append(r)
    return sheet_of, blocks


def _ring(n, cx, cy, rx=33.0, ry=24.0):
    out = []
    for i in range(max(n, 0)):
        a = -math.pi / 2 + 2 * math.pi * i / max(n, 1)
        out.append((round((cx + rx * math.cos(a)) / 1.27) * 1.27,
                    round((cy + ry * math.sin(a)) / 1.27) * 1.27))
    return out


def _consolidate_pins(ref, pingeom, pn, skip, power_ports, global_set):
    """Collapse runs of co-linear same-net power pins of ONE part into a bus + ONE terminator,
    so a connector/MCU with many VBUS/GND pins doesn't stack a label per pin. pingeom:
    {pin:(ax,ay,dx,dy)}. A bus only forms where no foreign pin sits on its line (no shorts).
    Returns (wire_strs, handled{(ref,pin)}, junc_pts, terms) where each term is
    ('port',sym,x,y,rot) | ('glabel',name,x,y,ang) | ('label',name,x,y,ang)."""
    is_pwr = lambda net: bool(net) and bool(_POWER.search(net.rsplit("/", 1)[-1]))
    stub_end = {p: (ax + dx * C.STUB, ay + dy * C.STUB) for p, (ax, ay, dx, dy) in pingeom.items()}
    groups = {}
    for p, (ax, ay, dx, dy) in pingeom.items():
        if (ref, p) in skip:
            continue
        net = pn.get((ref, p))
        if not is_pwr(net):
            continue
        bx, by = stub_end[p]
        vert = abs(dx) > abs(dy)
        key = (net, 'V', round(bx, 2)) if vert else (net, 'H', round(by, 2))
        groups.setdefault(key, []).append((p, ax, ay, bx, by))
    wires, handled, juncs, terms = [], set(), set(), []
    for (net, axis, coord), grp in groups.items():
        if len(grp) < 2:
            continue
        taps = sorted((g[4] if axis == 'V' else g[3]) for g in grp)
        lo, hi = taps[0], taps[-1]
        grp_pins = {g[0] for g in grp}
        if any((abs(stub_end[q][0] - coord) < 0.51 if axis == 'V' else abs(stub_end[q][1] - coord) < 0.51)
               and lo - 0.01 < (stub_end[q][1] if axis == 'V' else stub_end[q][0]) < hi + 0.01
               for q in pingeom if q not in grp_pins):
            continue                                    # foreign pin on the bus line -> skip
        leaf = net.rsplit("/", 1)[-1]
        for (p, ax, ay, bx, by) in grp:
            wires.append(C.emit_wire(ax, ay, bx, by))
            handled.add((ref, p))
            if (by if axis == 'V' else bx) > lo + 0.01:
                juncs.add((round(bx, 3), round(by, 3)))
        if axis == 'V':
            wires.append(C.emit_wire(coord, lo, coord, hi + 2.54))
            tx, ty, ang = coord, hi + 2.54, 270
        else:
            wires.append(C.emit_wire(lo, coord, hi + 2.54, coord))
            tx, ty, ang = hi + 2.54, coord, 0
        port_sym = power_ports.get(net) or power_ports.get(leaf)
        if port_sym:
            terms.append(('port', port_sym, tx, ty, 0 if port_sym == "GND" else 180))
        elif net in global_set or leaf in global_set:
            terms.append(('glabel', leaf, tx, ty, ang))
        else:
            terms.append(('label', leaf, tx, ty, ang))
    return wires, handled, juncs, terms


def layout_block(ic, refs, parts, nets_block, used, power_ports, global_set):
    """Place an IC block: IC centered, each owned 2-pin passive seated INLINE at the IC pin
    it shares a net with (rotated to align) and DIRECTLY WIRED to it (route_L, body-aware) --
    so decouplers attach to the device by a real wire, not a label alias; runs of co-linear
    power pins consolidate to a bus + one terminator. Returns (placements, rotations,
    pre_wire_segs, handled_pins, junctions, terms). route_L failure -> fall back to the label
    path for that passive (no wire, not handled) so connectivity is never risked."""
    ic_key = (parts[ic][0], parts[ic][1])
    ic_pins = list(used[ic_key]["pins"])
    icx, icy = C.gridsnap(150, 110)        # snap ONCE so build_sheet_file's re-snap is a no-op
    placements, rotations = {ic: (icx, icy)}, {}
    pa = {p: C.pin_abs({ic: (icx, icy)}, used, {ic: parts[ic]}, ic, p) for p in ic_pins}
    pn = {(r, p): net for net, conns in nets_block.items() for r, p in conns}
    is_gnd = lambda net: bool(net) and net.rsplit("/", 1)[-1].upper().endswith("GND")

    bb = C.sym_body_box(used[ic_key]["block"])
    body_abs = (icx + bb[0], icx + bb[1], icy - bb[3], icy - bb[2]) if bb else None
    pin_pts = {(round(pa[p][0], 3), round(pa[p][1], 3)) for p in ic_pins}

    wires, handled, used_ic, ring_fallback, juncs = [], set(), set(), [], set()
    for P in [r for r in refs if r != ic]:
        P_key = (parts[P][0], parts[P][1])
        P_pins = list(used[P_key]["pins"])
        cand = []
        if len(P_pins) == 2:
            for pp in P_pins:
                net = pn.get((P, pp))
                if not net:
                    continue
                for ip in ic_pins:
                    if pn.get((ic, ip)) == net and (ic, ip) not in used_ic:
                        cand.append((0 if is_gnd(net) else 1, pp, ip))
        if not cand:
            ring_fallback.append(P)
            continue
        cand.sort(key=lambda c: c[0], reverse=True)
        _, Ppin, icpin = cand[0]
        ax, ay, dx, dy = pa[icpin]
        lx, ly, pang, _len = used[P_key]["pins"][Ppin]
        # orient so the ANCHORED pin faces back toward the IC (-outward): the cap body and
        # its OTHER pin then sit on the far side, so the IC->anchor wire can't cross them
        # (that crossing was breaking connectivity -- the wire ran through the other pin).
        def anchor_out(R):
            a = math.radians(pang + R)
            return (-math.cos(a), math.sin(a))
        rot = min((0, 90, 180, 270),
                  key=lambda R: (anchor_out(R)[0] + dx) ** 2 + (anchor_out(R)[1] + dy) ** 2)
        gap = C.STUB + 5.08
        Tx, Ty = ax + dx * gap, ay + dy * gap
        rr = math.radians(rot)
        rlx, rly = lx * math.cos(rr) - ly * math.sin(rr), lx * math.sin(rr) + ly * math.cos(rr)
        placements[P] = (round((Tx - rlx) / 1.27) * 1.27, round((Ty + rly) / 1.27) * 1.27)
        rotations[P] = rot
        pax, pay, _, _ = C.pin_abs(placements, used, {ic: parts[ic], P: parts[P]}, P, Ppin, rotations)
        segs = C.route_L((round(ax, 3), round(ay, 3)), (round(pax, 3), round(pay, 3)),
                         [body_abs] if body_abs else [], pin_pts)
        if segs is None:                      # blocked -> keep it but connect by label (safe)
            ring_fallback.append(P)
            del placements[P], rotations[P]
            continue
        used_ic.add((ic, icpin))
        for (x1, y1, x2, y2) in segs:
            wires.append(C.emit_wire(x1, y1, x2, y2))
        juncs.add((round(ax, 3), round(ay, 3)))   # IC pin = pin + stub-to-port + this wire (3-way)
        handled.add((P, Ppin))
        pin_pts.add((round(pax, 3), round(pay, 3)))

    # consolidate runs of co-linear same-net power pins of the IC -> bus + ONE terminator
    cw, ch, cj, terms = _consolidate_pins(ic, pa, pn, used_ic, power_ports, global_set)
    wires += cw; handled |= ch; juncs |= cj

    rx = (max(abs(bb[0]), abs(bb[1])) + 22) if bb else 30
    ry = (max(abs(bb[2]), abs(bb[3])) + 16) if bb else 24
    for P, p in zip(ring_fallback, _ring(len(ring_fallback), icx, icy, rx=rx, ry=ry)):
        placements[P] = p
    return placements, rotations, wires, handled, juncs, terms


def build_hier(board, outdir=None, *, rev=REV, date=DATE):
    """Hierarchical generation for a gen-modules MODS board (eps-8pin / pcie-8pin-*)."""
    gm = _gm()
    base = dict(gm.MODS)[board]
    parts, nets = gm.build(board)
    used = C.load_symbols(gm.LIBS, parts)
    return build_hier_from(parts, nets, used, gm.LIBS, base, outdir=outdir, rev=rev, date=date)


def build_hier_rev3(outdir=None, *, rev=REV, date=DATE, root_name=None):
    """Hierarchical version of the 24-pin rev3 board (TPS2121 mux + 16-pin mezzanine + §6.13)
    from gen-24pin-rev3's pre-built parts/nets (its write is guarded under __main__, so this
    import has no side effect). Verify against the flat rev3 netlist (g3.nets). Pass
    outdir=modules/atx-24pin-rev3 + root_name='24pin-module.kicad_sch' to ADOPT it as the
    board's canonical schematic."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("gen_24pin_rev3",
                                                  os.path.join(ROOT, "scripts", "gen-24pin-rev3.py"))
    g3 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g3)
    return build_hier_from(g3.parts, g3.nets, g3.used, g3.gm.LIBS, "24pin-module-rev3",
                           power_ports=g3.POWER_PORTS, outdir=outdir, rev=rev, date=date,
                           root_name=root_name)


def build_hier_from(parts, nets, used, libs, base, *, power_ports=None, outdir=None,
                    rev=REV, date=DATE, root_name=None):
    """Hierarchical generation from pre-built parts/nets — usable by ANY generator (e.g.
    gen-24pin-rev3, with its mux + mezzanine). power_ports defaults to GND/+5VSB/+3V3; pass
    the board's full set (rev3 adds +5V_SYS/+5V_MAIN) so those rails use ports, not labels.
    root_name names the root .kicad_sch (default <base>-hier.kicad_sch); set it to adopt the
    output as a board's canonical schematic (e.g. '24pin-module.kicad_sch')."""
    project = os.path.splitext(root_name)[0] if root_name else f"{base}-hier"
    sheet_of, blocks = partition(parts, nets, used)
    ic_blocks = sorted(b for b in blocks if b != "ROOT")

    net_sheets = {net: {sheet_of.get(r, "ROOT") for r, _ in conns} for net, conns in nets.items()}
    def crossing(net):
        return len(net_sheets.get(net, set())) > 1
    power_ports = power_ports or {"GND": "GND", "+5VSB": "+5VSB", "+3V3": "+3V3"}
    # A net needs a GLOBAL label to cross sheets UNLESS it has a power PORT (which is global by
    # symbol name). Power-ISH nets without a port (e.g. VBUS) MUST still go global, else they
    # split into per-sheet local nets that share a name but aren't connected.
    def needs_glabel(net):
        return crossing(net) and net.rsplit("/", 1)[-1] not in power_ports

    outdir = outdir or os.path.join(ROOT, "build", "sch-hier", base)
    os.makedirs(outdir, exist_ok=True)
    for f in glob.glob(os.path.join(outdir, "*.kicad_sch")):
        os.remove(f)

    root_uuid = C.u()
    sheet_uuid = {ic: C.u() for ic in ic_blocks}
    used_of = lambda refs: {(parts[r][0], parts[r][1]): used[(parts[r][0], parts[r][1])] for r in refs}

    def sheet_nets(refs):
        rs = set(refs)
        out = {}
        for net, conns in nets.items():
            sub = [(r, p) for r, p in conns if r in rs]
            if sub:
                out[net] = sub
        return out

    # --- sub-sheets ------------------------------------------------------------------
    for i, ic in enumerate(ic_blocks):
        refs = blocks[ic]
        nS = sheet_nets(refs)
        gS = [net for net in nS if needs_glabel(net)]
        place, rot, pre_wires, handled, juncs, eterms = layout_block(
            ic, refs, parts, nS, used, power_ports, set(gS))
        build_sheet_file(os.path.join(outdir, f"block_{ic}.kicad_sch"), project,
                         {r: parts[r] for r in refs}, nS, used_of(refs), libs,
                         instance_path=f"{root_uuid}/{sheet_uuid[ic]}", file_uuid=C.u(),
                         placement=place, paper="A4", power_ports=power_ports, global_nets=gS,
                         rotations=rot, pre_wires=pre_wires, handled_pins=handled,
                         junctions=juncs, extra_terms=eterms,
                         title=f"{ic} — {parts[ic][2]}", rev=rev, date=date)

    # --- root ------------------------------------------------------------------------
    sheet_blocks = []
    cols = max(1, math.ceil(math.sqrt(len(ic_blocks))))
    for i, ic in enumerate(ic_blocks):
        sx, sy = 40 + (i % cols) * 64, 25 + (i // cols) * 52
        sheet_blocks.append(emit_sheet(ic, f"block_{ic}.kicad_sch", sx, sy, 52, 42,
                                       sheet_uuid[ic], project, root_uuid, str(i + 2)))
    rparts = blocks.get("ROOT", [])
    rc = max(1, math.ceil(math.sqrt(len(rparts))))
    base_y = 25 + (math.ceil(len(ic_blocks) / cols)) * 52 + 20
    rplace = {}
    for i, r in enumerate(sorted(rparts)):
        rplace[r] = C.gridsnap(45 + (i % rc) * 60, base_y + (i // rc) * 48)   # snap ONCE
    nR = sheet_nets(rparts)
    gR = set(net for net in nR if needs_glabel(net))
    pnR = {(r, p): net for net, conns in nR.items() for r, p in conns}
    # consolidate each root connector's repeated power pins (USB-C VBUS/GND etc.) -> bus + 1 term
    r_wires, r_handled, r_juncs, r_terms = [], set(), set(), []
    for r in rparts:
        pg = {p: C.pin_abs(rplace, used, {r: parts[r]}, r, p) for p in used[(parts[r][0], parts[r][1])]["pins"]}
        cw, ch, cj, ct = _consolidate_pins(r, pg, pnR, set(), power_ports, gR)
        r_wires += cw; r_handled |= ch; r_juncs |= cj; r_terms += ct
    root_path = os.path.join(outdir, root_name or f"{base}-hier.kicad_sch")
    build_sheet_file(root_path, project, {r: parts[r] for r in rparts}, nR, used_of(rparts), libs,
                     instance_path=root_uuid, file_uuid=root_uuid, placement=rplace, paper="A3",
                     power_ports=power_ports, powerflag_nets=["+5VSB", "GND"], global_nets=gR,
                     extra_blocks=sheet_blocks, title=f"{base} — root (interconnect)",
                     rev=rev, date=date, pre_wires=r_wires, handled_pins=r_handled,
                     junctions=r_juncs, extra_terms=r_terms)

    # auto-declutter: relocate overlapping value/reference text (free text only -> connectivity
    # is untouched). Label overlaps are left to the placement passes (can't move a label off its
    # wire). See cec_sch_overlap for the detector + the remaining-overlap report.
    try:
        import cec_sch_overlap as OV
        for f in glob.glob(os.path.join(outdir, "*.kicad_sch")):
            OV.fix_file(f)
    except Exception:
        pass
    return root_path, parts, nets


def _gm():
    spec = importlib.util.spec_from_file_location("gen_modules", os.path.join(ROOT, "scripts", "gen-modules.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def verify(root_path, parts, nets):
    out = os.path.join(tempfile.gettempdir(), "cec_hier_verify.net")
    if os.path.exists(out):
        os.remove(out)
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", out, root_path],
                   capture_output=True, text=True)
    txt = open(out).read() if os.path.exists(out) else ""
    # Each hier net as its OWN pin-set (do NOT union by leaf name -- that masks a SPLIT, where
    # two same-named local nets on different sheets look connected but aren't, e.g. VBUS).
    hier = []
    for m in re.finditer(r'\(net\s+\(code[^)]*\)\s*\(name\s+"([^"]+)"\)(.*?)(?=\(net\s|\Z)', txt, re.S):
        nodes = set(re.findall(r'\(node\s+\(ref\s+"([^"]+)"\)\s*\(pin\s+"([^"]+)"\)', m.group(2)))
        if nodes:
            hier.append((m.group(1), nodes))
    want = {}
    for net, conns in nets.items():
        want.setdefault(net.rsplit("/", 1)[-1], set()).update((r, p) for r, p in conns)
    miss = {}
    matched = 0
    for nm, pins in want.items():
        if any(pins <= hn for _, hn in hier):        # all pins live in ONE hier net
            matched += 1
        else:                                        # split across sheets, or genuinely missing
            pieces = [(hl, sorted(hn & pins)) for hl, hn in hier if hn & pins]
            miss[nm + (" SPLIT" if len(pieces) > 1 else "")] = pieces or sorted(pins)
    return {"flat_nets": len(want), "hier_nets": len(hier), "matched": matched,
            "n_missing_nets": len(miss), "missing": dict(list(miss.items())[:8])}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate a hierarchical (per-IC sub-sheet) schematic.")
    ap.add_argument("board", nargs="?", default="eps-8pin")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--rev", default=REV)
    ap.add_argument("--date", default=DATE)
    a = ap.parse_args(argv)
    if a.board in ("atx-24pin-rev3", "rev3", "24pin-rev3"):
        root_path, parts, nets = build_hier_rev3(rev=a.rev, date=a.date)
    else:
        root_path, parts, nets = build_hier(a.board, rev=a.rev, date=a.date)
    rep = verify(root_path, parts, nets)
    ok = rep["n_missing_nets"] == 0
    print(f"root: {os.path.relpath(root_path, ROOT)}")
    print(f"verify: flat_nets={rep['flat_nets']} hier_nets={rep['hier_nets']} "
          f"matched={rep['matched']}/{rep['flat_nets']} missing_nets={rep['n_missing_nets']}  "
          f"{'PASS' if ok else 'FAIL'}")
    for nm, pins in rep["missing"].items():
        print(f"  MISSING {nm}: {pins}")
    if not a.no_render:
        import cec_sch_review
        cec_sch_review.review(root_path, erc=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
