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
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOTDIR = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOTDIR, "scripts"))
import cec_sch  # noqa: E402


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


def build_leaf(parts, nets, footprints, props, placement, nc_skip,
               power_ports, powerflag_nets, hier_exports, sections,
               libs, project, path_prefix, sheet_instances_path, own_uuid,
               page, out_path, paper="A2", title=None, comment1=""):
    """Write one leaf schematic (a functional block with real components).

    `path_prefix` is the FULL chain of sheet-symbol uuids (starting with the
    project ROOT_UUID) leading down to this file, used for every component's
    `instances.path`. `sheet_instances_path` is that same chain WITHOUT the
    leading root uuid, used for this file's own `sheet_instances` footer.
    Both are plain strings already joined with "/" by the caller -- this
    function does not know or care how deep the hierarchy is.
    """
    placement = {r: cec_sch.gridsnap(*xy) for r, xy in placement.items()}
    used = cec_sch.load_symbols(libs, parts)

    body = [cec_sch.emit_symbol(r, *parts[r][:2], parts[r][2], *placement[r],
                                 used[(parts[r][0], parts[r][1])]["pins"],
                                 project, path_prefix,
                                 footprints.get(r, ""), props.get(r))
            for r in parts]

    # guard: a pin must not be in two nets
    seen = {}
    for net_name, conns in nets.items():
        for c in conns:
            if c in seen:
                raise SystemExit(f"pin {c} in two nets: {seen[c]} and {net_name}")
            seen[c] = net_name

    extra = []
    need_syms = set(power_ports.values())
    if powerflag_nets:
        need_syms.add("PWR_FLAG")
    for sym in sorted(need_syms):
        extra.append(cec_sch._power_block(libs, sym))

    wires, labels, flags, hlabels = [], [], [], []
    pwr_seq = [0]

    def pwr_ref(prefix):
        pwr_seq[0] += 1
        return f"{prefix}{pwr_seq[0]:02d}"

    for net_name, conns in nets.items():
        port = power_ports.get(net_name)
        hx = hier_exports.get(net_name)
        hier_anchor = hx[1] if hx else None
        for ref, pin in conns:
            ax, ay, dx, dy = cec_sch.pin_abs(placement, used, parts, ref, pin)
            bx, by = ax + dx * cec_sch.STUB, ay + dy * cec_sch.STUB
            wires.append(cec_sch.emit_wire(ax, ay, bx, by))
            lang = 0 if dx > 0 else (180 if dx < 0 else (270 if dy < 0 else 90))
            if hier_anchor is not None and (ref, pin) == hier_anchor:
                hlabels.append(_hier_label(net_name, hx[0], bx, by, lang))
            elif port:
                rot = 0 if port == "GND" else 180
                flags.append(cec_sch.emit_global_power(port, bx, by, project,
                                                        path_prefix, pwr_ref("#PWR"), rot))
            else:
                labels.append(cec_sch.emit_label(net_name, bx, by, lang))

    if powerflag_nets:
        base_y = round((max(oy for _ox, oy in placement.values()) + 25.4) / cec_sch.GRID) * cec_sch.GRID
        base_x = round((min(ox for ox, _oy in placement.values())) / cec_sch.GRID) * cec_sch.GRID
        for i, net_name in enumerate(sorted(powerflag_nets)):
            sx = base_x + i * 25.4
            ty, by_ = base_y, base_y + 10.16
            wires.append(cec_sch.emit_wire(sx, ty, sx, by_))
            port = power_ports.get(net_name, net_name)
            if port == "GND":
                flags.append(cec_sch.emit_global_power("PWR_FLAG", sx, ty, project, path_prefix, pwr_ref("#FLG"), 180))
                flags.append(cec_sch.emit_global_power(port, sx, by_, project, path_prefix, pwr_ref("#PWR"), 0))
            elif net_name in power_ports:
                flags.append(cec_sch.emit_global_power(port, sx, ty, project, path_prefix, pwr_ref("#PWR"), 180))
                flags.append(cec_sch.emit_global_power("PWR_FLAG", sx, by_, project, path_prefix, pwr_ref("#FLG"), 0))
            else:
                labels.append(cec_sch.emit_label(net_name, sx, ty, 90))
                flags.append(cec_sch.emit_global_power("PWR_FLAG", sx, by_, project, path_prefix, pwr_ref("#FLG"), 0))

    ncs = []
    for ref, (lib, name, _v) in parts.items():
        for pin in used[(lib, name)]["pins"]:
            if (ref, pin) in seen or (ref, pin) in nc_skip:
                continue
            ax, ay, _dx, _dy = cec_sch.pin_abs(placement, used, parts, ref, pin)
            ncs.append(cec_sch.emit_noconnect(ax, ay))

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
        + "\n".join(labels) + "\n"
        + ("\n".join(hlabels) + "\n" if hlabels else "")
        + ("\n".join(flags) + "\n" if flags else "")
        + ("\n".join(ncs) + "\n" if ncs else "")
        + f'\t(sheet_instances\n\t\t(path "/{sheet_instances_path}"\n\t\t\t(page "{page}")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
    open(out_path, "w").write(content)
    return {"parts": len(parts), "nets": len(nets), "labels": len(labels),
            "hlabels": len(hlabels), "wires": len(wires), "flags": len(flags),
            "nc": len(ncs)}


def _sheet_pin_block(name, shape, x, y, angle):
    return (f'\t\t(pin "{name}" {shape}\n'
            f'\t\t\t(at {cec_sch.f(x)} {cec_sch.f(y)} {angle})\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (justify left))\n'
            f'\t\t\t(uuid "{cec_sch.u()}")\n\t\t)')


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
        px, py = cec_sch.gridsnap(s01_x + s01_w, s01_y + 8 + i * 5.588)
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
                       own_uuid, out_path, title, paper="A3"):
    """
    leaves: ordered list of dicts, each:
        {id, sym_uuid, filename, sheetname, page, x, y, w, h,
         pins: [(net_name, shape), ...]}     # pins on this leaf's sheet box
    root_exports: set of net names that ALSO need a hierarchical_label in
        THIS file reaching further up (matching a pin on `own_sheet_sym_uuid`
        as it appears in the grandparent/root file). Shape is always
        "output", matching every pin already declared there (root's own
        HIER_EXPORTS convention, unchanged by this restructure).
    """
    sheets = []
    # net_name -> list of (x, y, angle) absolute pin-stub anchor points to
    # connect together via same-name labels within this file.
    net_points = {}

    # NOTE on sheet-pin angle: per this project's pin-geometry convention
    # (cec_sch.pin_abs: outward = -cos(angle) i.e. OPPOSITE the pin's declared
    # angle, since `angle` points FROM the connection point TOWARD the body),
    # a pin on a box's RIGHT edge has the body to its LEFT, so the angle must
    # be 180 (pointing left, into the box) for "outward" (where a wire
    # attaches) to correctly resolve to +x. root's own sheet-01 pins (in
    # build_root, unchanged) use angle 0 and are NEVER wired to anything at
    # that level (by design, sheets 02-09 are still placeholders) -- so that
    # latent mismatch has never been exercised. This file DOES wire real
    # copper to every leaf pin, so it must get the angle right.
    for leaf in leaves:
        pins_blocks = []
        n = len(leaf["pins"])
        for i, (net_name, shape) in enumerate(leaf["pins"]):
            px, py = cec_sch.gridsnap(leaf["x"] + leaf["w"], leaf["y"] + 8 + i * 5.588)
            pins_blocks.append(_sheet_pin_block(net_name, shape, px, py, 180))
            net_points.setdefault(net_name, []).append((px, py, 180))
        sheets.append(_sheet_block(leaf["sym_uuid"], leaf["x"], leaf["y"], leaf["w"], leaf["h"],
                                    leaf["sheetname"], leaf["filename"],
                                    project, root_uuid, leaf["page"], pins_blocks))

    # stub wires + labels off every leaf sheet-pin (same-name labels connect
    # within this one file, exactly like build_leaf's component-pin nets)
    wires, labels, hlabels = [], [], []
    for net_name, pts in net_points.items():
        for (px, py, _ang) in pts:
            ex = px + cec_sch.STUB
            wires.append(cec_sch.emit_wire(px, py, ex, py))
            labels.append(cec_sch.emit_label(net_name, ex, py, 0))

    # root-facing hierarchical labels: one per net that must reach the
    # grandparent, stacked in a column clear of the sheet boxes. Grid-aligned
    # (GRID=1.27mm) so kicad-cli doesn't flag endpoint_off_grid.
    max_x = max((leaf["x"] + leaf["w"] + 40) for leaf in leaves) if leaves else 40
    hx = round(max_x / cec_sch.GRID) * cec_sch.GRID
    hy0 = round(20 / cec_sch.GRID) * cec_sch.GRID
    hstep = round(7.62 / cec_sch.GRID) * cec_sch.GRID
    for i, net_name in enumerate(sorted(n for n in net_points if n in root_exports)):
        hy = hy0 + i * hstep
        wires.append(cec_sch.emit_wire(hx - cec_sch.STUB, hy, hx, hy))
        labels.append(cec_sch.emit_label(net_name, hx - cec_sch.STUB, hy, 0))
        hlabels.append(_hier_label(net_name, "output", hx, hy, 0))

    missing = sorted(root_exports - set(net_points))
    if missing:
        raise SystemExit(f"build_thin_parent: root_exports not produced by any leaf pin: {missing}")

    title_blk = _title_block(title,
                              "Thin parent sheet -- sheet-symbol fan-out/fan-in ONLY, no "
                              "components, per the owner's 2026-07-02 format correction",
                              "Leaf sheets: " + ", ".join(l["sheetname"] for l in leaves))

    content = (
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
        f"\t(uuid \"{own_uuid}\")\n\t(paper \"{paper}\")\n"
        f"{title_blk}\n"
        "\t(lib_symbols\n\t)\n"
        + "\n".join(sheets) + "\n"
        + "\n".join(wires) + "\n"
        + "\n".join(labels) + "\n"
        + ("\n".join(hlabels) + "\n" if hlabels else "")
        + f'\t(sheet_instances\n\t\t(path "/{own_sheet_sym_uuid}"\n\t\t\t(page "2")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
    open(out_path, "w").write(content)
    return {"leaves": len(leaves), "nets": len(net_points), "root_exports": len(root_exports)}
