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

def lib_symbols_section(used, extra_blocks=()):
    parts = ["\t(lib_symbols"]
    for (lib, name), s in used.items():
        parts.append("\t\t" + _namespace(s["block"], name, lib).replace("\n", "\n\t\t"))
    for blk in extra_blocks:
        parts.append("\t\t" + blk.replace("\n", "\n\t\t"))
    parts.append("\t)")
    return "\n".join(parts)

def pin_abs(placement, used, parts, ref, num):
    """absolute (x,y) of a pin's connection end, its angle, and outward unit vec."""
    lib, name, _ = parts[ref]
    lx, ly, ang, length = used[(lib, name)]["pins"][num]
    ox, oy = placement[ref]
    # symbol-local: pin root at (lx,ly); the wire end is `length` away along `ang`.
    ex = lx + length * math.cos(math.radians(ang))
    ey = ly + length * math.sin(math.radians(ang))
    # schematic Y is inverted relative to symbol Y
    ax, ay = ox + ex, oy - ey
    # outward direction (continuing past the pin end), Y inverted
    dx = math.cos(math.radians(ang))
    dy = -math.sin(math.radians(ang))
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

def emit_global_power(symname, x, y):
    # instance of a power symbol (e.g. PWR_FLAG); 0 deg, value carried by lib sym
    return (
        "\t(symbol\n"
        f'\t\t(lib_id "power:{symname}")\n'
        f"\t\t(at {f(x)} {f(y)} 0)\n\t\t(unit 1)\n"
        "\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n"
        f"\t\t(uuid {u()})\n"
        f'\t\t(property "Reference" "#FLG{x:.0f}{y:.0f}" (at {f(x)} {f(y-2.54)} 0) (effects (font (size 1.27 1.27)) (hide yes)))\n'
        f'\t\t(property "Value" "{symname}" (at {f(x)} {f(y+3.81)} 0) (effects (font (size 1.27 1.27))))\n'
        f'\t\t(pin "1" (uuid {u()}))\n'
        "\t)")

def build_schematic(out_path, project, parts, nets, used, libs,
                    paper="A3", powerflag_nets=(), nc_skip=()):
    """Write a .kicad_sch. powerflag_nets: nets that get a PWR_FLAG. nc_skip:
    set of (ref,pin) intentionally left with neither net nor NC (e.g. a button
    pad documented elsewhere)."""
    root = re.search(r'\(uuid\s+"?([0-9a-fA-F-]+)"?\s*\)', open(out_path).read()).group(1)

    # placement grid sized to the largest symbol, generous gutter for stubs+labels
    def extent(p):
        xs = [v[0] for v in p.values()]; ys = [v[1] for v in p.values()]
        return ((max(xs)-min(xs)) if xs else 0, (max(ys)-min(ys)) if ys else 0)
    cw = max((extent(s["pins"])[0] for s in used.values()), default=0) + 50.8
    ch = max((extent(s["pins"])[1] for s in used.values()), default=0) + 50.8
    cols = 5
    placement = {r: (63.5 + (i % cols) * cw, 50.8 + (i // cols) * ch)
                 for i, r in enumerate(parts)}

    # guard: a pin must not be in two nets
    seen = {}
    for net, conns in nets.items():
        for c in conns:
            if c in seen: raise SystemExit(f"pin {c} in two nets: {seen[c]} and {net}")
            seen[c] = net

    # PWR_FLAG symbol embedded once if used
    extra = []
    if powerflag_nets:
        extra.append(_pwrflag_block(libs))

    body = [emit_symbol(r, *parts[r][:2], parts[r][2], *placement[r],
                        used[(parts[r][0], parts[r][1])]["pins"], project, root)
            for r in parts]

    wires, labels = [], []
    # net labels on outward stubs
    flag_anchor = {}
    for net, conns in nets.items():
        for ref, pin in conns:
            ax, ay, dx, dy = pin_abs(placement, used, parts, ref, pin)
            bx, by = ax + dx * STUB, ay + dy * STUB
            wires.append(emit_wire(ax, ay, bx, by))
            lang = 0 if dx > 0 else (180 if dx < 0 else (270 if dy < 0 else 90))
            labels.append(emit_label(net, bx, by, lang))
            flag_anchor.setdefault(net, (bx, by, dx, dy))

    # PWR_FLAG instances: drop one on a stub end of each flagged net
    flags = []
    for net in powerflag_nets:
        if net in flag_anchor:
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

_PWRFLAG_CACHE = {}
def _pwrflag_block(libs):
    if "v" not in _PWRFLAG_CACHE:
        pw = libs.get("power")
        if pw is None:
            raise SystemExit("power library not loaded (need PWR_FLAG)")
        _PWRFLAG_CACHE["v"] = _namespace(symbol_block(pw, "PWR_FLAG"), "PWR_FLAG", "power")
    return _PWRFLAG_CACHE["v"]
