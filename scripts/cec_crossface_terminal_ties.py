"""Discover exact duplicated ties between real plated terminal centres.

This read-only bounded prescreen grants no cut, current, barrel, clearance or
release authority. Every proposed deletion must still pass native surviving
partitions, unchanged trace/rated-current graphs and exact saved cut replay.
In particular, same pin numbers or schematic equivalence never witness a tie.
"""
import time
import pcbnew


def discover(board, seed_track_uuids, *, max_tracks=8, timeout_s=10.):
    """Expand a source-owned seed only across exact, directly duplicated ties.

    Every endpoint is the actual centre of a nonzero-drill PTH land which
    flashes on BOTH real enabled faces. The keeper is an unchanged native
    straight track with identical endpoints and no narrower copper. No via,
    inferred same-pin bridge, zone bbox or interpolated contact is credited.
    """
    if (type(seed_track_uuids) not in (list,tuple) or not seed_track_uuids
            or type(max_tracks) is not int or not 1<=max_tracks<=16
            or len(seed_track_uuids)>max_tracks
            or any(type(u) is not str or not u for u in seed_track_uuids)
            or len(set(seed_track_uuids))!=len(seed_track_uuids)
            or type(timeout_s) not in (int,float) or not 0<timeout_s<=10):
        raise ValueError('bounded_exact_terminal_tie_discovery_required')
    deadline=time.monotonic()+timeout_s
    uid=lambda item:item.m_Uuid.AsString()
    tracks={uid(t):t for t in board.GetTracks()}
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    enabled=set(map(int,board.GetEnabledLayers().CuStack()))
    if (len(tracks)>16384 or len(pads)>16384 or len(tracks)!=len(list(board.GetTracks()))
            or not set(seed_track_uuids)<=tracks.keys()):
        raise ValueError('bounded_actual_terminal_tie_source_inventory_required')
    selected=[tracks[u] for u in seed_track_uuids]
    if (any(t.GetClass()!='PCB_TRACK' or t.GetParentGroup() is not None for t in selected)
            or len({(t.GetNetname(),int(t.GetLayer())) for t in selected})!=1):
        raise ValueError('one_ungrouped_source_net_and_face_tie_seed_required')
    net=str(selected[0].GetNetname());face=int(selected[0].GetLayer())
    if not net or face not in enabled or net.rsplit('/',1)[-1].upper() in ('GND','AGND','PGND','DGND'):
        raise ValueError('actual_non_ground_terminal_tie_seed_required')
    def endpoints(t):return tuple(sorted((tuple(t.GetStart()),tuple(t.GetEnd()))))
    keepers={}
    for t in tracks.values():
        if time.monotonic()>=deadline:raise ValueError('terminal_tie_discovery_deadline')
        if (t.GetClass()=='PCB_TRACK' and t.GetNetname()==net and int(t.GetLayer()) in enabled
                and int(t.GetLayer())!=face and t.GetWidth()>0 and t.GetStart()!=t.GetEnd()):
            keepers.setdefault(endpoints(t),[]).append(t)
    centres={}
    for pad in pads:
        if (pad.GetNetname()==net and pad.GetAttribute()==pcbnew.PAD_ATTRIB_PTH
                and pad.HasHole() and min(pad.GetDrillSize())>0):
            centres.setdefault(tuple(pad.GetPosition()),[]).append(pad)
    candidates={}
    for t in tracks.values():
        if time.monotonic()>=deadline:raise ValueError('terminal_tie_discovery_deadline')
        if (t.GetClass()!='PCB_TRACK' or t.GetNetname()!=net or int(t.GetLayer())!=face
                or t.GetParentGroup() is not None or t.GetWidth()<=0 or t.GetStart()==t.GetEnd()):continue
        points=endpoints(t);matches=[]
        for other in keepers.get(points,[]):
            if other.GetWidth()<t.GetWidth():continue
            witnesses=[]
            for point in points:
                actual=[p for p in centres.get(point,[]) if p.IsOnLayer(face) and p.FlashLayer(face)
                        and p.IsOnLayer(other.GetLayer()) and p.FlashLayer(other.GetLayer())]
                if not actual:break
                witnesses.append(sorted(uid(p) for p in actual))
            if len(witnesses)==2:matches.append(dict(keeper_uuid=uid(other),keeper_layer_id=int(other.GetLayer()),
                keeper_width_nm=int(other.GetWidth()),endpoint_pad_uuids=witnesses))
        if matches:candidates[uid(t)]=dict(uuid=uid(t),net=net,layer_id=face,width_nm=int(t.GetWidth()),
            start_nm=list(t.GetStart()),end_nm=list(t.GetEnd()),source_locked=bool(t.IsLocked()),
            unchanged_native_keeper_witnesses=sorted(matches,key=lambda row:row['keeper_uuid']))
    if not set(seed_track_uuids)<=candidates.keys():
        raise ValueError('every_seed_requires_exact_crossface_plated_terminal_witnesses')
    chosen=set(seed_track_uuids);points=set().union(*(set(endpoints(tracks[u])) for u in chosen))
    while True:
        more={u for u in candidates if u not in chosen and points&set(endpoints(tracks[u]))}
        if not more:break
        if len(chosen|more)>max_tracks:raise ValueError('whole_connected_terminal_tie_exceeds_discovery_bound')
        chosen|=more;points=set().union(*(set(endpoints(tracks[u])) for u in chosen))
    return dict(schema=1,seed_track_uuids=sorted(seed_track_uuids),net=net,source_layer_id=face,
        track_uuids=sorted(chosen),witnesses=[candidates[u] for u in sorted(chosen)],
        exact_actual_plated_centres_not_logical_pin_equivalence=True,
        read_only_discovery_not_redundancy_or_current_proof=True,
        saved_native_partitions_rated_paths_and_cut_replay_required=True,
        cut_authority=False,current_qualified=False,barrel_ampacity_qualified=False,release_authority=False)
