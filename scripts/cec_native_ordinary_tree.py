"""Bounded ordinary branch proposals over actual retained native components.

The inventories are read-only. The optional private constructor only adds
untrusted proposed tracks; neither API is a source-cut or routing receiver.
THT/via barrels and already connected alternate layers are native graph edges,
not extra XY routes to invent. Every saved subtract/add still requires whole
native partition, process/current/field, DRC and absolute-cut receiving.
"""
import math
import time


def spanning_variants(ports, components, *, maximum_variants=4,maximum_ports=8):
    """Deterministic integer-distance trees between retained component sets.

    Eight actual ports by default, at most sixteen explicitly, and four proposals. A proposal is geometry
    only: its edges are not clearance, current or route-completion evidence.
    """
    if (type(maximum_ports) is not int or not 2<=maximum_ports<=16
            or type(ports) is not dict or not 2<=len(ports)<=maximum_ports
            or any(type(u) is not str or not u or type(p) not in (list,tuple) or len(p)!=2
                or any(type(x) is not int or abs(x)>2_000_000_000 for x in p) for u,p in ports.items())
            or type(components) not in (list,tuple) or not 1<=len(components)<=maximum_ports
            or any(type(c) not in (list,tuple,set,frozenset) or not c
                or any(type(u) is not str or u not in ports for u in c) for c in components)
            or sum(len(c) for c in components)!=len(ports)
            or set().union(*(set(c) for c in components))!=set(ports)
            or type(maximum_variants) is not int or not 1<=maximum_variants<=4):
        raise ValueError('bounded_unique_actual_port_component_partition_required')
    groups=sorted(tuple(sorted(c)) for c in components)
    labels={u:i for i,c in enumerate(groups) for u in c}
    ids=sorted(ports)
    edges=sorted((sum((ports[u][j]-ports[v][j])**2 for j in (0,1)),u,v)
        for i,u in enumerate(ids) for v in ids[i+1:] if labels[u]!=labels[v])
    def tree(blocked):
        root=list(range(len(groups)));selected=[]
        def find(x):
            while root[x]!=x:x=root[x]
            return x
        for _,u,v in edges:
            if (u,v) in blocked:continue
            a,b=find(labels[u]),find(labels[v])
            if a==b:continue
            root[b]=a;selected.append([u,v])
            if len(selected)==len(groups)-1:break
        return selected if len(selected)==len(groups)-1 else None
    base=tree(set());out=[]
    if base is None:raise ValueError('native_port_component_tree_unavailable')
    out.append(base)
    if maximum_variants==1:return out
    for edge in base:
        candidate=tree({tuple(edge)})
        if candidate is not None and candidate not in out:out.append(candidate)
        if len(out)>=maximum_variants:break
    return out


def retained_port_components(board, net, layer_id, source_track_uuids, *, timeout_s=2.,
        maximum_source_tracks=32,maximum_ports=8):
    """Inventory real contacts after a literal, explicitly bounded track cut.

    Keep the old source items on the scratch board for exact contact discovery,
    but omit them from the private connectivity graph. Newly constructed real
    tracks, alternate copper layers, filled zones and physical barrels remain
    in that graph. NPTH holes and virtual planning disks never become ports.
    """
    import pcbnew
    import cec_force_current as force
    if (type(maximum_source_tracks) is not int or not 1<=maximum_source_tracks<=128
            or type(maximum_ports) is not int or not 2<=maximum_ports<=16
            or type(net) is not str or not net or type(layer_id) is not int
            or not board.IsLayerEnabled(layer_id)
            or type(source_track_uuids) not in (list,tuple,set,frozenset)
            or not 1<=len(source_track_uuids)<=maximum_source_tracks
            or any(type(u) is not str or not u for u in source_track_uuids)
            or len(set(source_track_uuids))!=len(source_track_uuids)
            or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.):
        raise ValueError('explicit_bounded_native_port_scope_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('native_retained_port_inventory_deadline')
    tracks=list(board.GetTracks());pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    zones=[z for z in board.Zones() if not z.GetIsRuleArea()]
    if len(tracks)+len(pads)+len(zones)>16384:
        raise ValueError('native_retained_port_material_bound')
    live={force._uid(t):t for t in tracks};cut=set(source_track_uuids)
    if not cut<=live.keys() or any(live[u].GetClass()!='PCB_TRACK'
            or str(live[u].GetNetname())!=net or int(live[u].GetLayer())!=layer_id for u in cut):
        raise ValueError('literal_actual_one_net_face_track_cut_required')
    source=[live[u] for u in sorted(cut)]
    ports=[]
    for item in [*pads,*(t for t in tracks if t.GetClass()=='PCB_VIA')]:
        tick()
        if (str(item.GetNetname())!=net or not item.IsOnLayer(layer_id)
                or item.GetClass()=='PAD' and item.GetAttribute() not in
                (pcbnew.PAD_ATTRIB_SMD,pcbnew.PAD_ATTRIB_PTH)):continue
        if any(item.GetEffectiveShape(layer_id).Collide(t.GetEffectiveShape(layer_id),0) for t in source):
            ports.append(item)
    if not 2<=len(ports)<=maximum_ports or len({force._uid(p) for p in ports})!=len(ports):
        raise ValueError('actual_retained_native_ports_outside_explicit_work_lease')
    material={}
    for item in [*pads,*tracks,*zones]:
        tick()
        if str(item.GetNetname())!=net or force._uid(item) in cut:continue
        if item.GetClass()=='PAD' and item.GetAttribute() not in (pcbnew.PAD_ATTRIB_SMD,pcbnew.PAD_ATTRIB_PTH):continue
        if item.GetClass()=='ZONE' and not item.IsFilled():raise ValueError('native_retained_port_fill_unknown')
        uid=force._uid(item)
        if uid in material:raise ValueError('ambiguous_native_retained_port_identity')
        material[uid]=item
    graph=pcbnew.CONNECTIVITY_DATA()
    for item in material.values():
        tick()
        if not graph.Add(item):raise ValueError('native_retained_port_graph_refused')
    remaining={force._uid(p) for p in ports};groups=[]
    while remaining:
        tick();seed=min(remaining)
        reached={seed}|{force._uid(i) for i in graph.GetConnectedItems(material[seed])}
        if not reached<=material.keys():raise ValueError('native_retained_port_graph_contains_nonmaterial')
        component=sorted(remaining&reached);groups.append(component);remaining.difference_update(component)
    # Native cross-layer connectivity is necessary but not sufficient for
    # retaining a via's old face contact. A quotient tree may bypass a via
    # through its OTHER face, leaving that unchanged barrel dangling when the
    # source tracks are cut. Preserve this explicit via obligation, not an
    # invented extra route to every already-connected PTH pad.
    via_contacts={}
    for via in (p for p in ports if p.GetClass()=='PCB_VIA'):
        witnesses=[];shape=via.GetEffectiveShape(layer_id)
        for uid,item in material.items():
            tick()
            if item.GetClass()=='PCB_VIA' or not item.IsOnLayer(layer_id):continue
            if item.GetClass()=='ZONE':
                if not item.HasFilledPolysForLayer(layer_id):continue
                other=item.GetFilledPolysList(layer_id)
            else:other=item.GetEffectiveShape(layer_id)
            if shape.Collide(other,0):witnesses.append(uid)
        via_contacts[force._uid(via)]=sorted(witnesses)
    return dict(ports={force._uid(p):list(p.GetPosition()) for p in ports},components=sorted(groups),
        omitted_source_track_uuids=sorted(cut),native_retained_material_count=len(material),
        retained_via_face_contacts=via_contacts,
        missing_source_via_face_contacts=sorted(u for u,c in via_contacts.items() if not c),
        maximum_source_tracks=maximum_source_tracks,maximum_ports=maximum_ports,
        source_cut_authorized=False,route_admitted=False,new_capacity_credited=False,release_authority=False)


def construct(board,source,*,board_hint,source_track_uuids,allow_locked_track_uuids=(),
        maximum_source_tracks=32,maximum_ports=8,maximum_edge_attempts=64,
        timeout_s=60.,per_edge_timeout_s=4.,conservative_cross_layer_proposals=True):
    """Build a native-feasible tree on an exact private source snapshot.

    Try real cross-component port pairs in distance order, not one immutable
    geometric MST. Failed bounded searches are local observations, never global
    no-path proofs. Recompute actual retained connectivity after every REAL
    addition, with unchanged native/outline/field-search guards and explicit
    fine interior grids. Source tracks/poses are never removed or changed.

    On refusal, roll back every proposed addition. On success the caller must
    still perform a separately authorized exact source cut, native DRC, whole
    current/field/partition and absolute-cut receiving. Search pruning grants
    neither shielding nor route/current/fabrication qualification.
    """
    from pathlib import Path
    import pcbnew
    import cec_force_current as force
    import cec_field_coupling as field
    import cec_field_search as field_search
    import cec_ordinary_route_receiving as ordinary
    import cec_fr as fr
    import cec_route_quality as quality
    from cec_native_items import discard_items
    result=dict(schema=1,scope='bounded_native_feasible_ordinary_component_tree_construction',
        ok=False,complete=False,errors=[],attempts=[],added_track_uuids=[],
        source_tracks_retired=False,source_cut_authorized=False,route_admitted=False,
        new_capacity_credited=False,shielding_qualified=False,release_authority=False,no_path_proof=False)
    before=field._field_snapshot_inventory(board);added=[];started=time.monotonic()
    try:
        if (type(board_hint) is not str or not board_hint
                or type(maximum_edge_attempts) is not int or not 1<=maximum_edge_attempts<=128
                or type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=60.
                or type(per_edge_timeout_s) not in (int,float) or not math.isfinite(per_edge_timeout_s)
                or not 0<per_edge_timeout_s<=10. or type(conservative_cross_layer_proposals) is not bool):
            raise ValueError('explicit_bounded_native_ordinary_tree_construction_required')
        deadline=started+timeout_s;source=Path(source).resolve();family=force._family(source,board_hint)
        epoch=force._code_identity();parent=pcbnew.LoadBoard(str(source))
        if before!=field._field_snapshot_inventory(parent):
            raise ValueError('exact_private_ordinary_source_geometry_required')
        ids=ordinary._ids(source_track_uuids,'native_tree_source_track_inventory',128)
        permissions=ordinary._ids(allow_locked_track_uuids,'native_tree_locked_track_inventory',128)
        live={force._uid(t):t for t in board.GetTracks()}
        if not ids or not ids<=live.keys() or not permissions<=ids:
            raise ValueError('literal_source_tree_track_scope_required')
        selected=[live[u] for u in sorted(ids)];net=str(selected[0].GetNetname());layer=int(selected[0].GetLayer())
        if (any(t.GetClass()!='PCB_TRACK' or str(t.GetNetname())!=net or int(t.GetLayer())!=layer
                or t.GetParentGroup() is not None or t.IsLocked() and force._uid(t) not in permissions for t in selected)
                or len({t.GetWidth() for t in selected})!=1 or not 0<selected[0].GetWidth()<=350000
                or ids!={force._uid(t) for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'
                    and str(t.GetNetname())==net and int(t.GetLayer())==layer}
                or net not in ordinary.eligible_nets(parent,source,board_hint)):
            raise ValueError('complete_positive_ordinary_uniform_ungrouped_face_scope_required')
        initial=retained_port_components(board,net,layer,sorted(ids),
            maximum_source_tracks=maximum_source_tracks,maximum_ports=maximum_ports)
        result['initial_native_components']=initial
        width=int(selected[0].GetWidth());code=selected[0].GetNetCode()
        resolver=fr._project_netclass_resolver(str(source))
        clearance=max(parent.GetDesignSettings().m_MinClearance,
            round(float((resolver(net) or {}).get('clearance',0))*1e6))
        guard=field_search.PlanarSearchGuard(board,net,netclass_resolver=resolver,board_hint=board_hint,
            conservative_cross_layer_proposals=conservative_cross_layer_proposals)
        tried=set();cache={}
        while True:
            if time.monotonic()>=deadline:raise ValueError('native_component_tree_construction_lease_exhausted')
            current=retained_port_components(board,net,layer,sorted(ids),
                maximum_source_tracks=maximum_source_tracks,maximum_ports=maximum_ports)
            missing=set(current['missing_source_via_face_contacts'])
            if len(current['components'])==1 and not missing:
                result['final_native_components']=current;break
            labels={u:i for i,c in enumerate(current['components']) for u in c};ports=current['ports']
            ordered=sorted(ports)
            choices=sorted((labels[u]==labels[v],sum((ports[u][j]-ports[v][j])**2 for j in (0,1)),u,v)
                for i,u in enumerate(ordered) for v in ordered[i+1:]
                if (labels[u]!=labels[v] or u in missing or v in missing) and (u,v) not in tried)
            if not choices or len(tried)>=maximum_edge_attempts:
                raise ValueError('bounded_native_component_pairs_exhausted_not_no_path_proof')
            same_component,_,u,v=choices[0];tried.add((u,v));first,last=[pcbnew.VECTOR2I(*ports[q]) for q in (u,v)]
            row=dict(ports=[u,v],start_nm=list(first),end_nm=list(last),
                components_before=len(current['components']),status='searching',
                missing_via_face_contacts_before=sorted(missing),
                purpose='preserve_source_via_face_contact' if same_component else 'join_native_components')
            result['attempts'].append(row);diagnostics={}
            with force._thermal_hint(board_hint):
                legs=fr._guarded_profiled_lastmile_legs(board,first,last,width,layer,clearance,code,
                    lambda a,b,r:fr._edge_leg_clear(board,a,b,r),foreign_cache=cache,
                    deadline_monotonic=min(deadline,time.monotonic()+per_edge_timeout_s),
                    maze_margin_mm=2.,allow_maze=True,refine_maze=True,
                    refinement_grids_mm=(.2,.1),endpoint_detail_grid_mm=.1,compact_phase_jogs=True,
                    run_guard=lambda a,b,w:guard(a,b,w,layer),search_diagnostics=diagnostics)
            # Persist bounded decision telemetry, not megabytes of duplicate
            # lattice frontiers per failed pair. The unchanged native predicate
            # remains the only geometry guard, not this diagnostic subset.
            row['maze_tiers']=[dict(grid_mm=t.get('grid_mm'),path_found=t.get('path_found'),
                path_accepted=t.get('path_accepted'),endpoint_detail_grid_mm=t.get('endpoint_detail_grid_mm'),
                stop=(t.get('native_endpoint_check') or {}).get('stop'),
                search_counts=(t.get('native_endpoint_check') or {}).get('search_counts'),
                nearest_expanded_point=(t.get('native_endpoint_check') or {}).get('nearest_expanded_point'))
                for t in diagnostics.get('maze_tiers',[])[:8]]
            if not legs:row['status']='bounded_search_unavailable';continue
            path=quality.compact_collinear_path([list(legs[0][0])]+[list(b) for a,b,w in legs])
            if any(w!=width for a,b,w in legs) or not all(
                    quality.is_canonical_stroke(a,b,tolerance_nm=0)
                    and fr._edge_leg_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width//2)
                    and fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width,layer,clearance,{code})
                    and guard(pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*b),width,layer) is True
                    for a,b in zip(path,path[1:])):
                raise ValueError('native_tree_returned_path_not_canonical_full_width_field_guarded')
            for a,b in zip(path,path[1:]):
                t=selected[0].Duplicate();t.m_Uuid.Clone(pcbnew.KIID())
                t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*b));board.Add(t);added.append(t)
            after=retained_port_components(board,net,layer,sorted(ids),
                maximum_source_tracks=maximum_source_tracks,maximum_ports=maximum_ports)
            if (len(after['components'])>=len(current['components'])
                    and not set(after['missing_source_via_face_contacts'])<missing):
                raise ValueError('proposed_native_branch_did_not_join_components_or_restore_via_face')
            row.update(status='native_components_joined',path_nm=path,components_after=len(after['components']),
                missing_via_face_contacts_after=after['missing_source_via_face_contacts'])
        after=field._field_snapshot_inventory(board)
        if any(after.get(k)!=v for k,v in before.items()):
            raise ValueError('native_tree_modified_preexisting_source_geometry')
        if epoch!=force._code_identity() or family!=force._family(source,board_hint):
            raise ValueError('native_tree_source_or_code_changed')
        result.update(ok=True,complete=True,added_track_uuids=[force._uid(t) for t in added],
            field_search_pruning=guard.report(),actual_source_tracks_unchanged=True,
            original_source_and_code_unchanged=True,construction_only=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
        if added:discard_items(board,added)
        exact=before==field._field_snapshot_inventory(board)
        result['all_proposed_additions_rolled_back_exactly']=exact
        if not exact:result['errors'].append('native_tree_rollback_did_not_restore_private_source')
    result['elapsed_s']=time.monotonic()-started
    return result
