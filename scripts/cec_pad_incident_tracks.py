"""Exact surface-pad contact inventory for local placement transactions.

A routed endpoint need not equal the pad centre. Use native copper containment
at zero margin, with net and layer identity, to name incident boundaries. This
does not grant permission to delete or move any copper; locks/groups remain a
separate ownership decision. Interior, contained and shared contacts retain
the entire trace as a native reconnection boundary instead of claiming it.
"""
from collections import defaultdict

import pcbnew
import cec_fr as fr


def inspect(board, pads, *, internal_uuids=()):
    pads = tuple(pads)
    internal = set(internal_uuids)
    by_net_layer = defaultdict(list)
    for item in board.GetTracks():
        if item.GetClass() == 'PCB_TRACK' and item.GetNetCode() > 0:
            by_net_layer[(int(item.GetNetCode()), int(item.GetLayer()))].append(item)
    rows, owners, faults, barrels = [], defaultdict(set), [], []
    # A diagnostic must not normalize live net assignments through an
    # inherited short. Use a private native graph of the authored material.
    graph = fr._read_only_route_connectivity(board,{p.GetNetCode() for p in pads if p.GetNetCode()>0})
    vias=[item for item in board.GetTracks() if item.GetClass()=='PCB_VIA'
        and item.GetNetCode()>0 and item.m_Uuid.AsString() not in internal]
    native_members = {}
    pad_by_id = {pad.m_Uuid.AsString(): pad for pad in pads}

    def natively_connected(pad, track_id):
        uid = pad.m_Uuid.AsString()
        if uid not in native_members:
            native_members[uid] = {item.m_Uuid.AsString()
                for item in graph.GetConnectedItems(pad)}
        return track_id in native_members[uid]

    for pad in pads:
        if pad.GetNetCode() <= 0 or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
            continue
        uid = pad.m_Uuid.AsString()
        for layer in pad.GetLayerSet().CuStack():
            shape = pad.GetEffectiveShape(layer)
            for via in vias:
                if (via.GetNetCode()!=pad.GetNetCode() or not via.IsOnLayer(layer)
                        or not shape.Collide(via.GetEffectiveShape(layer),0)):continue
                vid=via.m_Uuid.AsString()
                if not natively_connected(pad,vid):
                    faults.append(dict(uuid=vid,pad_uuid=uid,reason='direct_barrel_contact_not_native'))
                    continue
                barrels.append(dict(ref=pad.GetParentFootprint().GetReference(),pad=str(pad.GetNumber()),
                    pad_uuid=uid,net=pad.GetNetname(),via_uuid=vid,contact_nm=list(via.GetPosition()),
                    layer=int(layer),layers=list(map(int,via.GetLayerSet().CuStack())),
                    fixed_boundary=True,contact_kind='native_direct_barrel_boundary'))
            for track in by_net_layer[(int(pad.GetNetCode()), int(layer))]:
                tid = track.m_Uuid.AsString()
                if tid in internal:
                    continue
                ends = (track.GetStart(), track.GetEnd())
                contacts = [i for i, at in enumerate(ends) if shape.Collide(at, 0)]
                if not contacts:
                    # No authority to split/remove a trunk at an interior tap.
                    # Keep it byte-exact and name a real, live endpoint as a
                    # restoration obligation. Native connectivity must agree;
                    # this is not a proximity-based copper ownership claim.
                    if shape.Collide(track.GetEffectiveShape(layer), 0):
                        if not natively_connected(pad, tid):
                            faults.append(dict(uuid=tid,pad_uuid=uid,reason='midsegment_contact_not_native'))
                            continue
                        center=pad.GetCenter()
                        at=min(ends,key=lambda p:((p.x-center.x)**2+(p.y-center.y)**2,p.x,p.y))
                        rows.append(dict(ref=pad.GetParentFootprint().GetReference(),pad=str(pad.GetNumber()),
                            pad_uuid=uid,net=pad.GetNetname(),track_uuid=tid,contact_nm=list(at),far_nm=list(at),
                            pad_center_nm=list(center),layer=int(layer),fixed_boundary=True,
                            contact_kind='native_midsegment_boundary'))
                    continue
                if len(contacts) != 1:
                    # Both endpoints lie within a land: ownership of a stub
                    # cannot be proved, but retaining it requires no ownership
                    # transfer. Anchor to one real native endpoint and leave
                    # the WHOLE original trace byte-exact. A later independent
                    # proof must still establish restoration of its component.
                    if not natively_connected(pad, tid):
                        faults.append(dict(uuid=tid, pad_uuid=uid,
                                           reason='contained_pad_contact_not_native'))
                        continue
                    center = pad.GetCenter()
                    at = min(ends, key=lambda p: ((p.x-center.x)**2+(p.y-center.y)**2, p.x, p.y))
                    owners[tid].add(uid)
                    rows.append(dict(ref=pad.GetParentFootprint().GetReference(), pad=str(pad.GetNumber()),
                        pad_uuid=uid, net=pad.GetNetname(), track_uuid=tid, contact_nm=list(at), far_nm=list(at),
                        pad_center_nm=list(center), layer=int(layer), fixed_boundary=True,
                        contact_kind='native_contained_trace_boundary'))
                    continue
                owners[tid].add(uid)
                index = contacts[0]
                rows.append(dict(ref=pad.GetParentFootprint().GetReference(),
                    pad=str(pad.GetNumber()), pad_uuid=uid, net=pad.GetNetname(),
                    track_uuid=tid, contact_nm=list(ends[index]), far_nm=list(ends[1-index]),
                    pad_center_nm=list(pad.GetCenter()), layer=int(layer)))
    for uid, pad_ids in owners.items():
        if len(pad_ids) != 1:
            # A shared trace is not a uniquely owned removable branch. Keep
            # every native pad contact as a separate restoration obligation;
            # even producer receipts must not make this trace movable.
            for row in rows:
                if row['track_uuid'] != uid:
                    continue
                if not natively_connected(pad_by_id[row['pad_uuid']], uid):
                    faults.append(dict(uuid=uid, pad_uuid=row['pad_uuid'],
                                       reason='shared_pad_contact_not_native'))
                    continue
                row.update(fixed_boundary=True, contact_kind='native_shared_trace_boundary')
                row['far_nm'] = list(row['contact_nm'])
    return dict(ok=not faults, contacts=sorted(rows,key=lambda r:(r['ref'],r['pad'],r['track_uuid'])),
                native_barrel_contacts=sorted(barrels,key=lambda r:(r['ref'],r['pad'],r['via_uuid'],r['layer'])),
                faults=faults, contact_tolerance_nm=0, release_authority=False)
