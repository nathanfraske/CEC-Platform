#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Own the local IC-power-pin -> bypass-cap -> GND-entry cell.

Placement already assigns a distinct value-qualified capacitor to each audited
device supply pin. This routing pass turns that ownership into copper before
the broad router runs:

* shortest guarded local supply link;
* immediate GND return at the capacitor;
* via in pad only for a fabrication profile that explicitly permits POFV;
* otherwise the shortest legal dogbone;
* all-or-nothing rollback for each local cell; and
* exact per-terminal admission for the board-wide GND-access reservation.
"""
from __future__ import annotations

import argparse
import json
import math
import heapq
import os
import shutil
import subprocess
import sys
import tempfile

import pcbnew

import cec_constraints
import cec_fab_profile
import cec_fr
import cec_stage_admission


MM = 1_000_000
ENDPOINT_NECKDOWN_GROUP = cec_fr.ENDPOINT_NECKDOWN_GROUP
ENDPOINT_NECKDOWN_RULE_BEGIN = cec_fr.ENDPOINT_NECKDOWN_RULE_BEGIN
ENDPOINT_NECKDOWN_RULE_END = cec_fr.ENDPOINT_NECKDOWN_RULE_END


def _group_endpoint_neckdowns(board, items, full_width):
    """Put only generated sub-class endpoint tracks in a named rule group."""
    return cec_fr.group_endpoint_neckdowns(board, items, full_width)


def _ensure_endpoint_neckdown_rule(board_path, report):
    """Install the narrow-track exception only for the generated PCB group.

    The Power netclass remains at its trunk width.  KiCad evaluates custom
    rules in reverse order, so this final, group-qualified rule overrides that
    floor only for endpoint tracks which the guarded generator explicitly put
    in ``CEC_LOCAL_ENDPOINT_NECKDOWN``.  No net name, reference, or board
    coordinate is baked into the exception.
    """
    return cec_fr.ensure_endpoint_neckdown_rule(board_path, report)


def _missing_assignment_report(row):
    """Preserve why one bypass requirement has no one-to-one assignment."""
    nearest_ref = row.get("nearest_ref")
    nearest_mm = row.get("nearest_mm")
    limit_mm = row.get("max_mm")
    report = {
        "owner": row.get("ref"), "pin": row.get("pin"),
        "rail": row.get("rail"), "cap": nearest_ref,
        "status": "refused",
        "nearest_compatible_ref": nearest_ref,
        "nearest_compatible_mm": (round(float(nearest_mm), 3)
                                  if nearest_mm is not None else None),
        "assignment_limit_mm": (round(float(limit_mm), 3)
                                if limit_mm is not None else None),
    }
    if nearest_ref is None or nearest_mm is None:
        report["reason"] = "no compatible local bypass capacitor"
        report["assignment_failure"] = "no_compatible_component"
    elif (limit_mm is not None
          and not cec_constraints._within_physical_distance_limit(
              nearest_mm, limit_mm)):
        report["reason"] = "nearest compatible capacitor outside assignment limit"
        report["assignment_failure"] = "compatible_component_out_of_range"
        report["assignment_gap_mm"] = round(
            float(nearest_mm) - float(limit_mm), 3)
    else:
        # A compatible part exists inside the radius but bipartite ownership
        # assigned it to another requirement.  Moving this package cannot
        # manufacture another distinct capacitor.
        report["reason"] = "compatible in-limit capacitor already owned"
        report["assignment_failure"] = "distinct_component_contention"
        report["assignment_gap_mm"] = 0.0
    return report


def _netclass(board, net):
    try:
        klass = board.GetNetInfo().GetNetItem(net).GetNetClassSlow()
        return {
            "width": klass.GetTrackWidth(),
            "clearance": klass.GetClearance(),
            "via_dia": klass.GetViaDiameter() / MM,
            "via_drill": klass.GetViaDrill() / MM,
        }
    except Exception:                                    # noqa: BLE001
        return {
            "width": pcbnew.FromMM(0.25),
            "clearance": pcbnew.FromMM(0.20),
            "via_dia": 0.6, "via_drill": 0.3,
        }


def _board_legal_through_via_geometry(board, diameter_mm, drill_mm):
    """Compatibility wrapper for the shared board-rule authority."""
    return cec_fab_profile.board_legal_through_via_geometry(
        board, diameter_mm, drill_mm)


def _hole_to_hole_clear(board, position, drill_mm, *, tolerance_mm=0.0005):
    """Check the net-independent finished-hole edge clearance.

    Same-net copper is allowed to overlap, so the copper spot guard cannot
    enforce drill spacing.  Include every existing via and drilled footprint
    pad using the board's resolved fabrication-profile floor.
    """
    try:
        minimum = float(board.GetDesignSettings().m_HoleToHoleMin) / MM
    except Exception:                                    # noqa: BLE001
        minimum = 0.25
    candidate_radius = float(drill_mm) / 2.0
    conflicts = []

    def consider(point, other_drill_mm, identity):
        center = math.hypot(
            point.x - position.x, point.y - position.y) / MM
        edge = center - candidate_radius - float(other_drill_mm) / 2.0
        if edge + float(tolerance_mm) < minimum:
            conflicts.append({
                "item": identity, "center_mm": round(center, 4),
                "edge_mm": round(edge, 4),
                "minimum_mm": round(minimum, 4),
            })

    for item in board.GetTracks():
        if item.GetClass() == "PCB_VIA":
            consider(item.GetPosition(), item.GetDrillValue() / MM,
                     "via:%s" % item.m_Uuid.AsString())
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            if pad.GetAttribute() not in (
                    pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                continue
            drill = pad.GetDrillSize()
            other = max(drill.x, drill.y) / MM
            if other > 0:
                consider(pad.GetPosition(), other, "%s.%s" % (
                    footprint.GetReference(), pad.GetPadName()))
    return not conflicts, conflicts


def _shortest_track_path_mm(board, left, right, *, snap_mm=0.06):
    """Return explicit-copper path length between two pads, excluding zones.

    A global connectivity answer is insufficient for bypass ownership: both
    pads can be connected through a distant plane entry and still form a poor
    high-frequency loop.  This compact graph follows routed track/arc endpoints
    and through vias.  Zones are deliberately excluded so only a visible local
    link can satisfy the supply-path contract.
    """
    if left.GetNetCode() <= 0 or left.GetNetCode() != right.GetNetCode():
        return None
    snap = max(1, pcbnew.FromMM(snap_mm))

    def key(point, layer):
        return (int(round(point.x / snap)), int(round(point.y / snap)),
                int(layer))

    graph = {}
    points = {}

    def add_node(node, point):
        graph.setdefault(node, [])
        points.setdefault(node, point)

    def edge(a, b, cost):
        graph.setdefault(a, []).append((b, float(cost)))
        graph.setdefault(b, []).append((a, float(cost)))

    net_code = left.GetNetCode()
    for item in board.GetTracks():
        if item.GetNetCode() != net_code:
            continue
        if item.GetClass() == "PCB_VIA":
            point = item.GetPosition()
            nodes = []
            for layer in item.GetLayerSet().CuStack():
                node = key(point, layer)
                add_node(node, point); nodes.append(node)
            for node in nodes[1:]:
                edge(nodes[0], node, 0.0)
            continue
        start, end, layer = item.GetStart(), item.GetEnd(), item.GetLayer()
        a, b = key(start, layer), key(end, layer)
        add_node(a, start); add_node(b, end)
        try:
            length = item.GetLength() / MM
        except Exception:                                # noqa: BLE001
            length = math.hypot(end.x - start.x, end.y - start.y) / MM
        edge(a, b, length)

    source, target = ("pad", "source"), ("pad", "target")
    graph[source], graph[target] = [], []
    for node, point in points.items():
        layer = node[2]
        if left.IsOnLayer(layer) and left.HitTest(point, snap):
            edge(source, node, 0.0)
        if right.IsOnLayer(layer) and right.HitTest(point, snap):
            edge(target, node, 0.0)
    serial = 0
    queue = [(0.0, serial, source)]
    best = {source: 0.0}
    while queue:
        distance, _serial, node = heapq.heappop(queue)
        if distance != best.get(node):
            continue
        if node == target:
            return distance
        for neighbor, cost in graph.get(node, ()):
            candidate = distance + cost
            if candidate + 1e-12 < best.get(neighbor, float("inf")):
                best[neighbor] = candidate
                serial += 1
                heapq.heappush(queue, (candidate, serial, neighbor))
    return None


def _pad_identity(pad):
    """Return JSON-safe endpoint ownership for refusal certificates."""
    ref = None
    try:
        parent = pad.GetParentFootprint()
        ref = parent.GetReference() if parent is not None else None
    except Exception:                                  # noqa: BLE001
        try:
            parent = pad.GetParent()
            ref = parent.GetReference() if parent is not None else None
        except Exception:                              # noqa: BLE001
            pass
    return {"kind": "pad", "ref": ref,
            "pad": str(pad.GetPadName())}


def _pofv_supply_bridge_ops(board, owner_pad, cap_pad, width, clearance,
                            net_code, bridge_layers, spec):
    """Bridge an assigned supply cell through two qualified POFV pad seats.

    This is the low-inductance fallback for adjacent fine-pitch power pins
    whose package row cannot fit another face-layer via dogbone.  It is
    available only when the declared fabrication profile explicitly supports
    plated-over filled vias.  Board minima, process dimensions, pad-local
    containment, hole spacing, edge clearance, and the inner route are all
    proven before any copper is returned to the caller.
    """
    profile_name = cec_fab_profile.active_profile_name(board)
    profile = (cec_fab_profile.get_profile(profile_name)
               if profile_name else None)
    preferred = cec_fab_profile.preferred_pofv_geometry(profile)
    if not preferred or not bridge_layers:
        return None, None
    # A filled/capped via wholly contained by the assigned endpoint pad is an
    # endpoint-limited local interconnect, not a trunk-layer transition.  Use
    # the declared POFV geometry clamped to board minima (the same exception
    # already enforced for immediate decoupler GND returns).  The independent
    # conformance gate exempts it only after proving exact same-net pad
    # containment; an ordinary off-pad via still owes the full netclass size.
    requested_diameter = float(preferred[0])
    requested_drill = float(preferred[1])
    _ordinary_diameter, _ordinary_drill, board_limits = \
        _board_legal_through_via_geometry(
            board, requested_diameter, requested_drill)
    # Do not clamp a profile-qualified POFV to the ordinary through-via land
    # rule: that would make it larger than the fine-pitch pad it must be fully
    # contained by.  The release gates already model this exact exception and
    # suppress ordinary diameter/annular findings only after proving profile,
    # dimensions, and same-net full-land containment.  Every non-contained or
    # off-pad via remains subject to the normal board/netclass minima.
    diameter, drill = requested_diameter, requested_drill
    process_ok, _process_reason = cec_fab_profile.pofv_dimensions(
        profile, diameter, drill)
    if not process_ok:
        return None, None
    positions = [owner_pad.GetPosition(), cap_pad.GetPosition()]
    pads = [owner_pad, cap_pad]
    pofv_allowed = []
    for pad, position in zip(pads, positions):
        contained = set(pad.GetLayerSet().CuStack())
        pofv_allowed.append(bool(
            cec_fr._edge_leg_clear(
                board, position, position,
                pcbnew.FromMM(diameter) // 2)
            and _hole_to_hole_clear(board, position, drill)[0]
            and cec_fr._via_spot_clear(
                board, position, pcbnew.FromMM(diameter), clearance,
                {net_code}, drill_nm=pcbnew.FromMM(drill),
                net_code=net_code, contained_layers=contained)))
    try:
        minimum_hole = board.GetDesignSettings().m_HoleToHoleMin / MM
    except Exception:                                   # noqa: BLE001
        minimum_hole = 0.25
    ordinary_diameter, ordinary_drill, _ordinary_limits = \
        _board_legal_through_via_geometry(
            board, float(spec["via_dia"]), float(spec["via_drill"]))

    def endpoint_escape(pad):
        try:
            if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD):
                return None
        except Exception:                                # noqa: BLE001
            return None
        try:
            board_min = board.GetDesignSettings().m_TrackMinWidth
        except Exception:                                # noqa: BLE001
            board_min = pcbnew.FromMM(0.20)
        minor = min(pad.GetSize().x, pad.GetSize().y)
        if minor >= width:
            return None
        local_width = min(width, max(int(board_min), minor // 2))
        budget = pcbnew.FromMM(max(0.6, min(1.5, 1.5 * width / MM)))
        return local_width, budget

    def endpoint_seats(index):
        """Return one low-inductance endpoint seat with an explicit via mode.

        A narrow IC land may be unable to contain the selected POFV even when
        its assigned capacitor land can.  Requiring the same via style at both
        ends unnecessarily refuses an otherwise ordinary professional escape.
        Prefer an in-pad POFV whenever it is qualified; otherwise use the same
        bounded, guarded dogbone sweep as the generic bridge engine, with an
        ordinary board-legal through via off the pad.
        """
        pad, position = pads[index], positions[index]
        if pofv_allowed[index]:
            return [((position.x, position.y), [
                ("via", position, drill, diameter)], "pofv")]
        layers = sorted(set(pad.GetLayerSet().CuStack()))
        if not layers:
            return []
        layer = layers[0]
        escape = endpoint_escape(pad)
        rows = []
        for off in (0.55, 0.8, 1.2, 1.6, 2.0, 2.5):
            for angle in (0, 90, 180, 270, 45, 135, 225, 315):
                radians = math.radians(angle)
                seat = pcbnew.VECTOR2I(
                    int(position.x + math.cos(radians) * pcbnew.FromMM(off)),
                    int(position.y + math.sin(radians) * pcbnew.FromMM(off)))
                if not cec_fr._edge_leg_clear(
                        board, seat, seat,
                        pcbnew.FromMM(ordinary_diameter) // 2):
                    continue
                if not _hole_to_hole_clear(
                        board, seat, ordinary_drill)[0]:
                    continue
                legs = cec_fr._guarded_profiled_lastmile_legs(
                    board, position, seat, width, layer, clearance, net_code,
                    lambda a, b, half: cec_fr._edge_leg_clear(
                        board, a, b, half),
                    start_escape=escape, allow_maze=False)
                if not legs:
                    continue
                if not cec_fr._via_spot_clear(
                        board, seat, pcbnew.FromMM(ordinary_diameter),
                        clearance, {net_code},
                        drill_nm=pcbnew.FromMM(ordinary_drill),
                        net_code=net_code):
                    continue
                ops = [("trk", a, b, leg_width, layer)
                       for a, b, leg_width in legs]
                ops.append(("via", seat, ordinary_drill,
                            ordinary_diameter))
                rows.append(((seat.x, seat.y), ops, "dogbone"))
                # Preserve a deterministic but useful directional choice set.
                # The complete bridge ranking below selects on total copper.
                if len(rows) >= 16:
                    return rows
        return rows

    seats_a = endpoint_seats(0)
    seats_b = endpoint_seats(1)
    if not seats_a or not seats_b:
        return None, None
    pair_rows = cec_fr._ranked_bridge_seat_pairs(
        [(point, ops) for point, ops, _mode in seats_a],
        [(point, ops) for point, ops, _mode in seats_b],
        pcbnew.FromMM(minimum_hole + ordinary_drill))
    modes = {
        (point[0], point[1], tuple(
            (op[0], op[1].x, op[1].y) for op in ops if op[0] == "via")):
        mode for point, ops, mode in seats_a + seats_b}
    for layer in bridge_layers:
        for (left, left_ops), (right, right_ops) in pair_rows:
            start = pcbnew.VECTOR2I(int(left[0]), int(left[1]))
            end = pcbnew.VECTOR2I(int(right[0]), int(right[1]))
            legs = cec_fr._guarded_profiled_lastmile_legs(
                board, start, end, width, layer, clearance, net_code,
                lambda a, b, half: cec_fr._edge_leg_clear(
                    board, a, b, half),
                allow_maze=True, maze_margin_mm=2.0)
            if not legs:
                continue
            ops = list(left_ops)
            ops.extend(("trk", a, b, leg_width, layer)
                       for a, b, leg_width in legs)
            ops.extend(right_ops)
            def seat_mode(point, endpoint_ops):
                key = (point[0], point[1], tuple(
                    (op[0], op[1].x, op[1].y)
                    for op in endpoint_ops if op[0] == "via"))
                return modes.get(key, "unknown")
            endpoint_modes = [seat_mode(left, left_ops),
                              seat_mode(right, right_ops)]
            via_rows = [op for op in ops if op[0] == "via"]
            return ops, {
            "fab_profile": profile_name,
            "diameter_mm": round(max(op[3] for op in via_rows), 3),
            "drill_mm": round(max(op[2] for op in via_rows), 3),
            "requested_diameter_mm": round(requested_diameter, 3),
            "requested_drill_mm": round(requested_drill, 3),
            "netclass_via_diameter_mm": round(
                float(spec.get("via_dia") or 0.0), 3),
            "netclass_via_drill_mm": round(
                float(spec.get("via_drill") or 0.0), 3),
            "endpoint_modes": endpoint_modes,
            "endpoint_limited_local_via": "pofv" in endpoint_modes,
            "qualified_process_exception": bool(
                "pofv" in endpoint_modes and (
                    diameter + 1e-9 < _ordinary_diameter
                    or drill + 1e-9 < _ordinary_drill)),
            "board_limits": board_limits,
        }
    return None, None


def _local_supply_limit_mm(direct_mm, class_width_mm=0.25,
                           clearance_mm=0.20):
    """Maximum local bypass path including one obstacle-escape throat.

    A ratio-only bound is too tight when a fine-pitch pad is already close to
    its capacitor: the guarded path may need to go around one adjacent land by
    one full netclass width plus clearance.  The additive term stays bounded,
    so a remote dogleg cannot become acceptable merely because its endpoints
    are farther apart.
    """
    direct_mm = float(direct_mm)
    quantization_mm = 0.05
    # A canonical dogbone plus 45-degree inner-layer bridge can add just over
    # 35% when the only legal via seat is on the far side of a narrow package
    # pin.  Forty percent is still a strict local bound, but admits that real
    # geometry instead of failing on grid-scale differences (the U11 case was
    # 4.559 mm against 4.448 mm at the old ratio).
    return max(direct_mm + 0.35,
               direct_mm * 1.40 + quantization_mm,
               direct_mm + float(class_width_mm) + float(clearance_mm)
               + quantization_mm)


def _add_supply_link(board, owner_pad, cap_pad, *, lock, diagnostics=None,
                     group_neckdowns=True, link_role="supply"):
    net = owner_pad.GetNetname()
    if net != cap_pad.GetNetname():
        if diagnostics is not None:
            diagnostics.update({
                "schema": 1, "conclusion": "owner_cap_rail_mismatch",
                "owner": _pad_identity(owner_pad),
                "cap": _pad_identity(cap_pad)})
        return None, "owner/cap rail mismatch"
    direct = math.hypot(
        owner_pad.GetPosition().x - cap_pad.GetPosition().x,
        owner_pad.GetPosition().y - cap_pad.GetPosition().y) / MM
    path_before = _shortest_track_path_mm(board, owner_pad, cap_pad)
    common = sorted(
        set(owner_pad.GetLayerSet().CuStack()) &
        set(cap_pad.GetLayerSet().CuStack()))
    if not common:
        if diagnostics is not None:
            diagnostics.update({
                "schema": 1, "conclusion": "no_common_copper_layer",
                "owner": _pad_identity(owner_pad),
                "cap": _pad_identity(cap_pad)})
        return None, "owner/cap have no common copper layer"
    spec = _netclass(board, net)
    try:
        board_min = board.GetDesignSettings().m_TrackMinWidth
    except Exception:                                    # noqa: BLE001
        board_min = pcbnew.FromMM(0.20)
    # The electrical class owns the body of the link.  A previous version used
    # half the smaller endpoint land as the width of the *entire* route.  That
    # made a fine-pitch bypass connection turn a multi-amp rail into a long,
    # locked bottleneck.  Keep only a bounded endpoint escape narrow and
    # require a class-width throat between the lands, matching final signoff.
    width = max(int(board_min), int(spec["width"]))
    clearance = max(pcbnew.FromMM(0.20), int(spec["clearance"]))
    local_limit = _local_supply_limit_mm(
        direct, width / MM, clearance / MM)
    if path_before is not None and path_before <= local_limit + 1e-9:
        return {
            "status": "covered-local", "items": [],
            "length_mm": round(path_before, 3),
            "direct_mm": round(direct, 3),
            "max_local_mm": round(local_limit, 3),
        }, None

    def escape(pad):
        try:
            if int(pad.GetAttribute()) != int(pcbnew.PAD_ATTRIB_SMD):
                return None
        except Exception:                                # noqa: BLE001
            return None
        minor = min(pad.GetSize().x, pad.GetSize().y)
        if minor >= width:
            return None
        local_width = min(width, max(int(board_min), minor // 2))
        budget = pcbnew.FromMM(max(0.6, min(1.5, 1.5 * width / MM)))
        return local_width, budget

    start_escape = escape(owner_pad)
    end_escape = escape(cap_pad)
    locality_rejections = []

    def _legs_length_mm(legs):
        return sum(math.hypot(b.x - a.x, b.y - a.y) / MM
                   for a, b, _leg_width in legs)

    def _ops_length_mm(ops):
        return sum(math.hypot(op[2].x - op[1].x,
                              op[2].y - op[1].y) / MM
                   for op in (ops or ()) if op[0] != "via")

    def _within_locality(kind, candidate_length):
        if candidate_length <= local_limit + 1e-9:
            return True
        locality_rejections.append({
            "kind": kind,
            "length_mm": round(candidate_length, 3),
            "max_local_mm": round(local_limit, 3),
        })
        return False

    net_code = owner_pad.GetNetCode()
    start, end = owner_pad.GetPosition(), cap_pad.GetPosition()
    for layer in common:
        path = cec_fr._guarded_profiled_lastmile_legs(
            board, start, end, width, layer, clearance, net_code,
            lambda a, b, half: cec_fr._edge_leg_clear(
                board, a, b, half),
            start_escape=start_escape,
            end_escape=end_escape)
        if not path:
            continue
        path_length = _legs_length_mm(path)
        if not _within_locality("same-layer", path_length):
            continue
        items = []
        for a, b, leg_width in path:
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(a); track.SetEnd(b)
            track.SetWidth(leg_width); track.SetLayer(layer)
            track.SetNetCode(net_code); track.SetLocked(bool(lock))
            board.Add(track); items.append(track)
        endpoint_neckdown = (_group_endpoint_neckdowns(board, items, width)
                             if group_neckdowns else None)
        return {
            "status": "linked", "layer": board.GetLayerName(layer),
            "width_mm": round(width / MM, 3),
            "neckdown_widths_mm": sorted({
                round(item.GetWidth() / MM, 3) for item in items
                if item.GetWidth() < width}),
            "length_mm": round(path_length, 3),
            "endpoint_neckdown": endpoint_neckdown,
            "items": items,
            "direct_mm": round(direct, 3),
            "max_local_mm": round(local_limit, 3),
        }, None

    # Adjacent fine-pitch power pins can be individually escapable yet unable
    # to support two class-width face-layer throats at once.  The generic
    # last-mile engine already owns a guarded two-via bridge for exactly that
    # topology; use it here with the *assigned* owner/cap pair rather than
    # falling back to the older nearest-load heuristic.  Plane layers are
    # excluded from routing, via geometry satisfies both netclass and board
    # minima, and every stub/via/inner leg receives the same edge and foreign-
    # copper checks as the same-layer path above.
    all_cu = set(board.GetEnabledLayers().CuStack())
    plane_ids = {board.GetLayerID(name) for name in cec_fr.plane_layers(board)}
    plane_ids.discard(-1)
    bridge_layers = [
        layer for layer in all_cu
        if layer not in set(common) and layer not in plane_ids
        and not any(role in board.GetLayerName(layer).upper()
                    for role in ("GND", "PWR"))]
    bridge_layers.sort(key=lambda layer: (
        0 if "SIG" in board.GetLayerName(layer).upper() else
        1 if board.GetLayerName(layer).upper().startswith("IN") else
        2 if layer == pcbnew.B_Cu else 3,
        layer))
    diameter, drill, board_limits = _board_legal_through_via_geometry(
        board, float(spec["via_dia"]), float(spec["via_drill"]))
    ops = None
    bridge_meta = None
    bridge_mode = None

    if bridge_layers:
        ops, bridge_meta = _pofv_supply_bridge_ops(
            board, owner_pad, cap_pad, width, clearance, net_code,
            bridge_layers, spec)
        if ops and _within_locality(
                "via-in-pad-bridge", _ops_length_mm(ops)):
            bridge_mode = "via-in-pad-bridge"
        else:
            ops = None
            bridge_meta = None
            ops = cec_fr._lastmile_bridge(
                board, (start.x, start.y),
                set(owner_pad.GetLayerSet().CuStack()),
                (end.x, end.y), set(cap_pad.GetLayerSet().CuStack()),
                width, net_code, bridge_layers, clearance,
                drill=drill, dia=diameter, seat_limit=48,
                leg_ok=lambda a, b, half: cec_fr._edge_leg_clear(
                    board, a, b, half),
                start_escape=start_escape, end_escape=end_escape,
                allow_maze=True, maze_margin_mm=2.0)
            if ops and _within_locality("via-bridge", _ops_length_mm(ops)):
                bridge_mode = "via-bridge"
            else:
                ops = None
    if ops:
        items = []
        used_layers = set()
        neckdowns = set()
        copper_length = 0.0
        via_count = 0
        via_diameters = []
        via_drills = []
        for op in ops:
            if op[0] == "via":
                _, at, op_drill, op_diameter = op
                item = pcbnew.PCB_VIA(board)
                item.SetPosition(at)
                item.SetDrill(pcbnew.FromMM(op_drill))
                item.SetWidth(pcbnew.FromMM(op_diameter))
                item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                item.SetNetCode(net_code); item.SetLocked(bool(lock))
                board.Add(item); items.append(item); via_count += 1
                via_diameters.append(float(op_diameter))
                via_drills.append(float(op_drill))
                continue
            _, a, b, leg_width, layer = op
            item = pcbnew.PCB_TRACK(board)
            item.SetStart(a); item.SetEnd(b)
            item.SetWidth(leg_width); item.SetLayer(layer)
            item.SetNetCode(net_code); item.SetLocked(bool(lock))
            board.Add(item); items.append(item); used_layers.add(layer)
            copper_length += math.hypot(
                b.x - a.x, b.y - a.y) / MM
            if leg_width < width:
                neckdowns.add(round(leg_width / MM, 3))
        endpoint_neckdown = (_group_endpoint_neckdowns(board, items, width)
                             if group_neckdowns else None)
        return {
            "status": bridge_mode or "via-bridge",
            "layers": [board.GetLayerName(layer)
                       for layer in sorted(used_layers)],
            "width_mm": round(width / MM, 3),
            "neckdown_widths_mm": sorted(neckdowns),
            "length_mm": round(copper_length, 3),
            "vias": via_count,
            "via_diameter_mm": round(max(via_diameters), 3),
            "via_drill_mm": round(max(via_drills), 3),
            "board_limits": ((bridge_meta or {}).get("board_limits")
                             or board_limits),
            "via_in_pad": bridge_mode == "via-in-pad-bridge",
            "fab_profile": ((bridge_meta or {}).get("fab_profile")),
            "qualified_process_exception": bool(
                (bridge_meta or {}).get("qualified_process_exception")),
            "endpoint_limited_local_via": bool(
                (bridge_meta or {}).get("endpoint_limited_local_via")),
            "endpoint_modes": ((bridge_meta or {}).get("endpoint_modes")),
            "endpoint_neckdown": endpoint_neckdown,
            "items": items,
            "direct_mm": round(direct, 3),
            "max_local_mm": round(local_limit, 3),
        }, None

    # A shared GND entry is a different electrical primitive from a rail
    # trunk.  Fine-pitch owner pads can be narrower than the GND netclass and
    # may sit between adjacent package pins, so insisting on class width for
    # the entire owner-to-capacitor link can make a physically sound local
    # return impossible.  Only this explicitly requested role may use a
    # bounded, full-cell neckdown, and only after the ordinary class-width and
    # guarded multilayer searches above have both failed.  The resulting
    # copper is still clearance-checked by the same last-mile engine, remains
    # inside the existing locality bound, and is placed in the named endpoint
    # exception group for exact DRC visibility.
    if link_role == "shared-ground-entry":
        endpoint_minor = min(
            owner_pad.GetSize().x, owner_pad.GetSize().y,
            cap_pad.GetSize().x, cap_pad.GetSize().y)
        local_width = min(width, max(int(board_min), int(endpoint_minor)))
        if local_width < width:
            for layer in common:
                path = cec_fr._guarded_profiled_lastmile_legs(
                    board, start, end, local_width, layer, clearance,
                    net_code,
                    lambda a, b, half: cec_fr._edge_leg_clear(
                        board, a, b, half))
                if not path:
                    continue
                path_length = _legs_length_mm(path)
                if not _within_locality(
                        "shared-ground-neckdown", path_length):
                    continue
                items = []
                for a, b, leg_width in path:
                    item = pcbnew.PCB_TRACK(board)
                    item.SetStart(a); item.SetEnd(b)
                    item.SetWidth(leg_width); item.SetLayer(layer)
                    item.SetNetCode(net_code); item.SetLocked(bool(lock))
                    board.Add(item); items.append(item)
                endpoint_neckdown = (
                    _group_endpoint_neckdowns(board, items, width)
                    if group_neckdowns else None)
                return {
                    "status": "shared-ground-neckdown",
                    "role": link_role,
                    "layer": board.GetLayerName(layer),
                    "width_mm": round(local_width / MM, 3),
                    "class_width_mm": round(width / MM, 3),
                    "length_mm": round(path_length, 3),
                    "endpoint_neckdown": endpoint_neckdown,
                    "items": items,
                    "direct_mm": round(direct, 3),
                    "max_local_mm": round(local_limit, 3),
                }, None
    if diagnostics is not None:
        certificate = cec_fr._lastmile_refusal_certificate(
            board, start, end, width, clearance, net_code,
            sorted(set(common) | set(bridge_layers)),
            endpoint_a=_pad_identity(owner_pad),
            endpoint_b=_pad_identity(cap_pad), maze_searched=True,
            maze_margin_mm=2.0, start_escape=start_escape,
            end_escape=end_escape)
        certificate["search"]["via_bridge"] = bool(bridge_layers)
        certificate["search"]["via_bridge_layers"] = [
            board.GetLayerName(layer) for layer in bridge_layers]
        certificate["locality"] = {
            "direct_mm": round(direct, 3),
            "max_local_mm": round(local_limit, 3),
            "rejected_candidates": locality_rejections,
        }
        diagnostics.update(certificate)
    return None, "no guarded local supply path within locality bound"


def audit_supply_access_board(board, *, max_assignment_mm=3.5):
    """Prove each selected bypass cell has a legal local rail launch.

    This is a read-only placement oracle even though it reuses the exact
    generator: every trial segment is removed immediately.  A distance-only
    bypass check can pass while foreign pads or package geometry make the
    owner-to-cap link impossible; discovering that after global routing is too
    late for a professional flow.  Reusing ``_add_supply_link`` keeps the
    preflight and eventual copper construction identical by construction.
    """
    assignment = cec_constraints._device_bypass_assignment(
        board, project_max_mm=max_assignment_mm)
    rows = []
    for missing in assignment.get("missing") or ():
        rows.append(_missing_assignment_report(missing))
    for assigned in assignment.get("assigned", {}).values():
        requirement = assigned["requirement"]
        cap = board.FindFootprintByReference(assigned.get("cap_ref"))
        cap_rail = next(
            (pad for pad in cap.Pads()
             if pad.GetNetname() == requirement.get("rail")), None) \
            if cap else None
        row = {
            "owner": requirement.get("ref"),
            "pin": requirement.get("pin"),
            "rail": requirement.get("rail"),
            "cap": assigned.get("cap_ref"),
            "placement_distance_mm": round(
                float(assigned.get("distance_mm") or 0.0), 3),
        }
        if requirement.get("pad") is None or cap_rail is None:
            row.update({"status": "refused",
                        "reason": "missing owner or capacitor rail pad"})
            rows.append(row)
            continue
        before = {item.m_Uuid.AsString() for item in board.GetTracks()}
        diagnostic = {}
        supply, error = _add_supply_link(
            board, requirement["pad"], cap_rail, lock=True,
            diagnostics=diagnostic, group_neckdowns=False)
        generated = [
            item for item in list(board.GetTracks())
            if item.m_Uuid.AsString() not in before]
        for item in generated:
            board.Remove(item)
        row.update({
            "status": "accessible" if error is None else "refused",
            "reason": error,
            "supply": ({key: value for key, value in supply.items()
                        if key != "items"} if supply else None),
            "trial_item_count": len(generated),
            "certificate": diagnostic or None,
        })
        rows.append(row)
    refused = [row for row in rows if row.get("status") == "refused"]
    return {
        "schema": 1, "ok": not refused,
        "requirements": len(assignment.get("requirements") or ()),
        "accessible": len(rows) - len(refused),
        "refused": refused, "cells": rows,
    }


def supply_access_reservations_board(board, *, max_assignment_mm=3.5,
                                     ground_reach_mm=1.5):
    """Return exact, read-only copper primitives for future bypass cells.

    Broad power objects are planned before the local PI materializer, but that
    ordering must not let a pour consume the only legal supply bridge,
    capacitor GND return, owner GND return, or shared-entry via column.  Run
    the *same collective, all-or-nothing synthesizer* used by production,
    serialize its exact track/via geometry, then remove every trial item.
    Pour planning can reserve the complete cells without guessing at a
    component-sized halo or baking in a board-specific coordinate.

    The historical function name is retained for API compatibility; its
    contract now deliberately covers the complete local PI cell.
    """
    assignment = cec_constraints._device_bypass_assignment(
        board, project_max_mm=max_assignment_mm)
    before = {item.m_Uuid.AsString() for item in board.GetTracks()}
    report = synthesize_board(
        board, board_path=getattr(board, "GetFileName", lambda: "")(),
        max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm, lock=True,
        assignment=assignment, group_neckdowns=False)
    ground_report = synthesize_ground_plane_access_board(
        board, board_path=getattr(board, "GetFileName", lambda: "")(),
        reach_mm=ground_reach_mm, lock=True,
        group_neckdowns=False)
    generated = [item for item in list(board.GetTracks())
                 if item.m_Uuid.AsString() not in before]
    provenance = {
        row.get("uuid"): row
        for row in report.get("generated_items") or () if row.get("uuid")}
    # The global GND-portal pass runs after the bypass-cell pass and therefore
    # contributes generated vias/tracks that are absent from the first
    # provenance table.  Preserve their owning footprint/pad explicitly.  A
    # lost owner used to become ``?`` in the pour planner, creating a real
    # future-copper obstacle that placement could neither identify nor move.
    for terminal in ground_report.get("terminals") or ():
        owner = str(terminal.get("ref") or "")
        if not owner:
            continue
        for uuid in terminal.get("generated_item_uuids") or ():
            provenance.setdefault(uuid, {
                "uuid": uuid,
                "owner": owner,
                "cap": None,
                "pad": str(terminal.get("pad") or ""),
                "purpose": "ground_plane_access",
            })
    primitives = []
    try:
        for item in generated:
            source = provenance.get(item.m_Uuid.AsString(), {})
            common = {
                "net": item.GetNetname(),
                "net_code": int(item.GetNetCode()),
                "owner": source.get("owner"),
                "cap": source.get("cap"),
                "pad": source.get("pad"),
                "purpose": source.get("purpose", "bypass_cell"),
            }
            if item.GetClass() == "PCB_VIA":
                at = item.GetPosition()
                primitives.append(dict(
                    common, kind="via",
                    at_mm=[at.x / MM, at.y / MM],
                    diameter_mm=item.GetWidth(pcbnew.F_Cu) / MM,
                    drill_mm=item.GetDrillValue() / MM,
                    layer_ids=sorted(
                        int(layer) for layer in item.GetLayerSet().CuStack())))
            else:
                start, end = item.GetStart(), item.GetEnd()
                primitives.append(dict(
                    common, kind="track", layer_id=int(item.GetLayer()),
                    start_mm=[start.x / MM, start.y / MM],
                    end_mm=[end.x / MM, end.y / MM],
                    width_mm=item.GetWidth() / MM))
    finally:
        for item in generated:
            board.Remove(item)
    result = _report_only(report)
    result.update({
        "ok": bool(report.get("ok") and ground_report.get("ok")),
        "read_only": True,
        "trial_item_count": len(generated),
        "primitives": primitives,
        "ground_access": _report_only(ground_report),
        "refused": (list(report.get("refused") or ()) + [{
            **row, "stage": "ground_plane_access"}
            for row in ground_report.get("refused") or ()]),
    })
    return result


def _reservation_file_worker(board_path, report_path, *, max_assignment_mm,
                             ground_reach_mm):
    board = pcbnew.LoadBoard(board_path)
    report = supply_access_reservations_board(
        board, max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm)
    with open(report_path, "w", encoding="utf-8") as sink:
        json.dump(report, sink, indent=2, sort_keys=True)


def supply_access_reservations_file(board_path, *, max_assignment_mm=3.5,
                                    ground_reach_mm=1.5, timeout=180):
    """Probe complete-cell reservations in a disposable pcbnew process.

    Removing trial tracks invalidates child proxies in KiCad's deprecated
    SWIG API.  A planner that keeps using that BOARD can consequently fault
    during an unrelated later operation.  The file boundary makes rollback
    literal (the source is never saved) and exits without running unsafe SWIG
    finalizers after the JSON evidence is durable.
    """
    fd, report_path = tempfile.mkstemp(
        prefix="cec-cell-reservations-", suffix=".json",
        dir=os.path.dirname(os.path.abspath(board_path)))
    os.close(fd)
    command = [
        sys.executable, os.path.abspath(__file__), "--reservation-worker",
        "--board", os.path.abspath(board_path), "--report", report_path,
        "--max-assignment-mm", str(float(max_assignment_mm)),
        "--ground-reach-mm", str(float(ground_reach_mm)),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=float(timeout))
        if completed.returncode:
            raise RuntimeError(
                "cell reservation worker exited %d: %s" % (
                    completed.returncode,
                    (completed.stderr or completed.stdout or
                     "no diagnostic")[-1600:]))
        with open(report_path, encoding="utf-8") as source:
            return json.load(source)
    finally:
        try:
            os.unlink(report_path)
        except OSError:
            pass


def _existing_return(board, pad, reach_mm):
    board.BuildConnectivity()
    connected = {
        item.m_Uuid.AsString()
        for item in board.GetConnectivity().GetConnectedItems(pad)}
    pos = pad.GetPosition()
    candidates = []
    for item in board.GetTracks():
        if (item.GetClass() != "PCB_VIA" or item.GetNetname() != "GND"
                or item.m_Uuid.AsString() not in connected):
            continue
        at = item.GetPosition()
        distance = math.hypot(at.x - pos.x, at.y - pos.y) / MM
        if distance <= reach_mm + 1e-9:
            candidates.append((distance, item))
    return min(candidates, default=None, key=lambda row: row[0])


def _shared_ground_return(board, pad, portal_pad, reach_mm):
    """Prove a bounded explicit-copper path to a peer's local GND via.

    The cell generator can legitimately use one qualified via for two nearby
    ground lands when a guarded same-net link joins them.  Final audit used to
    forget that topology and demanded a second via inside ``reach_mm`` of the
    linked land.  Keep this proof deliberately stricter than global
    connectivity: zones are excluded, the peer must itself own an immediate
    via, and the visible track path must fit the same bounded-locality rule
    used by the generator.
    """
    portal_return = _existing_return(board, portal_pad, reach_mm)
    if portal_return is None:
        return None
    direct = math.hypot(
        pad.GetPosition().x - portal_pad.GetPosition().x,
        pad.GetPosition().y - portal_pad.GetPosition().y) / MM
    path = _shortest_track_path_mm(board, pad, portal_pad)
    spec = _netclass(board, "GND")
    local_limit = _local_supply_limit_mm(
        direct, float(spec["width"]) / MM,
        max(pcbnew.FromMM(0.20), int(spec["clearance"])) / MM)
    if path is None or path > local_limit + 1e-9:
        return None
    return {
        "status": "shared-ground-entry",
        "path_mm": round(path, 3),
        "direct_mm": round(direct, 3),
        "max_local_mm": round(local_limit, 3),
        "portal_via_distance_mm": round(portal_return[0], 3),
        "via_uuid": portal_return[1].m_Uuid.AsString(),
        "shared_with": _pad_identity(portal_pad),
    }


def _add_ground_return(board, pad, *, board_path, reach_mm, lock):
    covered = _existing_return(board, pad, reach_mm)
    if covered is not None:
        existing_via = covered[1]
        blocking, _allowed = cec_fab_profile.via_at_pad_conflicts(
            board, existing_via.GetPosition(),
            existing_via.GetWidth(pcbnew.F_Cu),
            existing_via.GetDrillValue(), existing_via.GetNetCode())
        if blocking is not None:
            return None, (
                "existing immediate GND return is not fabrication-qualified: "
                "%s" % blocking)
        return {
            "status": "covered", "distance_mm": round(covered[0], 3),
            "via_uuid": existing_via.m_Uuid.AsString(), "items": [],
        }, None
    gnd_code = pad.GetNetCode()
    pos = pad.GetPosition()
    layer = pad.GetLayer()
    profile_name = cec_fab_profile.active_profile_name(
        board, hint=board_path)
    profile = (cec_fab_profile.get_profile(profile_name)
               if profile_name else None)
    pofv = cec_fab_profile.preferred_pofv_geometry(profile)
    pofv_refusal = "board has no declared POFV profile"
    if pofv:
        requested_diameter, requested_drill = pofv
        ordinary_diameter, ordinary_drill, board_limits = \
            _board_legal_through_via_geometry(
                board, requested_diameter, requested_drill)
        # A profile-qualified, filled/capped via that is wholly contained by
        # its same-net endpoint pad is not an ordinary off-pad through via.
        # Keep the declared POFV geometry here, exactly as the supply-side
        # endpoint bridge does.  The spot/fabrication checks below admit it
        # only with exact process dimensions and full same-net containment;
        # any dogbone fallback still uses the ordinary board-legal geometry.
        diameter, drill = requested_diameter, requested_drill
        process_ok, process_reason = cec_fab_profile.pofv_dimensions(
            profile, diameter, drill)
        edge_clear = cec_fr._edge_leg_clear(
            board, pos, pos, pcbnew.FromMM(diameter) // 2)
        hole_clear, hole_conflicts = _hole_to_hole_clear(
            board, pos, drill)
        spot_clear = process_ok and cec_fr._via_spot_clear(
            board, pos, pcbnew.FromMM(diameter),
            pcbnew.FromMM(0.20), {gnd_code},
            drill_nm=pcbnew.FromMM(drill),
            net_code=gnd_code, contained_layers={layer})
        if process_ok and edge_clear and hole_clear and spot_clear:
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pos)
            via.SetDrill(pcbnew.FromMM(drill))
            via.SetWidth(pcbnew.FromMM(diameter))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNetCode(gnd_code); via.SetLocked(bool(lock))
            board.Add(via)
            return {
                "status": "via-in-pad", "distance_mm": 0.0,
                "via_uuid": via.m_Uuid.AsString(), "items": [via],
                "fab_profile": profile_name,
                "diameter_mm": round(diameter, 3),
                "drill_mm": round(drill, 3),
                "requested_diameter_mm": round(requested_diameter, 3),
                "requested_drill_mm": round(requested_drill, 3),
                "endpoint_limited_local_via": True,
                "qualified_process_exception": bool(
                    diameter + 1e-9 < ordinary_diameter
                    or drill + 1e-9 < ordinary_drill),
                "board_limits": board_limits,
            }, None
        if not process_ok:
            pofv_refusal = process_reason
        elif not edge_clear:
            pofv_refusal = "board-edge clearance blocks the pad center"
        elif not hole_clear:
            pofv_refusal = "drill clearance blocks the pad center: %s" % (
                hole_conflicts[:2],)
        else:
            pofv_refusal = "pad-center via barrel or land is obstructed"

    spec = _netclass(board, "GND")
    diameter, drill, board_limits = _board_legal_through_via_geometry(
        board, max(0.6, float(spec["via_dia"])),
        max(0.3, float(spec["via_drill"])))
    pad_minor = min(pad.GetSize().x, pad.GetSize().y) / MM
    try:
        board_min = board.GetDesignSettings().m_TrackMinWidth / MM
    except Exception:                                    # noqa: BLE001
        board_min = 0.20
    stub_width = min(0.30, max(board_min, pad_minor / 2.0))
    start_radius = max(
        0.45, pad_minor / 2.0 + diameter / 2.0 + 0.20)
    radii = sorted({
        round(value, 3) for value in
        (start_radius, start_radius + 0.20, start_radius + 0.40,
         min(reach_mm, start_radius + 0.65))
        if value <= reach_mm + 1e-9})
    tested_sites = 0
    dogbone_rejections = {
        "stub_foreign_clearance": 0,
        "stub_edge_clearance": 0,
        "via_edge_clearance": 0,
        "via_spot_clearance": 0,
        "via_pad_qualification": 0,
        "via_hole_clearance": 0,
        "stub_pair_overlap": 0,
    }
    for radius in radii:
        for angle_deg in (0, 180, 90, 270, 45, 135, 225, 315,
                          22.5, 67.5, 112.5, 157.5,
                          202.5, 247.5, 292.5, 337.5):
            angle = math.radians(angle_deg)
            at = pcbnew.VECTOR2I(
                int(round(pos.x + math.cos(angle) * radius * MM)),
                int(round(pos.y + math.sin(angle) * radius * MM)))
            tested_sites += 1
            checks = (
                ("stub_foreign_clearance", cec_fr._tap_foreign_clear(
                    board, pos, at, pcbnew.FromMM(stub_width),
                    layer, pcbnew.FromMM(0.20), {gnd_code})),
                ("stub_edge_clearance", cec_fr._edge_leg_clear(
                    board, pos, at, pcbnew.FromMM(stub_width) // 2)),
                ("via_edge_clearance", cec_fr._edge_leg_clear(
                    board, at, at, pcbnew.FromMM(diameter) // 2)),
                ("via_spot_clearance", cec_fr._via_spot_clear(
                    board, at, pcbnew.FromMM(diameter),
                    pcbnew.FromMM(0.20), {gnd_code},
                    drill_nm=pcbnew.FromMM(drill), net_code=gnd_code)),
                # Same-net copper is exempt from the ordinary spot-clearance
                # guard, but a standard dogbone barrel may still graze the
                # edge of its source pad.  That is neither a legal separated
                # dogbone nor a fully-contained, profile-qualified POFV seat.
                # Apply the fabrication authority at the materialization
                # boundary so every generated via is in exactly one class.
                ("via_pad_qualification",
                 cec_fab_profile.via_at_pad_conflicts(
                     board, at, pcbnew.FromMM(diameter),
                     pcbnew.FromMM(drill), gnd_code)[0] is None),
                ("via_hole_clearance", _hole_to_hole_clear(
                    board, at, drill)[0]),
                ("stub_pair_overlap", cec_fr._tap_pair_overlap_clear(
                    board, pos, at, pcbnew.FromMM(stub_width),
                    layer, gnd_code, set())),
            )
            failed = [name for name, ok in checks if not ok]
            if failed:
                for name in failed:
                    dogbone_rejections[name] += 1
                continue
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(at)
            via.SetDrill(pcbnew.FromMM(drill))
            via.SetWidth(pcbnew.FromMM(diameter))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNetCode(gnd_code); via.SetLocked(bool(lock))
            board.Add(via)
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(pos); track.SetEnd(at)
            track.SetWidth(pcbnew.FromMM(stub_width))
            track.SetLayer(layer); track.SetNetCode(gnd_code)
            track.SetLocked(bool(lock)); board.Add(track)
            return {
                "status": "dogbone", "distance_mm": round(radius, 3),
                "via_uuid": via.m_Uuid.AsString(),
                "items": [track, via], "fab_profile": profile_name,
                "diameter_mm": round(diameter, 3),
                "drill_mm": round(drill, 3),
                "board_limits": board_limits,
            }, None
    return None, (
        "no legal immediate GND return: via-in-pad %s; "
        "%d dogbone sites rejected (%s)" %
        (pofv_refusal, tested_sites, ", ".join(
            "%s=%d" % pair for pair in dogbone_rejections.items()
            if pair[1])))


def _add_ground_return_pair(board, owner_pad, cap_pad, *, board_path,
                            reach_mm, lock, group_neckdowns=True):
    """Give both local GND pads an immediate entry, sharing one when needed.

    Fine-pitch IC ground lands often cannot physically contain the board-legal
    POFV diameter and can be boxed in by adjacent pins.  When either the owner
    or capacitor pad has a legal immediate via, a short guarded same-net link
    to that via is a lower-inductance and manufacturable fallback.  Both
    independent-via and shared-entry forms remain all-or-nothing at the caller.
    """
    before = {item.m_Uuid.AsString() for item in board.GetTracks()}

    def attempt(cap_first):
        order = (("cap", cap_pad), ("owner", owner_pad)) if cap_first else (
            ("owner", owner_pad), ("cap", cap_pad))
        result = {}
        errors = {}
        for name, pad in order:
            result[name], errors[name] = _add_ground_return(
                board, pad, board_path=board_path,
                reach_mm=reach_mm, lock=lock)
        if errors["owner"] is None and errors["cap"] is None:
            return result["owner"], result["cap"], None, None

        link_error = None
        if (errors["owner"] is None) != (errors["cap"] is None):
            ground_link, link_error = _add_supply_link(
                board, owner_pad, cap_pad, lock=lock,
                group_neckdowns=group_neckdowns,
                link_role="shared-ground-entry")
            if link_error is None:
                # The guarded direct link is itself the missing pad's proof of
                # access to the already-qualified local via.  Re-probing for a
                # second via made success depend on the via centre also being
                # inside ``reach_mm`` (1.503 mm was rejected against 1.500 mm)
                # even though the short visible copper path had just passed
                # the stricter local-link guard.  Record the shared portal
                # explicitly instead of demanding redundant barrels.
                covered_name = ("owner" if errors["owner"] is None
                                else "cap")
                shared_name = "cap" if covered_name == "owner" else "owner"
                covered = result[covered_name] or {}
                result[shared_name] = {
                    "status": "shared-ground-entry",
                    "distance_mm": ground_link.get("length_mm"),
                    "via_uuid": covered.get("via_uuid"),
                    "shared_with": covered_name,
                    "items": [],
                }
                errors[shared_name] = None
                clean_link = {
                    key: value for key, value in ground_link.items()
                    if key != "items"}
                clean_link["status"] = "shared-ground-entry"
                clean_link["seat_order"] = (
                    "capacitor-first" if cap_first else "owner-first")
                clean_link["portal_owner"] = covered_name
                return (result["owner"], result["cap"],
                        clean_link, None)
            else:
                link_error = "guarded shared-entry link: %s" % link_error
        else:
            link_error = "neither pad has a legal immediate via"
        reasons = []
        if errors["owner"]:
            reasons.append("owner GND: %s" % errors["owner"])
        if errors["cap"]:
            reasons.append("capacitor GND: %s" % errors["cap"])
        if link_error:
            reasons.append(link_error)
        return (result.get("owner"), result.get("cap"), None,
                "; ".join(reasons))

    owner_first = attempt(False)
    if owner_first[3] is None:
        return owner_first

    # Ground entries are a coupled cell.  A greedy first via can consume the
    # only barrel seat available to the other pad even though the reverse
    # ordering closes both.  Roll back only this pair's trial copper and prove
    # the reciprocal order before declaring a geometric refusal.
    for item in list(board.GetTracks()):
        if item.m_Uuid.AsString() not in before:
            board.Remove(item)
    board.BuildConnectivity()
    cap_first = attempt(True)
    if cap_first[3] is None:
        if cap_first[2] is None:
            cap_first = (cap_first[0], cap_first[1], {
                "status": "independent-ground-entries",
                "seat_order": "capacitor-first",
            }, None)
        return cap_first
    return (cap_first[0], cap_first[1], None,
            "owner-first failed: %s; capacitor-first failed: %s" %
            (owner_first[3], cap_first[3]))


def _report_only(value):
    """Remove live pcbnew objects from persistent/inter-process evidence.

    Generator return dictionaries use ``items`` internally for transactional
    rollback.  Those SWIG objects are neither deterministic evidence nor
    picklable, and must never cross a worker or JSON boundary.
    """
    if isinstance(value, dict):
        return {
            key: _report_only(item)
            for key, item in value.items() if key != "items"
        }
    if isinstance(value, list):
        return [_report_only(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_report_only(item) for item in value)
    return value


def _point_segment_distance_mm(point, start, end):
    px, py = point.x / MM, point.y / MM
    ax, ay = start.x / MM, start.y / MM
    bx, by = end.x / MM, end.y / MM
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    if span <= 1e-18:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / span))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _segments_distance_mm(a, b, c, d):
    """Exact minimum centreline distance between two finite segments."""
    def orient(p, q, r):
        return ((q.x - p.x) * (r.y - p.y) -
                (q.y - p.y) * (r.x - p.x))

    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    if ((o1 == 0 or o2 == 0 or (o1 < 0) != (o2 < 0)) and
            (o3 == 0 or o4 == 0 or (o3 < 0) != (o4 < 0))):
        return 0.0
    return min(
        _point_segment_distance_mm(a, c, d),
        _point_segment_distance_mm(b, c, d),
        _point_segment_distance_mm(c, a, b),
        _point_segment_distance_mm(d, a, b),
    )


def ripup_foreign_local_copper(board, *, max_assignment_mm=3.5,
                               ground_reach_mm=1.5,
                               protected_nets=(), demotable_nets=(),
                               assignment=None):
    """Clear only unlocked, non-priority copper from bypass-cell channels.

    This is used solely when continuing a previously routed seed.  Component
    geometry is unchanged; old ordinary routing is allowed to surrender the
    small supply/return neighborhood so the priority cell can be rebuilt
    first.  Locked nets, explicitly protected nets, same-cell GND/rail copper,
    and wide current trunks are never removed.  The residual router owns the
    exact named nets removed here.
    """
    assignment = assignment or cec_constraints._device_bypass_assignment(
        board, project_max_mm=max_assignment_mm)
    demotable = set(demotable_nets or ())
    protected = set(protected_nets or ()) - demotable
    protected.update(
        item.GetNetname() for item in board.GetTracks()
        if (item.IsLocked() and item.GetNetname()
            and item.GetNetname() not in demotable))
    regions = []
    for assigned in assignment.get("assigned", {}).values():
        requirement = assigned["requirement"]
        cap = board.FindFootprintByReference(assigned.get("cap_ref"))
        owner = board.FindFootprintByReference(requirement.get("ref"))
        if cap is None or owner is None or requirement.get("pad") is None:
            continue
        cap_rail = next((pad for pad in cap.Pads()
                         if pad.GetNetname() == requirement.get("rail")), None)
        cap_gnd = next((pad for pad in cap.Pads()
                        if pad.GetNetname() == "GND"), None)
        owner_gnds = [pad for pad in owner.Pads()
                      if pad.GetNetname() == "GND"]
        if cap_rail is None or cap_gnd is None or not owner_gnds:
            continue
        owner_gnd = min(owner_gnds, key=lambda pad: math.hypot(
            pad.GetPosition().x - cap_gnd.GetPosition().x,
            pad.GetPosition().y - cap_gnd.GetPosition().y))
        regions.append({
            "owner": requirement.get("ref"),
            "cap": assigned.get("cap_ref"),
            "allowed_nets": {"GND", requirement.get("rail")},
            "ground_points": (
                owner_gnd.GetPosition(), cap_gnd.GetPosition()),
            "supply_segment": (
                requirement["pad"].GetPosition(),
                cap_rail.GetPosition()),
        })

    selected = []
    blocked = []
    ground_radius = min(2.0, max(0.9, float(ground_reach_mm) + 0.35))
    supply_radius = 0.45
    for item in list(board.GetTracks()):
        net = item.GetNetname()
        if not net:
            continue
        if (item.IsLocked() and net not in demotable) or net in protected:
            continue
        try:
            item_radius = (item.GetWidth(pcbnew.F_Cu)
                           if item.GetClass() == "PCB_VIA" else
                           item.GetWidth()) / MM / 2.0
        except Exception:                               # noqa: BLE001
            item_radius = 0.30
        hit = None
        for region in regions:
            if net in region["allowed_nets"]:
                continue
            if item.GetClass() == "PCB_VIA":
                point = item.GetPosition()
                close_ground = any(
                    math.hypot(point.x - ground.x,
                               point.y - ground.y) / MM
                    <= ground_radius + item_radius
                    for ground in region["ground_points"])
                close_supply = _point_segment_distance_mm(
                    point, *region["supply_segment"]
                ) <= supply_radius + item_radius
            else:
                start, end = item.GetStart(), item.GetEnd()
                close_ground = any(
                    _point_segment_distance_mm(ground, start, end)
                    <= ground_radius + item_radius
                    for ground in region["ground_points"])
                close_supply = _segments_distance_mm(
                    start, end, *region["supply_segment"]
                ) <= supply_radius + item_radius
            if close_ground or close_supply:
                hit = region
                break
        if hit is None:
            continue
        # A wide current trunk is placement authority, not ordinary residual
        # routing.  Report it but never silently tear it up.
        if item.GetClass() != "PCB_VIA" and item.GetWidth() >= pcbnew.FromMM(1.0):
            blocked.append({
                "uuid": item.m_Uuid.AsString(), "net": net,
                "kind": item.GetClass(), "owner": hit["owner"],
                "cap": hit["cap"], "reason": "wide_current_trunk",
            })
            continue
        selected.append((item, hit))

    removed = []
    for item, region in selected:
        removed.append({
            "uuid": item.m_Uuid.AsString(), "net": item.GetNetname(),
            "kind": item.GetClass(), "owner": region["owner"],
            "cap": region["cap"],
        })
        board.Remove(item)
    return {
        "schema": 1,
        "removed_count": len(removed),
        "removed_items": removed,
        "removed_nets": sorted({row["net"] for row in removed}),
        "protected_nets": sorted(protected),
        "demotable_nets": sorted(demotable),
        "blocked_count": len(blocked),
        "blocked_items": blocked,
        "ground_radius_mm": ground_radius,
        "supply_radius_mm": supply_radius,
    }


def ripup_foreign_ground_access_copper(board, targets, *, reach_mm=1.5,
                                        protected_nets=(),
                                        demotable_nets=()):
    """Clear bounded ordinary copper around named, proven-blocked GND pads."""
    demotable = set(demotable_nets or ())
    protected = set(protected_nets or ()) - demotable
    protected.update(
        item.GetNetname() for item in board.GetTracks()
        if (item.IsLocked() and item.GetNetname()
            and item.GetNetname() not in demotable))
    points = []
    missing = []
    for target in targets or ():
        ref, number = target.get("ref"), str(target.get("pad"))
        footprint = board.FindFootprintByReference(ref)
        pad = footprint.FindPadByNumber(number) if footprint else None
        if pad is None or pad.GetNetname() != "GND":
            missing.append({"ref": ref, "pad": number})
            continue
        points.append((ref, number, pad.GetPosition()))

    radius = min(2.0, max(0.9, float(reach_mm) + 0.35))
    selected, blocked = [], []
    for item in list(board.GetTracks()):
        net = item.GetNetname()
        if (not net or net == "GND"
                or (item.IsLocked() and net not in demotable)
                or net in protected):
            continue
        item_radius = ((item.GetWidth(pcbnew.F_Cu)
                        if item.GetClass() == "PCB_VIA" else
                        item.GetWidth()) / MM / 2.0)
        hit = None
        for ref, number, point in points:
            distance = (math.hypot(
                item.GetPosition().x - point.x,
                item.GetPosition().y - point.y) / MM
                if item.GetClass() == "PCB_VIA" else
                _point_segment_distance_mm(
                    point, item.GetStart(), item.GetEnd()))
            if distance <= radius + item_radius:
                hit = (ref, number)
                break
        if hit is None:
            continue
        if (item.GetClass() != "PCB_VIA" and
                item.GetWidth() >= pcbnew.FromMM(1.0)):
            blocked.append({
                "uuid": item.m_Uuid.AsString(), "net": net,
                "kind": item.GetClass(), "ref": hit[0], "pad": hit[1],
                "reason": "wide_current_trunk",
            })
            continue
        selected.append((item, hit))

    removed = []
    for item, hit in selected:
        removed.append({
            "uuid": item.m_Uuid.AsString(), "net": item.GetNetname(),
            "kind": item.GetClass(), "ref": hit[0], "pad": hit[1],
        })
        board.Remove(item)
    return {
        "schema": 1, "target_count": len(points),
        "missing_targets": missing, "radius_mm": radius,
        "removed_count": len(removed), "removed_items": removed,
        "removed_nets": sorted({row["net"] for row in removed}),
        "protected_nets": sorted(protected),
        "demotable_nets": sorted(demotable),
        "blocked_count": len(blocked), "blocked_items": blocked,
    }


def _ripup_file_worker(board_path, report_path, *, max_assignment_mm,
                        ground_reach_mm, protected_nets,
                        demotable_nets=(), ground_targets=()):
    """One-process pcbnew mutation boundary for routed-seed local rip-up."""
    board = pcbnew.LoadBoard(board_path)
    report = (ripup_foreign_ground_access_copper(
        board, ground_targets, reach_mm=ground_reach_mm,
        protected_nets=protected_nets,
        demotable_nets=demotable_nets) if ground_targets else
        ripup_foreign_local_copper(
            board, max_assignment_mm=max_assignment_mm,
            ground_reach_mm=ground_reach_mm,
            protected_nets=protected_nets,
            demotable_nets=demotable_nets))
    pcbnew.SaveBoard(board_path, board)
    with open(report_path, "w", encoding="utf-8") as sink:
        json.dump(report, sink, indent=2, sort_keys=True)


def _ripup_file_subprocess(board_path, *, max_assignment_mm,
                           ground_reach_mm, protected_nets,
                           demotable_nets=(), ground_targets=()):
    """Run destructive pcbnew child removal in an isolated interpreter.

    KiCad's deprecated SWIG API invalidates unrelated child proxies after a
    Remove().  The process boundary is therefore part of correctness: the
    synthesis pass always loads a fresh board object after rip-up.
    """
    fd, report_path = tempfile.mkstemp(
        prefix="cec-decoupler-ripup-", suffix=".json",
        dir=os.path.dirname(os.path.abspath(board_path)))
    os.close(fd)
    command = [
        sys.executable, os.path.abspath(__file__), "--ripup-worker",
        "--board", os.path.abspath(board_path),
        "--report", report_path,
        "--max-assignment-mm", str(float(max_assignment_mm)),
        "--ground-reach-mm", str(float(ground_reach_mm)),
    ]
    for net in sorted(set(protected_nets or ())):
        command.extend(["--protected-net", net])
    for net in sorted(set(demotable_nets or ())):
        command.extend(["--demotable-net", net])
    for target in ground_targets or ():
        command.extend([
            "--target-ground", "%s:%s" % (
                target.get("ref"), target.get("pad"))])
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=180)
        if completed.returncode:
            raise RuntimeError(
                "local rip-up worker exited %d: %s" % (
                    completed.returncode,
                    (completed.stderr or completed.stdout)[-1000:]))
        with open(report_path, encoding="utf-8") as source:
            return json.load(source)
    finally:
        try:
            os.unlink(report_path)
        except OSError:
            pass


def _ground_probe_file_worker(board_path, report_path, *, reach_mm):
    board = pcbnew.LoadBoard(board_path)
    report = synthesize_ground_plane_access_board(
        board, board_path=board_path, reach_mm=reach_mm, lock=True)
    payload = {
        "schema": 1,
        "refused": [
            {"ref": row.get("ref"), "pad": str(row.get("pad")),
             "reason": row.get("reason")}
            for row in report.get("refused") or ()],
    }
    with open(report_path, "w", encoding="utf-8") as sink:
        json.dump(payload, sink, indent=2, sort_keys=True)


def _ground_probe_file_subprocess(board_path, *, reach_mm):
    fd, report_path = tempfile.mkstemp(
        prefix="cec-ground-access-probe-", suffix=".json",
        dir=os.path.dirname(os.path.abspath(board_path)))
    os.close(fd)
    command = [
        sys.executable, os.path.abspath(__file__), "--ground-probe-worker",
        "--board", os.path.abspath(board_path), "--report", report_path,
        "--ground-reach-mm", str(float(reach_mm)),
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=180)
        if completed.returncode:
            raise RuntimeError(
                "ground-access probe exited %d: %s" % (
                    completed.returncode,
                    (completed.stderr or completed.stdout)[-1000:]))
        with open(report_path, encoding="utf-8") as source:
            return json.load(source)
    finally:
        try:
            os.unlink(report_path)
        except OSError:
            pass


def synthesize_board(board, *, board_path="", max_assignment_mm=3.5,
                     ground_reach_mm=1.5, lock=True, assignment=None,
                     group_neckdowns=True):
    """Lay every assigned device bypass cell in place, atomically per cell."""
    assignment = assignment or cec_constraints._device_bypass_assignment(
        board, project_max_mm=max_assignment_mm)
    rows = []
    generated = []
    missing = [_missing_assignment_report(row)
               for row in assignment.get("missing") or ()]
    for assigned in assignment.get("assigned", {}).values():
        requirement = assigned["requirement"]
        cap = board.FindFootprintByReference(assigned["cap_ref"])
        owner = board.FindFootprintByReference(requirement["ref"])
        owner_pad = requirement["pad"]
        cap_rail = next(
            (pad for pad in cap.Pads()
             if pad.GetNetname() == requirement["rail"]), None)
        cap_gnd = next(
            (pad for pad in cap.Pads()
             if pad.GetNetname() == "GND"), None)
        owner_gnd_pads = ([pad for pad in owner.Pads()
                           if pad.GetNetname() == "GND"]
                          if owner is not None else [])
        row = {
            "owner": requirement["ref"], "pin": requirement["pin"],
            "rail": requirement["rail"], "cap": assigned["cap_ref"],
            "placement_distance_mm": round(
                float(assigned["distance_mm"]), 3),
        }
        before = {item.m_Uuid.AsString() for item in board.GetTracks()}
        if cap_rail is None or cap_gnd is None or not owner_gnd_pads:
            row.update({
                "status": "refused",
                "reason": ("assigned capacitor lacks rail/GND pad or owner "
                           "has no GND pin")})
            rows.append(row)
            continue
        owner_gnd = min(owner_gnd_pads, key=lambda pad: math.hypot(
            pad.GetPosition().x - cap_gnd.GetPosition().x,
            pad.GetPosition().y - cap_gnd.GetPosition().y))
        row["owner_ground_pin"] = owner_gnd.GetPadName()
        row["ground_pin_distance_mm"] = round(math.hypot(
            owner_gnd.GetPosition().x - cap_gnd.GetPosition().x,
            owner_gnd.GetPosition().y - cap_gnd.GetPosition().y) / MM, 3)
        diagnostic = {}
        supply, error = _add_supply_link(
            board, owner_pad, cap_rail, lock=lock,
            diagnostics=diagnostic,
            group_neckdowns=group_neckdowns)
        if error is None:
            owner_ground, ground, ground_link, error = (
                _add_ground_return_pair(
                    board, owner_gnd, cap_gnd, board_path=board_path,
                    reach_mm=ground_reach_mm, lock=lock,
                    group_neckdowns=group_neckdowns))
        else:
            owner_ground = ground = ground_link = None
        if error is not None:
            for item in list(board.GetTracks()):
                if item.m_Uuid.AsString() not in before:
                    board.Remove(item)
            row.update({"status": "refused", "reason": error,
                        "certificate": diagnostic or None,
                        "supply": _report_only(supply),
                        "ground_return": _report_only(ground),
                        "owner_ground_return": _report_only(owner_ground),
                        "ground_link": _report_only(ground_link)})
            rows.append(row)
            continue
        created = [
            item for item in board.GetTracks()
            if item.m_Uuid.AsString() not in before]
        generated.extend({
            "uuid": item.m_Uuid.AsString(), "net": item.GetNetname(),
            "kind": item.GetClass(), "owner": requirement["ref"],
            "cap": assigned["cap_ref"],
        } for item in created)
        row.update({
            "status": "owned", "supply": {
                key: value for key, value in supply.items()
                if key != "items"},
            "ground_return": {
                key: value for key, value in ground.items()
                if key != "items"},
            "owner_ground_return": {
                key: value for key, value in owner_ground.items()
                if key != "items"},
            "ground_link": ground_link,
            "generated": len(created),
        })
        rows.append(row)
    rows.extend(missing)
    refused = [row for row in rows if row.get("status") == "refused"]
    required_vias = sorted({
        item.get("uuid") for item in generated
        if item.get("kind") == "PCB_VIA" and item.get("net") == "GND"
        and item.get("uuid")})
    supply_nets = sorted({
        item.get("net") for item in generated
        if item.get("net") and item.get("net") != "GND"})
    return {
        "schema": 1, "ok": not refused,
        "requirements": len(assignment.get("requirements") or ()),
        "owned": sum(row.get("status") == "owned" for row in rows),
        "refused": refused, "cells": rows,
        "generated_items": generated,
        "generated_item_count": len(generated),
        "required_via_uuids": required_vias,
        "protected_nets": (["GND"] if required_vias else []),
        "partial_supply_nets": supply_nets,
    }


def audit_pre_route_cells_board(board, *, board_path="",
                                max_assignment_mm=3.5,
                                ground_reach_mm=1.5):
    """Read-only exact feasibility proof for the complete cell population.

    Cell feasibility is collective: an individually legal same-net via can
    consume the drill-spacing budget needed by the next bypass cell.  Run the
    real all-or-nothing generator in its deterministic assignment order, then
    remove every trial item.  Placement admission therefore sees precisely
    the conflicts that the production pre-route stage would encounter.
    """
    before = {item.m_Uuid.AsString() for item in board.GetTracks()}
    report = synthesize_board(
        board, board_path=board_path,
        max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm, lock=True)
    trial_items = [
        item for item in list(board.GetTracks())
        if item.m_Uuid.AsString() not in before]
    for item in trial_items:
        board.Remove(item)
    report = dict(report)
    report.update({"read_only": True,
                   "trial_item_count": len(trial_items)})
    return report


def synthesize_ground_returns_board(
        board, *, board_path="", max_assignment_mm=3.5,
        ground_reach_mm=1.5, ground_pin_max_mm=2.5, lock=True):
    """Reserve bypass and IC ground entries before the global router.

    This is intentionally a separate priority stage.  Waiting until detailed
    routing is complete lets unrelated inner-layer copper occupy the through-
    via barrel at the only useful point.  Ground returns are laid first and the
    GND net is protected; local supply links remain for the post-route cell
    finish so shared power nets are not excluded from the global router.
    """
    assignment = cec_constraints._device_bypass_assignment(
        board, project_max_mm=max_assignment_mm)
    rows, generated = [], []
    for missing in assignment.get("missing") or ():
        rows.append(_missing_assignment_report(missing))
    for assigned in assignment.get("assigned", {}).values():
        req = assigned["requirement"]
        cap = board.FindFootprintByReference(assigned["cap_ref"])
        owner = board.FindFootprintByReference(req["ref"])
        cap_gnd = next((pad for pad in cap.Pads()
                        if pad.GetNetname() == "GND"), None) if cap else None
        owner_gnds = ([pad for pad in owner.Pads()
                       if pad.GetNetname() == "GND"] if owner else [])
        row = {"owner": req["ref"], "pin": req["pin"],
               "rail": req["rail"], "cap": assigned["cap_ref"],
               "placement_distance_mm": round(
                   float(assigned["distance_mm"]), 3)}
        if cap_gnd is None or not owner_gnds:
            row.update({"status": "refused",
                        "reason": "missing capacitor or owner GND pad"})
            rows.append(row); continue
        owner_gnd = min(owner_gnds, key=lambda pad: math.hypot(
            pad.GetPosition().x - cap_gnd.GetPosition().x,
            pad.GetPosition().y - cap_gnd.GetPosition().y))
        ground_gap = math.hypot(
            owner_gnd.GetPosition().x - cap_gnd.GetPosition().x,
            owner_gnd.GetPosition().y - cap_gnd.GetPosition().y) / MM
        row.update({"owner_ground_pin": owner_gnd.GetPadName(),
                    "ground_pin_distance_mm": round(ground_gap, 3)})
        if ground_gap > ground_pin_max_mm + 1e-9:
            row.update({"status": "refused",
                        "reason": "cap-to-owner GND gap %.3fmm exceeds %.3fmm" %
                                  (ground_gap, ground_pin_max_mm)})
            rows.append(row); continue
        before = {item.m_Uuid.AsString() for item in board.GetTracks()}
        owner_return, cap_return, ground_link, error = (
            _add_ground_return_pair(
                board, owner_gnd, cap_gnd, board_path=board_path,
                reach_mm=ground_reach_mm, lock=lock))
        if error is not None:
            for item in list(board.GetTracks()):
                if item.m_Uuid.AsString() not in before:
                    board.Remove(item)
            row.update({"status": "refused", "reason": error,
                        "owner_ground_return": _report_only(owner_return),
                        "ground_return": _report_only(cap_return),
                        "ground_link": _report_only(ground_link)})
            rows.append(row); continue
        created = [item for item in board.GetTracks()
                   if item.m_Uuid.AsString() not in before]
        generated.extend({"uuid": item.m_Uuid.AsString(),
                          "net": item.GetNetname(),
                          "kind": item.GetClass(),
                          "owner": req["ref"],
                          "cap": assigned["cap_ref"]}
                         for item in created)
        row.update({
            "status": "owned", "generated": len(created),
            "owner_ground_return": {
                key: value for key, value in owner_return.items()
                if key != "items"},
            "ground_return": {
                key: value for key, value in cap_return.items()
                if key != "items"},
            "ground_link": ground_link,
        })
        rows.append(row)
    refused = [row for row in rows if row.get("status") == "refused"]
    required_vias = sorted({
        entry.get("via_uuid")
        for row in rows if row.get("status") == "owned"
        for entry in (row.get("owner_ground_return"),
                      row.get("ground_return"))
        if isinstance(entry, dict) and entry.get("via_uuid")
    })
    return {"schema": 1, "ok": not refused,
            "requirements": len(assignment.get("requirements") or ()),
            "owned": len(rows) - len(refused), "refused": refused,
            "cells": rows, "generated_items": generated,
            "generated_item_count": len(generated),
            "required_via_uuids": required_vias,
            "protected_nets": (["GND"] if generated else [])}


def synthesize_ground_plane_access_board(
        board, *, board_path="", reach_mm=1.5, lock=True,
        group_neckdowns=True):
    """Give every surface GND pad a guarded portal to a dedicated plane.

    Protecting GND at net scope is valid only when every surface terminal has
    plane access.  Reserving just the bypass-cell returns and then excluding
    GND from the residual router can strand unrelated connector, protection,
    and filter pads.  Reuse the same qualified POFV-or-dogbone primitive for
    all SMD GND pads before signal routing and publish the exact via UUID set
    that the subsequent plane-fill stage must prove connected.
    """
    pads = []
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            try:
                surface = (int(pad.GetAttribute()) ==
                           int(pcbnew.PAD_ATTRIB_SMD))
            except Exception:                           # noqa: BLE001
                surface = False
            if surface and pad.GetNetname() == "GND":
                position = pad.GetPosition()
                pads.append((footprint.GetReference(), pad.GetPadName(),
                             position.x, position.y, pad))
    pads.sort(key=lambda row: (row[0], str(row[1]), row[2], row[3]))

    before = {item.m_Uuid.AsString() for item in board.GetTracks()}
    rows = []
    live_rows = []
    for reference, number, _x, _y, pad in pads:
        result, error = _add_ground_return(
            board, pad, board_path=board_path,
            reach_mm=reach_mm, lock=lock)
        row = {"ref": reference, "pad": str(number)}
        if error is not None:
            row.update({"status": "refused", "reason": error})
        else:
            row.update(_report_only(result))
            row["generated_item_uuids"] = sorted(
                item.m_Uuid.AsString()
                for item in (result.get("items") or ()))
        rows.append(row)
        live_rows.append((row, pad))

    # A separate barrel per land is preferred, but dense packages can make
    # that geometrically impossible.  Complete a refused terminal through the
    # nearest already-qualified GND portal when a short guarded pad-to-pad link
    # fits the same return budget.  This is the generic shared-entry pattern
    # used by professional layouts for adjacent ground lands; it remains
    # all-or-nothing and cannot turn a distant plane connection into a local
    # return by label alone.
    portals = [(row, pad) for row, pad in live_rows
               if row.get("status") != "refused" and row.get("via_uuid")]
    for row, pad in live_rows:
        if row.get("status") != "refused":
            continue
        position = pad.GetPosition()
        candidates = []
        for portal_row, portal_pad in portals:
            if portal_pad is pad:
                continue
            covered = _existing_return(board, portal_pad, reach_mm)
            if covered is None:
                continue
            via_position = covered[1].GetPosition()
            via_distance = math.hypot(
                via_position.x - position.x,
                via_position.y - position.y) / MM
            if via_distance <= reach_mm + 1e-9:
                candidates.append((
                    via_distance, portal_row.get("ref") or "",
                    str(portal_row.get("pad") or ""), portal_row,
                    portal_pad))
        candidates.sort(key=lambda item: item[:3])
        independent_refusal = row.get("reason")
        shared_failures = []
        for _distance, _ref, _number, portal_row, portal_pad in candidates:
            attempt_before = {
                item.m_Uuid.AsString() for item in board.GetTracks()}
            owner_return, _portal_return, ground_link, error = (
                _add_ground_return_pair(
                    board, pad, portal_pad, board_path=board_path,
                    reach_mm=reach_mm, lock=lock,
                    group_neckdowns=group_neckdowns))
            if error is None:
                row.clear()
                row.update({
                    "ref": _pad_identity(pad).get("ref"),
                    "pad": str(pad.GetPadName()),
                    "status": "shared-ground-entry",
                    "distance_mm": owner_return.get("distance_mm"),
                    "via_uuid": owner_return.get("via_uuid"),
                    "shared_with": {
                        "ref": portal_row.get("ref"),
                        "pad": portal_row.get("pad"),
                    },
                    "ground_link": _report_only(ground_link),
                    "independent_refusal": independent_refusal,
                })
                row["generated_item_uuids"] = sorted(
                    item.m_Uuid.AsString()
                    for item in board.GetTracks()
                    if item.m_Uuid.AsString() not in attempt_before)
                portals.append((row, pad))
                break
            for item in list(board.GetTracks()):
                if item.m_Uuid.AsString() not in attempt_before:
                    board.Remove(item)
            shared_failures.append({
                "ref": portal_row.get("ref"),
                "pad": portal_row.get("pad"), "reason": error})
        if row.get("status") == "refused":
            row["shared_entry_candidates"] = len(candidates)
            row["shared_entry_failures"] = shared_failures[:8]

    generated = [
        item for item in board.GetTracks()
        if item.m_Uuid.AsString() not in before]
    refused = [row for row in rows if row.get("status") == "refused"]
    required_vias = sorted({
        row.get("via_uuid") for row in rows
        if row.get("via_uuid")})
    return {
        "schema": 1,
        "ok": not refused,
        "pads": len(rows),
        "covered": sum(row.get("status") == "covered" for row in rows),
        "via_in_pad": sum(
            row.get("status") == "via-in-pad" for row in rows),
        "dogbones": sum(row.get("status") == "dogbone" for row in rows),
        "shared_entries": sum(
            row.get("status") == "shared-ground-entry" for row in rows),
        "refused": refused,
        "terminals": rows,
        "generated_item_count": len(generated),
        "generated_items": [{
            "uuid": item.m_Uuid.AsString(),
            "net": item.GetNetname(),
            "kind": item.GetClass(),
        } for item in generated],
        "required_via_uuids": required_vias,
        "protected_nets": (["GND"] if rows and not refused else []),
    }


def _drc_regressed_except(before, after, allowed_types=()):
    """Compare structural DRC by type while naming stage-deferred classes."""
    allowed = set(allowed_types)
    keys = set(before.drc_types) | set(after.drc_types)
    return any(
        kind not in allowed
        and after.drc_types.get(kind, 0) > before.drc_types.get(kind, 0)
        for kind in keys)


def _drc_regression(before, after, allowed_types=()):
    """Return the exact unexpected DRC delta for blocker provenance."""
    allowed = set(allowed_types)
    keys = set(before.drc_types) | set(after.drc_types)
    return {
        kind: after.drc_types.get(kind, 0) - before.drc_types.get(kind, 0)
        for kind in sorted(keys)
        if (kind not in allowed and
            after.drc_types.get(kind, 0) > before.drc_types.get(kind, 0))
    }


def _stage_drc_regression(before, after, *, allowed_types=(),
                          generated_nets=()):
    """Return only DRC growth attributable to this generated-net stage.

    KiCad may report one of several already-overlapping violations depending
    on insertion/UUID order.  Adding many same-net vias made an unchanged
    SENSE crossing alternate between ``tracks_crossing`` and ``clearance``;
    a type-counter-only gate therefore accepted or rolled back byte-equivalent
    GND synthesis nondeterministically.  The stage still fails closed when the
    total nondeferred count grows, when a novel locus names a net this stage
    generated, or when a new locus is not attributable from available
    evidence.  A one-for-one reclassification wholly among untouched nets is
    retained as telemetry rather than mislabeled as generated geometry.
    """
    allowed = set(allowed_types)
    positive = _drc_regression(before, after, allowed)
    if not positive:
        return {}
    before_count = sum(
        int(count) for kind, count in before.drc_types.items()
        if kind not in allowed)
    after_count = sum(
        int(count) for kind, count in after.drc_types.items()
        if kind not in allowed)
    if after_count > before_count:
        return positive

    import collections
    before_loci = collections.Counter(
        (str(row.get("type") or ""), str(row.get("where") or ""))
        for row in getattr(before, "drc_loci", ())
        if str(row.get("type") or "") not in allowed)
    after_loci = collections.Counter(
        (str(row.get("type") or ""), str(row.get("where") or ""))
        for row in getattr(after, "drc_loci", ())
        if str(row.get("type") or "") not in allowed)
    novel = list((after_loci - before_loci).elements())
    positive_total = sum(positive.values())
    if len(novel) < positive_total:
        return positive
    markers = tuple("[%s]" % str(net) for net in generated_nets if net)
    for kind, where in novel:
        if not where or any(marker in where for marker in markers):
            return positive
    return {}


def _score_summary(metrics):
    summary = cec_stage_admission.snapshot(metrics)
    summary.update({
        "drc_types": dict(metrics.drc_types),
        "drc_loci": list(getattr(metrics, "drc_loci", ())),
    })
    return summary


def synthesize_ground_returns(source, destination, *, max_assignment_mm=3.5,
                              ground_reach_mm=1.5,
                              ground_pin_max_mm=2.5):
    """Transactional file wrapper for the pre-route ground-return stage."""
    import cec_score

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    cec_fr.copy_project_sidecars(source, destination)
    before = cec_score.score(source)
    board = pcbnew.LoadBoard(destination)
    report = synthesize_ground_returns_board(
        board, board_path=destination,
        max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm,
        ground_pin_max_mm=ground_pin_max_mm, lock=True)
    pcbnew.SaveBoard(destination, board)
    after = cec_score.score(destination)
    # A reserved GND barrel is intentionally dangling until the later plane
    # fill/global-route stage connects it on an inner GND layer.  Admit only
    # that named, expected pre-route class; every geometry, clearance, short,
    # pair, or connectivity regression still rolls the transaction back.
    deferred_types = {"via_dangling"}
    stage_drc_regression = _stage_drc_regression(
        before, after, allowed_types=deferred_types,
        generated_nets={"GND"})
    admission = cec_stage_admission.evaluate(
        before, after, allowed_new_drc_types=deferred_types)
    regression = (not report.get("ok")
                  or bool(stage_drc_regression)
                  or not admission["accepted"])
    deferred_drc = {
        kind: after.drc_types.get(kind, 0) - before.drc_types.get(kind, 0)
        for kind in deferred_types
        if after.drc_types.get(kind, 0) > before.drc_types.get(kind, 0)}
    report.update({
        "before": _score_summary(before),
        "after": _score_summary(after),
        "admission": admission,
        "drc_regression": stage_drc_regression,
        "drc_reclassification": (
            _drc_regression(before, after, deferred_types)
            if not stage_drc_regression else {}),
        "deferred_pre_route_drc": deferred_drc,
        "rolled_back": bool(regression),
    })
    if regression:
        shutil.copy2(source, destination)
        cec_fr.copy_project_sidecars(source, destination)
        report["ok"] = False
        report["reason"] = (
            "one or more complete local cells refused"
            if report.get("refused") else
            (admission["decision"] if not admission["accepted"] else
             "full-board DRC/connectivity/pair regression"))
    return report


def _prune_ground_access_drc_groups(board, report, before_drc, after_drc):
    """Remove only generated terminal groups named by a new exact DRC.

    Board-wide GND access is a collection of independent local portals, not
    one indivisible route.  The historical file transaction discarded every
    legal portal when one generated dogbone touched a protected pour.  Decode
    the UUID-backed DRC identities and roll back the complete terminal group
    (via plus its incident stub/link) for each implicated generated item.

    Existing-source DRC is debt-neutral here: only identities absent from the
    input artifact can reject a generated group.  Any unattributed new fault
    remains for the wrapper's full-board fail-closed gate and therefore can
    never be hidden by this selective admission.
    """
    import cec_certificate_repair

    before_identities = set(
        cec_certificate_repair._structural_drc_identities(before_drc))
    after_identities = set(
        cec_certificate_repair._structural_drc_identities(after_drc))
    new_identities = sorted(after_identities - before_identities)
    generated = {
        str(item.get("uuid") or "")
        for item in (report.get("generated_items") or ())
        if item.get("uuid")
    }
    implicated = set()
    kinds_by_uuid = {}
    for identity in new_identities:
        try:
            row = json.loads(identity)
        except (TypeError, ValueError):
            continue
        if not isinstance(row, list) or len(row) < 3 or row[1] != "uuid":
            continue
        kind = str(row[0] or "")
        for uid in row[2] if isinstance(row[2], list) else ():
            uid = str(uid or "")
            if uid in generated:
                implicated.add(uid)
                kinds_by_uuid.setdefault(uid, set()).add(kind)

    rejected_groups = []
    remove_uuids = set()
    for terminal in report.get("terminals") or ():
        group = {
            str(uid) for uid in (terminal.get("generated_item_uuids") or ())
            if uid
        }
        hits = sorted(group & implicated)
        if not hits:
            continue
        remove_uuids.update(group)
        kinds = sorted({kind for uid in hits
                        for kind in kinds_by_uuid.get(uid, ())})
        rejected_groups.append({
            "ref": str(terminal.get("ref") or ""),
            "pad": str(terminal.get("pad") or ""),
            "generated_item_uuids": sorted(group),
            "implicated_item_uuids": hits,
            "drc_types": kinds,
        })
        terminal["pre_admission_status"] = terminal.get("status")
        terminal["status"] = "refused"
        terminal["reason"] = (
            "terminal-local GND access rejected by exact full-board DRC: %s"
            % (", ".join(kinds) or "unclassified structural fault"))
        terminal["generated_item_uuids"] = []

    # Defensive fallback for a producer bug which emitted a generated UUID
    # without attaching it to its terminal row.  Remove that primitive too;
    # the still-live new identity will make the wrapper roll back the entire
    # transaction if a dependent item was not attributable.
    remove_uuids.update(implicated)
    for item in list(board.GetTracks()):
        if item.m_Uuid.AsString() in remove_uuids:
            board.Remove(item)

    live_route = {
        item.m_Uuid.AsString(): item for item in board.GetTracks()
    }
    live = {
        item.m_Uuid.AsString(): item for item in board.GetTracks()
        if item.m_Uuid.AsString() in generated
    }
    report["generated_items"] = [{
        "uuid": uid, "net": item.GetNetname(), "kind": item.GetClass(),
    } for uid, item in sorted(live.items())]
    report["generated_item_count"] = len(live)
    report["required_via_uuids"] = sorted({
        str(row.get("via_uuid"))
        for row in (report.get("terminals") or ())
        if row.get("status") != "refused"
        and str(row.get("via_uuid") or "") in live_route
    })
    refused = [row for row in (report.get("terminals") or ())
               if row.get("status") == "refused"]
    report["refused"] = refused
    report["ok"] = not refused
    report["protected_nets"] = (["GND"] if report["ok"] else [])
    report["exact_group_admission"] = {
        "schema": 1,
        "before_structural_drc_identities": sorted(before_identities),
        "after_structural_drc_identities": sorted(after_identities),
        "new_structural_drc_identities": new_identities,
        "implicated_generated_item_uuids": sorted(implicated),
        "removed_generated_item_uuids": sorted(remove_uuids),
        "rejected_terminal_groups": rejected_groups,
    }
    return report


def synthesize_ground_plane_access(source, destination, *, reach_mm=1.5,
                                   repair_existing_copper=False,
                                   protected_nets=(), demotable_nets=()):
    """Transactionally reserve complete SMD GND access before net protection."""
    import cec_certificate_repair
    import cec_score

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    cec_fr.copy_project_sidecars(source, destination)
    drc_dir = tempfile.mkdtemp(prefix="cec-ground-access-drc-")
    before_drc_path = os.path.join(drc_dir, "before.json")
    after_drc_path = os.path.join(drc_dir, "after-bulk.json")
    final_drc_path = os.path.join(drc_dir, "after-admission.json")
    before_drc = cec_certificate_repair._run_drc(
        source, before_drc_path)
    before = cec_score.score(source, drc_json=before_drc_path)
    probe = ({"schema": 1, "skipped": "not_requested", "refused": []}
             if not repair_existing_copper else
             _ground_probe_file_subprocess(
                 destination, reach_mm=reach_mm))
    ripup = ({"schema": 1, "skipped": "not_requested",
              "removed_count": 0, "removed_nets": []}
             if not probe.get("refused") else
             _ripup_file_subprocess(
                 destination, max_assignment_mm=3.5,
                 ground_reach_mm=reach_mm,
                 protected_nets=protected_nets,
                 demotable_nets=demotable_nets,
                 ground_targets=probe["refused"]))
    board = pcbnew.LoadBoard(destination)
    report = synthesize_ground_plane_access_board(
        board, board_path=destination, reach_mm=reach_mm, lock=True)
    pcbnew.SaveBoard(destination, board)
    after_drc = cec_certificate_repair._run_drc(
        destination, after_drc_path)
    _prune_ground_access_drc_groups(
        board, report, before_drc, after_drc)
    pcbnew.SaveBoard(destination, board)
    # The local PI transaction can add through vias on any input, not only an
    # already-routed seed.  A saved KiCad zone retains its previous fill until
    # it is explicitly refilled; scoring newly-added foreign-net vias against
    # that stale fill reports false via-to-plane clearance/hole-clearance
    # regressions.  Refill after every successful cell mutation so placement,
    # fresh production, and routed-repair paths all admit the same physical
    # board state.
    if report.get("ok") and report.get("generated_item_count"):
        try:
            cec_fr.refill_zones(destination)
        except Exception as exc:                         # noqa: BLE001
            report["zone_refill_error"] = "%s: %s" % (
                type(exc).__name__, exc)
            report["ok"] = False
    final_drc = cec_certificate_repair._run_drc(
        destination, final_drc_path)
    after = cec_score.score(destination, drc_json=final_drc_path)
    deferred_types = {"via_dangling"}
    repair_deferred_opens = bool(
        repair_existing_copper and ripup.get("removed_count"))
    if repair_deferred_opens:
        deferred_types.add("track_dangling")
    stage_drc_regression = _stage_drc_regression(
        before, after, allowed_types=deferred_types,
        generated_nets={"GND"})
    exact_new_identities = sorted(
        set(cec_certificate_repair._structural_drc_identities(final_drc))
        - set(cec_certificate_repair._structural_drc_identities(before_drc)))
    partial_admission = bool(
        not report.get("ok") and report.get("generated_item_count")
        and not exact_new_identities)
    report["partial_admission"] = partial_admission
    allowed_open_nets = set(ripup.get("removed_nets") or ())
    admission = cec_stage_admission.evaluate(
        before, after,
        allow_unconnected_growth=repair_deferred_opens,
        allowed_new_unconnected_nets=allowed_open_nets,
        allowed_new_drc_types=deferred_types)
    regression = (
        (not report.get("ok") and not partial_admission)
        or bool(stage_drc_regression)
        or bool(exact_new_identities)
        or not admission["accepted"])
    deferred_drc = {
        kind: after.drc_types.get(kind, 0) - before.drc_types.get(kind, 0)
        for kind in deferred_types
        if after.drc_types.get(kind, 0) > before.drc_types.get(kind, 0)}
    report.update({
        "before": _score_summary(before),
        "after": _score_summary(after),
        "admission": admission,
        "drc_regression": stage_drc_regression,
        "drc_reclassification": (
            _drc_regression(before, after, deferred_types)
            if not stage_drc_regression else {}),
        "deferred_pre_route_drc": deferred_drc,
        "rolled_back": bool(regression),
        "priority_complete": bool(report.get("ok") and not regression),
        "repair_probe": probe,
        "local_ripup": ripup,
        "deferred_ripup_opens": bool(
            repair_deferred_opens and
            after.unconnected > before.unconnected),
        "before_structural_drc_identities": sorted(
            cec_certificate_repair._structural_drc_identities(before_drc)),
        "after_structural_drc_identities": sorted(
            cec_certificate_repair._structural_drc_identities(final_drc)),
        "new_structural_drc_identities": exact_new_identities,
    })
    if regression:
        shutil.copy2(source, destination)
        cec_fr.copy_project_sidecars(source, destination)
        report["ok"] = False
        report["reason"] = (
            "one or more SMD GND terminals lack guarded plane access"
            if report.get("refused") else
            (admission["decision"] if not admission["accepted"] else
             "full-board DRC/connectivity/pair regression"))
    shutil.rmtree(drc_dir, ignore_errors=True)
    return report


def synthesize_pre_route(source, destination, *, max_assignment_mm=3.5,
                         ground_reach_mm=1.5,
                         ground_pin_max_mm=2.5,
                         repair_existing_copper=False,
                         protected_nets=(), demotable_nets=()):
    """Transactionally own complete local bypass cells before global routing.

    Supply links and both immediate GND entries are local, topology-critical
    copper.  Deferring the rail side until after the broad router allowed
    ordinary routes to occupy the only guarded launch, producing failures that
    no amount of final-wave effort could repair.  This wrapper admits the
    complete cell early while allowing only the explicitly temporary dangling
    GND-via DRC class; the following dedicated-plane stage must consume those
    exact via UUIDs.
    """
    import cec_score

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    cec_fr.copy_project_sidecars(source, destination)
    before = cec_score.score(source)
    ripup = ({"schema": 1, "skipped": "not_requested",
              "removed_count": 0, "removed_nets": []}
             if not repair_existing_copper else
             _ripup_file_subprocess(
                 destination, max_assignment_mm=max_assignment_mm,
                 ground_reach_mm=ground_reach_mm,
                 protected_nets=protected_nets,
                 demotable_nets=demotable_nets))
    board = pcbnew.LoadBoard(destination)
    report = synthesize_board(
        board, board_path=destination,
        max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm, lock=True)
    report["endpoint_neckdown_reconcile"] = \
        cec_fr.reconcile_endpoint_neckdown_groups(
            board, netclass_resolver=cec_fr._project_netclass_resolver(
                destination))
    pcbnew.SaveBoard(destination, board)
    rule_report = report
    recovered = report["endpoint_neckdown_reconcile"]
    if recovered.get("min_width_mm") is not None:
        rule_report = {**report, "endpoint_neckdown": recovered}
    report["endpoint_neckdown_rule"] = \
        _ensure_endpoint_neckdown_rule(destination, rule_report)
    # Fresh placements and routed seeds have the same saved-zone lifecycle:
    # every generated PI via must be incorporated into a new zone fill before
    # exact DRC admission.  Conditioning this on local rip-up mode left fresh
    # production boards scored against stale plane copper.
    if report.get("ok") and report.get("generated_item_count"):
        try:
            cec_fr.refill_zones(destination)
        except Exception as exc:                         # noqa: BLE001
            report["zone_refill_error"] = "%s: %s" % (
                type(exc).__name__, exc)
            report["ok"] = False
    after = cec_score.score(destination)
    repair_deferred_opens = bool(
        repair_existing_copper and ripup.get("removed_count"))
    deferred_types = {"via_dangling"}
    if repair_deferred_opens:
        # The local transaction intentionally tears up ordinary residual nets
        # so priority power-integrity cells can own their escape first.  These
        # exact named nets are handed to the immediately following router;
        # dangling fragments are therefore stage-local, never release waivers.
        deferred_types.add("track_dangling")
    generated_nets = {
        str(item.get("net")) for item in report.get("generated_items", ())
        if item.get("net")}
    stage_drc_regression = _stage_drc_regression(
        before, after, allowed_types=deferred_types,
        generated_nets=generated_nets)
    allowed_open_nets = set(ripup.get("removed_nets") or ())
    admission = cec_stage_admission.evaluate(
        before, after,
        allow_unconnected_growth=repair_deferred_opens,
        allowed_new_unconnected_nets=allowed_open_nets,
        allowed_new_drc_types=deferred_types)
    regression = (not report.get("ok")
                  or bool(stage_drc_regression)
                  or not admission["accepted"])
    deferred_drc = {
        kind: after.drc_types.get(kind, 0) - before.drc_types.get(kind, 0)
        for kind in deferred_types
        if after.drc_types.get(kind, 0) > before.drc_types.get(kind, 0)}
    report.update({
        "before": _score_summary(before),
        "after": _score_summary(after),
        "admission": admission,
        "drc_regression": stage_drc_regression,
        "drc_reclassification": (
            _drc_regression(before, after, deferred_types)
            if not stage_drc_regression else {}),
        "deferred_pre_route_drc": deferred_drc,
        "rolled_back": bool(regression),
        "priority_complete": bool(report.get("ok") and not regression),
        "ground_pin_max_mm": float(ground_pin_max_mm),
        "local_ripup": ripup,
        "deferred_ripup_opens": bool(
            repair_deferred_opens and
            after.unconnected > before.unconnected),
    })
    if regression:
        shutil.copy2(source, destination)
        cec_fr.copy_project_sidecars(source, destination)
        report["ok"] = False
        report["priority_complete"] = False
        report["reason"] = (
            "one or more complete local cells refused"
            if report.get("refused") else
            (admission["decision"] if not admission["accepted"] else
             "full-board DRC/connectivity/pair regression"))
    return report


def audit_board(board, *, board_path="", max_assignment_mm=3.5,
                ground_reach_mm=1.5, ground_pin_max_mm=2.5):
    """Measure the completed IC-pin/cap/ground-return cell on final copper."""
    assignment = cec_constraints._device_bypass_assignment(
        board, project_max_mm=max_assignment_mm)
    rows = []
    for missing in assignment.get("missing") or ():
        rows.append(_missing_assignment_report(missing))
    for assigned in assignment.get("assigned", {}).values():
        req = assigned["requirement"]
        cap = board.FindFootprintByReference(assigned["cap_ref"])
        owner = board.FindFootprintByReference(req["ref"])
        cap_rail = next((pad for pad in cap.Pads()
                         if pad.GetNetname() == req["rail"]), None)
        cap_gnd = next((pad for pad in cap.Pads()
                        if pad.GetNetname() == "GND"), None)
        owner_gnds = ([pad for pad in owner.Pads()
                       if pad.GetNetname() == "GND"]
                      if owner is not None else [])
        row = {"owner": req["ref"], "pin": req["pin"],
               "rail": req["rail"], "cap": assigned["cap_ref"],
               "placement_distance_mm": round(
                   float(assigned["distance_mm"]), 3)}
        if cap_rail is None or cap_gnd is None or not owner_gnds:
            row.update({"status": "refused",
                        "reason": "missing rail/GND pad geometry"})
            rows.append(row); continue
        owner_gnd = min(owner_gnds, key=lambda pad: math.hypot(
            pad.GetPosition().x - cap_gnd.GetPosition().x,
            pad.GetPosition().y - cap_gnd.GetPosition().y))
        direct = math.hypot(
            req["pad"].GetPosition().x - cap_rail.GetPosition().x,
            req["pad"].GetPosition().y - cap_rail.GetPosition().y) / MM
        supply_path = _shortest_track_path_mm(board, req["pad"], cap_rail)
        supply_spec = _netclass(board, req["rail"])
        supply_limit = _local_supply_limit_mm(
            direct, float(supply_spec["width"]) / MM,
            max(pcbnew.FromMM(0.20),
                int(supply_spec["clearance"])) / MM)
        cap_return = _existing_return(board, cap_gnd, ground_reach_mm)
        owner_return = _existing_return(board, owner_gnd, ground_reach_mm)
        cap_shared = (None if cap_return is not None else
                      _shared_ground_return(
                          board, cap_gnd, owner_gnd, ground_reach_mm))
        owner_shared = (None if owner_return is not None else
                        _shared_ground_return(
                            board, owner_gnd, cap_gnd, ground_reach_mm))
        ground_gap = math.hypot(
            owner_gnd.GetPosition().x - cap_gnd.GetPosition().x,
            owner_gnd.GetPosition().y - cap_gnd.GetPosition().y) / MM
        reasons = []
        if supply_path is None:
            reasons.append("no explicit local supply copper")
        elif supply_path > supply_limit + 1e-9:
            reasons.append("supply copper %.3fmm exceeds local limit %.3fmm" %
                           (supply_path, supply_limit))
        if cap_return is None and cap_shared is None:
            reasons.append("capacitor GND has no connected via within %.2fmm" %
                           ground_reach_mm)
        if owner_return is None and owner_shared is None:
            reasons.append("owner GND pin has no connected via within %.2fmm" %
                           ground_reach_mm)
        if ground_gap > ground_pin_max_mm + 1e-9:
            reasons.append("cap-to-owner GND gap %.3fmm exceeds %.3fmm" %
                           (ground_gap, ground_pin_max_mm))
        row.update({
            "status": "owned" if not reasons else "refused",
            "reason": "; ".join(reasons) if reasons else None,
            "supply_path_mm": (round(supply_path, 3)
                               if supply_path is not None else None),
            "supply_local_limit_mm": round(supply_limit, 3),
            "ground_pin_distance_mm": round(ground_gap, 3),
            "owner_ground_pin": owner_gnd.GetPadName(),
            "cap_ground_return_mm": (round(cap_return[0], 3)
                                     if cap_return else
                                     (cap_shared.get("path_mm")
                                      if cap_shared else None)),
            "owner_ground_return_mm": (round(owner_return[0], 3)
                                       if owner_return else
                                       (owner_shared.get("path_mm")
                                        if owner_shared else None)),
            "cap_ground_return_status": (
                "immediate-via" if cap_return else
                ("shared-ground-entry" if cap_shared else "missing")),
            "owner_ground_return_status": (
                "immediate-via" if owner_return else
                ("shared-ground-entry" if owner_shared else "missing")),
            "cap_ground_return_evidence": cap_shared,
            "owner_ground_return_evidence": owner_shared,
        })
        rows.append(row)
    refused = [row for row in rows if row.get("status") == "refused"]
    return {"schema": 1, "ok": not refused,
            "requirements": len(assignment.get("requirements") or ()),
            "owned": len(rows) - len(refused), "refused": refused,
            "cells": rows, "ground_reach_mm": ground_reach_mm,
            "ground_pin_max_mm": ground_pin_max_mm}


def synthesize(source, destination, *, max_assignment_mm=3.5,
               ground_reach_mm=1.5, ground_pin_max_mm=2.5):
    """Apply the cell finish transactionally against full-board signoff metrics."""
    import cec_score

    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    shutil.copy2(source, destination)
    cec_fr.copy_project_sidecars(source, destination)
    before = cec_score.score(source)
    board = pcbnew.LoadBoard(destination)
    report = synthesize_board(
        board, board_path=destination,
        max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm, lock=True)
    report["endpoint_neckdown_reconcile"] = \
        cec_fr.reconcile_endpoint_neckdown_groups(
            board, netclass_resolver=cec_fr._project_netclass_resolver(
                destination))
    pcbnew.SaveBoard(destination, board)
    rule_report = report
    recovered = report["endpoint_neckdown_reconcile"]
    if recovered.get("min_width_mm") is not None:
        rule_report = {**report, "endpoint_neckdown": recovered}
    report["endpoint_neckdown_rule"] = \
        _ensure_endpoint_neckdown_rule(destination, rule_report)
    try:
        cec_fr.refill_zones(destination)
    except Exception as error:                            # noqa: BLE001
        report["refill_error"] = "%s: %s" % (type(error).__name__, error)
    after = cec_score.score(destination)
    audit = audit_board(
        pcbnew.LoadBoard(destination), board_path=destination,
        max_assignment_mm=max_assignment_mm,
        ground_reach_mm=ground_reach_mm,
        ground_pin_max_mm=ground_pin_max_mm)
    admission = cec_stage_admission.evaluate(before, after)
    regression = not admission["accepted"]
    report.update({
        "before": admission["before"],
        "after": admission["after"],
        "admission": admission,
        "audit": audit, "rolled_back": bool(regression),
    })
    if regression:
        shutil.copy2(source, destination)
        cec_fr.copy_project_sidecars(source, destination)
        report["ok"] = False
        report["reason"] = admission["decision"]
    else:
        report["ok"] = bool(report.get("ok") and audit.get("ok"))
    return report


def _main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--ripup-worker", action="store_true")
    parser.add_argument("--ground-probe-worker", action="store_true")
    parser.add_argument("--reservation-worker", action="store_true")
    parser.add_argument("--board")
    parser.add_argument("--report")
    parser.add_argument("--max-assignment-mm", type=float, default=3.5)
    parser.add_argument("--ground-reach-mm", type=float, default=1.5)
    parser.add_argument("--protected-net", action="append", default=[])
    parser.add_argument("--demotable-net", action="append", default=[])
    parser.add_argument("--target-ground", action="append", default=[])
    args = parser.parse_args(argv)
    if not args.board or not args.report:
        parser.error("private worker requires --board --report")
    if args.reservation_worker:
        _reservation_file_worker(
            args.board, args.report,
            max_assignment_mm=args.max_assignment_mm,
            ground_reach_mm=args.ground_reach_mm)
    elif args.ground_probe_worker:
        _ground_probe_file_worker(
            args.board, args.report, reach_mm=args.ground_reach_mm)
    elif args.ripup_worker:
        targets = []
        for token in args.target_ground:
            if ":" not in token:
                parser.error("--target-ground requires REF:PAD")
            ref, pad = token.rsplit(":", 1)
            targets.append({"ref": ref, "pad": pad})
        _ripup_file_worker(
            args.board, args.report,
            max_assignment_mm=args.max_assignment_mm,
            ground_reach_mm=args.ground_reach_mm,
            protected_nets=args.protected_net,
            demotable_nets=args.demotable_net,
            ground_targets=targets)
    else:
        parser.error("private worker mode is required")
    # pcbnew SWIG may dereference invalidated child proxies during interpreter
    # teardown after Remove().  All durable outputs are already closed; bypass
    # Python finalizers at this private process boundary.
    os._exit(0)


if __name__ == "__main__":
    _main()
