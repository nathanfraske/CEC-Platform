#!/usr/bin/env python3
"""Routing preflight: pin access, fanout, stack policy, and congestion.

This is a read-only planning stage.  It turns board geometry into explicit
evidence before a detailed router is allowed to spend minutes on a candidate:

* exact declared routing layers and reference-plane adjacency;
* per-pad octilinear escape availability and POFV eligibility;
* deterministic array-package fanout assignments;
* negotiated-congestion summaries on every legal routing layer; and
* hierarchical net tiers for escape, critical-pair, power, and residual work.

No result relaxes KiCad DRC or fabrication rules.  It is safe to run in a wave
worker and JSON output is intentionally compact enough for the dashboard.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


_DIRECTIONS = (
    ("E", 1.0, 0.0), ("NE", math.sqrt(0.5), -math.sqrt(0.5)),
    ("N", 0.0, -1.0), ("NW", -math.sqrt(0.5), -math.sqrt(0.5)),
    ("W", -1.0, 0.0), ("SW", -math.sqrt(0.5), math.sqrt(0.5)),
    ("S", 0.0, 1.0), ("SE", math.sqrt(0.5), math.sqrt(0.5)),
)


def _compile_prospective_route_reservations(board_path, board, pour_hints):
    """Solve exact current corridors for an unfrozen placement finalist.

    ``uniform_stamp`` is a visual/interchangeability recipe, not routed-copper
    authority.  Placement selection nevertheless happens before pour-first can
    freeze a winner, so simply refusing the stamp disabled all exact pin-access
    adjudication on those boards.  Use only the stamp's *net/layer intent* as
    input to the same territory planner used by pour-first, then reserve the
    planner's actual path masks, Manhattan copper, and bridge barrels.  No
    stamped polygon is trusted or forwarded.

    This authority is deliberately scoped to placement preflight by the
    ``CEC_PROSPECTIVE_POUR_RESERVATIONS`` environment handshake.  Detailed
    routing still requires the later complete ``CEC_POURFIRST_STATE`` freeze.
    """
    import cec_fab_profile
    import cec_pour_plan
    import cec_slab_pour
    import cec_synth_pipeline

    layers_by_net = collections.defaultdict(list)
    for row in pour_hints or ():
        net = str((row or {}).get("net") or "")
        if not net:
            continue
        layers = tuple((row or {}).get("layers") or ())
        if not layers and (row or {}).get("layer"):
            layers = (str(row["layer"]),)
        for layer in layers or ("F.Cu",):
            layer = str(layer)
            if layer not in layers_by_net[net]:
                layers_by_net[net].append(layer)
    asks = [
        {"net": net, "layers": tuple(layers),
         "provenance": "prospective_route_preflight"}
        for net, layers in sorted(layers_by_net.items())
    ]
    if not asks:
        return {"enabled": False, "corridors": [], "report": {},
                "fingerprint": None, "source": "prospective_full_board",
                "reason": "no_current_domain_asks"}

    collect = {}
    lanes, vias, planner_report = cec_pour_plan.plan_pours(
        board, asks, manifolds=True, collect=collect,
        relief_diagnostics=False)
    grid = collect.get("_grid")
    if grid is None:
        raise RuntimeError("prospective pour planner returned no exact grid")

    corridors = []
    report = {}
    reserved_nets = set()
    for net, row in sorted(collect.items()):
        if net == "_grid" or not isinstance(row, dict):
            continue
        exact, reserved = cec_slab_pour.reservation_from_search(
            net, row.get("ok", False), row.get("path_cells") or {},
            row.get("bridges") or [], row.get("rcells") or {},
            row.get("foreign") or {}, grid)
        report[net] = {
            "reserved": bool(reserved),
            "rects": len(exact) if reserved else 0,
            "path_found": bool((planner_report.get(net) or {}).get(
                "path_found", False)),
        }
        if reserved:
            reserved_nets.add(net)
            corridors.extend(exact)

    # The path-mask reservation protects the searched spine.  Also project
    # the exact realized Manhattan copper so a finalist cannot place a signal
    # through a manifold or terminal flare outside that spine.
    pour_rect_count = 0
    for lane in lanes or ():
        net = str((lane or {}).get("net") or "")
        if net not in reserved_nets:
            continue
        rectangles, approximate = \
            cec_synth_pipeline._orthogonal_polygon_rectangles(
                (lane or {}).get("polygon") or ())
        if approximate:
            raise RuntimeError(
                "prospective pour planner emitted non-Manhattan geometry")
        for index, (x0, y0, x1, y1) in enumerate(rectangles):
            if x1 <= x0 or y1 <= y0:
                raise RuntimeError(
                    "prospective pour planner emitted an inverted rectangle "
                    "for %s on %s: %r" % (
                        net, str(lane.get("layer") or "F.Cu"),
                        (x0, y0, x1, y1)))
            corridors.append({
                "net": net, "layer": str(lane.get("layer") or "F.Cu"),
                "kind": "prospective_pour",
                "name": str(lane.get("name") or
                            "prospective:%s:%d" % (net, index)),
                "x0": float(x0), "y0": float(y0),
                "x1": float(x1), "y1": float(y1),
            })
            pour_rect_count += 1

    via_rows = [via for via in (vias or ())
                if str((via or {}).get("net") or "") in reserved_nets]
    if via_rows:
        corridors.extend(cec_slab_pour.bridge_via_reservations(
            via_rows, cec_fab_profile.routing_layers(
                board, hint=board_path, include_power=True)))

    digest = hashlib.sha256(json.dumps({
        "corridors": corridors, "report": report,
    }, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8")).hexdigest()
    return {
        "enabled": bool(corridors), "corridors": corridors,
        "report": report, "fingerprint": digest,
        "source": "prospective_full_board",
        "prospective": True, "ask_count": len(asks),
        "reserved_nets": sorted(reserved_nets),
        "pour_rect_count": pour_rect_count,
        "bridge_via_count": len(via_rows),
    }


def compile_route_reservations(board_path, *, board=None):
    """Compile the exact routed-object reservation used by detailed routing.

    The route recipe is environment-scoped by ``cec_synth_pipeline._oracle_env``.
    When enabled, this calls the same PourPlan loader, ask merge, locked-net
    filtering, and over-under search that ``route_once`` consumes. It raises on
    an enabled-but-broken compiler because a rail-free placement score is not
    comparable to the board the detailed router will actually receive.
    """
    if os.environ.get("CEC_POUR_RESERVE", "0") != "1":
        return {"enabled": False, "corridors": [], "report": {},
                "fingerprint": None}
    import pcbnew
    import cec_fab_profile
    import cec_fr
    import cec_slab_pour
    import cec_synth_pipeline

    state_path = os.environ.get("CEC_POURFIRST_STATE", "").strip()
    if state_path:
        state = cec_fr._pourfirst_state()
        if state.get("placement_scope") != "complete":
            raise RuntimeError(
                "pour reservation state is not a complete-placement authority")
        frozen = tuple(state.get("frozen_nets") or ())
        corridors = list(state.get("corridors") or ())
        report = dict(state.get("reserve_report") or {})
        if not frozen or not corridors or any(
                not (report.get(net) or {}).get("reserved")
                for net in frozen):
            raise RuntimeError(
                "pour reservation state is incomplete: frozen=%d "
                "corridors=%d" % (len(frozen), len(corridors)))
        if any(str((row or {}).get("provenance") or "") == "uniform_stamp"
               for row in state.get("pours") or ()):
            raise RuntimeError(
                "legacy uniform_stamp geometry cannot own route reservations")
        # A frozen routed-power transition is a through-barrel, not merely a
        # point inside one of the lane masks. Pour-first already exports these
        # exact barrel keepouts to placement, but older route-reservation
        # compilation dropped them and allowed a precision pair to occupy a
        # future drill clearance. Replay then correctly refused to drill
        # through the locked signal and the board failed after an otherwise
        # successful priority route. Project every selected barrel onto every
        # legal routing layer using the same generic geometry primitive as the
        # power compiler. Deduplicate for forward compatibility with states
        # that may persist these rows directly.
        state_vias = list(state.get("vias") or ())
        signatures = {
            (str(row.get("net") or ""),
             str(row.get("layer") or ""),
             str(row.get("kind") or ""),
             round(float(row.get("x0") or 0.0), 6),
             round(float(row.get("y0") or 0.0), 6),
             round(float(row.get("x1") or 0.0), 6),
             round(float(row.get("y1") or 0.0), 6))
            for row in corridors
        }
        if state_vias:
            reservation_board = board or pcbnew.LoadBoard(board_path)
            if reservation_board is None:
                raise RuntimeError(
                    "frozen via reservation could not load its board")
            via_rows = cec_slab_pour.bridge_via_reservations(
                state_vias,
                cec_fab_profile.routing_layers(
                    reservation_board, hint=board_path,
                    include_power=True))
            for row in via_rows:
                signature = (
                    str(row.get("net") or ""),
                    str(row.get("layer") or ""),
                    str(row.get("kind") or ""),
                    round(float(row.get("x0") or 0.0), 6),
                    round(float(row.get("y0") or 0.0), 6),
                    round(float(row.get("x1") or 0.0), 6),
                    round(float(row.get("y1") or 0.0), 6))
                if signature not in signatures:
                    corridors.append(row)
                    signatures.add(signature)
        # Corridors reserve the routed spine, but a concave pour can include
        # terminal/manifold copper outside that spine.  Precision and global
        # routing must see the same exact Manhattan rectangle union used by the
        # independent foreign-copper checker.  This is intentionally not a
        # polygon bounding box: hook pockets remain legal routing territory.
        import cec_constraints
        frozen_pour_rows = []
        for region in cec_constraints.high_current_pour_regions(board_path):
            row = dict(region)
            row.update({
                "kind": "frozen_pour",
                "name": "frozen-pour:%s" % region.get("net", ""),
            })
            signature = (
                str(row.get("net") or ""),
                str(row.get("layer") or ""),
                str(row.get("kind") or ""),
                round(float(row.get("x0") or 0.0), 6),
                round(float(row.get("y0") or 0.0), 6),
                round(float(row.get("x1") or 0.0), 6),
                round(float(row.get("y1") or 0.0), 6))
            if signature not in signatures:
                corridors.append(row)
                signatures.add(signature)
                frozen_pour_rows.append(row)
        digest = hashlib.sha256(json.dumps({
            "corridors": corridors, "report": report,
        }, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8")).hexdigest()
        return {"enabled": True, "corridors": corridors, "report": report,
                "fingerprint": digest, "source": "frozen_full_board",
                "state_path": state_path,
                "frozen_nets": list(frozen),
                "frozen_via_count": len(state_vias),
                "frozen_pour_rect_count": len(frozen_pour_rows)}

    board = board or pcbnew.LoadBoard(board_path)
    if board is None:
        raise RuntimeError("reservation compiler could not load board")
    _hints, pours, _rules = cec_synth_pipeline._oracle_hints_pours(board_path)
    if any(str((row or {}).get("provenance") or "") == "uniform_stamp"
           for row in pours or ()):
        if os.environ.get("CEC_PROSPECTIVE_POUR_RESERVATIONS", "0") == "1":
            return _compile_prospective_route_reservations(
                board_path, board, pours)
        raise RuntimeError(
            "legacy uniform_stamp pour hints are not exact route reservations")
    compiled = cec_slab_pour.reserve_pour_corridors(
        board, pours, verbose=False)
    corridors = list(compiled.get("corridors") or ())
    report = dict(compiled.get("report") or {})
    digest = hashlib.sha256(json.dumps({
        "corridors": corridors, "report": report,
    }, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8")).hexdigest()
    return {"enabled": True, "corridors": corridors, "report": report,
            "fingerprint": digest}


def apply_route_reservations(conns, stackup, blocked_cells, reservations,
                             height, width):
    """Project routed-object ownership into the negotiated global problem.

    Successfully reserved nets are removed because the routed object owns all
    of their pads. Every other connection receives the reservation cells as
    hard foreign copper, unioned with the exact pad/body obstacles already
    produced by ``build_problem``. The returned stackup arrays remain aligned
    with the filtered connection list.
    """
    reservation = dict(reservations or {})
    if not reservation.get("enabled"):
        return tuple(conns), dict(stackup), tuple(blocked_cells), {
            "owned_nets": [], "cell_count": 0}
    report = reservation.get("report") or {}
    owned_nets = {
        str(net) for net, row in report.items()
        if isinstance(row, dict) and row.get("reserved")}
    layer_names = tuple(stackup.get("layer_names") or ())
    layer_index = {name: index for index, name in enumerate(layer_names)}
    grid_mm = float(stackup.get("grid_mm", 1.0) or 1.0)
    origin = tuple(stackup.get("grid_origin_mm") or (0.0, 0.0))
    if len(origin) != 2 or grid_mm <= 0:
        raise ValueError("route reservation needs a valid grid origin/pitch")
    owners = collections.defaultdict(set)
    for row in reservation.get("corridors") or ():
        layer_name = str(row.get("layer", ""))
        if layer_name not in layer_index:
            raise ValueError("reservation uses non-routing layer %r" % layer_name)
        x0, y0, x1, y1 = (float(row[name])
                          for name in ("x0", "y0", "x1", "y1"))
        gx0 = max(0, int(math.floor((x0 - origin[0]) / grid_mm)))
        gy0 = max(0, int(math.floor((y0 - origin[1]) / grid_mm)))
        gx1 = min(int(width) - 1, int(math.ceil(
            (x1 - origin[0]) / grid_mm) - 1))
        gy1 = min(int(height) - 1, int(math.ceil(
            (y1 - origin[1]) / grid_mm) - 1))
        if gx1 < gx0 or gy1 < gy0:
            continue
        layer = layer_index[layer_name]
        net = str(row.get("net", ""))
        for gy in range(gy0, gy1 + 1):
            for gx in range(gx0, gx1 + 1):
                owners[(layer, gy, gx)].add(net)

    keep = [index for index, conn in enumerate(conns)
            if str(conn[0]) not in owned_nets]
    filtered_conns = tuple(conns[index] for index in keep)
    filtered_blocked = []
    for index in keep:
        net = str(conns[index][0])
        cells = set(blocked_cells[index])
        cells.update(cell for cell, cell_owners in owners.items()
                     if any(owner != net for owner in cell_owners))
        filtered_blocked.append(cells)
    filtered_stackup = dict(stackup)
    for key in ("allowed_layers_by_conn", "net_kinds", "netclasses"):
        values = tuple(stackup.get(key) or ())
        if len(values) != len(conns):
            raise ValueError("stackup %s length does not match connections" % key)
        filtered_stackup[key] = tuple(values[index] for index in keep)
    filtered_stackup.update({
        "reservation_enabled": True,
        "reservation_fingerprint": reservation.get("fingerprint"),
        "reservation_rect_count": len(reservation.get("corridors") or ()),
        "reservation_cell_count": len(owners),
        "reservation_owned_nets": tuple(sorted(owned_nets)),
        "reservation_connections_removed": len(conns) - len(filtered_conns),
    })
    return (filtered_conns, filtered_stackup, tuple(filtered_blocked), {
        "owned_nets": sorted(owned_nets), "cell_count": len(owners)})


def apply_preowned_connections(conns, stackup, blocked_cells, owned_nets):
    """Remove nets already completed by a higher-priority exact stage."""
    owned = {str(net) for net in (owned_nets or ()) if net}
    if not owned:
        return tuple(conns), dict(stackup), tuple(blocked_cells)
    keep = [index for index, conn in enumerate(conns)
            if str(conn[0]) not in owned]
    filtered = dict(stackup)
    for key in ("allowed_layers_by_conn", "net_kinds", "netclasses"):
        values = tuple(stackup.get(key) or ())
        if len(values) != len(conns):
            raise ValueError("stackup %s length does not match connections" % key)
        filtered[key] = tuple(values[index] for index in keep)
    filtered["preowned_nets"] = tuple(sorted(owned))
    filtered["preowned_connections_removed"] = len(conns) - len(keep)
    return (tuple(conns[index] for index in keep), filtered,
            tuple(blocked_cells[index] for index in keep))


def _segment_hits_rect(x0, y0, x1, y1, rect):
    """Liang-Barsky segment/closed-rectangle intersection."""
    rx0, ry0, rx1, ry1 = rect
    dx, dy = x1 - x0, y1 - y0
    p = (-dx, dx, -dy, dy)
    q = (x0 - rx0, rx1 - x0, y0 - ry0, ry1 - y0)
    lo, hi = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-15:
            if qi < 0:
                return False
            continue
        ratio = qi / pi
        if pi < 0:
            lo = max(lo, ratio)
        else:
            hi = min(hi, ratio)
        if lo > hi:
            return False
    return True


def _pad_records(board, routing_layers, *, pofv_geometry=None):
    import pcbnew
    layer_ids = {name: board.GetLayerID(name) for name in routing_layers}
    records = []
    via_radius_nm = (int(round(pofv_geometry[0] * 1e6 / 2.0))
                     if pofv_geometry else None)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            net = pad.GetNetname()
            if not net:
                continue
            layers = tuple(name for name, layer_id in layer_ids.items()
                           if layer_id >= 0 and pad.IsOnLayer(layer_id))
            if not layers:
                continue
            pos = pad.GetPosition()
            boxes = []
            for name in layers:
                try:
                    box = pad.GetEffectiveShape(layer_ids[name]).BBox()
                    boxes.append((box.GetX() / 1e6, box.GetY() / 1e6,
                                  (box.GetX() + box.GetWidth()) / 1e6,
                                  (box.GetY() + box.GetHeight()) / 1e6))
                except Exception:                       # noqa: BLE001
                    pass
            size = pad.GetSize()
            fallback = (pos.x / 1e6 - size.x / 2e6,
                        pos.y / 1e6 - size.y / 2e6,
                        pos.x / 1e6 + size.x / 2e6,
                        pos.y / 1e6 + size.y / 2e6)
            bbox = (min(box[0] for box in boxes), min(box[1] for box in boxes),
                    max(box[2] for box in boxes), max(box[3] for box in boxes)) \
                if boxes else fallback
            try:
                smd = int(pad.GetAttribute()) == int(pcbnew.PAD_ATTRIB_SMD)
            except Exception:                           # noqa: BLE001
                smd = False
            pofv = False
            if smd and via_radius_nm is not None:
                try:
                    import cec_fab_profile
                    pofv = bool(cec_fab_profile._pad_contains_circle(
                        pad, pos, via_radius_nm))
                except Exception:                       # noqa: BLE001
                    pofv = False
            records.append({
                "ref": ref, "pad": str(pad.GetNumber()), "net": net,
                "x": pos.x / 1e6, "y": pos.y / 1e6,
                "bbox": bbox, "layers": layers, "smd": smd,
                "pofv": pofv,
            })
    return records


def analyze_pin_access(board_path=None, *, escape_mm=1.25,
                       clearance_mm=0.20, board_db=None, placements=None,
                       use_spatial_index=True):
    """Return deterministic octilinear escape options for every routed pad.

    ``board_db`` is an optional immutable :class:`cec_boarddb.BoardDB`.  It
    lets placement repair apply an exact translation/180-degree delta without
    serializing and reparsing a complete KiCad board.  The ordinary board-path
    entry point constructs the same database once and remains API compatible.
    """
    import cec_boarddb

    if board_db is None:
        if not board_path:
            raise ValueError("board_path or board_db is required")
        board_db = cec_boarddb.BoardDB.from_board(board_path)
    view = board_db.view(placements)
    pads = view.pad_records
    routing_layers = board_db.routing_layers
    pofv_geometry = board_db.pofv_geometry_mm
    profile_name = board_db.profile
    edge = board_db.edge_bbox
    edge_rect = (edge[0] + clearance_mm,
                 edge[1] + clearance_mm,
                 edge[2] - clearance_mm,
                 edge[3] - clearance_mm)
    spatial = view.spatial_index if use_spatial_index else None

    rows = []
    by_ref = collections.defaultdict(list)
    for index, pad in enumerate(pads):
        options = []
        blocked_options = []
        for name, dx, dy in _DIRECTIONS:
            x1 = pad["x"] + dx * escape_mm
            y1 = pad["y"] + dy * escape_mm
            if not (edge_rect[0] <= x1 <= edge_rect[2]
                    and edge_rect[1] <= y1 <= edge_rect[3]):
                continue
            clear_layers = []
            blocked_layers = []
            for layer in pad["layers"]:
                blockers = []
                candidate_indices = (spatial.query_segment(
                    layer, pad["x"], pad["y"], x1, y1,
                    margin=clearance_mm)
                                     if spatial is not None
                                     else range(len(pads)))
                for other_index in candidate_indices:
                    other = pads[other_index]
                    if other_index == index or layer not in other["layers"]:
                        continue
                    if other["net"] == pad["net"]:
                        continue
                    rect = (other["bbox"][0] - clearance_mm,
                            other["bbox"][1] - clearance_mm,
                            other["bbox"][2] + clearance_mm,
                            other["bbox"][3] + clearance_mm)
                    if _segment_hits_rect(pad["x"], pad["y"], x1, y1, rect):
                        blockers.append({
                            key: other[key]
                            for key in ("ref", "pad", "net", "x", "y")})
                # KiCad may change footprint enumeration order after a
                # save/reload. Evidence order is part of deterministic repair
                # ranking and must come from identity, not file traversal.
                blockers.sort(key=lambda row: (
                    row["ref"], row["pad"], row["net"],
                    round(row["x"], 6), round(row["y"], 6)))
                blockers = blockers[:8]
                if not blockers:
                    clear_layers.append(layer)
                else:
                    blocked_layers.append({"layer": layer,
                                           "blockers": blockers})
            if clear_layers:
                options.append({"direction": name,
                                "layers": tuple(clear_layers)})
            if blocked_layers:
                blocked_options.append({"direction": name,
                                        "layers": blocked_layers})
        mode = ("trace" if options else
                "via_in_pad" if pad["pofv"] else "blocked")
        row = {key: pad[key] for key in ("ref", "pad", "net", "x", "y")}
        row.update({"mode": mode, "directions": tuple(
            option["direction"] for option in options),
            "options": options, "blocked_options": blocked_options,
            "pofv": pad["pofv"]})
        rows.append(row)
        by_ref[pad["ref"]].append(row)

    blocked = [row for row in rows if row["mode"] == "blocked"]
    constrained = [row for row in rows
                   if row["mode"] == "trace" and len(row["directions"]) <= 2]
    footprints = []
    for ref, items in sorted(by_ref.items()):
        footprints.append({
            "ref": ref, "pads": len(items),
            "blocked": sum(item["mode"] == "blocked" for item in items),
            "via_in_pad": sum(item["mode"] == "via_in_pad" for item in items),
            "constrained": sum(item in constrained for item in items),
            "min_directions": min((len(item["directions"]) for item in items),
                                  default=0),
        })
    return {
        "pads": rows, "pad_count": len(rows),
        "blocked_count": len(blocked),
        "constrained_count": len(constrained),
        "blocked": blocked, "constrained": constrained,
        "footprints": footprints,
        "escape_mm": float(escape_mm), "clearance_mm": float(clearance_mm),
        "pofv_geometry_mm": pofv_geometry,
        "routing_layers": tuple(routing_layers),
        "profile": profile_name,
        "geometry": {
            "schema": board_db.SCHEMA,
            "base_fingerprint": board_db.fingerprint,
            "view_fingerprint": view.fingerprint,
            **view.invalidation,
        },
    }


def plan_array_fanouts(pin_access):
    """Create deterministic ring/quadrant fanout cells for array packages.

    A package qualifies as an array when it has at least 64 routed pads and at
    least eight distinct X and Y coordinates. Outer two rings prefer dogbones;
    deeper rings use declared POFV when it fits. A blocked deep pad without
    POFV is reported as a hard preflight failure rather than guessed through.
    """
    by_ref = collections.defaultdict(list)
    for row in pin_access["pads"]:
        by_ref[row["ref"]].append(row)
    route_layers = tuple(pin_access["routing_layers"])
    arrays = []
    for ref, pads in sorted(by_ref.items()):
        xs = sorted(set(round(pad["x"], 6) for pad in pads))
        ys = sorted(set(round(pad["y"], 6) for pad in pads))
        if len(pads) < 64 or len(xs) < 8 or len(ys) < 8:
            continue
        xi = {value: index for index, value in enumerate(xs)}
        yi = {value: index for index, value in enumerate(ys)}
        cx, cy = (xs[0] + xs[-1]) / 2.0, (ys[0] + ys[-1]) / 2.0
        cells = []
        for pad in sorted(pads, key=lambda item: (item["pad"], item["y"], item["x"])):
            ix, iy = xi[round(pad["x"], 6)], yi[round(pad["y"], 6)]
            ring = min(ix, len(xs) - 1 - ix, iy, len(ys) - 1 - iy)
            ew = "E" if pad["x"] >= cx else "W"
            ns = "S" if pad["y"] >= cy else "N"
            outward = ns + ew
            directions = tuple(pad["directions"])
            direction = outward if outward in directions else (
                directions[0] if directions else None)
            if ring >= 2 and pad["pofv"]:
                mode = "via_in_pad"
            elif direction:
                mode = "dogbone"
            elif pad["pofv"]:
                mode = "via_in_pad"
            else:
                mode = "blocked"
            target_index = min(max(0, ring), max(0, len(route_layers) - 1))
            cells.append({
                "pad": pad["pad"], "net": pad["net"], "ring": ring,
                "quadrant": ns + ew, "mode": mode,
                "direction": direction,
                "target_layer": (route_layers[target_index]
                                 if route_layers else None),
            })
        arrays.append({
            "ref": ref, "pads": len(cells), "grid": (len(xs), len(ys)),
            "max_ring": max((cell["ring"] for cell in cells), default=0),
            "blocked": sum(cell["mode"] == "blocked" for cell in cells),
            "via_in_pad": sum(cell["mode"] == "via_in_pad" for cell in cells),
            "dogbone": sum(cell["mode"] == "dogbone" for cell in cells),
            "cells": cells,
        })
    return {"arrays": arrays,
            "array_count": len(arrays),
            "blocked": sum(array["blocked"] for array in arrays)}


def hierarchical_tiers(conns, stackup, pin_access, declared_critical=(),
                       local_span_mm=6.0):
    """Partition nets into ordered, non-overlapping detailed-route tiers."""
    conn_nets = {conn[0] for conn in conns}
    # Pin-access analysis also sees KiCad's one-pad ``unconnected-(...)``
    # pseudo-nets. They are useful obstruction geometry, but they are not route
    # work and must never enter a protected priority tier.
    constrained_nets = ({row["net"] for row in pin_access["constrained"]}
                        & conn_nets)
    blocked_nets = ({row["net"] for row in pin_access["blocked"]}
                    & conn_nets)
    by_kind = collections.defaultdict(set)
    for conn, kind in zip(conns, stackup["net_kinds"]):
        by_kind[kind].add(conn[0])
    critical_pairs = set(by_kind["high_speed"])
    critical_control = ((set(declared_critical) & conn_nets)
                        - critical_pairs)
    # A difficult power-pad launch remains owned by the local-cell/routed-power
    # stages; sending the entire rail through a signal escape tier creates a
    # competing skinny topology and can pre-empt its pour corridor.  Power
    # identity therefore outranks access scarcity in this partition.  The
    # access evidence is still retained on the pad for placement feedback.
    power = (set(by_kind["power"])
             - critical_pairs - critical_control)
    escape = ((constrained_nets | blocked_nets)
              - critical_pairs - critical_control - power)
    # Short, footprint-local connections should be completed before broad
    # rails consume their tiny routing pocket.  Derive them from physical span
    # and signal policy, not net names or references.  This captures enable/
    # soft-start passives and local LED logic while excluding pair, declared
    # critical, and power work that already has a higher-authority owner.
    grid_mm = float(stackup.get("grid_mm") or 1.0)
    points_by_net = collections.defaultdict(set)
    for conn in conns:
        if len(conn) < 3:
            continue
        net, source, sink = conn[:3]
        for endpoint in (source, sink):
            if len(endpoint) >= 3:
                points_by_net[net].add(
                    (int(endpoint[-2]), int(endpoint[-1])))
    local = set()
    for net in by_kind["signal"]:
        points = points_by_net.get(net, set())
        if len(points) < 2:
            continue
        ys = [point[0] for point in points]
        xs = [point[1] for point in points]
        span = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) * grid_mm
        if span <= float(local_span_mm) + 1e-9:
            local.add(net)
    local -= critical_pairs | critical_control | power
    escape -= local
    residual = (conn_nets - critical_pairs - critical_control
                - local - escape - power)
    return [
        # A critical coupled route owns its launch geometry as well as its
        # long corridor.  Routing generic constrained escapes first can consume
        # the only legal pair launch and defeats the point of precision-first.
        {"name": "critical_pairs", "nets": sorted(critical_pairs),
         "protect_after": True},
        # Board design intent, not a naming heuristic: e.g. a dropout
        # comparator chain, clock/reset, or interlock can be electrically more
        # important than an otherwise ordinary short GPIO net.
        {"name": "critical_control", "nets": sorted(critical_control),
         "protect_after": True},
        {"name": "local_interconnect", "nets": sorted(local),
         "protect_after": True},
        {"name": "pin_escape", "nets": sorted(escape),
         "protect_after": True},
        {"name": "power_distribution", "nets": sorted(power),
         "protect_after": True},
        {"name": "residual_signals", "nets": sorted(residual),
         "protect_after": False},
    ]


def _resolve_critical_selectors(selectors, available_nets):
    """Resolve exact or leaf-name critical selectors without guessing.

    Hierarchical KiCad nets gain sheet prefixes in the PCB. Board policy is
    allowed to say ``COMP_THRESH`` rather than repeat that generated prefix,
    but a leaf that matches two nets is ambiguous and fails closed.
    """
    import cec_constraint_ir
    return cec_constraint_ir.resolve_net_selectors(
        selectors, available_nets)


def precision_pair_avoid(board_path, reservations=None):
    """Return the exact obstacle rectangles used by the precision pair stage.

    A routed-object reservation is authoritative when enabled. Boards without
    that feature retain the historical PourPlan corridor hints. Keeping this
    adapter here gives placement proof and detailed routing one obstacle view
    instead of two subtly different approximations.
    """
    reservation = dict(reservations or {})
    if reservation.get("enabled"):
        rows = reservation.get("corridors") or ()
        return tuple(
            (float(row["x0"]), float(row["y0"]),
             float(row["x1"]), float(row["y1"]),
             str(row.get("name") or row.get("net") or "reservation"),
             str(row.get("layer") or "F.Cu"))
            for row in rows if row.get("layer"))

    import cec_synth_pipeline
    hints, _pours, _rules = cec_synth_pipeline._oracle_hints_pours(board_path)
    return tuple(
        (float(row["x0"]), float(row["y0"]),
         float(row["x1"]), float(row["y1"]),
         str(row.get("name") or "corridor"), str(layer))
        for row in hints
        if str(row.get("name") or "").startswith("corr_")
        for layer in (row.get("layers") or ("F.Cu",)))


def route_priority_policy(value=None):
    """Return the explicit critical-signal versus power ownership policy.

    ``critical-first`` is the production default: constrained pairs claim
    legal empty-board copper and the exact power compiler must subsequently
    prove a new route around that locked prefix. ``power-first`` remains an
    intentional diagnostic/ablation mode for boards whose power geometry is
    declared immutable before signal routing.  Keeping this choice explicit
    prevents the mere presence of a stale frozen-power sidecar from silently
    reversing the pipeline order.
    """
    policy = str(value or os.environ.get(
        "CEC_ROUTE_PRIORITY_POLICY", "critical-first")).strip().lower()
    aliases = {
        "critical": "critical-first", "signal-first": "critical-first",
        "signal": "critical-first", "power": "power-first",
    }
    policy = aliases.get(policy, policy)
    if policy not in ("critical-first", "power-first"):
        raise ValueError("unknown CEC_ROUTE_PRIORITY_POLICY %r" % policy)
    return policy


def priority_pair_avoid(board_path, reservations=None, *, policy=None):
    """Return pair obstacles for the selected executable owner order.

    Exact pad/copper/edge checks remain active in both modes.  Only the
    *replannable future power* rectangles are omitted in critical-first mode;
    final power admission must then solve around the locked pair.  This is not
    permission to route over materialized copper or canonical fixed keepouts.
    """
    selected = route_priority_policy(policy)
    if selected == "power-first" and (reservations or {}).get("enabled"):
        return precision_pair_avoid(board_path, reservations)
    return ()


def priority_kelvin_avoid(reservations=None, *, policy=None):
    """Return future-power obstacles visible to the Kelvin owner.

    Kelvin and coupled pairs share one executable priority decision.  Under
    ``critical-first`` neither may be refused by replannable future-power
    rectangles; the later exact power reconciliation must route around their
    locked copper.  ``power-first`` retains the frozen corridor obstacles for
    both.  Centralizing this prevents preflight and production from silently
    implementing different owner orders.
    """
    selected = route_priority_policy(policy)
    if selected == "power-first" and (reservations or {}).get("enabled"):
        return tuple((reservations or {}).get("corridors") or ())
    return ()


def _probe_critical_pairs_on_board(board, board_path, *, avoid=(),
                                   kelvin_avoid=(), do_pairs=True,
                                   include_pair_names=None):
    import cec_fr
    import cec_precision_route

    existing = cec_fr.owned_locked_nets(board_path)
    report = cec_precision_route.precision_route_board(
        board, board_path=board_path, do_kelvin=True,
        do_pairs=bool(do_pairs),
        pair_grid=True, verbose=False, avoid=tuple(avoid or ()),
        kelvin_avoid=tuple(kelvin_avoid or ()),
        existing_locked_nets=existing,
        include_pair_names=include_pair_names)
    pairs = report.get("pairs") or {}
    kelvin = report.get("kelvin") or {}
    route_quality = report.get("route_quality") or {}
    keep = ("name", "p", "n", "route_mode", "segments", "length_mm",
            "coupled_len_mm", "refused", "flow_through", "refs",
            "endpoint_stations", "failed_edge", "failed_layer",
            "layer_refusals",
            "fully_owned", "flow_leg_refusal", "flow_leg_order",
            "flow_leg_difficulty", "flow_through_pad_closure",
            "local_pad_closure",
            "post_closure_geometry", "pair_search_budget_s",
            "pair_search_budget_exhausted", "failure_certificate")

    def blocker_refs(value):
        refs = set()
        if isinstance(value, dict):
            if value.get("kind") in ("pad", "footprint_graphic") \
                    and value.get("ref"):
                refs.add(str(value["ref"]))
            for key, child in value.items():
                # The certificate's global A* frontier intentionally records
                # distant obstacles encountered while proving that no middle
                # corridor exists.  Those objects are forensic context, not
                # causal endpoint blockers and must never become blind placer
                # targets.  Exact portal screens outside the certificate keep
                # supplying the actionable local blocker set.
                if key == "failure_certificate":
                    continue
                refs.update(blocker_refs(child))
        elif isinstance(value, (tuple, list)):
            for child in value:
                refs.update(blocker_refs(child))
        return refs

    def blocker_relief(value, endpoint_refs):
        """Project exact portal screens into bounded placement vectors.

        Precision routing retains rich fallback trees.  The historical compact
        handoff kept only blocker reference names, discarding the pair axis and
        normal that make those blockers actionable.  Extract the geometry
        before compaction so the placer can move complete cells perpendicular
        to the refused channel instead of trying blind rotations.
        """
        accumulator = {}

        def visit(node):
            if isinstance(node, dict):
                screened = node.get("screened")
                normal = node.get("normal")
                axis = node.get("axis")
                if (isinstance(screened, dict)
                        and isinstance(normal, (list, tuple))
                        and len(normal) >= 2
                        and isinstance(axis, (list, tuple))
                        and len(axis) >= 2):
                    by_endpoint = {}
                    for label, row in screened.items():
                        if isinstance(row, dict):
                            endpoint = str(label).split(":", 1)[0]
                            by_endpoint.setdefault(endpoint, []).append(row)
                    for endpoint, rows in by_endpoint.items():
                        # A side is binding only when every sign failed.
                        if (not rows or any(int(row.get("accepted", 0) or 0)
                                            for row in rows)):
                            continue
                        for screen in rows:
                            for blocker in screen.get("blockers") or ():
                                if not isinstance(blocker, dict):
                                    continue
                                ref = str(blocker.get("ref") or "")
                                if not ref or ref in endpoint_refs:
                                    continue
                                key = (
                                    ref, endpoint,
                                    round(float(normal[0]), 6),
                                    round(float(normal[1]), 6),
                                    round(float(axis[0]), 6),
                                    round(float(axis[1]), 6),
                                )
                                accumulator[key] = (
                                    accumulator.get(key, 0)
                                    + int(blocker.get("count", 1) or 1))
                for child in node.values():
                    if isinstance(child, (dict, list)):
                        visit(child)
            elif isinstance(node, list):
                for child in node:
                    if isinstance(child, (dict, list)):
                        visit(child)

        visit(value)
        return [{
            "ref": ref, "endpoint": endpoint,
            "normal": [nx, ny], "axis": [ax, ay], "count": count,
        } for (ref, endpoint, nx, ny, ax, ay), count in sorted(
            accumulator.items(),
            key=lambda item: (-item[1], item[0]))[:24]]

    def compact(row):
        result = {key: row[key] for key in keep if key in row}
        refs = set(result.get("refs") or ())
        for net in (row.get("p"), row.get("n")):
            if not net:
                continue
            refs.update(pad[0] for pad in
                        cec_precision_route._pads_on_net(board, net))
        result["refs"] = sorted(refs)
        # Pair pads legitimately appear as obstacles to the opposite member
        # during fan-in enumeration. They are topology endpoints, not foreign
        # placement blockers; keep the two roles separate for ECO repair.
        result["blocker_refs"] = sorted(blocker_refs(row) - refs)
        result["blocker_relief"] = blocker_relief(row, refs)
        return result

    # Kelvin's generator reports human-readable endpoint certificates such as
    # ``RS1->U10.9 CANONICAL-REFUSED: ...``. Project them into the same stable,
    # component-addressable evidence shape used by coupled-pair failures so
    # placement repair can act on the real endpoints instead of merely logging
    # the refusal. Reference parsing is deliberately topology-only and accepts
    # arbitrary KiCad reference prefixes.
    kelvin_refused = []
    endpoint_pattern = re.compile(
        r"([A-Za-z][A-Za-z0-9_-]*)\s*->\s*"
        r"([A-Za-z][A-Za-z0-9_-]*)")
    kelvin_detail = {
        (str(row.get("net") or ""), str(row.get("reason") or "")): row
        for row in (kelvin.get("refused_details") or ())
        if isinstance(row, dict)
    }
    for net, reasons in sorted((kelvin.get("refused") or {}).items()):
        for reason in reasons or ():
            match = endpoint_pattern.search(str(reason))
            refs = sorted(set(match.groups())) if match else []
            row = {"net": str(net), "reason": str(reason), "refs": refs}
            detail = kelvin_detail.get((str(net), str(reason))) or {}
            for key in (
                    "source_ref", "target_ref", "target_pad",
                    "source_position_mm", "target_position_mm",
                    "current_distance_mm", "max_distance_mm",
                    "required_closer_mm", "reason_kind", "mode",
                    "tap_start_position_mm", "width_mm", "clearance_mm",
                    "inward_vector", "target_inward_mm",
                    "canonical_min_inward_mm", "blocker_refs",
                    "blocker_details"):
                if key in detail:
                    row[key] = detail[key]
            kelvin_refused.append(row)

    pairs_ok = bool(report.get("pairs_ok"))
    kelvin_ok = not kelvin_refused
    quality_refused = []
    for row in route_quality.get("issues") or ():
        if row.get("severity") != "blocking":
            continue
        compact_issue = {
            key: row[key] for key in (
                "type", "severity", "net", "layer", "at_mm",
                "neighbors_mm", "opening_angle_deg", "path_turn_deg",
                "track_uuids", "segment_lengths_mm", "widths_mm",
                "message") if key in row}
        net = str(row.get("net") or "")
        compact_issue["refs"] = sorted({
            str(pad[0]) for pad in
            cec_precision_route._pads_on_net(board, net) if pad[0]})
        quality_refused.append(compact_issue)
    # Fail closed even if a future precision implementation returns
    # ``pairs_ok=False`` without either an explicit pair row or a quality row.
    quality_error = (not pairs_ok and not (pairs.get("refused") or ())
                     and not quality_refused)

    return {
        "pairs_ok": pairs_ok,
        "kelvin_ok": kelvin_ok,
        "critical_routes_ok": pairs_ok and kelvin_ok,
        "route_quality": {
            "ok": bool(route_quality.get("ok")),
            "blocking_count": int(
                route_quality.get("blocking_count", 0) or 0),
            "refused": quality_refused,
            "error": ("pairs_ok false without refusal evidence"
                      if quality_error else None),
        },
        "kelvin": {
            "taps": int(kelvin.get("taps", 0) or 0),
            "segments": int(kelvin.get("segments", 0) or 0),
            "by_net": dict(kelvin.get("by_net") or {}),
            "covered": dict(kelvin.get("covered") or {}),
            "refused": kelvin_refused,
        },
        "routed": [compact(row)
                   for row in (pairs.get("routed") or ())],
        "refused": [compact(row)
                    for row in (pairs.get("refused") or ())],
    }


def probe_critical_pairs(board_path, reservations=None, *, do_pairs=True,
                         include_pair_names=None, priority_policy=None):
    """Prove Kelvin-then-coupled-pair feasibility on the placement.

    This uses the same exact critical-route order as production: Kelvin taps
    are committed first, then the guarded pair router sees their copper along
    with the configured pour obstacles. It mutates only an in-memory board and
    returns a compact manifest suitable for placement ranking. A checker
    failure is a hard refusal, never evidence that the placement is safe.
    """
    try:
        import pcbnew
        board = pcbnew.LoadBoard(board_path)
        # No reservation means the production priority order: route critical
        # signal physics first. An explicit reservation remains available for
        # diagnostics/ablation, but it is not the default authority.
        # ``None`` preserves the public API's historical meaning that an
        # explicitly supplied reservation is authoritative. Internal pipeline
        # callers always pass their owner-order policy so a sidecar cannot
        # accidentally change semantics.
        if priority_policy is None:
            avoid = (precision_pair_avoid(board_path, reservations)
                     if reservations is not None else ())
        else:
            avoid = priority_pair_avoid(
                board_path, reservations, policy=priority_policy)
        selected_policy = route_priority_policy(priority_policy)
        kelvin_avoid = priority_kelvin_avoid(
            reservations, policy=selected_policy)
        return _probe_critical_pairs_on_board(
            board, board_path, avoid=avoid,
            kelvin_avoid=kelvin_avoid, do_pairs=do_pairs,
            include_pair_names=include_pair_names)
    except Exception as exc:                              # noqa: BLE001
        return {
            "pairs_ok": False, "kelvin_ok": False,
            "critical_routes_ok": False,
            "kelvin": {"taps": 0, "segments": 0, "by_net": {},
                       "covered": {}, "refused": []},
            "routed": [], "refused": [],
            "error": "%s: %s" % (type(exc).__name__, exc),
        }


def critical_route_refusal_count(report):
    """Return one comparable count for the complete precision ladder.

    Accept both the compact preflight shape (Kelvin refusals are a list) and
    the raw precision-router shape (Kelvin refusals are grouped by net). This
    keeps repair ranking and production admission on one definition.
    """
    if not isinstance(report, dict):
        return 1
    if "critical_route_refused_count" in report:
        return int(report.get("critical_route_refused_count", 0) or 0)
    kelvin_refused = ((report.get("kelvin") or {}).get("refused") or ())
    if isinstance(kelvin_refused, dict):
        kelvin_count = sum(len(rows or ())
                           for rows in kelvin_refused.values())
    else:
        kelvin_count = len(kelvin_refused)
    pair_count = len(report.get("refused") or ())
    if "pairs" in report:
        pair_count = len((report.get("pairs") or {}).get("refused") or ())
    quality = report.get("route_quality") or {}
    quality_rows = quality.get("refused") or ()
    quality_count = len(quality_rows)
    if not quality_count:
        quality_count = int(quality.get("blocking_count", 0) or 0)
    if quality.get("error") and not quality_count:
        quality_count = 1
    return (kelvin_count + pair_count + quality_count
            + (1 if report.get("error") else 0))


def compile_priority_routes(board_path, *, priority_policy=None):
    """Compile the configured route-owner order as executable evidence.

    The production ``critical-first`` policy lets guarded differential pairs
    claim their coupled geometry before replanning routed power objects around
    the locked prefix.  ``power-first`` remains available as an explicit
    diagnostic policy and then treats the existing routed-power authority as an
    obstacle.  The returned board is never saved; detailed routing independently
    repeats the configured order.
    """
    import pcbnew

    board = pcbnew.LoadBoard(board_path)
    if board is None:
        raise RuntimeError("priority compiler could not load board")
    reservations = compile_route_reservations(board_path, board=board)
    policy = route_priority_policy(priority_policy)
    avoid = priority_pair_avoid(
        board_path, reservations, policy=policy)
    kelvin_avoid = priority_kelvin_avoid(
        reservations, policy=policy)
    if policy == "power-first" and reservations.get("enabled"):
        critical = _probe_critical_pairs_on_board(
            board, board_path, avoid=avoid, kelvin_avoid=kelvin_avoid)
        reservations["priority_order"] = (
            "routed_power_objects", "critical_pairs", "residual_signals")
    else:
        critical = _probe_critical_pairs_on_board(
            board, board_path, avoid=avoid, kelvin_avoid=kelvin_avoid)
        reservations["priority_order"] = (
            "critical_pairs", "routed_power_objects", "residual_signals")
    reservations["priority_policy"] = policy
    reservations["critical_pair_avoid_count"] = len(avoid)
    reservations["kelvin_avoid_count"] = len(kelvin_avoid)
    return critical, reservations


def _connection_net(row):
    """Best-effort net extraction from compact router refusal records."""
    if isinstance(row, dict):
        return str(row.get("net") or row.get("name") or "")
    if isinstance(row, (tuple, list)) and row:
        return str(row[0])
    return ""


def _annotate_blockage_witnesses(rows, pin_access, stackup, *, limit=24):
    """Join router grid witnesses to physical refs that placement can move."""
    grid_mm = float((stackup or {}).get("grid_mm", 1.0) or 1.0)
    origin = tuple((stackup or {}).get("grid_origin_mm") or (0.0, 0.0))
    if len(origin) != 2:
        origin = (0.0, 0.0)
    pads_by_net = collections.defaultdict(list)
    all_pads = []
    for pad in (pin_access or {}).get("pads") or ():
        pads_by_net[str(pad.get("net", ""))].append(pad)
        all_pads.append(pad)

    def cell_distance(pad, x, y):
        gx = (float(pad.get("x", 0.0)) - float(origin[0])) / grid_mm
        gy = (float(pad.get("y", 0.0)) - float(origin[1])) / grid_mm
        return abs(gx - float(x)) + abs(gy - float(y))

    annotated = []
    for source in list(rows or ())[:max(0, int(limit))]:
        row = dict(source)
        if row.get("kind") == "over_capacity":
            x, y = int(row.get("x", 0)), int(row.get("y", 0))
            connections = list(row.get("connections") or ())
            residual_nets = {
                str(conn.get("net", "")) for conn in connections
                if not conn.get("protected")}
            protected_nets = {
                str(conn.get("net", "")) for conn in connections
                if conn.get("protected")}
            candidate_nets = residual_nets or {
                str(conn.get("net", "")) for conn in connections}
            candidates = {}
            for net in sorted(candidate_nets):
                for pad in pads_by_net.get(net, ()):
                    ref = str(pad.get("ref", ""))
                    if not ref:
                        continue
                    distance = cell_distance(pad, x, y)
                    previous = candidates.get(ref)
                    item = {"ref": ref, "net": net,
                            "distance_cells": round(distance, 6),
                            "role": ("residual_endpoint"
                                     if net in residual_nets
                                     else "protected_endpoint")}
                    if previous is None or (distance, net) < (
                            previous["distance_cells"], previous["net"]):
                        candidates[ref] = item
            blocking = {}
            hx0 = float(origin[0]) + x * grid_mm
            hy0 = float(origin[1]) + y * grid_mm
            hx1, hy1 = hx0 + grid_mm, hy0 + grid_mm
            routed_nets = residual_nets | protected_nets
            for pad in all_pads:
                bbox = tuple(pad.get("bbox") or ())
                if len(bbox) != 4:
                    continue
                if (bbox[2] < hx0 or bbox[0] > hx1
                        or bbox[3] < hy0 or bbox[1] > hy1):
                    continue
                net = str(pad.get("net", ""))
                if net in routed_nets:
                    continue
                ref = str(pad.get("ref", ""))
                if ref:
                    blocking[ref] = {"ref": ref, "net": net,
                                     "distance_cells": 0.0,
                                     "role": "foreign_blocker"}
            ordered = sorted(
                list(blocking.values()) + list(candidates.values()),
                key=lambda item: (
                    0 if item["role"] == "foreign_blocker" else 1,
                    item["distance_cells"], item["ref"], item["net"]))
            row["candidate_refs"] = ordered[:12]
            row["critical_nets"] = sorted(protected_nets)
            row["residual_nets"] = sorted(residual_nets)
        elif row.get("kind") == "unroutable":
            net = str(row.get("net", ""))
            endpoints = []
            terminal_cells = [tuple(row.get("src") or ()),
                              tuple(row.get("dst") or ())]
            for pad in pads_by_net.get(net, ()):
                ref = str(pad.get("ref", ""))
                if not ref:
                    continue
                gx = (float(pad.get("x", 0.0)) - float(origin[0])) / grid_mm
                gy = (float(pad.get("y", 0.0)) - float(origin[1])) / grid_mm
                distance = min((abs(gx - float(cell[2]))
                                + abs(gy - float(cell[1]))
                                for cell in terminal_cells if len(cell) == 3),
                               default=0.0)
                endpoints.append({
                    "ref": ref, "net": net,
                    "distance_cells": round(distance, 6),
                    "role": "unroutable_endpoint"})
            row["candidate_refs"] = sorted(
                endpoints, key=lambda item: (
                    item["distance_cells"], item["ref"]))[:12]
            # If the launch is boxed in, try every cardinal exit; otherwise a
            # perpendicular reroute is selected later from the endpoint span.
            row.setdefault("escape_directions", ("N", "S", "E", "W"))
        annotated.append(row)
    return annotated


@dataclass(frozen=True)
class IncrementalAccessContext:
    """Board-invariant inputs for exact placement-delta access screening."""

    board_path: str
    board_db: object
    conns: tuple
    stackup: dict
    future_congestion: object
    route_reservations: dict
    critical_selectors: tuple
    grid_mm: float
    build_wall_s: float


def prepare_incremental_access(board_path, *, critical_nets=(), grid_mm=0.5):
    """Load one immutable geometry/problem context for many placement trials."""
    import cec_boarddb
    import cec_coord_router as ccr

    started = time.monotonic()
    database = cec_boarddb.BoardDB.from_board(board_path)
    conns, _height, _width, _foreign, stackup = ccr.build_problem(
        board_path, grid_mm=float(grid_mm), detailed=True)
    stackup = dict(stackup)
    available_nets = {conn[0] for conn in conns}
    declaration = _resolve_critical_selectors(
        tuple(critical_nets or ()), available_nets)
    protected_nets = {
        conn[0] for conn, kind in zip(conns, stackup["net_kinds"])
        if kind == "high_speed"}
    protected_nets.update(declaration["resolved"])
    import cec_future_congestion
    # Incremental access needs only the frozen routed-object reservations.
    # Compiling priority routes here used to replay the complete Kelvin/CAN/
    # USB precision solver even though none of its copper or verdict entered
    # this context.  The baseline exact preflight already owns that proof; a
    # placement delta receives a new exact proof only if it survives this
    # cheap screen and becomes a finalist.
    route_reservations = compile_route_reservations(board_path)
    future_congestion = cec_future_congestion.prepare(
        database, conns, stackup, critical_nets=protected_nets,
        reservations=route_reservations["corridors"],
        reservation_report=route_reservations["report"],
        grid_mm=float(grid_mm))
    # Dense per-connection blockage cells belong to global routing, not this
    # access-only context. Retaining them would defeat the bounded memory goal.
    stackup.pop("_blocked_cells_by_conn", None)
    return IncrementalAccessContext(
        board_path=os.path.abspath(board_path), board_db=database,
        conns=tuple(conns), stackup=stackup,
        future_congestion=future_congestion,
        route_reservations=route_reservations,
        critical_selectors=tuple(critical_nets or ()),
        grid_mm=float(grid_mm),
        build_wall_s=round(time.monotonic() - started, 6))


def analyze_incremental_access(context, *, placements=None,
                               escape_mm=1.25, clearance_mm=0.20,
                               run_future_congestion=False):
    """Run the ordinary quick access gate on an exact in-memory board delta.

    This intentionally corresponds to ``analyze(..., run_congestion=False,
    run_critical_routes=False)``. Full congestion, coupled-pair construction,
    bypass checks, KiCad connectivity, and DRC still run on materialized
    finalists. The return shape matches :func:`analyze` so the shared compact
    evidence projection and ordering remain authoritative.
    """
    started = time.monotonic()
    conns = context.conns
    stackup = context.stackup
    pin_access = analyze_pin_access(
        board_db=context.board_db, placements=placements,
        escape_mm=escape_mm, clearance_mm=clearance_mm)
    fanout = plan_array_fanouts(pin_access)
    available_nets = {conn[0] for conn in conns}
    declaration = _resolve_critical_selectors(
        context.critical_selectors, available_nets)
    declared_critical = set(declaration["resolved"])
    tiers = hierarchical_tiers(
        conns, stackup, pin_access,
        declared_critical=declared_critical)
    critical_routes = {
        "pairs_ok": True, "kelvin_ok": True, "critical_routes_ok": True,
        "kelvin": {"taps": 0, "segments": 0, "by_net": {},
                   "covered": {}, "refused": []},
        "routed": [], "refused": [],
        "skipped": "incremental_access_screen"}
    critical_nets = {
        conn[0] for conn, kind in zip(conns, stackup["net_kinds"])
        if kind in ("power", "high_speed")}
    critical_nets |= declared_critical
    critical_nets |= {"GND", "/GND"}
    for row in pin_access.get("pads") or ():
        row["critical"] = row.get("net") in critical_nets
    critical_pin_blocked = sum(
        bool(row.get("critical"))
        for row in (pin_access.get("blocked") or ()))
    future_congestion = (context.future_congestion.evaluate(placements)
                         if run_future_congestion else None)
    return {
        "schema": 1,
        "board": context.board_path,
        "stackup": stackup,
        "pin_access": pin_access,
        "fanout": fanout,
        "tiers": tiers,
        "congestion": None,
        "future_congestion": future_congestion,
        "route_reservations": dict(context.route_reservations),
        "critical_routes": critical_routes,
        "criticality": {
            "nets": sorted(critical_nets),
            "declaration": declaration,
            "pin_access_blocked_count": critical_pin_blocked,
            "unroutable_count": 0,
        },
        "gate": (declaration["ok"]
                 and critical_pin_blocked == 0
                 and fanout["blocked"] == 0),
        "warnings": ({"ordinary_pads_without_straight_escape":
                      pin_access["blocked_count"]}
                     if pin_access["blocked_count"] else {}),
        "incremental": {
            "schema": 1,
            "context_build_wall_s": context.build_wall_s,
            "base_fingerprint": context.board_db.fingerprint,
            "view_fingerprint":
                pin_access["geometry"]["view_fingerprint"],
            "invalidation": {
                key: pin_access["geometry"][key]
                for key in ("dirty_footprints", "dirty_footprint_count",
                            "dirty_pad_indices", "dirty_pad_count")},
        },
        "wall_s": round(time.monotonic() - started, 6),
    }


def render_congestion_map(usage, capacity, layer_names, output_path,
                          *, panel_px=700):
    """Render every route-layer utilization field as a nearest-cell heatmap."""
    import numpy as np
    from PIL import Image, ImageDraw

    raw = np.asarray(usage, dtype=np.float32)
    panels = []
    for layer, name in enumerate(layer_names):
        field = raw[layer]
        ratio = field / max(1.0, float(capacity))
        rgb = np.zeros((field.shape[0], field.shape[1], 3), dtype=np.uint8)
        occupied = field > 0
        legal = occupied & (ratio <= 1.0)
        over = ratio > 1.0
        rgb[legal, 0] = 20
        rgb[legal, 1] = np.clip(80 + 150 * ratio[legal], 0, 255).astype(np.uint8)
        rgb[legal, 2] = np.clip(120 + 120 * ratio[legal], 0, 255).astype(np.uint8)
        rgb[over, 0] = 255
        rgb[over, 1] = np.clip(180 - 50 * (ratio[over] - 1), 20, 180).astype(np.uint8)
        rgb[over, 2] = 25
        image = Image.fromarray(rgb, mode="RGB")
        scale = max(1, int(panel_px / max(image.width, image.height)))
        image = image.resize((image.width * scale, image.height * scale),
                             Image.Resampling.NEAREST)
        framed = Image.new("RGB", (image.width, image.height + 30), (7, 12, 18))
        framed.paste(image, (0, 30))
        draw = ImageDraw.Draw(framed)
        draw.text((8, 8), "%s  capacity=%d  peak=%.0f" % (
            name, capacity, float(field.max()) if field.size else 0.0),
                  fill=(230, 240, 245))
        panels.append(framed)
    columns = 2 if len(panels) > 1 else 1
    rows = int(math.ceil(len(panels) / columns))
    cell_w = max(panel.width for panel in panels)
    cell_h = max(panel.height for panel in panels)
    canvas = Image.new("RGB", (columns * cell_w, rows * cell_h), (4, 8, 12))
    for index, panel in enumerate(panels):
        x = (index % columns) * cell_w
        y = (index // columns) * cell_h
        canvas.paste(panel, (x, y))
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    canvas.save(output_path)
    return output_path


def analyze(board_path, *, grid_mm=0.5, iters=40, backend="auto",
            run_congestion=True, heatmap_path=None,
            early_stop_plateau=True, plateau_patience=8,
            plateau_min_delta=1.0, critical_nets=None, board_hint=None,
            run_critical_routes=True, run_future_congestion=False,
            compiled_priority_routes=None):
    import cec_coord_router as ccr
    import cec_board_policy
    started = time.monotonic()
    policy = cec_board_policy.load(board_path, board_hint=board_hint)
    if critical_nets is None:
        critical_nets = tuple(
            (policy.get("params") or {}).get("critical_route_nets", ()) or ())
    else:
        critical_nets = tuple(critical_nets)
    declared_selectors = critical_nets
    conns, height, width, foreign, stackup = ccr.build_problem(
        board_path, grid_mm=grid_mm, detailed=True)
    blocked_cells = stackup.pop("_blocked_cells_by_conn", ())
    if run_critical_routes:
        if compiled_priority_routes is None:
            critical_routes, route_reservations = compile_priority_routes(
                board_path)
        else:
            critical_routes, route_reservations = compiled_priority_routes
    else:
        critical_routes = {
            "pairs_ok": True, "kelvin_ok": True,
            "critical_routes_ok": True,
            "kelvin": {"taps": 0, "segments": 0, "by_net": {},
                       "covered": {}, "refused": []},
            "routed": [], "refused": [],
            "skipped": "quick_access_screen"}
        route_reservations = compile_route_reservations(board_path)
    conns, stackup, blocked_cells, _reservation_projection = \
        apply_route_reservations(
            conns, stackup, blocked_cells, route_reservations,
            height, width)
    pair_owned_nets = {
        net for row in (critical_routes.get("routed") or ())
        if not row.get("refused")
        for net in (row.get("p"), row.get("n")) if net}
    conns, stackup, blocked_cells = apply_preowned_connections(
        conns, stackup, blocked_cells, pair_owned_nets)
    pin_access = analyze_pin_access(board_path)
    fanout = plan_array_fanouts(pin_access)
    available_nets = {conn[0] for conn in conns}
    declaration = _resolve_critical_selectors(
        critical_nets, available_nets)
    declared_critical = set(declaration["resolved"])
    tiers = hierarchical_tiers(
        conns, stackup, pin_access,
        declared_critical=declared_critical)
    critical_nets = {
        net for row in (critical_routes.get("routed") or [])
        for net in (row.get("p"), row.get("n")) if net}
    critical_nets |= {
        net for row in (critical_routes.get("refused") or [])
        for net in (row.get("p"), row.get("n")) if net}
    critical_nets |= {
        conn[0] for conn, kind in zip(conns, stackup["net_kinds"])
        if kind in ("power", "high_speed")}
    critical_nets |= declared_critical
    critical_nets |= {"GND", "/GND"}
    for row in pin_access.get("pads") or ():
        row["critical"] = row.get("net") in critical_nets
    critical_pin_blocked = sum(
        bool(row.get("critical")) for row in (pin_access.get("blocked") or ()))
    congestion = None
    future_congestion = None
    if run_future_congestion:
        import cec_boarddb
        import cec_future_congestion
        database = cec_boarddb.BoardDB.from_board(board_path)
        protected_nets = {
            conn[0] for conn, kind in zip(conns, stackup["net_kinds"])
            if kind == "high_speed"}
        protected_nets.update(declared_critical)
        future_congestion = cec_future_congestion.prepare(
            database, conns, stackup, critical_nets=protected_nets,
            reservations=route_reservations["corridors"],
            reservation_report=route_reservations["report"],
            grid_mm=float(grid_mm)).evaluate()
    if run_congestion:
        priority_by_net = {
            net: priority
            for priority, tier in enumerate(tiers)
            for net in tier["nets"]
        }
        connection_priorities = [
            priority_by_net[conn[0]] for conn in conns]
        routed = ccr.route_problem(
            conns, height, width, backend=backend, grid_mm=grid_mm,
            iters=iters, foreign_cells=foreign,
            blocked_cells_by_conn=blocked_cells,
            L=len(stackup["layer_names"]),
            layer_names=stackup["layer_names"],
            allowed_layers=stackup["allowed_layers_by_conn"],
            connection_priorities=connection_priorities,
            # Exact production routing locks the pair and declared-control
            # tiers before residual work. Mirror that ownership in global
            # placement prediction so later traffic cannot erase their lanes.
            protected_priority_max=1,
            cost_mode="fixed",
            early_stop_plateau=bool(early_stop_plateau),
            plateau_patience=min(max(2, int(plateau_patience)),
                                 max(2, int(iters))),
            plateau_min_delta=float(plateau_min_delta))
        congestion = {
            "backend": routed["backend"], "cost_mode": routed["cost_mode"],
            "backend_requested": routed.get("backend_requested"),
            "backend_work_cells": routed.get("backend_work_cells"),
            "auto_gpu_floor": routed.get("auto_gpu_floor"),
            "wall_s": routed["wall_s"], "iters": routed["iters_used"],
            "residual_overuse": routed["residual_overuse"],
            "residual_overuse_escaped": routed["residual_overuse_escaped"],
            "unroutable_count": routed["unroutable_count"],
            "unroutable_connections": routed["unroutable_connections"],
            "negotiation": routed.get("negotiation") or {},
            **routed["congestion"],
        }
        congestion["blockage_witnesses"] = _annotate_blockage_witnesses(
            routed.get("blockage_witnesses") or (), pin_access, stackup)
        if routed.get("route_awareness_service"):
            congestion["route_awareness_service"] = dict(
                routed["route_awareness_service"])
        congestion["critical_unroutable_count"] = sum(
            _connection_net(row) in critical_nets
            for row in congestion.get("unroutable_connections") or ())
        if heatmap_path:
            render_congestion_map(
                routed["usage"], routed["congestion"]["capacity"],
                stackup["layer_names"], heatmap_path)
            congestion["heatmap"] = os.path.abspath(heatmap_path)
    return {
        "schema": 1, "board": os.path.abspath(board_path),
        "board_hint": board_hint or policy.get("board"),
        "policy": ({"board": policy.get("board"),
                    "fingerprint": policy.get("fingerprint"),
                    "source": policy.get("source")}
                   if policy else None),
        "stackup": stackup, "pin_access": pin_access,
        "fanout": fanout, "tiers": tiers, "congestion": congestion,
        "future_congestion": future_congestion,
        "route_reservations": route_reservations,
        "critical_routes": critical_routes,
        "criticality": {
            "nets": sorted(critical_nets),
            # Keep policy input separate from the canonical resolver payload;
            # the latter is reused by incremental placement evidence.
            "selectors": list(declared_selectors),
            "declaration": declaration,
            "pin_access_blocked_count": critical_pin_blocked,
            "unroutable_count": int(
                (congestion or {}).get("critical_unroutable_count", 0) or 0),
        },
        # A missing 1.25 mm straight ray on an ordinary perimeter pad is a
        # congestion warning, not proof that a shorter neck-down or local maze
        # is impossible. Array fanout cells are explicit, however: an assigned
        # BGA ball with neither dogbone nor qualified POFV is a hard refusal.
        "gate": (declaration["ok"]
                 and critical_routes.get(
                     "critical_routes_ok",
                     critical_routes.get("pairs_ok")) is True
                 and critical_pin_blocked == 0
                 and fanout["blocked"] == 0
                 and (congestion is None
                      or congestion["unroutable_count"] == 0)),
        "warnings": ({"ordinary_pads_without_straight_escape":
                      pin_access["blocked_count"]}
                     if pin_access["blocked_count"] else {}),
        "wall_s": round(time.monotonic() - started, 3),
    }


def analyze_multiresolution(board_path, *, grid_mm=0.5, iters=40,
                            backend="auto", coarse_factor=2.0,
                            coarse_iters=None, heatmap_path=None,
                            early_stop_plateau=True,
                            plateau_patience=8,
                            plateau_min_delta=1.0,
                            critical_nets=None, board_hint=None,
                            run_future_congestion=False):
    """Run deterministic coarse-to-fine physical preflight.

    The coarser level cheaply exposes macro bottlenecks and layer starvation;
    the requested ``grid_mm`` level is always authoritative, so a coarse pass
    can never waive a fine obstruction.  Only compact summaries are retained
    for earlier levels.  The dense usage tensor never enters JSON or storage.
    """

    fine = float(grid_mm)
    coarse = round(fine * max(1.0, float(coarse_factor)), 6)
    levels = [coarse] if coarse > fine + 1e-9 else []
    levels.append(fine)
    coarse_budget = (max(2, int(math.ceil(int(iters) / 2.0)))
                     if coarse_iters is None else max(1, int(coarse_iters)))
    reports = []
    compiled_priority_routes = None
    started = time.monotonic()
    for index, resolution in enumerate(levels):
        authoritative = index == len(levels) - 1
        report = analyze(
            board_path, grid_mm=resolution,
            iters=(int(iters) if authoritative else coarse_budget),
            backend=backend, run_congestion=True,
            heatmap_path=(heatmap_path if authoritative else None),
            early_stop_plateau=early_stop_plateau,
            plateau_patience=plateau_patience,
            plateau_min_delta=plateau_min_delta,
            critical_nets=critical_nets,
            board_hint=board_hint,
            run_future_congestion=(bool(run_future_congestion)
                                   and authoritative),
            compiled_priority_routes=compiled_priority_routes)
        reports.append(report)
        # Critical/Kelvin copper feasibility and routed-object reservations are
        # exact millimetre geometry; they do not change with the congestion
        # raster pitch.  Reuse the first proof for later resolutions instead
        # of spending the same bounded pair-search budget once per level.
        if (compiled_priority_routes is None
                and isinstance(report.get("critical_routes"), dict)
                and isinstance(report.get("route_reservations"), dict)):
            compiled_priority_routes = (
                report["critical_routes"], report["route_reservations"])
    final = reports[-1]
    levels_summary = []
    for report, resolution in zip(reports, levels):
        congestion = report.get("congestion") or {}
        negotiation = congestion.get("negotiation") or {}
        levels_summary.append({
            "grid_mm": resolution,
            "authoritative": report is final,
            "gate": bool(report.get("gate")),
            "backend": congestion.get("backend"),
            "wall_s": congestion.get("wall_s"),
            "iters": congestion.get("iters"),
            "unroutable_count": int(
                congestion.get("unroutable_count", 0) or 0),
            "residual_overuse": float(
                congestion.get("residual_overuse", 0.0) or 0.0),
            "residual_overuse_escaped": float(
                congestion.get("residual_overuse_escaped", 0.0) or 0.0),
            "plateau": bool(negotiation.get("plateau")),
            "best_iteration": negotiation.get("best_iteration"),
            "stall_age": negotiation.get("stall_age"),
            "hotspots": list(congestion.get("hotspots") or ())[:8],
        })
    final["multiresolution"] = {
        "schema": 1, "levels": levels_summary,
        "authoritative_grid_mm": fine,
        "agreement": len({(row["gate"], row["unroutable_count"] == 0,
                            row["residual_overuse_escaped"] == 0.0)
                           for row in levels_summary}) == 1,
        "wall_s": round(time.monotonic() - started, 3),
    }
    final["wall_s"] = final["multiresolution"]["wall_s"]
    return final


def compact_placement_evidence(report, *, blocked_limit=24,
                               connection_limit=24, hotspot_limit=16):
    """Reduce a full preflight report to stable placement-ranking evidence.

    The detailed router and dashboard retain the full report. Placement only
    needs the hard fanout refusal, ordinary pin-access warning, unreachable
    connection count, and negotiated-capacity residuals. Keeping this
    projection here prevents production placement and fresh-wave placement
    from drifting into different definitions of route awareness.
    """
    if not isinstance(report, dict):
        return {"error": "missing preflight report"}
    if report.get("error"):
        return {"error": str(report["error"])}
    congestion = report.get("congestion") or {}
    future = report.get("future_congestion") or {}
    route_reservations = report.get("route_reservations") or {}
    pin_access = report.get("pin_access") or {}
    fanout = report.get("fanout") or {}
    stackup = report.get("stackup") or {}
    critical = report.get("criticality") or {}
    declaration = critical.get("declaration") or {}
    critical_routes = report.get("critical_routes") or {}
    refused_pairs = list(critical_routes.get("refused") or ())
    kelvin = critical_routes.get("kelvin") or {}
    refused_kelvin = list(kelvin.get("refused") or ())
    route_quality = critical_routes.get("route_quality") or {}
    refused_quality = list(route_quality.get("refused") or ())
    quality_error_count = (
        1 if route_quality.get("error") and not refused_quality else 0)
    critical_error_count = 1 if critical_routes.get("error") else 0
    pair_refs = {
        str(ref) for row in refused_pairs
        for ref in (row.get("refs") or ()) if ref}
    kelvin_refs = {
        str(ref) for row in refused_kelvin
        for ref in (row.get("refs") or ()) if ref}
    kelvin_blocker_refs = {
        str(ref) for row in refused_kelvin
        for ref in (row.get("blocker_refs") or ())
        if ref and str(ref) not in kelvin_refs}
    kelvin_blocker_details = []
    seen_kelvin_blockers = set()
    for refusal in refused_kelvin:
        endpoints = {str(ref) for ref in (refusal.get("refs") or ())}
        for blocker in refusal.get("blocker_details") or ():
            if not isinstance(blocker, dict):
                continue
            row = dict(blocker)
            row["kelvin_net"] = str(refusal.get("net") or "")
            row["source_ref"] = str(refusal.get("source_ref") or "")
            row["target_ref"] = str(refusal.get("target_ref") or "")
            row["width_mm"] = float(refusal.get("width_mm", 0.25) or 0.25)
            row["clearance_mm"] = float(
                refusal.get("clearance_mm", 0.2) or 0.2)
            row["endpoint_owned"] = bool(
                row.get("ref") and str(row.get("ref")) in endpoints)
            signature = (
                row.get("kelvin_net"), row.get("path_kind"),
                row.get("kind"), row.get("ref"), row.get("pad"),
                tuple(row.get("leg_start_mm") or ()),
                tuple(row.get("leg_end_mm") or ()))
            if signature in seen_kelvin_blockers:
                continue
            seen_kelvin_blockers.add(signature)
            kelvin_blocker_details.append(row)
    compact_refused_kelvin = [{
        key: value for key, value in row.items()
        if key != "blocker_details"}
        for row in refused_kelvin]

    # A precision-pair refusal can contain several fallback attempts.  Each
    # portal attempt reports both terminal sides, the pair-normal vector, and
    # the exact foreign pads that rejected candidate launches.  Only a side
    # for which *every* sign is blocked is binding: a blocker seen on one
    # rejected sign is not actionable when the other sign has a legal portal.
    # Collapse the nested fail stack into a small, stable placement hint while
    # retaining the full report for the dashboard and forensic record.
    relief_accumulator = {}

    # New precision reports project the actionable portal vectors before
    # compacting their fallback tree.  Keep the recursive reader below for
    # older/direct reports and merge both shapes into one stable contract.
    for refused in refused_pairs:
        for row in refused.get("blocker_relief") or ():
            if not isinstance(row, dict):
                continue
            ref = str(row.get("ref") or "")
            normal = row.get("normal")
            axis = row.get("axis")
            endpoint = str(row.get("endpoint") or "terminal")
            if (not ref or ref in pair_refs
                    or not isinstance(normal, (list, tuple))
                    or len(normal) < 2
                    or not isinstance(axis, (list, tuple))
                    or len(axis) < 2):
                continue
            key = (
                ref, endpoint,
                round(float(normal[0]), 6),
                round(float(normal[1]), 6),
                round(float(axis[0]), 6),
                round(float(axis[1]), 6),
            )
            relief_accumulator[key] = (
                relief_accumulator.get(key, 0)
                + int(row.get("count", 1) or 1))

    def collect_pair_relief(value):
        if isinstance(value, dict):
            screened = value.get("screened")
            normal = value.get("normal")
            axis = value.get("axis")
            if (isinstance(screened, dict)
                    and isinstance(normal, (list, tuple))
                    and len(normal) >= 2
                    and isinstance(axis, (list, tuple))
                    and len(axis) >= 2):
                by_endpoint = {}
                for label, row in screened.items():
                    if not isinstance(row, dict):
                        continue
                    endpoint = str(label).split(":", 1)[0]
                    by_endpoint.setdefault(endpoint, []).append(row)
                for endpoint, rows in by_endpoint.items():
                    if not rows or any(int(row.get("accepted", 0) or 0) > 0
                                       for row in rows):
                        continue
                    for row in rows:
                        for blocker in row.get("blockers") or ():
                            if not isinstance(blocker, dict):
                                continue
                            ref = str(blocker.get("ref") or "")
                            if not ref or ref in pair_refs:
                                continue
                            key = (
                                ref, endpoint,
                                round(float(normal[0]), 6),
                                round(float(normal[1]), 6),
                                round(float(axis[0]), 6),
                                round(float(axis[1]), 6),
                            )
                            relief_accumulator[key] = (
                                relief_accumulator.get(key, 0)
                                + int(blocker.get("count", 1) or 1))
            for child in value.values():
                collect_pair_relief(child)
        elif isinstance(value, list):
            for child in value:
                collect_pair_relief(child)

    collect_pair_relief(refused_pairs)
    pair_blocker_relief = [{
        "ref": ref, "endpoint": endpoint,
        "normal": [nx, ny], "axis": [ax, ay], "count": count,
    } for (ref, endpoint, nx, ny, ax, ay), count in sorted(
        relief_accumulator.items(),
        key=lambda item: (-item[1], item[0]))]
    binding_pair_blockers = {
        row["ref"] for row in pair_blocker_relief}
    if not binding_pair_blockers:
        binding_pair_blockers = {
            str(ref) for row in refused_pairs
            for ref in (row.get("blocker_refs") or ())
            if ref and str(ref) not in pair_refs}
    return {
        "wall_s": report.get("wall_s"),
        "gate": report.get("gate"),
        "fanout_blocked_count": int(fanout.get("blocked", 0) or 0),
        "critical_pair_refused_count": (
            len(refused_pairs)
            + critical_error_count),
        "critical_pair_error": critical_routes.get("error"),
        "critical_pair_refused": refused_pairs,
        "critical_pair_failure_certificates": [{
            "name": row.get("name"),
            "certificate": dict(row.get("failure_certificate") or {}),
        } for row in refused_pairs if row.get("failure_certificate")],
        "critical_pair_refs": sorted(pair_refs),
        "critical_pair_blocker_refs": sorted(binding_pair_blockers),
        "critical_pair_blocker_relief": pair_blocker_relief[
            :int(connection_limit)],
        "critical_pair_flow_through_refs": sorted({
            str(ref) for row in refused_pairs
            for ref in (row.get("flow_through") or ()) if ref}),
        "critical_kelvin_refused_count": len(refused_kelvin),
        "critical_kelvin_refused": compact_refused_kelvin,
        "critical_kelvin_refs": sorted(kelvin_refs),
        "critical_kelvin_blocker_refs": sorted(kelvin_blocker_refs),
        "critical_kelvin_blocker_details": kelvin_blocker_details[
            :int(connection_limit)],
        "critical_route_quality_refused_count": (
            len(refused_quality) + quality_error_count),
        "critical_route_quality_refused": refused_quality,
        "critical_route_quality_refs": sorted({
            str(ref) for row in refused_quality
            for ref in (row.get("refs") or ()) if ref}),
        "critical_route_quality_error": route_quality.get("error"),
        "critical_route_refused_count": (
            len(refused_kelvin) + len(refused_pairs)
            + len(refused_quality) + quality_error_count
            + critical_error_count),
        "critical_declaration_error_count": (
            len(declaration.get("unresolved") or ())
            + len(declaration.get("ambiguous") or {})),
        "critical_declaration": declaration,
        "critical_pin_access_blocked_count": int(
            critical.get("pin_access_blocked_count", 0) or 0),
        "critical_unroutable_count": int(
            critical.get("unroutable_count", 0) or 0),
        # A missing straight escape ray is a warning rather than proof of
        # impossibility, but it is a strong placement-ranking signal.
        "pin_access_blocked_count":
            int(pin_access.get("blocked_count", 0) or 0),
        "pin_access_blocked":
            list(pin_access.get("blocked") or ())[:int(blocked_limit)],
        "unroutable_count": int(congestion.get("unroutable_count", 0) or 0),
        "unroutable_connections":
            list(congestion.get("unroutable_connections") or ())[
                :int(connection_limit)],
        "residual_overuse": float(
            congestion.get("residual_overuse", 0.0) or 0.0),
        "residual_overuse_escaped": float(
            congestion.get("residual_overuse_escaped", 0.0) or 0.0),
        "blocked_cell_count": int(stackup.get("blocked_cell_count", 0) or 0),
        "blocked_cells_per_layer":
            list(stackup.get("blocked_cells_per_layer") or ()),
        "layers": list(congestion.get("layers") or ()),
        "hotspots": list(congestion.get("hotspots") or ())[
            :int(hotspot_limit)],
        "blockage_witnesses": list(
            congestion.get("blockage_witnesses") or ())[
                :int(connection_limit)],
        "backend": congestion.get("backend"),
        "backend_requested": congestion.get("backend_requested"),
        "backend_work_cells": congestion.get("backend_work_cells"),
        "auto_gpu_floor": congestion.get("auto_gpu_floor"),
        "route_awareness_service": dict(
            congestion.get("route_awareness_service") or {}),
        "negotiation": dict(congestion.get("negotiation") or {}),
        "future_congestion_present": report.get(
            "future_congestion") is not None,
        "future_congestion": dict(future),
        "future_critical_corridor_conflicts": int(
            future.get("critical_corridor_conflicts", 0) or 0),
        "future_reservation_crossings": int(
            future.get("reservation_crossings", 0) or 0),
        "future_reservation_refused_count": len(
            future.get("reservation_refused_nets") or ()),
        "future_reservation_rect_count": int(
            future.get("reservation_rect_count", 0) or 0),
        "future_reservation_cell_count": int(
            future.get("reservation_cell_count", 0) or 0),
        "future_reservation_owned_nets": list(
            future.get("reservation_owned_nets") or ()),
        "route_reservation_enabled": bool(route_reservations.get("enabled")),
        "route_reservation_fingerprint": route_reservations.get("fingerprint"),
        "future_overflow_units": int(
            future.get("overflow_units", 0) or 0),
        "future_corridor_obstacle_crossings": int(
            future.get("corridor_obstacle_crossings", 0) or 0),
        "future_expected_via_count": int(
            future.get("expected_via_count", 0) or 0),
        "future_wire_demand_units": int(
            future.get("wire_demand_units", 0) or 0),
        "multiresolution": dict(report.get("multiresolution") or {}),
    }


def placement_evidence_key(evidence):
    """Best-first lexicographic key for physically preflighted placements."""
    if not isinstance(evidence, dict) or evidence.get("error"):
        return (1, 999999, 999999, 999999, 999999, 999999, 999999,
                999999, 999999, 999999, 999999, 999999, 1.0e30,
                1.0e30, 1.0e30, 1.0e30, 1.0e30, 1.0e30)
    return (
        0,
        int(evidence.get(
            "critical_route_refused_count",
            evidence.get("critical_pair_refused_count", 0)) or 0),
        int(evidence.get("critical_declaration_error_count", 0) or 0),
        int(evidence.get("critical_pin_access_blocked_count", 0) or 0),
        int(evidence.get("critical_unroutable_count", 0) or 0),
        int(evidence.get("fanout_blocked_count", 0) or 0),
        int(evidence.get("pin_access_blocked_count", 0) or 0),
        int(evidence.get("unroutable_count", 0) or 0),
        0 if evidence.get("future_congestion_present") else 1,
        int(evidence.get("future_reservation_refused_count", 0) or 0),
        int(evidence.get("future_reservation_crossings", 0) or 0),
        int(evidence.get("future_critical_corridor_conflicts", 0) or 0),
        int(evidence.get("future_overflow_units", 0) or 0),
        int(evidence.get("future_corridor_obstacle_crossings", 0) or 0),
        int(evidence.get("future_expected_via_count", 0) or 0),
        int(evidence.get("future_wire_demand_units", 0) or 0),
        float(evidence.get("residual_overuse_escaped", 0.0) or 0.0),
        float(evidence.get("residual_overuse", 0.0) or 0.0),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board")
    parser.add_argument("--grid-mm", type=float, default=0.5)
    parser.add_argument("--iters", type=int, default=40)
    parser.add_argument("--backend", choices=("auto", "cpu", "gpu"), default="auto")
    parser.add_argument("--no-congestion", action="store_true")
    parser.add_argument("--heatmap")
    parser.add_argument("--multiresolution", action="store_true")
    parser.add_argument("--future-congestion", action="store_true",
                        help="include incremental layer/via/corridor forecast")
    parser.add_argument("--coarse-factor", type=float, default=2.0)
    critical_group = parser.add_mutually_exclusive_group()
    critical_group.add_argument(
        "--critical-net", action="append", default=None,
        help="exact or unambiguous leaf net to prioritize; repeatable")
    critical_group.add_argument(
        "--no-policy-critical-nets", action="store_true",
        help="controlled A/B only: disable board-policy critical selectors")
    parser.add_argument("--board-hint",
                        help="board identity for renamed/archive PCB artifacts")
    parser.add_argument("-o", "--output")
    args = parser.parse_args()
    critical_nets = (() if args.no_policy_critical_nets
                     else args.critical_net)
    if args.multiresolution and not args.no_congestion:
        report = analyze_multiresolution(
            args.board, grid_mm=args.grid_mm, iters=args.iters,
            backend=args.backend, coarse_factor=args.coarse_factor,
            heatmap_path=args.heatmap, critical_nets=critical_nets,
            board_hint=args.board_hint,
            run_future_congestion=args.future_congestion)
    else:
        report = analyze(args.board, grid_mm=args.grid_mm, iters=args.iters,
                         backend=args.backend,
                         run_congestion=not args.no_congestion,
                         heatmap_path=args.heatmap,
                         run_future_congestion=args.future_congestion,
                         critical_nets=critical_nets,
                         board_hint=args.board_hint)
    payload = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        with open(args.output, "w") as handle:
            handle.write(payload + "\n")
    else:
        print(payload)


if __name__ == "__main__":
    main()
