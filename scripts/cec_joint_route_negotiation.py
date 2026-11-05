"""Bounded cooperative proposals around a failed joint-route frontier.

One failed candidate may intersect several generated singleton routes. They
are not immutable Source copper. Negotiate that whole small conflict set,
retaining required entries and all old choices. Every action uses the real
typed menu producer and native obstacle geometry; none grants cut, current,
saved-board, or fabrication authority.
"""
import copy
import math


def _ordinary_prefix_anchor(request, *, timeout_s):
    """A literal saved ordinary open, not a worker's negotiability flag.

    This only funds a different proposal order. Re-derive its Source scope,
    original lands, dimensions and actual manufacturer signal/control pin.
    It grants no new route, cut, current, placement or admission authority.
    """
    import pcbnew
    import cec_ordinary_signal_completion as ordinary
    import cec_cell_row_rebuild as row
    import cec_device_power_roles as roles
    import cec_force_current as force
    scoped=request.get('source_ordinary_join_scope',{})
    if (request.get('kind')!='source_boundary'
            or scoped.get('scope')!='source_typed_stationary_ordinary_signal_join'
            or scoped.get('complete') is not True or scoped.get('net')!=request.get('net')
            or request.get('simultaneous_obstacle_and_original_open_connectivity_required') is not True
            or request.get('no_power_pair_measurement_or_current_authority') is not True):
        raise ValueError('fresh_source_ordinary_causal_anchor_required')
    before=pcbnew.LoadBoard(str(scoped['source']))
    if row._source_binding(before)!=request.get('source_ordinary_native_binding'):
        raise ValueError('literal_source_ordinary_causal_anchor_binding_required')
    fresh=ordinary.plan(before,scoped['source'],board_hint=scoped['board_hint'],
        net=request['net'],timeout_s=timeout_s)
    demand=fresh.get('request',{})
    if (fresh!=scoped or demand.get('width_nm')!=request.get('width_nm')
            or demand.get('clearance_nm')!=request.get('clearance_nm')):
        raise ValueError('fresh_source_ordinary_causal_anchor_dimensions_required')
    pads=ordinary._pads(before,demand)
    if {force._uid(p) for p in pads}!={request[e].get('pad_uuid') for e in ('a','b')}:
        raise ValueError('literal_source_ordinary_causal_anchor_lands_required')
    actual=[]
    for pad in pads:
        fp=pad.GetParentFootprint();model=roles.footprint_contract(fp)
        if (model is not None and set(model['pins'])=={p.GetNumber() for p in fp.Pads()}
                and model['pins'].get(pad.GetNumber()) in ('signal_input','signal_output','control')):
            actual.append(dict(pad_uuid=force._uid(pad),owner=fp.GetReference(),pin=pad.GetNumber(),
                role=model['pins'][pad.GetNumber()],manufacturer_source=model['source']))
    witnesses=request.get('source_macro_signal_pin_witnesses')
    if (type(witnesses) is not list or not witnesses
            or any(w not in actual for w in witnesses)):
        raise ValueError('actual_manufacturer_ordinary_causal_anchor_pin_required')
    return True


def _ground_request_closure(requests,key):
    """Keep the source-directed owner/reference-to-cap obligation chain.

    Presence is context, never permission to promote a newly regenerated
    portal choice. The caller holds actual existing packet geometry and only
    adds proposals for the explicitly negotiated target domain.
    """
    result={};root=None
    for _ in range(4):
        if key in result or key not in requests:
            raise ValueError('missing_or_circular_negotiated_ground_portal')
        request=requests[key]
        if request.get('kind')!='ground' or request.get('net')!='GND':
            raise ValueError('typed_negotiated_ground_portal_required')
        result[key]=request;entry=request.get('selected_bypass_entry')
        if not entry:
            if root is not None and key!=root:
                raise ValueError('negotiated_ground_chain_does_not_reach_selected_cap')
            return result
        uid=request.get('a',{}).get('pad_uuid')
        portal=entry.get('portal_obligation');selected_root=entry.get('root_portal_obligation')
        target=requests.get(portal,{})
        if (entry.get('owner_ground_pad_uuid')!=uid or not uid
                or target.get('a',{}).get('pad_uuid')!=entry.get('portal_pad_uuid')
                or selected_root not in requests or root is not None and selected_root!=root
                or requests[selected_root].get('a',{}).get('pad_uuid')!=entry.get('root_portal_pad_uuid')):
            raise ValueError('exact_negotiated_ground_dependency_identity_required')
        root=selected_root;key=portal
    raise ValueError('bounded_negotiated_ground_portal_chain_required')


def propose(board,packet,requests,selection,*,board_path,board_hint,timeout_s=10.,
            max_actions=4,include_power_layer=False,measurement_bridges=False,source_board=None):
    import cec_cell_escape_replan as escape
    from cec_native_items import discard_items
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(max_actions) is not int or not 1<=max_actions<=4
            or type(include_power_layer) is not bool or type(measurement_bridges) is not bool
            or set(packet['domains'])!=set(requests)
            or escape.row._source_binding(board)!=packet['source_native_binding']
            or selection.get('complete') is not False or selection.get('input_unchanged') is not True
            or selection.get('domain_binding')!=escape.joint._binding(packet['domains'])):
        raise ValueError('exact_failed_frontier_and_explicit_cluster_work_bound_required')
    binding=escape.row._source_binding(board)
    material,groups=escape.cell._cell_trial_snapshot(board)
    result=dict(packet,domains=copy.deepcopy(packet['domains']))
    eligible={'source_boundary','ground_boundary','ground','local_supply','measurement','isolated_measurement'}
    singleton={key:values[0] for key,values in packet['domains'].items() if len(values)==1}
    hard={key:q for key,q in singleton.items() if not q['ops']
        or requests[key].get('required_projected_ground_entry') is not None
        or requests[key].get('required_new_ground_dogbone') is not None
        or requests[key]['kind'] not in eligible}
    oracle=escape.conflict_oracle(board)
    hard_values=list(hard.values())
    if any(oracle(a,b) for index,a in enumerate(hard_values) for b in hard_values[index+1:]):
        raise ValueError('required_cluster_obstacles_are_not_compatible')
    tasks=[];causal_tasks=[];cycle_tasks=[];qualified=set();seen_causal=set();seen_cycles=set()
    order={'ground':0,'measurement':1,'isolated_measurement':1,'local_supply':2,
        'ground_boundary':3,'source_boundary':4}
    for failure in selection.get('failure_frontier',[])[:4]:
        key=failure.get('obligation')
        if key not in requests:continue
        assigned=failure.get('assigned',{})
        if (type(assigned) is not dict or key in assigned or any(len([q for q in packet['domains'].get(peer,[])
                if q['id']==choice_id])!=1 for peer,choice_id in assigned.items())):
            raise ValueError('exact_failed_cluster_assigned_choice_required')
        if key not in hard and requests[key]['kind'] in eligible:
            for peer,choice_id in assigned.items():
                if 'source_ordinary_join_scope' not in requests[peer]:continue
                anchor=next(q for q in packet['domains'][peer] if q['id']==choice_id)
                if not anchor['ops'] or not any(oracle(anchor,q) for q in packet['domains'][key]):continue
                if peer not in qualified:
                    _ordinary_prefix_anchor(requests[peer],timeout_s=timeout_s);qualified.add(peer)
                identity=(peer,choice_id,key)
                if identity in seen_causal:continue
                seen_causal.add(identity)
                # Hold the selector's exact causal prefix, not an invented
                # preferred route or a negotiability label. Replan ONLY the
                # failed eligible obligation. This also handles domains with
                # several choices; the old singleton tier cannot see them.
                causal_tasks.append((peer,anchor,[key],assigned,'source_ordinary_failed_prefix'))
        for anchor in sorted(packet['domains'][key],key=lambda q:(q['cost'],q['id']))[:4]:
            if any(oracle(anchor,q) for other,q in hard.items() if other!=key):continue
            blockers=[other for other,q in singleton.items()
                if other!=key and other not in hard and oracle(anchor,q)]
            assigned_ground=[]
            for other,choice_id in assigned.items():
                if (other==key or other in hard or other in blockers
                        or len(packet['domains'][other])<=1
                        or requests[other]['kind']!='ground'
                        or requests[other].get('required_projected_ground_entry') is not None):
                    continue
                chosen=next(q for q in packet['domains'][other] if q['id']==choice_id)
                if not chosen['ops'] or not oracle(anchor,chosen):continue
                # Two independently legal Ground alternatives can both be
                # eliminated by the selector's actual supply prefix. A
                # multi-choice domain is not immutable Source copper. Fund
                # only this exact assigned conflict, with its whole typed
                # owner/reference/cap closure, not arbitrary soft Ground.
                _ground_request_closure(requests,other)
                blockers.append(other);assigned_ground.append(other)
            # A Ground-only retry may be boxed in by two generated supply
            # paths. Its other ORIGINAL choice can clear the failed anchor
            # while conflicting with an earlier assigned generated path.
            # Follow that exact two-edge conflict cycle, rather than freezing
            # the entire failed prefix or funding another identical retry.
            # No new Ground geometry/portal is promoted: this pivot is an
            # already source-guarded packet choice, and only the obstructing
            # generated path gets a fresh typed menu below.
            for pivot in assigned_ground[:4]:
                for alternative in sorted(packet['domains'][pivot],key=lambda q:(q['cost'],q['id']))[:4]:
                    if (len(cycle_tasks)>=16 or alternative['id']==assigned[pivot]
                            or not alternative['ops'] or oracle(alternative,anchor)
                            or any(oracle(alternative,q) for other,q in hard.items() if other!=pivot)):
                        continue
                    targets=[];refused=False
                    for peer,choice_id in assigned.items():
                        if peer==pivot:continue
                        actual=next(q for q in packet['domains'][peer] if q['id']==choice_id)
                        if not oracle(alternative,actual):continue
                        if (peer in hard or requests[peer]['kind'] not in eligible
                                or requests[peer].get('required_projected_ground_entry') is not None):
                            refused=True;break
                        targets.append(peer)
                    if refused or not 1<=len(targets)<=max_actions:continue
                    identity=(key,anchor['id'],pivot,alternative['id'],tuple(sorted(targets)))
                    if identity in seen_cycles:continue
                    seen_cycles.add(identity)
                    context=dict(assigned);context.pop(pivot);context[key]=anchor['id']
                    cycle_tasks.append((pivot,alternative,targets,context,'assigned_ground_alternate_conflict_cycle',
                        dict(original_assigned=dict(assigned),failed_obligation=key,
                            failed_anchor_choice_id=anchor['id'],pivot_original_choice_id=assigned[pivot])))
            if not 1<=len(blockers)<=max_actions:continue
            # The selector's real conflicting prefix is causal evidence.
            # Do not spend every action on an unrelated lexicographically
            # earlier singleton before visiting the reported blocker.
            blockers.sort(key=lambda other:(other not in assigned,order[requests[other]['kind']],
                len(_ground_request_closure(requests,other)) if requests[other]['kind']=='ground' else 0,other))
            tasks.append((key,anchor,blockers,assigned,
                'failed_assigned_ground_cluster' if assigned_ground else 'conflicting_singleton_cluster'))
    # A richer generated domain must not spend the entire fixed action
    # budget retrying the same boxed-in Ground leaf under each anchor while
    # starving its already-derived two-edge cycle. Interleave construction
    # families; preserve each family's causal order and every old choice.
    # This changes scheduling only, not Source scope or the four-action cap.
    families=[causal_tasks,tasks,cycle_tasks]
    tasks=[family[index]for index in range(max(map(len,families),default=0))
        for family in families if index<len(family)]
    actions=[];attempted={}
    for task in tasks:
        anchor_key,anchor,blockers,assigned,basis=task[:5]
        cycle_origin=task[5] if len(task)==6 else None
        if len(actions)>=max_actions:break
        # A finite budget buys distinct failure-frontier work before another
        # anchor repeats the same failed leaf. No new retries/work allowance.
        rank={key:index for index,key in enumerate(blockers)}
        blockers=sorted(blockers,key=lambda key:(attempted.get(key,0),rank[key]))
        fixed={key:q for key,q in singleton.items() if key not in blockers and key!=anchor_key}
        if basis in ('source_ordinary_failed_prefix','failed_assigned_ground_cluster',
                     'assigned_ground_alternate_conflict_cycle'):
            fixed.update({peer:next(q for q in packet['domains'][peer] if q['id']==choice_id)
                for peer,choice_id in assigned.items() if peer not in blockers})
        fixed[anchor_key]=anchor
        values=list(fixed.values())
        if any(oracle(a,b) for index,a in enumerate(values) for b in values[index+1:]):continue
        for key in blockers:
            if len(actions)>=max_actions:break
            # A richer anchor menu is not a reason to spend every slot on
            # the same generated leaf. Try each typed target once in this
            # invocation; preserve unused slots for a newly exposed frontier
            # after joint selection. No extra action or geometry is granted.
            if attempted.get(key,0):continue
            evidence=dict(obligation=key,anchor_obligation=anchor_key,anchor_choice_id=anchor['id'],
                negotiation_basis=basis,
                conflict_cluster=list(blockers),held_obligations=sorted(fixed),added_choices=0,
                failure_frontier_assigned_choices=dict(cycle_origin['original_assigned'] if cycle_origin else assigned))
            if cycle_origin is not None:
                evidence['proposed_cycle_context_choices']=dict(assigned)
                evidence['original_failed_ground_conflict_cycle']=cycle_origin
            work_requests=(_ground_request_closure(requests,key) if requests[key]['kind']=='ground'
                else {key:requests[key]})
            anchor_context=(_ground_request_closure(requests,anchor_key)
                if basis=='assigned_ground_alternate_conflict_cycle' else {})
            held=dict(fixed);missing_portal=None
            for dependency in {**work_requests,**anchor_context}:
                if dependency==key or dependency in held:continue
                compatible=[q for q in result['domains'][dependency]
                    if all(not oracle(q,v) for v in held.values())]
                if not compatible:
                    missing_portal=dependency;break
                held[dependency]=min(compatible,key=lambda q:(q['cost'],q['id']))
            evidence['source_ground_request_closure']=sorted(work_requests) if requests[key]['kind']=='ground' else []
            evidence['held_anchor_ground_request_closure']=sorted(anchor_context)
            evidence['held_dependency_obligations']=sorted(set(held)-set(fixed))
            if missing_portal is not None:
                evidence['producer_attempted']=False
                evidence['refusal']='no_compatible_existing_packet_portal:'+missing_portal
                actions.append(evidence);break
            try:
                for q in held.values():escape._native_ops(board,q['ops'],q['net'])
                attempted[key]=attempted.get(key,0)+1
                evidence['producer_attempted']=True
                context={peer:values[0] for peer,values in result['domains'].items()
                    if peer!=key and len(values)==1}
                context.update({peer:q for peer,q in held.items() if peer!=key})
                evidence['conflict_context_key']=escape._held_conflict_context_key(
                    packet['source_native_binding'],key,context)
                fresh=escape.menus(board,work_requests,board_path=board_path,board_hint=board_hint,
                    timeout_s=timeout_s,max_choices=48,include_power_layer=include_power_layer,
                    measurement_bridges=measurement_bridges,source_board=source_board,whole_requests=requests)
                evidence['diagnostics']=fresh['diagnostics'][key]
                compatible=[q for q in fresh['domains'][key] if all(not oracle(q,v) for v in held.values())]
                used={q['id'] for q in result['domains'][key]};ordinal=0
                for q in compatible:
                    if len(result['domains'][key])>=96:break
                    if any(q['ops']==old['ops'] and q.get('requires_ground_entry')==old.get('requires_ground_entry')
                            for old in result['domains'][key]):continue
                    while 'cluster_'+str(ordinal) in used:ordinal+=1
                    q=dict(q,id='cluster_'+str(ordinal));used.add(q['id'])
                    result['domains'][key].append(q);evidence['added_choices']+=1
                evidence['compatible_choices']=len(compatible)
                chosen=min(compatible,key=lambda q:(q['cost'],q['id'])) if compatible else None
            finally:
                discard_items(board,[t for t in board.GetTracks() if escape.force._uid(t) not in material])
                if (escape.cell._cell_trial_snapshot(board)!=(material,groups)
                        or escape.row._source_binding(board)!=binding):
                    raise ValueError('joint_cluster_proposal_changed_private_source')
            actions.append(evidence)
            if chosen is None:break
            fixed[key]=chosen
    result['cooperative_conflict_cluster']=dict(actions=actions,eligible_anchor_trials=len(tasks),
        eligible_ground_conflict_cycles=len(cycle_tasks),maximum_ground_conflict_cycles=16,
        maximum_actions=max_actions,per_action_max_seconds=timeout_s,
        mandatory_obligations=sorted(hard),source_unchanged=True,
        all_original_choices_and_obligations_retained=True,
        finite_proposals_only_not_no_path_proof=True,routing_admitted=False,release_authority=False)
    return result
