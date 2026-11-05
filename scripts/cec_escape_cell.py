"""Bounded, layer-local escape-cell extraction and retained-copper islands.

No refdes, net-name or board-coordinate policy belongs here. A cell may absorb
only unlocked or independently re-provable narrow tracks. Pads, full-width
trunks, vias and other owners remain fixed. Islands never traverse a plane or
another layer: global net membership is not a proof of a short local return.
"""
from __future__ import annotations

import math

MM = 1_000_000


def _uid(item):
    return str(item.m_Uuid.AsString())


def _xy(point):
    return (int(point.x), int(point.y))


def _owners(board, item):
    return sorted(g.GetName() for g in board.Groups() if g.ContainsItem(item))


def _track_row(board, item):
    return {"uuid": _uid(item), "start": list(_xy(item.GetStart())),
            "end": list(_xy(item.GetEnd())), "layer": int(item.GetLayer()),
            "width_nm": int(item.GetWidth()), "locked": bool(item.IsLocked()),
            "groups": _owners(board, item)}


def extract(board, via, boundary, full_width, *, radius_mm=2.0, max_tracks=24):
    """Capture the complete cut boundary of a bounded narrow-track component.

    The explicit cut includes copper-area contacts, not just coincident track
    endpoints. Reconnecting these cut anchors is required even if the whole
    electrical net happens to be connected elsewhere through a plane.
    """
    import pcbnew
    import cec_fr
    center, radius = _xy(via.GetPosition()), round(radius_mm * MM)
    def inside(point):
        return math.dist(center, _xy(point)) <= radius
    tracks = { _uid(item): item for item in board.GetTracks()
               if item.GetNetCode() == via.GetNetCode()
               and item.GetClass() in {"PCB_TRACK", "PCB_ARC"} }
    selected = {row["uuid"] for row in boundary["branches"]}
    if any(key not in tracks for key in selected):
        return {"refused": "cell_branch_missing"}
    if any(not inside(point) for key in selected
           for point in (tracks[key].GetStart(), tracks[key].GetEnd())):
        return {"refused": "cell_branch_outside_window"}
    endpoints = {}
    for key, item in tracks.items():
        for point in (item.GetStart(), item.GetEnd()):
            endpoints.setdefault((*_xy(point), int(item.GetLayer())), set()).add(key)
    queue = sorted(selected)
    while queue:
        item = tracks[queue.pop(0)]
        for point in (item.GetStart(), item.GetEnd()):
            for key in sorted(endpoints[(*_xy(point), int(item.GetLayer()))] - selected):
                neighbor = tracks[key]
                owners = _owners(board, neighbor)
                if (neighbor.GetClass() != "PCB_TRACK" or neighbor.GetWidth() >= full_width
                        or (neighbor.IsLocked() and not owners)
                        or any(name != cec_fr.ENDPOINT_NECKDOWN_GROUP for name in owners)
                        or not all(inside(p) for p in (neighbor.GetStart(), neighbor.GetEnd()))):
                    continue
                if len(selected) >= max_tracks:
                    return {"refused": "cell_track_budget_exhausted", "limit": max_tracks}
                selected.add(key)
                queue.append(key)
    if len(selected) > max_tracks:
        return {"refused": "cell_track_budget_exhausted", "limit": max_tracks}
    anchors = {}
    refused = []
    def anchor(point, layer, source, width=full_width):
        if not inside(point):
            refused.append({"reason": "cut_anchor_outside_window", "source": source})
            return
        key = (*_xy(point), int(layer))
        row = anchors.setdefault(key, {"anchor": list(_xy(point)), "layer": int(layer),
                                      "width_nm": full_width, "locked": False, "sources": []})
        row["width_nm"] = max(row["width_nm"], int(width))
        if source not in row["sources"]:
            row["sources"].append(source)
    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()
            if pad.GetNetCode() == via.GetNetCode()]
    removed = [tracks[key] for key in sorted(selected)]
    retained = [item for key, item in tracks.items() if key not in selected]
    other_vias = [item for item in board.GetTracks() if item.GetClass() == "PCB_VIA"
                  and item.GetNetCode() == via.GetNetCode() and _uid(item) != _uid(via)]
    # Preserve every original contact with the barrel, including contact by
    # area with a fixed track. Those contacts may not lie on a removed branch.
    for row in boundary["fixed_contacts"]:
        if row["uuid"] not in selected:
            anchor(pcbnew.VECTOR2I(*row["anchor"]), row["layer"], row["uuid"])
    for row in boundary["pads"]:
        for layer in row["layers"]:
            anchor(pcbnew.VECTOR2I(*row["anchor"]), layer, row["uuid"])
    for item in removed:
        layer = int(item.GetLayer())
        shape = item.GetEffectiveShape()
        for pad in pads:
            if pad.IsOnLayer(layer) and (shape.Collide(pad.GetEffectiveShape(layer), 0)
                    or pad.GetEffectiveShape(layer).Collide(shape, 0)):
                anchor(pad.GetPosition(), layer, _uid(pad), item.GetWidth())
        for other in retained:
            if int(other.GetLayer()) != layer or not shape.Collide(other.GetEffectiveShape(), 0):
                continue
            if other.GetClass() != "PCB_TRACK":
                refused.append({"reason": "arc_cut_contact", "source": _uid(other)})
                continue
            near = min((other.GetStart(), other.GetEnd()),
                       key=lambda p: (min(math.dist(_xy(p), _xy(item.GetStart())),
                                          math.dist(_xy(p), _xy(item.GetEnd()))), _xy(p)))
            anchor(near, layer, _uid(other), item.GetWidth())
        for other in other_vias:
            if other.IsOnLayer(layer) and shape.Collide(other.GetPosition(), other.GetWidth(other.TopLayer()) // 2):
                anchor(other.GetPosition(), layer, _uid(other), item.GetWidth())
        for point in (item.GetStart(), item.GetEnd()):
            if point == via.GetPosition():
                continue
            members = endpoints[(*_xy(point), layer)]
            # An unshared endpoint remains an explicit outlet. Do not erase a
            # dangling or externally owned anchor just because there is no pad.
            if len(members & selected) == 1:
                anchor(point, layer, _uid(item), item.GetWidth())
    if refused:
        return {"refused": "cell_cut_not_bounded", "evidence": refused}
    return {"tracks": [_track_row(board, item) for item in removed],
            "anchors": [anchors[key] for key in sorted(anchors)],
            "expanded_tracks": len(selected) - len(boundary["branches"]),
            "center_nm": list(center), "radius_mm": radius_mm}


def retained_islands(board, anchors, net_code, *, center_nm, radius_mm=2.0,
                     max_primitives=128):
    """Partition cut anchors by exact retained *local same-layer* copper.

    Primitive budget overflow fails closed rather than asserting a partially
    sampled connectivity proof. Vias and zones cannot merge return anchors.
    """
    import pcbnew
    radius = radius_mm * MM
    def inside(point):
        return math.dist(center_nm, _xy(point)) <= radius
    primitives = []
    for item in board.GetTracks():
        if (item.GetClass() == "PCB_TRACK" and item.GetNetCode() == net_code
                and inside(item.GetStart()) and inside(item.GetEnd())):
            primitives.append((int(item.GetLayer()), _uid(item), item.GetEffectiveShape()))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() != net_code or not inside(pad.GetPosition()):
                continue
            # Only connected convex land shapes are eligible to merge points.
            # A custom disconnected pad primitive cannot prove an island.
            if pad.GetShape() not in (pcbnew.PAD_SHAPE_RECT, pcbnew.PAD_SHAPE_CIRCLE,
                                     pcbnew.PAD_SHAPE_OVAL, pcbnew.PAD_SHAPE_ROUNDRECT):
                continue
            box = pad.GetBoundingBox()
            if any(math.dist(center_nm, (x, y)) > radius
                   for x in (box.GetX(), box.GetX() + box.GetWidth())
                   for y in (box.GetY(), box.GetY() + box.GetHeight())):
                continue
            for layer in pad.GetLayerSet().CuStack():
                primitives.append((int(layer), _uid(fp) + ":" + _uid(pad),
                                   pad.GetEffectiveShape(layer)))
    if len(primitives) > max_primitives:
        return {"refused": "retained_island_budget_exhausted", "count": len(primitives),
                "limit": max_primitives}
    parent = list(range(len(primitives) + len(anchors)))
    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    def merge(i, j):
        parent[root(j)] = root(i)
    for i, (layer, _key, shape) in enumerate(primitives):
        for j in range(i):
            other_layer, _other_key, other = primitives[j]
            if layer == other_layer and shape.Collide(other, 0) and other.Collide(shape, 0):
                merge(i, j)
        for j, anchor in enumerate(anchors):
            if layer == anchor["layer"] and shape.Collide(pcbnew.VECTOR2I(*anchor["anchor"]), 0):
                merge(i, len(primitives) + j)
    groups = {}
    for index, anchor in enumerate(anchors):
        groups.setdefault(root(len(primitives) + index), []).append(anchor)
    return {"groups": sorted(groups.values(), key=lambda rows: (rows[0]["layer"], rows[0]["anchor"])),
            "anchors": len(anchors), "islands": len(groups), "primitives": len(primitives)}
