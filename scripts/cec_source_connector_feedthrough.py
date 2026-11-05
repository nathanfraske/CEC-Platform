"""Receive a Source-canonical, existing plated sideband feedthrough.

CEC pin numbering is a Source-owned remap, not a publisher pin-number claim.
The selected connector catalog, current hierarchical symbols/netlist and local
remap records jointly identify the interface. No passive pin, net name or
Default class grants a current exemption. Approximate inherited footprints,
barrel/load/thermal/fabrication qualification and all shared gates stay open.
"""
import ast
import math
from pathlib import Path
import time


def _need(value,reason):
    if not value:raise ValueError(reason)


CATALOG={
    '2191161161':dict(manufacturer='Molex',footprint='cec:CEC_12V2x6_Horizontal',
        source_symbol='cec:CEC_CONN_12V2x6',
        source_pin_roles={'13':'SENSE0','14':'SENSE1','15':'PWR_STABLE','16':'CBL_PRES'},
        publisher_source='https://www.molex.com/en-us/products/series-chart/219116',
        publisher_scope='selected part is through-hole, 16 circuits, 12 power and 4 signal',
        numbering_scope='CEC Source remap only; not publisher physical-pin numbering'),
}


def _role_records():
    """Fresh local Source remap and intent, independently of board/net/ref names."""
    import cec_force_current as force
    root=Path(__file__).resolve().parent.parent
    footprint=root/'lib/cec.pretty/CEC_12V2x6_Horizontal.kicad_mod'
    generator=root/'scripts/gen-modules.py'
    text=footprint.read_text()
    _need(all(s in text for s in ('2191161161','2191160001-SD',
        '13-16 = sideband S1..S4 (SENSE0/SENSE1/CARD_PWR_STABLE/CARD_CBL_PRES#)')),
        'current_Source_connector_remap_record_missing')
    tables=[]
    for node in ast.walk(ast.parse(generator.read_text())):
        if isinstance(node,ast.Assign)and any(isinstance(n,ast.Name)and n.id=='SIDEBAND'for n in node.targets):
            tables.append(ast.literal_eval(node.value))
    _need(len(tables)==1 and len(tables[0])==4
        and {str(pin):role for role,pin,_ in tables[0]}==CATALOG['2191161161']['source_pin_roles'],
        'current_Source_sideband_intent_table_mismatch')
    return {str(p):force._hash(p)for p in (footprint,generator)}


def _parts(board,net,deadline):
    """All actual conductors, with no zone-owner or net-name connectivity credit."""
    import pcbnew
    import cec_force_current as force
    _need(not any(z.GetNetname()==net and not z.GetIsRuleArea()for z in board.Zones()),
        'feedthrough_target_zone_ownership_not_supported')
    items=[*(p for f in board.GetFootprints()for p in f.Pads()),*board.GetTracks()]
    items=[i for i in items if i.GetNetname()==net]
    _need(0<len(items)<=2048,'bounded_actual_feedthrough_material_required')
    graph=pcbnew.CONNECTIVITY_DATA();remaining={force._uid(i):i for i in items};result=[]
    _need(len(remaining)==len(items),'unique_feedthrough_native_identity_required')
    for item in items:
        _need(time.monotonic()<deadline and graph.Add(item),'feedthrough_native_graph_unknown')
    while remaining:
        _need(time.monotonic()<deadline,'feedthrough_partition_deadline')
        seed=remaining[min(remaining)]
        reached=({force._uid(seed)}|{force._uid(i)for i in graph.GetConnectedItems(seed)})&remaining.keys()
        _need(reached,'nonempty_feedthrough_component_required');result.append(set(reached))
        for uid in reached:del remaining[uid]
    return result


def _canonical(board,source,hint,pad_uuids,deadline):
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_source_ground_leaf as roles
    import cec_source_no_connect as nc
    import cec_quiet_signal_requests as pins
    import cec_current_topology as current
    import cec_pair_semantics as pairs
    import cec_synth_pipeline as synth
    from cec_footprint_fields import footprint_properties
    _need(Path(board.GetFileName()).resolve()==source,'exact_saved_feedthrough_Source_required')
    records=_role_records();root=nc._root(board,hint)
    _need(root is not None,'current_canonical_feedthrough_hierarchy_required')
    files,hashes,instances=roles._hierarchy(Path(root).resolve(),deadline)
    tree,exporter=roles._export(Path(root).resolve(),deadline)
    components,nets,node_net=roles._tables(tree)
    _need(type(exporter)is dict and Path(exporter.get('exporter','')).is_file()
        and force._hash(Path(exporter['exporter']))==exporter.get('exporter_sha256'),
        'fresh_bound_feedthrough_exporter_required')
    allpads=[p for f in board.GetFootprints()for p in f.Pads()]
    by_id={force._uid(p):p for p in allpads}
    _need(len(by_id)==len(allpads)and set(pad_uuids)<=by_id.keys(),'exact_existing_feedthrough_lands_required')
    ends=[by_id[u]for u in pad_uuids];net=ends[0].GetNetname()
    _need(net and net!='GND'and all(p.GetNetCode()>0 and p.GetNetname()==net for p in ends),
        'same_exact_live_feedthrough_net_required')
    protected={n for pair in fr._board_kelvin_pairs(board)for n in pair}
    protected|={n for _,a,b in pairs.coupled_pair_names(board)for n in(a,b)}
    protected|={q[k]for q in pairs.analog_input_pairs(board)for k in('p','n')}
    protected|=set(pairs.unresolved_current_monitor_nets(board))
    with force._thermal_hint(hint):
        protected|=set(current.board_current_domains(board,hint))
        _need(synth.spec_net_current_contract(hint,net)is None,'feedthrough_cannot_own_rated_current_domain')
    _need(net not in protected,'feedthrough_cannot_own_ground_power_pair_or_measurement_domain')
    native=[p for p in allpads if p.GetNetname()==net]
    _need(2<=len(native)<=8 and nets.get(net)=={(p.GetParentFootprint().GetReference(),p.GetNumber())for p in native},
        'exact_complete_Source_feedthrough_net_required')
    identities={};witnesses=[]
    for pad in native:
        _need(time.monotonic()<deadline,'feedthrough_Source_scope_deadline')
        fp=pad.GetParentFootprint();ref=fp.GetReference();number=pad.GetNumber()
        if ref not in identities:identities[ref]=roles._identity(board,ref,components,instances,deadline)
        identity=identities[ref];actual=pins._source_pin(identity,number,deadline)
        _need(node_net.get((ref,number))==net and pad.GetPinType()in('',actual['type'])
            and pad.GetPinFunction()in('',actual['name']), 'feedthrough_Source_native_pin_contradiction')
        _need(actual['type']not in('power_in','power_out')and not fp.IsDNP(),
            'fitted_nonpower_Source_feedthrough_terminal_required')
        if force._uid(pad)not in pad_uuids:continue
        props=footprint_properties(fp);mpn=props.get('MPN');catalog=CATALOG.get(mpn)
        blocks=[block for tag,block in identity[2].children if tag=='symbol'and roles.sch.prop_value(block,'Reference')==ref]
        exported={synth._val(p,'name',''):synth._val(p,'value','')for p in synth._kids(components[ref],'property')}
        _need(catalog is not None and props.get('Manufacturer')==catalog['manufacturer']
            and len(blocks)==1 and roles.sch.prop_value(blocks[0],'Manufacturer')==catalog['manufacturer']
            and exported.get('Manufacturer')==catalog['manufacturer']
            and fp.GetFPIDAsString()==catalog['footprint']and identity[3]['lib_id']==catalog['source_symbol'],
            'positive_selected_Source_sideband_connector_package_required')
        _need(number in catalog['source_pin_roles']and actual==dict(type='passive',name='SENSE'),
            'actual_Source_sideband_channel_pin_required')
        package_pads=[p for p in fp.Pads()if p.GetNumber()]
        _need(len(package_pads)==16 and {p.GetNumber()for p in package_pads}=={str(i)for i in range(1,17)},
            'complete_actual_selected_connector_package_required')
        for member in package_pads:
            numeric=int(member.GetNumber());wanted='+12V'if numeric<=6 else'GND'if numeric<=12 else'SENSE'
            _need(pins._source_pin(identity,member.GetNumber(),deadline)==dict(type='passive',name=wanted)
                and node_net.get((ref,member.GetNumber()))==member.GetNetname(),
                'complete_canonical_connector_channel_map_required')
        _need(pad.GetAttribute()==pcbnew.PAD_ATTRIB_PTH and pad.HasHole(),
            'actual_existing_plated_feedthrough_land_required')
        witnesses.append(dict(pad_uuid=force._uid(pad),owner_uuid=force._uid(fp),pin=number,
            source_symbol_uuid=identity[3]['uuid'],actual_Source_pin=actual,selected_mpn=mpn,
            manufacturer=props['Manufacturer'],channel=catalog['source_pin_roles'][number],catalog=catalog))
    _need(len(witnesses)==2 and len({w['owner_uuid']for w in witnesses})==2
        and len({(w['selected_mpn'],w['pin'],w['channel'])for w in witnesses})==1,
        'two_distinct_same_part_same_Source_channel_connectors_required')
    resolver=fr._project_netclass_resolver(str(source),board=board);spec=resolver(net)or{}
    _need(str(spec.get('name','')).casefold()not in('power','gnd','ground','kelvin','can','usb','differential','clock','rf','highspeed')
        and spec.get('track_width')and spec.get('clearance'),'authored_nonpower_feedthrough_geometry_required')
    width=max(board.GetDesignSettings().m_TrackMinWidth,math.ceil(float(spec['track_width'])*1e6))
    clearance=max(board.GetDesignSettings().m_MinClearance,math.ceil(float(spec['clearance'])*1e6))
    _need(0<width<500000 and clearance>0,'bounded_positive_feedthrough_Source_geometry_required')
    _need(hashes=={str(p):force._hash(p)for p in files}and records==_role_records(),
        'feedthrough_Source_role_or_hierarchy_epoch_changed')
    return dict(net=net,requested_pad_uuids=list(pad_uuids),witnesses=witnesses,
        source_class=spec['name'],width_nm=width,clearance_nm=clearance,
        canonical_Source=dict(root=str(root),schematic_files_sha256=hashes,exporter=exporter,role_records_sha256=records),
        publisher_numeric_pin_map_claimed=False,Source_numbering_remap_only=True,
        inherited_approximate_footprint_qualified=False,current_authority=False)


def _annular_contact(pad,tracks,face):
    import pcbnew
    import cec_force_current as force
    _need(pad.IsOnLayer(face)and pad.FlashLayer(face),'actual_flashed_feedthrough_channel_required')
    land=pcbnew.SHAPE_POLY_SET();pad.TransformShapeToPolygon(land,face,0,1,pcbnew.ERROR_INSIDE,False)
    hole=pcbnew.SHAPE_POLY_SET();pad.GetEffectiveHoleShape().TransformToPolygon(hole,1,pcbnew.ERROR_OUTSIDE)
    land.BooleanSubtract(hole);incoming=pcbnew.SHAPE_POLY_SET()
    for t in tracks:
        if t.IsOnLayer(face):
            shape=pcbnew.SHAPE_POLY_SET();t.TransformShapeToPolygon(shape,face,0,1,pcbnew.ERROR_INSIDE,False);incoming.BooleanAdd(shape)
    incoming.BooleanIntersection(land)
    _need(incoming.OutlineCount()>0 and incoming.Area()>0,'positive_drill_subtracted_feedthrough_contact_required')
    return dict(pad_uuid=force._uid(pad),layer=face,positive_native_contact_nm2=incoming.Area(),
        actual_drill_subtracted=True,barrel_current_qualified=False)


def _routing_layers(board, net, resolver, *, allow_nonplane_power_role=False):
    """An explicit Source-derived search menu, not plane/reference authority.

    Unknown/unprofiled boards retain the legacy default behavior. Opting in
    must resolve a known profile from this saved Source board, never an
    environment variable, caller layer list or candidate-only property.
    Actual planes, disabled faces and coupled-channel restrictions remain
    excluded by the existing layer resolver; native/field guards still apply.
    """
    import cec_fab_profile as fab
    import cec_fr as fr
    _need(type(allow_nonplane_power_role) is bool,
        'explicit_boolean_Source_nonplane_recovery_policy_required')
    profile = fab.board_profile_name(board)
    if allow_nonplane_power_role:
        _need(profile is not None,
            'nonplane_recovery_requires_known_saved_Source_profile')
    allowed = fr._lastmile_route_layers(board, net_name=net,
        spec=resolver(net) or {}, exclude_front=False,
        allow_nonplane_power_role=allow_nonplane_power_role)
    return dict(scope='Source_profile_nonplane_search_menu_not_reference_authority',
        allow_nonplane_power_role=allow_nonplane_power_role,
        saved_Source_profile=profile, allowed_layer_ids=list(allowed),
        actual_planes_and_disabled_layers_excluded=True,
        current_or_plane_reference_or_barrel_qualified=False)


def _frontier_contacts(parent, items, proof, roots, access_uuids, deadline, *,
        allow_nonplane_power_role=False):
    """Actual retained Source copper, not a new terminal or barrel waiver.

    Explicit access identities must belong one to each original canonical
    connector island. Only those actual connector PTHs, full-class ordinary
    strokes and already-present full-depth through barrels can be used. The
    independent additive receiver still proves every old byte unchanged.
    """
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    _need(type(access_uuids) in (list, tuple) and len(access_uuids) == 2
        and all(type(u) is str and u for u in access_uuids)
        and len(set(access_uuids)) == 2, 'two_exact_retained_feedthrough_access_identities_required')
    originals = {force._uid(i): i for i in [
        *(p for f in parent.GetFootprints() for p in f.Pads()), *parent.GetTracks()]}
    _need(set(access_uuids) <= originals.keys(), 'existing_Source_feedthrough_access_required')
    membership = [next((index for index, part in enumerate(roots) if u in part), None) for u in access_uuids]
    _need(set(membership) == {0, 1}, 'one_actual_access_per_original_connector_island_required')
    resolver = fr._project_netclass_resolver(str(parent.GetFileName()), board=parent)
    policy = _routing_layers(parent, proof['net'], resolver,
        allow_nonplane_power_role=allow_nonplane_power_role)
    policy['used_layer_ids'] = sorted({int(t.GetLayer()) for t in items})
    allowed = set(policy['allowed_layer_ids'])
    contacts = []
    for uid in access_uuids:
        _need(time.monotonic() < deadline, 'feedthrough_frontier_contact_deadline')
        original = originals[uid]; kind = original.GetClass()
        _need(original.GetNetname() == proof['net'], 'same_actual_Source_feedthrough_access_net_required')
        if kind == 'PAD':
            _need(uid in proof['requested_pad_uuids']
                and original.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and original.HasHole(),
                'only_canonical_Source_connector_lands_are_frontier_pad_access')
        elif kind == 'PCB_TRACK':
            _need(original.GetWidth() >= proof['width_nm'] and int(original.GetLayer()) in allowed
                and not original.HasSolderMask() and original.GetLength() > 0,
                'actual_full_class_Source_feedthrough_track_access_required')
        elif kind == 'PCB_VIA':
            _need(original.GetViaType() == pcbnew.VIATYPE_THROUGH
                and original.TopLayer() == pcbnew.F_Cu and original.BottomLayer() == pcbnew.B_Cu
                and original.GetDrillValue() > 0
                and all(original.IsOnLayer(l) and original.GetWidth(l) > original.GetDrillValue()
                    for l in parent.GetEnabledLayers().CuStack()),
                'actual_existing_full_depth_Source_signal_barrel_required')
        else:
            raise ValueError('unsupported_Source_feedthrough_frontier_kind')
        faces = sorted({int(t.GetLayer()) for t in items if original.IsOnLayer(t.GetLayer())
            and t.GetEffectiveShape(t.GetLayer()).Collide(original.GetEffectiveShape(t.GetLayer()), 0)})
        _need(faces and set(faces) <= allowed, 'actual_new_track_to_retained_Source_access_contact_required')
        for face in faces:
            if kind == 'PAD':
                contact = _annular_contact(original, items, face)
            else:
                land = pcbnew.SHAPE_POLY_SET()
                original.TransformShapeToPolygon(land, face, 0, 1, pcbnew.ERROR_INSIDE, False)
                if kind == 'PCB_VIA':
                    _need(original.FlashLayer(face), 'actual_flashed_retained_Source_barrel_face_required')
                    hole = pcbnew.SHAPE_POLY_SET()
                    pcbnew.SHAPE_SEGMENT(original.GetPosition(), original.GetPosition(),
                        original.GetDrillValue()).TransformToPolygon(hole, 1, pcbnew.ERROR_OUTSIDE)
                    land.BooleanSubtract(hole)
                incoming = pcbnew.SHAPE_POLY_SET()
                for track in items:
                    if track.IsOnLayer(face):
                        poly = pcbnew.SHAPE_POLY_SET()
                        track.TransformShapeToPolygon(poly, face, 0, 1, pcbnew.ERROR_INSIDE, False)
                        incoming.BooleanAdd(poly)
                incoming.BooleanIntersection(land)
                _need(incoming.OutlineCount() > 0 and incoming.Area() > 0,
                    'positive_actual_Source_access_copper_not_hole_or_bbox_required')
                contact = dict(layer=face, positive_native_contact_nm2=incoming.Area(),
                    actual_drill_subtracted=kind == 'PCB_VIA')
            contacts.append(dict(source_access_uuid=uid, source_kind=kind,
                source_connector_island_index=membership[list(access_uuids).index(uid)], **contact))
    return dict(complete=True, actual_contacts=contacts, Source_routing_layer_policy=policy,
        original_barrels_used_for_physical_access_only=True, new_barrels=0,
        old_barrel_capacity_credited=False, new_current_budget=False,
        every_old_native_partition_and_exact_Source_additive_receiving_required=True,
        current_qualified=False, barrel_qualified=False, release_authority=False)


def _receive(source,candidate,*,board_hint,pad_uuids,timeout_s=10.,access_uuids=(),
        allow_nonplane_power_role=False):
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_additive_route_receiving as additive
    import cec_source_literal_additions as literal
    import cec_native_partition_pair as partitions
    from cec_route_proposal_guard import RouteProposalGuard
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10.,'bounded_feedthrough_receiving_lease_required')
    _need(type(allow_nonplane_power_role)is bool,'explicit_boolean_Source_nonplane_recovery_policy_required')
    _need(type(board_hint)is str and board_hint and type(pad_uuids)in(tuple,list)
        and len(pad_uuids)==2 and all(type(u)is str and u for u in pad_uuids)
        and len(set(pad_uuids))==2,'two_explicit_existing_Source_feedthrough_pad_UUIDs_required')
    deadline=time.monotonic()+timeout_s
    frontier = bool(access_uuids)
    result=dict(scope=('Source_canonical_existing_native_frontier_sideband_feedthrough' if frontier
        else 'Source_canonical_existing_plated_sideband_feedthrough'),ok=False,complete=False,errors=[],
        ordinary_reclassification=False,quiet_reclassification=False,new_current_budget=False,current_qualified=False,
        barrel_qualified=False,inherited_footprint_qualified=False,release_authority=False,routing_admitted=False,
        whole_shared_stage_still_required=True)
    try:
        source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        _need(source!=candidate,'distinct_saved_feedthrough_source_candidate_required')
        epoch=force._code_identity();families=[force._family(p,board_hint)for p in(source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
        proof=_canonical(parent,source,board_hint,pad_uuids,deadline);result['independently_compiled_Source_scope']=proof;net=proof['net']
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        _need(not old.keys()-new.keys(),'feedthrough_cannot_retire_any_Source_object')
        incoming=set(new)-set(old);items=[t for t in child.GetTracks()if force._uid(t)in incoming]
        _need(1<=len(items)<=32 and {force._uid(t)for t in items}==incoming,'only_bounded_new_feedthrough_tracks_required')
        names=literal.incoming_copper_nets(candidate.read_text(),incoming)
        _need(set(names)==incoming and all(n==net for n in names.values()),'literal_feedthrough_new_net_changed')
        resolver=fr._project_netclass_resolver(str(source),board=parent)
        policy=_routing_layers(parent,net,resolver,
            allow_nonplane_power_role=allow_nonplane_power_role)
        result['Source_routing_layer_policy']=policy
        allowed=policy['allowed_layer_ids']
        ops=[];foreign_cache={};code=parent.GetNetcodeFromNetname(net)
        for t in items:
            _need(t.GetClass()=='PCB_TRACK'and t.GetNetname()==net and t.GetWidth()==proof['width_nm']
                and int(t.GetLayer())in allowed and not t.HasSolderMask()and t.GetParentGroup()is None,
                'only_authored_actual_channel_feedthrough_tracks_required')
            a,z=tuple(t.GetStart()),tuple(t.GetEnd());dx,dy=abs(a[0]-z[0]),abs(a[1]-z[1])
            _need(a!=z and(dx==0 or dy==0 or dx==dy),'native_octilinear_feedthrough_track_required')
            _need(time.monotonic()<deadline and fr._edge_leg_clear(parent,t.GetStart(),t.GetEnd(),
                (t.GetWidth()+1)//2+proof['clearance_nm'])and fr._tap_foreign_clear(parent,
                t.GetStart(),t.GetEnd(),t.GetWidth(),int(t.GetLayer()),proof['clearance_nm'],{code},
                foreign_cache=foreign_cache),'feedthrough_native_foreign_rule_hole_or_edge_clearance_refused')
            ops.append(('trk',t.GetStart(),t.GetEnd(),t.GetWidth(),int(t.GetLayer())))
        _need(sum(t.GetLength()for t in items)<=200000000,'bounded_feedthrough_span_required')
        policy['used_layer_ids']=sorted({int(t.GetLayer())for t in items})
        before,after=[_parts(b,net,deadline)for b in(parent,child)]
        roots=[next(p for p in before if uid in p)for uid in pad_uuids]
        _need(roots[0]!=roots[1]and len(after)==len(before)-1,'exact_one_new_feedthrough_component_join_required')
        joined=next(p for p in after if pad_uuids[0]in p)
        _need(pad_uuids[1]in joined and incoming<=joined,'all_new_feedthrough_material_must_join_both_requested_lands')
        expected=roots[0]|roots[1]
        _need(joined&set().union(*before)==expected and all(any(p==q for q in after)for p in before if p not in roots),
            'feedthrough_cannot_acquire_other_Source_islands_or_hide_unreached_terminals')
        pads={force._uid(p):p for f in child.GetFootprints()for p in f.Pads()}
        source_pads={force._uid(p):p for f in parent.GetFootprints()for p in f.Pads()}
        if frontier:
            result['retained_native_frontier_contacts'] = _frontier_contacts(
                parent, items, proof, roots, access_uuids, deadline,
                allow_nonplane_power_role=allow_nonplane_power_role)
        else:
            contacts=[]
            for uid in pad_uuids:
                faces=sorted({int(t.GetLayer())for t in items if t.GetEffectiveShape(t.GetLayer()).Collide(pads[uid].GetEffectiveShape(t.GetLayer()),0)})
                _need(faces,'actual_new_feedthrough_terminal_contact_required')
                _need(all(source_pads[uid].IsOnLayer(face)and source_pads[uid].FlashLayer(face)for face in faces),
                    'only_already_flashed_Source_feedthrough_channels_supported')
                contacts.extend(_annular_contact(pads[uid],items,face)for face in faces)
            result['actual_flashed_annular_contacts']=contacts
        guard=RouteProposalGuard(parent,net,board_path=str(source),netclass_resolver=resolver,deadline=deadline,board_hint=board_hint)
        accepted=guard(ops)is True;result['native_route_proposal_guard']=guard.report()
        _need(accepted,'full_Source_feedthrough_route_proposal_guard_refused')
        shared=partitions.compare(parent,child,timeout_s=max(.001,min(10.,deadline-time.monotonic())))
        _need(shared['available']and shared['preserved'],'feedthrough_lost_retained_native_Source_partition')
        result['whole_native_Source_partitions']={k:v for k,v in shared.items()if k not in('source_parts','child_parts','demoted_parts')}
        saved=additive.receive(source,candidate,board_hint=board_hint,timeout_s=max(.001,min(10.,deadline-time.monotonic())))
        result['exact_saved_additive_receiving']=saved
        _need(saved.get('ok')is True and saved.get('complete')is True,'feedthrough_exact_Source_plus_tracks_not_received')
        binding=proof['canonical_Source']
        _need(all(force._hash(Path(p))==h for p,h in {**binding['schematic_files_sha256'],**binding['role_records_sha256']}.items())
            and force._hash(Path(binding['exporter']['exporter']))==binding['exporter']['exporter_sha256'],
            'feedthrough_canonical_Source_role_or_exporter_changed')
        _need(epoch==force._code_identity()and families==[force._family(p,board_hint)for p in(source,candidate)]
            and time.monotonic()<deadline,'feedthrough_saved_Source_candidate_code_or_lease_changed')
        result.update(ok=True,complete=True,source_components=len(before),candidate_components=len(after),
            added_native_uuids=sorted(incoming),unreached_Source_component_count=len(before)-2,
            only_requested_existing_Source_islands_joined=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def receive(source,candidate,*,board_hint,pad_uuids,timeout_s=10.,
        allow_nonplane_power_role=False):
    """Direct new-copper contact to both canonical connector PTHs.

    The optional recovery search policy admits only the known Source
    profile's non-plane power role. Default behavior and all physical,
    canonical-channel, field, current and saved-Source gates are unchanged.
    """
    return _receive(source,candidate,board_hint=board_hint,pad_uuids=pad_uuids,
        timeout_s=timeout_s,allow_nonplane_power_role=allow_nonplane_power_role)


def receive_native_frontier(source,candidate,*,board_hint,pad_uuids,access_uuids,timeout_s=10.,
        allow_nonplane_power_role=False):
    """Explicit retained physical access; not ordinary-net reclassification.

    The original direct-contact API is unchanged. This tier accepts no new
    barrels, current allocation, Source retirement or constructor verdict.
    """
    _need(type(access_uuids) in (list, tuple) and len(access_uuids) == 2
        and all(type(u) is str and u for u in access_uuids) and len(set(access_uuids)) == 2,
        'two_exact_retained_feedthrough_access_identities_required')
    return _receive(source,candidate,board_hint=board_hint,pad_uuids=pad_uuids,
        timeout_s=timeout_s,access_uuids=access_uuids,
        allow_nonplane_power_role=allow_nonplane_power_role)
