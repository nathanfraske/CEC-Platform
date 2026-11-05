"""Source-typed exact-port fan-out of an already isolated quiet sense tree.

Source selects two manufacturer measurement inputs resolving to the SAME
two-land shunt terminal. The existing front-only quiet tree and its actual
shunt exit remain immutable. Only a new bounded front trace chain ending in
the other input's physical land or an exact two-edge Source quiet junction
is permitted. This is not whole-net routing,
force capacity, a new Kelvin pickup, retirement, placement or release authority.
Independent complete native/current/field/return/Kelvin receiving remains due.
"""
import math
from pathlib import Path
import time

import pcbnew
import cec_force_current as force
import cec_fr as fr
import cec_measurement_current_branch as branch
import cec_isolated_measurement_completion as isolated
import cec_measurement_terminal_route as terminal


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('source_quiet_fanout_phase_deadline')


def _native_pads(board):
    rows = [p for f in board.GetFootprints() for p in f.Pads()]
    result = {force._uid(p): p for p in rows}
    if len(rows) != len(result) or len(rows) > 16384:
        raise ValueError('bounded_unique_fanout_native_land_inventory_required')
    return result


def _quiet_tree(board, root_uid, target_uid, domain, *, deadline):
    """Re-use current-only classification as one necessary geometric proof.

    Its numeric/current flags confer no routing authority. Re-derive unique
    exact shunt lineage for EVERY land and independently keep front-only
    policy and native inward departures. No arbitrary same-net boundary.
    """
    import cec_sense_topology as sense
    import cec_measurement_route_policy as policy
    from cec_kelvin_departure import audit_pad_departures
    pads = _native_pads(board)
    root, target = pads[root_uid], pads[target_uid]
    attempts = []
    for shared in (False, True):
        try:
            tree = branch._package_input_tree(board, root_uid, domain,
                deadline=deadline, allow_layer_branches=False,
                allow_resolved_multiowner_inputs=shared)
            break
        except ValueError as exc:
            attempts.append(str(exc))
    else:
        raise ValueError('no_exact_source_quiet_input_tree:' + str(attempts))
    if tree['via_uuids'] or target_uid not in tree['boundary_uuids']:
        raise ValueError('front_only_quiet_tree_at_exact_shunt_land_required')
    lineage = sense.board_evidence(board, anchor_refs=domain['authority_refs'])
    selected = [];primary = [];auxiliary = []
    for uid in tree['leaf_pad_uuids']:
        _tick(deadline)
        p = pads[uid]
        rows = [q for q in lineage['details'] if q.get('ok') is True
            and q['ref'] == p.GetParentFootprint().GetReference()]
        segments = [s for q in rows for s in sense.placement_segments(q)
            if s['net'] == root.GetNetname()
            and s['start'] == dict(ref=p.GetParentFootprint().GetReference(), pad=p.GetNumber())
            and s['end'] == dict(ref=target.GetParentFootprint().GetReference(), pad=target.GetNumber())
            and q['selected']['kind'] == 'direct']
        if len(rows) == 1 and len(segments) == 1:
            rule = policy.input_contract(board, uid)
            if (rule['kind'] != 'shunt_kelvin_front_no_via'
                or rule['permitted_layers'] != [int(pcbnew.F_Cu)]
                or rule['allow_layer_bridge'] is not False):
                raise ValueError('every_quiet_tree_input_must_keep_front_no_via_policy')
            primary.append((p,rows[0],segments[0]))
        else:
            auxiliary.append(p)
        selected.append(p)
    import cec_measurement_auxiliary_cut as aux
    auxiliary_proofs=[]
    for p in auxiliary:
        proofs=[]
        for paired,_row,_segment in primary:
            if force._uid(p.GetParentFootprint()) != force._uid(paired.GetParentFootprint()):
                continue
            try:
                proof=aux.plan(board,force._uid(paired),timeout_s=max(.001,deadline-time.monotonic()))
                if proof['boundary_uuids']==[force._uid(p)]:proofs.append(proof)
            except ValueError:
                continue
        if len(proofs)!=1 or not set(proofs[0]['track_uuids'])<=set(tree['track_uuids']):
            raise ValueError('quiet_auxiliary_land_requires_exact_declared_literal_input_strap')
        auxiliary_proofs.extend(proofs)
    if not primary:
        raise ValueError('actual_paired_input_required_for_quiet_tree')
    tracks = {force._uid(t): t for t in board.GetTracks()}
    native = [tracks[u] for u in tree['track_uuids']]
    demand = dict(source_topology=primary[0][1]['selected'],
        source_segment=primary[0][2])
    opposite = terminal._direct_pickup(demand, target)
    import cec_constraints as constraints
    inward = audit_pad_departures(target, opposite.GetPosition(), native,
        inner_min_mm=constraints._param('kelvin-sense-from-inner-pad', 'inner_min_mm', .1),
        target_pads=selected, connectivity_pads=selected)
    if inward['ok'] is not True:
        raise ValueError('retained_quiet_tree_must_have_actual_inward_shunt_departure')
    tree.update(exact_shunt_pad_uuid=target_uid, inward_departure=inward,
        literal_auxiliary_input_straps=auxiliary_proofs,
        exact_direct_lineage_rederived_for_all_inputs=True,
        routing_authority=False, kelvin_qualified=False)
    return tree


def _ports(board,tree,peer):
    """Only actual input lands or degree-two endpoint junctions, never interiors."""
    pads=_native_pads(board)
    material={force._uid(t):t for t in board.GetTracks()}
    ports=[dict(key='pad:'+force._uid(peer),at_nm=list(peer.GetPosition()),
        kind='actual_quiet_input_land',item_uuids=[force._uid(peer)])]
    ends={}
    for uid in tree['track_uuids']:
        item=material[uid]
        for p in (tuple(item.GetStart()),tuple(item.GetEnd())):
            ends.setdefault(p,[]).append(uid)
    for point,ids in ends.items():
        if (len(ids)!=2 or any(p.IsOnLayer(pcbnew.F_Cu)
                and p.GetEffectiveShape(pcbnew.F_Cu).Collide(pcbnew.VECTOR2I(*point),0)
                for p in pads.values())):
            continue
        ports.append(dict(key='junction:'+'+'.join(sorted(ids)),at_nm=list(point),
            kind='exact_two_source_quiet_track_endpoints',item_uuids=sorted(ids)))
    return ports


def plan(board, source, *, board_hint, pad_uuid, peer_pad_uuid=None, port_key=None, timeout_s=10.):
    import cec_current_topology as topology
    import cec_sense_topology as sense
    import cec_cell_row_rebuild as binding
    started = time.monotonic()
    deadline = started + isolated._budget(timeout_s, 10.)
    source = Path(source).resolve(strict=True)
    before = binding._source_binding(board)
    fresh = isolated.plan(board, source, board_hint=board_hint, pad_uuid=pad_uuid,
        timeout_s=max(.001, deadline-time.monotonic()))
    result = dict(schema=1, scope='source_exact_quiet_input_land_fanout',
        complete=False, source=str(source), source_sha256=force._hash(source),
        board_hint=board_hint, pad_uuid=pad_uuid, source_request=fresh,
        routing_admitted=False, current_authority=False, kelvin_qualified=False,
        retirement_authority=False, placement_authority=False, release_authority=False,
        no_path_proof=False)
    if not fresh['complete']:
        result['reason'] = 'actual_stranded_direct_measurement_input_required'
        return result
    demand = fresh['request']['demand']
    pads = _native_pads(board)
    target = pads[demand['target_uuid']]
    with force._thermal_hint(board_hint):
        domains = topology.board_current_domains(board, board_hint)
    domain = domains.get(demand['net'], {})
    if domain.get('complete') is not True:
        raise ValueError('complete_source_current_domain_required_for_quiet_fanout')
    lineage = sense.board_evidence(board, anchor_refs=domain['authority_refs'])
    candidates = []
    for row in lineage['details']:
        if row.get('ok') is not True or row['selected']['kind'] != 'direct':
            continue
        for s in sense.placement_segments(row):
            if (s['net'] != demand['net'] or s['end'] != demand['source_segment']['end']
                    or s['start']['ref'] == demand['source_segment']['start']['ref']):
                continue
            owners = [p for p in pads.values()
                if p.GetParentFootprint().GetReference() == s['start']['ref']
                and p.GetNumber() == s['start']['pad']]
            if len(owners) == 1 and (peer_pad_uuid is None or force._uid(owners[0]) == peer_pad_uuid):
                candidates.append(owners[0])
    if len(candidates) > 8:
        raise ValueError('bounded_source_quiet_peer_portfolio_required')
    candidates.sort(key=lambda p: (math.dist(p.GetPosition(), pads[pad_uuid].GetPosition()), force._uid(p)))
    result['refusals'] = []
    for peer in candidates:
        _tick(deadline)
        try:
            tree = _quiet_tree(board, force._uid(peer), force._uid(target), domain, deadline=deadline)
            if any(w < fresh['request']['width_nm']
                    for _face,w in tree['track_widths_by_uuid'].values()):
                raise ValueError('retained_quiet_tree_below_project_nonload_process_floor')
            if set(tree['leaf_pad_uuids']) & set(demand['source_input_island_uuids']):
                raise ValueError('quiet_peer_and_stranded_input_must_be_distinct_source_components')
            ports=_ports(board,tree,peer)
            if port_key is not None:ports=[p for p in ports if p['key']==port_key]
            if not ports:raise ValueError('selected_port_not_an_actual_source_quiet_endpoint')
            ports.sort(key=lambda p:(math.dist(p['at_nm'],pads[pad_uuid].GetPosition()),p['key']))
            result.update(complete=True, peer_pad_uuid=force._uid(peer),
                peer_position_nm=list(peer.GetPosition()), source_quiet_tree=tree,
                width_nm=fresh['request']['width_nm'], source_native_binding=before,
                ports=ports,port_key=port_key)
            break
        except ValueError as exc:
            result['refusals'].append(dict(peer_pad_uuid=force._uid(peer), reason=str(exc)))
    if before != binding._source_binding(board):
        raise ValueError('source_quiet_fanout_inventory_changed_native_source')
    _tick(deadline)
    result['elapsed_s'] = time.monotonic()-started
    return result


def contact_guard(board, proposal, *, deadline):
    """One exact retained port aperture; NOT the entire quiet tree."""
    from shapely.geometry import LineString,Point,GeometryCollection
    from shapely.ops import unary_union
    import cec_kelvin_copper_cut as cut
    import cec_measurement_leaf as leaf
    pads = _native_pads(board)
    demand = proposal['source_request']['request']['demand']
    root, peer = pads[proposal['pad_uuid']], pads[proposal['peer_pad_uuid']]
    width = proposal['width_nm'];layer = int(pcbnew.F_Cu)
    work = cut._Work(deadline)
    root_shape = cut._shape(root, layer, True, work)
    port=proposal['selected_port']
    if port not in _ports(board,proposal['source_quiet_tree'],peer):
        raise ValueError('actual_source_quiet_endpoint_port_required')
    port_ids=set(port['item_uuids'])
    tracks={force._uid(t):t for t in board.GetTracks()}
    aperture=(cut._shape(peer,layer,True,work) if port['kind']=='actual_quiet_input_land'
        else Point(port['at_nm']).buffer(max(tracks[u].GetWidth()/2 for u in port_ids)+width/2+1002,quad_segs=64))
    stranded = set(demand['source_input_island_uuids'])
    shapes = []
    for item in [*pads.values(), *board.GetTracks(),
            *[z for z in board.Zones() if not z.GetIsRuleArea()]]:
        work.tick()
        if item.GetNetCode() != root.GetNetCode() or not item.IsOnLayer(layer):
            continue
        if item.GetClass() == 'ZONE':
            if not item.IsFilled():
                raise ValueError('quiet_fanout_requires_actual_saved_same_net_fills')
            shape = cut._poly(item.GetFilledPolysList(layer), work)
        else:
            shape = cut._shape(item, layer, True, work)
        allowed = (aperture if port['kind']=='actual_quiet_input_land'
            or force._uid(item) in port_ids else GeometryCollection())
        if force._uid(item) in stranded:
            allowed = allowed.union(root_shape.buffer(width/2+1002))
        if port['kind']=='actual_quiet_input_land' and force._uid(item) == force._uid(peer):
            allowed = allowed.buffer(width/2+1002)
        shapes.append(shape.difference(allowed))
    blocked = unary_union(shapes)
    original = leaf._binding(board)
    def edge(a, b, w):
        work.tick()
        if not width <= w <= width+1 or tuple(a) == tuple(b):
            return False
        return not blocked.intersects(LineString([tuple(a), tuple(b)]).buffer(w/2+1000, quad_segs=64))
    def operations(ops):
        return bool(ops) and all(op[0] == 'trk' and int(op[4]) == layer
            and edge(op[1], op[2], op[3]) for op in ops)
    return dict(edge=edge, operations=operations, root=root, peer=peer,
        unchanged=lambda: original == leaf._binding(board))


def geometry(board, proposal, *, board_hint, timeout_s=10.):
    """One finite Source-owned front-only search; never a no-path proof."""
    from cec_field_search import PlanarSearchGuard
    deadline = time.monotonic()+isolated._budget(timeout_s, 10.)
    guard = contact_guard(board, proposal, deadline=deadline)
    root, peer = guard['root'], guard['peer']
    net = root.GetNetname();width = proposal['width_nm'];layer = int(pcbnew.F_Cu)
    gap = max(200000, int(board.GetDesignSettings().m_MinClearance))
    resolver = fr._project_netclass_resolver(str(board.GetFileName()), board=board)
    pruning = PlanarSearchGuard(board, net, netclass_resolver=resolver, board_hint=board_hint)
    foreign = {};diagnostics = []
    def complete(ops):
        if (not ops or len(ops) > isolated.MAX_TRACKS or not guard['operations'](ops)
                or sum(math.dist(op[1], op[2]) for op in ops) > isolated.MAX_PATH_LENGTH_NM):
            return False
        # Search points can form an endpoint-linear graph while the actual
        # finite-width capsules touch across a tiny jog. Same-net clearance
        # and general craft checks do not establish this operator's simple
        # branch scope. Apply the exact saved receiver predicate BEFORE
        # returning a proposal, without adding any provisional copper.
        try:
            _ordered_proposal(board, ops, root, width_nm=width,
                endpoint=proposal['selected_port']['at_nm'], deadline=deadline)
        except ValueError:
            _tick(deadline)
            return False
        if not all(fr._edge_leg_clear(board, pcbnew.VECTOR2I(*op[1]), pcbnew.VECTOR2I(*op[2]), width/2+gap)
                and fr._tap_foreign_clear(board, pcbnew.VECTOR2I(*op[1]), pcbnew.VECTOR2I(*op[2]), width,
                    layer, gap, {root.GetNetCode()}, foreign_cache=foreign) for op in ops):
            return False
        for report in (terminal.assess_path_craft(board, ops, net=net, deadline=deadline),
                terminal.assess_path_field(board, ops, net=net, deadline=deadline,
                    netclass_resolver=resolver, board_hint=board_hint)):
            if not (report.get('ok') is True and report.get('complete') is True
                    and report.get('board_mutated') is False):
                return False
        return True
    start, end = tuple(root.GetPosition()), tuple(proposal['selected_port']['at_nm'])
    def ops_for(points):
        return [['trk', list(a), list(b), width, layer] for a,b in zip(points, points[1:]) if a != b]
    paths=[*fr._canonical_45_xy_paths(start,end),*fr._offset_manhattan_xy_paths(start,end)]
    # General pin-exit tier, before a raster search: an initial cardinal
    # escape followed by canonical 45-degree geometry avoids an adjacent
    # package land that defeats both endpoint-only diagonal alternatives.
    # Distances are a finite search menu, not fabrication/clearance claims.
    for distance in(400000,500000,750000,1000000):
        for dx,dy in((0,1),(1,0),(0,-1),(-1,0)):
            launch=(start[0]+dx*distance,start[1]+dy*distance)
            paths.extend([start,*p] for p in fr._canonical_45_xy_paths(launch,end))
    for points in paths:
        _tick(deadline)
        ops = ops_for(points)
        if complete(ops):
            return dict(ops=ops, complete=True, source_unchanged=guard['unchanged'](), diagnostics=diagnostics)
    for index, margin in enumerate((6.,12.)):
        _tick(deadline)
        phase = time.monotonic()+(deadline-time.monotonic())/(2-index)
        detail = {}
        legs = fr._guarded_profiled_lastmile_legs(board, pcbnew.VECTOR2I(*start), pcbnew.VECTOR2I(*end),
            width, layer, gap, root.GetNetCode(),
            lambda a,b,h: fr._edge_leg_clear(board,a,b,h+gap)
                and guard['edge'](a,b,2*int(h)+1)
                and pruning(a,b,2*int(h)+1,layer) is True,
            foreign_cache=foreign, deadline_monotonic=phase, refine_maze=True,
            endpoint_detail_grid_mm=.2, maze_margin_mm=margin,
            max_length_nm=isolated.MAX_PATH_LENGTH_NM, refinement_grids_mm=(.2,.1),
            search_diagnostics=detail,
            run_guard=None if not pruning.active else lambda a,b,w: pruning(a,b,w,layer),
            path_validator=lambda rows: complete(ops_for([tuple(rows[0][0]), *[tuple(q[1]) for q in rows]])))
        diagnostics.append(dict(margin_mm=margin, search=detail))
        if legs:
            ops = ops_for([tuple(legs[0][0]), *[tuple(q[1]) for q in legs]])
            if complete(ops):
                return dict(ops=ops, complete=True, source_unchanged=guard['unchanged'](), diagnostics=diagnostics)
    return dict(ops=[], complete=False, source_unchanged=guard['unchanged'](),
        diagnostics=diagnostics, no_path_proof=False)


def construct_private(source, candidate, proposal, *, board_hint, timeout_s=10.):
    """Explicit composition of <=10-second Source, geometry and save phases."""
    import cec_cell_escape_replan as escape
    import cec_additive_pair_repair as additions
    source,candidate = [Path(p).resolve(strict=True) for p in (source,candidate)]
    if source == candidate or force._hash(source) != force._hash(candidate):
        raise ValueError('exact_private_source_copy_required_for_quiet_fanout')
    board = pcbnew.LoadBoard(str(source))
    fresh = plan(board, source, board_hint=board_hint, pad_uuid=proposal['pad_uuid'],
        peer_pad_uuid=proposal['peer_pad_uuid'],port_key=proposal.get('port_key'), timeout_s=timeout_s)
    if not fresh['complete']:
        raise ValueError('fresh_source_quiet_fanout_scope_refused')
    fresh['selected_port']=fresh['ports'][0]
    result = geometry(board, fresh, board_hint=board_hint, timeout_s=timeout_s)
    result['fresh_source_scope'] = fresh
    if not result['complete']:
        return result
    old = {force._uid(t) for t in board.GetTracks()}
    escape._native_ops(board, result['ops'], fresh['source_request']['request']['demand']['net'])
    started = time.monotonic();result['save'] = {}
    additions.save_native_additions(candidate, board, result['save'], old, board_hint=board_hint)
    if time.monotonic()-started >= timeout_s:
        raise ValueError('quiet_fanout_native_save_phase_deadline')
    result['candidate_sha256'] = force._hash(candidate)
    result['routing_admitted'] = result['release_authority'] = False
    return result


def _ordered_branch(items,root,*,width_nm,deadline):
    """Return the exact endpoint of one literal bounded new track chain."""
    if not 1<=len(items)<=isolated.MAX_TRACKS:
        raise ValueError('bounded_new_quiet_track_chain_required')
    adjacency={}
    for item in items:
        _tick(deadline)
        if (item.GetClass()!='PCB_TRACK' or item.GetLayer()!=pcbnew.F_Cu
                or item.GetWidth()!=width_nm or item.GetNetname()!=root.GetNetname()
                or item.HasSolderMask() or item.GetParentGroup() is not None):
            raise ValueError('quiet_branch_must_keep_source_front_nonload_dimensions_and_role')
        a,b=tuple(item.GetStart()),tuple(item.GetEnd())
        if a==b or a[0]!=b[0] and a[1]!=b[1] and abs(a[0]-b[0])!=abs(a[1]-b[1]):
            raise ValueError('canonical_nonempty_quiet_branch_required')
        for point in(a,b):adjacency.setdefault(point,[]).append((item,b if point==a else a))
    current=tuple(root.GetPosition())
    if (len(adjacency)!=len(items)+1 or len(adjacency.get(current,()))!=1
            or sum(len(v)==1 for v in adjacency.values())!=2
            or any(len(v)>2 for v in adjacency.values())):
        raise ValueError('single_rooted_nonbranching_quiet_addition_required')
    visited=set();ops=[];ordered=[]
    while len(visited)<len(items):
        choices=[(t,p) for t,p in adjacency[current] if force._uid(t) not in visited]
        if len(choices)!=1:raise ValueError('quiet_additions_disconnected_or_cyclic')
        item,peer=choices[0];visited.add(force._uid(item))
        ordered.append(item)
        ops.append(['trk',list(current),list(peer),width_nm,int(pcbnew.F_Cu)]);current=peer
    if sum(math.dist(op[1],op[2]) for op in ops)>isolated.MAX_PATH_LENGTH_NM:
        raise ValueError('bounded_quiet_additive_path_length_required')
    # An endpoint-linear graph alone misses a physical crossing at the
    # interior of a nonadjacent segment. Same-net DRC permits that contact,
    # but this stage owns one simple branch, not a hidden mesh or shortcut.
    for index,left in enumerate(ordered):
        for right in ordered[index+2:]:
            _tick(deadline)
            if left.GetEffectiveShape(pcbnew.F_Cu).Collide(right.GetEffectiveShape(pcbnew.F_Cu),0):
                raise ValueError('quiet_branch_has_nonadjacent_native_copper_contact')
    return ops,current


def _ordered_proposal(board, ops, root, *, width_nm, endpoint, deadline):
    """Receiver-identical reject-only geometry on detached native tracks.

    This neither mutates the board nor proves Source/foreign/field/craft
    authority. Those existing guards and independent saved receiving remain
    mandatory. In particular no short-edge, angle or overlap tolerance is
    introduced to turn a self-contacting branch into a valid proposal.
    """
    if type(ops) not in (list, tuple) or not 1 <= len(ops) <= isolated.MAX_TRACKS:
        raise ValueError('bounded_new_quiet_track_proposal_required')
    items=[]
    for op in ops:
        _tick(deadline)
        if (type(op) not in (list, tuple) or len(op) != 5 or op[0] != 'trk'
                or op[3] != width_nm or type(op[3]) is not int
                or type(op[4]) is not int or op[4] != int(pcbnew.F_Cu)
                or any(type(p) not in (list, tuple) or len(p) != 2
                    or any(type(v) is not int for v in p) for p in op[1:3])):
            raise ValueError('exact_front_quiet_native_track_proposal_required')
        track=pcbnew.PCB_TRACK(board)
        track.SetNet(root.GetNet());track.SetLayer(pcbnew.F_Cu);track.SetWidth(width_nm)
        track.SetStart(pcbnew.VECTOR2I(*op[1]));track.SetEnd(pcbnew.VECTOR2I(*op[2]))
        items.append(track)
    ordered, actual=_ordered_branch(items,root,width_nm=width_nm,deadline=deadline)
    if tuple(endpoint) != actual:
        raise ValueError('proposed_branch_must_end_at_exact_selected_source_port')
    return ordered, actual


def receive(source, candidate, *, board_hint, pad_uuid, peer_pad_uuid, timeout_s=10.):
    import cec_additive_route_receiving as additive
    import cec_source_literal_additions as literal
    import cec_current_topology as topology
    started = time.monotonic();deadline = started+isolated._budget(timeout_s,10.)
    result = dict(schema=1, ok=False, complete=False, errors=[],
        routing_admitted=False, current_authority=False, kelvin_qualified=False,
        retirement_authority=False, placement_authority=False, release_authority=False,
        mandatory_shared_receiving=list(isolated.SHARED_RECEIVERS))
    try:
        source,candidate=[Path(p).resolve(strict=True) for p in (source,candidate)]
        if source==candidate:
            raise ValueError('distinct_quiet_fanout_native_endpoints_required')
        epoch=force._code_identity();families=[force._family(p,board_hint) for p in (source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        fresh=plan(parent,source,board_hint=board_hint,pad_uuid=pad_uuid,
            peer_pad_uuid=peer_pad_uuid,timeout_s=max(.001,deadline-time.monotonic()))
        result['independently_compiled_source_scope']=fresh
        if not fresh['complete']:
            raise ValueError('independent_source_quiet_tree_refused')
        received=additive.receive(source,candidate,timeout_s=max(.001,deadline-time.monotonic()))
        result['source_delta']=received
        if received.get('ok') is not True or received.get('complete') is not True:
            raise ValueError('exact_literal_source_plus_additions_required')
        incoming=set(received['added_native_uuids'])
        items=[t for t in child.GetTracks() if force._uid(t) in incoming]
        if not incoming or {force._uid(t) for t in items} != incoming:
            raise ValueError('only_bounded_quiet_fanout_tracks_may_be_added')
        pads=_native_pads(child)
        net=fresh['source_request']['request']['demand']['net']
        if any(n!=net for n in literal.incoming_copper_nets(candidate.read_text(),incoming).values()):
            raise ValueError('saved_literal_quiet_fanout_net_differs')
        ops,endpoint=_ordered_branch(items,pads[pad_uuid],width_nm=fresh['width_nm'],deadline=deadline)
        ports=[p for p in fresh['ports'] if tuple(p['at_nm'])==endpoint]
        if len(ports)!=1:raise ValueError('new_branch_must_end_at_exact_source_quiet_port')
        fresh['selected_port']=ports[0]
        guard=contact_guard(parent,fresh,deadline=deadline)
        if not guard['operations'](ops) or not guard['unchanged']():
            raise ValueError('quiet_fanout_acquires_contact_outside_exact_input_land')
        for kind,proof in [('craft',terminal.assess_path_craft(parent,ops,net=net,deadline=deadline)),
                ('field',terminal.assess_path_field(parent,ops,net=net,deadline=deadline,
                    netclass_resolver=fr._project_netclass_resolver(str(source)),board_hint=board_hint))]:
            result[kind]=proof
            if not(proof.get('ok')is True and proof.get('complete')is True
                    and proof.get('board_mutated')is False):
                raise ValueError('quiet_fanout_complete_path_'+kind+'_refused')
        with force._thermal_hint(board_hint):
            domain=topology.board_current_domains(parent,board_hint)[net]
        target=fresh['source_request']['request']['demand']['target_uuid']
        result['saved_shared_quiet_tree']=_quiet_tree(child,pad_uuid,target,domain,deadline=deadline)
        if not incoming<=set(result['saved_shared_quiet_tree']['track_uuids']):
            raise ValueError('every_new_track_must_belong_to_one_typed_quiet_tree')
        counts=[fr.net_connectivity_component_count(b,b.GetNetcodeFromNetname(net)) for b in(parent,child)]
        if counts[1] != counts[0]-1:
            raise ValueError('exactly_one_source_quiet_input_component_must_close')
        _tick(deadline)
        if epoch!=force._code_identity() or families!=[force._family(p,board_hint) for p in(source,candidate)]:
            raise ValueError('quiet_fanout_source_candidate_or_code_epoch_changed')
        result.update(ok=True,complete=True,added_native_uuids=sorted(incoming),
            source_components=counts[0],candidate_components=counts[1],
            exact_source_shunt_and_original_quiet_tree_retained=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s']=time.monotonic()-started
    return result
