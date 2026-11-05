"""Short local reconnection of a positively typed, exclusive resistor monitor.

The source monitor's manufacturer/selected-divider contract and the existing
one-tap consumer allocation are independent authorities. Neither gives a bus
or load branch a thin-wire exemption. Only its exact old monitor tracks, plus
an explicitly obsolete original generated root pickup, can be retired. Saved
native replay, complete partitions and drilled/current graphs are mandatory;
DRC, Kelvin, field, pair, stack and release receiving remain separate gates.
"""
import json,math,tempfile,time,uuid
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as debt
import cec_distributed_supply as supply
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_generated_pickup_retirement as pickup
import cec_kelvin_copper_cut as physical
import cec_ordinary_route_receiving as ordinary
import cec_resistive_monitor_branch as monitor
import cec_route_dimensions as dimensions
import cec_route_quality as craft
import cec_supply_consumer_branch as consumer
from cec_native_items import discard_items

POLICY='positive-exclusive-resistive-monitor-local-reconnection-v1'


def require(value,message):
    if not value:raise ValueError(message)


def canonical(points):
    require(type(points) is list and 2<=len(points)<=16 and all(type(p) in (list,tuple)
        and len(p)==2 and all(type(v) is int and abs(v)<2000000000 for v in p) for p in points),
        'bounded_literal_monitor_reconnection_points_required')
    points=[list(p) for p in points]
    require(all(a!=z and craft.is_canonical_stroke(a,z,tolerance_nm=0) for a,z in zip(points,points[1:])),
        'monitor_reconnection_needs_exact_nonzero_0_45_strokes')
    for a,b,c in zip(points,points[1:],points[2:]):
        u=[b[i]-a[i] for i in (0,1)];v=[c[i]-b[i] for i in (0,1)]
        dot=sum(x*y for x,y in zip(u,v))
        require(dot>0 and abs(u[0]*v[1]-u[1]*v[0])<=dot,'monitor_reconnection_sharp_turn_or_backtracking')
    from shapely.geometry import LineString
    require(LineString(points).is_simple and points[0]!=points[-1],'monitor_reconnection_self_crossing_or_closed_path')
    return points


def plan(source,*,board_hint,pad_uuid,target_uuid,points_nm,retire_root_pickup=False,allow_locked_source=False):
    require(type(board_hint) is str and bool(board_hint) and type(pad_uuid) is str and bool(pad_uuid)
        and type(target_uuid) is str and bool(target_uuid) and type(retire_root_pickup) is bool
        and type(allow_locked_source) is bool,'explicit_literal_monitor_reconnection_context_required')
    source=Path(source).resolve();board=pcbnew.LoadBoard(str(source));deadline=time.monotonic()+10.
    leaf=monitor.plan(board,pad_uuid,timeout_s=10.);cut=set(leaf['track_uuids'])
    live={force._uid(t):t for t in board.GetTracks()};pads={force._uid(p):p for f in board.GetFootprints() for p in f.Pads()}
    root=pads[pad_uuid];require(root.GetAttribute()==pcbnew.PAD_ATTRIB_SMD,'monitor_reconnection_fixed_smd_root_required')
    inventory=consumer.inventory(board,board_hint=board_hint,timeout_s=10.)
    require(inventory['complete'],'complete_source_consumer_allocation_required')
    rows=[q for q in inventory['proofs'] if cut<=q['retained_island_track_requirements'].keys()
        and any(r==leaf['source_resistive_monitor_contract'] for r in q['budget'].get('closed_monitor_loads',[]))]
    require(len(rows)==1,'one_positive_source_monitor_and_consumer_allocation_required');allocation=rows[0]
    old=[live[u] for u in sorted(cut)]
    require(all(t.GetClass()=='PCB_TRACK' and not t.HasSolderMask() and not t.GetParentGroup()
        and (not t.IsLocked() or allow_locked_source) for t in old)
        and len({(t.GetWidth(),bool(t.IsLocked())) for t in old})==1,
        'plain_uniform_explicitly_locked_source_monitor_tracks_required')
    target=({**live,**pads}).get(target_uuid)
    eligible=set(allocation['exact_branch_material_uuids'])|{allocation['root_pad_uuid']}
    if target is not None and target.GetClass()=='PCB_VIA' and target_uuid in allocation['retained_consumer_island_uuids']:
        # A retained native barrel need not have been emitted by the current
        # allocation generator. Require its real contact with already sized
        # source allocation copper, never a nearby same-net monitor pickup.
        joins=[live[u] for u,r in allocation['track_requirements'].items()
            if live[u].GetWidth()>=math.ceil(r['required_mm']*1e6)
            and target.IsOnLayer(live[u].GetLayer()) and target.GetEffectiveShape(live[u].GetLayer()).Collide(
                live[u].GetEffectiveShape(live[u].GetLayer()),0)]
        if joins:eligible.add(target_uuid)
    require(target is not None and target_uuid in eligible and target_uuid not in cut|set(leaf['via_uuids'])
        and target.GetNetname()==leaf['net'],'retained_actual_allocated_target_conductor_required')
    points=canonical(points_nm)
    actual_faces=[int(l) for l in (pcbnew.F_Cu,pcbnew.B_Cu) if root.IsOnLayer(l)]
    require(len(actual_faces)==1,'one_actual_outer_smd_monitor_face_required')
    face=actual_faces[0];require(points[0]==list(root.GetPosition()) and target.IsOnLayer(face),
        'literal_stationary_monitor_root_and_actual_outer_face_required')
    via_ids=leaf['via_uuids']
    empty_generator_groups=[]
    if retire_root_pickup:
        require(len(via_ids)==1 and list(live[via_ids[0]].GetPosition())==points[0],
            'only_one_exact_source_root_pickup_can_become_obsolete')
        for g in board.Groups():
            members={force._uid(t) for t in g.GetItems()}
            if members and members<=set(via_ids):
                require(g.GetName()==fr.LOCAL_POFV_SIGNAL_VIA_GROUP and not g.GetParentGroup()
                    and not any(other.ContainsItem(g) for other in board.Groups()),
                    'only_exact_unnested_generated_pickup_owner_can_retire_empty')
                empty_generator_groups.append(force._uid(g))
    else:require(not via_ids,'surface_reconnection_must_not_leave_an_unused_source_pickup')
    spec,contract=monitor.route_spec(board,source,pad_uuid,deadline=time.monotonic()+10.)
    profile=fab.active_profile_name(board,hint=str(source));require(bool(profile),'actual_monitor_factory_profile_required')
    authority=dict(amps=contract['current_upper_bound_a'],margin_included=True,geometry_margin=1.,
        source='manufacturer_voltage_bounds_and_selected_resistance_minimum')
    canonical_face=fab.COPPER_LAYER_IDS[face]
    required=dimensions.current_trace_widths(authority,[canonical_face],profile,rise_c=30.)[canonical_face]
    width=max(old[0].GetWidth(),math.ceil(max(spec['track_width'],required)*1e6))
    require(0<width<=350000,'bounded_positive_monitor_only_width_required')
    gap=max(board.GetDesignSettings().m_MinClearance,math.ceil(float(spec.get('clearance') or .2)*1e6))
    new=[]
    for a,z in zip(points,points[1:]):
        t=old[0].Duplicate();t.SetLayer(face);t.SetWidth(width);t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
        require(fr._edge_leg_clear(board,t.GetStart(),t.GetEnd(),(width+1)//2+gap)
            and fr._tap_foreign_clear(board,t.GetStart(),t.GetEnd(),width,face,gap,{root.GetNetCode()}),
            'monitor_reconnection_native_foreign_hole_rule_area_or_edge_refused');new.append(t)
    length=sum(t.GetLength() for t in new)/1e6
    require(length+0.01<leaf['source_length_mm'],'monitor_reconnection_must_strictly_shorten_source_leaf')
    work=physical._Work(time.monotonic()+10.)
    target_metal=physical._shape(target,face,False,work)
    if target.GetClass()=='PCB_VIA' or target.GetClass()=='PAD' and target.HasHole():
        require(physical._simple_drill(target,tuple(board.GetEnabledLayers().CuStack())),
            'simple_existing_target_drill_required')
        target_metal=target_metal.difference(physical._hole(target,True,work))
    contact=target_metal.intersection(physical._shape(new[-1],face,False,work))
    require(not contact.is_empty and contact.area>0,'positive_actual_target_metal_contact_not_bore_required')
    require(time.monotonic()<deadline,'monitor_reconnection_source_planning_deadline')
    result=dict(policy=POLICY,authority_sha256=force._hash(Path(__file__).resolve()),source_sha256=force._hash(source),
        board_hint=board_hint,pad_uuid=pad_uuid,target_uuid=target_uuid,points_nm=points,layer=face,width_nm=width,
        retire_root_pickup=retire_root_pickup,allow_locked_source=allow_locked_source,source_leaf=leaf,
        retired_track_uuids=sorted(cut),retired_via_uuids=via_ids if retire_root_pickup else [],
        retired_empty_generator_group_uuids=sorted(empty_generator_groups),
        root_pad_uuid=allocation['root_pad_uuid'],anchor_uuid=allocation['anchor_uuid'],source_budget=allocation['budget'],
        candidate_length_mm=length,positive_native_target_contact_area_nm2=contact.area,
        monitor_bound_not_a_bus_load_rating=True,terminal_barrel_or_release_qualified=False)
    # Phase manifests are JSON protocols. A nested native (layer,width) tuple
    # must not make a freshly reconstructed saved manifest look forged.
    return json.loads(json.dumps(result,allow_nan=False))


def construct(source,proposal):
    board=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in board.GetTracks()}
    old=[live[u] for u in proposal['retired_track_uuids']];prototype=old[0].Duplicate();discard_items(board,old)
    fingerprint=repr((POLICY,proposal['source_sha256'],proposal['pad_uuid'],proposal['target_uuid'],proposal['points_nm']))
    for index,(a,z) in enumerate(zip(proposal['points_nm'],proposal['points_nm'][1:])):
        t=prototype.Duplicate();t.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,fingerprint+str(index)))))
        t.SetLayer(proposal['layer']);t.SetWidth(proposal['width_nm'])
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));board.Add(t)
    if proposal['retire_root_pickup']:
        obsolete=pickup.plan(board,proposal['retired_via_uuids'],timeout_s=10.);pickup.subtract(board,obsolete)
    additive._ground_refill(board);return board


def receive(source,candidate,proposal,*,board_hint):
    result=dict(ok=False,complete=False,errors=[],source_current_reduced=False,branch_sharing_assumed=False,
        placement_authority=False,current_or_terminal_capacity_qualified=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)];epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)]
        fresh=plan(source,board_hint=board_hint,**{k:proposal[k] for k in (
            'pad_uuid','target_uuid','points_nm','retire_root_pickup','allow_locked_source')})
        require(fresh==proposal,'stale_or_forged_monitor_reconnection_plan')
        require(force._sidecars(source)==force._sidecars(candidate),'monitor_reconnection_rules_or_project_changed')
        _,old=additive._nodes(source);_,got=additive._nodes(candidate)
        retired=set(proposal['retired_track_uuids'])|set(proposal['retired_via_uuids']);added=got.keys()-old.keys()
        require(old.keys()-got.keys()==retired|set(proposal['retired_empty_generator_group_uuids'])
            and len(added)==len(proposal['points_nm'])-1,'exact_monitor_cut_and_addition_inventory_required')
        with tempfile.TemporaryDirectory(prefix='cec-monitor-replay-') as temporary:
            path=force._copy_family(source,Path(temporary)/'expected');field._save_field_snapshot(construct(source,proposal),path)
            _,expected=additive._nodes(path)
            require(got.keys()==expected.keys() and all(syntax._freeze(got[u])==syntax._freeze(expected[u]) for u in got),
                'monitor_exact_source_reconstruction_differs')
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        leaf=monitor.plan(child,proposal['pad_uuid'],timeout_s=10.)
        retained_source_ids=set(old)|{force._uid(p) for f in parent.GetFootprints() for p in f.Pads()}
        require(leaf['source_resistive_monitor_contract']==proposal['source_leaf']['source_resistive_monitor_contract']
            and set(leaf['track_uuids'])==set(added) and not leaf['via_uuids']
            and proposal['target_uuid'] in leaf['boundary_uuids']
            and set(leaf['boundary_uuids'])<=retained_source_ids,'exact_saved_exclusive_monitor_leaf_and_retained_target_required')
        inventory=consumer.inventory(child,board_hint=board_hint,timeout_s=10.)
        rows=[q for q in inventory['proofs'] if q['root_pad_uuid']==proposal['root_pad_uuid']]
        require(inventory['complete'] and len(rows)==1 and rows[0]['anchor_uuid']==proposal['anchor_uuid']
            and rows[0]['budget']==proposal['source_budget'],'same_complete_consumer_tap_and_entire_budget_required')
        first=ordinary._partition(parent,time.monotonic()+10.,retired_uuids=retired)
        last=ordinary._partition(child,time.monotonic()+10.,retained_keys=set().union(*first))
        require(all(any(a<=z for z in last) for a in first),'monitor_reconnection_lost_surviving_native_partition')
        graphs=[pickup._scoped_terminal_graph(b,leaf['net'],timeout_s=10.) for b in (parent,child)]
        require(graphs[0]['pad_uuids']==graphs[1]['pad_uuids'],'monitor_reconnection_changed_actual_drilled_terminal_inventory')
        budget=proposal['source_budget'];contract=dict(net=leaf['net'],current_authority=budget['current_authority'],
            required_by_layer_mm=budget['required_by_layer_mm'],routing_layers=list(budget['required_by_layer_mm']))
        rated=[supply._graph(b,leaf['net'],contract) for b in (parent,child)]
        require(all(not q['unsupported_terminal_uuids'] and q['planar_full_width_components'] is not None for q in rated)
            and all(any(set(a)<=set(z) for z in rated[1]['planar_full_width_components'])
                for a in rated[0]['planar_full_width_components']),'monitor_reconnection_lost_actual_allocated_full_width_join')
        current=debt.receive(source,candidate,board_hint=board_hint)
        require(current['ok'] and current['complete'],'monitor_reconnection_current_debt_worsened_or_unknown')
        require(epoch==force._code_identity() and proposal['authority_sha256']==force._hash(Path(__file__).resolve())
            and families==[force._family(p,board_hint) for p in (source,candidate)],'monitor_reconnection_epoch_changed')
        result.update(ok=True,complete=True,retired_track_uuids=proposal['retired_track_uuids'],
            retired_via_uuids=proposal['retired_via_uuids'],added_native_uuids=sorted(added),
            retired_empty_generator_group_uuids=proposal['retired_empty_generator_group_uuids'],
            source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),exact_native_source_reconstruction=True,
            all_surviving_native_partitions_preserved=True,source_allocation_group_exact=True,
            all_preexisting_allocated_full_width_joins_preserved=True,actual_drilled_terminal_graphs=graphs,
            allocated_full_width_graphs=rated,independent_whole_current_debt=current,saved_monitor_leaf=leaf,
            same_source_consumer_proof=rows[0],centerline_removed_mm=proposal['source_leaf']['source_length_mm']-leaf['source_length_mm'],
            source_candidate_and_code_unchanged=True,pads_moved=0,new_vias=0,
            full_native_drc_kelvin_fields_pairs_stack_and_release_still_required=True)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,physical.Unknown) as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    return result
