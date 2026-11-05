"""Finite ordinary capacitor reseating with its actual contained ground entry.

No power/paired/sense route or arbitrary ground barrel is mutable here. Only
an unlocked two-land capacitor on an independently eligible ordinary net,
and its unique branch-free, native-process-qualified in-pad return, enter
this proposal. Package/current/plane/partition receiving remains independent.
"""
import json,math,time
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_device_bypass as capacitors
import cec_ordinary_route_receiving as ordinary
import cec_fab_profile as fab
import cec_pi_cleanup as placement
import cec_fr as fr
import cec_constraints as constraints
import cec_field_coupling as field
from cec_resistive_monitor_branch import resistor_contract


def plan(board,source,via_uuid,*,hint):
    live={force._uid(t):t for t in board.GetTracks()}
    via=live.get(via_uuid)
    if (via is None or via.GetClass()!='PCB_VIA' or via.GetNetname()!='GND'
            or via.GetViaType()!=pcbnew.VIATYPE_THROUGH
            or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu
            or not fab.local_pofv_via_decision(board,via)[0]):
        raise ValueError('actual_process_qualified_inpad_return_required')
    layers=list(board.GetEnabledLayers().CuStack())
    owners=[p for f in board.GetFootprints() for p in f.Pads()
        if p.GetNetname()=='GND' and any(p.IsOnLayer(l) and
            fab._pad_contains_circle(p,via.GetPosition(),via.GetWidth(l)//2) for l in layers)]
    if len(owners)!=1:raise ValueError('unique_actual_contained_return_owner_required')
    ground=owners[0];cap=ground.GetParentFootprint();pads=list(cap.Pads())
    farads=capacitors.capacitance_f(cap.GetValue())
    grouped={force._uid(i):g for g in board.Groups() for i in g.GetItems()}
    capacitor=(capacitors.capacitor_identity(cap.GetReference(),cap.GetFPIDAsString())
        and capacitors.local_bypass_technology(cap.GetValue(),cap.GetFPIDAsString())
        and farads is not None and 0<farads<=1e-3)
    resistor=resistor_contract(cap)
    if (cap.IsLocked() or cap.IsDNP() or force._uid(cap) in grouped or len(pads)!=2
            or not (capacitor or resistor)
            or any(p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or p.HasHole() for p in pads)):
        raise ValueError('unlocked_native_two_land_local_RC_support_required')
    supply=next(p for p in pads if force._uid(p)!=force._uid(ground))
    eligible=ordinary.eligible_nets(board,source,hint)
    if supply.GetNetname() not in eligible:raise ValueError('source_ordinary_terminal_authority_required')
    if via_uuid in grouped and (grouped[via_uuid].GetName()!=fr.LOCAL_POFV_SIGNAL_VIA_GROUP
            or grouped[via_uuid].IsLocked()):raise ValueError('return_entry_has_protected_source_group')
    if any(t!=via and t.GetNetname()=='GND' and any(t.IsOnLayer(l) and
            t.GetEffectiveShape(l).Collide(via.GetEffectiveShape(l),0) for l in layers)
            for t in board.GetTracks()):raise ValueError('owned_inpad_entry_has_external_ground_branch')
    if any(p!=ground and p.GetNetname()=='GND' and any(p.IsOnLayer(l) and
            p.GetEffectiveShape(l).Collide(via.GetEffectiveShape(l),0) for l in layers)
            for f in board.GetFootprints() for p in f.Pads()):
        raise ValueError('owned_inpad_entry_has_another_ground_land')
    planes=sorted(force._uid(z) for z in board.Zones() if not z.GetIsRuleArea()
        and z.GetNetname()=='GND' and z.IsFilled() and any(z.IsOnLayer(l) and
            z.GetFilledPolysList(l).Collide(via.GetEffectiveShape(l),0) for l in layers))
    if len(planes)<2:raise ValueError('two_original_actual_ground_plane_contacts_required')
    peers=[p for f in board.GetFootprints() if f!=cap for p in f.Pads()
        if p.GetNetCode()==supply.GetNetCode()]
    if len(peers)!=1:raise ValueError('unique_native_ordinary_owner_terminal_required')
    # Do not silently apply a loose ordinary RC seating bound to a selected
    # manufacturer bypass. This operator does not reassign such capacitors.
    with force._thermal_hint(hint):assigned=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    if any(row['cap_ref']==cap.GetReference() for row in assigned['assigned'].values()):
        raise ValueError('selected_device_bypass_requires_separate_nonworse_PI_receiver')
    # A rigid move of an EXISTING source-owned in-pad barrel may retain its
    # exact saved native factory rule. Profile names and an arbitrary new via
    # do not grant this context. The normal ordinary minima remain unchanged.
    import cec_existing_local_pofv_pad_rule as saved_rule
    context=(saved_rule.inspect(board,ground,via.GetPosition(),via.GetWidth(via.TopLayer()),
        via.GetDrillValue(),via.GetNetCode()) if via_uuid in grouped else None)
    if context is not None:context=json.loads(json.dumps(context,allow_nan=False))
    return dict(footprint_uuid=force._uid(cap),via_uuid=via_uuid,ref=cap.GetReference(),
        supply_pad_uuid=force._uid(supply),ground_pad_uuid=force._uid(ground),net=str(supply.GetNetname()),
        source_pose_nm=list(cap.GetPosition()),source_orientation=cap.GetOrientationDegrees(),
        source_via_nm=list(via.GetPosition()),source_ground_nm=list(ground.GetPosition()),
        diameter_nm=via.GetWidth(via.TopLayer()),drill_nm=via.GetDrillValue(),
        original_ground_planes=planes,owner_pad_uuid=force._uid(peers[0]),
        source_fields=[dict(uuid=force._uid(f),position_nm=list(f.GetPosition()),
            angle_deg=f.GetTextAngle().AsDegrees()) for f in cap.GetFields()],
        source_owner_distance_nm=math.dist(tuple(supply.GetPosition()),tuple(peers[0].GetPosition())),
        source_supply_nm=list(supply.GetPosition()),source_local_pad_rule=context)


def _barrel_process(board,scope,via,ground):
    """Receive retained source geometry/rule; never authorize a new small via.

    Native group-only controls independently prove the saved local rule is
    decisive. Here it is usable only after the same source pad/owned barrel
    receives a rigid RC transform; full saved-object replay remains required.
    """
    import cec_existing_local_pofv_pad_rule as saved_rule
    settings=board.GetDesignSettings();diameter=scope['diameter_nm'];drill=scope['drill_nm']
    if (force._uid(via)!=scope['via_uuid'] or via.GetNetname()!='GND'
            or via.GetViaType()!=pcbnew.VIATYPE_THROUGH or via.GetDrillValue()!=drill
            or via.TopLayer()!=pcbnew.F_Cu or via.BottomLayer()!=pcbnew.B_Cu
            or any(via.GetWidth(l)!=diameter for l in board.GetEnabledLayers().CuStack())):
        raise ValueError('RC_return_retained_source_barrel_geometry_required')
    if (diameter>=settings.m_ViasMinSize and drill>=settings.m_MinThroughDrill
            and diameter-drill>=2*settings.m_ViasMinAnnularWidth):
        return dict(ordinary_board_dimensions=True,existing_local_rule_retained=False)
    context=scope.get('source_local_pad_rule')
    if type(context) is not dict:raise ValueError('relocated_entry_below_native_absolute_via_floor')
    source=Path(context['source']);rule_path=Path(context['rule'])
    if (force._hash(source)!=context['source_sha256'] or force._hash(rule_path)!=context['rule_sha256']
            or fab.board_profile_name(board)!=context['profile']
            or list(saved_rule._floors(board)[:3])!=context['ordinary_board_limits_nm']):
        raise ValueError('RC_return_existing_native_rule_source_profile_or_floors_changed')
    original=pcbnew.LoadBoard(str(source))
    old_pad=next(p for f in original.GetFootprints() for p in f.Pads() if force._uid(p)==scope['ground_pad_uuid'])
    old_via=next(t for t in original.GetTracks() if force._uid(t)==scope['via_uuid'])
    fresh=saved_rule.inspect(original,old_pad,old_via.GetPosition(),diameter,drill,old_via.GetNetCode())
    if fresh is None or json.loads(json.dumps(fresh,allow_nan=False))!=context:
        raise ValueError('RC_return_source_local_rule_not_independently_rederived')
    old_groups=[g for g in original.Groups() if g.ContainsItem(old_via)]
    new_groups=[g for g in board.Groups() if g.ContainsItem(via)]
    if (len(old_groups)!=1 or len(new_groups)!=1 or force._uid(old_groups[0])!=force._uid(new_groups[0])
            or old_groups[0].GetName()!=saved_rule.GROUP or new_groups[0].GetName()!=saved_rule.GROUP
            or old_groups[0].IsLocked() or new_groups[0].IsLocked()
            or force._uid(ground)!=scope['ground_pad_uuid'] or ground.GetNetCode()!=via.GetNetCode()
            or via.GetPosition()!=ground.GetPosition()
            or not fab._pad_contains_circle(ground,via.GetPosition(),(diameter+1)//2,tolerance_nm=0)
            or saved_rule.geometry(context,(diameter/1e6,drill/1e6))!=(diameter/1e6,drill/1e6)):
        raise ValueError('RC_return_actual_unchanged_factory_group_and_exact_inpad_geometry_required')
    actual_rule=Path(board.GetFileName()).with_suffix('.kicad_dru')
    if not actual_rule.is_file() or force._hash(actual_rule)!=context['rule_sha256']:
        raise ValueError('RC_return_existing_rule_bytes_changed_or_absent')
    return dict(ordinary_board_dimensions=False,existing_local_rule_retained=True,
        source_context=context,only_exact_retained_source_barrel=True,new_barrel_or_geometry_authorized=False,
        independent_saved_native_membership_and_DRC_required=True,release_authority=False)


def pose(board,scope,position_nm,orientation_deg):
    if (type(position_nm) not in (tuple,list) or len(position_nm)!=2
            or any(type(v) is not int or abs(v)>2000000000 for v in position_nm)
            or type(orientation_deg) not in (int,float) or not math.isfinite(orientation_deg)
            or math.dist(position_nm,scope['source_pose_nm'])>6000000
            or (orientation_deg-scope['source_orientation'])%90!=0):
        raise ValueError('finite_six_mm_native_quarter_turn_pose_required')
    cap=next(f for f in board.GetFootprints() if force._uid(f)==scope['footprint_uuid'])
    via=next(t for t in board.GetTracks() if force._uid(t)==scope['via_uuid'])
    ground=next(p for p in cap.Pads() if force._uid(p)==scope['ground_pad_uuid'])
    supply=next(p for p in cap.Pads() if force._uid(p)==scope['supply_pad_uuid'])
    cap.SetOrientationDegrees(orientation_deg);cap.SetPosition(pcbnew.VECTOR2I(*position_nm))
    fields={force._uid(f):f for f in cap.GetFields()}
    for row in scope['source_fields']:
        fields[row['uuid']].SetPosition(pcbnew.VECTOR2I(*row['position_nm']))
        fields[row['uuid']].SetTextAngle(pcbnew.EDA_ANGLE(row['angle_deg'],pcbnew.DEGREES_T))
    angle=math.radians(orientation_deg-scope['source_orientation']);c,s=round(math.cos(angle)),round(math.sin(angle))
    dx,dy=(scope['source_via_nm'][i]-scope['source_ground_nm'][i] for i in (0,1))
    via.SetPosition(pcbnew.VECTOR2I(ground.GetPosition().x+c*dx+s*dy,ground.GetPosition().y-s*dx+c*dy))
    # Keep authored labels stationary; a separate readable-field stage can
    # move them after native route/placement receiving, not implicitly here.
    return cap,via,supply,ground


def preflight(board,scope,*,corridor_segments=(),corridor_layer=None,clearance_nm=200000):
    cap=next(f for f in board.GetFootprints() if force._uid(f)==scope['footprint_uuid'])
    via=next(t for t in board.GetTracks() if force._uid(t)==scope['via_uuid'])
    pads={force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}
    ground,supply=map(pads.get,(scope['ground_pad_uuid'],scope['supply_pad_uuid']))
    if corridor_segments and (corridor_layer is None or any(via.GetEffectiveShape(corridor_layer).Collide(
            pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*s),pcbnew.VECTOR2I(*t),width),clearance_nm)
            for s,t,width,_ in corridor_segments)):
        raise ValueError('actual_full_source_current_corridor_still_blocked')
    if math.dist(tuple(supply.GetPosition()),tuple(pads[scope['owner_pad_uuid']].GetPosition()))>max(6000000,scope['source_owner_distance_nm'])+1:
        raise ValueError('bounded_ordinary_owner_terminal_reach_exceeded')
    cap.BuildCourtyardCaches()
    placement._pose_preflight(board,cap)
    if not fab._pad_contains_circle(ground,via.GetPosition(),scope['diameter_nm']//2):
        raise ValueError('actual_ground_land_containment_lost')
    if not fab.local_pofv_via_decision(board,via)[0]:raise ValueError('actual_local_factory_owner_lost')
    process=_barrel_process(board,scope,via,ground)
    detail={}
    # The moved trial item is already in this read-only board. Exclude only
    # that exact same-position/net UUID from duplicate-hole discovery. All
    # NEW-hole absolute floors were checked above, with no identity waiver.
    if not fr._via_spot_clear(board,via.GetPosition(),scope['diameter_nm'],clearance_nm,{via.GetNetCode()},
            drill_nm=scope['drill_nm'],net_code=via.GetNetCode(),foreign_cache={},
            contained_layers=set(map(int,ground.GetLayerSet().CuStack())),report=detail,
            existing_via_uuid=scope['via_uuid']):
        raise ValueError('actual_all_layer_return_entry_refused:'+str(detail))
    for uid in scope['original_ground_planes']:
        z=next(z for z in board.Zones() if force._uid(z)==uid)
        if not any(z.IsOnLayer(l) and z.GetFilledPolysList(l).Collide(via.GetEffectiveShape(l),0)
                for l in board.GetEnabledLayers().CuStack()):
            raise ValueError('actual_original_ground_plane_entry_lost')
    return dict(ok=True,ordinary_net=scope['net'],actual_inpad_ground=True,
        retained_barrel_process=process,
        old_plane_contacts_preserved=True,ordinary_owner_reach_bounded=True,
        saved_native_partition_and_current_receiving_required=True,release_authority=False)


def reserve_future_pose(board,source,request,*,board_hint,blocked_net,timeout_s=10.):
    """Source-owned future lands/return as disposable routing obstacles only.

    It does not pre-approve a seat, move source material or authorize ripup.
    The caller must remove ALL returned items before saving any construction.
    Part and return geometry are rederived from the immutable saved source.
    """
    import cec_future_pose_clearance as future
    from cec_native_items import discard_items
    if (type(request) is not dict
            or set(request)!={'schema','source_sha256','via_uuid','position_nm','orientation_deg'}
            or type(request['schema']) is not int or request['schema']!=1
            or request['source_sha256']!=force._hash(source)
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10
            or type(blocked_net) is not str or not blocked_net):
        raise ValueError('exact_source_owned_future_RC_pose_required')
    deadline=time.monotonic()+timeout_s;parent=pcbnew.LoadBoard(str(source))
    scope=plan(parent,source,request['via_uuid'],hint=board_hint)
    if blocked_net in (scope['net'],'GND'):raise ValueError('foreign_owned_RC_future_obstacles_required')
    cap=next(f for f in parent.GetFootprints() if force._uid(f)==scope['footprint_uuid'])
    _,via,supply,_=pose(parent,scope,request['position_nm'],request['orientation_deg'])
    future_via_position=list(via.GetPosition())
    owner=next(p for f in parent.GetFootprints() for p in f.Pads() if force._uid(p)==scope['owner_pad_uuid'])
    if math.dist(tuple(supply.GetPosition()),tuple(owner.GetPosition()))>max(6000000,scope['source_owner_distance_nm'])+1:
        raise ValueError('bounded_ordinary_owner_terminal_reach_exceeded')
    # Reload the immutable source rather than undoing a trial transform:
    # native field motion and cached courtyards must not drift the witness.
    parent=pcbnew.LoadBoard(str(source))
    target=[v/1e6 for v in request['position_nm']]+[request['orientation_deg']]
    witness=future.plan(parent,{scope['ref']:target},source=source,board_hint=board_hint,
        timeout_s=max(.001,min(10.,deadline-time.monotonic())))
    items=[]
    try:
        items=future._install_reservations(board,witness,blocked_net,deadline)
        net=board.FindNet('GND')
        if net is None or net.GetNetCode()<=0:raise ValueError('actual_owned_future_return_net_required')
        v=pcbnew.PCB_VIA(board);v.SetPosition(pcbnew.VECTOR2I(*future_via_position))
        v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        v.SetWidth(scope['diameter_nm']);v.SetDrill(scope['drill_nm']);v.SetNet(net)
        board.Add(v);items.append(v)
        if request['source_sha256']!=force._hash(source) or time.monotonic()>=deadline:
            raise ValueError('future_RC_source_or_deadline_changed')
    except Exception:
        discard_items(board,items);raise
    return items,dict(source_sha256=request['source_sha256'],source_scope=scope,
        future_position_nm=future_via_position,source_derived_geometry=True,
        blockers=witness['blockers'],saved_copper=False,pose_admitted=False,release_authority=False)


def receive(source,candidate,*,via_uuid,board_hint,timeout_s=10.):
    """Rediscover the sole source-owned RC return; replay its exact rigid move.

    Only its actual component and one contained branch-free GND entry move.
    All old source copper survives. Ordinary additive leads must restore
    every old native partition; saved construction cannot choose ownership,
    power capacity, a new via rule, a different package or release authority.
    """
    from pathlib import Path
    import tempfile
    import cec_additive_route_receiving as additive
    import cec_board_geometry as geometry
    import cec_copper_echo as sexpr
    report=dict(schema=1,ok=False,complete=False,errors=[],
        scope='independent_source_owned_ordinary_RC_and_exact_return_pose',
        routing_admitted=False,current_qualified=False,placement_qualified=False,
        release_authority=False,source_material_retired=False)
    try:
        if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
                or not 0<timeout_s<=10 or type(via_uuid) is not str or not via_uuid):
            raise ValueError('bounded_source_RC_pose_receiving_required')
        deadline=time.monotonic()+timeout_s
        source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
        families=[force._family(p,board_hint) for p in (source,candidate)]
        epoch=force._code_identity()
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        scope=plan(parent,source,via_uuid,hint=board_hint)
        selected=[f for f in child.GetFootprints() if force._uid(f)==scope['footprint_uuid']]
        if len(selected)!=1:raise ValueError('saved_source_owned_RC_missing')
        cap=selected[0]
        if geometry.outline_bbox_mm(parent)!=geometry.outline_bbox_mm(child):
            raise ValueError('owned_RC_pose_outline_changed')
        old_parts=ordinary._partition(parent,deadline)
        pads=[p for f in parent.GetFootprints() for p in f.Pads() if force._uid(f)==scope['footprint_uuid']]
        via=next(t for t in parent.GetTracks() if force._uid(t)==via_uuid)
        keys={force._uid(q):force._item_key(q) for q in [*pads,via]}
        old_pose=[*scope['source_pose_nm'],scope['source_orientation']]
        if [*list(cap.GetPosition()),cap.GetOrientationDegrees()]==old_pose:
            raise ValueError('nonempty_source_owned_RC_pose_required')
        posed_cap,posed_via,_,_=pose(parent,scope,list(cap.GetPosition()),cap.GetOrientationDegrees())
        # These are the source-derived items, not arbitrary child items.
        # Exact native serialized replay below receives package/via properties.
        report['source_pose_preflight']=preflight(parent,scope)
        new_keys={force._item_key(q):keys[force._uid(q)] for q in [*posed_cap.Pads(),posed_via]}
        report['candidate_pose_preflight']=preflight(child,scope)
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        if old.keys()-new.keys():raise ValueError('owned_RC_pose_retired_source_object')
        incoming=new.keys()-old.keys()
        additions=[t for t in child.GetTracks() if force._uid(t) in incoming]
        if not 0<=len(additions)<=32 or {force._uid(t) for t in additions}!=incoming:
            raise ValueError('only_bounded_ordinary_RC_leads_may_be_added')
        spec=fr._project_netclass_resolver(str(source))(scope['net']) or {}
        floor=max(parent.GetDesignSettings().m_TrackMinWidth,math.ceil((spec.get('track_width') or .2)*1e6))
        if any(t.GetClass()!='PCB_TRACK' or t.GetNetname()!=scope['net']
                or not floor<=t.GetWidth()<=350000 for t in additions):
            raise ValueError('ordinary_source_class_RC_tracks_only')
        with tempfile.TemporaryDirectory(prefix='cec-owned-RC-pose-') as work:
            projected=force._copy_family(source,Path(work)/'projected')
            additive._ground_refill(parent);field._save_field_snapshot(parent,projected)
            _,expected=additive._nodes(projected)
            allowed={scope['footprint_uuid'],via_uuid}
            allowed|={force._uid(z) for z in parent.Zones() if not z.GetIsRuleArea() and z.GetNetname()=='GND'}
            if (expected.keys()!=old.keys() or any(sexpr._freeze(expected[u])!=sexpr._freeze(old[u])
                    for u in old if u not in allowed)):
                raise ValueError('source_RC_repose_changed_unowned_native_material')
            remaining=min(10.,deadline-time.monotonic())
            if remaining<=0:raise ValueError('source_RC_pose_receiving_deadline')
            replay=additive.receive(projected,candidate,timeout_s=remaining)
            report['exact_native_source_pose_plus_additions']=replay
            if not replay['ok'] or not replay['complete']:
                raise ValueError('saved_owned_RC_source_replay_refused:'+str(replay['errors']))
        retained=set().union(*old_parts)
        last=ordinary._partition(child,deadline,retained_keys=retained,_identity_rebindings=new_keys)
        if any(not any(p<=q for q in last) for p in old_parts):
            raise ValueError('source_RC_pose_original_partition_lost')
        if (time.monotonic()>=deadline or epoch!=force._code_identity()
                or families!=[force._family(p,board_hint) for p in (source,candidate)]):
            raise ValueError('source_RC_pose_identity_or_deadline_changed')
        report.update(ok=True,complete=True,source_scope=scope,
            added_ordinary_lead_count=len(additions),all_source_contacts_preserved_without_new_leads=not bool(additions),
            source_owned_inpad_entry_geometry_preserved=True,
            all_original_terminal_and_copper_partitions_preserved=True,
            exact_unowned_source_nodes_preserved=True,source_candidate_and_code_unchanged=True,
            full_native_DRC_field_current_pair_and_assembly_receiving_required=True)
    except Exception as exc:report['errors'].append(type(exc).__name__+':'+str(exc))
    return report
