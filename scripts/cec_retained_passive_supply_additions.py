"""Bounded local capacitor reconnection without retiring any supply copper.

The caller independently reconstructs the exact Source passive/Ground-via
pose and all additive native objects. This additional scope check permits
only short same-face, full-Source-current capacitor links. It grants no bus,
barrel, pour, load, clearance, physical-return or fabrication authority.
"""
import math
import re
import time
import pcbnew
import cec_constraints as constraints
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_force_current as force
import cec_route_quality as quality


def detached_leaf_ports(source, candidate, source_pad_uuid):
    """Literal old cap-end pickups needing reconnection, not a copper cut.

    Rejoining a moved cap only at its IC can strand the old pickup as a
    dangling stub even though the net is globally connected. Prefer its
    actual existing free endpoint. Every Source conductor remains present.
    This read-only hint is neither current nor construction authority.
    """
    pads={force._uid(p):p for f in source.GetFootprints() for p in f.Pads()}
    targets={force._uid(p):p for f in candidate.GetFootprints() for p in f.Pads()}
    if source_pad_uuid not in pads or source_pad_uuid not in targets:
        raise ValueError('literal_source_capacitor_pickup_pad_required')
    pad,target=pads[source_pad_uuid],targets[source_pad_uuid]
    face=cells.cec_return_escape.smd_surface_layer(pad)
    if face is None or pad.GetNetname()=='GND' or pad.GetNetCode()<=0:
        raise ValueError('positive_surface_supply_pickup_required')
    edges=[t for t in source.GetTracks() if t.GetNetname()==pad.GetNetname() and t.IsOnLayer(face)]
    lands=[p for uid,p in pads.items() if uid!=source_pad_uuid and p.GetNetname()==pad.GetNetname() and p.IsOnLayer(face)]
    ports=[]
    for edge in edges:
        if edge.GetClass()!='PCB_TRACK' or not edge.GetEffectiveShape(face).Collide(pad.GetEffectiveShape(face),0):continue
        for at in (edge.GetStart(),edge.GetEnd()):
            if not pad.HitTest(at,0) or target.HitTest(at,0):continue
            if any(p.GetEffectiveShape(face).Collide(at,0) for p in lands):continue
            if any(force._uid(t)!=force._uid(edge) and t.GetEffectiveShape(face).Collide(at,0) for t in edges):continue
            ports.append(dict(at_nm=list(at),layers=[int(face)],native_uuids=[force._uid(edge)]))
    if len(ports)>16:raise ValueError('bounded_literal_detached_supply_pickups_required')
    return sorted(ports,key=lambda q:(q['at_nm'],q['native_uuids']))


def inspect(source, candidate, selected_footprint_uuids, added_native_uuids, *,
            board_hint, timeout_s=10.):
    if (type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not 0<timeout_s<=10.
            or type(board_hint) is not str or not board_hint
            or type(selected_footprint_uuids) not in (list,tuple,set)
            or not 1<=len(selected_footprint_uuids)<=4
            or len(set(selected_footprint_uuids))!=len(selected_footprint_uuids)
            or type(added_native_uuids) not in (list,tuple,set)
            or not 1<=len(added_native_uuids)<=32
            or len(set(added_native_uuids))!=len(added_native_uuids)):
        raise ValueError('bounded_retained_capacitor_supply_additions_required')
    deadline=time.monotonic()+timeout_s
    def tick():
        if time.monotonic()>=deadline:raise ValueError('retained_capacitor_supply_addition_deadline')
    first={force._uid(f):f for f in source.GetFootprints()}
    last={force._uid(f):f for f in candidate.GetFootprints()}
    if first.keys()!=last.keys() or not set(selected_footprint_uuids)<=first.keys():
        raise ValueError('literal_retained_capacitor_population_required')
    with force._thermal_hint(board_hint):
        assigned=constraints._device_bypass_assignment(source,project_max_mm=3.5)
    scopes=[]
    for uid in selected_footprint_uuids:
        tick();a,b=first[uid],last[uid]
        if (a.IsDNP() or a.IsLocked() or not re.search(r'(?:^|:)C_[0-9]{4}(?:_|$)',a.GetFPIDAsString())
                or len(list(a.Pads()))!=2 or len(list(b.Pads()))!=2):
            raise ValueError('source_selected_populated_surface_capacitor_required')
        matches=[q['requirement'] for q in assigned['assigned'].values() if q['cap_ref']==a.GetReference()]
        if len(matches)!=1:raise ValueError('unique_source_selected_capacitor_assignment_required')
        req=matches[0];owner=source.FindFootprintByReference(req['ref'])
        peer=candidate.FindFootprintByReference(req['ref'])
        model=roles.footprint_contract(owner) if owner else None
        if (owner is None or peer is None or force._uid(owner) in selected_footprint_uuids
                or tuple(owner.GetPosition())!=tuple(peer.GetPosition())
                or owner.GetOrientationDegrees()!=peer.GetOrientationDegrees()
                or owner.IsFlipped()!=peer.IsFlipped() or not model
                or model!=roles.footprint_contract(peer)
                or set(p.GetNumber() for p in owner.Pads())!=set(model['pins'])
                or model['pins'].get(str(req['pin'])) not in ('power_input','power_output')):
            raise ValueError('exact_stationary_complete_manufacturer_supply_owner_required')
        positive=next((p for p in a.Pads() if p.GetNetname()==req['rail']),None)
        target=next((p for p in b.Pads() if force._uid(p)==force._uid(positive)),None) if positive else None
        supply=owner.FindPadByNumber(str(req['pin']))
        face=cells.cec_return_escape.smd_surface_layer(positive) if positive else None
        if (positive is None or target is None or supply is None or face is None
                or req['rail']=='GND' or supply.GetNetname()!=req['rail']
                or (req.get('return_rail') or 'GND')!='GND'
                or {p.GetNetname() for p in a.Pads()}!={'GND',req['rail']}
                or any(p.HasHole() or p.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD for p in [*a.Pads(),*b.Pads(),*owner.Pads()])
                or cells.cec_return_escape.smd_surface_layer(target)!=face or not supply.IsOnLayer(face)
                or any(math.dist(tuple(p.GetPosition()),tuple(supply.GetPosition()))>3500000 for p in (positive,target))):
            raise ValueError('actual_source_and_target_local_surface_capacitor_required')
        with force._thermal_hint(board_hint): current=cells._supply_current_widths(source,req['rail'])
        if not current or face not in current['required_by_layer_nm']:
            raise ValueError('positive_unchanged_full_source_supply_current_required')
        floor=max(200000,int(source.GetDesignSettings().m_TrackMinWidth),
            int(cells._netclass(source,req['rail'])['width']),int(current['required_by_layer_nm'][face]))
        # Preserve the Source launch width too, not just a newly computed
        # smaller minimum. Existing barrels, wide buses and every old stroke
        # remain literal unchanged objects under the outer additive replay.
        for t in source.GetTracks():
            tick()
            if (t.GetClass()=='PCB_TRACK' and t.GetNetname()==req['rail'] and t.GetLayer()==face
                    and t.GetEffectiveShape(face).Collide(positive.GetEffectiveShape(face),0)):
                floor=max(floor,int(t.GetWidth()))
        scopes.append(dict(capacitor_pad=target,owner_pad=peer.FindPadByNumber(str(req['pin'])),
            source_capacitor_pad_uuid=force._uid(positive),
            net=req['rail'],face=int(face),width_floor_nm=floor,current=current,
            source_owner_role=model['pins'][str(req['pin'])],manufacturer_source=model['source']))
    old={force._uid(t) for t in source.GetTracks()};live={force._uid(t):t for t in candidate.GetTracks()}
    if set(added_native_uuids)&old or not set(added_native_uuids)<=live.keys():
        raise ValueError('exact_new_native_supply_track_identity_required')
    graph=pcbnew.CONNECTIVITY_DATA();selected=[];length=0
    for uid in added_native_uuids:
        tick();t=live[uid]
        if (t.GetClass()!='PCB_TRACK' or t.GetParentGroup() is not None or t.HasSolderMask()
                or not 0<t.GetLength()<=8000000
                or not quality.is_canonical_stroke(tuple(t.GetStart()),tuple(t.GetEnd()),tolerance_nm=0)):
            raise ValueError('new_canonical_same_face_supply_strokes_only')
        owners=[s for s in scopes if s['net']==t.GetNetname() and s['face']==int(t.GetLayer())
            and t.GetWidth()>=s['width_floor_nm']
            and all(math.dist(tuple(p),tuple(s['capacitor_pad'].GetPosition()))<=6000000
                for p in (t.GetStart(),t.GetEnd()))]
        if not owners:raise ValueError('full_source_width_and_local_capacitor_supply_scope_required')
        length+=t.GetLength()
        if length>32000000:raise ValueError('bounded_total_retained_capacitor_supply_length_required')
        if not graph.Add(t):raise ValueError('native_supply_component_inventory_refused')
        selected.append((t,owners))
    pending=set(added_native_uuids);components=[]
    actual=pcbnew.CONNECTIVITY_DATA()
    for item in [*[p for f in candidate.GetFootprints() for p in f.Pads()],*candidate.GetTracks()]:
        tick()
        if not actual.Add(item):raise ValueError('native_capacitor_supply_contact_graph_refused')
    while pending:
        tick();uid=min(pending);t=live[uid]
        group=({uid}|{force._uid(q) for q in graph.GetConnectedItems(t)})&pending
        pending-=group;roots=[]
        for s in scopes:
            cap=s['capacitor_pad'];owner=s['owner_pad'];face=s['face']
            if not any(live[u].GetNetname()==s['net'] and live[u].GetLayer()==face
                    and live[u].GetEffectiveShape(face).Collide(cap.GetEffectiveShape(face),0) for u in group):continue
            reached={force._uid(q) for q in actual.GetConnectedItems(cap)}|{force._uid(cap)}
            if not group<=reached or force._uid(owner) not in reached:continue
            roots.append(dict(capacitor_pad_uuid=force._uid(cap),owner_pad_uuid=force._uid(owner),
                source_owner_role=s['source_owner_role'],manufacturer_source=s['manufacturer_source'],
                unchanged_full_rail_current_contract=s['current'],width_floor_nm=s['width_floor_nm']))
        if not roots:raise ValueError('every_new_supply_component_must_reconnect_its_actual_capacitor_and_owner')
        components.append(dict(new_track_uuids=sorted(group),source_selected_supply_roots=roots))
    pickup_receiving=[]
    for s in scopes:
        for port in detached_leaf_ports(source,candidate,s['source_capacitor_pad_uuid']):
            tick();at=pcbnew.VECTOR2I(*port['at_nm']);face=s['face']
            if not any(live[u].GetNetname()==s['net'] and live[u].GetLayer()==face
                    and live[u].GetEffectiveShape(face).Collide(at,0) for u in added_native_uuids):
                raise ValueError('detached_source_capacitor_pickup_must_be_rejoined_not_left_dangling')
            pickup_receiving.append(port)
    return dict(components=components,added_track_count=len(added_native_uuids),
        detached_source_pickups_rejoined=pickup_receiving,
        no_source_supply_conductor_barrel_or_pour_change_authorized=True,
        source_input_output_roles_and_full_rail_current_preserved=True,
        independent_original_partitions_current_ground_fields_drc_and_stack_required=True,
        current_qualified=False,routing_admitted=False,release_authority=False)
