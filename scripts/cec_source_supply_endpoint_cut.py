"""Literal supply pad-contact retirement, never old/new neckdown qualification.

An existing undersized component stays debt. Only its departing pad lead
or bounded manufacturer-input chain may be retired to a retained full-width
junction. Complete whole-current replacement and every original partition
remain mandatory. This owner never authorizes a smaller replacement width.
"""
import time,math
from pathlib import Path
import pcbnew
import cec_force_current as force
import cec_device_power_roles as roles
import cec_source_ground_leaf as source
import cec_synth_pipeline as synth
from cec_footprint_fields import footprint_properties


def _power_input_owner(board,pad,board_hint,deadline,context):
    """Fresh complete Source identity, not a native label or load allocation."""
    fp=pad.GetParentFootprint();model=roles.footprint_contract(fp)
    if not model or model['pins'].get(pad.GetNumber())!='power_input':
        return None
    if (fp.IsDNP()or pad.HasHole()or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
            or tuple(pad.GetLayerSet().CuStack())!=(fp.GetLayer(),)
            or pad.GetNetCode()<=0 or pad.GetNetname()=='GND'):
        raise ValueError('positive_native_manufacturer_supply_input_required')
    if not context:
        root=source.source_nc._root(board,board_hint)
        if root is None:raise ValueError('canonical_supply_input_source_required')
        _files,hashes,instances=source._hierarchy(root,deadline)
        tree,export=source._export(root,deadline)
        comps,_nets,node_net=source._tables(tree)
        context.update(hashes=hashes,instances=instances,comps=comps,
            node_net=node_net,export=export)
    mapping=roles.physical_pinmap(fp,model,board_hint=board_hint,
        timeout_s=min(8.,max(.001,deadline-time.monotonic())))
    identity=source._identity(board,fp.GetReference(),context['comps'],context['instances'],deadline)
    _native,path,sf,symbol=identity
    libraries=[b for tag,b in sf.children if tag=='lib_symbols']
    if len(libraries)!=1:raise ValueError('supply_input_complete_embedded_library_required')
    tree=synth.parse_sexpr(libraries[0]);selected=[n for n in synth._kids(tree,'symbol')
        if len(n)>1 and n[1]==symbol['lib_id']]
    if len(selected)!=1 or synth._first(selected[0],'extends')is not None:
        raise ValueError('supply_input_unique_complete_source_symbol_required')
    queue=selected[:];pins={};count=0
    while queue:
        source._tick(deadline);node=queue.pop();count+=1
        if count>8192:raise ValueError('supply_input_embedded_symbol_inventory_bound')
        if isinstance(node,list)and node:
            if node[0]=='pin':
                number=synth._val(node,'number','')
                if not number or number in pins or len(node)<2:
                    raise ValueError('supply_input_unique_embedded_pin_required')
                pins[number]=dict(type=node[1],name=synth._val(node,'name',''))
            queue.extend(n for n in node if isinstance(n,list))
    lint={p['num']:p for p in symbol['pins']}
    if (set(pins)!=set(model['pins'])or set(mapping)!=set(pins)
            or len(lint)!=len(symbol['pins'])or set(lint)!=set(pins)
            or any(lint[n]['type']!=pins[n]['type']for n in pins)):
        raise ValueError('supply_input_complete_source_manufacturer_pinmap_required')
    for number,pads in mapping.items():
        for peer in pads:
            if (context['node_net'].get((fp.GetReference(),number),'')!=peer.GetNetname()
                    or peer.GetPinFunction()not in('',pins[number]['name'])
                    or peer.GetPinType()not in('',pins[number]['type'])):
                raise ValueError('supply_input_complete_native_source_pin_net_mismatch')
    # Only the selected connected input is passed to the connected-pin
    # predicate. A legitimate NC on an unrelated Alert/output is untouched.
    connected=source._pin(identity,pad.GetNumber())
    if connected['type']!='power_in'or pins[pad.GetNumber()]['type']!='power_in':
        raise ValueError('canonical_selected_manufacturer_power_input_required')
    source._tick(deadline)
    if any(force._hash(Path(p))!=h for p,h in context['hashes'].items()):
        raise ValueError('supply_input_source_hierarchy_changed')
    proof=dict(scope='fresh_source_manufacturer_power_input',owner=fp.GetReference(),
        owner_uuid=force._uid(fp),pin=pad.GetNumber(),rail=pad.GetNetname(),
        manufacturer_source=model['source'],device_package=model['device_package'],
        source_schematic=str(path),symbol_uuid=symbol['uuid'],
        schematic_files_sha256=context['hashes'],exporter=context['export'],
        complete_pin_nets={force._uid(p):dict(number=p.GetNumber(),net=p.GetNetname())
            for pads in mapping.values()for p in pads},current_authority=False,
        source_no_connect_or_native_metadata_not_written=True)
    # The native frame is independently recompiled during priority and saved
    # receiving. Bind the entire fresh exported tree and executable, excluding
    # ONLY the existing policy's generated design/date clock value. Never
    # weaken the complete transport comparison or reuse an old export pass.
    import cec_source_netlist_semantics as semantics
    return semantics.replay_identity(proof)


def _supply_tied_address_owner(board,pad,board_hint,deadline,context):
    """Retire an existing address lead without aliasing it to a power pin.

    The actual complete manufacturer map and current exported schematic
    must tie this input to exactly one power input of the SAME package.
    This only owns the old literal lead: its replacement still carries the
    entire rail contract through the existing current and saved receivers.
    """
    fp=pad.GetParentFootprint();model=roles.footprint_contract(fp)
    if not model or model['pins'].get(pad.GetNumber())!='address':return None
    if (fp.IsDNP()or pad.HasHole()or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
            or tuple(pad.GetLayerSet().CuStack())!=(fp.GetLayer(),)
            or pad.GetNetCode()<=0 or pad.GetNetname()=='GND'):
        raise ValueError('positive_native_supply_tied_address_required')
    peers=[p for p in fp.Pads()if model['pins'].get(p.GetNumber())=='power_input'
        and p.GetNetCode()==pad.GetNetCode()and p.GetNetname()==pad.GetNetname()]
    if len(peers)!=1:raise ValueError('unique_same_package_address_supply_input_required')
    power=peers[0]
    authority=_power_input_owner(board,power,board_hint,deadline,context)
    if authority is None:raise ValueError('complete_source_address_supply_input_required')
    identity=source._identity(board,fp.GetReference(),context['comps'],context['instances'],deadline)
    connected=source._pin(identity,pad.GetNumber())
    if (connected['type']not in('input','passive')
            or context['node_net'].get((fp.GetReference(),pad.GetNumber()))!=pad.GetNetname()
            or context['node_net'].get((fp.GetReference(),power.GetNumber()))!=pad.GetNetname()):
        raise ValueError('canonical_same_package_address_supply_tie_required')
    source._tick(deadline)
    return dict(authority,scope='fresh_source_manufacturer_supply_tied_address',
        pin=pad.GetNumber(),power_input_pin=power.GetNumber(),
        source_power_input_authority=authority,source_address_electrical_type=connected['type'],
        address_role_not_reclassified=True,address_load_not_inferred=True)


def _power_input_chain(board,pad,new,incident,*,authority,contract,source_floor,
                       allow_locked,deadline):
    """One Source-derived simple chain; every other native contact is retained."""
    import cec_route_quality as quality
    def tick():source._tick(deadline)
    groups=list(board.Groups());alltracks=list(board.GetTracks());face=pad.GetParentFootprint().GetLayer()
    roots=[t for t in incident if t.GetParentGroup()is not None and 0<t.GetWidth()<=350000]
    owner_groups={force._uid(g):g for g in groups if any(g.ContainsItem(t)for t in roots)}
    if len(owner_groups)!=1:raise ValueError('unique_existing_supply_endpoint_group_required')
    group=next(iter(owner_groups.values()));members=list(group.GetItems())
    if (group.GetName()!='CEC_LOCAL_ENDPOINT_NECKDOWN'or group.IsLocked()
            or group.GetParentGroup()is not None or not 1<=len(members)<=512
            or any(t.GetClass()!='PCB_TRACK'for t in members)):
        raise ValueError('unique_existing_supply_endpoint_group_required')
    cohort={force._uid(t):t for t in members if t.GetNetCode()==pad.GetNetCode()
        and t.GetLayer()==face and 0<t.GetWidth()<=350000}
    selected={force._uid(t):t for t in roots};points=set()
    for t in roots:points.update((tuple(t.GetStart()),tuple(t.GetEnd())))
    changed=True
    while changed:
        tick();changed=False
        for uid,t in cohort.items():
            ends={tuple(t.GetStart()),tuple(t.GetEnd())}
            if uid not in selected and ends&points:
                selected[uid]=t;points|=ends;changed=True
    if (not 1<=len(selected)<=4 or sum(t.GetLength()for t in selected.values())>1500000
            or any(t.IsLocked()and not allow_locked for t in selected.values())):
        raise ValueError('bounded_locked_supply_input_chain_required')
    for t in selected.values():
        tick()
        if (t.HasSolderMask()or t.GetWidth()<board.GetDesignSettings().m_TrackMinWidth
                or not 0<t.GetLength()or not quality.is_canonical_stroke(tuple(t.GetStart()),tuple(t.GetEnd()),tolerance_nm=0)
                or [force._uid(g)for g in groups if g.ContainsItem(t)]!=[force._uid(group)]):
            raise ValueError('plain_unique_canonical_supply_input_chain_required')
    degrees={at:sum(at in(tuple(t.GetStart()),tuple(t.GetEnd()))for t in selected.values())for at in points}
    ends={at for at,count in degrees.items()if count==1}
    pad_ends={at for at in ends if pad.HitTest(pcbnew.VECTOR2I(*at),0)}
    if len(ends)!=2 or len(pad_ends)!=1 or any(d>2 for d in degrees.values()):
        raise ValueError('unbranched_single_root_supply_input_chain_required')
    throat=next(iter(ends-pad_ends));full,gap=source_floor(next(iter(selected.values())))
    if type(full)is not int or type(gap)is not int or full<=0 or gap<0:
        raise ValueError('literal_source_supply_input_dimensions_required')
    if face not in contract['required_by_layer_nm']:
        raise ValueError('source_supply_input_current_layer_required')
    width=max(full,contract['required_by_layer_nm'][face])
    fixed=[t for t in alltracks if t.GetClass()=='PCB_TRACK'and force._uid(t)not in selected
        and t.GetNetCode()==pad.GetNetCode()and t.GetLayer()==face and t.GetWidth()>=width
        and throat in(tuple(t.GetStart()),tuple(t.GetEnd()))]
    if len(fixed)!=1 or new.HitTest(pcbnew.VECTOR2I(*throat),0):
        raise ValueError('one_fixed_full_current_supply_input_carrier_required')
    if any(source_floor(t)!=(full,gap)for t in selected.values()):
        raise ValueError('single_source_supply_input_chain_dimension_contract_required')
    fixed_ids={force._uid(t)for t in fixed}
    # Consecutive thin edges can overlap the SAME retained round cap.
    # That is not a second branch. Any other pad/track/barrel/fill contact
    # remains outside this simple endpoint owner, regardless of net name.
    for t in selected.values():
        tick();shape=t.GetEffectiveShape(face)
        for fp in board.GetFootprints():
            for peer in fp.Pads():
                if (force._uid(peer)!=force._uid(pad)and peer.IsOnLayer(face)
                        and shape.Collide(peer.GetEffectiveShape(face),0)):
                    raise ValueError('supply_input_chain_other_land_contact')
        for peer in alltracks:
            if (force._uid(peer)not in set(selected)|fixed_ids and peer.IsOnLayer(face)
                    and shape.Collide(peer.GetEffectiveShape(face),0)):
                raise ValueError('supply_input_chain_unowned_conductor_contact')
        for zone in board.Zones():
            if zone.GetIsRuleArea()or not zone.IsOnLayer(face):continue
            if not zone.IsFilled():raise ValueError('supply_input_chain_unknown_fill_contact')
            if zone.HasFilledPolysForLayer(face)and zone.GetFilledPolysList(face).Collide(shape,0):
                raise ValueError('supply_input_chain_pour_contact_not_owned')
    ids=set(selected)
    return dict(kind='source_supply_pad_contact_lead_restoration',retired_track_uuids=sorted(ids),
        pad_uuid=force._uid(pad),net=pad.GetNetname(),layer_id=int(face),
        retained_throat_nm=list(throat),retained_throat_track_uuids=sorted(fixed_ids),
        source_group_uuid=force._uid(group),remaining_group_members=sorted(force._uid(i)for i in members if force._uid(i)not in ids),
        source_edges=[dict(uuid=u,source_nm=[list(selected[u].GetStart()),list(selected[u].GetEnd())],
            width_nm=selected[u].GetWidth(),locked=bool(selected[u].IsLocked()))for u in sorted(ids)],
        source_width_nm=min(t.GetWidth()for t in selected.values()),source_authority=authority,
        unchanged_full_rail_current_contract=contract,width_nm=width,clearance_nm=gap,
        old_oversized_neckdown_not_qualified=True,new_thin_allowance=False,
        new_prefix_requires_independent_whole_current_receiving=True,saved_candidate_authorized=False)


def retained_throat_contacts(board,posed,cuts,*,board_hint,moving_via_uuids=(),timeout_s=10.):
    """Keep a fixed throat literal; disclose each lost owned companion contact.

    This supplies no connection/cut permission. The complete compiler must
    independently emit and receive each moved Source land's exact old port.
    A shared barrel or unrelated moving terminal cannot be silently left.
    """
    from cec_measurement_leaf import _bypass_supply_owner
    if type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10:
        raise ValueError('bounded_retained_supply_throat_observation_required')
    deadline=time.monotonic()+timeout_s;result=[]
    old={force._uid(t):t for t in board.GetTracks()}
    target={force._uid(p):p for fp in posed.GetFootprints()for p in fp.Pads()}
    for cut in cuts:
        owner_authority=cut['source_authority']
        if owner_authority.get('scope')not in('fresh_source_manufacturer_power_input',
                'fresh_source_manufacturer_supply_tied_address'):continue
        power_pin=owner_authority.get('power_input_pin',owner_authority['pin'])
        for uid in cut['retained_throat_track_uuids']:
            source._tick(deadline);edge=old[uid];face=int(edge.GetLayer());contacts=[]
            for fp in board.GetFootprints():
                for pad in fp.Pads():
                    new=target.get(force._uid(pad))
                    if (new is None or not pad.IsOnLayer(face)
                            or not edge.GetEffectiveShape(face).Collide(pad.GetEffectiveShape(face),0)):
                        continue
                    if pad.GetNetname()!=cut['net']:
                        raise ValueError('fixed_supply_throat_source_foreign_land_contact')
                    if (tuple(new.GetPosition())==tuple(pad.GetPosition())
                            and new.GetOrientationDegrees()==pad.GetOrientationDegrees()):continue
                    points=[list(at)for at in(edge.GetStart(),edge.GetEnd())if pad.HitTest(at,0)]
                    split=cut.get('source_split_supply_input')
                    if (not points and force._uid(pad)==cut['pad_uuid'] and split is not None
                            and split.get('kind')=='two_Source_short_input_arms_two_fixed_full_current_ports'
                            and split.get('pad_uuid')==cut['pad_uuid']
                            and split.get('first_literal_full_current_junctions_only')is True
                            and set(cut['retired_track_uuids'])<=set(split.get('complete_retired_track_uuids',[]))
                            and uid in split.get('complete_retained_carrier_uuids',[])
                            and edge.GetWidth()>=cut['width_nm']
                            and tuple(cut['retained_throat_nm'])in(tuple(edge.GetStart()),tuple(edge.GetEnd()))):
                        # A retained wide round cap/body can touch this SAME
                        # original VS land without its centreline endpoint
                        # falling inside that land. The independently typed
                        # split-input cut already demands full-current repair
                        # to this actual immutable carrier endpoint. Preserve
                        # that real Source contact through the same endpoint;
                        # no companion pad or midspan anchor gains this scope.
                        points=[list(cut['retained_throat_nm'])]
                    if not points:raise ValueError('fixed_supply_throat_moving_contact_needs_exact_source_endpoint')
                    if force._uid(pad)==cut['pad_uuid']:authority=owner_authority
                    elif (owner_authority.get('scope')=='fresh_source_manufacturer_supply_tied_address'
                            and force._uid(fp)==owner_authority['owner_uuid']
                            and pad.GetNumber()==power_pin):
                        authority=owner_authority['source_power_input_authority']
                    else:
                        authority=_bypass_supply_owner(board,pad,board_hint)
                        if (authority.get('owner')!=owner_authority['owner']
                                or str(authority.get('supply_pin'))!=power_pin
                                or authority.get('rail')!=cut['net']):
                            raise ValueError('fixed_supply_throat_unrelated_moving_companion')
                    contacts.append(dict(pad_uuid=force._uid(pad),source_contact_nm=points,
                        source_companion_authority=authority,
                        exact_old_port_reconstruction_mandatory=True))
            for via_id in moving_via_uuids:
                via=old[via_id]
                if via.IsOnLayer(face)and edge.GetEffectiveShape(face).Collide(via.GetEffectiveShape(face),0):
                    raise ValueError('fixed_supply_throat_cannot_drop_moving_barrel_contact')
            result.append(dict(uuid=uid,net=cut['net'],layer_id=face,
                source_nm=[list(edge.GetStart()),list(edge.GetEnd())],width_nm=int(edge.GetWidth()),
                source_supply_cut_pad_uuid=cut['pad_uuid'],lost_moving_contacts=contacts,
                literal_source_throat_retained=True,all_old_contacts_still_due=True,
                current_authority=False,saved_candidate_authorized=False))
    source._tick(deadline)
    return result


def output_bypass_owner(board,pad,board_hint):
    """Fresh canonical mux output-cap assignment, never a load allocation."""
    import cec_constraints as constraints
    import cec_source_no_connect as nc
    import cec_sch_lint as sch
    deadline=time.monotonic()+10.;fp=pad.GetParentFootprint()
    with force._thermal_hint(board_hint):assigned=constraints._device_bypass_assignment(board,project_max_mm=3.5)
    selected=[q['requirement']for q in assigned['assigned'].values()if q['cap_ref']==fp.GetReference()]
    if len(selected)!=1:raise ValueError('unique_source_output_bypass_assignment_required')
    req=selected[0];owner=board.FindFootprintByReference(req['ref']);model=roles.footprint_contract(owner)if owner else None
    pins=[p for p in owner.Pads()if model and model['pins'].get(p.GetNumber())=='power_output']if owner else[]
    if (not model or model['device_package']!='TPS2121 RUX' or len(list(owner.Pads()))!=12
            or {p.GetNumber()for p in owner.Pads()}!={str(n)for n in range(1,13)}
            or owner.GetValue()!='TPS2121RUXR' or not owner.GetFPIDAsString().endswith(':RUX0012A')
            or {p.GetNumber()for p in pins}!={'1','8'}or any(p.GetNetname()!=req['rail']for p in pins)
            or str(req['pin'])not in('1','8')or pad.GetNetname()!=req['rail']
            or len(list(fp.Pads()))!=2 or {p.GetNetname()for p in fp.Pads()}!={'GND',req['rail']}
            or fp.IsDNP()or owner.IsDNP()or fp.IsFlipped()!=owner.IsFlipped()
            or any(p.HasHole()or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in [*fp.Pads(),*pins])
            or min(math.dist(tuple(pad.GetPosition()),tuple(p.GetPosition()))for p in pins)>3500000):
        raise ValueError('positive_source_mux_output_bypass_required')
    root=nc._root(board,board_hint)
    if root is None:raise ValueError('canonical_output_bypass_source_required')
    files,hashes,instances=source._hierarchy(root,deadline);tree,export=source._export(root,deadline)
    comps,nets,node_net=source._tables(tree);identities=[]
    for item in (fp,owner):
        ref=item.GetReference();entries=instances.get(ref,[]);comp=comps.get(ref)
        if len(entries)!=1 or comp is None:raise ValueError('unique_output_bypass_source_instance_required')
        path,sf,symbol,instance=entries[0];blocks=[b for t,b in sf.children if t=='symbol'and sch.prop_value(b,'Reference')==ref]
        if len(blocks)!=1:raise ValueError('unique_output_bypass_symbol_required')
        block=blocks[0];props=footprint_properties(item)
        for key,native,compiled in [('Value',item.GetValue(),synth._val(comp,'value','')),('Footprint',item.GetFPIDAsString(),synth._val(comp,'footprint',''))]:
            if native!=sch.prop_value(block,key)or native!=compiled:raise ValueError('output_bypass_source_identity_mismatch')
        mpn=sch.prop_value(block,'MPN');exported={synth._val(p,'name',''):synth._val(p,'value','')for p in synth._kids(comp,'property')}
        if not mpn or exported.get('MPN')!=mpn or props.get('MPN')not in(None,'',mpn):raise ValueError('output_bypass_mpn_contradiction')
        if item is owner and mpn!='TPS2121RUXR':raise ValueError('output_bypass_selected_mux_mpn_required')
        if synth._val(comp,'tstamps','')!=symbol['uuid']:raise ValueError('output_bypass_symbol_uuid_mismatch')
        sheet=synth._first(comp,'sheetpath');native_path=item.GetPath().AsString()
        if instance and synth._val(sheet,'tstamps','')!='/'+'/'.join(instance)+'/':raise ValueError('output_bypass_hierarchy_mismatch')
        if native_path and native_path.rstrip('/').split('/')[-1]!=symbol['uuid']:raise ValueError('output_bypass_native_path_mismatch')
        if '(dnp yes)'in block:raise ValueError('output_bypass_source_dnp')
        identities.append((item,path,sf,symbol))
    # Inspect actual canonical embedded library, not native blank annotations
    # nor a prose Note. The selected mux's two OUT lands are one source net.
    for identity,expected in ((identities[0],{str(n)for n in(1,2)}),(identities[1],{str(n)for n in range(1,13)})):
        _,_,sf,symbol=identity
        libs=[b for t,b in sf.children if t=='lib_symbols']
        if len(libs)!=1:raise ValueError('output_bypass_source_library_required')
        tree_lib=synth.parse_sexpr(libs[0]);selected_lib=[n for n in synth._kids(tree_lib,'symbol')if len(n)>1 and n[1]==symbol['lib_id']]
        if len(selected_lib)!=1:raise ValueError('output_bypass_selected_library_required')
        todo=[selected_lib[0]];library_pins=[]
        while todo:
            node=todo.pop()
            if node and node[0]=='pin':library_pins.append(node)
            todo.extend(n for n in node if isinstance(n,list))
        numbers=[synth._val(n,'number','')for n in library_pins]
        if len(numbers)!=len(expected)or set(numbers)!=expected:raise ValueError('output_bypass_complete_source_pinmap_required')
        if identity[0]is fp and any(len(n)<2 or n[1]!='passive'for n in library_pins):
            raise ValueError('source_bypass_cap_passive_pin_type_required')
        if identity[0]is owner:
            for n in library_pins:
                if synth._val(n,'number','')in('1','8')and(synth._val(n,'name','')!='OUT'or n[1]not in('power_in','power_out','output')):
                    raise ValueError('canonical_mux_output_pin_contradiction')
    for identity,numbers in ((identities[0],[p.GetNumber()for p in fp.Pads()]),(identities[1],['1','8'])):
        for number in numbers:
            source._pin(identity,number)
            native=identity[0].FindPadByNumber(number)
            if node_net.get((identity[0].GetReference(),number))!=native.GetNetname():raise ValueError('output_bypass_source_net_mismatch')
    if any(force._hash(Path(p))!=h for p,h in hashes.items())or time.monotonic()>=deadline:raise ValueError('output_bypass_source_epoch_changed')
    proof=dict(cap_ref=fp.GetReference(),owner=owner.GetReference(),supply_pin=str(req['pin']),rail=req['rail'],
        manufacturer_source=model['source'],scope='fresh_source_mux_output_bypass',schematic_files_sha256=hashes,
        exporter=export,native_missing_procurement_fields_not_role_authority=True,current_authority=False)
    # Forks and complete native frames rederive this same Source assignment.
    # Bind the complete fresh netlist tree, hierarchy and executable exactly,
    # excluding only the existing policy's generated design/date clock. A
    # raw export hash changes each second even when no electrical input does.
    import cec_source_netlist_semantics as semantics
    return semantics.replay_identity(proof)


def plan(source_board,posed,*,board_hint,source_floor,allow_locked=False,timeout_s=10.,
         isolated_component_track_uuids=()):
    if (type(allow_locked)is not bool or type(timeout_s)not in(int,float)
            or not math.isfinite(timeout_s)or not 0<timeout_s<=10 or not callable(source_floor)
            or type(board_hint)is not str or not board_hint):raise ValueError('bounded_supply_lead_cut_required')
    import cec_decoupler_cell as cells
    from cec_measurement_leaf import _bypass_supply_owner
    deadline=time.monotonic()+timeout_s;tracks=list(source_board.GetTracks());target={force._uid(p):p for fp in posed.GetFootprints()for p in fp.Pads()};result=[];context={};selected_ids=set()
    if len(target)+len(tracks)>16384:raise ValueError('source_supply_lead_inventory_bound')
    if (type(isolated_component_track_uuids)not in(list,tuple,set,frozenset)
            or len(isolated_component_track_uuids)>512
            or any(type(u)is not str or not u for u in isolated_component_track_uuids)
            or not set(isolated_component_track_uuids)<={force._uid(t)for t in tracks if t.GetClass()=='PCB_TRACK'}):
        raise ValueError('literal_existing_isolated_supply_transport_scope_required')
    isolated=set(isolated_component_track_uuids)
    for fp in source_board.GetFootprints():
        for pad in fp.Pads():
            if time.monotonic()>=deadline:raise ValueError('source_supply_lead_cut_deadline')
            uid=force._uid(pad);new=target.get(uid)
            if new is None or tuple(pad.GetPosition())==tuple(new.GetPosition())or pad.GetNetname()=='GND'or pad.HasHole():continue
            incident=[t for t in tracks if t.GetClass()=='PCB_TRACK'and t.GetNetCode()==pad.GetNetCode()and t.GetLayer()==fp.GetLayer()and any(pad.HitTest(at,0)and not new.HitTest(at,0)for at in(t.GetStart(),t.GetEnd()))]
            thin=[t for t in incident if t.GetParentGroup()is not None and 0<t.GetWidth()<=350000]
            if not thin:continue
            roots={force._uid(t)for t in thin}
            if roots&isolated:
                component=set(roots);points={tuple(at)for t in thin for at in(t.GetStart(),t.GetEnd())}
                cohort={force._uid(t):t for g in source_board.Groups()if any(g.ContainsItem(t)for t in thin)
                    for t in g.GetItems()if t.GetClass()=='PCB_TRACK'and t.GetNetCode()==pad.GetNetCode()
                    and t.GetLayer()==fp.GetLayer()and 0<t.GetWidth()<=350000}
                changed=True
                while changed:
                    source._tick(deadline);changed=False
                    for key,t in cohort.items():
                        ends={tuple(t.GetStart()),tuple(t.GetEnd())}
                        if key not in component and ends&points:
                            component.add(key);points|=ends;changed=True
                if not component<=isolated:raise ValueError('supply_lead_cut_overlaps_partial_isolated_transport')
                # Negative scope only: the enclosing compiler has just
                # independently derived the COMPLETE rigid isolated owner.
                # This function grants no transport, cut or saved admission
                # for any excluded object. Do not double-own its input lead.
                continue
            authority=_power_input_owner(source_board,pad,board_hint,deadline,context)
            if authority is None:
                authority=_supply_tied_address_owner(source_board,pad,board_hint,deadline,context)
            if authority is not None:
                with force._thermal_hint(board_hint):contract=cells._supply_current_widths(source_board,pad.GetNetname())
                if not contract:raise ValueError('source_whole_current_contract_required_for_supply_cut')
                import cec_source_split_supply_input as split_input
                chains=split_input.chains(source_board,pad,new,incident,authority=authority,
                    contract=contract,source_floor=source_floor,allow_locked=allow_locked,deadline=deadline)
                if chains is None:
                    chains=[_power_input_chain(source_board,pad,new,incident,authority=authority,
                        contract=contract,source_floor=source_floor,allow_locked=allow_locked,deadline=deadline)]
                for chain in chains:
                    if selected_ids&set(chain['retired_track_uuids']):raise ValueError('ambiguous_source_supply_endpoint_cut')
                    selected_ids.update(chain['retired_track_uuids']);result.append(chain)
                continue
            try:authority=_bypass_supply_owner(source_board,pad,board_hint)
            except ValueError:continue  # No authority: old grouped-motion gate remains.
            with force._thermal_hint(board_hint):contract=cells._supply_current_widths(source_board,pad.GetNetname())
            if not contract:raise ValueError('source_whole_current_contract_required_for_supply_cut')
            for edge in thin:
                if edge.IsLocked()and not allow_locked:raise ValueError('locked_supply_lead_retained')
                if edge.HasSolderMask()or edge.GetWidth()<source_board.GetDesignSettings().m_TrackMinWidth or not 0<edge.GetLength()<=1500000:raise ValueError('bounded_plain_supply_pad_lead_required')
                if any(force._uid(p)!=uid and p.IsOnLayer(edge.GetLayer())and
                    edge.GetEffectiveShape(edge.GetLayer()).Collide(p.GetEffectiveShape(edge.GetLayer()),0)
                    for other in source_board.GetFootprints()for p in other.Pads()):
                    raise ValueError('supply_pad_contact_lead_has_other_land_contact')
                groups=[g for g in source_board.Groups()if g.ContainsItem(edge)]
                if len(groups)!=1 or groups[0].IsLocked()or groups[0].GetParentGroup()is not None or groups[0].GetName()!='CEC_LOCAL_ENDPOINT_NECKDOWN':raise ValueError('unique_existing_supply_endpoint_group_required')
                ends=[tuple(edge.GetStart()),tuple(edge.GetEnd())];roots=[at for at in ends if pad.HitTest(pcbnew.VECTOR2I(*at),0)]
                if len(roots)!=1:raise ValueError('single_supply_pad_contact_lead_required')
                throat=next(at for at in ends if at not in roots);full,gap=source_floor(edge)
                fixed=[t for t in tracks if t.GetClass()=='PCB_TRACK'and force._uid(t)!=force._uid(edge)and t.GetNetCode()==pad.GetNetCode()and t.GetLayer()==edge.GetLayer()and t.GetWidth()>=full and throat in(tuple(t.GetStart()),tuple(t.GetEnd()))]
                if not fixed:raise ValueError('first_fixed_full_current_junction_required')
                if new.HitTest(pcbnew.VECTOR2I(*throat),0):raise ValueError('retained_supply_junction_inside_moving_land')
                result.append(dict(kind='source_supply_pad_contact_lead_restoration',retired_track_uuids=[force._uid(edge)],pad_uuid=uid,net=pad.GetNetname(),layer_id=int(edge.GetLayer()),retained_throat_nm=list(throat),retained_throat_track_uuids=sorted(force._uid(t)for t in fixed),source_group_uuid=force._uid(groups[0]),remaining_group_members=sorted(force._uid(i)for i in groups[0].GetItems()if force._uid(i)!=force._uid(edge)),source_width_nm=edge.GetWidth(),source_authority=authority,unchanged_full_rail_current_contract=contract,width_nm=max(full,contract['required_by_layer_nm'][edge.GetLayer()]),clearance_nm=gap,old_oversized_neckdown_not_qualified=True,new_thin_allowance=False,saved_candidate_authorized=False))
    if context and any(force._hash(Path(p))!=h for p,h in context['hashes'].items()):
        raise ValueError('supply_input_source_hierarchy_changed')
    source._tick(deadline)
    return result


def component_point(component,point):
    """Exact integer geometry only, never ownership or receiving authority."""
    delta=component.get('delta_nm')
    if (type(point)not in(tuple,list)or len(point)!=2 or any(type(v)is not int for v in point)
            or type(delta)not in(tuple,list)or len(delta)!=2
            or any(type(v)is not int or abs(v)>64000000 for v in delta)):
        raise ValueError('literal_isolated_component_point_and_motion_required')
    transform=component.get('cardinal_transform')
    if transform is None:return tuple(point[k]+delta[k]for k in(0,1))
    if (type(transform)is not dict or set(transform)!={'turn_deg','source_origin_nm','candidate_origin_nm'}
            or type(transform['turn_deg'])is not int or transform['turn_deg']not in(90,180,270)
            or any(type(transform[k])not in(tuple,list)or len(transform[k])!=2
                or any(type(v)is not int for v in transform[k])
                for k in('source_origin_nm','candidate_origin_nm'))):
        raise ValueError('exact_isolated_component_cardinal_transform_required')
    c,s={90:(0,1),180:(-1,0),270:(0,-1)}[transform['turn_deg']]
    x,y=(point[k]-transform['source_origin_nm'][k]for k in(0,1))
    target=transform['candidate_origin_nm']
    return (target[0]+c*x+s*y,target[1]-s*x+c*y)


def selected_component_motion(cap,live,supply,after_supply,*,allow_cardinal_rotations=False):
    """Derive ONE common native rigid transform of both complete footprints.

    No independent capacitor placement or pad-only rotation may carry copper.
    Other terminal routing remains the enclosing complete macro's obligation.
    """
    if type(allow_cardinal_rotations)is not bool:
        raise ValueError('explicit_isolated_supply_cardinal_policy_required')
    owner=supply.GetParentFootprint();after_owner=after_supply.GetParentFootprint()
    turn=(after_owner.GetOrientationDegrees()-owner.GetOrientationDegrees())%360
    if turn not in(0,90,180,270)or turn and not allow_cardinal_rotations:
        raise ValueError('explicit_exact_isolated_supply_cardinal_motion_required')
    motion=dict(delta_nm=[b-a for a,b in zip(cap.GetPosition(),live.GetPosition())])
    if turn:
        motion['cardinal_transform']=dict(turn_deg=int(turn),source_origin_nm=list(owner.GetPosition()),
            candidate_origin_nm=list(after_owner.GetPosition()))
    if math.dist(tuple(owner.GetPosition()),tuple(after_owner.GetPosition()))>64000000:
        raise ValueError('bounded_isolated_supply_owner_motion_required')
    for old,new in((cap.GetParentFootprint(),live.GetParentFootprint()),(owner,after_owner)):
        oldpads={force._uid(p):p for p in old.Pads()};newpads={force._uid(p):p for p in new.Pads()}
        if (not oldpads.keys()==newpads.keys()or old.IsFlipped()!=new.IsFlipped()
                or (new.GetOrientationDegrees()-old.GetOrientationDegrees())%360!=turn
                or tuple(new.GetPosition())!=component_point(motion,tuple(old.GetPosition()))):
            raise ValueError('both_selected_supply_owners_require_one_exact_rigid_transform')
        for u,p in oldpads.items():
            q=newpads[u];expected=component_point(motion,tuple(p.GetPosition()))
            if (tuple(q.GetPosition())!=expected or math.dist(tuple(p.GetPosition()),expected)>64000000
                    or (q.GetOrientationDegrees()-p.GetOrientationDegrees())%360!=turn
                    or p.GetNumber()!=q.GetNumber()or p.GetNetname()!=q.GetNetname()
                    or tuple(p.GetSize())!=tuple(q.GetSize())or p.GetShape()!=q.GetShape()
                    or p.GetAttribute()!=q.GetAttribute()or tuple(p.GetOffset())!=tuple(q.GetOffset())
                    or tuple(p.GetDrillSize())!=tuple(q.GetDrillSize())
                    or set(p.GetLayerSet().Seq())!=set(q.GetLayerSet().Seq())):
                raise ValueError('complete_selected_supply_land_transform_required')
    return motion


def _same_native_surface_metal(first,second,face):
    """No motion owner is needed for literally unchanged conductive metal."""
    if (first.GetNetname()!=second.GetNetname()or first.GetNumber()!=second.GetNumber()
            or first.HasHole()or second.HasHole()
            or first.GetAttribute()!=second.GetAttribute()
            or list(first.GetLayerSet().CuStack())!=[face]
            or list(second.GetLayerSet().CuStack())!=[face]):return False
    old=first.GetEffectivePolygon(face,pcbnew.ERROR_OUTSIDE)
    new=second.GetEffectivePolygon(face,pcbnew.ERROR_OUTSIDE)
    lost=pcbnew.SHAPE_POLY_SET(old);lost.BooleanSubtract(new)
    gained=pcbnew.SHAPE_POLY_SET(new);gained.BooleanSubtract(old)
    return not lost.OutlineCount()and not gained.OutlineCount()


def isolated_components(source_board,posed,*,board_hint,source_floor,allow_locked=False,
                        timeout_s=10.,transported=False,allow_cardinal_rotations=False,
                        source_rc_input_prefixes=(),defer_independent_endpoint_reconstruction=False):
    """Exact rigid transport of a complete isolated selected-bypass component.

    This is not a cut, fixed-throat fiction, thin allowance or qualification
    of inherited neckdown debt. Only two original selected supply lands and
    their whole branch-free surface component can move together. The normal
    macro still owns every other terminal and all physical/current receiving.
    """
    import cec_decoupler_cell as cells
    import cec_fr as fr
    import cec_route_quality as quality
    from cec_measurement_leaf import _bypass_supply_owner
    if (type(allow_locked)is not bool or type(transported)is not bool
            or type(allow_cardinal_rotations)is not bool
            or type(defer_independent_endpoint_reconstruction)is not bool
            or type(board_hint)is not str or not board_hint
            or type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10):
        raise ValueError('bounded_isolated_selected_bypass_transport_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('isolated_bypass_transport_deadline')
    import cec_macro_rc_input_prefix as rc_prefix
    prefix_requests=rc_prefix.requests(source_rc_input_prefixes)
    def uid(i):return force._uid(i)
    oldpads={uid(p):p for f in source_board.GetFootprints()for p in f.Pads()}
    newpads={uid(p):p for f in posed.GetFootprints()for p in f.Pads()}
    oldtracks={uid(t):t for t in source_board.GetTracks()}
    newtracks={uid(t):t for t in posed.GetTracks()}
    if (not oldpads.keys()==newpads.keys()or not oldtracks.keys()==newtracks.keys()
            or len(oldpads)+len(oldtracks)>16384):
        raise ValueError('exact_isolated_bypass_native_population_required')
    if any(q['pad_uuid']not in oldpads for q in prefix_requests):
        raise ValueError('provisional_RC_actual_Source_input_identity_required')
    # The initial observation ignores NO foreign contact. It may carry only
    # pending identity selectors, never a clearance/retirement proof. Export
    # the complete canonical node exactly once when the transported physical
    # verification actually needs its scope; no cached success is consumed.
    prefixes=rc_prefix.provisional_prefixes(source_board,posed,board_hint=board_hint,
        identity_requests=prefix_requests,timeout_s=min(10.,max(.001,deadline-time.monotonic()))) \
        if prefix_requests and transported else []
    tick()
    def state(t):
        return (t.GetClass(),t.GetNetname(),int(t.GetLayer()),tuple(t.GetStart()),
            tuple(t.GetEnd()),int(t.GetWidth()),bool(t.IsLocked()),bool(t.HasSolderMask()))
    groups=list(source_board.Groups());newgroups={uid(g):g for g in posed.Groups()}
    graph=fr._read_only_route_connectivity(source_board)
    materials=[*oldpads.values(),*oldtracks.values(),
        *[z for z in source_board.Zones()if not z.GetIsRuleArea()]]
    result=[];seen=set()
    for fp in source_board.GetFootprints():
        tick()
        cpads=list(fp.Pads())
        if len(cpads)!=2 or {p.GetNetname()for p in cpads}=={'GND'}:continue
        power=[p for p in cpads if p.GetNetname()!='GND'and p.GetNetCode()>0]
        if len(power)!=1 or 'GND'not in {p.GetNetname()for p in cpads}:continue
        cap=power[0];live=newpads[uid(cap)]
        delta=tuple(b-a for a,b in zip(cap.GetPosition(),live.GetPosition()))
        if (delta==(0,0)and fp.GetOrientationDegrees()==live.GetParentFootprint().GetOrientationDegrees()
                and fp.GetPosition()==live.GetParentFootprint().GetPosition()):continue
        # Non-owned/shared supply components stay with their existing owner.
        try:authority=_bypass_supply_owner(source_board,cap,board_hint)
        except ValueError:continue
        # This is the SELECTED rigid-bypass constructor's work bound, not
        # a veto on every other Source-typed capacitor in a larger macro.
        # Positively selected owners retain the original64 bound exactly;
        # declining this role grants no copper motion/cut to any other cap.
        if any(abs(v)>64000000 for v in delta):
            raise ValueError('bounded_isolated_supply_literal_translation_required')
        owner=source_board.FindFootprintByReference(authority['owner'])
        supply=owner.FindPadByNumber(authority['supply_pin'])if owner else None
        model=roles.footprint_contract(owner)if owner else None
        if not supply or not model or model['pins'].get(supply.GetNumber())!='power_input':continue
        pads={uid(cap),uid(supply)}
        reached={uid(i):i for i in graph.GetConnectedItems(cap)};reached[uid(cap)]=cap
        if {u for u,i in reached.items()if i.GetClass()=='PAD'}!=pads:continue
        strokes={u:i for u,i in reached.items()if i.GetClass()=='PCB_TRACK'}
        if not strokes:continue
        if set(reached)!=pads|set(strokes):
            raise ValueError('isolated_bypass_cannot_own_barrel_zone_arc_or_other_material')
        if len(strokes)>16 or sum(t.GetLength()for t in strokes.values())>8000000:
            raise ValueError('bounded_complete_isolated_bypass_component_required')
        if set(strokes)&seen:raise ValueError('isolated_bypass_component_has_dual_selected_owner')
        face=int(cap.GetLayerSet().CuStack()[0])
        # A capacitor may pivot around its fixed supply land while only its
        # Ground return moves. If BOTH supply lands' actual copper and every
        # complete supply stroke remain exact, this owner must not demand an
        # unnecessary device rotation or claim transport of that fixed metal.
        # The enclosing macro still owns all footprint/return/partition work.
        if (delta==(0,0)and all(_same_native_surface_metal(p,newpads[uid(p)],face)
                for p in(cap,supply))and all(state(t)==state(newtracks[u])for u,t in strokes.items())):
            continue
        try:
            motion=selected_component_motion(cap,live,supply,newpads[uid(supply)],
                allow_cardinal_rotations=allow_cardinal_rotations)
        except ValueError as exc:
            if (not defer_independent_endpoint_reconstruction
                    or str(exc)!='both_selected_supply_owners_require_one_exact_rigid_transform'):
                raise
            # A complete compiler can place the device and its bypass
            # independently. That is NOT a rigid copper-transport owner.
            # Validate each complete native footprint's exact rigid pose,
            # then decline this owner without excluding or moving any edge.
            # The enclosing Source endpoint/cut compiler must own every
            # changed contact, reconstruct it at the whole-rail requirement
            # and independently receive all original native partitions.
            # No other source/identity/geometry failure is catch-and-skipped.
            for old,new in ((cap,live),(supply,newpads[uid(supply)])):
                selected_component_motion(old,new,old,new,
                    allow_cardinal_rotations=allow_cardinal_rotations)
            continue
        for pad in (cap,supply):
            q=newpads[uid(pad)];a=pad.GetParentFootprint();z=q.GetParentFootprint()
            if (pad.HasHole()or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                    or list(pad.GetLayerSet().CuStack())!=[face]
                    or pad.GetNetname()!=authority['rail']or q.GetNetname()!=pad.GetNetname()
                    or q.GetNumber()!=pad.GetNumber()or q.GetSize()!=pad.GetSize()
                    or q.GetShape()!=pad.GetShape()or q.GetAttribute()!=pad.GetAttribute()
                    or q.HasHole()
                    or list(q.GetLayerSet().CuStack())!=[face]
                    or a.IsDNP()or z.IsDNP()or a.IsFlipped()!=z.IsFlipped()
                    or a.GetValue()!=z.GetValue()or a.GetFPIDAsString()!=z.GetFPIDAsString()
                    or a.GetReference()!=z.GetReference()
                    or a.GetPath().AsString()!=z.GetPath().AsString()
                    or footprint_properties(a)!=footprint_properties(z)):
                raise ValueError('both_selected_supply_lands_require_identical_native_identity')
        if face not in(pcbnew.F_Cu,pcbnew.B_Cu):
            raise ValueError('isolated_bypass_single_source_surface_required')
        # Centreline chain topology is independent of overlapping annular
        # stroke ends; real material contact is checked separately below.
        degrees={}
        for t in strokes.values():
            tick()
            if (t.GetNetname()!=authority['rail']or int(t.GetLayer())!=face
                    or t.HasSolderMask()or not 0<t.GetWidth()<=500000 or t.GetLength()<=0
                    or not quality.is_canonical_stroke(tuple(t.GetStart()),tuple(t.GetEnd()),tolerance_nm=0)
                    or t.IsLocked()and not allow_locked):
                raise ValueError('plain_exact_locked_scope_isolated_supply_strokes_required')
            for at in(tuple(t.GetStart()),tuple(t.GetEnd())):degrees[at]=degrees.get(at,0)+1
        ends=[at for at,n in degrees.items()if n==1]
        if len(ends)!=2 or any(n not in(1,2)for n in degrees.values()):
            raise ValueError('whole_isolated_supply_component_must_be_unbranched')
        if any(sum(p.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*at),0)
                for p in(cap,supply))!=1 for at in ends):
            raise ValueError('isolated_component_endpoints_require_exact_selected_lands')
        if any(not any(p.GetEffectiveShape(face).Collide(pcbnew.VECTOR2I(*at),0)
                for at in ends)for p in(cap,supply)):
            raise ValueError('each_selected_supply_land_requires_one_chain_end')
        connected={ends[0]};pending=[ends[0]]
        while pending:
            at=pending.pop()
            for t in strokes.values():
                a,z=tuple(t.GetStart()),tuple(t.GetEnd())
                if at not in(a,z):continue
                other=z if at==a else a
                if other not in connected:connected.add(other);pending.append(other)
        if connected!=set(degrees):raise ValueError('isolated_supply_no_body_joined_extra_cycle')
        # Native connectivity must not omit a foreign contact or an opaque
        # same-net zone/body contact. Unknown fills cannot certify absence.
        for material in materials:
            tick()
            if uid(material)in reached or not material.IsOnLayer(face):continue
            if material.GetClass()=='ZONE':
                if not material.IsFilled():raise ValueError('isolated_supply_unknown_saved_fill')
                shape=material.GetFilledPolysList(face)
            else:shape=material.GetEffectiveShape(face)
            if any(shape.Collide(t.GetEffectiveShape(face),0)for t in strokes.values()):
                raise ValueError('isolated_supply_has_unowned_native_contact')
        group_rows=[]
        for g in groups:
            members={uid(i):i for i in g.GetItems()};owned=set(members)&set(strokes)
            if not owned:continue
            if (g.GetName()!='CEC_LOCAL_ENDPOINT_NECKDOWN'or g.IsLocked()or g.GetParentGroup()
                    or uid(g)not in newgroups
                    or newgroups[uid(g)].GetName()!=g.GetName()or newgroups[uid(g)].IsLocked()!=g.IsLocked()
                    or newgroups[uid(g)].GetParentGroup()
                    or {uid(i)for i in newgroups[uid(g)].GetItems()}!=set(members)
                    or any(i.GetClass()!='PCB_TRACK'for i in members.values())):
                raise ValueError('exact_partial_existing_endpoint_group_required')
            for u,item in members.items():
                if u not in owned and state(item)!=state(newtracks[u]):
                    raise ValueError('unowned_mixed_group_member_must_remain_exact')
            group_rows.append(dict(uuid=uid(g),transported_members=sorted(owned),
                stationary_members=sorted(set(members)-owned),all_members=sorted(members)))
        with force._thermal_hint(board_hint):contract=cells._supply_current_widths(source_board,authority['rail'])
        if (not contract or not contract.get('current_authority')
                or type(contract.get('required_by_layer_nm',{}).get(face))is not int
                or contract['required_by_layer_nm'][face]<=0):
            raise ValueError('isolated_supply_unchanged_whole_current_contract_required')
        rows=[]
        for u,t in sorted(strokes.items()):
            full,gap=source_floor(t);tick()
            if full<=0 or gap<=0 or t.GetWidth()<source_board.GetDesignSettings().m_TrackMinWidth:
                raise ValueError('isolated_supply_positive_original_dimension_contract_required')
            oldstate=state(t);expected=list(oldstate)
            expected[3]=component_point(motion,oldstate[3])
            expected[4]=component_point(motion,oldstate[4])
            if any(math.dist(oldstate[k],expected[k])>64000000 for k in(3,4)):
                raise ValueError('bounded_isolated_supply_whole_conductor_motion_required')
            wanted=tuple(expected)if transported else oldstate
            if state(newtracks[u])!=wanted:
                raise ValueError('isolated_supply_track_identity_width_lock_or_exact_transform_changed')
            rows.append(dict(uuid=u,source_nm=[list(t.GetStart()),list(t.GetEnd())],
                candidate_nm=[list(expected[3]),list(expected[4])],width_nm=t.GetWidth(),
                locked=bool(t.IsLocked()),source_full_width_nm=full,clearance_nm=gap))
        # These are fresh complete manufacturer RC prefixes of this SAME
        # moving device. They remain provisional foreign metal until the
        # compiler proves their mandatory retirement and fixed-port request.
        pending=[q for q in prefixes if force._uid(oldpads[q['pad_uuid']].GetParentFootprint())==uid(owner)]
        pending_ids={u for q in pending for u in q['track_uuids']}
        if any(q['net']==authority['rail']for q in pending)or pending_ids&set(reached):
            raise ValueError('provisional_RC_cannot_exempt_supply_or_same_net_contact')
        if transported:
            # A rigid internal shape may still land on an unrelated same-net
            # object. Recompile the actual child component, not only the
            # expected five strokes, and reject all new external contacts.
            child_graph=fr._read_only_route_connectivity(posed)
            actual={uid(i)for i in child_graph.GetConnectedItems(newpads[uid(cap)])}|{uid(cap)}
            if actual!=set(reached):raise ValueError('transported_isolated_supply_gained_or_lost_native_contact')
            child_material=[*newpads.values(),*newtracks.values(),
                *[z for z in posed.Zones()if not z.GetIsRuleArea()]]
            for material in child_material:
                tick()
                if uid(material)in reached or not material.IsOnLayer(face):continue
                if uid(material)in pending_ids:continue
                if material.GetClass()=='ZONE':
                    if not material.IsFilled():raise ValueError('transported_isolated_supply_unknown_fill')
                    shape=material.GetFilledPolysList(face)
                else:shape=material.GetEffectiveShape(face)
                if any(shape.Collide(newtracks[u].GetEffectiveShape(face),0)for u in strokes):
                    raise ValueError('transported_isolated_supply_has_foreign_or_unowned_contact:'+uid(material))
        proof=dict(scope='rigid_complete_isolated_selected_bypass_supply_component',
            source_selected_bypass=authority,source_manufacturer_contract=model,
            supply_pad_uuids=sorted(pads),track_uuids=sorted(strokes),layer_id=face,
            **motion,tracks=rows,partial_source_groups=group_rows,
            unchanged_full_rail_current_contract=contract,source_widths_locks_groups_retained=True,
            inherited_neckdown_debt_qualified=False,new_thin_allowance=False,
            all_other_device_terminal_obligations_remain_required=True,release_authority=False)
        if pending:proof['mandatory_source_rc_prefix_retirements']=pending
        if not transported:
            pending_requests=[q for q in prefix_requests
                if uid(oldpads[q['pad_uuid']].GetParentFootprint())==uid(owner)]
            if pending_requests:
                proof['pending_source_rc_input_prefix_requests']=pending_requests
        result.append(proof)
        seen.update(strokes)
    return result


def verify_isolated_components(source_board,posed,proofs,**options):
    """Recompile actual whole component; recorded success is never authority."""
    fresh=isolated_components(source_board,posed,transported=True,**options)
    import json
    stable=lambda q:json.loads(json.dumps(q,allow_nan=False))
    expected=stable(proofs)
    for proof in expected:
        if 'pending_source_rc_input_prefix_requests'not in proof:continue
        # A pending declaration cannot supply cut IDs, success, geometry or
        # role evidence. Only this independent fresh native/canonical replay
        # may replace its exact selectors with completed mandatory proof.
        matches=[q for q in fresh if q['supply_pad_uuids']==proof.get('supply_pad_uuids')
            and q['track_uuids']==proof.get('track_uuids')]
        pending=proof.pop('pending_source_rc_input_prefix_requests')
        if (len(matches)!=1 or 'mandatory_source_rc_prefix_retirements'in proof
                or pending!=[q['identity_request']for q in matches[0].get('mandatory_source_rc_prefix_retirements',[])]
                or not pending):
            raise ValueError('isolated_supply_pending_RC_scope_missing_partial_or_forged')
        proof['mandatory_source_rc_prefix_retirements']=matches[0]['mandatory_source_rc_prefix_retirements']
    if stable(fresh)!=expected:raise ValueError('isolated_supply_stale_or_forged_transport_proof')
    return fresh
