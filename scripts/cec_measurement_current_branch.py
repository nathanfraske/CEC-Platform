"""Source-typed non-load measurement leaves, never power capacity credit.

A global current-path failure must remain a failure, but it must not turn
every positively identified high-impedance input stub into a full-load trunk.
Only exact endpoint-linear manufacturer measurement leaves meeting their
ordinary project/process floor may be omitted. Native source/sink partitions
must be identical after their collective removal, even for an already open
rail. No current split, numeric input load, zone/barrel capacity or release
qualification is inferred. Missing/partial evidence retains the old strict
width obligation.
"""
import math
import time

import pcbnew
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fr as fr
import cec_measurement_leaf as leaf
import cec_route_dimensions as dimensions


def plan(board,pad_uuid,*,timeout_s=2.):
    """Existing manufacturer input semantics plus native layer transitions.

    Keep the surface-only retirement planner unchanged. A plated exclusive
    input leaf is current-check evidence, not permission to rip up barrels or
    a way to assign a typical bias current as a rail-load maximum.
    """
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10):
        raise ValueError('bounded_native_measurement_branch_plan_required')
    deadline=time.monotonic()+timeout_s
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    roots=[p for p in pads if force._uid(p)==pad_uuid]
    if len(pads)>16384 or len(roots)!=1:
        raise ValueError('native_measurement_source_land_unknown')
    root=roots[0];owner=root.GetParentFootprint()
    if owner.IsDNP():raise ValueError('dnp_measurement_input_has_no_exemption')
    try:
        return leaf.plan(board,pad_uuid,timeout_s=timeout_s)
    except ValueError:
        pass
    import cec_pair_semantics as semantics
    from cec_return_escape import smd_surface_layer
    from cec_resistive_monitor_branch import _native_exclusive_plan
    manufacturer=roles.footprint_contract(owner)
    pair=semantics.footprint_input_contract(owner)
    if (owner.IsDNP() or not manufacturer or not pair
            or manufacturer['pins'].get(str(root.GetNumber()))!='measurement'
            or str(root.GetNumber()) not in pair[1] or root.GetNetCode()<=0
            or root.HasHole() or root.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
            or smd_surface_layer(root) is None):
        raise ValueError('manufacturer_typed_native_measurement_land_required')
    q=_native_exclusive_plan(board,pad_uuid,deadline=deadline)
    q['scope']='source_typed_native_measurement_branch_current_only'
    q['manufacturer_source']=manufacturer['source']
    return q


def _partitions(pads,material,deadline):
    graph=pcbnew.CONNECTIVITY_DATA()
    for item in [*pads,*material]:
        if time.monotonic()>=deadline or not graph.Add(item):raise ValueError('measurement_branch_native_graph_unknown')
    remaining={force._uid(p) for p in pads};parts=[]
    for pad in pads:
        if time.monotonic()>=deadline:raise ValueError('measurement_branch_native_deadline')
        uid=force._uid(pad)
        if uid not in remaining:continue
        reached={uid}|{force._uid(i) for i in graph.GetConnectedItems(pad)}
        part=tuple(sorted(reached & remaining));parts.append(part);remaining-=set(part)
    return tuple(sorted(parts))


def _package_input_tree(board,pad_uuid,domain,*,deadline,allow_layer_branches=False,
                        allow_resolved_multiowner_inputs=False):
    """A bounded package nonload tree with ONE actual current-pad tap.

    A voltage monitor can share its package-local node with a differential
    input. The old single-departure walk refused that entirely typed fork.
    This is current-check classification ONLY, never retirement or Kelvin
    authority. Every encountered land is manufacturer-typed, all external
    contact is enclosed by one native source/sink land, and the caller still
    removes the complete cohort and compares actual current partitions.
    """
    from cec_return_escape import smd_surface_layer
    import cec_fab_profile as fab
    import cec_pair_semantics as semantics
    import cec_kelvin_copper_cut as cut
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    root=next(p for p in pads if force._uid(p)==pad_uuid)
    owner=root.GetParentFootprint();model=roles.footprint_contract(owner)
    pair=semantics.footprint_input_contract(owner);surface=smd_surface_layer(root)
    if (not model or not pair or owner.IsDNP() or surface is None
            or model['pins'].get(str(root.GetNumber()))!='measurement'
            or str(root.GetNumber()) not in pair[1] or domain.get('complete') is not True
            or owner.GetReference() in domain.get('authority_refs',())):
        raise ValueError('typed_same_package_input_tree_required')
    if (type(allow_layer_branches) is not bool or type(allow_resolved_multiowner_inputs) is not bool):
        raise ValueError('explicit_native_layer_tree_mode_required')
    models={force._uid(owner):model};input_owners={force._uid(owner):owner}
    material=[i for i in [*pads,*board.GetTracks(),*[z for z in board.Zones() if not z.GetIsRuleArea()]]
        if i.GetNetCode()==root.GetNetCode() and (allow_layer_branches or i.IsOnLayer(surface))]
    if len(material)>4096:raise ValueError('package_input_tree_inventory_bound')
    groups=list(board.Groups());group_owners={}
    for group in groups:
        for item in group.GetItems():
            group_owners.setdefault(force._uid(item),[]).append(group)
    pofv_groups=[g for g in groups if g.GetName()==fr.LOCAL_POFV_SIGNAL_VIA_GROUP]
    pofv_cache={}
    selected={};boundaries={};pending=[root]
    def tick():
        if time.monotonic()>=deadline:raise ValueError('package_input_tree_deadline')
    copper=set(map(int,board.GetEnabledLayers().CuStack()))
    def item_layers(item):return copper.intersection(map(int,item.GetLayerSet().CuStack()))
    def native(item,layer):
        if item.GetClass()=='ZONE':
            if not item.IsFilled():raise ValueError('package_input_tree_fill_unknown')
            return item.GetFilledPolysList(layer)
        return item.GetEffectiveShape(layer)
    shapes={(force._uid(i),l):native(i,l) for i in material for l in item_layers(i)}
    def touching(a,b):
        return any(shapes[force._uid(a),l].Collide(shapes[force._uid(b),l],0)
            for l in item_layers(a)&item_layers(b))
    while pending:
        tick();item=pending.pop();uid=force._uid(item)
        if uid in selected:continue
        kind=item.GetClass()
        item_groups=group_owners.get(uid,())
        if item_groups:
            # The process group owns exact filled/capped barrels, not the
            # current carried by a net. Re-prove this live via and reject
            # ambiguous owners, forged track groups and stale local seats.
            # This exception remains classification-only: no group member
            # obtains retirement, Kelvin or ampacity authority.
            if (not allow_layer_branches or kind!='PCB_VIA' or len(item_groups)!=1
                    or len(pofv_groups)!=1 or item_groups[0].GetName()!=fr.LOCAL_POFV_SIGNAL_VIA_GROUP
                    or any(i.GetClass()!='PCB_VIA' for i in item_groups[0].GetItems())
                    or not fab.local_pofv_via_decision(board,item,cache=pofv_cache)[0]):
                raise ValueError('package_input_tree_grouped_material')
        if kind=='PAD':
            parent=item.GetParentFootprint();parent_uid=force._uid(parent)
            if parent_uid not in models and allow_resolved_multiowner_inputs:
                other_model=roles.footprint_contract(parent)
                if (parent.IsDNP() or parent.GetReference() in domain.get('authority_refs',())
                        or not other_model or not semantics.footprint_input_contract(parent)):
                    raise ValueError('package_input_tree_untyped_land')
                models[parent_uid]=other_model;input_owners[parent_uid]=parent
            if (parent_uid not in models or item.HasHole()
                    or item.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or smd_surface_layer(item)!=surface
                    or models[parent_uid]['pins'].get(str(item.GetNumber()))!='measurement'):
                raise ValueError('package_input_tree_untyped_land')
        elif kind=='PCB_TRACK':
            a,b=tuple(item.GetStart()),tuple(item.GetEnd())
            if ((not allow_layer_branches and item.GetLayer()!=surface) or not 0<item.GetWidth()<=350000 or item.GetLength()<=0
                    or a[0]!=b[0] and a[1]!=b[1] and abs(a[0]-b[0])!=abs(a[1]-b[1])):
                raise ValueError('package_input_tree_noncanonical_thin_track')
        elif kind=='PCB_VIA' and allow_layer_branches:
            limits=dimensions.board_limits(board);dia=item.GetWidth(item.TopLayer());drill=item.GetDrillValue()
            ordinary=bool(drill>=round(limits['via_drill']*1e6)
                and dia>=round(limits['via_diameter']*1e6)
                and (dia-drill)/2>=round(limits['annular']*1e6))
            if (int(item.GetViaType())!=int(pcbnew.VIATYPE_THROUGH)
                    or int(item.TopLayer())!=int(pcbnew.F_Cu) or int(item.BottomLayer())!=int(pcbnew.B_Cu)
                    or not ordinary and not fab.local_pofv_via_decision(board,item)[0]):
                raise ValueError('package_input_tree_declared_through_barrel_required')
        else:raise ValueError('package_input_tree_surface_only')
        selected[uid]=item
        if len(selected)>(48 if allow_resolved_multiowner_inputs else 24):
            raise ValueError('package_input_tree_scope_bound')
        for other in material:
            tick();other_uid=force._uid(other)
            if other_uid in selected or not touching(item,other):continue
            same_owner=False
            if other.GetClass()=='PAD':
                other_parent=other.GetParentFootprint()
                same_owner=force._uid(other_parent)==force._uid(owner)
                if allow_resolved_multiowner_inputs and not same_owner:
                    other_model=roles.footprint_contract(other_parent)
                    # A current terminal is always a boundary. Neither a
                    # shared net nor a monitor-like refdes may turn it into
                    # an exempt input. Every additional owner is retyped.
                    same_owner=bool(other_parent.GetReference() not in domain.get('authority_refs',())
                        and not other_parent.IsDNP() and other_model
                        and semantics.footprint_input_contract(other_parent)
                        and other_model['pins'].get(str(other.GetNumber()))=='measurement')
            thin=other.GetClass()=='PCB_TRACK' and 0<other.GetWidth()<=350000
            barrel=allow_layer_branches and other.GetClass()=='PCB_VIA'
            if same_owner or thin or barrel:pending.append(other)
            else:boundaries[other_uid]=other
    local_pads=[i for i in selected.values() if i.GetClass()=='PAD']
    tracks=[i for i in selected.values() if i.GetClass()=='PCB_TRACK']
    vias=[i for i in selected.values() if i.GetClass()=='PCB_VIA']
    pin_ids={(force._uid(p.GetParentFootprint()),p.GetNumber()) for p in local_pads}
    if (not 1<=len(local_pads)<=8 or len(pin_ids)!=len(local_pads)
            or not 1<=len(tracks)<=(32 if allow_resolved_multiowner_inputs else 16)
            or len(vias)>(8 if allow_resolved_multiowner_inputs else 4)
            or sum(t.GetLength() for t in tracks)>(64000000 if allow_resolved_multiowner_inputs else 24000000)):
        raise ValueError('bounded_typed_package_inputs_and_tree_required')
    authority=force._authority_pads(board,str(root.GetNetname()),domain)
    tapped=[p for p in authority if force._uid(p) in boundaries]
    if len(tapped)!=1:raise ValueError('single_native_current_land_tap_required')
    tap=tapped[0];work=cut._Work(deadline)
    if allow_resolved_multiowner_inputs:
        if not 2<=len(input_owners)<=4:raise ValueError('resolved_multiowner_input_tree_requires_distinct_packages')
        import cec_sense_topology as sense
        lineage=sense.board_evidence(board,anchor_refs=domain['authority_refs'])
        for package in input_owners.values():
            tick()
            witnesses=[r for r in lineage['details'] if r.get('ok') is True
                and r['ref']==package.GetReference()]
            if len(witnesses)!=1:raise ValueError('multiowner_input_source_topology_not_unique')
            legs=[q for q in sense.placement_segments(witnesses[0])
                if q['start']['ref']==package.GetReference()
                and q['end']==dict(ref=tap.GetParentFootprint().GetReference(),pad=str(tap.GetNumber()))
                and q['net']==str(root.GetNetname())]
            if len(legs)!=1 or not any(force._uid(p.GetParentFootprint())==force._uid(package)
                    and str(p.GetNumber())==str(legs[0]['start']['pad']) for p in local_pads):
                raise ValueError('multiowner_input_does_not_resolve_to_same_exact_shunt_land')
    for external in boundaries.values():
        tick()
        for conductor in [*tracks,*vias]:
            for layer in item_layers(external)&item_layers(conductor):
                shape=(cut._poly(external.GetFilledPolysList(layer),work) if external.GetClass()=='ZONE'
                    else cut._shape(external,layer,False,work))
                overlap=shape.intersection(cut._shape(conductor,layer,False,work))
                aperture=cut._shape(tap,layer,True,work).buffer(1000) if tap.IsOnLayer(layer) else None
                if not overlap.is_empty and (aperture is None or not overlap.difference(aperture).is_empty):
                    raise ValueError('package_input_tree_acquires_external_contact')
    # Centreline endpoints must form a real tree, not a same-net mesh or
    # invented high-impedance bypass between two source/sink contacts.
    nodes={};edges=[];contained_tracks=[]
    def node(point,layer):
        on=[force._uid(p) for p in [*local_pads,tap]
            if p.IsOnLayer(layer) and shapes[force._uid(p),layer].Collide(pcbnew.VECTOR2I(*point),0)]
        if len(on)>1:raise ValueError('package_input_tree_ambiguous_land_contact')
        if on:return ('pad',on[0])
        barrels=[force._uid(v) for v in vias if tuple(v.GetPosition())==point and v.IsOnLayer(layer)]
        if len(barrels)>1:raise ValueError('package_input_tree_ambiguous_barrel_contact')
        return ('via',barrels[0]) if barrels else ('point',layer,*point)
    for track in tracks:
        a,b=node(tuple(track.GetStart()),int(track.GetLayer())),node(tuple(track.GetEnd()),int(track.GetLayer()))
        if a==b:
            # Endpoints collapse to a land-node, not a circuit loop, when
            # the ENTIRE manufactured conductor is contained in that one
            # real input/tap land. A centreline-only test would hide caps or
            # excursions outside it. Keep this material in the classified
            # cohort; only omit its redundant graph edge, never its copper.
            land=next((p for p in [*local_pads,tap]
                if a==('pad',force._uid(p))),None)
            layer=int(track.GetLayer())
            if (land is None or not land.IsOnLayer(layer)
                    or not cut._shape(track,layer,False,work).difference(
                        cut._shape(land,layer,True,work)).is_empty):
                raise ValueError('package_input_tree_redundant_loop')
            contained_tracks.append(force._uid(track));continue
        edges.append((a,b));nodes.setdefault(a,set()).add(b);nodes.setdefault(b,set()).add(a)
    # A filled/capped barrel fully inside a real SMD land is itself the
    # endpoint's surface contact. A fake extra track inside that land is
    # neither necessary nor a second layer transition. Represent only the
    # proved native via-to-land edge; never infer one from proximity.
    pad_contacts={}
    for via in vias:
        via_node=('via',force._uid(via));contacts=[]
        if via_node not in nodes:continue
        for pad in [*local_pads,tap]:
            for layer in item_layers(via)&item_layers(pad):
                tick()
                if (touching(via,pad)
                        and fab.local_pofv_via_decision(board,via,cache=pofv_cache)[0]
                        and cut._shape(via,layer,False,work).difference(
                            cut._shape(pad,layer,False,work)).is_empty):
                    contacts.append((pad,layer));break
        if len(contacts)>1:raise ValueError('package_input_tree_ambiguous_barrel_land')
        if contacts:
            pad,layer=contacts[0];land_node=('pad',force._uid(pad))
            edges.append((via_node,land_node));nodes[via_node].add(land_node)
            nodes.setdefault(land_node,set()).add(via_node)
            pad_contacts[force._uid(via)]=layer
    reached=set();todo=[('pad',pad_uuid)]
    while todo:
        point=todo.pop()
        if point in reached:continue
        reached.add(point);todo.extend(nodes.get(point,()))
    if (reached!=set(nodes) or len(edges)!=len(nodes)-1
            or {('pad',force._uid(p)) for p in [*local_pads,tap]}-reached
            or any(n[0]=='point' and len(peers)==1 for n,peers in nodes.items())):
        raise ValueError('package_input_tree_not_one_endpoint_tree')
    if any(len(nodes.get(('via',force._uid(v)),()))!=2 or len({t.GetLayer() for t in tracks
            if force._uid(v) in (node(tuple(t.GetStart()),int(t.GetLayer()))[1],
                node(tuple(t.GetEnd()),int(t.GetLayer()))[1])}
                |({pad_contacts[force._uid(v)]} if force._uid(v) in pad_contacts else set()))!=2 for v in vias):
        raise ValueError('package_input_tree_exclusive_layer_transition_required')
    ids=sorted(force._uid(t) for t in tracks);via_ids=sorted(force._uid(v) for v in vias)
    return dict(schema=1,scope=('typed_resolved_multi_package_input_tree_current_only' if allow_resolved_multiowner_inputs
        else 'typed_same_package_native_layer_tree_current_only' if vias
        else 'typed_same_package_nonload_tree_current_only'),pad_uuid=pad_uuid,
        net=str(root.GetNetname()),track_uuids=ids,via_uuids=via_ids,native_removed_material_uuids=sorted(ids+via_ids),
        track_widths_by_uuid={force._uid(t):(int(t.GetLayer()),int(t.GetWidth())) for t in tracks},
        fully_land_contained_track_uuids=sorted(contained_tracks),
        leaf_pad_uuids=sorted(force._uid(p) for p in local_pads),boundary_uuids=sorted(boundaries),
        source_length_mm=sum(t.GetLength() for t in tracks)/1e6,
        manufacturer_source=model['source'],retirement_authority=False,release_authority=False,
        current_path_qualified=False,new_numeric_load_assumed=False)


def inventory(board,source,domains,*,timeout_s=2.,max_leaves=64):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s)
            or not 0<timeout_s<=10 or type(max_leaves) is not int or not 1<=max_leaves<=64):
        raise ValueError('bounded_typed_measurement_branch_inventory_required')
    deadline=time.monotonic()+timeout_s;resolver=fr._project_netclass_resolver(str(source))
    tracks={force._uid(t):t for t in board.GetTracks()};cohorts={};refusals=[];count=0
    for fp in board.GetFootprints():
        try:model=roles.footprint_contract(fp)
        except (ValueError,RuntimeError) as exc:
            refusals.append(dict(ref=fp.GetReference(),reason=str(exc)))
            continue
        if not model:continue
        for pad in fp.Pads():
            net=str(pad.GetNetname());domain=domains.get(net,{})
            if model['pins'].get(str(pad.GetNumber()))!='measurement' or domain.get('complete') is not True:continue
            if time.monotonic()>=deadline or count>=max_leaves:
                return dict(uuids=[],proofs=[],refusals=refusals,complete=False,release_authority=False)
            count+=1
            try:
                if fp.GetReference() in domain['authority_refs']:
                    raise ValueError('measurement_input_is_declared_current_terminal')
                if fp.IsDNP():raise ValueError('dnp_measurement_input_has_no_exemption')
                attempts=[]
                try:
                    proposal=_package_input_tree(board,force._uid(pad),domain,deadline=deadline)
                except ValueError as exc:
                    attempts.append(dict(stage='surface_package_tree',reason=str(exc)))
                    try:
                        proposal=_package_input_tree(board,force._uid(pad),domain,deadline=deadline,allow_layer_branches=True)
                    except ValueError as exc:
                        attempts.append(dict(stage='native_layer_package_tree',reason=str(exc)))
                        try:
                            proposal=_package_input_tree(board,force._uid(pad),domain,deadline=deadline,
                                allow_layer_branches=True,allow_resolved_multiowner_inputs=True)
                        except (ValueError,RuntimeError) as exc:
                            attempts.append(dict(stage='resolved_multiowner_input_tree',reason=str(exc)))
                            try:
                                proposal=plan(board,force._uid(pad),timeout_s=max(.001,deadline-time.monotonic()))
                            except (ValueError,RuntimeError) as exc:
                                attempts.append(dict(stage='exclusive_native_leaf',reason=str(exc)))
                                refusals.append(dict(pad_uuid=force._uid(pad),net=net,
                                    reason=str(exc),attempts=attempts))
                                continue
                width_basis=dimensions.nonload_measurement_width(board,source,net,
                    parent_spec=resolver(net) or {})
                floor=width_basis['width_nm']
                widths=[w for _,w in proposal.get('track_widths_by_uuid',{}).values()]
                if not widths:widths=[proposal['width_nm']]
                if any(w<floor for w in widths):raise ValueError('measurement_branch_below_project_process_floor')
                proposal['nonload_width_basis']=width_basis
                cohorts.setdefault(net,[]).append(proposal)
            except (ValueError,RuntimeError) as exc:
                refusals.append(dict(pad_uuid=force._uid(pad),net=net,reason=str(exc)))
    admitted=set();proofs=[]
    for net,proposals in sorted(cohorts.items()):
        try:
            ids={u for p in proposals for u in p['track_uuids']}
            cut_ids=ids|{u for p in proposals for u in p.get('native_removed_material_uuids',[])}
            pads=force._authority_pads(board,net,domains[net]);pad_ids={force._uid(p) for p in pads}
            material=[p for fp in board.GetFootprints() for p in fp.Pads()
                if p.GetNetname()==net and force._uid(p) not in pad_ids]
            material += [t for t in tracks.values() if t.GetNetname()==net]
            material += [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()==net]
            if not pads or len(material)+len(pads)>4096:raise ValueError('measurement_branch_native_inventory_bound')
            before=_partitions(pads,material,deadline)
            after=_partitions(pads,[i for i in material if force._uid(i) not in cut_ids],deadline)
            if before!=after:raise ValueError('measurement_removal_changes_current_terminal_partitions')
            admitted|=ids
            proofs.append(dict(net=net,leaf_pad_uuids=sorted(p['pad_uuid'] for p in proposals),
                track_uuids=sorted(ids),native_current_terminal_partitions=before,
                native_exclusive_branch_material_uuids=sorted(cut_ids),
                nonload_width_bases=[dict(pad_uuid=p['pad_uuid'],
                    **p['nonload_width_basis']) for p in sorted(proposals,key=lambda p:p['pad_uuid'])],
                fully_land_contained_track_uuids=sorted({u for p in proposals
                    for u in p.get('fully_land_contained_track_uuids',[])}),
                partitions_unchanged_after_collective_removal=True,
                manufacturer_nonload_role=True,new_numeric_load_assumed=False,
                current_path_qualified=False,release_authority=False))
        except (ValueError,RuntimeError) as exc:
            refusals.append(dict(net=net,reason=str(exc)))
    # No partially timed-out portfolio may grant an exemption.
    complete=time.monotonic()<deadline
    return dict(uuids=sorted(admitted) if complete else [],proofs=proofs if complete else [],
        refusals=refusals,complete=complete,current_path_qualified=False,release_authority=False)
