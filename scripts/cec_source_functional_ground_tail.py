"""Reseat one existing normal functional-Ground tail at a fixed IC terminal.

This distinct tier does not broaden the older multiface cohort operator.
Fresh manufacturer/canonical identity owns a complete single-surface linear
tail, not a force return or an arbitrary GND island. All original UUIDs,
locks, class/process dimensions and fixed root contacts survive. No new
segments, local-via process, barrel rating, current or sharing is inferred.
Saved receiving composes five independently bounded original-parent checks.
"""
import json
import math
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_source_functional_ground_cohort as native
import cec_source_ground_leaf as canonical
import cec_source_literal_additions as literal
import cec_source_retaining_ses_import as raw
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items

SCOPE='Source_fixed_terminal_normal_functional_ground_tail-v1'
MAX_TRACKS=8


def _need(value,reason):
    if not value:raise ValueError(reason)


def _deadline(seconds):
    _need(type(seconds)in(int,float)and math.isfinite(seconds)and 0<seconds<=10.,
        'bounded_functional_ground_tail_lease_required')
    return time.monotonic()+seconds


def _left(deadline):
    remaining=deadline-time.monotonic()
    _need(remaining>0,'functional_ground_tail_deadline')
    return min(10.,remaining)


def _stable(value):return json.loads(json.dumps(value,sort_keys=True,allow_nan=False))


def _surface(pad):
    faces=tuple(map(int,pad.GetLayerSet().CuStack()))
    _need(len(faces)==1 and faces[0]in(pcbnew.F_Cu,pcbnew.B_Cu),
        'functional_ground_tail_unique_actual_surface_required')
    return faces[0]


def _source_pin(board,hint,pad,deadline):
    """Actual selected measurement IC Ground; reference/NC is NOT Ground."""
    from cec_source_sideband_monitor_tap import _identity
    from cec_footprint_fields import footprint_properties
    import cec_source_netlist_semantics as semantics
    fp=pad.GetParentFootprint();properties=footprint_properties(fp);model=roles.footprint_contract(fp)
    permitted={'measurement','signal_output','power_input','ground','reference','no_connect',
        'address','signal_input','signal_io'}
    _need(model and set(model['pins'].values())<=permitted
        and {'measurement','signal_output','power_input','ground'}<=set(model['pins'].values())
        and model['pins'].get(pad.GetNumber())=='ground'
        and model['source'].startswith('https://www.ti.com/')
        and properties.get('Manufacturer')=='Texas Instruments'and properties.get('MPN')
        and roles.contract(fp.GetValue(),mpn=properties['MPN'],footprint=fp.GetFPIDAsString())==model,
        'positive_registered_measurement_IC_ground_required')
    by_pin=roles.physical_pinmap(fp,model,board_hint=hint,timeout_s=_left(deadline))
    _need(all(len(v)==1 for v in by_pin.values())and all(not p.HasHole()
        and p.GetAttribute()==pcbnew.PAD_ATTRIB_SMD
        and tuple(map(int,p.GetLayerSet().CuStack()))==(int(fp.GetLayer()),)for p in fp.Pads()),
        'complete_unique_surface_measurement_package_required')
    root=canonical.source_nc._root(board,hint)
    _need(root is not None,'functional_ground_tail_canonical_root_required')
    root=Path(root).resolve(strict=True)
    files,hashes,instances=canonical._hierarchy(root,deadline)
    tree,exporter=canonical._export(root,deadline);comps,nets,node_net=canonical._tables(tree)
    identity=_identity(board,fp.GetReference(),comps,instances,deadline)
    _,path,sf,symbol=identity
    libraries=[b for tag,b in sf.children if tag=='lib_symbols']
    _need(len(libraries)==1,'functional_ground_tail_embedded_library_required')
    embedded=canonical.synth.parse_sexpr(libraries[0]);selected=[n for n in canonical.synth._kids(embedded,'symbol')
        if len(n)>1 and n[1]==symbol['lib_id']]
    _need(len(selected)==1 and canonical.synth._first(selected[0],'extends')is None,
        'functional_ground_tail_unique_complete_symbol_required')
    todo=[selected[0]];pins={};visited=0
    while todo:
        _left(deadline);node=todo.pop();visited+=1
        _need(visited<=8192,'functional_ground_tail_symbol_inventory_bound')
        if isinstance(node,list)and node:
            if node[0]=='pin':
                number=canonical.synth._val(node,'number','')
                _need(number and number not in pins and len(node)>1,'functional_ground_tail_unique_Source_pin_required')
                pins[number]=dict(name=canonical.synth._val(node,'name',''),type=node[1])
            todo.extend(n for n in node if isinstance(n,list))
    source_pins={p['num']:p for p in symbol['pins']}
    _need(len(source_pins)==len(symbol['pins'])and pins.keys()==source_pins.keys()==model['pins'].keys(),
        'functional_ground_tail_complete_Source_pin_inventory_required')
    # Some current symbols declare stationary REF/optional-NC pins passive.
    # They remain exact Source/native contacts, NEVER movable Ground roots.
    kinds={'measurement':{'input'},'ground':{'power_in'},'reference':{'input','passive'},
        'power_input':{'power_in'},'signal_output':{'output','open_collector'},'no_connect':{'no_connect','passive'},
        'address':{'input'},'signal_input':{'input'},'signal_io':{'bidirectional'}}
    for number,lands in by_pin.items():
        _left(deadline);land=lands[0];actual=pins[number]
        _need(actual['name']and actual['type']==source_pins[number]['type']
            and actual['type']in kinds[model['pins'][number]]
            and land.GetPinType()in('',actual['type'])and land.GetPinFunction()in('',actual['name'])
            and node_net.get((fp.GetReference(),number))==str(land.GetNetname()),
            'functional_ground_tail_complete_Source_native_pin_parity_required:'+number+':'+repr(dict(
                embedded=actual,symbol=source_pins[number],manufacturer_role=model['pins'][number],
                native_type=land.GetPinType(),native_function=land.GetPinFunction(),
                export_net=node_net.get((fp.GetReference(),number)),native_net=str(land.GetNetname()))))
    pin=pad.GetNumber()
    _need(pins[pin]==dict(name='GND',type='power_in')
        and canonical._pin(identity,pin)['type']=='power_in'
        and node_net.get((fp.GetReference(),pin))=='GND',
        'functional_ground_tail_actual_named_connected_Ground_required')
    _need(hashes=={str(p):force._hash(p)for p in files},'functional_ground_tail_Source_changed')
    _left(deadline)
    return dict(model=model,owner_uuid=force._uid(fp),owner_reference=fp.GetReference(),pin=pin,
        source_root=str(root),source_sheet=str(path),symbol_uuid=symbol['uuid'],lib_id=symbol['lib_id'],
        schematic_files_sha256=hashes,
        exporter=semantics.replay_identity(dict(exporter=exporter))['exporter'],Source_pin_inventory=pins,
        functional_ground_return=True,current_authority=False,release_authority=False)


def _polygon(item,face,error):
    from cec_source_class_ground_literal_endpoint_tail import _polygon as polygon
    return polygon(item,face,error)


def _root_contact(t,peer,pad,face,root,deadline):
    """Conservative native overlap must lie wholly inside the REAL fixed land.

    A short first leg can put the following bend inside the same owner land.
    The complete path still starts at the exact fixed Source root; requiring
    *every* touching leg to repeat that endpoint confuses path serialization
    with a physical contact. Retained peer tracks must still terminate at
    that Source root, and their entire overlap must fit the actual land.
    """
    _left(deadline)
    is_owner=peer.GetClass()=='PAD'and force._uid(peer)==force._uid(pad)
    if not is_owner and(peer.GetClass()!='PCB_TRACK'
            or root not in(tuple(peer.GetStart()),tuple(peer.GetEnd()))):return False
    overlap=_polygon(t,face,pcbnew.ERROR_OUTSIDE)
    overlap.BooleanIntersection(_polygon(peer,face,pcbnew.ERROR_OUTSIDE))
    if not overlap.OutlineCount():return False
    if is_owner:return True
    overlap.BooleanSubtract(_polygon(pad,face,pcbnew.ERROR_INSIDE))
    return overlap.OutlineCount()==0


def _contacts(board,tracks,via,pad,deadline):
    face=_surface(pad);root=tuple(pad.GetPosition());owned={force._uid(t)for t in tracks}|{force._uid(via)}
    peers=[*board.GetTracks(),*(p for f in board.GetFootprints()for p in f.Pads())]
    _need(len(peers)<=16384,'functional_ground_tail_contact_inventory_bound')
    enabled=tuple(map(int,board.GetEnabledLayers().CuStack()));bounds={};root_contacts=set()
    for zone in board.Zones():
        _left(deadline)
        if zone.GetIsRuleArea()or not zone.IsOnLayer(face):continue
        _need(zone.IsFilled(),'functional_ground_tail_unknown_saved_surface_fill')
        _need(not any(t.GetEffectiveShape(face).Collide(zone.GetFilledPolysList(face),0)for t in tracks),
            'functional_ground_tail_unowned_surface_zone_contact')
    # The barrel has exactly the final chain stroke, not a hidden shortcut
    # to an earlier round cap. Nonadjacent strokes may not touch at all.
    _need([i for i,t in enumerate(tracks)if native._contact(via,t,face,bounds)]==[len(tracks)-1],
        'functional_ground_tail_barrel_has_hidden_owned_shortcut')
    for peer in peers:
        _left(deadline)
        if force._uid(peer)in owned:continue
        if any(native._contact(via,peer,f,bounds)for f in enabled if peer.IsOnLayer(f)):
            raise ValueError('functional_ground_tail_barrel_has_unowned_native_contact:'+force._uid(peer))
        for t in tracks:
            if not native._contact(t,peer,face,bounds):continue
            _need(peer.GetNetCode()==pad.GetNetCode()and _root_contact(t,peer,pad,face,root,deadline),
                'functional_ground_tail_unowned_interior_contact:'+force._uid(peer))
            root_contacts.add(force._uid(peer))
    _need(force._uid(pad)in root_contacts,'functional_ground_tail_actual_fixed_root_contact_required')
    for i,t in enumerate(tracks):
        for j,peer in enumerate(tracks[i+1:],i+1):
            if native._contact(t,peer,face,bounds):
                _need(j==i+1 and len({tuple(t.GetStart()),tuple(t.GetEnd())}&{tuple(peer.GetStart()),tuple(peer.GetEnd())})==1,
                    'functional_ground_tail_hidden_crossing_or_round_cap_shortcut')
    return sorted(root_contacts)


def plan(source,*,board_hint,owner_pad_uuid,via_uuid,locked_item_uuids=(),timeout_s=10.):
    deadline=_deadline(timeout_s);source=Path(source).resolve(strict=True)
    _need(type(board_hint)is str and board_hint,'functional_ground_tail_explicit_Source_hint_required')
    locks=ordinary._ids(locked_item_uuids,'functional_ground_tail_explicit_locks',MAX_TRACKS+1)
    board=pcbnew.LoadBoard(str(source));family=force._family(source,board_hint);epoch=force._code_identity()
    pads={force._uid(p):p for f in board.GetFootprints()for p in f.Pads()};live={force._uid(t):t for t in board.GetTracks()}
    _need(owner_pad_uuid in pads and via_uuid in live,'functional_ground_tail_exact_Source_items_required')
    pad,via=pads[owner_pad_uuid],live[via_uuid];face=_surface(pad)
    _need(pad.GetNetname()=='GND'and pad.GetNetCode()>0 and not pad.HasHole()
        and pad.GetAttribute()==pcbnew.PAD_ATTRIB_SMD and not pad.GetParentFootprint().IsDNP()
        and face in(pcbnew.F_Cu,pcbnew.B_Cu),'functional_ground_tail_actual_surface_Ground_required')
    source_pin=_source_pin(board,board_hint,pad,deadline)
    _need(via.GetClass()=='PCB_VIA'and via.GetNetCode()==pad.GetNetCode()
        and via.GetViaType()==pcbnew.VIATYPE_THROUGH and via.TopLayer()==pcbnew.F_Cu and via.BottomLayer()==pcbnew.B_Cu,
        'functional_ground_tail_existing_normal_full_depth_barrel_required')
    import cec_route_dimensions as dimensions
    spec=fr._project_netclass_resolver(str(source),board=board)('GND')or{}
    _need(all(spec.get(k)for k in('track_width','clearance','via_diameter','via_drill')),
        'functional_ground_tail_original_Ground_class_required')
    limits=dimensions.board_limits(board);width=math.ceil(max(spec['track_width'],limits['track_width'])*1e6)
    gap=max(int(board.GetDesignSettings().m_MinClearance),math.ceil(spec['clearance']*1e6))
    diameter=int(via.GetWidth(pcbnew.F_Cu));drill=int(via.GetDrillValue())
    normal=dimensions.ordinary_via_geometry(spec,limits,requested=(diameter/1e6,drill/1e6))
    _need(diameter>=math.ceil(normal[0]*1e6)and drill>=math.ceil(normal[1]*1e6)>0
        and all(via.GetWidth(l)==diameter for l in board.GetEnabledLayers().CuStack()),
        'functional_ground_tail_unchanged_normal_process_and_class_floor_required')
    import cec_native_via_land_context as lands
    lands.inspect(board,via,at=via.GetPosition(),maximum_diameter_nm=diameter,drill_nm=drill,
        net_code=via.GetNetCode(),clearance_nm=gap)
    grouped={force._uid(i)for g in board.Groups()for i in g.GetItems()}
    _need(via.GetParentGroup()is None and via_uuid not in grouped,'functional_ground_tail_grouped_barrel_not_owned')
    candidates=[t for t in live.values()if t.GetClass()=='PCB_TRACK'and t.GetNetCode()==pad.GetNetCode()]
    incident=[t for t in candidates if any(native._contact(t,via,l)for l in board.GetEnabledLayers().CuStack()if t.IsOnLayer(l))]
    _need(len(incident)==1 and int(incident[0].GetLayer())==face,
        'functional_ground_tail_exactly_one_surface_departure_required')
    axis=tuple(via.GetPosition());root=tuple(pad.GetPosition());cursor=axis;chain=[];seen=set()
    while True:
        _left(deadline)
        peers=[t for t in candidates if force._uid(t)not in seen and cursor in(tuple(t.GetStart()),tuple(t.GetEnd()))]
        _need(len(peers)==1,'functional_ground_tail_unbranched_literal_Source_chain_required')
        t=peers[0];uid=force._uid(t);a,z=tuple(t.GetStart()),tuple(t.GetEnd())
        _need(int(t.GetLayer())==face and t.GetWidth()==width and uid not in grouped and t.GetParentGroup()is None
            and not t.HasSolderMask()and a!=z and(a[0]==z[0]or a[1]==z[1]or abs(a[0]-z[0])==abs(a[1]-z[1]))
            and t.GetLength()<=8000000,'functional_ground_tail_exact_ungrouped_class_Source_strokes_required')
        chain.append(t);seen.add(uid);_need(len(chain)<=MAX_TRACKS,'functional_ground_tail_work_bound')
        cursor=z if cursor==a else a
        if cursor==root:break
    chain.reverse();points=[list(root)];cursor=root
    for t in chain:
        cursor=tuple(t.GetEnd())if cursor==tuple(t.GetStart())else tuple(t.GetStart());points.append(list(cursor))
    owned=[*chain,via];actual_locks={force._uid(t)for t in owned if t.IsLocked()}
    _need(locks==actual_locks,'functional_ground_tail_all_and_only_Source_locks_must_be_explicit')
    roots=_contacts(board,chain,via,pad,deadline)
    import cec_ground_return_shortcut as reference
    contacts=reference._reference_contacts(board,via)
    _need(len({f for _,f in contacts})>=2,'functional_ground_tail_two_actual_Source_reference_planes_required')
    observed=__import__('cec_decoupler_cell')._existing_return(board,pad,16.,allow_native_track_body=True)
    _need(observed is not None and force._uid(observed[1])==via_uuid,
        'functional_ground_tail_actual_selected_Source_return_required')
    _need(family==force._family(source,board_hint)and epoch==force._code_identity(),'functional_ground_tail_Source_epoch_changed')
    _left(deadline)
    return _stable(dict(schema=1,scope=SCOPE,source=str(source),source_sha256=force._hash(source),source_family=family,
        code_identity=epoch,board_hint=board_hint,owner_pad_uuid=owner_pad_uuid,via_uuid=via_uuid,
        locked_item_uuids=sorted(locks),track_uuids=[force._uid(t)for t in chain],source_points_nm=points,
        face=face,width_nm=width,clearance_nm=gap,diameter_nm=diameter,drill_nm=drill,
        source_length_nm=sum(t.GetLength()for t in chain),actual_Source_return_mm=observed[0],fixed_root_contact_uuids=roots,
        reference_contacts=contacts,Source_pin=source_pin,no_Source_retirement_or_new_segments=True,
        current_authority=False,barrel_capacity_qualified=False,routing_admitted=False,release_authority=False))


def _assess(board,q,points,deadline):
    _need(type(points)in(list,tuple)and len(points)==len(q['source_points_nm'])
        and all(type(p)in(list,tuple)and len(p)==2 and all(type(v)is int and abs(v)<=2000000000 for v in p)for p in points),
        'functional_ground_tail_exact_cardinality_integer_path_required')
    _need(list(points[0])==q['source_points_nm'][0]and 0<math.dist(points[-1],q['source_points_nm'][-1])<=1000000,
        'functional_ground_tail_fixed_root_and_one_mm_barrel_motion_required')
    _need(len({tuple(p)for p in points})==len(points),'functional_ground_tail_repeated_vertex_or_cycle')
    _need(sum(math.dist(a,z)for a,z in zip(points,points[1:]))<=q['source_length_nm']+1,
        'functional_ground_tail_must_not_lengthen_Source_return')
    live={force._uid(t):t for t in board.GetTracks()};via=live[q['via_uuid']];tracks=[live[u]for u in q['track_uuids']]
    pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==q['owner_pad_uuid'])
    for t,a,z in zip(tracks,points,points[1:]):
        _need(a!=z and(a[0]==z[0]or a[1]==z[1]or abs(a[0]-z[0])==abs(a[1]-z[1])),
            'functional_ground_tail_canonical_full_Source_strokes_required')
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
    via.SetPosition(pcbnew.VECTOR2I(*points[-1]))
    _need(_contacts(board,tracks,via,pad,deadline)==q['fixed_root_contact_uuids'],
        'functional_ground_tail_fixed_native_contacts_changed')
    basis=pcbnew.LoadBoard(q['source']);owned=set(q['track_uuids'])|{q['via_uuid']}
    discard_items(basis,[t for t in basis.GetTracks()if force._uid(t)in owned])
    gap=q['clearance_nm'];nc=pad.GetNetCode();cache={};detail={}
    _need(fr._edge_leg_clear(basis,via.GetPosition(),via.GetPosition(),(q['diameter_nm']+1)//2+gap)
        and fr._via_spot_clear(basis,via.GetPosition(),q['diameter_nm'],gap,{nc},drill_nm=q['drill_nm'],
            net_code=nc,foreign_cache=cache,report=detail),'functional_ground_tail_all_face_normal_via_guard_refused:'+repr(detail))
    import cec_source_rule_signal_launches as immutable
    _need(all(immutable._immutable_power_clear(basis,via.GetPosition(),via.GetPosition(),q['diameter_nm'],int(f),gap,nc)
        for f in basis.GetEnabledLayers().CuStack()),'functional_ground_tail_immutable_power_column_conflict')
    ops=[]
    for t in tracks:
        _left(deadline)
        _need(fr._edge_leg_clear(basis,t.GetStart(),t.GetEnd(),(t.GetWidth()+1)//2+gap)
            and fr._tap_foreign_clear(basis,t.GetStart(),t.GetEnd(),t.GetWidth(),q['face'],gap,{nc},foreign_cache=cache)
            and immutable._immutable_power_clear(basis,t.GetStart(),t.GetEnd(),t.GetWidth(),q['face'],gap,nc),
            'functional_ground_tail_native_full_width_path_guard_refused')
        ops.append(('trk',t.GetStart(),t.GetEnd(),t.GetWidth(),q['face']))
    ops.append(('via',via.GetPosition(),q['drill_nm']/1e6,q['diameter_nm']/1e6))
    from cec_route_proposal_guard import RouteProposalGuard
    guard=RouteProposalGuard(basis,'GND',board_path=q['source'],board_hint=q['board_hint'],
        netclass_resolver=fr._project_netclass_resolver(q['source']),deadline=deadline,
        preflight_s=min(9.1,_left(deadline)))
    _need(guard(ops)is True,'functional_ground_tail_new_craft_or_field_refused:'+repr(guard.report()))
    return dict(complete=True,ok=True,native_column=detail,craft_and_field=guard.report(),
        fixed_root_contacts_retained=True,all_actual_faces_and_immutable_power_checked=True)


def _stencil(source,generated,q):
    text=raw.raw_text(source);positions=raw.inventory(text);nodes=literal._inventory(raw.raw_text(generated))[0]
    for uid in sorted([*q['track_uuids'],q['via_uuid']],key=lambda u:positions[u][0],reverse=True):
        a,z=positions[uid];node=text[a:z]
        for name in(('at',)if uid==q['via_uuid']else('start','end')):
            old=literal._child(node,name);new=literal._child(nodes[uid][2],name)
            _need(old is not None and new is not None,'functional_ground_tail_exact_native_pose_children_required')
            x,y=old;u,v=new;node=node[:x]+nodes[uid][2][u:v]+node[y:]
        text=text[:a]+node+text[z:]
    return text


def write_private(q,directory,points_nm,*,timeout_s=10.):
    deadline=_deadline(timeout_s)
    fresh=plan(q['source'],board_hint=q['board_hint'],owner_pad_uuid=q['owner_pad_uuid'],via_uuid=q['via_uuid'],
        locked_item_uuids=q['locked_item_uuids'],timeout_s=_left(deadline))
    _need(fresh==q,'functional_ground_tail_stale_or_forged_Source_proposal')
    board=pcbnew.LoadBoard(q['source']);geometry=_assess(board,q,points_nm,deadline);ground=additive._ground_refill(board)
    target=force._copy_family(Path(q['source']),Path(directory))
    with tempfile.TemporaryDirectory(prefix='cec-fixed-Ground-tail-save-')as work:
        generated=Path(work)/'native.kicad_pcb';field._save_field_snapshot(board,generated)
        raw.write_raw(target,literal.assemble(_stencil(Path(q['source']),generated,q),raw.raw_text(generated),ground_ids=ground))
    _need(force._code_identity()==q['code_identity']and force._family(Path(q['source']),q['board_hint'])==q['source_family'],
        'functional_ground_tail_Source_changed_during_write')
    _left(deadline)
    return dict(complete=True,candidate=str(target),candidate_sha256=force._hash(target),geometry=geometry,
        independent_saved_receiving_still_required=True,routing_admitted=False,release_authority=False)


def receive(source,candidate,*,board_hint,owner_pad_uuid,via_uuid,locked_item_uuids=(),timeout_s=10.):
    """Five finite <=timeout_s constituents; never a skipped/expired predicate.

    The total bound is five times the per-constituent limit. Each new lease
    follows a COMPLETED prior proof and an unchanged Source/child/code epoch.
    Native DRC, actual current debt and global qualification remain enclosing
    pipeline gates, not permissions supplied by this local operator.
    """
    _deadline(timeout_s);started=time.monotonic()
    r=dict(schema=1,scope=SCOPE,complete=False,ok=False,phases={},errors=[],maximum_constituents=5,
        per_constituent_limit_s=timeout_s,current_authority=False,barrel_capacity_qualified=False,
        routing_admitted=False,release_authority=False,whole_shared_stage_still_required=True)
    stage='fresh_Source'
    try:
        source,candidate=map(lambda p:Path(p).resolve(strict=True),(source,candidate));_need(source!=candidate,'distinct_functional_ground_tail_paths_required')
        code=force._code_identity();families=[force._family(p,board_hint)for p in(source,candidate)]
        def begin(name):
            _need(code==force._code_identity()and families==[force._family(p,board_hint)for p in(source,candidate)],
                'functional_ground_tail_saved_epoch_changed')
            r['phases'][name]=dict(started_s=time.monotonic()-started);return _deadline(timeout_s)
        def finish(name,deadline,**values):
            _left(deadline);r['phases'][name].update(values,complete=True,elapsed_s=time.monotonic()-started-r['phases'][name]['started_s'])
        deadline=begin(stage)
        q=plan(source,board_hint=board_hint,owner_pad_uuid=owner_pad_uuid,via_uuid=via_uuid,
            locked_item_uuids=locked_item_uuids,timeout_s=_left(deadline));r['independent_Source_proposal']=q
        _need(force._sidecars(source)==force._sidecars(candidate),'functional_ground_tail_sidecars_changed')
        finish(stage,deadline)
        stage='exact_native_scope';deadline=begin(stage)
        parent,child=map(lambda p:pcbnew.LoadBoard(str(p)),(source,candidate))
        old=literal._inventory(raw.raw_text(source))[0];new=literal._inventory(raw.raw_text(candidate))[0]
        parsed_old=additive._nodes(source)[1];parsed_new=additive._nodes(candidate)[1]
        _need(old.keys()==new.keys(),'functional_ground_tail_no_new_or_retired_Source_objects')
        owned=set(q['track_uuids'])|{via_uuid};ground={force._uid(z)for z in parent.Zones()if not z.GetIsRuleArea()and z.GetNetname()=='GND'}
        for uid,(_,_,node)in old.items():
            _left(deadline)
            if uid in owned:
                fields=('at',)if uid==via_uuid else('start','end')
                for name in fields:
                    span=literal._child(node,name);got=literal._child(new[uid][2],name)
                    _need(span is not None and got is not None,'functional_ground_tail_pose_field_missing')
                first=additive.sexpr._freeze([v for v in parsed_old[uid]if not(isinstance(v,list)and v and v[0]in fields)])
                last=additive.sexpr._freeze([v for v in parsed_new[uid]if not(isinstance(v,list)and v and v[0]in fields)])
                _need(first==last,'functional_ground_tail_Source_process_or_lock_changed')
            elif uid in ground:
                a=parsed_old[uid];b=parsed_new[uid]
                _need(additive._without(a,'filled_polygon')==additive._without(b,'filled_polygon'),
                    'functional_ground_tail_authored_Ground_zone_changed')
            else:_need(node==new[uid][2],'functional_ground_tail_unowned_literal_changed:'+uid)
        live={force._uid(t):t for t in child.GetTracks()};points=[q['source_points_nm'][0]]
        cursor=tuple(points[0])
        for uid in q['track_uuids']:
            t=live[uid];_need(tuple(t.GetStart())==cursor,'functional_ground_tail_exact_ordered_Source_path_required')
            cursor=tuple(t.GetEnd());points.append(list(cursor))
        _need(list(live[via_uuid].GetPosition())==points[-1],'functional_ground_tail_actual_barrel_axis_required')
        reconstructed=pcbnew.LoadBoard(str(source));geometry=_assess(reconstructed,q,points,deadline)
        finish(stage,deadline,geometry=geometry)
        stage='native_returns_and_partitions';deadline=begin(stage)
        import cec_native_partition_pair as partitions
        import cec_ground_return_preservation as returns
        import cec_ground_return_shortcut as reference
        shared=partitions.compare(parent,child,timeout_s=_left(deadline))
        _need(shared.get('available')is True and shared.get('preserved')is True,'functional_ground_tail_Source_partition_lost')
        returned=returns.receive(parent,child,timeout_s=_left(deadline))
        _need(returned.get('complete')is True and returned.get('ok')is True,'functional_ground_tail_known_return_worsened')
        _need(set(map(tuple,reference._reference_contacts(child,live[via_uuid])))>=set(map(tuple,q['reference_contacts'])),
            'functional_ground_tail_Source_plane_contact_lost')
        finish(stage,deadline,native_partitions={k:v for k,v in shared.items()if k not in('source_parts','child_parts','demoted_parts')},all_known_returns=returned)
        stage='independent_literal_refill_replay';deadline=begin(stage)
        with tempfile.TemporaryDirectory(prefix='cec-fixed-Ground-tail-receive-')as work:
            projected=force._copy_family(source,Path(work)/'projected');generated=Path(work)/'posed.kicad_pcb'
            field._save_field_snapshot(reconstructed,generated);raw.write_raw(projected,_stencil(source,generated,q))
            replay=additive.receive(projected,candidate,board_hint=board_hint,timeout_s=_left(deadline))
        _need(replay.get('complete')is True and replay.get('ok')is True and replay.get('existing_ground_fill_matches_independent_native_replay')is True,
            'functional_ground_tail_saved_refill_or_literal_replay_refused')
        finish(stage,deadline,replay=replay)
        stage='actual_parent_whole_field';deadline=begin(stage)
        before=field.field_coupling_summary(str(source),board=parent,board_hint=board_hint,
            _work=field._ProposalWork(deadline,16384,1000000,1000000,16384))
        with tempfile.TemporaryDirectory(prefix='cec-fixed-Ground-tail-field-')as work:
            path=force._copy_family(candidate,Path(work)/'private');private=pcbnew.LoadBoard(str(path));additive._ground_refill(private)
            after=field.field_coupling_summary(str(path),board=private,board_hint=board_hint,
                _work=field._ProposalWork(deadline,16384,1000000,1000000,16384))
        oldkeys=field.blocker_keys(before);introduced=[v for v in after['interactions']if v.get('blocking')
            and next(iter(field.blocker_keys(dict(interactions=[v]))))not in oldkeys]
        _need(not introduced,'functional_ground_tail_new_actual_parent_field_blocker')
        finish(stage,deadline,source_blocking_count=before['blocking_count'],candidate_blocking_count=after['blocking_count'],
            actual_parent_old_old_interactions_compared=True)
        _need(all(force._hash(Path(p))==h for p,h in q['Source_pin']['schematic_files_sha256'].items()),
            'functional_ground_tail_final_Source_hierarchy_changed')
        _need(force._hash(Path(q['Source_pin']['exporter']['exporter']))==q['Source_pin']['exporter']['exporter_sha256'],
            'functional_ground_tail_final_exporter_changed')
        _need(code==force._code_identity()and families==[force._family(p,board_hint)for p in(source,candidate)],
            'functional_ground_tail_final_saved_epoch_changed')
        _left(deadline)
        r.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),code_identity=code,
            all_original_UUIDs_locks_groups_process_and_contacts_preserved=True,new_objects=0,retired_objects=0,
            original_normal_process_and_current_requirements_unchanged=True)
    except Exception as exc:r['errors'].append(type(exc).__name__+':'+str(exc));r['failed_stage']=stage
    r['elapsed_s']=time.monotonic()-started
    return r
