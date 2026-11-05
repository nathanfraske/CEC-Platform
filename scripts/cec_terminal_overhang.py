"""Conservative transaction-owned trace-junction normalization.

Only explicit transaction-owned straight segments may shrink. Every same-net
contact is retained. Filled zones, curved copper and uncertain geometry veto
trimming. Non-centreline straight-track contacts must still collide with the
trimmed segment. This is a proposal-stage
normalizer; independent DRC, pad ownership and pair physics still admit it.
"""
from fractions import Fraction


def _point(vector):
    return int(vector.x), int(vector.y)


def _geometry_order(item):
    return (item.GetNetname(), int(item.GetLayer()), item.GetClass(),
            min(_point(item.GetStart()), _point(item.GetEnd())),
            max(_point(item.GetStart()), _point(item.GetEnd())),
            item.m_Uuid.AsString())


def _cross(a,b):
    return a[0]*b[1]-a[1]*b[0]


def _parameter(a,b,p):
    v=(b[0]-a[0],b[1]-a[1]);d=(p[0]-a[0],p[1]-a[1])
    if _cross(v,d) or v==(0,0):return None
    t=Fraction(d[0],v[0]) if v[0] else Fraction(d[1],v[1])
    return t if 0<=t<=1 else None


def _segment_contacts(a,b,c,d):
    """Exact centreline contacts on AB; parallel overlap keeps its extremes."""
    v=(b[0]-a[0],b[1]-a[1]);w=(d[0]-c[0],d[1]-c[1])
    offset=(c[0]-a[0],c[1]-a[1]);den=_cross(v,w)
    if den:
        t=Fraction(_cross(offset,w),den);u=Fraction(_cross(offset,v),den)
        return [t] if 0<=t<=1 and 0<=u<=1 else []
    if _cross(offset,v):return []
    contacts=[t for p in (c,d) if (t:=_parameter(a,b,p)) is not None]
    contacts.extend(Fraction(i) for i,p in enumerate((a,b))
                    if _parameter(c,d,p) is not None)
    return sorted(set(contacts))


def trim_generated_overhangs(board, track_uuids, *, nets=None):
    """Trim only exposed ends outside the extrema of exact legal junctions.

    A branch endpoint in the middle of another straight trace is a junction,
    not a reason to delete either branch. Keeping the extrema of *all* contact
    sites preserves every edge between them and removes only terminal excess.
    Contact with a pad, barrel or zone makes that segment ineligible. Every
    pre-existing straight-track contact must remain after the proposed trim.
    This intentionally leaves complex cases for native admission.
    """
    import pcbnew
    scope=set(track_uuids or ());wanted=None if nets is None else set(nets)
    if not scope or wanted==set():return {'changed_count':0,'changes':[],'vetoes':[]}
    pads=[pad for fp in board.GetFootprints() for pad in fp.Pads()]
    changed=[];vetoes=[]
    # One deterministic pass. Shrinking another segment never introduces a
    # contact, and junction extrema on that segment remain present.
    tracks=sorted(board.GetTracks(),key=_geometry_order)
    for item in tracks:
        uid=item.m_Uuid.AsString()
        if (uid not in scope or item.GetClass()!='PCB_TRACK'
                or (wanted is not None and item.GetNetname() not in wanted)):
            continue
        start,end=_point(item.GetStart()),_point(item.GetEnd())
        if start==end:continue
        layer=item.GetLayer();net=item.GetNetCode()
        shape=pcbnew.SHAPE_SEGMENT(item.GetStart(),item.GetEnd(),item.GetWidth())
        contacts=[];contact_shapes=[];reason=None
        try:
            # Physical anchors may contact a centreline away from their origin.
            # Veto the whole trace rather than infer that contact from a box.
            for pad in pads:
                if (pad.GetNetCode()==net and pad.IsOnLayer(layer)
                        and pad.GetEffectiveShape(layer).Collide(shape,0)):
                    reason='pad_contact';break
            if reason:continue
            for zone in board.Zones():
                if zone.GetIsRuleArea() or zone.GetNetCode()!=net or not zone.IsOnLayer(layer):continue
                filled=zone.GetFilledPolysList(layer)
                if filled and filled.OutlineCount() and filled.Collide(shape,0):
                    reason='filled_zone_contact';break
            if reason:continue
            for other in tracks:
                if other.m_Uuid.AsString()==uid or other.GetNetCode()!=net or not other.IsOnLayer(layer):continue
                other_shape=other.GetEffectiveShape(layer)
                if not other_shape.Collide(shape,0):continue
                if other.GetClass()!='PCB_TRACK':
                    reason='barrel_or_curved_contact';break
                sites=_segment_contacts(start,end,_point(other.GetStart()),_point(other.GetEnd()))
                contact_shapes.append(other_shape)
                contacts.extend(sites)
        except Exception as exc:
            reason='uncertain_geometry:'+type(exc).__name__
        if reason:
            vetoes.append({'uuid':uid,'reason':reason});continue
        if len(set(contacts))<2:continue
        lo,hi=min(contacts),max(contacts)
        if lo==0 and hi==1:continue
        def position(t):
            xy=[Fraction(start[i])+(end[i]-start[i])*t for i in range(2)]
            # Never round a junction or introduce a non-octilinear delta.
            return tuple(int(v) for v in xy) if all(v.denominator==1 for v in xy) else None
        a,b=position(lo),position(hi)
        if a is None or b is None or a==b:continue
        trimmed=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),item.GetWidth())
        try:
            retained=all(other.Collide(trimmed,0) for other in contact_shapes)
        except Exception:
            retained=False
        if not retained:
            vetoes.append({'uuid':uid,'reason':'would_lose_physical_contact'});continue
        item.SetStart(pcbnew.VECTOR2I(*a));item.SetEnd(pcbnew.VECTOR2I(*b))
        changed.append({'uuid':uid,'net':item.GetNetname(),'layer':board.GetLayerName(layer),
            'before_nm':[list(start),list(end)],'after_nm':[list(a),list(b)],
            'contact_count':len(set(contacts))})
    if changed:board.BuildConnectivity()
    return {'changed_count':len(changed),'changes':changed,'vetoes':vetoes}


def _craft_improvement(before, after):
    """Remove a touched fault without worsening another retained fault.

    Fault identities alone are insufficient: an unchanged junction identity
    can become a sharper backtrack while a different corner disappears.
    """
    import math
    def faults(report):
        result = {}
        for row in report.get('issues', ()):
            key = (row['type'], row.get('net'), row.get('layer'),
                   tuple(row.get('at_mm') or ()),
                   tuple(sorted(row.get('track_uuids') or ())))
            angle = row.get('opening_angle_deg')
            if angle is not None and (type(angle) not in (int, float)
                    or not math.isfinite(angle)):
                raise ValueError('non_finite_craft_angle')
            if key in result and angle is not None:
                prior = result[key]
                angle = min(prior, angle) if prior is not None else angle
            result[key] = angle
        return result
    old, new = faults(before), faults(after)
    if not set(new) < set(old):
        return False
    return all((old[key] is None and angle is None)
               or (old[key] is not None and angle is not None
                   and angle + 1e-9 >= old[key])
               for key, angle in new.items())


def repair_generated_acute_corners(board, track_uuids, *, nets, clearance_mm,
                                  avoid=()):
    """Offer shortest octilinear seats for an unanchored degree-two corner.

    Both incident objects must belong to the caller's new-copper transaction.
    Every old same-net physical contact is retained and every proposed segment
    passes the exact foreign-copper, edge and declared reservation guards.
    Pair-wide geometry/coupling/skew and native DRC are mandatory caller gates.
    """
    import math
    import pcbnew
    import cec_fr
    import cec_precision_route as precision
    import cec_route_quality as quality
    scope=set(track_uuids or ());wanted=set(nets)
    if not math.isfinite(clearance_mm) or clearance_mm<0:
        raise ValueError('clearance must be finite and non-negative')
    if not scope or not wanted:return {'changed_count':0,'changes':[]}
    tracks=sorted(board.GetTracks(),key=_geometry_order)
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    ends={}
    for item in tracks:
        if item.GetClass()!='PCB_TRACK':continue
        for point in (item.GetStart(),item.GetEnd()):
            ends.setdefault((_point(point),item.GetNetCode(),item.GetLayer()),[]).append(item)
    changes=[];used=set()
    for (point,net,layer),incident in sorted(ends.items()):
        if len(incident)!=2:continue
        a,b=incident;ids={a.m_Uuid.AsString(),b.m_Uuid.AsString()}
        if not ids<=scope or ids&used or a.GetNetname() not in wanted or a.GetWidth()!=b.GetWidth():continue
        outer=[]
        for item in incident:
            outer.append(_point(item.GetEnd()) if _point(item.GetStart())==point else _point(item.GetStart()))
        v=[(p[0]-point[0],p[1]-point[1]) for p in outer]
        if not all(math.hypot(*x)>0 for x in v) or sum(v[0][i]*v[1][i] for i in range(2))<=0:continue
        old_shapes=[item.GetEffectiveShape(layer) for item in incident]
        anchors=[]
        uncertain=False
        try:
            for pad in pads:
                if pad.GetNetCode()!=net or not pad.IsOnLayer(layer):continue
                shape=pad.GetEffectiveShape(layer)
                if shape.Collide(pcbnew.VECTOR2I(*point),0):uncertain=True;break
                if any(shape.Collide(old,0) for old in old_shapes):anchors.append(shape)
            for other in tracks:
                if other.m_Uuid.AsString() in ids or other.GetNetCode()!=net or not other.IsOnLayer(layer):continue
                shape=other.GetEffectiveShape(layer)
                if any(shape.Collide(old,0) for old in old_shapes):anchors.append(shape)
                if other.GetClass()=='PCB_VIA' and shape.Collide(pcbnew.SHAPE_CIRCLE(pcbnew.VECTOR2I(*point),1),0):uncertain=True;break
            for zone in board.Zones():
                if zone.GetIsRuleArea() or zone.GetNetCode()!=net or not zone.IsOnLayer(layer):continue
                shape=zone.GetFilledPolysList(layer)
                if shape and shape.OutlineCount() and any(shape.Collide(old,0) for old in old_shapes):uncertain=True;break
        except Exception:
            uncertain=True
        if uncertain:continue
        first,last=outer;dx,dy=last[0]-first[0],last[1]-first[1]
        if not dx or not dy:continue
        diagonal=min(abs(dx),abs(dy));sx=1 if dx>0 else -1;sy=1 if dy>0 else -1
        candidates=[(first[0]+sx*diagonal,first[1]+sy*diagonal),
                    (last[0]-sx*diagonal,last[1]-sy*diagonal)]
        for bend in candidates:
            if bend in (first,last,point):continue
            new_points=[first,bend,last];new_shapes=[pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*q),a.GetWidth()) for p,q in zip(new_points,new_points[1:])]
            try:
                if not all(any(anchor.Collide(shape,0) for shape in new_shapes) for anchor in anchors):continue
                if any(not cec_fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*q),a.GetWidth(),layer,int(round(clearance_mm*1e6)),{net})
                       or not cec_fr._edge_leg_clear(board,pcbnew.VECTOR2I(*p),pcbnew.VECTOR2I(*q),a.GetWidth()//2)
                       for p,q in zip(new_points,new_points[1:])):continue
                if precision._crosses_avoid([(x/1e6,y/1e6) for x,y in new_points],precision._avoid_for_layer(avoid,board.GetLayerName(layer)),a.GetWidth()/1e6):continue
            except Exception:continue
            # A legal replacement of THIS corner can introduce an acute turn
            # at either unchanged outer endpoint, or cross a same-member
            # retained segment. Foreign-net clearance alone cannot detect
            # either. Test the actual native mutation against the whole
            # incident graph and roll it back before offering another seat.
            before_craft=quality.analyze_board(board,
                critical_nets=wanted,track_uuid_scope=ids)
            def crossing_keys():
                selected=[t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'
                          and t.GetNetCode()==net and t.GetLayer()==layer]
                return {tuple(sorted((x.m_Uuid.AsString(),y.m_Uuid.AsString())))
                    for i,x in enumerate(selected) for y in selected[i+1:]
                    if ({x.m_Uuid.AsString(),y.m_Uuid.AsString()} & ids)
                    and precision._seg_cross(_point(x.GetStart()),_point(x.GetEnd()),
                                             _point(y.GetStart()),_point(y.GetEnd()))}
            before_cross=crossing_keys()
            old_positions=[(_point(item.GetStart()),_point(item.GetEnd())) for item in incident]
            for item in incident:
                if _point(item.GetStart())==point:item.SetStart(pcbnew.VECTOR2I(*bend))
                else:item.SetEnd(pcbnew.VECTOR2I(*bend))
            after_craft=quality.analyze_board(board,
                critical_nets=wanted,track_uuid_scope=ids)
            if not _craft_improvement(before_craft, after_craft) or not crossing_keys() <= before_cross:
                for item,(old_start,old_end) in zip(incident,old_positions):
                    item.SetStart(pcbnew.VECTOR2I(*old_start))
                    item.SetEnd(pcbnew.VECTOR2I(*old_end))
                continue
            changes.append({'track_uuids':sorted(ids),'net':a.GetNetname(),
                            'before_nm':list(point),'after_nm':list(bend)})
            used.update(ids);break
    if changes:board.BuildConnectivity()
    return {'changed_count':len(changes),'changes':changes}
