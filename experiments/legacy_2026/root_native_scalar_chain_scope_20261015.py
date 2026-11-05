"""Read-only ordinary chain proposals, never permission to cut source copper."""
import math
from collections import defaultdict
import pcbnew
import cec_force_current as force
import cec_native_ordinary_chain_scope as typed


def request_variants(board,issues,eligible,*,max_extra_tracks=0):
    if type(max_extra_tracks) is not int or not 0<=max_extra_tracks<=4:
        raise ValueError('bounded_scalar_chain_extension_required')
    all_tracks=list(board.GetTracks());pads=[p for f in board.GetFootprints() for p in f.Pads()]
    if len(all_tracks)>8192 or len(pads)>16384:raise ValueError('bounded_native_chain_inventory_required')
    tracks={force._uid(t):t for t in all_tracks if t.GetClass()=='PCB_TRACK'}
    if len(tracks)!=sum(t.GetClass()=='PCB_TRACK' for t in all_tracks):
        raise ValueError('unique_native_scalar_track_inventory_required')
    point=lambda v:(int(v.x),int(v.y));rows=[];at=defaultdict(list)
    for uid,t in tracks.items():
        row=dict(uuid=uid,kind=t.GetClass(),net=str(t.GetNetname()),layer=int(t.GetLayer()),
            width_nm=t.GetWidth(),grouped=t.GetParentGroup() is not None,locked=bool(t.IsLocked()),
            start_nm=list(point(t.GetStart())),end_nm=list(point(t.GetEnd())))
        rows.append(row)
        for p in (point(t.GetStart()),point(t.GetEnd())):at[(row['net'],row['layer'],p)].append(uid)
    lookup={r['uuid']:r for r in rows};anchors={}
    def anchored(net,layer,p):
        key=(net,layer,p)
        if key in anchors:return anchors[key]
        probe=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*p),2)
        for item in [*pads,*(t for t in all_tracks if t.GetClass()=='PCB_VIA')]:
            if item.IsOnLayer(layer) and item.GetEffectiveShape(layer).Collide(probe,0):
                anchors[key]=True;return True
        incident=set(at[key])
        for uid,t in tracks.items():
            if uid in incident or int(t.GetLayer())!=layer or str(t.GetNetname())!=net:continue
            if t.GetEffectiveShape(layer).Collide(probe,0):
                anchors[key]=True;return True
        anchors[key]=False;return False
    result=[];seen=set()
    for issue in issues:
        ids=set(issue['track_uuids']);net=issue['net']
        if issue['type']!='acute_backtrack' or net not in eligible or len(ids)!=2 or not ids<=tracks.keys():continue
        seed=[lookup[u] for u in sorted(ids)]
        if (any(r['grouped'] or not 0<r['width_nm']<=350000 for r in seed)
                or len({(r['layer'],r['width_nm']) for r in seed})!=1):continue
        try:base=typed.chain(rows,sorted(ids),eligible,allow_locked_track_uuids=[r['uuid'] for r in seed if r['locked']])
        except ValueError:continue
        layer=base['source_layer'];width=base['source_width_nm'];ends=[tuple(p) for p in base['endpoints_nm']]
        walks=[]
        for start in ends:
            choices=[([],start)];used=set(ids);p=start
            for _ in range(max_extra_tracks):
                if anchored(net,layer,p):break
                incident=at[(net,layer,p)]
                if len(incident)!=2:break
                next_ids=set(incident)-used
                if len(next_ids)!=1:break
                uid=next(iter(next_ids));r=lookup[uid]
                if r['grouped'] or r['width_nm']!=width:break
                a,b=tuple(r['start_nm']),tuple(r['end_nm']);end=b if a==p else a
                used.add(uid);p=end;choices.append((choices[-1][0]+[uid],p))
            walks.append(choices)
        proposals=[]
        for left in walks[0]:
            for right in walks[1]:
                extra=left[0]+right[0]
                if len(extra)>max_extra_tracks or len(set(extra))!=len(extra):continue
                scope=ids|set(extra)
                if scope&set(extra)&ids:continue
                if frozenset(scope) in seen:continue
                locks=[u for u in sorted(scope) if lookup[u]['locked']]
                try:proof=typed.chain(rows,sorted(scope),eligible,allow_locked_track_uuids=locks)
                except ValueError:continue
                a,b=map(tuple,proof['endpoints_nm']);length=sum(math.dist(lookup[u]['start_nm'],lookup[u]['end_nm']) for u in scope)
                dx,dy=abs(b[0]-a[0]),abs(b[1]-a[1]);short=max(dx,dy)+(math.sqrt(2)-1)*min(dx,dy)
                if length-short<1000:continue
                proposals.append(dict(net=net,source_track_uuids=sorted(scope),typed_chain=proof,
                    endpoint_a_nm=list(a),endpoint_b_nm=list(b),old_length_nm=length,
                    predicted_maximum_length_saved_nm=length-short))
        for row in sorted(proposals,key=lambda r:(-r['predicted_maximum_length_saved_nm'],len(r['source_track_uuids']),r['source_track_uuids'])):
            key=frozenset(row['source_track_uuids'])
            if key not in seen:seen.add(key);result.append(row)
    return result
