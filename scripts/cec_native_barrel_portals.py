"""Retained plated-barrel access for bounded, read-only route proposals.

Native drill/flash and finite incident copper decide physical access. This
does not qualify barrel ampacity, allocate current or authorize new copper.
No same-net island union, plane pickup or new via is inferred here.
"""
import math
import time

import pcbnew

MAX_ITEMS = 8192
MAX_PORTALS = 256


def inventory(board, net_code, layers, bounds_nm, *, deadline):
    import cec_fr as fr
    if (type(net_code) is not int or net_code <= 0
            or not isinstance(layers, (tuple, list)) or not 1 <= len(layers) <= 8
            or any(type(l) is not int for l in layers)
            or type(deadline) not in (int, float) or not math.isfinite(deadline)
            or not time.monotonic() < deadline <= time.monotonic()+10.
            or len(bounds_nm) != 4 or any(type(v) is not int for v in bounds_nm)):
        raise ValueError('bounded_exact_retained_barrel_inventory_required')
    x0, y0, x1, y1 = bounds_nm
    if x0 > x1 or y0 > y1:
        raise ValueError('retained_barrel_inventory_bounds_required')
    enabled = set(map(int, board.GetEnabledLayers().CuStack()))
    planes = {int(board.GetLayerID(n)) for n in fr.plane_layers(board)}
    if not set(layers) <= enabled-planes:
        raise ValueError('retained_barrel_explicit_nonplane_faces_required')
    items = [*board.GetTracks(), *(p for fp in board.GetFootprints() for p in fp.Pads())]
    if len(items) > MAX_ITEMS:
        raise ValueError('retained_barrel_native_inventory_bound')
    rows = {}; seen = set()
    for item in items:
        if time.monotonic() >= deadline:
            raise ValueError('retained_barrel_inventory_deadline')
        if int(item.GetNetCode()) != net_code or item.GetClass() not in ('PAD', 'PCB_VIA'):
            continue
        at = tuple(item.GetPosition())
        if not x0 <= at[0] <= x1 or not y0 <= at[1] <= y1:
            continue
        actual = set(map(int, fr._through_barrel_layers(board, item)))
        accessible = sorted(l for l in layers if l in actual and item.FlashLayer(l))
        if len(accessible) < 2:
            continue
        uid = str(item.m_Uuid.AsString())
        if not uid or uid in seen:
            raise ValueError('retained_barrel_ambiguous_native_identity')
        seen.add(uid)
        if len(seen) > MAX_PORTALS:
            raise ValueError('retained_barrel_portal_inventory_bound')
        rows.setdefault(at, []).append(dict(item=item, uuid=uid, layers=accessible,
            at_nm=list(at), native_kind=item.GetClass(), new_barrel=False,
            capacity_qualified=False))
    return {at: sorted(values, key=lambda row: row['uuid']) for at, values in rows.items()}


def receive_operations(board, operations, transitions, *, terminal_points=(), deadline):
    """Require finite copper on each NEW incident face, minus actual drill voids."""
    import cec_fr as fr
    if len(operations) > 4096 or len(transitions) > MAX_PORTALS:
        raise ValueError('retained_barrel_saved_operation_inventory_bound')
    rows = []
    for row, source_face, target_face in transitions:
        if time.monotonic() >= deadline:
            raise ValueError('retained_barrel_contact_deadline')
        at = tuple(row['at_nm']); incidents = []
        for op in operations:
            if (op[0] != 'trk' or int(op[4]) not in (source_face, target_face)
                    or at not in (tuple(op[1]), tuple(op[2]))):
                continue
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(op[1]); track.SetEnd(op[2]); track.SetWidth(op[3]); track.SetLayer(op[4])
            track.SetNetCode(row['item'].GetNetCode()); incidents.append(track)
        faces = {int(t.GetLayer()) for t in incidents}
        # A real retained terminal already owns its other incident face.
        # Interior transitions need positive incident material on BOTH faces.
        required = {source_face, target_face} if at not in terminal_points else faces
        if (not incidents or not required <= faces
                or not fr._barrel_contacts_tracks(board, row['item'], incidents,
                    timeout_s=min(1., max(.001, deadline-time.monotonic())))):
            raise ValueError('retained_barrel_finite_incident_copper_refused')
        rows.append(dict(uuid=row['uuid'], at_nm=list(at), native_kind=row['native_kind'],
            source_layer=source_face, target_layer=target_face,
            finite_new_incident_copper_verified=True, new_barrel=False,
            barrel_capacity_qualified=False, release_authority=False))
    return rows
