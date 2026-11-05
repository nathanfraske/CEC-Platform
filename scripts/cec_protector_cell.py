"""Complete Source-owned passive protector ports and bounded reconstruction.

The selected manufacturer, current hierarchy and actual native six lands
must agree. Pair copper, one exact full-class Ground leaf and a previously
isolated clamp reference are distinct mandatory domains. No ordinary-net,
load, internally-connected-pad, pose or release waiver follows from the part
name. This constructor never selects or admits a saved candidate.
"""
import json
import math
from pathlib import Path
import subprocess
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_device_power_roles as roles
import cec_force_current as force
import cec_fr as fr
import cec_decoupler_cell as cells
import cec_measurement_leaf as leaf
import cec_paired_route_reconstruction as paired
import cec_precision_route as precision
import cec_source_ground_leaf as source_pin
import cec_source_no_connect as source_nc
import cec_sch_lint as sch
import cec_synth_pipeline as synth
import cec_full_current_planar_reflow as full
import cec_source_current_ports as source_ports
from cec_source_current_ports import port as _port, aggregate_ports as _aggregate_ports, stroke_port as _stroke_port
from cec_footprint_fields import footprint_properties
from cec_native_items import discard_items


def _deadline(seconds):
    if type(seconds)not in(int,float)or not math.isfinite(seconds)or not 0<seconds<=10.:
        raise ValueError('bounded_protector_constituent_required')
    return time.monotonic()+seconds


def _remaining(deadline):
    left=deadline-time.monotonic()
    if left<=0:raise ValueError('protector_constituent_deadline')
    return min(10.,left)


def _stable(value):return json.loads(json.dumps(value,allow_nan=False))


def _owner(board,uid):
    fps=[fp for fp in board.GetFootprints() if force._uid(fp)==uid]
    if len(fps)!=1:raise ValueError('unique_native_protector_owner_required')
    fp=fps[0];model=roles.passive_steering_protector_contract(fp)
    if (model is None or fp.IsLocked() or any(g.ContainsItem(fp)for g in board.Groups())):
        raise ValueError('unlocked_ungrouped_exact_selected_protector_required')
    return fp,model


def _source_symbol(board,fp,model,hint,deadline):
    root=source_nc._root(board,hint)
    if root is None:raise ValueError('current_protector_hierarchy_required')
    root=root.resolve()
    files,hashes,instances=source_pin._hierarchy(root,deadline)
    tree,exporter=source_pin._export(root,deadline)
    comps,nets,node_net=source_pin._tables(tree)
    identity=source_pin._identity(board,fp.GetReference(),comps,instances,deadline)
    _,path,sf,symbol=identity
    blocks=[b for tag,b in sf.children if tag=='symbol'and sch.prop_value(b,'Reference')==fp.GetReference()]
    exported={synth._val(p,'name',''):synth._val(p,'value','')
        for p in synth._kids(comps[fp.GetReference()],'property')}
    fields=footprint_properties(fp)
    for field in ('Manufacturer','LCSC'):
        if (len(blocks)!=1 or sch.prop_value(blocks[0],field)!=fields[field]
                or exported.get(field)!=fields[field]):
            raise ValueError('protector_actual_source_selection_mismatch:'+field)
    libs=[b for tag,b in sf.children if tag=='lib_symbols']
    if len(libs)!=1:raise ValueError('protector_embedded_source_library_required')
    library=synth.parse_sexpr(libs[0])
    selected=[node for node in synth._kids(library,'symbol')if len(node)>1 and node[1]==symbol['lib_id']]
    if len(selected)!=1 or synth._first(selected[0],'extends')is not None:
        raise ValueError('protector_complete_embedded_symbol_required')
    todo=[selected[0]];pins=[];visited=0
    while todo:
        _remaining(deadline);node=todo.pop();visited+=1
        if visited>8192:raise ValueError('protector_source_symbol_bound')
        if isinstance(node,list)and node:
            if node[0]=='pin':pins.append(node)
            todo.extend(child for child in node if isinstance(child,list))
    if len(pins)!=6 or {synth._val(p,'number','')for p in pins}!=set(model['pins']):
        raise ValueError('protector_all_six_source_pins_required')
    records=[]
    for pad in fp.Pads():
        _remaining(deadline);num=pad.GetNumber()
        actual=next(p for p in pins if synth._val(p,'number','')==num)
        endpoint=source_pin._pin(identity,num)
        if (actual[1]!=model['source_pin_type'] or endpoint['type']!=model['source_pin_type']
                or synth._val(actual,'name','')!=model['source_pin_functions'][num]
                or node_net.get((fp.GetReference(),num))!=pad.GetNetname()):
            raise ValueError('protector_source_native_manufacturer_pin_mismatch:'+num)
        # Every actual native peer on the IO/clamp nets must be exported too.
        # No extra PCB-only land or old exported netlist can silently join.
        net=str(pad.GetNetname())
        if num!='2':
            native={(f.GetReference(),p.GetNumber())for f in board.GetFootprints()for p in f.Pads()
                if p.GetNetname()==net}
            if native!=nets.get(net,set()):
                raise ValueError('protector_source_native_complete_net_membership_mismatch:'+num)
        records.append(dict(pad_uuid=force._uid(pad),pin=num,net=net,
            source_function=synth._val(actual,'name',''),source_type=actual[1]))
    if hashes!={str(p):force._hash(p)for p in files}:
        raise ValueError('protector_source_hierarchy_changed')
    # Only the already-standard full-export-tree semantic digest survives
    # a fresh recompile. The generated design-date byte digest is not design
    # authority; every other export node, CLI binary and Source file remains
    # bound. Never drop a component/net/property or accept a stale export.
    export_identity={k:v for k,v in exporter.items()if k!='netlist_sha256'}
    # Reuse this very export for the fitted-component model as well.  A
    # second CLI call is neither needed nor a substitute for pin identity.
    # These are electrical declarations, not copper or conductor capacity.
    import cec_component_jumper_metadata as jumper
    exported_jumper_contract=jumper.from_export_tree(tree).get(fp.GetReference())
    if exported_jumper_contract is None:
        raise ValueError('protector_complete_exported_component_required')
    return dict(root=str(root),files_sha256=hashes,exporter=export_identity,
        symbol_uuid=symbol['uuid'],sheet=str(path),pins=sorted(records,key=lambda r:r['pin']),
        exported_component_jumper_contract=exported_jumper_contract,
        fresh_export=True,complete_native_peer_membership=True)


def _frame(source,owner_uuid,board_hint,pair_name,deadline):
    source=Path(source).resolve(strict=True)
    if source.suffix!='.kicad_pcb' or type(board_hint)is not str or not board_hint:
        raise ValueError('named_saved_protector_source_context_required')
    family=force._family(source,board_hint);epoch=force._code_identity()
    board=pcbnew.LoadBoard(str(source));binding=row._source_binding(board)
    fp,model=_owner(board,owner_uuid)
    symbol=_source_symbol(board,fp,model,board_hint,deadline)
    cut=paired.plan(board,source,board_hint=board_hint,pair_name=pair_name,
        preserve_native_pad_barrels=True,allow_source_width_repair=True)
    pair=cut['pair'];banks=model['io_banks']
    bank_nets=[str(fp.FindPadByNumber(bank[0]).GetNetname())for bank in banks]
    if set(bank_nets)!={pair['p'],pair['n']}:
        raise ValueError('protector_actual_banks_must_match_complete_declared_pair')
    pad_ids={force._uid(p)for p in fp.Pads()}
    kept=cut['source_barrel_classification']['pad_witnesses']
    if any(w['pad_uuid']in pad_ids for w in kept):
        raise ValueError('protector_pad_barrel_motion_needs_separate_exact_owner')
    ground_pad=fp.FindPadByNumber(model['ground_pin'])
    ground=leaf.plan_source_class_ground(board,force._uid(ground_pad),timeout_s=_remaining(deadline))
    live={force._uid(t):t for t in board.GetTracks()}
    if (len(ground['boundary_uuids'])!=1 or ground['boundary_uuids'][0]not in live
            or live[ground['boundary_uuids'][0]].GetClass()!='PCB_VIA'):
        raise ValueError('protector_ground_leaf_needs_exact_retained_barrel_boundary')
    from cec_ground_return_shortcut import _reference_contacts
    references=_reference_contacts(board,live[ground['boundary_uuids'][0]])
    witness=cells._existing_return(board,ground_pad,16.,allow_native_track_body=True)
    if witness is None:raise ValueError('protector_source_ground_return_unknown')
    clamp=fp.FindPadByNumber(model['clamp_reference_pin'])
    graph=fr._read_only_route_connectivity(board)
    if any(force._uid(item)!=force._uid(clamp)for item in graph.GetConnectedItems(clamp)):
        raise ValueError('protector_connected_clamp_needs_complete_retained_source_leaf_owner')
    kind,domain,contract=full._model(board,source,str(clamp.GetNetname()),board_hint)
    if kind!='aggregate_source_sink' or domain is None:
        raise ValueError('protector_explicit_complete_aggregate_clamp_domain_required')
    anchors=_aggregate_ports(board,source,str(clamp.GetNetname()),domain,contract,deadline)
    with force._thermal_hint(board_hint):current=cells._supply_current_widths(board,str(clamp.GetNetname()))
    if current is None or current['current_authority']!=contract['current_authority']:
        raise ValueError('protector_unchanged_positive_clamp_current_contract_required')
    q=dict(schema=1,scope='source_typed_complete_passive_protector_cell',source=str(source),
        source_sha256=force._hash(source),source_family=family,code_identity=epoch,
        source_native_binding=binding,board_hint=board_hint,owner_uuid=owner_uuid,owner_ref=fp.GetReference(),
        source_pose=[fp.GetPosition().x/1e6,fp.GetPosition().y/1e6,fp.GetOrientationDegrees()],
        manufacturer=model,source_symbol=symbol,pair_plan=cut,ground_leaf=ground,
        source_ground_return_mm=witness[0],source_ground_reference_contacts=references,
        ground_pad_uuid=force._uid(ground_pad),clamp_pad_uuid=force._uid(clamp),
        clamp_source_isolated=True,clamp_current_contract=current,clamp_domain=domain,
        clamp_aggregate_source_ports=anchors,
        retired_track_uuids=sorted(set(cut['retired_track_uuids'])|set(ground['track_uuids'])),
        retired_via_uuids=cut['retired_via_uuids'],
        mandatory_domains=['functional_ground','aggregate_clamp_reference','whole_declared_pair'],
        all_four_IO_lands_mandatory=True,internal_pin_short_not_native_connectivity_credit=True,
        original_parts_pinout_power_pours_and_outline_immutable=True,
        complete_saved_receiving_still_required=True,routing_admitted=False,
        current_qualified=False,fab_ready=False,release_authority=False)
    if (row._source_binding(board)!=binding or force._family(source,board_hint)!=family
            or force._code_identity()!=epoch):raise ValueError('protector_source_epoch_changed')
    _remaining(deadline)
    return board,q


def _project(parent,q,target_pose,max_shift_mm):
    if (type(target_pose)not in(list,tuple)or len(target_pose)!=3
            or any(type(v)not in(int,float)or not math.isfinite(v)for v in target_pose)
            or type(max_shift_mm)not in(int,float)or not math.isfinite(max_shift_mm)
            or not 0<max_shift_mm<=32.):
        raise ValueError('bounded_complete_protector_pose_required')
    old=q['source_pose'];turn=(target_pose[2]-old[2])%360
    if turn not in (0,90,180,270)or math.dist(old[:2],target_pose[:2])>max_shift_mm:
        raise ValueError('bounded_cardinal_protector_pose_required')
    board=pcbnew.LoadBoard(q['source'])
    if row._source_binding(board)!=q['source_native_binding']:
        raise ValueError('protector_projection_source_changed')
    fp,model=_owner(board,q['owner_uuid'])
    outgoing=set(q['retired_track_uuids'])|set(q['retired_via_uuids'])
    discard_items(board,[t for t in board.GetTracks()if force._uid(t)in outgoing])
    fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in target_pose[:2])))
    fp.SetOrientationDegrees(target_pose[2])
    clamp=fp.FindPadByNumber(model['clamp_reference_pin'])
    anchors=q['clamp_aggregate_source_ports']
    ports=[*anchors['root_ports'],*[_stroke_port(s,tuple(clamp.GetPosition()))
        for s in anchors['retained_full_width_strokes']]]
    target=min(ports,key=lambda p:(math.dist(p['at_nm'],tuple(clamp.GetPosition())),
        p.get('pad_uuid',''),p.get('native_uuids',[])))
    width=max(int(board.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(board,clamp.GetNetname())['width']))
    request=dict(kind='source_boundary',net=str(clamp.GetNetname()),a=_port(clamp),b=target,
        width_nm=width,unchanged_full_rail_current_contract=q['clamp_current_contract'],
        source_clamp_role='passive_steering_clamp_reference',
        every_surviving_source_component_port_mandatory=True,
        new_load_budget_inferred=False,pulse_rating_used_as_continuous_current=False)
    return board,request


def _screen(board,ref,deadline):
    import cec_escape_pose_frontier as poses
    refs={ref}if type(ref)is str else set(ref)
    if not 1<=len(refs)<=8 or any(type(r)is not str or not r for r in refs):
        raise ValueError('bounded_native_cell_pose_screen_refs_required')
    courts=poses.courtyard_screen(board,refs)
    surface=poses.surface_screen(board,refs,selected_refs=refs,
        allow_native_ground_refill=True,timeout_s=_remaining(deadline))
    _remaining(deadline)
    return dict(ok=bool(courts['ok']and surface['ok']),courtyards=courts,surface=surface,
        no_routing_or_fabrication_admission=True)


def _final_ground_reference(board,ground,source_return_mm,deadline):
    """Reobserve the actual final witness, never reuse a pre-route plane proof."""
    from cec_ground_return_shortcut import _reference_contacts
    result=cells._existing_return(board,ground,1.5,allow_native_track_body=True)
    if result is None or result[0]>min(1.5,source_return_mm)+.000001:
        raise ValueError('protector_final_ground_not_immediate_or_source_nonregressing')
    contacts=_reference_contacts(board,result[1])
    _remaining(deadline)
    return dict(return_mm=result[0],via_uuid=force._uid(result[1]),references=contacts,
        freshly_observed_after_all_routes_and_final_refill=True)


def receive(source,candidate,proposal,*,timeout_s=10.):
    """Fresh complete original-Source saved replay, never a constructor flag."""
    from cec_protector_cell_receiving import receive as saved_receive
    return saved_receive(source,candidate,proposal,timeout_s=timeout_s)


def compile(source,*,owner_uuid,board_hint,pair_name,target_pose,max_shift_mm=6.,timeout_s=10.):
    """Rederive original Source contracts and ALL mandatory restoration ports."""
    deadline=_deadline(timeout_s)
    parent,q=_frame(source,owner_uuid,board_hint,pair_name,deadline)
    board,clamp=_project(parent,q,target_pose,max_shift_mm)
    q.update(target_pose=list(target_pose),max_shift_mm=max_shift_mm,clamp_request=clamp,
        pose_screen=_screen(board,q['owner_ref'],deadline),projected_native_binding=row._source_binding(board))
    if (force._code_identity()!=q['code_identity']or force._family(Path(q['source']),board_hint)!=q['source_family']):
        raise ValueError('protector_compilation_epoch_changed')
    _remaining(deadline)
    return board,q


def pose_menu(source,*,owner_uuid,board_hint,pair_name,radius_mm=4.,max_trials=32,timeout_s=10.):
    """Finite relative/cardinal native prescreen; no repeated old route wave.

    Reuse one immutable freshly compiled Source frame within this invocation.
    Every offered pose still needs public fresh compile and complete routing.
    A timeout or an empty finite menu is explicitly NOT a no-path proof.
    """
    deadline=_deadline(timeout_s)
    if (type(radius_mm)not in(int,float)or not math.isfinite(radius_mm)or not 0<radius_mm<=16.
            or type(max_trials)is not int or not 1<=max_trials<=64):
        raise ValueError('bounded_relative_protector_pose_menu_required')
    parent,q=_frame(source,owner_uuid,board_hint,pair_name,deadline)
    offsets=sorted({(x,y)for x in(-radius_mm,-radius_mm/2,0.,radius_mm/2,radius_mm)
        for y in(-radius_mm,-radius_mm/2,0.,radius_mm/2,radius_mm)
        if math.hypot(x,y)<=radius_mm},key=lambda p:(math.hypot(*p),p))
    proposals=[(x,y,turn)for x,y in offsets for turn in(0,90,180,270)][:max_trials]
    accepted=[];trials=[];complete=True
    for x,y,turn in proposals:
        if deadline-time.monotonic()<.35:
            complete=False;break
        pose=[q['source_pose'][0]+x,q['source_pose'][1]+y,(q['source_pose'][2]+turn)%360]
        board,clamp=_project(parent,q,pose,radius_mm)
        try:screen=_screen(board,q['owner_ref'],deadline)
        except ValueError as exc:
            trials.append(dict(pose=pose,error=str(exc)));complete=False;break
        trials.append(dict(pose=pose,ok=screen['ok'],screen=screen))
        if screen['ok']:accepted.append(dict(target_pose=pose,clamp_request=clamp))
    unchanged=(row._source_binding(parent)==q['source_native_binding']
        and force._code_identity()==q['code_identity']
        and force._family(Path(q['source']),board_hint)==q['source_family'])
    if not unchanged:raise ValueError('protector_pose_menu_source_epoch_changed')
    if time.monotonic()>=deadline:complete=False
    return dict(schema=1,scope='complete_protector_native_pose_prescreen',complete=complete,
        proposals=accepted,trials=trials,max_trials=max_trials,radius_mm=radius_mm,
        source_sha256=q['source_sha256'],source_family=q['source_family'],code_identity=q['code_identity'],
        source_unchanged=unchanged,source_contract=q,no_path_proof=False,
        routing_admitted=False,release_authority=False)


def construct(proposal,*,timeout_s=10.,pair_grid=True):
    """Attempt all mandatory domains atomically; never return a partial PCB.

    Explicit separately bounded constituents, not a hidden extended solver
    lease. A complete result is PRIVATE construction only; the original-parent
    composed saved receiver and all suite gates still owe fresh verification.
    """
    if type(pair_grid)is not bool:raise ValueError('explicit_protector_pair_search_policy_required')
    _deadline(timeout_s)
    import cec_additive_route_receiving as additive
    import cec_cell_escape_replan as escape
    import cec_complete_cell_receiving as paths
    import cec_ground_return_preservation as returns
    from cec_ground_return_shortcut import _reference_contacts
    stages=['source_compilation','ground_return','clamp_menu','clamp_selection','whole_pair','final_physical_observation']
    report=dict(schema=1,scope='complete_private_protector_construction',complete=False,
        errors=[],phases={},per_constituent_limit_s=timeout_s,maximum_constituents=len(stages),
        aggregate_limit_s=timeout_s*len(stages),partial_candidate_emitted=False,
        all_mandatory_domains=['functional_ground','aggregate_clamp_reference','whole_declared_pair'],
        routing_admitted=False,fab_ready=False,current_qualified=False,release_authority=False)
    initial=time.monotonic();stage=stages[0]
    phase_started=initial;deadline=initial+timeout_s
    try:
        if type(proposal)is not dict:raise ValueError('complete_protector_proposal_mapping_required')
        source=Path(proposal['source'])
        board,q=compile(source,owner_uuid=proposal['owner_uuid'],board_hint=proposal['board_hint'],
            pair_name=proposal['pair_plan']['pair']['name'],target_pose=proposal['target_pose'],
            max_shift_mm=proposal['max_shift_mm'],timeout_s=_remaining(deadline))
        if _stable(q)!=_stable(proposal):raise ValueError('stale_or_forged_complete_protector_proposal')
        if not q['pose_screen']['ok']:raise ValueError('protector_native_pose_prescreen_refused')
        _remaining(deadline)
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started)
        stage=stages[1];phase_started=time.monotonic();deadline=phase_started+timeout_s
        fp,model=_owner(board,q['owner_uuid'])
        ground=fp.FindPadByNumber(model['ground_pin']);diagnostic={}
        result,error=cells._add_ground_return(board,ground,board_path=str(source),reach_mm=1.5,
            lock=True,diagnostics=diagnostic)
        if result is None:
            report['phases'][stage]=dict(diagnostic=diagnostic,error=error)
            raise ValueError('protector_mandatory_ground_return_unconstructed')
        made=[force._uid(t)for t in result['items']]
        if any(t.GetClass()=='PCB_TRACK'and t.GetWidth()<q['ground_leaf']['width_nm']for t in result['items']):
            raise ValueError('protector_ground_restore_below_source_class_width')
        additive._ground_refill(board)
        witness=cells._existing_return(board,ground,1.5,allow_native_track_body=True)
        if witness is None or witness[0]>min(1.5,q['source_ground_return_mm'])+.000001:
            raise ValueError('protector_ground_return_not_immediate_or_source_nonregressing')
        references=_reference_contacts(board,witness[1]);_remaining(deadline)
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started,
            return_mm=witness[0],via_uuid=force._uid(witness[1]),added_uuids=made,references=references)
        stage=stages[2];phase_started=time.monotonic();deadline=phase_started+timeout_s
        parent=pcbnew.LoadBoard(str(source))
        menus=escape.menus(board,{'clamp_reference':q['clamp_request']},board_path=str(source),
            board_hint=q['board_hint'],timeout_s=_remaining(deadline),include_power_layer=True,source_board=parent)
        if not menus['domains'].get('clamp_reference'):
            report['phases'][stage]=dict(menu=menus,elapsed_s=time.monotonic()-phase_started)
            raise ValueError('protector_mandatory_clamp_reference_has_no_guarded_path')
        _remaining(deadline)
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started,menu=menus)
        stage=stages[3];phase_started=time.monotonic();deadline=phase_started+timeout_s
        selection=escape.choose(board,menus,timeout_s=_remaining(deadline))
        if not selection['complete']:raise ValueError('protector_clamp_path_selection_incomplete')
        clamp_items=escape.construct_private(board,menus,selection)
        connected=source_ports.full_width_connection(parent,board,source,q['clamp_request'],q['board_hint'],deadline)
        if connected is None or not connected['all_named_contacts_connected'] or not connected['zone_and_foreign_net_edges_excluded']:
            raise ValueError('protector_actual_clamp_endpoints_not_connected')
        _remaining(deadline)
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started,selection=selection,
            named_endpoints=connected,added_uuids=[force._uid(t)for t in clamp_items])
        stage=stages[4];phase_started=time.monotonic();deadline=phase_started+timeout_s
        pair_report=precision.precision_route_board(board,board_path=str(source),verbose=False,
            do_kelvin=False,do_pairs=True,include_pair_names=[q['pair_plan']['pair']['name']],
            pair_grid=pair_grid,_pair_search_deadline=deadline)
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started,pair=pair_report)
        _remaining(deadline)
        if not pair_report['pairs_ok']:raise ValueError('protector_whole_pair_construction_incomplete')
        stage=stages[5];phase_started=time.monotonic();deadline=phase_started+timeout_s
        additive._ground_refill(board)
        final_ground=_final_ground_reference(board,ground,q['source_ground_return_mm'],deadline)
        all_returns=returns.receive(parent,board,timeout_s=_remaining(deadline))
        if not all_returns['ok']or not all_returns['complete']:
            raise ValueError('protector_all_source_ground_return_receiving_refused')
        requests=dict(clamp_reference=q['clamp_request'],functional_ground=dict(kind='ground',net='GND',
            a=_port(ground),reach_mm=1.5,width_nm=q['ground_leaf']['width_nm']))
        old_ids={force._uid(t)for t in parent.GetTracks()};new_items={force._uid(t):t for t in board.GetTracks()if force._uid(t)not in old_ids}
        nonpair={u for u,t in new_items.items()if t.GetNetname()not in(q['pair_plan']['pair']['p'],q['pair_plan']['pair']['n'])}
        # Pair-owned local Ground returns have a separate exact pair receiver;
        # only the declared protector Ground/clamp additions enter this subproof.
        owned_nonpair=set(made)|set(report['phases']['clamp_selection']['added_uuids'])
        if not owned_nonpair<=nonpair:raise ValueError('protector_nonpair_addition_scope_changed')
        received=paths._receive_paths(parent,board,requests,owned_nonpair,q['board_hint'],deadline,
            received_barrel_uuids=[u for u in owned_nonpair if new_items[u].GetClass()=='PCB_VIA'])
        connected=source_ports.full_width_connection(parent,board,source,q['clamp_request'],q['board_hint'],deadline)
        if (connected is None or not connected['all_named_contacts_connected']
                or not connected['zone_and_foreign_net_edges_excluded']):
            raise ValueError('protector_saved_clamp_named_endpoint_connection_lost')
        report['phases'][stage]=dict(elapsed_s=time.monotonic()-phase_started,
            final_protector_ground_reference=final_ground,all_source_ground_returns=all_returns,
            actual_nonpair_paths=received,clamp_named_endpoints=connected)
        if (force._code_identity()!=q['code_identity']or force._family(source,q['board_hint'])!=q['source_family']
                or any(force._hash(p)!=h for p,h in q['source_symbol']['files_sha256'].items())):
            raise ValueError('protector_construction_source_or_code_changed')
        _remaining(deadline)
        if time.monotonic()-initial>=timeout_s*len(stages):raise ValueError('protector_composed_construction_deadline')
        report.update(complete=True,proposal=q,elapsed_s=time.monotonic()-initial,
            exact_saved_original_parent_composed_receiving_still_required=True)
        return board,report
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,subprocess.TimeoutExpired)as exc:
        report['errors'].append(type(exc).__name__+':'+str(exc))
        report['phases'].setdefault(stage,{})['elapsed_s']=time.monotonic()-phase_started
        report.update(failed_stage=stage,elapsed_s=time.monotonic()-initial,no_path_proof=False)
        return None,report
