#!/usr/bin/env python3
"""Transactional coarse-grid router for long residual connections.

This stage proves full-size project-netclass dogbone vias first, searches a
coarse octilinear grid with exact KiCad collision guards, smooths the result,
and adopts it only when whole-board DRC/connectivity strictly improves.
"""

import argparse
import heapq
import json
import math
import os
import shutil
import tempfile

import pcbnew

import cec_fr
import cec_fab_profile
import cec_field_coupling
import cec_score
import cec_stage_admission

MM = 1_000_000


def _octilinear(a, b, tolerance_nm=1_000):
    dx, dy = abs(a.x - b.x), abs(a.y - b.y)
    return dx <= tolerance_nm or dy <= tolerance_nm or abs(dx - dy) <= tolerance_nm


def _net_code(board, name):
    for code, info in board.GetNetInfo().NetsByNetcode().items():
        if info.GetNetname() == name:
            return int(code)
    raise ValueError(f"unknown net {name!r}")


def _item_uuid(item):
    return item.m_Uuid.AsString()


def _item_anchors(board, item):
    """Return legal copper attachment points carried by one connected item."""
    kind = item.GetClass()
    if kind == "PCB_TRACK":
        return [{"description": f"track {_item_uuid(item)} endpoint",
                 "position": point, "kind": "track",
                 "layers": {int(item.GetLayer())}}
                for point in (item.GetStart(), item.GetEnd())]
    if kind == "PCB_VIA":
        layers = {int(layer) for layer in board.GetEnabledLayers().CuStack()
                  if item.IsOnLayer(layer)}
        return [{"description": f"via {_item_uuid(item)}",
                 "position": item.GetPosition(), "kind": "via",
                 "layers": layers}]
    layers = {int(layer) for layer in board.GetEnabledLayers().CuStack()
              if item.IsOnLayer(layer)}
    return [{"description": f"pad {_item_uuid(item)}",
             "position": item.GetPosition(), "kind": "pad", "layers": layers}]


def _terminal_components(board, net_code, net_name, score):
    """Resolve the two complete copper islands named by qualified DRC.

    DRC's displayed endpoint on an already-routed multidrop island is only a
    representative.  Routing to the entire island gives the search every legal
    boundary entry and avoids false failures caused by that arbitrary point.
    """
    items = []
    for footprint in board.GetFootprints():
        items.extend(pad for pad in footprint.Pads()
                     if int(pad.GetNetCode()) == int(net_code))
    items.extend(item for item in board.GetTracks()
                 if int(item.GetNetCode()) == int(net_code))
    by_uuid = {_item_uuid(item): item for item in items}
    pair_uuids = None
    for row in score.detail.get("unconnected_items", []):
        endpoints = row.get("items", [])
        if len(endpoints) != 2 or not all(
                f"[{net_name}]" in endpoint.get("description", "")
                for endpoint in endpoints):
            continue
        uuids = [endpoint.get("uuid") for endpoint in endpoints]
        if all(uuid in by_uuid for uuid in uuids):
            pair_uuids = uuids
            break
    if pair_uuids is None:
        pads = [item for item in items if item.GetClass() == "PAD"]
        if len(pads) == 2:
            return [[anchor for anchor in _item_anchors(board, pad)]
                    for pad in pads]
        raise ValueError(f"no exact qualified DRC open pair for {net_name}")
    connectivity = board.GetConnectivity()
    components = []
    for uuid in pair_uuids:
        connected = list(connectivity.GetConnectedItems(by_uuid[uuid]))
        anchors = []
        for item in connected:
            if int(item.GetNetCode()) == int(net_code):
                anchors.extend(_item_anchors(board, item))
        components.append(anchors)
    if not all(components):
        raise ValueError(f"empty connectivity component for {net_name}")
    return components


def _prune_component_anchors(components, cap=32):
    """Keep the boundary anchors nearest the opposite disconnected island."""
    pruned = []
    for index, anchors in enumerate(components):
        others = components[1 - index]
        ranked = sorted(anchors, key=lambda anchor: min(
            math.hypot(anchor["position"].x - other["position"].x,
                       anchor["position"].y - other["position"].y)
            for other in others))
        pruned.append(ranked[:cap])
    return pruned


def _dogbone_seats(board, code, start, width, clearance, via_dia, via_drill,
                   start_layer=pcbnew.F_Cu, radius_mm=6.0,
                   step_mm=0.1, cap=32):
    rows = []
    steps = int(round(radius_mm / step_mm))
    for dx_i in range(-steps, steps + 1):
        for dy_i in range(-steps, steps + 1):
            if not (dx_i == 0 or dy_i == 0 or abs(dx_i) == abs(dy_i)):
                continue
            dx, dy = dx_i * step_mm, dy_i * step_mm
            distance = math.hypot(dx, dy)
            if distance < max(0.4, via_dia / MM) or distance > radius_mm:
                continue
            seat = pcbnew.VECTOR2I(
                int(start.x + dx * MM), int(start.y + dy * MM))
            if not cec_fr._tap_foreign_clear(
                    board, start, seat, width, start_layer,
                    clearance, {code}):
                continue
            if not cec_fr._via_spot_clear(
                    board, seat, via_dia, clearance, {code},
                    drill_nm=via_drill, net_code=code):
                continue
            rows.append((distance, seat.x, seat.y, seat))
    rows.sort()
    return [row[-1] for row in rows[:cap]]


def _component_seats(board, anchors, route_layer, code, width, clearance,
                     via_dia, via_drill, cap=128):
    # Prefer copper already present on the requested layer. Searching dozens
    # of cross-layer dogbone seats when each island already exposes a legal
    # same-layer boundary made a small local reconnect look like a whole-board
    # via-placement problem and dominated runtime. A transition is considered
    # only when the component has no attachment on this layer.
    direct = [
        {"position": anchor["position"], "anchor": anchor,
         "via": False, "anchor_index": anchor_index}
        for anchor_index, anchor in enumerate(anchors)
        if route_layer in anchor["layers"]
    ]
    if direct:
        direct.sort(key=lambda row: (
            row["position"].x, row["position"].y, row["anchor_index"]))
        return direct[:cap]
    rows = []
    profile_name = cec_fab_profile.board_profile_name(board)
    profile = cec_fab_profile.get_profile(profile_name) if profile_name else None
    pofv = cec_fab_profile.preferred_pofv_geometry(profile)
    for anchor_index, anchor in enumerate(anchors):
        if anchor["kind"] == "pad" and pofv:
            pofv_dia = int(round(float(pofv[0]) * MM))
            pofv_drill = int(round(float(pofv[1]) * MM))
            if (cec_fr._edge_leg_clear(
                    board, anchor["position"], anchor["position"],
                    pofv_dia // 2)
                    and cec_fr._via_spot_clear(
                        board, anchor["position"], pofv_dia, clearance,
                        {code}, drill_nm=pofv_drill, net_code=code,
                        contained_layers=anchor["layers"])):
                rows.append({"position": anchor["position"],
                             "anchor": anchor, "via": True,
                             "via_dia": pofv_dia,
                             "via_drill": pofv_drill,
                             "anchor_index": anchor_index})
        for anchor_layer in sorted(anchor["layers"]):
            for position in _dogbone_seats(
                    board, code, anchor["position"], width, clearance,
                    via_dia, via_drill, start_layer=anchor_layer, cap=16):
                rows.append({"position": position,
                             "anchor": {**anchor, "attach_layer": anchor_layer},
                             "via": True, "via_dia": via_dia,
                             "via_drill": via_drill,
                             "anchor_index": anchor_index})
    rows.sort(key=lambda row: (
        row["via"], row["position"].x, row["position"].y,
        row["anchor_index"]))
    return rows[:cap]


def _grid(board, step_mm, terminals=(), margin_mm=6.0):
    box = board.GetBoardEdgesBoundingBox()
    left, right = box.GetLeft() / MM, box.GetRight() / MM
    top, bottom = box.GetTop() / MM, box.GetBottom() / MM
    if terminals:
        tx = [point.x / MM for point in terminals]
        ty = [point.y / MM for point in terminals]
        left = max(left, min(tx) - margin_mm)
        right = min(right, max(tx) + margin_mm)
        top = max(top, min(ty) - margin_mm)
        bottom = min(bottom, max(ty) + margin_mm)
    x0 = math.floor(left / step_mm)
    x1 = math.ceil(right / step_mm)
    y0 = math.floor(top / step_mm)
    y1 = math.ceil(bottom / step_mm)
    return {
        (ix, iy): pcbnew.VECTOR2I(
            int(round(ix * step_mm * MM)), int(round(iy * step_mm * MM)))
        for ix in range(x0, x1 + 1)
        for iy in range(y0, y1 + 1)
    }


def _smooth(points, clear):
    result = [points[0]]
    index = 0
    while index < len(points) - 1:
        chosen = index + 1
        for candidate in range(len(points) - 1, index, -1):
            if (_octilinear(points[index], points[candidate])
                    and clear(points[index], points[candidate])):
                chosen = candidate
                break
        result.append(points[chosen])
        index = chosen
    return result


def _attachment(a, b, clear):
    """Return the shortest clear 0/45/90 one-bend attachment, if any."""
    dx, dy = b.x - a.x, b.y - a.y
    diagonal = min(abs(dx), abs(dy))
    sx = 0 if dx == 0 else (1 if dx > 0 else -1)
    sy = 0 if dy == 0 else (1 if dy > 0 else -1)
    candidates = [[a, b]]
    candidates += [[a, pcbnew.VECTOR2I(a.x, b.y), b],
                   [a, pcbnew.VECTOR2I(b.x, a.y), b]]
    if diagonal:
        candidates += [[a, pcbnew.VECTOR2I(
            a.x + sx * diagonal, a.y + sy * diagonal), b],
                       [a, pcbnew.VECTOR2I(
            b.x - sx * diagonal, b.y - sy * diagonal), b]]
    valid = []
    for points in candidates:
        legs = [(start, end) for start, end in zip(points, points[1:])
                if start != end]
        if (legs and all(_octilinear(start, end) and clear(start, end)
                         for start, end in legs)):
            length = sum(math.hypot(start.x - end.x, start.y - end.y)
                         for start, end in legs)
            valid.append((length, points))
    return min(valid, key=lambda row: row[0])[1] if valid else None


def find_channel(board, net_name, layer_name, score, grid_mm=0.5):
    code = _net_code(board, net_name)
    components = _prune_component_anchors(
        _terminal_components(board, code, net_name, score))
    layer = board.GetLayerID(layer_name)
    resolver = cec_fr._project_netclass_resolver(board.GetFileName())
    spec = resolver(net_name)
    width = int(round(float(spec["track_width"]) * MM))
    clearance = int(round(float(spec["clearance"]) * MM))
    via_dia = int(round(float(spec["via_diameter"]) * MM))
    via_drill = int(round(float(spec["via_drill"]) * MM))
    starts = _component_seats(
        board, components[0], layer, code, width, clearance,
        via_dia, via_drill)
    goals = _component_seats(
        board, components[1], layer, code, width, clearance,
        via_dia, via_drill)
    if not starts or not goals:
        return None, {"reason": "no_project_via_dogbone_seat",
                      "start_seats": len(starts), "goal_seats": len(goals)}

    zones, copper = cec_fr._foreign_shape_indexes(board, layer, {code})
    # Ordinary collision clearance cannot see electromagnetic coupling.  Fold
    # the release authority into expansion: an unshielded nearby cross-layer
    # leg must be approximately perpendicular, and a same-layer close parallel
    # run is unavailable.  Treating shield presence conservatively here cannot
    # waive a route; the independent final checker remains authoritative.
    netclass = (resolver(net_name) or {}).get("name")
    route_role = cec_field_coupling.classify_net(
        net_name, netclass=netclass)
    field_segments = []
    field_resolver = cec_field_coupling._project_netclass_resolver(
        board.GetFileName())
    for item in board.GetTracks():
        if (item.GetClass() != "PCB_TRACK" or not item.GetNetname()
                or item.GetNetCode() == code):
            continue
        other_name = item.GetNetname()
        other_role = cec_field_coupling.classify_net(
            other_name,
            netclass=(field_resolver(other_name)
                      if field_resolver else None))
        related = ((route_role["aggressor"] and other_role["victim"])
                   or (route_role["victim"] and other_role["aggressor"]))
        if not related or cec_field_coupling._pair_mates(
                net_name, other_name):
            continue
        start, end = item.GetStart(), item.GetEnd()
        if start == end:
            continue
        lid = int(item.GetLayer())
        field_segments.append({
            "net": other_name,
            "layer": cec_fab_profile.COPPER_LAYER_IDS.get(
                lid, board.GetLayerName(lid)),
            "a": (start.x / MM, start.y / MM),
            "b": (end.x / MM, end.y / MM),
            "width_mm": item.GetWidth() / MM,
        })
    route_layer_name = cec_fab_profile.COPPER_LAYER_IDS.get(
        int(layer), board.GetLayerName(layer))
    field_rejections = {"same_layer_parallel": 0,
                        "unshielded_oblique": 0}

    def field_clear(a, b):
        if not field_segments or a == b:
            return True
        candidate = {
            "net": net_name, "layer": route_layer_name,
            "a": (a.x / MM, a.y / MM),
            "b": (b.x / MM, b.y / MM),
            "width_mm": width / MM,
        }
        for other in field_segments:
            center = cec_field_coupling._segment_distance(candidate, other)
            edge_gap = center - (candidate["width_mm"]
                                 + other["width_mm"]) / 2.0
            if edge_gap > 1.0 + 1e-9:
                continue
            angle = cec_field_coupling._acute_angle(candidate, other)
            if candidate["layer"] == other["layer"]:
                overlap = cec_field_coupling._parallel_overlap(
                    candidate, other)
                if angle <= 15.0 + 1e-9 and overlap >= 1.0 - 1e-9:
                    field_rejections["same_layer_parallel"] += 1
                    return False
            elif angle < 75.0 - 1e-9:
                # Filled-plane shielding can make this legal, but proving a
                # plane for every search edge is expensive and brittle.  The
                # conservative search finds a perpendicular/separated route;
                # final admission may later accept a shielded optimization.
                field_rejections["unshielded_oblique"] += 1
                return False
        return True
    clear_cache = {}

    def clear(a, b):
        ka, kb = (a.x, a.y), (b.x, b.y)
        key = (ka, kb) if ka <= kb else (kb, ka)
        if key not in clear_cache:
            clear_cache[key] = bool(
                cec_fr._edge_leg_clear(board, a, b, width // 2)
                and cec_fr._snapshot_foreign_clear(
                    a, b, width, clearance, zones, copper)
                and field_clear(a, b))
        return clear_cache[key]

    nodes = _grid(
        board, grid_mm,
        [row["position"] for row in starts + goals])
    free = {key: clear(point, pcbnew.VECTOR2I(point.x + 1, point.y))
            for key, point in nodes.items()}
    sources, target_nodes = [], {}
    # A terminal can sit inside the field-exclusion halo of a nearby victim;
    # reaching the first safe grid line may require a longer perpendicular
    # escape than the ordinary 1.25 mm grid snap.  Expand only when classified
    # field interactions exist; exact copper and field guards still validate
    # every attachment leg.
    attachment_reach_mm = 2.5 if field_segments else 1.25
    for key, point in nodes.items():
        if not free[key]:
            continue
        for seat_index, seat_row in enumerate(starts):
            seat = seat_row["position"]
            distance = math.hypot(point.x - seat.x, point.y - seat.y) / MM
            attachment = (_attachment(seat, point, clear)
                          if distance <= attachment_reach_mm else None)
            if attachment:
                sources.append((distance, key, seat_index, attachment))
                break
        for seat_index, seat_row in enumerate(goals):
            seat = seat_row["position"]
            distance = math.hypot(point.x - seat.x, point.y - seat.y) / MM
            attachment = (_attachment(point, seat, clear)
                          if distance <= attachment_reach_mm else None)
            if attachment:
                target_nodes[key] = (distance, seat_index, attachment)
                break
    if not sources or not target_nodes:
        return None, {"reason": "no_octilinear_grid_attachment",
                      "sources": len(sources), "goals": len(target_nodes)}

    goal_keys = list(target_nodes)
    heuristic = lambda key: min(
        math.hypot(key[0] - goal[0], key[1] - goal[1])
        for goal in goal_keys) * grid_mm
    queue, distance, previous, start_index, start_attachment = [], {}, {}, {}, {}
    for cost, key, seat_index, attachment in sources:
        if cost < distance.get(key, math.inf):
            distance[key], previous[key], start_index[key] = cost, None, seat_index
            start_attachment[key] = attachment
            heapq.heappush(queue, (cost + heuristic(key), cost, key))
    directions = ((-1, -1), (-1, 0), (-1, 1), (0, -1),
                  (0, 1), (1, -1), (1, 0), (1, 1))
    end, expanded = None, 0
    while queue:
        _estimate, cost, key = heapq.heappop(queue)
        if cost != distance.get(key):
            continue
        expanded += 1
        if key in target_nodes:
            end = key
            break
        for dx, dy in directions:
            neighbor = (key[0] + dx, key[1] + dy)
            if (neighbor not in nodes or not free[neighbor]
                    or not clear(nodes[key], nodes[neighbor])):
                continue
            next_cost = cost + grid_mm * (math.sqrt(2) if dx and dy else 1)
            if next_cost < distance.get(neighbor, math.inf):
                distance[neighbor] = next_cost
                previous[neighbor] = key
                start_index[neighbor] = start_index[key]
                start_attachment[neighbor] = start_attachment[key]
                heapq.heappush(
                    queue, (next_cost + heuristic(neighbor), next_cost, neighbor))
    if end is None:
        return None, {"reason": "coarse_channel_exhausted",
                      "expanded": expanded, "grid_nodes": len(nodes)}

    keys, cursor = [], end
    while cursor is not None:
        keys.append(cursor)
        cursor = previous[cursor]
    keys.reverse()
    raw = (start_attachment[end]
           + [nodes[key] for key in keys[1:]]
           + target_nodes[end][2][1:])
    points = _smooth(raw, clear)
    start_row = starts[start_index[end]]
    goal_row = goals[target_nodes[end][1]]
    route = {"net": net_name, "code": code, "layer": layer,
             "layer_name": layer_name,
             "terminals": [start_row["anchor"], goal_row["anchor"]],
             "points": points, "width": width,
             "via_dia": via_dia, "via_drill": via_drill,
             "start_via": start_row["via"],
             "goal_via": goal_row["via"],
             "start_via_dia": start_row.get("via_dia", via_dia),
             "start_via_drill": start_row.get("via_drill", via_drill),
             "goal_via_dia": goal_row.get("via_dia", via_dia),
             "goal_via_drill": goal_row.get("via_drill", via_drill)}
    return route, {"reason": "found", "expanded": expanded,
                   "raw_points": len(raw), "smoothed_points": len(points),
                   "start_seats": len(starts), "goal_seats": len(goals),
                   "field_guard_rejections": field_rejections}


def add_channel(board, route):
    start_pad = route["terminals"][0]["position"]
    goal_pad = route["terminals"][1]["position"]
    points = route["points"]
    start_layer = route["terminals"][0].get(
        "attach_layer", route["layer"])
    goal_layer = route["terminals"][1].get(
        "attach_layer", route["layer"])
    legs = ([(start_pad, points[0], start_layer)]
            + [(a, b, route["layer"])
               for a, b in zip(points, points[1:])]
            + [(points[-1], goal_pad, goal_layer)])
    for start, end, layer in legs:
        if start == end:
            continue
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(start)
        track.SetEnd(end)
        track.SetWidth(route["width"])
        track.SetLayer(layer)
        track.SetNetCode(route["code"])
        board.Add(track)
    via_points = []
    if route["start_via"]:
        via_points.append((points[0], route["start_via_dia"],
                           route["start_via_drill"]))
    if route["goal_via"]:
        via_points.append((points[-1], route["goal_via_dia"],
                           route["goal_via_drill"]))
    for point, diameter, drill in via_points:
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(point)
        via.SetWidth(diameter)
        via.SetDrill(drill)
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetNetCode(route["code"])
        board.Add(via)


def route_one(board_path, out_path, net_name, layers, grid_mm=0.5):
    before = cec_score.score(board_path, None)
    directory = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(directory, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix="cec-coarse-channel-", suffix=".kicad_pcb",
        dir=directory, delete=False)
    trial = handle.name
    handle.close()
    shutil.copy2(board_path, trial)
    cec_fr.copy_project_sidecars(board_path, trial)
    board = pcbnew.LoadBoard(trial)
    board.BuildConnectivity()
    attempts = []
    for layer in layers:
        route, detail = find_channel(board, net_name, layer, before, grid_mm)
        attempts.append({"layer": layer, **detail})
        if route is None:
            continue
        add_channel(board, route)
        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.BuildConnectivity()
        pcbnew.SaveBoard(trial, board)
        after = cec_score.score(trial, None)
        admission = cec_stage_admission.evaluate(
            before, after, require_strict=True)
        if admission.get("accepted"):
            shutil.copy2(trial, out_path)
            cec_fr.copy_project_sidecars(trial, out_path)
            os.remove(trial)
            return {"adopted": True, "net": net_name, "layer": layer,
                    "attempts": attempts, "admission": admission,
                    "before": vars(before), "after": vars(after)}
        return {"adopted": False, "net": net_name, "attempts": attempts,
                "admission": admission, "before": vars(before),
                "after": vars(after), "trial_path": trial}
    os.remove(trial)
    return {"adopted": False, "net": net_name, "attempts": attempts,
            "admission": {"accepted": False, "decision": "no_coarse_channel"},
            "before": vars(before)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("board")
    parser.add_argument("out")
    parser.add_argument("--net", required=True)
    parser.add_argument("--layers", default="F.Cu,PWR,SIG2,B.Cu")
    parser.add_argument("--grid-mm", type=float, default=0.5)
    parser.add_argument("--report")
    args = parser.parse_args()
    result = route_one(
        os.path.abspath(args.board), os.path.abspath(args.out), args.net,
        [name.strip() for name in args.layers.split(",") if name.strip()],
        float(args.grid_mm))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as sink:
            json.dump(result, sink, indent=2, sort_keys=True, default=str)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    raise SystemExit(0 if result.get("adopted") else 1)


if __name__ == "__main__":
    main()
