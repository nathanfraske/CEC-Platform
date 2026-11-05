"""Positive ordinary-signal scope for additive native-portal geometry.

Scope is independently derived from the existing ordinary eligibility owner,
not borrowed from quiet outputs. No power, pair, sense or placement authority.
All ten shared receiving gates remain mandatory before private selection.
"""
import math
from pathlib import Path
import time


def _budget(value,maximum):
    if type(value)not in(int,float)or not math.isfinite(value)or not 0<value<=maximum:
        raise ValueError('bounded_ordinary_signal_work_lease_required')
    return float(value)


def plan(board,source,*,board_hint,net,timeout_s=10.):
    import cec_force_current as force
    import cec_ordinary_route_receiving as ordinary
    import cec_route_dimensions as dimensions
    import cec_fr as fr
    if type(board_hint)is not str or not board_hint or type(net)is not str or not net:
        raise ValueError('explicit_ordinary_source_net_and_board_required')
    deadline=time.monotonic()+_budget(timeout_s,10.);source=Path(source).resolve(strict=True)
    result=dict(scope='source_typed_stationary_ordinary_signal_join',source=str(source),
        board_hint=board_hint,net=net,complete=False,routing_admitted=False,
        current_qualified=False,release_authority=False,no_path_proof=False)
    if net not in ordinary.eligible_nets(board,source,board_hint):
        result['reason']='source_net_not_positively_ordinary';return result
    pads=[p for fp in board.GetFootprints()for p in fp.Pads()if p.GetNetname()==net]
    if not 2<=len(pads)<=256:raise ValueError('bounded_actual_ordinary_pad_inventory_required')
    by_id={force._uid(p):p for p in pads}
    if len(by_id)!=len(pads):raise ValueError('ambiguous_ordinary_native_land_identity')
    graph=fr._read_only_route_connectivity(board);components={};remaining=set(by_id)
    while remaining:
        if time.monotonic()>=deadline:raise ValueError('ordinary_source_inventory_deadline')
        uid=min(remaining);root=by_id[uid]
        reached=({uid}|{force._uid(i)for i in graph.GetConnectedItems(root)})&by_id.keys()
        for u in reached:components[u]=uid
        remaining-=reached
    choices=[(math.dist(tuple(a.GetPosition()),tuple(b.GetPosition())),force._uid(a),force._uid(b))
        for i,a in enumerate(sorted(pads,key=force._uid))for b in sorted(pads,key=force._uid)[i+1:]
        if components[force._uid(a)]!=components[force._uid(b)]]
    if not choices:
        result['reason']='ordinary_native_pad_components_already_joined';return result
    _,a,b=min(choices)
    spec=fr._project_netclass_resolver(str(source))(net)or{}
    compiled=dimensions.compile_spec(spec,limits=dimensions.board_limits(board),role='branch')
    width=round(compiled['track_width']*1e6)
    clearance=max(int(board.GetDesignSettings().m_MinClearance),round(float(spec.get('clearance')or 0)*1e6))
    if not 0<width<500000 or clearance<=0:raise ValueError('bounded_authored_ordinary_geometry_required')
    if time.monotonic()>=deadline:raise ValueError('ordinary_source_scope_deadline')
    result.update(complete=True,request=dict(net=net,root_pad_uuid=a,target_pad_uuid=b,
        width_nm=width,clearance_nm=clearance,source_class=spec.get('name','Default'),
        native_pad_component_count=len(set(components.values()))))
    return result


def _pads(board,request):
    import cec_force_current as force
    pads={force._uid(p):p for fp in board.GetFootprints()for p in fp.Pads()}
    ends=[pads.get(request[k])for k in('root_pad_uuid','target_pad_uuid')]
    if any(p is None or p.GetNetname()!=request['net']for p in ends):
        raise ValueError('exact_ordinary_native_lands_required')
    return ends


def construct_private(source,candidate,proposal,*,board_hint,timeout_s=20.):
    import pcbnew
    import cec_force_current as force
    import cec_certificate_repair as repair
    import cec_native_portal_geometry as geometry
    started=time.monotonic();deadline=started+_budget(timeout_s,20.)
    source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
    if source==candidate or force._hash(source)!=force._hash(candidate):
        raise ValueError('exact_private_ordinary_source_copy_required')
    board=pcbnew.LoadBoard(str(source))
    fresh=plan(board,source,board_hint=board_hint,net=proposal['net'],timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    if not fresh['complete']:raise ValueError('fresh_ordinary_source_scope_refused')
    request=fresh['request'];ends=_pads(board,request)
    target=dict(target_net=request['net'],width_mm=request['width_nm']/1e6,
        source_board_hint=board_hint,
        clearance_mm=request['clearance_nm']/1e6,retained_same_face_track_ends=True,retained_barrel_face_access=True,
        source_local_pad_rule_launches=True,
        middle_grid_schedule_mm=[.5,.25],
        route_endpoints=[dict(uuid=force._uid(p),kind='pad',
            x_mm=p.GetPosition().x/1e6,y_mm=p.GetPosition().y/1e6)for p in ends])
    remaining=deadline-time.monotonic()
    if remaining<=3.:
        return dict(complete=False,reason='ordinary_construction_lease_before_search',release_authority=False)
    outer=repair._WORKER_DEADLINE.get()
    token=repair._WORKER_DEADLINE.set(min(deadline,outer)if outer is not None else deadline)
    try:
        attempt=repair._spawn_apply(geometry.apply_native_portals,
            (str(candidate),target,min(10.,remaining-3.)),timeout_s=remaining,search_budget_arg=2)
    finally:repair._WORKER_DEADLINE.reset(token)
    return dict(complete=bool(attempt.get('closed'))and time.monotonic()<deadline,
        construction=attempt,independently_recompiled_source_request=request,
        target=target,elapsed_s=time.monotonic()-started,routing_admitted=False,
        current_qualified=False,release_authority=False)


def receive(source,candidate,*,board_hint,net,timeout_s=10.):
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_additive_route_receiving as additive
    import cec_source_literal_additions as literal
    deadline=time.monotonic()+_budget(timeout_s,10.)
    result=dict(ok=False,complete=False,errors=[],scope='ordinary_saved_additive_native_join',
        routing_admitted=False,current_qualified=False,release_authority=False,
        whole_shared_stage_still_required=True)
    try:
        source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        if source==candidate:raise ValueError('distinct_ordinary_source_and_candidate_required')
        epoch=force._code_identity();families=[force._family(p,board_hint)for p in(source,candidate)]
        before,after=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
        scoped=plan(before,source,board_hint=board_hint,net=net,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        if not scoped['complete']:raise ValueError('fresh_ordinary_saved_scope_refused')
        request=scoped['request'];ends=_pads(after,request);source_ends=_pads(before,request)
        for a,b in zip(source_ends,ends):
            if (force._item_key(a)!=force._item_key(b)or tuple(a.GetSize())!=tuple(b.GetSize())
                    or a.GetShape()!=b.GetShape()or a.GetAttribute()!=b.GetAttribute()
                    or tuple(a.GetLayerSet().CuStack())!=tuple(b.GetLayerSet().CuStack())
                    or a.GetParentFootprint().GetValue()!=b.GetParentFootprint().GetValue()
                    or a.GetParentFootprint().GetFPIDAsString()!=b.GetParentFootprint().GetFPIDAsString()):
                raise ValueError('ordinary_terminal_identity_pose_or_geometry_changed')
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        if old.keys()-new.keys():raise ValueError('ordinary_additive_scope_retired_source_material')
        incoming=new.keys()-old.keys()
        material={force._uid(t):t for t in after.GetTracks()if force._uid(t)in incoming}
        if not 1<=len(material)<=512:raise ValueError('bounded_new_ordinary_native_material_required')
        names=literal.incoming_copper_nets(candidate.read_text(),set(incoming))
        if any(n!=net for n in names.values()):raise ValueError('ordinary_literal_saved_net_mismatch')
        if any(t.GetNetname()!=net or t.GetClass()not in('PCB_TRACK','PCB_VIA')
            or t.GetClass()=='PCB_TRACK'and t.GetWidth()!=request['width_nm']for t in material.values()):
            raise ValueError('ordinary_new_material_net_kind_or_width_changed')
        graph=fr._read_only_route_connectivity(after)
        reached={force._uid(ends[0])}|{force._uid(i)for i in graph.GetConnectedItems(ends[0])}
        if force._uid(ends[1])not in reached or not material.keys()<=reached:
            raise ValueError('new_ordinary_material_not_one_native_terminal_join')
        counts=[fr.net_connectivity_component_count(b,b.GetNetcodeFromNetname(net))for b in(before,after)]
        if counts[1]>=counts[0]:raise ValueError('ordinary_native_component_count_not_reduced')
        if epoch!=force._code_identity()or families!=[force._family(p,board_hint)for p in(source,candidate)]or time.monotonic()>=deadline:
            raise ValueError('ordinary_source_candidate_code_or_deadline_changed')
        result.update(ok=True,complete=True,source_components=counts[0],candidate_components=counts[1],
            added_native_uuids=sorted(material),source_ordinary_scope_independently_recompiled=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError)as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
