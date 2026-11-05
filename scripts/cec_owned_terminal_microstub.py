"""Propose tiny new-owned endpoint nib removal, never electrical permission.

The old source copper is immutable. A source-adjacent, same-width nib may be
proposed only from actual generated native material and an actual craft
finding. The caller STILL owes exact saved delta/terminal/current/contact,
field, DRC and (when applicable) absolute Kelvin receiving after the cut.
"""
import math,time
import pcbnew
import cec_force_current as force
import cec_native_track_ports as tracks


def plan(parent,board,created_track_uuids,craft,*,timeout_s=1.,maximum_candidates=4):
    if (type(created_track_uuids) not in (list,tuple,set) or not 1<=len(created_track_uuids)<=1024
            or len(set(created_track_uuids))!=len(created_track_uuids)
            or any(type(u) is not str or not u for u in created_track_uuids)
            or type(craft) is not dict or type(craft.get('issues')) is not list
            or len(craft['issues'])>4096 or type(maximum_candidates) is not int
            or not 1<=maximum_candidates<=4 or type(timeout_s) not in (int,float)
            or not math.isfinite(timeout_s) or not 0<timeout_s<=3.):
        raise ValueError('bounded_literal_new_owned_terminal_microstub_scope_required')
    original={force._uid(t):t for t in parent.GetTracks()}
    items={force._uid(t):t for t in board.GetTracks()};created=set(created_track_uuids)
    if (len(items)>16384 or len(items)!=len(list(board.GetTracks()))
            or created & original.keys() or not created<=items.keys()):
        raise ValueError('created_terminal_nib_must_not_be_source_copper')
    deadline=time.monotonic()+timeout_s;plans=[];seen=set()
    def identity(t):
        return (t.GetClass(),str(t.GetNetname()),int(t.GetLayer()),int(t.GetWidth()),
            tuple(t.GetStart()),tuple(t.GetEnd()),bool(t.IsLocked()))
    for issue in craft['issues']:
        if time.monotonic()>=deadline:raise ValueError('owned_terminal_microstub_proposal_deadline')
        if issue.get('type') not in ('acute_backtrack','covered_backtrack'):continue
        ids=issue.get('track_uuids',[])
        if not isinstance(ids,list) or len(ids)!=2 or len(set(ids))!=2 or not set(ids)<=items.keys():continue
        small=[u for u in ids if u in created];old=[u for u in ids if u in original]
        if len(small)!=1 or len(old)!=1:continue
        uid,retained=small[0],old[0];t,peer=items[uid],items[retained]
        if (uid in seen or t.GetClass()!='PCB_TRACK' or peer.GetClass()!='PCB_TRACK'
                or identity(peer)!=identity(original[retained]) or t.GetParentGroup() is not None
                or t.GetNetCode()!=peer.GetNetCode() or t.GetLayer()!=peer.GetLayer()
                or t.GetWidth()!=peer.GetWidth() or t.GetLength()<=0):
            continue
        covered=all(tracks.on_centerline(peer,tuple(at)) for at in (t.GetStart(),t.GetEnd()))
        # For actual straight same-width strokes, segment inclusion implies
        # exact capsule inclusion (the same native round-cap kernel on both).
        # This is a geometric source subset proof, not a tolerance increase
        # to turn a 50.001-um overlap into a nominal 50-um "micro" stub.
        if not covered and t.GetLength()>min(50000,t.GetWidth()//20):continue
        shared={tuple(t.GetStart()),tuple(t.GetEnd())}&{tuple(peer.GetStart()),tuple(peer.GetEnd())}
        if len(shared)!=1:continue
        other=next(p for p in (tuple(t.GetStart()),tuple(t.GetEnd())) if p not in shared)
        if not peer.GetEffectiveShape(peer.GetLayer()).Collide(pcbnew.VECTOR2I(*other),0):continue
        seen.add(uid);plans.append(dict(uuid=uid,retained_source_track_uuid=retained,
            net=str(t.GetNetname()),layer=int(t.GetLayer()),length_nm=round(t.GetLength()),
            unchanged_width_nm=int(t.GetWidth()),shared_endpoint_nm=list(next(iter(shared))),
            surviving_new_endpoint_nm=list(other),retained_native_material_contains_surviving_axis=True,
            entire_native_stroke_is_exact_source_capsule_subset=covered,
            kind='source_covered_new_stroke' if covered else 'source_adjacent_new_microstub'))
        if len(plans)>=maximum_candidates:break
    return dict(schema=1,proposals=plans,source_copper_or_native_board_changed=False,
        automatic_cut_or_contact_or_current_authority=False,
        exact_saved_native_source_receiving_still_required=True,release_authority=False)
