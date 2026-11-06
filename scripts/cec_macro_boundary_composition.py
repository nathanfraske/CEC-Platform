"""Compose two independently owned ordinary cuts at their literal old join.

A base Source cell stub may end at a neighbour which a Source-owned ordinary
barrel move also retires. That old bend is not a retained target. Include the
already-retired stub in the same native cut component so its real pad and
every surviving barrel/track/land remain mandatory reconstruction ports.
No extra Source edge, Ground/power/pair role or current rating is acquired.
"""
import copy,json,time
import pcbnew
import cec_cell_row_rebuild as row
import cec_device_power_roles as roles
import cec_force_current as force
import cec_ordinary_route_receiving as ordinary


def _positive_signal_terminal(parent, proposal, pad, deadline, cache):
    """Reprove an IC signal or a selected programming passive's NODE only."""
    fp = pad.GetParentFootprint()
    contract = roles.footprint_contract(fp)
    if (contract and contract == proposal.get('device_contracts', {}).get(fp.GetReference())
            and set(p.GetNumber() for p in fp.Pads()) == set(contract['pins'])
            and contract['pins'].get(pad.GetNumber()) in
                ('signal_input','signal_output','signal_io','address','enable','reset','mode')):
        return True
    selected = proposal.get('selected_programming_resistors', {})
    if not selected:
        return False
    if 'programming' not in cache:
        import cec_programming_resistor_placement as programming
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('source_boundary_composition_deadline')
        fresh = programming.plan(parent, proposal['poses'], board_hint=proposal['board_hint'],
            timeout_s=min(10., remaining),
            reference_group_uuids=proposal.get('reference_group_uuids', ()),
            **programming.replay_options(proposal))
        if fresh != selected:
            raise ValueError('source_boundary_programming_owner_changed')
        cache['programming'] = fresh
    for item in cache['programming'].values():
        nodes = {item['signal_pad_uuid']}
        divider = item.get('source_monitor_divider', {})
        if divider.get('upper_motion') is True:
            nodes.add(divider['upper_node_pad_uuid'])
        if force._uid(pad) in nodes and pad.GetNetname() == item['net']:
            return True
    return False


def _compose_base_pairs(parent, source, proposal, requests, extras, deadline, cache):
    """Replace two already-owned stubs' anonymous join by their real ports.

    The native cut-component receiver below inventories ALL surviving copper
    contacts. This does not discard a bend that still meets a pad, via, zone,
    or third trace: that contact remains a mandatory component port. No new
    source cut, width, lock permission, or current authority is introduced.
    """
    tracks = {force._uid(t): t for t in parent.GetTracks()}
    pads = {force._uid(p): p for f in parent.GetFootprints() for p in f.Pads()}
    base = set(proposal['retired_track_uuids'])
    extra_ids = {r['change']['uuid'] for r in extras}
    groups = {}
    for key, request in requests.items():
        uid = key[len('boundary:'):] if key.startswith('boundary:') else ''
        if uid not in base or uid in extra_ids or request.get('kind') != 'source_boundary':
            continue
        for side, other in (('a', 'b'), ('b', 'a')):
            node, end = request.get(side, {}), request.get(other, {})
            if (set(node) != {'at_nm', 'layers'} or not end.get('pad_uuid')
                    or type(node['at_nm']) not in (list, tuple) or len(node['at_nm']) != 2
                    or any(type(n) is not int for n in node['at_nm'])
                    or type(node['layers']) not in (list, tuple) or len(node['layers']) != 1):
                continue
            group = (request.get('net'), tuple(node['layers']), tuple(node['at_nm']))
            groups.setdefault(group, []).append((key, uid, request, end))
    remaining = copy.deepcopy(requests); result = copy.deepcopy(extras); composed = []
    eligible = None
    for (net, layers, point), entries in groups.items():
        if len(entries) != 2 or len({e[1] for e in entries}) != 2:
            continue
        if time.monotonic() >= deadline:
            raise ValueError('source_boundary_composition_deadline')
        if eligible is None:
            eligible = ordinary.eligible_nets(parent, source, proposal['board_hint'])
        if net == 'GND' or net not in eligible:
            continue
        face = layers[0]
        for key, uid, request, end in entries:
            edge, pad = tracks.get(uid), pads.get(end['pad_uuid'])
            if (edge is None or pad is None or edge.GetClass() != 'PCB_TRACK'
                    or edge.GetNetname() != net or pad.GetNetname() != net
                    or edge.GetLayer() != face or end.get('layers') != list(layers)
                    or not pad.IsOnLayer(face) or pad.HasHole()
                    or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                    or pad.GetParentFootprint().GetReference() not in proposal['poses']
                    or edge.GetParentGroup() is not None or edge.HasSolderMask()
                    or not 0 < edge.GetWidth() <= 350000
                    or not 0 < edge.GetLength() <= 8000000
                    # The source producer uses the literal old width. A wider
                    # demand cannot be replaced by a narrower native component.
                    or type(request.get('width_nm')) is not int
                    or request['width_nm'] != edge.GetWidth()):
                raise ValueError('positive_existing_ordinary_base_pair_required')
            ends = (tuple(edge.GetStart()), tuple(edge.GetEnd()))
            if point not in ends or ends[0] == ends[1]:
                raise ValueError('literal_owned_base_pair_endpoint_required')
            other = ends[1] if point == ends[0] else ends[0]
            if not pad.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*other), 0):
                raise ValueError('actual_base_pair_source_pad_contact_required')
            if not _positive_signal_terminal(parent, proposal, pad, deadline, cache):
                raise ValueError('source_boundary_positive_manufacturer_signal_terminal_required')
        # Both original demands are replaced, never silently dropped. The
        # existing cut-component builder projects source contacts to the
        # actual moved pads and retains any third contact at this old join.
        for key, uid, request, end in entries:
            edge = tracks[uid]
            proof = dict(source_base_boundary_uuid=uid,
                original_base_pair_uuids=sorted(e[1] for e in entries),
                original_internal_join_nm=list(point), original_pad_uuid=end['pad_uuid'],
                base_edge_was_already_positively_retired=True,
                no_additional_source_edge_retired=True,
                actual_native_component_ports_still_independently_required=True)
            result.append(dict(change=dict(uuid=uid, net=net,
                source_nm=[list(edge.GetStart()), list(edge.GetEnd())]),
                authority=dict(kind='positive_source_ordinary', native_source_uuid=uid),
                source_base_boundary_composition=proof))
            composed.append(dict(original_request_id=key, original_request=copy.deepcopy(request),
                required_replacement_request_id='macro_boundary:'+uid,
                source_base_boundary_composition=True, source_base_boundary_uuid=uid,
                source_composition_proof=proof,
                exact_source_edge_endpoint_obligation_composed_not_omitted=True))
            del remaining[key]
    return remaining, result, composed


def compose_rated_forks(parent,source,proposal,extras,retired,*,deadline):
    """Compose an already-owned full-current fork and its already-cut port.

    No edge is discovered or acquired here. Each original fork, independent
    extra and their bounded union must freshly retain the SAME full-current
    contract. Native cut-component receiving then restores every surviving
    contact instead of inventing an anchor on a now-retired internal bend.
    Source lock permissions belong to their original independent owners;
    this neither globally unlocks copper nor expands fork lock permissions.
    """
    import cec_cell_shared_fork as forks
    import cec_full_current_planar_reflow as full
    if (proposal.get('scope')!='source_typed_complete_cell_escape_proposal'
            or proposal.get('source_native_binding')!=row._source_binding(parent)
            or type(extras)is not list or len(extras)>64
            or type(retired)not in(set,frozenset)or len(retired)>128
            or not time.monotonic()<deadline<=time.monotonic()+10.):
        raise ValueError('bounded_exact_rated_fork_composition_required')
    def tick():
        if time.monotonic()>=deadline:raise ValueError('rated_fork_composition_deadline')
    def stable(value):return json.dumps(value,sort_keys=True,allow_nan=False)
    def current(plan):
        return stable([plan[k]for k in ('current_domain_kind','domain','contract',
            'net','layer_id','width_nm','full_current_floor_nm')])
    def typed(ids,*,max_source_cut_mm=32.):
        tick()
        return full.plan(parent,source,board_hint=proposal['board_hint'],
            retired_track_uuids=sorted(ids),timeout_s=min(10.,deadline-time.monotonic()),
            max_source_cut_mm=max_source_cut_mm)
    tracks={force._uid(t):t for t in parent.GetTracks()}
    by_id={q['change']['uuid']:q for q in extras}
    if len(by_id)!=len(extras)or not by_id.keys()<=retired:
        raise ValueError('unique_already_retired_rated_fork_extras_required')
    result=copy.deepcopy(extras);records=[];used=set()
    for index,fork in enumerate(proposal.get('source_owned_shared_supply_forks',[])):
        tick();base=set(fork['track_uuids'])
        incident={p['native_uuid']for p in fork['retained_native_ports']if p['native_uuid']in by_id}
        if not incident:continue
        if (fork.get('kind')!='rated_supply'or not base or not base<=retired
                or base&by_id.keys()or not base|incident<=tracks.keys()):
            raise ValueError('disjoint_existing_full_current_fork_owners_required')
        work=fork['source_work_bounds']
        fresh=forks.plan(parent,fork['requested_root_pad_uuids'],moving_refs=fork['moving_refs'],
            kind='rated_supply',board_hint=proposal['board_hint'],
            allow_owned_locked=fork['allow_owned_locked'],
            max_tracks=work['max_tracks'],max_length_mm=work['max_length_mm'],
            allow_full_current_supply_width=fork.get('allow_full_current_supply_width',False),
            timeout_s=min(10.,deadline-time.monotonic()))
        if stable(fresh)!=stable(fork):raise ValueError('rated_fork_original_source_owner_changed')
        baseline=typed(base,max_source_cut_mm=work['max_length_mm'])
        if stable(baseline)!=stable(fork['full_current_source_plan']):
            raise ValueError('rated_fork_original_full_current_plan_changed')
        graph=pcbnew.CONNECTIVITY_DATA()
        for uid,extra in by_id.items():
            tick();edge=tracks.get(uid)
            if (edge is not None and edge.GetClass()=='PCB_TRACK'
                    and edge.GetNetname()==fork['net']and int(edge.GetLayer())==fork['layer']
                    and not graph.Add(edge)):
                raise ValueError('native_rated_extra_component_inventory_refused')
        selected=set(incident)
        for uid in sorted(incident):
            if (tracks[uid].GetClass()!='PCB_TRACK'or tracks[uid].GetNetname()!=fork['net']
                    or int(tracks[uid].GetLayer())!=fork['layer']):
                raise ValueError('one_literal_rated_fork_extra_face_required')
            selected|={force._uid(t)for t in graph.GetConnectedItems(tracks[uid])}&by_id.keys()
        union=base|selected
        if union&used or not 1<=len(union)<=8:
            raise ValueError('disjoint_bounded_eight_edge_rated_fork_union_required')
        for uid in sorted(selected):
            tick();extra=by_id[uid];authority=extra.get('authority',{});edge=tracks[uid]
            points=extra['change'].get('source_nm')
            fresh=typed({uid})
            if (authority.get('kind')!='unchanged_full_current_source_edge'
                    or authority.get('native_source_uuid')!=uid
                    or stable(authority.get('source_plan'))!=stable(fresh)
                    or current(fresh)!=current(baseline)
                    or extra['change'].get('net')!=edge.GetNetname()
                    or type(points)not in(list,tuple)or len(points)!=2
                    or any(type(p)not in(list,tuple)or len(p)!=2
                        or any(type(n)is not int for n in p)for p in points)
                    or list(map(list,points))!=[list(edge.GetStart()),list(edge.GetEnd())]):
                raise ValueError('same_fresh_full_current_extra_owner_required')
        combined=typed(union)
        if current(combined)!=current(baseline):
            raise ValueError('rated_fork_union_current_or_source_width_changed')
        for port in fork['retained_native_ports']:
            uid=port['native_uuid']
            if uid in retired-union:raise ValueError('rated_fork_retained_port_cut_outside_union')
            if uid not in selected:continue
            at=pcbnew.VECTOR2I(*port['at_nm']);face=port['layer_id']
            if (face!=fork['layer']or not tracks[uid].IsOnLayer(face)
                    or not tracks[uid].GetEffectiveShape(face).Collide(at,0)
                    or not any(tracks[u].GetEffectiveShape(face).Collide(at,0)for u in base)):
                raise ValueError('literal_both_sides_rated_fork_extra_contact_required')
        for uid in sorted(base):
            edge=tracks[uid]
            result.append(dict(change=dict(uuid=uid,net=str(edge.GetNetname()),
                source_nm=[list(edge.GetStart()),list(edge.GetEnd())]),
                authority=dict(kind='unchanged_full_current_source_edge',native_source_uuid=uid,
                    source_plan=typed({uid}))))
        records.append(dict(original_fork_index=index,original_fork=copy.deepcopy(fork),
            original_extra_uuids=sorted(selected),composed_union_uuids=sorted(union),
            fresh_union_source_plan=combined,consumed_internal_port_uuids=sorted(incident),
            source_lock_manifest=[dict(uuid=u,locked=bool(tracks[u].IsLocked()),
                owner='original_rated_fork'if u in base else'independent_full_current_extra')for u in sorted(union)],
            retirement_set_unchanged=True,no_new_cut_or_current_authority=True,
            every_surviving_native_contact_still_requires_reconstruction=True))
        used|=union
    if len(result)>64:raise ValueError('bounded_composed_rated_cut_component_scope_required')
    if set(q['change']['uuid']for q in result)|set(proposal['retired_track_uuids'])!=by_id.keys()|set(proposal['retired_track_uuids']):
        raise ValueError('rated_fork_composition_cannot_acquire_additional_copper')
    tick()
    return result,records


def compose_rated_leaves(parent,source,proposal,requests,extras,*,deadline):
    """Replace an already-owned rated leaf's retired bend by real ports.

    Every original leaf and selected peer is freshly proved; no missing
    request, new cut, lower rating or inferred lock consent is introduced.
    The later native component inventory restores all surviving contacts.
    """
    import cec_measurement_leaf as leaves
    import cec_full_current_planar_reflow as full
    if (proposal.get('scope')!='source_typed_complete_cell_escape_proposal'
            or proposal.get('source_native_binding')!=row._source_binding(parent)
            or type(requests)is not dict or len(requests)>64
            or type(extras)is not list or len(extras)>64
            or not time.monotonic()<deadline<=time.monotonic()+10.):
        raise ValueError('bounded_exact_rated_leaf_composition_required')
    def left():
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ValueError('rated_leaf_composition_deadline')
        return min(10.,remaining)
    def stable(value):
        # Native layer maps use integer keys; prepared receipts use JSON
        # string keys. Normalize before sorting (10 sorts before 2 only in
        # the latter). Preserve every key/value, not a rating subset.
        wire=json.loads(json.dumps(value,allow_nan=False))
        return json.dumps(wire,sort_keys=True,allow_nan=False)
    def current(plan):return stable([plan[k]for k in ('current_domain_kind','domain','contract',
        'net','layer_id','width_nm','full_current_floor_nm')])
    tracks={force._uid(t):t for t in parent.GetTracks()}
    by_id={r['change']['uuid']:r for r in extras}
    base=set(proposal['retired_track_uuids'])
    if len(by_id)!=len(extras)or not by_id.keys()<=tracks.keys():
        raise ValueError('unique_literal_rated_leaf_extra_owners_required')
    remaining=copy.deepcopy(requests);result=copy.deepcopy(extras);records=[]
    for leaf in proposal.get('rated_supply_leaves',[]):
        left();key='rated_supply:'+leaf['pad_uuid'];request=remaining.get(key)
        if request is None:continue
        targets=set(request.get('b',{}).get('native_uuids',[]));incident=targets&by_id.keys()
        if not incident:continue
        own=set(leaf['track_uuids'])
        if (not own or not own<=base or own&by_id.keys()or not own<=tracks.keys()
                or request.get('kind')!='source_boundary' or request.get('net')!=leaf['net']
                or request.get('a',{}).get('pad_uuid')!=leaf['pad_uuid']
                or request.get('width_nm')!=leaf['width_nm']
                or stable(request.get('unchanged_full_rail_current_contract'))
                    !=stable(leaf['unchanged_full_rail_current_contract'])):
            raise ValueError('exact_existing_rated_leaf_request_and_cut_required')
        if leaf['scope']=='source_typed_full_load_rated_supply_leaf':
            fresh=leaves.plan_rated_supply(parent,leaf['pad_uuid'],
                board_hint=proposal['board_hint'],timeout_s=left())
        elif leaf['scope']=='source_typed_full_load_rated_bypass_supply_leaf':
            moving=(leaf['source_selected_bypass']['owner']
                if 'source_resolved_moving_owner_supply_leaves'in leaf else None)
            fresh=leaves.plan_rated_bypass_supply(parent,leaf['pad_uuid'],
                board_hint=proposal['board_hint'],timeout_s=left(),moving_owner_ref=moving)
        else:raise ValueError('positive_original_rated_leaf_kind_required')
        if stable(fresh)!=stable(leaf):raise ValueError('rated_leaf_original_Source_owner_changed')
        baseline=full.plan(parent,source,board_hint=proposal['board_hint'],
            retired_track_uuids=sorted(own),timeout_s=left())
        graph=pcbnew.CONNECTIVITY_DATA()
        for uid in by_id:
            left();edge=tracks[uid]
            if (edge.GetClass()=='PCB_TRACK'and edge.GetNetname()==leaf['net']
                    and int(edge.GetLayer())==leaf['layer']and not graph.Add(edge)):
                raise ValueError('native_rated_leaf_extra_graph_refused')
        selected=set(incident)
        for uid in incident:
            selected|={force._uid(t)for t in graph.GetConnectedItems(tracks[uid])}&by_id.keys()
        if len(own|selected)>8:raise ValueError('bounded_eight_edge_rated_leaf_union_required')
        peer_spans=[]
        for uid in sorted(selected):
            left();extra=by_id[uid];authority=extra.get('authority',{});edge=tracks[uid]
            original_plan=authority.get('source_plan',{})
            peer=full.plan(parent,source,board_hint=proposal['board_hint'],
                retired_track_uuids=[uid],timeout_s=left(),
                max_source_track_mm=original_plan.get('max_source_track_mm',8.),
                max_source_cut_mm=original_plan.get('max_source_cut_mm',32.))
            if (authority.get('kind')!='unchanged_full_current_source_edge'
                    or authority.get('native_source_uuid')!=uid
                    or stable(authority.get('source_plan'))!=stable(peer)
                    or current(peer)!=current(baseline)
                    or extra['change'].get('net')!=edge.GetNetname()
                    or stable(extra['change'].get('source_nm'))
                        !=stable([list(edge.GetStart()),list(edge.GetEnd())])):
                raise ValueError('same_fresh_full_current_rated_leaf_peer_required')
            peer_spans.append(peer['max_source_track_mm'])
        combined=full.plan(parent,source,board_hint=proposal['board_hint'],
            retired_track_uuids=sorted(own|selected),timeout_s=left(),
            max_source_track_mm=max([baseline['max_source_track_mm'],*peer_spans]))
        if current(combined)!=current(baseline):raise ValueError('rated_leaf_union_current_changed')
        at=request['b'].get('at_nm');face=leaf['layer']
        if (request['b'].get('layers')!=[face]or at!=leaf['points_nm'][-1]
                or not incident<=set(leaf['boundary_uuids'])
                or not all(tracks[u].IsOnLayer(face)
                    and tracks[u].GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*at),0)for u in incident)):
            raise ValueError('literal_rated_leaf_peer_join_required')
        for uid in sorted(own):
            edge=tracks[uid]
            result.append(dict(change=dict(uuid=uid,net=str(edge.GetNetname()),
                source_nm=[list(edge.GetStart()),list(edge.GetEnd())]),
                authority=dict(kind='unchanged_full_current_source_edge',native_source_uuid=uid,
                    source_plan=full.plan(parent,source,board_hint=proposal['board_hint'],
                        retired_track_uuids=[uid],timeout_s=left()))))
        records.append(dict(original_request_id=key,original_request=copy.deepcopy(request),
            original_rated_leaf=copy.deepcopy(leaf),fresh_union_source_plan=combined,
            required_replacement_request_id='macro_boundary:'+min(own),
            exact_source_edge_endpoint_obligation_composed_not_omitted=True,
            retirement_set_unchanged=True,no_new_cut_or_current_authority=True))
        del remaining[key]
    left()
    if (len(result)>64 or len({r['change']['uuid']for r in result})!=len(result)
            or {r['change']['uuid']for r in result}|base!=by_id.keys()|base
            or proposal['source_native_binding']!=row._source_binding(parent)):
        raise ValueError('rated_leaf_composition_changed_Source_or_retirement_scope')
    return remaining,result,records


def compose(parent,source,proposal,requests,extras,*,deadline):
    if (proposal.get('scope')!='source_typed_complete_cell_escape_proposal'
            or proposal.get('source_native_binding')!=row._source_binding(parent)
            or type(requests) is not dict or len(requests)>64
            or type(extras) is not list or len(extras)>64
            or not time.monotonic()<deadline<=time.monotonic()+10.):
        raise ValueError('bounded_exact_source_boundary_composition_required')
    tracks={force._uid(t):t for t in parent.GetTracks()}
    pads={force._uid(p):p for f in parent.GetFootprints() for p in f.Pads()}
    base=set(proposal['retired_track_uuids'])
    cache={}
    requests,extras,base_pairs=_compose_base_pairs(parent,source,proposal,requests,extras,deadline,cache)
    by_id={r['change']['uuid']:r for r in extras}
    if len(by_id)!=len(extras):raise ValueError('unique_original_extra_boundary_scope_required')
    eligible=None;remaining={};composed=base_pairs;result=copy.deepcopy(extras)
    for key,request in requests.items():
        if time.monotonic()>=deadline:raise ValueError('source_boundary_composition_deadline')
        targets=request.get('b',{}).get('native_uuids',[])
        uid=key[len('boundary:'):] if key.startswith('boundary:') else ''
        if (uid not in base or uid in by_id or len(targets)!=1 or targets[0] not in by_id
                or request.get('kind')!='source_boundary' or request.get('net')=='GND'):
            remaining[key]=request;continue
        stub=tracks.get(uid);peer=tracks.get(targets[0]);pad=pads.get(request.get('a',{}).get('pad_uuid'))
        authority=by_id[targets[0]].get('authority',{})
        if authority!={'kind':'positive_source_ordinary','native_source_uuid':targets[0]}:
            # Other existing reconstruction contracts stay independent.
            remaining[key]=request;continue
        if eligible is None:eligible=ordinary.eligible_nets(parent,source,proposal['board_hint'])
        if (stub is None or peer is None or pad is None or stub.GetClass()!='PCB_TRACK'
                or peer.GetClass()!='PCB_TRACK' or stub.GetNetname() not in eligible
                or stub.GetNetname()!=peer.GetNetname() or stub.GetNetname()!=pad.GetNetname()
                or stub.GetNetname()!=request['net'] or stub.GetLayer()!=peer.GetLayer()
                or stub.GetParentGroup() is not None or stub.HasSolderMask()
                or not 0<stub.GetWidth()<=350000 or not 0<stub.GetLength()<=8000000
                or type(request.get('width_nm')) is not int
                or request['width_nm']!=stub.GetWidth() or pad.HasHole()
                or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                or pad.GetParentFootprint().GetReference() not in proposal['poses']):
            raise ValueError('positive_existing_ordinary_base_boundary_required')
        if not _positive_signal_terminal(parent,proposal,pad,deadline,cache):
            raise ValueError('source_boundary_positive_manufacturer_signal_terminal_required')
        face=int(stub.GetLayer());at=request['b'].get('at_nm')
        if (type(at) not in (list,tuple) or len(at)!=2 or any(type(n) is not int for n in at)
                or request['b'].get('layers')!=[face] or request['a'].get('layers')!=[face]
                or not pad.IsOnLayer(face)):
            raise ValueError('one_literal_original_boundary_face_required')
        endpoint=tuple(at);ends=(tuple(stub.GetStart()),tuple(stub.GetEnd()))
        if (endpoint not in ends or endpoint not in (tuple(peer.GetStart()),tuple(peer.GetEnd()))
                or ends[0]==ends[1]):raise ValueError('exact_original_cut_edge_endpoint_join_required')
        other=ends[1] if ends[0]==endpoint else ends[0]
        if (not pad.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*other),0)
                or not stub.GetEffectiveShape(face).Collide(peer.GetEffectiveShape(face),0)):
            raise ValueError('actual_original_pad_to_cut_component_contact_required')
        proof=dict(source_base_boundary_uuid=uid,original_neighbour_uuid=targets[0],
            original_internal_join_nm=list(endpoint),original_pad_uuid=force._uid(pad),
            base_edge_was_already_positively_retired=True,no_additional_source_edge_retired=True,
            actual_native_component_ports_still_independently_required=True)
        result.append(dict(change=dict(uuid=uid,net=str(stub.GetNetname()),
            source_nm=[list(stub.GetStart()),list(stub.GetEnd())]),
            authority=dict(kind='positive_source_ordinary',native_source_uuid=uid),
            source_base_boundary_composition=proof))
        composed.append(dict(original_request_id=key,original_request=copy.deepcopy(request),
            required_replacement_request_id='macro_boundary:'+uid,source_pad_uuid=force._uid(pad),
            source_base_boundary_composition=True,source_base_boundary_uuid=uid,
            source_composition_proof=proof,
            exact_source_edge_endpoint_obligation_composed_not_omitted=True))
    if len(result)>64:raise ValueError('bounded_composed_native_cut_component_scope_required')
    return remaining,result,composed
