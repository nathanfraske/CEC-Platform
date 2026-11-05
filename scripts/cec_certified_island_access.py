"""Bounded attachment alternatives on two native-certified copper islands.

Planning only: no copper is moved, no same-net proximity is connectivity, and
no third island is substituted for either named endpoint's component.
"""
import math

import pcbnew
import cec_fr

MM = 1_000_000


def _key(item):
    kind = item.GetClass()
    uid = item.m_Uuid.AsString()
    if kind == 'PAD':
        point = item.GetPosition()
        return (kind, uid, item.GetParentFootprint().GetReference(),
                str(item.GetNumber()), int(point.x), int(point.y))
    if kind == 'PCB_VIA':
        point = item.GetPosition()
        return (kind, uid, int(point.x), int(point.y))
    if kind in {'PCB_TRACK', 'PCB_ARC'}:
        a, b = item.GetStart(), item.GetEnd()
        return (kind, uid, int(item.GetLayer()), int(a.x), int(a.y),
                int(b.x), int(b.y), int(item.GetWidth()))
    return None


def _anchors(board, item, class_width_nm):
    kind = item.GetClass()
    layers = frozenset(int(layer) for layer in board.GetEnabledLayers().CuStack()
                       if item.IsOnLayer(layer))
    if not layers:
        return []
    owner = dict(kind='via' if kind == 'PCB_VIA' else 'trk',
                 uuid=item.m_Uuid.AsString())
    escape = None
    if kind == 'PAD':
        owner.update(kind='pad', ref=item.GetParentFootprint().GetReference(),
                     pad=str(item.GetNumber()))
        if (item.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and
                min(item.GetSize().x, item.GetSize().y) < class_width_nm):
            # This flag affects ordering only. Actual neck-down geometry is
            # recomputed by the exact route solver from the live native pad.
            escape = True
    points = ((item.GetStart(), item.GetEnd()) if kind in {'PCB_TRACK', 'PCB_ARC'}
              else (item.GetPosition(),))
    return [(int(point.x), int(point.y), layers, escape,
             {**owner, 'x_mm': point.x/MM, 'y_mm': point.y/MM}) for point in points]


def _existing_full_stack_contact(board, item):
    """Existing plated barrel access, never permission to create a barrel."""
    enabled = {int(layer) for layer in board.GetEnabledLayers().CuStack()}
    try:
        if len(enabled) < 2:
            return False
        if item.GetClass() == 'PCB_VIA':
            if item.GetViaType() != pcbnew.VIATYPE_THROUGH:
                return False
            diameter, drill = int(item.GetWidth()), int(item.GetDrillValue())
        elif item.GetClass() == 'PAD':
            if item.GetAttribute() != pcbnew.PAD_ATTRIB_PTH or not item.HasHole():
                return False
            size, hole = item.GetSize(), item.GetDrillSize()
            diameter, drill = min(size.x, size.y), max(hole.x, hole.y)
        else:
            return False
        actual = {int(layer) for layer in item.GetLayerSet().CuStack()}
        return bool(enabled <= actual and 0 < drill < diameter)
    except (AttributeError, TypeError, ValueError):
        return False


def plan(board, net_code, sources, *, limit=6, max_mm=25., max_shift_mm=8.,
         max_items=4096, class_width_nm=500000, existing_access_shift_mm=None,
         interior_contacts=False):
    """Sources are two live (item, x_nm, y_nm) anchors from one exact pair."""
    if (len(sources) != 2 or isinstance(limit, bool) or int(limit) != limit or limit < 0
            or isinstance(max_items, bool) or int(max_items) != max_items or max_items < 1
            or not all(math.isfinite(v) and v >= 0 for v in (max_mm, max_shift_mm))
            or (existing_access_shift_mm is not None and (
                type(existing_access_shift_mm) not in (int, float)
                or not math.isfinite(existing_access_shift_mm)
                or not 0 < existing_access_shift_mm <= 80))
            or type(interior_contacts) is not bool
            or (interior_contacts and (type(class_width_nm) is not int
                                      or class_width_nm <= 0))):
        raise ValueError('invalid bounded island access domain')
    report = dict(schema=1, candidates=[], connectivity='native_connected_items',
                  limit=int(limit), max_mm=float(max_mm), max_shift_mm=float(max_shift_mm))
    if limit == 0:
        return report
    rows = {}
    for item in [*(pad for fp in board.GetFootprints() for pad in fp.Pads()),
                 *board.GetTracks()]:
        if int(item.GetNetCode()) != int(net_code):
            continue
        key = _key(item)
        if key is None:
            continue
        if key in rows:
            return {**report, 'refusal': 'ambiguous_native_item_identity'}
        rows[key] = item
        if len(rows) > max_items:
            return {**report, 'refusal': 'island_inventory_budget_exhausted'}
    # A cached board graph can be stale after an in-memory emission or
    # rollback. Rebuilding that graph is worse: KiCad may propagate a pad's
    # net onto inherited touching copper. Attachment discovery is read-only
    # authority, so build a private, fresh native contact graph instead.
    conn = cec_fr._read_only_route_connectivity(board, {net_code})
    islands = []
    anchors = []
    existing_access = []
    interiors = []
    for source_index, (source, x, y) in enumerate(sources):
        key = _key(source)
        if key not in rows or int(source.GetNetCode()) != int(net_code):
            return {**report, 'refusal': 'source_not_live_on_target_net'}
        if (int(x), int(y)) not in {(a[0], a[1]) for a in
                _anchors(board, rows[key], int(class_width_nm))}:
            return {**report, 'refusal': 'source_point_not_live'}
        members = {key}
        try:
            for item in conn.GetConnectedItems(rows[key]):
                if int(item.GetNetCode()) == int(net_code):
                    linked = _key(item)
                    if linked in rows:
                        members.add(linked)
        except Exception as exc:
            return {**report, 'refusal': 'native_connectivity_unavailable',
                    'error': type(exc).__name__}
        islands.append(members)
        points = []
        remote_access = []
        interior_points = []
        seen = set()
        for member in sorted(members):
            for point in _anchors(board, rows[member], int(class_width_nm)):
                shift = math.hypot(point[0]-x, point[1]-y)
                if shift > max_shift_mm*MM + 1e-6:
                    if (existing_access_shift_mm is not None
                            and shift <= existing_access_shift_mm*MM + 1e-6
                            and _existing_full_stack_contact(board, rows[member])):
                        remote_access.append(point)
                    continue
                # Prefer pad/via ownership at coincident points by retaining
                # layer/owner-aware anchors; different layers are never merged.
                point_key = (point[0], point[1], point[2], tuple(sorted(point[4].items())))
                if point_key not in seen:
                    seen.add(point_key)
                    points.append(point)
            if interior_contacts and rows[member].GetClass() == 'PCB_TRACK':
                import cec_native_track_ports as ports
                item = rows[member]
                opposite = sources[1-source_index]
                for point in ports.sites(item,
                        toward_nm=(int(opposite[1]), int(opposite[2])), max_sites=4):
                    # A one-nanometre point beside a source end is not a new
                    # physical launch domain. Keep a full class-width gap.
                    if (min(math.hypot(point[0]-end.x, point[1]-end.y)
                            for end in (item.GetStart(), item.GetEnd())) < class_width_nm
                            or math.hypot(point[0]-x, point[1]-y) > max_shift_mm*MM + 1e-6
                            or not ports.on_centerline(item, point)):
                        continue
                    layers = frozenset(int(layer) for layer in board.GetEnabledLayers().CuStack()
                                       if item.IsOnLayer(layer))
                    if layers:
                        interior_points.append((point[0], point[1], layers, None,
                            dict(kind='track_contact', uuid=item.m_Uuid.AsString(),
                                 x_mm=point[0]/MM, y_mm=point[1]/MM)))
        anchors.append(points)
        existing_access.append(remote_access)
        interiors.append(interior_points)
    report['component_items'] = [len(items) for items in islands]
    report['component_anchors'] = [len(items) for items in anchors]
    if islands[0] & islands[1]:
        return {**report, 'already_connected': True}
    pairs = cec_fr._bounded_route_aware_anchor_pairs(
        anchors[0], anchors[1], limit=int(limit)+1, max_mm=max_mm)
    access_pairs = []
    if existing_access_shift_mm is not None:
        # The local DRC witness is not the whole native component. Reserve a
        # finite tier for pre-existing plated layer access before spending the
        # lease on nearby pad/segment aliases. Pair distance is unchanged.
        reserved = min(2, max(1, int(limit)//3))
        access_pairs = []
        for left, right in ((existing_access[0], anchors[1]),
                            (anchors[0], existing_access[1]),
                            (existing_access[0], existing_access[1])):
            access_pairs.extend(cec_fr._bounded_route_aware_anchor_pairs(
                left, right, limit=reserved, max_mm=max_mm))
        access_pairs = cec_fr._route_aware_anchor_pair_order(access_pairs)[:reserved]
        report['existing_access_tier'] = dict(
            source='same_fresh_native_connected_component_existing_plated_contacts',
            shift_budget_mm=float(existing_access_shift_mm),
            component_anchors=[len(values) for values in existing_access],
            reserved_limit=reserved, proposed_pairs=len(access_pairs),
            pair_distance_bound_mm=float(max_mm),
            layer_access_only_not_path_clearance_or_new_barrel_authority=True,
            routing_authority=False, release_authority=False)
    interior_pairs = []
    if interior_contacts:
        reserved = min(2, max(1, int(limit)//3))
        for left, right in ((interiors[0], anchors[1]),
                            (anchors[0], interiors[1]),
                            (interiors[0], interiors[1])):
            interior_pairs.extend(cec_fr._bounded_route_aware_anchor_pairs(
                left, right, limit=reserved, max_mm=max_mm))
        interior_pairs = cec_fr._route_aware_anchor_pair_order(interior_pairs)[:reserved]
        report['interior_contact_tier'] = dict(
            source='same_fresh_native_connected_component_straight_track_centerlines',
            max_sites_per_track=4, endpoint_separation_nm=class_width_nm,
            component_anchors=[len(values) for values in interiors],
            local_shift_bound_mm=float(max_shift_mm), pair_distance_bound_mm=float(max_mm),
            reserved_limit=reserved, proposed_pairs=len(interior_pairs),
            ranking='after_existing_remote_access_before_local_aliases',
            geometry_only=True, routing_authority=False, release_authority=False)
    pairs = access_pairs + interior_pairs + pairs
    original = tuple((int(source[1]), int(source[2]), tuple(sorted(
        int(layer) for layer in board.GetEnabledLayers().CuStack()
        if source[0].IsOnLayer(layer)))) for source in sources)
    seen = set()
    for distance, left, right in pairs:
        key = ((left[0], left[1], tuple(sorted(left[2]))),
               (right[0], right[1], tuple(sorted(right[2]))))
        if key == original or key in seen:
            continue
        seen.add(key)
        report['candidates'].append(dict(endpoints=[left[4], right[4]],
            distance_mm=round(float(distance),6),
            layers=[sorted(left[2]),sorted(right[2])]))
        if len(report['candidates']) >= limit:
            break
    return report
