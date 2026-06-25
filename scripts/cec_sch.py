#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Shared schematic-emit helpers for the CEC generator scripts. The generators
# describe a board as PARTS (refdes -> lib/symbol/value) and NETS (name ->
# [(refdes, pin), ...]); this module turns that into a KiCad 10 .kicad_sch with:
#
#   - symbols embedded VERBATIM from the source libraries (only the top-level
#     symbol name is namespaced as lib:Name), so KiCad's ERC reports no
#     lib_symbol_mismatch;
#   - a short WIRE STUB off every connected pin, with the net label at the stub
#     end (away from the body) so labels never overlap pin names;
#   - a PWR_FLAG on each power net that is fed from a connector / off-board, so
#     ERC's "Input Power pin not driven" does not fire;
#   - a no-connect flag on every pin that is intentionally left unconnected.
#
# Pin geometry (position, angle, length) is read from the symbol so stubs extend
# in the correct outward direction. Hand-authored without kicad-cli; validate
# with `kicad-cli sch erc`.
import re, uuid, math

GRID = 1.27          # label/stub offset quantum
STUB = 3.81          # wire-stub length beyond the pin end (mm)

def f(x):
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s

def u():
    return str(uuid.uuid4())

def carve(text, start):
    """Return the balanced s-expr starting at index `start` (text[start]=='(')."""
    d = 0; instr = esc = False; j = start
    while j < len(text):
        c = text[j]
        if instr:
            if esc: esc = False
            elif c == '\\': esc = True
            elif c == '"': instr = False
        else:
            if c == '"': instr = True
            elif c == '(': d += 1
            elif c == ')':
                d -= 1
                if d == 0: return text[start:j+1]
        j += 1
    raise ValueError("unbalanced s-expr")

def symbol_block(libtext, name):
    i = libtext.find(f'(symbol "{name}"')
    if i < 0: raise SystemExit(f"symbol not found: {name}")
    return carve(libtext, i)

def pin_table(block):
    """num -> (x, y, angle, length) in symbol-local coordinates."""
    pins = {}
    for m in re.finditer(
        r'\(pin\s+[A-Za-z_]+\s+[A-Za-z_]+\s*\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\)\s*\(length\s+(-?[\d.]+)\)',
        block):
        seg = block[m.start():m.start()+260]
        num = re.search(r'\(number "([^"]+)"', seg)
        if num:
            pins[num.group(1)] = (float(m.group(1)), float(m.group(2)),
                                  int(m.group(3)), float(m.group(4)))
    return pins

def load_symbols(libs, parts):
    """parts: refdes -> (lib, name, value). Returns used[(lib,name)] = {block,pins}."""
    used = {}
    for lib, name, _ in parts.values():
        if (lib, name) not in used:
            blk = symbol_block(libs[lib], name)
            used[(lib, name)] = {"block": blk, "pins": pin_table(blk)}
    return used

def _namespace(block, name, lib):
    # rename only the top-level (symbol "Name" -> (symbol "lib:Name"); child
    # units (Name_0_1 etc.) keep their bare names, exactly as KiCad expects.
    return block.replace(f'(symbol "{name}"', f'(symbol "{lib}:{name}"', 1)

def reindent(block, base):
    """Re-tab a single multi-line s-expr so each line's indentation equals its
    true paren-nesting depth (+ base). KiCad re-serializes embedded symbols at a
    canonical depth; matching it avoids ERC's lib_symbol_mismatch warnings. Only
    leading whitespace is rewritten; string contents are untouched."""
    # tokenize into lines, tracking depth at the START of each line
    out = []
    depth = base
    # work char by char so we know depth precisely at each newline
    # first, strip existing leading whitespace per line, then re-add by depth
    raw_lines = block.split("\n")
    d = base
    instr = esc = False
    for li, line in enumerate(raw_lines):
        stripped = line.lstrip("\t ")
        # a line that starts with ')' closes one level before it is printed
        lead = d - (1 if stripped.startswith(")") else 0)
        out.append(("\t" * max(lead, 0)) + stripped if stripped else "")
        # now update depth by scanning this line's parens (ignoring strings)
        for c in line:
            if instr:
                if esc: esc = False
                elif c == "\\": esc = True
                elif c == '"': instr = False
            else:
                if c == '"': instr = True
                elif c == "(": d += 1
                elif c == ")": d -= 1
    return "\n".join(out)

def lib_symbols_section(used, extra_blocks=()):
    parts = ["\t(lib_symbols"]
    for (lib, name), s in used.items():
        parts.append(reindent(_namespace(s["block"], name, lib), 2))
    for blk in extra_blocks:
        parts.append(reindent(blk, 2))
    parts.append("\t)")
    return "\n".join(parts)

def pin_abs(placement, used, parts, ref, num):
    """Absolute (x,y) of a pin's CONNECTION point, and the outward unit vector.

    In KiCad a pin's connection point is its (at) coordinate; `length` extends
    from there toward the body along `ang`. So the attach point is just (at)
    placed (schematic Y is inverted vs symbol Y), and "outward" — where a stub
    extends, away from the body — is the opposite of `ang`.
    """
    lib, name, _ = parts[ref]
    lx, ly, ang, _length = used[(lib, name)]["pins"][num]
    ox, oy = placement[ref]
    ax, ay = ox + lx, oy - ly
    dx = -math.cos(math.radians(ang))      # outward = opposite the pin's body dir
    dy = math.sin(math.radians(ang))       # (+ because schematic Y is inverted)
    return ax, ay, dx, dy

def sym_body_box(block):
    """Local body bounding box (minx,maxx,miny,maxy) from rectangles only (the
    drawn outline), used as a keep-out for wire routing. Empty -> None."""
    xs, ys = [], []
    for m in re.finditer(r'\(rectangle\s*\(start\s+(-?[\d.]+)\s+(-?[\d.]+)\)\s*\(end\s+(-?[\d.]+)\s+(-?[\d.]+)\)', block):
        xs += [float(m.group(1)), float(m.group(3))]
        ys += [float(m.group(2)), float(m.group(4))]
    return (min(xs), max(xs), min(ys), max(ys)) if xs else None

def _seg_hits_box(x1, y1, x2, y2, box, pad=0.0):
    """True if axis-aligned segment (x1,y1)-(x2,y2) intersects rect box+pad."""
    bx0, bx1, by0, by1 = box[0]-pad, box[1]+pad, box[2]-pad, box[3]+pad
    if abs(y1-y2) < 1e-6:                       # horizontal
        if not (by0 <= y1 <= by1): return False
        lo, hi = sorted((x1, x2))
        return not (hi <= bx0 or lo >= bx1)
    if abs(x1-x2) < 1e-6:                       # vertical
        if not (bx0 <= x1 <= bx1): return False
        lo, hi = sorted((y1, y2))
        return not (hi <= by0 or lo >= by1)
    return False

def route_L(p, q, boxes, pin_pts):
    """Try the two axis-aligned L-routes between pin connection points p and q.
    Return a list of grid-snapped wire segments avoiding every keep-out box and
    not passing through any foreign pin point, or None if neither L is clean."""
    (x1, y1), (x2, y2) = p, q
    if abs(x1-x2) < 1e-6 or abs(y1-y2) < 1e-6:
        cand = [[(x1, y1, x2, y2)]]                     # already straight
    else:
        cand = [[(x1, y1, x2, y1), (x2, y1, x2, y2)],   # horizontal-first
                [(x1, y1, x1, y2), (x1, y2, x2, y2)]]   # vertical-first
    ends = {p, q}
    for segs in cand:
        ok = True
        for (sx1, sy1, sx2, sy2) in segs:
            if any(_seg_hits_box(sx1, sy1, sx2, sy2, b, pad=0.0) for b in boxes):
                ok = False; break
            # the corner/intermediate point must not land on a foreign pin
            for pt in ((sx1, sy1), (sx2, sy2)):
                if pt not in ends and pt in pin_pts:
                    ok = False; break
            if not ok: break
        if ok:
            return segs
    return None

_OHM = "Ω"   # Ω
_MULT = {"R": "", "k": "k", "K": "k", "m": "m", "M": "M"}

def fmt_cap(v):
    """Capacitance value -> standard nF/uF naming: 100n->100nF, 1u->1uF."""
    return v + "F" if re.match(r'^\d+(\.\d+)?[pnuµ]$', v) else v

def fmt_res(v):
    """Resistance value -> decimal + Ω (2.2kΩ-standard): 2k2->2.2kΩ, 10k->10kΩ,
    2m->2mΩ. Non-numeric placeholders (e.g. 'R_ID (OQ-6)') pass through."""
    m = re.match(r'^(\d+)([kKmMR])(\d+)$', v)      # RKM with internal letter
    if m:
        return f"{m.group(1)}.{m.group(3)}{_MULT[m.group(2)]}{_OHM}"
    m = re.match(r'^(\d+)([kKmMR])$', v)            # trailing multiplier
    if m:
        return f"{m.group(1)}{_MULT[m.group(2)]}{_OHM}"
    if re.match(r'^\d+$', v):                       # bare ohms
        return v + _OHM
    return v

def fmt_value(name, val):
    if name == "C_Small":
        return fmt_cap(val)
    if name == "R_Small":
        return fmt_res(val)
    return val

def emit_symbol(ref, lib, name, val, x, y, pins, project, root, fp="", props=None):
    val = fmt_value(name, val)
    props = props or {}
    pinblk = "\n".join(f'\t\t(pin "{n}" (uuid "{u()}"))' for n in pins)
    ds = props.get("Datasheet", "")
    # extra BOM properties (LCSC / MPN / Manufacturer / Description ...) preserved through regeneration
    extra = "".join(
        f'\t\t(property "{k}" "{v}" (at {f(x)} {f(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        for k, v in props.items() if k not in ("Datasheet", "Reference", "Value", "Footprint") and v)
    return (
        "\t(symbol\n"
        f'\t\t(lib_id "{lib}:{name}")\n'
        f"\t\t(at {f(x)} {f(y)} 0)\n\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n"
        "\t\t(fields_autoplaced yes)\n"
        f'\t\t(uuid "{u()}")\n'
        f'\t\t(property "Reference" "{ref}" (at {f(x)} {f(y-15.24)} 0) (effects (font (size 1.27 1.27))))\n'
        f'\t\t(property "Value" "{val}" (at {f(x)} {f(y+15.24)} 0) (effects (font (size 1.27 1.27))))\n'
        f'\t\t(property "Footprint" "{fp}" (at {f(x)} {f(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        f'\t\t(property "Datasheet" "{ds}" (at {f(x)} {f(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        f"{extra}"
        f"{pinblk}\n"
        f'\t\t(instances\n\t\t\t(project "{project}"\n\t\t\t\t(path "/{root}" (reference "{ref}") (unit 1))\n\t\t\t)\n\t\t)\n'
        "\t)")

def emit_wire(x1, y1, x2, y2):
    return (f"\t(wire (pts (xy {f(x1)} {f(y1)}) (xy {f(x2)} {f(y2)}))\n"
            f'\t\t(stroke (width 0) (type default)) (uuid "{u()}"))')

def emit_label(net, x, y, ang):
    just = "left" if ang in (0, 270) else "right"
    return (f'\t(label "{net}" (at {f(x)} {f(y)} {ang}) '
            f'(effects (font (size 1.27 1.27)) (justify {just} bottom)) (uuid "{u()}"))')

def emit_noconnect(x, y):
    return f'\t(no_connect (at {f(x)} {f(y)}) (uuid "{u()}"))'

def emit_global_power(symname, x, y, project, root, ref, rot=0):
    # instance of a power symbol (PWR_FLAG, GND, +3V3, +5VSB ...). Its single pin
    # sits at the symbol origin, so place the origin on the wire endpoint. The
    # instance block must match regular symbols: real project name + root-sheet
    # path + an annotated #PWR/#FLG reference. A bare "/" path or empty project
    # makes KiCad crash when it rebuilds instances on save.
    return (
        "\t(symbol\n"
        f'\t\t(lib_id "cec-power:{symname}")\n'
        f"\t\t(at {f(x)} {f(y)} {rot})\n\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n"
        f'\t\t(uuid "{u()}")\n'
        f'\t\t(property "Reference" "{ref}" (at {f(x)} {f(y-2.54)} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        f'\t\t(property "Value" "{symname}" (at {f(x)} {f(y+3.81)} 0) (effects (font (size 1.27 1.27))))\n'
        f'\t\t(pin "1" (uuid "{u()}"))\n'
        f'\t\t(instances\n\t\t\t(project "{project}"\n\t\t\t\t(path "/{root}" (reference "{ref}") (unit 1))\n\t\t\t)\n\t\t)\n'
        "\t)")

def gridsnap(x, y):
    return (round(x / GRID) * GRID, round(y / GRID) * GRID)

def emit_section(label, x0, y0, x1, y1):
    """A labelled functional-group box: a dashed rectangle + a bold title at its top-left.
    Pure annotation (graphic layer) -- no electrical effect, invisible to ERC/the netlist.
    Group component clusters inside these so the sheet reads by function."""
    return (
        f'\t(rectangle\n\t\t(start {f(x0)} {f(y0)})\n\t\t(end {f(x1)} {f(y1)})\n'
        f'\t\t(stroke (width 0.254) (type dash))\n\t\t(fill (type none))\n\t\t(uuid "{u()}")\n\t)\n'
        f'\t(text "{label}"\n\t\t(exclude_from_sim no)\n\t\t(at {f(x0 + 1.5)} {f(y0 + 1.5)} 0)\n'
        f'\t\t(effects (font (size 2 2) (thickness 0.35) (bold yes)) (justify left top))\n\t\t(uuid "{u()}")\n\t)'
    )

def build_schematic(out_path, project, parts, nets, used, libs,
                    paper="A3", powerflag_nets=(), nc_skip=(), placement=None,
                    power_ports=None, wire_nets=None, footprints=None, sections=None, props=None):
    """Write a .kicad_sch.

    power_ports: {net: power-symbol} (e.g. {"GND":"GND","+3V3":"+3V3"}). Pins on
      these nets get a power-port symbol at the stub end (GND points down,
      positive rails up) instead of a text label — far more readable, and the
      ports satisfy ERC so these nets need no PWR_FLAG.
    powerflag_nets: nets that still get a PWR_FLAG (use only for non-port nets).
    nc_skip: (ref,pin) left with neither net nor NC. placement: {refdes:(x,y)}
      functional layout; omitted parts auto-grid. All origins grid-snapped."""
    power_ports = power_ports or {}
    footprints = footprints or {}
    wire_nets = set(wire_nets or ())
    root = re.search(r'\(uuid\s+"?([0-9a-fA-F-]+)"?\s*\)', open(out_path).read()).group(1)

    # auto-grid sized to the largest symbol, generous gutter for stubs+labels
    def extent(p):
        xs = [v[0] for v in p.values()]; ys = [v[1] for v in p.values()]
        return ((max(xs)-min(xs)) if xs else 0, (max(ys)-min(ys)) if ys else 0)
    cw = (round((max((extent(s["pins"])[0] for s in used.values()), default=0) + 50.8) / GRID) * GRID)
    ch = (round((max((extent(s["pins"])[1] for s in used.values()), default=0) + 50.8) / GRID) * GRID)
    cols = 5
    auto = {r: (63.5 + (i % cols) * cw, 50.8 + (i // cols) * ch)
            for i, r in enumerate(parts)}
    placement = {r: gridsnap(*(placement or {}).get(r, auto[r])) for r in parts}

    # guard: a pin must not be in two nets
    seen = {}
    for net, conns in nets.items():
        for c in conns:
            if c in seen: raise SystemExit(f"pin {c} in two nets: {seen[c]} and {net}")
            seen[c] = net

    # power-symbol blocks embedded once each (ports + any PWR_FLAG)
    extra = []
    need_syms = set(power_ports.values())
    if powerflag_nets:
        need_syms.add("PWR_FLAG")
    for sym in sorted(need_syms):
        extra.append(_power_block(libs, sym))

    props = props or {}
    body = [emit_symbol(r, *parts[r][:2], parts[r][2], *placement[r],
                        used[(parts[r][0], parts[r][1])]["pins"], project, root,
                        footprints.get(r, ""), props.get(r))
            for r in parts]

    # keep-out body boxes (absolute) and the set of all pin connection points,
    # for the wire router.
    boxes, all_pins = [], set()
    for ref, (lib, name, _v) in parts.items():
        ox, oy = placement[ref]
        bb = sym_body_box(used[(lib, name)]["block"])
        if bb:
            boxes.append((ox+bb[0], ox+bb[1], oy-bb[3], oy-bb[2]))
        for pnum in used[(lib, name)]["pins"]:
            ax, ay, _dx, _dy = pin_abs(placement, used, parts, ref, pnum)
            all_pins.add((round(ax, 3), round(ay, 3)))

    wires, labels, flags = [], [], []
    flag_anchor = {}
    routed = set()           # nets drawn pin-to-pin (skip label/port emission)
    pwr_seq = [0]            # running counter for #PWR / #FLG references
    def pwr_ref(prefix):
        pwr_seq[0] += 1
        return f"{prefix}{pwr_seq[0]:02d}"

    # 1) direct point-to-point routing for opted-in 2-pin nets (fallback: labels)
    for net in list(wire_nets):
        conns = nets.get(net, [])
        if len(conns) != 2:
            continue
        (r1, p1), (r2, p2) = conns
        a = pin_abs(placement, used, parts, r1, p1)
        b = pin_abs(placement, used, parts, r2, p2)
        pa, pb = (round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3))
        segs = route_L(pa, pb, boxes, all_pins)
        if segs:
            for (x1, y1, x2, y2) in segs:
                wires.append(emit_wire(*gridsnap(x1, y1), *gridsnap(x2, y2)))
            routed.add(net)

    # 2) remaining nets: power ports or text labels on outward stubs
    for net, conns in nets.items():
        if net in routed:
            continue
        port = power_ports.get(net)
        for ref, pin in conns:
            ax, ay, dx, dy = pin_abs(placement, used, parts, ref, pin)
            bx, by = ax + dx * STUB, ay + dy * STUB
            wires.append(emit_wire(ax, ay, bx, by))
            if port:
                # power port at the stub end; GND points down (rot 0), positive
                # rails point up (rot 180) — its pin sits at the symbol origin.
                rot = 0 if port == "GND" else 180
                flags.append(emit_global_power(port, bx, by, project, root,
                                               pwr_ref("#PWR"), rot))
            else:
                lang = 0 if dx > 0 else (180 if dx < 0 else (270 if dy < 0 else 90))
                labels.append(emit_label(net, bx, by, lang))
            flag_anchor.setdefault(net, (bx, by, dx, dy))

    # PWR_FLAG drivers for connector-fed power nets. A net that enters only on
    # passive/power-input pins (e.g. +5VSB and GND off the RJ-45) has no driving
    # source, so ERC raises power_pin_not_driven. The fix is a standalone driver
    # "stamp" placed in free space below the content: a power-port (joins the
    # global net by name) and a PWR_FLAG (power_out, marks it driven) on a short
    # vertical wire. Top element points up, bottom points down, so the two tiny
    # graphics never overlap. Works whether or not the net is ported elsewhere.
    if powerflag_nets and placement:
        base_y = round((max(oy for _ox, oy in placement.values()) + 25.4) / GRID) * GRID
        base_x = round((min(ox for ox, _oy in placement.values())) / GRID) * GRID
        for i, net in enumerate(sorted(powerflag_nets)):
            sx = base_x + i * 25.4
            ty, by_ = base_y, base_y + 10.16
            wires.append(emit_wire(sx, ty, sx, by_))
            port = power_ports.get(net, net)
            if port == "GND":          # flag up top, GND port (points down) at bottom
                flags.append(emit_global_power("PWR_FLAG", sx, ty, project, root, pwr_ref("#FLG"), 180))
                flags.append(emit_global_power(port, sx, by_, project, root, pwr_ref("#PWR"), 0))
            elif net in power_ports:   # a defined power-rail SYMBOL: port up top, flag at bottom
                flags.append(emit_global_power(port, sx, ty, project, root, pwr_ref("#PWR"), 180))
                flags.append(emit_global_power("PWR_FLAG", sx, by_, project, root, pwr_ref("#FLG"), 0))
            else:                      # arbitrary labeled rail (no power symbol): text label + PWR_FLAG
                labels.append(emit_label(net, sx, ty, 90))
                flags.append(emit_global_power("PWR_FLAG", sx, by_, project, root, pwr_ref("#FLG"), 0))

    # no-connect flags on every pin not in a net and not skipped
    ncs = []
    for ref, (lib, name, _) in parts.items():
        for pin in used[(lib, name)]["pins"]:
            if (ref, pin) in seen or (ref, pin) in nc_skip:
                continue
            ax, ay, _dx, _dy = pin_abs(placement, used, parts, ref, pin)
            ncs.append(emit_noconnect(ax, ay))

    content = (
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
        f"\t(uuid \"{root}\")\n\t(paper \"{paper}\")\n"
        f"{lib_symbols_section(used, extra)}\n"
        + ("\n".join(emit_section(lbl, *box) for lbl, box in (sections or {}).items()) + "\n" if sections else "")
        + "\n".join(body) + "\n"
        + "\n".join(wires) + "\n"
        + "\n".join(labels) + "\n"
        + ("\n".join(flags) + "\n" if flags else "")
        + ("\n".join(ncs) + "\n" if ncs else "")
        + "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n")
    open(out_path, "w").write(content)
    return {"parts": len(parts), "nets": len(nets), "labels": len(labels),
            "wires": len(wires), "flags": len(flags), "nc": len(ncs),
            "routed": len(routed), "root": root}

_POWER_CACHE = {}
def _power_block(libs, name):
    if name not in _POWER_CACHE:
        pw = libs.get("power")
        if pw is None:
            raise SystemExit("power library not loaded")
        _POWER_CACHE[name] = _namespace(symbol_block(pw, name), name, "cec-power")
    return _POWER_CACHE[name]
