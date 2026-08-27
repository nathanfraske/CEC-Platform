#!/usr/bin/env python3
"""Migrate an existing routed candidate to an approved six-layer profile.

The transform deliberately changes only board setup, the old In2 power zones,
the new In4 ground plane, and the shared mezzanine seats. Existing tracks stay
on their physical layer IDs, so old In2 signal routing remains signal routing.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pcbnew

import cec_constraints
import cec_fab_profile as fab
import cec_mezz_contract as mezz


def _balanced_span(text, marker, start=0):
    pos = text.find(marker, start)
    if pos < 0:
        raise ValueError("missing %s section" % marker)
    depth = 0
    quoted = False
    escaped = False
    for idx in range(pos, len(text)):
        ch = text[idx]
        if quoted:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                quoted = False
            continue
        if ch == '"':
            quoted = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return pos, idx + 1
    raise ValueError("unterminated %s section" % marker)


def _replace_block(text, marker, replacement):
    start, end = _balanced_span(text, marker)
    return text[:start] + replacement + text[end:]


def _replace_footprint_at(text, ref, x_mm, y_mm, rotation):
    pos = 0
    while True:
        try:
            start, end = _balanced_span(text, "(footprint", pos)
        except ValueError:
            break
        block = text[start:end]
        if re.search(r'\(property\s+"Reference"\s+"%s"' % re.escape(ref), block):
            at = re.compile(
                r'(\n[ \t]*)\(at\s+[-+0-9.eE]+\s+[-+0-9.eE]+'
                r'(?:\s+[-+0-9.eE]+)?\)')
            if not at.search(block):
                raise ValueError("%s footprint has no placement" % ref)
            repl = r'\1(at %.6g %.6g %.6g)' % (x_mm, y_mm, rotation)
            block = at.sub(repl, block, count=1)
            return text[:start] + block + text[end:]
        pos = end
    raise ValueError("missing footprint %s" % ref)


def _migrate_old_power_zones(text):
    """Move old In2 fills to In3, except the obsolete In2 GND fill."""
    out = []
    pos = 0
    while True:
        found = text.find("(zone", pos)
        if found < 0:
            out.append(text[pos:])
            break
        out.append(text[pos:found])
        start, end = _balanced_span(text, "(zone", found)
        block = text[start:end]
        if '(layer "In2.Cu")' in block:
            net = re.search(r'\(net\s+"([^"]+)"\)', block)
            if net and net.group(1).upper().rsplit("/", 1)[-1] == "GND":
                pos = end
                continue
            block = block.replace('"In2.Cu"', '"In3.Cu"')
        out.append(block)
        pos = end
    return "".join(out)


def _gnd_plane_text(board):
    if board.FindNet("GND") is None:
        raise ValueError("cannot create In4 ground plane: board has no GND net")
    bb = board.GetBoardEdgesBoundingBox()
    x0 = pcbnew.ToMM(bb.GetLeft()) + 0.25
    y0 = pcbnew.ToMM(bb.GetTop()) + 0.25
    x1 = pcbnew.ToMM(bb.GetRight()) - 0.25
    y1 = pcbnew.ToMM(bb.GetBottom()) - 0.25
    if x1 <= x0 or y1 <= y0:
        raise ValueError("invalid board outline for In4 ground plane")
    return (
        '\t(zone\n\t\t(net "GND")\n\t\t(layer "In4.Cu")\n'
        '\t\t(uuid "%s")\n\t\t(name "GND2 Plane")\n'
        '\t\t(hatch edge 0.5)\n\t\t(connect_pads yes (clearance 0.3))\n'
        '\t\t(min_thickness 0.25)\n'
        '\t\t(fill yes (thermal_gap 0.3) (thermal_bridge_width 0.5) '
        '(island_removal_mode 0))\n'
        '\t\t(polygon (pts (xy %.6g %.6g) (xy %.6g %.6g) '
        '(xy %.6g %.6g) (xy %.6g %.6g)))\n\t)'
        % (uuid.uuid4(), x0, y0, x1, y0, x1, y1, x0, y1))


def _set_properties(text, profile_name):
    for key, value in fab.board_properties(profile_name).items():
        pat = re.compile(r'\(property\s+"%s"\s+"[^"]*"\)' % re.escape(key))
        row = '\t(property "%s" "%s")' % (key, value)
        if pat.search(text):
            text = pat.sub(row.strip(), text, count=1)
        else:
            marker = "\n\t(embedded_fonts no)"
            position = text.rfind(marker)
            if position < 0:
                raise ValueError("board has no top-level embedded_fonts marker")
            # Generated footprints may themselves use one-tab indentation and
            # contain ``embedded_fonts``. The board-level marker is the last
            # one before the root close; first-match insertion silently puts
            # fabrication authority inside a footprint on those files.
            text = text[:position] + "\n" + row + text[position:]
    return text


def _set_pofv_defaults(text):
    for name in ("capping", "filling"):
        pat = re.compile(r'\(%s\s+(?:yes|no)\)' % name)
        if pat.search(text):
            text = pat.sub("(%s yes)" % name, text, count=1)
        else:
            marker = "\n\t\t(allow_soldermask_bridges_in_footprints no)"
            if marker not in text:
                raise ValueError("board setup lacks solder-mask defaults")
            text = text.replace(marker, marker + "\n\t\t(%s yes)" % name, 1)
    return text


def declare_profile(path, profile_name, *, write=True):
    """Persist an already-realized fabrication contract without moving copper.

    Derived and archived boards may preserve the exact approved six-layer
    stackup while losing the four top-level CEC properties that authorize POFV.
    Inferring that authority from a filename would be unsafe.  This operation
    therefore requires an explicit profile, inserts metadata only, and then
    runs the complete physical stackup/profile validator before replacing the
    input.  A four-layer or otherwise mismatched board is refused unchanged.
    """
    path = os.path.abspath(path)
    fab.get_profile(profile_name)
    board = pcbnew.LoadBoard(path)
    if board is None:
        raise ValueError("KiCad could not load %s" % path)
    declared = fab.board_profile_name(board)
    if declared and declared != profile_name:
        raise ValueError(
            "board declares %r, refusing explicit profile %r" %
            (declared, profile_name))
    with open(path, encoding="utf-8") as handle:
        original = handle.read()
    updated = _set_properties(original, profile_name)
    changed = updated != original

    fd, tmp = tempfile.mkstemp(prefix="cec_profile_", suffix=".kicad_pcb",
                               dir=os.path.dirname(path))
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)
        declared_board = pcbnew.LoadBoard(tmp)
        errors = cec_constraints._fab_profile_errors(
            declared_board, tmp, profile_name)
        if errors:
            raise ValueError(
                "profile declaration refused: " + "; ".join(errors))
        if write and changed:
            os.replace(tmp, path)
            tmp = None
        return {
            "path": path,
            "profile": profile_name,
            "vendor_stackup": fab.get_profile(profile_name)["vendor_stackup"],
            "changed": changed,
            "written": bool(write and changed),
            "geometry_changed": False,
        }
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def migrate_board(path, *, board_hint=None, profile_name=None, write=True):
    path = os.path.abspath(path)
    hint = board_hint or path
    profile_name = profile_name or fab.profile_for_board_hint(hint)
    if not profile_name:
        raise ValueError("no approved six-layer profile for %s" % hint)
    board = pcbnew.LoadBoard(path)
    if board is None:
        raise ValueError("KiCad could not load %s" % path)
    ok, why = cec_constraints._chk_through_vias_only(board, path, {})
    if ok is False:
        raise ValueError("cannot migrate non-through vias: %s" % why)

    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    text = _replace_block(text, "(layers", fab.layers_text(profile_name))
    text = _replace_block(text, "(stackup", fab.stackup_text(profile_name))
    text = _set_pofv_defaults(text)
    text = _set_properties(text, profile_name)
    text = _migrate_old_power_zones(text)

    x0, y0, x1, y1 = cec_constraints._edge_bbox(board)
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    if any(token in str(hint).replace("\\", "/").lower()
           for token in ("hub-standard-rev2", "atx-24pin-rev3")):
        for segment in mezz.SEGMENTS:
            dx, dy = segment["dc"]
            text = _replace_footprint_at(
                text, segment["ref"], cx + dx, cy + dy, segment["rot"])
        dx, dy = mezz.GROUND_LUG["dc"]
        text = _replace_footprint_at(text, mezz.GROUND_LUG["ref"],
                                     cx + dx, cy + dy, 0.0)

    if '(layer "In4.Cu")' not in "".join(
            _balanced_zone for _balanced_zone in re.findall(
                r'\(zone[\s\S]*?\n\t\)', text)):
        marker = "\n\t(embedded_fonts no)"
        position = text.rfind(marker)
        if position < 0:
            raise ValueError("board has no top-level embedded_fonts marker")
        text = (text[:position] + "\n" + _gnd_plane_text(board)
                + text[position:])

    fd, tmp = tempfile.mkstemp(prefix="cec_6l_", suffix=".kicad_pcb",
                               dir=os.path.dirname(path))
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        migrated = pcbnew.LoadBoard(tmp)
        errors = cec_constraints._fab_profile_errors(migrated, tmp, profile_name)
        if errors:
            raise ValueError("profile validation failed: " + "; ".join(errors))
        if any(token in str(hint).replace("\\", "/").lower()
               for token in ("hub-standard-rev2", "atx-24pin-rev3")):
            mate_ok, mate_detail = cec_constraints._chk_mezzanine_segment_contract(
                migrated, tmp, {})
            if not mate_ok:
                raise ValueError("mezzanine validation failed: %s" % mate_detail)
        if write:
            os.replace(tmp, path)
            tmp = None
        return {"path": path, "profile": profile_name,
                "vendor_stackup": fab.get_profile(profile_name)["vendor_stackup"],
                "written": bool(write)}
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("boards", nargs="+")
    parser.add_argument("--check", action="store_true",
                        help="validate the migration without replacing the input")
    args = parser.parse_args(argv)
    for path in args.boards:
        print(migrate_board(path, write=not args.check))


if __name__ == "__main__":
    main()
