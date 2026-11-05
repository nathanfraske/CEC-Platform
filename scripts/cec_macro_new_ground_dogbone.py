"""Mandatory NEW local attachments, distinct from known-return preservation.

An integer site proposes a bounded dogbone; it grants no cut or route credit.
The exact Source-selected low-power bypass, unchanged class, Source process
menu and actual posed land own the obligation. Its real column must obstruct
any cooperatively retired foreign lead, and every such lead is independently
restored. Unknown original returns stay unknown. No power-pour, current,
package-internal connection, process-rule or release authority is added.

A separately typed device attachment keeps the manufacturer's actual role
(including a Source-grounded address input); it is never a bypass alias.
Long lands use the existing native metal-to-metal path metric, not a larger
electrical reach. Every known Source return must still independently survive.
"""
import hashlib
import heapq
import json
import math
import time
import uuid
from pathlib import Path

import pcbnew
import cec_cell_row_rebuild as row
import cec_decoupler_cell as cell
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_shortcut as reference
import cec_measurement_leaf as leaf
import cec_native_placement_context as native
import cec_route_quality as quality


def _lease(seconds):
    if type(seconds)not in(int,float)or not math.isfinite(seconds)or not 0<seconds<=10.:
        raise ValueError('bounded_new_ground_dogbone_lease_required')
    return time.monotonic()+seconds


def _digest(pad,deadline):
    material=native._native_stationary_land(pad,deadline)
    if material is None:raise ValueError('new_ground_native_land_unknown')
    return hashlib.sha256(repr(material[:3]+material[4:]).encode()).hexdigest()


def _column(board,pad,point,diameter,drill):
    via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I(*point));via.SetNet(pad.GetNet())
    via.SetWidth(diameter);via.SetDrill(drill);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    return via


def _device_attachment(parent,pad,proposal):
    """Positive Source device role, never a general same-net Ground mesh."""
    fp=pad.GetParentFootprint();model=roles.footprint_contract(fp)
    if model is None:return None
    role=model['pins'].get(pad.GetNumber())
    if (role not in ('ground','power_return','reference','address')
            or set(model['pins'].values())&{'power_output','switch','feedback'}):
        raise ValueError('positive_nonconverter_device_ground_attachment_required')
    pins=roles.physical_pinmap(fp,model,board_hint=proposal['board_hint'])
    if (pad.GetNetname()!='GND' or len(pins[pad.GetNumber()])!=1
            or force._uid(pins[pad.GetNumber()][0])!=force._uid(pad)
            or not any(p.GetNetname()=='GND' and model['pins'].get(p.GetNumber())
                in ('ground','power_return') for p in fp.Pads())):
        raise ValueError('literal_source_grounded_device_attachment_required')
    previous=cell._existing_return(parent,pad,16.,allow_native_track_body=True)
    if previous is None or previous[0]<=0:
        raise ValueError('known_positive_source_device_attachment_return_required')
    return dict(owner_uuid=force._uid(fp),owner=fp.GetReference(),pin=pad.GetNumber(),
        pad_uuid=force._uid(pad),net=pad.GetNetname(),manufacturer_role=role,
        manufacturer=model,source_return_mm=previous[0],
        source_reference_via_uuid=force._uid(previous[1]),
        actual_role_not_reclassified=True,current_authority=False,release_authority=False)


def _source_address_entry(parent,pad,device,width,escape,diameter,deadline):
    """Preserve a real Source address escape, not a new Ground-width waiver.

    A preferred Ground class can exceed the existing, explicitly owned
    fine-pin entry. Only a manufacturer-grounded ADDRESS with that actual
    Source entry may use the shared native endpoint classifier's full-width
    VIA throat instead of manufacturing another full-width TRACK throat.
    Functional Ground/return pins, unknown entries and smaller barrels keep
    the original operator. Current and all other Ground obligations remain
    outside this geometric entry permission.
    """
    if (device is None or device['manufacturer_role']!='address' or escape is None
            or diameter<width):return None
    narrow,budget=escape
    if (type(narrow)is not int or not 0<narrow<width or budget<=0
            or narrow<max(200000,int(parent.GetDesignSettings().m_TrackMinWidth))):return None
    groups=[g for g in parent.Groups()if g.GetName()==fr.ENDPOINT_NECKDOWN_GROUP]
    if len(groups)!=1 or groups[0].GetParentGroup()is not None:return None
    face=cell.cec_return_escape.smd_surface_layer(pad)
    if face is None:return None
    shape=pad.GetEffectiveShape(face);members=[]
    for track in groups[0].GetItems():
        if time.monotonic()>=deadline:raise ValueError('source_address_entry_deadline')
        if (track.GetClass()!='PCB_TRACK'or track.GetNetCode()!=pad.GetNetCode()
                or track.GetLayer()!=face or track.GetWidth()>=width):continue
        if not any(shape.Collide(point,0)for point in(track.GetStart(),track.GetEnd())):continue
        if (track.GetWidth()!=narrow or not quality.is_canonical_stroke(
                tuple(track.GetStart()),tuple(track.GetEnd()),tolerance_nm=0)):
            return None
        members.append(dict(uuid=force._uid(track),start_nm=list(track.GetStart()),
            end_nm=list(track.GetEnd()),width_nm=int(track.GetWidth()),face=int(face),
            locked=bool(track.IsLocked())))
    if not 1<=len(members)<=4:return None
    return dict(scope='source_existing_grounded_address_endpoint_entry',
        source_pad_uuid=force._uid(pad),source_group_uuid=force._uid(groups[0]),
        source_group_name=groups[0].GetName(),source_tracks=sorted(members,key=lambda r:r['uuid']),
        entry_width_nm=narrow,preferred_class_width_nm=width,maximum_entry_centerline_nm=budget,
        full_class_native_via_throat_required=True,manufacturer_role_unchanged='address',
        functional_ground_return_or_current_authority=False,release_authority=False)


def _address_entry_geometry(board,proof,tracks):
    """Repeat the existing shared native classifier; a Source label is not proof."""
    entry=proof.get('source_address_entry')
    if entry is None:return None
    if (entry['entry_width_nm']!=proof['endpoint_escape'][0]
            or proof['diameter_nm']<proof['width_nm']
            or any(t.GetWidth()!=entry['entry_width_nm']for t in tracks)):
        raise ValueError('source_address_entry_width_or_native_via_throat_changed')
    qualified,rejected=fr._qualified_endpoint_neckdown_tracks(board,tracks,proof['width_nm'],
        required_clearance=proof['clearance_nm'])
    if rejected or {force._uid(t)for t in qualified}!={force._uid(t)for t in tracks}:
        raise ValueError('source_address_entry_shared_native_geometry_refused:'+str(rejected))
    return dict(shared_native_endpoint_classifier=True,source_entry_width_preserved=True,
        full_class_native_via_throat_received=True,track_uuids=sorted(force._uid(t)for t in tracks),
        current_qualified=False,release_authority=False)


def _split_native_land_exit(pad,legs):
    """Split only at a real canonical lattice contact with the native land.

    Native return observation has zero cost within actual land metal. A
    constructor may expose that real contact, rather than charging a long
    SMD land as external wire. No expanded land, fake junction or clearance
    exemption is created. The enclosing native guards still inspect metal.
    """
    result=[]
    for a,b,width in legs:
        pa,pb=tuple(a),tuple(b);dx,dy=pb[0]-pa[0],pb[1]-pa[1]
        steps=max(abs(dx),abs(dy))
        if (steps and quality.is_canonical_stroke(pa,pb,tolerance_nm=0)
                and pad.HitTest(a,0) and not pad.HitTest(b,0)):
            sx,sy=dx//steps,dy//steps;lo,hi=0,steps
            while hi-lo>1:
                mid=(lo+hi)//2;p=pcbnew.VECTOR2I(pa[0]+sx*mid,pa[1]+sy*mid)
                if pad.HitTest(p,0):lo=mid
                else:hi=mid
            contact=pcbnew.VECTOR2I(pa[0]+sx*lo,pa[1]+sy*lo)
            if contact!=a and contact!=b:
                result.append((a,contact,width));a=contact
        result.append((a,b,width))
    return result


def _new_surface_path_mm(pad,via,tracks):
    """The existing native endpoint metric on ONLY the incoming stub."""
    graph={};points={}
    for op in tracks:
        a,b=tuple(op[1]),tuple(op[2]);face=op[4]
        ka,kb=(*a,face),(*b,face)
        points[ka]=pcbnew.VECTOR2I(*a);points[kb]=pcbnew.VECTOR2I(*b)
        length=math.dist(a,b)/1e6
        graph.setdefault(ka,[]).append((kb,length));graph.setdefault(kb,[]).append((ka,length))
    return cell._query_explicit_track_path_mm((graph,points),pad,via,1)


def plan(parent,private,proposal,requests,*,timeout_s=10.):
    deadline=_lease(timeout_s)
    if type(requests)not in(list,tuple)or len(requests)>4:
        raise ValueError('bounded_explicit_new_ground_dogbones_required')
    if not requests:return [],[]
    source=Path(parent.GetFileName()).resolve();binding=row._source_binding(parent)
    if (not source.is_file()or proposal.get('source_native_binding')!=binding
            or row._source_binding(pcbnew.LoadBoard(str(source)))!=binding):
        raise ValueError('literal_saved_new_ground_source_required')
    family=force._family(source,proposal['board_hint'])
    profile_name=fab.board_profile_name(parent);profile=fab.get_profile(profile_name)if profile_name else None
    menu=fab.local_pofv_geometry_candidates(profile,board=parent)if profile else ()
    if not menu or fab.board_profile_name(private)!=profile_name:
        raise ValueError('existing_source_new_ground_process_menu_required')
    old={force._uid(p):p for f in parent.GetFootprints()for p in f.Pads()}
    live={force._uid(p):p for f in private.GetFootprints()for p in f.Pads()}
    proofs=[];columns=[];seen=set();sites=set()
    for request in requests:
        if time.monotonic()>=deadline:raise ValueError('new_ground_dogbone_plan_deadline')
        if (type(request)is not dict or set(request)!={'owner_pad_uuid','position_nm','geometry_index'}
                or type(request['owner_pad_uuid'])is not str or request['owner_pad_uuid']in seen
                or request['owner_pad_uuid']not in old or request['owner_pad_uuid']not in live
                or type(request['geometry_index'])is not int or not 0<=request['geometry_index']<len(menu)
                or type(request['position_nm'])not in(list,tuple)or len(request['position_nm'])!=2
                or any(type(v)is not int or abs(v)>2000000000 for v in request['position_nm'])
                or tuple(request['position_nm'])in sites):
            raise ValueError('unique_source_new_ground_pad_site_and_geometry_event_required')
        uid=request['owner_pad_uuid'];before,pad=old[uid],live[uid];fp=pad.GetParentFootprint();ref=fp.GetReference()
        face=cell.cec_return_escape.smd_surface_layer(pad)
        if (ref not in proposal['poses']or face is None or pad.HasHole()or pad.GetNetname()!='GND'
                or before.GetNetname()!='GND'or fp.IsDNP()or fp.IsLocked()
                or tuple(before.GetPosition())==tuple(pad.GetPosition())
                or tuple(fp.GetPosition())!=tuple(round(v*1e6)for v in proposal['poses'][ref][:2])
                or abs((fp.GetOrientationDegrees()-proposal['poses'][ref][2]+180)%360-180)>1e-9):
            raise ValueError('actual_moved_selected_bypass_surface_ground_and_immediate_site_required')
        device=_device_attachment(parent,before,proposal)
        if device is not None and roles.footprint_contract(fp)!=device['manufacturer']:
            raise ValueError('unchanged_source_device_attachment_manufacturer_required')
        authority=None
        if device is None:
            authority=leaf._bypass_supply_owner(parent,before,proposal['board_hint'],ground_return=True)
            owner=parent.FindFootprintByReference(authority.get('owner',''))
            model=roles.footprint_contract(owner)if owner else None
            if (not model or model['pins'].get(authority.get('supply_pin'))!='power_input'
                    or set(model['pins'].values())&{'power_output','switch','feedback'}):
                raise ValueError('positive_low_power_new_bypass_ground_owner_required')
        geometry=menu[request['geometry_index']];diameter,drill=[round(v*1e6)for v in geometry]
        # This first operator supports a separated off-pad seat at ordinary
        # native floors only. A center-only POFV rule cannot fund a dogbone.
        for board in(parent,private):
            if tuple(round(v*1e6)for v in fab.board_legal_through_via_geometry(board,*geometry)[:2])!=(diameter,drill):
                raise ValueError('new_ground_seat_must_meet_unchanged_ordinary_native_floors')
        column=_column(private,pad,request['position_nm'],diameter,drill)
        if (pad.GetEffectiveShape(face).Collide(column.GetEffectiveShape(face),0)
                or fr._via_pad_excluded(private,column.GetPosition(),diameter,drill,pad.GetNetCode())is not None
                or any(t.GetClass()=='PCB_VIA'and tuple(t.GetPosition())==tuple(column.GetPosition())
                    for t in private.GetTracks())):
            raise ValueError('new_ground_requires_separated_new_assembly_legal_seat')
        if (not fr._edge_leg_clear(private,column.GetPosition(),column.GetPosition(),diameter//2)
                or not cell._hole_to_hole_clear(private,column.GetPosition(),drill/1e6)[0]):
            raise ValueError('new_ground_existing_edge_or_drill_conflict')
        spec=cell._netclass(parent,'GND')
        width=max(200000,int(parent.GetDesignSettings().m_TrackMinWidth),int(spec['width']))
        gap=max(200000,int(parent.GetDesignSettings().m_MinClearance),int(spec['clearance']))
        previous=cell._existing_return(parent,before,16.,allow_native_track_body=True)
        reach=.8 if device is None else min(.8,device['source_return_mm'])
        # AABB separation is only a necessary screen, never path evidence.
        # Actual incoming native contacts are observed both before offering
        # and after saving; the electrical bound is not enlarged.
        work_nm=800000 if device is None else math.ceil(reach*1e6+
            math.hypot(*pad.GetSize())/2+diameter/2)
        distance=math.dist(tuple(pad.GetPosition()),request['position_nm'])
        if (not 0<distance<=work_nm or (device is not None
                and cell._return_path_aabb_lower_bound_mm(pad,column)>reach)):
            raise ValueError('actual_moved_selected_bypass_surface_ground_and_immediate_site_required')
        escape=(fr._pad_local_escape(pad,width,gap,
            max(200000,int(parent.GetDesignSettings().m_TrackMinWidth))) if device is not None else None)
        name='required-new-ground:'+force._hash(source)+':'+uid+':'+repr(tuple(column.GetPosition()))
        column.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,name))))
        proof=dict(schema=1,scope='source_required_new_immediate_bypass_ground_dogbone',
            source=str(source),source_sha256=force._hash(source),source_family=family,
            source_native_binding=binding,board_hint=proposal['board_hint'],pad_uuid=uid,owner=ref,
            target_pose=list(proposal['poses'][ref]),face=int(face),pad_point_nm=list(pad.GetPosition()),
            point_nm=list(column.GetPosition()),diameter_nm=diameter,drill_nm=drill,
            geometry_index=request['geometry_index'],source_process_geometry_menu_mm=[list(g)for g in menu],
            profile=profile_name,width_nm=width,clearance_nm=gap,maximum_surface_path_mm=.8,
            source_bypass_owner=authority,source_return_mm=previous[0]if previous else None,
            original_unknown_return_not_promoted_to_known=previous is None,
            actual_land_sha256=_digest(pad,deadline),proposal_column_uuid=force._uid(column),
            mandatory_new_saved_barrel_and_stub=True,no_power_window_or_current_credit=True,release_authority=False)
        if device is not None:
            proof.update(scope='source_required_new_immediate_device_ground_attachment_dogbone',
                source_device_attachment=device,maximum_surface_path_mm=reach,
                maximum_centerline_work_nm=work_nm,
                endpoint_escape=None if escape is None else list(escape),
                native_land_contact_metric_not_larger_electrical_reach=True)
            entry=_source_address_entry(parent,before,device,width,escape,diameter,deadline)
            if entry is not None:proof['source_address_entry']=entry
        proofs.append(proof)
        columns.append(column);seen.add(uid);sites.add(tuple(column.GetPosition()))
    if (row._source_binding(parent)!=binding or family!=force._family(source,proposal['board_hint'])
            or time.monotonic()>=deadline):
        raise ValueError('new_ground_source_changed_or_plan_expired')
    return proofs,columns


def rederive(board,proof,*,timeout_s=10.):
    deadline=_lease(timeout_s);source=Path(proof['source'])
    if not source.is_file()or force._hash(source)!=proof['source_sha256']:
        raise ValueError('new_ground_source_changed')
    parent=pcbnew.LoadBoard(str(source))
    fresh,_=plan(parent,board,dict(source_native_binding=row._source_binding(parent),
        board_hint=proof['board_hint'],poses={proof['owner']:proof['target_pose']}),
        [dict(owner_pad_uuid=proof['pad_uuid'],position_nm=proof['point_nm'],geometry_index=proof['geometry_index'])],
        timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if json.loads(json.dumps(fresh[0]))!=proof or time.monotonic()>=deadline:
        raise ValueError('new_ground_dogbone_stale_forged_or_expired')


def required_ops(proof,ops):
    try:
        if type(ops)not in(list,tuple)or not 2<=len(ops)<=16:return False
        vias=[o for o in ops if o[0]=='via'];tracks=[o for o in ops if o[0]=='trk']
        device=proof.get('scope')=='source_required_new_immediate_device_ground_attachment_dogbone'
        widths=all(o[3]==proof['width_nm'] for o in tracks)
        if device and proof.get('endpoint_escape') is not None:
            narrow,budget=proof['endpoint_escape'];used=0.;body=0.;full=False;widths=True
            for op in tracks:
                length=math.dist(op[1],op[2])
                if op[3]==proof['width_nm']:full=True;body+=length
                elif op[3]==narrow and not full:used+=length
                else:widths=False
            total=used+body
            # Same full-class throat reservation as the existing shared
            # endpoint profiler, not an all-thin device attachment.
            throat=min(250000,total*.25) if proof['width_nm']>=500000 else 0.
            widths=widths and used<=budget and body>0 and body+1e-6>=throat
            entry=proof.get('source_address_entry')
            if entry is not None and not full:
                widths=bool(entry['manufacturer_role_unchanged']=='address'
                    and entry['entry_width_nm']==narrow and proof['diameter_nm']>=proof['width_nm']
                    and all(o[3]==narrow for o in tracks)and used<=budget)
        return bool(len(vias)==1 and len(tracks)+1==len(ops)and list(vias[0][1])==proof['point_nm']
            and round(vias[0][2]*1e6)==proof['drill_nm']and round(vias[0][3]*1e6)==proof['diameter_nm']
            and list(tracks[0][1])==proof['pad_point_nm']and list(tracks[-1][2])==proof['point_nm']
            and all(list(a[2])==list(b[1])for a,b in zip(tracks,tracks[1:]))
            and widths and all(o[4]==proof['face']
                and quality.is_canonical_stroke(tuple(o[1]),tuple(o[2]),tolerance_nm=0)for o in tracks)
            and sum(math.dist(o[1],o[2])for o in tracks)<=
                (proof['maximum_centerline_work_nm'] if device else proof['maximum_surface_path_mm']*1e6))
    except(TypeError,ValueError,KeyError,IndexError,OverflowError):return False


def entry_ops(board,proof,*,timeout_s=10.):
    deadline=_lease(timeout_s);rederive(board,proof,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==proof['pad_uuid'])
    at=pcbnew.VECTOR2I(*proof['point_nm']);dia=proof['diameter_nm'];drill=proof['drill_nm'];gap=proof['clearance_nm']
    detail=dict(scope='exact_required_new_ground_dogbone_offer',found=False,no_path_proof=False,release_authority=False)
    spot={};clear=bool(fr._edge_leg_clear(board,at,at,dia//2+gap)
        and cell._hole_to_hole_clear(board,at,drill/1e6)[0]
        and fr._via_spot_clear(board,at,dia,gap,{pad.GetNetCode()},drill_nm=drill,
            net_code=pad.GetNetCode(),foreign_cache={},report=spot))
    detail['native_column_admission']=spot
    if not clear or time.monotonic()>=deadline:return [],detail
    via=_column(board,pad,proof['point_nm'],dia,drill)
    try:detail['reference_contacts']=reference._reference_contacts(board,via)
    except ValueError as exc:detail['reference_refusal']=str(exc);return [],detail
    device=proof.get('scope')=='source_required_new_immediate_device_ground_attachment_dogbone'
    extra={}
    entry=proof.get('source_address_entry')
    route_width=proof['width_nm']if entry is None else entry['entry_width_nm']
    if device and proof['endpoint_escape'] is not None and entry is None:
        extra=dict(start_escape=tuple(proof['endpoint_escape']),end_escape=(proof['width_nm'],0))
    legs=fr._guarded_profiled_lastmile_legs(board,pad.GetPosition(),at,route_width,proof['face'],gap,
        pad.GetNetCode(),lambda s,t,h:fr._edge_leg_clear(board,s,t,h+gap),foreign_cache={},
        deadline_monotonic=deadline,allow_maze=True,refine_maze=True,endpoint_detail_grid_mm=.2,
        compact_phase_jogs=True,max_length_nm=proof.get('maximum_centerline_work_nm',800000),
        search_diagnostics=detail,**extra)
    if device and legs:legs=_split_native_land_exit(pad,legs)
    ops=[('trk',tuple(s),tuple(t),int(w),proof['face'])for s,t,w in legs]if legs else []
    ops.append(('via',tuple(at),drill/1e6,dia/1e6))
    if not required_ops(proof,ops)or time.monotonic()>=deadline:return [],detail
    if entry is not None:
        # This temporary material supplies no retained success/ownership.
        # Saved receiving below repeats the same proof on actual saved items.
        from cec_native_items import discard_items
        temporary=[];before=row._source_binding(board)
        try:
            for op in ops:
                if op[0]=='via':item=_column(board,pad,op[1],dia,drill)
                else:
                    item=pcbnew.PCB_TRACK(board);item.SetNet(pad.GetNet());item.SetLayer(op[4])
                    item.SetStart(pcbnew.VECTOR2I(*op[1]));item.SetEnd(pcbnew.VECTOR2I(*op[2]));item.SetWidth(op[3])
                board.Add(item);temporary.append(item)
            detail['source_address_entry_native_geometry']=_address_entry_geometry(board,proof,
                [t for t in temporary if t.GetClass()=='PCB_TRACK'])
        finally:
            discard_items(board,temporary)
            if row._source_binding(board)!=before:raise ValueError('source_address_entry_offer_changed_board')
    if device:
        distance=_new_surface_path_mm(pad,via,[o for o in ops if o[0]=='trk'])
        detail['incoming_native_surface_path_mm']=distance
        if distance is None or distance>proof['maximum_surface_path_mm']:return [],detail
    detail['found']=True
    return ops,detail


def receive(board,proofs,incoming,*,timeout_s=10.):
    deadline=_lease(timeout_s);observed=[]
    for proof in proofs:
        if time.monotonic()>=deadline:raise ValueError('new_ground_saved_observation_deadline')
        # The complete receiver independently recompiled the proof before
        # this saved-material observation. No live-plan proof is inherited.
        pad=next((p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==proof['pad_uuid']),None)
        if pad is None or _digest(pad,deadline)!=proof['actual_land_sha256']:
            raise ValueError('required_new_saved_ground_land_changed')
        matches=[t for t in board.GetTracks()if force._uid(t)in incoming and t.GetClass()=='PCB_VIA'
            and t.GetNetname()=='GND'and list(t.GetPosition())==proof['point_nm']
            and t.GetDrillValue()==proof['drill_nm']and t.GetViaType()==pcbnew.VIATYPE_THROUGH
            and t.TopLayer()==pcbnew.F_Cu and t.BottomLayer()==pcbnew.B_Cu
            and all(t.GetWidth(l)==proof['diameter_nm']for l in board.GetEnabledLayers().CuStack())]
        if len(matches)!=1:raise ValueError('required_new_saved_ground_dogbone_not_constructed')
        via=matches[0];distance=cell._shortest_track_path_mm(board,pad,via,snap_mm=.000001)
        if distance is None or distance>proof['maximum_surface_path_mm']:
            raise ValueError('required_new_saved_ground_has_no_immediate_terminal_path')
        if tuple(round(v*1e6)for v in fab.board_legal_through_via_geometry(board,
                proof['diameter_nm']/1e6,proof['drill_nm']/1e6)[:2])!=(proof['diameter_nm'],proof['drill_nm']):
            raise ValueError('new_saved_ground_ordinary_native_process_changed')
        # Independently observe the promised NEW full-class surface stub,
        # not a thin/other-face path accepted merely by native connectivity.
        device=proof.get('scope')=='source_required_new_immediate_device_ground_attachment_dogbone'
        allowed_widths={proof['width_nm']}
        if device and proof['endpoint_escape'] is not None:allowed_widths.add(proof['endpoint_escape'][0])
        edges={}
        for track in board.GetTracks():
            if (force._uid(track)not in incoming or track.GetClass()!='PCB_TRACK'
                    or track.GetNetname()!='GND'or track.GetLayer()!=proof['face']
                    or track.GetWidth()not in allowed_widths):continue
            a,b=tuple(track.GetStart()),tuple(track.GetEnd())
            if not quality.is_canonical_stroke(a,b,tolerance_nm=0):continue
            op=('trk',a,b,int(track.GetWidth()),int(track.GetLayer()))
            edges.setdefault(a,[]).append((b,op));edges.setdefault(b,[]).append((a,('trk',b,a,op[3],op[4])))
        start=tuple(pad.GetPosition());target=tuple(via.GetPosition());queue=[(0.,start,[])];best={start:0.};path=None
        while queue:
            if time.monotonic()>=deadline:raise ValueError('new_ground_saved_surface_path_deadline')
            length,point,ops=heapq.heappop(queue)
            work=proof.get('maximum_centerline_work_nm',proof['maximum_surface_path_mm']*1e6)
            if length!=best.get(point)or length>work:continue
            if point==target:path=ops;break
            for other,op in edges.get(point,[]):
                cost=length+math.dist(point,other)
                if cost<best.get(other,float('inf'))and len(ops)<15:
                    best[other]=cost;heapq.heappush(queue,(cost,other,ops+[op]))
        actual=(path or [])+[('via',target,proof['drill_nm']/1e6,proof['diameter_nm']/1e6)]
        if not required_ops(proof,actual):
            raise ValueError('new_saved_ground_requires_literal_incoming_full_class_surface_stub')
        incoming_distance=_new_surface_path_mm(pad,via,path or [])
        if incoming_distance is None or incoming_distance>proof['maximum_surface_path_mm']:
            raise ValueError('new_saved_ground_incoming_native_surface_path_too_long')
        entry_proof=None
        if proof.get('source_address_entry')is not None:
            source=Path(proof['source'])
            if force._hash(source)!=proof['source_sha256']:raise ValueError('source_address_entry_source_changed')
            parent=pcbnew.LoadBoard(str(source))
            original=next(p for f in parent.GetFootprints()for p in f.Pads()if force._uid(p)==proof['pad_uuid'])
            device=_device_attachment(parent,original,dict(board_hint=proof['board_hint']))
            spec=cell._netclass(parent,'GND')
            actual_width=max(200000,int(parent.GetDesignSettings().m_TrackMinWidth),int(spec['width']))
            actual_gap=max(200000,int(parent.GetDesignSettings().m_MinClearance),int(spec['clearance']))
            actual_escape=fr._pad_local_escape(pad,actual_width,actual_gap,
                max(200000,int(parent.GetDesignSettings().m_TrackMinWidth)))
            if (device is None or proof['width_nm']!=actual_width or proof['clearance_nm']!=actual_gap
                    or actual_escape is None or list(actual_escape)!=proof['endpoint_escape']
                    or proof['maximum_surface_path_mm']!=min(.8,device['source_return_mm'])):
                raise ValueError('source_address_entry_actual_source_class_or_return_changed')
            fresh=_source_address_entry(parent,original,device,proof['width_nm'],
                tuple(proof['endpoint_escape']),proof['diameter_nm'],deadline)
            if fresh!=proof['source_address_entry']:raise ValueError('source_address_entry_stale_or_forged')
            path_strokes={(tuple(op[1]),tuple(op[2]),op[3],op[4])for op in path or []}
            tracks=[t for t in board.GetTracks()if force._uid(t)in incoming and t.GetClass()=='PCB_TRACK'
                and ((tuple(t.GetStart()),tuple(t.GetEnd()),int(t.GetWidth()),int(t.GetLayer()))in path_strokes
                    or (tuple(t.GetEnd()),tuple(t.GetStart()),int(t.GetWidth()),int(t.GetLayer()))in path_strokes)]
            entry_proof=_address_entry_geometry(board,proof,tracks)
        observed.append(dict(pad_uuid=proof['pad_uuid'],via_uuid=force._uid(via),surface_path_mm=distance,
            reference_contacts=reference._reference_contacts(board,via),exact_new_return_constructed=True,
            literal_incoming_full_class_surface_stub_received=entry_proof is None,
            source_address_entry_native_geometry=entry_proof,
            incoming_native_surface_path_mm=incoming_distance,
            original_unknown_return_not_promoted_to_known=proof['original_unknown_return_not_promoted_to_known'],
            current_qualified=False,release_authority=False))
    if time.monotonic()>=deadline:raise ValueError('new_ground_saved_observation_deadline')
    return observed
