"""Bounded reuse of real same-face, unchanged-source-width supply copper.

An already connected pad/barrel must not acquire a redundant routed tail.
Use only actual anchors and native straight tracks at the full source/class
floor. No zone, intermediate pad, layer change, thinner leaf, fictitious
conductor or assumed parallel-current share grants continuity here. This
geometric proof is not barrel ampacity, thermal or release qualification.
"""
from collections import deque
import hashlib
import math
import time

import pcbnew
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
from cec_native_bus_column import _authority
import cec_native_supply_via_context as web


def _binding(inventory):
    return hashlib.sha256(repr(sorted(inventory.items())).encode()).hexdigest()


def portal(board, at_nm, *, net, source, board_hint, from_layer, to_layer,
           run_guard, endpoint_guard, timeout_s=2.):
    """Read-only exact retained through-via reuse; no new barrel is inferred.

    Its real two-face contacts must already meet unchanged source/class web
    and native process floors. Partial-stack or undersized retained barrels
    receive no preference or waiver merely because they already exist.
    """
    if (not isinstance(at_nm, (list, tuple)) or len(at_nm) != 2
            or any(type(v) is not int or abs(v) > 2_000_000_000 for v in at_nm)
            or type(net) is not str or not net or not source or not board_hint
            or type(from_layer) is not int or type(to_layer) is not int
            or from_layer == to_layer or not callable(run_guard) or not callable(endpoint_guard)
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10.):
        raise ValueError('bounded_exact_retained_source_portal_required')
    enabled = tuple(map(int, board.GetEnabledLayers().CuStack()))
    deadline = time.monotonic()+timeout_s
    planes = {board.GetLayerID(n) for n in fr.plane_layers(board)}
    if any(l not in enabled or l in planes for l in (from_layer, to_layer)):
        return None
    matches = [i for i in board.GetTracks() if i.GetClass() == 'PCB_VIA'
        and tuple(i.GetPosition()) == tuple(at_nm) and str(i.GetNetname()) == net]
    if len(matches) != 1:
        return None
    via = matches[0]
    if (via.GetViaType() != pcbnew.VIATYPE_THROUGH or int(via.TopLayer()) != pcbnew.F_Cu
            or int(via.BottomLayer()) != pcbnew.B_Cu
            or not all(via.IsOnLayer(l) for l in enabled)):
        return None
    authority = _authority(board, net)
    if authority is None:
        return None
    spec = cells._netclass(board, net); settings = board.GetDesignSettings()
    native_floor = max(spec['width'], settings.m_TrackMinWidth)
    contract = dict(net=net, current_authority=authority['current_authority'],
        required_by_layer_mm={fab.COPPER_LAYER_IDS[l]:w/1e6
            for l,w in authority['required_by_layer_nm'].items()},
        routing_layers=[fab.COPPER_LAYER_IDS[l] for l in enabled if l not in planes])
    before = field._field_snapshot_inventory(board)
    remaining = deadline-time.monotonic()
    if remaining <= 0:
        return None
    try:
        proof = web.receive(board, force._uid(via), contract, timeout_s=min(timeout_s,remaining))
    except ValueError:
        return None
    if (not proof['ok'] or not proof['complete']
            or any(fab.COPPER_LAYER_IDS[l] not in proof['actual_contact_layers']
                for l in (from_layer, to_layer))
            or endpoint_guard({'native_uuids': [force._uid(via)]}) is not True):
        return None
    drill = via.GetDrillValue()
    if drill < settings.m_MinThroughDrill:
        return None
    for layer in enabled:
        if time.monotonic() >= deadline:
            return None
        diameter = via.GetWidth(layer)
        if (diameter < settings.m_ViasMinSize or diameter-drill < 2*settings.m_ViasMinAnnularWidth
                or run_guard(tuple(at_nm),tuple(at_nm),diameter,layer) is not True):
            return None
        if (fab.COPPER_LAYER_IDS[layer] in proof['actual_contact_layers']
                and diameter-drill < max(native_floor, authority['required_by_layer_nm'][layer])):
            return None
    if before != field._field_snapshot_inventory(board):
        raise ValueError('native_retained_source_portal_mutated_board')
    return dict(schema=1, scope='exact_actual_retained_full_source_web_through_portal',
        via_uuid=force._uid(via), at_nm=list(at_nm), net=net,
        from_layer=fab.COPPER_LAYER_IDS[from_layer], to_layer=fab.COPPER_LAYER_IDS[to_layer],
        source_binding_sha256=_binding(before), actual_native_contacts=proof,
        unchanged_source_current_authority=authority['current_authority'],
        board_mutated=False, current_sharing_inferred=False,
        plated_barrel_ampacity_qualified=False, release_authority=False)


def plan(board, start_uuid, end_uuid, *, source, board_hint, layer,
         run_guard, endpoint_guard, timeout_s=2., max_items=512):
    """Read-only source-owned native proof, or None when not proved in budget.

    Guards must explicitly receive actual anchors and every reused conductor.
    Only literal True grants permission; truthy/unknown results never do.
    The caller must still receive saved connectivity, current debt, actual
    barrel contacts, fields and full native DRC of the whole transaction.
    """
    if (type(start_uuid) is not str or not start_uuid or type(end_uuid) is not str
            or not end_uuid or start_uuid == end_uuid or not source or not board_hint
            or type(layer) is not int or layer not in board.GetEnabledLayers().CuStack()
            or not callable(run_guard) or not callable(endpoint_guard)
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10. or type(max_items) is not int
            or not 2 <= max_items <= 1024):
        raise ValueError('bounded_actual_source_rated_continuation_required')
    deadline = time.monotonic()+timeout_s
    if layer in {board.GetLayerID(n) for n in fr.plane_layers(board)}:
        return None
    native = [*(p for fp in board.GetFootprints() for p in fp.Pads()), *board.GetTracks()]
    if len(native) > 16384:
        raise ValueError('native_rated_continuation_inventory_bound')
    anchors = {}
    for item in native:
        uid = force._uid(item)
        if uid not in (start_uuid, end_uuid):
            continue
        if uid in anchors:
            raise ValueError('ambiguous_native_rated_continuation_anchor')
        anchors[uid] = item
    if set(anchors) != {start_uuid, end_uuid}:
        return None
    start, end = anchors[start_uuid], anchors[end_uuid]
    net = str(start.GetNetname())
    if (start.GetNetCode() <= 0 or start.GetNetCode() != end.GetNetCode()
            or any(i.GetClass() not in ('PAD', 'PCB_VIA') or not i.IsOnLayer(layer)
                or i.GetClass() == 'PAD' and i.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH
                for i in (start, end))):
        return None
    authority = _authority(board, net)
    if authority is None:
        return None
    spec = cells._netclass(board, net)
    width = max(spec['width'], authority['required_by_layer_nm'][layer],
        board.GetDesignSettings().m_TrackMinWidth)
    for item in (start, end):
        if (item.GetClass() == 'PCB_VIA' and (item.GetDrillValue() <= 0
                or item.GetWidth(layer)-item.GetDrillValue() < width)
                or endpoint_guard({'native_uuids': [force._uid(item)]}) is not True):
            return None
    tracks = sorted((i for i in board.GetTracks() if i.GetClass() == 'PCB_TRACK'
        and i.GetNetCode() == start.GetNetCode() and int(i.GetLayer()) == layer
        and i.GetWidth() >= width), key=force._uid)
    if len(tracks)+2 > max_items:
        return None
    before = field._field_snapshot_inventory(board)
    # Keep shapes alive while their borrowed SWIG bounding boxes are in use.
    nodes = [start, end, *tracks]
    shapes = [i.GetEffectiveShape(layer) for i in nodes]
    boxes = [s.BBox() for s in shapes]
    permitted = {0: True, 1: True}
    def allows(index):
        if index not in permitted:
            item = nodes[index]
            permitted[index] = run_guard(tuple(item.GetStart()), tuple(item.GetEnd()),
                item.GetWidth(), layer) is True
        return permitted[index]
    def overlaps(a, b):
        return not (a.GetRight() < b.GetX() or b.GetRight() < a.GetX()
            or a.GetBottom() < b.GetY() or b.GetBottom() < a.GetY())
    parents = {0: None}; queue = deque([0]); tested = 0
    while queue and 1 not in parents:
        index = queue.popleft()
        for other in range(len(nodes)):
            if time.monotonic() >= deadline:
                return None
            if other in parents or not overlaps(boxes[index], boxes[other]):
                continue
            tested += 1
            if shapes[index].Collide(shapes[other], 0) and allows(other):
                parents[other] = index; queue.append(other)
                if other == 1:
                    break
    if 1 not in parents:
        return None
    path = [1]
    while parents[path[-1]] is not None:
        path.append(parents[path[-1]])
    path.reverse()
    if before != field._field_snapshot_inventory(board):
        raise ValueError('native_rated_continuation_mutated_source')
    return dict(schema=1, scope='actual_same_face_full_source_width_continuation',
        source=str(source), board_hint=board_hint, source_binding_sha256=_binding(before),
        net=net, layer=fab.COPPER_LAYER_IDS[layer], start_uuid=start_uuid, end_uuid=end_uuid,
        native_path_uuids=[force._uid(nodes[i]) for i in path],
        reused_track_rows=[dict(uuid=force._uid(nodes[i]), width_nm=nodes[i].GetWidth(),
            start_nm=list(nodes[i].GetStart()), end_nm=list(nodes[i].GetEnd()))
            for i in path if i >= 2],
        unchanged_source_current_authority=authority['current_authority'],
        source_physical_floor_nm=authority['required_by_layer_nm'][layer],
        unchanged_class_and_native_floor_nm=max(spec['width'],
            board.GetDesignSettings().m_TrackMinWidth), required_full_width_nm=width,
        tested_native_contacts=tested, complete=True, connected=True, board_mutated=False,
        zones_or_intermediate_pads_or_layer_jumps_used=False, current_sharing_inferred=False,
        plated_barrel_ampacity_qualified=False, thermal_qualified=False, release_authority=False)


def retained_entry(board, parent, start_uuid, *, source, board_hint, layer,
                   run_guard, endpoint_guard, timeout_s=2.):
    """Receive a new branch reached through actual unchanged rated copper.

    An overlap trimmer may remove the added segment at a source pad. That
    does not justify fabricating an incident segment or accepting a hint:
    require an actual same-face, full-source-width native path containing
    both retained and newly added tracks to a real newly added barrel.
    Surface contact, saved barrel contacts and whole-board admission remain
    independent obligations of the caller.
    """
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10. or type(start_uuid) is not str
            or not start_uuid or type(layer) is not int or not source
            or not board_hint or not callable(run_guard)
            or not callable(endpoint_guard)):
        raise ValueError('bounded_actual_retained_entry_required')
    deadline = time.monotonic()+timeout_s
    before = field._field_snapshot_inventory(board)
    original = field._field_snapshot_inventory(parent)
    stable = {key: row for key, row in original.items() if key[0] in ('track', 'pad')}
    if any(before.get(key) != row for key, row in stable.items()):
        return None
    old = {key[1] for key in original if key[0] == 'track'}
    added = {key[1] for key in before if key[0] == 'track'}-old
    portals = sorted((t for t in board.GetTracks()
        if t.GetClass() == 'PCB_VIA' and force._uid(t) in added
        and t.IsOnLayer(layer)), key=force._uid)
    if not 1 <= len(portals) <= 6:
        return None
    for via in portals:
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            return None
        received = plan(board, start_uuid, force._uid(via), source=source,
            board_hint=board_hint, layer=layer, run_guard=run_guard,
            endpoint_guard=endpoint_guard, timeout_s=min(remaining, 10.))
        if received is None:
            continue
        track_ids = {row['uuid'] for row in received['reused_track_rows']}
        retained, incoming = sorted(track_ids & old), sorted(track_ids & added)
        if not retained or not incoming:
            continue
        if before != field._field_snapshot_inventory(board):
            raise ValueError('native_retained_entry_mutated_source')
        return dict(received, scope='actual_retained_full_width_new_branch_entry',
            parent_binding_sha256=_binding(original),
            retained_track_uuids=retained, added_track_uuids=incoming,
            added_barrel_uuid=force._uid(via), original_native_material_unchanged=True,
            incident_added_pad_segment_inferred=False)
    return None
