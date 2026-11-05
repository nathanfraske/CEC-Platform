"""Trim a received branch's charged source spur at its actual new tap.

Changing a retained-component tap can leave an electrically connected but
geometrically dangling old tail. This bounded constructor only trims exact
small full-load-rated SOURCE edges; it never authorizes main-force rip-up,
placement, current sharing or publication. A final independent rated-branch,
native DRC, current, field and Kelvin replay remains mandatory.
"""
import math
from pathlib import Path
import time

import pcbnew
import cec_force_current as force
import cec_rated_branch_repair as rated
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items


def plan(source,trial,*,board_hint,retired_track_uuids,dangling_track_uuids,
         max_source_track_mm=8.,max_retired_tracks=8,max_replacement_width_mm=.35,
         max_source_width_mm=.35,timeout_s=10.):
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10:
        raise ValueError('bounded_rated_spur_rebuild_required')
    deadline=time.monotonic()+timeout_s
    dangling=ordinary._ids(dangling_track_uuids,'rated_source_spurs',4)
    if not dangling:raise ValueError('positive_native_source_spur_required')
    source,trial=map(lambda p:Path(p).resolve(),(source,trial))
    epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,trial)]
    initial=rated.receive(source,trial,board_hint=board_hint,retired_track_uuids=retired_track_uuids,
        allow_rated_layer_bridges=True,max_source_track_mm=max_source_track_mm,
        max_retired_tracks=max_retired_tracks,max_replacement_width_mm=max_replacement_width_mm,
        max_source_width_mm=max_source_width_mm,
        timeout_s=timeout_s)
    if not initial['ok'] or not initial['complete']:
        raise ValueError('independently_received_initial_rated_branch_required')
    parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,trial)]
    original={force._uid(t):t for t in parent.GetTracks()}
    live={force._uid(t):t for t in child.GetTracks()}
    contracts=initial['source_proposal']['contracts']
    added=set(initial['added_native_uuids'])
    taps=[t for t in child.GetTracks() if force._uid(t) in added and t.GetClass()=='PCB_VIA']
    if not 1<=len(taps)<=4:raise ValueError('actual_received_new_barrel_tap_required')
    retired=set(initial['retired_track_uuids']);extra=[];prefixes=[]
    other=[*(p for f in child.GetFootprints() for p in f.Pads()),
           *[z for z in child.Zones() if not z.GetIsRuleArea()]]
    def touching(item,at,layer,code):
        if item.GetNetCode()!=code or not item.IsOnLayer(layer):return False
        if item.GetClass()=='ZONE':
            if not item.IsFilled() or not item.HasFilledPolysForLayer(layer):
                raise ValueError('rated_spur_native_fill_unknown')
            return item.GetFilledPolysList(layer).Collide(pcbnew.SHAPE_SEGMENT(at,at,1),0)
        return item.GetEffectiveShape(layer).Collide(at,0)
    def contacts(at,layer,code,skip):
        return [t for u,t in live.items() if u not in skip and touching(t,at,layer,code)]\
            +[p for p in other if touching(p,at,layer,code)]
    def clear_peeled_contacts(at,end,width,layer,code,walk):
        removed_shape=pcbnew.SHAPE_SEGMENT(at,end,width)
        for item in [*other,*live.values()]:
            if time.monotonic()>=deadline:raise ValueError('rated_spur_walk_deadline')
            iid=force._uid(item)
            if (iid in walk or iid in added or item.GetNetCode()!=code
                    or not item.IsOnLayer(layer)):continue
            if item.GetClass()=='ZONE':
                if not item.IsFilled() or not item.HasFilledPolysForLayer(layer):
                    raise ValueError('rated_spur_native_fill_unknown')
                shape=item.GetFilledPolysList(layer)
            else:shape=item.GetEffectiveShape(layer)
            if not shape.Collide(removed_shape,0) or touching(item,end,layer,code):continue
            raise ValueError('rated_spur_peel_has_retained_native_contact')
    for seed in sorted(dangling):
        edge=live.get(seed)
        if (edge is None or seed not in original or edge.GetClass()!='PCB_TRACK'
                or edge.GetNetname() not in contracts or seed in retired):
            raise ValueError('dangling_item_not_retained_rated_source_track')
        layer=edge.GetLayer();code=edge.GetNetCode()
        loose=[at for at in (edge.GetStart(),edge.GetEnd()) if not contacts(at,layer,code,{seed})]
        if len(loose)!=1:raise ValueError('exactly_one_native_free_source_end_required')
        at=loose[0];walk=set()
        while True:
            if time.monotonic()>=deadline:raise ValueError('rated_spur_walk_deadline')
            uid=force._uid(edge)
            if uid in walk or uid in retired:raise ValueError('rated_spur_revisit_or_overlap')
            # Retype every extra cut from the immutable parent, not from the
            # worker's designation of an old conductor as "unimportant".
            rated.plan(parent,source,board_hint=board_hint,retired_track_uuids=[uid],
                max_source_track_mm=max_source_track_mm,max_retired_tracks=max_retired_tracks,
                max_source_width_mm=max_source_width_mm,
                timeout_s=max(.001,deadline-time.monotonic()))
            walk.add(uid)
            if len(retired|walk)>max_retired_tracks:raise ValueError('rated_spur_total_source_work_bound')
            far=edge.GetEnd() if at==edge.GetStart() else edge.GetStart()
            dx,dy=far.x-at.x,far.y-at.y;length2=dx*dx+dy*dy
            hits=[]
            for tap in taps:
                if tap.GetNetCode()!=code or not tap.IsOnLayer(layer):continue
                pt=tap.GetPosition();ux,uy=pt.x-at.x,pt.y-at.y
                dot=ux*dx+uy*dy
                if ux*dy==uy*dx and 0<dot<=length2:hits.append((dot,tap))
            if hits:
                _,tap=min(hits,key=lambda q:(q[0],force._uid(q[1])))
                tap_at=tap.GetPosition()
                # A land, old barrel or tee on the peeled portion is not an
                # unused tail. Final partition receiving is independent too.
                clear_peeled_contacts(at,tap_at,edge.GetWidth(),layer,code,walk)
                if tap_at!=far:
                    prefixes.append(dict(net=edge.GetNetname(),layer_id=layer,
                        width_nm=edge.GetWidth(),start_nm=list(far),end_nm=list(tap_at),
                        original_track_uuid=uid,actual_new_tap_uuid=force._uid(tap)))
                break
            clear_peeled_contacts(at,far,edge.GetWidth(),layer,code,walk)
            neighbours=contacts(far,layer,code,walk)
            if len(neighbours)!=1 or neighbours[0].GetClass()!='PCB_TRACK':
                raise ValueError('source_spur_stops_at_native_barrel_land_or_tee')
            next_edge=neighbours[0]
            if tuple(far) not in (tuple(next_edge.GetStart()),tuple(next_edge.GetEnd())):
                raise ValueError('source_spur_continuation_not_exact_degree_two_endpoint')
            at=far;edge=next_edge
        retired.update(walk);extra.extend(sorted(walk))
    whole=rated.plan(parent,source,board_hint=board_hint,retired_track_uuids=sorted(retired),
        max_source_track_mm=max_source_track_mm,max_retired_tracks=max_retired_tracks,
        max_source_width_mm=max_source_width_mm,
        timeout_s=max(.001,deadline-time.monotonic()))
    if families!=[force._family(p,board_hint) for p in (source,trial)] or epoch!=force._code_identity():
        raise ValueError('rated_spur_source_trial_or_code_changed')
    return dict(schema=1,source=str(source),source_sha256=force._hash(source),
        trial=str(trial),trial_sha256=force._hash(trial),
        additional_retired_track_uuids=sorted(extra),retired_track_uuids=sorted(retired),
        retained_prefixes=prefixes,whole_original_source_plan=whole,
        source_current_reduced=False,new_vias=0,release_authority=False,receiving_required=True)


def materialize(board,proposal):
    """Private construction only; never an independently received result."""
    live={force._uid(t):t for t in board.GetTracks()}
    ids=set(proposal['additional_retired_track_uuids'])
    if not ids or not ids<=live.keys():raise ValueError('exact_source_spur_material_required')
    discard_items(board,[live[u] for u in sorted(ids)])
    added=[]
    for row in proposal['retained_prefixes']:
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I(*row['start_nm']))
        t.SetEnd(pcbnew.VECTOR2I(*row['end_nm']));t.SetWidth(row['width_nm']);t.SetLayer(row['layer_id'])
        t.SetNetCode(board.GetNetcodeFromNetname(row['net']));t.SetLocked(True);board.Add(t)
        added.append(force._uid(t))
    return dict(added_track_uuids=added,retired_track_uuids=sorted(ids),
        routing_admitted=False,release_authority=False)
