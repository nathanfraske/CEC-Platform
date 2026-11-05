"""Attach stranded supply/passive islands to a rated current trunk.

This bounded additive tier owns local terminal connections, never the main
power bus. Load-bearing attachments carry the unchanged whole-net current
contract. Positively typed resistor-to-control islands use the existing
project/board branch dimensions only when an independent rated source-to-sink
trunk already exists. No guessed load, current split, via, neckdown or zone
credit is used; whole-board current receiving remains mandatory. Only these
non-load islands may use two profile-qualified, fully contained POFV seats.
It fills the gap between source/sink-only force routing and ordinary supply
routing that correctly excludes aggregate current domains.
"""
from collections import defaultdict
import json
import math
from pathlib import Path
import subprocess
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_current_debt as debt
import cec_current_topology as topology
import cec_device_power_roles as roles
import cec_decoupler_cell as cells
import cec_distributed_supply as supply
import cec_fab_profile as fab
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_placement_geometry as physical
import cec_route_quality as craft
import cec_route_dimensions as dimensions
import cec_search_budget as search
import cec_stage_admission as stage
import cec_support_pivot_receiving as silk


def _bound(value):
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=10:
        raise ValueError('bounded_power_terminal_access_required')
    return float(value)


def _passive_class(fp):
    library=fp.GetFPIDAsString().split(':',1)[0]
    return next((kind for kind in ('Resistor_SMD','Capacitor_SMD')
        if library==kind or library.endswith('-'+kind)),None)


def _control_divider_island(board, pads, connected, net):
    """Source-typed non-load island; no inferred numeric pin-current budget.

    Only populated series resistors whose opposite nodes terminate at known
    manufacturer control/address/reference inputs are eligible. A power pin,
    measurement input, unknown IC or connector refuses this alternate pickup.
    This does not rate the pre-existing source-connected branch or divider.
    """
    import cec_synth_pipeline as synth
    own=[p for p in pads if force._uid(p) in connected]
    if not own:return False
    all_pads=[p for fp in board.GetFootprints() for p in fp.Pads()]
    for pad in own:
        fp=pad.GetParentFootprint();pins=list(fp.Pads())
        resistance=synth._r_value_ohms(fp.GetValue())
        dnp,excluded=constraints._fp_assembly_state(fp)
        if (dnp or excluded or _passive_class(fp)!='Resistor_SMD' or len(pins)!=2
                or resistance is None or resistance<=0 or not math.isfinite(resistance)):
            return False
        opposite=[p for p in pins if force._uid(p)!=force._uid(pad)]
        if len(opposite)!=1 or not opposite[0].GetNetname() or opposite[0].GetNetname()==net:return False
        node=[p for p in all_pads if p.GetNetname()==opposite[0].GetNetname()]
        witnessed=False
        for target in node:
            part=target.GetParentFootprint();model=roles.footprint_contract(part)
            if _passive_class(part)=='Resistor_SMD':continue
            if not model or model['pins'].get(str(target.GetNumber())) not in ('control','address','reference'):
                return False
            witnessed=True
        if not witnessed:return False
    return True


def _branch_widths(board, project, contract, control_only):
    """Only a source-typed non-load motif may select ordinary branch geometry.

    The full-current contract is NOT modified or reclassified. The constructor
    and receiver both derive this separate local role from the source board.
    """
    if type(control_only) is not bool:raise ValueError('explicit_source_typed_branch_role_required')
    ordinary=dimensions.compile_spec(project,limits=dimensions.board_limits(board),role='branch')
    floor=float(ordinary['track_width'])
    if not math.isfinite(floor) or floor<=0:raise ValueError('power_terminal_branch_floor_missing')
    return {name:(floor if control_only else max(floor,float(value)))
        for name,value in contract['required_by_layer_mm'].items()}


def _bridge_layers(board, task, source_layer):
    planes={int(board.GetLayerID(n)) for n in fr.plane_layers(board)}
    return sorted((int(lid) for lid in board.GetEnabledLayers().CuStack()
        if int(lid)!=source_layer and int(lid) not in planes
        and fab.COPPER_LAYER_IDS.get(int(lid)) in task['branch_width_by_layer_mm']),
        key=lambda lid:(lid!=pcbnew.B_Cu,lid))


def _contained_bridge_seats(board, pads, *, clearance_nm):
    """Existing fabrication opt-in and exact native pad contact, not ampacity."""
    profile_name=fab.active_profile_name(board)
    if not profile_name:return None
    profile=fab.get_profile(profile_name)
    preferred=fab.preferred_pofv_geometry(profile)
    if not preferred:return None
    # Prefer a contained via that also meets the ordinary board minima. A
    # process permitting smaller POFV does not require choosing its smallest
    # land/drill or producing avoidable native ordinary-rule diagnostics.
    diameter,drill,_=cells._board_legal_through_via_geometry(board,*preferred)
    preferred=(diameter,drill)
    if not fab.pofv_dimensions(profile,*preferred)[0]:return None
    if len(pads)!=2 or math.dist(list(pads[0].GetPosition()),list(pads[1].GetPosition()))<=0:return None
    for pad in pads:
        if pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.HasHole():return None
        if not fr._via_spot_clear(board,pad.GetPosition(),round(preferred[0]*1e6),clearance_nm,
                {pad.GetNetCode()},drill_nm=round(preferred[1]*1e6),net_code=pad.GetNetCode(),
                contained_layers=set(pad.GetLayerSet().CuStack())):return None
        # The bridge engine independently checks containment too. Fail closed
        # here rather than granting the ordinary off-pad dogbone fallback.
        inset=math.ceil(preferred[0]*1e6/2)+1000
        layer=next(iter(pad.GetLayerSet().CuStack()))
        polygon=pcbnew.SHAPE_POLY_SET()
        pad.TransformShapeToPolygon(polygon,layer,0,1000,pcbnew.ERROR_INSIDE,False)
        from cec_board_geometry import material_boundaries, material_leg_clear
        if not material_leg_clear(polygon,material_boundaries(polygon),pad.GetPosition(),
                pad.GetPosition(),inset):return None
    return preferred


def _excluded_nets(source, exclude_nets):
    if (not isinstance(exclude_nets,(tuple,list,set,frozenset)) or len(exclude_nets)>256
            or any(type(n) is not str or not n for n in exclude_nets)):
        raise ValueError('explicit_bounded_power_terminal_exclusions_required')
    # Whole-net leases are not unlocked by this additive tier. Locked-item
    # prefixes are different: their exact native objects remain unchanged.
    return set(exclude_nets)|set(force._ownership(source,()))


def tasks(board, *, source, board_hint, radius_mm=6., timeout_s=10., exclude_nets=()):
    """Source-native stranded cells and actual rated trunk access points."""
    deadline=time.monotonic()+_bound(timeout_s)
    immutable_nets=_excluded_nets(source,exclude_nets)
    if type(radius_mm) not in (int,float) or not math.isfinite(radius_mm) or not 0<radius_mm<=8:
        raise ValueError('bounded_power_terminal_locality_required')
    with force._thermal_hint(board_hint):
        domains=topology.board_current_domains(board,board_hint)
        contracts=topology.route_width_contracts(board,board_hint=board_hint)
    resolver=fr._project_netclass_resolver(str(source));cohorts=defaultdict(list)
    capacitors=[]
    for fp in board.GetFootprints():
        pads=list(fp.Pads())
        dnp,excluded=constraints._fp_assembly_state(fp)
        value=constraints._capacitance_f_board(fp.GetValue())
        if not dnp and not excluded and value is not None and value>0 and len(pads)==2:
            for p in pads:
                if (p.GetNetname() and not constraints._ground_net(p.GetNetname())
                        and any(constraints._ground_net(q.GetNetname()) for q in pads if q!=p)):
                    capacitors.append((fp,p))
    for owner in board.GetFootprints():
        model=roles.footprint_contract(owner)
        if not model:continue
        for pad in owner.Pads():
            if model['pins'].get(str(pad.GetNumber()))!='power_input':continue
            net=str(pad.GetNetname());domain=domains.get(net,{})
            if net not in contracts or domain.get('complete') is not True or constraints._ground_net(net):continue
            cohorts[net].append((owner,pad))
    # Full-current geometry may also attach a populated resistor/capacitor
    # island. This is physical part-class metadata, not a reference prefix or
    # inferred electrical load; measurement IC lands remain excluded. In
    # particular, a source-to-shunt-only force solve otherwise leaves its
    # rail's isolated OVP/undervoltage dividers outside every construction tier.
    for owner in board.GetFootprints():
        pads=list(owner.Pads());dnp,excluded=constraints._fp_assembly_state(owner)
        if dnp or excluded or len(pads)!=2 or _passive_class(owner) is None:continue
        for pad in pads:
            net=str(pad.GetNetname());domain=domains.get(net,{})
            if net in contracts and domain.get('complete') is True and not constraints._ground_net(net):
                cohorts[net].append((owner,pad))
    result=[];refused=[]
    for net,cells in sorted(cohorts.items()):
        if net in immutable_nets:
            refused.append(dict(net=net,reason='immutable_whole_net_owner'));continue
        if time.monotonic()>=deadline:raise ValueError('power_terminal_inventory_deadline')
        domain=domains[net];contract=dict(contracts[net]);project=resolver(net) or {}
        contract['required_by_layer_mm']={layer:max(value,
            float(board.GetDesignSettings().m_TrackMinWidth)/1e6)
            for layer,value in contract['required_by_layer_mm'].items()}
        graph,(pads,kept,members)=force._graph(board,net,domain,contract,project)
        if graph['rated_connectivity']['connected'] is not True:
            refused.append(dict(net=net,reason='existing_trace_rated_trunk_required'));continue
        # A saved native graph checks strandedness. The separate rated graph
        # limits attachment points; a thin source-connected branch is NOT a
        # new full-current pickup simply because it has the same net name.
        native=pcbnew.CONNECTIVITY_DATA()
        material=[p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname()==net]
        material += [t for t in board.GetTracks() if t.GetNetname()==net]
        material += [z for z in board.Zones() if not z.GetIsRuleArea() and z.GetNetname()==net]
        if len(material)>4096:raise ValueError('power_terminal_native_inventory_bound')
        for item in material:
            if time.monotonic()>=deadline or not native.Add(item):raise ValueError('power_terminal_native_graph_unavailable')
        source_ids={force._uid(p) for p in pads}
        contract['required_by_layer_mm']=graph['required_by_layer_mm']
        contract['clearance_mm']=max(.2,float(board.GetDesignSettings().m_MinClearance)/1e6,
            float(project.get('clearance') or 0))
        items={force._uid(i):i for i in material};anchors=[]
        for anchor in force._anchors(pads,kept,members):
            for lid in anchor['layers']:
                name=fab.COPPER_LAYER_IDS.get(lid)
                if name not in contract['routing_layers']:continue
                selected=dict(uuid=anchor['uuid'],kind=anchor['kind'],layer=lid,point_nm=anchor['point'])
                proof=supply._anchor_contact(board,selected,contract,items=items)
                if proof['ok']:anchors.append(dict(selected,contact=proof))
        for owner,pad in cells:
            connected={force._uid(pad)}|{force._uid(i) for i in native.GetConnectedItems(pad)}
            if connected & source_ids:continue
            control_only=_control_divider_island(board,[i for i in material if i.GetClass()=='PAD'],connected,net)
            branch_widths=_branch_widths(board,project,contract,control_only)
            endpoints=[(owner,pad),*((fp,p) for fp,p in capacitors
                if p.GetNetname()==net and force._uid(p) in connected
                and math.dist(tuple(p.GetPosition()),tuple(pad.GetPosition()))<=3.5e6)]
            found=False
            for cap,target in endpoints:
                if target.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or target.HasHole():continue
                candidates=[]
                local_anchors=list(anchors)
                if control_only:
                    # Actual source-connected SMD terminals are safe geometric
                    # pickups for this non-load motif. Do not claim their old
                    # branch is newly rated; independent current/debt gates
                    # still receive the entire unchanged domain below.
                    for pickup in material:
                        if (pickup.GetClass()!='PAD' or pickup.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD
                                or pickup.HasHole() or force._uid(pickup) in connected):continue
                        peers={force._uid(pickup)}|{force._uid(i) for i in native.GetConnectedItems(pickup)}
                        if not peers & source_ids:continue
                        for lid in pickup.GetLayerSet().CuStack():
                            name=fab.COPPER_LAYER_IDS.get(int(lid))
                            if name not in contract['routing_layers']:continue
                            width=math.ceil(branch_widths[name]*1e6)
                            if min(pickup.GetSize().x,pickup.GetSize().y)<width:continue
                            selected=dict(uuid=force._uid(pickup),kind='pad_center',layer=int(lid),
                                point_nm=list(pickup.GetPosition()),source_control_only=True,
                                existing_pickup_branch_capacity_qualified=False)
                            proof=supply._anchor_contact(board,selected,contract,items=items)
                            if proof['ok']:local_anchors.append(dict(selected,contact=proof))
                for track in kept:
                    if track.GetClass()!='PCB_TRACK' or force._item_key(track) not in members[0]:continue
                    lid=int(track.GetLayer());name=fab.COPPER_LAYER_IDS.get(lid)
                    if name not in contract['routing_layers'] or not target.IsOnLayer(lid):continue
                    selected=dict(uuid=force._uid(track),kind='rated_track_projection',layer=lid,
                        point_nm=supply.native_track_projection(track,target),projection_pad_uuid=force._uid(target))
                    proof=supply._anchor_contact(board,selected,contract,items=items)
                    if proof['ok']:local_anchors.append(dict(selected,contact=proof))
                for anchor in local_anchors:
                    lid=anchor['layer'];name=fab.COPPER_LAYER_IDS[lid]
                    width=math.ceil(branch_widths[name]*1e6)
                    if not target.IsOnLayer(lid) or min(target.GetSize().x,target.GetSize().y)<width:continue
                    distance=math.dist(tuple(target.GetPosition()),anchor['point_nm'])/1e6
                    if 0<distance<=radius_mm:candidates.append(dict(anchor,direct_mm=distance))
                candidates.sort(key=lambda a:(a['direct_mm'],a['layer'],a['uuid'],a['point_nm']))
                if candidates:
                    found=True;result.append(dict(net=net,owner=owner.GetReference(),pin=pad.GetNumber(),
                        cap=cap.GetReference(),cap_pad=target.GetNumber(),cap_uuid=force._uid(target),
                        start_nm=list(target.GetPosition()),contract=contract,radius_mm=radius_mm,anchors=candidates[:32],
                        bypass_value_or_assignment_qualified=False,
                        control_only_divider_motif=control_only,
                        branch_width_by_layer_mm=branch_widths,
                        branch_role=('typed_nonload_control' if control_only else 'full_current_load'),
                        source_island_pad_uuids=sorted(force._uid(p) for p in material if p.GetClass()=='PAD'
                            and force._uid(p) in connected)))
            if not found:refused.append(dict(net=net,owner=owner.GetReference(),reason='no_local_full_width_rated_anchor'))
    ordered=sorted(result,key=lambda r:(r['anchors'][0]['direct_mm'],r['net'],r['owner']))
    selected=defaultdict(dict)
    for task in ordered:
        key=(task['net'],tuple(task['source_island_pad_uuids']))
        if len(selected[key])<4:selected[key].setdefault(task['cap_uuid'],task)
    # Different terminals on one native island are alternative access points,
    # not duplicate electrical obligations. Keep a bounded fair menu; the
    # constructor commits at most one feed for each unchanged source island.
    return dict(tasks=sorted((task for group in selected.values() for task in group.values()),
        key=lambda r:(r['anchors'][0]['direct_mm'],r['net'],r['owner'])),
        refusals=refused,board_mutated=False,whole_power_qualified=False,release_authority=False)


def construct(board, *, source, board_hint, timeout_s=10., radius_mm=6., max_joins=8,
              max_attempts=64, work_limit=262144, refine_maze=True, exclude_nets=()):
    deadline=time.monotonic()+_bound(timeout_s)
    if type(max_joins) is not int or not 1<=max_joins<=8 or type(max_attempts) is not int or not 1<=max_attempts<=64:
        raise ValueError('bounded_power_terminal_menu_required')
    if type(refine_maze) is not bool:raise ValueError('explicit_power_terminal_refinement_required')
    report=dict(joins=[],attempts=[],created_uuids=[],new_vias=0,new_zones=0,neckdowns=0,
        no_path_proof=False,whole_power_qualified=False,release_authority=False)
    inventory=tasks(board,source=source,board_hint=board_hint,radius_mm=radius_mm,
        timeout_s=max(.001,deadline-time.monotonic()),exclude_nets=exclude_nets)
    report['source_inventory']=inventory
    fed_islands=set()
    with search.scoped(work_limit) as budget, force._thermal_hint(board_hint):
        for task in inventory['tasks']:
            if time.monotonic()>=deadline or len(report['joins'])>=max_joins:break
            island=(task['net'],tuple(task['source_island_pad_uuids']))
            if island in fed_islands:continue
            for anchor in task['anchors']:
                if time.monotonic()>=deadline or len(report['attempts'])>=max_attempts or budget.stop_reason:break
                layer=anchor['layer'];name=fab.COPPER_LAYER_IDS[layer]
                width=math.ceil(task['branch_width_by_layer_mm'][name]*1e6)
                gap=math.ceil(task['contract']['clearance_mm']*1e6)
                attempt=dict(cap_uuid=task['cap_uuid'],net=task['net'],anchor=anchor,accepted=False)
                report['attempts'].append(attempt)
                validated=set()
                def validate(legs):
                    rows=[dict(net=task['net'],layer=layer,start_nm=list(a),end_nm=list(b),width_nm=w) for a,b,w in legs]
                    key=json.dumps(rows,sort_keys=True)
                    if key in validated:return True
                    bound=min(deadline,time.monotonic()+1.)
                    quality=craft.assess_proposed_route(board,rows,deadline=bound)
                    if not quality.get('ok') or not quality.get('complete'):
                        attempt.setdefault('craft_refusals',[]).append(quality);return False
                    check=field.assess_proposed_route(board,rows,netclass_resolver=fr._project_netclass_resolver(str(source)),deadline=bound)
                    if check.get('ok') is True and check.get('complete') is True:
                        validated.add(key);return True
                    attempt.setdefault('field_refusals',[]).append(check)
                    return False
                legs=fr._guarded_profiled_lastmile_legs(board,pcbnew.VECTOR2I(*task['start_nm']),
                    pcbnew.VECTOR2I(*anchor['point_nm']),width,layer,gap,board.GetNetcodeFromNetname(task['net']),
                    lambda a,b,half:fr._edge_leg_clear(board,a,b,half),allow_maze=True,maze_margin_mm=4.,
                    deadline_monotonic=min(deadline,time.monotonic()+2.),max_length_nm=radius_mm*1e6,
                    foreign_cache={},path_validator=validate,refine_maze=refine_maze)
                if not legs:
                    # The diagnostic API has no shared-deadline argument. Do
                    # not spend unbounded post-search time on a second scan.
                    attempt['refusal']=dict(reason='bounded_native_lastmile_exhausted',
                        deadline_reached=time.monotonic()>=deadline,
                        no_path_proof=False,start_nm=task['start_nm'],end_nm=anchor['point_nm'],
                        width_nm=width,clearance_nm=gap,layer=layer)
                    if not task['control_only_divider_motif'] or anchor['kind']!='pad_center':continue
                    by_id={force._uid(p):p for fp in board.GetFootprints() for p in fp.Pads()}
                    endpoints=[by_id[task['cap_uuid']],by_id[anchor['uuid']]]
                    preferred=_contained_bridge_seats(board,endpoints,clearance_nm=gap)
                    if not preferred:continue
                    project=fr._project_netclass_resolver(str(source))(task['net']) or {}
                    spec=dict(via_dia=project.get('via_diameter') or .6,via_drill=project.get('via_drill') or .3)
                    def bridge_ok(ops):
                        vias=[op for op in ops if op[0]=='via']
                        if len(vias)!=2 or {tuple(op[1]) for op in vias}!={tuple(p.GetPosition()) for p in endpoints}:return False
                        if any((op[3],op[2])!=tuple(preferred) for op in vias):return False
                        tracks=[(op[1],op[2],op[3],op[4]) for op in ops if op[0]=='trk']
                        if any(w!=math.ceil(task['branch_width_by_layer_mm'][fab.COPPER_LAYER_IDS[lid]]*1e6)
                                for a,b,w,lid in tracks):return False
                        rows=[dict(net=task['net'],layer=lid,start_nm=list(a),end_nm=list(b),width_nm=w)
                            for a,b,w,lid in tracks]
                        bound=min(deadline,time.monotonic()+1.)
                        quality=craft.assess_proposed_route(board,rows,deadline=bound)
                        if not quality.get('ok') or not quality.get('complete'):return False
                        check=field.assess_proposed_route(board,rows,
                            netclass_resolver=fr._project_netclass_resolver(str(source)),deadline=bound)
                        return check.get('ok') is True and check.get('complete') is True
                    ops,modes=cells._pofv_supply_bridge_ops(board,*endpoints,width,gap,
                        board.GetNetcodeFromNetname(task['net']),_bridge_layers(board,task,layer),spec,
                        ops_ok=bridge_ok,deadline_monotonic=min(deadline,time.monotonic()+2.),
                        max_length_nm=radius_mm*1e6,allow_maze=True,pofv_geometry=preferred)
                    if not ops:continue
                    ids=[]
                    for op in ops:
                        if op[0]=='via':
                            t=pcbnew.PCB_VIA(board);t.SetPosition(op[1]);t.SetDrill(round(op[2]*1e6));t.SetWidth(round(op[3]*1e6))
                            t.SetViaType(pcbnew.VIATYPE_THROUGH);t.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
                            report['new_vias']+=1
                        else:
                            t=pcbnew.PCB_TRACK(board);t.SetStart(op[1]);t.SetEnd(op[2]);t.SetWidth(op[3]);t.SetLayer(op[4])
                        t.SetNetCode(board.GetNetcodeFromNetname(task['net']));t.SetLocked(True);board.Add(t);ids.append(force._uid(t))
                    attempt.update(accepted=True,bridge_modes=modes)
                    report['joins'].append(dict(task=task,anchor=anchor,created_uuids=ids,control_only_pofv_bridge=True))
                    report['created_uuids'].extend(ids);fed_islands.add(island);break
                ids=[]
                for a,b,w in legs:
                    if w!=width:raise ValueError('power_terminal_body_width_changed')
                    t=pcbnew.PCB_TRACK(board);t.SetStart(a);t.SetEnd(b);t.SetWidth(w)
                    t.SetLayer(layer);t.SetNetCode(board.GetNetcodeFromNetname(task['net']));t.SetLocked(True)
                    board.Add(t);ids.append(force._uid(t))
                attempt['accepted']=True
                report['joins'].append(dict(task=task,anchor=anchor,created_uuids=ids))
                report['created_uuids'].extend(ids);fed_islands.add(island);break
        report['search_work']=budget.report()
    return report


def receive(source,candidate,*,board_hint,timeout_s=10.,radius_mm=6.,exclude_nets=()):
    """Re-derive all source ownership; a caller's success packet is not proof."""
    _bound(timeout_s);source,candidate=map(lambda p:Path(p).resolve(),(source,candidate))
    result=dict(ok=False,complete=False,errors=[],whole_power_qualified=False,release_authority=False)
    families=[force._family(p,board_hint) for p in (source,candidate)];epoch=force._code_identity()
    try:
        parent,child=[pcbnew.LoadBoard(str(p)) for p in (source,candidate)]
        inventory=tasks(parent,source=source,board_hint=board_hint,radius_mm=radius_mm,
            timeout_s=timeout_s,exclude_nets=exclude_nets)
        delta=additive.receive(source,candidate,timeout_s=timeout_s);result['additive']=delta
        if not delta['ok'] or not delta['complete']:raise ValueError('power_terminal_exact_additive_refused')
        _,old=additive._nodes(source);_,new=additive._nodes(candidate)
        incoming=set(new)-set(old);added=[t for t in child.GetTracks() if force._uid(t) in incoming]
        if not 1<=len(added)==len(incoming)<=128:raise ValueError('power_terminal_copper_only_delta_required')
        remaining={force._uid(t):t for t in added if t.GetClass()=='PCB_TRACK'}
        via_items={force._uid(t):t for t in added if t.GetClass()=='PCB_VIA'};gained=[]
        if len(remaining)+len(via_items)!=len(incoming):raise ValueError('power_terminal_unsupported_copper_kind')
        old_pads={force._uid(p):p for fp in parent.GetFootprints() for p in fp.Pads()};fed_islands=set()
        for task in inventory['tasks']:
            island=(task['net'],tuple(task['source_island_pad_uuids']))
            if island in fed_islands:continue
            for anchor in task['anchors']:
                matched=False
                for layer in [anchor['layer'],*_bridge_layers(parent,task,anchor['layer'])]:
                    cursor=tuple(task['start_nm']);end=tuple(anchor['point_nm']);chain=[];length=0.;seats=[]
                    if layer!=anchor['layer']:
                        if not task['control_only_divider_motif'] or anchor['kind']!='pad_center':continue
                        endpoints=[old_pads[task['cap_uuid']],old_pads[anchor['uuid']]]
                        preferred=_contained_bridge_seats(parent,endpoints,
                            clearance_nm=math.ceil(task['contract']['clearance_mm']*1e6))
                        if not preferred:continue
                        for pad in endpoints:
                            options=[(u,v) for u,v in via_items.items() if v.GetNetname()==task['net']
                                and tuple(v.GetPosition())==tuple(pad.GetPosition()) and v.GetViaType()==pcbnew.VIATYPE_THROUGH
                                and v.GetWidth()==round(preferred[0]*1e6) and v.GetDrill()==round(preferred[1]*1e6)
                                and int(v.TopLayer())==pcbnew.F_Cu and int(v.BottomLayer())==pcbnew.B_Cu]
                            if len(options)!=1:break
                            seats.append(options[0][0])
                        if len(seats)!=2:continue
                    width=math.ceil(task['branch_width_by_layer_mm'][fab.COPPER_LAYER_IDS[layer]]*1e6)
                    while cursor!=end:
                        choices=[(u,t) for u,t in remaining.items() if u not in chain
                            and t.GetNetname()==task['net'] and t.GetLayer()==layer and t.GetWidth()==width
                            and cursor in (tuple(t.GetStart()),tuple(t.GetEnd()))]
                        if len(choices)!=1:break
                        uid,t=choices[0];chain.append(uid);length+=t.GetLength()/1e6
                        if t.GetLength()<=0 or len(chain)>64 or length>radius_mm:break
                        cursor=tuple(t.GetEnd()) if cursor==tuple(t.GetStart()) else tuple(t.GetStart())
                    if cursor==end and chain and length<=radius_mm:
                        for uid in chain:remaining.pop(uid)
                        for uid in seats:via_items.pop(uid)
                        gained.append(dict(cap_uuid=task['cap_uuid'],net=task['net'],anchor=anchor,
                            track_uuids=chain,pofv_uuids=seats,branch_role=task['branch_role']))
                        fed_islands.add(island)
                        matched=True;break
                if matched:break
        if remaining or via_items or not gained:raise ValueError('unowned_or_incomplete_power_terminal_chain')
        result['gained_cells']=gained
        result['current_debt']=debt.receive(source,candidate,board_hint=board_hint)
        if not result['current_debt']['ok'] or not result['current_debt']['complete']:raise ValueError('power_terminal_current_receiving_refused')
        result['physical']=physical.evaluate(candidate,timeout_s=timeout_s)
        result['craft']=craft.analyze_board(child,track_uuid_scope=incoming)
        if not result['physical']['ok'] or not result['craft']['craft_ok']:raise ValueError('power_terminal_physical_or_craft_refused')
        grades=[]
        with tempfile.TemporaryDirectory(prefix='cec-power-terminal-grade-') as work:
            for name,path in [('source',source),('candidate',candidate)]:
                private=force._copy_family(path,Path(work)/name);out=Path(work)/(name+'.json')
                run=subprocess.run(['kicad-cli','pcb','drc','--format','json','--severity-all','--output',str(out),str(private)],
                    capture_output=True,text=True,timeout=timeout_s)
                if run.returncode:raise ValueError('power_terminal_native_drc_failed')
                grades.append(json.loads(out.read_text()))
        before,after=grades;known={stage._canonical_identity(v) for v in before['violations']}
        inventories=(silk._silk_inventory(parent,old),silk._silk_inventory(child,new))
        faults=[v for v in after['violations'] if stage._canonical_identity(v) not in known
            and not silk._inherited_silk_overlap(parent,child,v,old,new,inventories=inventories)]
        result.update(source_opens=len(before['unconnected_items']),opens=len(after['unconnected_items']),new_native_faults=faults)
        if faults or result['opens']>=result['source_opens']:raise ValueError('power_terminal_no_native_nonregressing_gain')
        with force._thermal_hint(board_hint):
            before_field=field.field_coupling_summary(str(source),board=parent)
            after_field=field.field_coupling_summary(str(candidate),board=child)
        result['new_field_blockers']=sorted(field.blocker_keys(after_field)-field.blocker_keys(before_field))
        if result['new_field_blockers']:raise ValueError('power_terminal_new_field_blocker')
        stable=families==[force._family(p,board_hint) for p in (source,candidate)] and epoch==force._code_identity()
        if not stable:raise ValueError('power_terminal_source_candidate_or_code_changed')
        result.update(ok=True,complete=True,source_candidate_and_code_unchanged=True)
    except Exception as exc:result['errors'].append(type(exc).__name__+':'+str(exc))
    return result


def run(source,directory,*,board_hint,source_sha256,timeout_s=10.,radius_mm=6.,exclude_nets=()):
    """Private pipeline entry: construct once, then independently receive.

    A partial retained connection is not a completed current domain or board.
    No source/authority file is rewritten, no board is published or promoted.
    """
    _bound(timeout_s);source,directory=map(lambda p:Path(p).resolve(),(source,directory))
    _excluded_nets(source,exclude_nets)
    protected=force._protected_paths(source,board_hint)
    force._check_proposal_directory(directory,protected)
    if directory.exists() or force._hash(source)!=source_sha256:
        raise ValueError('fresh_power_terminal_output_and_exact_source_required')
    family=force._family(source,board_hint);epoch=force._code_identity();directory.mkdir(parents=True)
    board=pcbnew.LoadBoard(str(source))
    report=dict(ok=False,prefix_accepted=False,source=str(source),source_sha256=source_sha256,
        release_authority=False,whole_power_qualified=False,completed_nets=[],selected=str(source))
    try:
        construction=construct(board,source=source,board_hint=board_hint,
            timeout_s=timeout_s,radius_mm=radius_mm,exclude_nets=exclude_nets)
        report['construction']=construction
        if construction['created_uuids']:
            candidate=force._copy_family(source,directory/'candidate')
            additive._ground_refill(board);field._save_field_snapshot(board,candidate)
            report['receiving']=receive(source,candidate,board_hint=board_hint,
                timeout_s=timeout_s,radius_mm=radius_mm,exclude_nets=exclude_nets)
            if report['receiving']['ok']:
                report.update(ok=True,prefix_accepted=True,selected=str(candidate),board=str(candidate),
                    board_sha256=force._hash(candidate),source_opens=report['receiving']['source_opens'],
                    opens=report['receiving']['opens'])
    except Exception as exc:report['errors']=[type(exc).__name__+':'+str(exc)]
    stable=family==force._family(source,board_hint) and epoch==force._code_identity()
    report['source_and_code_unchanged']=stable
    if not stable:report.update(ok=False,prefix_accepted=False,selected=str(source))
    force._write(directory/'receiving.json',report)
    return report
