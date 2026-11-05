"""Bounded, topology-owned copper inside a rigidly moved placement cell.

This is not whole-net ownership. Only short, unbranched same-layer paths
between two exact cell terminals may follow the cell. Foreign contacts,
zones, vias, locks and explicit groups remain boundaries. The caller must
still reconnect external anchors and run whole-board admission.
"""
from collections import defaultdict
import math


def chains(edges, terminals, *, blocked_nodes=(), max_items=12,
           max_length_mm=8.0):
    """Find bounded degree-two paths; no board names or spatial seat recipes.

    All edges, including immovable ones, participate in degree calculation.
    Removing them from the graph would incorrectly hide a real junction.
    Nodes include net and layer, so coincident traces on different layers
    cannot create a fictitious route through the board.
    """
    adjacency = defaultdict(list)
    for edge in edges:
        for node in (edge['start'], edge['end']):
            adjacency[node].append(edge)
    blocked = set(blocked_nodes)
    result = {}
    for origin in sorted(terminals):
        if origin in blocked:
            continue
        for first in adjacency[origin]:
            node, edge, path, seen, length = origin, first, [], set(), 0.0
            while True:
                uid = edge['uuid']
                if uid in seen or not edge.get('movable', False):
                    break
                seen.add(uid)
                path.append(uid)
                length += edge['length_mm']
                if len(path) > max_items or length > max_length_mm:
                    break
                node = edge['end'] if node == edge['start'] else edge['start']
                if node in blocked:
                    break
                if node in terminals:
                    if node != origin and terminals[node] != terminals[origin]:
                        result.setdefault(tuple(sorted(path)), {
                            'uuids': list(path), 'terminals': [origin, node],
                            'length_mm': round(length, 6)})
                    break
                adjacent = adjacency[node]
                if len(adjacent) != 2:
                    break
                edge = next(item for item in adjacent if item['uuid'] != uid)
    return [result[key] for key in sorted(result)]


def _uid(item):
    return item.m_Uuid.AsString()


def _node(item, point):
    return (int(item.GetNetCode()), int(item.GetLayer()),
            int(point.x), int(point.y))


def plan(board, footprints, *, generated_locked_uuids=(),
         protected_nets=(), max_items=12, max_length_mm=8.0):
    """Native contact check for the bounded pure-graph proposal above.

    Straight paths only in this slice. An arc/via touching a proposed path
    stays a fixed contact, not an excuse to silently translate half a route.
    Native shapes catch foreign pad overlap and mid-segment copper junctions
    that an endpoint-only graph cannot see.
    """
    import pcbnew

    moving = {_uid(fp) for fp in footprints}
    pads = [pad for fp in board.GetFootprints() for pad in fp.Pads()
            if pad.IsOnCopperLayer()]
    tracks = list(board.GetTracks())
    track_map = {_uid(item): item for item in tracks}
    authorized = set(generated_locked_uuids)
    protected = set(protected_nets)
    grouped = {_uid(item) for group in board.Groups()
               for item in group.GetItems()}
    terminals, ambiguous = {}, set()
    for pad in pads:
        if (_uid(pad.GetParentFootprint()) in moving
                and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD
                and pad.GetNetCode() > 0):
            # Copper endpoints inside the native land are real terminals even
            # when rounded coordinates differ from its centre. Do not enlarge
            # the land or use a proximity/bounding-box ownership shortcut.
            nodes = {_node(pad, pad.GetCenter())}
            for track in tracks:
                if (track.GetClass() != 'PCB_TRACK' or track.GetNetCode() != pad.GetNetCode()
                        or not pad.IsOnLayer(track.GetLayer())):
                    continue
                shape = pad.GetEffectiveShape(track.GetLayer())
                nodes.update(_node(track, point) for point in (track.GetStart(), track.GetEnd())
                             if shape.Collide(point, 0))
            for node in nodes:
                if node in terminals and terminals[node] != _uid(pad):
                    ambiguous.add(node)
                terminals[node] = _uid(pad)
    edges = []
    for item in tracks:
        if item.GetClass() != 'PCB_TRACK':
            continue
        a, b = item.GetStart(), item.GetEnd()
        edges.append(dict(uuid=_uid(item), start=_node(item, a),
            end=_node(item, b), length_mm=math.hypot(b.x-a.x, b.y-a.y)/1e6,
            movable=(_uid(item) not in grouped
                     and item.GetNetname() not in protected
                     and (not item.IsLocked() or _uid(item) in authorized))))
    proposed = chains(edges, terminals, blocked_nodes=ambiguous, max_items=max_items,
                      max_length_mm=max_length_mm)
    accepted, rejected, selected = [], [], set()
    for chain in proposed:
        ids = set(chain['uuids'])
        reason = None
        for uid in chain['uuids']:
            item = track_map[uid]
            layer, net = item.GetLayer(), item.GetNetCode()
            shape = item.GetEffectiveShape(layer)
            for pad in pads:
                if (_uid(pad.GetParentFootprint()) not in moving
                        and pad.IsOnLayer(layer) and pad.GetNetCode() == net
                        and shape.Collide(pad.GetEffectiveShape(layer), 0)):
                    reason = 'foreign_pad_contact'
                    break
            if reason:
                break
            for other in tracks:
                if (_uid(other) in ids or not other.IsOnLayer(layer)
                        or other.GetNetCode() != net):
                    continue
                if not shape.Collide(other.GetEffectiveShape(layer), 0):
                    continue
                # External incident branches are already explicitly removed
                # and reconnected by the parent move at a selected pad.
                # Permit only a single shared terminal, never a collinear
                # overlap or a mid-segment tee hidden by the endpoint graph.
                common = ({_node(item, item.GetStart()), _node(item, item.GetEnd())}
                          & {_node(other, other.GetStart()), _node(other, other.GetEnd())}
                          & terminals.keys()) if other.GetClass() == 'PCB_TRACK' else set()
                permitted = False
                if len(common) == 1:
                    node = next(iter(common))
                    vectors = []
                    for obj in (item, other):
                        far = obj.GetEnd() if _node(obj, obj.GetStart()) == node else obj.GetStart()
                        vectors.append((far.x-node[2], far.y-node[3]))
                    (ax, ay), (bx, by) = vectors
                    permitted = ax*by != ay*bx or ax*bx + ay*by <= 0
                if not permitted:
                    reason = 'external_copper_contact'
                    break
            if reason:
                break
            for zone in board.Zones():
                if (zone.GetNetCode() == net and zone.IsOnLayer(layer)
                        and not zone.GetIsRuleArea()
                        and zone.Outline().Collide(
                            pcbnew.SEG(item.GetStart(), item.GetEnd()),
                            int(item.GetWidth()/2))):
                    # Conservative: an unfilled authored zone is still a
                    # boundary. No zone fill is invented by this local move.
                    reason = 'zone_contact'
                    break
            if reason:
                break
        if len(selected | ids) > max_items:
            reason = 'cell_item_budget'
        if reason:
            rejected.append({**chain, 'reason': reason})
        else:
            accepted.append(chain)
            selected.update(ids)
    return dict(schema=1, internal_track_uuids=sorted(selected),
                accepted=accepted, rejected=rejected,
                max_items=max_items, max_length_mm=max_length_mm,
                release_authority=False)


def copper_inventory(board):
    """Exact native track/arc/via identity and geometry (not a DRC score)."""
    result = {}
    for item in board.GetTracks():
        row = [item.GetClass(), item.GetNetname(), bool(item.IsLocked())]
        if item.GetClass() == 'PCB_VIA':
            pos = item.GetPosition()
            row.extend([pos.x, pos.y, item.TopLayer(), item.BottomLayer(),
                        item.GetWidth(item.TopLayer()), item.GetDrillValue(),
                        int(item.GetViaType()),
                        [(int(layer), int(item.GetWidth(layer)))
                         for layer in board.GetEnabledLayers().CuStack()
                         if item.IsOnLayer(layer)]])
        else:
            a, b = item.GetStart(), item.GetEnd()
            row.extend([a.x, a.y, b.x, b.y, item.GetLayer(), item.GetWidth()])
            if item.GetClass() == 'PCB_ARC':
                mid = item.GetMid()
                row.extend([mid.x, mid.y])
        uid = _uid(item)
        if not uid or uid in result:
            raise ValueError('ambiguous native copper identity')
        result[uid] = row
    return result


def compare_inventory(before, after, *, moved=(), removed=()):
    """Authorize only declared moves/removals; no unrelated copper changes."""
    moved, removed = set(moved), set(removed)
    unauthorized = sorted(uid for uid in before.keys() | after.keys()
                          if before.get(uid) != after.get(uid)
                          and uid not in moved | removed)
    errors = []
    if moved & removed:
        errors.append('conflicting_ownership')
    if not (moved | removed) <= before.keys():
        errors.append('unknown_owned_item')
    if not moved <= after.keys() or removed & after.keys():
        errors.append('owned_item_postcondition')
    return dict(ok=not unauthorized and not errors,
                unauthorized_uuids=unauthorized, errors=errors,
                retained_unrelated_items=len(before.keys() - moved - removed),
                moved_items=len(moved), removed_items=len(removed))
