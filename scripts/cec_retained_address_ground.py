"""Retain a positively Source-grounded ADDRESS strap, not a power return.

Only an exact old factory dogbone/barrel may follow its real package rigidly.
No new conductor/hole, cut, reach, current, reference-pin or functional-return
authority is created. Every actual Ground/power-return request stays mandatory.
The enclosing complete macro still independently receives every physical delta.
"""
import copy
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_cell_row_rebuild as row
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_fab_profile as fab
import cec_force_current as force
import cec_fr as fr
import cec_ground_return_shortcut as ground
import cec_projected_ground_contact as projected
import cec_quiet_signal_requests as pins
import cec_source_ground_leaf as canonical
import cec_source_netlist_semantics as semantic
import cec_source_signal_bias_placement as rigid

KIND='source_retained_address_ground_connection'


def _need(condition,reason):
    if not condition:raise ValueError(reason)


def _lease(seconds):
    _need(type(seconds)in(int,float)and math.isfinite(seconds)and 0<seconds<=10.,
        'bounded_retained_address_ground_lease_required')
    return time.monotonic()+seconds


def _remaining(deadline):
    result=deadline-time.monotonic()
    _need(result>0,'retained_address_ground_deadline')
    return min(10.,result)


def _group(board,via):
    matches=[g for g in board.Groups()if g.ContainsItem(via)]
    _need(len(matches)==1,'retained_address_factory_group_required')
    group=matches[0];items=list(group.GetItems())
    _need(group.GetParentGroup()is None and group.GetName()==fr.LOCAL_POFV_SIGNAL_VIA_GROUP
        and 1<=len(items)<=256 and all(i.GetClass()=='PCB_VIA'for i in items),
        'exact_top_level_address_factory_via_group_required')
    return dict(uuid=force._uid(group),name=group.GetName(),locked=bool(group.IsLocked()),
        members=sorted(force._uid(i)for i in items))


def _source_pair(board,pad,deadline):
    """One bounded Source axis dogbone, never a guessed GND mesh or bypass."""
    face=cells.cec_return_escape.smd_surface_layer(pad)
    if face is None or pad.HasHole()or pad.GetAttribute()!=pcbnew.PAD_ATTRIB_SMD:return None
    candidates=[];items=list(board.GetTracks());vias={}
    _need(len(items)<=16384,'bounded_retained_address_native_inventory_required')
    for item in items:
        if item.GetClass()=='PCB_VIA':vias.setdefault(tuple(item.GetPosition()),[]).append(item)
    for track in items:
        _remaining(deadline)
        if (track.GetClass()!='PCB_TRACK'or track.GetNetname()!='GND'or track.GetLayer()!=face
                or not 0<track.GetWidth()<=350000 or not 0<track.GetLength()<=4000000):continue
        for a,b in ((track.GetStart(),track.GetEnd()),(track.GetEnd(),track.GetStart())):
            if not pad.HitTest(a,0):continue
            for via in vias.get(tuple(b),()):
                if (via.GetClass()=='PCB_VIA'and via.GetNetname()=='GND'
                        and tuple(via.GetPosition())==tuple(b)
                        and via.GetViaType()==pcbnew.VIATYPE_THROUGH
                        and via.TopLayer()==pcbnew.F_Cu and via.BottomLayer()==pcbnew.B_Cu
                        and fab.local_pofv_dogbone_matches(pad,a,b,face,pad.GetNetCode())):
                    candidates.append((track,via))
    unique={(force._uid(t),force._uid(v)):(t,v)for t,v in candidates}
    if len(unique)!=1:return None
    track,via=next(iter(unique.values()))
    # A Source branch or second surface terminal is not this retained leaf.
    for item in [*items,*(p for f in board.GetFootprints()for p in f.Pads())]:
        _remaining(deadline)
        if force._uid(item)in{force._uid(pad),force._uid(track),force._uid(via)}:continue
        if (item.GetNetname()=='GND'and item.IsOnLayer(face)
                and item.GetEffectiveShape(face).Collide(track.GetEffectiveShape(face),0)):
            return None
    return track,via


def _canonical(board,owner,pad,board_hint,deadline):
    root=canonical.source_nc._root(board,board_hint)
    _need(root is not None,'retained_address_canonical_root_required');root=root.resolve()
    files,hashes,instances=canonical._hierarchy(root,deadline)
    tree,exporter=canonical._export(root,deadline)
    _need(all(exporter.get(k)==v for k,v in semantic.metadata(tree).items()),
        'retained_address_fresh_source_semantics_required')
    components,nets,node_net=canonical._tables(tree)
    identity=canonical._identity(board,owner.GetReference(),components,instances,deadline)
    pin=pins._source_pin(identity,pad.GetNumber(),deadline)
    _need(pin['type']=='input'and node_net.get((owner.GetReference(),pad.GetNumber()))=='GND',
        'canonical_ground_tied_input_address_required')
    model=roles.footprint_contract(owner)
    for actual in owner.Pads():
        _need(node_net.get((owner.GetReference(),actual.GetNumber()))==actual.GetNetname(),
            'retained_address_complete_canonical_owner_nets_required')
        if model['pins'].get(actual.GetNumber())in('ground','power_return')and actual.GetNetname()=='GND':
            _need(pins._source_pin(identity,actual.GetNumber(),deadline)['type']=='power_in',
                'canonical_retained_address_functional_power_ground_required')
    expected=pad.GetPinFunction()or model.get('native_pin_functions',{}).get(pad.GetNumber())
    _need(not expected or pin['name']==expected,'canonical_address_pin_name_changed')
    return semantic.replay_identity(dict(root=str(root),files_sha256=hashes,exporter=exporter,
        source_symbol_uuid=identity[3]['uuid'],source_pin=pin))


def _point(parent,child,ref,point):
    first=parent.FindFootprintByReference(ref);last=child.FindFootprintByReference(ref)
    turn=(last.GetOrientationDegrees()-first.GetOrientationDegrees())%360
    _need(turn%90==0,'cardinal_retained_address_source_transform_required')
    x,y=point;ox,oy=first.GetPosition();dx,dy=x-ox,y-oy
    for _ in range(int(round(turn/90))%4):dx,dy=dy,-dx
    return [last.GetPosition().x+dx,last.GetPosition().y+dy]


def _group_geometry(parent,child,group,poses,deadline):
    """All old group axes: exact or independently positive rigid Source seats.

    Another owned cell may legitimately share this process group. Membership
    alone cannot license a moved barrel: actual Source pad containment or its
    literal dogbone, exact owner pose, unchanged dimensions and BOTH process
    checks must prove that other axis. No other track/cut authority follows.
    """
    old={force._uid(t):t for t in parent.GetTracks()};live={force._uid(t):t for t in child.GetTracks()}
    result={}
    for uid in group['members']:
        _remaining(deadline)
        _need(uid in old and uid in live,'complete_retained_address_factory_material_required')
        before,after=old[uid],live[uid]
        first=projected._via_signature(parent,before);last=projected._via_signature(child,after)
        expected=copy.deepcopy(first);owners=[]
        if first!=last:
            for ref in sorted(poses):
                fp=parent.FindFootprintByReference(ref);newfp=child.FindFootprintByReference(ref)
                _need(fp is not None and newfp is not None,'exact_retained_address_cohort_required')
                for pad in fp.Pads():
                    face=cells.cec_return_escape.smd_surface_layer(pad)
                    if (face is None or pad.HasHole()or pad.GetNetname()!=before.GetNetname()):continue
                    at=before.GetPosition();radius=before.GetWidth(face)/2
                    contained=fab._pad_contains_circle(pad,at,radius,tolerance_nm=0)
                    dogbone=any(t.GetClass()=='PCB_TRACK'and t.GetNetname()==pad.GetNetname()
                        and t.GetLayer()==face and any(tuple(b)==tuple(at)
                            and fab.local_pofv_dogbone_matches(pad,a,b,face,pad.GetNetCode())
                            for a,b in ((t.GetStart(),t.GetEnd()),(t.GetEnd(),t.GetStart())))
                        for t in parent.GetTracks())if not contained else False
                    if not contained and not dogbone:continue
                    rigid._rigid_part(fp,newfp,poses)
                    candidate=copy.deepcopy(first);candidate['at_nm']=_point(parent,child,ref,first['at_nm'])
                    if candidate==last:owners.append(force._uid(pad));expected=candidate
            _need(owners,'unowned_retained_address_factory_member_motion')
            _need(all(fab.local_pofv_via_decision(b,v,allow_source_track_body=True)[0]
                for b,v in ((parent,before),(child,after))),
                'retained_address_other_source_factory_process_required')
        _need(expected==last,'retained_address_factory_member_geometry_changed')
        result[uid]=dict(signature=expected,positive_rigid_source_pad_owners=sorted(set(owners)))
    return result


def _derive(parent,child,pad_uuid,poses,board_hint,deadline):
    source=Path(parent.GetFileName()).resolve()
    _need(source.is_file(),'saved_retained_address_source_required')
    binding=row._source_binding(parent);digest=force._hash(source)
    _need(row._source_binding(pcbnew.LoadBoard(str(source)))==binding,
        'literal_saved_retained_address_source_required')
    old={force._uid(p):p for f in parent.GetFootprints()for p in f.Pads()}
    live={force._uid(p):p for f in child.GetFootprints()for p in f.Pads()}
    _need(pad_uuid in old and pad_uuid in live,'literal_retained_address_land_required')
    before,pad=old[pad_uuid],live[pad_uuid];fp=before.GetParentFootprint();after=pad.GetParentFootprint()
    model=roles.footprint_contract(fp)
    _need(model is not None and model['pins'].get(before.GetNumber())=='address'
        and before.GetNetname()=='GND'and pad.GetNetname()=='GND'and not fp.IsDNP()
        and not fp.IsLocked()and not set(model['pins'].values())&{'power_output','switch','feedback'},
        'positive_nonreturn_manufacturer_address_required')
    roles.physical_pinmap(fp,model,board_hint=board_hint,timeout_s=_remaining(deadline))
    _need(type(poses)is dict and 1<=len(poses)<=8 and fp.GetReference()in poses,
        'bounded_exact_retained_address_cohort_required')
    target_pose=poses[fp.GetReference()]
    rigid._rigid_part(fp,after,poses)
    authority=_canonical(parent,fp,before,board_hint,deadline)
    pair=_source_pair(parent,before,deadline)
    _need(pair is not None,'unique_retained_source_address_factory_dogbone_required')
    track,via=pair;tracks={force._uid(t):t for t in child.GetTracks()}
    _need(force._uid(track)in tracks and force._uid(via)in tracks,
        'complete_retained_address_source_material_required')
    current,entry=tracks[force._uid(track)],tracks[force._uid(via)]
    expected_track=projected._anchor_signature(parent,track)
    expected_via=projected._via_signature(parent,via)
    def transform(point):return _point(parent,child,fp.GetReference(),point)
    expected_track['start_nm']=transform(expected_track['start_nm'])
    expected_track['end_nm']=transform(expected_track['end_nm'])
    expected_via['at_nm']=transform(expected_via['at_nm'])
    _need(projected._anchor_signature(child,current)==expected_track
        and projected._via_signature(child,entry)==expected_via,
        'exact_rigid_retained_address_dogbone_and_barrel_required')
    child_pair=_source_pair(child,pad,deadline)
    _need(child_pair is not None and tuple(force._uid(t)for t in child_pair)==(force._uid(track),force._uid(via)),
        'unchanged_retained_address_leaf_native_contact_relation_required')
    group=_group(parent,via)
    _need(_group(child,entry)==group,'complete_retained_address_factory_group_changed')
    members=_group_geometry(parent,child,group,poses,deadline)
    for board,item in ((parent,via),(child,entry)):
        _need(fab.local_pofv_via_decision(board,item,allow_source_track_body=True)[0],
            'retained_address_actual_source_process_required')
    source_refs=ground._reference_contacts(parent,via);saved_refs=ground._reference_contacts(child,entry)
    _need(source_refs and saved_refs==source_refs,'retained_address_reference_plane_contacts_changed')
    first=cells._shortest_track_path_mm(parent,before,via,snap_mm=.000001)
    last=cells._shortest_track_path_mm(child,pad,entry,snap_mm=.000001)
    _need(first is not None and last is not None and 0<=last<=first+1e-9 and first<=4.,
        'retained_address_native_path_missing_or_worse')
    functional=sorted(force._uid(p)for p in fp.Pads()if p.GetNetname()=='GND'
        and model['pins'].get(p.GetNumber())in('ground','power_return'))
    _need(functional,'retained_address_real_functional_ground_required')
    _need(row._source_binding(parent)==binding and force._hash(source)==digest
        and all(force._hash(path)==sha for path,sha in authority['files_sha256'].items())
        and force._hash(authority['exporter']['exporter'])==authority['exporter']['exporter_sha256'],
        'retained_address_source_changed')
    _remaining(deadline)
    return json.loads(json.dumps(dict(schema=1,scope=KIND,source=str(source),source_sha256=digest,
        source_native_binding=binding,board_hint=board_hint,pad_uuid=pad_uuid,owner=fp.GetReference(),
        target_pose=list(target_pose),poses=poses,manufacturer=model,canonical=authority,
        retained_track=expected_track,retained_barrel=expected_via,factory_group=group,
        independently_observed_factory_member_geometry=members,
        source_plane_contacts=source_refs,source_path_mm=first,saved_path_mm=last,
        functional_ground_pad_uuids=functional,new_copper_or_hole_authority=False,
        functional_return_or_immediate_return_qualified=False,current_authority=False,
        other_group_member_motion_authorized=False,release_authority=False),allow_nan=False))


def _functional(board,requests,proof,deadline):
    import cec_constraints as constraints
    import cec_cell_escape_replan as escape
    import cec_ground_return_policy as policy
    selected=None;entries=None
    for uid in proof['functional_ground_pad_uuids']:
        request=requests.get('ground:'+uid)
        _need(request is not None and request.get('kind')=='ground'and request.get('net')=='GND'
            and request.get('a',{}).get('pad_uuid')==uid,
            'retained_address_functional_ground_obligation_must_remain')
        pad=next(p for f in board.GetFootprints()for p in f.Pads()if force._uid(p)==uid)
        _need(request['a'].get('at_nm')==list(pad.GetPosition())
            and request['a'].get('layers')==list(map(int,pad.GetLayerSet().CuStack())),
            'retained_address_exact_functional_ground_endpoint_required')
        entry=request.get('selected_bypass_entry')
        if entry is not None:
            if entries is None:
                with force._thermal_hint(proof['board_hint']):
                    assignment=constraints._device_bypass_assignment(board,project_max_mm=3.5)
                selected={}
                for item in assignment['assigned'].values():
                    req=item['requirement']
                    if req['ref']!=proof['owner']or(req.get('return_rail')or'GND')!='GND':continue
                    _need(item['cap_ref']not in selected,'unique_retained_address_functional_bypass_required')
                    selected[item['cap_ref']]=dict(owner=req['ref'],pin=str(req['pin']),rail=req['rail'])
                entries=escape.assigned_ground_entries(board,selected,board_hint=proof['board_hint'])
            _need(json.loads(json.dumps(entries.get(uid)))==entry,
                'fresh_retained_address_functional_ground_hierarchy_required')
        expected=policy.reach(pad,{}if entry is None else entries)
        _need(request.get('reach_mm')==expected,'unchanged_retained_address_functional_ground_reach_required')
        _remaining(deadline)


def convert(parent,child,proposal,requests,*,timeout_s=10.):
    deadline=_lease(timeout_s);result=copy.deepcopy(requests)
    _need(type(proposal)is dict and type(proposal.get('poses'))is dict
        and type(proposal.get('board_hint'))is str and type(requests)is dict and len(requests)<=64,
        'bounded_retained_address_request_context_required')
    pads={force._uid(p):p for f in parent.GetFootprints()for p in f.Pads()}
    for key,request in requests.items():
        if request.get('kind')!='ground'or request.get('net')!='GND':continue
        if any(k in request for k in ('required_new_ground_dogbone','required_projected_ground_entry')):continue
        pad=pads.get(request.get('a',{}).get('pad_uuid'));model=roles.footprint_contract(pad.GetParentFootprint())if pad else None
        if not model or model['pins'].get(pad.GetNumber())!='address':continue
        owner=pad.GetParentFootprint().GetReference()
        if owner not in proposal['poses']or _source_pair(parent,pad,deadline)is None:continue
        proof=_derive(parent,child,force._uid(pad),proposal['poses'],proposal['board_hint'],deadline)
        _functional(child,requests,proof,deadline)
        result[key]=dict(kind=KIND,net='GND',a=copy.deepcopy(request['a']),
            source_retained_logical_address=proof)
    _remaining(deadline)
    return result


def observe(child,request,requests,*,timeout_s=10.):
    deadline=_lease(timeout_s)
    _need(request.get('kind')==KIND and request.get('net')=='GND',
        'positive_retained_address_connection_request_required')
    proof=request.get('source_retained_logical_address')
    _need(type(proof)is dict and request.get('a',{}).get('pad_uuid')==proof.get('pad_uuid'),
        'exact_retained_address_request_required')
    source=Path(proof['source'])
    _need(source.is_file()and force._hash(source)==proof['source_sha256'],
        'retained_address_source_file_changed')
    parent=pcbnew.LoadBoard(str(source))
    fresh=_derive(parent,child,proof['pad_uuid'],proof['poses'],proof['board_hint'],deadline)
    _need(fresh==proof,'fresh_retained_address_source_proof_required')
    _functional(child,requests,proof,deadline)
    pad=next(p for f in child.GetFootprints()for p in f.Pads()if force._uid(p)==proof['pad_uuid'])
    _need(list(pad.GetPosition())==request['a'].get('at_nm')
        and list(map(int,pad.GetLayerSet().CuStack()))==request['a'].get('layers'),
        'actual_retained_address_request_endpoint_required')
    return dict(ok=True,scope=KIND,source_path_mm=proof['source_path_mm'],saved_path_mm=proof['saved_path_mm'],
        via_uuid=proof['retained_barrel']['uuid'],functional_return_or_immediate_return_qualified=False,
        functional_ground_obligations_preserved=True,new_copper_or_hole_authority=False,
        current_authority=False,release_authority=False)
