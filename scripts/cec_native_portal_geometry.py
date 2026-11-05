"""Geometry-only native endpoint search; source role and admission are external.

No quiet, ordinary, power, pair or Kelvin role is inferred by this helper.
Each caller must freshly prove its own source scope and saved transaction.
"""
import math
import time


def _budget(value):
    if type(value)not in(int,float)or not math.isfinite(value)or not 0<value<=10.:
        raise ValueError("bounded_native_portal_work_lease_required")
    return float(value)


def _grid_schedule(value):
    """Finite proposal resolutions, not clearance or manufacturing rules.

    Omitted inputs retain the original single-resolution search. A caller
    may spend the SAME lease on successively finer grids; native channel
    axes, endpoint geometry and all complete-operation guards are unchanged.
    """
    if (type(value)not in(tuple,list)or not 1<=len(value)<=3
            or any(type(x)not in(int,float)or not math.isfinite(x)or not .1<=x<=1.
                for x in value)
            or any(a<=b for a,b in zip(value,value[1:]))):
        raise ValueError('finite_strictly_refining_native_portal_grid_schedule_required')
    return tuple(float(x)for x in value)


def _face_strata_pairs(pairs,*,maximum=12):
    """Schedule singleton SUBSETS of already-proved native face menus.

    One combined heap can spend its lease on the cheap surface start before
    expanding a retained barrel's other faces. Fund distinct layer topologies
    once, not repeated physical aliases. This creates neither copper nor face
    access; the caller retains the original combined portfolio and guards.
    """
    if type(maximum)is not int or not 1<=maximum<=16 or len(pairs)>32:
        raise ValueError('bounded_native_face_strata_required')
    choices={}
    for index,pair in enumerate(pairs):
        if len(pair)!=2:raise ValueError('two_proved_native_face_menus_required')
        faces=[p.get('layers')for p in pair]
        if any(type(ls)not in(list,tuple)or not ls or len(ls)>8 or len(set(ls))!=len(ls)
                or any(type(l)is not int for l in ls)for ls in faces):
            raise ValueError('literal_proved_native_face_menus_required')
        if all(len(ls)==1 for ls in faces):continue
        for first in sorted(faces[0]):
            for last in sorted(faces[1]):
                choices.setdefault((first,last),(index,pair))
    result=[]
    # Common faces need no new layer jump; all other proven topologies follow
    # deterministically. These are proposal priorities, never via permission.
    for signature in sorted(choices,key=lambda s:(s[0]!=s[1],s))[:maximum]:
        index,pair=choices[signature]
        result.append(tuple(dict(p,layers=[face])for p,face in zip(pair,signature)))
    return result


def _lane_request(value):
    """A search restriction only; never endpoint, role or layer authority."""
    if value is None:return None
    if(type(value)is not dict or set(value)!={'kind','pair_index','from_layer','to_layer','reverse'}
            or value['kind']not in('source_local_face','retained_face')
            or type(value['pair_index'])is not int or not 0<=value['pair_index']<(
                16 if value['kind']=='source_local_face'else 32)
            or any(type(value[k])is not int or not 0<=value[k]<=31 for k in('from_layer','to_layer'))
            or type(value['reverse'])is not bool):
        raise ValueError('exact_bounded_native_topology_lane_required')
    return dict(value)


def _lane_pair(pairs,lane):
    """Narrow a freshly proved pair, preserving all non-layer metadata."""
    lane=_lane_request(lane)
    if lane is None or lane['pair_index']>=len(pairs):
        raise ValueError('requested_native_lane_pair_not_available')
    pair=pairs[lane['pair_index']]
    if len(pair)!=2:raise ValueError('two_native_lane_endpoints_required')
    result=[]
    for row,key in zip(pair,('from_layer','to_layer')):
        layers=row.get('layers')
        if(type(layers)not in(list,tuple)or not 1<=len(layers)<=8
                or any(type(v)is not int for v in layers)or lane[key]not in layers):
            raise ValueError('requested_lane_face_not_positively_proved')
        result.append(dict(row,layers=[lane[key]]))
    return tuple(result)


def _source_local_pair_menu(board,roots,menus,*,width,clearance,layers,deadline,
        contained_intervals_only=False):
    """Fresh real Source-rule proposals and original retained endpoint rows."""
    import cec_source_rule_signal_launches as local
    report=dict(scope='source_rule_local_signal_portfolio',launch_menus=[],attempts=[],
        release_authority=False,no_path_proof=False)
    proposed=[]
    for index,pad in enumerate(roots):
        # Do not spend the other terminal's finite launch lease rediscovering
        # a new hole where a positively rooted native barrel ALREADY exposes
        # every authorized route face. These rows are supplied by the native
        # component-port compiler, not by source-local proposal metadata.
        # This only prunes redundant proposal work; it creates no access or
        # exemption. The retained menu and complete saved guards stay intact.
        complete_ports=[r for r in menus[index]if r.get('retained_barrel_uuid')
            and r.get('native_finite_track_barrel_contact')is True
            and r.get('retained_same_face_root_pad_uuid')==str(pad.m_Uuid.AsString())
            and set(layers)<=set(r.get('layers',()))]
        if complete_ports:
            report['launch_menus'].append(dict(choices=[],complete=True,
                reason='retained_rooted_barrel_already_exposes_all_authorized_faces',
                retained_barrel_uuids=sorted({r['retained_barrel_uuid']for r in complete_ports}),
                new_hole_requested=False,release_authority=False))
            proposed.append([])
            continue
        policy=dict(contained_intervals_only=True)if contained_intervals_only else{}
        q=local.propose(board,pad,width_nm=width,clearance_nm=clearance,
            route_layers=layers,deadline=min(deadline,time.monotonic()+1.),max_sites=4,**policy)
        report['launch_menus'].append(q);proposed.append(q['choices'])
    if not any(proposed):return [],report
    def old(row):return dict(at_nm=row['at_nm'],layers=row['layers'],operations=[],retained_native_contact=row)
    options=[[old(r)for r in menu[:4]]+p for menu,p in zip(menus,proposed)]
    pairs=[(a,b)for a in options[0]for b in options[1]if a['operations']or b['operations']]
    pairs.sort(key=lambda p:(-(bool(p[0]['operations'])+bool(p[1]['operations'])),
        math.dist(p[0]['at_nm'],p[1]['at_nm']),p[0]['at_nm'],p[1]['at_nm']))
    seen=set();work=[]
    for a,b in pairs:
        key=(tuple(a['at_nm']),tuple(b['at_nm']),tuple(a['layers']),tuple(b['layers']))
        if key not in seen:seen.add(key);work.append((a,b))
        if len(work)>=16:break
    return work,report


def _source_local_operations(board,roots,menus,*,net,width,clearance,layers,bridges,
        deadline,guard,planar,turn_guard,lane=None,contained_intervals_only=False):
    """Compose new local launches with a route; do not invent native aliases."""
    import json
    import pcbnew
    import cec_fr as fr
    import cec_field_coupling as field
    import cec_certificate_repair as repair
    import cec_field_search as field_search
    from cec_route_proposal_guard import RouteProposalGuard
    started=time.monotonic();lane=_lane_request(lane)
    if lane is not None and lane['kind']!='source_local_face':
        raise ValueError('source_prefix_lane_kind_required')
    work,report=_source_local_pair_menu(board,roots,menus,width=width,clearance=clearance,
        layers=layers,deadline=deadline,contained_intervals_only=contained_intervals_only)
    if not work:
        if lane is not None:raise ValueError('requested_source_local_lane_not_available')
        return None,report
    source=str(board.GetFileName());source_geometry=field._field_snapshot_inventory(board)
    spec=fr._project_netclass_resolver(source)(net)or{}
    contexts={};setup_elapsed=0.
    def prepare(pair):
        nonlocal setup_elapsed
        prefix=RouteProposalGuard._unpack(pair[0]['operations']+pair[1]['operations'])
        vias=[op for op in prefix if op[0]=='via'];gap=int(board.GetDesignSettings().m_HoleToHoleMin)
        if any(math.dist(tuple(a[1]),tuple(b[1]))*2<pcbnew.FromMM(a[2])+pcbnew.FromMM(b[2])+2*gap
                for i,a in enumerate(vias)for b in vias[i+1:]):return None
        # Native endpoint seeds must be REAL copper, not proposed metadata.
        # Materialize only on this disposable private board; a refusal drops
        # the whole object graph. Original source/guard remain untouched.
        key=json.dumps(pair[0]['operations']+pair[1]['operations'],sort_keys=True)
        if key not in contexts:
            setup_started=time.monotonic()
            scratch=pcbnew.LoadBoard(source)
            if field._field_snapshot_inventory(scratch)!=source_geometry:
                raise ValueError('local_signal_prefix_requires_exact_saved_source')
            scratch_code=scratch.GetNetcodeFromNetname(net)
            if scratch_code<=0:raise ValueError('positive_scratch_local_signal_net_required')
            repair._lay_ops(scratch,prefix,scratch_code,lock=False)
            foreign={};local_planar=field_search.PlanarSearchGuard(scratch,net,
                netclass_resolver=fr._project_netclass_resolver(source,board=scratch))
            if getattr(local_planar,'active',True)is False:local_planar=None
            contexts[key]=(prefix,scratch,scratch_code,foreign,local_planar)
            setup_elapsed+=time.monotonic()-setup_started
            report.update(immutable_prefix_setup_elapsed_s=setup_elapsed,
                prefix_cache_materializations=len(contexts),
                topology_search_lease_allocated_after_prefix_setup=True)
        return contexts[key]
    def search(pair,first,last,lease,*,face_stratified):
        prepared=prepare(pair)
        if prepared is None or time.monotonic()>=lease:return None
        prefix,scratch,scratch_code,foreign,local_planar=prepared
        def complete_ok(middle):
            ops=[*prefix,*middle]
            return (turn_guard is None or turn_guard(ops))and guard(ops)
        diagnostics={};a,b=pair[first],pair[last]
        middle=fr._lastmile_bridge(scratch,tuple(a['at_nm']),set(a['layers']),
            tuple(b['at_nm']),set(b['layers']),width,scratch_code,bridges,clearance,
            drill=float(spec.get('via_drill')or .3),dia=float(spec.get('via_diameter')or .6),
            leg_ok=lambda p,q,r:fr._edge_leg_clear(scratch,p,q,r),allow_maze=True,
            foreign_cache=foreign,width_for_layer=lambda layer:width,deadline_monotonic=lease,
            diagnostics=diagnostics,ops_ok=complete_ok,planar_guard=local_planar,multilayer_lays=layers,
            _multilayer_only=True,_multilayer_pair_limit=1,native_endpoint_seeds=True,
            middle_native_board_envelope=True,middle_grid_mm=.25,obstacle_channel_axes=True,
            canonical_turns_only=True,middle_max_vias=2,
            max_expanded_states=200000 if lane is not None else 50000,search_wall_cap_s=10.)
        report['attempts'].append(dict(local_endpoints=[a,b],found=middle is not None,diagnostics=diagnostics,
            face_stratified=face_stratified,launch_order=[first,last],
            proposal_guard_last_attempt=(guard.last_attempt()if callable(getattr(guard,'last_attempt',None))else None),
            local_original_deadline_monotonic=deadline,deadline_monotonic=lease,
            exact_prefix_materialized_on_disposable_board=True,original_board_unchanged=
                field._field_snapshot_inventory(board)==source_geometry))
        if middle is not None and complete_ok(middle):
            report.update(elapsed_s=time.monotonic()-started,complete_local_launch_prefix_in_guard=True)
            return [*prefix,*middle]
        return None
    if lane is not None:
        pair=_lane_pair(work,lane)
        # Setup remains charged to this worker's ORIGINAL lease; it cannot
        # reset the cap. Unlike the shared portfolio, this worker spends its
        # remaining effort on exactly one positively proved topology/order.
        prepare(pair)
        first,last=(1,0)if lane['reverse']else(0,1)
        report.update(independent_lane=lane,one_complete_prefix_and_topology=True)
        found=search(pair,first,last,deadline,face_stratified=True)
        report['elapsed_s']=time.monotonic()-started
        return found,report
    # The Source-prefix path needs the same categorical fairness as retained
    # endpoints. Only singleton SUBSETS of actual native scratch faces are
    # proposed, after the exact prefix is materialized. Common faces need no
    # additional layer jump; keep the original combined portfolio as fallback.
    strata=_face_strata_pairs(work)
    common=[p for p in strata if p[0]['layers']==p[1]['layers']]
    warm=common if common else strata[:6]
    # Expensive immutable native setup belongs to the original local lease,
    # not to the first topology's future search slice. Otherwise setup alone
    # can exhaust that slice and starve every later face. Cache only exact
    # operation-identical prefixes; no geometry is shared across mutations.
    prepared_warm=[]
    for pair in warm:
        if time.monotonic()>=deadline:break
        if prepare(pair)is not None:prepared_warm.append(pair)
    warm=prepared_warm
    warm_work=[(p,first,last)for p in warm for first,last in((0,1),(1,0))]
    warm_deadline=min(deadline,time.monotonic()+min(2.,max(0.,deadline-time.monotonic())*.5))
    report.update(face_strata_count=len(warm),both_launch_directions=True,
        face_strata_share_original_local_lease=True,original_combined_portfolio_preserved=True)
    for index,(pair,first,last)in enumerate(warm_work):
        now=time.monotonic()
        if now>=warm_deadline:break
        lease=now+(warm_deadline-now)/(len(warm_work)-index)
        found=search(pair,first,last,lease,face_stratified=True)
        if found is not None:return found,report
    for index,pair in enumerate(work):
        if time.monotonic()>=deadline:break
        if prepare(pair)is None or time.monotonic()>=deadline:continue
        lease=min(deadline,time.monotonic()+min(2.,max(.05,(deadline-time.monotonic())/min(3,len(work)-index))))
        found=search(pair,0,1,lease,face_stratified=False)
        if found is not None:return found,report
    report['elapsed_s']=time.monotonic()-started
    return None,report


def apply_native_portals(candidate,target,search_s,*,launch_labels=('second_endpoint_first','first_endpoint_first'),lane=None):
    """Walk from actual native lands before choosing any new via seat.

    A preselected dogbone can be locally valid but globally trapped. Reuse
    the existing bounded native-endpoint 3D search instead of spending its
    entire lease behind those fixed seat pairs. This is additive geometry
    only: the typed scope receiver and all shared gates remain mandatory.
    """
    import pcbnew
    import cec_fr as fr
    import cec_force_current as force
    import cec_additive_pair_repair as additive
    import cec_certificate_repair as repair
    from cec_route_proposal_guard import RouteProposalGuard
    from cec_field_search import PlanarSearchGuard
    seconds=_budget(search_s);lane=_lane_request(lane);started=time.monotonic();deadline=started+seconds
    grids=_grid_schedule(target.get('middle_grid_schedule_mm',(.25,)))
    if type(launch_labels)not in(tuple,list)or len(launch_labels)!=2 or any(type(x)is not str or not x for x in launch_labels):
        raise ValueError('two_explicit_native_endpoint_launch_labels_required')
    board=pcbnew.LoadBoard(str(candidate));net=target['target_net'];code=board.GetNetcodeFromNetname(net)
    endpoints=target['route_endpoints']
    if code<=0 or len(endpoints)!=2:raise ValueError('exact_native_portal_pair_required')
    resolver=fr._project_netclass_resolver(str(candidate));spec=resolver(net)or{}
    if any(type(target[k])not in(int,float)or not math.isfinite(target[k])or target[k]<=0
            for k in('width_mm','clearance_mm')):
        raise ValueError('positive_finite_native_portal_geometry_required')
    width=round(target['width_mm']*1e6);clearance=round(target['clearance_mm']*1e6)
    if (width<max(round(float(spec.get('track_width')or 0)*1e6),board.GetDesignSettings().m_TrackMinWidth)
            or clearance<max(int(board.GetDesignSettings().m_MinClearance),round(float(spec.get('clearance')or 0)*1e6))):
        raise ValueError('native_portal_cannot_relax_project_geometry')
    pads={force._uid(p):p for fp in board.GetFootprints()for p in fp.Pads()}
    roots=[pads.get(e['uuid'])for e in endpoints]
    if any(p is None or p.GetNetname()!=net or e['kind']!='pad'
            or tuple(p.GetPosition())!=(round(e['x_mm']*1e6),round(e['y_mm']*1e6))
            for p,e in zip(roots,endpoints)):
        raise ValueError('native_portal_must_start_on_exact_retained_native_lands')
    retained=target.get('retained_same_face_track_ends',False)
    if type(retained) is not bool:
        raise ValueError('explicit_retained_same_face_track_end_policy_required')
    barrel_access=target.get('retained_barrel_face_access',False)
    if type(barrel_access) is not bool or barrel_access and not retained:
        raise ValueError('explicit_rooted_retained_barrel_access_policy_required')
    local_launches=target.get('source_local_pad_rule_launches',False)
    if type(local_launches)is not bool or local_launches and not retained:
        raise ValueError('explicit_source_local_pad_rule_launch_policy_required')
    inset_only=target.get('source_local_contained_intervals_only',False)
    if type(inset_only)is not bool or inset_only and not local_launches:
        raise ValueError('explicit_source_local_contained_interval_policy_required')
    if lane is not None and(not retained or lane['kind']=='source_local_face'and not local_launches):
        raise ValueError('lane_requires_independently_enabled_native_portfolio')
    layers=[set(map(int,p.GetLayerSet().CuStack()))for p in roots]
    all_layers=fr._lastmile_route_layers(board,net_name=net,spec=spec,exclude_front=False)
    bridges=fr._lastmile_route_layers(board,net_name=net,spec=spec,exclude_front=True)
    if not bridges or len(all_layers)<2:
        return dict(closed=0,reason='no_authorized_native_portal_layer_pool',release_authority=False)
    guard=RouteProposalGuard(board,net,board_path=str(candidate),netclass_resolver=resolver,
        deadline=deadline,memoize_exact_positive=True,preflight_s=4.,
        board_hint=target.get('source_board_hint'))
    planar=PlanarSearchGuard(board,net,netclass_resolver=resolver)
    if getattr(planar,'active',True)is False:planar=None
    import cec_native_component_ports as ports
    menus=[[dict(at_nm=list(p.GetPosition()),layers=sorted(ls),native_uuids=[force._uid(p)],
        pad_uuid=force._uid(p))] for p,ls in zip(roots,layers)]
    scheduling=None;turn_guard=None
    if retained:
        menus=[ports.same_face_track_endpoints(board,net,p,route_layers=all_layers,
            toward_nm=tuple(other.GetPosition()),max_sites=16,
            minimum_barrel_web_nm=width if barrel_access else None,
            deadline=min(deadline,time.monotonic()+1.)) for p,other in ((roots[0],roots[1]),(roots[1],roots[0]))]
        if any(not m for m in menus):
            return dict(closed=0,reason='no_actual_authorized_same_face_root',release_authority=False)
        turn_guard=ports.plain_endpoint_turn_guard(board,net)
    pairs=sorted([(a,b) for a in menus[0] for b in menus[1]],
        key=lambda pair:(math.dist(pair[0]['at_nm'],pair[1]['at_nm']),
            tuple(pair[0]['at_nm']),tuple(pair[1]['at_nm']),
            tuple(pair[0]['layers']),tuple(pair[1]['layers'])))
    if retained:
        pairs=ports.diverse_pairs(pairs,point=lambda e:e['at_nm'],layers=lambda e:e['layers'],
            limit=32,breadth=8)
        pairs,scheduling=ports.rank_by_native_egress(board,net,pairs,route_layers=all_layers,
            width_for_layer=lambda l:width,clearance_nm=clearance,
            deadline=min(deadline,time.monotonic()+1.),planar_guard=planar)
    diagnostics={};directions=[];old={force._uid(t)for t in board.GetTracks()}
    before=fr.net_connectivity_component_count(board,code)
    operations=None;foreign_cache={};local_report=None
    if local_launches and(lane is None or lane['kind']=='source_local_face'):
        operations,local_report=_source_local_operations(board,roots,menus,net=net,width=width,
            clearance=clearance,layers=all_layers,bridges=bridges,
            deadline=(deadline if lane is not None else
                min(deadline,time.monotonic()+max(.05,(deadline-time.monotonic())*.5))),
            guard=guard,planar=planar,turn_guard=turn_guard,
            **({'contained_intervals_only':True}if inset_only else{}),
            **({'lane':lane}if lane is not None else{}))
    # Try both exact ends, without any pin or placement authority. Search is
    # directional even though the electrical join is symmetric. A finite
    # reverse refusal retains the historical output-first alternative, all
    # inside ONE unchanged deadline and against the same immutable copper.
    work=[(pair,launch,first,last) for pair in pairs
        for launch,first,last in [(launch_labels[0],1,0),(launch_labels[1],0,1)]]
    proposal_guard=lambda ops:(turn_guard is None or turn_guard(ops))and guard(ops)
    def search(pair,launch,first,last,grid,slice_deadline,*,face_stratified=False):
        nonlocal diagnostics
        diagnostics={}
        found=fr._lastmile_bridge(board,tuple(pair[first]['at_nm']),set(pair[first]['layers']),
            tuple(pair[last]['at_nm']),set(pair[last]['layers']),width,code,bridges,clearance,
            drill=float(spec.get('via_drill')or .3),dia=float(spec.get('via_diameter')or .6),
            leg_ok=lambda a,b,half:fr._edge_leg_clear(board,a,b,half),
            allow_maze=True,foreign_cache=foreign_cache,width_for_layer=lambda layer:width,
            deadline_monotonic=slice_deadline,diagnostics=diagnostics,ops_ok=proposal_guard,planar_guard=planar,
            multilayer_lays=all_layers,_multilayer_only=True,_multilayer_pair_limit=1,
            native_endpoint_seeds=True,middle_native_board_envelope=True,middle_grid_mm=grid,
            obstacle_channel_axes=True,canonical_turns_only=True,middle_max_vias=2,
            max_expanded_states=200000 if lane is not None else 50000,search_wall_cap_s=10.)
        directions.append(dict(launch=launch,native_endpoints=pair,found=found is not None,
            grid_mm=grid,deadline_monotonic=slice_deadline,diagnostics=diagnostics,
            face_stratified=face_stratified,original_global_deadline_monotonic=deadline))
        return found
    if lane is not None and lane['kind']=='retained_face':
        pair=_lane_pair(pairs,lane);first,last=(1,0)if lane['reverse']else(0,1)
        operations=search(pair,launch_labels[0]if lane['reverse']else launch_labels[1],
            first,last,grids[-1],deadline,face_stratified=True)
    strata=_face_strata_pairs(pairs)if retained and lane is None else []
    strata_work=[(pair,launch,first,last)for pair in strata
        for launch,first,last in[(launch_labels[0],1,0),(launch_labels[1],0,1)]]
    # The warm pass shares ONE finite slice of the original lease, leaving
    # the original all-face portfolio and all configured grids as fallback.
    # Every remaining stratum gets an equal share, not an exponential tail.
    strata_deadline=min(deadline,time.monotonic()+min(3.,max(0.,deadline-time.monotonic())*.35))
    if operations is None:
        for index,(pair,launch,first,last)in enumerate(strata_work):
            now=time.monotonic()
            if now>=strata_deadline:break
            lease=now+(strata_deadline-now)/(len(strata_work)-index)
            operations=search(pair,launch,first,last,grids[-1],lease,face_stratified=True)
            if operations is not None:break
    for resolution,grid in enumerate(grids if lane is None else()):
        if operations is not None:break
        if time.monotonic()>=deadline:break
        # Reserve an equal share of REMAINING time for every finer pass.
        # A coarse refusal is not a no-path proof and cannot consume the
        # original fine-grid pass's entire lease. Never reset the outer cap.
        now=time.monotonic()
        resolution_deadline=min(deadline,now+(deadline-now)/(len(grids)-resolution))
        for index,(pair,launch,first,last) in enumerate(work):
            if time.monotonic()>=resolution_deadline:break
            diagnostics={}
            # Both endpoint orders and every retained alias share this
            # resolution's finite slice against exactly the same Source.
            slice_deadline=(min(resolution_deadline,time.monotonic()+min(4.,
                max(.05,(resolution_deadline-time.monotonic())/min(3,len(work)-index))))
                if retained else resolution_deadline)
            operations=search(pair,launch,first,last,grid,slice_deadline)
            directions[-1]['resolution_deadline_monotonic']=resolution_deadline
            if operations is not None:break
    report=dict(closed=0,search_scope='bounded_native_endpoint_portal_geometry',
        diagnostics=diagnostics,directions=directions,proposal_counts=dict(guard.counts),
        proposal_guard=(guard.report()if callable(getattr(guard,'report',None))else None),
        retained_same_face_track_ends=retained,endpoint_scheduling=scheduling,
        retained_barrel_face_access=barrel_access,
        source_local_pad_rule_launches=local_report,
        face_strata_count=len(strata),face_strata_share_original_lease=True,
        original_combined_portfolio_preserved=True,
        middle_grid_schedule_mm=list(grids),
        all_resolutions_share_original_lease_and_exact_native_guards=True,
        elapsed_s=time.monotonic()-started,no_path_proof=False,release_authority=False)
    if lane is not None:report['independent_lane']=lane
    if operations is None or time.monotonic()>=deadline:return report
    # A complete operation list still earns the same transaction guard. The
    # plan-local exact-positive cache does not survive source mutation.
    if not proposal_guard(operations):return report
    report['native_materialization']=repair._lay_ops(board,operations,code,lock=False,
        reuse_existing_collinear=True)
    after=fr.net_connectivity_component_count(board,code)
    if after>=before:return report
    report.update(closed=1,components_before=before,components_after=after)
    additive.save_native_additions(candidate,board,report,old,board_hint=target.get('source_board_hint'))
    report['search_elapsed_s']=report['elapsed_s']
    report['elapsed_s']=time.monotonic()-started
    report['elapsed_includes_final_native_guard_connectivity_and_save']=True
    return report
