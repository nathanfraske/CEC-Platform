"""Reroot one under-floor routing kernel through existing full-stack barrels.

This is separate from unchanged-width, fixed-port finishing. Thin source tracks may occupy any positively specified non-reference signal
face. Only under-floor ungrouped routing primitives are retired; all full-current conductors, lands,
parts, groups, rules, budgets and barrel geometry remain literal. A full-budget
outer-face path joins two *different* surviving native components. Native
saved receiving and all whole-board gates remain mandatory; no barrel,
thermal, electrical or fabrication rating is inferred.
"""
import json,math,tempfile,time,uuid
from pathlib import Path
import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as syntax
import cec_current_debt as debt
import cec_distributed_supply as supply
import cec_existing_current_path_refinement as capacity
import cec_field_coupling as field
import cec_force_current as force
import cec_fab_profile as fab
import cec_native_current_capture as capture
import cec_ordinary_route_receiving as ordinary
import cec_pair_semantics as semantics
import cec_precision_route as precision
import cec_route_corner_contacts as contacts
from cec_generated_pickup_retirement import _scoped_terminal_graph
from cec_native_items import discard_items

POLICY='actual-signal-face-supply-kernel-existing-barrel-reembedding-v1'
def require(value,message):
    if not value:raise ValueError(message)
def plain(value):return json.loads(json.dumps(value,allow_nan=False))

def net_parts(board,net,omitted,deadline):
    items=[*(p for fp in board.GetFootprints() for p in fp.Pads()),*board.GetTracks(),
        *[z for z in board.Zones() if not z.GetIsRuleArea()]]
    items=[i for i in items if i.GetNetname()==net and force._uid(i) not in omitted]
    require(0<len(items)<=2048 and len({force._uid(i) for i in items})==len(items),
        'bounded_unique_actual_supply_material_required')
    conn=pcbnew.CONNECTIVITY_DATA();remaining={force._uid(i):i for i in items};parts=[]
    for item in items:
        require(time.monotonic()<deadline and conn.Add(item),'supply_kernel_native_connectivity_unknown')
    while remaining:
        require(time.monotonic()<deadline,'supply_kernel_native_partition_deadline')
        uid=min(remaining);reached={uid}|{force._uid(i) for i in conn.GetConnectedItems(remaining[uid])}
        own=remaining.keys()&reached;require(own,'nonempty_supply_native_component_required')
        parts.append(sorted(own))
        for u in own:del remaining[u]
    return sorted(parts)

def through_barrel(item):
    return item.GetClass()=='PCB_VIA' and int(item.GetViaType())==int(pcbnew.VIATYPE_THROUGH) \
        and int(item.TopLayer())==int(pcbnew.F_Cu) and int(item.BottomLayer())==int(pcbnew.B_Cu) \
        and 0<item.GetDrillValue()<item.GetWidth(item.TopLayer())

def component_attached_barrel(board,item):
    """A component's existing copper interface is a root, not routing debt.

    An ungrouped via-in-pad is still a component attachment. Native contact
    on any enabled copper face terminates discovery and forbids retirement;
    a generator group is neither necessary nor sufficient to infer this.
    """
    pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    require(len(pads)<=16384,'bounded_native_supply_barrel_pad_inventory_required')
    return any(p.GetNetCode()==item.GetNetCode() and any(p.IsOnLayer(face)
        and item.IsOnLayer(face) and p.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face),0)
        for face in board.GetEnabledLayers().CuStack()) for p in pads)

def supply_model(board,source,net,hint):
    excluded={n for pair in precision.derive_coupled_pairs(str(source),board=board) for n in (pair['p'],pair['n'])}
    excluded|={n for pair in semantics.analog_input_pairs(board) for n in (pair['p'],pair['n'])}
    excluded|=semantics.unresolved_current_monitor_nets(board)
    require(net!='GND' and net not in excluded,'supply_kernel_is_not_ground_pair_or_kelvin_authority')
    return capacity.full._model(board,source,net,hint)

def source_face_floor(board,source,contract,face):
    """Actual current/factory floor, not the preferred routing stroke width."""
    canonical=fab.COPPER_LAYER_IDS.get(face)
    require(face in board.GetEnabledLayers().CuStack()
        and face not in {board.GetLayerID(n) for n in capacity.fr.plane_layers(board)}
        and canonical in contract.get('routing_layers',()),'positive_source_signal_routing_face_required')
    actual=contract.get('required_by_layer_mm',{}).get(canonical)
    require(type(actual) in (int,float) and math.isfinite(actual) and actual>0,
        'positive_actual_source_face_current_floor_required')
    process=contract.get('process_by_layer',{}).get(canonical,{}).get('track_width_mm',0.)
    require(type(process) in (int,float) and math.isfinite(process) and process>=0,
        'actual_source_face_factory_floor_unknown')
    return max(math.ceil(actual*1e6),math.ceil(process*1e6),board.GetDesignSettings().m_TrackMinWidth)

def retained_supply_barrel_root(board,item,source,contract):
    """Keep component, saved-pour and already-current-sized native interfaces.

    This is conservative discovery/retirement protection, not a rating for
    the existing barrel. It deliberately does not infer layer current sharing.
    """
    if component_attached_barrel(board,item):return True
    tracks=list(board.GetTracks());zones=list(board.Zones())
    require(len(tracks)+len(zones)<=16384,'bounded_existing_supply_root_inventory_required')
    for face in board.GetEnabledLayers().CuStack():
        if not item.IsOnLayer(face):continue
        for zone in zones:
            if (zone.GetNetCode()==item.GetNetCode() and not zone.GetIsRuleArea()
                    and zone.IsOnLayer(face) and zone.IsFilled() and zone.HasFilledPolysForLayer(face)):
                if zone.GetFilledPolysList(face).Collide(item.GetEffectiveShape(face),0):return True
        try:floor=source_face_floor(board,source,contract,int(face))
        except ValueError:continue
        for track in tracks:
            if (track.GetClass()=='PCB_TRACK' and track.GetNetCode()==item.GetNetCode()
                    and track.GetLayer()==face and track.GetWidth()>=floor
                    and track.GetEffectiveShape(face).Collide(item.GetEffectiveShape(face),0)):return True
    return False

def discover(source,*,board_hint,seed_track_uuids,allow_locked_source=False):
    """Follow the entire thin native component across ordinary routing vias.

    This is discovery, not deletion permission. Pads, full-width tracks and
    grouped or component-attached barrels terminate a kernel. Do not repeat two-edge cuts that
    strand the rest of the same generated pickup on another face.
    """
    require(type(allow_locked_source) is bool,'explicit_kernel_discovery_lock_policy_required')
    seeds=ordinary._ids(seed_track_uuids,'supply_kernel_seeds',64)
    source=Path(source).resolve();board=pcbnew.LoadBoard(str(source));epoch=force._code_identity()
    family=force._family(source,board_hint);live={force._uid(t):t for t in board.GetTracks()}
    require(seeds<=live.keys(),'actual_supply_kernel_seed_tracks_required')
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    deadline=time.monotonic()+10.;offered={};refused=[]
    for seed in sorted(seeds):
        item=live[seed];net=str(item.GetNetname())
        try:
            require(item.GetClass()=='PCB_TRACK','plain_supply_kernel_seed_required')
            _,_,contract=supply_model(board,source,net,board_hint);eligible={}
            for uid,t in live.items():
                require(time.monotonic()<deadline,'supply_kernel_discovery_deadline')
                if t.GetNetname()!=net or uid in grouped or t.GetParentGroup() or t.IsLocked() and not allow_locked_source:continue
                if through_barrel(t) and t.GetWidth(t.TopLayer())<=1500000 and not retained_supply_barrel_root(board,t,source,contract):eligible[uid]=t
                elif t.GetClass()=='PCB_TRACK' and not t.HasSolderMask():
                    try:floor=source_face_floor(board,source,contract,int(t.GetLayer()))
                    except ValueError:continue
                    if 0<t.GetWidth()<=350000 and t.GetWidth()<floor:eligible[uid]=t
            require(seed in eligible and len(eligible)<=2048,'positive_underfloor_routing_seed_required')
            conn=pcbnew.CONNECTIVITY_DATA()
            for t in eligible.values():require(conn.Add(t),'native_supply_kernel_discovery_item_refused')
            selected=({seed}|{force._uid(t) for t in conn.GetConnectedItems(item)})&eligible.keys()
            tracks=sorted(u for u in selected if eligible[u].GetClass()=='PCB_TRACK')
            vias=sorted(u for u in selected if eligible[u].GetClass()=='PCB_VIA')
            require(1<=len(tracks)<=16 and len(vias)<=4,'discovered_supply_kernel_exceeds_finite_transaction_scope')
            offered[tuple(sorted(selected))]=dict(net=net,retired_track_uuids=tracks,retired_via_uuids=vias,
                discovery_is_not_retirement_authority=True)
        except ValueError as e:refused.append(dict(seed_uuid=seed,reason=str(e)))
    require(epoch==force._code_identity() and family==force._family(source,board_hint),'supply_kernel_discovery_source_changed')
    return dict(complete=True,code_identity=epoch,source_sha256=force._hash(source),kernels=list(offered.values()),
        refusals=refused,native_cross_layer_causal_closure=True,source_mutated=False,release_authority=False)

def plan(source,*,board_hint,retired_track_uuids,retired_via_uuids,start_uuid,end_uuid,
        layer,width_nm,points_nm,allow_locked_source=False):
    require(type(board_hint) is str and bool(board_hint) and type(allow_locked_source) is bool
        and type(layer) is int and type(width_nm) is int,'explicit_supply_kernel_context_required')
    source=Path(source).resolve();epoch=force._code_identity();authority=force._hash(Path(__file__))
    board=pcbnew.LoadBoard(str(source));live={force._uid(i):i for i in board.GetTracks()}
    tracks=ordinary._ids(retired_track_uuids,'supply_kernel_track_cut',16)
    vias=ordinary._ids(retired_via_uuids,'supply_kernel_via_cut',4) if retired_via_uuids else set()
    cut=tracks|vias;require(tracks and not tracks&vias and cut<=live.keys(),'actual_bounded_supply_kernel_cut_required')
    grouped={force._uid(i) for g in board.Groups() for i in g.GetItems()}
    require(not cut&grouped and all(not live[u].GetParentGroup() and
        (not live[u].IsLocked() or allow_locked_source) for u in cut),'plain_explicitly_owned_supply_routing_primitives_required')
    require(all(live[u].GetClass()=='PCB_TRACK' and not live[u].HasSolderMask() for u in tracks)
        and all(through_barrel(live[u]) and live[u].GetWidth(live[u].TopLayer())<=1500000 for u in vias),
        'only_thin_plain_tracks_and_actual_routing_through_vias_supported')
    require(not any(component_attached_barrel(board,live[u]) for u in vias),
        'component_attached_supply_barrels_are_immutable_roots_not_routing_pickups')
    require(len({str(live[u].GetNetname()) for u in cut})==1,'one_actual_source_supply_net_required')
    net=str(live[next(iter(tracks))].GetNetname());kind,domain,contract=supply_model(board,source,net,board_hint)
    require(not any(retained_supply_barrel_root(board,live[u],source,contract) for u in vias),
        'existing_current_sized_or_saved_pour_barrel_is_an_immutable_root')
    source_face_floors={}
    for uid in tracks:
        t=live[uid];floor=source_face_floor(board,source,contract,int(t.GetLayer()));source_face_floors[uid]=floor
        require(0<t.GetWidth()<=350000 and t.GetWidth()<floor and 0<t.GetLength()<=16000000,
            'supply_kernel_must_not_retire_already_full_current_sized_copper')
    old_length=sum(live[u].GetLength() for u in tracks)
    require(old_length<=32000000,'bounded_old_supply_kernel_span_required')
    floor=capacity.capacity_floor(board,contract,layer)
    require(floor<=width_nm<=2000000,'new_supply_bridge_must_meet_entire_actual_current_and_factory_floor')
    require(type(start_uuid) is str and type(end_uuid) is str and start_uuid!=end_uuid
        and {start_uuid,end_uuid}<=live.keys() and not {start_uuid,end_uuid}&cut,
        'two_distinct_retained_native_supply_barrels_required')
    ports=[live[u] for u in (start_uuid,end_uuid)]
    require(all(through_barrel(i) and i.GetNetname()==net and i.IsOnLayer(layer)
        and i.GetWidth(layer)>=width_nm for i in ports),'actual_unchanged_sufficient_land_existing_barrels_required')
    points=[list(p) for p in capacity.geometry._points(points_nm)]
    require(points[0]==list(ports[0].GetPosition()) and points[-1]==list(ports[1].GetPosition()),
        'bridge_ports_must_be_literal_existing_barrel_centres')
    new_length=sum(math.dist(a,z) for a,z in zip(points,points[1:]))
    require(new_length<=32000000 and new_length<old_length,'strictly_shorter_bounded_supply_kernel_reembedding_required')
    deadline=time.monotonic()+10.;before=net_parts(board,net,set(),deadline);after_cut=net_parts(board,net,cut,deadline)
    require(len(before)==1,'source_supply_native_material_must_already_be_connected')
    memberships=[next((i for i,p in enumerate(after_cut) if uid in p),None) for uid in (start_uuid,end_uuid)]
    require(None not in memberships and memberships[0]!=memberships[1],
        'new_bridge_must_join_distinct_surviving_components_not_add_a_redundant_loop')
    # Every selected primitive is one connected source routing kernel. Board
    # copper outside that kernel cannot manufacture a spurious cut topology.
    conn=pcbnew.CONNECTIVITY_DATA()
    for uid in cut:require(conn.Add(live[uid]),'supply_kernel_cut_connectivity_unknown')
    seed=next(iter(cut));connected={seed}|{force._uid(i) for i in conn.GetConnectedItems(live[seed])}
    require(cut<=connected,'one_connected_source_routing_kernel_required')
    with force._thermal_hint(board_hint):guard=capture.Guard(board,source,net=net,board_hint=board_hint,timeout_s=10.)
    require(not cut&guard.exclusive,'supply_kernel_cannot_retire_an_exclusive_manufacturer_control_leaf')
    spec=capacity.fr._project_netclass_resolver(str(source),board=board)(net) or {}
    clearance=max(board.GetDesignSettings().m_MinClearance,math.ceil(float(spec.get('clearance') or .2)*1e6))
    for a,z in zip(points,points[1:]):
        require(capacity.fr._edge_leg_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),(width_nm+1)//2+clearance)
            and capacity.fr._tap_foreign_clear(board,pcbnew.VECTOR2I(*a),pcbnew.VECTOR2I(*z),width_nm,layer,clearance,{ports[0].GetNetCode()})
            and guard(tuple(a),tuple(z),width_nm,layer),'supply_bridge_foreign_rule_edge_or_control_capture_refused')
    require(epoch==force._code_identity() and authority==force._hash(Path(__file__)),'supply_kernel_plan_epoch_changed')
    return plain(dict(policy=POLICY,source_sha256=force._hash(source),code_identity=epoch,authority_sha256=authority,board_hint=board_hint,
        retired_track_uuids=sorted(tracks),retired_via_uuids=sorted(vias),start_uuid=start_uuid,end_uuid=end_uuid,
        net=net,layer=layer,width_nm=width_nm,actual_current_factory_floor_nm=floor,points_nm=points,
        allow_locked_source=allow_locked_source,contract=contract,domain=domain,current_domain_kind=kind,
        source_length_nm=old_length,candidate_length_nm=new_length,cut_only_native_components=after_cut,
        actual_source_face_floor_by_track_nm=source_face_floors,no_reference_face_track_retirement=True,
        native_anchor_components=memberships,unchanged_routing_preference_mm=spec.get('track_width'),
        source_current_or_width_requirement_reduced=False,new_barrel_or_part_authorized=False,release_authority=False))

def construct(source,proposal):
    board=pcbnew.LoadBoard(str(source));live={force._uid(i):i for i in board.GetTracks()}
    discard_items(board,[live[u] for u in proposal['retired_track_uuids']+proposal['retired_via_uuids']])
    net=board.GetNetcodeFromNetname(proposal['net'])
    key=repr((POLICY,proposal['source_sha256'],proposal['retired_track_uuids'],proposal['retired_via_uuids'],proposal['points_nm']))
    for i,(a,z) in enumerate(zip(proposal['points_nm'],proposal['points_nm'][1:])):
        t=pcbnew.PCB_TRACK(board);t.SetNetCode(net);t.SetLayer(proposal['layer']);t.SetWidth(proposal['width_nm']);t.SetLocked(True)
        t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z))
        t.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,key+str(i)))));board.Add(t)
    additive._ground_refill(board);return board

def receive(source,candidate,proposal,*,board_hint):
    result=dict(ok=False,complete=False,errors=[],new_capacity_credited=False,current_or_barrel_qualified=False,
        new_barrels=0,pads_moved=0,source_current_reduced=False,routing_admitted=False,fab_ready=False,release_authority=False)
    try:
        source,candidate=[Path(p).resolve() for p in (source,candidate)];epoch=force._code_identity()
        families=[force._family(p,board_hint) for p in (source,candidate)]
        fresh=plan(source,board_hint=board_hint,**{k:proposal[k] for k in ('retired_track_uuids','retired_via_uuids',
            'start_uuid','end_uuid','layer','width_nm','points_nm','allow_locked_source')})
        require(fresh==proposal,'stale_or_forged_supply_kernel_plan')
        require(force._sidecars(source)==force._sidecars(candidate),'supply_kernel_changed_companions_or_rules')
        _,old=additive._nodes(source);_,got=additive._nodes(candidate)
        cut=set(proposal['retired_track_uuids']+proposal['retired_via_uuids']);added=got.keys()-old.keys()
        require(old.keys()-got.keys()==cut and len(added)==len(proposal['points_nm'])-1,'exact_supply_kernel_track_and_barrel_delta_required')
        with tempfile.TemporaryDirectory(prefix='cec-supply-kernel-') as work:
            replay=force._copy_family(source,Path(work)/'expected');field._save_field_snapshot(construct(source,proposal),replay)
            _,expected=additive._nodes(replay)
            require(got.keys()==expected.keys() and all(syntax._freeze(n)==syntax._freeze(got[u]) for u,n in expected.items()),
                'unowned_saved_supply_kernel_or_force_copper_change')
        boards=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        kind,domain,contract=supply_model(boards[1],candidate,proposal['net'],board_hint)
        require(plain(contract)==proposal['contract'] and plain(domain)==proposal['domain'] and kind==proposal['current_domain_kind'],
            'supply_kernel_actual_current_authority_or_domain_changed')
        parts=ordinary._partition(boards[0],time.monotonic()+10.,retired_uuids=cut)
        after=ordinary._partition(boards[1],time.monotonic()+10.,retained_keys=set().union(*parts))
        require(all(any(a<=z for z in after) for a in parts),'supply_kernel_lost_surviving_native_region')
        terminal_graphs=[_scoped_terminal_graph(b,proposal['net'],timeout_s=10.) for b in boards]
        require(terminal_graphs[0]['pad_uuids']==terminal_graphs[1]['pad_uuids'],'supply_kernel_actual_terminal_inventory_changed')
        rated=[supply._graph(b,proposal['net'],contract) for b in boards]
        require(all(not r['unsupported_terminal_uuids'] and r['planar_full_width_components'] is not None for r in rated)
            and all(any(set(a)<=set(z) for z in rated[1]['planar_full_width_components']) for a in rated[0]['planar_full_width_components']),
            'supply_kernel_lost_old_full_current_planar_terminal_join')
        current=debt.receive(source,candidate,board_hint=board_hint)
        require(current['ok'] and current['complete'],'supply_kernel_whole_current_debt_regressed_or_unknown')
        require(epoch==force._code_identity() and proposal['authority_sha256']==force._hash(Path(__file__))
            and families==[force._family(p,board_hint) for p in (source,candidate)],'supply_kernel_source_or_epoch_changed')
        result.update(ok=True,complete=True,source_sha256=force._hash(source),candidate_sha256=force._hash(candidate),
            retired_track_uuids=proposal['retired_track_uuids'],retired_via_uuids=proposal['retired_via_uuids'],
            added_native_uuids=sorted(added),exact_native_source_reconstruction=True,all_surviving_native_components_preserved=True,
            old_force_planes_parts_lands_groups_barrels_and_rules_exact=True,actual_drilled_terminal_graphs=terminal_graphs,
            old_planar_current_sized_terminal_graphs=rated,all_old_current_sized_joins_preserved=True,
            whole_parent_current_receiving=current,whole_unchanged_current_contract_on_every_new_stroke=True,
            actual_source_face_floors_rederived=True,reference_face_tracks_and_retained_current_barrel_roots_unchanged=True,
            centerline_removed_mm=(proposal['source_length_nm']-proposal['candidate_length_nm'])/1e6,
            native_custom_rules_fields_kelvin_ground_returns_pairs_stack_and_release_receiving_still_required=True)
    except (ValueError,RuntimeError,KeyError,TypeError,OSError) as e:result['errors'].append(type(e).__name__+':'+str(e))
    return result
