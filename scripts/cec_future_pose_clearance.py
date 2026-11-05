"""Clear an ordinary route from a proposed support seat BEFORE moving a land.

The immutable source is inspected with detached native footprint copies. Only
exact foreign ordinary tracks may be retired; power, paired/sense copper,
barrels, groups and filled power territories are never displaced. Disposable
native permission polygons reserve the future foreign lands during rerouting.
An independently received prefix retains all original poses and connections.
This is not permission to apply the poses or transfer old placement authority.
"""
from pathlib import Path
import argparse
import json
import math
import subprocess
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_cell_row_rebuild as row_rebuild
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_fill_geometry as native
import cec_ordinary_route_receiving as ordinary
import cec_rectilinear_copper as contour
import cec_stage_admission as stage
import cec_support_motion as motion
from cec_native_items import discard_items


ERROR_NM = 1000


def _budget(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=10:
        raise ValueError('finite_future_pose_budget_required')
    return float(value)


def _future_pads(board, poses):
    if type(poses) is not dict or not 1<=len(poses)<=motion.MAX_REFS:
        raise ValueError('bounded_explicit_future_poses_required')
    footprints={fp.GetReference():fp for fp in board.GetFootprints()}
    if len(footprints)!=len(list(board.GetFootprints())):
        raise ValueError('ambiguous_source_footprint_identity')
    copies=[];pads=[];proofs=[]
    for ref,target in sorted(poses.items()):
        if (ref not in footprints or type(target) not in (list,tuple) or len(target)!=3
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in target)
                or abs(target[2]/90-round(target[2]/90))>1e-9):
            raise ValueError('finite_native_quarter_turn_pose_required')
        fp=footprints[ref];at=fp.GetPosition()
        domain=motion.capture(board,dict(ref=ref),motion.limits())
        proof=motion.evaluate(domain,dict(dx_mm=target[0]-at.x/1e6,
            dy_mm=target[1]-at.y/1e6,rotation_delta_deg=target[2]-fp.GetOrientationDegrees()))
        if not proof['ok']:raise ValueError('future_pose_outside_support_envelope:'+ref)
        # FOOTPRINT(copy) is a native deep geometric copy. It is deliberately
        # never added: duplicate child UUIDs or a temporary short must not
        # enter the source's connectivity or trigger net propagation.
        clone=pcbnew.FOOTPRINT(fp);copies.append(clone)
        clone.SetOrientationDegrees(target[2])
        clone.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in target[:2])))
        # Future copper preclear cannot grant a body/pad permission that the
        # actual local placement stage would reject. Check detached native
        # geometry before investing in any routing or retiring an edge.
        import cec_pi_cleanup as cleanup
        cleanup._pose_native_permissions(board,clone)
        for pad in clone.Pads():
            layers=tuple(pad.GetLayerSet().CuStack())
            if len(layers)!=1 or layers[0]!=fp.GetLayer():
                raise ValueError('single_face_support_land_required')
            pads.append((ref,pad,int(layers[0])))
        proofs.append(dict(ref=ref,source_pose_mm=[at.x/1e6,at.y/1e6,fp.GetOrientationDegrees()],
            target_pose_mm=list(target),motion=proof))
    return copies,pads,proofs


def _cut_boundaries(board, retired, deadline):
    """Real surviving contacts of cut groups, not obsolete internal bends.

    A retained pad/barrel/tee may meet the MIDDLE of a retired edge. Endpoint
    enumeration alone abandons that native source conductor, even when the
    two end trees reconnect successfully. Include exact surviving centres or
    track ends on actual removed copper; never invent same-name-island access.
    The independent whole-source partition receiver remains mandatory.
    """
    pending={force._uid(t):t for t in board.GetTracks() if force._uid(t) in retired}
    surviving=[p for fp in board.GetFootprints() for p in fp.Pads()]
    surviving += [t for t in board.GetTracks() if force._uid(t) not in retired]
    result=[]
    while pending:
        seed=pending.pop(min(pending));group=[seed];queue=[seed]
        while queue:
            a=queue.pop()
            for uid,b in list(pending.items()):
                contour._check_deadline(deadline)
                if (a.GetNetCode()==b.GetNetCode() and a.GetLayer()==b.GetLayer()
                        and a.GetEffectiveShape(a.GetLayer()).Collide(b.GetEffectiveShape(b.GetLayer()),0)):
                    group.append(b);queue.append(b);del pending[uid]
        layer=seed.GetLayer();anchors=set()
        for edge in group:
            for at in (edge.GetStart(),edge.GetEnd()):
                marker=pcbnew.SHAPE_SEGMENT(at,at,1)
                for other in surviving:
                    contour._check_deadline(deadline)
                    if (other.GetNetCode()==edge.GetNetCode() and other.IsOnLayer(layer)
                            and other.GetEffectiveShape(layer).Collide(marker,0)):
                        anchors.add(tuple(at));break
            shape=edge.GetEffectiveShape(layer)
            for other in surviving:
                contour._check_deadline(deadline)
                if other.GetNetCode()!=edge.GetNetCode() or not other.IsOnLayer(layer):continue
                if other.GetClass() in ('PAD','PCB_VIA'):
                    sites=(tuple(other.GetPosition()),)
                elif other.GetClass()=='PCB_TRACK':
                    sites=(tuple(other.GetStart()),tuple(other.GetEnd()))
                else:continue
                for point in sites:
                    marker=pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*point),pcbnew.VECTOR2I(*point),1)
                    if (shape.Collide(marker,0)
                            and other.GetEffectiveShape(layer).Collide(marker,0)):
                        anchors.add(point)
                if len(anchors)>32:raise ValueError('finite_native_cut_contact_boundary_required')
        result.append(dict(net=str(seed.GetNetname()),layer=board.GetLayerName(layer),
            width_nm=max(int(t.GetWidth()) for t in group),anchors_nm=[list(a) for a in sorted(anchors)],
            retired_track_uuids=sorted(force._uid(t) for t in group)))
    return result


def plan(board, poses, *, source, board_hint, allow_locked_track_uuids=(), timeout_s=10.):
    """Read-only exact blocker inventory and source-bound native reservations."""
    deadline=time.monotonic()+_budget(timeout_s)
    unlock=ordinary._ids(allow_locked_track_uuids,'future_pose_locked_scope',32)
    source=Path(source).resolve();binding=row_rebuild._source_binding(board)
    copies,pads,proofs=_future_pads(board,poses)
    eligible=ordinary.eligible_nets(board,source,board_hint)
    local=fr._foreign_clearance_resolver(board)
    minimum=int(board.GetDesignSettings().m_MinClearance)
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    tracks={force._uid(t):t for t in board.GetTracks()}
    blockers=[];retired=set();lands=[]
    for ref,pad,layer in pads:
        contour._check_deadline(deadline)
        shape=pcbnew.SHAPE_POLY_SET()
        pad.TransformShapeToPolygon(shape,layer,0,ERROR_NM,pcbnew.ERROR_OUTSIDE,False)
        if shape.OutlineCount()!=1 or shape.HoleCount(0):
            raise ValueError('simple_drill_free_future_land_required')
        gap=max(minimum,int(local(pad,layer)))
        lands.append(dict(ref=ref,pad=str(pad.GetNumber()),uuid=force._uid(pad),
            net=str(pad.GetNetname()),layer=board.GetLayerName(layer),clearance_nm=gap,
            polygons_nm=native.snapshot(shape,deadline,max_vertices=4096,max_polygons=1)))
        for uid,item in tracks.items():
            contour._check_deadline(deadline)
            if not item.IsOnLayer(layer) or item.GetNetCode()==pad.GetNetCode():continue
            clearance=max(gap,int(local(item,layer)))
            if not shape.Collide(item.GetEffectiveShape(layer),clearance):continue
            removable=(item.GetClass()=='PCB_TRACK' and uid not in grouped
                and str(item.GetNetname()) in eligible and 0<item.GetWidth()<500000
                and (not item.IsLocked() or uid in unlock))
            blockers.append(dict(ref=ref,pad=str(pad.GetNumber()),uuid=uid,
                kind=item.GetClass(),net=str(item.GetNetname()),layer=board.GetLayerName(layer),
                clearance_nm=clearance,ordinary_retirement_allowed=removable))
            if removable:retired.add(uid)
        # Static foreign pads and protected filled territories are not route
        # edges. A placement replan, not a broader retirement, is required.
        for fp in [*copies,*[f for f in board.GetFootprints() if f.GetReference() not in poses]]:
            for other in fp.Pads():
                contour._check_deadline(deadline)
                if not other.IsOnLayer(layer) or other.GetNetCode()==pad.GetNetCode():continue
                if force._uid(other)==force._uid(pad) and fp.GetReference()==ref:continue
                if shape.Collide(other.GetEffectiveShape(layer),max(gap,int(local(other,layer)))):
                    blockers.append(dict(ref=ref,pad=str(pad.GetNumber()),uuid=force._uid(other),
                        kind='PAD',net=str(other.GetNetname()),ordinary_retirement_allowed=False))
        for zone in board.Zones():
            contour._check_deadline(deadline)
            if not zone.IsOnLayer(layer):continue
            if zone.GetIsRuleArea():
                # Only footprint placement is prohibited by this flag.
                # A track-only keepout is not a ban on otherwise legal lands.
                hit=zone.GetDoNotAllowFootprints() and shape.Collide(zone.Outline(),0)
            elif zone.GetNetCode()==pad.GetNetCode() or zone.GetNetname()=='GND':
                continue  # Existing GND-only refill is explicit in receiving.
            else:
                if not zone.IsFilled() or not zone.HasFilledPolysForLayer(layer):
                    raise ValueError('future_land_foreign_fill_unknown')
                hit=shape.Collide(zone.GetFilledPolysList(layer),max(gap,int(local(zone,layer))))
            if hit:blockers.append(dict(ref=ref,pad=str(pad.GetNumber()),uuid=force._uid(zone),
                kind='ZONE',net=str(zone.GetNetname()),ordinary_retirement_allowed=False))
    if len(retired)>32:raise ValueError('future_pose_retirement_scope_bound')
    if not unlock<=retired:raise ValueError('locked_permission_outside_actual_blockers')
    if row_rebuild._source_binding(board)!=binding:raise ValueError('read_only_future_pose_changed_source')
    result=dict(schema=1,scope='future_land_ordinary_preclear_not_pose_or_release_admission',
        source_sha256=force._hash(source),source_binding=binding,board_hint=board_hint,
        poses=proofs,lands=lands,blockers=blockers,retired_track_uuids=sorted(retired),
        allow_locked_track_uuids=sorted(unlock),
        affected_ordinary_nets=sorted({str(tracks[u].GetNetname()) for u in retired}),
        cut_boundaries=_cut_boundaries(board,retired,deadline),
        ok=all(r['ordinary_retirement_allowed'] for r in blockers),
        future_land_geometry_error_nm=ERROR_NM,board_mutated=False,release_authority=False)
    result['plan_sha256']=contour._digest(result)
    return result


def _extend_ordinary_cut(board, retired, eligible, grouped, unlock, deadline, limit_mm,
                         reserved_shapes=()):
    """Follow only exact degree-two source track joints to safer cut anchors.

    No pad, barrel, branch, group, arc or wider/power route can be swallowed.
    Locked extensions remain explicit refused blockers until their exact IDs
    receive permission. This is source-topology scope, not a spatial rip-up.
    """
    if (type(limit_mm) not in (int,float) or not math.isfinite(limit_mm)
            or not 0<=limit_mm<=10):
        raise ValueError('finite_source_cut_extension_bound_required')
    if not limit_mm:return []
    tracks=list(board.GetTracks());pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    seen=set(retired);queue=[(t,bool(reserved_shapes)) for t in sorted(tracks,key=force._uid)
        if force._uid(t) in retired];deferred=[];visited=set()
    length=0.;result=[]
    while (queue or deferred) and len(result)<16:
        if not queue:queue,deferred=deferred,[]
        edge,prioritize=queue.pop(0);layer=edge.GetLayer()
        key=(force._uid(edge),prioritize)
        if key in visited:continue
        visited.add(key)
        for at in (edge.GetStart(),edge.GetEnd()):
            contour._check_deadline(deadline)
            marker=pcbnew.SHAPE_SEGMENT(at,at,1)
            # Extend trapped cut ends before spending the bounded scope on a
            # perfectly usable external end. Only source-derived reservations
            # supply this optional scheduling hint; native ownership is still
            # established by the degree-two contact checks below.
            if prioritize and not any(shape.Collide(marker,0) for shape in reserved_shapes):
                deferred.append((edge,False));continue
            def touches(item):
                return (item.GetNetCode()==edge.GetNetCode() and item.IsOnLayer(layer)
                    and item.GetEffectiveShape(layer).Collide(marker,0))
            if any(touches(p) for p in pads):continue
            incident=[t for t in tracks if touches(t)]
            if len(incident)!=2:continue
            other=next((t for t in incident if force._uid(t)!=force._uid(edge)),None)
            if other is None or force._uid(other) in seen:continue
            uid=force._uid(other)
            if (other.GetClass()!='PCB_TRACK' or other.GetLayer()!=layer or uid in grouped
                    or str(other.GetNetname()) not in eligible or not 0<other.GetWidth()<500000
                    or tuple(at) not in (tuple(other.GetStart()),tuple(other.GetEnd()))):continue
            added=math.dist(tuple(other.GetStart()),tuple(other.GetEnd()))
            if length+added>limit_mm*1e6:continue
            length+=added;seen.add(uid);queue.append((other,prioritize))
            result.append(dict(uuid=uid,kind='PCB_TRACK',net=str(other.GetNetname()),
                layer=board.GetLayerName(layer),source_degree_two_contact_nm=list(at),
                source_length_nm=round(added),ordinary_retirement_allowed=not other.IsLocked() or uid in unlock))
    return result


def plan_ground_reference_links(board, reference_pad_uuids, *, source, board_hint,
                                allow_locked_track_uuids=(), timeout_s=10., cut_extension_mm=0.,
                                owner_ground=False):
    """Preclear a real isolated, explicitly grounded manufacturer REF land.

    The destination is the source-selected bypass return already connected to
    that IC's true ground, or that independently verified ground land itself.
    Workers cannot supply a net, coordinate, invented
    capacitor or arbitrary keepout. This reserves an orthogonal class-width
    local link, not permission to move either package or waive source debt.
    Only source-owned ordinary blocker tracks are eligible for reconstruction.
    """
    import cec_local_branch_access as access
    import cec_decoupler_cell as cells
    if type(owner_ground) is not bool:
        raise ValueError('explicit_source_ground_destination_mode_required')
    deadline=time.monotonic()+_budget(timeout_s)
    wanted=ordinary._ids(reference_pad_uuids,'ground_reference_link_targets',4)
    if not wanted:raise ValueError('nonempty_ground_reference_link_targets_required')
    unlock=ordinary._ids(allow_locked_track_uuids,'future_link_locked_scope',32)
    source=Path(source).resolve();binding=row_rebuild._source_binding(board)
    tasks={r['pad_uuid']:r for r in access.targets(board,board_hint=board_hint)
        if r['role']=='ground_reference'}
    if not wanted<=tasks.keys():raise ValueError('source_isolated_ground_reference_link_required')
    eligible=ordinary.eligible_nets(board,source,board_hint)
    local=fr._foreign_clearance_resolver(board)
    minimum=int(board.GetDesignSettings().m_MinClearance)
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    tracks={force._uid(t):t for t in board.GetTracks()}
    blockers=[];retired=set();lands=[];links=[]
    for uid in sorted(wanted):
        task=tasks[uid]
        a=board.FindFootprintByReference(task['owner']).FindPadByNumber(task['pin'])
        destination=dict(ref=task['cap'],pin=task['cap_pad'],uuid=task['destination_uuid'],
            role='assigned_bypass_return',at_nm=task['b_nm'])
        if owner_ground:
            alternatives=task['verified_ground_alternatives']
            if len(alternatives)!=1:
                raise ValueError('unique_source_verified_owner_ground_destination_required')
            destination=dict(alternatives[0])
        b=board.FindFootprintByReference(destination['ref']).FindPadByNumber(destination['pin'])
        if force._uid(b)!=destination['uuid'] or list(b.GetPosition())!=destination['at_nm']:
            raise ValueError('source_ground_destination_identity_changed')
        layers=set(a.GetLayerSet().CuStack())&set(b.GetLayerSet().CuStack())
        if len(layers)!=1 or a.HasHole() or b.HasHole():
            raise ValueError('single_surface_ground_reference_link_required')
        layer=next(iter(layers));spec=cells._netclass(board,a.GetNetname())
        width=max(int(board.GetDesignSettings().m_TrackMinWidth),int(spec['width']))
        gap=max(minimum,int(spec['clearance']),200000)
        points=[list(a.GetPosition()),[a.GetPosition().x,b.GetPosition().y],list(b.GetPosition())]
        points=[p for i,p in enumerate(points) if not i or p!=points[i-1]]
        shape=pcbnew.SHAPE_POLY_SET()
        for left,right in zip(points,points[1:]):
            edge=pcbnew.PCB_TRACK(board);edge.SetLayer(layer);edge.SetWidth(width)
            edge.SetStart(pcbnew.VECTOR2I(*left));edge.SetEnd(pcbnew.VECTOR2I(*right))
            polygon=pcbnew.SHAPE_POLY_SET()
            edge.TransformShapeToPolygon(polygon,layer,0,ERROR_NM,pcbnew.ERROR_OUTSIDE,False)
            shape.BooleanAdd(polygon)
        if shape.OutlineCount()!=1 or shape.HoleCount(0):
            raise ValueError('simple_native_ground_reference_link_required')
        row=dict(ref=task['owner'],pad=task['pin'],uuid=uid,net=task['net'],
            layer=board.GetLayerName(layer),clearance_nm=gap,
            polygons_nm=native.snapshot(shape,deadline,max_vertices=4096,max_polygons=1))
        lands.append(row);links.append(dict(task=task,destination=destination,
            points_nm=points,width_nm=width,layer=int(layer)))
        for item in [*tracks.values(),*(p for fp in board.GetFootprints() for p in fp.Pads())]:
            contour._check_deadline(deadline)
            if not item.IsOnLayer(layer) or item.GetNetCode()==a.GetNetCode():continue
            clearance=max(gap,int(local(item,layer)))
            if not shape.Collide(item.GetEffectiveShape(layer),clearance):continue
            identity=force._uid(item)
            removable=(item.GetClass()=='PCB_TRACK' and identity not in grouped
                and str(item.GetNetname()) in eligible and 0<item.GetWidth()<500000
                and (not item.IsLocked() or identity in unlock))
            blockers.append(dict(ref=task['owner'],pad=task['pin'],uuid=identity,
                kind=item.GetClass(),net=str(item.GetNetname()),layer=board.GetLayerName(layer),
                clearance_nm=clearance,ordinary_retirement_allowed=removable))
            if removable:retired.add(identity)
        for zone in board.Zones():
            contour._check_deadline(deadline)
            if not zone.IsOnLayer(layer):continue
            if zone.GetIsRuleArea():
                hit=zone.GetDoNotAllowTracks() and shape.Collide(zone.Outline(),0)
            elif zone.GetNetCode()==a.GetNetCode():continue
            else:
                if not zone.IsFilled() or not zone.HasFilledPolysForLayer(layer):
                    raise ValueError('ground_reference_foreign_fill_unknown')
                hit=shape.Collide(zone.GetFilledPolysList(layer),max(gap,int(local(zone,layer))))
            if hit:blockers.append(dict(ref=task['owner'],pad=task['pin'],uuid=force._uid(zone),
                kind='ZONE',net=str(zone.GetNetname()),ordinary_retirement_allowed=False))
    reservations=[]
    for land in lands:
        reserved=native.reconstruct(land['polygons_nm'],deadline,max_vertices=4096,max_polygons=1)
        reserved.Inflate(land['clearance_nm']+300000+2*ERROR_NM,
            pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,ERROR_NM)
        reservations.append(reserved)
    extensions=_extend_ordinary_cut(board,retired,eligible,grouped,unlock,deadline,cut_extension_mm,
        reserved_shapes=reservations)
    blockers.extend(extensions)
    retired.update(r['uuid'] for r in extensions if r['ordinary_retirement_allowed'])
    if len(retired)>32:raise ValueError('ground_reference_retirement_scope_bound')
    if not unlock<=retired:raise ValueError('locked_permission_outside_actual_blockers')
    if row_rebuild._source_binding(board)!=binding:raise ValueError('future_reference_link_changed_source')
    result=dict(schema=1,scope='source_ground_reference_link_ordinary_preclear',
        source_sha256=force._hash(source),source_binding=binding,board_hint=board_hint,
        reference_pad_uuids=sorted(wanted),owner_ground=owner_ground,
        links=links,poses=[],lands=lands,blockers=blockers,
        cut_extension_mm=float(cut_extension_mm),source_owned_cut_extensions=extensions,
        retired_track_uuids=sorted(retired),allow_locked_track_uuids=sorted(unlock),
        affected_ordinary_nets=sorted({str(tracks[u].GetNetname()) for u in retired}),
        cut_boundaries=_cut_boundaries(board,retired,deadline),
        ok=all(r['ordinary_retirement_allowed'] for r in blockers),
        board_mutated=False,release_authority=False,reference_link_not_yet_constructed=True)
    result['plan_sha256']=contour._digest(result)
    return result


def _install_reservations(board, proposal, net, deadline):
    local=fr._project_netclass_resolver(board.GetFileName())
    route_gap=max(int(board.GetDesignSettings().m_MinClearance),
        fr._nm(float((local(net) or {}).get('clearance') or 0)))
    zones=[]
    try:
        for row in proposal['lands']:
            if row['net']==net:continue
            shape=native.reconstruct(row['polygons_nm'],deadline,max_vertices=4096,max_polygons=1)
            # Outer chords plus a second native offset need explicit outward
            # error reserve. This planning reserve adds no manufactured copper.
            shape.Inflate(max(route_gap,row['clearance_nm'])+2*ERROR_NM,
                pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,ERROR_NM)
            polygons=native.snapshot(shape,deadline,max_vertices=4096,max_polygons=1)
            z=pcbnew.ZONE(board);z.SetLayer(board.GetLayerID(row['layer']))
            z.SetIsRuleArea(True);z.SetDoNotAllowTracks(True);z.SetDoNotAllowVias(True)
            z.SetDoNotAllowFootprints(False);z.SetDoNotAllowZoneFills(False)
            z.SetZoneName('TEMP FUTURE LAND '+row['ref']+'.'+row['pad'])
            # Modifying the owned outline avoids the SWIG SetOutline lifetime
            # hazard. Never pass a borrowed temporary polygon into SetOutline.
            z.Outline().NewOutline()
            for x,y in polygons[0][0]:z.Outline().Append(x,y)
            board.Add(z);zones.append(z)
        return zones
    except Exception:
        discard_items(board,zones)
        raise


def plan_native_portals(board, portal_pad_uuids, *, source, board_hint,
                        via_diameter_nm, via_drill_nm, allow_locked_track_uuids=(),
                        timeout_s=10.,cut_extension_mm=0.):
    """Reserve actual process-qualified SMD via seats across the whole stack.

    A portal is only a future geometric demand. It does not add a barrel,
    authorize current, waive spacing, or displace power/pairs/ground/pads.
    Only independently typed ordinary source edges can be reconstructed.
    """
    import cec_fab_profile as fab
    deadline=time.monotonic()+_budget(timeout_s)
    wanted=ordinary._ids(portal_pad_uuids,'native_portal_lands',8)
    unlock=ordinary._ids(allow_locked_track_uuids,'native_portal_locked_scope',32)
    if (not wanted or type(via_diameter_nm) is not int or type(via_drill_nm) is not int
            or not 0<via_drill_nm<via_diameter_nm<=2000000):
        raise ValueError('explicit_bounded_native_portal_geometry_required')
    source=Path(source).resolve();binding=row_rebuild._source_binding(board)
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    by_uid={force._uid(p):p for p in pads}
    if len(by_uid)!=len(pads) or not wanted<=by_uid.keys():
        raise ValueError('unambiguous_actual_source_portal_lands_required')
    eligible=ordinary.eligible_nets(board,source,board_hint)
    local=fr._foreign_clearance_resolver(board)
    resolver=fr._project_netclass_resolver(str(source))
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    tracks={force._uid(t):t for t in board.GetTracks()}
    blockers=[];retired=set();lands=[];portals=[];reservations=[]
    for uid in sorted(wanted):
        contour._check_deadline(deadline)
        pad=by_uid[uid];fp=pad.GetParentFootprint();at=pad.GetPosition()
        if (fp.GetAttributes()&pcbnew.FP_DNP or pad.HasHole() or pad.GetNetCode()<=0
                or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                or len(tuple(pad.GetLayerSet().CuStack()))!=1):
            raise ValueError('populated_single_face_native_portal_land_required')
        decision=fab.via_pad_decision(board,pad,at,via_diameter_nm,via_drill_nm,pad.GetNetCode())
        if decision[0] is not True:raise ValueError('native_portal_process_refused:'+decision[1])
        foreign_pad,qualified=fab.via_at_pad_conflicts(board,at,via_diameter_nm,via_drill_nm,pad.GetNetCode())
        if foreign_pad is not None:raise ValueError('native_portal_pad_or_hole_obstruction')
        via=pcbnew.PCB_VIA(board);via.SetPosition(at);via.SetNetCode(pad.GetNetCode())
        via.SetWidth(via_diameter_nm);via.SetDrill(via_drill_nm)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        spec=resolver(str(pad.GetNetname())) or {}
        gap=max(int(board.GetDesignSettings().m_MinClearance),200000,
            fr._nm(float(spec.get('clearance') or 0)))
        portals.append(dict(pad_uuid=uid,ref=fp.GetReference(),pin=str(pad.GetNumber()),
            net=str(pad.GetNetname()),at_nm=list(at),process_decision=decision[1],
            proposed_barrel_not_constructed=True,current_capacity_credited=False))
        for layer in board.GetEnabledLayers().CuStack():
            contour._check_deadline(deadline)
            shape=pcbnew.SHAPE_POLY_SET()
            via.TransformShapeToPolygon(shape,layer,0,ERROR_NM,pcbnew.ERROR_OUTSIDE)
            polygons=native.snapshot(shape,deadline,max_vertices=4096,max_polygons=1)
            lands.append(dict(ref=fp.GetReference(),pad=str(pad.GetNumber()),uuid=uid,
                net=str(pad.GetNetname()),layer=board.GetLayerName(layer),clearance_nm=gap,
                polygons_nm=polygons))
            reserved=shape.CloneDropTriangulation();reserved.Inflate(gap+300000+2*ERROR_NM,
                pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,ERROR_NM);reservations.append(reserved)
            for other_uid,item in tracks.items():
                contour._check_deadline(deadline)
                if not item.IsOnLayer(layer) or item.GetNetCode()==pad.GetNetCode():continue
                clearance=max(gap,int(local(item,layer)))
                if not shape.Collide(item.GetEffectiveShape(layer),clearance):continue
                removable=(item.GetClass()=='PCB_TRACK' and other_uid not in grouped
                    and item.GetNetname() in eligible and 0<item.GetWidth()<500000
                    and (not item.IsLocked() or other_uid in unlock))
                blockers.append(dict(uuid=other_uid,kind=item.GetClass(),net=str(item.GetNetname()),
                    layer=board.GetLayerName(layer),clearance_nm=clearance,
                    ordinary_retirement_allowed=removable))
                if removable:retired.add(other_uid)
            for zone in board.Zones():
                contour._check_deadline(deadline)
                if not zone.IsOnLayer(layer):continue
                if zone.GetIsRuleArea():hit=zone.GetDoNotAllowVias() and shape.Collide(zone.Outline(),0)
                elif zone.GetNetCode()==pad.GetNetCode() or zone.GetNetname()=='GND':continue
                else:
                    if not zone.IsFilled() or not zone.HasFilledPolysForLayer(layer):
                        raise ValueError('native_portal_foreign_fill_unknown')
                    hit=shape.Collide(zone.GetFilledPolysList(layer),max(gap,int(local(zone,layer))))
                if hit:blockers.append(dict(uuid=force._uid(zone),kind='ZONE',net=str(zone.GetNetname()),
                    layer=board.GetLayerName(layer),ordinary_retirement_allowed=False))
    extensions=_extend_ordinary_cut(board,retired,eligible,grouped,unlock,deadline,cut_extension_mm,
        reserved_shapes=reservations)
    blockers.extend(extensions);retired.update(r['uuid'] for r in extensions if r['ordinary_retirement_allowed'])
    if len(retired)>32 or not unlock<=retired:raise ValueError('native_portal_cut_or_lock_scope_bound')
    if row_rebuild._source_binding(board)!=binding:raise ValueError('native_portal_source_changed')
    result=dict(schema=1,scope='source_native_portal_ordinary_preclear',source_sha256=force._hash(source),
        source_binding=binding,board_hint=board_hint,portal_pad_uuids=sorted(wanted),
        via_diameter_nm=via_diameter_nm,via_drill_nm=via_drill_nm,cut_extension_mm=float(cut_extension_mm),
        portals=portals,poses=[],lands=lands,blockers=blockers,source_owned_cut_extensions=extensions,
        retired_track_uuids=sorted(retired),allow_locked_track_uuids=sorted(unlock),
        affected_ordinary_nets=sorted({str(tracks[u].GetNetname()) for u in retired}),
        cut_boundaries=_cut_boundaries(board,retired,deadline),
        ok=all(r['ordinary_retirement_allowed'] for r in blockers),board_mutated=False,
        proposed_barrels_not_constructed=True,current_authority=False,release_authority=False)
    result['plan_sha256']=contour._digest(result)
    return result


def _source_sense_maze(board, source, root_uuid, target_uuid, launch, tap, width, gap,
                       eligible, grouped, deadline,margin_mm,rated_lookahead=(),input_island_uuids=()):
    """Disposable ordinary-edge ablation is lookahead, never cut authority.

    Ordinary barrels, groups, pads and all current/pair/ground material remain.
    The returned path is inspected AGAIN on the real source to type exact
    blockers and locked permissions. No stripped snapshot can be a candidate.
    """
    import cec_kelvin_copper_cut as cut
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    from shapely.prepared import prep
    with tempfile.TemporaryDirectory(prefix='cec-source-sense-lookahead-') as work:
        path=force._copy_family(source,Path(work)/'snapshot')
        scratch=field._save_field_snapshot(board,path)
        live={force._uid(p):p for fp in scratch.GetFootprints() for p in fp.Pads()}
        a,b=live[root_uuid],live[target_uuid]
        tracks=list(scratch.GetTracks())
        if len(tracks)>16384:raise ValueError('source_sense_lookahead_inventory_bound')
        discard_items(scratch,[t for t in tracks if t.GetClass()=='PCB_TRACK'
            and force._uid(t) not in grouped and ((t.GetNetname() in eligible and 0<t.GetWidth()<500000)
                or force._uid(t) in rated_lookahead)])
        work=cut._Work(deadline)
        retained={**live,**{force._uid(t):t for t in scratch.GetTracks()}}
        contacts=[a,b,*[retained[u] for u in input_island_uuids]]
        kernel=unary_union([cut._shape(p,pcbnew.F_Cu,True,work).buffer(1002) for p in contacts])
        forbidden=[]
        for item in [*live.values(),*scratch.GetTracks(),*[z for z in scratch.Zones() if not z.GetIsRuleArea()]]:
            if not item.IsOnLayer(pcbnew.F_Cu) or item.GetNetCode()!=a.GetNetCode():continue
            part=(cut._poly(item.GetFilledPolysList(pcbnew.F_Cu),work) if item.GetClass()=='ZONE'
                else cut._shape(item,pcbnew.F_Cu,True,work))
            forbidden.append(part.difference(kernel))
        blocked=prep(unary_union(forbidden))
        def guard(s,t,w):
            contour._check_deadline(deadline)
            return not blocked.intersects(LineString([tuple(s),tuple(t)]).buffer(w/2+1000,quad_segs=32))
        launch,tap=pcbnew.VECTOR2I(*launch),pcbnew.VECTOR2I(*tap)
        if not guard(launch,tap,width) or not fr._tap_foreign_clear(scratch,launch,tap,width,
                pcbnew.F_Cu,gap,{a.GetNetCode()}):
            raise ValueError('protected_source_inner_face_stem_obstructed')
        legs=fr._maze_lastmile_legs(scratch,a.GetPosition(),launch,width,pcbnew.F_Cu,gap,a.GetNetCode(),
            lambda s,t,h:fr._edge_leg_clear(scratch,s,t,h+gap),grid_mm=.1,margin_mm=margin_mm,foreign_cache={},
            deadline_monotonic=deadline,max_length_nm=24000000,run_guard=guard)
        if not legs:raise ValueError('bounded_source_sense_corridor_refused_not_no_path_proof:'+root_uuid)
        return [list(legs[0][0]),*[list(t) for _,t,_ in legs],list(tap)]


def _isolated_measurement_input_island(board, graph, pad, model, deadline):
    """A bounded native package-local measurement island, never a force tap.

    Retain its copper exactly. Every participating pad must be an explicit
    manufacturer measurement input on this same package and same net; tiny
    local planar links are allowed, but no barrel, zone, other component,
    supply, control, grouped copper or arbitrary same-net pickup is authority.
    """
    root=force._uid(pad)
    live={force._uid(i):i for i in [*(p for fp in board.GetFootprints() for p in fp.Pads()),
        *board.GetTracks(),*board.Zones()]}
    members={root}|{force._uid(i) for i in graph.GetConnectedItems(pad)}
    if len(members)>16 or not members<=live.keys():return None
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    owner=force._uid(pad.GetParentFootprint());pads=0;length=0
    for uid in sorted(members):
        contour._check_deadline(deadline)
        item=live[uid]
        if uid in grouped or item.GetNetCode()!=pad.GetNetCode():return None
        if item.GetClass()=='PAD':
            if (force._uid(item.GetParentFootprint())!=owner or item.HasHole()
                    or list(item.GetLayerSet().CuStack())!=[pcbnew.F_Cu]
                    or model['pins'].get(str(item.GetNumber()))!='measurement'):return None
            pads+=1
        elif item.GetClass()=='PCB_TRACK':
            if (item.GetLayer()!=pcbnew.F_Cu or not 0<item.GetWidth()<=350000
                    or not 0<item.GetLength()<=2000000
                    or not contour._centerline_allowed(tuple(item.GetStart()),tuple(item.GetEnd()),'chamfer45')):return None
            length+=item.GetLength()
        else:return None
    if not 1<=pads<=8 or length>4000000:return None
    return sorted(members)


def plan_sense_input_links(board, sense_input_pad_uuids, *, source, board_hint,
                          allow_locked_track_uuids=(), timeout_s=10.,
                          cut_extension_mm=0., corridor_style='y_first',corridor_margin_mm=5.,
                          allow_rated_lookahead=False,rated_source_span_mm=8.):
    """Reserve real manufacturer inputs -> their current-authority shunt.

    No coordinates, nets, shunt names or pin-role assertions come from a worker.
    This is only an ordinary preclear: it neither emits a Kelvin route nor
    permits moving force copper. Same-net force material OUTSIDE the actual
    two terminal bodies is a protected obstruction, not a convenient pickup.
    """
    import cec_current_topology as topology
    import cec_sense_topology as sense
    import cec_device_power_roles as roles
    import cec_route_dimensions as dimensions
    import cec_rated_branch_repair as rated
    deadline=time.monotonic()+_budget(timeout_s)
    if corridor_style not in ('x_first','y_first','native_maze'):
        raise ValueError('bounded_source_sense_corridor_style_required')
    if (type(corridor_margin_mm) not in (int,float) or not math.isfinite(corridor_margin_mm)
            or not 0<corridor_margin_mm<=8):
        raise ValueError('bounded_source_sense_corridor_margin_required')
    if type(allow_rated_lookahead) is not bool:
        raise ValueError('explicit_rated_sense_lookahead_mode_required')
    source_span=rated.source_span_mm(rated_source_span_mm)
    wanted=ordinary._ids(sense_input_pad_uuids,'sense_input_link_targets',8)
    if not wanted:raise ValueError('nonempty_source_sense_input_targets_required')
    unlock=ordinary._ids(allow_locked_track_uuids,'future_sense_locked_scope',32)
    source=Path(source).resolve();binding=row_rebuild._source_binding(board)
    with force._thermal_hint(board_hint):domains=topology.board_current_domains(board,board_hint)
    anchors={r for domain in domains.values() if domain.get('complete')
        for r in domain['authority_refs']}
    lineage=sense.board_evidence(board,anchor_pairs=(),anchor_refs=anchors)
    graph=fr._read_only_route_connectivity(board)
    pads={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
    if len(pads)!=sum(len(list(fp.Pads())) for fp in board.GetFootprints()):
        raise ValueError('ambiguous_source_sense_pad_identity')
    tasks={};tap_cohorts={};input_islands={}
    for row in lineage['details']:
        contour._check_deadline(deadline)
        if not row['ok'] or row['selected']['kind']!='direct':continue
        fp=board.FindFootprintByReference(row['ref']);model=roles.footprint_contract(fp)
        for pin,leg in zip(row['pins'],('p','n')):
            actual=[p for p in fp.Pads() if str(p.GetNumber())==pin]
            if len(actual)!=1:continue
            a=actual[0];uid=force._uid(a);declared=row['selected'][leg]
            if not model or model['pins'].get(pin)!='measurement':continue
            selected=row['selected'][leg]
            tap_cohorts.setdefault((selected['anchor_ref'],selected['anchor_pad']),[]).append(uid)
            if uid not in wanted:continue
            if (a.HasHole() or list(a.GetLayerSet().CuStack())!=[pcbnew.F_Cu] or fp.IsDNP()):continue
            island=_isolated_measurement_input_island(board,graph,a,model,deadline)
            if island is None:continue
            shunt=board.FindFootprintByReference(declared['anchor_ref'])
            selected=[p for p in shunt.Pads() if str(p.GetNumber())==declared['anchor_pad']]
            peer=[p for p in shunt.Pads()
                if str(p.GetNumber())==row['selected']['n' if leg=='p' else 'p']['anchor_pad']]
            if len(selected)!=1 or len(peer)!=1:continue
            b=selected[0]
            if (b.HasHole() or not b.IsOnLayer(pcbnew.F_Cu) or shunt.IsDNP()
                    or a.GetNetCode()!=b.GetNetCode() or a.GetNetCode()<=0
                    or not domains.get(a.GetNetname(),{}).get('complete')
                    or declared['anchor_ref'] not in domains[a.GetNetname()]['authority_refs']):continue
            tasks[uid]=(a,b,peer[0],row,leg);input_islands[uid]=island
    if set(tasks)!=wanted:raise ValueError('source_isolated_direct_manufacturer_sense_input_required')
    eligible=ordinary.eligible_nets(board,source,board_hint)
    local=fr._foreign_clearance_resolver(board)
    resolver=fr._project_netclass_resolver(str(source))
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    tracks={force._uid(t):t for t in board.GetTracks()}
    local_items={**pads,**tracks}
    rated_lookahead=set()
    if allow_rated_lookahead:
        with force._thermal_hint(board_hint):
            rating=topology.distributed_supply_contracts(board,board_hint,netclass_resolver=resolver)
        for identity,item in tracks.items():
            current=rating['contracts'].get(item.GetNetname())
            required=(current or {}).get('required_by_layer_mm',{}).get(board.GetLayerName(item.GetLayer()))
            if (item.GetClass()=='PCB_TRACK' and item.GetLayer() in (pcbnew.F_Cu,pcbnew.B_Cu)
                    and identity not in grouped and required is not None and 0<required<=.35
                    and math.ceil(required*1e6)<=item.GetWidth()<=350000 and 0<item.GetLength()<=source_span*1e6):
                rated_lookahead.add(identity)
    blockers=[];retired=set();lands=[];links=[]
    for uid,(a,b,peer,row,leg) in sorted(tasks.items()):
        contour._check_deadline(deadline)
        spec=dimensions.compile_spec(resolver(a.GetNetname()) or {},
            limits=dimensions.board_limits(board),role='branch')
        width=fr._nm(max(.25,spec['track_width']))
        gap=max(int(board.GetDesignSettings().m_MinClearance),fr._nm(max(.2,spec.get('clearance',0))))
        tx,ty,ux,uy=fr._inner_edge_pt(b,peer.GetPosition(),inset_mm=.1)
        # Each manufacturer input owns a separate source-derived tap. Joining
        # outside the shunt would leave a shared thin stem that is not an
        # exclusive measurement leaf. Rank in the actual shunt frame, not X.
        cohort=tap_cohorts[(b.GetParentFootprint().GetReference(),str(b.GetNumber()))]
        perpendicular=(-uy,ux)
        cohort=sorted(cohort,key=lambda key:(sum(c*d for c,d in
            zip(pads[key].GetPosition(),perpendicular)),key))
        offset=(cohort.index(uid)-(len(cohort)-1)/2)*max(.5,width/1e6+.1)
        tx+=perpendicular[0]*offset;ty+=perpendicular[1]*offset
        tap=list(pcbnew.VECTOR2I_MM(tx,ty))
        launch=list(pcbnew.VECTOR2I_MM(tx+ux*.6,ty+uy*.6))
        if not b.GetEffectiveShape(pcbnew.F_Cu).Collide(pcbnew.VECTOR2I(*tap),0):
            raise ValueError('source_input_cohort_taps_exceed_actual_pad')
        start=list(a.GetPosition())
        bend=[launch[0],start[1]] if corridor_style=='x_first' else [start[0],launch[1]]
        points=[start,bend,launch,tap]
        points=[p for i,p in enumerate(points) if not i or p!=points[i-1]]
        if corridor_style=='native_maze':
            points=_source_sense_maze(board,source,uid,force._uid(b),launch,tap,width,gap,
                eligible,grouped,deadline,corridor_margin_mm,rated_lookahead,input_islands[uid])
        # The maze may approach the fixed exit seat from inside its final
        # stem, then retrace it when the source-pad tap is appended. Remove
        # only exact collinear overrun before reservations and guards; the
        # same actual endpoints and all true bends still get full validation.
        import cec_route_quality as quality
        points=quality.compact_collinear_path(points)
        if len(points)<2:raise ValueError('distinct_native_sense_endpoints_required')
        if sum(math.dist(x,y) for x,y in zip(points,points[1:]))>24000000:
            raise ValueError('finite_source_sense_corridor_length_required')
        shape=pcbnew.SHAPE_POLY_SET();terminals=pcbnew.SHAPE_POLY_SET()
        for p in (a,b,*[local_items[u] for u in input_islands[uid] if u!=uid]):
            part=pcbnew.SHAPE_POLY_SET()
            p.TransformShapeToPolygon(part,pcbnew.F_Cu,0,ERROR_NM,pcbnew.ERROR_INSIDE,False)
            terminals.BooleanAdd(part)
        for left,right in zip(points,points[1:]):
            edge=pcbnew.PCB_TRACK(board);edge.SetLayer(pcbnew.F_Cu);edge.SetWidth(width)
            edge.SetStart(pcbnew.VECTOR2I(*left));edge.SetEnd(pcbnew.VECTOR2I(*right))
            part=pcbnew.SHAPE_POLY_SET()
            edge.TransformShapeToPolygon(part,pcbnew.F_Cu,0,ERROR_NM,pcbnew.ERROR_OUTSIDE,False)
            shape.BooleanAdd(part)
        if shape.OutlineCount()!=1 or shape.HoleCount(0):
            raise ValueError('simple_native_source_sense_corridor_required')
        lands.append(dict(ref=row['ref'],pad=str(a.GetNumber()),uuid=uid,
            net=str(a.GetNetname()),layer=board.GetLayerName(pcbnew.F_Cu),clearance_nm=gap,
            polygons_nm=native.snapshot(shape,deadline,max_vertices=4096,max_polygons=1)))
        links.append(dict(pad_uuid=uid,owner=row['ref'],pin=str(a.GetNumber()),leg=leg,
            manufacturer=roles.footprint_contract(a.GetParentFootprint()),
            lineage=row,destination_uuid=force._uid(b),destination_ref=b.GetParentFootprint().GetReference(),
            destination_pin=str(b.GetNumber()),points_nm=points,width_nm=width,layer=int(pcbnew.F_Cu),
            retained_measurement_input_island_uuids=input_islands[uid]))
        for item in [*tracks.values(),*pads.values()]:
            contour._check_deadline(deadline)
            if not item.IsOnLayer(pcbnew.F_Cu) or force._uid(item) in (uid,force._uid(b)):continue
            identity=force._uid(item);same=item.GetNetCode()==a.GetNetCode()
            clearance=0 if same else max(gap,int(local(item,pcbnew.F_Cu)))
            if same:
                part=pcbnew.SHAPE_POLY_SET()
                item.TransformShapeToPolygon(part,pcbnew.F_Cu,0,ERROR_NM,pcbnew.ERROR_OUTSIDE,False)
                part.BooleanSubtract(terminals)
                hit=shape.Collide(part,0)
            else:hit=shape.Collide(item.GetEffectiveShape(pcbnew.F_Cu),clearance)
            if not hit:continue
            removable=(not same and item.GetClass()=='PCB_TRACK' and identity not in grouped
                and str(item.GetNetname()) in eligible and 0<item.GetWidth()<500000
                and (not item.IsLocked() or identity in unlock))
            blockers.append(dict(ref=row['ref'],pad=str(a.GetNumber()),uuid=identity,
                kind=item.GetClass(),net=str(item.GetNetname()),layer=board.GetLayerName(pcbnew.F_Cu),
                clearance_nm=clearance,same_net_force_obstruction=same,
                ordinary_retirement_allowed=removable))
            if removable:retired.add(identity)
        for zone in board.Zones():
            contour._check_deadline(deadline)
            if not zone.IsOnLayer(pcbnew.F_Cu):continue
            if zone.GetIsRuleArea():hit=zone.GetDoNotAllowTracks() and shape.Collide(zone.Outline(),0)
            elif zone.GetNetname()=='GND':continue  # Only the independently received GND refill may change.
            else:
                if not zone.IsFilled() or not zone.HasFilledPolysForLayer(pcbnew.F_Cu):
                    raise ValueError('source_sense_foreign_fill_unknown')
                part=pcbnew.SHAPE_POLY_SET(zone.GetFilledPolysList(pcbnew.F_Cu))
                if zone.GetNetCode()==a.GetNetCode():part.BooleanSubtract(terminals)
                hit=shape.Collide(part,0 if zone.GetNetCode()==a.GetNetCode() else
                    max(gap,int(local(zone,pcbnew.F_Cu))))
            if hit:blockers.append(dict(ref=row['ref'],pad=str(a.GetNumber()),uuid=force._uid(zone),
                kind='ZONE',net=str(zone.GetNetname()),ordinary_retirement_allowed=False))
    reservations=[]
    for land in lands:
        reserved=native.reconstruct(land['polygons_nm'],deadline,max_vertices=4096,max_polygons=1)
        reserved.Inflate(land['clearance_nm']+300000+2*ERROR_NM,
            pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,ERROR_NM)
        reservations.append(reserved)
    extensions=_extend_ordinary_cut(board,retired,eligible,grouped,unlock,deadline,cut_extension_mm,
        reserved_shapes=reservations)
    blockers.extend(extensions);retired.update(r['uuid'] for r in extensions if r['ordinary_retirement_allowed'])
    if len(retired)>32:raise ValueError('source_sense_retirement_scope_bound')
    if not unlock<=retired:raise ValueError('locked_permission_outside_actual_blockers')
    if row_rebuild._source_binding(board)!=binding:raise ValueError('source_sense_corridor_changed_source')
    result=dict(schema=1,scope='source_sense_input_link_ordinary_preclear',source_sha256=force._hash(source),
        source_binding=binding,board_hint=board_hint,sense_input_pad_uuids=sorted(wanted),
        corridor_style=corridor_style,links=links,poses=[],lands=lands,blockers=blockers,
        corridor_margin_mm=float(corridor_margin_mm),
        allow_rated_lookahead=allow_rated_lookahead,
        rated_source_span_mm=source_span,
        cut_extension_mm=float(cut_extension_mm),source_owned_cut_extensions=extensions,
        retired_track_uuids=sorted(retired),allow_locked_track_uuids=sorted(unlock),
        affected_ordinary_nets=sorted({str(tracks[u].GetNetname()) for u in retired}),
        cut_boundaries=_cut_boundaries(board,retired,deadline),
        ok=all(r['ordinary_retirement_allowed'] for r in blockers),board_mutated=False,
        sense_link_not_yet_constructed=True,release_authority=False,kelvin_qualified=False)
    result['plan_sha256']=contour._digest(result)
    return result


def _source_boundary_face_obligation(board,net,point,layer,*,source_uuids,deadline):
    """A retained trace tip or unsupported via face is not a free XY alias.

    This read-only proposal constraint never adds connectivity. A real PTH
    land alone remains free to use its actual plated faces. Only an actual
    surviving source track tip with no other same-face material, or an actual
    surviving source via losing its face contact, pins the exact old face.
    """
    contour._check_deadline(deadline)
    at=pcbnew.VECTOR2I(*point)
    live=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks()]
    if len(live)>16384:raise ValueError('bounded_native_source_face_inventory_required')
    seeds=[i for i in live if str(i.GetNetname())==net and i.IsOnLayer(layer)
        and i.GetEffectiveShape(layer).Collide(at,0)]
    witnesses=[]
    for item in seeds:
        contour._check_deadline(deadline);uid=force._uid(item)
        if uid not in source_uuids:continue
        if item.GetClass() in ('PCB_TRACK','PCB_ARC') and tuple(point) in (tuple(item.GetStart()),tuple(item.GetEnd())):
            others=[i for i in seeds if force._uid(i)!=uid]
            if not others:witnesses.append(dict(uuid=uid,reason='surviving_source_trace_tip_needs_its_face'))
        elif item.GetClass()=='PCB_VIA':
            others=[i for i in live if force._uid(i)!=uid and i.GetClass()!='PCB_VIA'
                and str(i.GetNetname())==net and i.IsOnLayer(layer)
                and i.GetEffectiveShape(layer).Collide(item.GetEffectiveShape(layer),0)]
            if not others:
                # Only literal saved filled copper is a face witness. An
                # authored outline, another layer or planning keepout is not.
                filled=any(not z.GetIsRuleArea() and str(z.GetNetname())==net and z.IsOnLayer(layer)
                    and z.IsFilled() and z.HasFilledPolysForLayer(layer)
                    and z.GetFilledPolysList(layer).Collide(item.GetEffectiveShape(layer),0) for z in board.Zones())
                if not filled:witnesses.append(dict(uuid=uid,reason='surviving_source_via_needs_its_face'))
    return dict(at_nm=list(point),layer=int(layer),required=bool(witnesses),witnesses=witnesses,
        connectivity_or_current_credited=False)


def _ops_restore_literal_source_faces(ops,points,layer,required):
    """Exact new centreline incidence, not nearby caps or another face."""
    for point,needed in zip(points,required):
        if not needed:continue
        found=False
        for op in ops:
            if op[0]!='trk' or int(op[4])!=int(layer):continue
            a,b=op[1],op[2];dx,dy=b.x-a.x,b.y-a.y;px,py=point[0]-a.x,point[1]-a.y
            if dx*py-dy*px==0 and 0<=px*dx+py*dy<=dx*dx+dy*dy and (dx or dy):
                found=True;break
        if not found:return False
    return True


def _native_boundary_access(board, net, start, destination, layer, width, *, deadline,
                            gap, spec, maze_margin_mm, validate_ops, planar_guard, diagnostics,
                            source=None, board_hint=None,obstacle_channel_axes=False):
    """Finite access on the exact retained components of two actual cut ends.

    This is search scheduling only. No same-name island, guessed plane
    contact, boundary retirement, pad movement or current credit is granted.
    The strict ordinary receiver must still restore every old boundary and
    conductor partition, and saved native DRC must reject dangling tails.
    """
    import cec_native_component_ports as ports
    retained_contacts = set()
    if source is not None and board_hint is not None:
        parent = pcbnew.LoadBoard(str(source))
        retained_contacts = ordinary._retained_ordinary_pofv_contacts(parent, board,
            source=source, board_hint=board_hint, deadline=deadline)
    live=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks()]
    source_uuids={force._uid(i) for i in (list(parent.GetTracks()) if source is not None and board_hint is not None else live)}
    def menu(point,toward):
        seeds=[i for i in live if i.GetNetname()==net and i.IsOnLayer(layer)
            and i.GetEffectiveShape(layer).Collide(pcbnew.VECTOR2I(*point),0)]
        if not seeds:raise ValueError('retained_cut_boundary_native_contact_missing')
        # A real pad/via contact outranks its coincident track alias. Their
        # exact native connected component, not the net name, owns the menu.
        seeds.sort(key=lambda i:({'PCB_VIA':0,'PAD':1,'PCB_TRACK':2}.get(i.GetClass(),3),force._uid(i)))
        seed=seeds[0];faces=[int(layer)]
        obligation=_source_boundary_face_obligation(board,net,point,layer,
            source_uuids=source_uuids,deadline=deadline)
        if obligation['required']:
            # Do not exchange a retained source tip/face for a distant point
            # on its globally connected component. That leaves real copper
            # dangling even if every logical terminal still reaches the net.
            diagnostics.setdefault('literal_source_face_obligations',[]).append(obligation)
            return [dict(at_nm=list(point),layers=faces,native_uuids=[force._uid(seed)],
                literal_source_face_required=True)]
        if (seed.GetClass()=='PCB_VIA' and seed.GetViaType()==pcbnew.VIATYPE_THROUGH
                or seed.GetClass()=='PAD' and seed.GetAttribute()==pcbnew.PAD_ATTRIB_PTH):
            # Do not describe a real plated contact as F.Cu-only simply
            # because its removed incident edge was on F.Cu. That seeds an
            # unnecessary replacement-hole search at an occupied drill and
            # can bury the correct all-layer alias behind a finite menu.
            faces=[int(face) for face in board.GetEnabledLayers().CuStack()
                if seed.IsOnLayer(face) and seed.GetEffectiveShape(face).Collide(
                    pcbnew.VECTOR2I(*point),0)]
        boundary=dict(at_nm=list(point),layers=faces,native_uuids=[force._uid(seed)])
        return ports.endpoints(board,net,boundary,toward_nm=list(toward),
            max_sites=16,max_shift_mm=8.,deadline=deadline,
            prefer_native_via_access=True,minimum_local_via_web_nm=width)
    left,right=menu(start,destination),menu(destination,start)
    native={force._uid(i):i for i in live}
    def full_port(p):
        for uid in p['native_uuids']:
            item=native[uid]
            if item.GetClass() in ('PCB_TRACK','PCB_ARC') and item.GetWidth()<width:return False
            if (item.GetClass()=='PCB_VIA' and item.GetWidth(item.TopLayer())-item.GetDrillValue()<width
                    and uid not in retained_contacts):return False
        return True
    ranked=sorted(((s,t) for s in left if full_port(s) for t in right if full_port(t)),
        key=lambda pair:(sum(not p.get('native_via_access',False)
            and not any(native[u].GetClass()=='PCB_VIA' for u in p['native_uuids']) for p in pair),
            sum((x-y)**2 for x,y in zip(pair[0]['at_nm'],pair[1]['at_nm']))))
    pairs=ports.diverse_pairs(ranked,point=lambda p:p['at_nm'],layers=lambda p:p['layers'],limit=8,breadth=8)
    layers=fr._lastmile_route_layers(board,net_name=net,spec=spec,exclude_front=False)
    pairs, egress = ports.rank_by_native_egress(board, net, pairs,
        route_layers=layers, width_for_layer=lambda _layer: width,
        clearance_nm=gap, deadline=min(deadline,time.monotonic()+.5),
        planar_guard=planar_guard)
    diagnostics['exact_native_port_egress_scheduling']=egress
    nc=board.GetNetcodeFromNetname(net);attempts=[]
    for s,t in pairs:
        if time.monotonic()>=deadline:break
        # A restored tree may now present a retained barrel beside the last
        # cut end. Try finite short same-layer paths from that EXACT native
        # component before making another hole or restarting a large maze.
        # Every whole leg and complete craft/field predicate remains binding.
        cache={}
        for face in sorted(set(s['layers'])&set(t['layers'])&set(layers)):
            for path in fr._canonical_45_xy_paths(tuple(s['at_nm']),tuple(t['at_nm'])):
                if time.monotonic()>=deadline:break
                points=[pcbnew.VECTOR2I(*point) for point in path]
                ops=[('trk',a,b,width,face) for a,b in zip(points,points[1:]) if a!=b]
                if (sum(math.dist(tuple(o[1]),tuple(o[2])) for o in ops)>
                        math.dist(start,destination)+fr._nm(4*maze_margin_mm)):continue
                if not ops or any(not fr._edge_leg_clear(board,o[1],o[2],width//2+gap)
                        or not fr._tap_foreign_clear(board,o[1],o[2],width,face,gap,{nc},foreign_cache=cache)
                        or planar_guard is not None and not planar_guard(o[1],o[2],width,face)
                        for o in ops):continue
                if validate_ops(ops):
                    attempts.append(dict(start=s,destination=t,found=True,
                        direct_native_component_path=True,layer=int(face)))
                    diagnostics['exact_retained_component_access']=attempts
                    return ops
        local={};ops=fr._lastmile_bridge(board,s['at_nm'],s['layers'],t['at_nm'],t['layers'],
            width,nc,layers,gap,dia=float(spec.get('via_diameter') or .6),
            drill=float(spec.get('via_drill') or .3),seat_limit=8,
            leg_ok=lambda a,b,h:fr._edge_leg_clear(board,a,b,h+gap),allow_maze=True,
            maze_margin_mm=maze_margin_mm,foreign_cache={},
            deadline_monotonic=min(deadline,time.monotonic()+2.),multilayer_lays=layers,
            ops_ok=validate_ops,planar_guard=planar_guard,refine_stubs=True,
            minimum_local_via_web_nm=width,middle_grid_mm=.5 if obstacle_channel_axes else .1,
            obstacle_channel_axes=obstacle_channel_axes,
            canonical_turns_only=True,
            _multilayer_only=True,_multilayer_pair_limit=2,
            max_length_nm=math.dist(start,destination)+fr._nm(4*maze_margin_mm),diagnostics=local)
        attempts.append(dict(start=s,destination=t,found=bool(ops),bridge_diagnostics=local))
        if ops:
            diagnostics['exact_retained_component_access']=attempts
            return ops
    diagnostics['exact_retained_component_access']=attempts
    return None


def construct(board, proposal, *, source, timeout_s=10., maze_margin_mm=4., refine_maze=False,
              per_boundary_leases=False,preserve_retained_shields=False,repair_terminal_joins=False,
              obstacle_channel_axes=False,source_guided_detours=True):
    """Private in-memory prefix; no moved footprints or permanent keepouts."""
    budget=_budget(timeout_s)
    if type(maze_margin_mm) not in (int,float) or not math.isfinite(maze_margin_mm) or not 0<maze_margin_mm<=8:
        raise ValueError('bounded_future_pose_maze_required')
    if (type(refine_maze) is not bool or type(per_boundary_leases) is not bool
            or type(preserve_retained_shields) is not bool or type(repair_terminal_joins) is not bool
            or type(obstacle_channel_axes) is not bool or type(source_guided_detours) is not bool):
        raise ValueError('explicit_future_pose_maze_refinement_required')
    content=dict(proposal);digest=content.pop('plan_sha256',None)
    if digest!=contour._digest(content):raise ValueError('future_pose_plan_identity_changed')
    if proposal.get('scope')=='source_native_portal_ordinary_preclear':
        actual=plan_native_portals(board,proposal['portal_pad_uuids'],source=source,
            board_hint=proposal['board_hint'],allow_locked_track_uuids=proposal['allow_locked_track_uuids'],
            timeout_s=budget,cut_extension_mm=proposal['cut_extension_mm'],
            via_diameter_nm=proposal['via_diameter_nm'],via_drill_nm=proposal['via_drill_nm'])
    elif proposal.get('scope')=='source_sense_input_link_ordinary_preclear':
        actual=plan_sense_input_links(board,proposal['sense_input_pad_uuids'],source=source,
            board_hint=proposal['board_hint'],allow_locked_track_uuids=proposal['allow_locked_track_uuids'],
            timeout_s=budget,cut_extension_mm=proposal['cut_extension_mm'],corridor_style=proposal['corridor_style'],
            corridor_margin_mm=proposal['corridor_margin_mm'],allow_rated_lookahead=proposal['allow_rated_lookahead'],
            rated_source_span_mm=proposal['rated_source_span_mm'])
    elif proposal.get('scope')=='source_full_load_supply_link_ordinary_preclear':
        import cec_rated_link_preclear as rated_link
        actual=rated_link.plan(board,proposal['root_uuid'],proposal['peer_uuid'],source=source,
            board_hint=proposal['board_hint'],allow_locked_track_uuids=proposal['allow_locked_track_uuids'],
            timeout_s=budget,cut_extension_mm=proposal['cut_extension_mm'])
    elif proposal.get('scope')=='source_ground_reference_link_ordinary_preclear':
        actual=plan_ground_reference_links(board,proposal['reference_pad_uuids'],source=source,
            board_hint=proposal['board_hint'],allow_locked_track_uuids=proposal['allow_locked_track_uuids'],
            timeout_s=budget,cut_extension_mm=proposal['cut_extension_mm'],
            owner_ground=proposal.get('owner_ground',False))
    else:
        poses={r['ref']:r['target_pose_mm'] for r in proposal['poses']}
        actual=plan(board,poses,source=source,board_hint=proposal['board_hint'],
            allow_locked_track_uuids=proposal['allow_locked_track_uuids'],timeout_s=budget)
    # Persisted JSON arrays reload as lists while several native binding
    # inventories are tuples. Compare the same complete canonical JSON
    # identity used for the signed recipe; Python container type equality is
    # not source-change evidence. All source-derived fields still participate.
    if contour._digest(actual)!=contour._digest(proposal) or not actual['ok']:
        raise ValueError('future_pose_source_or_permission_changed')
    retired=set(proposal['retired_track_uuids'])
    if not retired:
        return dict(changed=False,closed=0,temporary_rule_areas_removed=True,release_authority=False)
    # A removed connected cut can have several surviving native junctions.
    # Lease each independently required restoration, not the cut-group label:
    # otherwise one successful first join consumes the remaining joins' work.
    # The opt-in total is still bounded to eight <=10-second slices.
    boundary_count=sum(max(0,len(cut['anchors_nm'])-1) for cut in proposal['cut_boundaries'])
    if per_boundary_leases and not 1<=boundary_count<=8:
        raise ValueError('finite_source_boundary_work_leases_required')
    original_source_uuids={force._uid(t) for t in board.GetTracks()}
    removed=[t for t in board.GetTracks() if force._uid(t) in retired]
    # Capture native scalars BEFORE discard_items destroys the SWIG objects.
    # These original source segments are hints only; all new-copper source
    # ownership, future reservations and exact saved receiving remain intact.
    source_guides={force._uid(t):dict(net=t.GetNetname(),layer=int(t.GetLayer()),
        width_nm=t.GetWidth(),points_nm=[list(t.GetStart()),list(t.GetEnd())])
        for t in removed if t.GetClass()=='PCB_TRACK'}
    discard_items(board,removed)
    # Per-hop native guards and independent receivers use private contact
    # graphs. Never normalize the live source's nets through inherited debt.
    whole_deadline=time.monotonic()+budget*(boundary_count if per_boundary_leases else 1)
    deadline=whole_deadline;reports=[]
    with force._thermal_hint(proposal['board_hint']):
        for net in proposal['affected_ordinary_nets']:
            remaining=whole_deadline-time.monotonic()
            if remaining<=0:break
            shield_context=None;shield_guard=None
            if preserve_retained_shields:
                from cec_field_search import RetainedShieldSearchGuard,retained_shield_search
                resolver=fr._project_netclass_resolver(str(source))
                shield_guard=RetainedShieldSearchGuard(board,net,board_path=str(source),
                    netclass_resolver=resolver,timeout_s=min(10.,remaining),board_hint=proposal['board_hint'])
                shield_context=retained_shield_search(board,shield_guard,deadline=whole_deadline)
                shield_context.__enter__()
            zones=[]
            try:
                zones=_install_reservations(board,proposal,net,whole_deadline)
                # A nearest-net reconnection can join the surviving trees
                # upstream and leave both old cut-end tails dangling. Restore
                # each exact external cut boundary instead of relying on a
                # lower component count or a probe inside its own old tail.
                routed=dict(closed=0,restored=[],refused=[],field_proofs=[],craft_proofs=[])
                resolver=fr._project_netclass_resolver(str(source));spec=resolver(net) or {}
                from cec_field_search import PlanarSearchGuard
                field_guard=PlanarSearchGuard(board,net,netclass_resolver=resolver)
                planar_guard=field_guard if field_guard.active else None
                nc=board.GetNetcodeFromNetname(net)
                gap=max(int(board.GetDesignSettings().m_MinClearance),fr._nm(float(spec.get('clearance') or 0)))
                from cec_route_quality import assess_proposed_route as craft_assess
                for cut in proposal['cut_boundaries']:
                    if cut['net']!=net:continue
                    points=cut['anchors_nm'];layer=board.GetLayerID(cut['layer'])
                    if len(points)<2:
                        routed['refused'].append(dict(cut=cut,reason='two_external_boundaries_required'));continue
                    width=max(cut['width_nm'],int(board.GetDesignSettings().m_TrackMinWidth),
                        fr._nm(float(spec.get('track_width') or 0)))
                    validated=set()
                    literal_faces=(False,False);literal_points=(points[0],points[-1])
                    def validate_original_ops(ops):
                        # Native refill is part of validation, not a two-second
                        # search heuristic. Retain the original aggregate lease
                        # but let a complete guarded proposal use its remaining
                        # verification budget. Expiry still refuses the child.
                        bound=deadline
                        rows=[dict(net=net,layer=int(op[4]),start_nm=list(op[1]),
                            end_nm=list(op[2]),width_nm=int(op[3])) for op in ops if op[0]=='trk']
                        vias=[dict(net=net,at_nm=list(op[1]),drill_nm=fr._nm(op[2]),
                            diameter_nm=fr._nm(op[3]),top_layer=int(pcbnew.F_Cu),
                            bottom_layer=int(pcbnew.B_Cu)) for op in ops if op[0]=='via']
                        key=contour._digest(dict(tracks=rows,vias=vias,
                            literal_source_face_points=literal_points,literal_source_faces=literal_faces,
                            literal_source_layer=int(layer)))
                        if key in validated:return True
                        if not rows or any(r['width_nm']<width for r in rows):return False
                        if not _ops_restore_literal_source_faces(ops,literal_points,layer,literal_faces):
                            routed['literal_source_face_refusals']=routed.get('literal_source_face_refusals',0)+1
                            return False
                        # Match the unchanged receiving graph's full-width
                        # conductor criterion BEFORE spending field/refill
                        # work on a candidate it cannot receive. Fabrication
                        # legality alone gives no displaced-edge capacity.
                        if any(v['diameter_nm']-v['drill_nm']<width for v in vias):
                            routed['boundary_barrel_refusals']=routed.get('boundary_barrel_refusals',0)+1
                            return False
                        craft=craft_assess(board,rows,deadline=bound)
                        routed['craft_proofs'].append(craft)
                        if craft.get('ok') is not True or craft.get('complete') is not True:return False
                        proof=field.assess_proposed_route(board,rows,proposed_vias=vias,
                            netclass_resolver=resolver,deadline=bound)
                        # Search diagnostics are not admission. Keep every
                        # outcome/count but bounded examples, not megabytes
                        # of repeated nonblocking interactions per trial.
                        routed['field_proof_count']=routed.get('field_proof_count',0)+1
                        if len(routed['field_proofs'])<32:
                            details={k:v for k,v in proof.items() if k!='interactions'}
                            blocking=[r for r in proof.get('interactions',()) if r.get('blocking')]
                            details.update(interactions=blocking[:32],
                                omitted_interaction_count=len(proof.get('interactions',()))-min(32,len(blocking)))
                            routed['field_proofs'].append(details)
                            if proof.get('ok') is not True and len(routed.get('refused_field_geometry',[]))<4:
                                routed.setdefault('refused_field_geometry',[]).append(dict(
                                    tracks=rows,vias=vias,reason=proof.get('reason'),
                                    new_blockers=proof.get('new_blockers',[])[:8],
                                    source_authority=False,admitted=False))
                        ok=proof.get('ok') is True and proof.get('complete') is True
                        if ok:validated.add(key)
                        return ok
                    def validate_ops(ops):
                        if not repair_terminal_joins:return validate_original_ops(ops)
                        import cec_terminal_join_search as joins
                        return joins.accept(board,ops,net_code=nc,clearance_nm=gap,
                            validate=validate_original_ops,deadline=deadline)
                    def validate(legs):
                        # This callback only returns a predicate for immutable
                        # planar-leg sequences. Rewrites are emitted through
                        # the operation-list bridge path, not an unreturned
                        # temporary copy of a single-layer route.
                        return validate_original_ops([('trk',a,b,w,layer) for a,b,w in legs])
                    for destination in points[1:]:
                        deadline=(min(whole_deadline,time.monotonic()+budget)
                            if per_boundary_leases else whole_deadline)
                        if time.monotonic()>=deadline:
                            routed['refused'].append(dict(cut=cut,destination_nm=destination,
                                reason='source_boundary_work_lease_exhausted',no_path_proof=False))
                            continue
                        obligations=[_source_boundary_face_obligation(board,net,p,layer,
                            source_uuids=original_source_uuids,deadline=deadline)
                            for p in (points[0],destination)]
                        literal_faces=tuple(q['required'] for q in obligations)
                        literal_points=(points[0],destination)
                        routed.setdefault('source_boundary_face_obligations',[]).append(obligations)
                        # Exact source contacts can share an existing barrel
                        # or an already restored native tree. Do not search
                        # for another hole/route after real connectivity has
                        # restored their coordinate aliases. Independent
                        # full-width boundary/partition replay still follows.
                        live=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks()]
                        seeds=[[i for i in live if i.GetNetCode()==nc and i.IsOnLayer(layer)
                            and i.GetEffectiveShape(layer).Collide(pcbnew.VECTOR2I(*point),0)]
                            for point in (points[0],destination)]
                        if all(seeds):
                            graph=fr._read_only_route_connectivity(board,{nc})
                            members={force._item_key(i) for i in [seeds[0][0],
                                *graph.GetConnectedItems(seeds[0][0])]}
                            if not any(literal_faces) and any(force._item_key(i) in members for i in seeds[1]):
                                routed['restored'].append(dict(cut=cut,destination_nm=destination,
                                    legs=0,vias=0,native_contact_already_restored=True,receiving_required=True))
                                continue
                        # Reserve time for a legal layer transition. A failed
                        # face-layer maze is not proof that a six-layer board
                        # cannot reconnect its exact source-owned boundaries.
                        legs=None
                        hints=[source_guides[u] for u in cut['retired_track_uuids'] if u in source_guides]
                        if source_guided_detours and len(hints)==1:
                            hint=hints[0];guide=hint['points_nm']
                            if guide[0]!=points[0]:guide=list(reversed(guide))
                            if (hint['net']==net and hint['layer']==int(layer) and width>=hint['width_nm']
                                    and guide==[points[0],destination]):
                                import cec_source_guided_ordinary_detour as guided
                                original_deadline=deadline;deadline=min(deadline,time.monotonic()+1.)
                                try:
                                    packet=guided.propose(board,guide,net_code=nc,layer=int(layer),
                                        width_nm=width,clearance_nm=gap,deadline=deadline,
                                        max_checked=128,max_returned=1,
                                        validate=lambda p:validate([(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width)
                                            for a,b in zip(p,p[1:])]),
                                        run_guard=(None if planar_guard is None else
                                            lambda a,b,w:planar_guard(a,b,w,layer)))
                                    if packet['options']:
                                        chosen=packet['options'][0]['points_nm']
                                        legs=[(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width) for a,b in zip(chosen,chosen[1:])]
                                    routed.setdefault('source_guide_trials',[]).append(dict(
                                        selected=bool(legs),checked=packet['checked_candidates'],
                                        every_returned_leg_native_guarded=packet['all_returned_paths_fully_native_guarded'],
                                        search_complete=packet['complete'],no_path_proof=False))
                                except (ValueError,TimeoutError) as exc:
                                    # An unsupported or exhausted hint is not
                                    # proof that the ordinary boundary cannot
                                    # route. The unchanged general maze and
                                    # independent saved receivers still follow.
                                    routed.setdefault('source_guide_trials',[]).append(dict(
                                        selected=False,reason=str(exc),no_path_proof=False))
                                finally:deadline=original_deadline
                        planar_deadline=min(deadline,time.monotonic()+2.)
                        if not legs:legs=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*points[0]),
                            pcbnew.VECTOR2I(*destination),width,layer,gap,nc,
                            lambda a,b,half:fr._edge_leg_clear(board,a,b,half),
                            allow_maze=True,maze_margin_mm=maze_margin_mm,foreign_cache={},
                            deadline_monotonic=planar_deadline,path_validator=validate,
                            refine_maze=refine_maze,
                            refinement_grids_mm=((.2,.1) if refine_maze else ()),
                            endpoint_detail_grid_mm=(.1 if refine_maze else None),compact_phase_jogs=True,
                            run_guard=(None if planar_guard is None else
                                lambda a,b,w:planar_guard(a,b,w,layer)))
                        ops=[('trk',a,b,w,layer) for a,b,w in legs] if legs else None
                        diagnostics={}
                        if not ops and time.monotonic()<deadline:
                            layers=fr._lastmile_route_layers(board,net_name=net,spec=spec,
                                exclude_front=False)
                            bridge_layers=[lay for lay in layers if lay!=layer]
                            if bridge_layers:
                                ops=fr._lastmile_bridge(board,tuple(points[0]),{int(layer)},
                                    tuple(destination),{int(layer)},width,nc,bridge_layers,gap,
                                    dia=float(spec.get('via_diameter') or .6),
                                    drill=float(spec.get('via_drill') or .3),seat_limit=24,
                                    leg_ok=lambda a,b,half:fr._edge_leg_clear(board,a,b,half),
                                    allow_maze=True,maze_margin_mm=maze_margin_mm,
                                    foreign_cache={},deadline_monotonic=(
                                        min(deadline,time.monotonic()+2.) if refine_maze else deadline),
                                    multilayer_lays=layers,ops_ok=validate_ops,
                                    planar_guard=planar_guard,refine_stubs=refine_maze,
                                    minimum_local_via_web_nm=width,
                                    obstacle_channel_axes=obstacle_channel_axes,
                                    max_length_nm=math.dist(points[0],destination)+fr._nm(4*maze_margin_mm),
                                    diagnostics=diagnostics)
                        if not ops and refine_maze and time.monotonic()<deadline:
                            ops=_native_boundary_access(board,net,points[0],destination,layer,width,
                                deadline=deadline,gap=gap,spec=spec,maze_margin_mm=maze_margin_mm,
                                validate_ops=validate_ops,planar_guard=planar_guard,diagnostics=diagnostics,
                                source=source,board_hint=proposal['board_hint'],
                                obstacle_channel_axes=obstacle_channel_axes)
                        if not ops or not validate_ops(ops):
                            routed['refused'].append(dict(cut=cut,reason='bounded_boundary_route_refused',
                                destination_nm=destination,bridge_diagnostics=diagnostics,
                                no_path_proof=False));continue
                        items=[]
                        for op in ops:
                            if op[0]=='via':
                                _,at,drill,dia=op
                                edge=pcbnew.PCB_VIA(board);edge.SetPosition(at)
                                edge.SetWidth(fr._nm(dia));edge.SetDrill(fr._nm(drill))
                                edge.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
                                edge.SetViaType(pcbnew.VIATYPE_THROUGH)
                            else:
                                _,a,b,w,lay=op
                                edge=pcbnew.PCB_TRACK(board);edge.SetStart(a);edge.SetEnd(b)
                                edge.SetWidth(w);edge.SetLayer(lay)
                            edge.SetNetCode(nc);edge.SetLocked(True);board.Add(edge);items.append(edge)
                        pofv=fr.group_local_pofv_signal_vias(board,items)
                        routed['closed']+=1
                        routed['restored'].append(dict(cut=cut,destination_nm=destination,
                            legs=sum(op[0]=='trk' for op in ops),vias=sum(op[0]=='via' for op in ops),
                            layers=sorted({board.GetLayerName(op[4]) for op in ops if op[0]=='trk'}),
                            local_pofv_group=pofv,bridge_diagnostics=diagnostics))
                routed['field_search']=field_guard.report()
                if shield_guard is not None:routed['retained_shield_search']=shield_guard.report()
                reports.append(dict(net=net,construction=routed))
            finally:
                try:
                    discard_items(board,zones)
                finally:
                    if shield_context is not None:shield_context.__exit__(None,None,None)
    return dict(changed=True,closed=sum(r['construction']['closed'] for r in reports),
        nets=reports,retired_track_uuids=sorted(retired),temporary_rule_areas_removed=True,
        per_boundary_leases=per_boundary_leases,
        source_guided_detours=source_guided_detours,
        independent_boundary_work_leases=boundary_count if per_boundary_leases else 1,
        preserve_retained_shields=preserve_retained_shields,
        repair_terminal_joins=repair_terminal_joins,
        obstacle_channel_axes=obstacle_channel_axes,
        max_construction_wall_s=budget*(boundary_count if per_boundary_leases else 1),
        original_poses_retained=True,release_authority=False,independent_receiving_required=True)


def prepare(source, poses, directory, *, board_hint, allow_locked_track_uuids=(),
            timeout_s=10., maze_margin_mm=4., reference_pad_uuids=(), cut_extension_mm=0.,
            owner_ground=False, refine_maze=False,sense_input_pad_uuids=(),corridor_style='y_first',
            corridor_margin_mm=5.,portal_pad_uuids=(),via_diameter_nm=None,via_drill_nm=None):
    """Receive the ordinary prefix before offering its future pose recipe."""
    timeout_s=_budget(timeout_s);source=Path(source).resolve();directory=Path(directory).resolve()
    if type(refine_maze) is not bool:
        raise ValueError('explicit_future_pose_maze_refinement_required')
    if directory.exists():raise ValueError('fresh_future_pose_directory_required')
    directory.mkdir(parents=True)
    family=force._family(source,board_hint);epoch=force._code_identity()
    if type(owner_ground) is not bool or (owner_ground and not reference_pad_uuids):
        raise ValueError('explicit_source_reference_destination_required')
    if sum(bool(v) for v in (reference_pad_uuids,poses,sense_input_pad_uuids,portal_pad_uuids))!=1:
        raise ValueError('one_source_preclear_scope_required')
    def propose(board,path,*,locked=(),extension_mm=0.):
        if portal_pad_uuids:
            return plan_native_portals(board,portal_pad_uuids,source=path,board_hint=board_hint,
                allow_locked_track_uuids=locked,timeout_s=timeout_s,cut_extension_mm=extension_mm,
                via_diameter_nm=via_diameter_nm,via_drill_nm=via_drill_nm)
        if sense_input_pad_uuids:
            return plan_sense_input_links(board,sense_input_pad_uuids,source=path,board_hint=board_hint,
                allow_locked_track_uuids=locked,timeout_s=timeout_s,cut_extension_mm=extension_mm,
                corridor_style=corridor_style,corridor_margin_mm=corridor_margin_mm)
        if reference_pad_uuids:
            return plan_ground_reference_links(board,reference_pad_uuids,source=path,board_hint=board_hint,
                allow_locked_track_uuids=locked,timeout_s=timeout_s,cut_extension_mm=extension_mm,
                owner_ground=owner_ground)
        if extension_mm:raise ValueError('source_reference_cut_required_for_extension')
        return plan(board,poses,source=path,board_hint=board_hint,
            allow_locked_track_uuids=locked,timeout_s=timeout_s)
    board=pcbnew.LoadBoard(str(source));proposal=propose(board,source,
        locked=allow_locked_track_uuids,extension_mm=cut_extension_mm)
    force._write(directory/'preclear-plan.json',proposal)
    if not proposal['ok']:
        result=dict(ok=False,reason='destination_requires_placement_replan',plan=proposal,
            board=None,source_unchanged=family==force._family(source,board_hint),release_authority=False)
        force._write(directory/'receiving.json',result);return result
    if not proposal['retired_track_uuids']:
        stable=family==force._family(source,board_hint) and epoch==force._code_identity()
        result=dict(ok=stable,reason='no_ordinary_obstruction' if stable else 'source_identity_changed',
            plan=proposal,board=str(source),source_unchanged=stable,
            release_authority=False,future_placement_admitted=False)
        force._write(directory/'receiving.json',result);return result
    candidate=force._copy_family(source,directory/'candidate');board.SetFileName(str(source))
    construction=construct(board,proposal,source=source,timeout_s=timeout_s,
        maze_margin_mm=maze_margin_mm,refine_maze=refine_maze)
    additive._ground_refill(board);field._save_field_snapshot(board,candidate)
    additive.bind_local_via_rule(board,candidate)
    receipt=ordinary.receive(source,candidate,retired_track_uuids=proposal['retired_track_uuids'],
        allow_locked_track_uuids=proposal['allow_locked_track_uuids'],board_hint=board_hint,timeout_s=timeout_s)
    def drc(path,name):
        target=directory/name
        # KiCad CLI can create a .kicad_prl beside even a read-only input.
        # Grade an exact isolated family so diagnostics never mutate a control
        # or silently extend the companion inventory bound by receiving.
        isolated=force._copy_family(path,directory/('grade-'+Path(name).stem))
        run=subprocess.run(['kicad-cli','pcb','drc','--format','json','--severity-all',
            '--output',str(target),str(isolated)],capture_output=True,text=True,timeout=timeout_s)
        if run.returncode!=0:raise ValueError('native_future_pose_drc_failed:'+run.stderr[:512])
        return json.loads(target.read_text())
    before=drc(source,'source-drc.json');after=drc(candidate,'native-drc.json')
    old={stage._canonical_identity(v) for v in before['violations']}
    new=[v for v in after['violations'] if stage._canonical_identity(v) not in old]
    # Inspect the saved received child with detached copies again: a reroute
    # that preserves connectivity but still covers the future seat is a fail.
    future=propose(pcbnew.LoadBoard(str(candidate)),candidate)
    final_family=force._family(source,board_hint);final_epoch=force._code_identity()
    stable=family==final_family and epoch==final_epoch
    ok=(receipt['ok'] is True and receipt['complete'] is True and not new and stable
        and len(after['unconnected_items'])<=len(before['unconnected_items'])
        and not future['blockers'])
    result=dict(schema=1,ok=ok,reason='received_preclear_prefix' if ok else 'preclear_prefix_refused',
        source=str(source),source_sha256=force._hash(source),board=str(candidate),
        board_sha256=force._hash(candidate),plan=proposal,construction=construction,
        independent_ordinary_receiving=receipt,future_blockers=future['blockers'],
        new_native_faults=new,source_opens=len(before['unconnected_items']),opens=len(after['unconnected_items']),
        source_and_code_unchanged=stable,
        source_family_before=family,source_family_after=final_family,code_before=epoch,code_after=final_epoch,
        source_family_changes=[p for p in sorted(family.keys()|final_family.keys()) if family.get(p)!=final_family.get(p)],
        code_changes=[p for p in sorted(epoch.keys()|final_epoch.keys()) if epoch.get(p)!=final_epoch.get(p)],
        release_authority=False,future_placement_admitted=False)
    force._write(directory/'receiving.json',result)
    return result


def prepare_ground_reference_links(source, reference_pad_uuids, directory, *, board_hint,
                                   allow_locked_track_uuids=(), timeout_s=10.,
                                   maze_margin_mm=4., cut_extension_mm=0.,owner_ground=False,
                                   refine_maze=False):
    """Independently receive the ordinary prefix; never emit the ground link.

    The subsequently constructed source-derived reference link still needs
    separate additive/current/physical/release admission. A preclear receipt
    is not evidence that an isolated package terminal has been connected.
    """
    if not reference_pad_uuids:raise ValueError('nonempty_ground_reference_link_targets_required')
    return prepare(source,{},directory,board_hint=board_hint,
        allow_locked_track_uuids=allow_locked_track_uuids,timeout_s=timeout_s,
        maze_margin_mm=maze_margin_mm,reference_pad_uuids=reference_pad_uuids,owner_ground=owner_ground,
        cut_extension_mm=cut_extension_mm,refine_maze=refine_maze)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    target=parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--recipe',type=Path)
    target.add_argument('--ground-reference-pad',action='append',default=[])
    parser.add_argument('--source-sha256')
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--hint',required=True)
    parser.add_argument('--allow-locked-track',action='append',default=[])
    parser.add_argument('--seconds',type=float,default=10.)
    parser.add_argument('--maze-margin-mm',type=float,default=4.)
    parser.add_argument('--cut-extension-mm',type=float,default=0.)
    parser.add_argument('--owner-ground',action='store_true',
        help='Reserve the source-verified owner ground instead of its assigned bypass return')
    args=parser.parse_args();recipe=json.loads(args.recipe.read_text()) if args.recipe else {}
    if force._hash(args.source)!=(recipe.get('source_sha256') if args.recipe else args.source_sha256):
        raise ValueError('explicit_future_pose_recipe_source_changed')
    result=prepare(args.source,recipe.get('poses',{}),args.out,board_hint=args.hint,
        allow_locked_track_uuids=args.allow_locked_track,timeout_s=args.seconds,
        maze_margin_mm=args.maze_margin_mm,reference_pad_uuids=args.ground_reference_pad,
        cut_extension_mm=args.cut_extension_mm,owner_ground=args.owner_ground)
    print(json.dumps({k:result.get(k) for k in ('ok','reason','source_opens','opens','board')}),flush=True)
    print(json.dumps(dict(retired=result['plan']['retired_track_uuids'],
        blockers=len(result.get('future_blockers',result['plan']['blockers'])),
        new_drc=len(result.get('new_native_faults',[])),
        errors=(result.get('independent_ordinary_receiving') or {}).get('errors'))),flush=True)
    return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
