"""Finite, owner-derived post-route local PI cleanup proposals.

Keep owners and every existing conductor fixed. Move only an unlocked selected
two-land bypass, then rebuild its short supply/return cell with the normal
native process/clearance tools. An unsuccessful cell restores both its pose
and all trial copper. Construction is not independent board admission.
"""
import math
import time

import pcbnew
import cec_constraints as constraints
import cec_decoupler_cell as cell
import cec_force_current as force
import cec_local_copper_cell as copper
import cec_search_budget as budgets
import cec_synth_pipeline as synth


def _pose_native_permissions(board,cap):
    """Native permissions and authored pour reservations for future seats."""
    cap.BuildCourtyardCaches()
    layer=pcbnew.B_CrtYd if cap.IsFlipped() else pcbnew.F_CrtYd
    courtyard=cap.GetCourtyard(layer)
    own_box=synth._footprint_courtyard_box(cap)
    # Native permission areas are independent of foreign copper. A clear
    # court/trace seat can still occupy an assembly vent or a pad/body-only
    # keepout. Check its actual permission and face before constructing any
    # local return; never infer permission from an empty copper inventory.
    import cec_native_rule_areas as rule_areas
    face=pcbnew.B_Cu if cap.IsFlipped() else pcbnew.F_Cu
    body=courtyard
    if not body.OutlineCount():
        x0,x1,y0,y1=own_box
        body=pcbnew.SHAPE_POLY_SET();body.NewOutline()
        for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1)):
            body.Append(round(x*1e6),round(y*1e6))
    for rule in rule_areas.areas(board,'footprints'):
        if face in rule['layers'] and rule['shape'].Collide(body,0):
            raise ValueError('PI_pose_native_footprint_keepout:'+rule['identity']['uuid'])
    pad_rules=rule_areas.areas(board,'pads')
    for pad in cap.Pads():
        for copper_layer in pad.GetLayerSet().CuStack():
            for rule in pad_rules:
                if copper_layer in rule['layers'] and rule['shape'].Collide(pad.GetEffectiveShape(copper_layer),0):
                    raise ValueError('PI_pose_native_pad_keepout:'+rule['identity']['uuid'])
    # Match the independent full-board pour-first checker before routing or
    # refilling. A native filler can make a perfectly DRC-clear antipad around
    # an illegally placed capacitor; that empty fill is not a legal seat.
    # Use literal native contours, actual pad faces and net names, never a
    # bounding box or a zone-name exception. Reworking a reserved contour is
    # a separate typed current/geometry transaction, not this pose's power.
    for zone,copper_layer in constraints.laid_pour_regions(board):
        for pad in cap.Pads():
            if (pad.IsOnLayer(copper_layer) and pad.GetNetname()!=zone.GetNetname()
                    and zone.Outline().Collide(pad.GetEffectiveShape(copper_layer),0)):
                raise ValueError('PI_pose_reserved_laid_pour:'+force._uid(zone))


def _pose_preflight(board,cap):
    """Cheap conservative local check, never a native-DRC replacement.

    A supply-pivot rotation can be electrically promising yet overlap another
    package or put its moved return on a foreign trace. Reject those seats
    before building a complete cell. Read every live enabled copper layer,
    actual filled polygons, local/project clearances and authored courtyards.
    """
    import cec_fr as fr
    _pose_native_permissions(board,cap)
    minimum=board.GetDesignSettings().m_MinClearance
    own_id=force._uid(cap)
    layer=pcbnew.B_CrtYd if cap.IsFlipped() else pcbnew.F_CrtYd
    courtyard=cap.GetCourtyard(layer)
    own_box=synth._footprint_courtyard_box(cap)
    for fp in board.GetFootprints():
        if force._uid(fp)==own_id or fp.IsFlipped()!=cap.IsFlipped():continue
        other=fp.GetCourtyard(layer)
        if courtyard.OutlineCount() and other.OutlineCount():
            collision=courtyard.Collide(other,0)
        else:
            box=synth._footprint_courtyard_box(fp)
            collision=(min(own_box[1],box[1])>max(own_box[0],box[0])+1e-6
                and min(own_box[3],box[3])>max(own_box[2],box[2])+1e-6)
        if collision:raise ValueError('PI_pose_courtyard_overlap:'+str(fp.GetReference()))
    for x in own_box[:2]:
        for y in own_box[2:]:
            at=pcbnew.VECTOR2I_MM(x,y)
            if not fr._edge_leg_clear(board,at,at,0):raise ValueError('PI_pose_outside_native_outline')
    pads=[p for fp in board.GetFootprints() if force._uid(fp)!=own_id for p in fp.Pads()]
    tracks=list(board.GetTracks())
    zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
    for pad in cap.Pads():
        clearance=max(minimum,int(cell._netclass(board,str(pad.GetNetname()))['clearance']))
        for copper_layer in board.GetEnabledLayers().CuStack():
            if not pad.IsOnLayer(copper_layer):continue
            shape=pad.GetEffectiveShape(copper_layer)
            for item in [*pads,*tracks]:
                if item.GetNetCode()==pad.GetNetCode() or not item.IsOnLayer(copper_layer):continue
                gap=max(clearance,int(cell._netclass(board,str(item.GetNetname()))['clearance']))
                if shape.Collide(item.GetEffectiveShape(copper_layer),gap):
                    raise ValueError('PI_pose_foreign_copper_clearance:'+force._uid(item))
            for zone in zones:
                if zone.GetNetCode()==pad.GetNetCode() or not zone.IsOnLayer(copper_layer):continue
                if not zone.IsFilled():raise ValueError('PI_pose_foreign_zone_fill_unknown')
                native=zone.GetFilledPolysList(copper_layer)
                if native.OutlineCount() and shape.Collide(native,max(clearance,zone.GetLocalClearance())):
                    raise ValueError('PI_pose_foreign_filled_zone_clearance:'+force._uid(zone))


def _selected(board,cap_ref):
    assignment=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    rows=[r for r in assignment['assigned'].values() if r['cap_ref']==cap_ref]
    if len(rows)!=1:raise ValueError('cleanup_requires_unique_source_selected_bypass')
    row=rows[0];req=row['requirement'];cap=board.FindFootprintByReference(cap_ref)
    owner=board.FindFootprintByReference(req['ref'])
    pads=list(cap.Pads());grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    if ((req.get('return_rail') or 'GND')!='GND' or cap.IsLocked() or force._uid(cap) in grouped
            or len(pads)!=2 or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole() for p in pads)):
        raise ValueError('cleanup_requires_unlocked_two_land_ground_bypass')
    rail=next((p for p in pads if p.GetNetname()==req['rail']),None)
    _return,gnd,grounds=cell._cell_return_pads(req,owner,cap)
    if rail is None or gnd is None or not grounds:raise ValueError('cleanup_terminal_geometry_missing')
    return req,cap,owner,rail,gnd,grounds


def pose_menu(board,cap_ref,*,max_poses=16,gap_mm=.1):
    if (type(max_poses) is not int or not 1<=max_poses<=64
            or type(gap_mm) not in (int,float) or not math.isfinite(gap_mm) or not 0<=gap_mm<=1):
        raise ValueError('bounded_PI_pose_menu_required')
    req,cap,owner,rail,gnd,grounds=_selected(board,cap_ref)
    tangent=synth._decoupler_tangent_target(owner,cap,req['pad'],rail,grounds,gnd,
        gap_mm=gap_mm,ground_max_mm=2.5)
    at=cap.GetPosition();origin=[at.x/1e6,at.y/1e6];angle=cap.GetOrientationDegrees()
    current=math.dist(force._point(req['pad']),force._point(rail))/1e6
    rows=[];seen={};families=[]
    def eligible(row):
        # Score real transformed terminals rather than the footprint origin.
        # This cheap filter does not prove copper or authorize the proposal.
        posed=pcbnew.FOOTPRINT(cap)
        posed.SetPosition(pcbnew.VECTOR2I_MM(*row['position_mm']))
        posed.SetOrientationDegrees(row['orientation_deg'])
        supply=posed.FindPadByNumber(rail.GetNumber())
        ground=posed.FindPadByNumber(gnd.GetNumber())
        if (math.dist(force._point(supply),force._point(req['pad']))/1e6>current+1e-6
                or min(math.dist(force._point(ground),force._point(p))/1e6 for p in grounds)>2.5):return False
        try:_pose_preflight(board,posed)
        except ValueError:return False
        return True
    def offer(row,collection):
        key=tuple(round(v,6) for v in [*row['position_mm'],row['orientation_deg']])
        if ((math.dist(key[:2],origin)<1e-6 and abs((key[2]-angle)%360)<1e-5)
                or not eligible(row)):return
        if key in seen:
            if row['basis']=='native_owner_courtyard_tangent':return
            previous=seen[key]
            previous[:]=[r for r in previous if tuple([*r['position_mm'],r['orientation_deg']])!=key]
        seen[key]=collection;row.update(position_mm=list(key[:2]),orientation_deg=key[2]);collection.append(row)
    # A full tangent seat may require a separate incident-branch transition.
    # Smaller source-to-tangent translations keep actual old land contacts
    # when possible; native receiving, never this interpolation, proves them.
    for target in (tangent or {}).get('candidates',[]):
        family=[]
        for fraction in (1.,.5,.25,.75):
            theta=target['orientation_deg'] if fraction==1. else angle
            position=[origin[i]+fraction*(target['position_mm'][i]-origin[i]) for i in (0,1)]
            offer(dict(position_mm=position,orientation_deg=theta,
                basis='native_owner_courtyard_tangent',fraction=fraction,
                target_supply_mm=target['supply_mm'],source_supply_mm=current),family)
        if family:families.append(family)
    # A real existing return portal is another useful seat, particularly when
    # a through barrel cannot pass a protected inner power lane at the old
    # capacitor location. Use only the saved connected local portal; the
    # constructor/receiver still re-prove its topology and all old contacts.
    portal=cell._existing_return(board,gnd,1.5)
    portal_rows=[]
    if portal is not None and portal[0]>.01:
        gx,gy=force._point(gnd);vx,vy=force._point(portal[1])
        for fraction in (1.,.75,.5,.25):
            offer(dict(position_mm=[origin[0]+fraction*(vx-gx)/1e6,
                origin[1]+fraction*(vy-gy)/1e6],orientation_deg=angle,
                basis='native_connected_return_portal',fraction=fraction,
                source_ground_path_mm=portal[0],source_supply_mm=current),portal_rows)
    # Rotate the return around the actual fixed supply land as a final local
    # alternative. This does not authorize its copper or manufacturing rules.
    pivot_rows=[]
    for delta in (90.,180.,270.):
        rotated=pcbnew.FOOTPRINT(cap);rotated.Rotate(rail.GetPosition(),pcbnew.EDA_ANGLE(delta,pcbnew.DEGREES_T))
        p=rotated.GetPosition();key=(p.x/1e6,p.y/1e6,rotated.GetOrientationDegrees())
        offer(dict(position_mm=list(key[:2]),orientation_deg=key[2],
            basis='native_fixed_supply_return_pivot',source_supply_mm=current),pivot_rows)
    # Breadth before interpolation: a small menu must not spend its entire
    # budget on four fractions of one identical seat and starve both native
    # portal and fixed-supply alternatives.
    queues=[];families=[f for f in families if f]
    if families:queues.append(families.pop(0))
    if portal_rows:queues.append(portal_rows)
    if pivot_rows:queues.append(pivot_rows)
    queues.extend(families[:max(1,max_poses//4)])
    while queues and len(rows)<max_poses:
        for queue in queues:
            if queue and len(rows)<max_poses:rows.append(queue.pop(0))
        queues=[q for q in queues if q]
    return rows[:max_poses]


def construct_bypass_board(board,*,cap_ref,position_mm,orientation_deg,board_hint,
        board_path='',return_reach_mm=.8,search_work_limit=256):
    result=dict(ok=False,constructed=False,release_authority=False,power_authority=False,
        requires_independent_receiving=True,cap=cap_ref,generated_items=[],reason=None)
    if (type(search_work_limit) is not int or not 1<=search_work_limit<=4096
            or type(return_reach_mm) not in (int,float) or not math.isfinite(return_reach_mm)
            or not 0<return_reach_mm<=1.5 or not isinstance(position_mm,(list,tuple)) or len(position_mm)!=2
            or type(board_hint) is not str or not board_hint
            or any(type(v) not in (int,float) or not math.isfinite(v) for v in [*position_mm,orientation_deg])):
        result['reason']='invalid_bounded_PI_cleanup_proposal';return result
    started=time.monotonic();snapshot=cell._cell_trial_snapshot(board);cap=None;original_pose=None
    source_copper=copper.copper_inventory(board)
    source_nets=[(item,item.GetNetCode()) for item in board.GetTracks()]
    try:
        with force._thermal_hint(board_hint):
            req,cap,owner,rail,gnd,grounds=_selected(board,cap_ref)
            at=cap.GetPosition();original_pose=(pcbnew.VECTOR2I(at.x,at.y),cap.GetOrientationDegrees())
            delta=(orientation_deg-original_pose[1])%360
            if (math.dist(position_mm,[at.x/1e6,at.y/1e6])>6
                    or not any(abs(delta-a)<1e-5 for a in (0.,90.,180.,270.))):
                raise ValueError('PI_cleanup_pose_exceeds_bounded_domain')
            before_supply=math.dist(force._point(req['pad']),force._point(rail))/1e6
            before_ground=cell._existing_return(board,gnd,1.5)
            before_topology=(cell._existing_return_topology(board,gnd,before_ground[1])
                if before_ground is not None else {})
            before_path=cell._shortest_track_path_mm(board,req['pad'],rail)
            cap.SetPosition(pcbnew.VECTOR2I_MM(*position_mm));cap.SetOrientationDegrees(orientation_deg)
            after_supply=math.dist(force._point(req['pad']),force._point(rail))/1e6
            if after_supply>before_supply+1e-6:raise ValueError('PI_cleanup_supply_pin_distance_would_regress')
            ground=min(grounds,key=lambda p:math.dist(force._point(p),force._point(gnd)))
            if math.dist(force._point(ground),force._point(gnd))/1e6>2.5:
                raise ValueError('PI_cleanup_owner_return_distance_exceeds_policy')
            _pose_preflight(board,cap)
            result['native_pose_preflight_passed']=True
            with budgets.scoped(search_work_limit) as work:
                built=cell._construct_coupled_cell(board,req['pad'],rail,ground,gnd,
                    return_rail='GND',board_path=board_path,ground_reach_mm=return_reach_mm,
                    lock=True,group_neckdowns=True)
            result.update(cell=built,work=work.report(),owner=req['ref'],pin=str(req['pin']),rail=req['rail'])
            if built.get('error') is not None:raise ValueError('local_PI_cell_not_constructed')
            after_ground=cell._existing_return(board,gnd,return_reach_mm)
            after_path=cell._shortest_track_path_mm(board,req['pad'],rail)
            if after_ground is None or after_path is None:raise ValueError('native_local_PI_path_not_received')
            old_return=before_ground[0] if before_ground is not None else None
            after_topology=cell._existing_return_topology(board,gnd,after_ground[1])
            retained_vip=bool(before_ground is not None
                and force._uid(before_ground[1])==force._uid(after_ground[1])
                and before_topology.get('topology_qualified') is True
                and after_topology.get('topology_qualified') is True)
            progress=(after_supply<before_supply-.01 or before_path is None
                or after_path<before_path-.01 or old_return is None or after_ground[0]<old_return-.01)
            if not progress:raise ValueError('no_measured_local_PI_cleanup_progress')
            if before_path is not None and after_path>before_path+1e-6:
                raise ValueError('native_supply_path_would_regress')
            if old_return is not None and after_ground[0]>old_return+1e-6 and not retained_vip:
                raise ValueError('native_ground_return_path_would_regress')
            current_copper=copper.copper_inventory(board)
            if any(current_copper.get(uid)!=geometry for uid,geometry in source_copper.items()):
                raise ValueError('PI_constructor_changed_inherited_native_copper')
            created=[i for i in board.GetTracks() if force._uid(i) not in snapshot[0]]
            # These are generated local process returns, not an exemption for
            # inherited vias. Actual dimensions/owners are independently read.
            import cec_fr as fr
            # Bypass returns are PI cells, not single-ended signal-transition
            # barrels. Do not claim that unrelated exception before the
            # selected fabrication process has qualified the actual dogbone.
            fr.group_local_pofv_signal_vias(board,[i for i in created if i.GetClass()=='PCB_VIA'])
            result.update(ok=True,constructed=True,reason='measured_local_PI_cleanup_proposed',
                before=dict(supply_mm=before_supply,supply_path_mm=before_path,ground_path_mm=old_return),
                after=dict(supply_mm=after_supply,supply_path_mm=after_path,ground_path_mm=after_ground[0]),
                original_qualified_via_still_fully_in_pad=retained_vip,
                generated_items=[dict(uuid=force._uid(i),net=str(i.GetNetname()),kind=i.GetClass()) for i in created])
    except Exception as exc:
        if original_pose is not None:
            cap.SetPosition(original_pose[0]);cap.SetOrientationDegrees(original_pose[1])
        result['rollback']=cell._rollback_cell_trial(board,snapshot)
        # KiCad's rebuild can propagate nets through an inherited short.
        # Rollback must retain that exact source debt, not relabel a track as
        # though the proposal had repaired it. No rebuilt graph is trusted
        # after restoring the immutable source net labels.
        for item,net_code in source_nets:
            if item.GetNetCode()!=net_code:item.SetNetCode(net_code)
        if copper.copper_inventory(board)!=source_copper:
            raise RuntimeError('PI_cleanup_rollback_changed_inherited_copper')
        result['reason']=str(exc);result['constructed']=False;result['ok']=False
    result['elapsed_s']=round(time.monotonic()-started,6)
    return result
