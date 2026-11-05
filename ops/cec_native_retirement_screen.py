"""Bounded native cut ranking; never ownership, current or admission proof."""
import math,time
import pcbnew
import cec_force_current as force


def screen(board,track_uuids,*,timeout_s=.25,max_items=2048):
    r=dict(state='unknown',complete=False,source_mutated=False,admission_or_deletion_authority=False)
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=2
            or type(max_items) is not int or not 1<=max_items<=4096
            or type(track_uuids) not in (list,tuple,set) or not 1<=len(track_uuids)<=8
            or any(type(u) is not str or not u for u in track_uuids)
            or len(set(track_uuids))!=len(track_uuids)):
        raise ValueError('bounded_literal_native_retirement_screen_required')
    deadline=time.monotonic()+timeout_s;cut=set(track_uuids)
    try:
        tracks={force._uid(t):t for t in board.GetTracks()}
        if not cut<=tracks.keys() or any(tracks[u].GetClass()!='PCB_TRACK' for u in cut):
            raise ValueError('actual_plain_source_tracks_required')
        codes={tracks[u].GetNetCode() for u in cut}
        if len(codes)!=1 or next(iter(codes))<=0:raise ValueError('one_actual_source_net_required')
        code=next(iter(codes));items=[p for f in board.GetFootprints() for p in f.Pads() if p.GetNetCode()==code]
        items += [t for t in tracks.values() if t.GetNetCode()==code]
        items += [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetCode()==code]
        if len(items)>max_items or any(z.GetClass()=='ZONE' and not z.IsFilled() for z in items):
            raise ValueError('complete_bounded_native_net_inventory_required')
        if len({force._uid(i) for i in items})!=len(items):raise ValueError('unique_native_source_items_required')
        def partition(omitted):
            conn=pcbnew.CONNECTIVITY_DATA();remaining={force._uid(i):i for i in items if force._uid(i) not in omitted}
            for item in remaining.values():
                if time.monotonic()>=deadline:raise ValueError('native_screen_deadline')
                if not conn.Add(item):raise ValueError('native_screen_item_refused')
            parts=[]
            while remaining:
                if time.monotonic()>=deadline:raise ValueError('native_screen_deadline')
                uid=min(remaining);reached={uid}|{force._uid(i) for i in conn.GetConnectedItems(remaining[uid])}
                own=remaining.keys()&reached
                if not own:raise ValueError('native_screen_empty_component')
                parts.append(set(own))
                for u in own:del remaining[u]
            return parts
        before,after=partition(set()),partition(cut)
        preserved=all(not part-cut or any(part-cut<=q for q in after) for part in before)
        r.update(state='preserved' if preserved else 'lost',complete=True,
            before_components=len(before),after_components=len(after),inspected_items=len(items),
            actual_bores_current_fields_kelvin_native_drc_and_ownership_still_required=True)
    except (ValueError,RuntimeError) as exc:r['reason']=str(exc)
    return r
