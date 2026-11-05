"""Source-native endpoint dependencies of explicitly moving through barrels.

This is construction geometry, not a motion, cut, current or release permit.
An in-pad via transported on its owning face also owns exact source track
endpoints on OTHER faces. Treating only the pad's SMD face leaves the original
back-side lead behind. All actual same-net barrel contacts must agree; an
unmoved barrel or stationary pad is not silently dragged with the selected one.
"""
import math,time
import pcbnew
import cec_force_current as force


def plan(board,requests,*,timeout_s=10.):
    if (type(requests) is not list or len(requests)>32 or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=10):
        raise ValueError('bounded_explicit_native_barrel_endpoint_motion_required')
    deadline=time.monotonic()+timeout_s
    tracks=list(board.GetTracks());vias=[v for v in tracks if v.GetClass()=='PCB_VIA']
    live={force._uid(v):v for v in vias};offsets={}
    if len(tracks)>8192 or len(vias)>2048:raise ValueError('bounded_source_barrel_endpoint_inventory_required')
    for q in requests:
        if (type(q) is not dict or set(q)!={'uuid','offset_nm'} or type(q['uuid']) is not str
                or q['uuid'] not in live or q['uuid'] in offsets or type(q['offset_nm']) is not list
                or len(q['offset_nm'])!=2 or any(type(n) is not int for n in q['offset_nm'])
                or not 0<math.hypot(*q['offset_nm'])<=16000000):
            raise ValueError('exact_source_through_barrel_offset_required')
        v=live[q['uuid']]
        if (v.GetNetCode()<=0 or v.GetViaType()!=pcbnew.VIATYPE_THROUGH
                or v.TopLayer()!=pcbnew.F_Cu or v.BottomLayer()!=pcbnew.B_Cu
                or not 0<v.GetDrillValue()<v.GetWidth(v.TopLayer())):
            raise ValueError('known_positive_source_through_barrel_required')
        offsets[q['uuid']]=tuple(q['offset_nm'])
    bynet={}
    for v in vias:bynet.setdefault(v.GetNetCode(),[]).append(v)
    rows=[];nodes={}
    for track in tracks:
        if time.monotonic()>=deadline:raise ValueError('native_moving_barrel_endpoint_deadline')
        if track.GetClass()!='PCB_TRACK':continue
        face=int(track.GetLayer());net=track.GetNetCode()
        for end,at in enumerate((track.GetStart(),track.GetEnd())):
            point=pcbnew.SHAPE_CIRCLE(at,0)
            contacts=[v for v in bynet.get(net,()) if v.IsOnLayer(face)
                and v.GetEffectiveShape(face).Collide(point,0)]
            if not any(force._uid(v) in offsets for v in contacts):continue
            choices={offsets.get(force._uid(v),(0,0)) for v in contacts}
            if len(choices)!=1:raise ValueError('moving_and_stationary_native_barrel_endpoint_conflict')
            offset=next(iter(choices));key=(int(net),face,tuple(at))
            if key in nodes and nodes[key]!=offset:raise ValueError('native_barrel_endpoint_offset_conflict')
            nodes[key]=offset
            rows.append(dict(track_uuid=force._uid(track),endpoint=end,net=track.GetNetname(),net_code=int(net),
                layer=face,source_nm=list(at),offset_nm=list(offset),
                candidate_nm=[a+d for a,d in zip(at,offset)],
                actual_source_barrel_uuids=sorted(force._uid(v) for v in contacts)))
            if len(rows)>256:raise ValueError('bounded_source_moving_barrel_endpoint_dependencies_required')
    return dict(rows=rows,source_geometry_unchanged=True,motion_or_retirement_authority=False,
        exact_native_source_endpoint_contacts_used=True,saved_source_partition_receiving_required=True,
        current_qualified=False,release_authority=False)
