"""Source-proved full-width Ground-entry retention under real package motion.

A moved footprint does not imply a lost contact. Its projected SMD land can
still contain the complete original entry, even after a quarter-turn changes
the land polygon. Keep that SOURCE copper rather than cut/rebuild it. This is
not an unchanged-land claim, an immediate-return waiver or route admission.
"""
import hashlib,json,math,time
from pathlib import Path
import pcbnew
import cec_cell_row_rebuild as row
import cec_decoupler_cell as cell
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_force_current as force
import cec_ground_return_shortcut as ground
import cec_measurement_leaf as leaf
import cec_native_placement_context as native


def _land_digest(pad,deadline):
    shape=native._native_stationary_land(pad,deadline)
    if shape is None:raise ValueError('projected_native_ground_land_geometry_unknown')
    # KiCad reassigns numeric NETINFO codes on save/load. The immutable
    # terminal UUID, pin, NET NAME and exact per-layer native polygons own
    # this saved proof; an allocator ordinal is not electrical identity.
    stable=shape[:3]+shape[4:]
    return hashlib.sha256(repr(stable).encode()).hexdigest()


def _group_uuid(board,item):
    # GetParentGroup() is an EDA_GROUP proxy, not a UUID-bearing PCB_GROUP
    # in KiCad 10. Resolve the literal native container from this board.
    groups=[force._uid(g) for g in board.Groups() if g.ContainsItem(item)]
    if len(groups)>1:raise ValueError('unique_source_ground_entry_native_group_required')
    return groups[0] if groups else None


def _via_signature(board,via):
    return dict(uuid=force._uid(via),net=str(via.GetNetname()),at_nm=list(via.GetPosition()),
        drill_nm=int(via.GetDrillValue()),diameters_nm={str(int(l)):int(via.GetWidth(l)) for l in board.GetEnabledLayers().CuStack()},
        type=int(via.GetViaType()),top=int(via.TopLayer()),bottom=int(via.BottomLayer()),locked=bool(via.IsLocked()),
        group_uuid=_group_uuid(board,via))


def _direct_full_axis(item,via,face):
    """A native edge kiss is continuity, not a full-class direct via entry.

    Only credit a source stroke whose centreline actually passes through
    the barrel axis, with the full stroke width inside its outer diameter.
    The factory process predicate separately owns the plated hole/annulus.
    """
    if force._uid(item)==force._uid(via):return True
    if item.GetClass()!='PCB_TRACK' or item.GetWidth()+4000>via.GetWidth(face):return False
    a=tuple(item.GetStart());b=tuple(item.GetEnd());p=tuple(via.GetPosition())
    dx=b[0]-a[0];dy=b[1]-a[1];px=p[0]-a[0];py=p[1]-a[1]
    return (dx*py==dy*px and 0<=px*dx+py*dy<=dx*dx+dy*dy
        and (dx!=0 or dy!=0 or p==a))


def _anchor_signature(board,item):
    if item.GetClass()=='PCB_VIA':return _via_signature(board,item)
    return dict(uuid=force._uid(item),net=str(item.GetNetname()),layer=int(item.GetLayer()),
        start_nm=list(item.GetStart()),end_nm=list(item.GetEnd()),width_nm=int(item.GetWidth()),
        locked=bool(item.IsLocked()),mask=bool(item.HasSolderMask()),
        group_uuid=_group_uuid(board,item))


def _return_to(board,pad,via):
    cost=cell._shortest_track_path_mm(board,pad,via,snap_mm=.000001)
    if cost is None or cost>16.:
        cost=cell._straight_filled_return_mm(board,pad,via,include_native_tracks=True)
    return cost if cost is not None and cost<=16. else None


def plan_capacitor_entries(board,poses,*,board_hint,timeout_s=10.):
    """Rederive retained entries for a finite cohort of Source bypass caps.

    Only the original saved board and requested package poses are inputs.
    A caller cannot nominate a barrel, substitute an arbitrary Ground role,
    or turn an inherited long return into immediate-return qualification.
    The transport independently observes these ephemeral proofs again.
    Already-zero, completely in-pad Source barrels defer to that transport's
    existing owner-following tier; optional retention must not pin an
    off-centre barrel in a land that is legitimately moving away from it.
    """
    import cec_device_bypass as bypass
    if (type(poses)is not dict or not 1<=len(poses)<=8
            or any(type(ref)is not str or not ref for ref in poses)
            or type(board_hint)is not str or not board_hint
            or type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10.):
        raise ValueError('bounded_Source_capacitor_entry_cohort_required')
    deadline=time.monotonic()+timeout_s;proofs={};owners=set();moving=0
    source=Path(board.GetFileName())
    if not board.GetFileName()or not source.is_file():
        raise ValueError('saved_Source_capacitor_entry_cohort_required')
    digest=force._hash(source);binding=row._source_binding(board)
    if row._source_binding(pcbnew.LoadBoard(str(source)))!=binding:
        raise ValueError('literal_saved_Source_capacitor_entry_cohort_required')
    for ref,target in sorted(poses.items()):
        if (type(ref)is not str or not ref or type(target)not in(list,tuple)
                or len(target)!=3
                or any(type(v)not in(int,float)or not math.isfinite(v)for v in target)):
            raise ValueError('finite_Source_capacitor_entry_pose_required')
        matches=[fp for fp in board.GetFootprints()if fp.GetReference()==ref]
        if len(matches)!=1:raise ValueError('unique_actual_Source_capacitor_required')
        fp=matches[0];uid=force._uid(fp);pads=list(fp.Pads())
        face=int(fp.GetLayer());turn=(target[2]-fp.GetOrientationDegrees())%360
        value=bypass.capacitance_f(fp.GetValue())
        if (uid in owners or fp.IsLocked()or fp.IsDNP()or len(pads)!=2
                or len({force._uid(p)for p in pads})!=2
                or len({p.GetNumber()for p in pads})!=2
                or sum(p.GetNetname()=='GND'for p in pads)!=1
                or not bypass.capacitor_identity(ref,fp.GetFPIDAsString())
                or not bypass.local_bypass_technology(fp.GetValue(),fp.GetFPIDAsString())
                or value is None or not 0<value<=1e-3
                or face not in(int(pcbnew.F_Cu),int(pcbnew.B_Cu))
                or turn not in(0.,90.,180.,270.)
                or math.dist(tuple(fp.GetPosition()),[round(v*1e6)for v in target[:2]])>6000000
                or list(fp.Zones())
                or any(p.HasHole()or p.IsLocked()or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                    or p.GetNetCode()<=0 or set(map(int,p.GetLayerSet().CuStack()))!={face}
                    for p in pads)):
            raise ValueError('actual_grounded_Source_surface_bypass_capacitor_required')
        owners.add(uid)
        if (tuple(fp.GetPosition())==tuple(round(v*1e6)for v in target[:2])and turn==0):
            continue
        moving+=1
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('Source_capacitor_entry_cohort_deadline')
        pad=next(p for p in pads if p.GetNetname()=='GND')
        witness=cell._existing_return(board,pad,16.,allow_native_track_body=True)
        if witness is not None and witness[0]==0.:
            via=witness[1]
            land=pcbnew.SHAPE_POLY_SET();pad.TransformShapeToPolygon(land,face,0,1000,pcbnew.ERROR_INSIDE)
            outer=pcbnew.SHAPE_POLY_SET();via.TransformShapeToPolygon(outer,face,0,1000,pcbnew.ERROR_OUTSIDE)
            outer.BooleanSubtract(land)
            if not outer.OutlineCount():
                # Fresh positive bypass authority even though no retention
                # proof is needed. The existing transport still re-proves
                # unique native ownership, process, motion and clearance.
                leaf._bypass_supply_owner(board,pad,board_hint,ground_return=True)
                d,h=via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6
                if (fab.board_legal_through_via_geometry(board,d,h)[:2]!=(d,h)
                        and not fab.local_pofv_via_decision(board,via,allow_source_track_body=True)[0]):
                    raise ValueError('source_ground_barrel_process_ownership_required')
                continue
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('Source_capacitor_entry_cohort_deadline')
        proof=plan(board,force._uid(pad),target,board_hint=board_hint,timeout_s=remaining)
        if proof['source_ground_role']['kind']!='source_selected_bypass_ground':
            raise ValueError('Source_selected_bypass_Ground_entry_required')
        proofs[force._uid(pad)]=proof
    if not moving:raise ValueError('actual_moving_Source_capacitor_entries_required')
    if (time.monotonic()>=deadline or force._hash(source)!=digest
            or row._source_binding(board)!=binding):
        raise ValueError('Source_capacitor_entry_cohort_changed_or_expired')
    return {uid:proofs[uid]for uid in sorted(proofs)}


def plan(board,pad_uuid,target_pose,*,board_hint,timeout_s=10.,allow_octilinear_rotations=False):
    """Prove the entire original entry disk is inside the actual posed land."""
    if (type(pad_uuid) is not str or not pad_uuid or type(board_hint) is not str or not board_hint
            or type(target_pose) not in (list,tuple) or len(target_pose)!=3
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in target_pose)
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(allow_octilinear_rotations) is not bool):
        raise ValueError('bounded_projected_native_ground_contact_required')
    deadline=time.monotonic()+timeout_s;binding=row._source_binding(board);source=Path(board.GetFileName())
    if not board.GetFileName() or not source.is_file():raise ValueError('saved_projected_ground_contact_source_required')
    digest=force._hash(source)
    if row._source_binding(pcbnew.LoadBoard(str(source)))!=binding:
        raise ValueError('literal_saved_projected_ground_contact_source_required')
    pads=[p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p)==pad_uuid]
    if len(pads)!=1:raise ValueError('literal_source_ground_entry_land_required')
    pad=pads[0];fp=pad.GetParentFootprint();model=roles.footprint_contract(fp)
    face=cell.cec_return_escape.smd_surface_layer(pad)
    turn=(target_pose[2]-fp.GetOrientationDegrees())%360
    if (pad.GetNetname()!='GND' or face is None or pad.HasHole() or fp.IsLocked() or fp.IsDNP()
            or not any(abs(turn-a)<1e-6 for a in range(0,361,45 if allow_octilinear_rotations else 90))
            or math.dist(tuple(fp.GetPosition()),[round(v*1e6) for v in target_pose[:2]])>32000000):
        raise ValueError('bounded_source_ground_smd_pose_required')
    if model:
        role=model['pins'].get(str(pad.GetNumber()))
        if role not in ('ground','reference') or set(model['pins'].values())&{'power_output','switch','power_return'}:
            raise ValueError('positive_low_power_manufacturer_ground_entry_required')
        authority=dict(kind='manufacturer_ground',role=role,source=model['source'])
    else:
        selected=leaf._bypass_supply_owner(board,pad,board_hint,ground_return=True)
        authority=dict(kind='source_selected_bypass_ground',selected_bypass=selected)
    old_point=tuple(pad.GetPosition());widths=[max(200000,int(board.GetDesignSettings().m_TrackMinWidth),int(cell._netclass(board,'GND')['width']))]
    anchors=[]
    for item in board.GetTracks():
        if time.monotonic()>=deadline:raise ValueError('projected_ground_entry_deadline')
        if item.GetNetname()!='GND' or not item.IsOnLayer(face):continue
        if item.GetClass()=='PCB_TRACK' and old_point in (tuple(item.GetStart()),tuple(item.GetEnd())):
            widths.append(int(item.GetWidth()));anchors.append(force._uid(item))
        elif item.GetClass()=='PCB_VIA' and old_point==tuple(item.GetPosition()):
            widths.append(int(item.GetWidth(face)));anchors.append(force._uid(item))
    if not anchors:raise ValueError('exact_source_ground_entry_axis_required_not_proximity')
    projected=pcbnew.FOOTPRINT(fp);projected.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target_pose[:2])))
    projected.SetOrientationDegrees(target_pose[2]);future=next(p for p in projected.Pads() if force._uid(p)==pad_uuid)
    # INSIDE target minus OUTSIDE source-entry disk, with explicit polygon
    # errors. A centre-only overlap cannot hide a clipped full-class return.
    land=pcbnew.SHAPE_POLY_SET();future.TransformShapeToPolygon(land,face,0,1000,pcbnew.ERROR_INSIDE)
    marker=pcbnew.PCB_TRACK(board);marker.SetLayer(face);marker.SetStart(pcbnew.VECTOR2I(*old_point))
    marker.SetEnd(pcbnew.VECTOR2I(*old_point));marker.SetWidth(max(widths)+4000)
    disk=pcbnew.SHAPE_POLY_SET();marker.TransformShapeToPolygon(disk,face,0,1000,pcbnew.ERROR_OUTSIDE)
    disk.BooleanSubtract(land)
    if disk.OutlineCount():raise ValueError('full_class_source_ground_entry_not_contained_in_projected_land')
    witness=cell._existing_return(board,pad,16.,allow_native_track_body=True)
    if witness is None:raise ValueError('known_source_ground_return_required')
    via=witness[1];references=ground._reference_contacts(board,via)
    d,h=via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6
    if (fab.board_legal_through_via_geometry(board,d,h)[:2]!=(d,h)
            and not fab.local_pofv_via_decision(board,via,allow_source_track_body=True)[0]):
        raise ValueError('source_ground_barrel_process_ownership_required')
    future_digest=_land_digest(future,deadline)
    if row._source_binding(board)!=binding or force._hash(source)!=digest or time.monotonic()>=deadline:
        raise ValueError('projected_ground_entry_source_changed_or_expired')
    items={force._uid(t):t for t in board.GetTracks()}
    direct=[u for u in anchors if _direct_full_axis(items[u],via,face)]
    result=dict(schema=1,scope='projected_full_class_native_ground_entry_retention',source=str(source.resolve()),
        source_sha256=digest,source_native_binding=binding,board_hint=board_hint,pad_uuid=pad_uuid,owner=fp.GetReference(),
        target_pose=list(target_pose),source_entry_nm=list(old_point),entry_width_nm=max(widths),
        source_entry_native_uuids=sorted(anchors),source_return_mm=witness[0],
        source_entry_signatures={u:_anchor_signature(board,items[u]) for u in sorted(anchors)},
        full_class_direct_reference_anchor_uuids=sorted(direct),
        source_reference_via=_via_signature(board,via),actual_saved_reference_contacts=references,
        future_land_sha256=future_digest,source_ground_role=authority,
        numeric_net_allocator_code_is_not_saved_identity=True,
        complete_source_entry_disk_contained=True,entire_source_land_unchanged=False,
        unchanged_source_return_is_not_new_immediate_return_qualification=True,
        no_new_copper_or_hole=True,current_qualified=False,routing_admitted=False,release_authority=False)
    if allow_octilinear_rotations:result['allow_octilinear_rotations']=True
    return result


def observe(board,pad,proof,*,timeout_s=10.):
    """Rederive SOURCE authority; prove the retained live path after ALL cuts."""
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.:
        raise ValueError('bounded_projected_ground_observation_required')
    deadline=time.monotonic()+timeout_s
    source=Path(proof['source'])
    if not source.is_file() or force._hash(source)!=proof['source_sha256']:
        raise ValueError('projected_ground_source_file_changed')
    before=pcbnew.LoadBoard(str(source))
    fresh=plan(before,proof['pad_uuid'],proof['target_pose'],board_hint=proof['board_hint'],
        timeout_s=max(.001,deadline-time.monotonic()),
        allow_octilinear_rotations=proof.get('allow_octilinear_rotations',False))
    if json.loads(json.dumps(fresh))!=proof:raise ValueError('stale_or_forged_projected_ground_entry_proof')
    if force._uid(pad)!=proof['pad_uuid'] or _land_digest(pad,deadline)!=proof['future_land_sha256']:
        raise ValueError('exact_projected_live_ground_land_required')
    live={force._uid(t):t for t in board.GetTracks()}
    if not set(proof['source_entry_native_uuids'])<=live.keys():return None
    if any(_anchor_signature(board,live[u])!=s for u,s in proof['source_entry_signatures'].items()):return None
    oldvia=proof['source_reference_via'];via=live.get(oldvia['uuid'])
    if via is None or _via_signature(board,via)!=oldvia:return None
    if ground._reference_contacts(board,via)!=proof['actual_saved_reference_contacts']:return None
    d,h=via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6
    if (fab.board_legal_through_via_geometry(board,d,h)[:2]!=(d,h)
            and not fab.local_pofv_via_decision(board,via,allow_source_track_body=True)[0]):return None
    witness=_return_to(board,pad,via)
    if witness is None or witness>proof['source_return_mm']+.000001:return None
    if time.monotonic()>=deadline:raise ValueError('projected_ground_observation_deadline')
    return dict(source_return_mm=proof['source_return_mm'],saved_return_mm=witness,
        via_uuid=force._uid(via),actual_saved_reference_contacts=proof['actual_saved_reference_contacts'],
        full_source_entry_preserved_after_all_cuts=True,
        full_class_direct_reference_reach_proved=bool(proof['full_class_direct_reference_anchor_uuids']),
        new_immediate_return_qualification=False,release_authority=False)


def plan_barrel_reuse(board,pad_uuid,via_uuid,target_pose,*,board_hint,timeout_s=10.,allow_octilinear_rotations=False):
    """Keep an existing qualified Ground barrel under a different posed land.

    This proves stationary native material, not a right to drag its former
    owner or omit that owner's old connection. Every old terminal and every
    affected native partition still needs complete reconstruction/receiving.
    """
    if (type(pad_uuid) is not str or not pad_uuid or type(via_uuid) is not str or not via_uuid
            or type(board_hint) is not str or not board_hint
            or type(target_pose) not in (list,tuple) or len(target_pose)!=3
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in target_pose)
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(allow_octilinear_rotations) is not bool):
        raise ValueError('bounded_projected_ground_barrel_reuse_required')
    deadline=time.monotonic()+timeout_s;source=Path(board.GetFileName())
    if not board.GetFileName() or not source.is_file():raise ValueError('saved_ground_barrel_reuse_source_required')
    binding=row._source_binding(board);digest=force._hash(source)
    if row._source_binding(pcbnew.LoadBoard(str(source)))!=binding:
        raise ValueError('literal_saved_ground_barrel_reuse_source_required')
    pads=[p for fp in board.GetFootprints() for p in fp.Pads() if force._uid(p)==pad_uuid]
    vias=[v for v in board.GetTracks() if force._uid(v)==via_uuid and v.GetClass()=='PCB_VIA']
    if len(pads)!=1 or len(vias)!=1:raise ValueError('literal_source_ground_land_and_barrel_required')
    pad,via=pads[0],vias[0];fp=pad.GetParentFootprint();face=cell.cec_return_escape.smd_surface_layer(pad)
    turn=(target_pose[2]-fp.GetOrientationDegrees())%360
    if (pad.GetNetname()!='GND' or via.GetNetname()!='GND' or pad.HasHole() or face is None
            or fp.IsLocked() or fp.IsDNP() or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
            or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu
            or not any(abs(turn-a)<1e-6 for a in range(0,361,45 if allow_octilinear_rotations else 90))
            or math.dist(tuple(fp.GetPosition()),[round(v*1e6) for v in target_pose[:2]])>32000000):
        raise ValueError('bounded_low_power_ground_land_and_full_through_barrel_required')
    model=roles.footprint_contract(fp)
    if model:
        role=model['pins'].get(str(pad.GetNumber()))
        if role not in ('ground','reference') or set(model['pins'].values())&{'power_output','switch','power_return'}:
            raise ValueError('positive_low_power_ground_barrel_reuse_owner_required')
        authority=dict(kind='manufacturer_ground',role=role,source=model['source'])
    else:
        authority=dict(kind='source_selected_bypass_ground',
            selected_bypass=leaf._bypass_supply_owner(board,pad,board_hint,ground_return=True))
    old=cell._existing_return(board,pad,16.,allow_native_track_body=True)
    if old is None:raise ValueError('known_source_ground_return_required_for_barrel_reuse')
    refs=ground._reference_contacts(board,via)
    d,h=via.GetWidth(via.TopLayer())/1e6,via.GetDrillValue()/1e6
    if (fab.board_legal_through_via_geometry(board,d,h)[:2]!=(d,h)
            and not fab.local_pofv_via_decision(board,via,allow_source_track_body=True)[0]):
        raise ValueError('qualified_source_ground_barrel_process_required')
    projected=pcbnew.FOOTPRINT(fp)
    projected.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target_pose[:2])))
    projected.SetOrientationDegrees(target_pose[2]);future=next(p for p in projected.Pads() if force._uid(p)==pad_uuid)
    land=pcbnew.SHAPE_POLY_SET();future.TransformShapeToPolygon(land,face,0,1000,pcbnew.ERROR_INSIDE)
    outer=pcbnew.SHAPE_POLY_SET();via.TransformShapeToPolygon(outer,face,0,1000,pcbnew.ERROR_OUTSIDE)
    outer.BooleanSubtract(land)
    if outer.OutlineCount():raise ValueError('entire_stationary_ground_barrel_must_fit_projected_land')
    future_digest=_land_digest(future,deadline)
    if row._source_binding(board)!=binding or force._hash(source)!=digest or time.monotonic()>=deadline:
        raise ValueError('ground_barrel_reuse_source_changed_or_expired')
    result=dict(schema=1,scope='projected_full_native_ground_barrel_reuse',source=str(source.resolve()),
        source_sha256=digest,source_native_binding=binding,board_hint=board_hint,pad_uuid=pad_uuid,
        owner=fp.GetReference(),target_pose=list(target_pose),source_reference_via=_via_signature(board,via),
        source_return_mm=old[0],actual_saved_reference_contacts=refs,future_land_sha256=future_digest,
        source_ground_role=authority,complete_source_barrel_contained_in_projected_land=True,
        former_owner_connections_not_retired_or_waived=True,no_new_copper_or_hole=True,
        current_qualified=False,routing_admitted=False,release_authority=False)
    if allow_octilinear_rotations:result['allow_octilinear_rotations']=True
    return result


def observe_barrel_reuse(board,pad,proof,*,timeout_s=10.):
    """Independently rederive the source and the exact unchanged live barrel."""
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.:
        raise ValueError('bounded_ground_barrel_reuse_observation_required')
    deadline=time.monotonic()+timeout_s;source=Path(proof['source'])
    if not source.is_file() or force._hash(source)!=proof['source_sha256']:
        raise ValueError('ground_barrel_reuse_source_changed')
    fresh=plan_barrel_reuse(pcbnew.LoadBoard(str(source)),proof['pad_uuid'],
        proof['source_reference_via']['uuid'],proof['target_pose'],board_hint=proof['board_hint'],
        timeout_s=max(.001,deadline-time.monotonic()),
        allow_octilinear_rotations=proof.get('allow_octilinear_rotations',False))
    if json.loads(json.dumps(fresh))!=proof:raise ValueError('stale_or_forged_ground_barrel_reuse_proof')
    fp=pad.GetParentFootprint();pose=proof['target_pose']
    if (force._uid(pad)!=proof['pad_uuid'] or list(fp.GetPosition())!=[round(v*1e6) for v in pose[:2]]
            or abs((fp.GetOrientationDegrees()-pose[2]+180)%360-180)>1e-9
            or _land_digest(pad,deadline)!=proof['future_land_sha256']):
        raise ValueError('exact_projected_ground_barrel_reuse_land_required')
    live={force._uid(t):t for t in board.GetTracks()};signature=proof['source_reference_via']
    via=live.get(signature['uuid'])
    if via is None or _via_signature(board,via)!=signature:return None
    if ground._reference_contacts(board,via)!=proof['actual_saved_reference_contacts']:return None
    if not fab.local_pofv_via_decision(board,via,allow_source_track_body=True)[0]:return None
    # Containment was proved with the exact native land digest; this is an
    # existing full reference barrel, not a centre-only/new-hole shortcut.
    if time.monotonic()>=deadline:raise ValueError('ground_barrel_reuse_observation_deadline')
    return dict(via_uuid=force._uid(via),saved_return_mm=0.,
        actual_saved_reference_contacts=proof['actual_saved_reference_contacts'],
        stationary_native_barrel_and_full_land_reproved=True,release_authority=False)
