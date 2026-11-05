"""Bounded Source-owned Ground barrel seats inside the SAME projected land.

Pure proposal validation: no copper is emitted or removed. Full expanded
native circles, not pad boxes, prove positive containment before and after.
The enclosing macro still owns exact dimensions/groups, factory reproof,
all-face clearance, saved replay and every original physical return.
"""
import math,time
import pcbnew
import cec_force_current as force


def resolve(source,candidate,requests,owner_proofs,*,maximum_shift_nm,timeout_s=10.,maximum_translation_mm=64.):
    if (type(requests) not in (list,tuple) or len(requests)>4
            or type(maximum_translation_mm) not in (int,float) or not math.isfinite(maximum_translation_mm)
            or not 0<maximum_translation_mm<=128.
            or type(maximum_shift_nm) is not int or not 0<maximum_shift_nm<=maximum_translation_mm*1e6
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10):
        raise ValueError('bounded_explicit_source_ground_inpad_seats_required')
    if not requests:return []
    deadline=time.monotonic()+timeout_s
    old={force._uid(v):v for v in source.GetTracks()}
    lands=[{force._uid(p):p for f in b.GetFootprints() for p in f.Pads()} for b in (source,candidate)]
    proofs={row['uuid']:row for row in owner_proofs};result=[];seen=set()
    for q in requests:
        if time.monotonic()>=deadline:raise ValueError('source_ground_inpad_seat_deadline')
        if (type(q) is not dict or set(q)!={'uuid','owner_pad_uuid','position_nm'}
                or type(q['uuid']) is not str or q['uuid'] in seen or q['uuid'] not in proofs
                or type(q['owner_pad_uuid']) is not str
                or type(q['position_nm']) is not list or len(q['position_nm'])!=2
                or any(type(v) is not int or abs(v)>2000000000 for v in q['position_nm'])):
            raise ValueError('unique_literal_source_ground_inpad_seat_required')
        uid=q['uuid'];seen.add(uid);proof=proofs[uid];v=old[uid]
        pad_uid=q['owner_pad_uuid'];a=lands[0].get(pad_uid);b=lands[1].get(pad_uid)
        if (a is None or b is None or v.GetClass()!='PCB_VIA' or v.GetNetname()!='GND'
                or a.GetNetname()!=b.GetNetname() or a.GetNetname()!='GND'
                or a.GetNetCode()!=v.GetNetCode()
                or a.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or b.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                or a.HasHole() or b.HasHole() or a.GetParentFootprint().IsDNP()
                or force._uid(a.GetParentFootprint())!=force._uid(b.GetParentFootprint())
                or proof['actual_source_ownership_basis']!='complete_native_in_pad_containment'
                or proof['source_owner_pad_uuids']!=[pad_uid]
                or proof['owner_footprint_uuids']!=[force._uid(a.GetParentFootprint())]):
            raise ValueError('one_actual_source_owned_inpad_ground_land_required')
        source_at=tuple(v.GetPosition());target=tuple(q['position_nm'])
        rigid=tuple(source_at[i]+proof['translation_nm'][i] for i in (0,1))
        offset=tuple(target[i]-rigid[i] for i in (0,1))
        if (math.dist(source_at,target)>maximum_shift_nm or not 0<math.hypot(*offset)<=500000):
            raise ValueError('bounded_nonzero_projected_land_ground_seat_required')
        faces=[int(l) for l in source.GetEnabledLayers().CuStack() if a.IsOnLayer(l)]
        if len(faces)!=1 or faces!=[int(l) for l in candidate.GetEnabledLayers().CuStack() if b.IsOnLayer(l)]:
            raise ValueError('same_actual_surface_ground_seat_required')
        face=faces[0]
        for pad,at in ((a,source_at),(b,target)):
            material=pcbnew.SHAPE_POLY_SET()
            # The unchanged via's complete outer land plus 100 nm is
            # required inside actual pad copper on both Source and target.
            v.TransformShapeToPolygon(material,face,100,1,pcbnew.ERROR_OUTSIDE)
            material.Move(pcbnew.VECTOR2I(at[0]-source_at[0],at[1]-source_at[1]))
            material.BooleanSubtract(pad.GetEffectivePolygon(face,pcbnew.ERROR_INSIDE))
            if material.OutlineCount():raise ValueError('positive_native_ground_seat_containment_required')
        result.append(dict(uuid=uid,owner_pad_uuid=pad_uid,
            source_owner_footprint_uuid=force._uid(a.GetParentFootprint()),
            position_nm=list(target),source_displacement_nm=[target[i]-source_at[i] for i in (0,1)],
            rigid_owner_target_nm=list(rigid),owner_relative_offset_nm=list(offset),
            source_and_projected_complete_native_containment=True,positive_margin_nm=100,
            same_source_barrel_geometry_and_count=True,source_power_or_signal_motion_authorized=False,
            clearance_qualified=False,current_qualified=False,release_authority=False))
    if time.monotonic()>=deadline:raise ValueError('source_ground_inpad_seat_deadline')
    return result
