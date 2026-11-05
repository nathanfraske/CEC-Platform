"""Read-only exact on-stroke supply-tail proposals at real retained joins.

Only integral native centreline intersections of full-width retained source
tracks can anchor a trim. This module never mutates, infers branch sharing,
supplies a current budget or admits a cut. The supply-loop receiver must
independently re-prove the real source contract, terminal joins and saved cut.
"""
import math
import time
import pcbnew
import cec_force_current as force


def _cross(a,b):return a[0]*b[1]-a[1]*b[0]


def intersections(a,b,c,d):
    """Native-integer segments; no rounded intersection becomes a contact."""
    r=(b[0]-a[0],b[1]-a[1]);s=(d[0]-c[0],d[1]-c[1]);q=(c[0]-a[0],c[1]-a[1])
    den=_cross(r,s)
    if den:
        t=_cross(q,s);u=_cross(q,r)
        if den<0:den,t,u=-den,-t,-u
        if not 0<t<den or not 0<=u<=den:return []
        nums=(a[0]*den+r[0]*t,a[1]*den+r[1]*t)
        return [(nums[0]//den,nums[1]//den)] if all(n%den==0 for n in nums) else []
    if _cross(q,r):return []
    length2=r[0]*r[0]+r[1]*r[1]
    return sorted({p for p in (c,d) if p not in (a,b)
        and 0<(p[0]-a[0])*r[0]+(p[1]-a[1])*r[1]<length2})


def propose(board,track_uuid,*,required_width_by_layer_nm,retired_track_uuids=(),
            maximum_candidates=8,timeout_s=10.):
    if (type(track_uuid) is not str or not track_uuid
            or type(required_width_by_layer_nm) is not dict or not required_width_by_layer_nm
            or any(type(k) is not int or type(v) is not int or not 0<v<=1000000
                   for k,v in required_width_by_layer_nm.items())
            or type(retired_track_uuids) not in (list,tuple,set) or len(retired_track_uuids)>32
            or len(set(retired_track_uuids))!=len(retired_track_uuids)
            or type(maximum_candidates) is not int or not 1<=maximum_candidates<=8
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('bounded_explicit_native_supply_trim_inventory_required')
    tracks=list(board.GetTracks());live={force._uid(t):t for t in tracks}
    if len(live)!=len(tracks) or len(tracks)>8192:raise ValueError('native_supply_trim_inventory_bound')
    target=live.get(track_uuid);retired=set(retired_track_uuids)
    if not retired<=live.keys() or track_uuid in retired:
        raise ValueError('native_supply_trim_retained_target_required')
    if (target is None or target.GetClass()!='PCB_TRACK'
            or target.GetLayer() not in required_width_by_layer_nm
            or not required_width_by_layer_nm[target.GetLayer()]<=target.GetWidth()<=1000000
            or target.GetParentGroup() is not None or not 0<target.GetLength()<=32000000):
        raise ValueError('native_supply_trim_full_width_source_track_required')
    a,b=tuple(target.GetStart()),tuple(target.GetEnd());rows=[];seen=set();deadline=time.monotonic()+timeout_s
    for t in sorted(tracks,key=force._uid):
        if time.monotonic()>=deadline:raise ValueError('native_supply_trim_proposal_deadline')
        uid=force._uid(t)
        if (uid==track_uuid or uid in retired or t.GetClass()!='PCB_TRACK'
                or t.GetLayer()!=target.GetLayer() or t.GetNetCode()!=target.GetNetCode()
                or t.GetWidth()<required_width_by_layer_nm[target.GetLayer()]):continue
        for point in intersections(a,b,tuple(t.GetStart()),tuple(t.GetEnd())):
            for start,end in ((a,point),(point,b)):
                key=(start,end)
                if key in seen:continue
                seen.add(key);rows.append(dict(request=dict(uuid=track_uuid,start_nm=list(start),end_nm=list(end),
                    locked_source_requested=bool(target.IsLocked())),source_anchor_track_uuid=uid,
                    literal_native_intersection_nm=list(point),
                    predicted_removed_length_nm=target.GetLength()-math.dist(start,end)))
    rows.sort(key=lambda r:(-r['predicted_removed_length_nm'],r['source_anchor_track_uuid'],r['request']['start_nm']))
    return dict(schema=1,source_track_uuid=track_uuid,proposals=rows[:maximum_candidates],
        complete=len(rows)<=maximum_candidates,source_board_mutated=False,
        independently_received_whole_source_cut_still_required=True,
        mutation_or_receiving_authority=False,current_qualified=False,release_authority=False)
