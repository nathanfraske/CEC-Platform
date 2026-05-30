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

def emit_symbol(ref, lib, name, val, x, y, pins, project, root):
    pinblk = "\n".join(f'\t\t(pin "{n}" (uuid {u()}))' for n in pins)
    return (
        "\t(symbol\n"
        f'\t\t(lib_id "{lib}:{name}")\n'
        f"\t\t(at {f(x)} {f(y)} 0)\n\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n"
        "\t\t(fields_autoplaced yes)\n"
        f"\t\t(uuid {u()})\n"
        f'\t\t(property "Reference" "{ref}" (at {f(x)} {f(y-15.24)} 0) (effects (font (size 1.27 1.27))))\n'
        f'\t\t(property "Value" "{val}" (at {f(x)} {f(y+15.24)} 0) (effects (font (size 1.27 1.27))))\n'
        f'\t\t(property "Footprint" "" (at {f(x)} {f(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        f'\t\t(property "Datasheet" "" (at {f(x)} {f(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        f"{pinblk}\n"
        f'\t\t(instances\n\t\t\t(project "{project}"\n\t\t\t\t(path "/{root}" (reference "{ref}") (unit 1))\n\t\t\t)\n\t\t)\n'
        "\t)")

def emit_wire(x1, y1, x2, y2):
    return (f"\t(wire (pts (xy {f(x1)} {f(y1)}) (xy {f(x2)} {f(y2)}))\n"
            f"\t\t(stroke (width 0) (type default)) (uuid {u()}))")

def emit_label(net, x, y, ang):
    just = "left" if ang in (0, 270) else "right"
    return (f'\t(label "{net}" (at {f(x)} {f(y)} {ang}) '
            f'(effects (font (size 1.27 1.27)) (justify {just} bottom)) (uuid {u()}))')

def emit_noconnect(x, y):
    return f"\t(no_connect (at {f(x)} {f(y)}) (uuid {u()}))"

def emit_global_power(symname, x, y, rot=0):
    # instance of a power symbol (PWR_FLAG, GND, +3V3, +5VSB ...). Its single pin
    # sits at the symbol origin, so place the origin on the wire endpoint.
    return (
        "\t(symbol\n"
        f'\t\t(lib_id "power:{symname}")\n'
        f"\t\t(at {f(x)} {f(y)} {rot})\n\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n"
        f"\t\t(uuid {u()})\n"
        f'\t\t(property "Reference" "#PWR{abs(hash((x,y,symname)))%100000}" (at {f(x)} {f(y-2.54)} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        f'\t\t(property "Value" "{symname}" (at {f(x)} {f(y+3.81)} 0) (effects (font (size 1.27 1.27))))\n'
        f'\t\t(pin "1" (uuid {u()}))\n'
        f'\t\t(instances\n\t\t\t(project "" (path "/" (reference "#PWR?") (unit 1)))\n\t\t)\n'
        "\t)")

def gridsnap(x, y):
    return (round(x / GRID) * GRID, round(y / GRID) * GRID)

def build_schematic(out_path, project, parts, nets, used, libs,
                    paper="A3", powerflag_nets=(), nc_skip=(), placement=None,
                    power_ports=None):
    """Write a .kicad_sch.

    power_ports: {net: power-symbol} (e.g. {"GND":"GND","+3V3":"+3V3"}). Pins on
      these nets get a power-port symbol at the stub end (GND points down,
      positive rails up) instead of a text label — far more readable, and the
      ports satisfy ERC so these nets need no PWR_FLAG.
    powerflag_nets: nets that still get a PWR_FLAG (use only for non-port nets).
    nc_skip: (ref,pin) left with neither net nor NC. placement: {refdes:(x,y)}
      functional layout; omitted parts auto-grid. All origins grid-snapped."""
    power_ports = power_ports or {}
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

    body = [emit_symbol(r, *parts[r][:2], parts[r][2], *placement[r],
                        used[(parts[r][0], parts[r][1])]["pins"], project, root)
            for r in parts]

    wires, labels, flags = [], [], []
    flag_anchor = {}
    for net, conns in nets.items():
        port = power_ports.get(net)
        for ref, pin in conns:
            ax, ay, dx, dy = pin_abs(placement, used, parts, ref, pin)
            bx, by = ax + dx * STUB, ay + dy * STUB
            wires.append(emit_wire(ax, ay, bx, by))
            if port:
                # power port at the stub end; GND points down (rot 0), positive
                # rails point up (rot 180) — its pin sits at the symbol origin.
                rot = 0 if port == "GND" else 180
                flags.append(emit_global_power(port, bx, by, rot))
            else:
                lang = 0 if dx > 0 else (180 if dx < 0 else (270 if dy < 0 else 90))
                labels.append(emit_label(net, bx, by, lang))
            flag_anchor.setdefault(net, (bx, by, dx, dy))

    # PWR_FLAG instances for any remaining (non-port) flagged nets
    for net in powerflag_nets:
        if net in flag_anchor and net not in power_ports:
            bx, by, dx, dy = flag_anchor[net]
            fx, fy = bx + dx * STUB, by + dy * STUB
            wires.append(emit_wire(bx, by, fx, fy))
            flags.append(emit_global_power("PWR_FLAG", fx, fy))

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
        f"\t(uuid {root})\n\t(paper \"{paper}\")\n"
        f"{lib_symbols_section(used, extra)}\n"
        + "\n".join(body) + "\n"
        + "\n".join(wires) + "\n"
        + "\n".join(labels) + "\n"
        + ("\n".join(flags) + "\n" if flags else "")
        + ("\n".join(ncs) + "\n" if ncs else "")
        + "\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n")
    open(out_path, "w").write(content)
    return {"parts": len(parts), "nets": len(nets), "labels": len(labels),
            "wires": len(wires), "flags": len(flags), "nc": len(ncs), "root": root}

_POWER_CACHE = {}
def _power_block(libs, name):
    if name not in _POWER_CACHE:
        pw = libs.get("power")
        if pw is None:
            raise SystemExit("power library not loaded")
        _POWER_CACHE[name] = _namespace(symbol_block(pw, name), name, "power")
    return _POWER_CACHE[name]
