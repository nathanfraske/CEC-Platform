"""Conservative physical-material evidence for a native trace corner.

This is observation, not permission to alter a trace, pad, barrel or zone.
Inside/outside polygon bounds prove a hidden result in BOTH directions;
failure to find a visible subtraction is never promoted to that proof.
Identical pre-drill copper unions remain identical after the unchanged
native bores are subtracted. No hole, current or contact rule is relaxed.
"""
import math
import time

import pcbnew
import cec_force_current as force
import cec_native_fill_geometry as fills
from cec_octilinear_corner import coordinate_inset


def microsplice_coverage(board, splice_uuid, receiver_uuids):
    """Exact equal-width H/45 union coverage of a cardinal import splice.

    End discs are retained verbatim. On the intervening tube one half is
    covered by the perpendicular receiver's rectangular web, and the other
    by the diagonal web/start disc. (r+h)^2 <= 2*r^2 is checked as an exact
    integer inequality. This is neither a clearance tolerance nor permission
    to delete the object; no source geometry or electrical role is changed.
    """
    result=dict(ok=False,complete=False,covered=False,errors=[],source_mutated=False,
        retirement_or_current_or_contact_authority=False,release_authority=False)
    try:
        if (type(splice_uuid) is not str or not splice_uuid
                or type(receiver_uuids) not in (list,tuple) or len(receiver_uuids)!=2
                or any(type(u) is not str or not u for u in receiver_uuids)
                or len({splice_uuid,*receiver_uuids})!=3):
            raise ValueError('three_literal_distinct_microsplice_tracks_required')
        tracks=list(board.GetTracks())
        if len(tracks)>16384:raise ValueError('microsplice_native_inventory_bound')
        live={force._uid(t):t for t in tracks};ids=[splice_uuid,*receiver_uuids]
        if not set(ids)<=live.keys():raise ValueError('literal_microsplice_tracks_missing')
        items=[live[u] for u in ids]
        if (any(t.GetClass()!='PCB_TRACK' or t.GetNetCode()<=0 or t.HasSolderMask() for t in items)
                or len({(t.GetNetCode(),int(t.GetLayer()),t.GetWidth()) for t in items})!=1):
            raise ValueError('one_exact_same_net_face_width_native_microsplice_required')
        edge=items[0];width=int(edge.GetWidth());p,q=tuple(edge.GetStart()),tuple(edge.GetEnd())
        if width<=0 or not ((p[0]==q[0])!=(p[1]==q[1])):
            raise ValueError('nonzero_cardinal_microsplice_required')
        h=abs(p[0]-q[0])+abs(p[1]-q[1])
        if (width+2*h)**2>2*width**2:
            raise ValueError('splice_tube_not_covered_by_exact_two_web_bound')
        def direction(a,b):return tuple((b[i]>a[i])-(b[i]<a[i]) for i in (0,1))
        def other(t,at):
            a,b=tuple(t.GetStart()),tuple(t.GetEnd())
            return b if a==at else a if b==at else None
        for a,b in ((p,q),(q,p)):
            v=direction(b,a)
            for horizontal,diagonal in ((items[1],items[2]),(items[2],items[1])):
                first,last=other(horizontal,a),other(diagonal,b)
                if first is None or last is None:continue
                u=direction(a,first);d=direction(b,last)
                if (sum(x*y for x,y in zip(u,v))!=0 or sum(abs(x) for x in u)!=1
                        or d!=tuple(-u[i]-v[i] for i in (0,1))):continue
                hd=[first[i]-a[i] for i in (0,1)];dd=[last[i]-b[i] for i in (0,1)]
                if (not ((hd[0]==0)!=(hd[1]==0)) or abs(dd[0])!=abs(dd[1])
                        or 2*sum(abs(x) for x in hd)<width or 8*dd[0]**2<width**2):continue
                result.update(ok=True,complete=True,covered=True,splice_uuid=splice_uuid,
                    receiver_uuids=[force._uid(horizontal),force._uid(diagonal)],
                    splice_length_nm=h,width_nm=width,
                    exact_tube_inequality=dict(lhs=(width+2*h)**2,rhs=2*width**2),
                    original_round_end_discs_preserved_at_exact_endpoints=True,
                    exact_constant_width_capsule_union_coverage=True,
                    unchanged_common_drills_do_not_change_coverage=True)
                return result
        raise ValueError('two_actual_perpendicular_and_45_native_web_receivers_required')
    except (ValueError,RuntimeError,TypeError,KeyError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def observe(board, track_uuids, at_nm, *, inset_limit_nm=50000,
            polygon_error_nm=100, timeout_s=10.):
    result = dict(ok=False, complete=False, errors=[],
        hidden_material_equivalence_proved=False,
        literal_redundant_microsplice_coverage=[],
        exposed_hard90_not_present_by_positive_native_material_evidence=False,
        source_mutated=False, mutation_or_necessity_authority=False,
        electrical_or_current_or_fabrication_qualified=False,
        release_authority=False)
    started = time.monotonic()
    try:
        if (type(track_uuids) not in (list, tuple) or len(track_uuids)!=2
                or any(type(u) is not str or not u for u in track_uuids)
                or len(set(track_uuids))!=2 or type(at_nm) not in (list, tuple)
                or len(at_nm)!=2 or any(type(v) is not int for v in at_nm)
                or type(inset_limit_nm) is not int or not 1<=inset_limit_nm<=2000000
                or type(polygon_error_nm) is not int or not 1<=polygon_error_nm<=1000
                or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
                or not 0<timeout_s<=10.):
            raise ValueError('bounded_literal_native_corner_observation_required')
        deadline = started+timeout_s
        def tick():
            if time.monotonic()>=deadline:raise ValueError('native_corner_material_deadline')
        tracks = list(board.GetTracks())
        pads = [p for fp in board.GetFootprints() for p in fp.Pads()]
        material = tracks+pads+list(board.Zones())
        if len(material)>16384:raise ValueError('native_corner_material_inventory_bound')
        live = {force._uid(t):t for t in tracks}
        if not set(track_uuids)<=live.keys():raise ValueError('native_corner_source_tracks_missing')
        old = [live[u] for u in track_uuids]
        if (any(t.GetClass()!='PCB_TRACK' or t.GetNetCode()<=0 for t in old)
                or len({(t.GetNetname(),int(t.GetLayer()),t.GetWidth()) for t in old})!=1):
            raise ValueError('one_literal_same_width_net_face_corner_required')
        face = int(old[0].GetLayer());net = str(old[0].GetNetname())
        vectors=[];far=[];actual_near=[]
        for t in old:
            ends=[tuple(t.GetStart()),tuple(t.GetEnd())]
            nearest=min(ends,key=lambda p:math.dist(p,at_nm))
            if math.dist(nearest,at_nm)>1000:
                raise ValueError('literal_native_corner_endpoint_not_present')
            opposite=ends[1] if nearest==ends[0] else ends[0]
            vectors.append(tuple(opposite[i]-at_nm[i] for i in (0,1)))
            far.append(opposite);actual_near.append(list(nearest))
        norm=math.hypot(*vectors[0])*math.hypot(*vectors[1])
        if not norm or abs(sum(a*b for a,b in zip(*vectors)))/norm>1e-5:
            raise ValueError('native_corner_is_not_an_actual_right_angle')
        def micro_witnesses():
            proofs=[]
            for splice,first in ((old[0],old[1]),(old[1],old[0])):
                for t in tracks:
                    tick()
                    if force._uid(t) in track_uuids or t.GetClass()!='PCB_TRACK':continue
                    if (t.GetNetCode()!=splice.GetNetCode() or t.GetLayer()!=face
                            or t.GetWidth()!=splice.GetWidth()):continue
                    if not {tuple(t.GetStart()),tuple(t.GetEnd())}&{tuple(splice.GetStart()),tuple(splice.GetEnd())}:continue
                    proof=microsplice_coverage(board,force._uid(splice),[force._uid(first),force._uid(t)])
                    if proof['covered']:proofs.append(proof)
            return proofs
        step=coordinate_inset(*vectors,maximum_nm=inset_limit_nm,minimum_nm=1)
        if step is None:
            micro=micro_witnesses()
            if not micro:raise ValueError('native_corner_has_no_exact_bounded_octilinear_miter')
            result.update(ok=True,complete=True,net=net,layer_id=face,
                track_uuids=list(track_uuids),source_corner_nm=list(at_nm),
                literal_redundant_microsplice_coverage=micro,
                exposed_hard90_not_present_by_positive_native_material_evidence=True,
                virtual_miter_not_available=True,method='exact_source_two_web_microsplice_coverage',
                elapsed_s=round(time.monotonic()-started,6))
            return result
        inset=[tuple(at_nm[i]+(step if v[i]>0 else -step if v[i]<0 else 0)
                     for i in (0,1)) for v in vectors]
        # A constant-width straight capsule splits EXACTLY into the union
        # of its two sub-capsules. Cancel the common, unchanged far tails
        # analytically before applying polygon error bounds; comparing
        # their rounded far caps as inner/outer polygons would manufacture
        # uncertainty slivers in material that did not change at all.
        # A near-endpoint alias is not assumed collinear with that tail.
        local_old=[];common=[]
        for template,near,opposite,seat in zip(old,actual_near,far,inset):
            dx,dy=opposite[0]-near[0],opposite[1]-near[1]
            sx,sy=seat[0]-near[0],seat[1]-near[1]
            if sx*dy!=sy*dx or not 0<=sx*dx+sy*dy<=dx*dx+dy*dy:
                raise ValueError('corner_alias_not_an_exact_source_capsule_split')
            for collection,start,end in ((local_old,near,seat),(common,seat,opposite)):
                if start==end:continue
                t=template.Duplicate();t.SetStart(pcbnew.VECTOR2I(*start));t.SetEnd(pcbnew.VECTOR2I(*end))
                collection.append(t)
        dx,dy=inset[1][0]-inset[0][0],inset[1][1]-inset[0][1]
        if not (dx or dy) or dx and dy and abs(dx)!=abs(dy):
            raise ValueError('virtual_corner_segment_not_exactly_octilinear')
        crossing=old[0].Duplicate();crossing.SetStart(pcbnew.VECTOR2I(*inset[0]))
        crossing.SetEnd(pcbnew.VECTOR2I(*inset[1]));new=[crossing]
        def polygon(item,error):
            tick();p=pcbnew.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(p,face,0,polygon_error_nm,error)
            fills.identity(p,deadline)
            return p
        def union(items,error):
            p=pcbnew.SHAPE_POLY_SET()
            for item in items:p.BooleanAdd(polygon(item,error))
            return p
        old_outer=union(local_old,pcbnew.ERROR_OUTSIDE)
        old_inner=union(local_old,pcbnew.ERROR_INSIDE)
        new_outer=union(new,pcbnew.ERROR_OUTSIDE)
        new_inner=union(new,pcbnew.ERROR_INSIDE)
        retained=union(common,pcbnew.ERROR_INSIDE);owners=[]
        shapes=[t.GetEffectiveShape(face) for t in local_old+new]
        for item in material:
            tick();uid=force._uid(item)
            if uid in track_uuids or item.GetNetname()!=net or not item.IsOnLayer(face):continue
            if item.GetClass()=='ZONE':
                if item.GetIsRuleArea():continue
                if not item.IsFilled() or not item.HasFilledPolysForLayer(face):
                    raise ValueError('unfilled_same_net_material_is_not_hidden_corner_evidence')
                poly=item.GetFilledPolysList(face)
                fills.identity(poly,deadline)
            else:
                if not any(s.Collide(item.GetEffectiveShape(face),0) for s in shapes):continue
                poly=polygon(item,pcbnew.ERROR_INSIDE)
            retained.BooleanAdd(poly);owners.append(uid)
        removed=old_outer.CloneDropTriangulation()
        removed.BooleanSubtract(new_inner);removed.BooleanSubtract(retained)
        added=new_outer.CloneDropTriangulation()
        added.BooleanSubtract(old_inner);added.BooleanSubtract(retained)
        for p in (removed,added):fills.identity(p,deadline)
        tick()
        micro=[]
        if removed.OutlineCount() or added.OutlineCount():
            micro=micro_witnesses()
        result.update(ok=True,complete=True,net=net,layer_id=face,
            track_uuids=list(track_uuids),source_corner_nm=list(at_nm),
            source_literal_near_endpoints_nm=actual_near,coordinate_inset_nm=step,
            polygon_error_nm=polygon_error_nm,retained_same_net_native_uuids=sorted(owners),
            removed_upper_bound_outlines=removed.OutlineCount(),
            added_upper_bound_outlines=added.OutlineCount(),
            hidden_material_equivalence_proved=not removed.OutlineCount() and not added.OutlineCount(),
            literal_redundant_microsplice_coverage=micro,
            exposed_hard90_not_present_by_positive_native_material_evidence=(
                not removed.OutlineCount() and not added.OutlineCount() or bool(micro)),
            method='outside_old_minus_inside_new_retained_and_reverse',
            unchanged_far_tails_canceled_by_exact_straight_capsule_decomposition=True,
            unchanged_drill_subtraction_preserves_proved_pre_drill_equivalence=True,
            source_current_contact_and_fabrication_authority_not_inferred=True)
    except (ValueError,RuntimeError,TypeError,KeyError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=round(time.monotonic()-started,6)
    return result
