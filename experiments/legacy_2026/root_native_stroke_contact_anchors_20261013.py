"""Conservative native contact constraints for UNSAVED stroke motion only.

No native connectivity/current/admission credit. A body contact is frozen or
rigidly transported, never approximated by unrelated endpoint coordinates.
The caller still independently receives every actual saved source transform.
"""
import math,time
import pcbnew
import cec_force_current as force
import cec_fr as fr


def plan(board,node_ids,stationary_pad_uuids,moving_pad_uuids,*,timeout_s=10.):
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
        raise ValueError('bounded_native_stroke_contact_lease_required')
    deadline=time.monotonic()+timeout_s
    if (type(node_ids) is not dict or not 2<=len(node_ids)<=8192
            or set(node_ids.values())!=set(range(len(node_ids)))):
        raise ValueError('literal_bounded_source_stroke_nodes_required')
    tracks={force._uid(t):t for t in board.GetTracks()}
    pads={force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}
    stationary,moving=map(set,(stationary_pad_uuids,moving_pad_uuids))
    if (stationary&moving or not stationary|moving<=pads.keys() or len(tracks)>4096 or len(pads)>8192):
        raise ValueError('disjoint_literal_source_pad_contact_inventory_required')
    graph=fr._read_only_route_connectivity(board)
    fixed=set();required=set();links=set();witnesses=[];seen=set()
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_stroke_contact_deadline')
    def endpoints(item,layer):
        pts=([tuple(item.GetStart()),tuple(item.GetEnd())] if item.GetClass()=='PCB_TRACK'
            else [tuple(item.GetPosition())])
        keys=[(int(item.GetNetCode()),int(layer),at) for at in pts]
        if any(k not in node_ids for k in keys):raise ValueError('source_native_contact_nodes_missing')
        return [node_ids[k] for k in keys],pts
    for uid,item in tracks.items():
        tick()
        if item.GetClass() not in ('PCB_TRACK','PCB_VIA'):continue
        faces=([item.GetLayer()] if item.GetClass()=='PCB_TRACK' else
            [l for l in board.GetEnabledLayers().CuStack() if item.IsOnLayer(l)])
        for layer in faces:
            ids,pts=endpoints(item,layer);shape=item.GetEffectiveShape(layer)
            for pad_uid in stationary|moving:
                tick();pad=pads[pad_uid]
                if (pad.GetNetCode()!=item.GetNetCode() or not pad.IsOnLayer(layer)
                        or not shape.Collide(pad.GetEffectiveShape(layer),0)):continue
                (fixed if pad_uid in stationary else required).update(ids)
                witnesses.append(dict(conductor_uuid=uid,pad_uuid=pad_uid,layer=int(layer),
                    node_indices=ids,kind='conservative_native_pad_body_motion_anchor'))
            for neighbor in graph.GetConnectedItems(item):
                tick();peer_uid=force._uid(neighbor)
                other=tracks.get(peer_uid)
                if (other is None or other==item or not other.IsOnLayer(layer)
                        or other.GetNetCode()!=item.GetNetCode()):continue
                pair=tuple(sorted((uid,peer_uid)))+(int(layer),)
                if pair in seen:continue
                seen.add(pair)
                if other.GetClass() not in ('PCB_TRACK','PCB_VIA'):
                    raise ValueError('curved_source_contact_requires_separate_motion_owner')
                if not shape.Collide(other.GetEffectiveShape(layer),0):continue
                other_ids,other_pts=endpoints(other,layer)
                if set(pts)&set(other_pts):continue
                combined=sorted(set(ids+other_ids))
                links.update((combined[0],i) for i in combined[1:])
                witnesses.append(dict(conductor_uuids=pair[:2],layer=int(layer),node_indices=combined,
                    kind='conservative_native_interior_body_rigid_link'))
                if len(links)>8192 or len(witnesses)>32768:
                    raise ValueError('bounded_native_stroke_contact_inventory_exceeded')
    return dict(fixed_nodes=sorted(fixed),required_nodes=sorted(required),rigid_links=sorted(links),
        witnesses=witnesses,contacts_preserved=False,construction_exclusions_only=True,
        current_qualified=False,routing_admitted=False,release_authority=False)
