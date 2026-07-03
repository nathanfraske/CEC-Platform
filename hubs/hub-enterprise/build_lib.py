#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Hierarchical-schematic assembly helpers for the ENT hub capture. Reuses
# scripts/cec_sch.py's low-level primitives (symbol embedding, pin geometry,
# wire/label/power-port emission) but supplies its OWN top-level orchestration
# because cec_sch.build_schematic() assumes a flat, single-sheet project (its
# own file IS the project root). This project is a genuine THREE-level
# hierarchy for subsystem 01 (root -> 01-power-input [thin parent, sheet
# symbols only] -> 01a..01g leaf sheets [the actual components]), per the
# owner's 2026-07-02 format correction: "each functional block literally on
# its own sheet", not several dashed-frame sections crowded onto one sheet.
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
#     stable, but is kept fixed here for deterministic regeneration.
#   - `hierarchical_label`s inside a file correspond, by NAME, to `pin`s on
#     the `(sheet ...)` block that instantiates that file one level up. This
#     project's convention (established pre-restructure and preserved here)
#     is that every crossing uses shape "output" on both ends.
import os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOTDIR, "scripts"))
import cec_sch  # noqa: E402
import cec_sch_layout  # noqa: E402  -- the T1 layout engine (charter integration)

# Paper sizes (mm, landscape) for the content-centering pass.
PAPER = {"A4": (297.0, 210.0), "A3": (420.0, 297.0)}


def _hier_label(name, shape, x, y, angle):
    just = "left" if angle in (0, 270) else "right"
    return (f'\t(hierarchical_label "{name}"\n'
            f'\t\t(shape {shape})\n'
            f'\t\t(at {cec_sch.f(x)} {cec_sch.f(y)} {angle})\n'
            f'\t\t(effects (font (size 1.27 1.27)) (justify {just}))\n'
            f'\t\t(uuid "{cec_sch.u()}")\n\t)')


def _title_block(title, comment1="", comment2="", comment3="", rev="DRAFT"):
    lines = ['\t(title_block\n',
             f'\t\t(title "{title}")\n',
             '\t\t(date "2026-07-02")\n',
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
        # vertical 2-pin passive: fields beside the body
        side = 1 if text_side == "right" else -1
        fx = (xmax + G) if side > 0 else (xmin - G)
        just = "left" if side > 0 else "right"
        fields = [("Reference", ref, fx, y - 2 * G, just),
                  ("Value", val, fx, y + 2 * G, just)]
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


def build_leaf(parts, nets, footprints, props, placement, nc_skip,
               power_ports, powerflag_nets, hier_exports, sections,
               libs, project, path_prefix, sheet_instances_path, own_uuid,
               page, out_path, paper="A2", title=None, comment1="",
               pwr_base=0, layout=None):
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
    """
    placement = _norm_placement(placement)
    used = cec_sch.load_symbols(libs, parts)
    layout = layout or {}
    consumed = set(layout.get("consumed", ()))
    hier_at = dict(layout.get("hier_at", {}))
    text_side = dict(layout.get("text_side", {}))

    lay_wires = [list(w) for w in layout.get("wires", ())]
    lay_labels = [list(l) for l in layout.get("labels", ())]
    lay_power = [list(p) for p in layout.get("power", ())]

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
    if powerflag_nets:
        pf_y = max(p[1] for p in placement.values()) + 19.05
        pf_x = min(p[0] for p in placement.values())
        xs += [pf_x, pf_x + (len(powerflag_nets) - 1) * 25.4 + 5]
        ys += [pf_y, pf_y + 17]
    dx, dy = _center_shift((min(xs), max(xs), min(ys), max(ys)), paper)

    placement = {r: (x + dx, y + dy, rot) for r, (x, y, rot) in placement.items()}
    for w in lay_wires:
        w[0] += dx; w[2] += dx; w[1] += dy; w[3] += dy
    for l in lay_labels:
        l[1] += dx; l[2] += dy
    for p in lay_power:
        p[1] += dx; p[2] += dy
    hier_at = {n: (x + dx, y + dy, a) for n, (x, y, a) in hier_at.items()}
    junction_strs = []  # wire_decouplers-style pre-emitted junctions are NOT
    # translatable strings; leaves compose those rails via layout["rails"]
    # below instead, so nothing is lost by starting empty here.

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
        hlabels.append(_hier_label(net_name, shape, hx_, hy_, hang_))

    for rail in layout.get("decoupler_rails", ()):
        rw, rj, rp = cec_sch_layout.wire_decouplers(
            rail["_plan"], placement, used, parts, project, path_prefix,
            lambda prefix="#PWR": pwr_ref(prefix))
        wires += rw
        junction_strs += rj
        flags += rp

    for net_name, conns in nets.items():
        port = power_ports.get(net_name)
        hx = hier_exports.get(net_name)
        hier_anchor = hx[1] if hx and net_name not in hier_at else None
        for ref, pin in conns:
            if (ref, pin) in consumed:
                continue
            ax, ay, dx_, dy_ = cec_sch_layout.pin_abs_rot(placement, used, parts, ref, pin)
            bx, by = ax + dx_ * cec_sch.STUB, ay + dy_ * cec_sch.STUB
            wires.append(cec_sch.emit_wire(ax, ay, bx, by))
            lang = 0 if dx_ > 0 else (180 if dx_ < 0 else (270 if dy_ < 0 else 90))
            if hier_anchor is not None and (ref, pin) == hier_anchor:
                hlabels.append(_hier_label(net_name, hx[0], bx, by, lang))
            elif port:
                flags.append(_emit_power2(port, bx, by, _port_rot(port, dx_, dy_),
                                          project, path_prefix, pwr_ref("#PWR")))
            else:
                labels.append(cec_sch.emit_label(net_name, bx, by, lang))

    if powerflag_nets:
        base_y = round((max(p[1] for p in placement.values()) + 19.05) / cec_sch.GRID) * cec_sch.GRID
        base_x = round((min(p[0] for p in placement.values())) / cec_sch.GRID) * cec_sch.GRID
        for i, net_name in enumerate(sorted(powerflag_nets)):
            sx = base_x + i * 25.4
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
                labels.append(cec_sch.emit_label(net_name, sx, ty, 90))
                flags.append(_emit_power2("PWR_FLAG", sx, by_, 0, project, path_prefix, pwr_ref("#FLG")))

    ncs = []
    pin_pts = []
    for ref, (lib, name, _v) in parts.items():
        for pin in used[(lib, name)]["pins"]:
            ax, ay, _dx, _dy = cec_sch_layout.pin_abs_rot(placement, used, parts, ref, pin)
            pin_pts.append((ax, ay))
            if (ref, pin) in seen or (ref, pin) in nc_skip:
                continue
            ncs.append(cec_sch.emit_noconnect(ax, ay))

    junctions = _auto_junctions(wires, pin_pts, junction_strs)

    # NOTE: per the owner's 2026-07-02 format correction, leaf sheets carry NO
    # dashed-frame section graphics -- the sheet itself (one file, one proper
    # title) IS the grouping. `sections` is accepted for signature symmetry
    # with the pre-restructure generator but is expected empty/None here.
    section_gfx = "\n".join(cec_sch.emit_section(lbl, *box) for lbl, box in (sections or {}).items())

    title_blk = _title_block(title or out_path, comment1) if title else ""

    content = (
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
        f"\t(uuid \"{own_uuid}\")\n\t(paper \"{paper}\")\n"
        + (title_blk + "\n" if title_blk else "")
        + f"{cec_sch.lib_symbols_section(used, extra)}\n"
        + (section_gfx + "\n" if section_gfx else "")
        + "\n".join(body) + "\n"
        + "\n".join(wires) + "\n"
        + ("\n".join(junctions) + "\n" if junctions else "")
        + "\n".join(labels) + "\n"
        + ("\n".join(hlabels) + "\n" if hlabels else "")
        + ("\n".join(flags) + "\n" if flags else "")
        + ("\n".join(ncs) + "\n" if ncs else "")
        + f'\t(sheet_instances\n\t\t(path "/{sheet_instances_path}"\n\t\t\t(page "{page}")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
    open(out_path, "w").write(content)
    return {"parts": len(parts), "nets": len(nets), "labels": len(labels),
            "hlabels": len(hlabels), "wires": len(wires), "flags": len(flags),
            "junctions": len(junctions), "nc": len(ncs)}


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


def build_root(hier_exports, project, root_uuid, sheet01_sym_uuid,
               placeholder_uuids, placeholder_titles, out_path, paper="A3"):
    """Write hub-enterprise.kicad_sch (root): sheet instance for 01 (real,
    with hierarchical-label pins matching sheet01's exports) + placeholder
    sheet symbols for 02-09 (no pins -- nothing captured there yet).

    UNCHANGED by the 01a-01g leaf restructure: the root only ever sees ONE
    box named "01-power-input" exposing these 15 pins, regardless of whether
    that file is (as before) a flat capture sheet or (now) a thin parent that
    fans the same 15 signals out to seven leaf files of its own."""
    s01_x, s01_y, s01_w, s01_h = 20, 20, 70, 92
    names = list(hier_exports.keys())
    pin_blocks = []
    for i, name in enumerate(names):
        shape = hier_exports[name][0]
        # X must land EXACTLY on the box's right edge (s01_x + s01_w) -- do not
        # gridsnap it (verified empirically: a sheet pin whose X is off the
        # box edge by even a fraction of a mm, e.g. via naive gridsnapping,
        # silently fails to bind to the box's boundary in kicad-cli's
        # connectivity resolution -- it still LOOKS fine and ERC still runs,
        # but the pin never joins its net; see build_thin_parent below, where
        # this bug was actually exercised and root-caused, since these root
        # pins currently have nothing wired to them so it stays dormant here).
        px, py = s01_x + s01_w, cec_sch.gridsnap(0, s01_y + 8 + i * 5.588)[1]
        pin_blocks.append(_sheet_pin_block(name, shape, px, py, 0))
    sheets = [_sheet_block(sheet01_sym_uuid, s01_x, s01_y, s01_w, s01_h,
                            "01-power-input", "01-power-input.kicad_sch",
                            project, root_uuid, "2", pin_blocks)]

    # placeholder sheets: 2 columns x 4 rows, no pins
    grid_x = [140, 220]
    grid_y = [20, 65, 110, 155]
    page = 3
    for idx, num in enumerate(sorted(placeholder_uuids)):
        sx = grid_x[idx % 2]
        sy = grid_y[idx // 2]
        name, _desc = placeholder_titles[num]
        sheets.append(_sheet_block(placeholder_uuids[num], sx, sy, 70, 35,
                                    name, f"{name}.kicad_sch",
                                    project, root_uuid, str(page)))
        page += 1

    title_block = (
        '\t(title_block\n'
        '\t\t(title "CEC Hub -- Enterprise (ENT)")\n'
        '\t\t(date "2026-07-02")\n'
        '\t\t(rev "DRAFT")\n'
        '\t\t(company "CEC")\n'
        '\t\t(comment 1 "Hierarchical capture per hubs/hub-enterprise/SCHEMATIC-PLAN.md")\n'
        '\t\t(comment 2 "One schematic serves all ENT SKUs via the population/DNP matrix (REQ-105)")\n'
        '\t\t(comment 3 "DRAFT until every sheet passes the verification protocol -- see SCHEMATIC-PLAN.md sec 2")\n'
        '\t)'
    )
    legend = (
        '\t(text "Sheet map: 00=root 01=power-input(CAPTURED -- thin parent + 7 leaf sheets '
        '01a..01g, per functional block) 02=compute-core '
        '03=compute-rails 04=storage 05=module-ports 06=t1-dataplane 07=uplink '
        '08=secio-aux 09=watchdog(placeholders, capture pending) -- 10=voting-pair '
        '(MCX only, captured LAST per plan, not yet stubbed).\\n'
        'Population/DNP: per-SKU via BOM fields (fab DNP matrix), never schematic variants."\n'
        '\t\t(at 20 185 0)\n'
        '\t\t(effects (font (size 1.27 1.27)) (justify left top))\n'
        f'\t\t(uuid "{cec_sch.u()}")\n\t)'
    )

    content = (
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
        f"\t(uuid \"{root_uuid}\")\n\t(paper \"{paper}\")\n"
        f"{title_block}\n"
        "\t(lib_symbols\n\t)\n"
        + "\n".join(sheets) + "\n"
        + legend + "\n"
        + '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
    open(out_path, "w").write(content)


def build_placeholder(num, sheet_sym_uuid, name, desc, project, page, out_path, paper="A4"):
    """Write a minimal, valid, empty placeholder sheet (02-09): a title block
    + a 'capture pending' note, no components, no hierarchical labels yet.
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
        '\t\t(comment 1 "CAPTURE PENDING -- see hubs/hub-enterprise/SCHEMATIC-PLAN.md sheet map")\n'
        '\t)\n'
        "\t(lib_symbols\n\t)\n"
        f'\t(text "{name} -- CAPTURE PENDING\\n\\n{desc}\\n\\nSee SCHEMATIC-PLAN.md sec 1 for BOM src + population."\n'
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
# further up to the grandparent (here: the project root), one
# `hierarchical_label` per such net. No components, no dashed frames -- the
# owner's 2026-07-02 correction: "each functional block literally on its own
# sheet", so this file's only job is fan-out/fan-in of sheet pins.
# ---------------------------------------------------------------------------
def build_thin_parent(leaves, root_exports, project, root_uuid, own_sheet_sym_uuid,
                       own_uuid, out_path, title, paper="A3",
                       global_power_exports=None, libs=None, pwr_base=0,
                       gp_block_xy=None):
    """
    leaves: ordered list of dicts, each:
        {id, sym_uuid, filename, sheetname, page, x, y, w, h,
         pins: [(net_name, shape, side), ...]}   # side in {'right','left'}
    root_exports: set of net names that ALSO need a hierarchical_label in
        THIS file reaching further up (matching a pin on `own_sheet_sym_uuid`
        as it appears in the grandparent/root file). Shape is always
        "output", matching every pin already declared there (root's own
        HIER_EXPORTS convention, unchanged by this restructure).
    global_power_exports: {net_name: power_symbol_name} for root-exports that
        are REAL KiCad global power nets (GND/+3V3/+5VSB/+5V_MAIN/+5V_SYS --
        `(power global)` symbols, which connect project-wide by name alone,
        with NO hierarchical-label plumbing needed at all). Every leaf that
        uses one of these nets places its OWN ordinary global power symbol
        (unchanged, same as any other net in POWER_PORTS) -- so unlike the
        other root_exports, THESE have no leaf sheet-pin to anchor to here.
        The root-facing hierarchical_label instead gets its OWN local global
        power symbol stamped right next to it: that symbol is the SAME
        already-project-wide net (electrically identical to every leaf's
        copy), and its presence is what keeps the hierarchical_label from
        reading as label_dangling. Needs `libs` (for the "power" library).

    T1-integration layout (2026-07-03, the owner's "not ugly spread out"
    correction): a net shared by exactly TWO leaf boxes is now a REAL DRAWN
    WIRE between the two sheet pins (source on a right edge, destination on a
    left edge -- the eFuse->cascade flow), routed on a per-destination lane
    column with a deterministic no-crossing order; a net with ONE leaf pin
    gets its hierarchical label DIRECTLY at the pin stub (no label-alias
    pair). Everything is grid-aligned (box origins/sizes included, so the
    sheet-pin-must-sit-exactly-on-the-box-edge rule and the 1.27mm grid are
    satisfied SIMULTANEOUSLY -- the old off-grid-edge ERC/lint noise is gone
    by construction), then the whole composition is centered on the page.
    """
    global_power_exports = global_power_exports or {}
    G = cec_sch.GRID
    STUB = cec_sch.STUB

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
            tap = net_name in root_exports
            tapx = lane - 7.62
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
                    hier.append((net_name, tapx, sy + 5.08, 0))
                    hier_tapped.add(net_name)
                else:
                    wires.append((sx, sy, lane, sy))
                wires.append((lane, sy, lane, tyy))
                wires.append((lane, tyy, txx, tyy))

    # ---- global power exports: stamp + hier label rows, a tidy block
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
    hlabels = [_hier_label(n, "output", sx_(x), sy_(y), a) for (n, x, y, a) in hier]
    for net_name, px, py in gp_rows:
        # component-style instances path (full chain from the true root),
        # matching how every regular part inside a leaf sheet is addressed
        # -- NOT the single-hop convention that sheet_instances/sheet-pins
        # need (see the notes above/in this function's docstring).
        flags.append(_emit_power2(global_power_exports[net_name], sx_(px), sy_(py),
                                  180, project, f"{root_uuid}/{own_sheet_sym_uuid}",
                                  pwr_ref("#PWR")))
    junctions = _auto_junctions(wire_strs, [])
    wires, labels = wire_strs, label_strs

    extra_syms = []
    if global_power_exports:
        for sym in sorted(set(global_power_exports.values())):
            extra_syms.append(cec_sch._power_block(libs, sym))
    lib_symbols_section = ("\t(lib_symbols\n" + "\n".join(cec_sch.reindent(s, 2) for s in extra_syms) + "\n\t)\n") \
        if extra_syms else "\t(lib_symbols\n\t)\n"

    title_blk = _title_block(title,
                              "Thin parent sheet -- sheet-symbol fan-out/fan-in ONLY, no "
                              "components, per the owner's 2026-07-02 format correction",
                              "Leaf sheets: " + ", ".join(l["sheetname"] for l in leaves))

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
        + f'\t(sheet_instances\n\t\t(path "/{own_sheet_sym_uuid}"\n\t\t\t(page "2")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
    open(out_path, "w").write(content)
    return {"leaves": len(leaves), "nets": len(net_pins), "wired_nets": len(pairs),
            "root_exports": len(root_exports),
            "global_power": len(global_power_exports)}
