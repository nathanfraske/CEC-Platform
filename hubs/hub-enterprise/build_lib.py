#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
#
# Hierarchical-schematic assembly helpers for the ENT hub capture. Reuses
# scripts/cec_sch.py's low-level primitives (symbol embedding, pin geometry,
# wire/label/power-port emission) but supplies its OWN top-level orchestration
# because cec_sch.build_schematic() assumes a flat, single-sheet project (its
# own file IS the root, `instances` path = "/<its-own-uuid>", footer always
# `sheet_instances (path "/" (page "1"))`). A genuine two-level hierarchy needs:
#   - child-sheet symbol `instances` paths of "/<ROOT_UUID>/<SHEET_SYM_UUID>"
#     (NOT the child file's own identity uuid);
#   - `hierarchical_label` objects (not plain labels) at the sheet boundary;
#   - the child's OWN `sheet_instances` keyed by just "/<SHEET_SYM_UUID>"
#     (the root's own entry is the special-cased literal "/"; a first-level
#     child's sheet_instances path does not repeat the root uuid -- only the
#     symbol `instances` paths do).
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


def build_sheet01(parts, nets, footprints, props, placement, nc_skip,
                   power_ports, powerflag_nets, hier_exports, sections,
                   libs, project, root_uuid, sheet_sym_uuid, own_uuid,
                   page, out_path, paper="A2"):
    """Write 01-power-input.kicad_sch."""
    path_prefix = f"{root_uuid}/{sheet_sym_uuid}"
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

    section_gfx = "\n".join(cec_sch.emit_section(lbl, *box) for lbl, box in (sections or {}).items())

    content = (
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n\t(generator_version \"10.0\")\n"
        f"\t(uuid \"{own_uuid}\")\n\t(paper \"{paper}\")\n"
        f"{cec_sch.lib_symbols_section(used, extra)}\n"
        + (section_gfx + "\n" if section_gfx else "")
        + "\n".join(body) + "\n"
        + "\n".join(wires) + "\n"
        + "\n".join(labels) + "\n"
        + ("\n".join(hlabels) + "\n" if hlabels else "")
        + ("\n".join(flags) + "\n" if flags else "")
        + ("\n".join(ncs) + "\n" if ncs else "")
        + f'\t(sheet_instances\n\t\t(path "/{sheet_sym_uuid}"\n\t\t\t(page "{page}")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n')
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
    sheet symbols for 02-09 (no pins -- nothing captured there yet)."""
    # sheet-01 box: pins for all hier_exports along its right edge. NOTE: these
    # 15 pins are deliberately left with nothing wired to them at the root --
    # sheets 02-09 are placeholders (no pins of their own yet, per the plan),
    # so there is no consumer to wire them to. KiCad has no "intentionally
    # unconnected hierarchical pin" marker (a no_connect object attaches to a
    # component pin, not a sheet pin -- tried, it just adds a SEPARATE
    # no_connect_dangling warning on top of the original pin_not_connected).
    # This yields an EXPECTED, DOCUMENTED `pin_not_connected` finding per pin
    # (see scripts/check_hub_ent_sch.py / the final report) that clears
    # naturally as each consuming sheet is captured and wired.
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
        '\t(text "Sheet map: 00=root 01=power-input(CAPTURED) 02=compute-core '
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
