"""Source-typed quiet output proposals and saved native join receiving.

These signals remain Sense-class victims, never ordinary signals or power
branches. Positive source/package roles supply routing scope only. They do
not prove ADC configuration, electrical loading, accuracy or current ratings.
The shared received stage must still receive the exact source delta, current,
pairs, field, Ground returns, intakes, parity, native DRC, craft and live epoch.
"""
import math
import time
from pathlib import Path


def _budget(value,maximum):
    if type(value)not in (int,float)or not math.isfinite(value)or not 0<value<=maximum:
        raise ValueError('bounded_quiet_signal_work_lease_required')
    return float(value)


def plan(board,source,*,board_hint,net,timeout_s=10.):
    import cec_quiet_signal_requests as requests
    import cec_fr as fr
    source=Path(source).resolve(strict=True)
    if type(net)is not str or not net:raise ValueError('explicit_quiet_signal_net_required')
    report=requests.plan(board,source,board_hint=board_hint,timeout_s=_budget(timeout_s,10.))
    result=dict(scope='source_typed_stationary_quiet_signal_join',board_hint=board_hint,
        source=str(source),net=net,complete=False,source_requests=report,
        routing_admitted=False,current_qualified=False,adc_mode_qualified=False,
        load_qualified=False,release_authority=False,no_path_proof=False)
    if report.get('complete')is not True:
        result['reason']='source_request_compilation_incomplete';return result
    selected=[r for r in report['requests']if r['net']==net]
    if len(selected)!=1:
        result['reason']='no_unique_source_typed_quiet_request';return result
    request=selected[0]
    if fr.net_connectivity_component_count(board,board.GetNetcodeFromNetname(net))<2:
        result['reason']='quiet_signal_already_native_connected';return result
    result.update(complete=True,request=request)
    return result


def _pads(board,request):
    import cec_force_current as force
    pads={force._uid(p):p for fp in board.GetFootprints()for p in fp.Pads()}
    roots=[pads.get(request[k])for k in ('root_pad_uuid','target_pad_uuid')]
    if any(p is None or p.GetNetname()!=request['net']for p in roots):
        raise ValueError('exact_quiet_request_native_lands_required')
    return roots


def _geometry_worker(candidate,target,search_s):
    """Geometry-only first-pair breadth; saved/full receiving is separate."""
    import cec_certificate_repair as repair
    return repair._certified_via_target_worker(candidate,target,search_s,
        additive_only=True,seat_pair_first=True)


def _native_portal_worker(candidate,target,search_s):
    """Typed quiet wrapper; generic geometry supplies NO quiet authority."""
    import cec_fr as fr
    import cec_native_portal_geometry as geometry
    _budget(search_s,10.)
    spec=fr._project_netclass_resolver(str(candidate))(target['target_net'])or{}
    if str(spec.get('name','')).casefold()!='sense':
        raise ValueError('quiet_portal_cannot_relax_sensitive_project_class')
    result=geometry.apply_native_portals(candidate,target,search_s,launch_labels=('input_first','output_first'))
    result['search_scope']='source_typed_quiet_native_endpoint_portals'
    return result


def construct_private(source,candidate,proposal,*,board_hint,timeout_s=20.,strategy='seat_pair'):
    """Recompile real scope before a bounded generic geometry-only attempt."""
    import pcbnew
    import cec_force_current as force
    import cec_additive_pair_repair as additive
    import cec_certificate_repair as repair
    if strategy not in ('seat_pair','native_portals') or type(strategy)is not str:
        raise ValueError('explicit_bounded_quiet_geometry_strategy_required')
    started=time.monotonic();seconds=_budget(timeout_s,20.);deadline=started+seconds
    source,candidate=[Path(p).resolve(strict=True)for p in (source,candidate)]
    if source==candidate or force._hash(source)!=force._hash(candidate):
        raise ValueError('exact_private_source_copy_required')
    b=pcbnew.LoadBoard(str(source))
    remaining=deadline-time.monotonic()
    if remaining<=0:raise ValueError('quiet_construction_lease_exhausted_before_source_scope')
    fresh=plan(b,source,board_hint=board_hint,net=proposal['net'],timeout_s=min(10.,remaining))
    if not fresh['complete']:raise ValueError('fresh_source_quiet_request_refused')
    request=fresh['request'];pads=_pads(b,request)
    endpoints=[]
    for p in pads:
        endpoints.append(dict(uuid=force._uid(p),kind='pad',net=request['net'],
            ref=p.GetParentFootprint().GetReference(),pad=p.GetNumber(),
            native_layer=b.GetLayerName(p.GetLayer()),
            copper_layers=[b.GetLayerName(l)for l in p.GetLayerSet().CuStack()],
            x_mm=p.GetPosition().x/1e6,y_mm=p.GetPosition().y/1e6))
    target=dict(target_net=request['net'],route_endpoints=endpoints,
        width_mm=request['width_nm']/1e6,clearance_mm=request['clearance_nm']/1e6,
        distance_mm=math.dist(tuple(pads[0].GetPosition()),tuple(pads[1].GetPosition()))/1e6)
    if strategy=='native_portals':
        # The freshly compiled manufacturer-typed quiet request owns scope;
        # local saved-rule geometry does not turn Sense into ordinary routing.
        target.update(retained_same_face_track_ends=True,retained_barrel_face_access=True,
            source_local_pad_rule_launches=True)
    remaining=deadline-time.monotonic()
    # The lease covers fresh scope compilation, setup, search and saving.
    # Do not hand the search a new full lease after spending time on scope.
    # Keep a real child setup/save reserve and clamp the supervisor as well.
    if remaining<=3.:
        return dict(complete=False,reason='quiet_construction_lease_exhausted_before_search',
            elapsed_s=time.monotonic()-started,routing_admitted=False,release_authority=False)
    outer=repair._WORKER_DEADLINE.get()
    token=repair._WORKER_DEADLINE.set(min(deadline,outer)if outer is not None else deadline)
    try:
        # At most ten seconds of geometric search/preflight, with independent
        # source compilation and native-save/IPC space INSIDE this one lease.
        # A successful native field proof must not be dropped merely because
        # setup was incorrectly charged against a fresh eight-second search.
        search=min(10.,remaining-3.)
        selected_worker=_native_portal_worker if strategy=='native_portals'else _geometry_worker
        attempt=repair._spawn_apply(selected_worker,(str(candidate),target,search),
            timeout_s=remaining,search_budget_arg=2)
    finally:repair._WORKER_DEADLINE.reset(token)
    return dict(complete=bool(attempt.get('closed'))and time.monotonic()<deadline,construction=attempt,
        elapsed_s=time.monotonic()-started,whole_construction_lease_s=seconds,
        geometry_strategy=strategy,
        independently_recompiled_source_request=request,target=target,
        routing_admitted=False,current_qualified=False,release_authority=False)


def receive(source,candidate,*,board_hint,net,timeout_s=10.):
    """Receive typed scope and a real saved join, NOT the whole shared stage."""
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_additive_route_receiving as additive
    import cec_source_literal_additions as literal
    started=time.monotonic();deadline=started+_budget(timeout_s,10.)
    result=dict(scope='source_typed_quiet_signal_saved_native_join',ok=False,complete=False,
        errors=[],routing_admitted=False,current_qualified=False,adc_mode_qualified=False,
        load_qualified=False,release_authority=False,
        mandatory_shared_receiving=['invariants','field','ground_returns','source_intake',
            'candidate_intake','parity','native','craft','source_live'])
    try:
        source,candidate=[Path(p).resolve(strict=True)for p in (source,candidate)]
        families=[force._family(p,board_hint)for p in (source,candidate)];code=force._code_identity()
        parent,child=[pcbnew.LoadBoard(str(p))for p in (source,candidate)]
        proof=plan(parent,source,board_hint=board_hint,net=net,
            timeout_s=min(10.,max(.001,deadline-time.monotonic())))
        result['independently_compiled_source_scope']=proof
        if not proof['complete']:raise ValueError('source_quiet_request_unavailable')
        request=proof['request'];old_pads=_pads(parent,request);new_pads=_pads(child,request)
        for a,b in zip(old_pads,new_pads):
            if (force._item_key(a)!=force._item_key(b)or a.GetNetname()!=b.GetNetname()
                    or tuple(a.GetSize())!=tuple(b.GetSize())or a.GetShape()!=b.GetShape()
                    or a.GetAttribute()!=b.GetAttribute()
                    or tuple(a.GetLayerSet().CuStack())!=tuple(b.GetLayerSet().CuStack())
                    or a.GetParentFootprint().GetValue()!=b.GetParentFootprint().GetValue()
                    or a.GetParentFootprint().GetFPIDAsString()!=b.GetParentFootprint().GetFPIDAsString()):
                raise ValueError('quiet_terminal_identity_pose_or_geometry_changed')
        _,before=additive._nodes(source);_,after=additive._nodes(candidate)
        if before.keys()-after.keys():raise ValueError('quiet_additive_scope_retired_source_material')
        incoming=after.keys()-before.keys()
        native={force._uid(t):t for t in child.GetTracks()if force._uid(t)in incoming}
        if not native or len(native)>512:raise ValueError('bounded_new_quiet_native_material_required')
        saved_nets=literal.incoming_copper_nets(candidate.read_text(),set(incoming))
        if any(name!=net for name in saved_nets.values()):
            raise ValueError('literal_saved_quiet_net_differs_from_native_signal')
        if any(t.GetNetname()!=net or t.GetClass()not in ('PCB_TRACK','PCB_VIA')
                or t.GetClass()=='PCB_TRACK'and t.GetWidth()!=request['width_nm']for t in native.values()):
            raise ValueError('new_quiet_material_net_kind_or_class_width_changed')
        resolver=fr._project_netclass_resolver(str(candidate));spec=resolver(net)or{}
        if str(spec.get('name','')).casefold()!='sense':
            raise ValueError('quiet_signal_lost_sensitive_project_class')
        graph=fr._read_only_route_connectivity(child)
        reached={force._uid(new_pads[0])}|{force._uid(i)for i in graph.GetConnectedItems(new_pads[0])}
        if force._uid(new_pads[1])not in reached or not native.keys()<=reached:
            raise ValueError('new_quiet_copper_is_not_one_rooted_native_terminal_join')
        counts=[fr.net_connectivity_component_count(b,b.GetNetcodeFromNetname(net))for b in (parent,child)]
        if counts[1]>=counts[0]:raise ValueError('quiet_native_component_count_not_reduced')
        if (families!=[force._family(p,board_hint)for p in (source,candidate)]
                or code!=force._code_identity()or time.monotonic()>=deadline):
            raise ValueError('quiet_source_candidate_code_epoch_or_lease_changed')
        result.update(ok=True,complete=True,source_components=counts[0],candidate_components=counts[1],
            added_native_uuids=sorted(native),source_class_preserved=True,
            whole_shared_stage_still_required=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=round(time.monotonic()-started,6)
    return result


def receive_projected(source,candidate,*,board_hint,required_quiet_output_pad_uuids,
                      macro_options,timeout_s=10.):
    """Explicit complete-macro quiet path only; legacy receive is unchanged.

    Recompile original Source and the actual saved poses independently. No
    caller packet or hypothetical baseline is authority. This never invokes
    complete_macro.receive: that separate owner must still receive every
    other changed node on the same final candidate, followed by all16.
    """
    import cec_macro_quiet_output as projected
    return projected.receive(source,candidate,board_hint=board_hint,
        required_quiet_output_pad_uuids=required_quiet_output_pad_uuids,
        macro_options=macro_options,timeout_s=timeout_s)
