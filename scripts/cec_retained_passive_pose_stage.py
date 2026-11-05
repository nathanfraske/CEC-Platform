"""Saved, bounded grounded-passive poses with every Source stroke retained.

The request specifies poses, not copper ownership, roles or current ratings.
The independent receiver reconstructs Source-owned Ground barrels, exact
annotation associations and all original native partitions. No IC motion,
track cut, new conductor, outline growth or routing/release authority.
"""
import json
import math
import re
from pathlib import Path
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_pose_additive_reconstruction as pose_receiving
import cec_smd_macro_transport as transport


def plan(source, poses, *, board_hint, reference_group_uuids=(),max_shift_mm=6.,
         allow_source_ground_barrel_motion=True,allow_cardinal_reference_maps=False,
         retain_projected_ground_entries=False):
    if (type(poses)is not dict or not 1<=len(poses)<=8
            or type(board_hint)is not str or not board_hint
            or type(reference_group_uuids)not in(list,tuple)
            or len(reference_group_uuids)>8
            or any(type(u)is not str or not u for u in reference_group_uuids)
            or len(set(reference_group_uuids))!=len(reference_group_uuids)
            or type(max_shift_mm)not in(int,float)or not math.isfinite(max_shift_mm)
            or not 0<max_shift_mm<=32.
            or type(allow_source_ground_barrel_motion)is not bool
            or type(allow_cardinal_reference_maps)is not bool
            or type(retain_projected_ground_entries)is not bool
            or retain_projected_ground_entries and not allow_source_ground_barrel_motion
            or allow_cardinal_reference_maps and (
                not allow_source_ground_barrel_motion or not reference_group_uuids)
            or allow_source_ground_barrel_motion and max_shift_mm>6.
            or not allow_source_ground_barrel_motion and reference_group_uuids):
        raise ValueError('finite_explicit_retained_passive_pose_request_required')
    deadline=time.monotonic()+10.
    source=Path(source).resolve(strict=True)
    family=force._family(source,board_hint);code=force._code_identity()
    board=pcbnew.LoadBoard(str(source));chosen=[];actual_movement=False
    literal_grouped=set()
    if not allow_source_ground_barrel_motion:
        # KiCad can retain a literal group member that its SWIG group API
        # does not resolve (notably footprint-owned pads). Native load is
        # not permission to discard that saved ownership boundary.
        import cec_source_literal_additions as lex
        import cec_source_retaining_ses_import as literal
        inventory,*_=lex._inventory(literal.raw_text(source))
        literal_grouped={member for _,_,node in inventory.values()
            if literal.kind(node)=='group'for member in lex._members(node)[1]}
    for ref,target in sorted(poses.items()):
        if (type(ref)is not str or not ref or type(target)not in(list,tuple)
                or len(target)!=3 or any(type(v)not in(int,float) or not math.isfinite(v) for v in target)):
            raise ValueError('finite_literal_native_passive_pose_required')
        fp=board.FindFootprintByReference(ref)
        if fp is None:raise ValueError('existing_Source_passive_required')
        delta=math.dist(tuple(fp.GetPosition()),tuple(round(v*1e6)for v in target[:2]))/1e6
        turn=(target[2]-fp.GetOrientationDegrees())%360
        if delta>max_shift_mm or turn not in(0.,90.,180.,270.):
            raise ValueError('bounded_cardinal_retained_passive_pose_required')
        if not allow_source_ground_barrel_motion:
            # A larger explicit placement-work radius is not authority to
            # carry copper or disconnect a return. This distinct mode owns
            # only genuinely isolated, value-qualified grounded ceramics.
            # The original attached-barrel tier remains limited to 6 mm.
            import cec_device_bypass as bypass
            import cec_detached_ordinary_passive_translation as detached
            pads=list(fp.Pads())
            grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
            copper_faces=set(map(int,board.GetEnabledLayers().CuStack()))
            if (fp.IsLocked()or fp.IsDNP()or fp.GetParentGroup()or list(fp.Groups())
                    or not bypass.capacitor_identity(fp.GetReference(),fp.GetFPIDAsString())
                    or not bypass.local_bypass_technology(fp.GetValue(),fp.GetFPIDAsString())
                    or not re.search(r'(?:^|:)C_[0-9]{4}(?:_|$)',fp.GetFPIDAsString())
                    or bypass.capacitance_f(fp.GetValue())is None
                    or not 0<bypass.capacitance_f(fp.GetValue())<=1e-3 or len(pads)!=2
                    or len({p.GetNumber()for p in pads})!=2
                    or sum(p.GetNetname()=='GND'for p in pads)!=1
                    or list(fp.Zones())
                    or {force._uid(fp),*[force._uid(p)for p in pads]}&(grouped|literal_grouped)
                    or any(p.GetNetCode()<=0 or p.HasHole()or p.IsLocked()or p.GetParentGroup()
                        or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                        or set(map(int,p.GetLayerSet().CuStack()))!={int(fp.GetLayer())} for p in pads)
                    or any(int(g.GetLayer())in copper_faces|{int(pcbnew.Edge_Cuts)}
                        for g in [*fp.GraphicalItems(),*fp.GetFields()])):
                raise ValueError('isolated_grounded_ceramic_pose_without_barrel_motion_required')
            detached._detached(board,fp,deadline)
        actual_movement=actual_movement or delta>0 or turn!=0
        chosen.append(force._uid(fp))
    if not actual_movement:raise ValueError('actual_retained_passive_pose_change_required')
    if (time.monotonic()>=deadline or family!=force._family(source,board_hint)
            or code!=force._code_identity()):
        raise ValueError('retained_passive_pose_Source_or_code_changed')
    result=dict(schema=1,
        scope='exact_Source_retained_copper_grounded_passive_pose',
        source=str(source),source_sha256=force._hash(source),source_family=family,
        code_identity=code,board_hint=board_hint,poses=poses,
        selected_footprint_uuids=sorted(chosen),
        reference_group_uuids=list(reference_group_uuids),
        source_tracks_retired=False,new_conductors_authorized=False,
        current_qualified=False,routing_admitted=False,release_authority=False)
    # Preserve the exact existing JSON schema for the default attached tier.
    # Explicit new work bounds never relabel an old proof or default radius.
    if max_shift_mm!=6. or not allow_source_ground_barrel_motion:
        result.update(max_shift_mm=max_shift_mm,
            allow_source_ground_barrel_motion=allow_source_ground_barrel_motion)
    if allow_cardinal_reference_maps:
        result['allow_cardinal_reference_maps']=True
    if retain_projected_ground_entries:
        result['retain_projected_ground_entries']=True
    return json.loads(json.dumps(result,allow_nan=False))


def _fresh(source, proposal):
    fresh=plan(source,proposal['poses'],board_hint=proposal['board_hint'],
        reference_group_uuids=proposal['reference_group_uuids'],
        max_shift_mm=proposal.get('max_shift_mm',6.),
        allow_source_ground_barrel_motion=proposal.get('allow_source_ground_barrel_motion',True),
        allow_cardinal_reference_maps=proposal.get('allow_cardinal_reference_maps',False),
        retain_projected_ground_entries=proposal.get('retain_projected_ground_entries',False))
    if (json.dumps(fresh,sort_keys=True,separators=(',',':'),allow_nan=False)
            !=json.dumps(proposal,sort_keys=True,separators=(',',':'),allow_nan=False)):
        raise ValueError('stale_or_forged_retained_passive_pose_proposal')
    return fresh


def construct(source, directory, proposal, *, timeout_s=10.):
    if type(timeout_s)not in(int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.:
        raise ValueError('bounded_retained_passive_pose_lease_required')
    source=Path(source).resolve(strict=True);directory=Path(directory).resolve()
    if directory.exists():raise ValueError('fresh_private_retained_passive_directory_required')
    _fresh(source,proposal)
    original=pcbnew.LoadBoard(str(source));target=force._copy_family(source,directory)
    child=pcbnew.LoadBoard(str(target))
    retained_entries={}
    if proposal.get('retain_projected_ground_entries',False):
        import cec_projected_ground_contact as contacts
        retained_entries=contacts.plan_capacitor_entries(original,proposal['poses'],
            board_hint=proposal['board_hint'],timeout_s=timeout_s)
    references={}
    if proposal['reference_group_uuids']:
        import cec_source_reference_group_transport as maps
        groups={force._uid(g):g for g in original.Groups()}
        selections=[]
        for uid in proposal['reference_group_uuids']:
            group=groups.get(uid)
            owners=[] if group is None else [i for i in group.GetItems()if i.GetClass()=='FOOTPRINT']
            if len(owners)!=1 or force._uid(owners[0])not in proposal['selected_footprint_uuids']:
                raise ValueError('selected_passive_source_reference_group_required')
            ref=owners[0].GetReference();target_pose=proposal['poses'][ref]
            if ((target_pose[2]-owners[0].GetOrientationDegrees())%360
                    and not proposal.get('allow_cardinal_reference_maps',False)):
                raise ValueError('retained_passive_reference_map_translation_only')
            selections.append((force._uid(owners[0]),uid))
        proofs=maps.inspect_many(source,selections,timeout_s=timeout_s)
        requests=[];cardinal_requests=[]
        for proof in proofs:
            owner=next(fp for fp in original.GetFootprints()if force._uid(fp)==proof['owner_uuid'])
            ref=owner.GetReference();references[ref]=proof
            delta=tuple(round(proposal['poses'][ref][k]*1e6)-tuple(owner.GetPosition())[k]for k in(0,1))
            requests.append((proof,delta))
            turn=int((proposal['poses'][ref][2]-owner.GetOrientationDegrees())%360)//90
            cardinal_requests.append((proof,turn,delta))
        if proposal.get('allow_cardinal_reference_maps',False):
            # Existing exact Source-map machinery, not a new group/ink
            # allowance. The separate physical receiver still reconstructs
            # grounded passive roles and every Source conductor/contact.
            import cec_source_reference_group_cardinal_batch as cardinal
            cardinal.transform_many(child,cardinal_requests,timeout_s=timeout_s,
                maximum_translation_mm=proposal.get('max_shift_mm',6.))
        else:maps.transform_many(child,requests)
    for ref,pose in proposal['poses'].items():
        if ref in references:continue
        fp=child.FindFootprintByReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in pose[:2])))
        fp.SetOrientationDegrees(pose[2])
    if proposal.get('allow_source_ground_barrel_motion',True):
        carried=transport.apply(original,child,source_path=source,board_hint=proposal['board_hint'],
            maximum_shift_mm=6.,retain_source_tracks=True,carry_ground_barrels_only=True,
            allow_cardinal_rotations=True,reference_group_uuids=proposal['reference_group_uuids'],
            **({'retained_ground_contacts':list(retained_entries.values())}if retained_entries else {}),
            timeout_s=timeout_s)
    else:
        carried=dict(changes=[],source_ground_barrels_moved=False,
            independently_isolated_ceramic_only=True)
    started=time.monotonic();additive._ground_refill(child)
    if time.monotonic()-started>timeout_s:raise ValueError('retained_passive_Ground_refill_deadline')
    field._save_field_snapshot(child,target)
    # KiCad may reorder hidden properties/opaque fields in EVERY footprint
    # even though only these selected passives moved. Keep all other Source
    # subtrees exact, including closed-map owners outside this pose cohort.
    import cec_source_literal_footprint_retention as footprint_text
    import cec_source_retaining_ses_import as source_text
    source_text.write_raw(target,footprint_text.retain(source_text.raw_text(source),
        source_text.raw_text(target),proposal['selected_footprint_uuids']))
    result=receive(source,target,proposal,timeout_s=timeout_s)
    return dict(candidate=str(target),candidate_sha256=force._hash(target),
        source_barrel_transport=carried,receiving=result,
        ok=result['ok'],complete=result['complete'],release_authority=False)


def receive(source, candidate, proposal, *, timeout_s=10.):
    r=dict(ok=False,complete=False,errors=[],routing_admitted=False,
        current_qualified=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        if source==candidate:raise ValueError('distinct_saved_retained_passive_candidate_required')
        epoch=force._code_identity()
        families=[force._family(p,proposal['board_hint'])for p in(source,candidate)]
        fresh=_fresh(source,proposal)
        proof=pose_receiving.receive(source,candidate,
            selected_footprint_uuids=fresh['selected_footprint_uuids'],
            board_hint=fresh['board_hint'],max_shift_mm=fresh.get('max_shift_mm',6.),timeout_s=timeout_s,
            allow_source_ground_barrel_motion=fresh.get('allow_source_ground_barrel_motion',True),
            reference_group_uuids=fresh['reference_group_uuids'],
            **({'allow_cardinal_reference_maps':True}
                if fresh.get('allow_cardinal_reference_maps',False) else {}),
            **({'retain_projected_ground_entries':True}
                if fresh.get('retain_projected_ground_entries',False)else {}))
        r['independent_Source_pose_reconstruction']=proof
        if not proof['ok']or not proof['complete']:
            raise ValueError('retained_passive_Source_pose_refused:'+str(proof['errors']))
        if proof['exact_source_plus_additions'].get('added_native_uuids'):
            raise ValueError('passive_pose_cannot_add_new_material')
        # The Source receiver intentionally accepts a finite selected pose.
        # The saved transaction must additionally bind the requested target,
        # not merely any other accepted pose of these same native identities.
        board=pcbnew.LoadBoard(str(candidate))
        for ref,pose in fresh['poses'].items():
            fp=board.FindFootprintByReference(ref)
            if (fp is None or tuple(fp.GetPosition())!=tuple(round(v*1e6)for v in pose[:2])
                    or (fp.GetOrientationDegrees()-pose[2])%360!=0):
                raise ValueError('saved_retained_passive_pose_differs_from_request')
        if not fresh.get('allow_source_ground_barrel_motion',True):
            import cec_capacitor_return_repack as assignments
            original=pcbnew.LoadBoard(str(source))
            if assignments._assignments(original,fresh['board_hint'])!=assignments._assignments(board,fresh['board_hint']):
                raise ValueError('isolated_passive_source_bypass_assignment_changed')
        _fresh(source,proposal)
        if (epoch!=force._code_identity()
                or families!=[force._family(p,fresh['board_hint'])for p in(source,candidate)]):
            raise ValueError('retained_passive_Source_candidate_or_code_changed_during_receiving')
        r.update(ok=True,complete=True,source_sha256=force._hash(source),
            candidate_sha256=force._hash(candidate),
            all_Source_tracks_and_arcs_retained_exactly=True,
            Source_owned_Ground_barrels_and_annotation_only=True,
            independent_original_parent_current_fields_returns_DRC_and_stack_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError)as exc:
        r['errors'].append(type(exc).__name__+':'+str(exc))
    return r
