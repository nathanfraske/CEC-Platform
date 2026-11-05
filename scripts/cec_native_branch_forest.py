"""Bounded native branch transactions for private motion reconstruction.

An obstructed branch junction is not a routing terminal. Collect its literal
equal-width, equal-owner native edges to clear external ports, then propose a
whole-tree transaction. This never credits reduced current, divided current,
new barrel capacity or automatic retirement. Saved native partitions, source
current, Kelvin, factory and mating receiving remain mandatory.
"""
import math
import json
import time
import pcbnew
import cec_force_current as force
import cec_fr as fr


def plan(board, rows, *, clearance_for, timeout_s=3., maximum_members=16,
         maximum_cut_nm=96000000, maximum_ports=16, maximum_input_edges=64,
         allow_literal_body_cohort=False, allow_lock_tightening=False,
         provisional_reconstruction_track_uuids=(), normalize_free_pending_junctions=False,
         source_path=None, board_hint=None, prefer_existing_ordinary_barrel_ports=False,
         collapse_retained_native_ports=False,close_provisional_native_junctions=False):
    if (type(allow_literal_body_cohort) is not bool or type(allow_lock_tightening) is not bool
            or type(normalize_free_pending_junctions) is not bool
            or type(prefer_existing_ordinary_barrel_ports) is not bool
            or type(collapse_retained_native_ports) is not bool
            or type(close_provisional_native_junctions) is not bool
            or close_provisional_native_junctions and not (
                collapse_retained_native_ports and allow_literal_body_cohort)
            or prefer_existing_ordinary_barrel_ports and not normalize_free_pending_junctions
            or not callable(clearance_for) or type(timeout_s) not in (int, float)
            or not math.isfinite(timeout_s) or not 0 < timeout_s <= 10
            or type(maximum_members) is not int or not 3 <= maximum_members <= 32
            or type(maximum_cut_nm) is not int or not 0 < maximum_cut_nm <= 96000000
            or type(maximum_ports) is not int or not 3 <= maximum_ports <= 32
            or type(maximum_input_edges) is not int or not 1<=maximum_input_edges<=128
            or type(rows) not in (list, tuple) or not 1 <= len(rows) <= maximum_input_edges):
        raise ValueError('bounded_explicit_native_branch_transaction_required')
    deadline = time.monotonic() + timeout_s
    items = {force._uid(t): t for t in board.GetTracks()}
    pads = [p for f in board.GetFootprints() for p in f.Pads()]
    pending = {r['uid']: r for r in rows}
    if type(provisional_reconstruction_track_uuids) not in (list,tuple,set,frozenset):
        raise ValueError('literal_bounded_branch_provisional_track_inventory_required')
    provisional=set(provisional_reconstruction_track_uuids)
    if (len(provisional)>256 or len(provisional)!=len(provisional_reconstruction_track_uuids)
            or not provisional<=items.keys()
            or any(items[u].GetClass()!='PCB_TRACK' for u in provisional)):
        raise ValueError('literal_bounded_branch_provisional_track_inventory_required')
    if len(items) > 8192 or len(pads) > 4096 or len(pending) != len(rows):
        raise ValueError('bounded_unique_native_branch_inventory_required')
    for uid, row in pending.items():
        item = items.get(uid)
        if (item is None or item.GetClass() != 'PCB_TRACK' or row['item'] != item
                or row['net'] != str(item.GetNetname()) or row['code'] != item.GetNetCode()
                or row['layer'] != item.GetLayer() or row['width'] != item.GetWidth()
                or row['locked'] != item.IsLocked()
                or {tuple(row['start']), tuple(row['end'])} !=
                   {tuple(item.GetStart()), tuple(item.GetEnd())}):
            raise ValueError('branch_transaction_must_name_literal_native_edges')
    ordinary_nets=set()
    if normalize_free_pending_junctions:
        from pathlib import Path
        import cec_ordinary_route_receiving as ordinary
        if (source_path is None or Path(source_path).resolve()!=Path(board.GetFileName()).resolve()
                or type(board_hint) is not str or not board_hint):
            raise ValueError('free_pending_branch_exact_ordinary_source_context_required')
        ordinary_nets=ordinary.eligible_nets(board,Path(source_path),board_hint)
    caches = {}
    consumed = set()
    forests = []
    refusals = []

    def tick():
        if time.monotonic() >= deadline:
            raise ValueError('native_branch_transaction_deadline')

    def groups(item):
        return sorted(force._uid(g) for g in board.Groups() if g.ContainsItem(item))

    def signature(item):
        return (int(item.GetNetCode()), int(item.GetLayer()), item.GetWidth(),
                bool(item.IsLocked()), tuple(groups(item)))

    def typed(item):
        return any(g.ContainsItem(item) and
                   g.GetName().startswith('CEC_LOCAL_SUPPLY_ALLOCATION_V1|')
                   for g in board.Groups())

    def endpoints(item):
        return (tuple(item.GetStart()), tuple(item.GetEnd()))

    def native_contacts(at, root):
        tick()
        code, layer, width = root.GetNetCode(), root.GetLayer(), root.GetWidth()
        cap = pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*at), pcbnew.VECTOR2I(*at), width)
        def hit(item):
            return (item.GetNetCode() == code and item.IsOnLayer(layer)
                    and item.GetEffectiveShape(layer).Collide(cap, 0))
        terminals = [force._uid(p) for p in pads if hit(p)]
        barrels = [u for u, t in items.items() if t.GetClass() == 'PCB_VIA' and hit(t)]
        tracks = [u for u, t in items.items() if t.GetClass() == 'PCB_TRACK' and hit(t)]
        return terminals, barrels, tracks

    def clear(at, root):
        gap = clearance_for(str(root.GetNetname()))
        if type(gap) is not int or not 0 <= gap <= 2000000:
            raise ValueError('explicit_native_branch_clearance_required')
        zones,copper=obstacles(root.GetNetCode(),root.GetLayer())
        return fr._snapshot_foreign_clear(pcbnew.VECTOR2I(*at),pcbnew.VECTOR2I(*at),
            root.GetWidth(),gap,zones,copper)

    def obstacles(code,layer):
        key=(int(code),int(layer))
        if key not in caches:
            zones,copper=fr._identified_foreign_shape_indexes(board,layer,{code})
            if provisional:
                native=copper.get('rows',()) if isinstance(copper,dict) else copper
                copper=fr._bucket_foreign_shapes([r for r in native
                    if (r[2] or {}).get('uuid') not in provisional])
            caches[key]=(zones,copper)
        return caches[key]

    def free_pending_node(root,terminals,barrels,touching):
        return (normalize_free_pending_junctions and str(root.GetNetname()) in ordinary_nets
                and not terminals and not barrels and len(touching)>=2
                and set(touching)<=pending.keys())

    def provisional_only_node(terminals,barrels,touching,owned=()):
        # Exact declared pending source tracks can form a clear-looking
        # junction with NO retained material. It is not an external port on
        # any net. Follow its real same-owner edges; the complete source
        # current/partition receivers still decide the resulting transaction.
        return (close_provisional_native_junctions and not terminals and not barrels
                and len(touching)>=2 and set(touching)<=(provisional|set(owned)))

    for uid, row in sorted(pending.items()):
        tick()
        if uid in consumed or row['typed_anchor_retained'] or typed(items[uid]):
            continue
        root = items[uid]
        # Leave ordinary degree-two work to its existing bounded receiver.
        seeds = []
        for at in endpoints(root):
            terminals, barrels, touching = native_contacts(at, root)
            if clear(at,root) and not (free_pending_node(root,terminals,barrels,touching)
                    or provisional_only_node(terminals,barrels,touching,{uid})):
                continue
            if len(touching) >= 3 or (allow_literal_body_cohort and len(touching) >= 2
                    and any(at not in endpoints(items[u]) for u in touching)):
                seeds.append((at, terminals, barrels, touching))
        if not seeds:
            continue
        member_ids = {uid}
        queue = list(endpoints(root))
        visited = set()
        ports = set()
        branch_nodes = []
        actual_body_terminal_ports=[]
        merged_member_cohorts=[]
        closed_provisional_junctions=[]
        def admit_member(other):
            item = items[other]
            left, right = signature(item), signature(root)
            same_owner = left[:3] == right[:3] and left[4] == right[4]
            if (not same_owner or typed(item)
                    or (left[3] != right[3] and not allow_lock_tightening)):
                raise ValueError('branch_width_lock_group_or_current_allocation_boundary')
            if other in consumed:
                if not (close_provisional_native_junctions or (
                        normalize_free_pending_junctions and str(root.GetNetname()) in ordinary_nets)):
                    raise ValueError('native_branch_transaction_already_consumed_boundary')
                previous=[f for f in forests if other in f['member_uuids']]
                if len(previous)!=1:raise ValueError('unique_native_prior_body_cohort_required')
                prior=previous[0]
                if any(signature(items[u])[:3]!=signature(root)[:3]
                    or signature(items[u])[4]!=signature(root)[4] or typed(items[u])
                    or (items[u].IsLocked()!=root.IsLocked() and not allow_lock_tightening)
                    for u in prior['member_uuids']):
                    raise ValueError('prior_native_body_cohort_owner_width_or_lock_boundary')
                forests.remove(prior);consumed.difference_update(prior['member_uuids'])
                merged_member_cohorts.append(prior['member_uuids'])
                ports.update(tuple(p) for p in prior['external_ports_nm'])
                for contact in (prior.get('retained_native_port_island_collapse') or {}).get('contacts',[]):
                    ports.add(tuple(contact['at_nm']))
                branch_nodes.extend(prior['source_branch_nodes'])
                actual_body_terminal_ports.extend(prior['actual_retained_body_terminal_ports'])
                closed_provisional_junctions.extend(prior.get('closed_provisional_junctions',[]))
                for u in prior['member_uuids']:
                    if u not in member_ids:
                        member_ids.add(u);queue.extend(endpoints(items[u]))
            if other not in member_ids:
                member_ids.add(other)
                queue.extend(endpoints(item))
            if (len(member_ids) > maximum_members or
                    sum(items[u].GetLength() for u in member_ids) > maximum_cut_nm or
                    any(items[u].GetLength() > 32000000 for u in member_ids)):
                raise ValueError('native_branch_transaction_count_or_length_bound:'+json.dumps(dict(
                    net=str(root.GetNetname()),layer=int(root.GetLayer()),
                    actual_member_count=len(member_ids),maximum_members=maximum_members,
                    actual_source_cut_length_nm=sum(items[u].GetLength() for u in member_ids),
                    maximum_cut_nm=maximum_cut_nm,
                    source_track_uuids=sorted(member_ids),work_bound_not_ownership_or_current_permission=True),
                    sort_keys=True))

        while True:
            while queue:
                tick()
                at = queue.pop()
                if at in visited:
                    continue
                visited.add(at)
                terminals, barrels, touching = native_contacts(at, root)
                pending_only=provisional_only_node(terminals,barrels,touching,member_ids)
                if clear(at,root) and not (free_pending_node(root,terminals,barrels,touching) or pending_only):
                    ports.add(at)
                    continue
                if pending_only:
                    closed_provisional_junctions.append(dict(at_nm=list(at),
                        actual_declared_pending_track_uuids=sorted(touching),
                        actual_retained_land_or_barrel_contacts=0,
                        external_port_or_current_authority=False))
                if terminals or barrels:
                    raise ValueError('blocked_branch_is_actual_native_terminal_or_barrel:' + json.dumps(dict(
                        requested_track_uuid=uid, at_nm=list(at), net=str(root.GetNetname()),
                        layer=int(root.GetLayer()), width_nm=root.GetWidth(),
                        actual_native_pad_uuids=terminals, actual_native_barrel_uuids=barrels), sort_keys=True))
                interior = [u for u in touching if at not in endpoints(items[u])]
                if not touching or (interior and not allow_literal_body_cohort):
                    raise ValueError('branch_interior_body_contact_requires_separate_ownership:'+json.dumps(dict(
                        requested_track_uuid=uid,at_nm=list(at),net=str(root.GetNetname()),
                        layer=int(root.GetLayer()),width_nm=root.GetWidth(),
                        touching_native_track_uuids=touching,
                        interior_contact_track_uuids=interior,
                        native_track_ports={u:[list(p) for p in endpoints(items[u])] for u in touching}),sort_keys=True))
                if len(touching) >= 3 or interior:
                    branch_nodes.append(dict(at_nm=list(at), native_track_uuids=sorted(touching),
                        literal_native_body_contact_uuids=interior))
                for other in touching:
                    admit_member(other)
            # A body contact outside the retained apertures requires closure of
            # its actual whole edge. It cannot be silently treated as a port,
            # rounded to an endpoint, or discarded as redundant.
            port_caps = [pcbnew.SHAPE_SEGMENT(pcbnew.VECTOR2I(*p), pcbnew.VECTOR2I(*p),
                          root.GetWidth()) for p in ports]
            extension = set()
            for member in sorted(member_ids):
                tick()
                shape = items[member].GetEffectiveShape(root.GetLayer())
                contacts = [p for p in pads if p.GetNetCode() == root.GetNetCode()
                            and p.IsOnLayer(root.GetLayer()) and
                            shape.Collide(p.GetEffectiveShape(root.GetLayer()), 0)]
                contacts += [t for u, t in items.items() if u not in member_ids
                             and t.GetNetCode() == root.GetNetCode() and
                             t.IsOnLayer(root.GetLayer()) and
                             shape.Collide(t.GetEffectiveShape(root.GetLayer()), 0)]
                for other in contacts:
                    if any(c.Collide(other.GetEffectiveShape(root.GetLayer()), 0) for c in port_caps):
                        continue
                    if allow_literal_body_cohort and other.GetClass() in ('PAD','PCB_VIA'):
                        at=tuple(other.GetPosition())
                        centered=bool(shape.Collide(other.GetPosition(),0))
                        # A conducting land's exact center is a legitimate
                        # routing target even when its existing capture is
                        # off-center. A barrel needs a separate body-contact
                        # proof when its center is outside the owned strip.
                        ordinary_barrel=(other.GetClass()=='PCB_VIA' and normalize_free_pending_junctions
                            and str(root.GetNetname()) in ordinary_nets)
                        if (centered or other.GetClass()=='PAD' or ordinary_barrel) and clear(at,root):
                            if other.GetClass()=='PCB_VIA':
                                gap=clearance_for(str(root.GetNetname()))
                                if not all(fr._snapshot_foreign_clear(other.GetPosition(),other.GetPosition(),
                                    other.GetWidth(l),gap,*obstacles(root.GetNetCode(),l))
                                    for l in board.GetEnabledLayers().CuStack()):
                                    raise ValueError('native_body_terminal_barrel_all_face_clearance_required')
                            ports.add(at)
                            port_caps.append(pcbnew.SHAPE_SEGMENT(other.GetPosition(),other.GetPosition(),root.GetWidth()))
                            actual_body_terminal_ports.append(dict(native_uuid=force._uid(other),
                                kind=other.GetClass(),at_nm=list(at),source_center_in_owned_actual_copper=centered,
                                actual_retained_terminal_material_contact=True,
                                source_positive_ordinary_barrel_context=ordinary_barrel,
                                new_barrel_or_current_authority=False))
                            continue
                    if not allow_literal_body_cohort or other.GetClass() != 'PCB_TRACK':
                        raise ValueError('unrepresented_native_branch_body_or_terminal_contact:'+json.dumps(dict(
                            requested_track_uuid=uid,member_track_uuid=member,net=str(root.GetNetname()),
                            layer=int(root.GetLayer()),contact_uuid=force._uid(other),
                            contact_kind=other.GetClass(),contact_position_nm=list(other.GetPosition()),
                            retained_ports_nm=[list(p) for p in sorted(ports)]),sort_keys=True))
                    extension.add(force._uid(other))
            if not extension:
                # Body-contact closure may have just consumed the copper
                # that originally made a clear endpoint look retained. Its
                # old classification cannot survive that ownership change.
                # Revisit every pending/owned-only node to a fixed point.
                revisit=[]
                for at in sorted(ports):
                    terminals,barrels,touching=native_contacts(at,root)
                    if provisional_only_node(terminals,barrels,touching,member_ids):
                        revisit.append(at)
                if revisit:
                    ports.difference_update(revisit);visited.difference_update(revisit)
                    queue.extend(revisit)
                    continue
                break
            for other in sorted(extension):
                admit_member(other)
        ordinary_two_terminal_kernel=bool(len(ports)==2 and branch_nodes and
            normalize_free_pending_junctions and str(root.GetNetname()) in ordinary_nets
            and allow_literal_body_cohort and collapse_retained_native_ports
            and close_provisional_native_junctions and not signature(root)[4])
        # Vertex degree is not terminal count. A positive ordinary network
        # can contain internal tees/loops yet have exactly two actual retained
        # terminals. Reconstruct its whole finite kernel as one connection;
        # never apply this classification to current/ground/pair/group debt.
        # The actual-material port check below still rejects phantom ends.
        minimum_ports=2 if ordinary_two_terminal_kernel or allow_literal_body_cohort and any(
            n.get('literal_native_body_contact_uuids') for n in branch_nodes) else 3
        if not branch_nodes or not minimum_ports <= len(ports) <= maximum_ports:
            raise ValueError('whole_native_branch_clear_external_ports_required:'+json.dumps(dict(
                requested_track_uuid=uid,net=str(root.GetNetname()),layer=int(root.GetLayer()),
                width_nm=int(root.GetWidth()),source_member_uuids=sorted(member_ids),
                branch_nodes=branch_nodes,retained_ports_nm=[list(p) for p in sorted(ports)],
                minimum_ports=minimum_ports,maximum_ports=maximum_ports,
                electrical_or_retirement_permission_granted=False),sort_keys=True))
        if allow_literal_body_cohort:
            # Closure can expose an internal, already-clear junction. It is
            # not an external port once every contacting edge is owned.
            actual_ports=set()
            for at in ports:
                terminals,barrels,touching=native_contacts(at,root)
                if terminals or barrels or set(touching)-member_ids:
                    actual_ports.add(at)
            if not minimum_ports <= len(actual_ports) <= maximum_ports:
                raise ValueError('whole_native_body_branch_actual_retained_ports_required')
            ports=actual_ports
        tightened_lock = any(items[u].IsLocked() for u in member_ids)
        # A geometric tree merely proposes joins between already connected
        # source ports. It is not evidence that any proposed leg is routable.
        retained_port_islands=None
        if collapse_retained_native_ports:
            from cec_native_retained_port_islands import collapse
            representatives,retained_port_islands=collapse(board,
                net_code=int(root.GetNetCode()),layer=int(root.GetLayer()),
                width_nm=int(root.GetWidth()),points_nm=sorted(ports),
                retired_uuids=member_ids,provisional_uuids=provisional,deadline=deadline,
                maximum_retired_tracks=maximum_members,maximum_ports=maximum_ports)
            ports=set(representatives)
        ordered_ports = sorted(ports)
        reached = {ordered_ports[0]}
        edges = []
        barrel_roots=[];barrel_star=None
        if prefer_existing_ordinary_barrel_ports and str(root.GetNetname()) in ordinary_nets:
            import cec_fab_profile as fab
            for item in items.values():
                if (item.GetClass()!='PCB_VIA' or item.GetNetCode()!=root.GetNetCode()
                        or not item.IsOnLayer(root.GetLayer()) or tuple(item.GetPosition()) not in ports
                        or item.GetViaType()!=pcbnew.VIATYPE_THROUGH):continue
                diameter=item.GetWidth(item.TopLayer());drill=item.GetDrillValue()
                legal_d,legal_h,_=fab.board_legal_through_via_geometry(board,diameter/1e6,drill/1e6)
                if ((diameter<math.ceil(legal_d*1e6) or drill<math.ceil(legal_h*1e6))
                        and not fab.local_pofv_via_decision(board,item)[0]):continue
                barrel_roots.append((sum(math.dist(tuple(item.GetPosition()),p) for p in ports),
                    tuple(item.GetPosition()),force._uid(item)))
            if barrel_roots:
                length,origin,identity=min(barrel_roots)
                if length<=maximum_cut_nm:
                    barrel_star=dict(native_barrel_uuid=identity,at_nm=list(origin),
                        proposed_star_length_nm=round(length),new_barrel_or_current_credit=False)
                    edges=[(origin,p) for p in sorted(ports-{origin},key=lambda p:(math.dist(origin,p),p))]
        if barrel_star is None:
            while len(reached) < len(ports):
                tick()
                _, left, right = min((math.dist(a, b), a, b)
                    for a in reached for b in ports - reached)
                edges.append((left, right))
                reached.add(right)
        if len(edges) > len(member_ids):
            raise ValueError('bounded_native_branch_route_identity_pool_required:'+json.dumps(dict(
                net=str(root.GetNetname()),layer=int(root.GetLayer()),
                actual_retired_source_track_count=len(member_ids),
                actual_retained_external_port_count=len(ports),
                proposed_tree_edge_count=len(edges),
                source_track_uuids=sorted(member_ids),
                external_native_ports_nm=[list(p) for p in ordered_ports],
                no_path_proved=False,source_retirement_authorized=False,
                current_or_clearance_qualified=False,release_authority=False),sort_keys=True))
        selected = sorted(member_ids)
        route_rows = []
        for identity, (start, end) in zip(selected, edges):
            item = items[identity]
            route_rows.append(dict(uid=identity, item=item, net=str(item.GetNetname()),
                code=int(item.GetNetCode()), layer=int(item.GetLayer()), width=item.GetWidth(),
                start=start, end=end, locked=tightened_lock,
                groups=[g for g in board.Groups() if g.ContainsItem(item)],
                typed_anchor_retained=False, envelope_extension_uuids=[],
                native_branch_transaction_member_uuids=selected))
        forests.append(dict(member_uuids=selected, external_ports_nm=[list(p) for p in ordered_ports],
            source_branch_nodes=branch_nodes, route_rows=route_rows,
            actual_retained_body_terminal_ports=actual_body_terminal_ports,
            retained_native_port_island_collapse=retained_port_islands,
            closed_provisional_junctions=closed_provisional_junctions,
            merged_previously_planned_native_member_cohorts=merged_member_cohorts,
            literal_two_port_body_cohort=len(ordered_ports)==2,
            positive_ordinary_two_terminal_kernel=ordinary_two_terminal_kernel,
            existing_positive_ordinary_barrel_tree=barrel_star,
            width_nm=root.GetWidth(), layer=int(root.GetLayer()), net=str(root.GetNetname()),
            source_lock_tightened=any(items[u].IsLocked()!=tightened_lock for u in member_ids),
            body_contacts_closed_from_actual_native_material=allow_literal_body_cohort,
            clear_ports_do_not_grant_routing_or_current_authority=True))
        consumed.update(member_ids)
    tick()
    remaining = [dict(r) for r in rows if r['uid'] not in consumed]
    proof = dict(schema=1, complete=True,
        transactions=[{k: v for k, v in f.items() if k != 'route_rows'} for f in forests],
        exact_retired_uuids=sorted(consumed), no_width_or_layer_reduction=True,
        native_geometry_mutated=False, source_partitions_and_current_receiving_required=True,
        literal_body_cohort_requested=allow_literal_body_cohort,
        lock_tightening_requested=allow_lock_tightening,
        saved_whole_source_current_receiving_required=allow_literal_body_cohort or allow_lock_tightening,
        excluded_provisional_obstacle_track_uuids=sorted(provisional),
        exclusions_only_for_scope_planning_not_saved_clearance_authority=True,
        free_pending_junctions_normalized=normalize_free_pending_junctions,
        exact_provisional_junction_closure_requested=close_provisional_native_junctions,
        proactive_junction_scope_positive_ordinary_nets_only=True,
        automatic_retirement_authorized=False, current_qualified=False, release_authority=False)
    return remaining, forests, proof
