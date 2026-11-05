"""Receive a short Source-canonical CAN transceiver endpoint join.

This is not ordinary routing, pair-performance qualification, or permission
to touch existing copper. Both selected embedded CAN pins must identify the
same fitted transceiver and either series SMD lands or one plated connector.
The series tier permits surface tracks only; direct connectors may use
Source-contained, independently process-qualified local signal barrels.
No remote barrel or current qualification follows. All whole-board electrical,
pair, current, field, native, contact and Source gates remain mandatory.
"""
import math
from pathlib import Path
import re
import time


def _need(value,reason):
    if not value:raise ValueError(reason)


def _canonical_pair(board,source,hint,net,deadline):
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_pair_semantics as pairs
    import cec_source_ground_leaf as roles
    import cec_source_no_connect as nc
    import cec_quiet_signal_requests as pins
    import cec_current_topology as current
    import cec_synth_pipeline as synth
    _need(Path(board.GetFileName()).resolve()==source,'exact_saved_CAN_source_required')
    matched=[(p,n)for kind,p,n in pairs.coupled_pair_names(board)if kind=='can'and net in(p,n)]
    _need(len(matched)==1,'unique_selected_CAN_pair_required')
    root=nc._root(board,hint)
    _need(root is not None,'current_canonical_CAN_schematic_required')
    files,hashes,instances=roles._hierarchy(Path(root).resolve(),deadline)
    tree,exporter=roles._export(root,deadline)
    _need(type(exporter)is dict and type(exporter.get('exporter'))is str
        and Path(exporter['exporter']).is_file()
        and force._hash(Path(exporter['exporter']))==exporter.get('exporter_sha256'),
        'fresh_bound_CAN_exporter_required')
    components,nets,node_net=roles._tables(tree)
    resolver=fr._project_netclass_resolver(str(source),board=board)
    with force._thermal_hint(hint):
        protected=set(current.board_current_domains(board,hint))
        _need(all(synth.spec_net_current_contract(hint,name)is None for name in matched[0]),
            'CAN_members_cannot_be_current_domains')
    protected|={z.GetNetname()for z in board.Zones()if not z.GetIsRuleArea()}
    witnesses=[];active_owners=[];faces=set();identities={};peer_owners=[];topologies=[]
    for name,wanted in zip(matched[0],('CANH','CANL')):
        _need(time.monotonic()<deadline,'CAN_source_scope_deadline')
        spec=resolver(name)or{}
        _need(str(spec.get('name','')).casefold()=='can'and name not in protected,
            'authored_CAN_class_without_power_or_pour_ownership_required')
        pads=[p for f in board.GetFootprints()for p in f.Pads()if p.GetNetname()==name]
        _need(len(pads)==2 and len({force._uid(p)for p in pads})==2
            and all(not p.GetParentFootprint().IsDNP()for p in pads),
            'two_fitted_CAN_endpoint_lands_required')
        expected={(p.GetParentFootprint().GetReference(),p.GetNumber())for p in pads}
        _need(nets.get(name)==expected,'exact_canonical_CAN_terminal_net_required')
        rows=[]
        for pad in pads:
            fp=pad.GetParentFootprint();ref=fp.GetReference();number=pad.GetNumber()
            if ref not in identities:identities[ref]=roles._identity(board,ref,components,instances,deadline)
            pin=pins._source_pin(identities[ref],number,deadline)
            _need(node_net.get((ref,number))==name and pad.GetPinType()in('',pin['type'])
                and pad.GetPinFunction()in('',pin['name']), 'CAN_source_native_pin_contradiction')
            rows.append((pad,fp,pin))
        active=[r for r in rows if r[2]==dict(type='bidirectional',name=wanted)]
        passive=[r for r in rows if r[2]['type']=='passive']
        _need(len(active)==len(passive)==1,'Source_CANH_CANL_and_passive_series_land_required')
        active_pad,_,_=active[0];peer,series,_=passive[0]
        actual=tuple(map(int,active_pad.GetLayerSet().CuStack()))
        _need(active_pad.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not active_pad.HasHole()
            and len(actual)==1 and actual[0]in(pcbnew.F_Cu,pcbnew.B_Cu),'one_active_CAN_surface_face_required')
        face=actual[0];faces.add(face)
        if peer.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not peer.HasHole():
            _need(len(list(series.Pads()))==2 and re.search(r'(?:^|:)R_\d{4}_\d{4}Metric(?:_|$)',
                series.GetFPIDAsString()) and tuple(map(int,peer.GetLayerSet().CuStack()))==(face,),
                'canonical_two_land_series_resistor_required')
            topologies.append('series_surface')
        else:
            _need(peer.GetAttribute()==pcbnew.PAD_ATTRIB_PTH and peer.HasHole()
                and peer.IsOnLayer(face)and peer.FlashLayer(face), 'actual_plated_CAN_connector_contact_required')
            topologies.append('direct_plated_connector')
        peer_owners.append(force._uid(series))
        active_owners.append(force._uid(active[0][1]))
        witnesses.append(dict(net=name,active_pad_uuid=force._uid(active[0][0]),
            series_pad_uuid=force._uid(passive[0][0]),active_source_pin=active[0][2]))
    _need(len(set(active_owners))==1 and len(faces)==1,'same_transceiver_and_CAN_surface_required')
    _need(len(set(topologies))==1 and(topologies[0]!='direct_plated_connector' or len(set(peer_owners))==1),
        'coherent_two_member_CAN_endpoint_topology_required')
    _need(hashes=={str(p):force._hash(p)for p in files},'CAN_schematic_epoch_changed')
    _need(force._hash(Path(exporter['exporter']))==exporter['exporter_sha256'],
        'CAN_exporter_epoch_changed')
    spec=resolver(net)or{};settings=board.GetDesignSettings()
    width=max(settings.m_TrackMinWidth,math.ceil(float(spec.get('track_width')or 0)*1e6))
    clearance=max(settings.m_MinClearance,math.ceil(float(spec.get('clearance')or 0)*1e6))
    _need(0<width<=1000000 and clearance>0 and spec.get('track_width')and spec.get('clearance'),
        'positive_authored_CAN_dimensions_required')
    return dict(pair_members=list(matched[0]),witnesses=witnesses,face=next(iter(faces)),
        endpoint_topology=topologies[0],
        net=net,width_nm=int(width),clearance_nm=int(clearance),source_class=spec['name'],
        canonical_source=dict(root=str(root),schematic_files_sha256=hashes,exporter=exporter))


def _local_barrels(parent,child,items,proof):
    """Only true Source-contained local POFV, not nominal class exceptions."""
    import pcbnew
    import cec_fab_profile as fab
    import cec_existing_local_pofv_pad_rule as rule
    import cec_force_current as force
    active=next(w['active_pad_uuid']for w in proof['witnesses']if w['net']==proof['net'])
    pads=[p for f in parent.GetFootprints()for p in f.Pads()if force._uid(p)==active]
    _need(len(pads)==1,'unique_Source_CAN_active_land_required')
    pad=pads[0];context=rule.resolve(parent,pad)
    _need(context is not None,'actual_Source_CAN_local_barrel_rule_required')
    diameter,drill=rule.geometry(context,(context['minimum_nm']['via_diameter']/1e6,
        context['minimum_nm']['hole_size']/1e6))
    _need(fab.board_profile_name(parent)==fab.board_profile_name(child),'CAN_factory_profile_changed')
    records=[];cache={}
    for via in items:
        _need(via.GetClass()=='PCB_VIA'and via.GetNetname()==proof['net']and via.IsLocked()
            and via.GetViaType()==pcbnew.VIATYPE_THROUGH and via.TopLayer()==pcbnew.F_Cu
            and via.BottomLayer()==pcbnew.B_Cu and via.GetDrillValue()==round(drill*1e6)
            and all(via.GetWidth(l)==round(diameter*1e6)for l in child.GetEnabledLayers().CuStack())
            and fab._pad_contains_circle(pad,via.GetPosition(),math.ceil(diameter*1e6/2),tolerance_nm=0),
            'exact_Source_contained_CAN_local_barrel_required')
        decision,why=fab.local_pofv_via_decision(child,via,cache=cache)
        _need(decision,'saved_CAN_local_barrel_process_not_received:'+str(why))
        records.append(dict(uuid=force._uid(via),Source_rule=context,independent_saved_process=why,
            plated_barrel_current_qualified=False))
    return records


def _partition(board,net):
    import pcbnew
    import cec_force_current as force
    material=[p for f in board.GetFootprints()for p in f.Pads()if p.GetNetname()==net]
    material += [t for t in board.GetTracks()if t.GetNetname()==net]
    _need(len(material)<=512,'bounded_CAN_native_component_inventory_required')
    graph=pcbnew.CONNECTIVITY_DATA()
    for item in material:_need(graph.Add(item),'CAN_native_graph_refused')
    remaining={force._uid(i):i for i in material};parts=[]
    _need(len(remaining)==len(material),'unique_CAN_native_conductor_identity_required')
    while remaining:
        seed=remaining[min(remaining)]
        reached=({force._uid(seed)}|{force._uid(i)for i in graph.GetConnectedItems(seed)})&remaining.keys()
        parts.append(set(reached))
        for uid in reached:del remaining[uid]
    return parts


def receive(source,candidate,*,board_hint,net,timeout_s=10.):
    import pcbnew
    import cec_force_current as force
    import cec_additive_route_receiving as additive
    import cec_source_literal_additions as literal
    import cec_fr as fr
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10.,
        'bounded_CAN_endpoint_receiving_required')
    _need(type(net)is str and bool(net)and type(board_hint)is str and bool(board_hint),
        'explicit_CAN_endpoint_identity_required')
    deadline=time.monotonic()+timeout_s
    result=dict(scope='Source_canonical_CAN_surface_endpoint_join',ok=False,complete=False,errors=[],
        ordinary_reclassification=False,pair_performance_qualified=False,current_qualified=False,
        release_authority=False,routing_admitted=False,whole_shared_stage_still_required=True)
    try:
        source,candidate=[Path(p).resolve(strict=True)for p in(source,candidate)]
        _need(source!=candidate,'distinct_CAN_source_candidate_required')
        epoch=force._code_identity();families=[force._family(p,board_hint)for p in(source,candidate)]
        parent,child=[pcbnew.LoadBoard(str(p))for p in(source,candidate)]
        proof=_canonical_pair(parent,source,board_hint,net,deadline)
        result['independently_compiled_source_scope']=proof
        direct=proof['endpoint_topology']=='direct_plated_connector'
        if direct:result['scope']='Source_canonical_CAN_plated_connector_join'
        _,before=additive._nodes(source);_,after=additive._nodes(candidate)
        _need(not before.keys()-after.keys(),'CAN_addition_cannot_retire_Source_material')
        incoming=set(after)-set(before)
        items=[t for t in child.GetTracks()if force._uid(t)in incoming]
        _need(1<=len(items)<=18 and {force._uid(t)for t in items}==incoming,
            'only_bounded_new_CAN_tracks_required')
        _need(all(n==net for n in literal.incoming_copper_nets(candidate.read_text(),incoming).values()),
            'literal_CAN_addition_net_changed')
        tracks=[t for t in items if t.GetClass()=='PCB_TRACK']
        vias=[t for t in items if t.GetClass()=='PCB_VIA']
        _need(1<=len(tracks)<=16 and len(tracks)+len(vias)==len(items)
            and len(vias)<=(2 if direct else 0),'bounded_CAN_track_and_local_barrel_inventory_required')
        allowed=fr._lastmile_route_layers(parent,net_name=net,
            spec=fr._project_netclass_resolver(str(source))(net)or{},exclude_front=False)if direct else[proof['face']]
        for item in tracks:
            _need(item.GetClass()=='PCB_TRACK'and item.GetNetname()==net
                and item.GetWidth()==proof['width_nm']and int(item.GetLayer())in allowed
                and not item.HasSolderMask()and item.GetParentGroup()is None,
                'authored_surface_CAN_track_geometry_required')
            a,b=tuple(item.GetStart()),tuple(item.GetEnd());dx,dy=abs(a[0]-b[0]),abs(a[1]-b[1])
            _need(a!=b and(dx==0 or dy==0 or dx==dy),'canonical_CAN_endpoint_segments_required')
        _need(sum(t.GetLength()for t in tracks)<=16000000,'bounded_local_CAN_endpoint_length_required')
        if vias:result['Source_contained_local_barrels']=_local_barrels(parent,child,vias,proof)
        old_parts,new_parts=[_partition(b,net)for b in(parent,child)]
        _need(len(old_parts)==2 and len(new_parts)==1 and incoming<=new_parts[0],
            'complete_one_component_CAN_endpoint_join_required')
        saved=additive.receive(source,candidate,board_hint=board_hint,
            timeout_s=max(.001,min(10.,deadline-time.monotonic())))
        result['exact_saved_additive_receiving']=saved
        _need(saved.get('ok')is True and saved.get('complete')is True,'CAN_exact_Source_delta_not_received')
        _need(epoch==force._code_identity()and families==[force._family(p,board_hint)for p in(source,candidate)]
            and time.monotonic()<deadline,'CAN_saved_epoch_or_lease_changed')
        result.update(ok=True,complete=True,source_components=2,candidate_components=1,
            added_native_uuids=sorted(incoming),Source_CAN_scope_independently_recompiled=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
