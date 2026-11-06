"""Fresh pending full-current reconstruction, never priority/cut admission.

The enclosing saved macro receiver independently compiles every Source cut.
Packet records are claims to compare, not proof inputs. This observer replays
the existing singleton current owners and complete native component demands.
Its result can affect ONLY the priority-motion refusal: incoming barrels must
still face all ordinary geometry checks and all saved/current gates remain.
"""
import copy
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_decoupler_cell as cells
import cec_fab_profile as fab
import cec_force_current as force
import cec_full_current_planar_reflow as full
import cec_macro_cut_components as components
import cec_measurement_leaf as leaf
import cec_native_construction_frame as frame
from cec_native_items import discard_items


KIND = 'unchanged_full_current_source_edge'


def _need(value, reason):
    if not value:raise ValueError('priority_reconstruction_'+reason)


def _stable(value):
    def unique(rows):
        result={}
        for key,item in rows:
            _need(key not in result,'ambiguous_JSON_key')
            result[key]=item
        return result
    # Native layer-keyed dictionaries become named JSON keys at the Source
    # producer boundary; normalize that exact representation, not key order.
    literal=json.loads(json.dumps(value,allow_nan=False),object_pairs_hook=unique)
    return json.dumps(literal,sort_keys=True,separators=(',', ':'),allow_nan=False)


def _ids(value, limit, label):
    _need(type(value)is list and len(value)<=limit and all(type(u)is str and u for u in value)
        and len(set(value))==len(value), 'unique_bounded_'+label)
    return set(value)


def _groups(board,item):
    return sorted((force._uid(g),g.GetName(),g.IsLocked(),
        sorted(force._uid(q)for q in g.GetItems()))for g in board.Groups()if g.ContainsItem(item))


def _definition(node, omit):
    return [r for r in node if not(isinstance(r,list)and r and r[0]in omit)]


def _contained(pad,via,face):
    if not pad.IsOnLayer(face)or not via.IsOnLayer(face):return False
    shape=pcbnew.SHAPE_POLY_SET()
    via.TransformShapeToPolygon(shape,face,0,1,pcbnew.ERROR_OUTSIDE)
    shape.BooleanSubtract(pad.GetEffectivePolygon(face,pcbnew.ERROR_INSIDE))
    return not shape.OutlineCount()


def _seat(board,pad,via,tracks):
    """Same actual SMD land, complete native in-pad or literal dogbone."""
    faces=[l for l in board.GetEnabledLayers().CuStack()if pad.IsOnLayer(l)]
    if (pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD or pad.HasHole()or len(faces)!=1
            or pad.GetNetname()!=via.GetNetname()):return False
    face=faces[0]
    if _contained(pad,via,face):return True
    for t in tracks.values():
        if t.GetClass()!='PCB_TRACK'or t.GetNetname()!=via.GetNetname()or not t.IsOnLayer(face):continue
        for a,b in ((t.GetStart(),t.GetEnd()),(t.GetEnd(),t.GetStart())):
            if tuple(b)==tuple(via.GetPosition())and fab.local_pofv_dogbone_matches(
                    pad,a,b,face,via.GetNetCode()):return True
    return False


def _supply_owner(source, candidate, proposal, pad, requests, board_hint, deadline, cache):
    """Reprove the actual supply role without pretending every owner is a cap.

    A monitor divider's upper rail land retains the complete rail contract;
    its resistance does not grant a reduced-current launch or barrel rating.
    """
    selected = proposal.get('selected_programming_resistors', {})
    matches = [item for item in selected.values()
        if item.get('source_monitor_divider', {}).get('upper_motion') is True
        and item['source_monitor_divider'].get('upper_power_pad_uuid') == force._uid(pad)]
    if matches:
        _need(len(matches) == 1, 'unique_selected_monitor_supply_owner')
        if 'monitor_requests' not in cache:
            import cec_programming_resistor_placement as programming
            remaining = deadline - time.monotonic()
            _need(remaining > 0, 'deadline')
            cache['monitor_requests'] = programming.requests(source, candidate, proposal,
                timeout_s=min(10., remaining))
        key = 'monitor_divider_supply:' + force._uid(pad)
        fresh = cache['monitor_requests'].get(key)
        _need(fresh is not None and key in requests
            and _stable(requests[key]) == _stable(fresh), 'fresh_complete_monitor_supply_request')
        item = fresh['source_programming_resistor']; divider = item['source_monitor_divider']
        _need(fresh['no_power_bypass_or_current_authority'] is True
            and fresh['new_barrel_authority'] is False
            and fresh['unchanged_full_rail_current_contract']
            and divider['supply_net'] == pad.GetNetname(), 'unchanged_monitor_supply_authority')
        role = dict(reference=divider['upper_reference'], rail=divider['supply_net'],
            source_programming_resistor=item,
            required_full_rail_request_id=key,
            unchanged_full_rail_current_contract=fresh['unchanged_full_rail_current_contract'],
            bypass_owner=False, new_current_authority=False, barrel_capacity_qualified=False)
        return 'source_selected_monitor_divider', role, divider['upper_reference']
    role = leaf._bypass_supply_owner(source, pad, board_hint)
    return 'source_selected_bypass', role, role['cap_ref']


def inspect(source,candidate,transport,packet,*,board_hint,timeout_s=10.):
    """Read-only, single <=10s observer. No supplied proof is authority."""
    _need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=10.,'bounded_deadline')
    deadline=time.monotonic()+timeout_s
    def tick():_need(time.monotonic()<deadline,'deadline')
    tick()
    _need(type(board_hint)is str and board_hint and type(packet)is dict
        and packet.get('scope')=='source_typed_complete_native_macro_requests','complete_Source_packet')
    import cec_cell_macro_requests as compiler
    path=Path(packet['source']).resolve(strict=True)
    _need(Path(source.GetFileName()).resolve()==path,'literal_Source_path')
    epoch=force._code_identity();sha=force._hash(path);family=force._family(path,board_hint)
    proposal=packet.get('source_plan',{})
    _need(packet.get('source_sha256')==sha and packet.get('code_identity')==epoch
        and proposal.get('board_hint')==board_hint
        and proposal.get('source_native_binding')==compiler.row._source_binding(source)
        and _stable(packet.get('transport'))==_stable(transport),'Source_code_transport_binding')
    claimed=_stable(packet);motion=_stable(transport)
    _need(len(claimed.encode())<=32*1024*1024,'packet_size')
    bindings=[frame.binding(b,deadline)for b in(source,candidate)]
    def live():
        tick()
        _need(sha==force._hash(path)and epoch==force._code_identity()
            and family==force._family(path,board_hint)and claimed==_stable(packet)
            and motion==_stable(transport)
            and bindings==[frame.binding(b,deadline)for b in(source,candidate)],'live_inputs_changed')
        tick()
    try:
        old={force._uid(t):t for t in source.GetTracks()};new={force._uid(t):t for t in candidate.GetTracks()}
        pads={force._uid(p):p for f in source.GetFootprints()for p in f.Pads()}
        targets={force._uid(p):p for f in candidate.GetFootprints()for p in f.Pads()}
        layers=tuple(map(int,source.GetEnabledLayers().CuStack()))
        _need(old.keys()==new.keys()and pads.keys()==targets.keys()
            and layers==tuple(map(int,candidate.GetEnabledLayers().CuStack())),'UNCUT_population_and_stack')
        changes=transport.get('changes');extras=packet.get('additional_source_boundary_ownership')
        records=packet.get('additional_source_cut_components');requests=packet.get('requests')
        _need(type(changes)is list and len(changes)<=512 and type(extras)is list and len(extras)<=64
            and type(records)is list and len(records)<=64 and type(requests)is dict and len(requests)<=64,'bounded_records')
        changed={q['uuid']:q for q in changes}
        _need(len(changed)==len(changes),'unique_changes')
        retired=_ids(packet.get('retired_track_uuids'),128,'retirements')
        _need(retired<=old.keys()and all(old[u].GetClass()=='PCB_TRACK'for u in retired),'track_only_cuts')
        rated=[r for r in extras if r.get('authority',{}).get('kind')==KIND]
        rated_ids={r['change']['uuid']for r in rated}
        _need(0<len(rated)==len(rated_ids)<=16 and rated_ids<=retired,
            'rated_retired_changes:'+str((len(rated),len(rated_ids),sorted(rated_ids-retired))))
        _,source_nodes=frame.nodes(source,deadline);_,candidate_nodes=frame.nodes(candidate,deadline)
        source_zones={force._uid(z)for z in source.Zones()}
        _need(source_zones=={force._uid(z)for z in candidate.Zones()}
            and all(_stable(source_nodes[u])==_stable(candidate_nodes[u])for u in source_zones),'unchanged_UNCUT_Source_zones')
        fresh=[];nets=set()
        for record in rated:
            tick();uid=record['change']['uuid'];a,b=old[uid],new[uid];saved=record['authority']
            actual=record['change']
            _need((uid not in changed or _stable(actual)==_stable(changed[uid]))
                and (uid in changed or [list(a.GetStart()),list(a.GetEnd())]==[list(b.GetStart()),list(b.GetEnd())])
                and a.GetClass()==b.GetClass()=='PCB_TRACK'
                and not a.HasSolderMask()and _stable(_definition(source_nodes[uid],{'start','end'}))==
                _stable(_definition(candidate_nodes[uid],{'start','end'}))
                and _stable(record['change'].get('source_nm'))==_stable([list(a.GetStart()),list(a.GetEnd())])
                and _stable(record['change'].get('candidate_nm'))==_stable([list(b.GetStart()),list(b.GetEnd())]),'literal_rated_transport')
            plan=saved.get('source_plan',{})
            derived=full.plan(source,path,board_hint=board_hint,retired_track_uuids=[uid],
                timeout_s=max(.001,deadline-time.monotonic()),
                max_source_track_mm=plan.get('max_source_track_mm',8.),max_source_cut_mm=plan.get('max_source_cut_mm',32.))
            authority=dict(kind=KIND,native_source_uuid=uid,source_plan=derived)
            _need(_stable(saved)==_stable(authority),'fresh_entire_singleton_current_plan')
            fresh.append(dict(change=copy.deepcopy(actual),authority=authority));nets.add(a.GetNetname())
        # A same-rail omission cannot vanish from component/contact accounting
        # by relabelling just one record as ordinary or omitting its proof.
        _need({u for u in retired if old[u].GetNetname()in nets}==rated_ids,'complete_same_rail_rated_cut_denominator')
        cut=frame.clone(candidate,deadline)
        discard_items(cut,[t for t in cut.GetTracks()if force._uid(t)in retired])
        demands,derived_components=components.requests(source,cut,fresh,retired,transport,
            project_contacts=compiler._project_contacts,deadline=deadline)
        selected_records=[r for r in records if set(r.get('source_extra_edge_uuids',[]))&rated_ids]
        _need(_stable(selected_records)==_stable(derived_components),'fresh_complete_component_inventory')
        contracts={}
        for net in nets:
            tick()
            with force._thermal_hint(board_hint):contracts[net]=cells._supply_current_widths(source,net)
            _need(contracts[net]is not None,'unchanged_full_rail_current_contract')
        for key,request in demands.items():
            request['unchanged_full_rail_current_contract']=contracts[request['net']]
            _need(key in requests and _stable(requests[key])==_stable(request),'every_exact_mandatory_component_request')
        barrels=[];roles=[];role_cache={}
        moving=transport.get('source_process_barrel_motion')
        _need(type(moving)is list and len(moving)<=64 and len({r['uuid']for r in moving})==len(moving),'unique_owned_barrels')
        for proof in moving:
            tick();uid=proof['uuid'];a,b=old.get(uid),new.get(uid)
            if a is None or a.GetNetname()not in nets:continue
            _need(uid in changed and a.GetClass()==b.GetClass()=='PCB_VIA'and uid not in retired
                and a.GetViaType()==b.GetViaType()==pcbnew.VIATYPE_THROUGH
                and (a.TopLayer(),a.BottomLayer())==(pcbnew.F_Cu,pcbnew.B_Cu)
                and _stable(_definition(source_nodes[uid],{'at'}))==_stable(_definition(candidate_nodes[uid],{'at'}))
                and _groups(source,a)==_groups(candidate,b)
                and tuple(a.GetPosition())!=tuple(b.GetPosition()),'same_full_native_retained_barrel')
            owners=proof.get('source_owner_pad_uuids')
            _need(type(owners)is list and len(owners)==1 and owners[0]in pads,'one_actual_supply_pad_owner')
            pad,after=pads[owners[0]],targets[owners[0]]
            role_key,role,owner_ref=_supply_owner(source,candidate,proposal,pad,requests,
                board_hint,deadline,role_cache)
            _need(role['rail']==a.GetNetname()and owner_ref==pad.GetParentFootprint().GetReference()
                and _seat(source,pad,a,old)and _seat(candidate,after,b,new)
                and fab.local_pofv_via_decision(source,a)[0]and fab.local_pofv_via_decision(candidate,b)[0],
                'fresh_selected_supply_owner_and_native_POFV_seat')
            delta=[y-x for x,y in zip(tuple(a.GetPosition()),tuple(b.GetPosition()))]
            _need(proof.get('translation_nm')==delta and proof.get('owner_footprint_uuids')==[force._uid(pad.GetParentFootprint())],
                'same_barrel_owner_transform')
            first,last=pad.GetParentFootprint(),after.GetParentFootprint()
            turn=(last.GetOrientationDegrees()-first.GetOrientationDegrees())%360
            _need(turn in(0,90,180,270)and first.IsFlipped()==last.IsFlipped()
                and first.GetValue()==last.GetValue()and first.GetFPIDAsString()==last.GetFPIDAsString()
                and first.IsDNP()==last.IsDNP()and pad.GetSize()==after.GetSize()
                and pad.GetShape()==after.GetShape()and pad.GetAttribute()==after.GetAttribute()
                and tuple(pad.GetLayerSet().Seq())==tuple(after.GetLayerSet().Seq()),'same_cardinal_selected_supply_land')
            c,s=round(math.cos(math.radians(turn))),round(math.sin(math.radians(turn)))
            def projected(point):
                x,y=point[0]-first.GetPosition().x,point[1]-first.GetPosition().y
                return(last.GetPosition().x+c*x+s*y,last.GetPosition().y-s*x+c*y)
            _need(tuple(b.GetPosition())==projected(tuple(a.GetPosition()))
                and tuple(after.GetPosition())==projected(tuple(pad.GetPosition())),
                'exact_same_relative_owner_barrel_seat')
            contacts=[]
            for face in layers:
                tick()
                if not a.IsOnLayer(face):continue
                shape=a.GetEffectiveShape(face)
                # No source pour access, other barrel, direct pad contact or
                # retained stroke disappears behind a rated-edge label.
                for z in source.Zones():
                    if z.GetIsRuleArea()or not z.IsOnLayer(face):continue
                    _need(z.IsFilled()and z.HasFilledPolysForLayer(face),'known_old_barrel_zone_contacts')
                    _need(not z.GetFilledPolysList(face).Collide(shape,0),'old_barrel_power_or_other_zone_contact')
                for item in [*pads.values(),*old.values()]:
                    tick();other=force._uid(item)
                    if other==uid or not item.IsOnLayer(face)or not shape.Collide(item.GetEffectiveShape(face),0):continue
                    if other==owners[0]and item.GetClass()=='PAD':
                        _need(_contained(pad,a,face)and _contained(after,b,face),
                            'same_complete_owner_pad_contact')
                        contacts.append(dict(source_uuid=other,layer_id=face,
                            unchanged_complete_owner_pad_containment=True))
                        continue
                    if item.GetClass()=='PCB_TRACK'and other not in rated_ids:
                        # A retained keeper can touch the old barrel as well as
                        # a retired edge. It is NOT allowed to move: the fresh
                        # component must already demand a full-current path
                        # between both actual surviving contacts after motion.
                        _need(other not in retired and other not in changed
                            and item.GetNetname()==a.GetNetname()
                            and _stable(source_nodes[other])==_stable(candidate_nodes[other])
                            and _groups(source,item)==_groups(candidate,new[other]),
                            'every_old_barrel_contact_has_rated_cut_owner')
                        groups=[r for r in derived_components
                            if r['net']==a.GetNetname()and r['layer_id']==face
                            and all(sum(c['source_item_uuid']==u for c in r['surviving_contacts'])==1
                                for u in (uid,other))]
                        _need(len(groups)==1,'unique_retained_keeper_barrel_component')
                        group=groups[0]
                        floor=max(r['source_plan']['full_current_floor_nm']
                            for r in group['original_authorities'])
                        _need(item.GetWidth()>=floor,'retained_keeper_full_current_floor')
                        endpoints=[demands[k][end]for k in group['request_ids']for end in('a','b')]
                        for contact in group['surviving_contacts']:
                            if contact['source_item_uuid']not in (uid,other):continue
                            ports=contact['projected_literal_ports']
                            _need(bool(ports)and all(p in endpoints for p in ports),
                                'mandatory_retained_keeper_and_barrel_ports')
                        contacts.append(dict(source_uuid=other,layer_id=face,
                            request_ids=group['request_ids'],
                            unchanged_retained_rated_component_anchor=True))
                        continue
                    _need(item.GetNetname()==a.GetNetname()and other in rated_ids,'every_old_barrel_contact_has_rated_cut_owner')
                    group=[r for r in derived_components if other in r['source_extra_edge_uuids']]
                    _need(len(group)==1,'unique_old_barrel_component')
                    matches=[c for c in group[0]['surviving_contacts']if c['source_item_uuid']==uid
                        and other in c['contacting_owned_edge_uuids']]
                    _need(len(matches)==1,'mandatory_old_barrel_contact')
                    expected=dict(native_uuids=[uid],at_nm=list(b.GetPosition()),layers=[face])
                    _need(matches[0]['projected_literal_ports']==[expected]
                        and any(expected==demands[k][end]for k in group[0]['request_ids']for end in('a','b')),
                        'mandatory_same_physical_barrel_port')
                    contacts.append(dict(source_uuid=other,layer_id=face,request_ids=group[0]['request_ids']))
            _need(contacts,'nonempty_complete_old_barrel_contacts')
            barrels.append(uid);roles.append(dict(uuid=uid,complete_old_contacts=contacts,**{role_key:role}))
        return dict(complete=True,scope='fresh_pending_full_current_macro_reconstruction',
            track_uuids=sorted(rated_ids&changed.keys()),barrel_uuids=sorted(barrels),
            source_singleton_current_owners=fresh,source_components=derived_components,
            mandatory_request_ids=sorted(demands),retained_source_supply_barrels=roles,
            priority_motion_only=True,incoming_barrel_geometry_checks_still_required=True,
            full_saved_paths_partitions_current_field_and_Ground_still_required=True,
            current_sharing_inferred=False,current_reduced=False,barrel_capacity_qualified=False,
            cut_authority=False,routing_admitted=False,current_qualified=False,release_authority=False)
    finally:live()
