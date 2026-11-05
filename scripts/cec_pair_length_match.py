"""Bounded compact length-match proposals over NEW owned pair tracks only.

This never lowers a source skew, coupling, width or clearance rule. Native
whole-pair/tree, reference, current, field and uncapped DRC receiving remain
mandatory. No retained source copper, pad, via, pose or pour is editable.
"""
import math
import time


def offset_path(start, end, amplitude_nm, side, *, lead_nm=500000, end_lead_nm=None):
    """One monotone 45-degree offset, without a hairpin or hard corner."""
    if end_lead_nm is None:end_lead_nm=lead_nm
    if (any(type(p) not in (tuple,list) or len(p)!=2 or
            any(type(v) is not int or abs(v)>2000000000 for v in p)
            for p in (start,end)) or type(amplitude_nm) is not int or
            amplitude_nm<=0 or type(side) is not int or side not in (-1,1)
            or type(lead_nm) is not int or lead_nm<=0
            or type(end_lead_nm) is not int or end_lead_nm<=0):
        raise ValueError('bounded_integer_owned_offset_geometry_required')
    dx,dy=end[0]-start[0],end[1]-start[1]
    if bool(dx)==bool(dy):
        raise ValueError('nonzero_cardinal_owned_source_segment_required')
    length=abs(dx)+abs(dy)
    if length<lead_nm+end_lead_nm+2*amplitude_nm+500000:
        return None
    ux,uy=(int(math.copysign(1,dx)) if dx else 0,
           int(math.copysign(1,dy)) if dy else 0)
    nx,ny=-side*uy,side*ux
    def at(run,off):
        return (start[0]+ux*run+nx*off,start[1]+uy*run+ny*off)
    return [tuple(start),at(lead_nm,0),at(lead_nm+amplitude_nm,amplitude_nm),
        at(length-end_lead_nm-amplitude_nm,amplitude_nm),at(length-end_lead_nm,0),tuple(end)]


def compact_window_leads(length_nm, amplitude_nm):
    """Finite shortest windows, placed along the retained straight segment.

    Each has only a 0.5 mm offset plateau. Long parallel offsets unnecessarily
    sacrifice pair coupling; moving a compact window can avoid a local via
    or connector without enlarging it or changing the source skew rule.
    """
    if any(type(v) is not int or not 0<v<=2000000000
           for v in (length_nm,amplitude_nm)):
        raise ValueError('positive_bounded_integer_matching_window_required')
    available=length_nm-2*amplitude_nm-500000
    if available<1000000:return []
    starts=[500000,1500000,2500000,available//2,
            available//4,3*available//4,available-1500000,available-500000]
    return list(dict.fromkeys((first,available-first) for first in starts
                              if 500000<=first<=available-500000))


def balance(board,pair,editable_track_uuids,*,deadline,max_proposals=24,max_changes=2):
    import pcbnew
    import cec_pair_skew as skew
    import cec_precision_route as route
    import cec_fr as fr
    import cec_force_current as force
    from cec_native_items import discard_items
    if (pair.get('kind') not in ('can','usb','diff') or type(max_proposals) is not int
            or not 1<=max_proposals<=128 or type(max_changes) is not int or
            not 1<=max_changes<=8 or not math.isfinite(deadline)):
        raise ValueError('bounded_source_owned_pair_length_balance_required')
    editable=set(editable_track_uuids)
    if len(editable)>512 or any(type(u) is not str or not u for u in editable):
        raise ValueError('finite_explicit_new_owned_track_scope_required')
    before=skew.from_board(board,pair)
    receipt=dict(scope='new_owned_pair_copper_length_match_proposal_only',before=before,
        attempts=0,changes=[],deadline_exhausted=False,source_skew_limit_changed=False,
        retained_source_geometry_editable=False,one_window_per_owned_original_track=True,
        release_authority=False,rejection_counts={},rejection_examples=[])
    def reject(reason,track,**details):
        counts=receipt['rejection_counts'];counts[reason]=counts.get(reason,0)+1
        if len(receipt['rejection_examples'])<16:
            receipt['rejection_examples'].append(dict(reason=reason,track_uuid=force._uid(track),
                start_nm=list(track.GetStart()),end_nm=list(track.GetEnd()),**details))
    if before['ok']:
        receipt.update(after=before,reason='existing_whole_net_skew_within_limit');return receipt
    width=route._nm(pair['width']);clearance=route._nm(route._pair_clearance(board,pair,None))
    shorter=pair['p'] if before['p_length_mm']<before['n_length_mm'] else pair['n']
    for _ in range(max_changes):
        now=skew.from_board(board,pair)
        if now['ok']:break
        required_nm=math.ceil((now['skew_mm']-now['limit_mm']+.20)*1e6)
        amplitude=math.ceil(required_nm/(2*math.sqrt(2)-2))
        amplitude=min(amplitude,3000000)
        amplitudes=sorted({max(1,math.ceil(amplitude*f)) for f in (1.,.8,.6,.4,.2)},reverse=True)
        all_items=list(board.GetTracks())
        tracks=[t for t in all_items if force._uid(t) in editable
            and t.GetClass()=='PCB_TRACK' and t.GetNetname()==shorter
            and t.GetWidth()==width and t.GetParentGroup() is None
            and bool(t.GetStart().x!=t.GetEnd().x)!=bool(t.GetStart().y!=t.GetEnd().y)]
        tracks.sort(key=lambda t:(-t.GetLength(),int(t.GetLayer()),tuple(t.GetStart()),
                                  tuple(t.GetEnd()),force._uid(t)))
        change=None
        for track in tracks:
            if receipt['attempts']>=max_proposals or time.monotonic()>=deadline:break
            start,end=tuple(track.GetStart()),tuple(track.GetEnd());layer=int(track.GetLayer())
            # A physical terminal or an actual graph junction cannot become
            # a tuning site merely because a long straight crosses it.
            incident=[sum(t.GetClass()=='PCB_TRACK' and t.GetNetname()==shorter
                and t.GetLayer()==layer and p in (tuple(t.GetStart()),tuple(t.GetEnd()))
                for t in all_items) for p in (start,end)]
            pads=[p for f in board.GetFootprints() for p in f.Pads() if p.IsOnLayer(layer)]
            terminals=[*pads,*[v for v in all_items if v.GetClass()=='PCB_VIA' and v.IsOnLayer(layer)]]
            anchors=[[item for item in terminals if item.GetNetname()==shorter
                and item.GetEffectiveShape(layer).Collide(
                    pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*p),width),0)]
                for p in (start,end)]
            # A true terminal may own degree one. Its contact and the first
            # straight lead are unchanged, never displaced or widened. A
            # floating degree-one end or a branching junction is not a site.
            if any(degree not in (1,2) or (degree==1 and not anchor)
                   for degree,anchor in zip(incident,anchors)):
                reject('not_an_unbranched_owned_window',track,incident=incident);continue
            anchor_ids={force._uid(item) for row in anchors for item in row}
            choices=[(value,side,first,last) for value in amplitudes
                     for first,last in compact_window_leads(abs(end[0]-start[0])+abs(end[1]-start[1]),value)
                     for side in (-1,1)]
            for amplitude_value,side,first_lead,last_lead in choices:
                if receipt['attempts']>=max_proposals or time.monotonic()>=deadline:break
                points=offset_path(start,end,amplitude_value,side,
                                   lead_nm=first_lead,end_lead_nm=last_lead)
                if points is None:continue
                receipt['attempts']+=1
                # Both actual turns lie outside all physical terminals. The
                # original straight contact leads retain exact endpoints.
                if any(item.GetEffectiveShape(layer).Collide(
                        pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*p),width),0)
                        for item in terminals for p in (points[1],points[-2])):
                    reject('turn_inside_native_terminal',track,amplitude_nm=amplitude_value,side=side);continue
                cache={};netcode=int(track.GetNetCode())
                if not all(fr._edge_leg_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),width//2)
                    and fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),width,
                        layer,clearance,{netcode},foreign_cache=cache)
                    for a,z in zip(points,points[1:])):
                    reject('foreign_copper_or_board_material',track,amplitude_nm=amplitude_value,side=side);continue
                # Same-member copper is not a tuning exemption. Nonincident
                # native contacts would create a redundant tree edge or a
                # new terminal branch; reject them before changing anything.
                nonincident=[item for item in all_items if item!=track
                    and item.GetNetname()==shorter and item.IsOnLayer(layer)]
                same_pads=[p for p in pads if p.GetNetname()==shorter]
                if any(item.GetEffectiveShape(layer).Collide(
                        pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),width),0)
                        for item in (*nonincident,*same_pads)
                        for a,z in zip(points[1:-1],points[2:-1])):
                    reject('same_member_redundant_contact',track,amplitude_nm=amplitude_value,side=side);continue
                original_uuid=force._uid(track)
                incoming=[]
                for a,z in zip(points,points[1:]):
                    t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
                    t.SetWidth(width);t.SetLayer(layer);t.SetNetCode(netcode);board.Add(t)
                    incoming.append(force._uid(t))
                # Never offset an offset in this transaction. Distribute
                # matching over original straight windows instead of making
                # nested sideways zigzags in one otherwise clean corridor.
                discard_items(board,[track]);editable.remove(original_uuid)
                change=dict(retired_new_track_uuid=original_uuid,incoming_uuids=incoming,
                    points_nm=points,amplitude_nm=amplitude_value,layer=layer,shorter_member_net=shorter,
                    unchanged_terminal_anchor_uuids=sorted(anchor_ids),
                    unchanged_straight_leads_nm=[first_lead,last_lead],
                    purpose='existing_source_whole_pair_length_match',native_pair_receiving_required=True)
                receipt['changes'].append(change);break
            if change:break
        if change is None:break
    receipt.update(after=skew.from_board(board,pair),deadline_exhausted=time.monotonic()>=deadline)
    return receipt
