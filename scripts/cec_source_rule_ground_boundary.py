"""Bounded native-boundary Ground dogbones under an EXISTING saved pad rule.

This separate tier never changes ordinary dimensions or guesses a cap role.
Every proposal owes exact native physical, live process and reference proofs.
The enclosing source-literal saved/current/partition/native receivers remain due.
"""
import math
import time
from pathlib import Path
import pcbnew
from shapely.geometry import LineString,box
import cec_assembly_envelope as assembly
import cec_decoupler_cell as cells
import cec_existing_local_pofv_pad_rule as rule
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_shortcut as ground
import cec_ground_mesh_entry as mesh
import cec_source_ground_leaf as source_leaf
import cec_source_netlist_semantics as semantic
from cec_native_items import discard_items


def _require(ok,reason):
    if not ok:raise ValueError(reason)


def _source_role(board,pad,board_hint,deadline):
    uid=force._uid(pad)
    candidates=source_leaf._candidates(board)
    selected=candidates.get(uid)
    if not selected or selected[1]not in('source_control_shunt_ground','source_manufacturer_functional_ground_pin'):
        raise ValueError('positive_source_functional_or_control_shunt_ground_required')
    proof=source_leaf.plan(board,board_hint=board_hint,timeout_s=min(10.,max(.001,deadline-time.monotonic())))
    _require(proof.get('complete')and not proof.get('errors'),'complete_source_ground_boundary_intent_required')
    actual=proof.get('proofs',{}).get(uid)
    _require(actual is not None and actual.get('kind')==selected[1]
        and actual.get('owner')==pad.GetParentFootprint().GetReference()
        and actual.get('pin')==pad.GetNumber()and actual.get('net')=='GND',
        'exact_source_ground_boundary_pin_required')
    normalized=semantic.replay_identity(actual)
    files=actual['schematic_files_sha256'];exporter=actual['exporter']
    _require(all(force._hash(Path(p))==h for p,h in files.items())
        and force._hash(Path(exporter['exporter']))==exporter['exporter_sha256'],
        'source_ground_boundary_schematic_or_exporter_changed')
    if actual['kind']=='source_control_shunt_ground':
        controls=[v for v in candidates.values()if v[1]=='source_control_shunt_ground'
            and v[3]is not None and force._uid(v[3])==force._uid(selected[3])]
        _require(len(controls)==1,'unique_source_ground_boundary_control_shunt_required')
    return normalized


def _native_polygon(shape):
    poly=pcbnew.SHAPE_POLY_SET();shape.TransformToPolygon(poly,1000,pcbnew.ERROR_OUTSIDE)
    result=assembly.polygon_from_native(poly)
    _require(result.is_valid and not result.is_empty,'native_ground_boundary_shape_required')
    return result


def _coordinates(shape):
    if hasattr(shape,'geoms'):
        return [p for part in shape.geoms for p in _coordinates(part)]
    return list(shape.coords)if not shape.is_empty else[]


def _immutable_zone_clear(board,start,end,width_nm,face,clearance_nm,net_code):
    """No refill/antipad credit against any saved foreign filled copper."""
    segment=pcbnew.SHAPE_SEGMENT(start,end,width_nm)
    local_clearance=fr._foreign_clearance_resolver(board)
    for zone in board.Zones():
        if zone.GetIsRuleArea()or zone.GetNetCode()==net_code or not zone.IsOnLayer(face):continue
        if not zone.IsFilled()or not zone.HasFilledPolysForLayer(face):
            raise ValueError('foreign_ground_boundary_zone_fill_unknown')
        gap=max(clearance_nm,int(zone.GetLocalClearance()),int(local_clearance(zone,face)))
        if zone.GetFilledPolysList(face).Collide(segment,gap):return False
    return True


def boundary_events(board,pad,diameter_nm,clearance_nm,reach_mm,*,deadline,max_events=64):
    """Pure finite proposal region. Exact guards, not this polygon, admit ink/copper."""
    _require(type(max_events)is int and 1<=max_events<=64,'bounded_ground_boundary_event_count_required')
    pos=pad.GetPosition();origin=(pos.x/1e6,pos.y/1e6);reach=reach_mm
    axes=((1,0),(0,1),(1,1),(1,-1));events={};cache={};examined=0
    def add(polygon,margin,identity,priority):
        nonlocal examined
        _require(time.monotonic()<deadline,'source_ground_boundary_event_deadline')
        expanded=polygon.buffer(margin,join_style=1)
        for dx,dy in axes:
            factor=reach/math.hypot(dx,dy)
            cut=expanded.intersection(LineString([(origin[0]-dx*factor,origin[1]-dy*factor),
                (origin[0]+dx*factor,origin[1]+dy*factor)]))
            for x,y in _coordinates(cut):
                d=round(((x-origin[0])/dx if dx else(y-origin[1])/dy)*1e6)
                at=(pos.x+dx*d,pos.y+dy*d);distance=math.dist(tuple(pos),at)/1e6
                if distance<=0 or distance>reach+1e-12:continue
                event=dict(at_nm=list(at),distance_mm=distance,origin=identity)
                key=(priority,distance,at)
                if at not in events or key<events[at][0]:events[at]=(key,event)
        examined+=1
    # A separated dogbone first clears its own real pad face. No fixed
    # radius is inferred from pad_minor; native final rule forbids overlap.
    add(_native_polygon(pad.GetEffectiveShape(cells._ground_terminal_layer(pad))),
        diameter_nm/2e6+.002,dict(kind='native_source_pad_face_exit',uuid=force._uid(pad)),0)
    extent=round((reach+diameter_nm/2e6+.5)*1e6)
    query=pcbnew.BOX2I(pcbnew.VECTOR2I(pos.x-extent,pos.y-extent),pcbnew.VECTOR2I(2*extent,2*extent))
    crop=box(origin[0]-reach-.5,origin[1]-reach-.5,origin[0]+reach+.5,origin[1]+reach+.5)
    for layer in board.GetEnabledLayers().CuStack():
        # Ordinary saved fills are not route reservations in fr's generic
        # indexes; this tier nevertheless owes immutable foreign fields.
        for zone in board.Zones():
            if zone.GetIsRuleArea()or zone.GetNetCode()==pad.GetNetCode()or not zone.IsOnLayer(layer):continue
            _require(zone.IsFilled()and zone.HasFilledPolysForLayer(layer),
                'foreign_ground_boundary_zone_fill_unknown')
            polygon=assembly.polygon_from_native(zone.GetFilledPolysList(layer)).intersection(crop)
            if not polygon.is_empty:
                add(polygon,diameter_nm/2e6+max(clearance_nm,int(zone.GetLocalClearance()))/1e6+.002,
                    dict(kind='saved_foreign_filled_zone',uuid=force._uid(zone),proposal_face=int(layer)),1)
        zones,copper=fr._foreign_shape_indexes(board,int(layer),{pad.GetNetCode()},cache=cache)
        for index in(zones,copper):
            for row in fr._indexed_shape_rows(index,query):
                _require(time.monotonic()<deadline,'source_ground_boundary_event_deadline')
                polygon=_native_polygon(row[0]).intersection(crop)
                if polygon.is_empty:continue
                gap=max(clearance_nm,int(row[3])if len(row)>3 else 0)
                add(polygon,diameter_nm/2e6+gap/1e6+.002,
                    dict((row[2]or{})if len(row)>2 else{},proposal_face=int(layer)),1)
    rows=[r for _,r in sorted(events.values(),key=lambda p:p[0])]
    return dict(events=rows[:max_events],generated=len(rows),truncated=max(0,len(rows)-max_events),
        native_shapes_examined=examined,proposal_polygon_error_nm=1000,proposal_guard_nm=2000)


def construct(board,pad,*,board_path,reach_mm,lock=False,diagnostics=None,timeout_s=3.):
    """Return (normal Ground-result,error); absent exact rule is neutral.

    On every refusal all native items/groups are rolled back. This is a
    constructor only, not saved source/current/native/fabrication admission.
    """
    if(type(timeout_s)not in(int,float)or not math.isfinite(timeout_s)or not 0<timeout_s<=10
        or type(reach_mm)not in(int,float)or not math.isfinite(reach_mm)or not 0<reach_mm<=1.5
        or type(lock)is not bool):raise ValueError('bounded_source_rule_ground_boundary_lease_required')
    started=time.monotonic();deadline=started+timeout_s;info=diagnostics if diagnostics is not None else{}
    info.update(scope='existing_source_rule_ground_native_boundary_events',applicable=False,
        generated_choices=0,consumed_events=0,release_authority=False,current_authority=False,
        timeout_s=timeout_s,requested_reach_mm=reach_mm,
        source_pad_geometry=dict(uuid=force._uid(pad),position_nm=list(pad.GetPosition()),
            size_nm=list(pad.GetSize()),shape=int(pad.GetShape()),
            copper_layers=list(map(int,pad.GetLayerSet().CuStack()))))
    context=rule.resolve(board,pad)
    if context is None:return None,'source_rule_ground_boundary_not_applicable'
    created=[];group_state={force._uid(g):(g,set(force._uid(i)for i in g.GetItems()))for g in board.Groups()}
    try:
        _require(pad.GetNetname()=='GND'and pad.GetNetCode()>0 and not pad.HasHole()
            and pad.GetAttribute()==pcbnew.PAD_ATTRIB_SMD,'actual_source_surface_ground_required')
        role=_source_role(board,pad,str(board_path),deadline)
        if role['kind']=='source_control_shunt_ground':
            _require(reach_mm<=.8,'unchanged_control_shunt_ground_reach_required')
        diameter,drill=rule.geometry(context,(context['minimum_nm']['via_diameter']/1e6,
            context['minimum_nm']['hole_size']/1e6));dia=round(diameter*1e6);hole=round(drill*1e6)
        spec=cells._netclass(board,'GND');width=max(int(board.GetDesignSettings().m_TrackMinWidth),int(spec['width']))
        gap=max(200000,int(board.GetDesignSettings().m_MinClearance),int(spec['clearance']))
        _require(width>0,'source_ground_boundary_full_class_width_required')
        face=cells._ground_terminal_layer(pad);pos=pad.GetPosition()
        inventory=boundary_events(board,pad,dia,gap,reach_mm,deadline=deadline)
        info.update(applicable=True,source_rule=context,source_role=role,geometry_nm=dict(diameter=dia,drill=hole,lead=width,clearance=gap),
            boundary_inventory={k:v for k,v in inventory.items()if k!='events'},refusals=[])
        for event in inventory['events']:
            _require(time.monotonic()<deadline,'source_ground_boundary_constructor_deadline')
            info['consumed_events']+=1;at=pcbnew.VECTOR2I(*event['at_nm']);report={}
            owner=dict(pad=pad,start=pos,layer=int(face))
            if not fr._via_spot_clear(board,at,dia,gap,{pad.GetNetCode()},drill_nm=hole,
                    net_code=pad.GetNetCode(),local_pofv_dogbone=owner,report=report):
                info['refusals'].append(dict(event=event,check='native_via',evidence=report));continue
            checks=[fr._tap_foreign_clear(board,pos,at,width,face,gap,{pad.GetNetCode()}),
                _immutable_zone_clear(board,pos,at,width,face,gap,pad.GetNetCode()),
                all(_immutable_zone_clear(board,at,at,dia,int(layer),gap,pad.GetNetCode())
                    for layer in board.GetEnabledLayers().CuStack()),
                fr._edge_leg_clear(board,pos,at,width/2+gap),fr._edge_leg_clear(board,at,at,dia/2+gap),
                cells._hole_to_hole_clear(board,at,drill)[0],
                fr._tap_pair_overlap_clear(board,pos,at,width,face,pad.GetNetCode(),set())]
            if not all(checks):
                info['refusals'].append(dict(event=event,check='full_class_lead_edge_hole_pair',checks=checks));continue
            via=pcbnew.PCB_VIA(board);via.SetPosition(at);via.SetWidth(dia);via.SetDrill(hole)
            via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNetCode(pad.GetNetCode());via.SetLocked(lock);board.Add(via)
            track=pcbnew.PCB_TRACK(board);track.SetStart(pos);track.SetEnd(at);track.SetWidth(width)
            track.SetLayer(face);track.SetNetCode(pad.GetNetCode());track.SetLocked(lock);board.Add(track);created=[track,via]
            try:
                local=fab.local_pofv_via_decision(board,via,reach_mm=reach_mm)
                _require(local[0]is True,'live_source_ground_boundary_process_refused')
                contacts=ground._reference_contacts(board,via);mesh._reference_envelopes(board,via,contacts,deadline)
                _require(time.monotonic()<deadline,'source_ground_boundary_constructor_deadline')
                membership=fr.group_local_pofv_signal_vias(board,[via])
                _require(bool(membership),'source_ground_boundary_exact_native_group_required')
            except ValueError as exc:
                discard_items(board,created);created=[]
                info['refusals'].append(dict(event=event,check='live_process_reference_membership',reason=str(exc)));continue
            info.update(generated_choices=1,selected_event=event,actual_reference_contacts=contacts,
                existing_native_group_membership=membership,elapsed_s=time.monotonic()-started)
            return dict(status='source-rule-ground-boundary-dogbone',distance_mm=event['distance_mm'],
                via_uuid=force._uid(via),items=created,diameter_mm=diameter,drill_mm=drill,
                source_rule=context,source_role=role,full_class_lead_width_nm=width,
                full_native_reference_annuli=True,ordinary_global_floors_unchanged=True,
                saved_source_current_native_and_return_receiving_still_required=True),None
        return None,'source_rule_ground_boundary_finite_events_refused'
    except (ValueError,RuntimeError,TypeError,OSError)as exc:
        info['error']=type(exc).__name__+':'+str(exc)
        return None,info['error']
    finally:
        if not info['generated_choices']:
            if created:discard_items(board,created)
            for group in list(board.Groups()):
                previous=group_state.get(force._uid(group))
                if previous is None:discard_items(board,[group]);continue
                for item in list(group.GetItems()):
                    if force._uid(item)not in previous[1]:group.RemoveItem(item)
        info['elapsed_s']=time.monotonic()-started
