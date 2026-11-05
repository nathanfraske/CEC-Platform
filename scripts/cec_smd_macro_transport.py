"""Provisional native endpoint transport for explicitly bounded SMD poses.

Actual source lands and short, re-proved POFV dogbones own their barrels.
Process grouping is not a placement lock, but arbitrary route groups remain
immutable. No proximity-only ownership, trace thinning, hole/outline motion,
current sharing or saved-board admission is granted. Noncanonical boundary
seeds must be reconstructed and independently received before saving a PCB.
"""
import math
import time
from collections import defaultdict
from pathlib import Path

import pcbnew
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_route_quality as quality


def _endpoint_contact_index(board,items):
    """Ephemeral Source-only broad phase; every hit still uses native metal.

    The caller keeps this board immutable. Numeric net codes are therefore
    valid only for this one transport transaction, never a serialized proof
    or cross-save cache. Native boxes only discard impossible contacts.
    """
    result=defaultdict(list);layers=tuple(board.GetEnabledLayers().CuStack())
    for item,shift,owner in items:
        code=item.GetNetCode()
        for face in layers:
            if not item.IsOnLayer(face):continue
            shape=item.GetEffectiveShape(face);box=shape.BBox()
            result[code,int(face)].append((item,shift,owner,shape,
                (box.GetLeft(),box.GetTop(),box.GetRight(),box.GetBottom())))
    return result


def _endpoint_contacts(index,net_code,face,point):
    x,y=point;at=pcbnew.VECTOR2I(x,y)
    return [(item,shift,owner) for item,shift,owner,shape,(left,top,right,bottom)
        in index.get((net_code,int(face)),())
        if left<=x<=right and top<=y<=bottom and shape.Collide(at,0)]


def apply(source, candidate, *, maximum_shift_mm=6., maximum_translation_mm=64., maximum_footprints=16,
          maximum_conductors=256, timeout_s=10., ordinary_via_poses=(),
          source_path=None, board_hint=None, allow_cardinal_rotations=False,allow_octilinear_rotations=False,
          local_signal_return_via_poses=(), maximum_ordinary_vias=4,
          maximum_local_return_shift_mm=3., local_signal_port_via_poses=(),
          maximum_local_signal_port_shift_mm=3., retained_ground_contacts=(),
          reused_ground_barrel_contacts=(),stationary_ground_barrel_uuids=(),
          local_signal_port_offsets=(),retain_source_tracks=False,
          carry_ground_barrels_only=False,source_ground_barrel_seats=(),reference_group_uuids=(),
          rebuild_source_ground_endpoints=False,allow_owned_locked_ground_endpoints=False,
          rebuild_source_supply_endpoints=False,source_rc_input_prefixes=(),source_control_ground_return_axes=()):
    """Transport source copper only after explicit bounded FP pose proposals.

    Validate the complete request before writes. If the final live POFV check
    refuses, restore every conductor. The enclosing transaction owns the FP
    proposals, ground refill, boundary routing and whole-board acceptance.
    """
    # An explicit construction reach is separate from any physical or
    # electrical acceptance. Preserve the legacy64 ceiling unless the
    # caller deliberately forwards a larger finite work tier; the enclosing
    # Source compiler still independently bounds EVERY role's motion.
    if (type(maximum_translation_mm) not in (int,float) or not math.isfinite(maximum_translation_mm)
            or not 0 < maximum_translation_mm <= 128.
            or type(maximum_shift_mm) not in (int,float) or not math.isfinite(maximum_shift_mm)
            or not 0 < maximum_shift_mm <= maximum_translation_mm
            or type(maximum_footprints) is not int or not 1 <= maximum_footprints <= 32
            or type(maximum_conductors) is not int or not 1 <= maximum_conductors <= 512
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10. or type(allow_cardinal_rotations) is not bool
            or type(allow_octilinear_rotations) is not bool
            or type(retain_source_tracks) is not bool
            or type(carry_ground_barrels_only) is not bool
            or type(rebuild_source_ground_endpoints) is not bool
            or type(rebuild_source_supply_endpoints) is not bool
            or rebuild_source_supply_endpoints and retain_source_tracks
            or type(allow_owned_locked_ground_endpoints) is not bool
            or allow_owned_locked_ground_endpoints and not rebuild_source_ground_endpoints
            or rebuild_source_ground_endpoints and retain_source_tracks
            or type(source_ground_barrel_seats) not in (list,tuple) or len(source_ground_barrel_seats)>4
            or type(source_control_ground_return_axes) not in (list,tuple) or len(source_control_ground_return_axes)>4
            or source_control_ground_return_axes and (local_signal_return_via_poses or carry_ground_barrels_only)
            or source_ground_barrel_seats and not carry_ground_barrels_only
            or carry_ground_barrels_only and (not retain_source_tracks or ordinary_via_poses
                or local_signal_return_via_poses or local_signal_port_via_poses or local_signal_port_offsets)
            or type(maximum_ordinary_vias) is not int or not 1<=maximum_ordinary_vias<=8
            or type(maximum_local_return_shift_mm) not in (int,float)
            or not math.isfinite(maximum_local_return_shift_mm) or not 0<maximum_local_return_shift_mm<=6.
            or type(maximum_local_signal_port_shift_mm) not in (int,float)
            or not math.isfinite(maximum_local_signal_port_shift_mm) or not 0<maximum_local_signal_port_shift_mm<=6.
            or type(retained_ground_contacts) not in (tuple,list) or len(retained_ground_contacts)>16
            or type(reused_ground_barrel_contacts) not in (tuple,list) or len(reused_ground_barrel_contacts)>16):
        raise ValueError('bounded_explicit_native_smd_macro_scope_required')
    deadline=time.monotonic()+timeout_s
    import cec_macro_rc_input_prefix as rc_prefix
    source_rc_input_prefixes=rc_prefix.requests(source_rc_input_prefixes)
    if source_rc_input_prefixes and (not rebuild_source_supply_endpoints or source_path is None
            or Path(source_path).resolve()!=Path(source.GetFileName()).resolve()):
        raise ValueError('provisional_RC_requires_actual_Source_complete_supply_reconstruction')
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_smd_macro_transport_deadline')
    def index(items):
        rows=list(items)
        if len(rows)>16384:raise ValueError('native_smd_macro_inventory_bound')
        lookup={force._uid(t):t for t in rows}
        if len(rows)!=len(lookup):raise ValueError('native_smd_macro_duplicate_identity')
        return lookup
    old_fp,new_fp=index(source.GetFootprints()),index(candidate.GetFootprints())
    reference_owners={}
    if (type(reference_group_uuids) not in (list,tuple) or len(reference_group_uuids)>8
            or len(set(reference_group_uuids))!=len(reference_group_uuids)
            or any(type(u)is not str or not u for u in reference_group_uuids)):
        raise ValueError('explicit_source_reference_group_uuid_scope_required')
    if reference_group_uuids:
        import cec_source_reference_group_transport as reference_transport
        if source_path is None:raise ValueError('actual_reference_group_source_path_required')
        annotation_requests=[]
        for group_uuid in reference_group_uuids:
            g=next((g for g in source.Groups() if force._uid(g)==group_uuid),None)
            owners=[] if g is None else [i for i in g.GetItems() if i.GetClass()=='FOOTPRINT']
            if len(owners)!=1:raise ValueError('actual_one_owner_reference_group_required')
            uid=force._uid(owners[0]);fp=old_fp[uid];after=new_fp.get(uid)
            if after is None or after.IsFlipped()!=fp.IsFlipped():
                raise ValueError('source_reference_group_same_face_required')
            turn=(after.GetOrientationDegrees()-fp.GetOrientationDegrees())%360
            if turn%90:raise ValueError('source_reference_group_exact_cardinal_only')
            proof=reference_transport.inspect(source_path,owner_uuid=uid,group_uuid=group_uuid)
            reference_owners[uid]=proof
            annotation_requests.append((proof,int(turn)//90,
                tuple(b-a for a,b in zip(tuple(fp.GetPosition()),tuple(after.GetPosition())))))
        if any(turn for proof,turn,delta in annotation_requests):
            import cec_source_reference_group_cardinal_batch as cardinal
            cardinal.verify_native(source_path,candidate,annotation_requests,timeout_s=max(.001,deadline-time.monotonic()),
                maximum_translation_mm=maximum_shift_mm)
        else:reference_transport.verify_native(source_path,candidate,[(proof,delta)for proof,turn,delta in annotation_requests],
            maximum_translation_mm=maximum_shift_mm)
    old,new=index(source.GetTracks()),index(candidate.GetTracks())
    def group_context(board):
        return {force._uid(g):(str(g.GetName()),bool(g.IsLocked()),
            tuple(sorted(force._uid(t) for t in g.GetItems()))) for g in board.Groups()}
    if group_context(source)!=group_context(candidate):
        raise ValueError('native_smd_macro_source_group_context_changed')
    if (tuple(source.GetEnabledLayers().CuStack())!=tuple(candidate.GetEnabledLayers().CuStack())
            or fab.board_profile_name(source)!=fab.board_profile_name(candidate)):
        raise ValueError('native_smd_macro_source_stack_or_factory_profile_changed')
    if old_fp.keys()!=new_fp.keys() or old.keys()!=new.keys():
        raise ValueError('native_smd_macro_source_population_changed')
    moved={};pads=[];transforms={};clone_owners=[]
    def point_shift(at,owner):
        if owner not in transforms:return (0,0)
        row=transforms[owner];x,y=at[0]-row['source_origin_nm'][0],at[1]-row['source_origin_nm'][1]
        c,s=row['cos'],row['sin'];target=row['candidate_origin_nm']
        return (target[0]+round(c*x+s*y)-at[0],target[1]+round(-s*x+c*y)-at[1])
    def land_shape(p,lid):
        poly=p.GetEffectivePolygon(lid,pcbnew.ERROR_OUTSIDE)
        if poly.OutlineCount()>64:raise ValueError('native_smd_macro_land_outline_bound')
        result=[];count=0;origin=tuple(p.GetPosition())
        for i in range(poly.OutlineCount()):
            entries=[]
            for ring in [poly.COutline(i),*[poly.CHole(i,j) for j in range(poly.HoleCount(i))]]:
                tick();count+=ring.PointCount()
                if count>8192 or ring.ArcCount():raise ValueError('native_smd_macro_land_polygon_bound')
                entries.append(tuple((int(ring.CPoint(j).x)-origin[0],int(ring.CPoint(j).y)-origin[1])
                    for j in range(ring.PointCount())))
            result.append(tuple(entries))
        return tuple(result)
    for uid,fp in old_fp.items():
        tick();after=new_fp[uid]
        if (str(fp.GetReference())!=str(after.GetReference()) or str(fp.GetValue())!=str(after.GetValue())
                or str(fp.GetFPIDAsString())!=str(after.GetFPIDAsString()) or fp.IsLocked()!=after.IsLocked()
                or fp.GetAttributes()!=after.GetAttributes()
                or {f.GetName():f.GetText() for f in fp.GetFields()}!={f.GetName():f.GetText() for f in after.GetFields()}):
            raise ValueError('native_smd_macro_source_component_identity_changed')
        ps,qs=index(fp.Pads()),index(after.Pads())
        if ps.keys()!=qs.keys() or fp.IsFlipped()!=after.IsFlipped():
            raise ValueError('native_smd_macro_pad_population_or_face_changed')
        shift=tuple(b-a for a,b in zip(tuple(fp.GetPosition()),tuple(after.GetPosition())))
        turn=(after.GetOrientationDegrees()-fp.GetOrientationDegrees())%360
        permitted=(allow_cardinal_rotations and turn%90==0 or allow_octilinear_rotations and turn%45==0)
        if (turn and not permitted
                or math.hypot(*shift)>maximum_shift_mm*1e6):
            raise ValueError('native_smd_macro_exact_bounded_translation_required')
        expected=ps
        if shift!=(0,0) or turn:
            if ((fp.GetParentGroup() is not None or after.GetParentGroup() is not None) and uid not in reference_owners
                    or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in ps.values())):
                raise ValueError('native_smd_macro_ungrouped_all_smd_owner_required')
            if any(len([l for l in source.GetEnabledLayers().CuStack() if p.IsOnLayer(l)])!=1 for p in ps.values()):
                raise ValueError('native_smd_macro_single_actual_smd_copper_face_required')
            moved[uid]=shift
            cardinal=turn%90==0
            c,s=math.cos(math.radians(turn)),math.sin(math.radians(turn))
            transforms[uid]=dict(source_origin_nm=list(fp.GetPosition()),candidate_origin_nm=list(after.GetPosition()),
                **({'cardinal_turn_deg':turn} if cardinal else {'octilinear_turn_deg':turn}),
                cos=round(c) if cardinal else c,sin=round(s) if cardinal else s)
            if turn:
                # Native cloned lands provide the exact rotated copper
                # expectation, including custom/chamfered/roundrect pads.
                # Retain the owning clone while borrowed pads are inspected.
                clone=fp.Clone();projected=pcbnew.Cast_to_FOOTPRINT(pcbnew.Cast_to_BOARD_ITEM(clone))
                clone_owners.append((clone,projected));projected.SetOrientationDegrees(after.GetOrientationDegrees())
                projected.SetPosition(after.GetPosition());expected=index(projected.Pads())
        for puid,p in ps.items():
            q=qs[puid]
            pad_shift=point_shift(tuple(p.GetPosition()),uid)
            pad_motion=math.hypot(*pad_shift)
            if pad_motion>maximum_shift_mm*1e6:
                # A cardinal turn can move the outer land farther than the
                # footprint origin. This is an explicit work-extent refusal,
                # not evidence that the source pad's copper shape changed.
                raise ValueError('native_smd_macro_pad_motion_work_limit_exceeded:'+
                    str(fp.GetReference())+':'+str(p.GetNumber())+':'+puid+
                    ':actual_nm='+str(round(pad_motion))+':limit_nm='+str(round(maximum_shift_mm*1e6)))
            if (p.GetNumber()!=q.GetNumber() or p.GetNetname()!=q.GetNetname()
                    or tuple(p.GetSize())!=tuple(q.GetSize())
                    or tuple(p.GetDrillSize())!=tuple(q.GetDrillSize())
                    or p.GetShape()!=q.GetShape() or p.GetAttribute()!=q.GetAttribute()
                    or tuple(p.GetOffset())!=tuple(q.GetOffset())
                    or set(p.GetLayerSet().Seq())!=set(q.GetLayerSet().Seq())
                    or any(land_shape(expected[puid],l)!=land_shape(q,l) for l in source.GetEnabledLayers().CuStack() if p.IsOnLayer(l))
                    or tuple(q.GetPosition())!=tuple(v+d for v,d in zip(tuple(p.GetPosition()),pad_shift))):
                raise ValueError('native_smd_macro_source_land_changed')
            if p.GetNetCode()>0:pads.append((p,point_shift(tuple(p.GetPosition()),uid),uid))
    if not 1<=len(moved)<=maximum_footprints:
        raise ValueError('native_smd_macro_nonempty_bounded_owner_cohort_required')
    def dims(t,b):
        base=(t.GetClass(),str(t.GetNetname()),t.IsLocked(),
              tuple(sorted(force._uid(g) for g in b.Groups() if g.ContainsItem(t))))
        if t.GetClass()=='PCB_TRACK':return base+(int(t.GetLayer()),int(t.GetWidth()))
        if t.GetClass()=='PCB_VIA':return base+(int(t.TopLayer()),int(t.BottomLayer()),
            int(t.GetViaType()),int(t.GetDrillValue()),
            tuple((int(l),int(t.GetWidth(l))) for l in b.GetEnabledLayers().CuStack()))
        return base
    for uid,t in old.items():
        tick();q=new[uid]
        if (dims(t,source)!=dims(q,candidate)
                or tuple(t.GetStart())!=tuple(q.GetStart()) or tuple(t.GetEnd())!=tuple(q.GetEnd())):
            raise ValueError('native_smd_macro_requires_unchanged_source_conductors')
    retained_entries={};retained_items=set();retention=[]
    if retained_ground_contacts:
        import cec_projected_ground_contact as contact
        import cec_cell_row_rebuild as row
        import json
        if (source_path is None or Path(source_path).resolve()!=Path(source.GetFileName()).resolve()
                or type(board_hint) is not str or not board_hint):
            raise ValueError('exact_saved_projected_ground_transport_context_required')
        binding=row._source_binding(source)
        live_pads={force._uid(p):p for fp in candidate.GetFootprints() for p in fp.Pads()}
        for proof in retained_ground_contacts:
            tick()
            if (type(proof) is not dict or proof.get('pad_uuid') in retained_entries
                    or proof.get('pad_uuid') not in live_pads or proof.get('source_native_binding')!=binding
                    or proof.get('source')!=str(Path(source_path).resolve()) or proof.get('board_hint')!=board_hint):
                raise ValueError('literal_unique_source_projected_ground_transport_proof_required')
            pad=live_pads[proof['pad_uuid']];fp=pad.GetParentFootprint();pose=proof['target_pose']
            if (force._uid(fp) not in moved or list(fp.GetPosition())!=[round(v*1e6) for v in pose[:2]]
                    or abs((fp.GetOrientationDegrees()-pose[2]+180)%360-180)>1e-9):
                raise ValueError('exact_moving_projected_ground_transport_pose_required')
            observed=contact.observe(candidate,pad,proof,timeout_s=max(.001,deadline-time.monotonic()))
            if observed is None:raise ValueError('projected_ground_transport_source_entry_not_live')
            retained_entries[proof['pad_uuid']]=tuple(proof['source_entry_nm'])
            retained_items.update(proof['source_entry_native_uuids']);retained_items.add(proof['source_reference_via']['uuid'])
            retention.append(dict(proposal=json.loads(json.dumps(proof)),before_transport=observed))
    import cec_stationary_ground_barrel as stationary_ground
    stationary_proofs=stationary_ground.plan(source,stationary_ground_barrel_uuids,
        source_path=source_path,board_hint=board_hint,timeout_s=max(.001,deadline-time.monotonic()))
    for proof in stationary_proofs:
        uid=proof['source_reference_via']['uuid']
        if uid in retained_items:raise ValueError('stationary_ground_barrel_has_duplicate_retention_authority')
        retained_items.add(uid)
    reused=[]
    if reused_ground_barrel_contacts:
        import cec_projected_ground_contact as contact
        import cec_cell_row_rebuild as row
        import json
        if (source_path is None or Path(source_path).resolve()!=Path(source.GetFileName()).resolve()
                or type(board_hint) is not str or not board_hint):
            raise ValueError('exact_saved_ground_barrel_reuse_transport_context_required')
        binding=row._source_binding(source)
        live_pads={force._uid(p):p for fp in candidate.GetFootprints() for p in fp.Pads()}
        seen_pads=set()
        for proof in reused_ground_barrel_contacts:
            tick()
            if (type(proof) is not dict or proof.get('pad_uuid') not in live_pads
                    or proof.get('pad_uuid') in seen_pads or proof.get('pad_uuid') in retained_entries
                    or proof.get('source_native_binding')!=binding
                    or proof.get('source')!=str(Path(source_path).resolve()) or proof.get('board_hint')!=board_hint
                    or proof.get('source_reference_via',{}).get('uuid') in retained_items):
                raise ValueError('unique_literal_ground_barrel_reuse_transport_proof_required')
            pad=live_pads[proof['pad_uuid']]
            if force._uid(pad.GetParentFootprint()) not in moved:
                raise ValueError('actual_moving_ground_barrel_reuse_owner_required')
            observed=contact.observe_barrel_reuse(candidate,pad,proof,timeout_s=max(.001,deadline-time.monotonic()))
            if observed is None:raise ValueError('stationary_ground_barrel_reuse_not_live')
            seen_pads.add(proof['pad_uuid']);retained_items.add(proof['source_reference_via']['uuid'])
            reused.append(dict(proposal=json.loads(json.dumps(proof)),before_transport=observed))
    def pad_point_shift(p,at,owner):
        # A moved package need not move a full-width entry still contained
        # in its independently projected land. Only this EXACT source axis
        # is fixed; other points and all other terminal obligations remain.
        if retained_entries.get(force._uid(p))==tuple(at):return (0,0)
        return point_shift(at,owner)
    def one_shift(matches,label):
        ds={row[1] for row in matches}
        if len(ds)>1:raise ValueError('native_smd_macro_ambiguous_'+label)
        return next(iter(ds),(0,0))
    via_moves={};via_proofs=[];owned_dogbones=set();via_owners={};dogbone_owners={}
    stationary_other_barrels=[]
    tracks=[t for t in old.values() if t.GetClass()=='PCB_TRACK']
    native_pads=[]
    for p,d,o in pads:
        if p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD:continue
        bb=p.GetBoundingBox()
        native_pads.append((p,d,o,(bb.GetLeft(),bb.GetTop(),bb.GetRight(),bb.GetBottom())))
    for uid,v in old.items():
        tick()
        if v.GetClass()!='PCB_VIA':continue
        if uid in retained_items:continue
        in_pad=[];dogbone_matches=[];dogbone_rows=[];at=tuple(v.GetPosition())
        # Boxes only discard impossible owners. Every surviving proposal is
        # proved with complete native copper or an actual source dogbone.
        near=max(int(v.GetWidth(v.TopLayer()))//2,math.ceil(fab.LOCAL_POFV_REACH_MM*1e6))+5000
        tails=[t for t in tracks if t.GetNetCode()==v.GetNetCode()
            and any(math.dist(tuple(pt),at)<=5000 for pt in (t.GetStart(),t.GetEnd()))]
        for p,shift,owner,bb in native_pads:
            tick()
            if (p.GetNetCode()!=v.GetNetCode() or at[0]<bb[0]-near or at[0]>bb[2]+near
                    or at[1]<bb[1]-near or at[1]>bb[3]+near):continue
            faces=[int(l) for l in source.GetEnabledLayers().CuStack() if p.IsOnLayer(l)]
            if len(faces)!=1:continue
            lid=faces[0]
            if not v.IsOnLayer(lid):continue
            shift=point_shift(at,owner)
            poly=pcbnew.SHAPE_POLY_SET();v.TransformShapeToPolygon(poly,lid,0,1,pcbnew.ERROR_OUTSIDE)
            poly.BooleanSubtract(p.GetEffectivePolygon(lid,pcbnew.ERROR_INSIDE))
            if poly.OutlineCount()==0:
                in_pad.append((p,shift,owner));continue
            for t in tails:
                if t.GetNetCode()!=v.GetNetCode() or t.GetLayer()!=lid:continue
                for a,b in ((t.GetStart(),t.GetEnd()),(t.GetEnd(),t.GetStart())):
                    if (math.dist(tuple(b),tuple(v.GetPosition()))<=5000
                            and fab.local_pofv_dogbone_matches(p,a,b,lid,v.GetNetCode())):
                        dogbone_matches.append((p,shift,owner))
                        dogbone_rows.append((force._uid(t),owner));break
        # Complete native in-pad containment owns a plated axis. A short
        # trace to another component is a boundary, not a second barrel
        # owner. Do not rigidly drag that inter-owner trace with the cap;
        # its two actual source endpoints are transported independently.
        # Multiple disagreeing in-pad owners remain an explicit refusal.
        matches=in_pad if in_pad else dogbone_matches
        chosen_owners={q[2] for q in matches}
        dogbones=[u for u,o in dogbone_rows if not in_pad and o in chosen_owners]
        shift=one_shift(matches,'barrel_owner')
        if shift==(0,0):continue
        if carry_ground_barrels_only and v.GetNetname()!='GND':
            # A retained-trace passive move must not implicitly drag its
            # incoming supply/signal transition. Preserve that axis exactly
            # and independently re-prove its SAME Source pad after the move.
            # A partial overlap or lost dogbone remains a real refusal.
            ok,reason=fab.local_pofv_via_decision(source,v)
            if not ok:raise ValueError('stationary_source_barrel_process_refused:'+uid+':'+reason)
            stationary_other_barrels.append(dict(uuid=uid,
                source_owner_pad_uuids=sorted({force._uid(q[0]) for q in matches}),
                original_position_nm=list(at),source_local_POFV_reproved=True))
            continue
        if math.hypot(*shift)>maximum_shift_mm*1e6:
            raise ValueError('native_smd_macro_owned_barrel_motion_bound')
        ok,reason=fab.local_pofv_via_decision(source,v)
        groups=[g for g in source.Groups() if g.ContainsItem(v)]
        if (not ok or groups and (len(groups)!=1 or groups[0].IsLocked()
                or groups[0].GetName()!=fr.LOCAL_POFV_SIGNAL_VIA_GROUP)):
            raise ValueError('native_smd_macro_barrel_has_no_movable_source_process_owner:'+uid+':'+reason)
        via_moves[uid]=shift;owned_dogbones.update(dogbones)
        owners={q[2] for q in matches}
        if len(owners)==1:
            via_owners[uid]=next(iter(owners))
            for dogbone in dogbones:dogbone_owners[dogbone]=next(iter(owners))
        via_proofs.append(dict(uuid=uid,source_owner_pad_uuids=sorted({force._uid(q[0]) for q in matches}),
            owner_footprint_uuids=sorted({q[2] for q in matches}),translation_nm=list(shift),
            actual_source_ownership_basis='complete_native_in_pad_containment' if in_pad else 'bounded_native_smd_dogbone',
            independently_reconstructed_inter_owner_dogbone_uuids=sorted({u for u,o in dogbone_rows if in_pad and o not in chosen_owners}),
            source_local_POFV_reproved=True,source_process_group_uuids=[force._uid(g) for g in groups]))
    import cec_inpad_ground_barrel_seats as ground_seats
    seated_ground=ground_seats.resolve(source,candidate,source_ground_barrel_seats,via_proofs,
        maximum_shift_nm=round(maximum_shift_mm*1e6),maximum_translation_mm=maximum_translation_mm,
        timeout_s=max(.001,deadline-time.monotonic()))
    for seat in seated_ground:
        via_moves[seat['uuid']]=tuple(seat['source_displacement_nm'])
        proof=next(row for row in via_proofs if row['uuid']==seat['uuid'])
        proof['rigid_owner_translation_nm']=proof['translation_nm']
        proof['translation_nm']=list(seat['source_displacement_nm'])
        proof['owner_relative_offset_nm']=list(seat['owner_relative_offset_nm'])
    seated_ground_ids={row['uuid'] for row in seated_ground}
    canonical_return_axes=[]
    if source_control_ground_return_axes:
        if (source_path is None or Path(source_path).resolve()!=Path(source.GetFileName()).resolve()
                or type(board_hint)is not str or not board_hint or not 1<=len(moved)<=8):
            raise ValueError('actual_Source_control_return_axis_context_required')
        import cec_control_shunt_ground_return_axes as return_axes
        actual_poses={old_fp[u].GetReference():[new_fp[u].GetPosition().x/1e6,
            new_fp[u].GetPosition().y/1e6,new_fp[u].GetOrientationDegrees()]for u in moved}
        canonical_return_axes=return_axes.derive(source,candidate,
            dict(poses=actual_poses,board_hint=board_hint,reference_group_uuids=reference_group_uuids),
            source_control_ground_return_axes,timeout_s=max(.001,deadline-time.monotonic()))
        local_signal_return_via_poses=[{k:q[k]for k in('uuid','owner_pad_uuid','position_nm')}for q in canonical_return_axes]
    canonical_axis_by_via={q['uuid']:q for q in canonical_return_axes}
    local_return_proofs=[]
    if local_signal_return_via_poses:
        import cec_ordinary_route_receiving as ordinary
        import cec_constraints as constraints
        if (type(local_signal_return_via_poses) not in (list,tuple)
                or not 1<=len(local_signal_return_via_poses)<=4 or source_path is None
                or Path(source_path).resolve()!=Path(source.GetFileName()).resolve()
                or type(board_hint) is not str or not board_hint):
            raise ValueError('exact_bounded_local_signal_return_reseat_context_required')
        signals=ordinary.eligible_nets(source,Path(source_path),board_hint);seen_returns=set()
        for q in local_signal_return_via_poses:
            tick()
            if (type(q) is not dict or set(q)!={'uuid','owner_pad_uuid','position_nm'}
                    or q['uuid'] not in old or q['uuid'] in seen_returns
                    or type(q['position_nm']) is not list or len(q['position_nm'])!=2
                    or any(type(n) is not int or abs(n)>2000000000 for n in q['position_nm'])):
                raise ValueError('unique_literal_local_signal_return_reseat_required')
            if q['uuid'] in retained_items:raise ValueError('retained_ground_contact_cannot_be_explicitly_reseated')
            seen_returns.add(q['uuid']);v=old[q['uuid']]
            owners=[p for p,_,_ in pads if force._uid(p)==q['owner_pad_uuid']]
            if len(owners)!=1:raise ValueError('actual_local_signal_return_owner_required')
            p=owners[0];fp=p.GetParentFootprint();members=list(fp.Pads())
            value=constraints._capacitance_f_board(fp.GetValue())
            axis=canonical_axis_by_via.get(q['uuid'])
            programming_axis=(axis is not None and 'source_programming_resistor'in axis
                and axis['owner_pad_uuid']==force._uid(p))
            # A fresh canonical role may carry exactly the same Source map
            # independently inspected and verified earlier in this call.
            # Merely naming a group never extends the legacy raw RC API.
            role=(axis.get('source_programming_resistor',axis.get('source_control_shunt'))
                if axis is not None and axis['owner_pad_uuid']==force._uid(p)else None)
            mapped_axis=(role is not None and force._uid(fp)in reference_owners
                and role.get('source_reference_group_authorization')==reference_owners[force._uid(fp)])
            ordinary_rc=bool(value and 0<value<=1e-6
                and len([z for z in members if str(z.GetNetname()) in signals])==1)
            if (v.GetClass()!='PCB_VIA' or str(v.GetNetname())!='GND' or str(p.GetNetname())!='GND'
                    or len(members)!=2 or not(ordinary_rc or programming_axis)
                    or fp.IsLocked() or fp.GetParentGroup() is not None and not mapped_axis
                    or any(z.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or z.HasHole() for z in members)
                    or not fab.local_pofv_via_decision(source,v)[0]):
                raise ValueError('existing_qualified_private_signal_rc_return_required')
            if q['uuid'] in via_moves:
                original_proof=next((r for r in via_proofs if r['uuid']==q['uuid']),None)
                if (original_proof is None or original_proof['source_owner_pad_uuids']!=[force._uid(p)]
                        or original_proof['owner_footprint_uuids']!=[force._uid(fp)]):
                    raise ValueError('local_return_reseat_cannot_override_another_owner_transform')
            groups=[g for g in source.Groups() if g.ContainsItem(v)]
            if any(g.GetName()!=fr.LOCAL_POFV_SIGNAL_VIA_GROUP or g.IsLocked() for g in groups):
                raise ValueError('source_local_signal_return_group_is_protected')
            incident=[t for u,t in old.items() if u!=q['uuid'] and t.GetNetname()==v.GetNetname()
                and any(t.IsOnLayer(l) and t.GetEffectiveShape(l).Collide(v.GetEffectiveShape(l),0)
                    for l in source.GetEnabledLayers().CuStack())]
            if (len(incident)!=1 or incident[0].GetClass()!='PCB_TRACK'
                    or incident[0].GetParentGroup() is not None
                    or not any(tuple(at)==tuple(v.GetPosition()) for at in (incident[0].GetStart(),incident[0].GetEnd()))
                    or not any(p.HitTest(at) for at in (incident[0].GetStart(),incident[0].GetEnd()))
                    or not 0<incident[0].GetLength()<=1500000):
                raise ValueError('unique_source_local_signal_return_dogbone_required')
            if any(z.GetNetname()==v.GetNetname() and force._uid(z)!=force._uid(p)
                and any(z.IsOnLayer(l) and z.GetEffectiveShape(l).Collide(v.GetEffectiveShape(l),0)
                    for l in source.GetEnabledLayers().CuStack()) for z,_,_ in pads):
                raise ValueError('source_local_signal_return_has_another_native_land_contact')
            shift=tuple(b-a for a,b in zip(tuple(v.GetPosition()),q['position_nm']))
            if not 0<math.hypot(*shift)<=maximum_local_return_shift_mm*1e6:
                raise ValueError('source_local_signal_return_reseat_motion_bound')
            before=math.dist(tuple(p.GetPosition()),tuple(v.GetPosition()))
            target_pad=next(z for z in new_fp[force._uid(fp)].Pads() if force._uid(z)==force._uid(p))
            after=math.dist(tuple(target_pad.GetPosition()),q['position_nm'])
            if not after+10000<before:raise ValueError('measured_local_signal_return_shortening_required')
            via_proofs=[r for r in via_proofs if r['uuid']!=q['uuid']]
            via_owners.pop(q['uuid'],None)
            via_moves[q['uuid']]=shift;owned_dogbones.add(force._uid(incident[0]))
            proof=dict(uuid=q['uuid'],owner_pad_uuid=force._uid(p),owner_footprint_uuid=force._uid(fp),
                translation_nm=list(shift),source_dogbone_uuid=force._uid(incident[0]),
                source_return_nm=round(before),proposed_return_nm=round(after),
                source_local_POFV_reproved=True,source_process_group_uuids=[force._uid(g) for g in groups],
                source_barrel_geometry_and_count_retained=True,current_capacity_not_inferred=True)
            local_return_proofs.append(proof)
    signal_port_proofs=[];relative_ports={}
    if type(local_signal_port_offsets) not in (list,tuple) or len(local_signal_port_offsets)>4:
        raise ValueError('bounded_explicit_owner_relative_signal_port_offsets_required')
    if local_signal_port_offsets:
        if type(local_signal_port_via_poses) not in (list,tuple):
            raise ValueError('explicit_disjoint_signal_port_pose_inventories_required')
        expanded=list(local_signal_port_via_poses)
        for request in local_signal_port_offsets:
            tick()
            if (type(request) is not dict or set(request) not in (
                        {'uuid','owner_pad_uuid','offset_nm'},
                        {'uuid','owner_pad_uuid','offset_nm','maximum_port_length_nm'})
                    or type(request['uuid']) is not str or request['uuid'] not in old
                    or request['uuid'] in relative_ports
                    or type(request['owner_pad_uuid']) is not str
                    or type(request['offset_nm']) is not list or len(request['offset_nm'])!=2
                    or any(type(v) is not int for v in request['offset_nm'])
                    or not 0<math.hypot(*request['offset_nm'])<=maximum_local_signal_port_shift_mm*1e6):
                raise ValueError('unique_bounded_owner_relative_signal_port_offset_required')
            length_limit=request.get('maximum_port_length_nm')
            if 'maximum_port_length_nm' in request and (type(length_limit) is not int
                    or not 0<length_limit<=round(fab.LOCAL_POFV_REACH_MM*1e6)):
                raise ValueError('explicit_signal_escape_length_cannot_exceed_existing_process_reach')
            owned=next((q for q in via_proofs if q['uuid']==request['uuid']),None)
            if (owned is None or owned['source_owner_pad_uuids']!=[request['owner_pad_uuid']]
                    or len(owned['owner_footprint_uuids'])!=1):
                raise ValueError('relative_signal_port_requires_unique_transported_source_owner')
            via=old[request['uuid']];owner=owned['owner_footprint_uuids'][0]
            rigid=tuple(v+d for v,d in zip(tuple(via.GetPosition()),point_shift(tuple(via.GetPosition()),owner)))
            relative_ports[request['uuid']]=dict(rigid_source_barrel_target_nm=list(rigid),
                owner_relative_correction_nm=list(request['offset_nm']))
            if length_limit is not None:
                relative_ports[request['uuid']]['maximum_port_length_nm']=length_limit
            expanded.append(dict(uuid=request['uuid'],owner_pad_uuid=request['owner_pad_uuid'],
                position_nm=[v+d for v,d in zip(rigid,request['offset_nm'])]))
        local_signal_port_via_poses=expanded
    if local_signal_port_via_poses:
        import cec_ordinary_route_receiving as ordinary
        if (type(local_signal_port_via_poses) not in (list,tuple)
                or not 1<=len(local_signal_port_via_poses)<=4 or source_path is None
                or Path(source_path).resolve()!=Path(source.GetFileName()).resolve()
                or type(board_hint) is not str or not board_hint):
            raise ValueError('exact_bounded_local_signal_port_reseat_context_required')
        signals=ordinary.eligible_nets(source,Path(source_path),board_hint)
        seen_ports=set()
        for q in local_signal_port_via_poses:
            tick()
            if (type(q) is not dict or set(q)!={'uuid','owner_pad_uuid','position_nm'}
                    or q['uuid'] not in old or q['uuid'] in seen_ports
                    or type(q['position_nm']) is not list or len(q['position_nm'])!=2
                    or any(type(n) is not int or abs(n)>2000000000 for n in q['position_nm'])):
                raise ValueError('unique_literal_local_signal_port_reseat_required')
            if q['uuid'] in retained_items:raise ValueError('retained_ground_contact_cannot_be_explicitly_reseated')
            seen_ports.add(q['uuid']);v=old[q['uuid']]
            owned=next((r for r in via_proofs if r['uuid']==q['uuid']),None)
            owners=[p for p,_,_ in pads if force._uid(p)==q['owner_pad_uuid']]
            if len(owners)!=1:raise ValueError('actual_source_local_signal_port_owner_required')
            p=owners[0];fp=p.GetParentFootprint()
            if (owned is None or owned['actual_source_ownership_basis']!='bounded_native_smd_dogbone'
                    or owned['source_owner_pad_uuids']!=[force._uid(p)]
                    or owned['owner_footprint_uuids']!=[force._uid(fp)]
                    or force._uid(fp) not in moved or fp.IsLocked() or fp.GetParentGroup() is not None
                    or str(v.GetNetname()) not in signals or p.GetNetCode()!=v.GetNetCode()
                    or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole()
                    or not fab.local_pofv_via_decision(source,v)[0]):
                raise ValueError('positive_unique_moving_ordinary_smd_dogbone_owner_required')
            groups=[g for g in source.Groups() if g.ContainsItem(v)]
            if any(g.GetName()!=fr.LOCAL_POFV_SIGNAL_VIA_GROUP or g.IsLocked() for g in groups):
                raise ValueError('source_local_signal_port_group_is_protected')
            tails=[t for t in tracks if t.GetNetCode()==v.GetNetCode()
                and any(tuple(at)==tuple(v.GetPosition()) for at in (t.GetStart(),t.GetEnd()))
                and any(fab.local_pofv_dogbone_matches(p,a,b,t.GetLayer(),v.GetNetCode())
                    for a,b in ((t.GetStart(),t.GetEnd()),(t.GetEnd(),t.GetStart()))
                    if tuple(b)==tuple(v.GetPosition()))]
            if len(tails)!=1 or tails[0].GetParentGroup() is not None:
                raise ValueError('unique_ungrouped_source_local_signal_port_dogbone_required')
            shift=tuple(b-a for a,b in zip(tuple(v.GetPosition()),q['position_nm']))
            # An explicit relative correction is measured from the SAME
            # Source-owner rigid transform, not from the old board origin.
            # Keep the independent global movement limit as well. Historical
            # absolute requests retain their original local work bound.
            limit=maximum_shift_mm if q['uuid'] in relative_ports else maximum_local_signal_port_shift_mm
            if not 0<math.hypot(*shift)<=limit*1e6:
                raise ValueError('source_local_signal_port_reseat_motion_bound')
            target=next(z for z in new_fp[force._uid(fp)].Pads() if force._uid(z)==force._uid(p))
            before=math.dist(tuple(p.GetPosition()),tuple(v.GetPosition()))
            after=math.dist(tuple(target.GetPosition()),q['position_nm'])
            explicit_length=relative_ports.get(q['uuid'],{}).get('maximum_port_length_nm')
            if (not 0<after<=fab.LOCAL_POFV_REACH_MM*1e6
                    or explicit_length is None and not after+10000<before
                    or explicit_length is not None and after>explicit_length):
                raise ValueError('measured_nonempty_local_signal_port_shortening_required')
            # Only the source-proved private ordinary dogbone may change its
            # relative barrel seat. All other incident native endpoints are
            # transported by the same explicit axis; they still require
            # canonical reconstruction and complete saved-board receiving.
            via_proofs=[r for r in via_proofs if r['uuid']!=q['uuid']]
            via_owners.pop(q['uuid'],None)
            dogbone_owners.pop(force._uid(tails[0]),None)
            via_moves[q['uuid']]=shift;owned_dogbones.add(force._uid(tails[0]))
            signal_port_proofs.append(dict(uuid=q['uuid'],owner_pad_uuid=force._uid(p),
                owner_footprint_uuid=force._uid(fp),translation_nm=list(shift),
                source_dogbone_uuid=force._uid(tails[0]),source_port_length_nm=round(before),
                proposed_port_length_nm=round(after),source_local_POFV_reproved=True,
                source_process_group_uuids=[force._uid(g) for g in groups],
                source_barrel_geometry_and_count_retained=True,current_capacity_not_inferred=True))
            if q['uuid'] in relative_ports:signal_port_proofs[-1].update(relative_ports[q['uuid']])
    ordinary_proofs=[]
    if ordinary_via_poses:
        import cec_ordinary_route_receiving as ordinary
        if (type(ordinary_via_poses) not in (list,tuple) or not 1<=len(ordinary_via_poses)<=maximum_ordinary_vias
                or source_path is None or Path(source_path).resolve()!=Path(source.GetFileName()).resolve()
                or type(board_hint) is not str or not board_hint):
            raise ValueError('native_smd_macro_exact_ordinary_source_context_required')
        allowed=ordinary.eligible_nets(source,Path(source_path),board_hint);seen=set()
        for q in ordinary_via_poses:
            tick()
            if (type(q) is not dict or set(q)!={'uuid','position_nm'} or type(q['uuid']) is not str
                    or q['uuid'] in seen or q['uuid'] not in old or q['uuid'] in via_moves
                    or type(q['position_nm']) is not list or len(q['position_nm'])!=2
                    or any(type(n) is not int or abs(n)>2000000000 for n in q['position_nm'])):
                raise ValueError('native_smd_macro_unique_literal_ordinary_barrel_pose_required')
            if q['uuid'] in retained_items:raise ValueError('retained_ground_contact_cannot_be_explicitly_reseated')
            uid=q['uuid'];seen.add(uid);v=old[uid]
            if (v.GetClass()!='PCB_VIA' or v.GetParentGroup() is not None or str(v.GetNetname()) not in allowed
                    or v.GetViaType()!=pcbnew.VIATYPE_THROUGH or v.TopLayer()!=pcbnew.F_Cu or v.BottomLayer()!=pcbnew.B_Cu):
                raise ValueError('native_smd_macro_free_barrel_not_source_typed_ordinary')
            d,h=int(v.GetWidth(v.TopLayer())),int(v.GetDrillValue())
            rd,rh,_=fab.board_legal_through_via_geometry(source,d/1e6,h/1e6)
            if d<math.ceil(rd*1e6) or h<math.ceil(rh*1e6):
                raise ValueError('native_smd_macro_free_barrel_below_source_factory_floor')
            shift=tuple(b-a for a,b in zip(tuple(v.GetPosition()),q['position_nm']))
            if not 0<math.hypot(*shift)<=3000000:raise ValueError('native_smd_macro_free_barrel_motion_bound')
            peers=[]
            for p,_,_ in pads:
                if p.GetNetCode()==v.GetNetCode() and any(p.IsOnLayer(l)
                    and p.GetEffectiveShape(l).Collide(v.GetEffectiveShape(l),0) for l in source.GetEnabledLayers().CuStack()):
                    raise ValueError('native_smd_macro_free_barrel_has_actual_land_contact')
            for t in old.values():
                if force._uid(t)==uid or t.GetNetCode()!=v.GetNetCode():continue
                if not any(t.IsOnLayer(l) and t.GetEffectiveShape(l).Collide(v.GetEffectiveShape(l),0)
                    for l in source.GetEnabledLayers().CuStack()):continue
                if (t.GetClass()!='PCB_TRACK' or t.GetParentGroup() is not None
                        or not any(v.GetEffectiveShape(t.GetLayer()).Collide(at,0) for at in (t.GetStart(),t.GetEnd()))):
                    raise ValueError('native_smd_macro_free_barrel_hidden_or_protected_contact:'+uid+':'+force._uid(t)+':'+t.GetClass())
                peers.append(force._uid(t))
            if not 2<=len(peers)<=8:raise ValueError('native_smd_macro_free_barrel_bounded_live_stubs_required')
            if any(not z.GetIsRuleArea() and z.GetNetCode()==v.GetNetCode()
                and any(z.IsOnLayer(l) and (not z.IsFilled() or z.HasFilledPolysForLayer(l)
                    and z.GetFilledPolysList(l).Collide(v.GetEffectiveShape(l),0)) for l in source.GetEnabledLayers().CuStack())
                for z in source.Zones()):
                raise ValueError('native_smd_macro_free_barrel_has_source_pour_contact')
            via_moves[uid]=shift;ordinary_proofs.append(dict(uuid=uid,translation_nm=list(shift),
                source_typed_ordinary=True,actual_source_incident_track_uuids=sorted(peers),
                original_barrel_geometry_retained=True,new_routing_clearance_or_admission_not_granted=True))
    via_items=[(v,via_moves.get(uid,(0,0)),uid) for uid,v in old.items() if v.GetClass()=='PCB_VIA']
    stationary_axes={r['proposal']['source_reference_via']['uuid'] for r in reused}
    stationary_axes.update(r['source_reference_via']['uuid'] for r in stationary_proofs)
    pad_contacts=_endpoint_contact_index(source,pads)
    via_contacts=_endpoint_contact_index(source,via_items)
    stationary_neckdowns=[];stationary_wide_contacts=[];retained_source_debt_contacts=[];neckdown_context=None;neckdown_contracts={};dimension_contracts={}
    candidate_pads={force._uid(p):p for fp in candidate.GetFootprints() for p in fp.Pads()}
    def literal_source_floor(t):
        nonlocal neckdown_context
        import cec_cell_row_rebuild as row
        import cec_route_dimensions as dimensions
        import cec_current_topology as topology
        if neckdown_context is None:
            if source_path is None or type(board_hint) is not str or not board_hint:
                raise ValueError('native_smd_macro_stationary_contact_source_context_required')
            path=Path(source_path).resolve()
            if not path.is_file() or path!=Path(source.GetFileName()).resolve():
                raise ValueError('native_smd_macro_stationary_contact_literal_source_required')
            family=force._family(path,board_hint);saved=pcbnew.LoadBoard(str(path))
            if row._source_binding(saved)!=row._source_binding(source):
                raise ValueError('native_smd_macro_stationary_neckdown_requires_exact_saved_source')
            with force._thermal_hint(board_hint):
                domains=topology.board_current_domains(source,board_hint=board_hint)
            neckdown_context=(path,family,dimensions.project_resolver(path,board=source),domains)
        key=(str(t.GetNetname()),int(t.GetLayer()))
        if key not in dimension_contracts:
            path,family,resolver,domains=neckdown_context
            spec=resolver(key[0]) or {};layer=source.GetLayerName(t.GetLayer())
            with force._thermal_hint(board_hint):authority=topology.current_contract_for_net(key[0],board_hint,domains)
            rated=dimensions.current_trace_widths(authority,(layer,),fab.active_profile_name(source,hint=board_hint),rise_c=30.)[layer] if authority else 0
            full=math.ceil(max(float(spec.get('track_width') or 0),
                float((spec.get('track_width_by_layer_mm') or {}).get(layer) or 0),
                dimensions.board_limits(source)['track_width'],rated)*1e6)
            clearance=max(int(source.GetDesignSettings().m_MinClearance),math.ceil(float(spec.get('clearance') or 0)*1e6))
            dimension_contracts[key]=(full,clearance)
        return dimension_contracts[key]
    def retain_contained_wide_contact(t,points,ds):
        if (t.GetParentGroup() is not None or source_path is None
                or type(board_hint) is not str or not board_hint):return None
        carried=[]
        for at,delta in zip(points,ds):
            if not any(delta):continue
            if any(point_shift(at,o)!=(0,0) for p,_,o in
                    _endpoint_contacts(pad_contacts,t.GetNetCode(),t.GetLayer(),at)):return None
            actual=[v for v,_,_ in _endpoint_contacts(via_contacts,t.GetNetCode(),t.GetLayer(),at)
                if via_moves.get(force._uid(v),(0,0))!=(0,0)]
            if not actual:return None
            for v in actual:
                uid=force._uid(v)
                if not any(r['uuid']==uid for r in via_proofs):return None
                poly=pcbnew.SHAPE_POLY_SET();v.TransformShapeToPolygon(poly,t.GetLayer(),0,1,pcbnew.ERROR_OUTSIDE)
                poly.Move(pcbnew.VECTOR2I(*via_moves[uid]))
                copper=pcbnew.SHAPE_POLY_SET()
                t.TransformShapeToPolygon(copper,t.GetLayer(),0,1,pcbnew.ERROR_INSIDE)
                poly.BooleanSubtract(copper)
                if poly.OutlineCount():return None
                carried.append(uid)
        if not carried:return None
        full,clearance=literal_source_floor(t)
        if t.GetWidth()<full:return None
        return dict(uuid=force._uid(t),net=str(t.GetNetname()),layer=int(t.GetLayer()),
            full_width_floor_nm=full,carried_source_process_barrel_uuids=sorted(set(carried)),
            exact_unchanged_wide_source_copper_fully_contains_each_carried_barrel=True,
            current_qualified=False,release_authority=False)
    def retain_qualified_neckdown(t,points,ds):
        """Keep exact Source copper, never transport or ungroup an exception.

        A small package slide can leave its original endpoint in the same
        native land. Re-prove the complete real narrow component against the
        unchanged class/current floor on both boards. A carried Source
        in-pad barrel may reconnect through that SAME land, but an arbitrary
        moving barrel never grants retention. The final post-transport proof
        below catches a departing throat.
        """
        nonlocal neckdown_context
        groups=[g for g in source.Groups() if g.ContainsItem(t)]
        group=groups[0] if len(groups)==1 else None
        if (group is None or group.GetName()!=fr.ENDPOINT_NECKDOWN_GROUP
                or group.IsLocked() or source_path is None
                or type(board_hint) is not str or not board_hint):return None
        path=Path(source_path).resolve()
        if not path.is_file() or path!=Path(source.GetFileName()).resolve():return None
        contacts=[];carried=[]
        for at,delta in zip(points,ds):
            if not any(delta):continue
            actual=_endpoint_contacts(pad_contacts,t.GetNetCode(),t.GetLayer(),at)
            if not actual:return None
            for p,_,owner in actual:
                q=candidate_pads[force._uid(p)]
                if not q.IsOnLayer(t.GetLayer()) or not q.GetEffectiveShape(t.GetLayer()).Collide(pcbnew.VECTOR2I(*at),0):
                    return None
                contacts.append(dict(pad_uuid=force._uid(p),at_nm=list(at)))
            for v,_,_ in _endpoint_contacts(via_contacts,t.GetNetCode(),t.GetLayer(),at):
                vid=force._uid(v);shift=via_moves.get(vid,(0,0))
                if shift==(0,0):continue
                proof=next((q for q in via_proofs if q['uuid']==vid
                    and q['actual_source_ownership_basis']=='complete_native_in_pad_containment'),None)
                if proof is None:return None
                owners={force._uid(p) for p,_,_ in actual}&set(proof['source_owner_pad_uuids'])
                contained=[]
                for puid in sorted(owners):
                    poly=pcbnew.SHAPE_POLY_SET()
                    v.TransformShapeToPolygon(poly,t.GetLayer(),0,1,pcbnew.ERROR_OUTSIDE)
                    poly.Move(pcbnew.VECTOR2I(*shift))
                    poly.BooleanSubtract(candidate_pads[puid].GetEffectivePolygon(t.GetLayer(),pcbnew.ERROR_INSIDE))
                    if not poly.OutlineCount():contained.append(puid)
                if not contained:return None
                carried.append(dict(uuid=vid,same_source_and_projected_owner_pad_uuids=contained,
                    complete_projected_in_pad_barrel_containment=True))
        if not contacts:return None
        key=(str(t.GetNetname()),int(t.GetLayer()),force._uid(group))
        if key not in neckdown_contracts:
            full,clearance=literal_source_floor(t)
            cohort=[item for item in group.GetItems() if item.GetClass()=='PCB_TRACK'
                and item.GetNetCode()==t.GetNetCode() and item.GetLayer()==t.GetLayer()]
            if not 1<=len(cohort)<=maximum_conductors:return None
            ids={force._uid(item) for item in cohort}
            before,_=fr._qualified_endpoint_neckdown_tracks(source,cohort,full,required_clearance=clearance)
            after,_=fr._qualified_endpoint_neckdown_tracks(candidate,[new[u] for u in ids],full,required_clearance=clearance)
            neckdown_contracts[key]=(ids,full,clearance,
                {force._uid(item) for item in before}&{force._uid(item) for item in after})
        ids,full,clearance,qualified=neckdown_contracts[key]
        if force._uid(t) not in qualified:return None
        return dict(uuid=force._uid(t),group_uuid=force._uid(group),net=key[0],layer=key[1],
            source_and_projected_pad_contacts=contacts,full_width_floor_nm=full,
            source_owned_barrels_carried_within_same_land=carried,
            required_clearance_nm=clearance,source_group_cohort_uuids=sorted(ids),
            original_copper_group_width_and_throat_retained=True,
            original_track_lock_retained=bool(t.IsLocked()),
            source_and_projected_neckdown_geometry_reproved=True,
            current_qualified=False,release_authority=False)
    ground_endpoint_cuts=[]
    if rebuild_source_ground_endpoints:
        import cec_source_ground_endpoint_cut as endpoint_cut
        ground_endpoint_cuts=endpoint_cut.plan(source,candidate,source_floor=literal_source_floor,
            allow_locked=allow_owned_locked_ground_endpoints,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    endpoint_retirements={u for q in ground_endpoint_cuts for u in q['retired_track_uuids']}
    fixed_ground_throats={u for q in ground_endpoint_cuts for u in q['retained_throat_track_uuids']}
    supply_endpoint_cuts=[];isolated_supply=[];isolated_strokes={}
    if rebuild_source_supply_endpoints:
        import cec_source_supply_endpoint_cut as supply_cut
        isolated_supply=supply_cut.isolated_components(source,candidate,board_hint=board_hint,
            source_floor=literal_source_floor,allow_locked=allow_owned_locked_ground_endpoints,
            allow_cardinal_rotations=allow_cardinal_rotations,
            defer_independent_endpoint_reconstruction=True,
            source_rc_input_prefixes=source_rc_input_prefixes,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        isolated_strokes={r['uuid']:(q,r)for q in isolated_supply for r in q['tracks']}
        supply_endpoint_cuts=supply_cut.plan(source,candidate,board_hint=board_hint,
            source_floor=literal_source_floor,allow_locked=allow_owned_locked_ground_endpoints,
            isolated_component_track_uuids=tuple(isolated_strokes),
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        endpoint_retirements|={u for q in supply_endpoint_cuts for u in q['retired_track_uuids']}
        fixed_ground_throats|={u for q in supply_endpoint_cuts for u in q['retained_throat_track_uuids']}
        if set(isolated_strokes)&(endpoint_retirements|fixed_ground_throats):
            raise ValueError('isolated_supply_transport_overlaps_endpoint_cut_or_fixed_throat')
    retained_supply_throats=[]
    if supply_endpoint_cuts:
        retained_supply_throats=supply_cut.retained_throat_contacts(source,candidate,supply_endpoint_cuts,
            board_hint=board_hint,moving_via_uuids=[u for u,d in via_moves.items()if any(d)],
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    retained_supply_throat_ids={q['uuid']for q in retained_supply_throats}
    proposals=[]
    for uid,t in old.items():
        tick()
        if uid in retained_supply_throat_ids:continue
        if uid in isolated_strokes:
            proof,stroke=isolated_strokes[uid]
            owners=sorted({force._uid(p.GetParentFootprint())for f in source.GetFootprints()
                for p in f.Pads()if force._uid(p)in proof['supply_pad_uuids']})
            proposals.append(dict(uuid=uid,source_nm=stroke['source_nm'],candidate_nm=stroke['candidate_nm'],
                net=str(t.GetNetname()),source_dimensions_and_groups_retained=True,
                source_endpoint_owner_footprint_uuids=[owners,owners],
                endpoint_has_explicit_nonfootprint_motion=[False,False],
                provisional_boundary_reconstruction_required=False))
            continue
        # These exact, positively source-qualified leads are not stretched
        # or unlocked.  The enclosing complete compiler MUST retire them
        # and reconstruct all old partitions plus the new physical return.
        if uid in endpoint_retirements:continue
        # An explicit zero-cut placement portfolio may carry only qualified
        # Source barrels. Never drag a priority trace merely because its old
        # endpoint was inside a moved pad. The enclosing saved receiver must
        # still prove every original native partition and all clearances.
        if retain_source_tracks and t.GetClass() in ('PCB_TRACK','PCB_ARC'):continue
        if t.GetClass()=='PCB_VIA':
            shift=via_moves.get(uid,(0,0));points=[tuple(t.GetPosition())];ds=[shift]
            motion_owners=[sorted({o for q in via_proofs if q['uuid']==uid
                for o in q['owner_footprint_uuids']})]
            unowned_motion=[bool(shift!=(0,0) and not motion_owners[0])]
        elif t.GetClass()=='PCB_TRACK':
            points=[tuple(t.GetStart()),tuple(t.GetEnd())];ds=[];motion_owners=[];unowned_motion=[]
            for at in points:
                pt=pcbnew.VECTOR2I(*at)
                contacts=_endpoint_contacts(via_contacts,t.GetNetCode(),t.GetLayer(),at)
                matches=[(p,pad_point_shift(p,at,o),o) for p,d,o in
                    _endpoint_contacts(pad_contacts,t.GetNetCode(),t.GetLayer(),at)]
                stationary=[(v,(0,0),o) for v,d,o in contacts if o in retained_items
                    and o in stationary_axes
                    and tuple(v.GetPosition())==tuple(at)]
                # This exact proved barrel axis stays put even when its
                # former land moves away. That old terminal is a separate
                # mandatory Ground-restoration obligation, not permission
                # to drag the shared hole or waive the old connection.
                if stationary:matches=stationary
                matches.extend((v,point_shift(at,via_owners[o]) if o in via_owners else d,o)
                    for v,d,o in contacts)
                ds.append(one_shift(matches,'endpoint_contact'))
                owned={o if o in transforms else via_owners.get(o) for _,d,o in matches if d!=(0,0)}
                motion_owners.append(sorted(o for o in owned if o is not None))
                unowned_motion.append(bool(ds[-1]!=(0,0) and None in owned))
            rigid_dogbone=(uid in dogbone_owners and all(d==point_shift(at,dogbone_owners[uid])
                for at,d in zip(points,ds)))
            if any(d!=(0,0) for d in ds) and t.GetParentGroup() is None:
                retained=retain_contained_wide_contact(t,points,ds)
                if retained is not None:
                    stationary_wide_contacts.append(retained)
                    ds=[(0,0),(0,0)];motion_owners=[[],[]];unowned_motion=[False,False]
            if any(d!=(0,0) for d in ds) and t.GetParentGroup() is not None:
                import cec_retained_fullwidth_supply_contact as full_contact
                retained=full_contact.plan(source,candidate,track_uuid=uid,board_hint=board_hint,
                    source_floor=literal_source_floor,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                if retained is not None:
                    stationary_wide_contacts.append(retained)
                    ds=[(0,0),(0,0)];motion_owners=[[],[]];unowned_motion=[False,False]
            if any(d!=(0,0) for d in ds) and t.GetParentGroup() is not None:
                import cec_retained_source_supply_contact as retained_debt
                retained=retained_debt.plan(source,candidate,track_uuid=uid,board_hint=board_hint,
                    source_floor=literal_source_floor,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
                if retained is not None:
                    retained_source_debt_contacts.append(retained)
                    ds=[(0,0),(0,0)];motion_owners=[[],[]];unowned_motion=[False,False]
            if any(d!=(0,0) for d in ds) and t.GetParentGroup() is not None:
                retained=retain_qualified_neckdown(t,points,ds)
                if retained is not None:
                    stationary_neckdowns.append(retained)
                    ds=[(0,0),(0,0)];motion_owners=[[],[]];unowned_motion=[False,False]
            if any(d!=(0,0) for d in ds) and t.GetParentGroup() is not None:
                if uid not in owned_dogbones or len(set(ds))!=1 and not rigid_dogbone:
                    raise ValueError('native_smd_macro_arbitrary_grouped_route_is_immutable')
        else:continue
        if uid in retained_items and any(d!=(0,0) for d in ds):
            raise ValueError('native_smd_macro_retained_ground_anchor_has_conflicting_endpoint_motion')
        if not any(d!=(0,0) for d in ds):continue
        targets=[tuple(v+d for v,d in zip(at,shift)) for at,shift in zip(points,ds)]
        if len(targets)==2 and targets[0]==targets[1]:raise ValueError('native_smd_macro_empty_boundary_seed')
        proposals.append(dict(uuid=uid,source_nm=points,candidate_nm=targets,
            net=str(t.GetNetname()),source_dimensions_and_groups_retained=True,
            source_endpoint_owner_footprint_uuids=motion_owners,
            endpoint_has_explicit_nonfootprint_motion=unowned_motion,
            provisional_boundary_reconstruction_required=(len(targets)==2
                and (ds[0]!=ds[1] and not rigid_dogbone or not quality.is_canonical_stroke(*targets)))))
    if any(q['uuid'] in fixed_ground_throats for q in proposals):
        raise ValueError('source_ground_endpoint_full_width_throat_must_remain_fixed')
    if not (0 if retention or reused or retain_source_tracks or endpoint_retirements else 1)<=len(proposals)<=maximum_conductors:
        raise ValueError('native_smd_macro_changed_conductor_budget')
    def pose(t,points):
        if t.GetClass()=='PCB_VIA':t.SetPosition(pcbnew.VECTOR2I(*points[0]))
        else:t.SetStart(pcbnew.VECTOR2I(*points[0]));t.SetEnd(pcbnew.VECTOR2I(*points[1]))
    try:
        for r in proposals:pose(new[r['uuid']],r['candidate_nm'])
        for r in retained_source_debt_contacts:
            tick()
            import cec_retained_source_supply_contact as retained_debt
            final=retained_debt.plan(source,candidate,track_uuid=r['uuid'],board_hint=board_hint,
                source_floor=literal_source_floor,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            if final is None:raise ValueError('retained_source_supply_contact_or_group_changed_after_transport')
            r['after_complete_transport_independently_reproved']=True
        for r in stationary_wide_contacts:
            if not r.get('common_source_and_projected_same_pad_native_core'):continue
            tick()
            import cec_retained_fullwidth_supply_contact as full_contact
            final=full_contact.plan(source,candidate,track_uuid=r['uuid'],board_hint=board_hint,
                source_floor=literal_source_floor,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
            if final is None:raise ValueError('retained_fullwidth_source_group_contact_changed_after_transport')
            r['after_complete_transport_independently_reproved']=True
        for r in stationary_other_barrels:
            tick();v=new[r['uuid']]
            ok,reason=fab.local_pofv_via_decision(candidate,v)
            if not ok:raise ValueError('stationary_source_barrel_destination_POFV_refused:'+r['uuid']+':'+reason)
            owners=[p for f in candidate.GetFootprints() for p in f.Pads()
                if force._uid(p) in r['source_owner_pad_uuids']]
            same_owner=False
            for pad in owners:
                for lid in candidate.GetEnabledLayers().CuStack():
                    if not pad.IsOnLayer(lid):continue
                    poly=pcbnew.SHAPE_POLY_SET()
                    v.TransformShapeToPolygon(poly,lid,0,1,pcbnew.ERROR_OUTSIDE)
                    poly.BooleanSubtract(pad.GetEffectivePolygon(lid,pcbnew.ERROR_INSIDE))
                    if not poly.OutlineCount():same_owner=True
                    for t in tracks:
                        if t.GetLayer()!=lid or t.GetNetCode()!=pad.GetNetCode():continue
                        if any(math.dist(tuple(b),tuple(v.GetPosition()))<=5000
                                and fab.local_pofv_dogbone_matches(pad,a,b,lid,v.GetNetCode())
                                for a,b in ((t.GetStart(),t.GetEnd()),(t.GetEnd(),t.GetStart()))):
                            same_owner=True
            if not same_owner:raise ValueError('stationary_source_barrel_same_native_owner_lost:'+r['uuid'])
            r.update(candidate_local_POFV_reproved=True,same_source_native_owner_reproved=True,
                native_axis_and_dimensions_unchanged=True)
        for r in [*via_proofs,*local_return_proofs,*signal_port_proofs]:
            tick();ok,reason=fab.local_pofv_via_decision(candidate,new[r['uuid']])
            if not ok:raise ValueError('native_smd_macro_destination_POFV_refused:'+r['uuid']+':'+reason)
            if r in signal_port_proofs:
                owner=next(p for f in candidate.GetFootprints() for p in f.Pads() if force._uid(p)==r['owner_pad_uuid'])
                leg=new[r['source_dogbone_uuid']];via=new[r['uuid']]
                faces=[l for l in candidate.GetEnabledLayers().CuStack() if owner.IsOnLayer(l)]
                if len(faces)!=1:raise ValueError('same_native_local_signal_port_surface_not_reproved')
                poly=pcbnew.SHAPE_POLY_SET();via.TransformShapeToPolygon(poly,faces[0],0,1,pcbnew.ERROR_OUTSIDE)
                poly.BooleanSubtract(owner.GetEffectivePolygon(faces[0],pcbnew.ERROR_INSIDE))
                if poly.OutlineCount() and not any(fab.local_pofv_dogbone_matches(owner,a,b,faces[0],owner.GetNetCode())
                    for a,b in ((leg.GetStart(),leg.GetEnd()),(leg.GetEnd(),leg.GetStart())) if tuple(b)==tuple(via.GetPosition())):
                    raise ValueError('same_native_signal_port_owner_and_dogbone_not_reproved')
            if r in local_return_proofs:
                owner=next(p for f in candidate.GetFootprints() for p in f.Pads() if force._uid(p)==r['owner_pad_uuid'])
                leg=new[r['source_dogbone_uuid']];via=new[r['uuid']];faces=[l for l in candidate.GetEnabledLayers().CuStack() if owner.IsOnLayer(l)]
                contained=False
                if len(faces)==1:
                    poly=pcbnew.SHAPE_POLY_SET();via.TransformShapeToPolygon(poly,faces[0],0,1,pcbnew.ERROR_OUTSIDE)
                    poly.BooleanSubtract(owner.GetEffectivePolygon(faces[0],pcbnew.ERROR_INSIDE));contained=not poly.OutlineCount()
                if len(faces)!=1 or not (contained or any(fab.local_pofv_dogbone_matches(owner,a,b,faces[0],owner.GetNetCode())
                    for a,b in ((leg.GetStart(),leg.GetEnd()),(leg.GetEnd(),leg.GetStart())) if tuple(b)==tuple(via.GetPosition()))):
                    raise ValueError('same_native_signal_return_owner_and_dogbone_not_reproved')
            r.update(candidate_local_POFV_reproved=True)
            if r in via_proofs:
                r['original_barrel_geometry_count_and_relative_owner_seat_preserved']=r['uuid'] not in seated_ground_ids
                if r['uuid'] in seated_ground_ids:
                    r['original_barrel_geometry_and_count_preserved']=True
                    r['explicitly_received_same_pad_ground_seat']=True
            else:
                r.update(original_barrel_geometry_and_count_preserved=True,
                    source_owner_identity_preserved=True,relative_owner_seat_preserved=False)
        for r in retention:
            tick();pad=live_pads[r['proposal']['pad_uuid']]
            observed=contact.observe(candidate,pad,r['proposal'],timeout_s=max(.001,deadline-time.monotonic()))
            if observed is None:raise ValueError('retained_ground_contact_lost_after_complete_native_transport')
            r['after_complete_transport']=observed
        for r in reused:
            tick();pad=live_pads[r['proposal']['pad_uuid']]
            observed=contact.observe_barrel_reuse(candidate,pad,r['proposal'],timeout_s=max(.001,deadline-time.monotonic()))
            if observed is None:raise ValueError('stationary_ground_barrel_reuse_lost_after_transport')
            r['after_complete_transport']=observed
        for r in stationary_neckdowns:
            tick()
            qualified,_=fr._qualified_endpoint_neckdown_tracks(candidate,
                [new[u] for u in r['source_group_cohort_uuids']],r['full_width_floor_nm'],
                required_clearance=r['required_clearance_nm'])
            if r['uuid'] not in {force._uid(item) for item in qualified}:
                raise ValueError('native_smd_macro_stationary_neckdown_throat_lost_after_transport')
            r['after_complete_transport_neckdown_geometry_reproved']=True
        if neckdown_context is not None and force._family(neckdown_context[0],board_hint)!=neckdown_context[1]:
            raise ValueError('native_smd_macro_stationary_neckdown_source_family_changed')
        if isolated_supply:
            isolated_supply=supply_cut.verify_isolated_components(source,candidate,isolated_supply,board_hint=board_hint,
                source_floor=literal_source_floor,allow_locked=allow_owned_locked_ground_endpoints,
                allow_cardinal_rotations=allow_cardinal_rotations,
                defer_independent_endpoint_reconstruction=True,
                source_rc_input_prefixes=source_rc_input_prefixes,
                timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    except Exception:
        for r in proposals:pose(new[r['uuid']],r['source_nm'])
        raise
    result=dict(schema=1,scope='provisional_source_owned_smd_cohort_endpoint_transport',
        changes=proposals,source_process_barrel_motion=via_proofs,
        explicit_source_typed_ordinary_barrel_motion=ordinary_proofs,
        explicitly_reproved_private_signal_return_reseats=local_return_proofs,
        explicitly_reproved_private_signal_port_reseats=signal_port_proofs,
        moved_owner_footprint_uuids=sorted(moved),
        source_owner_cardinal_transforms={u:{k:v for k,v in r.items() if k not in ('cos','sin')}
            for u,r in transforms.items() if 'cardinal_turn_deg' in r},
        transient_rebuild_required_uuids=[q['uuid'] for q in proposals if q['provisional_boundary_reconstruction_required']],
        all_source_dimensions_and_identities_retained=True,new_barrels_created=0,
        native_boundary_connectivity_and_clearance_not_yet_received=True,
        source_current_reduced=False,current_qualified=False,
        saved_candidate_authorized=False,routing_admitted=False,release_authority=False)
    if retained_supply_throats:
        result['retained_source_supply_endpoint_throats']=retained_supply_throats
    diagonal={u:{k:v for k,v in r.items() if k not in ('cos','sin')}
        for u,r in transforms.items() if 'octilinear_turn_deg' in r}
    if diagonal:
        result['source_owner_octilinear_transforms']=diagonal
        result['explicit_octilinear_native_poses']=True
    if retention:
        result.update(independently_retained_projected_ground_contacts=retention,
            retained_projected_ground_native_uuids=sorted(retained_items))
    if reused:
        result.update(independently_reused_stationary_ground_barrels=reused,
            reused_stationary_ground_barrel_uuids=sorted(r['proposal']['source_reference_via']['uuid'] for r in reused))
    if stationary_proofs:
        result['explicit_stationary_source_ground_barrels']=stationary_proofs
    if stationary_neckdowns:
        result['independently_retained_source_endpoint_neckdowns']=stationary_neckdowns
    if ground_endpoint_cuts:
        result['source_ground_endpoint_restoration_cuts']=ground_endpoint_cuts
    if supply_endpoint_cuts:
        result['source_supply_endpoint_restoration_cuts']=supply_endpoint_cuts
    if isolated_supply:
        result['rigid_isolated_selected_bypass_supply_components']=isolated_supply
    if stationary_wide_contacts:
        result['independently_retained_wide_source_via_contacts']=stationary_wide_contacts
    if retained_source_debt_contacts:
        result['independently_retained_source_supply_contacts_with_unqualified_debt']=retained_source_debt_contacts
    if retain_source_tracks:
        result['all_source_tracks_and_arcs_retained_exactly']=True
    if carry_ground_barrels_only:
        result['only_source_ground_barrels_may_move']=True
        result['stationary_non_ground_barrels']=stationary_other_barrels
    if seated_ground:
        result['source_ground_inpad_seats']=seated_ground
    if maximum_translation_mm!=64.:
        result['explicit_maximum_translation_work_mm']=maximum_translation_mm
    if canonical_return_axes:return_axes.apply_and_promote(result,canonical_return_axes)
    return result
