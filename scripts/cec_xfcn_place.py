#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize and place the XFCN contract on the current Standard Beta PCBs.

Only the explicitly contracted interface footprints are replaced.  Copper is
preserved except for tracks/vias that terminate inside a retired interface
footprint's local body/pad envelope; this removes obsolete blade fan-out stubs
without ripping an entire high-current rail elsewhere on the board.  Pipeline-
owned SENSEC zones are replaced from the final terminal/shunt geometry; stale
pre-interface slabs are never retained or accumulated.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew

import cec_swig_guard as _swig_guard
import cec_pcb_reconcile
import cec_sch_gates
import cec_constraints
import cec_fr
import cec_xfcn_contract as contract


# Keep KiCad's Python wrapper registry alive across zone fill and board
# round-trips. Without this pin, a successful fill can invalidate unrelated
# BOX2I proxies and crash the integration before its atomic save.
_swig_guard.pin()


ROOT = contract.ROOT
FP_LIBRARY = ROOT / "lib/vendor/Connector_Screw.pretty"


def _mm(value):
    return value / 1e6


def _cleanup_temporary_board(path):
    """Remove a temporary board and KiCad's implicit companion project file."""
    board_path = Path(path)
    for candidate in (board_path, board_path.with_suffix(".kicad_pro")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _enforce_contract_stackup(path, plan):
    """Persist an explicitly contracted copper stack after pcbnew serialization.

    KiCad's SWIG board API does not expose a stable stackup mutator across the
    supported versions, while SaveBoard preserves the existing s-expression.
    Replace only the four named copper thickness scalars and record the profile
    as a board property.  Every replacement is cardinality-checked so a format
    change fails closed instead of producing a partly modified stackup.
    """
    spec = plan.get("stackup")
    if not spec:
        return
    board_path = Path(path)
    text = board_path.read_text(encoding="utf-8")
    for layer, thickness_mm in spec["copper_mm"].items():
        pattern = (
            r'(\(layer\s+"' + re.escape(layer) +
            r'"\s+\(type\s+"copper"\)\s+\(thickness\s+)([0-9.]+)(\))')
        text, count = re.subn(
            pattern, lambda match: match.group(1) + f"{thickness_mm:.3f}" + match.group(3),
            text, count=1, flags=re.DOTALL)
        if count != 1:
            raise SystemExit(
                f"REFUSE stackup enforcement: expected one {layer} thickness, found {count}")
    key = "CEC_XFCN_STACKUP"
    value = spec["profile"]
    property_pattern = r'\(property\s+"' + key + r'"\s+"[^"]*"\)'
    replacement = f'(property "{key}" "{value}")'
    if re.search(property_pattern, text):
        text, count = re.subn(property_pattern, replacement, text, count=1)
        if count != 1:
            raise SystemExit("REFUSE stackup property replacement cardinality")
    else:
        text, count = re.subn(
            r'(?=\n\t\(footprint\s)', "\n\t" + replacement,
            text, count=1)
        if count != 1:
            raise SystemExit("REFUSE stackup property insertion point missing")
    board_path.write_text(text, encoding="utf-8")


def _enforce_contract_contact_interface(path, plan):
    """Persist machine-readable daughterboard contact-system metadata."""
    spec = plan.get("contact_interface")
    if not spec:
        return
    board_path = Path(path)
    text = board_path.read_text(encoding="utf-8")
    finish_pattern = r'\(copper_finish\s+"[^"]*"\)'
    finish_replacement = f'(copper_finish "{spec["copper_finish"]}")'
    text, count = re.subn(
        finish_pattern, finish_replacement, text, count=1)
    if count != 1:
        raise SystemExit("REFUSE contact-interface copper_finish cardinality")

    properties = {
        "CEC_XFCN_CONTACT_INTERFACE": spec["profile"],
        "CEC_XFCN_CONTACT_INTERPOSER": spec["interposer"],
        "CEC_XFCN_COPPER_COIN": spec["copper_coin"],
    }
    for key, value in properties.items():
        pattern = r'\(property\s+"' + re.escape(key) + r'"\s+"[^"]*"\)'
        replacement = f'(property "{key}" "{value}")'
        if re.search(pattern, text):
            text, count = re.subn(pattern, replacement, text, count=1)
            if count != 1:
                raise SystemExit(
                    f"REFUSE contact property replacement cardinality: {key}")
        else:
            text, count = re.subn(
                r'(?=\n\t\(footprint\s)', "\n\t" + replacement,
                text, count=1)
            if count != 1:
                raise SystemExit(
                    f"REFUSE contact property insertion point missing: {key}")
    board_path.write_text(text, encoding="utf-8")


def _cleanup_orphan_temporary_projects(directory):
    """Bounded cleanup for project files leaked by older temporary saves."""
    directory = Path(directory).resolve()
    removed = 0
    for candidate in directory.glob("tmp*.kicad_pro"):
        if candidate.resolve().parent != directory:
            continue
        if candidate.with_suffix(".kicad_pcb").exists():
            continue
        candidate.unlink()
        removed += 1
    return removed


def _strip_managed_zone_blocks(path, managed_nets):
    """Atomically remove selected top-level KiCad zone expressions.

    KiCad 10's Python wrapper can tear down its global type registry when a
    ZONE child is removed from a mutation-heavy board, turning every later
    BOARD/BOX2I result into a raw ``SwigPyObject``.  Source-board cleanup is a
    simple ownership operation, so perform it on the serialized s-expression
    after the normal board save.  The balanced scanner understands quoted
    strings and escapes and removes only zones whose explicit ``net_name`` is
    in the caller's closed set.
    """
    path = Path(path)
    targets = {str(net) for net in managed_nets if str(net)}
    if not targets:
        return 0
    text = path.read_text(encoding="utf-8")
    starts = [match.start() for match in re.finditer(
        r"(?m)^[ \t]*\(zone\b", text)]
    spans = []
    for start in starts:
        depth = 0
        quoted = escaped = False
        end = None
        for index in range(start, len(text)):
            char = text[index]
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
                continue
            if char == '"':
                quoted = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:
            raise SystemExit("REFUSE managed-zone cleanup: unterminated zone")
        block = text[start:end]
        names = re.findall(
            r'\((?:net_name|net)\s+"((?:\\.|[^"\\])*)"\)', block)
        if len(names) > 1:
            raise SystemExit(
                "REFUSE managed-zone cleanup: zone has multiple net_name fields")
        # Keep net-code-zero rule/keepout zones, which legitimately have no
        # net_name. Only an explicitly named target can be removed.
        if names and names[0] in targets:
            # Include the following newline so repeated runs are byte-stable.
            if end < len(text) and text[end] == "\n":
                end += 1
            spans.append((start, end))
    if not spans:
        return 0
    for start, end in reversed(spans):
        text = text[:start] + text[end:]
    fd, temporary = tempfile.mkstemp(suffix=".kicad_pcb", dir=path.parent)
    os.close(fd)
    try:
        Path(temporary).write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        _cleanup_temporary_board(temporary)
    return len(spans)


def _box_mm(item, inflate=0.0):
    box = item.GetBoundingBox(False, False)
    return (
        _mm(box.GetX()) - inflate,
        _mm(box.GetY()) - inflate,
        _mm(box.GetX() + box.GetWidth()) + inflate,
        _mm(box.GetY() + box.GetHeight()) + inflate,
    )


def _point_in_box(point, box):
    x, y = _mm(point.x), _mm(point.y)
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def _segment_intersects_box(start, end, box):
    """Liang-Barsky segment/rectangle intersection in millimetres."""
    x0, y0, x1, y1 = _mm(start.x), _mm(start.y), _mm(end.x), _mm(end.y)
    dx, dy = x1 - x0, y1 - y0
    p = (-dx, dx, -dy, dy)
    q = (x0 - box[0], box[2] - x0, y0 - box[1], box[3] - y0)
    low, high = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-12:
            if qi < 0:
                return False
            continue
        ratio = qi / pi
        if pi < 0:
            low = max(low, ratio)
        else:
            high = min(high, ratio)
        if low > high:
            return False
    return True


def _boxes_overlap(a, b, clearance=0.20):
    return not (
        a[2] + clearance <= b[0] or b[2] + clearance <= a[0] or
        a[3] + clearance <= b[1] or b[3] + clearance <= a[1])


def _overlap_penetration(a, b):
    return min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])


def _edge_box(board):
    box = board.GetBoardEdgesBoundingBox()
    if box.GetWidth() <= 0 or box.GetHeight() <= 0:
        return None
    return (
        _mm(box.GetX()), _mm(box.GetY()),
        _mm(box.GetX() + box.GetWidth()), _mm(box.GetY() + box.GetHeight()),
    )


def _target_edge_box(plan, fallback):
    """KiCad Edge.Cuts bbox for an optional rectangular finished-board datum."""
    rect = plan.get("outline_rect_mm")
    if rect is None:
        return fallback
    x0, y0, x1, y1 = map(float, rect)
    # The generated Edge.Cuts segments use a 0.10 mm stroke.
    return (x0 - 0.05, y0 - 0.05, x1 + 0.05, y1 + 0.05)


def _set_rect_outline(board, rect):
    """Replace a rectangular Edge.Cuts authority with a contracted rectangle."""
    existing = [item for item in board.GetDrawings()
                if item.GetLayer() == pcbnew.Edge_Cuts]
    if len(existing) != 4 or any(
            not isinstance(item, pcbnew.PCB_SHAPE) or
            item.GetShape() != pcbnew.SHAPE_T_SEGMENT for item in existing):
        raise SystemExit(
            "REFUSE outline compaction: source Edge.Cuts is not a four-line rectangle")
    for item in existing:
        board.Remove(item)
    x0, y0, x1, y1 = map(float, rect)
    for start, end in (
            ((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
            ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        item = pcbnew.PCB_SHAPE(board)
        item.SetShape(pcbnew.SHAPE_T_SEGMENT)
        item.SetLayer(pcbnew.Edge_Cuts)
        item.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(start[0]), pcbnew.FromMM(start[1])))
        item.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(end[0]), pcbnew.FromMM(end[1])))
        item.SetWidth(pcbnew.FromMM(0.10))
        board.Add(item)


def _validate_hole_edge_margin(footprints, rect, minimum):
    """Conservatively gate drill-edge material on a compact rectangular board."""
    if rect is None or minimum is None:
        return []
    x0, y0, x1, y1 = map(float, rect)
    findings = []
    for footprint in footprints:
        for pad in footprint.Pads():
            if not pad.HasHole():
                continue
            position = pad.GetPosition()
            drill = pad.GetDrillSize()
            radius = max(_mm(drill.x), _mm(drill.y)) / 2.0
            x, y = _mm(position.x), _mm(position.y)
            margin = min(x - x0, x1 - x, y - y0, y1 - y) - radius
            if margin + 1e-6 < minimum:
                findings.append(
                    f"{footprint.GetReference()}.{pad.GetNumber()}={margin:.3f} mm")
    return findings


def _source_pad_nets(root_schematic):
    result = {}
    for members, net in cec_pcb_reconcile.netlist_groups(str(root_schematic)).items():
        for ref, pin in members:
            result[(ref, str(pin))] = net
    return result


def _footprint_id(footprint):
    fpid = footprint.GetFPID()
    return f"{fpid.GetLibNickname()}:{fpid.GetLibItemName()}"


def _angle_degrees(footprint):
    return float(footprint.GetOrientationDegrees()) % 360.0


def _integrated(board, plan, pad_nets):
    if _edge_box(board) != _target_edge_box(plan, _edge_box(board)):
        return False
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    if any(ref in footprints for ref in plan["remove_refs"]):
        return False
    for ref, expectation in contract.project_refs(plan).items():
        fp = footprints.get(ref)
        if not fp:
            return False
        part = contract.PARTS[expectation["part"]]
        if _footprint_id(fp) != part["footprint"]:
            return False
        # Placement idempotence includes the assembly identity.  A footprint
        # can be mechanically correct while still carrying a superseded MPN
        # as its value; treating that state as integrated lets stale BOM data
        # survive indefinitely on otherwise current boards.
        if fp.GetValue() != part["value"]:
            return False
        x, y, angle = plan["placements_mm"][ref]
        pos = fp.GetPosition()
        if math.hypot(_mm(pos.x) - x, _mm(pos.y) - y) > 0.01:
            return False
        if abs((_angle_degrees(fp) - angle + 180) % 360 - 180) > 0.01:
            return False
        for pad in fp.Pads():
            expected_net = pad_nets.get((ref, pad.GetNumber()))
            if expected_net is not None and pad.GetNetname() != expected_net:
                return False
    move_contract = dict(plan.get("preserved_moves_mm", {}))
    move_contract.update(plan.get("fixed_power_path_placements_mm", {}))
    for ref, (x, y, angle) in move_contract.items():
        fp = footprints.get(ref)
        if not fp:
            return False
        pos = fp.GetPosition()
        if math.hypot(_mm(pos.x) - x, _mm(pos.y) - y) > 0.01:
            return False
        if abs((_angle_degrees(fp) - angle + 180) % 360 - 180) > 0.01:
            return False
    return True


def _managed_pours_match(board, board_path, plan):
    """True only when laid managed-zone outlines equal canonical final geometry."""
    managed = set(plan.get("managed_pour_nets", ()))
    if not managed:
        return True
    if plan.get("managed_pour_source") == "pipeline":
        # Source placement must be copper-neutral. The full-board planner owns
        # these paths after every component is known and reserves them before
        # signal routing; retaining any source zone resurrects stale slabs.
        return not any(zone.GetNetname() in managed for zone in board.Zones())
    expected = []
    for pour in cec_constraints.canonical_high_current_pours(
            str(board_path), board=board):
        if pour.get("net") not in managed:
            continue
        xs = [float(point[0]) for point in pour.get("polygon") or ()]
        ys = [float(point[1]) for point in pour.get("polygon") or ()]
        if not xs or not ys:
            continue
        expected.append((
            pour["net"], pour.get("layer", "F.Cu"),
            round(min(xs), 3), round(max(xs), 3),
            round(min(ys), 3), round(max(ys), 3),
        ))
    actual = []
    for zone in board.Zones():
        net = zone.GetNetname()
        if net not in managed:
            continue
        layers = list(zone.GetLayerSet().CuStack())
        if len(layers) != 1:
            return False
        box = zone.GetBoundingBox()
        actual.append((
            net, board.GetLayerName(layers[0]),
            round(_mm(box.GetX()), 3),
            round(_mm(box.GetX() + box.GetWidth()), 3),
            round(_mm(box.GetY()), 3),
            round(_mm(box.GetY() + box.GetHeight()), 3),
        ))
    return sorted(actual) == sorted(expected)


def _new_footprint(board, ref, expectation, inventory, pad_nets, net_object):
    part = contract.PARTS[expectation["part"]]
    item_name = part["footprint"].split(":", 1)[1]
    footprint = pcbnew.FootprintLoad(
        str(part.get("footprint_dir", FP_LIBRARY)), item_name)
    if footprint is None:
        raise SystemExit(f"cannot load {part['footprint']} for {ref}")
    footprint.SetReference(ref)
    footprint.SetValue(inventory[ref]["value"])
    library_name = part["footprint"].split(":", 1)[0]
    footprint.SetFPID(pcbnew.LIB_ID(library_name, item_name))
    footprint.SetExcludedFromBOM(not part["in_bom"])
    footprint.SetExcludedFromPosFiles(not part["in_bom"])
    footprint.SetDNP(False)
    for pad in footprint.Pads():
        net = pad_nets.get((ref, pad.GetNumber()))
        if net is None:
            raise SystemExit(f"{ref}.{pad.GetNumber()} has no live schematic net")
        pad.SetNet(net_object(net))
    return footprint


def _add_track(board, net, layer, width_mm, start, end):
    if start == end:
        return None
    item = pcbnew.PCB_TRACK(board)
    item.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(start[0]), pcbnew.FromMM(start[1])))
    item.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(end[0]), pcbnew.FromMM(end[1])))
    item.SetWidth(pcbnew.FromMM(width_mm))
    item.SetLayer(board.GetLayerID(layer))
    # Set the scalar net code.  Persisting a SWIG NETINFO_ITEM proxy can be
    # rebound during subsequent board mutations and serialize as a neighbour
    # net even when GetNetname() was correct before SaveBoard().
    item.SetNetCode(net.GetNetCode())
    board.Add(item)
    return item


def _live_net(board, name):
    """Resolve a net immediately before assigning a new copper item.

    KiCad's SWIG NETINFO_ITEM proxies can be invalidated or rebound while a
    board is being mutated.  Retaining them across footprint removals/adds has
    produced correctly placed tracks carrying an adjacent net.  Re-querying
    the board here is cheap and makes generated copper fail-safe.
    """
    net = board.FindNet(name)
    if net is None:
        raise SystemExit(f"REFUSE: generated copper references missing net {name}")
    if net.GetNetname() != name:
        raise SystemExit(
            f"REFUSE: net resolver mismatch for {name}: {net.GetNetname()}")
    return net


def _add_bolt_pad_stitching(board, plan, net_objects):
    """Four through-vias outside each provisional T34069 washer/contact pad."""
    vias = tracks = 0
    for ref, expectation in plan["refs"].items():
        if expectation["part"] != contract.T340_DB:
            continue
        x, y, angle = plan["placements_mm"][ref]
        if angle != 0:
            raise SystemExit(f"REFUSE: {ref} bolt-pad stitch generator expects rotation 0")
        net = net_objects[expectation["net"]]
        # The provisional pad spans y +/-2.5. Vias stay outside the pad and
        # its sample-gated washer/contact envelope, with symmetric F/B pickups.
        via_y = y - 3.35
        pad_y = y - 2.0
        for dx in (-2.25, -0.75, 0.75, 2.25):
            via_x = x + dx
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(via_x), pcbnew.FromMM(via_y)))
            via.SetDrill(pcbnew.FromMM(0.50))
            via.SetWidth(pcbnew.FromMM(1.00))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNetCode(net.GetNetCode())
            board.Add(via)
            vias += 1
            for layer in ("F.Cu", "B.Cu"):
                if _add_track(board, net, layer, 1.00,
                              (via_x, via_y), (via_x, pad_y)) is not None:
                    tracks += 1
    return vias, tracks


def _add_contract_routes(board, plan, net_objects):
    count = 0
    for route in plan.get("routes_mm", []):
        net = _live_net(board, route["net"])
        for start, end in zip(route["points"], route["points"][1:]):
            item = _add_track(
                board, net, route["layer"], route["width"], start, end)
            if item and item.GetNetname() != route["net"]:
                raise SystemExit(
                    f"REFUSE: generated route net changed from {route['net']} "
                    f"to {item.GetNetname()}")
            if item:
                count += 1
    return count


def _add_contract_vias(board, plan, net_objects):
    count = 0
    existing = [track for track in board.GetTracks()
                if isinstance(track, pcbnew.PCB_VIA)]
    for spec in plan.get("vias_mm", []):
        if any(
                via.GetNetname() == spec["net"] and
                math.hypot(_mm(via.GetPosition().x) - spec["at"][0],
                           _mm(via.GetPosition().y) - spec["at"][1]) <= 0.01
                for via in existing):
            continue
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(
            pcbnew.FromMM(spec["at"][0]), pcbnew.FromMM(spec["at"][1])))
        via.SetDrill(pcbnew.FromMM(spec["drill"]))
        via.SetWidth(pcbnew.FromMM(spec["diameter"]))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(_live_net(board, spec["net"]).GetNetCode())
        board.Add(via)
        if via.GetNetname() != spec["net"]:
            raise SystemExit(
                f"REFUSE: generated via net changed from {spec['net']} "
                f"to {via.GetNetname()}")
        existing.append(via)
        count += 1
    return count


def _enforce_contract_copper_nets(board, plan):
    """Rebind contract copper after KiCad has finalized its serialized net map."""
    tracks = list(board.GetTracks())
    for route in plan.get("routes_mm", []):
        code = board.GetNetcodeFromNetname(route["net"])
        if code <= 0:
            raise SystemExit(
                f"REFUSE: final copper references missing net {route['net']}")
        layer = board.GetLayerID(route["layer"])
        for a, b in zip(route["points"], route["points"][1:]):
            matches = []
            for item in tracks:
                if isinstance(item, pcbnew.PCB_VIA) or item.GetLayer() != layer:
                    continue
                start = (_mm(item.GetStart().x), _mm(item.GetStart().y))
                end = (_mm(item.GetEnd().x), _mm(item.GetEnd().y))
                direct = math.hypot(start[0] - a[0], start[1] - a[1]) <= 0.01 and \
                    math.hypot(end[0] - b[0], end[1] - b[1]) <= 0.01
                reverse = math.hypot(start[0] - b[0], start[1] - b[1]) <= 0.01 and \
                    math.hypot(end[0] - a[0], end[1] - a[1]) <= 0.01
                if direct or reverse:
                    matches.append(item)
            if len(matches) != 1:
                raise SystemExit(
                    f"REFUSE: expected one generated {route['net']} segment "
                    f"{a}->{b}, found {len(matches)}")
            matches[0].SetNetCode(code)
    for spec in plan.get("vias_mm", []):
        code = board.GetNetcodeFromNetname(spec["net"])
        matches = [
            item for item in tracks if isinstance(item, pcbnew.PCB_VIA) and
            math.hypot(_mm(item.GetPosition().x) - spec["at"][0],
                       _mm(item.GetPosition().y) - spec["at"][1]) <= 0.01
        ]
        if len(matches) != 1:
            raise SystemExit(
                f"REFUSE: expected one generated {spec['net']} via at "
                f"{spec['at']}, found {len(matches)}")
        matches[0].SetNetCode(code)


def apply_project(name, write=False, force=False, source_pcb=None, output_pcb=None):
    plan = contract.PROJECTS[name]
    source_path = Path(source_pcb).resolve() if source_pcb else ROOT / plan["pcb"]
    pcb_path = Path(output_pcb).resolve() if output_pcb else source_path
    root_schematic = ROOT / plan["root_schematic"]
    if not source_path.is_file():
        raise SystemExit(f"{name}: missing PCB {source_path}")
    if write:
        pcb_path.parent.mkdir(parents=True, exist_ok=True)
    board = pcbnew.LoadBoard(str(source_path))
    outline_before = _edge_box(board)
    outline_target = _target_edge_box(plan, outline_before)
    pad_nets = _source_pad_nets(root_schematic)
    inventory = cec_sch_gates.inventory(str(root_schematic))
    contracted_refs = contract.project_refs(plan)
    interface_refs = set(plan["remove_refs"]) | set(contracted_refs)

    source_findings = contract.audit_project(name)
    if source_findings:
        raise SystemExit(
            f"{name}: REFUSE stale schematic contract: "
            + "; ".join(source_findings))

    # A routed candidate may predate a value-only source correction.  Refresh
    # metadata only when source and candidate still agree on footprint
    # geometry; a footprint mismatch remains a hard reconciliation problem.
    refreshed_values = []
    for footprint in board.GetFootprints():
        ref = footprint.GetReference()
        expected = inventory.get(ref)
        if expected is None:
            continue
        expected_value = expected.get("value")
        expected_footprint = expected.get("footprint")
        # Contracted parts use the pinned part identity.  Other candidate
        # parts retain the older copy-refresh behavior and are only eligible
        # when operating on a derived input board.
        if ref in contracted_refs:
            part = contract.PARTS[contracted_refs[ref]["part"]]
            expected_value = part["value"]
            expected_footprint = part["footprint"]
        elif source_pcb is None or ref in interface_refs:
            continue
        old_value = footprint.GetValue()
        if (expected_value is not None and old_value != expected_value and
                _footprint_id(footprint) == expected_footprint):
            footprint.SetValue(expected_value)
            refreshed_values.append({
                "ref": ref, "from": old_value, "to": expected_value,
            })
    placements_integrated = _integrated(board, plan, pad_nets)
    already_integrated = placements_integrated and not refreshed_values
    managed_pour_nets = set(plan.get("managed_pour_nets", ()))
    if placements_integrated and managed_pour_nets:
        already_integrated = (
            already_integrated
            and _managed_pours_match(board, source_path, plan))
    if not force and already_integrated:
        if write and pcb_path != source_path:
            pcbnew.SaveBoard(str(pcb_path), board)
            _enforce_contract_stackup(pcb_path, plan)
            _enforce_contract_contact_interface(pcb_path, plan)
        return {
            "project": name, "status": "already-integrated",
            "source_pcb": str(source_path), "pcb": str(pcb_path),
            "outline_before_mm": outline_before, "outline_after_mm": outline_before,
            "removed_refs": [], "added_refs": [], "local_copper_removed": 0,
            "refreshed_values": refreshed_values,
        }

    # Snapshot every SWIG proxy and all information derived from it before the
    # first Remove(), which can invalidate KiCad container proxies.
    footprints = list(board.GetFootprints())
    tracks = list(board.GetTracks())
    # A forced route/zone regeneration must not churn footprints that already
    # satisfy the complete placement contract.  Besides being faster, keeping
    # them stable prevents needless KiCad net-table renumbering.
    reuse_footprints = placements_integrated
    old_footprints = [
        fp for fp in footprints
        if fp.GetReference() in (
            set(plan["remove_refs"]) if reuse_footprints else interface_refs)
    ]
    move_contract = dict(plan.get("preserved_moves_mm", {}))
    move_contract.update(plan.get("fixed_power_path_placements_mm", {}))
    move_refs = set(move_contract) - set(contracted_refs)
    contracted_move_footprints = [
        fp for fp in footprints if fp.GetReference() in move_refs]
    if len(contracted_move_footprints) != len(move_refs):
        missing = sorted(
            move_refs
            - {fp.GetReference() for fp in contracted_move_footprints})
        raise SystemExit(f"{name}: REFUSE preserved move ref(s) missing: {missing}")
    move_footprints = []
    for fp in contracted_move_footprints:
        x, y, angle = move_contract[fp.GetReference()]
        pos = fp.GetPosition()
        if (math.hypot(_mm(pos.x) - x, _mm(pos.y) - y) > 0.01
                or abs((_angle_degrees(fp) - angle + 180) % 360 - 180) > 0.01):
            move_footprints.append(fp)
    old_boxes = [_box_mm(fp, inflate=0.30) for fp in old_footprints + move_footprints]
    affected_nets = {
        pad.GetNetname() for fp in old_footprints + move_footprints
        for pad in fp.Pads() if pad.GetNetname()
    }
    affected_nets.update(
        pad_nets[(ref, pin)]
        for ref, expectation in contracted_refs.items()
        for pin in contract.expectation_nets(expectation)
        if (ref, pin) in pad_nets)

    local_copper = []
    for track in tracks:
        if isinstance(track, pcbnew.PCB_VIA) and any(
                math.hypot(_mm(track.GetPosition().x) - x,
                           _mm(track.GetPosition().y) - y) <= 0.05
                for x, y in plan.get("remove_vias_mm", [])):
            local_copper.append(track)
            continue
        if not isinstance(track, pcbnew.PCB_VIA) and any(
                (
                    math.hypot(_mm(track.GetStart().x) - a[0],
                               _mm(track.GetStart().y) - a[1]) <= 0.05 and
                    math.hypot(_mm(track.GetEnd().x) - b[0],
                               _mm(track.GetEnd().y) - b[1]) <= 0.05
                ) or (
                    math.hypot(_mm(track.GetStart().x) - b[0],
                               _mm(track.GetStart().y) - b[1]) <= 0.05 and
                    math.hypot(_mm(track.GetEnd().x) - a[0],
                               _mm(track.GetEnd().y) - a[1]) <= 0.05
                )
                for a, b in plan.get("remove_track_segments_mm", [])):
            local_copper.append(track)
            continue
        if track.GetNetname() in plan.get("replace_track_nets", []):
            local_copper.append(track)
            continue
        if track.GetNetname() not in affected_nets:
            continue
        points = [track.GetPosition()] if isinstance(track, pcbnew.PCB_VIA) else [
            track.GetStart(), track.GetEnd()]
        if any(_point_in_box(point, box) for point in points for box in old_boxes):
            local_copper.append(track)

    net_objects = {str(net): obj for net, obj in board.GetNetInfo().NetsByName().items()}

    def net_object(name):
        if name not in net_objects:
            obj = pcbnew.NETINFO_ITEM(board, name)
            board.Add(obj)
            net_objects[name] = obj
        return net_objects[name]

    if reuse_footprints:
        current_by_ref = {fp.GetReference(): fp for fp in footprints}
        new_footprints = [current_by_ref[ref] for ref in contracted_refs]
        new_boxes = {ref: _box_mm(current_by_ref[ref]) for ref in contracted_refs}
    else:
        new_footprints = []
        new_boxes = {}
        for ref, expectation in contracted_refs.items():
            footprint = _new_footprint(
                board, ref, expectation, inventory, pad_nets, net_object)
            x, y, angle = plan["placements_mm"][ref]
            footprint.SetPosition(pcbnew.VECTOR2I(
                pcbnew.FromMM(x), pcbnew.FromMM(y)))
            footprint.SetOrientationDegrees(angle)
            new_boxes[ref] = _box_mm(footprint)
            new_footprints.append(footprint)

    moved_boxes = {}
    for footprint in move_footprints:
        ref = footprint.GetReference()
        x, y, angle = move_contract[ref]
        footprint.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        footprint.SetOrientationDegrees(angle)
        moved_boxes[ref] = _box_mm(footprint)

    # Remove every pre-existing trace/via that enters a new interface or moved
    # component envelope, even when it belongs to a foreign net.  Merely
    # deleting old pad-connected stubs misses long signal tracks crossing a
    # newly enlarged terminal land and can silently create shorts.
    new_keepouts = list(new_boxes.values()) + list(moved_boxes.values())
    for ref, expectation in plan["refs"].items():
        if expectation["part"] == contract.T340_DB:
            x, y, _angle = plan["placements_mm"][ref]
            new_keepouts.append((x - 3.0, y - 3.95, x + 3.0, y - 1.50))
    selected = {id(item) for item in local_copper}
    for track in tracks:
        if id(track) in selected:
            continue
        if isinstance(track, pcbnew.PCB_VIA):
            intersects = any(_point_in_box(track.GetPosition(), box) for box in new_keepouts)
        else:
            intersects = any(
                _segment_intersects_box(track.GetStart(), track.GetEnd(), box)
                for box in new_keepouts)
        if intersects:
            local_copper.append(track)
            selected.add(id(track))

    collisions = []
    ordered = sorted(new_boxes)
    for index, ref in enumerate(ordered):
        for other_ref in ordered[index + 1:]:
            if _boxes_overlap(new_boxes[ref], new_boxes[other_ref]):
                allowance = plan.get("interface_body_overlap_allowance_mm", 0.0)
                px, py = _overlap_penetration(new_boxes[ref], new_boxes[other_ref])
                if min(px, py) > allowance + 1e-6:
                    collisions.append(f"{ref}<->{other_ref}")
    for existing in footprints:
        existing_ref = existing.GetReference()
        if existing_ref in interface_refs or existing_ref in move_refs:
            continue
        box = _box_mm(existing)
        for ref, new_box in new_boxes.items():
            if _boxes_overlap(new_box, box):
                collisions.append(f"{ref}{new_box}<->{existing_ref}{box}")
    for ref, new_box in new_boxes.items():
        for moved_ref, moved_box in moved_boxes.items():
            if _boxes_overlap(new_box, moved_box):
                collisions.append(f"{ref}{new_box}<->{moved_ref}{moved_box}")
    stationary = [fp for fp in footprints
                  if fp.GetReference() not in interface_refs | move_refs]
    for moved_ref, moved_box in moved_boxes.items():
        for existing in stationary:
            existing_ref = existing.GetReference()
            box = _box_mm(existing)
            if _boxes_overlap(moved_box, box):
                collisions.append(f"{moved_ref}{moved_box}<->{existing_ref}{box}")
    moved_order = sorted(moved_boxes)
    for index, ref in enumerate(moved_order):
        for other_ref in moved_order[index + 1:]:
            if _boxes_overlap(moved_boxes[ref], moved_boxes[other_ref]):
                collisions.append(f"{ref}<->{other_ref}")
    if collisions:
        raise SystemExit(f"{name}: REFUSE footprint collision(s): {', '.join(collisions)}")
    if outline_target is not None:
        tolerance = max(
            0.30,  # provisional bolt pads intentionally approach the board edge
            plan.get("edge_overhang_allowance_mm", 0.0))
        exempt = set(plan.get("footprint_outline_exempt_refs", ()))
        for ref, box in new_boxes.items():
            if ref in exempt:
                continue
            if (box[0] < outline_target[0] - tolerance or
                    box[1] < outline_target[1] - tolerance or
                    box[2] > outline_target[2] + tolerance or
                    box[3] > outline_target[3] + tolerance):
                raise SystemExit(
                    f"{name}: REFUSE {ref} footprint box {box} exceeds outline {outline_target}")

    final_footprints = list(footprints) if reuse_footprints else (
        new_footprints + move_footprints +
        [fp for fp in footprints
         if fp.GetReference() not in interface_refs | move_refs])
    hole_findings = _validate_hole_edge_margin(
        final_footprints, plan.get("outline_rect_mm"),
        plan.get("minimum_hole_edge_mm"))
    if hole_findings:
        raise SystemExit(
            f"{name}: REFUSE compact outline hole-edge margin: {', '.join(hole_findings)}")

    report = {
        "project": name,
        "status": "dry-run" if not write else "applied",
        "source_pcb": str(source_path),
        "pcb": str(pcb_path),
        "outline_before_mm": outline_before,
        "removed_refs": sorted(fp.GetReference() for fp in old_footprints),
        "added_refs": [] if reuse_footprints else sorted(contracted_refs),
        "local_copper_removed": len(local_copper),
        "refreshed_values": refreshed_values,
        "placements_mm": plan["placements_mm"],
        "preserved_moves_mm": plan.get("preserved_moves_mm", {}),
        "fixed_power_path_placements_mm": plan.get(
            "fixed_power_path_placements_mm", {}),
        "footprint_boxes_mm": new_boxes,
        "stitch_vias_added": 0,
        "stitch_tracks_added": 0,
        "contract_tracks_added": 0,
        "contract_vias_added": 0,
        "managed_pour_zones_removed": 0,
        "managed_pour_zones_added": 0,
    }
    strip_pipeline_zones = False
    if not write:
        report["outline_after_mm"] = outline_target
        return report

    # Add replacements first, then perform all removals without dereferencing
    # any old board child again.
    if not reuse_footprints:
        for footprint in new_footprints:
            board.Add(footprint)
    for item in local_copper:
        board.Remove(item)
    for footprint in old_footprints:
        board.Remove(footprint)
    if plan.get("outline_rect_mm") is not None:
        _set_rect_outline(board, plan["outline_rect_mm"])
    # Footprint replacement can renumber KiCad's board-local net table.  The
    # Python bindings expose transient codes until a board round-trip; copper
    # generated before that point can serialize under an adjacent net even if
    # its in-memory name looked correct.  Normalize through a private temporary
    # board, reload, then resolve every generated item against the stable table.
    board.SynchronizeNetsAndNetClasses(False)
    board.BuildListOfNets()
    fd, normalization_board = tempfile.mkstemp(
        suffix=".kicad_pcb", dir=pcb_path.parent)
    os.close(fd)
    try:
        pcbnew.SaveBoard(normalization_board, board)
        board = pcbnew.LoadBoard(normalization_board)
    finally:
        _cleanup_temporary_board(normalization_board)
    net_objects = {
        str(net): obj for net, obj in board.GetNetInfo().NetsByName().items()
    }
    stitch_vias, stitch_tracks = _add_bolt_pad_stitching(board, plan, net_objects)
    report["stitch_vias_added"] = stitch_vias
    report["stitch_tracks_added"] = stitch_tracks
    report["contract_tracks_added"] = _add_contract_routes(board, plan, net_objects)
    report["contract_vias_added"] = _add_contract_vias(board, plan, net_objects)
    if managed_pour_nets:
        if plan.get("managed_pour_source") == "pipeline":
            # Do not remove ZONE children through pcbnew here; KiCad 10 can
            # destroy its global SWIG type registry on that operation. Count
            # the closed target set now and strip its serialized expressions
            # atomically after the normal save below.
            strip_pipeline_zones = True
            report["managed_pour_zones_removed"] = sum(
                1 for zone in board.Zones()
                if zone.GetNetname() in managed_pour_nets)
        else:
            pours = [
                pour for pour in cec_constraints.canonical_high_current_pours(
                    str(source_path), board=board)
                if pour.get("net") in managed_pour_nets
            ]
            found = {pour.get("net") for pour in pours}
            missing = sorted(managed_pour_nets - found)
            if missing:
                raise SystemExit(
                    f"{name}: REFUSE managed pour regeneration missing {missing}")
            replacement = cec_fr.replace_generated_power_pours(
                board, pours, managed_nets=managed_pour_nets, fill=False)
            report["managed_pour_zones_removed"] = replacement["removed"]
            report["managed_pour_zones_added"] = replacement["added"]
    # Defer filling until after the copper round-trip below. KiCad 10's SWIG
    # wrapper can invalidate unrelated geometry proxies immediately after a
    # fill in a mutation-heavy process; the later reload is the intended
    # stabilization boundary and already performs the authoritative fill.
    # Zone removal invalidates KiCad 10's BOX2I result wrapper in this process
    # even though the Edge.Cuts objects are untouched.  The target was already
    # validated (or constructed by _set_rect_outline); defer the independent
    # bbox re-read until the immediately following board round-trip.
    outline_after = outline_target
    report["outline_after_mm"] = outline_after

    # One last private round-trip finalizes KiCad's net-number serialization.
    # Rebind the exact contract geometry afterward, so generated copper cannot
    # silently inherit a neighbouring code as happened on the compact ATX DB.
    fd, copper_board = tempfile.mkstemp(suffix=".kicad_pcb", dir=pcb_path.parent)
    os.close(fd)
    try:
        pcbnew.SaveBoard(copper_board, board)
        board = pcbnew.LoadBoard(copper_board)
        reloaded_outline = _edge_box(board)
        if reloaded_outline != outline_target:
            raise SystemExit(
                f"{name}: REFUSE outline differs from contract "
                f"{outline_target} -> {reloaded_outline}")
    finally:
        _cleanup_temporary_board(copper_board)
    _enforce_contract_copper_nets(board, plan)
    if list(board.Zones()):
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # ZONE_FILLER can rebuild the local net table.  Serialize and reload that
    # final table once more, then bind contract copper without any later board
    # mutation.  This mirrors a normal editor open/save cycle and prevents a
    # correct in-memory name from being emitted under a stale numeric code.
    fd, filled_board = tempfile.mkstemp(suffix=".kicad_pcb", dir=pcb_path.parent)
    os.close(fd)
    try:
        pcbnew.SaveBoard(filled_board, board)
        board = pcbnew.LoadBoard(filled_board)
    finally:
        _cleanup_temporary_board(filled_board)
    _enforce_contract_copper_nets(board, plan)

    fd, temporary = tempfile.mkstemp(suffix=".kicad_pcb", dir=pcb_path.parent)
    os.close(fd)
    try:
        pcbnew.SaveBoard(temporary, board)
        os.replace(temporary, pcb_path)
    finally:
        _cleanup_temporary_board(temporary)
    _enforce_contract_stackup(pcb_path, plan)
    _enforce_contract_contact_interface(pcb_path, plan)
    if strip_pipeline_zones:
        stripped = _strip_managed_zone_blocks(pcb_path, managed_pour_nets)
        if stripped != report["managed_pour_zones_removed"]:
            raise SystemExit(
                f"{name}: REFUSE serialized managed-zone count drift: "
                f"expected {report['managed_pour_zones_removed']}, "
                f"removed {stripped}")
    report["orphan_temp_projects_removed"] = (
        _cleanup_orphan_temporary_projects(pcb_path.parent))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", action="append", choices=sorted(contract.PROJECTS))
    parser.add_argument("--apply", action="store_true", help="write the reviewed placement to the PCB")
    parser.add_argument("--force", action="store_true", help="reapply and clean interface-local copper")
    parser.add_argument(
        "--input-board", type=Path,
        help="one-project routed/candidate PCB to migrate instead of the manifest placement")
    parser.add_argument(
        "--output-board", type=Path,
        help="write migrated PCB here; requires --apply and preserves --input-board")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    projects = args.project or list(contract.PROJECTS)
    if (args.input_board or args.output_board) and len(projects) != 1:
        parser.error("--input-board/--output-board require exactly one --project")
    if args.output_board and not args.apply:
        parser.error("--output-board requires --apply")
    # pcbnew's SWIG ownership can return an invalid board proxy after a prior
    # board in the same process removed children.  Isolate each project in its
    # own worker process; this also makes all-project unattended runs reliable.
    if len(projects) > 1 and not args.worker:
        reports = []
        for name in projects:
            command = [sys.executable, str(Path(__file__).resolve()),
                       "--project", name, "--worker", "--json"]
            if args.apply:
                command.append("--apply")
            if args.force:
                command.append("--force")
            process = subprocess.run(command, capture_output=True, text=True)
            if process.returncode:
                if process.stderr:
                    print(process.stderr, file=sys.stderr, end="")
                if process.stdout:
                    print(process.stdout, file=sys.stderr, end="")
                raise SystemExit(process.returncode)
            start = process.stdout.find("[")
            if start < 0:
                print(process.stdout, file=sys.stderr, end="")
                raise SystemExit(f"{name}: worker produced no JSON report")
            payload, _end = json.JSONDecoder().raw_decode(process.stdout[start:])
            reports.extend(payload)
    else:
        reports = [apply_project(
            name, args.apply, args.force,
            source_pcb=args.input_board, output_pcb=args.output_board)
            for name in projects]
    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for report in reports:
            print(f"{report['project']}: {report['status']}; "
                  f"removed={len(report['removed_refs'])}; added={len(report['added_refs'])}; "
                  f"local_copper_removed={report['local_copper_removed']}")


if __name__ == "__main__":
    main()
    # KiCad 10's pcbnew/wx SWIG modules can crash while Python tears down a
    # successfully completed mutation process, after the atomic save and JSON
    # report have both finished. Let the OS reclaim extension state instead of
    # running the faulty extension destructors; exceptions never reach here.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
